"""Configuration loading with YAML defaults and user overrides.

Implements a two-layer config strategy: a bundled ``default.yaml`` (shipped
via ``importlib.resources``) provides sensible defaults, while an optional
user file at ``~/.downloads-agent/config.yaml`` overrides individual values
through recursive deep-merge. This lets users change one setting without
re-specifying the entire config.

Validation is performed eagerly in ``Config.__post_init__`` so invalid
configurations fail fast at load time rather than mid-execution.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.resources import files, as_file
from pathlib import Path
from typing import Any

import yaml

from downloads_agent.errors import ConfigError


_DEFAULT_CONFIG_REF = files("downloads_agent") / "data" / "default.yaml"
USER_CONFIG_DIR = Path.home() / ".downloads-agent"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.yaml"


_KNOWN_CONFIG_KEYS = frozenset({
    "downloads_dir", "archive_dir", "inactive_days", "max_operations",
    "date_subfolder", "categories", "ignore_names", "ignore_dirs",
    "ignore_patterns",  # backward compat alias
})


@dataclass
class Config:
    """Validated application configuration.

    All fields are populated by ``load_config()`` from merged YAML sources.
    Validation runs in ``__post_init__``, so constructing a ``Config`` with
    invalid values raises ``ConfigError`` immediately.

    Attributes:
        downloads_dir: Absolute path to the monitored directory (default ~/Downloads).
        archive_dir: Absolute path to the archive root (default ~/Downloads/Archive).
        inactive_days: Minimum days since last use before a file is considered inactive.
        max_operations: Safety cap on moves per run (enforced only on ``--execute``).
        date_subfolder: Whether to create YYYY-MM subdirectories within categories.
        categories: Mapping of category name → list of file extensions (lowercase, no dot).
        ignore_names: Filenames to skip during scanning (e.g. ``.DS_Store``).
        ignore_dirs: Directory names to skip during scanning (e.g. ``Archive``).
    """

    downloads_dir: Path
    archive_dir: Path
    inactive_days: int
    max_operations: int
    date_subfolder: bool
    categories: dict[str, list[str]]
    ignore_names: list[str]
    ignore_dirs: list[str]

    def __post_init__(self) -> None:
        """Validate field types, ranges, and cross-field invariants.

        Raises:
            ConfigError: On type mismatch, out-of-range value, path conflict,
                empty categories, or archive-inside-downloads without ignore.
        """
        if not isinstance(self.inactive_days, int):
            raise ConfigError(
                f"inactive_days must be an integer, got {type(self.inactive_days).__name__}"
            )
        if self.inactive_days < 1:
            raise ConfigError(
                f"inactive_days must be >= 1, got {self.inactive_days}"
            )
        if not isinstance(self.max_operations, int):
            raise ConfigError(
                f"max_operations must be an integer, got {type(self.max_operations).__name__}"
            )
        if self.max_operations < 1:
            raise ConfigError(
                f"max_operations must be >= 1, got {self.max_operations}"
            )
        if self.downloads_dir.resolve() == self.archive_dir.resolve():
            raise ConfigError(
                "downloads_dir and archive_dir must be different directories"
            )
        if not isinstance(self.categories, dict):
            raise ConfigError(
                f"categories must be a mapping, got {type(self.categories).__name__}"
            )
        if not self.categories:
            raise ConfigError("categories must not be empty")
        # Guard against archiving the archive itself: if archive_dir is a
        # subdirectory of downloads_dir, its top-level folder must be excluded
        # from scanning via ignore_dirs. Without this, the scanner would treat
        # archived files as new candidates and re-archive them indefinitely.
        try:
            archive_rel = self.archive_dir.resolve().relative_to(
                self.downloads_dir.resolve()
            )
            if archive_rel.parts:
                top_dir = archive_rel.parts[0]
                if top_dir not in self.ignore_dirs:
                    raise ConfigError(
                        f"archive_dir '{self.archive_dir.name}' is inside downloads_dir "
                        f"but not in ignore_dirs. Add '{top_dir}' to ignore_dirs to "
                        f"prevent archiving the archive itself."
                    )
        except ValueError:
            pass  # archive_dir is not inside downloads_dir — fine


def _expand_path(p: str) -> Path:
    """Expand ``~`` and resolve to an absolute path."""
    return Path(p).expanduser().resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, wrapping parse/IO errors into ``ConfigError``."""
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML syntax error in {path}: {e}") from e
    except OSError as e:
        raise ConfigError(f"Cannot read config file {path}: {e}") from e


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*; override values win.

    Nested dicts are merged key-by-key so that a user config like
    ``{"categories": {"Custom": ["xyz"]}}`` adds a category without
    erasing the built-in ones. Non-dict values (lists, scalars) are
    replaced wholesale.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> Config:
    """Load config from bundled defaults merged with optional user overrides.

    The merge strategy is: deep-merge user values on top of ``default.yaml``,
    then construct and validate a ``Config`` dataclass. Unknown keys produce
    a stderr warning (forward-compatible), and the legacy ``ignore_patterns``
    key is silently renamed to ``ignore_names`` for backward compatibility.

    Args:
        config_path: Explicit path to a user config file. Falls back to
            ``~/.downloads-agent/config.yaml`` if not provided.

    Returns:
        A fully validated ``Config`` instance.

    Raises:
        ConfigError: On YAML syntax errors, unreadable files, or validation
            failures in the resulting ``Config``.
    """
    with as_file(_DEFAULT_CONFIG_REF) as default_path:
        base = _load_yaml(default_path)

    user_path = config_path or USER_CONFIG_PATH
    if user_path.exists():
        user = _load_yaml(user_path)
        # Backward compat: rename old key before merge
        if "ignore_patterns" in user and "ignore_names" not in user:
            user["ignore_names"] = user.pop("ignore_patterns")
        merged = _deep_merge(base, user)
        # Warn about unknown config keys
        for key in user:
            if key not in _KNOWN_CONFIG_KEYS:
                print(f"warning: unknown config key '{key}', ignored", file=sys.stderr)
    else:
        merged = base

    ignore_names = merged.get("ignore_names", merged.get("ignore_patterns", []))

    return Config(
        downloads_dir=_expand_path(merged["downloads_dir"]),
        archive_dir=_expand_path(merged["archive_dir"]),
        inactive_days=merged["inactive_days"],
        max_operations=merged["max_operations"],
        date_subfolder=merged["date_subfolder"],
        categories=merged["categories"],
        ignore_names=ignore_names,
        ignore_dirs=merged["ignore_dirs"],
    )

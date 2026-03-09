"""Configuration loading with YAML defaults and user overrides."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files, as_file
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG_REF = files("downloads_agent") / "data" / "default.yaml"
USER_CONFIG_DIR = Path.home() / ".downloads-agent"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    downloads_dir: Path
    archive_dir: Path
    inactive_days: int
    max_operations: int
    date_subfolder: bool
    categories: dict[str, list[str]]
    ignore_names: list[str]
    ignore_dirs: list[str]


def _expand_path(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base. Override values win; dicts are merged recursively."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> Config:
    """Load config from default.yaml merged with optional user overrides."""
    with as_file(_DEFAULT_CONFIG_REF) as default_path:
        base = _load_yaml(default_path)

    user_path = config_path or USER_CONFIG_PATH
    if user_path.exists():
        user = _load_yaml(user_path)
        # Backward compat: rename old key before merge
        if "ignore_patterns" in user and "ignore_names" not in user:
            user["ignore_names"] = user.pop("ignore_patterns")
        merged = _deep_merge(base, user)
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

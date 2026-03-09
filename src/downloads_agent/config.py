"""Configuration loading with YAML defaults and user overrides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "default.yaml"
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
    ignore_patterns: list[str]
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
    base = _load_yaml(DEFAULT_CONFIG_PATH)

    user_path = config_path or USER_CONFIG_PATH
    if user_path.exists():
        user = _load_yaml(user_path)
        merged = _deep_merge(base, user)
    else:
        merged = base

    return Config(
        downloads_dir=_expand_path(merged["downloads_dir"]),
        archive_dir=_expand_path(merged["archive_dir"]),
        inactive_days=merged["inactive_days"],
        max_operations=merged["max_operations"],
        date_subfolder=merged["date_subfolder"],
        categories=merged["categories"],
        ignore_patterns=merged["ignore_patterns"],
        ignore_dirs=merged["ignore_dirs"],
    )

"""Tests for config module."""

from __future__ import annotations

from pathlib import Path

import yaml

from downloads_agent.config import load_config, _deep_merge, Config


def test_load_config_defaults() -> None:
    """Default config should load without errors."""
    config = load_config(config_path=Path("/nonexistent/path.yaml"))
    assert isinstance(config, Config)
    assert config.inactive_days == 30
    assert config.max_operations == 500
    assert config.date_subfolder is True


def test_load_config_user_override(tmp_path: Path) -> None:
    """User config should override default values."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text(yaml.dump({
        "inactive_days": 7,
        "max_operations": 100,
    }))

    config = load_config(config_path=user_config)
    assert config.inactive_days == 7
    assert config.max_operations == 100
    # Non-overridden values should remain default
    assert config.date_subfolder is True


def test_load_config_category_merge(tmp_path: Path) -> None:
    """User categories should merge with defaults."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text(yaml.dump({
        "categories": {
            "Custom": ["abc", "def"],
        },
    }))

    config = load_config(config_path=user_config)
    assert "Custom" in config.categories
    # Default categories should still exist (deep merge)
    assert "Documents" in config.categories


def test_deep_merge_basic() -> None:
    """_deep_merge should recursively merge dicts."""
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}


def test_deep_merge_override_replaces_non_dict() -> None:
    """_deep_merge should replace non-dict values."""
    base = {"a": [1, 2]}
    override = {"a": [3, 4]}
    result = _deep_merge(base, override)
    assert result == {"a": [3, 4]}


def test_load_config_missing_yaml(tmp_path: Path) -> None:
    """Missing user config should use defaults only."""
    missing = tmp_path / "no_such_file.yaml"
    config = load_config(config_path=missing)
    assert isinstance(config, Config)
    assert config.inactive_days == 30


def test_load_config_ignore_names_backward_compat(tmp_path: Path) -> None:
    """Old 'ignore_patterns' key should still work in user config."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text(yaml.dump({
        "ignore_patterns": [".DS_Store", ".custom"],
    }))

    config = load_config(config_path=user_config)
    assert ".DS_Store" in config.ignore_names
    assert ".custom" in config.ignore_names

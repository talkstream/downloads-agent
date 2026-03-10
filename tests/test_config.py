"""Tests for config module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from downloads_agent.config import load_config, _deep_merge, Config
from downloads_agent.errors import ConfigError


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


def test_config_negative_inactive_days() -> None:
    """negative inactive_days should raise ConfigError."""
    with pytest.raises(ConfigError, match="inactive_days must be >= 1"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/dl/Archive"),
            inactive_days=-1,
            max_operations=500,
            date_subfolder=True,
            categories={"Documents": ["pdf"]},
            ignore_names=[],
            ignore_dirs=["Archive"],
        )


def test_config_zero_max_operations() -> None:
    """zero max_operations should raise ConfigError."""
    with pytest.raises(ConfigError, match="max_operations must be >= 1"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/dl/Archive"),
            inactive_days=30,
            max_operations=0,
            date_subfolder=True,
            categories={"Documents": ["pdf"]},
            ignore_names=[],
            ignore_dirs=["Archive"],
        )


def test_config_same_downloads_and_archive_dir() -> None:
    """downloads_dir == archive_dir should raise ConfigError."""
    with pytest.raises(ConfigError, match="must be different"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/dl"),
            inactive_days=30,
            max_operations=500,
            date_subfolder=True,
            categories={"Documents": ["pdf"]},
            ignore_names=[],
            ignore_dirs=[],
        )


def test_config_empty_categories() -> None:
    """empty categories should raise ConfigError."""
    with pytest.raises(ConfigError, match="categories must not be empty"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/dl/Archive"),
            inactive_days=30,
            max_operations=500,
            date_subfolder=True,
            categories={},
            ignore_names=[],
            ignore_dirs=["Archive"],
        )


def test_config_archive_inside_downloads_without_ignore() -> None:
    """archive_dir inside downloads_dir must be in ignore_dirs."""
    with pytest.raises(ConfigError, match="not in ignore_dirs"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/dl/Backup"),
            inactive_days=30,
            max_operations=500,
            date_subfolder=True,
            categories={"Documents": ["pdf"]},
            ignore_names=[],
            ignore_dirs=[],
        )


def test_config_archive_inside_downloads_with_ignore() -> None:
    """archive_dir inside downloads_dir should pass if in ignore_dirs."""
    config = Config(
        downloads_dir=Path("/tmp/dl"),
        archive_dir=Path("/tmp/dl/Backup"),
        inactive_days=30,
        max_operations=500,
        date_subfolder=True,
        categories={"Documents": ["pdf"]},
        ignore_names=[],
        ignore_dirs=["Backup"],
    )
    assert config.archive_dir == Path("/tmp/dl/Backup")


def test_config_archive_outside_downloads() -> None:
    """archive_dir outside downloads_dir should not require ignore_dirs."""
    config = Config(
        downloads_dir=Path("/tmp/dl"),
        archive_dir=Path("/tmp/archive"),
        inactive_days=30,
        max_operations=500,
        date_subfolder=True,
        categories={"Documents": ["pdf"]},
        ignore_names=[],
        ignore_dirs=[],
    )
    assert config.archive_dir == Path("/tmp/archive")


def test_config_invalid_inactive_days_type() -> None:
    """String inactive_days should raise ConfigError."""
    with pytest.raises(ConfigError, match="must be an integer"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/archive"),
            inactive_days="thirty",  # type: ignore[arg-type]
            max_operations=500,
            date_subfolder=True,
            categories={"Documents": ["pdf"]},
            ignore_names=[],
            ignore_dirs=[],
        )


def test_config_invalid_categories_type() -> None:
    """Non-dict categories should raise ConfigError."""
    with pytest.raises(ConfigError, match="must be a mapping"):
        Config(
            downloads_dir=Path("/tmp/dl"),
            archive_dir=Path("/tmp/archive"),
            inactive_days=30,
            max_operations=500,
            date_subfolder=True,
            categories=["Documents"],  # type: ignore[arg-type]
            ignore_names=[],
            ignore_dirs=[],
        )


def test_load_config_malformed_yaml(tmp_path: Path) -> None:
    """Malformed YAML should raise ConfigError."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text("{ broken yaml: [")

    with pytest.raises(ConfigError, match="YAML syntax error"):
        load_config(config_path=user_config)


def test_config_unknown_key_warning(tmp_path: Path, capsys) -> None:
    """Unknown config keys should produce a warning in stderr."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text(yaml.dump({
        "inactive_days": 14,
        "some_unknown_key": "value",
    }))

    load_config(config_path=user_config)
    captured = capsys.readouterr()
    assert "unknown config key 'some_unknown_key'" in captured.err

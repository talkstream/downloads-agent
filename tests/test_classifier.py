"""Tests for classifier module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from downloads_agent.classifier import classify
from downloads_agent.config import Config


def test_classify_known_extensions(default_config: Config) -> None:
    """Known extensions should map to their categories."""
    assert classify("pdf", False, default_config) == "Documents"
    assert classify("jpg", False, default_config) == "Images"
    assert classify("mp4", False, default_config) == "Videos"
    assert classify("mp3", False, default_config) == "Audio"
    assert classify("py", False, default_config) == "Code"
    assert classify("zip", False, default_config) == "Archives"


def test_classify_case_insensitive(default_config: Config) -> None:
    """Classification should be case-insensitive."""
    assert classify("PDF", False, default_config) == "Documents"
    assert classify("Jpg", False, default_config) == "Images"


def test_classify_unknown_extension(default_config: Config) -> None:
    """Unknown extensions should map to 'Other'."""
    assert classify("xyz", False, default_config) == "Other"
    assert classify("qwerty", False, default_config) == "Other"


def test_classify_empty_extension(default_config: Config) -> None:
    """Empty extension should map to 'Other'."""
    assert classify("", False, default_config) == "Other"


def test_classify_directory(default_config: Config) -> None:
    """Directories should always map to 'Folders'."""
    assert classify("", True, default_config) == "Folders"
    assert classify("pdf", True, default_config) == "Folders"


def _load_extension_params() -> list[tuple[str, str]]:
    """Load all extensions from default.yaml for parameterized tests."""
    from importlib.resources import files, as_file

    ref = files("downloads_agent") / "data" / "default.yaml"
    with as_file(ref) as p:
        data = yaml.safe_load(p.read_text())

    params = []
    for category, extensions in data["categories"].items():
        if category == "Other" or not extensions:
            continue
        for ext in extensions:
            params.append((ext, category))
    return params


def _make_default_config() -> Config:
    """Create a Config with all default.yaml categories for parameterized tests."""
    from importlib.resources import files, as_file

    ref = files("downloads_agent") / "data" / "default.yaml"
    with as_file(ref) as p:
        data = yaml.safe_load(p.read_text())

    return Config(
        downloads_dir=Path("/tmp/Downloads"),
        archive_dir=Path("/tmp/Downloads/Archive"),
        inactive_days=30,
        max_operations=500,
        date_subfolder=True,
        categories=data["categories"],
        ignore_names=[],
        ignore_dirs=[],
    )


_DEFAULT_CONFIG = _make_default_config()


@pytest.mark.parametrize("ext,expected_category", _load_extension_params())
def test_classify_all_default_extensions(ext: str, expected_category: str) -> None:
    """Every extension from default.yaml should classify to its configured category."""
    assert classify(ext, False, _DEFAULT_CONFIG) == expected_category

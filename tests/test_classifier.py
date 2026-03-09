"""Tests for classifier module."""

from __future__ import annotations

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

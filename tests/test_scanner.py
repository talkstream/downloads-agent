"""Tests for scanner module."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from downloads_agent.config import Config
from downloads_agent.scanner import scan


def test_scan_returns_only_inactive(populated_downloads: Config) -> None:
    """Active files should not appear in scan results."""
    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(populated_downloads)

    names = {item.name for item in items}
    # Old files should be present
    assert "report.pdf" in names
    assert "photo.jpg" in names
    # Active files should NOT be present
    assert "recent.pdf" not in names
    assert "fresh.jpg" not in names


def test_scan_ignores_hidden_files(populated_downloads: Config) -> None:
    """Hidden files (starting with .) should be skipped."""
    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(populated_downloads)

    names = {item.name for item in items}
    assert ".DS_Store" not in names


def test_scan_ignores_configured_dirs(populated_downloads: Config) -> None:
    """Directories in ignore_dirs should be skipped."""
    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(populated_downloads)

    names = {item.name for item in items}
    assert "Archive" not in names


def test_scan_includes_old_directories(populated_downloads: Config) -> None:
    """Old directories should be included as items."""
    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(populated_downloads)

    dirs = [item for item in items if item.is_dir]
    dir_names = {d.name for d in dirs}
    assert "old_project" in dir_names
    assert "active_project" not in dir_names


def test_scan_collects_correct_metadata(populated_downloads: Config) -> None:
    """FileInfo should have correct extension and size."""
    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(populated_downloads)

    pdf = next(item for item in items if item.name == "report.pdf")
    assert pdf.extension == "pdf"
    assert pdf.size > 0
    assert not pdf.is_dir


def test_scan_empty_directory(default_config: Config) -> None:
    """Scan should return empty list for empty directory."""
    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(default_config)

    assert items == []


def test_scan_nonexistent_directory(default_config: Config) -> None:
    """Scan should return empty list if directory doesn't exist."""
    import shutil
    shutil.rmtree(default_config.downloads_dir)

    items = scan(default_config)
    assert items == []


def test_scan_respects_spotlight_date(populated_downloads: Config) -> None:
    """If Spotlight returns a recent date, file should be considered active."""
    recent = datetime.now(timezone.utc) - timedelta(days=5)

    def mock_spotlight(path: Path) -> datetime | None:
        if path.name == "report.pdf":
            return recent
        return None

    with patch("downloads_agent.scanner._get_spotlight_last_used", side_effect=mock_spotlight):
        items = scan(populated_downloads)

    names = {item.name for item in items}
    # report.pdf has recent spotlight date → should not be archived
    assert "report.pdf" not in names
    # Others still should be
    assert "photo.jpg" in names

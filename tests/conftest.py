"""Shared fixtures for downloads-agent tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from downloads_agent.config import Config


@pytest.fixture
def default_config(tmp_path: Path) -> Config:
    """Config pointing at a temporary downloads directory."""
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    archive = downloads / "Archive"

    return Config(
        downloads_dir=downloads,
        archive_dir=archive,
        inactive_days=30,
        max_operations=500,
        date_subfolder=True,
        categories={
            "Documents": ["pdf", "docx", "txt", "csv"],
            "Images": ["jpg", "jpeg", "png", "gif", "svg"],
            "Videos": ["mp4", "mov", "mkv"],
            "Audio": ["mp3", "wav", "flac"],
            "Code": ["py", "js", "ts", "json", "yaml"],
            "Archives": ["zip", "tar", "gz", "dmg"],
            "Other": [],
        },
        ignore_patterns=[".DS_Store", ".localized"],
        ignore_dirs=["Archive"],
    )


@pytest.fixture
def populated_downloads(default_config: Config) -> Config:
    """Config with a populated Downloads directory containing old and new files."""
    downloads = default_config.downloads_dir
    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=60)).timestamp()
    new_ts = (now - timedelta(days=5)).timestamp()

    # Old files (inactive)
    old_files = [
        "report.pdf", "photo.jpg", "video.mp4", "song.mp3",
        "script.py", "archive.zip", "notes.txt", "data.csv",
        "unknown.xyz",
    ]
    for name in old_files:
        f = downloads / name
        f.write_text(f"content of {name}")
        os.utime(f, (old_ts, old_ts))

    # New files (active — won't be archived)
    new_files = ["recent.pdf", "fresh.jpg"]
    for name in new_files:
        f = downloads / name
        f.write_text(f"content of {name}")
        os.utime(f, (new_ts, new_ts))

    # Old directory
    old_dir = downloads / "old_project"
    old_dir.mkdir()
    (old_dir / "file.txt").write_text("inner file")
    os.utime(old_dir, (old_ts, old_ts))

    # New directory
    new_dir = downloads / "active_project"
    new_dir.mkdir()
    (new_dir / "file.txt").write_text("inner file")
    os.utime(new_dir, (new_ts, new_ts))

    # Hidden file (should be ignored)
    (downloads / ".DS_Store").write_text("hidden")

    # Archive directory (should be ignored)
    archive = downloads / "Archive"
    archive.mkdir()

    return default_config

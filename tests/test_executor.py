"""Tests for executor module."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from downloads_agent.config import Config
from downloads_agent.planner import build_plan, MovePlan, MoveOperation
from downloads_agent.scanner import FileInfo
from downloads_agent.executor import execute, LOCK_FILE


def _make_file_info(
    path: Path,
    ext: str = "pdf",
    is_dir: bool = False,
    size: int = 1024,
    days_old: int = 60,
) -> FileInfo:
    """Helper to create FileInfo instances."""
    now = datetime.now(timezone.utc)
    mod_date = now - timedelta(days=days_old)
    return FileInfo(
        path=path,
        name=path.name,
        extension=ext,
        size=size,
        is_dir=is_dir,
        last_used=mod_date,
        modification_date=mod_date,
    )


def test_execute_moves_files(default_config: Config) -> None:
    """Files should be physically moved to archive."""
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test content")

    items = [_make_file_info(f, "pdf", size=len("test content"))]
    plan = build_plan(items, default_config)

    with patch("downloads_agent.executor.LOCK_DIR", downloads / ".lock_dir"), \
         patch("downloads_agent.executor.LOCK_FILE", downloads / ".lock_dir" / "lock"), \
         patch("downloads_agent.executor.LOG_DIR", downloads / ".lock_dir" / "logs"):
        result = execute(plan)

    assert result.moved == 1
    assert result.failed == 0
    assert not f.exists()
    assert result.log_path.exists()


def test_execute_writes_transaction_log(default_config: Config) -> None:
    """Transaction log should be valid JSON with correct structure."""
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test")

    items = [_make_file_info(f, "pdf", size=4)]
    plan = build_plan(items, default_config)

    lock_dir = downloads / ".lock_dir"
    with patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"), \
         patch("downloads_agent.executor.LOG_DIR", lock_dir / "logs"):
        result = execute(plan)

    log_data = json.loads(result.log_path.read_text())
    assert "timestamp" in log_data
    assert "version" in log_data
    assert "operations" in log_data
    assert log_data["operations"][0]["status"] == "ok"


def test_execute_creates_directories(default_config: Config) -> None:
    """Target archive directories should be created automatically."""
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test")

    items = [_make_file_info(f, "pdf", size=4)]
    plan = build_plan(items, default_config)

    lock_dir = downloads / ".lock_dir"
    with patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"), \
         patch("downloads_agent.executor.LOG_DIR", lock_dir / "logs"):
        execute(plan)

    assert default_config.archive_dir.exists()


def test_execute_moves_directories(default_config: Config) -> None:
    """Directories should be moved entirely to Archive/Folders/."""
    downloads = default_config.downloads_dir
    d = downloads / "old_project"
    d.mkdir()
    (d / "inner.txt").write_text("inner")

    items = [_make_file_info(d, "", is_dir=True, size=5)]
    plan = build_plan(items, default_config)

    lock_dir = downloads / ".lock_dir"
    with patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"), \
         patch("downloads_agent.executor.LOG_DIR", lock_dir / "logs"):
        result = execute(plan)

    assert result.moved == 1
    assert not d.exists()
    archived = default_config.archive_dir / "Folders" / "old_project"
    assert archived.exists()
    assert (archived / "inner.txt").read_text() == "inner"


def test_execute_lockfile_cleanup(default_config: Config) -> None:
    """Lockfile should be cleaned up after execution."""
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test")

    items = [_make_file_info(f, "pdf", size=4)]
    plan = build_plan(items, default_config)

    lock_dir = downloads / ".lock_dir"
    lock_file = lock_dir / "lock"
    with patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_file), \
         patch("downloads_agent.executor.LOG_DIR", lock_dir / "logs"):
        execute(plan)

    assert not lock_file.exists()

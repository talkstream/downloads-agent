"""Tests for executor module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from downloads_agent.config import Config
from downloads_agent.planner import build_plan
from downloads_agent.executor import execute

from conftest import make_file_info


def _patch_executor(tmp_path: Path):
    """Patch LOCK_DIR, LOCK_FILE, and LOG_DIR for executor tests."""
    lock_dir = tmp_path / ".lock_dir"
    return (
        patch("downloads_agent.executor.LOCK_DIR", lock_dir),
        patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"),
        patch("downloads_agent.executor.LOG_DIR", lock_dir / "logs"),
    )


def test_execute_moves_files(default_config: Config) -> None:
    """Files should be physically moved to archive."""
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test content")

    items = [make_file_info(f, "pdf", size=len("test content"))]
    plan = build_plan(items, default_config)

    p1, p2, p3 = _patch_executor(downloads)
    with p1, p2, p3:
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

    items = [make_file_info(f, "pdf", size=4)]
    plan = build_plan(items, default_config)

    p1, p2, p3 = _patch_executor(downloads)
    with p1, p2, p3:
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

    items = [make_file_info(f, "pdf", size=4)]
    plan = build_plan(items, default_config)

    p1, p2, p3 = _patch_executor(downloads)
    with p1, p2, p3:
        execute(plan)

    assert default_config.archive_dir.exists()


def test_execute_moves_directories(default_config: Config) -> None:
    """Directories should be moved entirely to Archive/Folders/."""
    downloads = default_config.downloads_dir
    d = downloads / "old_project"
    d.mkdir()
    (d / "inner.txt").write_text("inner")

    items = [make_file_info(d, "", is_dir=True, size=5)]
    plan = build_plan(items, default_config)

    p1, p2, p3 = _patch_executor(downloads)
    with p1, p2, p3:
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

    items = [make_file_info(f, "pdf", size=4)]
    plan = build_plan(items, default_config)

    lock_dir = downloads / ".lock_dir"
    lock_file = lock_dir / "lock"
    p1, p2, p3 = _patch_executor(downloads)
    with p1, p2, p3:
        execute(plan)

    assert not lock_file.exists()


def test_execute_collision_at_execution_time(default_config: Config) -> None:
    """If target file was created between plan and execute, collision should be resolved."""
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test content")

    items = [make_file_info(f, "pdf", size=len("test content"))]
    plan = build_plan(items, default_config)

    # Create the target file before execution (simulates race condition)
    dest = plan.operations[0].destination
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("already exists")

    p1, p2, p3 = _patch_executor(downloads)
    with p1, p2, p3:
        result = execute(plan)

    assert result.moved == 1
    assert not f.exists()
    # Original destination should still have old content
    assert dest.read_text() == "already exists"
    # New file should be at _1 suffix path
    collision_dest = dest.parent / f"{dest.stem}_1{dest.suffix}"
    assert collision_dest.exists()
    assert collision_dest.read_text() == "test content"

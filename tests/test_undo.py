"""Tests for undo module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from downloads_agent.errors import DownloadsAgentError
from downloads_agent.undo import undo, list_runs, _cleanup_empty_dirs


def _create_log(log_dir: Path, name: str, operations: list[dict]) -> Path:
    """Helper to create a transaction log file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.json"
    log_data = {
        "timestamp": "2026-01-01T00:00:00",
        "version": "0.1.0",
        "operations": operations,
        "summary": {"files_moved": len(operations), "total_size": 0},
    }
    log_path.write_text(json.dumps(log_data))
    return log_path


def _patch_undo(tmp_path: Path):
    """Patch LOG_DIR and lock for undo tests."""
    log_dir = tmp_path / "logs"
    lock_dir = tmp_path / "lock_dir"
    return (
        patch("downloads_agent.undo.LOG_DIR", log_dir),
        patch("downloads_agent.executor.LOCK_DIR", lock_dir),
        patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"),
    )


def test_undo_restores_files(tmp_path: Path) -> None:
    """Undo should move files back to their original locations."""
    # Setup: create "archived" file
    src = tmp_path / "Downloads" / "doc.pdf"
    dst = tmp_path / "Archive" / "Documents" / "doc.pdf"
    dst.parent.mkdir(parents=True)
    dst.write_text("content")

    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-01_090000", [
        {"source": str(src), "destination": str(dst), "size": 7, "is_dir": False, "status": "ok"},
    ])

    src.parent.mkdir(parents=True, exist_ok=True)

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        result = undo()

    assert result.restored == 1
    assert src.exists()
    assert src.read_text() == "content"


def test_undo_specific_run(tmp_path: Path) -> None:
    """Undo should work with a specific run_id."""
    src = tmp_path / "Downloads" / "pic.jpg"
    dst = tmp_path / "Archive" / "Images" / "pic.jpg"
    dst.parent.mkdir(parents=True)
    dst.write_text("image data")

    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-15_100000", [
        {"source": str(src), "destination": str(dst), "size": 10, "is_dir": False, "status": "ok"},
    ])

    src.parent.mkdir(parents=True, exist_ok=True)

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        result = undo("2026-01-15_100000")

    assert result.restored == 1
    assert result.log_file == "2026-01-15_100000.json"


def test_undo_skips_errors(tmp_path: Path) -> None:
    """Undo should skip operations that had errors."""
    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-01_090000", [
        {"source": "/no/such", "destination": "/no/dst", "size": 0, "is_dir": False, "status": "error"},
    ])

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        result = undo()

    assert result.skipped == 1
    assert result.restored == 0


def test_undo_missing_log(tmp_path: Path) -> None:
    """Undo should raise FileNotFoundError for missing logs."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        with pytest.raises(DownloadsAgentError, match="No transaction logs found"):
            undo()


def test_undo_cleans_empty_dirs(tmp_path: Path) -> None:
    """Undo should clean up empty archive directories."""
    src = tmp_path / "Downloads" / "doc.pdf"
    archive_dir = tmp_path / "Archive" / "Documents" / "2026-01"
    dst = archive_dir / "doc.pdf"
    dst.parent.mkdir(parents=True)
    dst.write_text("content")

    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-01_090000", [
        {"source": str(src), "destination": str(dst), "size": 7, "is_dir": False, "status": "ok"},
    ])

    src.parent.mkdir(parents=True, exist_ok=True)

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        undo()

    # Empty archive dirs should be cleaned up
    assert not archive_dir.exists()


def test_list_runs(tmp_path: Path) -> None:
    """list_runs should return logs sorted newest first."""
    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-01_090000", [])
    _create_log(log_dir, "2026-01-08_090000", [])

    with patch("downloads_agent.undo.LOG_DIR", log_dir):
        runs = list_runs()

    assert len(runs) == 2
    assert runs[0].stem == "2026-01-08_090000"


def test_undo_invalid_run_id(tmp_path: Path) -> None:
    """Undo should reject run_id with path traversal."""
    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        with pytest.raises(DownloadsAgentError, match="Invalid run ID format"):
            undo("../../../etc/passwd")


def test_undo_invalid_run_id_special_chars(tmp_path: Path) -> None:
    """Undo should reject run_id with special characters."""
    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        with pytest.raises(DownloadsAgentError, match="Invalid run ID format"):
            undo("foo; rm -rf /")


def test_cleanup_empty_dirs_respects_stop_at(tmp_path: Path) -> None:
    """_cleanup_empty_dirs should not remove the stop_at directory."""
    archive = tmp_path / "Archive"
    deep_dir = archive / "Documents" / "2026-01"
    deep_dir.mkdir(parents=True)

    _cleanup_empty_dirs({deep_dir}, stop_at=archive)

    # Archive itself should still exist
    assert archive.exists()
    # But inner empty dirs should be removed
    assert not (archive / "Documents" / "2026-01").exists()
    assert not (archive / "Documents").exists()


def test_undo_with_lockfile(tmp_path: Path) -> None:
    """Undo should acquire and release lockfile properly."""
    src = tmp_path / "Downloads" / "doc.pdf"
    dst = tmp_path / "Archive" / "Documents" / "doc.pdf"
    dst.parent.mkdir(parents=True)
    dst.write_text("content")

    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-01_090000", [
        {"source": str(src), "destination": str(dst), "size": 7, "is_dir": False, "status": "ok"},
    ])

    src.parent.mkdir(parents=True, exist_ok=True)

    lock_dir = tmp_path / "lock_dir"
    lock_file = lock_dir / "lock"
    with patch("downloads_agent.undo.LOG_DIR", log_dir), \
         patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_file):
        result = undo()

    assert result.restored == 1
    # Lock should be released
    assert not lock_file.exists()


def test_undo_malformed_json_log(tmp_path: Path) -> None:
    """Malformed JSON log should raise DownloadsAgentError."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "2026-01-01_090000.json"
    log_path.write_text("{invalid json!!!")

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        with pytest.raises(DownloadsAgentError, match="corrupt"):
            undo("2026-01-01_090000")


def test_undo_missing_operations_key(tmp_path: Path) -> None:
    """Log without 'operations' key should raise DownloadsAgentError."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "2026-01-01_090000.json"
    log_path.write_text(json.dumps({"timestamp": "2026-01-01T00:00:00"}))

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        with pytest.raises(DownloadsAgentError, match="missing 'operations'"):
            undo("2026-01-01_090000")


def test_undo_destination_already_deleted(tmp_path: Path) -> None:
    """Undo when archived file no longer exists should skip correctly."""
    src = tmp_path / "Downloads" / "doc.pdf"
    # Destination does NOT exist — file was already deleted
    dst = tmp_path / "Archive" / "Documents" / "doc.pdf"

    log_dir = tmp_path / "logs"
    _create_log(log_dir, "2026-01-01_090000", [
        {"source": str(src), "destination": str(dst), "size": 7, "is_dir": False, "status": "ok"},
    ])

    src.parent.mkdir(parents=True, exist_ok=True)

    p1, p2, p3 = _patch_undo(tmp_path)
    with p1, p2, p3:
        result = undo()

    assert result.skipped == 1
    assert result.restored == 0
    assert result.failed == 0

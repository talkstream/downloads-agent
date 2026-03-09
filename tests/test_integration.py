"""Full-cycle integration test: scan → plan → execute → undo."""

from __future__ import annotations

from unittest.mock import patch

from downloads_agent.config import Config
from downloads_agent.executor import execute
from downloads_agent.planner import build_plan
from downloads_agent.scanner import scan
from downloads_agent.undo import undo


def test_full_cycle(populated_downloads: Config, tmp_path) -> None:
    """Populate Downloads → scan → plan → execute → verify → undo → verify restored."""
    config = populated_downloads
    downloads = config.downloads_dir

    # Collect original file names (excluding hidden and ignored)
    original_files = {
        f.name for f in downloads.iterdir()
        if not f.name.startswith(".") and f.name != "Archive"
    }

    lock_dir = tmp_path / "lock_dir"
    log_dir = tmp_path / "log_dir"

    with patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None):
        items = scan(config)

    assert len(items) > 0
    inactive_names = {item.name for item in items}

    plan = build_plan(items, config)
    assert plan.total_files + plan.total_dirs == len(items)

    with patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"), \
         patch("downloads_agent.executor.LOG_DIR", log_dir):
        result = execute(plan)

    assert result.moved == len(items)
    assert result.failed == 0
    assert result.log_path.exists()

    # Verify files are moved out of downloads
    remaining = {
        f.name for f in downloads.iterdir()
        if not f.name.startswith(".") and f.name != "Archive"
    }
    for name in inactive_names:
        assert name not in remaining, f"{name} should have been moved"

    # Verify archive directory exists and has content
    assert config.archive_dir.exists()

    # Undo
    with patch("downloads_agent.undo.LOG_DIR", log_dir), \
         patch("downloads_agent.executor.LOCK_DIR", lock_dir), \
         patch("downloads_agent.executor.LOCK_FILE", lock_dir / "lock"):
        undo_result = undo(archive_dir=config.archive_dir)

    assert undo_result.restored == len(items)
    assert undo_result.failed == 0

    # Verify files are restored
    restored = {
        f.name for f in downloads.iterdir()
        if not f.name.startswith(".") and f.name != "Archive"
    }
    assert restored == original_files

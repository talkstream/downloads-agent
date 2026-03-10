"""Tests for CLI module."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from downloads_agent.config import Config


def test_cli_no_command(capsys) -> None:
    """CLI with no command should print help and exit 0."""
    with patch("sys.argv", ["downloads-agent"]):
        with pytest.raises(SystemExit) as exc_info:
            from downloads_agent.cli import main
            main()
    assert exc_info.value.code == 0


def test_cli_version(capsys) -> None:
    """CLI --version should print version."""
    with patch("sys.argv", ["downloads-agent", "--version"]):
        with pytest.raises(SystemExit) as exc_info:
            from downloads_agent.cli import main
            main()
    assert exc_info.value.code == 0


def test_cli_scan_missing_dir(capsys, tmp_path: Path) -> None:
    """CLI scan should exit 1 for missing downloads dir."""
    from downloads_agent.cli import main

    config_file = tmp_path / "config.yaml"
    import yaml
    config_file.write_text(yaml.dump({
        "downloads_dir": str(tmp_path / "nonexistent"),
        "archive_dir": str(tmp_path / "archive"),
    }))

    with patch("sys.argv", ["downloads-agent", "--config", str(config_file), "scan"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1


def test_cli_run_exit_code_on_failure(default_config: Config, tmp_path: Path) -> None:
    """CLI run --execute should exit 1 when there are failures."""
    from downloads_agent.cli import _cmd_run
    import argparse

    # Create a file that will fail to move (destination parent is a file, not dir)
    downloads = default_config.downloads_dir
    f = downloads / "doc.pdf"
    f.write_text("test")

    old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).timestamp()
    os.utime(f, (old_ts, old_ts))

    args = argparse.Namespace(
        config=None,
        execute=True,
        quiet=True,
        no_notify=True,
        json=False,
    )

    # Mock scan to return a file, and execute to return a result with failures
    from downloads_agent.executor import ExecutionResult

    mock_result = ExecutionResult(moved=0, failed=1, skipped=0, total_size=0, log_path=tmp_path / "log.json")

    with patch("downloads_agent.cli.load_config", return_value=default_config), \
         patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None), \
         patch("downloads_agent.executor.execute", return_value=mock_result), \
         patch("downloads_agent.executor.acquire_lock"), \
         patch("downloads_agent.executor.release_lock"):
        with pytest.raises(SystemExit) as exc_info:
            _cmd_run(args)
    assert exc_info.value.code == 1


def test_cli_undo_invalid_run_id() -> None:
    """CLI undo with path traversal should exit 1."""
    from downloads_agent.cli import main

    with patch("sys.argv", ["downloads-agent", "undo", "../../../etc/passwd"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1


def test_cli_no_verbose_flag() -> None:
    """CLI should not have --verbose flag (dead flag removed)."""
    from downloads_agent.cli import main

    with patch("sys.argv", ["downloads-agent", "--verbose", "scan"]):
        with pytest.raises(SystemExit):
            # --verbose is no longer recognized
            main()

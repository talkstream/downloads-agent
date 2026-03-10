"""Tests for scheduler module."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from downloads_agent.errors import DownloadsAgentError
from downloads_agent.scheduler import install, uninstall, is_installed, CRON_MARKER, _get_current_crontab


def test_install_adds_cron_entry() -> None:
    """install() should add a cron line with the marker."""
    installed_content = None

    def capture_crontab(content: str) -> None:
        nonlocal installed_content
        installed_content = content

    with patch("downloads_agent.scheduler._get_current_crontab", return_value=""), \
         patch("downloads_agent.scheduler._set_crontab", side_effect=capture_crontab), \
         patch("downloads_agent.scheduler._get_agent_path", return_value="/usr/local/bin/downloads-agent"):
        result = install()

    assert CRON_MARKER in result
    assert "0 9 * * 0" in result
    assert CRON_MARKER in installed_content


def test_install_replaces_existing_entry() -> None:
    """install() should replace an existing cron entry."""
    existing = f"old line {CRON_MARKER}\nother job\n"
    installed_content = None

    def capture_crontab(content: str) -> None:
        nonlocal installed_content
        installed_content = content

    with patch("downloads_agent.scheduler._get_current_crontab", return_value=existing), \
         patch("downloads_agent.scheduler._set_crontab", side_effect=capture_crontab), \
         patch("downloads_agent.scheduler._get_agent_path", return_value="/usr/local/bin/downloads-agent"):
        install()

    # Should have exactly one marker line
    marker_count = installed_content.count(CRON_MARKER)
    assert marker_count == 1
    assert "other job" in installed_content


def test_uninstall_removes_entry() -> None:
    """uninstall() should remove the cron entry."""
    existing = f"0 9 * * 0 /usr/local/bin/downloads-agent run --execute {CRON_MARKER}\nother job\n"
    installed_content = None

    def capture_crontab(content: str) -> None:
        nonlocal installed_content
        installed_content = content

    with patch("downloads_agent.scheduler._get_current_crontab", return_value=existing), \
         patch("downloads_agent.scheduler._set_crontab", side_effect=capture_crontab):
        result = uninstall()

    assert result is True
    assert CRON_MARKER not in installed_content


def test_uninstall_no_entry() -> None:
    """uninstall() should return False if no entry exists."""
    with patch("downloads_agent.scheduler._get_current_crontab", return_value="other job\n"):
        result = uninstall()

    assert result is False


def test_is_installed() -> None:
    """is_installed() should detect the cron marker."""
    with patch("downloads_agent.scheduler._get_current_crontab", return_value=f"line {CRON_MARKER}"):
        assert is_installed() is True

    with patch("downloads_agent.scheduler._get_current_crontab", return_value="other"):
        assert is_installed() is False


def test_install_redirect_order() -> None:
    """Cron line should have correct redirect order: >> file 2>&1."""
    installed_content = None

    def capture_crontab(content: str) -> None:
        nonlocal installed_content
        installed_content = content

    with patch("downloads_agent.scheduler._get_current_crontab", return_value=""), \
         patch("downloads_agent.scheduler._set_crontab", side_effect=capture_crontab), \
         patch("downloads_agent.scheduler._get_agent_path", return_value="/usr/local/bin/downloads-agent"):
        result = install()

    # Correct order: >> "logfile" 2>&1
    assert ">> " in result
    assert "2>&1" in result
    # >> should come before 2>&1
    assert result.index(">>") < result.index("2>&1")


def test_get_current_crontab_failure_raises() -> None:
    """_get_current_crontab should raise on unexpected crontab failure."""
    mock_result = subprocess.CompletedProcess(
        args=["crontab", "-l"],
        returncode=1,
        stdout="",
        stderr="some unexpected error",
    )
    with patch("downloads_agent.scheduler.subprocess.run", return_value=mock_result):
        with pytest.raises(DownloadsAgentError, match="Failed to read crontab"):
            _get_current_crontab()


def test_get_current_crontab_no_crontab() -> None:
    """_get_current_crontab should return empty string for 'no crontab' message."""
    mock_result = subprocess.CompletedProcess(
        args=["crontab", "-l"],
        returncode=1,
        stdout="",
        stderr="no crontab for user",
    )
    with patch("downloads_agent.scheduler.subprocess.run", return_value=mock_result):
        assert _get_current_crontab() == ""


def test_get_current_crontab_oserror_raises() -> None:
    """_get_current_crontab should raise when crontab binary is missing."""
    with patch("downloads_agent.scheduler.subprocess.run", side_effect=OSError("not found")):
        with pytest.raises(DownloadsAgentError, match="crontab command not available"):
            _get_current_crontab()

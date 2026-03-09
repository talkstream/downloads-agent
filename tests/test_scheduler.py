"""Tests for scheduler module."""

from __future__ import annotations

from unittest.mock import patch

from downloads_agent.scheduler import install, uninstall, is_installed, CRON_MARKER


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

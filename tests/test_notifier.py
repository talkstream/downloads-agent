"""Tests for notifier module."""

from __future__ import annotations

from unittest.mock import patch

from downloads_agent.notifier import notify


def test_notify_calls_osascript() -> None:
    """notify() should call osascript with message and title as argv."""
    with patch("downloads_agent.notifier.subprocess.run") as mock_run:
        notify("Test message", "Test Title")

    mock_run.assert_called_once()
    args = mock_run.call_args
    cmd = args[0][0]  # First positional arg (the command list)

    assert cmd[0] == "osascript"
    assert cmd[1] == "-e"
    # Message and title should be passed as separate argv items (injection-proof)
    assert cmd[3] == "Test message"
    assert cmd[4] == "Test Title"


def test_notify_default_title() -> None:
    """notify() should use default title when not specified."""
    with patch("downloads_agent.notifier.subprocess.run") as mock_run:
        notify("Hello")

    cmd = mock_run.call_args[0][0]
    assert cmd[4] == "downloads-agent"


def test_notify_handles_timeout() -> None:
    """notify() should not raise on timeout."""
    import subprocess
    with patch("downloads_agent.notifier.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
        # Should not raise
        notify("Test")


def test_notify_handles_os_error() -> None:
    """notify() should not raise on OSError."""
    with patch("downloads_agent.notifier.subprocess.run", side_effect=OSError("no osascript")):
        # Should not raise
        notify("Test")


def test_notify_injection_proof() -> None:
    """Malicious message should not be interpolated into osascript command."""
    with patch("downloads_agent.notifier.subprocess.run") as mock_run:
        # This would cause injection if using string interpolation
        notify('"; do shell script "rm -rf /"', "title")

    cmd = mock_run.call_args[0][0]
    # The malicious string should be passed as a separate argv item, not in the -e script
    script = cmd[2]
    assert "rm -rf" not in script
    assert cmd[3] == '"; do shell script "rm -rf /"'

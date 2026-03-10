"""macOS native notifications via osascript (injection-proof).

Sends user-facing notifications using AppleScript's ``display notification``
command. Message and title are passed as ``argv`` to the ``on run`` handler
rather than interpolated into the script string — this prevents shell/script
injection regardless of the message content.
"""

from __future__ import annotations

import subprocess


def notify(message: str, title: str = "downloads-agent") -> None:
    """Send a macOS notification via osascript.

    The AppleScript ``on run argv`` handler receives *message* and *title*
    as positional arguments, avoiding string interpolation that could allow
    injection. Failures (timeout, missing osascript) are silently swallowed
    because notifications are non-critical — a failure here should never
    prevent the main pipeline from completing.

    Args:
        message: Notification body text.
        title: Notification title (shown in bold).
    """
    try:
        subprocess.run(
            [
                "osascript", "-e",
                "on run argv\n"
                "display notification (item 1 of argv) "
                'with title (item 2 of argv) sound name "Glass"\n'
                "end run",
                message, title,
            ],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

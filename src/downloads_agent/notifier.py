"""macOS native notifications via osascript."""

from __future__ import annotations

import subprocess


def notify(message: str, title: str = "downloads-agent") -> None:
    """Send a macOS notification (injection-proof via argv passing)."""
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

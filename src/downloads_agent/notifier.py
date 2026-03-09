"""macOS native notifications via osascript."""

from __future__ import annotations

import subprocess


def notify(message: str, title: str = "downloads-agent") -> None:
    """Send a macOS notification."""
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{message}" with title "{title}" sound name "Glass"',
            ],
            capture_output=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

"""Cron job installation and management."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

CRON_MARKER = "# downloads-agent"
LOG_PATH = Path.home() / ".downloads-agent" / "logs" / "cron.log"


def _get_agent_path() -> str:
    """Find the downloads-agent executable."""
    path = shutil.which("downloads-agent")
    if path:
        return path
    # Fallback: run as module
    return "python3 -m downloads_agent"


def _get_current_crontab() -> str:
    """Get current crontab content."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
    except OSError:
        pass
    return ""


def _set_crontab(content: str) -> None:
    """Set crontab content."""
    subprocess.run(
        ["crontab", "-"],
        input=content,
        text=True,
        check=True,
    )


def install() -> str:
    """Install weekly cron job (Sunday 09:00)."""
    current = _get_current_crontab()

    # Remove existing entry if present
    lines = [line for line in current.splitlines() if CRON_MARKER not in line]

    agent_cmd = _get_agent_path()
    cron_line = f"0 9 * * 0 {agent_cmd} run --execute --quiet 2>&1 >> {LOG_PATH} {CRON_MARKER}"
    lines.append(cron_line)

    # Ensure trailing newline
    new_content = "\n".join(lines).strip() + "\n"
    _set_crontab(new_content)
    return cron_line


def uninstall() -> bool:
    """Remove cron job. Returns True if entry was found and removed."""
    current = _get_current_crontab()
    lines = current.splitlines()
    new_lines = [line for line in lines if CRON_MARKER not in line]

    if len(new_lines) == len(lines):
        return False

    new_content = "\n".join(new_lines).strip()
    if new_content:
        new_content += "\n"
    _set_crontab(new_content)
    return True


def is_installed() -> bool:
    """Check if cron job is installed."""
    current = _get_current_crontab()
    return CRON_MARKER in current


def get_status() -> dict:
    """Get scheduler status."""
    from downloads_agent.undo import list_runs

    installed = is_installed()
    runs = list_runs()
    last_run = runs[0].stem if runs else None

    return {
        "installed": installed,
        "last_run": last_run,
        "schedule": "Every Sunday at 09:00" if installed else "Not scheduled",
    }

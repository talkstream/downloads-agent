"""Scan Downloads directory and collect file metadata."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from downloads_agent.config import Config


@dataclass
class FileInfo:
    path: Path
    name: str
    extension: str  # lowercase, without dot; empty for dirs
    size: int  # bytes
    is_dir: bool
    last_used: datetime
    modification_date: datetime


def _get_spotlight_last_used(path: Path) -> datetime | None:
    """Get kMDItemLastUsedDate from Spotlight metadata."""
    try:
        result = subprocess.run(
            ["mdls", "-name", "kMDItemLastUsedDate", "-raw", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = result.stdout.strip()
        if raw and raw != "(null)":
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S %z")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _get_dir_size(path: Path) -> int:
    """Get total directory size recursively."""
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def should_ignore(name: str, is_dir: bool, config: Config) -> bool:
    """Check if a file/dir should be ignored."""
    if name.startswith("."):
        return True
    if name in config.ignore_names:
        return True
    if is_dir and name in config.ignore_dirs:
        return True
    return False


def scan(config: Config) -> list[FileInfo]:
    """Scan downloads_dir (depth 1) and return inactive items."""
    downloads = config.downloads_dir
    if not downloads.exists():
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - (config.inactive_days * 86400)
    results: list[FileInfo] = []

    for entry in sorted(downloads.iterdir()):
        name = entry.name
        is_dir = entry.is_dir()

        if should_ignore(name, is_dir, config):
            continue
        if entry.is_symlink():
            continue

        # Get stat once to avoid TOCTOU and double syscall
        stat_result = entry.stat()

        # Get last used date
        spotlight_date = _get_spotlight_last_used(entry)
        mtime = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)

        if spotlight_date is not None:
            last_used = spotlight_date
        else:
            last_used = mtime

        # Skip active items
        if last_used.timestamp() > cutoff:
            continue

        # Collect metadata
        if is_dir:
            size = _get_dir_size(entry)
            ext = ""
        else:
            size = stat_result.st_size
            ext = entry.suffix.lstrip(".").lower()

        results.append(FileInfo(
            path=entry,
            name=name,
            extension=ext,
            size=size,
            is_dir=is_dir,
            last_used=last_used,
            modification_date=mtime,
        ))

    return results

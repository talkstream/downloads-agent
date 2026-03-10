"""Scan the Downloads directory and collect metadata for inactive files.

First stage of the pipeline. Iterates ``~/Downloads`` at depth 1 (no
recursive descent into subdirectories) and queries macOS Spotlight
(``mdls kMDItemLastUsedDate``) for each item's last-used timestamp,
falling back to ``mtime`` when Spotlight is unavailable. Items inactive
longer than ``inactive_days`` are returned as ``FileInfo`` dataclasses
for downstream classification and planning.

Key design choices:
- Depth-1 scanning keeps the tool predictable and fast.
- Spotlight fallback ensures correct behavior on non-macOS or when
  ``mdls`` is unavailable (e.g. inside CI containers).
- ``stat()`` is called once per entry to avoid TOCTOU races and
  redundant syscalls.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from downloads_agent.config import Config

# Track whether Spotlight unavailability warning was shown
_spotlight_warned = False


@dataclass
class FileInfo:
    """Metadata for a single file or directory in ~/Downloads.

    Produced by ``scan()`` and consumed by the classifier and planner.

    Attributes:
        path: Absolute path to the item.
        name: Filename (basename) without leading directory.
        extension: Lowercase extension without the leading dot; empty for
            directories and extensionless files.
        size: Size in bytes (recursive total for directories).
        is_dir: Whether this item is a directory.
        last_used: Best-known last-use timestamp (Spotlight or mtime).
        modification_date: Filesystem modification time (always from stat).
    """

    path: Path
    name: str
    extension: str
    size: int
    is_dir: bool
    last_used: datetime
    modification_date: datetime


def _get_spotlight_last_used(path: Path) -> datetime | None:
    """Query macOS Spotlight for the item's last-used date.

    Calls ``mdls -name kMDItemLastUsedDate -raw`` and parses the result.
    Returns ``None`` (triggering an mtime fallback in the caller) when:
    - Spotlight has no data for this item (returns ``"(null)"``).
    - The ``mdls`` command times out (>5 s) or is absent.
    - The date string cannot be parsed.

    A module-level ``_spotlight_warned`` flag ensures the "mdls unavailable"
    warning is printed at most once per process, avoiding log spam when
    Spotlight is entirely missing (e.g. in CI).
    """
    global _spotlight_warned
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
    except (subprocess.TimeoutExpired, ValueError):
        pass
    except OSError:
        if not _spotlight_warned:
            _spotlight_warned = True
            print(
                "warning: mdls (Spotlight) is unavailable, "
                "falling back to mtime for all files",
                file=sys.stderr,
            )
    return None


def _get_dir_size(path: Path) -> int:
    """Sum the sizes of all regular files under *path*, recursively.

    Silently skips individual files or subtrees that raise ``OSError``
    (permissions, broken symlinks) to avoid aborting the entire scan
    because of one inaccessible item.
    """
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
    """Determine whether an item should be excluded from scanning.

    Exclusion rules (checked in order):
    1. Hidden files/dirs (name starts with ``"."``)
    2. Names listed in ``config.ignore_names`` (e.g. ``.DS_Store``)
    3. Directories listed in ``config.ignore_dirs`` (e.g. ``Archive``)
    """
    if name.startswith("."):
        return True
    if name in config.ignore_names:
        return True
    if is_dir and name in config.ignore_dirs:
        return True
    return False


def scan(config: Config) -> list[FileInfo]:
    """Scan ``downloads_dir`` at depth 1 and return items inactive beyond the threshold.

    Pipeline stage 1. Iterates the top-level contents of the downloads
    directory, skipping symlinks, hidden files, and ignored names/dirs.
    Each surviving item is checked against the inactivity cutoff using
    Spotlight metadata (preferred) or mtime (fallback).

    Args:
        config: Validated application configuration.

    Returns:
        A list of ``FileInfo`` for items whose ``last_used`` date is older
        than ``config.inactive_days``, sorted alphabetically by name.
    """
    downloads = config.downloads_dir
    if not downloads.exists():
        return []

    # Epoch-seconds cutoff: items with last_used older than this are inactive
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
        try:
            stat_result = entry.stat()
        except OSError:
            continue  # file disappeared between iterdir and stat

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

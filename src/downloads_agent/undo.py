"""Reverse previous archive operations using transaction logs.

Pipeline stage 5 (rollback). Reads a JSON transaction log produced by
``executor.execute()``, reverses every successful move (destination → source),
and cleans up empty directories left behind. Operations are replayed in
reverse order to correctly handle nested directory structures.

Run IDs are validated via regex to prevent path traversal attacks
(e.g. ``../../../etc/passwd``).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from downloads_agent.errors import DownloadsAgentError


@dataclass
class UndoResult:
    """Summary of an undo operation.

    Attributes:
        log_file: Filename (not path) of the transaction log that was undone.
        restored: Number of items successfully moved back to their original location.
        failed: Number of items that could not be restored (``OSError``).
        skipped: Number of entries skipped (non-"ok" status, or source missing).
    """

    log_file: str
    restored: int
    failed: int
    skipped: int

LOG_DIR = Path.home() / ".downloads-agent" / "logs"


def list_runs() -> list[Path]:
    """List available transaction logs, most recent first.

    Returns paths sorted in reverse chronological order (newest first).
    Excludes non-transaction files like ``cron.log``.
    """
    if not LOG_DIR.exists():
        return []
    logs = sorted(LOG_DIR.glob("*.json"), reverse=True)
    # Exclude cron.log and other non-transaction files
    return [p for p in logs if p.stem not in ("cron",)]


def undo(run_id: str | None = None, archive_dir: Path | None = None) -> UndoResult:
    """Reverse a previous execution by replaying its transaction log backward.

    Locates the transaction log (by *run_id* or most recent), validates the
    run ID format via regex to prevent path traversal, then moves each
    successfully archived item back to its original location. Operations are
    replayed in reverse order so nested directory structures are restored
    correctly (children before parents). Empty archive directories left
    behind are cleaned up, stopping at *archive_dir*.

    Args:
        run_id: Transaction log stem in ``YYYY-MM-DD_HHMMSS`` format.
            Must match a strict regex to prevent path traversal attacks
            (e.g. ``../../etc/passwd``). Defaults to the most recent log.
        archive_dir: Root archive directory used as the ceiling for empty
            directory cleanup — this directory itself is never removed.

    Returns:
        An ``UndoResult`` with restored/failed/skipped counts.

    Raises:
        DownloadsAgentError: If *run_id* format is invalid, the log file
            does not exist, the log is corrupt JSON, or missing the
            ``operations`` key.
    """
    from downloads_agent.executor import acquire_lock, release_lock

    if run_id:
        # Strict format validation prevents path traversal via run_id
        # (e.g. "../../etc/passwd" would be rejected by the regex).
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{6}", run_id):
            raise DownloadsAgentError(f"Invalid run ID format: {run_id}")
        log_path = LOG_DIR / f"{run_id}.json"
        if not log_path.exists():
            raise DownloadsAgentError(f"Transaction log not found: {log_path}")
    else:
        runs = list_runs()
        if not runs:
            raise DownloadsAgentError("No transaction logs found.")
        log_path = runs[0]

    try:
        with open(log_path) as f:
            log_data = json.load(f)
    except json.JSONDecodeError as e:
        raise DownloadsAgentError(
            f"Transaction log is corrupt: {log_path}: {e}"
        ) from e

    if "operations" not in log_data:
        raise DownloadsAgentError(
            f"Transaction log missing 'operations' key: {log_path}"
        )

    acquire_lock()
    try:
        restored = 0
        failed = 0
        skipped = 0
        empty_dirs: set[Path] = set()

        # Reverse operations to undo in reverse order
        for entry in reversed(log_data["operations"]):
            if entry["status"] != "ok":
                skipped += 1
                continue

            src = Path(entry["destination"])
            dst = Path(entry["source"])

            try:
                if not src.exists():
                    skipped += 1
                    continue

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                restored += 1

                # Track parent directories for cleanup
                empty_dirs.add(src.parent)
            except OSError as e:
                print(
                    f"warning: failed to undo {src} → {dst}: {e}",
                    file=sys.stderr,
                )
                failed += 1

        # Clean up empty directories created by archiving
        _cleanup_empty_dirs(empty_dirs, stop_at=archive_dir)
    finally:
        release_lock()

    return UndoResult(
        log_file=log_path.name,
        restored=restored,
        failed=failed,
        skipped=skipped,
    )


def _cleanup_empty_dirs(dirs: set[Path], stop_at: Path | None = None) -> None:
    """Remove empty directories, walking up the tree.

    Args:
        dirs: Set of directories to consider for cleanup.
        stop_at: Do not remove this directory or any ancestor of it.
    """
    stop_resolved = stop_at.resolve() if stop_at else None

    # Sort deepest first
    sorted_dirs = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
    for d in sorted_dirs:
        try:
            while d.exists() and d.is_dir() and not any(d.iterdir()):
                if stop_resolved and d.resolve() == stop_resolved:
                    break
                d.rmdir()
                d = d.parent
        except OSError:
            pass

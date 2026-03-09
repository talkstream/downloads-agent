"""Rollback operations from transaction logs."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

LOG_DIR = Path.home() / ".downloads-agent" / "logs"


def list_runs() -> list[Path]:
    """List available transaction logs, most recent first."""
    if not LOG_DIR.exists():
        return []
    logs = sorted(LOG_DIR.glob("*.json"), reverse=True)
    # Exclude cron.log and other non-transaction files
    return [p for p in logs if p.stem not in ("cron",)]


def undo(run_id: str | None = None, archive_dir: Path | None = None) -> dict:
    """Undo a specific run or the latest one.

    Args:
        run_id: Transaction log ID (YYYY-MM-DD_HHMMSS format).
        archive_dir: Root archive directory (used as ceiling for empty dir cleanup).

    Returns a summary dict with restored/failed/skipped counts.
    """
    from downloads_agent.executor import acquire_lock, release_lock

    if run_id:
        # Sanitize: only allow YYYY-MM-DD_HHMMSS format
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{6}", run_id):
            raise ValueError(f"Invalid run ID format: {run_id}")
        log_path = LOG_DIR / f"{run_id}.json"
        if not log_path.exists():
            raise FileNotFoundError(f"Transaction log not found: {log_path}")
    else:
        runs = list_runs()
        if not runs:
            raise FileNotFoundError("No transaction logs found.")
        log_path = runs[0]

    with open(log_path) as f:
        log_data = json.load(f)

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
            except Exception:
                failed += 1

        # Clean up empty directories created by archiving
        _cleanup_empty_dirs(empty_dirs, stop_at=archive_dir)
    finally:
        release_lock()

    return {
        "log_file": log_path.name,
        "restored": restored,
        "failed": failed,
        "skipped": skipped,
    }


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

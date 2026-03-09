"""Rollback operations from transaction logs."""

from __future__ import annotations

import json
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


def undo(run_id: str | None = None) -> dict:
    """Undo a specific run or the latest one.

    Returns a summary dict with restored/failed/skipped counts.
    """
    if run_id:
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
    _cleanup_empty_dirs(empty_dirs)

    return {
        "log_file": log_path.name,
        "restored": restored,
        "failed": failed,
        "skipped": skipped,
    }


def _cleanup_empty_dirs(dirs: set[Path]) -> None:
    """Remove empty directories, walking up the tree."""
    # Sort deepest first
    sorted_dirs = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
    for d in sorted_dirs:
        try:
            while d.exists() and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
        except OSError:
            pass

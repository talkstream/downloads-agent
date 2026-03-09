"""Execute move operations with transaction logging and lockfile."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from downloads_agent import __version__
from downloads_agent.planner import MovePlan

LOCK_DIR = Path.home() / ".downloads-agent"
LOCK_FILE = LOCK_DIR / "lock"
LOG_DIR = LOCK_DIR / "logs"


@dataclass
class ExecutionResult:
    moved: int
    failed: int
    total_size: int
    log_path: Path


def _acquire_lock() -> None:
    """Create a lockfile to prevent parallel runs."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        # Check if the process is still running
        try:
            pid = int(LOCK_FILE.read_text().strip())
            os.kill(pid, 0)
            raise RuntimeError(
                f"Another downloads-agent is running (PID {pid}). "
                f"Remove {LOCK_FILE} if this is stale."
            )
        except (ValueError, ProcessLookupError, PermissionError):
            # Stale lockfile — remove it
            LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    """Remove the lockfile."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


def execute(plan: MovePlan) -> ExecutionResult:
    """Execute all move operations and write transaction log."""
    _acquire_lock()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc)
        log_entries: list[dict] = []
        moved = 0
        failed = 0
        total_size = 0

        for op in plan.operations:
            entry = {
                "source": str(op.source),
                "destination": str(op.destination),
                "size": op.size,
                "is_dir": op.is_dir,
                "status": "pending",
            }
            try:
                # Skip symlinks
                if op.source.is_symlink():
                    entry["status"] = "skipped"
                    log_entries.append(entry)
                    continue

                # Create target parent directory
                op.destination.parent.mkdir(parents=True, exist_ok=True)

                # Move
                shutil.move(str(op.source), str(op.destination))
                entry["status"] = "ok"
                moved += 1
                total_size += op.size
            except Exception as e:
                entry["status"] = "error"
                entry["error"] = str(e)
                failed += 1
            log_entries.append(entry)

        # Write transaction log
        log_name = timestamp.strftime("%Y-%m-%d_%H%M%S") + ".json"
        log_path = LOG_DIR / log_name
        log_data = {
            "timestamp": timestamp.isoformat(),
            "version": __version__,
            "operations": log_entries,
            "summary": {
                "files_moved": moved,
                "files_failed": failed,
                "total_size": total_size,
            },
        }
        log_path.write_text(json.dumps(log_data, indent=2, ensure_ascii=False))

        return ExecutionResult(
            moved=moved,
            failed=failed,
            total_size=total_size,
            log_path=log_path,
        )
    finally:
        _release_lock()

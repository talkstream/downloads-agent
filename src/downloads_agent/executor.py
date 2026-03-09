"""Execute move operations with transaction logging and lockfile."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from downloads_agent import __version__
from downloads_agent.errors import LockError
from downloads_agent.planner import MovePlan, resolve_collision

LOCK_DIR = Path.home() / ".downloads-agent"
LOCK_FILE = LOCK_DIR / "lock"
LOG_DIR = LOCK_DIR / "logs"


@dataclass
class ExecutionResult:
    moved: int
    failed: int
    total_size: int
    log_path: Path


def acquire_lock() -> None:
    """Create a lockfile atomically via O_CREAT | O_EXCL."""
    for _attempt in range(2):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                pid = int(LOCK_FILE.read_text().strip())
                os.kill(pid, 0)
            except ProcessLookupError:
                # Stale lockfile — remove and retry
                LOCK_FILE.unlink(missing_ok=True)
                continue
            except (ValueError, PermissionError):
                pass
            # Process alive or lockfile unreadable — fail immediately
            raise LockError(
                f"Another downloads-agent is running (lockfile {LOCK_FILE}). "
                f"Remove it manually if this is stale."
            )
    # Stale lock could not be cleared after retries
    raise LockError(
        f"Another downloads-agent is running (lockfile {LOCK_FILE}). "
        f"Remove it manually if this is stale."
    )


def release_lock() -> None:
    """Remove the lockfile."""
    LOCK_FILE.unlink(missing_ok=True)


def execute(plan: MovePlan) -> ExecutionResult:
    """Execute all move operations and write transaction log."""
    acquire_lock()
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

                # TOCTOU symlink hardening: verify resolved path is within source's parent
                resolved = op.source.resolve()
                source_parent = op.source.parent.resolve()
                if not str(resolved).startswith(str(source_parent) + "/") and resolved != source_parent:
                    entry["status"] = "skipped"
                    entry["error"] = "resolved path outside downloads directory"
                    log_entries.append(entry)
                    continue

                # Re-check collision at execution time
                dest = op.destination
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest = resolve_collision(dest)
                    entry["destination"] = str(dest)

                # Move
                shutil.move(str(op.source), str(dest))
                entry["status"] = "ok"
                moved += 1
                total_size += op.size
            except Exception as e:
                entry["status"] = "error"
                entry["error"] = str(e)
                failed += 1
            log_entries.append(entry)

        # Write transaction log atomically
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

        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(LOG_DIR), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(log_path))
        except BaseException:
            os.unlink(tmp_path)
            raise

        return ExecutionResult(
            moved=moved,
            failed=failed,
            total_size=total_size,
            log_path=log_path,
        )
    finally:
        release_lock()

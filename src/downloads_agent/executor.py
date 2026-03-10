"""Execute move operations with atomic lockfile and transaction logging.

Pipeline stage 4. Takes a ``MovePlan`` and performs the actual file moves
via ``shutil.move``, guarded by a mutual-exclusion lockfile and producing
a JSON transaction log that enables ``undo``.

Security & reliability measures:
- **Atomic lock**: ``O_CREAT | O_EXCL`` ensures only one instance runs
  at a time, with stale-lock detection via PID liveness check.
- **TOCTOU symlink hardening**: each source is verified to not be (or
  resolve through) a symlink pointing outside the downloads directory.
- **Runtime collision re-check**: destinations are re-checked at move time
  to handle files created between planning and execution.
- **Atomic log write**: transaction log is written to a temp file then
  renamed via ``os.replace`` so a crash never produces a partial log.
"""

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
    """Summary of a completed execution run.

    Attributes:
        moved: Number of items successfully moved.
        failed: Number of items that raised an ``OSError`` during move.
        skipped: Number of items skipped (symlinks, TOCTOU failures).
        total_size: Cumulative size in bytes of successfully moved items.
        log_path: Absolute path to the JSON transaction log for this run.
    """

    moved: int
    failed: int
    skipped: int
    total_size: int
    log_path: Path


def acquire_lock() -> None:
    """Create a lockfile atomically via ``O_CREAT | O_EXCL``.

    The lock file contains the owning process's PID. If the file already
    exists, the PID is read and checked for liveness via ``os.kill(pid, 0)``.
    A stale lock (dead PID) is removed and retried once. This two-attempt
    loop handles the common case of a previous crash leaving a stale lock.

    Raises:
        LockError: If another live process holds the lock, or the lockfile
            is unreadable (invalid PID, permission denied).
    """
    for _attempt in range(2):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        try:
            # O_CREAT | O_EXCL: atomically create-or-fail — the kernel
            # guarantees no race between existence check and creation.
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
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
            except ValueError:
                raise LockError(
                    f"Lockfile {LOCK_FILE} contains invalid PID. "
                    f"Remove it manually: rm {LOCK_FILE}"
                )
            except PermissionError:
                raise LockError(
                    f"Cannot read lockfile {LOCK_FILE} (permission denied). "
                    f"Check file permissions or remove it manually."
                )
            # Process alive — fail immediately
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
    """Execute all planned moves under a lockfile, producing a transaction log.

    For each operation: skips symlinks and items whose resolved path escapes
    the downloads directory (TOCTOU hardening), re-checks collisions at move
    time, then performs ``shutil.move``. Every outcome (ok/skipped/error) is
    recorded in the transaction log for later ``undo``.

    The transaction log is written atomically: data goes to a temp file first,
    then ``os.replace`` swaps it into place. A crash during write leaves no
    partial log — the temp file is cleaned up in the ``except`` handler.

    Args:
        plan: A ``MovePlan`` from ``build_plan()``.

    Returns:
        An ``ExecutionResult`` summarizing moved/failed/skipped counts.
    """
    acquire_lock()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc)
        log_entries: list[dict] = []
        moved = 0
        failed = 0
        skipped = 0
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
                    skipped += 1
                    log_entries.append(entry)
                    continue

                # TOCTOU symlink hardening: between scan and execute, a file could
                # be replaced by a symlink pointing outside ~/Downloads. Resolve
                # the real path and verify it's still within the expected parent.
                resolved = op.source.resolve()
                source_parent = op.source.parent.resolve()
                if not str(resolved).startswith(str(source_parent) + "/") and resolved != source_parent:
                    entry["status"] = "skipped"
                    entry["error"] = "resolved path outside downloads directory"
                    skipped += 1
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
            except OSError as e:
                entry["status"] = "error"
                entry["error"] = f"{type(e).__name__}: {e}"
                failed += 1
            log_entries.append(entry)

        # Atomic log write: write to a temp file, then os.replace() into the
        # final path. This ensures a crash never produces a half-written log.
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
            try:
                os.unlink(tmp_path)
            except OSError:
                pass  # cleanup failure is secondary to the original error
            raise

        return ExecutionResult(
            moved=moved,
            failed=failed,
            skipped=skipped,
            total_size=total_size,
            log_path=log_path,
        )
    finally:
        release_lock()

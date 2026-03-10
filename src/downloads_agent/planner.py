"""Build a move plan with collision handling and human-readable summary.

Pipeline stage 3. Consumes ``FileInfo`` items from the scanner, classifies
each one, computes destination paths with date-based subdirectories, and
resolves filename collisions — all without touching the filesystem. The
resulting ``MovePlan`` can be displayed as a dry-run preview or passed to
the executor for actual file moves.

Separating planning from execution enables the "dry-run by default"
philosophy: users always see what *would* happen before committing.
The ``check_max`` guard is intentionally deferred to execution time so
dry-run output is never artificially truncated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from downloads_agent.classifier import classify
from downloads_agent.config import Config
from downloads_agent.errors import DownloadsAgentError
from downloads_agent.scanner import FileInfo


@dataclass
class MoveOperation:
    """A single planned file or directory move."""

    source: Path
    destination: Path
    size: int
    is_dir: bool


@dataclass
class CategorySummary:
    """Aggregated statistics for one file category (e.g. Documents, Images).

    Used by ``format_plan()`` to render the dry-run preview with per-category
    counts, sizes, and date-bucket breakdowns.
    """

    name: str
    count: int = 0
    total_size: int = 0
    date_buckets: dict[str, int] = field(default_factory=dict)  # YYYY-MM → count
    date_sizes: dict[str, int] = field(default_factory=dict)  # YYYY-MM → size
    items: list[tuple[str, int]] = field(default_factory=list)  # (name, size) for dirs


@dataclass
class MovePlan:
    """Complete move plan with operations and summary statistics.

    Produced by ``build_plan()``, consumed by ``executor.execute()``
    (for actual moves) or ``format_plan()`` (for dry-run display).
    """

    operations: list[MoveOperation]
    file_summaries: dict[str, CategorySummary]
    folder_summary: CategorySummary | None
    total_files: int
    total_dirs: int
    total_size: int


_MAX_COLLISION_ATTEMPTS = 10_000


def resolve_collision(target: Path) -> Path:
    """Return *target* if it doesn't exist, or append ``_1``, ``_2``, … suffix.

    The suffix is inserted before the file extension (``report_1.pdf``) and
    is bounded at 10,000 attempts to prevent infinite loops on pathological
    filesystems. Never overwrites an existing file.

    Raises:
        DownloadsAgentError: If all 10,000 candidate names are taken.
    """
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    for counter in range(1, _MAX_COLLISION_ATTEMPTS + 1):
        new_name = f"{stem}_{counter}{suffix}"
        candidate = parent / new_name
        if not candidate.exists():
            return candidate
    raise DownloadsAgentError(
        f"Cannot resolve collision for {target}: "
        f"exceeded {_MAX_COLLISION_ATTEMPTS} attempts"
    )


def format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def build_plan(items: list[FileInfo], config: Config, check_max: bool = False) -> MovePlan:
    """Build a move plan from scanned items.

    Classifies each item, computes its destination path (with optional
    YYYY-MM date subfolder), and resolves any filename collisions at
    plan time. Collisions are re-checked at execution time to handle
    files created between planning and execution.

    Args:
        items: ``FileInfo`` list from ``scan()``.
        config: Validated application configuration.
        check_max: If ``True``, raise ``DownloadsAgentError`` when the plan
            exceeds ``max_operations``. Intentionally ``False`` for dry-runs
            so users can see the full scope before deciding.

    Returns:
        A ``MovePlan`` with operations and per-category summaries.

    Raises:
        DownloadsAgentError: When *check_max* is ``True`` and the plan
            exceeds ``config.max_operations``.
    """
    operations: list[MoveOperation] = []
    file_summaries: dict[str, CategorySummary] = {}
    folder_summary: CategorySummary | None = None

    for item in items:
        category = classify(item.extension, item.is_dir, config)

        if item.is_dir:
            target = config.archive_dir / "Folders" / item.name
        else:
            if config.date_subfolder:
                date_folder = item.modification_date.strftime("%Y-%m")
                target = config.archive_dir / category / date_folder / item.name
            else:
                target = config.archive_dir / category / item.name

        target = resolve_collision(target)

        operations.append(MoveOperation(
            source=item.path,
            destination=target,
            size=item.size,
            is_dir=item.is_dir,
        ))

        # Update summaries
        if item.is_dir:
            if folder_summary is None:
                folder_summary = CategorySummary(name="Folders")
            folder_summary.count += 1
            folder_summary.total_size += item.size
            folder_summary.items.append((item.name, item.size))
        else:
            if category not in file_summaries:
                file_summaries[category] = CategorySummary(name=category)
            summary = file_summaries[category]
            summary.count += 1
            summary.total_size += item.size
            date_key = item.modification_date.strftime("%Y-%m")
            summary.date_buckets[date_key] = summary.date_buckets.get(date_key, 0) + 1
            summary.date_sizes[date_key] = summary.date_sizes.get(date_key, 0) + item.size

    # Safety cap checked only when executing (check_max=True) so dry-runs
    # always show the full plan regardless of max_operations.
    if check_max and len(operations) > config.max_operations:
        raise DownloadsAgentError(
            f"Plan has {len(operations)} operations, exceeding max_operations={config.max_operations}. "
            f"Increase max_operations in config or reduce inactive_days."
        )

    total_files = sum(s.count for s in file_summaries.values())
    total_dirs = folder_summary.count if folder_summary else 0
    total_size = sum(op.size for op in operations)

    return MovePlan(
        operations=operations,
        file_summaries=file_summaries,
        folder_summary=folder_summary,
        total_files=total_files,
        total_dirs=total_dirs,
        total_size=total_size,
    )


def format_plan(plan: MovePlan) -> str:
    """Format a move plan as a human-readable dry-run preview.

    Categories are sorted by total size (largest first), date buckets
    within each category are sorted chronologically, and directories
    are listed by size (top 10 shown). Ends with a total summary line.
    """
    from datetime import datetime  # noqa: F811 — scoped import for clarity

    lines: list[str] = []
    lines.append(f"downloads-agent dry run — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    # File categories
    if plan.file_summaries:
        lines.append("  Files:")
        # Sort categories by size descending
        for cat_name in sorted(plan.file_summaries, key=lambda c: plan.file_summaries[c].total_size, reverse=True):
            summary = plan.file_summaries[cat_name]
            lines.append(f"    {cat_name + '/':<20s} ← {summary.count} files (~{format_size(summary.total_size)})")
            # Date buckets sorted chronologically
            for date_key in sorted(summary.date_buckets):
                count = summary.date_buckets[date_key]
                size = summary.date_sizes[date_key]
                lines.append(f"      {date_key + '/':<18s} ← {count} files (~{format_size(size)})")
        lines.append("")

    # Folder summary
    if plan.folder_summary:
        lines.append("  Folders:")
        fs = plan.folder_summary
        lines.append(f"    {'Folders/':<20s} ← {fs.count} dirs (~{format_size(fs.total_size)})")
        # Show top dirs by size
        for name, size in sorted(fs.items, key=lambda x: x[1], reverse=True)[:10]:
            lines.append(f"      {name + '/':<28s} (~{format_size(size)})")
        if len(fs.items) > 10:
            lines.append(f"      ... and {len(fs.items) - 10} more")
        lines.append("")

    # Total
    parts = []
    if plan.total_files:
        parts.append(f"{plan.total_files} files")
    if plan.total_dirs:
        parts.append(f"{plan.total_dirs} dirs")
    lines.append(f"  Total: {' + '.join(parts)} (~{format_size(plan.total_size)}) → Archive/")
    lines.append("  Run with --execute to apply.")

    return "\n".join(lines)

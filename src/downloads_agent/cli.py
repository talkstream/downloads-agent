"""Command-line interface for downloads-agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from downloads_agent import __version__
from downloads_agent.config import load_config
from downloads_agent.planner import format_size


def _cmd_scan(args: argparse.Namespace) -> None:
    """Show current state of Downloads directory."""
    config = load_config(args.config)
    downloads = config.downloads_dir

    if not downloads.exists():
        print(f"Directory not found: {downloads}")
        sys.exit(1)

    from downloads_agent.scanner import scan, _get_dir_size
    from downloads_agent.classifier import classify

    # Count all items (including active)
    total_files = 0
    total_dirs = 0
    total_size = 0

    for entry in downloads.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.name in config.ignore_patterns:
            continue
        if entry.is_dir() and entry.name in config.ignore_dirs:
            continue
        if entry.is_symlink():
            continue

        if entry.is_dir():
            total_dirs += 1
            total_size += _get_dir_size(entry)
        else:
            total_files += 1
            total_size += entry.stat().st_size

    # Scan for inactive items
    inactive = scan(config)
    inactive_files = [f for f in inactive if not f.is_dir]
    inactive_dirs = [f for f in inactive if f.is_dir]
    inactive_size = sum(f.size for f in inactive)

    print(f"Downloads: {downloads}")
    print(f"  Total: {total_files} files, {total_dirs} dirs (~{format_size(total_size)})")
    print(f"  Inactive (>{config.inactive_days} days): "
          f"{len(inactive_files)} files, {len(inactive_dirs)} dirs "
          f"(~{format_size(inactive_size)})")
    print()

    if inactive:
        # Category breakdown
        cat_counts: dict[str, int] = {}
        cat_sizes: dict[str, int] = {}
        for item in inactive:
            cat = classify(item.extension, item.is_dir, config)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            cat_sizes[cat] = cat_sizes.get(cat, 0) + item.size

        print("  By category:")
        for cat in sorted(cat_counts, key=lambda c: cat_sizes[c], reverse=True):
            print(f"    {cat + ':':<16s} {cat_counts[cat]:>5d} items  (~{format_size(cat_sizes[cat])})")
    else:
        print("  All files are active — nothing to archive.")


def _cmd_run(args: argparse.Namespace) -> None:
    """Run organizer (dry-run by default, --execute for real)."""
    config = load_config(args.config)

    from downloads_agent.scanner import scan
    from downloads_agent.planner import build_plan, format_plan
    from downloads_agent.notifier import notify

    items = scan(config)
    if not items:
        msg = "Nothing to archive — all files are active."
        if not args.quiet:
            print(msg)
        if not args.no_notify:
            notify(msg)
        return

    plan = build_plan(items, config, check_max=args.execute)

    if not args.execute:
        # Dry-run
        if not args.quiet:
            print(format_plan(plan))
        if not args.no_notify:
            notify(
                f"Dry run: {plan.total_files} files + {plan.total_dirs} dirs "
                f"(~{format_size(plan.total_size)}) would be archived"
            )
        return

    # Execute
    from downloads_agent.executor import execute

    if not args.quiet:
        print(f"Archiving {plan.total_files} files + {plan.total_dirs} dirs "
              f"(~{format_size(plan.total_size)})...")

    result = execute(plan)

    if not args.quiet:
        print(f"Done: {result.moved} moved, {result.failed} failed")
        print(f"Transaction log: {result.log_path}")

    if not args.no_notify:
        notify(f"Moved {result.moved} items (~{format_size(result.total_size)}) to Archive/")


def _cmd_undo(args: argparse.Namespace) -> None:
    """Undo a previous run."""
    from downloads_agent.undo import undo, list_runs

    try:
        result = undo(args.run_id)
    except FileNotFoundError as e:
        print(str(e))
        sys.exit(1)

    print(f"Undo {result['log_file']}:")
    print(f"  Restored: {result['restored']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Skipped: {result['skipped']}")


def _cmd_install(args: argparse.Namespace) -> None:
    """Install cron job."""
    from downloads_agent.scheduler import install

    cron_line = install()
    print(f"Cron job installed: {cron_line}")


def _cmd_uninstall(args: argparse.Namespace) -> None:
    """Remove cron job."""
    from downloads_agent.scheduler import uninstall

    if uninstall():
        print("Cron job removed.")
    else:
        print("No cron job found.")


def _cmd_status(args: argparse.Namespace) -> None:
    """Show scheduler status."""
    from downloads_agent.scheduler import get_status

    status = get_status()
    print(f"Schedule: {status['schedule']}")
    print(f"Installed: {'yes' if status['installed'] else 'no'}")
    print(f"Last run: {status['last_run'] or 'never'}")


def _cmd_config(args: argparse.Namespace) -> None:
    """Show current configuration."""
    import yaml
    from dataclasses import asdict

    config = load_config(args.config)
    d = asdict(config)
    # Convert Path objects to strings
    d["downloads_dir"] = str(d["downloads_dir"])
    d["archive_dir"] = str(d["archive_dir"])
    print(yaml.dump(d, default_flow_style=False, allow_unicode=True))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="downloads-agent",
        description="Automated Downloads organizer for macOS",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=None, help="Path to config file")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", action="store_true", help="Errors only")
    parser.add_argument("--no-notify", action="store_true", help="Disable macOS notifications")

    subparsers = parser.add_subparsers(dest="command")

    # scan
    subparsers.add_parser("scan", help="Analyze current Downloads state")

    # run
    run_parser = subparsers.add_parser("run", help="Organize Downloads (dry-run by default)")
    run_parser.add_argument("--execute", action="store_true", help="Actually move files")

    # undo
    undo_parser = subparsers.add_parser("undo", help="Undo a previous run")
    undo_parser.add_argument("run_id", nargs="?", default=None, help="Run ID to undo (default: latest)")

    # install / uninstall / status / config
    subparsers.add_parser("install", help="Install weekly cron job")
    subparsers.add_parser("uninstall", help="Remove cron job")
    subparsers.add_parser("status", help="Show scheduler status")
    subparsers.add_parser("config", help="Show current config")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "scan": _cmd_scan,
        "run": _cmd_run,
        "undo": _cmd_undo,
        "install": _cmd_install,
        "uninstall": _cmd_uninstall,
        "status": _cmd_status,
        "config": _cmd_config,
    }
    commands[args.command](args)

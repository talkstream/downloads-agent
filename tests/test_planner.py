"""Tests for planner module."""

from __future__ import annotations

from pathlib import Path

import pytest

from downloads_agent.config import Config
from downloads_agent.errors import DownloadsAgentError
from downloads_agent.planner import build_plan, format_plan, format_size, resolve_collision

from conftest import make_file_info


def test_build_plan_categorizes_files(default_config: Config) -> None:
    """Files should be categorized correctly in the plan."""
    downloads = default_config.downloads_dir
    items = [
        make_file_info(downloads / "doc.pdf", "pdf"),
        make_file_info(downloads / "pic.jpg", "jpg"),
    ]

    plan = build_plan(items, default_config)
    assert plan.total_files == 2
    assert plan.total_dirs == 0
    assert "Documents" in plan.file_summaries
    assert "Images" in plan.file_summaries


def test_build_plan_directories_go_to_folders(default_config: Config) -> None:
    """Directories should be placed in Folders/ category."""
    downloads = default_config.downloads_dir
    items = [
        make_file_info(downloads / "my_project", is_dir=True, ext=""),
    ]

    plan = build_plan(items, default_config)
    assert plan.total_dirs == 1
    assert plan.folder_summary is not None
    assert plan.folder_summary.count == 1
    dest = plan.operations[0].destination
    assert "Folders" in str(dest)


def test_build_plan_date_subfolder(default_config: Config) -> None:
    """Files should have YYYY-MM date subfolder in destination."""
    downloads = default_config.downloads_dir
    items = [make_file_info(downloads / "doc.pdf", "pdf", days_old=60)]

    plan = build_plan(items, default_config)
    dest = plan.operations[0].destination
    # Should contain a date folder like 2026-01
    parts = dest.parts
    assert any(len(p) == 7 and p[4] == "-" for p in parts)


def test_build_plan_no_date_subfolder(default_config: Config) -> None:
    """Without date_subfolder, files go directly into category."""
    default_config.date_subfolder = False
    downloads = default_config.downloads_dir
    items = [make_file_info(downloads / "doc.pdf", "pdf")]

    plan = build_plan(items, default_config)
    dest = plan.operations[0].destination
    assert dest == default_config.archive_dir / "Documents" / "doc.pdf"


def test_resolve_collision(tmp_path: Path) -> None:
    """Collision resolution should add _1, _2 suffixes."""
    target = tmp_path / "file.pdf"
    assert resolve_collision(target) == target

    target.touch()
    assert resolve_collision(target) == tmp_path / "file_1.pdf"

    (tmp_path / "file_1.pdf").touch()
    assert resolve_collision(target) == tmp_path / "file_2.pdf"


def test_build_plan_max_operations(default_config: Config) -> None:
    """Exceeding max_operations should raise ValueError."""
    default_config.max_operations = 2
    downloads = default_config.downloads_dir
    items = [
        make_file_info(downloads / "a.pdf", "pdf"),
        make_file_info(downloads / "b.pdf", "pdf"),
        make_file_info(downloads / "c.pdf", "pdf"),
    ]

    with pytest.raises(DownloadsAgentError, match="max_operations"):
        build_plan(items, default_config, check_max=True)


def test_format_size() -> None:
    """Size formatting should produce human-readable strings."""
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1_048_576) == "1.0 MB"
    assert format_size(1_073_741_824) == "1.0 GB"
    assert format_size(2_500_000_000) == "2.3 GB"


def test_format_plan_output(default_config: Config) -> None:
    """format_plan should produce readable output."""
    downloads = default_config.downloads_dir
    items = [
        make_file_info(downloads / "doc.pdf", "pdf", size=1_048_576),
        make_file_info(downloads / "pic.jpg", "jpg", size=2_097_152),
        make_file_info(downloads / "old_dir", is_dir=True, ext="", size=5_000_000),
    ]

    plan = build_plan(items, default_config)
    output = format_plan(plan)

    assert "dry run" in output
    assert "Documents" in output
    assert "Images" in output
    assert "Folders" in output
    assert "--execute" in output

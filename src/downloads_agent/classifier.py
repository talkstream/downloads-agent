"""Extension-based file classification."""

from __future__ import annotations

from downloads_agent.config import Config


def _build_extension_map(categories: dict[str, list[str]]) -> dict[str, str]:
    """Build a reverse map: extension → category name."""
    ext_map: dict[str, str] = {}
    for category, extensions in categories.items():
        if category == "Other":
            continue
        for ext in extensions:
            ext_map[ext.lower()] = category
    return ext_map


def classify(extension: str, is_dir: bool, config: Config) -> str:
    """Classify a file by extension or a directory as 'Folders'."""
    if is_dir:
        return "Folders"
    if not extension:
        return "Other"
    ext_map = _build_extension_map(config.categories)
    return ext_map.get(extension.lower(), "Other")

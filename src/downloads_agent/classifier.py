"""Extension-based file classification."""

from __future__ import annotations

from functools import lru_cache

from downloads_agent.config import Config


def _build_extension_map(categories: tuple[tuple[str, tuple[str, ...]], ...]) -> dict[str, str]:
    """Build a reverse map: extension → category name (cached via hashable input)."""
    ext_map: dict[str, str] = {}
    for category, extensions in categories:
        if category == "Other":
            continue
        for ext in extensions:
            ext_map[ext.lower()] = category
    return ext_map


_build_extension_map_cached = lru_cache(maxsize=4)(_build_extension_map)


def classify(extension: str, is_dir: bool, config: Config) -> str:
    """Classify a file by extension or a directory as 'Folders'."""
    if is_dir:
        return "Folders"
    if not extension:
        return "Other"
    # Convert categories to hashable form for caching
    cat_key = tuple(
        (k, tuple(v)) for k, v in sorted(config.categories.items())
    )
    ext_map = _build_extension_map_cached(cat_key)
    return ext_map.get(extension.lower(), "Other")

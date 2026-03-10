"""Extension-based file classification with cached reverse lookup.

Pipeline stage 2. Maps a file's lowercase extension to a category name
(e.g. ``"pdf"`` → ``"Documents"``) using a reverse lookup table built
once from the config's ``categories`` dict and then LRU-cached.

The caching strategy converts the mutable ``dict[str, list[str]]`` into
a hashable ``tuple[tuple[str, tuple[str, ...]], ...]]`` so it can serve
as an ``lru_cache`` key. This avoids rebuilding the extension map on
every call while still invalidating automatically if the config changes.
"""

from __future__ import annotations

from functools import lru_cache

from downloads_agent.config import Config


def _build_extension_map(categories: tuple[tuple[str, tuple[str, ...]], ...]) -> dict[str, str]:
    """Build a reverse map from extension to category name.

    Accepts a hashable tuple representation of the categories dict so the
    result can be memoized by ``lru_cache``. The ``"Other"`` category is
    excluded because it serves as the default fallback for unrecognized
    extensions and should not appear in the lookup table.
    """
    ext_map: dict[str, str] = {}
    for category, extensions in categories:
        if category == "Other":
            continue
        for ext in extensions:
            ext_map[ext.lower()] = category
    return ext_map


_build_extension_map_cached = lru_cache(maxsize=4)(_build_extension_map)


def classify(extension: str, is_dir: bool, config: Config) -> str:
    """Classify a file by extension or a directory as ``"Folders"``.

    Lookup is O(1) via a cached reverse extension map. Directories always
    map to ``"Folders"`` regardless of extension. Files with no extension
    or an unrecognized extension map to ``"Other"``.

    Args:
        extension: Lowercase extension without the leading dot.
        is_dir: Whether the item is a directory.
        config: Configuration providing the categories mapping.

    Returns:
        Category name string (e.g. ``"Documents"``, ``"Images"``, ``"Other"``).
    """
    if is_dir:
        return "Folders"
    if not extension:
        return "Other"
    # Convert categories dict to a hashable tuple so lru_cache can use it
    # as a key. Sorted to ensure consistent ordering across dict iterations.
    cat_key = tuple(
        (k, tuple(v)) for k, v in sorted(config.categories.items())
    )
    ext_map = _build_extension_map_cached(cat_key)
    return ext_map.get(extension.lower(), "Other")

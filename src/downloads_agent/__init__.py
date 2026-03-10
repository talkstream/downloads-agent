"""downloads-agent — Automated Downloads Organizer for macOS.

A rule-based CLI tool that archives inactive files from ``~/Downloads``
into a structured ``Archive/Category/YYYY-MM/`` hierarchy. Designed around
a reversible five-stage pipeline::

    scan → classify → plan → execute → undo

Public API re-exports the core functions so library consumers can
orchestrate the pipeline programmatically without touching the CLI.
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "Config",       # Validated configuration dataclass
    "load_config",  # YAML config loader with defaults + user overrides
    "scan",         # Reads ~/Downloads, returns inactive FileInfo list
    "classify",     # Maps file extension → category name
    "build_plan",   # Builds MovePlan with collision handling
    "execute",      # Moves files, writes atomic transaction log
    "undo",         # Reverses a previous run from its transaction log
]

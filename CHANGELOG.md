# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed
- `RuntimeError` → `LockError` in `acquire_lock()` — CLI now shows clean error instead of traceback

### Changed
- Simplified `acquire_lock()` flow: removed `for/else/break` pattern, direct `raise LockError`
- Added `logger.warning()` in undo bare `except` for failure diagnostics
- Fixed stale docstring in `undo()`: "dict" → "UndoResult"
- Replaced `getattr(args, "json", False)` → `args.json` in CLI (global flag, always present)
- Extracted `_patch_executor()` test helper (DRY, mirrors `_patch_undo()`)
- Module-level `_DEFAULT_CONFIG` in test_classifier (avoids 97× YAML reload)

## [0.1.0] - 2026-03-10

### Added
- Initial release
- Rule-based file classification by extension (Documents, Images, Videos, Audio, Code, Archives)
- Spotlight `kMDItemLastUsedDate` integration with mtime fallback
- Dry-run mode (default) with detailed preview
- Transaction logging (JSON) for full undo support
- Collision-safe archiving with `_1`, `_2` suffixes
- Directory archiving to `Archive/Folders/`
- Weekly cron scheduling (Sunday 09:00)
- macOS native notifications
- Custom exception hierarchy (`DownloadsAgentError`, `ConfigError`, `LockError`)
- `UndoResult` dataclass for structured undo results
- Config validation (`__post_init__`) for invalid values
- Unknown config key warnings
- CLI epilog with typical workflow
- `--json` flag for machine-readable output (scan/run)
- TOCTOU symlink hardening in executor
- PEP 561 `py.typed` marker
- mypy type checking in CI
- pre-commit hooks (ruff, trailing whitespace, YAML check)
- 85%+ test coverage threshold
- Parameterized classifier tests for all 90+ extensions
- Full-cycle integration test (scan → plan → execute → undo)

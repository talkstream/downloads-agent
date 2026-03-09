# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

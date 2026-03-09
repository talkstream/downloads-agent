# downloads-agent

## Architecture

Pipeline: `scan → classify → plan → execute → undo`

## Module Responsibilities

- `scanner.py` — reads ~/Downloads (depth 1), queries Spotlight for last-used dates, returns `FileInfo` list
- `classifier.py` — maps file extension → category name via cached reverse lookup
- `planner.py` — builds `MovePlan` with collision handling and summary stats
- `executor.py` — moves files with lockfile, writes atomic JSON transaction logs
- `undo.py` — reverses operations from transaction logs, cleans empty dirs
- `config.py` — YAML config loading with defaults + user overrides + validation
- `cli.py` — argparse CLI with scan/run/undo/install/uninstall/status/config commands
- `notifier.py` — macOS native notifications via osascript (injection-proof)
- `scheduler.py` — cron job management for weekly auto-runs
- `errors.py` — exception hierarchy: `DownloadsAgentError`, `ConfigError`, `LockError`

## Testing Conventions

- All tests use `tmp_path` fixtures — never touch real filesystem
- Spotlight calls mocked: `patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None)`
- Lock/log dirs patched per test to avoid interference
- `conftest.py` provides `default_config`, `populated_downloads`, `make_file_info` helpers
- Run: `pytest tests/ -v`

## macOS-Only Constraints

- Spotlight metadata (`mdls`) for last-used detection
- `osascript` for native notifications
- `crontab` for scheduling
- BSD `sed -i ''` in shell scripts

## Key Design Decisions

- Dry-run by default (`run` without `--execute`)
- `check_max` only enforced on execute, not dry-run
- Collision resolution: `_1`, `_2` suffix — never overwrite
- Transaction logs enable full undo
- Single source of truth for version: `__init__.py.__version__`

## Commands

```bash
pytest tests/ -v                              # run tests
ruff check src/ tests/                        # lint
mypy src/                                     # type check
pre-commit run --all-files                    # all pre-commit hooks
```

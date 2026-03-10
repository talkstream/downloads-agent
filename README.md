# downloads-agent

> **macOS only** — requires Spotlight (`mdls`), `osascript`, and `crontab`.

Automated Downloads organizer for macOS. Moves inactive files from `~/Downloads` to a structured `Archive/` directory, categorized by file type and date.

## Features

- **Rule-based classification** — files sorted by extension into Documents, Images, Videos, Audio, Code, Archives
- **Smart inactivity detection** — uses macOS Spotlight `kMDItemLastUsedDate` with mtime fallback
- **Safe by default** — dry-run mode shows what would happen before moving anything
- **Transaction log** — every run is logged as JSON, enabling full undo
- **Collision-safe** — never overwrites; adds `_1`, `_2` suffixes
- **Directories** — moved whole into `Archive/Folders/` without touching contents
- **Weekly scheduling** — optional cron job (Sunday 09:00)
- **macOS notifications** — native alerts after each run

## Installation

```bash
pipx install .
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Analyze current Downloads state
downloads-agent scan

# Dry-run — show what would be moved (default)
downloads-agent run

# Actually move files
downloads-agent run --execute

# Undo the last run
downloads-agent undo

# Undo a specific run
downloads-agent undo 2026-03-09_090000

# Install weekly cron job (Sunday 09:00)
downloads-agent install

# Remove cron job
downloads-agent uninstall

# Show scheduler status
downloads-agent status

# Show current configuration
downloads-agent config
```

## Archive Structure

```
~/Downloads/Archive/
├── Documents/
│   ├── 2024-05/
│   │   ├── report.pdf
│   │   └── notes.txt
│   └── 2025-01/
│       └── thesis.docx
├── Images/
│   └── 2024-08/
│       ├── photo.jpg
│       └── screenshot.png
├── Videos/
│   └── 2025-02/
│       └── recording.mp4
├── Audio/
├── Code/
├── Archives/
├── Other/
└── Folders/
    ├── old_project/
    └── backup_files/
```

## Configuration

Default config is built-in. Override by creating `~/.downloads-agent/config.yaml`:

```yaml
downloads_dir: ~/Downloads
archive_dir: ~/Downloads/Archive
inactive_days: 30          # files unused for 30+ days → archive
max_operations: 500        # safety limit per run
date_subfolder: true       # Type/YYYY-MM/ structure

categories:
  Documents:
    - pdf
    - docx
    - txt
    # ... see src/downloads_agent/data/default.yaml for full list

ignore_names:
  - .DS_Store
  - .localized

ignore_dirs:
  - Archive
```

## Global Flags

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to config file |
| `--quiet` | Errors only |
| `--no-notify` | Disable macOS notifications |
| `--json` | Machine-readable JSON output (scan, run) |

## JSON Output

The `--json` flag produces machine-readable output for `scan` and `run` commands.

**`scan --json`** — Downloads directory summary:

```json
{
  "downloads_dir": "/Users/you/Downloads",
  "total_files": 120,
  "total_dirs": 5,
  "total_size": 5368709120,
  "inactive_files": 42,
  "inactive_dirs": 2,
  "inactive_size": 1073741824,
  "categories": {
    "Documents": {"count": 15, "size": 524288000},
    "Images": {"count": 10, "size": 104857600}
  }
}
```

**`run --json`** (dry-run) — planned operations:

```json
{
  "operations": [
    {"source": "/path/from", "destination": "/path/to", "size": 12345, "is_dir": false}
  ],
  "total_files": 42,
  "total_dirs": 2,
  "total_size": 1073741824
}
```

**`run --execute --json`** — execution result:

```json
{
  "moved": 40,
  "failed": 2,
  "skipped": 0,
  "total_size": 1073741824,
  "log_path": "/Users/you/.downloads-agent/logs/2026-03-09_090000.json"
}
```

## System Requirements

- **macOS** (tested on Ventura+)
- **Python 3.11+**
- **Spotlight** (`mdls`) — used for `kMDItemLastUsedDate` to detect when files were last opened
- **osascript** — used for native macOS notifications
- **crontab** — used for optional weekly scheduling

## How It Works

1. **Scan** — reads `~/Downloads` (top level only), queries Spotlight for last-used dates
2. **Classify** — maps file extensions to categories; directories → `Folders/`
3. **Plan** — builds move operations with collision detection
4. **Execute** — moves files via `shutil.move` (atomic rename on same volume), writes JSON transaction log
5. **Notify** — sends macOS notification with summary

## Architecture

```
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌─────────┐    ┌──────┐
│  scan   │───▶│ classify │───▶│  plan   │───▶│ execute │◀──▶│ undo │
│         │    │          │    │         │    │         │    │      │
│Spotlight│    │ext→cat   │    │collision│    │lockfile │    │reverse│
│+ mtime  │    │LRU cache │    │handling │    │TOCTOU   │    │moves  │
│fallback │    │          │    │dry-run  │    │atomic   │    │cleanup│
└─────────┘    └──────────┘    └─────────┘    │log write│    └──────┘
                                              └─────────┘
```

Each stage is a pure function of its inputs (config + data from the previous stage), making the pipeline easy to test in isolation.

**Module map** — each stage maps to a single module:

| Stage | Module | Responsibility |
|-------|--------|----------------|
| scan | `scanner.py` | Read ~/Downloads, query Spotlight, emit `FileInfo` |
| classify | `classifier.py` | Map extension → category via cached reverse lookup |
| plan | `planner.py` | Build `MovePlan` with collision resolution |
| execute | `executor.py` | Move files under lockfile, write transaction log |
| undo | `undo.py` | Reverse moves from transaction log |
| — | `config.py` | YAML loading, deep-merge, validation |
| — | `cli.py` | Argparse CLI, command dispatch |
| — | `scheduler.py` | Cron job management |
| — | `notifier.py` | macOS native notifications |
| — | `errors.py` | Exception hierarchy |

## Design Principles

- **Dry-run by default** — `run` shows a preview; `--execute` is required to actually move files. This prevents accidental data loss.
- **Transaction safety** — every execution writes an atomic JSON log. No partial logs exist even after a crash (tempfile + `os.replace`).
- **Collision-safe** — files are never overwritten. Collisions are resolved by appending `_1`, `_2`, … suffixes (bounded at 10,000).
- **Reversible** — `undo` reads a transaction log and reverses every move, then cleans up empty directories.
- **Fail-open for non-critical paths** — Spotlight unavailability, notification failures, and individual file errors never abort the entire run.

## Security Model

| Threat | Mitigation |
|--------|------------|
| **TOCTOU symlink attack** | Before each move, the source is resolved and verified to remain within ~/Downloads |
| **Script injection via notifications** | Message/title passed as `argv` to osascript, not interpolated into the script |
| **Path traversal via undo run ID** | Strict regex validation: only `YYYY-MM-DD_HHMMSS` format accepted |
| **Concurrent execution corruption** | Atomic lockfile via `O_CREAT \| O_EXCL` with PID-based stale detection |
| **Crontab data loss** | Unexpected `crontab -l` errors raise instead of silently overwriting |
| **Shell injection in cron command** | Agent path is `shlex.quote()`-d in the cron line |

## Testing

180 tests, 75%+ line coverage, three categories:

- **Unit tests** — each pipeline stage tested in isolation with `tmp_path` fixtures
- **Parameterized tests** — all 90+ extensions from `default.yaml` verified against their expected category
- **Integration tests** — CLI commands tested end-to-end with mocked Spotlight and filesystem

Key testing conventions:
- Real filesystem never touched — all tests use `tmp_path`
- Spotlight always mocked: `patch("downloads_agent.scanner._get_spotlight_last_used", return_value=None)`
- Lock/log directories patched per test to avoid cross-test interference

## Transaction Logs

Stored at `~/.downloads-agent/logs/YYYY-MM-DD_HHMMSS.json`:

```json
{
  "timestamp": "2026-03-09T09:00:00+00:00",
  "version": "0.1.0",
  "operations": [
    {"source": "/path/from", "destination": "/path/to", "size": 12345, "is_dir": false, "status": "ok"}
  ],
  "summary": {"files_moved": 42, "total_size": 1073741824}
}
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run a specific test
pytest tests/test_scanner.py -v
```

## License

MIT

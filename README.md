# downloads-agent

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

## How It Works

1. **Scan** — reads `~/Downloads` (top level only), queries Spotlight for last-used dates
2. **Classify** — maps file extensions to categories; directories → `Folders/`
3. **Plan** — builds move operations with collision detection
4. **Execute** — moves files via `shutil.move` (atomic rename on same volume), writes JSON transaction log
5. **Notify** — sends macOS notification with summary

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

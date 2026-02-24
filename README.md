# remarkable_watcher

Watches directories for reMarkable `.rm` notebook files and converts each page to PDF.

- **v6+ files** (reMarkable software 3+): converted via [`rmc`](https://github.com/chemag/rmc)
- **Pre-v6 files**: converted via [`rm2pdf`](https://github.com/rorycl/rm2pdf)
- PDF and ePub annotations are silently skipped — only notebook pages are converted.

## Requirements

- Python 3.10+
- [Inkscape](https://inkscape.org/) (required by `rmc` for SVG→PDF rendering)
- `rmc` and/or `rm2pdf` — see below

## Setup

### Option A — Nix + direnv (recommended)

Requires [Nix](https://nixos.org/download/) with flakes enabled and [direnv](https://direnv.net/).
Inkscape and Python are provided by the Nix dev shell.

```bash
direnv allow        # activates the Nix shell, creates .venv, installs Python deps
```

### Option B — plain virtualenv

Requires Python 3.10+ and Inkscape installed on your system (e.g. `brew install inkscape`).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

Both options make two commands available:

| Command      | Description                              |
|--------------|------------------------------------------|
| `rm-watch`   | Daemon — watches directories for changes |
| `rm-convert` | One-shot — converts files or directories |

### Install conversion tools

```bash
# rmc — for v6+ files (reMarkable software 3+)
pip install rmc

# rm2pdf — for pre-v6 files (optional)
nix profile install nixpkgs#rm2pdf
# or, via Go:
go install github.com/rorycl/rm2pdf@latest
```

## Usage

### Watcher daemon

```bash
rm-watch DIR [DIR…] --output OUTPUT_DIR [--delay SECS] [--no-recursive]
```

```
rm-watch ~/remarkable/sync --output ~/Documents/notes
rm-watch ~/remarkable/sync --output ~/Documents/notes --delay 2.0
```

### One-shot converter

```bash
rm-convert PATH [PATH…] --output OUTPUT_DIR [--no-recursive]
```

```
rm-convert page.rm --output ~/Documents/notes
rm-convert ~/remarkable/sync --output ~/Documents/notes
```

## Run at login (macOS)

Inkscape must be installed to your Nix profile so it is available outside the dev shell:

```bash
nix profile install nixpkgs#inkscape
```

Templates are in `support/`. Copy and personalise them:

```bash
# 1. Copy the wrapper script to the project root
cp support/run-watcher.sh .
chmod +x run-watcher.sh

# 2. Copy the plist template, filling in LABEL, PROJECT_DIR, WATCH_DIR, OUTPUT_DIR
cp support/com.example.remarkable-watcher.plist \
   ~/Library/LaunchAgents/com.YOURNAME.remarkable-watcher.plist
$EDITOR ~/Library/LaunchAgents/com.YOURNAME.remarkable-watcher.plist

# 3. Load it
launchctl load ~/Library/LaunchAgents/com.YOURNAME.remarkable-watcher.plist
```

Logs are written to `/tmp/remarkable-watcher.log` and `/tmp/remarkable-watcher.err`.

```bash
# Check it is running
launchctl list | grep remarkable

# Watch live output
tail -f /tmp/remarkable-watcher.log

# Stop / restart
launchctl unload ~/Library/LaunchAgents/com.YOURNAME.remarkable-watcher.plist
launchctl load   ~/Library/LaunchAgents/com.YOURNAME.remarkable-watcher.plist
```

## Development

```bash
pytest          # run tests
```

Tests in `tests/test_watcher.py` cover version detection, notebook filtering, conversion dispatch, debounce logic, and real fixture files under `tests/fixtures/v6_notebook/`.

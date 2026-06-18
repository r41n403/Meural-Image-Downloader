# meural-download

Download all of your personal uploads from [Meural](https://my.meural.netgear.com/uploads) to your local machine.

Uses a real browser session via [Playwright](https://playwright.dev/python/) so it works regardless of changes to Netgear's authentication system.

## Requirements

- Python 3.9+
- macOS, Linux, or Windows

## Setup

Install Playwright and its Chromium browser (one-time):

```bash
pip3 install playwright
python3 -m playwright install chromium
```

## Usage

```bash
python3 meural_download.py
```

**First run** opens a browser window. Log into Meural, navigate to your uploads page, then return to the terminal and press Enter. Your session is saved to `meural_session.json` so all future runs are fully headless — no login required.

Downloaded files are saved to `meural_downloads/` by default. A `meural_downloaded.txt` manifest tracks completed downloads, so re-running the script safely skips files you already have.

## Options

| Flag | Default | Description |
|---|---|---|
| `--output DIR` | `meural_downloads` | Directory to save images into |
| `--delay SECS` | `1.5` | Pause between each download |
| `--batch-size N` | `20` | Number of downloads before a longer pause |
| `--batch-pause SECS` | `30` | Length of the longer pause between batches |
| `--reset` | — | Delete saved session and force re-login |

### Examples

```bash
# Save to a custom folder
python3 meural_download.py --output ~/Pictures/Meural

# Re-login (e.g. session expired)
python3 meural_download.py --reset

# Slower rate limiting for large libraries
python3 meural_download.py --delay 2 --batch-size 10 --batch-pause 60
```

## Files

| File | Description |
|---|---|
| `meural_session.json` | Saved browser session (auto-created, gitignored) |
| `meural_downloaded.txt` | Manifest of downloaded URLs (auto-created, gitignored) |

> **Note:** `meural_session.json` contains authentication cookies. It is listed in `.gitignore` and should never be committed to version control.

## How it works

1. Opens a Chromium browser (headless on subsequent runs) and navigates to your uploads page
2. Scrolls to the bottom, collecting image URLs from all upload cards
3. Downloads each image with rate limiting and automatic retry on HTTP 403/429
4. Records each completed download in a manifest to enable safe re-runs

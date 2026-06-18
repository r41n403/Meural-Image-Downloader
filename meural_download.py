#!/usr/bin/env python3
"""
meural_download.py
Downloads all uploads from your Meural account (my.meural.netgear.com/uploads).

Setup (one-time):
    pip3 install playwright
    python3 -m playwright install chromium

Usage:
    python3 meural_download.py
    python3 meural_download.py --output ./my_meural_files

First run opens a browser window so you can log in manually.
Session is saved to meural_session.json — subsequent runs are fully headless.
"""

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

UPLOADS_URL   = "https://my.meural.netgear.com/uploads"
SESSION_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meural_session.json")
MANIFEST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meural_downloaded.txt")


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.strip().strip(".")
    return name or "untitled"


def guess_extension(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    _, ext = os.path.splitext(path)
    return ext.lower() if ext else ""


def load_manifest() -> set:
    if not os.path.exists(MANIFEST_FILE):
        return set()
    with open(MANIFEST_FILE) as f:
        return {line.strip() for line in f if line.strip()}


def record_manifest(url: str) -> None:
    with open(MANIFEST_FILE, "a") as f:
        f.write(url + "\n")


def download_file(url: str, dest: str, retries: int = 4) -> int:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            with open(dest, "wb") as f:
                f.write(data)
            return len(data)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                wait = 30 * (2 ** attempt)  # 30s, 60s, 120s
                print(f"    Rate limited (HTTP {e.code}) — waiting {wait}s before retry…")
                time.sleep(wait)
            else:
                raise


def collect_image_urls(page) -> list:
    """Scroll to the bottom of /uploads and collect all image URLs."""
    from playwright.sync_api import TimeoutError as PWTimeout

    seen_urls = set()
    items = []
    last_count = -1
    stall_rounds = 0

    print("Scrolling through uploads…")
    while stall_rounds < 4:
        imgs = page.query_selector_all("img")
        for img in imgs:
            # Prefer highest-res source: srcset > data-src > src
            srcset = img.get_attribute("srcset") or ""
            src = ""
            if srcset:
                # Pick the last (largest) srcset entry
                parts = [p.strip().split()[0] for p in srcset.split(",") if p.strip()]
                src = parts[-1] if parts else ""
            if not src:
                src = img.get_attribute("data-src") or img.get_attribute("src") or ""

            if not src or src in seen_urls:
                continue
            if "cloudfront.net" not in src and "meural" not in src:
                continue

            seen_urls.add(src)
            alt = img.get_attribute("alt") or ""
            items.append({"url": src, "name": alt or f"image_{len(items)+1}"})

        if len(items) == last_count:
            stall_rounds += 1
        else:
            stall_rounds = 0
            last_count = len(items)
            print(f"  {len(items)} images found so far…")

        page.evaluate("window.scrollBy(0, window.innerHeight * 3)")
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except PWTimeout:
            pass
        time.sleep(0.8)

    return items


def do_headed_login(pw):
    """Open a visible browser, let the user log in, save session, return context."""
    print("\nOpening browser for login…")
    print("Log into Meural in the browser window that opens.")
    print("Once you can see your uploads page, come back here and press Enter.\n")

    browser = pw.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://my.meural.netgear.com/login")

    input("Press Enter once you are logged in and can see the uploads page…")

    context.storage_state(path=SESSION_FILE)
    print(f"Session saved to {SESSION_FILE}")
    return browser, context


def do_headless_login(pw):
    """Restore saved session, return (browser, context). Returns None if session expired."""
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(storage_state=SESSION_FILE)
    page = context.new_page()
    page.goto(UPLOADS_URL, wait_until="networkidle", timeout=20000)

    if "/login" in page.url or "accounts" in page.url:
        browser.close()
        return None, None

    return browser, context


def main():
    parser = argparse.ArgumentParser(description="Download all Meural uploads.")
    parser.add_argument("--output",      default="meural_downloads", help="Output directory")
    parser.add_argument("--delay",       type=float, default=1.5,   help="Seconds between downloads (default 1.5)")
    parser.add_argument("--batch-size",  type=int,   default=20,    help="Pause after this many downloads (default 20)")
    parser.add_argument("--batch-pause", type=float, default=30.0,  help="Seconds to pause between batches (default 30)")
    parser.add_argument("--reset",       action="store_true",        help="Force re-login (delete saved session)")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run:")
        print("  pip3 install playwright")
        print("  python3 -m playwright install chromium")
        sys.exit(1)

    if args.reset and os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
        print("Saved session removed.")

    with sync_playwright() as pw:
        browser = context = None

        # Try restoring a saved session first
        if os.path.exists(SESSION_FILE):
            print("Restoring saved session…")
            browser, context = do_headless_login(pw)
            if context is None:
                print("Session expired — need to log in again.")

        # Fall back to headed login if needed
        if context is None:
            browser, context = do_headed_login(pw)
            # After manual login, navigate to uploads
            page = context.new_page()
            page.goto(UPLOADS_URL, wait_until="networkidle")
        else:
            page = context.pages[0] if context.pages else context.new_page()
            if UPLOADS_URL not in page.url:
                page.goto(UPLOADS_URL, wait_until="networkidle")

        print("On uploads page. Collecting images…\n")
        items = collect_image_urls(page)
        browser.close()

    if not items:
        print("No images found.")
        print("Try deleting meural_session.json and running again to re-login.")
        sys.exit(0)

    print(f"\nFound {len(items)} images total.")

    # ── Download ──────────────────────────────────────────────────────────────
    os.makedirs(args.output, exist_ok=True)
    downloaded = load_manifest()

    pending = [it for it in items if it["url"] not in downloaded]
    skipped = len(items) - len(pending)
    if skipped:
        print(f"Skipping {skipped} already-downloaded images.")
    print(f"Downloading {len(pending)} new images to: {os.path.abspath(args.output)}\n")

    if not pending:
        print("Nothing new to download.")
        sys.exit(0)

    ok = fail = batch_count = 0
    for i, item in enumerate(pending, 1):
        url  = item["url"]
        name = safe_filename(item["name"])
        ext  = guess_extension(url)
        filename = name + ext

        # Never overwrite an existing file — append a counter if needed
        dest = os.path.join(args.output, filename)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(args.output, f"{name}_{counter}{ext}")
            counter += 1

        try:
            size = download_file(url, dest)
            record_manifest(url)
            print(f"  [{i}/{len(pending)}] OK  {filename}  ({size/1024:.1f} KB)")
            ok += 1
            batch_count += 1
        except Exception as e:
            print(f"  [{i}/{len(pending)}] FAIL  {filename}: {e}")
            fail += 1

        if args.delay:
            time.sleep(args.delay)

        # Batch pause to avoid rate limiting
        if args.batch_size and batch_count > 0 and batch_count % args.batch_size == 0 and i < len(pending):
            print(f"\n  Pausing {args.batch_pause}s after {batch_count} downloads…\n")
            time.sleep(args.batch_pause)

    print(f"\nDone. {ok} downloaded, {fail} failed, {skipped} skipped.")
    print(f"Files saved to: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()

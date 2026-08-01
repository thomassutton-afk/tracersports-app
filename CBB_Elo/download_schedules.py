#!/usr/bin/env python3
"""
download_schedules.py

Automates the manual "click Share & Export -> Get table as Excel Workbook"
step across every D1 team's 1995-96 schedule page on sports-reference.com/cbb,
saving each download as <Team Name>.xls into an output folder ready for
build_cbb_db.py.

IMPORTANT
---------
- Run this from your own machine / home network, not a cloud box. Sports-
  Reference blocks datacenter IPs outright (confirmed while testing this).
- This uses a REAL, visible (non-headless) browser by default. That's
  intentional -- headless automation is far more likely to get flagged as a
  bot. Let it run in the foreground; don't use the machine's browser for
  anything else on the same profile while it runs.
- It's polite by default: a randomized multi-second delay between every
  team, and it's fully resumable -- rerun it anytime and it will skip teams
  it already has a file for.
- ~305 teams at the default delay takes roughly 30-50 minutes. If you get
  blocked partway through, stop, wait a while, and rerun -- it'll pick up
  where it left off.

SETUP
-----
    pip install playwright
    playwright install chromium

USAGE
-----
    python download_schedules.py schedules_1996/

    # slower/faster pacing:
    python download_schedules.py schedules_1996/ --min-delay 6 --max-delay 12

    # only redo teams that previously failed:
    python download_schedules.py schedules_1996/ --retry-failed
"""

import argparse
import csv
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

SEASON_STATS_URL = "https://www.sports-reference.com/cbb/seasons/men/1996-school-stats.html"
SCHEDULE_URL_TMPL = "https://www.sports-reference.com/cbb/schools/{slug}/men/1996-schedule.html"


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\- ]", "", name).strip()
    return re.sub(r"\s+", "_", name)


def get_team_list(page):
    """Scrape (slug, display_name) pairs from the season school-stats page."""
    page.goto(SEASON_STATS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    links = page.eval_on_selector_all(
        "table a[href*='/cbb/schools/']",
        "els => els.map(e => ({href: e.getAttribute('href'), text: e.textContent}))"
    )
    teams = {}
    for link in links:
        m = re.search(r"/cbb/schools/([^/]+)/men/", link["href"])
        if not m:
            continue
        slug = m.group(1)
        name = link["text"].strip()
        if slug and name:
            teams[slug] = name
    return sorted(teams.items(), key=lambda kv: kv[1])


def download_one_team(page, slug, display_name, out_dir, context):
    url = SCHEDULE_URL_TMPL.format(slug=slug)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)

    # Open the "Share & Export" panel above the schedule table
    share_button = page.get_by_text("Share & Export", exact=False).first
    share_button.click()
    page.wait_for_timeout(500)

    export_link = page.get_by_text("Get table as Excel Workbook", exact=False).first
    with page.expect_download(timeout=20000) as download_info:
        export_link.click()
    download = download_info.value

    dest = out_dir / f"{sanitize_filename(display_name)}.xls"
    download.save_as(dest)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--min-delay", type=float, default=4.0)
    ap.add_argument("--max-delay", type=float, default=9.0)
    ap.add_argument("--headless", action="store_true", help="not recommended -- more likely to be blocked")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                     help="stop after this many teams -- use for a quick test run")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / "_download_log.csv"

    already_ok = set()
    previously_failed = set()
    if log_path.exists():
        with open(log_path, newline="") as f:
            for row in csv.DictReader(f):
                if row["status"] == "ok":
                    already_ok.add(row["slug"])
                else:
                    previously_failed.add(row["slug"])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        print("Fetching D1 team list for 1995-96 season...")
        teams = get_team_list(page)
        print(f"Found {len(teams)} teams.\n")

        log_rows = []
        # keep prior log entries we're not redoing
        if log_path.exists():
            with open(log_path, newline="") as f:
                for row in csv.DictReader(f):
                    if row["slug"] in already_ok:
                        log_rows.append(row)
                    elif not args.retry_failed:
                        log_rows.append(row)

        attempted = 0
        for i, (slug, name) in enumerate(teams, 1):
            if slug in already_ok:
                continue
            if slug in previously_failed and not args.retry_failed:
                continue
            if args.limit is not None and attempted >= args.limit:
                print(f"\nReached --limit {args.limit}, stopping test run.")
                break
            attempted += 1

            print(f"[{i}/{len(teams)}] {name} ({slug}) ...", end=" ", flush=True)
            try:
                dest = download_one_team(page, slug, name, args.out_dir, context)
                print(f"OK -> {dest.name}")
                log_rows.append({"slug": slug, "team": name, "status": "ok", "note": ""})
            except (PWTimeout, Exception) as e:
                print(f"FAILED ({e})")
                log_rows.append({"slug": slug, "team": name, "status": "failed", "note": str(e)[:200]})

            # write log incrementally so a crash doesn't lose progress
            with open(log_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["slug", "team", "status", "note"])
                writer.writeheader()
                writer.writerows(log_rows)

            time.sleep(random.uniform(args.min_delay, args.max_delay))

        browser.close()

    n_ok = sum(1 for r in log_rows if r["status"] == "ok")
    n_fail = sum(1 for r in log_rows if r["status"] == "failed")
    print(f"\nDone. {n_ok} downloaded, {n_fail} failed.")
    if n_fail:
        print(f"Rerun with --retry-failed to retry the failures (see {log_path.name}).")


if __name__ == "__main__":
    main()

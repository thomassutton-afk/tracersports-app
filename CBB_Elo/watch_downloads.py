#!/usr/bin/env python3
"""
watch_downloads.py

A helper for the fully-manual workflow: YOU click "Share & Export" ->
"Get table as Excel Workbook" in your normal browser for each team's
1995-96 schedule page. This script just watches your Downloads folder,
and the moment a new sports-reference export lands, it:

  1. Waits for the download to finish writing
  2. Reads the title of your active browser window (which sports-reference
     puts the team name in) to guess the team name
  3. Shows you the guess and lets you confirm/edit it with one keystroke
  4. Moves + renames the file into your schedules_1996/ folder

This does NOT touch sports-reference.com or automate the browser in any
way -- it only watches your local Downloads folder and reads the window
title via Windows APIs. All the clicking is still you, in your regular
browser.

TIP: when you type the team name, use the SAME short form sports-reference
uses in its opponent columns (e.g. "Kentucky", not "Kentucky Wildcats" --
"North Carolina", not "North Carolina Tar Heels"). That's what
build_cbb_db.py matches on to merge each game across both teams' files, so
consistency here matters more than exact accuracy.

USAGE
-----
    python watch_downloads.py schedules_1996/

    # if your browser downloads somewhere other than the default:
    python watch_downloads.py schedules_1996/ --downloads "D:\\Downloads"

Then just leave this running in a terminal, alt-tab to your browser, and
click through Share & Export for each team. Ctrl+C to stop.
"""

import argparse
import csv
import ctypes
import re
import shutil
import time
from pathlib import Path


def get_active_window_title() -> str:
    """Windows-only: read the title of the currently focused window."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def guess_team_name(window_title: str) -> str:
    """Try to pull a team name out of a sports-reference tab title, e.g.
    '1995-96 Kentucky Wildcats Schedule and Results | Sports-Reference.com'
    -> 'Kentucky'
    Falls back to the raw title (minus site suffix) if the pattern doesn't match.
    """
    title = window_title.split(" | ")[0].strip()
    m = re.search(r"\d{4}-\d{2}\s+(.+?)\s+(Schedule|Roster|Stats|Men's)", title)
    if m:
        candidate = m.group(1)
        # drop a trailing mascot word if it looks like one (capitalized last word)
        words = candidate.split()
        if len(words) > 1:
            return " ".join(words[:-1])  # best-effort guess, user confirms anyway
        return candidate
    return title


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\- ]", "", name).strip()
    return re.sub(r"\s+", "_", name)


def wait_for_stable_file(path: Path, checks=3, interval=0.5) -> bool:
    """Wait until a file's size stops changing (download finished)."""
    last_size = -1
    stable_count = 0
    for _ in range(60):  # up to ~30s
        if not path.exists():
            time.sleep(interval)
            continue
        size = path.stat().st_size
        if size == last_size and size > 0:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            stable_count = 0
        last_size = size
        time.sleep(interval)
    return path.exists()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--downloads", type=Path,
                     default=Path.home() / "Downloads")
    ap.add_argument("--pattern", default="sportsref_download*")
    ap.add_argument("--auto", action="store_true",
                     help="don't prompt per file -- accept the guessed team name automatically")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.out_dir / "_watch_log.csv"

    # baseline: files already sitting in Downloads when we start are ignored
    # once, up front. After that we do NOT track "seen" filenames going
    # forward -- every processed file gets moved out of Downloads
    # immediately, so anything matching the pattern that we find on a later
    # poll is guaranteed to be a new download, even if it happens to reuse
    # the same default filename (sports-reference always calls the export
    # the same thing, and once the old one is moved away, the browser has
    # no reason to append "(1)" to the new one).
    baseline = set(args.downloads.glob(args.pattern))
    if baseline:
        print(f"Ignoring {len(baseline)} pre-existing file(s) already in Downloads.")
    log_rows = []
    if log_path.exists():
        with open(log_path, newline="") as f:
            log_rows = list(csv.DictReader(f))

    print(f"Watching {args.downloads} for '{args.pattern}' ...")
    print(f"New files will be moved into {args.out_dir}")
    print("Go click 'Share & Export' -> 'Get table as Excel Workbook' in your browser.")
    print("Ctrl+C to stop.\n")

    try:
        while True:
            current = set(args.downloads.glob(args.pattern)) - baseline
            new_files = sorted(current, key=lambda p: p.stat().st_mtime if p.exists() else 0)
            for f in new_files:
                if not wait_for_stable_file(f):
                    print(f"  ! {f.name} never stabilized, skipping")
                    continue

                title = get_active_window_title()
                guess = guess_team_name(title)
                print(f"\nNew file: {f.name}")
                print(f"  active window title: {title!r}")
                if args.auto:
                    team_name = guess
                    print(f"  Team name: {team_name} (auto)")
                else:
                    answer = input(f"  Team name [{guess}]: ").strip()
                    team_name = answer if answer else guess

                dest = args.out_dir / f"{sanitize_filename(team_name)}.xls"
                if dest.exists():
                    dest = args.out_dir / f"{sanitize_filename(team_name)}_dup{int(time.time())}.xls"
                    print(f"  (name collision -- saved as {dest.name}, check manually)")

                shutil.move(str(f), str(dest))
                print(f"  -> saved as {dest.name}")

                log_rows.append({"source_file": f.name, "window_title": title,
                                  "team_name": team_name, "dest": dest.name})
                with open(log_path, "w", newline="") as lf:
                    writer = csv.DictWriter(lf, fieldnames=["source_file", "window_title", "team_name", "dest"])
                    writer.writeheader()
                    writer.writerows(log_rows)

            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\nStopped. {len(log_rows)} files processed this session (see {log_path.name}).")


if __name__ == "__main__":
    main()

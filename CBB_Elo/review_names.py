#!/usr/bin/env python3
"""
review_names.py

Companion to watch_downloads.py --auto. Walks through _watch_log.csv,
shows you each guessed team name next to the file, and lets you fix any
that are wrong -- renaming the actual file to match. Only shows files
where you haven't already confirmed the name (so you can run this
multiple times as more downloads come in).

USAGE
-----
    python review_names.py schedules_1996/
"""

import argparse
import csv
from pathlib import Path
import re


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\- ]", "", name).strip()
    return re.sub(r"\s+", "_", name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", type=Path)
    args = ap.parse_args()

    log_path = args.out_dir / "_watch_log.csv"
    if not log_path.exists():
        print(f"No log found at {log_path}")
        return

    with open(log_path, newline="") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        if row.get("reviewed") == "yes":
            continue
        dest_path = args.out_dir / row["dest"]
        if not dest_path.exists():
            row["reviewed"] = "yes"  # file was moved/renamed elsewhere already
            continue

        print(f"\n{row['dest']}")
        print(f"  window title was: {row['window_title']!r}")
        answer = input(f"  Correct name is '{row['team_name']}'? [Enter=yes / type new name]: ").strip()
        if answer:
            new_path = args.out_dir / f"{sanitize_filename(answer)}.xls"
            dest_path.rename(new_path)
            row["team_name"] = answer
            row["dest"] = new_path.name
            print(f"  renamed -> {new_path.name}")
        row["reviewed"] = "yes"

        with open(log_path, "w", newline="") as lf:
            fieldnames = ["source_file", "window_title", "team_name", "dest", "reviewed"]
            writer = csv.DictWriter(lf, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                r.setdefault("reviewed", "")
            writer.writerows(rows)

    print("\nAll caught up.")


if __name__ == "__main__":
    main()

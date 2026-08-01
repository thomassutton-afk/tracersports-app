#!/usr/bin/env python3
"""
make_checklist.py

Builds a full-roster checklist of every D1 team for a season and cross-
checks it against the schedule files you've already downloaded, so you
know exactly which teams are done and which are still missing.

SETUP
-----
Export the season's "School Stats" table the same way you've been
exporting team schedules: go to

    https://www.sports-reference.com/cbb/seasons/men/1996-school-stats.html

click Share & Export -> Get table as Excel Workbook, and save it
somewhere (don't run it through watch_downloads.py -- save it manually
so it isn't mistaken for a team schedule file).

USAGE
-----
    python make_checklist.py 1996_School_Stats.xls schedules_1996/

Prints a checklist to the terminal and also writes checklist.md into the
schedules folder so you can reopen it anytime without rerunning.
"""

import argparse
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup


def normalize_name(name: str) -> str:
    name = name.replace("\u2013", "-").replace("\u2014", "-")  # en/em dash -> hyphen
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\(\d+\)", "", name)
    name = name.replace("'", "")  # e.g. "St. John's" -> "St. Johns" -- drop, don't split
    name = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return name.strip()


def clean_team_name(name: str) -> str:
    """Sports-Reference appends ' NCAA' to tournament teams on the School
    Stats page (e.g. 'Arizona NCAA') -- strip that so it matches the plain
    school name used everywhere else (schedule files, opponent columns)."""
    name = re.sub(r"\s+NCAA\s*$", "", name.strip())
    return name.strip()


def get_full_team_list(stats_export_path: Path):
    """Pull every D1 team name out of the School Stats export. Handles two
    formats sports-reference can produce for 'Get table as Excel Workbook':
      - a real binary/XML Excel workbook (opens directly in Excel)
      - an HTML table saved with an .xls extension (like the team schedule
        exports)
    """
    raw = stats_export_path.read_bytes()

    # genuine Excel file (xlsx/zip signature, or legacy OLE binary xls)
    is_zip = raw[:4] == b"PK\x03\x04"
    is_ole = raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    if is_zip or is_ole:
        import pandas as pd
        engine = "openpyxl" if is_zip else "xlrd"
        df = pd.read_excel(stats_export_path, header=None, engine=engine)

        # find the header row/column that says "School"
        school_col = None
        header_row = None
        for r in range(min(10, len(df))):
            for c in range(df.shape[1]):
                if str(df.iat[r, c]).strip().lower() == "school":
                    school_col, header_row = c, r
                    break
            if school_col is not None:
                break
        if school_col is None:
            print("Couldn't find a 'School' column in that workbook.")
            return []

        names = []
        for r in range(header_row + 1, len(df)):
            val = df.iat[r, school_col]
            if val is None or (isinstance(val, float) and str(val) == "nan"):
                continue
            name = clean_team_name(str(val))
            if name and name.lower() != "school":
                names.append(name)
        # de-dupe while preserving order, pair with a fake slug (unused downstream)
        seen = set()
        out = []
        for name in names:
            if name not in seen:
                seen.add(name)
                out.append((normalize_name(name), name))
        return out

    # otherwise assume it's the HTML-table-as-.xls format
    html = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    # attempt 1: linked school names (works on some exports)
    teams = {}
    for a in soup.select("a[href*='/cbb/schools/']"):
        href = a.get("href", "")
        m = re.search(r"/cbb/schools/([^/]+)/", href)
        name = clean_team_name(a.get_text(strip=True))
        if m and name:
            teams[m.group(1)] = name
    if teams:
        return sorted(teams.items(), key=lambda kv: kv[1])

    # attempt 2: sports-reference's usual data-stat attribute for this column
    cells = soup.select("[data-stat='school_name']")
    names = []
    for cell in cells:
        text = clean_team_name(cell.get_text(strip=True))
        if text and text.lower() != "school":
            names.append(text)
    if names:
        seen = set()
        out = []
        for name in names:
            key = normalize_name(name)
            if key not in seen:
                seen.add(key)
                out.append((key, name))
        return out

    # attempt 3: generic -- find whichever column's header cell says "School"
    table = soup.find("table")
    if table is None:
        return []
    header_cells = table.find("tr")
    school_idx = None
    if header_cells:
        for idx, cell in enumerate(header_cells.find_all(["th", "td"])):
            if cell.get_text(strip=True).lower() == "school":
                school_idx = idx
                break
    if school_idx is None:
        return []
    names = []
    for row in table.select("tbody tr") or table.find_all("tr")[1:]:
        cells = row.find_all(["th", "td"])
        if len(cells) > school_idx:
            text = clean_team_name(cells[school_idx].get_text(strip=True))
            if text and text.lower() != "school":
                names.append(text)
    seen = set()
    out = []
    for name in names:
        key = normalize_name(name)
        if key not in seen:
            seen.add(key)
            out.append((key, name))
    return out


def get_downloaded_teams(folder: Path):
    """Return {normalized_name: filename} for every schedule file in the folder."""
    downloaded = {}
    for f in list(folder.glob("*.xls")) + list(folder.glob("*.xlsx")):
        display_name = f.stem.replace("_", " ").strip()
        downloaded[normalize_name(display_name)] = f.name
    return downloaded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stats_export", type=Path)
    ap.add_argument("schedules_folder", type=Path)
    args = ap.parse_args()

    full_list = get_full_team_list(args.stats_export)
    if not full_list:
        print("Couldn't find any team links in that file -- make sure it's the "
              "School Stats table export, not a team schedule file.")
        return

    downloaded = get_downloaded_teams(args.schedules_folder)

    have, missing = [], []
    for slug, name in full_list:
        if normalize_name(name) in downloaded:
            have.append(name)
        else:
            missing.append(name)

    # files in the folder that didn't match any known D1 team -- likely typos
    # or misfires (e.g. a bad window-title guess)
    known_keys = {normalize_name(name) for _, name in full_list}
    unmatched_files = [fn for key, fn in downloaded.items() if key not in known_keys]

    print(f"D1 teams this season: {len(full_list)}")
    print(f"Downloaded:           {len(have)}")
    print(f"Missing:              {len(missing)}\n")

    if missing:
        print("Missing teams:")
        for name in missing:
            print(f"  [ ] {name}")

    if unmatched_files:
        print("\nFiles that don't match any D1 team (check these -- possible typos/misfires):")
        for fn in unmatched_files:
            print(f"  ? {fn}")

    # write a persistent markdown checklist too
    out_path = args.schedules_folder / "checklist.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# 1995-96 D1 checklist ({len(have)}/{len(full_list)} downloaded)\n\n")
        for name in have:
            f.write(f"- [x] {name}\n")
        for name in missing:
            f.write(f"- [ ] {name}\n")
        if unmatched_files:
            f.write("\n## Unmatched files (check these)\n")
            for fn in unmatched_files:
                f.write(f"- ? {fn}\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

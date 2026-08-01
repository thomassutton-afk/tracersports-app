#!/usr/bin/env python3
"""
make_launcher.py

Generates an HTML page of direct links to every D1 team's schedule page
for a given season, so you can click straight through them instead of
searching sports-reference for each team. Since school URL slugs are
stable across years, build/fix this ONE team_slugs.csv once and it works
for every future season -- just change --year.

FIRST TIME SETUP
----------------
Run once to generate a best-guess slug for every team:

    python make_launcher.py guess_slugs schedules_1996/teams.txt team_slugs.csv

(teams.txt = one team name per line -- you already have this list from
your build_cbb_db.py output, or just re-export it from the School Stats
file with make_checklist.py's roster.)

This produces team_slugs.csv with a guessed URL slug per team. Guesses
are NOT guaranteed correct -- sports-reference doesn't always use the
obvious hyphenated name (e.g. it might be "unlv" or it might be
"nevada-las-vegas" -- I can't verify without fetching the live site).
Open the launcher once, and for any link that 404s, fix that one row in
team_slugs.csv by hand (grab the real slug from the URL once you find the
team via sports-reference's own search). You'll only ever have to fix
each team once, total, ever -- not per season.

EVERY SEASON AFTER THAT
------------------------
    python make_launcher.py launcher team_slugs.csv launcher_1997.html --year 1997

Open launcher_1997.html in your browser -- every team name is a link
that opens that team's 1997 schedule page directly in a new tab.
"""

import argparse
import csv
import re
from pathlib import Path


def guess_slug(name: str) -> str:
    """Best-effort guess at a sports-reference URL slug. Not guaranteed
    correct -- verify once per team, then it's stable forever."""
    s = name.lower()
    s = s.replace("&", "")
    s = s.replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def cmd_guess_slugs(args):
    with open(args.teams_file, encoding="utf-8") as f:
        teams = [line.strip() for line in f if line.strip()]
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["team", "slug"])
        for t in teams:
            w.writerow([t, guess_slug(t)])
    print(f"Wrote {len(teams)} guessed slugs to {args.out_csv}")
    print("Open the launcher once and fix any team whose link 404s -- "
          "this only needs doing once, ever, per team.")


def cmd_make_launcher(args):
    with open(args.slugs_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    links = []
    for row in sorted(rows, key=lambda r: r["team"]):
        url = f"https://www.sports-reference.com/cbb/schools/{row['slug']}/men/{args.year}-schedule.html"
        links.append(f'<li><a href="{url}" target="_blank" rel="noopener">{row["team"]}</a></li>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{args.year} CBB Schedule Launcher</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 700px; margin: 2rem auto; }}
h1 {{ font-size: 1.2rem; }}
ul {{ list-style: none; padding: 0; column-count: 2; }}
li {{ margin-bottom: 0.3rem; }}
a {{ text-decoration: none; color: #1a5fb4; }}
a:visited {{ color: #888; }}
a:hover {{ text-decoration: underline; }}
</style></head>
<body>
<h1>{args.year} D1 schedule pages ({len(links)} teams)</h1>
<p>Click a team to open its {args.year} schedule page in a new tab, then use the
export bookmarklet (or Share &amp; Export manually). Visited links turn grey so
you can track progress at a glance.</p>
<ul>
{chr(10).join(links)}
</ul>
</body></html>
"""
    Path(args.out_html).write_text(html, encoding="utf-8")
    print(f"Wrote {args.out_html} with {len(links)} links.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("guess-slugs" if False else "guess_slugs")
    g.add_argument("teams_file")
    g.add_argument("out_csv")
    g.set_defaults(func=cmd_guess_slugs)

    m = sub.add_parser("launcher")
    m.add_argument("slugs_csv")
    m.add_argument("out_html")
    m.add_argument("--year", required=True)
    m.set_defaults(func=cmd_make_launcher)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

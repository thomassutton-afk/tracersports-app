#!/usr/bin/env python3
"""
investigate_d2_opponents.py

Lists every opponent name in the games table that didn't match the D1
roster, with how many games it appears in, and -- for each -- the closest
name(s) actually in the roster. A close fuzzy match with a non-trivial game
count is a strong candidate for a name-mismatch bug (the same class of
issue as the St. John's/en-dash cases fixed earlier) rather than a genuine
small-conference opponent.

USAGE
-----
    python investigate_d2_opponents.py cbb_1996.db
"""

import argparse
import difflib
import sqlite3
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", type=Path)
    ap.add_argument("--min-games", type=int, default=1,
                     help="only show opponent names appearing in at least this many games")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    cur = conn.cursor()

    roster = [r[0] for r in cur.execute("SELECT team_name FROM teams").fetchall()]
    roster_set = set(roster)

    rows = cur.execute("""
        SELECT opponent, COUNT(*) AS n FROM (
            SELECT home_team AS opponent FROM games WHERE away_team NOT IN (SELECT team_name FROM teams)
            UNION ALL
            SELECT away_team AS opponent FROM games WHERE home_team NOT IN (SELECT team_name FROM teams)
        )
        GROUP BY opponent
        ORDER BY n DESC
    """).fetchall()
    # the query above actually lists the D1 side of D1-vs-nonD1 games by mistake;
    # what we actually want is the non-D1 side itself:
    rows = cur.execute("""
        SELECT name, COUNT(*) AS n FROM (
            SELECT away_team AS name FROM games WHERE away_team NOT IN (SELECT team_name FROM teams)
            UNION ALL
            SELECT home_team AS name FROM games WHERE home_team NOT IN (SELECT team_name FROM teams)
        )
        GROUP BY name
        ORDER BY n DESC
    """).fetchall()

    conn.close()

    print(f"{len(rows)} distinct opponent names not matching the {len(roster)}-team D1 roster.\n")
    print(f"{'Name':<30} {'Games':>6}  Closest roster match(es)")
    print("-" * 80)
    likely_mismatches = []
    for name, n in rows:
        if n < args.min_games:
            continue
        close = difflib.get_close_matches(name, roster, n=2, cutoff=0.6)
        flag = ""
        if close:
            ratio = difflib.SequenceMatcher(None, name, close[0]).ratio()
            if ratio > 0.75:
                flag = "  <-- LIKELY MISMATCH"
                likely_mismatches.append((name, close[0], n))
        print(f"{name:<30} {n:>6}  {', '.join(close) if close else '(no close match)'}{flag}")

    if likely_mismatches:
        print(f"\n{len(likely_mismatches)} names look like likely mismatches, covering "
              f"{sum(n for _,_,n in likely_mismatches)} games total:")
        for name, match, n in likely_mismatches:
            print(f"  {name!r}  ->  probably  {match!r}   ({n} games)")


if __name__ == "__main__":
    main()

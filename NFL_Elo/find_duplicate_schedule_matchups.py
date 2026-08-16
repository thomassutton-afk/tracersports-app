"""
find_duplicate_schedule_matchups.py

READ-ONLY diagnostic. Finds any (season, type, round, home_team, away_team)
combination in `schedule` that has MORE THAN ONE distinct date -- this is
exactly the signature left behind when a source file's dates get corrected
and re-loaded: the corrected rows get added, but nothing removes the old
ones, since schedule's uniqueness check treats date as part of what makes
a row unique in the first place.

Deletes nothing. Just shows you what's duplicated so you (or I) can decide
which row is the stale one before touching anything.

Usage:
    python3 find_duplicate_schedule_matchups.py nfl_elo.db [--season 2026]
"""
import sys
import argparse
import db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", nargs="?", default="nfl_elo.db")
    ap.add_argument("--season", type=int, default=None)
    args = ap.parse_args()

    conn = db.connect(args.db_path)

    query = """
        SELECT season, type, round, home_team, away_team, home_code, away_code,
               GROUP_CONCAT(schedule_id) as ids, GROUP_CONCAT(date) as dates,
               COUNT(*) as n
        FROM schedule
    """
    params = []
    if args.season:
        query += " WHERE season = ?"
        params.append(args.season)
    query += """
        GROUP BY season, type, round, home_team, away_team
        HAVING COUNT(DISTINCT date) > 1
        ORDER BY season, home_code
    """
    rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No duplicate matchups found (same teams/type/round, different dates).")
        return

    print(f"Found {len(rows)} matchup(s) with more than one date in `schedule`:\n")
    for season, type_, round_, home, away, home_code, away_code, ids, dates, n in rows:
        home_name = db.display_name(conn, home, season)
        away_name = db.display_name(conn, away, season)
        print(f"  {home_name} vs {away_name}  ({season} {type_}{'/' + round_ if round_ else ''})")
        for sid, d in zip(ids.split(","), dates.split(",")):
            print(f"    schedule_id={sid}  date={d}")
        print()

    print(f"Total rows involved: {sum(r[9] for r in rows)}  "
          f"(expected to collapse down to {len(rows)} once duplicates are resolved)")


if __name__ == "__main__":
    main()

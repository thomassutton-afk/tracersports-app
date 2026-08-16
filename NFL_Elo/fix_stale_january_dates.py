"""
fix_stale_january_dates.py

Targeted cleanup for one specific, very identifiable class of bad row:
a `schedule` entry with season=S but a date in January (or earlier) of
that SAME calendar year S. That's chronologically impossible for the
NFL -- season S always starts in September of year S and, if a game
falls in January/February, it's January/February of year S+1, never
year S itself. So any row shaped like (season=2026, date=2026-01-03) is
provably wrong, not a judgment call.

This is exactly what's left over after correcting a source file's dates
and re-running add_season.py: the corrected (season=2026, date=2027-01-03)
row gets added, but the original bad (season=2026, date=2026-01-03) row
is never removed on its own.

Safety rule: this will only delete a stale row if a matching CORRECTED
row (same season/type/round/home_team/away_team, but a chronologically
valid date) already exists in the table -- i.e. it only cleans up
confirmed duplicates, never removes a row that has no replacement and
would leave a gap in the schedule.

Usage:
    python3 fix_stale_january_dates.py nfl_elo.db --season 2026
    python3 fix_stale_january_dates.py nfl_elo.db --season 2026 --dry-run
"""
import sys
import argparse
import db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", nargs="?", default="nfl_elo.db")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true",
                     help="show what would be deleted without deleting anything")
    args = ap.parse_args()

    conn = db.connect(args.db_path)
    season = args.season

    # Every schedule row tagged with this season
    rows = conn.execute(
        "SELECT schedule_id, date, type, round, home_team, away_team, home_code, away_code "
        "FROM schedule WHERE season = ?",
        (season,),
    ).fetchall()

    stale = [r for r in rows if r[1].startswith(f"{season}-01") or r[1].startswith(f"{season}-02")
             or r[1].startswith(f"{season}-03") or r[1].startswith(f"{season}-04")
             or r[1].startswith(f"{season}-05") or r[1].startswith(f"{season}-06")
             or r[1].startswith(f"{season}-07") or r[1].startswith(f"{season}-08")]

    if not stale:
        print(f"No chronologically-impossible dates found for season {season} -- nothing to fix.")
        return

    print(f"Found {len(stale)} row(s) tagged season={season} with a date in Jan-Aug {season} "
          f"(impossible -- the season hasn't started yet at that point):\n")

    to_delete = []
    for sid, d, type_, round_, home, away, home_code, away_code in stale:
        from datetime import date as date_cls
        stale_date = date_cls.fromisoformat(d)
        correct_date = stale_date.replace(year=stale_date.year + 1).isoformat()

        # Look specifically for the exact year-rollover counterpart (same month/day,
        # year+1) -- NOT just "any other game between these two teams later in the
        # season," which can coincidentally exist (these two teams may have a
        # legitimate, unrelated earlier meeting) and would make this match the
        # wrong row purely by luck of unordered SQL results.
        replacement = conn.execute(
            "SELECT schedule_id, date FROM schedule "
            "WHERE season = ? AND type = ? AND IFNULL(round,'RS') = IFNULL(?,'RS') "
            "AND home_team = ? AND away_team = ? AND schedule_id != ? AND date = ?",
            (season, type_, round_, home, away, sid, correct_date),
        ).fetchone()

        home_name = db.display_name(conn, home, season)
        away_name = db.display_name(conn, away, season)
        if replacement:
            print(f"  STALE: {home_name} vs {away_name}  date={d}  "
                  f"(exact year-rollover replacement confirmed: schedule_id={replacement[0]}, "
                  f"date={replacement[1]}) -> will delete")
            to_delete.append(sid)
        else:
            print(f"  STALE: {home_name} vs {away_name}  date={d}  "
                  f"-- no exact {correct_date} replacement found -- leaving this one alone, "
                  f"needs a manual look")

    if not to_delete:
        print("\nNothing safe to delete (no confirmed replacements found).")
        return

    print(f"\n{'Would delete' if args.dry_run else 'Deleting'} {len(to_delete)} confirmed-stale row(s).")
    if args.dry_run:
        print("(dry run -- nothing was actually deleted; re-run without --dry-run to apply)")
        return

    conn.executemany("DELETE FROM schedule WHERE schedule_id = ?", [(sid,) for sid in to_delete])
    conn.commit()
    print("Done.")


if __name__ == "__main__":
    main()

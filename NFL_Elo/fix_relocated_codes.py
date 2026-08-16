"""
fix_relocated_codes.py

ONE-TIME cleanup for a specific mistake: loading a schedule/results file
that uses modern nflverse-style codes (LAC/LAR/LV) instead of the codes
Continelo has always used for those same three franchises (SD/STL/OAK -
see build_nfl_db.py's docstring). Since those codes had never been
registered as aliases, add_season.py did exactly what it's documented to
do with an unrecognized code: it minted three brand new phantom
franchises starting at the base rating, instead of resolving to the
real, long-running Chargers/Rams/Raiders history.

This script:
  1. Finds each phantom team_id (the one currently aliased to LAC/LAR/LV).
  2. Finds the REAL team_id for the corresponding old code (SD/STL/OAK).
  3. Deletes every schedule row that references a phantom team_id (these
     are exactly the rows that got created wrong; nothing else is touched).
  4. Deletes the phantom's team_history, team_aliases, and teams rows.
  5. Re-registers LAC/LAR/LV as aliases pointing at the REAL team_id
     instead, so every future file using those codes resolves correctly.

It does NOT touch anything in `games` or `ratings` - this only affects
brand-new phantom teams that (by definition) have zero played games yet.

After running this, re-run add_season.py on the same source file. The
schedule rows this script deleted will be correctly re-inserted under
the real team_ids; every other row in that file is untouched and will
just be silently ignored as an already-existing duplicate.

Usage:
    python3 fix_relocated_codes.py nfl_elo.db
"""
import sys
import db

# new-file code -> the code Continelo has always used for that same franchise
CODE_FIXES = {
    "LAC": "SD",   # LA/San Diego Chargers
    "LAR": "STL",  # LA/St. Louis Rams
    "LV": "OAK",   # LV/Oakland Raiders
}


def fix_one(conn, new_code: str, real_code: str) -> None:
    phantom_row = conn.execute(
        "SELECT team_id FROM team_aliases WHERE alias = ?", (new_code,)
    ).fetchone()
    if not phantom_row:
        print(f"  {new_code}: no alias found at all -- nothing to fix (maybe already fixed?).")
        return
    phantom_id = phantom_row[0]

    real_row = conn.execute(
        "SELECT team_id FROM team_aliases WHERE alias = ?", (real_code,)
    ).fetchone()
    if not real_row:
        print(f"  {new_code}: can't find the real team_id for '{real_code}' -- "
              f"skipping this one, needs a manual look.")
        return
    real_id = real_row[0]

    if phantom_id == real_id:
        print(f"  {new_code}: already correctly aliased to {real_id} -- nothing to fix.")
        return

    n_sched = conn.execute(
        "SELECT COUNT(*) FROM schedule WHERE home_team = ? OR away_team = ?",
        (phantom_id, phantom_id),
    ).fetchone()[0]
    conn.execute("DELETE FROM schedule WHERE home_team = ? OR away_team = ?",
                 (phantom_id, phantom_id))

    conn.execute("DELETE FROM team_history WHERE team_id = ?", (phantom_id,))
    conn.execute("DELETE FROM team_aliases WHERE alias = ?", (new_code,))
    conn.execute("DELETE FROM teams WHERE team_id = ?", (phantom_id,))

    db.add_alias(conn, new_code, real_id, note=f"nflverse code for {real_code}")

    print(f"  {new_code}: removed phantom team {phantom_id} (and {n_sched} bad schedule "
          f"row(s) referencing it), re-aliased '{new_code}' -> {real_id} ('{real_code}').")


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "nfl_elo.db"
    conn = db.connect(db_path)

    print(f"Fixing relocated-franchise code mismatches in {db_path}:\n")
    for new_code, real_code in CODE_FIXES.items():
        fix_one(conn, new_code, real_code)

    conn.commit()
    print("\nDone. Now re-run add_season.py on the same source file to correctly "
          "re-insert the schedule rows that were just deleted, under the real team_ids.")


if __name__ == "__main__":
    main()

"""
reingest_phase2.py - Re-loads every historical season into cfb_elo.db
using the Phase 2 postseason classification (dedup + Round labels),
so it actually takes effect in the stored database - not just in
fresh normalize_sr_games.py output like test_phase2.py checked.

WHAT THIS DOES, IN ORDER:
  1. Backs up cfb_elo.db to a timestamped file FIRST. Always run this
     script with that backup step intact - if anything looks wrong
     afterward, you restore the backup and investigate, rather than
     re-deriving 30 seasons of history from scratch.
  2. For every season with a raw file in Results/ (1996-2025), re-runs
     normalize_sr_games.py against the raw CSV, then DELETES that
     season's existing rows from games/schedule and reloads them fresh
     from the newly-classified/deduped output. The delete-first step
     matters - see module note above on why a naive re-run would
     double up postseason games instead of replacing them.
  3. Runs ONE rebuild_ratings() pass per variant (echo, pulse) at the
     end, not once per season (which would be needlessly slow -
     rebuild_ratings() replays the ENTIRE database's history every
     time it's called).
  4. Runs sanity_checks() and prints a before/after summary, including
     the Round label breakdown across the whole database.

Run from inside CFB_Elo:
    python reingest_phase2.py

Nothing here touches conference/division data, franchise resets, or
FCS membership tables - none of those are populated by add_season.py
in the first place (see its own docstring), so a games-only reload
can't disturb them.
"""
import glob
import os
import shutil
import sqlite3
from datetime import datetime

import normalize_sr_games
import add_season
import rebuild
from rebuild import VARIANTS

DB_PATH = "cfb_elo.db"
RESULTS_DIR = "Results"
PARSED_DIR = "parsed_results"


def backup_db() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"cfb_elo_backup_{ts}.db"
    shutil.copy(DB_PATH, backup_path)
    print(f"Backed up {DB_PATH} -> {backup_path}")
    return backup_path


def reload_season(conn, season: int) -> dict:
    raw_path = os.path.join(RESULTS_DIR, f"CFB_{season}_Results.csv")
    if not os.path.exists(raw_path):
        print(f"  {season}: SKIPPED, no raw file at {raw_path}")
        return {}

    os.makedirs(PARSED_DIR, exist_ok=True)
    parsed_path = os.path.join(PARSED_DIR, f"parsed_games_{season}.csv")
    df = normalize_sr_games.normalize(raw_path)
    df.to_csv(parsed_path, index=False)

    before = conn.execute("SELECT COUNT(*) FROM games WHERE season=?", (season,)).fetchone()[0]
    conn.execute("DELETE FROM games WHERE season=?", (season,))
    conn.execute("DELETE FROM schedule WHERE season=?", (season,))
    conn.commit()

    stats, seasons_touched, new_teams = add_season.load_file(conn, parsed_path)
    after = conn.execute("SELECT COUNT(*) FROM games WHERE season=?", (season,)).fetchone()[0]

    extra = f", {len(new_teams)} new team(s)" if new_teams else ""
    print(f"  {season}: {before} -> {after} games "
          f"({stats.get('attempted', 0)} attempted, {stats.get('inserted', 0)} inserted, "
          f"{stats.get('scheduled', 0)} scheduled){extra}")
    return stats


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found in this folder - run this from inside CFB_Elo.")
        return

    backup_db()
    conn = sqlite3.connect(DB_PATH)

    raw_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "CFB_*_Results.csv")))
    seasons = sorted(int(os.path.basename(f).split("_")[1]) for f in raw_files)
    print(f"Reloading {len(seasons)} seasons: {seasons[0]}-{seasons[-1]}")
    print()

    for season in seasons:
        reload_season(conn, season)

    print()
    print("Rebuilding ratings for all variants (this is the slow part - be patient)...")
    for variant in VARIANTS:
        rebuild.rebuild_ratings(conn, variant)
        print(f"  {variant}: done")

    warnings = rebuild.sanity_checks(conn, seasons, "echo")
    print()
    print(f"Sanity check warnings: {len(warnings)}")
    for w in warnings:
        print(" ", w)

    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    round_counts = conn.execute(
        "SELECT COALESCE(round, '(none - regular season)'), COUNT(*) "
        "FROM games GROUP BY round ORDER BY 2 DESC"
    ).fetchall()
    print()
    print(f"Total games in database: {total_games}")
    print("Round label breakdown (whole database, all seasons):")
    for round_, count in round_counts:
        print(f"  {round_}: {count}")

    conn.close()
    print()
    print("Done. If anything looks wrong, restore the backup (cfb_elo_backup_*.db) and investigate.")


if __name__ == "__main__":
    main()

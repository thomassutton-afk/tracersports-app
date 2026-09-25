"""
test_phase2.py - Smoke test for the postseason Phase 2 patch.

Run this from inside your CFB_Elo folder:
    python test_phase2.py

It does two things, printing what it finds along the way:

  PART 1 - Re-normalizes one season from each postseason era and
  prints the Round value counts, so you can eyeball that the
  classification looks sane (e.g. does 2024 show CFP-R1/CFP-QF/
  CFP-SF/NC in the counts you'd expect from a 12-team bracket?).

  PART 2 - Copies your REAL cfb_elo.db to a throwaway file, runs a
  full rebuild against the copy using the current (patched) code, and
  diffs every team's post_rate against your untouched original
  database. Since every new multiplier still defaults to a no-op
  (bowl_rank_bonus_max=0.0, postseason_round_mult={}, etc.), the
  ratings should come back IDENTICAL for every game except the ~8
  that were previously double-counted duplicates (six bowl games plus
  the 2010 SEC Championship Game) - those teams' ratings should shift
  slightly now that the duplicate is gone.

  Your real cfb_elo.db is never touched - all rebuilding happens
  against a copy in a temp file, which this script deletes at the end.
"""
import shutil
import sqlite3
import tempfile
import os

import normalize_sr_games
import rebuild

REAL_DB = "cfb_elo.db"
RESULTS_DIR = "Results"

# One representative season per postseason era.
TEST_SEASONS = [1996, 1998, 2000, 2006, 2010, 2014, 2015, 2024, 2025]


def part1_classification_check():
    print("=" * 70)
    print("PART 1 - Round classification counts by era")
    print("=" * 70)
    for year in TEST_SEASONS:
        path = os.path.join(RESULTS_DIR, f"CFB_{year}_Results.csv")
        if not os.path.exists(path):
            print(f"{year}: SKIPPED (file not found at {path})")
            continue
        out = normalize_sr_games.normalize(path)
        counts = out[out["Round"].notna()]["Round"].value_counts().to_dict()
        print(f"{year}: {counts}")
    print()


def part2_rating_diff_check():
    print("=" * 70)
    print("PART 2 - Full rebuild against a scratch copy, diffed vs. real db")
    print("=" * 70)
    if not os.path.exists(REAL_DB):
        print(f"SKIPPED - {REAL_DB} not found in this folder.")
        return

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(tmp_fd)
    shutil.copy(REAL_DB, tmp_path)

    try:
        conn = sqlite3.connect(tmp_path)
        rebuild.rebuild_ratings(conn, "echo")
        warnings = rebuild.sanity_checks(conn, range(1996, 2026), "echo")
        print(f"Sanity check warnings: {len(warnings)}")
        for w in warnings[:10]:
            print(" ", w)

        old = sqlite3.connect(REAL_DB)
        old_ratings = dict(old.execute(
            "SELECT team||'-'||season||'-'||game_id, post_rate "
            "FROM ratings WHERE variant='echo'"
        ).fetchall())
        new_ratings = dict(conn.execute(
            "SELECT team||'-'||season||'-'||game_id, post_rate "
            "FROM ratings WHERE variant='echo'"
        ).fetchall())
        old.close()

        print(f"Old row count: {len(old_ratings)}  New row count: {len(new_ratings)}")

        diffs = [
            k for k in old_ratings
            if k in new_ratings and abs(old_ratings[k] - new_ratings[k]) > 1e-9
        ]
        print(f"Rating differences: {len(diffs)}")
        if diffs:
            print("  (Expect a small handful here - the games that were previously")
            print("   double-counted duplicates. A large number would mean something")
            print("   unexpected changed - worth digging into before merging.)")
            for k in diffs[:15]:
                print(f"   {k}: old={old_ratings[k]:.3f} new={new_ratings[k]:.3f}")

        conn.close()
    finally:
        os.remove(tmp_path)


if __name__ == "__main__":
    part1_classification_check()
    part2_rating_diff_check()

#!/usr/bin/env python3
"""
split_calibration.py

Splits the elo_ledger into two groups -- games between two D1 teams, and
games where one side is a non-D1 ("D2" flat-rated) opponent -- and reports
accuracy/Brier/calibration separately for each. This isolates whether the
flat D2 fallback rating (1,125, never updated) is driving the overconfidence
seen in the 80-100% bucket of the full-season calibration check.

Only counts each game once (using the row where `team` is the D1 side, so
a D1-vs-D1 game is naturally counted from both directions -- harmless for
averaged metrics since both rows carry identical accuracy/Brier values).

USAGE
-----
    python split_calibration.py cbb_1996.db
"""

import argparse
import sqlite3
from pathlib import Path


def pct(x):
    return f"{100*x:.1f}%"


def report(cur, where_clause, label):
    row = cur.execute(f"""
        SELECT COUNT(*) AS n, AVG(accuracy) AS acc, AVG(brier) AS brier, AVG(log_loss) AS ll
        FROM elo_ledger e
        JOIN teams t1 ON e.team = t1.team_name
        LEFT JOIN teams t2 ON e.opponent = t2.team_name
        WHERE {where_clause}
    """).fetchone()
    print(f"\n=== {label} ({row['n']:,} rows) ===")
    if not row["n"]:
        print("  (no games in this category)")
        return
    print(f"  Accuracy: {pct(row['acc'])}   Brier: {row['brier']:.4f}   Log loss: {row['ll']:.4f}")

    print(f"  {'Bucket':<12} {'Games':>7} {'Predicted avg':>15} {'Actual win rate':>17}")
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    for lo, hi in buckets:
        r = cur.execute(f"""
            SELECT COUNT(*) AS n, AVG(expected_win_pct) AS pred, AVG(result) AS actual
            FROM elo_ledger e
            JOIN teams t1 ON e.team = t1.team_name
            LEFT JOIN teams t2 ON e.opponent = t2.team_name
            WHERE {where_clause} AND e.expected_win_pct >= ? AND e.expected_win_pct < ?
        """, (lo, hi)).fetchone()
        if r["n"]:
            print(f"  {lo:.0%}-{hi:.0%}     {r['n']:>7} {pct(r['pred']):>15} {pct(r['actual']):>17}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", type=Path)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    report(cur, "t2.team_name IS NOT NULL", "D1 vs D1 games")
    report(cur, "t2.team_name IS NULL", "D1 vs non-D1 (D2 flat-rated) games")

    conn.close()


if __name__ == "__main__":
    main()

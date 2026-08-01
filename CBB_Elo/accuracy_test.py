#!/usr/bin/env python3
"""
accuracy_test.py

Analyzes the elo_ledger table (written by run_elo_1996.py) to see how well
the Elo model actually predicted game outcomes across the 1995-96 season.

Uses the same metrics the workbook itself defines:
  - Accuracy: did the model's favorite (Expected >= 50%) actually win?
  - Brier score: mean squared error between Expected win% and Result
                 (0 = perfect, 0.25 = always guessing 50/50, 1 = perfectly wrong)
  - Log loss: cross-entropy between Expected win% and Result
              (0 = perfect, heavily penalizes confident-and-wrong predictions)

Also reports two baselines for context:
  - "Coin flip": what you'd get always guessing 50/50 (Brier = 0.25)
  - "Always home team": accuracy from blindly picking the home team every
    time (a common sanity-check baseline in sports prediction)

USAGE
-----
    python accuracy_test.py cbb_1996.db
"""

import argparse
import sqlite3
from pathlib import Path


def pct(x):
    return f"{100*x:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", type=Path)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='elo_ledger'").fetchone():
        print("No elo_ledger table found -- run run_elo_1996.py first.")
        return

    n_rows = cur.execute("SELECT COUNT(*) FROM elo_ledger").fetchone()[0]
    n_games = n_rows // 2  # each game produces two ledger rows (home + away perspective)
    print(f"{n_games:,} games ({n_rows:,} ledger rows) in {args.db_path}\n")

    # --- overall metrics ---
    overall = cur.execute("""
        SELECT AVG(accuracy) AS acc, AVG(brier) AS brier, AVG(log_loss) AS ll
        FROM elo_ledger
    """).fetchone()

    home_win_rate = cur.execute("""
        SELECT AVG(CASE WHEN home_away='H' AND result=1 THEN 1
                        WHEN home_away='A' AND result=0 THEN 1
                        ELSE 0 END)
        FROM elo_ledger WHERE home_away IN ('H','A')
    """).fetchone()[0]

    print("=== Overall ===")
    print(f"  Accuracy (favorite won):  {pct(overall['acc'])}")
    print(f"  Brier score:              {overall['brier']:.4f}   (0=perfect, 0.25=coin flip)")
    print(f"  Log loss:                 {overall['ll']:.4f}   (0=perfect)")
    print()
    print("=== Baselines for context ===")
    print(f"  Coin flip (always 50%):   Brier = 0.2500")
    print(f"  Always pick home team:    {pct(home_win_rate)} accuracy in games with a real home team")
    print()

    # --- by game type / tournament tier ---
    print("=== By game type ===")
    rows = cur.execute("""
        SELECT
            CASE
                WHEN t_mult = 1.0 THEN 'Regular season'
                ELSE 'Tournament'
            END AS category,
            COUNT(*)/2 AS games,
            AVG(accuracy) AS acc,
            AVG(brier) AS brier
        FROM elo_ledger
        GROUP BY category
        ORDER BY games DESC
    """).fetchall()
    for r in rows:
        print(f"  {r['category']:<16} {r['games']:>5} games   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- by home/away/neutral ---
    print("=== By venue ===")
    rows = cur.execute("""
        SELECT home_away, COUNT(*) AS n, AVG(accuracy) AS acc, AVG(brier) AS brier
        FROM elo_ledger GROUP BY home_away ORDER BY home_away
    """).fetchall()
    label = {"H": "Home team's perspective", "A": "Away team's perspective", "N": "Neutral site"}
    for r in rows:
        print(f"  {label.get(r['home_away'], r['home_away']):<26} {r['n']:>5} rows   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- calibration: does a 70% "expected" team actually win ~70% of the time? ---
    print("=== Calibration (expected win% bucket vs actual win rate) ===")
    print(f"  {'Bucket':<12} {'Games':>7} {'Predicted avg':>15} {'Actual win rate':>17}")
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    for lo, hi in buckets:
        row = cur.execute("""
            SELECT COUNT(*) AS n, AVG(expected_win_pct) AS pred, AVG(result) AS actual
            FROM elo_ledger
            WHERE expected_win_pct >= ? AND expected_win_pct < ?
        """, (lo, hi)).fetchone()
        if row["n"]:
            print(f"  {lo:.0%}-{hi:.0%}     {row['n']:>7} {pct(row['pred']):>15} {pct(row['actual']):>17}")
    print()

    # --- how accuracy trends across the season (does the model improve as K settles?) ---
    print("=== Accuracy by month ===")
    rows = cur.execute("""
        SELECT substr(date,1,7) AS month, COUNT(*)/2 AS games, AVG(accuracy) AS acc, AVG(brier) AS brier
        FROM elo_ledger GROUP BY month ORDER BY month
    """).fetchall()
    for r in rows:
        print(f"  {r['month']}   {r['games']:>5} games   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- biggest upsets: lowest expected win% among winners ---
    print("=== 10 biggest upsets (lowest pre-game win probability for the winner) ===")
    rows = cur.execute("""
        SELECT date, team, opponent, expected_win_pct, points_for, points_against
        FROM elo_ledger
        WHERE result = 1.0
        ORDER BY expected_win_pct ASC
        LIMIT 10
    """).fetchall()
    for r in rows:
        print(f"  {r['date']}  {r['team']} beat {r['opponent']}  "
              f"({r['points_for']}-{r['points_against']}, given only {pct(r['expected_win_pct'])} to win)")

    conn.close()


if __name__ == "__main__":
    main()

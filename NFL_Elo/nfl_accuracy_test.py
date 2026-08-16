#!/usr/bin/env python3
"""
nfl_accuracy_test.py

Analyzes the `ratings` table in nfl_elo.db to see how well the Elo model
actually predicted game outcomes, with the option to restrict the analysis
to specific season(s).

Uses the same core metrics as the NBA/WNBA versions:
  - Accuracy: did the model's favorite (expected_win >= 50%) actually win?
  - Brier score: mean squared error between expected_win and result
                 (0 = perfect, 0.25 = always guessing 50/50, 1 = perfectly wrong)
  - Log loss: cross-entropy between expected_win and result
              (0 = perfect, heavily penalizes confident-and-wrong predictions;
               computed here since the table doesn't store it directly)

Also reports two baselines for context:
  - "Coin flip": what you'd get always guessing 50/50 (Brier = 0.25)
  - "Always home team": accuracy from blindly picking the home team every time

USAGE
-----
    python nfl_accuracy_test.py nfl_elo.db
    python nfl_accuracy_test.py nfl_elo.db --seasons 2023
    python nfl_accuracy_test.py nfl_elo.db --seasons 2021,2022,2023
    python nfl_accuracy_test.py nfl_elo.db --seasons 2015-2019
    python nfl_accuracy_test.py nfl_elo.db --seasons 2015-2019,2023
"""

import argparse
import math
import sqlite3
from pathlib import Path


def pct(x):
    return f"{100 * x:.1f}%"


def parse_seasons(spec: str):
    """Parse a seasons spec like '2023' / '2021,2022' / '2015-2019' / '2015-2019,2023'
    into a sorted list of individual season ints."""
    seasons = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            lo, hi = int(lo.strip()), int(hi.strip())
            if lo > hi:
                lo, hi = hi, lo
            seasons.update(range(lo, hi + 1))
        else:
            seasons.add(int(chunk))
    return sorted(seasons)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", type=Path)
    ap.add_argument(
        "--seasons",
        type=str,
        default=None,
        help="Season(s) to include, e.g. '2023', '2021,2022', '2015-2019', "
             "or '2015-2019,2023'. Default: all seasons in the table.",
    )
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if not cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ratings'"
    ).fetchone():
        print("No ratings table found in this database.")
        return

    available_seasons = [
        r[0] for r in cur.execute("SELECT DISTINCT season FROM ratings ORDER BY season")
    ]

    if args.seasons:
        seasons = parse_seasons(args.seasons)
        missing = [s for s in seasons if s not in available_seasons]
        if missing:
            print(f"Warning: no data for season(s) {missing} -- skipping those.\n")
        seasons = [s for s in seasons if s in available_seasons]
        if not seasons:
            print("None of the requested seasons are present in this database.")
            print(f"Available seasons: {available_seasons}")
            return
    else:
        seasons = available_seasons

    placeholders = ",".join("?" for _ in seasons)
    season_filter = f"season IN ({placeholders})"
    params = list(seasons)

    n_rows = cur.execute(
        f"SELECT COUNT(*) FROM ratings WHERE {season_filter}", params
    ).fetchone()[0]
    n_games = n_rows // 2  # each game produces two ledger rows (team + opponent perspective)

    season_label = (
        f"season {seasons[0]}"
        if len(seasons) == 1
        else f"seasons {seasons[0]}-{seasons[-1]}"
        if seasons == list(range(seasons[0], seasons[-1] + 1))
        else f"seasons {seasons}"
    )
    print(f"{n_games:,} games ({n_rows:,} ledger rows) -- {season_label} -- {args.db_path}\n")

    # --- overall metrics (Brier comes from the table; log loss computed here) ---
    overall = cur.execute(
        f"""
        SELECT AVG(accuracy) AS acc, AVG(brier) AS brier,
               expected_win, result
        FROM ratings WHERE {season_filter}
        """,
        params,
    )
    # Need accuracy/brier averages plus a full pass for log loss
    agg = cur.execute(
        f"SELECT AVG(accuracy) AS acc, AVG(brier) AS brier FROM ratings WHERE {season_filter}",
        params,
    ).fetchone()

    eps = 1e-15
    ll_rows = cur.execute(
        f"SELECT expected_win, result FROM ratings WHERE {season_filter}", params
    ).fetchall()
    log_losses = []
    for r in ll_rows:
        p = min(max(r["expected_win"], eps), 1 - eps)
        y = r["result"]
        log_losses.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    avg_ll = sum(log_losses) / len(log_losses) if log_losses else float("nan")

    home_win_rate = cur.execute(
        f"""
        SELECT AVG(CASE WHEN home_away='H' AND result=1 THEN 1
                        WHEN home_away='A' AND result=0 THEN 1
                        ELSE 0 END)
        FROM ratings WHERE {season_filter} AND home_away IN ('H','A')
        """,
        params,
    ).fetchone()[0]

    print("=== Overall ===")
    print(f"  Accuracy (favorite won):  {pct(agg['acc'])}")
    print(f"  Brier score:              {agg['brier']:.4f}   (0=perfect, 0.25=coin flip)")
    print(f"  Log loss:                 {avg_ll:.4f}   (0=perfect)")
    print()
    print("=== Baselines for context ===")
    print(f"  Coin flip (always 50%):   Brier = 0.2500")
    print(f"  Always pick home team:    {pct(home_win_rate)} accuracy in games with a real home team")
    print()

    # --- by game type: Regular season vs Playoffs ---
    print("=== By game type ===")
    rows = cur.execute(
        f"""
        SELECT
            CASE WHEN type = 'R' THEN 'Regular season' ELSE 'Playoffs' END AS category,
            COUNT(*) / 2 AS games,
            AVG(accuracy) AS acc,
            AVG(brier) AS brier
        FROM ratings
        WHERE {season_filter}
        GROUP BY category
        ORDER BY games DESC
        """,
        params,
    ).fetchall()
    for r in rows:
        print(f"  {r['category']:<16} {r['games']:>5} games   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- by home/away ---
    print("=== By venue ===")
    rows = cur.execute(
        f"""
        SELECT home_away, COUNT(*) AS n, AVG(accuracy) AS acc, AVG(brier) AS brier
        FROM ratings WHERE {season_filter} GROUP BY home_away ORDER BY home_away
        """,
        params,
    ).fetchall()
    label = {"H": "Home team's perspective", "A": "Away team's perspective", "N": "Neutral site"}
    for r in rows:
        print(f"  {label.get(r['home_away'], r['home_away']):<26} {r['n']:>5} rows   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- calibration: does a 70% "expected" team actually win ~70% of the time? ---
    print("=== Calibration (expected win% bucket vs actual win rate) ===")
    print(f"  {'Bucket':<12} {'Games':>7} {'Predicted avg':>15} {'Actual win rate':>17}")
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    for lo, hi in buckets:
        row = cur.execute(
            f"""
            SELECT COUNT(*) AS n, AVG(expected_win) AS pred, AVG(result) AS actual
            FROM ratings
            WHERE {season_filter} AND expected_win >= ? AND expected_win < ?
            """,
            params + [lo, hi],
        ).fetchone()
        if row["n"]:
            print(f"  {lo:.0%}-{hi:.0%}     {row['n']:>7} {pct(row['pred']):>15} {pct(row['actual']):>17}")
    print()

    # --- accuracy by season (only meaningful/interesting when multiple seasons selected) ---
    print("=== Accuracy by season ===")
    rows = cur.execute(
        f"""
        SELECT season, COUNT(*) / 2 AS games, AVG(accuracy) AS acc, AVG(brier) AS brier
        FROM ratings WHERE {season_filter} GROUP BY season ORDER BY season
        """,
        params,
    ).fetchall()
    for r in rows:
        print(f"  {r['season']}   {r['games']:>5} games   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- accuracy trend by month within the selected season(s) ---
    print("=== Accuracy by month ===")
    rows = cur.execute(
        f"""
        SELECT substr(date,1,7) AS month, COUNT(*) / 2 AS games, AVG(accuracy) AS acc, AVG(brier) AS brier
        FROM ratings WHERE {season_filter} GROUP BY month ORDER BY month
        """,
        params,
    ).fetchall()
    for r in rows:
        print(f"  {r['month']}   {r['games']:>5} games   acc {pct(r['acc'])}   brier {r['brier']:.4f}")
    print()

    # --- biggest upsets: lowest expected win% among winners ---
    print("=== 10 biggest upsets (lowest pre-game win probability for the winner) ===")
    rows = cur.execute(
        f"""
        SELECT date, team, opponent, expected_win, points_for, points_against
        FROM ratings
        WHERE {season_filter} AND result = 1.0
        ORDER BY expected_win ASC
        LIMIT 10
        """,
        params,
    ).fetchall()
    for r in rows:
        print(
            f"  {r['date']}  {r['team']} beat {r['opponent']}  "
            f"({r['points_for']}-{r['points_against']}, given only {pct(r['expected_win'])} to win)"
        )

    conn.close()


if __name__ == "__main__":
    main()

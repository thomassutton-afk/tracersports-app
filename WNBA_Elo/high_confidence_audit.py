#!/usr/bin/env python3
"""
high_confidence_audit.py

Pulls every game where the model gave a team >= a confidence threshold
(default 90%) to win, and breaks down what's going on inside that bucket --
by game type, playoff round, po_mult, season, and rest/blowout context --
so you can see whether the modern-era overconfidence in the 90%+ bucket
traces back to a specific cause (playoff scaling, small sample, a handful
of teams, etc.) rather than a general model problem.

USAGE
-----
    python high_confidence_audit.py wnba_elo.db
    python high_confidence_audit.py wnba_elo.db --seasons 2012-2025
    python high_confidence_audit.py wnba_elo.db --threshold 0.85
    python high_confidence_audit.py wnba_elo.db --seasons 2012-2025 --csv out.csv
"""

import argparse
import csv as csv_module
import sqlite3
from pathlib import Path


def pct(x):
    return f"{100 * x:.1f}%"


def parse_seasons(spec: str):
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
        help="Season(s) to include, e.g. '2023', '2021,2022', '2012-2025'. "
             "Default: all seasons in the table.",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        help="Minimum expected_win to include a row (default 0.90).",
    )
    ap.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional path to also dump the full game-level detail as a CSV.",
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
            return
    else:
        seasons = available_seasons

    season_ph = ",".join("?" for _ in seasons)
    where = f"season IN ({season_ph}) AND expected_win >= ?"
    params = list(seasons) + [args.threshold]

    season_label = (
        f"season {seasons[0]}"
        if len(seasons) == 1
        else f"seasons {seasons[0]}-{seasons[-1]}"
        if seasons == list(range(seasons[0], seasons[-1] + 1))
        else f"seasons {seasons}"
    )

    rows = cur.execute(
        f"""
        SELECT date, season, type, round, po_mult, team, opponent, home_away,
               pre_rate, opp_pre_rate, expected_win, result, accuracy, brier,
               points_for, points_against, mov, mov_mult, k, keff,
               days_off, opp_days_off, rest_adj
        FROM ratings
        WHERE {where}
        ORDER BY date
        """,
        params,
    ).fetchall()

    if not rows:
        print(f"No games found at expected_win >= {args.threshold} for {season_label}.")
        return

    n = len(rows)
    n_correct = sum(r["accuracy"] for r in rows)
    n_wrong = n - n_correct
    avg_pred = sum(r["expected_win"] for r in rows) / n
    actual_rate = n_correct / n
    avg_brier = sum(r["brier"] for r in rows) / n

    print(f"=== High-confidence audit (expected_win >= {pct(args.threshold)}) -- {season_label} -- {args.db_path} ===\n")
    print(f"  Rows (team-perspective):   {n}")
    print(f"  Predicted avg win%:        {pct(avg_pred)}")
    print(f"  Actual favorite win rate:  {pct(actual_rate)}")
    print(f"  Gap (predicted - actual):  {pct(avg_pred - actual_rate)}")
    print(f"  Avg Brier in this bucket:  {avg_brier:.4f}")
    print()

    # --- breakdown by game type ---
    print("=== By game type ===")
    by_type = {}
    for r in rows:
        key = "Regular season" if r["type"] == "R" else "Playoffs"
        by_type.setdefault(key, []).append(r)
    for key, grp in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        acc = sum(g["accuracy"] for g in grp) / len(grp)
        pred = sum(g["expected_win"] for g in grp) / len(grp)
        print(f"  {key:<16} {len(grp):>4} rows   predicted {pct(pred)}   actual {pct(acc)}   gap {pct(pred-acc)}")
    print()

    # --- breakdown by playoff round / po_mult, if any playoff rows present ---
    po_rows = [r for r in rows if r["type"] != "R"]
    if po_rows:
        print("=== Playoff rows by round / po_mult ===")
        by_round = {}
        for r in po_rows:
            key = (r["round"], r["po_mult"])
            by_round.setdefault(key, []).append(r)
        for (rnd, pm), grp in sorted(by_round.items(), key=lambda kv: (kv[0][0] or 0)):
            acc = sum(g["accuracy"] for g in grp) / len(grp)
            pred = sum(g["expected_win"] for g in grp) / len(grp)
            rnd_label = f"round {rnd}" if rnd is not None else "round n/a"
            print(f"  {rnd_label:<12} po_mult {pm:<6} {len(grp):>4} rows   predicted {pct(pred)}   actual {pct(acc)}   gap {pct(pred-acc)}")
        print()

    # --- breakdown by season ---
    print("=== By season ===")
    by_season = {}
    for r in rows:
        by_season.setdefault(r["season"], []).append(r)
    for season, grp in sorted(by_season.items()):
        acc = sum(g["accuracy"] for g in grp) / len(grp)
        pred = sum(g["expected_win"] for g in grp) / len(grp)
        print(f"  {season}   {len(grp):>4} rows   predicted {pct(pred)}   actual {pct(acc)}   gap {pct(pred-acc)}")
    print()

    # --- rest/blowout context stats ---
    avg_rest_adj = sum(r["rest_adj"] for r in rows) / n
    avg_mov_mult = sum(r["mov_mult"] for r in rows) / n
    avg_keff = sum(r["keff"] for r in rows) / n
    print("=== Context averages across this bucket ===")
    print(f"  Avg rest_adj:  {avg_rest_adj:.3f}")
    print(f"  Avg mov_mult:  {avg_mov_mult:.3f}")
    print(f"  Avg keff:      {avg_keff:.2f}")
    print()

    # --- the misses: every upset where the "sure thing" lost ---
    misses = [r for r in rows if r["result"] == 0.0]
    misses.sort(key=lambda r: -r["expected_win"])
    print(f"=== All {len(misses)} misses in this bucket (favorite lost) ===")
    print(f"  {'Date':<12} {'Season':<7} {'Type':<5} {'Favorite':<10} {'Beaten by':<10} {'Pred%':>7} {'Score':>9}")
    for r in misses:
        score = f"{r['points_against']}-{r['points_for']}"
        print(
            f"  {r['date']:<12} {r['season']:<7} {r['type']:<5} {r['team']:<10} "
            f"{r['opponent']:<10} {pct(r['expected_win']):>7} {score:>9}"
        )
    print()

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv_module.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for r in rows:
                writer.writerow(dict(r))
        print(f"Full game-level detail written to {args.csv}")

    conn.close()


if __name__ == "__main__":
    main()

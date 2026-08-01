"""
Calibration backtest for simulate_season.py.

Instead of eyeballing whether projected win ranges "look about right,"
this reconstructs a series of weekly historical checkpoints from a
database that already has the FULL completed season loaded, re-runs
the Monte Carlo projection as if standing at that point in time, and
grades each projection against the now-known final result.

CHECKPOINT SPACING: checkpoints are exactly `--days` (default 7) apart,
anchored to the LAST game date and walking backward. Any leftover time
that doesn't divide evenly into full periods falls at the START of the
season (a short first "week"), not the end - so every checkpoint you
compare across weeks represents the same-length lookahead except the
very first one.

MARGIN SAMPLING: by default, the margin-of-victory for each simulated
game is drawn only from real games that had ALREADY happened as of
that checkpoint (`--allow-mov-leak` reverts to sampling from the full
season, matching production simulate_season.py, but that lets
information from the future leak into early-season checkpoints).

Two numbers come out of this:

1. COVERAGE: of all (team, checkpoint) projections, what fraction had
   the actual final win total fall inside the reported 10th-90th
   percentile band? A well-calibrated model should land close to 80%.
   Materially above/below that means the bands are too wide/narrow.

2. PIT (probability integral transform): for each projection, where
   does the actual outcome fall within that trial's full simulated
   distribution (as a percentile, 0-100)? Across many projections
   these percentiles should be roughly UNIFORM. Clustering near 50
   means bands are too wide (underconfident); clustering near the
   edges (0/100) means bands are too narrow (overconfident).

Usage:
    python3 backtest_calibration.py --season 2026
    python3 backtest_calibration.py --season 2026 --trials 300 --days 7
    python3 backtest_calibration.py --season 2026 --allow-mov-leak

Writes reports/calibration_<season>.csv (one row per team/checkpoint)
and prints the aggregate coverage + PIT summary to stdout.
"""
import argparse
import copy
import csv
import os
import random
from collections import defaultdict
from datetime import timedelta

import db
import engine

DB_PATH = "nba_elo.db"
OUT_DIR = "reports"


def wl_from_games(games):
    """W/L record for every team across exactly the games given."""
    wl = defaultdict(lambda: [0, 0])
    for g in games:
        if g["home_pts"] > g["away_pts"]:
            wl[g["home_team"]][0] += 1
            wl[g["away_team"]][1] += 1
        else:
            wl[g["away_team"]][0] += 1
            wl[g["home_team"]][1] += 1
    return {t: tuple(v) for t, v in wl.items()}


def mov_pool_from(games):
    pool = [abs(g["home_pts"] - g["away_pts"]) for g in games if g["home_pts"] != g["away_pts"]]
    return pool or [10]


def build_engine_from(games, params, resets):
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        eng.process_game(g)
    return eng


def weekly_checkpoints(first_date, last_date, days):
    """Checkpoint dates spaced exactly `days` apart, anchored to
    last_date and walking backward, so any leftover period shorter
    than `days` falls at the start of the season rather than the end.
    Excludes last_date itself (no games would remain to simulate)."""
    checkpoints = []
    d = last_date - timedelta(days=days)
    while d > first_date:
        checkpoints.append(d)
        d -= timedelta(days=days)
    return sorted(checkpoints)


def simulate_from_checkpoint(eng, remaining, mov_pool, trials, rng):
    """Returns {team: [simulated_added_wins per trial]}."""
    per_team_wins = defaultdict(list)
    for _ in range(trials):
        trial_eng = copy.deepcopy(eng)
        trial_w = defaultdict(int)
        for g in remaining:
            preview = trial_eng.preview_matchup(
                home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
                season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
            )
            home_wins = rng.random() < preview["expected_win_home"]
            margin = rng.choice(mov_pool)
            home_pts, away_pts = (100 + margin, 100) if home_wins else (100, 100 + margin)
            synthetic = dict(
                date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                home_team=g["home_team"], away_team=g["away_team"],
                home_pts=home_pts, away_pts=away_pts, ot=0, neutral=g["neutral"],
            )
            trial_eng.process_game(synthetic)
            if home_wins:
                trial_w[g["home_team"]] += 1
            else:
                trial_w[g["away_team"]] += 1
        teams_this_trial = set(trial_w) | set(per_team_wins)
        for t in teams_this_trial:
            per_team_wins[t].append(trial_w.get(t, 0))
    return per_team_wins


def percentile(sorted_vals, p):
    n = len(sorted_vals)
    idx = min(n - 1, max(0, int(p * n)))
    return sorted_vals[idx]


def pit_rank(sorted_vals, actual):
    """Fraction of simulated trials <= actual. 0=actual beat nothing,
    1=actual beat everything. Uses simple ECDF; ties split at midpoint."""
    n = len(sorted_vals)
    less = sum(1 for v in sorted_vals if v < actual)
    equal = sum(1 for v in sorted_vals if v == actual)
    return (less + 0.5 * equal) / n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--trials", type=int, default=300, help="trials per checkpoint (lower than production for speed)")
    parser.add_argument("--days", type=int, default=7, help="checkpoint spacing in days, anchored to season end")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow-mov-leak", action="store_true",
                         help="sample margins from the FULL season (matches production simulate_season.py) "
                              "instead of only games known as of each checkpoint")
    args = parser.parse_args()

    conn = db.connect(DB_PATH)
    rng = random.Random(args.seed)
    params = db.load_active_params(conn) or engine.default_params()
    resets = db.load_resets(conn)

    all_games = [g for g in db.load_games(conn) if g["season"] == args.season]
    all_games.sort(key=lambda g: (g["date"], g["game_id"]))
    reg_games = [g for g in all_games if g["type"] == "R"]

    if not reg_games:
        print(f"No regular-season games found for {args.season}.")
        return

    final_wl = wl_from_games(reg_games)
    full_mov_pool = mov_pool_from(all_games)

    first_date, last_date = reg_games[0]["date"], reg_games[-1]["date"]
    checkpoint_dates = weekly_checkpoints(first_date, last_date, args.days)

    rows = []
    for checkpoint_date in checkpoint_dates:
        games_so_far = [g for g in reg_games if g["date"] <= checkpoint_date]
        remaining = [g for g in reg_games if g["date"] > checkpoint_date]
        if not remaining or not games_so_far:
            continue
        current_wl = wl_from_games(games_so_far)

        eng = build_engine_from(games_so_far, params, resets)
        mov_pool = full_mov_pool if args.allow_mov_leak else mov_pool_from(games_so_far)

        sim_wins = simulate_from_checkpoint(eng, remaining, mov_pool, args.trials, rng)

        for team, added_wins in sim_wins.items():
            base_w, _ = current_wl.get(team, (0, 0))
            trial_finals = sorted(base_w + w for w in added_wins)
            actual_w, actual_l = final_wl.get(team, (None, None))
            if actual_w is None:
                continue

            p10 = percentile(trial_finals, 0.10)
            p50 = percentile(trial_finals, 0.50)
            p90 = percentile(trial_finals, 0.90)
            in_range = p10 <= actual_w <= p90
            pit = pit_rank(trial_finals, actual_w)

            rows.append(dict(
                date=checkpoint_date, games_remaining=len(remaining), team=team,
                current_w=base_w, p10=p10, p50=p50, p90=p90,
                actual_final_w=actual_w, in_range=in_range, pit=round(pit, 4),
            ))

    if not rows:
        print("No checkpoints produced any rows - season may be too short for the given --days.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, f"calibration_{args.season}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    coverage = sum(r["in_range"] for r in rows) / n
    below = sum(1 for r in rows if r["actual_final_w"] < r["p10"]) / n
    above = sum(1 for r in rows if r["actual_final_w"] > r["p90"]) / n

    pit_buckets = [0] * 10
    for r in rows:
        b = min(9, int(r["pit"] * 10))
        pit_buckets[b] += 1

    print(f"\n{n} team/checkpoint projections across {len(checkpoint_dates)} weekly checkpoints "
          f"({checkpoint_dates[0]} to {checkpoint_dates[-1]}).\n")
    print(f"Coverage (actual within p10-p90):  {coverage:.1%}   (target: ~80%)")
    print(f"Actual fell BELOW p10:              {below:.1%}   (target: ~10%)")
    print(f"Actual fell ABOVE p90:               {above:.1%}   (target: ~10%)")
    print("\nPIT histogram (should be roughly flat if well-calibrated):")
    for i, c in enumerate(pit_buckets):
        bar = "#" * int(c / max(pit_buckets) * 40) if max(pit_buckets) else ""
        print(f"  {i*10:>3}-{i*10+10:<3}%: {c:>4}  {bar}")

    print(f"\nWrote {csv_path}")


if __name__ == "__main__":
    main()

"""
nfl_reconstruct_engine.py

The real version of nfl_reconstruct.py -- same warm-up + rolling-window
idea, but driven by the actual engine.EloEngine instead of a simplified
stand-in. Because EloEngine.params is just a mutable attribute, one single
engine instance can run continuously across all 30 seasons while its
params get swapped at each season boundary -- team rating state carries
forward exactly like it does in production; only alpha/kmax/hfa change.

Also re-runs the era-stability check (tune separately per era) against
the real formula, since the whole point of doing this over is to confirm
the HFA-decay finding wasn't an artifact of the simplified engine.
"""
import sys
import json
import sqlite3
from collections import defaultdict

import pandas as pd

import engine
from nfl_tune_engine import load_games_as_dicts, games_to_weeks, run_engine, \
    coordinate_ascent_engine, log_loss_of

WARMUP_START = 1996
WARMUP_END = 2005
WINDOW_LEN = 10


def weeks_for_season_range(games: list[dict], lo: int, hi: int) -> list[list[dict]]:
    subset = [g for g in games if lo <= g["season"] <= hi]
    return games_to_weeks(subset)


def era_stability_check(games: list[dict], n_eras: int = 3, rounds: int = 3):
    print("=== Era stability (real engine) ===\n")
    seasons = sorted({g["season"] for g in games})
    n = len(seasons)
    edges = [seasons[int(i * n / n_eras)] for i in range(n_eras)] + [seasons[-1] + 1]
    for i in range(n_eras):
        lo, hi = edges[i], edges[i + 1] - 1
        weeks = weeks_for_season_range(games, lo, hi)
        tuned = coordinate_ascent_engine(weeks, rounds=rounds)
        print(f"  {lo}-{hi}: alpha={tuned['alpha']}  kmax={tuned['kmax']}  "
              f"hfa={tuned['hfa']}  log_loss={tuned['train_log_loss']:.4f}")
    print()


def build_schedule(games: list[dict], rounds: int = 3) -> pd.DataFrame:
    print("=== Building honest per-season schedule (real engine) ===\n")
    schedule = {}

    warmup_weeks = weeks_for_season_range(games, WARMUP_START, WARMUP_END)
    warmup_params = coordinate_ascent_engine(warmup_weeks, rounds=rounds)
    for y in range(WARMUP_START, WARMUP_END + 1):
        schedule[y] = {**warmup_params, "window": f"{WARMUP_START}-{WARMUP_END} (warm-up, in-sample)"}
    print(f"  warm-up {WARMUP_START}-{WARMUP_END}: alpha={warmup_params['alpha']} "
          f"kmax={warmup_params['kmax']} hfa={warmup_params['hfa']}")

    seasons = sorted({g["season"] for g in games})
    for y in [s for s in seasons if s > WARMUP_END]:
        win_start, win_end = y - WINDOW_LEN, y - 1
        weeks = weeks_for_season_range(games, win_start, win_end)
        params = coordinate_ascent_engine(weeks, rounds=rounds, start=(0.4, 44.0, 52.0))
        schedule[y] = {**params, "window": f"{win_start}-{win_end} (rolling, out-of-sample)"}
        print(f"  season {y}: tuned on {win_start}-{win_end}  ->  "
              f"alpha={params['alpha']} kmax={params['kmax']} hfa={params['hfa']}")

    rows = [{"season": y, **{k: v for k, v in schedule[y].items() if k != "train_log_loss"}}
            for y in sorted(schedule)]
    return pd.DataFrame(rows)


def simulate_with_schedule(games: list[dict], schedule_df: pd.DataFrame) -> list[dict]:
    """One continuous EloEngine, params swapped at each season boundary --
    exactly the change rebuild.py would need to make this live."""
    sched = schedule_df.set_index("season")[["alpha", "kmax", "hfa"]].to_dict("index")
    weeks = games_to_weeks(games)

    eng = engine.EloEngine(engine.default_params())
    all_rows = []
    current_season = None
    for wk_games in weeks:
        season = wk_games[0]["season"]
        if season != current_season:
            p = sched[season]
            new_params = engine.default_params()
            new_params["alpha"] = p["alpha"]
            new_params["kmax"] = p["kmax"]
            new_params["hfa"] = p["hfa"]
            eng.params = new_params
            current_season = season
        for row_home, row_away in eng.process_week(wk_games):
            all_rows.append(row_home)
            all_rows.append(row_away)
    return all_rows


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "nfl_elo.db"
    games = load_games_as_dicts(db_path)
    print(f"Loaded {len(games):,} games\n")

    era_stability_check(games, n_eras=3)

    schedule_df = build_schedule(games)
    schedule_df.to_csv("nfl_param_schedule_engine.csv", index=False)
    print(f"\nSaved -> nfl_param_schedule_engine.csv\n")

    print("=== Reconstructing with the honest schedule (real engine) ===")
    honest_rows = simulate_with_schedule(games, schedule_df)
    honest_ll = log_loss_of(honest_rows)
    home_rows = [r for r in honest_rows if r["home_away"] == "H"]
    honest_acc = sum(r["accuracy"] for r in home_rows) / len(home_rows)
    honest_brier = sum(r["brier"] for r in home_rows) / len(home_rows)
    print(f"Honest schedule: n={len(home_rows)}  accuracy={honest_acc*100:.2f}%  "
          f"brier={honest_brier:.4f}  log_loss={honest_ll:.4f}")

    baseline_rows = run_engine(games_to_weeks(games), 0.3, 46.0, 72.0)
    baseline_home = [r for r in baseline_rows if r["home_away"] == "H"]
    baseline_acc = sum(r["accuracy"] for r in baseline_home) / len(baseline_home)
    baseline_brier = sum(r["brier"] for r in baseline_home) / len(baseline_home)
    print(f"Current deployed (alpha=0.3 kmax=46 hfa=72): accuracy={baseline_acc*100:.2f}%  "
          f"brier={baseline_brier:.4f}  log_loss={log_loss_of(baseline_rows):.4f}")

    pd.DataFrame(home_rows).to_csv("nfl_ratings_reconstructed_engine.csv", index=False)
    print("\nSaved -> nfl_ratings_reconstructed_engine.csv")

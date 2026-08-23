"""
cfb_tune_engine.py

Forked from NFL_Elo's nfl_tune_engine.py. Same approach: imports
engine.py directly and drives the REAL EloEngine/process_week - the
exact code path production uses - rather than reimplementing the Elo
formula in a second place. Only alpha/kmax/hfa are tuned (same three
headline knobs as the NFL version); everything else (k_floor,
rest_minor/major, div/conf multipliers, playoff round multipliers)
stays at engine.py's baseline.

USE THIS ONLY ONCE REAL GAME DATA IS LOADED. The starting search
ranges below are copied from the NFL version as a reasonable place to
begin, NOT validated for CFB - CFB's score variance is much wider than
the NFL's (60-3 games are common), so don't be surprised if the
optimal alpha/kmax/hfa land somewhere very different from NFL's tuned
values once there's enough CFB history in the database to tune
against.

Usage:
    python3 cfb_tune_engine.py cfb_elo.db
"""
import sys
import sqlite3
from collections import defaultdict

import pandas as pd

import engine


def load_games_as_dicts(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT date, season, type, round, home_team, away_team, "
        "home_code, away_code, home_pts, away_pts, ot, neutral "
        "FROM games ORDER BY date, game_id", conn
    )
    conn.close()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.to_dict("records")


def games_to_weeks(games: list[dict]) -> list[list[dict]]:
    """Group games into (season, week) batches, in chronological order,
    exactly like rebuild.py must already be doing to call process_week.
    Note: unlike rebuild.py, this does NOT annotate home_conf/away_conf
    (see rebuild.py's `_annotate_conferences`) - tuning only touches
    alpha/kmax/hfa, none of which depend on conf/div classification,
    so every game here scores as "not a conference/division game."
    That's fine for tuning those three params, but don't reuse this
    function's output for anything that needs accurate conf_game_mult/
    div_game_mult behavior."""
    by_season = defaultdict(list)
    for g in games:
        by_season[g["season"]].append(g)

    weeks = []
    for season in sorted(by_season):
        season_games = sorted(by_season[season], key=lambda g: g["date"])
        season_start = season_games[0]["date"]
        by_week = defaultdict(list)
        for g in season_games:
            wk = engine.week_from_date(g["date"], season_start)
            by_week[wk].append(g)
        for wk in sorted(by_week):
            weeks.append(by_week[wk])
    return weeks


def log_loss_of(rows: list[dict]) -> float:
    home_rows = [r for r in rows if r["home_away"] == "H"]
    return sum(r["test"] for r in home_rows) / len(home_rows)


def run_engine(weeks: list[list[dict]], alpha: float, kmax: float, hfa: float,
               resets: set | None = None) -> list[dict]:
    params = engine.default_params()
    params["alpha"] = alpha
    params["kmax"] = kmax
    params["hfa"] = hfa
    eng = engine.EloEngine(params, resets=resets)
    all_rows = []
    for wk_games in weeks:
        for row_home, row_away in eng.process_week(wk_games):
            all_rows.append(row_home)
            all_rows.append(row_away)
    return all_rows


def coordinate_ascent_engine(weeks: list[list[dict]], rounds: int = 3,
                              start=(0.3, 46.0, 55.0)) -> dict:
    alpha, kmax, hfa = start
    # UNTUNED STARTING RANGES - copied from NFL_Elo's search grid.
    # CFB's much higher score variance may mean the true optimum for
    # kmax/hfa in particular sits well outside these bounds; widen them
    # if the coordinate ascent keeps landing on a range edge.
    alpha_range = [round(0.1 * i, 2) for i in range(1, 10)]
    kmax_range = list(range(20, 71, 2))
    hfa_range = list(range(0, 121, 4))

    def score(a, k, h):
        rows = run_engine(weeks, a, k, h)
        return log_loss_of(rows)

    best_ll = score(alpha, kmax, hfa)

    for _ in range(rounds):
        improved = False

        best_a, best_a_ll = alpha, best_ll
        for a in alpha_range:
            ll = score(a, kmax, hfa)
            if ll < best_a_ll:
                best_a, best_a_ll = a, ll
        if best_a != alpha:
            alpha, best_ll, improved = best_a, best_a_ll, True

        best_k, best_k_ll = kmax, best_ll
        for k in kmax_range:
            ll = score(alpha, k, hfa)
            if ll < best_k_ll:
                best_k, best_k_ll = k, ll
        if best_k != kmax:
            kmax, best_ll, improved = best_k, best_k_ll, True

        best_h, best_h_ll = hfa, best_ll
        for h in hfa_range:
            ll = score(alpha, kmax, h)
            if ll < best_h_ll:
                best_h, best_h_ll = h, ll
        if best_h != hfa:
            hfa, best_ll, improved = best_h, best_h_ll, True

        if not improved:
            break

    return {"alpha": alpha, "kmax": kmax, "hfa": hfa, "train_log_loss": best_ll}


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "cfb_elo.db"
    games = load_games_as_dicts(db_path)
    weeks = games_to_weeks(games)
    print(f"Loaded {len(games):,} games across {len(weeks)} team-weeks\n")

    tuned = coordinate_ascent_engine(weeks, rounds=3)
    print(f"Engine-faithful full-history tune: alpha={tuned['alpha']} "
          f"kmax={tuned['kmax']} hfa={tuned['hfa']}  log_loss={tuned['train_log_loss']:.4f}")

    baseline_rows = run_engine(weeks, 0.3, 46.0, 72.0)
    print(f"NFL_Elo's baseline, run against CFB data for comparison only "
          f"(alpha=0.3 kmax=46 hfa=72): log_loss={log_loss_of(baseline_rows):.4f}")


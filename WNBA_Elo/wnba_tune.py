#!/usr/bin/env python3
"""
wnba_tune.py

Coordinate-ascent tuning of alpha / Kmax / HCA for the WNBA version of the
ContinElo engine. Mirrors the NBA process: lock in parameters against the
seasons you currently have, then treat future seasons (2012-2026, once
added) as the true out-of-sample test -- there's no held-out slice carved
out of this file.

Everything else (KMIN, K_DECAY, MOV-mult formula, PO_MULT table, rest-day
adjustment) is held at the NBA-tuned constants, matching the original
ContinElo methodology of only tuning alpha, Kmax, and HCA.

USAGE
-----
    python wnba_tune.py wnba_elo.db

WHAT IT DOES
------------
1. Loads every game in the `games` table, sorts chronologically.
2. Runs coordinate ascent across the full dataset, minimizing log-loss,
   sweeping alpha -> Kmax -> HCA in rounds until no parameter improves.
3. Prints the locked-in parameters and their in-sample fit metrics.

The real out-of-sample check happens later, once 2012-2026 data is added --
rerun evaluate() against that data using the params printed here, unchanged.
"""

import argparse
import math
import sqlite3
from dataclasses import dataclass

import pandas as pd

# ---------------------------------------------------------------------------
# Fixed constants (not tuned -- matches ContinElo methodology)
# ---------------------------------------------------------------------------
BASE = 1500
KMIN = 6
K_DECAY = 0.15
REST_SCALE = 8
REST_CAP = 16
GAMES_PLAYED_CAP = 82  # never binds for WNBA (short season), kept for parity

PO_MULT = {
    "RS": 1.00, "INS": 1.02,
    0.5: 1.05, 1: 1.10, 2: 1.20, 3: 1.35, 4: 1.50,
}

VARIANT = "continelo"  # "continelo" (Echo, carry-forward) or "elo" (Pulse, reset)


# ---------------------------------------------------------------------------
# Core formulas (parametrized by alpha / kmax / hca)
# ---------------------------------------------------------------------------

def preseason_rating(prev_end: float, alpha: float, variant: str) -> float:
    if variant == "elo":
        return float(BASE)
    return alpha * prev_end + (1 - alpha) * BASE


def rest_adj(rest_diff: int) -> float:
    return max(-REST_CAP, min(REST_CAP, rest_diff * REST_SCALE))


def k_factor(games_played: int, kmax: float) -> float:
    gp = min(games_played, GAMES_PLAYED_CAP)
    return max(KMIN, kmax - K_DECAY * gp)


def po_mult(round_val, game_type: str) -> float:
    if game_type != "P":
        return PO_MULT["RS"]
    try:
        key = float(round_val) if round_val not in ("RS", "INS", None) else round_val
    except (TypeError, ValueError):
        key = round_val
    return PO_MULT.get(key, 1.00)


def expected_win_pct(pre, opp_pre, ra, ora, hca):
    adj_team = pre + ra + hca
    adj_opp = opp_pre + ora
    return 1 / (1 + 10 ** ((adj_opp - adj_team) / 400))


def mov_mult(mov_abs, rating_diff_abs, ot):
    mult = ((mov_abs + 5) ** 0.6) / (12 + 0.01 * rating_diff_abs)
    if ot:
        mult *= 0.9
    return mult


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_games(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT date, season, type, round, home_team, away_team, "
        "home_pts, away_pts, ot FROM games ORDER BY date, game_id", conn
    )
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Simulator: run the full multi-season engine for one param set,
# return per-game expected_win_pct (home team) and result (1 if home won).
# ---------------------------------------------------------------------------

def simulate(games: pd.DataFrame, alpha: float, kmax: float, hca: float) -> pd.DataFrame:
    games = games.sort_values(["date"], kind="stable").reset_index(drop=True)

    ratings: dict[str, float] = {}          # team -> current rating
    last_season: dict[str, int] = {}        # team -> last season seen
    last_game_date: dict[str, pd.Timestamp] = {}
    games_played: dict[str, int] = {}       # team -> games played THIS season
    season_start: dict[int, pd.Timestamp] = (
        games.groupby("season")["date"].min().to_dict()
    )

    out_ewp = []
    out_result = []

    for row in games.itertuples(index=False):
        season = row.season
        home, away = row.home_team, row.away_team

        for team in (home, away):
            if last_season.get(team) is None:
                # brand new team, no history -> base rating
                ratings[team] = BASE
                games_played[team] = 0
            elif last_season[team] != season:
                # season rollover -> apply carry-forward formula
                ratings[team] = preseason_rating(ratings[team], alpha, VARIANT)
                games_played[team] = 0
            last_season[team] = season

        pre_home = ratings[home]
        pre_away = ratings[away]

        s_start = season_start[season]
        home_days_off = (row.date - last_game_date.get(home, s_start)).days
        away_days_off = (row.date - last_game_date.get(away, s_start)).days
        if home not in last_game_date:
            home_days_off = (row.date - s_start).days
        else:
            home_days_off -= 1
        if away not in last_game_date:
            away_days_off = (row.date - s_start).days
        else:
            away_days_off -= 1

        rest_diff_home = home_days_off - away_days_off
        rest_diff_away = away_days_off - home_days_off
        ra_home = rest_adj(rest_diff_home)
        ra_away = rest_adj(rest_diff_away)

        ewp_home = expected_win_pct(pre_home, pre_away, ra_home, ra_away, hca)
        result_home = 1.0 if row.home_pts > row.away_pts else 0.0

        mov_abs = abs(row.home_pts - row.away_pts)
        rating_diff_abs = abs(pre_home - pre_away)
        mm = mov_mult(mov_abs, rating_diff_abs, row.ot)

        gp_home = games_played[home] + 1
        gp_away = games_played[away] + 1
        games_played[home] = gp_home
        games_played[away] = gp_away

        pm = po_mult(row.round, row.type)
        k_home = k_factor(gp_home, kmax)
        k_away = k_factor(gp_away, kmax)
        keff_home = k_home * pm
        keff_away = k_away * pm

        rc_home = keff_home * mm * (result_home - ewp_home)
        rc_away = keff_away * mm * ((1 - result_home) - (1 - ewp_home))

        ratings[home] = pre_home + rc_home
        ratings[away] = pre_away + rc_away
        last_game_date[home] = row.date
        last_game_date[away] = row.date

        out_ewp.append(ewp_home)
        out_result.append(result_home)

    result_df = games.copy()
    result_df["ewp_home"] = out_ewp
    result_df["result_home"] = out_result
    return result_df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def log_loss(p, y):
    p = min(max(p, 1e-9), 1 - 1e-9)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def evaluate(sim_df: pd.DataFrame) -> dict:
    n = len(sim_df)
    acc = (
        ((sim_df["ewp_home"] >= 0.5) & (sim_df["result_home"] == 1))
        | ((sim_df["ewp_home"] < 0.5) & (sim_df["result_home"] == 0))
    ).mean()
    brier = ((sim_df["ewp_home"] - sim_df["result_home"]) ** 2).mean()
    ll = sum(log_loss(p, y) for p, y in zip(sim_df["ewp_home"], sim_df["result_home"])) / n
    return {"n": n, "accuracy": acc, "brier": brier, "log_loss": ll}


# ---------------------------------------------------------------------------
# Coordinate ascent tuning (minimizes log-loss on the given games subset)
# ---------------------------------------------------------------------------

def coordinate_ascent(train_games: pd.DataFrame, rounds: int = 3) -> dict:
    alpha, kmax, hca = 0.6, 58.0, 84.0  # start from NBA-tuned values

    alpha_range = [round(0.1 * i, 2) for i in range(1, 10)]        # 0.1 .. 0.9
    kmax_range = list(range(20, 101, 4))                            # 20 .. 100
    hca_range = list(range(0, 141, 4))                               # 0 .. 140

    def score(a, k, h):
        sim = simulate(train_games, a, k, h)
        return evaluate(sim)["log_loss"]

    best_ll = score(alpha, kmax, hca)
    print(f"  starting point: alpha={alpha} kmax={kmax} hca={hca}  log_loss={best_ll:.4f}")

    for rnd in range(1, rounds + 1):
        improved = False

        best_a, best_a_ll = alpha, best_ll
        for a in alpha_range:
            ll = score(a, kmax, hca)
            if ll < best_a_ll:
                best_a, best_a_ll = a, ll
        if best_a != alpha:
            alpha, best_ll, improved = best_a, best_a_ll, True

        best_k, best_k_ll = kmax, best_ll
        for k in kmax_range:
            ll = score(alpha, k, hca)
            if ll < best_k_ll:
                best_k, best_k_ll = k, ll
        if best_k != kmax:
            kmax, best_ll, improved = best_k, best_k_ll, True

        best_h, best_h_ll = hca, best_ll
        for h in hca_range:
            ll = score(alpha, kmax, h)
            if ll < best_h_ll:
                best_h, best_h_ll = h, ll
        if best_h != hca:
            hca, best_ll, improved = best_h, best_h_ll, True

        print(f"  round {rnd}: alpha={alpha} kmax={kmax} hca={hca}  log_loss={best_ll:.4f}")
        if not improved:
            print("  converged (no parameter improved this round)")
            break

    return {"alpha": alpha, "kmax": kmax, "hca": hca, "train_log_loss": best_ll}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path")
    ap.add_argument("--rounds", type=int, default=3,
                     help="max coordinate-ascent rounds (default 3)")
    args = ap.parse_args()

    games = load_games(args.db_path)
    seasons = sorted(games["season"].unique())
    n_seasons = len(seasons)
    print(f"Loaded {len(games):,} games across {n_seasons} seasons "
          f"({seasons[0]}-{seasons[-1]})\n")

    print("=== Coordinate ascent across all loaded seasons (minimizing log-loss) ===")
    tuned = coordinate_ascent(games, rounds=args.rounds)
    print()

    print("=== Locked-in parameters ===")
    print(f"  alpha={tuned['alpha']}  kmax={tuned['kmax']}  hca={tuned['hca']}")
    print()

    print("=== In-sample fit with locked-in parameters ===")
    sim = simulate(games, tuned["alpha"], tuned["kmax"], tuned["hca"])
    metrics = evaluate(sim)
    print(f"  n={metrics['n']:,}  accuracy={metrics['accuracy']*100:.2f}%  "
          f"brier={metrics['brier']:.4f}  log_loss={metrics['log_loss']:.4f}")
    print()

    print("=== For reference: NBA constants (0.6 / 58 / 84) on the same games ===")
    nba_sim = simulate(games, 0.6, 58.0, 84.0)
    nba_metrics = evaluate(nba_sim)
    print(f"  n={nba_metrics['n']:,}  accuracy={nba_metrics['accuracy']*100:.2f}%  "
          f"brier={nba_metrics['brier']:.4f}  log_loss={nba_metrics['log_loss']:.4f}")
    print()
    print("These are in-sample numbers, not a validation result -- they just show")
    print("how much the tuned params moved fit versus reusing the NBA constants")
    print("as-is. The real test comes once 2012-2026 games are added: rerun this")
    print("script's evaluate()/simulate() against that new data using the alpha,")
    print("kmax, hca values locked in above, unchanged, to see if they hold up.")


if __name__ == "__main__":
    main()

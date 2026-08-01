#!/usr/bin/env python3
"""
nfl_tune.py

Coordinate-ascent tuning of alpha / K / HFA for the NFL version of the
ContinElo engine. Mirrors the NBA/WNBA process (wnba_tune.py): lock in
parameters against the seasons you currently have, then treat future
seasons you add as the true out-of-sample test -- there's no held-out
slice carved out of this file.

Everything else (the MOV-multiplier formula, the division/conference K
boosts, the playoff-round PO_MULT table) is held at the values baked into
the original Continelo workbook -- matching the NBA/WNBA approach of only
tuning the three headline parameters and leaving the rest of the formula
alone.

Structural note vs. the NBA/WNBA version: Continelo's NFL formula has no
rest-day adjustment and no games-played K-decay -- K is just a flat
constant per game (boosted by the div/conf/playoff multipliers, but not by
how far into the season a team is). So there's nothing to hold fixed there;
those dimensions simply don't exist in this model.

USAGE
-----
    python nfl_tune.py nfl_elo.db

WHAT IT DOES
------------
1. Loads every game in the `games` table (built by build_nfl_db.py), sorted
   chronologically.
2. Runs coordinate ascent across the full dataset, minimizing log-loss,
   sweeping alpha -> K -> HFA in rounds until no parameter improves.
3. Prints the locked-in parameters and their in-sample fit metrics,
   compared against the workbook's original hand-set values (alpha=0.3,
   K=20, HFA=55).
"""

import argparse
import math
import sqlite3

import pandas as pd

# ---------------------------------------------------------------------------
# Fixed constants (not tuned -- matches the validated Continelo workbook)
# ---------------------------------------------------------------------------
BASE = 1500
DIV_GAME_MULT = 1.1
CONF_GAME_MULT = 1.02

PO_MULT = {None: 1.00, 1.0: 1.10, 2.0: 1.20, 3.0: 1.35, 4.0: 1.50}  # WC/DV/CC/SB

# team -> (conference, division), pre- and post-2002 realignment
CONF_DIV_PRE2002 = {
    "ARI": ("NFC", "East"), "ATL": ("NFC", "West"), "BAL": ("AFC", "Central"),
    "BUF": ("AFC", "East"), "CAR": ("NFC", "West"), "CHI": ("NFC", "Central"),
    "CIN": ("AFC", "Central"), "CLE": ("AFC", "Central"), "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"), "DET": ("NFC", "Central"), "GB": ("NFC", "Central"),
    "IND": ("AFC", "East"), "JAX": ("AFC", "Central"), "KC": ("AFC", "West"),
    "MIA": ("AFC", "East"), "MIN": ("NFC", "Central"), "NE": ("AFC", "East"),
    "NO": ("NFC", "West"), "NYG": ("NFC", "East"), "NYJ": ("AFC", "East"),
    "OAK": ("AFC", "West"), "PHI": ("NFC", "East"), "PIT": ("AFC", "Central"),
    "SD": ("AFC", "West"), "SEA": ("AFC", "West"), "SF": ("NFC", "West"),
    "STL": ("NFC", "West"), "TB": ("NFC", "Central"), "TEN": ("AFC", "Central"),
    "WAS": ("NFC", "East"),
}
CONF_DIV_2002_PLUS = {
    "ARI": ("NFC", "West"), "ATL": ("NFC", "South"), "BAL": ("AFC", "North"),
    "BUF": ("AFC", "East"), "CAR": ("NFC", "South"), "CHI": ("NFC", "North"),
    "CIN": ("AFC", "North"), "CLE": ("AFC", "North"), "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"), "DET": ("NFC", "North"), "GB": ("NFC", "North"),
    "HOU": ("AFC", "South"), "IND": ("AFC", "South"), "JAX": ("AFC", "South"),
    "KC": ("AFC", "West"), "MIA": ("AFC", "East"), "MIN": ("NFC", "North"),
    "NE": ("AFC", "East"), "NO": ("NFC", "South"), "NYG": ("NFC", "East"),
    "NYJ": ("AFC", "East"), "OAK": ("AFC", "West"), "PHI": ("NFC", "East"),
    "PIT": ("AFC", "North"), "SD": ("AFC", "West"), "SEA": ("NFC", "West"),
    "SF": ("NFC", "West"), "STL": ("NFC", "West"), "TB": ("NFC", "South"),
    "TEN": ("AFC", "South"), "WAS": ("NFC", "East"),
}


def conf_div(team: str, season: int):
    table = CONF_DIV_PRE2002 if season <= 2001 else CONF_DIV_2002_PLUS
    return table.get(team, (None, None))


# ---------------------------------------------------------------------------
# Core formulas (parametrized by alpha / k / hfa; everything else fixed)
# ---------------------------------------------------------------------------

def preseason_rating(prev_end: float, alpha: float) -> float:
    return alpha * prev_end + (1 - alpha) * BASE


def expected_win_pct(pre_home, pre_away, hfa, neutral):
    adj_home = pre_home + (0 if neutral else hfa)
    adj_away = pre_away
    return 1 / (1 + 10 ** ((adj_away - adj_home) / 400))


def mov_mult(mov_abs, rating_diff_abs, ot):
    mult = ((mov_abs + 3) ** 0.8) / (7.5 + 0.006 * rating_diff_abs)
    if ot:
        mult *= 0.7
    return mult


def po_mult(round_val, game_type: str) -> float:
    if game_type != "P":
        return 1.0
    return PO_MULT.get(round_val, 1.0)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_games(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT date, season, type, round, home_team, away_team, "
        "home_pts, away_pts, ot, neutral FROM games ORDER BY date, game_id", conn
    )
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Simulator: run the full multi-season engine for one param set,
# return per-game expected_win_pct (home team) and result (1/0.5/0 for
# home win/tie/loss).
# ---------------------------------------------------------------------------

def simulate(games: pd.DataFrame, alpha: float, k: float, hfa: float) -> pd.DataFrame:
    games = games.sort_values(["date"], kind="stable").reset_index(drop=True)

    ratings: dict[str, float] = {}
    last_season: dict[str, int] = {}

    out_ewp = []
    out_result = []

    for row in games.itertuples(index=False):
        season = row.season
        home, away = row.home_team, row.away_team

        for team in (home, away):
            if last_season.get(team) is None:
                ratings[team] = BASE
            elif last_season[team] != season:
                ratings[team] = preseason_rating(ratings[team], alpha)
            last_season[team] = season

        pre_home = ratings[home]
        pre_away = ratings[away]

        home_conf, home_div = conf_div(home, season)
        away_conf, away_div = conf_div(away, season)
        conf_g = home_conf is not None and home_conf == away_conf
        div_g = conf_g and home_div == away_div

        pm = po_mult(row.round, row.type)
        keff = k * (DIV_GAME_MULT if div_g else 1) * (CONF_GAME_MULT if conf_g else 1) * pm

        neutral = bool(row.neutral)
        ewp_home = expected_win_pct(pre_home, pre_away, hfa, neutral)

        if row.home_pts > row.away_pts:
            result_home = 1.0
        elif row.home_pts < row.away_pts:
            result_home = 0.0
        else:
            result_home = 0.5

        mov_abs = abs(row.home_pts - row.away_pts)
        rating_diff_abs = abs(pre_home - pre_away)
        mm = mov_mult(mov_abs, rating_diff_abs, row.ot)

        rc_home = keff * mm * (result_home - ewp_home)
        rc_away = keff * mm * ((1 - result_home) - (1 - ewp_home))

        ratings[home] = pre_home + rc_home
        ratings[away] = pre_away + rc_away

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
    alpha, k, hfa = 0.3, 46.0, 55.0  # start from the workbook's own values

    alpha_range = [round(0.1 * i, 2) for i in range(1, 10)]  # 0.1 .. 0.9
    k_range = list(range(2, 61, 2))                           # 2 .. 60
    hfa_range = list(range(0, 121, 4))                        # 0 .. 120

    def score(a, kk, h):
        sim = simulate(train_games, a, kk, h)
        return evaluate(sim)["log_loss"]

    best_ll = score(alpha, k, hfa)
    print(f"  starting point: alpha={alpha} k={k} hfa={hfa}  log_loss={best_ll:.4f}")

    for rnd in range(1, rounds + 1):
        improved = False

        best_a, best_a_ll = alpha, best_ll
        for a in alpha_range:
            ll = score(a, k, hfa)
            if ll < best_a_ll:
                best_a, best_a_ll = a, ll
        if best_a != alpha:
            alpha, best_ll, improved = best_a, best_a_ll, True

        best_k, best_k_ll = k, best_ll
        for kk in k_range:
            ll = score(alpha, kk, hfa)
            if ll < best_k_ll:
                best_k, best_k_ll = kk, ll
        if best_k != k:
            k, best_ll, improved = best_k, best_k_ll, True

        best_h, best_h_ll = hfa, best_ll
        for h in hfa_range:
            ll = score(alpha, k, h)
            if ll < best_h_ll:
                best_h, best_h_ll = h, ll
        if best_h != hfa:
            hfa, best_ll, improved = best_h, best_h_ll, True

        print(f"  round {rnd}: alpha={alpha} k={k} hfa={hfa}  log_loss={best_ll:.4f}")
        if not improved:
            print("  converged (no parameter improved this round)")
            break

    return {"alpha": alpha, "k": k, "hfa": hfa, "train_log_loss": best_ll}


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

    if len(games) < 2000:
        print(f"NOTE: only {len(games):,} games loaded. Coordinate ascent on this few "
              "games can easily overfit noise -- treat any parameter move as a weak "
              "signal until you've rerun this against the full multi-season database.\n")

    print("=== Coordinate ascent across all loaded seasons (minimizing log-loss) ===")
    tuned = coordinate_ascent(games, rounds=args.rounds)
    print()

    print("=== Locked-in parameters ===")
    print(f"  alpha={tuned['alpha']}  k={tuned['k']}  hfa={tuned['hfa']}")
    print()

    print("=== In-sample fit with locked-in parameters ===")
    sim = simulate(games, tuned["alpha"], tuned["k"], tuned["hfa"])
    metrics = evaluate(sim)
    print(f"  n={metrics['n']:,}  accuracy={metrics['accuracy']*100:.2f}%  "
          f"brier={metrics['brier']:.4f}  log_loss={metrics['log_loss']:.4f}")
    print()

    print("=== For reference: the workbook's original values (alpha=0.3, k=20, hfa=55) ===")
    orig_sim = simulate(games, 0.3, 20.0, 55.0)
    orig_metrics = evaluate(orig_sim)
    print(f"  n={orig_metrics['n']:,}  accuracy={orig_metrics['accuracy']*100:.2f}%  "
          f"brier={orig_metrics['brier']:.4f}  log_loss={orig_metrics['log_loss']:.4f}")
    print()
    print("These are in-sample numbers, not a validation result -- they just show how")
    print("much the tuned params move fit versus the workbook's hand-set values on the")
    print("games currently loaded. Rerun this once you've built nfl_elo.db from all 10+")
    print("seasons for a much more meaningful (though still in-sample) read.")


if __name__ == "__main__":
    main()

"""
Week-by-week stabilization check: how many weeks into a real season does
simulate_season.py's Monte Carlo projection become "close" to what
actually happened?

This is a BACKTEST - it only makes sense for a season that's already
fully played out and sitting in `games`. For each checkpoint (see
below), it:

  1. Builds a scratch Elo engine using ONLY real games on or before that
     checkpoint date - exactly what the model would have known at that
     point in the season, nothing from the future.
  2. Projects the rest of the season the same way simulate_season.py
     does: remaining games (drawn from the ACTUAL schedule, since we
     know it in hindsight) are simulated many times, winners drawn from
     the model's own expected-win probability, ratings updating game by
     game within each simulated trial.
  3. Compares the averaged projected final win total for each team
     against what ACTUALLY happened that season.
  4. Records mean absolute error (in wins) and Spearman rank
     correlation between projected and actual final standings.

CHECKPOINT SCHEDULE: anchored to the season's actual final day, working
backward in 7-day steps. Every checkpoint after the first lands exactly
7 days apart, and the LAST checkpoint IS the season's actual final day
(a full week). Only the very first checkpoint is a partial week -
whatever's left over between the season opener and the first 7-day mark
counting back from the end.

Usage:
    python3 stabilization_check.py --season 2025
    python3 stabilization_check.py --season 2025 --variant pulse --trials 500

Writes reports/stabilization_<season>_<variant>.csv and .txt.
"""
import argparse
import csv
import os
import random
from datetime import date, timedelta

import db
import engine
from rebuild import variant_params
from simulate_season import historical_mov_pool, simulate_one_season

DB_PATH = "nba_elo.db"
OUT_DIR = "reports"
LEAGUE_LABEL = "NBA"


def season_game_dates(conn, season):
    rows = conn.execute(
        "SELECT DISTINCT date FROM games WHERE season = ? AND type = 'R' ORDER BY date",
        (season,),
    ).fetchall()
    return [date.fromisoformat(r[0]) for r in rows]


def checkpoint_dates(all_dates):
    """Anchored to the season's last game date, stepping back 7 days at
    a time until we'd go before the season opener. Week 1 (the earliest
    checkpoint) is whatever's left over; every other week is a full 7
    days, and the final checkpoint always lands exactly on the season's
    last day."""
    start, end = all_dates[0], all_dates[-1]
    cps = []
    d = end
    while d >= start:
        cps.append(d)
        d -= timedelta(days=7)
    cps.reverse()
    return cps


def record_as_of(games, cutoff=None):
    """team -> (wins, losses) from a list of already-played R games,
    optionally filtered to date <= cutoff. cutoff=None means "use every
    game passed in" (used to get the real final season record)."""
    record = {}
    for g in games:
        if cutoff is not None and g["date"] > cutoff:
            continue
        home, away = g["home_team"], g["away_team"]
        record.setdefault(home, [0, 0])
        record.setdefault(away, [0, 0])
        if g["home_pts"] > g["away_pts"]:
            record[home][0] += 1
            record[away][1] += 1
        elif g["away_pts"] > g["home_pts"]:
            record[away][0] += 1
            record[home][1] += 1
    return {t: tuple(v) for t, v in record.items()}


def build_engine_as_of(conn, variant, cutoff):
    """Same replay simulate_season.py's build_current_engine does, but
    only fed games up through `cutoff` - a scratch engine, nothing
    written back to the database. Deliberately reuses ALL history
    (every prior season too), since that's what current ratings
    actually depend on - only games AFTER cutoff are excluded."""
    games = [g for g in db.load_games(conn) if g["date"] <= cutoff]
    resets = db.load_resets(conn)
    params = variant_params(conn, variant)
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        eng.process_game(g)
    return eng


def spearman(actual, projected, teams):
    """Rank correlation between two win-total dicts (more wins = better
    rank), same tie-break convention as real_standings/summarize."""
    n = len(teams)
    if n < 2:
        return float("nan")

    def ranks(values):
        order = sorted(teams, key=lambda t: -values[t])
        return {t: i + 1 for i, t in enumerate(order)}

    ra, rp = ranks(actual), ranks(projected)
    d2 = sum((ra[t] - rp[t]) ** 2 for t in teams)
    return 1 - (6 * d2) / (n * (n**2 - 1))


def run_checkpoint(base_engine, season_teams, played_so_far, remaining,
                    actual_final, mov_pool, trials, rng):
    current = record_as_of(played_so_far)

    if not remaining:
        # Season's already over as of this checkpoint - the "projection"
        # is trivially the real final record.
        return dict(games_played=len(played_so_far), games_remaining=0, mae=0.0, rho=1.0)

    results = []
    for _ in range(trials):
        trial = simulate_one_season(base_engine, remaining, mov_pool, rng)
        trial_final = {}
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            add_w = trial["wl"].get(team, {}).get("w", 0)
            trial_final[team] = base_w + add_w
        results.append(trial_final)

    projected_avg = {team: sum(r[team] for r in results) / trials for team in season_teams}

    common = sorted(t for t in season_teams if t in actual_final)
    actual_wins = {t: actual_final[t][0] for t in common}
    mae = sum(abs(projected_avg[t] - actual_wins[t]) for t in common) / len(common)
    rho = spearman(actual_wins, projected_avg, common)

    return dict(games_played=len(played_so_far), games_remaining=len(remaining), mae=mae, rho=rho)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--variant", default="echo", choices=["echo", "pulse"])
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--seed", type=int, default=None, help="for reproducible results")
    args = parser.parse_args()

    conn = db.connect(DB_PATH)
    all_dates = season_game_dates(conn, args.season)
    if not all_dates:
        print(f"No regular-season games found for season {args.season}.")
        return

    all_games = [g for g in db.load_games(conn) if g["season"] == args.season and g["type"] == "R"]
    season_teams = {g["home_team"] for g in all_games} | {g["away_team"] for g in all_games}
    actual_final = record_as_of(all_games)  # no cutoff = the real final season record
    mov_pool = historical_mov_pool(conn)

    cps = checkpoint_dates(all_dates)
    rng = random.Random(args.seed)

    rows = []
    for i, cp in enumerate(cps, start=1):
        played_so_far = [g for g in all_games if g["date"] <= cp]
        remaining = [g for g in all_games if g["date"] > cp]
        base_engine = build_engine_as_of(conn, args.variant, cp)

        result = run_checkpoint(base_engine, season_teams, played_so_far, remaining,
                                 actual_final, mov_pool, args.trials, rng)
        rows.append(dict(week=i, checkpoint_date=cp.isoformat(), **result))
        print(f"  Week {i:>2} ({cp.isoformat()}): "
              f"{result['games_played']:>4} played, {result['games_remaining']:>4} remaining  "
              f"-> MAE {result['mae']:.2f} wins, rank corr {result['rho']:.3f}")

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = "" if args.variant == "echo" else f"_{args.variant}"
    csv_path = os.path.join(OUT_DIR, f"stabilization_{args.season}{suffix}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["week", "checkpoint_date", "games_played",
                                           "games_remaining", "mae", "rho"])
        w.writeheader()
        for row in rows:
            w.writerow(row)

    txt_path = os.path.join(OUT_DIR, f"stabilization_{args.season}{suffix}.txt")
    with open(txt_path, "w") as f:
        label = "Echo" if args.variant == "echo" else "Pulse"
        f.write(f"{LEAGUE_LABEL} {label} - Weekly Stabilization Check ({args.season})\n")
        f.write("=" * 62 + "\n")
        f.write(f"{args.trials} trials per checkpoint. MAE = mean absolute error in\n")
        f.write("projected final wins vs. what actually happened. Rank corr = Spearman\n")
        f.write("correlation between projected and actual final standings (1.0 = perfect).\n\n")
        f.write(f"{'Week':<6}{'Date':<12}{'Played':>8}{'Remaining':>11}{'MAE':>8}{'RankCorr':>10}\n")
        f.write("-" * 62 + "\n")
        for row in rows:
            f.write(f"{row['week']:<6}{row['checkpoint_date']:<12}{row['games_played']:>8}"
                     f"{row['games_remaining']:>11}{row['mae']:>8.2f}{row['rho']:>10.3f}\n")

    print(f"\nWrote {csv_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()

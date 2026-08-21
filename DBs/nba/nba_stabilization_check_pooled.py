"""
Multi-season pooled trust check: is the coverage/calibration picture
from a single season real, or was it just sampling noise?

A single season only gives you ~30 teams per checkpoint - with that few
samples, the standard error on a coverage percentage that's truly 80%
is around +/-7%, so one week reading "73%" or "87%" is statistically
indistinguishable from "correctly calibrated." This version runs the
SAME checkpoint logic as stabilization_check.py across MANY seasons and
pools every team-season together at each week index, so "week 5" means
"week 5 across every season combined" - e.g. 10 seasons x 30 teams =
300 samples instead of 30, which shrinks that noise a lot.

Same three simulation methods as before, same coin-flip baseline:

  DYNAMIC - simulate_season.py's actual method (full-strength rating
            drift within each trial).
  DAMPED  - same, but each simulated game's rating change is scaled by
            --damping before being applied (default 0.5).
  FROZEN  - win probabilities fixed at the start, no mid-trial rating
            updates at all.

WEEK ALIGNMENT: each season gets its own checkpoint schedule exactly
like the single-season script (anchored to that season's actual final
day, stepping back 7 days). Pooling happens by WEEK INDEX SINCE SEASON
START (week 1 = each season's first checkpoint, week 2 = second, etc.)
- not by calendar date - so "week 3" always means "3 checkpoints into
whichever season," which is the natural way to ask "how many weeks in
can we trust this." Shorter (lockout/COVID) seasons simply stop
contributing at their own final week, so late week indices are pooled
from fewer seasons - the report shows how many teams/seasons back each
row so you can see where the sample thins out.

Usage:
    python3 stabilization_check.py --seasons 2016-2025
    python3 stabilization_check.py --seasons 2016,2018,2019,2021-2025 --damping 0.6 --trials 300

Writes reports/stabilization_pooled_<seasons>_<variant>.csv and .txt.
"""
import argparse
import copy
import csv
import os
import random
from datetime import date, timedelta
from math import comb

import db
import engine
from rebuild import variant_params
from simulate_season import historical_mov_pool, simulate_one_season

DB_PATH = "nba_elo.db"
OUT_DIR = "reports"
LEAGUE_LABEL = "NBA"

_coinflip_cache = {}


def coinflip_band_width(n, p=0.5):
    if n <= 0:
        return 0
    if n in _coinflip_cache:
        return _coinflip_cache[n]
    pmf = [comb(n, k) * (p**k) * ((1 - p) ** (n - k)) for k in range(n + 1)]
    cum = 0.0
    p10 = p90 = n
    for k, mass in enumerate(pmf):
        cum += mass
        if cum >= 0.10 and p10 == n and k < n:
            p10 = k
        if cum >= 0.90:
            p90 = k
            break
    width = p90 - p10
    _coinflip_cache[n] = width
    return width


def parse_seasons(spec):
    """'2016-2025' -> range. '2016,2018,2020-2022' -> mixed list."""
    seasons = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            seasons.update(range(int(lo), int(hi) + 1))
        elif part:
            seasons.add(int(part))
    return sorted(seasons)


def season_game_dates(conn, season):
    rows = conn.execute(
        "SELECT DISTINCT date FROM games WHERE season = ? AND type = 'R' ORDER BY date",
        (season,),
    ).fetchall()
    return [date.fromisoformat(r[0]) for r in rows]


def checkpoint_dates(all_dates):
    start, end = all_dates[0], all_dates[-1]
    cps = []
    d = end
    while d >= start:
        cps.append(d)
        d -= timedelta(days=7)
    cps.reverse()
    return cps


def record_as_of(games, cutoff=None):
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
    """Uses ALL history up to cutoff, across every season in the DB -
    not just the season being tested - since that's what real ratings
    actually depend on."""
    games = [g for g in db.load_games(conn) if g["date"] <= cutoff]
    resets = db.load_resets(conn)
    params = variant_params(conn, variant)
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        eng.process_game(g)
    return eng


def bands_from_wins(per_team_wins):
    bands = {}
    for team, wins in per_team_wins.items():
        wins.sort()
        n = len(wins)
        bands[team] = dict(
            p10=wins[int(0.10 * n)],
            p50=wins[int(0.50 * n)],
            p90=wins[min(n - 1, int(0.90 * n))],
            avg=sum(wins) / n,
        )
    return bands


def simulate_one_season_damped(base_engine, remaining_games, mov_pool, rng, damping):
    eng = copy.deepcopy(base_engine)
    wl = {}
    for g in remaining_games:
        preview = eng.preview_matchup(
            home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
            season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
        )
        home_wins = rng.random() < preview["expected_win_home"]
        margin = rng.choice(mov_pool)
        home_pts, away_pts = (100 + margin, 100) if home_wins else (100, 100 + margin)
        synthetic_game = dict(
            date=g["date"], season=g["season"], type=g["type"], round=g["round"],
            home_team=g["home_team"], away_team=g["away_team"],
            home_pts=home_pts, away_pts=away_pts, ot=0, neutral=g["neutral"],
        )
        pre_home = eng.teams[g["home_team"]].rating if g["home_team"] in eng.teams else eng.params["base"]
        pre_away = eng.teams[g["away_team"]].rating if g["away_team"] in eng.teams else eng.params["base"]
        eng.process_game(synthetic_game)
        post_home = eng.teams[g["home_team"]].rating
        post_away = eng.teams[g["away_team"]].rating
        eng.teams[g["home_team"]].rating = pre_home + damping * (post_home - pre_home)
        eng.teams[g["away_team"]].rating = pre_away + damping * (post_away - pre_away)
        for team in (g["home_team"], g["away_team"]):
            wl.setdefault(team, {"w": 0, "l": 0})
        if home_wins:
            wl[g["home_team"]]["w"] += 1
            wl[g["away_team"]]["l"] += 1
        else:
            wl[g["away_team"]]["w"] += 1
            wl[g["home_team"]]["l"] += 1
    return dict(wl=wl, ratings=eng.current_ratings())


def project_bands_dynamic(base_engine, season_teams, current, remaining, mov_pool, trials, rng):
    per_team_wins = {team: [] for team in season_teams}
    for _ in range(trials):
        trial = simulate_one_season(base_engine, remaining, mov_pool, rng)
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            add_w = trial["wl"].get(team, {}).get("w", 0)
            per_team_wins[team].append(base_w + add_w)
    return bands_from_wins(per_team_wins)


def project_bands_damped(base_engine, season_teams, current, remaining, mov_pool, trials, rng, damping):
    per_team_wins = {team: [] for team in season_teams}
    for _ in range(trials):
        trial = simulate_one_season_damped(base_engine, remaining, mov_pool, rng, damping)
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            add_w = trial["wl"].get(team, {}).get("w", 0)
            per_team_wins[team].append(base_w + add_w)
    return bands_from_wins(per_team_wins)


def project_bands_frozen(base_engine, season_teams, current, remaining, trials, rng):
    game_probs = []
    for g in remaining:
        preview = base_engine.preview_matchup(
            home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
            season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
        )
        game_probs.append((g["home_team"], g["away_team"], preview["expected_win_home"]))
    per_team_wins = {team: [] for team in season_teams}
    for _ in range(trials):
        trial_wins = {}
        for home, away, p in game_probs:
            if rng.random() < p:
                trial_wins[home] = trial_wins.get(home, 0) + 1
            else:
                trial_wins[away] = trial_wins.get(away, 0) + 1
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            per_team_wins[team].append(base_w + trial_wins.get(team, 0))
    return bands_from_wins(per_team_wins)


def games_remaining_per_team(remaining):
    counts = {}
    for g in remaining:
        counts[g["home_team"]] = counts.get(g["home_team"], 0) + 1
        counts[g["away_team"]] = counts.get(g["away_team"], 0) + 1
    return counts


def raw_scores(bands, common, actual_final, remaining_counts):
    """Per-team raw values (not yet averaged) so they can be POOLED
    across seasons before computing final stats - pooling raw values
    is the correct way to combine samples, not averaging pre-computed
    per-season percentages."""
    hits, widths, ratios, abs_errs = [], [], [], []
    for t in common:
        actual_wins = actual_final[t][0]
        b = bands[t]
        width = b["p90"] - b["p10"]
        widths.append(width)
        abs_errs.append(abs(b["avg"] - actual_wins))
        hits.append(1 if b["p10"] <= actual_wins <= b["p90"] else 0)
        n_i = remaining_counts.get(t, 0)
        baseline_width = coinflip_band_width(n_i)
        if baseline_width > 0:
            ratios.append(width / baseline_width)
    return dict(hits=hits, widths=widths, ratios=ratios, abs_errs=abs_errs)


def pooled_stats(raw_list):
    """Combine a list of raw_scores() dicts (one per season) into one
    pooled coverage/width/ratio/mae."""
    hits, widths, ratios, abs_errs = [], [], [], []
    for r in raw_list:
        hits += r["hits"]
        widths += r["widths"]
        ratios += r["ratios"]
        abs_errs += r["abs_errs"]
    n = len(hits)
    if n == 0:
        return dict(coverage=float("nan"), avg_band_width=float("nan"),
                    coinflip_ratio=float("nan"), mae=float("nan"), n_teams=0)
    return dict(
        coverage=sum(hits) / n,
        avg_band_width=sum(widths) / len(widths) if widths else 0.0,
        coinflip_ratio=sum(ratios) / len(ratios) if ratios else 0.0,
        mae=sum(abs_errs) / len(abs_errs) if abs_errs else 0.0,
        n_teams=n,
    )


def run_checkpoint(base_engine, season_teams, played_so_far, remaining, actual_final,
                    mov_pool, trials, rng, damping):
    current = record_as_of(played_so_far)
    common = sorted(t for t in season_teams if t in actual_final)

    if not remaining:
        empty = dict(hits=[1] * len(common), widths=[0] * len(common),
                     ratios=[], abs_errs=[0] * len(common))
        return dict(dyn=empty, frz=dict(empty), dmp=dict(empty))

    remaining_counts = games_remaining_per_team(remaining)

    dyn_bands = project_bands_dynamic(base_engine, season_teams, current, remaining, mov_pool, trials, rng)
    frz_bands = project_bands_frozen(base_engine, season_teams, current, remaining, trials, rng)
    dmp_bands = project_bands_damped(base_engine, season_teams, current, remaining, mov_pool, trials, rng, damping)

    return dict(
        dyn=raw_scores(dyn_bands, common, actual_final, remaining_counts),
        frz=raw_scores(frz_bands, common, actual_final, remaining_counts),
        dmp=raw_scores(dmp_bands, common, actual_final, remaining_counts),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=str, required=True,
                         help="e.g. '2016-2025' or '2016,2018,2020-2022'")
    parser.add_argument("--variant", default="echo", choices=["echo", "pulse"])
    parser.add_argument("--trials", type=int, default=300,
                         help="pooling across seasons reduces the need for huge per-checkpoint "
                              "trial counts - default is lower than the single-season script")
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    seasons = parse_seasons(args.seasons)
    conn = db.connect(DB_PATH)
    mov_pool = historical_mov_pool(conn)
    rng = random.Random(args.seed)

    # pooled[week_index]["dyn"/"frz"/"dmp"] = list of raw_scores() dicts, one per season
    pooled = {}
    seasons_used = []

    for season in seasons:
        all_dates = season_game_dates(conn, season)
        if not all_dates:
            print(f"  (skipping {season}: no regular-season games found)")
            continue
        all_games = [g for g in db.load_games(conn) if g["season"] == season and g["type"] == "R"]
        season_teams = {g["home_team"] for g in all_games} | {g["away_team"] for g in all_games}
        actual_final = record_as_of(all_games)
        cps = checkpoint_dates(all_dates)
        seasons_used.append(season)

        print(f"Season {season}: {len(cps)} checkpoints")
        for i, cp in enumerate(cps, start=1):
            played_so_far = [g for g in all_games if g["date"] <= cp]
            remaining = [g for g in all_games if g["date"] > cp]
            base_engine = build_engine_as_of(conn, args.variant, cp)

            result = run_checkpoint(base_engine, season_teams, played_so_far, remaining,
                                     actual_final, mov_pool, args.trials, rng, args.damping)

            pooled.setdefault(i, {"dyn": [], "frz": [], "dmp": []})
            pooled[i]["dyn"].append(result["dyn"])
            pooled[i]["frz"].append(result["frz"])
            pooled[i]["dmp"].append(result["dmp"])

    print(f"\nPooled across {len(seasons_used)} seasons: {seasons_used}\n")

    rows = []
    for wk in sorted(pooled):
        d = pooled_stats(pooled[wk]["dyn"])
        f = pooled_stats(pooled[wk]["frz"])
        m = pooled_stats(pooled[wk]["dmp"])
        n_seasons_here = len(pooled[wk]["dyn"])
        rows.append(dict(week=wk, n_seasons=n_seasons_here, n_teams=d["n_teams"],
                          dyn_coverage=d["coverage"], dyn_avg_band_width=d["avg_band_width"],
                          dyn_coinflip_ratio=d["coinflip_ratio"], dyn_mae=d["mae"],
                          frz_coverage=f["coverage"], frz_avg_band_width=f["avg_band_width"],
                          frz_coinflip_ratio=f["coinflip_ratio"], frz_mae=f["mae"],
                          dmp_coverage=m["coverage"], dmp_avg_band_width=m["avg_band_width"],
                          dmp_coinflip_ratio=m["coinflip_ratio"], dmp_mae=m["mae"]))
        print(f"  Week {wk:>2} (n={d['n_teams']:>4} team-seasons, {n_seasons_here} seasons)")
        print(f"           dynamic: band {d['avg_band_width']:>5.2f}  coinflip {d['coinflip_ratio']:>4.2f}x  coverage {d['coverage']:>5.1%}")
        print(f"           damped:  band {m['avg_band_width']:>5.2f}  coinflip {m['coinflip_ratio']:>4.2f}x  coverage {m['coverage']:>5.1%}")
        print(f"           frozen:  band {f['avg_band_width']:>5.2f}  coinflip {f['coinflip_ratio']:>4.2f}x  coverage {f['coverage']:>5.1%}")

    os.makedirs(OUT_DIR, exist_ok=True)
    season_tag = args.seasons.replace(",", "_").replace("-", "to")
    suffix = "" if args.variant == "echo" else f"_{args.variant}"
    fieldnames = ["week", "n_seasons", "n_teams",
                  "dyn_coverage", "dyn_avg_band_width", "dyn_coinflip_ratio", "dyn_mae",
                  "dmp_coverage", "dmp_avg_band_width", "dmp_coinflip_ratio", "dmp_mae",
                  "frz_coverage", "frz_avg_band_width", "frz_coinflip_ratio", "frz_mae"]
    csv_path = os.path.join(OUT_DIR, f"stabilization_pooled_{season_tag}{suffix}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    txt_path = os.path.join(OUT_DIR, f"stabilization_pooled_{season_tag}{suffix}.txt")
    with open(txt_path, "w") as f:
        label = "Echo" if args.variant == "echo" else "Pulse"
        f.write(f"{LEAGUE_LABEL} {label} - Pooled Multi-Season Trust Check\n")
        f.write(f"Seasons: {seasons_used}\n")
        f.write("=" * 100 + "\n")
        f.write(f"{args.trials} trials per checkpoint per season. Each week's stats are POOLED\n")
        f.write("across every season's team at that week index (week 1 = each season's first\n")
        f.write("checkpoint, etc.) - not averaged per-season, but combined at the team level, so\n")
        f.write("the sample size (n_teams) is much larger than any single season alone.\n")
        f.write("COVERAGE target ~80%. COINFLIP RATIO: 1.0 = no better than a coin flip.\n\n")
        f.write(f"{'Week':<6}{'nSea':>6}{'nTeam':>7}  "
                f"{'DynBand':>8}{'DynRat':>8}{'DynCov':>8}   "
                f"{'DmpBand':>8}{'DmpRat':>8}{'DmpCov':>8}   "
                f"{'FrzBand':>8}{'FrzRat':>8}{'FrzCov':>8}\n")
        f.write("-" * 100 + "\n")
        for row in rows:
            f.write(f"{row['week']:<6}{row['n_seasons']:>6}{row['n_teams']:>7}  "
                     f"{row['dyn_avg_band_width']:>8.2f}{row['dyn_coinflip_ratio']:>7.2f}x{row['dyn_coverage']:>8.1%}   "
                     f"{row['dmp_avg_band_width']:>8.2f}{row['dmp_coinflip_ratio']:>7.2f}x{row['dmp_coverage']:>8.1%}   "
                     f"{row['frz_avg_band_width']:>8.2f}{row['frz_coinflip_ratio']:>7.2f}x{row['frz_coverage']:>8.1%}\n")

    print(f"\nWrote {csv_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()

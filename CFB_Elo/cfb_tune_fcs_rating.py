"""
cfb_tune_fcs_rating.py

Tunes `fcs_rating` IN ISOLATION - alpha/kmax/hfa are held FIXED at the
current tuned CFB values (see CFB_Elo_HANDOFF.md's "2006 parameters",
validated walk-forward on 1996-2005: alpha=0.7, kmax=96, hfa=68), not
engine.py's untuned BASELINE_PARAMS. Only fcs_rating is swept.

WHY SCORE ONLY FBS-vs-FCS GAMES, NOT ALL GAMES: fcs_rating only enters
the win-probability math on the FBS side's row in a game where the
opponent isn't FBS that season (see engine.py's FCS HANDLING) - every
other game's log-loss is completely unaffected by its value. Scoring
against all games would dilute the signal to the point of noise, since
FBS-vs-FCS games are a small fraction of the schedule. engine.py's
process_week() already gives us a clean way to isolate them: a game
produces ONE row (not two) exactly when one side was non-FBS that
season - only the FBS side ever gets a row (see engine.py's FCS
HANDLING / process_week docstring). This script scores fcs_rating
using ONLY those single-row games' `test` (log-loss) values.

WHY ONE CONTINUOUS REPLAY PER CANDIDATE, NOT A FRESH REPLAY PER ERA:
apply_season_entry() (rebuild.py) needs to know if a season is the
very first one this engine instance has EVER processed
(is_first_season) to decide whether to do the real conference-average
season-entry blend or just flat-start every team at `base` (1500) -
that's the correct behavior for a from-scratch database, but it would
be WRONG to trigger for, say, an era block starting in 2006, since
those teams have real prior history in production. Restarting fresh
per era (the way NFL_Elo's era_stability_check does, harmlessly, since
NFL_Elo has no season-entry blending at all) would bias that era's
FBS-vs-FCS log-loss by flattening every team's true entering rating in
the era's first season. Instead, this script runs ONE continuous,
correctly-seasoned replay across the full 1996-2025 history per
candidate fcs_rating value, then splits THAT run's rows by era for
reporting - same insight into whether the value drifts, no reset
artifact, and cheaper (one sweep instead of one sweep per era).

Prints two things:
  1. A GLOBAL sweep across all 30 seasons.
  2. The SAME sweep's rows re-scored within 3 roughly-equal eras (same
     3-way split idea as NFL_Elo's era_stability_check), to show
     whether the optimal value drifts across time.

Usage:
    python3 cfb_tune_fcs_rating.py cfb_elo.db
"""
import sys

import db
import engine
import rebuild

# Held FIXED for this entire tune - see module docstring. fcs_rating
# itself is overwritten per candidate by _params() below.
FIXED_ALPHA = 0.7
FIXED_KMAX = 96.0
FIXED_HFA = 68.0

FCS_RATING_RANGE = list(range(800, 1501, 25))

N_ERAS = 3


def _params(fcs_rating: float) -> dict:
    p = engine.default_params()
    p["alpha"] = FIXED_ALPHA
    p["kmax"] = FIXED_KMAX
    p["hfa"] = FIXED_HFA
    p["fcs_rating"] = float(fcs_rating)
    return p


def replay(conn, games: list[dict], resets: set, season_rosters: dict,
           weeks: dict, params: dict) -> list[list[dict]]:
    """One full, correctly-seasoned replay across every week in
    `weeks`, for ONE fixed params dict. Returns every game's row list
    in chronological order (each entry is what engine.process_week()
    returned for that game: two rows for FBS-vs-FBS, one row for
    FBS-vs-FCS, per this module's docstring). `games`/`weeks`/
    `season_rosters` are computed ONCE by main() and reused across
    every candidate fcs_rating value - only `params` changes here."""
    eng = engine.EloEngine(params, resets=resets)
    first_season = games[0]["season"]
    current_season = None
    all_game_rows = []
    for key in sorted(weeks):
        season = key[0]
        if season != current_season:
            rebuild.apply_season_entry(
                conn, eng, season, season_rosters.get(season, set()),
                is_first_season=(season == first_season),
            )
            current_season = season
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        for game_rows in eng.process_week(week_games):
            all_game_rows.append(game_rows)
    return all_game_rows


def fcs_log_loss(all_game_rows: list[list[dict]], lo: int | None = None,
                  hi: int | None = None) -> tuple[float | None, int]:
    """Mean log-loss over FBS-vs-FCS games only (single-row games - see
    module docstring), optionally restricted to seasons in [lo, hi]."""
    tests = []
    for game_rows in all_game_rows:
        if len(game_rows) != 1:
            continue
        row = game_rows[0]
        if lo is not None and not (lo <= row["season"] <= hi):
            continue
        tests.append(row["test"])
    if not tests:
        return None, 0
    return sum(tests) / len(tests), len(tests)


def era_bounds(games: list[dict], n_eras: int) -> list[tuple[int, int]]:
    seasons = sorted({g["season"] for g in games})
    n = len(seasons)
    edges = [seasons[int(i * n / n_eras)] for i in range(n_eras)] + [seasons[-1] + 1]
    return [(edges[i], edges[i + 1] - 1) for i in range(n_eras)]


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "cfb_elo.db"
    conn = db.connect(db_path)

    games = db.load_games(conn)
    if not games:
        print(f"No games found in {db_path}.")
        sys.exit(1)
    rebuild._annotate_conferences(conn, games)
    resets = db.load_resets(conn)
    season_rosters = rebuild._season_fbs_teams(games)
    weeks = rebuild._week_buckets(games)
    eras = era_bounds(games, N_ERAS)

    print(f"Loaded {len(games):,} games "
          f"({games[0]['season']}-{games[-1]['season']}).")
    print(f"Fixed for this tune: alpha={FIXED_ALPHA} kmax={FIXED_KMAX} hfa={FIXED_HFA}\n")

    # One replay per candidate fcs_rating - global AND per-era log-loss
    # come from that SAME run's rows (see module docstring on why).
    print("=== GLOBAL sweep (all seasons) ===")
    global_results = []
    era_results = {era: [] for era in eras}
    for fcs_rating in FCS_RATING_RANGE:
        params = _params(fcs_rating)
        all_game_rows = replay(conn, games, resets, season_rosters, weeks, params)

        ll, n = fcs_log_loss(all_game_rows)
        if ll is None:
            print(f"  fcs_rating={fcs_rating:4d}  (no FBS-vs-FCS games found)")
        else:
            print(f"  fcs_rating={fcs_rating:4d}  n={n:5d}  log_loss={ll:.4f}")
            global_results.append((fcs_rating, ll, n))

        for era in eras:
            lo, hi = era
            era_ll, era_n = fcs_log_loss(all_game_rows, lo, hi)
            if era_ll is not None:
                era_results[era].append((fcs_rating, era_ll, era_n))

    if global_results:
        best_fcs, best_ll, best_n = min(global_results, key=lambda r: r[1])
        print(f"\n  -> GLOBAL best: fcs_rating={best_fcs}  log_loss={best_ll:.4f}  (n={best_n})\n")
    else:
        print("\n  -> No FBS-vs-FCS games found in the full history.\n")

    print(f"=== Era stability check ({N_ERAS}-way split) ===\n")
    for era in eras:
        lo, hi = era
        results = era_results[era]
        if not results:
            print(f"  {lo}-{hi}: no FBS-vs-FCS games in this window\n")
            continue
        for fcs_rating, ll, n in results:
            print(f"  {lo}-{hi}  fcs_rating={fcs_rating:4d}  n={n:4d}  log_loss={ll:.4f}")
        best_fcs, best_ll, best_n = min(results, key=lambda r: r[1])
        print(f"  -> {lo}-{hi} best: fcs_rating={best_fcs}  log_loss={best_ll:.4f}  (n={best_n})\n")


if __name__ == "__main__":
    main()

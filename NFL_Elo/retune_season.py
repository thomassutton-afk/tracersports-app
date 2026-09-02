"""
retune_season.py

The recurring offseason task this whole exercise was building toward.

Run this once after add_season.py has loaded a new season's games:

    python3 retune_season.py nfl_elo.db

First time it's run (no param_schedule.json yet): bootstraps the full
history -- locks 1996-2005 as a one-time in-sample warm-up tune, then
walks forward one season at a time, tuning each season only on the
trailing 10 seasons before it (real EloEngine, never the season's own
results). This matches nfl_reconstruct_engine.py's logic exactly; this
script is the version meant to be run for real and re-run every year,
rather than as a one-off research artifact.

Every subsequent run: the schedule file already covers everything up
through last season. This only needs to tune ONE new season (the
newest one now in the database) on ITS trailing 10 seasons, add that
one row, and leave every prior season's locked parameters untouched.

After updating the schedule, this hands off to rebuild.py exactly like
add_season.py already does -- see the NOTE at the bottom of this file
for the one small edit rebuild.py itself still needs before this
actually takes effect.
"""
import sys

import db
from nfl_tune_engine import load_games_as_dicts, games_to_weeks, coordinate_ascent_engine

WARMUP_START = 1996
WARMUP_END = 2005
WINDOW_LEN = 10
DB_PATH = "nfl_elo.db"


def weeks_for_range(games, lo, hi):
    subset = [g for g in games if lo <= g["season"] <= hi]
    return games_to_weeks(subset)


def bootstrap_full_schedule(conn, games) -> dict:
    print(f"No existing schedule found -- bootstrapping full history "
          f"({WARMUP_START}-present). This only needs to happen once.\n")
    schedule = {}

    warmup_weeks = weeks_for_range(games, WARMUP_START, WARMUP_END)
    warmup = coordinate_ascent_engine(warmup_weeks, rounds=3)
    for y in range(WARMUP_START, WARMUP_END + 1):
        schedule[y] = {"alpha": warmup["alpha"], "kmax": warmup["kmax"], "hfa": warmup["hfa"]}
    print(f"  warm-up {WARMUP_START}-{WARMUP_END} (in-sample): "
          f"alpha={warmup['alpha']} kmax={warmup['kmax']} hfa={warmup['hfa']}")

    seasons = sorted({g["season"] for g in games})
    for y in [s for s in seasons if s > WARMUP_END]:
        weeks = weeks_for_range(games, y - WINDOW_LEN, y - 1)
        p = coordinate_ascent_engine(weeks, rounds=3, start=(0.4, 44.0, 52.0))
        schedule[y] = {"alpha": p["alpha"], "kmax": p["kmax"], "hfa": p["hfa"]}
        print(f"  season {y} (rolling {y-WINDOW_LEN}-{y-1}): "
              f"alpha={p['alpha']} kmax={p['kmax']} hfa={p['hfa']}")

    return schedule


def append_newest_season(conn, games, schedule: dict) -> dict:
    seasons = sorted({g["season"] for g in games})
    newest = seasons[-1]
    if newest in schedule:
        print(f"Season {newest} already has a locked entry in the schedule -- nothing to do.\n"
              f"(If you're re-running this after correcting/backfilling {newest}'s games, "
              f"that's fine -- its parameters were tuned on {newest-WINDOW_LEN}-{newest-1} "
              f"anyway, never on {newest} itself, so nothing needs to change.)")
        return schedule

    weeks = weeks_for_range(games, newest - WINDOW_LEN, newest - 1)
    p = coordinate_ascent_engine(weeks, rounds=3, start=(0.4, 44.0, 52.0))
    schedule[newest] = {"alpha": p["alpha"], "kmax": p["kmax"], "hfa": p["hfa"]}
    print(f"Added season {newest} (tuned on {newest-WINDOW_LEN}-{newest-1}, "
          f"never on {newest}'s own results): alpha={p['alpha']} kmax={p['kmax']} hfa={p['hfa']}")
    return schedule


def add_specific_season(conn, games, schedule: dict, season: int) -> dict:
    """Lock in a season's parameters BEFORE it has any completed games in
    the database -- e.g. you've uploaded next season's schedule (all
    unplayed, sitting in `schedule`, not `games`) and want honest
    predictions for week 1 before a single game has been played. This
    never needs that season's own results anyway (only the trailing
    window before it), so there's no reason to wait for games to exist."""
    if season in schedule:
        print(f"Season {season} already has a locked entry -- nothing to do.")
        return schedule
    weeks = weeks_for_range(games, season - WINDOW_LEN, season - 1)
    if not weeks:
        print(f"No games found for {season-WINDOW_LEN}-{season-1} -- can't tune season "
              f"{season} yet (nothing to build a trailing window from).")
        return schedule
    p = coordinate_ascent_engine(weeks, rounds=3, start=(0.4, 44.0, 52.0))
    schedule[season] = {"alpha": p["alpha"], "kmax": p["kmax"], "hfa": p["hfa"]}
    print(f"Added season {season} (tuned on {season-WINDOW_LEN}-{season-1}, "
          f"before any {season} game has been played): "
          f"alpha={p['alpha']} kmax={p['kmax']} hfa={p['hfa']}")
    return schedule


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", nargs="?", default=DB_PATH)
    ap.add_argument("--season", type=int, default=None,
                     help="Force-add this specific season (tuned on its trailing "
                          "window) even if it has no completed games yet -- use this "
                          "for a schedule-only upload (e.g. locking in next season's "
                          "params before Week 1 so predictions use the right numbers).")
    args = ap.parse_args()

    conn = db.connect(args.db_path)
    games = load_games_as_dicts(args.db_path)

    existing = db.load_param_schedule(conn)
    if existing is None:
        schedule = bootstrap_full_schedule(conn, games)
    elif args.season is not None:
        schedule = add_specific_season(conn, games, existing, args.season)
    else:
        schedule = append_newest_season(conn, games, existing)

    db.save_param_schedule(conn, schedule)
    print(f"\nSaved -> {db.SCHEDULE_FILE}")

    try:
        from rebuild import rebuild_ratings
        rebuild_ratings(conn)
        print("Ratings rebuilt using the updated schedule.")
    except ImportError:
        print("\nNOTE: could not import rebuild_ratings (rebuild.py not found in this "
              "environment). Run 'python3 rebuild.py' separately once rebuild.py has been "
              "updated to call db.params_for_season(conn, season) at each season boundary "
              "instead of one static params dict for the whole replay -- see this repo's "
              "nfl_reconstruct_engine.py:simulate_with_schedule() for the exact pattern "
              "(swap eng.params right before the first process_week() call of each new season).")


if __name__ == "__main__":
    main()

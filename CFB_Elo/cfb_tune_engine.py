"""
cfb_tune_engine.py

Forked from NFL_Elo's nfl_tune_engine.py. Same approach: imports
engine.py directly and drives the REAL EloEngine/process_week - the
exact code path production uses - rather than reimplementing the Elo
formula in a second place. Tunes FOUR knobs: alpha/kmax/hfa (the same
three headline knobs as the NFL version) PLUS fcs_rating, the fixed
opponent-strength constant used for any non-FBS team (see engine.py's
FCS HANDLING) - CFB has no NFL_Elo equivalent for this fourth one, so
there's no "known good" value to start from at all. Everything else
(k_floor, rest_minor/major, div/conf multipliers, playoff round
multipliers) stays at engine.py's baseline.

Reuses db.load_games() and rebuild._annotate_conferences() rather than
querying the database directly - this is what makes fcs_rating
tunable at all here: without real home_is_fbs/away_is_fbs flags
attached to every game, every game would look like two FBS teams
playing (process_week defaults missing flags to True), and fcs_rating
would have zero effect on the loss being optimized.

USE THIS ONLY ONCE REAL GAME DATA *AND* CONFERENCE MEMBERSHIP ARE
LOADED (i.e. after load_conference_membership.py has been run for
every season, not just add_season.py) - otherwise every team looks
non-FBS (see db.py's fbs_membership comment) and this would just be
tuning fcs_rating against noise. The starting search ranges below are
NOT validated for CFB - CFB's score variance is much wider than the
NFL's (60-3 games are common), so don't be surprised if the optimal
alpha/kmax/hfa land somewhere very different from NFL's tuned values
once there's enough CFB history in the database to tune against.

Usage:
    python3 cfb_tune_engine.py cfb_elo.db
"""
import sys

import db
import engine
import rebuild


def load_games_as_dicts(db_path: str) -> list[dict]:
    """Reuses db.load_games() + rebuild._annotate_conferences() so this
    tuner sees EXACTLY the same conf/div/FBS annotations production
    rebuilds use - a hand-rolled reimplementation here risked silently
    drifting out of sync with rebuild.py, the same trap NFL_Elo's
    original nfl_tune.py fell into with the Elo formula itself (see
    this module's docstring)."""
    conn = db.connect(db_path)
    games = db.load_games(conn)
    rebuild._annotate_conferences(conn, games)
    return games


def games_to_weeks(games: list[dict]) -> list[list[dict]]:
    """Group games into (season, week) batches, in chronological order,
    via rebuild._week_buckets() - same bucketing production uses,
    rather than a second reimplementation of it here."""
    buckets = rebuild._week_buckets(games)
    return [sorted(buckets[key], key=lambda g: g["date"]) for key in sorted(buckets)]


def log_loss_of(rows: list[dict]) -> float:
    home_rows = [r for r in rows if r["home_away"] == "H"]
    return sum(r["test"] for r in home_rows) / len(home_rows)


def run_engine(weeks: list[list[dict]], alpha: float, kmax: float, hfa: float,
               fcs_rating: float, resets: set | None = None) -> list[dict]:
    params = engine.default_params()
    params["alpha"] = alpha
    params["kmax"] = kmax
    params["hfa"] = hfa
    params["fcs_rating"] = fcs_rating
    eng = engine.EloEngine(params, resets=resets)
    all_rows = []
    for wk_games in weeks:
        for row_list in eng.process_week(wk_games):
            all_rows.extend(row_list)
    return all_rows


def coordinate_ascent_engine(weeks: list[list[dict]], rounds: int = 3,
                              start=(0.3, 46.0, 55.0, 1200.0)) -> dict:
    alpha, kmax, hfa, fcs_rating = start
    # UNTUNED STARTING RANGES - alpha/kmax/hfa copied from NFL_Elo's
    # search grid; fcs_rating has NO prior art at all (NFL has no
    # equivalent concept), so this range is just "somewhere plausibly
    # below base (1500), wide enough to find the actual optimum."
    # CFB's much higher score variance may mean the true optimum for
    # kmax/hfa in particular sits well outside these bounds; widen any
    # of these if the coordinate ascent keeps landing on a range edge.
    alpha_range = [round(0.1 * i, 2) for i in range(1, 10)]
    kmax_range = list(range(20, 71, 2))
    hfa_range = list(range(0, 121, 4))
    fcs_range = list(range(900, 1500, 25))

    def score(a, k, h, f):
        rows = run_engine(weeks, a, k, h, f)
        return log_loss_of(rows)

    best_ll = score(alpha, kmax, hfa, fcs_rating)

    for _ in range(rounds):
        improved = False

        best_a, best_a_ll = alpha, best_ll
        for a in alpha_range:
            ll = score(a, kmax, hfa, fcs_rating)
            if ll < best_a_ll:
                best_a, best_a_ll = a, ll
        if best_a != alpha:
            alpha, best_ll, improved = best_a, best_a_ll, True

        best_k, best_k_ll = kmax, best_ll
        for k in kmax_range:
            ll = score(alpha, k, hfa, fcs_rating)
            if ll < best_k_ll:
                best_k, best_k_ll = k, ll
        if best_k != kmax:
            kmax, best_ll, improved = best_k, best_k_ll, True

        best_h, best_h_ll = hfa, best_ll
        for h in hfa_range:
            ll = score(alpha, kmax, h, fcs_rating)
            if ll < best_h_ll:
                best_h, best_h_ll = h, ll
        if best_h != hfa:
            hfa, best_ll, improved = best_h, best_h_ll, True

        best_f, best_f_ll = fcs_rating, best_ll
        for f in fcs_range:
            ll = score(alpha, kmax, hfa, f)
            if ll < best_f_ll:
                best_f, best_f_ll = f, ll
        if best_f != fcs_rating:
            fcs_rating, best_ll, improved = best_f, best_f_ll, True

        if not improved:
            break

    return {"alpha": alpha, "kmax": kmax, "hfa": hfa, "fcs_rating": fcs_rating,
            "train_log_loss": best_ll}


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "cfb_elo.db"
    games = load_games_as_dicts(db_path)
    weeks = games_to_weeks(games)
    print(f"Loaded {len(games):,} games across {len(weeks)} team-weeks\n")

    tuned = coordinate_ascent_engine(weeks, rounds=3)
    print(f"Engine-faithful full-history tune: alpha={tuned['alpha']} "
          f"kmax={tuned['kmax']} hfa={tuned['hfa']} fcs_rating={tuned['fcs_rating']}  "
          f"log_loss={tuned['train_log_loss']:.4f}")

    baseline_rows = run_engine(weeks, 0.3, 46.0, 72.0, 1200.0)
    print(f"Untuned starting point, run against CFB data for comparison only "
          f"(alpha=0.3 kmax=46 hfa=72 fcs_rating=1200): "
          f"log_loss={log_loss_of(baseline_rows):.4f}")



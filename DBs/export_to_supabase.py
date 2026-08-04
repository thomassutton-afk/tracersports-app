"""
export_to_supabase.py — moves finished ratings data from a per-sport SQLite
database (built by the NBA_Elo / WNBA_Elo / etc. toolchain) into the new
multi-sport Supabase schema (schema.sql).

USAGE
-----
Dry run first (no Supabase connection needed, just prints what WOULD be
written, plus sample rows, so you can sanity-check before touching the
real database):

    python export_to_supabase.py --league nba --db nba_elo.db --dry-run
    python export_to_supabase.py --league wnba --db wnba_elo.db --dry-run

Real run (writes to Supabase; needs a .env file — see bottom of this file
for what it should contain):

    python export_to_supabase.py --league nba --db nba_elo.db
    python export_to_supabase.py --league wnba --db wnba_elo.db

WHAT THIS DOES
--------------
1. teams        — resolves each opaque team_id (e.g. "nba_0003") to its
                   CURRENT 3-letter code and full name, using team_history
                   (the row with end_season IS NULL is "current"). Marks a
                   team `active` if that current code appears in this
                   league's live site config (lib/sports/{league}/config.js)
                   — i.e. it's a team the site actually displays today.
2. games         — one row per team per game, copied from the `ratings`
                   table, with team/opponent remapped from opaque IDs to
                   current codes. Tagged variant='continelo' (Echo) only —
                   see note below.
3. preseason_ratings — APPROXIMATED as each team's `pre_rate` from its
                   first chronological game of a season. This isn't
                   necessarily identical to a true "preseason" figure if
                   the source system computes one separately — flagged as
                   an approximation, not verified against source intent.

WHAT THIS DOES NOT DO YET
--------------------------
- No Pulse (reset-each-season) variant — only Echo/continelo exists in the
  source data right now. Re-run this script against a Pulse-computing
  version of the engine later to backfill that variant; nothing here needs
  to change structurally when that happens.
- No `standings` table population — deferred. The site's Standings tab
  already derives everything it needs from game-level data directly
  (same pattern as StandingsTab.jsx's mock data), so a separately
  maintained standings table isn't blocking anything yet. Revisit if a
  need for it becomes concrete (e.g. an All-Time champions page).
- `conference`/`division` columns in the new `teams` table are left NULL
  intentionally. Per the project's architecture, that display metadata
  comes from lib/sports/{league}/config.js at render time, not the
  database — this export only needs to satisfy the FK from games/standings.
"""

import argparse
import os
import sqlite3
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — fine for --dry-run, needed for a real run

# Current, live-site team codes per league — used only to set `active` on
# historical teams. Source of truth is each league's config.js; keep this
# in sync manually if a team is added/removed from the live site.
ACTIVE_CODES = {
    "nba": {
        "ATL", "BOS", "BRK", "CHH", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAS", "SAC", "TOR", "UTA", "WAS",
    },
    "wnba": {
        "ATL", "CHI", "CON", "IND", "NYL", "TOR", "WAS", "DAL", "GSV", "LVA",
        "LAS", "MIN", "PHX", "POR", "SEA",
    },
}

SPORT_FOR_LEAGUE = {
    "nba": "basketball",
    "wnba": "basketball",
}

VARIANT = "continelo"  # Echo. See module docstring — Pulse doesn't exist yet.


def resolve_current_codes(conn):
    """
    Returns {team_id: (current_code, full_name)} for every team_id in the
    SQLite database, using the team_history row with end_season IS NULL as
    the "current" identity. Falls back to the row with the highest
    start_season if none has a NULL end_season (shouldn't happen in
    practice, but better to fall back than crash).
    """
    cur = conn.cursor()
    cur.execute("SELECT team_id, team_name FROM teams")
    full_names = dict(cur.fetchall())

    cur.execute(
        "SELECT team_id, code, start_season, end_season FROM team_history "
        "ORDER BY team_id, start_season"
    )
    by_team = {}
    for team_id, code, start, end in cur.fetchall():
        by_team.setdefault(team_id, []).append((code, start, end))

    result = {}
    for team_id, rows in by_team.items():
        current = next((r for r in rows if r[2] is None), None)
        if current is None:
            current = max(rows, key=lambda r: r[1])  # highest start_season
        code = current[0]
        result[team_id] = (code, full_names.get(team_id, code))
    return result


def build_teams(conn, league, id_to_code):
    sport = SPORT_FOR_LEAGUE[league]
    active_set = ACTIVE_CODES[league]
    rows = []
    seen_codes = set()
    for team_id, (code, full_name) in id_to_code.items():
        if code in seen_codes:
            continue  # a code should map to exactly one team_id; guard anyway
        seen_codes.add(code)
        rows.append(
            {
                "league": league,
                "team_id": code,
                "sport": sport,
                "full_name": full_name,
                "city": None,  # comes from config.js at render time
                "nickname": None,  # comes from config.js at render time
                "conference": None,  # intentional — see module docstring
                "division": None,  # intentional — see module docstring
                "active": code in active_set,
            }
        )
    return rows


GAMES_COLUMNS = [
    "game_id", "team_id", "date", "season", "type", "round", "opponent_id",
    "home_away", "points_for", "points_against", "ot", "days_off",
    "opp_days_off", "rest_diff", "rest_adj", "pre_gm_rate", "opp_pre_gm_rate",
    "expected_win_pct", "mov", "result", "accuracy", "brier", "mov_mult",
    "games_played", "k", "po_mult", "k_eff", "rating_change", "post_gm_rate",
    "w", "l", "r1w", "r1l", "r2w", "r2l", "r3w", "r3l", "fw", "fl",
]


def build_games(conn, league, id_to_code):
    cur = conn.cursor()
    cur.execute(
        "SELECT game_id, team, opponent, home_away, date, season, type, "
        "round, games_played, days_off, opp_days_off, rest_adj, pre_rate, "
        "opp_pre_rate, expected_win, points_for, points_against, ot, mov, "
        "result, accuracy, brier, mov_mult, po_mult, k, keff, "
        "rating_change, post_rate, w, l, r1w, r1l, r2w, r2l, r3w, r3l, fw, fl "
        "FROM ratings"
    )
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        team_code = id_to_code.get(r["team"], (r["team"], None))[0]
        opp_code = id_to_code.get(r["opponent"], (r["opponent"], None))[0]
        rows.append(
            {
                "game_id": str(r["game_id"]),
                "league": league,
                "variant": VARIANT,
                "team_id": team_code,
                "date": r["date"],
                "season": r["season"],
                "type": r["type"],
                "round": r["round"],
                "opponent_id": opp_code,
                "home_away": r["home_away"],
                "points_for": r["points_for"],
                "points_against": r["points_against"],
                "ot": r["ot"],
                "days_off": r["days_off"],
                "opp_days_off": r["opp_days_off"],
                "rest_diff": (
                    None
                    if r["days_off"] is None or r["opp_days_off"] is None
                    else r["days_off"] - r["opp_days_off"]
                ),
                "rest_adj": r["rest_adj"],
                "pre_gm_rate": r["pre_rate"],
                "opp_pre_gm_rate": r["opp_pre_rate"],
                "expected_win_pct": r["expected_win"],
                "mov": r["mov"],
                "result": r["result"],
                "accuracy": r["accuracy"],
                "brier": r["brier"],
                "mov_mult": r["mov_mult"],
                "games_played": r["games_played"],
                "k": r["k"],
                "po_mult": r["po_mult"],
                "k_eff": r["keff"],
                "rating_change": r["rating_change"],
                "post_gm_rate": r["post_rate"],
                "w": r["w"],
                "l": r["l"],
                "r1w": r["r1w"], "r1l": r["r1l"],
                "r2w": r["r2w"], "r2l": r["r2l"],
                "r3w": r["r3w"], "r3l": r["r3l"],
                "fw": r["fw"], "fl": r["fl"],
            }
        )
    return rows


def build_preseason_ratings(games_rows):
    """
    APPROXIMATION: uses each team's earliest game of a season as a proxy
    for a "preseason" rating (its pre_gm_rate). Not verified against
    whatever the source engine considers a true preseason value — flagged
    for a look if that turns out to matter (e.g. if there's a real
    preseason projection distinct from "rating entering game 1").
    """
    earliest = {}
    for g in games_rows:
        key = (g["league"], g["season"], g["variant"], g["team_id"])
        if key not in earliest or g["date"] < earliest[key]["date"]:
            earliest[key] = g
    return [
        {
            "league": g["league"],
            "season": g["season"],
            "variant": g["variant"],
            "team_id": g["team_id"],
            "preseason_elo": g["pre_gm_rate"],
        }
        for g in earliest.values()
    ]


SCHEDULE_COLUMNS = [
    "league", "variant", "team_id", "date", "season", "type", "round",
    "opponent_id", "home_away", "neutral", "expected_win_pct", "days_off",
    "opp_days_off", "rest_diff", "rest_adj",
]


def build_schedule(conn, league, id_to_code):
    """
    Reads the local `schedule` table (unplayed games with Elo's
    predictions, if write_schedule_predictions() has run for them) and
    expands each row into two Supabase rows - one per team - mirroring
    games' one-row-per-team-per-game shape so GamesPanel.jsx can reuse
    the same per-team rendering logic for both tables.

    expected_win_pct is always THIS row's team_id's own win probability
    (home row + away row sum to 1.0), matching games.expected_win_pct's
    convention. rest_adj is stored once per local schedule row (the
    home team's value); the away row's is that value negated, since
    preview_matchup()'s +/-16 clamp is symmetric both ways - see
    db.py's write_schedule_predictions() docstring.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT date, season, type, round, home_team, away_team, neutral, "
        "expected_win_home, expected_win_away, home_days_off, away_days_off, rest_adj "
        "FROM schedule"
    )
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        home_code = id_to_code.get(r["home_team"], (r["home_team"], None))[0]
        away_code = id_to_code.get(r["away_team"], (r["away_team"], None))[0]

        rest_diff = (
            None
            if r["home_days_off"] is None or r["away_days_off"] is None
            else r["home_days_off"] - r["away_days_off"]
        )
        home_rest_adj = r["rest_adj"]
        away_rest_adj = None if home_rest_adj is None else -home_rest_adj

        base = dict(
            league=league, variant=VARIANT, date=r["date"], season=r["season"],
            type=r["type"], round=r["round"], neutral=r["neutral"],
        )
        rows.append(dict(
            base, team_id=home_code, opponent_id=away_code, home_away="H",
            expected_win_pct=r["expected_win_home"],
            days_off=r["home_days_off"], opp_days_off=r["away_days_off"],
            rest_diff=rest_diff, rest_adj=home_rest_adj,
        ))
        rows.append(dict(
            base, team_id=away_code, opponent_id=home_code, home_away="A",
            expected_win_pct=r["expected_win_away"],
            days_off=r["away_days_off"], opp_days_off=r["home_days_off"],
            rest_diff=None if rest_diff is None else -rest_diff,
            rest_adj=away_rest_adj,
        ))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True, choices=list(SPORT_FOR_LEAGUE))
    parser.add_argument("--db", required=True, help="Path to the SQLite .db file")
    parser.add_argument("--dry-run", action="store_true", help="Don't touch Supabase, just report")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    id_to_code = resolve_current_codes(conn)
    teams_rows = build_teams(conn, args.league, id_to_code)
    games_rows = build_games(conn, args.league, id_to_code)
    preseason_rows = build_preseason_ratings(games_rows)
    schedule_rows = build_schedule(conn, args.league, id_to_code)
    conn.close()

    print(f"League: {args.league}")
    print(f"  teams:              {len(teams_rows)} rows "
          f"({sum(1 for t in teams_rows if t['active'])} active, "
          f"{sum(1 for t in teams_rows if not t['active'])} historical)")
    print(f"  games:              {len(games_rows)} rows")
    print(f"  preseason_ratings:  {len(preseason_rows)} rows")
    print(f"  schedule:           {len(schedule_rows)} rows "
          f"({len(schedule_rows) // 2} upcoming game(s))")
    print()
    print("Sample team rows:")
    for t in teams_rows[:5]:
        print(" ", t)
    print()
    print("Sample game rows:")
    for g in games_rows[:2]:
        print(" ", g)
    print()
    print("Sample schedule rows:")
    for s in schedule_rows[:2]:
        print(" ", s)

    if args.dry_run:
        print("\n[dry run] No Supabase connection made, nothing written.")
        return

    write_to_supabase(args.league, teams_rows, games_rows, preseason_rows, schedule_rows)


def write_to_supabase(league, teams_rows, games_rows, preseason_rows, schedule_rows):
    import psycopg2
    from psycopg2.extras import execute_values

    db_host = os.environ.get("SUPABASE_DB_HOST")
    db_port = os.environ.get("SUPABASE_DB_PORT", "5432")
    db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    db_user = os.environ.get("SUPABASE_DB_USER")
    db_pass = os.environ.get("SUPABASE_DB_PASS")

    if not all([db_host, db_user, db_pass]):
        print(
            "Missing SUPABASE_DB_HOST / SUPABASE_DB_USER / SUPABASE_DB_PASS "
            "environment variables. Set them in a .env file (see bottom of "
            "this script) and make sure something loads it (e.g. "
            "python-dotenv), or export them in your shell before running."
        )
        sys.exit(1)

    conn = psycopg2.connect(
        host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass
    )
    cur = conn.cursor()

    execute_values(
        cur,
        """
        INSERT INTO teams (league, team_id, sport, full_name, city, nickname,
                            conference, division, active)
        VALUES %s
        ON CONFLICT (league, team_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            active = EXCLUDED.active
        """,
        [
            (
                t["league"], t["team_id"], t["sport"], t["full_name"],
                t["city"], t["nickname"], t["conference"], t["division"],
                t["active"],
            )
            for t in teams_rows
        ],
    )
    print(f"Wrote {len(teams_rows)} team rows.")

    execute_values(
        cur,
        f"""
        INSERT INTO games ({', '.join(GAMES_COLUMNS)}, league, variant)
        VALUES %s
        -- Conflict target is a stable natural key, not game_id. game_id
        -- comes from SQLite's AUTOINCREMENT and gets reassigned if the
        -- local `games` table is ever rebuilt from scratch (e.g. a full
        -- re-import from Results files) - two exports done before/after
        -- such a rebuild would otherwise insert every game twice under
        -- different game_ids. This natural key can't drift like that.
        -- Must exactly match idx_games_natural_key in schema.sql.
        ON CONFLICT (league, season, variant, team_id, date, opponent_id, home_away, type, (COALESCE(round, '')))
        DO NOTHING
        """,
        [
            tuple(g[c] for c in GAMES_COLUMNS) + (g["league"], g["variant"])
            for g in games_rows
        ],
    )
    print(f"Wrote {len(games_rows)} game rows.")

    execute_values(
        cur,
        """
        INSERT INTO preseason_ratings (league, season, variant, team_id, preseason_elo)
        VALUES %s
        ON CONFLICT (league, season, variant, team_id) DO UPDATE SET
            preseason_elo = EXCLUDED.preseason_elo
        """,
        [
            (p["league"], p["season"], p["variant"], p["team_id"], p["preseason_elo"])
            for p in preseason_rows
        ],
    )
    print(f"Wrote {len(preseason_rows)} preseason rating rows.")

    # `schedule` needs a full sync, not just an insert: unlike `games`
    # (immutable once played), a schedule row's prediction changes every
    # time ratings update, AND rows disappear entirely from the local
    # `schedule` table the moment their game gets a real score (see
    # prune_played_schedule_rows() in db.py). If we only upserted here,
    # an already-played game's last prediction would linger in Supabase
    # forever alongside its now-real result in `games`. So: always
    # delete anything for this league+variant first (even if there are
    # zero upcoming games locally right now - that's a valid state,
    # e.g. end of season, and Supabase should reflect it), then upsert
    # the current set.
    cur.execute(
        "DELETE FROM schedule WHERE league = %s AND variant = %s",
        (league, VARIANT),
    )
    if schedule_rows:
        execute_values(
            cur,
            f"""
            INSERT INTO schedule ({', '.join(SCHEDULE_COLUMNS)})
            VALUES %s
            ON CONFLICT (league, variant, team_id, date, opponent_id, type, (COALESCE(round, '')))
            DO UPDATE SET
                expected_win_pct = EXCLUDED.expected_win_pct,
                days_off = EXCLUDED.days_off,
                opp_days_off = EXCLUDED.opp_days_off,
                rest_diff = EXCLUDED.rest_diff,
                rest_adj = EXCLUDED.rest_adj
            """,
            [tuple(s[c] for c in SCHEDULE_COLUMNS) for s in schedule_rows],
        )
    print(f"Synced {len(schedule_rows)} schedule rows "
          f"({len(schedule_rows) // 2} upcoming game(s)).")

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()

# .env file this script expects for a real (non-dry-run) run:
#
#   SUPABASE_DB_HOST=db.xxxxxxxxxxxx.supabase.co
#   SUPABASE_DB_PORT=5432
#   SUPABASE_DB_NAME=postgres
#   SUPABASE_DB_USER=postgres
#   SUPABASE_DB_PASS=your_new_rotated_password
#
# These come from the Supabase project's connection info — NOT your
# Supabase account login. Load it with `pip install python-dotenv` and
# `from dotenv import load_dotenv; load_dotenv()` at the top of this file
# if you want it read automatically, or just export the variables in your
# shell before running.

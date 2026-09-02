"""SQLite storage for the NFL Elo model.

TEAM IDENTITY MODEL
--------------------
`teams.team_id` is a permanent synthetic ID (e.g. "nfl_0001") assigned
once to a franchise and never changed, regardless of relocations or
rebrands. It carries no meaning of its own - it's just a stable peg for
`games` and `ratings` to reference.

Every human-readable code a franchise has ever played under - including
whatever it currently uses - lives in `team_aliases`, resolved to that
permanent ID via `resolve_team_id`. No single code is privileged as
"the real one." Note: unlike NBA, an NFL franchise's CODE typically does
NOT change across a relocation (Oakland/LA/Las Vegas all play as "OAK") -
aliases here mostly exist for alternate codes used by other data sources
(e.g. nflverse's "LV" for the same franchise Continelo tracks as "OAK").

`team_history` tracks which code/name a franchise used during which
seasons, so you can ask "what was this team called in 1996?" (Houston
Oilers) vs "in 2010?" (Tennessee Titans) even though both are the same
team_id. `teams.team_name` remains a simple current-name fallback for
convenience/older callers.

NFL-SPECIFIC SCHEMA ADDITIONS
------------------------------
- `games`/`schedule` carry `home_code`/`away_code` (the stable NFL
  abbreviation, e.g. "ARI") alongside `home_team`/`away_team` (the
  permanent synthetic team_id). This is so engine.py's conference/
  division lookup can stay pure/DB-free - it reads the code straight
  off the game data instead of needing a database call.
- `ratings` carries `conf_game`/`div_game` (whether this was a
  conference/division matchup) and `t` (ties - football has them,
  basketball doesn't), on top of the same columns NBA/WNBA use.
"""
from __future__ import annotations
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id   TEXT PRIMARY KEY,
    team_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    game_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT NOT NULL,
    season     INTEGER NOT NULL,
    type       TEXT NOT NULL CHECK(type IN ('R','P')),
    round      TEXT,
    home_team  TEXT NOT NULL REFERENCES teams(team_id),
    away_team  TEXT NOT NULL REFERENCES teams(team_id),
    home_code  TEXT NOT NULL,
    away_code  TEXT NOT NULL,
    home_pts   INTEGER NOT NULL,
    away_pts   INTEGER NOT NULL,
    ot         INTEGER NOT NULL DEFAULT 0,
    neutral    INTEGER NOT NULL DEFAULT 0
);

-- A plain UNIQUE constraint treats every NULL `round` as distinct from
-- every other NULL, so regular-season games (round IS NULL) would
-- never be deduplicated. IFNULL(round, 'RS') makes NULLs compare equal
-- to each other for uniqueness purposes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_unique
    ON games(date, home_team, away_team, type, IFNULL(round, 'RS'));

-- Unplayed games live here, NEVER in `games`. This is deliberate: the
-- rating engine (rebuild_ratings) only ever reads from `games`, and
-- has no code path that touches `schedule` at all. A game with no
-- score literally cannot reach the rating math - there's no "0-0
-- tie" failure mode possible, because there's no score column here
-- to default to 0.
CREATE TABLE IF NOT EXISTS schedule (
    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    season      INTEGER NOT NULL,
    type        TEXT NOT NULL CHECK(type IN ('R','P')),
    round       TEXT,
    home_team   TEXT NOT NULL REFERENCES teams(team_id),
    away_team   TEXT NOT NULL REFERENCES teams(team_id),
    home_code   TEXT NOT NULL,
    away_code   TEXT NOT NULL,
    neutral     INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_unique
    ON schedule(date, home_team, away_team, type, IFNULL(round, 'RS'));

CREATE TABLE IF NOT EXISTS ratings (
    game_id       INTEGER NOT NULL REFERENCES games(game_id),
    team          TEXT NOT NULL,
    opponent      TEXT NOT NULL,
    home_away     TEXT NOT NULL,
    date          TEXT NOT NULL,
    season        INTEGER NOT NULL,
    type          TEXT NOT NULL,
    round         TEXT,
    conf_game     INTEGER,
    div_game      INTEGER,
    games_played  INTEGER,
    days_off      INTEGER,
    opp_days_off  INTEGER,
    rest_adj      REAL,
    pre_rate      REAL,
    opp_pre_rate  REAL,
    expected_win  REAL,
    points_for    INTEGER,
    points_against INTEGER,
    ot            INTEGER,
    mov           INTEGER,
    result        REAL,
    accuracy      INTEGER,
    test          REAL,
    brier         REAL,
    mov_mult      REAL,
    po_mult       REAL,
    k             REAL,
    keff          REAL,
    rating_change REAL,
    post_rate     REAL,
    w REAL, l REAL, t REAL, r1w REAL, r1l REAL, r2w REAL, r2l REAL,
    r3w REAL, r3l REAL, fw REAL, fl REAL,
    PRIMARY KEY (game_id, team)
);

CREATE TABLE IF NOT EXISTS params (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every code a franchise has ever used (current or historical, plus
-- alternate codes from other data sources) maps here to its permanent
-- team_id. Loaders resolve raw source-file codes through this table; a
-- code with no alias yet is treated as a brand new franchise (see
-- register_new_team).
CREATE TABLE IF NOT EXISTS team_aliases (
    alias      TEXT PRIMARY KEY,
    team_id    TEXT NOT NULL REFERENCES teams(team_id),
    note       TEXT
);

-- Era-scoped code/name for a franchise, so games display under the
-- name/code the team actually used at the time (e.g. Houston Oilers
-- in 1996, Tennessee Titans in 2010 - same team_id). end_season IS
-- NULL means "still current."
CREATE TABLE IF NOT EXISTS team_history (
    team_id      TEXT NOT NULL REFERENCES teams(team_id),
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season   INTEGER,
    PRIMARY KEY (team_id, start_season)
);

-- Forced resets: a team_id that folded and was later revived (same
-- code/brand reused for what is functionally a new franchise) needs
-- its rating wiped back to the base rating at the start of the given
-- season, instead of the normal season-to-season regression from its
-- old final rating. No NFL franchise has needed this historically -
-- kept for schema parity with NBA/WNBA in case one ever does.
CREATE TABLE IF NOT EXISTS franchise_resets (
    team_id TEXT NOT NULL,
    season  INTEGER NOT NULL,
    note    TEXT,
    PRIMARY KEY (team_id, season)
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    return conn


# --------------------------------------------------------------------
# Franchise identity: synthetic IDs, aliases, era-scoped history
# --------------------------------------------------------------------

def next_team_id(conn: sqlite3.Connection) -> str:
    """Generate the next sequential permanent franchise ID, e.g.
    'nfl_0001'. Once assigned, a team_id never changes - relocations
    and rebrands are handled entirely through aliases/team_history."""
    row = conn.execute(
        "SELECT team_id FROM teams WHERE team_id LIKE 'nfl\\_%' ESCAPE '\\' "
        "ORDER BY team_id DESC LIMIT 1"
    ).fetchone()
    n = int(row[0].split("_")[1]) + 1 if row else 1
    return f"nfl_{n:04d}"


def add_alias(conn: sqlite3.Connection, alias: str, team_id: str, note: str = "") -> None:
    """Register that `alias` (a team code as it appears in a source
    file) refers to the same franchise as the existing `team_id`."""
    conn.execute(
        "INSERT INTO team_aliases(alias, team_id, note) VALUES (?, ?, ?) "
        "ON CONFLICT(alias) DO UPDATE SET team_id=excluded.team_id, note=excluded.note",
        (alias, team_id, note),
    )


def resolve_team_id(conn: sqlite3.Connection, code: str) -> str:
    """Translate a raw team code from a source file into its permanent
    team_id, following the registered alias. Returns the code unchanged
    if no alias exists yet (caller should register one first - see
    register_new_team)."""
    row = conn.execute("SELECT team_id FROM team_aliases WHERE alias = ?", (code,)).fetchone()
    return row[0] if row else code


def add_team_history(conn: sqlite3.Connection, team_id: str, code: str, name: str,
                      start_season: int, end_season: Optional[int] = None) -> None:
    conn.execute(
        "INSERT INTO team_history(team_id, code, name, start_season, end_season) "
        "VALUES (?, ?, ?, ?, ?)",
        (team_id, code, name, start_season, end_season),
    )


def close_team_history(conn: sqlite3.Connection, team_id: str, end_season: int) -> None:
    """Close out the currently-open (end_season IS NULL) history row for
    a franchise - call this right before its code/name changes, e.g. a
    relocation or rebrand taking effect."""
    conn.execute(
        "UPDATE team_history SET end_season = ? WHERE team_id = ? AND end_season IS NULL",
        (end_season, team_id),
    )


def register_new_team(conn: sqlite3.Connection, code: str, name: str, start_season: int) -> str:
    """Register a franchise never seen before: mint a permanent
    synthetic team_id, register `code` as its alias, set the current
    display name, and open a team_history row starting this season.
    Returns the new team_id."""
    team_id = next_team_id(conn)
    upsert_team(conn, team_id, name)
    add_alias(conn, code, team_id, note="initial code")
    add_team_history(conn, team_id, code, name, start_season)
    return team_id


def rename_current_history(conn: sqlite3.Connection, team_id: str, name: str) -> bool:
    """Update the name on team_id's currently-open (end_season IS NULL)
    team_history row, for a cosmetic rename that does NOT change its
    code (e.g. fixing a placeholder name after registration). Use
    close_team_history + add_team_history instead for an actual
    relocation/rebrand, which should start a new era.
    Returns True if a row was updated, False if there was no open row
    to update (team predates team_history and needs one opened first)."""
    before = conn.total_changes
    conn.execute(
        "UPDATE team_history SET name = ? WHERE team_id = ? AND end_season IS NULL",
        (name, team_id),
    )
    return conn.total_changes > before


def display_name(conn: sqlite3.Connection, team_id: str, season: int) -> str:
    """The name a franchise went by during `season` - e.g. 'Houston
    Oilers' for a given team_id in 1996, 'Tennessee Titans' for the
    same team_id in 2010. Falls back to teams.team_name if no
    era-specific history row covers that season yet."""
    row = conn.execute(
        "SELECT name FROM team_history WHERE team_id = ? AND start_season <= ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (team_id, season, season),
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute("SELECT team_name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    return row[0] if row else team_id


def add_reset(conn: sqlite3.Connection, team_id: str, season: int, note: str = "") -> None:
    """Force team_id's rating to reset to the base rating at the start
    of `season`, ignoring its actual prior-season history. Use this
    when a folded franchise's brand/code is reused for what is really
    a new team."""
    conn.execute(
        "INSERT INTO franchise_resets(team_id, season, note) VALUES (?, ?, ?) "
        "ON CONFLICT(team_id, season) DO UPDATE SET note=excluded.note",
        (team_id, season, note),
    )


def load_resets(conn: sqlite3.Connection) -> set[tuple[str, int]]:
    rows = conn.execute("SELECT team_id, season FROM franchise_resets").fetchall()
    return {(t, s) for t, s in rows}


PARAMS_FILE = "active_params.json"
# Active (tuned) parameters live in this file, deliberately SEPARATE
# from the database, so deleting/resetting nfl_elo.db can never
# silently wipe out tuning. There's no set_params.py for NFL yet (see
# TEMPLATE.md - it's only worth building while actively tuning); until
# then, retuning means hand-editing BASELINE_PARAMS in engine.py and
# running rebuild.py, or writing to this file directly.


def save_active_params(conn: sqlite3.Connection, params: dict) -> None:
    """Persist the currently-active (possibly tuned) parameter set to
    active_params.json, so it survives between script runs AND survives
    the database being deleted/recreated."""
    import json
    with open(PARAMS_FILE, "w") as f:
        json.dump(params, f, indent=2)


def load_active_params(conn: sqlite3.Connection) -> Optional[dict]:
    """Returns the persisted active parameter set from active_params.json,
    or None if that file doesn't exist (in which case callers should
    fall back to the original baseline). Unlike NBA/WNBA's playoff_mult
    (numeric round keys, which JSON round-trips as strings and need
    restoring), NFL's playoff_round_mult keys are already strings
    ('WC'/'DV'/'CC'/'SB'), so no reparse is needed here."""
    import json
    import os
    if not os.path.exists(PARAMS_FILE):
        return None
    with open(PARAMS_FILE) as f:
        return json.load(f)


SCHEDULE_FILE = "param_schedule.json"
# A per-season override of alpha/kmax/hfa (see nfl_tune_engine.py /
# nfl_reconstruct_engine.py). Deliberately a SEPARATE file from
# active_params.json rather than a new shape inside it, so a system that
# doesn't know about scheduling yet (or a person hand-editing
# active_params.json) can't accidentally desync the two. If this file
# exists, rebuild.py should prefer it over active_params.json and swap
# eng.params at each season boundary; if it doesn't exist, nothing about
# current behavior changes.


def save_param_schedule(conn: sqlite3.Connection, schedule: dict[int, dict]) -> None:
    """Persist a season -> {alpha, kmax, hfa} schedule. `schedule` keys
    are ints (seasons); JSON needs string keys, so this round-trips them
    through str() on save and int() on load."""
    import json
    with open(SCHEDULE_FILE, "w") as f:
        json.dump({str(season): params for season, params in schedule.items()}, f, indent=2)


def load_param_schedule(conn: sqlite3.Connection) -> Optional[dict[int, dict]]:
    """Returns the persisted season -> {alpha, kmax, hfa} schedule, or
    None if no schedule file exists yet (caller should fall back to
    load_active_params()/baseline - see PARAMS_FILE note above)."""
    import json
    import os
    if not os.path.exists(SCHEDULE_FILE):
        return None
    with open(SCHEDULE_FILE) as f:
        raw = json.load(f)
    return {int(season): params for season, params in raw.items()}


def params_for_season(conn: sqlite3.Connection, season: int) -> dict:
    """The single lookup rebuild.py needs at each season boundary: the
    schedule's entry for this season if one exists (merged onto the
    engine baseline, so only alpha/kmax/hfa are overridden and
    everything else - k_floor, rest adjustments, div/conf/playoff
    multipliers - stays at the validated baseline); otherwise the most
    recently locked EARLIER season in the schedule (e.g. an unplayed
    season with a schedule uploaded via add_season.py but not yet
    retuned inherits last season's numbers, not the original stale
    baseline - a season with no games yet and no schedule entry is a
    far more common case than "the schedule file itself is missing",
    and defaulting all the way back to hfa=72/kmax=46 for it would be
    a much worse failure mode than defaulting to last season's already
    -corrected values); otherwise falls back to active_params.json;
    otherwise the engine's own baseline."""
    import engine
    schedule = load_param_schedule(conn)
    base = engine.default_params()
    if schedule:
        if season in schedule:
            base.update({k: v for k, v in schedule[season].items() if k in ("alpha", "kmax", "hfa")})
            return base
        earlier = [s for s in schedule if s < season]
        if earlier:
            nearest = max(earlier)
            base.update({k: v for k, v in schedule[nearest].items() if k in ("alpha", "kmax", "hfa")})
            return base
    active = load_active_params(conn)
    if active:
        base.update({k: v for k, v in active.items() if k in base})
        return base
    return base


def upsert_team(conn: sqlite3.Connection, team_id: str, team_name: str) -> None:
    conn.execute(
        "INSERT INTO teams(team_id, team_name) VALUES (?, ?) "
        "ON CONFLICT(team_id) DO UPDATE SET team_name=excluded.team_name",
        (team_id, team_name),
    )


def add_scheduled_game(conn: sqlite3.Connection, d: date, season: int, type_: str, round_,
                        home_team: str, away_team: str, home_code: str, away_code: str,
                        neutral: int = 0) -> bool:
    """Returns True if a new schedule row was inserted, False if it was
    already there."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO schedule(date, season, type, round, home_team, away_team, "
        "home_code, away_code, neutral) VALUES (?,?,?,?,?,?,?,?,?)",
        (d.isoformat(), season, type_, round_, home_team, away_team, home_code, away_code, neutral),
    )
    return conn.total_changes > before


def upcoming_games(conn: sqlite3.Connection, season: int | None = None) -> list[dict]:
    """Schedule entries that don't yet have a matching row in `games`
    (i.e. games that haven't been played/scored yet)."""
    query = """
        SELECT s.schedule_id, s.date, s.season, s.type, s.round,
               s.home_team, s.away_team, s.home_code, s.away_code, s.neutral
        FROM schedule s
        WHERE NOT EXISTS (
            SELECT 1 FROM games g
            WHERE g.date = s.date AND g.home_team = s.home_team AND g.away_team = s.away_team
              AND g.type = s.type AND IFNULL(g.round, 'RS') = IFNULL(s.round, 'RS')
        )
    """
    params = []
    if season is not None:
        query += " AND s.season = ?"
        params.append(season)
    query += " ORDER BY s.date, s.schedule_id"

    rows = conn.execute(query, params).fetchall()
    cols = ["schedule_id", "date", "season", "type", "round", "home_team", "away_team",
            "home_code", "away_code", "neutral"]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["date"] = datetime.fromisoformat(d["date"]).date()
        out.append(d)
    return out


def prune_played_schedule_rows(conn: sqlite3.Connection) -> int:
    """Delete schedule rows that now have a matching completed game in
    `games` (i.e. the result has come in - the schedule placeholder is
    no longer needed). Returns the number removed."""
    before = conn.total_changes
    conn.execute("""
        DELETE FROM schedule
        WHERE EXISTS (
            SELECT 1 FROM games g
            WHERE g.date = schedule.date AND g.home_team = schedule.home_team
              AND g.away_team = schedule.away_team AND g.type = schedule.type
              AND IFNULL(g.round, 'RS') = IFNULL(schedule.round, 'RS')
        )
    """)
    conn.commit()
    return conn.total_changes - before


def add_game(conn: sqlite3.Connection, d: date, season: int, type_: str, round_,
             home_team: str, away_team: str, home_code: str, away_code: str,
             home_pts: int, away_pts: int, ot: int = 0, neutral: int = 0) -> bool:
    """Returns True if a new row was inserted, False if it was a duplicate
    (matched on date, home_team, away_team, type, and round) and ignored."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO games(date, season, type, round, home_team, away_team, "
        "home_code, away_code, home_pts, away_pts, ot, neutral) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (d.isoformat(), season, type_, round_, home_team, away_team, home_code, away_code,
         home_pts, away_pts, ot, neutral),
    )
    return conn.total_changes > before


def load_games(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        "SELECT game_id, date, season, type, round, home_team, away_team, "
        "home_code, away_code, home_pts, away_pts, ot, neutral FROM games ORDER BY date, game_id"
    )
    out = []
    for row in cur.fetchall():
        gid, d, season, type_, round_, home, away, home_code, away_code, hp, ap, ot, neutral = row
        out.append(dict(
            game_id=gid, date=datetime.fromisoformat(d).date(), season=season,
            type=type_, round=round_, home_team=home, away_team=away,
            home_code=home_code, away_code=away_code,
            home_pts=hp, away_pts=ap, ot=ot, neutral=neutral,
        ))
    return out


def clear_ratings(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM ratings")


def save_ratings(conn: sqlite3.Connection, rows: list[dict], game_id_by_row: list[int]) -> None:
    cols = ["game_id", "team", "opponent", "home_away", "date", "season", "type", "round",
            "conf_game", "div_game", "games_played", "days_off", "opp_days_off", "rest_adj",
            "pre_rate", "opp_pre_rate", "expected_win", "points_for", "points_against", "ot",
            "mov", "result", "accuracy", "test", "brier", "mov_mult", "po_mult", "k", "keff",
            "rating_change", "post_rate", "w", "l", "t", "r1w", "r1l", "r2w", "r2l", "r3w", "r3l",
            "fw", "fl"]
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO ratings ({','.join(cols)}) VALUES ({placeholders})"
    for gid, r in zip(game_id_by_row, rows):
        r = dict(r)
        r["date"] = r["date"].isoformat()
        conn.execute(sql, [gid] + [r[c] for c in cols[1:]])

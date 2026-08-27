"""
Multi-season schema for the FCS schedule/results database.

One database now covers every season instead of one file per year. Reference
data (team_aliases, team_home_city) is season-independent and shared across
all years - build it once, it just keeps working.
"""
import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    season INTEGER,
    team_name TEXT,
    conference TEXT,
    wins INTEGER,
    losses INTEGER,
    ties INTEGER DEFAULT 0,
    games_played INTEGER,
    has_full_schedule INTEGER DEFAULT 0,
    PRIMARY KEY (season, team_name)
);

CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER,
    team TEXT,
    date TEXT,
    opponent_raw TEXT,
    opponent TEXT,
    opponent_fcs TEXT,          -- canonical FCS opponent name, or NULL if opponent isn't FCS
    location TEXT,               -- home / away / neutral / unresolved
    opp_rank INTEGER,
    non_conf INTEGER DEFAULT 0,
    homecoming INTEGER DEFAULT 0,
    site TEXT,
    result TEXT,                 -- display string, e.g. "W 35-14"
    wl TEXT,                     -- W / L / T
    team_score INTEGER,
    opp_score INTEGER,
    ot TEXT,
    attendance TEXT,
    source TEXT,                 -- provenance note - which file/screenshot/site this came from
    FOREIGN KEY (season, team) REFERENCES teams(season, team_name)
);

-- Season-independent reference data. Add to these once; every season benefits.
CREATE TABLE IF NOT EXISTS team_aliases (
    alias TEXT PRIMARY KEY,      -- name variant as it appears in some source
    canonical_name TEXT          -- the name used in teams.team_name
);

CREATE TABLE IF NOT EXISTS team_home_city (
    team_name TEXT PRIMARY KEY,
    city TEXT
);

-- Staging area: every new source lands here first, gets cross-checked against
-- `games` (and other staged sources) for the same season, THEN gets promoted.
CREATE TABLE IF NOT EXISTS staging_games (
    staging_id INTEGER PRIMARY KEY AUTOINCREMENT,
    season INTEGER,
    source TEXT,
    team TEXT,
    date TEXT,
    opponent_raw TEXT,
    opponent_fcs TEXT,
    result TEXT,
    team_score INTEGER,
    opponent_score INTEGER,
    site_location TEXT,
    home_away_neutral TEXT,
    notes TEXT,
    already_in_verified INTEGER DEFAULT 0,
    conflicts_with_verified INTEGER DEFAULT 0,
    promoted INTEGER DEFAULT 0
);

DROP VIEW IF EXISTS team_completion;
CREATE VIEW team_completion AS
WITH all_team_games AS (
    SELECT season, team AS the_team, date, COALESCE(opponent_fcs, opponent) AS other_side
    FROM games WHERE wl IS NOT NULL
    UNION
    SELECT season, opponent_fcs AS the_team, date, team AS other_side
    FROM games WHERE wl IS NOT NULL AND opponent_fcs IS NOT NULL
)
SELECT
    t.season,
    t.team_name,
    t.games_played AS expected_games,
    COUNT(DISTINCT atg.date || '|' || atg.other_side) AS games_filled
FROM teams t
LEFT JOIN all_team_games atg ON atg.the_team = t.team_name AND atg.season = t.season
GROUP BY t.season, t.team_name;

DROP VIEW IF EXISTS still_needs_filling;
CREATE VIEW still_needs_filling AS
SELECT season, team_name, expected_games, games_filled,
       expected_games - games_filled AS games_remaining
FROM team_completion
WHERE expected_games - games_filled > 0
ORDER BY season, games_remaining DESC, team_name;
"""


def init_db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    con.commit()
    return con


def migrate_legacy_1996_db(new_path, legacy_path, season=1996):
    """One-time helper: import the already-finished fcs_1996.db (single-season
    schema) into the new multi-season schema, so 1996 doesn't have to be rebuilt."""
    con = init_db(new_path)
    cur = con.cursor()
    legacy = sqlite3.connect(legacy_path)
    lcur = legacy.cursor()

    teams = lcur.execute(
        "SELECT team_name, conference, wins, losses, games_played, has_full_schedule FROM teams"
    ).fetchall()
    cur.executemany(
        "INSERT OR REPLACE INTO teams (season, team_name, conference, wins, losses, games_played, has_full_schedule) "
        "VALUES (?,?,?,?,?,?,?)",
        [(season, *t) for t in teams],
    )

    games = lcur.execute("""
        SELECT team, date, opponent_raw, opponent, opponent_fcs, location, opp_rank,
               non_conf, homecoming, site, result, wl, team_score, opp_score, ot, attendance, source_team_page
        FROM games
    """).fetchall()
    cur.executemany(
        "INSERT INTO games (season, team, date, opponent_raw, opponent, opponent_fcs, location, opp_rank, "
        "non_conf, homecoming, site, result, wl, team_score, opp_score, ot, attendance, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(season, *g) for g in games],
    )
    con.commit()
    legacy.close()
    return con

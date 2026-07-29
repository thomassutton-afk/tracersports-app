-- ============================================================================
-- TRACER — Fresh Multi-Sport Schema
-- sport = 'basketball' | 'football' | ...   league = 'nba' | 'wnba' | 'nfl' | ...
-- Every team-referencing table is keyed by (league, team_id), since team_id
-- values are NOT globally unique (e.g. "NY" exists in both NBA and WNBA).
-- ============================================================================

CREATE TABLE IF NOT EXISTS teams (
    league       TEXT NOT NULL,
    team_id      TEXT NOT NULL,
    sport        TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    city         TEXT NOT NULL,
    nickname     TEXT NOT NULL,
    conference   TEXT,              -- nullable: some sports/leagues don't use conferences
    division     TEXT,              -- nullable: e.g. WNBA has none
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (league, team_id)
);

CREATE TABLE IF NOT EXISTS seasons (
    league      TEXT NOT NULL,
    season      INTEGER NOT NULL,
    variant     TEXT NOT NULL,
    start_date  DATE,
    end_date    DATE,
    PRIMARY KEY (league, season, variant)
);

CREATE TABLE IF NOT EXISTS preseason_ratings (
    league         TEXT NOT NULL,
    season         INTEGER NOT NULL,
    variant        TEXT NOT NULL,
    team_id        TEXT NOT NULL,
    preseason_elo  FLOAT NOT NULL,
    PRIMARY KEY (league, season, variant, team_id),
    FOREIGN KEY (league, team_id) REFERENCES teams(league, team_id)
);

CREATE TABLE IF NOT EXISTS games (
    game_id             TEXT    NOT NULL,
    league              TEXT    NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL,
    date                DATE    NOT NULL,
    season              INTEGER NOT NULL,
    type                TEXT    NOT NULL,
    round               TEXT    NOT NULL,
    opponent_id         TEXT    NOT NULL,
    home_away           TEXT    NOT NULL,
    points_for          INTEGER NOT NULL,
    points_against      INTEGER NOT NULL,
    ot                  INTEGER NOT NULL DEFAULT 0,
    days_off            INTEGER,
    opp_days_off        INTEGER,
    rest_diff           INTEGER,
    rest_adj            FLOAT,
    pre_gm_rate         FLOAT,
    opp_pre_gm_rate     FLOAT,
    expected_win_pct    FLOAT,
    mov                 INTEGER,
    result              FLOAT,
    accuracy            INTEGER,
    brier               FLOAT,
    mov_mult            FLOAT,
    games_played        INTEGER,
    k                   FLOAT,
    po_mult             FLOAT,
    k_eff               FLOAT,
    rating_change       FLOAT,
    post_gm_rate        FLOAT,
    w                   INTEGER DEFAULT 0,
    l                   INTEGER DEFAULT 0,
    r1w INTEGER DEFAULT 0, r1l INTEGER DEFAULT 0,
    r2w INTEGER DEFAULT 0, r2l INTEGER DEFAULT 0,
    r3w INTEGER DEFAULT 0, r3l INTEGER DEFAULT 0,
    fw  INTEGER DEFAULT 0, fl  INTEGER DEFAULT 0,
    PRIMARY KEY (game_id, league, variant, team_id),
    FOREIGN KEY (league, team_id)     REFERENCES teams(league, team_id),
    FOREIGN KEY (league, opponent_id) REFERENCES teams(league, team_id)
);

CREATE TABLE IF NOT EXISTS standings (
    league              TEXT    NOT NULL,
    season              INTEGER NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL,
    rs_wins             INTEGER DEFAULT 0,
    rs_losses           INTEGER DEFAULT 0,
    rs_end_rating       FLOAT,
    po_r1_wins          INTEGER DEFAULT 0,
    po_r1_losses        INTEGER DEFAULT 0,
    po_r2_wins          INTEGER DEFAULT 0,
    po_r2_losses        INTEGER DEFAULT 0,
    po_r3_wins          INTEGER DEFAULT 0,
    po_r3_losses        INTEGER DEFAULT 0,
    po_finals_wins      INTEGER DEFAULT 0,
    po_finals_losses    INTEGER DEFAULT 0,
    po_end_rating       FLOAT,
    is_rs_champ         BOOLEAN DEFAULT FALSE,
    is_conf_champ       BOOLEAN DEFAULT FALSE,
    is_div_champ        BOOLEAN DEFAULT FALSE,
    is_champion          BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (league, season, variant, team_id),
    FOREIGN KEY (league, team_id) REFERENCES teams(league, team_id)
);

CREATE INDEX IF NOT EXISTS idx_games_league_season_variant     ON games (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_standings_league_season_variant ON standings (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_preseason_league_season_variant ON preseason_ratings (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_teams_sport                     ON teams (sport);

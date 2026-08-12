"""
ContinElo Phase 2 — Step 1: Create Database Tables
Run this once to set up the schema in Supabase.

Usage:
    python create_tables.py
"""

import os
import psycopg2

# -------------------------------------------------------------------
# CONNECTION — fill in your password here, do not share this file
# -------------------------------------------------------------------
DB_HOST = "aws-1-us-west-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.fhummqxfssfctswzkajj"
DB_PASS = os.environ.get("DB_PASS")
# -------------------------------------------------------------------

CREATE_TABLES_SQL = """

-- Teams: one row per franchise, stable across relocations
CREATE TABLE IF NOT EXISTS teams (
    team_id     TEXT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    city        TEXT NOT NULL,
    nickname    TEXT NOT NULL,
    conference  TEXT NOT NULL,
    division    TEXT NOT NULL
);

-- Seasons: one row per season per variant
CREATE TABLE IF NOT EXISTS seasons (
    season      INTEGER NOT NULL,
    variant     TEXT    NOT NULL,
    start_date  DATE,
    end_date    DATE,
    PRIMARY KEY (season, variant)
);

-- Preseason ratings: the previous season's end rating for each team
-- (used to compute the first game's PreGmRate)
CREATE TABLE IF NOT EXISTS preseason_ratings (
    season          INTEGER NOT NULL,
    variant         TEXT    NOT NULL,
    team_id         TEXT    NOT NULL REFERENCES teams(team_id),
    preseason_elo   FLOAT   NOT NULL,
    PRIMARY KEY (season, variant, team_id)
);

-- Games: one row per team per game per variant (4 rows per physical game)
CREATE TABLE IF NOT EXISTS games (
    game_id             TEXT    NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL REFERENCES teams(team_id),
    date                DATE    NOT NULL,
    season              INTEGER NOT NULL,
    type                TEXT    NOT NULL,
    round               TEXT    NOT NULL,
    opponent_id         TEXT    NOT NULL REFERENCES teams(team_id),
    home_away           TEXT    NOT NULL,
    points_for          INTEGER NOT NULL,
    points_against      INTEGER NOT NULL,
    ot                  INTEGER NOT NULL,
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
    r1w                 INTEGER DEFAULT 0,
    r1l                 INTEGER DEFAULT 0,
    r2w                 INTEGER DEFAULT 0,
    r2l                 INTEGER DEFAULT 0,
    r3w                 INTEGER DEFAULT 0,
    r3l                 INTEGER DEFAULT 0,
    fw                  INTEGER DEFAULT 0,
    fl                  INTEGER DEFAULT 0,
    PRIMARY KEY (game_id, variant, team_id)
);

-- Standings: aggregated per team per season per variant
CREATE TABLE IF NOT EXISTS standings (
    season              INTEGER NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL REFERENCES teams(team_id),
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
    is_champion         BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (season, variant, team_id)
);

"""

def main():
    print("Connecting to database...")
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    conn.autocommit = True
    cur = conn.cursor()

    print("Creating tables...")
    cur.execute(CREATE_TABLES_SQL)

    # Verify tables exist
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"\nTables in database: {tables}")

    expected = {"games", "preseason_ratings", "seasons", "standings", "teams"}
    missing = expected - set(tables)
    if missing:
        print(f"\n❌ Missing tables: {missing}")
    else:
        print("\n✅ All tables created successfully.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()

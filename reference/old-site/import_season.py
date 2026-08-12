"""
ContinElo Phase 2 — Step 2: Seed Teams + Import 2024-25 Season
Run after create_tables.py.

Usage:
    python import_season.py "NBA Continelo V2 2025.xlsx"
"""

import os
import sys
import psycopg2
import psycopg2.extras
import pandas as pd
from continelo_engine import (
    ContinEloEngine, load_preseason_ratings_from_excel, MANUAL_COLS
)

# -------------------------------------------------------------------
# CONNECTION — fill in your password here, do not share this file
# -------------------------------------------------------------------
DB_HOST = "aws-1-us-west-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.fhummqxfssfctswzkajj"
DB_PASS = os.environ.get("DB_PASS")
# -------------------------------------------------------------------

TEAMS = [
    ("ATL", "Atlanta Hawks",            "Atlanta",       "Hawks",        "East", "Southeast"),
    ("BOS", "Boston Celtics",           "Boston",        "Celtics",      "East", "Atlantic"),
    ("BRK", "Brooklyn Nets",            "Brooklyn",      "Nets",         "East", "Atlantic"),
    ("CHA", "Charlotte Hornets",        "Charlotte",     "Hornets",      "East", "Southeast"),
    ("CHI", "Chicago Bulls",            "Chicago",       "Bulls",        "East", "Central"),
    ("CLE", "Cleveland Cavaliers",      "Cleveland",     "Cavaliers",    "East", "Central"),
    ("DAL", "Dallas Mavericks",         "Dallas",        "Mavericks",    "West", "Southwest"),
    ("DEN", "Denver Nuggets",           "Denver",        "Nuggets",      "West", "Northwest"),
    ("DET", "Detroit Pistons",          "Detroit",       "Pistons",      "East", "Central"),
    ("GS",  "Golden State Warriors",    "San Francisco", "Warriors",     "West", "Pacific"),
    ("HOU", "Houston Rockets",          "Houston",       "Rockets",      "West", "Southwest"),
    ("IND", "Indiana Pacers",           "Indianapolis",  "Pacers",       "East", "Central"),
    ("LAC", "LA Clippers",              "Los Angeles",   "Clippers",     "West", "Pacific"),
    ("LAL", "Los Angeles Lakers",       "Los Angeles",   "Lakers",       "West", "Pacific"),
    ("MEM", "Memphis Grizzlies",        "Memphis",       "Grizzlies",    "West", "Southwest"),
    ("MIA", "Miami Heat",               "Miami",         "Heat",         "East", "Southeast"),
    ("MIL", "Milwaukee Bucks",          "Milwaukee",     "Bucks",        "East", "Central"),
    ("MIN", "Minnesota Timberwolves",   "Minneapolis",   "Timberwolves", "West", "Northwest"),
    ("NO",  "New Orleans Pelicans",     "New Orleans",   "Pelicans",     "West", "Southwest"),
    ("NY",  "New York Knicks",          "New York",      "Knicks",       "East", "Atlantic"),
    ("OKC", "Oklahoma City Thunder",    "Oklahoma City", "Thunder",      "West", "Northwest"),
    ("ORL", "Orlando Magic",            "Orlando",       "Magic",        "East", "Southeast"),
    ("PHI", "Philadelphia 76ers",       "Philadelphia",  "76ers",        "East", "Atlantic"),
    ("PHX", "Phoenix Suns",             "Phoenix",       "Suns",         "West", "Pacific"),
    ("POR", "Portland Trail Blazers",   "Portland",      "Trail Blazers","West", "Northwest"),
    ("SA",  "San Antonio Spurs",        "San Antonio",   "Spurs",        "West", "Southwest"),
    ("SAC", "Sacramento Kings",         "Sacramento",    "Kings",        "West", "Pacific"),
    ("TOR", "Toronto Raptors",          "Toronto",       "Raptors",      "East", "Atlantic"),
    ("UTA", "Utah Jazz",                "Salt Lake City","Jazz",         "West", "Northwest"),
    ("WAS", "Washington Wizards",       "Washington",    "Wizards",      "East", "Southeast"),
]


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )


def seed_teams(cur):
    print("Seeding teams...")
    psycopg2.extras.execute_values(cur, """
        INSERT INTO teams (team_id, full_name, city, nickname, conference, division)
        VALUES %s
        ON CONFLICT (team_id) DO NOTHING
    """, TEAMS)
    cur.execute("SELECT COUNT(*) FROM teams")
    print(f"  Teams in database: {cur.fetchone()[0]}")


def import_season(cur, xlsx_path, variant="continelo"):
    print(f"\nImporting 2024-25 season ({variant})...")

    excel_df    = pd.read_excel(xlsx_path, sheet_name="RawData")
    if variant == "elo":
        preseason = {team: 1500.0 for team in [
            "ATL","BOS","BRK","CHA","CHI","CLE","DAL","DEN","DET","GS",
            "HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NO","NY",
            "OKC","ORL","PHI","PHX","POR","SA","SAC","TOR","UTA","WAS"
        ]}
    else:
        preseason = load_preseason_ratings_from_excel(xlsx_path)
    manual_df   = excel_df[MANUAL_COLS].copy()
    manual_df = manual_df.dropna(subset=["PointsFor", "PointsAgainst"]).copy()

    engine      = ContinEloEngine(variant=variant)
    calc_df     = engine.process_season(manual_df, preseason)

    # Build rows for the games table
    rows = []
    for idx, row in calc_df.iterrows():
        # Generate a stable game_id from date + teams (no NBA API id yet)
        date_str = str(row["Date"].date()).replace("-", "")
        teams_sorted = "_".join(sorted([str(row["Team"]), str(row["Opponent"])]))
        game_id = f"{date_str}_{teams_sorted}"

        rows.append((
            game_id,
            variant,
            str(row["Team"]),
            row["Date"].date(),
            int(row["Season"]),
            str(row["Type"]),
            str(row["Round"]),
            str(row["Opponent"]),
            str(row["HomeAway"]),
            int(row["PointsFor"]),
            int(row["PointsAgainst"]),
            int(row["OT"]),
            int(row["DaysOff"]),
            int(row["OppDaysOff"]),
            int(row["RestDiff"]),
            float(row["RestAdj"]),
            float(row["PreGmRate"]),
            float(row["OppPreGmRate"]),
            float(row["ExpectedWin%"]),
            int(row["MOV"]),
            float(row["Result"]),
            int(row["Accuracy"]),
            float(row["Brier"]),
            float(row["MOVMult"]),
            int(row["GamesPlayed"]),
            float(row["K"]),
            float(row["POMult"]),
            float(row["Keff"]),
            float(row["RatingChange"]),
            float(row["PostGmRate"]),
            int(row["W"]),
            int(row["L"]),
            int(row["R1W"]),
            int(row["R1L"]),
            int(row["R2W"]),
            int(row["R2L"]),
            int(row["R3W"]),
            int(row["R3L"]),
            int(row["FW"]),
            int(row["FL"]),
        ))

    psycopg2.extras.execute_values(cur, """
        INSERT INTO games (
            game_id, variant, team_id, date, season, type, round,
            opponent_id, home_away, points_for, points_against, ot,
            days_off, opp_days_off, rest_diff, rest_adj,
            pre_gm_rate, opp_pre_gm_rate, expected_win_pct,
            mov, result, accuracy, brier, mov_mult,
            games_played, k, po_mult, k_eff, rating_change, post_gm_rate,
            w, l, r1w, r1l, r2w, r2l, r3w, r3l, fw, fl
        ) VALUES %s
        ON CONFLICT (game_id, variant, team_id) DO NOTHING
    """, rows)

    print(f"  Inserted {len(rows)} rows.")

    # Insert preseason ratings
    preseason_rows = [
        (2026, variant, team, float(rating))
        for team, rating in preseason.items()
    ]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO preseason_ratings (season, variant, team_id, preseason_elo)
        VALUES %s
        ON CONFLICT DO NOTHING
    """, preseason_rows)
    print(f"  Inserted {len(preseason_rows)} preseason ratings.")

    # Insert season record
    cur.execute("""
        INSERT INTO seasons (season, variant, start_date, end_date)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (
        2026, variant,
        calc_df["Date"].min().date(),
        calc_df["Date"].max().date(),
    ))


def verify(cur):
    print("\nVerification:")
    cur.execute("SELECT COUNT(*) FROM games WHERE season = 2025")
    n = cur.fetchone()[0]
    print(f"  Game rows for 2025: {n}  (expected 2642 for continelo)")

    cur.execute("""
        SELECT team_id, ROUND(MAX(post_gm_rate)::numeric, 2) as peak_rating
        FROM games WHERE season = 2025 AND variant = 'continelo'
        GROUP BY team_id ORDER BY peak_rating DESC LIMIT 5
    """)
    print("\n  Top 5 peak ratings this season:")
    for team, rating in cur.fetchall():
        print(f"    {team}: {rating}")

    cur.execute("""
        SELECT team_id, SUM(w) as wins, SUM(l) as losses
        FROM games WHERE season = 2025 AND variant = 'continelo'
        GROUP BY team_id ORDER BY wins DESC LIMIT 5
    """)
    print("\n  Top 5 teams by wins:")
    for team, w, l in cur.fetchall():
        print(f"    {team}: {w}-{l}")


def main():
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "NBA Continelo V2 2025.xlsx"

    conn = get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        seed_teams(cur)
        import_season(cur, xlsx_path, variant="elo")
        conn.commit()
        verify(cur)
        print("\n✅ Import complete.")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

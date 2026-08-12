"""
ContinElo Phase 2 — Step 3: Bulk Historical Import
Imports all 62 Excel files (31 seasons x 2 variants) into the database.

Usage:
    python import_all.py
"""

import os
import psycopg2
import psycopg2.extras
import pandas as pd
from continelo_engine import (
    ContinEloEngine, load_preseason_ratings_from_excel,
    MANUAL_COLS, BASE, preseason_rating
)

# -------------------------------------------------------------------
# CONNECTION
# -------------------------------------------------------------------
DB_HOST = "aws-1-us-west-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.fhummqxfssfctswzkajj"
DB_PASS = os.environ.get("DB_PASS")
# -------------------------------------------------------------------

# Folders containing the Excel files (relative to this script)
CONTINELO_FOLDER = "ContinElo"
ELO_FOLDER       = "ELO"
SEASONS          = range(2026, 2027)  # 1996 through 2026 inclusive


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )


def load_preseason_elo(xlsx_path, variant):
    """
    Load preseason ratings from the DataTable sheet.
    For continelo: applies 0.6 * prev_end + 0.4 * 1500 formula.
    For elo: always returns 1500 for every team.
    """
    if variant == "elo":
        # Elo files may not have PreSeasonElo column — always 1500
        try:
            df = pd.read_excel(xlsx_path, sheet_name="DataTable")
            teams = df["TeamID"].tolist()
            return {team: BASE for team in teams}
        except Exception:
            # Fallback: use standard 30 teams
            return {t: BASE for t in TEAMS_30}

    # ContinElo: read prev_end from DataTable and apply formula
    return load_preseason_ratings_from_excel(xlsx_path)


def import_file(cur, xlsx_path, season, variant):
    """Import one Excel file into the games and related tables."""

    excel_df = pd.read_excel(xlsx_path, sheet_name="RawData")

    # Keep only the manual columns that exist in this file
    cols_present = [c for c in MANUAL_COLS if c in excel_df.columns]
    manual_df = excel_df[cols_present].copy()

    # Drop rows with no score — future unplayed games
    manual_df = manual_df.dropna(subset=["PointsFor", "PointsAgainst"]).copy()

    # If Season column is missing, fill it in
    if "Season" not in manual_df.columns:
        manual_df["Season"] = season

    preseason = load_preseason_elo(xlsx_path, variant)

    engine    = ContinEloEngine(variant=variant)
    calc_df   = engine.process_season(manual_df, preseason)

    # --- Games rows ---
    rows = []
    for _, row in calc_df.iterrows():
        date_str     = str(row["Date"].date()).replace("-", "")
        teams_sorted = "_".join(sorted([str(row["Team"]), str(row["Opponent"])]))
        game_id      = f"{date_str}_{teams_sorted}"

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
        ON CONFLICT (game_id, variant, team_id) DO UPDATE SET
            pre_gm_rate      = EXCLUDED.pre_gm_rate,
            post_gm_rate     = EXCLUDED.post_gm_rate,
            rating_change    = EXCLUDED.rating_change,
            expected_win_pct = EXCLUDED.expected_win_pct,
            accuracy         = EXCLUDED.accuracy,
            brier            = EXCLUDED.brier
    """, rows)

    # --- Preseason ratings ---
    preseason_rows = [
        (season, variant, team, float(rating))
        for team, rating in preseason.items()
    ]
    psycopg2.extras.execute_values(cur, """
        INSERT INTO preseason_ratings (season, variant, team_id, preseason_elo)
        VALUES %s
        ON CONFLICT (season, variant, team_id) DO UPDATE SET
            preseason_elo = EXCLUDED.preseason_elo
    """, preseason_rows)

    # --- Season record ---
    cur.execute("""
        INSERT INTO seasons (season, variant, start_date, end_date)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (season, variant) DO UPDATE SET
            start_date = EXCLUDED.start_date,
            end_date   = EXCLUDED.end_date
    """, (
        season, variant,
        calc_df["Date"].min().date(),
        calc_df["Date"].max().date(),
    ))

    return len(rows)


# Fallback team list if DataTable sheet is unreadable
TEAMS_30 = [
    "ATL","BOS","BRK","CHA","CHI","CLE","DAL","DEN","DET","GS",
    "HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NO","NY",
    "OKC","ORL","PHI","PHX","POR","SA","SAC","TOR","UTA","WAS"
]


def main():
    conn = get_connection()
    conn.autocommit = False
    cur  = conn.cursor()

    total_rows    = 0
    files_ok      = 0
    files_failed  = 0

    jobs = (
        [(season, "continelo", os.path.join(CONTINELO_FOLDER, f"NBA Continelo V2 {season}.xlsx"))
         for season in SEASONS]
        +
        [(season, "elo", os.path.join(ELO_FOLDER, f"NBA ELO V2 {season}.xlsx"))
         for season in SEASONS]
    )

    print(f"Starting bulk import: {len(jobs)} files\n")

    for season, variant, path in jobs:
        if not os.path.exists(path):
            print(f"  ⚠️  NOT FOUND: {path}")
            files_failed += 1
            continue

        try:
            n = import_file(cur, path, season, variant)
            conn.commit()
            total_rows += n
            files_ok   += 1
            print(f"  ✅  {variant:10s} {season}  —  {n} rows")
        except Exception as e:
            conn.rollback()
            files_failed += 1
            print(f"  ❌  {variant:10s} {season}  —  ERROR: {e}")

    cur.close()
    conn.close()

    print(f"\n{'='*50}")
    print(f"Files imported:  {files_ok}")
    print(f"Files failed:    {files_failed}")
    print(f"Total rows:      {total_rows:,}")
    print(f"{'='*50}")

    if files_failed == 0:
        print("\n✅ Bulk import complete — all files imported successfully.")
    else:
        print(f"\n⚠️  {files_failed} file(s) had issues — check the errors above.")


if __name__ == "__main__":
    main()

"""
ContinElo Phase 3 — Live Pipeline
Fetches newly completed NBA games, calculates ratings, and writes to the database.

Run manually or via Windows Task Scheduler every 10 minutes.

Usage:
    python pipeline.py
"""

import os
import time
import logging
import requests
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import date, timedelta

from continelo_engine import (
    ContinEloEngine, BASE, preseason_rating,
    rest_adj, k_factor, po_mult, mov_mult,
    expected_win_pct, rating_change, accuracy, brier
)

def get_ot_status(game_id: str) -> int:
    """Returns 1 if game went to OT, 0 if regulation."""
    try:
        time.sleep(0.6)
        from nba_api.stats.endpoints import boxscoresummaryv2
        summary = boxscoresummaryv2.BoxScoreSummaryV2(game_id=game_id)
        line_score = summary.get_data_frames()[6]
        ot_cols = [c for c in line_score.columns if c.startswith('PT_OT')]
        for col in ot_cols:
            if line_score[col].sum() > 0:
                return 1
        return 0
    except Exception as e:
        log.warning(f"  Could not get OT status for {game_id}: {e}")
        return 0

# -------------------------------------------------------------------
# CONNECTION
# -------------------------------------------------------------------
DB_HOST = "aws-1-us-west-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.fhummqxfssfctswzkajj"
DB_PASS = os.environ.get("DB_PASS")
# -------------------------------------------------------------------

CURRENT_SEASON     = 2026
CURRENT_SEASON_STR = "2025-26"

IST_FINALS = {
    "0022401239": 2025,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Database helpers
# -------------------------------------------------------------------

def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )


def get_last_game_date(cur, season, variant):
    cur.execute("""
        SELECT MAX(date) FROM games
        WHERE season = %s AND variant = %s
    """, (season, variant))
    return cur.fetchone()[0]


def get_team_current_rating(cur, team_id, season, variant):
    cur.execute("""
        SELECT post_gm_rate FROM games
        WHERE team_id = %s AND season = %s AND variant = %s
        ORDER BY date DESC, games_played DESC
        LIMIT 1
    """, (team_id, season, variant))
    row = cur.fetchone()
    if row:
        return float(row[0])
    cur.execute("""
        SELECT preseason_elo FROM preseason_ratings
        WHERE team_id = %s AND season = %s AND variant = %s
    """, (team_id, season, variant))
    row = cur.fetchone()
    if row:
        prev_end = float(row[0])
        return preseason_rating(prev_end, variant)
    return BASE


def get_team_last_game_date(cur, team_id, season, variant):
    cur.execute("""
        SELECT MAX(date) FROM games
        WHERE team_id = %s AND season = %s AND variant = %s
    """, (team_id, season, variant))
    row = cur.fetchone()
    return row[0] if row else None


def get_team_games_played(cur, team_id, season, variant):
    cur.execute("""
        SELECT COUNT(*) FROM games
        WHERE team_id = %s AND season = %s AND variant = %s
    """, (team_id, season, variant))
    return cur.fetchone()[0]


def get_season_start_date(cur, season, variant):
    cur.execute("""
        SELECT MIN(date) FROM games
        WHERE season = %s AND variant = %s
    """, (season, variant))
    row = cur.fetchone()
    return row[0] if row else None


# -------------------------------------------------------------------
# Game ID parsing
# -------------------------------------------------------------------

def parse_game_id(game_id: str):
    if game_id in IST_FINALS:
        return "P", "INS"

    prefix = game_id[:3]

    if prefix == "002":
        return "R", "RS"
    elif prefix == "005":
        return "P", 0.5
    elif prefix == "004":
        round_num = int(game_id[6:8])
        return "P", round_num
    else:
        return None, None


# -------------------------------------------------------------------
# NBA API fetching
# -------------------------------------------------------------------

def fetch_completed_games(since_date: date, season_str: str):
    log.info(f"Fetching games since {since_date} for season {season_str}...")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.nba.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://www.nba.com',
        'Connection': 'keep-alive',
        'x-nba-stats-origin': 'stats',
        'x-nba-stats-token': 'true',
    }

    all_rows = []

    for season_type in ["Regular+Season", "Playoffs", "PlayIn"]:
        try:
            time.sleep(1)
            url = (
                f"https://stats.nba.com/stats/leaguegamelog"
                f"?Counter=0&DateFrom=&DateTo=&Direction=DESC"
                f"&ISTRound=&LeagueID=00&PlayerOrTeam=T"
                f"&Season={season_str}&SeasonType={season_type}&Sorter=DATE"
            )
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            headers_row = data['resultSets'][0]['headers']
            rows = data['resultSets'][0]['rowSet']
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=headers_row)
            df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"]).dt.date
            df = df[df["GAME_DATE"] > since_date]
            if not df.empty:
                all_rows.append(df)
        except Exception as e:
            log.warning(f"  Could not fetch {season_type}: {e}")

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True)


# -------------------------------------------------------------------
# Team abbreviation mapping
# -------------------------------------------------------------------

NBA_API_TO_CONTINELO = {
    "NOP": "NO",
    "NYK": "NY",
    "GSW": "GS",
    "SAS": "SA",
    "UTA": "UTA",
    "BKN": "BRK",
    "CHA": "CHA",
}

def normalize_team(abbr: str) -> str:
    return NBA_API_TO_CONTINELO.get(abbr, abbr)


# -------------------------------------------------------------------
# Core processing
# -------------------------------------------------------------------

def process_new_games(cur, games_df: pd.DataFrame, season: int, variant: str):
    if games_df.empty:
        return 0

    games_df = games_df.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)

    game_ids = games_df["GAME_ID"].unique()
    inserted = 0

    season_start = get_season_start_date(cur, season, variant)

    for game_id in game_ids:
        pair = games_df[games_df["GAME_ID"] == game_id]
        if len(pair) != 2:
            log.warning(f"  Game {game_id} has {len(pair)} rows, expected 2 — skipping")
            continue

        game_type, round_val = parse_game_id(game_id)
        if game_type is None:
            log.info(f"  Skipping non-regular game {game_id}")
            continue

        game_date = pair.iloc[0]["GAME_DATE"]

        rows = {}
        for _, r in pair.iterrows():
            ha = "H" if r["MATCHUP"].find("vs.") != -1 else "A"
            rows[ha] = r

        if "H" not in rows or "A" not in rows:
            log.warning(f"  Could not determine home/away for {game_id} — skipping")
            continue

        home_row = rows["H"]
        away_row = rows["A"]

        home_team = normalize_team(home_row["TEAM_ABBREVIATION"])
        away_team = normalize_team(away_row["TEAM_ABBREVIATION"])

        home_pf = int(home_row["PTS"])
        away_pf = int(away_row["PTS"])

        ot = get_ot_status(game_id)

        pre_home   = get_team_current_rating(cur, home_team, season, variant)
        pre_away   = get_team_current_rating(cur, away_team, season, variant)
        last_home  = get_team_last_game_date(cur, home_team, season, variant)
        last_away  = get_team_last_game_date(cur, away_team, season, variant)
        gp_home    = get_team_games_played(cur, home_team, season, variant)
        gp_away    = get_team_games_played(cur, away_team, season, variant)

        for team, opponent, pf, pa, home_away in [
            (home_team, away_team, home_pf, away_pf, "H"),
            (away_team, home_team, away_pf, home_pf, "A"),
        ]:
            pre       = pre_home  if team == home_team else pre_away
            opp_pre   = pre_away  if team == home_team else pre_home
            team_last = last_home if team == home_team else last_away
            opp_last  = last_away if team == home_team else last_home
            gp        = (gp_home  if team == home_team else gp_away) + 1

            if team_last:
                days_off = (game_date - team_last).days - 1
            elif season_start:
                days_off = (game_date - season_start).days
            else:
                days_off = 3

            if opp_last:
                opp_days_off = (game_date - opp_last).days - 1
            elif season_start:
                opp_days_off = (game_date - season_start).days
            else:
                opp_days_off = 3

            rd   = days_off - opp_days_off
            ord_ = opp_days_off - days_off
            ra   = rest_adj(rd)
            ora  = rest_adj(ord_)

            ewp  = expected_win_pct(pre, opp_pre, ra, ora, home_away)
            mov  = pf - pa
            res  = 1.0 if mov > 0 else (0.0 if mov < 0 else 0.5)
            mm   = mov_mult(pf, pa, pre, opp_pre, ot)
            k    = k_factor(gp)
            pm   = po_mult(round_val)
            ke   = k * pm
            rc   = rating_change(ke, mm, res, ewp)
            post = pre + rc
            acc  = accuracy(ewp, res)
            br   = brier(ewp, res)

            is_rs = (game_type == "R")
            is_po = (game_type == "P")
            try:
                rnd = float(round_val) if round_val not in ("RS", "INS") else None
            except (TypeError, ValueError):
                rnd = None

            w   = int(is_rs and res == 1.0)
            l   = int(is_rs and res == 0.0)
            r1w = int(is_po and rnd == 1 and res == 1.0)
            r1l = int(is_po and rnd == 1 and res == 0.0)
            r2w = int(is_po and rnd == 2 and res == 1.0)
            r2l = int(is_po and rnd == 2 and res == 0.0)
            r3w = int(is_po and rnd == 3 and res == 1.0)
            r3l = int(is_po and rnd == 3 and res == 0.0)
            fw  = int(is_po and rnd == 4 and res == 1.0)
            fl  = int(is_po and rnd == 4 and res == 0.0)

            round_str = str(round_val)

            cur.execute("""
                INSERT INTO games (
                    game_id, variant, team_id, date, season, type, round,
                    opponent_id, home_away, points_for, points_against, ot,
                    days_off, opp_days_off, rest_diff, rest_adj,
                    pre_gm_rate, opp_pre_gm_rate, expected_win_pct,
                    mov, result, accuracy, brier, mov_mult,
                    games_played, k, po_mult, k_eff, rating_change, post_gm_rate,
                    w, l, r1w, r1l, r2w, r2l, r3w, r3l, fw, fl
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                ON CONFLICT (game_id, variant, team_id) DO UPDATE SET
                    post_gm_rate     = EXCLUDED.post_gm_rate,
                    pre_gm_rate      = EXCLUDED.pre_gm_rate,
                    rating_change    = EXCLUDED.rating_change,
                    expected_win_pct = EXCLUDED.expected_win_pct,
                    accuracy         = EXCLUDED.accuracy,
                    brier            = EXCLUDED.brier
            """, (
                game_id, variant, team, game_date, season,
                game_type, round_str, opponent, home_away,
                pf, pa, ot,
                days_off, opp_days_off, rd, ra,
                pre, opp_pre, ewp,
                mov, res, acc, br, mm,
                gp, k, pm, ke, rc, post,
                w, l, r1w, r1l, r2w, r2l, r3w, r3l, fw, fl
            ))

        inserted += 1
        log.info(f"  Processed: {game_id}  {home_team} vs {away_team}  "
                 f"{home_pf}-{away_pf}  ({game_type} {round_val})")

    return inserted


# -------------------------------------------------------------------
# Main pipeline run
# -------------------------------------------------------------------

def run():
    log.info("=== Pipeline run started ===")

    conn = get_connection()
    conn.autocommit = False
    cur  = conn.cursor()

    try:
        total = 0
        for variant in ["continelo", "elo"]:
            last_date = get_last_game_date(cur, CURRENT_SEASON, variant)

            if last_date is None:
                log.warning(f"  No existing data for {variant} {CURRENT_SEASON} — skipping")
                continue

            log.info(f"  {variant}: last game in DB = {last_date}")

            new_games = fetch_completed_games(last_date, CURRENT_SEASON_STR)

            if new_games.empty:
                log.info(f"  {variant}: no new games found")
                continue

            log.info(f"  {variant}: {len(new_games)} new team-game rows found")

            n = process_new_games(cur, new_games, CURRENT_SEASON, variant)
            conn.commit()
            total += n
            log.info(f"  {variant}: {n} games processed and committed")

        if total == 0:
            log.info("No new games — nothing to do.")
        else:
            log.info(f"=== Pipeline complete: {total} new games processed ===")

    except Exception as e:
        conn.rollback()
        log.error(f"Pipeline error: {e}", exc_info=True)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run()
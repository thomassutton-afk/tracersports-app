#!/usr/bin/env python3
"""
run_elo_1996.py

Runs every game in cbb_1996.db (built by build_cbb_db.py) through the Elo
engine from elo_engine.py, and writes two new tables back into the same
database:

    elo_ledger          -- one row per team-per-game (pre/post rating, K,
                            expected win%, everything the workbook tracked)
    elo_final_ratings    -- one row per team, final end-of-season rating

USAGE
-----
    python run_elo_1996.py cbb_1996.db

    # with an optional team -> conference mapping for the conference-game bonus:
    python run_elo_1996.py cbb_1996.db --conferences conferences.csv

conferences.csv (optional) should have two columns: team,conference
matching the exact team names used in your schedules_1996/ filenames.
Without it, the conference-game (x1.15 K) bonus is simply not applied --
every other part of the model (K decay, home court, MOV multiplier,
tournament round scaling, D2 fallback) runs exactly as in the workbook
regardless.

ROUND ASSIGNMENT
-----------------
Your schedule data marks each game's type as REG / CTOURN / NCAA (that's
what sports-reference itself uses), but doesn't give an explicit bracket
round. Since both conference and NCAA tournaments are single-elimination,
a team's Nth tournament game of that type IS round N by definition -- so
round numbers are assigned by counting each team's own CTOURN/NCAA games
in chronological order. This is exact, not a guess.

There's no "EARLY" (early-season multi-team tournament) tier in this era's
data -- sports-reference doesn't separate those from REG in 1995-96
schedule exports, so all non-tournament games are treated as plain
regular season, same as the workbook would if that tier were absent.
"""

import argparse
import csv
import sqlite3
from collections import defaultdict
from pathlib import Path

from elo_engine import EloEngine


def load_games(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    games = cur.execute("""
        SELECT date, game_type, home_team, away_team, neutral_site,
               home_score, away_score, ot
        FROM games
        ORDER BY date
    """).fetchall()
    teams = [r[0] for r in cur.execute("SELECT team_name FROM teams").fetchall()]
    conn.close()
    return [dict(g) for g in games], set(teams)


def assign_rounds(games):
    """Add is_tournament / tier / round_ to each game dict, by counting each
    team's own CTOURN/NCAA/NIT appearances in chronological order."""
    ctourn_count = defaultdict(int)
    ncaa_count = defaultdict(int)
    nit_count = defaultdict(int)

    for g in games:
        gtype = (g.get("game_type") or "REG").upper()
        if gtype == "NCAA":
            ncaa_count[g["home_team"]] += 1
            ncaa_count[g["away_team"]] += 1
            rnd = max(ncaa_count[g["home_team"]], ncaa_count[g["away_team"]])
            ncaa_count[g["home_team"]] = ncaa_count[g["away_team"]] = rnd
            g["is_tournament"] = True
            g["tier"] = "NCAA"
            g["round"] = rnd
        elif gtype == "CTOURN":
            ctourn_count[g["home_team"]] += 1
            ctourn_count[g["away_team"]] += 1
            rnd = max(ctourn_count[g["home_team"]], ctourn_count[g["away_team"]])
            ctourn_count[g["home_team"]] = ctourn_count[g["away_team"]] = rnd
            g["is_tournament"] = True
            g["tier"] = "CONF"
            g["round"] = rnd
        elif gtype == "NIT":
            # the workbook has no dedicated NIT tier -- treat it like the
            # "EARLY" postseason-tournament tier (a modest, round-scaling
            # multiplier) rather than silently flattening it to a plain
            # regular-season game, since it IS still a single-elimination
            # postseason tournament game
            nit_count[g["home_team"]] += 1
            nit_count[g["away_team"]] += 1
            rnd = max(nit_count[g["home_team"]], nit_count[g["away_team"]])
            nit_count[g["home_team"]] = nit_count[g["away_team"]] = rnd
            g["is_tournament"] = True
            g["tier"] = "EARLY"
            g["round"] = rnd
        else:
            g["is_tournament"] = False
            g["tier"] = "NONE"
            g["round"] = None
    return games


def load_conferences(path: Path):
    if not path:
        return {}
    mapping = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mapping[row["team"].strip()] = row["conference"].strip()
    return mapping


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", type=Path)
    ap.add_argument("--conferences", type=Path, default=None)
    args = ap.parse_args()

    games, d1_teams = load_games(args.db_path)
    print(f"Loaded {len(games)} games, {len(d1_teams)} D1 teams.")

    games = assign_rounds(games)

    conferences = load_conferences(args.conferences)
    if conferences:
        print(f"Loaded conference mapping for {len(conferences)} teams -- conference bonus enabled.")
    else:
        print("No --conferences file given -- conference-game bonus disabled for this run.")

    engine = EloEngine(d1_teams=d1_teams, conferences=conferences)

    unrecognized_types = set()
    for g in games:
        gtype = (g.get("game_type") or "REG").upper()
        if gtype not in ("REG", "CTOURN", "NCAA", "NIT"):
            unrecognized_types.add(gtype)
        engine.process_game(
            date=g["date"],
            home_team=g["home_team"],
            away_team=g["away_team"],
            home_pts=g["home_score"],
            away_pts=g["away_score"],
            neutral_site=bool(g["neutral_site"]),
            is_tournament=g["is_tournament"],
            tier=g["tier"],
            round_=g["round"],
            ot=bool(g["ot"]),
        )

    if unrecognized_types:
        print(f"Note: saw unrecognized game_type values treated as regular season: {unrecognized_types}")

    # write results back to the database
    conn = sqlite3.connect(args.db_path)
    cur = conn.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS elo_ledger;
        DROP TABLE IF EXISTS elo_final_ratings;

        CREATE TABLE elo_ledger (
            id INTEGER PRIMARY KEY,
            date TEXT,
            team TEXT,
            opponent TEXT,
            home_away TEXT,
            games_played INTEGER,
            pre_rating REAL,
            opp_pre_rating REAL,
            expected_win_pct REAL,
            points_for INTEGER,
            points_against INTEGER,
            ot INTEGER,
            mov INTEGER,
            result REAL,
            mov_mult REAL,
            t_mult REAL,
            c_mult REAL,
            k REAL,
            k_eff REAL,
            rating_change REAL,
            post_rating REAL,
            accuracy INTEGER,
            log_loss REAL,
            brier REAL
        );

        CREATE TABLE elo_final_ratings (
            team TEXT PRIMARY KEY,
            final_rating REAL
        );
    """)
    cur.executemany("""
        INSERT INTO elo_ledger
        (date, team, opponent, home_away, games_played, pre_rating, opp_pre_rating,
         expected_win_pct, points_for, points_against, ot, mov, result,
         mov_mult, t_mult, c_mult, k, k_eff, rating_change, post_rating,
         accuracy, log_loss, brier)
        VALUES
        (:date, :team, :opponent, :home_away, :games_played, :pre_rating, :opp_pre_rating,
         :expected_win_pct, :points_for, :points_against, :ot, :mov, :result,
         :mov_mult, :t_mult, :c_mult, :k, :k_eff, :rating_change, :post_rating,
         :accuracy, :log_loss, :brier)
    """, engine.ledger)

    final = sorted(engine.final_ratings().items(), key=lambda kv: -kv[1])
    cur.executemany("INSERT INTO elo_final_ratings (team, final_rating) VALUES (?, ?)", final)

    conn.commit()
    conn.close()

    print(f"\nWrote elo_ledger ({len(engine.ledger)} rows) and elo_final_ratings ({len(final)} teams) to {args.db_path}")
    print("\nTop 10 final ratings:")
    for team, rating in final[:10]:
        print(f"  {rating:7.1f}  {team}")


if __name__ == "__main__":
    main()

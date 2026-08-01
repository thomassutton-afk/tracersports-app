#!/usr/bin/env python3
"""
build_nfl_db.py

Builds nfl_elo.db in the same shape as nba_elo.db / wnba_elo.db, so
nfl_accuracy_test.py (and any other tooling written against that schema)
works unmodified against NFL data.

Tables created:
    teams            team_id, team_name
    games            one row per game (game_id, date, season, type, round,
                      home_team, away_team, home_pts, away_pts, ot, neutral)
    ratings          two rows per game (one per team's perspective) -- the
                      full Elo ledger, same columns as nba/wnba
    params           model parameters (k, hfa, alpha, base)
    team_aliases     alternate codes for the same franchise (e.g. nflverse's
                      LA/LAC/LV codes for teams Continelo tracks as one
                      continuous STL/SD/OAK)
    team_history     name changes for a given team_id over time
    franchise_resets present for schema parity with nba/wnba; empty for NFL
                      (no case in this data of a franchise being "revived
                      from scratch" the way WNBA's Portland Fire was)

USAGE
-----
    python build_nfl_db.py parsed_games_1996.csv parsed_games_1997.csv ...
    python build_nfl_db.py --dir /path/to/csvs
    python build_nfl_db.py --dir /path/to/csvs --out nfl_elo.db

Notes on fields that don't exist in the Continelo workbook's own formulas:
    - keff / mov_mult / po_mult / rating_change / post_rate / test /
      accuracy / mov / result -- straight from the validated Elo engine.
    - brier -- (expected_win - result)^2, added here (workbook doesn't
      compute this, but it's cheap and the accuracy-test script wants it).
    - games_played -- 1-indexed count of games that team has played so far
      that season (regular + postseason combined), incrementing continuously.
      Also now an INPUT to the engine (see k decay below), not just a
      derived output column, so it's computed before compute_elo() runs.
    - days_off / opp_days_off -- calendar days since each team's previous
      game that season. Also now an INPUT to the engine (see rest_adj
      below), computed before compute_elo() runs instead of after.
    - k -- no longer a fixed constant. compute_elo() now decays k per row
      as a fraction of the season: K = Kmax - (Kmax - Kfloor) * (games_played
      / season_length(season)), where season_length is 16 before 2021 and
      17 from 2021 on. Kmax/Kfloor come from params (k / k_floor). Pulled
      here from the engine's own output column rather than hardcoded.
    - rest_adj -- tiered, not linear. 0 for equal rest; +/-rest_minor for a
      1-4 day differential (short week); +/-rest_major for 6+ days (bye
      week or bigger). Computed inside compute_elo() from the days_off /
      opp_days_off columns above and added into the effective rating gap
      alongside hfa, same slot the NBA/WNBA rest_adj occupies. Pulled here
      from the engine's own output column rather than hardcoded to 0.0.
    - t -- extra column (not in nba/wnba schema) for regular-season ties,
      since football has them and basketball doesn't. Harmless addition;
      any query written against the nba/wnba schema still works.

REQUIRES an updated nfl_elo.py: compute_elo() must accept days_off /
opp_days_off / games_played as input columns (computed below, before the
call, instead of after), must read K_FLOOR / REST_MINOR / REST_MAJOR
alongside the existing K / HFA / ALPHA / BASE constants, and must return
a per-row "K" output column plus a "RestAdj" output column so this script
can write real values instead of the old 20.0 / 0.0 placeholders.
"""
import argparse
import glob
import os
import sqlite3
from datetime import datetime

import pandas as pd

from nfl_elo import compute_elo, TEAM_NAME_TO_ID
from load_and_run import load_parsed_games

ROUND_TO_NUM = {"WC": 1.0, "DV": 2.0, "CC": 3.0, "SB": 4.0}

# team_id -> current display name
TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "OAK": "Las Vegas Raiders", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SD": "Los Angeles Chargers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "STL": "Los Angeles Rams", "TB": "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}

# team_id -> [(name, start_season, end_season_or_None), ...] in chronological order
TEAM_HISTORY = {
    "TEN": [("Houston Oilers", 1996, 1996), ("Tennessee Oilers", 1997, 1998),
            ("Tennessee Titans", 1999, None)],
    "STL": [("St. Louis Rams", 1996, 2015), ("Los Angeles Rams", 2016, None)],
    "SD":  [("San Diego Chargers", 1996, 2016), ("Los Angeles Chargers", 2017, None)],
    "OAK": [("Oakland Raiders", 1996, 2019), ("Las Vegas Raiders", 2020, None)],
    "WAS": [("Washington Redskins", 1996, 2019), ("Washington Football Team", 2020, 2021),
            ("Washington Commanders", 2022, None)],
    "HOU": [("Houston Texans", 2002, None)],
}

# alternate codes seen in other data sources (e.g. nflverse) for a franchise
# Continelo tracks under one continuous team_id
TEAM_ALIASES = [
    ("LA", "STL", "nflverse code for the Rams post-2016 move"),
    ("LAC", "SD", "nflverse code for the Chargers post-2017 move"),
    ("LV", "OAK", "nflverse code for the Raiders post-2020 move"),
]

SCHEMA = """
CREATE TABLE teams (
    team_id TEXT PRIMARY KEY,
    team_name TEXT NOT NULL
);

CREATE TABLE games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    season INTEGER NOT NULL,
    type TEXT NOT NULL,
    round REAL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_pts INTEGER NOT NULL,
    away_pts INTEGER NOT NULL,
    ot INTEGER NOT NULL DEFAULT 0,
    neutral INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ratings (
    game_id INTEGER NOT NULL,
    team TEXT NOT NULL,
    opponent TEXT NOT NULL,
    home_away TEXT NOT NULL,
    date TEXT NOT NULL,
    season INTEGER NOT NULL,
    type TEXT NOT NULL,
    round REAL,
    games_played INTEGER,
    days_off INTEGER,
    opp_days_off INTEGER,
    rest_adj REAL,
    pre_rate REAL,
    opp_pre_rate REAL,
    expected_win REAL,
    points_for INTEGER,
    points_against INTEGER,
    ot INTEGER,
    mov INTEGER,
    result REAL,
    accuracy INTEGER,
    test REAL,
    brier REAL,
    mov_mult REAL,
    po_mult REAL,
    k REAL,
    keff REAL,
    rating_change REAL,
    post_rate REAL,
    w REAL,
    l REAL,
    t REAL,
    r1w REAL, r1l REAL,
    r2w REAL, r2l REAL,
    r3w REAL, r3l REAL,
    fw REAL, fl REAL,
    PRIMARY KEY (game_id, team)
);

CREATE TABLE params (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE team_aliases (
    alias TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    note TEXT
);

CREATE TABLE team_history (
    team_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season INTEGER
);

CREATE TABLE franchise_resets (
    team_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    note TEXT
);
"""


def round_label_to_cols(round_label, result):
    """Given Continelo's Round label ('WC'/'DV'/'CC'/'SB') and this row's
    Result (1/0.5/0), return the (r1w,r1l,r2w,r2l,r3w,r3l,fw,fl) tuple with
    the appropriate slot set."""
    cols = {"r1w": 0.0, "r1l": 0.0, "r2w": 0.0, "r2l": 0.0,
            "r3w": 0.0, "r3l": 0.0, "fw": 0.0, "fl": 0.0}
    slot = {"WC": "r1", "DV": "r2", "CC": "r3", "SB": "f"}.get(round_label)
    if slot is None:
        return cols
    if result == 1:
        cols[f"{slot}w"] = 1.0
    elif result == 0:
        cols[f"{slot}l"] = 1.0
    return cols


def build(csv_files, out_path):
    print(f"Loading {len(csv_files)} file(s):")
    all_games = []
    for path in csv_files:
        print(f"  - {path}")
        all_games.append(load_parsed_games(path))
    games = pd.concat(all_games, ignore_index=True)

    seasons = sorted(games["Season"].unique())
    print(f"\nSeasons: {seasons[0]}-{seasons[-1]} ({len(seasons)} seasons)")

    # --- games_played / days_off / opp_days_off: computed BEFORE compute_elo()
    # now, not after. The engine needs these as inputs -- games_played drives
    # the k-decay fraction, days_off/opp_days_off drive rest_adj -- so they
    # have to exist on the frame compute_elo() actually sees, in the same
    # chronological order it processes games in. NOTE: this assumes
    # compute_elo() passes these three input columns through to its output
    # untouched (same as it already does with HomeAway, PointsFor, etc.) --
    # verify that's true in nfl_elo.py before running this.
    games["Date"] = pd.to_datetime(games["Date"])
    games = games.sort_values(["Date", "Team"]).reset_index(drop=True)

    games["games_played"] = games.groupby(["Season", "Team"]).cumcount() + 1

    games["prev_date"] = games.groupby(["Season", "Team"])["Date"].shift(1)
    games["days_off"] = (games["Date"] - games["prev_date"]).dt.days

    opp_prev = games[["Date", "Season", "Team", "prev_date"]].rename(
        columns={"Team": "Opponent", "prev_date": "opp_prev_date"}
    )
    games = games.merge(opp_prev, on=["Date", "Season", "Opponent"], how="left")
    games["opp_days_off"] = (games["Date"] - games["opp_prev_date"]).dt.days
    games = games.drop(columns=["prev_date", "opp_prev_date"])

    print("Running Elo engine...")
    result = compute_elo(games)
    result["Date"] = pd.to_datetime(result["Date"])
    result = result.sort_values(["Date", "Team"]).reset_index(drop=True)

    if os.path.exists(out_path):
        os.remove(out_path)
    conn = sqlite3.connect(out_path)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    # --- teams ---
    team_ids = sorted(set(games["Team"]) | set(games["Opponent"]))
    cur.executemany(
        "INSERT INTO teams (team_id, team_name) VALUES (?, ?)",
        [(t, TEAM_NAMES.get(t, t)) for t in team_ids],
    )

    # --- team_history ---
    history_rows = []
    for t in team_ids:
        if t in TEAM_HISTORY:
            for name, start, end in TEAM_HISTORY[t]:
                history_rows.append((t, t, name, start, end))
        else:
            history_rows.append((t, t, TEAM_NAMES.get(t, t), seasons[0], None))
    cur.executemany(
        "INSERT INTO team_history (team_id, code, name, start_season, end_season) VALUES (?,?,?,?,?)",
        history_rows,
    )

    # --- team_aliases ---
    cur.executemany(
        "INSERT INTO team_aliases (alias, team_id, note) VALUES (?,?,?)",
        [row for row in TEAM_ALIASES if row[1] in team_ids],
    )

    # --- params ---
    from nfl_elo import (
        K, HFA, ALPHA, BASE, DIV_GAME_MULT, CONF_GAME_MULT,
        K_FLOOR, REST_MINOR, REST_MAJOR,
    )
    cur.executemany(
        "INSERT INTO params (key, value) VALUES (?, ?)",
        [
            ("k", str(K)), ("hfa", str(HFA)), ("alpha", str(ALPHA)), ("base", str(BASE)),
            ("div_game_mult", str(DIV_GAME_MULT)), ("conf_game_mult", str(CONF_GAME_MULT)),
            ("k_floor", str(K_FLOOR)),
            ("rest_minor", str(REST_MINOR)), ("rest_major", str(REST_MAJOR)),
        ],
    )

    # --- games (one row per game). Normally we take the HomeAway=='H' row;
    # neutral-site games (e.g. the Super Bowl) have HomeAway=='N' on both
    # sides, so for those we deterministically pick the alphabetically
    # first team as the "home_team" column and flag neutral=1.
    result["_pair_key"] = result.apply(
        lambda r: (r["Date"], int(r["Season"]), frozenset([r["Team"], r["Opponent"]])), axis=1
    )

    def pick_primary(group):
        h = group[group["HomeAway"] == "H"]
        if len(h):
            row = h.iloc[0].copy()
            row["_neutral"] = 0
            return row
        row = group.sort_values("Team").iloc[0].copy()
        row["_neutral"] = 1
        return row

    home_rows = (
        result.groupby("_pair_key", sort=False, group_keys=False)
        .apply(pick_primary)
        .reset_index(drop=True)
    )
    home_rows = home_rows.sort_values(["Date", "Team"]).reset_index(drop=True)
    home_rows["game_id"] = home_rows.index + 1
    game_id_lookup = {}  # (Date, Season, frozenset({Team,Opponent})) -> game_id

    games_insert = []
    for _, r in home_rows.iterrows():
        round_num = ROUND_TO_NUM.get(r["Round"])
        games_insert.append((
            r["game_id"], r["Date"].strftime("%Y-%m-%d"), int(r["Season"]), r["Type"],
            round_num, r["Team"], r["Opponent"], int(r["PointsFor"]), int(r["PointsAgainst"]),
            int(r["OT"]), int(r["_neutral"]),
        ))
        key = (r["Date"], int(r["Season"]), frozenset([r["Team"], r["Opponent"]]))
        game_id_lookup[key] = r["game_id"]

    cur.executemany(
        """INSERT INTO games (game_id, date, season, type, round, home_team, away_team,
                               home_pts, away_pts, ot, neutral)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        games_insert,
    )

    # --- ratings (both perspectives of every game) ---
    ratings_insert = []
    for _, r in result.iterrows():
        key = (r["Date"], int(r["Season"]), frozenset([r["Team"], r["Opponent"]]))
        game_id = game_id_lookup[key]
        round_num = ROUND_TO_NUM.get(r["Round"])
        brier = (r["ExpectedWin%"] - r["Result"]) ** 2
        po_cols = round_label_to_cols(r["Round"] if r["Type"] == "P" else None, r["Result"])
        days_off = None if pd.isna(r["days_off"]) else int(r["days_off"])
        opp_days_off = None if pd.isna(r["opp_days_off"]) else int(r["opp_days_off"])

        ratings_insert.append((
            game_id, r["Team"], r["Opponent"], r["HomeAway"], r["Date"].strftime("%Y-%m-%d"),
            int(r["Season"]), r["Type"], round_num, int(r["games_played"]),
            days_off, opp_days_off, r["RestAdj"],
            r["PreGmRate"], r["OppPreGmRate"], r["ExpectedWin%"],
            int(r["PointsFor"]), int(r["PointsAgainst"]), int(r["OT"]), int(r["MOV"]),
            r["Result"], int(r["Accuracy"]), r["Test"], brier,
            r["MOVMult"], r["POMult"], r["K"],  # k now decays per row; see nfl_elo.py
            r["Keff"], r["RatingChange"], r["PostGmRate"],
            float(r["W"]), float(r["L"]), float(r["T"]),
            po_cols["r1w"], po_cols["r1l"], po_cols["r2w"], po_cols["r2l"],
            po_cols["r3w"], po_cols["r3l"], po_cols["fw"], po_cols["fl"],
        ))

    cur.executemany(
        """INSERT INTO ratings (
               game_id, team, opponent, home_away, date, season, type, round,
               games_played, days_off, opp_days_off, rest_adj,
               pre_rate, opp_pre_rate, expected_win, points_for, points_against,
               ot, mov, result, accuracy, test, brier, mov_mult, po_mult, k, keff,
               rating_change, post_rate, w, l, t, r1w, r1l, r2w, r2l, r3w, r3l, fw, fl
           ) VALUES (%s)""" % ",".join(["?"] * 40),
        ratings_insert,
    )

    conn.commit()
    n_games = cur.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    n_ratings = cur.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
    conn.close()

    print(f"\nWrote {out_path}")
    print(f"  games:   {n_games:,}")
    print(f"  ratings: {n_ratings:,}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_files", nargs="*")
    parser.add_argument("--dir", help="Folder to glob for parsed_games_*.csv files")
    parser.add_argument("--out", default="nfl_elo.db")
    args = parser.parse_args()

    csv_files = list(args.csv_files)
    if args.dir:
        csv_files += sorted(glob.glob(os.path.join(args.dir, "parsed_games_*.csv")))
    csv_files = sorted(set(csv_files))
    if not csv_files:
        raise SystemExit("No CSV files given. Pass file paths directly or use --dir.")

    build(csv_files, args.out)


if __name__ == "__main__":
    main()

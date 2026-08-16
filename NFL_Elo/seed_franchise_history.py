"""
ONE-TIME: pre-register every NFL franchise's complete era history
before loading any season data, instead of registering teams "live"
as add_season.py encounters them and running franchise.py relocate
between season loads.

This only works because NFL's full relocation/rename history (1996-
present) is already fully known and settled - see TEMPLATE.md section
8 for when this pattern is (and isn't) appropriate.

Run this ONCE, against an empty database, before the first
add_season.py call. After this, add_season.py should never see a
"new" team at all when loading 1996-2025 - every code in every season
file will already resolve through an existing alias to a franchise
that already has its complete, correct era history.

Usage:
    python3 seed_franchise_history.py
"""
import glob
import pandas as pd
import db

DB_PATH = "nfl_elo.db"
NORMALIZED_DIR = "parsed_games_normalized"

# Current display name for every franchise that has only ever had ONE
# era (no relocation/rename) - franchises WITH history below aren't
# listed here, their first era's own name is used instead.
TEAM_NAMES = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers",
}

# team_id-seed-key (== the code Continelo's own files always use for
# this franchise, per nfl_elo.py's TEAM_NAME_TO_ID - see
# franchise.py's docstring: NFL relocations here change the NAME, not
# the code) -> [(name, start_season, end_season_or_None), ...] in
# chronological order.
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

# Alternate codes seen in OTHER data sources (e.g. nflverse) for a
# franchise Continelo itself tracks under one continuous code - these
# aren't used by our own normalized files today, but registering them
# means a future data source using them won't be treated as a new team.
TEAM_ALIASES = [
    ("LA", "STL", "nflverse code for the Rams post-2016 move"),
    ("LAC", "SD", "nflverse code for the Chargers post-2017 move"),
    ("LV", "OAK", "nflverse code for the Raiders post-2020 move"),
]


def first_seasons_from_data(normalized_dir: str) -> dict[str, int]:
    """The earliest season each code actually appears in the real
    normalized game files - used to catch any drift between this
    script's hardcoded TEAM_HISTORY and what's actually in the data
    (e.g. if a new season file introduces a genuinely new team)."""
    first = {}
    for path in sorted(glob.glob(f"{normalized_dir}/parsed_games_*.csv")):
        df = pd.read_csv(path)
        season = int(df["Season"].iloc[0])
        for code in set(df["Team"]) | set(df["Opp"]):
            if code not in first or season < first[code]:
                first[code] = season
    return first


def seed(conn, first_seasons: dict[str, int]) -> None:
    all_codes = sorted(set(first_seasons) | set(TEAM_HISTORY) | set(TEAM_NAMES))

    for code in all_codes:
        actual_first = first_seasons.get(code)
        if code in TEAM_HISTORY:
            eras = TEAM_HISTORY[code]
            first_name, first_start, _ = eras[0]
            if actual_first is not None and actual_first != first_start:
                print(f"WARNING: {code} first appears in the data in {actual_first}, "
                      f"but TEAM_HISTORY says {first_start} - check for drift.")
            team_id = db.register_new_team(conn, code, first_name, first_start)
            for name, start, end in eras[1:]:
                db.close_team_history(conn, team_id, start - 1)
                db.add_team_history(conn, team_id, code, name, start, end)
        else:
            name = TEAM_NAMES.get(code, code)
            start = actual_first if actual_first is not None else 1996
            db.register_new_team(conn, code, name, start)

    for alias, target_code, note in TEAM_ALIASES:
        target_team_id = db.resolve_team_id(conn, target_code)
        db.add_alias(conn, alias, target_team_id, note=note)

    conn.commit()


def main():
    conn = db.connect(DB_PATH)
    existing = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    if existing:
        print(f"'{DB_PATH}' already has {existing} team(s) registered - refusing to seed "
              f"into a non-empty database. Delete/rename it first if you want a clean seed.")
        return

    first_seasons = first_seasons_from_data(NORMALIZED_DIR)
    seed(conn, first_seasons)

    n_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    n_history = conn.execute("SELECT COUNT(*) FROM team_history").fetchone()[0]
    n_aliases = conn.execute("SELECT COUNT(*) FROM team_aliases").fetchone()[0]
    print(f"Seeded {n_teams} franchises, {n_history} team_history era(s), "
          f"{n_aliases} alias(es).")
    print("Ready for add_season.py - no team registrations should happen during the "
          "historical load.")


if __name__ == "__main__":
    main()

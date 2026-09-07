#!/usr/bin/env python3
"""
nba_csv_to_xlsx.py

Converts a Basketball-Reference-style season schedule CSV (Date, Visitor/Neutral,
PTS, Home/Neutral, PTS, Box Score, OT, Attend., LOG, Arena, Notes) into the
"long format" xlsx schema used in NBA_1996_Results.xlsx:

    Date | Season | Type | Round | Team | Opp | HomeAway | PF | PA | OT

Each game becomes TWO rows (one per team's perspective).

USAGE:
    python3 nba_csv_to_xlsx.py INPUT.csv OUTPUT.xlsx --season 1995 [--playoff-start YYYY-MM-DD]

If --playoff-start is omitted, the script tries to auto-detect the regular
season -> playoffs boundary (see detect_playoff_start) and prints what it
found so you can sanity-check it. If it looks wrong, pass --playoff-start
explicitly (e.g. --playoff-start 1995-04-27).

Playoff ROUND is inferred structurally, not from hardcoded brackets:
for each team, its playoff opponents are visited in order; the Nth distinct
opponent a team faces in the playoffs is round N. This works for any
single-elimination bracket regardless of best-of-5 / best-of-7 length, as
long as the games are in chronological order and there are no play-in-style
byes for the same round.
"""

import argparse
import csv
import sys
from datetime import datetime
from collections import defaultdict

try:
    import openpyxl
except ImportError:
    sys.exit("This script requires openpyxl: pip install openpyxl --break-system-packages")

# Full team name -> 3-letter abbreviation, matching the convention used in
# NBA_1996_Results.xlsx. Extend this dict if you feed in seasons with other
# franchise names (e.g. Bobcats, Wizards, Thunder, Pelicans, etc.)
TEAM_ABBR = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Jersey Nets": "NJN",
    "New York Knicks": "NYK",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Seattle SuperSonics": "SEA",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Vancouver Grizzlies": "VAN",
    "Washington Bullets": "WAS",
    "Washington Wizards": "WAS",
}


def parse_date(s):
    # e.g. "Fri Nov 4 1994"
    return datetime.strptime(s.strip(), "%a %b %d %Y")


def load_games(csv_path):
    """Return list of dicts: date, visitor, vpts, home, hpts, ot(bool)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    header_idx = None
    for i, r in enumerate(rows):
        if r and r[0].strip() == "Date":
            header_idx = i
            break
    if header_idx is None:
        sys.exit("Could not find header row starting with 'Date' in the CSV.")

    games = []
    for r in rows[header_idx + 1:]:
        if not r or len(r) < 5 or not r[0].strip():
            continue
        date = parse_date(r[0])
        visitor = r[1].strip()
        vpts = int(r[2])
        home = r[3].strip()
        hpts = int(r[4])
        ot_flag = 1 if len(r) > 6 and r[6].strip() != "" else 0
        games.append({
            "date": date, "visitor": visitor, "vpts": vpts,
            "home": home, "hpts": hpts, "ot": ot_flag,
        })
    return games


def detect_playoff_start(games):
    """
    Heuristic: look at gaps between consecutive unique game dates in the
    LAST 25% of the season chronologically (to avoid mistaking the
    All-Star break, which happens mid-season, for the playoff boundary).
    The largest gap in that window is treated as the reg-season/playoff
    split. Returns the first playoff date.
    """
    dates = sorted(set(g["date"] for g in games))
    cutoff_search_start = int(len(dates) * 0.75)
    window = dates[cutoff_search_start:]
    best_gap = None
    best_idx = None
    for i in range(1, len(window)):
        gap = (window[i] - window[i - 1]).days
        if best_gap is None or gap > best_gap:
            best_gap = gap
            best_idx = i
    if best_idx is None:
        return None
    return window[best_idx]


def abbr(team_name):
    if team_name not in TEAM_ABBR:
        sys.exit(f"Unknown team name '{team_name}'. Add it to TEAM_ABBR in the script.")
    return TEAM_ABBR[team_name]


def assign_rounds(playoff_games):
    """
    playoff_games: list of game dicts, already sorted by date.
    Returns a dict mapping id(game) -> round int, using the
    "Nth distinct opponent per team" structural method described in the
    module docstring.
    """
    opponent_sequence = defaultdict(list)  # team -> [opp1, opp2, ...] in order faced
    round_for_game = {}

    for g in playoff_games:
        vteam, hteam = abbr(g["visitor"]), abbr(g["home"])

        def round_for(team, opp):
            seq = opponent_sequence[team]
            if not seq or seq[-1] != opp:
                seq.append(opp)
            return len(seq)

        rv = round_for(vteam, hteam)
        rh = round_for(hteam, vteam)
        if rv != rh:
            print(f"WARNING: round mismatch for {g['date'].date()} "
                  f"{vteam}@{hteam}: visitor round {rv}, home round {rh}. "
                  f"Using the higher of the two -- double check this series.")
        round_for_game[id(g)] = max(rv, rh)

    return round_for_game


def build_rows(games, season, playoff_start):
    rows = []
    playoff_games = sorted([g for g in games if g["date"] >= playoff_start], key=lambda g: g["date"])
    round_lookup = assign_rounds(playoff_games)

    for g in sorted(games, key=lambda g: g["date"]):
        vteam, hteam = abbr(g["visitor"]), abbr(g["home"])
        is_playoff = g["date"] >= playoff_start
        game_type = "P" if is_playoff else "R"
        round_val = round_lookup[id(g)] if is_playoff else "RS"

        # visitor's row
        rows.append([g["date"], season, game_type, round_val, vteam, hteam, "A", g["vpts"], g["hpts"], g["ot"]])
        # home's row
        rows.append([g["date"], season, game_type, round_val, hteam, vteam, "H", g["hpts"], g["vpts"], g["ot"]])

    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_csv")
    ap.add_argument("output_xlsx")
    ap.add_argument("--season", type=int, required=True,
                     help="Season label to use, matching the xlsx convention "
                          "(e.g. the 1994-95 season -> 1995).")
    ap.add_argument("--playoff-start", type=str, default=None,
                     help="YYYY-MM-DD. If omitted, auto-detected from the schedule gaps.")
    args = ap.parse_args()

    games = load_games(args.input_csv)
    print(f"Loaded {len(games)} games from {args.input_csv} "
          f"({games[0]['date'].date()} to {games[-1]['date'].date()}).")

    if args.playoff_start:
        playoff_start = datetime.strptime(args.playoff_start, "%Y-%m-%d")
    else:
        playoff_start = detect_playoff_start(games)
        if playoff_start is None:
            sys.exit("Could not auto-detect playoff start. Pass --playoff-start explicitly.")
        print(f"Auto-detected playoff start: {playoff_start.date()}  "
              f"(verify this is correct -- pass --playoff-start to override)")

    n_reg = sum(1 for g in games if g["date"] < playoff_start)
    n_playoff = sum(1 for g in games if g["date"] >= playoff_start)
    print(f"Regular season games: {n_reg}, Playoff games: {n_playoff}")

    rows = build_rows(games, args.season, playoff_start)

    # Sanity check: round distribution
    round_counts = defaultdict(int)
    for r in rows:
        if r[2] == "P":
            round_counts[r[3]] += 1
    print("Playoff rows per round (2 rows/game):", dict(sorted(round_counts.items())))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Date", "Season", "Type", "Round", "Team", "Opp", "HomeAway", "PF", "PA", "OT"])
    for r in rows:
        ws.append(r)
    # format date column
    for row in ws.iter_rows(min_row=2, min_col=1, max_col=1):
        row[0].number_format = "m/d/yyyy"

    wb.save(args.output_xlsx)
    print(f"Wrote {len(rows)} rows to {args.output_xlsx}")


if __name__ == "__main__":
    main()

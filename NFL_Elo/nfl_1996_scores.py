#!/usr/bin/env python3
"""
Pull every NFL game score for the 1996 season and save it to a CSV file.

Data source: devstopfix/nfl_results on GitHub, a public-domain dataset of
NFL results from 1978-2014 (Pro Football Reference blocks scripted access
as of mid-2026, so this is a much more reliable source than scraping).

Requires:
    pip install requests pandas

Usage:
    python nfl_1996_scores.py
    python nfl_1996_scores.py --output my_scores.csv
"""

import argparse
import sys
from io import StringIO

import pandas as pd
import requests

DATA_URL = (
    "https://raw.githubusercontent.com/devstopfix/nfl_results/"
    "master/nfl%20{year}.csv"
)

# Week numbers > 17 in this dataset are playoff rounds, not regular-season weeks.
PLAYOFF_ROUND_NAMES = {
    18: "Wild Card",
    19: "Divisional",
    20: "Conference Championship",
    22: "Super Bowl",
}


def fetch_season_games(year: int) -> pd.DataFrame:
    """Download and parse the season CSV for the given year."""
    url = DATA_URL.format(year=year)
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Could not fetch {url}: HTTP {resp.status_code}")

    df = pd.read_csv(StringIO(resp.text))

    df["kickoff"] = pd.to_datetime(df["kickoff"])
    df["date"] = df["kickoff"].dt.date

    df["round"] = df["week"].map(PLAYOFF_ROUND_NAMES).fillna(
        "Week " + df["week"].astype(str)
    )

    # Figure out winner/loser for convenience.
    df["winner"] = df.apply(
        lambda r: r["home_team"] if r["home_score"] > r["visitors_score"]
        else (r["visiting_team"] if r["visitors_score"] > r["home_score"] else "Tie"),
        axis=1,
    )

    df = df[
        [
            "season", "week", "round", "date",
            "home_team", "home_score",
            "visiting_team", "visitors_score",
            "winner",
        ]
    ].rename(columns={
        "visiting_team": "away_team",
        "visitors_score": "away_score",
    })

    return df.sort_values(["week", "date"]).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", "-o", default="nfl_1996_scores.csv",
        help="Output CSV filename (default: nfl_1996_scores.csv)"
    )
    args = parser.parse_args()

    print("Fetching 1996 NFL season scores...")
    try:
        games = fetch_season_games(1996)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    games.to_csv(args.output, index=False)
    print(f"Saved {len(games)} games to {args.output}")
    print(games.head(10).to_string(index=False))


if __name__ == "__main__":
    main()

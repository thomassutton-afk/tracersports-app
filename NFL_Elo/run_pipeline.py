"""
Batch pipeline for the Continelo Elo system.

Point this at all your parsed_games_*.csv files (any order) and it will:
  1. Load + normalize each file (team-name mapping, week derivation, etc.)
  2. Sort everything into chronological season order
  3. Run them through the Elo engine IN ONE PASS, so ratings correctly
     carry over from one season to the next (the alpha/base blend needs
     each team's real final rating from the prior season -- running a
     season in isolation gives wrong answers for every season after the
     first).
  4. Write one detailed <season>_elo.csv per season (every game, every
     column, same as RawData in the workbook).
  5. Write one rankings_summary.csv with each team's end-of-season rating
     and rank, for every season -- the "quick answer" file.

USAGE
-----
    python run_pipeline.py parsed_games_1996.csv parsed_games_1997.csv ...

    # or point it at a folder and it'll grab every parsed_games_*.csv in it
    python run_pipeline.py --dir /path/to/csvs

Output goes to ./elo_output/ by default (--out to change it).
"""
import argparse
import glob
import os
import sys

import pandas as pd

from nfl_elo import compute_elo
from load_and_run import load_parsed_games


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_files", nargs="*", help="parsed_games_*.csv files to load")
    parser.add_argument("--dir", help="Folder to glob for parsed_games_*.csv files")
    parser.add_argument("--out", default="elo_output", help="Output directory (default: elo_output)")
    args = parser.parse_args()

    csv_files = list(args.csv_files)
    if args.dir:
        csv_files += sorted(glob.glob(os.path.join(args.dir, "parsed_games_*.csv")))
    csv_files = sorted(set(csv_files))

    if not csv_files:
        print("No CSV files given. Pass file paths directly or use --dir.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {len(csv_files)} file(s):")
    all_games = []
    for path in csv_files:
        print(f"  - {path}")
        all_games.append(load_parsed_games(path))

    games = pd.concat(all_games, ignore_index=True)

    seasons = sorted(games["Season"].unique())
    print(f"\nSeasons found: {seasons}")
    print("Running Elo engine (single pass, so ratings carry over across seasons)...")

    result = compute_elo(games)

    os.makedirs(args.out, exist_ok=True)

    # One detail file per season
    for season in seasons:
        season_df = result[result["Season"] == season]
        out_path = os.path.join(args.out, f"{season}_elo.csv")
        season_df.to_csv(out_path, index=False)
        print(f"Wrote {len(season_df)} rows -> {out_path}")

    # One combined rankings summary, all seasons
    summary_rows = []
    for season in seasons:
        season_df = result[result["Season"] == season]
        final = (
            season_df.sort_values(["Team", "Week"])
            .groupby("Team")
            .tail(1)
            .sort_values("PostGmRate", ascending=False)
            .reset_index(drop=True)
        )
        final.insert(0, "Rank", range(1, len(final) + 1))
        summary_rows.append(final[["Season", "Rank", "Team", "PostGmRate", "Week", "Type", "Round"]])

    summary = pd.concat(summary_rows, ignore_index=True)
    summary_path = os.path.join(args.out, "rankings_summary.csv")
    summary.to_csv(summary_path, index=False)
    print(f"Wrote rankings summary -> {summary_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()

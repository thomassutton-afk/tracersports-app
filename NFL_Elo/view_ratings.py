"""
Quick viewer for elo_output/rankings_summary.csv.

USAGE (run from the NFL_Elo folder, in Command Prompt):

    python view_ratings.py                # print every season, best to worst
    python view_ratings.py --season 2003   # just one season
    python view_ratings.py --csv           # also write ratings_sorted.csv
"""
import argparse
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, help="Only show this season")
    parser.add_argument("--csv", action="store_true", help="Also write ratings_sorted.csv")
    parser.add_argument("--in", dest="in_path", default="elo_output/rankings_summary.csv")
    args = parser.parse_args()

    df = pd.read_csv(args.in_path)

    if args.season:
        df = df[df["Season"] == args.season]

    df = df.sort_values(["Season", "PostGmRate"], ascending=[True, False])
    df["PostGmRate"] = df["PostGmRate"].round(1)

    view = df[["Season", "Rank", "Team", "PostGmRate"]]
    print(view.to_string(index=False))

    if args.csv:
        out_path = "ratings_sorted.csv"
        view.to_csv(out_path, index=False)
        print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

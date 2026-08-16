"""
Load a `parsed_games_*.csv` file (Date,Season,Type,Round,Team,Opp,HomeAway,
PointsFor,PointsAgainst,OT) and run it through the Continelo Elo engine.
"""
import sys
import pandas as pd

from nfl_elo import TEAM_NAME_TO_ID, PLAYOFF_ROUND_LABEL, week_from_date, compute_elo

MASTER_OT_PATH = "master_ot.csv"  # Season, Date, Team, Opponent, OT -- see README


def load_master_ot(path: str = MASTER_OT_PATH) -> pd.DataFrame:
    """Load the combined real-OT-flag reference table (1996-1997 verified
    against the Continelo workbook; 1999-2025 from nflverse; 1998 not yet
    available -- see README for how to fill that gap)."""
    ot = pd.read_csv(path, parse_dates=["Date"])
    return ot


def apply_master_ot(games: pd.DataFrame, ot_path: str = MASTER_OT_PATH) -> pd.DataFrame:
    """Overwrite games['OT'] using the master OT reference table wherever a
    matching (Season, Date, Team, Opponent) row exists. Games not found in
    the reference table keep whatever OT value they already had (usually 0,
    since the source CSVs don't carry real OT data)."""
    try:
        ot = load_master_ot(ot_path)
    except FileNotFoundError:
        print(f"WARNING: {ot_path} not found -- OT flags left as-is.", file=sys.stderr)
        return games

    games = games.merge(
        ot.rename(columns={"OT": "OT_real"}),
        on=["Season", "Date", "Team", "Opponent"],
        how="left",
    )
    matched = games["OT_real"].notna()
    games.loc[matched, "OT"] = games.loc[matched, "OT_real"].astype(int)
    unmatched_seasons = sorted(games.loc[~matched, "Season"].unique())
    if unmatched_seasons:
        print(
            f"NOTE: no verified OT data for season(s) {unmatched_seasons} -- "
            "those games are left as regulation (OT=0) unless the source CSV "
            "already had real flags.",
            file=sys.stderr,
        )
    games = games.drop(columns=["OT_real"])
    return games


def load_parsed_games(csv_path: str, use_master_ot: bool = True,
                       master_ot_path: str = MASTER_OT_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["Date"])

    # Map full team names -> Continelo TeamIDs
    missing = set(df["Team"]) | set(df["Opp"])
    missing = {t for t in missing if t not in TEAM_NAME_TO_ID}
    if missing:
        raise ValueError(f"No TeamID mapping for: {sorted(missing)}")

    df["Team"] = df["Team"].map(TEAM_NAME_TO_ID)
    df["Opponent"] = df["Opp"].map(TEAM_NAME_TO_ID)

    # Type: 'Reg' -> 'R', 'Playoff' -> 'P'
    df["Type"] = df["Type"].map({"Reg": "R", "Playoff": "P"})

    # Round: regular season -> 'RS'; playoffs, numeric round -> WC/DV/CC/SB
    def round_label(row):
        if row["Type"] == "R":
            return "RS"
        return PLAYOFF_ROUND_LABEL[int(row["Round"])]

    df["Round"] = df.apply(round_label, axis=1)

    # OT: some parsed_games exports carry a real flag (0/1, True/False, 'OT');
    # others (like the 1996 file) only have the placeholder 'Unknown' for
    # every row, meaning the source data simply didn't capture OT.
    def ot_flag(v):
        s = str(v).strip().lower()
        return 1 if s in {"1", "true", "ot", "yes"} else 0

    df["OT"] = df["OT"].apply(ot_flag)

    # Patch in real OT flags from master_ot.csv (Season, Date, Team, Opponent)
    # wherever we have them -- this is the preferred, verified source.
    if use_master_ot:
        df = apply_master_ot(df, master_ot_path)

    if (df["OT"] == 0).all() and df["Opp"].notna().any():
        raw_ot_values = set(pd.read_csv(csv_path)["OT"].astype(str).unique())
        if raw_ot_values <= {"Unknown", "unknown", "nan"}:
            print(
                "WARNING: no OT data available for this file (source column "
                "was 'Unknown' and master_ot.csv had no coverage for this "
                "season) -- all games treated as regulation. Ratings for "
                "teams in actual OT games will drift ~1-2 points from the "
                "true source.",
                file=sys.stderr,
            )

    # Week: derive per season from Date using Tue-Mon buckets; playoff
    # rounds get their own pseudo-week numbers continuing after the regular
    # season so chronological ordering within a season is preserved.
    weeks = []
    for season, sdf in df.groupby("Season"):
        reg_start = sdf.loc[sdf["Type"] == "R", "Date"].min()
        reg_weeks = sdf["Date"].apply(lambda d: week_from_date(d, reg_start))
        # Playoff rows: continue numbering after the max regular season week
        max_reg_week = reg_weeks[sdf["Type"] == "R"].max()
        po_order = {"WC": 1, "DV": 2, "CC": 3, "SB": 4}
        is_po = sdf["Type"] == "P"
        po_weeks = sdf.loc[is_po, "Round"].map(po_order) + max_reg_week
        combined = reg_weeks.copy()
        combined.loc[is_po] = po_weeks
        weeks.append(combined)
    df["Week"] = pd.concat(weeks).astype(int)

    df = df[
        ["Week", "Season", "Type", "Round", "Team", "Opponent", "HomeAway",
         "PointsFor", "PointsAgainst", "OT", "Date"]
    ]
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    return df


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "parsed_games_1996.csv"
    games = load_parsed_games(csv_path)
    result = compute_elo(games)
    out_path = csv_path.replace(".csv", "_elo.csv")
    result.to_csv(out_path, index=False)
    print(f"Wrote {len(result)} rows to {out_path}")
    return result


if __name__ == "__main__":
    main()

"""
ONE-TIME conversion: rewrite parsed_games_YYYY.csv into the same file
conventions NBA/WNBA's add_season.py already expects, so NFL's loader
doesn't need any bespoke per-file translation logic going forward.

Fixes four convention mismatches in the original parsed_games files
(none of these are inherent to football - they're just how that
particular export script happened to write things):
  - Team/Opp: full names ("Kansas City Chiefs") -> stable codes ("KC"),
    via nfl_elo.py's TEAM_NAME_TO_ID table.
  - Type: "Reg"/"Playoff" -> "R"/"P".
  - Round: numeric playoff round (1-4) -> "RS" for regular season,
    "WC"/"DV"/"CC"/"SB" for playoffs, via PLAYOFF_ROUND_LABEL.
  - OT: corrected using master_ot.csv wherever a verified flag exists
    (this data gap is real and can't be fixed - what's fixed here is
    requiring every future load to re-join a correction file forever;
    after this, the correction is permanent, baked into the file once).

Does NOT compute a Week number - that stays add_season.py's job (it's
genuinely NFL-specific, not a file-convention issue - see this
project's TEMPLATE.md).

Usage:
    python3 normalize_parsed_games.py
        (reads every file in parsed_games/, writes to
        parsed_games_normalized/, using master_ot.csv for OT)
"""
import os
import glob
import pandas as pd
from nfl_elo import TEAM_NAME_TO_ID, PLAYOFF_ROUND_LABEL

SRC_DIR = "parsed_games"
OUT_DIR = "parsed_games_normalized"
MASTER_OT_PATH = "master_ot.csv"


def load_master_ot(path: str) -> pd.DataFrame:
    ot = pd.read_csv(path, parse_dates=["Date"])
    return ot


def normalize_file(path: str, ot_table: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["Date"])

    missing = (set(df["Team"]) | set(df["Opp"])) - set(TEAM_NAME_TO_ID)
    if missing:
        raise ValueError(f"{path}: no TeamID mapping for {sorted(missing)}")
    df["Team"] = df["Team"].map(TEAM_NAME_TO_ID)
    df["Opp"] = df["Opp"].map(TEAM_NAME_TO_ID)

    df["Type"] = df["Type"].map({"Reg": "R", "Playoff": "P"})
    if df["Type"].isna().any():
        raise ValueError(f"{path}: unrecognized Type value(s)")

    def round_label(row):
        if row["Type"] == "R":
            return "RS"
        return PLAYOFF_ROUND_LABEL[int(row["Round"])]
    df["Round"] = df.apply(round_label, axis=1)

    # Start from whatever's in the source file (usually the
    # "Unknown" placeholder -> 0), then overwrite with master_ot.csv
    # wherever a verified (Season, Date, Team, Opp) match exists.
    def ot_flag(v):
        s = str(v).strip().lower()
        return 1 if s in {"1", "true", "ot", "yes"} else 0
    df["OT"] = df["OT"].apply(ot_flag)

    merged = df.merge(
        ot_table.rename(columns={"OT": "OT_real", "Opponent": "Opp"}),
        on=["Season", "Date", "Team", "Opp"], how="left",
    )
    matched = merged["OT_real"].notna()
    df.loc[matched, "OT"] = merged.loc[matched, "OT_real"].astype(int)

    return df[["Date", "Season", "Type", "Round", "Team", "Opp", "HomeAway",
               "PointsFor", "PointsAgainst", "OT"]]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ot_table = load_master_ot(MASTER_OT_PATH)

    files = sorted(glob.glob(os.path.join(SRC_DIR, "parsed_games_*.csv")))
    print(f"Normalizing {len(files)} file(s) from {SRC_DIR}/ -> {OUT_DIR}/\n")

    unmatched_seasons = set()
    for path in files:
        df = normalize_file(path, ot_table)
        season = int(df["Season"].iloc[0])
        matched_this_season = (ot_table["Season"] == season).any()
        if not matched_this_season:
            unmatched_seasons.add(season)

        out_path = os.path.join(OUT_DIR, os.path.basename(path))
        df.to_csv(out_path, index=False)
        print(f"  {os.path.basename(path)}: {len(df)} rows -> {out_path}")

    if unmatched_seasons:
        print(f"\nNOTE: no verified OT data for season(s) {sorted(unmatched_seasons)} "
              f"- those games' OT defaults to 0 unless the source file already had a "
              f"real flag.")
    print("\nDone.")


if __name__ == "__main__":
    main()

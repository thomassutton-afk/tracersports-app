"""
convert_sportsref_schedule.py

Replaces the entire manual pipeline (number games -> duplicate+flip
home/away -> sort -> XLOOKUP names to codes -> copy columns into a
separate file) with one script. Reads a raw Sports-Reference-style
schedule -- ONE row per game, with Week/Day/Date/VisTm/Pts/HomeTm/Pts/Time
columns and full team names -- and writes the two-rows-per-game shape
add_season.py expects (Date/Season/Type/Round/Team/Opp/HomeAway/
PointsFor/PointsAgainst/OT), with team names already translated to
Continelo's own codes via nfl_elo.py's TEAM_NAME_TO_ID table (the SAME
table normalize_parsed_games.py and load_and_run.py use) -- so this can
never reintroduce the LAC/LAR/LV-vs-SD/STL/OAK mismatch, since it uses
the exact same translation table as everything else in this system.

Because every row is generated directly from the SAME source row (no
copy-paste, no separate flip step, no manual row alignment), there's no
step where a row's Team/Opp could end up mismatched with its own Date --
that's the failure mode that produced the ARI/LAR-style bug, and this
script has no equivalent step for it to happen in.

Handles unplayed games (blank Pts columns) automatically -- those rows
just get PointsFor/PointsAgainst left blank, which is exactly what
add_season.py already expects for schedule-only (not-yet-played) games.

Usage:
    python3 convert_sportsref_schedule.py raw_schedule.xlsx 2026 --out NFL_2026_Results.xlsx
"""
import sys
import os
import argparse
import pandas as pd

from nfl_elo import TEAM_NAME_TO_ID


def _find_header_row(lines: list[str]) -> int:
    """Sports-Reference's CSV export prepends a citation line and blank
    lines before the real header -- find the actual 'Week,Day,...VisTm...'
    row rather than assuming it's line 0."""
    for i, line in enumerate(lines):
        if "VisTm" in line and "HomeTm" in line:
            return i
    raise ValueError("Could not find a header row containing 'VisTm'/'HomeTm' -- "
                      "this doesn't look like a Sports-Reference schedule export.")


def _read_sportsref_file(raw_path: str) -> pd.DataFrame:
    """Sports-Reference's .xls export is often not a real binary Excel
    file -- it's an HTML 'frameset' shell whose actual worksheet data
    lives in a SEPARATE companion file (named like
    '<basename>_files/sheet001.htm'), which is why Excel can open the
    .xls directly (it knows to stitch the two together) but pandas
    can't read the .xls alone. Try the normal path first; if that
    fails, look for the companion file next to it and read that instead.

    The CSV export has its own quirks: a citation line + blank lines
    before the real header, and two unlabeled columns (Date and the '@'
    marker) that pandas will read as 'Unnamed: N' -- both are handled
    positionally below rather than by name."""
    import os

    if raw_path.lower().endswith(".csv"):
        with open(raw_path, newline="") as f:
            lines = f.readlines()
        header_idx = _find_header_row(lines)
        return pd.read_csv(raw_path, skiprows=header_idx)

    try:
        xl = pd.ExcelFile(raw_path)
        return pd.read_excel(xl, sheet_name=xl.sheet_names[0])
    except ValueError:
        pass  # not a real binary Excel file -- fall through to the HTML path below

    base = os.path.splitext(raw_path)[0]
    candidates = [
        f"{base}_files/sheet001.htm",
        f"{base}_files/Sheet1.htm",
        f"{base}.files/sheet001.htm",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            print(f"  (read as HTML frameset -- using companion file: {candidate})")
            tables = pd.read_html(candidate)
            return max(tables, key=len)  # the real schedule table is the biggest one

    raise FileNotFoundError(
        f"'{raw_path}' looks like an HTML frameset export, but I couldn't find its "
        f"companion data file (checked: {candidates}). If you have a "
        f"'{os.path.basename(base)}_files' folder saved alongside the .xls, make sure "
        f"it's uploaded/present in the same directory -- Excel needs it to render the "
        f"sheet, and so does this script."
    )


MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
          "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
          "December": 12}


def _parse_sportsref_date(raw: str, season: int) -> pd.Timestamp:
    """Sports-Reference gives dates as 'August 6' / 'January 3' -- NO
    YEAR at all. This is the actual root cause of the January-rollover
    bug from earlier: a season labeled 2026 genuinely has no year
    printed anywhere to tell you Week 17/18 falls in January 2027, not
    2026. Apply the same domain rule established then: Jan/Feb dates
    belong to season+1 (a season can't have a game before it starts in
    September), everything else belongs to the season year itself."""
    month_name, day = raw.strip().split()
    month = MONTHS[month_name]
    year = season + 1 if month <= 2 else season
    return pd.Timestamp(year=year, month=month, day=int(day))


def convert(raw_path: str, season: int) -> pd.DataFrame:
    df = _read_sportsref_file(raw_path)

    # Column positions are fixed in Sports-Reference's export even though
    # two of them (Date, and the '@' marker) have no header name at all:
    # 0=Week 1=Day 2=Date(no year) 3=VisTm 4=Pts 5=(@ marker, unused) 6=HomeTm 7=Pts 8=Time
    cols = list(df.columns)
    df = df.rename(columns={
        cols[0]: "Week", cols[1]: "Day", cols[2]: "DateRaw",
        cols[3]: "VisTm", cols[4]: "VisPts",
        cols[6]: "HomeTm", cols[7]: "HomePts",
    })

    # Drop preseason rows (Week is 'Pre0', 'Pre1', ...) -- these never go
    # into ratings, same as the rest of this pipeline only ever handles
    # regular season ('R') and playoffs ('P').
    n_before = len(df)
    df = df[~df["Week"].astype(str).str.startswith("Pre")].copy()
    n_preseason = n_before - len(df)
    if n_preseason:
        print(f"  Dropped {n_preseason} preseason row(s) (Week Pre0/Pre1/...) -- "
              f"these don't go into ratings.")

    df["Date"] = df["DateRaw"].apply(lambda d: _parse_sportsref_date(d, season))

    missing = (set(df["VisTm"]) | set(df["HomeTm"])) - set(TEAM_NAME_TO_ID)
    if missing:
        raise ValueError(f"No TeamID mapping for: {sorted(missing)} -- add these to "
                          f"nfl_elo.py's TEAM_NAME_TO_ID before converting.")

    vis_code = df["VisTm"].map(TEAM_NAME_TO_ID)
    home_code = df["HomeTm"].map(TEAM_NAME_TO_ID)
    vis_pts, home_pts = df["VisPts"], df["HomePts"]

    round_label = "RS"  # this converter is for the regular-season sheet;
    # playoff rows (if present in the same file) would need Round derived
    # separately -- flag if that ever shows up here rather than guessing.
    type_ = "R"

    home_rows = pd.DataFrame({
        "Date": df["Date"], "Season": season, "Type": type_, "Round": round_label,
        "Team": home_code, "Opp": vis_code, "HomeAway": "H",
        "PointsFor": home_pts, "PointsAgainst": vis_pts, "OT": 0,
    })
    away_rows = pd.DataFrame({
        "Date": df["Date"], "Season": season, "Type": type_, "Round": round_label,
        "Team": vis_code, "Opp": home_code, "HomeAway": "A",
        "PointsFor": vis_pts, "PointsAgainst": home_pts, "OT": 0,
    })

    out = pd.concat([home_rows, away_rows], ignore_index=True)
    out = out.sort_values(["Date", "Team"]).reset_index(drop=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_path", help="Raw Sports-Reference schedule file (one row per game)")
    ap.add_argument("season", type=int)
    ap.add_argument("--out", default=None,
                     help="Output path (default: Results/parsed_games_<season>.xlsx)")
    args = ap.parse_args()

    out_path = args.out or f"Results/parsed_games_{args.season}.xlsx"
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    result = convert(args.raw_path, args.season)
    result.to_excel(out_path, index=False)

    n_games = len(result) // 2
    n_played = (result["PointsFor"].notna()).sum() // 2
    print(f"Converted {n_games} game(s) -> {out_path} ({len(result)} rows, "
          f"H+A perspective for each game)")
    print(f"  {n_played} already played, {n_games - n_played} still upcoming (unplayed)")

    # Quick self-check: every team should have exactly 17 total appearances,
    # and no team should host the same opponent twice while never hosting
    # the other leg -- catch it here instead of downstream.
    home_only = result[result["HomeAway"] == "H"]
    counts = home_only.groupby("Team").size()
    total_counts = result.groupby("Team").size()
    off_total = total_counts[total_counts != 17]
    if len(off_total):
        print(f"\n  WARNING: team(s) not at 17 total games: {off_total.to_dict()}")

    pair_counts = {}
    for _, row in home_only.iterrows():
        key = frozenset([row["Team"], row["Opp"]])
        pair_counts.setdefault(key, []).append(row["Team"])
    lopsided = [(k, v) for k, v in pair_counts.items() if len(v) == 2 and v[0] == v[1]]
    if lopsided:
        print(f"\n  WARNING: {len(lopsided)} pair(s) with the same team hosting both meetings:")
        for k, v in lopsided:
            print(f"    {sorted(k)}")
    if not len(off_total) and not lopsided:
        print("\n  Self-check passed: all teams at 17 games, no lopsided home/away pairs.")


if __name__ == "__main__":
    main()

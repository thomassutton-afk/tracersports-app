"""
Add a new season's games to the database, from a single command.

Usage:
    python3 add_season.py /path/to/parsed_games_2025.csv

Expects a file already in the normalized shape produced by
normalize_parsed_games.py: Date, Season, Type ('R'/'P'), Round ('RS' or
'WC'/'DV'/'CC'/'SB'), Team, Opp (stable NFL codes, e.g. "ARI" - NOT
full team names), HomeAway ('H'/'A'), PointsFor, PointsAgainst, OT
(0/1). If you're loading a brand new season for the first time, run
that normalizer on the raw source file first - this script does not
do team-name-to-code translation, "Reg"/"Playoff" label conversion, or
OT correction itself; those are one-time file-format fixes, not an
ongoing per-load step. See TEMPLATE.md for why.

A row with a real score goes into `games` (and affects ratings). A row
with everything else but NO score yet (e.g. a future game on the
schedule) goes into `schedule` instead - it is never treated as a 0-0
result, and never touches the rating engine.

It will:
  1. Auto-detect any team codes not already in the database and
     register them as brand new franchises - each gets a permanent
     synthetic team_id (e.g. "nfl_0031") and an era-scoped history
     entry starting at the earliest season the code appears in this
     file. In practice this should rarely fire once every existing
     franchise has been pre-seeded (see TEMPLATE.md section 8) - it's
     mainly here for a genuinely new expansion team down the line.
  2. Insert every completed game (deduped automatically - re-running on
     the same file is always safe).
  3. Route unplayed games to `schedule`.
  4. Rebuild the FULL ratings history from every game in the database,
     week by week (see rebuild.py / engine.py's module docstring for
     why NFL replays week-by-week rather than game-by-game).
  5. Run a handful of sanity checks and print a standings summary.

Naming a new team:
    New teams get registered with team_name == their code (e.g. "SEA")
    as a placeholder, so nothing blocks the load. Fix the display name
    afterward with:

        python3 -c "import db; c=db.connect('nfl_elo.db'); \\
            db.rename_current_history(c, 'nfl_0031', 'Seattle Seahawks'); \\
            db.upsert_team(c,'nfl_0031','Seattle Seahawks'); c.commit()"

    (Use franchise.py status to look up a code's team_id.)
"""
import sys
from pathlib import Path
import pandas as pd
import db
from rebuild import rebuild_ratings, standings, sanity_checks

DB_PATH = "nfl_elo.db"


def _read_any(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path, parse_dates=["Date"])
    else:
        xl = pd.ExcelFile(path)
        sheet = "RawData" if "RawData" in xl.sheet_names else xl.sheet_names[0]
        df = pd.read_excel(path, sheet_name=sheet)
    return df


def _register_new_teams(conn, homes: pd.DataFrame, upcoming: pd.DataFrame) -> set[str]:
    """Find any team codes in this file that don't already resolve to
    a known team_id, register each as a brand new franchise (permanent
    synthetic team_id + an era-scoped team_history entry starting at
    the earliest season that code appears in this file), and remap
    `homes`/`upcoming`'s Team/opponent columns in place from the raw
    code to the new team_id. home_code/away_code (the raw codes) are
    left untouched - those are what the engine's conf/div lookup needs,
    and a code doesn't stop being a code just because it's now aliased.
    Returns the set of raw codes that were newly registered."""
    existing_teams = {row[0] for row in conn.execute("SELECT team_id FROM teams").fetchall()}
    for df in (homes, upcoming):
        df["Team"] = df["Team"].apply(lambda c: db.resolve_team_id(conn, c))
        df["opponent"] = df["opponent"].apply(lambda c: db.resolve_team_id(conn, c))

    new_codes = ((set(homes["Team"]) | set(homes["opponent"])
                  | set(upcoming["Team"]) | set(upcoming["opponent"])) - existing_teams)
    if new_codes:
        combined = pd.concat(
            [homes[["Team", "opponent", "Season"]], upcoming[["Team", "opponent", "Season"]]],
            ignore_index=True,
        )
        code_to_new_id = {}
        for code in sorted(new_codes):
            first_season = int(combined.loc[
                (combined["Team"] == code) | (combined["opponent"] == code), "Season"
            ].min())
            code_to_new_id[code] = db.register_new_team(conn, code, code, first_season)
        for df in (homes, upcoming):
            df["Team"] = df["Team"].replace(code_to_new_id)
            df["opponent"] = df["opponent"].replace(code_to_new_id)
    return new_codes


def load_file(conn, path: str) -> tuple[dict, set[int], set[str]]:
    df = _read_any(path)

    out = pd.DataFrame()
    out["Date"] = df["Date"]
    out["Season"] = df["Season"]
    out["Type"] = df["Type"]
    out["Round"] = df["Round"]
    out["Team"] = df["Team"]
    out["opponent"] = df["Opp"]
    out["HomeAway"] = df["HomeAway"]
    out["OT"] = df["OT"] if "OT" in df.columns else 0
    out["points_for"] = df["PointsFor"] if "PointsFor" in df.columns else pd.NA
    out["points_against"] = df["PointsAgainst"] if "PointsAgainst" in df.columns else pd.NA
    df = out

    # Keep the "H" row as canonical. Neutral-site games (the Super
    # Bowl every year, played at a fixed neutral stadium - both rows
    # say "N", neither says "H") have no true home team; pick one
    # deterministically (alphabetically first team code) so each game
    # is stored exactly once, and flag it neutral so the engine skips
    # home-field advantage for it (see engine.py - home-field
    # advantage for an arbitrarily-chosen "home" team at a game that
    # isn't at anyone's home stadium was a real gap in the original
    # nfl_elo.py, which stored this flag but never actually used it).
    is_home_away = df["HomeAway"] == "H"
    is_neutral_canonical = (df["HomeAway"] == "N") & (df["Team"] < df["opponent"])
    homes = df[is_home_away | is_neutral_canonical].copy()
    homes["neutral"] = (homes["HomeAway"] == "N").astype(int)

    required = ["Date", "Season", "Type", "Team", "opponent"]
    bad_mask = homes[required].isna().any(axis=1)
    if bad_mask.any():
        print(f"WARNING: skipping {bad_mask.sum()} row(s) with missing/blank data:")
        for idx, row in homes[bad_mask].iterrows():
            print(f"  ~row {idx + 2}: {row[required].to_dict()}")
        homes = homes[~bad_mask].copy()

    # A row with everything EXCEPT a score is an upcoming/unplayed
    # game - it goes to `schedule`, never to `games`.
    has_score = homes[["points_for", "points_against"]].notna().all(axis=1)
    upcoming = homes[~has_score].copy()
    homes = homes[has_score].copy()

    # Preserve the raw stable codes (needed by engine.py's conf/div
    # lookup) BEFORE _register_new_teams remaps Team/opponent to
    # permanent team_ids.
    for frame in (homes, upcoming):
        frame["home_code"] = frame["Team"]
        frame["away_code"] = frame["opponent"]

    new_teams = _register_new_teams(conn, homes, upcoming)

    inserted = 0
    attempted = 0
    seasons = set()
    for _, r in homes.iterrows():
        attempted += 1
        round_ = None if r["Round"] == "RS" else r["Round"]
        seasons.add(int(r["Season"]))
        was_new = db.add_game(
            conn,
            d=pd.Timestamp(r["Date"]).date(),
            season=int(r["Season"]),
            type_=r["Type"],
            round_=round_,
            home_team=r["Team"],
            away_team=r["opponent"],
            home_code=r["home_code"],
            away_code=r["away_code"],
            home_pts=int(r["points_for"]),
            away_pts=int(r["points_against"]),
            ot=int(r["OT"]),
            neutral=int(r["neutral"]),
        )
        if was_new:
            inserted += 1

    scheduled = 0
    for _, r in upcoming.iterrows():
        round_ = None if r["Round"] == "RS" else r["Round"]
        seasons.add(int(r["Season"]))
        was_new = db.add_scheduled_game(
            conn,
            d=pd.Timestamp(r["Date"]).date(),
            season=int(r["Season"]),
            type_=r["Type"],
            round_=round_,
            home_team=r["Team"],
            away_team=r["opponent"],
            home_code=r["home_code"],
            away_code=r["away_code"],
            neutral=int(r["neutral"]),
        )
        if was_new:
            scheduled += 1

    pruned = db.prune_played_schedule_rows(conn)

    conn.commit()
    return (dict(attempted=attempted, inserted=inserted, scheduled=scheduled, pruned=pruned),
            seasons, new_teams)


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 add_season.py /path/to/parsed_games_YYYY.csv")
        sys.exit(1)
    path = sys.argv[1]
    if not Path(path).exists():
        print(f"File not found: {path}")
        sys.exit(1)

    conn = db.connect(DB_PATH)
    counts, seasons, new_teams = load_file(conn, path)

    print(f"Read {counts['attempted'] + counts['scheduled']} rows from {path}.")
    print(f"Inserted {counts['inserted']} new completed game(s) "
          f"({counts['attempted'] - counts['inserted']} were already in the database).")
    if counts["scheduled"]:
        print(f"Added {counts['scheduled']} upcoming (unplayed) game(s) to the schedule "
              f"- these are NOT included in ratings until they have a real score.")
    if counts["pruned"]:
        print(f"Removed {counts['pruned']} schedule placeholder(s) that now have a real result.")
    if new_teams:
        print(f"Registered new team code(s): {sorted(new_teams)} "
              f"(placeholder names set - rename them, see this script's docstring)")

    rebuild_ratings(conn)
    print("Ratings rebuilt for the full history (week by week).\n")

    warnings = sanity_checks(conn, seasons)
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("Sanity checks passed: no NaNs, no missing teams, standings look complete.\n")

    for season in sorted(seasons):
        print(f"--- {season} standings ---")
        for team, name, w, l, t, rating in standings(conn, season):
            record = f"{w:.0f}-{l:.0f}" + (f"-{t:.0f}" if t else "")
            print(f"{name:24s} {record:>8s}   Elo {rating:.2f}")
        print()


if __name__ == "__main__":
    main()

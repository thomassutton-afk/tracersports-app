"""
normalize_sr_games.py

Converts a raw Sports-Reference CFB schedule/scores export (one row per
GAME - Winner, Winner's Pts, an unlabeled site-indicator column, Loser,
Loser's Pts, Notes) into the standardized per-team-perspective shape
add_season.py expects: Date, Season, Type, Round, Team, Opp, HomeAway,
PointsFor, PointsAgainst, OT, TeamAPRank, OppAPRank - one row per team
per game (both perspectives), same convention as NFL_Elo's
normalize_parsed_games.py.

SITE-INDICATOR COLUMN: Sports-Reference's raw export has no header for
this column (it sits between the winner's points and the loser's name),
so pandas reads it in as "Unnamed: N". Its values:
    ""  (blank) -> the Winner was the HOME team
    "@"         -> the Winner was the AWAY team (played at the Loser's
                   home stadium - the Loser was actually the home team)
    "N"         -> neutral site; neither team was truly "home"

WHAT THIS DOES:
  - Emits TWO output rows per raw game row (one per team's own
    perspective), each carrying that team's own HomeAway tag
    ('H'/'A'/'N') for this game.
  - Strips and preserves the AP poll rank prefix, e.g. "(11) Penn
    State" -> name="Penn State", rank=11 -> into TeamAPRank/OppAPRank.
    Display-only; the Elo engine never reads these (see db.py's module
    docstring).
  - Derives a stable team CODE by slugifying the full team name (e.g.
    "Southern California" -> "southern-california", "Miami (FL)" ->
    "miami-fl", "Louisiana-Monroe" -> "louisiana-monroe") - CFB has no
    standard stable abbreviation the way NFL codes exist, so
    add_season.py's franchise auto-registration keys off these slugs
    going forward. A genuine program name change later goes through
    team_history/team_aliases, same as any other rename - this script
    does not need to know about that; it just slugifies whatever name
    appears in a given season's file.
  - Assigns Season as the FALL year a season is conventionally labeled
    under, even for games played in January/February of the following
    calendar year (bowl games) - date.month <= 6 means "belongs to
    last year's season."
  - Type is ALWAYS 'R' and Round is ALWAYS blank for every game,
    including bowls and conference championships - postseason
    classification (CFP rounds, bowl tiers) is a DEFERRED, separate
    process (see add_season.py's module docstring); for now every game
    counts toward ratings/standings identically, as instructed.
  - OT is hardcoded to 0 for every row - this source format carries no
    overtime flag. Revisit if/when a source with real OT data is added.

WHAT THIS DOES NOT DO:
  - No conference/division assignment (`team_conference_history` is
    populated through a separate process - this source has no
    conference column at all).
  - No FBS/FCS filtering - every team that appears (including an FCS
    opponent in a given box score) gets registered, consistent with
    the "start FBS, leave door open" scope decision.

Usage:
    python3 normalize_sr_games.py raw_sports_ref_1996.csv parsed_games_1996.csv
"""
import re
import sys

import pandas as pd

RANK_RE = re.compile(r"^\((\d+)\)\s*(.+)$")


def parse_team(raw: str) -> tuple[str, "int | None"]:
    """Split a Sports-Reference team field like '(11) Penn State' into
    (name, rank). Returns (raw, None) if there's no rank prefix - most
    teams most weeks are unranked."""
    m = RANK_RE.match(str(raw).strip())
    if m:
        return m.group(2).strip(), int(m.group(1))
    return str(raw).strip(), None


def slugify(name: str) -> str:
    """Derive a stable team code from a full name. See module docstring
    - CFB has no standard abbreviation source, so this IS the code."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def season_for_date(d) -> int:
    """The fall year a game's season is conventionally labeled under -
    e.g. a January 2, 1997 bowl game belongs to the "1996 season"."""
    return d.year - 1 if d.month <= 6 else d.year


def _find_header_row(path: str) -> int:
    """Sports-Reference's raw export has a citation-request preamble
    (and sometimes blank lines) before the real header row. Scan for
    the actual 'Rk,Wk,Date,...' header line rather than assuming it's
    line 0."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if line.startswith("Rk,Wk,Date"):
                return i
    return 0


def normalize(path: str) -> pd.DataFrame:
    header_row = _find_header_row(path)
    df = pd.read_csv(path, skiprows=header_row)

    # The raw export's unlabeled site-indicator column loads as
    # "Unnamed: N" - rename it to something addressable regardless of
    # its exact position.
    site_cols = [c for c in df.columns if c.startswith("Unnamed")]
    if site_cols:
        df = df.rename(columns={site_cols[0]: "Site"})
    else:
        df["Site"] = ""
    df["Site"] = df["Site"].fillna("")

    # Sports-Reference sometimes repeats the header row mid-file (page
    # breaks in the original HTML table); drop those, plus any row
    # missing a real Winner/Loser matchup.
    df = df[df["Winner"].notna() & df["Loser"].notna()].copy()
    df = df[df["Winner"] != "Winner"].copy()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    n_bad_dates = df["Date"].isna().sum()
    if n_bad_dates:
        print(f"WARNING: skipping {n_bad_dates} row(s) with unparseable dates.")
    df = df[df["Date"].notna()].copy()

    # The winner's and loser's points columns both come in as "Pts" in
    # the raw header, so pandas suffixes the second one "Pts.1".
    loser_pts_col = "Pts.1" if "Pts.1" in df.columns else "Pts"

    # A row with a real matchup but NO score (blank Pts on either side)
    # is a postponed, cancelled, or forfeited game that never actually
    # got played - Sports-Reference still lists it, but there's no
    # result to record. Skip these rather than crashing; they're
    # genuinely rare (a handful across 30 seasons), not a sign
    # something's wrong with the file.
    n_no_score = (df["Pts"].isna() | df[loser_pts_col].isna()).sum()
    if n_no_score:
        skipped = df[df["Pts"].isna() | df[loser_pts_col].isna()]
        print(f"WARNING: skipping {n_no_score} row(s) with no final score "
              f"(likely postponed/cancelled games):")
        for _, sr in skipped.iterrows():
            print(f"  {sr['Date'].date()}: {sr['Winner']} vs {sr['Loser']}")
    df = df[df["Pts"].notna() & df[loser_pts_col].notna()].copy()

    rows = []
    for _, r in df.iterrows():
        season = season_for_date(r["Date"])
        winner_name, winner_rank = parse_team(r["Winner"])
        loser_name, loser_rank = parse_team(r["Loser"])
        winner_code = slugify(winner_name)
        loser_code = slugify(loser_name)
        site = str(r["Site"]).strip()

        if site == "@":
            winner_ha, loser_ha = "A", "H"
        elif site == "N":
            winner_ha, loser_ha = "N", "N"
        else:
            winner_ha, loser_ha = "H", "A"

        date_str = r["Date"].date().isoformat()
        win_pts = int(r["Pts"])
        lose_pts = int(r[loser_pts_col])

        rows.append(dict(
            Date=date_str, Season=season, Type="R", Round=None,
            Team=winner_code, Opp=loser_code, HomeAway=winner_ha,
            PointsFor=win_pts, PointsAgainst=lose_pts, OT=0,
            TeamAPRank=winner_rank, OppAPRank=loser_rank,
        ))
        rows.append(dict(
            Date=date_str, Season=season, Type="R", Round=None,
            Team=loser_code, Opp=winner_code, HomeAway=loser_ha,
            PointsFor=lose_pts, PointsAgainst=win_pts, OT=0,
            TeamAPRank=loser_rank, OppAPRank=winner_rank,
        ))

    return pd.DataFrame(rows, columns=[
        "Date", "Season", "Type", "Round", "Team", "Opp", "HomeAway",
        "PointsFor", "PointsAgainst", "OT", "TeamAPRank", "OppAPRank",
    ])


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 normalize_sr_games.py raw_sports_ref.csv parsed_games_YYYY.csv")
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    out = normalize(src)
    out.to_csv(dst, index=False)
    seasons = sorted(out["Season"].unique())
    print(f"Wrote {len(out)} team-game rows ({len(out) // 2} games) to {dst}.")
    print(f"Season(s) covered: {seasons}")


if __name__ == "__main__":
    main()

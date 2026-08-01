#!/usr/bin/env python3
"""
build_cbb_db.py

Builds a SQLite database of 1995-96 D1 college basketball games from
Sports-Reference "Get table as Excel Workbook" exports (school schedule
& results pages -- .xls files that are actually HTML tables).

WORKFLOW
--------
1. For each D1 school, go to its 1995-96 schedule page on sports-reference.com/cbb
   e.g. https://www.sports-reference.com/cbb/schools/kentucky/men/1996-schedule.html
2. Click "Share & Export" (top right of the table) -> "Get table as Excel Workbook"
3. Save the downloaded file, renamed to the team's slug, e.g. "kentucky.xls"
   (sports-reference always names the download the same generic thing, so it
   MUST be renamed -- the file itself does not contain the team name)
4. Drop all renamed files into one folder, e.g. schedules_1996/
5. Run:  python build_cbb_db.py schedules_1996/ cbb_1995_96.db

WHAT IT DOES
------------
- Parses every row of every file into a "team-perspective" game record
  (this team, opponent, date, home/away/neutral, scores, type, arena, OT)
- Matches each game across the two teams' files (a Kentucky home game vs
  Duke should show up in both kentucky.xls and duke.xls) and merges them
  into one canonical row
- If a team's file wasn't downloaded (e.g. a non-D1 opponent, or a school
  you haven't gotten to yet), the game is kept as a single-sided record
  (source_count = 1) so nothing is silently dropped -- you can re-run the
  script after adding more files and it will upgrade those to source_count = 2
- Writes everything into a `games` table plus a `teams` table in SQLite
"""

import sys
import re
import sqlite3
import unicodedata
from pathlib import Path
from collections import defaultdict

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Parsing a single sports-reference export file
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace -- used ONLY
    as a matching key, never displayed."""
    name = name.replace("\u2013", "-").replace("\u2014", "-")  # en/em dash -> hyphen
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\(\d+\)", "", name)          # strip trailing AP rank e.g. "(15)"
    name = name.replace("'", "")                  # e.g. "St. John's" -> "St. Johns" -- drop, don't split
    name = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return name.strip()


def parse_schedule_file(path: Path):
    """Parse one team's exported schedule file into a list of raw game dicts."""
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("tbody tr")

    team_name = path.stem.replace("_", " ").replace("-", " ").strip()

    games = []
    for row in rows:
        if row.get("class") and "thead" in row.get("class"):
            continue  # repeated header row sports-reference sometimes injects

        def cell(stat):
            el = row.find(attrs={"data-stat": stat})
            return el.get_text(strip=True) if el else ""

        date_el = row.find(attrs={"data-stat": "date_game"})
        date_iso = date_el.get("csk") if date_el is not None else None
        if not date_iso:
            continue  # skip malformed / blank rows

        game_type = cell("game_type") or "REG"
        location_flag = cell("game_location")  # '@' = away, 'N' = neutral, '' = home
        opponent = cell("opp_name")
        opponent = re.sub(r"\s*\(\d+\)\s*$", "", opponent).strip()  # strip AP rank
        team_pts = cell("pts")
        opp_pts = cell("opp_pts")
        ot = cell("overtimes")
        arena = cell("arena")
        result = cell("game_result")  # W / L

        if not opponent or not team_pts or not opp_pts:
            continue  # cancelled / no-result row

        games.append({
            "team": team_name,
            "team_key": normalize_name(team_name),
            "opponent": opponent,
            "opp_key": normalize_name(opponent),
            "date": date_iso,
            "game_type": game_type,
            "location_flag": location_flag,
            "team_pts": int(team_pts),
            "opp_pts": int(opp_pts),
            "result": result,
            "ot": ot,
            "arena": arena,
        })
    return team_name, games


# ---------------------------------------------------------------------------
# Merging team-perspective records into canonical games
# ---------------------------------------------------------------------------

# Some opponent references use a full/expanded name where a team's own file
# uses an abbreviation (or vice versa) -- these share no character sequence
# in common, so no amount of fuzzy/normalized matching can bridge them on
# its own. Add entries here as {alternate form: the name actually used for
# that team's own filename/teams-table entry}.
NAME_ALIASES = {
    "Maryland-Baltimore County": "UMBC",
    "Virginia Military Institute": "VMI",
}


def to_canonical(rec, name_lookup=None):
    """Turn one team-perspective record into a canonical (home, away, scores) row.

    name_lookup, if given, maps normalize_name(key) -> the ONE authoritative
    display name for that team (built from every team's own schedule file).
    This matters because a merged game's raw text could come from either
    side's file -- without resolving through name_lookup, the SAME real team
    could end up displayed under different spellings across different games
    (their own file's spelling for some games, whatever punctuation an
    opponent happened to use for others), which breaks any later exact-name
    lookup against the teams table (e.g. the Elo engine's D1/D2 check).
    """
    if rec["location_flag"] == "@":
        home_raw, away_raw = rec["opponent"], rec["team"]
        home_pts, away_pts = rec["opp_pts"], rec["team_pts"]
        neutral = 0
    elif rec["location_flag"] == "N":
        home_raw, away_raw = sorted([rec["team"], rec["opponent"]])
        if home_raw == rec["team"]:
            home_pts, away_pts = rec["team_pts"], rec["opp_pts"]
        else:
            home_pts, away_pts = rec["opp_pts"], rec["team_pts"]
        neutral = 1
    else:
        home_raw, away_raw = rec["team"], rec["opponent"]
        home_pts, away_pts = rec["team_pts"], rec["opp_pts"]
        neutral = 0

    home_key = normalize_name(home_raw)
    away_key = normalize_name(away_raw)
    name_lookup = name_lookup or {}
    home = name_lookup.get(home_key, home_raw)
    away = name_lookup.get(away_key, away_raw)

    return {
        "date": rec["date"],
        "game_type": rec["game_type"],
        "home": home, "away": away,
        "home_key": home_key, "away_key": away_key,
        "home_pts": home_pts, "away_pts": away_pts,
        "neutral": neutral,
        "ot": rec["ot"],
        "arena": rec["arena"],
    }


def build_database(folder: Path, db_path: Path):
    files = sorted(folder.glob("*.xls")) + sorted(folder.glob("*.xlsx")) + sorted(folder.glob("*.html"))
    if not files:
        print(f"No .xls/.xlsx/.html files found in {folder}")
        return

    all_raw = []
    team_display_names = {}
    for f in files:
        team_name, games = parse_schedule_file(f)
        team_display_names[normalize_name(team_name)] = team_name
        all_raw.extend(games)
        print(f"  parsed {f.name}: {len(games)} games ({team_name})")

    # register alternate-name aliases (abbreviation <-> full name, etc.) so
    # they resolve to the same canonical entry -- only if that canonical
    # team's own file was actually loaded
    for alt_name, canonical_name in NAME_ALIASES.items():
        canonical_key = normalize_name(canonical_name)
        if canonical_key in team_display_names:
            team_display_names[normalize_name(alt_name)] = team_display_names[canonical_key]

    # group team-perspective records into canonical games keyed by
    # (date, unordered pair of team keys). name_lookup ensures every game
    # involving a known team displays that team's ONE registered name,
    # regardless of which file's spelling the raw record came from.
    grouped = defaultdict(list)
    for rec in all_raw:
        canon = to_canonical(rec, name_lookup=team_display_names)
        key = (canon["date"], frozenset([canon["home_key"], canon["away_key"]]))
        grouped[key].append(canon)

    final_games = []
    for key, versions in grouped.items():
        if len(versions) >= 2:
            # two independent sources agreeing -- trust it, flag mismatches
            v = versions[0]
            mismatched = any(
                v2["home_pts"] != v["home_pts"] or v2["away_pts"] != v["away_pts"]
                for v2 in versions[1:]
            )
            v["source_count"] = len(versions)
            v["score_mismatch"] = int(mismatched)
        else:
            v = versions[0]
            v["source_count"] = 1
            v["score_mismatch"] = 0
        final_games.append(v)

    # write to sqlite
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        DROP TABLE IF EXISTS games;
        DROP TABLE IF EXISTS teams;

        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_name TEXT UNIQUE
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            date TEXT,
            season TEXT DEFAULT '1995-96',
            game_type TEXT,
            home_team TEXT,
            away_team TEXT,
            neutral_site INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            ot TEXT,
            arena TEXT,
            source_count INTEGER,
            score_mismatch INTEGER
        );
    """)

    team_names = sorted(team_display_names.values())
    cur.executemany("INSERT OR IGNORE INTO teams (team_name) VALUES (?)",
                     [(t,) for t in team_names])

    cur.executemany("""
        INSERT INTO games (date, game_type, home_team, away_team, neutral_site,
                            home_score, away_score, ot, arena, source_count, score_mismatch)
        VALUES (:date, :game_type, :home, :away, :neutral,
                :home_pts, :away_pts, :ot, :arena, :source_count, :score_mismatch)
    """, final_games)

    conn.commit()

    n_games = cur.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    n_teams = cur.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    n_single = cur.execute("SELECT COUNT(*) FROM games WHERE source_count = 1").fetchone()[0]
    n_mismatch = cur.execute("SELECT COUNT(*) FROM games WHERE score_mismatch = 1").fetchone()[0]
    conn.close()

    print(f"\nDone -> {db_path}")
    print(f"  teams loaded:            {n_teams}")
    print(f"  games written:           {n_games}")
    print(f"  single-sourced games:    {n_single}  (opponent's file not yet loaded)")
    print(f"  score mismatches:        {n_mismatch}  (worth spot-checking)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python build_cbb_db.py <folder_of_exports> <output.db>")
        sys.exit(1)
    build_database(Path(sys.argv[1]), Path(sys.argv[2]))

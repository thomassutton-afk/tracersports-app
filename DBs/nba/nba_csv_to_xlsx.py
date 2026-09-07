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
import os
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
    # Early BAA/NBA teams -- confirmed against basketball-reference.com
    # standings/schedule pages directly (not the APBR convention, which
    # uses DIFFERENT codes for several of these, e.g. APBR's "SLB" vs BR's
    # actual "STB" for the St. Louis Bombers -- so APBR's list is NOT a
    # safe stand-in for BR-sourced data like yours).
    "Philadelphia Warriors": "PHW",
    "Washington Capitols": "WSC",
    "Rochester Royals": "ROC",
    "Syracuse Nationals": "SYR",
    "St. Louis Bombers": "STB",
    "Chicago Stags": "CHS",
    "Cleveland Rebels": "CLR",
    "Detroit Falcons": "DTF",
    "Pittsburgh Ironmen": "PIT",
    "Toronto Huskies": "TRH",
    "Providence Steamrollers": "PRO",
    "Baltimore Bullets": "BLB",  # the original 1947-54 franchise (BAA/NBA)
                                  # -- NOT the same code as the later
                                  # 1963-73 Baltimore Bullets, if you ever
                                  # add that one, verify separately.
    "Minneapolis Lakers": "MNL",
    "Fort Wayne Pistons": "FTW",
    "Indianapolis Olympians": "INO",
    "Indianapolis Jets": "INJ",
    "Anderson Packers": "AND",
    "Tri-Cities Blackhawks": "TRI",
    "Sheboygan Red Skins": "SHE",
    "Waterloo Hawks": "WAT",
    "Milwaukee Hawks": "MLH",   # Tri-Cities Blackhawks relocated here in 1951
    "St. Louis Hawks": "STL",   # Milwaukee Hawks relocated here in 1955 (pre-Atlanta)
    # NOTE: the original 1948-50 Denver Nuggets (BR code "DNN") are
    # DELIBERATELY NOT mapped here under the plain name "Denver Nuggets",
    # because that string is already mapped above to the MODERN Denver
    # Nuggets ("DEN"). Adding a second "Denver Nuggets" key would silently
    # overwrite that mapping and corrupt every modern Nuggets game you
    # ever process with this script -- a real bug I almost introduced.
    # If your 1950 season CSV uses the plain name "Denver Nuggets" for the
    # original franchise, use --team-alias "Denver Nuggets=DNN" for that
    # run only (see --help) instead of editing this dict.
}


def parse_date(s):
    # e.g. "Fri Nov 4 1994"
    return datetime.strptime(s.strip(), "%a %b %d %Y")


def load_games(csv_path):
    """
    Return list of dicts: date, visitor, vpts, home, hpts, ot(bool).

    Column positions are located by HEADER NAME, not fixed index, because
    different scrapes/eras of basketball-reference schedule exports add or
    drop columns (e.g. some include a "Start (ET)" column right after
    Date; the "Box Score"/OT columns are unnamed in the header but their
    position shifts along with everything else). Locating "Visitor/Neutral"
    and "Home/Neutral" by name, and "Box Score" per-row, makes this
    resilient to that instead of assuming a fixed layout.
    """
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

    header = [h.strip() for h in rows[header_idx]]
    try:
        v_idx = header.index("Visitor/Neutral")
    except ValueError:
        sys.exit("Could not find a 'Visitor/Neutral' column in the header.")
    if header[v_idx + 2] != "Home/Neutral":
        sys.exit(f"Expected 'Home/Neutral' two columns after 'Visitor/Neutral' "
                  f"(found {header[v_idx + 2]!r}). This file's layout doesn't "
                  f"match what this script expects -- please share a sample row.")
    vpts_idx, h_idx, hpts_idx = v_idx + 1, v_idx + 2, v_idx + 3

    attend_idx = None
    for i in range(hpts_idx + 1, len(header)):
        if header[i].lower().startswith("attend"):
            attend_idx = i
            break
    if attend_idx is None:
        attend_idx = len(header)  # no Attend. column found; scan to end of row

    games = []
    skipped = []
    for line_no, r in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if not r or len(r) < 5 or not r[0].strip():
            continue
        try:
            date = parse_date(r[0])
            visitor = r[v_idx].strip()
            vpts = int(r[vpts_idx])
            home = r[h_idx].strip()
            hpts = int(r[hpts_idx])

            # Find the "Box Score" cell in this row's box-score/OT block;
            # the OT indicator (if any) is the cell right after it.
            ot_flag = 0
            for i in range(hpts_idx + 1, min(attend_idx, len(r))):
                if r[i].strip().lower() == "box score":
                    if i + 1 < min(attend_idx, len(r)) and r[i + 1].strip():
                        ot_flag = 1
                    break
        except (ValueError, IndexError) as e:
            skipped.append((line_no, r, e))
            continue
        games.append({
            "date": date, "visitor": visitor, "vpts": vpts,
            "home": home, "hpts": hpts, "ot": ot_flag,
        })

    if skipped:
        print(f"\nSkipped {len(skipped)} unparseable row(s) -- these did NOT make it "
              f"into the output. Inspect them (often a cancelled/forfeited game, or a "
              f"team that folded mid-season needs special handling):")
        for line_no, r, e in skipped:
            print(f"  line {line_no}: {r}  ({e})")
        print()

    if not games:
        sys.exit("No games were successfully parsed from this file -- check the "
                  "skipped-row messages above (if any) or the file's column layout.")

    return games


def check_all_teams_known(games, overrides=None):
    """
    Scan every team name in the file up front and report ALL unknown ones
    at once, instead of failing on the first one -- saves re-running the
    script once per newly-discovered team name.
    """
    overrides = overrides or {}
    unknown = sorted({g["visitor"] for g in games if g["visitor"] not in TEAM_ABBR and g["visitor"] not in overrides}
                      | {g["home"] for g in games if g["home"] not in TEAM_ABBR and g["home"] not in overrides})
    if unknown:
        print("Unknown team name(s) -- add these to TEAM_ABBR in the script "
              "(verify each abbreviation at basketball-reference.com/teams/ first):")
        for name in unknown:
            print(f"  - {name!r}")
        sys.exit(1)


def detect_playoff_start(games, max_opponents=5):
    """
    Structural heuristic (replaces the old gap-based one): scan backward
    from the end of the season and find the EARLIEST date such that no
    team has faced more than `max_opponents` distinct opponents in the
    remaining (tail) games. Playoff teams only ever face a small, bounded
    set of opponents (roughly one per round); regular-season teams face
    nearly the whole league. This doesn't depend on there being a
    schedule gap at all, which the old heuristic required -- some early
    seasons (e.g. 1946-47) played almost daily right through the reg
    season -> playoff transition, so the "biggest gap" heuristic locked
    onto the first small in-season gap (e.g. an off day in mid-March)
    instead of the real boundary in early April, silently producing a
    playoff-start weeks too early.

    This is monotonic: as the tail grows (the candidate start date moves
    earlier), each team's opponent set can only grow, never shrink -- so
    once the threshold is exceeded it stays exceeded for every earlier
    date too. That means a single backward pass finds the true boundary
    without any gap-guessing, tie-breaking, or lucky scheduling required.

    Returns (start_date, (team, opponent_count)) for the boundary found,
    or (None, None) if no date in the season satisfies the threshold at
    all (e.g. a season with no clean playoff bracket -- try raising
    max_opponents, or fall back to --playoff-start).
    """
    games_by_date = defaultdict(list)
    for g in games:
        games_by_date[g["date"]].append(g)
    dates_desc = sorted(games_by_date.keys(), reverse=True)

    opponents = defaultdict(set)
    best_start, best_diag = None, None
    for d in dates_desc:
        for g in games_by_date[d]:
            opponents[g["visitor"]].add(g["home"])
            opponents[g["home"]].add(g["visitor"])
        worst_team, worst_count = max(
            ((t, len(o)) for t, o in opponents.items()), key=lambda x: x[1]
        )
        if worst_count > max_opponents:
            break
        best_start, best_diag = d, (worst_team, worst_count)
    return best_start, best_diag


def abbr(team_name, overrides=None):
    if overrides and team_name in overrides:
        return overrides[team_name]
    if team_name not in TEAM_ABBR:
        sys.exit(f"Unknown team name '{team_name}'. Add it to TEAM_ABBR in the script.")
    return TEAM_ABBR[team_name]


def load_tiebreakers(path):
    """
    Same CSV format as --manual-rounds (Team1,Team2,Round[,StartDate,EndDate]),
    but used as a light override LAYERED ON TOP of the automatic bye-aware
    assign_rounds(), rather than replacing it. Use this for a season that's
    otherwise clean (auto-detects fine) except for one or two preliminary
    tiebreaker/play-in games that would otherwise get miscounted as a real
    round-1 series -- e.g. 1950's two Central Division tiebreakers.

    A fractional Round (e.g. 0.5) is treated as NON-PROGRESSING: the game
    gets tagged with that Round, but doesn't count toward either team's
    "rounds reached" for the automatic algorithm, so their real next
    series still correctly lands on round 1. A whole-number Round DOES
    count toward progression, same as an automatically computed round --
    use that if the automatic algorithm gets a specific pair wrong for
    some other reason.

    NOT for a pair that meets twice (once in the override, once for real)
    -- that needs the full --manual-rounds file with StartDate/EndDate
    instead, since this mechanism only stores one forced round per pair.
    """
    return load_manual_rounds(path)


def _resolve_forced_round(overrides, key, date):
    """Look up a forced round for `key` (a frozenset team pair) whose
    date range (if any) covers `date`. Returns None if no override
    applies -- normal automatic computation should proceed."""
    if not overrides:
        return None
    entries = overrides.get(key)
    if not entries:
        return None
    candidates = [rnd for (rnd, start, end) in entries
                  if (start is None or date >= start) and (end is None or date <= end)]
    return candidates[0] if len(candidates) == 1 else None


def assign_rounds(playoff_games, overrides=None, tiebreakers=None):
    """
    playoff_games: list of game dicts, already sorted by date.

    Bye-aware structural method: a SERIES' round number is 1 + the highest
    round either of its two participants has already reached (0 if neither
    has played a playoff game yet). Because playoff_games is chronological,
    by the time a team's next series starts, any prior series it (or its
    new opponent) finished has already been assigned its round -- so a
    team with a bye (its first game is against an opponent who already
    won a round) correctly lands in that later round, rather than being
    miscounted as "round 1" just because it's THAT team's first game. This
    was the old method's failure mode (see git history / prior version:
    counting each team's Nth distinct opponent independently, which
    disagreed whenever one side of a series had a bye and the other
    didn't -- confirmed for 1947, where two teams enter directly at what
    the real bracket calls the Semifinals).

    `tiebreakers`, if given (see load_tiebreakers), forces specific pairs
    to a specific round -- fractional rounds (e.g. 0.5) don't count
    toward either team's progression, so the automatic method still gets
    their REAL next round right.

    Only assumes: a clean, non-overlapping single-elimination bracket
    where a pair of teams meets at most once per postseason at this
    round-counting level (see load_manual_rounds's StartDate/EndDate
    mechanism for seasons where a pair genuinely meets twice, e.g. a
    tiebreaker followed by a real series) and no team plays two series
    concurrently. Returns (round_lookup, team_series_count) -- the latter
    is used by check_round_assignment_sane to catch brackets that aren't
    actually clean single-elimination (e.g. a genuine "runners-up" format
    where a team plays two separate series at the same structural stage:
    that shows up here as one team accumulating more series than there
    are rounds, since each new series a team starts always gets a
    strictly higher round number than any series it's already played).
    """
    team_round_reached = defaultdict(int)
    team_series_count = defaultdict(int)
    series_round = {}
    round_lookup = {}

    for g in playoff_games:
        vteam, hteam = abbr(g["visitor"], overrides), abbr(g["home"], overrides)
        key = frozenset((vteam, hteam))
        if key not in series_round:
            forced = _resolve_forced_round(tiebreakers, key, g["date"])
            if forced is not None:
                this_round = forced
                progresses = float(forced).is_integer()
            else:
                this_round = max(team_round_reached[vteam], team_round_reached[hteam]) + 1
                progresses = True
            series_round[key] = this_round
            if progresses:
                team_round_reached[vteam] = this_round
                team_round_reached[hteam] = this_round
                team_series_count[vteam] += 1
                team_series_count[hteam] += 1
        round_lookup[id(g)] = series_round[key]

    return round_lookup, team_series_count


def check_round_assignment_sane(round_lookup, team_series_count, max_plausible_round=4):
    """
    Refuse to proceed if the bye-aware method's core assumption -- a
    clean, non-overlapping single-elimination bracket -- doesn't hold.

    Unlike the old opponent-counting method, this one can't produce a
    same-series disagreement (a series' round is computed once, not once
    per team), so the failure signal is different: a team playing MORE
    series than there are plausible rounds. That can only happen if the
    bracket isn't really single-elimination -- e.g. a genuine "runners-up"
    format where a team plays two separate series at what's structurally
    the same stage, or a round-robin pool (confirmed one-off case: 1954's
    three-team round robin per division). Aborts with an explanation
    instead of writing a file with wrong Round values.
    """
    max_round = max(round_lookup.values(), default=0)
    overplayed = {t: c for t, c in team_series_count.items() if c > max_plausible_round}
    if overplayed or max_round > max_plausible_round:
        lines = [
            "",
            "REFUSING TO WRITE OUTPUT: the playoff round-assignment method's",
            "assumption (a clean, non-overlapping single-elimination bracket,",
            "byes allowed) does not hold for this season's data.",
            "",
            "This is a KNOWN issue for some early NBA seasons -- confirmed",
            "one-offs: 1950 (transitional 3-division format), 1954 (three-team",
            "round robin per division, unique in NBA history). Other seasons",
            "with non-elimination formats may have the same problem -- check",
            "each one rather than assuming.",
            "",
            f"Highest round number computed: {max_round} (only trusted up to "
            f"{max_plausible_round}).",
        ]
        if overplayed:
            lines.append(f"{len(overplayed)} team(s) played more series than there are "
                          f"plausible rounds -- a team can't do that in a clean single-"
                          f"elimination bracket, even with byes:")
            for t, c in sorted(overplayed.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  {t}: {c} series")
        lines += [
            "",
            "This season's playoffs need round numbers assigned by hand (from",
            "the actual bracket -- basketball-reference's playoff pages show it)",
            "rather than computed. No file was written.",
        ]
        sys.exit("\n".join(lines))


def load_manual_rounds(path):
    """
    Read a hand-built team-pair -> round mapping from a CSV with columns
    Team1,Team2,Round (using the same abbreviations as TEAM_ABBR), plus two
    OPTIONAL columns StartDate,EndDate (YYYY-MM-DD).

    Returns dict: frozenset({team1, team2}) -> list of (round, start, end).

    Most pairs only ever meet once per postseason, so a single dateless row
    (StartDate/EndDate blank) is enough and matches any game between that
    pair -- this is the common case, e.g. NYK,CLR,1.

    Some early seasons had a preliminary tiebreaker/play-in game that could
    put the SAME pair of teams into two different rounds (confirmed for
    1948: Baltimore and Chicago met in a one-game Western Division
    tiebreaker on 3/25, then again in a full Semifinals series in April --
    with no dates, a plain team-pair lookup can't tell those two rounds
    apart). For pairs like that, give each row a StartDate/EndDate spanning
    just that series/game so the right game lands in the right round, e.g.:
        BLB,CHS,1,1948-03-25,1948-03-25
        BLB,CHS,3,1948-04-07,1948-04-08

    Round accepts fractional values (e.g. 0.5) for play-in/tiebreaker-style
    games that precede round 1 but shouldn't be counted as a full playoff
    round -- matching the convention already used elsewhere in this
    pipeline (WNBA Commissioner's Cup games, modern play-in games). Use
    this for any preliminary/seeding game before the main bracket starts,
    e.g. 1948's Western Division Tiebreaker (BLB vs CHS, WSC vs CHS):
        BLB,CHS,0.5,1948-03-25,1948-03-25
        WSC,CHS,0.5,,
    """
    mapping = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t1, t2, rnd_s = row["Team1"].strip(), row["Team2"].strip(), row["Round"].strip()
            rnd = float(rnd_s) if "." in rnd_s else int(rnd_s)
            start_s = (row.get("StartDate") or "").strip()
            end_s = (row.get("EndDate") or "").strip()
            start_d = datetime.strptime(start_s, "%Y-%m-%d") if start_s else None
            end_d = datetime.strptime(end_s, "%Y-%m-%d") if end_s else None
            mapping[frozenset((t1, t2))].append((rnd, start_d, end_d))
    return mapping


def build_rows(games, season, playoff_start, overrides=None, manual_rounds=None,
                tiebreakers=None, exclude_teams=None):
    rows = []
    exclude_teams = exclude_teams or set()

    def _is_excluded(g):
        return (abbr(g["visitor"], overrides) in exclude_teams
                or abbr(g["home"], overrides) in exclude_teams)

    playoff_games = sorted([g for g in games if g["date"] >= playoff_start and not _is_excluded(g)],
                            key=lambda g: g["date"])

    if manual_rounds is not None:
        round_lookup = {}
        missing = set()
        ambiguous = []
        for g in playoff_games:
            vteam, hteam = abbr(g["visitor"], overrides), abbr(g["home"], overrides)
            key = frozenset((vteam, hteam))
            entries = manual_rounds.get(key)
            if not entries:
                missing.add((vteam, hteam))
                continue
            candidates = [rnd for (rnd, start, end) in entries
                          if (start is None or g["date"] >= start)
                          and (end is None or g["date"] <= end)]
            if not candidates:
                missing.add((vteam, hteam))
                continue
            if len(candidates) > 1:
                ambiguous.append((g, vteam, hteam, candidates))
                continue
            round_lookup[id(g)] = candidates[0]
        if missing or ambiguous:
            lines = []
            if missing:
                lines.append("Some playoff matchups aren't in your --manual-rounds file "
                              "(or no entry's date range covers this game):")
                for vteam, hteam in sorted(missing):
                    lines.append(f"  {vteam} vs {hteam}")
            if ambiguous:
                lines.append("Some games match multiple --manual-rounds entries for the same "
                              "pair -- this pair meets more than once (e.g. a tiebreaker/play-in "
                              "followed by a real series); add StartDate/EndDate columns to "
                              "disambiguate:")
                for g, vteam, hteam, candidates in ambiguous:
                    lines.append(f"  {g['date'].date()} {vteam} vs {hteam}: could be round(s) {candidates}")
            lines.append("Add/fix them (Team1,Team2,Round[,StartDate,EndDate]) and re-run.")
            sys.exit("\n".join(lines))
    else:
        round_lookup, team_series_count = assign_rounds(playoff_games, overrides, tiebreakers)
        check_round_assignment_sane(round_lookup, team_series_count)

    for g in sorted(games, key=lambda g: g["date"]):
        vteam, hteam = abbr(g["visitor"], overrides), abbr(g["home"], overrides)
        is_playoff = g["date"] >= playoff_start and not _is_excluded(g)
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
                     help="YYYY-MM-DD. If omitted, auto-detected structurally (see "
                          "--max-playoff-opponents).")
    ap.add_argument("--max-playoff-opponents", type=int, default=4,
                     help="Auto-detection threshold: the max distinct opponents any "
                          "one team may face after the detected playoff-start date. "
                          "Default 5 covers up to ~4 rounds plus a bit of slack. Raise "
                          "this if auto-detection fails or looks wrong for an unusual "
                          "playoff format (e.g. round-robin pools); lower it if it's "
                          "still catching stray regular-season games.")
    ap.add_argument("--team-alias", action="append", default=[],
                     metavar="NAME=CODE",
                     help="Override/add a team-name-to-abbreviation mapping for THIS RUN "
                          "only, without editing TEAM_ABBR in the script. Repeatable. "
                          "Use this for a name that's genuinely ambiguous across eras -- "
                          "e.g. --team-alias \"Denver Nuggets=DNN\" when processing a "
                          "1949-50 file, since the plain name 'Denver Nuggets' is "
                          "permanently mapped to the modern franchise (DEN) in the script "
                          "to avoid corrupting modern-era data by default.")
    ap.add_argument("--manual-rounds", type=str, default=None,
                     help="Path to a CSV with columns Team1,Team2,Round giving the playoff "
                          "round for each matchup by hand, bypassing the automatic "
                          "single-elimination-bracket detection entirely. Use this whenever "
                          "the script refuses to write output because the bracket assumption "
                          "doesn't hold (confirmed for 1947, 1948; check others). Get the "
                          "pairings from basketball-reference's '...{LEAGUE}_{YEAR}_standings.html' "
                          "page, which lists every series under a 'Playoff Series' heading.")
    ap.add_argument("--tiebreakers", type=str, default=None,
                     help="Path to a CSV, same format as --manual-rounds, but layered ON TOP "
                          "of automatic detection instead of replacing it. Use this for a "
                          "season that otherwise auto-detects fine except for one or two "
                          "preliminary tiebreaker/play-in games (e.g. 1950's two Central "
                          "Division tiebreakers) that would otherwise get miscounted as a real "
                          "round-1 series. Give those rows a fractional Round (e.g. 0.5) so "
                          "they don't count toward either team's progression. NOT for a pair "
                          "that meets twice (tiebreaker then real series) -- that needs the "
                          "full --manual-rounds file with StartDate/EndDate instead.")
    ap.add_argument("--exclude-teams", type=str, default=None,
                     help="Comma-separated team abbreviations (TEAM_ABBR codes) to drop from "
                          "consideration entirely for this run. Use this when a team that did "
                          "NOT make the playoffs has one or two trailing regular-season games "
                          "that happen to fall on/after the real playoff-start date (a single "
                          "global date cutoff can't separate these, since a non-qualifying "
                          "team's schedule isn't guaranteed to end before the qualifiers' "
                          "postseason begins) -- confirmed for 1953, where Milwaukee Hawks "
                          "played Fort Wayne and Indianapolis a day or two into what was "
                          "otherwise a clean playoff bracket for the 8 real qualifiers, "
                          "corrupting their round counts. Diagnose this by looking for a team "
                          "appearing in only ONE series with exactly one distinct opponent "
                          "each -- unlike a real tiebreaker (also one game) a straggler shows "
                          "up against teams who are each independently mid-series with someone "
                          "else already.")
    args = ap.parse_args()

    overrides = {}
    for item in args.team_alias:
        if "=" not in item:
            sys.exit(f"--team-alias must be in the form NAME=CODE, got: {item!r}")
        name, code = item.split("=", 1)
        overrides[name.strip()] = code.strip()

    manual_rounds = load_manual_rounds(args.manual_rounds) if args.manual_rounds else None
    tiebreakers = load_tiebreakers(args.tiebreakers) if args.tiebreakers else None
    exclude_teams = {t.strip() for t in args.exclude_teams.split(",")} if args.exclude_teams else set()

    games = load_games(args.input_csv)
    print(f"Loaded {len(games)} games from {args.input_csv} "
          f"({games[0]['date'].date()} to {games[-1]['date'].date()}).")
    check_all_teams_known(games, overrides)

    if args.playoff_start:
        playoff_start = datetime.strptime(args.playoff_start, "%Y-%m-%d")
    else:
        playoff_start, diag = detect_playoff_start(games, args.max_playoff_opponents)
        if playoff_start is None:
            sys.exit(f"Could not auto-detect playoff start: no date in this season keeps "
                      f"every team's opponent count at or below "
                      f"--max-playoff-opponents={args.max_playoff_opponents}. Try raising "
                      f"that threshold, or pass --playoff-start explicitly.")
        worst_team, worst_count = diag
        print(f"Auto-detected playoff start: {playoff_start.date()}  "
              f"(widest case: {worst_team} faced {worst_count} distinct opponent(s) after "
              f"this date -- verify this is correct, or pass --playoff-start / "
              f"--max-playoff-opponents to override)")

    def _excluded(g):
        return abbr(g["visitor"], overrides) in exclude_teams or abbr(g["home"], overrides) in exclude_teams

    n_reg = sum(1 for g in games if g["date"] < playoff_start or _excluded(g))
    n_playoff = sum(1 for g in games if g["date"] >= playoff_start and not _excluded(g))
    print(f"Regular season games: {n_reg}, Playoff games: {n_playoff}")

    rows = build_rows(games, args.season, playoff_start, overrides, manual_rounds, tiebreakers, exclude_teams)

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

    out_dir = os.path.dirname(args.output_xlsx)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    wb.save(args.output_xlsx)
    print(f"Wrote {len(rows)} rows to {args.output_xlsx}")


if __name__ == "__main__":
    main()

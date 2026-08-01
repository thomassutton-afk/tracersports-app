"""
NFL "Continelo" Elo rating engine.

This is a faithful Python re-implementation of the Elo system found in the
`RawData` table of NFL_Continelo_test.xlsx. It reproduces, column-for-column,
the same calculations the workbook performs with Excel formulas:

    PreGmRate / OppPreGmRate  -> column N / O
    ExpectedWin%              -> column P
    MOV                       -> column T
    Result                    -> column U
    Accuracy                  -> column V   (diagnostic only)
    Test (log-loss)           -> column W   (diagnostic only)
    MOVMult                   -> column X
    POMult                    -> column Y
    Keff                      -> column Z
    RatingChange               -> column AA
    PostGmRate                -> column AB
    W/L/T                     -> columns AC/AD/AE

Model parameters (from the workbook's named ranges, sheet RawData!AQ1:AQ4):
    k       = 46      Kmax -- ceiling of the per-row K decay (was a flat
                       base K-factor; now decayed toward k_floor over the
                       course of the season, see decayed_k())
    k_floor = 36.2    floor K decays to by the last game of the regular
                       season (fraction-of-season decay, robust to the
                       2021 16->17 game rule change -- see season_length())
    hfa     = 72      home field advantage, in rating points
    alpha   = 0.3     season carry-over weight (new season rating blends
                      alpha * last season's final rating with (1-alpha) * base)
    base    = 1500    starting / fallback rating
    rest_minor = 6    rest_adj for a 1-4 day rest differential
    rest_major = 24   rest_adj for a 6+ day rest differential (bye week+)

k_floor/rest_minor/rest_major are starting priors, not final -- tune via
coordinate ascent against Brier score on the 1996-2005 window only, with
2006-2025 held out as the true out-of-sample test.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# ----------------------------------------------------------------------
# Model parameters (named ranges in the workbook)
# ----------------------------------------------------------------------
K = 46          # locked Kmax (was flat K=20; now the ceiling of a per-game decay)
HFA = 72        # locked
ALPHA = 0.3     # locked
BASE = 1500.0

# K decay (Option 2: fraction-of-season, not fixed-slope -- see K_FLOOR note
# below). Starting priors, tune both against Brier on 1996-2005 only.
K_FLOOR = 36.2       # floor K reaches by the last game of the regular season

# Rest adjustment (Option 3: tiered, not linear -- see rest_adj() below).
# Starting priors, tune both against Brier on 1996-2005 only.
REST_MINOR = 6.0     # applied for a 1-4 day rest differential (short week)
REST_MAJOR = 24.0    # applied for a 6+ day rest differential (bye week or bigger)

# Conference/Division game multipliers used in Keff
DIV_GAME_MULT = 1.1
CONF_GAME_MULT = 1.02

# Playoff round multipliers (POMult), keyed off the `Round` column when
# `Type` == "P" (playoff). Any round not listed defaults to 1.0.
PLAYOFF_ROUND_MULT = {
    "WC": 1.1,
    "DV": 1.2,
    "CC": 1.35,
    "SB": 1.5,
}


def season_length(season: int) -> int:
    """Regular-season game count. The league expanded 16 -> 17 games in
    2021; K-decay needs this because it's a hardcoded fraction denominator,
    not a fixed per-game slope, so it stays correct across the rule change
    without needing separate pre/post-2021 logic anywhere else."""
    return 17 if season >= 2021 else 16


def decayed_k(kmax: float, kfloor: float, games_played: int, season: int) -> float:
    """K = Kmax - (Kmax - Kfloor) * fraction of season played so far.
    games_played is 1-indexed and continues into the playoffs; clamped at
    1.0 so K never decays past the floor once the regular season ends."""
    length = season_length(season)
    frac = min(games_played, length) / length
    return kmax - (kmax - kfloor) * frac


def rest_adj(days_off: Optional[float], opp_days_off: Optional[float]) -> float:
    """Tiered rest adjustment (Option 3). 0 for equal rest; +/-REST_MINOR
    for a 1-4 day differential (short week); +/-REST_MAJOR for 6+ days
    (bye week or bigger). No 5-day case exists in the data, so it falls
    into the minor tier by not meeting the >=6 threshold. First game of a
    season has no prior game (NaN on both sides) -> no adjustment."""
    if days_off is None or opp_days_off is None or pd.isna(days_off) or pd.isna(opp_days_off):
        return 0.0
    diff = days_off - opp_days_off
    if diff == 0:
        return 0.0
    magnitude = REST_MAJOR if abs(diff) >= 6 else REST_MINOR
    return math.copysign(magnitude, diff)

# ----------------------------------------------------------------------
# Team conference / division reference table (mirrors the workbook's
# DataTable / Pre02Conf / Pre02Div columns, used for seasons <= 2001;
# for seasons > 2001 the *_2002_PLUS table applies).
# ----------------------------------------------------------------------
TEAM_CONF_DIV_PRE2002 = {
    "ARI": ("NFC", "East"), "ATL": ("NFC", "West"), "BAL": ("AFC", "Central"),
    "BUF": ("AFC", "East"), "CAR": ("NFC", "West"), "CHI": ("NFC", "Central"),
    "CIN": ("AFC", "Central"), "CLE": ("AFC", "Central"), "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"), "DET": ("NFC", "Central"), "GB": ("NFC", "Central"),
    "IND": ("AFC", "East"), "JAX": ("AFC", "Central"), "KC": ("AFC", "West"),
    "MIA": ("AFC", "East"), "MIN": ("NFC", "Central"), "NE": ("AFC", "East"),
    "NO": ("NFC", "West"), "NYG": ("NFC", "East"), "NYJ": ("AFC", "East"),
    "OAK": ("AFC", "West"), "PHI": ("NFC", "East"), "PIT": ("AFC", "Central"),
    "SD": ("AFC", "West"), "SEA": ("AFC", "West"), "SF": ("NFC", "West"),
    "STL": ("NFC", "West"), "TB": ("NFC", "Central"), "TEN": ("AFC", "Central"),
    "WAS": ("NFC", "East"),
}

TEAM_CONF_DIV_2002_PLUS = {
    "ARI": ("NFC", "West"), "ATL": ("NFC", "South"), "BAL": ("AFC", "North"),
    "BUF": ("AFC", "East"), "CAR": ("NFC", "South"), "CHI": ("NFC", "North"),
    "CIN": ("AFC", "North"), "CLE": ("AFC", "North"), "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"), "DET": ("NFC", "North"), "GB": ("NFC", "North"),
    "HOU": ("AFC", "South"), "IND": ("AFC", "South"), "JAX": ("AFC", "South"),
    "KC": ("AFC", "West"), "MIA": ("AFC", "East"), "MIN": ("NFC", "North"),
    "NE": ("AFC", "East"), "NO": ("NFC", "South"), "NYG": ("NFC", "East"),
    "NYJ": ("AFC", "East"), "OAK": ("AFC", "West"), "PHI": ("NFC", "East"),
    "PIT": ("AFC", "North"), "SD": ("AFC", "West"), "SEA": ("NFC", "West"),
    "SF": ("NFC", "West"), "STL": ("NFC", "West"), "TB": ("NFC", "South"),
    "TEN": ("AFC", "South"), "WAS": ("NFC", "East"),
}


def conf_div(team: str, season: int) -> tuple[str, str]:
    table = TEAM_CONF_DIV_PRE2002 if season <= 2001 else TEAM_CONF_DIV_2002_PLUS
    return table[team]


# ----------------------------------------------------------------------
# Full-name -> TeamID mapping used to read the parsed_games CSVs.
# Franchises that relocated keep a single ID across the move (matching the
# workbook's own convention, e.g. Houston Oilers games are tagged "TEN").
# ----------------------------------------------------------------------
TEAM_NAME_TO_ID = {
    "Arizona Cardinals": "ARI", "Phoenix Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Houston Oilers": "TEN",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Oakland Raiders": "OAK", "Los Angeles Raiders": "OAK", "Las Vegas Raiders": "OAK",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "St. Louis Rams": "STL", "Los Angeles Rams": "STL",
    "San Diego Chargers": "SD", "Los Angeles Chargers": "SD",
    "Seattle Seahawks": "SEA",
    "San Francisco 49ers": "SF",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Oilers": "TEN", "Tennessee Titans": "TEN",
    "Washington Redskins": "WAS", "Washington Football Team": "WAS",
    "Washington Commanders": "WAS",
}

# Playoff round labels used in Continelo (`Round` column) once we've mapped
# a CSV's generic numeric playoff round to the round code POMult expects.
PLAYOFF_ROUND_LABEL = {1: "WC", 2: "DV", 3: "CC", 4: "SB"}


def week_from_date(dt: pd.Timestamp, season_start: pd.Timestamp) -> int:
    """Bucket a game date into an NFL week number.

    Weeks run Tuesday -> Monday (the day after Monday Night Football is the
    start of a new week), which correctly groups Thursday games with the
    following Sunday/Monday slate, including the Thanksgiving game.
    """
    # Tuesday on/before the season's first game date
    anchor = season_start - pd.Timedelta(days=(season_start.weekday() - 1) % 7)
    return int((dt - anchor).days // 7) + 1


@dataclass
class EloEngine:
    """Stateful Elo engine reproducing the workbook's rating logic."""

    k: float = K
    hfa: float = HFA
    alpha: float = ALPHA
    base: float = BASE

    # team -> season -> final (post-last-game) rating for that season
    _season_final: dict[str, dict[int, float]] = field(default_factory=dict)
    # team -> current in-season rating (None until the team's first game
    # of the season has been computed as a PreGmRate)
    _current: dict[str, float] = field(default_factory=dict)
    _current_season: Optional[int] = None

    def _start_season(self, season: int) -> None:
        """Roll every team's rating into the new season using the
        alpha/base blend, exactly like the workbook's IFERROR fallback."""
        # Recompute the opening rating for every team we've seen before,
        # blending in last season's final rating.
        new_current: dict[str, float] = {}
        for team, seasons in self._season_final.items():
            if (season - 1) in seasons:
                last = seasons[season - 1]
                new_current[team] = self.alpha * last + (1 - self.alpha) * self.base
        self._current = new_current
        self._current_season = season

    def pre_game_rating(self, team: str, season: int) -> float:
        if self._current_season != season:
            self._start_season(season)
        return self._current.get(team, self.base)

    def record_result(self, team: str, season: int, post_rating: float) -> None:
        self._current[team] = post_rating
        self._season_final.setdefault(team, {})[season] = post_rating


def compute_elo(games: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the full Continelo Elo table for a set of games.

    `games` must have one row per team per game (i.e. two rows per game,
    one from each team's perspective) with columns:
        Season, Week, Type ('R' or 'P'), Round ('RS','WC','DV','CC','SB'),
        Team, Opponent, HomeAway ('H'/'A'), PointsFor, PointsAgainst, OT (0/1),
        games_played, days_off, opp_days_off

    games_played / days_off / opp_days_off must already be computed on the
    input (build_nfl_db.py does this before calling compute_elo(), in the
    same chronological order this function processes games in) -- they
    drive the K decay and rest_adj below and have to reflect each team's
    actual position in the season as of that row, not a post-hoc summary.

    Rows must be pre-sorted so that, within a season, all of a team's games
    appear in chronological (Week) order -- games must be processed in week
    order across the whole league for PreGmRate to look back correctly.

    Returns a DataFrame matching the workbook's RawData columns, plus RestAdj
    and K (the decayed per-row K, before div/conf/playoff multipliers --
    Keff is K after those multipliers, same as before).
    """
    games = games.sort_values(["Season", "Week"], kind="stable").reset_index(drop=True)

    engine = EloEngine()
    out_rows = []

    for season, season_games in games.groupby("Season", sort=True):
        for week, week_games in season_games.groupby("Week", sort=True):
            # Snapshot pre-game ratings for every team playing this week
            # BEFORE any of this week's results are applied (all games in
            # a week use the same starting rating, matching the workbook,
            # which looks at "Week < this row's Week").
            pre_ratings = {}
            for team in pd.unique(week_games["Team"]):
                pre_ratings[team] = engine.pre_game_rating(team, season)

            week_updates = []  # (team, season, post_rating) to apply after the week

            for _, g in week_games.iterrows():
                team = g["Team"]
                opp = g["Opponent"]
                home_away = g["HomeAway"]
                pts_for = g["PointsFor"]
                pts_against = g["PointsAgainst"]
                ot = int(g["OT"])

                pre = pre_ratings[team]
                opp_pre = pre_ratings[opp]

                team_conf, team_div = conf_div(team, season)
                opp_conf, opp_div = conf_div(opp, season)
                conf_g = int(team_conf == opp_conf)
                div_g = int(conf_g and team_div == opp_div)

                team_rest_adj = rest_adj(g.get("days_off"), g.get("opp_days_off"))

                team_eff = pre + (HFA if home_away == "H" else 0) + team_rest_adj
                opp_eff = opp_pre + (HFA if home_away == "A" else 0)
                expected = 1 / (1 + 10 ** ((opp_eff - team_eff) / 400))

                mov = pts_for - pts_against
                if mov > 0:
                    result = 1.0
                elif mov == 0:
                    result = 0.5
                else:
                    result = 0.0

                accuracy = int(
                    (expected >= 0.5 and result == 1) or (expected < 0.5 and result == 0)
                )
                test_logloss = -(
                    result * math.log(expected) + (1 - result) * math.log(1 - expected)
                )

                mov_mult = (
                    ((abs(mov) + 3) ** 0.8)
                    / (7.5 + 0.006 * abs(pre - opp_pre))
                    * (0.7 if ot == 1 else 1)
                )

                if g["Type"] == "P":
                    po_mult = PLAYOFF_ROUND_MULT.get(g["Round"], 1.0)
                else:
                    po_mult = 1.0

                k_row = decayed_k(engine.k, K_FLOOR, int(g["games_played"]), season)
                k_eff = (
                    k_row
                    * (DIV_GAME_MULT if div_g else 1)
                    * (CONF_GAME_MULT if conf_g else 1)
                    * po_mult
                )

                rating_change = (k_eff * mov_mult) * (result - expected)
                post = pre + rating_change

                win = int(g["Type"] == "R" and result > 0.5)
                loss = int(g["Type"] == "R" and result < 0.5)
                tie = int(g["Type"] == "R" and result == 0.5)

                out_rows.append(
                    {
                        "Date": g["Date"] if "Date" in g else None,
                        "Week": week,
                        "Season": season,
                        "Type": g["Type"],
                        "Round": g["Round"],
                        "Team": team,
                        "Opponent": opp,
                        "Conf": team_conf,
                        "OppConf": opp_conf,
                        "Div": team_div,
                        "OppDiv": opp_div,
                        "ConfG": conf_g,
                        "DivG": div_g,
                        "HomeAway": home_away,
                        "games_played": g["games_played"],
                        "days_off": g.get("days_off"),
                        "opp_days_off": g.get("opp_days_off"),
                        "PreGmRate": pre,
                        "OppPreGmRate": opp_pre,
                        "ExpectedWin%": expected,
                        "RestAdj": team_rest_adj,
                        "PointsFor": pts_for,
                        "PointsAgainst": pts_against,
                        "OT": ot,
                        "MOV": mov,
                        "Result": result,
                        "Accuracy": accuracy,
                        "Test": test_logloss,
                        "MOVMult": mov_mult,
                        "POMult": po_mult,
                        "K": k_row,
                        "Keff": k_eff,
                        "RatingChange": rating_change,
                        "PostGmRate": post,
                        "W": win,
                        "L": loss,
                        "T": tie,
                    }
                )
                week_updates.append((team, season, post))

            # Apply this week's results so next week's PreGmRate sees them
            for team, season_, post in week_updates:
                engine.record_result(team, season_, post)

    return pd.DataFrame(out_rows)

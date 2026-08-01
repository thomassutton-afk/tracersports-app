#!/usr/bin/env python3
"""
elo_engine.py

A faithful Python re-implementation of the Elo model from NCAA_CBB_ELO_2026.xlsx.
Every formula and parameter below was pulled directly from that workbook's
RawData sheet (and its named ranges), not guessed:

    Kmin=20  Kmax=78  HCA=68  alpha=0.6  base=1500  d2pen=0.75 (d2base=1125)

    K(gp)        = max(Kmin, Kmax - 0.35 * min(gp, 30))
    MOVMult      = ((|MOV|+5)^0.6) / (12 + 0.01*|preA-preB|) * (0.9 if OT else 1)
    T_Mult       = 1                                   if regular season
                   CHOOSE(round, 1.15,1.25,1.4,1.55,1.7,1.85)   if NCAA tourney
                   1.1 + 0.05*round                    if conference tourney
                   1.05 + 0.03*round                   if "early season" tourney
    C_Mult       = 1.15 if same conference else 1
    Keff         = K * T_Mult * C_Mult
    Expected     = 1 / (1 + 10^((opp_eff - own_eff)/400))
                   where home team's effective rating gets +HCA (neutral site: neither does)
    RatingChange = Keff * MOVMult * (Result - Expected)
    PostRating   = PreRating + RatingChange

    A team's rating carries into a new season as: alpha*prev_final + (1-alpha)*base
    A non-D1 ("D2") opponent is always rated at base*d2pen and never updates.

This module has no I/O of its own -- see run_elo_1996.py for wiring it up to
a games database.
"""

from dataclasses import dataclass, field
import math


DEFAULT_PARAMS = dict(
    Kmin=20.0,
    Kmax=78.0,
    HCA=68.0,
    alpha=0.6,
    base=1500.0,
    d2pen=0.75,
)


@dataclass
class EloEngine:
    d1_teams: set = None          # set of team names considered D1 -- anything else is treated as D2
    conferences: dict = None      # optional {team_name: conference_name} for the conference bonus
    prev_season_final: dict = None  # optional {team_name: rating} to carry a prior season in
    params: dict = None

    def __post_init__(self):
        self.p = dict(DEFAULT_PARAMS)
        if self.params:
            self.p.update(self.params)
        self.d2base = self.p["base"] * self.p["d2pen"]
        self.conferences = self.conferences or {}
        self.prev_season_final = self.prev_season_final or {}
        self._rating = {}       # team -> current rating this season
        self._games_played = {}  # team -> games played so far this season
        self.ledger = []        # list of per-team-perspective result dicts

    def is_d1(self, team: str) -> bool:
        if self.d1_teams is None:
            return True
        return team in self.d1_teams

    def _pre_rating(self, team: str) -> float:
        if team in self._rating:
            return self._rating[team]
        if not self.is_d1(team):
            return self.d2base
        prev = self.prev_season_final.get(team)
        if prev is not None:
            return self.p["alpha"] * prev + (1 - self.p["alpha"]) * self.p["base"]
        return self.p["base"]

    def _k_factor(self, games_played_including_this_one: int) -> float:
        return max(self.p["Kmin"], self.p["Kmax"] - 0.35 * min(games_played_including_this_one, 30))

    def _tournament_mult(self, is_tournament: bool, tier: str, rnd) -> float:
        if not is_tournament:
            return 1.0
        if tier == "NCAA":
            table = {1: 1.15, 2: 1.25, 3: 1.4, 4: 1.55, 5: 1.7, 6: 1.85}
            return table.get(rnd, 1.85)
        if tier == "CONF":
            return 1.1 + 0.05 * rnd
        if tier == "EARLY":
            return 1.05 + 0.03 * rnd
        return 1.0

    def process_game(self, date, home_team, away_team, home_pts, away_pts,
                      neutral_site=False, is_tournament=False, tier="NONE", round_=None,
                      ot=False, conf_game=None):
        """Process one game and update both teams' ratings. Returns the ledger
        rows (dicts) for the home and away perspectives."""

        pre_home = self._pre_rating(home_team)
        pre_away = self._pre_rating(away_team)
        gp_home = self._games_played.get(home_team, 0) + 1
        gp_away = self._games_played.get(away_team, 0) + 1

        hca = 0.0 if neutral_site else self.p["HCA"]
        home_eff = pre_home + hca
        away_eff = pre_away
        exp_home = 1.0 / (1.0 + 10 ** ((away_eff - home_eff) / 400.0))
        exp_away = 1.0 - exp_home

        mov = home_pts - away_pts
        result_home = 1.0 if mov > 0 else (0.5 if mov == 0 else 0.0)
        result_away = 1.0 - result_home

        mov_mult = ((abs(mov) + 5) ** 0.6) / (12 + 0.01 * abs(pre_home - pre_away))
        if ot:
            mov_mult *= 0.9

        t_mult = self._tournament_mult(is_tournament, tier, round_)

        if conf_game is None:
            ch, ca = self.conferences.get(home_team), self.conferences.get(away_team)
            conf_game = bool(ch and ca and ch == ca)
        c_mult = 1.15 if conf_game else 1.0

        k_home = self._k_factor(gp_home)
        k_away = self._k_factor(gp_away)
        keff_home = k_home * t_mult * c_mult
        keff_away = k_away * t_mult * c_mult

        change_home = keff_home * mov_mult * (result_home - exp_home)
        change_away = keff_away * mov_mult * (result_away - exp_away)

        post_home = pre_home + change_home
        post_away = pre_away + change_away

        # IMPORTANT: only D1 teams carry a rating forward. Non-D1 ("D2")
        # opponents are always re-evaluated at the flat d2base rating next
        # time they appear (matching the workbook's IF(Conf="D2", d2base, ...)
        # which ignores any prior computed value) -- so their state is
        # deliberately NOT persisted here.
        if self.is_d1(home_team):
            self._rating[home_team] = post_home
            self._games_played[home_team] = gp_home
        if self.is_d1(away_team):
            self._rating[away_team] = post_away
            self._games_played[away_team] = gp_away

        accuracy_home = 1 if ((exp_home >= 0.5 and result_home == 1.0) or (exp_home < 0.5 and result_home == 0.0)) else 0
        eps = 1e-9
        log_loss_home = -(result_home * math.log(max(exp_home, eps)) + (1 - result_home) * math.log(max(1 - exp_home, eps)))
        brier_home = (exp_home - result_home) ** 2
        accuracy_away = 1 if ((exp_away >= 0.5 and result_away == 1.0) or (exp_away < 0.5 and result_away == 0.0)) else 0
        log_loss_away = -(result_away * math.log(max(exp_away, eps)) + (1 - result_away) * math.log(max(1 - exp_away, eps)))
        brier_away = (exp_away - result_away) ** 2

        row_home = dict(
            date=date, team=home_team, opponent=away_team, home_away=("N" if neutral_site else "H"),
            games_played=gp_home, pre_rating=pre_home, opp_pre_rating=pre_away,
            expected_win_pct=exp_home, points_for=home_pts, points_against=away_pts, ot=int(bool(ot)),
            mov=mov, result=result_home, mov_mult=mov_mult, t_mult=t_mult, c_mult=c_mult,
            k=k_home, k_eff=keff_home, rating_change=change_home, post_rating=post_home,
            accuracy=accuracy_home, log_loss=log_loss_home, brier=brier_home,
        )
        row_away = dict(
            date=date, team=away_team, opponent=home_team, home_away=("N" if neutral_site else "A"),
            games_played=gp_away, pre_rating=pre_away, opp_pre_rating=pre_home,
            expected_win_pct=exp_away, points_for=away_pts, points_against=home_pts, ot=int(bool(ot)),
            mov=-mov, result=result_away, mov_mult=mov_mult, t_mult=t_mult, c_mult=c_mult,
            k=k_away, k_eff=keff_away, rating_change=change_away, post_rating=post_away,
            accuracy=accuracy_away, log_loss=log_loss_away, brier=brier_away,
        )
        self.ledger.append(row_home)
        self.ledger.append(row_away)
        return row_home, row_away

    def final_ratings(self) -> dict:
        return dict(self._rating)

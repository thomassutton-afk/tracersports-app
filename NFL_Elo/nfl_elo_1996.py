#!/usr/bin/env python3
"""
NFL Elo rating engine — 1996 season.

Replicates the Excel workbook's RawData formulas exactly:
  - Base K-factor (k)      = 20
  - Home field advantage   = 55 Elo points
  - Season carryover alpha = 0.3   (unused for a single-season 1996 run)
  - Base / starting rating = 1500
  - Division-game K bump   = x1.10
  - Conference-game K bump = x1.02  (stacks with division bump)
  - Playoff round bump     = WC x1.10, DV x1.20, CC x1.35, SB x1.50
  - MOV multiplier         = ((|MOV|+3)^0.8) / (7.5 + 0.006*|rating diff|),
                              x0.7 if the game went to overtime
"""

import csv
import json
import math

K_BASE = 20
HFA = 55
ALPHA = 0.3
BASE_RATING = 1500
PLAYOFF_MULT = {"WC": 1.10, "DV": 1.20, "CC": 1.35, "SB": 1.50}


def expected_win_pct(team_rating, opp_rating, site):
    """site: 'H' (team is home), 'A' (team is away), 'N' (neutral)."""
    team_adj = team_rating + (HFA if site == "H" else 0)
    opp_adj = opp_rating + (HFA if site == "A" else 0)
    return 1 / (1 + 10 ** ((opp_adj - team_adj) / 400))


def mov_multiplier(mov, rating_diff, ot):
    mult = ((abs(mov) + 3) ** 0.8) / (7.5 + 0.006 * abs(rating_diff))
    if ot:
        mult *= 0.7
    return mult


def k_effective(same_div, same_conf, game_type, round_code):
    k = K_BASE
    if same_div:
        k *= 1.1
    if same_conf:
        k *= 1.02
    if game_type == "P":
        k *= PLAYOFF_MULT.get(round_code, 1.0)
    return k


def run_season(games, team_conf_div, starting_ratings=None):
    """
    games: list of dicts with week, type, round, home, away,
           home_pts, away_pts, ot, site (H/N)
    team_conf_div: {team: {"conf": ..., "div": ...}}
    starting_ratings: optional {team: rating} for teams with season history;
                       any team not present starts at BASE_RATING.
    Returns: list of per-game result rows (one row per team per game, like
             the Excel RawData table), and the final ratings dict.
    """
    ratings = dict(starting_ratings or {})

    def get_rating(team):
        return ratings.get(team, BASE_RATING)

    results = []
    for g in sorted(games, key=lambda x: x["week"]):
        home, away = g["home"], g["away"]
        home_pre = get_rating(home)
        away_pre = get_rating(away)

        home_site = g["site"]  # 'H' or 'N'
        away_site = "A" if home_site == "H" else "N"

        home_conf, home_div = team_conf_div[home]["conf"], team_conf_div[home]["div"]
        away_conf, away_div = team_conf_div[away]["conf"], team_conf_div[away]["div"]
        same_conf = home_conf == away_conf
        same_div = same_conf and home_div == away_div

        home_exp = expected_win_pct(home_pre, away_pre, home_site)
        away_exp = expected_win_pct(away_pre, home_pre, away_site)

        mov = g["home_pts"] - g["away_pts"]
        if mov > 0:
            home_result, away_result = 1.0, 0.0
        elif mov < 0:
            home_result, away_result = 0.0, 1.0
        else:
            home_result, away_result = 0.5, 0.5

        movmult = mov_multiplier(mov, home_pre - away_pre, g["ot"])
        keff = k_effective(same_div, same_conf, g["type"], g["round"])

        home_change = keff * movmult * (home_result - home_exp)
        away_change = keff * movmult * (away_result - away_exp)

        home_post = home_pre + home_change
        away_post = away_pre + away_change

        ratings[home] = home_post
        ratings[away] = away_post

        for team, opp, pre, exp_, pts_for, pts_against, result, change, post, site in [
            (home, away, home_pre, home_exp, g["home_pts"], g["away_pts"], home_result, home_change, home_post, home_site),
            (away, home, away_pre, away_exp, g["away_pts"], g["home_pts"], away_result, away_change, away_post, away_site),
        ]:
            results.append({
                "week": g["week"], "type": g["type"], "round": g["round"],
                "team": team, "opponent": opp, "home_away": site,
                "pre_rating": pre, "opp_pre_rating": ratings.get(opp),
                "expected_win_pct": exp_, "points_for": pts_for, "points_against": pts_against,
                "ot": g["ot"], "mov": pts_for - pts_against, "result": result,
                "mov_mult": movmult, "keff": keff, "rating_change": change,
                "post_rating": post,
            })

    return results, ratings


def main():
    with open("games_1996.json") as f:
        games = json.load(f)
    with open("team_conf_div.json") as f:
        team_conf_div = json.load(f)

    results, final_ratings = run_season(games, team_conf_div)

    with open("elo_1996_gamelog.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"Processed {len(games)} games, {len(results)} team-game rows.")
    print("\nFinal 1996 Elo ratings (top 10):")
    for team, rating in sorted(final_ratings.items(), key=lambda x: -x[1])[:10]:
        print(f"  {team:4s} {rating:8.2f}")


if __name__ == "__main__":
    main()

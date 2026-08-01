#!/usr/bin/env python3
"""
Print and save the final 1996 Elo standings, sorted highest to lowest.

Reads elo_1996_gamelog.csv (produced by nfl_elo_1996.py) and, for each team,
takes their post_rating from the last game they played that season.

Usage:
    python final_standings_1996.py
"""

import csv

INPUT_FILE = "elo_1996_gamelog.csv"
OUTPUT_FILE = "final_standings_1996.csv"

last_week = {}
last_rating = {}

with open(INPUT_FILE) as f:
    for row in csv.DictReader(f):
        team = row["team"]
        week = int(row["week"])
        if team not in last_week or week >= last_week[team]:
            last_week[team] = week
            last_rating[team] = float(row["post_rating"])

standings = sorted(last_rating.items(), key=lambda x: -x[1])

print(f"{'Rank':<5}{'Team':<6}{'Final Elo':>10}")
for i, (team, rating) in enumerate(standings, start=1):
    print(f"{i:<5}{team:<6}{rating:>10.2f}")

with open(OUTPUT_FILE, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["rank", "team", "final_elo"])
    for i, (team, rating) in enumerate(standings, start=1):
        w.writerow([i, team, round(rating, 2)])

print(f"\nSaved to {OUTPUT_FILE}")

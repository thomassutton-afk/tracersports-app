"""
Quick test to verify nba_api is working and can pull current data.
"""

from nba_api.stats.endpoints import scoreboardv2, leaguegamelog
import json

print("Testing NBA API connection...\n")

# Test 1: Recent scoreboard (May 8 2026 — should have playoff games)
print("=== Scoreboard for May 8, 2026 ===")
try:
    board = scoreboardv2.ScoreboardV2(
        game_date="2026-05-08",
        league_id="00",
        day_offset=0
    )
    games = board.game_header.get_data_frame()
    if games.empty:
        print("  No games found for that date.")
    else:
        for _, g in games.iterrows():
            print(f"  Game ID: {g['GAME_ID']}  |  {g['GAME_STATUS_TEXT']}")
            print(f"    {g['HOME_TEAM_ID']} vs {g['VISITOR_TEAM_ID']}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 2: Pull game log for current season
print("\n=== Recent games from LeagueGameLog (2025-26 season) ===")
try:
    log = leaguegamelog.LeagueGameLog(
        season="2025-26",
        season_type_all_star="Playoffs",
        league_id="00"
    )
    df = log.get_data_frames()[0]
    print(f"  Total playoff game-team rows found: {len(df)}")
    if not df.empty:
        print(f"  Most recent games:")
        recent = df.sort_values("GAME_DATE", ascending=False).head(6)
        for _, r in recent.iterrows():
            print(f"    {r['GAME_DATE']}  {r['TEAM_ABBREVIATION']:4s}  "
                  f"Game ID: {r['GAME_ID']}  WL: {r['WL']}")
except Exception as e:
    print(f"  ERROR: {e}")

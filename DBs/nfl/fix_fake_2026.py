"""
One-off cleanup: removes simulated/test completed games that were
loaded into `games` at some point and never got removed by a normal
add_season.py run, since that pipeline only ever adds games (by
design - see export_to_supabase.py's build_games() docstring), never
deletes ones that later disappear from a source file.

As of today, the real 2026 NFL season has zero completed games (it
starts 2026-09-09), so this deletes every season=2026 row in `games`
unconditionally. Do NOT reuse this once the real season is underway -
at that point some season=2026 games will be real, and this would
delete those too. If you need this later for a *different* season/
reason, scope the DELETE below by date range or a specific team/
opponent pair instead of the whole season.

Rebuilds ratings for both variants afterward so the rating history
(and everyone's current rating) reflects the real games only.
"""
import sqlite3
from rebuild import rebuild_ratings, VARIANTS

DB_PATH = "nfl_elo.db"
FAKE_SEASON = 2026

conn = sqlite3.connect(DB_PATH)
cur = conn.execute("SELECT COUNT(*) FROM games WHERE season = ?", (FAKE_SEASON,))
n = cur.fetchone()[0]
print(f"Found {n} game row(s) for season {FAKE_SEASON} - deleting.")

conn.execute("DELETE FROM games WHERE season = ?", (FAKE_SEASON,))
conn.commit()

for variant in VARIANTS:
    rebuild_ratings(conn, variant)
    print(f"Ratings rebuilt ({variant}).")

conn.close()
print("Done. Now run add_season.py as usual, then export_to_supabase.py "
      "--league nfl to push the corrected local state to Supabase.")

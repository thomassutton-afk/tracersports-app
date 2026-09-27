"""
Checks the round-by-round prediction accuracy in cfb_elo.db, and
spot-checks a few of the specific cases from the classify_round()
date-gate fix. Run with: python check_bowl_accuracy.py
"""
import sqlite3

conn = sqlite3.connect("cfb_elo.db")

print("=== Accuracy / Brier by round, per variant ===")
for variant in ("echo", "pulse"):
    print(f"\n--- {variant} ---")
    rows = conn.execute(
        """
        SELECT COALESCE(round, 'REGULAR') AS rnd, COUNT(*), AVG(accuracy), AVG(brier)
        FROM ratings WHERE variant=? GROUP BY rnd ORDER BY rnd
        """,
        (variant,),
    ).fetchall()
    for rnd, n, acc, brier in rows:
        print(f"  {rnd:10s} n={n:6d} (games~{n // 2:5d})  accuracy={acc:.3f}  brier={brier:.4f}")

print("\n=== Spot check: Memphis 2016 regular-season home games ===")
print("(should all show round = None now, not BOWL)")
rows = conn.execute(
    """
    SELECT g.date, t1.team_name, t2.team_name, g.round
    FROM games g
    JOIN teams t1 ON g.home_team = t1.team_id
    JOIN teams t2 ON g.away_team = t2.team_id
    WHERE g.season = 2016 AND (t1.team_name = 'memphis' OR t2.team_name = 'memphis')
    ORDER BY g.date
    """
).fetchall()
for date, home, away, round_ in rows:
    print(f"  {date}  {home} vs {away}  ->  round={round_}")

print("\n=== Spot check: Nov 30 conference championship games ===")
print("(should all still show round = CCG)")
rows = conn.execute(
    """
    SELECT date, round FROM games
    WHERE date IN ('2001-11-30', '2006-11-30', '2012-11-30', '2018-11-30')
    ORDER BY date
    """
).fetchall()
for date, round_ in rows:
    print(f"  {date}  ->  round={round_}")

conn.close()

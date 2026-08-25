import sqlite3

conn = sqlite3.connect('wnba_elo.db')
query = """
    SELECT date, home_team, away_team, COUNT(*) as n,
           GROUP_CONCAT(type || ':' || IFNULL(round,'NULL')) as variants
    FROM games
    WHERE season=2021
    GROUP BY date, home_team, away_team
    HAVING COUNT(*) > 1
"""
for row in conn.execute(query).fetchall():
    print(row)
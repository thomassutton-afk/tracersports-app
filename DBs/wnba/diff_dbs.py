import sqlite3

a = sqlite3.connect(r'C:\Users\tjsut\tracersports-app\DBs\wnba_elo.db')
b = sqlite3.connect(r'C:\Users\tjsut\tracersports-app\DBs\wnba\wnba_elo.db')

def keys(conn):
    return set(conn.execute(
        "SELECT date, home_team, away_team, type, IFNULL(round,-1) FROM games"
    ).fetchall())

ka, kb = keys(a), keys(b)

print(f"DBs\\wnba_elo.db: {len(ka)} games")
print(f"DBs\\wnba\\wnba_elo.db: {len(kb)} games")

only_in_a = ka - kb
only_in_b = kb - ka

print(f"\nIn DBs\\wnba_elo.db but NOT in DBs\\wnba\\wnba_elo.db ({len(only_in_a)}):")
for row in sorted(only_in_a)[:30]:
    print(" ", row)

print(f"\nIn DBs\\wnba\\wnba_elo.db but NOT in DBs\\wnba_elo.db ({len(only_in_b)}):")
for row in sorted(only_in_b)[:30]:
    print(" ", row)
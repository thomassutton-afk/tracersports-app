import sqlite3

conn = sqlite3.connect('wnba_elo.db')

# Preview first: confirm exactly which rows will be deleted
preview = conn.execute("""
    SELECT game_id, date, home_team, away_team, type, round
    FROM games
    WHERE season = 2021
      AND type = 'R'
      AND EXISTS (
          SELECT 1 FROM games g2
          WHERE g2.date = games.date
            AND g2.home_team = games.home_team
            AND g2.away_team = games.away_team
            AND g2.type = 'P'
      )
""").fetchall()

print(f"Found {len(preview)} stale duplicate rows to delete:")
for row in preview:
    print(row)

confirm = input("\nDelete these rows? (yes/no): ")
if confirm.strip().lower() == "yes":
    conn.execute("""
        DELETE FROM games
        WHERE season = 2021
          AND type = 'R'
          AND EXISTS (
              SELECT 1 FROM games g2
              WHERE g2.date = games.date
                AND g2.home_team = games.home_team
                AND g2.away_team = games.away_team
                AND g2.type = 'P'
          )
    """)
    conn.commit()
    print("Deleted.")
else:
    print("Aborted, nothing deleted.")

conn.close()
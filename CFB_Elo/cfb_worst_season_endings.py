"""
cfb_worst_season_endings.py

Finds the 10 lowest FBS season-ending ratings, all-time, Echo variant.

"Season-ending rating" = each (team, season)'s LAST rating row that
season (same definition rebuild.standings() uses: ORDER BY date DESC,
game_id DESC, LIMIT 1) - not a single worst point-in-time dip mid-season,
and not an average across the season.

FBS-only: a team/season is included only if db.is_fbs(team, season) is
true - so a bad FCS-caliber team's rock-bottom season doesn't crowd out
what this is actually asking (the worst FBS programs/seasons).

Usage:
    python3 cfb_worst_season_endings.py cfb_elo.db
"""
import sys

import db

VARIANT = "echo"
TOP_N = 10


def worst_season_endings(conn, variant: str, n: int) -> list[tuple]:
    rows = conn.execute(
        """
        SELECT r.team, r.season,
               (SELECT post_rate FROM ratings r2
                WHERE r2.team = r.team AND r2.season = r.season AND r2.variant = r.variant
                ORDER BY r2.date DESC, r2.game_id DESC LIMIT 1) AS final_rating
        FROM ratings r
        WHERE r.type = 'R' AND r.variant = ?
        GROUP BY r.team, r.season
        """,
        (variant,),
    ).fetchall()

    fbs_only = [
        (team, season, rating) for team, season, rating in rows
        if rating is not None and db.is_fbs(conn, team, season)
    ]
    fbs_only.sort(key=lambda r: r[2])
    return fbs_only[:n]


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "cfb_elo.db"
    conn = db.connect(db_path)

    worst = worst_season_endings(conn, VARIANT, TOP_N)
    if not worst:
        print("No FBS season-ending ratings found.")
        return

    print(f"10 worst FBS season-ending ratings, all-time ({VARIANT}):\n")
    for i, (team, season, rating) in enumerate(worst, start=1):
        name = db.display_name(conn, team, season)
        print(f"  {i:2d}. {name:28s} {season}   {rating:.1f}")


if __name__ == "__main__":
    main()

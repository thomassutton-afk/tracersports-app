"""Recompute the full ratings history from the games table."""
from __future__ import annotations
import sqlite3
import engine
import db


def rebuild_ratings(conn: sqlite3.Connection, params: dict | None = None) -> None:
    if params is None:
        params = db.load_active_params(conn) or engine.default_params()
    games = db.load_games(conn)
    resets = db.load_resets(conn)
    db.clear_ratings(conn)
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        rows = eng.process_game(g)
        db.save_ratings(conn, rows, [g["game_id"], g["game_id"]])
    conn.commit()


def standings(conn: sqlite3.Connection, season: int):
    """Regular-season W/L + final rating as of end of that season's games
    seen so far. Team name reflects whatever the franchise was actually
    called THAT season (e.g. Seattle SuperSonics in 1996, Oklahoma City
    Thunder in 2010), via db.display_name - not just its current name."""
    cur = conn.execute(
        """
        SELECT r.team,
               SUM(r.w) AS wins, SUM(r.l) AS losses,
               (SELECT post_rate FROM ratings r2
                WHERE r2.team = r.team AND r2.season = r.season
                ORDER BY r2.date DESC, r2.game_id DESC LIMIT 1) AS final_rating
        FROM ratings r
        WHERE r.season = ? AND r.type = 'R'
        GROUP BY r.team
        ORDER BY final_rating DESC
        """,
        (season,),
    )
    rows = cur.fetchall()
    return [
        (team, db.display_name(conn, team, season), wins, losses, rating)
        for team, wins, losses, rating in rows
    ]


def sanity_checks(conn: sqlite3.Connection, seasons) -> list[str]:
    """Basic health checks for a set of seasons: no NaN ratings, no
    team missing win/loss totals, no team that played games but has
    no standings row."""
    warnings = []
    for season in seasons:
        rows = standings(conn, season)
        for team, name, w, l, rating in rows:
            if rating is None or rating != rating:  # NaN check
                warnings.append(f"Season {season}: {name} has an invalid (NaN) rating.")
            if w is None or l is None:
                warnings.append(f"Season {season}: {name} is missing win/loss totals.")
        game_teams = conn.execute(
            "SELECT DISTINCT home_team FROM games WHERE season=? "
            "UNION SELECT DISTINCT away_team FROM games WHERE season=?",
            (season, season),
        ).fetchall()
        standings_teams = {r[0] for r in rows}
        for (tid,) in game_teams:
            if tid not in standings_teams:
                warnings.append(f"Season {season}: {tid} played games but has no standings row.")
    return warnings


if __name__ == "__main__":
    conn = db.connect("nba_elo.db")
    rebuild_ratings(conn)
    for row in standings(conn, 1996):
        print(row)

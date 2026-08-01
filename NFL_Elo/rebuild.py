"""
Replay every game in `games` into `ratings`, from scratch.

Unlike NBA/WNBA (replay strictly one game at a time, in date order),
NFL's engine processes games in WEEKLY BATCHES - see engine.py's
module docstring for why. rebuild_ratings() here groups every game by
(season, week) - using the same week_from_date() bucketing add_season.py
uses when loading new games - and calls engine.process_week() once per
week, in chronological (season, week) order.
"""
import db
import engine


def _week_buckets(games: list[dict]) -> dict[tuple[int, int], list[dict]]:
    """Group games into (season, week), anchored to that season's own
    opener - NOT a fixed calendar date, since the season opener's
    weekday varies year to year."""
    season_start = {}
    for g in games:
        season_start.setdefault(g["season"], g["date"])
        if g["date"] < season_start[g["season"]]:
            season_start[g["season"]] = g["date"]

    weeks: dict[tuple[int, int], list[dict]] = {}
    for g in games:
        wk = engine.week_from_date(g["date"], season_start[g["season"]])
        weeks.setdefault((g["season"], wk), []).append(g)
    return weeks


def build_current_engine(conn, resets=None, params=None) -> engine.EloEngine:
    """Replay every REAL game in the database, week by week, to get
    each team's current state - without writing anything back to the
    database. Shared by rebuild_ratings() (which also saves the
    per-game rows) and by predict.py/simulate_season.py (which only
    need the resulting ratings, not another database write)."""
    games = db.load_games(conn)
    resets = resets if resets is not None else db.load_resets(conn)
    params = params if params is not None else (db.load_active_params(conn) or engine.default_params())
    eng = engine.EloEngine(params, resets=resets)

    weeks = _week_buckets(games)
    for key in sorted(weeks):
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        game_dicts = [
            dict(date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                 home_team=g["home_team"], away_team=g["away_team"],
                 home_code=g["home_code"], away_code=g["away_code"],
                 home_pts=g["home_pts"], away_pts=g["away_pts"], ot=g["ot"], neutral=g["neutral"])
            for g in week_games
        ]
        eng.process_week(game_dicts)

    return eng


def rebuild_ratings(conn) -> None:
    games = db.load_games(conn)
    if not games:
        db.clear_ratings(conn)
        conn.commit()
        return

    resets = db.load_resets(conn)
    params = db.load_active_params(conn) or engine.default_params()
    eng = engine.EloEngine(params, resets=resets)

    weeks = _week_buckets(games)

    db.clear_ratings(conn)
    for key in sorted(weeks):
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        game_dicts = [
            dict(date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                 home_team=g["home_team"], away_team=g["away_team"],
                 home_code=g["home_code"], away_code=g["away_code"],
                 home_pts=g["home_pts"], away_pts=g["away_pts"], ot=g["ot"], neutral=g["neutral"])
            for g in week_games
        ]
        results = eng.process_week(game_dicts)
        game_ids = []
        for g in week_games:
            game_ids.extend([g["game_id"], g["game_id"]])
        rows = [row for pair in results for row in pair]
        db.save_ratings(conn, rows, game_ids)

    conn.commit()


def standings(conn, season: int):
    """Regular-season W/L/T + final rating as of end of that season's
    games seen so far. Team name reflects whatever the franchise was
    actually called THAT season, via db.display_name - not just its
    current name."""
    cur = conn.execute(
        """
        SELECT r.team,
               SUM(r.w) AS wins, SUM(r.l) AS losses, SUM(r.t) AS ties,
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
        (team, db.display_name(conn, team, season), wins, losses, ties, rating)
        for team, wins, losses, ties, rating in rows
    ]


def sanity_checks(conn, seasons) -> list[str]:
    """Basic health checks for a set of seasons: no NaN ratings, no
    team missing win/loss/tie totals, no team that played games but
    has no standings row."""
    warnings = []
    for season in seasons:
        rows = standings(conn, season)
        for team, name, w, l, t, rating in rows:
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

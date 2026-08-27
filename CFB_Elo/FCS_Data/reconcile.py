"""
The checks that actually caught real errors this season: Morehead State's
record, the Middle Tennessee/Murray State W-L bug, Evansville's missing games.
Every new source should run through these before anything gets promoted.
"""
import datetime
from reference import resolve_fcs_name, classify_location, norm


def to_month_day(date_str):
    """Accepts 'MM-DD-YYYY' or 'YYYY-MM-DD'; returns 'Month D' to match the
    format used throughout the `games` table."""
    for fmt in ('%m-%d-%Y', '%Y-%m-%d'):
        try:
            d = datetime.datetime.strptime(date_str, fmt)
            return d.strftime('%B %-d')
        except ValueError:
            continue
    return date_str  # already in "Month D" form, presumably


def check_internal_record(games, stated_wins, stated_losses, stated_ties=0):
    """Does a team's own parsed game list sum to its stated record? Returns
    (ok: bool, actual_w, actual_l, actual_t, n_games)."""
    w = sum(1 for g in games if g.get('wl') == 'W')
    l = sum(1 for g in games if g.get('wl') == 'L')
    t = sum(1 for g in games if g.get('wl') == 'T')
    ok = (w, l, t) == (stated_wins, stated_losses, stated_ties) and len(games) == stated_wins + stated_losses + stated_ties
    return ok, w, l, t, len(games)


def stage_games(con, season, source_name, team, games, get_date=None, get_opp=None,
                 get_result=None, get_scores=None, get_site=None, get_notes=None):
    """Insert games into staging_games for one team, auto-resolving opponent
    names and flagging matches/conflicts against whatever's already in `games`
    for this season. `games` is a list of dicts in whatever shape the caller's
    parser produced; the get_* callables extract the fields we need (defaults
    assume the shape parsers.py produces)."""
    get_date = get_date or (lambda g: g.get('date'))
    get_opp = get_opp or (lambda g: g.get('opponent_raw') or g.get('opponent'))
    get_result = get_result or (lambda g: g.get('wl'))
    get_scores = get_scores or (lambda g: (g.get('team_score') or g.get('pf'), g.get('opp_score') or g.get('pa')))
    get_site = get_site or (lambda g: g.get('site') or g.get('location'))
    get_notes = get_notes or (lambda g: g.get('notes', ''))

    cur = con.cursor()
    verified = {}
    for t, date, opp_fcs, wl, ts, os_ in cur.execute(
            "SELECT team, date, opponent_fcs, wl, team_score, opp_score FROM games "
            "WHERE season=? AND opponent_fcs IS NOT NULL AND wl IS NOT NULL", (season,)):
        verified[(t, opp_fcs, date)] = (wl, ts, os_)
        flip = {'W': 'L', 'L': 'W', 'T': 'T'}.get(wl, wl)
        verified[(opp_fcs, t, date)] = (flip, os_, ts)

    inserted = 0
    for g in games:
        raw_date = get_date(g)
        md = to_month_day(raw_date)
        opp_raw = get_opp(g)
        opp_fcs = resolve_fcs_name(con, opp_raw, season)
        wl = get_result(g)
        ts, os_ = get_scores(g)
        site = get_site(g)
        notes = get_notes(g)
        hac = classify_location(con, team, opp_fcs, site)

        already, conflict = 0, 0
        if opp_fcs and (team, opp_fcs, md) in verified:
            vwl, vts, vos = verified[(team, opp_fcs, md)]
            already = 1
            if (vwl, vts, vos) != (wl, ts, os_):
                conflict = 1

        cur.execute("""
            INSERT INTO staging_games (season, source, team, date, opponent_raw, opponent_fcs,
                result, team_score, opponent_score, site_location, home_away_neutral, notes,
                already_in_verified, conflicts_with_verified)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (season, source_name, team, md, opp_raw, opp_fcs, wl, ts, os_, site, hac, notes, already, conflict))
        inserted += 1
    con.commit()
    return inserted


def cross_check_staged_sources(con, season):
    """Compares every pair of not-yet-promoted staged games for the same
    (team, date, opponent) across DIFFERENT sources. Returns a list of
    mismatch dicts - empty means everything staged so far agrees."""
    cur = con.cursor()
    rows = cur.execute("""
        SELECT source, team, date, opponent_fcs, result, team_score, opponent_score
        FROM staging_games WHERE season=? AND opponent_fcs IS NOT NULL AND promoted=0
    """, (season,)).fetchall()
    by_key = {}
    for source, team, date, opp, result, ts, os_ in rows:
        by_key.setdefault((team, date, opp), []).append((source, result, ts, os_))

    mismatches = []
    for key, entries in by_key.items():
        results = set((r, ts, os_) for _, r, ts, os_ in entries)
        if len(results) > 1:
            mismatches.append({'team': key[0], 'date': key[1], 'opponent': key[2], 'entries': entries})
    return mismatches


def record_reconciliation_report(con, season):
    """For every team with a stated TeamList record, compares it against what
    the currently-promoted `games` table reconstructs. Flags mismatches like
    Morehead State's 2-8-vs-6-4 discrepancy for manual review - never silently
    trusts one side."""
    outer_cur = con.cursor()
    inner_cur = con.cursor()
    report = []
    # Count both perspectives (team=X's own games, and games recorded from the
    # opponent's side with opponent_fcs=X), deduped by (date, other side) - same
    # logic as the team_completion view, so this can't miss opponent-recovered games.
    unified_sql = """
        WITH all_games AS (
            SELECT team AS the_team, date, COALESCE(opponent_fcs, opponent) AS other_side, wl
            FROM games WHERE season=? AND wl IS NOT NULL
            UNION
            SELECT opponent_fcs AS the_team, date, team AS other_side,
                   CASE wl WHEN 'W' THEN 'L' WHEN 'L' THEN 'W' ELSE wl END AS wl
            FROM games WHERE season=? AND wl IS NOT NULL AND opponent_fcs IS NOT NULL
        )
        SELECT wl, COUNT(*) FROM (
            SELECT DISTINCT date, other_side, wl FROM all_games WHERE the_team=?
        ) GROUP BY wl
    """
    for team, wins, losses in outer_cur.execute(
            "SELECT team_name, wins, losses FROM teams WHERE season=? AND has_full_schedule=1", (season,)):
        tally = dict(inner_cur.execute(unified_sql, (season, season, team)).fetchall())
        w, l = tally.get('W', 0), tally.get('L', 0)
        if (w, l) != (wins, losses):
            report.append({'team': team, 'teamlist_record': f'{wins}-{losses}', 'reconstructed_record': f'{w}-{l}'})
    return report


def promote_team(con, season, team):
    """Move all staged, non-conflicting rows for a team into `games`, mark the
    team's schedule as full. Rows already flagged conflicts_with_verified are
    skipped - resolve those manually first."""
    cur = con.cursor()
    rows = cur.execute("""
        SELECT staging_id, date, opponent_raw, opponent_fcs, result, team_score,
               opponent_score, home_away_neutral, site_location, source
        FROM staging_games
        WHERE season=? AND team=? AND promoted=0 AND conflicts_with_verified=0
    """, (season, team)).fetchall()

    for sid, date, opp_raw, opp_fcs, wl, ts, os_, hac, site, source in rows:
        cur.execute("""
            INSERT INTO games (season, team, date, opponent_raw, opponent, opponent_fcs,
                location, non_conf, homecoming, site, result, wl, team_score, opp_score, source)
            VALUES (?,?,?,?,?,?,?,0,0,?,?,?,?,?,?)
        """, (season, team, date, opp_raw, opp_raw, opp_fcs, hac, site,
              f"{wl} {ts}-{os_}", wl, ts, os_, source))
        cur.execute("UPDATE staging_games SET promoted=1 WHERE staging_id=?", (sid,))

    cur.execute("UPDATE teams SET has_full_schedule=1 WHERE season=? AND team_name=?", (season, team))
    con.commit()
    return len(rows)


def completion_report(con, season):
    cur = con.cursor()
    total = cur.execute("SELECT SUM(expected_games) FROM team_completion WHERE season=?", (season,)).fetchone()[0]
    filled = cur.execute(
        "SELECT SUM(MIN(games_filled, expected_games)) FROM team_completion WHERE season=?", (season,)
    ).fetchone()[0]
    gaps = cur.execute(
        "SELECT team_name, expected_games, games_filled, games_remaining FROM still_needs_filling WHERE season=?",
        (season,)).fetchall()
    return {'total_expected': total, 'total_filled': filled,
            'pct': round(100 * filled / total, 2) if total else None, 'gaps': gaps}

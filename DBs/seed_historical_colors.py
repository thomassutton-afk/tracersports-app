"""
One-time seed for team_history.{primary,secondary,tertiary}_color.

Only sets colors for eras that DIFFER from a franchise's current identity
(the one already in lib/sports/{league}/config.js) - current eras are left
NULL on purpose, so the frontend's fallback-to-config.js path is what
serves them, same source of truth as everywhere else on the site.

Confidence varies a lot by entry - see the comment on each row. A few
(SEA, VAN, NJN, the 1988-2002 Hornets) are sourced from published team-color
references; several others are my best-effort estimate with no solid
source found, flagged VERIFY. Re-run with corrected values any time via
`franchise.py set-colors` for a single era, or by editing this file and
re-running it (set_era_colors is idempotent - safe to run twice).

USAGE - run from DBs\\ (matches every other pipeline script's convention;
do NOT run from inside DBs\\nba\\ or DBs\\wnba\\, see the Operations Guide's
"working directory is critical" note):

    python3 seed_historical_colors.py --league nba
    python3 seed_historical_colors.py --league wnba

Each targets the TOP-LEVEL db (DBs/nba_elo.db or DBs/wnba_elo.db) - the
one export_to_supabase.py actually reads - not the subfolder working copy.
If you also want the subfolder copy in sync for your next add_season.py
run, follow your normal copy convention afterward.
"""
import argparse
import importlib.util
import os
import sys

# NBA eras. team_id, start_season identify the exact team_history row
# (see franchise.py status). All colors here are for OLD eras only -
# each of these team_ids' CURRENT era is left NULL, served by config.js.
NBA_COLORS = [
    # Seattle SuperSonics (1996-2008) -> Oklahoma City Thunder.
    # Sourced: teamcolorcodes.com.
    ("nba_0025", 1996, "#00653A", "#FFC200", "#FFFFFF"),
    # Vancouver Grizzlies (1996-2001) -> Memphis Grizzlies. Sourced: the
    # "retro" Grizzlies palette (teamcolorcodes.com) - this is literally
    # the Vancouver-era look, carried into Memphis's own early years.
    ("nba_0028", 1996, "#00B2A9", "#BC7844", "#E43C40"),
    # New Jersey Nets (1996-2012) -> Brooklyn Nets. Sourced:
    # teamcolorcodes.com "historical colors of the New Jersey Nets".
    ("nba_0017", 1996, "#002A60", "#CD1041", "#C6CFD4"),
    # Charlotte Hornets, ORIGINAL 1988-2002 era (1996-2002 in our data)
    # -> New Orleans Hornets. Sourced: teamcolorcodes.com.
    ("nba_0003", 1996, "#00778B", "#280071", "#F9423A"),
    # New Orleans Hornets 2003-2005 - VERIFY, no solid source found for
    # this specific transitional era; reused the Charlotte-era palette
    # above since the brand/logo carried over largely unchanged at first.
    ("nba_0003", 2003, "#00778B", "#280071", "#B5985A"),
    # New Orleans/Oklahoma City Hornets 2006-2007 (temporary post-Katrina
    # dual-market season) - VERIFY, same reasoning as above.
    ("nba_0003", 2006, "#00778B", "#280071", "#B5985A"),
    # New Orleans Hornets 2008-2013 (post OKC-Thunder-split return) -
    # VERIFY, same reasoning as above.
    ("nba_0003", 2008, "#00778B", "#280071", "#B5985A"),
    # Charlotte Bobcats (2005-2014) -> Charlotte Hornets (2015-present).
    # VERIFY - low confidence, no solid source found.
    ("nba_0030", 2005, "#FF8500", "#00285E", "#A1A1A4"),
    # Washington Bullets (1996-1997) -> Washington Wizards. VERIFY - low
    # confidence, no solid source found for this specific 2-season tail
    # end of the Bullets identity.
    ("nba_0029", 1996, "#002868", "#BF0D3E", "#FFFFFF"),
]

# WNBA eras - only the three franchises that relocated/renamed but are
# STILL ACTIVE need this (their current era already covered by
# config.js). The 5 truly-folded teams (Sting/Rockers/Comets/
# Monarchs/Sol) only ever had one identity each, so their config.js
# entries alone are already the complete picture - no team_history
# color rows needed for those.
WNBA_COLORS = [
    # Utah Starzz (1997-2002) -> ... -> Las Vegas Aces. VERIFY - low
    # confidence, no solid source found.
    ("wnba_0008", 1997, "#5B2B82", "#00A9A5", "#FDB927"),
    # San Antonio Silver Stars (2003-2013). VERIFY - low confidence.
    ("wnba_0008", 2003, "#8A8D8F", "#000000", "#00A99D"),
    # San Antonio Stars (2014-2017, dropped "Silver"). VERIFY - reused
    # the Silver Stars-era palette above; no indication of an actual
    # color change alongside the name shortening, but not confirmed.
    ("wnba_0008", 2014, "#8A8D8F", "#000000", "#00A99D"),
    # Detroit Shock (1998-2009) -> Tulsa Shock -> Dallas Wings. VERIFY -
    # low confidence, no solid source found.
    ("wnba_0009", 1998, "#C8102E", "#002868", "#FDB827"),
    # Tulsa Shock (2010-2015). VERIFY - low confidence.
    ("wnba_0009", 2010, "#004B8D", "#8DC63F", "#A7A9AC"),
    # Orlando Miracle (1999-2002) -> Connecticut Sun. VERIFY - low
    # confidence, no solid source found.
    ("wnba_0012", 1999, "#006B8F", "#5B2B82", "#C4CED4"),
]


def load_db_module(league: str):
    path = os.path.join(os.path.dirname(__file__), league, "db.py")
    spec = importlib.util.spec_from_file_location(f"{league}_db", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--league", required=True, choices=["nba", "wnba"])
    args = p.parse_args()

    db = load_db_module(args.league)
    db_path = os.path.join(os.path.dirname(__file__), f"{args.league}_elo.db")
    if not os.path.exists(db_path):
        print(f"Expected top-level db at {db_path} - not found. Run this from DBs\\, "
              f"not from inside DBs\\{args.league}\\.")
        sys.exit(1)

    conn = db.connect(db_path)
    rows = NBA_COLORS if args.league == "nba" else WNBA_COLORS

    applied, skipped = 0, 0
    for team_id, start_season, primary, secondary, tertiary in rows:
        ok = db.set_era_colors(conn, team_id, start_season, primary, secondary, tertiary)
        if ok:
            applied += 1
        else:
            skipped += 1
            print(f"  SKIPPED: no {team_id} era starts at {start_season} in this db - "
                  f"check 'franchise.py status' if this is unexpected.")
    conn.commit()
    print(f"{args.league}: applied {applied}, skipped {skipped} (of {len(rows)} total).")


if __name__ == "__main__":
    main()

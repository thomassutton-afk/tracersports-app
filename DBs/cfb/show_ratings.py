"""Print current CFB Elo ratings (read-only; nothing is rebuilt or written).

Run from DBs/cfb:
    python show_ratings.py                  # top 25, echo + pulse side by side, latest season
    python show_ratings.py --top 136        # everyone
    python show_ratings.py --variant pulse  # one variant only
    python show_ratings.py --season 2025 --top 10
    python show_ratings.py --team "Ohio State"   # one team, matched on display name (substring)

Ratings come from the same rebuild.standings() that add_season.py prints, so records and
Elo match that output. Names are your display names (short ones if team_display_names.json
is next to this script).
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, rebuild

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="../cfb_elo.db")
ap.add_argument("--season", type=int)
ap.add_argument("--variant", choices=["echo", "pulse", "both"], default="both")
ap.add_argument("--top", type=int, default=25)
ap.add_argument("--team")
a = ap.parse_args()

conn = db.connect(a.db)
season = a.season or conn.execute("SELECT MAX(season) FROM games").fetchone()[0]
asof = conn.execute("SELECT MAX(date) FROM games WHERE season=?", (season,)).fetchone()[0]

short = {}
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_display_names.json")
if os.path.exists(p):
    short = {v["team_id"]: v["short"] for v in json.load(open(p, encoding="utf-8")).values()}

variants = ["echo", "pulse"] if a.variant == "both" else [a.variant]
tables = {}
for v in variants:
    rows = rebuild.standings(conn, season, v)          # sorted by rating, FBS teams only
    tables[v] = {tid: (i + 1, short.get(tid, name), w, l, t, r) for i, (tid, name, w, l, t, r) in enumerate(rows)}

main = tables[variants[0]]
order = sorted(main, key=lambda tid: main[tid][0])
if a.team:
    order = [tid for tid in order if a.team.lower() in main[tid][1].lower()]
else:
    order = order[: a.top]

print(f"{season} season, through games dated {asof}  |  {len(main)} FBS teams\n")
head = f"{'#':>3}  {'Team':<24}{'Rec':>7}"
for v in variants: head += f"  {v + ' Elo':>10}{'rk':>5}"
print(head)
for tid in order:
    rk, name, w, l, t, _ = main[tid]
    rec = f"{int(w)}-{int(l)}" + (f"-{int(t)}" if t else "")
    line = f"{rk:>3}  {name:<24}{rec:>7}"
    for v in variants:
        r = tables[v].get(tid)
        line += f"  {r[5]:>10.1f}{r[0]:>5}" if r else f"  {'-':>10}{'-':>5}"
    print(line)

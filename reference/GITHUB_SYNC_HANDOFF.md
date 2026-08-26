# TRACER Sports — GitHub Sync Handoff

*Last updated: 2026-08-25*

## The two repos

- **`TRACERsports`** — the production/live repo. Deployed site reads from here (indirectly, via Supabase).
- **`tracersports-app`** — the sandbox/testing repo. Where new features (NFL, CFB) get built out before they're ready for production.

Both repos cover NBA and WNBA today. Sandbox is additionally building out NFL and CFB support, which does not exist in main yet.

**Why they diverge:** sandbox is where active feature work happens, so it regularly gets ahead of main. But sandbox doesn't always stay in sync with bug fixes that land in main first, and vice versa. Periodic compatibility checks (comparing file-by-file across both repos) are how we catch drift in either direction.

## The general sync workflow

1. Pull the full file tree from both repos, diff shared (non-NFL) files.
2. For each difference, determine **direction**: is one repo ahead with a real fix the other needs, or is the difference just expected NFL-only code that hasn't shipped to main yet?
3. Port real fixes in whichever direction is correct — usually sandbox → main for bug fixes discovered while building NFL, but sometimes main → sandbox (e.g. main had `@vercel/analytics` in `package.json` that sandbox was missing).
4. Never blindly copy a whole file without checking direction first — a couple of "sandbox is ahead" assumptions turned out to be backwards (e.g. sandbox's team colors were actually wrong, main's were correct).

## Data pipeline (NBA/WNBA today, NFL/CFB later)

Local SQLite (`*_elo.db`) → `export_to_supabase.py` → Supabase Postgres → live site reads from Supabase.

**Important gotcha:** the Supabase export uses `ON CONFLICT DO NOTHING`. This means:
- New games insert fine on a normal re-run.
- **Corrections to existing games do NOT propagate.** If a game's score is fixed locally (via `delete_season.py` + `add_season.py`), re-running the export will silently skip that row since it already "exists" in Supabase by its natural key.
- **Fix pattern:** `DELETE FROM games WHERE league=... AND season=...` (scoped as narrowly as safe — a single game if only one changed, a whole season if the correction cascades through the Elo chain) in Supabase's SQL Editor, then re-run the export so it inserts clean.
- This has bitten us twice in one session (a two-game score swap, and a full-season Commissioner's Cup backfill). **Worth considering changing this to a real upsert (`ON CONFLICT ... DO UPDATE`) so re-exports self-heal.** Not yet done.

**Supabase connection note:** the direct hostname (`db.xxxx.supabase.co`) is IPv6-only unless you're on Supabase's paid IPv4 add-on. If it stops resolving (DNS failure, but the project is otherwise healthy in the dashboard), switch `.env` to the **session pooler** host instead (`aws-0-<region>.pooler.supabase.com`, port `5432`, user becomes `postgres.<project-ref>`). Already made this switch once this session — noting it here in case it needs to happen again on a different machine/environment.

## Franchise management (`franchise.py`)

Handles relocations, renames, and revivals (a folded team's code being reused for a new franchise). The `revive` command had a real bug: it always assumes a prior era exists to close and a new one needs opening — but if a team is revived in the **same season** it's first registered (a code reused for a same-year expansion with zero prior history), `add_season.py`'s automatic registration already created that season's `team_history` row, and `revive`'s own insert collides with it (`UNIQUE constraint failed`).

**Fixed** (see `franchise.py` in this session's outputs): `revive` now checks whether a `team_history` row already exists for that exact `(team_id, season)` before trying to insert one. If it does, it just updates the name if given and leaves the row alone. Genuine multi-season revivals (a team with real prior history, gap, then reactivated) are unaffected — that path still works as originally designed.

**This fix has not yet been ported to `DBs/nba/franchise.py`** — worth checking whether NBA's version has the same bug (it very likely does, same underlying pattern).

## Known remaining work

### Phase 1 — port color/bracket infrastructure to main (not NFL-gated)
Sandbox reworked `lib/teamColors.js` with better dark-color detection and a new `getTextColor()` helper, and updated `BracketTab.jsx`/`OverallBracketTab.jsx` to use it. This improves bracket readability for **any** dark-colored team, NBA/WNBA included — not NFL-specific. Should be ported to main independent of NFL timing. Verify no NBA/WNBA team's actual rendered color changes unexpectedly as a side effect before shipping.

### Phase 2 — adopt `update_wnba_results.py` in main
New sandbox tool: pulls final scores from ESPN's scoreboard API into `WNBA_2026_Results.xlsx`, with built-in mirror-row validation (won't save if two teams' rows for the same game disagree). Directly relevant after this session's Commissioner's Cup gap — this kind of validation would likely have caught it earlier. Worth deciding whether NBA needs an equivalent script.

### Phase 3 — NFL merge (when ready, not yet)
`lib/sports/registry.js` in **sandbox now actually imports and registers `nflConfig`** — NFL is functionally wired into sandbox's navigation, a real milestone. Main still has zero NFL wiring (deliberately — its `registry.js` comment says not to add future leagues until ready). When it's time:
- `lib/sports/registry.js`, `DBs/team_divisions.py`, `lib/sports/nfl/config.js`, `lib/gamesData.js`
- `app/[league]/page.js`, `app/[league]/season/page.js`, `app/[league]/all-time/page.js`
- `schema.sql` (adds a `t`/ties column — remember this needs a Supabase-side `ALTER TABLE` migration too, same as we did for NBA/WNBA)
- `app/about/page.js` content update
- Watch for interaction with Phase 1 if that's done first — some of these files may end up touching the same color-function calls.

### Data quality watch-items
- **`teams.team_name` can go stale** relative to `team_history` (the actual source of truth for a team's current identity/code). Found one case where a legacy team_id's display name didn't match its real current code — worth a spot-check across all teams if this hasn't been done recently, especially after any rebuild.
- **Commissioner's Cup games with fractional `Round` values** (e.g. `0.1`) may not import reliably — one instance found and diagnosed this session (LVA @ NYL, 2026-06-30) where the game existed in the authoritative ratings reference but was missing from the working local database entirely. Worth scanning the full results source for any other Cup-type rows that may have silently failed to import the same way, rather than assuming it was an isolated incident.

## General lessons for whoever picks this up

- **Always verify blob content directly (via Git's blob API) rather than trusting `raw.githubusercontent.com`** — that CDN can lag behind a fresh push by a noticeable amount, and produced at least one false "this didn't work" moment this session.
- **Both `[team]` and `[league]` bracket-notation paths in URLs need percent-encoding** (`%5B`/`%5D`) when hitting GitHub's Contents API directly — plain brackets return 404s.
- **`rebuild_ratings()` requires an explicit `variant` argument** (`"echo"` or `"pulse"`) in both NBA and WNBA — no default. Any script calling it needs to loop over both.
- When comparing local vs. Supabase vs. any exported reference file, the safest check is always by **date + matchup**, not `game_id` — SQLite reassigns `game_id`s on any `delete_season`/`add_season` rebuild, so the same real-world game can end up under a different ID locally than the one Supabase already has.

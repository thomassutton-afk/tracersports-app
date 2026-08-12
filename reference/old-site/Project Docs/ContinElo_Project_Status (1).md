# ContinElo — Project Status
*Updated May 17, 2026*

## What This Is
An Elo-based NBA team rating system (two variants: Elo reset and ContinElo carry-forward)
covering 1995-96 through present. Migrated from Excel into a database-backed public website.

## Stack
- **Database:** Supabase (Postgres) — project fhummqxfssfctswzkajj
- **Backend:** Python scripts in C:\Users\tjsut\ContinElo\
- **Website:** Next.js app in C:\Users\tjsut\ContinElo\website\
- **Hosting:** Vercel — https://continelo.vercel.app

## Phases

### Phase 1 — Calculation Engine ✅
- `continelo_engine.py` verified against Excel
- All formulas match within floating point tolerance

### Phase 2 — Database ✅
- Supabase schema created (teams, seasons, games, preseason_ratings, standings)
- All 62 Excel files imported (156,888 rows, 1996–2026, both variants)
- Supabase views created:
  - `season_accuracy` — game count, avg accuracy, avg brier per season/variant
  - `season_records` — win/loss totals per team/season/variant
  - `current_ratings` — latest post_gm_rate per team/variant (used by dashboard)
  - `season_standings` — used by Season page and All-Time Rankings for end-of-RS
    and end-of-playoff ratings per team/season/variant

### Phase 3 — Live Pipeline ✅
- `pipeline.py` running via Windows Task Scheduler every 10 minutes
- Critical bug fixed (May 2026): pipeline was snapshotting opponent ratings and last
  game dates AFTER writing the first team's row. Fix: snapshot both teams' ratings,
  last game dates, and games played counts BEFORE the loop that processes each row.
- Known limitation: OT detection not implemented — all games default to OT=0.
  This affects MOVMult slightly for overtime games. To be fixed.
- Known precision note: playoff ratings differ from Excel by small floating point
  amounts (fractions of a point early, up to ~1-2 points after many games). This is
  a Python vs Excel float precision difference, not a formula error. Non-playoff
  teams match exactly.

### Phase 4 — Website ✅
All pages are deployed, live on Vercel, and working with real data as of May 17, 2026.

#### Pages built and live:

**Dashboard** (`app/Dashboard.jsx`)
- Three tabs: Power Rankings, Standings, Playoff Bracket
- Power Rankings: all 30 teams ranked by current rating, logo + abbreviation pill,
  strength bar, last-game rating change, RS record, ContinElo/Elo variant toggle
- Standings: conference view and division view, grouped by auto-berths / play-in /
  lottery, playoff result badges, RS ratings
- Playoff Bracket: full bracket with completed series (winners/losers/scores/ratings),
  TBD placeholders for unplayed rounds, play-in tournament sub-view, champion banner
- Recent games feed, model accuracy strip (game count, accuracy %, Brier score)
- Pulls from `current_ratings`, `season_records`, `season_accuracy` views and
  `games` table directly for recent games and playoff data

**Season Page** (`app/season/[year]/SeasonPage.jsx`)
- Season selector dropdown covering 1996–2026
- Three tabs: Standings, Rating Chart, Game Log
- Standings: sortable by any column, East/West filter, historical identity display
  (SEA for OKC pre-2009, VAN for MEM pre-2002, NJN for BRK pre-2013, etc.),
  playoff results, pre-season rating (ContinElo variant only), strength bar
- Rating Chart: filter by playoff teams / conference / division / head-to-head /
  all teams, hover highlight dims all other lines, season summary strip
  (champion, finalist, highest rated, model accuracy)
- Game Log: paginated (25/page), filterable by RS/playoffs, home team perspective,
  win probability, rating change badge
- ContinElo/Elo variant toggle works on this page
- Real data confirmed working as of May 17, 2026 (e.g. 2025-26: 2,608 games rated,
  68.4% accuracy, 0.208 Brier; OKC 64-18, SA 62-20 leading the West)

**All-Time Rankings** (`app/all-time/AllTimeRankings.jsx`)
- 921 team-seasons (1995-96 through 2025-26, both variants stored)
- Hero stats: team-season count, champion count, top all-time rating with team/season,
  average rating across filtered results
- Playoff depth filter: All Seasons → Made Playoffs → Won Round 1 →
  Won Conf. Semis → Won Conf. Finals → Champions Only
- Era filter: All Eras, 1990s, 2000s, 2010s, 2020s
- Team search by name or abbreviation
- Sortable columns: rank, team, season, RS record, pre-season rating, RS rating,
  playoff result, final rating
- Pagination (50 per page)
- Historical identity display with logos (GS 2016-17 shows Warriors logo, etc.)
- Top all-time: GS 2016-17 at 1861.6, CHI 1995-96 at 1838.5, GS 2014-15 at 1831.1
- ContinElo/Elo variant toggle works on this page

**Team Page** (`app/team/[abbr]/TeamPage.jsx`)
- All 30 franchise pages at /team/[abbr] (lowercase), redirect at /team → /team/sa
- Three tabs: Rating History, Season-by-Season, Game Log
- Rating History: continuous SVG line chart spanning all 30 seasons, area fill,
  peak and trough markers with ratings labeled, season boundary grid lines,
  1500 average baseline, franchise identity legend for relocated/renamed teams
- Season-by-Season: one row per season, sortable, playoff result, pre-season rating,
  strength bar, championship markers, links to season pages
- Game Log: filterable by season and game type (RS/playoffs), paginated,
  pre-game rating, win probability, rating change, post-game rating
- Hero stats: current rating, this season's record, championships, all-time peak,
  all-time record
- ContinElo/Elo variant toggle works on this page
- Team selector dropdown in nav for switching franchises

**About Page** (`app/about/AboutPage.jsx`)
- What is ContinElo, Elo vs ContinElo comparison table, key concepts (HCA, rest,
  MOV, K factor, playoff multipliers), model accuracy section, data coverage section
- Static page, no data fetching

#### Logo system:
- All 30 current team logos in `public/logos/current/ABBR.png`
- Historical logos in `public/logos/historical/ABBR_YYYY.png`
- API route at `app/api/logo-index/route.js` scans the historical folder at runtime
  and returns a JSON index — no hardcoded list needed, just drop files in the folder
- Historical logos confirmed working: correct logos display for SEA, VAN, NJN, NOH,
  Charlotte Bobcats, etc. on Season and All-Time pages
- Dashboard always uses /current/ logos (current season only)

#### Infrastructure:
- `app/layout.tsx` — root layout with global font imports and metadata
- `lib/supabase.js` — Supabase client (anon key still hardcoded — see Known Issues)
- `globals.css` — shared CSS variables, nav, hero, table, game card, accuracy strip,
  color stripe styles used by Dashboard

## Design Language
- **Background:** cream #F5F0E8, surface #FDFAF5
- **Primary:** ACC purple #663399
- **Accent / top teams:** UT burnt orange #BF5700
- **Success / live:** UO green #154733
- Three-color horizontal stripe (purple / orange / green) — signature element on
  every page top and bottom
- **Fonts:** Playfair Display (headings), DM Sans (body), IBM Plex Mono (numbers/labels)
- Team colors used throughout: abbreviation pills, strength bars, chart lines,
  bracket cards all use official primary team colors

## Known Issues / Future Work

### To fix soon:
- **OT detection in pipeline.py** — currently defaults to OT=0 for all games.
  Affects MOVMult slightly for overtime games. NBA API does not expose OT directly;
  needs to be inferred (e.g. from total game duration or score patterns).
- **Supabase anon key hardcoded** in `lib/supabase.js` — should read from
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` environment variable. The key is already set
  in Vercel environment variables; just needs the code change.

### Pipeline hosting:
- Pipeline currently runs on a personal Windows machine via Task Scheduler.
  If the machine is off or asleep, no updates run.
- **Option:** Move to Vercel Cron Jobs — define a cron schedule in `vercel.json`
  that calls an API route (`app/api/pipeline/route.js`) on a timer. Vercel's free
  tier supports cron jobs running as frequently as once per day; paid tier supports
  every minute. This would eliminate the dependency on the Windows machine entirely.
- **Alternative:** GitHub Actions scheduled workflow (free, runs every 5–10 minutes,
  just needs the DB credentials as secrets).

### Future phases:
- **Picks page** (`/picks`) — daily game predictions vs. moneyline odds, adjustable
  threshold, historical pick record and ROI. Requires a moneyline odds data source.
  Page structure planned in Website Design Spec but not built yet.
- **Mobile optimization** — site is desktop-first. Mobile layout pass is a future phase.
- **Extended historical coverage** — pre-1995-96 seasons (full NBA history).
- **College basketball version** — separate variant of the system.
- **Shareable URLs** — deep links to specific team/season/chart configurations.
- **Social sharing cards** — game result cards for sharing.

## Next Session — Start Here
1. Fix Supabase anon key: change `lib/supabase.js` to read from
   `process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY` instead of hardcoded string
2. Investigate OT detection options in pipeline.py
3. Decide on pipeline hosting: stay on Windows Task Scheduler, or move to
   Vercel Cron Jobs / GitHub Actions
4. Any visual polish on existing pages
5. Eventually: Picks page (needs odds data source first)

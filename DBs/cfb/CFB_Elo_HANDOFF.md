# CFB_Elo — Project Handoff

**Status as of this handoff:** Core Elo engine is solid, data-driven-tuned,
has real postseason-round classification, and now correctly handles an
in-progress current season (unplayed games route to `schedule` instead of
vanishing). **Migrated into `DBs/cfb/`** to match the site's `nba`/`nfl`/`wnba`
layout — committed and pushed, confirmed working against the real database.
Season projections (`simulate_season.py`) are ported and validated. 30
historical seasons (1996–2025) plus an in-progress 2026 season are loaded.
**Still not on the live site** — `export_to_supabase.py` has zero CFB
awareness, `lib/sports/` has no `cfb/` config, and closing that gap is a real
scoping project in its own right, not a quick patch (see §10, item 6, which
now has a concrete breakdown of what it actually involves).

This document is meant to let a fresh conversation (or future-you) pick up
exactly where this one left off, without re-deriving any of the design
reasoning below. Read this fully before making further changes — several
design decisions here look arbitrary in isolation but were deliberately
chosen after working through real alternatives.

---

## 1. What this project is

`CFB_Elo` is a College Football Elo rating pipeline, forked from an existing
`NFL_Elo` codebase (part of a larger multi-sport project — `tracersports-app`
on GitHub, feeding a site called TRACER Sports). It computes weekly Elo
ratings for every FBS program, going back to the 1996 season, from
Sports-Reference schedule/standings exports.

Repo: `github.com/thomassutton-afk/tracersports-app`, now in `DBs/cfb/`
(migrated from a root-level `CFB_Elo/` this session — a separate
Python/SQLite data-engineering project, distinct from the site's
Next.js/Supabase frontend, but now following the same layout convention as
`DBs/nba`, `DBs/nfl`, `DBs/wnba`). The database itself is `DBs/cfb_elo.db`
(one level up from the scripts, sibling to `nba_elo.db`/`nfl_elo.db`/
`wnba_elo.db`) — every script's `DB_PATH` resolves via
`os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db")`,
matching the sibling leagues' convention exactly. A few structural gaps
remain beyond the move itself — see §10, item 5.

## 2. Current data state

- **30 full historical seasons (1996–2025), plus an in-progress 2026 season**
  — 24,247 total games in the database. 260 completed 2026 games plus 630
  correctly-scheduled upcoming 2026 games (fixed this session — see below and
  §10, item 1, now resolved).
- Both rating variants (Echo = continuous carryover, Pulse = full reset each
  season) computed and stored in `cfb_elo.db`.
- Conference membership (`team_conference_history`) and FBS status
  (`fbs_membership`) loaded for every season through 2026 via
  `load_conference_membership.py`.
- **Data-integrity cleanup done this session:** found and fixed duplicate raw
  rows in the Sports-Reference source data. Two distinct patterns:
  - Some games have two rows with *different* `Notes` text (one with the
    real bowl/event name, one with just a generic venue name) — 25 such
    pairs across 1996–2025, 8 of which would have silently double-counted a
    game's Elo impact once postseason classification could tell the two
    copies apart (six bowl games plus the 2010 SEC Championship Game).
  - A separate, older, unrelated bug: some games have two **fully
    identical** rows already sitting in the database (same teams, same
    score) — confirmed in at least 10 of the 1996–2005 seasons (3–5 extra
    rows each), pre-dating this session's work entirely. Root cause not
    fully traced; likely from an earlier double-load at some point in the
    project's history.
  - Both are now fixed by `normalize_sr_games.dedupe_raw_rows()`, keyed on
    `(Date, Winner, Loser)`, run before classification. **This required a
    full re-ingest of every season** (delete + reload from raw CSVs, not
    just a code fix) to actually take effect in `cfb_elo.db` — done this
    session. If you ever see game counts change unexpectedly after a
    reload, check this section before assuming something's broken.
- **New this session: fixed the unplayed-games/schedule bug (former §10 item
  1).** `normalize_sr_games.py` was unconditionally dropping every scoreless
  row. Now a scoreless row's DATE decides its fate: today-or-future (within a
  small buffer for a same-day result not yet posted) → kept and routed to
  `schedule` for prediction; further in the past → still dropped as a
  genuine postponement, same as before. Validated end-to-end against the
  real 630 upcoming 2026 games — all correctly landed in `schedule`, not
  `games`. See §5e for a second, related classification fix found and
  fixed the same session.
- **New this session: found and fixed a real classification bug behind the
  BOWL-accuracy gap (former §10 item 3) — see §5e and §8.** Not a modeling
  gap; `classify_round()`'s bare `"Bowl"` regex match was catching venue
  names (Memphis's Liberty Bowl Memorial Stadium, UTEP's Sun Bowl Stadium,
  UCLA's Rose Bowl, and the annual regular-season Texas-Oklahoma game at the
  Cotton Bowl), misclassifying 104-113 ordinary regular-season games as
  postseason across 1996-2025 depending on exactly how it's counted. Fixed
  with a December-June date gate on the `"___ Bowl"`-based checks
  specifically (NOT on the `"Championship"`/CCG check, which needed to stay
  open through Nov 30 for years when Championship Saturday falls there, and
  never had this collision risk anyway). Re-ingested and confirmed: the
  corrected BOWL accuracy is actually a bit LOWER (60.1-60.2%, was
  61.2-61.9%) since the misclassified games had been propping the number up
  — the real postseason gap is slightly worse than originally reported, but
  now trustworthy. CFP-SF accuracy improved substantially (was suffering the
  same venue-collision bug via a different code path) once its false
  positives were removed.

## 3. File-by-file summary

| File | What it does |
|---|---|
| `db.py` | SQLite schema + all data-access helpers. See §4 for the CFB-specific schema additions. |
| `engine.py` | The actual Elo math (`EloEngine`, weekly-batch replay). See §5 for the season-entry/FCS/postseason mechanics — these are the parts that differ meaningfully from the NFL version. |
| `rebuild.py` | Replays all games from `games` into `ratings`, from scratch, for one rating variant. Owns `apply_season_entry()` — the actual implementation of the conference-average algorithm (engine.py just executes what this hands it). |
| `add_season.py` | Loads one season's normalized CSV into `games`/`schedule`, registers new teams, triggers a full rebuild, writes schedule predictions. |
| `franchise.py` | `rename` (cosmetic name fix), `realign` (conference change), `revive` (fold+revival reset). No `relocate` — CFB programs don't physically relocate the way NFL/NBA franchises do. |
| `normalize_sr_games.py` | Converts a raw Sports-Reference schedule CSV into the standardized per-team-row shape `add_season.py` expects. Handles AP rank parsing, team-code slugification, season-year logic for bowl games, source-data dedup, and full postseason `Round` classification (see §5e). Unplayed-game routing and the venue-name-collision fix (both former known bugs) are fixed this session — see §2 and §5e. |
| `load_conference_membership.py` | Loads one season's Standings CSV into `team_conference_history` + `fbs_membership`. Triggers a full rebuild (FBS status now affects rating math, not just display). **Must be run for a season AFTER `add_season.py` has loaded that season's games** — otherwise every team in it silently scores as FCS (fixed rating, no persisted `ratings` row, invisible in standings) until this catches up. Confirmed directly loading 2026: games loaded fine, but standings came back completely empty until this was run. Re-run for 2026 this session with the full real Standings export: 0 unresolved teams, no `KNOWN_ALIASES` gaps. |
| `cfb_tune_engine.py` | Coordinate-ascent tuner over `alpha`/`kmax`/`hfa`/`fcs_rating` for one window, using the real engine (not a reimplementation). |
| `cfb_tune_fcs_rating.py` | Separate era-block tuning for `fcs_rating` specifically (too thin a sample to tune on the same rolling cadence as the others). |
| `cfb_build_param_schedule.py` | Builds the actual `param_schedule.json` (see §7) via a rolling 10-year walk-forward search, seeded from one continuous engine's real snapshotted state at each window boundary (not a fresh flat restart per window) — genuinely equivalent to what production's continuous replay does. Heavy compute job (30 seasons × coordinate-ascent search × real multi-season replay per candidate) — a "kick off and let it churn" script. |
| `cfb_accuracy_report.py` | Accuracy/calibration report: overall + regular-season + postseason (by round) accuracy/Brier/log-loss, by-season and by-month breakdowns, calibration table, biggest upsets, worst predictions. **Naming doesn't match the sibling leagues' `report.py` convention** — see §10, item 5. See §8 for current output (partially refreshed this session — see that section's note on what still needs a full re-run). |
| `rebuild_ratings_only.py` | Thin wrapper that just re-runs `rebuild.rebuild_ratings()` for both variants against an existing `cfb_elo.db` without touching `games` — useful after a params or engine change that doesn't need a re-ingest. |
| `reingest_phase2.py` | Backs up `cfb_elo.db`, re-normalizes and reloads every season 1996-2026 through the current `normalize_sr_games.py`/`classify_round()`, then rebuilds ratings for both variants. The right tool whenever a classification or normalization fix needs to retroactively apply to already-loaded history — used twice this session (the unplayed-games fix and the venue-collision fix each needed a full re-ingest, not just a code change, to take effect in `cfb_elo.db`). |
| `test_phase2.py` | Sanity-checks the postseason classification against a copy of the real db (never touches `cfb_elo.db` directly). |
| `cfb_worst_season_endings.py` | Analysis script — not part of the core pipeline. |
| `predict.py` | Predicts upcoming/unplayed games from current ratings. Has one known simplification — see §10, item 9 (deferred by deliberate decision this session, not urgent). |
| `simulate_season.py` | **New this session** — ported from `TRACERsports/DBs/nfl/simulate_season.py`. Monte Carlo season projection (remaining schedule simulated many times from current ratings). One real CFB-specific addition beyond a straight port: remaining games need `home_conf`/`away_conf`/`home_div`/`away_div`/`home_is_fbs`/`away_is_fbs` annotated (via `rebuild._annotate_conferences()`) before `process_week()`/`preview_matchup()` can use them correctly — the NFL original doesn't need this. Also filters final projections to FBS teams only, since a same-season FCS "buy game" opponent otherwise gets a meaningless fragment-of-a-season win projection. Validated against the real 2026 season (1000 trials, 630 remaining games) — sane output across all ~136 teams, no errors. |

## 4. Schema additions beyond NFL_Elo

- **`team_conference_history`** — era-scoped conference/division per team
  (`team_id, conference, division, start_season, end_season`). Deliberately
  separate from `team_history` (which is for renames/relocations) — a
  conference switch isn't a relocation.
- **`fbs_membership`** — `(team_id, season)`. The actual "is this team FBS
  this season" signal. Populated for every school in a season's Standings
  file, **including independents** (who deliberately get no
  `team_conference_history` row — see §5). **No row for a (team, season) is
  treated identically to "genuinely FCS" by `db.is_fbs()`** — there's no way
  to distinguish "actually FCS" from "just hasn't been loaded yet" from
  inside the engine. See §3's `load_conference_membership.py` entry.
- **`conference_tier`** — `(conference, start_season, end_season, tier)`,
  `tier ∈ {power, midmajor}`. Used only to bucket FBS independents (who have
  no literal conference) for season-entry averaging. Auto-seeded on first
  `db.connect()` via `seed_conference_tiers()`:
  - SEC, Big Ten, ACC, Big 12 → power, 1996–present
  - Pac-12 → power, 1996–2023 (dissolved after 2023)
  - Old football-playing Big East → power, 1996–2012 (split into the
    American in 2013)
  - Everything else defaults to `midmajor` via `tier_for_conference()`'s
    fallback — **this seed list is not exhaustive**, see §10.
- **`games`/`schedule`** carry nullable `home_ap_rank`/`away_ap_rank`.
  **Changed this session:** previously display-only and never read by the
  engine; now actually read for `Round=="BOWL"` games specifically, to
  score bowl importance by the two teams' own rank instead of a hardcoded
  bowl-name list — see §5e.

## 5. Key architecture decisions (read this before changing the engine)

### 5a. Team identity
No canonical abbreviation table exists for CFB (unlike NFL). Team codes are
slugified full names (`brigham-young`, `texas-a-m`, `miami-fl`). Sports-
Reference's *standings* exports use shorter common names (`BYU`, `USC`) that
don't match the *schedule* export's full names — `load_conference_membership.py`'s
`KNOWN_ALIASES` dict bridges this gap. It currently covers: byu, usc,
ole-miss, utep, lsu, smu, pitt, ucf, unlv, uconn, umass, uab, utsa. Extend it
whenever `reports/unresolved_conference_teams_*.csv` flags a new mismatch.

### 5b. FCS handling
Any team with no `fbs_membership` row for a season is treated as a
**fixed-strength opponent** (`fcs_rating` — see §7 for its tuned values):
- Used only to compute the *FBS* opponent's expected outcome/rating change.
- Never gets a `TeamState`, never gets a persisted `ratings` row, never
  appears in standings.
- This was specifically chosen to sidestep a real identity-continuity bug:
  Texas A&M-Commerce renamed to East Texas A&M in 2025 while remaining FCS
  the whole time, which split one program across two `team_id`s with no
  clean way to merge them. Since neither ever gets a real tracked rating,
  the split is harmless.
- **Same mechanism is the cause of the empty-standings trap** described in
  §3/§10 — a season with no `fbs_membership` rows yet looks, from the
  engine's point of view, exactly like a season where every FBS team
  suddenly became FCS.

### 5c. Conference-average season-entry (replaces flat-1500 reversion)
This is the single biggest structural change from NFL_Elo. NFL_Elo blends
every team toward one shared constant (`base`, 1500) between seasons. CFB
programs sit at wildly different competitive tiers that roughly track their
conference, so this blends toward a **conference (or tier) average** instead.

Implemented as `rebuild.apply_season_entry()`, called **once per season
boundary**, before that season's first `process_week()` call — this is a
genuine restructuring, not a parameter tweak. `engine.py`'s `process_week()`
now *requires* every FBS team to already have a `TeamState` before it runs
(raises `KeyError` otherwise) — season entry is no longer lazy/per-team the
way NFL_Elo's was.

**Four-step algorithm** (see `apply_season_entry()`'s docstring for the full
version):
1. **Step A** — group every returning team's current rating by its **last**
   season's conference (or power/midmajor tier, for a returning independent).
2. **Step B** — average each group; regress every returning team toward its
   own group's average via `regress_returning_team()`.
3. **Step C** — recompute conference averages using **this** season's
   membership, but only from the now-regressed returning teams (never from a
   team debuting the same season — avoids circularity when multiple teams
   join the same conference simultaneously).
4. **Step D** — any team never tracked before (true debut, or a former
   fixed-rating FCS opponent) gets inducted via `induct_new_team()` at
   **0.5 × fcs_rating + 0.5 × (its new conference's Step-C average)**.

**Realignment-year rule:** a team's target always uses **last** season's
conference, never the season being entered. This means a team switching
conferences (e.g. Oklahoma Big 12→SEC in 2024) still contributes to and
draws from its *old* conference's average in the transition year, and only
starts drawing from the *new* conference the following season. No special-
casing needed — this falls out of "always use last season's conference"
applied uniformly.

**Independents:** Notre Dame → power tier pool. Every other independent →
midmajor tier pool (`db.INDEPENDENT_TIER`, currently just `{"notre-dame":
"power"}`, defaults everyone else to midmajor).

**Pulse stays flat.** Only Echo uses conference-average reversion — Pulse
still blends toward the shared `base` constant, preserving its meaning as a
pure "no information" comparison baseline. If both variants encoded
conference strength, the distinction between them would blur.

**First-ever loaded season (1996) is a special case:** every team starts
flat at `base`, bypassing the Step D blend entirely (`is_first_season=True`
flag). There's no genuine "graduated from FCS" signal when every team is new
simultaneously — the blend logic is specifically for a team debuting into an
*already-established* league.

**Still unsolved:** genuine first-year-FBS teams (a real promotion, not just
a renamed-but-still-FCS case) likely start overrated by the 50/50 blend —
newcomers are usually behind their new conference-mates initially. This was
deliberately left as "start simple, calibrate later" — see §10.

### 5d. Conference multiplier (collapsed from NFL's two-tier system)
NFL_Elo had separate `div_game_mult` (1.1) and `conf_game_mult` (1.02).
CFB's remaining divisions are largely vestigial post-2020s realignment, so
these collapsed into a single `conf_game_mult` (seeded at 1.1, the old
division-tier value). `div_game` is still computed and stored on every
`ratings` row for potential future display use — it just no longer moves the
K-multiplier.

### 5e. Postseason — full classification done, values still untuned

**Round now takes one of:** `"CCG"`, `"NC"`, `"CFP-R1"`, `"CFP-QF"`,
`"CFP-SF"`, `"BOWL"`, or `None` (regular season). Classification happens in
`normalize_sr_games.classify_round(notes, season, date)` (the `date` param
was added this session — see the venue-collision fix below), checked in this
order (order matters — see the NC/CCG note below):

1. **`NC`** (national championship) — explicit in `Notes` from 2006 onward
   (`"BCS Championship"` 2006–2013, `"College Football Playoff National
   Championship"` 2014+). For 1998–2005, the BCS title game was just
   whichever of Rose/Sugar/Orange/Fiesta was that year's designated host in
   the normal bowl rotation, with **no distinguishing text in `Notes`** —
   handled via a hardcoded year→bowl lookup (`BCS_EMBEDDED_TITLE_BOWL`),
   cross-referenced against BCS history and confirmed directly against the
   1998 and 2000 raw files.
2. **`CFP-R1`** (12-team first round) — explicit in `Notes` from 2024 onward
   (`"College Football Playoff - First Round"`).
3. **`CFP-SF`** (semifinal) — **never** named as such in `Notes`, in either
   the 4-team (2014–2023) or 12-team (2024+) era — just the host bowl's
   ordinary name. Handled via a season→bowl-pair lookup (`CFP_SEMIFINAL_PAIR`),
   a 3-year rotation cycle (Rose/Sugar → Orange/Cotton → Fiesta/Peach),
   confirmed directly against the 2024/2025 raw files and against
   independent sources for 2014–2023.
4. **`CFP-QF`** (12-team quarterfinal, 2024+ only) — whichever New Year's Six
   bowl isn't that season's semifinal host (`NY6_BOWLS`) — also never
   explicitly named as a quarterfinal in `Notes`.
5. **`CCG`** (conference championship) — `"Championship"` appearing in
   `Notes`. **Only checked after NC is ruled out** — both `"BCS
   Championship"` and `"College Football Playoff National Championship"`
   also contain the word "Championship," and would otherwise be
   misclassified as a conference championship game. This was a real bug in
   the codebase before this session (harmless in practice only because
   `conf_championship_mult` was still `1.0`).
6. **`BOWL`** — every other bowl, identified by `"Bowl"` appearing in
   `Notes`. **Deliberately not split into a hardcoded "major bowl" name
   list** (the earlier design direction, which would have needed its own
   era-branching — BCS-era "major" bowls ≠ NY6 bowls ≠ the pre-BCS "big
   bowls," and the set changes again once a bowl becomes a CFP host some
   years and not others). Instead, bowl importance is scored directly off
   the two teams' own AP ranks at the multiplier level — see below.
7. `None` — regular season.

**New this session — every `"___ Bowl"`-based check above (NC's
embedded-title case, CFP-SF, CFP-QF, and plain BOWL) is gated to a
December-through-June window** (`date.month == 12 or date.month <= 6`,
reusing `season_for_date()`'s own year-boundary convention). Root cause:
Sports-Reference's `Notes` field also carries venue names for ordinary
regular-season games, and several stadiums are themselves named `"___ Bowl"`
— Memphis's Liberty Bowl Memorial Stadium, UTEP's Sun Bowl Stadium, Toledo's
Glass Bowl, UCLA's Rose Bowl — plus the annual regular-season
Texas-Oklahoma game, played every October at the Cotton Bowl in Dallas.
Without the date gate, `"\bBowl\b"` matches those venue names directly, and
the CFP-SF semifinal-pair check had the *identical* collision independently
(2015's semifinal host was the Cotton Bowl, 2017's was the Rose Bowl — every
UCLA or Texas-OU regular-season game those years was already being
misclassified as `CFP-SF` before this fix). Confirmed and fixed: 113 real
false positives across 1996-2025, re-ingested via `reingest_phase2.py`.

**The CCG (`"Championship"`) check is deliberately NOT gated the same way —
this needed its own, different reasoning, not just a wider version of the
same date window.** Two things ruled out a shared gate: (1) `"Championship"`
has zero observed collision risk with any venue name across 30 years of
data, so it doesn't need a gate at all; (2) Championship Saturday itself
sometimes falls on **November 30** (confirmed: MAC/Pac-12 in 2001, 2006,
2012, 2018) — gating CCG to December would have incorrectly dropped those,
and widening the BOWL-side gate into late November to cover them instead
would reintroduce the venue-collision bug (Memphis/UTEP/Toledo/UCLA all play
real regular-season home games that late too — confirmed 12 such collisions
checking just the Nov 20-30 window).

**Two multiplier mechanisms apply these, both firing regardless of `type`**
(every CFB game, postseason included, is still `type='R'` by design — see
`normalize_sr_games.py`'s docstring):

- **`_postseason_mult()` / `postseason_round_mult`** — a CCG-style,
  type-agnostic parallel to NFL_Elo's inherited `playoff_round_mult`. This
  is necessary because `playoff_round_mult`/`_po_mult()` are **permanently
  inert for CFB** — they only ever fire for `type='P'` games, which never
  happens here. `playoff_round_mult` is kept only for structural parity
  with NFL_Elo; don't confuse the two when reading `engine.py`.
- **`_bowl_mult()` / `bowl_mult` + `bowl_rank_*`** — for `Round=="BOWL"`
  only. Both teams ranked → bonus decays **exponentially** off the best
  possible combined AP rank (`home_ap_rank + away_ap_rank`, ranges 3
  best-case to 49 worst-case) — a top-5-vs-top-5 bowl is disproportionately
  more major than a linear falloff would give it (explicit design choice —
  linear was the first draft, rejected). Exactly one team ranked → a much
  smaller, compressed-scale exponential bump using that team's own rank
  (deliberately small: this tier is rare and rarely involves a
  highly-ranked team anyway). Neither ranked → the flat `bowl_mult` base
  only.

**All of `postseason_round_mult`, `bowl_rank_bonus_max`, and
`bowl_one_ranked_bonus_max` are still at their no-op defaults** (`{}` /
`0.0`) — same "untuned placeholder" convention as `conf_championship_mult`
always has been. **Classification is done and now trustworthy (the
venue-collision bug above is fixed); the actual multiplier VALUES remain
untuned by deliberate decision** — see §10, item 2 for the reasoning on why
this is being left alone for now rather than tuned opportunistically.

**Source-data dedup** (`normalize_sr_games.dedupe_raw_rows()`) runs
immediately before classification, for a specific reason: `add_season.py`'s
insert uses `INSERT OR IGNORE` keyed on `(date, home, away, type, round)`.
Two raw rows for the same real game that differ only in `Notes` text used to
dedupe by accident (both got `Round=None` under the old CCG-only
classification) — but once classification can tell them apart (one
recognizes a bowl/event name, the other doesn't), they'd get *different*
`round` values and both insert successfully, double-counting that game. See
§2 for the concrete cases this actually caught.

## 6. Tuning philosophy — two tracks, not one grid search

- **Track A (log-loss coordinate ascent)** — `alpha`, `kmax`, `hfa`,
  `fcs_rating`, and (not yet added) `conf_game_mult`/`conf_championship_mult`/
  the new postseason multipliers. These directly reshape a game's predicted
  outcome, so minimizing prediction error is the right objective.
- **Track B (data-driven calibration, NOT grid search)** — things like the
  first-year-FBS discount (§5c/§10). These should be *measured* from
  observed outcomes, not searched for by minimizing overall log-loss, which
  risks quietly overfitting one noisy number to a handful of newcomer-seasons.

## 7. Tuning results — now a real walk-forward schedule, not a single window

**This is the biggest change since the last handoff.** `param_schedule.json`
now exists and is populated for every season 1996–2025 (built by
`cfb_build_param_schedule.py` — see §3 for its methodology). Sample values,
showing genuine era drift rather than one flat number everywhere:

| Season | alpha | kmax | hfa | fcs_rating |
|---|---|---|---|---|
| 1996 | 0.7 | 96 | 68 | 1100 |
| 2006 | 0.7 | 96 | 68 | 1075 |
| 2010 | 0.7 | 88 | 68 | 1075 |
| 2014 | 0.6 | 100 | 60 | 1075 |
| 2020 | 0.6 | 100 | 44 | 925 |
| 2025 | 0.6 | 100 | 44 | 925 |

`fcs_rating` is tuned separately (`cfb_tune_fcs_rating.py`, era-block values:
1100 for 1996–2005, 1075 for 2006–2015, 925 for 2016–2025 — too thin a
sample to tune on the same rolling cadence as the other three) and slotted
in by season when the schedule is built. `alpha`/`kmax`/`hfa` are searched
per rolling 10-year window, seeded from one continuous engine's real
snapshotted state at each window boundary — genuinely equivalent to what
production's continuous replay does, not an artificial fresh-restart-per-window
search. **Confirmed this session: `param_schedule.json` contains no entries
for `postseason_round_mult`/`bowl_mult`/`conf_championship_mult`** — those
still fall back to `engine.py`'s untuned `BASELINE_PARAMS` defaults for
every season, regardless of the schedule. This is the concrete gap behind
§10, item 1.

The original "2006 parameters" walk-forward validation from the previous
handoff (`alpha=0.7, kmax=96, hfa=68`, holdout log-loss 0.4998 vs. untuned
baseline's 0.5176) is superseded by this full schedule — no need to keep
re-deriving that one-window proof of concept, it's been generalized into
the real cadence now.

## 8. Accuracy snapshot — REFRESHED this session after the venue-collision fix (§5e), Echo variant

**The table below supersedes the previous handoff's numbers, which were
computed on contaminated data** (104-113 misclassified regular-season games
mixed into the BOWL/CFP-SF buckets — see §2 and §5e). This round-by-round
breakdown is from a direct post-fix query (`check_bowl_accuracy.py`,
included this session) against the real re-ingested `cfb_elo.db`:

| Round | n (games) | Accuracy | Brier |
|---|---|---|---|
| BOWL | 922 | 60.2% | 0.2382 |
| CCG | 148 | 72.3% | 0.1892 |
| CFP-R1 | 8 | 87.5% | 0.1325 |
| CFP-QF | 8 | 50.0% | 0.2689 |
| CFP-SF | 24 | 62.5% | 0.2056 |
| NC | 28 | 53.6% | 0.2500 |
| Regular season | 21,750 | 74.7% | 0.1683 |

Baselines for context: coin flip = 0.2500 Brier; always-pick-home ≈ 62%
accuracy.

**What changed vs. the contaminated numbers, and why it matters:** BOWL
accuracy actually went DOWN (60.2%, was 61.9%) — the misclassified games
(mostly Memphis/UTEP/Toledo beating overmatched non-conference opponents)
were easy, correctly-predicted games that had been quietly propping the
number up. The real postseason gap is a bit worse than originally reported,
but now it's measuring the right thing. CFP-SF improved substantially
(62.5%, was 51.5%) now that its own independent venue-collision false
positives (2015 Cotton Bowl, 2017 Rose Bowl — see §5e) are gone.

**Reading the BOWL gap:** TJ's read, which the data doesn't contradict — a
lot of non-CFP bowl games are closer to preseason exhibitions than
high-stakes postseason football for a lot of the teams in them (opt-outs,
portal departures, low stakes for a 6-6 team in a minor bowl), which an Elo
model that only ever sees team-vs-team results has no way to see. `CFP-SF`/
`NC` sitting near a coin flip is a small sample (24-28 games) and may partly
reflect that a title-adjacent game is, by construction, a matchup between
two elite teams with a genuinely small true gap — not necessarily a
calibration failure.

**Not yet refreshed:** the overall all-games/regular-season-vs-postseason
aggregate figures and log-loss numbers from the original `cfb_accuracy_report.py`
full report weren't regenerated this session (that script wasn't available
in this environment — only the round-by-round query above was run directly).
Worth a full `cfb_accuracy_report.py` re-run for the complete picture,
including the calibration table, before treating this section as fully
up to date.

## 9. Standard per-season / update-season workflow

```
python3 normalize_sr_games.py Results/CFB_YYYY_Results.csv parsed_results/parsed_games_YYYY.csv
python3 add_season.py parsed_results/parsed_games_YYYY.csv
python3 load_conference_membership.py Standings/CFB_YYYY_Standings.csv --season YYYY
```

**Order matters:** conference membership must load *after* games for that
season, or every team in it will look FCS (no `fbs_membership` row yet) and
get excluded from standings until the conference step catches up. Confirmed
directly this session — running these out of order on 2026 produced a
successful-looking load (260 games inserted, 0 sanity warnings) with
completely empty standings, because every team scored as FCS in the
meantime. Both `add_season.py` and `load_conference_membership.py` trigger
their own full rebuild, so re-running either is always safe.

**An in-progress (not-yet-completed) season now works correctly** (fixed
this session — see §2, §10 item 1): `normalize_sr_games.py` routes a
scoreless row to `schedule` for prediction if its date is today-or-future
(within a small buffer for a same-day result not yet posted), and still
drops it as a genuine postponement only if the date is further in the past.
After running the three commands above for an in-progress season, run
`python3 simulate_season.py --season YYYY` too if season projections are
wanted (ported this session — see §3).

## 10. What's left to do (in rough priority order)

**Items 1, 3, 4, 8, and 11 from the previous handoff are done this session.**
Item 2 is deliberately deferred (not forgotten). Item 9 is deliberately
deferred (not urgent, see its entry). Item 10 was reviewed and needs no
change unless a design preference changes. **Item 6 is the live item** — the
rest of this list exists mostly so nothing gets silently dropped.

1. ~~Fix the unplayed-games/schedule bug.~~ **DONE.** `normalize_sr_games.py`
   now routes a scoreless row to `schedule` (today-or-future date) instead of
   dropping it, and only drops a genuine stale postponement. Validated
   end-to-end against the real 630 upcoming 2026 games. See §2, §9.

2. **Tune the postseason multipliers — explicitly SKIPPED for now, by
   decision, not an oversight.** `postseason_round_mult`, `bowl_rank_bonus_max`,
   `bowl_one_ranked_bonus_max`, and `conf_championship_mult` are all still at
   their no-op defaults. Classification is done and now trustworthy (§5e),
   so this is a legitimate Track A job whenever it's picked back up — just
   not now. Worth re-reading §8's reading of the BOWL gap first if/when this
   gets revisited: TJ's view is a lot of the gap reflects real low-stakes/
   opt-out dynamics an Elo model can't see, not something tuning alone fixes.

3. ~~Investigate the `BOWL`-accuracy gap as its own question.~~ **DONE** —
   turned out to be a data-classification bug, not a modeling gap. See §5e
   and §8 for the full root-cause and corrected numbers.

4. ~~Port `simulate_season.py`.~~ **DONE** — ported from
   `TRACERsports/DBs/nfl/simulate_season.py`, CFB-specific conference/FBS
   annotation fix added, validated against real 2026 data. See §3.

5. **`DBs/` migration — core move DONE this session, some structural gaps
   remain.** `CFB_Elo/` → `DBs/cfb/`, `cfb_elo.db` → `DBs/cfb_elo.db`,
   every `DB_PATH` reference updated to the sibling-repo convention,
   committed/pushed, confirmed working against the real database
   (`rebuild_ratings_only.py`, `predict.py`, `franchise.py` all ran clean
   from the new location). **Remaining gaps**, your call on whether "match
   the structure" extends this far: `delete_season.py`, `report.py`,
   `stabilization_check.py`, `test_db.py`, `test_engine.py` exist for
   nba/nfl/wnba but not CFB yet, and `cfb_accuracy_report.py`'s name doesn't
   match the sibling `report.py` convention.

6. **Supabase/site integration — THE LIVE ITEM, concrete scope now known.**
   `export_to_supabase.py` has zero CFB awareness; closing that gap turned
   out to split into three genuinely different pieces of work, not one:
   - **Easy, mechanical:** add `"cfb": "football"` to `SPORT_FOR_LEAGUE` and
     a `"cfb"` entry to `ACTIVE_CODES`. The `--league` CLI flag
     auto-validates off `SPORT_FOR_LEAGUE`'s keys, so this alone unblocks
     running the exporter at all. Open design question: `ACTIVE_CODES` for
     the pro leagues is a small hand-maintained set of ~30 franchises that
     rarely change — CFB has ~136 FBS teams with real year-to-year
     membership churn (realignment), so hand-maintaining it the same way is
     a maintenance trap. Since `fbs_membership` already tracks exactly this,
     generating `ACTIVE_CODES["cfb"]` from the current season's
     `fbs_membership` at export time (instead of hardcoding it) is probably
     the right call.
   - **Real, blocking gap:** `build_games()`'s and `build_season_projection()`'s
     raw SQL queries match CFB's actual `ratings`/`season_projections` schema
     columns exactly (verified directly — `w`/`l`/`t`/`r1w`.../`fw`/`fl` and
     `median_wins`/`trials`/`remaining_games`/`computed_at` are all already
     there) — but `build_schedule()` selects `p.predicted_spread` from
     `schedule_predictions`, and that column **does not exist at all** in
     CFB's `schedule_predictions` table, not just NULL. This isn't a
     one-line fix: NFL's `predicted_spread` isn't a rule-of-thumb constant
     (not "538's Elo/25") — it's a real regression fit against actual Vegas
     closing lines (`spread.py`, calibrated against `games_betting.csv`,
     refit periodically). No equivalent CFB betting-lines dataset exists in
     this repo. Until this is resolved, `build_schedule()` will hard-crash
     against `cfb_elo.db`. Options: (a) add the column now as nullable and
     leave it NULL for CFB until real odds data + a calibrated CFB
     `spread.py` exist, or (b) source a CFB betting-lines dataset and build
     the calibration now. (a) is almost certainly the right near-term call —
     don't invent an uncalibrated conversion constant just to fill the
     column.
   - **Real, substantial content-authoring project, not a data export:**
     `lib/sports/cfb/config.js` doesn't exist. Looking at `lib/sports/nfl/config.js`
     as the template, this needs hand-authored conferences, divisions, a
     `playoffFormat` definition, and a full per-team roster with colors —
     for CFB that's ~136 teams across ~10 conferences (SEC, Big Ten, ACC,
     Big 12, American, Mountain West, MAC, C-USA, Sun Belt, independents)
     and a 12-team CFP bracket with byes for the top 4 seeds plus both
     at-large and conference-champion auto-bids — a meaningfully bigger and
     differently-shaped job than any pro league's config. This deserves
     planning as its own effort, not a quick addition alongside a bug fix.

   **Suggested near-term scope, not yet started:** add the two dict entries,
   add `predicted_spread` as a nullable column and skip CFB calibration for
   now, and start `config.js` with just the team roster/conferences/colors —
   defer the playoff bracket display until closer to the actual CFP.

7. **First-year-FBS discount calibration (Track B) — still not actionable.**
   Needs enough real newcomer-season data to measure from, which doesn't
   exist yet. Don't grid-search this (§6) once it is actionable.

8. ~~Fix `add_season.py`'s stale docstring.~~ **DONE** — the stale
   "Round=None for bowls" paragraph is removed, and the Round description at
   the top of the file's docstring now reflects real classification.

9. **Close `predict.py`'s known gap — deliberately deferred, low urgency.**
   `preview_matchup()` falls back to a flat `base` rating (not
   conference-average) when previewing a season with zero real games loaded
   yet. Investigated this session: `conn` is already available at the one
   call site (`predict_all()`), so threading it through is structurally
   feasible, but a correct fix isn't a one-liner — it needs to find every
   other returning team in the same conference, average their current
   ratings (with the same overall-FBS-average fallback `rebuild.py`'s real
   `_enter_season()` uses for empty conferences), and handle the previewed
   team itself being a debut (needing the 50/50 fcs_rating blend too). Only
   matters in the narrow window before a season's very first game is loaded
   — once `add_season.py` has loaded even one real game, the real
   conference-average logic takes over automatically. **Decided this
   session:** not worth building now, since the 2026 season is already
   loaded and running — this window won't matter again until next season's
   preseason, ~11 months out.

10. ~~Extend `conference_tier` seed data.~~ **REVIEWED this session, no
    change made.** Researched the actual history: the WAC (pre- and
    post-1999 Mountain West split) and the American (formed 2013) were never
    AQ/Power-5-equivalent conferences at any point — Group of Five by any
    standard definition, same tier as Conference USA/MAC/Sun Belt, which
    already correctly default to `midmajor`. The existing fallback already
    handles all of them correctly; there's no actual gap to fill under the
    current binary power/midmajor scheme. **Open question for TJ, not yet
    decided:** whether a third tier is wanted for a conference like the
    American (competitive enough to lose Cincinnati/Houston/UCF to the Big
    12 in 2023) or whether binary is fine as-is.

11. ~~Routine maintenance: check `reports/unresolved_conference_teams_*.csv`.~~
    **DONE for 2026** — ran `load_conference_membership.py` against the real
    `Standings/CFB_2026_Standings.csv`: 0 unresolved teams, no `KNOWN_ALIASES`
    gaps. Still something to re-check whenever a new season is loaded.

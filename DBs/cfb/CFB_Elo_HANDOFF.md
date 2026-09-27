# CFB_Elo — Project Handoff

**Status as of this handoff:** Core Elo engine is solid, data-driven-tuned,
and (as of this session) has real postseason-round classification instead
of the earlier CCG-only version. 30 historical seasons (1996–2025) plus a
partial 2026 season are loaded and validated. **Not yet ready to treat like
the live NBA/NFL/WNBA site sections** — the current-season prediction
pipeline has a real bug (see §10, item 1), the postseason multipliers are
still untuned no-ops, and there is zero integration outside the `CFB_Elo/`
folder itself (no Supabase export, no frontend awareness).

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

Repo: `github.com/thomassutton-afk/tracersports-app`, in the `CFB_Elo/`
subfolder (a separate Python/SQLite data-engineering project, distinct from
the site's Next.js/Supabase frontend). The site itself has `DBs/nba`,
`DBs/nfl`, `DBs/wnba` following a consistent pattern — `CFB_Elo` still lives
at the repo root, not under `DBs/`, and hasn't been migrated in (see §10,
item 5).

## 2. Current data state

- **30 full historical seasons (1996–2025), plus a partial 2026 season**
  loaded and in progress. ~23,987 completed games through 2025, plus 260
  completed 2026 games as of this handoff (630 remaining 2026 games are
  currently NOT in the pipeline at all — see §10, item 1, this is a real bug,
  not an intentional gap).
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

## 3. File-by-file summary

| File | What it does |
|---|---|
| `db.py` | SQLite schema + all data-access helpers. See §4 for the CFB-specific schema additions. |
| `engine.py` | The actual Elo math (`EloEngine`, weekly-batch replay). See §5 for the season-entry/FCS/postseason mechanics — these are the parts that differ meaningfully from the NFL version. |
| `rebuild.py` | Replays all games from `games` into `ratings`, from scratch, for one rating variant. Owns `apply_season_entry()` — the actual implementation of the conference-average algorithm (engine.py just executes what this hands it). |
| `add_season.py` | Loads one season's normalized CSV into `games`/`schedule`, registers new teams, triggers a full rebuild, writes schedule predictions. **Its own docstring's "postseason: Round=None for bowls" paragraph is now stale** — fix this next time you're in the file, see §10. |
| `franchise.py` | `rename` (cosmetic name fix), `realign` (conference change), `revive` (fold+revival reset). No `relocate` — CFB programs don't physically relocate the way NFL/NBA franchises do. |
| `normalize_sr_games.py` | Converts a raw Sports-Reference schedule CSV into the standardized per-team-row shape `add_season.py` expects. Handles AP rank parsing, team-code slugification, season-year logic for bowl games, source-data dedup, and full postseason `Round` classification (see §5e). **Known bug:** unconditionally drops any row with no final score — this was fine when the assumption was "only completed historical seasons get loaded" but breaks for an in-progress current season, where most unscored rows are real future games, not postponements. See §10, item 1. |
| `load_conference_membership.py` | Loads one season's Standings CSV into `team_conference_history` + `fbs_membership`. Triggers a full rebuild (FBS status now affects rating math, not just display). **Must be run for a season AFTER `add_season.py` has loaded that season's games** — otherwise every team in it silently scores as FCS (fixed rating, no persisted `ratings` row, invisible in standings) until this catches up. Confirmed directly this session loading 2026: 260 games loaded fine, but standings came back completely empty until this was run. |
| `cfb_tune_engine.py` | Coordinate-ascent tuner over `alpha`/`kmax`/`hfa`/`fcs_rating` for one window, using the real engine (not a reimplementation). |
| `cfb_tune_fcs_rating.py` | Separate era-block tuning for `fcs_rating` specifically (too thin a sample to tune on the same rolling cadence as the others). |
| `cfb_build_param_schedule.py` | **New since the last handoff.** Builds the actual `param_schedule.json` (see §7) via a rolling 10-year walk-forward search, seeded from one continuous engine's real snapshotted state at each window boundary (not a fresh flat restart per window) — genuinely equivalent to what production's continuous replay does. Heavy compute job (30 seasons × coordinate-ascent search × real multi-season replay per candidate) — a "kick off and let it churn" script. |
| `cfb_accuracy_report.py` | **New since the last handoff.** Accuracy/calibration report: overall + regular-season + postseason (by round) accuracy/Brier/log-loss, by-season and by-month breakdowns, calibration table, biggest upsets, worst predictions. See §9 for current output. |
| `rebuild_ratings_only.py` | **New since the last handoff.** Thin wrapper that just re-runs `rebuild.rebuild_ratings()` for both variants against an existing `cfb_elo.db` without touching `games` — useful after a params or engine change that doesn't need a re-ingest. |
| `cfb_worst_season_endings.py` | Analysis script — not part of the core pipeline. |
| `predict.py` | Predicts upcoming/unplayed games from current ratings. Has one known simplification — see §10. |
| `simulate_season.py` | **Does not exist yet.** Season Monte Carlo projections are a no-op in `add_season.py` (prints a message, skips gracefully) until this is ported from NFL_Elo. |

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

### 5e. Postseason — full classification done this session (values still untuned)

**Round now takes one of:** `"CCG"`, `"NC"`, `"CFP-R1"`, `"CFP-QF"`,
`"CFP-SF"`, `"BOWL"`, or `None` (regular season). Classification happens in
`normalize_sr_games.classify_round(notes, season)`, checked in this order
(order matters — see the NC/CCG note below):

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

**Two multiplier mechanisms apply these, both new this session, both firing
regardless of `type`** (every CFB game, postseason included, is still
`type='R'` by design — see `normalize_sr_games.py`'s docstring):

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
always has been. **Classification is done; the actual multiplier VALUES are
not tuned yet.** This is the top item in §10.

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

## 8. Accuracy snapshot (from `cfb_accuracy_report.py`, full 1996–2025+partial-2026 history, Echo variant)

Use this as the baseline to compare against once the postseason multipliers
(§5e) actually get tuned — right now these numbers reflect classification
with zero postseason-specific rating impact yet.

| Scope | n | Accuracy | Brier | Log-loss |
|---|---|---|---|---|
| All games | 23,943 | 74.9% | 0.1666 | 0.4993 |
| Regular season | 22,692 | 75.6% | 0.1633 | 0.4916 |
| Postseason (all) | 1,251 | 62.7% | 0.2251 | 0.6391 |

Baselines for context: coin flip = 0.2500 Brier; always-pick-home = 62.2%
accuracy.

**By postseason round:**

| Round | n | Accuracy | Brier |
|---|---|---|---|
| BOWL | 1,026 | 61.9% | 0.2295 |
| CCG | 148 | 72.3% | 0.1892 |
| CFP-R1 | 8 | 87.5% | 0.1325 |
| CFP-QF | 8 | 50.0% | 0.2689 |
| CFP-SF | 33 | 51.5% | 0.2383 |
| NC | 28 | 53.6% | 0.2500 |

**Reading this:** the model is well-calibrated overall (predicted vs. actual
win rate matches within ~1 point across every probability bucket — see the
full report for the calibration table). `BOWL` games are doing almost all of
the postseason accuracy damage, plausibly a real structural gap (roster
opt-outs, portal departures, a month of dead time between selection and
kickoff) that an Elo model — which only ever sees team-vs-team results —
has no way to see. `CFP-SF`/`NC` sitting near a coin flip is a small sample
(28–33 games) and may partly reflect that a title game is, by construction,
a matchup between two elite teams with a genuinely small true gap between
them — not necessarily a calibration failure. Worth re-running this report
after the postseason multipliers are tuned to see whether tuning moves
these numbers at all (it may not — the multipliers change how much a result
*teaches* the model, not the pre-game win probability itself).

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

**Known limitation for an in-progress (not-yet-completed) season:**
`normalize_sr_games.py` currently drops any row with no final score
entirely — it does NOT route future/unplayed games into the `schedule`
table the way `add_season.py`'s docstring says it should. This was never a
problem loading a fully-completed historical season (a handful of
postponements, genuinely rare), but for the current season it means
hundreds of legitimate future games are simply absent from the pipeline,
not sitting in `schedule` awaiting a prediction. **This needs an actual code
fix** (distinguish "postponed/cancelled in an otherwise-complete season"
from "hasn't been played yet in the current season" as two different
cases) — see §10, item 1.

## 10. What's left to do (in rough priority order)

1. **Fix the unplayed-games/schedule bug.** `normalize_sr_games.py` drops
   every unscored row instead of routing it to `schedule` for prediction.
   This is the actual blocker for the current season being usable for
   anything resembling "here's who's favored this week" — confirmed
   directly this session loading 2026 (630 future games silently absent
   from the pipeline). Needs a real code change, not a workaround.

2. **Tune the postseason multipliers.** Classification (§5e) is done and
   validated; `postseason_round_mult`, `bowl_rank_bonus_max`,
   `bowl_one_ranked_bonus_max`, and `conf_championship_mult` are all still
   at their no-op defaults. Now that real postseason data exists with real
   `Round` labels, this is a legitimate Track A tuning job. Worth
   re-running `cfb_accuracy_report.py` afterward to see whether it moves
   the postseason accuracy numbers in §9 at all.

3. **Investigate the `BOWL`-accuracy gap (61.9%) as its own question,
   separate from tuning.** Plausibly a structural gap (roster opt-outs,
   portal departures) an Elo model can't see regardless of how well-tuned
   its multipliers are — worth deciding whether that's an accepted
   limitation or something worth investigating further before assuming
   tuning alone will fix it.

4. **Port `simulate_season.py`** from NFL_Elo if season projections are
   wanted for CFB (currently a graceful no-op in `add_season.py`).

5. **Decide on the `DBs/` migration.** The site's other sports live under
   `DBs/nba`, `DBs/nfl`, `DBs/wnba`; `CFB_Elo` still lives at the repo root.
   Structural gaps beyond just moving the folder: missing
   `accuracy_report.py`-equivalent (now actually exists as
   `cfb_accuracy_report.py` — naming convention differs from the other
   sports' `report.py`, worth aligning or not), `delete_season.py`,
   `stabilization_check.py`, `test_db.py`, `test_engine.py` don't exist for
   CFB yet.

6. **Zero integration outside `CFB_Elo/` itself.** `export_to_supabase.py`'s
   `SPORT_FOR_LEAGUE`/league-config dicts have no CFB entries, `schema.sql`
   has no CFB/college references, `lib/sports/` has no `cfb/` config folder,
   the frontend (`app/`) has no CFB references anywhere. A structurally
   perfect backend doesn't appear on the live site without this — separate
   effort from item 5.

7. **First-year-FBS discount calibration (Track B).** Once there's enough
   real newcomer data, measure how first-year FBS teams actually perform
   relative to their Step-D starting point and calibrate a discount — don't
   grid-search this (§6).

8. **Fix `add_season.py`'s stale docstring** — still claims bowls/CCGs load
   with `Round=None`, no longer true since this session's postseason work.
   Small, but will mislead whoever reads it next if left as-is.

9. **Close `predict.py`'s known gap:** `preview_matchup()` falls back to a
   flat `base` rating (not conference-average) when previewing a season with
   zero real games loaded yet — correctly reproducing the conference average
   there would need database access this method intentionally doesn't have.
   Only matters for previewing a season's very first games before any real
   results exist for it.

10. **Extend `conference_tier` seed data as gaps surface.** Only
    SEC/Big Ten/ACC/Big 12/Pac-12/old Big East are seeded — everything else
    defaults to midmajor. Worth a deliberate review pass (WAC/Mountain West
    split history, the American's tier status, etc.) rather than waiting for
    something to look wrong.

11. **Routine maintenance:** check `reports/unresolved_conference_teams_*.csv`
    whenever a new season is loaded and extend `KNOWN_ALIASES` as needed.

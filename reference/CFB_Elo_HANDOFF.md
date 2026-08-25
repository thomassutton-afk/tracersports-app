# CFB_Elo — Project Handoff

**Status as of this handoff:** Fully loaded, working, tuned-and-validated for one
window. Not yet in "shipped" state — the tuned parameters exist but haven't
been written into the engine's defaults or a walk-forward schedule yet.

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
the site's Next.js/Supabase frontend).

## 2. Current data state

- **30 seasons loaded: 1996–2025.** ~23,990 games, 259 teams, both rating
  variants (Echo = continuous carryover, Pulse = full reset each season)
  computed and stored in `cfb_elo.db`.
- Conference membership (`team_conference_history`) and FBS status
  (`fbs_membership`) loaded for every season via `load_conference_membership.py`.
- No known unresolved teams or load errors as of the last full reload.
- Two rows are correctly, deliberately excluded: a cancelled 2013 game and a
  cancelled 2015 game (McNeese State vs. LSU) — both had no final score in
  the source data and get skipped with a printed warning, not silently
  dropped.

## 3. File-by-file summary

| File | What it does |
|---|---|
| `db.py` | SQLite schema + all data-access helpers. See §4 for the CFB-specific schema additions. |
| `engine.py` | The actual Elo math (`EloEngine`, weekly-batch replay). See §5 for the season-entry/FCS/postseason mechanics — these are the parts that differ meaningfully from the NFL version. |
| `rebuild.py` | Replays all games from `games` into `ratings`, from scratch, for one rating variant. Owns `apply_season_entry()` — the actual implementation of the conference-average algorithm (engine.py just executes what this hands it). |
| `add_season.py` | Loads one season's normalized CSV into `games`/`schedule`, registers new teams, triggers a full rebuild, writes schedule predictions. |
| `franchise.py` | `rename` (cosmetic name fix), `realign` (conference change), `revive` (fold+revival reset). No `relocate` — CFB programs don't physically relocate the way NFL/NBA franchises do. |
| `normalize_sr_games.py` | Converts a raw Sports-Reference schedule CSV into the standardized per-team-row shape `add_season.py` expects. Handles AP rank parsing, team-code slugification, season-year logic for bowl games, and Phase-1 CCG classification. |
| `load_conference_membership.py` | Loads one season's Standings CSV into `team_conference_history` + `fbs_membership`. Triggers a full rebuild (FBS status now affects rating math, not just display). |
| `cfb_tune_engine.py` | Coordinate-ascent tuner over `alpha`/`kmax`/`hfa`/`fcs_rating`, using the real engine (not a reimplementation). |
| `predict.py` | Predicts upcoming/unplayed games from current ratings. Has one known simplification — see §8. |
| `simulate_season.py` | **Does not exist yet.** Season Monte Carlo projections are a no-op in `add_season.py` (prints a message, skips gracefully) until this is ported from NFL_Elo. |

## 4. Schema additions beyond NFL_Elo

- **`team_conference_history`** — era-scoped conference/division per team
  (`team_id, conference, division, start_season, end_season`). Deliberately
  separate from `team_history` (which is for renames/relocations) — a
  conference switch isn't a relocation.
- **`fbs_membership`** — `(team_id, season)`. The actual "is this team FBS
  this season" signal. Populated for every school in a season's Standings
  file, **including independents** (who deliberately get no
  `team_conference_history` row — see §5).
- **`conference_tier`** — `(conference, start_season, end_season, tier)`,
  `tier ∈ {power, midmajor}`. Used only to bucket FBS independents (who have
  no literal conference) for season-entry averaging. Auto-seeded on first
  `db.connect()` via `seed_conference_tiers()`:
  - SEC, Big Ten, ACC, Big 12 → power, 1996–present
  - Pac-12 → power, 1996–2023 (dissolved after 2023)
  - Old football-playing Big East → power, 1996–2012 (split into the
    American in 2013)
  - Everything else defaults to `midmajor` via `tier_for_conference()`'s
    fallback — **this seed list is not exhaustive**, see §8.
- **`games`/`schedule`** gained `home_ap_rank`/`away_ap_rank` (nullable,
  display-only, never read by the engine).

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
**fixed-strength opponent** (`fcs_rating` — see §7 for its tuned value):
- Used only to compute the *FBS* opponent's expected outcome/rating change.
- Never gets a `TeamState`, never gets a persisted `ratings` row, never
  appears in standings.
- This was specifically chosen to sidestep a real identity-continuity bug:
  Texas A&M-Commerce renamed to East Texas A&M in 2025 while remaining FCS
  the whole time, which split one program across two `team_id`s with no
  clean way to merge them. Since neither ever gets a real tracked rating,
  the split is harmless.

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
deliberately left as "start simple, calibrate later" — see §8, item 4.

### 5d. Conference multiplier (collapsed from NFL's two-tier system)
NFL_Elo had separate `div_game_mult` (1.1) and `conf_game_mult` (1.02).
CFB's remaining divisions are largely vestigial post-2020s realignment, so
these collapsed into a single `conf_game_mult` (seeded at 1.1, the old
division-tier value). `div_game` is still computed and stored on every
`ratings` row for potential future display use — it just no longer moves the
K-multiplier.

### 5e. Postseason — Phase 1 done, Phase 2 deferred
- **Phase 1 (done):** conference championship games are classified via a
  regex match on the raw `Notes` field (`"Championship"` — reliably matches
  "SEC Championship (Atlanta GA)", "Big 12 Championship (St. Louis MO)",
  etc. across every era regardless of exact conference name). These get
  `Round="CCG"` and a dedicated `conf_championship_mult` (currently `1.0` —
  an explicit untuned no-op placeholder). `Type` stays `'R'` for these
  (postseason games are never reclassified as `'P'`).
- **Phase 2 (deferred):** bowl/CFP-round classification. Blocked on real
  era-branching logic — the postseason *format* itself changed multiple
  times across 1996–2025 (no unified system pre-1998, BCS 1998–2013,
  4-team CFP 2014–2023, 12-team CFP 2024+). The raw `Notes` text is already
  carried through to every parsed CSV specifically so this can be built
  later without re-running the normalizer against original raw files again.

## 6. Tuning philosophy — two tracks, not one grid search

- **Track A (log-loss coordinate ascent)** — `alpha`, `kmax`, `hfa`,
  `fcs_rating`, and (not yet added) `conf_game_mult`/`conf_championship_mult`.
  These directly reshape a game's predicted outcome, so minimizing
  prediction error is the right objective. This is what `cfb_tune_engine.py`
  does.
- **Track B (data-driven calibration, NOT grid search)** — things like the
  first-year-FBS discount (§5c/§8). These should be *measured* from observed
  outcomes, not searched for by minimizing overall log-loss, which risks
  quietly overfitting one noisy number to a handful of newcomer-seasons.

## 7. Tuning results so far

Three configurations have been evaluated (full 1996–2025 history, Echo
variant, home-perspective rows only):

| Config | alpha | kmax | hfa | fcs_rating | Full-history accuracy | Full-history log-loss | Brier |
|---|---|---|---|---|---|---|---|
| Untuned (NFL-inherited placeholders) | 0.3 | 46 | 72 | 1200 | 73.77% | 0.5192 | 0.1736 |
| Full-history tune (NOT walk-forward-valid — uses all 30 years) | 0.6 | 100 | 56 | 1075 | 74.85% | 0.4989 | 0.1664 |
| **"2006 parameters"** (tuned on 1996–2005 ONLY) | **0.7** | **96** | **68** | **1075** | — | — | — |

**"2006 parameters" is the important one — this is the first real
walk-forward entry.** Tuned using *only* data through 2005 (nothing from
2006 onward was used), matching genuine walk-forward methodology: to know
what parameters should apply starting in 2006, you can only use data
available before 2006.

**Holdout validation (the check that matters):**

| | Train (1996–2005) log-loss | Holdout (2006–2025) log-loss |
|---|---|---|
| Untuned baseline | 0.5280 | 0.5176 |
| **"2006 parameters"** | 0.5036 | **0.4998** |

The "2006 parameters" performed *better* on the untouched 2006–2025 holdout
than on their own training data (0.4998 vs. 0.5036) — the opposite of
overfitting. If they'd been fit to noise specific to the early era, holdout
performance would have been *worse*, not better. This is genuine evidence
the tuned values reflect a stable property of the sport, not an artifact of
one decade's particular mix of results.

**Also notable:** `alpha=0.7`, roughly double NFL's `0.3` — CFB team
strength carries over season-to-season much more than NFL parity mechanisms
would suggest, consistent with no draft-based leveling and sustained
recruiting/roster advantages for top programs. `fcs_rating=1075` — notably
lower than the 1200 placeholder guess, meaning FCS opponents are weaker
relative to FBS than initially estimated.

**These parameters have NOT been written into `engine.py`'s
`BASELINE_PARAMS` yet, and no `param_schedule.json` exists yet.** That's the
first item in §8.

## 8. What's left to do (in rough priority order)

1. **Write "2006 parameters" into a walk-forward schedule.** The
   infrastructure already exists (`db.params_for_season()`,
   `param_schedule.json` — inherited unchanged from NFL_Elo) but is currently
   unused for CFB. Needs: an actual `param_schedule.json` file with an entry
   for season 2006 onward using `alpha=0.7, kmax=96, hfa=68, fcs_rating=1075`.
   **Open design question, not yet decided:** what should 1996–2005 itself
   use? Options: the untuned placeholder (honest about not having tuned
   that era), the same "2006 parameters" applied retroactively, or a
   separately-tuned "1996 parameters" entry. Needs a decision before writing
   the file.

2. **Build the actual walk-forward re-tuning cadence.** The "2006
   parameters" is a proof-of-concept for one window. A real walk-forward
   process needs: a decided window strategy (expanding from 1996, or a
   fixed-length rolling lookback?), a refresh cadence (every season? every
   five years?), and a repeatable script that re-tunes and appends a new
   `param_schedule.json` entry each time — mirroring whatever process was
   used for NFL_Elo (worth looking at that implementation directly if it
   still exists, rather than re-deriving the approach from scratch).

3. **Postseason Phase 2** — bowl/CFP-round classification, with real
   era-branching logic for the three-plus distinct postseason formats CFB
   has used since 1996. `Notes` is already captured and waiting.

4. **First-year-FBS discount calibration (Track B).** Once there's enough
   real newcomer data, measure how first-year FBS teams actually perform
   relative to their Step-D starting point and calibrate a discount — don't
   grid-search this.

5. **Port `simulate_season.py`** from NFL_Elo if season projections are
   wanted for CFB (currently a graceful no-op).

6. **Close `predict.py`'s known gap:** `preview_matchup()` falls back to a
   flat `base` rating (not conference-average) when previewing a season with
   zero real games loaded yet — correctly reproducing the conference average
   there would need database access this method intentionally doesn't have.
   Only matters for previewing a season's very first games before any real
   results exist for it. Documented in `engine.py`'s
   `_preview_season_entry()` docstring.

7. **Extend `conference_tier` seed data as gaps surface.** Only
   SEC/Big Ten/ACC/Big 12/Pac-12/old Big East are seeded — everything else
   defaults to midmajor. Worth a deliberate review pass (WAC/Mountain West
   split history, the American's tier status, etc.) rather than waiting for
   something to look wrong.

8. **Add `conf_game_mult`/`conf_championship_mult` to Track A tuning.**
   Currently only `alpha`/`kmax`/`hfa`/`fcs_rating` are searched.

9. **Routine maintenance:** check `reports/unresolved_conference_teams_*.csv`
   whenever a new season is loaded and extend `KNOWN_ALIASES` as needed.

## 9. Standard per-season workflow (for loading a new season later)

```
python3 normalize_sr_games.py Results/CFB_YYYY_Results.csv parsed_results/parsed_games_YYYY.csv
python3 add_season.py parsed_results/parsed_games_YYYY.csv
python3 load_conference_membership.py Standings/CFB_YYYY_Standings.csv --season YYYY
```

Order matters: conference membership must load *after* games for that
season, or every team in it will look FCS (no `fbs_membership` row yet) and
get excluded from standings until the conference step catches up. Both
`add_season.py` and `load_conference_membership.py` trigger their own full
rebuild, so re-running either is always safe.

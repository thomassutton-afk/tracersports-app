# Tracer Elo — Project Template

This describes the shared structure that `NBA_Elo` and `WNBA_Elo` are now
built to, confirmed file-for-file identical (aside from a DB path and two
tuned parameters). Use this as the spec when standing up a new sport.

**The rule: identical tooling, sport-specific math.** Every file below
should exist, with the same name, same function names, and same behavior,
in every sport's project folder. The one thing that's allowed — expected —
to differ is the actual Elo formulas inside `engine.py`, because those
encode that sport's own rules (season length, playoff structure, how rest
matters, etc.), not an arbitrary implementation choice. Don't force NFL's
K-factor or rest-day handling to match NBA/WNBA's; re-derive it from NFL's
own rules the way NBA/WNBA's was derived from the WNBA workbook.

---

## 1. File manifest

| File | Role |
|---|---|
| `db.py` | SQLite schema + all read/write helpers. No Elo math. |
| `engine.py` | Pure Elo math, no I/O. Takes/returns plain dicts. |
| `rebuild.py` | Replays `games` chronologically into `ratings`. Also holds `standings()` and `sanity_checks()`. |
| `add_season.py` | The one command to load a season file: registers new teams, inserts games, routes unplayed games to `schedule`, rebuilds, runs sanity checks, prints standings. |
| `franchise.py` | CLI for relocations, renames, and fold/revival resets — all backed by the database, not hardcoded dicts. |
| `predict.py` | Read-only win probabilities for every unplayed game in `schedule`. |
| `simulate_season.py` | Monte Carlo rest-of-season projection. |
| `accuracy_report.py` | Accuracy/Brier/log-loss report — overall, by season, by month, calibration buckets, biggest upsets, worst misses. Writes `reports/accuracy_by_game.csv` + `reports/accuracy_summary.txt`. |
| `report.py` | Writes `reports/summary.txt`, `standings.csv`, `game_log.csv`. |
| `test_db.py` / `test_engine.py` | Regression tests, each one locking in a specific bug that was found and fixed once. Not generic scaffolding — write a new one any time a real bug gets fixed. |
| `delete_season.py` | Safely remove a season's games/ratings and rebuild the rest. |

Optional, sport-specific, NOT part of the required set:
- An offline parameter-fitting tool (WNBA's `wnba_tune.py`, NFL's
  `nfl_tune.py`, CBB's `platt_calibration.py`) — different sports may want
  different fitting approaches. Build one if useful; don't force a shape.
- One-off historical bootstrap scripts (WNBA's `load_1997.py`/`load_1998.py`)
  for whatever your first-load process looks like. These are throwaway,
  not maintained long-term.
- `high_confidence_audit.py`, `verify_against_workbook.py` — genuinely
  useful diagnostic tools, but lower priority; build them if/when needed.

Deliberately NOT in the set: `set_params.py` (a live parameter-tuning CLI).
We dropped it for NBA/WNBA once parameters were locked in — retuning now
just means editing `DEFAULT_PARAMS`/`BASELINE_PARAMS` in `engine.py`
directly and running `rebuild.py`. Add it back for a new sport only while
still actively tuning; drop it once parameters stabilize.

---

## 2. Team identity model

Every team gets a **permanent synthetic ID**, e.g. `nfl_0001`, assigned
once and never changed regardless of relocation or rebrand. It's a
database key, not something anyone types or reads day-to-day — you
interact with a team through its code (`MIL`) or display name
(`Milwaukee Bucks`), never the raw ID, except when looking one up via
`franchise.py status`.

Three tables carry this:

- **`teams`** — `team_id` → current `team_name` (a simple fallback).
- **`team_aliases`** — every code a franchise has ever used (current or
  historical) → its permanent `team_id`. Loaders resolve raw source-file
  codes through this table.
- **`team_history`** — era-scoped: which `code`/`name` a franchise used
  between `start_season` and `end_season` (`NULL` = still current). This
  is what lets `standings()` show "Seattle SuperSonics" for a 1996 record
  and "Oklahoma City Thunder" for a 2010 record from the same `team_id`.

Key functions in `db.py`:
- `next_team_id(conn)` — mints the next `<sport>_NNNN` ID. **Change the
  prefix per sport** (`nfl_`, `cbb_`, etc.) — that's the one line that
  needs to differ here.
- `register_new_team(conn, code, name, start_season)` — the only correct
  way to add a brand-new franchise: mints an ID, registers the alias,
  opens the first `team_history` row. Called from `add_season.py` when a
  genuinely new code shows up, using the *earliest season that code
  appears in the file being loaded* as `start_season`.
- `rename_current_history(conn, team_id, name)` — updates the name on the
  currently-open `team_history` row, for a cosmetic fix that doesn't
  change the code (e.g. correcting a placeholder name).
- `close_team_history` / `add_team_history` — used together by
  `franchise.py relocate`/`revive` to end one era and start the next.
- `display_name(conn, team_id, season)` — the season-aware name lookup.
  Everything user-facing (`standings()`, `predict.py`, `simulate_season.py`)
  should call this, never a flat `teams.team_name` join.

`franchise.py` has three commands, each identifying a team by
`--current-code` (never a raw `team_id` — that's an internal key you
should never need to type; each command resolves the code internally
via `db.resolve_team_id` and fails with a clear message if the code
isn't registered yet):
- `relocate --current-code --alias --name --season` — same franchise, new
  code/city. Closes the old `team_history` era at `season - 1`, opens a
  new one at `season`. Rating history is untouched.
- `rename --current-code --name` — cosmetic-only, same code, updates the
  *current* era's name, doesn't open a new one.
- `revive --current-code --season --name` — same code/brand reused after a
  fold. Forces a rating reset to base at `season`, and opens a new
  `team_history` era (folds don't need any action; only revivals do).

**A team has to already be registered (i.e. have appeared in at least
one season file loaded via `add_season.py`) before any of these can act
on it.** You can't pre-relocate a franchise that doesn't exist in the
database yet through `franchise.py` alone — see §8 for how to get around
that when you already know a sport's full franchise history in advance.

---

## 3. Database schema

Six core tables, same in every sport:

```
teams            (team_id PK, team_name)
games            (game_id PK, date, season, type, round, home_team, away_team,
                   home_pts, away_pts, ot, neutral)
                 UNIQUE(date, home_team, away_team, type, IFNULL(round,-1))
schedule         (schedule_id PK, date, season, type, round, home_team,
                   away_team, neutral)   -- unplayed games ONLY, never in `games`
                 UNIQUE(date, home_team, away_team, type, IFNULL(round,-1))
ratings          (game_id, team, ... one row per team per game, PK(game_id, team))
team_aliases     (alias PK, team_id, note)
team_history     (team_id, code, name, start_season, end_season, PK(team_id, start_season))
franchise_resets (team_id, season, note, PK(team_id, season))
params           (key PK, value)   -- currently unused now that set_params.py is gone,
                                       kept for schema stability
```

`ratings` columns will vary in count depending on how many bookkeeping
fields that sport's math needs (win/loss-by-round columns, etc.) — keep
whatever the engine needs to reconstruct standings, don't force NBA's
exact column list onto a sport with a different playoff structure (NFL
doesn't have `r1w`/`r2w`/etc. in the same shape a 4-round NBA playoff
bracket does — use whatever your engine's `process_game()` actually
returns).

**The `schedule` table is not optional.** It's what prevents an
unplayed game from ever being able to look like a real 0-0 result — the
rating engine has no code path that reads from it at all.

**Why `IFNULL(round, -1)` in the unique indexes:** a plain SQL `UNIQUE`
treats every `NULL` as distinct from every other `NULL`, so regular-
season games (`round IS NULL`) would never dedupe against each other.
This is exactly the kind of thing `test_db.py` should have a regression
test for.

---

## 4. `add_season.py` contract

Given a `.csv` or `.xlsx` file (accepting either a "raw results" shape
or an "Echo Ratings"-style `RawData` sheet — adapt column names to
whatever that sport's source data actually looks like):

1. **Resolve columns.** Scores are optional — a row can be missing
   `points_for`/`points_against` entirely (a pure schedule export).
2. **Split into `homes` (has a score) and `upcoming` (doesn't).**
3. **Register new teams.** For every code that doesn't already resolve
   to a known `team_id`, call `register_new_team()` with `start_season`
   = the earliest season that code appears in *this file*. Re-resolve
   the dataframes afterward so games reference the new permanent IDs,
   not the raw codes.
4. **Insert completed games** via `db.add_game()` (deduped automatically).
5. **Insert unplayed games** via `db.add_scheduled_game()`.
6. **Prune stale schedule rows** — `db.prune_played_schedule_rows()`
   clears schedule placeholders that now have a real result.
7. **Rebuild ratings**, run `sanity_checks()`, print `standings()`.

Re-running on the same file (or a file with today's newly-final scores
appended to yesterday's schedule) must always be safe — that's the
point of the dedup + prune step.

---

## 5. Engine contract

`engine.py` needs, at minimum:

- `BASELINE_PARAMS` / `default_params()` — the sport's original tuned
  values, frozen, never mutated in place.
- `EloEngine(params, resets)` with `process_game(g) -> [row_home, row_away]`
  — the one function that mutates state, called only for real, completed
  games during a chronological replay.
- `preview_matchup(home_team, away_team, game_date, season, type_, round_,
  neutral) -> dict` — the **read-only** twin of `process_game()`. Must
  not mutate any engine state. This is the one piece of genuinely new
  logic (beyond `process_game`) every sport's engine needs, since
  `predict.py`/`simulate_season.py` both depend on it.
- A season-entry guard: whatever handles season-to-season regression
  and forced resets must fire **exactly once** per (team, season) — not
  once per game. Guard on "have I already entered this season" *first*,
  before checking anything else (including forced resets), or a reset
  will silently re-fire before every game of that season instead of
  just the opener. This was a real bug we found and fixed in NBA's
  engine — write a `test_engine.py` case for it in every sport.

---

## 6. Naming conventions

- `DB_PATH = "<sport>_elo.db"` — a plain module-level constant in every
  script that touches the database, not a CLI argument. (Exception:
  `accuracy_report.py` additionally takes `--seasons` as a filter.)
- Team ID prefix: `<sport>_NNNN`, e.g. `nfl_0001`.
- `OUT_DIR = "reports"` for every script that writes output.
- Script docstrings should name the actual sport/league in their title
  (not copy-pasted from another project — we found and fixed two of
  these copy-paste artifacts already, in a README and in `engine.py`'s
  header).

---

## 7. Testing convention

`test_db.py` and `test_engine.py` are not boilerplate — each test case
documents one specific bug that was found and fixed, so it can never
silently come back during a future refactor. When you port code between
sports (or fix a bug in one), check whether the other sports need the
same fix, and add a matching regression test in each.

Before considering a new sport "synced" to this template, run a smoke
test: load a tiny CSV with a brand-new team and one unplayed game
through `add_season.py`, confirm the team gets a real synthetic ID and
an open `team_history` row, confirm the unplayed game lands in
`schedule` not `games`, then run `franchise.py relocate`/`rename`
against it and confirm the era history updates correctly. This is the
same test sequence used to validate the NBA/WNBA sync — see the
worked example against a temp database in this project's chat history
if you want the exact commands.

---

## 8. Pre-seeding known franchise history

`franchise.py` only operates on teams that already exist in the
database — it has no path for "set up this team's history before it's
ever appeared in a game." For a brand new sport, that's usually fine:
load season files in chronological order, and run `relocate`/`rename`/
`revive` right when you reach the season each one takes effect.

But if a sport's *entire* relocation/rename history is already known
in advance (true for NFL — every relocation from 1996 onward is a
matter of public record), it's worth pre-seeding all of it in one pass,
before loading any game data, rather than interleaving `franchise.py`
calls between season loads:

1. Write a one-time script with a static table of every franchise's
   full history: `{team_id_seed_key: [(code, name, start_season,
   end_season_or_None), ...]}`, in chronological order per franchise.
2. For each franchise, call `db.register_new_team()` for its *first*
   era, then `db.close_team_history()` + `db.add_team_history()` for
   each subsequent era — exactly what `relocate` does internally, just
   run directly against the known table instead of one CLI call at a
   time.
3. Also seed `team_aliases` for any alternate codes other data sources
   use for the same franchise (e.g. nflverse's post-move codes for a
   team the box scores otherwise track under one continuous code).

After that, `add_season.py` never sees a "new" team at all — every code
in every season file already resolves through an alias to a franchise
that already has its complete, correct era history. This only works
because the history is fully known upfront; don't do this for a sport
where relocations are still happening or historical data is uncertain,
since register_new_team's start_season is meant to reflect *when a code
first actually appears in loaded data*, not a guess.



## 9. Checklist for bringing a new sport online

1. Re-derive `engine.py`'s math from that sport's own rules/workbook —
   don't port NBA/WNBA's formulas. Keep the module structure (`BASELINE_PARAMS`,
   `EloEngine`, `process_game`, `preview_matchup`, the season-entry guard)
   the same shape.
2. Build `db.py` from the schema in §3, with the sport's own `next_team_id`
   prefix.
3. Build `add_season.py` per the contract in §4, adapted to that sport's
   actual source-file column names/shape.
4. Build `rebuild.py`, `franchise.py`, `predict.py`, `simulate_season.py`,
   `accuracy_report.py`, `report.py`, `delete_season.py` — these should
   need little to no sport-specific logic at all, since none of the
   NBA/WNBA versions of these files contain any NBA/WNBA-specific
   assumptions once `DB_PATH` is swapped.
5. Write `test_db.py`/`test_engine.py`, including the dedup and
   season-entry-guard cases at minimum.
6. Smoke test per §7.
7. Load real historical data via `add_season.py` (or a one-off bootstrap
   script if the historical data needs special handling), confirm
   `accuracy_report.py` output looks sane against the actual historical
   record.

# WNBA Echo Ratings — Elo Model

A Python + SQLite rebuild of the `WNBA_Echo_Ratings_1997.xlsx` Elo model.
Verified against the original workbook: all 230 game-rows in `RawData`
match to floating-point precision, and the final standings / post-
playoff ratings match the `Standings` and `Playoffs` sheets exactly.

## Files

- `engine.py` — the rating math (home-court edge, rest adjustment,
  margin-of-victory scaling, dynamic K-factor, playoff multipliers,
  season-to-season regression to the mean). Pure Python, no state
  outside what you pass in.
- `db.py` — SQLite schema and read/write helpers.
  - `games` — the raw input: one row per actual game (date, season,
    type, round, home/away team, scores, OT flag).
  - `ratings` — the engine's output: one row per team per game
    (pre/post rating, expected win %, rating change, W/L, etc.),
    equivalent to the original `RawData` sheet.
  - `teams` — team_id → team name.
- `rebuild.py` — replays every game in `games` through the engine, in
  chronological order, and refills `ratings`. Also has a `standings()`
  helper.
- `add_season.py` — **the only script you need going forward.** Point
  it at a new season's file and it loads, dedupes, rebuilds, and
  sanity-checks in one command (see below).
- `verify_against_workbook.py` — one-off diff tool against an original
  Echo-Ratings-style workbook, for whenever you still have one to
  cross-check.
- `test_engine.py` / `test_db.py` — regression tests for the two real
  bugs found while validating 1998-2000 (see below). Run these after
  any change to `engine.py` or `db.py`.
- `wnba_elo.db` — the database itself (1997-2000 loaded, 748 games).

## Checking model accuracy

```
python3 accuracy_report.py
```

Computes, for every game in the database: whether the favored team
actually won (**accuracy**), the squared error between predicted and
actual outcome (**Brier score** - lower is better, 0.25 is the
baseline for always guessing 50/50), and **log loss** (penalizes
confident wrong predictions much more heavily than Brier).

Prints an overall/regular-season/playoff summary to the terminal, and
writes two files to `reports/`:

- **`accuracy_summary.txt`** — the same summary, broken down by
  season too, plus the 10 biggest confident misses (games the model
  was most surprised by).
- **`accuracy_by_game.csv`** — every game with its prediction and
  score, for digging in yourself (e.g. in Excel).

This is read-only and doesn't touch the database.

## Reading the database without a separate tool

```
python3 report.py
```

Writes three files into a `reports/` folder, always reflecting
whatever's currently in `wnba_elo.db`:

- **`summary.txt`** — plain-text standings by season, just open it.
- **`standings.csv`** — one row per team per season (rank, W/L, final
  Elo) — opens straight into Excel.
- **`game_log.csv`** — every game, both teams' perspectives, with
  pre/post rating and expected win % — also opens into Excel.

Run it any time; it's read-only and doesn't touch the database.

If you'd rather browse the raw tables directly, **DB Browser for
SQLite** (https://sqlitebrowser.org/) is a free GUI that opens
`wnba_elo.db` like a spreadsheet.

## Relocations and folded teams

Use `franchise.py` for both of these.

**Relocation (same franchise, new city/abbreviation - rating carries
over unchanged).** Say Utah Starzz becomes the San Antonio Silver
Stars and future files will use the code `SAS` instead of `UTA`:

```
python3 franchise.py relocate --alias SAS --team-id UTA --name "San Antonio Silver Stars"
```

From then on, `add_season.py` automatically translates any `SAS` code
in a new file back into the existing `UTA` team_id, so the rating
history continues seamlessly - no reset, no gap. If a team's code
*doesn't* change but its name does, skip the alias and just:

```
python3 franchise.py rename --team-id CHA --name "New Team Name"
```

**Fold + revival (a team folds, and the same code/brand comes back
later as what's functionally a new franchise - must NOT inherit the
old rating).** Right before loading the season it returns in:

```
python3 franchise.py revive --team-id MIA --season 2010 --name "Miami Sol"
```

This forces that team_id to start the given season at the base rating
(1500) exactly, ignoring whatever it ended on before folding, then
rebuilds. You only need this if the *same* team_id/code is reused —
folding itself needs no action (a team just stops appearing in future
files), and a genuinely new expansion team with a fresh code already
starts at 1500 automatically.

`python3 franchise.py status` lists every team, every relocation
alias, and every forced reset currently registered, so you can check
your work.

## Neutral-site seasons (e.g. the 2020 COVID "bubble")

If a source file's `HomeAway` column uses `'N'` instead of `'H'`/`'A'`
(no true home team - e.g. the entire 2020 season played at IMG
Academy), `add_season.py` handles it automatically: it picks one of
the two symmetric rows per game as the stored "home" team (arbitrary,
alphabetically first - it doesn't matter which, since neither side
gets an advantage) and flags the game `neutral=1`. The engine skips
home-court advantage entirely for any game flagged this way, while
still applying the normal rest-day adjustment. Nothing extra to do -
just run `add_season.py` as usual.

## Tuning the model's parameters

```
python3 set_params.py show                              # see what's active
python3 set_params.py set --hca 90 --alpha 0.55          # change one or more levers
python3 set_params.py set --po-round1 1.15 --po-half 1.05  # playoff multipliers
python3 set_params.py reset                              # back to the original values
```

Any change with `set` is **retroactive** — it recomputes the entire
history, every season, with the new values, and saves the tuning so it
stays in effect for future `add_season.py` runs too (until you `reset`
or `set` again).

**Your Excel backups will no longer match once you tune anything** —
they were computed with the original values, and that's expected, not
a bug. `verify_against_workbook.py` is built to keep working anyway:
it always recomputes ratings in-memory using the frozen original
parameters (never touching the live tuned `ratings` table), so it
stays a valid sanity check on the *engine's* correctness regardless of
whatever you've tuned. Levers available: `alpha`, `base`, `hca`,
`kmin`, `kmax`, and the playoff multipliers (`--po-round1` through
`--po-round4`, `--po-half` for round 0.5).

## Deleting a whole season

```
python3 delete_season.py --season 2012 --season 2013
```

Shows how much it's about to delete and asks for confirmation
(`--yes` skips the prompt, for scripting). Removes those seasons'
games and ratings, clears any forced fold/revival resets registered
for them, and rebuilds everything else. All other seasons, team names,
and relocation aliases are untouched.

For a single game instead of a whole season, use `fix_game.py delete`
(see below).

## Fixing a mistake

**A single wrong game (wrong score, wrong date, duplicate entry, etc.):**
use `fix_game.py` — no need to touch anything else.

```
# find the game_id
python3 fix_game.py find --date 1998-06-11 --team CHA

# correct it
python3 fix_game.py update --game-id 116 --home-pts 84 --away-pts 61

# or delete it outright
python3 fix_game.py delete --game-id 116
```

Any of these rebuilds the full ratings history automatically, so the
correction ripples forward correctly through every later game and
season.

**A full reset (wipe everything and reload from source files):**
delete the database file and re-run `add_season.py` on each season's
file, in chronological order:

```
rm wnba_elo.db
python3 add_season.py /path/to/1997_file.xlsx
python3 add_season.py /path/to/1998_file.xlsx
python3 add_season.py /path/to/1999_file.xlsx
python3 add_season.py /path/to/2000_file.xlsx
# ...and so on
```

`db.py`'s `connect()` recreates the schema automatically if the file
doesn't exist. This only makes sense if you keep your original season
files around somewhere — the database itself isn't the source of
truth, the files are.

## Adding a new season (the only thing you need to do going forward)

```
python3 add_season.py /path/to/your_results_file.xlsx
```

That's it — one command. It works with either shape of file you've
used so far (a raw results file with `Date/Team/Opp/PF/PA/OT` columns,
or a full Echo-Ratings workbook — it'll read the `RawData` sheet).

It will:
1. Auto-register any team ID it hasn't seen before, with a placeholder
   name equal to the ID (e.g. `"IND"`). Rename it afterward with:
   ```
   python3 -c "import db; c=db.connect('wnba_elo.db'); db.upsert_team(c,'IND','Indiana Fever'); c.commit()"
   ```
2. Insert the games. **Re-running it on the same file is always safe**
   — duplicates are detected and skipped, not double-counted.
3. Rebuild the entire ratings history from game one, so every prior
   season stays consistent (this is what correctly regresses each
   team's new-season rating toward the mean from where it actually
   ended up the year before).
4. Run a few sanity checks (no NaN ratings, no team missing from the
   standings it should appear in) and print the standings.

If something looks off, run `python3 test_engine.py && python3
test_db.py` — those catch the two real bugs found while building this
(see below) and will flag if either regresses.

### If you still have a computed Echo Ratings workbook for a season

`verify_against_workbook.py` still works exactly as before — useful
the first time you bring in a season if you happen to have both the
raw results and the Excel version:

```
python3 verify_against_workbook.py /path/to/WNBA_Echo_Ratings_YYYY.xlsx
```

### Bugs found (and fixed) during verification, for the record

1. **Rest days must reset every season.** A team's `DaysOff` for its
   first game of a season is measured from that season's own opening
   day, not from its last game of the previous season. Caught by
   diffing the 1998 workbook against the database.
2. **SQLite's `UNIQUE` constraint treats every `NULL` as distinct.**
   Regular-season games store `round = NULL`, so re-running a loader
   on the same file silently doubled every regular-season game (while
   correctly deduping playoff games, which have a real round number).
   Fixed with an index on `IFNULL(round, -1)` instead of a plain
   `UNIQUE(...)` constraint. Caught by re-running the loader on the
   2000 file and noticing win totals had doubled.

Both are covered by `test_db.py` / `test_engine.py` now, and every
season loaded so far (1997-2000) has been re-verified since the fixes.

## Querying rankings

```python
import db
from rebuild import standings

conn = db.connect("wnba_elo.db")
for team, name, wins, losses, rating in standings(conn, 1997):
    print(f"{name:22s} {wins:.0f}-{losses:.0f}  Elo {rating:.1f}")
```

Or query `ratings` directly for anything else (game logs, accuracy /
Brier score of the model's predictions, rest-day effects, etc.) — it
has every column the original `RawData` sheet had.

## Model parameters

Defined in `engine.py::DEFAULT_PARAMS`, taken directly from the
workbook's named ranges:

| param | value | meaning |
|---|---|---|
| `alpha` | 0.6 | weight on prior season's final rating when a new season starts (the rest reverts to `base`) |
| `base` | 1500 | league-average rating / expansion-team starting rating |
| `hca` | 84 | home-court advantage, in Elo points |
| `kmin` / `kmax` | 6 / 58 | K-factor floor/ceiling — early-season games move ratings more |
| `playoff_mult` | 1.1 / 1.2 / 1.35 / 1.5 (rounds 1-4), 0.5→1.05 | extra weight on playoff games |

**Rest days reset every season.** A team's `DaysOff` for its first
game of a season is measured from that season's own opening day, not
from its last game of the previous season. This was confirmed by
diffing against both the 1997 and 1998 workbooks (each season lives in
its own workbook with its own `RawData` table, so "days since last
game" only ever looks within the current season's table). Rating
carryover between seasons (the `alpha` blend) is unaffected by this -
only the rest-day/rest-adjustment inputs are season-scoped.

## Verifying against a workbook

If you have an Echo-Ratings-style workbook (with a computed `RawData`
sheet) for a season already in the database, you can diff it against
the database column-by-column at any time:

```
python3 verify_against_workbook.py /path/to/WNBA_Echo_Ratings_1998.xlsx
```

It reports the max absolute difference per column and, if anything is
off by more than 1e-6, prints the worst-offending rows. As of this
writing, 1997 (230 rows) and 1998 (316 rows) both match to
floating-point precision (~1e-13).

Run `python3 test_engine.py` after any change to `engine.py` - it has
a regression test for the season-boundary rest-day behavior above,
plus a check that season-to-season rating regression still works.

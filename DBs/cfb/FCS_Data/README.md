# FCS Schedule Pipeline

Reusable tooling for building the FCS (1-AA) college football schedule/results
database, season by season. Built from the 1996 season; designed so 1997+
season is "drop in the files, run ingest + reconcile" rather than a rebuild.

## Files
- `schema.py` — multi-season SQLite schema (one db, `season` column throughout).
  `init_db(path)` creates it; `migrate_legacy_1996_db()` is a one-time import
  of the original single-season fcs_1996.db.
- `reference.py` — season-independent lookups: `FCS_ALIASES` (name variants ->
  canonical names) and `FCS_HOME_CITY` (campus locations, for home/away/neutral
  resolution). Add to these as new seasons turn up new variants; they compound.
- `parsers.py` — `parse_wikipedia_schedule()` for the messy multi-team export
  format, `parse_recordbook_schedules()` for the Coach/PF/PA/Location/Notes
  record-book format. Screenshots still need manual transcription into a
  list-of-dicts, but everything downstream is shared.
- `reconcile.py` — the actual value-add. `stage_games()` inserts a new source
  into `staging_games` and auto-flags matches/conflicts against what's already
  verified. `cross_check_staged_sources()` catches disagreements between two
  not-yet-promoted sources. `record_reconciliation_report()` compares every
  team's reconstructed W-L against the reference TeamList file and flags
  mismatches - this is what caught Morehead State, Middle Tennessee, and
  (this run) 9 more teams whose extra games trace to playoff runs the
  TeamList reference apparently doesn't count. `promote_team()` moves clean
  staged rows into `games`. `completion_report()` gives the same "still needs
  filling" view as before, now parameterized by season.

## Workflow for a new season
1. `con = schema.init_db('fcs.db')` (or reuse the existing multi-season file)
2. `reference.seed_reference_tables(con)` — safe to re-run, it's idempotent
3. Load that season's TeamList into `teams` (season, team_name, conference, wins, losses, games_played)
4. For each source: parse it, then `reconcile.stage_games(con, season, source_name, team, games)`
5. `reconcile.cross_check_staged_sources(con, season)` — resolve any conflicts before promoting
6. `reconcile.promote_team(con, season, team)` per team once its staged data looks clean
7. `reconcile.completion_report(con, season)` — see what's left
8. `reconcile.record_reconciliation_report(con, season)` — sanity-check final records against TeamList,
   investigate mismatches (playoff games are the most common innocent cause)

## Known open items (1996)
- Charleston Southern, Connecticut, Fordham, Lafayette, Rhode Island, South
  Carolina State: each has 1 more parsed game than games_played suggested at
  the very start of the project - likely playoff-related, unconfirmed.
- Southern Utah: Montana Tech game dated Sep 28 in one source, Sep 29 in
  another - unresolved, doesn't affect the score.
- The 9 additional record mismatches found by this session's reconciliation
  sweep (Chattanooga, Hampton, Hofstra, Marshall, Morgan State, Northeastern,
  Rhode Island, plus the already-known Connecticut/Middle Tennessee) - Marshall
  confirmed as a playoff-run undercount; others unconfirmed but same pattern likely.

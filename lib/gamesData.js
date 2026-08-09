/**
 * gamesData.js — shared game-pairing/fetch helpers.
 *
 * Extracted out of app/[league]/GamesPanel.jsx (unchanged logic, just moved)
 * so the homepage's "Today's Games" strip can reuse the exact same
 * pairing/query code instead of a second hand-copied version that could
 * silently drift from GamesPanel's behavior over time.
 */

import { supabase } from "@/lib/supabase";

export function formatDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function roundLabel(round, type, leagueConfig) {
  if (type !== "P") return "Reg. Season";
  return leagueConfig.engine?.roundLabels?.[round] ?? round ?? "Playoffs";
}

export function pairGameRows(rows) {
  const seen = new Set();
  const games = [];
  for (const row of rows) {
    if (row.home_away !== "H" || !row.points_for || row.points_for < 50) continue;
    const key = `${row.date}_${row.team_id}_${row.opponent_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const away = rows.find(
      (g) => g.date === row.date && g.team_id === row.opponent_id && g.home_away === "A"
    );
    games.push({
      date: row.date,
      home: row.team_id,
      away: row.opponent_id,
      homeScore: row.points_for,
      awayScore: row.points_against,
      homeRating: row.post_gm_rate,
      awayRating: away?.post_gm_rate ?? null,
      homeChange: row.rating_change,
      awayChange: away?.rating_change ?? null,
      winProb: row.expected_win_pct,
      round: row.round,
      type: row.type,
      ot: row.ot || false,
      upcoming: false,
    });
  }
  return games;
}

export function pairScheduleRows(rows, nextGameByTeam) {
  const seen = new Set();
  const games = [];
  for (const row of rows) {
    if (row.home_away !== "H") continue;
    const key = `${row.date}_${row.team_id}_${row.opponent_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const isNextForHome = nextGameByTeam[row.team_id] === row.date;
    const isNextForAway = nextGameByTeam[row.opponent_id] === row.date;
    games.push({
      date: row.date,
      home: row.team_id,
      away: row.opponent_id,
      winProb: row.expected_win_pct,
      round: row.round,
      type: row.type,
      upcoming: true,
      showPick: isNextForHome && isNextForAway,
    });
  }
  return games;
}

export async function getGamesForDate(league, dateStr, season, variant) {
  const { data } = await supabase
    .from("games")
    .select(
      "team_id,post_gm_rate,rating_change,date,type,round,opponent_id,home_away,points_for,points_against,expected_win_pct,ot"
    )
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .eq("date", dateStr);
  return pairGameRows(data || []);
}

export async function getNextGameDateByTeam(league, season, variant) {
  const { data } = await supabase
    .from("schedule")
    .select("team_id, date")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant);
  const earliest = {};
  for (const row of data || []) {
    if (!earliest[row.team_id] || row.date < earliest[row.team_id]) {
      earliest[row.team_id] = row.date;
    }
  }
  return earliest;
}

export async function getScheduledGamesForDate(league, dateStr, season, variant) {
  const [{ data }, nextGameByTeam] = await Promise.all([
    supabase
      .from("schedule")
      .select("team_id,opponent_id,home_away,date,type,round,expected_win_pct")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .eq("date", dateStr),
    getNextGameDateByTeam(league, season, variant),
  ]);
  return pairScheduleRows(data || [], nextGameByTeam);
}

export async function getLatestGameDate(league, season, variant) {
  const { data } = await supabase
    .from("games")
    .select("date")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .eq("home_away", "H")
    .not("points_for", "is", null)
    .order("date", { ascending: false })
    .limit(1);
  return data?.[0]?.date ?? null;
}

// Games (played OR scheduled) for a specific calendar date - used by the
// homepage, which (unlike GamesPanel) wants "today" specifically, not
// "whatever the latest available date is." Returns [] if there's nothing
// on that date either way, which is the homepage's cue to skip that
// league's section entirely rather than showing something stale.
export async function getGamesOrScheduleForDate(league, dateStr, season, variant) {
  const played = await getGamesForDate(league, dateStr, season, variant);
  if (played.length > 0) return played;
  return getScheduledGamesForDate(league, dateStr, season, variant);
}

// ---------------------------------------------------------------------------
// Season-level helpers — shared by the live Dashboard (app/[league]/page.js)
// and the historical Season Page (app/[league]/season/page.js). Both need
// "aggregate this league's games for season X, variant Y" - same shape,
// just a different X - so this is one function, not two copies.
// ---------------------------------------------------------------------------

// Every season that actually has data for a league, newest first. Reads
// preseason_ratings rather than games directly - it's one row per team per
// season (not one row per team per game), so pulling the full table to
// dedupe season values client-side stays cheap even after 30+ seasons of
// history, where doing the same thing against `games` would not.
export async function getAvailableSeasons(league) {
  // Season ranges don't differ between Echo/Pulse - both variants are
  // written for every game a season has - so this intentionally always
  // reads the 'echo' variant rather than depending on whichever variant
  // the page happens to be showing right now.
  const { data, error } = await supabase
    .from("preseason_ratings")
    .select("season")
    .eq("league", league)
    .eq("variant", "echo");

  if (error || !data) return { seasons: [], error };

  const seasons = [...new Set(data.map((r) => r.season))].sort((a, b) => b - a);
  return { seasons, error: null };
}

// The most recent season with real data for a league. Deliberately NOT a
// hardcoded constant anywhere in the app - a hardcoded "current season"
// silently goes stale the moment a new season starts and nobody remembers
// to bump it. This just asks the data what the latest season actually is.
export async function getCurrentSeason(league) {
  const { seasons, error } = await getAvailableSeasons(league);
  if (error || seasons.length === 0) return { season: null, error };
  return { season: seasons[0], error: null };
}

// Per-team season standings: RS + combined W/L, latest rating, and rating
// change - for an arbitrary season (unlike the Dashboard's use of this same
// shape, which only ever asks for the current one). Paginated the same way
// as every other full-season query in this file, since Supabase/PostgREST
// caps a single request's rows regardless of how big the actual result is.
export async function fetchSeasonStandings(league, season, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, date, post_gm_rate, rating_change, w, l")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { standings: [], error };

    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  const byTeam = {};
  for (const row of allRows) {
    const t = (byTeam[row.team_id] ??= { team_id: row.team_id, w: 0, l: 0, rating: null, change: null });
    t.w += row.w ?? 0;
    t.l += row.l ?? 0;
    t.rating = row.post_gm_rate; // rows are date-ascending, so the last one seen is latest
    t.change = row.rating_change;
  }

  const standings = Object.values(byTeam).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  return { standings, error: null };
}

// Every game row (both types) for a team across a season, used by Season
// Page to derive regular-season-only record/rating, the true season-end
// rating (which includes playoff games, when a team made the playoffs),
// AND the season's model-accuracy summary — all from one query, rather
// than fetching the same season's rows three separate times.
export async function fetchSeasonTeamGames(league, season, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, date, type, post_gm_rate, rating_change, w, l, home_away, accuracy, brier")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { rows: [], error };
    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { rows: allRows, error: null };
}

// Each team's preseason rating for a season/variant. Small table (one row
// per team), so a single unpaged query is fine. Pulse resets every team to
// the same baseline each season, so this is only meaningful for Echo —
// callers should skip rendering it for Pulse rather than show a column of
// identical numbers.
export async function fetchPreseasonRatings(league, season, variant) {
  const { data, error } = await supabase
    .from("preseason_ratings")
    .select("team_id, preseason_elo")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant);

  if (error) return { byTeam: {}, error };
  const byTeam = {};
  for (const row of data ?? []) byTeam[row.team_id] = row.preseason_elo;
  return { byTeam, error: null };
}

// League-wide model accuracy for a season, straight off games.accuracy/
// .brier (populated per game row by the rating engine) - no separate
// season_accuracy table needed, that ContinElo-era table was never carried
// into the new schema. Counts each real-world game once (home_away='H'
// rows only), same de-dup convention as pairGameRows above.
export function buildSeasonAccuracy(rows) {
  const homeRows = rows.filter((r) => r.home_away === "H" && r.accuracy != null);
  if (homeRows.length === 0) return null;
  const avgAccuracy = homeRows.reduce((sum, r) => sum + r.accuracy, 0) / homeRows.length;
  const brierRows = homeRows.filter((r) => r.brier != null);
  const avgBrier = brierRows.length
    ? brierRows.reduce((sum, r) => sum + r.brier, 0) / brierRows.length
    : null;
  return {
    n: homeRows.length,
    pct: (avgAccuracy * 100).toFixed(1),
    brier: avgBrier != null ? avgBrier.toFixed(3) : null,
  };
}

// Reduces fetchSeasonTeamGames' raw rows into one row per team: RS-only
// record + RS-end rating, plus the true final rating for the season (the
// last game either way — so it reflects playoff games too, for teams that
// made it that far).
export function buildSeasonStandingsRows(rows) {
  const byTeam = {};
  for (const row of rows) {
    const t = (byTeam[row.team_id] ??= {
      team_id: row.team_id,
      rsW: 0,
      rsL: 0,
      rsRating: null,
      finalRating: null,
      finalChange: null,
    });
    if (row.type === "R") {
      t.rsW += row.w ?? 0;
      t.rsL += row.l ?? 0;
      t.rsRating = row.post_gm_rate; // rows are date-ascending — last 'R' row seen is RS-end rating
    }
    t.finalRating = row.post_gm_rate; // last row overall, regardless of type
    t.finalChange = row.rating_change;
  }
  return Object.values(byTeam);
}

// Raw playoff game rows (type='P', excluding round=0.1 in-season-tournament
// games) for an arbitrary season - same query BracketTab's data needs for
// the current season, just not locked to it.
export async function fetchSeasonPlayoffGames(league, season, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, round, result, opponent_id, home_away, date")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .eq("type", "P")
      .neq("round", "0.1")
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { poGames: [], error };
    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { poGames: allRows, error: null };
}

// Rolls up raw playoff game rows into a per-team { round: {w, l} } tally,
// plus which round (if any) each team was CROWNED in - i.e. actually won
// the series in, not just appeared in. "Won the series" is read off
// leagueConfig.playoffFormat.winsNeeded when the league defines it (WNBA
// does, per round); leagues that don't (NBA - every round is best-of-7)
// fall back to 4 wins, which is every best-of-7 series in NBA history.
// keyFn defaults to grouping by team_id (Season Page's use — one season's
// worth of playoff rows at a time, so team_id alone is a unique key). The
// All-Time/Team pages pass rows spanning every season at once, so they key
// by `${team_id}-${season}` instead — same tally logic either way.
export function tallyPlayoffResults(poGames, leagueConfig, keyFn = (row) => row.team_id) {
  const winsNeeded = leagueConfig.playoffFormat?.winsNeeded ?? {};
  const roundLabels = leagueConfig.engine?.roundLabels ?? {};
  const roundNumbers = Object.keys(roundLabels)
    .map(Number)
    .filter((n) => !Number.isNaN(n) && n >= 1); // excludes 'RS' and Play-In's 0.5

  const highestRound = roundNumbers.length ? Math.max(...roundNumbers) : null;

  const byKey = {};
  for (const row of poGames) {
    const key = keyFn(row);
    const t = (byKey[key] ??= { rounds: {}, champion: false, highestRound: null });
    const rnd = row.round;
    const r = (t.rounds[rnd] ??= { w: 0, l: 0 });
    if (row.result === 1) r.w += 1;
    else r.l += 1;

    const rndNum = Number(rnd);
    if (!Number.isNaN(rndNum) && (t.highestRound === null || rndNum > t.highestRound)) {
      t.highestRound = rndNum;
    }
  }

  for (const t of Object.values(byKey)) {
    if (t.highestRound === highestRound && highestRound !== null) {
      const needed = winsNeeded[highestRound] ?? 4;
      const w = t.rounds[String(highestRound)]?.w ?? 0;
      if (w >= needed) t.champion = true;
    }
  }

  return byKey;
}

// ---------------------------------------------------------------------------
// All-time helpers — season-optional versions of the season-level helpers
// above (season=omitted fetches every season a league has), used by the
// All-Time Rankings and Team pages. Season Page keeps using the originals
// above unchanged; these are separate functions rather than an
// `season = null` branch on the existing ones, since the row shape differs
// (grouped by team+season, not just team) and callers need both at once
// in some cases (Team page shows one team's all-time row AND uses the
// same season-scoped fetch for its own dashboard-style current view).
// ---------------------------------------------------------------------------

// Every RS+PO game row for every team across every season a league has.
// Same pagination pattern as the season-scoped fetches, just without the
// `.eq("season", ...)` filter — this is the single most expensive query
// on the site (150k+ rows for a league with 30 seasons of NBA history),
// so All-Time/Team pages should call this once and derive everything else
// client-side rather than re-querying per team or per season.
export async function fetchAllTimeTeamGames(league, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, season, date, type, post_gm_rate, rating_change, w, l")
      .eq("league", league)
      .eq("variant", variant)
      .order("season", { ascending: true })
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { rows: [], error };
    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { rows: allRows, error: null };
}

// Preseason rating for every team, every season. Pulse resets to base
// every year (so this is Echo-only, same caveat as fetchPreseasonRatings)
// but still one row per team per season, so still paginated.
export async function fetchAllTimePreseasonRatings(league, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("preseason_ratings")
      .select("team_id, season, preseason_elo")
      .eq("league", league)
      .eq("variant", variant)
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { byTeamSeason: {}, error };
    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  const byTeamSeason = {};
  for (const row of allRows) byTeamSeason[`${row.team_id}-${row.season}`] = row.preseason_elo;
  return { byTeamSeason, error: null };
}

// Every playoff game row (type='P', excluding in-season-tournament) for
// every team across every season.
export async function fetchAllTimePlayoffGames(league, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, season, round, result, opponent_id, home_away, date")
      .eq("league", league)
      .eq("variant", variant)
      .eq("type", "P")
      .neq("round", "0.1")
      .order("season", { ascending: true })
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { poGames: [], error };
    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { poGames: allRows, error: null };
}

// Reduces fetchAllTimeTeamGames' raw rows into one row per team-SEASON
// (not one row per team, like buildSeasonStandingsRows) — the All-Time
// page's grain is "how did this team do in this specific season."
export function buildAllTimeRows(rows) {
  const byTeamSeason = {};
  for (const row of rows) {
    const key = `${row.team_id}-${row.season}`;
    const t = (byTeamSeason[key] ??= {
      team_id: row.team_id,
      season: row.season,
      rsW: 0,
      rsL: 0,
      rsRating: null,
      finalRating: null,
    });
    if (row.type === "R") {
      t.rsW += row.w ?? 0;
      t.rsL += row.l ?? 0;
      t.rsRating = row.post_gm_rate;
    }
    t.finalRating = row.post_gm_rate;
  }
  return Object.values(byTeamSeason);
}

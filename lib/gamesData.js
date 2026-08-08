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

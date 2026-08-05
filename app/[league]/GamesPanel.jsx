"use client";

/**
 * GamesPanel — date-navigable box scores, ported from the old Dashboard's
 * "Games" sidebar. Pairs the two per-team rows for each game (home + away
 * perspective) into a single game object, same logic as the old site's
 * pairGameRows/getGamesForDate/getLatestGameDate.
 */

import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import TeamMark from "./TeamMark";
import SeasonProjection from "./SeasonProjection";

function shiftDate(dateStr, delta) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + delta);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

function formatDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function roundLabel(round, type, leagueConfig) {
  if (type !== "P") return "Reg. Season";
  return leagueConfig.engine?.roundLabels?.[round] ?? round ?? "Playoffs";
}

function pairGameRows(rows) {
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

// Unplayed games from `schedule` - no score/rating-change columns exist
// yet for these, unlike `games` where they're always populated. Mirrors
// pairGameRows' per-team-row pairing, minus the fields that don't apply.
//
// `nextGameByTeam` is {team_id: earliest still-upcoming date} across the
// whole season (see getNextGameDateByTeam below) - a game only gets
// showPick=true when it's the IMMEDIATE next unplayed game for BOTH
// teams involved (ESPN-style: a scheduled game 3 games out for a team
// doesn't get a prediction shown yet, even though the engine could
// technically compute one). The game itself still always renders either
// way - this only controls whether the pick badge shows.
function pairScheduleRows(rows, nextGameByTeam) {
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

async function getGamesForDate(league, dateStr, season, variant) {
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

// Earliest still-upcoming (unplayed) date per team, across the whole
// season. `schedule` only ever contains unplayed games (played games
// get pruned locally and the table gets fully replaced on export - see
// export_to_supabase.py's build_schedule() docstring), so the earliest
// row for a given team_id IS that team's next game, full stop. Used to
// gate the prediction badge in pairScheduleRows above.
async function getNextGameDateByTeam(league, season, variant) {
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

// Fallback for a date with no played games yet - checks `schedule` for
// upcoming (unplayed) games instead, so a future date shows the matchup
// (and, when eligible, Elo's pick) rather than just "No games on this
// date".
async function getScheduledGamesForDate(league, dateStr, season, variant) {
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

async function getLatestGameDate(league, season, variant) {
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

export default function GamesPanel({ league, season, variant, leagueConfig }) {
  const [latestDate, setLatestDate] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getLatestGameDate(league, season, variant).then((date) => {
      if (cancelled) return;
      setLatestDate(date);
      setSelectedDate(date);
    });
    return () => {
      cancelled = true;
    };
  }, [league, season, variant]);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setLoading(true);
    getGamesForDate(league, selectedDate, season, variant).then((rows) => {
      if (cancelled) return;
      if (rows.length > 0) {
        setGames(rows);
        setLoading(false);
        return;
      }
      // No played games this date yet - see if any are on the schedule.
      getScheduledGamesForDate(league, selectedDate, season, variant).then((upcoming) => {
        if (cancelled) return;
        setGames(upcoming);
        setLoading(false);
      });
    });
    return () => {
      cancelled = true;
    };
  }, [league, selectedDate, season, variant]);

  return (
    <div className="right-col">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, gap: 8 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>Games</div>
        {latestDate && selectedDate !== latestDate && (
          <button
            onClick={() => setSelectedDate(latestDate)}
            style={{
              fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--acc)",
              background: "none", border: "1px solid rgba(102,51,153,0.25)",
              borderRadius: 5, padding: "3px 8px", cursor: "pointer",
            }}
          >
            Jump to latest
          </button>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14 }}>
        <button
          onClick={() => selectedDate && setSelectedDate(shiftDate(selectedDate, -1))}
          style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text2)", background: "#fff", border: "1px solid var(--border2)", borderRadius: 6, padding: "4px 9px", cursor: "pointer" }}
        >
          ‹
        </button>
        <input
          type="date"
          value={selectedDate || ""}
          onChange={(e) => setSelectedDate(e.target.value)}
          style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)", background: "#fff", border: "1px solid var(--border2)", borderRadius: 6, padding: "4px 8px", flex: 1 }}
        />
        <button
          onClick={() => selectedDate && setSelectedDate(shiftDate(selectedDate, 1))}
          style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text2)", background: "#fff", border: "1px solid var(--border2)", borderRadius: 6, padding: "4px 9px", cursor: "pointer" }}
        >
          ›
        </button>
      </div>

      {loading ? (
        <div style={{ color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13, padding: "1.5rem 0", textAlign: "center" }}>
          Loading…
        </div>
      ) : games.length === 0 ? (
        <div style={{ color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 12, padding: "1.5rem 0", textAlign: "center", border: "1px dashed var(--border2)", borderRadius: 10 }}>
          No games on {selectedDate ? formatDate(selectedDate) : "this date"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {games.map((g, i) => {
            if (g.upcoming) {
              const homeTeam = leagueConfig.teams[g.home];
              const awayTeam = leagueConfig.teams[g.away];
              const homeFav = g.winProb != null && g.winProb >= 0.5;
              const favPct = g.winProb != null ? Math.round(homeFav ? g.winProb * 100 : (1 - g.winProb) * 100) : null;
              return (
                <div key={i} style={{ background: "var(--surface)", border: "1px dashed var(--border2)", borderRadius: 10, padding: "10px 12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>
                    <span>{formatDate(g.date)}</span>
                    <span style={{ fontWeight: 700, letterSpacing: 0.5 }}>UPCOMING</span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", padding: "12px 0 8px" }}>
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.away}</span>
                    </div>

                    {awayTeam && <TeamMark team={awayTeam} teamId={g.away} league={league} size={34} />}

                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, padding: "0 8px", flexShrink: 0, minWidth: 44 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>@</span>
                    </div>

                    {homeTeam && <TeamMark team={homeTeam} teamId={g.home} league={league} size={34} />}

                    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.home}</span>
                    </div>
                  </div>

                  {g.showPick && favPct != null && (
                    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 4, borderTop: "1px solid var(--border)", marginTop: 2, paddingTop: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)" }}>
                      <span>Elo&apos;s pick:</span>
                      {!homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>◀</span>}
                      <strong>{homeFav ? g.home : g.away} {favPct}%</strong>
                      {homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>▶</span>}
                    </div>
                  )}
                </div>
              );
            }

            const homeWon = g.homeScore > g.awayScore;
            const isPlayoff = g.type === "P";
            const homeTeam = leagueConfig.teams[g.home];
            const awayTeam = leagueConfig.teams[g.away];
            const homeFav = g.winProb != null && g.winProb >= 0.5;
            const favPct = g.winProb != null ? Math.round(homeFav ? g.winProb * 100 : (1 - g.winProb) * 100) : null;
            return (
              <div key={i} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>
                  <span>{formatDate(g.date)}</span>
                  <span style={{ color: isPlayoff ? "var(--ut)" : "var(--text3)", fontWeight: isPlayoff ? 700 : 400 }}>
                    {roundLabel(g.round, g.type, leagueConfig)}
                  </span>
                </div>

                <div style={{ display: "flex", alignItems: "center", padding: "12px 0 8px" }}>
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.away}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 30, fontWeight: 900, lineHeight: 1, color: homeWon ? "var(--text)" : "#D4AF37" }}>
                      {g.awayScore}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>{g.awayRating?.toFixed(1)}</span>
                  </div>

                  {awayTeam && <TeamMark team={awayTeam} teamId={g.away} league={league} size={34} />}

                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, padding: "0 8px", flexShrink: 0, minWidth: 44 }}>
                    {g.ot && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, padding: "2px 5px", borderRadius: 3, background: "rgba(191,87,0,0.15)", color: "var(--ut)", border: "1px solid rgba(191,87,0,0.25)" }}>
                        OT
                      </span>
                    )}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>@</span>
                  </div>

                  {homeTeam && <TeamMark team={homeTeam} teamId={g.home} league={league} size={34} />}

                  <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.home}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 30, fontWeight: 900, lineHeight: 1, color: homeWon ? "#D4AF37" : "var(--text)" }}>
                      {g.homeScore}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>{g.homeRating?.toFixed(1)}</span>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border)", marginTop: 2, paddingTop: 8, fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  <span>
                    {g.away}{" "}
                    <strong style={{ color: g.awayChange > 0 ? "#1a7a34" : "#b91c1c" }}>
                      {g.awayChange > 0 ? "+" : ""}{g.awayChange?.toFixed(1)}
                    </strong>
                  </span>
                  {favPct != null && (
                    <span style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text2)" }}>
                      {!homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>◀</span>}
                      <strong>{favPct}%</strong>
                      {homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>▶</span>}
                    </span>
                  )}
                  <span>
                    {g.home}{" "}
                    <strong style={{ color: g.homeChange > 0 ? "#1a7a34" : "#b91c1c" }}>
                      {g.homeChange > 0 ? "+" : ""}{g.homeChange?.toFixed(1)}
                    </strong>
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <SeasonProjection league={league} season={season} variant={variant} leagueConfig={leagueConfig} />
    </div>
  );
}

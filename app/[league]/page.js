"use client";

/**
 * app/[league]/page.js — Real Dashboard, league-agnostic, LIVE Supabase data.
 *
 * Matches the old single-league Dashboard.jsx layout: two-column grid
 * (ratings table left, Games panel right), Echo/Pulse variant read from the
 * ?variant= search param (toggle lives in Nav.jsx, shared across the site).
 *
 * Fetches every game row for the current season/variant, then reduces
 * client-side to: latest row per team (for current rating + last change)
 * and summed w/l across all rows (season record) — w/l in the games table
 * are per-game results (1/0), not running totals, so they must be summed,
 * not read off the latest row.
 *
 * Playoff Bracket tab: live for conference-bracket leagues (NBA) via
 * BracketTab.jsx. Overall-bracket leagues (WNBA: top-8, no conferences)
 * still show a placeholder — that format needs its own component, not a
 * variant of BracketTab, since the whole layout assumes two conferences
 * funneling into a Finals column.
 */

import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import { supabase } from "@/lib/supabase";
import TeamMark from "./TeamMark";
import StandingsTab from "./StandingsTab";
import GamesPanel from "./GamesPanel";
import BracketTab from "./BracketTab";
import OverallBracketTab from "./OverallBracketTab";

const TABS = [
  { id: "rankings", label: "Power Rankings" },
  { id: "standings", label: "Standings" },
  { id: "bracket", label: "Playoff Bracket" },
];

const CURRENT_SEASON = 2026;

const VARIANT_LABELS = {
  echo: "Echo ratings — carry-forward variant",
  pulse: "Pulse ratings — season-reset variant",
};

async function fetchStandings(league, season, variant) {
  const PAGE_SIZE = 1000; // matches Supabase/PostgREST's typical default Max Rows;
                           // safe even if the project's cap is raised later, since
                           // we stop as soon as a page comes back short.
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

    // A short page means we've hit the end of the result set.
    if (!data || data.length < PAGE_SIZE) break;

    from += PAGE_SIZE;
  }

  const byTeam = {};
  for (const row of allRows) {
    const t = (byTeam[row.team_id] ??= { team_id: row.team_id, w: 0, l: 0, rating: null, change: null });
    t.w += row.w ?? 0;
    t.l += row.l ?? 0;
    // rows are date-ascending, so the last one we see is the latest
    t.rating = row.post_gm_rate;
    t.change = row.rating_change;
  }

  const standings = Object.values(byTeam).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  return { standings, error: null };
}

async function fetchPlayoffGames(league, season, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, round, result, post_gm_rate, opponent_id, home_away, points_for, points_against, date, game_id")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .eq("type", "P")
      .neq("round", "0.1") // excludes in-season tournament games (round=0.1); games.round is TEXT in Postgres, so compare as a string, not a number
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { poGames: [], error };

    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { poGames: allRows, error: null };
}

async function fetchProjection(league, season, variant) {
  const { data, error } = await supabase
    .from("season_projections")
    .select("team_id, avg_wins, p10_wins, p90_wins, prob_finish_first, remaining_games")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant);

  if (error) return { projByTeam: {}, error };

  const projByTeam = {};
  for (const row of data ?? []) {
    projByTeam[row.team_id] = row;
  }
  return { projByTeam, error: null };
}

export default function LeaguePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const league = params.league;
  const variant = searchParams.get("variant") || "echo";
  const [activeTab, setActiveTab] = useState("rankings");
  const [standings, setStandings] = useState([]);
  const [projByTeam, setProjByTeam] = useState({});
  const [poGames, setPoGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  // No season_projections rows exist once a season's finished (simulate_season
  // has nothing left to project over remaining games) - this is empty for a
  // completed NBA season and populated for an in-progress WNBA season right
  // now, and flips back automatically once a new season's projections start
  // getting written, no manual toggle needed.
  const hasProjections = Object.keys(projByTeam).length > 0;

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  useEffect(() => {
    if (!leagueConfig) return;
    setLoading(true);
    Promise.all([
      fetchStandings(league, CURRENT_SEASON, variant),
      fetchProjection(league, CURRENT_SEASON, variant),
      // Only conference-bracket leagues (NBA) need actual playoff game rows
      // right now — OverallBracketTab (WNBA) projects off standings alone.
      leagueConfig.playoffFormat?.type === "conference-bracket"
        ? fetchPlayoffGames(league, CURRENT_SEASON, variant)
        : Promise.resolve({ poGames: [], error: null }),
    ]).then(([standingsResult, projResult, poResult]) => {
      setStandings(standingsResult.standings);
      setFetchError(standingsResult.error);
      setProjByTeam(projResult.projByTeam); // projection errors are non-fatal - table still renders, projection columns just show "—"
      setPoGames(poResult.poGames); // playoff-fetch errors are non-fatal - bracket tab just renders empty/TBD
      setLoading(false);
    });
  }, [league, leagueConfig, variant]);

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)", color: "var(--text3)", fontSize: 13 }}>
        Loading…
      </div>
    );
  }

  if (fetchError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)", color: "#b91c1c", fontSize: 13 }}>
        Couldn&apos;t load ratings: {fetchError.message}
      </div>
    );
  }

  if (standings.length === 0) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)", color: "var(--text3)", fontSize: 13 }}>
        No data yet for {leagueConfig.label} season {CURRENT_SEASON}.
      </div>
    );
  }

  const minRating = Math.min(...standings.map((r) => r.rating ?? 0));
  const maxRating = Math.max(...standings.map((r) => r.rating ?? 0));

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">
            {leagueConfig.seasonLabel(CURRENT_SEASON)} Season
          </div>
          <div className="hero-heading">Dashboard</div>
          <div className="hero-sub">
            {VARIANT_LABELS[variant]} · Updated after every game
          </div>
        </div>
      </div>

      <div
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          maxWidth: 1280,
          margin: "0 auto",
          padding: "0 2rem",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              fontSize: 13,
              fontFamily: "var(--font-mono)",
              padding: "12px 20px",
              cursor: "pointer",
              background: "none",
              border: "none",
              marginBottom: -1,
              borderBottom:
                activeTab === tab.id
                  ? "2px solid var(--acc)"
                  : "2px solid transparent",
              color: activeTab === tab.id ? "var(--acc)" : "var(--text3)",
              fontWeight: activeTab === tab.id ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "rankings" && (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
        <div className="main-grid">
          <div className="left-col">
            <div className="section-label">Current Ratings</div>
            <table className="ratings-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Team</th>
                  <th className="r">Rating</th>
                  <th className="r" style={{ width: 90 }}>Strength</th>
                  <th className="r">Δ Last</th>
                  <th className="r">Record</th>
                  {hasProjections && (
                    <>
                      <th className="r">Proj. W</th>
                      <th className="r">10th–90th</th>
                      <th className="r">P(1st)</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {standings.map((row, i) => {
                  const team = leagueConfig.teams[row.team_id];
                  if (!team) return null; // defensive: skip any team_id not in this league's config
                  const barPct = maxRating > minRating ? ((row.rating - minRating) / (maxRating - minRating)) * 100 : 50;
                  const chgPos = (row.change ?? 0) > 0;
                  // some primaries are pure black (e.g. Nets) — fall back to tertiary so the bar/border isn't invisible
                  const fillColor = team.primary === "#000000" ? team.tertiary : team.primary;
                  const proj = projByTeam[row.team_id];
                  return (
                    <tr
                      key={row.team_id}
                      style={{
                        borderLeft: `4px solid ${fillColor}`,
                        background: `linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`,
                      }}
                    >
                      <td style={{ textAlign: "right", padding: "0 10px 0 6px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "#fff", width: 36 }}>
                        {i + 1}
                      </td>
                      <td style={{ padding: "10px 8px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <TeamMark team={team} teamId={row.team_id} league={league} />
                          <span style={{ fontSize: 13, fontWeight: 700, color: team.secondary }}>{team.name}</span>
                        </div>
                      </td>
                      <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
                        {row.rating?.toFixed(1) ?? "—"}
                      </td>
                      <td style={{ padding: "0 8px", width: 130 }}>
                        <div style={{ height: 4, background: "rgba(0,0,0,0.12)", borderRadius: 2 }}>
                          <div style={{ width: `${barPct}%`, height: 4, borderRadius: 2, background: fillColor }} />
                        </div>
                      </td>
                      <td style={{ textAlign: "right", padding: "0 12px" }}>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 12,
                            fontWeight: 700,
                            padding: "2px 8px",
                            borderRadius: 4,
                            color: chgPos ? "#1a7a34" : "#b91c1c",
                            background: chgPos ? "rgba(26,122,52,0.12)" : "rgba(185,28,28,0.10)",
                          }}
                        >
                          {chgPos ? "+" : ""}
                          {row.change?.toFixed(1) ?? "—"}
                        </span>
                      </td>
                      <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>
                        {row.w}–{row.l}
                      </td>
                      {hasProjections && (
                        <>
                          <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>
                            {proj?.avg_wins?.toFixed(1) ?? "—"}
                          </td>
                          <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)" }}>
                            {proj ? `${proj.p10_wins}–${proj.p90_wins}` : "—"}
                          </td>
                          <td
                            style={{
                              textAlign: "right",
                              padding: "0 16px",
                              fontFamily: "var(--font-mono)",
                              fontSize: 12,
                              fontWeight: proj?.prob_finish_first >= 0.05 ? 700 : 400,
                              color: proj?.prob_finish_first >= 0.05 ? "var(--acc)" : "var(--text2)",
                            }}
                          >
                            {proj ? `${(proj.prob_finish_first * 100).toFixed(proj.prob_finish_first < 0.01 ? 1 : 0)}%` : "—"}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <GamesPanel league={league} season={CURRENT_SEASON} variant={variant} leagueConfig={leagueConfig} />
        </div>
        </div>
      )}

      {activeTab === "standings" && (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
          <StandingsTab leagueConfig={leagueConfig} standings={standings} />
        </div>
      )}

      {activeTab === "bracket" && (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
          {leagueConfig.playoffFormat?.type === "conference-bracket" ? (
            <div style={{ overflowX: "auto" }}>
              <BracketTab poGames={poGames} standings={standings} leagueConfig={leagueConfig} season={CURRENT_SEASON} />
            </div>
          ) : leagueConfig.playoffFormat?.type === "overall-bracket" ? (
            <div style={{ overflowX: "auto" }}>
              <OverallBracketTab standings={standings} leagueConfig={leagueConfig} season={CURRENT_SEASON} />
            </div>
          ) : (
            <div style={{ padding: "2.5rem 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
              Playoff Bracket — coming soon
            </div>
          )}
        </div>
      )}
    </div>
  );
}

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
 * Playoff Bracket tab is still a placeholder — each league's bracket format
 * differs enough (NBA: conference bracket + play-in; WNBA: top-8 overall)
 * that it's its own task.
 */

import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import { supabase } from "@/lib/supabase";
import TeamMark from "./TeamMark";
import StandingsTab from "./StandingsTab";
import GamesPanel from "./GamesPanel";

const TABS = [
  { id: "rankings", label: "Power Rankings" },
  { id: "standings", label: "Standings" },
  { id: "bracket", label: "Playoff Bracket" },
];

const CURRENT_SEASON = 2026;

const VARIANT_LABELS = {
  continelo: "Echo ratings — carry-forward variant",
  elo: "Pulse ratings — season-reset variant",
};

async function fetchStandings(league, season, variant) {
  const { data, error } = await supabase
    .from("games")
    .select("team_id, date, post_gm_rate, rating_change, w, l")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .order("date", { ascending: true })
    // Supabase caps results at 1000 rows by default — a full season across
    // every team (e.g. ~2,460 rows for 30 NBA teams x 82 games) silently
    // gets truncated without this. 20000 comfortably covers any league's
    // full season with room to grow.
    .range(0, 19999);

  if (error) return { standings: [], error };

  const byTeam = {};
  for (const row of data ?? []) {
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

export default function LeaguePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const league = params.league;
  const variant = searchParams.get("variant") || "continelo";
  const [activeTab, setActiveTab] = useState("rankings");
  const [standings, setStandings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

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
    fetchStandings(league, CURRENT_SEASON, variant).then(({ standings, error }) => {
      setStandings(standings);
      setFetchError(error);
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
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "4rem 2rem", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
          Playoff Bracket — coming soon
        </div>
      )}
    </div>
  );
}

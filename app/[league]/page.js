"use client";

/**
 * app/[league]/page.js — Real Dashboard, league-agnostic.
 *
 * Currently rendering MOCK data (see generateMockRatings below), not live
 * Supabase queries — the real per-league databases aren't ready yet. Once
 * they are, swap generateMockRatings() for a real Supabase query using the
 * same shape (team_id, rating, change, w, l) and nothing else here needs to
 * change.
 *
 * Standings and Playoff Bracket tabs are placeholders on purpose — each
 * league's playoff format differs enough (NBA: conference bracket + play-in;
 * WNBA: top-8 overall, no play-in) that building those properly is its own
 * task, not something to rush alongside this first pass.
 */

import { useState, useMemo } from "react";
import { useParams } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";

const TABS = [
  { id: "rankings", label: "Power Rankings" },
  { id: "standings", label: "Standings" },
  { id: "bracket", label: "Playoff Bracket" },
];

// Deterministic pseudo-random from a string, so mock data doesn't jump
// around on every re-render/hot-reload.
function seededRandom(seed) {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h << 5) - h + seed.charCodeAt(i);
    h |= 0;
  }
  return () => {
    h = (h * 1103515245 + 12345) & 0x7fffffff;
    return h / 0x7fffffff;
  };
}

function generateMockRatings(leagueConfig) {
  const teamIds = Object.keys(leagueConfig.teams);
  return teamIds
    .map((id) => {
      const rand = seededRandom(id);
      const rating = 1400 + rand() * 250;
      const change = (rand() - 0.5) * 30;
      const w = Math.floor(rand() * 40);
      const l = Math.floor(rand() * 30);
      return { team_id: id, rating, change, w, l };
    })
    .sort((a, b) => b.rating - a.rating);
}

function TeamMark({ team, size = 28 }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: team.primary,
        color: team.secondary === "#FFFFFF" || team.secondary === "#fff" ? team.secondary : "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--font-mono)",
        fontSize: size * 0.36,
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {team.nickname ? team.nickname.slice(0, 2).toUpperCase() : "??"}
    </div>
  );
}

export default function LeaguePage() {
  const params = useParams();
  const league = params.league;
  const [activeTab, setActiveTab] = useState("rankings");

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  const ratings = useMemo(
    () => (leagueConfig ? generateMockRatings(leagueConfig) : []),
    [leagueConfig]
  );

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  const minRating = Math.min(...ratings.map((r) => r.rating));
  const maxRating = Math.max(...ratings.map((r) => r.rating));

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">{leagueConfig.fullName}</div>
          <div className="hero-heading">
            {leagueConfig.seasonLabel(2026)} Season
          </div>
          <div className="hero-sub">
            Echo ratings — carry-forward variant · Placeholder data, not live yet
          </div>
        </div>
        <div className="hero-stats">
          <div className="hero-stat">
            <div className="hero-stat-val">{ratings.length}</div>
            <div className="hero-stat-lbl">Teams</div>
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

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
        {activeTab === "rankings" && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ fontSize: 11, color: "var(--text3)", textTransform: "uppercase", letterSpacing: 1 }}>
                <th style={{ textAlign: "right", padding: "0 10px 8px 6px", width: 36 }}>#</th>
                <th style={{ textAlign: "left", padding: "0 8px 8px" }}>Team</th>
                <th style={{ textAlign: "right", padding: "0 16px 8px" }}>Rating</th>
                <th style={{ textAlign: "right", padding: "0 8px 8px", width: 130 }}>Strength</th>
                <th style={{ textAlign: "right", padding: "0 12px 8px" }}>Δ Last</th>
                <th style={{ textAlign: "right", padding: "0 16px 8px" }}>Record</th>
              </tr>
            </thead>
            <tbody>
              {ratings.map((row, i) => {
                const team = leagueConfig.teams[row.team_id];
                const barPct = ((row.rating - minRating) / (maxRating - minRating)) * 100;
                const chgPos = row.change > 0;
                const fillColor = team.primary;
                return (
                  <tr
                    key={row.team_id}
                    style={{
                      borderLeft: `4px solid ${fillColor}`,
                      background: `linear-gradient(to right, ${fillColor}22 0%, transparent 340px)`,
                    }}
                  >
                    <td style={{ textAlign: "right", padding: "10px 10px 10px 6px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--text3)" }}>
                      {i + 1}
                    </td>
                    <td style={{ padding: "10px 8px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <TeamMark team={team} />
                        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{team.name}</span>
                      </div>
                    </td>
                    <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700 }}>
                      {row.rating.toFixed(1)}
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
                        {row.change.toFixed(1)}
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
        )}

        {activeTab === "standings" && (
          <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            Standings — coming soon
          </div>
        )}

        {activeTab === "bracket" && (
          <div style={{ padding: "4rem 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            Playoff Bracket — coming soon
          </div>
        )}
      </div>
    </div>
  );
}

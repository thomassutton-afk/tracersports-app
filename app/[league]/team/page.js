"use client";

/**
 * app/[league]/team/page.js — Team selector landing page.
 *
 * The old site put its team dropdown directly in the nav bar, always
 * visible on every team page, letting you jump between teams without
 * detouring through a list page first (reference/old-site/TeamPage.jsx —
 * the <select> next to Echo/Pulse). This page gets you the same outcome —
 * "pick any team, land on its page" — through a dedicated landing page
 * instead, same pattern as Season's selector: kept out of the shared
 * Nav.jsx component so a page-specific concern (which team is selected)
 * doesn't add complexity to a component every other page also depends on.
 * Nav's new "Teams" link points here.
 *
 * Once a team is picked, the URL itself (/[league]/team/[teamId]) is what
 * you'd bookmark/share/link to — this page is just the on-ramp, not
 * something a Team page itself ever redirects back to.
 */

import { useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import TeamMark from "../TeamMark";

export default function TeamSelectorPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const league = params.league;
  const variant = searchParams.get("variant") || "echo";

  const [selected, setSelected] = useState("");

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  const teamIds = Object.keys(leagueConfig.teams).sort();

  function goToTeam(teamId) {
    if (!teamId) return;
    router.push(`/${league}/team/${teamId}?variant=${variant}`);
  }

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">Franchise History</div>
          <div className="hero-heading">Teams</div>
          <div className="hero-sub">Pick a team to see its full {leagueConfig.label} history</div>
        </div>
        <select
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            goToTeam(e.target.value);
          }}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "6px 12px",
            border: "1px solid var(--border2)",
            borderRadius: 8,
            background: "var(--surface)",
            color: "var(--text)",
            cursor: "pointer",
          }}
        >
          <option value="" disabled>
            Jump to a team…
          </option>
          {teamIds.map((id) => (
            <option key={id} value={id}>
              {id} — {leagueConfig.teams[id].name}
            </option>
          ))}
        </select>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            gap: 12,
          }}
        >
          {teamIds.map((id) => {
            const team = leagueConfig.teams[id];
            return (
              <button
                key={id}
                onClick={() => goToTeam(id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "14px 16px",
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                  cursor: "pointer",
                  textAlign: "left",
                  fontFamily: "inherit",
                }}
              >
                <TeamMark team={team} teamId={id} league={league} size={32} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: team.secondary }}>{team.name}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", letterSpacing: 0.5 }}>
                    {id}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

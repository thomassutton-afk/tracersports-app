"use client";

/**
 * app/[league]/season/page.js — Season Page, v1 (Standings only).
 *
 * Ported from reference/old-site/SeasonPage.jsx, restructured to be
 * league-agnostic (reads leagueConfig.teams instead of a hardcoded NBA-only
 * TEAM_COLORS dict) and to only query tables that actually exist and are
 * populated in the new schema.
 *
 * Deliberately NOT built out in this pass — real work, tracked separately:
 *   - Rating Chart tab (heatmap + head-to-head) — shows as "coming soon"
 *     for now; old page's data came from ad-hoc client-side reduction of
 *     raw game rows, portable, just a second chunk of work on top of this.
 *   - Game Log tab — same story, plus pagination UI.
 *
 * Era-correct name/code/colors (e.g. a 1996 game shows "Seattle
 * SuperSonics" rather than "Oklahoma City Thunder") come from
 * lib/historicalIdentity.js, backed by the real team_history table —
 * same mechanism All-Time Rankings uses (see that page's header comment),
 * not a separate one. Falls back to the current team's name/colors from
 * config.js whenever an era has no history row or no colors backfilled
 * yet, which is the common case.
 *
 * Season selector is local page state, not a route segment or a Nav.jsx
 * control — kept deliberately out of the shared Nav component so someone
 * new to the codebase can see everything about how season selection works
 * by reading this one file, rather than tracing a page-specific concern
 * into a component every other page also depends on.
 */

import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import {
  getAvailableSeasons,
  fetchSeasonTeamGames,
  fetchPreseasonRatings,
  buildSeasonStandingsRows,
  buildSeasonAccuracy,
  fetchSeasonPlayoffGames,
  tallyPlayoffResults,
} from "@/lib/gamesData";
import {
  fetchTeamHistory,
  getDisplayIdentity,
  fetchLogoIndex,
  resolveHistoricalLogoPath,
} from "@/lib/historicalIdentity";
import HistoricalTeamMark from "../HistoricalTeamMark";

const VARIANT_LABELS = {
  echo: "Echo ratings — carry-forward variant",
  pulse: "Pulse ratings — season-reset variant",
};

const TABS = [
  { id: "standings", label: "Standings" },
  { id: "chart", label: "Rating Chart" },
  { id: "gamelog", label: "Game Log" },
];

export default function SeasonPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const league = params.league;
  const variant = searchParams.get("variant") || "echo";

  const [seasons, setSeasons] = useState([]);
  const [season, setSeason] = useState(null);
  const [rows, setRows] = useState([]);
  const [preseasonByTeam, setPreseasonByTeam] = useState({});
  const [accuracy, setAccuracy] = useState(null);
  const [poByTeam, setPoByTeam] = useState({});
  const [historyByTeam, setHistoryByTeam] = useState({});
  const [logoIndex, setLogoIndex] = useState({});
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [activeTab, setActiveTab] = useState("standings");
  const [confFilter, setConfFilter] = useState("all");

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  // Team history + logo index — independent of season/variant, fetched
  // once per league, same as All-Time Rankings does with this exact data.
  useEffect(() => {
    if (!leagueConfig) return;
    fetchTeamHistory(league).then(({ byTeam }) => setHistoryByTeam(byTeam));
    fetchLogoIndex(league).then(setLogoIndex);
  }, [league, leagueConfig]);

  // Season list + default to the most recent season, once per league.
  useEffect(() => {
    if (!leagueConfig) return;
    setSeason(null);
    setSeasons([]);
    getAvailableSeasons(league).then(({ seasons: list }) => {
      setSeasons(list);
      if (list.length > 0) setSeason(list[0]);
    });
  }, [league, leagueConfig]);

  useEffect(() => {
    if (!leagueConfig || season === null) return;
    setLoading(true);
    Promise.all([
      fetchSeasonTeamGames(league, season, variant),
      fetchPreseasonRatings(league, season, variant),
      fetchSeasonPlayoffGames(league, season, variant),
    ]).then(([gamesResult, preseasonResult, poResult]) => {
      if (gamesResult.error) {
        setFetchError(gamesResult.error);
        setRows([]);
        setAccuracy(null);
      } else {
        setFetchError(null);
        setRows(buildSeasonStandingsRows(gamesResult.rows));
        setAccuracy(buildSeasonAccuracy(gamesResult.rows));
      }
      setPreseasonByTeam(preseasonResult.byTeam);
      setPoByTeam(tallyPlayoffResults(poResult.poGames, leagueConfig));
      setLoading(false);
    });
  }, [league, leagueConfig, variant, season]);

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  const showPreseason = variant === "echo";
  const hasConferences = !!leagueConfig?.hasConferences;

  const filtered = rows.filter((r) => {
    if (!hasConferences || confFilter === "all") return true;
    const team = leagueConfig.teams[r.team_id];
    return team?.conf === confFilter;
  });
  const sorted = [...filtered].sort((a, b) => (b.finalRating ?? 0) - (a.finalRating ?? 0));
  const ratings = sorted.map((r) => r.finalRating ?? 0);
  const maxRating = ratings.length ? Math.max(...ratings) : 0;
  const minRating = ratings.length ? Math.min(...ratings) : 0;
  const roundLabels = leagueConfig?.engine?.roundLabels ?? {};
  const isCurrentSeason = seasons.length > 0 && season === seasons[0];
  const hasPlayoffData = Object.keys(poByTeam).length > 0;

  function playoffLabel(teamId) {
    const po = poByTeam[teamId];
    if (!po || po.highestRound === null) return null;
    const rec = po.rounds[String(po.highestRound)];
    const label = roundLabels[String(po.highestRound)] ?? `Round ${po.highestRound}`;
    return { label, w: rec?.w ?? 0, l: rec?.l ?? 0, champion: po.champion };
  }

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">
            {leagueConfig ? leagueConfig.seasonLabel(season ?? 0) : ""} Season
            {isCurrentSeason && hasPlayoffData ? " · Playoffs" : ""}
          </div>
          <div className="hero-heading">Season Overview</div>
          <div className="hero-sub">{leagueConfig ? VARIANT_LABELS[variant] : ""}</div>
        </div>
        {seasons.length > 0 && (
          <select
            value={String(season ?? "")}
            onChange={(e) => setSeason(Number(e.target.value))}
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
            {seasons.map((y) => (
              <option key={y} value={String(y)}>
                {leagueConfig.seasonLabel(y)}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Accuracy strip — deliberately small/muted (fine print, not a
          headline stat): compact single line, tucked under the hero rather
          than styled like a stats dashboard. */}
      {accuracy && (
        <div style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
          <div
            style={{
              maxWidth: 1200,
              margin: "0 auto",
              padding: "0.5rem 2rem",
              display: "flex",
              gap: 18,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text3)",
            }}
          >
            <span>{Number(accuracy.n).toLocaleString()} games rated</span>
            <span>·</span>
            <span>{accuracy.pct}% accuracy</span>
            {accuracy.brier != null && (
              <>
                <span>·</span>
                <span>{accuracy.brier} Brier score</span>
              </>
            )}
          </div>
        </div>
      )}

      {/* TABS */}
      <div style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
        <div style={{ display: "flex", maxWidth: 1200, margin: "0 auto", padding: "0 2rem" }}>
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                fontSize: 13,
                fontFamily: "var(--font-mono)",
                padding: "12px 20px",
                cursor: "pointer",
                background: "none",
                border: "none",
                marginBottom: -1,
                borderBottom: activeTab === id ? "2px solid var(--acc)" : "2px solid transparent",
                color: activeTab === id ? "var(--acc)" : "var(--text3)",
                fontWeight: activeTab === id ? 600 : 400,
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
        {activeTab !== "standings" ? (
          <div style={{ padding: "60px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            {TABS.find((t) => t.id === activeTab).label} — coming soon.
          </div>
        ) : loading ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            Loading…
          </div>
        ) : fetchError ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: "#b91c1c", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            Couldn&apos;t load standings: {fetchError.message}
          </div>
        ) : sorted.length === 0 ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            No data for {leagueConfig?.label} season {season}.
          </div>
        ) : (
          <>
            {hasConferences && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
                {["all", ...leagueConfig.conferences].map((c) => (
                  <button
                    key={c}
                    onClick={() => setConfFilter(c)}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      padding: "4px 12px",
                      borderRadius: 6,
                      cursor: "pointer",
                      border: `1px solid ${confFilter === c ? "var(--acc)" : "var(--border2)"}`,
                      color: confFilter === c ? "var(--acc)" : "var(--text3)",
                      background: confFilter === c ? "var(--acc-dim)" : "none",
                    }}
                  >
                    {c === "all" ? `All ${rows.length}` : c}
                  </button>
                ))}
                <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text3)", fontFamily: "var(--font-mono)" }}>
                  Click column headers to sort
                </span>
              </div>
            )}

            <div style={{ overflowX: "auto", borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={thStyle("right")}>#</th>
                    <th style={thStyle("left")}>Team</th>
                    {showPreseason && <th style={thStyle("right")}>Pre-Season</th>}
                    <th style={thStyle("right")}>RS Record</th>
                    <th style={thStyle("right")}>RS Rating</th>
                    <th style={{ ...thStyle("right"), width: 90 }}>Strength</th>
                    <th style={thStyle("left")}>Playoffs</th>
                    <th style={thStyle("right")}>Final Rating</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row, i) => {
                    const team = leagueConfig.teams[row.team_id];
                    if (!team) return null;
                    // Era-correct name/colors when this season's identity
                    // differs from the team's current one (e.g. 1996 shows
                    // "Seattle SuperSonics" instead of "Oklahoma City
                    // Thunder") - falls back to the current team's own
                    // name/colors internally within getDisplayIdentity
                    // whenever there's no history row or no colors
                    // backfilled yet for the matched era.
                    const identity = getDisplayIdentity(row.team_id, season, historyByTeam, leagueConfig);
                    const logoPath = resolveHistoricalLogoPath(row.team_id, season, historyByTeam, logoIndex, league);
                    const barPct = maxRating > minRating ? ((row.finalRating - minRating) / (maxRating - minRating)) * 100 : 50;
                    const fillColor = identity.primary === "#000000" ? identity.tertiary : identity.primary;
                    const po = playoffLabel(row.team_id);
                    const preseason = preseasonByTeam[row.team_id];
                    return (
                      <tr
                        key={row.team_id}
                        style={{
                          borderTop: "1px solid var(--border)",
                          borderLeft: `4px solid ${fillColor}`,
                          background: `linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`,
                        }}
                      >
                        <td style={{ textAlign: "right", padding: "0 10px 0 6px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "#fff", width: 36 }}>
                          {i + 1}
                        </td>
                        <td style={{ padding: "10px 8px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <HistoricalTeamMark
                              logoPath={logoPath}
                              currentLogoTeamId={row.team_id}
                              league={league}
                              abbr={identity.code}
                              color={fillColor}
                              size={28}
                            />
                            <span style={{ fontSize: 13, fontWeight: 700, color: identity.secondary }}>{identity.name}</span>
                          </div>
                        </td>
                        {showPreseason && (
                          <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>
                            {preseason != null ? preseason.toFixed(1) : "—"}
                          </td>
                        )}
                        <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>
                          {row.rsW}–{row.rsL}
                        </td>
                        <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--text)" }}>
                          {row.rsRating?.toFixed(1) ?? "—"}
                        </td>
                        <td style={{ padding: "0 8px", width: 130 }}>
                          <div style={{ height: 4, background: "rgba(0,0,0,0.12)", borderRadius: 2 }}>
                            <div style={{ width: `${barPct}%`, height: 4, borderRadius: 2, background: fillColor }} />
                          </div>
                        </td>
                        <td style={{ padding: "0 12px" }}>
                          {po ? (
                            <span
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: 11,
                                fontWeight: po.champion ? 700 : 500,
                                color: po.champion ? "var(--ut)" : "var(--text2)",
                              }}
                            >
                              {po.champion ? "Champion" : `${po.label} (${po.w}–${po.l})`}
                            </span>
                          ) : (
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--border2)" }}>—</span>
                          )}
                        </td>
                        <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
                          {row.finalRating?.toFixed(1) ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function thStyle(align) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 9,
    fontWeight: 500,
    color: "var(--text3)",
    textTransform: "uppercase",
    letterSpacing: 1.2,
    padding: "10px 12px",
    textAlign: align,
    whiteSpace: "nowrap",
    background: "var(--surface)",
    borderBottom: "2px solid var(--border)",
  };
}

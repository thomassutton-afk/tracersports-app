"use client";

/**
 * SeasonProjection — compact Monte Carlo season-projection table.
 * Sits in page.js's right column, below <GamesPanel>, in the space
 * that's left over there since GamesPanel is usually shorter than the
 * full ratings table on the left.
 *
 * Reads season_projections (see db.py's save_season_projection /
 * export_to_supabase.py's build_season_projection for how this data
 * gets here). Renders nothing at all - not even a "no projection"
 * placeholder - once a season has no remaining games: an empty result
 * here is the normal, expected end state (see clear_season_projection
 * in db.py), not an error state worth taking up space to announce.
 */

import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";

async function getProjection(league, season, variant) {
  const { data, error } = await supabase
    .from("season_projections")
    .select("team_id, avg_wins, p10_wins, median_wins, p90_wins, prob_finish_first, remaining_games, computed_at")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .order("avg_wins", { ascending: false });

  if (error) return { rows: [], error };
  return { rows: data || [], error: null };
}

export default function SeasonProjection({ league, season, variant, leagueConfig }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProjection(league, season, variant).then(({ rows }) => {
      if (cancelled) return;
      setRows(rows);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [league, season, variant]);

  // Nothing to show, and nothing worth showing an empty state for -
  // see module docstring. Loading briefly renders nothing rather than
  // a flash of "Loading..." for what's usually a fast query.
  if (loading || rows.length === 0) return null;

  const remaining = rows[0]?.remaining_games;

  return (
    <div style={{ marginTop: 20 }}>
      <div className="section-label">
        Season Projection
        {remaining != null && (
          <span style={{ fontWeight: 400, color: "var(--text3)", marginLeft: 6 }}>
            ({remaining} game{remaining === 1 ? "" : "s"} remaining, simulated)
          </span>
        )}
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left", padding: "4px 8px 6px 0", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", fontWeight: 600 }}>Team</th>
            <th style={{ textAlign: "right", padding: "4px 8px 6px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", fontWeight: 600 }}>Proj. W</th>
            <th style={{ textAlign: "right", padding: "4px 8px 6px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", fontWeight: 600 }}>10th–90th</th>
            <th style={{ textAlign: "right", padding: "4px 0 6px 8px", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", fontWeight: 600 }}>P(1st)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const team = leagueConfig.teams[r.team_id];
            if (!team) return null; // defensive, same as page.js's ratings table
            return (
              <tr key={r.team_id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "6px 8px 6px 0", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, color: team.secondary }}>
                  {team.name}
                </td>
                <td style={{ textAlign: "right", padding: "6px 8px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>
                  {r.avg_wins?.toFixed(1)}
                </td>
                <td style={{ textAlign: "right", padding: "6px 8px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)" }}>
                  {r.p10_wins}–{r.p90_wins}
                </td>
                <td style={{ textAlign: "right", padding: "6px 0 6px 8px", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: r.prob_finish_first >= 0.05 ? 700 : 400, color: r.prob_finish_first >= 0.05 ? "var(--acc)" : "var(--text2)" }}>
                  {(r.prob_finish_first * 100).toFixed(r.prob_finish_first < 0.01 ? 1 : 0)}%
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", marginTop: 8, lineHeight: 1.4 }}>
        Projection based on current ratings and simulated remaining games - a plausible
        range of outcomes, not a guarantee.
      </div>
    </div>
  );
}

"use client";

/**
 * app/[league]/page.js
 *
 * Step 1: prove the pipeline works — real Supabase data, rendered, routed by
 * league. No styling decisions, no colors, no bracket/chart complexity yet.
 * Once this reliably shows real rows for /nba, we build the real Dashboard
 * on top of the same query pattern.
 *
 * Requires: schema.sql applied, and at least one league's games imported
 * with the new `league` column populated (e.g. league = 'nba').
 */

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { supabase } from '@/lib/supabase';
import { getLeagueConfig } from '@/lib/sports/registry';

const CURRENT_SEASON = 2026;
const VARIANT = 'continelo';

async function getCurrentRatings(league) {
  // Pull the most recent game row per team for this league/season/variant,
  // then read post_gm_rate off it. No view dependency — works directly
  // against the raw `games` table so this isn't blocked on views existing yet.
  const { data, error } = await supabase
    .from('games')
    .select('team_id, post_gm_rate, rating_change, date')
    .eq('league', league)
    .eq('season', CURRENT_SEASON)
    .eq('variant', VARIANT)
    .order('date', { ascending: false });

  if (error) {
    console.error('Supabase query failed:', error);
    return { rows: [], error };
  }

  // Keep only the latest row per team_id (data is already date-desc sorted)
  const latestByTeam = {};
  for (const row of data ?? []) {
    if (!latestByTeam[row.team_id]) latestByTeam[row.team_id] = row;
  }

  return { rows: Object.values(latestByTeam), error: null };
}

export default function LeaguePage() {
  const params = useParams();
  const league = params.league;

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  const [ratings, setRatings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [queryError, setQueryError] = useState(null);

  useEffect(() => {
    if (!leagueConfig) return;
    setLoading(true);
    getCurrentRatings(league).then(({ rows, error }) => {
      setRatings(rows);
      setQueryError(error);
      setLoading(false);
    });
  }, [league]);

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: 'monospace' }}>
        <p>Unknown league: "{league}"</p>
        <p>{configError}</p>
      </div>
    );
  }

  const sorted = [...ratings].sort((a, b) => (b.post_gm_rate ?? 0) - (a.post_gm_rate ?? 0));

  return (
    <div style={{ padding: 40, fontFamily: 'monospace', maxWidth: 700, margin: '0 auto' }}>
      <h1>{leagueConfig.label} — Current Ratings</h1>
      <p style={{ color: '#888', fontSize: 13 }}>
        Season {leagueConfig.seasonLabel(CURRENT_SEASON)} · {VARIANT}
      </p>

      {loading && <p>Loading…</p>}

      {queryError && (
        <p style={{ color: 'crimson' }}>
          Query failed — check that the schema is applied and this league has
          data imported with league = "{league}". ({queryError.message})
        </p>
      )}

      {!loading && !queryError && sorted.length === 0 && (
        <p>No rows found for league="{league}", season={CURRENT_SEASON}, variant="{VARIANT}".
           This is expected if data hasn't been imported for this league yet.</p>
      )}

      {!loading && sorted.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 20 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc', textAlign: 'left' }}>
              <th style={{ padding: '6px 8px' }}>#</th>
              <th style={{ padding: '6px 8px' }}>Team</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Rating</th>
              <th style={{ padding: '6px 8px', textAlign: 'right' }}>Last Δ</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => {
              const team = leagueConfig.teams[row.team_id];
              return (
                <tr key={row.team_id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '6px 8px' }}>{i + 1}</td>
                  <td style={{ padding: '6px 8px' }}>{team?.name ?? row.team_id}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right' }}>{row.post_gm_rate?.toFixed(1)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                    {row.rating_change > 0 ? '+' : ''}{row.rating_change?.toFixed(1)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

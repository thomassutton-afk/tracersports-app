"use client";

/**
 * ContinElo — Season Page (v5)
 * Visual refresh to match Dashboard.jsx:
 * - Warm #F5F0E8 background, matching C tokens
 * - Team-color left-gradient rows in standings (same pattern as Power Rankings)
 * - Secondary color team names, tc/ts/tt helpers + BRK/SA overrides
 * - Consistent nav, hero, stripe, font tokens
 */

import { useState, useEffect, useRef } from "react";
import { supabase } from "@/lib/supabase";
import Link from "next/link";
import Footer from "@/components/Footer";

// ---------------------------------------------------------------------------
// Season helpers
// ---------------------------------------------------------------------------
const SEASONS = Array.from({ length: 31 }, (_, i) => 1996 + i);
const SEASON_LABEL = (y) => `${y - 1}–${String(y).slice(2)}`;

// ---------------------------------------------------------------------------
// Team color tables — mirrored from Dashboard.jsx
// ---------------------------------------------------------------------------
const TEAM_COLORS = {
  ATL:'#C8102E', BOS:'#007A33', BRK:'#000000', CHA:'#00778B',
  CHI:'#CE1141', CLE:'#860038', DAL:'#0050B5', DEN:'#0E2240',
  DET:'#1D42BA', GS:'#1D428A',  HOU:'#CE1141', IND:'#002D62',
  LAC:'#0C2340', LAL:'#552583', MEM:'#5D76A9', MIA:'#98002E',
  MIL:'#00471B', MIN:'#236192', NO:'#0C2340',  NY:'#1D4289',
  OKC:'#0072CE', ORL:'#0050B5', PHI:'#006BB6', PHX:'#1D1160',
  POR:'#E03A3E', SA:'#9EA2A2',  SAC:'#5A2D81', TOR:'#BA0C2F',
  UTA:'#330072', WAS:'#E31837',
}

const TEAM_SECONDARY = {
  ATL:'#FDB927', BOS:'#FFFFFF', BRK:'#FFFFFF', CHA:'#1D1160',
  CHI:'#000000', CLE:'#B9975B', DAL:'#B8C4CA', DEN:'#FEC524',
  DET:'#C8102E', GS:'#FFC72C',  HOU:'#000000', IND:'#FDBB30',
  LAC:'#C8102E', LAL:'#FDB927', MEM:'#F5B112', MIA:'#F9A01B',
  MIL:'#EEE1C6', MIN:'#78BE21', NO:'#B9975B',  NY:'#FF8200',
  OKC:'#F9423A', ORL:'#000000', PHI:'#ED174C', PHX:'#E56020',
  POR:'#000000', SA:'#000000',  SAC:'#FFFFFF', TOR:'#000000',
  UTA:'#FFFFFF', WAS:'#002B5C',
}

const TEAM_TERTIARY = {
  ATL:'#FFFFFF', BOS:'#BA9653', BRK:'#707372', CHA:'#FFFFFF',
  CHI:'#FFFFFF', CLE:'#000000', DAL:'#9EA2A2', DEN:'#8B2131',
  DET:'#FFFFFF', GS:'#FFFFFF',  HOU:'#C4CED4', IND:'#FFFFFF',
  LAC:'#FFFFFF', LAL:'#000000', MEM:'#12173F', MIA:'#000000',
  MIL:'#000000', MIN:'#0C2340', NO:'#C8102E',  NY:'#FFFFFF',
  OKC:'#FFB81C', ORL:'#9EA2A2', PHI:'#FFFFFF', PHX:'#FFFFFF',
  POR:'#FFFFFF', SA:'#FFFFFF',  SAC:'#707372', TOR:'#FFFFFF',
  UTA:'#000000', WAS:'#9EA2A2',
}

const tc = a => TEAM_COLORS[a]   || '#663399'
const ts = a => TEAM_SECONDARY[a] || TEAM_COLORS[a] || '#663399'
const tt = a => TEAM_TERTIARY[a]  || '#FFFFFF'

// ---------------------------------------------------------------------------
// Display identity lookup — season-aware abbr, name, color
// ---------------------------------------------------------------------------
const DISPLAY_IDENTITIES = {
  OKC: [
    { through: 2001, abbr:"SEA", name:"Seattle SuperSonics",    color:"#00653A" },
    { through: 2008, abbr:"SEA", name:"Seattle SuperSonics",    color:"#00653A" },
  ],
  MEM: [
    { through: 2001, abbr:"VAN", name:"Vancouver Grizzlies",    color:"#00B2A9" },
  ],
  BRK: [
    { through: 2012, abbr:"NJN", name:"New Jersey Nets",        color:"#002A60" },
  ],
  NO: [
    { through: 2002, abbr:"CHA", name:"Charlotte Hornets",      color:"#1D1160" },
    { through: 2013, abbr:"NOH", name:"New Orleans Hornets",    color:"#002B5C" },
  ],
  CHA: [
    { through: 2014, abbr:"CHA", name:"Charlotte Bobcats",      color:"#F26522" },
  ],
  WAS: [
    { through: 1997, abbr:"WAS", name:"Washington Bullets",     color:"#E31837" },
  ],
};

function getDisplayIdentity(team_id, season) {
  const overrides = DISPLAY_IDENTITIES[team_id];
  if (overrides) {
    for (const o of overrides) {
      if (season <= o.through) return { abbr: o.abbr, name: o.name, color: o.color };
    }
  }
  return { abbr: team_id, name: null, color: TEAM_COLORS[team_id] || "#663399" };
}

// ---------------------------------------------------------------------------
// Historical logo lookup
// ---------------------------------------------------------------------------
// Each entry is { abbr, maxYear } — maxYear caps how far that abbr's logos
// can reach. Without this, an abbr reused by a *different* still-active
// franchise (e.g. "CHA" = original Charlotte Hornets 1988-2002, but also
// Charlotte Bobcats 2004-2014 and the modern Charlotte Hornets 2014-present)
// will keep supplying newer and newer logo years to whichever team's search
// pool includes it, hijacking the match once those years exceed the other
// legitimate entries.
const FRANCHISE_ABBRS = {
  OKC: [{ abbr: "SEA", maxYear: 2008 }, { abbr: "OKC", maxYear: Infinity }],
  MEM: [{ abbr: "VAN", maxYear: 2001 }, { abbr: "MEM", maxYear: Infinity }],
  BRK: [{ abbr: "NJ",  maxYear: 2012 }, { abbr: "BRK", maxYear: Infinity }],
  NO:  [{ abbr: "CHA", maxYear: 2002 }, { abbr: "NOH", maxYear: 2013 }, { abbr: "NO", maxYear: Infinity }],
  CHA: [{ abbr: "CHA", maxYear: Infinity }],
};

let _logoIndexCache = null;
let _logoIndexPromise = null;

function fetchLogoIndex() {
  if (_logoIndexCache) return Promise.resolve(_logoIndexCache);
  if (_logoIndexPromise) return _logoIndexPromise;
  _logoIndexPromise = fetch("/api/logo-index")
    .then(r => r.json())
    .then(data => { _logoIndexCache = data; return data; });
  return _logoIndexPromise;
}

function resolveHistoricalLogoPath(team_id, season, index) {
  const segments = FRANCHISE_ABBRS[team_id] ?? [{ abbr: team_id, maxYear: Infinity }];
  let bestFile = null;
  let bestYear = -1;
  for (const { abbr, maxYear } of segments) {
    const cap = Math.min(season, maxYear);
    const years = index[abbr] ?? [];
    for (const year of years) {
      if (year <= cap && year > bestYear) {
        bestYear = year;
        bestFile = `/logos/historical/${abbr}_${year}.png`;
      }
    }
  }
  return bestFile ?? `/logos/current/${team_id}.png`;
}

function useLogoIndex() {
  const [index, setIndex] = useState(_logoIndexCache);
  useEffect(() => {
    if (_logoIndexCache) { setIndex(_logoIndexCache); return; }
    fetchLogoIndex().then(setIndex);
  }, []);
  return index;
}

function TeamLogo({ team_id, season, size = 28, style = {} }) {
  const [errored, setErrored] = useState(false);
  const index = useLogoIndex();
  const identity = getDisplayIdentity(team_id, season);
  const color = identity.color;

  if (!index || errored) {
    return (
      <span style={{
        fontFamily: mono, fontSize: Math.max(8, size * 0.38), fontWeight: 700,
        padding: "2px 6px", borderRadius: 4,
        border: `1.5px solid ${color}`, color,
        letterSpacing: 0.3, flexShrink: 0, lineHeight: 1,
        display: "inline-flex", alignItems: "center", ...style,
      }}>
        {identity.abbr}
      </span>
    );
  }

  return (
    <img
      src={resolveHistoricalLogoPath(team_id, season, index)}
      alt={identity.abbr}
      width={size} height={size}
      onError={() => setErrored(true)}
      style={{
        width: size, height: size, objectFit: "contain",
        flexShrink: 0, display: "block",
        filter: 'drop-shadow(0 0 4px rgba(255,255,255,0.95)) drop-shadow(0 0 10px rgba(255,255,255,0.6))',
        ...style,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Design tokens — match Dashboard.jsx
// ---------------------------------------------------------------------------
const mono  = "'IBM Plex Mono', monospace"
const serif = "'Playfair Display', Georgia, serif"
const C = {
  bg:'#F5F0E8', surface:'#FDFAF5', border:'#EDE8DD', border2:'#E0D9CE',
  text:'#1A1816', text2:'#5C5650', text3:'#9A9490',
  acc:'#663399', ut:'#BF5700', uo:'#154733',
}

// ---------------------------------------------------------------------------
// Conference / Division membership
// ---------------------------------------------------------------------------
const CONFERENCES = {
  East: ["ATL","BOS","BRK","CHA","CHI","CLE","DET","IND","MIA","MIL","NY","ORL","PHI","TOR","WAS"],
  West: ["DAL","DEN","GS","HOU","LAC","LAL","MEM","MIN","NO","OKC","PHX","POR","SA","SAC","UTA"],
};

const DIVISIONS_MODERN = {
  Atlantic:  ["BOS","BRK","NY","PHI","TOR"],
  Central:   ["CHI","CLE","DET","IND","MIL"],
  Southeast: ["ATL","CHA","MIA","ORL","WAS"],
  Northwest: ["DEN","MIN","OKC","POR","UTA"],
  Pacific:   ["GS","LAC","LAL","PHX","SAC"],
  Southwest: ["DAL","HOU","MEM","NO","SA"],
};

const DIVISIONS_PRE2005 = {
  Atlantic: ["BOS","MIA","NY","BRK","ORL","PHI","WAS"],
  Central:  ["ATL","CHA","CHI","CLE","DET","IND","MIL","TOR"],
  Midwest:  ["DAL","DEN","HOU","MIN","NO","SA","UTA"],
  Pacific:  ["GS","LAC","LAL","MEM","PHX","POR","SAC","OKC"],
};

function getDivisions(season) {
  return season >= 2005 ? DIVISIONS_MODERN : DIVISIONS_PRE2005;
}

// ---------------------------------------------------------------------------
// Round labels
// ---------------------------------------------------------------------------
const ROUND_LABELS = {
  RS: "Reg. Season", "0.5": "Play-In", INS: "In-Season Tourn.",
  "1": "Round 1", "2": "Conf. Semis", "3": "Conf. Finals", "4": "NBA Finals",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const fmt1      = (r) => (r != null ? Number(r).toFixed(1) : "—");
const fmtRecord = (w, l) => (w != null ? `${w}–${l}` : "—");
const fmtDate   = (d) => {
  if (!d) return "";
  return new Date(d + "T12:00:00").toLocaleDateString("en-US", { month:"short", day:"numeric" });
};
const chgColor = (n) => (n > 0 ? "#1a7a34" : n < 0 ? "#b91c1c" : C.text3);
const chgStr   = (n) => (n == null ? "—" : (n > 0 ? "+" : "") + Number(n).toFixed(1));

// ---------------------------------------------------------------------------
// Rating color scale — red (low) → amber → green (high)
// ---------------------------------------------------------------------------
const RATING_STOPS = [
  [0,    '#C8102E'],
  [0.2,  '#E05A28'],
  [0.42, '#F5A623'],
  [0.62, '#7AB648'],
  [0.82, '#2D9B5A'],
  [1.0,  '#154733'],
]

function ratingColor(val, globalMin, globalMax) {
  const t = Math.max(0, Math.min(1, (val - globalMin) / (globalMax - globalMin || 1)))
  for (let i = 1; i < RATING_STOPS.length; i++) {
    const [p0, c0] = RATING_STOPS[i-1]
    const [p1, c1] = RATING_STOPS[i]
    if (t <= p1) {
      const f = (t - p0) / (p1 - p0)
      const h = (hex) => [parseInt(hex.slice(1,3),16), parseInt(hex.slice(3,5),16), parseInt(hex.slice(5,7),16)]
      const [r0,g0,b0] = h(c0), [r1,g1,b1] = h(c1)
      return `rgb(${Math.round(r0+f*(r1-r0))},${Math.round(g0+f*(g1-g0))},${Math.round(b0+f*(b1-b0))})`
    }
  }
  return RATING_STOPS.at(-1)[1]
}

// ---------------------------------------------------------------------------
// Snap game-by-game data to weekly Sunday snapshots
// Input: byTeam = { abbr: [{date: ms, rating: number}, ...] } already sorted asc
// Returns: { abbr: [{sunday: Date, rating: number}, ...] }
// ---------------------------------------------------------------------------
function buildWeeklySnapshots(byTeam, year) {
  // Opening night: first game date across all teams
  const allDates = Object.values(byTeam).flat().map(p => p.date).sort((a,b) => a-b)
  if (!allDates.length) return {}

  const openingNight = allDates[0]

  // lastDate = the absolute latest game date across ALL teams in the set,
  // so teams eliminated early still get columns through the end of the season
  // (their rating forward-fills from their last game into those later Sundays)
  const lastDate = Math.max(...Object.values(byTeam).map(pts => pts.at(-1)?.date ?? 0))
  const sundays = []
  // Walk to first Sunday on or after opening night
  const d = new Date(openingNight)
  while (d.getDay() !== 0) d.setDate(d.getDate() + 1)
  while (d.getTime() <= lastDate) {
    sundays.push(d.getTime())
    d.setDate(d.getDate() + 7)
  }

  const result = {}
  for (const [abbr, points] of Object.entries(byTeam)) {
    const snaps = []
    // Opening night: use the rating from their first game
    const firstGame = points[0]
    if (!firstGame) { result[abbr] = snaps; continue }
    snaps.push({ date: openingNight, rating: firstGame.rating, label: 'Opening' })

    // For each Sunday, find the last game on or before that Sunday.
    // Forward-fill: if a team has no game on/before this Sunday, use opening night.
    // If they're eliminated and have no games after their last date, last known rating fills forward.
    for (const sun of sundays) {
      let best = firstGame // default = opening night rating (forward-fill from start)
      for (const p of points) {
        if (p.date <= sun) best = p
        else break
      }
      snaps.push({ date: sun, rating: best.rating, label: null })
    }
    result[abbr] = snaps
  }
  return result
}

// ---------------------------------------------------------------------------
// RatingHeatmap — heatmap of weekly snapshots, one row per team
// ---------------------------------------------------------------------------
function RatingHeatmap({ seriesData, year, standings = [] }) {
  const [tooltip, setTooltip] = useState(null) // {x,y,abbr,date,rating,change}

  if (!seriesData?.length) {
    return (
      <div style={{ padding:'40px 0', textAlign:'center', color:C.text3, fontSize:13, fontFamily:mono }}>
        No data
      </div>
    )
  }

  // RS rating map for delta calculation — use rs_end_rating so delta is RS-only,
  // consistent with the sort order (which also uses rs_end_rating)
  const rsMap = {}
  for (const t of standings) rsMap[t.team_id] = t.rs_end_rating ?? null

  // Build weekly snapshots from raw game-by-game data
  const byTeam = {}
  for (const s of seriesData) {
    byTeam[s.team] = s.points // already sorted asc by date
  }
  const snapshots = buildWeeklySnapshots(byTeam, year)

  // Global min/max across all teams and weeks for consistent color scale
  const allVals = Object.values(snapshots).flat().map(p => p.rating)
  const globalMin = Math.min(...allVals)
  const globalMax = Math.max(...allVals)

  // Week labels — derive month labels from snapshot dates of first team
  const firstAbbr = seriesData[0].team
  const weeks = snapshots[firstAbbr] || []
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const monthLabels = weeks.map((w, i) => {
    if (i === 0) return 'Open'
    const dt = new Date(w.date)
    const prev = new Date(weeks[i-1].date)
    return dt.getMonth() !== prev.getMonth() ? MONTHS[dt.getMonth()] : ''
  })

  const CELL_H = 26
  const LABEL_W = 44
  const DELTA_W = 44 // right-side delta badge column

  return (
    <div>
      {/* Month header */}
      <div style={{ display:'flex', marginBottom:2, paddingLeft:LABEL_W, paddingRight:DELTA_W+8 }}>
        {monthLabels.map((lbl, i) => (
          <div key={i} style={{
            flex:1, textAlign:'center',
            fontFamily:mono, fontSize:9, color:C.text3,
            fontWeight: lbl && lbl !== 'Open' ? 600 : 400,
            minWidth:0,
          }}>{lbl}</div>
        ))}
      </div>

      {/* Team rows */}
      {seriesData.map(({ team }) => {
        const snaps = snapshots[team] || []
        const identity = getDisplayIdentity(team, year)
        const teamColor = identity.color || tc(team)
        const openingRating = snaps[0]?.rating
        // Delta = RS end rating minus opening night — consistent with RS-based sort order
        const rsEndRating = rsMap[team] ?? snaps.at(-1)?.rating
        const seasonChange = (rsEndRating != null && openingRating != null)
          ? Math.round(rsEndRating - openingRating) : null

        return (
          <div key={team} style={{ display:'flex', alignItems:'stretch', marginBottom:1 }}>
            {/* Team label */}
            <div style={{
              width:LABEL_W, flexShrink:0, fontFamily:mono, fontSize:10, fontWeight:600,
              color:teamColor, paddingRight:6, textAlign:'right', lineHeight:`${CELL_H}px`,
            }}>
              {identity.abbr}
            </div>
            {/* Cells — flex:1 so they fill all available width evenly */}
            {snaps.map((snap, i) => {
              const bg = ratingColor(snap.rating, globalMin, globalMax)
              const isHovered = tooltip?.abbr === team && tooltip?.weekIdx === i
              return (
                <div
                  key={i}
                  style={{
                    flex:1, height:CELL_H, minWidth:0,
                    background: bg,
                    opacity: isHovered ? 1 : 0.85,
                    outline: isHovered ? `2px solid ${C.text}` : 'none',
                    outlineOffset: -1,
                    cursor:'default',
                    transition:'opacity 0.1s',
                  }}
                  onMouseEnter={(e) => {
                    const prev = i > 0 ? snaps[i-1].rating : null
                    setTooltip({
                      x: e.clientX, y: e.clientY,
                      abbr: team, name: identity.name || team,
                      weekIdx: i,
                      date: new Date(snap.date).toLocaleDateString('en-US',{month:'short',day:'numeric'}),
                      rating: snap.rating,
                      change: prev != null ? Math.round(snap.rating - prev) : null,
                    })
                  }}
                  onMouseMove={(e) => setTooltip(t => t ? {...t, x:e.clientX, y:e.clientY} : t)}
                  onMouseLeave={() => setTooltip(null)}
                />
              )
            })}
            {/* Season delta badge */}
            <div style={{
              width:DELTA_W, flexShrink:0, paddingLeft:8,
              fontFamily:mono, fontSize:10, fontWeight:600,
              lineHeight:`${CELL_H}px`,
              color: seasonChange == null ? C.text3
                : seasonChange > 0 ? '#1a7a34'
                : seasonChange < 0 ? '#b91c1c'
                : C.text3,
            }}>
              {seasonChange == null ? '' : seasonChange > 0 ? `+${seasonChange}` : seasonChange}
            </div>
          </div>
        )
      })}

      {/* Legend */}
      <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:14,
        paddingLeft:LABEL_W, borderTop:`1px solid ${C.border}`, paddingTop:12 }}>
        <span style={{ fontFamily:mono, fontSize:9, color:C.text3 }}>Lower</span>
        <div style={{ display:'flex', height:8, width:160, borderRadius:2, overflow:'hidden' }}>
          {RATING_STOPS.slice(0,-1).map(([,c], i) => (
            <div key={i} style={{ flex:1, background:c }} />
          ))}
        </div>
        <span style={{ fontFamily:mono, fontSize:9, color:C.text3 }}>Higher</span>
        <span style={{ marginLeft:16, fontFamily:mono, fontSize:9, color:C.text3 }}>
          Opening night + every Sunday · rightmost badge = season Δ
        </span>
      </div>

      {/* Floating tooltip */}
      {tooltip && (
        <div style={{
          position:'fixed', left:tooltip.x+14, top:tooltip.y-44,
          background:C.surface, border:`1px solid ${C.border2}`,
          borderRadius:8, padding:'7px 11px',
          fontFamily:mono, fontSize:11, lineHeight:1.7,
          pointerEvents:'none', zIndex:999,
          boxShadow:'0 2px 10px rgba(0,0,0,0.1)',
        }}>
          <div style={{ fontWeight:700, color: getDisplayIdentity(tooltip.abbr, year).color }}>
            {tooltip.abbr}
          </div>
          <div style={{ color:C.text2 }}>{tooltip.date}</div>
          <div style={{ color:C.text }}>
            Rating: <strong>{tooltip.rating?.toFixed(1)}</strong>
          </div>
          {tooltip.change != null && (
            <div style={{ color: tooltip.change > 0 ? '#1a7a34' : tooltip.change < 0 ? '#b91c1c' : C.text3 }}>
              Wk Δ: {tooltip.change > 0 ? '+' : ''}{tooltip.change}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// H2HChart — clean two-team SVG line chart (still works great at 2 lines)
// ---------------------------------------------------------------------------
function H2HChart({ seriesData, year, width = 820, height = 300 }) {
  const [hovered, setHovered] = useState(null)

  if (!seriesData?.length) {
    return (
      <div style={{ height, display:'flex', alignItems:'center', justifyContent:'center',
        color:C.text3, fontSize:13, fontFamily:mono }}>
        Select two teams above
      </div>
    )
  }

  // Build weekly snapshots
  const byTeam = {}
  for (const s of seriesData) byTeam[s.team] = s.points
  const snapshots = buildWeeklySnapshots(byTeam, year)

  const allPoints = Object.values(snapshots).flat()
  if (!allPoints.length) return null

  const allRatings = allPoints.map(p => p.rating)
  const allDates   = allPoints.map(p => p.date)
  const minR = Math.min(...allRatings) - 20
  const maxR = Math.max(...allRatings) + 20
  const minD = Math.min(...allDates)
  const maxD = Math.max(...allDates)
  const pad = { top:16, right:56, bottom:28, left:54 }
  const W = width - pad.left - pad.right
  const H = height - pad.top - pad.bottom

  const xS = d => ((d - minD) / (maxD - minD || 1)) * W
  const yS = r => H - ((r - minR) / (maxR - minR || 1)) * H

  const rawStep = (maxR - minR) / 5
  const step = Math.ceil(rawStep / 10) * 10 || 10
  const yTicks = []
  for (let v = Math.ceil(minR/step)*step; v <= maxR; v += step) yTicks.push(v)

  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const xTicks = []
  const seenMo = new Set()
  ;[...allDates].sort((a,b)=>a-b).forEach(d => {
    const dt = new Date(d)
    const key = `${dt.getFullYear()}-${dt.getMonth()}`
    if (!seenMo.has(key)) { seenMo.add(key); xTicks.push({ d, label: MONTHS[dt.getMonth()] }) }
  })

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`}
        style={{ overflow:'visible' }}
        onMouseLeave={() => setHovered(null)}>
        {yTicks.map(v => (
          <g key={v}>
            <line x1={pad.left} y1={pad.top+yS(v)} x2={pad.left+W} y2={pad.top+yS(v)}
              stroke={C.border} strokeWidth={1} />
            <text x={pad.left-6} y={pad.top+yS(v)+4} textAnchor="end"
              fontSize={9} fill={C.text3} fontFamily={mono}>{v.toFixed(0)}</text>
          </g>
        ))}
        {xTicks.map(({d,label}) => (
          <text key={d} x={pad.left+xS(d)} y={pad.top+H+18}
            textAnchor="middle" fontSize={9} fill={C.text3} fontFamily={mono}>{label}</text>
        ))}
        {seriesData.map(({ team }) => {
          const snaps = snapshots[team] || []
          const identity = getDisplayIdentity(team, year)
          const color = identity.color
          const isHov = hovered === team
          const dimmed = hovered && !isHov
          const pts = snaps.map(p => `${pad.left+xS(p.date)},${pad.top+yS(p.rating)}`).join(' ')
          const last = snaps.at(-1)
          return (
            <g key={team} onMouseEnter={() => setHovered(team)} style={{ cursor:'pointer' }}>
              <polyline points={pts} fill="none" stroke={color}
                strokeWidth={isHov ? 3 : 2} strokeLinejoin="round" strokeLinecap="round"
                opacity={dimmed ? 0.15 : 1}
                style={{ transition:'opacity 0.15s, stroke-width 0.15s' }} />
              {last && (
                <text x={pad.left+xS(last.date)+6} y={pad.top+yS(last.rating)+4}
                  fontSize={10} fill={color} opacity={dimmed ? 0.15 : 1}
                  fontFamily={mono} fontWeight="700"
                  style={{ transition:'opacity 0.15s' }}>
                  {identity.abbr}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {/* Team swatches */}
      <div style={{ display:'flex', gap:20, marginTop:14,
        borderTop:`1px solid ${C.border}`, paddingTop:12 }}>
        {seriesData.map(({ team }) => {
          const identity = getDisplayIdentity(team, year)
          const snaps = snapshots[team] || []
          const change = snaps.length > 1
            ? Math.round((snaps.at(-1)?.rating ?? 0) - (snaps[0]?.rating ?? 0)) : null
          const isHov = hovered === team
          return (
            <div key={team}
              style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer',
                opacity: (hovered && !isHov) ? 0.3 : 1, transition:'opacity 0.15s' }}
              onMouseEnter={() => setHovered(team)}
              onMouseLeave={() => setHovered(null)}>
              <div style={{ width:24, height: isHov ? 4 : 3,
                background:identity.color, borderRadius:2 }} />
              <span style={{ fontFamily:mono, fontSize:11, fontWeight: isHov ? 700 : 500,
                color: isHov ? identity.color : C.text2 }}>
                {identity.abbr}{identity.name ? ` · ${identity.name}` : ''}
              </span>
              {change != null && (
                <span style={{ fontFamily:mono, fontSize:10,
                  color: change > 0 ? '#1a7a34' : change < 0 ? '#b91c1c' : C.text3 }}>
                  ({change > 0 ? '+' : ''}{change})
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Playoff result cell
// ---------------------------------------------------------------------------
function PlayoffResult({ r1w, r1l, r2w, r2l, r3w, r3l, fw, fl, pi_w, pi_l }) {
  if (fw >= 4)               return <span style={{ color:C.ut,  fontWeight:700, fontFamily:mono, fontSize:11 }}>Champion</span>;
  if (fw > 0 || fl > 0)      return <span style={{ color:"#444",fontWeight:600, fontFamily:mono, fontSize:11 }}>Finals ({fw}–{fl})</span>;
  if (r3w > 0 || r3l > 0)   return <span style={{ color:"#555",fontFamily:mono, fontSize:11 }}>CF ({r3w}–{r3l})</span>;
  if (r2w > 0 || r2l > 0)   return <span style={{ color:"#666",fontFamily:mono, fontSize:11 }}>CS ({r2w}–{r2l})</span>;
  if (r1w > 0 || r1l > 0)   return <span style={{ color:"#888",fontFamily:mono, fontSize:11 }}>R1 ({r1w}–{r1l})</span>;
  if (pi_w > 0 || pi_l > 0) return <span style={{ color:"#aaa",fontFamily:mono, fontSize:11 }}>Play-In</span>;
  return <span style={{ color:C.border2, fontFamily:mono, fontSize:11 }}>—</span>;
}

// ---------------------------------------------------------------------------
// Sortable TH
// ---------------------------------------------------------------------------
function Th({ col, label, sortCol, sortDir, onSort, align="right" }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)} style={{
      fontFamily: mono, fontSize:10, fontWeight:500,
      color: active ? C.acc : C.text3,
      textTransform:"uppercase", letterSpacing:1,
      padding:"10px 12px", textAlign:align,
      cursor:"pointer", userSelect:"none",
      whiteSpace:"nowrap", background: C.surface,
      borderBottom:`2px solid ${C.border}`,
    }}>
      {label}
      <span style={{ marginLeft:3, color: active ? C.acc : C.border2 }}>
        {active ? (sortDir==="asc" ? "↑" : "↓") : "↕"}
      </span>
    </th>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function SeasonPage({ initialYear = 2026 }) {
  const safeYear = Number(initialYear) || 2026;

  const [year,         setYear]         = useState(safeYear);
  const [variant,      setVariant]      = useState("continelo");
  const [standings,    setStandings]    = useState([]);
  const [games,        setGames]        = useState([]);
  const [accuracy,     setAccuracy]     = useState(null);
  const [chartSeries,  setChartSeries]  = useState([]);
  const [chartFilter,  setChartFilter]  = useState("playoffs");
  const [chartSub,     setChartSub]     = useState("East");
  const [h2hTeam1,     setH2hTeam1]     = useState("BOS");
  const [h2hTeam2,     setH2hTeam2]     = useState("LAL");
  const [chartMode,    setChartMode]    = useState("heatmap");
  const [confFilter,   setConfFilter]   = useState("all");
  const [gameFilter,   setGameFilter]   = useState("all");
  const [gamePage,     setGamePage]     = useState(1);
  const [loading,      setLoading]      = useState(true);
  const [chartLoading, setChartLoading] = useState(true);
  const [activeTab,    setActiveTab]    = useState("standings");
  const [sortCol,      setSortCol]      = useState("final_rating");
  const [sortDir,      setSortDir]      = useState("desc");

  const GAMES_PER_PAGE = 25;
  const allTeams       = Object.keys(TEAM_COLORS).sort();
  const divisions      = getDivisions(year);

  const TAB_COLORS = { standings: C.acc, chart: C.ut, gamelog: C.uo }

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir(col === "team_id" ? "asc" : "desc"); }
  }

  // ---- Standings + accuracy -----------------------------------------------
  useEffect(() => {
    setLoading(true);
    async function load() {
      const { data: rsRows } = await supabase
        .from("season_standings")
        .select("team_id, final_rating")
        .eq("season", year).eq("variant", variant).eq("type", "R");

      const { data: finalRowsP } = await supabase
        .from("season_standings")
        .select("team_id, final_rating")
        .eq("season", year).eq("variant", variant).eq("type", "P");

      const { data: finalRowsR } = await supabase
        .from("season_standings")
        .select("team_id, final_rating")
        .eq("season", year).eq("variant", variant).eq("type", "R");

      const { data: records } = await supabase
        .from("season_records")
        .select("team_id, wins, losses")
        .eq("season", year).eq("variant", variant);

      const { data: preseason } = await supabase
        .from("preseason_ratings")
        .select("team_id, preseason_elo")
        .eq("season", year).eq("variant", variant);

      const { data: poGames } = await supabase
        .from("games")
        .select("team_id, round, result")
        .eq("season", year).eq("variant", variant).eq("type", "P")
        .not("round", "in", '("INS")').limit(5000);

      const rsMap = {}, finalMap = {}, recMap = {}, preMap = {}, poMap = {};

      (rsRows     || []).forEach(r => { rsMap[r.team_id]    = r.final_rating; });
      (finalRowsR || []).forEach(r => { finalMap[r.team_id] = r.final_rating; });
      (finalRowsP || []).forEach(r => { finalMap[r.team_id] = r.final_rating; });
      (records    || []).forEach(r => { recMap[r.team_id]   = { w: r.wins, l: r.losses }; });
      (preseason  || []).forEach(r => { preMap[r.team_id]   = r.preseason_elo; });

      (poGames || []).forEach(row => {
        if (!poMap[row.team_id]) poMap[row.team_id] = { r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,pi_w:0,pi_l:0 };
        const p = poMap[row.team_id], rnd = parseFloat(row.round), win = row.result === 1;
        if (rnd === 0.5) { win ? p.pi_w++ : p.pi_l++; }
        if (rnd === 1)   { win ? p.r1w++  : p.r1l++;  }
        if (rnd === 2)   { win ? p.r2w++  : p.r2l++;  }
        if (rnd === 3)   { win ? p.r3w++  : p.r3l++;  }
        if (rnd === 4)   { win ? p.fw++   : p.fl++;   }
      });

      const allIds = new Set([
        ...Object.keys(rsMap), ...Object.keys(finalMap), ...Object.keys(recMap),
      ]);

      const rows = [...allIds].map(tid => ({
        team_id:       tid,
        preseason_elo: preMap[tid]   ?? null,
        rs_end_rating: rsMap[tid]    ?? null,
        final_rating:  finalMap[tid] ?? null,
        w: recMap[tid]?.w ?? 0, l: recMap[tid]?.l ?? 0,
        ...(poMap[tid] ?? { r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,pi_w:0,pi_l:0 }),
      }));

      setStandings(rows);
      setLoading(false);

      const { data: acc } = await supabase
        .from("season_accuracy")
        .select("game_count, avg_accuracy, avg_brier")
        .eq("season", year).eq("variant", variant).single();

      if (acc) setAccuracy({
        n: acc.game_count,
        pct: (acc.avg_accuracy * 100).toFixed(1),
        brier: Number(acc.avg_brier).toFixed(3),
      });
    }
    load();
  }, [year, variant]);

  // ---- Game log -----------------------------------------------------------
  useEffect(() => {
    setGamePage(1);
    async function loadGames() {
      let q = supabase
        .from("games")
        .select(`game_id, date, team_id, opponent_id, home_away,
                 points_for, points_against, type, round,
                 expected_win_pct, rating_change, result, ot`)
        .eq("season", year).eq("variant", variant).eq("home_away", "H")
        .order("date", { ascending: false }).limit(3000);

      if (gameFilter === "RS") q = q.eq("type", "R");
      if (gameFilter === "PO") q = q.eq("type", "P");

      const { data } = await q;
      setGames(data || []);
    }
    loadGames();
  }, [year, variant, gameFilter]);

  // ---- Chart data ---------------------------------------------------------
  useEffect(() => {
    setChartLoading(true);
    async function loadChart() {
      let teamsToShow = [];

      if (chartMode === "h2h") {
        teamsToShow = [h2hTeam1, h2hTeam2].filter(Boolean);
      } else {
        // Heatmap filters
        if (chartFilter === "playoffs") {
          teamsToShow = standings
            .filter(t => t.r1w > 0 || t.r1l > 0 || t.fw > 0 || t.fl > 0 ||
                         t.r2w > 0 || t.r2l > 0 || t.r3w > 0 || t.r3l > 0 ||
                         t.pi_w > 0 || t.pi_l > 0)
            .map(t => t.team_id);
          if (!teamsToShow.length) { setChartLoading(false); return; }
        } else if (chartFilter === "east") {
          teamsToShow = CONFERENCES.East;
        } else if (chartFilter === "west") {
          teamsToShow = CONFERENCES.West;
        } else if (chartFilter === "all") {
          teamsToShow = allTeams;
        }
      }

      if (!teamsToShow.length) { setChartSeries([]); setChartLoading(false); return; }

      // Paginate to work around Supabase's server-side row limit (often 1000 by default).
      // A full season for 16-30 teams can exceed 1000 rows easily.
      const PAGE = 1000;
      let allRows = [];
      let from = 0;
      while (true) {
        const { data, error } = await supabase
          .from("games")
          .select("team_id, date, post_gm_rate")
          .eq("season", year).eq("variant", variant)
          .in("team_id", teamsToShow)
          .not("post_gm_rate", "is", null)
          .order("date", { ascending: true })
          .range(from, from + PAGE - 1);
        if (error || !data || data.length === 0) break;
        allRows = allRows.concat(data);
        if (data.length < PAGE) break;
        from += PAGE;
      }

      const byTeam = {};
      for (const row of allRows) {
        if (row.post_gm_rate == null) continue
        if (!byTeam[row.team_id]) byTeam[row.team_id] = [];
        byTeam[row.team_id].push({ date: new Date(row.date).getTime(), rating: row.post_gm_rate });
      }

      // Sort heatmap rows by RS end rating descending (from standings, not last game —
      // avoids playoff noise where a team's last game is a loss tanking their rating)
      const rsRatingMap = {};
      for (const t of standings) rsRatingMap[t.team_id] = t.rs_end_rating ?? 0;

      const sorted = teamsToShow
        .filter(t => byTeam[t])
        .sort((a, b) => (rsRatingMap[b] ?? 0) - (rsRatingMap[a] ?? 0));

      setChartSeries(sorted.map(t => ({ team: t, points: byTeam[t] })));
      setChartLoading(false);
    }
    loadChart();
  }, [year, variant, chartFilter, chartMode, h2hTeam1, h2hTeam2, standings]);

  // ---- Sorted + filtered standings ----------------------------------------
  const filteredStandings = standings
    .filter(t => {
      if (confFilter === "East") return CONFERENCES.East.includes(t.team_id);
      if (confFilter === "West") return CONFERENCES.West.includes(t.team_id);
      return true;
    })
    .sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      const av  = a[sortCol] ?? (sortDir === "asc" ? Infinity : -Infinity);
      const bv  = b[sortCol] ?? (sortDir === "asc" ? Infinity : -Infinity);
      if (typeof av === "string") return dir * av.localeCompare(bv);
      return dir * (av - bv);
    });

  const sortedByFinal = [...standings].sort((a,b) => (b.final_rating||0) - (a.final_rating||0));
  const champion     = standings.find(t => t.fw >= 4);
  const finalist     = standings.find(t => t.fl > 0 && t.fw < 4);
  const highestRated = sortedByFinal[0];

  const maxR = Math.max(...standings.map(t => t.final_rating || 0));
  const minR = Math.min(...standings.map(t => t.final_rating || 9999));
  const pagedGames = games.slice((gamePage-1)*GAMES_PER_PAGE, gamePage*GAMES_PER_PAGE);
  const totalPages = Math.ceil(games.length / GAMES_PER_PAGE);

  // =========================================================================
  return (
    <div className="dash">

      {/* NAV */}
      <nav className="nav" style={{ background: C.bg, borderBottom:`1px solid ${C.border2}`, display:'grid', gridTemplateColumns:'1fr auto 1fr', alignItems:'center' }}>
        <div className="nav-brand" style={{ justifySelf:'start' }}>
          <span className="brand-dot"/>
          <span>
            <span style={{ color:'#663399' }}>TR</span><span style={{ color:'#BF5700' }}>AC</span><span style={{ color:'#154733' }}>ER</span>
          </span>
        </div>
        <div className="nav-links">
          <Link href="/"         className="nav-link">Dashboard</Link>
          <span className="nav-link active">Season</span>
          <Link href="/all-time" className="nav-link">All-Time</Link>
          <Link href="/team/ny"  className="nav-link">Teams</Link>
          <Link href="/about"    className="nav-link">About</Link>
        </div>
        <div style={{ justifySelf:'end', display:'flex', alignItems:'center', gap:8 }}>
          <select value={String(year)} onChange={e => setYear(Number(e.target.value))} style={S.select}>
            {[...SEASONS].reverse().map(y => (
              <option key={y} value={String(y)}>{SEASON_LABEL(y)}</option>
            ))}
          </select>
          <div className="variant-toggle">
            <button className={`vt-btn${variant==="continelo" ? " active" : ""}`}
              onClick={() => setVariant("continelo")}>Echo</button>
            <button className={`vt-btn${variant==="elo" ? " active" : ""}`}
              onClick={() => setVariant("elo")}>Pulse</button>
          </div>
        </div>
      </nav>

      {/* COLOR STRIPE */}
      <div className="color-stripe">
        <div className="stripe-acc"/><div className="stripe-ut"/><div className="stripe-uo"/>
      </div>

      {/* HERO */}
      <div className="hero">
        <div>
          <div className="hero-label">{SEASON_LABEL(year)} Season{year === 2026 ? " · Playoffs" : ""}</div>
          <div className="hero-heading">Season Overview</div>
          <div className="hero-sub">
            {variant === "continelo" ? "Echo ratings — carry-forward variant · Updated after every game"
                                     : "Pulse ratings — season-reset variant · Updated after every game"}
          </div>
        </div>
      </div>

      {/* ACCURACY STRIP — sits between hero and tabs, only shown when data is available */}
      {accuracy && (
        <div style={{ borderBottom:`1px solid ${C.border}`, background: C.surface }}>
          <div style={{ maxWidth:1200, margin:"0 auto", padding:"0.75rem 2rem",
            display:"flex", alignItems:"center", gap:24 }}>
            <div>
              <div style={{ fontFamily: mono, fontSize:18, fontWeight:500, color: C.text, lineHeight:1 }}>
                {Number(accuracy.n).toLocaleString()}
              </div>
              <div style={{ fontSize:10, color: C.text3, textTransform:"uppercase",
                letterSpacing:1, marginTop:3, fontFamily: mono }}>Games Rated</div>
            </div>
            <div style={{ width:1, height:32, background: C.border2 }}/>
            <div>
              <div style={{ fontFamily: mono, fontSize:18, fontWeight:500, color: C.text, lineHeight:1 }}>
                {accuracy.pct}%
              </div>
              <div style={{ fontSize:10, color: C.text3, textTransform:"uppercase",
                letterSpacing:1, marginTop:3, fontFamily: mono }}>Accuracy</div>
            </div>
            <div style={{ width:1, height:32, background: C.border2 }}/>
            <div>
              <div style={{ fontFamily: mono, fontSize:18, fontWeight:500, color: C.text, lineHeight:1 }}>
                {accuracy.brier}
              </div>
              <div style={{ fontSize:10, color: C.text3, textTransform:"uppercase",
                letterSpacing:1, marginTop:3, fontFamily: mono }}>Brier Score</div>
            </div>
          </div>
        </div>
      )}

      {/* TABS */}
      <div style={{ borderBottom:`1px solid ${C.border}`, background:"#fff" }}>
        <div style={{ display:"flex", maxWidth:1200, margin:"0 auto", padding:"0 2rem" }}>
          {[
            { id:"standings", label:"Standings" },
            { id:"chart",     label:"Rating Chart" },
            { id:"gamelog",   label:"Game Log" },
          ].map(({ id, label }) => {
            const tabColor = TAB_COLORS[id]
            return (
              <button key={id} onClick={() => setActiveTab(id)} style={{
                fontSize:13, fontFamily: mono, padding:"12px 20px",
                cursor:"pointer", background:"none", border:"none", marginBottom:-1,
                borderBottom: activeTab===id ? `2px solid ${tabColor}` : "2px solid transparent",
                color: activeTab===id ? tabColor : C.text3,
                fontWeight: activeTab===id ? 600 : 400,
                transition:"all 0.15s", whiteSpace:"nowrap",
              }}>{label}</button>
            )
          })}
        </div>
      </div>

      {/* CONTENT */}
      <div style={{ maxWidth:1200, margin:"0 auto", padding:"1.5rem 2rem 4rem" }}>

        {/* ===== STANDINGS ===== */}
        {activeTab === "standings" && (
          <>
            <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16, flexWrap:"wrap" }}>
              {["all","East","West"].map(c => (
                <button key={c}
                  style={{ ...S.filterBtn, ...(confFilter===c ? S.filterActive : {}) }}
                  onClick={() => setConfFilter(c)}>
                  {c==="all" ? "All 30" : c}
                </button>
              ))}
              <span style={{ marginLeft:"auto", fontSize:10, color: C.text3, fontFamily: mono }}>
                Click column headers to sort
              </span>
            </div>

            {loading ? (
              <div style={{ padding:"40px 0", textAlign:"center", color: C.text3,
                fontFamily: mono, fontSize:13 }}>Loading standings…</div>
            ) : (
              <div style={{ overflowX:"auto", borderRadius:12,
                border:`1px solid ${C.border}`, background:"#fff", marginBottom:16 }}>
                <table style={{ width:"100%", borderCollapse:"collapse" }}>
                  <thead>
                    <tr>
                      <th style={{ fontFamily: mono, fontSize:9, fontWeight:500, color: C.text3,
                        textTransform:"uppercase", letterSpacing:1.2, padding:"10px 10px 10px 6px",
                        textAlign:"right", width:36, background: C.surface,
                        borderBottom:`2px solid ${C.border}` }}>#</th>
                      <Th col="team_id"       label="Team"          sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                      {variant==="continelo" && (
                        <Th col="preseason_elo" label="Pre-Season"   sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                      )}
                      <Th col="w"             label="RS Record"     sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                      <Th col="rs_end_rating" label="RS Rating"     sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                      <th style={{ fontFamily: mono, fontSize:9, fontWeight:500, color: C.text3,
                        textTransform:"uppercase", letterSpacing:1.2, padding:"10px 8px",
                        width:60, background: C.surface, borderBottom:`2px solid ${C.border}` }}>
                        Strength
                      </th>
                      <Th col="r1w"           label="Playoff"       sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                      <Th col="final_rating"  label="Final Rating"  sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStandings.map((team, i) => {
                      const isTop3     = i < 3 && confFilter === "all";
                      const isChamp    = team.fw >= 4;
                      const barPct     = maxR > minR ? ((team.final_rating-minR)/(maxR-minR))*100 : 50;
                      const identity   = getDisplayIdentity(team.team_id, year);
                      const teamColor  = identity.color || tc(team.team_id);
                      const secColor   = ts(team.team_id);
                      const fillColor  = team.team_id === 'BRK' ? tt(team.team_id) : teamColor;
                      const rowGradient = `linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`;

                      return (
                        <tr key={team.team_id}
                          style={{
                            borderBottom:`1px solid ${C.border}`,
                            borderLeft:`4px solid ${fillColor}`,
                            background: rowGradient,
                            transition:"opacity 0.1s",
                          }}
                          onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
                          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                        >
                          {/* Rank */}
                          <td style={{ textAlign:"right", padding:"0 10px 0 6px",
                            fontFamily: mono, fontSize:13, fontWeight:700,
                            color: isTop3 ? '#fff' : 'rgba(255,255,255,0.5)', width:36 }}>
                            {i+1}
                          </td>
                          {/* Team */}
                          <td style={{ padding:"10px 8px" }}>
                            <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                              <div style={{ width:34, display:"flex", alignItems:"center",
                                justifyContent:"center", flexShrink:0 }}>
                                <TeamLogo team_id={team.team_id} season={year} size={28} />
                              </div>
                              <div>
                                <div style={{ fontSize:13, fontWeight:700, color: secColor, lineHeight:1.2 }}>
                                  {identity.name
                                    ? identity.name
                                    : (TEAM_COLORS[team.team_id] ? getTeamFullName(team.team_id) : team.team_id)}
                                </div>
                                {identity.name && (
                                  <div style={{ fontSize:10, color:"rgba(255,255,255,0.55)",
                                    fontStyle:"italic", marginTop:2, fontFamily: mono }}>
                                    now: {getTeamFullName(team.team_id)}
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                          {/* Pre-Season */}
                          {variant==="continelo" && (
                            <td style={{ padding:"0 12px", fontFamily: mono, fontSize:12,
                              textAlign:"right", color: C.text2 }}>
                              {team.preseason_elo ? fmt1(team.preseason_elo) : "—"}
                            </td>
                          )}
                          {/* W–L record (combined) */}
                          <td style={{ padding:"0 12px", fontFamily: mono, fontSize:12,
                            fontWeight:500, color: C.text, textAlign:"right", whiteSpace:"nowrap" }}>
                            {team.w}–{team.l}
                          </td>
                          {/* RS Rating */}
                          <td style={{ padding:"0 16px", fontFamily: mono, fontSize:14,
                            fontWeight:700, color: C.text, textAlign:"right", whiteSpace:"nowrap" }}>
                            {fmt1(team.rs_end_rating)}
                          </td>
                          {/* Strength bar — compact, matches Dashboard width */}
                          <td style={{ padding:"0 8px", width:80 }}>
                            <div style={{ height:4, background:"rgba(0,0,0,0.12)", borderRadius:2, width:50 }}>
                              <div style={{ width:`${barPct}%`, height:4, borderRadius:2,
                                background: isChamp ? C.ut : fillColor }} />
                            </div>
                          </td>
                          {/* Playoff */}
                          <td style={{ padding:"0 10px" }}>
                            <PlayoffResult {...team} />
                          </td>
                          {/* Final Rating */}
                          <td style={{ textAlign:"right", padding:"0 16px",
                            fontFamily: mono, fontSize:14, fontWeight:700,
                            color: C.text, whiteSpace:"nowrap" }}>
                            {fmt1(team.final_rating)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* ===== CHART ===== */}
        {activeTab === "chart" && (
          <>
            {/* Season summary strip */}
            {!loading && standings.length > 0 && (
              <div style={{ display:"flex", alignItems:"center", gap:24,
                background:"#fff", border:`1px solid ${C.border}`,
                borderRadius:12, padding:"16px 20px", marginBottom:20, flexWrap:"wrap" }}>
                {champion && (() => {
                  const id = getDisplayIdentity(champion.team_id, year);
                  return (
                    <div style={{ display:"flex", flexDirection:"column" }}>
                      <div style={{ fontSize:10, color: C.text3, fontFamily: mono,
                        textTransform:"uppercase", letterSpacing:1 }}>Champion</div>
                      <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:4 }}>
                        <TeamLogo team_id={champion.team_id} season={year} size={28} />
                        <span style={{ fontFamily: mono, fontSize:10, fontWeight:700,
                          padding:"2px 7px", borderRadius:4,
                          border:`1.5px solid ${getDisplayIdentity(champion.team_id,year).color}`,
                          color: getDisplayIdentity(champion.team_id,year).color, letterSpacing:0.5 }}>
                          {getDisplayIdentity(champion.team_id,year).abbr}
                        </span>
                        <span style={{ fontFamily: mono, fontSize:16, fontWeight:700, color: C.text }}>
                          {fmt1(champion.final_rating)}
                        </span>
                        <span style={{ fontFamily: mono, fontSize:11, color: C.text3 }}>
                          {fmtRecord(champion.w, champion.l)}
                        </span>
                      </div>
                    </div>
                  );
                })()}
                {finalist && (() => {
                  const id = getDisplayIdentity(finalist.team_id, year);
                  return (
                    <div style={{ display:"flex", flexDirection:"column" }}>
                      <div style={{ fontSize:10, color: C.text3, fontFamily: mono,
                        textTransform:"uppercase", letterSpacing:1 }}>🥈 Finalist</div>
                      <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:4 }}>
                        <TeamLogo team_id={finalist.team_id} season={year} size={28} />
                        <span style={{ fontFamily: mono, fontSize:10, fontWeight:700,
                          padding:"2px 7px", borderRadius:4,
                          border:`1.5px solid ${id.color}`, color: id.color, letterSpacing:0.5 }}>
                          {id.abbr}
                        </span>
                        <span style={{ fontFamily: mono, fontSize:16, fontWeight:700, color: C.text }}>
                          {fmt1(finalist.final_rating)}
                        </span>
                        <span style={{ fontFamily: mono, fontSize:11, color: C.text3 }}>
                          {fmtRecord(finalist.w, finalist.l)}
                        </span>
                      </div>
                    </div>
                  );
                })()}
                {highestRated && (() => {
                  const id = getDisplayIdentity(highestRated.team_id, year);
                  return (
                    <div style={{ display:"flex", flexDirection:"column" }}>
                      <div style={{ fontSize:10, color: C.text3, fontFamily: mono,
                        textTransform:"uppercase", letterSpacing:1 }}>📈 Highest Rated</div>
                      <div style={{ display:"flex", alignItems:"center", gap:8, marginTop:4 }}>
                        <TeamLogo team_id={highestRated.team_id} season={year} size={28} />
                        <span style={{ fontFamily: mono, fontSize:10, fontWeight:700,
                          padding:"2px 7px", borderRadius:4,
                          border:`1.5px solid ${id.color}`, color: id.color, letterSpacing:0.5 }}>
                          {id.abbr}
                        </span>
                        <span style={{ fontFamily: mono, fontSize:16, fontWeight:700, color: C.text }}>
                          {fmt1(highestRated.final_rating)}
                        </span>
                        <span style={{ fontFamily: mono, fontSize:11, color: C.text3 }}>
                          {fmtRecord(highestRated.w, highestRated.l)}
                        </span>
                      </div>
                    </div>
                  );
                })()}
                {accuracy && (
                  <div style={{ display:"flex", flexDirection:"column",
                    borderLeft:`1px solid ${C.border}`, paddingLeft:20, marginLeft:4 }}>
                    <div style={{ fontSize:10, color: C.text3, fontFamily: mono,
                      textTransform:"uppercase", letterSpacing:1 }}>Model Accuracy</div>
                    <div style={{ display:"flex", alignItems:"baseline", gap:12, marginTop:4 }}>
                      <span style={{ fontFamily: mono, fontSize:16, fontWeight:700, color: C.text }}>
                        {accuracy.pct}%
                      </span>
                      <span style={{ fontFamily: mono, fontSize:11, color: C.text3 }}>
                        Brier {accuracy.brier}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Mode toggle + filter controls */}
            <div style={{ display:"flex", alignItems:"center", gap:10,
              marginBottom:16, flexWrap:"wrap" }}>

              {/* Heatmap / H2H mode toggle */}
              <div style={{ display:"flex", background:C.border, borderRadius:8,
                overflow:"hidden", border:`1px solid ${C.border2}` }}>
                {[['heatmap','Heatmap'],['h2h','Head-to-Head']].map(([m,l]) => (
                  <button key={m} onClick={() => setChartMode(m)} style={{
                    fontFamily:mono, fontSize:11, padding:'5px 14px', cursor:'pointer',
                    border:'none',
                    background: chartMode===m ? C.acc : 'transparent',
                    color: chartMode===m ? '#fff' : C.text2,
                    transition:'all 0.15s',
                  }}>{l}</button>
                ))}
              </div>

              {/* Heatmap group filter */}
              {chartMode === "heatmap" && (
                <div style={{ display:"flex", gap:6 }}>
                  {[
                    { id:"playoffs", label:"Playoff Teams" },
                    { id:"east",     label:"East" },
                    { id:"west",     label:"West" },
                    { id:"all",      label:"All 30" },
                  ].map(({ id, label }) => (
                    <button key={id}
                      style={{ ...S.filterBtn, ...(chartFilter===id ? S.filterActive : {}) }}
                      onClick={() => setChartFilter(id)}>
                      {label}
                    </button>
                  ))}
                </div>
              )}

              {/* H2H team selectors */}
              {chartMode === "h2h" && (
                <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                  <select value={h2hTeam1} onChange={e=>setH2hTeam1(e.target.value)} style={S.select}>
                    {allTeams.map(t=><option key={t} value={t}>{t}</option>)}
                  </select>
                  <span style={{ color: C.text3, fontFamily: mono, fontSize:12 }}>vs</span>
                  <select value={h2hTeam2} onChange={e=>setH2hTeam2(e.target.value)} style={S.select}>
                    {allTeams.map(t=><option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              )}
            </div>

            <div style={{ background:"#fff", border:`1px solid ${C.border}`,
              borderRadius:12, padding:"20px 24px", marginBottom:24 }}>
              {chartLoading ? (
                <div style={{ padding:"40px 0", textAlign:"center", color: C.text3,
                  fontFamily: mono, fontSize:13 }}>Loading…</div>
              ) : chartMode === "h2h" ? (
                <H2HChart seriesData={chartSeries} year={year} width={860} height={300} />
              ) : (
                <RatingHeatmap seriesData={chartSeries} year={year} standings={standings} />
              )}
            </div>
          </>
        )}

        {/* ===== GAME LOG ===== */}
        {activeTab === "gamelog" && (
          <>
            <div style={{ display:"flex", alignItems:"center",
              justifyContent:"space-between", marginBottom:16 }}>
              <span style={{ fontSize:12, color: C.text3, fontFamily: mono }}>
                {games.length} games
              </span>
              <div style={{ display:"flex", gap:8 }}>
                {[{id:"all",label:"All"},{id:"RS",label:"Regular Season"},{id:"PO",label:"Playoffs"}].map(({id,label})=>(
                  <button key={id}
                    style={{ ...S.filterBtn, ...(gameFilter===id ? S.filterActive : {}) }}
                    onClick={() => setGameFilter(id)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ overflowX:"auto", borderRadius:12,
              border:`1px solid ${C.border}`, background:"#fff" }}>
              <table style={{ width:"100%", borderCollapse:"collapse" }}>
                <thead>
                  <tr style={{ borderBottom:`1px solid ${C.border}` }}>
                    {["Date","Type","Away","Score","Home","Win Prob","Home Δ","OT"].map((h, hi) => (
                      <th key={h} style={{ fontFamily: mono, fontSize:9, fontWeight:500,
                        color: C.text3, textTransform:"uppercase", letterSpacing:1.2,
                        padding:"10px 12px", textAlign: hi === 3 ? "center" : hi >= 5 ? "right" : "left",
                        whiteSpace:"nowrap", background: C.surface,
                        borderBottom:`2px solid ${C.border}` }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedGames.map(g => {
                    const homeWon   = g.result === 1;
                    const isPlayoff = g.type === "P";
                    const roundLbl  = ROUND_LABELS[String(g.round)] || g.round;
                    const homeId    = getDisplayIdentity(g.team_id, year);
                    const awayId    = getDisplayIdentity(g.opponent_id, year);
                    const chg       = g.rating_change;
                    return (
                      <tr key={`${g.game_id}-${g.team_id}`}
                        style={{ borderBottom:`1px solid ${C.border}`, transition:"background 0.1s" }}
                        onMouseEnter={e => e.currentTarget.style.background = C.bg}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                        <td style={{ padding:"10px 12px", fontFamily: mono,
                          fontSize:11, color: C.text3 }}>{fmtDate(g.date)}</td>
                        <td style={{ padding:"10px 12px" }}>
                          <span style={{ fontFamily: mono, fontSize:10, padding:"2px 7px",
                            borderRadius:4, fontWeight:500,
                            background: isPlayoff ? `rgba(191,87,0,0.1)` : `rgba(102,51,153,0.08)`,
                            color: isPlayoff ? C.ut : C.acc }}>
                            {isPlayoff ? roundLbl : "RS"}
                          </span>
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily: mono, fontSize:12,
                          fontWeight: homeWon ? 400 : 700, color: homeWon ? C.text3 : C.text }}>
                          <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                            <TeamLogo team_id={g.opponent_id} season={year} size={18} />
                            {awayId.abbr}
                          </div>
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily: mono,
                          textAlign:"center", fontWeight:600 }}>
                          <span style={{ color: homeWon ? C.text3 : C.text }}>{g.points_against}</span>
                          <span style={{ color: C.border2, margin:"0 4px" }}>–</span>
                          <span style={{ color: homeWon ? C.text : C.text3 }}>{g.points_for}</span>
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily: mono, fontSize:12,
                          fontWeight: homeWon ? 700 : 400, color: homeWon ? C.text : C.text3 }}>
                          <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                            <TeamLogo team_id={g.team_id} season={year} size={18} />
                            {homeId.abbr}
                          </div>
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily: mono,
                          textAlign:"right", fontSize:12, color: C.text3 }}>
                          {g.expected_win_pct != null
                            ? `${Math.round(g.expected_win_pct*100)}% / ${Math.round((1-g.expected_win_pct)*100)}%`
                            : "—"}
                        </td>
                        <td style={{ padding:"10px 12px", textAlign:"right" }}>
                          <span style={{
                            fontFamily: mono, fontSize:12, fontWeight:700,
                            padding:"2px 8px", borderRadius:4, display:"inline-block",
                            color: chgColor(chg),
                            background: chg > 0 ? "rgba(26,122,52,0.12)" : chg < 0 ? "rgba(185,28,28,0.10)" : "transparent",
                          }}>
                            {chgStr(chg)}
                          </span>
                        </td>
                        <td style={{ padding:"10px 12px", fontFamily: mono,
                          textAlign:"right", fontSize:11, color: C.text3 }}>
                          {g.ot ? "OT" : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div style={{ display:"flex", alignItems:"center",
                justifyContent:"center", gap:16, marginTop:20 }}>
                <button
                  style={{ fontFamily: mono, fontSize:12, padding:"6px 14px",
                    border:`1px solid ${C.border2}`, borderRadius:6, background:"#fff",
                    color: C.acc, cursor:"pointer",
                    opacity: gamePage===1 ? 0.4 : 1 }}
                  disabled={gamePage===1}
                  onClick={() => setGamePage(p=>p-1)}>← Prev</button>
                <span style={{ fontSize:12, color: C.text3, fontFamily: mono }}>
                  Page {gamePage} of {totalPages} · {games.length} games
                </span>
                <button
                  style={{ fontFamily: mono, fontSize:12, padding:"6px 14px",
                    border:`1px solid ${C.border2}`, borderRadius:6, background:"#fff",
                    color: C.acc, cursor:"pointer",
                    opacity: gamePage===totalPages ? 0.4 : 1 }}
                  disabled={gamePage===totalPages}
                  onClick={() => setGamePage(p=>p+1)}>Next →</button>
              </div>
            )}
          </>
        )}
      </div>

      <Footer/>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team full names (needed since we removed the old TEAM_INFO lookup)
// ---------------------------------------------------------------------------
const TEAM_FULL_NAMES = {
  ATL:'Atlanta Hawks',          BOS:'Boston Celtics',         BRK:'Brooklyn Nets',
  CHA:'Charlotte Hornets',      CHI:'Chicago Bulls',           CLE:'Cleveland Cavaliers',
  DAL:'Dallas Mavericks',       DEN:'Denver Nuggets',          DET:'Detroit Pistons',
  GS:'Golden State Warriors',   HOU:'Houston Rockets',         IND:'Indiana Pacers',
  LAC:'LA Clippers',            LAL:'Los Angeles Lakers',      MEM:'Memphis Grizzlies',
  MIA:'Miami Heat',             MIL:'Milwaukee Bucks',         MIN:'Minnesota Timberwolves',
  NO:'New Orleans Pelicans',    NY:'New York Knicks',           OKC:'Oklahoma City Thunder',
  ORL:'Orlando Magic',          PHI:'Philadelphia 76ers',      PHX:'Phoenix Suns',
  POR:'Portland Trail Blazers', SA:'San Antonio Spurs',        SAC:'Sacramento Kings',
  TOR:'Toronto Raptors',        UTA:'Utah Jazz',               WAS:'Washington Wizards',
}
function getTeamFullName(abbr) { return TEAM_FULL_NAMES[abbr] || abbr }

// ---------------------------------------------------------------------------
// Shared style tokens
// ---------------------------------------------------------------------------
const S = {
  navLink:    { padding:"6px 12px", color: C.text3, cursor:"pointer", borderRadius:6,
                textDecoration:"none", fontSize:13 },
  select:     { fontFamily: mono, fontSize:12, padding:"5px 10px",
                border:`1px solid ${C.border2}`, borderRadius:8,
                background:"#fff", color: C.text, cursor:"pointer" },
  vtBtn:      { padding:"5px 14px", cursor:"pointer", color: C.text3, border:"none",
                background:"none", fontFamily: mono, fontSize:12 },
  vtActive:   { background: C.acc, color:"#fff" },
  filterBtn:  { fontFamily: mono, fontSize:11, padding:"4px 12px", borderRadius:6,
                border:`1px solid ${C.border2}`, background:"none",
                color: C.text3, cursor:"pointer" },
  filterActive:{ border:`1px solid ${C.acc}`, color: C.acc,
                 background:`rgba(102,51,153,0.07)` },
}

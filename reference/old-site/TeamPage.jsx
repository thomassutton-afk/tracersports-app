"use client";

/**
 * ContinElo — Team Page
 * File: app/team/[abbr]/TeamPage.jsx
 *
 * Shows all-time rating history for a franchise across every season.
 * Hero element: continuous SVG line chart spanning all 30 seasons.
 */

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import Footer from "@/components/Footer";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TEAMS_LIST = [
  "ATL","BOS","BRK","CHA","CHI","CLE","DAL","DEN","DET","GS",
  "HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NO","NY",
  "OKC","ORL","PHI","PHX","POR","SA","SAC","TOR","UTA","WAS",
];

const TEAM_NAMES = {
  ATL:"Atlanta Hawks",        BOS:"Boston Celtics",         BRK:"Brooklyn Nets",
  CHA:"Charlotte Hornets",    CHI:"Chicago Bulls",           CLE:"Cleveland Cavaliers",
  DAL:"Dallas Mavericks",     DEN:"Denver Nuggets",          DET:"Detroit Pistons",
  GS:"Golden State Warriors", HOU:"Houston Rockets",         IND:"Indiana Pacers",
  LAC:"LA Clippers",          LAL:"Los Angeles Lakers",      MEM:"Memphis Grizzlies",
  MIA:"Miami Heat",           MIL:"Milwaukee Bucks",         MIN:"Minnesota Timberwolves",
  NO:"New Orleans Pelicans",  NY:"New York Knicks",          OKC:"Oklahoma City Thunder",
  ORL:"Orlando Magic",        PHI:"Philadelphia 76ers",      PHX:"Phoenix Suns",
  POR:"Portland Trail Blazers",SA:"San Antonio Spurs",       SAC:"Sacramento Kings",
  TOR:"Toronto Raptors",      UTA:"Utah Jazz",               WAS:"Washington Wizards",
};

const TEAM_COLORS = {
  ATL:"#C8102E", BOS:"#007A33", BRK:"#000000", CHA:"#00778B",
  CHI:"#CE1141", CLE:"#860038", DAL:"#0050B5", DEN:"#0E2240",
  DET:"#1D42BA", GS:"#1D428A",  HOU:"#CE1141", IND:"#002D62",
  LAC:"#0C2340", LAL:"#552583", MEM:"#5D76A9", MIA:"#98002E",
  MIL:"#00471B", MIN:"#236192", NO:"#0C2340",  NY:"#1D4289",
  OKC:"#0072CE", ORL:"#0050B5", PHI:"#006BB6", PHX:"#1D1160",
  POR:"#E03A3E", SA:"#9EA2A2",  SAC:"#5A2D81", TOR:"#BA0C2F",
  UTA:"#330072", WAS:"#E31837",
};

// Historical identities — keyed by current team_id
const IDENTITIES = {
  OKC: [
    { through: 2008, abbr: "SEA", name: "Seattle SuperSonics", color: "#00653A" },
  ],
  MEM: [
    { through: 2001, abbr: "VAN", name: "Vancouver Grizzlies", color: "#00B2A9" },
  ],
  BRK: [
    { through: 2012, abbr: "NJN", name: "New Jersey Nets", color: "#002A60" },
  ],
  NO: [
    { through: 2002, abbr: "CHA", name: "Charlotte Hornets", color: "#1D1160" },
    { through: 2013, abbr: "NOH", name: "New Orleans Hornets", color: "#002B5C" },
  ],
  CHA: [
    { through: 2014, abbr: "CHA", name: "Charlotte Bobcats", color: "#F26522" },
  ],
};

function getIdentity(teamId, season) {
  const overrides = IDENTITIES[teamId];
  if (overrides) {
    for (const o of overrides) {
      if (season <= o.through) return { abbr: o.abbr, name: o.name, color: o.color };
    }
  }
  return {
    abbr: teamId,
    name: TEAM_NAMES[teamId] || teamId,
    color: TEAM_COLORS[teamId] || "#663399",
  };
}

const SEASONS = Array.from({ length: 31 }, (_, i) => 1996 + i);
const SEASON_LABEL = (y) => `${y - 1}–${String(y).slice(2)}`;

// ---------------------------------------------------------------------------
// Logo helpers
// Two separate components for the two contexts on this page:
//   CurrentTeamLogo  — always uses /current/, for the hero and nav area
//   HistoricalTeamLogo — uses /historical/ file-driven scan, for season table
//                        and game log where season context matters
// ---------------------------------------------------------------------------

// ── /current/ logo (hero, nav, chart section) ─────────────────────────────
function getCurrentLogoPath(team_id) {
  return `/logos/current/${team_id}.png`;
}

function CurrentTeamLogo({ team_id, size = 28, style = {} }) {
  const [errored, setErrored] = useState(false);
  const color = TEAM_COLORS[team_id] || "#663399";
  if (errored) {
    return (
      <span style={{
        fontFamily: "IBM Plex Mono, monospace",
        fontSize: Math.max(8, size * 0.38),
        fontWeight: 700, padding: "2px 6px", borderRadius: 4,
        border: `1.5px solid ${color}`, color,
        letterSpacing: 0.3, flexShrink: 0, lineHeight: 1,
        display: "inline-flex", alignItems: "center", ...style,
      }}>
        {team_id}
      </span>
    );
  }
  return (
    <img
      src={getCurrentLogoPath(team_id)}
      alt={team_id}
      width={size}
      height={size}
      onError={() => setErrored(true)}
      style={{ width: size, height: size, objectFit: "contain", flexShrink: 0, display: "block", ...style }}
    />
  );
}

// ── /historical/ logo (season-by-season table, game log) ──────────────────
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

function HistoricalTeamLogo({ team_id, season, size = 28, style = {} }) {
  const [errored, setErrored] = useState(false);
  const index = useLogoIndex();
  const identity = getIdentity(team_id, season);
  const color = identity.color;

  if (!index || errored) {
    return (
      <span style={{
        fontFamily: "IBM Plex Mono, monospace",
        fontSize: Math.max(8, size * 0.38),
        fontWeight: 700, padding: "2px 6px", borderRadius: 4,
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
      width={size}
      height={size}
      onError={() => setErrored(true)}
      style={{ width: size, height: size, objectFit: "contain", flexShrink: 0, display: "block", ...style }}
    />
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const fmt1    = (v) => v != null ? Number(v).toFixed(1) : "—";
const fmtRec  = (w, l) => w != null ? `${w}–${l}` : "—";
const fmtDate = (d) => {
  if (!d) return "";
  return new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

// ---------------------------------------------------------------------------
// SVG All-Time Rating Chart
// ---------------------------------------------------------------------------
function AllTimeChart({ points, color, width = 900, height = 320 }) {
  const [hover, setHover] = useState(null); // { point, x, y }

  if (!points || points.length < 2) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center",
        color: "#bbb", fontSize: 13, fontFamily: "IBM Plex Mono, monospace" }}>
        No chart data available
      </div>
    );
  }

  const ratings = points.map(p => p.rating);
  const dates   = points.map(p => p.date);
  const minR    = Math.min(...ratings) - 20;
  const maxR    = Math.max(...ratings) + 20;
  const minD    = Math.min(...dates);
  const maxD    = Math.max(...dates);
  const pad     = { top: 20, right: 24, bottom: 36, left: 56 };
  const W       = width  - pad.left - pad.right;
  const H       = height - pad.top  - pad.bottom;

  const xS = d => ((d - minD) / (maxD - minD || 1)) * W;
  const yS = r => H - ((r - minR) / (maxR - minR || 1)) * H;

  // Y-axis ticks
  const rawStep = (maxR - minR) / 5;
  const step    = Math.ceil(rawStep / 10) * 10 || 10;
  const yTicks  = [];
  for (let v = Math.ceil(minR / step) * step; v <= maxR; v += step) yTicks.push(v);

  // X-axis: one tick per season (first game of each season)
  const seasonTicks = [];
  const seenSeason  = new Set();
  [...points].sort((a, b) => a.date - b.date).forEach(p => {
    if (!seenSeason.has(p.season)) {
      seenSeason.add(p.season);
      // Only label every 5 seasons to avoid crowding
      if ((p.season - 1996) % 5 === 0 || p.season === 2026) {
        seasonTicks.push({ d: p.date, label: String(p.season) });
      }
    }
  });

  // Polyline path
  const sortedPts = [...points].sort((a, b) => a.date - b.date);
  const polylineStr = sortedPts
    .map(p => `${pad.left + xS(p.date)},${pad.top + yS(p.rating)}`)
    .join(" ");

  // Area fill (translucent)
  const areaStr =
    `${pad.left + xS(minD)},${pad.top + H} ` +
    sortedPts.map(p => `${pad.left + xS(p.date)},${pad.top + yS(p.rating)}`).join(" ") +
    ` ${pad.left + xS(maxD)},${pad.top + H}`;

  // Season boundary lines (subtle vertical lines per season start)
  const seasonBoundaries = [];
  const firstBySeason = {};
  sortedPts.forEach(p => {
    if (!firstBySeason[p.season]) firstBySeason[p.season] = p.date;
  });
  Object.values(firstBySeason).forEach(d => {
    seasonBoundaries.push(d);
  });

  // Peak and trough points
  const peak   = sortedPts.reduce((a, b) => b.rating > a.rating ? b : a, sortedPts[0]);
  const trough = sortedPts.reduce((a, b) => b.rating < a.rating ? b : a, sortedPts[0]);

  // Season summaries, chronological — each with its band start and its true
  // end-of-season point (the last game of that season on the actual line)
  const seasonList = [...new Set(sortedPts.map(p => p.season))].sort((a, b) => a - b);
  const seasonSummaries = seasonList.map((season, i) => {
    const seasonPts = sortedPts.filter(p => p.season === season);
    const endPoint  = seasonPts[seasonPts.length - 1];
    return {
      season,
      bandStart: firstBySeason[season],
      bandEnd:   i < seasonList.length - 1 ? firstBySeason[seasonList[i + 1]] : maxD + 1,
      endPoint,
    };
  });

  // Given an SVG-space x, find which season's band the cursor is in and
  // return that season's fixed end-of-season point (not a per-game value)
  function seasonAt(svgX) {
    const targetDate = minD + ((svgX - pad.left) / (W || 1)) * (maxD - minD);
    return (
      seasonSummaries.find(s => targetDate >= s.bandStart && targetDate < s.bandEnd) ||
      seasonSummaries[seasonSummaries.length - 1]
    );
  }

  function handleMove(e) {
    const svgEl = e.currentTarget.ownerSVGElement || e.currentTarget;
    const rect = svgEl.getBoundingClientRect();
    const fracX = (e.clientX - rect.left) / rect.width;
    const svgX = fracX * width;
    const s = seasonAt(svgX);
    setHover({
      point: s.endPoint,
      x: pad.left + xS(s.endPoint.date),
      y: pad.top + yS(s.endPoint.rating),
      bandStart: pad.left + xS(s.bandStart),
      bandEnd: pad.left + xS(Math.min(s.bandEnd, maxD)),
    });
  }

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: "visible" }}
      role="img"
      aria-label={`All-time TRACER rating chart`}
    >
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0.01} />
        </linearGradient>
      </defs>

      {/* Season boundary grid lines */}
      {seasonBoundaries.map((d, i) => (
        <line key={i}
          x1={pad.left + xS(d)} y1={pad.top}
          x2={pad.left + xS(d)} y2={pad.top + H}
          stroke="#ede8dd" strokeWidth={1} strokeDasharray="2,4" />
      ))}

      {/* Y-axis grid lines and labels */}
      {yTicks.map(v => (
        <g key={v}>
          <line
            x1={pad.left} y1={pad.top + yS(v)}
            x2={pad.left + W} y2={pad.top + yS(v)}
            stroke="#ede8dd" strokeWidth={1} />
          <text x={pad.left - 8} y={pad.top + yS(v) + 4}
            textAnchor="end" fontSize={9} fill="#bbb"
            fontFamily="IBM Plex Mono, monospace">
            {v.toFixed(0)}
          </text>
        </g>
      ))}

      {/* 1500 baseline (average) */}
      {1500 >= minR && 1500 <= maxR && (
        <line
          x1={pad.left} y1={pad.top + yS(1500)}
          x2={pad.left + W} y2={pad.top + yS(1500)}
          stroke="#ddd" strokeWidth={1.5} strokeDasharray="6,3"
          opacity={0.6} />
      )}

      {/* X-axis season labels */}
      {seasonTicks.map(({ d, label }) => (
        <text key={label} x={pad.left + xS(d)} y={pad.top + H + 20}
          textAnchor="middle" fontSize={9} fill="#bbb"
          fontFamily="IBM Plex Mono, monospace">
          {label}
        </text>
      ))}

      {/* Area fill */}
      <polygon points={areaStr} fill="url(#areaGrad)" />

      {/* Rating line */}
      <polyline
        points={polylineStr}
        fill="none"
        stroke={color}
        strokeWidth={2.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Peak marker */}
      <circle
        cx={pad.left + xS(peak.date)}
        cy={pad.top + yS(peak.rating)}
        r={4}
        fill={color}
        stroke="#fff"
        strokeWidth={2}
      />
      <text
        x={pad.left + xS(peak.date)}
        y={pad.top + yS(peak.rating) - 10}
        textAnchor="middle"
        fontSize={9}
        fill={color}
        fontFamily="IBM Plex Mono, monospace"
        fontWeight="700"
      >
        {peak.rating.toFixed(0)}
      </text>

      {/* Trough marker (only if meaningfully different from peak) */}
      {peak.rating - trough.rating > 30 && (
        <>
          <circle
            cx={pad.left + xS(trough.date)}
            cy={pad.top + yS(trough.rating)}
            r={3}
            fill="#ccc"
            stroke="#fff"
            strokeWidth={1.5}
          />
          <text
            x={pad.left + xS(trough.date)}
            y={pad.top + yS(trough.rating) + 16}
            textAnchor="middle"
            fontSize={9}
            fill="#bbb"
            fontFamily="IBM Plex Mono, monospace"
          >
            {trough.rating.toFixed(0)}
          </text>
        </>
      )}

      {/* Hover crosshair + highlighted point */}
      {hover && (
        <g style={{ pointerEvents: "none" }}>
          {/* Shaded band across the hovered season's full width */}
          <rect
            x={hover.bandStart} y={pad.top}
            width={Math.max(0, hover.bandEnd - hover.bandStart)} height={H}
            fill={color} opacity={0.05}
          />
          <line
            x1={hover.x} y1={pad.top}
            x2={hover.x} y2={pad.top + H}
            stroke={color} strokeWidth={1} strokeDasharray="3,3" opacity={0.5}
          />
          <circle cx={hover.x} cy={hover.y} r={5} fill={color} stroke="#fff" strokeWidth={2} />

          {/* Tooltip — flips to the left near the right edge so it stays on-canvas */}
          {(() => {
            const boxW = 108, boxH = 46;
            const flip = hover.x + 14 + boxW > pad.left + W;
            const boxX = flip ? hover.x - 14 - boxW : hover.x + 14;
            const boxY = Math.max(pad.top, Math.min(hover.y - boxH / 2, pad.top + H - boxH));
            return (
              <g>
                <rect x={boxX} y={boxY} width={boxW} height={boxH} rx={6}
                  fill="#fff" stroke="#ede8dd" strokeWidth={1}
                  style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.12))" }} />
                <text x={boxX + 10} y={boxY + 17} fontSize={11} fontWeight="700"
                  fill="#1a1a1a" fontFamily="IBM Plex Mono, monospace">
                  {SEASON_LABEL(hover.point.season)}
                </text>
                <text x={boxX + 10} y={boxY + 31} fontSize={10} fill="#888"
                  fontFamily="IBM Plex Mono, monospace">
                  {new Date(hover.point.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })} · Final
                </text>
                <text x={boxX + 10} y={boxY + 42} fontSize={12} fontWeight="700"
                  fill={color} fontFamily="IBM Plex Mono, monospace">
                  {hover.point.rating.toFixed(1)}
                </text>
              </g>
            );
          })()}
        </g>
      )}

      {/* Mouse-tracking overlay — sits on top, drives the hover state */}
      <rect
        x={pad.left} y={pad.top} width={W} height={H}
        fill="transparent"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
        style={{ cursor: "crosshair" }}
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Playoff result cell
// ---------------------------------------------------------------------------
function PlayoffResult({ r1w, r1l, r2w, r2l, r3w, r3l, fw, fl, pi_w, pi_l }) {
  if (fw >= 4) return <span style={{ color: "#BF5700", fontWeight: 700 }}>Champion</span>;
  if (fl > 0)  return <span style={{ color: "#663399", fontWeight: 600 }}>Finals ({fw}–{fl})</span>;
  if (r3w > 0 || r3l > 0) return <span style={{ color: "#444" }}>Conf Finals ({r3w}–{r3l})</span>;
  if (r2w > 0 || r2l > 0) return <span style={{ color: "#666" }}>Conf Semis ({r2w}–{r2l})</span>;
  if (r1w > 0 || r1l > 0) return <span style={{ color: "#888" }}>Round 1 ({r1w}–{r1l})</span>;
  if (pi_w > 0 || pi_l > 0) return <span style={{ color: "#aaa" }}>Play-In</span>;
  return <span style={{ color: "#ddd" }}>—</span>;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function TeamPage({ abbr: initialAbbr = "BOS" }) {
  const abbr = (initialAbbr || "BOS").toUpperCase();

  const [variant,      setVariant]      = useState("continelo");
  const [activeTab,    setActiveTab]    = useState("history");
  const [chartData,    setChartData]    = useState([]);
  const [seasonRows,   setSeasonRows]   = useState([]);
  const [games,        setGames]        = useState([]);
  const [currentInfo,  setCurrentInfo]  = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [chartLoading, setChartLoading] = useState(true);
  const [gameFilter,   setGameFilter]   = useState("all");  // all | RS | PO
  const [gameSeason,   setGameSeason]   = useState("all");
  const [gamePage,     setGamePage]     = useState(1);

  const GAMES_PER_PAGE = 30;
  const teamColor = TEAM_COLORS[abbr] || "#663399";
  const currentName = TEAM_NAMES[abbr] || abbr;

  // ── All-time chart data ──────────────────────────────────────────────────
  useEffect(() => {
    setChartLoading(true);
    async function loadChart() {
      let allPoints = [];
      let from = 0;
      const PAGE = 1000; // Supabase caps rows-per-request at 1000 regardless of requested size
      while (true) {
        const { data, error } = await supabase
          .from("games")
          .select("date, post_gm_rate, season")
          .eq("team_id", abbr)
          .eq("variant", variant)
          .order("date", { ascending: true })
          .range(from, from + PAGE - 1);
        if (error || !data || data.length === 0) break;
        allPoints = allPoints.concat(
          data.map(r => ({
            date:   new Date(r.date + "T12:00:00").getTime(),
            rating: r.post_gm_rate,
            season: r.season,
          }))
        );
        if (data.length < PAGE) break;
        from += PAGE;
      }
      setChartData(allPoints);
      setChartLoading(false);
    }
    loadChart();
  }, [abbr, variant]);

  // ── Season-by-season table + current-season header info ──────────────────
  useEffect(() => {
    setLoading(true);
    async function loadSeasons() {
      // RS end ratings
      const { data: rsRows } = await supabase
        .from("season_standings")
        .select("season, final_rating")
        .eq("team_id", abbr)
        .eq("variant", variant)
        .eq("type", "R");

      // Playoff end ratings
      const { data: poRows } = await supabase
        .from("season_standings")
        .select("season, final_rating")
        .eq("team_id", abbr)
        .eq("variant", variant)
        .eq("type", "P");

      // Win/loss records
      const { data: records } = await supabase
        .from("season_records")
        .select("season, wins, losses")
        .eq("team_id", abbr)
        .eq("variant", variant);

      // Preseason ratings
      const { data: preseason } = await supabase
        .from("preseason_ratings")
        .select("season, preseason_elo")
        .eq("team_id", abbr)
        .eq("variant", variant);

      // Playoff game results per season
      const { data: poGames } = await supabase
        .from("games")
        .select("season, round, result")
        .eq("team_id", abbr)
        .eq("variant", variant)
        .eq("type", "P")
        .not("round", "in", '("INS")')
        .limit(5000);

      // Build maps
      const rsMap  = {};
      const poMap  = {};
      const recMap = {};
      const preMap = {};
      const pfMap  = {};

      (rsRows   || []).forEach(r => { rsMap[r.season]  = r.final_rating; });
      (poRows   || []).forEach(r => { poMap[r.season]  = r.final_rating; });
      (records  || []).forEach(r => { recMap[r.season] = { w: r.wins, l: r.losses }; });
      (preseason|| []).forEach(r => { preMap[r.season] = r.preseason_elo; });

      (poGames || []).forEach(row => {
        if (!pfMap[row.season]) pfMap[row.season] = { r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,pi_w:0,pi_l:0 };
        const p = pfMap[row.season];
        const rnd = parseFloat(row.round);
        const win = row.result === 1;
        if (rnd === 0.5) { win ? p.pi_w++ : p.pi_l++; }
        if (rnd === 1)   { win ? p.r1w++  : p.r1l++;  }
        if (rnd === 2)   { win ? p.r2w++  : p.r2l++;  }
        if (rnd === 3)   { win ? p.r3w++  : p.r3l++;  }
        if (rnd === 4)   { win ? p.fw++   : p.fl++;   }
      });

      // All seasons this team has data for
      const allSeasons = new Set([
        ...Object.keys(rsMap).map(Number),
        ...Object.keys(poMap).map(Number),
        ...Object.keys(recMap).map(Number),
      ]);

      const rows = [...allSeasons].sort((a, b) => b - a).map(season => {
        const pf = pfMap[season] || { r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,pi_w:0,pi_l:0 };
        const rec = recMap[season] || { w: null, l: null };
        const identity = getIdentity(abbr, season);
        return {
          season,
          identity,
          preseason_elo:  preMap[season]  ?? null,
          rs_end_rating:  rsMap[season]   ?? null,
          po_end_rating:  poMap[season]   ?? null,
          final_rating:   poMap[season] ?? rsMap[season] ?? null,
          w: rec.w, l: rec.l,
          ...pf,
          is_champion: pf.fw >= 4,
        };
      });

      setSeasonRows(rows);

      // Current season info for header
      const cur = rows.find(r => r.season === 2026) || rows[0];
      if (cur) {
        setCurrentInfo({
          rating:  cur.final_rating,
          w: cur.w, l: cur.l,
          champions: rows.filter(r => r.is_champion).length,
          peakRating: Math.max(...rows.map(r => r.final_rating || 0)),
          peakSeason: rows.find(r => r.final_rating === Math.max(...rows.map(x => x.final_rating || 0)))?.season,
        });
      }
      setLoading(false);
    }
    loadSeasons();
  }, [abbr, variant]);

  // ── Game log ─────────────────────────────────────────────────────────────
  useEffect(() => {
    setGamePage(1);
    async function loadGames() {
      const PAGE = 1000; // Supabase caps rows-per-request at 1000 regardless of requested size
      let allGames = [];
      let from = 0;
      while (true) {
        let q = supabase
          .from("games")
          .select(`game_id, date, season, opponent_id, home_away,
                   points_for, points_against, type, round,
                   pre_gm_rate, post_gm_rate, expected_win_pct,
                   rating_change, result, ot`)
          .eq("team_id", abbr)
          .eq("variant", variant)
          .order("date", { ascending: false })
          .range(from, from + PAGE - 1);

        if (gameFilter === "RS") q = q.eq("type", "R");
        if (gameFilter === "PO") q = q.eq("type", "P");
        if (gameSeason !== "all") q = q.eq("season", Number(gameSeason));

        const { data, error } = await q;
        if (error || !data || data.length === 0) break;
        allGames = allGames.concat(data);
        if (data.length < PAGE) break;
        from += PAGE;
      }
      setGames(allGames);
    }
    loadGames();
  }, [abbr, variant, gameFilter, gameSeason]);

  // ── Derived ──────────────────────────────────────────────────────────────
  const pagedGames  = games.slice((gamePage - 1) * GAMES_PER_PAGE, gamePage * GAMES_PER_PAGE);
  const totalPages  = Math.ceil(games.length / GAMES_PER_PAGE);

  // Stats from season rows
  const totalWins   = seasonRows.reduce((s, r) => s + (r.w || 0), 0);
  const totalLosses = seasonRows.reduce((s, r) => s + (r.l || 0), 0);
  const championships = seasonRows.filter(r => r.is_champion).length;

  // Chart peak/trough
  const allRatings = chartData.map(p => p.rating);
  const chartPeak  = allRatings.length ? Math.max(...allRatings) : null;
  const chartTrough= allRatings.length ? Math.min(...allRatings) : null;
  const chartCurrent = chartData.length ? chartData[chartData.length - 1]?.rating : null;

  const ROUND_LABELS = {
    RS: "Reg Season", "0.5": "Play-In", INS: "IST Final",
    "1": "R1", "2": "R2", "3": "CF", "4": "Finals",
  };

  // =========================================================================
  return (
    <div className="dash">

      {/* NAV */}
      <nav className="nav" style={{ background:"#F5F0E8", borderBottom:"1px solid #E0D9CE", display:'grid', gridTemplateColumns:'1fr auto 1fr', alignItems:'center' }}>
        <div className="nav-brand" style={{ justifySelf:'start' }}>
          <span className="brand-dot"/>
          <span>
            <span style={{ color: "#663399" }}>TR</span><span style={{ color: "#BF5700" }}>AC</span><span style={{ color: "#154733" }}>ER</span>
          </span>
        </div>
        <div className="nav-links">
          <Link href="/"            className="nav-link">Dashboard</Link>
          <Link href="/season/2026" className="nav-link">Season</Link>
          <Link href="/all-time"    className="nav-link">All-Time</Link>
          <span className="nav-link active">Teams</span>
          <Link href="/about"       className="nav-link">About</Link>
        </div>
        <div style={{ justifySelf:'end', display:'flex', alignItems:'center', gap:8 }}>
          <select
            value={abbr}
            onChange={e => { window.location.href = `/team/${e.target.value.toLowerCase()}`; }}
            style={S.select}
          >
            {TEAMS_LIST.map(t => (
              <option key={t} value={t}>{t} — {TEAM_NAMES[t]}</option>
            ))}
          </select>
          <div className="variant-toggle">
            <button className={`vt-btn${variant === "continelo" ? " active" : ""}`}
              onClick={() => setVariant("continelo")}>Echo</button>
            <button className={`vt-btn${variant === "elo" ? " active" : ""}`}
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
          <div className="hero-label" style={{ color: teamColor }}>Franchise History · 1995–96 to Present</div>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 8 }}>
            <CurrentTeamLogo team_id={abbr} size={56} />
            <div className="hero-heading" style={{ marginBottom: 0 }}>{currentName}</div>
          </div>
          <div className="hero-sub">
            {variant === "continelo" ? "Echo carry-forward variant" : "Pulse season-reset variant"}
          </div>
        </div>

        {/* Hero stat cards */}
        <div style={S.heroCards}>
          <div style={S.heroCard}>
            <div style={{ ...S.heroCardVal, color: teamColor }}>
              {currentInfo ? fmt1(currentInfo.rating) : "—"}
            </div>
            <div style={S.heroCardLbl}>Current Rating</div>
          </div>
          <div style={S.heroDivider} />
          <div style={S.heroCard}>
            <div style={S.heroCardVal}>{currentInfo ? `${currentInfo.w}–${currentInfo.l}` : "—"}</div>
            <div style={S.heroCardLbl}>This Season</div>
          </div>
          <div style={S.heroDivider} />
          <div style={S.heroCard}>
            <div style={{ ...S.heroCardVal, color: championships > 0 ? "#BF5700" : "#1a1a1a" }}>
              {championships > 0 ? `×${championships}` : championships}
            </div>
            <div style={S.heroCardLbl}>Championships</div>
          </div>
          <div style={S.heroDivider} />
          <div style={S.heroCard}>
            <div style={{ ...S.heroCardVal, color: teamColor }}>
              {chartPeak ? chartPeak.toFixed(0) : "—"}
            </div>
            <div style={S.heroCardLbl}>All-Time Peak</div>
          </div>
          <div style={S.heroDivider} />
          <div style={S.heroCard}>
            <div style={S.heroCardVal}>{totalWins.toLocaleString()}–{totalLosses.toLocaleString()}</div>
            <div style={S.heroCardLbl}>All-Time Record</div>
          </div>
        </div>
      </div>

      {/* TAB BAR */}
      <div style={S.tabBar}>
        <div style={S.tabBarInner}>
          {[
            { id: "history", label: "Rating History",    color: "#663399" },
            { id: "seasons", label: "Season-by-Season",  color: "#BF5700" },
            { id: "gamelog", label: "Game Log",          color: "#154733" },
          ].map(({ id, label, color }) => (
            <button key={id} onClick={() => setActiveTab(id)} style={{
              ...S.tab,
              color: activeTab === id ? color : "#999",
              borderBottomColor: activeTab === id ? color : "transparent",
              fontWeight: activeTab === id ? 600 : 400,
            }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* CONTENT */}
      <div style={S.content}>

        {/* ===== RATING HISTORY CHART ===== */}
        {activeTab === "history" && (
          <>
            {/* Peak / trough summary row */}
            {!chartLoading && chartData.length > 0 && (
              <div style={S.summaryRow}>
                <div style={S.summaryCard}>
                  <div style={S.summaryLbl}>All-Time Peak</div>
                  <div style={{ ...S.summaryVal, color: teamColor }}>{chartPeak?.toFixed(1) ?? "—"}</div>
                  <div style={S.summaryDesc}>
                    {chartData.find(p => p.rating === chartPeak)
                      ? SEASON_LABEL(chartData.find(p => p.rating === chartPeak).season)
                      : ""}
                  </div>
                </div>
                <div style={S.summaryCard}>
                  <div style={S.summaryLbl}>All-Time Low</div>
                  <div style={{ ...S.summaryVal, color: "#aaa" }}>{chartTrough?.toFixed(1) ?? "—"}</div>
                  <div style={S.summaryDesc}>
                    {chartData.find(p => p.rating === chartTrough)
                      ? SEASON_LABEL(chartData.find(p => p.rating === chartTrough).season)
                      : ""}
                  </div>
                </div>
                <div style={S.summaryCard}>
                  <div style={S.summaryLbl}>Current</div>
                  <div style={{ ...S.summaryVal, color: teamColor }}>{chartCurrent?.toFixed(1) ?? "—"}</div>
                  <div style={S.summaryDesc}>2025–26 season</div>
                </div>
                <div style={S.summaryCard}>
                  <div style={S.summaryLbl}>Games in Dataset</div>
                  <div style={S.summaryVal}>{chartData.length.toLocaleString()}</div>
                  <div style={S.summaryDesc}>Across 30 seasons</div>
                </div>
              </div>
            )}

            <div style={S.chartCard}>
              {chartLoading ? (
                <div style={S.loading}>Loading all-time rating data…</div>
              ) : (
                <AllTimeChart
                  points={chartData}
                  color={teamColor}
                  width={960}
                  height={340}
                />
              )}
            </div>

            {/* Historical identity legend (if applicable) */}
            {IDENTITIES[abbr] && (
              <div style={S.identityLegend}>
                <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 10, color: "#aaa",
                  textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>
                  Franchise Identities
                </span>
                {[...IDENTITIES[abbr]].reverse().map((id, i, arr) => {
                  const from = i < arr.length - 1 ? arr[i + 1].through + 1 : 1996;
                  return (
                    <span key={id.abbr} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 11, fontWeight: 700,
                        padding: "2px 7px", borderRadius: 4,
                        border: `1.5px solid ${id.color}`, color: id.color }}>
                        {id.abbr}
                      </span>
                      <span style={{ fontSize: 12, color: "#666" }}>
                        {id.name} ({SEASON_LABEL(from)} – {SEASON_LABEL(id.through)})
                      </span>
                    </span>
                  );
                })}
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 11, fontWeight: 700,
                    padding: "2px 7px", borderRadius: 4,
                    border: `1.5px solid ${teamColor}`, color: teamColor }}>
                    {abbr}
                  </span>
                  <span style={{ fontSize: 12, color: "#666" }}>
                    {currentName} ({SEASON_LABEL(
                      (IDENTITIES[abbr]?.[IDENTITIES[abbr].length - 1]?.through ?? 1995) + 1
                    )} – present)
                  </span>
                </span>
              </div>
            )}
          </>
        )}

        {/* ===== SEASON-BY-SEASON TABLE ===== */}
        {activeTab === "seasons" && (
          <>
            {loading ? (
              <div style={S.loading}>Loading season data…</div>
            ) : (
              <div style={S.tableWrap}>
                <table style={S.table}>
                  <thead>
                    <tr style={S.thead}>
                      <th style={{ ...S.th, textAlign: "left" }}>Season</th>
                      <th style={{ ...S.th, textAlign: "left" }}>Identity</th>
                      {variant === "continelo" && <th style={S.th}>Pre-Season</th>}
                      <th style={S.th}>RS Record</th>
                      <th style={S.th}>RS Rating</th>
                      <th style={{ ...S.th, width: 90 }}>Strength</th>
                      <th style={{ ...S.th, textAlign: "left" }}>Playoff Result</th>
                      <th style={S.th}>Final Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seasonRows.map((row, i) => {
                      const isChamp    = row.is_champion;
                      const isCurrent  = row.season === 2026;
                      const rowColor   = row.identity.color;
                      const allFinals  = seasonRows.map(r => r.final_rating || 0);
                      const maxR       = Math.max(...allFinals);
                      const minR       = Math.min(...allFinals);
                      const barPct     = maxR > minR
                        ? ((row.final_rating - minR) / (maxR - minR)) * 100
                        : 50;

                      return (
                        <tr key={row.season}
                          style={{
                            ...S.tr,
                            background: isChamp
                              ? "rgba(191,87,0,0.04)"
                              : isCurrent
                              ? "rgba(102,51,153,0.03)"
                              : "transparent",
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = "#f5f0e8"}
                          onMouseLeave={e => e.currentTarget.style.background = isChamp
                            ? "rgba(191,87,0,0.04)"
                            : isCurrent
                            ? "rgba(102,51,153,0.03)"
                            : "transparent"}
                        >
                          <td style={S.td}>
                            <Link href={`/season/${row.season}`} style={{
                              fontFamily: "IBM Plex Mono, monospace", fontSize: 13,
                              fontWeight: isCurrent ? 700 : 500,
                              color: isCurrent ? "#663399" : "#333",
                              textDecoration: "none",
                            }}>
                              {SEASON_LABEL(row.season)}
                              {isCurrent && (
                                <span style={{ marginLeft: 6, fontSize: 9, color: "#663399",
                                  background: "rgba(102,51,153,0.1)", padding: "1px 5px", borderRadius: 3,
                                  fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>
                                  Now
                                </span>
                              )}
                            </Link>
                          </td>
                          <td style={S.td}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <HistoricalTeamLogo team_id={abbr} season={row.season} size={24} />
                              <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 9,
                                fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                                border: `1.5px solid ${rowColor}`, color: rowColor,
                                letterSpacing: 0.3, flexShrink: 0 }}>
                                {row.identity.abbr}
                              </span>
                              {row.identity.abbr !== abbr && (
                                <span style={{ fontSize: 11, color: "#888", fontStyle: "italic" }}>
                                  {row.identity.name}
                                </span>
                              )}
                            </div>
                          </td>
                          {variant === "continelo" && (
                            <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                              textAlign: "right", color: "#999" }}>
                              {fmt1(row.preseason_elo)}
                            </td>
                          )}
                          <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                            textAlign: "right", color: "#555" }}>
                            {fmtRec(row.w, row.l)}
                          </td>
                          <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                            textAlign: "right", fontWeight: 500, color: "#333" }}>
                            {fmt1(row.rs_end_rating)}
                          </td>
                          {/* Strength bar */}
                          <td style={{ ...S.td, paddingLeft: 12 }}>
                            <div style={{ height: 4, background: "#f0ece3", borderRadius: 2, width: "100%", minWidth: 60 }}>
                              <div style={{ height: 4, borderRadius: 2, width: `${barPct}%`,
                                background: isChamp ? "#BF5700" : rowColor }} />
                            </div>
                          </td>
                          <td style={{ ...S.td, fontSize: 12 }}>
                            <PlayoffResult {...row} />
                          </td>
                          <td style={{ ...S.td, textAlign: "right" }}>
                            <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 14,
                              fontWeight: 700,
                              color: isChamp ? "#BF5700" : i === 0 ? "#663399" : "#1a1a1a" }}>
                              {fmt1(row.final_rating)}
                            </span>

                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* All-time summary footer */}
            {!loading && seasonRows.length > 0 && (
              <div style={S.footerSummary}>
                <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 11, color: "#888" }}>
                  {seasonRows.length} seasons &nbsp;·&nbsp;
                  All-time record: {totalWins.toLocaleString()}–{totalLosses.toLocaleString()} ({((totalWins / (totalWins + totalLosses)) * 100).toFixed(1)}%) &nbsp;·&nbsp;
                  {championships > 0 ? `${championships} championship${championships > 1 ? "s" : ""}` : "No championships"}
                </span>
              </div>
            )}
          </>
        )}

        {/* ===== GAME LOG ===== */}
        {activeTab === "gamelog" && (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
              <span style={{ fontSize: 12, color: "#aaa", fontFamily: "IBM Plex Mono, monospace" }}>
                {games.length.toLocaleString()} games
              </span>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {/* Season filter */}
                <select
                  value={gameSeason}
                  onChange={e => { setGameSeason(e.target.value); setGamePage(1); }}
                  style={S.select}
                >
                  <option value="all">All Seasons</option>
                  {[...SEASONS].reverse().map(y => (
                    <option key={y} value={String(y)}>{SEASON_LABEL(y)}</option>
                  ))}
                </select>
                {/* Type filter */}
                {[{ id: "all", label: "All" }, { id: "RS", label: "Regular Season" }, { id: "PO", label: "Playoffs" }].map(({ id, label }) => (
                  <button key={id}
                    style={{ ...S.filterBtn, ...(gameFilter === id ? S.filterActive : {}) }}
                    onClick={() => { setGameFilter(id); setGamePage(1); }}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div style={S.tableWrap}>
              <table style={S.table}>
                <thead>
                  <tr style={S.thead}>
                    <th style={{ ...S.th, textAlign: "left" }}>Date</th>
                    <th style={{ ...S.th, textAlign: "left" }}>Season</th>
                    <th style={{ ...S.th, textAlign: "left" }}>Type</th>
                    <th style={{ ...S.th, textAlign: "left" }}>Opponent</th>
                    <th style={{ ...S.th, textAlign: "center" }}>H/A</th>
                    <th style={{ ...S.th, textAlign: "center" }}>Score</th>
                    <th style={S.th}>Pre-Game</th>
                    <th style={S.th}>Win Prob</th>
                    <th style={S.th}>Rating Δ</th>
                    <th style={S.th}>Post-Game</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedGames.map(g => {
                    const won     = g.result === 1;
                    const isPlayoff = g.type === "P";
                    const roundLbl  = ROUND_LABELS[String(g.round)] || g.round;
                    const oppColor  = TEAM_COLORS[g.opponent_id] || "#888";

                    return (
                      <tr key={`${g.game_id}-${g.season}`} style={S.tr}
                        onMouseEnter={e => e.currentTarget.style.background = "#f5f0e8"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                        <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                          fontSize: 11, color: "#888" }}>
                          {fmtDate(g.date)}
                        </td>
                        <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace", fontSize: 11 }}>
                          <Link href={`/season/${g.season}`}
                            style={{ color: "#663399", textDecoration: "none", fontWeight: 500 }}>
                            {SEASON_LABEL(g.season)}
                          </Link>
                        </td>
                        <td style={S.td}>
                          <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 9,
                            padding: "2px 6px", borderRadius: 4, fontWeight: 500,
                            background: isPlayoff ? "rgba(191,87,0,0.1)" : "rgba(102,51,153,0.07)",
                            color: isPlayoff ? "#BF5700" : "#663399" }}>
                            {isPlayoff ? roundLbl : "RS"}
                          </span>
                        </td>
                        <td style={S.td}>
                          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                            <HistoricalTeamLogo team_id={g.opponent_id} season={g.season} size={18} />
                            <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 9,
                              fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                              border: `1.5px solid ${oppColor}`, color: oppColor }}>
                              {g.opponent_id}
                            </span>
                          </div>
                        </td>
                        <td style={{ ...S.td, textAlign: "center", fontFamily: "IBM Plex Mono, monospace",
                          fontSize: 11, color: "#888" }}>
                          {g.home_away}
                        </td>
                        <td style={{ ...S.td, textAlign: "center", fontFamily: "IBM Plex Mono, monospace", fontWeight: 600 }}>
                          <span style={{ color: won ? "#1a1a1a" : "#aaa" }}>{g.points_for}</span>
                          <span style={{ color: "#ccc", margin: "0 4px" }}>–</span>
                          <span style={{ color: won ? "#aaa" : "#1a1a1a" }}>{g.points_against}</span>
                        </td>
                        <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                          textAlign: "right", fontSize: 12, color: "#666" }}>
                          {fmt1(g.pre_gm_rate)}
                        </td>
                        <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                          textAlign: "right", fontSize: 12, color: "#888" }}>
                          {g.expected_win_pct != null
                            ? `${Math.round(g.expected_win_pct * 100)}%`
                            : "—"}
                        </td>
                        <td style={{ ...S.td, textAlign: "right" }}>
                          <span style={{
                            fontFamily: "IBM Plex Mono, monospace", fontSize: 11, fontWeight: 600,
                            padding: "2px 7px", borderRadius: 5, display: "inline-block",
                            color: g.rating_change > 0 ? "#2d7a3a" : g.rating_change < 0 ? "#c0392b" : "#888",
                            background: g.rating_change > 0
                              ? "rgba(45,122,58,0.08)"
                              : g.rating_change < 0
                              ? "rgba(192,57,43,0.08)"
                              : "transparent",
                          }}>
                            {g.rating_change > 0 ? "+" : ""}{g.rating_change?.toFixed(1) ?? "—"}
                          </span>
                        </td>
                        <td style={{ ...S.td, fontFamily: "IBM Plex Mono, monospace",
                          textAlign: "right", fontWeight: 700,
                          color: won ? (teamColor) : "#aaa", fontSize: 13 }}>
                          {fmt1(g.post_gm_rate)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div style={S.pagination}>
                <button style={{ ...S.pageBtn, opacity: gamePage === 1 ? 0.35 : 1 }}
                  disabled={gamePage === 1}
                  onClick={() => { setGamePage(1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  ««
                </button>
                <button style={{ ...S.pageBtn, opacity: gamePage === 1 ? 0.35 : 1 }}
                  disabled={gamePage === 1}
                  onClick={() => { setGamePage(p => p - 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  ← Prev
                </button>
                <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 12, color: "#888" }}>
                  Page {gamePage} of {totalPages} · {((gamePage - 1) * GAMES_PER_PAGE + 1).toLocaleString()}–{Math.min(gamePage * GAMES_PER_PAGE, games.length).toLocaleString()} of {games.length.toLocaleString()}
                </span>
                <button style={{ ...S.pageBtn, opacity: gamePage === totalPages ? 0.35 : 1 }}
                  disabled={gamePage === totalPages}
                  onClick={() => { setGamePage(p => p + 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  Next →
                </button>
                <button style={{ ...S.pageBtn, opacity: gamePage === totalPages ? 0.35 : 1 }}
                  disabled={gamePage === totalPages}
                  onClick={() => { setGamePage(totalPages); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  »»
                </button>
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
// Styles
// ---------------------------------------------------------------------------
const S = {
  page:     { background: "#F5F0E8", minHeight: "100vh", fontFamily: "'DM Sans', sans-serif", color: "#1a1a1a" },
  nav:      { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 2rem", height: 56, background: "#FDFAF5", borderBottom: "1px solid #ede8dd", position: "sticky", top: 0, zIndex: 100, gap: 16 },
  brand:    { fontFamily: "'Playfair Display', Georgia, serif", fontSize: 20, fontWeight: 900, textDecoration: "none", display: "flex", alignItems: "center", gap: 8, flexShrink: 0 },
  brandDot: { width: 8, height: 8, borderRadius: "50%", background: "#BF5700", display: "inline-block" },
  navLinks: { display: "flex", gap: 4, fontSize: 13 },
  navLink:  { padding: "6px 12px", color: "#777", cursor: "pointer", borderRadius: 6, textDecoration: "none" },
  select:   { fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, padding: "5px 10px", border: "1px solid #ddd", borderRadius: 8, background: "#fff", color: "#333", cursor: "pointer" },
  variantToggle: { display: "flex", background: "#f0ece3", border: "1px solid #ddd", borderRadius: 8, overflow: "hidden" },
  vtBtn:    { padding: "5px 14px", cursor: "pointer", color: "#888", border: "none", background: "none", fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 },
  vtActive: { background: "#663399", color: "#fff" },
  stripe:   { height: 4 },

  hero:      { padding: "2rem 2rem 1.5rem", borderBottom: "1px solid #ede8dd", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "2rem", maxWidth: 1280, margin: "0 auto", flexWrap: "wrap" },
  eyebrow:   { fontFamily: "IBM Plex Mono, monospace", fontSize: 11, fontWeight: 500, letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 },
  heading:   { fontFamily: "'Playfair Display', Georgia, serif", fontSize: 38, fontWeight: 900, letterSpacing: -1.5, color: "#1a1a1a", margin: 0, lineHeight: 1.05 },
  sub:       { fontSize: 13, color: "#888", marginTop: 8, fontWeight: 300 },

  heroCards:   { display: "flex", alignItems: "center", background: "#FDFAF5", border: "1px solid #ede8dd", borderRadius: 12, overflow: "hidden", flexShrink: 0, flexWrap: "wrap" },
  heroCard:    { padding: "14px 22px", textAlign: "center" },
  heroCardVal: { fontFamily: "IBM Plex Mono, monospace", fontSize: 20, fontWeight: 600, color: "#1a1a1a", lineHeight: 1 },
  heroCardLbl: { fontFamily: "IBM Plex Mono, monospace", fontSize: 10, color: "#aaa", textTransform: "uppercase", letterSpacing: 1, marginTop: 5 },
  heroDivider: { width: 1, alignSelf: "stretch", background: "#ede8dd", margin: "10px 0" },

  tabBar:      { borderBottom: "1px solid #ede8dd", background: "#fff" },
  tabBarInner: { display: "flex", maxWidth: 1280, margin: "0 auto", padding: "0 2rem" },
  tab: {
    fontSize: 13, fontFamily: "IBM Plex Mono, monospace", padding: "12px 20px",
    cursor: "pointer", background: "none", border: "none", marginBottom: -1,
    borderBottom: "2px solid transparent", transition: "all 0.15s", whiteSpace: "nowrap",
  },

  content:    { maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 3rem" },
  loading:    { padding: "40px 0", textAlign: "center", color: "#aaa", fontFamily: "IBM Plex Mono, monospace", fontSize: 13 },

  callout:    { display: "flex", gap: 12, alignItems: "flex-start", background: "rgba(102,51,153,0.05)", border: "1px solid rgba(102,51,153,0.15)", borderRadius: 10, padding: "14px 18px", marginBottom: 20 },

  summaryRow:  { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 20 },
  summaryCard: { background: "#fff", border: "1px solid #ede8dd", borderRadius: 10, padding: "14px 16px" },
  summaryLbl:  { fontFamily: "IBM Plex Mono, monospace", fontSize: 10, color: "#aaa", textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 },
  summaryVal:  { fontFamily: "IBM Plex Mono, monospace", fontSize: 22, fontWeight: 600, color: "#1a1a1a", lineHeight: 1 },
  summaryDesc: { fontSize: 11, color: "#888", marginTop: 5 },

  chartCard:   { background: "#fff", border: "1px solid #ede8dd", borderRadius: 12, padding: "20px 24px", marginBottom: 20, overflowX: "auto" },

  identityLegend: { display: "flex", alignItems: "center", flexWrap: "wrap", gap: 16, padding: "12px 16px",
    background: "#fff", border: "1px solid #ede8dd", borderRadius: 10 },

  tableWrap:  { overflowX: "auto", borderRadius: 12, border: "1px solid #ede8dd", background: "#fff", marginBottom: 16 },
  table:      { width: "100%", borderCollapse: "collapse" },
  thead:      { borderBottom: "1px solid #ede8dd" },
  th:         { fontFamily: "IBM Plex Mono, monospace", fontSize: 10, fontWeight: 500, color: "#aaa", textTransform: "uppercase", letterSpacing: 1, padding: "10px 12px", textAlign: "right", whiteSpace: "nowrap", background: "#fdfaf5" },
  tr:         { borderBottom: "1px solid #f0ece3", transition: "background 0.1s" },
  td:         { padding: "9px 12px", fontSize: 13, verticalAlign: "middle" },

  filterBtn:   { fontFamily: "IBM Plex Mono, monospace", fontSize: 11, padding: "4px 12px", borderRadius: 6, border: "1px solid #ddd", background: "none", color: "#999", cursor: "pointer" },
  filterActive:{ border: "1px solid #663399", color: "#663399", background: "rgba(102,51,153,0.07)" },

  pagination:  { display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 16 },
  pageBtn:     { fontFamily: "IBM Plex Mono, monospace", fontSize: 12, padding: "6px 14px", border: "1px solid #ddd", borderRadius: 8, background: "#fff", color: "#663399", cursor: "pointer" },

  footerSummary: { padding: "12px 16px", background: "#fff", border: "1px solid #ede8dd", borderRadius: 10, textAlign: "center" },
};

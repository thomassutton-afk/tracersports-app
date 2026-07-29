"use client";

/**
 * ContinElo — All-Time Rankings Page
 * File: app/all-time/AllTimeRankings.jsx
 *
 * Queries the games table directly (same pattern as SeasonPage.jsx)
 * since standings may not be fully populated.
 */

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import Footer from "@/components/Footer";

// ---------------------------------------------------------------------------
// Design tokens — kept in sync with Dashboard.jsx
// ---------------------------------------------------------------------------
const C = {
  bg:'#F5F0E8', surface:'#FDFAF5', border:'#EDE8DD', border2:'#E0D9CE',
  text:'#1A1816', text2:'#5C5650', text3:'#9A9490',
  acc:'#663399', ut:'#BF5700', uo:'#154733',
}
const mono  = "'IBM Plex Mono', monospace"
const serif = "'Playfair Display', Georgia, serif"

const S = {
  filterBar:      { background:C.surface, borderBottom:`1px solid ${C.border}`, padding:"0 2rem" },
  filterBarInner: { display:"flex", alignItems:"center", gap:16, flexWrap:"wrap", maxWidth:1280, margin:"0 auto", padding:"12px 0" },
  filterGroup:      { display:"flex", alignItems:"center", gap:8 },
  filterGroupLabel: { fontFamily:mono, fontSize:10, fontWeight:500, color:C.text3, textTransform:"uppercase", letterSpacing:1, flexShrink:0 },
  pillRow:    { display:"flex", gap:6, flexWrap:"wrap" },
  pill:       { fontFamily:mono, fontSize:11, padding:"4px 12px", borderRadius:20, border:`1px solid ${C.border2}`, background:"none", color:C.text2, cursor:"pointer", transition:"all 0.15s", whiteSpace:"nowrap" },
  pillActive: { border:`1px solid ${C.acc}`, color:C.acc, background:`${C.acc}0d`, fontWeight:600 },
  filterDivider: { width:1, height:28, background:C.border, flexShrink:0 },
  searchInput: { fontFamily:mono, fontSize:12, padding:"5px 12px", border:`1px solid ${C.border2}`, borderRadius:20, background:"#fff", color:C.text, outline:"none", width:160 },
  contextBanner:      { background:`${C.acc}08`, borderBottom:`1px solid ${C.acc}1f` },
  contextBannerInner: { maxWidth:1280, margin:"0 auto", padding:"8px 2rem", display:"flex", alignItems:"center" },
  tableSection: { maxWidth:1280, margin:"0 auto", padding:"1.5rem 2rem 2rem" },
  tableWrap: { overflowX:"auto", borderRadius:10, border:`1px solid ${C.border}`, background:"#fff", marginBottom:20 },
  table: { width:"100%", borderCollapse:"collapse" },
  th: { fontFamily:mono, fontSize:9, fontWeight:500, color:C.text3, textTransform:"uppercase", letterSpacing:1.2, padding:"7px 12px", textAlign:"right", whiteSpace:"nowrap", background:"#fff", borderBottom:`2px solid ${C.border}` },
  td: { padding:"9px 12px", fontSize:13, verticalAlign:"middle" },
  loadingState: { padding:"80px 0", display:"flex", flexDirection:"column", alignItems:"center" },
  emptyState:   { padding:"80px 0", display:"flex", flexDirection:"column", alignItems:"center", textAlign:"center" },
  paginationRow: { display:"flex", alignItems:"center", justifyContent:"center", gap:12, marginTop:8 },
  pageBtn: { fontFamily:mono, fontSize:11, padding:"5px 14px", border:`1px solid ${C.border2}`, borderRadius:6, background:"transparent", color:C.acc, cursor:"pointer" },
};

// ---------------------------------------------------------------------------
// Team colors (official primary)
// ---------------------------------------------------------------------------
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

const TEAM_SECONDARY = {
  ATL:'#FDB927', BOS:'#FFFFFF', BRK:'#FFFFFF', CHA:'#1D1160',
  CHI:'#000000', CLE:'#B9975B', DAL:'#002B5E', DEN:'#FEC524',
  DET:'#C8102E', GS:'#FFC72C',  HOU:'#000000', IND:'#FDBB30',
  LAC:'#C8102E', LAL:'#FDB927', MEM:'#F5B112', MIA:'#F9A01B',
  MIL:'#EEE1C6', MIN:'#78BE21', NO:'#B9975B',  NY:'#FF8200',
  OKC:'#F9423A', ORL:'#000000', PHI:'#ED174C', PHX:'#E56020',
  POR:'#000000', SA:'#000000',  SAC:'#000000', TOR:'#000000',
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

const ts = a => TEAM_SECONDARY[a] || TEAM_COLORS[a] || '#663399'
const tt = a => TEAM_TERTIARY[a]  || '#FFFFFF'

const TEAM_NAMES = {
  ATL:"Atlanta Hawks",        BOS:"Boston Celtics",         BRK:"Brooklyn Nets",
  CHA:"Charlotte Hornets",    CHI:"Chicago Bulls",           CLE:"Cleveland Cavaliers",
  DAL:"Dallas Mavericks",     DEN:"Denver Nuggets",          DET:"Detroit Pistons",
  GS:"Golden State Warriors", HOU:"Houston Rockets",         IND:"Indiana Pacers",
  LAC:"LA Clippers",          LAL:"Los Angeles Lakers",      MEM:"Memphis Grizzlies",
  MIA:"Miami Heat",           MIL:"Milwaukee Bucks",         MIN:"Minnesota Timberwolves",
  NO:"New Orleans Pelicans",  NY:"New York Knicks",           OKC:"Oklahoma City Thunder",
  ORL:"Orlando Magic",        PHI:"Philadelphia 76ers",      PHX:"Phoenix Suns",
  POR:"Portland Trail Blazers", SA:"San Antonio Spurs",      SAC:"Sacramento Kings",
  TOR:"Toronto Raptors",      UTA:"Utah Jazz",               WAS:"Washington Wizards",
};

// ---------------------------------------------------------------------------
// Display identity lookup — season-aware abbr, name, and color
// Returns { abbr, name, color } for what to SHOW the user
// ---------------------------------------------------------------------------
const DISPLAY_IDENTITIES = {
  OKC: [
    { through: 2001, abbr:"SEA", name:"Seattle SuperSonics", color:"#00653A" },
    { through: 2008, abbr:"SEA", name:"Seattle SuperSonics", color:"#00653A" },
  ],
  MEM: [
    { through: 2001, abbr:"VAN", name:"Vancouver Grizzlies", color:"#00B2A9" },
  ],
  BRK: [
    { through: 2012, abbr:"NJN", name:"New Jersey Nets",     color:"#002A60" },
  ],
  NO: [
    { through: 2002, abbr:"CHA", name:"Charlotte Hornets",   color:"#1D1160" },
    { through: 2013, abbr:"NOH", name:"New Orleans Hornets", color:"#002B5C" },
  ],
  CHA: [
    { through: 2014, abbr:"CHA", name:"Charlotte Bobcats",   color:"#F26522" },
  ],
  WAS: [
    { through: 1997, abbr:"WAS", name:"Washington Bullets",  color:"#E31837" },
  ],
};

function getDisplayIdentity(team_id, season) {
  const overrides = DISPLAY_IDENTITIES[team_id];
  if (overrides) {
    for (const o of overrides) {
      if (season <= o.through) {
        return { abbr: o.abbr, name: o.name, color: o.color };
      }
    }
  }
  return {
    abbr:  team_id,
    name:  null,
    color: TEAM_COLORS[team_id] || "#663399",
  };
}

// ---------------------------------------------------------------------------
// Historical logo system — mirrors SeasonPage.jsx exactly
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

// Module-level cache so the fetch only happens once per page load.
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

// ---------------------------------------------------------------------------
// TeamLogo component — renders the correct historical logo for team_id + season
// Falls back to a colored abbreviation pill while loading or on image error
// ---------------------------------------------------------------------------
function TeamLogo({ team_id, season, size = 28, style = {} }) {
  const [errored, setErrored] = useState(false);
  const index = useLogoIndex();
  const identity = getDisplayIdentity(team_id, season);
  const color = identity.color;

  if (!index || errored) {
    return (
      <span style={{
        fontFamily: mono,
        fontSize: Math.max(8, size * 0.38),
        fontWeight: 700,
        padding: "2px 6px",
        borderRadius: 4,
        border: `1.5px solid ${color}`,
        color,
        letterSpacing: 0.3,
        flexShrink: 0,
        lineHeight: 1,
        display: "inline-flex",
        alignItems: "center",
        ...style,
      }}>
        {identity.abbr}
      </span>
    );
  }

  const src = resolveHistoricalLogoPath(team_id, season, index);

  return (
    <img
      src={src}
      alt={identity.abbr}
      width={size}
      height={size}
      onError={() => setErrored(true)}
      style={{
        width: size,
        height: size,
        objectFit: "contain",
        flexShrink: 0,
        display: "block",
        filter: 'drop-shadow(0 0 4px rgba(255,255,255,0.95)) drop-shadow(0 0 10px rgba(255,255,255,0.6))',
        ...style,
      }}
    />
  );
}

const SEASON_LABEL = (y) => `${y-1}\u2013${String(y).slice(2)}`;
const fmt1   = (v) => v != null ? Number(v).toFixed(1) : "\u2014";
const fmtRec = (w, l) => w != null ? `${w}\u2013${l}` : "\u2014";

// ---------------------------------------------------------------------------
// Filter options
// ---------------------------------------------------------------------------
const DEPTH_FILTERS = [
  { id:"all",      label:"All Seasons",     desc:"All 930 team-seasons" },
  { id:"playoffs", label:"Made Playoffs",   desc:"Qualified for postseason" },
  { id:"r2",       label:"Won Round 1",     desc:"Advanced to conference semis" },
  { id:"r3",       label:"Won Conf. Semis", desc:"Reached conference finals" },
  { id:"finals",   label:"Won Conf. Finals",desc:"Reached NBA Finals" },
  { id:"champion", label:"Champions Only",  desc:"Won the NBA title" },
];

const DECADES = ["All Eras","1990s","2000s","2010s","2020s"];

// ---------------------------------------------------------------------------
// Playoff result badge
// ---------------------------------------------------------------------------
function PlayoffBadge({ row }) {
  if (row.is_champion)              return <span style={BS.champ}>Champion</span>;
  if (row.po_finals_losses > 0)     return <span style={BS.finals}>Finals ({row.po_finals_wins}&ndash;{row.po_finals_losses})</span>;
  if (row.po_r3_wins > 0 || row.po_r3_losses > 0) return <span style={BS.r3}>Conf Finals ({row.po_r3_wins}&ndash;{row.po_r3_losses})</span>;
  if (row.po_r2_wins > 0 || row.po_r2_losses > 0) return <span style={BS.r2}>Conf Semis ({row.po_r2_wins}&ndash;{row.po_r2_losses})</span>;
  if (row.po_r1_wins > 0 || row.po_r1_losses > 0) return <span style={BS.r1}>Round 1 ({row.po_r1_wins}&ndash;{row.po_r1_losses})</span>;
  if (row.made_playoffs)            return <span style={BS.pi}>Play-In</span>;
  return <span style={BS.none}>&mdash;</span>;
}
const BS = {
  champ:  { color:C.ut,    fontWeight:700, fontSize:12 },
  finals: { color:C.acc,   fontWeight:600, fontSize:12 },
  r3:     { color:C.text2, fontWeight:500, fontSize:12 },
  r2:     { color:C.text2, fontSize:12 },
  r1:     { color:C.text3, fontSize:12 },
  pi:     { color:C.text3, fontSize:12 },
  none:   { color:C.border2, fontSize:12 },
};

// ---------------------------------------------------------------------------
// Sortable column header
// ---------------------------------------------------------------------------
function Th({ col, label, sortCol, sortDir, onSort, align="right" }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)} style={{
      fontFamily:mono, fontSize:9, fontWeight:500,
      color: active ? C.acc : C.text3,
      textTransform:"uppercase", letterSpacing:1.2,
      padding:"7px 12px", textAlign:align,
      cursor:"pointer", userSelect:"none",
      whiteSpace:"nowrap", background:C.surface,
      borderBottom:`2px solid ${C.border}`,
    }}>
      {label}
      <span style={{ marginLeft:3, color: active ? C.acc : C.border2 }}>
        {active ? (sortDir==="asc" ? "\u2191" : "\u2193") : "\u2195"}
      </span>
    </th>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function AllTimeRankings() {
  const [variant,    setVariant]    = useState("continelo");
  const [depth,      setDepth]      = useState("all");
  const [decade,     setDecade]     = useState("All Eras");
  const [teamSearch, setTeamSearch] = useState("");
  const [sortCol,    setSortCol]    = useState("final_rating");
  const [sortDir,    setSortDir]    = useState("desc");
  const [page,       setPage]       = useState(1);
  const [allData,    setAllData]    = useState([]);
  const [loading,    setLoading]    = useState(true);

  const PER_PAGE = 50;

  // --------------------------------------------------------------------------
  // Data fetch — queries season_standings view + season_records view +
  // preseason_ratings table, same pattern as SeasonPage.jsx
  // --------------------------------------------------------------------------
  useEffect(() => {
    setLoading(true);
    setAllData([]);

    async function load() {
      // 1. RS end rating per team per season
      const { data: rsRows } = await supabase
        .from("season_standings")
        .select("team_id, season, final_rating")
        .eq("variant", variant)
        .eq("type", "R");

      // 2. Playoff end rating per team per season
      const { data: poRows } = await supabase
        .from("season_standings")
        .select("team_id, season, final_rating")
        .eq("variant", variant)
        .eq("type", "P");

      // 3. Win/loss records
      const { data: records } = await supabase
        .from("season_records")
        .select("team_id, season, wins, losses")
        .eq("variant", variant);

      // 4. Preseason ratings
      const { data: preseason } = await supabase
        .from("preseason_ratings")
        .select("team_id, season, preseason_elo")
        .eq("variant", variant);

      // 5. Playoff game results
      let poGames = [];
      let poFrom = 0;
      const PO_PAGE = 1000;
      while (true) {
        const { data, error } = await supabase
          .from("games")
          .select("team_id, season, round, result")
          .eq("variant", variant)
          .eq("type", "P")
          .not("round", "in", '("INS")')
          .range(poFrom, poFrom + PO_PAGE - 1);
        if (error || !data || data.length === 0) break;
        poGames = poGames.concat(data);
        if (data.length < PO_PAGE) break;
        poFrom += PO_PAGE;
      }

      // Build lookup maps
      const rsMap  = {};
      const poMap  = {};
      const recMap = {};
      const preMap = {};
      const pfMap  = {};

      (rsRows    || []).forEach(r => { rsMap[`${r.team_id}-${r.season}`]  = r.final_rating; });
      (poRows    || []).forEach(r => { poMap[`${r.team_id}-${r.season}`]  = r.final_rating; });
      (records   || []).forEach(r => { recMap[`${r.team_id}-${r.season}`] = { w:r.wins, l:r.losses }; });
      (preseason || []).forEach(r => { preMap[`${r.team_id}-${r.season}`] = r.preseason_elo; });

      (poGames || []).forEach(row => {
        const key = `${row.team_id}-${row.season}`;
        if (!pfMap[key]) pfMap[key] = { r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,pi_w:0,pi_l:0 };
        const p = pfMap[key];
        const rnd = parseFloat(row.round);
        const win = row.result === 1;
        if (rnd === 0.5) { win ? p.pi_w++ : p.pi_l++; }
        if (rnd === 1)   { win ? p.r1w++  : p.r1l++;  }
        if (rnd === 2)   { win ? p.r2w++  : p.r2l++;  }
        if (rnd === 3)   { win ? p.r3w++  : p.r3l++;  }
        if (rnd === 4)   { win ? p.fw++   : p.fl++;   }
      });

      // Collect all unique team-season keys
      const allKeys = new Set([
        ...Object.keys(rsMap),
        ...Object.keys(poMap),
        ...Object.keys(recMap),
      ]);

      const rows = [...allKeys].map(key => {
        const [team_id, seasonStr] = key.split("-");
        const season = Number(seasonStr);
        const pf  = pfMap[key]  || { r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,pi_w:0,pi_l:0 };
        const rec = recMap[key] || { w:null, l:null };
        const rs_end = rsMap[key] ?? null;
        const po_end = poMap[key] ?? null;
        const is_champion   = pf.fw >= 4;
        const made_playoffs = pf.r1w > 0 || pf.r1l > 0 || pf.pi_w > 0 || pf.pi_l > 0;
        const in_r2         = pf.r2w > 0 || pf.r2l > 0;
        const in_r3         = pf.r3w > 0 || pf.r3l > 0;
        const in_finals     = pf.fw  > 0 || pf.fl  > 0;

        return {
          team_id, season,
          rs_wins: rec.w, rs_losses: rec.l,
          rs_end_rating:  rs_end,
          po_end_rating:  po_end,
          final_rating:   po_end ?? rs_end,
          rating_delta:   (po_end ?? rs_end) != null && rs_end != null ? (po_end ?? rs_end) - rs_end : null,
          preseason_elo:  preMap[key] ?? null,
          po_r1_wins: pf.r1w, po_r1_losses: pf.r1l,
          po_r2_wins: pf.r2w, po_r2_losses: pf.r2l,
          po_r3_wins: pf.r3w, po_r3_losses: pf.r3l,
          po_finals_wins: pf.fw, po_finals_losses: pf.fl,
          is_champion, made_playoffs, in_r2, in_r3, in_finals,
          is_rs_champ: false, is_conf_champ: false,
        };
      });

      // Derive RS champion (best wins per season)
      const seasonBest = {};
      rows.forEach(r => {
        if (r.rs_wins == null) return;
        const cur = seasonBest[r.season];
        if (!cur || r.rs_wins > cur.wins) seasonBest[r.season] = { team_id: r.team_id, wins: r.rs_wins };
      });
      rows.forEach(r => {
        if (seasonBest[r.season]?.team_id === r.team_id) r.is_rs_champ = true;
      });

      setAllData(rows);
      setLoading(false);
    }

    load();
  }, [variant]);

  function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir(col === "team_id" || col === "season" ? "asc" : "desc"); }
    setPage(1);
  }

  const filtered = useMemo(() => {
    let rows = [...allData];

    if (depth === "playoffs") rows = rows.filter(r => r.made_playoffs);
    if (depth === "r2")       rows = rows.filter(r => r.in_r2);
    if (depth === "r3")       rows = rows.filter(r => r.in_r3);
    if (depth === "finals")   rows = rows.filter(r => r.in_finals);
    if (depth === "champion") rows = rows.filter(r => r.is_champion);

    if (decade === "1990s") rows = rows.filter(r => r.season <= 2000);
    if (decade === "2000s") rows = rows.filter(r => r.season > 2000 && r.season <= 2010);
    if (decade === "2010s") rows = rows.filter(r => r.season > 2010 && r.season <= 2020);
    if (decade === "2020s") rows = rows.filter(r => r.season > 2020);

    if (teamSearch.trim()) {
      const q = teamSearch.trim().toLowerCase();
      rows = rows.filter(r =>
        r.team_id.toLowerCase().includes(q) ||
        (TEAM_NAMES[r.team_id]||"").toLowerCase().includes(q) ||
        (getDisplayIdentity(r.team_id, r.season).name||"").toLowerCase().includes(q)
      );
    }

    rows.sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      const av  = a[sortCol] ?? (sortDir === "asc" ? Infinity : -Infinity);
      const bv  = b[sortCol] ?? (sortDir === "asc" ? Infinity : -Infinity);
      if (typeof av === "string") return dir * av.localeCompare(bv);
      return dir * (av - bv);
    });

    return rows;
  }, [allData, depth, decade, teamSearch, sortCol, sortDir]);

  const totalPages = Math.ceil(filtered.length / PER_PAGE);
  const pageRows   = filtered.slice((page-1)*PER_PAGE, page*PER_PAGE);

  const overallRankMap = useMemo(() => {
    const sorted = [...filtered].sort((a,b) => (b.final_rating||0)-(a.final_rating||0));
    const map = {};
    sorted.forEach((r,i) => { map[`${r.team_id}-${r.season}`] = i+1; });
    return map;
  }, [filtered]);

  const currentDepth = DEPTH_FILTERS.find(d => d.id === depth);

  return (
    <div className="dash">

      {/* NAV */}
      <nav className="nav" style={{ background:C.bg, borderBottom:`1px solid ${C.border2}` }}>
        <div className="nav-brand">
          <span className="brand-dot"/>
          <span>
            <span style={{ color:C.acc }}>TR</span><span style={{ color:C.ut }}>AC</span><span style={{ color:C.uo }}>ER</span>
          </span>
        </div>
        <div className="nav-links">
          <Link href="/"            className="nav-link">Dashboard</Link>
          <Link href="/season/2026" className="nav-link">Season</Link>
          <span className="nav-link active">All-Time</span>
          <Link href="/team/ny"     className="nav-link">Teams</Link>
          <Link href="/about"       className="nav-link">About</Link>
        </div>
        <div className="nav-right">
          <div className="variant-toggle">
            <button className={`vt-btn${variant==="continelo" ? " active" : ""}`} onClick={() => { setVariant("continelo"); setPage(1); }}>Echo</button>
            <button className={`vt-btn${variant==="elo"       ? " active" : ""}`} onClick={() => { setVariant("elo");       setPage(1); }}>Pulse</button>
          </div>
        </div>
      </nav>

      <div className="color-stripe">
        <div className="stripe-acc"/><div className="stripe-ut"/><div className="stripe-uo"/>
      </div>

      {/* HERO */}
      <div className="hero">
        <div>
          <div className="hero-label">Historical Record</div>
          <div className="hero-heading">All-Time Rankings</div>
          <div className="hero-sub">
            Every team-season from 1995–96 through 2025–26 &nbsp;·&nbsp;
            {variant === "continelo" ? "Echo carry-forward variant" : "Pulse season-reset variant"}
          </div>
        </div>
      </div>

      {/* FILTER BAR */}
      <div style={S.filterBar}>
        <div style={S.filterBarInner}>
          <div style={S.filterGroup}>
            <span style={S.filterGroupLabel}>Playoff Depth</span>
            <div style={S.pillRow}>
              {DEPTH_FILTERS.map(f => (
                <button key={f.id} title={f.desc}
                  style={{ ...S.pill, ...(depth===f.id?S.pillActive:{}) }}
                  onClick={() => { setDepth(f.id); setPage(1); }}>
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div style={S.filterDivider} />
          <div style={S.filterGroup}>
            <span style={S.filterGroupLabel}>Era</span>
            <div style={S.pillRow}>
              {DECADES.map(d => (
                <button key={d}
                  style={{ ...S.pill, ...(decade===d?S.pillActive:{}) }}
                  onClick={() => { setDecade(d); setPage(1); }}>
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div style={S.filterDivider} />
          <div style={S.filterGroup}>
            <span style={S.filterGroupLabel}>Team</span>
            <input type="text" placeholder="Search team\u2026" value={teamSearch}
              onChange={e => { setTeamSearch(e.target.value); setPage(1); }}
              style={S.searchInput} />
          </div>
          <div style={{ marginLeft:"auto", fontSize:11, color:C.text3, fontFamily:mono, alignSelf:"center", flexShrink:0 }}>
            {loading ? "Loading\u2026" : `${filtered.length.toLocaleString()} results`}
          </div>
        </div>
      </div>

      {depth !== "all" && (
        <div style={S.contextBanner}>
          <div style={S.contextBannerInner}>
            <span style={{ fontFamily:mono, fontSize:11, color:C.acc, fontWeight:600, textTransform:"uppercase", letterSpacing:1 }}>
              {currentDepth.label}
            </span>
            <span style={{ fontSize:12, color:C.text2, marginLeft:12 }}>{currentDepth.desc}</span>
          </div>
        </div>
      )}

      {/* TABLE */}
      <div style={S.tableSection}>
        {loading ? (
          <div style={S.loadingState}>
            <div style={{ fontFamily:mono, fontSize:13, color:C.text3 }}>Loading historical data\u2026</div>
          </div>
        ) : filtered.length === 0 ? (
          <div style={S.emptyState}>
            <div style={{ fontSize:32, marginBottom:12 }}>📭</div>
            <div style={{ fontFamily:mono, fontSize:13, color:C.text3 }}>No results match your filters</div>
            <button style={{ ...S.pill, marginTop:16, background:C.acc, color:"#fff", border:"none" }}
              onClick={() => { setDepth("all"); setDecade("All Eras"); setTeamSearch(""); }}>
              Clear filters
            </button>
          </div>
        ) : (
          <>
            <div style={S.tableWrap}>
              <table style={S.table}>
                <thead>
                  <tr>
                    <th style={{ ...S.th, width:52, textAlign:"center" }}>Rank</th>
                    <Th col="team_id"       label="Team"         sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                    {variant === "continelo" && (
                      <Th col="preseason_elo" label="Pre-Season" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    )}
                    <Th col="rs_wins"       label="RS Record"    sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <Th col="rs_end_rating" label="RS Rating"    sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <th style={{ ...S.th, textAlign:"left", width:170 }}>Playoff Result</th>
                    <Th col="final_rating"  label="Final Rating" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <Th col="rating_delta"  label="Δ Playoff"    sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const overallRank = overallRankMap[`${row.team_id}-${row.season}`];
                    const isChamp  = row.is_champion;
                    const identity = getDisplayIdentity(row.team_id, row.season);
                    const color    = identity.color;
                    const secColor = ts(row.team_id);
                    const fillColor = row.team_id === 'BRK' ? tt(row.team_id) : color;
                    const rowGradient = `linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`;
                    const barPct  = Math.max(5, Math.min(100, ((row.final_rating-1200)/700)*100));

                    return (
                      <tr key={`${row.team_id}-${row.season}`}
                        style={{ borderBottom:`1px solid ${C.border}`, borderLeft:`4px solid ${fillColor}`, background: rowGradient, transition:"opacity 0.1s" }}
                        onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
                        onMouseLeave={e => e.currentTarget.style.opacity = '1'}>



                        <td style={{ ...S.td, textAlign:"center", fontFamily:mono, fontSize:13, fontWeight:700, color:"#fff", width:36 }}>
                          {overallRank}
                        </td>

                        <td style={{ ...S.td, padding:"10px 8px" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                            <div style={{ width:34, display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                              <TeamLogo team_id={row.team_id} season={row.season} size={28} />
                            </div>
                            <div>
                              <Link href={`/season/${row.season}`} style={{ display:"block", fontFamily:mono, fontSize:10, fontWeight:600, color:secColor, opacity:0.75, textDecoration:"none", letterSpacing:0.3, marginBottom:2 }}>
                                {SEASON_LABEL(row.season)}
                              </Link>
                              <div style={{ fontSize:13, fontWeight:700, color:secColor, lineHeight:1.2 }}>
                                {identity.name || TEAM_NAMES[row.team_id] || row.team_id}
                                {identity.name && <div style={{ fontSize:10, color:"rgba(255,255,255,0.6)", fontStyle:"italic", fontWeight:400, marginTop:1 }}>now: {TEAM_NAMES[row.team_id]}</div>}
                              </div>
                            </div>
                          </div>
                        </td>

                        {variant === "continelo" && (
                          <td style={{ ...S.td, fontFamily:mono, fontSize:12, textAlign:"right", color:C.text3 }}>
                            {fmt1(row.preseason_elo)}
                          </td>
                        )}

                        <td style={{ ...S.td, fontFamily:mono, fontSize:12, textAlign:"right", color:C.text2 }}>
                          {fmtRec(row.rs_wins, row.rs_losses)}
                        </td>

                        <td style={{ ...S.td, fontFamily:mono, fontSize:13, textAlign:"right", color:C.text, fontWeight:600 }}>
                          {fmt1(row.rs_end_rating)}
                        </td>

                        <td style={S.td}><PlayoffBadge row={row} /></td>

                        <td style={{ ...S.td, textAlign:"right", padding:"0 16px" }}>
                          <div style={{ fontFamily:mono, fontSize:14, fontWeight:700, color:isChamp?C.ut:overallRank===1?C.acc:C.text }}>
                            {fmt1(row.final_rating)}
                          </div>
                          <div style={{ height:3, background:C.border, borderRadius:2, marginTop:3, width:60, marginLeft:"auto" }}>
                            <div style={{ height:3, borderRadius:2, background:isChamp?C.ut:fillColor, width:`${barPct}%` }} />
                          </div>
                        </td>

                        <td style={{ ...S.td, textAlign:"right", padding:"0 14px" }}>
                          {row.rating_delta != null ? (
                            <span style={{
                              fontFamily:mono, fontSize:12, fontWeight:700,
                              padding:"2px 8px", borderRadius:4, display:"inline-block",
                              color: row.rating_delta > 0 ? "#1a7a34" : row.rating_delta < 0 ? "#b91c1c" : C.text3,
                              background: row.rating_delta > 0 ? "rgba(26,122,52,0.12)" : row.rating_delta < 0 ? "rgba(185,28,28,0.10)" : "transparent",
                            }}>
                              {row.rating_delta > 0 ? "+" : ""}{row.rating_delta.toFixed(1)}
                            </span>
                          ) : (
                            <span style={{ color:C.border2, fontSize:12 }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div style={S.paginationRow}>
                <button style={{ ...S.pageBtn, opacity:page===1?0.35:1 }} disabled={page===1} onClick={() => { setPage(1); window.scrollTo({top:0,behavior:"smooth"}); }}>&#171;&#171;</button>
                <button style={{ ...S.pageBtn, opacity:page===1?0.35:1 }} disabled={page===1} onClick={() => { setPage(p=>p-1); window.scrollTo({top:0,behavior:"smooth"}); }}>&larr; Prev</button>
                <span style={{ fontFamily:mono, fontSize:12, color:C.text3 }}>
                  Page {page} of {totalPages} &nbsp;&middot;&nbsp; {((page-1)*PER_PAGE+1).toLocaleString()}&ndash;{Math.min(page*PER_PAGE,filtered.length).toLocaleString()} of {filtered.length.toLocaleString()}
                </span>
                <button style={{ ...S.pageBtn, opacity:page===totalPages?0.35:1 }} disabled={page===totalPages} onClick={() => { setPage(p=>p+1); window.scrollTo({top:0,behavior:"smooth"}); }}>Next &rarr;</button>
                <button style={{ ...S.pageBtn, opacity:page===totalPages?0.35:1 }} disabled={page===totalPages} onClick={() => { setPage(totalPages); window.scrollTo({top:0,behavior:"smooth"}); }}>&#187;&#187;</button>
              </div>
            )}
          </>
        )}
      </div>

      <Footer/>
    </div>
  );
}

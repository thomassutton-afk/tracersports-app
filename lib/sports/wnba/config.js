/**
 * WNBA league config.
 *
 * VERIFY BEFORE SHIP:
 * - Team colors below are best-effort from general knowledge, NOT pulled from
 *   official brand guides. Toronto Tempo and Portland Fire are 2026 expansion
 *   teams I have low confidence on — treat their colors as placeholders.
 * - Engine tuning (kMax/kMin/kDecay/hca) is copied from NBA as a starting
 *   point. WNBA plays far fewer games per season (44 in 2026, 50 from 2027
 *   vs NBA's 82), so K-factor decay almost certainly needs separate
 *   backtesting against real WNBA results before this is trustworthy.
 * - Playoff format assumed: top 8 overall (no conference bracket, no
 *   play-in) — confirm this is still current before building BracketTab
 *   equivalent for this league.
 */

export const wnbaConfig = {
  id: 'wnba',
  sport: 'basketball',
  label: 'WNBA',
  fullName: "Women's National Basketball Association",

  // Season plays entirely within one calendar year (May–Oct)
  seasonFormat: 'single-year',
  seasonLabel: (year) => `${year}`,

  hasConferences: true,
  hasDivisions: false,

  conferences: ['East', 'West'],
  divisions: null,

  // Top 8 overall make playoffs regardless of conference — single ladder,
  // not two conference brackets like the NBA. Confirm before building UI.
  playoffFormat: {
    type: 'overall-bracket',
    autoSeeds: 8,
    playInSeeds: 0,
    roundsPerConference: null, // not conference-split
  },

  teams: {
    ATL: { name: 'Atlanta Dream',           city: 'Atlanta',       nickname: 'Dream',      conf: 'East', div: null, primary: '#E31837', secondary: '#000000', tertiary: '#C3996B' },
    CHI: { name: 'Chicago Sky',             city: 'Chicago',       nickname: 'Sky',        conf: 'East', div: null, primary: '#418FDE', secondary: '#FFCD00', tertiary: '#00285E' },
    CON: { name: 'Connecticut Sun',         city: 'Uncasville',    nickname: 'Sun',        conf: 'East', div: null, primary: '#E03A3E', secondary: '#0A2240', tertiary: '#FF6600' },
    IND: { name: 'Indiana Fever',           city: 'Indianapolis',  nickname: 'Fever',      conf: 'East', div: null, primary: '#E03A3E', secondary: '#002D62', tertiary: '#FFC633' },
    NY:  { name: 'New York Liberty',        city: 'New York',      nickname: 'Liberty',    conf: 'East', div: null, primary: '#6ECEB2', secondary: '#000000', tertiary: '#FFFFFF' },
    TOR: { name: 'Toronto Tempo',           city: 'Toronto',       nickname: 'Tempo',      conf: 'East', div: null, primary: '#5C2D91', secondary: '#000000', tertiary: '#FFFFFF' }, // VERIFY — new 2026 expansion team
    WAS: { name: 'Washington Mystics',      city: 'Washington',    nickname: 'Mystics',    conf: 'East', div: null, primary: '#E03A3E', secondary: '#002B5C', tertiary: '#FFD200' },

    DAL: { name: 'Dallas Wings',            city: 'Arlington',     nickname: 'Wings',      conf: 'West', div: null, primary: '#002F6C', secondary: '#C4D600', tertiary: '#B1B3B3' },
    GS:  { name: 'Golden State Valkyries',  city: 'San Francisco', nickname: 'Valkyries',  conf: 'West', div: null, primary: '#6F2C91', secondary: '#000000', tertiary: '#C4B7A6' }, // VERIFY — 2025 expansion team
    LV:  { name: 'Las Vegas Aces',          city: 'Las Vegas',     nickname: 'Aces',       conf: 'West', div: null, primary: '#C8102E', secondary: '#000000', tertiary: '#A7A8AA' },
    LA:  { name: 'Los Angeles Sparks',      city: 'Los Angeles',   nickname: 'Sparks',     conf: 'West', div: null, primary: '#702F8A', secondary: '#FFC72C', tertiary: '#000000' },
    MIN: { name: 'Minnesota Lynx',          city: 'Minneapolis',   nickname: 'Lynx',       conf: 'West', div: null, primary: '#236192', secondary: '#78BE21', tertiary: '#9EA2A2' },
    PHX: { name: 'Phoenix Mercury',         city: 'Phoenix',       nickname: 'Mercury',    conf: 'West', div: null, primary: '#201747', secondary: '#E56020', tertiary: '#FFFFFF' },
    POR: { name: 'Portland Fire',           city: 'Portland',      nickname: 'Fire',       conf: 'West', div: null, primary: '#E03A3E', secondary: '#000000', tertiary: '#FFFFFF' }, // VERIFY — new 2026 expansion team
    SEA: { name: 'Seattle Storm',           city: 'Seattle',       nickname: 'Storm',      conf: 'West', div: null, primary: '#2C5234', secondary: '#FEE11A', tertiary: '#003087' },
  },

  // Engine tuning — STARTING POINT ONLY, needs backtesting against real
  // WNBA results before treated as final (see file header note)
  engine: {
    base: 1500,
    alpha: 0.6,
    hca: 84,
    kMax: 58,
    kMin: 6,
    kDecay: 0.30,   // steeper than NBA's 0.15 since ~44-50 games, not 82 — UNVERIFIED, backtest this
    restScale: 8,
    restCap: 16,
    gamesPlayedCap: 44,
    poMult: { RS: 1.00, 1: 1.10, 2: 1.20, 3: 1.35 }, // no play-in/INS tiers — VERIFY round count
    roundLabels: { RS: 'Reg. Season', '1': 'First Round', '2': 'Semifinals', '3': 'WNBA Finals' },
  },
};

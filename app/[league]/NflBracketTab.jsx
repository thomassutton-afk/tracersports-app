"use client";

/**
 * NflBracketTab — 7-seeds-per-conference bracket with a #1 seed bye
 * (leagueConfig.playoffFormat.type === 'conference-bracket-bye').
 *
 * Structurally different from BracketTab.jsx (NBA) in two ways:
 *   1. No play-in — playoffFormat.playInSeeds is always 0 for this format.
 *   2. NFL playoff games are single-elimination (winner-take-all), not a
 *      best-of-N series — so unlike BracketTab's buildBracket() (which
 *      tallies wins across multiple games to find a series winner), each
 *      round here is exactly one game per matchup. buildMatches() below
 *      is the simpler equivalent: one row per (round, team-pair).
 *
 * The #1 seed's bye is handled by simply never drawing a Wild Card game
 * for them — their card first appears normally as one side of their real
 * Divisional-round game, the same as every other team's card appears in
 * whatever round they first play in. No placeholder/BYE card, no special
 * Round 1 slot reserved for them (per-project decision — see HANDOFF).
 *
 * LIVE, not projected: unlike OverallBracketTab.jsx (WNBA), this reads
 * actual completed playoff games (poGames), not standings alone. A round
 * that hasn't been played yet simply doesn't render a matchup for it —
 * no fabricated "who'd win" guess.
 */

import TeamMark from "./TeamMark";

const mono = "var(--font-mono)";
const serif = "var(--font-display)";
const C = {
  acc: "var(--acc)",
  ut: "var(--ut)",
  text: "var(--text)",
  text2: "var(--text2)",
  text3: "var(--text3)",
};

function winPct(t) {
  return t.w / (t.w + t.l || 1);
}

function standingsSort(a, b) {
  const pa = winPct(a), pb = winPct(b);
  if (Math.abs(pa - pb) > 0.0001) return pb - pa;
  return b.w - a.w;
}

// One row per (round, team-pair) — NFL playoff games are single-elimination,
// so unlike BracketTab.jsx's series win-tallying, a "match" here is complete
// as soon as its one game has a result. round comes back from Supabase as
// TEXT ('WC'/'DV'/'CC'/'SB'), compared as plain strings — no float-parsing
// needed the way BracketTab.jsx needs for NBA/WNBA's numeric rounds.
function buildMatches(poGames) {
  const map = {};
  for (const g of poGames) {
    const pair = [g.team_id, g.opponent_id].sort().join("_");
    const key = `${g.round}_${pair}`;
    if (!map[key]) {
      const [a, b] = [g.team_id, g.opponent_id].sort();
      map[key] = { round: g.round, t1: a, t2: b, scores: {}, ratings: {}, winner: null, date: g.date };
    }
    const m = map[key];
    m.scores[g.team_id] = g.points_for;
    m.ratings[g.team_id] = g.post_gm_rate;
    if (g.result === 1) m.winner = g.team_id;
  }
  return Object.values(map);
}

export default function NflBracketTab({ poGames, standings, leagueConfig, season }) {
  const teams = leagueConfig.teams;
  const tc = (abbr) => teams[abbr]?.primary || "#663399";
  const ts = (abbr) => teams[abbr]?.secondary || tc(abbr);
  const tn = (abbr) => teams[abbr]?.name || abbr;
  const roundLabels = leagueConfig.engine?.roundLabels || {};
  const seasonLabel = leagueConfig.seasonLabel ? leagueConfig.seasonLabel(season) : season;

  const conferences = leagueConfig.conferences || [];
  const [confA, confB] = conferences; // e.g. ['AFC', 'NFC']

  const teamsIn = (confName) => standings.filter((t) => teams[t.team_id]?.conf === confName).sort(standingsSort);
  const aSeeded = teamsIn(confA);
  const bSeeded = teamsIn(confB);
  const seedMap = {};
  aSeeded.forEach((t, i) => { seedMap[t.team_id] = i + 1; });
  bSeeded.forEach((t, i) => { seedMap[t.team_id] = i + 1; });

  const matches = buildMatches(poGames);
  const isConf = (confName) => (m) => teams[m.t1]?.conf === confName && teams[m.t2]?.conf === confName;
  const minSeed = (m) => Math.min(seedMap[m.t1] ?? 99, seedMap[m.t2] ?? 99);
  const byRound = (rnd, pred) => matches.filter((m) => m.round === rnd && pred(m)).sort((x, y) => minSeed(x) - minSeed(y));

  const aWC = byRound("WC", isConf(confA));
  const aDV = byRound("DV", isConf(confA));
  const aCC = byRound("CC", isConf(confA));
  const bWC = byRound("WC", isConf(confB));
  const bDV = byRound("DV", isConf(confB));
  const bCC = byRound("CC", isConf(confB));
  const sb = matches.find((m) => m.round === "SB");
  const champion = sb?.winner || null;

  // ── Geometry ────────────────────────────────────────────────────────────
  // Same card dimensions as BracketTab.jsx/OverallBracketTab.jsx, for a
  // consistent look across every league's bracket. Wild Card has 3 games
  // (not the 4-pairs-of-2 shape NBA's Round 1 has), so the grouping/gap
  // pattern here is simpler: just 3 stacked cards, evenly gapped.
  const CARD_H = 76;
  const CARD_GAP = 10;
  const WC_H = CARD_H * 3 + CARD_GAP * 2;

  // Divisional cards center over whichever Wild Card game(s) feed them.
  // Since the #1 seed's bye means Divisional isn't a clean "pair adjacent
  // WC games" reduction the way NBA's R1->R2 is, each DV card is instead
  // positioned by its own minimum seed's rank among the conference's DV
  // games — the lower-seeded matchup (i.e. the one the #1 seed is in)
  // renders first/top, same ordering rule used for every round here.
  const DV_GAP = 28;
  const dvTop = (i) => i * (CARD_H + DV_GAP);
  const DV_H = aDV.length ? dvTop(aDV.length - 1) + CARD_H : CARD_H;

  const ccTop = (WC_H - CARD_H) / 2;
  const BRACKET_H = Math.max(WC_H, CARD_H);

  const CW = { wc: 152, dv: 152, cc: 152, sb: 202 };

  function TeamRow({ abbr, score, isWin, seed, showSeed }) {
    if (!abbr) return <div style={{ height: CARD_H / 2 }} />;
    const color = tc(abbr);
    const sec = ts(abbr);
    return (
      <div
        style={{
          height: CARD_H / 2, display: "flex", alignItems: "center", overflow: "hidden",
          background: isWin ? `${color}cc` : `${color}55`, paddingRight: 6, gap: 4,
        }}
      >
        {showSeed && (
          <div style={{ width: 16, textAlign: "center", fontFamily: mono, fontSize: 11, color: isWin ? sec : "rgba(0,0,0,0.4)", flexShrink: 0, fontWeight: 600 }}>
            {seed ?? ""}
          </div>
        )}
        <div style={{ width: 26, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <TeamMark team={teams[abbr]} teamId={abbr} league={leagueConfig.id} size={18} />
        </div>
        <div
          style={{
            fontFamily: mono, fontSize: 9, fontWeight: 700, padding: "1px 4px", borderRadius: 3,
            flexShrink: 0, minWidth: 28, textAlign: "center",
            border: `1.5px solid ${isWin ? sec : "rgba(0,0,0,0.2)"}`, color: isWin ? sec : "rgba(0,0,0,0.5)",
            background: "transparent", letterSpacing: 0.3,
          }}
        >
          {abbr}
        </div>
        <div style={{ flex: 1 }} />
        {score != null && (
          <div style={{ fontFamily: mono, fontSize: 13, fontWeight: 900, color: isWin ? sec : "rgba(0,0,0,0.45)" }}>
            {score}
          </div>
        )}
      </div>
    );
  }

  function MatchCard({ m, w = 152 }) {
    if (!m) {
      return <div style={{ width: w, background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, height: CARD_H }} />;
    }
    let { t1, t2 } = m;
    const s1 = seedMap[t1] ?? 99, s2 = seedMap[t2] ?? 99;
    if (s2 < s1) [t1, t2] = [t2, t1];
    const isComplete = !!m.winner;
    const winnerColor = isComplete ? tc(m.winner) : null;
    return (
      <div style={{ width: w, borderRadius: 8, overflow: "hidden", border: isComplete ? `1px solid ${winnerColor}50` : "1px solid rgba(0,0,0,0.12)", boxShadow: isComplete ? `0 2px 12px ${winnerColor}20` : "0 1px 3px rgba(0,0,0,0.08)" }}>
        <TeamRow abbr={t1} score={m.scores[t1]} isWin={m.winner === t1} seed={seedMap[t1]} showSeed />
        <div style={{ height: 1, background: isComplete ? `${winnerColor}30` : "rgba(0,0,0,0.08)" }} />
        <TeamRow abbr={t2} score={m.scores[t2]} isWin={m.winner === t2} seed={seedMap[t2]} showSeed />
      </div>
    );
  }

  function ColHeader({ label, w }) {
    return (
      <div style={{ width: w, flexShrink: 0, fontFamily: mono, fontSize: 9, fontWeight: 700, color: "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1.6, paddingBottom: 8, borderBottom: "1px solid rgba(0,0,0,0.15)", marginBottom: 12, textAlign: "center" }}>
        {label}
      </div>
    );
  }

  function ConfBracket({ wc, dv, cc, confColor, confName, mirror }) {
    const cols = [
      <div key="wc" style={{ width: CW.wc, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", gap: CARD_GAP }}>
          {[0, 1, 2].map((i) => <MatchCard key={i} m={wc[i] || null} w={CW.wc} />)}
        </div>
      </div>,
      <div key="dv" style={{ width: CW.dv, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
        {[0, 1].map((i) => (
          <div key={i} style={{ position: "absolute", top: dvTop(i) + (BRACKET_H - DV_H) / 2, left: 0, right: 0 }}>
            <MatchCard m={dv[i] || null} w={CW.dv} />
          </div>
        ))}
      </div>,
      <div key="cc" style={{ width: CW.cc, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
        <div style={{ position: "absolute", top: ccTop, left: 0, right: 0 }}>
          <MatchCard m={cc[0] || null} w={CW.cc} />
        </div>
      </div>,
    ];
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, height: 30, flexDirection: mirror ? "row-reverse" : "row" }}>
          <div style={{ width: 3, height: 16, borderRadius: 2, background: confColor, flexShrink: 0 }} />
          <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 700, color: confColor, textTransform: "uppercase", letterSpacing: 2 }}>
            {confName} Conference
          </span>
          <div style={{ flex: 1, height: 1, background: `${confColor}30` }} />
        </div>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 6, flexDirection: mirror ? "row-reverse" : "row" }}>
          {mirror ? [...cols].reverse() : cols}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <span style={{ fontFamily: mono, fontSize: 9, color: C.text3 }}>Seeds reflect RS standings (win%) · #1 seed has a Wild Card bye</span>
      </div>

      <div style={{ background: "#DDD5C4", borderRadius: 14, padding: "16px 14px 20px", boxShadow: "0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)", border: "1px solid #C8BFB1", position: "relative", overflow: "hidden", width: "fit-content", margin: "0 auto" }}>
        <div style={{ position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)", width: "80%", height: "40%", borderRadius: "50%", background: "radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)", pointerEvents: "none" }} />

        <div style={{ display: "flex", gap: 6, marginBottom: 0 }}>
          <ColHeader label={roundLabels.WC || "Wild Card"} w={CW.wc} />
          <ColHeader label={roundLabels.DV || "Divisional"} w={CW.dv} />
          <ColHeader label={roundLabels.CC || "Conf. Championship"} w={CW.cc} />
          <ColHeader label={roundLabels.SB || "Super Bowl"} w={CW.sb} />
          <ColHeader label={roundLabels.CC || "Conf. Championship"} w={CW.cc} />
          <ColHeader label={roundLabels.DV || "Divisional"} w={CW.dv} />
          <ColHeader label={roundLabels.WC || "Wild Card"} w={CW.wc} />
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "flex-start", position: "relative" }}>
          <ConfBracket wc={aWC} dv={aDV} cc={aCC} confColor="rgba(191,45,45,0.9)" confName={confA} mirror={false} />

          <div style={{ flexShrink: 0, width: CW.sb, alignSelf: "stretch", position: "relative", minHeight: BRACKET_H }}>
            {champion && (
              <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-start", gap: 8 }}>
                <TeamMark team={teams[champion]} teamId={champion} league={leagueConfig.id} size={64} />
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2, marginBottom: 4 }}>
                    {seasonLabel} {leagueConfig.label} Champion
                  </div>
                  <div style={{ fontFamily: serif, fontSize: 20, fontWeight: 900, color: C.text, lineHeight: 1.1 }}>
                    {tn(champion)}
                  </div>
                </div>
              </div>
            )}
            <div style={{ position: "absolute", top: ccTop, left: 0, right: 0 }}>
              <MatchCard m={sb || null} w={CW.sb} />
            </div>
          </div>

          <ConfBracket wc={bWC} dv={bDV} cc={bCC} confColor="rgba(45,80,191,0.9)" confName={confB} mirror={true} />
        </div>

        <div style={{ display: "flex", gap: 20, marginTop: 28, fontFamily: mono, fontSize: 9, color: "rgba(0,0,0,0.35)", flexWrap: "wrap" }}>
          <span># = Conference seed (RS standings)</span>
        </div>
      </div>
    </div>
  );
}

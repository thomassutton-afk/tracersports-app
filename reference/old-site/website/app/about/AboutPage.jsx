"use client";

/**
 * ContinElo — About Page
 * File: app/about/AboutPage.jsx
 */

import Link from "next/link";
import Footer from "@/components/Footer";

function Section({ title, eyebrow, children }) {
  return (
    <div style={S.section}>
      {eyebrow && <div style={S.eyebrow}>{eyebrow}</div>}
      <h2 style={S.sectionHeading}>{title}</h2>
      {children}
    </div>
  );
}

export default function AboutPage() {
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
          <Link href="/team/ny"     className="nav-link">Teams</Link>
          <span className="nav-link active">About</span>
        </div>
        <div style={{ justifySelf:'end' }}/>
      </nav>

      {/* COLOR STRIPE */}
      <div className="color-stripe">
        <div className="stripe-acc"/><div className="stripe-ut"/><div className="stripe-uo"/>
      </div>

      {/* HERO */}
      <div className="hero">
        <div>
          <div className="hero-label">Methodology</div>
          <div className="hero-heading">About TRACER</div>
          <div className="hero-sub">
            A quick rundown of how it works, and who built it
          </div>
        </div>
      </div>

      {/* CONTENT */}
      <div style={S.contentWrap}>

        <Section title="What is TRACER?">
          <p style={S.body}>
            TRACER is an Elo-based rating system for the NBA, calculating a single number
            for every team after every game, going back to the 1995–96 season. An Elo
            rating is a predictive system that calculates the probability of who will win
            a game based on both teams' current ratings.
          </p>
        </Section>

        <div style={S.divider} />

        <Section title="What's the difference between Pulse and Echo?">
          <p style={S.body}>
            Pulse and Echo ratings are identical in calculation. The only difference is
            how they handle season-to-season carryover. The Pulse rating is an in-season
            snapshot only. Every team begins the season with an identical rating, and only
            the games in that season affect it. The Echo rating never fully resets: teams
            carry forward 60% of their rating gap from average, resetting the rest of the
            way toward a league-average baseline.
          </p>
        </Section>

        <div style={S.divider} />

        <Section title="How are the ratings calculated?">
          <p style={S.body}>
            At its core, it's a standard Elo logistic model. Before each game, both teams'
            current ratings are converted into a win probability using a logistic curve.
            Every game moves a team's rating up or down based on the result, how
            surprising it was, and the margin of victory. Other factors also affect the
            size of the change, like home-court advantage, rest, and whether the game went
            to overtime.
          </p>
        </Section>

        <div style={S.divider} />

        <Section title="How accurate is it?">
          <p style={S.body}>
            Going back to the 1995–96 season, the TRACER Echo rating has correctly
            predicted the winner in 66.8% of games, with a Brier score of 0.209. After
            finishing the system, I tested it against the now-defunct NBA Elo ratings that
            used to be available on FiveThirtyEight. Echo beat the FiveThirtyEight model on
            accuracy, a result confirmed by significance testing.
          </p>
          <div style={S.metricsRow}>
            <div style={S.metricCard}>
              <div style={S.metricVal}>66.8%</div>
              <div style={S.metricLabel}>Accuracy</div>
            </div>
            <div style={S.metricCard}>
              <div style={S.metricVal}>0.209</div>
              <div style={S.metricLabel}>Brier Score</div>
            </div>
          </div>
        </Section>

        <div style={S.divider} />

        <Section title="Who makes this?">
          <p style={S.body}>
            TRACER was designed and built by me, TJ Sutton, during the downtime between
            graduation and starting grad school. I graduated from the University of Texas
            with a degree in Sport Management and a minor in sports analytics. The system
            came together as a learn-as-you-go process. I set out to teach myself about
            rating systems, which led me to Elo ratings in sports outside of chess. For the
            first four months, it only lived in Excel spreadsheets on my computer. In May,
            I decided to move it online to share with others. Hope you enjoy!
          </p>
          <p style={S.body}>
            If you have any questions or feedback, you can reach me at{" "}
            <a href="mailto:tracersports4@gmail.com" style={S.link}>
              tracersports4@gmail.com
            </a>
            , or find TRACER on{" "}
            <a href="https://twitter.com/tracersports" style={S.link} target="_blank" rel="noopener noreferrer">
              X
            </a>{" "}
            and{" "}
            <a href="https://instagram.com/tracersports" style={S.link} target="_blank" rel="noopener noreferrer">
              Instagram
            </a>.
          </p>
        </Section>

        {/* CTA */}
        <div style={S.ctaRow}>
          <Link href="/"         style={S.ctaPrimary}>View current ratings →</Link>
          <Link href="/all-time" style={S.ctaSecondary}>Explore all-time rankings →</Link>
        </div>

      </div>

      <Footer/>
    </div>
  );
}

const S = {
  contentWrap: { maxWidth: 760, margin: "0 auto", padding: "0 2rem 4rem" },

  section:        { padding: "3rem 0 0" },
  eyebrow:        { fontFamily: "IBM Plex Mono, monospace", fontSize: 10, fontWeight: 500, color: "#663399", letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 },
  sectionHeading: { fontFamily: "'Playfair Display', Georgia, serif", fontSize: 28, fontWeight: 900, letterSpacing: -0.5, color: "#1a1a1a", margin: "0 0 1.25rem" },
  body:           { fontSize: 15, lineHeight: 1.75, color: "#444", marginBottom: "1.1rem" },
  divider:        { height: 1, background: "#ede8dd", marginTop: "2rem" },
  link:           { color: "#663399", textDecoration: "underline" },

  metricsRow: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, margin: "0.5rem 0 1rem", maxWidth: 400 },
  metricCard: { background: "#fff", border: "1px solid #ede8dd", borderRadius: 12, padding: "16px 20px" },
  metricVal:  { fontFamily: "IBM Plex Mono, monospace", fontSize: 28, fontWeight: 600, color: "#663399", lineHeight: 1 },
  metricLabel:{ fontFamily: "IBM Plex Mono, monospace", fontSize: 11, fontWeight: 500, color: "#aaa", textTransform: "uppercase", letterSpacing: 1, margin: "6px 0 0" },

  ctaRow:      { display: "flex", gap: 12, marginTop: "3rem", paddingTop: "2rem", borderTop: "1px solid #ede8dd" },
  ctaPrimary:  { fontFamily: "IBM Plex Mono, monospace", fontSize: 13, fontWeight: 600, padding: "10px 22px", borderRadius: 8, background: "#663399", color: "#fff", textDecoration: "none" },
  ctaSecondary:{ fontFamily: "IBM Plex Mono, monospace", fontSize: 13, fontWeight: 500, padding: "10px 22px", borderRadius: 8, background: "none", border: "1px solid #663399", color: "#663399", textDecoration: "none" },
};

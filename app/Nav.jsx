"use client";

/**
 * Shared site nav — brand mark + league switcher.
 *
 * Season/All-Time/Teams/About links are intentionally NOT here yet — those
 * pages don't exist in this new structure yet. Add them back in, league-aware
 * (e.g. `/${league}/season/2026`), as each page gets built. Don't add dead
 * links ahead of real pages.
 *
 * The Echo/Pulse rating-variant toggle lives on the Dashboard/Season pages
 * themselves (it's page-level state, not nav-level), so it isn't here.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { getAllLeagueIds, getLeagueConfig } from "@/lib/sports/registry";

export default function Nav() {
  const pathname = usePathname();
  const currentLeague = pathname.split("/")[1]; // "" | "nba" | "wnba" | ...
  const leagueIds = getAllLeagueIds();

  return (
    <>
      <nav className="nav">
        <Link href="/" className="nav-brand">
          <span className="brand-dot" />
          <span>
            <span style={{ color: "#663399" }}>TR</span>
            <span style={{ color: "#BF5700" }}>AC</span>
            <span style={{ color: "#154733" }}>ER</span>
          </span>
        </Link>

        <div className="nav-links" />

        <div className="nav-right">
          <div className="league-switcher">
            {leagueIds.map((id) => {
              const config = getLeagueConfig(id);
              const active = currentLeague === id;
              return (
                <Link
                  key={id}
                  href={`/${id}`}
                  className={`ls-btn${active ? " active" : ""}`}
                >
                  {config.label}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>

      <div className="color-stripe">
        <div className="stripe-acc" />
        <div className="stripe-ut" />
        <div className="stripe-uo" />
      </div>
    </>
  );
}

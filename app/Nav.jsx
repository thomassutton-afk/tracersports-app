"use client";

/**
 * Shared site nav — brand mark, league switcher, and Echo/Pulse variant
 * toggle. All three are shared chrome, live in the URL (league as a path
 * segment, variant as a ?variant= search param) so any page can read the
 * current selection without needing a separate state-management layer.
 *
 * Season/All-Time/Teams/About links are intentionally NOT here yet — those
 * pages don't exist in this new structure yet. Add them back in, league-aware
 * (e.g. `/${league}/season/2026`), as each page gets built. Don't add dead
 * links ahead of real pages.
 */

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { getAllLeagueIds, getLeagueConfig } from "@/lib/sports/registry";

const VARIANTS = [
  { id: "continelo", label: "Echo" },
  { id: "elo", label: "Pulse" },
];

export default function Nav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentLeague = pathname.split("/")[1]; // "" | "nba" | "wnba" | ...
  const currentVariant = searchParams.get("variant") || "continelo";
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
          <div className="variant-toggle">
            {VARIANTS.map((v) => (
              <Link
                key={v.id}
                href={`${pathname}?variant=${v.id}`}
                className={`vt-btn${currentVariant === v.id ? " active" : ""}`}
              >
                {v.label}
              </Link>
            ))}
          </div>
          <div className="league-switcher">
            {leagueIds.map((id) => {
              const config = getLeagueConfig(id);
              const active = currentLeague === id;
              return (
                <Link
                  key={id}
                  href={`/${id}?variant=${currentVariant}`}
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

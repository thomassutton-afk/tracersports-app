/**
 * TRACER Sports — Season Page Route
 * File: app/season/[year]/page.js
 */

import SeasonPage from "./SeasonPage";

export async function generateStaticParams() {
  return Array.from({ length: 31 }, (_, i) => ({
    year: String(1996 + i),
  }));
}

export async function generateMetadata({ params }) {
  const { year } = await params;
  const y = Number(year);
  const label = `${y - 1}–${String(y).slice(2)}`;
  return {
    title: `${label} Season | TRACER Sports`,
    description: `Full standings, rating chart, and game log for the ${label} NBA season — TRACER power ratings.`,
  };
}

export default async function Page({ params }) {
  const { year } = await params;
  return <SeasonPage initialYear={Number(year)} />;
}
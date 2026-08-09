/**
 * GET /api/logo-index?league=nba
 *
 * Scans public/logos/historical/ for files named `{CODE}_{year}.png` and
 * returns { [CODE]: [year, year, ...] } — the manifest lib/historicalIdentity.js's
 * resolveHistoricalLogoPath() picks the best-matching file from. File-driven
 * on purpose (same as the old site): drop a new logo file in, it shows up,
 * no manifest to hand-edit.
 *
 * League scoping / a real collision risk worth knowing about: several
 * abbreviations exist in BOTH NBA and WNBA (DAL, DET, ORL, UTA, WAS, ATL,
 * CHI, IND, MIN, PHX, POR, TOR...). The 117 files already in
 * public/logos/historical/ today are all NBA and are stored flat (no
 * subfolder) — that's fine as long as WNBA has zero historical logos, but
 * the moment a WNBA file with a colliding code lands in that same flat
 * folder, a query for that code could resolve to the wrong league's team.
 * This route checks for a league subfolder (public/logos/historical/{league}/)
 * FIRST and only falls back to the flat folder if that subfolder doesn't
 * exist — so: NBA's existing flat files need no changes, but any future
 * WNBA historical logos should go in public/logos/historical/wnba/ rather
 * than flat, to stay collision-safe.
 */
import { readdir } from "fs/promises";
import path from "path";

const FILE_PATTERN = /^([A-Za-z0-9]+)_(\d{4})\.png$/i;

async function buildIndexFromDir(dir) {
  let files;
  try {
    files = await readdir(dir);
  } catch {
    return null; // directory doesn't exist
  }

  const index = {};
  for (const file of files) {
    const match = file.match(FILE_PATTERN);
    if (!match) continue;
    const [, code, year] = match;
    (index[code.toUpperCase()] ??= []).push(Number(year));
  }
  return index;
}

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const league = searchParams.get("league");

  const historicalRoot = path.join(process.cwd(), "public", "logos", "historical");

  let index = null;
  if (league) {
    index = await buildIndexFromDir(path.join(historicalRoot, league));
  }
  if (!index) {
    index = await buildIndexFromDir(historicalRoot);
  }

  return Response.json(index ?? {});
}

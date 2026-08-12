// app/api/logo-index/route.js  (Next.js App Router)
// — or —
// pages/api/logo-index.js      (Next.js Pages Router)
//
// Reads public/logos/historical/ on the server and returns a JSON index of
// the form: { ABBR: [year, year, ...], ... }
// e.g. { ATL: [1996, 2008, 2016, 2021], BOS: [1996, 1997], ... }
//
// The client uses this to resolve the correct logo for any team + season
// without any hardcoded list. Just drop a new ABBR_YYYY.png into the folder
// and it is picked up automatically on the next request.

import { readdir } from "fs/promises";
import { join } from "path";

// ─── App Router version ───────────────────────────────────────────────────────
export async function GET() {
  try {
    const dir = join(process.cwd(), "public", "logos", "historical");
    const files = await readdir(dir);
    const index = buildIndex(files);
    return Response.json(index, {
      headers: { "Cache-Control": "public, max-age=3600" },
    });
  } catch (err) {
    console.error("logo-index API error:", err);
    return Response.json({}, { status: 500 });
  }
}

// ─── Pages Router version (export default handler instead if needed) ──────────
// export default async function handler(req, res) {
//   try {
//     const dir = join(process.cwd(), "public", "logos", "historical");
//     const files = await readdir(dir);
//     res.setHeader("Cache-Control", "public, max-age=3600");
//     res.json(buildIndex(files));
//   } catch (err) {
//     console.error("logo-index API error:", err);
//     res.status(500).json({});
//   }
// }

// ─── Shared logic ─────────────────────────────────────────────────────────────
function buildIndex(files) {
  const index = {};

  for (const file of files) {
    // Match ABBR_YYYY.png — abbr is one or more uppercase letters/digits,
    // year is exactly 4 digits.
    const match = file.match(/^([A-Z0-9]+)_(\d{4})\.png$/i);
    if (!match) continue;

    const abbr = match[1].toUpperCase();
    const year = Number(match[2]);

    if (!index[abbr]) index[abbr] = [];
    index[abbr].push(year);
  }

  // Sort each year array ascending so the scan logic can rely on order
  for (const abbr of Object.keys(index)) {
    index[abbr].sort((a, b) => a - b);
  }

  return index;
}

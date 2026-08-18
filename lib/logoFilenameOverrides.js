/**
 * A team's DB code (teamId — the pipeline's permanent franchise
 * identity, stable across relocations/rebrands) doesn't always match
 * the filename its logo is stored under, since logo files are named by
 * whatever abbreviation the logo source/vendor actually ships under —
 * usually the team's CURRENT abbreviation. Two cases live here:
 *
 * - NFL: OAK (Las Vegas Raiders), SD (LA Chargers), STL (LA Rams) —
 *   the pipeline keeps the pre-relocation code as the permanent
 *   identity (same reasoning as NBA's CHH), but logo files are named
 *   LV.png/LAC.png/LAR.png.
 * - A few team IDs collide with reserved Windows device names (CON,
 *   PRN, AUX, NUL, COM1-9, LPT1-9), so a file literally named
 *   `CON.png` can't exist on disk on Windows.
 *
 * This is the ONLY place that needs to know about either case — teamId
 * itself (DB lookups, display, config.js keys, etc.) is untouched
 * everywhere else. Shared by TeamMark.jsx and HistoricalTeamMark.jsx
 * so the two can't drift out of sync on this.
 */
export const FILENAME_OVERRIDES = {
  CON: "CON_", // WNBA Connecticut Sun — reserved Windows device name
  OAK: "LV",   // NFL Las Vegas Raiders — logo file uses current abbreviation
  SD: "LAC",   // NFL Los Angeles Chargers — logo file uses current abbreviation
  STL: "LAR",  // NFL Los Angeles Rams — logo file uses current abbreviation
};

export function logoFileName(teamId) {
  return FILENAME_OVERRIDES[teamId] || teamId;
}

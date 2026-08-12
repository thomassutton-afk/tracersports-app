# ContinElo — Logo System

*Updated May 2026*

---

## Folder Structure

All logo files live under `public/logos/`, split into two subfolders:

```
public/
  logos/
    current/
      ATL.png
      BOS.png
      BRK.png
      CHA.png
      CHI.png
      CLE.png
      DAL.png
      DEN.png
      DET.png
      GS.png
      HOU.png
      IND.png
      LAC.png
      LAL.png
      MEM.png
      MIA.png
      MIL.png
      MIN.png
      NO.png
      NY.png
      OKC.png
      ORL.png
      PHI.png
      PHX.png
      POR.png
      SA.png
      SAC.png
      TOR.png
      UTA.png
      WAS.png
    historical/
      ATL_1996.png
      BOS_1996.png
      ... (one or more files per franchise, including relocated/renamed identities)
      SEA_1996.png
      SEA_2001.png
      OKC_2009.png
      VAN_1996.png
      MEM_2002.png
      NJ_1996.png
      BRK_2013.png
      CHA_1996.png     ← original Charlotte Hornets
      NOH_2003.png     ← New Orleans Hornets
      NO_2013.png
      CHA_2005.png     ← Charlotte Bobcats era (maps to current CHA franchise)
      CHA_2015.png     ← Charlotte Hornets name restored
      ...
```

---

## Naming Conventions

### `/current/`

- **Pattern:** `ABBR.png` — no year suffix, always the current identity.
- **30 files total**, one per franchise, keyed by their present-day DB `team_id`.
- Examples: `OKC.png`, `MEM.png`, `BRK.png`

### `/historical/`

- **Pattern:** `ABBR_YYYY.png` — where `ABBR` is the abbreviation used *by that identity* (not necessarily the current franchise `team_id`), and `YYYY` is the **first season** that logo was used.
- The earliest year in any filename is **1996**, even if the real-world logo predates that. If a logo was in use before 1996 and unchanged into the dataset's range, the file is named `_1996`.
- Historical files cover **all 30 current franchises** including seasons where their identity, city, or name was different.
- Relocated/renamed identities use the abbreviation they were known by at the time, not the current `team_id`:
  - Seattle SuperSonics → `SEA_1996.png`, `SEA_2001.png` (maps to OKC franchise)
  - Vancouver Grizzlies → `VAN_1996.png` (maps to MEM franchise)
  - New Jersey Nets → `NJ_1996.png` (maps to BRK franchise)
  - Charlotte Hornets (original) → `CHA_1996.png` (maps to NO franchise)
  - New Orleans Hornets → `NOH_2003.png` (maps to NO franchise)
  - Charlotte Bobcats → `CHA_2005.png` (maps to CHA franchise)

---

## Which Folder to Use — By Context

| Context | Folder | Reason |
|---|---|---|
| Dashboard (`Dashboard.jsx`) | `/current/` | Always shows the live 2026 season; current identity only |
| Season pages (`SeasonPage.jsx`) | `/historical/` | Must show the correct logo for each historical season |
| All-Time page | `/historical/` | Spans multiple seasons; same requirement |
| Teams pages | `/historical/` | Will display full franchise timeline |

**Rule of thumb:** if the view is tied to a specific season year, use `/historical/`. If it's always "right now", use `/current/`.

---

## Historical Logo Lookup Logic

Historical pages determine which logo file to display using a **file-driven scan**, not a hardcoded mapping table. The logic works as follows:

### Step 1 — Resolve the abbreviation list for the franchise

Each DB `team_id` maps to one or more abbreviations that have been used across its history. This franchise-to-abbreviation mapping is maintained in code (e.g. `FRANCHISE_ABBRS` in a shared constants file):

| DB `team_id` | Historical abbreviations (chronological) |
|---|---|
| OKC | SEA, OKC |
| MEM | VAN, MEM |
| BRK | NJ, BRK |
| NO | CHA, NOH, NO |
| CHA | CHA, CHA (Bobcats era uses same abbr, distinguished by year) |
| All others | Same as `team_id` — single entry |

> **Note on CHA:** The original Charlotte Hornets (pre-2002, now the NO franchise) and the Charlotte Bobcats/current Hornets (CHA franchise) share the `CHA` abbreviation. They are distinguished purely by year range — the lookup logic handles this correctly because each franchise only scans its own abbreviation list for files that are ≤ the target season.

### Step 2 — Scan for matching files

For the target franchise and season, collect all files from `/historical/` whose name matches any of the franchise's abbreviations and whose year suffix is ≤ the target season:

```
candidate files = all files where:
  filename matches ABBR_YYYY.png
  AND ABBR is in the franchise's abbreviation list
  AND YYYY ≤ target season
```

### Step 3 — Pick the newest match

From the candidates, select the file with the **highest year** (most recent logo introduced before or during the target season):

```
logo file = max(candidates, key=year)
```

### Example — OKC franchise, season 2000

Abbreviation list: `[SEA, OKC]`
Candidates ≤ 2000: `SEA_1996.png` (year 1996)
→ Display: `SEA_1996.png`

### Example — OKC franchise, season 2003

Abbreviation list: `[SEA, OKC]`
Candidates ≤ 2003: `SEA_1996.png` (1996), `SEA_2001.png` (2001)
→ Display: `SEA_2001.png`

### Example — OKC franchise, season 2015

Abbreviation list: `[SEA, OKC]`
Candidates ≤ 2015: `SEA_1996.png` (1996), `SEA_2001.png` (2001), `OKC_2009.png` (2009)
→ Display: `OKC_2009.png`

---

## Dashboard Logo Lookup (Current Season Only)

The Dashboard always uses `/current/` logos. No year logic is needed — it's a direct path:

```javascript
function getCurrentLogoPath(team_id) {
  return `/logos/current/${team_id}.png`
}
```

The `TeamLogo` component in `Dashboard.jsx` uses this function and falls back to a colored abbreviation pill if the image fails to load.

---

## Implementation Notes

- Logo files are served as Next.js static assets from `public/`. Reference them in code as `/logos/current/OKC.png` or `/logos/historical/SEA_1996.png` — no `public/` prefix.
- The historical scan logic should live in a shared utility (e.g. `lib/logos.js`) so Season, All-Time, and Teams pages all use the same function.
- Logo files should be square PNGs, transparent background, consistent size (100×100px or 200×200px recommended).
- When a new logo era begins (e.g. a team rebrands), add the new `ABBR_YYYY.png` to `/historical/` and update `/current/ABBR.png`. No code changes needed — the scan picks it up automatically.

---

## Adding a New Logo

**For a current rebrand:**
1. Replace `public/logos/current/ABBR.png` with the new logo.
2. Add `public/logos/historical/ABBR_YYYY.png` (where YYYY is the first season it applies).
3. No code changes required — the historical scan picks up the new file automatically.

**For a new franchise abbreviation/identity (relocation, rename):**
1. Add the new `ABBR_YYYY.png` to `/historical/`.
2. Update `FRANCHISE_ABBRS` in the shared constants file to include the new abbreviation in that franchise's list.
3. Update `/current/TEAM_ID.png` if the current identity changed.

---

*This document should be updated whenever the folder structure, naming convention, or lookup logic changes.*

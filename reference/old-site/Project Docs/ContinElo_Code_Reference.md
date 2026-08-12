# ContinElo — Frequently Used Code Snippets

*Reference doc for recurring patterns across the codebase*

---

## Database Connection

Used in every Python script (`create_tables.py`, `import_season.py`, `import_all.py`, `pipeline.py`).

```python
import psycopg2

DB_HOST = "aws-1-us-west-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.fhummqxfssfctswzkajj"
DB_PASS = "071606Tedi!!"

def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )

# Standard usage pattern
conn = get_connection()
conn.autocommit = False
cur = conn.cursor()
# ... do work ...
conn.commit()
cur.close()
conn.close()
```

---

## Supabase JS Client

Used in every frontend component (`Dashboard.jsx`, `SeasonPage.jsx`, etc.).

```javascript
import { supabase } from '@/lib/supabase'

// Basic query pattern
const { data, error } = await supabase
    .from('games')
    .select('team_id, post_gm_rate, date')
    .eq('season', 2026)
    .eq('variant', variant)
    .order('date', { ascending: false })
    .limit(100)
```

---

## 30-Team Reference Lists

### Python (import scripts)

```python
TEAMS_30 = [
    "ATL","BOS","BRK","CHA","CHI","CLE","DAL","DEN","DET","GS",
    "HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NO","NY",
    "OKC","ORL","PHI","PHX","POR","SA","SAC","TOR","UTA","WAS"
]
```

### JavaScript (frontend)

```javascript
const TEAM_COLORS = {
    ATL:"#C8102E", BOS:"#007A33", BRK:"#222222", CHA:"#1D1160",
    CHI:"#CE1141", CLE:"#860038", DAL:"#00538C", DEN:"#0E2240",
    DET:"#C8102E", GS:"#1D428A",  HOU:"#CE1141", IND:"#002D62",
    LAC:"#C8102E", LAL:"#552583", MEM:"#5D76A9", MIA:"#98002E",
    MIL:"#00471B", MIN:"#0C2340", NO:"#0C2340",  NY:"#006BB6",
    OKC:"#007AC1", ORL:"#0077C0", PHI:"#006BB6", PHX:"#1D1160",
    POR:"#E03A3E", SA:"#8A8D8F",  SAC:"#5A2D81", TOR:"#CE1141",
    UTA:"#002B5C", WAS:"#002B5C",
}

const TEAM_NAMES = {
    ATL:"Atlanta Hawks",        BOS:"Boston Celtics",         BRK:"Brooklyn Nets",
    CHA:"Charlotte Hornets",    CHI:"Chicago Bulls",           CLE:"Cleveland Cavaliers",
    DAL:"Dallas Mavericks",     DEN:"Denver Nuggets",          DET:"Detroit Pistons",
    GS:"Golden State Warriors", HOU:"Houston Rockets",         IND:"Indiana Pacers",
    LAC:"LA Clippers",          LAL:"Los Angeles Lakers",      MEM:"Memphis Grizzlies",
    MIA:"Miami Heat",           MIL:"Milwaukee Bucks",         MIN:"Minnesota Timberwolves",
    NO:"New Orleans Pelicans",  NY:"New York Knicks",          OKC:"Oklahoma City Thunder",
    ORL:"Orlando Magic",        PHI:"Philadelphia 76ers",      PHX:"Phoenix Suns",
    POR:"Portland Trail Blazers", SA:"San Antonio Spurs",      SAC:"Sacramento Kings",
    TOR:"Toronto Raptors",      UTA:"Utah Jazz",               WAS:"Washington Wizards",
}
```

---

## Historical Identity / Display Mapping

Used in `SeasonPage.jsx`, `AllTimeRankings.jsx`, `TeamPage.jsx` — converts DB `team_id` + season into what to show the user (different abbr, name, color for relocated/renamed teams).

```javascript
const DISPLAY_IDENTITIES = {
    OKC: [
        { through: 2008, abbr:"SEA", name:"Seattle SuperSonics", color:"#00653A" },
    ],
    MEM: [
        { through: 2001, abbr:"VAN", name:"Vancouver Grizzlies", color:"#00B2A9" },
    ],
    BRK: [
        { through: 2012, abbr:"NJN", name:"New Jersey Nets", color:"#002A60" },
    ],
    NO: [
        { through: 2002, abbr:"CHA", name:"Charlotte Hornets", color:"#1D1160" },
        { through: 2012, abbr:"NOH", name:"New Orleans Hornets", color:"#002B5C" },
    ],
    CHA: [
        { through: 2014, abbr:"CHA", name:"Charlotte Bobcats", color:"#F26522" },
    ],
}

function getDisplayIdentity(team_id, season) {
    const overrides = DISPLAY_IDENTITIES[team_id]
    if (overrides) {
        for (const o of overrides) {
            if (season <= o.through) return { abbr: o.abbr, name: o.name, color: o.color }
        }
    }
    return { abbr: team_id, name: null, color: TEAM_COLORS[team_id] || "#663399" }
}
```

---

## Bulk Paginated Supabase Fetch

Used when a query might exceed Supabase's row limit (e.g. playoff games across all seasons in `AllTimeRankings.jsx`).

```javascript
let allRows = []
let from = 0
const PAGE = 1000

while (true) {
    const { data, error } = await supabase
        .from('games')
        .select('team_id, season, round, result')
        .eq('variant', variant)
        .eq('type', 'P')
        .range(from, from + PAGE - 1)
    if (error || !data || data.length === 0) break
    allRows = allRows.concat(data)
    if (data.length < PAGE) break
    from += PAGE
}
```

---

## Playoff Record Aggregator

Takes raw playoff game rows and builds a per-team record object. Used in `Dashboard.jsx`, `SeasonPage.jsx`, `AllTimeRankings.jsx`.

```javascript
const pfMap = {}

for (const row of poGames) {
    const key = row.team_id  // or `${row.team_id}-${row.season}` for all-time
    if (!pfMap[key]) pfMap[key] = { r1w:0, r1l:0, r2w:0, r2l:0, r3w:0, r3l:0, fw:0, fl:0, pi_w:0, pi_l:0 }
    const p = pfMap[key]
    const rnd = parseFloat(row.round)
    const win = row.result === 1
    if (rnd === 0.5) { win ? p.pi_w++ : p.pi_l++ }
    if (rnd === 1)   { win ? p.r1w++  : p.r1l++  }
    if (rnd === 2)   { win ? p.r2w++  : p.r2l++  }
    if (rnd === 3)   { win ? p.r3w++  : p.r3l++  }
    if (rnd === 4)   { win ? p.fw++   : p.fl++   }
}
```

---

## Playoff Result Badge (JSX)

Displays the furthest playoff result for a team-season. Used in `SeasonPage.jsx`, `AllTimeRankings.jsx`, `TeamPage.jsx`.

```jsx
function PlayoffResult({ r1w, r1l, r2w, r2l, r3w, r3l, fw, fl, pi_w, pi_l }) {
    if (fw >= 4)               return <span style={{ color:"#BF5700", fontWeight:700 }}>🏆 Champion</span>
    if (fl > 0)                return <span style={{ color:"#663399" }}>Finals ({fw}–{fl})</span>
    if (r3w > 0 || r3l > 0)   return <span style={{ color:"#444" }}>Conf Finals ({r3w}–{r3l})</span>
    if (r2w > 0 || r2l > 0)   return <span style={{ color:"#666" }}>Conf Semis ({r2w}–{r2l})</span>
    if (r1w > 0 || r1l > 0)   return <span style={{ color:"#888" }}>Round 1 ({r1w}–{r1l})</span>
    if (pi_w > 0 || pi_l > 0) return <span style={{ color:"#aaa" }}>Play-In</span>
    return <span style={{ color:"#ddd" }}>—</span>
}
```

---

## Season Label Formatter

Converts the end-year integer (e.g. `2026`) to display format (`"2025–26"`). Used everywhere.

```javascript
const SEASON_LABEL = (y) => `${y - 1}–${String(y).slice(2)}`
// e.g. SEASON_LABEL(2026) → "2025–26"
// e.g. SEASON_LABEL(1996) → "1995–96"
```

---

## ContinElo Engine — Core Formula Functions (Python)

The heart of `continelo_engine.py`. Reference when tweaking formulas or verifying calculations.

```python
BASE  = 1500
ALPHA = 0.6
HCA   = 84
KMAX  = 58
KMIN  = 6
K_DECAY = 0.15

def preseason_rating(prev_end, variant):
    if variant == "elo":
        return float(BASE)
    return ALPHA * prev_end + (1 - ALPHA) * BASE   # 0.6 * prev + 0.4 * 1500

def k_factor(games_played):
    return max(KMIN, KMAX - K_DECAY * min(games_played, 82))

def rest_adj(rest_diff):
    return max(-16, min(16, rest_diff * 8))

def expected_win_pct(pre, opp_pre, rest_adj_team, rest_adj_opp, home_away):
    adj_team = pre + rest_adj_team + (HCA if home_away == "H" else 0)
    adj_opp  = opp_pre + rest_adj_opp + (HCA if home_away == "A" else 0)
    return 1 / (1 + 10 ** ((adj_opp - adj_team) / 400))

def mov_mult(points_for, points_against, pre, opp_pre, ot):
    mov = abs(points_for - points_against)
    mult = ((mov + 5) ** 0.6) / (12 + 0.01 * abs(pre - opp_pre))
    return mult * (0.9 if ot == 1 else 1.0)

def rating_change(keff, movm, result, ewp):
    return keff * movm * (result - ewp)

PO_MULT = { "RS":1.00, "INS":1.02, 0.5:1.05, 1:1.10, 2:1.20, 3:1.35, 4:1.50 }
```

---

## NBA API Team Abbreviation Mapping

Used in `pipeline.py` — the NBA API uses different abbreviations for some teams than ContinElo does.

```python
NBA_API_TO_CONTINELO = {
    "NOP": "NO",
    "NYK": "NY",
    "GSW": "GS",
    "SAS": "SA",
    "BKN": "BRK",
}

def normalize_team(abbr):
    return NBA_API_TO_CONTINELO.get(abbr, abbr)
```

---

## Game ID Generator (Python)

Used in import scripts to create a stable `game_id` from date + teams (before NBA API IDs were in use).

```python
date_str     = str(row["Date"].date()).replace("-", "")
teams_sorted = "_".join(sorted([str(row["Team"]), str(row["Opponent"])]))
game_id      = f"{date_str}_{teams_sorted}"
# e.g. "20251205_BOS_LAL"
```

---

## Round/Type Detection from NBA Game ID

Used in `pipeline.py` to determine game type and playoff round from the NBA API's `game_id` prefix.

```python
IST_FINALS = {
    "0022401239": 2025,   # update each year with correct ID
}

def parse_game_id(game_id):
    if game_id in IST_FINALS:
        return "P", "INS"
    prefix = game_id[:3]
    if prefix == "002":   return "R", "RS"
    elif prefix == "005": return "P", 0.5
    elif prefix == "004":
        round_num = int(game_id[6:8])
        return "P", round_num
    else:
        return None, None   # preseason / unknown — skip
```

---

## Variant Toggle (JSX)

The ContinElo / Elo switcher used in every page nav.

```jsx
const [variant, setVariant] = useState('continelo')

// In JSX:
<div className="variant-toggle">
    <button className={`vt-btn${variant === 'continelo' ? ' active' : ''}`}
        onClick={() => setVariant('continelo')}>ContinElo</button>
    <button className={`vt-btn${variant === 'elo' ? ' active' : ''}`}
        onClick={() => setVariant('elo')}>Elo</button>
</div>
```

---

## Design Tokens (CSS Variables)

Defined in `globals.css`. Use these everywhere instead of raw hex values.

```css
--acc:       #663399;   /* purple — primary */
--ut:        #BF5700;   /* burnt orange — top teams / champions */
--uo:        #154733;   /* green — live / success */
--bg:        #F5F0E8;   /* cream page background */
--surface:   #FDFAF5;   /* card / table background */
--surface2:  #EDE8DE;   /* hover / secondary surface */
--border:    rgba(0,0,0,0.08);
--border2:   rgba(0,0,0,0.15);
--text:      #1A1816;
--text2:     #5C5650;
--text3:     #9A9490;
--font-display: 'Playfair Display', Georgia, serif;
--font-body:    'DM Sans', sans-serif;
--font-mono:    'IBM Plex Mono', monospace;
```

---

## Three-Color Stripe

The signature stripe element that appears at the top and bottom of every page.

```html
<!-- HTML / globals.css class -->
<div class="color-stripe">
    <div class="stripe-acc"></div>
    <div class="stripe-ut"></div>
    <div class="stripe-uo"></div>
</div>
```

```javascript
// Inline JSX version (used on Team page with team-specific gradient)
<div style={{ height: 4, background: "linear-gradient(90deg, #663399 33%, #BF5700 66%, #154733 100%)" }} />

// Team page version (team color bleeds into the gradient)
<div style={{ height: 4, background: `linear-gradient(90deg, ${teamColor} 50%, #BF5700 75%, #154733 100%)` }} />
```

---

## Sortable Column Header (JSX)

Used in `SeasonPage.jsx` and `AllTimeRankings.jsx` — handles active state, direction arrows, and sort toggle.

```jsx
function Th({ col, label, sortCol, sortDir, onSort, align = "right" }) {
    const active = sortCol === col
    return (
        <th onClick={() => onSort(col)} style={{
            fontFamily: "IBM Plex Mono, monospace", fontSize: 10, fontWeight: 500,
            color: active ? "#663399" : "#aaa",
            textTransform: "uppercase", letterSpacing: 1,
            padding: "10px 12px", textAlign: align,
            cursor: "pointer", userSelect: "none", whiteSpace: "nowrap",
        }}>
            {label}
            <span style={{ marginLeft: 4, opacity: active ? 1 : 0.4 }}>
                {active ? (sortDir === "asc" ? "↑" : "↓") : "↕"}
            </span>
        </th>
    )
}

// Sort handler
function handleSort(col) {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc")
    else { setSortCol(col); setSortDir("desc") }
}
```

---

## Supabase Views Reference

Views that exist in the database and what they return.

| View | Key columns | Used by |
|---|---|---|
| `current_ratings` | `team_id, variant, post_gm_rate, rating_change` | Dashboard power rankings |
| `season_records` | `team_id, season, variant, wins, losses` | Standings, All-Time |
| `season_accuracy` | `season, variant, game_count, avg_accuracy, avg_brier` | Hero stats strip |
| `season_standings` | `team_id, season, variant, type (R/P), final_rating` | Season page, All-Time |

`season_standings` must be queried twice — once with `type = 'R'` for RS end rating, once with `type = 'P'` for playoff end rating — then merged in JS.

---

## Logo Path Helpers

### Current season (Dashboard only)
```javascript
function getCurrentLogoPath(team_id) {
    return `/logos/current/${team_id}.png`
}
```

### Historical (Season, All-Time, Team pages)
Requires the logo index from the API route (`/api/logo-index`), which scans `public/logos/historical/` for `ABBR_YYYY.png` files.

```javascript
const FRANCHISE_ABBRS = {
    OKC: ["SEA", "OKC"],
    MEM: ["VAN", "MEM"],
    BRK: ["NJ",  "BRK"],
    NO:  ["CHA", "NOH", "NO"],
    CHA: ["CHA"],
}

function resolveHistoricalLogoPath(team_id, season, index) {
    const abbrs = FRANCHISE_ABBRS[team_id] ?? [team_id]
    let bestFile = null, bestYear = -1
    for (const abbr of abbrs) {
        const years = index[abbr] ?? []
        for (const year of years) {
            if (year <= season && year > bestYear) {
                bestYear = year
                bestFile = `/logos/historical/${abbr}_${year}.png`
            }
        }
    }
    return bestFile ?? `/logos/current/${team_id}.png`
}
```

---

## Formatting Helpers

Small utility functions used constantly across all pages.

```javascript
const fmt1      = (v) => v != null ? Number(v).toFixed(1) : "—"
const fmtRecord = (w, l) => w != null ? `${w}–${l}` : "—"
const fmtDate   = (d) => {
    if (!d) return ""
    return new Date(d + "T12:00:00").toLocaleDateString("en-US", { month:"short", day:"numeric" })
}
const chgColor  = (n) => n > 0 ? "#2d7a3a" : n < 0 ? "#c0392b" : "#888"
const chgStr    = (n) => n == null ? "—" : (n > 0 ? "+" : "") + Number(n).toFixed(1)
```

---

*Last updated May 2026*

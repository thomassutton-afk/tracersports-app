# Benchmarking ContinElo Against FiveThirtyEight's NBA Elo Model

**Date:** July 20, 2026
**Author:** TJ Sutton, ContinElo / TRACER Sports
**Scope:** 1995–96 through 2023–24 NBA seasons (29 complete seasons)

---

## 1. Purpose

This report tests whether ContinElo's win-probability predictions are more
accurate than FiveThirtyEight's published NBA Elo model, over the identical
set of games. It's written so anyone — including a future version of me —
can re-run the whole thing from scratch and get the same numbers.

**Headline result:** ContinElo outperformed the FiveThirtyEight-derived Elo
model on both accuracy (66.83% vs. 66.61%) and Brier score (0.2089 vs.
0.2098) across 73,278 identical games, and the edge is statistically
significant under three independent tests (see Section 6).

---

## 2. Data Sources

### 2.1 ContinElo data (this project)

Exported directly from the Supabase `games` table via SQL Editor:

```sql
SELECT
  date,
  season,
  team_id,
  opponent_id,
  home_away,
  points_for,
  points_against,
  type,
  round,
  expected_win_pct,
  result
FROM games
WHERE variant = 'continelo'
  AND season BETWEEN 1996 AND 2024
ORDER BY date, team_id;
```

- **Rows exported:** 73,280
- **Export date:** July 20, 2026
- **File:** `continelo_export.csv`
- **SHA-256:** `d82f8d81af191395803a3a7af72899205e9022150cbc645fe2a2a47b8f7f7ef7`

Note: the Supabase Table/SQL Editor caps results at 100 rows by default in
its preview pane. Use the row-limit setting or the Table Editor's export
feature (with filters applied) to get the full row count — the SHA-256
above is how you confirm you exported the same data.

### 2.2 Benchmark data — FiveThirtyEight NBA Elo

FiveThirtyEight's live NBA Elo model was discontinued after 538 was
disbanded in 2023. The dataset used here is a continuation of the same
methodology, maintained by Neil Paine (a former FiveThirtyEight writer),
using 538's original Elo formula and game-level format.

- **Source:** `https://github.com/Neil-Paine-1/NBA-elo`
- **File used:** `nba_elo.csv`
- **Direct download URL:** `https://raw.githubusercontent.com/Neil-Paine-1/NBA-elo/main/nba_elo.csv`
- **Download date:** July 20, 2026
- **Raw file SHA-256:** `be12a0ffcf49820ec967bfc4e838d477728a345753e4ebcc8e1b455cc98d8bff`
- **Row count (raw, all-time):** 151,410
- **Coverage in raw file:** 1946-11-01 through 2025-03-17

**Important limitation:** as of the download date, this file's most recent
game is March 17, 2025 — partway through the 2024–25 regular season. It
does **not** include 2024–25 playoffs or any 2025–26 games. For that
reason, this benchmark is restricted to **complete seasons only: 1996–2024
(29 seasons)**. 2025 and 2026 are excluded from the comparison entirely,
not padded with partial data.

You should re-download this file before re-running the analysis, since it
updates periodically — check its row count and date range against the
numbers above and expect them to differ (grow) over time. If Neil Paine's
repo becomes unavailable, the original 538 archive
(`https://github.com/fivethirtyeight/data`, `nba-elo/nbaallelo.csv`) covers
1946–2015 in a similar row-per-team-game format and could substitute for
the older portion of this range.

---

## 3. Metrics Definitions

Both metrics are computed identically for both models, on the exact same
games.

**Accuracy** — the fraction of games where the model's win probability
correctly favored the actual winner:

```
correct = (prob >= 0.5 AND team won) OR (prob < 0.5 AND team lost)
accuracy = mean(correct)
```

**Brier score** — measures probability calibration, not just correctness.
Lower is better; 0.25 is what a model that always predicts a 50/50 coin
flip would score.

```
brier = mean((prob - result)^2)
```

where `result` is 1 if the team won, 0 if it lost.

---

## 4. Team Code Reconciliation

ContinElo stores games under a **franchise-based** `team_id` that stays
constant across relocations (e.g., `OKC` is used for the entire Seattle
SuperSonics → Oklahoma City Thunder history). FiveThirtyEight/Paine's data
uses **era-specific** codes that change at the point of relocation or
rebrand. To join the two datasets on `date + team + opponent`, every
ContinElo `team_id` was mapped to the correct era-specific 538 code for
that season.

The mapping was **not assumed** — it was derived empirically by inspecting
which codes actually appear in the 538 file for each season, then verified
by confirming the match rate approached 100%. The final mapping:

| ContinElo `team_id` | 538/Paine code | Season cutoff |
|---|---|---|
| `OKC` | `SEA` → `OKC` | `SEA` through season 2008, `OKC` from 2009 |
| `MEM` | `VAN` → `MEM` | `VAN` through season 2001, `MEM` from 2002 |
| `BRK` | `NJN` → `BRK` | `NJN` through season 2012, `BRK` from 2013 |
| `NO`  | `CHH` → `NOK` → `NOP` | `CHH` through 2002, `NOK` for 2006–2007 (post-Katrina "New Orleans/Oklahoma City Hornets"), `NOP` all other seasons ≥2003 |
| `CHA` | `CHO` | All seasons (538/Paine applies the current "CHO" code retroactively to the 2005+ Charlotte franchise, covering both the Bobcats era and the renamed Hornets) |
| `WAS` | `WSB` → `WAS` | `WSB` through season 1997 (Washington Bullets), `WAS` from 1998 (renamed Wizards) |
| `GS`  | `GSW` | All seasons |
| `NY`  | `NYK` | All seasons |
| `PHX` | `PHO` | All seasons |
| `SA`  | `SAS` | All seasons |
| all others | same code | — |

Join key: `date + "_" + mapped_team_code + "_" + mapped_opponent_code`,
matched against 538's `date + team1 + team2` (their file already stores
one row per team per game, matching ContinElo's structure, so this is a
direct key match with no aggregation needed).

**Match rate: 73,278 / 73,280 rows (99.997%).** The 2 remaining unmatched
rows were not investigated further — at that volume they don't move any
result and are most likely a data entry quirk (e.g. a postponed/replayed
game) in one source or the other.

---

## 5. Results

### 5.1 Overall (1996–2024, 73,278 games)

| Model | Accuracy | Brier |
|---|---|---|
| **ContinElo** | **66.83%** | **0.2089** |
| FiveThirtyEight / Paine Elo | 66.61% | 0.2098 |

### 5.2 Per-season

| Season | Games | ContinElo Acc% | 538 Acc% | ContinElo Brier | 538 Brier | ContinElo better (acc) | ContinElo better (brier) |
|---:|---:|---:|---:|---:|---:|:---:|:---:|
| 1996 | 2514 | 69.29 | 70.01 | 0.1984 | 0.1929 | No | No |
| 1997 | 2522 | 70.66 | 70.66 | 0.1902 | 0.1918 | Tie | Yes |
| 1998 | 2520 | 71.75 | 71.59 | 0.1865 | 0.1867 | Yes | Yes |
| 1999 | 1582 | 70.16 | 67.89 | 0.2073 | 0.2070 | Yes | No |
| 2000 | 2528 | 67.88 | 67.88 | 0.2003 | 0.2013 | Tie | Yes |
| 2001 | 2520 | 67.46 | 67.70 | 0.2043 | 0.2061 | No | Yes |
| 2002 | 2520 | 64.68 | 64.13 | 0.2169 | 0.2187 | Yes | Yes |
| 2003 | 2554 | 66.95 | 66.48 | 0.2067 | 0.2067 | Yes | Tie |
| 2004 | 2542 | 65.85 | 65.70 | 0.2115 | 0.2115 | Yes | Tie |
| 2005 | 2628 | 65.98 | 66.13 | 0.2092 | 0.2088 | No | No |
| 2006 | 2638 | 66.11 | 66.03 | 0.2144 | 0.2157 | Yes | Yes |
| 2007 | 2618 | 65.24 | 64.48 | 0.2187 | 0.2194 | Yes | Yes |
| 2008 | 2630 | 67.68 | 68.67 | 0.2016 | 0.2014 | No | No |
| 2009 | 2630 | 69.66 | 69.05 | 0.1974 | 0.1972 | Yes | No |
| 2010 | 2624 | 69.51 | 69.21 | 0.2007 | 0.2017 | Yes | Yes |
| 2011 | 2622 | 67.73 | 68.19 | 0.2032 | 0.2022 | No | No |
| 2012 | 2148 | 67.50 | 67.13 | 0.2070 | 0.2083 | Yes | Yes |
| 2013 | 2628 | 67.96 | 67.43 | 0.2031 | 0.2035 | Yes | Yes |
| 2014 | 2638 | 65.35 | 65.05 | 0.2108 | 0.2126 | Yes | Yes |
| 2015 | 2622 | 67.35 | 66.59 | 0.2072 | 0.2084 | Yes | Yes |
| 2016 | 2632 | 69.83 | 69.53 | 0.1990 | 0.1994 | Yes | Yes |
| 2017 | 2618 | 64.55 | 64.78 | 0.2176 | 0.2193 | No | Yes |
| 2018 | 2624 | 66.54 | 66.62 | 0.2136 | 0.2149 | No | Yes |
| 2019 | 2624 | 65.40 | 65.32 | 0.2131 | 0.2151 | Yes | Yes |
| 2020 | 2286 | 63.69 | 63.34 | 0.2220 | 0.2232 | Yes | Yes |
| 2021 | 2342 | 60.63 | 60.80 | 0.2307 | 0.2336 | No | Yes |
| 2022 | 2646 | 64.85 | 64.17 | 0.2238 | 0.2272 | Yes | Yes |
| 2023 | 2640 | 63.71 | 63.03 | 0.2278 | 0.2306 | Yes | Yes |
| 2024 | 2638 | 64.82 | 64.14 | 0.2146 | 0.2183 | Yes | Yes |

**Summary:** ContinElo had the better (lower) Brier score in **21 of 29**
seasons, and better accuracy in **19 of 29** seasons.

`season` is coded as the end year of the season (1996 = the 1995–96
season), consistent with the rest of the ContinElo project.

---

## 6. Statistical Significance

A season-over-season edge this small (roughly 0.2 accuracy points, 0.001
Brier points) could plausibly be noise. Three tests were run to check:

**McNemar's test (game-level, on disagreements only).** Of the games where
the two models picked different winners: ContinElo was right and 538 was
wrong 1,798 times; 538 was right and ContinElo was wrong 1,638 times.
χ² = 7.36, **p = 0.0067**.

**Wilcoxon signed-rank test (game-level, on per-game Brier differences).**
**p = 0.0012**.

**Season-level paired bootstrap (the most conservative check — treats
each of the 29 seasons as one independent observation, rather than
treating 73,278 games as independent, which they aren't, since games
within a season share standings, home courts, and roster continuity).**
Mean Brier difference (ContinElo − 538) across seasons: **−0.00087**
(negative favors ContinElo). 10,000-resample bootstrap 95% confidence
interval: **[−0.00143, −0.00021]** — the interval does not cross zero.

All three tests agree the edge is real, not sampling noise, even under the
most conservative (season-level) framing.

---

## 7. Limitations and Caveats

- **This compares two full systems, not two formulas in isolation.**
  538/Paine's model may include adjustments (rest, injuries, margin of
  victory) that differ from ContinElo's in ways beyond the core Elo
  constants (K-factor, HCA, carry-forward alpha). A win here means
  "ContinElo's overall system performs better," not "ContinElo's specific
  formula choices are individually superior."
- **No 2025–26 benchmark yet.** The 538/Paine archive doesn't cover the
  current season as of this writing. Re-run this analysis once it catches
  up, or find a live alternative source, to extend the comparison.
- **The 2005–2007 New Orleans Hornets required special handling** (the
  post-Katrina "New Orleans/Oklahoma City Hornets" branding uses a
  distinct `NOK` code in the 538 data) — this is a genuine historical
  quirk, not a data error, and is documented in Section 4.
- **This tests the ContinElo (carry-forward) variant only.** The `elo`
  (season-reset) variant was not included in this run; the same
  methodology applies if that comparison is wanted later — just change
  `variant = 'continelo'` to `variant = 'elo'` in the Section 2.1 query
  and re-run.

---

## 8. Full Reproduction Steps

Anyone with Python (pandas, scipy) and access to the ContinElo Supabase
project can reproduce this end to end:

**Step 1 — Export ContinElo data.** Run the SQL query in Section 2.1
against the Supabase project, using the Table Editor's export (not the SQL
Editor's row-capped download) to get all 73,280 rows.

**Step 2 — Download the benchmark data.**
```bash
curl -sL -o nba_elo_538.csv \
  "https://raw.githubusercontent.com/Neil-Paine-1/NBA-elo/main/nba_elo.csv"
```

**Step 3 — Filter to complete seasons and compute the benchmark's own
metrics (sanity check before comparing).**
```python
import pandas as pd

df = pd.read_csv("nba_elo_538.csv")
complete = df[(df['season'] >= 1996) & (df['season'] <= 2024)].copy()
complete['result']  = (complete['score1'] > complete['score2']).astype(int)
complete['correct'] = ((complete['elo_prob1'] >= 0.5) & (complete['result'] == 1)) | \
                       ((complete['elo_prob1'] < 0.5) & (complete['result'] == 0))
complete['brier']   = (complete['elo_prob1'] - complete['result'])**2
print(complete['correct'].mean(), complete['brier'].mean())
# Expect roughly 0.6661 accuracy, 0.2098 Brier if using the same file version
```

**Step 4 — Apply the team-code mapping from Section 4** to the ContinElo
export's `team_id` and `opponent_id` columns, build the join key, and
merge:
```python
def to_538(team_id, season):
    if team_id == 'OKC':  return 'SEA' if season <= 2008 else 'OKC'
    if team_id == 'MEM':  return 'VAN' if season <= 2001 else 'MEM'
    if team_id == 'BRK':  return 'NJN' if season <= 2012 else 'BRK'
    if team_id == 'NO':
        if season <= 2002: return 'CHH'
        if season in (2006, 2007): return 'NOK'
        return 'NOP'
    if team_id == 'CHA':  return 'CHO'
    if team_id == 'WAS':  return 'WSB' if season <= 1997 else 'WAS'
    simple = {'GS':'GSW', 'NY':'NYK', 'PHX':'PHO', 'SA':'SAS'}
    return simple.get(team_id, team_id)

ce['team_538']     = ce.apply(lambda r: to_538(r['team_id'], r['season']), axis=1)
ce['opponent_538'] = ce.apply(lambda r: to_538(r['opponent_id'], r['season']), axis=1)
ce['jkey']     = ce['date'] + '_' + ce['team_538'] + '_' + ce['opponent_538']
elo538['jkey'] = elo538['date'].astype(str) + '_' + elo538['team1'] + '_' + elo538['team2']
merged = ce.merge(elo538[['jkey','elo_prob1','score1','score2']], on='jkey', how='left')
```
Confirm the match rate lands near 99.997% (73,278/73,280) before trusting
the results — a materially lower match rate means the team-code mapping
needs adjustment for that data vintage.

**Step 5 — Compute accuracy and Brier for both models** on the merged,
matched rows only (drop unmatched rows first), using the formulas in
Section 3.

**Step 6 — Run the significance tests** from Section 6
(`scipy.stats.wilcoxon` for the Wilcoxon test; McNemar's test and the
bootstrap are both straightforward to hand-roll, ~10 lines each, as shown
in the working session that produced this report).

---

## 9. Data File Checksums (for exact verification)

If you want to confirm you're looking at the *exact* same data this report
was generated from (rather than a newer version of the 538/Paine file,
which updates periodically):

| File | SHA-256 |
|---|---|
| `continelo_export.csv` | `d82f8d81af191395803a3a7af72899205e9022150cbc645fe2a2a47b8f7f7ef7` |
| `nba_elo_538.csv` (raw download) | `be12a0ffcf49820ec967bfc4e838d477728a345753e4ebcc8e1b455cc98d8bff` |
| `merged_comparison.csv` (joined dataset) | `6b5d879eff59c04d01f9bc01c4bee6419dce6481b3f9550ac2fd118c399b42ca` |
| `season_comparison.csv` (per-season summary) | `83ba1c5b6b609ebec1279de83ac650222bc8bd983961d021ce96e8cf09747969` |

---

*ContinElo vs. 538 Elo Benchmark — generated July 20, 2026*

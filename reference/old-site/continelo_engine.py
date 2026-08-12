"""
ContinElo Calculation Engine
Phase 1 — Replicates every formula from the Technical Specification (Section 3 & 5).
Supports both 'elo' (reset) and 'continelo' (carry-forward) variants.

Usage:
    from continelo_engine import ContinEloEngine

    engine = ContinEloEngine(variant='continelo')
    results = engine.process_season(games_df, preseason_ratings)
    engine.verify_against_excel(excel_df, results)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# System Constants (Section 2)
# ---------------------------------------------------------------------------
BASE = 1500
ALPHA = 0.6
HCA = 84
KMAX = 58
KMIN = 6
K_DECAY = 0.15

PO_MULT = {
    "RS":  1.00,
    "INS": 1.02,
    0.5:   1.05,
    1:     1.10,
    2:     1.20,
    3:     1.35,
    4:     1.50,
}

REST_SCALE = 8       # Elo points per rest-day advantage
REST_CAP   = 16      # Max rest adjustment (±)


# ---------------------------------------------------------------------------
# Core formula functions
# ---------------------------------------------------------------------------

def preseason_rating(prev_end: float, variant: str) -> float:
    """Pre-season Elo for a team given their end-of-last-season rating."""
    if variant == "elo":
        return float(BASE)
    return ALPHA * prev_end + (1 - ALPHA) * BASE


def rest_adj(rest_diff: int) -> float:
    return max(-REST_CAP, min(REST_CAP, rest_diff * REST_SCALE))


def games_played_capped(gp: int) -> int:
    return min(gp, 82)


def k_factor(games_played: int) -> float:
    return max(KMIN, KMAX - K_DECAY * games_played_capped(games_played))


def po_mult(round_val) -> float:
    """Return playoff multiplier for the given round value."""
    # round_val may be string 'RS'/'INS' or numeric 0.5/1/2/3/4
    try:
        key = float(round_val) if round_val not in ("RS", "INS") else round_val
    except (TypeError, ValueError):
        key = round_val
    return PO_MULT.get(key, 1.00)


def k_eff(k: float, pmult: float) -> float:
    return k * pmult


def expected_win_pct(
    pre: float, opp_pre: float,
    rest_adj_team: float, rest_adj_opp: float,
    home_away: str,
) -> float:
    adj_team = pre + rest_adj_team + (HCA if home_away == "H" else 0)
    adj_opp  = opp_pre + rest_adj_opp + (HCA if home_away == "A" else 0)
    return 1 / (1 + 10 ** ((adj_opp - adj_team) / 400))


def result_value(points_for: int, points_against: int) -> float:
    mov = points_for - points_against
    if mov > 0:
        return 1.0
    if mov < 0:
        return 0.0
    return 0.5  # tie (theoretically impossible in NBA)


def mov_mult(points_for: int, points_against: int,
             pre: float, opp_pre: float, ot: int) -> float:
    mov = abs(points_for - points_against)
    rating_diff = abs(pre - opp_pre)
    mult = ((mov + 5) ** 0.6) / (12 + 0.01 * rating_diff)
    if ot == 1:
        mult *= 0.9
    return mult


def rating_change(keff: float, movm: float, result: float, ewp: float) -> float:
    return keff * movm * (result - ewp)


def accuracy(ewp: float, result: float) -> int:
    if ewp >= 0.5 and result == 1.0:
        return 1
    if ewp < 0.5 and result == 0.0:
        return 1
    return 0


def brier(ewp: float, result: float) -> float:
    return (ewp - result) ** 2


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class ContinEloEngine:
    """
    Processes games in chronological order for a single rating variant.

    Parameters
    ----------
    variant : 'elo' or 'continelo'
    """
    variant: str = "continelo"

    def process_season(
        self,
        games_df: pd.DataFrame,
        preseason_ratings: dict[str, float],
        season_start_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Calculate all derived columns for every row in games_df.

        Parameters
        ----------
        games_df : DataFrame with manual columns:
            Date, Season, Type, Round, Team, Opponent, HomeAway,
            PointsFor, PointsAgainst, OT
            (GamesPlayed may be pre-filled or will be computed here)

        preseason_ratings : {team_abbrev: preseason_elo}
            For 'elo' variant: all values should be 1500.
            For 'continelo': 0.6 * prev_end + 0.4 * 1500.

        season_start_date : used for DaysOff calculation on the first game.
            Defaults to the earliest date in games_df.

        Returns
        -------
        DataFrame with all calculated columns added.
        """
        df = games_df.copy()

        # Ensure dates are proper Python date / pandas Timestamp
        df["Date"] = pd.to_datetime(df["Date"])

        if season_start_date is None:
            season_start_date = df["Date"].min()
        season_start_ts = pd.Timestamp(season_start_date)

        # Sort strictly: Date, then stable tie-break by index
        df = df.sort_values(["Date"], kind="stable").reset_index(drop=True)

        # State tracking
        current_ratings: dict[str, float] = {}   # team -> current rating
        last_game_date:  dict[str, pd.Timestamp] = {}  # team -> last game date
        games_played_count: dict[str, int] = {}   # team -> gp count this season

        # Pre-populate ratings from preseason table.
        # preseason_ratings contains the PREVIOUS season's end rating (prev_end).
        # Apply the variant formula to get the actual starting rating.
        for team, prev_end in preseason_ratings.items():
            current_ratings[team] = preseason_rating(prev_end, self.variant)

        # Build a lookup: for each row, what is the opponent's rating ENTERING
        # that specific game (i.e. before the opponent's own row is processed)?
        # Strategy: identify game pairs (Team A vs Team B on same date) and
        # snapshot both teams' ratings simultaneously before processing either row.
        # We do two passes:
        #   Pass 1: compute pre-game ratings for every row (snapshot before update)
        #   Pass 2: fill in all other derived columns using those snapshots.
        #
        # Implementation: iterate rows in order; for each row, read current_ratings
        # for BOTH team and opponent BEFORE updating anything. Store snapshots.
        # Then apply updates for this team after computing its row.
        # The key insight: when we reach the opponent's row later, current_ratings
        # for that opponent was already updated by their own previous game — but
        # we must NOT use the post-game rating from this paired game.
        # Solution: track a "pre_game_snapshot" dict keyed by (team, date_str, opp)
        # populated on first encounter of a game pair.

        pre_game_snapshots: dict[tuple, float] = {}  # (team, date_str, opp) -> pre_rate

        # Output columns (all float/int)
        out_cols = [
            "GamesPlayed", "DaysOff", "OppDaysOff", "RestDiff", "OppRestDiff",
            "RestAdj", "OppRestAdj", "PreGmRate", "OppPreGmRate",
            "ExpectedWin%", "MOV", "Result", "Accuracy", "Brier",
            "MOVMult", "POMult", "K", "Keff", "RatingChange", "PostGmRate",
            "W", "L", "R1W", "R1L", "R2W", "R2L", "R3W", "R3L", "FW", "FL",
        ]
        for col in out_cols:
            df[col] = 0.0

        # Process row by row (must be sequential)
        for idx, row in df.iterrows():
            team     = row["Team"]
            opponent = row["Opponent"]
            game_date = row["Date"]
            home_away = row["HomeAway"]
            pf = int(row["PointsFor"])
            pa = int(row["PointsAgainst"])
            ot = int(row["OT"])
            round_val = row["Round"]
            game_type = row["Type"]
            date_str  = str(game_date.date())

            # Snapshot key for this game pair (team sees opponent's pre-game rating)
            snap_key_team = (team,     date_str, opponent)
            snap_key_opp  = (opponent, date_str, team)

            # On first encounter of this game pair, snapshot BOTH teams' ratings
            # AND last_game_dates (so OppDaysOff is computed correctly)
            if snap_key_team not in pre_game_snapshots:
                pre_game_snapshots[snap_key_team] = current_ratings.get(
                    team, preseason_rating(preseason_ratings.get(team, BASE), self.variant))
            if snap_key_opp not in pre_game_snapshots:
                pre_game_snapshots[snap_key_opp] = current_ratings.get(
                    opponent, preseason_rating(preseason_ratings.get(opponent, BASE), self.variant))

            pre     = pre_game_snapshots[snap_key_team]
            opp_pre = pre_game_snapshots[snap_key_opp]

            # Snapshot last game dates for rest calculation (before either row updates them)
            lgd_snap_key_team = ("lgd", team,     date_str, opponent)
            lgd_snap_key_opp  = ("lgd", opponent, date_str, team)
            if lgd_snap_key_team not in pre_game_snapshots:
                pre_game_snapshots[lgd_snap_key_team] = last_game_date.get(team)
            if lgd_snap_key_opp not in pre_game_snapshots:
                pre_game_snapshots[lgd_snap_key_opp] = last_game_date.get(opponent)

            team_last_date = pre_game_snapshots[lgd_snap_key_team]
            opp_last_date  = pre_game_snapshots[lgd_snap_key_opp]

            # --- GamesPlayed ---
            gp = games_played_count.get(team, 0) + 1
            games_played_count[team] = gp
            df.at[idx, "GamesPlayed"] = gp

            # --- DaysOff ---
            if team_last_date is not None:
                days_off = (game_date - team_last_date).days - 1
            else:
                days_off = (game_date - season_start_ts).days
            df.at[idx, "DaysOff"] = days_off

            # --- OppDaysOff ---
            if opp_last_date is not None:
                opp_days_off = (game_date - opp_last_date).days - 1
            else:
                opp_days_off = (game_date - season_start_ts).days
            df.at[idx, "OppDaysOff"] = opp_days_off

            # --- Rest diffs and adjustments ---
            rd  = days_off - opp_days_off
            ord_ = opp_days_off - days_off
            ra  = rest_adj(rd)
            ora = rest_adj(ord_)
            df.at[idx, "RestDiff"]    = rd
            df.at[idx, "OppRestDiff"] = ord_
            df.at[idx, "RestAdj"]     = ra
            df.at[idx, "OppRestAdj"]  = ora

            # --- Ratings entering this game ---
            df.at[idx, "PreGmRate"]    = pre
            df.at[idx, "OppPreGmRate"] = opp_pre

            # --- Expected win % ---
            ewp = expected_win_pct(pre, opp_pre, ra, ora, home_away)
            df.at[idx, "ExpectedWin%"] = ewp

            # --- Result / MOV ---
            mov = pf - pa
            res = result_value(pf, pa)
            df.at[idx, "MOV"]    = mov
            df.at[idx, "Result"] = res

            # --- Accuracy & Brier ---
            df.at[idx, "Accuracy"] = accuracy(ewp, res)
            df.at[idx, "Brier"]    = brier(ewp, res)

            # --- MOVMult ---
            mm = mov_mult(pf, pa, pre, opp_pre, ot)
            df.at[idx, "MOVMult"] = mm

            # --- K, POMult, Keff ---
            k  = k_factor(gp)
            pm = po_mult(round_val)
            ke = k_eff(k, pm)
            df.at[idx, "K"]      = k
            df.at[idx, "POMult"] = pm
            df.at[idx, "Keff"]   = ke

            # --- Rating change & post-game rating ---
            rc   = rating_change(ke, mm, res, ewp)
            post = pre + rc
            df.at[idx, "RatingChange"] = rc
            df.at[idx, "PostGmRate"]   = post

            # --- Win/Loss flags ---
            is_rs = (game_type == "R")
            is_po = (game_type == "P")
            try:
                rnd = float(round_val) if round_val not in ("RS", "INS") else None
            except (TypeError, ValueError):
                rnd = None

            df.at[idx, "W"]   = int(is_rs and res == 1.0)
            df.at[idx, "L"]   = int(is_rs and res == 0.0)
            df.at[idx, "R1W"] = int(is_po and rnd == 1 and res == 1.0)
            df.at[idx, "R1L"] = int(is_po and rnd == 1 and res == 0.0)
            df.at[idx, "R2W"] = int(is_po and rnd == 2 and res == 1.0)
            df.at[idx, "R2L"] = int(is_po and rnd == 2 and res == 0.0)
            df.at[idx, "R3W"] = int(is_po and rnd == 3 and res == 1.0)
            df.at[idx, "R3L"] = int(is_po and rnd == 3 and res == 0.0)
            df.at[idx, "FW"]  = int(is_po and rnd == 4 and res == 1.0)
            df.at[idx, "FL"]  = int(is_po and rnd == 4 and res == 0.0)

            # --- Update state ---
            current_ratings[team] = post
            last_game_date[team]  = game_date

        return df

    def verify_against_excel(
        self,
        excel_df: pd.DataFrame,
        calculated_df: pd.DataFrame,
        tolerance: float = 1e-4,
        columns_to_check: Optional[list[str]] = None,
    ) -> dict:
        """
        Compare calculated values against Excel ground truth.
        Returns a summary dict; raises ValueError if PostGmRate mismatches exist.

        Parameters
        ----------
        excel_df : the raw Excel RawData sheet (with Excel-calculated values)
        calculated_df : output of process_season()
        tolerance : float mismatch threshold (default 0.0001 per spec §5.3)
        columns_to_check : list of column names to compare (default: key columns)
        """
        if columns_to_check is None:
            columns_to_check = [
                "GamesPlayed", "DaysOff", "OppDaysOff", "RestDiff", "OppRestDiff",
                "RestAdj", "OppRestAdj", "PreGmRate", "OppPreGmRate",
                "ExpectedWin%", "MOV", "Result", "MOVMult",
                "K", "POMult", "Keff", "RatingChange", "PostGmRate",
            ]

        results = {}
        any_postgm_fail = False

        for col in columns_to_check:
            if col not in excel_df.columns or col not in calculated_df.columns:
                results[col] = {"status": "SKIPPED (column missing)"}
                continue

            excel_vals = pd.to_numeric(excel_df[col], errors="coerce")
            calc_vals  = pd.to_numeric(calculated_df[col], errors="coerce")

            diff = (excel_vals - calc_vals).abs()
            mask = diff > tolerance
            n_fail = int(mask.sum())

            if n_fail == 0:
                results[col] = {"status": "PASS", "max_diff": float(diff.max())}
            else:
                # Collect failing rows
                fail_rows = []
                for i in diff[mask].nlargest(5).index:
                    fail_rows.append({
                        "row": int(i),
                        "team": str(excel_df.loc[i, "Team"]) if "Team" in excel_df.columns else "?",
                        "date": str(excel_df.loc[i, "Date"]) if "Date" in excel_df.columns else "?",
                        "excel": float(excel_vals[i]),
                        "calc":  float(calc_vals[i]),
                        "diff":  float(diff[i]),
                    })
                results[col] = {
                    "status": "FAIL",
                    "n_failures": n_fail,
                    "max_diff": float(diff.max()),
                    "worst_rows": fail_rows,
                }
                if col == "PostGmRate":
                    any_postgm_fail = True

        summary = {
            "variant":    self.variant,
            "tolerance":  tolerance,
            "n_rows":     len(excel_df),
            "columns":    results,
            "all_pass":   all(v.get("status") == "PASS" for v in results.values()
                              if v.get("status") != "SKIPPED (column missing)"),
        }

        if any_postgm_fail:
            n = results["PostGmRate"]["n_failures"]
            raise ValueError(
                f"PostGmRate verification FAILED: {n} row(s) exceed tolerance {tolerance}. "
                f"See summary['columns']['PostGmRate'] for details."
            )

        return summary


# ---------------------------------------------------------------------------
# Convenience: build preseason_ratings dict from Excel DataTable sheet
# ---------------------------------------------------------------------------

def load_preseason_ratings_from_excel(
    excel_path: str,
    sheet_name: str = "DataTable",
    team_col: str = "TeamID",
    rating_col: str = "PreSeasonElo",
) -> dict[str, float]:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    return dict(zip(df[team_col], df[rating_col].astype(float)))


# ---------------------------------------------------------------------------
# Convenience: load RawData manual columns only
# ---------------------------------------------------------------------------

MANUAL_COLS = ["Date", "Season", "Type", "Round", "Team", "Opponent",
               "HomeAway", "PointsFor", "PointsAgainst", "OT"]

def load_manual_columns(excel_path: str, sheet_name: str = "RawData") -> pd.DataFrame:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    return df[MANUAL_COLS].copy()


# ---------------------------------------------------------------------------
# CLI: run verification against the 2024-25 Excel file
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "NBA_Continelo_V2_2025.xlsx"
    variant   = sys.argv[2] if len(sys.argv) > 2 else "continelo"

    print(f"=== ContinElo Engine Verification ===")
    print(f"File:    {xlsx_path}")
    print(f"Variant: {variant}\n")

    # Load Excel data
    excel_df       = pd.read_excel(xlsx_path, sheet_name="RawData")
    preseason_dict = load_preseason_ratings_from_excel(xlsx_path)
    manual_df      = excel_df[MANUAL_COLS].copy()

    engine = ContinEloEngine(variant=variant)
    calculated_df = engine.process_season(manual_df, preseason_dict)

    try:
        summary = engine.verify_against_excel(excel_df, calculated_df)
        print("VERIFICATION RESULT:", "✅ ALL PASS" if summary["all_pass"] else "❌ FAILURES FOUND")
        print(f"Rows checked: {summary['n_rows']}\n")

        for col, info in summary["columns"].items():
            status = info.get("status", "?")
            icon = "✅" if status == "PASS" else ("⚠️" if "SKIP" in status else "❌")
            max_d = f"  max_diff={info['max_diff']:.6f}" if "max_diff" in info else ""
            print(f"  {icon} {col:20s} {status}{max_d}")
            if status == "FAIL":
                for r in info.get("worst_rows", []):
                    print(f"       row {r['row']} | {r['team']} {r['date']} | "
                          f"excel={r['excel']:.4f} calc={r['calc']:.4f} diff={r['diff']:.6f}")
    except ValueError as e:
        print(f"\n❌ CRITICAL: {e}")
        sys.exit(1)

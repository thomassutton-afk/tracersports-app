"""
One-off verification tool: diff an original Echo-Ratings-style
workbook's RawData sheet, column by column, against what the engine
produces using the ORIGINAL baseline parameters - regardless of
whatever parameters are currently "active" (tuned) in the database.

This deliberately does NOT read the `ratings` table, because that
table reflects whatever parameters are currently active, which may
have been tuned away from the workbook's original values (see
set_params.py). This script always recomputes the full history
in-memory with the frozen baseline parameters, so it keeps working as
a sanity check no matter how much tuning has happened since.

Usage:
    python3 verify_against_workbook.py /path/to/WNBA_Echo_Ratings_YYYY.xlsx
"""
import sys
import pandas as pd
import db
import engine

DB_PATH = "wnba_elo.db"

COLUMNS = [
    ("PreGmRate", "pre_rate"), ("ExpectedWin%", "expected_win"),
    ("RatingChange", "rating_change"), ("PostGmRate", "post_rate"),
    ("K", "k"), ("MOVMult", "mov_mult"), ("DaysOff", "days_off"),
    ("OppDaysOff", "opp_days_off"), ("RestAdj", "rest_adj"),
]

TOLERANCE = 1e-6


def compute_baseline_ratings() -> pd.DataFrame:
    """Recompute the full history with the frozen original parameters,
    entirely in memory - never touches the `ratings` table."""
    conn = db.connect(DB_PATH)
    games = db.load_games(conn)
    resets = db.load_resets(conn)  # fold/revival resets are data facts, not tuning - always apply
    eng = engine.EloEngine(engine.default_params(), resets=resets)
    rows = []
    for g in games:
        rows.extend(eng.process_game(g))
    return pd.DataFrame(rows)


def main(xlsx_path: str):
    raw = pd.read_excel(xlsx_path, sheet_name="RawData")
    needed = ["Date", "Season", "Team", "Opponent"] + [c for c, _ in COLUMNS]
    raw = raw[needed].copy()

    mine = compute_baseline_ratings()
    mine["date"] = pd.to_datetime(mine["date"])

    merged = raw.merge(
        mine, left_on=["Date", "Season", "Team", "Opponent"],
        right_on=["date", "season", "team", "opponent"], how="outer", indicator=True,
    )

    only_xlsx = (merged["_merge"] == "left_only").sum()
    only_db = (merged["_merge"] == "right_only").sum()
    print(f"Rows only in workbook (missing from DB): {only_xlsx}")
    print(f"Rows only in DB (missing from workbook): {only_db}")

    both = merged[merged["_merge"] == "both"]
    print(f"Rows present in both: {len(both)}\n")

    any_bad = False
    for col_xl, col_db in COLUMNS:
        diff = (both[col_xl] - both[col_db]).abs()
        max_diff = diff.max()
        status = "OK" if max_diff < TOLERANCE else "MISMATCH"
        if status == "MISMATCH":
            any_bad = True
        print(f"  {col_xl:14s} max abs diff: {max_diff:.2e}  [{status}]")

    if any_bad:
        print("\nSome columns diverge beyond tolerance - inspect the worst rows below.")
        print("(If you've tuned parameters with set_params.py, this is expected: the")
        print(" workbook reflects the ORIGINAL values, not your tuned ones. This tool")
        print(" always checks the engine's baseline mode, not your live tuned ratings.)")
        for col_xl, col_db in COLUMNS:
            diff = (both[col_xl] - both[col_db]).abs()
            if diff.max() >= TOLERANCE:
                worst = both.loc[diff.sort_values(ascending=False).index[:5]]
                print(f"\nWorst rows for {col_xl}:")
                print(worst[["Date", "Team", "Opponent", col_xl, col_db]].to_string(index=False))
        sys.exit(1)
    else:
        print("\nAll columns match within tolerance (checked against the original")
        print("baseline parameters, independent of any tuning you've applied).")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 verify_against_workbook.py <path to xlsx>")
        sys.exit(1)
    main(sys.argv[1])

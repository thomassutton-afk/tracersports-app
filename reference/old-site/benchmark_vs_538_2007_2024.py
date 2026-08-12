"""
ContinElo vs. 538/Paine Elo — Out-of-Sample Benchmark (2007-2024)

Same test as benchmark_vs_538.py, but restricted to seasons 2007-2024.
1996-2006 is excluded because that range was used to help tune ContinElo's
K, HCA, and alpha constants -- testing on it would be in-sample and could
make ContinElo look better than it really is on genuinely new data.
This script checks whether the edge over 538/Paine holds up on seasons
the constants were NOT tuned against.

Usage:
    python benchmark_vs_538_2007_2024.py
"""

import os
import psycopg2
import pandas as pd
import numpy as np
from scipy.stats import chi2, wilcoxon

# -------------------------------------------------------------------
# CONNECTION — same credentials pattern as your other scripts
# -------------------------------------------------------------------
DB_HOST = "aws-1-us-west-2.pooler.supabase.com"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres.fhummqxfssfctswzkajj"
DB_PASS = os.environ.get("DB_PASS")
# -------------------------------------------------------------------

VARIANT = "continelo"   # change to "elo" to test the reset variant instead
SEASON_START = 2007     # excludes 1996-2006 (the constant-tuning window)
SEASON_END   = 2024     # last complete season in the 538/Paine archive as of July 2026
FTE_URL = "https://raw.githubusercontent.com/Neil-Paine-1/NBA-elo/main/nba_elo.csv"


def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )


def fetch_continelo_data():
    print(f"Pulling {VARIANT} games ({SEASON_START}-{SEASON_END}) from Supabase...")
    conn = get_connection()
    query = """
        SELECT date, season, team_id, opponent_id, home_away,
               points_for, points_against, type, round,
               expected_win_pct, result
        FROM games
        WHERE variant = %s
          AND season BETWEEN %s AND %s
        ORDER BY date, team_id
    """
    df = pd.read_sql(query, conn, params=(VARIANT, SEASON_START, SEASON_END))
    conn.close()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    print(f"  {len(df):,} rows pulled")
    return df


def fetch_fte_data():
    print("Downloading 538/Paine Elo dataset...")
    df = pd.read_csv(FTE_URL)
    print(f"  {len(df):,} rows total, {df['date'].min()} to {df['date'].max()}")
    complete = df[(df["season"] >= SEASON_START) & (df["season"] <= SEASON_END)].copy()
    n_seasons = complete["season"].nunique()
    print(f"  {len(complete):,} rows in the {SEASON_START}-{SEASON_END} window "
          f"({n_seasons} seasons)")
    if n_seasons < (SEASON_END - SEASON_START + 1):
        print("  WARNING: fewer seasons present than expected — check for "
              "incomplete/missing seasons before trusting results.")
    return complete


# Empirically-verified team code mapping (see the benchmark report, Section 5)
def to_538(team_id, season):
    if team_id == "OKC":
        return "SEA" if season <= 2008 else "OKC"
    if team_id == "MEM":
        return "VAN" if season <= 2001 else "MEM"
    if team_id == "BRK":
        return "NJN" if season <= 2012 else "BRK"
    if team_id == "NO":
        if season <= 2002:
            return "CHH"
        if season in (2006, 2007):
            return "NOK"
        return "NOP"
    if team_id == "CHA":
        return "CHO"
    if team_id == "WAS":
        return "WSB" if season <= 1997 else "WAS"
    simple = {"GS": "GSW", "NY": "NYK", "PHX": "PHO", "SA": "SAS"}
    return simple.get(team_id, team_id)


def join_datasets(ce, fte):
    print("\nJoining on date + team + opponent...")
    ce = ce.copy()
    # Neutral-site games (home_away == 'N') map straight through --
    # to_538() only depends on team_id/season, and the join key below
    # doesn't use home_away at all, so N-flagged games join correctly.
    ce["team_538"] = ce.apply(lambda r: to_538(r["team_id"], r["season"]), axis=1)
    ce["opponent_538"] = ce.apply(lambda r: to_538(r["opponent_id"], r["season"]), axis=1)
    ce["jkey"] = ce["date"] + "_" + ce["team_538"] + "_" + ce["opponent_538"]

    fte = fte.copy()
    fte["jkey"] = fte["date"].astype(str) + "_" + fte["team1"] + "_" + fte["team2"]

    merged = ce.merge(fte[["jkey", "elo_prob1", "score1", "score2"]], on="jkey", how="left")
    matched = merged["elo_prob1"].notna().sum()
    total = len(merged)
    print(f"  Matched: {matched:,} / {total:,}  ({matched/total*100:.3f}%)")
    if matched / total < 0.999:
        print("  WARNING: match rate below 99.9% — the team code mapping may need "
              "updating for this data vintage. Check merged[merged.elo_prob1.isna()] "
              "for unmatched rows before trusting results.")
    return merged.dropna(subset=["elo_prob1"]).copy()


def compute_metrics(m):
    m["ce_correct"] = ((m["expected_win_pct"] >= 0.5) & (m["result"] == 1)) | \
                       ((m["expected_win_pct"] < 0.5) & (m["result"] == 0))
    m["ce_brier"] = (m["expected_win_pct"] - m["result"]) ** 2
    m["fte_correct"] = ((m["elo_prob1"] >= 0.5) & (m["result"] == 1)) | \
                        ((m["elo_prob1"] < 0.5) & (m["result"] == 0))
    m["fte_brier"] = (m["elo_prob1"] - m["result"]) ** 2
    m["brier_diff"] = m["ce_brier"] - m["fte_brier"]
    return m


def print_overall(m):
    print("\n" + "=" * 60)
    print(f"OVERALL — {SEASON_START}-{SEASON_END} (out-of-sample), identical games")
    print("=" * 60)
    print(f"{'Model':<25}{'Accuracy':>12}{'Brier':>12}")
    print(f"{'ContinElo (' + VARIANT + ')':<25}"
          f"{m['ce_correct'].mean()*100:>11.2f}%{m['ce_brier'].mean():>12.4f}")
    print(f"{'538 / Paine Elo':<25}"
          f"{m['fte_correct'].mean()*100:>11.2f}%{m['fte_brier'].mean():>12.4f}")
    print(f"\nGames compared: {len(m):,}")


def print_per_season(m):
    print("\n" + "=" * 60)
    print("PER-SEASON")
    print("=" * 60)
    s = m.groupby("season").agg(
        games=("ce_correct", "count"),
        ce_acc=("ce_correct", "mean"),
        fte_acc=("fte_correct", "mean"),
        ce_brier=("ce_brier", "mean"),
        fte_brier=("fte_brier", "mean"),
    )
    s["ce_acc"] = (s["ce_acc"] * 100).round(2)
    s["fte_acc"] = (s["fte_acc"] * 100).round(2)
    s["ce_brier"] = s["ce_brier"].round(4)
    s["fte_brier"] = s["fte_brier"].round(4)
    pd.set_option("display.width", 140)
    print(s)
    ce_acc_wins = (s["ce_acc"] > s["fte_acc"]).sum()
    ce_brier_wins = (s["ce_brier"] < s["fte_brier"]).sum()
    print(f"\nContinElo had better accuracy in {ce_acc_wins}/{len(s)} seasons")
    print(f"ContinElo had better (lower) Brier in {ce_brier_wins}/{len(s)} seasons")
    return s


def run_significance_tests(m):
    print("\n" + "=" * 60)
    print("SIGNIFICANCE TESTS")
    print("=" * 60)

    # McNemar's test — game-level accuracy disagreements
    ce_right_fte_wrong = ((m["ce_correct"]) & (~m["fte_correct"])).sum()
    fte_right_ce_wrong = ((m["fte_correct"]) & (~m["ce_correct"])).sum()
    n_disc = ce_right_fte_wrong + fte_right_ce_wrong
    mcnemar_stat = (abs(ce_right_fte_wrong - fte_right_ce_wrong) - 1) ** 2 / n_disc
    p_mcnemar = 1 - chi2.cdf(mcnemar_stat, df=1)
    print("\nMcNemar's test (accuracy, game-level)")
    print(f"  ContinElo right / 538 wrong: {ce_right_fte_wrong:,}")
    print(f"  538 right / ContinElo wrong: {fte_right_ce_wrong:,}")
    print(f"  chi2 = {mcnemar_stat:.2f}, p = {p_mcnemar:.4f}")

    # Wilcoxon signed-rank — game-level Brier differences
    _, p_wilcoxon = wilcoxon(m["brier_diff"])
    print(f"\nWilcoxon signed-rank (Brier, game-level): p = {p_wilcoxon:.4f}")

    # Season-level paired bootstrap — most conservative check
    season_diffs = m.groupby("season")["brier_diff"].mean().values
    print(f"\nSeason-level mean Brier diff (ContinElo - 538): {season_diffs.mean():.5f}")
    print(f"  (negative = ContinElo better on average)")
    print(f"  ContinElo had the lower-Brier season in "
          f"{(season_diffs < 0).sum()}/{len(season_diffs)} seasons")

    rng = np.random.default_rng(42)
    boot_means = np.array([
        rng.choice(season_diffs, size=len(season_diffs), replace=True).mean()
        for _ in range(10000)
    ])
    ci_low, ci_high = np.percentile(boot_means, [2.5, 97.5])
    print(f"  95% bootstrap CI on season-level mean diff: [{ci_low:.5f}, {ci_high:.5f}]")
    print(f"  CI excludes zero (statistically significant): {ci_low > 0 or ci_high < 0}")


def main():
    ce = fetch_continelo_data()
    fte = fetch_fte_data()
    merged = join_datasets(ce, fte)
    merged = compute_metrics(merged)

    print_overall(merged)
    season_summary = print_per_season(merged)
    run_significance_tests(merged)

    merged.to_csv("benchmark_merged_2007_2024.csv", index=False)
    season_summary.to_csv("benchmark_by_season_2007_2024.csv")
    print("\nSaved: benchmark_merged_2007_2024.csv, benchmark_by_season_2007_2024.csv")


if __name__ == "__main__":
    main()

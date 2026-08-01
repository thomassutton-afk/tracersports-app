#!/usr/bin/env python3
"""
platt_calibration.py

Fits a Platt scaling correction to the Elo model's predictions: a simple
2-parameter logistic regression of actual outcome against the model's own
predicted win probability, in log-odds space. This answers two separate
questions the raw accuracy numbers can't:

  1. Is the model's confidence curve the right SHAPE overall (slope), or
     is it systematically too flat/too steep?
  2. Is there a constant BIAS (intercept) -- e.g. home/away or D1/D2
     handling pushing everything a bit in one direction?

Only needs numpy (already installed alongside pandas). No sklearn/scipy
required.

METHOD
------
For each game, let p = the model's ExpectedWin% and y = actual Result (0/1).
Convert p to natural log-odds: x = ln(p/(1-p)).
Fit y ~ sigmoid(a*x + b) by Newton's method (2 parameters, converges in a
handful of iterations since this is a small, convex problem).

  a == 1 and b == 0  -> the model is already perfectly calibrated
  a > 1              -> the model is UNDERconfident -- real outcomes swing
                        more sharply with rating gap than predicted; a
                        recalibrated model should push probabilities
                        further from 50%
  a < 1              -> the model is OVERconfident -- probabilities should
                        be pulled back toward 50%
  b != 0             -> a constant shift in one direction regardless of
                        rating gap (rarely expected in a home/away-
                        symmetric dataset like this one; investigate if
                        it's large)

The fitted (a, b) also translate back into the Elo formula's own units:
  effective divisor = 400 / a   (replaces the "400" in the expected-score formula)
  effective point bias = b * 400 / ln(10)   (an unaccounted-for rating shift, in Elo points)

USAGE
-----
    python platt_calibration.py cbb_1996.db
"""

import argparse
import math
import sqlite3
from pathlib import Path

import numpy as np


def fit_platt(x: np.ndarray, y: np.ndarray, iters=50):
    theta = np.array([1.0, 0.0])  # start at "no correction": a=1, b=0
    X = np.column_stack([x, np.ones_like(x)])
    for _ in range(iters):
        z = X @ theta
        q = 1 / (1 + np.exp(-z))
        grad = X.T @ (q - y) / len(y)
        w = q * (1 - q)
        w = np.clip(w, 1e-6, None)
        H = (X * w[:, None]).T @ X / len(y)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        theta = theta - step
        if np.max(np.abs(step)) < 1e-10:
            break
    return theta


def metrics(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    brier = np.mean((p - y) ** 2)
    logloss = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    acc = np.mean(((p >= 0.5) & (y == 1)) | ((p < 0.5) & (y == 0)))
    return acc, brier, logloss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db_path", type=Path)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db_path)
    rows = conn.execute("SELECT expected_win_pct, result FROM elo_ledger").fetchall()
    conn.close()

    p_raw = np.array([r[0] for r in rows])
    y = np.array([r[1] for r in rows])

    ties = np.sum(y == 0.5)
    if ties:
        print(f"Excluding {ties} tie rows (Result=0.5) -- not meaningful for a win/loss fit.\n")
    mask = y != 0.5
    p_raw, y = p_raw[mask], y[mask]

    p_clipped = np.clip(p_raw, 1e-6, 1 - 1e-6)
    x = np.log(p_clipped / (1 - p_clipped))  # natural log-odds

    a, b = fit_platt(x, y)

    print(f"Fitted correction:  a (slope) = {a:.4f}    b (intercept) = {b:.4f}\n")

    if a > 1.05:
        print(f"a > 1: the model is UNDERconfident -- real outcomes separate more sharply")
        print(f"       by rating gap than the raw probabilities suggest.")
    elif a < 0.95:
        print(f"a < 1: the model is OVERconfident -- probabilities should be pulled")
        print(f"       back toward 50% across the board.")
    else:
        print(f"a is close to 1 -- the overall confidence scale looks about right.")

    effective_divisor = 400 / a
    effective_bias = b * 400 / math.log(10)
    print(f"\nIn the Elo formula's own units, this suggests:")
    print(f"  effective divisor:     {effective_divisor:.1f}   (currently hardcoded as 400)")
    print(f"  effective point bias:  {effective_bias:+.1f} Elo points  (ideally ~0 in a symmetric dataset)")

    # recalibrated predictions
    p_recal = 1 / (1 + np.exp(-(a * x + b)))

    print("\n=== Before vs. after recalibration ===")
    for label, p in [("Raw model", p_raw), ("Platt-recalibrated", p_recal)]:
        acc, brier, ll = metrics(p, y)
        print(f"  {label:<20} accuracy {100*acc:.1f}%   brier {brier:.4f}   log loss {ll:.4f}")

    print("\n=== Calibration buckets, recalibrated ===")
    print(f"  {'Bucket':<12} {'Games':>7} {'Predicted avg':>15} {'Actual win rate':>17}")
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    for lo, hi in buckets:
        m = (p_recal >= lo) & (p_recal < hi)
        if m.sum():
            print(f"  {lo:.0%}-{hi:.0%}     {m.sum():>7} {100*p_recal[m].mean():>14.1f}% {100*y[m].mean():>16.1f}%")


if __name__ == "__main__":
    main()

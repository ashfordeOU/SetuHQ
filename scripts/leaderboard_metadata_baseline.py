#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A floor for the real-TOI leaderboard: a method that never looks at a light curve.

    python scripts/leaderboard_metadata_baseline.py     # writes docs/leaderboard/submissions/metadata-baseline.json

It reads only the public inputs (docs/leaderboard/tuning_inputs.json): for every held-out star the TOI number,
period, duration, ephemeris errors and epoch, the fields a blind search is given anyway. A logistic regression
(numpy, iteratively reweighted least squares with a small ridge; no randomness) is fitted on the tuning half's CP/KP
against FP TOIs. Its decision threshold maximises Youden's J on 5-fold cross-validated tuning predictions (folds by
TOI order). Held-out stars it predicts to be planets get one event exactly on the published ephemeris, passed and
unflagged; the others get none. The method ignores the light curve, so on the inverted and scrambled controls it
reports the same events: its control false-alarm rate is honest, and high.

The point is a floor. If light-curve methods do not beat it, the benchmark's J mostly measures how separable false
positives are from catalogue metadata (a TOI's number, for example, tracks when it was alerted), not how well a
method reads light curves.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from setuhq import leaderboard as L  # noqa: E402

FEATURES = ("TOI number", "log10 period", "duration (h)", "log10 period error", "log10 mid-time error", "mid-time (BTJD)")
RIDGE = 1e-3
FOLDS = 5


def features(t: dict) -> list[float]:
    def lg(x, floor):
        return math.log10(max(x, floor)) if x is not None else math.nan

    return [float(t["toi"]), lg(t["period"], 1e-3), t["duration_hours"] if t["duration_hours"] is not None else math.nan,
            lg(t["period_err"], 1e-7), lg(t["tranmid_err"], 1e-6),
            t["tranmid_bjd"] - 2457000.0 if t["tranmid_bjd"] is not None else math.nan]


class Logistic:
    """Standardised features, an intercept, IRLS (Newton) with a ridge on the slopes. Missing values: the training mean."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Logistic":
        self.mu = np.nanmean(X, axis=0)
        X = np.where(np.isnan(X), self.mu, X)
        self.sd = X.std(axis=0)
        self.sd[self.sd == 0] = 1.0
        Z = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])
        w = np.zeros(Z.shape[1])
        reg = RIDGE * np.eye(Z.shape[1])
        reg[0, 0] = 0.0
        for _ in range(100):
            p = 1 / (1 + np.exp(-Z @ w))
            g = Z.T @ (p - y) + reg @ w
            H = Z.T @ (Z * (p * (1 - p))[:, None]) + reg
            step = np.linalg.solve(H, g)
            w -= step
            if np.max(np.abs(step)) < 1e-10:
                break
        self.w = w
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.where(np.isnan(X), self.mu, X)
        Z = np.hstack([np.ones((len(X), 1)), (X - self.mu) / self.sd])
        return 1 / (1 + np.exp(-Z @ self.w))


def best_threshold(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """The threshold on cross-validated scores that maximises J on the tuning half; ties go to the higher threshold."""
    best = (-2.0, 1.0)
    for th in sorted(set(np.round(p, 6))):
        j = (p[y == 1] >= th).mean() + (p[y == 0] < th).mean() - 1
        if j > best[0] + 1e-12 or (abs(j - best[0]) <= 1e-12 and th > best[1]):
            best = (j, th)
    return best


def build_submission() -> dict:
    """The baseline's submission, built from the public inputs only; the same bytes on every run."""
    inputs = json.loads(L.INPUTS.read_text())
    sample = L.load_sample()
    if L.inputs_sha256(inputs) != L.inputs_sha256(L.public_inputs(sample)):
        raise SystemExit("tuning_inputs.json does not match the frozen sample")
    train = sorted((t for t in inputs["tuning"] if t["class"] in ("positive", "fp")), key=lambda t: float(t["toi"]))
    X = np.array([features(t) for t in train], float)
    y = np.array([t["class"] == "positive" for t in train], float)
    cv = np.empty(len(train))
    for k in range(FOLDS):
        test = np.arange(len(train)) % FOLDS == k
        cv[test] = Logistic().fit(X[~test], y[~test]).predict(X[test])
    j_cv, th = best_threshold(cv, y)
    model = Logistic().fit(X, y)
    held = inputs["held_out"]
    score = model.predict(np.array([features(t) for t in held], float))
    # Searched only where the benchmark had a light curve to search (a SPOC 2-minute sector): the per-star rows' no_data
    # field, a property of the star in MAST, not a label. So the floor's control, small-planet and reliability columns
    # count the same stars as the Probes'. J does not depend on it (it is over the searchable set).
    searchable = L.benchmark_searchable(json.loads(L.BENCHMARK.read_text()))
    preds = []
    for t, s in zip(held, score):
        if t["toi"] not in searchable:
            preds.append({"toi": t["toi"], "tic": t["tic"], "searched": False, "events": [], "controls": None})
            continue
        ev = [{"t_center": round(t["tranmid_bjd"] - 2457000.0, 6), "duration_hours": t["duration_hours"],
               "period_days": t["period"], "passed": True, "flags": []}] if s >= th else []
        preds.append({"toi": t["toi"], "tic": t["tic"], "searched": True, "events": ev,
                      "controls": {"inverted": [dict(e) for e in ev], "scrambled": [dict(e) for e in ev]}})
    sub = {"format": L.FORMAT, "id": L.FLOOR_ID, "name": "Metadata only, no light curve (a floor)", "kind": "baseline",
           "submitter": "exoplan (seeded baseline)", "sample_sha256": sample["sha256"], "inputs_sha256": L.inputs_sha256(inputs),
           "tuned_on": "tuning", "scope": "held_out",
           "provenance": {
               "method": ("Never reads a light curve. A logistic regression on the public TOI number, period, duration, "
                          "ephemeris errors and epoch, fitted on the tuning half's CP/KP against FP TOIs; held-out stars "
                          f"above the threshold ({th:.3f}, chosen by 5-fold cross-validated J = {j_cv:.2f} on the tuning "
                          "half) get one event on the published ephemeris. Stars the benchmark could not search (no SPOC "
                          "2-minute light curve) are submitted as not searched. The same events stand on the controls, because "
                          "the method ignores the light curve. A floor, not a vetter."),
               "code_version": "scripts/leaderboard_metadata_baseline.py",
               "generated_from": [{"file": "docs/leaderboard/tuning_inputs.json",
                                   "sha256": hashlib.sha256(L.INPUTS.read_bytes()).hexdigest()},
                                  {"file": str(L.BENCHMARK.relative_to(ROOT)), "rows": "per_star no_data only (searchability)"}],
               "features": list(FEATURES), "threshold": round(th, 6), "tuning_cv_j": round(j_cv, 4),
               "coefficients": [round(float(c), 6) for c in model.w]},
           "predictions": preds}
    return sub


def main() -> int:
    sub = build_submission()
    preds, th, j_cv = sub["predictions"], sub["provenance"]["threshold"], sub["provenance"]["tuning_cv_j"]
    out = L.SUBMISSIONS / f"{L.FLOOR_ID}.json"
    out.write_text(json.dumps(sub, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"wrote {out.relative_to(ROOT)}: threshold {th:.3f}, tuning CV J {j_cv:.2f}, "
          f"{sum(1 for p in preds if p['events'])} of {len(preds)} held-out stars predicted planets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

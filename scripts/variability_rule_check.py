# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Measure the coherent-variable rule and its red-noise null on synthetic TESS-like light curves.

Writes docs/sweep/variability_rule_check.json, which the #/variables page quotes in its limits. Each case is
20 light curves on one sector's 2-minute cadence (27.4 d with a 1-day gap), seeded, so the numbers reproduce:

    python scripts/variability_rule_check.py

* a sinusoid (300 ppm; periods 0.5 to 3 d) in white noise (200 ppm per point);
* red noise alone (an AR(1) process, 1-day correlation time, 600 ppm) plus the white noise;
* the same sinusoid in that strong red noise.

For each light curve: does the rule call it a variable (variables.classify_variability), and does its own
red-noise null (variables.variability_null) pass the rule.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from setuhq.variables import classify_variability, variability, variability_null  # noqa: E402

OUT = ROOT / "docs" / "sweep" / "variability_rule_check.json"
N = 20
SEED = 20261020
WHITE, RED, TAU, AMP = 2e-4, 6e-4, 1.0, 3e-4
PERIODS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]


def main() -> int:
    t = np.arange(0, 27.4, 2 / 1440)
    t = t[(t < 13) | (t > 14)]
    rng = np.random.default_rng(SEED)

    def red():
        dt = np.diff(t, prepend=t[0])
        a = np.exp(-dt / TAU)
        e = rng.normal(0, 1, t.size)
        x = np.zeros(t.size)
        for i in range(1, t.size):
            x[i] = a[i] * x[i - 1] + np.sqrt(1 - a[i] ** 2) * e[i]
        return RED * x

    def sine(k):
        return AMP * np.sin(2 * np.pi * t / PERIODS[k % len(PERIODS)] + rng.uniform(0, 2 * np.pi))

    cases = {
        "sinusoid_in_white_noise": lambda k: 1 + rng.normal(0, WHITE, t.size) + sine(k),
        "red_noise_alone": lambda k: 1 + rng.normal(0, WHITE, t.size) + red(),
        "sinusoid_in_strong_red_noise": lambda k: 1 + rng.normal(0, WHITE, t.size) + red() + sine(k),
    }
    out = {"n": N, "seed": SEED, "white_ppm": WHITE * 1e6, "red_ppm": RED * 1e6, "red_tau_days": TAU,
           "sinusoid_ppm": AMP * 1e6, "periods_days": PERIODS, "baseline_days": 27.4, "gap_days": [13, 14],
           "script": "scripts/variability_rule_check.py", "cases": {}}
    for name, gen in cases.items():
        variable = null = 0
        for k in range(N):
            f = gen(k)
            v = classify_variability(variability(t, f))
            variable += bool(v and v["class"] == "variable")
            null += int(variability_null(t, f, [], seed=k)["variable"])
        out["cases"][name] = {"variable": variable, "null_variable": null}
        print(f"{name:30s} called variable {variable}/{N}; its red-noise null passes {null}/{N}")
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

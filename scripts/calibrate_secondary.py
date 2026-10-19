#!/usr/bin/env python3
"""Calibrate the all-phase weak-secondary search (dvtests.secondary_search) on white noise, and reproduce the
false-alarm and detection rates quoted in the code and the README.

The scan's statistic at each box position is (baseline − mean flux in the box)/(σ/√n). Its maximum over the phase
is a look-elsewhere statistic whose distribution has to be simulated: neighbouring boxes overlap (the coarse step is
a quarter duration), the peak is refined in steps of a fortieth of a duration, and the robust spread (MAD) used to
normalise it is itself estimated from the same few dozen to few hundred positions. For a grid of position counts
(set by P/T14), at 2- and 10-minute cadence, this script simulates pure white-noise light curves and records the
99.9% quantiles of

* q_dip = (largest dip statistic) / (robust spread): the threshold for ``secondary_any_phase``;
* q_abs = (largest |excursion|, dip or brightening) / (robust spread): the white-noise gate of the reduced FPP.

The larger of the two cadences is kept at each position count. It also measures the effective number of
independent positions N_eff, from P(max > z) = 1 − Φ(z)^N_eff at the true σ, which the reduced FPP's null
likelihood uses. Output: ``docs/results/secondary_calibration.json``, whose table is copied into
``exoplan.dvtests.SECONDARY_TABLE``.

    python scripts/calibrate_secondary.py               # the table (about 10 minutes) and the rates
    python scripts/calibrate_secondary.py --rates-only  # only the reproduced rates
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.stats import beta, norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from exoplan import dvtests  # noqa: E402

DUR = 0.125
DAYS = 27.0
PERIODS = (1.0, 1.5, 2.5, 4.0, 6.27, 10.0, 13.0)


def clopper_pearson(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    a = (1 - level) / 2
    lo = 0.0 if k == 0 else float(beta.ppf(a, k, n - k + 1))
    hi = 1.0 if k == n else float(beta.ppf(1 - a, k + 1, n - k))
    return lo, hi


def white_scans(period: float, cadence_min: float, n: int, seed0: int):
    t = np.arange(0.0, DAYS, cadence_min / 1440.0)
    q_dip, q_abs, raw, positions = [], [], [], None
    for k in range(n):
        rng = np.random.default_rng(seed0 + k)
        f = 1.0 + rng.normal(0.0, 1e-3, t.size)
        s = dvtests.secondary_search(t, f, period=period, t0=0.3, duration=DUR, noise=1e-3)
        rs = s["scan_robust_sigma"]
        q_dip.append(s["snr"] / rs)
        q_abs.append(max(s["snr"], s["max_brightening_snr"]) / rs)
        raw.append(s["snr"])
        positions = s["n_trials"]
    return positions, np.array(q_dip), np.array(q_abs), np.array(raw)


def table(n_sims: int) -> list[dict]:
    rows = []
    for period in PERIODS:
        best = None
        for cadence in (2.0, 10.0):
            positions, q_dip, q_abs, raw = white_scans(period, cadence, n_sims, 10_000 * int(period * 100) + int(cadence))
            z = float(np.quantile(q_dip, 0.999))
            # N_eff at the true σ: P(raw max > zz) = 1 − Φ(zz)^N_eff, at zz = the 99% quantile of the raw maximum
            zz = float(np.quantile(raw, 0.99))
            n_eff = math.log(0.99) / math.log(norm.cdf(zz))
            row = {"period": period, "cadence_min": cadence, "positions": positions, "q_dip_999": z,
                   "q_abs_999": float(np.quantile(q_abs, 0.999)), "n_eff": n_eff, "n_sims": n_sims}
            print(row, flush=True)
            if best is None or row["q_dip_999"] > best["q_dip_999"]:
                best = dict(row, q_abs_999=max(row["q_abs_999"], (best or row)["q_abs_999"]),
                            n_eff=max(row["n_eff"], (best or row)["n_eff"]))
            else:
                best["q_abs_999"] = max(best["q_abs_999"], row["q_abs_999"])
                best["n_eff"] = max(best["n_eff"], row["n_eff"])
        rows.append(best)
    return rows


def rates(n_clean: int = 3000) -> dict:
    """The rates quoted in the docstrings and the README, reproduced."""
    from test_dvtests import DUR as D, P, T0, _curve, _transits, trapezoid  # noqa: F401

    out = {}
    # 1. secondary false flags on clean planets: the plain 3 x robust rule, the look-elsewhere rule of 0990a12
    #    (z = max(3, isf(0.001/(positions/4)))), and the current rule (the white-noise table), all with the
    #    periodicity and brightening conditions
    plain = loe = current = 0
    for seed in range(n_clean):
        t, f, e = _curve(np.random.default_rng(1000 + seed), events=_transits(1000e-6))
        flags, m = dvtests.extended_vet(t, f, e, period=P, t0=T0, duration=D)
        s = m["secondary"]
        base = s["snr"] > s["max_brightening_snr"] and s["periodic"]
        plain += int(base and s["snr"] > 3 * s["scan_robust_sigma"])
        z = max(3.0, float(norm.isf(1e-3 / (s["n_trials"] * 0.25))))
        loe += int(base and s["snr"] > z * s["scan_robust_sigma"])
        current += int("secondary_any_phase" in flags)
        if seed == 199:
            first200 = {"plain_3x_robust": plain, "lookelsewhere_0990a12": loe, "white_table": current}
    for name, k in (("plain_3x_robust", plain), ("lookelsewhere_0990a12", loe), ("white_table", current)):
        lo, hi = clopper_pearson(k, n_clean)
        out[f"secondary_false_flags_{name}"] = {"k": k, "n": n_clean, "rate": k / n_clean, "ci95": [lo, hi],
                                                "k_first_200_seeds": first200[name]}
        print(name, k, "/", n_clean, f"95% CI {lo:.4f}-{hi:.4f}; first 200 seeds: {first200[name]}", flush=True)
    # 2. odd/even timing: a 15-minute offset over ten epochs, and clean four-epoch planets
    det_lin = det_fit = 0
    for seed in range(20):
        t, f, e = _curve(np.random.default_rng(2000 + seed), events=_transits(3000e-6, odd_shift=15 / 1440),
                         cadence_min=2.0, noise=3e-4, shape="trapezoid")
        times = dvtests.epoch_times(t, f, e, period=P, t0=T0, duration=D, template=dvtests.shape_template(None, D))
        r = dvtests.timing_test(times)
        oe = r["odd_even"]
        lin_red = r["linear"]["chi2"] / r["linear"]["dof"]
        n = np.array([x["epoch"] for x in times], float)
        tt = np.array([x["t_mid"] for x in times])
        ss = np.array([x["sigma"] for x in times])
        b, cov, _ = dvtests._wls(np.column_stack([np.ones_like(n), n, n % 2]), tt, ss)
        raw = abs(b[2]) / math.sqrt(cov[2, 2])
        det_lin += int(raw / math.sqrt(max(1.0, lin_red)) > 3)
        det_fit += int(oe["significant"])
    clean = 0
    for seed in range(200):
        t, f, e = _curve(np.random.default_rng(3000 + seed), days=15.0, events=_transits(3000e-6, days=15.0),
                         cadence_min=2.0, noise=3e-4, shape="trapezoid")
        flags, _ = dvtests.extended_vet(t, f, e, period=P, t0=T0, duration=D)
        clean += int("odd_even_timing" in flags)
    out["odd_even_timing"] = {"offset_15min_detected_linear_inflation": det_lin, "offset_15min_detected_fit_inflation":
                              det_fit, "of": 20, "clean_4_epoch_flagged": clean, "clean_n": 200}
    print(out["odd_even_timing"], flush=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sims", type=int, default=20000, help="white-noise scans per period and cadence")
    ap.add_argument("--rates-only", action="store_true")
    ap.add_argument("--out", default="docs/results/secondary_calibration.json")
    args = ap.parse_args(argv)
    out = Path(args.out)
    data = json.loads(out.read_text()) if out.exists() else {}
    if not args.rates_only:
        data["table"] = table(args.sims)
        data["note"] = ("99.9% quantiles over white-noise scans (27 days, T14 = 0.125 d, 2- and 10-minute cadence, the "
                        "larger kept); positions = coarse box positions of secondary_search")
    data["rates"] = rates()
    out.write_text(json.dumps(data, indent=1, default=int) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

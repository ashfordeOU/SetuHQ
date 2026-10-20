# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Synthetic light curves shared by the S2 tests."""

import numpy as np

from setuhq.dvtests import trapezoid
from setuhq.lightcurve import LightCurve


def trapezoid_lc(*, seed, period, t0, duration, depth, noise, days=27.0, cadence_min=2.0, secondary=0.0,
                 secondary_phase=0.5, gap=(13.2, 14.2), target="TIC 123"):
    """A TESS-like light curve: trapezoid transits (and optional secondaries), white noise, a mid-sector gap."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, cadence_min / 1440.0)
    f = 1 + rng.normal(0, noise, t.size)
    for n in range(int(days / period) + 2):
        f -= depth * trapezoid(t - (t0 + n * period), duration)
        if secondary:
            f -= secondary * trapezoid(t - (t0 + (n + secondary_phase) * period), duration)
    keep = ~((t > gap[0]) & (t < gap[1])) if gap else np.ones(t.size, bool)
    return LightCurve(target=target, mission="TESS", time=t[keep], flux=f[keep], flux_err=np.full(keep.sum(), noise),
                      provenance={"sector": 1, "time_unit": "BTJD"})

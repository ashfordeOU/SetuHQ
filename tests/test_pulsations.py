# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Pulsations (setuhq.pulsations): pre-whitening, S/N stop, combinations, background, numax/Δν, type, null. Offline."""

import math

import numpy as np
import pytest

from setuhq import pulsations as pu

CAD = 2.0 / 1440.0


def _series(freqs, days=20.0, noise=5e-4, seed=0, gap=True):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, CAD)
    if gap:
        t = t[(t < days / 2 - 0.5) | (t > days / 2 + 0.5)]
    y = 1.0 + rng.normal(0, noise, t.size)
    for f, a, ph in freqs:
        y += a * np.sin(2 * math.pi * (f * t + ph))
    return t, y


def test_amplitude_spectrum_gives_semi_amplitude():
    t, y = _series([(10.0, 1e-3, 0.1)], noise=0)
    f, a = pu.amplitude_spectrum(t, y, fmin=9, fmax=11)
    assert f[np.argmax(a)] == pytest.approx(10.0, abs=0.01)
    assert a.max() == pytest.approx(1e-3, rel=0.03)


def test_prewhitening_recovers_frequencies_amplitudes_and_phases():
    true = [(12.3456, 2e-3, 0.2), (15.789, 8e-4, 0.7), (1.234, 5e-4, 0.4), (31.1, 3e-4, 0.9)]
    t, y = _series(true)
    r = pu.prewhiten(t, y, fmax=60)
    sig = [x for x in r["frequencies"] if x["significant"]]
    assert len(sig) == 4
    for f, a, ph in true:
        x = min(sig, key=lambda z: abs(z["frequency"] - f))
        assert abs(x["frequency"] - f) < 5 * x["sigma_frequency"]
        assert x["amplitude"] == pytest.approx(a, abs=4 * x["sigma_amplitude"])
        # the phase is referred to the first time stamp, which is t = 0 here
        assert min(abs(x["phase"] - ph), 1 - abs(x["phase"] - ph)) < 0.02
    assert "S/N" in r["stop"] and r["stop"].endswith(f"< {r['snr_stop']:g}")
    assert all(x["snr"] >= 4 for x in sig)
    assert r["rayleigh"] == pytest.approx(1 / r["baseline_days"])


def test_uncertainties_follow_montgomery_odonoghue():
    t, y = _series([(10.0, 1e-3, 0.0)], noise=1e-3)
    x = pu.prewhiten(t, y, fmin=5, fmax=15)["frequencies"][0]
    n, T = t.size, t[-1] - t[0]
    assert x["sigma_amplitude"] == pytest.approx(math.sqrt(2 / n) * 1e-3, rel=0.1)
    assert x["sigma_frequency"] == pytest.approx(math.sqrt(6 / n) * 1e-3 / (math.pi * T * x["amplitude"]), rel=0.1)


def test_combination_and_harmonic_flags():
    f1, f2 = 10.1, 13.7
    t, y = _series([(f1, 3e-3, 0), (f2, 2e-3, 0.3), (f1 + f2, 6e-4, 0.1), (2 * f1, 5e-4, 0.5)], noise=3e-4)
    r = pu.prewhiten(t, y, fmax=60)
    by = {round(x["frequency"], 1): x for x in r["frequencies"]}
    assert by[round(f1 + f2, 1)]["combination"] in ("f1+f2", "f2+f1")
    assert by[round(2 * f1, 1)]["combination"] == "2f1"
    assert by[round(f1, 1)]["combination"] is None


def test_white_noise_gives_few_false_frequencies():
    t, y = _series([], noise=1e-3, seed=3)
    r = pu.prewhiten(t, y, fmax=100)
    assert r["n_significant"] <= 1


def test_ar1_surrogate_keeps_variance_and_correlation():
    rng = np.random.default_rng(1)
    t = np.arange(0, 10, CAD)
    x = np.zeros(t.size)
    for i in range(1, t.size):
        x[i] = 0.8 * x[i - 1] + rng.normal(0, 1e-3)
    y = pu.ar1_surrogate(t, x, seed=2)
    assert np.std(y) == pytest.approx(np.std(x), rel=0.15)
    assert np.corrcoef(y[:-1], y[1:])[0, 1] == pytest.approx(0.8, abs=0.05)


def test_false_frequency_rate_on_red_noise_is_reported():
    rng = np.random.default_rng(4)
    t = np.arange(0, 8, CAD)
    x = np.zeros(t.size)
    for i in range(1, t.size):
        x[i] = 0.9 * x[i - 1] + rng.normal(0, 3e-4)
    r = pu.false_frequency_rate(t, x, n_surrogates=3, seed=1, fmax=40)
    assert r["n_surrogates"] == 3 and len(r["counts"]) == 3 and r["mean_false_per_lightcurve"] is not None


def test_power_density_is_normalised_by_parseval():
    rng = np.random.default_rng(5)
    t = np.arange(0, 10, CAD)
    y = rng.normal(0, 1e-3, t.size)
    nu, p = pu.power_density(t, y)
    assert np.sum(p) * (nu[1] - nu[0]) == pytest.approx(np.var(y), rel=1e-6)


def test_background_fit_recovers_a_harvey_profile():
    rng = np.random.default_rng(6)
    nu = np.arange(1.0, 4000.0, 0.5)
    a, b, c, w = 50.0, 150.0, 3.0, 0.5
    model = w + pu.harvey(nu, a, b, c)
    p = model * rng.chisquare(2, nu.size) / 2
    fit = pu.fit_background(nu, p, ncomp=1)
    comp = fit["components"][0]
    assert comp["b_uhz"] == pytest.approx(b, rel=0.1)
    assert comp["c"] == pytest.approx(c, rel=0.15)
    assert fit["white"] == pytest.approx(w, rel=0.05)


def test_solar_like_numax_and_dnu_on_a_simulated_oscillator():
    rng = np.random.default_rng(7)
    t = np.arange(0.0, 27.0, CAD)
    numax, dnu = 430.0, 28.9
    y = rng.normal(0, 60e-6, t.size)
    for n in range(8, 22):
        for ell, off in ((0, 0.0), (1, 0.5), (2, -0.12)):
            nu = dnu * (n + 1.2 + off)
            amp = 20e-6 * math.exp(-0.5 * ((nu - numax) / (0.25 * numax / 2.355)) ** 2) * (1.0, 1.3, 0.6)[ell]
            for _ in range(3):  # a few closely spaced components, like a damped mode
                f = (nu + rng.normal(0, 0.1)) / pu.DAY_TO_UHZ
                y += amp / math.sqrt(3) * np.sin(2 * math.pi * f * t + rng.uniform(0, 2 * math.pi))
    s = pu.solar_like(t, 1 + y, numax_range=(100, 2000), n_boot=20, seed=1)
    assert s["detected"]
    assert s["numax_uhz"] == pytest.approx(numax, rel=0.1)
    assert s["dnu_uhz"] == pytest.approx(dnu, rel=0.03)
    assert s["numax_err_uhz"] > 0 and s["dnu_err_uhz"] > 0


def test_solar_like_says_when_nothing_is_there():
    rng = np.random.default_rng(8)
    t = np.arange(0.0, 20.0, CAD)
    s = pu.solar_like(t, 1 + rng.normal(0, 1e-4, t.size), numax_range=(100, 2000), n_boot=5)
    assert s["detected"] is False and "no power excess" in s["why"]


def test_type_heuristics_and_their_uncertainty():
    def f(x, a=1e-3, s=10.0):
        return {"frequency": x, "amplitude": a, "snr": s, "significant": True, "combination": None}
    dsct = pu.classify([f(15), f(18), f(22), f(25), f(31)], teff=7500)
    assert dsct["label"] == "δ Scuti" and dsct["confidence"] in ("medium", "low")
    gdor = pu.classify([f(0.9), f(1.1), f(1.4), f(1.7), f(2.1)], teff=7000)
    assert gdor["label"] == "γ Doradus"
    hyb = pu.classify([f(15), f(18), f(22), f(1.0, 3e-4), f(1.3, 3e-4), f(1.6, 3e-4)], teff=7300)
    assert hyb["label"].startswith("hybrid")
    rot = pu.classify([f(0.37, 5e-3), {**f(0.74, 1e-3), "combination": "2f1"}], teff=4500)
    assert rot["label"] == "rotation" and rot["confidence"] == "low"
    none = pu.classify([])
    assert none["label"] == "unclear" and none["confidence"] == "low"
    for c in (dsct, gdor, hyb, rot):
        assert c["confidence"] != "high" and c["reasons"]


def test_frequency_matching_is_one_to_one():
    m = pu.match_frequencies([10.0, 10.02, 20.0], [10.01, 20.5], 0.05)
    assert m["matched"] == 1 and m["recall"] == 0.5
    assert m["pairs"][0]["ours"] in (10.0, 10.02)

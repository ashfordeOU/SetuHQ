# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Flares (setuhq.flares): templates, detection, morphology, energies, the FFD, completeness and nulls. Offline."""

import math

import numpy as np
import pytest

from setuhq import flares as fl
from setuhq.passbands import band_fraction, band_integral, planck_lambda

CAD = 2.0 / 1440.0


def _lc(seed=1, days=8.0, noise=5e-4, flares=(), rot=0.003):
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, days, CAD)
    t = t[(t < days / 2 - 0.3) | (t > days / 2)]  # a mid-sector gap
    f = 1.0 + rot * np.sin(2 * np.pi * t / 2.7) + rng.normal(0, noise, t.size)
    for tp, fw, a in flares:
        f *= 1.0 + fl.integrated_template(t, tp, fw / 1440.0, a, exposure=CAD)
    return t, f


def test_mendoza_template_shape_and_area():
    x = np.linspace(-3, 60, 300_001)
    y = fl.mendoza_template(x, 0.0, 1.0, 1.0)
    assert np.all(np.isfinite(y)) and y.min() >= 0
    assert y.max() == pytest.approx(0.95, abs=0.02)            # the published constants peak just under 1
    k = int(np.argmax(y))
    assert -0.05 < x[k] < 0.05                                  # at t_peak
    above = x[y >= y.max() / 2]
    assert above.max() - above.min() == pytest.approx(1.0, abs=0.1)   # FWHM ≈ 1 in units of the FWHM parameter
    assert fl.template_area() == pytest.approx(np.trapezoid(y, x), rel=0.01)
    # fast rise, slow decay
    assert x[k] - above.min() < above.max() - x[k]
    # no overflow far from the peak
    assert np.all(np.isfinite(fl.mendoza_template(np.array([-1e3, 1e4]), 0.0, 1.0, 1.0)))


def test_davenport_template_is_continuous_at_the_peak():
    y = fl.davenport_template(np.array([-1e-6, 1e-6]), 0.0, 1.0, 1.0)
    assert y[0] == pytest.approx(1.0, abs=1e-3) and y[1] == pytest.approx(0.992, abs=0.01)


def test_exposure_integration_keeps_the_equivalent_duration():
    t = np.arange(-0.05, 0.3, CAD)
    inst = fl.integrated_template(t, 0.0, 1 / 1440, 0.01, exposure=0, template="mendoza2022")
    integ = fl.integrated_template(t, 0.0, 1 / 1440, 0.01, exposure=CAD)
    true = 0.01 * (1 / 1440) * fl.template_area()
    assert np.sum(integ) * CAD == pytest.approx(true, rel=0.05)
    assert integ.max() < inst.max()


def test_detrend_preserves_a_flare_and_removes_rotation():
    t, f = _lc(flares=[(2.0, 10.0, 0.02)])
    d = fl.detrend(t, f, fl.FlareConfig())
    k = int(np.argmin(np.abs(t - 2.0)))
    assert d["resid"][k] > 0.015                      # the flare survives the trend
    quiet = np.abs(t - 2.0) > 0.3
    assert np.std(d["resid"][quiet]) < 7e-4           # the 0.3% rotation does not


def test_detects_and_characterises_injected_flares():
    inj = [(1.5, 6.0, 0.02), (3.0, 15.0, 0.008), (5.5, 4.0, 0.012), (5.5 + 12 / 1440, 5.0, 0.01), (7.0, 3.0, 0.015)]
    t, f = _lc(flares=inj)
    out = fl.detect_flares(t, f, np.full(t.size, 5e-4), star={"teff": 3200.0, "radius": 0.3})
    peaks = [x["t_peak"] for x in out["flares"]]
    for tp, fw, a in inj[:3] + inj[4:]:
        assert any(abs(p - tp) < 0.02 for p in peaks), tp
    big = min(out["flares"], key=lambda x: abs(x["t_peak"] - 1.5))
    assert big["amplitude"] == pytest.approx(0.02 * 0.95, rel=0.2)
    assert big["fwhm_minutes"] == pytest.approx(6.0, rel=0.35)
    assert big["rise_minutes"] < big["decay_minutes"]
    true_ed = 0.02 * 6 / 1440 * fl.template_area() * 86400
    assert big["ed_s"] == pytest.approx(true_ed, rel=0.2)
    assert big["e_bol_erg"] > 0 and big["status"] == "computed" and "9000 K" in big["assumption"]
    double = min(out["flares"], key=lambda x: abs(x["t_peak"] - 5.5))
    assert double["n_components"] >= 2 and double["morphology"] == "complex"
    assert out["summary"]["n_flares"] == len(out["flares"])
    assert all(x["delta_bic_vs_quadratic"] >= 6 and x["delta_bic_shape"] >= 10 for x in out["flares"])


def test_no_flares_in_white_noise_and_a_clean_inverted_null():
    t, f = _lc(seed=7, flares=())
    out = fl.detect_flares(t, f)
    assert out["summary"]["n_flares"] == 0
    nul = fl.inverted_null(t, f)
    assert nul["false_positives"] == 0


def test_inverted_null_finds_no_real_flare():
    t, f = _lc(flares=[(2.0, 10.0, 0.02), (6.0, 5.0, 0.01)])
    assert fl.detect_flares(t, f)["summary"]["n_flares"] >= 2
    assert fl.inverted_null(t, f)["false_positives"] == 0


def test_symmetric_bumps_are_rejected_by_the_shape_test():
    t, f = _lc(seed=3)
    f = f * (1 + 0.004 * np.exp(-0.5 * ((t - 2.0) / 0.02) ** 2))   # a 30-minute symmetric bump: not a flare
    out = fl.detect_flares(t, f)
    assert not any(abs(x["t_peak"] - 2.0) < 0.05 for x in out["flares"])
    assert any(abs(r["t_start"] - 2.0) < 0.1 and "symmetric" in r["why"] for r in out["rejected"])


def test_energies_unavailable_without_teff_and_radius():
    e = fl.flare_energies(10.0, {"teff": None, "radius": 0.3})
    assert e["e_bol_erg"] is None and e["status"] == "unavailable" and "Teff" in e["why"] and "magnitude" in e["why"]
    assert fl.flare_energies(10.0, None)["status"] == "unavailable"


def test_bolometric_energy_matches_the_closed_form():
    star = {"teff": 3300.0, "radius": 0.35}
    ed = 20.0
    e = fl.flare_energies(ed, star, "TESS")
    r = 0.35 * 6.957e10
    expect = ed * math.pi * r ** 2 * 5.670374419e-5 * 9000.0 ** 4 * band_integral(3300.0, "TESS") / band_integral(9000.0, "TESS")
    assert e["e_bol_erg"] == pytest.approx(expect, rel=1e-9)        # Shibayama et al. 2013 / Günther et al. 2020
    assert e["luminosity_route"].startswith("Teff") and e["teff_source"] == "TIC v8.2"
    # a 9000 K flare puts about a fifth of its light in the TESS band (Medina et al. 2020 quote 20.9%)
    assert 0.15 < band_fraction(9000.0, "TESS") < 0.3


def test_magnitude_route_uses_sullivan_zero_point_and_is_primary():
    star = {"teff": 3300.0, "radius": 0.35, "tmag": 9.0, "distance_pc": 10.0}
    lum = fl.stellar_band_luminosity(star)
    pc = 3.0856775814913673e18
    expect = 4 * math.pi * (10 * pc) ** 2 * 4.03e-6 * 10 ** (-0.4 * 9.0)
    assert lum["l_band_magnitude_erg_s"] == pytest.approx(expect, rel=1e-12)
    assert lum["l_band_erg_s"] == lum["l_band_magnitude_erg_s"] and lum["route"].startswith("magnitude")
    e = fl.flare_energies(20.0, star)
    assert e["e_band_erg"] == pytest.approx(20.0 * expect) and e["e_band_teff_radius_erg"] > 0
    # no Teff, but a magnitude and a distance: energies from the magnitude route
    assert fl.flare_energies(20.0, {"tmag": 9.0, "distance_pc": 10.0})["status"] == "computed"
    # a fallback Teff carries its label
    e2 = fl.flare_energies(20.0, {"teff": 3200.0, "radius": 0.2, "teff_source": "Teff from the CHEOPS archive"}, "CHEOPS")
    assert e2["teff_source"] == "Teff from the CHEOPS archive"


def test_planck_integral_against_stefan_boltzmann():
    lam = np.geomspace(1e-6, 1e-1, 200_000)
    y = planck_lambda(lam, 5772.0)
    assert math.pi * np.trapezoid(y, lam) == pytest.approx(5.670374419e-5 * 5772.0 ** 4, rel=1e-3)


def test_powerlaw_mle_recovers_the_index():
    rng = np.random.default_rng(0)
    alpha, emin = 1.9, 1e30
    e = emin * (1 - rng.random(4000)) ** (-1 / (alpha - 1))
    r = fl.powerlaw_mle(e, emin)
    assert r["alpha"] == pytest.approx(alpha, abs=3 * r["alpha_err"])
    assert r["alpha_err"] == pytest.approx((r["alpha"] - 1) / math.sqrt(4000))
    c = fl.compare_lognormal(e, emin)
    assert c["R"] is not None and (c["R"] > 0 or c["p_value"] > 0.1)   # a true power law is not rejected for a log-normal
    ln = np.exp(rng.normal(math.log(3e30), 0.6, 4000))
    c2 = fl.compare_lognormal(ln, 3e30)
    assert c2["R"] < 0 and c2["preferred"] == "log-normal"


def test_ffd_is_cumulative():
    d = fl.ffd([3e30, 1e30, 2e30, None], 2.0)
    assert d["energy"] == [3e30, 2e30, 1e30] and d["rate_per_day"] == [0.5, 1.0, 1.5]


def test_injection_recovery_is_seeded_and_monotone():
    t, f = _lc(seed=5, days=6.0)
    kw = dict(n_trials=2, per_trial=12, amp_range=(5e-4, 5e-2), fwhm_minutes=(2.0, 20.0), seed=4)
    a = fl.inject_recover(t, f, **kw)
    b = fl.inject_recover(t, f, **kw)
    assert [x["recovered"] for x in a["injections"]] == [x["recovered"] for x in b["injections"]]
    curve = a["by_amplitude"]
    assert curve[0]["fraction"] < 0.5 and curve[-1]["fraction"] >= 0.9
    lo, hi = curve[-1]["ci95"]
    assert lo <= curve[-1]["fraction"] <= hi
    assert fl.completeness_limit([{"lo": 1, "n": 5, "fraction": 0.2}, {"lo": 2, "n": 5, "fraction": 0.95},
                                  {"lo": 3, "n": 5, "fraction": 1.0}]) == 2


def test_wavelet_denoising_lowers_the_noise_and_keeps_a_flare():
    pytest.importorskip("pywt")
    rng = np.random.default_rng(2)
    x = rng.normal(0, 1e-3, 4096)
    t = np.arange(x.size) * CAD
    x += fl.mendoza_template(t, 3.0, 8 / 1440, 0.02)
    y = fl.swt_denoise(x, wavelet="db18", level=2)
    quiet = np.abs(t - 3.0) > 0.2
    assert np.std(y[quiet]) < 0.8 * np.std(x[quiet])
    k = int(np.argmin(np.abs(t - 3.0)))
    assert y[k - 2: k + 3].max() > 0.012
    assert y.size == x.size


def test_denoised_detection_recovers_at_least_as_many_weak_flares():
    pytest.importorskip("pywt")
    t, f = _lc(seed=11, days=6.0, noise=1e-3)
    kw = dict(n_trials=2, per_trial=12, amp_range=(2e-3, 2e-2), fwhm_minutes=(3.0, 20.0), seed=9)
    a = fl.inject_recover(t, f, config=fl.config_for("TESS", 120), **kw)
    b = fl.inject_recover(t, f, config=fl.config_for("TESS", 120, denoise=True), **kw)
    assert sum(x["recovered"] for x in b["injections"]) >= sum(x["recovered"] for x in a["injections"])
    assert fl.inverted_null(t, f, config=fl.config_for("TESS", 120, denoise=True))["false_positives"] == 0


def test_cheops_defaults_follow_poyatos():
    c = fl.config_for("CHEOPS")
    assert c.detrend == "savgol" and c.window_days == pytest.approx(20 / 1440) and c.n3 == 5
    assert fl.config_for("TESS", 20).n3 == 5 and fl.config_for("TESS", 120).n3 == 3


def test_savgol_detrend_on_a_cheops_like_visit():
    rng = np.random.default_rng(4)
    cad = 42.0 / 86400
    t = np.arange(0, 0.2, cad)
    t = t[(t % (99 / 1440)) < 60 / 1440]          # orbit gaps
    f = 1 + 0.002 * np.sin(2 * np.pi * t / 0.15) + rng.normal(0, 2e-4, t.size)
    f *= 1 + fl.integrated_template(t, t[40], 2 / 1440, 0.01, exposure=cad)
    out = fl.detect_flares(t, f, config=fl.config_for("CHEOPS"), band="CHEOPS", star={"teff": 3000, "radius": 0.2})
    assert any(abs(x["t_peak"] - t[40]) < 3 * cad for x in out["flares"])
    assert out["summary"]["savgol_degrees"] and min(out["summary"]["savgol_degrees"]) >= 2


def test_bic_effective_n_penalises_red_noise():
    assert fl._bic(1.0, 100, 3, rho=0.5) > fl._bic(1.0, 100, 3) - 100   # finite, and
    d_white = fl._bic(1.0, 100, 3) - fl._bic(0.8, 100, 6)
    d_red = fl._bic(1.0, 100, 3, rho=0.6) - fl._bic(0.8, 100, 6, rho=0.6)
    assert d_red < d_white                     # an extra component needs more improvement in red noise


def test_single_flares_are_rarely_split():
    t, f = _lc(seed=21, days=6.0)
    r = fl.inject_recover(t, f, n_trials=2, per_trial=10, amp_range=(5e-3, 5e-2), fwhm_minutes=(3.0, 30.0), seed=2)
    fs = fl.false_split_rate(r["injections"])
    assert fs["recovered_clean"] >= 10 and fs["rate"] <= 0.2


def test_injections_keep_the_drawn_fwhm_distribution_in_gappy_data():
    # CHEOPS-like: 45-min stretches every 99 min; the FWHM is drawn once per injection, only the position is redrawn,
    # and only the start and the peak plus three FWHM must fit in a stretch, so long flares are not crowded out
    rng = np.random.default_rng(3)
    cad = 60 / 86400
    t = np.arange(0, 1.5, cad)
    t = t[(t * 1440) % 99 < 45]
    f = 1 + rng.normal(0, 5e-4, t.size)
    r = fl.inject_recover(t, f, config=fl.config_for("CHEOPS", 60), band="CHEOPS", n_trials=3, per_trial=8,
                          amp_range=(3e-3, 3e-2), fwhm_minutes=(0.5, 10.0), seed=1)
    pl = r["placement"]
    assert pl["n_placed"] == 24 and pl["n_unplaced"] == 0
    assert abs(sum(b["expected_fraction"] for b in pl["histogram"]) - 1) < 1e-9
    assert sum(b["placed"] for b in pl["histogram"]) == 24
    long_ = np.mean([x["fwhm_minutes"] > math.sqrt(0.5 * 10.0) for x in r["injections"]])
    assert 0.3 <= long_ <= 0.8   # half expected above the log midpoint


def test_two_component_injections_merge_only_when_the_secondary_is_too_faint():
    t, f = _lc(seed=5, days=6.0)
    kw = dict(n_trials=1, per_trial=10, amp_range=(1e-2, 5e-2), fwhm_minutes=(5.0, 20.0), seed=4)
    clear = fl.merge_rate(fl.inject_recover(t, f, second={"ratio": (0.3, 0.5), "separation_fwhm": (3, 5)}, **kw)["injections"])
    faint = fl.merge_rate(fl.inject_recover(t, f, second={"ratio": (0.02, 0.05), "separation_fwhm": (1, 2)}, **kw)["injections"])
    assert clear["n"] >= 8 and clear["rate"] <= 0.3
    # below min_component_fraction (0.1) a secondary cannot be kept as a component: merged by construction
    assert faint["n"] >= 8 and faint["rate"] >= 0.9


def test_inverted_null_masks_real_flares():
    t, f = _lc(seed=8, flares=[(2.0, 30.0, 0.05), (4.5, 20.0, 0.04)])
    nul = fl.inverted_null(t, f)
    assert nul["masked_real_flares"] >= 2 and nul["false_positives"] == 0

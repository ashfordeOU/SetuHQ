"""S1a: the limb-darkened transit model and fit, the density and V-shape tests, and LD injections."""

import math

import numpy as np
import pytest

from exoplan import methods as M
from exoplan import transitfit as T
from exoplan.injection import Injection, synthetic_subject


@pytest.mark.parametrize("z,k", [(0.0, 0.1), (0.5, 0.1), (0.95, 0.1), (1.05, 0.1), (0.3, 0.5), (1.2, 0.5), (0.0, 1.2)])
def test_uniform_disc_is_the_overlap_area(z, k):
    assert 1 - T.occulted_flux([z], k, 0.0, 0.0)[0] == pytest.approx(M.overlap_area(z, k) / math.pi, abs=1e-9)


def test_limb_darkened_model_matches_a_brute_force_integral():
    xs = np.linspace(-1, 1, 1601)
    X, Y = np.meshgrid(xs, xs)
    r2 = X ** 2 + Y ** 2
    mu = np.sqrt(np.clip(1 - r2, 0, 1))
    u1, u2 = 0.33, 0.23
    I = (1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2) * (r2 < 1)
    for z, k in [(0.0, 0.1), (0.6, 0.1), (0.97, 0.1), (0.5, 0.3)]:
        brute = (I * (((X - z) ** 2 + Y ** 2) < k * k)).sum() / I.sum()
        assert 1 - T.occulted_flux([z], k, u1, u2)[0] == pytest.approx(brute, rel=3e-3)  # the brute grid's own pixel error


def test_claret_table_reproduces_the_atlas_rows_and_interpolates_in_logg():
    for teff, u1, u2 in M.CLARET_TESS:
        assert T.ld_coeffs(teff, 4.5) == pytest.approx((u1, u2), abs=1e-9)
    a = T.ld_coeffs(6000, 4.0)
    b = T.ld_coeffs(6000, 4.5)
    mid = T.ld_coeffs(6000, 4.25)
    assert mid == pytest.approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    assert T.ld_coeffs(None, None) == T.ld_coeffs(T.SUN_TEFF, T.SUN_LOGG)


def test_pi_men_c_numbers_from_the_atlas():
    # ATLAS C4: (a/R★, P) = (13.38, 6.2679 d) gives ρ★ = 1.153 g/cm³; M★ = 1.094, R★ = 1.10 gives 1.159.
    assert T.rho_star(13.38, 6.2679) == pytest.approx(1.153, abs=0.001)
    assert T.rho_catalogue(1.094, 1.10) == pytest.approx(1.159, abs=0.001)
    # ATLAS C3: k = 0.01703 at b = 0.59 with u ≈ (0.33, 0.23) is ~9% deeper than k², about 315 ppm.
    assert T.model_depth(0.01703, 0.59, 0.33, 0.23) * 1e6 == pytest.approx(315, abs=3)
    # Huang 2018: T14 = 2.953 h with b = 0.59, k = 0.01703 gives a/R★ near the published 13.38.
    assert T.a_over_r(2.953 / 24, 0.59, 0.01703, 6.2679) == pytest.approx(13.38, rel=0.01)
    assert T.t23(2.953 / 24, 0.59, 0.01703, 6.2679) / (2.953 / 24) == pytest.approx(0.95, abs=0.01)  # ATLAS E4: U-shaped


def _pi_men_like(seed=1, noise=1e-4, n=5):
    u1, u2 = T.ld_coeffs(6037, 4.42)
    rng = np.random.default_rng(seed)
    t = np.arange(0, 32, 2 / 1440)
    P = 6.2679
    f = T.transit_model(t, 3.0, 0.01703, 2.953 / 24, 0.59, P, u1, u2) + rng.normal(0, noise, t.size)
    return t, f, np.full(t.size, noise), [3.0 + i * P for i in range(n)], P, u1, u2


def test_the_fit_recovers_an_injected_pi_men_c_within_its_errors():
    t, f, e, eps, P, u1, u2 = _pi_men_like()
    fit = T.fit_transit(t, f, e, t0=3.005, duration=0.09, depth=2.4e-4, period=P, u1=u1, u2=u2, epochs=eps, stellar_density=1.159)
    truth_depth = T.model_depth(0.01703, 0.59, u1, u2) * 1e6
    assert abs(fit.depth_ppm - truth_depth) < 3 * max(fit.depth_err_ppm, 1.0)
    assert abs(fit.t14_hours - 2.953) < 3 * max(fit.t14_err_hours, 0.01)
    assert abs(fit.t0 - 3.0) < 3 * fit.t0_err + 1e-4
    assert fit.b_range[0] - 0.05 <= 0.59 <= fit.b_range[1] + 0.05
    assert fit.rho_range[0] * 0.9 <= 1.153 <= fit.rho_range[1] * 1.1
    assert not fit.v_shape and not fit.rho_flag and fit.n_epochs == 5
    # Both errors and ranges are stated, and the profile range contains the best fit.
    assert fit.depth_range_ppm[0] <= fit.depth_ppm <= fit.depth_range_ppm[1]


def test_a_box_fit_would_miss_what_the_model_recovers():
    # The old box measure (mean flux over the marked window) reads shallow; the model recovers the full depth.
    t, f, e, eps, P, u1, u2 = _pi_men_like(noise=3e-5)
    inside = np.zeros(t.size, bool)
    for c in eps:
        inside |= np.abs(t - c) <= 0.5 * 2.953 / 24
    box = (1 - f[inside].mean()) * 1e6
    fit = T.fit_transit(t, f, e, t0=3.0, duration=0.12, depth=2.4e-4, period=P, u1=u1, u2=u2, epochs=eps)
    truth = T.model_depth(0.01703, 0.59, u1, u2) * 1e6
    assert box < 0.92 * truth and fit.depth_ppm == pytest.approx(truth, rel=0.05)


def test_v_shape_flags_a_grazing_eclipsing_binary_but_not_a_planet():
    u1, u2 = T.ld_coeffs(5800, 4.4)
    rng = np.random.default_rng(2)
    t = np.arange(0, 10, 10 / 1440)
    f = T.transit_model(t, 5, 0.25, 0.12, 1.1, 3.3, u1, u2, exptime=10 / 1440, supersample=5) + rng.normal(0, 5e-4, t.size)
    eb = T.fit_transit(t, f, np.full(t.size, 5e-4), t0=5, duration=0.1, depth=0.01, period=3.3, u1=u1, u2=u2, epochs=[5 - 3.3, 5, 5 + 3.3])
    assert eb.grazing and eb.v_shape and eb.v_shape_dchi2 > T.V_SHAPE_DCHI2 and eb.t23_hours == 0.0
    t2, f2, e2, eps, P, u1b, u2b = _pi_men_like()
    planet = T.fit_transit(t2, f2, e2, t0=3.0, duration=0.12, depth=2.4e-4, period=P, u1=u1b, u2=u2b, epochs=eps)
    assert not planet.v_shape


def test_density_mismatch_is_flagged_only_outside_the_3_sigma_range():
    t, f, e, eps, P, u1, u2 = _pi_men_like()
    ok = T.fit_transit(t, f, e, t0=3.0, duration=0.12, depth=2.4e-4, period=P, u1=u1, u2=u2, epochs=eps, stellar_density=1.159)
    # A star 30 times denser than the transit allows (the signal would be on another star): flagged.
    bad = T.fit_transit(t, f, e, t0=3.0, duration=0.12, depth=2.4e-4, period=P, u1=u1, u2=u2, epochs=eps, stellar_density=35.0)
    assert not ok.rho_flag and bad.rho_flag and bad.rho_ratio < T.RHO_BOUNDS[0]


def test_single_transit_has_no_density_and_says_so():
    t, f, e, eps, P, u1, u2 = _pi_men_like()
    fit = T.fit_transit(t, f, e, t0=3.0, duration=0.12, depth=2.4e-4, period=None, u1=u1, u2=u2)
    assert fit.rho_star is None and fit.a_rs is None and "single transit" in fit.notes[0]


def test_injections_use_the_limb_darkened_model():
    inj = Injection(5.0, 5.0 + 3 / 24, 0.002, b=0.2)
    s = synthetic_subject(np.random.default_rng(0), subject_id="ld", length_days=10.0, white_ppm=0.0, red_ppm=0.0,
                          injections=(inj,), dropout_fraction=0.0)
    deficit = 1 - s.flux
    mid = np.argmin(np.abs(s.time - 5.0625))
    assert deficit[mid] == pytest.approx(0.002, rel=0.02)  # the stated depth is the mid-transit depth
    # A rounded bottom: half-way to the edge the deficit is already lower (a box would be flat).
    quarter = np.argmin(np.abs(s.time - (5.0 + 0.75 / 24)))
    assert deficit[quarter] < 0.985 * deficit[mid]


def test_stored_pi_men_run_carries_the_fit_and_bounded_fap():
    import csv
    import json
    from pathlib import Path

    from exoplan.store import read_classifications_csv

    run = Path("runs/tess-pi-men-s1")
    cls = read_classifications_csv(run / "classifications.csv")
    assert len(cls) == 10 and {c.reviewer_id for c in cls} >= {"claude-skeptic", "claude-volunteer"}
    rows = list(csv.DictReader((run / "candidates.csv").open()))
    on = [r for r in rows if r["passed"] == "True" and "off_ephemeris" not in r["flags"]]
    assert len(on) == 5 and all(r["fap_label"] == "< 1.0e-04 (10,000 trials)" for r in on)
    assert all(250 < float(r["fit_depth_ppm"]) < 350 and float(r["fit_depth_err_ppm"]) > 0 for r in on)
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["rebuilds"][-1]["fap_trials"] == 10000 and "not asked again" in manifest["rebuilds"][-1]["reused"]
    val = json.loads(Path("docs/results/pi_men_validation.json").read_text())
    r = val["ratios_vs_huang_2018"]
    assert 0.9 < r["depth"] < 1.1 and 0.9 < r["duration"] < 1.1  # the box gave 0.81 and 0.64
    assert r["box_depth"] < 0.85 and r["box_duration"] < 0.7


def test_the_pipeline_fits_every_consensus_dip(tmp_path):
    from exoplan.config import RunConfig
    from exoplan.lightcurve import LightCurve
    from exoplan.pipeline import run_pipeline
    from exoplan.reviewers.simulated import SimulatedVolunteer

    rng = np.random.default_rng(5)
    time = np.arange(0.0, 13.0, 10 / 1440)
    flux = 1 + rng.normal(0, 2e-4, time.size)
    for k in range(3):
        flux *= T.inject_transit(time, 2.5 + 4.0 * k, 2500e-6, 0.2, b=0.3)
    lc = LightCurve(target="TIC FIT-1", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 2e-4), provenance={"sector": 1, "time_unit": "BTJD"})
    reviewers = [SimulatedVolunteer("v", snr_threshold=4.5, miss_probability=0.0, seed=1)]
    out = run_pipeline(RunConfig(name="fit", subject_days=13.0, min_points=100, fap_trials=0), [lc], reviewers, tmp_path)
    passed = [c for c in out.candidates if c.passed]
    assert passed and all(c.fit and abs(c.fit["depth_ppm"] - 2500) < 300 and abs(c.fit["t14_hours"] - 4.8) < 0.8 for c in passed)
    row = passed[0].as_row()
    assert row["fit_depth_ppm"] == passed[0].fit["depth_ppm"] and row["fit_b"] == passed[0].fit["b"]


def test_a_wrong_search_period_does_not_bias_the_joint_fit():
    # Fable B1: the BLS period is approximate; held fixed it smears the epochs into a long grazing shape.
    t, f, e, eps, P, u1, u2 = _pi_men_like(seed=6, noise=6e-5, n=3)
    wrong = P + 0.005
    fit = T.fit_transit(t, f, e, t0=eps[1], duration=0.12, depth=2.4e-4, period=wrong, u1=u1, u2=u2,
                        epochs=[eps[1] + n * wrong for n in (-1, 0, 1)], stellar_density=1.159)
    right = T.fit_transit(t, f, e, t0=eps[1], duration=0.12, depth=2.4e-4, period=P, u1=u1, u2=u2,
                          epochs=[eps[1] + n * P for n in (-1, 0, 1)], stellar_density=1.159)
    # The wrong search period gives the same answer as the right one.
    assert fit.b == pytest.approx(right.b, abs=0.05) and fit.rho_star == pytest.approx(right.rho_star, rel=0.1)
    assert fit.t14_hours == pytest.approx(right.t14_hours, abs=0.05) and not fit.rho_flag and not fit.v_shape
    truth_rho = T.rho_star(T.a_over_r(2.953 / 24, 0.59, 0.01703, P), P)
    assert fit.period_free and fit.period_search == wrong
    assert abs(fit.period_days - P) < max(3 * fit.period_err, 1e-3)
    assert fit.b_range[0] - 0.02 <= 0.59 <= fit.b_range[1] + 0.02
    assert truth_rho / 2 <= fit.rho_star <= truth_rho * 2
    assert abs(fit.t14_hours - 2.953) < 3 * max(fit.t14_err_hours, 0.02)


def test_a_density_prior_pins_b_and_a_over_r_and_an_unconstrained_b_prints_as_an_upper_limit():
    t, f, e, eps, P, u1, u2 = _pi_men_like(seed=2, noise=2e-4, n=3)
    free = T.fit_transit(t, f, e, t0=eps[0], duration=0.12, depth=2.4e-4, period=P, u1=u1, u2=u2, epochs=eps)
    truth_ars = T.a_over_r(2.953 / 24, 0.59, 0.01703, P)
    rho = T.rho_star(truth_ars, P)
    pri = T.fit_transit(t, f, e, t0=eps[0], duration=0.12, depth=2.4e-4, period=P, u1=u1, u2=u2, epochs=eps,
                        rho_prior=(rho, 0.05 * rho))
    assert pri.rho_prior and abs(pri.rho_star - rho) < 0.15 * rho
    assert abs(pri.a_rs - truth_ars) < 0.1 * truth_ars and abs(pri.b - 0.59) < 0.2
    assert pri.t23_over_t14 == pytest.approx(T.t23(2.953 / 24, 0.59, 0.01703, P) / (2.953 / 24), abs=0.08)
    assert (pri.b_range[1] - pri.b_range[0]) < (free.b_range[1] - free.b_range[0])
    d = free.as_dict()
    d.update(b_upper_limit=True, b_range=[0.0, 0.87])
    assert T.b_text(d) == "b < 0.87 (1σ)"
    assert T.b_text(dict(d, b_upper_limit=False, b=0.59, b_err=0.05)) == "b = 0.59 ± 0.05"

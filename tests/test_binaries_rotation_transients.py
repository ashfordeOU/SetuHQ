# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Eclipsing binaries (setuhq.binaries), rotation (setuhq.rotation) and transients (setuhq.transients): synthetic
light curves with known answers. Offline."""

import numpy as np
import pytest

from setuhq import binaries as B
from setuhq import rotation as R
from setuhq import transients as X


def _time(days=27.0, cadence_min=10.0, gap=True, start=1325.0):
    t = np.arange(start, start + days, cadence_min / 1440)
    return t[(t < start + days / 2 - 0.5) | (t > start + days / 2 + 0.5)] if gap else t


# ---------------------------------------------------------------- eclipsing binaries

@pytest.mark.parametrize("period,dp,ds,phase_s,width", [(2.7, 0.2, 0.08, 0.5, 0.04), (5.1, 0.15, 0.05, 0.42, 0.03),
                                                         (0.45, 0.25, 0.22, 0.5, 0.3)])
def test_a_binary_is_found_with_its_period_depths_and_secondary_phase(period, dp, ds, phase_s, width):
    rng = np.random.default_rng(1)
    t = _time()
    f = B.synthetic_eb(t, period, 1325.3, dp, ds, phase_s, width) + rng.normal(0, 1e-3, t.size)
    r = B.analyse(t, f)
    assert r["eb_candidate"] and r["period"] == pytest.approx(period, rel=0.005)
    clean = B.synthetic_eb(t, period, 1325.3, dp, ds, phase_s, width)
    # depth below the out-of-eclipse level (the maximum: overlapping wide eclipses never return to 1)
    assert r["primary"]["depth"] == pytest.approx(1 - clean.min() / clean.max(), rel=0.1)
    assert r["secondary"] and abs(r["secondary"]["phase"] - phase_s) < 0.01
    assert r["secondary"]["e_cos_omega_hint"] == pytest.approx(np.pi / 2 * (r["secondary"]["phase"] - 0.5))
    assert "confirmed" not in B.LABEL.replace("never a confirmed", "") and "never a confirmed or new binary" in B.LABEL


def test_detached_and_contact_morphology():
    rng = np.random.default_rng(2)
    t = _time()
    d = B.analyse(t, B.synthetic_eb(t, 3.3, 1325.2, 0.3, 0.1, 0.5, 0.03) + rng.normal(0, 1e-3, t.size))
    c = B.analyse(t, B.synthetic_eb(t, 0.4, 1325.1, 0.25, 0.2, 0.5, 0.3) + rng.normal(0, 1e-3, t.size))
    assert d["morphology"]["class"] == "detached"
    assert c["morphology"]["class"] in ("contact", "ellipsoidal")


def test_equal_minima_double_the_period_and_say_so():
    rng = np.random.default_rng(3)
    t = _time()
    r = B.analyse(t, B.synthetic_eb(t, 3.3, 1325.3, 0.1, 0.1, 0.5, 0.03) + rng.normal(0, 1e-3, t.size))
    assert r["period"] == pytest.approx(3.3, rel=0.005) and r["period_ambiguous"]
    # the doubled minimum is not counted as independent evidence of a secondary
    assert not any("secondary minimum" in x for x in r["reasons"])


def test_a_planet_transit_spots_and_noise_are_not_flagged():
    rng = np.random.default_rng(4)
    t = _time()
    planet = 1 - 0.006 * (np.abs(((t - 1326) / 3.5 + 0.5) % 1 - 0.5) * 3.5 < 0.06) + rng.normal(0, 1e-3, t.size)
    r = B.analyse(t, planet)
    assert not r["eb_candidate"] and r["period"] == pytest.approx(3.5, rel=0.01)
    spots = R.spot_model(t, 4.2, 0.01, rng, lifetime_periods=(0.8, 1.5)) + rng.normal(0, 1e-3, t.size)
    assert not B.analyse(t, spots)["eb_candidate"]
    assert not B.analyse(t, 1 + rng.normal(0, 1e-3, t.size))["eb_candidate"]


def test_vetting_hints_are_advisory_and_see_odd_even_and_secondary():
    rng = np.random.default_rng(5)
    t = _time()
    # an EB at twice the "transit" period: alternate dips differ, and a secondary sits at phase 0.5 of the transit period
    f = B.synthetic_eb(t, 4.0, 1325.5, 0.02, 0.012, 0.5, 0.02) + rng.normal(0, 5e-4, t.size)
    h = B.vetting_hints(t, f, 2.0, 1325.5, 0.08)
    assert h["odd_even_sigma"] > 5
    assert "not used by SetuHQ's planet vetting" in h["note"] and "pre-registered" in h["note"]


def test_vetting_code_does_not_use_the_binaries_module():
    from pathlib import Path

    src = Path(B.__file__).resolve().parent
    for f in ("vet.py", "pipeline.py", "dvtests.py", "variables.py", "benchmark.py", "benchmark_toi.py"):
        text = (src / f).read_text()
        assert "import binaries" not in text and "setuhq.binaries" not in text and "binaries." not in text, f


# ---------------------------------------------------------------- rotation

@pytest.mark.parametrize("period", [0.7, 1.5, 3.0, 5.5, 8.0])
def test_rotation_period_recovered_from_evolving_spots(period):
    rng = np.random.default_rng(int(period * 10))
    t = _time(cadence_min=2.0)
    f = R.spot_model(t, period, 5e-3, rng, n_spots=1) + rng.normal(0, 1e-3, t.size)
    r = R.measure(t, f)
    assert r["detected"]
    assert r["period"] == pytest.approx(period, rel=0.1)
    assert 0 < r["period_err"] < 0.3 * period


def test_two_spot_groups_give_the_double_of_the_periodogram_peak():
    t = _time(cadence_min=2.0)
    ph = 2 * np.pi * (t - t[0]) / 8.0
    # two dips per rotation of unequal depth: the periodogram peaks at 4 d, the ACF at 8 d
    f = 1 - 4e-3 * np.clip(np.cos(ph), 0, None) ** 4 - 3e-3 * np.clip(np.cos(ph + np.pi), 0, None) ** 4
    f += np.random.default_rng(0).normal(0, 3e-4, t.size)
    r = R.measure(t, f)
    assert r["detected"] and r["period"] == pytest.approx(8.0, rel=0.1) and r["alias"] == pytest.approx(4.0, rel=0.1)


def test_long_periods_are_reported_as_beyond_the_limit_never_as_a_period():
    rng = np.random.default_rng(9)
    t = _time(cadence_min=2.0)
    for p in (18.0, 25.0):
        r = R.measure(t, R.spot_model(t, p, 5e-3, rng, n_spots=1) + rng.normal(0, 1e-3, t.size))
        assert not r["detected"] and r["period"] is None and r["beyond_limit"]
        assert any("13 d" in x for x in r["reasons"])
    assert "13 days" in R.LABEL and R.LIMIT_DAYS == 13.0


def test_noise_gives_no_rotation_period():
    rng = np.random.default_rng(11)
    t = _time(cadence_min=2.0)
    for _ in range(3):
        assert not R.measure(t, 1 + rng.normal(0, 1e-3, t.size))["detected"]


# ---------------------------------------------------------------- transients

def test_a_flare_an_asteroid_and_a_momentum_dump_are_found_and_told_apart():
    rng = np.random.default_rng(5)
    t = _time(cadence_min=2.0)
    f = 1 + rng.normal(0, 1e-3, t.size)
    f += X.flare_model(t, 1330.3, 0.02) + X.asteroid_model(t, 1335.0, 0.004, 0.3) + X.dump_spike(t, 1342.0, 0.01, 2)
    r = X.find_transients(t, f, quality={"momentum_dump": [1342.0, 1348.0], "scattered_light": []})
    by = {round(c["t_peak"]): c for c in r["candidates"]}
    assert by[1330]["class_hint"] == "flare-like" and not by[1330]["likely_false_alarm"]
    assert by[1335]["class_hint"] == "asteroid-crossing-like" and by[1335]["likely_false_alarm"]
    assert by[1342]["class_hint"] == "momentum-dump-like" and by[1342]["likely_false_alarm"]
    assert all(c["label"] == "transient candidate" for c in r["candidates"])
    assert by[1330]["peak"] == pytest.approx(0.02, rel=0.15)


def test_a_supernova_in_a_difference_light_curve_has_its_rise_peak_and_class():
    rng = np.random.default_rng(6)
    t = _time(start=1400.0, cadence_min=30.0)
    y = X.sn_model(t, 1405.0, 17.0, 40.0) + rng.normal(0, 2.0, t.size)
    r = X.find_transients(t, y, mode="difference", zero_point=X.TESS_ZERO_POINT, aperture_correction=0.85)
    (c,) = r["candidates"]
    assert c["class_hint"] == "extragalactic-transient-like" and c["scale"] == "slow"
    assert c["t_peak"] == pytest.approx(1422.0, abs=1.0)
    assert c["first_light"]["t0"] == pytest.approx(1405.0, abs=1.5) and c["rise_time"] == pytest.approx(17.0, rel=0.15)
    assert c["peak_mag"] == pytest.approx(20.44 - 2.5 * np.log10(40 / 0.85), abs=0.1)


def test_control_apertures_and_moving_centroids_screen_false_alarms():
    rng = np.random.default_rng(7)
    t = _time(start=1400.0, cadence_min=30.0)
    bump = X.asteroid_model(t, 1410.0, 30.0, 1.5)
    y = bump + rng.normal(0, 2.0, t.size)
    r = X.find_transients(t, y, mode="difference", controls=[bump * 0.8, bump * 0.9])
    assert r["candidates"] and all(c["class_hint"] == "scattered-light-like" for c in r["candidates"])
    cen = np.zeros((t.size, 2))
    cen[:, 0] = np.where(np.abs(t - 1410) < 1, (t - 1410) * 2, 0)
    r = X.find_transients(t, X.asteroid_model(t, 1410.0, 30.0, 0.3) + rng.normal(0, 2.0, t.size), mode="difference", centroid=cen)
    assert r["candidates"][0]["class_hint"] == "asteroid-crossing-like" and r["candidates"][0]["centroid_shift_px"] > 1


def test_periodic_stars_mark_their_slow_brightenings():
    t = _time(cadence_min=2.0)
    f = 1 + 0.02 * np.sin(2 * np.pi * t / 4.8) + np.random.default_rng(8).normal(0, 1e-3, t.size)
    r = X.find_transients(t, f)
    slow = [c for c in r["candidates"] if c["scale"] == "slow"]
    assert r["periodic"] and r["periodic"]["period"] == pytest.approx(4.8, rel=0.1)
    assert all(c["class_hint"] == "periodic-variability-like" and c["likely_false_alarm"] for c in slow)


def test_quiet_noise_gives_no_candidate_and_quality_times_are_read():
    rng = np.random.default_rng(12)
    t = _time(cadence_min=2.0)
    assert X.find_transients(t, 1 + rng.normal(0, 1e-3, t.size))["candidates"] == []
    q = X.quality_times([1.0, 2.0, 3.0, 4.0], [0, 32, 4096, 2048 | 32])
    assert q["momentum_dump"] == [2.0, 4.0] and q["scattered_light"] == [3.0, 4.0]


def test_transient_wording_never_says_new_or_confirmed():
    assert "never a new, discovered or confirmed object" in X.LABEL
    for word in ("new transient", "discovered", "confirmed transient"):
        assert word not in X.LABEL.replace("never a new, discovered or confirmed object", "")

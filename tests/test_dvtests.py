"""S2 light-curve tests (dvtests.py): crowding, all-phase secondary, odd/even depth and timing, and the decide switch."""

import math

import numpy as np
import pytest

from exoplan import dvtests
from exoplan.dvtests import (crowding, epoch_depths, epoch_times, extended_vet, implied_albedo, odd_even_depth_test,
                             secondary_search, timing_test, trapezoid)
from exoplan.vet import DISQUALIFYING

P, T0, DUR = 4.0, 1.0, 0.15


def _curve(rng, *, days=40.0, noise=2e-4, events=(), cadence_min=10.0, shape="box"):
    """Flat light curve with events given as (centre, depth, duration): boxes, or trapezoids (a tenth of the
    duration in ingress, the timing template's own shape)."""
    t = np.arange(0.0, days, cadence_min / 1440.0)
    f = 1.0 + rng.normal(0.0, noise, t.size)
    for centre, depth, dur in events:
        if shape == "box":
            f[np.abs(t - centre) <= 0.5 * dur] -= depth
        else:
            f -= depth * trapezoid(t - centre, dur)
    return t, f, np.full(t.size, noise)


def _transits(depth, *, phase=0.0, days=40.0, odd_depth=None, dur=DUR, shift=0.0, odd_shift=0.0):
    out = []
    for n in range(int(days / P) + 1):
        c = T0 + (n + phase) * P + shift + (odd_shift if n % 2 else 0.0)
        out.append((c, (odd_depth if (odd_depth is not None and n % 2) else depth), dur))
    return out


def test_crowding_flags_below_threshold():
    assert crowding({"crowdsap": 0.7, "flfrcsap": 0.9})["crowded"] is True
    assert crowding({"crowdsap": 0.95})["crowded"] is False
    assert crowding({})["crowded"] is None          # unknown is not "uncrowded"
    flags, metrics = extended_vet([], [], [], period=None, t0=None, duration=None, provenance={"crowdsap": 0.5})
    assert flags == ("crowded",) and metrics["crowding"]["crowdsap"] == 0.5


def test_secondary_search_finds_an_eccentric_secondary_the_phase_half_check_misses(rng):
    events = _transits(3000e-6) + _transits(1500e-6, phase=0.37)
    t, f, e = _curve(rng, events=events)
    sec = secondary_search(t, f, period=P, t0=T0, duration=DUR)
    assert abs(sec["phase"] - 0.37) < 0.02
    assert sec["depth_ppm"] == pytest.approx(1500, rel=0.1)
    assert sec["snr"] > 20
    assert abs(sec["phase_05"]["snr"]) < 4                      # nothing at phase 0.5
    flags, metrics = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "secondary_any_phase" in flags
    # the box error is the robust scatter over sqrt(n), closed form
    assert sec["sigma_ppm"] == pytest.approx(2e-4 / math.sqrt(sec["n_points"]) * 1e6, rel=0.15)


def test_planet_has_no_significant_secondary(rng):
    t, f, e = _curve(rng, events=_transits(1000e-6))
    flags, metrics = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "secondary_any_phase" not in flags
    sec = metrics["secondary"]
    assert sec["snr"] < max(sec["threshold_sigma"], sec["max_brightening_snr"])
    assert sec["n_trials"] > 50
    assert sec["scan_robust_sigma"] == pytest.approx(1.0, abs=0.25)      # white noise: the scan spread is ~1


def test_a_lone_dip_is_not_a_secondary(rng):
    """One isolated dip away from the transits gives a large box statistic, but it is in one epoch only."""
    t, f, e = _curve(rng, events=_transits(1000e-6) + [(T0 + 5 * P + 0.4 * P, 2500e-6, DUR)])
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    sec = m["secondary"]
    assert abs(sec["phase"] - 0.4) < 0.03 and sec["snr"] > 5
    assert sec["max_epoch_share"] > 0.7 and not sec["periodic"]
    assert "secondary_any_phase" not in flags


def _scan_flag_rate(n, *, period, cadence, red=0.0, seed0=0, days=27.0):
    t = np.arange(0.0, days, cadence / 1440.0)
    knots = np.arange(0.0, days + 0.2, 0.15)
    flagged = 0
    spreads = []
    for i in range(n):
        rng = np.random.default_rng(seed0 + i)
        f = 1 + rng.normal(0, 1e-3, t.size)
        if red:
            f += np.interp(t, knots, rng.normal(0, red, knots.size))
        sec = dvtests.assess_secondary(dvtests.secondary_search(t, f, period=period, t0=0.3, duration=0.125))
        flagged += sec["significant"]
        spreads.append(sec["scan_robust_sigma"])
    return flagged, float(np.median(spreads))


def test_secondary_false_alarm_rate_on_white_noise():
    """2000 white-noise scans (pi Men's geometry, 193 positions, 10-minute bins): at most 0.3% flagged. The rule is
    calibrated at 0.1% per scan (scripts/calibrate_secondary.py)."""
    flagged, spread = _scan_flag_rate(2000, period=6.27, cadence=10.0, seed0=500000)
    assert flagged <= 6
    assert spread == pytest.approx(1.0, abs=0.1)


def test_secondary_false_alarm_rate_follows_the_scan_spread():
    """Red-ish noise (a 0.15-day random walk on top of white noise) widens the scan statistic; because the threshold
    scales with the scan's own robust spread (1.7 here), the false-alarm rate stays below 1% (2 in 1000 measured)."""
    flagged, spread = _scan_flag_rate(1000, period=6.27, cadence=10.0, red=5e-4, seed0=700000)
    assert spread > 1.5
    assert flagged <= 10

def test_secondary_must_beat_the_largest_brightening(rng):
    """A dip that is no deeper than the brightenings seen elsewhere is noise, whatever its nominal sigma."""
    t, f, e = _curve(rng, events=_transits(3000e-6) + _transits(800e-6, phase=0.3) + _transits(-900e-6, phase=0.7))
    flags, metrics = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert metrics["secondary"]["snr"] > dvtests.SECONDARY_SIGMA
    assert metrics["secondary"]["max_brightening_snr"] > metrics["secondary"]["snr"]
    assert "secondary_any_phase" not in flags


def test_implied_albedo_closed_form():
    # delta_sec = A_g (k / (a/R*))^2 -> A_g = 100e-6 * 10^2 / 0.1^2 = 1.0
    assert implied_albedo(100e-6, 0.1, 10.0) == pytest.approx(1.0)
    assert implied_albedo(100e-6, None, 10.0) is None


def test_odd_even_depth_closed_form():
    epochs = [{"parity": "odd", "depth": 3e-3, "sigma": 1e-4}, {"parity": "odd", "depth": 3e-3, "sigma": 1e-4},
              {"parity": "even", "depth": 2e-3, "sigma": 1e-4}]
    r = odd_even_depth_test(epochs)
    # no scatter about the parity means (scale 1), plus the 2% floor on each parity
    so = math.hypot(1e-4 / math.sqrt(2), 0.02 * 3e-3)
    se = math.hypot(1e-4, 0.02 * 2e-3)
    assert r["error_scale"] == 1.0
    assert r["odd_err_ppm"] == pytest.approx(so * 1e6)
    assert r["delta_sigma"] == pytest.approx(1e-3 / math.hypot(so, se))
    assert r["significant"]
    # scatter about the parity means inflates the errors by sqrt(chi2_red)
    eps = [{"parity": "odd", "depth": 3e-3 + d, "sigma": 1e-4} for d in (3e-4, -3e-4)] + \
          [{"parity": "even", "depth": 3e-3 + d, "sigma": 1e-4} for d in (3e-4, -3e-4)]
    r = odd_even_depth_test(eps, floor=0.0)
    assert r["epoch_dof"] == 2 and r["epoch_chi2"] == pytest.approx(4 * 9.0)
    assert r["error_scale"] == pytest.approx(math.sqrt(18.0))
    assert r["odd_err_ppm"] == pytest.approx(1e-4 / math.sqrt(2) * math.sqrt(18.0) * 1e6)
    assert odd_even_depth_test([{"parity": "odd", "depth": 3e-3, "sigma": 1e-4}]) is None


def test_odd_even_depth_on_a_binary_at_twice_the_period(rng):
    t, f, e = _curve(rng, events=_transits(3000e-6, odd_depth=2000e-6))
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "odd_even_depth" in flags
    assert m["odd_even_depth"]["odd_depth_ppm"] == pytest.approx(2000, rel=0.1)
    assert m["odd_even_depth"]["even_depth_ppm"] == pytest.approx(3000, rel=0.1)
    t, f, e = _curve(rng, events=_transits(3000e-6))
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "odd_even_depth" not in flags and m["odd_even_depth"]["delta_sigma"] < 3


def test_epoch_times_recover_injected_shifts_with_calibrated_errors():
    """Every epoch shifted by +6 minutes: over 100 epochs (10 noise seeds) the pulls (measured − injected)/σ have
    mean ≈ 0 and spread ≈ 1, and σ matches the closed form of Carter et al. 2008 for a trapezoid,
    σ_tc = Q⁻¹ T √(τ/2T) with Q = √(ΓT) δ/σ, i.e. (σ/δ) √(τ/(2Γ)), τ the ingress and Γ the sampling rate (0.77 min)."""
    shift = 6.0 / 1440.0
    tpl = lambda dt: trapezoid(dt, DUR)
    pulls, sigmas = [], []
    for seed in range(10):
        t, f, e = _curve(np.random.default_rng(seed), events=_transits(3000e-6, shift=shift), cadence_min=2.0,
                         noise=5e-4, shape="trapezoid")
        times = epoch_times(t, f, e, period=P, t0=T0, duration=DUR, template=tpl)
        assert len(times) >= 9
        pulls += [((ep["t_mid"] - ep["t_predicted"]) - shift) / ep["sigma"] for ep in times]
        sigmas += [ep["sigma"] for ep in times]
    pulls = np.array(pulls)
    assert abs(pulls.mean()) < 0.25
    assert 0.8 < pulls.std() < 1.2
    tau, rate = 0.1 * DUR, 1440.0 / 2.0
    carter = (5e-4 / 3000e-6) * math.sqrt(tau / (2 * rate))
    assert np.median(sigmas) == pytest.approx(carter, rel=0.2)


def test_timing_test_closed_form():
    # three epochs exactly on a line: chi2 = 0, p = 1; odd offset estimated with its propagated error
    eps = [{"epoch": n, "t_mid": 1.0 + 4.0 * n, "sigma": 1e-3} for n in (0, 1, 2, 3)]
    r = timing_test(eps)
    assert r["linear"]["chi2"] == pytest.approx(0.0, abs=1e-12)
    assert r["linear"]["p_value"] == pytest.approx(1.0)
    assert r["odd_even"]["offset_minutes"] == pytest.approx(0.0, abs=1e-6)
    assert not r["odd_even"]["significant"]
    assert timing_test(eps[:3])["odd_even"] is None         # three epochs: no spare degree of freedom
    assert timing_test(eps[:1])["linear"] is None


def test_odd_even_offset_error_is_inflated_by_its_fit():
    """Scatter the odd/even model cannot absorb widens the error by sqrt(chi2_red) of that fit, closed form."""
    sig = 1e-3
    jitter = [0.0, 3e-3, 3e-3, -3e-3, -3e-3, 0.0]
    eps = [{"epoch": n, "t_mid": 1.0 + 4.0 * n + j, "sigma": sig} for n, j in enumerate(jitter)]
    r = timing_test(eps)
    n = np.arange(6.0)
    a = np.column_stack([np.ones(6), n, n % 2])
    y = np.array([e["t_mid"] for e in eps])
    beta = np.linalg.lstsq(a, y, rcond=None)[0]
    chi_red = float(np.sum((y - a @ beta) ** 2) / sig ** 2 / 3)
    raw = math.sqrt(np.linalg.inv(a.T @ a / sig ** 2)[2, 2])
    assert chi_red > 1
    assert r["odd_even"]["offset_err_minutes"] == pytest.approx(raw * math.sqrt(chi_red) * 1440, rel=1e-9)


def test_clean_three_epoch_planet_gets_no_odd_even_timing_flag(rng):
    t, f, e = _curve(rng, days=11.0, events=_transits(3000e-6, days=11.0), cadence_min=2.0, noise=3e-4,
                     shape="trapezoid")
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert m["timing"]["n_epochs"] == 3 and m["timing"]["odd_even"] is None
    assert "odd_even_timing" not in flags


def test_odd_even_timing_flags_an_offset_between_parities(rng):
    t, f, e = _curve(rng, events=_transits(3000e-6, odd_shift=15.0 / 1440.0), cadence_min=2.0, noise=3e-4,
                     shape="trapezoid")
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "odd_even_timing" in flags
    assert m["timing"]["odd_even"]["offset_minutes"] == pytest.approx(15.0, abs=3.0)
    t, f, e = _curve(rng, events=_transits(3000e-6), cadence_min=2.0, noise=3e-4, shape="trapezoid")
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "odd_even_timing" not in flags and "timing_inconsistent" not in flags
    assert m["timing"]["linear"]["p_value"] > 1e-3


def test_timing_inconsistent_on_large_ttvs(rng):
    events = [(c + 0.02 * math.sin(2 * math.pi * n / 5), d, w) for n, (c, d, w) in enumerate(_transits(3000e-6))]
    t, f, e = _curve(rng, events=events, cadence_min=2.0, noise=3e-4, shape="trapezoid")
    flags, m = extended_vet(t, f, e, period=P, t0=T0, duration=DUR)
    assert "timing_inconsistent" in flags
    assert m["timing"]["linear"]["p_value"] < 1e-3


def test_shape_template_from_the_fit_is_unit_depth():
    """The fitted limb-darkened shape, normalised: 1 at mid-transit, 0 outside T14."""
    fit = {"k": 0.1, "b": 0.3, "t14_hours": 3.0, "period_days": 4.0, "u1": 0.4, "u2": 0.25}
    tpl = dvtests.shape_template(fit, 3.0 / 24)
    assert tpl(np.array([0.0]))[0] == pytest.approx(1.0)
    assert tpl(np.array([0.07]))[0] == pytest.approx(0.0, abs=1e-12)
    assert 0.0 < tpl(np.array([0.06]))[0] < 1.0
    box = dvtests.shape_template(None, 0.1)
    assert box(np.array([0.0]))[0] == 1.0 and box(np.array([0.06]))[0] == 0.0


def test_epoch_depths_cover_only_observed_epochs(rng):
    t, f, e = _curve(rng, days=10.0, events=_transits(3000e-6, days=10.0))
    eps = epoch_depths(t, f, period=P, t0=T0, duration=DUR)
    assert [x["epoch"] for x in eps] == [0, 1, 2]
    assert [x["parity"] for x in eps] == ["even", "odd", "even"]


def test_decide_switch_replaces_phase_half_secondary():
    assert dvtests.decide(("secondary_eclipse",), base_disqualifying=DISQUALIFYING)       # replaced: passes
    assert not dvtests.decide(("secondary_any_phase",), base_disqualifying=DISQUALIFYING)
    assert not dvtests.decide(("low_snr",), base_disqualifying=DISQUALIFYING)             # base flags still count
    assert dvtests.decide(("crowded", "timing_inconsistent"), base_disqualifying=DISQUALIFYING)  # informational


def test_epochs_without_a_dip_stay_out_of_the_timing_tests():
    """An epoch whose fitted depth is not significant has no mid-time: on a P/2 alias every other epoch is empty, and
    its mid-time (the deepest noise dip in the window, 67 minutes off) flagged a clean planet timing_inconsistent."""
    eps = [{"epoch": n, "parity": "odd" if n % 2 else "even", "t_mid": 1.0 + 4.0 * n + (67 / 1440 if n % 2 else 0.0),
            "sigma": 1e-3, "depth": 600e-6 if n % 2 == 0 else 50e-6, "depth_err": 60e-6} for n in range(6)]
    r = timing_test(eps)
    assert r["n_epochs"] == 3 and [s["epoch"] for s in r["skipped_epochs"]] == [1, 3, 5]
    assert r["linear"]["chi2"] == pytest.approx(0.0, abs=1e-9) and not r["linear"]["inconsistent"]
    assert "half the true one" in r["period_alias_note"]
    # without depth errors (older callers) every epoch is kept
    assert timing_test([{k: v for k, v in e.items() if k != "depth_err"} for e in eps])["n_epochs"] == 6


def test_a_planet_vetted_at_half_its_period_gets_an_alias_note_not_a_timing_flag():
    from dvtests_helpers import trapezoid_lc

    for seed in range(3):
        lc = trapezoid_lc(seed=seed, period=8.0, t0=1.0, duration=0.15, depth=600e-6, noise=300e-6, gap=None)
        flags, m = extended_vet(lc.time, lc.flux, lc.flux_err, period=4.0, t0=1.0, duration=0.15)
        assert "timing_inconsistent" not in flags and "odd_even_timing" not in flags, (seed, flags)
        assert "half the true one" in m["timing"].get("period_alias_note", ""), m["timing"]

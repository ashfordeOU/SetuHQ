import numpy as np

from exoplan.lightcurve import LightCurve
from exoplan.preprocess import bin_lightcurve, clean, detrend, mad_sigma, running_median


def trapezoid(time: np.ndarray, t_start: float, t_end: float, depth: float) -> np.ndarray:
    """Flux deficit of a trapezoidal transit with 10 % ingress and egress (a test signal for the detrender)."""
    tau = 0.1 * (t_end - t_start)
    ingress = np.clip((time - t_start) / tau, 0.0, 1.0)
    egress = np.clip((t_end - time) / tau, 0.0, 1.0)
    return depth * np.minimum(ingress, egress) * ((time >= t_start) & (time <= t_end))


def test_running_median_of_constant_is_constant():
    time = np.linspace(0, 10, 500)
    assert np.allclose(running_median(time, np.full_like(time, 3.0), 1.0), 3.0)


def test_mad_sigma_matches_gaussian_scatter(rng):
    values = rng.normal(0, 0.01, 200_000)
    assert abs(mad_sigma(values) - 0.01) < 2e-4


def test_clean_removes_cosmic_ray_spike_but_keeps_transit_points(rng):
    time = np.arange(0, 5, 0.01)
    flux = 1 + rng.normal(0, 1e-4, time.size)
    flux[100] += 0.01  # upward spike, should go
    flux[300:310] -= 5e-4  # shallow dip, well inside the 10-sigma low limit, should stay
    lc = LightCurve("t", "TESS", time, flux, np.full(time.size, 1e-4))
    cleaned = clean(lc)
    assert len(cleaned) == len(lc) - 1
    assert np.any(cleaned.flux < 1 - 3e-4)


def test_clean_drops_invalid_errors():
    time = np.arange(10.0)
    lc = LightCurve("t", "TESS", time, np.ones(10), np.r_[np.zeros(3), np.full(7, 1e-4)])
    assert len(clean(lc)) == 7


def test_detrend_preserves_transit_depth(rng):
    time = np.arange(0, 13, 10 / 1440)
    trend = 1 + 0.01 * np.sin(2 * np.pi * time / 5.0)  # slow, curved stellar variability
    transit = trapezoid(time, 6.0, 6.2, 0.003)
    flux = trend * (1 - transit) + rng.normal(0, 1e-4, time.size)
    lc = LightCurve("t", "TESS", time, flux, np.full(time.size, 1e-4))
    out = detrend(lc, window_days=1.0)
    in_transit = (time > 6.05) & (time < 6.15)
    depth = 1 - np.mean(out.flux[in_transit])
    assert 0.0025 < depth < 0.0035


def test_bin_lightcurve_reduces_points_and_adds_errors_in_quadrature():
    time = np.arange(0, 1, 1 / 1440)  # one-minute cadence over a day
    lc = LightCurve("t", "TESS", time, np.ones(time.size), np.full(time.size, 1e-3))
    binned = bin_lightcurve(lc, 10)
    assert len(binned) == 144
    expected = 1e-3 / np.sqrt(10)
    assert abs(np.median(binned.flux_err) - expected) / expected < 0.05


def test_detrend_mask_does_not_depend_on_flux_units(rng):
    time = np.arange(0, 13, 2 / 1440)
    transit = trapezoid(time, 6.0, 6.15, 0.005)
    relative = (1 - transit) + rng.normal(0, 1e-4, time.size)
    depths = []
    for scale in (1.0, 1e4):
        lc = LightCurve("t", "TESS", time, relative * scale, np.full(time.size, 1e-4 * scale))
        out = detrend(lc, window_days=1.0)
        inside = (time > 6.03) & (time < 6.12)
        depths.append(1 - np.mean(out.flux[inside]))
    assert abs(depths[0] - depths[1]) < 2e-4
    assert depths[0] > 0.0045


import pytest  # noqa: E402

from exoplan.preprocess import diff_sigma, low_runs  # noqa: E402


def _eclipse_curve(rng, sigmas, *, noise=3e-4):
    """2-minute cadence, 6 days, one 2-hour box eclipse per entry at depth = sigma x the point noise."""
    time = np.arange(0.0, 6.0, 2 / 1440)
    flux = 1 + rng.normal(0, noise, time.size)
    centres = []
    for i, s in enumerate(sigmas):
        c = 1.0 + 1.5 * i
        flux[np.abs(time - c) < 1 / 24] -= s * noise
        centres.append(c)
    return LightCurve(target="T", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, noise)), centres


@pytest.mark.parametrize("sigma", [10, 11, 12, 15, 17, 20, 100])
def test_clean_keeps_deep_eclipses(rng, sigma):
    """Eclipses 10 to 100 times the per-point scatter (a 3% binary at 300 ppm) survive cleaning point for point,
    including the 10-12 sigma band where points straddle the clip (the hysteresis keeps them).
    Before the run-length guard every one of their points was removed."""
    lc, (c,) = _eclipse_curve(rng, [sigma])
    inside = np.abs(lc.time - c) < 1 / 24
    cleaned = clean(lc)
    kept = np.isin(lc.time[inside], cleaned.time)
    assert kept.all()
    assert 1 - np.mean(cleaned.flux[np.abs(cleaned.time - c) < 1 / 24]) == pytest.approx(sigma * 3e-4, rel=0.05)


def test_clean_still_removes_isolated_low_and_high_spikes(rng):
    lc, _ = _eclipse_curve(rng, [])
    flux = lc.flux.copy()
    flux[[100, 900, 901, 2000, 2500, 2501, 2502]] -= 0.01   # a lone point, a pair and a triple: all removed
    flux[3000] += 0.01                            # an upward spike: removed as before
    lc = lc.with_data(lc.time, flux, lc.flux_err)
    cleaned = clean(lc)
    for i in (100, 900, 901, 2000, 2500, 2501, 2502, 3000):
        assert lc.time[i] not in cleaned.time
    assert len(cleaned) == len(lc) - 8
    assert cleaned.provenance["spike_clip_low_min_run"] == 10      # 20 minutes at 2-minute cadence


def test_low_runs():
    m = np.array([1, 0, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1], bool)
    assert low_runs(m, 3).tolist() == [0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 1]


def test_deep_eclipse_reaches_the_prepared_light_curve(rng):
    """Through the whole preparation (clean, normalise, detrend, 10-minute bins) a 20-sigma eclipse keeps its depth."""
    from exoplan.config import RunConfig
    from exoplan.pipeline import prepare_lightcurves

    lc, (c,) = _eclipse_curve(rng, [20])
    (prep,) = prepare_lightcurves([lc], RunConfig(name="x"))
    inside = np.abs(prep.time - c) < 0.75 / 24
    assert inside.sum() >= 8
    assert 1 - np.mean(prep.flux[inside]) == pytest.approx(20 * 3e-4, rel=0.1)
    assert diff_sigma(lc.flux) > 0


def test_clean_run_length_follows_the_cadence(rng):
    """The run that saves a deep dip is 20 minutes long: 10 cadences at 2 minutes, 3 (the minimum) at 30 minutes."""
    time = np.arange(0.0, 20.0, 30 / 1440)
    flux = 1 + rng.normal(0, 3e-4, time.size)
    flux[[300, 301, 302]] -= 0.01               # 90 minutes at 30-minute cadence: a real dip, kept
    flux[500] -= 0.01                           # one cadence: removed
    lc = LightCurve(target="T", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 3e-4))
    cleaned = clean(lc)
    assert cleaned.provenance["spike_clip_low_min_run"] == 3
    assert np.isin(time[[300, 301, 302]], cleaned.time).all() and time[500] not in cleaned.time

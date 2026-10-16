import numpy as np

from exoplan.injection import trapezoid
from exoplan.lightcurve import LightCurve
from exoplan.preprocess import bin_lightcurve, clean, detrend, mad_sigma, running_median


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

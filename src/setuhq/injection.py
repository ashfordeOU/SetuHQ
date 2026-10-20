"""Synthetic light curves with known transits.

Injection is how a volunteer panel, or Claude's panel, is calibrated. Each
reviewer's hit rate on injected transits (true positives) and its marks on
empty segments (false positives) give a skill score, which becomes its weight
in the consensus.

The noise model is white noise plus red noise (an AR(1) process with a
0.5-day timescale), with a small fraction of cadences dropped. It is only a
stand-in for real stellar and instrumental noise, and the benchmarks say so.

Each injected transit is the same limb-darkened model the transit fit uses
(:func:`setuhq.transitfit.inject_transit`: quadratic limb darkening, Claret
2017 TESS coefficients for a Sun-like star), not a box or trapezoid, so a box
detector is not flattered by box-shaped fakes. ``depth`` is the mid-transit
depth and the duration is T14; ``b`` is the impact parameter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from setuhq.subjects import Subject


@dataclass(frozen=True)
class Injection:
    t_start: float
    t_end: float
    depth: float
    b: float = 0.3

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    def hit_by(self, t_center: float, tolerance: float | None = None) -> bool:
        """True if a mark centred at ``t_center`` lies within this transit, widened by ``tolerance``."""
        pad = 0.5 * self.duration if tolerance is None else tolerance
        return self.t_start - pad <= t_center <= self.t_end + pad


def limb_darkened(time: np.ndarray, injection: Injection, *, exptime: float = 0.0) -> np.ndarray:
    """Relative flux of the injected transit: the fit's own limb-darkened model (single transit, long period)."""
    from setuhq.transitfit import inject_transit

    mid = 0.5 * (injection.t_start + injection.t_end)
    return inject_transit(time, mid, injection.depth, injection.duration, b=injection.b, exptime=exptime)


def random_injection(rng: np.random.Generator, length_days: float, *, depth_ppm=(300.0, 3000.0), duration_hours=(1.0, 6.0)) -> Injection:
    """Depth is log-uniform, duration uniform and the impact parameter uniform in [0, 0.9], within the given
    ranges. The transit lies inside the segment."""
    log_lo, log_hi = np.log10(depth_ppm[0]), np.log10(depth_ppm[1])
    depth = 10 ** rng.uniform(log_lo, log_hi) * 1e-6
    duration = rng.uniform(*duration_hours) / 24.0
    t_start = rng.uniform(0.15 * length_days, 0.85 * length_days - duration)
    return Injection(t_start=t_start, t_end=t_start + duration, depth=depth, b=float(rng.uniform(0.0, 0.9)))


def fixed_injection(length_days: float, depth_ppm: float, duration_hours: float) -> Injection:
    """A transit of fixed depth and duration, placed at the centre of the segment."""
    duration = duration_hours / 24.0
    t_start = 0.5 * length_days - 0.5 * duration
    return Injection(t_start=t_start, t_end=t_start + duration, depth=depth_ppm * 1e-6)


def detrended(subject: Subject, window_days: float = 1.0) -> Subject:
    """Run a synthetic subject through the same detrending as real data, so calibration sees the pipeline's conditions."""
    from setuhq.lightcurve import LightCurve
    from setuhq.preprocess import detrend

    lc = detrend(
        LightCurve(subject.provenance.get("target", "synthetic"), subject.mission, subject.time, subject.flux, subject.flux_err),
        window_days=window_days,
    )
    return Subject(
        subject_id=subject.subject_id,
        mission=subject.mission,
        time_unit=subject.time_unit,
        time=lc.time,
        flux=lc.flux,
        flux_err=lc.flux_err,
        provenance=subject.provenance,
    )


def synthetic_subject(
    rng: np.random.Generator,
    *,
    subject_id: str,
    length_days: float = 13.0,
    cadence_min: float = 10.0,
    white_ppm: float = 300.0,
    red_ppm: float = 200.0,
    injections: tuple[Injection, ...] = (),
    dropout_fraction: float = 0.02,
) -> Subject:
    cadence = cadence_min / 1440.0
    time = np.arange(0.0, length_days, cadence)
    keep = rng.random(time.size) > dropout_fraction
    time = time[keep]

    phi = np.exp(-cadence / 0.5)
    red = lfilter([np.sqrt(1 - phi * phi)], [1.0, -phi], rng.normal(size=time.size)) * red_ppm * 1e-6
    white = rng.normal(0.0, white_ppm * 1e-6, size=time.size)
    flux = 1.0 + red + white
    for injection in injections:
        flux = flux * limb_darkened(time, injection, exptime=cadence)
    flux_err = np.full(time.size, white_ppm * 1e-6)
    return Subject(
        subject_id=subject_id,
        mission="SYNTHETIC",
        time_unit="days",
        time=time,
        flux=flux,
        flux_err=flux_err,
        provenance={"target": "synthetic", "injections": [i.__dict__ for i in injections]},
    )

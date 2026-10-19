"""Vetting: the checks that separate planet-like dips from eclipsing binaries and artefacts.

Planet Hunters candidates are vetted by the science team after volunteer
selection. This module applies the same kind of tests automatically, using
only the light curve (no centroid or pixel data is available here):

* ``low_snr``: the event is too weak to trust.
* ``too_short``: the dip is shorter than any plausible transit.
* ``edge_event``: the dip sits at the edge of a segment, so it is only partly observed.
* ``odd_even_mismatch``: alternate transits differ in depth. This suggests a
  binary at twice the period. The BLS errors are inflated by the per-epoch depths'
  scatter about their parity means and get a 2% systematic floor (since the review fixes
  after 5a03087; before, a clean 1% hot Jupiter failed this test).
* ``secondary_eclipse``: a significant dip at phase 0.5. This suggests an eclipsing binary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from exoplan.preprocess import mad_sigma
from exoplan.search import PeriodicSignal
from exoplan.subjects import Subject

ODD_EVEN_FLOOR = 0.02  # systematic floor on each parity's depth error, as a fraction of its depth
DISQUALIFYING = frozenset({"insufficient_points", "low_snr", "too_short", "odd_even_mismatch", "secondary_eclipse"})


@dataclass(frozen=True)
class VettingResult:
    passed: bool
    flags: tuple[str, ...]
    metrics: dict = field(default_factory=dict)


def vet_event(
    t_start: float,
    t_end: float,
    subject: Subject,
    periodic: PeriodicSignal | None = None,
    *,
    min_snr: float = 7.0,
    min_duration_minutes: float = 15.0,
    edge_days: float = 0.1,
    sigma_threshold: float = 3.0,
) -> VettingResult:
    flags: list[str] = []
    inside = (subject.time >= t_start) & (subject.time <= t_end)
    n_in = int(inside.sum())
    metrics: dict = {"n_in_transit": n_in}
    if n_in < 2:
        flags.append("insufficient_points")
        return VettingResult(False, tuple(flags), metrics)

    depth = float(1.0 - np.mean(subject.flux[inside]))
    noise = mad_sigma(subject.flux - 1.0)
    snr = depth / (noise / np.sqrt(n_in)) if np.isfinite(noise) and noise > 0 else 0.0
    duration_minutes = (t_end - t_start) * 1440.0
    metrics.update(depth=depth, snr=snr, duration_minutes=duration_minutes)

    if snr < min_snr:
        flags.append("low_snr")
    if duration_minutes < min_duration_minutes:
        flags.append("too_short")
    if t_start - subject.start < edge_days or subject.end - t_end < edge_days:
        flags.append("edge_event")

    if periodic is not None:
        metrics.update(odd_err=periodic.odd_err, even_err=periodic.even_err, secondary_depth=periodic.secondary_depth, secondary_err=periodic.secondary_err)
        # BLS's odd/even errors are white-noise errors. Box depths scatter more than that from epoch to epoch (where
        # the bins fall on ingress and egress, a small period error), so they are inflated by the per-epoch depths'
        # scatter about their parity means and given a 2% systematic floor each (dvtests.odd_even_depth_test).
        scale = _parity_scale(subject, periodic)
        odd_err = math.hypot(periodic.odd_err * scale, ODD_EVEN_FLOOR * abs(periodic.odd_depth))
        even_err = math.hypot(periodic.even_err * scale, ODD_EVEN_FLOOR * abs(periodic.even_depth))
        metrics.update(odd_even_error_scale=scale)
        odd_even_sigma = np.hypot(odd_err, even_err)
        # Both parities must show a real dip, else one lone transit fakes a mismatch.
        both_present = min(
            periodic.odd_depth / periodic.odd_err if periodic.odd_err > 0 else 0.0,
            periodic.even_depth / periodic.even_err if periodic.even_err > 0 else 0.0,
        ) >= 5.0
        if (
            both_present
            and odd_even_sigma > 0
            and abs(periodic.odd_depth - periodic.even_depth) > sigma_threshold * odd_even_sigma
        ):
            flags.append("odd_even_mismatch")
        if periodic.secondary_err > 0 and periodic.secondary_depth > sigma_threshold * periodic.secondary_err:
            flags.append("secondary_eclipse")
        metrics.update(period=periodic.period, odd_depth=periodic.odd_depth, even_depth=periodic.even_depth)

    passed = not (set(flags) & DISQUALIFYING)
    return VettingResult(passed, tuple(flags), metrics)


def _parity_scale(subject: Subject, periodic: PeriodicSignal) -> float:
    """√χ²ᵣ (at least 1) of the per-epoch box depths about their parity means, at the BLS ephemeris."""
    from exoplan.dvtests import parity_scatter_scale

    eps = [e for e in measure_epochs(subject, periodic) if e["depth_ppm"] is not None and e["sigma_ppm"]]
    if len(eps) < 3:
        return 1.0
    scale, _, _ = parity_scatter_scale([e["depth_ppm"] for e in eps], [e["sigma_ppm"] for e in eps],
                                       [e["epoch"] % 2 for e in eps])
    return scale


def measure_epochs(subject: Subject, periodic: PeriodicSignal, *, phase: float = 0.0) -> list[dict]:
    """Measure the depth at every BLS-predicted epoch inside the subject.

    Each window is centred on ``t0 + (k + phase) * period`` and is one BLS
    duration wide. ``phase=0.5`` measures the secondary windows. The depth is
    1 minus the mean flux of the points inside; its sigma is the subject's
    robust scatter divided by sqrt(n), the same noise model as the SNR check.
    An epoch with fewer than two points stores ``None`` for depth and sigma,
    which means the data do not cover it, not that a dip is absent.

    Epochs are predicted within this one subject, never across the sector.
    """
    if periodic.period <= 0:
        return []
    noise = mad_sigma(subject.flux - 1.0)
    half = 0.5 * periodic.duration
    k_lo = int(np.ceil((subject.start - periodic.t0) / periodic.period - phase))
    k_hi = int(np.floor((subject.end - periodic.t0) / periodic.period - phase))
    out: list[dict] = []
    for k in range(k_lo, k_hi + 1):
        mid = periodic.t0 + (k + phase) * periodic.period
        inside = np.abs(subject.time - mid) <= half
        n = int(inside.sum())
        depth = sigma = None
        if n >= 2:
            depth = float(1.0 - np.mean(subject.flux[inside])) * 1e6
            sigma = float(noise / np.sqrt(n)) * 1e6 if np.isfinite(noise) else None
        out.append({"epoch": k, "t_mid": float(mid), "n_points": n, "depth_ppm": depth, "sigma_ppm": sigma})
    return out

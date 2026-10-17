"""Vetting: the checks that separate planet-like dips from eclipsing binaries and artefacts.

Planet Hunters candidates are vetted by the science team after volunteer
selection. This module applies the same kind of tests automatically, using
only the light curve (no centroid or pixel data is available here):

* ``low_snr``: the event is too weak to trust.
* ``too_short``: the dip is shorter than any plausible transit.
* ``edge_event``: the dip sits at the edge of a segment, so it is only partly observed.
* ``odd_even_mismatch``: alternate transits differ in depth. This suggests a
  binary at twice the period.
* ``secondary_eclipse``: a significant dip at phase 0.5. This suggests an eclipsing binary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from exoplan.preprocess import mad_sigma
from exoplan.search import PeriodicSignal
from exoplan.subjects import Subject

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
        odd_even_sigma = np.hypot(periodic.odd_err, periodic.even_err)
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

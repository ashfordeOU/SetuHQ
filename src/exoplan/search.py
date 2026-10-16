"""Automatic signal search. This is the machine's own view, used for vetting and calibration.

Two complementary searches:

* :func:`bls_search` finds periodic box-shaped dips with Box Least Squares
  (Kovács et al. 2002, as implemented in astropy). It needs at least two transits.
* :func:`single_event_search` finds one-off dips with a boxcar matched filter.
  This is the mode Planet Hunters depends on, since volunteers were good at
  single transits that periodic searches miss.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from astropy.timeseries import BoxLeastSquares

from exoplan.preprocess import mad_sigma
from exoplan.subjects import Subject

DEFAULT_DURATIONS_DAYS = (1 / 24, 2 / 24, 4 / 24, 8 / 24)


@dataclass(frozen=True)
class PeriodicSignal:
    period: float
    t0: float
    duration: float
    depth: float
    snr: float
    n_transits: int
    odd_depth: float
    odd_err: float
    even_depth: float
    even_err: float
    secondary_depth: float
    secondary_err: float

    def covers(self, time: float) -> bool:
        """True if ``time`` falls within one duration of a predicted transit."""
        phase = (time - self.t0 + 0.5 * self.period) % self.period - 0.5 * self.period
        return abs(phase) <= self.duration


@dataclass(frozen=True)
class SingleEvent:
    t_start: float
    t_end: float
    depth: float
    snr: float

    @property
    def center(self) -> float:
        return 0.5 * (self.t_start + self.t_end)

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start


def bls_search(
    subject: Subject,
    *,
    min_period: float = 0.5,
    max_period: float | None = None,
    durations=DEFAULT_DURATIONS_DAYS,
) -> PeriodicSignal | None:
    """Return the strongest periodic box signal in a subject, or ``None`` if there is none to search."""
    span = subject.end - subject.start
    if max_period is None:
        max_period = span / 2.0
    if max_period <= min_period or len(subject) < 10:
        return None

    model = BoxLeastSquares(subject.time, subject.flux, dy=subject.flux_err)
    periods = model.autoperiod(
        durations,
        minimum_period=min_period,
        maximum_period=max_period,
        minimum_n_transit=2,
        frequency_factor=1.0,
    )
    if periods.size == 0:
        return None

    result = model.power(periods, durations, objective="snr")
    i = int(np.argmax(result.power))
    period = float(result.period[i])
    t0 = float(result.transit_time[i])
    duration = float(result.duration[i])
    stats = model.compute_stats(period, duration, t0)

    counts = np.asarray(stats["per_transit_count"])
    odd_depth, odd_err = stats["depth_odd"]
    even_depth, even_err = stats["depth_even"]
    sec_depth, sec_err = stats["depth_phased"]
    return PeriodicSignal(
        period=period,
        t0=t0,
        duration=duration,
        depth=float(result.depth[i]),
        snr=float(result.depth_snr[i]),
        n_transits=int(np.count_nonzero(counts > 0)),
        odd_depth=float(odd_depth),
        odd_err=float(odd_err),
        even_depth=float(even_depth),
        even_err=float(even_err),
        secondary_depth=float(sec_depth),
        secondary_err=float(sec_err),
    )


def single_event_search(
    subject: Subject,
    *,
    durations=DEFAULT_DURATIONS_DAYS,
    snr_threshold: float = 5.0,
    max_events: int = 10,
) -> list[SingleEvent]:
    """Boxcar matched filter for single dips. Returns non-overlapping events, strongest first.

    A window that spans a data gap is rejected, so a gap cannot fake a dip.

    Significance is measured empirically for each duration: the robust scatter
    of all boxcar means in the subject. Red noise therefore raises the
    threshold automatically, which a white-noise sigma would not do.
    """
    time = subject.time
    if time.size < 4:
        return []
    cadence = float(np.median(np.diff(time)))
    if not np.isfinite(cadence) or cadence <= 0:
        return []
    deficit = subject.flux - 1.0
    cumsum = np.concatenate([[0.0], np.cumsum(deficit)])

    candidates: list[tuple[float, int, int, float, float]] = []
    for duration in durations:
        n = max(2, int(round(duration / cadence)))
        if n >= time.size:
            continue
        starts = np.arange(time.size - n + 1)
        mean_dip = -(cumsum[starts + n] - cumsum[starts]) / n
        scale = mad_sigma(mean_dip)
        if not np.isfinite(scale) or scale <= 0:
            continue
        contiguous = (time[starts + n - 1] - time[starts]) <= 1.5 * max(n - 1, 1) * cadence
        snr = np.where(contiguous, mean_dip / scale, -np.inf)
        for i in np.flatnonzero(snr >= snr_threshold):
            candidates.append((float(snr[i]), int(i), int(i + n - 1), float(mean_dip[i]), float(duration)))

    candidates.sort(key=lambda c: c[0], reverse=True)
    chosen: list[SingleEvent] = []
    for snr, first, last, depth, _ in candidates:
        t_start, t_end = float(time[first]), float(time[last])
        if any(t_start <= e.t_end + cadence and t_end >= e.t_start - cadence for e in chosen):
            continue
        chosen.append(SingleEvent(t_start=t_start, t_end=t_end, depth=depth, snr=snr))
        if len(chosen) >= max_events:
            break
    return chosen

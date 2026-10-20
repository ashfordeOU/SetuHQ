# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Automatic signal search. This is the machine's own view, used for vetting and calibration.

Two complementary searches:

* :func:`bls_search` finds periodic box-shaped dips with Box Least Squares
  (Kovács et al. 2002, as implemented in astropy). It needs at least two transits.
* :func:`single_event_search` finds one-off dips with a boxcar matched filter.
  This is the mode Planet Hunters depends on, since volunteers were good at
  single transits that periodic searches miss.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from astropy.timeseries import BoxLeastSquares

from setuhq.preprocess import mad_sigma
from setuhq.subjects import Subject

DEFAULT_DURATIONS_DAYS = (1 / 24, 2 / 24, 4 / 24, 8 / 24)
MAX_PERIODS = 200_000  # cap on the BLS period grid; a longer baseline gets a coarser grid


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
    # Empirical false-alarm probability from block-bootstrap trials (false_alarm_probability), or None if not run.
    # When no trial reached the observed SNR, ``fap`` is the upper bound 1/(N + 1) and ``fap_bound`` is True.
    fap: float | None = None
    fap_trials: int = 0
    fap_exceed: int = 0
    fap_bound: bool = False
    fap_tail: float | None = None   # Gumbel fit to the null maxima, extrapolated (indicative only)
    fap_method: str = ""

    @property
    def fap_label(self) -> str:
        """The FAP as it may be printed: never below what the trials resolve."""
        return fap_label(self.fap, self.fap_trials, self.fap_bound)

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
    max_periods: int = MAX_PERIODS,
) -> PeriodicSignal | None:
    """Return the strongest periodic box signal in a subject, or ``None`` if there is none to search.

    The subject may be one segment or a stitched multi-sector light curve
    (:func:`stitch`). The default ``max_period`` is half the time span. When
    the span makes the period grid longer than ``max_periods``, the grid is
    thinned evenly in frequency to that many periods.
    """
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
    if periods.size > max_periods:
        periods = periods[np.linspace(0, periods.size - 1, max_periods).round().astype(int)]

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


FAP_TRIALS = 20
FAP_BLOCK_DAYS = 0.5
FAP_METHOD = ("block bootstrap: the detected box is removed, the residuals are cut into {block:g}-day blocks and "
              "shuffled, and BLS reruns on each of {n:,} copies; p = (k + 1)/(N + 1) with k copies reaching the observed "
              "SNR (Davison & Hinkley 1997); with k = 0 it is an upper bound. Tail: a Gumbel fit to the {n:,} null "
              "maxima, indicative, extrapolated beyond the trials, conservative (BLS maxima are lighter-tailed than "
              "Gumbel), never given below 1e-6")
FAP_CACHE_VERSION = 2  # part of the null-maxima cache key: bump it when the trial procedure changes
FAP_TAIL_FLOOR = 1e-6  # the extrapolated tail is never given below this


@dataclass(frozen=True)
class FapResult:
    fap: float
    n_trials: int
    exceed: int
    bound: bool
    tail: float | None
    method: str


def fap_label(fap: float | None, n_trials: int, bound: bool) -> str:
    if fap is None or n_trials <= 0:
        return "not computed"
    return (f"< {fap:.1e}" if bound else f"{fap:.2g}") + f" ({n_trials:,} trials)"


def _fap_cache_key(time, residual, flux_err, params: tuple, version: int | None = FAP_CACHE_VERSION) -> str:
    """The null-maxima cache key: the data, the grid and trial parameters, and FAP_CACHE_VERSION (None: the
    key used before the version was added)."""
    import hashlib

    tail = params if version is None else params + (version,)
    return hashlib.sha256(b"".join([np.ascontiguousarray(time).tobytes(), np.ascontiguousarray(residual).tobytes(),
                                    np.ascontiguousarray(flux_err).tobytes(), repr(tail).encode()])).hexdigest()[:32]


def fap_inputs(subject: Subject, signal: PeriodicSignal, block_days: float = FAP_BLOCK_DAYS) -> tuple[np.ndarray, list]:
    """The block bootstrap's inputs: the flux with the detected box removed, and the index blocks to shuffle."""
    time, flux = subject.time, subject.flux
    phase = (time - signal.t0 + 0.5 * signal.period) % signal.period - 0.5 * signal.period
    residual = flux + signal.depth * (np.abs(phase) <= 0.5 * signal.duration)
    cadence = float(np.median(np.diff(time))) if time.size > 1 else 0.0
    per_block = max(2, int(round(block_days / cadence))) if cadence > 0 else time.size
    blocks = [np.arange(i, min(i + per_block, time.size)) for i in range(0, time.size, per_block)]
    return residual, blocks


def fap_seeds(seed: int, n_trials: int) -> np.ndarray:
    """The trials' seeds. The first n of a longer run are the seeds of an n-trial run, so trials can be extended."""
    return np.random.default_rng(seed).integers(0, 2**63 - 1, size=n_trials)


def fap_tail_label(tail: float | None) -> str:
    """The Gumbel tail as it may be printed: indicative, and never below FAP_TAIL_FLOOR."""
    if tail is None:
        return "not computed (fewer than 100 trials)"
    head = f"< {FAP_TAIL_FLOOR:.0e}" if tail <= FAP_TAIL_FLOOR else f"≈ {tail:.1e}"
    return f"{head} (indicative, extrapolated beyond the trials, conservative: BLS maxima are lighter-tailed than Gumbel)"


def _null_maxima(args) -> list[float]:
    time, residual, flux_err, blocks, seeds, min_period, max_period, durations, sid, mission, unit = args
    out = []
    for seed in seeds:
        rng = np.random.default_rng(int(seed))
        order = np.concatenate([blocks[i] for i in rng.permutation(len(blocks))])
        scrambled = Subject(sid, mission, unit, time, residual[order], flux_err[order], {})
        trial = bls_search(scrambled, min_period=min_period, max_period=max_period, durations=durations)
        out.append(float(trial.snr) if trial is not None else float("-inf"))
    return out


def false_alarm_probability(
    subject: Subject,
    signal: PeriodicSignal,
    *,
    min_period: float = 0.5,
    max_period: float | None = None,
    durations=DEFAULT_DURATIONS_DAYS,
    n_trials: int = FAP_TRIALS,
    block_days: float = FAP_BLOCK_DAYS,
    seed: int = 0,
    cache_dir: str | Path | None = None,
    workers: int | None = None,
    stop_after: int | None = None,
) -> FapResult:
    """Empirical false-alarm probability of a BLS peak, with red noise kept.

    The BLS SNR assumes white noise. Here the detected box model is removed
    from the flux, the residuals are cut into contiguous blocks of about
    ``block_days`` and the blocks are shuffled in time (a block bootstrap), so
    correlated noise within a block survives but any periodicity is destroyed.
    BLS runs on each of ``n_trials`` scrambled copies with the same grid
    limits, and records each copy's peak SNR (the null maxima).

    The FAP is (k + 1)/(N + 1), with k copies at or above the observed SNR. With
    k = 0 that is an upper bound, and ``bound`` says so: nothing smaller is ever
    reported from N trials. With N ≥ 100 a Gumbel fit to the null maxima gives
    an extrapolated tail value, kept separately and labelled indicative.

    The null maxima are cached under ``cache_dir`` (keyed by the data, grid,
    seed and FAP_CACHE_VERSION), so a re-run costs nothing; with ``workers`` > 1 the trials run in
    parallel processes, each with its own fixed seed (the result does not
    depend on the number of workers).

    With ``stop_after`` = m, the trials run in order in chunks and stop as soon as more than m of them reach the
    observed SNR: the signal then cannot pass a cut at (m + 1)/(N + 1), and the FAP returned, (k + 1)/(n + 1) over
    the n trials run, is above it. A run that completes is the same as without ``stop_after`` (same seeds, same order).
    """
    time = subject.time
    residual, blocks = fap_inputs(subject, signal, block_days)
    seeds = fap_seeds(seed, n_trials)
    key = _fap_cache_key(time, residual, subject.flux_err, (min_period, max_period, tuple(durations), block_days, seed, n_trials))
    path = Path(cache_dir) / f"{key}.json" if cache_dir else None
    null = None
    if path and path.exists():
        null = json.loads(path.read_text()).get("null_max")
    stopped = False
    if null is None:
        common = (time, residual, subject.flux_err, blocks)
        tail_args = (min_period, max_period, durations, subject.subject_id, subject.mission, subject.time_unit)
        workers = workers if workers is not None else (min(4, os.cpu_count() or 1) if n_trials >= 200 else 1)
        if stop_after is not None:
            null = []
            pool = None
            if workers > 1:
                import multiprocessing as mp

                pool = mp.get_context("fork").Pool(workers)
            try:
                for start in range(0, n_trials, 50):
                    chunk = seeds[start:start + 50]
                    if pool is not None:
                        parts = pool.map(_null_maxima, [common + (c,) + tail_args for c in np.array_split(chunk, workers) if len(c)])
                        null += [x for part in parts for x in part]
                    else:
                        null += _null_maxima(common + (chunk,) + tail_args)
                    if sum(1 for x in null if x >= signal.snr) > stop_after:
                        stopped = len(null) < n_trials
                        break
            finally:
                if pool is not None:
                    pool.close()
                    pool.join()
        elif workers > 1:
            import multiprocessing as mp

            chunks = np.array_split(seeds, workers * 4)
            with mp.get_context("fork").Pool(workers) as pool:
                parts = pool.map(_null_maxima, [common + (c,) + tail_args for c in chunks if len(c)])
            null = [x for part in parts for x in part]
        else:
            null = _null_maxima(common + (seeds,) + tail_args)
        if path and not stopped:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"subject_id": subject.subject_id, "n_trials": n_trials, "seed": seed,
                                        "block_days": block_days, "cache_version": FAP_CACHE_VERSION, "null_max": null}))
    if n_trials <= 0:
        return FapResult(float("nan"), 0, 0, False, None, "")
    arr = np.asarray(null, float)
    exceed = int(np.count_nonzero(arr >= signal.snr))
    if stopped:
        n_run = arr.size
        return FapResult(fap=(exceed + 1) / (n_run + 1), n_trials=n_run, exceed=exceed, bound=False, tail=None,
                         method=FAP_METHOD.format(block=block_days, n=n_trials)
                         + f"; stopped after {n_run:,} of {n_trials:,} trials once {exceed} reached the observed SNR, so the "
                           f"FAP is above {(stop_after + 1) / (n_trials + 1):.1e}")
    fap = (exceed + 1) / (n_trials + 1)
    tail = None
    finite = arr[np.isfinite(arr)]
    if finite.size >= 100:
        from scipy.stats import gumbel_r

        loc, scale = gumbel_r.fit(finite)
        tail = max(float(gumbel_r.sf(signal.snr, loc, scale)), FAP_TAIL_FLOOR)
    return FapResult(fap=float(fap), n_trials=n_trials, exceed=exceed, bound=exceed == 0, tail=tail,
                     method=FAP_METHOD.format(block=block_days, n=n_trials))


def with_fap(subject: Subject, signal: PeriodicSignal | None, *, min_period: float = 0.5,
             n_trials: int = FAP_TRIALS, seed: int | None = None, cache_dir: str | Path | None = None,
             stop_after: int | None = None) -> PeriodicSignal | None:
    """``signal`` with its false-alarm probability filled in. The seed defaults to one derived from the subject id."""
    if signal is None or n_trials <= 0:
        return signal
    if seed is None:
        import hashlib

        seed = int(hashlib.sha256(subject.subject_id.encode()).hexdigest()[:8], 16)
    r = false_alarm_probability(subject, signal, min_period=min_period, n_trials=n_trials, seed=seed, cache_dir=cache_dir,
                                stop_after=stop_after)
    return replace(signal, fap=r.fap, fap_trials=r.n_trials, fap_exceed=r.exceed, fap_bound=r.bound, fap_tail=r.tail,
                   fap_method=r.method)


def stitch(subjects_or_curves, *, subject_id: str | None = None) -> Subject:
    """Join light curves (or subjects) of one target into one time series for a multi-sector search.

    Each piece is divided by its own median flux first, so sectors with
    different flux levels line up at 1.0. The pieces should already be
    detrended. Times are sorted.
    """
    pieces = [p for p in subjects_or_curves if len(p) > 0]
    if not pieces:
        raise ValueError("nothing to stitch")
    time, flux, flux_err = [], [], []
    for piece in pieces:
        level = float(np.median(piece.flux))
        level = level if np.isfinite(level) and level != 0 else 1.0
        time.append(np.asarray(piece.time, float))
        flux.append(np.asarray(piece.flux, float) / level)
        flux_err.append(np.asarray(piece.flux_err, float) / abs(level))
    time, flux, flux_err = (np.concatenate(a) for a in (time, flux, flux_err))
    order = np.argsort(time, kind="stable")
    first = pieces[0]
    target = getattr(first, "target", None) or first.provenance.get("target", "")
    sectors = sorted({str(p.provenance.get("sector", "")) for p in pieces})
    from setuhq.subjects import TIME_UNITS

    return Subject(
        subject_id=subject_id or f"stitched-{target}",
        mission=first.mission,
        time_unit=getattr(first, "time_unit", None) or TIME_UNITS.get(first.mission, first.provenance.get("time_unit", "unknown")),
        time=time[order],
        flux=flux[order],
        flux_err=flux_err[order],
        provenance={"target": target, "sectors": sectors, "stitched_pieces": len(pieces)},
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

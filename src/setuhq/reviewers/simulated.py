"""Deterministic simulated volunteers.

These are classical detectors with human-like imperfections, not people and
not language models. They are the baseline panel and the calibration reference.
Each one has its own sensitivity, miss rate and boundary jitter. Every
subject gets its own seeded random stream, so runs are reproducible.

A simulated volunteer marks single events from :func:`single_event_search`. When
a periodic signal is strong enough, it also marks each predicted transit
epoch, as a human would mark each dip in a periodic light curve.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from setuhq.reviewers.base import NOISE, POTENTIAL_PLANET, Classification, Mark
from setuhq.search import bls_search, single_event_search
from setuhq.subjects import Subject


@dataclass
class SimulatedVolunteer:
    reviewer_id: str
    snr_threshold: float = 5.0
    miss_probability: float = 0.05
    boundary_jitter: float = 0.2
    periodic_snr_threshold: float = 10.0  # null BLS SNR on detrended noise peaks near 8.8 over 40 subjects
    seed: int = 0
    kind: str = "simulated"

    def available(self) -> bool:
        return True

    def review(self, subject: Subject, image_path: str | Path | None = None) -> Classification:
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, zlib.crc32(subject.subject_id.encode())]))
        marks: list[Mark] = []

        for event in single_event_search(subject, snr_threshold=self.snr_threshold):
            if rng.random() < self.miss_probability:
                continue
            marks.append(self._jittered(event.t_start, event.t_end, rng))

        periodic = bls_search(subject)
        if periodic is not None and periodic.snr >= self.periodic_snr_threshold:
            marks.extend(self._epoch_marks(subject, periodic, rng))

        marks = _drop_duplicates(marks)
        label = POTENTIAL_PLANET if marks else NOISE
        reason = None if marks else "other"
        confidence = min(1.0, len(marks) / 3.0) if marks else 0.0
        return Classification(
            reviewer_id=self.reviewer_id,
            subject_id=subject.subject_id,
            label=label,
            marks=tuple(marks),
            reason=reason,
            confidence=confidence,
            rationale="simulated detector",
        )

    def _jittered(self, t_start: float, t_end: float, rng: np.random.Generator) -> Mark:
        width = t_end - t_start
        start = t_start + rng.uniform(-self.boundary_jitter, self.boundary_jitter) * width
        end = t_end + rng.uniform(-self.boundary_jitter, self.boundary_jitter) * width
        if end <= start:
            end = start + max(width, 1e-4)
        return Mark(start, end)

    def _epoch_marks(self, subject: Subject, periodic, rng: np.random.Generator) -> list[Mark]:
        """Mark each predicted epoch only where the dip is actually present.

        An epoch counts when its in-window depth is at least half the periodic depth,
        so a single real transit is not marked again at an epoch where nothing happened.
        """
        marks = []
        first = int(np.ceil((subject.start - periodic.t0) / periodic.period))
        last = int(np.floor((subject.end - periodic.t0) / periodic.period))
        half = 0.5 * periodic.duration
        for k in range(first, last + 1):
            center = periodic.t0 + k * periodic.period
            inside = (subject.time >= center - half) & (subject.time <= center + half)
            if not inside.any():
                continue
            depth_here = 1.0 - float(np.mean(subject.flux[inside]))
            if depth_here < 0.5 * periodic.depth or rng.random() < self.miss_probability:
                continue
            marks.append(self._jittered(center - half, center + half, rng))
        return marks


def _drop_duplicates(marks: list[Mark]) -> list[Mark]:
    """Keep the first of any two marks whose centres fall within one mark width of each other."""
    kept: list[Mark] = []
    for mark in sorted(marks, key=lambda m: m.center):
        if kept and abs(mark.center - kept[-1].center) < 0.5 * (mark.t_end - mark.t_start + kept[-1].t_end - kept[-1].t_start):
            continue
        kept.append(mark)
    return kept

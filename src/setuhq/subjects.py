# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Subjects: the fixed-length, blind-coded units that reviewers look at.

Planet Hunters shows volunteers one light-curve segment at a time. This module
cuts each light curve into segments and gives every one an opaque ID. The
target name lives only in ``provenance`` and never reaches a reviewer, so a
review cannot be biased by knowing which star it is looking at.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

from setuhq.lightcurve import LightCurve

TIME_UNITS = {"TESS": "BTJD", "CHEOPS": "BJD_TDB-2457000"}


@dataclass(frozen=True, eq=False)
class Subject:
    subject_id: str
    mission: str
    time_unit: str
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    provenance: dict = field(default_factory=dict)

    @property
    def start(self) -> float:
        return float(self.time[0])

    @property
    def end(self) -> float:
        return float(self.time[-1])

    def __len__(self) -> int:
        return self.time.size


def blind_id(target: str, mission: str, sector, start: float) -> str:
    """Stable opaque identifier for a subject. It does not contain the target name."""
    key = f"{mission}|{target}|{sector}|{start:.6f}"
    return f"{mission.lower()}-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


def split_subjects(lc: LightCurve, *, length_days: float = 13.0, min_points: int = 300) -> list[Subject]:
    """Cut a light curve into consecutive, non-overlapping segments of ``length_days``.

    Segments with fewer than ``min_points`` points are skipped. A TESS sector is
    about 27 days, so 13-day subjects roughly match Planet Hunters' per-segment
    review of TESS data.
    """
    if len(lc) == 0:
        return []
    sector = lc.provenance.get("sector", "")
    subjects: list[Subject] = []
    start = float(lc.time[0])
    last = float(lc.time[-1])
    while start <= last:
        end = start + length_days
        mask = (lc.time >= start) & (lc.time < end)
        if mask.sum() >= min_points:
            subjects.append(
                Subject(
                    subject_id=blind_id(lc.target, lc.mission, sector, start),
                    mission=lc.mission,
                    time_unit=TIME_UNITS.get(lc.mission, lc.provenance.get("time_unit", "unknown")),
                    time=lc.time[mask],
                    flux=lc.flux[mask],
                    flux_err=lc.flux_err[mask],
                    provenance={"target": lc.target, "sector": sector, "segment_start": start, "segment_end": end, **lc.provenance},
                )
            )
        start = end
    return subjects

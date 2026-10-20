"""The reviewer interface: one independent classification of one subject.

The task mirrors the Planet Hunters CHEOPS classify workflow:

* T0, marking: mark the start and end of every dip that could be a transit.
* T1, classification: label the subject ``potential_planet`` or ``noise``.
  A ``noise`` label can carry a reason (eclipsing binary, stellar variability,
  instrumental, other).

Every reviewer, human or machine, returns a :class:`Classification` in this shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from setuhq.subjects import Subject

POTENTIAL_PLANET = "potential_planet"
NOISE = "noise"
LABELS = (POTENTIAL_PLANET, NOISE)
NOISE_REASONS = ("eclipsing_binary", "stellar_variability", "instrumental", "other")


@dataclass(frozen=True)
class Mark:
    t_start: float
    t_end: float
    kind: str = "transit"

    def __post_init__(self) -> None:
        if not (self.t_end > self.t_start):
            raise ValueError(f"mark end {self.t_end} must be after start {self.t_start}")

    @property
    def center(self) -> float:
        return 0.5 * (self.t_start + self.t_end)


@dataclass(frozen=True)
class Classification:
    reviewer_id: str
    subject_id: str
    label: str
    marks: tuple[Mark, ...] = ()
    reason: str | None = None
    confidence: float = 0.0
    rationale: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.label not in LABELS:
            raise ValueError(f"label must be one of {LABELS}, got {self.label!r}")
        if self.reason is not None and self.reason not in NOISE_REASONS:
            raise ValueError(f"reason must be one of {NOISE_REASONS}, got {self.reason!r}")


class Reviewer(Protocol):
    reviewer_id: str
    kind: str

    def available(self) -> bool: ...

    def review(self, subject: Subject, image_path: str | Path | None = None) -> Classification: ...

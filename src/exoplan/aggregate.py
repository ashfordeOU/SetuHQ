"""Consensus: turn many independent classifications into ranked events.

This follows the Planet Hunters idea. Marks from different reviewers that land
on the same dip are clustered in time. Each cluster is scored by the share of
the panel's skill-weighted reviewers who marked it. A cluster counts only if
the subject is also labelled ``potential_planet`` by enough of the weighted panel.

Clustering is single-linkage in one dimension: a mark joins a cluster when its
centre is within ``gap_days`` of the previous mark's centre.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from exoplan.reviewers.base import POTENTIAL_PLANET, Classification


@dataclass(frozen=True)
class Consensus:
    subject_id: str
    t_start: float
    t_end: float
    score: float
    n_reviewers: int
    reviewers: tuple[str, ...]
    planet_fraction: float

    @property
    def center(self) -> float:
        return 0.5 * (self.t_start + self.t_end)


def cluster_marks(entries, gap_days: float) -> list[list[tuple[str, float, float]]]:
    """Group ``(reviewer_id, t_start, t_end)`` entries into time clusters. Input order does not matter."""
    ordered = sorted(entries, key=lambda e: 0.5 * (e[1] + e[2]))
    clusters: list[list[tuple[str, float, float]]] = []
    last_center = None
    for entry in ordered:
        center = 0.5 * (entry[1] + entry[2])
        if last_center is None or center - last_center > gap_days:
            clusters.append([entry])
        else:
            clusters[-1].append(entry)
        last_center = center
    return clusters


def aggregate(
    classifications: list[Classification],
    weights: dict[str, float] | None = None,
    *,
    gap_days: float = 0.05,
    min_score: float = 0.5,
    min_planet_fraction: float = 0.5,
) -> list[Consensus]:
    """Return consensus events that pass both thresholds, grouped by subject and ordered by score."""
    weights = weights or {}
    by_subject: dict[str, list[Classification]] = defaultdict(list)
    for classification in classifications:
        by_subject[classification.subject_id].append(classification)

    results: list[Consensus] = []
    for subject_id in sorted(by_subject):
        panel = _latest_per_reviewer(by_subject[subject_id])
        total_weight = sum(_weight(weights, c.reviewer_id) for c in panel.values())
        if total_weight <= 0:
            continue
        planet_weight = sum(_weight(weights, c.reviewer_id) for c in panel.values() if c.label == POTENTIAL_PLANET)
        planet_fraction = planet_weight / total_weight
        if planet_fraction < min_planet_fraction:
            continue

        entries = [(c.reviewer_id, m.t_start, m.t_end) for c in panel.values() for m in c.marks]
        for cluster in cluster_marks(entries, gap_days):
            first_mark: dict[str, tuple[float, float]] = {}
            for reviewer_id, t_start, t_end in cluster:
                first_mark.setdefault(reviewer_id, (t_start, t_end))
            score = sum(_weight(weights, r) for r in first_mark) / total_weight
            if score < min_score:
                continue
            results.append(
                Consensus(
                    subject_id=subject_id,
                    t_start=median(t for t, _ in first_mark.values()),
                    t_end=median(t for _, t in first_mark.values()),
                    score=score,
                    n_reviewers=len(first_mark),
                    reviewers=tuple(sorted(first_mark)),
                    planet_fraction=planet_fraction,
                )
            )
    return sorted(_merge_duplicates(results, gap_days), key=lambda c: c.score, reverse=True)


def _merge_duplicates(events: list[Consensus], gap_days: float) -> list[Consensus]:
    """Keep the strongest of any two events in one subject whose centres are close.

    Two events are the same dip when their centres lie within half the sum of
    their durations plus the clustering gap. Clustering alone can split one dip
    when reviewers' boundaries disagree, and this step puts it back together.
    """
    kept: list[Consensus] = []
    # Ties go to the event with more reviewers, then to the wider one: the more complete dip wins.
    ranked = sorted(events, key=lambda c: (c.score, c.n_reviewers, c.t_end - c.t_start), reverse=True)
    for event in ranked:
        duplicate = any(
            other.subject_id == event.subject_id
            and abs(other.center - event.center)
            <= 0.5 * ((other.t_end - other.t_start) + (event.t_end - event.t_start)) + gap_days
            for other in kept
        )
        if not duplicate:
            kept.append(event)
    return kept


def _latest_per_reviewer(classifications: list[Classification]) -> dict[str, Classification]:
    """One classification per reviewer per subject. A later duplicate replaces an earlier one."""
    panel: dict[str, Classification] = {}
    for classification in classifications:
        panel[classification.reviewer_id] = classification
    return panel


def _weight(weights: dict[str, float], reviewer_id: str) -> float:
    return float(weights.get(reviewer_id, 1.0))

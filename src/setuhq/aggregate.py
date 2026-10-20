"""Consensus: turn many independent classifications into ranked events.

This follows the Planet Hunters idea. Marks from different reviewers that land
on the same dip are clustered in time. Each cluster is scored by the share of
the panel's skill-weighted reviewers who marked it. A cluster counts only if
the subject is also labelled ``potential_planet`` by enough of the weighted panel.

Clustering is single-linkage on intervals: marks are taken in order of start
time, and a mark joins the current cluster when its interval overlaps the
cluster's interval (the union of its marks so far) or its centre is within
``gap_days`` of the previous mark's centre. A wide mark that covers a dip
therefore counts even when its centre sits off the dip's centre.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from setuhq.reviewers.base import POTENTIAL_PLANET, Classification


@dataclass(frozen=True)
class Consensus:
    subject_id: str
    t_start: float
    t_end: float
    score: float
    n_reviewers: int
    reviewers: tuple[str, ...]
    planet_fraction: float
    # The marks that counted, one per reviewer: (reviewer_id, t_start, t_end).
    marks: tuple = ()

    @property
    def center(self) -> float:
        return 0.5 * (self.t_start + self.t_end)


def cluster_marks(entries, gap_days: float) -> list[list[tuple[str, float, float]]]:
    """Group ``(reviewer_id, t_start, t_end)`` entries into time clusters. Input order does not matter.

    A mark joins the current cluster when its interval overlaps the cluster's
    interval, or when its centre is within ``gap_days`` of the previous mark's centre.
    """
    ordered = sorted(entries, key=lambda e: (e[1], e[2]))
    clusters: list[list[tuple[str, float, float]]] = []
    hi = last_center = None
    for entry in ordered:
        t_start, t_end = entry[1], entry[2]
        center = 0.5 * (t_start + t_end)
        joins = hi is not None and (t_start <= hi or abs(center - last_center) <= gap_days)
        if joins:
            clusters[-1].append(entry)
            hi = max(hi, t_end)
        else:
            clusters.append([entry])
            hi = t_end
        last_center = center
    return clusters


def _one_mark_per_reviewer(cluster) -> dict[str, tuple[float, float]]:
    """Each reviewer's mark in a cluster: the one whose centre is nearest the cluster's median centre."""
    middle = median(0.5 * (a + b) for _, a, b in cluster)
    chosen: dict[str, tuple[float, float]] = {}
    for reviewer_id, t_start, t_end in cluster:
        best = chosen.get(reviewer_id)
        if best is None or abs(0.5 * (t_start + t_end) - middle) < abs(0.5 * sum(best) - middle):
            chosen[reviewer_id] = (t_start, t_end)
    return chosen


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
            first_mark = _one_mark_per_reviewer(cluster)
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
                    marks=tuple((r, a, b) for r, (a, b) in sorted(first_mark.items())),
                )
            )
    return sorted(_merge_duplicates(results, gap_days), key=lambda c: c.score, reverse=True)


def counting_rule(gap_days: float, min_score: float) -> str:
    """The rule that decides which marks count toward a consensus event, in words."""
    return (
        f"marks are taken in order of start time and a mark joins the cluster when its interval overlaps the "
        f"cluster's interval or its centre lies within {gap_days:g} d of the previous mark's centre (interval "
        f"single-linkage clustering, aggregate.py); each reviewer counts once, with the mark nearest the cluster's "
        f"median centre; a cluster whose weighted share is below {min_score:g} is dropped, and of two clusters on one "
        f"dip only the stronger is kept"
    )


def audit_marks(event: Consensus, classifications: list[Classification], gap_days: float) -> list[dict]:
    """For one event, every reviewer's marks over its window and whether each counted.

    This only reports the rule in :func:`aggregate`; it does not change it. A
    mark counts when it is the reviewer's mark in the event's cluster
    (``event.marks``). ``overlap_frac`` is the share of the consensus window
    [t_start, t_end] the mark covers. ``centre_gap_days`` is the distance from
    the mark's centre to the nearest centre of a counted mark (another one, for
    a counted mark). A mark that overlaps no counted mark and whose centre is
    more than ``gap_days`` from every counted centre fell in a separate cluster.
    """
    panel = _latest_per_reviewer([c for c in classifications if c.subject_id == event.subject_id])
    counted = {r: (a, b) for r, a, b in event.marks}
    centres = {r: 0.5 * (a + b) for r, (a, b) in counted.items()}
    width = event.t_end - event.t_start
    out = []
    for reviewer_id in sorted(panel):
        rows = []
        for m in panel[reviewer_id].marks:
            overlap = max(0.0, min(m.t_end, event.t_end) - max(m.t_start, event.t_start))
            is_counted = counted.get(reviewer_id) == (m.t_start, m.t_end)
            if overlap <= 0 and not is_counted:
                continue
            centre = 0.5 * (m.t_start + m.t_end)
            others = [c for r, c in centres.items() if not (is_counted and r == reviewer_id)]
            rows.append({
                "t_start": m.t_start,
                "t_end": m.t_end,
                "overlap_frac": overlap / width if width > 0 else None,
                "centre_gap_days": min(abs(centre - c) for c in others) if others else None,
                "counted": is_counted,
            })
        out.append({
            "reviewer_id": reviewer_id,
            "counted": reviewer_id in counted,
            # The counted mark's overlap when one counted, else the largest overlap of any mark.
            "overlap_frac": (next((r["overlap_frac"] for r in rows if r["counted"]), None) if reviewer_id in counted
                             else max((r["overlap_frac"] or 0.0 for r in rows), default=0.0)) if width > 0 else None,
            "marks": rows,
        })
    return out


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

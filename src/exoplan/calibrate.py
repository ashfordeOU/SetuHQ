"""Reviewer calibration by injection.

Each reviewer is run on synthetic subjects, half with one injected transit and
half empty. Its skill is the true-positive rate minus the false-positive rate:

    skill = TPR - FPR
    weight = max(skill, floor)

The floor keeps a weak reviewer from being silenced entirely, since its marks
still carry some information. The weights feed :func:`exoplan.aggregate.aggregate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from exoplan.injection import detrended, random_injection, synthetic_subject
from exoplan.render import render_subject
from exoplan.reviewers.base import POTENTIAL_PLANET


@dataclass(frozen=True)
class ReviewerSkill:
    reviewer_id: str
    tpr: float
    fpr: float
    weight: float
    n_injected: int
    n_empty: int


def calibrate_weights(
    reviewers,
    *,
    n_injected: int = 40,
    n_empty: int = 40,
    seed: int = 0,
    length_days: float = 13.0,
    cadence_min: float = 10.0,
    floor: float = 0.05,
    depth_ppm: tuple[float, float] = (300.0, 3000.0),
    duration_hours: tuple[float, float] = (1.0, 6.0),
    image_dir: str | Path | None = None,
) -> dict[str, ReviewerSkill]:
    """Run each reviewer on the same synthetic set and return its skill.

    Pass ``image_dir`` when a reviewer needs rendered images (the Claude reviewer does).
    """
    rng = np.random.default_rng(seed)
    injected_subjects = []
    for i in range(n_injected):
        injection = random_injection(rng, length_days, depth_ppm=depth_ppm, duration_hours=duration_hours)
        subject = synthetic_subject(
            rng,
            subject_id=f"cal-inj-{seed}-{i:04d}",
            length_days=length_days,
            cadence_min=cadence_min,
            injections=(injection,),
        )
        injected_subjects.append((detrended(subject), injection))
    empty_subjects = [
        detrended(
            synthetic_subject(rng, subject_id=f"cal-empty-{seed}-{i:04d}", length_days=length_days, cadence_min=cadence_min)
        )
        for i in range(n_empty)
    ]

    skills: dict[str, ReviewerSkill] = {}
    for reviewer in reviewers:
        hits = 0
        for subject, injection in injected_subjects:
            result = reviewer.review(subject, _render_for(subject, image_dir))
            if any(injection.hit_by(m.center) for m in result.marks):
                hits += 1
        false_alarms = 0
        for subject in empty_subjects:
            result = reviewer.review(subject, _render_for(subject, image_dir))
            if result.label == POTENTIAL_PLANET or result.marks:
                false_alarms += 1
        tpr = hits / max(1, n_injected)
        fpr = false_alarms / max(1, n_empty)
        skills[reviewer.reviewer_id] = ReviewerSkill(
            reviewer_id=reviewer.reviewer_id,
            tpr=tpr,
            fpr=fpr,
            weight=max(tpr - fpr, floor),
            n_injected=n_injected,
            n_empty=n_empty,
        )
    return skills


def _render_for(subject, image_dir: str | Path | None) -> Path | None:
    if image_dir is None:
        return None
    return render_subject(subject, Path(image_dir) / f"{subject.subject_id}.png")


def weights_from_skills(skills: dict[str, ReviewerSkill]) -> dict[str, float]:
    return {reviewer_id: skill.weight for reviewer_id, skill in skills.items()}

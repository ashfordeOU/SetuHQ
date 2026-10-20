"""Reviewer calibration by injection.

Each reviewer is run on synthetic subjects, half with one injected transit and
half empty. Its skill is the true-positive rate minus the false-positive rate:

    skill = TPR - FPR
    weight = max(skill, floor)

The floor keeps a weak reviewer from being silenced entirely, since its marks
still carry some information. The weights feed :func:`exoplan.aggregate.aggregate`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from exoplan.injection import detrended, random_injection, synthetic_subject
from exoplan.render import render_subject
from exoplan.reviewers.base import POTENTIAL_PLANET


WEIGHT_FLOOR = 0.05


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
    floor: float = WEIGHT_FLOOR,
    depth_ppm: tuple[float, float] = (300.0, 3000.0),
    duration_hours: tuple[float, float] = (1.0, 6.0),
    image_dir: str | Path | None = None,
) -> dict[str, ReviewerSkill]:
    """Run each reviewer on the same synthetic set and return its skill.

    Pass ``image_dir`` when a reviewer needs rendered images (the Sentinels do).
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


def calibration_path(weights_path: str | Path) -> Path:
    """Where the per-reviewer rates behind a weights file are kept: ``x.json`` -> ``x.calibration.json``.

    The weights file itself stays a flat ``{reviewer: weight}`` map, which ``exoplan run --weights`` reads.
    """
    p = Path(weights_path)
    return p.with_name(p.stem + ".calibration.json")


def calibration_record(skills: dict[str, ReviewerSkill], *, weights_file: str, floor: float = WEIGHT_FLOOR,
                       source: str = "", identities: dict[str, dict] | None = None) -> dict:
    """The rates and sample sizes behind a weights file, as stored next to it.

    ``identities`` (from :func:`identity`) adds each Sentinel's provider and model, so a weight is
    only ever applied to the provider and model it was measured on (:func:`apply_calibration`).
    """
    identities = identities or {}
    return {
        "weights_file": weights_file,
        "floor": floor,
        "rule": "weight = max(TPR - FPR, floor)",
        "source": source,
        "reviewers": {rid: {k: v for k, v in asdict(s).items() if k != "reviewer_id"} | identities.get(rid, {})
                      for rid, s in sorted(skills.items())},
    }


# A calibration status per reviewer, as the manifest and the pages show it.
CALIBRATED, UNCALIBRATED, UNIFORM = "calibrated", "uncalibrated", "uniform"
# What a calibration record without a stored provider was measured on: the Claude Code CLI at its default model.
LEGACY_IDENTITY = ("claude-code", "default")


def identity(reviewer) -> dict:
    """A Sentinel's provider and configured model ({} for a Probe): what a calibrated weight is tied to."""
    describe = getattr(reviewer, "describe", None)
    if describe is None:
        return {}
    d = describe()
    return {"provider": d["provider"], "model": d["model"]}


def apply_calibration(reviewers, weights: dict[str, float] | None, record: dict | None = None, *,
                      floor: float = WEIGHT_FLOOR) -> tuple[dict[str, float], dict[str, dict]]:
    """The weight each reviewer gets, and why.

    * No weights: every reviewer weighs 1.0 (status ``uniform``).
    * A reviewer with a weight, measured on the same provider and model (or on a Probe): that
      weight (``calibrated``). A record that stores no provider counts as measured on
      ``claude-code`` / ``default`` (:data:`LEGACY_IDENTITY`) and holds for that only.
    * A Sentinel with no weight, or one measured on another provider or model: the floor weight
      (``uncalibrated``). It still votes, as the weakest reviewer does, until it is calibrated.
    * A Probe with no weight keeps 1.0, as before (``uncalibrated``).

    Weights are therefore per provider and model, never per reviewer id alone.
    """
    rec = (record or {}).get("reviewers") or {}
    out_w: dict[str, float] = {}
    out_b: dict[str, dict] = {}
    for r in reviewers:
        rid = r.reviewer_id
        ident = identity(r)
        if weights is None:
            out_w[rid], out_b[rid] = 1.0, {"status": UNIFORM, "note": "no calibrated weights in use: every reviewer weighs 1.0"}
            continue
        stored = rec.get(rid) or {}
        if rid in weights:
            # A record that stores no provider predates other providers: its Sentinels were Claude through the
            # Claude Code CLI at its default model, and the weight is valid for exactly that and nothing else.
            measured = ((stored["provider"], stored.get("model")) if stored.get("provider") else LEGACY_IDENTITY)
            if ident and measured != (ident["provider"], ident["model"]):
                out_w[rid] = floor
                out_b[rid] = {"status": UNCALIBRATED, "note": f"its weight was measured on {measured[0]} / "
                              f"{measured[1]}, not {ident['provider']} / {ident['model']}: floor weight {floor}"}
            else:
                out_w[rid] = float(weights[rid])
                note = "measured by injection" if not ident or stored.get("provider") else \
                    "measured by injection; the record stores no provider, so it holds for claude-code / default only"
                out_b[rid] = {"status": CALIBRATED, "note": note}
        elif ident:
            out_w[rid] = floor
            out_b[rid] = {"status": UNCALIBRATED, "note": f"not calibrated on {ident['provider']} / {ident['model']}: floor weight {floor}"}
        else:
            out_w[rid] = 1.0
            out_b[rid] = {"status": UNCALIBRATED, "note": "not in the weights file: weight 1.0"}
    return out_w, out_b

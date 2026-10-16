"""Injection-recovery benchmark for a reviewer panel.

For each depth and duration, the benchmark injects one transit into a set of
synthetic subjects and runs the full panel, aggregation and vetting. It
reports completeness: the fraction of injected transits recovered as a vetted
candidate. It also reports false positives per subject on empty subjects.

The benchmark measures the panel and pipeline on the synthetic noise model.
It is not a claim about real light curves. Real-data performance needs a
separate benchmark against known planets.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from exoplan.config import RunConfig
from exoplan.injection import detrended, fixed_injection, synthetic_subject
from exoplan.pipeline import Candidate, build_candidates, review_subjects


@dataclass(frozen=True)
class BenchmarkRow:
    depth_ppm: float
    duration_hours: float
    n_subjects: int
    recovered: int

    @property
    def completeness(self) -> float:
        return self.recovered / self.n_subjects if self.n_subjects else float("nan")


@dataclass(frozen=True)
class BenchmarkResult:
    rows: list[BenchmarkRow]
    false_positives_per_subject: float
    n_empty: int
    panel: list[str]


def injection_recovery(
    reviewers,
    weights: dict[str, float] | None,
    config: RunConfig,
    *,
    depths_ppm=(300.0, 1000.0, 3000.0),
    durations_hours=(1.0, 2.0, 4.0),
    n_per_cell: int = 20,
    n_empty: int = 40,
    seed: int = 0,
    length_days: float = 13.0,
    cadence_min: float = 10.0,
    image_dir: str | Path | None = None,
) -> BenchmarkResult:
    weights = weights or {}
    with tempfile.TemporaryDirectory() as scratch:
        images = Path(image_dir) if image_dir is not None else Path(scratch)
        rng = np.random.default_rng(seed)

        empty = [
            detrended(
                synthetic_subject(rng, subject_id=f"bench-empty-{seed}-{i:04d}", length_days=length_days, cadence_min=cadence_min)
            )
            for i in range(n_empty)
        ]
        false_positives = sum(
            c.passed for c in _run(empty, reviewers, weights, config, images)
        )

        rows: list[BenchmarkRow] = []
        for depth in depths_ppm:
            for duration in durations_hours:
                subjects = []
                injections = []
                for i in range(n_per_cell):
                    injection = fixed_injection(length_days, depth, duration)
                    injections.append(injection)
                    subjects.append(
                        detrended(
                            synthetic_subject(
                                rng,
                                subject_id=f"bench-{int(depth)}-{int(duration * 10)}-{seed}-{i:04d}",
                                length_days=length_days,
                                cadence_min=cadence_min,
                                injections=(injection,),
                            )
                        )
                    )
                candidates = _run(subjects, reviewers, weights, config, images)
                recovered = 0
                for subject, injection in zip(subjects, injections):
                    if any(
                        c.passed and c.subject_id == subject.subject_id and injection.hit_by(c.t_center, tolerance=0.5 * injection.duration)
                        for c in candidates
                    ):
                        recovered += 1
                rows.append(BenchmarkRow(depth, duration, n_per_cell, recovered))

    return BenchmarkResult(
        rows=rows,
        false_positives_per_subject=false_positives / max(1, n_empty),
        n_empty=n_empty,
        panel=[r.reviewer_id for r in reviewers],
    )


def _run(subjects, reviewers, weights, config: RunConfig, images: Path) -> list[Candidate]:
    active = [r for r in reviewers if r.available()]
    classifications = review_subjects(subjects, active, image_dir=images)
    return build_candidates(subjects, classifications, weights, config)


def to_markdown(result: BenchmarkResult, *, title: str, weights: dict[str, float]) -> str:
    lines = [
        f"# {title}",
        "",
        f"Panel: {', '.join(result.panel)}",
        "",
        "Weights: " + ", ".join(f"{k}={v:.3f}" for k, v in sorted(weights.items())),
        "",
        "Completeness is the fraction of injected transits recovered as a vetted candidate, "
        "with the consensus centred within half a transit duration of the injection.",
        "",
        "| depth (ppm) | duration (h) | subjects | recovered | completeness |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in result.rows:
        lines.append(
            f"| {row.depth_ppm:.0f} | {row.duration_hours:.1f} | {row.n_subjects} | {row.recovered} | {row.completeness:.2f} |"
        )
    lines += [
        "",
        f"False positives: {result.false_positives_per_subject:.3f} vetted candidates per empty subject "
        f"({result.n_empty} empty subjects).",
        "",
    ]
    return "\n".join(lines)


__all__ = ["BenchmarkResult", "BenchmarkRow", "injection_recovery", "to_markdown", "build_candidates"]

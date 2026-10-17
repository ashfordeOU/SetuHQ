"""End-to-end run: light curves in, vetted candidate catalogue and provenance manifest out.

Stages, in order:

1. Clean, detrend and bin each light curve (:mod:`exoplan.preprocess`).
2. Cut into blind-coded subjects (:mod:`exoplan.subjects`) and render each as a PNG.
3. Every available reviewer classifies every subject independently.
4. Aggregate the panel into weighted consensus events (:mod:`exoplan.aggregate`).
5. Vet each consensus event (:mod:`exoplan.vet`).
6. Write candidates, classifications and a manifest that records versions and inputs.
"""

from __future__ import annotations

import csv
import json
import platform
import sys
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from exoplan import __version__
import numpy as np

from exoplan.aggregate import Consensus, aggregate, audit_marks, counting_rule
from exoplan.config import RunConfig
from exoplan.lightcurve import LightCurve
from exoplan.preprocess import bin_lightcurve, clean, detrend
from exoplan.render import render_subject
from exoplan.reviewers.base import Classification
from exoplan.reviewers.claude import PROMPT_VERSION, ReviewError
from exoplan.search import PeriodicSignal, bls_search, stitch, with_fap
from exoplan.store import Store
from exoplan.subjects import Subject, split_subjects
from exoplan.vet import VettingResult, measure_epochs, vet_event


@dataclass(frozen=True)
class Candidate:
    subject_id: str
    target: str
    mission: str
    t_start: float
    t_end: float
    time_unit: str
    score: float
    n_reviewers: int
    planet_fraction: float
    reviewers: tuple[str, ...]
    passed: bool
    flags: tuple[str, ...]
    depth_ppm: float
    snr: float
    period_days: float | None
    n_transits: int = 0
    # Empirical false-alarm probability of the periodic signal that covers this dip (search.false_alarm_probability).
    fap: float | None = None
    metrics: dict = field(default_factory=dict)
    candidate_id: str = ""
    # BLS ephemeris of the periodic signal, set only when it covers this dip.
    # Per subject by default; per target over all stitched sectors when search_scope is "sector".
    bls_t0: float | None = None
    bls_duration_days: float | None = None
    # Stored per-epoch measurements at each BLS-predicted epoch inside the subject.
    epochs: tuple = ()
    secondary_epochs: tuple = ()
    # Every reviewer's marks over the consensus window, each with its overlap
    # fraction, centre gap and whether it counted (aggregate.audit_marks), and
    # the counting rule they were judged by. Reported, not used to count.
    mark_audit: tuple = ()
    count_rule: dict = field(default_factory=dict)
    search_scope: str = "subject"

    @property
    def t_center(self) -> float:
        return 0.5 * (self.t_start + self.t_end)

    def as_row(self) -> dict:
        row = asdict(self)
        row["reviewers"] = ";".join(self.reviewers)
        row["flags"] = ";".join(self.flags)
        row["epochs"] = list(self.epochs)
        row["secondary_epochs"] = list(self.secondary_epochs)
        row["mark_audit"] = list(self.mark_audit)
        row["t_center"] = self.t_center
        row["duration_hours"] = (self.t_end - self.t_start) * 24.0
        return row


@dataclass
class RunSummary:
    run_dir: Path
    n_light_curves: int
    n_subjects: int
    n_classifications: int
    n_consensus: int
    n_passed: int
    skipped_reviewers: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)


def prepare_lightcurves(lightcurves: list[LightCurve], config: RunConfig) -> list[LightCurve]:
    """Clean, normalise, detrend and bin each light curve (each sector on its own)."""
    out = []
    for lc in lightcurves:
        cleaned = clean(lc)
        level = float(np.median(cleaned.flux)) if len(cleaned) else 1.0
        if np.isfinite(level) and level > 0:
            cleaned = cleaned.with_data(cleaned.time, cleaned.flux / level, cleaned.flux_err / level)
        detrended = detrend(cleaned, window_days=config.detrend_window_days)
        out.append(bin_lightcurve(detrended, config.bin_minutes))
    return out


def prepare_subjects(lightcurves: list[LightCurve], config: RunConfig, *, prepared: list[LightCurve] | None = None) -> list[Subject]:
    subjects: list[Subject] = []
    for binned in prepared if prepared is not None else prepare_lightcurves(lightcurves, config):
        subjects.extend(split_subjects(binned, length_days=config.subject_days, min_points=config.min_points))
    return subjects


def sector_signals(prepared: list[LightCurve], config: RunConfig) -> dict[str, PeriodicSignal | None]:
    """One BLS search per target over all its sectors stitched together, keyed by target.

    The maximum period is half the stitched time span, so a period longer than
    half a subject can be found when the sectors cover two transits.
    """
    by_target: dict[str, list[LightCurve]] = {}
    for lc in prepared:
        if len(lc):
            by_target.setdefault(lc.target, []).append(lc)
    out: dict[str, PeriodicSignal | None] = {}
    for target, curves in by_target.items():
        stitched = stitch(curves)
        signal = bls_search(stitched, min_period=config.min_period)
        out[target] = with_fap(stitched, signal, min_period=config.min_period, n_trials=config.fap_trials)
    return out


def plot_arrays(subject: Subject, points: int | None = None) -> dict:
    """Plot arrays for the dashboard and the Docket.

    By default these are the subject's own bins (``bin_minutes`` from the run
    config), with ``flux_err`` the error of each bin mean that
    :func:`exoplan.preprocess.bin_lightcurve` propagated from the same bin sums
    as the flux. Pass ``points`` to re-bin coarser; the error is then propagated
    the same way, sqrt(sum of squared errors) / n.
    """
    if points is None:
        time, flux, flux_err = subject.time, subject.flux, subject.flux_err
    else:
        edges = np.linspace(subject.start, subject.end, points + 1)
        index = np.clip(np.searchsorted(edges, subject.time, side="right") - 1, 0, points - 1)
        counts = np.bincount(index, minlength=points)
        keep = counts > 0
        time = np.bincount(index, weights=subject.time, minlength=points)[keep] / counts[keep]
        flux = np.bincount(index, weights=subject.flux, minlength=points)[keep] / counts[keep]
        flux_err = np.sqrt(np.bincount(index, weights=subject.flux_err**2, minlength=points)[keep]) / counts[keep]
    return {
        "subject_id": subject.subject_id,
        "time_unit": subject.time_unit,
        "start": subject.start,
        "end": subject.end,
        "time": [round(float(t), 5) for t in time],
        "flux": [round(float(f), 6) for f in flux],
        "flux_err": [round(float(e), 7) for e in flux_err],
    }


def review_subjects(
    subjects: list[Subject],
    reviewers,
    *,
    image_dir: str | Path | None,
    store: Store | None = None,
) -> list[Classification]:
    """Every reviewer classifies every subject. Subjects are rendered first, so every reviewer sees the same image."""
    classifications: list[Classification] = []
    for subject in subjects:
        image = None
        if image_dir is not None:
            image = render_subject(subject, Path(image_dir) / f"{subject.subject_id}.png")
            (Path(image_dir) / f"{subject.subject_id}.json").write_text(json.dumps(plot_arrays(subject)))
        if store is not None:
            store.add_subject(subject, image)
        for reviewer in reviewers:
            try:
                classification = reviewer.review(subject, image)
            except ReviewError as exc:
                warnings.warn(f"{reviewer.reviewer_id} skipped {subject.subject_id}: {exc}", stacklevel=2)
                continue
            classifications.append(classification)
            if store is not None:
                store.add_classification(classification)
    return classifications


def build_candidates(
    subjects: list[Subject],
    classifications: list[Classification],
    weights: dict[str, float],
    config: RunConfig,
    *,
    target_signals: dict[str, PeriodicSignal | None] | None = None,
) -> list[Candidate]:
    """Aggregate, search and vet. With ``target_signals`` (sector mode), each subject uses its
    target's multi-sector BLS signal instead of a search of the subject alone."""
    subject_by_id = {s.subject_id: s for s in subjects}
    consensus = aggregate(
        classifications,
        weights,
        gap_days=config.cluster_gap_days,
        min_score=config.min_score,
        min_planet_fraction=config.min_planet_fraction,
    )
    periodic_cache: dict[str, PeriodicSignal | None] = {}
    candidates: list[Candidate] = []
    for event in consensus:
        subject = subject_by_id[event.subject_id]
        if event.subject_id not in periodic_cache:
            if target_signals is not None:
                periodic_cache[event.subject_id] = target_signals.get(str(subject.provenance.get("target", "")))
            else:
                signal = bls_search(subject, min_period=config.min_period)
                periodic_cache[event.subject_id] = with_fap(subject, signal, min_period=config.min_period,
                                                            n_trials=config.fap_trials)
        result = _vet(event, subject, periodic_cache[event.subject_id])
        periodic = periodic_cache[event.subject_id]
        supported = periodic if periodic is not None and periodic.covers(event.center) else None
        candidate = _to_candidate(event, subject, result, supported)
        object.__setattr__(candidate, "search_scope", "sector" if target_signals is not None else "subject")
        object.__setattr__(candidate, "mark_audit", tuple(audit_marks(event, classifications, config.cluster_gap_days)))
        object.__setattr__(candidate, "count_rule", {
            "gap_days": config.cluster_gap_days,
            "min_score": config.min_score,
            "text": counting_rule(config.cluster_gap_days, config.min_score),
        })
        candidates.append(candidate)
    candidates.sort(key=lambda c: (not c.passed, -c.score))
    for index, candidate in enumerate(candidates):
        object.__setattr__(candidate, "candidate_id", f"{candidate.subject_id}-{index:03d}")
    return candidates


def run_pipeline(
    config: RunConfig,
    lightcurves: list[LightCurve],
    reviewers,
    out_dir: str | Path,
    *,
    weights: dict[str, float] | None = None,
    weights_source: str | None = None,
) -> RunSummary:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    active = [r for r in reviewers if r.available()]
    skipped = [r.reviewer_id for r in reviewers if not r.available()]
    if weights_source is None:
        weights_source = "supplied by caller" if weights else "uniform 1.0"
    weights = {r.reviewer_id: 1.0 for r in active} | (weights or {})

    prepared = prepare_lightcurves(lightcurves, config)
    subjects = prepare_subjects(lightcurves, config, prepared=prepared)
    target_signals = sector_signals(prepared, config) if config.search == "sector" else None
    store = Store(out / "exoplan.sqlite")
    try:
        classifications = review_subjects(subjects, active, image_dir=out / "subjects", store=store)
        candidates = build_candidates(subjects, classifications, weights, config, target_signals=target_signals)
        store.export_classifications_csv(out / "classifications.csv")
    finally:
        store.close()

    write_candidates(candidates, out)
    write_manifest(out, config, lightcurves, active, skipped, weights, subjects, classifications, candidates,
                   weights_source=weights_source)
    return RunSummary(
        run_dir=out,
        n_light_curves=len(lightcurves),
        n_subjects=len(subjects),
        n_classifications=len(classifications),
        n_consensus=len(candidates),
        n_passed=sum(c.passed for c in candidates),
        skipped_reviewers=skipped,
        candidates=candidates,
    )


def write_candidates(candidates: list[Candidate], out: Path) -> None:
    rows = [c.as_row() for c in candidates]
    fields = [
        "candidate_id", "target", "mission", "subject_id", "t_start", "t_end", "t_center", "time_unit",
        "duration_hours", "score", "n_reviewers", "planet_fraction", "reviewers", "passed", "flags",
        "depth_ppm", "snr", "period_days", "n_transits", "fap", "bls_t0", "bls_duration_days",
    ]
    with (out / "candidates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (out / "candidates.json").write_text(json.dumps(rows, indent=2, default=str))


def write_manifest(out, config, lightcurves, active, skipped, weights, subjects, classifications, candidates,
                   *, weights_source: str = "uniform 1.0") -> None:
    manifest = {
        "exoplan_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": _package_versions(["numpy", "scipy", "astropy", "matplotlib", "lightkurve", "anthropic"]),
        "config_name": config.name,
        "config_sha256": config.digest(),
        "subject_days": config.subject_days,
        # Where the periodic (BLS) search ran: each subject alone, or all sectors of a target stitched.
        "search_scope": config.search,
        "claude_prompt_version": PROMPT_VERSION,
        "inputs": [lc.provenance | {"target": lc.target, "mission": lc.mission} for lc in lightcurves],
        "reviewers": [
            {"id": r.reviewer_id, "kind": r.kind, "weight": weights.get(r.reviewer_id, 1.0)} for r in active
        ],
        "skipped_reviewers": skipped,
        # The weights used for consensus, for every reviewer the run knew about, and their source.
        "weights": {k: float(v) for k, v in sorted(weights.items())},
        "weights_source": weights_source,
        "counts": {
            "light_curves": len(lightcurves),
            "subjects": len(subjects),
            "classifications": len(classifications),
            "consensus_events": len(candidates),
            "passed_vetting": sum(c.passed for c in candidates),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))


EPHEMERIS_SNR = 10.0  # a periodic signal this strong is trusted to explain the other dips in its subject


def _vet(event: Consensus, subject: Subject, periodic: PeriodicSignal | None) -> VettingResult:
    """Vet one consensus event. A dip that does not fit a strong periodic signal is flagged, not rejected.

    A single real transit can sit beside an unrelated dip, so this flag only
    tells a reader to look twice. It does not change ``passed``.
    """
    on_ephemeris = periodic is not None and periodic.covers(event.center)
    result = vet_event(event.t_start, event.t_end, subject, periodic if on_ephemeris else None)
    if periodic is not None and periodic.snr >= EPHEMERIS_SNR and not on_ephemeris:
        return VettingResult(result.passed, result.flags + ("off_ephemeris",), result.metrics)
    return result


def _to_candidate(event: Consensus, subject: Subject, result: VettingResult, supported: PeriodicSignal | None = None) -> Candidate:
    period = result.metrics.get("period")
    epochs = measure_epochs(subject, supported) if supported is not None else ()
    secondary = measure_epochs(subject, supported, phase=0.5) if supported is not None else ()
    return Candidate(
        subject_id=event.subject_id,
        target=str(subject.provenance.get("target", "")),
        mission=subject.mission,
        t_start=event.t_start,
        t_end=event.t_end,
        time_unit=subject.time_unit,
        score=event.score,
        n_reviewers=event.n_reviewers,
        planet_fraction=event.planet_fraction,
        reviewers=event.reviewers,
        passed=result.passed,
        flags=result.flags,
        depth_ppm=float(result.metrics.get("depth", 0.0)) * 1e6,
        snr=float(result.metrics.get("snr", 0.0)),
        period_days=float(period) if period is not None else None,
        n_transits=supported.n_transits if supported is not None else 0,
        fap=supported.fap if supported is not None else None,
        bls_t0=supported.t0 if supported is not None else None,
        bls_duration_days=supported.duration if supported is not None else None,
        epochs=tuple(epochs),
        secondary_epochs=tuple(secondary),
        metrics={k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in result.metrics.items()},
    )


def _package_versions(names) -> dict[str, str]:
    found = {}
    for name in names:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return found

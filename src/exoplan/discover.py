"""Continuous discovery: run the pipeline over rotating batches of TESS targets and keep a catalogue of candidates.

Every run takes the next batch of TESS hosts in a fixed rotation, so coverage
advances steadily and a rerun on the same day gives the same batch. For each
target the two most recent sectors are reviewed. A candidate is compared with the
NASA Exoplanet Archive TOI table:

* ``known_toi``: a TOI on this TIC with a period within tolerance. Not new.
* ``new_candidate``: a passed dip that matches no known ephemeris. A candidate, not a
  confirmed planet. Confirmation needs radial velocities or independent photometry.

Candidates flagged ``off_ephemeris`` are excluded, since they are not explained by
the strong periodic signal of their own target.

The catalogue is a JSON file that accumulates across runs and is deduplicated on
(TIC, mid-time within 0.05 day).
"""

from __future__ import annotations

import json
import math
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from exoplan.config import RunConfig, build_reviewers, load_config
from exoplan.loaders import load_tess
from exoplan.pipeline import run_pipeline

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
PERIOD_TOLERANCE_DAYS = 0.05
MID_TIME_DEDUPE_DAYS = 0.05
MAX_FEED_DEPTH_PPM = 5000.0  # deeper dips are almost always binaries, so they stay out of the feed
MIN_FEED_TRANSITS = 2        # a candidate needs a periodic signal with at least two transits
MAX_FEED_FAP = 0.01          # and that signal's empirical false-alarm probability must be below this


@dataclass
class Target:
    tic: int
    toi_periods: list[float] = field(default_factory=list)
    toi_names: list[str] = field(default_factory=list)


def fetch_toi_targets() -> dict[int, Target]:
    """TOI table as a dict keyed by TIC ID. Each entry lists the known periods of that host."""
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

    table = NasaExoplanetArchive.query_criteria(table="toi", select="toi,tid,pl_orbper,tfopwg_disp")
    targets: dict[int, Target] = {}
    for row in table:
        if row["tid"] is None or np.ma.is_masked(row["tid"]):
            continue
        tic = int(row["tid"])
        target = targets.setdefault(tic, Target(tic))
        period = row["pl_orbper"]
        if period is not None and not np.ma.is_masked(period):
            target.toi_periods.append(float(getattr(period, "value", period)))
        target.toi_names.append(str(row["toi"]))
    return targets


def batch_for(targets: dict[int, Target], run_time: datetime, batch_size: int) -> list[Target]:
    """Deterministic rotation: the batch advances by one batch per day, so the whole catalogue is covered in time."""
    ordered = sorted(targets)
    if not ordered:
        return []
    days = int((run_time - EPOCH).total_seconds() // 86400)
    start = (days * batch_size) % len(ordered)
    chosen = [ordered[(start + i) % len(ordered)] for i in range(min(batch_size, len(ordered)))]
    return [targets[tic] for tic in chosen]


def classify_against_toi(candidate: dict, target: Target) -> str:
    period = candidate.get("period_days")
    if period is None or not target.toi_periods:
        return "new_candidate"
    for known in target.toi_periods:
        if abs(known - period) <= PERIOD_TOLERANCE_DAYS or abs(known - 2 * period) <= PERIOD_TOLERANCE_DAYS:
            return "known_toi"
    return "new_candidate"


def admits_fap(fap: float | None) -> bool:
    """Feed admission on the periodic signal's false-alarm probability. A signal without one is not admitted."""
    return fap is not None and fap < MAX_FEED_FAP


def load_catalog(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"candidates": [], "runs": [], "targets_reviewed": 0}


def is_duplicate(entry: dict, existing: list[dict]) -> bool:
    for other in existing:
        if other["tic"] == entry["tic"] and abs(other["t_center"] - entry["t_center"]) <= MID_TIME_DEDUPE_DAYS:
            return True
    return False


def run_discovery(
    config_path: str | Path,
    catalog_path: str | Path,
    *,
    batch_size: int = 20,
    sectors_per_target: int = 2,
    time_budget_s: float = 4.5 * 3600,
    run_time: datetime | None = None,
    work_dir: str | Path = "runs/discovery",
    cache_root: str | Path = "cache",
) -> dict:
    run_time = run_time or datetime.now(timezone.utc)
    started = time.monotonic()
    config: RunConfig = load_config(config_path)
    reviewers = build_reviewers(config.reviewers, cache_root=cache_root)
    weights_file = Path("docs/results/reviewer_weights.json")
    weights = json.loads(weights_file.read_text()) if weights_file.exists() else None

    catalog_path = Path(catalog_path)
    catalog = load_catalog(catalog_path)
    targets = fetch_toi_targets()
    batch = batch_for(targets, run_time, batch_size)

    run_log = {"time": run_time.isoformat(timespec="seconds"), "targets": [], "errors": [], "new": 0, "known": 0}
    for target in batch:
        if time.monotonic() - started > time_budget_s:
            run_log["errors"].append("time budget reached before the batch finished")
            break
        label = f"TIC {target.tic}"
        try:
            curves = load_tess(label)
            curves = sorted(curves, key=lambda c: c.provenance.get("sector", 0))[-sectors_per_target:]
            if not curves:
                run_log["errors"].append(f"{label}: no SPOC 2-minute data")
                continue
            out = Path(work_dir) / f"tic{target.tic}"
            summary = run_pipeline(config, curves, reviewers, out, weights=weights,
                                   weights_source=str(weights_file) if weights else None)
            run_log["targets"].append(target.tic)
            for candidate in summary.candidates:
                if not candidate.passed or "off_ephemeris" in candidate.flags:
                    continue
                if candidate.depth_ppm > MAX_FEED_DEPTH_PPM:
                    run_log["filtered_deep"] = run_log.get("filtered_deep", 0) + 1
                    continue
                if candidate.period_days is None or candidate.n_transits < MIN_FEED_TRANSITS:
                    run_log["filtered_single"] = run_log.get("filtered_single", 0) + 1
                    continue
                if not admits_fap(candidate.fap):
                    run_log["filtered_fap"] = run_log.get("filtered_fap", 0) + 1
                    continue
                entry = {
                    "tic": target.tic,
                    "sector_span": sorted({c.provenance.get("sector") for c in curves}),
                    "t_center": candidate.t_center,
                    "time_unit": candidate.time_unit,
                    "duration_hours": (candidate.t_end - candidate.t_start) * 24.0,
                    "depth_ppm": candidate.depth_ppm,
                    "snr": candidate.snr,
                    "score": candidate.score,
                    "n_reviewers": candidate.n_reviewers,
                    "period_days": candidate.period_days,
                    "n_transits": candidate.n_transits,
                    "fap": candidate.fap,
                    "status": classify_against_toi(
                        {"period_days": candidate.period_days}, target
                    ),
                    "candidate_id": candidate.candidate_id,
                    "found": run_time.isoformat(timespec="seconds"),
                    "status_note": "candidate only, not confirmed",
                }
                if is_duplicate(entry, catalog["candidates"]):
                    continue
                catalog["candidates"].append(entry)
                if entry["status"] == "new_candidate":
                    run_log["new"] += 1
                else:
                    run_log["known"] += 1
        except Exception as exc:  # one bad target must not stop the batch
            run_log["errors"].append(f"{label}: {type(exc).__name__}: {exc}")
            run_log.setdefault("tracebacks", []).append(traceback.format_exc(limit=2))

    catalog["targets_reviewed"] = catalog.get("targets_reviewed", 0) + len(run_log["targets"])
    catalog["runs"].append(run_log)
    catalog["runs"] = catalog["runs"][-200:]
    catalog["candidates"].sort(key=lambda c: (c["status"] != "new_candidate", -c["score"], -c["snr"]))
    catalog["updated"] = run_time.isoformat(timespec="seconds")
    catalog["config"] = config.name
    catalog["config_sha256"] = config.digest()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2, default=float))
    return run_log

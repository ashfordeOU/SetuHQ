"""Batch mode: the ``exoplan discover`` flow over many targets, cached and resumable (S4).

``exoplan discover`` reviews one rotating batch a day. ``exoplan batch`` takes any list of TIC targets and works
through it, so a target list of thousands can be spread over many sessions:

* **Resumable.** A state file (``state.json`` in the work directory) records each target's outcome: ``done``,
  ``no_data`` or ``failed`` (with the error and the number of attempts). It is rewritten atomically after every
  target, so a killed session loses at most the target in progress. A rerun skips ``done`` and ``no_data`` targets
  and retries ``failed`` ones up to ``retries`` times. The state is tied to the config's hash: a different config
  starts a fresh state file instead of mixing results.
* **Cached.** Light curves are downloaded once into ``cache/lightkurve`` (lightkurve's download directory), and the
  existing caches are used as they are: TIC parameters (``cache/tic``), FAP null maxima (``cache/fap``), reviewer
  responses (``cache/claude*``), and TPFs (``cache/tpf``) when the pixel tests are on.
* **Same rules.** Each target runs :func:`exoplan.pipeline.run_pipeline` and feeds the same feed rules as
  ``discover`` (:func:`exoplan.discover.feed_entry`); every passed candidate is also listed in
  ``batch_candidates.csv``. Throughput is measured, in targets and star-sectors per hour of wall time.
"""

from __future__ import annotations

import csv
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from exoplan.config import RunConfig, build_reviewers, load_config
from exoplan.discover import Target, feed_entry
from exoplan.pipeline import run_pipeline
from exoplan.stellar import tic_id

STATE_VERSION = 1


def read_targets(path: str | Path) -> list[int]:
    """TIC ids from a text file: one per line, as ``261136679`` or ``TIC 261136679``; ``#`` starts a comment."""
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tic = tic_id(line) if not line.isdigit() else int(line)
        if tic is None:
            raise ValueError(f"not a TIC id: {line!r}")
        out.append(tic)
    return list(dict.fromkeys(out))


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str))
    os.replace(tmp, path)


def load_state(path: Path, config: RunConfig) -> dict:
    """The batch state for this config, or a fresh one (a state made with another config is kept aside)."""
    if path.exists():
        state = json.loads(path.read_text())
        if state.get("config_sha256") == config.digest() and state.get("version") == STATE_VERSION:
            return state
        path.rename(path.with_name(f"{path.stem}.{state.get('config_sha256', 'old')[:12]}{path.suffix}"))
    return {"version": STATE_VERSION, "config": config.name, "config_sha256": config.digest(), "targets": {},
            "sessions": []}


def _default_loader(cache_root: Path):
    from exoplan.loaders import load_tess

    def load(label: str):
        return load_tess(label, download_dir=str(cache_root / "lightkurve"))
    return load


def run_batch(config_path: str | Path, targets: list[int], *, work_dir: str | Path = "runs/batch",
              cache_root: str | Path = "cache", sectors_per_target: int = 2, retries: int = 1,
              time_budget_s: float | None = None, max_targets: int | None = None, loader=None, reviewers=None,
              weights: dict | None = None, toi_targets: dict | None = None) -> dict:
    """Work through ``targets`` (TIC ids), resuming from the state file in ``work_dir``. Returns the session log.

    ``loader`` (label → list of LightCurve) and ``reviewers`` replace the defaults (MAST through lightkurve; the
    config's reviewers), which is how the tests run offline. ``toi_targets`` (TIC → Target) classifies feed entries
    as ``known_toi`` or ``new_candidate``; without it every TIC is matched against an empty TOI list.
    """
    config = load_config(config_path)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    cache_root = Path(cache_root)
    state_path = work / "state.json"
    state = load_state(state_path, config)
    loader = loader or _default_loader(cache_root)
    reviewers = reviewers if reviewers is not None else build_reviewers(config.reviewers, cache_root=cache_root)
    started, wall = datetime.now(timezone.utc), time.monotonic()
    log = {"started": started.isoformat(timespec="seconds"), "done": 0, "failed": 0, "no_data": 0, "skipped": 0,
           "star_sectors": 0, "feed": 0, "stopped": None}
    attempted = 0
    for tic in targets:
        key = str(tic)
        prior = state["targets"].get(key, {})
        if prior.get("status") in ("done", "no_data") or (prior.get("status") == "failed" and prior.get("attempts", 0) > retries):
            log["skipped"] += 1
            continue
        if max_targets is not None and attempted >= max_targets:
            log["stopped"] = f"max_targets {max_targets} reached"
            break
        if time_budget_s is not None and time.monotonic() - wall > time_budget_s:
            log["stopped"] = "time budget reached"
            break
        attempted += 1
        record = {"attempts": prior.get("attempts", 0) + 1, "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        t_start = time.monotonic()
        try:
            curves = sorted(loader(f"TIC {tic}"), key=lambda c: c.provenance.get("sector", 0))[-sectors_per_target:]
            if not curves:
                record.update(status="no_data")
                log["no_data"] += 1
            else:
                out = work / f"tic{tic}"
                summary = run_pipeline(config, curves, reviewers, out, weights=weights)
                target = (toi_targets or {}).get(tic) or Target(tic)
                run_log: dict = {}
                feed = [e for c in summary.candidates if (e := feed_entry(c, target, curves, started, run_log))]
                (out / "feed.json").write_text(json.dumps(feed, indent=1, default=float))
                record.update(status="done", run_dir=str(out), sectors=[c.provenance.get("sector") for c in curves],
                              n_candidates=len(summary.candidates), n_passed=summary.n_passed, n_feed=len(feed),
                              filtered=run_log)
                log["done"] += 1
                log["star_sectors"] += len(curves)
                log["feed"] += len(feed)
        except LookupError as exc:  # no SPOC 2-minute data for this star: final, not retried
            record.update(status="no_data", error=str(exc))
            log["no_data"] += 1
        except Exception as exc:  # noqa: BLE001 (one bad target must not stop the batch)
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(limit=3))
            log["failed"] += 1
        record["seconds"] = round(time.monotonic() - t_start, 2)
        state["targets"][key] = record
        _write_atomic(state_path, state)
    hours = max(time.monotonic() - wall, 1e-9) / 3600.0
    log.update(finished=datetime.now(timezone.utc).isoformat(timespec="seconds"), wall_hours=hours,
               targets_per_hour=log["done"] / hours, star_sectors_per_hour=log["star_sectors"] / hours,
               remaining=sum(1 for t in targets if state["targets"].get(str(t), {}).get("status") not in ("done", "no_data")))
    state["sessions"].append(log)
    _write_atomic(state_path, state)
    write_batch_candidates(work, state)
    return log


def write_batch_candidates(work: Path, state: dict) -> Path:
    """Every passed candidate of every done target, in one CSV (from each run's candidates.json)."""
    fields = ["tic", "candidate_id", "t_center", "period_days", "n_transits", "depth_ppm", "snr", "fap_label", "flags",
              "validation_label", "run_dir"]
    path = work / "batch_candidates.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for key, record in sorted(state["targets"].items()):
            if record.get("status") != "done":
                continue
            rows = json.loads((Path(record["run_dir"]) / "candidates.json").read_text())
            for r in rows:
                if r.get("passed"):
                    writer.writerow({**r, "tic": key, "run_dir": record["run_dir"],
                                     "validation_label": ((r.get("metrics") or {}).get("validation") or {}).get("label", "")})
    return path

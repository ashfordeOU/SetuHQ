# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Continuous discovery: run the pipeline over rotating batches of TESS targets and keep a catalogue of candidates.

Every run takes the next batch of TESS hosts in a fixed rotation, so coverage
advances steadily and a rerun on the same day gives the same batch. For each
target the two most recent sectors are reviewed. A candidate is compared with the
NASA Exoplanet Archive TOI table:

* ``known_toi``: the dip falls on a predicted transit of a TOI on this TIC
  (:func:`match_toi`). The matched TOI and the timing offset are stored. Not new.
* ``new_candidate``: a passed dip that matches no known ephemeris. A candidate, not a
  confirmed planet. Confirmation needs radial velocities or independent photometry.

A dip enters the feed only when it passed vetting, is on its own target's
periodic signal, is shallower than 5000 ppm, that periodic signal has at
least two transits and an empirical false-alarm probability below 0.001, and the
same signal (period within 0.5%) also reaches these parts of the rule in the other
reviewed sector. With the discovery config's 2,000 block-bootstrap trials,
FAP = (k + 1)/2001, so the rule passes at k ≤ 1 of 2,000 trials; the trials stop once
2 reach the signal's SNR. The two-sector part was added after the real-TOI benchmark
showed noise passing the earlier rule (FAP < 0.01 over 200 trials, one sector) about as
often as the feed reported new signals.

Candidates flagged ``off_ephemeris`` are excluded, since they are not explained by
the strong periodic signal of their own target.

The catalogue is a JSON file that accumulates across runs and is deduplicated on
(TIC, mid-time within 0.05 day).

Embargo (on by default). The catalogue ``setuhq discover`` writes is public: the scheduled workflow commits it
and deploys the site built from it. So any entry whose status is not ``known_toi`` is withheld from it
(:func:`embargo_catalog`): no TIC, coordinates, period, epoch, depth or any other field is written, logged or
printed, not even a count or a date: every public output (the catalogue, its run log, the site, the
command's output) is byte for byte what it would be had the signal not been found. Counts of held signals
live only in the private review pipeline (setuhq-ops). A withheld signal is not persisted
anywhere public; the search is deterministic and
reproducible from the data, the config and the code, so a private review pipeline re-searches those targets
itself and reports a signal before it is published. Only a private deployment opts out, with ``--publish-new``
or ``embargo = false`` under ``[discover]`` in its config; the public workflow sets neither. Every page that
reads the catalogue goes through :func:`public_catalog`, which applies the same rule again unless the catalogue
says ``"embargo": false``.
"""

from __future__ import annotations

from setuhq.i18n import N_

import json
import math
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from setuhq.config import RunConfig, build_reviewers, load_config
from setuhq.ephemeris import propagate
from setuhq.loaders import load_tess
from setuhq.pipeline import run_pipeline

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
PERIOD_TOLERANCE_DAYS = 0.05  # period-only fallback, for a TOI without a transit midtime
PERIOD_MATCH_FRACTION = 0.01  # candidate period within 1 percent of P or 2P
MIN_EPOCH_TOLERANCE_HOURS = 1.0
BTJD_OFFSET = 2457000.0
MID_TIME_DEDUPE_DAYS = 0.05
MAX_FEED_DEPTH_PPM = 5000.0  # deeper dips are almost always binaries, so they stay out of the feed
MIN_FEED_TRANSITS = 2        # a candidate needs a periodic signal with at least two transits
MAX_FEED_FAP = 0.001         # and that signal's empirical FAP must be below this (k ≤ 1 of 2,000 trials)
# The signal must also reach the rule's other parts in both reviewed sectors, with periods within this fraction.
# Chosen on the real-TOI benchmark's tuning half only and pre-registered (docs/results/feed_rule_preregistration.json,
# commit 8909cda) before its one held-out evaluation (docs/results/feed_rule_validation.json).
TWO_SECTOR_PERIOD_TOL = 0.005
PUBLIC_STATUS = "known_toi"  # under the embargo, the only status the public catalogue and site carry


@dataclass
class Toi:
    """One TOI's published ephemeris. ``tranmid`` is BJD (TDB); errors are 1 sigma; None when not published."""

    name: str
    period: float | None = None
    tranmid: float | None = None
    period_err: float | None = None
    tranmid_err: float | None = None
    duration_hours: float | None = None
    disposition: str | None = None


@dataclass
class Target:
    tic: int
    toi_periods: list[float] = field(default_factory=list)
    toi_names: list[str] = field(default_factory=list)
    tois: list[Toi] = field(default_factory=list)


def _value(row, key):
    try:
        value = row[key]
    except (KeyError, IndexError):
        return None
    if value is None or np.ma.is_masked(value):
        return None
    value = getattr(value, "value", value)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def fetch_toi_targets() -> dict[int, Target]:
    """TOI table as a dict keyed by TIC ID. Each entry lists the TOIs of that host with their ephemerides."""
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

    table = NasaExoplanetArchive.query_criteria(
        table="toi",
        select="toi,tid,pl_orbper,pl_orbpererr1,pl_tranmid,pl_tranmiderr1,pl_trandurh,tfopwg_disp",
    )
    targets: dict[int, Target] = {}
    for row in table:
        if row["tid"] is None or np.ma.is_masked(row["tid"]):
            continue
        tic = int(row["tid"])
        target = targets.setdefault(tic, Target(tic))
        toi = Toi(
            name=str(row["toi"]),
            period=_value(row, "pl_orbper"),
            tranmid=_value(row, "pl_tranmid"),
            period_err=_value(row, "pl_orbpererr1"),
            tranmid_err=_value(row, "pl_tranmiderr1"),
            duration_hours=_value(row, "pl_trandurh"),
            disposition=None if np.ma.is_masked(row["tfopwg_disp"]) else str(row["tfopwg_disp"]),
        )
        target.tois.append(toi)
        if toi.period is not None:
            target.toi_periods.append(toi.period)
        target.toi_names.append(toi.name)
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


def match_toi(candidate: dict, target: Target) -> dict | None:
    """The TOI whose ephemeris explains this dip, or None.

    ``candidate`` needs ``t_center`` (BTJD, or BJD when ``time_unit`` is not
    "BTJD"), ``duration_hours`` and ``period_days`` (may be None). For each
    TOI with a period and a transit midtime, the nearest predicted epoch
    T0 + n P is found and the offset of the dip's mid-time from it measured.
    The ephemeris uncertainty propagated to that epoch, sqrt(sT0^2 + (n sP)^2),
    is added at 3 sigma to each tolerance below. A dip matches when either

    * the offset is within max(1 h, half the dip's duration, half the TOI's
      published duration): the dip lies inside a predicted transit; or
    * the dip's BLS period is within 1 percent of P or 2P and the offset is
      within max(1 h, the dip's duration, the TOI's duration).

    The half-TOI-duration term matters: a box fit can catch only part of a
    long transit, and its mid-time then sits off the published mid-time
    (TOI-2669.01 at BTJD 3711.33 is 1.9 h off a 5.7 h transit). A TOI with a
    period but no midtime matches on period alone (P or 2P within 0.05 d),
    and the offset is then None. Of several matches the smallest offset wins.
    """
    t = candidate.get("t_center")
    if t is None:
        return None
    t_bjd = float(t) + (BTJD_OFFSET if candidate.get("time_unit", "BTJD") == "BTJD" else 0.0)
    dur_h = float(candidate.get("duration_hours") or 0.0)
    period = candidate.get("period_days")
    tois = target.tois or [Toi(name=n, period=p) for n, p in zip(target.toi_names, target.toi_periods)]
    best = None
    for toi in tois:
        if toi.period is None or toi.period <= 0:
            continue
        period_ok = period is not None and any(
            abs(period - k * toi.period) <= PERIOD_MATCH_FRACTION * k * toi.period for k in (1, 2))
        if toi.tranmid is None:
            close = period is not None and any(
                abs(k * toi.period - period) <= PERIOD_TOLERANCE_DAYS for k in (1, 2))
            if close and best is None:
                best = {"toi": toi.name, "offset_hours": None, "rule": "period only (no published midtime)"}
            continue
        n = round((t_bjd - toi.tranmid) / toi.period)
        predicted, sigma = propagate(toi.tranmid, toi.tranmid_err, toi.period, toi.period_err, n)
        offset_h = (t_bjd - predicted) * 24.0
        sigma_h = 24.0 * sigma
        toi_dur = toi.duration_hours or 0.0
        in_transit = max(MIN_EPOCH_TOLERANCE_HOURS, 0.5 * dur_h, 0.5 * toi_dur) + 3.0 * sigma_h
        with_period = max(MIN_EPOCH_TOLERANCE_HOURS, dur_h, toi_dur) + 3.0 * sigma_h
        rule = None
        if abs(offset_h) <= in_transit:
            rule = "mid-time on a predicted transit"
        elif period_ok and abs(offset_h) <= with_period:
            rule = "period and mid-time match"
        if rule and (best is None or best["offset_hours"] is None or abs(offset_h) < abs(best["offset_hours"])):
            best = {"toi": toi.name, "offset_hours": offset_h, "rule": rule, "epoch": int(n),
                    "ephemeris_sigma_hours": sigma_h, "disposition": toi.disposition}
    return best


def classify_against_toi(candidate: dict, target: Target) -> str:
    return "known_toi" if match_toi(candidate, target) else "new_candidate"


def toi_fields(candidate: dict, target: Target) -> dict:
    """Status plus the matched TOI and offset, as stored on a feed entry."""
    match = match_toi(candidate, target)
    return {
        "status": "known_toi" if match else "new_candidate",
        "toi_match": match["toi"] if match else None,
        "toi_offset_hours": match["offset_hours"] if match else None,
        "toi_match_rule": match["rule"] if match else None,
    }


def reclassify_catalog(catalog: dict, targets: dict[int, Target]) -> int:
    """Re-match every stored entry against the TOI ephemerides. Returns how many statuses changed."""
    changed = 0
    for entry in catalog.get("candidates", []):
        target = targets.get(int(entry["tic"]))
        if target is None:
            continue
        fields = toi_fields(entry, target)
        if fields["status"] != entry.get("status"):
            changed += 1
        entry.update(fields)
    return changed


def admits_fap(fap: float | None) -> bool:
    """Feed admission on the periodic signal's false-alarm probability. A signal without one is not admitted."""
    return fap is not None and fap < MAX_FEED_FAP


def feed_eligible(c) -> bool:
    """The feed rule before its FAP and two-sector parts: passed vetting, on its own periodic signal, at most
    MAX_FEED_DEPTH_PPM deep, at least MIN_FEED_TRANSITS transits. ``c`` is a Candidate or its row dict."""
    get = (lambda k: c.get(k)) if isinstance(c, dict) else (lambda k: getattr(c, k))
    flags = get("flags") or ()
    flags = flags.split(";") if isinstance(flags, str) else flags
    return (bool(get("passed")) and "off_ephemeris" not in flags and (get("depth_ppm") or 0) <= MAX_FEED_DEPTH_PPM
            and get("period_days") is not None and (get("n_transits") or 0) >= MIN_FEED_TRANSITS)


def two_sector_partner(c, candidates, tol: float = TWO_SECTOR_PERIOD_TOL):
    """A feed-eligible dip in another reviewed sector whose signal has the same period within ``tol``, or None."""
    get = lambda x, k: x.get(k) if isinstance(x, dict) else getattr(x, k)
    for r in candidates:
        if r is c or get(r, "sector") == get(c, "sector") or not feed_eligible(r):
            continue
        if abs(get(r, "period_days") - get(c, "period_days")) <= tol * get(c, "period_days"):
            return r
    return None


def feed_entry(candidate, target: Target, curves, run_time: datetime, run_log: dict, candidates=()) -> dict | None:
    """The feed entry for one candidate of a reviewed target, or None when the feed rules (module docstring) leave
    it out; the reason is counted in ``run_log``. ``candidates`` are all the target's candidates, for the two-sector
    part of the rule. Shared by ``setuhq discover`` and ``setuhq batch``."""
    if not candidate.passed or "off_ephemeris" in candidate.flags:
        return None
    if candidate.depth_ppm > MAX_FEED_DEPTH_PPM:
        run_log["filtered_deep"] = run_log.get("filtered_deep", 0) + 1
        return None
    if candidate.period_days is None or candidate.n_transits < MIN_FEED_TRANSITS:
        run_log["filtered_single"] = run_log.get("filtered_single", 0) + 1
        return None
    if not admits_fap(candidate.fap):
        run_log["filtered_fap"] = run_log.get("filtered_fap", 0) + 1
        return None
    if two_sector_partner(candidate, candidates) is None:
        run_log["filtered_one_sector"] = run_log.get("filtered_one_sector", 0) + 1
        return None
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
        "candidate_id": candidate.candidate_id,
        "found": run_time.isoformat(timespec="seconds"),
        "status_note": "candidate only, not confirmed",
    }
    entry.update(toi_fields(entry, target))
    return entry


HELD_LINE = N_("honesty.embargo", "Signals that match no known TOI are held for private review; "
               "they are published only after review and reporting.",
               note="The feed embargo line. Static: never add a number, a count or a date in any language.")


def held_line() -> str:
    """The one plain line the site shows wherever the feed is summarised. Static: no number, no date, nothing
    that changes when a signal is held."""
    return HELD_LINE


def embargo_catalog(catalog: dict, run_time: datetime | None = None) -> int:
    """Withhold every entry that is not ``known_toi`` from ``catalog`` (in place); returns how many were withheld
    (for the caller only: it is never stored, printed or logged).

    Rule: the catalogue written under the embargo is identical, byte for byte, to the one a run that found no
    such signal would write. So no count, date or flag of a hold is stored, and run logs keep a count of their
    targets (``n_targets``) in place of their TIC list. Counts of held signals belong to the private review
    pipeline (setuhq-ops), which re-searches the targets itself."""
    kept = [e for e in catalog.get("candidates", []) if e.get("status") == PUBLIC_STATUS]
    held = len(catalog.get("candidates", [])) - len(kept)
    catalog["candidates"] = kept
    for run in catalog.get("runs", []):
        if "targets" in run:
            run["n_targets"] = len(run.pop("targets") or [])
    for key in ("held_for_review", "held_last_date", "held_on_last_date"):  # from an earlier build: not public
        catalog.pop(key, None)
    catalog["embargo"] = True
    return held


def public_catalog(catalog: dict) -> dict:
    """The catalogue as a public page may show it: entries that are not ``known_toi`` are dropped, unless the
    catalogue was written by a private deployment that opted out (``"embargo": false``). Pages call this on
    every catalogue they read, so a catalogue that still holds such an entry never reaches the site. Run logs are
    shown with a count of targets, not their TICs, as :func:`embargo_catalog` stores them."""
    if catalog.get("embargo") is False:
        return catalog
    rows = catalog.get("candidates") or []
    kept = [e for e in rows if e.get("status") == PUBLIC_STATUS]
    runs = [{**{k: v for k, v in r.items() if k != "targets"}, "n_targets": r.get("n_targets", len(r.get("targets") or []))}
            for r in catalog.get("runs") or []]
    return {**{k: v for k, v in catalog.items() if not k.startswith("held_")}, "candidates": kept, "runs": runs}


def load_public_catalog(path: str | Path) -> dict:
    """Read a catalogue for a public page (:func:`public_catalog`)."""
    return public_catalog(json.loads(Path(path).read_text()))


def embargo_setting(config: RunConfig, publish_new: bool = False) -> bool:
    """True (withhold new signals) unless the CLI passed ``--publish-new`` or the config sets
    ``[discover] embargo = false``. Anything else, including a missing setting, keeps the embargo on."""
    if publish_new:
        return False
    return (config.raw.get("discover") or {}).get("embargo", True) is not False


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
    tics: list[int] | None = None,
    publish_new: bool = False,
) -> dict:
    """One discovery batch into ``catalog_path``. The embargo (module docstring) is on unless ``publish_new`` or
    the config's ``[discover] embargo = false`` turns it off. Under the embargo the returned run log, like the
    stored one, is what it would be had no withheld signal been found."""
    run_time = run_time or datetime.now(timezone.utc)
    started = time.monotonic()
    config: RunConfig = load_config(config_path)
    embargo = embargo_setting(config, publish_new)
    reviewers = build_reviewers(config.reviewers, cache_root=cache_root)
    weights_file = Path("docs/results/reviewer_weights.json")
    weights = json.loads(weights_file.read_text()) if weights_file.exists() else None

    catalog_path = Path(catalog_path)
    catalog = load_catalog(catalog_path)
    targets = fetch_toi_targets()
    # A named list of TIC ids (a re-run of earlier targets) instead of the day's rotation.
    batch = [targets[t] for t in tics if t in targets] if tics else batch_for(targets, run_time, batch_size)

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
                entry = feed_entry(candidate, target, curves, run_time, run_log, summary.candidates)
                if entry is None:
                    continue
                if is_duplicate(entry, catalog["candidates"]):
                    continue
                catalog["candidates"].append(entry)
                if entry["status"] == "new_candidate":
                    run_log["new"] += 1
                else:
                    run_log["known"] += 1
        except Exception as exc:  # one bad target must not stop the batch
            # Recorded the same way whether or not the target gave a withheld signal (type, message, frames: never
            # the entry), so an error record does not mark a target that gave one.
            run_log["errors"].append(f"{label}: {type(exc).__name__}: {exc}")
            run_log.setdefault("tracebacks", []).append(traceback.format_exc(limit=2))

    run_log["reclassified"] = reclassify_catalog(catalog, targets)
    catalog["targets_reviewed"] = catalog.get("targets_reviewed", 0) + len(run_log["targets"])
    catalog["runs"].append(run_log)
    if embargo:
        # Withheld before anything is written: the catalogue, the run log and the site built from them are public.
        run_log.pop("new", None)
        embargo_catalog(catalog, run_time)
    else:
        catalog["embargo"] = False
    catalog["runs"] = catalog["runs"][-200:]
    catalog["candidates"].sort(key=lambda c: (c["status"] != "new_candidate", -c["score"], -c["snr"]))
    catalog["updated"] = run_time.isoformat(timespec="seconds")
    catalog["config"] = config.name
    catalog["config_sha256"] = config.digest()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps(catalog, indent=2, default=float))
    return run_log

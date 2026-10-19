"""The all-sky sweep: work through a TESS sector's SPOC 2-minute targets, resumably, and keep what was searched.

    exoplan sweep configs/sweep.toml --sector 1 --limit 200 --workers 3

* **Targets.** The sector's SPOC 2-minute light curves, from one MAST query, cached as
  ``cache/sweep/targets/s0001.json``. They are taken in a fixed pseudo-random order, the sha256 of
  ``"<sector>:<tic>"``, so a slice of N targets is a fair sample of the sector, and ``--limit`` grows it.
* **Polite to MAST.** One request at a time from this process, at least ``--min-interval`` seconds apart
  (1 s by default), with exponential back-off on errors and rate limits (``polite``). Light-curve files are
  cached under ``cache/mast/sweep/`` and never fetched twice.
* **Resumable.** Each finished star-sector is written to ``cache/sweep/s0001/tic<id>.json`` as soon as it is
  done (write, then rename). A rerun skips every star-sector with a stored record and retries errors, so an
  interrupted sweep (a time budget, a crash, Ctrl-C) loses at most the stars in flight.
* **Coverage.** Every star-sector is recorded, searched or not: what was searched (file sha256, points,
  subjects, reviewers), what was found (catalogue entries by class), and what was rejected (marks below
  consensus, dips failing vetting, dips that are not planet candidates). The sector's record is
  ``<out>/sector_0001.json``; :func:`build_catalogue` merges every sector record and every ingested
  contribution into ``<out>/catalogue.json``, which the site reads.

The sweep's output is its own catalogue. It is separate from the discovery feed (``docs/discoveries``) and
nothing in it is a new planet: a planet candidate here is a light-curve classification, unconfirmed.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from exoplan.variables import CLASS_IDS, CLASSES, CONFIDENCE, RULES

SWEEP_DIR = "docs/sweep"
FORMAT = "exoplan-sweep/1"
CATALOGUE_FORMAT = "exoplan-everything-that-dims/1"


# ---------- politeness ----------
@dataclass
class Throttle:
    """At most one request per ``min_interval`` seconds from this process."""

    min_interval: float = 1.0
    clock: callable = time.monotonic
    sleep: callable = time.sleep
    last: float | None = None
    waited: float = 0.0

    def wait(self) -> None:
        now = self.clock()
        if self.last is not None and now - self.last < self.min_interval:
            pause = self.min_interval - (now - self.last)
            self.sleep(pause)
            self.waited += pause
        self.last = self.clock()


RETRYABLE = ("429", "500", "502", "503", "504", "timed out", "timeout", "temporarily", "connection", "reset", "too many")


def polite(fn, *args, throttle: Throttle, tries: int = 5, base_delay: float = 2.0, sleep=time.sleep, **kwargs):
    """Call ``fn`` after the throttle; on a rate limit, a server error or a network error, back off
    (``base_delay`` × 2^attempt seconds, with up to 25% jitter) and try again, ``tries`` times in all."""
    for attempt in range(tries):
        throttle.wait()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 (classified below)
            text = f"{type(exc).__name__} {exc}".lower()
            if attempt == tries - 1 or not any(k in text for k in RETRYABLE):
                raise
            sleep(base_delay * (2 ** attempt) * (1 + 0.25 * random.random()))
    raise RuntimeError("unreachable")


# ---------- targets ----------
def mast_targets(sector: int) -> list[dict]:
    """The sector's SPOC 2-minute light curves from MAST: TIC, position and the product URI."""
    from astroquery.mast import Observations

    rows = Observations.query_criteria(obs_collection="TESS", provenance_name="SPOC", sequence_number=int(sector),
                                       dataproduct_type="timeseries", t_exptime=120)
    out = []
    for r in rows:
        try:
            tic = int(str(r["target_name"]).strip())
        except ValueError:
            continue
        out.append({"tic": tic, "ra": float(r["s_ra"]), "dec": float(r["s_dec"]), "uri": str(r["dataURL"]), "obs_id": str(r["obs_id"])})
    return out


def sweep_key(sector: int, tic: int) -> str:
    return hashlib.sha256(f"{int(sector)}:{int(tic)}".encode()).hexdigest()


def sector_targets(sector: int, cache_root: str | Path = "cache", *, throttle: Throttle | None = None, query=None,
                   refresh: bool = False) -> tuple[list[dict], str]:
    """The sector's targets in sweep order, and when the list was fetched. Cached; ``query`` replaces the MAST
    call (tests)."""
    path = Path(cache_root) / "sweep" / "targets" / f"s{int(sector):04d}.json"
    if refresh or not path.exists():
        rows = polite(query or mast_targets, int(sector), throttle=throttle or Throttle())
        seen, uniq = set(), []
        for r in rows:
            if r["tic"] not in seen:
                seen.add(r["tic"])
                uniq.append(r)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"sector": int(sector), "fetched_at": _now(), "targets": uniq}, separators=(",", ":")))
    data = json.loads(path.read_text())
    return sorted(data["targets"], key=lambda r: sweep_key(sector, r["tic"])), data["fetched_at"]


def target_list_sha256(targets: list[dict]) -> str:
    return hashlib.sha256(",".join(str(t["tic"]) for t in targets).encode()).hexdigest()


def mast_download(uri: str, local: Path) -> None:
    from astroquery.mast import Observations

    status, msg, _ = Observations.download_file(uri, local_path=str(local))
    if status != "COMPLETE":
        raise OSError(f"download {status}: {msg}")


def fetch_file(target: dict, sector: int, cache_root: str | Path, *, throttle: Throttle, fetch=None) -> Path:
    """The target's light-curve file, from the cache when present, else from MAST (politely)."""
    name = target["uri"].rsplit("/", 1)[-1]
    local = Path(cache_root) / "mast" / "sweep" / f"s{int(sector):04d}" / name
    if local.exists() and local.stat().st_size > 0:
        return local
    local.parent.mkdir(parents=True, exist_ok=True)
    part = local.with_suffix(local.suffix + ".part")
    polite(fetch or mast_download, target["uri"], part, throttle=throttle)
    os.replace(part, local)
    return local


# ---------- one star (runs in a worker process) ----------
_WORKER: dict = {}


def _setup(config_path: str, cache_root: str, weights_path: str | None, toi_path: str | None) -> None:
    from exoplan.config import build_reviewers, load_config
    from exoplan.starsearch import code_fingerprint, panel_weights

    config = load_config(config_path)
    reviewers = [r for r in build_reviewers(config.reviewers, cache_root=cache_root)]
    weights, source = panel_weights(config, weights_path)
    _WORKER.update(config=config, reviewers=reviewers, weights=weights, source=source, code=code_fingerprint(),
                   tois=_toi_index(toi_path))


def _toi_index(path: str | None) -> dict:
    """TIC → discover.Target with its TOIs, from the cached TOI table (no network); {} when there is none."""
    if not path or not Path(path).exists():
        return {}
    import csv

    from exoplan.discover import Target, Toi

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    out: dict[int, Target] = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                tic = int(float(r["tid"]))
            except (TypeError, ValueError, KeyError):
                continue
            t = out.setdefault(tic, Target(tic))
            t.tois.append(Toi(name=str(r.get("toi")), period=num(r.get("pl_orbper")), tranmid=num(r.get("pl_tranmid")),
                              period_err=num(r.get("pl_orbpererr1")), tranmid_err=num(r.get("pl_tranmiderr1")),
                              duration_hours=num(r.get("pl_trandurh")), disposition=r.get("tfopwg_disp") or None))
    return out


def _search(job: dict) -> dict:
    from exoplan.starsearch import search_star

    w = _WORKER
    try:
        return search_star(job["path"], tic=job["tic"], sector=job["sector"], config=w["config"], reviewers=w["reviewers"],
                           weights=w["weights"], weights_source=w["source"], run_root=job["run_root"],
                           toi_target=w["tois"].get(job["tic"]), control=job["control"], code=w["code"])
    except Exception as exc:  # noqa: BLE001 (one star must not stop the sweep; recorded and retried next run)
        return {"tic": job["tic"], "sector": job["sector"], "status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "traceback": traceback.format_exc(limit=3)[-1500:], "searched_at": _now()}


# ---------- the sweep ----------
@dataclass
class SweepResult:
    sector: int
    done: int = 0                 # star-sectors with a stored record (this run and earlier ones)
    ran: int = 0                  # star-sectors searched in this run
    skipped: int = 0              # star-sectors skipped because a record was stored already
    errors: list = field(default_factory=list)
    stopped: str = ""
    record_path: Path | None = None


def record_path(cache_root, sector: int, tic: int) -> Path:
    return Path(cache_root) / "sweep" / f"s{int(sector):04d}" / f"tic{int(tic)}.json"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def run_sweep(config_path: str | Path, sector: int, *, limit: int, out_dir: str | Path = SWEEP_DIR, cache_root: str | Path = "cache",
              workers: int = 1, min_interval: float = 1.0, time_budget_s: float | None = None, control: bool = True,
              contributor: str = "exoplan", weights_path: str | None = "docs/results/reviewer_weights_full_panel.json",
              toi_path: str | None = None, query=None, fetch=None, log=print) -> SweepResult:
    """Search the first ``limit`` targets of the sector in sweep order, skipping those already done, then write
    the sector record and rebuild the catalogue. ``query`` and ``fetch`` replace the MAST calls (tests)."""
    started = time.monotonic()
    cache_root = Path(cache_root)
    toi_path = toi_path or str(cache_root / "toi" / "toi.csv")
    throttle = Throttle(min_interval)
    targets, fetched_at = sector_targets(sector, cache_root, throttle=throttle, query=query)
    chosen = targets[:limit]
    res = SweepResult(sector=int(sector))
    todo = []
    for t in chosen:
        p = record_path(cache_root, sector, t["tic"])
        if p.exists() and json.loads(p.read_text()).get("status") in ("searched", "no_data"):
            res.skipped += 1
        else:
            todo.append(t)
    log(f"sector {sector}: {len(targets)} SPOC 2-minute targets; slice {len(chosen)}; {res.skipped} already done; {len(todo)} to search")
    run_root = cache_root / "sweep" / "runs"
    common = (str(config_path), str(cache_root), weights_path, toi_path)

    def store(rec: dict) -> None:
        tgt = next(t for t in chosen if t["tic"] == rec["tic"])
        rec.setdefault("ra", tgt["ra"])
        if rec.get("ra") is None:
            rec["ra"] = tgt["ra"]
        if rec.get("dec") is None:
            rec["dec"] = tgt["dec"]
        _write_atomic(record_path(cache_root, sector, rec["tic"]), json.dumps(finite(rec), default=_json_default))
        res.ran += 1
        if rec["status"] == "error":
            res.errors.append(f"TIC {rec['tic']}: {rec['error']}")
        log(f"  TIC {rec['tic']}: {rec['status']}" + (f", {rec.get('n_dips', 0)} dips, {len(rec.get('entries', []))} entries, {rec.get('elapsed_s')} s"
                                                     if rec["status"] == "searched" else f" ({rec.get('error', '')})"))

    def job_for(t: dict) -> dict | None:
        try:
            path = fetch_file(t, sector, cache_root, throttle=throttle, fetch=fetch)
        except Exception as exc:  # noqa: BLE001
            store({"tic": t["tic"], "sector": int(sector), "status": "error", "error": f"download failed: {type(exc).__name__}: {str(exc)[:200]}",
                   "searched_at": _now()})
            return None
        return {"path": str(path), "tic": t["tic"], "sector": int(sector), "run_root": str(run_root), "control": control}

    def over_budget() -> bool:
        return time_budget_s is not None and time.monotonic() - started > time_budget_s

    if workers <= 1:
        _setup(*common)
        for t in todo:
            if over_budget():
                res.stopped = "time budget reached"
                break
            job = job_for(t)
            if job:
                store(_search(job))
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_setup, initargs=common) as pool:
            pending, queue = set(), list(todo)
            while queue or pending:
                while queue and len(pending) < 2 * workers and not over_budget():
                    job = job_for(queue.pop(0))
                    if job:
                        pending.add(pool.submit(_search, job))
                if over_budget() and queue:
                    res.stopped = "time budget reached"
                    queue.clear()
                if not pending:
                    continue
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for f in done:
                    store(f.result())
    res.done = sum(1 for t in chosen if record_path(cache_root, sector, t["tic"]).exists())
    res.record_path = write_sector_record(config_path, sector, chosen, targets, fetched_at, out_dir=out_dir, cache_root=cache_root,
                                          contributor=contributor, limit=limit, min_interval=min_interval)
    build_catalogue(out_dir)
    return res


def write_sector_record(config_path, sector: int, chosen: list[dict], targets: list[dict], fetched_at: str, *, out_dir, cache_root,
                        contributor: str, limit: int, min_interval: float) -> Path:
    """The sector's record: every star-sector of the slice with its stored result (or "pending")."""
    from exoplan.config import load_config
    from exoplan.starsearch import code_fingerprint

    config = load_config(config_path)
    stars = []
    for t in chosen:
        p = record_path(cache_root, sector, t["tic"])
        if p.exists():
            rec = json.loads(p.read_text())
            rec.pop("traceback", None)
        else:
            rec = {"tic": t["tic"], "sector": int(sector), "status": "pending", "ra": t["ra"], "dec": t["dec"]}
        stars.append(rec)
    codes = sorted({s.get("code") for s in stars if s.get("code")})
    record = {
        "format": FORMAT, "sector": int(sector), "generated_at": _now(), "contributor": contributor,
        "config_name": config.name, "config_file": Path(config_path).name, "config_sha256": config.digest(),
        "config_text": Path(config_path).read_text(), "code": codes[0] if len(codes) == 1 else codes,
        "code_now": code_fingerprint(),
        "targets_in_sector": len(targets), "targets_fetched_at": fetched_at, "target_list_sha256": target_list_sha256(targets),
        "order": "sha256 of '<sector>:<tic>', ascending (a fixed pseudo-random order: a slice is a fair sample)",
        "limit": int(limit), "slice": len(chosen), "min_interval_s": min_interval,
        "status_counts": {s: sum(1 for x in stars if x.get("status") == s) for s in ("searched", "no_data", "error", "pending")},
        "stars": stars,
    }
    path = Path(out_dir) / f"sector_{int(sector):04d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(finite(record), separators=(",", ":"), default=_json_default, allow_nan=False) + "\n")
    return path


# ---------- the catalogue: every sector record and every contribution ----------
def load_sources(sweep_dir: str | Path = SWEEP_DIR) -> list[dict]:
    """Every source of sweep results: the in-repo sector records, then each ingested contribution, with the
    name to credit."""
    sweep_dir = Path(sweep_dir)
    out = []
    for p in sorted(sweep_dir.glob("sector_*.json")):
        rec = json.loads(p.read_text())
        out.append({"name": rec.get("contributor") or "exoplan", "source": str(p.name), "bundle": None, "record": rec})
    for m in sorted((sweep_dir / "contributions").glob("*/manifest.json")):
        man = json.loads(m.read_text())
        rec = json.loads((m.parent / "results.json").read_text())
        out.append({"name": man["contributor"]["name"], "source": f"contributions/{m.parent.name}", "bundle": man["bundle_id"], "record": rec})
    return out


def build_catalogue(sweep_dir: str | Path = SWEEP_DIR) -> Path | None:
    """Merge every source into ``catalogue.json``: entries with credit, one coverage row per star-sector, and
    the counts the site shows. An entry found by two sources with the same class and panel is one entry with
    both credited; a disagreement keeps both entries."""
    sweep_dir = Path(sweep_dir)
    sources = load_sources(sweep_dir)
    if not sources:
        return None
    entries: dict[tuple, dict] = {}
    coverage: dict[tuple, dict] = {}
    searches = dips = marks = below = 0
    control = {c: 0 for c in CLASS_IDS}
    control_n = 0
    for src in sources:
        rec = src["record"]
        credit = {"name": src["name"], "source": src["source"], **({"bundle": src["bundle"]} if src["bundle"] else {})}
        for s in rec.get("stars", []):
            key = (int(s["tic"]), int(s["sector"]))
            row = coverage.setdefault(key, {"tic": key[0], "sector": key[1], "ra": s.get("ra"), "dec": s.get("dec"), "tmag": s.get("tmag"),
                                            "status": s.get("status"), "searched_by": [], "counts": {c: 0 for c in CLASS_IDS}, "n_dips": 0})
            if s.get("status") == "searched":
                searches += 1
                dips += s.get("n_dips", 0)
                marks += s.get("n_marks", 0)
                below += (s.get("rejected") or {}).get("below_consensus", 0)
                row["status"] = "searched"
                row["searched_by"].append(src["name"])
                row["n_dips"] = max(row["n_dips"], s.get("n_dips", 0))
                row.update({k: s.get(k) for k in ("file_sha256", "n_points", "rejected", "tois") if s.get(k) is not None})
                inv = (s.get("control") or {}).get("inverted")
                if inv:
                    control_n += 1
                    for c in CLASS_IDS:
                        control[c] += inv["counts"].get(c, 0)
            elif row["status"] != "searched":
                row["status"] = s.get("status")
                if s.get("error"):
                    row["error"] = s["error"]
            reviewers = s.get("reviewers") or []
            panel = ",".join(sorted(r["id"] for r in reviewers))
            for e in s.get("entries", []):
                k = (e["id"], e["class"], panel)
                if k in entries:
                    if credit["name"] not in [c["name"] for c in entries[k]["credit"]]:
                        entries[k]["credit"].append(credit)
                    continue
                entries[k] = {**e, "panel": [{"id": r["id"], "kind": r["kind"]} for r in reviewers], "file_sha256": s.get("file_sha256"),
                              "code": s.get("code"), "config_sha256": s.get("config_sha256"), "credit": [credit]}
    rows = list(coverage.values())
    for r in rows:
        r["counts"] = {c: 0 for c in CLASS_IDS}
    by_key = {(r["tic"], r["sector"]): r for r in rows}
    out_entries = sorted(entries.values(), key=lambda e: (CLASS_IDS.index(e["class"]), e["tic"], e["sector"], e.get("t_center") or 0))
    for e in out_entries:
        by_key[(e["tic"], e["sector"])]["counts"][e["class"]] += 1
    searched = [r for r in rows if r["status"] == "searched"]
    counts = {
        "stars_searched": len({r["tic"] for r in searched}), "star_sectors_searched": len(searched), "searches": searches,
        "star_sectors_recorded": len(rows), "not_searched": {s: sum(1 for r in rows if r["status"] == s) for s in ("no_data", "error", "pending")},
        "dips_reviewed": dips, "marks": marks, "below_consensus": below, "entries": len(out_entries),
        "by_class": {c: sum(1 for e in out_entries if e["class"] == c) for c in CLASS_IDS},
        "by_kind": {k: sum(1 for e in out_entries if e["kind"] == k) for k in ("dip", "brightening", "variability")},
        "control_inverted": {"star_sectors": control_n, "by_class": control},
        "sectors": sorted({r["sector"] for r in rows}),
        "planet_candidates_matching_toi": sum(1 for e in out_entries if e["class"] == "planet_candidate" and e.get("toi_match")),
    }
    contributors: dict[str, dict] = {}
    for src in sources:
        c = contributors.setdefault(src["name"], {"name": src["name"], "sources": [], "star_sectors": 0})
        c["sources"].append(src["source"])
        c["star_sectors"] += sum(1 for s in src["record"].get("stars", []) if s.get("status") == "searched")
    cat = {
        "format": CATALOGUE_FORMAT, "generated_at": _now(), "counts": counts,
        "classes": [{"id": c, "label": lab, "rule": RULES[c], "confidence": CONFIDENCE[c]} for c, lab in CLASSES],
        "sources": [{"name": s["name"], "source": s["source"], "bundle": s["bundle"], "sector": s["record"].get("sector"),
                     "slice": s["record"].get("slice"), "targets_in_sector": s["record"].get("targets_in_sector"),
                     "config_name": s["record"].get("config_name"), "config_sha256": s["record"].get("config_sha256"),
                     "code": s["record"].get("code"), "generated_at": s["record"].get("generated_at"),
                     "order": s["record"].get("order"),
                     "searched": sum(1 for x in s["record"].get("stars", []) if x.get("status") == "searched"),
                     "kinds": sorted({r.get("kind") for x in s["record"].get("stars", []) for r in x.get("reviewers") or [] if r.get("kind")})}
                    for s in sources],
        "contributors": sorted(contributors.values(), key=lambda c: -c["star_sectors"]),
        "coverage": sorted(rows, key=lambda r: (r["sector"], r["tic"])),
        "entries": out_entries,
    }
    path = sweep_dir / "catalogue.json"
    path.write_text(json.dumps(finite(cat), separators=(",", ":"), default=_json_default, allow_nan=False) + "\n")
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def finite(o):
    """A copy with every non-finite float (NaN, ±inf) replaced by None, so the files are strict JSON."""
    import math

    if isinstance(o, dict):
        return {k: finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [finite(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def _json_default(o):
    import numpy as np

    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)

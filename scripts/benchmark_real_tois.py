#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""S1c: run the blind benchmark on real TOIs (src/setuhq/benchmark_toi.py explains the design).

    python scripts/benchmark_real_tois.py freeze            # TOI table → docs/results/benchmark_toi_sample.json
    python scripts/benchmark_real_tois.py run --workers 4   # SPOC light curves (cache/mast) → cache/bench/<tic>.json
    python scripts/benchmark_real_tois.py report            # → docs/results/benchmark_real_tois.{md,json}

The clipping-fixed re-run (``--edition clipfix``) repeats the frozen protocol on the current code: the same sample,
seed, split, controls and metrics, on the same light curve of each star (the sector the first run recorded, read
from the download cache), into cache/bench_clipfix and docs/results/benchmark_real_tois_clipfix.{md,json}. The
first run's files stay as the historical pre-fix record:

    python scripts/benchmark_real_tois.py --edition clipfix rerun --workers 4
    python scripts/benchmark_real_tois.py --edition clipfix clipping
    python scripts/benchmark_real_tois.py --edition clipfix feed
    python scripts/benchmark_real_tois.py --edition clipfix report

Downloads and per-star outputs stay in the gitignored ``cache/``; only the frozen sample and the summary are
committed. A star with no SPOC 2-minute light curve is recorded as "no data", never dropped silently.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from setuhq import benchmark_toi as B  # noqa: E402

SAMPLE = ROOT / "docs/results/benchmark_toi_sample.json"
# The first run (pre-fix code): its per-star records give the re-run each star's sector and searchability.
FIRST_CACHE = ROOT / "cache/bench"
# Editions of the benchmark: the first run, and the re-run of the same protocol on the clipping-fixed code. Each keeps
# its own per-star cache and its own report files. Chosen with --edition (SETUHQ_BENCH_EDITION for worker processes).
EDITIONS = {"first": ("cache/bench", "docs/results/benchmark_real_tois.md"),
            "clipfix": ("cache/bench_clipfix", "docs/results/benchmark_real_tois_clipfix.md")}


def _edition_paths(edition: str):
    cache, md = EDITIONS[edition]
    return ROOT / cache, ROOT / md


EDITION = os.environ.get("SETUHQ_BENCH_EDITION", "first")
CACHE, OUT_MD = _edition_paths(EDITION)
# The Probes and their frozen calibrated weights (docs/results/reviewer_weights_full_panel.json, measured on the code of
# 2026-10-16; on the current code the same calibration gives other rates but, with three Probes and these thresholds,
# the same consensus decisions: tests/test_calibration_equivalence.py). A parameter of the frozen protocol.
PROBES = [("volunteer-sensitive", 4.5, 0.05, 11, 0.6), ("volunteer-typical", 5.0, 0.10, 12, 0.6), ("volunteer-cautious", 5.5, 0.15, 13, 0.4)]


def cmd_freeze(args) -> int:
    rows, fetched = B.fetch_toi_table(ROOT / "cache/toi/toi.csv", refresh=args.refresh)
    sample = B.freeze_sample(rows, fetched_at=fetched, n_pos=args.n_pos, n_fp=args.n_fp, n_fa=args.n_fa)
    SAMPLE.write_text(json.dumps(sample, indent=1) + "\n")
    print(f"{SAMPLE}: {sample['counts']} from the TOI table fetched {fetched}; sha256 {sample['sha256'][:16]}")
    return 0


# The pipeline code a result depends on (search, vetting, fit, reviewers). Each per-star result records the
# fingerprint of these files, so the report can say which code produced it and check it against the committed
# code. The benchmark's own scoring and reporting (benchmark_toi.py, this script) are re-applied at report time.
CODE_FILES = ["src/setuhq/discover.py"] + [
    f"src/setuhq/{m}.py" for m in ("aggregate", "config", "lightcurve", "loaders", "pipeline", "preprocess", "search",
                                     "subjects", "transitfit", "vet", "reviewers/base", "reviewers/simulated")]
# Each file enters the hash under the path it had when the committed fingerprints were taken (src/exoplan/...,
# before the rename to SetuHQ), with its canonical text (setuhq.starsearch.canonical_source: no SPDX header, the
# package name as exoplan), so docs/results/benchmark_real_tois.json still verifies after the rename.
LEGACY_PREFIX = ("src/setuhq/", "src/exoplan/")


def _label(f: str) -> str:
    return f.replace(*LEGACY_PREFIX, 1)


def _code_bytes(f: str, rev: str | None) -> bytes:
    from setuhq.starsearch import canonical_source

    if rev is None:
        return canonical_source((ROOT / f).read_bytes())
    import subprocess

    for path in (f, _label(f)):
        out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True, text=True)
        if out.returncode == 0:
            return canonical_source(out.stdout.strip().encode() + b"\n")
    raise FileNotFoundError(f"{f} is not in commit {rev}, under either name")


def code_fingerprint(rev: str | None = None) -> str:
    """sha256 of CODE_FILES (each under its historical path, see LEGACY_PREFIX), in the working tree (None) or at a
    commit."""
    import hashlib

    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(_label(f).encode() + b"\0" + _code_bytes(f, rev) + b"\0")
    return h.hexdigest()[:16]


def _code_ast(rev: str | None) -> str:
    """CODE_FILES as syntax trees without docstrings (comments never reach the tree): the code's behaviour."""
    import ast

    out = []
    for f in CODE_FILES:
        tree = ast.parse(_code_bytes(f, rev))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
        out.append(ast.dump(tree))
    return "\n".join(out)


def code_provenance(results: list[dict]) -> dict:
    """Which commit's pipeline code produced the per-star results, and whether HEAD differs from it only in
    comments and docstrings."""
    seen = sorted({r.get("code") for r in results if r.get("real")} - {None})
    commits = _git("log", "--format=%h", "-n", "30").splitlines()
    match = {fp: next((c for c in reversed(commits) if code_fingerprint(c) == fp), None) for fp in seen}
    same = {fp: (c is not None and _code_ast(c) == _code_ast(None)) for fp, c in match.items()}
    return {"fingerprints": seen, "commit": match, "head_same_behaviour": same}


def _config():
    from setuhq.config import RunConfig

    return RunConfig(name="benchmark-real-tois", subject_days=13.0, min_points=300, bin_minutes=10.0, detrend_window_days=1.0,
                     search="sector", min_period=0.5, fap_trials=0, fap_cache=None, fit_transits=True, stellar="none")


def _ephemerides(tic: int) -> list[tuple[float, float, float]]:
    """Every TOI on this star from the cached TOI table: (period, mid-time BTJD, T14 h), to mask before scrambling."""
    rows, _ = B.fetch_toi_table(ROOT / "cache/toi/toi.csv")
    out = []
    for r in rows:
        if r.get("tid") and int(float(r["tid"])) == tic:
            p, t0, d = B._num(r.get("pl_orbper")), B._num(r.get("pl_tranmid")), B._num(r.get("pl_trandurh"))
            if p and t0 and d:
                out.append((p, t0 - 2457000.0, d))
    return out


def run_star(toi: dict, code: str = "") -> dict:
    """Download one star's first SPOC 2-minute sector, run the panel on it and on its two controls, score it."""
    from setuhq.loaders import load_tess

    tic = toi["tic"]
    out = {"toi": toi["toi"], "tic": tic, "code": code, "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    target = f"TIC {tic}"
    try:
        import lightkurve as lk

        search = lk.search_lightcurve(target, author="SPOC", exptime=120)
        sectors = sorted(int(s) for s in search.table["sequence_number"]) if len(search) else []
        if not sectors:
            out["no_data"] = "no SPOC 2-minute light curve"
            return out
        sector = sectors[0]
        lcs = load_tess(target, [sector], download_dir=str(ROOT / "cache/mast"))
    except Exception as exc:  # noqa: BLE001 (recorded per star, the run goes on)
        out["no_data"] = f"download failed: {type(exc).__name__}: {str(exc)[:200]}"
        return out
    return run_curves(toi, lcs[0], sector, out)


def run_curves(toi: dict, lc, sector: int, out: dict) -> dict:
    """The panel on one star's light curve and on its two controls, each scored (the part of run_star after the
    download, shared with the re-run)."""
    from setuhq.pipeline import run_pipeline
    from setuhq.reviewers.simulated import SimulatedVolunteer

    tic = toi["tic"]
    target = f"TIC {tic}"
    out["sector"] = sector
    out["n_points"] = int(lc.time.size)
    # Stellar parameters from the TOI table (Teff, log g, R★; ρ★ from g and R★), so the fit needs no network.
    star = {"teff": toi.get("teff"), "logg": toi.get("logg"), "radius": toi.get("star_radius"), "source": "TOI table"}
    if toi.get("logg") and toi.get("star_radius"):
        g = 10 ** toi["logg"] / 100.0  # m/s²
        r = toi["star_radius"] * 6.957e8
        star["rho"] = 3 * g / (4 * 3.141592653589793 * 6.67430e-11 * r) / 1000.0
    reviewers = [SimulatedVolunteer(rid, snr_threshold=snr, miss_probability=miss, seed=seed) for rid, snr, miss, seed, _ in PROBES]
    weights = {rid: w for rid, *_, w in PROBES}
    config = _config()
    from dataclasses import replace

    variants = {"real": lc, "inverted": B.inverted(lc), "scrambled": B.scrambled(lc, seed=tic % (2**31), ephemerides=_ephemerides(tic))}
    for name, curve in variants.items():
        cfg = config if name == "real" else replace(config, fit_transits=False)
        run_dir = CACHE / str(tic) / name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "stellar.json").write_text(json.dumps({target: star}))
        try:
            run_pipeline(cfg, [curve], reviewers, run_dir, weights=weights, weights_source="frozen calibrated Probe weights")
            cands = json.loads((run_dir / "candidates.json").read_text())
        except Exception:  # noqa: BLE001
            out[name] = {"error": traceback.format_exc(limit=2)[-400:]}
            continue
        if name == "real":
            out["real"] = B.score_star(toi, cands)
        else:
            out[name] = {"passed": sum(1 for c in cands if c["passed"]), "consensus": len(cands)}
    out["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return out


def cmd_run(args) -> int:
    sample = json.loads(SAMPLE.read_text())
    CACHE.mkdir(parents=True, exist_ok=True)
    def failed(t):
        # A transient download or worker failure is retried; "no SPOC 2-minute light curve" is an answer and is kept.
        path = CACHE / f"{t['tic']}.json"
        return path.exists() and str(json.loads(path.read_text()).get("no_data", "")).startswith(("download failed", "worker failed"))

    todo = [t for t in sample["tois"] if not (CACHE / f"{t['tic']}.json").exists() or (args.retry_failed and failed(t))]
    if args.limit:
        todo = todo[: args.limit]
    code = code_fingerprint()
    print(f"{len(todo)} stars to run ({len(sample['tois']) - len(todo)} done); code {code}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_star, t, code): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            t = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"toi": t["toi"], "tic": t["tic"], "no_data": f"worker failed: {exc}"}
            (CACHE / f"{t['tic']}.json").write_text(json.dumps(res))
            if i % 10 == 0:
                print(f"{i}/{len(todo)} in {time.time() - t0:.0f} s", flush=True)
    return 0


def rerun_star(toi: dict, code: str) -> dict:
    """One star again on the current code, on the light curve the first run used: its recorded sector, read from the
    download cache (fetched only if the file is missing). A star the first run found no SPOC 2-minute light curve for
    keeps that answer, so the searchable set is the frozen one."""
    first = json.loads((FIRST_CACHE / f"{toi['tic']}.json").read_text())
    out = {"toi": toi["toi"], "tic": toi["tic"], "code": code, "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rerun_of": {"sector": first.get("sector"), "code": first.get("code"), "no_data": first.get("no_data")}}
    if not first.get("sector"):
        out["no_data"] = first.get("no_data") or "no SPOC 2-minute light curve"
        return out
    import shutil

    shutil.rmtree(CACHE / str(toi["tic"]), ignore_errors=True)  # a star restarted after a crash starts clean
    try:
        lc = load_cached(toi["tic"], first["sector"])
    except Exception as exc:  # noqa: BLE001 (recorded per star, the run goes on)
        out["no_data"] = f"download failed: {type(exc).__name__}: {str(exc)[:200]}"
        return out
    return run_curves(toi, lc, first["sector"], out)


def cmd_rerun(args) -> int:
    """The frozen protocol again on the current code, star by star into this edition's cache (resumable)."""
    if CACHE == FIRST_CACHE:
        print("rerun writes a new edition: use --edition clipfix")
        return 1
    sample = json.loads(SAMPLE.read_text())
    CACHE.mkdir(parents=True, exist_ok=True)

    def failed(t):
        path = CACHE / f"{t['tic']}.json"
        return path.exists() and str(json.loads(path.read_text()).get("no_data", "")).startswith(("download failed", "worker failed"))

    todo = [t for t in sample["tois"] if not (CACHE / f"{t['tic']}.json").exists() or failed(t)]
    if args.limit:
        todo = todo[: args.limit]
    code = code_fingerprint()
    print(f"{len(todo)} stars to re-run ({len(sample['tois']) - len(todo)} done); code {code}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(rerun_star, t, code): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            t = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"toi": t["toi"], "tic": t["tic"], "no_data": f"worker failed: {exc}"}
            res["finished"] = res.get("finished") or datetime.now(timezone.utc).isoformat(timespec="seconds")
            (CACHE / f"{t['tic']}.json").write_text(json.dumps(res))
            if i % 10 == 0:
                print(f"{i}/{len(todo)} in {time.time() - t0:.0f} s", flush=True)
    return 0


def load_cached(tic: int, sector: int):
    """The star's SPOC 2-minute light curve from the download cache (cache/mast), with no network call: the same
    steps as setuhq.loaders.load_tess after its download (quality == 0 and finite points, median-normalised)."""
    import lightkurve as lk
    import numpy as np

    from setuhq.lightcurve import LightCurve
    from setuhq.loaders import _file_provenance, _plain

    files = [f for f in sorted((ROOT / "cache/mast/mastDownload/TESS").glob(f"tess*-s{sector:04d}-{tic:016d}-*-s/*_lc.fits")) if f.stat().st_size]  # an interrupted download is empty
    if not files:  # downloaded before the cache directory was set: fetch it into cache/mast
        from setuhq.loaders import load_tess

        return load_tess(f"TIC {tic}", [sector], download_dir=str(ROOT / "cache/mast"))[0]
    lc = lk.read(str(files[0]), flux_column="pdcsap_flux")
    time, flux, flux_err, quality = (_plain(x) for x in (lc.time, lc.flux, lc.flux_err, lc.quality))
    good = (quality == 0) & np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
    median = np.median(flux[good])
    return LightCurve(target=f"TIC {tic}", mission="TESS", time=time[good], flux=(flux / median)[good],
                      flux_err=(flux_err / median)[good],
                      provenance={"source": "MAST", "author": "SPOC", "sector": int(lc.sector), "exptime_s": 120,
                                  "flux_column": "pdcsap_flux", "time_unit": "BTJD", "lightkurve_version": lk.__version__,
                                  **_file_provenance(lc)})


def rescore_star(res: dict, toi: dict, code: str) -> dict:
    """Re-vet one star's stored runs (real and both controls) with the current code, from the stored
    classifications (setuhq.pipeline.rebuild_run: the reviewers are not asked again), and score them again."""
    from dataclasses import replace

    from setuhq.pipeline import rebuild_run

    tic = res["tic"]
    lc = load_cached(tic, res["sector"])
    variants = {"real": lc, "inverted": B.inverted(lc), "scrambled": B.scrambled(lc, seed=tic % (2**31), ephemerides=_ephemerides(tic))}
    out = dict(res, code=code, rescored=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    for name, curve in variants.items():
        run_dir = CACHE / str(tic) / name
        if not (run_dir / "classifications.csv").exists():
            continue
        cfg = _config() if name == "real" else replace(_config(), fit_transits=False)
        try:
            try:
                cands = [c.as_row() for c in rebuild_run(cfg, [curve], run_dir)]
            except ValueError as exc:
                if "not reproduced" not in str(exc):
                    raise
                # The stored control was built before its construction changed (the scrambled control first masks
                # every known TOI): run the Probes on it afresh instead of reusing classifications of a different curve.
                cands = _fresh_variant(cfg, curve, run_dir)
                out.setdefault("rerun_fresh", []).append(name)
        except Exception:  # noqa: BLE001
            out[name] = {"error": traceback.format_exc(limit=2)[-400:]}
            continue
        out[name] = B.score_star(toi, cands) if name == "real" else {"passed": sum(1 for c in cands if c["passed"]), "consensus": len(cands)}
    return out


def _fresh_variant(cfg, curve, run_dir: Path) -> list[dict]:
    import shutil

    from setuhq.pipeline import run_pipeline
    from setuhq.reviewers.simulated import SimulatedVolunteer

    stellar = (run_dir / "stellar.json").read_text() if (run_dir / "stellar.json").exists() else None
    shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    if stellar:
        (run_dir / "stellar.json").write_text(stellar)
    reviewers = [SimulatedVolunteer(rid, snr_threshold=snr, miss_probability=miss, seed=seed) for rid, snr, miss, seed, _ in PROBES]
    run_pipeline(cfg, [curve], reviewers, run_dir, weights={rid: w for rid, *_, w in PROBES}, weights_source="frozen calibrated Probe weights")
    return json.loads((run_dir / "candidates.json").read_text())


def cmd_rescore(args) -> int:
    """Bring every stored per-star result to the current code (after a fix that changes vetting or the fit)."""
    sample = json.loads(SAMPLE.read_text())
    code = code_fingerprint()
    tois = {t["tic"]: t for t in sample["tois"]}
    todo = []
    for t in sample["tois"]:
        path = CACHE / f"{t['tic']}.json"
        if path.exists():
            r = json.loads(path.read_text())
            broken = any(isinstance(r.get(v), dict) and "error" in r[v] for v in ("real", "inverted", "scrambled"))
            if r.get("sector") and (r.get("code") != code or broken):
                todo.append(r)
    # A result whose code differs from the working tree only in comments and docstrings is current.
    prov = code_provenance(todo)
    todo = [r for r in todo if not prov["head_same_behaviour"].get(r.get("code"))
            or any(isinstance(r.get(v), dict) and "error" in r[v] for v in ("real", "inverted", "scrambled"))]
    print(f"{len(todo)} stars to re-score to code {code}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(rescore_star, r, tois[r["tic"]], code): r for r in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            r = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"TIC {r['tic']}: {type(exc).__name__}: {exc}", flush=True)
                continue
            (CACHE / f"{r['tic']}.json").write_text(json.dumps(res))
            if i % 10 == 0:
                print(f"{i}/{len(todo)} in {time.time() - t0:.0f} s", flush=True)
    return 0


CLIP = CACHE / "clip"
CLIP_RATIO = 8.0  # TOI depth / per-cadence scatter above which preprocess.clean (pre-fix) can delete the transit


def clip_star(res: dict, toi: dict) -> dict:
    """How exposed one star is to the known preprocess.clean bug (40cceca): clean() drops every point more than
    10x the point-to-point scatter below the 0.5-day running median, with no run-length test, so a transit deeper
    than about 10x the per-cadence scatter loses its in-transit points before review and BLS. Measured on the light
    curve the run used: the depth/scatter ratio, and the in-transit points before and after clean()."""
    import numpy as np

    from setuhq.preprocess import clean, diff_sigma

    lc = load_cached(res["tic"], res["sector"])
    sigma = float(diff_sigma(lc.flux))
    ratio = toi["depth_ppm"] * 1e-6 / sigma if toi.get("depth_ppm") and sigma > 0 else None
    t0, period, half = toi["tranmid_bjd"] - 2457000.0, toi["period"], 0.5 * toi["duration_hours"] / 24
    inside = lambda t: np.abs((t - t0 + 0.5 * period) % period - 0.5 * period) < half
    cleaned = clean(lc)
    n_raw, n_clean = int(inside(lc.time).sum()), int(inside(cleaned.time).sum())
    return {"tic": res["tic"], "toi": res["toi"], "scatter_ppm": sigma * 1e6, "depth_over_scatter": ratio,
            "affected": bool(ratio is not None and ratio > CLIP_RATIO), "in_transit_raw": n_raw, "in_transit_after_clean": n_clean,
            "in_transit_removed_fraction": (1 - n_clean / n_raw) if n_raw else None}


def cmd_clipping(args) -> int:
    sample = json.loads(SAMPLE.read_text())
    CLIP.mkdir(parents=True, exist_ok=True)
    tois = {t["tic"]: t for t in sample["tois"]}
    done = [json.loads((CACHE / f"{t['tic']}.json").read_text()) for t in sample["tois"] if (CACHE / f"{t['tic']}.json").exists()]
    todo = [r for r in done if r.get("real") and not (CLIP / f"{r['tic']}.json").exists()]
    print(f"{len(todo)} stars to measure for clipping", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(clip_star, r, tois[r["tic"]]): r for r in todo}
        for fut in as_completed(futures):
            r = futures[fut]
            try:
                (CLIP / f"{r['tic']}.json").write_text(json.dumps(fut.result()))
            except Exception as exc:  # noqa: BLE001
                print(f"TIC {r['tic']}: {type(exc).__name__}: {exc}", flush=True)
    return 0


FEED = CACHE / "feed"
# The feed rule this table measures, frozen as it stood when the sample was frozen (configs/discovery.toml and
# discover.MAX_FEED_FAP at fbc1ed9): FAP < 0.01 over 200 trials, one sector. The feed has since moved to the
# pre-registered two-sector rule (scripts/feed_rule_eval.py measures that one), so the cut is stated here.
FEED_FAP_TRIALS = 200
FEED_FAP_CUT = 0.01


def admits_old_fap(fap) -> bool:
    return fap is not None and fap < FEED_FAP_CUT


def feed_eligible(c: dict) -> bool:
    """The discovery feed's admission rule before its FAP test (discover.run_discovery): passed vetting, not
    off_ephemeris, at most MAX_FEED_DEPTH_PPM deep, on a periodic signal with at least MIN_FEED_TRANSITS transits."""
    from setuhq import discover as Dv

    return (bool(c["passed"]) and "off_ephemeris" not in (c.get("flags") or "") and (c.get("depth_ppm") or 0) <= Dv.MAX_FEED_DEPTH_PPM
            and c.get("period_days") is not None and (c.get("n_transits") or 0) >= Dv.MIN_FEED_TRANSITS)


def _target(tic: int):
    """The star's TOIs from the cached TOI table, as discover.Target, so a real dip is classed known_toi or new_candidate."""
    from setuhq import discover as Dv

    rows, _ = B.fetch_toi_table(ROOT / "cache/toi/toi.csv")
    target = Dv.Target(tic)
    for r in rows:
        if r.get("tid") and int(float(r["tid"])) == tic:
            toi = Dv.Toi(name=r["toi"], period=B._num(r.get("pl_orbper")), tranmid=B._num(r.get("pl_tranmid")),
                         period_err=B._num(r.get("pl_orbpererr1")), tranmid_err=B._num(r.get("pl_tranmiderr1")),
                         duration_hours=B._num(r.get("pl_trandurh")), disposition=r.get("tfopwg_disp") or None)
            target.tois.append(toi)
            if toi.period is not None:
                target.toi_periods.append(toi.period)
            target.toi_names.append(toi.name)
    return target


def feed_star(res: dict) -> dict:
    """Apply the discovery feed's full admission rule to one star's real curve and its two controls.

    Variants with no dip that passes the rule's non-FAP parts admit nothing, whatever the FAP, so only the others
    are re-run with the feed's FAP (200 block-bootstrap trials) and the feed's own weights file."""
    from dataclasses import replace

    from setuhq import discover as Dv
    from setuhq.pipeline import run_pipeline
    from setuhq.reviewers.simulated import SimulatedVolunteer

    tic = res["tic"]
    out = {"tic": tic, "toi": res["toi"], "sector": res.get("sector")}
    target = _target(tic)
    lc = None
    weights_file = ROOT / "docs/results/reviewer_weights.json"
    weights = json.loads(weights_file.read_text())
    for v in ("real", "inverted", "scrambled"):
        if not res.get(v) or "error" in res[v]:
            continue
        path = CACHE / str(tic) / v / "candidates.json"
        pre = [c for c in json.loads(path.read_text()) if feed_eligible(c)] if path.exists() else []
        row = {"pre_fap": len(pre), "admitted": 0, "new_candidate": 0, "known_toi": 0, "new_signals": 0, "fap": []}
        periods = set()
        if pre:
            if lc is None:
                lc = load_cached(tic, res["sector"])
            curve = {"real": lc, "inverted": B.inverted(lc),
                     "scrambled": B.scrambled(lc, seed=tic % (2**31), ephemerides=_ephemerides(tic))}[v]
            reviewers = [SimulatedVolunteer(rid, snr_threshold=snr, miss_probability=miss, seed=seed) for rid, snr, miss, seed, _ in PROBES]
            run_dir = FEED / str(tic) / v
            run_dir.mkdir(parents=True, exist_ok=True)
            cfg = replace(_config(), fit_transits=False, fap_trials=FEED_FAP_TRIALS, fap_cache=None)
            run_pipeline(cfg, [curve], reviewers, run_dir, weights=weights, weights_source=str(weights_file))
            for c in json.loads((run_dir / "candidates.json").read_text()):
                if feed_eligible(c) and admits_old_fap(c.get("fap")):
                    row["admitted"] += 1
                    row["fap"].append(c.get("fap"))
                    cand = {"t_center": c["t_center"], "time_unit": c.get("time_unit", "BTJD"),
                            "duration_hours": c["duration_hours"], "period_days": c["period_days"]}
                    status = "known_toi" if Dv.match_toi(cand, target) else "new_candidate"
                    row[status] += 1
                    if status == "new_candidate":
                        periods.add(round(c["period_days"], 3))
            row["new_signals"] = len(periods)  # the feed adds one entry per dip; this counts distinct periodic signals
        out[v] = row
    return out


def cmd_feed(args) -> int:
    sample = json.loads(SAMPLE.read_text())
    FEED.mkdir(parents=True, exist_ok=True)
    done = [json.loads((CACHE / f"{t['tic']}.json").read_text()) for t in sample["tois"] if (CACHE / f"{t['tic']}.json").exists()]
    todo = [r for r in done if r.get("real") and not (FEED / f"{r['tic']}.json").exists()]
    print(f"{len(todo)} stars to put through the feed rule", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(feed_star, r): r for r in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            r = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"tic": r["tic"], "toi": r["toi"], "error": f"{type(exc).__name__}: {exc}"[:300]}
            (FEED / f"{r['tic']}.json").write_text(json.dumps(res))
            if i % 10 == 0:
                print(f"{i}/{len(todo)} in {time.time() - t0:.0f} s", flush=True)
    return 0


SENTINEL_N = 20  # stars per class (CP/KP and FP) in the Sentinels' stated subsample, from the held-out half


def sentinel_subsample(sample: dict, done: dict) -> list[dict]:
    """A stated, seeded subsample of held-out stars that have a real-data run: SENTINEL_N CP/KP and SENTINEL_N FP."""
    import numpy as np

    rng = np.random.default_rng(sample["seed"] + 1)
    out = []
    for cls in ("positive", "fp"):
        pool = [t for t in sample["tois"] if t["half"] == "held_out" and t["class"] == cls and done.get(t["tic"], {}).get("real")]
        pool.sort(key=lambda t: t["toi"])
        idx = rng.permutation(len(pool))[:SENTINEL_N]
        out += [pool[i] for i in sorted(idx)]
    return out


def sentinel_panel(config: str | None) -> list:
    """The Sentinels to run: the two Claude personas through the Claude Code CLI (the benchmarked default), or
    the Sentinels of a run config's [[reviewers]] (any provider; Probes in it are ignored)."""
    from setuhq.config import SENTINEL_TYPES, build_reviewers, load_config
    from setuhq.reviewers.claude_code import ClaudeCodeReviewer

    if config is None:
        return [ClaudeCodeReviewer(reviewer_id=f"claude-{p}", persona=p, cache_dir=str(ROOT / "cache/claude-code"))
                for p in ("volunteer", "skeptic")]
    specs = [s for s in load_config(config).reviewers if s.get("type") in SENTINEL_TYPES]
    return build_reviewers(specs, cache_root=ROOT / "cache")


def cmd_sentinels(args) -> int:
    """The Sentinels on the stated subsample's real light curves, subject by subject. By default both Claude
    personas through the Claude Code CLI (cached in cache/claude-code); with ``--panel CONFIG`` the Sentinels of
    that config, on any provider. Each one runs only when its key, SDK or CLI is present here (a paid API is never
    called without its key in the environment). Results are merged into cache/bench/sentinels.json by reviewer
    id, so a provider added later is compared with every Sentinel already there (``report`` writes the φ table)."""
    import numpy as np

    from setuhq.subjects import Subject

    sample = json.loads(SAMPLE.read_text())
    done = {t["tic"]: json.loads((CACHE / f"{t['tic']}.json").read_text()) for t in sample["tois"] if (CACHE / f"{t['tic']}.json").exists()}
    sub = sentinel_subsample(sample, done)
    panel = sentinel_panel(args.panel)
    for r in panel:
        if not r.available():
            print(f"{r.reviewer_id}: not run ({r.unavailable_reason()})")
    reviewers = [r for r in panel if r.available()]
    if not reviewers:
        print("No Sentinel of this panel can run here; nothing was run.")
        return 1
    jobs = []
    for t in sub:
        sdir = CACHE / str(t["tic"]) / "real" / "subjects"
        for js in sorted(sdir.glob("*.json")):
            d = json.loads(js.read_text())
            subj = Subject(d["subject_id"], "TESS", d.get("time_unit", "BTJD"), np.asarray(d["time"]), np.asarray(d["flux"]), np.asarray(d["flux_err"]), {})
            for r in reviewers:
                jobs.append((t, subj, js.with_suffix(".png"), r))
    print(f"{len(sub)} stars, {len(jobs)} Sentinel reviews", flush=True)

    def one(job):
        t, subj, png, r = job
        try:
            c = r.review(subj, png)
            return t["toi"], r.reviewer_id, subj.subject_id, {"label": c.label, "reason": c.reason, "marks": [[m.t_start, m.t_end] for m in c.marks],
                                                              "model": c.metadata.get("model"), "model_reported": c.metadata.get("model_reported"),
                                                              "called_at": c.metadata.get("called_at")}
        except Exception as exc:  # noqa: BLE001
            return t["toi"], r.reviewer_id, subj.subject_id, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    from concurrent.futures import ThreadPoolExecutor

    path = CACHE / "sentinels.json"
    stored = json.loads(path.read_text()) if path.exists() else {}
    results = stored.get("results") or {}
    for r in reviewers:  # this run's answers replace any earlier ones of the same reviewer
        for per in results.values():
            per.pop(r.reviewer_id, None)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (toi, rid, sid, res) in enumerate(pool.map(one, jobs), 1):
            results.setdefault(toi, {}).setdefault(rid, {})[sid] = res
            if i % 10 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    identities = (stored.get("reviewers") or {}) | {r.reviewer_id: r.describe() for r in reviewers}
    path.write_text(json.dumps({"subsample": [t["toi"] for t in sub], "results": results, "reviewers": identities}, indent=1))
    return 0


def cmd_sentinels_carry(args) -> int:
    """The re-run edition's Sentinel answers, with no new call: the first run's stored answers (cache/bench/sentinels.json)
    are carried over for a star only when every one of its real subjects is byte-identical on this code (the image the
    Sentinel saw, and the subject's arrays and time range, which make up its prompt). Other stars are left out."""
    if CACHE == FIRST_CACHE:
        print("sentinels-carry fills a re-run edition: use --edition clipfix")
        return 1
    first = json.loads((FIRST_CACHE / "sentinels.json").read_text())
    sample = json.loads(SAMPLE.read_text())
    tic = {t["toi"]: t["tic"] for t in sample["tois"]}
    carried, not_carried, results = [], {}, {}
    for name in first["subsample"]:
        old_dir, new_dir = FIRST_CACHE / str(tic[name]) / "real" / "subjects", CACHE / str(tic[name]) / "real" / "subjects"
        sids = sorted({sid for per in first["results"].get(name, {}).values() for sid in per})
        old_set = sorted(p.stem for p in old_dir.glob("*.png"))
        new_set = sorted(p.stem for p in new_dir.glob("*.png"))
        why = None
        if not new_set:
            why = "not re-run"
        elif new_set != old_set or set(sids) != set(old_set):
            why = "different subjects"
        else:
            for sid in old_set:
                if (old_dir / f"{sid}.png").read_bytes() != (new_dir / f"{sid}.png").read_bytes():
                    why = f"subject {sid}: the image changed"
                    break
                if (old_dir / f"{sid}.json").read_bytes() != (new_dir / f"{sid}.json").read_bytes():
                    why = f"subject {sid}: the data changed"
                    break
        if why:
            not_carried[name] = why
        else:
            carried.append(name)
            results[name] = first["results"][name]
    # The subsample is the carried stars: a star whose subjects changed has no valid Sentinel answer, so it is left out
    # of every Sentinel measure (the report, the leaderboard's subsample scope), not counted as missed.
    out = {"subsample": carried, "results": results, "reviewers": first.get("reviewers") or {},
           "carried": {"from": "cache/bench/sentinels.json (the first run's stored answers; no Sentinel was asked again)",
                       "rule": "every real subject's image and data byte-identical on this code", "stars": carried,
                       "stated_subsample": first["subsample"], "not_carried": not_carried}}
    (CACHE / "sentinels.json").write_text(json.dumps(out, indent=1))
    print(f"carried {len(carried)} of {len(first['subsample'])} stars; not carried: {not_carried}")
    return 0


def sentinel_scores(sample: dict) -> dict | None:
    """Per persona: on CP/KP stars, did it mark a dip on the TOI's ephemeris; on FP stars, did it pass the TOI's
    dip as a potential planet. And how often the two personas agree (they share one model, so they correlate)."""
    path = CACHE / "sentinels.json"
    if not path.exists():
        return None
    from setuhq.discover import match_toi

    data = json.loads(path.read_text())
    out = B.sentinel_summary(data, sample, match_toi)
    if data.get("carried"):
        out["carried"] = data["carried"]
    return out


def _git(*args) -> str:
    import subprocess

    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


FROZEN_AFTER = "fbc1ed9"  # the last commit before the sample was frozen (2026-10-19T11:00:16Z); its thresholds were set without TOI data
THRESHOLD_PATHS = ["configs", "docs/results/reviewer_weights.json", "docs/results/reviewer_weights_full_panel.json"] + [
    f"src/setuhq/{m}.py" for m in ("aggregate", "config", "discover", "pipeline", "preprocess", "search", "subjects", "transitfit", "vet")
] + ["src/setuhq/reviewers"]


def _threshold_values(rev: str | None) -> dict[str, str]:
    """Every threshold-like value in THRESHOLD_PATHS at a revision (None: the working tree): module-level
    UPPER_CASE constants in the Python files, every key = value line in the config files and weights files, and
    the sha256 of each reference table (REFERENCE_TABLES)."""
    import hashlib
    import re
    import subprocess

    files = []
    # A revision from before the rename keeps the package under src/exoplan; its values are keyed by today's path.
    paths = THRESHOLD_PATHS + [_label(p) for p in THRESHOLD_PATHS if p.startswith(LEGACY_PREFIX[0])]
    for path in paths:
        listed = (_git("ls-tree", "-r", "--name-only", rev, "--", path) if rev else _git("ls-files", "--", path)).splitlines()
        files += [f for f in listed if f.endswith((".py", ".toml", ".json"))]
    out = {}
    for f in sorted(set(files)):
        text = _git("show", f"{rev}:{f}") if rev else ((ROOT / f).read_text() if (ROOT / f).exists() else "")
        key = f.replace(LEGACY_PREFIX[1], LEGACY_PREFIX[0], 1)
        if f.endswith(".py"):
            for m in re.finditer(r"^([A-Z][A-Z0-9_]+)\s*=\s*(.+?)\s*(?:#.*)?$", text, re.M):
                out[f"{key}:{m.group(1)}"] = m.group(2)
        elif f.endswith(".toml"):
            section = ""
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                if line.startswith("["):
                    section = line
                elif "=" in line:
                    k, v = (x.strip() for x in line.split("=", 1))
                    out[f"{key}:{section}{k}"] = v
        else:
            try:
                for k, v in json.loads(text).items():
                    out[f"{key}:{k}"] = json.dumps(v)
            except (ValueError, AttributeError):
                pass
    # The reference tables the vetting reads are thresholds too: track the bytes of the table the code reads (the
    # package copy where the revision has one, else the docs/results original), so editing a table or pointing the
    # code at another one is caught, while moving the same bytes into the package is not.
    for name, places in REFERENCE_TABLES.items():
        for f in places:
            if rev:
                listed = _git("ls-tree", "--name-only", rev, "--", f).strip()
                data = subprocess.run(["git", "show", f"{rev}:{f}"], cwd=ROOT, capture_output=True).stdout if listed else None
            else:
                data = (ROOT / f).read_bytes() if (ROOT / f).exists() else None
            if data is not None:
                out[f"table:{name}:sha256"] = hashlib.sha256(data).hexdigest()
                break
    return out


# The tables behind the fit and the vetting, each with the places the code has read it from, newest first.
REFERENCE_TABLES = {
    "claret2017_tess_quadratic.json": ("src/setuhq/data/claret2017_tess_quadratic.json",
                                       "docs/results/claret2017_tess_quadratic.json"),
    "secondary_calibration.json": ("src/setuhq/data/secondary_calibration.json", "docs/results/secondary_calibration.json"),
}

# Changes the audit accepts only in exactly this form, (value then, value now): the limb-darkening table's
# location moved from docs/results into the package, with the same bytes (its sha256 is tracked above).
EXACT_EXEMPTIONS = {
    "src/setuhq/transitfit.py:LD_TABLE": (
        'Path(__file__).resolve().parents[2] / "docs" / "results" / "claret2017_tess_quadratic.json"',
        'files("setuhq") / "data" / "claret2017_tess_quadratic.json"'),
}


# Values that decide nothing: where caches go, the cache key's version, and the floor below which the indicative
# Gumbel tail is not printed (no rule reads the tail).
NOT_THRESHOLDS = ("fap_cache", "FAP_CACHE_VERSION", "FAP_TAIL_FLOOR",
                  # Which AI provider a Sentinel runs on, its endpoint, key variable and labels: no rule reads them.
                  "KEY_ENV", "PROVIDER_LABELS", "_BASE_URL", "reviewers/gemini.py:BLOCKED", "reviewers/claude.py:DEFAULT_MODEL",
                  "config.py:SENTINEL_TYPES")


def _moved(before: dict, now: dict) -> set[str]:
    """Keys of constants that moved to another file with the same value (a refactor, not a change)."""
    def name(k):
        return k.rsplit(":", 1)[-1]

    gone = {k for k in before if k not in now}
    new = {k for k in now if k not in before}
    out = set()
    for k in gone:
        twin = [n for n in new if name(n) == name(k) and now[n] == before[k] and n.endswith(".py:" + name(k))]
        if len(twin) == 1:
            out |= {k, twin[0]}
    return out


def threshold_audit(rev: str | None = None) -> dict:
    """Did any threshold value change after the sample was frozen? (Then the held-out half could have chosen it.)
    Compares the values themselves, so a comment, a refactor or a bug fix that keeps every threshold is not counted
    (a constant moved to another module with the same value counts as unchanged); the commits since the freeze
    are listed so a reader can check them."""
    # Compared with the code that produced the results (``rev``), not with whatever the tree holds now: a threshold
    # changed later (the pre-registered feed rule) did not shape these numbers.
    before, now = _threshold_values(FROZEN_AFTER), _threshold_values(rev)
    moved = _moved(before, now)
    diff = {k: [before.get(k), now.get(k)] for k in sorted(set(before) | set(now))
            if before.get(k) != now.get(k) and k not in moved}
    changed = {k: v for k, v in diff.items()
               if not any(x in k for x in NOT_THRESHOLDS) and tuple(v) != EXACT_EXEMPTIONS.get(k)}
    ignored = {k: v for k, v in diff.items() if k not in changed}
    commits = _git("log", "--format=%h %s", f"{FROZEN_AFTER}..{rev or 'HEAD'}").splitlines()
    return {"frozen_after": FROZEN_AFTER, "compared_with": rev or "the working tree", "paths": THRESHOLD_PATHS, "values_checked": len(now), "changed": changed,
            "ignored_not_thresholds": ignored, "commits_since": commits, "clean": not changed}


def _newest(commits: list[str | None]) -> str | None:
    """The latest of these commits in the history (the code the newest results came from)."""
    order = _git("log", "--format=%h", "-n", "200").splitlines()
    known = [c for c in commits if c]
    return min(known, key=lambda c: next((i for i, h in enumerate(order) if h.startswith(c) or c.startswith(h)), 10**6)) if known else None


def feed_rule() -> dict | None:
    """The pre-registered two-sector rule's held-out evaluation and the live feed re-run, when they exist (for the
    re-run edition: its own evaluation and live re-run on the fixed code, with the first evaluation beside them)."""
    first = ROOT / "docs/results/feed_rule_validation.json"
    v = first if EDITION == "first" else ROOT / f"docs/results/feed_rule_validation_{EDITION}.json"
    if not v.exists():
        return None
    pre = ROOT / "docs/results/feed_rule_preregistration.json"
    live = ROOT / ("docs/results/feed_rule_live_rerun.json" if EDITION == "first" else f"docs/results/feed_rule_live_rerun_{EDITION}.json")
    out = {"validation": json.loads(v.read_text()), "preregistration": json.loads(pre.read_text()) if pre.exists() else None,
           "live": json.loads(live.read_text()) if live.exists() else None}
    if EDITION != "first":
        first_live = ROOT / "docs/results/feed_rule_live_rerun.json"
        out |= {"edition": EDITION, "first_validation": json.loads(first.read_text()) if first.exists() else None,
                "first_live": json.loads(first_live.read_text()) if first_live.exists() else None}
    return out


def live_feed(path: Path | None = None) -> dict | None:
    """The live discovery catalogue's new_candidate count: entries and distinct (TIC, period) signals. The S1c numbers
    describe the catalogue built under the old rule, kept as catalog_v1_fap200.json once the feed moved on."""
    if path is None:
        old = ROOT / "docs/discoveries/catalog_v1_fap200.json"
        path = old if old.exists() else ROOT / "docs/discoveries/catalog.json"
    if not path.exists():
        return None
    cat = json.loads(path.read_text())
    new = [c for c in cat.get("candidates", []) if c.get("status") == "new_candidate"]
    signals = {(c["tic"], round(c.get("period_days") or 0, 3)) for c in new}
    return {"source": str(path.relative_to(ROOT)), "updated": cat.get("updated"), "targets_reviewed": cat.get("targets_reviewed"),
            "new_candidate_entries": len(new), "new_signals": len(signals)}


# Why each threshold value changed after the sample was frozen (the re-run's audit): a pattern on the audit key, and
# the reason. Checked against the commits that set them; a changed value no pattern covers is reported as not explained.
AUDIT_REASONS = [
    (("configs/sweep.toml:", "configs/sweep_sentinels.toml:"),
     "the all-sky sweep's new configs",
     "New configs for the all-sky sweep (setuhq sweep), added after the freeze; the benchmark does not read them"),
    (("configs/discovery.toml:[search]fap_trials", "configs/discovery.toml:[search]fap_stop_after", "src/setuhq/discover.py:MAX_FEED_FAP",
      "src/setuhq/discover.py:TWO_SECTOR_PERIOD_TOL", "src/setuhq/discover.py:FAP"),
     "the feed's two-sector rule, pre-registered on the tuning half",
     "The discovery feed's two-sector rule, chosen on the tuning half only and pre-registered at 8909cda; this report's "
     "feed-level table keeps the frozen rule (FAP < 0.01 over 200 trials), and the new rule is measured separately below"),
    (("src/setuhq/vet.py:ODD_EVEN_FLOOR",), "the odd/even fix",
     "The odd/even fix (106c797): a 2% systematic floor on the odd/even depth errors, motivated by synthetic clean hot Jupiters and checked on pi Men c"),
    (("configs/default.toml:[vetting]", "src/setuhq/pipeline.py:TRANSIT_MASK_T14", "src/setuhq/pipeline.py:SCAN_KEYS"),
     "extended vetting, which only adds flags",
     "Extended (DV-style) and pixel-level vetting (bc43219, bd2dad4), which by default only add flags (decide = false); "
     "this report's scores read neither those flags nor the pixel tests, which are off"),
    (("configs/default.toml:[validation]", "src/setuhq/pipeline.py:DETREND_VARIANTS", "src/setuhq/pipeline.py:MIN_ANCHOR_SUPPORT"),
     "the reduced false-positive probability",
     "The reduced false-positive probability and its stability gate (0361a27, b0ab1c1), reported per candidate; this report's "
     "scores do not read it"),
    (("src/setuhq/reviewers/http.py:CREDENTIAL_PARAMS",), "a redaction list that is not a threshold",
     "Not a threshold: the list of URL parameters a Sentinel's error message redacts"),
]


def explain_audit(audit: dict) -> dict:
    groups, left = [], dict(audit["changed"])
    for prefixes, short, why in AUDIT_REASONS:
        keys = [k for k in list(left) if k.startswith(prefixes)]
        if keys:
            groups.append({"short": short, "why": why, "keys": keys})
            for k in keys:
                left.pop(k)
    return audit | {"explained": groups, "unexplained": left}


def against_first_run(results: list[dict], sample: dict, summary: dict) -> dict | None:
    """The re-run against the first run's committed report, measure by measure, paired on the same stars."""
    path = ROOT / "docs/results/benchmark_real_tois.json"
    if EDITION == "first" or not path.exists():
        return None
    first = json.loads(path.read_text())
    old = {r["toi"]: r for r in first["per_star"]}
    new = {r["toi"]: r for r in results}
    toi = {t["toi"]: t for t in sample["tois"]}
    held = [t for t in sample["tois"] if t["half"] == "held_out"]
    both = [t["toi"] for t in held if (old.get(t["toi"]) or {}).get("real") and (new.get(t["toi"]) or {}).get("real")]
    fh, nh = first["summary"]["held_out"], summary["held_out"]

    def paired(cls, test, where=lambda t: True):
        sel = [n for n in both if toi[n]["class"] == cls and where(toi[n])]
        return B.paired_change([test(old[n]) for n in sel], [test(new[n]) for n in sel])

    rec = lambda r: bool(r["real"]["recovered"])
    rows = [{"measure": "**Completeness: CP/KP recovered on searchable stars**", "first": fh["completeness"], "this": nh["completeness"],
             "paired": paired("positive", rec)},
            {"measure": "Completeness over all CP/KP stars", "first": fh["completeness_all_stars"], "this": nh["completeness_all_stars"]}]
    for fb, nb in zip(fh["completeness_by_radius"], nh["completeness_by_radius"]):
        a, b = fb["bin"]
        rows.append({"measure": f"… {a:g}–{b:g} R⊕", "first": fb, "this": nb,
                     "paired": paired("positive", rec, lambda t, a=a, b=b: t.get("radius_re") is not None and a <= t["radius_re"] < b)})
    for fb, nb in zip(fh["completeness_by_period"], nh["completeness_by_period"]):
        a, b = fb["bin"]
        rows.append({"measure": f"… {a:g}–{b:g} d", "first": fb, "this": nb,
                     "paired": paired("positive", rec, lambda t, a=a, b=b: a <= t["period"] < b)})
    rows += [{"measure": "FP TOIs whose dip the panel found", "first": fh["fp_seen"], "this": nh["fp_seen"],
              "paired": paired("fp", lambda r: bool(r["real"]["seen"]))},
             {"measure": "… of those, rejected or flagged binary-like", "first": fh["fp_flagged_of_seen"], "this": nh["fp_flagged_of_seen"]},
             {"measure": "FP TOIs whose dip passed vetting", "first": fh["fp_passed_unflagged"], "this": nh["fp_passed_unflagged"],
              "paired": paired("fp", rec)},
             {"measure": "CP/KP dips flagged binary-like", "first": fh["pos_flagged"], "this": nh["pos_flagged"]},
             {"measure": "FA TOIs whose dip the panel found", "first": fh["fa_seen"], "this": nh["fa_seen"],
              "paired": paired("fa", lambda r: bool(r["real"]["seen"]))}]
    for v in ("inverted", "scrambled"):
        any_fa = lambda r, v=v: bool((r.get(v) or {}).get("passed"))
        sel = [n for n in both if old[n].get(v) and new[n].get(v)]
        rows += [{"measure": f"{v.capitalize()} control: vetted false alarms per 1,000 star-sectors",
                  "first": fh["controls"][v]["per_1000_star_sectors"], "this": nh["controls"][v]["per_1000_star_sectors"]},
                 {"measure": f"{v.capitalize()} control: stars with any false alarm", "first": fh["controls"][v]["stars_with_any"],
                  "this": nh["controls"][v]["stars_with_any"],
                  "paired": B.paired_change([any_fa(old[n]) for n in sel], [any_fa(new[n]) for n in sel])}]
    for v in ("real", "inverted", "scrambled"):
        f1, f2 = (fh.get("feed") or {}).get(v), (nh.get("feed") or {}).get(v)
        if f1 and f2:
            rows.append({"measure": f"Feed level (frozen rule), {v} curves: distinct new signals per 1,000 star-sectors",
                         "first": f1["new_signals_per_1000"], "this": f2["new_signals_per_1000"]})
    fa_, na_ = first["summary"]["all"], summary["all"]
    allboth = [t["toi"] for t in sample["tois"] if t["class"] == "positive" and (old.get(t["toi"]) or {}).get("real")
               and (new.get(t["toi"]) or {}).get("real")]
    rows.append({"measure": "Whole sample (both halves): completeness", "first": fa_["completeness"], "this": na_["completeness"],
                 "paired": B.paired_change([rec(old[n]) for n in allboth], [rec(new[n]) for n in allboth])})
    # The stars the clipping bug exposed: what became of them.
    fc = first["clipping"]["held_out"]
    aff = [r for r in results if r.get("clip") and r["clip"]["affected"] and toi[r["toi"]]["half"] == "held_out"
           and toi[r["toi"]]["class"] == "positive" and (old.get(r["toi"]) or {}).get("real")]
    explained = fc.get("explained_tois") or []
    clip = {"n": len(aff), "first_recovered": sum(rec(old[r["toi"]]) for r in aff), "now_recovered": sum(rec(r) for r in aff),
            "first_median_removed": fc.get("median_removed_fraction_affected"), "first_explained": explained,
            "explained_now_recovered": [n for n in explained if (new.get(n) or {}).get("real") and rec(new[n])],
            "explained_still_missed": [n for n in explained if not ((new.get(n) or {}).get("real") and rec(new[n]))]}
    prov = first["code_provenance"]["commit"]
    return {"file": "docs/results/benchmark_real_tois.json", "code": ", ".join(f"commit {c}" for c in prov.values()),
            "stars_paired_held_out": len(both), "rows": rows, "clipping": clip, "why": why_changed(held, old, new),
            "note": why_note(why_changed(held, old, new))}


def why_changed(held: list[dict], old: dict, new: dict) -> dict:
    """Why the inverted control and the FP TOIs pass more often on the fixed code: each dip that passes vetting now
    and did not in the first run (matched by mid-time within 0.05 d), by what the first run did with it."""
    out = {"inverted": {"was_odd_even_rejected": 0, "new_deep_dip": 0, "other": 0, "no_longer_passing": 0}, "fp": {}}
    for t in held:
        a, b = (old.get(t["toi"]) or {}), (new.get(t["toi"]) or {})
        if not (a.get("real") and b.get("real")):
            continue
        clip = CLIP / f"{t['tic']}.json"
        scatter = json.loads(clip.read_text())["scatter_ppm"] if clip.exists() else None
        po, pn = FIRST_CACHE / str(t["tic"]) / "inverted" / "candidates.json", CACHE / str(t["tic"]) / "inverted" / "candidates.json"
        if po.exists() and pn.exists():
            co, cn = json.loads(po.read_text()), json.loads(pn.read_text())
            for c in cn:
                if not c["passed"]:
                    continue
                m = [x for x in co if abs(x["t_center"] - c["t_center"]) < 0.05]
                if m and m[0]["passed"]:
                    continue
                if m and "odd_even_mismatch" in (m[0]["flags"] or ""):
                    out["inverted"]["was_odd_even_rejected"] += 1
                elif not m and scatter and (c["depth_ppm"] or 0) > 10 * scatter:
                    out["inverted"]["new_deep_dip"] += 1
                else:
                    out["inverted"]["other"] += 1
            out["inverted"]["no_longer_passing"] += sum(1 for c in co if c["passed"] and not any(
                abs(x["t_center"] - c["t_center"]) < 0.05 and x["passed"] for x in cn))
        if t["class"] == "fp" and a["real"]["recovered"] != b["real"]["recovered"]:
            key = "gained" if b["real"]["recovered"] else "lost"
            out["fp"].setdefault(key, []).append({"toi": t["toi"], "first_run_flags": a["real"]["eb_flags"]})
    return out


def why_note(w: dict) -> str:
    inv, fp = w["inverted"], w["fp"]
    gained = fp.get("gained") or []
    oe = sum(1 for g in gained if "odd_even_mismatch" in g["first_run_flags"])
    return (f"Why the inverted control and the FP TOIs pass more often: of the dips on inverted curves that pass vetting now "
            f"and did not before, {inv['was_odd_even_rejected']} were rejected in the first run by the old odd/even test, "
            f"{inv['new_deep_dip']} are new dips deeper than 10× the point-to-point scatter (inverted bumps the old cleaning "
            f"deleted) and {inv['other']} are other; {inv['no_longer_passing']} that passed before no longer do. Of the "
            f"{len(gained)} FP TOIs whose dip now passes vetting, {oe} were rejected in the first run by the old odd/even "
            f"test; {len(fp.get('lost') or [])} FP TOI's dip no longer passes.")


STALE_HOURS = 12.0  # how far from a predicted epoch a missed TOI's dip may sit and still count as a stale-ephemeris case
STALE_DEPTH = 3.0   # the dip's depth (window or fitted, the larger) within this factor of the TOI's
STALE_SIGMA = 3.0   # and its offset at least this many sigma of the ephemeris error propagated to that epoch


def stale_ephemeris(results: list[dict], sample: dict) -> dict:
    """An audit, not a rule: CP/KP TOIs the benchmark counts as missed, with no dip at all on the published ephemeris
    (not "seen"), although a vetted dip of comparable depth sits near a predicted epoch, off it by more than
    match_toi's tolerance and by at least STALE_SIGMA sigma of the propagated ephemeris error, but within STALE_HOURS
    (and a quarter period), and matching no TOI of the star. Such a dip may be the TOI's own transit against a published ephemeris that has
    drifted; the frozen matching rule is not changed, so these stay misses."""
    from setuhq.discover import match_toi

    toi = {t["toi"]: t for t in sample["tois"]}
    rows = []
    for r in results:
        t = toi[r["toi"]]
        if t["class"] != "positive" or not r.get("real") or r["real"]["seen"] or not t.get("depth_ppm"):
            continue
        path = CACHE / str(r["tic"]) / "real" / "candidates.json"
        full = _target(r["tic"])
        t0, period = t["tranmid_bjd"] - 2457000.0, t["period"]
        best = None
        for c in json.loads(path.read_text()) if path.exists() else []:
            if not c["passed"] or match_toi(c, full):
                continue
            n = round((c["t_center"] - t0) / period)
            off = 24 * (c["t_center"] - (t0 + n * period))
            sigma_h = 24 * math.hypot(t.get("tranmid_err") or 0.0, n * (t.get("period_err") or 0.0))
            if abs(off) < STALE_SIGMA * sigma_h:
                continue
            ratio = max(c.get("depth_ppm") or 0, c.get("fit_depth_ppm") or 0) / t["depth_ppm"]
            if abs(off) <= min(STALE_HOURS, 6 * period) and 1 / STALE_DEPTH <= ratio <= STALE_DEPTH:
                if best is None or abs(off) < abs(best["offset_hours"]):
                    best = {"toi": t["toi"], "half": t["half"], "offset_hours": round(off, 1),
                            "offset_sigma": round(abs(off) / sigma_h, 1) if sigma_h else None, "depth_ratio": round(ratio, 2),
                            "dip_duration_hours": round(c["duration_hours"], 2), "toi_duration_hours": t["duration_hours"],
                            "dip_period_days": c.get("period_days") and round(c["period_days"], 4), "toi_period_days": period}
        if best:
            rows.append(best)
    rows.sort(key=lambda x: (x["half"] != "held_out", x["toi"]))
    return {"rule": (f"no dip lies on the published ephemeris but a vetted dip matching no TOI of the star, of depth within "
                     f"{STALE_DEPTH:g}x the TOI's (window or fitted depth, the larger), lies off the nearest predicted epoch by "
                     f"more than the matching tolerance and by at least {STALE_SIGMA:g} sigma of the propagated ephemeris error, "
                     f"but by at most {STALE_HOURS:g} h and a quarter period"),
            "held_out": sum(1 for x in rows if x["half"] == "held_out"), "all": len(rows), "stars": rows}


def cmd_report(args) -> int:
    sample = json.loads(SAMPLE.read_text())
    results = [json.loads((CACHE / f"{t['tic']}.json").read_text()) for t in sample["tois"] if (CACHE / f"{t['tic']}.json").exists()]
    tois = {t["tic"]: t for t in sample["tois"]}
    for r in results:
        # Score again from the stored candidates, so the current scoring rules apply to every star.
        for v in ("real", "inverted", "scrambled"):
            path = CACHE / str(r["tic"]) / v / "candidates.json"
            if r.get(v) and "error" not in r[v] and path.exists():
                cands = json.loads(path.read_text())
                r[v] = B.score_star(tois[r["tic"]], cands) if v == "real" else {"passed": sum(1 for c in cands if c["passed"]), "consensus": len(cands)}
        cpath = CLIP / f"{r['tic']}.json"
        if cpath.exists():
            r["clip"] = json.loads(cpath.read_text())
        fp = FEED / f"{r['tic']}.json"
        if fp.exists():
            r["feed"] = json.loads(fp.read_text())
    summary = B.summarise(results, sample)
    # The same numbers without the stars exposed to the preprocess clipping bug (depth/scatter > CLIP_RATIO).
    unaffected = [r for r in results if not (r.get("clip") or {}).get("affected")]
    summary_unaffected = B.summarise(unaffected, sample)
    # What the control false alarms are: dips on a periodic signal with at least two transits (the kind the
    # discovery feed could admit, before its FAP and depth rules) or single dips.
    toi_half = {t["tic"]: t["half"] for t in sample["tois"]}
    for half in ("held_out", "all"):
        for v in ("inverted", "scrambled"):
            kinds = {"periodic": 0, "single": 0}
            for r in results:
                if not r.get(v) or (half != "all" and toi_half.get(r["tic"]) != half):
                    continue
                path = CACHE / str(r["tic"]) / v / "candidates.json"
                for c in json.loads(path.read_text()) if path.exists() else []:
                    if c["passed"]:
                        kinds["periodic" if c.get("period_days") and (c.get("n_transits") or 0) >= 2 else "single"] += 1
            summary[half]["controls"][v]["kinds"] = kinds
    data = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sample": {k: sample[k] for k in ("source", "fetched_at", "seed", "rule", "counts", "sha256")},
            "panel": "the three Probes (deterministic detectors) with their frozen calibrated weights; sector-wide BLS; vetting; limb-darkened fit; the feed-level table adds the feed's FAP (200 trials)",
            "stars_run": len(results), "summary": summary, "loss": B.loss_table(results, sample),
            "clipping": B.clipping_summary(results, sample, CLIP_RATIO), "summary_unaffected": summary_unaffected, "sentinels": sentinel_scores(sample),
            "feed_implication": B.feed_implication(summary["held_out"], live_feed()),
            "feed_rule": feed_rule(),
            "code_commit": _git("rev-parse", "HEAD"), "code_provenance": (cp := code_provenance(results)),
            "threshold_audit": threshold_audit(_newest(list(cp["commit"].values()))),
            "per_star": [{k: r.get(k) for k in ("toi", "tic", "sector", "no_data", "real", "inverted", "scrambled")} for r in results]}
    if EDITION != "first":
        data = {"edition": EDITION, **data, "threshold_audit": explain_audit(data["threshold_audit"]),
                "stale_ephemeris": stale_ephemeris(results, sample),
                "against_first_run": against_first_run(results, sample, summary)}
    OUT_MD.with_suffix(".json").write_text(json.dumps(data, indent=1, default=float) + "\n")
    OUT_MD.write_text(B.to_markdown(data))
    print(OUT_MD.read_text())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--edition", choices=sorted(EDITIONS), default=None,
                    help="which run: 'first' (pre-fix code, the historical record) or 'clipfix' (the re-run on the fixed code)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--refresh", action="store_true")
    f.add_argument("--n-pos", type=int, default=300)
    f.add_argument("--n-fp", type=int, default=300)
    f.add_argument("--n-fa", type=int, default=100)
    f.set_defaults(func=cmd_freeze)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--retry-failed", action="store_true", help="run again the stars whose download or worker failed")
    r.set_defaults(func=cmd_run)
    rr = sub.add_parser("rerun", help="the frozen protocol again on the current code, from each star's recorded sector")
    rr.add_argument("--workers", type=int, default=4)
    rr.add_argument("--limit", type=int, default=0)
    rr.set_defaults(func=cmd_rerun)
    sc = sub.add_parser("sentinels-carry", help="the re-run's Sentinel answers: the first run's, where the subjects are byte-identical")
    sc.set_defaults(func=cmd_sentinels_carry)
    se = sub.add_parser("sentinels", help="the Sentinels on the stated 40-star subsample (cross-provider φ in 'report')")
    se.add_argument("--workers", type=int, default=2)
    se.add_argument("--panel", help="a run config whose [[reviewers]] Sentinels to run (any provider); default: the two "
                                    "Claude personas through the Claude Code CLI")
    se.set_defaults(func=cmd_sentinels)
    rs = sub.add_parser("rescore")
    rs.add_argument("--workers", type=int, default=4)
    rs.set_defaults(func=cmd_rescore)
    cl = sub.add_parser("clipping")
    cl.add_argument("--workers", type=int, default=2)
    cl.set_defaults(func=cmd_clipping)
    fe = sub.add_parser("feed")
    fe.add_argument("--workers", type=int, default=4)
    fe.set_defaults(func=cmd_feed)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = ap.parse_args(argv)
    if args.edition:
        set_edition(args.edition)
    return args.func(args)


def set_edition(edition: str) -> None:
    """Point every path at one edition's cache and report (worker processes inherit it through the environment)."""
    global EDITION, CACHE, OUT_MD, CLIP, FEED
    os.environ["SETUHQ_BENCH_EDITION"] = edition
    EDITION = edition
    CACHE, OUT_MD = _edition_paths(edition)
    CLIP, FEED = CACHE / "clip", CACHE / "feed"


if __name__ == "__main__":
    raise SystemExit(main())

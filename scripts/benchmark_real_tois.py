#!/usr/bin/env python3
"""S1c: run the blind benchmark on real TOIs (src/exoplan/benchmark_toi.py explains the design).

    python scripts/benchmark_real_tois.py freeze            # TOI table → docs/results/benchmark_toi_sample.json
    python scripts/benchmark_real_tois.py run --workers 4   # SPOC light curves (cache/mast) → cache/bench/<tic>.json
    python scripts/benchmark_real_tois.py report            # → docs/results/benchmark_real_tois.{md,json}

Downloads and per-star outputs stay in the gitignored ``cache/``; only the frozen sample and the summary are
committed. A star with no SPOC 2-minute light curve is recorded as "no data", never dropped silently.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exoplan import benchmark_toi as B  # noqa: E402

SAMPLE = ROOT / "docs/results/benchmark_toi_sample.json"
OUT_MD = ROOT / "docs/results/benchmark_real_tois.md"
CACHE = ROOT / "cache/bench"
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
CODE_FILES = ["src/exoplan/discover.py"] + [
    f"src/exoplan/{m}.py" for m in ("aggregate", "config", "lightcurve", "loaders", "pipeline", "preprocess", "search",
                                     "subjects", "transitfit", "vet", "reviewers/base", "reviewers/simulated")]


def _code_bytes(f: str, rev: str | None) -> bytes:
    return (ROOT / f).read_bytes() if rev is None else _git("show", f"{rev}:{f}").encode() + b"\n"


def code_fingerprint(rev: str | None = None) -> str:
    """sha256 of CODE_FILES, as in the working tree (None) or at a commit."""
    import hashlib

    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(f.encode() + b"\0" + _code_bytes(f, rev) + b"\0")
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
    from exoplan.config import RunConfig

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
    from exoplan.loaders import load_tess
    from exoplan.pipeline import run_pipeline
    from exoplan.reviewers.simulated import SimulatedVolunteer

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
    lc = lcs[0]
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
            run_pipeline(cfg, [curve], reviewers, run_dir, weights=weights, weights_source="calibrated Probe weights")
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


def load_cached(tic: int, sector: int):
    """The star's SPOC 2-minute light curve from the download cache (cache/mast), with no network call: the same
    steps as exoplan.loaders.load_tess after its download (quality == 0 and finite points, median-normalised)."""
    import lightkurve as lk
    import numpy as np

    from exoplan.lightcurve import LightCurve
    from exoplan.loaders import _file_provenance, _plain

    files = [f for f in sorted((ROOT / "cache/mast/mastDownload/TESS").glob(f"tess*-s{sector:04d}-{tic:016d}-*-s/*_lc.fits")) if f.stat().st_size]  # an interrupted download is empty
    if not files:  # downloaded before the cache directory was set: fetch it into cache/mast
        from exoplan.loaders import load_tess

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
    classifications (exoplan.pipeline.rebuild_run: the reviewers are not asked again), and score them again."""
    from dataclasses import replace

    from exoplan.pipeline import rebuild_run

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

    from exoplan.pipeline import run_pipeline
    from exoplan.reviewers.simulated import SimulatedVolunteer

    stellar = (run_dir / "stellar.json").read_text() if (run_dir / "stellar.json").exists() else None
    shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    if stellar:
        (run_dir / "stellar.json").write_text(stellar)
    reviewers = [SimulatedVolunteer(rid, snr_threshold=snr, miss_probability=miss, seed=seed) for rid, snr, miss, seed, _ in PROBES]
    run_pipeline(cfg, [curve], reviewers, run_dir, weights={rid: w for rid, *_, w in PROBES}, weights_source="calibrated Probe weights")
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

    from exoplan.preprocess import clean, diff_sigma

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
FEED_FAP_TRIALS = 200  # as configs/discovery.toml


def feed_eligible(c: dict) -> bool:
    """The discovery feed's admission rule before its FAP test (discover.run_discovery): passed vetting, not
    off_ephemeris, at most MAX_FEED_DEPTH_PPM deep, on a periodic signal with at least MIN_FEED_TRANSITS transits."""
    from exoplan import discover as Dv

    return (bool(c["passed"]) and "off_ephemeris" not in (c.get("flags") or "") and (c.get("depth_ppm") or 0) <= Dv.MAX_FEED_DEPTH_PPM
            and c.get("period_days") is not None and (c.get("n_transits") or 0) >= Dv.MIN_FEED_TRANSITS)


def _target(tic: int):
    """The star's TOIs from the cached TOI table, as discover.Target, so a real dip is classed known_toi or new_candidate."""
    from exoplan import discover as Dv

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

    from exoplan import discover as Dv
    from exoplan.pipeline import run_pipeline
    from exoplan.reviewers.simulated import SimulatedVolunteer

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
                if feed_eligible(c) and Dv.admits_fap(c.get("fap")):
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


def cmd_sentinels(args) -> int:
    """Both Sentinels (one Claude model, two personas) on the stated subsample's real light curves, subject by
    subject, through the Claude Code CLI; responses cached in cache/claude-code."""
    import numpy as np

    from exoplan.reviewers.claude_code import ClaudeCodeReviewer
    from exoplan.subjects import Subject

    sample = json.loads(SAMPLE.read_text())
    done = {t["tic"]: json.loads((CACHE / f"{t['tic']}.json").read_text()) for t in sample["tois"] if (CACHE / f"{t['tic']}.json").exists()}
    sub = sentinel_subsample(sample, done)
    reviewers = [ClaudeCodeReviewer(reviewer_id=f"claude-{p}", persona=p, cache_dir=str(ROOT / "cache/claude-code")) for p in ("volunteer", "skeptic")]
    if not all(r.available() for r in reviewers):
        print("The Claude Code CLI is not available here; the Sentinels were not run.")
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
        t, subj, png, shared = job
        r = ClaudeCodeReviewer(reviewer_id=shared.reviewer_id, persona=shared.persona, cache_dir=shared.cache_dir)  # one per thread
        try:
            c = r.review(subj, png)
            return t["toi"], r.reviewer_id, subj.subject_id, {"label": c.label, "reason": c.reason, "marks": [[m.t_start, m.t_end] for m in c.marks],
                                                              "model": r.last_model, "called_at": r.last_called_at}
        except Exception as exc:  # noqa: BLE001
            return t["toi"], r.reviewer_id, subj.subject_id, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    from concurrent.futures import ThreadPoolExecutor

    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (toi, rid, sid, res) in enumerate(pool.map(one, jobs), 1):
            results.setdefault(toi, {}).setdefault(rid, {})[sid] = res
            if i % 10 == 0:
                print(f"{i}/{len(jobs)}", flush=True)
    (CACHE / "sentinels.json").write_text(json.dumps({"subsample": [t["toi"] for t in sub], "results": results}, indent=1))
    return 0


def sentinel_scores(sample: dict) -> dict | None:
    """Per persona: on CP/KP stars, did it mark a dip on the TOI's ephemeris; on FP stars, did it pass the TOI's
    dip as a potential planet. And how often the two personas agree (they share one model, so they correlate)."""
    path = CACHE / "sentinels.json"
    if not path.exists():
        return None
    from exoplan.discover import match_toi

    data = json.loads(path.read_text())
    toi = {t["toi"]: t for t in sample["tois"]}
    rows = {}
    for name, per in data["results"].items():
        t = toi[name]
        target = B.target_for(t)
        for rid, subs in per.items():
            ok = [s for s in subs.values() if "error" not in s]
            hit = any(match_toi({"t_center": 0.5 * (a + b), "duration_hours": (b - a) * 24, "period_days": None, "time_unit": "BTJD"}, target)
                      for s in ok if s["label"] == "potential_planet" for a, b in s["marks"])
            rows.setdefault(name, {})[rid] = {"hit": hit, "errors": len(subs) - len(ok)}
    from collections import Counter

    models = Counter(s.get("model") or "not recorded" for per in data["results"].values() for subs in per.values() for s in subs.values())
    out = {"subsample": data["subsample"], "n_stars": len(rows), "personas": {}, "models": dict(models),
           "model_note": ("the model id the Claude Code CLI reported for each review (its modelUsage), with the call date; "
                          "\"not recorded\" for reviews answered before exoplan stored it (the cache key holds only \"default\")")}
    for rid in ("claude-volunteer", "claude-skeptic"):
        pos = [{"x": r[rid]["hit"]} for n, r in rows.items() if rid in r and toi[n]["class"] == "positive"]
        fp = [{"x": r[rid]["hit"]} for n, r in rows.items() if rid in r and toi[n]["class"] == "fp"]
        out["personas"][rid] = {"cp_kp_marked": B.rates(pos, "x"), "fp_marked_as_planet": B.rates(fp, "x"),
                                "errors": sum(r[rid]["errors"] for r in rows.values() if rid in r)}
    both = [(r["claude-volunteer"]["hit"], r["claude-skeptic"]["hit"]) for r in rows.values() if len(r) == 2]
    agree = sum(1 for a, b in both if a == b)
    n11 = sum(1 for a, b in both if a and b); n00 = sum(1 for a, b in both if not a and not b)
    n10 = sum(1 for a, b in both if a and not b); n01 = sum(1 for a, b in both if not a and b)
    den = ((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)) ** 0.5
    out["agreement"] = {"n": len(both), "agree": agree, "phi": (n11 * n00 - n10 * n01) / den if den else None}
    return out


def _git(*args) -> str:
    import subprocess

    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


FROZEN_AFTER = "fbc1ed9"  # the last commit before the sample was frozen (2026-10-19T11:00:16Z); its thresholds were set without TOI data
THRESHOLD_PATHS = ["configs", "docs/results/reviewer_weights.json", "docs/results/reviewer_weights_full_panel.json"] + [
    f"src/exoplan/{m}.py" for m in ("aggregate", "config", "discover", "pipeline", "preprocess", "search", "subjects", "transitfit", "vet")
] + ["src/exoplan/reviewers"]


def _threshold_values(rev: str | None) -> dict[str, str]:
    """Every threshold-like value in THRESHOLD_PATHS at a revision (None: the working tree): module-level
    UPPER_CASE constants in the Python files, and every key = value line in the config files and weights files."""
    import re

    files = []
    for path in THRESHOLD_PATHS:
        listed = _git("ls-tree", "-r", "--name-only", rev or "HEAD", "--", path).splitlines()
        files += [f for f in listed if f.endswith((".py", ".toml", ".json"))]
    out = {}
    for f in sorted(set(files)):
        text = _git("show", f"{rev}:{f}") if rev else ((ROOT / f).read_text() if (ROOT / f).exists() else "")
        if f.endswith(".py"):
            for m in re.finditer(r"^([A-Z][A-Z0-9_]+)\s*=\s*(.+?)\s*(?:#.*)?$", text, re.M):
                out[f"{f}:{m.group(1)}"] = m.group(2)
        elif f.endswith(".toml"):
            section = ""
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                if line.startswith("["):
                    section = line
                elif "=" in line:
                    k, v = (x.strip() for x in line.split("=", 1))
                    out[f"{f}:{section}{k}"] = v
        else:
            try:
                for k, v in json.loads(text).items():
                    out[f"{f}:{k}"] = json.dumps(v)
            except (ValueError, AttributeError):
                pass
    return out


# Values that decide nothing: where caches go, the cache key's version, and the floor below which the indicative
# Gumbel tail is not printed (no rule reads the tail).
NOT_THRESHOLDS = ("fap_cache", "FAP_CACHE_VERSION", "FAP_TAIL_FLOOR")


def threshold_audit(rev: str | None = None) -> dict:
    """Did any threshold value change after the sample was frozen? (Then the held-out half could have chosen it.)
    Compares the values themselves, so a comment, a refactor or a bug fix that keeps every threshold is not counted;
    the commits since the freeze are listed so a reader can check them."""
    # Compared with the code that produced the results (``rev``), not with whatever the tree holds now: a threshold
    # changed later (the pre-registered feed rule) did not shape these numbers.
    before, now = _threshold_values(FROZEN_AFTER), _threshold_values(rev)
    diff = {k: [before.get(k), now.get(k)] for k in sorted(set(before) | set(now)) if before.get(k) != now.get(k)}
    changed = {k: v for k, v in diff.items() if not any(x in k for x in NOT_THRESHOLDS)}
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
    """The pre-registered two-sector rule's held-out evaluation and the live feed re-run, when they exist."""
    v = ROOT / "docs/results/feed_rule_validation.json"
    if not v.exists():
        return None
    pre = ROOT / "docs/results/feed_rule_preregistration.json"
    live = ROOT / "docs/results/feed_rule_live_rerun.json"
    return {"validation": json.loads(v.read_text()), "preregistration": json.loads(pre.read_text()) if pre.exists() else None,
            "live": json.loads(live.read_text()) if live.exists() else None}


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
            "panel": "the three Probes (deterministic detectors) with their calibrated weights; sector-wide BLS; vetting; limb-darkened fit; the feed-level table adds the feed's FAP (200 trials)",
            "stars_run": len(results), "summary": summary, "loss": B.loss_table(results, sample),
            "clipping": B.clipping_summary(results, sample, CLIP_RATIO), "summary_unaffected": summary_unaffected, "sentinels": sentinel_scores(sample),
            "feed_implication": B.feed_implication(summary["held_out"], live_feed()),
            "feed_rule": feed_rule(),
            "code_commit": _git("rev-parse", "HEAD"), "code_provenance": (cp := code_provenance(results)),
            "threshold_audit": threshold_audit(_newest(list(cp["commit"].values()))),
            "per_star": [{k: r.get(k) for k in ("toi", "tic", "sector", "no_data", "real", "inverted", "scrambled")} for r in results]}
    OUT_MD.with_suffix(".json").write_text(json.dumps(data, indent=1, default=float) + "\n")
    OUT_MD.write_text(B.to_markdown(data))
    print(OUT_MD.read_text())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
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
    se = sub.add_parser("sentinels")
    se.add_argument("--workers", type=int, default=2)
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
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

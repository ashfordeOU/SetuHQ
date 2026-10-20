#!/usr/bin/env python3
"""The discovery feed's admission rule, old and new, measured on the real-TOI benchmark sample.

The S1c benchmark (scripts/benchmark_real_tois.py) found that noise alone passes the feed's rule about as often as
the live feed reports "new" signals. The proposed fix: a signal must be found independently in both sectors the feed
reviews, and its FAP must pass a 0.001 cut over 2,000 block-bootstrap trials. This script measures both rules on the
same runs, with the discovery config itself (subject-mode BLS, the Probes, the feed's weights file), on each star's
first two SPOC 2-minute sectors and on the same two controls per sector (flux-inverted; block-scrambled with every
known TOI masked first).

    python scripts/feed_rule_eval.py run --workers 3        # pipeline on both sectors x 3 curves -> cache/feedrule
    python scripts/feed_rule_eval.py tune                   # choose the two-sector rule on the tuning half only
                                                            # (trials run lazily, cached in cache/feedrule/trials)
    python scripts/feed_rule_eval.py evaluate               # once, on the held-out half, with the pre-registered rule

``tune`` writes docs/results/feed_rule_preregistration.json; it is committed before ``evaluate`` runs, and
``evaluate`` refuses to run unless that file is committed (its commit hash is recorded with the results).
"""

from __future__ import annotations

import argparse
import itertools
import json
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark_real_tois as BR  # noqa: E402
from exoplan import benchmark_toi as B  # noqa: E402
from exoplan import discover as Dv  # noqa: E402

CACHE = ROOT / "cache/feedrule"
PREREG = ROOT / "docs/results/feed_rule_preregistration.json"
RESULTS = ROOT / "docs/results/feed_rule_validation.json"
VARIANTS = ("real", "inverted", "scrambled")
OLD = {"trials": 200, "cut": 0.01}
NEW = {"trials": 2000, "cut": 0.001}
# The grid the tuning half chooses from: the period agreement between the two sectors' signals, and whether their
# depths must agree within a factor. The FAP part is fixed by the proposal (2,000 trials, 0.001).
GRID = {"period_tol": (0.005, 0.01, 0.02), "depth_factor": (None, 2.0), "aliases": (False, True)}
NOISE_TARGET_PER_100 = 1.0  # the tuning objective: most completeness among rules at or under this noise rate


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def discovery_config():
    from dataclasses import replace

    from exoplan.config import load_config

    cfg = load_config(ROOT / "configs/discovery.toml")
    return replace(cfg, fap_trials=0, fap_cache=None, fit_transits=False, stellar="none")


def probes(cfg):
    from exoplan.reviewers.simulated import SimulatedVolunteer

    return [SimulatedVolunteer(r["id"], snr_threshold=r.get("snr_threshold", 5.0), miss_probability=r.get("miss_probability", 0.1),
                               seed=r.get("seed", 0)) for r in cfg.reviewers if r.get("type") == "simulated"]


def curves_for(tic: int, sectors: list[int]) -> dict[str, list]:
    lcs = [BR.load_cached(tic, s) for s in sectors]
    eph = BR._ephemerides(tic)
    return {"real": lcs, "inverted": [B.inverted(lc) for lc in lcs],
            "scrambled": [B.scrambled(lc, seed=(tic * 100 + s) % (2**31), ephemerides=eph) for lc, s in zip(lcs, sectors)]}


def run_star(toi: dict) -> dict:
    """First two SPOC 2-minute sectors of one star; the discovery pipeline (no FAP yet) on each of the 3 curves."""
    import lightkurve as lk

    from exoplan.pipeline import run_pipeline

    tic = toi["tic"]
    out = {"tic": tic, "toi": toi["toi"]}
    try:
        search = lk.search_lightcurve(f"TIC {tic}", author="SPOC", exptime=120)
        sectors = sorted({int(s) for s in search.table["sequence_number"]}) if len(search) else []
    except Exception as exc:  # noqa: BLE001
        return dict(out, error=f"search failed: {type(exc).__name__}: {str(exc)[:200]}")
    out["sectors"] = sectors[:2]
    out["n_sectors_available"] = len(sectors)
    if not sectors:
        return dict(out, no_data=True)
    try:
        curves = curves_for(tic, out["sectors"])
    except Exception as exc:  # noqa: BLE001
        return dict(out, error=f"download failed: {type(exc).__name__}: {str(exc)[:200]}")
    cfg = discovery_config()
    weights = json.loads((ROOT / "docs/results/reviewer_weights.json").read_text())
    for name, cs in curves.items():
        run_dir = CACHE / str(tic) / name
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            run_pipeline(cfg, cs, probes(cfg), run_dir, weights=weights, weights_source="docs/results/reviewer_weights.json")
        except Exception:  # noqa: BLE001
            out[name] = {"error": traceback.format_exc(limit=2)[-400:]}
            continue
        out[name] = {"candidates": len(json.loads((run_dir / "candidates.json").read_text()))}
    return out


def cmd_run(args) -> int:
    sample = json.loads(BR.SAMPLE.read_text())
    have = {t["tic"] for t in sample["tois"] if (BR.CACHE / f"{t['tic']}.json").exists()
            and json.loads((BR.CACHE / f"{t['tic']}.json").read_text()).get("real")}
    CACHE.mkdir(parents=True, exist_ok=True)
    todo = [t for t in sample["tois"] if t["tic"] in have and not (CACHE / f"{t['tic']}.json").exists()]
    print(f"{len(todo)} stars to run", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_star, t): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            t = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"tic": t["tic"], "toi": t["toi"], "error": f"worker failed: {exc}"}
            if "error" not in res:  # a failure is retried by the next run
                (CACHE / f"{t['tic']}.json").write_text(json.dumps(res))
            else:
                print(f"TIC {t['tic']}: {res['error'][:120]}", flush=True)
            if i % 10 == 0:
                print(f"{i}/{len(todo)} in {time.time() - t0:.0f} s", flush=True)
    return 0


# ---------- the rules ----------

def rows(tic: int, variant: str) -> list[dict]:
    path = CACHE / str(tic) / variant / "candidates.json"
    return json.loads(path.read_text()) if path.exists() else []


def partners(c: dict, rs: list[dict], rule: dict) -> list[dict]:
    """Feed-eligible dips in the other reviewed sector whose signal has the same period (or, with ``aliases``, half
    or twice it), within ``period_tol``, and with ``depth_factor`` a depth within that factor."""
    ratios = (0.5, 1.0, 2.0) if rule.get("aliases") else (1.0,)
    out = []
    for r in rs:
        if r is c or r.get("sector") == c.get("sector") or not BR.feed_eligible(r):
            continue
        if not any(abs(r["period_days"] - q * c["period_days"]) <= rule["period_tol"] * q * c["period_days"] for q in ratios):
            continue
        f = rule.get("depth_factor")
        if f and not (1 / f <= (r["depth_ppm"] or 0) / max(c["depth_ppm"] or 1e-9, 1e-9) <= f):
            continue
        out.append(r)
    return out


class Trials:
    """The feed's block-bootstrap trials for one star's subject signals, extended lazily and cached on disk: the first
    n trials of a longer run are an n-trial run (same seeds, same order), so the old rule's 200 and the new rule's
    2,000 share them. A run stops as soon as 2 trials reach the signal's SNR: both cuts need k <= 1."""

    def __init__(self, tic: int, sectors: list[int]):
        self.tic, self.sectors = tic, sectors
        self.dir = CACHE / "trials" / str(tic)
        self._subjects = None
        self.cfg = discovery_config()

    def _subject(self, variant: str, sid: str):
        if self._subjects is None:
            from exoplan.pipeline import prepare_subjects

            curves = curves_for(self.tic, self.sectors)
            self._subjects = {v: {s.subject_id: s for s in prepare_subjects(curves[v], self.cfg)} for v in VARIANTS}
        return self._subjects[variant].get(sid)

    def passes(self, variant: str, sid: str, n: int, cut: float) -> bool:
        import hashlib

        from exoplan.search import _null_maxima, bls_search, fap_inputs, fap_seeds

        path = self.dir / f"{variant}_{sid}.json"
        st = json.loads(path.read_text()) if path.exists() else None
        if st is None:
            subj = self._subject(variant, sid)
            sig = bls_search(subj, min_period=self.cfg.min_period) if subj is not None else None
            st = {"snr": float(sig.snr) if sig is not None else None, "null": []}
        if st["snr"] is None:
            return False
        while len(st["null"]) < n and sum(1 for x in st["null"] if x >= st["snr"]) < 2:
            subj = self._subject(variant, sid)
            sig = bls_search(subj, min_period=self.cfg.min_period)
            residual, blocks = fap_inputs(subj, sig)
            seed = int(hashlib.sha256(subj.subject_id.encode()).hexdigest()[:8], 16)  # as exoplan.search.with_fap
            seeds = fap_seeds(seed, n)[len(st["null"]):len(st["null"]) + 100]
            from exoplan.search import DEFAULT_DURATIONS_DAYS

            st["null"] += _null_maxima((subj.time, residual, subj.flux_err, blocks, seeds, self.cfg.min_period, None,
                                        DEFAULT_DURATIONS_DAYS, subj.subject_id, subj.mission, subj.time_unit))
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(st))
        if not path.exists():
            self.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(st))
        head = st["null"][:n]
        k = sum(1 for x in head if x >= st["snr"])
        return len(head) == n and (k + 1) / (n + 1) < cut


def admitted(tr: Trials, variant: str, rule: dict, rs: list[dict], c: dict) -> bool:
    if not BR.feed_eligible(c):
        return False
    if rule["name"] == "old":
        return tr.passes(variant, c["subject_id"], OLD["trials"], OLD["cut"])
    return bool(partners(c, rs, rule)) and tr.passes(variant, c["subject_id"], NEW["trials"], NEW["cut"])


def _cand(c: dict) -> dict:
    return {"t_center": c["t_center"], "time_unit": c.get("time_unit", "BTJD"), "duration_hours": c["duration_hours"],
            "period_days": c["period_days"]}


def score_star(t: dict, rules: list[dict]) -> dict | None:
    """One star under each rule: is its TOI admitted on the ephemeris; how many distinct new (no-TOI) signals the real
    curve admits; how many distinct signals each control admits. Trials run only as far as each answer needs."""
    path = CACHE / f"{t['tic']}.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text())
    if not res.get("sectors"):
        return None
    tr = Trials(t["tic"], res["sectors"])
    target, full = B.target_for(t), BR._target(t["tic"])
    out = {"tic": t["tic"], "class": t["class"], "two_sectors": len(res["sectors"]) == 2}
    real = rows(t["tic"], "real")
    ordered = sorted(real, key=lambda c: -(c.get("snr") or 0))
    for i, rule in enumerate(rules):
        on = any(admitted(tr, "real", rule, real, c) for c in ordered if Dv.match_toi(_cand(c), target))
        new = {round(c["period_days"], 3) for c in ordered if not Dv.match_toi(_cand(c), full) and admitted(tr, "real", rule, real, c)}
        noise = {}
        for v in ("inverted", "scrambled"):
            rs = rows(t["tic"], v)
            noise[v] = len({round(c["period_days"], 3) for c in rs if admitted(tr, v, rule, rs, c)})
        out[str(i)] = {"on": on, "new": len(new), "noise": noise}
    return out


def score_half(half: str, rules: list[dict], workers: int) -> list[dict]:
    """Every star of a half scored under ``rules``. Each star's result is stored as it finishes (keyed by the rules),
    so a restart resumes where it stopped; the scoring itself is unchanged."""
    import hashlib

    tois = half_tois(half)
    rkey = hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:12]
    store = CACHE / "scored" / rkey
    store.mkdir(parents=True, exist_ok=True)
    out = []
    for t in tois:
        f = store / f"{t['tic']}.json"
        if f.exists():
            r = json.loads(f.read_text())
            if r:
                out.append(r)
    todo = [t for t in tois if not (store / f"{t['tic']}.json").exists()]
    print(f"{len(tois) - len(todo)} stars already scored, {len(todo)} to go", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(score_star, t, rules): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                r = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"TIC {futures[fut]['tic']}: {type(exc).__name__}: {exc}", flush=True)
                continue
            (store / f"{futures[fut]['tic']}.json").write_text(json.dumps(r))
            if r:
                out.append(r)
            if i % 20 == 0:
                print(f"{i}/{len(todo)} in {time.time() - t0:.0f} s", flush=True)
    return out


def summarise_rule(stars: list[dict], i: int) -> dict:
    pos = [s for s in stars if s["class"] == "positive"]
    fp = [s for s in stars if s["class"] == "fp"]
    n = len(stars)
    noise = {v: sum(s[str(i)]["noise"][v] for s in stars) for v in ("inverted", "scrambled")}
    worse = max(noise.values())
    _, lo, hi = B.wilson(min(worse, n), n)
    return {"targets": n, "two_sector_targets": sum(s["two_sectors"] for s in stars),
            "completeness": B.rates([{"x": s[str(i)]["on"]} for s in pos], "x"),
            "fp_rejected": B.rates([{"x": not s[str(i)]["on"]} for s in fp], "x"),
            "real_new_per_100": 100 * sum(s[str(i)]["new"] for s in stars) / n if n else None,
            "noise_counts": noise, "noise_per_100": {v: 100 * k / n for v, k in noise.items()} if n else None,
            "noise_worse_per_100": 100 * worse / n if n else None,
            "noise_worse_ci_per_100": [100 * lo, 100 * hi] if n else None}


def half_tois(half: str) -> list[dict]:
    return [t for t in json.loads(BR.SAMPLE.read_text())["tois"] if t["half"] == half]


def grid_rules() -> list[dict]:
    return [{"name": "two_sector", "period_tol": tol, "depth_factor": dep, "aliases": al}
            for tol, dep, al in itertools.product(GRID["period_tol"], GRID["depth_factor"], GRID["aliases"])]


def cmd_tune(args) -> int:
    rules = [{"name": "old"}] + grid_rules()
    stars = score_half("tuning", rules, args.workers)
    old = summarise_rule(stars, 0)
    trials = [{"rule": r, "tuning": summarise_rule(stars, i)} for i, r in enumerate(rules) if i]
    ok = [r for r in trials if r["tuning"]["noise_worse_per_100"] <= NOISE_TARGET_PER_100]
    if ok:
        chosen = max(ok, key=lambda r: (r["tuning"]["completeness"]["rate"] or 0, -r["rule"]["period_tol"],
                                        r["rule"]["depth_factor"] is not None, not r["rule"]["aliases"]))
    else:
        chosen = min(trials, key=lambda r: (r["tuning"]["noise_worse_per_100"], -(r["tuning"]["completeness"]["rate"] or 0)))
    prereg = {"written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "code_commit": _git("rev-parse", "HEAD"),
              "objective": (f"Among the grid's rules whose worse control gives at most {NOISE_TARGET_PER_100:g} false signals per "
                            "100 targets on the tuning half, the one with the highest tuning completeness (ties: the tighter period "
                            "tolerance, then the depth check, then no aliases); if none meets it, the lowest noise."),
              "grid": GRID, "fap": NEW, "old_rule": {"fap": OLD, "tuning": old}, "trials": trials,
              "chosen": chosen["rule"], "chosen_tuning": chosen["tuning"], "met_noise_target": bool(ok),
              "held_out_plan": ("Evaluated once on the held-out half: completeness, FP rejection and false signals per 100 targets "
                                "on both controls, old rule against the chosen rule. The fix is claimed only if the worse control's "
                                "held-out noise rate under the chosen rule is below the old rule's with non-overlapping Wilson 95% "
                                "intervals; otherwise the report says it is not shown to work.")}
    PREREG.write_text(json.dumps(prereg, indent=1) + "\n")
    print(json.dumps({"chosen": chosen, "old": old, "met_noise_target": bool(ok)}, indent=1))
    return 0


def cmd_evaluate(args) -> int:
    rel = str(PREREG.relative_to(ROOT))
    if _git("status", "--porcelain", "--", rel) or not _git("log", "-1", "--format=%h", "--", rel):
        print("The pre-registration must be committed, unchanged, before the held-out evaluation.")
        return 1
    if RESULTS.exists() and not args.again:
        print(f"{RESULTS} exists: the held-out evaluation runs once.")
        return 1
    prereg = json.loads(PREREG.read_text())
    stars = score_half("held_out", [{"name": "old"}, prereg["chosen"]], args.workers)
    old, new = summarise_rule(stars, 0), summarise_rule(stars, 1)
    clearly = new["noise_worse_ci_per_100"][1] < old["noise_worse_ci_per_100"][0]

    def shaped(r):
        star_sectors = 2 * r["two_sector_targets"] + (r["targets"] - r["two_sector_targets"])
        return {"targets": r["targets"], "star_sectors": star_sectors,
                "inverted": {"new_signals": r["noise_counts"]["inverted"], "new_signals_per_1000": 1000 * r["noise_counts"]["inverted"] / star_sectors},
                "scrambled": {"new_signals": r["noise_counts"]["scrambled"], "new_signals_per_1000": 1000 * r["noise_counts"]["scrambled"] / star_sectors},
                "completeness": r["completeness"], "fp_rejected": r["fp_rejected"],
                "expected_false_per_100_targets": r["noise_worse_per_100"], "expected_false_ci_per_100_targets": r["noise_worse_ci_per_100"],
                "real_new_per_100_targets": r["real_new_per_100"]}
    out = {"rule": prereg["chosen"] | {"fap_trials": NEW["trials"], "fap_cut": NEW["cut"]},
           "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "preregistration_commit": _git("log", "-1", "--format=%H", "--", rel), "code_commit": _git("rev-parse", "HEAD"),
           "held_out": shaped(new), "held_out_old_rule": shaped(old) | {"rule": {"name": "old"} | {"fap_trials": OLD["trials"], "fap_cut": OLD["cut"]}},
           "fix_clearly_lowers_noise": clearly,
           "notes": ["Each star's first two SPOC 2-minute sectors (the live feed reviews the latest two); a star with one sector "
                     "cannot pass the two-sector rule and counts as one target.",
                     "Discovery config: subject-mode BLS, the three Probes with the feed's weights file. Fit and TIC stellar "
                     "parameters off, because admission never reads them; docs/results/feed_rule_stellar_check.json shows "
                     "identical admission inputs with them on, on a seeded 20-star subsample.",
                     "A worker restart stopped the first held-out run at 120 of 345 stars before it wrote anything; the "
                     "script then gained a per-star store so the run resumes (the rule and the scoring are unchanged), "
                     "and the run was restarted. The trials already computed were reused from their cache."]}
    RESULTS.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


STELLAR_CHECK = ROOT / "docs/results/feed_rule_stellar_check.json"


def check_star(t: dict) -> dict:
    """One star's real curves through the exact discovery config (limb-darkened fit on, TIC stellar parameters) and
    through the evaluation's config (fit off): are the feed-admission inputs of every dip the same?"""
    from exoplan.config import load_config
    from exoplan.pipeline import run_pipeline

    res = json.loads((CACHE / f"{t['tic']}.json").read_text())
    curves = curves_for(t["tic"], res["sectors"])["real"]
    full = load_config(ROOT / "configs/discovery.toml")
    from dataclasses import replace

    full = replace(full, fap_trials=0, fap_cache=None)
    run_dir = CACHE / "stellar_check" / str(t["tic"])
    run_dir.mkdir(parents=True, exist_ok=True)
    weights = json.loads((ROOT / "docs/results/reviewer_weights.json").read_text())
    run_pipeline(full, curves, probes(full), run_dir, weights=weights)
    a = json.loads((run_dir / "candidates.json").read_text())
    b = rows(t["tic"], "real")
    key = lambda c: (c["subject_id"], round(c["t_start"], 6), BR.feed_eligible(c), round(c["depth_ppm"], 3),
                     c.get("period_days") and round(c["period_days"], 6), c.get("n_transits"))
    star = json.loads((run_dir / "stellar.json").read_text()) if (run_dir / "stellar.json").exists() else {}
    fits = [c.get("fit") or {} for c in a]
    return {"tic": t["tic"], "same_admission_inputs": sorted(map(key, a)) == sorted(map(key, b)), "dips": len(a),
            "tic_teff": next(iter(star.values()), {}).get("teff") if star else None,
            "fits": sum(1 for f in fits if f), "density_flags": sum(1 for c in a if "density_mismatch" in (c.get("flags") or "")),
            "v_shape_flags": sum(1 for c in a if "v_shape" in (c.get("flags") or ""))}


def cmd_check_stellar(args) -> int:
    """A stated, seeded subsample (20 tuning-half stars with two sectors): the evaluation runs without the fit and
    without TIC parameters because the feed's admission never reads them (passed, off_ephemeris, the window depth,
    the period and transit count, the FAP); this check shows the inputs are identical with them."""
    import numpy as np

    pool = [t for t in half_tois("tuning") if (CACHE / f"{t['tic']}.json").exists()
            and len(json.loads((CACHE / f"{t['tic']}.json").read_text()).get("sectors") or []) == 2]
    pool.sort(key=lambda t: t["toi"])
    pick = [pool[i] for i in sorted(np.random.default_rng(json.loads(BR.SAMPLE.read_text())["seed"] + 2).permutation(len(pool))[:20])]
    out = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(check_star, pick):
            out.append(r)
            print(r, flush=True)
    STELLAR_CHECK.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                         "stars": out, "all_same": all(r["same_admission_inputs"] for r in out)}, indent=1) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=3)
    r.set_defaults(func=cmd_run)
    cs = sub.add_parser("check-stellar")
    cs.add_argument("--workers", type=int, default=2)
    cs.set_defaults(func=cmd_check_stellar)
    tu = sub.add_parser("tune")
    tu.add_argument("--workers", type=int, default=4)
    tu.set_defaults(func=cmd_tune)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--workers", type=int, default=4)
    ev.add_argument("--again", action="store_true", help="re-run after a crash; the rule cannot change (it is committed)")
    ev.set_defaults(func=cmd_evaluate)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

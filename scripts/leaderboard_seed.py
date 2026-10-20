#!/usr/bin/env python3
"""Seed the real-TOI leaderboard with exoplan's own configurations, from stored results only.

    python scripts/leaderboard_seed.py --cache /path/to/cache/bench
    # writes docs/leaderboard/{tuning_inputs.json, submissions/*.json}

Nothing is re-run. A submission lists detected events, and the leaderboard does the scoring, so the entries are
built from the benchmark's stored per-star outputs (the gitignored ``cache/bench``):

* the Probes: every consensus event of the real, inverted and scrambled runs (``<tic>/<curve>/candidates.json``:
  mid-time, duration, BLS period, whether it passed vetting, and its flags);
* each Sentinel persona: every mark it made on the real light curve (``sentinels.json``), as an event that passed
  when the persona labelled the subject a potential planet. The Sentinels were never run on the controls.

Before writing, the script scores the entries with the leaderboard and checks that the outcomes equal the per-star
rows committed in docs/results/benchmark_real_tois.json (Probes) and the committed per-persona totals and agreement
(Sentinels); it stops if anything differs. The Probes + Sentinels combinations are derived by the leaderboard
itself (``leaderboard.DERIVED``). Once written, the submissions are committed, so scoring needs no cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exoplan import leaderboard as L  # noqa: E402
from exoplan.benchmark_toi import rates  # noqa: E402

PERSONAS = ("claude-volunteer", "claude-skeptic")
ATTRIBUTION = "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors."


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _event(c: dict) -> dict:
    flags = c["flags"].split(";") if isinstance(c["flags"], str) else list(c["flags"] or [])
    e = {"t_center": round(float(c["t_center"]), 6), "duration_hours": round(float(c["duration_hours"]), 6),
         "period_days": round(float(c["period_days"]), 8) if c.get("period_days") else None,
         "passed": bool(c["passed"]), "flags": [f for f in flags if f]}
    if c.get("snr") is not None:
        e["snr"] = round(float(c["snr"]), 4)
    return e


def probe_predictions(cache: Path, benchmark: dict, tois: list[str]) -> tuple[list[dict], list[str]]:
    by = {r["toi"]: r for r in benchmark["per_star"]}
    preds, files = [], []
    for name in tois:
        r = by[name]
        if not r.get("real"):
            preds.append({"toi": name, "tic": r["tic"], "searched": False, "events": [], "controls": None})
            continue
        ev = {}
        for v in ("real", "inverted", "scrambled"):
            path = cache / str(r["tic"]) / v / "candidates.json"
            ev[v] = [_event(c) for c in json.loads(path.read_text())]
            files.append(path)
        preds.append({"toi": name, "tic": r["tic"], "searched": True, "events": ev["real"],
                      "controls": {"inverted": ev["inverted"], "scrambled": ev["scrambled"]}})
    digest = hashlib.sha256(b"".join(_sha(p).encode() for p in files)).hexdigest()
    return preds, [digest, str(len(files))]


def sentinel_predictions(cache: dict, sample: dict, tois: list[str]) -> dict[str, list[dict]]:
    tic = {t["toi"]: t["tic"] for t in sample["tois"]}
    out = {p: [] for p in PERSONAS}
    for name in tois:
        for p in PERSONAS:
            events = []
            for s in cache["results"][name][p].values():
                if "error" in s:
                    continue
                for a, b in s["marks"]:
                    events.append({"t_center": round(0.5 * (a + b), 6), "duration_hours": round((b - a) * 24, 6),
                                   "period_days": None, "passed": s["label"] == "potential_planet", "flags": []})
            out[p].append({"toi": name, "tic": tic[name], "searched": True, "events": events, "controls": None})
    return out


def check(subs: dict, sample: dict, benchmark: dict) -> None:
    """The leaderboard's own outcomes must reproduce the committed benchmark numbers, or nothing is written."""
    per = {r["toi"]: r for r in benchmark["per_star"]}
    rows = L.outcomes(subs["probes"], sample)
    for row in rows:
        r = per[row["toi"]]
        if not r.get("real"):
            continue
        want = (r["real"]["seen"], r["real"]["recovered"], r["real"]["flagged"], r["inverted"]["passed"], r["scrambled"]["passed"])
        got = (row["seen"], row["recovered"], row["flagged"], row["controls"]["inverted"], row["controls"]["scrambled"])
        if want != got:
            raise SystemExit(f"TOI {row['toi']}: the events give {got}, the committed per-star row {want}. Not writing.")
    cls = {t["toi"]: t["class"] for t in sample["tois"]}
    committed = benchmark["sentinels"]["personas"]
    srows = {}
    for p in PERSONAS:
        if p not in subs:
            return
        srows[p] = L.outcomes(subs[p], sample)
        pos = rates([{"x": r["recovered"]} for r in srows[p] if cls[r["toi"]] == "positive"], "x")
        fp = rates([{"x": r["recovered"]} for r in srows[p] if cls[r["toi"]] == "fp"], "x")
        if (pos["k"], pos["n"], fp["k"], fp["n"]) != (committed[p]["cp_kp_marked"]["k"], committed[p]["cp_kp_marked"]["n"],
                                                      committed[p]["fp_marked_as_planet"]["k"], committed[p]["fp_marked_as_planet"]["n"]):
            raise SystemExit(f"{p}: events give CP/KP {pos['k']}/{pos['n']}, FP {fp['k']}/{fp['n']}; the committed report "
                             "says otherwise. Not writing.")
    a = benchmark["sentinels"]["agreement"]
    agree = sum(x["recovered"] == y["recovered"] for x, y in zip(*(srows[p] for p in PERSONAS)))
    if (agree, len(srows[PERSONAS[0]])) != (a["agree"], a["n"]):
        raise SystemExit(f"Sentinel agreement {agree} differs from the committed {a['agree']}/{a['n']}. Not writing.")


def submission(sid, name, kind, scope, method, preds, sources, benchmark, inputs_hash, sample) -> dict:
    prov = benchmark["code_provenance"]
    ta = benchmark["threshold_audit"]
    return {"format": L.FORMAT, "id": sid, "name": name, "kind": kind, "submitter": "exoplan (seeded entry)",
            "sample_sha256": sample["sha256"], "inputs_sha256": inputs_hash, "tuned_on": "none", "scope": scope,
            "provenance": {
                "method": method + " " + ATTRIBUTION,
                "code_version": (f"benchmark report from commit {benchmark['code_commit'][:7]}; pipeline code fingerprints "
                                 + ", ".join(f"{fp} = commit {c}" for fp, c in prov["commit"].items())),
                "generated_from": sources,
                "tuning": (f"none: no threshold changed after the sample was frozen (threshold audit: {ta['values_checked']} "
                           f"values, frozen after {ta['frozen_after']}, clean = {ta['clean']})"),
                "seeded_by": "scripts/leaderboard_seed.py"},
            "predictions": preds}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", type=Path, default=ROOT / "cache/bench",
                    help="the benchmark's per-star outputs (cache/bench), with sentinels.json")
    args = ap.parse_args(argv)
    if not args.cache.exists():
        raise SystemExit(f"{args.cache} not found: the committed submissions are kept as they are.")
    sample = L.load_sample()
    benchmark = json.loads(L.BENCHMARK.read_text())
    inputs_hash = L.write_inputs(sample)
    held, sub40 = L.scope_tois(sample, "held_out"), L.sentinel_subsample(benchmark)
    bsrc = {"file": "docs/results/benchmark_real_tois.json", "sha256": _sha(L.BENCHMARK), "rows": "per_star (checked)"}
    pmethod = ("The three Probes (Sensitive, Typical, Cautious) with their calibrated weights, sector-wide BLS, "
               "light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the "
               "benchmark report; every consensus event on the real and control curves. No FAP rule.")
    preds, (digest, nfiles) = probe_predictions(args.cache, benchmark, held)
    csrc = {"file": "cache/bench/<tic>/{real,inverted,scrambled}/candidates.json (gitignored)",
            "sha256": digest, "rows": f"{nfiles} files; sha256 over their sha256s in sample order"}
    subs = {"probes": submission("probes", "Probes only", "probes", "held_out", pmethod, preds, [csrc, bsrc], benchmark,
                                 inputs_hash, sample)}
    keep = set(sub40)
    subs["probes-subsample"] = submission(
        "probes-subsample", "Probes only", "probes", "sentinel_subsample",
        pmethod + " Restricted to the Sentinels' 40-star subsample, to compare like with like.",
        sorted([p for p in preds if p["toi"] in keep], key=lambda p: sub40.index(p["toi"])), [csrc, bsrc], benchmark,
        inputs_hash, sample)
    spath = args.cache / "sentinels.json"
    if spath.exists():
        cache = json.loads(spath.read_text())
        if cache["subsample"] != sub40:
            raise SystemExit("the Sentinel cache's subsample is not the committed one. Not writing.")
        ssrc = {"file": "cache/bench/sentinels.json (gitignored)", "sha256": _sha(spath),
                "rows": "per star and subject: the persona's label and marks"}
        sp = sentinel_predictions(cache, sample, sub40)
        for p, label in (("claude-volunteer", "Sentinel · Volunteer alone"), ("claude-skeptic", "Sentinel · Skeptic alone")):
            subs[p] = submission(p, label, "sentinel", "sentinel_subsample",
                                 f"One Sentinel persona ({p.split('-')[1]}) through the Claude Code CLI on every 13-day subject "
                                 "of the star's real light curve; each mark is an event, passed when the persona called the "
                                 "subject a potential planet. Not run on the controls.", sp[p], [ssrc, bsrc], benchmark,
                                 inputs_hash, sample)
    else:
        print(f"{spath} not found: the committed Sentinel submissions are kept as they are.")
    check(subs, sample, benchmark)
    for old in ("probes-or-sentinel", "probes-and-sentinel"):  # now derived by the leaderboard
        (L.SUBMISSIONS / f"{old}.json").unlink(missing_ok=True)
    for s in subs.values():
        (L.SUBMISSIONS / f"{s['id']}.json").write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"wrote docs/leaderboard/submissions/{s['id']}.json ({len(s['predictions'])} stars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

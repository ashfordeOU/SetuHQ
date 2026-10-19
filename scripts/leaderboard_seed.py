#!/usr/bin/env python3
"""Seed the real-TOI leaderboard with exoplan's own configurations, from stored per-star results only.

    python scripts/leaderboard_seed.py            # writes docs/leaderboard/{tuning_inputs.json,submissions/*.json}
    python scripts/leaderboard_seed.py --sentinels /path/to/cache/bench/sentinels.json

Nothing is re-run. The entries are built from:

* the Probes: the per-star rows committed in docs/results/benchmark_real_tois.json (``per_star``);
* the Sentinels: the stored Claude Code CLI responses of the benchmark's Sentinel step (cache/bench/sentinels.json,
  gitignored), scored per star exactly as scripts/benchmark_real_tois.py scores them. The script checks that its
  per-persona totals equal the totals committed in the benchmark report, and stops if they do not. Once written,
  the Sentinel submissions are committed, so the leaderboard needs no cache. Without the cache the committed
  Sentinel submissions are kept as they are.

Two Probes+Sentinels combinations are stated here, before scoring, as star-level rules on the stored outcomes
(not a run of the full panel's mark-level consensus, which would need the pipeline again):

* ``probes-or-sentinel``: a clean candidate when the Probes give one or either Sentinel marks the TOI's dip as a
  potential planet (the Sentinels as extra detectors);
* ``probes-and-sentinel``: a clean candidate only when the Probes give one and either Sentinel marks it too (the
  Sentinels as a check).
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
from exoplan.benchmark_toi import rates, target_for  # noqa: E402

PERSONAS = ("claude-volunteer", "claude-skeptic")
ATTRIBUTION = "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors."


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return "cache/bench/sentinels.json (gitignored)" if path.name == "sentinels.json" else path.name


def probe_rows(benchmark: dict, tois: list[str]) -> list[dict]:
    """Per-star outcomes of the Probes panel, from the committed per-star rows."""
    by = {r["toi"]: r for r in benchmark["per_star"]}
    out = []
    for name in tois:
        r = by[name]
        real = r.get("real")
        if not real:
            out.append({"toi": name, "tic": r["tic"], "searched": False, "seen": False, "recovered": False, "flagged": False,
                        "controls": None})
            continue
        out.append({"toi": name, "tic": r["tic"], "searched": True, "seen": bool(real["seen"]),
                    "recovered": bool(real["recovered"]), "flagged": bool(real["flagged"]),
                    "controls": {v: (r[v] or {}).get("passed") for v in ("inverted", "scrambled")}})
    return out


def sentinel_rows(cache: dict, sample: dict, tois: list[str]) -> dict[str, list[dict]]:
    """Per persona and star: seen (a mark on the TOI's ephemeris, any label), recovered (a mark there with the
    label potential_planet: the benchmark report's 'marked'), flagged (seen but not called a planet)."""
    from exoplan.discover import match_toi

    toi = {t["toi"]: t for t in sample["tois"]}
    out = {p: [] for p in PERSONAS}
    for name in tois:
        target = target_for(toi[name])
        for p in PERSONAS:
            subs = cache["results"][name][p]
            ok = [s for s in subs.values() if "error" not in s]
            on = lambda s: any(match_toi({"t_center": 0.5 * (a + b), "duration_hours": (b - a) * 24, "period_days": None,  # noqa: E731
                                          "time_unit": "BTJD"}, target) for a, b in s["marks"])
            seen = any(on(s) for s in ok)
            hit = any(on(s) for s in ok if s["label"] == "potential_planet")
            out[p].append({"toi": name, "tic": toi[name]["tic"], "searched": True, "seen": seen, "recovered": hit,
                           "flagged": seen and not hit, "controls": None, "errors": len(subs) - len(ok)})
    return out


def check_sentinels(rows: dict[str, list[dict]], benchmark: dict, sample: dict) -> None:
    """The per-star Sentinel outcomes must give the benchmark report's committed per-persona totals."""
    cls = {t["toi"]: t["class"] for t in sample["tois"]}
    committed = benchmark["sentinels"]["personas"]
    for p, rs in rows.items():
        pos = rates([{"x": r["recovered"]} for r in rs if cls[r["toi"]] == "positive"], "x")
        fp = rates([{"x": r["recovered"]} for r in rs if cls[r["toi"]] == "fp"], "x")
        if (pos["k"], pos["n"]) != (committed[p]["cp_kp_marked"]["k"], committed[p]["cp_kp_marked"]["n"]) or \
                (fp["k"], fp["n"]) != (committed[p]["fp_marked_as_planet"]["k"], committed[p]["fp_marked_as_planet"]["n"]):
            raise SystemExit(f"{p}: per-star outcomes give CP/KP {pos['k']}/{pos['n']}, FP {fp['k']}/{fp['n']}; the committed "
                             "benchmark report says otherwise. Not writing.")
    a = benchmark["sentinels"]["agreement"]
    both = list(zip(rows[PERSONAS[0]], rows[PERSONAS[1]]))
    agree = sum(x["recovered"] == y["recovered"] for x, y in both)
    if (agree, len(both)) != (a["agree"], a["n"]):
        raise SystemExit(f"Sentinel agreement {agree}/{len(both)} differs from the committed {a['agree']}/{a['n']}. Not writing.")


def combine(probes: list[dict], sentinels: dict[str, list[dict]], rule: str) -> list[dict]:
    out = []
    for i, pr in enumerate(probes):
        se = [sentinels[p][i] for p in PERSONAS]
        s_hit = any(s["recovered"] for s in se)
        p_clean = pr["recovered"] and not pr["flagged"]
        seen = pr["seen"] or any(s["seen"] for s in se)
        if rule == "or":
            recovered, clean = pr["recovered"] or s_hit, p_clean or s_hit
        else:
            recovered, clean = pr["recovered"] and s_hit, p_clean and s_hit
        out.append({"toi": pr["toi"], "tic": pr["tic"], "searched": pr["searched"], "seen": seen, "recovered": recovered,
                    "flagged": seen and not clean, "controls": None})
    return out


def submission(sid: str, name: str, kind: str, scope: str, method: str, preds: list[dict], sources: list[dict],
               benchmark: dict, inputs_hash: str, sample: dict) -> dict:
    prov = benchmark["code_provenance"]
    return {"format": L.FORMAT, "id": sid, "name": name, "kind": kind, "submitter": "exoplan (seeded entry)",
            "sample_sha256": sample["sha256"], "inputs_sha256": inputs_hash, "tuned_on": "none", "scope": scope,
            "provenance": {
                "method": method + " " + ATTRIBUTION,
                "code_version": (f"benchmark report from commit {benchmark['code_commit'][:7]}; pipeline code fingerprints "
                                 + ", ".join(f"{fp} = commit {c}" for fp, c in prov["commit"].items())),
                "generated_from": sources,
                "tuning": ("none: no threshold changed after the sample was frozen (threshold audit in "
                           f"docs/results/benchmark_real_tois.json: {benchmark['threshold_audit']['values_checked']} values, "
                           f"frozen after {benchmark['threshold_audit']['frozen_after']}, clean = {benchmark['threshold_audit']['clean']})"),
                "seeded_by": "scripts/leaderboard_seed.py"},
            "predictions": [{k: v for k, v in p.items() if k != "errors"} for p in preds]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sentinels", type=Path, default=ROOT / "cache/bench/sentinels.json",
                    help="the benchmark's stored Sentinel responses (cache/bench/sentinels.json)")
    args = ap.parse_args(argv)
    sample = L.load_sample()
    benchmark = json.loads(L.BENCHMARK.read_text())
    inputs_hash = L.write_inputs(sample)
    L.SUBMISSIONS.mkdir(parents=True, exist_ok=True)
    bsrc = {"file": "docs/results/benchmark_real_tois.json", "sha256": _sha(L.BENCHMARK), "rows": "per_star"}
    held = L.scope_tois(sample, "held_out")
    sub40 = L.sentinel_subsample(benchmark)
    probe_method = ("The three Probes (Sensitive, Typical, Cautious) with their calibrated weights, sector-wide BLS, "
                    "light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the "
                    "benchmark report. No FAP rule.")
    subs = [submission("probes", "Probes only", "probes", "held_out", probe_method, probe_rows(benchmark, held), [bsrc],
                       benchmark, inputs_hash, sample),
            submission("probes-subsample", "Probes only", "probes", "sentinel_subsample", probe_method + " Restricted to the "
                       "Sentinels' 40-star subsample, so the rows below compare like with like.", probe_rows(benchmark, sub40),
                       [bsrc], benchmark, inputs_hash, sample)]
    if args.sentinels.exists():
        cache = json.loads(args.sentinels.read_text())
        if cache["subsample"] != sub40:
            raise SystemExit("the Sentinel cache's subsample is not the committed one. Not writing.")
        srows = sentinel_rows(cache, sample, sub40)
        check_sentinels(srows, benchmark, sample)
        ssrc = {"file": _rel(args.sentinels), "sha256": _sha(args.sentinels),
                "rows": "per star and subject: the persona's label and marks"}
        for p, label in (("claude-volunteer", "Sentinel · Volunteer alone"), ("claude-skeptic", "Sentinel · Skeptic alone")):
            subs.append(submission(p, label, "sentinel", "sentinel_subsample",
                                   f"One Sentinel persona ({p.split('-')[1]}) through the Claude Code CLI on every 13-day "
                                   "subject of the star's real light curve. Recovered: it marked a dip on the TOI's ephemeris "
                                   "as a potential planet; flagged: it marked one there but called the subject noise. Not run "
                                   "on the controls.", srows[p], [bsrc, ssrc], benchmark, inputs_hash, sample))
        prs = probe_rows(benchmark, sub40)
        subs.append(submission("probes-or-sentinel", "Probes + Sentinels (either)", "combined", "sentinel_subsample",
                               "Star-level rule stated before scoring: a clean candidate when the Probes give one or either "
                               "Sentinel marks the TOI's dip as a potential planet. Not a run of the panel's mark-level "
                               "consensus. Controls not measured (the Sentinels never saw them).",
                               combine(prs, srows, "or"), [bsrc, ssrc], benchmark, inputs_hash, sample))
        subs.append(submission("probes-and-sentinel", "Probes + Sentinels (both)", "combined", "sentinel_subsample",
                               "Star-level rule stated before scoring: a clean candidate only when the Probes give one and "
                               "either Sentinel also marks the TOI's dip as a potential planet. Not a run of the panel's "
                               "mark-level consensus. Controls not measured (the Sentinels never saw them).",
                               combine(prs, srows, "and"), [bsrc, ssrc], benchmark, inputs_hash, sample))
    else:
        print(f"{args.sentinels} not found: the committed Sentinel submissions are kept as they are.")
    for s in subs:
        (L.SUBMISSIONS / f"{s['id']}.json").write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote docs/leaderboard/submissions/{s['id']}.json ({len(s['predictions'])} stars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

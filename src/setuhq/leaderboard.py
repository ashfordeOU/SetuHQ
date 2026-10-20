# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The public leaderboard on the frozen real-TOI benchmark (S5; the benchmark itself is S1c, benchmark_toi.py).

A **submission** is one JSON file: a method's detected events, per held-out star of the frozen sample
(``docs/results/benchmark_toi_sample.json``), on the real light curve and on its two controls, with provenance.
The leaderboard does the scoring itself: it decides whether an event lies on the TOI's ephemeris with the
benchmark's own ``score_star`` (``discover.match_toi``), and counts the control false alarms from the event lists.
A submitter states only what its method saw and what its own vetting passed.

The format (``exoplan-leaderboard/2``)::

    {"format": "exoplan-leaderboard/2", "id": "probes", "name": "Probes only",
     "sample_sha256": "<the frozen sample's hash>",
     "inputs_sha256": "<the canonical hash of docs/leaderboard/tuning_inputs.json>",
     "tuned_on": "none" | "tuning",
     "scope": "held_out" | "sentinel_subsample",
     "provenance": {"method": "...", "code_version": "...", "generated_from": [...]},
     "predictions": [{"toi": "1201.01", "tic": 12345, "searched": true,
                      "events": [{"t_center": 1325.50, "duration_hours": 3.0, "period_days": 6.27,
                                  "passed": true, "flags": []}],
                      "controls": {"inverted": [<events>], "scrambled": [<events>]}}, ...]}

Times are BTJD. ``passed`` is the method's own vetting verdict and ``flags`` its own reasons, from a fixed
vocabulary (``FLAGS``); every other field is whitelisted, so a label or a label proxy (radius, depth,
disposition) cannot ride along.

**Ranking.** Held-out entries are ranked by Youden's J (Youden 1950) with a square-and-add Wilson interval
(Newcombe 1998), on the searchable set the benchmark fixed (stars with a SPOC 2-minute light curve), with one
predicate on both sides: a *clean candidate* (an on-ephemeris event that passed, with no eclipsing-binary flag).
J = clean CP/KP share + not-clean FP share − 1, so calling every TOI a planet, flagged or not, scores J = 0, and
calling a star "not searched" counts it as not offered. J over every star of the scope is reported beside it. An
entry without control lists for every searched star is listed but not ranked; the controls gate ranking and do not
enter J. The Sentinels' 40-star subsample is never ranked: its intervals are too wide to order anything.

**Labels.** The public inputs (``docs/leaderboard/tuning_inputs.json``) hold the tuning half with its
dispositions and, for the held-out half, only TIC, TOI name and ephemeris. A submission states the hash of the
inputs it was built from and is refused for any other hash, for ``tuned_on`` other than none or tuning, for a field
outside the whitelist, or for not covering exactly the stars of its scope. The hash is an attestation, not a proof:
the held-out labels are public in the repository.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from setuhq.benchmark_toi import RADIUS_BINS, score_star, wilson

ROOT = Path(__file__).resolve().parents[2]
# Format names keep their exoplan- prefix from before the rename to SetuHQ: they name a schema version, and the
# committed records, submissions and catalogues carry them.
FORMAT = "exoplan-leaderboard/2"
INPUTS_FORMAT = "exoplan-leaderboard-inputs/1"
SAMPLE = ROOT / "docs/results/benchmark_toi_sample.json"
BENCHMARK = ROOT / "docs/results/benchmark_real_tois.json"
LB_DIR = ROOT / "docs/leaderboard"
INPUTS = LB_DIR / "tuning_inputs.json"
SUBMISSIONS = LB_DIR / "submissions"
RESULTS = LB_DIR / "leaderboard.json"
RESULTS_MD = LB_DIR / "leaderboard.md"

# What a blind search of a held-out star may know: where to look and when the published transits are.
HELD_OUT_PUBLIC = ("tic", "toi", "half", "period", "period_err", "tranmid_bjd", "tranmid_err", "duration_hours")
# Whitelists: nothing else may appear in a submission, a prediction or an event.
SUBMISSION_KEYS = frozenset({"format", "id", "name", "kind", "submitter", "sample_sha256", "inputs_sha256", "tuned_on",
                             "scope", "provenance", "predictions"})
PREDICTION_KEYS = frozenset({"toi", "tic", "searched", "events", "controls"})
EVENT_KEYS = frozenset({"t_center", "duration_hours", "period_days", "passed", "flags", "snr"})
PROVENANCE_KEYS = ("method", "code_version", "generated_from")
# The vetting vocabulary (vet.py, pipeline.py, transitfit.py): an event's flags must come from it.
FLAGS = frozenset({"low_snr", "too_short", "edge_event", "insufficient_points", "odd_even_mismatch", "secondary_eclipse",
                   "off_ephemeris", "v_shape", "density_mismatch"})
MAX_EVENTS = 500  # per light curve
SCOPES = ("held_out", "sentinel_subsample")
TUNED_ON = ("none", "tuning")
LABELISH = ("class", "disposition", "tfop", "label", "truth", "radius", "depth", "cp_kp", "is_planet")


def canonical_sha256(obj) -> str:
    """sha256 of the object's canonical JSON (sorted keys, no whitespace): the same bytes on every machine."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def load_sample(path: str | Path = SAMPLE) -> dict:
    return json.loads(Path(path).read_text())


def public_inputs(sample: dict) -> dict:
    """The inputs a submission may be built from: the tuning half in full, the held-out half without labels."""
    return {"format": INPUTS_FORMAT, "sample_sha256": sample["sha256"],
            **{k: sample[k] for k in ("source", "fetched_at", "seed", "rule")},
            "note": ("Tuning half: every field, dispositions included. Held-out half: only what a blind search needs "
                     "(TIC, TOI name, ephemeris); no disposition, class, depth or radius."),
            "tuning": [t for t in sample["tois"] if t["half"] == "tuning"],
            "held_out": [{k: t.get(k) for k in HELD_OUT_PUBLIC} for t in sample["tois"] if t["half"] == "held_out"]}


def inputs_sha256(inputs: dict) -> str:
    return canonical_sha256(inputs)


def full_sample_sha256(sample: dict) -> str:
    """The canonical hash of the whole sample file, held-out labels included: a submission stating it is refused."""
    return canonical_sha256(sample)


def sentinel_subsample(benchmark: dict) -> list[str]:
    """The Sentinels' stated subsample of held-out TOIs, as the benchmark report recorded it."""
    return list((benchmark.get("sentinels") or {}).get("subsample") or [])


def scope_tois(sample: dict, scope: str, benchmark: dict | None = None) -> list[str]:
    if scope == "held_out":
        return [t["toi"] for t in sample["tois"] if t["half"] == "held_out"]
    if scope == "sentinel_subsample":
        return sentinel_subsample(benchmark or {})
    raise ValueError(scope)


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _event_errors(events, where: str) -> list[str]:
    if not isinstance(events, list):
        return [f"{where}: events must be a list"]
    if len(events) > MAX_EVENTS:
        return [f"{where}: more than {MAX_EVENTS} events"]
    why = []
    for i, e in enumerate(events):
        w = f"{where} event {i}"
        if not isinstance(e, dict):
            why.append(f"{w}: must be an object")
            continue
        extra = sorted(set(e) - EVENT_KEYS)
        if extra:
            why.append(f"{w}: fields outside the whitelist ({', '.join(map(str, extra))})")
        if not _finite(e.get("t_center")):
            why.append(f"{w}: t_center (BTJD) must be a number")
        if not _finite(e.get("duration_hours")) or e["duration_hours"] <= 0:
            why.append(f"{w}: duration_hours must be a positive number")
        p = e.get("period_days")
        if p is not None and (not _finite(p) or p <= 0):
            why.append(f"{w}: period_days must be a positive number or null")
        if not isinstance(e.get("passed"), bool):
            why.append(f"{w}: passed must be true or false")
        fl = e.get("flags", [])
        if not isinstance(fl, list) or any(f not in FLAGS for f in fl):
            why.append(f"{w}: flags must be a list from {sorted(FLAGS)}")
        if "snr" in e and e["snr"] is not None and not _finite(e["snr"]):
            why.append(f"{w}: snr must be a number")
    return why


def validate(sub, sample: dict, inputs: dict, benchmark: dict | None = None) -> list[str]:
    """Every reason to refuse this submission (an empty list: accepted)."""
    if not isinstance(sub, dict):
        return ["a submission must be a JSON object"]
    why = []
    extra = sorted(set(sub) - SUBMISSION_KEYS)
    if extra:
        why.append(f"fields outside the whitelist ({', '.join(map(str, extra))})")
    if sub.get("format") != FORMAT:
        why.append(f"format must be {FORMAT!r}" + (": version 1 trusted self-reported outcomes and is retired"
                                                     if sub.get("format") == "exoplan-leaderboard/1" else ""))
    if sub.get("sample_sha256") != sample["sha256"]:
        why.append(f"sample_sha256 must be the frozen sample's hash {sample['sha256']}")
    stated = sub.get("inputs_sha256")
    raw = hashlib.sha256(SAMPLE.read_bytes()).hexdigest() if SAMPLE.exists() else None
    if stated in (full_sample_sha256(sample), sample["sha256"], raw):
        why.append("inputs_sha256 is a hash of the full sample, which holds the held-out labels: built with held-out labels")
    elif stated != inputs_sha256(inputs):
        why.append(f"inputs_sha256 must be the hash of the public tuning-half-only inputs ({inputs_sha256(inputs)})")
    if sub.get("tuned_on") not in TUNED_ON:
        why.append(f"tuned_on must be one of {TUNED_ON} (tuned on {sub.get('tuned_on')!r} touches held-out labels)"
                   if sub.get("tuned_on") in ("held_out", "all", "both") else f"tuned_on must be one of {TUNED_ON}")
    prov = sub.get("provenance")
    if not isinstance(prov, dict) or any(not prov.get(k) for k in PROVENANCE_KEYS):
        why.append(f"provenance must state {', '.join(PROVENANCE_KEYS)}")
    elif any(k.lower() in LABELISH for k in prov):
        why.append("provenance carries a label field")
    for k in ("id", "name"):
        if not isinstance(sub.get(k), str) or not sub.get(k):
            why.append(f"{k} must be a non-empty string")
    scope = sub.get("scope")
    if scope not in SCOPES:
        why.append(f"scope must be one of {SCOPES}")
        return why
    want = scope_tois(sample, scope, benchmark)
    if not want:
        why.append(f"scope {scope!r} has no stated stars")
        return why
    tic_of = {t["toi"]: t["tic"] for t in sample["tois"]}
    half_of = {t["toi"]: t["half"] for t in sample["tois"]}
    preds = sub.get("predictions")
    if not isinstance(preds, list):
        why.append("predictions must be a list")
        return why
    if not all(isinstance(p, dict) for p in preds):
        why.append("every prediction must be an object")
        return why
    names = [p.get("toi") for p in preds]
    dup = sorted({str(n) for n in names if names.count(n) > 1})
    if dup:
        why.append(f"duplicate predictions for TOI {', '.join(dup[:5])}")
    tuning = sorted(str(n) for n in set(names) if half_of.get(n) == "tuning")
    if tuning:
        why.append(f"predictions include {len(tuning)} tuning-half stars; submit the stars of the scope only")
    outside = sorted(str(n) for n in set(names) - set(want) - set(tuning))
    if outside:
        why.append(f"predictions for {len(outside)} TOIs outside the scope ({', '.join(outside[:5])})")
    absent = sorted(set(want) - set(names))
    if absent:
        why.append(f"no prediction for {len(absent)} stars of the scope ({', '.join(absent[:5])}); a star not searched is "
                   "submitted with searched: false, never left out")
    for p in preds:
        n = p.get("toi")
        extra = sorted(set(p) - PREDICTION_KEYS)
        if extra:
            why.append(f"TOI {n}: fields outside the whitelist ({', '.join(map(str, extra))})")
        if n in tic_of and p.get("tic") != tic_of[n]:
            why.append(f"TOI {n}: tic {p.get('tic')} is not the sample's {tic_of[n]}")
        if not isinstance(p.get("searched"), bool):
            why.append(f"TOI {n}: searched must be true or false")
            continue
        ctl = p.get("controls")
        if not p["searched"]:
            if p.get("events") or ctl:
                why.append(f"TOI {n}: a star not searched has no events and no controls")
            continue
        why += _event_errors(p.get("events"), f"TOI {n}")
        if ctl is not None:
            if not isinstance(ctl, dict) or set(ctl) != {"inverted", "scrambled"}:
                why.append(f"TOI {n}: controls must be {{inverted, scrambled}}, each a list of events or null")
            else:
                for v, evs in ctl.items():
                    if evs is not None:
                        why += _event_errors(evs, f"TOI {n} {v} control")
    return why


class Refused(ValueError):
    """A submission the leaderboard will not score, with every reason."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _rate(k: int, n: int) -> dict:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "lo": lo, "hi": hi}


def youden(sens: dict, spec: dict) -> dict:
    """J = sensitivity + specificity − 1, with Newcombe's square-and-add interval from the two Wilson intervals."""
    if sens["rate"] is None or spec["rate"] is None:
        return {"j": None, "lo": None, "hi": None}
    j = sens["rate"] + spec["rate"] - 1
    lo = j - math.hypot(sens["rate"] - sens["lo"], spec["rate"] - spec["lo"])
    hi = j + math.hypot(sens["hi"] - sens["rate"], spec["hi"] - spec["rate"])
    return {"j": j, "lo": max(-1.0, lo), "hi": min(1.0, hi)}


def _candidate(e: dict) -> dict:
    return {"t_center": e["t_center"], "duration_hours": e["duration_hours"], "period_days": e.get("period_days"),
            "passed": e["passed"], "flags": list(e.get("flags") or []), "snr": e.get("snr"), "time_unit": "BTJD"}


def benchmark_searchable(benchmark: dict | None) -> set[str] | None:
    """The searchable set the benchmark fixed: TOIs whose star has a SPOC 2-minute light curve (a per-star row with
    real-data results). It does not depend on what a submitter says it searched."""
    if not benchmark or not benchmark.get("per_star"):
        return None
    return {r["toi"] for r in benchmark["per_star"] if r.get("real")}


def outcomes(sub: dict, sample: dict, benchmark: dict | None) -> list[dict]:
    """Per star, what the scorer finds in the submitted events: seen, recovered, flagged (score_star, the benchmark's
    own scoring), and the control false alarms (passed events on each control curve, None when not run). Each row
    also says whether the benchmark counts the star as searchable. ``benchmark`` is required; pass ``None`` only to
    treat every star as searchable (the fallback, used by nothing that ranks)."""
    toi = {t["toi"]: t for t in sample["tois"]}
    searchable = benchmark_searchable(benchmark)
    rows = []
    for p in sub["predictions"]:
        t = toi[p["toi"]]
        row = {"toi": p["toi"], "cls": t["class"], "radius": t.get("radius_re"), "searched": p["searched"],
               "searchable": searchable is None or p["toi"] in searchable,
               "seen": False, "recovered": False, "flagged": False, "controls": None}
        if p["searched"]:
            s = score_star(t, [_candidate(e) for e in p.get("events") or []])
            row.update(seen=s["seen"], recovered=s["recovered"], flagged=s["flagged"])
            ctl = p.get("controls")
            if ctl is not None:
                row["controls"] = {v: (None if ctl[v] is None else sum(1 for e in ctl[v] if e["passed"])) for v in ctl}
        rows.append(row)
    return rows


def score_rows(rows: list[dict]) -> dict:
    """The leaderboard's measures from per-star outcomes, with Wilson 95% intervals."""
    searched = [r for r in rows if r["searched"]]
    clean = lambda r: r["recovered"] and not r["flagged"]  # noqa: E731
    pos_all = [r for r in rows if r["cls"] == "positive"]
    fp_all = [r for r in rows if r["cls"] == "fp"]
    pos, fp, fa = ([r for r in searched if r["cls"] == c] for c in ("positive", "fp", "fa"))
    out = {
        "completeness": _rate(sum(r["recovered"] for r in pos), len(pos)),
        "completeness_all_stars": _rate(sum(r["searched"] and r["recovered"] for r in pos_all), len(pos_all)),
        "completeness_clean": _rate(sum(clean(r) for r in pos), len(pos)),
        "completeness_by_radius": [dict(_rate(sum(r["recovered"] for r in sel), len(sel)), bin=[a, b])
                                   for a, b in RADIUS_BINS
                                   for sel in [[r for r in pos if r["radius"] is not None and a <= r["radius"] < b]]],
        "fp_found": _rate(sum(r["seen"] for r in fp), len(fp)),
        "fp_flagged_of_found": _rate(sum(r["flagged"] for r in fp if r["seen"]), sum(r["seen"] for r in fp)),
        "fp_rejection": _rate(sum(not clean(r) for r in fp), len(fp)),
        # Every FP star of the scope: one the method did not search was not offered as a candidate either.
        "fp_rejection_all_stars": _rate(sum(not (r["searched"] and clean(r)) for r in fp_all), len(fp_all)),
        "fa_found": _rate(sum(r["seen"] for r in fa), len(fa)),
    }
    # The rank key. One predicate on both sides: a clean candidate (recovered and not flagged), so an eclipsing-
    # binary flag cannot count as a rejection on one side and as a recovery on the other. Over the searchable set the
    # benchmark fixed, so a submitter cannot move stars out of it by calling them not searched.
    bpos = [r for r in rows if r["searchable"] and r["cls"] == "positive"]
    bfp = [r for r in rows if r["searchable"] and r["cls"] == "fp"]
    out["completeness_clean_searchable"] = _rate(sum(r["searched"] and clean(r) for r in bpos), len(bpos))
    out["fp_rejection_searchable"] = _rate(sum(not (r["searched"] and clean(r)) for r in bfp), len(bfp))
    out["youden_j"] = youden(out["completeness_clean_searchable"], out["fp_rejection_searchable"])
    out["completeness_clean_all_stars"] = _rate(sum(r["searched"] and clean(r) for r in pos_all), len(pos_all))
    out["youden_j_all_stars"] = youden(out["completeness_clean_all_stars"], out["fp_rejection_all_stars"])
    cands = [r for r in searched if clean(r)]
    out["reliability"] = _rate(sum(r["cls"] == "positive" for r in cands), len(cands))
    out["reliability_mix"] = {c: len([r for r in searched if r["cls"] == c]) for c in ("positive", "fp", "fa")}
    controls = {}
    for v in ("inverted", "scrambled"):
        counts = [r["controls"][v] for r in searched if r["controls"] and r["controls"].get(v) is not None]
        controls[v] = None if not counts else {
            "star_sectors": len(counts), "vetted_false_alarms": sum(counts),
            "per_1000_star_sectors": 1000 * sum(counts) / len(counts),
            "stars_with_any": _rate(sum(c > 0 for c in counts), len(counts))}
    out["controls"] = controls
    out["controls_complete"] = bool(searched) and all(
        r["controls"] and all(r["controls"].get(v) is not None for v in ("inverted", "scrambled")) for r in searched)
    out["coverage"] = {"stars": len(rows), "searched": len(searched),
                       "by_class": {c: [sum(1 for r in searched if r["cls"] == c), sum(1 for r in rows if r["cls"] == c)]
                                    for c in ("positive", "fp", "fa")}}
    return out


def score(sub, sample: dict, inputs: dict | None = None, benchmark: dict | None = None) -> dict:
    """The submission's scores on its scope; raises :class:`Refused`."""
    inputs = inputs if inputs is not None else public_inputs(sample)
    why = validate(sub, sample, inputs, benchmark)
    if why:
        raise Refused(why)
    return score_rows(outcomes(sub, sample, benchmark))


# Entries the leaderboard derives itself from seeded entries: the Probes+Sentinels combinations, stated as
# star-level rules before any of them was scored (commit 9e42c0b), applied to the scorer's own outcomes.
DERIVED = [
    {"id": "probes-or-sentinel", "rule": "either", "probes": "probes-subsample", "sentinels": ["claude-volunteer", "claude-skeptic"],
     "name": "Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus)",
     "method": ("A clean candidate when the Probes give one or either Sentinel marks the TOI's dip as a potential "
                "planet. Applied by the leaderboard to the component entries' scored outcomes.")},
    {"id": "probes-and-sentinel", "rule": "both", "probes": "probes-subsample", "sentinels": ["claude-volunteer", "claude-skeptic"],
     "name": "Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus)",
     "method": ("A clean candidate only when the Probes give one and either Sentinel also marks the TOI's dip as a "
                "potential planet. Applied by the leaderboard to the component entries' scored outcomes.")},
]


def combine(probes: list[dict], sentinels: list[list[dict]], rule: str) -> list[dict]:
    out = []
    for i, pr in enumerate(probes):
        se = [s[i] for s in sentinels]
        hit = any(s["recovered"] for s in se)
        p_clean = pr["recovered"] and not pr["flagged"]
        seen = pr["seen"] or any(s["seen"] for s in se)
        recovered, clean = (pr["recovered"] or hit, p_clean or hit) if rule == "either" else (pr["recovered"] and hit, p_clean and hit)
        out.append(dict(pr, seen=seen, recovered=recovered, flagged=seen and not clean, controls=None))
    return out


def load_submissions(directory: str | Path = SUBMISSIONS) -> list:
    return [json.loads(p.read_text()) for p in sorted(Path(directory).glob("*.json"))]


FLOOR_ID = "metadata-baseline"


BOOTSTRAP_DRAWS = 20000
BOOTSTRAP_SEED = 20261019


def _clean_on_searchable(rows: list[dict]) -> dict[str, tuple[bool, bool]]:
    """TOI → (is CP/KP, offered as a clean candidate), on the benchmark's searchable CP/KP and FP stars."""
    return {r["toi"]: (r["cls"] == "positive", bool(r["searched"] and r["recovered"] and not r["flagged"]))
            for r in rows if r["searchable"] and r["cls"] in ("positive", "fp")}


def paired_delta_j(rows_a: list[dict], rows_b: list[dict], draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED) -> dict:
    """ΔJ = J(a) − J(b) on the same stars, with a paired bootstrap: CP/KP and FP stars are resampled separately (the
    class sizes are fixed by the sample), and both entries are scored on each resample. Returns ΔJ, its 95% percentile
    interval and P(ΔJ ≤ 0)."""
    import numpy as np

    a, b = _clean_on_searchable(rows_a), _clean_on_searchable(rows_b)
    tois = sorted(set(a) & set(b))
    pos = np.array([a[t][0] for t in tois])
    oa, ob = np.array([a[t][1] for t in tois]), np.array([b[t][1] for t in tois])

    def j(o, idx_p, idx_f):
        return o[idx_p].mean(axis=-1) + (~o[idx_f]).mean(axis=-1) - 1

    ip, iF = np.where(pos)[0], np.where(~pos)[0]
    d = float(j(oa, ip, iF) - j(ob, ip, iF))
    rng = np.random.default_rng(seed)
    bp = rng.choice(ip, size=(draws, len(ip)))
    bf = rng.choice(iF, size=(draws, len(iF)))
    ds = j(oa, bp, bf) - j(ob, bp, bf)
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return {"delta_j": d, "lo": float(lo), "hi": float(hi), "p_le_0": float(np.mean(ds <= 0)), "draws": draws, "seed": seed,
            "stars": {"positive": int(len(ip)), "fp": int(len(iF))}}


def floor_comparison(entries: list[dict], rows_of: dict[str, list[dict]]) -> dict | None:
    """The metadata-only floor against the Probes on the ranked J, by a paired ΔJ (floor − Probes) over the same
    stars. The verdict: the floor significantly ahead, the Probes significantly ahead, or neither shown."""
    by = {e["id"]: e for e in entries}
    if "probes" not in by or FLOOR_ID not in by:
        return None
    dj = paired_delta_j(rows_of[FLOOR_ID], rows_of["probes"])
    verdict = "floor_ahead" if dj["lo"] > 0 else "probes_ahead" if dj["hi"] < 0 else "not_shown"
    return {"probes": by["probes"]["scores"]["youden_j"], "floor": by[FLOOR_ID]["scores"]["youden_j"], "paired": dj,
            "verdict": verdict}


def dj_text(dj: dict) -> str:
    return (f"paired ΔJ (floor − Probes) = {dj['delta_j']:+.3f}, 95% CI {dj['lo']:+.3f} to {dj['hi']:+.3f}, "
            f"P(ΔJ ≤ 0) = {dj['p_le_0']:.2f}")


def floor_note(floor: dict | None) -> str:
    """The interpretation sentence, from the paired ΔJ only."""
    if not floor:
        return ""
    dj, v = floor["paired"], floor["verdict"]
    if v == "floor_ahead":
        return (f"The metadata-only floor is significantly ahead of the Probes ({dj_text(dj)}): on this benchmark J mostly "
                "measures how separable false positives are from catalogue metadata.")
    if v == "probes_ahead":
        return (f"The Probes are significantly ahead of the metadata-only floor ({dj_text(dj)}): the light curves add "
                "information beyond what catalogue metadata predicts.")
    return (f"The benchmark cannot show that the Probes read light curves better than catalogue metadata predicts "
            f"dispositions ({dj_text(dj)}).")


SUBSAMPLE_NOTE = ("40 stars cannot order these configurations: the subsample is listed, never ranked, and every "
                  "interval is wide.")


def build(sample: dict, inputs: dict, benchmark: dict, submissions: list) -> dict:
    """Score every submission; refused ones are listed with their reasons, never scored."""
    entries, refused, rows_of = [], [], {}
    for sub in submissions:
        why = validate(sub, sample, inputs, benchmark)
        if why:
            refused.append({"id": sub.get("id") if isinstance(sub, dict) else None,
                            "name": sub.get("name") if isinstance(sub, dict) else None, "reasons": why})
            continue
        rows = outcomes(sub, sample, benchmark)
        rows_of[sub["id"]] = (sub, rows)
        entries.append({"id": sub["id"], "name": sub["name"], "scope": sub["scope"], "kind": sub.get("kind", ""),
                        "tuned_on": sub["tuned_on"], "provenance": sub["provenance"], "scores": score_rows(rows)})
    for d in DERIVED:
        parts = [d["probes"], *d["sentinels"]]
        if not all(p in rows_of and rows_of[p][0]["scope"] == "sentinel_subsample" for p in parts):
            continue
        order = [p["toi"] for p in rows_of[d["probes"]][0]["predictions"]]
        by = {p: {r["toi"]: r for r in rows_of[p][1]} for p in parts}
        rows = combine([by[d["probes"]][n] for n in order], [[by[s][n] for n in order] for s in d["sentinels"]], d["rule"])
        entries.append({"id": d["id"], "name": d["name"], "scope": "sentinel_subsample", "kind": "derived", "tuned_on": "none",
                        "provenance": {"method": d["method"], "code_version": "src/setuhq/leaderboard.py (DERIVED)",
                                       "generated_from": [f"docs/leaderboard/submissions/{p}.json" for p in parts]},
                        "scores": score_rows(rows)})
    # Ranking: held-out entries with every control measured, by Youden's J. Equal J shares a rank. Nothing else
    # is ranked: an entry without controls hides its false alarms, and 40 stars cannot order anything.
    jv = lambda e: e["scores"]["youden_j"]["j"]  # noqa: E731
    for e in entries:
        e["ranked"] = e["scope"] == "held_out" and e["scores"]["controls_complete"] and jv(e) is not None
        e["unranked_reason"] = ("" if e["ranked"] else "subsample: 40 stars cannot order configurations"
                                if e["scope"] == "sentinel_subsample" else "controls not measured for every searched star")
    ranked = [e for e in entries if e["ranked"]]
    for e in entries:
        e["rank"] = (1 + sum(1 for o in ranked if jv(o) > jv(e))) if e["ranked"] else None
    for e in ranked:
        je = e["scores"]["youden_j"]
        e["overlaps_ranks"] = sorted({o["rank"] for o in ranked if o is not e and o["scores"]["youden_j"]["lo"] <= je["hi"]
                                      and je["lo"] <= o["scores"]["youden_j"]["hi"]})
    # Ranked entries by J; the rest (the subsample included) in a fixed order that implies nothing: Probes,
    # Sentinels, then the derived combinations.
    kinds = ["probes", "baseline", "sentinel", "derived"]
    entries.sort(key=lambda e: (SCOPES.index(e["scope"]), not e["ranked"], -jv(e) if e["ranked"] else 0,
                                kinds.index(e["kind"]) if e["kind"] in kinds else len(kinds), e["id"]))
    floor = floor_comparison(entries, {k: v[1] for k, v in rows_of.items()})
    return {"format": "exoplan-leaderboard-results/4", "license": "CC-BY-4.0", "floor": floor, "floor_note": floor_note(floor), "sample_sha256": sample["sha256"],
            "inputs_sha256": inputs_sha256(inputs), "full_sample_sha256": full_sample_sha256(sample),
            "sentinel_subsample": sentinel_subsample(benchmark),
            "sentinel_subsample_sha256": canonical_sha256(sentinel_subsample(benchmark)),
            "sentinel_agreement": (benchmark.get("sentinels") or {}).get("agreement"),
            "benchmark_code_commit": benchmark.get("code_commit"), "rules": RULES, "subsample_note": SUBSAMPLE_NOTE,
            "entries": entries, "refused": refused}


RULES = [
    "Scored on the held-out half of the frozen sample only (TOIs by sha256(seed:TIC) parity); the tuning half is "
    "never scored.",
    "A submission lists, for every star of its scope, the events its method detected on the real light curve and on "
    "the flux-inverted and block-scrambled controls (time, duration, period, its own pass verdict and flags). The "
    "leaderboard decides which events lie on the TOI's ephemeris (the benchmark's score_star and match_toi) and "
    "counts control false alarms itself. Self-reported outcomes are not accepted.",
    "Rank: Youden's J on the searchable set the benchmark fixed (stars with a SPOC 2-minute light curve), with one "
    "predicate on both sides, a clean candidate (on the ephemeris, passed, no eclipsing-binary flag): J = the share of "
    "CP/KP stars offered as clean candidates + the share of FP stars not offered − 1, with a square-and-add Wilson "
    "interval. Calling every TOI a planet, with or without a flag, scores J = 0; a searchable star called not searched "
    "counts as not offered. J over every star of the scope is shown beside it. Where intervals overlap, the order is "
    "not a measured difference.",
    "The controls gate ranking and do not enter J: only held-out entries with both control lists on every searched "
    "star are ranked, others are listed unranked. The control lists are the method's own report; the leaderboard "
    "cannot recompute them without the light curves. The 40-star Sentinel subsample is never ranked.",
    "A floor: the metadata-only baseline uses no light curve at all, only the public TOI number, period, duration, "
    "ephemeris errors and epoch, with a logistic regression fitted on the tuning half. A method that does not beat "
    "it is not shown to read the light curves better than the catalogue's own metadata predicts dispositions.",
    "A submission states the sha256 of the public inputs it was built from (tuning half with labels, held-out half "
    "without). Any other hash, tuned_on other than none or tuning, a field outside the whitelist, a missing or extra "
    "star, or missing provenance: refused, with the reasons listed.",
    "The hash is an attestation: the held-out labels are public in the repository, so the leaderboard cannot prove "
    "they were not read, and a method's pass verdicts and control events are its own report. Maintainer-held decoy "
    "light curves and prospective scoring on TOIs still undispositioned would close these gaps; neither exists yet.",
    "FP rejection: FP stars whose TOI dip the method did not offer as a clean candidate (recovered and not flagged). "
    "Reliability: the share of clean candidates on TOI dips that are CP/KP, on this sample's class mix, which is not "
    "the TOI catalogue's. All rates carry Wilson 95% intervals. TFOPWG dispositions are the reference, not ground "
    "truth for every TOI.",
    "Measured on a stated benchmark; nothing on this leaderboard is a discovery.",
]


def _pct(r: dict | None) -> str:
    if not r or r.get("rate") is None:
        return "n/a"
    return f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']}; {100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)"


def rank_text(e: dict) -> str:
    """A rank, with the ranks whose J interval overlaps it (a tied group: the order is not a measured difference)."""
    ov = e.get("overlaps_ranks") or []
    return f"{e['rank']}" + (f" (interval overlaps #{', #'.join(map(str, ov))})" if ov else "")


def jtext(j: dict) -> str:
    return "n/a" if j["j"] is None else f"{j['j']:+.2f} ({j['lo']:+.2f} to {j['hi']:+.2f})"


def small_rate(s: dict) -> dict | None:
    """Completeness on CP/KP TOIs below 4 R⊕ (the radius bins that end at or below 4)."""
    sel = [b for b in s["completeness_by_radius"] if b["bin"][1] <= 4]
    k, n = sum(b["k"] for b in sel), sum(b["n"] for b in sel)
    return _rate(k, n) if n else None


SCOPE_LABEL = {"held_out": "Held-out half (every held-out star)",
               "sentinel_subsample": "The Sentinels' stated subsample (40 held-out stars: 20 CP/KP, 20 FP), not ranked"}


def to_markdown(res: dict) -> str:
    lines = ["# Leaderboard: the frozen real-TOI benchmark", "",
             "Not to be confused with the injection threshold sweep in [docs/threshold_sweep.md](../threshold_sweep.md), "
             "which tunes Probe thresholds on synthetic light curves.", "",
             "Measured on a stated benchmark; not discoveries. Sentinels run on Claude (Anthropic). Probes are "
             "deterministic matched-filter detectors.", "",
             f"Frozen sample sha256 `{res['sample_sha256']}` (docs/results/benchmark_toi_sample.json). Public inputs "
             f"(tuning half with labels, held-out half without) sha256 `{res['inputs_sha256']}` "
             "(docs/leaderboard/tuning_inputs.json). Sentinel subsample sha256 "
             f"`{res['sentinel_subsample_sha256']}`. Benchmark code commit `{res['benchmark_code_commit']}`.", "",
             "## Rules", ""] + [f"{i}. {r}" for i, r in enumerate(res["rules"], 1)]
    for scope in SCOPES:
        es = [e for e in res["entries"] if e["scope"] == scope]
        if not es:
            continue
        head = "| rank | entry | Youden J |" if scope == "held_out" else "| entry | Youden J |"
        lines += ["", f"## {SCOPE_LABEL[scope]}", ""]
        if scope == "sentinel_subsample":
            lines += [f"**{res['subsample_note']}**", ""]
        elif res.get("floor_note"):
            lines += [f"**{res['floor_note']}**", ""]
        lines += [head + " Youden J, all stars | clean completeness, searchable CP/KP | FP rejection, searchable FP | "
                  "recovered below 4 R⊕ | inverted control: stars with any | scrambled control: stars with any | reliability |",
                  "|" + "---|" * (10 if scope == "held_out" else 9)]
        for e in es:
            s = e["scores"]
            ctl = lambda v: _pct(s["controls"][v]["stars_with_any"]) if s["controls"][v] else "not measured"  # noqa: E731
            rank = (f"| {rank_text(e)} " if e["ranked"] else f"| unranked ({e['unranked_reason']}) ") if scope == "held_out" else ""
            lines.append(f"{rank}| {e['name']} | {jtext(s['youden_j'])} | {jtext(s['youden_j_all_stars'])} | "
                         f"{_pct(s['completeness_clean_searchable'])} | {_pct(s['fp_rejection_searchable'])} | "
                         f"{_pct(small_rate(s))} | {ctl('inverted')} | {ctl('scrambled')} | {_pct(s['reliability'])} |")
        lines += ["", "Entries:", ""] + [f"* **{e['name']}** (`{e['id']}`, tuned on: {e['tuned_on']}). {e['provenance']['method']}"
                                          for e in es]
    if res["refused"]:
        lines += ["", "## Refused", ""] + [f"* {r['name'] or r['id']}: {'; '.join(r['reasons'])}" for r in res["refused"]]
    lines += ["", "Clean completeness and FP rejection use the same predicate (a clean candidate: on the ephemeris, "
              "passed, no eclipsing-binary flag) over the searchable set the benchmark fixed. The benchmark report's "
              "headline completeness counts a recovered dip even when flagged, and its \"rejected or flagged\" rate is "
              "over the FP dips the panel found; both are in docs/results/benchmark_real_tois.md. Reliability depends on "
              "the sample's class mix; it is not the reliability on the TOI catalogue.", ""]
    return "\n".join(lines)


def write_inputs(sample: dict, path: str | Path = INPUTS) -> str:
    inputs = public_inputs(sample)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(inputs, indent=1, ensure_ascii=False) + "\n")
    return inputs_sha256(inputs)


def write_results(res: dict, json_path: str | Path = RESULTS, md_path: str | Path = RESULTS_MD) -> None:
    Path(json_path).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    Path(md_path).write_text(to_markdown(res))

"""The public leaderboard on the frozen real-TOI benchmark (S5; the benchmark itself is S1c, benchmark_toi.py).

A **submission** is one JSON file: a method's per-star outcomes on the held-out half of the frozen sample
(``docs/results/benchmark_toi_sample.json``, sha256 ``6f0e111e…``), with provenance. The leaderboard scores it on
the held-out half only, with Wilson 95% intervals, and refuses it when it could have used held-out labels.

The format (``exoplan-leaderboard/1``)::

    {"format": "exoplan-leaderboard/1", "id": "probes", "name": "Probes only",
     "sample_sha256": "<the frozen sample's hash>",
     "inputs_sha256": "<the hash of docs/leaderboard/tuning_inputs.json>",
     "tuned_on": "none" | "tuning",
     "scope": "held_out" | "sentinel_subsample",
     "provenance": {"method": "...", "code_version": "...", "generated_from": [...]},
     "predictions": [{"toi": "1201.01", "tic": 12345, "searched": true, "seen": true, "recovered": true,
                      "flagged": false, "controls": {"inverted": 0, "scrambled": 1}}, ...]}

Per held-out star (every star in the scope, no other):

* ``searched``: the method had a light curve for the star and ran on it.
* ``seen``: one of its detected events lies on the TOI's published ephemeris (``discover.match_toi``; the
  ephemeris is in the public inputs).
* ``recovered``: that event passed the method's own vetting, so the method offers it as a candidate.
* ``flagged``: the method rejected the on-ephemeris event or marked it binary-like. A *clean candidate* is
  recovered and not flagged.
* ``controls``: events that passed vetting on the star's flux-inverted and block-scrambled light curves
  (``benchmark_toi.inverted`` and ``benchmark_toi.scrambled``), or ``null`` when the method was not run on them.

The rule on labels. The **public inputs** file (``docs/leaderboard/tuning_inputs.json``) holds the tuning half
with its dispositions and, for the held-out half, only what a blind search needs (TIC, TOI name, ephemeris): no
disposition, class, depth or radius. A submission states the sha256 of the inputs it was built from. It is refused
when that hash is not the public inputs' hash (and the message says so when it is the hash of the full sample,
which holds the held-out labels), when it says it was tuned on the held-out half, when a prediction carries a
label field, or when it does not cover exactly the stars of its scope. The hash is an attestation, not a proof:
the held-out labels are public in the repository, so the leaderboard cannot tell whether someone read them. It
can refuse every submission that declares or shows that it did.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from exoplan.benchmark_toi import RADIUS_BINS, wilson

ROOT = Path(__file__).resolve().parents[2]
FORMAT = "exoplan-leaderboard/1"
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
# Keys that would carry a label (or a label proxy) if they appeared in a prediction.
LABEL_KEYS = frozenset({"class", "disposition", "tfopwg_disp", "label", "labels", "truth", "is_planet", "fp", "cp_kp"})
SCOPES = ("held_out", "sentinel_subsample")
TUNED_ON = ("none", "tuning")
PROVENANCE_KEYS = ("method", "code_version", "generated_from")


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


def _label_keys(obj, path="") -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in LABEL_KEYS:
                found.append(f"{path}{k}")
            found += _label_keys(v, f"{path}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _label_keys(v, f"{path}{i}.")
    return found


def validate(sub: dict, sample: dict, inputs: dict, benchmark: dict | None = None) -> list[str]:
    """Every reason to refuse this submission (an empty list: accepted)."""
    why = []
    if sub.get("format") != FORMAT:
        why.append(f"format must be {FORMAT!r}")
    if sub.get("sample_sha256") != sample["sha256"]:
        why.append(f"sample_sha256 must be the frozen sample's hash {sample['sha256']}")
    stated = sub.get("inputs_sha256")
    if stated == full_sample_sha256(sample) or stated == sample["sha256"]:
        why.append("inputs_sha256 is the hash of the full sample, which holds the held-out labels: built with held-out labels")
    elif stated != inputs_sha256(inputs):
        why.append(f"inputs_sha256 must be the hash of the public tuning-half-only inputs ({inputs_sha256(inputs)})")
    if sub.get("tuned_on") not in TUNED_ON:
        why.append(f"tuned_on must be one of {TUNED_ON} (tuned on {sub.get('tuned_on')!r} touches held-out labels)"
                   if sub.get("tuned_on") in ("held_out", "all", "both") else f"tuned_on must be one of {TUNED_ON}")
    prov = sub.get("provenance") or {}
    missing = [k for k in PROVENANCE_KEYS if not prov.get(k)]
    if missing:
        why.append(f"provenance must state {', '.join(missing)}")
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
    labels = _label_keys(preds)
    if labels:
        why.append(f"predictions carry label fields ({', '.join(sorted(set(labels))[:5])})")
    names = [p.get("toi") for p in preds if isinstance(p, dict)]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        why.append(f"duplicate predictions for TOI {', '.join(dup[:5])}")
    tuning = sorted(n for n in set(names) if half_of.get(n) == "tuning")
    if tuning:
        why.append(f"predictions include {len(tuning)} tuning-half stars; submit the held-out scope only")
    extra = sorted(set(names) - set(want) - set(tuning))
    if extra:
        why.append(f"predictions for {len(extra)} TOIs outside the scope ({', '.join(map(str, extra[:5]))})")
    absent = sorted(set(want) - set(names))
    if absent:
        why.append(f"no prediction for {len(absent)} stars of the scope ({', '.join(absent[:5])}); a star not searched is "
                   "submitted with searched: false, never left out")
    for p in preds:
        if not isinstance(p, dict):
            why.append("every prediction must be an object")
            break
        n = p.get("toi")
        if n in tic_of and p.get("tic") != tic_of[n]:
            why.append(f"TOI {n}: tic {p.get('tic')} is not the sample's {tic_of[n]}")
        if not isinstance(p.get("searched"), bool):
            why.append(f"TOI {n}: searched must be true or false")
            continue
        flags = {k: p.get(k) for k in ("seen", "recovered", "flagged")}
        if p["searched"]:
            if not all(isinstance(v, bool) for v in flags.values()):
                why.append(f"TOI {n}: seen, recovered and flagged must be true or false on a searched star")
                continue
            if (flags["recovered"] or flags["flagged"]) and not flags["seen"]:
                why.append(f"TOI {n}: recovered or flagged needs seen")
        elif any(flags.values()):
            why.append(f"TOI {n}: a star not searched cannot be seen, recovered or flagged")
        ctl = p.get("controls")
        if ctl is not None:
            if not isinstance(ctl, dict) or set(ctl) - {"inverted", "scrambled"}:
                why.append(f"TOI {n}: controls must be {{inverted, scrambled}}")
            elif any(v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0) for v in ctl.values()):
                why.append(f"TOI {n}: control counts must be non-negative integers or null")
    return why


class Refused(ValueError):
    """A submission the leaderboard will not score, with every reason."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _rate(k: int, n: int) -> dict:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": p, "lo": lo, "hi": hi}


def score(sub: dict, sample: dict, inputs: dict | None = None, benchmark: dict | None = None) -> dict:
    """The submission's scores on its scope, with Wilson 95% intervals; raises :class:`Refused`."""
    inputs = inputs if inputs is not None else public_inputs(sample)
    why = validate(sub, sample, inputs, benchmark)
    if why:
        raise Refused(why)
    toi = {t["toi"]: t for t in sample["tois"]}
    rows = [dict(p, cls=toi[p["toi"]]["class"], radius=toi[p["toi"]].get("radius_re")) for p in sub["predictions"]]
    searched = [r for r in rows if r["searched"]]
    clean = lambda r: r["recovered"] and not r["flagged"]  # noqa: E731
    pos_all = [r for r in rows if r["cls"] == "positive"]
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
        "fa_found": _rate(sum(r["seen"] for r in fa), len(fa)),
    }
    cands = [r for r in searched if clean(r)]
    out["reliability"] = _rate(sum(r["cls"] == "positive" for r in cands), len(cands))
    out["reliability_mix"] = {c: len([r for r in searched if r["cls"] == c]) for c in ("positive", "fp", "fa")}
    controls = {}
    for v in ("inverted", "scrambled"):
        counts = [r["controls"][v] for r in searched if r.get("controls") and r["controls"].get(v) is not None]
        controls[v] = None if not counts else {
            "star_sectors": len(counts), "vetted_false_alarms": sum(counts),
            "per_1000_star_sectors": 1000 * sum(counts) / len(counts),
            "stars_with_any": _rate(sum(c > 0 for c in counts), len(counts))}
    out["controls"] = controls
    out["coverage"] = {"stars": len(rows), "searched": len(searched),
                       "by_class": {c: [sum(1 for r in searched if r["cls"] == c), sum(1 for r in rows if r["cls"] == c)]
                                    for c in ("positive", "fp", "fa")}}
    return out


def load_submissions(directory: str | Path = SUBMISSIONS) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(Path(directory).glob("*.json"))]


def build(sample: dict, inputs: dict, benchmark: dict, submissions: list[dict]) -> dict:
    """Score every submission; refused ones are listed with their reasons, never scored."""
    entries, refused = [], []
    for sub in submissions:
        try:
            s = score(sub, sample, inputs, benchmark)
        except Refused as exc:
            refused.append({"id": sub.get("id"), "name": sub.get("name"), "reasons": exc.reasons})
            continue
        entries.append({"id": sub["id"], "name": sub["name"], "scope": sub["scope"], "kind": sub.get("kind", ""),
                        "tuned_on": sub["tuned_on"], "provenance": sub["provenance"], "scores": s})
    # Rank within each scope by completeness over every CP/KP star in it (a star not searched counts as missed,
    # so leaving hard stars out cannot raise the rank).
    key = lambda e: e["scores"]["completeness_all_stars"]["rate"] or 0  # noqa: E731
    entries.sort(key=lambda e: (SCOPES.index(e["scope"]), -key(e), e["id"]))
    for e in entries:  # equal completeness, equal rank
        e["rank"] = 1 + sum(1 for o in entries if o["scope"] == e["scope"] and key(o) > key(e))
    return {"format": "exoplan-leaderboard-results/1", "sample_sha256": sample["sha256"],
            "inputs_sha256": inputs_sha256(inputs), "full_sample_sha256": full_sample_sha256(sample),
            "sentinel_subsample": sentinel_subsample(benchmark),
            "sentinel_subsample_sha256": canonical_sha256(sentinel_subsample(benchmark)),
            "sentinel_agreement": (benchmark.get("sentinels") or {}).get("agreement"),
            "benchmark_code_commit": benchmark.get("code_commit"), "rules": RULES, "entries": entries, "refused": refused}


RULES = [
    "Scored on the held-out half of the frozen sample only (TOIs by sha256(seed:TIC) parity); the tuning half is "
    "never scored.",
    "A submission covers every star of its scope: the whole held-out half, or the Sentinels' stated 40-star "
    "subsample. A star without a light curve is submitted with searched: false and counts as missed in the "
    "all-stars completeness, which is the rank key.",
    "It states the sha256 of the public inputs it was built from (tuning half with labels, held-out half without). "
    "Any other hash, tuned_on other than none or tuning, a label field in a prediction, a missing or extra star, or "
    "missing provenance: refused, with the reasons listed.",
    "The hash is an attestation: the held-out labels are public in the repository, so the leaderboard cannot prove "
    "they were not read. It refuses every submission that declares or shows that they were.",
    "Completeness: CP/KP stars whose TOI dip the method recovered (passed its vetting). FP rejection: searched FP "
    "stars whose TOI dip the method did not offer as a clean candidate (recovered and not flagged). Controls: stars "
    "with any vetted event on the flux-inverted and block-scrambled light curves. Reliability: the share of clean "
    "candidates on TOI dips that are CP/KP, on this sample's class mix, which is not the TOI catalogue's.",
    "All rates carry Wilson 95% intervals. TFOPWG dispositions are the reference, not ground truth for every TOI.",
    "Measured on a stated benchmark; nothing on this leaderboard is a discovery.",
]


def _pct(r: dict | None) -> str:
    if not r or r.get("rate") is None:
        return "n/a"
    return f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']}; {100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)"


SCOPE_LABEL = {"held_out": "Held-out half (every held-out star)",
               "sentinel_subsample": "The Sentinels' stated subsample (40 held-out stars: 20 CP/KP, 20 FP)"}


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
        lines += ["", f"## {SCOPE_LABEL[scope]}", "",
                  "| rank | entry | completeness, all CP/KP stars | completeness, searchable | below 4 R⊕ | FP rejection | "
                  "inverted control: stars with any | scrambled control: stars with any | reliability |",
                  "|---:|---|---|---|---|---|---|---|---|"]
        for e in es:
            s = e["scores"]
            small = [b for b in s["completeness_by_radius"] if b["bin"][1] <= 4]
            k, n = sum(b["k"] for b in small), sum(b["n"] for b in small)
            ctl = lambda v: _pct(s["controls"][v]["stars_with_any"]) if s["controls"][v] else "not measured"  # noqa: E731
            lines.append(f"| {e['rank']} | {e['name']} | {_pct(s['completeness_all_stars'])} | {_pct(s['completeness'])} | "
                         f"{_pct(_rate(k, n)) if n else 'n/a'} | {_pct(s['fp_rejection'])} | {ctl('inverted')} | "
                         f"{ctl('scrambled')} | {_pct(s['reliability'])} |")
        lines += ["", "Entries:", ""] + [f"* **{e['name']}** (`{e['id']}`, tuned on: {e['tuned_on']}). {e['provenance']['method']}"
                                          for e in es]
    if res["refused"]:
        lines += ["", "## Refused", ""] + [f"* {r['name'] or r['id']}: {'; '.join(r['reasons'])}" for r in res["refused"]]
    lines += ["", "Rank is by completeness over every CP/KP star in the scope; equal completeness shares a rank. Where "
              "two entries' intervals overlap, their order is not a measured difference. Reliability depends on the sample's class mix (the held-out searched stars are about half "
              "CP/KP); it is not the reliability on the TOI catalogue. The Sentinel entries cover 40 stars, so their "
              "intervals are wide, and they were never run on the control light curves.", ""]
    return "\n".join(lines)


def write_inputs(sample: dict, path: str | Path = INPUTS) -> str:
    inputs = public_inputs(sample)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(inputs, indent=1, ensure_ascii=False) + "\n")
    return inputs_sha256(inputs)


def write_results(res: dict, json_path: str | Path = RESULTS, md_path: str | Path = RESULTS_MD) -> None:
    Path(json_path).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    Path(md_path).write_text(to_markdown(res))

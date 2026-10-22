# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Build docs/results/stellar_validation.json and .md from the item cache of scripts/stellar_validation.py.

The checks that set each capability's status are fixed here, before the numbers are read: a capability is
"validated" when every one of its checks passes, "partly validated" when some do, "unvalidated" when none do or
its items could not run. Every number is copied from the item records; nothing is recomputed here.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from setuhq import cheops as ch  # noqa: E402

# The metric each protocol check reads from its item's result. The thresholds and the pass rule are in the protocol
# file (docs/results/stellar_validation_protocol_v2.json); this table only says where each number is.
def _ci_low(r):
    return r["ci95"][0]


METRICS = {
    "recall_ci_low": lambda r: _ci_low(r["recall"]),
    "null_per_10d": lambda r: 10.0 * r["ours"]["inverted_null"] / r["ours"]["observing_days"],
    "bright_recall_ci_low": lambda r: _ci_low(r["bright_recall"]),
    "precision": lambda r: r["ours_matched"]["matched"] / r["ours_matched"]["of"],
    "band_energy_ratio_ci": lambda r: r["band_energy_data_ed_magnitude_ratio_ours_over_published"]["ci95"],
    "energy_ratio_ci": lambda r: r["energy_ratio_ours_over_published"]["ci95"],
    "fp_per_day": lambda r: r["false_positive_rate_per_day_upper"],
    "validation_split_rate": lambda r: r["validation_pooled"]["rate"],
    "cheops_null_fraction": lambda r: r["summary"]["null_fraction"],
    "cheops_bright_recovery_ci_low": lambda r: _ci_low(r["summary"]["injection_gate"]),
    "complex_ci_contains": lambda r: r["summary"]["denoised"]["complex_ci95"],
    "alpha_z": lambda r: abs(r["summary"]["denoised"]["power_law_above_median_energy"]["alpha"] - 1.92)
    / (r["summary"]["denoised"]["power_law_above_median_energy"]["alpha_err"] ** 2 + 0.07 ** 2) ** 0.5,
    "same_input_ok": lambda r: all(v.get("same_input_ok") for v in r["visits"]),
    "end_to_end_min_corr": lambda r: min(v["end_to_end"]["correlation"] for v in r["visits"]),
    "f1_f2_combined": lambda r: all(r["combined"]["f1_f2_recovered"]),
    "top10_strict": lambda r: r["recall_top10_strict"],
    "all_loose": lambda r: r["recall_all_loose"],
    "hr10_top10_min": lambda r: min(x["recall_top10_loose"] for x in r["sectors"].values()),
    "hr10_all_min": lambda r: min(x["recall_all_loose"] for x in r["sectors"].values()),
    "ar1_false_per_lc": lambda r: r["sectors"]["29"]["null"][0]["mean_false_per_lightcurve"],
    "max_combination_chance": lambda r: max(x["combination_chance"]["chance_rate"] for x in r["sectors"].values()),
    "granulation_ratio": lambda r: r["granulation_averaged"]["b_uhz"] / 150.87,
    "numax_abs_z": lambda r: abs(r["numax_z"]),
    "dnu_abs_diff": lambda r: abs(r["ours"]["dnu_uhz"] - 28.94),
}


def _apply(op, value, threshold):
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == "<":
        return value < threshold
    if op == "==":
        return value == threshold
    if op == "within":  # an interval (or a value) inside [lo, hi]
        lo, hi = threshold
        return (lo <= value[0] and value[1] <= hi) if isinstance(value, (list, tuple)) else lo <= value <= hi
    if op == "contains":  # an interval containing the threshold
        return value[0] <= threshold <= value[1]
    raise ValueError(op)


def _items(items_dir: Path) -> dict:
    out = {}
    for p in sorted(Path(items_dir).glob("*.json")):
        out[p.stem] = json.loads(p.read_text())
    return out


def _fmt(x, nd=2):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}g}" if abs(x) >= 1e4 or (0 < abs(x) < 1e-2) else f"{x:.{nd}f}"
    return str(x)


def _ci(d, nd=2):
    if not d or d.get("median") is None:
        return "n/a"
    c = d.get("ci95")
    return f"{d['median']:.{nd}f}" + (f" [{c[0]:.{nd}f}, {c[1]:.{nd}f}]" if c else "") + f" (n = {d['n']})"


def _frac(r):
    lo, hi = r["ci95"]
    k = next(r[x] for x in ("recovered", "found", "agree") if x in r)
    return f"{k}/{r['of']} = {k / max(r['of'], 1):.2f} [{lo:.2f}, {hi:.2f}]"


def write_report(items_dir, out_json, out_md, protocol, protocol_sha, fingerprint, refs):
    items = _items(items_dir)
    checks = []
    for c in protocol["checks"]:
        row = {"capability": c["capability"], "check": c["id"], "item": c["item"], "text": c["text"],
               "tuning": bool(c.get("tuning")), "gate": bool(c.get("gate")), "gated": bool(c.get("gated"))}
        rec = items.get(c["item"])
        if not rec or rec.get("status") != "ok":
            checks.append({**row, "result": "not run", "why": (rec or {}).get("error", "item not run")})
            continue
        try:
            value = METRICS[c["metric"]](rec["result"])
            ok = bool(_apply(c["op"], value, c["threshold"]))
            checks.append({**row, "value": value, "result": "pass" if ok else "fail"})
        except (KeyError, TypeError, IndexError, ZeroDivisionError, ValueError) as exc:
            checks.append({**row, "result": "not run", "why": f"{type(exc).__name__}: {exc}"})
    # gated comparisons count only when every gate of their capability passes; otherwise they are inconclusive
    for c in checks:
        if c["gated"]:
            gates = [g for g in checks if g["gate"] and g["capability"] == c["capability"]]
            if not all(g["result"] == "pass" for g in gates):
                c["computed_result"] = c["result"]
                c["result"] = "inconclusive"
                c["why"] = "a gate (the CHEOPS null or injection check) did not pass; the comparison is not interpretable"
        if c["tuning"]:
            c["computed_result"] = c["result"]
            c["result"] = "tuning set"
    caps = {}
    for cap in ("flares", "pulsations", "cheops"):
        cs = [c for c in checks if c["capability"] == cap and c["result"] in ("pass", "fail", "not run")]
        n_pass = sum(c["result"] == "pass" for c in cs)
        status = "validated" if cs and n_pass == len(cs) else "partly validated" if n_pass else "unvalidated"
        caps[cap] = {"status": status, "passed": n_pass, "of": len(cs),
                     "inconclusive": sum(1 for c in checks if c["capability"] == cap and c["result"] == "inconclusive"),
                     "tuning_set": sum(1 for c in checks if c["capability"] == cap and c["result"] == "tuning set")}
    # what could not be validated at all
    unvalidated = [
        "Flare energies: on TESS they use the TESS magnitude and distance (Sullivan et al. 2015 zero point) when the TIC "
        "has them, else TIC Teff and radius; on CHEOPS (no magnitude route) the TIC radius and, where the TIC has no Teff, "
        "the Teff from the CHEOPS archive, labelled. A star with neither route gets energies reported as unavailable.",
        "AU Mic sector 1 is the tuning star of the flare shape test: its numbers are reported, its null is not counted.",
        "GJ 1243: no machine-readable per-flare TESS catalogue was found; detections are reported, not compared.",
        "GJ 65: no per-flare table is public for Bruno et al. (2024); only an internal 120 s vs 20 s check.",
        "Poyatos et al. (2025) worked on 3-s CHEOPS imagettes reduced with PIPE; DACE serves DRP subarray light curves "
        "(about 42 s and longer), so the CHEOPS comparison is of aggregate numbers on different data products, not "
        "flare by flare, and it counts only when the CHEOPS null and injection gates pass. Their per-flare catalogue is "
        "not public.",
        "Bruno et al. (2024): no per-flare catalogue; their complex fraction (≳ 30%) is quoted for context only.",
        "Wavelet denoising: tuned and checked by injection on SetuHQ's own data; Poyatos et al.'s optimal parameters "
        "were found on imagettes and are not reproduced here.",
        "HR 10 CHEOPS frequencies: Salmon et al. (2024) publish no CHEOPS frequency list; only the TESS lists are compared.",
    ]
    record = {
        "kind": "setuhq-stellar-validation/1", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": protocol, "protocol_sha256": protocol_sha, "code_fingerprint": fingerprint,
        "capabilities": caps, "checks": checks, "unvalidated": unvalidated,
        "items": {k: {kk: v.get(kk) for kk in ("status", "code_fingerprint", "code_files", "protocol_sha256", "finished_at",
                                                "seconds", "error")} for k, v in items.items()},
        "results": {k: _summary(k, v) for k, v in items.items()},
        "references": {k: v.get("source") for k, v in refs.items() if isinstance(v, dict)},
        "cheops_credit": ch.credit(_cheops_visits(items)),
        "labels": ["Flares and frequencies are detected at the stated significance; nothing here is confirmed.",
                   "Types are heuristic (likely or candidate). Energies assume a 9000 K blackbody flare."],
    }
    Path(out_json).write_text(json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False) + "\n")
    Path(out_md).write_text(_markdown(record, items))
    print(f"wrote {out_json} and {out_md}: " + ", ".join(f"{k} {v['status']} ({v['passed']}/{v['of']})" for k, v in caps.items()))


def _cheops_visits(items) -> list[dict]:
    vs = []
    for name in ("cheops_flares", "hr10_cheops", "cheops_pycheops"):
        r = (items.get(name) or {}).get("result") or {}
        for c in r.get("credits") or []:
            vs.append({"file_key": c["file_key"], "obs_id": c.get("obs_id"), "pi_name": c.get("pi_name"),
                       "data_pipe_version": c.get("drp_version")})
    seen, out = set(), []
    for v in vs:
        if v["file_key"] not in seen:
            seen.add(v["file_key"])
            out.append(v)
    return out


def _summary(name, rec):
    """The numbers the report quotes (the full item records stay in the cache; flare lists are left out here)."""
    r = rec.get("result")
    if not r:
        return {"status": rec.get("status"), "error": rec.get("error")}
    drop = {"flares", "flares_20s", "frequencies", "pairs_loose", "targets", "visits", "stars", "injections"}
    out = {k: v for k, v in r.items() if k not in drop}
    if name == "cheops_flares":
        out["targets"] = [{k: t.get(k) for k in ("star", "public_visits", "used")} for t in r.get("targets", [])]
    if name in ("hr10_cheops", "cheops_pycheops"):
        out["visits"] = [{k: v for k, v in x.items() if k != "frequencies"} for x in r.get("visits", [])]
    if name == "quiet_stars":
        out["stars"] = [{k: s.get(k) for k in ("star", "tic", "sectors", "observing_days", "flares_detected", "inverted_null")}
                        for s in r.get("stars", [])]
    if name == "hr10_tess":
        out["sectors"] = {s: {k: v for k, v in x.items() if k not in ("frequencies", "pairs_loose")} for s, x in r["sectors"].items()}
    return out


def _markdown(rec, items) -> str:
    R = {k: (v.get("result") or {}) for k, v in items.items()}
    L = []
    a = L.append
    a("<!-- Generated by scripts/stellar_validation.py --report from the item records; do not edit by hand. -->")
    a("# Stellar validation: flares, pulsations and CHEOPS")
    a("")
    a(f"Protocol v{rec['protocol']['version']} (`docs/results/stellar_validation_protocol_v2.json`, sha256 "
      f"`{rec['protocol_sha256']}`), frozen {rec['protocol']['frozen']}, seed {rec['protocol']['seed']}; stellar code "
      f"fingerprint `{rec['code_fingerprint'][:16]}…` (each item records the fingerprint of the files it depends on). "
      f"Generated {rec['generated_at']}.")
    a("")
    a("**How far to trust this.** " + rec["protocol"]["history"])
    a("")
    a("Changes from v1:")
    a("")
    for ch_ in rec["protocol"]["changes_from_v1"]:
        a(f"- {ch_}")
    a("")
    a("Every comparison is against **published numbers**; where ours and theirs disagree, both are shown. Flares and "
      "frequencies are *detected* at the significance stated; nothing here is a confirmation, and types are heuristic.")
    a("")
    a("## Status")
    a("")
    a("| Capability | Status | Checks passed | Inconclusive (gated) | Tuning-set results (not counted) |")
    a("|---|---|---|---|---|")
    for k, v in rec["capabilities"].items():
        a(f"| {k} | **{v['status']}** | {v['passed']} of {v['of']} | {v['inconclusive']} | {v['tuning_set']} |")
    a("")
    a("| Capability | Check | Value | Result |")
    a("|---|---|---|---|")
    for c in rec["checks"]:
        v = c.get("value")
        vt = (f"[{v[0]:.2f}, {v[1]:.2f}]" if isinstance(v, (list, tuple)) and v and v[0] is not None
              else f"{v:.3g}" if isinstance(v, float) else str(v) if v is not None else "")
        res = c["result"] + (f" (computed: {c['computed_result']})" if c.get("computed_result") else "")
        a(f"| {c['capability']} | {c['text']} | {vt} | {res}{' — ' + c['why'] if c.get('why') else ''} |")
    a("")
    a("## Flares")
    a("")
    if R.get("aumic_gunther"):
        r = R["aumic_gunther"]
        a("### AU Mic, TESS sector 1 (2 min), against Günther et al. 2020 (tuning star)")
        a("")
        a(f"**{r.get('tuning_note', '')}**")
        a("")
        a("| Quantity | SetuHQ | Günther et al. 2020 |")
        a("|---|---|---|")
        a(f"| Flare events | {r['ours']['flares']} ({r['ours']['complex']} complex, {r['ours']['components']} components) | "
          f"{r['published']['outbursts']} outbursts, {r['published']['flares']} flare components |")
        a(f"| Complex (multi-peak) fraction | {r['ours']['complex_fraction']:.2f} | {r['published']['multi_fraction']:.2f} |")
        a(f"| Published flares inside one of our events (recall) | {_frac(r['recall'])} | |")
        a(f"| Our events that hold a published flare | {r['ours_matched']['matched']}/{r['ours_matched']['of']} | |")
        a(f"| Morphology agrees (simple/complex) | {_frac(r['morphology_agreement'])} | |" if r.get("morphology_agreement") else "")
        a(f"| Peak amplitude, ours / published (median, 95% CI) | {_ci(r['amplitude_ratio_ours_over_published'])} | |")
        a(f"| FWHM, ours / published, single-component events | {_ci(r.get('fwhm_ratio_ours_over_published_simple'))} | |")
        a(f"| Flux-inverted null | {r['ours']['inverted_null']} events in {r['ours']['observing_days']:.1f} d | |")
        a("")
        amps = ", ".join("%.4f" % m["amp"] for m in r["missed"])
        a(f"Missed published flares: {len(r['missed'])} (amplitudes {amps}). Energies: {r['energies']}.")
        a("")
    if R.get("gunther_energy_star"):
        r = R["gunther_energy_star"]
        a("### TIC 150359500, TESS sector 2, energies against Günther et al. 2020")
        a("")
        a("| Quantity | SetuHQ | Günther et al. 2020 |")
        a("|---|---|---|")
        a(f"| Flares | {r['ours']['flares']} events ({r['ours']['complex']} complex) | {r['published']['outbursts']} outbursts, {r['published']['flares']} components |")
        a(f"| Recall of published components | {_frac(r['recall'])} | |")
        a(f"| E_bol ours / published, per matched event, as they compute it (TIC Teff and radius) | {_ci(r['energy_ratio_ours_over_published'])} | |")
        a(f"| E_bol ours (primary route: TESS magnitude and distance) / published | {_ci(r.get('energy_ratio_primary_route_ours_over_published'))} | |")
        a(f"| Flux-inverted null | {r['ours']['inverted_null']} | |")
        a("")
    if R.get("proxima_medina"):
        r = R["proxima_medina"]
        a("### Proxima Cen, TESS sectors 11-12 (2 min), against Medina et al. 2020")
        a("")
        a("| Quantity | SetuHQ | Medina et al. 2020 |")
        a("|---|---|---|")
        a(f"| Flares | {r['ours']['flares']} ({r['ours']['complex']} complex) in {r['ours']['observing_days']:.1f} d | {r['published']['flares']} |")
        a(f"| Recall, all published flares | {_frac(r['recall'])} | |")
        for b in r["recall_by_published_ed"]:
            hi = f"{b['ed_hi_s']:g}" if b["ed_hi_s"] else "∞"
            a(f"| Recall, published ED {b['ed_lo_s']:g}-{hi} s | {b['recovered']}/{b['n']} = {b['fraction']:.2f} "
              f"[{b['ci95'][0]:.2f}, {b['ci95'][1]:.2f}] | |")
        a(f"| Our flares that are in their list | {r['ours_matched']['matched']}/{r['ours_matched']['of']} | |")
        a(f"| ED ours / published (median, 95% CI) | {_ci(r['ed_ratio_ours_over_published'])} | |")
        if r.get("ed_data_ratio_ours_over_published"):
            a(f"| ED summed over our detection window / published | {_ci(r['ed_data_ratio_ours_over_published'])} | |")
        a(f"| Recall, published ED ≥ 3 s (pooled) | {_frac(r['bright_recall'])} | |")
        a(f"| TESS-band energy, ours (model ED, primary luminosity) / published | {_ci(r.get('band_energy_ratio_ours_over_published'))} | |")
        a(f"| TESS-band energy measured as Medina et al. do (data ED × magnitude-route luminosity, Sullivan et al. 2015 zero point) / published | {_ci(r.get('band_energy_data_ed_magnitude_ratio_ours_over_published'))} | |")
        a(f"| Flux-inverted null | {r['ours']['inverted_null']} | |")
        a("")
        lum = r.get("luminosity") or {}
        a("Our default ED is the integral of the fitted template, which keeps the slow tail below the noise; Medina et al. "
          "sum the data over the flare (their §3.3), so the like-for-like energy uses our data-summed ED. Medina et al. "
          "derive the TESS-band luminosity from the TESS magnitude, the distance and Sullivan et al. (2015)'s zero point "
          "(4.03 × 10⁻⁶ erg s⁻¹ cm⁻²), as SetuHQ's magnitude route now does: "
          f"L_TESS = {_fmt(lum.get('l_band_magnitude_erg_s'), 3)} erg/s (TIC Tmag {lum.get('tmag')}, {_fmt(lum.get('distance_pc'), 3)} pc). "
          "TIC v8.2 has no Teff for Proxima Cen, so the Teff and radius route is unavailable here.")
        a("")
    if R.get("gj1243") or R.get("gj65"):
        a("### GJ 1243 and GJ 65 (no per-flare reference)")
        a("")
        a("| Star | Data | Flares | Complex | Inverted null | Note |")
        a("|---|---|---|---|---|---|")
        if R.get("gj1243"):
            r = R["gj1243"]
            a(f"| GJ 1243 | S14-15, 120 s, {r['ours']['observing_days']:.1f} d | {r['ours']['flares']} ({r['ours']['rate_per_day']:.2f}/d) | "
              f"{r['ours']['complex']} | {r['ours']['inverted_null']} | {r['reference']} |")
        if R.get("gj65"):
            r = R["gj65"]
            for ex in ("120", "20"):
                c = r.get(f"cadence_{ex}s")
                if c:
                    a(f"| GJ 65 | S30, {ex} s, {c['observing_days']:.1f} d | {c['flares']} | {c['complex']} | {c['inverted_null']} | |")
            a(f"| GJ 65 | 120 s flares found again at 20 s | {_frac(r['two_min_found_at_20s'])} | | | internal check only |")
        a("")
    if R.get("completeness"):
        a("### Completeness (injection and recovery on each star's own light curve)")
        a("")
        a("| Star | Injected | Recovered | 90% complete above amplitude | above ED (s) | above E_bol (erg) | recovered ED / injected | FFD α above the 90% energy | vs log-normal |")
        a("|---|---|---|---|---|---|---|---|---|")
        for k, r in R["completeness"].items():
            pl = r.get("ffd_power_law") or {}
            ln = r.get("ffd_vs_lognormal") or {}
            al = f"{pl['alpha']:.2f} ± {pl['alpha_err']:.2f} (n = {pl['n']})" if pl.get("alpha") else "n/a"
            lnx = f"R = {ln['R']:.2f}, p = {ln['p_value']:.2f}: {ln['preferred']}" if ln.get("R") is not None else "n/a"
            a(f"| {k} | {r['n_injected']} | {r['recovered']} | {_fmt(r['amplitude_90pct'], 3)} | {_fmt(r['ed_90pct_s'], 3)} | "
              f"{_fmt(r['energy_90pct_erg'], 3)} | {_ci(r['recovered_ed_ratio'])} | {al} | {lnx} |")
        a("")
        a("Completeness curves by amplitude, ED and energy, with Wilson 95% intervals per bin, are in "
          "`stellar_validation.json` under `results.completeness`.")
        a("")
    if R.get("false_split"):
        r = R["false_split"]
        a("### False splits: single flares that come back as several components")
        a("")
        a("| Star | Injected | Recovered clean (blends excluded) | Split into ≥ 2 | Rate [95% CI] | Real flares (complex) |")
        a("|---|---|---|---|---|---|")
        for k, v in r.items():
            if k == "validation_pooled":
                continue
            a(f"| {k}{' (tuning star)' if v.get('tuning_set') else ''} | {v['injected']} | {v['recovered_clean']} ({v['blends_excluded']} blends) | "
              f"{v['split']} | {_fmt(v['rate'])} [{v['ci95'][0]:.2f}, {v['ci95'][1]:.2f}] | {v['real_flares']} ({v['real_complex']}) |")
        vp = r["validation_pooled"]
        a(f"| **Proxima + GJ 1243** | | {vp['recovered_clean']} | {vp['split']} | {_fmt(vp['rate'])} [{vp['ci95'][0]:.2f}, {vp['ci95'][1]:.2f}] | |")
        a("")
        a("Before the review fixes (no effective-N correction, no visibility rule), single flares on AU Mic came back "
          "split 41% of the time (21 of 51, blends included); the AR(1) effective-N correction alone gave 39%.")
        a("")
    if R.get("quiet_stars"):
        r = R["quiet_stars"]
        a("### Nulls: quiet stars and flux-inverted light curves")
        a("")
        a("| Star | Sectors | Days | Detections (false positives) | Inverted null |")
        a("|---|---|---|---|---|")
        for s in r["stars"]:
            a(f"| {s['star']} | {s.get('sectors')} | {_fmt(s.get('observing_days'), 3)} | {s.get('flares_detected')} | {s.get('inverted_null')} |")
        a(f"| **all** | | {r['total_days']:.1f} | {r['total_detections']} ({_fmt(r['false_positive_rate_per_day_upper'], 3)} per day) | |")
        a("")
    a("## Pulsations")
    a("")
    if R.get("beta_pic"):
        r = R["beta_pic"]
        a("### β Pic, TESS sectors 5-7, against Zieba et al. 2019")
        a("")
        a("| Quantity | SetuHQ | Zieba et al. 2019 |")
        a("|---|---|---|")
        a(f"| Frequencies at S/N ≥ 4 | {r['n_significant']} | {r['published_n']} |")
        a(f"| Published recovered within 3σ | {r['recall_all_strict']:.2f} | |")
        a(f"| Published recovered within 1/T | {r['recall_all_loose']:.2f} [{r['recall_ci95_loose'][0]:.2f}, {r['recall_ci95_loose'][1]:.2f}] | |")
        a(f"| 10 strongest recovered (3σ / 1/T) | {r['recall_top10_strict']:.2f} / {r['recall_top10_loose']:.2f} | |")
        a(f"| Ours that match a published frequency (1/T) | {_fmt(r['ours_matched_fraction_loose'])} | |")
        a(f"| Type | {r['type']['label']} ({r['type']['confidence']}) | δ Scuti |")
        a("")
    if R.get("hr10_tess"):
        r = R["hr10_tess"]
        a("### HR 10, TESS sectors 2 and 29, against Salmon et al. 2024")
        a("")
        a("| Sector | Ours (S/N ≥ 4) | Ours (S/N ≥ 5) | Published (S/N ≥ 5) | Recall 3σ | Recall 1/T [95% CI] | Top-10 recall 3σ / 1/T | Amplitude ours / published |")
        a("|---|---|---|---|---|---|---|---|")
        for sec, x in r["sectors"].items():
            a(f"| {sec} | {x['n_significant']} | {x['n_snr5']} | {x['published_n']} | {x['recall_all_strict']:.2f} | "
              f"{x['recall_all_loose']:.2f} [{x['recall_ci95_loose'][0]:.2f}, {x['recall_ci95_loose'][1]:.2f}] | "
              f"{x['recall_top10_strict']:.2f} / {x['recall_top10_loose']:.2f} | {_ci(x['amplitude_ratio_ours_over_published'])} |")
        a("")
        g = r["granulation"]
        a(f"Granulation-like background (S29): our Harvey characteristic frequencies {', '.join(f'{b:.0f}' for b in g['ours_b_uhz_s29'])} µHz "
          f"(exponents {', '.join(f'{c:.1f}' for c in g['ours_exponent_s29'])}); with Salmon et al.'s estimator (one-day "
          f"periodograms averaged, one Harvey profile): {_fmt(g.get('averaged_estimator_b_uhz_s29'), 4)} µHz; Salmon et al.: "
          f"b = {g['published_b_uhz_s29']} µHz. {g['note']}. A mismatch here is reported as one (check hr10_granulation), not explained away.")
        for sec, x in r["sectors"].items():
            ch_ = x.get("combination_chance") or {}
            a(f"- S{sec}: {x.get('n_combinations', 0)} of the S/N ≥ 4 frequencies flagged as possible combinations; a random "
              f"frequency would be flagged with probability {_fmt(ch_.get('chance_rate'), 3)} (tolerance {_fmt(ch_.get('tolerance'), 3)} d⁻¹, "
              f"{ch_.get('n_parents')} parents), about {_fmt(ch_.get('expected_chance_flags'), 2)} chance flags expected.")
        nul = r["sectors"]["29"].get("null") or []
        for n_ in nul:
            a(f"- Null, {n_['kind']} surrogates of the S29 residual: {n_['mean_false_per_lightcurve']:.2f} false frequencies per light curve "
              f"on average, {n_['fraction_with_any']:.0%} of {n_['n_surrogates']} surrogates with any.")
        a(f"- Type: {r['sectors']['29']['type']['label']} ({r['sectors']['29']['type']['confidence']} confidence): "
          + "; ".join(r["sectors"]["29"]["type"]["reasons"]) + ".")
        a("")
    if R.get("hr10_cheops"):
        r = R["hr10_cheops"]
        a("### HR 10, CHEOPS (public DRP visits)")
        a("")
        if r.get("error"):
            a(f"Not run: {r['error']}.")
        else:
            c = r["combined"]
            a(f"Three visits together ({c['baseline_days']:.1f} d, {c['n_points']} points): {c['n_significant']} frequencies at "
              f"S/N ≥ 4; f1, f2 found: {c['f1_f2_recovered']}; {_fmt(c['ours_matched_fraction'])} of ours match Salmon et al.'s "
              f"TESS S29 list within 1/T, which recovers {_fmt(c['recall_tess_s29_published'])} of that list "
              f"({_fmt(c['recall_top10'])} of its 10 strongest). Background b: {', '.join(f'{b:.0f}' for b in c['background_b_uhz'])} µHz.")
            a("")
            a("| Visit | Programme | Days | Frequencies (S/N ≥ 4) | f1, f2 found | Decorrelation terms |")
            a("|---|---|---|---|---|---|")
            for v in r["visits"]:
                a(f"| {v['file_key']} | {v['programme']} | {v['baseline_days']:.2f} | {v['n_significant']} | {v['f1_f2_recovered']} | "
                  f"{', '.join(v['terms']) or 'none'} |")
            a("")
            a(f"{r['note']} Their CHEOPS granulation frequency (first visit): {r['published_granulation_b_uhz_cheops_visit1']} µHz.")
        a("")
    if R.get("toi197"):
        r = R["toi197"]
        o = r["ours"]
        a("### TOI-197, TESS sector 2, solar-like oscillations, against Huber et al. 2019")
        a("")
        a("| Quantity | SetuHQ (bootstrap 1σ) | Huber et al. 2019 | z |")
        a("|---|---|---|---|")
        if o.get("detected"):
            a(f"| numax (µHz) | {o['numax_uhz']:.1f} ± {_fmt(o['numax_err_uhz'], 3)} | {r['published']['numax_uhz'][0]} ± {r['published']['numax_uhz'][1]} | {r.get('numax_z', float('nan')):.2f} |")
            a(f"| Δν (µHz) | {_fmt(o['dnu_uhz'], 4)} ± {_fmt(o['dnu_err_uhz'], 3)} | {r['published']['dnu_uhz'][0]} ± {r['published']['dnu_uhz'][1]} | {r.get('dnu_z', float('nan')):.2f} |")
        else:
            a(f"| detection | none: {o.get('why')} | numax {r['published']['numax_uhz']} | |")
        a("")
        a(f"{r['data_note']}. Envelope ΔBIC {o.get('delta_bic_envelope', 0):.1f}. The Δν search window is 0.7-1.4 × the "
          f"scaling value ({_fmt(o.get('dnu_expected_uhz'), 3)} µHz), about ±6 µHz around the published value, so the "
          "tighter check asks for agreement within 1 µHz; our bootstrap uncertainty is large because the bootstrap "
          "redraws a smoothed spectrum.")
        a("")
    a("## CHEOPS")
    a("")
    if R.get("cheops_flares"):
        r = R["cheops_flares"]
        s = r["summary"]
        a("### CHEOPS M-dwarf flares, against Poyatos et al. 2025 (aggregate only; gated)")
        a("")
        a(f"Data: {r['data']}. Targets and visits used: "
          + "; ".join(f"{t['star']} {t.get('used', 0)} of {t.get('public_visits', '?')} public" for t in r["targets"]) + ".")
        a("")
        ig = s["injection_gate"]
        a(f"**Gates.** Injected flares with {ig['selection']}: {ig['recovered']}/{ig['of']} recovered "
          f"[{ig['ci95'][0]:.2f}, {ig['ci95'][1]:.2f}] (all injections: {ig['all_recovered']}/{ig['all_injected']}). "
          f"Flux-inverted null with the real flares masked: {s['original']['inverted_null']} (original) and "
          f"{s['denoised']['inverted_null']} (denoised) against {s['original']['flares']} and {s['denoised']['flares']} flares "
          f"(largest fraction {_fmt(s['null_fraction'])}). False splits of injected single flares: "
          f"{s['false_split']['split']}/{s['false_split']['recovered_clean']}. The comparisons below count only if both gates pass.")
        a("")
        a("| Quantity | SetuHQ original | SetuHQ denoised | Poyatos et al. 2025 (journal) |")
        a("|---|---|---|---|")
        o, d = s["original"], s["denoised"]
        a(f"| Flares | {o['flares']} in {o['observing_days']:.2f} d | {d['flares']} | 349 on 63 M dwarfs (imagettes) |")
        g = s.get("denoising_gain")
        a(f"| Gain from denoising | | {g:+.0%} | +34% |" if g is not None else "| Gain from denoising | | n/a | +34% |")
        a(f"| Complex fraction | {_fmt(o['complex_fraction'])} {o['complex_ci95'] and [round(x, 2) for x in o['complex_ci95']]} | "
          f"{_fmt(d['complex_fraction'])} {d['complex_ci95'] and [round(x, 2) for x in d['complex_ci95']]} | ≈ 0.40 |")
        for key in ("original", "denoised"):
            pl = s[key].get("power_law_above_median_energy")
            if pl and pl.get("alpha"):
                s[key]["_al"] = f"{pl['alpha']:.2f} ± {pl['alpha_err']:.2f} (n = {pl['n']})"
        a(f"| Power-law α (above our median energy) | {o.get('_al', 'n/a')} | {d.get('_al', 'n/a')} | 1.92 ± 0.07 |")
        for key in ("original", "denoised"):
            ln = s[key].get("vs_lognormal") or {}
            s[key]["_ln"] = f"R = {ln['R']:.2f}, p = {ln['p_value']:.2f}: {ln['preferred']}" if ln.get("R") is not None else "n/a"
        a(f"| Power law vs log-normal | {o['_ln']} | {d['_ln']} | log-normal preferred |")
        a("")
        a("The arXiv v2 numbers differ (291 flares on 62 stars, ~42% complex, +35%, α = 1.99 ± 0.10); the journal "
          "version's are used. Without a CHEOPS completeness curve per star, the power law is fitted above the median "
          "energy, not above a 90% completeness energy as Poyatos et al. do; the indices are not strictly comparable. "
          "Energies use the TIC radius and, where the TIC has no Teff, the Teff from the CHEOPS archive (labelled).")
        a("")
    if R.get("denoise_grid"):
        a("### Denoising parameters by injection (as Poyatos et al. chose theirs)")
        a("")
        for key, rows in R["denoise_grid"].items():
            if not isinstance(rows, list):
                a(f"- {key}: {rows}")
                continue
            a(f"**{key}**")
            a("")
            a("| Wavelet | Level | Recovered | Inverted null |")
            a("|---|---|---|---|")
            for x in rows:
                a(f"| {x['wavelet'] or 'none'} | {x['level'] or ''} | {x['recovered']}/{x['injected']} = {x['fraction']:.2f} "
                  f"[{x['ci95'][0]:.2f}, {x['ci95'][1]:.2f}] | {x['inverted_false_positives']} |")
            a("")

    if R.get("cheops_pycheops"):
        r = R["cheops_pycheops"]
        a("### Detrending against pycheops (Maxted et al. 2022), same 15 decorrelation terms")
        a("")
        a("| Visit | Programme | Points | Same input: rms difference (ppm), correlation | Same input: rms ours / pycheops (ppm) | End to end: rms difference, correlation | Raw inputs (DACE vs pycheops' DRP product) | End to end: rms ours / pycheops (ppm) |")
        a("|---|---|---|---|---|---|---|---|")
        for v in r["visits"]:
            if "same_input" not in v:
                a(f"| {v['file_key']} | | | {v.get('why')} | | | | |")
                continue
            si, ee, rw = v["same_input"], v["end_to_end"], v["raw_inputs"]
            a(f"| {v['file_key']} | {v['programme']} | {v['points_matched']} | {si['rms_difference_ppm']:.2f}, {si['correlation']:.4f} | "
              f"{v.get('same_input_rms_ours_ppm', float('nan')):.0f} / {v['rms_pycheops_ppm']:.0f} | "
              f"{ee['rms_difference_ppm']:.0f}, {ee['correlation']:.3f} | {rw['rms_difference_ppm']:.0f}, {rw['correlation']:.4f} | "
              f"{v['rms_ours_ppm']:.0f} / {v['rms_pycheops_ppm']:.0f} |")
        a("")
        a("On the same input, the linear decorrelation is the same model and gives the same light curve where both fits "
          "reach the least-squares optimum; where they differ, the one with the larger rms (on the same points and terms) "
          "is off the optimum. End to end, the inputs differ: pycheops reads the DRP FITS product and subtracts the "
          "contamination estimate, SetuHQ reads DACE's DRP arrays and keeps every unflagged point, so the detrended "
          "curves differ by about the difference of their inputs.")
        a("")
    a("## What is not validated")
    a("")
    for u in rec["unvalidated"]:
        a(f"- {u}")
    a("")
    a("## CHEOPS acknowledgement, credit and disclaimer")
    a("")
    c = rec["cheops_credit"]
    a(c["acknowledgement"])
    a("")
    for x in c["credits"]:
        a(f"- {x['programme']}, {x['file_key']} (obs id {x['obs_id']}, DRP {x['drp_version']}): {x['credit']}")
    a("")
    a("References: " + "; ".join(c["citations"]) + ".")
    a("")
    a(c["dace_acknowledgement"])
    a("")
    a(f"**{c['disclaimer']}** {c['commercial_use']}")
    a("")
    a("## References")
    a("")
    for k, v in rec["references"].items():
        if v:
            a(f"- {v}")
    a("- Günther, M. N., et al. 2020, AJ, 159, 60 (VizieR J/AJ/159/60)")
    a("- Medina, A. A., et al. 2020, ApJ, 905, 107 (VizieR J/ApJ/905/107)")
    a("- Maxted, P. F. L., et al. 2022, MNRAS, 514, 77 (pycheops)")
    a("")
    return "\n".join(x for x in L if x is not None) + "\n"

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Build docs/results/stellar_validation_v4.json and .md, and docs/results/stellar_figures_v4.json, from the item cache
of scripts/stellar_validation_v4.py.

The status rule is protocol v4's (the same as v3's): a capability is "validated" when every counted check passes,
"partly validated" when more than half do, and otherwise "not validated", always with "k of n checks pass". Counted
checks use held-out targets only; a check whose item did not run counts as not passing. Every number is copied from
the item records; nothing is recomputed here. The figures show the first held-out target of each capability in the
protocol's order, whatever its result.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from stellar_validation_report import _apply, status_of  # noqa: E402  (the same rule and comparisons as v3)

CAPS = ("binaries", "rotation", "transients")


def _lo(d):
    return d["ci95"][0]


# Where each protocol check's number is in its item's result (thresholds and pass rules are in the protocol file).
METRICS = {
    ("eb_catalogue", "detect_ci_low"): lambda r: _lo(r["held_out"]["detected"]),
    ("eb_catalogue", "period_ci_low"): lambda r: _lo(r["held_out"]["period"]),
    ("eb_catalogue", "depth_ratio_ci"): lambda r: r["held_out"]["depth_ratio"]["ci95"],
    ("eb_catalogue", "secphase_ci_low"): lambda r: _lo(r["held_out"]["secondary_phase"]),
    ("eb_catalogue", "width_spearman"): lambda r: r["held_out"]["width_spearman"],
    ("eb_catalogue", "morph_ci_low"): lambda r: _lo(r["held_out"]["morphology"]),
    ("eb_contrast", "false_eb"): lambda r: r["false_eb"],
    ("eb_injection", "recovery_ci_low"): lambda r: _lo(r["recovery"]),
    ("rot_catalogue", "detect_ci_low"): lambda r: _lo(r["held_out"]["detected"]),
    ("rot_catalogue", "match_ci_low"): lambda r: _lo(r["held_out"]["match"]),
    ("rot_catalogue", "alias_ci_low"): lambda r: _lo(r["held_out"]["alias"]),
    ("rot_catalogue", "coverage"): lambda r: r["held_out"]["coverage"]["fraction"],
    ("rot_null", "false_detections"): lambda r: r["false_detections"],
    ("rot_injection", "recovery_ci_low"): lambda r: _lo(r["recovery"]),
    ("tr_supernovae", "detect_ci_low"): lambda r: _lo(r["held_out"]["detected"]),
    ("tr_supernovae", "peak_time_ci_low"): lambda r: _lo(r["held_out"]["peak_time"]),
    ("tr_supernovae", "rise_ratio_ci"): lambda r: r["held_out"]["rise_ratio"]["ci95"],
    ("tr_supernovae", "peak_mag_diff_ci"): lambda r: r["held_out"]["peak_mag_diff"]["ci95"],
    ("tr_supernovae", "sn_like_ci_low"): lambda r: _lo(r["held_out"]["sn_like"]),
    ("tr_supernovae", "control_sn_like_rate"): lambda r: r["held_out"]["control_sn_like_rate"],
    ("tr_flares", "flare_like_ci_low"): lambda r: _lo(r["flare_like"]),
    ("tr_null", "fp_per_day"): lambda r: r["fp_per_day"],
    ("tr_screen", "screened_ci_low"): lambda r: _lo(r["screened"]),
}

UNVALIDATED = [
    "Planet vetting: unchanged. The eclipsing-binary module's vetting hints are advisory, no vetting decision uses "
    "them, and they were not evaluated; using them in vetting needs its own pre-registered evaluation.",
    "Eclipse widths: Prša et al. (2022) give 2-Gaussian widths, SetuHQ a full width at half depth, so only their rank "
    "order is compared. The e·cosω values are first-order hints from the secondary's phase, not compared with "
    "radial-velocity orbits.",
    "Rotation: one sector per star, as the protocol fixes; periods longer than about 13 days are not measured, and "
    "stitching sectors (with care for sector-to-sector offsets) is not done and not validated. Canto Martins et al. "
    "(2020) used every sector available to them.",
    "Transients: one TESScut sector per supernova, as the protocol fixes. When first light falls before that sector "
    "begins, the reference image already holds supernova light, so the rise time and the peak brightness are "
    "measured from a non-zero floor; the supernovae compared are all type Ia, so the extragalactic class hint is not "
    "tested on tidal disruption events or other transients.",
    "Scattered light: no labelled real sample was found; the screen (quality flags and control apertures) is "
    "described and exercised on synthetic events and the supernova cutouts' control apertures, not validated "
    "against a catalogue of scattered-light events.",
    "Asteroid crossings: screened by shape and, in cutouts, by a moving centroid; no catalogue of TESS asteroid "
    "crossings was compared (Fausnaugh et al. 2023's asteroid flags excluded those supernovae from the sample).",
]
LABELS = ["An eclipsing binary or a transient SetuHQ finds is a candidate, never new and never confirmed.",
          "Morphology and transient classes are heuristic hints from the light curve alone."]


def _items(items_dir: Path) -> dict:
    return {p.stem: json.loads(p.read_text()) for p in sorted(Path(items_dir).glob("*.json"))}


def _checks(protocol, items):
    rows = []
    for c in protocol["checks"]:
        row = {"capability": c["capability"], "check": c["id"], "item": c["item"], "text": c["text"]}
        rec = items.get(c["item"])
        if not rec or rec.get("status") != "ok":
            rows.append({**row, "result": "not run", "why": (rec or {}).get("error", "item not run")})
            continue
        try:
            value = METRICS[(c["item"], c["metric"])](rec["result"])
            ok = bool(_apply(c["op"], value, c["threshold"]))
            rows.append({**row, "value": value, "result": "pass" if ok else "fail"})
        except (KeyError, TypeError, IndexError, ZeroDivisionError, ValueError) as exc:
            rows.append({**row, "result": "not run", "why": f"{type(exc).__name__}: {exc}"})
    return rows


def _summary(name, res):
    """What the report keeps of an item: its numbers, without per-target light curves (those feed the figures)."""
    drop_row = {"lc_2h", "lc_6h", "phase_curve_100", "candidates", "trace"}
    out = {}
    for k, v in res.items():
        if k == "rows" and isinstance(v, list):
            out[k] = [{kk: vv for kk, vv in r.items() if kk not in drop_row} for r in v]
        elif k == "matched" and isinstance(v, list):
            out["matched_count"] = len(v)
        else:
            out[k] = v
    return out


def _first_held_out(rows, key_ok=None):
    for r in rows:
        if r.get("split") == "held_out":
            return r
    return None


def figures(items, protocol) -> dict:
    """The three figures' data: the first held-out target of each capability (protocol order), whatever its result."""
    from setuhq.stellar_io import tic_star

    cache = Path(__import__("os").environ.get("SETUHQ_CACHE", ROOT / "cache"))
    out = {"kind": "setuhq-stellar-figures-v4/1",
           "rule": "Each figure shows the first held-out target of its capability in protocol v4's order, whatever its result.",
           "licence": "Derived from public TESS data (MAST); no CHEOPS data."}
    ebr = ((items.get("eb_catalogue") or {}).get("result") or {}).get("rows") or []
    e = _first_held_out(ebr)
    if e and e.get("phase_curve_100"):
        out["binary"] = {"tic": e["tic"], "sector": e["sector"], "file_sha256": e.get("file_sha256"),
                         "phase": e["phase_curve_100"]["phase"], "flux": [None if v is None else round(v, 5) for v in e["phase_curve_100"]["flux"]],
                         "ours": {k: e.get(k) for k in ("eb_candidate", "period", "period_ratio", "period_match", "morphology", "depth_ratio")}
                         | {"primary": e.get("primary"), "secondary": e.get("secondary")},
                         "catalogue": e["catalogue"], "tic_values": tic_star(e["tic"], cache),
                         "source": f"TESS sector {e['sector']} SPOC 2-minute PDCSAP light curve of TIC {e['tic']} (MAST), folded on SetuHQ's period; "
                                   "the catalogue values are Prša et al. (2022, ApJS 258, 16)"}
    rr = ((items.get("rot_catalogue") or {}).get("result") or {}).get("rows") or []
    r = _first_held_out(rr)
    if r and r.get("lc_2h"):
        out["rotation"] = {"tic": r["tic"], "sector": r["sector"], "file_sha256": r.get("file_sha256"), "lc_2h": r["lc_2h"],
                           "ours": {k: r.get(k) for k in ("detected", "period", "period_err", "candidate_period", "alias", "rule")},
                           "published": r["published"], "published_err": r["published_err"], "tic_values": tic_star(r["tic"], cache),
                           "source": f"TESS sector {r['sector']} SPOC 2-minute PDCSAP light curve of TIC {r['tic']} (MAST), 2-hour bins; "
                                     "the published period is Canto Martins et al. (2020, ApJS 250, 20)"}
    sr = ((items.get("tr_supernovae") or {}).get("result") or {}).get("rows") or []
    s = _first_held_out(sr)
    if s and s.get("lc_6h"):
        out["transient"] = {"name": s["name"], "other": s["other"], "sector": s.get("sector"), "lc_6h": s["lc_6h"],
                            "matched": s.get("matched"), "published": s["published"], "cutout_sha256": s.get("cutout_sha256"),
                            "aperture_correction_source": s.get("aperture_correction_source"),
                            "source": f"TESS sector {s.get('sector')} full-frame images (SPOC) through MAST's TESScut, 11 x 11 pixels, "
                                      "difference photometry in a 3 x 3 aperture, 6-hour bins; the published peak and first light are "
                                      "Fausnaugh et al. (2023, ApJ 956, 108)"}
    return out


def write_report(items_dir, out_json, out_md, out_fig, protocol, protocol_sha, fingerprint, *, protocol_file, protocol_commit):
    items = _items(items_dir)
    checks = _checks(protocol, items)
    caps = {}
    for cap in CAPS:
        cs = [c for c in checks if c["capability"] == cap]
        k = sum(c["result"] == "pass" for c in cs)
        caps[cap] = {**status_of(k, len(cs)), "passed": k, "of": len(cs), "inconclusive": 0, "tuning_set": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "kind": "setuhq-stellar-validation-v4/1", "generated_at": now,
        "protocol_file": str(protocol_file), "protocol_sha256": protocol_sha, "protocol_commit": protocol_commit,
        "protocol_version": protocol["version"], "protocol_frozen": protocol["frozen"], "seed": protocol["seed"],
        "status_rule": protocol["status_rule"], "code_fingerprint": fingerprint,
        "capabilities": caps, "checks": checks, "unvalidated": UNVALIDATED,
        "items": {k: {kk: v.get(kk) for kk in ("status", "code_fingerprint", "code_files", "protocol_sha256", "finished_at",
                                                "seconds", "error")} for k, v in items.items()},
        "results": {k: _summary(k, v.get("result") or {}) for k, v in items.items()},
        "references": {"binaries": protocol["binaries"]["reference"], "rotation": protocol["rotation"]["reference"],
                       "transients": protocol["transients"]["reference"],
                       "flare_contrast": protocol["transients"]["flare_contrast"]["reference"]},
        "labels": LABELS,
    }
    Path(out_json).write_text(json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False) + "\n")
    Path(out_md).write_text(markdown(record, items, protocol))
    Path(out_fig).write_text(json.dumps(figures(items, protocol), indent=1, ensure_ascii=False, allow_nan=False) + "\n")
    print(f"wrote {out_json}, {out_md} and {out_fig}: " + ", ".join(f"{k} {v['label']}" for k, v in caps.items()))


def _f(x, nd=2):
    if x is None:
        return "n/a"
    if isinstance(x, list):
        return "[" + ", ".join(_f(v, nd) for v in x) + "]"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _fr(d):
    if not d or d.get("of") in (None, 0):
        return "0 of 0"
    lo, hi = d["ci95"]
    return f"{d['k']} of {d['of']} = {d['k'] / d['of']:.2f} (95% CI {lo:.2f}-{hi:.2f})"


def _bm(d, nd=2):
    if not d or d.get("median") is None:
        return "n/a"
    c = d.get("ci95")
    return f"{d['median']:.{nd}f}" + (f" (95% CI {c[0]:.{nd}f} to {c[1]:.{nd}f})" if c else "") + f", n = {d['n']}"


def markdown(rec, items, protocol) -> str:
    R = {k: (v.get("result") or {}) for k, v in items.items()}
    L = []
    a = L.append
    a("<!-- Generated by scripts/stellar_validation_v4.py --report from the item records; do not edit by hand. -->")
    a("# Stellar validation v4: eclipsing binaries, rotation and transients")
    a("")
    a(f"Protocol v4 (`{rec['protocol_file']}`, sha256 `{rec['protocol_sha256'][:16]}…`), frozen {rec['protocol_frozen']} and "
      f"committed on its own in `{(rec['protocol_commit'] or 'not committed')[:12]}` before any v4 code or run; seed {rec['seed']}. "
      f"Code fingerprint `{rec['code_fingerprint'][:16]}…`. Generated {rec['generated_at']}.")
    a("")
    a("Targets were drawn from the published catalogues by seeded rules on catalogue metadata alone, each split into a "
      "tuning set (used while the methods were written) and a held-out set (run once). Only held-out targets count. "
      f"Rule: {rec['status_rule']}")
    a("")
    a("| Capability | Status |")
    a("|---|---|")
    for cap, name in (("binaries", "Eclipsing binaries"), ("rotation", "Rotation"), ("transients", "Transients")):
        a(f"| {name} | **{rec['capabilities'][cap]['label']}** |")
    a("")
    a("## Every counted check")
    a("")
    a("| Capability | Check | Value | Result |")
    a("|---|---|---|---|")
    for c in rec["checks"]:
        a(f"| {c['capability']} | {c['text']} | {_f(c.get('value'), 3)} | {c['result']}{(' (' + c['why'] + ')') if c.get('why') else ''} |")
    a("")
    eb = R.get("eb_catalogue") or {}
    if eb:
        h, t = eb["held_out"], eb["tuning"]
        a("## Eclipsing binaries")
        a("")
        a(f"Reference: {protocol['binaries']['reference']}.")
        a("")
        a(f"- Held out ({h['n']} EBs): flagged {_fr(h['detected'])}; period within 0.5% {_fr(h['period'])}; "
          f"aliases: {h['aliases']['half']} at half, {h['aliases']['double']} at double the catalogue period.")
        a(f"- Primary depth, ours/catalogue: {_bm(h['depth_ratio'])}.")
        a(f"- Secondary phase within 0.01: {_fr(h['secondary_phase'])}; a secondary found at all: {_fr(h['secondary_found'])}.")
        a(f"- Width rank correlation (Spearman, {h['width_pairs']} pairs): {_f(h['width_spearman'])}. "
          f"Morphology (detached or not) agrees: {_fr(h['morphology'])}.")
        a(f"- Tuning split ({t['n']} EBs, not counted): flagged {_fr(t['detected'])}; period {_fr(t['period'])}.")
        if R.get("eb_contrast"):
            c = R["eb_contrast"]
            a(f"- Contrast set: {c['false_eb']} of {c['n']} planet hosts and quiet stars flagged: "
              + "; ".join(f"{r['star']} {'flagged' if r['eb_candidate'] else 'not flagged'}" for r in c["rows"]) + ".")
        if R.get("eb_injection"):
            i = R["eb_injection"]
            a(f"- Injected detached EBs: period within 0.5% {_fr(i['recovery'])}; flagged {_fr(i['flagged'])}.")
        a("")
        a("| TIC | Split | Catalogue P (d) | Ours P (d) | Flagged | Morph (cat.) | Ours | Depth ratio | Sec. phase diff |")
        a("|---|---|---|---|---|---|---|---|---|")
        for r in eb["rows"]:
            a(f"| {r['tic']} | {r['split']} | {r['catalogue']['period_d']:.5f} | {_f(r.get('period'), 5)} | {r['eb_candidate']} | "
              f"{r['catalogue']['morph']} | {r.get('morphology', 'n/a')} | {_f(r.get('depth_ratio'))} | {_f(r.get('secondary_phase_diff'), 4)} |")
        a("")
    ro = R.get("rot_catalogue") or {}
    if ro:
        h, t = ro["held_out"], ro["tuning"]
        a("## Rotation")
        a("")
        a(f"Reference: {protocol['rotation']['reference']}. {protocol['rotation']['limit']}")
        a("")
        a(f"- Held out ({h['n']} stars): detected {_fr(h['detected'])}; within 10% {_fr(h['match'])}; within 10% of the period, "
          f"half or double {_fr(h['alias'])}; uncertainty covers the difference (2σ) {_fr(h['coverage'])}.")
        a(f"- Ours/published among detections: {_bm(h['ratio'])}.")
        a(f"- Tuning split ({t['n']} stars, not counted): within 10% {_fr(t['match'])}.")
        if R.get("rot_null"):
            n = R["rot_null"]
            a(f"- Quiet stars: {n['false_detections']} of {n['n']} with a detected period.")
        if R.get("rot_injection"):
            i = R["rot_injection"]
            lp = i["long_period"]
            a(f"- Injected spot modulation (1-12 d): within 10% {_fr(i['recovery'])}; {i['aliases']} at half or double. "
              f"Beyond the limit (13-30 d, reported only): {lp['reported_beyond_limit']} of {lp['n']} reported as beyond it, "
              f"{lp['reported_as_a_period']} reported as a period (an alias inside the range).")
        a("")
        a("| TIC | Split | Published P (d) | Ours P (d) | Detected | Note |")
        a("|---|---|---|---|---|---|")
        for r in ro["rows"]:
            a(f"| {r['tic']} | {r['split']} | {r['published']} ± {r['published_err']} | {_f(r.get('period'), 3)}"
              f"{(' ± ' + _f(r.get('period_err'), 3)) if r.get('period_err') else ''} | {r.get('detected')} | "
              f"{(r.get('rule') or '; '.join(r.get('reasons') or []) or r.get('error', ''))[:120]} |")
        a("")
    sn = R.get("tr_supernovae") or {}
    if sn:
        h, t = sn["held_out"], sn["tuning"]
        a("## Transients")
        a("")
        a(f"Reference: {protocol['transients']['reference']}")
        a("")
        a(f"- Held out ({h['n']} supernovae): a candidate within 10 d of the published peak {_fr(h['detected'])} "
          f"(not marked as a likely false alarm: {_fr(h['detected_not_false_alarm'])}); peak within 2 d {_fr(h['peak_time'])}.")
        a(f"- Rise time ours/theirs ({h['rise_measured']} with a first-light fit): {_bm(h['rise_ratio'])}. "
          f"Peak magnitude ours minus theirs: {_bm(h['peak_mag_diff'])}.")
        a(f"- Class hint extragalactic-transient-like among detections: {_fr(h['sn_like'])}.")
        a(f"- Control apertures ({h['control_apertures']}): with an extragalactic-like candidate {_f(h['control_sn_like_rate'])}; "
          f"with any candidate {_f(h['control_any_candidate_rate'])}.")
        a(f"- Tuning split ({t['n']} supernovae, not counted): detected {_fr(t['detected'])}; peak within 2 d {_fr(t['peak_time'])}.")
        if R.get("tr_flares"):
            f = R["tr_flares"]
            a(f"- Proxima Cen S11-12: {f['matched_candidates']} candidates match one of Medina et al.'s {f['medina_flares']} flares; "
              f"flare-like {_fr(f['flare_like'])}; classes {f['matched_classes']}. AU Mic S1 (tuning): {f['aumic_tuning']['by_class']}.")
        if R.get("tr_null"):
            n = R["tr_null"]
            a(f"- Quiet stars: {n['not_false_alarm']} candidates not marked as false alarms in {n['days']:.1f} days "
              f"({_f(n['fp_per_day'], 3)} per day).")
        if R.get("tr_screen"):
            s = R["tr_screen"]
            a(f"- Injected false alarms: marked {_fr(s['screened'])} (momentum dumps {_fr(s['by_kind']['momentum_dump'])}; "
              f"asteroid-like bumps {_fr(s['by_kind']['asteroid'])}); found at all {_fr(s['found'])}.")
        a("")
        a("| Supernova | Split | Sector | Published peak (BTJD) | Ours | Δt (d) | Rise ratio | ΔT (mag) | Class hint |")
        a("|---|---|---|---|---|---|---|---|---|")
        for r in sn["rows"]:
            m = r.get("matched") or {}
            a(f"| {r['name']} ({r['other']}) | {r['split']} | {r.get('sector', 'n/a')} | {r['published']['t_peak_btjd']} | "
              f"{_f(m.get('t_peak'))} | {_f(r.get('peak_time_diff'))} | {_f(r.get('rise_ratio'))} | {_f(r.get('peak_mag_diff'))} | "
              f"{m.get('class_hint', r.get('error', 'not detected'))} |")
        a("")
    a("## Not validated")
    a("")
    for x in rec["unvalidated"]:
        a(f"- {x}")
    a("")
    a("## Data and credit")
    a("")
    a("Public TESS data from MAST: SPOC 2-minute light curves (Jenkins et al. 2016) and TESScut cutouts of SPOC "
      "full-frame images (Brasseur et al. 2019). TESS is funded by NASA's Science Mission Directorate. Published values: "
      "Prša et al. 2022 (ApJS 258, 16), Canto Martins et al. 2020 (ApJS 250, 20), Fausnaugh et al. 2023 (ApJ 956, 108) "
      "and Medina et al. 2020 (ApJ 905, 107), through VizieR (CDS, Strasbourg). No CHEOPS data are used.")
    a("")
    for x in rec["labels"]:
        a(f"- {x}")
    return "\n".join(L) + "\n"

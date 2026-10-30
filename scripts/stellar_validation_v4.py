#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Validate SetuHQ's eclipsing-binary, rotation and transient capabilities against published results, under the
frozen protocol v4 (docs/results/stellar_validation_protocol_v4.json), and write docs/results/
stellar_validation_v4.json and .md, and the figures' data (docs/results/stellar_figures_v4.json).

    python scripts/stellar_validation_v4.py --list
    python scripts/stellar_validation_v4.py --item eb_catalogue     # one item (resumable: done items are skipped)
    python scripts/stellar_validation_v4.py --all                   # every item, in order
    python scripts/stellar_validation_v4.py --report                # the result files from the item cache

Each item's result is stored at once under cache/stellar_validation_v4/<item>.json with the protocol hash and the
fingerprint of the code it uses; a stored item whose protocol or code differs is run again. The protocol was
committed on its own before this script existed; the held-out targets are run once. Data: public TESS SPOC light
curves and TESScut cutouts of SPOC full-frame images (MAST); the cutouts are deleted after their light curves are
derived (``--keep-cutouts`` keeps them). Published numbers are those frozen in the protocol (transcribed from
VizieR) and Medina et al. (2020)'s flare table (VizieR J/ApJ/905/107).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from setuhq import binaries as eb  # noqa: E402
from setuhq import ffi  # noqa: E402
from setuhq import rotation as rot  # noqa: E402
from setuhq import transients as tr  # noqa: E402
from setuhq.flares import wilson  # noqa: E402
from setuhq.stellar_io import fetch_tess  # noqa: E402

CACHE = Path(os.environ.get("SETUHQ_CACHE", ROOT / "cache"))
ITEMS_DIR = CACHE / "stellar_validation_v4"
PROTOCOL_FILE = ROOT / "docs/results/stellar_validation_protocol_v4.json"
PROTOCOL = json.loads(PROTOCOL_FILE.read_text())
SEED = PROTOCOL["seed"]
OUT_JSON = ROOT / "docs/results/stellar_validation_v4.json"
OUT_MD = ROOT / "docs/results/stellar_validation_v4.md"
OUT_FIG = ROOT / "docs/results/stellar_figures_v4.json"
KEEP_CUTOUTS = False


def protocol_hash() -> str:
    return hashlib.sha256(PROTOCOL_FILE.read_bytes()).hexdigest()


def protocol_commit() -> str | None:
    import subprocess

    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "-1", "--format=%H", "--", str(PROTOCOL_FILE.relative_to(ROOT))],
                             cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


def _clean(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.generic):
        return _clean(o.item())
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    return o


def frac(k: int, n: int) -> dict:
    return {"k": int(k), "of": int(n), "fraction": (k / n) if n else None, "ci95": list(wilson(k, n))}


def boot_median(x, n=2000, seed=SEED) -> dict:
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    if x.size < 3:
        return {"median": float(np.median(x)) if x.size else None, "ci95": None, "n": int(x.size)}
    rng = np.random.default_rng(seed)
    b = np.median(rng.choice(x, (n, x.size)), axis=1)
    return {"median": float(np.median(x)), "ci95": [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))], "n": int(x.size)}


def _lc(tic, sector):
    return fetch_tess(tic, [sector], cache_root=CACHE)[0]


def _spoc_path(tic, sector):
    idx = CACHE / "mast" / "stellar" / str(int(tic)) / "index_120.json"
    files = json.loads(idx.read_text())
    return CACHE / "mast" / "stellar" / str(int(tic)) / files[str(int(sector))]


def _binned(t, y, width):
    t, y = np.asarray(t, float), np.asarray(y, float)
    i = np.floor((t - t[0]) / width).astype(int)
    n = np.bincount(i)
    k = n > 0
    return (np.bincount(i, t)[k] / n[k]).tolist(), (np.bincount(i, y)[k] / n[k]).tolist()


def _circ(a, b):
    d = (a - b) % 1.0
    return min(d, 1 - d)


# ---------------------------------------------------------------- eclipsing binaries

def _eb_row(x, lc):
    r = eb.analyse(lc.time, lc.flux, lc.flux_err)
    P = r.get("period")
    row = {"tic": x["tic"], "split": x["split"], "sector": lc.provenance.get("sector"), "file_sha256": lc.provenance.get("file_sha256"),
           "catalogue": {k: x[k] for k in ("period_d", "morph", "depth_p_2g", "width_p_2g", "phase_p_2g", "depth_s_2g", "phase_s_2g")},
           "eb_candidate": r["eb_candidate"], "reasons": r["reasons"], "period": P, "period_err": r.get("period_err"),
           "period_ambiguous": r.get("period_ambiguous"), "period_rule": r.get("period_rule")}
    if P:
        ratio = P / x["period_d"]
        row["period_ratio"] = ratio
        row["period_match"] = bool(abs(ratio - 1) <= 0.005)
        row["alias"] = "half" if abs(ratio / 0.5 - 1) <= 0.005 else ("double" if abs(ratio / 2 - 1) <= 0.005 else None)
        row["primary"] = r["primary"]
        row["secondary"] = r["secondary"]
        row["morphology"] = r["morphology"]["class"]
        row["depth_ratio"] = r["primary"]["depth"] / x["depth_p_2g"] if x["depth_p_2g"] else None
        if x["phase_s_2g"] is not None:
            cat_sp = (x["phase_s_2g"] - x["phase_p_2g"]) % 1.0
            row["catalogue_secondary_phase"] = cat_sp
            if r["secondary"] and not r["secondary"].get("equal_minima_assumed"):
                row["secondary_phase_diff"] = _circ(r["secondary"]["phase"], cat_sp)
        pc = r["phase_curve"]
        cb, mb = _rebin_phase(pc["phase"], pc["flux"], 100)
        row["phase_curve_100"] = {"phase": cb, "flux": mb}
    else:
        row["period_match"] = False
    return row


def _rebin_phase(ph, fl, n):
    ph = np.asarray(ph, float)
    fl = np.asarray([np.nan if v is None else v for v in fl], float)
    idx = np.minimum((ph * n).astype(int), n - 1)
    ok = np.isfinite(fl)
    s = np.bincount(idx[ok], fl[ok], minlength=n)
    c = np.bincount(idx[ok], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / c
    return [round((i + 0.5) / n, 4) for i in range(n)], [None if not np.isfinite(v) else float(v) for v in m]


def _eb_summary(rows):
    from scipy.stats import spearmanr

    n = len(rows)
    det = sum(r["eb_candidate"] for r in rows)
    pm = [r for r in rows if r["eb_candidate"] and r.get("period_match")]
    sec_rows = [r for r in pm if r.get("catalogue_secondary_phase") is not None]
    sec_ok = sum(1 for r in sec_rows if r.get("secondary_phase_diff") is not None and r["secondary_phase_diff"] <= 0.01)
    w = [(r["primary"]["width_phase"], r["catalogue"]["width_p_2g"]) for r in pm if r["catalogue"]["width_p_2g"]]
    rho = float(spearmanr([a for a, _ in w], [b for _, b in w]).statistic) if len(w) >= 3 else None
    flagged = [r for r in rows if r["eb_candidate"]]
    morph_ok = sum(1 for r in flagged if (r.get("morphology") == "detached") == (r["catalogue"]["morph"] < 0.5))
    return {"n": n, "detected": frac(det, n), "period": frac(len(pm), n),
            "aliases": {"half": sum(r.get("alias") == "half" for r in rows), "double": sum(r.get("alias") == "double" for r in rows)},
            "depth_ratio": boot_median([r["depth_ratio"] for r in pm]),
            "secondary_phase": frac(sec_ok, len(sec_rows)),
            "secondary_found": frac(sum(1 for r in sec_rows if r.get("secondary_phase_diff") is not None), len(sec_rows)),
            "width_spearman": rho, "width_pairs": len(w), "morphology": frac(morph_ok, len(flagged)),
            "e_cos_omega_hints": [{"tic": r["tic"], "e_cos_omega": r["secondary"]["e_cos_omega_hint"]} for r in pm
                                  if r.get("secondary") and abs(r["secondary"]["e_cos_omega_hint"]) > 0.01]}


def item_eb_catalogue() -> dict:
    rows = []
    for x in PROTOCOL["binaries"]["targets"]:
        try:
            lc = None
            for s in [x["sector"]] + [s for s in x["sectors"] if s != x["sector"]]:
                try:
                    lc = _lc(x["tic"], s)
                    break
                except (LookupError, OSError, ValueError):
                    continue
            if lc is None:
                raise LookupError("no listed sector could be fetched")
            rows.append(_eb_row(x, lc))
        except Exception as exc:  # noqa: BLE001 (a target that fails is a miss, recorded)
            rows.append({"tic": x["tic"], "split": x["split"], "error": f"{type(exc).__name__}: {exc}", "eb_candidate": False,
                         "period_match": False, "catalogue": {k: x[k] for k in ("period_d", "morph", "depth_p_2g", "width_p_2g")}})
        print(f"  EB TIC {x['tic']} ({x['split']}): done", flush=True)
    held = [r for r in rows if r["split"] == "held_out"]
    tune = [r for r in rows if r["split"] == "tuning"]
    return {"held_out": _eb_summary(held), "tuning": _eb_summary(tune), "rows": rows}


def item_eb_contrast() -> dict:
    rows = []
    for s in PROTOCOL["binaries"]["contrast_set"]["stars"]:
        lc = _lc(s["tic"], s["sector"])
        r = eb.analyse(lc.time, lc.flux, lc.flux_err)
        rows.append({"star": s["name"], "tic": s["tic"], "sector": s["sector"], "kind": s["kind"], "eb_candidate": r["eb_candidate"],
                     "period": r.get("period"), "reasons": r["reasons"], "file_sha256": lc.provenance.get("file_sha256")})
    return {"false_eb": sum(r["eb_candidate"] for r in rows), "n": len(rows), "rows": rows}


def item_eb_injection() -> dict:
    c = PROTOCOL["binaries"]["injection"]
    rng = np.random.default_rng(SEED + 10)
    rows = []
    for s in PROTOCOL["binaries"]["contrast_set"]["stars"]:
        lc = _lc(s["tic"], s["sector"])
        for _ in range(c["per_star"]):
            P = float(np.exp(rng.uniform(*np.log(c["period_d"]))))
            dp = float(rng.uniform(*c["primary_depth"]))
            ds = float(rng.uniform(*c["secondary_ratio"])) * dp
            ph = float(rng.uniform(*c["secondary_phase"]))
            w = float(rng.uniform(*c["width_phase"]))
            t0 = float(lc.time[0] + rng.uniform(0, P))
            f = lc.flux * eb.synthetic_eb(lc.time, P, t0, dp, ds, ph, w)
            r = eb.analyse(lc.time, f, lc.flux_err)
            got = r.get("period")
            rows.append({"star": s["name"], "period": P, "depth_p": dp, "depth_s": ds, "phase_s": ph, "width": w,
                         "found_period": got, "eb_candidate": r["eb_candidate"],
                         "recovered": bool(got and abs(got / P - 1) <= 0.005)})
        print(f"  EB injections into {s['name']}: done", flush=True)
    k = sum(r["recovered"] for r in rows)
    return {"recovery": frac(k, len(rows)), "flagged": frac(sum(r["eb_candidate"] for r in rows), len(rows)), "rows": rows}


# ---------------------------------------------------------------- rotation

def _rot_summary(rows):
    n = len(rows)
    det = [r for r in rows if r.get("detected")]
    match = [r for r in det if abs(r["period"] / r["published"] - 1) <= 0.10]
    alias = [r for r in det if any(abs(r["period"] / (r["published"] * m) - 1) <= 0.10 for m in (1, 0.5, 2))]
    cov = [r for r in match if r.get("period_err") is not None and
           abs(r["period"] - r["published"]) <= 2 * math.hypot(r["period_err"], r["published_err"] or 0)]
    return {"n": n, "detected": frac(len(det), n), "match": frac(len(match), n), "alias": frac(len(alias), n),
            "coverage": frac(len(cov), len(match)),
            "ratio": boot_median([r["period"] / r["published"] for r in det])}


def item_rot_catalogue() -> dict:
    rows = []
    for x in PROTOCOL["rotation"]["targets"]:
        try:
            lc = _lc(x["tic"], x["sector"])
            r = rot.measure(lc.time, lc.flux)
            t2, f2 = _binned(lc.time, lc.flux, 2 / 24)
            rows.append({"tic": x["tic"], "split": x["split"], "sector": x["sector"], "published": x["prot_d"], "published_err": x["e_prot_d"],
                         "teff": x["teff"], "detected": r["detected"], "period": r["period"], "period_err": r["period_err"],
                         "candidate_period": r["candidate_period"], "alias": r["alias"], "rule": r["rule"], "reasons": r["reasons"],
                         "beyond_limit": r["beyond_limit"], "ls_period": r["lomb_scargle"]["period"], "acf_period": r["acf"]["period"],
                         "semi_amplitude": r["semi_amplitude"], "file_sha256": lc.provenance.get("file_sha256"),
                         "lc_2h": {"time": [round(v, 4) for v in t2], "flux": [round(v, 6) for v in f2]}})
        except Exception as exc:  # noqa: BLE001
            rows.append({"tic": x["tic"], "split": x["split"], "sector": x["sector"], "published": x["prot_d"],
                         "published_err": x["e_prot_d"], "detected": False, "error": f"{type(exc).__name__}: {exc}"})
        print(f"  rotation TIC {x['tic']} ({x['split']}): done", flush=True)
    return {"held_out": _rot_summary([r for r in rows if r["split"] == "held_out"]),
            "tuning": _rot_summary([r for r in rows if r["split"] == "tuning"]), "rows": rows}


def item_rot_null() -> dict:
    rows = []
    for s in PROTOCOL["rotation"]["null"]["stars"]:
        lc = _lc(s["tic"], s["sector"])
        r = rot.measure(lc.time, lc.flux)
        rows.append({"star": s["name"], "tic": s["tic"], "sector": s["sector"], "detected": r["detected"], "period": r["period"],
                     "candidate_period": r["candidate_period"], "semi_amplitude": r["semi_amplitude"], "reasons": r["reasons"]})
    return {"false_detections": sum(r["detected"] for r in rows), "n": len(rows), "rows": rows}


def item_rot_injection() -> dict:
    c = PROTOCOL["rotation"]["injection"]
    rng = np.random.default_rng(SEED + 20)
    rows, long_rows = [], []
    for s in PROTOCOL["rotation"]["null"]["stars"]:
        lc = _lc(s["tic"], s["sector"])
        for _ in range(c["per_star"]):
            P = float(np.exp(rng.uniform(*np.log(c["period_d"]))))
            a = float(np.exp(rng.uniform(*np.log(c["semi_amplitude_ppt"])))) * 1e-3
            r = rot.measure(lc.time, lc.flux * rot.spot_model(lc.time, P, a, rng))
            rows.append({"star": s["name"], "period": P, "semi_amplitude": a, "found": r["period"], "detected": r["detected"],
                         "recovered": bool(r["period"] and abs(r["period"] / P - 1) <= 0.10),
                         "alias": bool(r["period"] and any(abs(r["period"] / (P * m) - 1) <= 0.1 for m in (0.5, 2)))})
        lr = c["long_period_report"]
        for _ in range(lr["per_star"]):
            P = float(rng.uniform(*lr["period_d"]))
            a = float(np.exp(rng.uniform(*np.log(c["semi_amplitude_ppt"])))) * 1e-3
            r = rot.measure(lc.time, lc.flux * rot.spot_model(lc.time, P, a, rng))
            long_rows.append({"star": s["name"], "period": P, "semi_amplitude": a, "detected": r["detected"], "found": r["period"],
                              "beyond_limit": r["beyond_limit"]})
    return {"recovery": frac(sum(r["recovered"] for r in rows), len(rows)),
            "aliases": sum(r["alias"] for r in rows), "rows": rows,
            "long_period": {"n": len(long_rows), "reported_beyond_limit": sum(r["beyond_limit"] for r in long_rows),
                            "reported_as_a_period": sum(bool(r["detected"]) for r in long_rows), "rows": long_rows}}


# ---------------------------------------------------------------- transients

def item_tr_supernovae() -> dict:
    rows = []
    tc = CACHE / "tesscut"
    for x in PROTOCOL["transients"]["targets"]:
        row = {"name": x["name"], "other": x["other"], "split": x["split"], "published": {k: x[k] for k in (
            "tmag_peak", "t_peak_btjd", "t_first_light_btjd", "t_rise_d")}}
        try:
            ch = ffi.choose_sector(x["ra"], x["dec"], x["t_peak_btjd"], tc)
            row["sector_rule"] = ch["rule"]
            row["sector"] = ch["sector"]
            if ch["sector"] is None:
                raise LookupError(ch["rule"])
            path = ffi.fetch_cutout(x["ra"], x["dec"], ch["sector"], cache_dir=tc)
            row["cutout_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            d = ffi.difference_lightcurve(path, x["ra"], x["dec"])
            res = tr.find_transients(d["time"], d["flux"], d["flux_err"], mode="difference", quality=d["quality_times"],
                                     controls=list(d["controls"].values()), centroid=d["centroid"],
                                     zero_point=tr.TESS_ZERO_POINT, aperture_correction=d["aperture_correction"])
            cands = res["candidates"]
            near = [c for c in cands if abs(c["t_peak"] - x["t_peak_btjd"]) <= 10]
            m = min(near, key=lambda c: abs(c["t_peak"] - x["t_peak_btjd"])) if near else None
            row.update({"aperture_correction": d["aperture_correction"], "aperture_correction_source": d["aperture_correction_source"],
                        "controls_used": d["controls_used"], "cadence_days": d["cadence_days"],
                        "n_candidates": len(cands), "summary": res["summary"], "detected": m is not None,
                        "candidates": [{k: c.get(k) for k in ("scale", "t_peak", "peak", "peak_mag", "rise_time", "decay_time",
                                                              "class_hint", "likely_false_alarm")} for c in cands]})
            if m:
                row["matched"] = {k: m.get(k) for k in ("scale", "t_peak", "peak", "peak_mag", "rise_time", "decay_time",
                                                        "decay_time_lower_limit", "first_light", "class_hint", "hints", "reasons",
                                                        "likely_false_alarm")}
                row["peak_time_diff"] = m["t_peak"] - x["t_peak_btjd"]
                row["rise_ratio"] = m["rise_time"] / x["t_rise_d"] if m.get("first_light") else None
                row["peak_mag_diff"] = (m["peak_mag"] - x["tmag_peak"]) if m.get("peak_mag") is not None else None
            ctrl = []
            for name, cy in d["controls"].items():
                rc = tr.find_transients(d["time"], cy, mode="difference", quality=d["quality_times"])
                ctrl.append({"aperture": name, "n_candidates": rc["summary"]["n_candidates"],
                             "sn_like": sum(c["class_hint"] == "extragalactic-transient-like" for c in rc["candidates"])})
            row["controls"] = ctrl
            tb, fb = _binned(d["time"], d["flux"], 0.25)
            row["lc_6h"] = {"time": [round(v, 3) for v in tb], "flux_e_s": [round(v, 2) for v in fb]}
            if not KEEP_CUTOUTS:
                path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            row.update({"detected": False, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-1500:]})
        rows.append(row)
        print(f"  SN {x['name']} ({x['split']}): {'detected' if row.get('detected') else 'not detected'}", flush=True)
    out = {"rows": rows}
    for split in ("held_out", "tuning"):
        rs = [r for r in rows if r["split"] == split]
        det = [r for r in rs if r.get("detected")]
        ctrl = [c for r in rs for c in r.get("controls", [])]
        out[split] = {"n": len(rs), "detected": frac(len(det), len(rs)),
                      "peak_time": frac(sum(1 for r in det if abs(r["peak_time_diff"]) <= 2), len(rs)),
                      "rise_ratio": boot_median([r.get("rise_ratio") for r in det]),
                      "rise_measured": sum(1 for r in det if r.get("rise_ratio") is not None),
                      "peak_mag_diff": boot_median([r.get("peak_mag_diff") for r in det]),
                      "sn_like": frac(sum(1 for r in det if r["matched"]["class_hint"] == "extragalactic-transient-like"), len(det)),
                      "detected_not_false_alarm": frac(sum(1 for r in det if not r["matched"]["likely_false_alarm"]), len(rs)),
                      "control_apertures": len(ctrl),
                      "control_sn_like_rate": (sum(1 for c in ctrl if c["sn_like"]) / len(ctrl)) if ctrl else None,
                      "control_any_candidate_rate": (sum(1 for c in ctrl if c["n_candidates"]) / len(ctrl)) if ctrl else None}
    if not KEEP_CUTOUTS:
        shutil.rmtree(tc, ignore_errors=True)
    return out


def _vizier(cat):
    from astroquery.vizier import Vizier

    return Vizier(row_limit=-1, columns=["**"]).get_catalogs(cat)[0]


def item_tr_flares() -> dict:
    p = PROTOCOL["transients"]["flare_contrast"]
    med = _vizier("J/ApJ/905/107/table3")
    med = med[med["TIC"] == p["tic"]]
    peaks = np.array(med["Time"], float) - 2457000.0
    w = p["match_window_days"]
    per, matched = [], []
    for s in p["sectors"]:
        lc = _lc(p["tic"], s)
        res = tr.find_transients(lc.time, lc.flux, lc.flux_err, quality=tr.read_quality(_spoc_path(p["tic"], s)))
        cands = res["candidates"]
        for c in cands:
            if np.any((peaks >= c["t_start"] - w) & (peaks <= c["t_end"] + w)):
                matched.append({k: c.get(k) for k in ("t_peak", "peak", "rise_time", "decay_time", "class_hint", "scale")} | {"sector": s})
        per.append({"sector": s, "summary": res["summary"], "file_sha256": lc.provenance.get("file_sha256")})
    k = sum(m["class_hint"] == "flare-like" for m in matched)
    # the tuning star, reported only
    t = p["tuning_star"]
    lc = _lc(t["tic"], t["sectors"][0])
    au = tr.find_transients(lc.time, lc.flux, lc.flux_err, quality=tr.read_quality(_spoc_path(t["tic"], t["sectors"][0])))
    return {"medina_flares": int(len(peaks)), "matched_candidates": len(matched), "flare_like": frac(k, len(matched)),
            "matched_classes": {h: sum(m["class_hint"] == h for m in matched) for h in sorted({m["class_hint"] for m in matched})},
            "sectors": per, "matched": matched, "aumic_tuning": au["summary"]}


def item_tr_null() -> dict:
    rows = []
    for s in PROTOCOL["transients"]["null"]["stars"]:
        lc = _lc(s["tic"], s["sector"])
        res = tr.find_transients(lc.time, lc.flux, lc.flux_err, quality=tr.read_quality(_spoc_path(s["tic"], s["sector"])))
        days = float(lc.time[-1] - lc.time[0])
        keep = [c for c in res["candidates"] if not c["likely_false_alarm"]]
        rows.append({"star": s["name"], "tic": s["tic"], "sector": s["sector"], "days": days, "candidates": res["summary"]["n_candidates"],
                     "not_false_alarm": len(keep),
                     "events": [{k: c.get(k) for k in ("t_peak", "peak", "class_hint", "scale")} for c in res["candidates"]]})
    days = sum(r["days"] for r in rows)
    n = sum(r["not_false_alarm"] for r in rows)
    return {"days": days, "not_false_alarm": n, "fp_per_day": n / days if days else None, "rows": rows}


def item_tr_screen() -> dict:
    c = PROTOCOL["transients"]["screen_injection"]
    rng = np.random.default_rng(SEED + 30)
    rows = []
    for s in PROTOCOL["transients"]["null"]["stars"]:
        lc = _lc(s["tic"], s["sector"])
        q = tr.read_quality(_spoc_path(s["tic"], s["sector"]))
        dumps = np.array(q["momentum_dump"], float)
        dumps = dumps[(dumps > lc.time[0] + 0.5) & (dumps < lc.time[-1] - 0.5)]
        for i in range(c["per_star"]):
            kind = "momentum_dump" if i % 2 == 0 else "asteroid"
            amp = float(np.exp(rng.uniform(np.log(1e-3), np.log(1e-2))))
            if kind == "momentum_dump":
                if dumps.size == 0:
                    rows.append({"star": s["name"], "kind": kind, "screened": False, "note": "no momentum dump in this light curve"})
                    continue
                t_in = float(rng.choice(dumps))
                n_cad = int(rng.integers(1, 4))
                f = lc.flux + tr.dump_spike(lc.time, t_in, amp, n_cad)
                width = 0.05
            else:
                t_in = float(rng.uniform(lc.time[0] + 1, lc.time[-1] - 1))
                fw = float(rng.uniform(0.1, 1.0))
                f = lc.flux + tr.asteroid_model(lc.time, t_in, amp, fw)
                width = fw
            res = tr.find_transients(lc.time, f, lc.flux_err, quality=q)
            hit = [x for x in res["candidates"] if abs(x["t_peak"] - t_in) <= max(width, 0.05)]
            rows.append({"star": s["name"], "kind": kind, "t": t_in, "amplitude": amp, "found": bool(hit),
                         "classes": [x["class_hint"] for x in hit], "screened": bool(hit) and any(x["likely_false_alarm"] for x in hit)})
    k = sum(r["screened"] for r in rows)
    by = {kind: frac(sum(r["screened"] for r in rows if r["kind"] == kind), sum(1 for r in rows if r["kind"] == kind))
          for kind in ("momentum_dump", "asteroid")}
    return {"screened": frac(k, len(rows)), "found": frac(sum(r.get("found", False) for r in rows), len(rows)), "by_kind": by, "rows": rows}


# ---------------------------------------------------------------- the runner

ITEM_FILES = {"eb": ["binaries.py", "preprocess.py", "stellar_io.py", "loaders.py"],
              "rot": ["rotation.py", "binaries.py", "preprocess.py", "stellar_io.py", "loaders.py"],
              "tr": ["transients.py", "ffi.py", "binaries.py", "preprocess.py", "stellar_io.py", "loaders.py"]}
SCRIPT_FILES = ["scripts/stellar_validation_v4.py"]
CODE_FILES = sorted({f for v in ITEM_FILES.values() for f in v})

ITEMS = {"eb_catalogue": item_eb_catalogue, "eb_contrast": item_eb_contrast, "eb_injection": item_eb_injection,
         "rot_catalogue": item_rot_catalogue, "rot_null": item_rot_null, "rot_injection": item_rot_injection,
         "tr_supernovae": item_tr_supernovae, "tr_flares": item_tr_flares, "tr_null": item_tr_null, "tr_screen": item_tr_screen}


def item_files(name: str) -> list[str]:
    return [f"src/setuhq/{f}" for f in ITEM_FILES[name.split("_")[0]]] + SCRIPT_FILES


def item_fingerprint(name: str) -> str:
    from setuhq.starsearch import _fingerprint

    return _fingerprint(item_files(name), src=ROOT)


def code_fingerprint() -> str:
    from setuhq.starsearch import _fingerprint

    return _fingerprint([f"src/setuhq/{f}" for f in CODE_FILES] + SCRIPT_FILES, src=ROOT)


def run_item(name: str, force: bool = False) -> dict:
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{name}.json"
    ident = {"protocol_sha256": protocol_hash(), "code_fingerprint": item_fingerprint(name), "code_files": item_files(name)}
    if path.exists() and not force:
        old = json.loads(path.read_text())
        if {k: old.get(k) for k in ident} == ident and "result" in old:
            print(f"{name}: cached")
            return old
    t0 = time.time()
    try:
        result = ITEMS[name]()
        rec = {**ident, "item": name, "status": "ok", "seconds": round(time.time() - t0, 1), "result": _clean(result)}
    except Exception as exc:  # noqa: BLE001 (recorded: the report says what could not be validated)
        rec = {**ident, "item": name, "status": "error", "error": f"{type(exc).__name__}: {exc}",
               "trace": traceback.format_exc()[-3000:], "seconds": round(time.time() - t0, 1)}
    rec["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, default=_json, allow_nan=False))
    os.replace(tmp, path)
    print(f"{name}: {rec['status']} in {rec['seconds']} s", flush=True)
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--item", action="append", choices=sorted(ITEMS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--keep-cutouts", action="store_true")
    a = ap.parse_args()
    KEEP_CUTOUTS = a.keep_cutouts
    if a.list:
        print("\n".join(ITEMS))
    for n in (list(ITEMS) if a.all else a.item or []):
        run_item(n, a.force)
    if a.report:
        from stellar_validation_v4_report import write_report  # noqa: E402

        write_report(ITEMS_DIR, OUT_JSON, OUT_MD, OUT_FIG, PROTOCOL, protocol_hash(), code_fingerprint(),
                     protocol_file=PROTOCOL_FILE.relative_to(ROOT), protocol_commit=protocol_commit())

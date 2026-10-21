#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Validate SetuHQ's stellar capabilities (flares, pulsations, CHEOPS) against published results, under a frozen
protocol, and write docs/results/stellar_validation.json and .md.

    python scripts/stellar_validation.py --list
    python scripts/stellar_validation.py --item aumic_gunther      # one item (resumable: done items are skipped)
    python scripts/stellar_validation.py --all                     # every item, in order
    python scripts/stellar_validation.py --report                  # build the two result files from the item cache

Each item's result is stored at once under cache/stellar_validation/<item>.json, with the protocol hash and the
stellar code fingerprint; a stored item whose protocol or code differs is run again. Data: public TESS SPOC light
curves (MAST) and public CHEOPS DRP light curves (DACE, public mode); published numbers from
docs/results/stellar_validation_references.json and from VizieR (Günther et al. 2020, J/AJ/159/60; Medina et al.
2020, J/ApJ/905/107). The pycheops reference (item cheops_pycheops) reads decorrelated light curves that
pycheops wrote in its own environment (scripts/pycheops_reference.py); without them the item says so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from setuhq import cheops as ch  # noqa: E402
from setuhq import flares as fl  # noqa: E402
from setuhq import pulsations as pu  # noqa: E402
from setuhq.stellar_io import code_fingerprint, fetch_tess, tic_star  # noqa: E402

CACHE = Path(os.environ.get("SETUHQ_CACHE", ROOT / "cache"))
ITEMS_DIR = CACHE / "stellar_validation"
REFS = ROOT / "docs/results/stellar_validation_references.json"
OUT_JSON = ROOT / "docs/results/stellar_validation.json"
OUT_MD = ROOT / "docs/results/stellar_validation.md"
PYCHEOPS_DIR = Path(os.environ.get("SETUHQ_PYCHEOPS_REF", CACHE / "pycheops_ref"))

# ---------------------------------------------------------------- the frozen protocol

PROTOCOL = {
    "version": 1,
    "frozen": "2026-10-21",
    "seed": 20261021,
    "flares": {
        "match_window_days": 0.01,  # a published flare is recovered when its peak lies within one of our flare windows ± this
        "aumic": {"tic": 441420236, "sectors": [1], "reference": "Günther et al. 2020, J/AJ/159/60"},
        "gunther_energy_star": {"tic": 150359500, "sectors": [2], "reference": "Günther et al. 2020, J/AJ/159/60"},
        "proxima": {"tic": 388857263, "sectors": [11, 12], "reference": "Medina et al. 2020, J/ApJ/905/107"},
        "gj1243": {"tic": 273589987, "sectors": [14, 15]},
        "gj65": {"tic": 632499596, "sectors": [30], "exptimes": [120, 20]},
        "completeness": {"n_trials": 20, "per_trial": 10, "amp_range": [1e-4, 1e-1], "fwhm_minutes": [1.0, 60.0],
                         "stars": ["aumic", "proxima", "gj1243"]},
        "quiet": {"names": ["pi Men", "zeta Tuc", "beta Hyi"], "sector_limit": 2},
        "cheops_targets": ["AU Mic", "AD Leo", "EV Lac", "GJ 65", "Proxima Cen"],
        "tics": {"AU Mic": 441420236, "AD Leo": 95431305, "EV Lac": 154101678, "GJ 65": 632499596, "Proxima Cen": 388857263},
        "teff_fallback": "when TIC v8.2 has no Teff, the CHEOPS archive's target record (DACE teff_k), labelled as such",
        "cheops_max_visits_per_target": 25,
        "cheops_min_cadence_s": 0, "cheops_max_cadence_s": 60,
        "denoise_grid": {"wavelets": ["haar", "db4", "db18"], "levels": [1, 2, 3, 4], "n_trials": 3, "per_trial": 10},
    },
    "pulsations": {
        "snr_stop": 4.0, "noise_box_cd": 2.0, "max_frequencies": 100,
        "tolerance": "strict: 3 × the combined frequency uncertainty (ours and published, Montgomery & O'Donoghue); "
                     "loose: the Rayleigh resolution 1/T",
        "hr10": {"sectors": [2, 29], "fmin_cd": 0.05, "n_surrogates": 10},
        "beta_pic": {"sectors": [5, 6, 7], "fmin_cd": 5.0},
        "toi197": {"sectors": [2], "n_boot": 100},
    },
    "cheops": {"pycheops_visits": ["CH_PR100018_TG035201_V0300", "CH_PR100018_TG048901_V0300", "CH_PR100018_TG049601_V0300"],
               "terms": ["t", "t2", "x", "y", "x2", "y2", "xy", "sin1", "cos1", "sin2", "cos2", "sin3", "cos3", "bg", "contam"]},
}


def protocol_hash() -> str:
    return hashlib.sha256(json.dumps(PROTOCOL, sort_keys=True).encode()).hexdigest()


def refs() -> dict:
    return json.loads(REFS.read_text())


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


def _bootstrap_median(x, n=2000, seed=0):
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    if x.size < 3:
        return {"median": float(np.median(x)) if x.size else None, "ci95": None, "n": int(x.size)}
    rng = np.random.default_rng(seed)
    b = np.median(rng.choice(x, (n, x.size)), axis=1)
    return {"median": float(np.median(x)), "ci95": [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))], "n": int(x.size)}


def _star(name, tic):
    """TIC values, with the CHEOPS archive's Teff when the TIC has none (labelled; see the protocol)."""
    star = tic_star(tic, CACHE)
    if star is not None and not star.get("teff") and name:
        try:
            vs = ch.list_visits(name, cache_dir=CACHE / "cheops")["visits"]
        except ch.CheopsUnavailable:
            vs = []
        if vs and vs[0].get("teff_k"):
            star = {**star, "teff": float(vs[0]["teff_k"]), "teff_source": "CHEOPS archive target record (DACE teff_k)"}
    return star


def _tess(tic, sectors, exptime=120):
    return fetch_tess(tic, sectors, exptime=exptime, cache_root=CACHE)


def _flares_on(lcs, star, band="TESS", denoise=False):
    out = []
    for lc in lcs:
        cad = float(np.median(np.diff(lc.time))) * 86400
        cfg = fl.config_for(band, cad, denoise=denoise)
        r = fl.detect_flares(lc.time, lc.flux, lc.flux_err, config=cfg, star=star, band=band)
        r["inverted_null"] = fl.inverted_null(lc.time, lc.flux, lc.flux_err, config=cfg, band=band)
        r["sector"] = lc.provenance.get("sector")
        r["file_sha256"] = lc.provenance.get("file_sha256")
        for f in r["flares"]:
            f.pop("models", None)
        for f in r["rejected"]:
            f.pop("models", None)
        out.append(r)
    return out


def _match_times(ours, ref_times, window):
    """For each published peak time, whether one of our flare windows (± window) contains it, and which."""
    hits = []
    for x in ref_times:
        k = next((i for i, f in enumerate(ours) if f["t_start"] - window <= x <= f["t_end"] + window), None)
        hits.append(k)
    return hits


def _vizier(cat):
    from astroquery.vizier import Vizier

    return Vizier(row_limit=-1, columns=["**"]).get_catalogs(cat)[0]


# ---------------------------------------------------------------- flare items


def item_aumic_gunther() -> dict:
    p = PROTOCOL["flares"]["aumic"]
    lcs = _tess(p["tic"], p["sectors"])
    star = _star("AU Mic", p["tic"])
    res = _flares_on(lcs, star)
    ours = [f for r in res for f in r["flares"]]
    g = _vizier("J/AJ/159/60/table1")
    g = g[g["TIC"] == p["tic"]]
    tp = np.array(g["tpeak"], float) - 2457000.0
    hits = _match_times(ours, tp, PROTOCOL["flares"]["match_window_days"])
    k = sum(h is not None for h in hits)
    ours_matched = {h for h in hits if h is not None}
    # published outbursts with more than one flare component, against our complex events
    outb = {}
    for o, x in zip(g["Outbst"], tp):
        outb.setdefault(int(o), []).append(x)
    multi_pub = sum(1 for v in outb.values() if len(v) > 1)
    # per matched event: our peak amplitude against the largest published component in it; FWHM only where both
    # sides fit a single component (a multi-component FWHM is not comparable)
    ev: dict[int, list] = {}
    for h, a, w in zip(hits, g["Amp"], g["FWHMdt"]):
        if h is not None:
            ev.setdefault(h, []).append((float(a), float(w)))
    amp_ratio = [ours[h]["amplitude"] / max(a for a, _ in v) for h, v in ev.items()]
    fwhm_ratio = [ours[h]["fwhm_minutes"] / (v[0][1] * 1440) for h, v in ev.items()
                  if len(v) == 1 and ours[h]["n_components"] == 1 and v[0][1] > 0]
    simple_agree = sum(1 for h, v in ev.items() if (len(v) > 1) == (ours[h]["n_components"] > 1))
    return {"star": "AU Mic", "tic": p["tic"], "sectors": p["sectors"], "reference": p["reference"], "tic_values": star,
            "published": {"flares": int(len(tp)), "outbursts": len(outb), "outbursts_multi": multi_pub,
                          "multi_fraction": multi_pub / len(outb)},
            "ours": {"flares": len(ours), "complex": sum(f["n_components"] > 1 for f in ours),
                     "complex_fraction": sum(f["n_components"] > 1 for f in ours) / len(ours) if ours else None,
                     "components": sum(f["n_components"] for f in ours),
                     "rejected": sum(len(r["rejected"]) for r in res),
                     "inverted_null": sum(r["inverted_null"]["false_positives"] for r in res),
                     "observing_days": sum(r["summary"]["observing_days"] for r in res)},
            "recall": {"recovered": k, "of": int(len(tp)), "fraction": k / len(tp), "ci95": fl.wilson(k, len(tp))},
            "ours_matched": {"matched": len(ours_matched), "of": len(ours)},
            "missed": [{"tpeak_btjd": float(x), "amp": float(a), "fwhm_min": float(w) * 1440}
                       for x, a, w, h in zip(tp, g["Amp"], g["FWHMdt"], hits) if h is None],
            "amplitude_ratio_ours_over_published": _bootstrap_median(amp_ratio),
            "fwhm_ratio_ours_over_published_simple": _bootstrap_median(fwhm_ratio),
            "morphology_agreement": {"agree": simple_agree, "of": len(ev), "ci95": fl.wilson(simple_agree, len(ev))},
            "energies": ("TIC v8.2 has no Teff for AU Mic; ours use the CHEOPS archive's Teff (labelled). Günther et al. "
                         "give no energies for AU Mic, so there is nothing to compare them with"),
            "energy_teff_source": (star or {}).get("teff_source", "TIC"),
            "per_sector": [{k2: r[k2] for k2 in ("sector", "file_sha256", "summary")} for r in res],
            "flares": ours}


def item_gunther_energy_star() -> dict:
    p = PROTOCOL["flares"]["gunther_energy_star"]
    lcs = _tess(p["tic"], p["sectors"])
    star = tic_star(p["tic"], CACHE)
    res = _flares_on(lcs, star)
    ours = [f for r in res for f in r["flares"]]
    g = _vizier("J/AJ/159/60/table1")
    g = g[g["TIC"] == p["tic"]]
    tp = np.array(g["tpeak"], float) - 2457000.0
    hits = _match_times(ours, tp, PROTOCOL["flares"]["match_window_days"])
    # energies: our event energy against the sum of the published components in that event
    per_event: dict[int, float] = {}
    for h, e in zip(hits, g["Ebol"]):
        if h is not None and not np.ma.is_masked(e):
            per_event[h] = per_event.get(h, 0.0) + float(e)
    ratio = [ours[h]["e_bol_erg"] / e for h, e in per_event.items() if ours[h].get("e_bol_erg")]
    k = sum(h is not None for h in hits)
    return {"star": "TIC 150359500", "tic": p["tic"], "sectors": p["sectors"], "reference": p["reference"], "tic_values": star,
            "published": {"flares": int(len(tp)), "outbursts": int(len(set(g["Outbst"])))},
            "ours": {"flares": len(ours), "complex": sum(f["n_components"] > 1 for f in ours),
                     "inverted_null": sum(r["inverted_null"]["false_positives"] for r in res)},
            "recall": {"recovered": k, "of": int(len(tp)), "fraction": k / len(tp), "ci95": fl.wilson(k, len(tp))},
            "energy_ratio_ours_over_published": _bootstrap_median(ratio),
            "energy_method": "both: ED × πR²σT⁴ ∫R B(Teff) / ∫R B(9000 K) (Günther et al. 2020 use the same 9000 K blackbody)",
            "flares": ours}


def item_proxima_medina() -> dict:
    p = PROTOCOL["flares"]["proxima"]
    lcs = _tess(p["tic"], p["sectors"])
    star = _star("Proxima Cen", p["tic"])
    res = _flares_on(lcs, star)
    ours = [f for r in res for f in r["flares"]]
    m = _vizier("J/ApJ/905/107/table3")
    m = m[m["TIC"] == p["tic"]]
    tp = np.array(m["Time"], float) - 2457000.0
    hits = _match_times(ours, tp, PROTOCOL["flares"]["match_window_days"])
    k = sum(h is not None for h in hits)
    ed_pairs = [(ours[h]["ed_s"], float(e)) for h, e in zip(hits, m["ED"]) if h is not None]
    ed_data_pairs = [(ours[h]["ed_data_s"], float(e)) for h, e in zip(hits, m["ED"]) if h is not None]
    en_pairs = [(ours[h].get("e_band_erg"), float(e)) for h, e in zip(hits, m["Energy"]) if h is not None]
    enm_pairs = [(ours[h].get("e_band_from_magnitude_erg"), float(e)) for h, e in zip(hits, m["Energy"]) if h is not None]
    end_pairs = [(ours[h].get("e_band_from_magnitude_erg", 0) * ours[h]["ed_data_s"] / ours[h]["ed_s"], float(e))
                 for h, e in zip(hits, m["Energy"]) if h is not None and ours[h]["ed_s"]]
    # recall as a function of the published ED
    edp = np.array(m["ED"], float)
    rec = np.array([h is not None for h in hits])
    by_ed = []
    for lo, hi in ((0, 1), (1, 3), (3, 10), (10, 30), (30, 1e9)):
        s = (edp >= lo) & (edp < hi)
        n = int(s.sum())
        if n:
            kk = int(rec[s].sum())
            by_ed.append({"ed_lo_s": lo, "ed_hi_s": hi if hi < 1e9 else None, "n": n, "recovered": kk, "fraction": kk / n,
                          "ci95": fl.wilson(kk, n)})
    return {"star": "Proxima Cen", "tic": p["tic"], "sectors": p["sectors"], "reference": p["reference"], "tic_values": star,
            "published": {"flares": int(len(tp))},
            "ours": {"flares": len(ours), "complex": sum(f["n_components"] > 1 for f in ours),
                     "inverted_null": sum(r["inverted_null"]["false_positives"] for r in res),
                     "observing_days": sum(r["summary"]["observing_days"] for r in res)},
            "recall": {"recovered": k, "of": int(len(tp)), "fraction": k / len(tp), "ci95": fl.wilson(k, len(tp))},
            "recall_by_published_ed": by_ed,
            "ours_matched": {"matched": len({h for h in hits if h is not None}), "of": len(ours)},
            "ed_ratio_ours_over_published": _bootstrap_median([a / b for a, b in ed_pairs if b > 0]),
            "ed_data_ratio_ours_over_published": _bootstrap_median([a / b for a, b in ed_data_pairs if b > 0]),
            "band_energy_ratio_ours_over_published": _bootstrap_median([a / b for a, b in en_pairs if a and b > 0]),
            "band_energy_from_magnitude_ratio_ours_over_published": _bootstrap_median([a / b for a, b in enm_pairs if a and b > 0]),
            "band_energy_data_ed_magnitude_ratio_ours_over_published": _bootstrap_median([a / b for a, b in end_pairs if a and b > 0]),
            "flares": ours}


def item_gj1243() -> dict:
    p = PROTOCOL["flares"]["gj1243"]
    lcs = _tess(p["tic"], p["sectors"])
    star = tic_star(p["tic"], CACHE)
    res = _flares_on(lcs, star)
    ours = [f for r in res for f in r["flares"]]
    days = sum(r["summary"]["observing_days"] for r in res)
    return {"star": "GJ 1243", "tic": p["tic"], "sectors": p["sectors"], "tic_values": star,
            "ours": {"flares": len(ours), "complex": sum(f["n_components"] > 1 for f in ours), "observing_days": days,
                     "rate_per_day": len(ours) / days if days else None,
                     "inverted_null": sum(r["inverted_null"]["false_positives"] for r in res)},
            "reference": "none used: no machine-readable per-flare TESS catalogue of GJ 1243 was found; reported, not compared",
            "flares": ours}


def item_gj65() -> dict:
    p = PROTOCOL["flares"]["gj65"]
    star = _star("GJ 65", p["tic"])
    out = {"star": "GJ 65 (BL Cet + UV Cet, blended in TESS pixels)", "tic": p["tic"], "sectors": p["sectors"], "tic_values": star}
    by = {}
    for ex in p["exptimes"]:
        lcs = _tess(p["tic"], p["sectors"], exptime=ex)
        res = _flares_on(lcs, star)
        ours = [f for r in res for f in r["flares"]]
        by[ex] = ours
        out[f"cadence_{ex}s"] = {"flares": len(ours), "complex": sum(f["n_components"] > 1 for f in ours),
                                 "inverted_null": sum(r["inverted_null"]["false_positives"] for r in res),
                                 "observing_days": sum(r["summary"]["observing_days"] for r in res)}
    # 2-min flares found again at 20 s (internal consistency, same photons)
    w = PROTOCOL["flares"]["match_window_days"]
    k = sum(1 for f in by[120] if any(g["t_start"] - w <= f["t_peak"] <= g["t_end"] + w for g in by[20]))
    out["two_min_found_at_20s"] = {"found": k, "of": len(by[120]), "ci95": fl.wilson(k, len(by[120]))}
    out["complex_fraction"] = {str(ex): (sum(f["n_components"] > 1 for f in v) / len(v) if v else None) for ex, v in by.items()}
    out["reference"] = ("internal only: the same sector at 120 s and 20 s; Bruno et al. 2024 show GJ 65 but publish no "
                        "per-flare table")
    out["flares_20s"] = by[20]
    return out


def item_completeness() -> dict:
    c = PROTOCOL["flares"]["completeness"]
    out = {}
    for name in c["stars"]:
        p = PROTOCOL["flares"][name]
        lc = _tess(p["tic"], p["sectors"][:1])[0]
        star = _star({"aumic": "AU Mic", "proxima": "Proxima Cen"}.get(name), p["tic"])
        real = fl.detect_flares(lc.time, lc.flux, lc.flux_err, star=star)["flares"]
        r = fl.inject_recover(lc.time, lc.flux, lc.flux_err, star=star, n_trials=c["n_trials"], per_trial=c["per_trial"],
                              seed=PROTOCOL["seed"], amp_range=tuple(c["amp_range"]), fwhm_minutes=tuple(c["fwhm_minutes"]),
                              real_flares=real)
        ed_ratio = [x["ed_recovered_s"] / x["ed_s"] for x in r["injections"] if x["recovered"] and x["ed_s"] > 0]
        energies = [f.get("e_bol_erg") for f in real]
        lim = fl.completeness_limit(r["by_energy"]) if r["by_energy"] else None
        out[name] = {"tic": p["tic"], "sector": p["sectors"][0], "n_injected": r["n"],
                     "recovered": sum(x["recovered"] for x in r["injections"]),
                     "by_amplitude": r["by_amplitude"], "by_ed": r["by_ed"], "by_energy": r["by_energy"],
                     "amplitude_90pct": fl.completeness_limit(r["by_amplitude"]), "ed_90pct_s": fl.completeness_limit(r["by_ed"]),
                     "energy_90pct_erg": lim, "recovered_ed_ratio": _bootstrap_median(ed_ratio),
                     "ffd_power_law": fl.powerlaw_mle(energies, lim) if lim else None,
                     "ffd_vs_lognormal": fl.compare_lognormal(energies, lim) if lim else None}
    return out


def _named_tic(name):
    from astroquery.mast import Catalogs

    t = Catalogs.query_object(name, catalog="TIC", radius=0.003)
    t.sort("dstArcSec")
    return int(t[0]["ID"])


def item_quiet_stars() -> dict:
    q = PROTOCOL["flares"]["quiet"]
    rows = []
    for name in q["names"]:
        tic = _named_tic(name)
        try:
            lcs = _tess(tic, None)[: q["sector_limit"]]
        except LookupError as exc:
            rows.append({"star": name, "tic": tic, "error": str(exc)})
            continue
        res = _flares_on(lcs, tic_star(tic, CACHE))
        days = sum(r["summary"]["observing_days"] for r in res)
        n = sum(r["summary"]["n_flares"] for r in res)
        nn = sum(r["inverted_null"]["false_positives"] for r in res)
        rows.append({"star": name, "tic": tic, "sectors": [r["sector"] for r in res], "observing_days": days,
                     "flares_detected": n, "inverted_null": nn,
                     "events": [{k: f[k] for k in ("t_peak", "amplitude", "peak_sigma", "ed_s", "delta_bic_shape")}
                                for r in res for f in r["flares"]]})
    days = sum(r.get("observing_days", 0) for r in rows)
    n = sum(r.get("flares_detected", 0) for r in rows)
    return {"stars": rows, "total_days": days, "total_detections": n,
            "false_positive_rate_per_day_upper": (n / days) if days else None,
            "note": "Quiet solar-type stars are not expected to show detectable white-light flares at TESS precision; "
                    "every detection here counts as a false positive (an upper bound on the rate)."}


def _cheops_visits(name):
    lst = ch.list_visits(name, cache_dir=CACHE / "cheops")
    p = PROTOCOL["flares"]
    vs = []
    for v in lst["visits"]:
        cad = float(v["obs_exptime"]) * float(v["obs_nexp"])
        if p["cheops_min_cadence_s"] <= cad <= p["cheops_max_cadence_s"]:
            vs.append(v)
    return lst, vs[: p["cheops_max_visits_per_target"]]


def item_cheops_flares() -> dict:
    """CHEOPS DRP visits of M dwarfs in Poyatos et al. (2025)'s sample, with and without denoising."""
    out = {"targets": [], "data": "CHEOPS DRP (subarray) light curves via DACE public mode; Poyatos et al. used 3-s imagettes "
                                  "reduced with PIPE, which DACE does not serve", "acknowledgement": ch.credit([])}
    allv = []
    for name in PROTOCOL["flares"]["cheops_targets"]:
        try:
            lst, vs = _cheops_visits(name)
        except ch.CheopsUnavailable as exc:
            out["targets"].append({"star": name, "error": str(exc)})
            continue
        star = _star(name, PROTOCOL["flares"]["tics"][name])
        row = {"star": name, "public_visits": lst["n_public"], "used": len(vs), "tic_values": star, "visits": []}
        for v in vs:
            try:
                vis = ch.fetch_visit(v, cache_dir=CACHE / "cheops")
            except ch.CheopsUnavailable as exc:
                row["visits"].append({"file_key": v["file_key"], "error": str(exc)})
                continue
            d = ch.detrend_visit(vis)
            ok = np.isfinite(d["flux"])
            if ok.sum() < 30:
                continue
            rec = {"file_key": v["file_key"], "programme": ch.programme_id(v["file_key"]), "obs_id": v["obs_id"],
                   "pi": v["pi_name"], "cadence_s": vis.cadence_s, "terms": d["terms"]}
            for dn in (False, True):
                cfg = fl.config_for("CHEOPS", vis.cadence_s, denoise=dn)
                r = fl.detect_flares(d["time"][ok], d["flux"][ok], d["flux_err"][ok], config=cfg, star=star, band="CHEOPS")
                nul = fl.inverted_null(d["time"][ok], d["flux"][ok], d["flux_err"][ok], config=cfg, band="CHEOPS")
                for f in r["flares"]:
                    f.pop("models", None)
                rec["denoised" if dn else "original"] = {"flares": r["flares"], "days": r["summary"]["observing_days"],
                                                         "inverted_null": nul["false_positives"]}
            row["visits"].append(rec)
            allv.append(v)
        out["targets"].append(row)
    out.update(ch.credit(allv))
    summ = {}
    for key in ("original", "denoised"):
        fls = [f for t in out["targets"] for v in t.get("visits", []) if key in v for f in v[key]["flares"]]
        days = sum(v[key]["days"] for t in out["targets"] for v in t.get("visits", []) if key in v)
        nul = sum(v[key]["inverted_null"] for t in out["targets"] for v in t.get("visits", []) if key in v)
        en = [f.get("e_bol_erg") for f in fls]
        multi = sum(f["n_components"] > 1 for f in fls)
        summ[key] = {"flares": len(fls), "observing_days": days, "complex": multi,
                     "complex_fraction": multi / len(fls) if fls else None,
                     "complex_ci95": fl.wilson(multi, len(fls)) if fls else None, "inverted_null": nul}
        e_ok = sorted(e for e in en if e)
        if len(e_ok) >= 10:
            emin = float(np.percentile(e_ok, 50))  # without a CHEOPS completeness curve per star: the median energy
            summ[key]["power_law_above_median_energy"] = fl.powerlaw_mle(e_ok, emin)
            summ[key]["vs_lognormal"] = fl.compare_lognormal(e_ok, emin)
    o, dn = summ["original"]["flares"], summ["denoised"]["flares"]
    summ["denoising_gain"] = (dn - o) / o if o else None
    out["summary"] = summ
    return out


def item_denoise_grid() -> dict:
    g = PROTOCOL["flares"]["denoise_grid"]
    out = {}
    # one CHEOPS visit set (EV Lac, the longest public visits) and one TESS star
    try:
        lst, vs = _cheops_visits("EV Lac")
        segs = []
        for v in vs:
            d = ch.detrend_visit(ch.fetch_visit(v, cache_dir=CACHE / "cheops"))
            ok = np.isfinite(d["flux"])
            segs.append((d["time"][ok], d["flux"][ok]))
        t = np.concatenate([s[0] for s in segs])
        f = np.concatenate([s[1] for s in segs])
        out["cheops_ev_lac"] = fl.tune_denoising(t, f, mission="CHEOPS", band="CHEOPS", wavelets=g["wavelets"], levels=g["levels"],
                                                 n_trials=g["n_trials"], per_trial=g["per_trial"], seed=PROTOCOL["seed"],
                                                 amp_range=(3e-4, 3e-2), fwhm_minutes=(0.5, 10.0))
    except ch.CheopsUnavailable as exc:
        out["cheops_ev_lac"] = {"error": str(exc)}
    lc = _tess(PROTOCOL["flares"]["proxima"]["tic"], [12])[0]
    out["tess_proxima_s12"] = fl.tune_denoising(lc.time, lc.flux, lc.flux_err, wavelets=g["wavelets"], levels=g["levels"],
                                                n_trials=g["n_trials"], per_trial=g["per_trial"], seed=PROTOCOL["seed"],
                                                amp_range=(1e-3, 1e-1), fwhm_minutes=(2.0, 30.0))
    return out


# ---------------------------------------------------------------- pulsation items


def _tol_match(ours, pub, T, key_f="frequency_uhz", key_s="sigma_uhz", unit_per_cd=pu.DAY_TO_UHZ):
    of = [x["frequency"] * unit_per_cd for x in ours]
    osig = {round(x["frequency"] * unit_per_cd, 6): (x["sigma_frequency"] or 0) * unit_per_cd for x in ours}
    pf = [x[key_f] for x in pub]
    med_sig = float(np.median(list(osig.values()))) if osig else 0.0
    strict_tol = [3 * math.hypot(x[key_s], med_sig) for x in pub]
    loose = (1.0 / T) * unit_per_cd
    return {"strict": pu.match_frequencies(of, pf, strict_tol), "loose": pu.match_frequencies(of, pf, loose),
            "loose_tolerance": loose}


def item_hr10_tess() -> dict:
    r = refs()["hr10"]
    p = PROTOCOL["pulsations"]
    out = {"star": "HR 10", "tic": r["tic"], "reference": r["source"], "reference_data": r["data"], "sectors": {}}
    for sec in PROTOCOL["pulsations"]["hr10"]["sectors"]:
        lc = _tess(r["tic"], [sec])[0]
        a = pu.analyse(lc.time, lc.flux, teff=8840.0, fmin=p["hr10"]["fmin_cd"], snr_stop=p["snr_stop"], noise_box=p["noise_box_cd"],
                       max_frequencies=p["max_frequencies"], n_surrogates=p["hr10"]["n_surrogates"] if sec == 29 else 0,
                       seed=PROTOCOL["seed"], solar=False)
        pw = a["prewhitening"]
        sig = [x for x in pw["frequencies"] if x["significant"]]
        sig5 = [x for x in sig if x["snr"] >= 5.0]
        pub = r["sectors"][str(sec)]
        m = _tol_match(sig, pub, pw["baseline_days"])
        m5 = _tol_match(sig5, pub, pw["baseline_days"])
        top = sorted(pub, key=lambda x: -x["amplitude_pct"])[:10]
        mt = _tol_match(sig, top, pw["baseline_days"])
        amp_pairs = []
        for pr in m["loose"]["pairs"]:
            if pr["ours"] is not None:
                o = min(sig, key=lambda x: abs(x["frequency_uhz"] - pr["ours"]))
                pp = next(x for x in pub if x["frequency_uhz"] == pr["published"])
                amp_pairs.append(o["amplitude"] * 100 / pp["amplitude_pct"])
        bg = a["background"]
        out["sectors"][str(sec)] = {
            "file_sha256": lc.provenance.get("file_sha256"), "n_significant": len(sig), "n_snr5": len(sig5),
            "published_n": len(pub), "stop": pw["stop"], "baseline_days": pw["baseline_days"],
            "recall_all_strict": m["strict"]["recall"], "recall_all_loose": m["loose"]["recall"],
            "recall_top10_strict": mt["strict"]["recall"], "recall_top10_loose": mt["loose"]["recall"],
            "recall_ci95_loose": fl.wilson(m["loose"]["matched"], len(pub)),
            "ours_snr5_matched_loose": m5["loose"]["ours_matched_fraction"],
            "amplitude_ratio_ours_over_published": _bootstrap_median(amp_pairs),
            "pairs_loose": m["loose"]["pairs"], "frequencies": pw["frequencies"],
            "type": a["type"], "background": {k: bg[k] for k in ("white", "components", "ncomp")},
            "null": a.get("null"),
        }
    bgc = out["sectors"]["29"]["background"]["components"]
    out["granulation"] = {"ours_b_uhz_s29": [c["b_uhz"] for c in bgc], "ours_exponent_s29": [c["c"] for c in bgc],
                          "published_b_uhz_s29": r["granulation_b_uhz"]["tess_s29"],
                          "note": "Salmon et al. fit one Harvey component to an averaged periodogram (25 one-day series); "
                                  "we fit one or two to the full periodogram by maximum likelihood"}
    return out


def item_hr10_cheops() -> dict:
    """HR 10's three public CHEOPS visits: each alone (2 days: the dense δ Scuti spectrum is not resolved), and the
    three together (22 days), with two passes: decorrelate, extract the pulsations, decorrelate again with the
    pulsations divided out, extract again."""
    r = refs()["hr10"]
    p = PROTOCOL["pulsations"]
    try:
        lst = ch.list_visits("HR 10", cache_dir=CACHE / "cheops")
    except ch.CheopsUnavailable as exc:
        return {"error": str(exc), "status": "unvalidated"}
    out = {"star": "HR 10", "visits": [], **ch.credit(lst["visits"])}
    pubf = [x["frequency_uhz"] for x in r["sectors"]["29"]]
    vis = [ch.fetch_visit(v, cache_dir=CACHE / "cheops") for v in lst["visits"]]
    dets = [ch.detrend_visit(v, protect_upward=False) for v in vis]

    def combined(ds):
        t = np.concatenate([d["time"][np.isfinite(d["flux"])] for d in ds])
        f = np.concatenate([d["flux"][np.isfinite(d["flux"])] / np.nanmedian(d["flux"]) for d in ds])
        o = np.argsort(t)
        return t[o], f[o]

    def model(pw, times):
        m = np.ones(times.size)
        for x in pw["frequencies"]:
            m += x["amplitude"] * np.sin(2 * math.pi * (x["frequency"] * (times - pw["t0"]) + x["phase"]))
        return m

    kw = dict(fmin=0.5, snr_stop=p["snr_stop"], noise_box=p["noise_box_cd"], max_frequencies=60)
    pw = pu.prewhiten(*combined(dets), **kw)
    dets = [ch.detrend_visit(v, protect_upward=False, signal=model(pw, v.time)) for v in vis]
    t, f = combined(dets)
    pw = pu.prewhiten(t, f, **kw)
    s = [x for x in pw["frequencies"] if x["significant"]]
    T = pw["baseline_days"]
    m = pu.match_frequencies([x["frequency_uhz"] for x in s], pubf, 1.0 / T * pu.DAY_TO_UHZ)
    top = sorted(r["sectors"]["29"], key=lambda x: -x["amplitude_pct"])[:10]
    mt = pu.match_frequencies([x["frequency_uhz"] for x in s], [x["frequency_uhz"] for x in top], 1.0 / T * pu.DAY_TO_UHZ)
    nu, psd = pu.power_density(pw["time"], pw["residual"])
    bg = pu.fit_background(nu, psd, fmin_uhz=max(nu[0], 20.0))
    out["combined"] = {"visits": len(vis), "baseline_days": T, "n_points": pw["n_points"], "n_significant": len(s),
                       "stop": pw["stop"], "recall_tess_s29_published": m["recall"], "ours_matched_fraction": m["ours_matched_fraction"],
                       "recall_top10": mt["recall"], "frequencies": s,
                       "f1_f2_recovered": [any(abs(x["frequency_uhz"] - f0) < 1.0 / T * pu.DAY_TO_UHZ for x in s)
                                           for f0 in (73.8543, 17.6931)],
                       "background_b_uhz": [c["b_uhz"] for c in bg["components"]], "terms": [d["terms"] for d in dets]}
    for v, d in zip(lst["visits"], dets):
        ok = np.isfinite(d["flux"])
        one = pu.prewhiten(d["time"][ok], d["flux"][ok], **kw)
        sv = [x for x in one["frequencies"] if x["significant"]]
        Tv = one["baseline_days"]
        out["visits"].append({"file_key": v["file_key"], "programme": ch.programme_id(v["file_key"]), "obs_id": v["obs_id"],
                              "pi": v["pi_name"], "terms": d["terms"], "rms_detrended_ppm": d["rms_detrended_ppm"],
                              "baseline_days": Tv, "n_significant": len(sv), "frequencies": sv,
                              "f1_f2_recovered": [any(abs(x["frequency_uhz"] - f0) < 1.0 / Tv * pu.DAY_TO_UHZ for x in sv)
                                                  for f0 in (73.8543, 17.6931)]})
    out["published_granulation_b_uhz_cheops_visit1"] = r["granulation_b_uhz"]["cheops_visit1"]
    out["note"] = ("Salmon et al. used PIPE photometry of the 3-s imagettes (67 ppm per minute); DACE serves the DRP "
                   "subarray light curve (42 s). They publish no CHEOPS frequency list, so ours is compared with "
                   "their TESS sector 29 list.")
    return out


def item_beta_pic() -> dict:
    r = refs()["beta_pic"]
    p = PROTOCOL["pulsations"]
    lcs = _tess(r["tic"], p["beta_pic"]["sectors"])
    t = np.concatenate([lc.time for lc in lcs])
    f = np.concatenate([lc.flux / np.median(lc.flux) for lc in lcs])
    a = pu.prewhiten(t, f, fmin=p["beta_pic"]["fmin_cd"], snr_stop=p["snr_stop"], noise_box=p["noise_box_cd"],
                     max_frequencies=p["max_frequencies"])
    sig = [x for x in a["frequencies"] if x["significant"]]
    pub = [{"frequency_uhz": x["frequency_cd"] * pu.DAY_TO_UHZ, "sigma_uhz": x["sigma_cd"] * pu.DAY_TO_UHZ,
            "amplitude_mmag": x["amplitude_mmag"]} for x in r["frequencies"]]
    m = _tol_match(sig, pub, a["baseline_days"])
    top = sorted(pub, key=lambda x: -x["amplitude_mmag"])[:10]
    mt = _tol_match(sig, top, a["baseline_days"])
    return {"star": "beta Pic", "tic": r["tic"], "reference": r["source"], "reference_data": r["data"],
            "sectors": p["beta_pic"]["sectors"], "file_sha256": [lc.provenance.get("file_sha256") for lc in lcs],
            "n_significant": len(sig), "published_n": len(pub), "baseline_days": a["baseline_days"], "stop": a["stop"],
            "recall_all_strict": m["strict"]["recall"], "recall_all_loose": m["loose"]["recall"],
            "recall_ci95_loose": fl.wilson(m["loose"]["matched"], len(pub)),
            "recall_top10_strict": mt["strict"]["recall"], "recall_top10_loose": mt["loose"]["recall"],
            "ours_matched_fraction_loose": m["loose"]["ours_matched_fraction"], "pairs_loose": m["loose"]["pairs"],
            "type": pu.classify(a["frequencies"], teff=8000.0), "frequencies": sig,
            "note": "Zieba et al. excluded sector 4; so do we. Amplitudes: theirs in mmag, ours in relative flux."}


def item_toi197() -> dict:
    r = refs()["toi197"]
    p = PROTOCOL["pulsations"]["toi197"]
    lc = _tess(r["tic"], p["sectors"])[0]
    s = pu.solar_like(lc.time, lc.flux, numax_range=(100.0, 2000.0), n_boot=p["n_boot"], seed=PROTOCOL["seed"])
    out = {"star": "TOI-197", "tic": r["tic"], "reference": r["source"], "reference_data": r["data"], "sectors": p["sectors"],
           "file_sha256": lc.provenance.get("file_sha256"), "published": {"numax_uhz": r["numax_uhz"], "dnu_uhz": r["dnu_uhz"]},
           "ours": {k: s.get(k) for k in ("detected", "why", "numax_uhz", "numax_err_uhz", "dnu_uhz", "dnu_err_uhz",
                                          "dnu_expected_uhz", "delta_bic_envelope", "numax_guess_uhz")},
           "data_note": "SetuHQ reads SPOC PDCSAP; Huber et al. used a TASOC light curve"}
    if s.get("detected"):
        nm, en = r["numax_uhz"]
        out["numax_z"] = (s["numax_uhz"] - nm) / math.hypot(en, s["numax_err_uhz"] or 0)
        if s.get("dnu_uhz"):
            dn, ed = r["dnu_uhz"]
            out["dnu_z"] = (s["dnu_uhz"] - dn) / math.hypot(ed, s["dnu_err_uhz"] or 0)
    return out


# ---------------------------------------------------------------- CHEOPS item


def item_cheops_pycheops() -> dict:
    p = PROTOCOL["cheops"]
    rows = []
    for fk in p["pycheops_visits"]:
        ref_p = PYCHEOPS_DIR / f"ref_{fk}.json"
        if not ref_p.exists():
            rows.append({"file_key": fk, "status": "unvalidated", "why": f"no pycheops reference at {ref_p.name}"})
            continue
        ref = json.loads(ref_p.read_text())
        found = None
        for name in PROTOCOL["flares"]["cheops_targets"]:
            lst = ch.list_visits(name, cache_dir=CACHE / "cheops")
            found = next((v for v in lst["visits"] if v["file_key"] == fk), None)
            if found:
                break
        if not found:
            rows.append({"file_key": fk, "status": "unvalidated", "why": "visit not in the public listing"})
            continue
        vis = ch.fetch_visit(found, cache_dir=CACHE / "cheops")
        rt = np.array(ref["time"]) + ref["bjd_ref"] - 2457000.0
        rf = np.array(ref["flux_decorrelated"])
        rr = np.array(ref["flux_raw"])
        idx = np.array([int(np.argmin(np.abs(vis.time - x))) for x in rt])
        m = np.abs(vis.time[idx] - rt) < 1e-5

        def cmp(a, b):
            ok = np.isfinite(a) & np.isfinite(b)
            a, b = a[ok] / np.median(a[ok]), b[ok] / np.median(b[ok])
            return {"rms_difference_ppm": float(np.std(a - b) * 1e6), "correlation": float(np.corrcoef(a, b)[0, 1]), "n": int(ok.sum())}

        d = ch.detrend_visit(vis, terms=p["terms"], protect_upward=False)
        ours = d["flux"][idx][m]
        # the same model on pycheops' own input points: isolates the decorrelation from the data preparation
        sub = ch.CheopsVisit(meta=vis.meta, time=vis.time[idx][m], flux=rr[m], flux_err=vis.flux_err[idx][m], roll=vis.roll[idx][m],
                             x=vis.x[idx][m], y=vis.y[idx][m], bg=vis.bg[idx][m], contam=vis.contam[idx][m],
                             flags=np.zeros(int(m.sum()), np.int64))
        d2 = ch.detrend_visit(sub, terms=p["terms"], protect_upward=False, clip_sigma=1e9)
        rows.append({"file_key": fk, "programme": ch.programme_id(fk), "obs_id": found["obs_id"], "pi": found["pi_name"],
                     "pycheops_version": ref.get("pycheops_version"), "points_matched": int(m.sum()), "points_ours": int(vis.time.size),
                     "end_to_end": cmp(ours, rf[m]), "same_input": cmp(d2["flux"], rf[m]),
                     "same_input_rms_ours_ppm": float(np.nanstd(d2["flux"]) * 1e6), "raw_inputs": cmp(vis.flux[idx][m], rr[m]),
                     "rms_ours_ppm": float(np.nanstd(ours) * 1e6), "rms_pycheops_ppm": float(np.std(rf[m]) * 1e6)})
    return {"visits": rows, "terms": p["terms"], **ch.credit([r for r in rows if "obs_id" in r])}


# The code each item depends on (its fingerprint keys the item's cache, so a change elsewhere does not rerun it).
_FLARE = ["flares.py", "passbands.py", "stellar_io.py"]
_PULS = ["pulsations.py", "stellar_io.py"]
_CHEOPS = ["cheops.py", "stellar_io.py"]
ITEM_FILES = {"cheops_flares": _FLARE + ["cheops.py"], "denoise_grid": _FLARE + ["cheops.py"], "hr10_tess": _PULS,
              "hr10_cheops": _PULS + ["cheops.py"], "beta_pic": _PULS, "toi197": _PULS, "cheops_pycheops": _CHEOPS}


def item_fingerprint(name: str) -> str:
    from setuhq.starsearch import _fingerprint

    return _fingerprint(ITEM_FILES.get(name, _FLARE))


ITEMS = {
    "aumic_gunther": item_aumic_gunther, "gunther_energy_star": item_gunther_energy_star,
    "proxima_medina": item_proxima_medina, "gj1243": item_gj1243, "gj65": item_gj65, "completeness": item_completeness,
    "quiet_stars": item_quiet_stars, "cheops_flares": item_cheops_flares, "denoise_grid": item_denoise_grid,
    "hr10_tess": item_hr10_tess, "hr10_cheops": item_hr10_cheops, "beta_pic": item_beta_pic, "toi197": item_toi197,
    "cheops_pycheops": item_cheops_pycheops,
}


def run_item(name: str, force: bool = False) -> dict:
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{name}.json"
    ident = {"protocol_sha256": protocol_hash(), "code_fingerprint": item_fingerprint(name),
             "code_files": ITEM_FILES.get(name, _FLARE)}
    if path.exists() and not force:
        old = json.loads(path.read_text())
        if {k: old.get(k) for k in ident} == ident and "result" in old:
            print(f"{name}: cached")
            return old
    t0 = time.time()
    try:
        result = ITEMS[name]()
        rec = {**ident, "item": name, "status": "ok", "seconds": round(time.time() - t0, 1), "result": _clean(result)}
    except Exception as exc:  # noqa: BLE001 (recorded, so the report can say what could not be validated)
        rec = {**ident, "item": name, "status": "error", "error": f"{type(exc).__name__}: {exc}",
               "trace": traceback.format_exc()[-3000:], "seconds": round(time.time() - t0, 1)}
    rec["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, default=_json, allow_nan=False))
    os.replace(tmp, path)
    print(f"{name}: {rec['status']} in {rec['seconds']} s")
    return rec


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--item", action="append", choices=sorted(ITEMS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(ITEMS))
    for n in (list(ITEMS) if a.all else a.item or []):
        run_item(n, a.force)
    if a.report:
        from stellar_validation_report import write_report  # noqa: E402

        write_report(ITEMS_DIR, OUT_JSON, OUT_MD, PROTOCOL, protocol_hash(), code_fingerprint(), refs())

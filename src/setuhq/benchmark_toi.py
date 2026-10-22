# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""S1c: a blind benchmark on real TESS Objects of Interest (ATLAS R, S1; E7 for the reliability idea).

1. **A frozen sample.** From the archive's ``toi`` table: TOIs dispositioned CP or KP (positives), FP (false
   positives) and FA (false alarms), with a period of 0.5–13 d (so a 27-day sector holds at least two
   transits), one TOI per star, drawn with a fixed seed. The sample, its dispositions and the table's fetch
   date are stored before anything runs, with a hash. Each star is assigned to a tuning or a held-out half by
   a hash of its TIC; nothing is tuned here, so both halves are reported and the held-out half is the headline.
2. **Blinding.** The pipeline sees only the light curve (blind subject ids); dispositions and ephemerides are
   used only when scoring.
3. **Controls.** Each star's light curve is also run flux-inverted (dips become bumps) and block-scrambled
   (every known TOI's transits removed, then 0.5-day blocks shuffled, so no real transit or periodicity
   survives): any vetted candidate there is a false alarm. Controls are vetted but not fitted (the fit's
   flags do not change whether a dip passes).
4. **The panel.** The Probes (the deterministic detectors) with their calibrated weights, the sector-wide
   BLS search, vetting and the limb-darkened fit; no FAP (it is not part of vetting).
5. **Scoring.** A TOI is *recovered* when a dip that passed vetting lies on its ephemeris (``match_toi``). An FP
   TOI the panel found is *flagged* when vetting rejected it or marked it with an eclipsing-binary sign
   (odd/even, secondary eclipse, V shape, density mismatch). Rates carry Wilson 95% intervals.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
COLUMNS = ("tid,toi,tfopwg_disp,pl_orbper,pl_orbpererr1,pl_tranmid,pl_tranmiderr1,pl_trandurh,pl_trandep,pl_rade,"
           "st_tmag,st_teff,st_logg,st_rad,rowupdate")
POSITIVE = ("CP", "KP")
SEED = 20261019
MAX_PERIOD = 13.0
EB_FLAGS = ("odd_even_mismatch", "secondary_eclipse", "v_shape", "density_mismatch")
RADIUS_BINS = [(0, 2), (2, 4), (4, 8), (8, 30)]
PERIOD_BINS = [(0.5, 2), (2, 5), (5, 13.0)]


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float | None, float | None, float | None]:
    """A proportion with its Wilson score interval (95% by default). ``None`` for n = 0."""
    if n <= 0:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def fetch_toi_table(cache: str | Path = "cache/toi/toi.csv", refresh: bool = False) -> tuple[list[dict], str]:
    """The TOI table (selected columns) and when it was fetched; cached so the sample can be rebuilt offline."""
    path = Path(cache)
    if refresh or not path.exists():
        q = f"select {COLUMNS} from toi"
        with urllib.request.urlopen(TAP + "?" + urllib.parse.urlencode({"query": q, "format": "csv"}), timeout=120) as resp:  # noqa: S310
            text = resp.read().decode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    fetched = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return list(csv.DictReader(io.StringIO(path.read_text()))), fetched


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def half_of(tic: int, seed: int = SEED) -> str:
    return "held_out" if int(hashlib.sha256(f"{seed}:{tic}".encode()).hexdigest(), 16) % 2 else "tuning"


def freeze_sample(rows: list[dict], *, fetched_at: str, n_pos: int = 300, n_fp: int = 300, n_fa: int = 100,
                  seed: int = SEED, max_period: float = MAX_PERIOD) -> dict:
    """Draw the benchmark: one eligible TOI per star, in a seeded order, until each class is full."""
    eligible: dict[int, list[dict]] = {}
    for r in rows:
        disp = (r.get("tfopwg_disp") or "").strip()
        p, t0, dur = _num(r.get("pl_orbper")), _num(r.get("pl_tranmid")), _num(r.get("pl_trandurh"))
        if disp not in POSITIVE + ("FP", "FA") or not p or not t0 or not dur or not (0.5 <= p <= max_period):
            continue
        tic = int(float(r["tid"]))
        eligible.setdefault(tic, []).append({
            "tic": tic, "toi": r["toi"], "disposition": disp, "class": "positive" if disp in POSITIVE else disp.lower(),
            "period": p, "period_err": _num(r.get("pl_orbpererr1")), "tranmid_bjd": t0, "tranmid_err": _num(r.get("pl_tranmiderr1")),
            "duration_hours": dur, "depth_ppm": _num(r.get("pl_trandep")), "radius_re": _num(r.get("pl_rade")),
            "tmag": _num(r.get("st_tmag")), "teff": _num(r.get("st_teff")), "logg": _num(r.get("st_logg")),
            "star_radius": _num(r.get("st_rad")), "rowupdate": r.get("rowupdate"),
        })
    rng = np.random.default_rng(seed)
    tics = sorted(eligible)
    rng.shuffle(tics)
    quota = {"positive": n_pos, "fp": n_fp, "fa": n_fa}
    chosen = []
    for tic in tics:
        options = [t for t in sorted(eligible[tic], key=lambda t: t["toi"]) if quota[t["class"]] > 0]
        if not options:
            continue
        pick = options[int(rng.integers(len(options)))]
        quota[pick["class"]] -= 1
        pick = dict(pick, half=half_of(tic, seed), other_tois=[t["toi"] for t in eligible[tic] if t["toi"] != pick["toi"]])
        chosen.append(pick)
        if all(v <= 0 for v in quota.values()):
            break
    body = json.dumps(chosen, sort_keys=True).encode()
    return {"source": "NASA Exoplanet Archive, table toi", "url": TAP, "fetched_at": fetched_at, "seed": seed,
            "rule": f"tfopwg_disp in CP/KP (positive), FP, FA; 0.5 ≤ P ≤ {max_period} d; period, mid-time and duration "
                    "published; one TOI per star; seeded order; halves by sha256(seed:TIC) parity",
            "counts": {c: sum(1 for t in chosen if t["class"] == c) for c in quota},
            "sha256": hashlib.sha256(body).hexdigest(), "tois": chosen}


# ---------- the controls ----------
def inverted(lc):
    """Flux mirrored about 1: transits become bumps, so a vetted dip here is a false alarm."""
    return lc.with_data(lc.time, 2.0 - lc.flux, lc.flux_err)


def mask_transits(lc, ephemerides: list[tuple[float, float, float]], *, pad: float = 1.5):
    """The light curve without the points inside any known transit: (period d, mid-time BTJD, T14 h) each,
    removed out to ``pad`` × T14/2 either side of every epoch."""
    t = lc.time
    keep = np.ones(t.size, bool)
    for period, t0, dur_h in ephemerides:
        if not period or not t0 or not dur_h:
            continue
        phase = (t - t0 + 0.5 * period) % period - 0.5 * period
        keep &= np.abs(phase) > pad * 0.5 * dur_h / 24
    return lc.with_data(t[keep], lc.flux[keep], lc.flux_err[keep])


def scrambled(lc, *, block_days: float = 0.5, seed: int = 0, ephemerides: list | None = None):
    """0.5-day blocks shuffled in time (times kept): correlated noise survives, any periodicity does not.
    The star's known transits are removed first, so a vetted dip here is a false alarm, not a real transit
    moved to a new time."""
    if ephemerides:
        lc = mask_transits(lc, ephemerides)
    t = lc.time
    cadence = float(np.median(np.diff(t))) if t.size > 1 else 1.0
    per = max(2, int(round(block_days / cadence)))
    blocks = [np.arange(i, min(i + per, t.size)) for i in range(0, t.size, per)]
    order = np.concatenate([blocks[i] for i in np.random.default_rng(seed).permutation(len(blocks))])
    return lc.with_data(t, lc.flux[order], lc.flux_err[order])


# ---------- scoring ----------
def target_for(toi: dict):
    from setuhq.discover import Target, Toi

    return Target(tic=toi["tic"], tois=[Toi(name=toi["toi"], period=toi["period"], tranmid=toi["tranmid_bjd"],
                                            period_err=toi["period_err"], tranmid_err=toi["tranmid_err"],
                                            duration_hours=toi["duration_hours"], disposition=toi["disposition"])])


def alias(found: float | None, true: float) -> str | None:
    """How a found period relates to the TOI's: 1, 2, 1/2, 3, 1/3, 3/2 or 2/3 (within 1%), else None."""
    if not found:
        return None
    for name, f in (("P", 1), ("2P", 2), ("P/2", 0.5), ("3P", 3), ("P/3", 1 / 3), ("3P/2", 1.5), ("2P/3", 2 / 3)):
        if abs(found - f * true) <= 0.01 * f * true:
            return name
    return None


def score_star(toi: dict, candidates: list[dict]) -> dict:
    """What the panel did with one TOI's star: recovered (a passed dip on the ephemeris), seen-but-rejected, the
    EB flags on its dips, and every other passed dip (not on the ephemeris)."""
    from setuhq.discover import match_toi

    target = target_for(toi)
    on, off = [], []
    for c in candidates:
        m = match_toi(c, target)
        (on if m else off).append((c, m))
    passed_on = [c for c, _ in on if c["passed"]]
    flags = sorted({f for c, _ in on for f in (c["flags"].split(";") if isinstance(c["flags"], str) else c["flags"]) if f in EB_FLAGS})
    best = max(passed_on, key=lambda c: c.get("snr") or 0) if passed_on else None
    fit = (best or {}).get("fit") or {}
    return {
        "toi": toi["toi"], "class": toi["class"], "recovered": bool(passed_on), "seen": bool(on),
        "rejected_on_ephemeris": bool(on) and not passed_on, "eb_flags": flags,
        "flagged": bool(on) and (not passed_on or bool(flags)),
        "period_alias": alias((best or {}).get("period_days"), toi["period"]),
        "depth_ratio": fit["depth_ppm"] / toi["depth_ppm"] if fit.get("depth_ppm") and toi.get("depth_ppm") else None,
        "duration_ratio": fit["t14_hours"] / toi["duration_hours"] if fit.get("t14_hours") and toi.get("duration_hours") else None,
        "other_passed": sum(1 for c, _ in off if c["passed"]),
    }


def rates(rows: list[dict], key: str, where=lambda r: True) -> dict:
    sel = [r for r in rows if where(r)]
    k = sum(1 for r in sel if r[key])
    p, lo, hi = wilson(k, len(sel))
    return {"k": k, "n": len(sel), "rate": p, "lo": lo, "hi": hi}


def mcnemar_p(lost: int, gained: int) -> float:
    """Exact two-sided McNemar test on the discordant pairs (a binomial test of gained against lost at p = 1/2)."""
    from math import comb

    n = lost + gained
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(lost, gained) + 1)) / 2**n
    return min(1.0, 2 * tail)


PAIRED_DRAWS = 20000


def paired_change(before: list[bool], after: list[bool], draws: int = PAIRED_DRAWS, seed: int = SEED) -> dict:
    """The same stars measured twice (before and after a code change): each rate with its Wilson interval, the change
    in the rate with a paired bootstrap 95% interval (stars resampled, both measurements kept together), and the exact
    McNemar test on the stars that changed."""
    b, a = np.asarray(before, bool), np.asarray(after, bool)
    n = len(b)
    out = {"n": n, "before": rates([{"x": x} for x in b], "x"), "after": rates([{"x": x} for x in a], "x"),
           "gained": int(np.sum(~b & a)), "lost": int(np.sum(b & ~a)), "draws": draws, "seed": seed}
    if n == 0:
        return out | {"delta": None, "lo": None, "hi": None, "mcnemar_p": 1.0}
    idx = np.random.default_rng(seed).integers(0, n, size=(draws, n))
    ds = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    lo, hi = np.percentile(ds, [2.5, 97.5])
    return out | {"delta": float(a.mean() - b.mean()), "lo": float(lo), "hi": float(hi),
                  "mcnemar_p": mcnemar_p(out["lost"], out["gained"])}


CLAUDE_PAIR = ("claude-volunteer", "claude-skeptic")  # the benchmarked default: one Claude model, two personas


def sentinel_summary(data: dict, sample: dict, match) -> dict:
    """The Sentinels on the stated subsample, per reviewer and per pair.

    ``data`` is ``cache/bench/sentinels.json``: per TOI, per reviewer, per subject the label and marks.
    ``match(candidate, target)`` decides whether a mark lies on the TOI's ephemeris (``discover.match_toi``).
    Per reviewer: on CP/KP stars, did it mark a dip on the TOI's ephemeris as a potential planet; on FP stars,
    did it pass the TOI's dip as a potential planet. Per pair: agreement and φ over the stars both answered
    (:mod:`setuhq.agreement`), labelled same model or different provider/model.
    """
    from setuhq.agreement import constant_reviewers, effective_voters, pairwise

    toi = {t["toi"]: t for t in sample["tois"]}
    rows: dict[str, dict] = {}
    for name, per in data["results"].items():
        target = target_for(toi[name])
        for rid, subs in per.items():
            ok = [s for s in subs.values() if "error" not in s]
            hit = any(match({"t_center": 0.5 * (a + b), "duration_hours": (b - a) * 24, "period_days": None, "time_unit": "BTJD"}, target)
                      for s in ok if s["label"] == "potential_planet" for a, b in s["marks"])
            rows.setdefault(name, {})[rid] = {"hit": hit, "errors": len(subs) - len(ok)}
    seen = sorted({rid for r in rows.values() for rid in r})
    ids = [r for r in CLAUDE_PAIR if r in seen] + [r for r in seen if r not in CLAUDE_PAIR]
    identities = data.get("reviewers") or {}
    out = {"subsample": data["subsample"], "n_stars": len(rows), "personas": {}, "reviewers": identities}
    models = Counter(_model_label(s) for per in data["results"].values() for subs in per.values() for s in subs.values()
                     if "error" not in s)
    out["models"] = dict(models)
    out["model_note"] = ("the model id each provider reported for each review (the Claude Code CLI's modelUsage), with the call "
                         "date; \"not recorded\" for reviews answered before SetuHQ stored it (the cache key then held only "
                         "\"default\"); a configured id the provider did not report is marked so")
    for rid in ids:
        pos = [{"x": r[rid]["hit"]} for n, r in rows.items() if rid in r and toi[n]["class"] == "positive"]
        fp = [{"x": r[rid]["hit"]} for n, r in rows.items() if rid in r and toi[n]["class"] == "fp"]
        out["personas"][rid] = {"cp_kp_marked": rates(pos, "x"), "fp_marked_as_planet": rates(fp, "x"),
                                "errors": sum(r[rid]["errors"] for r in rows.values() if rid in r)}
    hits = {n: {rid: v["hit"] for rid, v in r.items()} for n, r in rows.items()}
    table = pairwise(hits, ids, identities)
    out["pairwise"] = table
    constant = constant_reviewers(hits, ids)
    out["effective_voters"] = effective_voters(table, ids, constant)
    out["effective_voters_k"] = len(ids) - len(constant)
    out["constant_reviewers"] = constant
    # The benchmarked pair, under its first name, so earlier reports read the same.
    pair = next((p for p in table if (p["a"], p["b"]) == CLAUDE_PAIR), None)
    if pair is not None:
        out["agreement"] = {k: pair[k] for k in ("n", "agree", "phi")}
    return out


def _model_label(review: dict) -> str:
    """The model a stored Sentinel review names: the reported id, a configured id marked as such, or "not recorded"."""
    model = review.get("model")
    if not model:
        return "not recorded"
    if review.get("model_reported") is False:
        return f"{model} (configured; not reported by the provider)"
    return model


def summarise(results: list[dict], sample: dict) -> dict:
    """Completeness, FP flagging and false alarms, overall and by radius and period, for each half."""
    toi = {t["toi"]: t for t in sample["tois"]}
    out = {}
    for half in ("held_out", "tuning", "all"):
        rs = [r for r in results if half == "all" or toi[r["toi"]]["half"] == half]
        real = [r["real"] for r in rs if r.get("real")]
        pos = [s for s in real if s["class"] == "positive"]
        fp = [s for s in real if s["class"] == "fp"]
        fa = [s for s in real if s["class"] == "fa"]
        by = lambda rows, key, field, bins: [dict(rates(rows, key, lambda s, a=a, b=b: toi[s["toi"]].get(field) is not None and a <= toi[s["toi"]][field] < b), bin=[a, b]) for a, b in bins]
        controls = {}
        for v in ("inverted", "scrambled"):
            fa_counts = [r[v]["passed"] for r in rs if r.get(v) is not None]
            controls[v] = {"star_sectors": len(fa_counts), "vetted_false_alarms": int(sum(fa_counts)),
                           "per_1000_star_sectors": 1000 * sum(fa_counts) / len(fa_counts) if fa_counts else None,
                           "stars_with_any": rates([{"x": c > 0} for c in fa_counts], "x")}
        out[half] = {
            "completeness": rates(pos, "recovered"),
            "completeness_by_radius": by(pos, "recovered", "radius_re", RADIUS_BINS),
            "completeness_by_period": by(pos, "recovered", "period", PERIOD_BINS),
            "fp_seen": rates(fp, "seen"), "fp_flagged_of_seen": rates([s for s in fp if s["seen"]], "flagged"),
            "fp_passed_unflagged": rates(fp, "recovered", ) | {"note": "FP TOIs whose dip passed vetting (with or without EB flags)"},
            "fa_seen": rates(fa, "seen"),
            "pos_flagged": rates([s for s in pos if s["seen"]], "flagged"),
            "period_aliases": {a: sum(1 for s in pos if s["period_alias"] == a) for a in ("P", "2P", "P/2", "3P", "P/3", "3P/2", "2P/3", None)},
            "depth_ratio_median": float(np.median([s["depth_ratio"] for s in pos if s["depth_ratio"]])) if any(s["depth_ratio"] for s in pos) else None,
            "duration_ratio_median": float(np.median([s["duration_ratio"] for s in pos if s["duration_ratio"]])) if any(s["duration_ratio"] for s in pos) else None,
            "controls": controls,
            "no_data": sum(1 for r in rs if not r.get("real")),
            # Not searchable: no SPOC 2-minute light curve (or the download failed). Kept as its own row, by class.
            "not_searchable": {c: sum(1 for r in rs if str(r.get("no_data", "")).startswith("no SPOC") and toi[r["toi"]]["class"] == c)
                               for c in ("positive", "fp", "fa")},
            # Stars whose download or run failed even after a retry: not a property of the star, so counted apart.
            "failed": sum(1 for r in rs if not r.get("real") and not str(r.get("no_data", "")).startswith("no SPOC")),
            # Completeness over every CP/KP star in the half, counting a star without 2-minute data as not recovered.
            "completeness_all_stars": rates([{"x": bool(r.get("real") and r["real"]["recovered"])} for r in rs
                                             if toi[r["toi"]]["class"] == "positive"], "x"),
            "feed": _feed_summary(rs),
        }
    return out


CLASSES = (("positive", "CP/KP"), ("fp", "FP"), ("fa", "FA"))


def loss_table(results: list[dict], sample: dict) -> dict:
    """For each half and class: TOIs in the sample, stars run with data, not searchable (no SPOC 2-minute light
    curve), failed (download or run failed, not retried successfully), and not yet run. A loss that differs by class
    would bias completeness (CP/KP) against reliability (FP, FA)."""
    res = {r["toi"]: r for r in results}
    out = {}
    for half in ("held_out", "tuning"):
        for cls, _ in CLASSES:
            tois = [t for t in sample["tois"] if t["half"] == half and t["class"] == cls]
            rows = [res.get(t["toi"]) for t in tois]
            no_spoc = sum(1 for r in rows if r and str(r.get("no_data", "")).startswith("no SPOC"))
            data = sum(1 for r in rows if r and r.get("real"))
            missing = sum(1 for r in rows if r is None)
            out.setdefault(half, {})[cls] = {"n": len(tois), "data": data, "not_searchable": no_spoc,
                                             "failed": len(tois) - data - no_spoc - missing, "not_run": missing}
    return out


def _loss_lines(loss: dict) -> list[str]:
    lines = ["## What could not be measured, by class and half", "",
             "| half | class | TOIs | run with data | not searchable (no SPOC 2-min) | download or run failed | not run |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for half, per in loss.items():
        for cls, label in CLASSES:
            v = per[cls]
            lines.append(f"| {half.replace('_', '-')} | {label} | {v['n']} | {v['data']} | {v['not_searchable']} | {v['failed']} | {v['not_run']} |")
    lines.append("")
    for half, per in loss.items():
        h = half.replace("_", "-")
        fail = {label: per[c]["failed"] + per[c]["not_run"] for c, label in CLASSES}
        if any(fail.values()):
            frac = {label: fail[label] / per[c]["n"] for c, label in CLASSES if per[c]["n"]}
            spread = max(frac.values()) - min(frac.values())
            lines.append(f"{h} half, lost to download or run failures: " + ", ".join(f"{k} {100 * v:.0f}%" for k, v in frac.items())
                         + (f"; **skewed by {100 * spread:.0f} points across classes, which biases completeness against reliability.**"
                            if spread > 0.10 else f"; the shares differ by {100 * spread:.0f} points across classes."))
        else:
            lines.append(f"{h} half: no star was lost to a download or run failure.")
        ns = {label: per[c]["not_searchable"] / per[c]["n"] for c, label in CLASSES if per[c]["n"]}
        if not ns:
            continue
        n_all, n_data = sum(per[c]["n"] for c, _ in CLASSES), sum(per[c]["data"] for c, _ in CLASSES)
        if n_all and n_data:
            lines.append(f"{h} half, class mix: sample " + ", ".join(f"{per[c]['n']} {label} ({100 * per[c]['n'] / n_all:.0f}%)" for c, label in CLASSES)
                         + "; searched " + ", ".join(f"{per[c]['data']} {label} ({100 * per[c]['data'] / n_data:.0f}%)" for c, label in CLASSES) + ".")
        spread = max(ns.values()) - min(ns.values())
        fp = per["fp"]
        lines.append(f"{h} half, not searchable (no SPOC 2-minute light curve): " + ", ".join(f"{k} {100 * v:.0f}%" for k, v in ns.items())
                     + (f". **This loss is skewed toward FP ({100 * spread:.0f} points): FP TOIs are more often found in full-frame images "
                        f"only. The FP measures describe the {fp['data']} of {fp['n']} FP TOIs whose stars have 2-minute data, a different "
                        "population from the full TOI FP list, so they are not the panel's reliability on all FP TOIs.**"
                        if spread > 0.10 else "."))
    lines += ["", "Not searchable is a property of the star (the TOI came from full-frame images) and is reported, not repaired.", ""]
    return lines


def clipping_summary(results: list[dict], sample: dict, ratio: float) -> dict:
    """Exposure to the preprocess.clean clipping bug of the code version that produced these numbers, per half:
    stars with a depth/scatter ratio above ``ratio`` by class, and the affected CP/KP misses whose in-transit points
    clean() removed (at least half of them: the miss is explained by the bug)."""
    toi = {t["toi"]: t for t in sample["tois"]}
    out = {"ratio": ratio}
    for half in ("held_out", "tuning", "all"):
        rs = [r for r in results if r.get("real") and (half == "all" or toi[r["toi"]]["half"] == half)]
        measured = [r for r in rs if r.get("clip")]
        aff = [r for r in measured if r["clip"]["affected"]]
        pos_aff = [r for r in aff if toi[r["toi"]]["class"] == "positive"]
        missed = [r for r in pos_aff if not r["real"]["recovered"]]
        explained = [r for r in missed if (r["clip"].get("in_transit_removed_fraction") or 0) >= 0.5]
        removed = [r["clip"]["in_transit_removed_fraction"] for r in aff if r["clip"].get("in_transit_removed_fraction") is not None]
        out[half] = {"stars_with_data": len(rs), "measured": len(measured),
                     "affected": {c: sum(1 for r in aff if toi[r["toi"]]["class"] == c) for c in ("positive", "fp", "fa")},
                     "cp_kp_affected_recovered": len(pos_aff) - len(missed), "cp_kp_affected_missed": len(missed),
                     "cp_kp_misses_explained": len(explained), "explained_tois": sorted(r["toi"] for r in explained),
                     "median_removed_fraction_affected": float(np.median(removed)) if removed else None}
    return out


def _clip_lines(data: dict) -> list[str]:
    c = data.get("clipping")
    if not c:
        return []
    if data.get("edition") == "clipfix":
        return _clipfix_lines(data)
    h, hu = data["summary"]["held_out"], (data.get("summary_unaffected") or {}).get("held_out")
    ch = c["held_out"]
    a = ch["affected"]
    lines = ["", "### Known bug in this code version: preprocess clipping", "",
             "`preprocess.clean` in the code that produced these numbers deletes every point more than 10× the point-to-point "
             "scatter below the 0.5-day running median, with no run-length test, so a transit or eclipse deeper than about "
             "10× the per-cadence scatter loses its in-transit points before review and BLS. A star is marked affected when "
             f"the TOI depth is more than {c['ratio']:g}× the per-cadence scatter of the light curve used. The fix is on a "
             "separate branch; after it merges only the affected stars are re-run, reported as a separate update.", "",
             f"Held-out affected stars: {a['positive']} CP/KP, {a['fp']} FP, {a['fa']} FA (of {ch['measured']} measured). "
             f"Affected CP/KP recovered anyway: {ch['cp_kp_affected_recovered']}; missed: {ch['cp_kp_affected_missed']}, of which "
             f"{ch['cp_kp_misses_explained']} lost at least half of their in-transit points to clean() (explained by the bug)"
             + (f": TOI {', '.join(ch['explained_tois'])}." if ch["explained_tois"] else ".")
             + (f" Median share of in-transit points removed on affected stars: {100 * ch['median_removed_fraction_affected']:.0f}%."
                if ch["median_removed_fraction_affected"] is not None else ""), ""]
    if hu:
        lines += ["| held-out measure | all stars | affected stars excluded |", "|---|---|---|",
                  f"| Completeness (headline, searchable stars) | {_pct(h['completeness'])} | {_pct(hu['completeness'])} |",
                  f"| FP TOIs found | {_pct(h['fp_seen'])} | {_pct(hu['fp_seen'])} |",
                  f"| … rejected or flagged binary-like | {_pct(h['fp_flagged_of_seen'])} | {_pct(hu['fp_flagged_of_seen'])} |"]
        for v in ("inverted", "scrambled"):
            f, fu = (h.get("feed") or {}).get(v), (hu.get("feed") or {}).get(v)
            if f and fu and f["new_signals_per_1000"] is not None and fu["new_signals_per_1000"] is not None:
                lines.append(f"| {v} control, feed-level false signals per 1,000 star-sectors | {f['new_signals_per_1000']:.0f} | {fu['new_signals_per_1000']:.0f} |")
        lines.append("")
    return lines


def _clipfix_lines(data: dict) -> list[str]:
    """The clipping bug's exposure on the fixed code: the same exposed stars, and what became of them."""
    c, cmp = data["clipping"], (data.get("against_first_run") or {}).get("clipping") or {}
    h, hu = data["summary"]["held_out"], (data.get("summary_unaffected") or {}).get("held_out")
    ch = c["held_out"]
    a = ch["affected"]
    med = ch["median_removed_fraction_affected"]
    lines = ["", "### The clipping bug, fixed: the stars it affected", "",
             "The first run's `preprocess.clean` deleted every point more than 10× the point-to-point scatter below the 0.5-day "
             "running median, so a transit deeper than about 10× the per-cadence scatter lost its in-transit points before review "
             "and BLS. This code removes a low point only when it is not part of a dip (a run of at least max(3, 20 minutes / "
             f"cadence) cadences more than 3σ below the median). A star is exposed when the TOI depth is more than {c['ratio']:g}× "
             "the per-cadence scatter of the light curve used (the same light curves as the first run, so the same stars).", "",
             f"Held-out exposed stars: {a['positive']} CP/KP, {a['fp']} FP, {a['fa']} FA (of {ch['measured']} measured)."
             + ((f" Share of in-transit points clean() removes on them now: median {100 * med:.0f}%"
                 + (f" (first run: {100 * cmp['first_median_removed']:.0f}%)." if cmp.get("first_median_removed") is not None else "."))
                if med is not None else "")
             + (f" Exposed CP/KP recovered: {cmp['now_recovered']} of {cmp['n']} (first run: {cmp['first_recovered']} of {cmp['n']})."
                if cmp.get("n") is not None else "")
             + (f" The {len(cmp['first_explained'])} misses the first run's bug explained (TOI {', '.join(cmp['first_explained'])}): "
                + (f"recovered now: TOI {', '.join(cmp['explained_now_recovered'])}" if cmp["explained_now_recovered"] else "none recovered now")
                + (f"; still missed: TOI {', '.join(cmp['explained_still_missed'])}." if cmp["explained_still_missed"] else ".")
                if cmp.get("first_explained") else ""), ""]
    if hu:
        lines += ["| held-out measure, this run | all stars | exposed stars excluded |", "|---|---|---|",
                  f"| Completeness (headline, searchable stars) | {_pct(h['completeness'])} | {_pct(hu['completeness'])} |",
                  f"| FP TOIs found | {_pct(h['fp_seen'])} | {_pct(hu['fp_seen'])} |",
                  f"| … rejected or flagged binary-like | {_pct(h['fp_flagged_of_seen'])} | {_pct(hu['fp_flagged_of_seen'])} |", ""]
    return lines


def _num_text(v) -> str:
    if isinstance(v, dict):
        return _pct(v)
    if isinstance(v, float):
        return f"{v:.0f}"
    return "—" if v is None else str(v)


def _change_text(pc: dict | None) -> str:
    if not pc or pc.get("delta") is None:
        return ""
    sg = lambda x: f"{100 * x:+.0f}".replace("-", "−")  # noqa: E731
    return (f"{sg(pc['delta'])} points (95% CI {sg(pc['lo'])} to {sg(pc['hi'])}); "
            f"{pc['gained']} gained, {pc['lost']} lost; McNemar p = {pc['mcnemar_p']:.2g}")


def _against_first_lines(data: dict) -> list[str]:
    """This run against the first run (pre-fix code), measure by measure, paired on the same stars where it can be."""
    af = data.get("against_first_run")
    if not af:
        return []
    lines = ["", "## Against the first run (pre-fix code)", "",
             f"The first run ({af['file']}, pipeline code {af['code']}) is kept as the historical pre-fix record. Same sample, "
             "seed, split, light curves, controls and scoring; only the code differs. Where both runs measured the same stars the "
             f"change is paired: a bootstrap over the stars ({PAIRED_DRAWS:,} draws, seed {SEED}) and the exact McNemar test on "
             "the stars whose outcome changed.", "",
             "| held-out measure | first run (pre-fix code) | this run | change, paired on the same stars |", "|---|---|---|---|"]
    for r in af["rows"]:
        lines.append(f"| {r['measure']} | {_num_text(r['first'])} | {_num_text(r['this'])} | {_change_text(r.get('paired'))} |")
    lines.append("")
    if af.get("note"):
        lines += [af["note"], ""]
    return lines


def _feed_summary(rs: list[dict]) -> dict | None:
    """Dips the live discovery feed would admit (its full rule, FAP < 0.01 over 200 trials included), per variant.

    On the controls every admitted dip is a false alarm. On the real curves a dip that matches no TOI on the star
    would enter the feed as ``new_candidate``."""
    feeds = [r["feed"] for r in rs if r.get("feed") and "error" not in r["feed"]]
    if not feeds:
        return None
    out = {}
    for v in ("real", "inverted", "scrambled"):
        rows = [f[v] for f in feeds if f.get(v)]
        n = len(rows)
        new_sig = sum(x["new_signals"] for x in rows)
        out[v] = {"star_sectors": n, "pre_fap": sum(x["pre_fap"] for x in rows), "admitted": sum(x["admitted"] for x in rows),
                  "new_candidate_entries": sum(x["new_candidate"] for x in rows), "known_toi_entries": sum(x["known_toi"] for x in rows),
                  "new_signals": new_sig, "new_signals_per_1000": 1000 * new_sig / n if n else None,
                  "stars_with_new": rates([{"x": x["new_signals"] > 0} for x in rows], "x")}
    return out


def _pct(r: dict | None) -> str:
    if not r or r.get("rate") is None:
        return "—"
    return f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']}; 95% CI {100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)"


def _not_searchable(h: dict) -> str:
    ns = h.get("not_searchable") or {}
    fail = f"; {h['failed']} more failed to download or run and are left out" if h.get("failed") else ""
    skew = "; **skewed toward FP**, see the class breakdown below" if ns.get("fp", 0) > 2 * max(1, ns.get("positive", 0)) else ""
    return (f"{sum(ns.values())} stars ({ns.get('positive', 0)} CP/KP, {ns.get('fp', 0)} FP, {ns.get('fa', 0)} FA); excluded from every rate "
            f"except the all-stars completeness{fail}{skew}")


FEED_SECTORS_PER_TARGET = 2  # discover.run_discovery reviews each target's two latest sectors


def feed_implication(h: dict, live: dict | None) -> dict | None:
    """What the controls' feed-level false-alarm rate implies for the live feed's new_candidate rate."""
    f = h.get("feed")
    if not f:
        return None
    ctrl = {v: f[v]["new_signals_per_1000"] for v in ("inverted", "scrambled") if f[v]["new_signals_per_1000"] is not None}
    if not ctrl:
        return None
    worst = max(ctrl.values())
    expected = worst / 1000 * FEED_SECTORS_PER_TARGET * 100  # false new_candidate signals per 100 targets
    out = {"control_new_signals_per_1000": ctrl, "expected_false_per_100_targets": expected,
           "real_new_signals_per_1000": f["real"]["new_signals_per_1000"]}
    if live and live.get("targets_reviewed"):
        observed = 100 * live["new_signals"] / live["targets_reviewed"]
        out["live_new_signals_per_100_targets"] = observed
        _, lo, hi = wilson(min(live["new_signals"], live["targets_reviewed"]), live["targets_reviewed"])
        out["live_ci_per_100_targets"] = [100 * lo, 100 * hi]
        out["live"] = live
        out["bad"] = expected >= 0.5 * observed if observed else expected > 0
    else:
        out["bad"] = expected >= 1.0
    return out


def _feed_lines(data: dict, h: dict) -> list[str]:
    f = h.get("feed")
    if not f:
        return ["", "The discovery feed's full rule (with its FAP) has not been applied to this run yet."]
    lines = ["", "### At the discovery feed's level (held-out)", "",
             "The live feed admits a dip only when it passed vetting, is on its own star's periodic signal (not `off_ephemeris`), is at "
             "most 5,000 ppm deep, has at least two transits and a FAP below 0.01 over 200 block-bootstrap trials "
             "(discover.run_discovery, configs/discovery.toml). The same rule, run with the feed's weights file, on each curve:", "",
             "| curve | star-sectors | dips before the FAP test | admitted | as `new_candidate` (entries) | distinct new signals | per 1,000 star-sectors | star-sectors with any |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for v in ("real", "inverted", "scrambled"):
        r = f[v]
        lines.append(f"| {v} | {r['star_sectors']} | {r['pre_fap']} | {r['admitted']} | {r['new_candidate_entries']} | {r['new_signals']} | "
                     f"{r['new_signals_per_1000']:.0f} | {_pct(r['stars_with_new'])} |" if r["new_signals_per_1000"] is not None else f"| {v} | 0 | | | | | | |")
    imp = data.get("feed_implication")
    if imp:
        lines += ["", "On the controls every admitted dip is a false alarm. On the real curves a `new_candidate` is a dip on no "
                  "published TOI of that star: it may be another planet, but most are expected to be false alarms.", ""]
        txt = (f"**What this implies for the live feed.** The worse control gives {max(imp['control_new_signals_per_1000'].values()):.0f} false "
               f"new signals per 1,000 star-sectors. The feed reviews {FEED_SECTORS_PER_TARGET} sectors per target, so it should expect about "
               f"{imp['expected_false_per_100_targets']:.1f} false `new_candidate` signals per 100 targets from noise alone.")
        if imp.get("live_new_signals_per_100_targets") is not None:
            lv = imp["live"]
            txt += (f" The live catalogue ({lv['source']}) holds {lv['new_signals']} distinct new signals over {lv['targets_reviewed']} targets, "
                    f"{imp['live_new_signals_per_100_targets']:.1f} per 100 targets.")
        if imp["bad"]:
            txt += (" **This is bad: false alarms alone could account for at least half of the feed's `new_candidate` rate, so a "
                    "`new_candidate` on the feed is more likely noise than a signal.**")
        else:
            txt += " False alarms alone account for less than half of the feed's `new_candidate` rate."
        lines.append(txt)
        if data.get("edition") == "clipfix":
            lines += ["", "This table keeps the rule the protocol was frozen with (FAP < 0.01 over 200 trials, one sector), and the "
                      "live catalogue it compares with is the one built under that rule, with pre-fix code. The feed has since moved "
                      "to the pre-registered two-sector rule; it is measured on this code at the end of this report."]
        else:
            lines += ["", "**Proposed next step (not applied here).** Require the signal to be found independently in each of the "
                      "two sectors the feed reviews, and raise the FAP evidence to 2,000 trials with a 0.001 cut. Choose the rule on "
                      "the tuning half only, then measure it once on the held-out half (both controls and CP/KP completeness) before "
                      "changing configs/discovery.toml. No threshold was changed on this sample."]
    return lines


def _headline(data: dict) -> list[str]:
    imp = data.get("feed_implication")
    if not imp or imp.get("live_new_signals_per_100_targets") is None:
        return []
    word = "consistent with noise" if imp["bad"] else "not explained by noise alone"
    return [f"**Headline: the live discovery feed's \"new\" signals are {word}.** On light curves with every real signal "
            f"destroyed (flux-inverted and scrambled), the feed's own rule admits about {imp['expected_false_per_100_targets']:.0f} "
            f"false new signals per 100 targets reviewed; the live feed shows {imp['live_new_signals_per_100_targets']:.1f} new "
            "signals per 100 targets"
            + (f" ({imp['live']['new_signals']} over {imp['live']['targets_reviewed']} targets; 95% CI {imp['live_ci_per_100_targets'][0]:.0f}–"
               f"{imp['live_ci_per_100_targets'][1]:.0f})" if imp.get("live_ci_per_100_targets") else "")
            + (f". On the real light curves of TOI hosts the same rule found {imp['real_new_signals_per_1000']:.0f} new signals per 1,000 star-sectors."
               if imp.get("real_new_signals_per_1000") is not None else ".")
            + (" The feed has since moved to a pre-registered two-sector rule, measured on this code at the end of this report."
               if data.get("edition") == "clipfix" else
               " A fix is proposed below" + ("; it was later pre-registered and tested, see the update at the end." if data.get("feed_rule") else ", not applied.")), ""]


def _ci(r: dict | None) -> str:
    return _pct(r) if r else "—"


def _fold(o: dict, n: dict) -> str:
    a, b = o["expected_false_per_100_targets"], n["expected_false_per_100_targets"]
    return f"{a / b:.1f}-fold" if b else "to zero"


def clipfix_feed_rule_lines(fr: dict) -> list[str]:
    """The pre-registered two-sector rule measured again, unchanged, on the fixed code; and the live feed re-run on it."""
    v, first, live = fr["validation"], fr.get("first_validation"), fr.get("live")
    n, o = v["held_out"], v["held_out_old_rule"]
    r = v["rule"]
    f = lambda x: f"{x['expected_false_per_100_targets']:.1f} ({x['expected_false_ci_per_100_targets'][0]:.1f}–{x['expected_false_ci_per_100_targets'][1]:.1f})"
    fn = (first or {}).get("held_out")
    col = " | two-sector rule, first evaluation (pre-fix code)" if fn else ""
    sep = "|---" if fn else ""
    x = lambda txt: f" | {txt}" if fn else ""
    lines = ["", "## The two-sector feed rule on this code", "",
             f"The feed's rule since 2026-10-20 was chosen on the tuning half only and pre-registered at commit "
             f"`{v['preregistration_commit'][:7]}` (docs/results/feed_rule_preregistration.json). Its first held-out evaluation "
             "(docs/results/feed_rule_validation.json) ran on the pre-fix code. Here the same rule, unchanged and not tuned "
             f"again (signal in both reviewed sectors with periods within {100 * r['period_tol']:g}%, FAP below {r['fap_cut']:g} over "
             f"{r['fap_trials']:,} trials), is measured on this code (docs/results/feed_rule_validation_clipfix.json): the discovery "
             "config, each held-out star's same first two SPOC 2-minute sectors, the same two controls per sector, every pipeline run "
             f"and FAP trial made afresh. {n['targets']} targets, {n['star_sectors']} star-sectors.", "",
             f"| held-out | old rule (FAP < 0.01, 200 trials, one sector) | two-sector rule{col} |", f"|---|---|---{sep}|",
             f"| False signals per 100 targets, worse control (95% CI) | {f(o)} | {f(n)}{x(f(fn) if fn else '')} |",
             f"| Inverted control: false signals | {o['inverted']['new_signals']} ({o['inverted']['new_signals_per_1000']:.0f} per 1,000 star-sectors) | {n['inverted']['new_signals']} ({n['inverted']['new_signals_per_1000']:.0f} per 1,000)"
             + x(f"{fn['inverted']['new_signals']} ({fn['inverted']['new_signals_per_1000']:.0f} per 1,000)" if fn else "") + " |",
             f"| Scrambled control: false signals | {o['scrambled']['new_signals']} ({o['scrambled']['new_signals_per_1000']:.0f} per 1,000) | {n['scrambled']['new_signals']} ({n['scrambled']['new_signals_per_1000']:.0f} per 1,000)"
             + x(f"{fn['scrambled']['new_signals']} ({fn['scrambled']['new_signals_per_1000']:.0f} per 1,000)" if fn else "") + " |",
             f"| CP/KP admitted on their ephemeris (feed-level completeness) | {_ci(o['completeness'])} | {_ci(n['completeness'])}{x(_ci(fn['completeness']) if fn else '')} |",
             f"| FP TOIs kept out | {_ci(o['fp_rejected'])} | {_ci(n['fp_rejected'])}{x(_ci(fn['fp_rejected']) if fn else '')} |",
             f"| New (no-TOI) signals on the real curves, per 100 targets | {o['real_new_per_100_targets']:.1f} | {n['real_new_per_100_targets']:.1f}"
             + x(f"{fn['real_new_per_100_targets']:.1f}" if fn else "") + " |", ""]
    verdict = (f"On this code the rule lowers the noise clearly (the 95% intervals do not overlap): {_fold(o, n)}. "
               if v["fix_clearly_lowers_noise"] else "**On this code the rule is not shown to lower the noise: the 95% intervals overlap.** ")
    real = n["real_new_per_100_targets"]
    worse = n["expected_false_per_100_targets"]
    reliable = ("**It does not make the feed reliable.** Noise alone still gives about "
                f"{worse:.1f} false signals per 100 targets, against {real:.1f} new signals per 100 targets on the real light curves of "
                "TOI hosts, so what the feed admits is still dominated by false alarms." if worse >= real else
                f"Noise alone gives {worse:.1f} false signals per 100 targets, against {real:.1f} new signals per 100 targets on the real "
                "light curves of TOI hosts; most of those are still expected to be false alarms.")
    lines += [verdict + reliable + f" Completeness at the feed's level: {100 * o['completeness']['rate']:.0f}% under the old rule, "
              f"{100 * n['completeness']['rate']:.0f}% under this one. A feed admission is a lead for human or follow-up review, not a "
              "candidate of any confirmed status.", ""]
    if live:
        lines += [f"**The live feed re-run on this code** ({live['targets']} targets of the live catalogue, the same sectors as its "
                  f"previous run, {live['when'][:10]}; TOI table {live['toi_table']}): {live['new_signals']} new signals "
                  f"({live['new_entries']} entries) and {live['known_signals']} known-TOI signals ({live['known_entries']} entries) are "
                  "admitted."
                  + (f" The previous re-run, on the pre-fix code (docs/results/feed_rule_live_rerun.json), admitted "
                     f"{fr['first_live']['new_signals']} new and {fr['first_live']['known_signals']} known-TOI signals."
                     if fr.get("first_live") else ""), ""]
    return lines


def feed_rule_lines(fr: dict | None) -> list[str]:
    """The pre-registered two-sector feed rule, its one held-out evaluation, and the live feed re-run under it."""
    if not fr or not fr.get("validation"):
        return []
    if fr.get("edition") == "clipfix":
        return clipfix_feed_rule_lines(fr)
    v, pre, live = fr["validation"], fr.get("preregistration") or {}, fr.get("live")
    n, o = v["held_out"], v["held_out_old_rule"]
    r = v["rule"]
    f = lambda x: f"{x['expected_false_per_100_targets']:.1f} ({x['expected_false_ci_per_100_targets'][0]:.1f}–{x['expected_false_ci_per_100_targets'][1]:.1f})"
    lines = ["", f"## Update {v['evaluated_at'][:10]}: the two-sector feed rule, pre-registered and tested once", "",
             f"The fix proposed above was chosen on the tuning half only and pre-registered at commit `{v['preregistration_commit'][:7]}` "
             "(docs/results/feed_rule_preregistration.json) before its one held-out evaluation (docs/results/feed_rule_validation.json). "
             f"Rule: the signal must reach the feed rule in both reviewed sectors with periods within {100 * r['period_tol']:g}%, and its "
             f"FAP must be below {r['fap_cut']:g} over {r['fap_trials']:,} trials. No rule in the grid met the stated noise target "
             f"(at most 1 false signal per 100 targets on the tuning half), so the pre-stated fallback chose the lowest noise."
             if not pre.get("met_noise_target", True) else "", "",
             "Measured with the discovery config itself (subject-mode BLS, the Probes, the feed's weights file) on each held-out "
             f"star's first two SPOC 2-minute sectors and the same two controls per sector: {n['targets']} targets, {n['star_sectors']} star-sectors.", "",
             "| held-out | old rule (FAP < 0.01, 200 trials, one sector) | new rule |", "|---|---|---|",
             f"| False signals per 100 targets, worse control (95% CI) | {f(o)} | {f(n)} |",
             f"| Inverted control: false signals | {o['inverted']['new_signals']} ({o['inverted']['new_signals_per_1000']:.0f} per 1,000 star-sectors) | {n['inverted']['new_signals']} ({n['inverted']['new_signals_per_1000']:.0f} per 1,000) |",
             f"| Scrambled control: false signals | {o['scrambled']['new_signals']} ({o['scrambled']['new_signals_per_1000']:.0f} per 1,000) | {n['scrambled']['new_signals']} ({n['scrambled']['new_signals_per_1000']:.0f} per 1,000) |",
             f"| CP/KP admitted on their ephemeris (feed-level completeness) | {_ci(o['completeness'])} | {_ci(n['completeness'])} |",
             f"| FP TOIs kept out | {_ci(o['fp_rejected'])} | {_ci(n['fp_rejected'])} |",
             f"| New (no-TOI) signals on the real curves, per 100 targets | {o['real_new_per_100_targets']:.1f} | {n['real_new_per_100_targets']:.1f} |", ""]
    verdict = ("The rule lowers the noise clearly (the 95% intervals do not overlap): about fourfold. "
               if v["fix_clearly_lowers_noise"] else "**The rule is not shown to lower the noise: the 95% intervals overlap.** ")
    lines += [verdict + f"**It does not make the feed reliable.** Noise alone still gives about {n['expected_false_per_100_targets']:.0f} false "
              f"signals per 100 targets, far above the {n['real_new_per_100_targets']:.1f} new signals per 100 targets the real light "
              "curves of TOI hosts produce, so what the feed admits is still dominated by false alarms. Completeness at the feed's "
              f"level fell from {100 * o['completeness']['rate']:.0f}% to {100 * n['completeness']['rate']:.0f}%. A feed admission is a lead "
              "for human or follow-up review, not a candidate of any confirmed status.", ""]
    if live:
        lines += [f"**The live feed re-run under the new rule** ({live['targets']} targets of the live catalogue, their latest two sectors, "
                  f"{live['when'][:10]}; TOI table from {live['toi_table']}): {live['new_signals']} of the {live['old_new_signals']} earlier new "
                  f"signals survive, and {live['known_signals']} known-TOI signals are admitted. The earlier catalogue is kept as "
                  f"{live['old_catalogue']}.", ""]
    return lines


def _sentinel_lines(se: dict) -> list[str]:
    """The Sentinels' section: per reviewer, then agreement. With only the Claude pair it reads as before."""
    ids = list(se["personas"])
    multi = any(r not in CLAUDE_PAIR for r in ids)
    who = (f"{len(ids)} Sentinels ({', '.join(_who(rid, se) for rid in ids)})" if multi else
           "Both Sentinels (one Claude model, two personas, through the Claude Code CLI)")
    carry = se.get("carried")
    lines = ["## The Sentinels on a stated subsample", ""]
    if carry:
        lines += [f"The Sentinels were not asked again: no API key or signed-in CLI was available for this run. Their answers from the "
                  f"first run are carried over only for the stars whose every subject image and prompt are byte-identical on this code "
                  f"({len(carry['stars'])} of the {len(carry['stated_subsample'])} stars of the stated subsample); the other "
                  f"{len(carry['not_carried'])} stars' subjects changed with the fix, so they are left out of this table, not guessed."
                  + (f" Left out: TOI {', '.join(sorted(carry['not_carried']))}." if carry["not_carried"] else ""), ""]
    lines += [f"{who} reviewed every subject of {se['n_stars']} "
             "held-out stars drawn with a fixed seed (" + (f"{_class_counts(se)} here; half CP/KP, half FP as drawn" if carry else "half CP/KP, half FP") + "), on the real light curves only. Scored per star: did the "
             "persona mark a dip on the TOI's ephemeris as a potential planet.", "",
             "| persona | CP/KP dips marked | FP dips marked as a potential planet | failed calls |", "|---|---|---|---:|"]
    for rid, v in se["personas"].items():
        lines.append(f"| {rid} | {_pct(v['cp_kp_marked'])} | {_pct(v['fp_marked_as_planet'])} | {v['errors']} |")
    if se.get("models"):
        lines += ["", ("Model, as each provider reported it: " if multi else "Model, as the Claude Code CLI reported it: ") + "; ".join(f"{k}: {v} reviews" for k, v in se["models"].items())
                  + ". Reviews answered before SetuHQ stored the model id say \"not recorded\": the CLI ran its default "
                  "model then, and the cache key holds only \"default\"."]
    ag = se.get("agreement") or {}
    lines += ["", f"The two personas agree on {ag['agree']} of {ag['n']} stars (φ = {ag['phi']:.2f}). They share one model, so their "
              "errors are correlated and they count as one correlated voter, not two independent ones (ATLAS K4)." if ag.get("phi") is not None else "", ""]
    if multi:
        lines += ["Agreement for every pair, over the stars both answered (φ near 1: one voter twice; near 0: independent):", "",
                  "| pair | same model? | stars | agree | φ |", "|---|---|---:|---:|---:|"]
        for p in se.get("pairwise") or []:
            same = {True: "yes", False: "no", None: "not recorded"}[p["same_model"]]
            phi = "–" if p["phi"] is None else f"{p['phi']:.2f}"
            lines.append(f"| {p['a']} · {p['b']} | {same} | {p['n']} | {p['agree']} | {phi} |")
        ev, const = se.get("effective_voters"), se.get("constant_reviewers") or []
        k = se.get("effective_voters_k", len(ids) - len(const))
        left_out = (f" Left out of k: {', '.join(const)}, which gave the same answer on every star, so its φ is "
                    "undefined." if const else "")
        if ev is not None:
            lines += ["", f"Effective number of independent Sentinels, k / (1 + (k − 1)·mean φ): {ev:.1f} of k = {k}.{left_out}", ""]
        elif const:
            lines += ["", f"No effective number of independent Sentinels: fewer than two reviewers with a defined φ.{left_out}", ""]
        lines += ["Only Claude has been benchmarked on the full subsample before; a provider's rates here are its first measurement.", ""]
    return lines


def _class_counts(se: dict) -> str:
    v = next(iter(se["personas"].values()))
    return f"{v['cp_kp_marked']['n']} CP/KP and {v['fp_marked_as_planet']['n']} FP"


def _who(rid: str, se: dict) -> str:
    ident = (se.get("reviewers") or {}).get(rid) or {}
    return f"{rid} on {ident['provider']} / {ident['model']}" if ident.get("provider") else rid


def _clipfix_audit_lines(au: dict) -> list[str]:
    """The threshold audit of the re-run: every value changed since the freeze, grouped by why it changed."""
    lines = ["## Was the held-out half used to choose a threshold?", "",
             f"Of {au['values_checked']} threshold values in {', '.join(au['paths'])}, these differ between {au['frozen_after']} "
             f"(the last commit before the sample was frozen) and {au.get('compared_with') or 'HEAD'} (the code of this run). Each is "
             "listed with why it changed; none was chosen on this sample's held-out results.", ""]
    for g in au.get("explained") or []:
        files: dict[str, list[str]] = {}
        for k in g["keys"]:
            files.setdefault(k.split(":", 1)[0], []).append(k)
        named = [f"`{f}` ({len(ks)} values)" if len(ks) > 3 else ", ".join(f"`{k}`" for k in ks) for f, ks in files.items()]
        lines.append(f"* {g['why']} ({'; '.join(named)}).")
    if au.get("unexplained"):
        lines.append("* **Not explained: " + "; ".join(f"{k}: {v[0]} → {v[1]}" for k, v in au["unexplained"].items()) + ".**")
    lines += ["", "`preprocess.clean`'s new run-length rule is a keyword default, not a module constant, so the audit does not "
              "list it: it was set and tested on synthetic eclipses (commits ab84328 and c25d1cd)."
              + (" Changed values that decide nothing: " + "; ".join(f"{k} ({v[0]} → {v[1]})" for k, v in au["ignored_not_thresholds"].items()) + "."
                 if au.get("ignored_not_thresholds") else ""), ""]
    return lines


def to_markdown(data: dict) -> str:
    s = data["sample"]
    h = data["summary"]["held_out"]
    a = data["summary"]["all"]
    clipfix = data.get("edition") == "clipfix"
    lines = [
        "# Blind benchmark on real TESS Objects of Interest" + (": re-run on the fixed code" if clipfix else ""),
        "",
        *(["This is the pre-registered protocol run again on the current code, after the two fixes that change default results "
           "(`preprocess.clean` keeps dips deeper than 10× the point-to-point scatter; `vet.py`'s odd/even test no longer fails "
           "clean deep planets). The sample, seed, split, light curves, controls and scoring are unchanged and nothing was tuned; "
           "every star was run again from its light curve. The first run, made with the pre-fix code, is kept as the historical "
           "record in docs/results/benchmark_real_tois.md; the comparison is below.", ""] if clipfix else []),
        f"Measured on a stated benchmark; not discoveries. Sample: {s['source']}, fetched {s['fetched_at'][:10]}, seed {s['seed']}, "
        f"sha256 `{s['sha256'][:16]}…` ({s['counts']['positive']} CP/KP, {s['counts']['fp']} FP, {s['counts']['fa']} FA TOIs). "
        f"Rule: {s['rule']}.",
        "",
        f"Panel: {data['panel']}. Each star's first SPOC 2-minute sector; the same light curve flux-inverted and "
        "block-scrambled as false-alarm controls. Nothing was tuned on this sample, so both halves are reported; the "
        "held-out half (by a hash of the TIC) is the headline. The headline completeness is over searchable stars (those "
        "with a SPOC 2-minute light curve), because that is what the pipeline can search and what the references measure; "
        "completeness over all stars is given beside it.",
        "",
        *_headline(data),
        "## Held-out half",
        "",
        "| measure | result | reference (not an SetuHQ requirement) |",
        "|---|---|---|",
        f"| **Completeness, headline: CP/KP TOIs recovered on searchable stars** (a vetted dip on the ephemeris) | {_pct(h['completeness'])} | Kepler Robovetter DR25 > 85% for P < 100 d (Thompson et al. 2018); Planet Hunters TESS: 85% of TOIs > 4 R⊕, 51% at 3–4 R⊕ (Eisner et al. 2021); both searched only stars with data |",
        f"| Completeness over all CP/KP stars (a star with no 2-minute data counts as missed) | {_pct(h.get('completeness_all_stars'))} | |",
        f"| Not searchable: no SPOC 2-minute light curve | {_not_searchable(h)} | |",
        f"| FP TOIs whose dip the panel found | {_pct(h['fp_seen'])} | |",
        f"| … of those, rejected or flagged as binary-like | {_pct(h['fp_flagged_of_seen'])} | light-curve-only; no published reference found (ATLAS R) |",
        f"| CP/KP dips flagged as binary-like (the cost of the flags) | {_pct(h['pos_flagged'])} | |",
        f"| FA TOIs whose dip the panel found | {_pct(h['fa_seen'])} | |",
    ]
    for v in ("inverted", "scrambled"):
        c = h["controls"][v]
        kinds = c.get("kinds") or {}
        kind_txt = f"; {kinds['periodic']} on a ≥2-transit periodic signal, {kinds['single']} single" if kinds else ""
        lines.append(f"| False alarms on {v} light curves | {c['vetted_false_alarms']} vetted dips over {c['star_sectors']} star-sectors "
                     f"({c['per_1000_star_sectors']:.0f} per 1,000{kind_txt}); stars with any: {_pct(c['stars_with_any'])} | proposed target ≤ 1 per 1,000 star-sectors (ATLAS R) |"
                     if c["per_1000_star_sectors"] is not None else f"| False alarms on {v} light curves | — | |")
    lines += _clip_lines(data)
    lines += _feed_lines(data, h)
    lines += _against_first_lines(data)
    lines += ["", "### Completeness by planet radius and period (held-out)", "", "| bin | recovered |", "|---|---|"]
    for r in h["completeness_by_radius"]:
        lines.append(f"| {r['bin'][0]}–{r['bin'][1]} R⊕ | {_pct(r)} |")
    for r in h["completeness_by_period"]:
        lines.append(f"| {r['bin'][0]}–{r['bin'][1]} d | {_pct(r)} |")
    pa = h["period_aliases"]
    lines += ["", f"Periods of recovered CP/KP signals: {', '.join(f'{k}: {v}' for k, v in pa.items() if v)} (None: single-transit or other).",
              f"Median fit/TOI ratios on recovered CP/KP: depth {h['depth_ratio_median']:.2f}, duration {h['duration_ratio_median']:.2f}." if h["depth_ratio_median"] else "",
              "", "## Whole sample (both halves)", "",
              f"Completeness {_pct(a['completeness'])}; FP found {_pct(a['fp_seen'])}, of which flagged {_pct(a['fp_flagged_of_seen'])}; "
              f"inverted false alarms {a['controls']['inverted']['vetted_false_alarms']} and scrambled {a['controls']['scrambled']['vetted_false_alarms']} "
              f"over {a['controls']['inverted']['star_sectors']} star-sectors. Stars with no SPOC 2-minute data: {a['no_data']}.",
              ""]
    se = data.get("sentinels")
    if se:
        lines += _sentinel_lines(se)
    if data.get("loss"):
        lines += _loss_lines(data["loss"])
    cp = data.get("code_provenance")
    if cp:
        parts = [f"`{fp}` = the pipeline code of commit {cp['commit'].get(fp) or 'unknown'}"
                 + (" (the current code differs from it only in comments and docstrings)" if cp["head_same_behaviour"].get(fp) else "")
                 for fp in cp["fingerprints"]]
        lines += ["## Code version", "", "Every per-star result records a fingerprint of the pipeline code that produced it "
                  "(search, vetting, fit, reviewers): " + "; ".join(parts) + "."
                  + (" Every star, controls included, was run again from its light curve on this code (`rerun`); no stored "
                     "classification was reused." if clipfix else " Results from earlier code were re-vetted with "
                     "it from their stored classifications (`rescore`), controls included."), ""]
    au = data.get("threshold_audit")
    if au and clipfix:
        lines += _clipfix_audit_lines(au)
    elif au:
        commits = "; ".join(au.get("commits_since") or []) or "none"
        lines += ["## Was the held-out half used to choose a threshold?", "",
                  (f"No. All {au['values_checked']} threshold values in {', '.join(au['paths'])} (module constants, config keys, "
                   f"reviewer weights) are the same at {au.get('compared_with') or 'HEAD'}, the code that produced these numbers, as at "
                   f"{au['frozen_after']}, the last commit before the sample was frozen. "
                   "The Probe thresholds and weights come from synthetic injection tests; the vetting, V-shape, density and "
                   "FAP rules were set before any TOI light curve was downloaded. "
                   f"Commits since the freeze, none of which changed a threshold: {commits}."
                   + (" Changed values that decide nothing: " + "; ".join(f"{k} ({v[0]} → {v[1]})" for k, v in au["ignored_not_thresholds"].items()) + "."
                      if au.get("ignored_not_thresholds") else "")
                   if au["clean"] else "**Yes, possibly: these threshold values changed after the sample was frozen: "
                   + "; ".join(f"{k}: {v[0]} → {v[1]}" for k, v in au["changed"].items()) + ".**"), ""]
    lines += feed_rule_lines(data.get("feed_rule"))
    lines += ["Recovered means the panel's consensus dip passed vetting and lies on the TOI's published ephemeris (`match_toi`). "
              "Flagged means vetting rejected the on-ephemeris dip, or marked it odd/even, secondary eclipse, V shape or density "
              "mismatch. Wilson 95% intervals. TFOPWG dispositions are the reference; they are not ground truth for every TOI.", ""]
    return "\n".join(lines)

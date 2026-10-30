# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Evidence from SetuHQ's own stored outputs, where they exist: candidates, ephemeris, TESS noise per timescale.

Read only, from the data root: every run directory under ``runs/`` with a ``candidates.json`` (its stored
subjects give the prepared TESS light curve) and the discovery catalogue (``docs/discoveries/catalog.json``).
Everything SetuHQ reports is a candidate: a dip found and vetted by Sentinels (AI models) and Probes
(deterministic detectors), never a confirmed or validated planet.

Noise per timescale ("CDPP-like"): the stored light curve is already cleaned, detrended and binned by the
pipeline. Points inside any stored candidate's dip are masked, the rest is cut into consecutive bins of 1, 3 and
6 hours (a bin needs half its expected points), and the robust scatter (1.4826 MAD) of the bin means is reported
in ppm. Detrending suppresses variability on timescales near the detrending window, so the 6-hour value is
optimistic for active stars. It is TESS-band noise for context, not a CHEOPS prediction.

Hooks for the stellar work (optional): if ``setuhq.flares``, ``setuhq.pulsations`` or ``setuhq.cheops`` is
installed and exposes ``proposal_evidence(target, *, tic, root) -> dict``, its answer is included. A missing
module, a missing hook or a failing hook is recorded and never stops the pack.
"""

from __future__ import annotations

import importlib
import json
import math
from pathlib import Path

HOOK_MODULES = (("flares", "setuhq.flares"), ("pulsations", "setuhq.pulsations"), ("cheops_ingest", "setuhq.cheops"))
TIMESCALES_H = (1.0, 3.0, 6.0)
CANDIDATE_LABEL = ("SetuHQ results are candidates, not confirmations: dips found in public TESS data and vetted by "
                   "Sentinels (AI models) and Probes (deterministic detectors). A match to a TOI means the signal "
                   "was already known; it does not mean SetuHQ confirmed it.")


def _robust_std(x: list[float]) -> float | None:
    if len(x) < 3:
        return None
    s = sorted(x)
    med = s[len(s) // 2] if len(s) % 2 else 0.5 * (s[len(s) // 2 - 1] + s[len(s) // 2])
    dev = sorted(abs(v - med) for v in x)
    mad = dev[len(dev) // 2] if len(dev) % 2 else 0.5 * (dev[len(dev) // 2 - 1] + dev[len(dev) // 2])
    return 1.4826 * mad


def noise_per_timescale(time: list[float], flux: list[float], masks: list[tuple[float, float]] = (),
                        hours=TIMESCALES_H) -> dict:
    """Robust scatter (ppm) of consecutive bin means at each timescale, with in-dip points masked."""
    pts = sorted((t, f) for t, f in zip(time, flux)
                 if f is not None and math.isfinite(f) and not any(a <= t <= b for a, b in masks))
    if len(pts) < 20:
        return {f"{h:g}h": None for h in hours} | {"n_points": len(pts)}
    dts = sorted(pts[i + 1][0] - pts[i][0] for i in range(len(pts) - 1))
    cadence = dts[len(dts) // 2]
    level = sorted(f for _, f in pts)[len(pts) // 2]
    out = {"n_points": len(pts), "cadence_minutes": cadence * 1440.0}
    for h in hours:
        width = h / 24.0
        need = max(2, int(0.5 * width / cadence))
        bins: dict[int, list[float]] = {}
        t_start = pts[0][0]
        for t, f in pts:
            bins.setdefault(int((t - t_start) // width), []).append(f / level - 1.0)
        means = [sum(v) / len(v) for v in bins.values() if len(v) >= need]
        s = _robust_std(means)
        out[f"{h:g}h"] = None if s is None else s * 1e6
        out[f"{h:g}h_bins"] = len(means)
    return out


def _cand_masks(cands: list[dict], subject_id: str) -> list[tuple[float, float]]:
    out = []
    for c in cands:
        if c.get("subject_id") != subject_id:
            continue
        p, t0 = c.get("period_days"), c.get("bls_t0") or c.get("t_center")
        dur = (c.get("duration_hours") or 3.0) / 24.0
        if p and t0:
            for e in c.get("epochs") or []:
                out.append((e["t_mid"] - dur, e["t_mid"] + dur))
        if c.get("t_start") is not None and c.get("t_end") is not None:
            pad = 0.5 * (c["t_end"] - c["t_start"])
            out.append((c["t_start"] - pad, c["t_end"] + pad))
    return out


def stored_evidence(root: Path, *, tic: int | None, names: list[str]) -> dict:
    """Candidates, ephemeris and light-curve noise for the target from stored outputs under ``root``."""
    wanted = {f"tic {tic}"} if tic else set()
    wanted |= {" ".join(n.lower().split()) for n in names if n}
    runs, sources = [], []
    for cands_p in sorted((root / "runs").glob("*/candidates.json")):
        try:
            cands = json.loads(cands_p.read_text())
        except (OSError, ValueError):
            continue
        mine = [c for c in cands if " ".join(str(c.get("target", "")).lower().split()) in wanted]
        if not mine:
            continue
        run = cands_p.parent
        sources.append(str(cands_p.relative_to(root)))
        rows = []
        for c in mine:
            fit = c.get("fit") or {}
            rows.append({k: c.get(k) for k in ("candidate_id", "passed", "flags", "period_days", "depth_ppm", "snr",
                                                "duration_hours", "t_center", "time_unit", "fap", "fap_label",
                                                "n_reviewers", "score")}
                        | {"fit": {k: fit.get(k) for k in ("t0", "t0_err", "period_days", "period_err", "depth_ppm",
                                                           "depth_err_ppm", "t14_hours", "t14_err_hours", "b")} if fit else None})
        noise = []
        for sid in sorted({c["subject_id"] for c in mine if c.get("subject_id")}):
            sp = run / "subjects" / f"{sid}.json"
            if sp.exists():
                s = json.loads(sp.read_text())
                noise.append({"subject": sid, "time_unit": s.get("time_unit"), "span": [s.get("start"), s.get("end")]}
                             | noise_per_timescale(s["time"], s["flux"], _cand_masks(cands, sid)))
                sources.append(str(sp.relative_to(root)))
        manifest = {}
        if (run / "manifest.json").exists():
            m = json.loads((run / "manifest.json").read_text())
            manifest = {"inputs": m.get("inputs"), "created_at": m.get("created_at"),
                        "reviewers": [{k: r.get(k) for k in ("id", "kind", "provider", "model") if k in r}
                                      for r in m.get("reviewers", [])]}
        runs.append({"run": str(run.relative_to(root)), "candidates": rows, "noise": noise, "manifest": manifest})
    catalogue = []
    cat_p = root / "docs" / "discoveries" / "catalog.json"
    if tic and cat_p.exists():
        cat = json.loads(cat_p.read_text())
        catalogue = [c for c in cat.get("candidates", []) if c.get("tic") == tic]
        if catalogue:
            sources.append(str(cat_p.relative_to(root)))
    return {"found": bool(runs or catalogue), "runs": runs, "catalogue": catalogue, "sources": sources,
            "label": CANDIDATE_LABEL}


def best_ephemeris(ev: dict) -> dict | None:
    """The stored ephemeris to propagate: a passed candidate's transit fit (with errors) first, else a catalogue
    entry (mid-time and period without errors)."""
    for run in ev.get("runs", []):
        for c in run["candidates"]:
            f = c.get("fit") or {}
            if c.get("passed") and f.get("t0") and f.get("period_days"):
                return {"t0": f["t0"], "t0_err": f.get("t0_err"), "period": f["period_days"],
                        "period_err": f.get("period_err"), "duration_hours": f.get("t14_hours"),
                        "depth_ppm": f.get("depth_ppm"),
                        "source": f"SetuHQ transit fit, {run['run']} {c['candidate_id']} (candidate, TESS band)"}
    for c in ev.get("catalogue", []):
        if c.get("t_center") and c.get("period_days"):
            return {"t0": c["t_center"], "t0_err": None, "period": c["period_days"], "period_err": None,
                    "duration_hours": c.get("duration_hours"), "depth_ppm": c.get("depth_ppm"),
                    "source": f"SetuHQ discovery catalogue {c.get('candidate_id')} (candidate, TESS band; no errors stored)"}
    return None


def stellar_hooks(target: str, *, tic: int | None, root: Path) -> dict:
    """Optional evidence from the stellar modules (flares, pulsations, CHEOPS ingest), when installed."""
    out = {}
    for key, mod_name in HOOK_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            out[key] = {"status": "not installed", "module": mod_name}
            continue
        hook = getattr(mod, "proposal_evidence", None)
        if hook is None:
            out[key] = {"status": "installed, no proposal_evidence hook", "module": mod_name}
            continue
        try:
            out[key] = {"status": "ok", "module": mod_name, "evidence": hook(target, tic=tic, root=root)}
        except Exception as exc:  # noqa: BLE001 (a hook never stops the pack)
            out[key] = {"status": f"hook failed: {type(exc).__name__}: {exc}", "module": mod_name}
    return out

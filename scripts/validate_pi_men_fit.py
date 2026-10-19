#!/usr/bin/env python3
"""pi Men c: the limb-darkened fit of the stored run against Huang et al. 2018 (and the archive's default row).

Reads ``runs/tess-pi-men-s1`` (candidates.json, after ``exoplan rebuild``; subjects/*.json; stellar.json) and
the reference rows in ``docs/results/pi_men_reference.json`` (NASA Exoplanet Archive ``ps`` table; refreshed
with ``--refresh`` when the archive answers). Writes ``docs/results/pi_men_validation.md`` and the JSON beside it.

Fits reported: the pipeline's own (one joint fit per 13-day subject, as written in candidates.json), and one
joint fit of every recovered epoch across both subjects, done here with the same code, twice: free (depth, T14
and k are robust; b, a/R★ and ρ★ are degenerate with five TESS transits) and with a Gaussian prior on ρ★ from
the TIC density and its error (b, a/R★ and T23/T14 then constrained). The period is free in both. The old box
measure (the mean flux over the panel's marked window) is shown beside them for comparison.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from exoplan.transitfit import b_text, fit_transit, ld_coeffs, rho_catalogue, t23  # noqa: E402

REF = Path("docs/results/pi_men_reference.json")
TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
COLS = "pl_name,pl_refname,default_flag,pl_orbper,pl_tranmid,pl_trandur,pl_trandep,pl_ratror,pl_imppar,pl_ratdor,st_teff,st_logg,st_rad,st_mass,st_dens"


def refresh_reference() -> dict:
    q = f"select {COLS} from ps where pl_name='pi Men c'"
    with urllib.request.urlopen(TAP + "?" + urllib.parse.urlencode({"query": q, "format": "csv"}), timeout=60) as resp:  # noqa: S310
        rows = list(csv.DictReader(io.StringIO(resp.read().decode())))
    num = lambda v: float(v) if v not in ("", None) else None
    out = []
    for r in rows:
        ref = r["pl_refname"].split("refstr=")[1].split(" ")[0] if "refstr=" in r["pl_refname"] else r["pl_refname"]
        out.append({"ref": ref, "default": r["default_flag"] == "1", **{k: num(r[k]) for k in COLS.split(",")[3:]}})
    data = {"source": "NASA Exoplanet Archive, table ps, pl_name = 'pi Men c'", "url": TAP,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": "pl_trandep is in percent (×10⁴ for ppm); pl_trandur in hours.", "rows": out}
    REF.write_text(json.dumps(data, indent=1) + "\n")
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", default="runs/tess-pi-men-s1")
    ap.add_argument("--refresh", action="store_true", help="fetch the archive rows again")
    ap.add_argument("--out", default="docs/results/pi_men_validation.md")
    args = ap.parse_args(argv)
    ref = refresh_reference() if args.refresh or not REF.exists() else json.loads(REF.read_text())
    huang = next(r for r in ref["rows"] if r["ref"].startswith("HUANG"))
    default = next(r for r in ref["rows"] if r["default"])
    run = Path(args.run)
    cands = [c for c in json.loads((run / "candidates.json").read_text()) if c["passed"] and c.get("fit")]
    period_ref = huang["pl_orbper"]
    tmid = huang["pl_tranmid"] - 2457000.0
    on = [c for c in cands if abs(((c["t_center"] - tmid + 0.5 * period_ref) % period_ref) - 0.5 * period_ref) < 0.1]
    star = next(iter(json.loads((run / "stellar.json").read_text()).values())) if (run / "stellar.json").exists() else {}
    # Pipeline fits: one per subject (shared by that subject's epochs).
    per_subject = {}
    for c in on:
        per_subject.setdefault(c["subject_id"], c["fit"])
    # One joint fit of every recovered epoch over both subjects, with the pipeline's mean BLS period.
    t, f, e = [], [], []
    for sid in per_subject:
        s = json.loads((run / "subjects" / f"{sid}.json").read_text())
        t.append(np.asarray(s["time"])), f.append(np.asarray(s["flux"])), e.append(np.asarray(s["flux_err"]))
    t, f, e = (np.concatenate(a) for a in (t, f, e))
    periods = [c["period_days"] for c in on if c.get("period_days")]
    period = float(np.mean(periods))
    epochs = sorted(c["fit"]["t0"] for c in on)
    # One period across both subjects: refine it from the first and last fitted mid-times.
    n = round((epochs[-1] - epochs[0]) / period)
    period = (epochs[-1] - epochs[0]) / n if n else period
    pred = [epochs[0] + k * period for k in range(n + 1)]
    u1, u2 = ld_coeffs(star.get("teff"), star.get("logg"))
    common = dict(t0=epochs[0], duration=huang["pl_trandur"] / 24, depth=2.5e-4, period=period, u1=u1, u2=u2, epochs=pred,
                  stellar_density=star.get("rho"))
    joint = fit_transit(t, f, e, **common).as_dict()
    prior = (fit_transit(t, f, e, **common, rho_prior=(star["rho"], star["rho_err"])).as_dict()
             if star.get("rho") and star.get("rho_err") else None)
    box_depth = float(np.mean([c["depth_ppm"] for c in on]))
    box_dur = float(np.mean([c["duration_hours"] for c in on]))
    rho_huang = rho_catalogue(huang["st_mass"], huang["st_rad"]) if huang.get("st_mass") else None
    ratios = lambda r: {"depth": joint["depth_ppm"] / (r["pl_trandep"] * 1e4) if r.get("pl_trandep") else None,
                        "duration": joint["t14_hours"] / r["pl_trandur"] if r.get("pl_trandur") else None,
                        "k": joint["k"] / r["pl_ratror"] if r.get("pl_ratror") else None,
                        "box_depth": box_depth / (r["pl_trandep"] * 1e4) if r.get("pl_trandep") else None,
                        "box_duration": box_dur / r["pl_trandur"] if r.get("pl_trandur") else None}
    out = {"run": str(run), "reference": ref["source"], "reference_fetched_at": ref["fetched_at"],
           "huang_2018": huang, "archive_default": default, "star": star, "ld": [u1, u2],
           "epochs_recovered": len(on), "epochs_predicted": len(pred), "joint_fit": joint, "joint_fit_density_prior": prior,
           "per_subject_fits": per_subject, "box": {"depth_ppm": box_depth, "duration_hours": box_dur},
           "ratios_vs_huang_2018": ratios(huang), "ratios_vs_archive_default": ratios(default),
           "rho_huang_mass_radius": rho_huang}
    Path(args.out).with_suffix(".json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    j = joint
    fmt = lambda x, d=2: "—" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{d}f}"
    rh, rd = ratios(huang), ratios(default)

    def pv(key, d=2):
        if not prior or prior.get(key) is None:
            return "—"
        err = {"k": "k_err", "t14_hours": "t14_err_hours", "depth_ppm": "depth_err_ppm", "rho_star": "rho_star_err"}.get(key)
        if key == "a_rs" and prior.get("a_rs_range"):
            lo, hi = prior["a_rs_range"]
            return f"{prior['a_rs']:.{d}f} (1σ {lo:.{d}f}–{hi:.{d}f})"
        return f"{prior[key]:.{d}f}" + (f" ± {prior[err]:.{d}f}" if err and prior.get(err) is not None else "")
    ars_free = (f"{fmt(j['a_rs'])} at the best-fit b, unconstrained (1σ {fmt(j['a_rs_range'][0])}–{fmt(j['a_rs_range'][1])})"
                if j.get("a_rs_range") else fmt(j["a_rs"]))
    t23_huang = (t23(huang["pl_trandur"] / 24, huang["pl_imppar"], huang["pl_ratror"], huang["pl_orbper"]) / (huang["pl_trandur"] / 24)
                 if huang.get("pl_imppar") is not None and huang.get("pl_ratror") else None)
    lines = [
        "# pi Men c: the limb-darkened fit against Huang et al. 2018",
        "",
        f"Run `{run}` (TESS SPOC sector 1, 10-minute bins), rebuilt from its stored classifications with the limb-darkened",
        f"fit (`src/exoplan/transitfit.py`). {len(on)} of {len(pred)} predicted epochs are recovered by the panel. Limb darkening:",
        f"Claret 2017 TESS quadratic u₁ = {u1:.3f}, u₂ = {u2:.3f} for the TIC's Teff {fmt(star.get('teff'), 0)} K and log g {fmt(star.get('logg'))}.",
        f"Reference: {ref['source']}, fetched {ref['fetched_at'][:10]} (`{REF}`).",
        "",
        "## Joint fit of every recovered epoch",
        "",
        "Two lines. **Free**: depth, T14 and k are robust; b, a/R★ and ρ★ are degenerate with five TESS transits, so b",
        "is an upper limit when its 1σ set reaches 0 and ρ★ is a range. **With the TIC density prior** (a Gaussian on ρ★,",
        f"{fmt(star.get('rho'), 3)} ± {fmt(star.get('rho_err'), 3)} g/cm³): b, a/R★ and T23/T14, to compare with Huang's b = {fmt(huang['pl_imppar'])}.",
        "Like-for-like comparisons lead: k and T14.",
        "",
        "| quantity | free | with the TIC density prior | Huang et al. 2018 | ratio (free / Huang) | archive default (" + default["ref"].replace("_", " ").title() + ") | ratio |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| Rp/R★ (k) | {fmt(j['k'], 4)} ± {fmt(j['k_err'], 4)} | {pv('k', 4)} | {fmt(huang['pl_ratror'], 5)} | **{fmt(rh['k'])}** | {fmt(default.get('pl_ratror'), 5)} | {fmt(rd['k'])} |",
        f"| T14 (h) | {fmt(j['t14_hours'])} ± {fmt(j['t14_err_hours'])} | {pv('t14_hours')} | {fmt(huang['pl_trandur'], 3)} | **{fmt(rh['duration'])}** | {fmt(default['pl_trandur'], 3)} | {fmt(rd['duration'])} |",
        f"| depth (ppm)¹ | {fmt(j['depth_ppm'], 0)} ± {fmt(j['depth_err_ppm'], 0)} | {pv('depth_ppm', 0)} | {fmt(huang['pl_trandep'] * 1e4, 0)} | {fmt(rh['depth'])} | {fmt(default['pl_trandep'] * 1e4, 0)} | {fmt(rd['depth'])} |",
        f"| P (d), fitted near the BLS period | {fmt(j['period_days'], 4)} ± {fmt(j['period_err'], 4)} | {fmt(prior['period_days'], 4) if prior else '—'} | {fmt(huang['pl_orbper'], 5)} | | | |",
        f"| b | {b_text(j)} | {b_text(prior) if prior else '—'} | {fmt(huang['pl_imppar'])} | | {fmt(default.get('pl_imppar'))} | |",
        f"| a/R★ | {ars_free} | {pv('a_rs')} | {fmt(huang['pl_ratdor'])} | | | |",
        f"| T23/T14 | {'unconstrained' if j['b_upper_limit'] else fmt(j['t23_over_t14'])} | {fmt(prior['t23_over_t14']) if prior else '—'} | {fmt(t23_huang)} (from Huang's b, k, a/R★) | | | |",
        f"| ρ★ transit (g/cm³) | 1σ range {fmt(j['rho_range'][0], 3)}–{fmt(j['rho_range'][1], 3)} | {pv('rho_star', 3)} (prior-dominated; not a test) | {fmt(rho_huang, 3)} from M★, R★ | | | |",
        "",
        "¹ Depth definitions differ: exoplan's is the limb-darkened model's depth at mid-transit; the archive's `pl_trandep` "
        "is the published transit depth as each paper defines it. Compare k and T14 first.",
        "",
        "Errors are conservative: the covariance at the best fit (scaled by √χ²ᵣ when above 1) added in quadrature to the "
        "spread along the impact-parameter profile (Δχ² ≤ 1), which overlap.",
        "",
        f"The box measure used before (the mean flux over the panel's marked window): depth {box_depth:.0f} ppm, duration "
        f"{box_dur:.2f} h, ratios **{fmt(rh['box_depth'])}** and **{fmt(rh['box_duration'])}** against Huang 2018 "
        f"({fmt(rd['box_depth'])} and {fmt(rd['box_duration'])} against the archive default row the README used to cite).",
        "",
        f"ρ★ check (free fit): the transit density against the TIC's {fmt(star.get('rho'), 3)} g/cm³ "
        f"({'flagged' if j['rho_flag'] else 'consistent within the illustrative 0.3–3 band at 3σ'}). V-shape test: "
        f"{'V-shaped' if j['v_shape'] else 'U-shaped (not grazing)' if not j['grazing'] else 'grazing best fit, but a full transit fits as well'}.",
        "",
        "## The pipeline's own fits (one joint fit per 13-day subject)",
        "",
        "| subject | epochs | P (d) | depth (ppm) | T14 (h) | b | ρ★ (g/cm³), 1σ range |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for sid, fit in per_subject.items():
        rr = fit.get("rho_range") or [None, None]
        lines.append(f"| {sid} | {fit['n_epochs']} | {fmt(fit.get('period_days'), 4)} | {fmt(fit['depth_ppm'], 0)} ± {fmt(fit['depth_err_ppm'], 0)} | "
                     f"{fmt(fit['t14_hours'])} ± {fmt(fit['t14_err_hours'])} | {b_text(fit) if 'b_upper_limit' in fit else fmt(fit['b'])} | "
                     f"{fmt(rr[0], 3)}–{fmt(rr[1], 3)} |")
    lines += ["", "Depth is the model's mid-transit depth; errors are conservative, as above. Each subject's fit frees the period "
              "near that subject's BLS period.", "",
              "## Ephemeris recovery (recorded earlier)",
              "",
              "Recorded by `scripts/validate_known_planets.py` at commit 0f6dbdc from a live query of the archive's default row",
              "then. Its timing columns stand; its depth and duration ratios came from the box measure and are superseded by",
              "the fit above.",
              "",
              "| planet | P (d) | predicted epochs in span | recovered | mean timing offset (min) | depth ratio (box) | duration ratio (box) |",
              "|---|---:|---:|---:|---:|---:|---:|",
              "| pi Men c | 6.26784 | 5 | 5 | -8.0 | 0.91 | 0.62 |", ""]
    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

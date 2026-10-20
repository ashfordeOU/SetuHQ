#!/usr/bin/env python3
"""pi Men (TIC 261136679), TESS sector 1: the S2 extended and pixel-level vetting and the S3 reduced FPP, on real SPOC data.

Inputs (downloaded into the gitignored ``cache/tpf`` by :func:`exoplan.pixel.fetch_spoc_product`, through MAST or,
when MAST's search service fails, the public STScI bucket that MAST's download links redirect to):

* the SPOC 2-minute light curve ``*_lc.fits`` (PDCSAP flux, CROWDSAP and FLFRCSAP);
* the SPOC target pixel file ``*_tp.fits``;
* SPOC's own DV report XML (``*_dvr.xml``), whose difference-image centroid offsets are shown for comparison.

Steps: the light curve is prepared as in the stored run's config (clean, detrend, 10-minute bins), the sector is
searched with BLS, and every epoch is fitted jointly with the limb-darkened model (period free near the BLS period,
TIC limb darkening from ``runs/tess-pi-men-s1/stellar.json``). The fitted ephemeris, T14 and depth drive the DV-style
light-curve tests (:func:`exoplan.dvtests.extended_vet`) and the pixel tests (:func:`exoplan.pixel.pixel_vet`).
Nearby stars come from the TIC, or Gaia DR3 when MAST fails, cached in ``cache/neighbours``.

Writes ``docs/results/pi_men_s2_vetting.json`` and ``.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from exoplan.config import load_config  # noqa: E402
from exoplan.dvtests import extended_vet  # noqa: E402
from exoplan.loaders import load_spoc_file  # noqa: E402
from exoplan.dvtests import assess_secondary, secondary_search  # noqa: E402
from exoplan.pipeline import (prepare_lightcurves, secondary_variants, vetting_lightcurve,  # noqa: E402
                              vetting_lightcurve_two_pass, vetting_window)
from exoplan.validate import scan_whiteness  # noqa: E402
from exoplan.pixel import (fetch_neighbours, fetch_spoc_product, load_tpf, order_target_first,  # noqa: E402
                           parse_dv_xml, pixel_vet)
from exoplan.search import bls_search, stitch  # noqa: E402
from exoplan.transitfit import fit_transit, ld_coeffs  # noqa: E402
from exoplan.validate import reduced_fpp  # noqa: E402

TIC, SECTOR = 261136679, 1


def _clean(obj):
    """JSON-safe: numpy scalars and arrays to Python, non-finite floats to strings."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if isinstance(obj, (np.floating, float)):
        x = float(obj)
        return x if math.isfinite(x) else str(x)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def run(cache: Path, run_dir: Path, config_path: Path) -> dict:
    lc_path = fetch_spoc_product(TIC, SECTOR, "lc.fits", cache)
    tpf_path = fetch_spoc_product(TIC, SECTOR, "tp.fits", cache)
    try:
        dv_path = fetch_spoc_product(TIC, SECTOR, "dvr.xml", cache)
        dv = parse_dv_xml(dv_path)
    except Exception as exc:  # noqa: BLE001 (the comparison is optional)
        dv_path, dv = None, {"error": f"{type(exc).__name__}: {exc}"}

    config = load_config(config_path)
    lc = load_spoc_file(lc_path, target=f"TIC {TIC}")
    prepared = prepare_lightcurves([lc], config)
    sector = stitch(prepared)
    signal = bls_search(sector, min_period=config.min_period)
    star = json.loads((run_dir / "stellar.json").read_text()).get(f"TIC {TIC}", {})
    u1, u2 = ld_coeffs(star.get("teff"), star.get("logg"))
    epochs = [signal.t0 + k * signal.period for k in range(-10, 10)
              if sector.time.min() <= signal.t0 + k * signal.period <= sector.time.max()
              and np.sum(np.abs(sector.time - (signal.t0 + k * signal.period)) <= 0.5 * signal.duration) >= 2]
    fit = fit_transit(sector.time, sector.flux, sector.flux_err, t0=epochs[len(epochs) // 2], duration=signal.duration,
                      depth=max(signal.depth, 2e-5), period=signal.period, u1=u1, u2=u2, epochs=epochs,
                      stellar_density=star.get("rho"))
    f = fit.as_dict()
    duration = f["t14_hours"] / 24.0
    # the DV-style tests read the light curve re-detrended with the fitted transits masked, as the pipeline does
    eph = dict(period=f["period_days"], t0=f["t0"], duration=duration)
    masked, phases = vetting_lightcurve_two_pass([lc], config, **eph)
    flags_lc, lc_tests = extended_vet(masked.time, masked.flux, masked.flux_err, **eph, fit=f,
                                      provenance=lc.provenance)
    lc_tests.update(transit_masked_detrend=True, masked_phases=list(phases),
                    detrend_window_days=vetting_window(config, duration))
    variants = secondary_variants([lc], config, **eph, extra_phases=phases)
    # the reviewer's wider grid: absolute windows 0.75-2 d x masks 1.0/1.5/2.0 T14 (for the README's stability statement)
    grid = []
    base_window = vetting_window(config, duration)
    for win in (0.75, 1.0, 1.25, 1.5, 2.0):
        for mask in (1.0, 1.5, 2.0):
            g_lc = vetting_lightcurve([lc], config, **eph, extra_phases=phases, window_scale=win / base_window,
                                      mask_t14=mask)
            sec = assess_secondary(secondary_search(g_lc.time, g_lc.flux, **eph))
            gate = scan_whiteness(sec)
            one = reduced_fpp(depth=f["depth_ppm"] * 1e-6, dv=dict(lc_tests, secondary=sec), fit=f).as_dict()
            grid.append({"window_days": win, "mask_t14": mask, "white": bool(gate["white"]),
                         "max_brightening_snr": sec["max_brightening_snr"], "snr": sec["snr"],
                         "robust_spread": sec["scan_robust_sigma"], "fpp": one["fpp"],
                         "fpp_range_noise_models": (one["evidence"].get("fpp_sensitivity") or {}).get("range")})
    lc_tests["detrending_grid"] = grid
    # the secondary flag itself across nearby run settings (detrend window x bin size), each through the full path
    # (two-pass detrend, the scan, assess_secondary), reported like the FPP: as a count, not one setting's verdict
    flag_grid = []
    for win in (1.0, 2.0):
        for binm in (2.0, 6.0, 10.0, 15.0, 20.0, 30.0):
            cfg = replace(config, detrend_window_days=win, bin_minutes=binm)
            first = vetting_lightcurve([lc], cfg, **eph)
            s1 = assess_secondary(secondary_search(first.time, first.flux, **eph), secondary_sigma=cfg.secondary_sigma)
            g_lc, g_phases = vetting_lightcurve_two_pass([lc], cfg, **eph)
            g_flags, g_tests = extended_vet(g_lc.time, g_lc.flux, g_lc.flux_err, **eph, fit=f)
            s = g_tests["secondary"]
            flag_grid.append({"window_days": win, "effective_window_days": vetting_window(cfg, duration),
                              "bin_minutes": binm, "first_pass_snr": s1["snr"],
                              "first_pass_significant": s1["significant"], "masked_phases": list(g_phases),
                              "snr": s["snr"], "threshold_sigma": s["threshold_sigma"],
                              "max_brightening_snr": s["max_brightening_snr"], "periodic": s["periodic"],
                              "max_epoch_share": s["max_epoch_share"], "phase": s["phase"],
                              "flagged": "secondary_any_phase" in g_flags})
    k, n = sum(g["flagged"] for g in flag_grid), len(flag_grid)
    lc_tests["secondary_flag_grid"] = flag_grid
    lc_tests["secondary_flag_stability"] = {
        "flagged": k, "n_settings": n,
        "verdict": ("no secondary flag on any setting" if k == 0 else "flagged on every setting" if k == n else
                    f"secondary at threshold; flag setting-dependent ({k} of {n} settings flag it)")}

    tpf = load_tpf(tpf_path)
    h = tpf.header
    neighbours = fetch_neighbours(h["ra"], h["dec"], radius_arcsec=150.0, cache_dir=cache.parent / "neighbours",
                                  epoch_years_since_2000=h.get("years_since_2000"), key=f"tic{TIC}")
    stars = order_target_first(neighbours.get("stars", []), h["ra_epoch"] or h["ra"], h["dec_epoch"] or h["dec"])
    pixel = pixel_vet(tpf, period=f["period_days"], t0=f["t0"], duration=duration, depth=f["depth_ppm"] * 1e-6,
                      stars=stars or None)
    validation = reduced_fpp(depth=f["depth_ppm"] * 1e-6, dv=lc_tests, fit=f, pixel=pixel, variants=variants).as_dict()
    return {
        "target": f"TIC {TIC} (pi Men)", "sector": SECTOR, "validation": validation,
        "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {"lightcurve": lc.provenance, "tpf": tpf.provenance,
                   "dv_report": dv_path.name if dv_path else None},
        "bls": {"period": signal.period, "t0": signal.t0, "duration_days": signal.duration, "snr": signal.snr},
        "fit": {k: f[k] for k in ("t0", "t0_err", "period_days", "period_err", "t14_hours", "t14_err_hours",
                                  "depth_ppm", "depth_err_ppm", "k", "b", "a_rs", "n_epochs")},
        "lightcurve_flags": list(flags_lc), "lightcurve_tests": lc_tests,
        "pixel_flags": pixel["flags"], "pixel": pixel, "neighbour_query": {k: neighbours.get(k) for k in ("source", "errors", "radius_arcsec")},
        "spoc_dv": dv,
    }


def _gate_line(v: dict) -> str:
    st = (v.get("evidence") or {}).get("fpp_stability")
    if st:
        lo, hi = st["range"]
        return (f"Stability: the FPP was computed on {st['n_settings']} detrending settings (the default and windows "
                f"×0.75 and ×1.5 with masks of 1.0 and 2.0 T14) under two noise models: range {_fmt(lo, 4)}–{_fmt(hi, 4)}, "
                f"median {_fmt(st['median_robust'], 4)} at the robust spread; {st['white_settings']} of {st['n_settings']} "
                f"settings pass the white-noise gate.")
    g = (v.get("evidence") or {}).get("scan_whiteness")
    if not g:
        return "White-noise gate: not applicable (no all-phase scan)."
    sens = (v.get("evidence") or {}).get("fpp_sensitivity") or {}
    return (f"White-noise gate on the secondary scan: robust spread {g['robust_spread']:.2f} (0.7–1.3), std/robust "
            f"{g['std_over_robust']:.2f} (≤ 1.3), largest |excursion| {g['max_excursion_over_robust']:.2f} robust spreads "
            f"(white 99.9%: {g['white_q_abs_999']:.2f} for {g['positions']} positions): "
            f"{'passed' if g['white'] else 'failed'}. FPP over noise models (evidence only): "
            + ", ".join(f"{k} {_fmt(x, 3)}" for k, x in (sens.get("by_noise_model") or {}).items()) + ".")


def _grid_lines(r: dict) -> str:
    grid = r["lightcurve_tests"].get("detrending_grid") or []
    if not grid:
        return ""
    white = sum(g["white"] for g in grid)
    fpps = [g["fpp"] for g in grid if g["fpp"] is not None]
    ranges = [x for g in grid for x in (g.get("fpp_range_noise_models") or []) if x is not None]
    rows = ["Wider grid (absolute windows 0.75–2 d × masks 1.0/1.5/2.0 T14): the white-noise gate passes on "
            f"{white} of {len(grid)} settings; where it passes, FPP {_fmt(min(fpps), 3) if fpps else 'n/a'}–"
            f"{_fmt(max(fpps), 3) if fpps else 'n/a'} (with both noise models on every setting, "
            f"{_fmt(min(ranges), 3) if ranges else 'n/a'}–{_fmt(max(ranges), 3) if ranges else 'n/a'}); the largest "
            f"brightening is {_fmt(min(g['max_brightening_snr'] for g in grid), 1)}–"
            f"{_fmt(max(g['max_brightening_snr'] for g in grid), 1)}σ.", "",
            "| window (d) | mask (T14) | gate | largest brightening | strongest dip | FPP (robust spread) |", "|---|---|---|---|---|---|"]
    for g in grid:
        rows.append(f"| {g['window_days']} | {g['mask_t14']} | {'white' if g['white'] else 'not white'} | "
                    f"{g['max_brightening_snr']:.1f}σ | {g['snr']:.1f}σ | {_fmt(g['fpp'], 4)} |")
    return "\n".join(rows)


def _fmt(x, nd=2):
    return "n/a" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{nd}f}"


def markdown(r: dict) -> str:
    fit, lt, px = r["fit"], r["lightcurve_tests"], r["pixel"]
    c = px["centroid"]
    sec, oe, tm, cr = lt.get("secondary") or {}, lt.get("odd_even_depth") or {}, lt.get("timing") or {}, lt["crowding"]
    lines = [
        "# pi Men (TIC 261136679), TESS sector 1: S2 extended and pixel-level vetting",
        "",
        f"Made {r['made_at']} by `scripts/vet_pi_men_s2.py` from the SPOC files `{r['inputs']['lightcurve'].get('file')}` and "
        f"`{r['inputs']['tpf'].get('file')}` (sha256 {r['inputs']['tpf'].get('file_sha256', '')[:12]}…). "
        "MAST's search service was failing on 2026-10-19; the files came from the public STScI bucket that MAST's "
        "download links redirect to. Every test below only adds flags; none changes a pass/fail decision by default.",
        "",
        f"Ephemeris from a joint limb-darkened fit of all {fit['n_epochs']} sector-1 epochs: P = {fit['period_days']:.5f} ± "
        f"{_fmt(fit['period_err'], 5)} d, T0 = {fit['t0']:.4f} BTJD, T14 = {fit['t14_hours']:.2f} ± {_fmt(fit['t14_err_hours'])} h, "
        f"depth {fit['depth_ppm']:.0f} ± {_fmt(fit['depth_err_ppm'], 0)} ppm.",
        "",
        "## Light-curve tests", "", ("On the light curve re-detrended with the fitted transits masked (1.5 T14 each side), as DV does, and phase 0.5 "
         f"masked too (masked phases: {', '.join(_fmt(p, 3) for p in lt.get('masked_phases') or [])}; the first pass's "
         "strongest dip is masked only when that pass already finds it significant)."),
        "",
        "| test | result | flag |",
        "|---|---|---|",
        f"| crowding | CROWDSAP = {_fmt(cr['crowdsap'], 4)}, FLFRCSAP = {_fmt(cr['flfrcsap'], 4)} (flag below {cr['crowding_min']}) | "
        f"{'crowded' if cr['crowded'] else 'none'} |",
        f"| secondary, all phases | strongest dip at phase {_fmt(sec.get('phase'), 3)}: {_fmt(sec.get('depth_ppm'), 1)} ± "
        f"{_fmt(sec.get('sigma_ppm'), 1)} ppm ({_fmt(sec.get('snr'), 1)}σ; largest brightening {_fmt(sec.get('max_brightening_snr'), 1)}σ; "
        f"{sec.get('n_trials')} coarse positions); threshold {_fmt(sec.get('threshold_sigma'), 1)}σ "
        f"({sec.get('threshold_rule')}; robust spread {_fmt(sec.get('scan_robust_sigma'))}); {sec.get('n_epochs')} epochs, "
        f"the largest carrying {_fmt((sec.get('max_epoch_share') or 0) * 100, 0)}% "
        f"({'periodic' if sec.get('periodic') else 'not periodic'}); at phase 0.5: "
        f"{_fmt((sec.get('phase_05') or {}).get('depth_ppm'), 1)} ± {_fmt((sec.get('phase_05') or {}).get('sigma_ppm'), 1)} ppm | "
        f"{'secondary_any_phase' if 'secondary_any_phase' in r['lightcurve_flags'] else 'none'} at the default setting"
        f"{'; **' + lt['secondary_flag_stability']['verdict'] + '**' if lt.get('secondary_flag_stability') else ''} |",
        f"| odd/even depth ({oe.get("source", "")}) | odd {_fmt(oe.get('odd_depth_ppm'), 0)} ± {_fmt(oe.get('odd_err_ppm'), 0)} ppm (n = {oe.get('n_odd')}), "
        f"even {_fmt(oe.get('even_depth_ppm'), 0)} ± {_fmt(oe.get('even_err_ppm'), 0)} ppm (n = {oe.get('n_even')}): "
        f"{_fmt(oe.get('delta_sigma'), 1)}σ | {'odd_even_depth' if 'odd_even_depth' in r['lightcurve_flags'] else 'none'} |",
    ]
    lin, ot = tm.get("linear") or {}, tm.get("odd_even") or {}
    lines += [
        f"| timing, linear ephemeris | {tm.get('n_epochs')} epochs, χ² = {_fmt(lin.get('chi2'), 1)} for {lin.get('dof')} dof, "
        f"p = {_fmt(lin.get('p_value'), 3)}; O−C (min): {', '.join(_fmt(x, 1) for x in (tm.get('o_minus_c_minutes') or []))} | "
        f"{'timing_inconsistent' if 'timing_inconsistent' in r['lightcurve_flags'] else 'none'} |",
        f"| odd/even timing | odd − even offset {_fmt(ot.get('offset_minutes'), 1)} ± {_fmt(ot.get('offset_err_minutes'), 1)} min "
        f"({_fmt(ot.get('delta_sigma'), 1)}σ) | {'odd_even_timing' if 'odd_even_timing' in r['lightcurve_flags'] else 'none'} |",
        "",
    ]
    fg = lt.get("secondary_flag_grid") or []
    if fg:
        st = lt["secondary_flag_stability"]
        lines += ["### The secondary flag across run settings", "",
                  f"The same two-pass preparation and secondary test on nearby run settings (the run's detrend window "
                  f"× bin size; the vetting window is never below 12 T14 = {_fmt(fg[0]['effective_window_days'])} d, so "
                  f"every window up to that gives the same light curve). {st['flagged']} of {st['n_settings']} settings "
                  f"flag the dip: **{st['verdict']}**.", "",
                  "| window (d) | vetting window (d) | bin (min) | first pass | masked phases | strongest dip | "
                  "threshold | dip / threshold | epochs: largest share | flag |", "|---|---|---|---|---|---|---|---|---|---|"]
        for g in fg:
            lines.append(f"| {g['window_days']} | {_fmt(g['effective_window_days'])} | {g['bin_minutes']:g} | "
                         f"{_fmt(g['first_pass_snr'], 2)}σ{' (significant)' if g['first_pass_significant'] else ''} | "
                         f"{', '.join(_fmt(p, 3) for p in g['masked_phases'])} | {_fmt(g['snr'], 2)}σ at "
                         f"{_fmt(g['phase'], 3)} | {_fmt(g['threshold_sigma'], 2)}σ | "
                         f"{_fmt(g['snr'] / g['threshold_sigma'], 3)} | {_fmt((g['max_epoch_share'] or 0) * 100, 0)}%"
                         f"{'' if g['periodic'] else ' (not periodic)'} | "
                         f"{'secondary_any_phase' if g['flagged'] else 'none'} |")
        lines.append("")
    lines += [
        "## Pixel-level tests",
        "",
    ]
    sat = c.get("saturation", {})
    pt, pc, fw, mo = c.get("psf_target", {}), c.get("psf_control", {}), c.get("flux_weighted", {}), px.get("motion", {})
    lines += [
        f"Difference image over {c.get('n_transits')} transits ({c.get('n_in')} in-transit and {c.get('n_out')} "
        f"out-of-transit cadences; errors scaled ×{_fmt(c.get('error_scale'))} by the scatter between transits). "
        f"Pixel scale {_fmt(c.get('pixel_scale_arcsec'))}″ from the TPF's WCS. Depth in the aperture pixels: "
        f"{_fmt((c.get('depth_in_aperture') or 0) * 1e6, 0)} ppm.",
        "",
        "| measure | offset | significance | note |",
        "|---|---|---|---|",
        f"| PSF fit to the difference image, from the catalogue position | {_fmt(pt.get('offset_total_px'), 3)} px = "
        f"{_fmt(pt.get('offset_arcsec'), 1)}″ (column {_fmt((pt.get('offset_px') or [None])[0], 3)}, row "
        f"{_fmt((pt.get('offset_px') or [None, None])[1], 3)}) | {_fmt(pt.get('sigma'), 1)}σ | systematic floor "
        f"{_fmt(pt.get('systematic_floor_px'), 3)} px |",
        f"| PSF fit, from the out-of-transit centroid (DV 'control') | {_fmt(pc.get('offset_total_px'), 3)} px = "
        f"{_fmt(pc.get('offset_arcsec'), 1)}″ (column {_fmt((pc.get('offset_px') or [None])[0], 3)}, row "
        f"{_fmt((pc.get('offset_px') or [None, None])[1], 3)}) | {_fmt(pc.get('sigma'), 1)}σ | fit quality "
        f"{_fmt(pc.get('quality'))} (reliable above 0.7) |",
        f"| flux-weighted, inside the aperture | {_fmt(math.hypot(*fw['offset_px']) if fw.get('offset_px') else None, 3)} px = "
        f"{_fmt(fw.get('offset_arcsec'), 1)}″ | {_fmt(fw.get('sigma'), 1)}σ | |",
        f"| centroid motion (per cadence) | shift ({_fmt((mo.get('shift_px') or [None])[0] * 1e3 if mo.get('shift_px') else None, 2)}, "
        f"{_fmt((mo.get('shift_px') or [None, None])[1] * 1e3 if mo.get('shift_px') else None, 2)}) millipixel; source offset "
        f"{_fmt(mo.get('source_offset_arcsec'), 1)}″ | {_fmt(mo.get('sigma'), 1)}σ (χ²₂ = {_fmt(mo.get('chi2'), 1)}) | "
        f"{'uninformative on a saturated star' if sat.get('saturated') else ''} |",
        "",
        f"Saturation: {'yes' if sat.get('saturated') else 'no'} ({sat.get('plateau_pixels')} contiguous pixels within 5% of the "
        f"brightest in column {sat.get('column')}; Tmag {_fmt(r['pixel']['header'].get('tessmag'))}). "
        f"Centroid reliable: **{'yes' if c.get('reliable') else 'no'}**"
        + (f" ({'; '.join(c.get('unreliable_reasons', []))})" if c.get("unreliable_reasons") else "") + ".",
        "",
        f"Ghost diagnostic: core {_fmt(px['ghost'].get('core'), 1)}, halo {_fmt(px['ghost'].get('halo'), 1)}. "
        f"Momentum dumps: {px['momentum_dumps']['n_dumps']} in the sector, "
        f"{len(px['momentum_dumps']['epochs_with_dump'])} within half a duration of a transit.",
        "",
        f"Pixel flags: {', '.join(r['pixel_flags']) or 'none'}. Light-curve flags: {', '.join(r['lightcurve_flags']) or 'none'}.",
        "",
    ]
    nb = px.get("neighbours")
    q = r["neighbour_query"]
    lines += ["## Nearby stars", ""]
    if nb and nb.get("stars"):
        lines += [f"Source: {q.get('source')}, within {q.get('radius_arcsec'):.0f}″. Depth in the aperture "
                  f"{nb['depth_aperture'] * 1e6:.0f} ppm (PDCSAP depth × CROWDSAP); a star more than "
                  f"{_fmt(nb['delta_mag_limit'])} mag fainter than the target cannot produce it even with a total eclipse "
                  f"if all its light fell in the aperture. Gaussian PSF σ = {nb['psf_sigma_px']} px (an approximation).",
                  "", "| star | Tmag | separation | share of aperture flux | needed depth | ruled out |", "|---|---|---|---|---|---|"]
        for s in nb["stars"][:15]:
            lines.append(f"| {s['id']} | {s['tmag']:.2f} | {s['separation_arcsec']:.1f}″ | {s['flux_share']:.2e} | "
                         f"{s['needed_depth']:.2e} | {'; '.join(s['ruled_out_by']) or 'no'} |")
        if len(nb["stars"]) > 15:
            lines.append(f"| … {len(nb['stars']) - 15} more | | | | | |")
    else:
        lines.append(f"Not available: {'; '.join(q.get('errors') or ['no stars returned'])}.")
    v = r["validation"]
    lines += ["", "## S3: reduced FPP (exoplan's scheme, not TRICERATOPS)", "",
              (f"FPP = {_fmt(v['fpp'], 4)} (robust-spread noise; with the scan's plain std instead: "
               f"{_fmt((v['evidence'].get('fpp_bracket_robust_vs_std') or [None, None])[1], 4)}), NFPP = {_fmt(v['nfpp'], 6)}; "
               f"class: {v['fpp_class']}." if v.get("fpp") is not None else f"{v['fpp_class']}.")
              + f" Label: **{v['label']}**.", "",
              _gate_line(v), "", _grid_lines(r), "",
              f"Not modelled: {'; '.join(v['not_modelled'])}. Notes: {'; '.join(v['notes']) or 'none'}. "
              f"Priors: {v['priors']['source']}."]
    lines += ["", "## SPOC's own DV centroid result, for comparison", ""]
    if isinstance(r["spoc_dv"], list):
        for row in r["spoc_dv"]:
            t = row.get("ticCentroidOffsets", {})
            lines.append(f"* TOI {row.get('toi')}: offset from the TIC position {_fmt((t.get('skyOffset') or {}).get('value'), 1)} ± "
                         f"{_fmt((t.get('skyOffset') or {}).get('uncertainty'), 1)}″ (row {_fmt((t.get('rowOffset') or {}).get('value'), 3)} px, "
                         f"column {_fmt((t.get('columnOffset') or {}).get('value'), 3)} px); DV quality metric "
                         f"{_fmt(row.get('quality'))} (DV counts above 0.7 as reliable).")
    else:
        lines.append(f"Not available: {r['spoc_dv'].get('error')}.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", default="cache/tpf")
    ap.add_argument("--run", default="runs/tess-pi-men-s1")
    ap.add_argument("--config", default="configs/tess_pi_men_s1.toml")
    ap.add_argument("--out", default="docs/results/pi_men_s2_vetting")
    args = ap.parse_args(argv)
    warnings.simplefilter("ignore")
    result = _clean(run(Path(args.cache), Path(args.run), Path(args.config)))
    out = Path(args.out)
    out.with_suffix(".json").write_text(json.dumps(result, indent=1) + "\n")
    out.with_suffix(".md").write_text(markdown(result))
    print(out.with_suffix(".md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())

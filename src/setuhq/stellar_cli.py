# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""``setuhq flares``, ``setuhq pulsations``, ``setuhq cheops``, ``setuhq binaries``, ``setuhq rotation`` and
``setuhq transients``: the stellar commands.

Each writes one JSON record (``--out``) with the result, its provenance (version, the stellar code fingerprint,
every input's sha256) and its labels, and prints a short summary. Detections are *detected* at a stated
significance; a variability type is *likely* or *candidate*; nothing is confirmed. An eclipsing binary or a
transient SetuHQ finds is a *candidate*, never new.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

LABEL = ("Detected at the stated significance; not a confirmation. Variability types are heuristic (likely or "
         "candidate). Energies assume a 9000 K blackbody flare and TIC Teff and radius, else they are unavailable.")


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o).__name__)


def _finite(o):
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _finite(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_finite(v) for v in o]
    if isinstance(o, np.generic):
        return _finite(o.item())
    if isinstance(o, np.ndarray):
        return _finite(o.tolist())
    return o


def _write(record: dict, out: str | None) -> None:
    text = json.dumps(_finite(record), indent=1, default=_json_default, allow_nan=False)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n")
        print(f"wrote {out}")


def _status(capability: str, what: str) -> str:
    """The capability's validation status as the committed record states it (setuhq.stellar_tools), printed with
    every run, so no output presents an unvalidated detector as validated."""
    from setuhq.stellar_tools import validation_file, validation_status

    status = validation_status(capability)
    print(f"{what}: {status} against published results ({validation_file(capability).replace('.json', '.md')})")
    return status


def _stitched(lcs):
    t = np.concatenate([lc.time for lc in lcs])
    f = np.concatenate([lc.flux / np.median(lc.flux) for lc in lcs])
    e = np.concatenate([lc.flux_err / np.median(lc.flux) for lc in lcs])
    o = np.argsort(t)
    return t[o], f[o], e[o]


def cmd_flares(args) -> int:
    from setuhq import flares as fl
    from setuhq.stellar_io import load_input, provenance

    lcs, star, inputs = load_input(args.target, sectors=args.sector, exptime=args.exptime, cache_root=args.cache)
    for k in ("teff", "radius", "tmag", "distance_pc"):
        v = getattr(args, k)
        if v is not None:
            star = {**(star or {}), k: v}
    per = []
    for lc in lcs:
        cad = float(np.median(np.diff(lc.time))) * 86400.0
        cfg = fl.config_for(args.mission, cad, denoise=args.denoise)
        out = fl.detect_flares(lc.time, lc.flux, lc.flux_err, config=cfg, star=star, band=args.mission)
        rec = {"sector": lc.provenance.get("sector"), **out}
        if not args.no_null:
            rec["inverted_null"] = fl.inverted_null(lc.time, lc.flux, lc.flux_err, config=cfg, band=args.mission)
        if args.completeness:
            rec["completeness"] = fl.inject_recover(lc.time, lc.flux, lc.flux_err, config=cfg, star=star, band=args.mission,
                                                    n_trials=args.completeness, per_trial=10, seed=args.seed,
                                                    real_flares=out["flares"])
        per.append(rec)
        s = out["summary"]
        print(f"{lc.target} sector {rec['sector']}: {s['n_flares']} flares detected ({s['n_complex']} complex) in "
              f"{s['observing_days']:.2f} d; {s['n_rejected']} candidates rejected by the template test"
              + (f"; inverted-flux null: {rec['inverted_null']['false_positives']}" if "inverted_null" in rec else ""))
    energies = [f["e_bol_erg"] for r in per for f in r["flares"] if f.get("e_bol_erg")]
    days = sum(r["summary"]["observing_days"] for r in per)
    record = {"kind": "setuhq-flares/1", "target": args.target, "star": star, "mission": args.mission, "results": per,
              "ffd": fl.ffd(energies, days), "label": LABEL, "validation_status": _status("flares", "flare detection"),
              "provenance": provenance(inputs)}
    _write(record, args.out)
    return 0


def cmd_pulsations(args) -> int:
    from setuhq import pulsations as pu
    from setuhq.stellar_io import load_input, provenance

    lcs, star, inputs = load_input(args.target, sectors=args.sector, exptime=args.exptime, cache_root=args.cache)
    t, f, _ = _stitched(lcs)
    teff = args.teff if args.teff is not None else (star or {}).get("teff")
    out = pu.analyse(t, f, teff=teff, fmin=args.fmin, fmax=args.fmax, max_frequencies=args.max_frequencies,
                     n_surrogates=args.surrogates, seed=args.seed, solar=True if args.solar else None)
    out.pop("_time", None)
    out.pop("_residual", None)
    pw = out["prewhitening"]
    print(f"{args.target}: {pw['n_significant']} frequencies at S/N ≥ {pw['snr_stop']:g} over {pw['baseline_days']:.1f} d "
          f"({pw['stop']}); type: {out['type']['label']} ({out['type']['confidence']} confidence)")
    for x in pw["frequencies"][:10]:
        print(f"  {x['id']:>4} {x['frequency']:10.5f} d⁻¹ {x['frequency_uhz']:9.3f} µHz  A={x['amplitude'] * 1e6:8.1f} ppm "
              f"S/N={x['snr']:.1f}{'  ' + x['combination'] if x['combination'] else ''}")
    record = {"kind": "setuhq-pulsations/1", "target": args.target, "star": star, **out, "label": LABEL,
              "validation_status": _status("pulsations", "frequency analysis"), "provenance": provenance(inputs)}
    _write(record, args.out)
    return 0


def cmd_cheops(args) -> int:
    from setuhq import cheops as ch
    from setuhq.stellar_io import provenance

    try:
        out = ch.get_cheops_lightcurve(args.target, file_key=args.file_key, max_visits=args.max_visits,
                                       cache_dir=Path(args.cache) / "cheops", offline=args.offline)
    except ch.CheopsUnavailable as exc:
        print(f"setuhq cheops: {exc}", file=sys.stderr)
        return 2
    print(f"{args.target}: {out['n_public_visits']} public CHEOPS visits ({out['n_not_public_dropped']} not public, "
          "skipped)")
    rows = []
    for v in out["visits"]:
        p, d = v["provenance"], v["detrend"]
        print(f"  {p['file_key']} ({p['programme']}, obs {p['obs_id']}): {p['n_points']} points at {v['cadence_s']:.0f} s; "
              f"terms {', '.join(d['terms']) or 'none'}; rms {d['rms_raw_ppm']:.0f} -> {d['rms_detrended_ppm']:.0f} ppm")
        row = {k: v[k] for k in ("provenance", "cadence_s", "detrend")}
        det = v["_detrended"]
        if args.flares:
            from setuhq import flares as fl

            ok = np.isfinite(det["flux"])
            cfg = fl.config_for("CHEOPS", v["cadence_s"], denoise=args.denoise)
            row["flares"] = fl.detect_flares(det["time"][ok], det["flux"][ok], det["flux_err"][ok], config=cfg, band="CHEOPS")
            print(f"    {row['flares']['summary']['n_flares']} flares detected")
        if args.points:
            ok = np.isfinite(det["flux"])
            row["points"] = {"time_btjd": det["time"][ok], "flux": det["flux"][ok]}
        rows.append(row)
    print("\n" + ch.credit_text([v["provenance"] for v in out["visits"]]))
    record = {"kind": "setuhq-cheops/1", "target": args.target, "n_public_visits": out["n_public_visits"],
              "n_not_public_dropped": out["n_not_public_dropped"], "visits": rows,
              "validation_status": _status("cheops", "CHEOPS ingest"), **ch.credit([v["provenance"] for v in out["visits"]]),
              "provenance": provenance([{"path": r["provenance"]["file_key"], "sha256": r["provenance"]["sha256"]} for r in rows])}
    _write(record, args.out)
    return 0


def _quality_for(target: str, lc, cache_root: str) -> dict | None:
    """Momentum-dump and scattered-light times for a SPOC light curve: read from the FITS file (given, or the one
    fetched into the cache), since the loaders drop flagged cadences. None for a CSV."""
    from setuhq import transients as tr
    from setuhq.stellar_io import parse_tic

    p = Path(target)
    if p.exists():
        return tr.read_quality(p) if "fits" in p.name.lower() else None
    tic = parse_tic(target)
    idx = Path(cache_root) / "mast" / "stellar" / str(tic) / "index_120.json"
    sec = lc.provenance.get("sector")
    if tic and idx.exists() and sec is not None:
        files = json.loads(idx.read_text())
        if str(sec) in files:
            return tr.read_quality(idx.parent / files[str(sec)])
    return None


def cmd_binaries(args) -> int:
    from setuhq import binaries as eb
    from setuhq.stellar_io import load_input, provenance

    lcs, star, inputs = load_input(args.target, sectors=args.sector, exptime=args.exptime, cache_root=args.cache)
    per = []
    for lc in lcs:
        out = eb.analyse(lc.time, lc.flux, lc.flux_err)
        out.pop("phase_curve", None)
        rec = {"sector": lc.provenance.get("sector"), **out}
        if args.transit_period is not None:
            rec["vetting_hints"] = eb.vetting_hints(lc.time, lc.flux, args.transit_period, args.transit_epoch,
                                                    args.transit_duration, flux_err=lc.flux_err)
        per.append(rec)
        if out.get("period"):
            sec = out["secondary"]
            print(f"{lc.target} sector {rec['sector']}: {'eclipsing-binary candidate' if out['eb_candidate'] else 'not flagged'}; "
                  f"P = {out['period']:.6f} ± {out['period_err']:.6f} d{' (ambiguous)' if out['period_ambiguous'] else ''}; "
                  f"primary depth {out['primary']['depth']:.4f}, width {out['primary']['width_phase']:.3f} in phase; "
                  + (f"secondary at phase {sec['phase']:.4f} (e cos w hint {sec['e_cos_omega_hint']:+.4f})" if sec else "no secondary")
                  + f"; morphology {out['morphology']['class']}")
        for r in out["reasons"]:
            print(f"  - {r}")
    record = {"kind": "setuhq-binaries/1", "target": args.target, "star": star, "results": per, "label": eb.LABEL,
              "validation_status": _status("binaries", "eclipsing-binary analysis"), "provenance": provenance(inputs)}
    _write(record, args.out)
    return 0


def cmd_rotation(args) -> int:
    from setuhq import rotation as ro
    from setuhq.stellar_io import load_input, provenance

    lcs, star, inputs = load_input(args.target, sectors=args.sector, exptime=args.exptime, cache_root=args.cache)
    per = []
    for lc in lcs:
        out = ro.measure(lc.time, lc.flux)
        out.pop("periodogram", None)
        per.append({"sector": lc.provenance.get("sector"), **out})
        if out["detected"]:
            print(f"{lc.target} sector {per[-1]['sector']}: rotation period {out['period']:.3f} ± {out['period_err']:.3f} d"
                  + (f" (alias {out['alias']:.3f} d)" if out.get("alias") else "") + f"; {out['rule']}")
        else:
            print(f"{lc.target} sector {per[-1]['sector']}: no rotation period measured: {'; '.join(out['reasons'])}")
    print(f"Limit: one TESS sector measures periods up to about {ro.LIMIT_DAYS:g} d; sectors are not stitched.")
    record = {"kind": "setuhq-rotation/1", "target": args.target, "star": star, "results": per, "label": ro.LABEL,
              "validation_status": _status("rotation", "rotation measurement"), "provenance": provenance(inputs)}
    _write(record, args.out)
    return 0


def cmd_transients(args) -> int:
    from setuhq import transients as tr
    from setuhq.stellar_io import provenance

    per, inputs = [], []
    if args.ra is not None and args.dec is not None:
        import hashlib

        from setuhq import ffi

        sector = args.sector[0] if args.sector else None
        if sector is None:
            if args.time is None:
                print("setuhq transients: give --sector or --time with --ra/--dec", file=sys.stderr)
                return 2
            ch = ffi.choose_sector(args.ra, args.dec, args.time, Path(args.cache) / "tesscut")
            sector = ch["sector"]
            if sector is None:
                print(f"setuhq transients: {ch['rule']}", file=sys.stderr)
                return 2
        path = ffi.fetch_cutout(args.ra, args.dec, sector, size=args.size, cache_dir=Path(args.cache) / "tesscut")
        inputs.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "sector": sector})
        d = ffi.difference_lightcurve(path, args.ra, args.dec)
        out = tr.find_transients(d["time"], d["flux"], d["flux_err"], mode="difference", quality=d["quality_times"],
                                 controls=list(d["controls"].values()), centroid=d["centroid"],
                                 zero_point=tr.TESS_ZERO_POINT, aperture_correction=d["aperture_correction"])
        out["photometry"] = {k: d[k] for k in ("pixel", "aperture_pixel", "controls_used", "aperture_correction",
                                               "aperture_correction_source", "n_reference_cadences", "camera", "ccd")}
        out["data_credit"] = ffi.CREDIT
        per.append({"sector": sector, **out})
        if not args.keep_cutout:
            path.unlink(missing_ok=True)
        where = f"RA {args.ra:.5f} Dec {args.dec:+.5f}"
    else:
        from setuhq.stellar_io import load_input

        lcs, _, inputs = load_input(args.target, sectors=args.sector, exptime=args.exptime, cache_root=args.cache)
        for lc in lcs:
            out = tr.find_transients(lc.time, lc.flux, lc.flux_err, quality=_quality_for(args.target, lc, args.cache))
            per.append({"sector": lc.provenance.get("sector"), **out})
        where = args.target
    for r in per:
        s = r["summary"]
        print(f"{where} sector {r['sector']}: {s['n_candidates']} transient candidates "
              f"({s['n_likely_false_alarms']} likely false alarms)")
        for c in r["candidates"][:20]:
            mag = f", T = {c['peak_mag']:.2f}" if c.get("peak_mag") is not None else ""
            print(f"  BTJD {c['t_peak']:.3f} ({c['scale']}): peak {c['peak']:.4g}{mag}, rise {c['rise_time']:.3f} d, "
                  f"decay {'> ' + format(c['decay_time_lower_limit'], '.2f') if c['decay_time'] is None else format(c['decay_time'], '.3f')} d; "
                  f"{c['class_hint']}")
    from setuhq.stellar_tools import TRANSIENT_SEARCH_AID

    print(TRANSIENT_SEARCH_AID)
    record = {"kind": "setuhq-transients/1", "target": args.target, "results": per, "label": f"{tr.LABEL} {TRANSIENT_SEARCH_AID}",
              "validation_status": _status("transients", "transient detection"), "provenance": provenance(inputs)}
    _write(record, args.out)
    return 0


def add_parsers(sub) -> None:
    """Add the six stellar commands to ``setuhq``'s sub-parsers."""
    def common(p, solar=False):
        p.add_argument("target", help="a TIC id (e.g. 'TIC 441420236'), a SPOC *_lc.fits file or a CSV (time, flux[, flux_err])")
        p.add_argument("--sector", type=int, nargs="*", help="TESS sectors (default: every SPOC sector)")
        p.add_argument("--exptime", type=int, default=120, choices=(20, 120), help="TESS cadence in seconds")
        p.add_argument("--cache", default="cache", help="cache root (MAST files, TIC values)")
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--out", help="write the JSON record here")

    fl = sub.add_parser("flares", help="detect stellar flares: morphology, energies, completeness and a null")
    common(fl)
    fl.add_argument("--mission", default="TESS", choices=("TESS", "CHEOPS"), help="sets the detection defaults and band")
    fl.add_argument("--denoise", action="store_true", help="stationary-wavelet denoising first (needs setuhq[wavelets])")
    fl.add_argument("--completeness", type=int, default=0, metavar="N", help="N injection-recovery trials (10 flares each)")
    fl.add_argument("--no-null", action="store_true", help="skip the flux-inverted null")
    for k, h in (("teff", "Teff (K)"), ("radius", "radius (solar radii)"), ("tmag", "TESS magnitude"), ("distance_pc", "distance (pc)")):
        fl.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float, help=f"override the TIC {h}")
    fl.set_defaults(func=cmd_flares)

    pu = sub.add_parser("pulsations", help="frequency analysis: pre-whitening, combinations, background, numax/Δν, type")
    common(pu)
    pu.add_argument("--fmin", type=float, help="lowest frequency (d⁻¹)")
    pu.add_argument("--fmax", type=float, help="highest frequency (d⁻¹; default Nyquist)")
    pu.add_argument("--max-frequencies", type=int, default=80)
    pu.add_argument("--surrogates", type=int, default=0, help="red-noise surrogates for the false-frequency rate")
    pu.add_argument("--teff", type=float, help="Teff (K) for the type heuristic (default: TIC)")
    pu.add_argument("--solar", action="store_true", help="always run the numax/Δν analysis")
    pu.set_defaults(func=cmd_pulsations)

    ch = sub.add_parser("cheops", help="public CHEOPS light curves of a target (DACE), detrended; optional flare search")
    ch.add_argument("target", help="a star name or 'RA DEC' in degrees")
    ch.add_argument("--file-key", help="one visit (CH_PR..._TG..._V....)")
    ch.add_argument("--max-visits", type=int, default=3)
    ch.add_argument("--offline", action="store_true", help="cache only, no network")
    ch.add_argument("--flares", action="store_true", help="also detect flares in each visit")
    ch.add_argument("--denoise", action="store_true", help="with --flares: wavelet denoising first")
    ch.add_argument("--points", action="store_true", help="include the detrended points in the record")
    ch.add_argument("--cache", default="cache")
    ch.add_argument("--out", help="write the JSON record here")
    ch.set_defaults(func=cmd_cheops)

    eb = sub.add_parser("binaries", help="eclipsing binaries and ellipsoidal or reflection variables: period, eclipses, "
                                         "secondary phase (e cos w hint), morphology; a candidate flag with reasons")
    common(eb)
    eb.add_argument("--transit-period", type=float, help="advisory vetting hints at a transit candidate's period (d)")
    eb.add_argument("--transit-epoch", type=float, help="its mid-transit time (BTJD)")
    eb.add_argument("--transit-duration", type=float, default=0.1, help="its duration (d)")
    eb.set_defaults(func=cmd_binaries)

    ro = sub.add_parser("rotation", help="a rotation period from spot modulation (Lomb-Scargle and ACF), per sector; "
                                         "periods beyond about 13 d are not measured")
    common(ro)
    ro.set_defaults(func=cmd_rotation)

    tr = sub.add_parser("transients", help="non-periodic brightenings: rise, decay, amplitude, class hints and "
                                           "false-alarm screens, in a SPOC light curve or a TESScut cutout of any position")
    tr.add_argument("target", nargs="?", default="cutout", help="a TIC id, a SPOC *_lc.fits file or a CSV (omit with --ra/--dec)")
    tr.add_argument("--sector", type=int, nargs="*", help="TESS sectors (with --ra/--dec: the one sector to cut out)")
    tr.add_argument("--exptime", type=int, default=120, choices=(20, 120), help="TESS cadence in seconds")
    tr.add_argument("--ra", type=float, help="RA (deg): photometry on a TESScut cutout of the full-frame images")
    tr.add_argument("--dec", type=float, help="Dec (deg)")
    tr.add_argument("--time", type=float, help="with --ra/--dec and no --sector: the sector containing this BTJD")
    tr.add_argument("--size", type=int, default=11, help="cutout size in pixels (default 11)")
    tr.add_argument("--keep-cutout", action="store_true", help="keep the downloaded cutout in the cache")
    tr.add_argument("--cache", default="cache", help="cache root (MAST files, TIC values, cutouts)")
    tr.add_argument("--seed", type=int, default=0)
    tr.add_argument("--out", help="write the JSON record here")
    tr.set_defaults(func=cmd_transients)

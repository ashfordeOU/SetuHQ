"""Export vetted candidates for follow-up in the style of an ExoFOP Community TOI (CTOI) submission (ATLAS F7, S4).

A person submits a CTOI under their own ExoFOP account; exoplan only prepares the table. **The field list below is
UNVERIFIED against ExoFOP's current CTOI upload form.** ExoFOP was unreachable while it was written (ATLAS F7 FLAG).
What ATLAS F7 does establish is that an upload needs period, epoch, depth and duration with their uncertainties, and
that a CTOI must not duplicate a TOI on the same star. Check the form before submitting, and edit
:data:`CTOI_FIELDS`, which is the only place the field list lives.

Which candidates are exported (one row per periodic signal per star):

* passed vetting, not ``off_ephemeris``, on a periodic signal with two or more transits;
* none of the S2 disqualifying flags (``secondary_any_phase``, ``odd_even_depth``, ``odd_even_timing``,
  ``centroid_offset``), whether or not the run's ``[vetting] decide`` was set;
* the S3 reduced FPP does not call it a likely nearby false positive, and its FPP is below 0.5;
* not a duplicate of a TOI on the same TIC (:func:`exoplan.discover.match_toi`). Without the TOI table the export is
  refused unless explicitly allowed, and every row then says the TOI check was not done.

Every row carries the ephemeris uncertainty one year after its reference epoch, and the predicted transit windows
for the next 12 months are written beside the table (:mod:`exoplan.ephemeris`). Depths are in ppm, as in the archive's
``toi`` table; the ``ps`` and ``pscomppars`` tables give depth in percent (ATLAS F6).
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from exoplan import dvtests, pixel
from exoplan.ephemeris import BTJD_OFFSET, cone, transit_windows
from exoplan.stellar import tic_id

R_SUN_IN_R_EARTH = 6.957e8 / 6.3781e6   # IAU nominal solar radius over the IAU nominal equatorial Earth radius
CTOI_FIELDS_STATUS = "UNVERIFIED against ExoFOP's current CTOI upload form (ExoFOP was unreachable; ATLAS F7 FLAG)"
# (key, column header, required). The required ones are ATLAS F7's minimal set; the rest are commonly given.
CTOI_FIELDS = (
    ("tic_id", "TIC ID", True),
    ("period_days", "Period (days)", True),
    ("period_unc_days", "Period unc (days)", True),
    ("epoch_bjd_tdb", "Epoch (BJD_TDB)", True),
    ("epoch_unc_days", "Epoch unc (days)", True),
    ("depth_ppm", "Depth (ppm)", True),
    ("depth_unc_ppm", "Depth unc (ppm)", True),
    ("duration_hours", "Duration (hours)", True),
    ("duration_unc_hours", "Duration unc (hours)", True),
    ("planet_radius_earth", "Planet radius (R_Earth)", False),
    ("planet_radius_unc_earth", "Planet radius unc (R_Earth)", False),
    ("snr", "SNR", False),
    ("notes", "Notes", False),
)
# exoplan's own columns, after the CTOI ones: provenance and the vetting behind each row. Not ExoFOP fields.
EXTRA_FIELDS = ("epoch_btjd", "n_transits", "fap_label", "fap_method", "flags", "crowdsap", "centroid",
                "fpp", "nfpp", "fpp_method", "validation_label", "epoch_sigma_hours_plus_1yr", "stellar_radius_source",
                "toi_check", "candidate_ids", "run", "config_sha256", "methods_url", "status")
EXPORT_DISQUALIFYING = dvtests.DISQUALIFYING | pixel.DISQUALIFYING
METHODS_URL = "https://github.com/ashfordeOU/EXOPLAN#readme"


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _flags(row: dict) -> list[str]:
    flags = row.get("flags") or []
    return [f for f in flags.split(";") if f] if isinstance(flags, str) else list(flags)


def exclusion(row: dict) -> str | None:
    """Why a candidate row is not exported, or None."""
    flags = _flags(row)
    if not row.get("passed"):
        return "did not pass vetting"
    if "off_ephemeris" in flags:
        return "off_ephemeris"
    if not row.get("period_days") or int(row.get("n_transits") or 0) < 2:
        return "not on a periodic signal with two or more transits"
    bad = sorted(set(flags) & EXPORT_DISQUALIFYING)
    if bad:
        return "S2 flags: " + ", ".join(bad)
    val = (row.get("metrics") or {}).get("validation") or {}
    if str(val.get("fpp_class", "")).startswith("likely nearby false positive"):
        return "S3: likely nearby false positive"
    if val.get("fpp") is not None and val["fpp"] >= 0.5:
        return f"S3: reduced FPP {val['fpp']:.2f} ≥ 0.5"
    if not (row.get("fit") or {}).get("period_days"):
        return "no transit fit with a period"
    return None


def _signal_key(row: dict) -> tuple:
    return (row.get("target"), round(float(row["fit"]["period_days"]), 2))


def ctoi_rows(candidates: list[dict], *, stars: dict | None = None, tois: dict | None = None,
              allow_unchecked: bool = False, run: str = "", config_sha256: str = "",
              methods_url: str = METHODS_URL) -> tuple[list[dict], list[dict]]:
    """(rows, excluded) from a run's ``candidates.json`` rows. ``tois`` maps TIC → :class:`exoplan.discover.Target`;
    when it is None the TOI duplicate check cannot be done, and rows are returned only with ``allow_unchecked``."""
    from exoplan.discover import match_toi

    excluded, groups = [], {}
    for row in candidates:
        why = exclusion(row)
        if why:
            excluded.append({"candidate_id": row.get("candidate_id"), "target": row.get("target"), "reason": why})
            continue
        groups.setdefault(_signal_key(row), []).append(row)
    rows = []
    for (target, _), members in groups.items():
        # the joint fit with the smallest period error stands for the signal
        best = min(members, key=lambda r: (r["fit"].get("period_err") or math.inf))
        f = best["fit"]
        tic = tic_id(str(target))
        if tic is None:
            excluded.append({"candidate_id": best.get("candidate_id"), "target": target, "reason": "not a TIC target"})
            continue
        toi_check = "not done (no TOI table)"
        if tois is not None:
            entry = {"t_center": f["t0"], "time_unit": best.get("time_unit", "BTJD"),
                     "duration_hours": f.get("t14_hours"), "period_days": f["period_days"]}
            match = match_toi(entry, tois[tic]) if tic in tois else None
            if match:
                excluded.append({"candidate_id": best.get("candidate_id"), "target": target,
                                 "reason": f"duplicates TOI {match['toi']} ({match['rule']})"})
                continue
            toi_check = "no TOI on this TIC matches" if tic in tois else "no TOI on this TIC"
        elif not allow_unchecked:
            excluded.append({"candidate_id": best.get("candidate_id"), "target": target,
                             "reason": "TOI duplicate check not done (no TOI table); pass allow_unchecked to export"})
            continue
        star = (stars or {}).get(target) or {}
        k, k_err = _num(f.get("k")), _num(f.get("k_err"))
        rad, rad_err = _num(star.get("radius")), _num(star.get("radius_err"))
        rp = rp_err = None
        if k and rad:
            rp = k * rad * R_SUN_IN_R_EARTH
            rp_err = rp * math.hypot((k_err or 0) / k, (rad_err or 0) / rad) if (k_err or rad_err) else None
        sigma_1yr = cone(t0=f["t0"], t0_err=f.get("t0_err"), period=f["period_days"], period_err=f.get("period_err"),
                         at=f["t0"] + 365.25)["sigma_hours"]
        val = (best.get("metrics") or {}).get("validation") or {}
        dv = (best.get("metrics") or {}).get("dv") or {}
        cen = ((best.get("metrics") or {}).get("pixel") or {}).get("centroid") or {}
        test = cen.get("psf_target") or cen.get("psf_control") or {}
        centroid = ("not run" if not cen else "unreliable: " + "; ".join(cen.get("unreliable_reasons", [])) if not cen.get("reliable")
                    else f"{test.get('offset_arcsec', float('nan')):.1f} arcsec, {test.get('sigma', float('nan')):.1f} sigma")
        flags = sorted(set(_flags(best)))
        rows.append({
            "tic_id": tic, "period_days": f["period_days"], "period_unc_days": f.get("period_err"),
            "epoch_bjd_tdb": f["t0"] + BTJD_OFFSET, "epoch_unc_days": f.get("t0_err"),
            "depth_ppm": f.get("depth_ppm"), "depth_unc_ppm": f.get("depth_err_ppm"),
            "duration_hours": f.get("t14_hours"), "duration_unc_hours": f.get("t14_err_hours"),
            "planet_radius_earth": rp, "planet_radius_unc_earth": rp_err, "snr": best.get("fap_snr") or best.get("snr"),
            "notes": (f"exoplan candidate, unvalidated, needs follow-up; {len(members)} vetted dip(s); "
                      f"S3: {val.get('label', 'not run')}; methods: {methods_url}"),
            "epoch_btjd": f["t0"], "n_transits": best.get("n_transits"), "fap_label": best.get("fap_label"),
            "fap_method": best.get("fap_method"), "flags": ";".join(flags),
            "crowdsap": (dv.get("crowding") or {}).get("crowdsap"), "centroid": centroid,
            "fpp": val.get("fpp"), "nfpp": val.get("nfpp"), "fpp_method": val.get("method"),
            "validation_label": val.get("label", ""), "epoch_sigma_hours_plus_1yr": sigma_1yr,
            "stellar_radius_source": star.get("source", "none") if rad else "none (no stellar radius)",
            "toi_check": toi_check, "candidate_ids": ";".join(sorted(str(m.get("candidate_id")) for m in members)),
            "run": run, "config_sha256": config_sha256, "methods_url": methods_url, "status": "candidate",
        })
    return rows, excluded


def check_row(row: dict) -> list[str]:
    """Schema check of one export row: every required CTOI field present and finite, uncertainties positive, the
    epoch a BJD, and the +1 yr ephemeris σ present. Returns the problems (empty when the row is valid)."""
    problems = []
    for key, header, required in CTOI_FIELDS:
        if key not in row:
            problems.append(f"missing {key}")
            continue
        if required and key != "tic_id" and _num(row[key]) is None:
            problems.append(f"{header} is not a finite number")
    for key in ("period_days", "depth_ppm", "duration_hours"):
        if (_num(row.get(key)) or 0) <= 0:
            problems.append(f"{key} must be positive")
    for key in ("period_unc_days", "epoch_unc_days", "depth_unc_ppm", "duration_unc_hours"):
        if (_num(row.get(key)) or 0) <= 0:
            problems.append(f"{key} must be a positive uncertainty")
    if not isinstance(row.get("tic_id"), int) or row["tic_id"] <= 0:
        problems.append("tic_id must be a positive integer")
    if (_num(row.get("epoch_bjd_tdb")) or 0) < 2.4e6:
        problems.append("epoch_bjd_tdb is not a BJD")
    if _num(row.get("epoch_sigma_hours_plus_1yr")) is None:
        problems.append("missing the +1 yr ephemeris uncertainty")
    if "confirmed" in str(row.get("validation_label", "")).lower():
        problems.append("a validation label may never say confirmed")
    return problems


def windows_for(rows: list[dict], *, start_btjd: float, days: float = 365.25, stars: dict | None = None,
                n_sigma: float = 3.0) -> list[dict]:
    """Predicted transit windows for every export row, ``days`` from ``start_btjd``."""
    out = []
    for r in rows:
        star = (stars or {}).get(f"TIC {r['tic_id']}") or {}
        for w in transit_windows(t0=r["epoch_btjd"], t0_err=r["epoch_unc_days"], period=r["period_days"],
                                 period_err=r["period_unc_days"], duration_hours=r["duration_hours"],
                                 start=start_btjd, end=start_btjd + days, n_sigma=n_sigma,
                                 ra=_num(star.get("ra")), dec=_num(star.get("dec"))):
            out.append({"tic_id": r["tic_id"], **w})
    return out


def btjd_now() -> float:
    from astropy.time import Time

    return float(Time(datetime.now(timezone.utc)).tdb.jd - BTJD_OFFSET)


def export_run(run_dir: str | Path, out_dir: str | Path, *, tois: dict | None = None, allow_unchecked: bool = False,
               start_btjd: float | None = None, days: float = 365.25) -> dict:
    """Write ``ctoi.csv``, ``ctoi.json`` (rows, exclusions, the field-list status) and ``predicted_windows.csv`` for
    one run directory. Raises ValueError if any row fails :func:`check_row`, and before writing anything when
    ``tois`` is None (no TOI duplicate check possible) unless ``allow_unchecked``."""
    if tois is None and not allow_unchecked:
        raise ValueError("no TOI table: the TOI duplicate check cannot be done; nothing written "
                         "(pass allow_unchecked to export rows marked as unchecked)")
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    candidates = json.loads((run_dir / "candidates.json").read_text())
    stars = json.loads((run_dir / "stellar.json").read_text()) if (run_dir / "stellar.json").exists() else {}
    manifest = json.loads((run_dir / "manifest.json").read_text()) if (run_dir / "manifest.json").exists() else {}
    rows, excluded = ctoi_rows(candidates, stars=stars, tois=tois, allow_unchecked=allow_unchecked,
                               run=run_dir.name, config_sha256=manifest.get("config_sha256", ""))
    for r in rows:
        problems = check_row(r)
        if problems:
            raise ValueError(f"export row for TIC {r['tic_id']} fails the schema: {problems}")
    start = btjd_now() if start_btjd is None else start_btjd
    windows = windows_for(rows, start_btjd=start, days=days, stars=stars)
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = [h for _, h, _ in CTOI_FIELDS] + list(EXTRA_FIELDS)
    keys = [k for k, _, _ in CTOI_FIELDS] + list(EXTRA_FIELDS)
    with (out_dir / "ctoi.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(["" if r.get(k) is None else r.get(k) for k in keys])
    if windows:
        with (out_dir / "predicted_windows.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(windows[0]))
            writer.writeheader()
            writer.writerows(windows)
    summary = {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": str(run_dir),
               "ctoi_fields_status": CTOI_FIELDS_STATUS,
               "ctoi_fields": [{"key": k, "header": h, "required": req} for k, h, req in CTOI_FIELDS],
               "submission": "a person submits CTOIs under their own ExoFOP account; exoplan does not",
               "toi_check": "done" if tois is not None else "not done", "rows": rows, "excluded": excluded,
               "windows": {"start_btjd": start, "days": days, "count": len(windows)}}
    (out_dir / "ctoi.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    return summary

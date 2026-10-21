# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""CHEOPS light curves: public Data Reduction Pipeline (DRP) photometry, roll-angle detrending, and a common
timeline with TESS.

**Public data only.** Visits are listed and fetched through DACE (dace.unige.ch, University of Geneva) in its
public mode, with no credentials: SetuHQ never reads a ``.dacerc`` or any key, and it keeps only visits whose
archive record says ``status_published``. Proprietary visits are skipped and never cached. Requests go one at a
time, per target, rate-limited and cached under ``cache/cheops/`` (one file per visit), so a visit is fetched
once. No raw CHEOPS file is shipped with SetuHQ; the tests use a small derived excerpt with its provenance.

**Acknowledgement.** Every output made from CHEOPS data carries :data:`ACKNOWLEDGEMENT` (ESA's text, word for
word), the programme and file key of each visit, the archive's credit line "Credit: ESA, <proposal PI>", the
mission, pipeline and performance papers (:data:`CITATIONS`), DACE's requested acknowledgement
(:data:`DACE_ACKNOWLEDGEMENT`) and :data:`DISCLAIMER`. :func:`credit` builds that block; tests check every
CHEOPS-derived output includes it.

**Detrending** (after pycheops, Maxted et al. 2022, and Poyatos et al. 2025's description of it): the DRP flux is
decorrelated linearly against the spacecraft roll angle's harmonics (sin and cos of φ, 2φ, 3φ), time (linear,
quadratic), the background, the centroid (x, y, their squares and product) and the contamination estimate. Terms
are added one at a time while each lowers the BIC by 2 or more; upward excursions (flares) can be kept out of the
fit so it does not eat them. Bad data: the DRP event flags, non-finite values and 5σ low outliers.

**Time.** DACE gives BJD_TDB − 2,400,000; :func:`to_btjd` converts to BTJD (BJD_TDB − 2,457,000), TESS's time axis,
so CHEOPS and TESS points share one timeline. The two bands differ (CHEOPS 330-1100 nm, TESS 600-1000 nm):
amplitudes are not interchangeable.
"""

from __future__ import annotations

import gzip
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- acknowledgement, credit and disclaimer

# ESA, CHEOPS Guest Observers Programme, Publication guidelines (cosmos.esa.int/web/cheops-guest-observers-programme/
# publication-guidelines), read 2026-10-21: the acknowledgement to include, word for word.
ACKNOWLEDGEMENT = (
    "CHEOPS is an ESA mission in partnership with Switzerland with important contributions to the payload and the "
    "ground segment from Austria, Belgium, France, Germany, Hungary, Italy, Portugal, Spain, Sweden, and the United "
    "Kingdom. The CHEOPS Consortium would like to gratefully acknowledge the support received by all the agencies, "
    "offices, universities, and industries involved. Their flexibility and willingness to explore new approaches "
    "were essential to the success of this mission. CHEOPS data analysed in this article will be made available in "
    "the CHEOPS mission archive (https://cheops.unige.ch/archive_browser/)."
)
# The guidelines' papers to cite: the mission, the Data Reduction Pipeline and the in-flight performance.
CITATIONS = [
    "Benz, W., et al. 2021, Experimental Astronomy, 51, 109 (the CHEOPS mission)",
    "Hoyer, S., et al. 2020, A&A, 635, A24 (the CHEOPS Data Reduction Pipeline)",
    "Fortier, A., et al. 2024, A&A, 687, A302 (CHEOPS in-flight performance)",
]
# ESDC terms and conditions (cosmos.esa.int/web/esdc/terms-and-conditions), the CHEOPS credit line.
CREDIT_TEMPLATE = "Credit: ESA, {pi}"
# DACE (dace.unige.ch/publications/): the acknowledgement it asks of published material that uses it.
DACE_ACKNOWLEDGEMENT = (
    "This publication makes use of The Data & Analysis Center for Exoplanets (DACE), which is a facility based at the "
    "University of Geneva (CH) dedicated to extrasolar planets data visualisation, exchange and analysis. DACE is a "
    "platform of the Swiss National Centre of Competence in Research (NCCR) PlanetS, federating the Swiss expertise "
    "in Exoplanet research. The DACE platform is available at https://dace.unige.ch."
)
DISCLAIMER = ("SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS "
              "mission or the CHEOPS Consortium.")
# ESDC terms: commercial use of ESA archive data needs ESA's prior authorisation.
COMMERCIAL_NOTE = ("ESA's archive terms require prior authorisation (data.licences@esa.int) before any commercial use "
                   "of CHEOPS data, including use that indirectly generates financial gain; SetuHQ's commercial licence "
                   "covers SetuHQ's code, not CHEOPS data.")
TERMS_URLS = {"esa_publication_guidelines": "https://www.cosmos.esa.int/web/cheops-guest-observers-programme/publication-guidelines",
              "esdc_terms": "https://cosmos.esa.int/web/esdc/terms-and-conditions",
              "dace_acknowledgement": "https://dace.unige.ch/publications/"}


def credit(visits: list[dict] | None = None) -> dict:
    """The block every CHEOPS-derived output carries: ESA's acknowledgement, each visit's programme, file key,
    observation id and credit line, the citations, DACE's acknowledgement, the disclaimer and the terms."""
    rows = []
    for v in visits or []:
        pi = v.get("pi_name")
        rows.append({"programme": programme_id(v.get("file_key")), "file_key": v.get("file_key"), "obs_id": v.get("obs_id"),
                     "visit_id": v.get("visit_id"), "pi_name": pi, "drp_version": v.get("data_pipe_version"),
                     "credit": CREDIT_TEMPLATE.format(pi=pi) if pi else "Credit: ESA"})
    return {"acknowledgement": ACKNOWLEDGEMENT, "credits": rows, "citations": list(CITATIONS),
            "dace_acknowledgement": DACE_ACKNOWLEDGEMENT, "disclaimer": DISCLAIMER, "commercial_use": COMMERCIAL_NOTE,
            "terms": dict(TERMS_URLS)}


def credit_text(visits: list[dict] | None = None) -> str:
    """:func:`credit` as plain text, for a page or a terminal."""
    c = credit(visits)
    lines = [c["acknowledgement"], ""]
    for r in c["credits"]:
        lines.append(f"{r['programme']} {r['file_key']} (obs id {r['obs_id']}): {r['credit']}")
    lines += ["", "Cite: " + "; ".join(c["citations"]), "", c["dace_acknowledgement"], "", c["disclaimer"], c["commercial_use"]]
    return "\n".join(lines)


def programme_id(file_key: str | None) -> str | None:
    """'CH_PR100010_TG001501_V0300' -> 'CH_PR100010'."""
    m = re.match(r"(CH_PR\d+)", str(file_key or ""))
    return m.group(1) if m else None


# ---------------------------------------------------------------- the archive (DACE, public mode)

DACE_EPOCH = 2_400_000.0
BTJD_EPOCH = 2_457_000.0
CACHE = "cache/cheops"
LIST_FIELDS = ("visit_id", "obj_id_catname", "file_key", "obs_id", "pi_name", "full_program_name", "data_pipe_version",
               "date_mjd_start", "date_mjd_end", "obs_exptime", "obs_nexp", "obj_mag_cheops", "teff_k", "ra_deg", "dec_deg",
               "status_published", "db_lc_available")


class CheopsUnavailable(RuntimeError):
    """CHEOPS data cannot be reached: the optional client is missing, the network or DACE is down, or the visit is
    not public. The message says which, and what to do."""


def to_btjd(bjd_minus_2400000) -> np.ndarray:
    return np.asarray(bjd_minus_2400000, float) + DACE_EPOCH - BTJD_EPOCH


def _client():
    try:
        import logging

        from dace_query.cheops import Cheops
        logging.getLogger("dace_query").setLevel(logging.ERROR)
    except ImportError as exc:
        raise CheopsUnavailable("fetching CHEOPS light curves needs the optional DACE client: "
                                "pip install 'setuhq[cheops]' (or read a DRP FITS file you downloaded with read_drp_fits)") from exc
    return Cheops


def _throttle():
    from setuhq.sweep import Throttle

    return Throttle(min_interval=1.0)


def _version(fk: str) -> int:
    m = re.search(r"_V(\d+)$", fk or "")
    return int(m.group(1)) if m else 0


def latest_versions(rows: list[dict]) -> list[dict]:
    """One row per visit: the highest DRP processing version of each file key's stem."""
    best: dict[str, dict] = {}
    for r in rows:
        stem = re.sub(r"_V\d+$", "", r.get("file_key") or "")
        if stem not in best or _version(r["file_key"]) > _version(best[stem]["file_key"]):
            best[stem] = r
    return sorted(best.values(), key=lambda r: r.get("date_mjd_start") or 0)


def public_only(rows: list[dict]) -> tuple[list[dict], int]:
    """The rows the archive marks published (public) with a DRP light curve; the count of the others, dropped."""
    keep = [r for r in rows if bool(r.get("status_published")) and bool(r.get("db_lc_available", True))]
    return keep, len(rows) - len(keep)


def list_visits(target: str, *, radius_arcsec: float = 60.0, cache_dir: str | Path = CACHE, refresh: bool = False,
                query=None, resolve=None) -> dict:
    """The public CHEOPS visits of ``target`` (a name Sesame resolves, or 'RA DEC' in degrees): a cone search of
    the archive, latest DRP version per visit, proprietary ones dropped. Cached per target."""
    key = re.sub(r"[^A-Za-z0-9_.+-]+", "_", target.strip())
    path = Path(cache_dir) / "visits" / f"{key}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    if resolve is None:
        def resolve(name):
            from astropy.coordinates import SkyCoord
            import astropy.units as u

            parts = name.split()
            if len(parts) == 2:
                try:
                    return SkyCoord(float(parts[0]) * u.deg, float(parts[1]) * u.deg)
                except ValueError:
                    pass
            return SkyCoord.from_name(name)
    try:
        coord = resolve(target)
    except Exception as exc:  # noqa: BLE001 (name service down or unknown name)
        raise CheopsUnavailable(f"cannot resolve {target!r} to a position: {exc}") from exc
    if query is None:
        Cheops = _client()

        def query(c, r):
            import astropy.units as u
            from astropy.coordinates import Angle

            return Cheops.query_region(sky_coord=c, angle=Angle(r * u.arcsec), output_format="dict")
    from setuhq.sweep import polite

    try:
        raw = polite(query, coord, radius_arcsec, throttle=_throttle(), tries=3)
    except CheopsUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CheopsUnavailable(f"the CHEOPS archive (DACE) did not answer for {target!r}: {exc}. "
                                "Try again later, or read a DRP FITS file with read_drp_fits") from exc
    rows = _rows(raw)
    public, dropped = public_only(rows)
    visits = [{k: _plain(r.get(k)) for k in LIST_FIELDS} for r in latest_versions(public)]
    out = {"target": target, "ra_deg": float(coord.ra.deg), "dec_deg": float(coord.dec.deg), "radius_arcsec": radius_arcsec,
           "visits": visits, "n_public": len(visits), "n_not_public_dropped": dropped,
           "source": "DACE public mode (dace.unige.ch), CHEOPS DRP light curves", **credit(visits)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out


def _rows(raw) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        keys = list(raw)
        n = len(raw[keys[0]]) if keys else 0
        return [{k: raw[k][i] for k in keys} for i in range(n)]
    if hasattr(raw, "to_dict"):
        return raw.to_dict("records")
    return list(raw)


def _plain(v):
    if isinstance(v, np.generic):
        return v.item()
    return v


ARRAYS = {"obj_date_bjd_vect": "bjd", "photom_flux_vect": "flux", "photom_flux_vect_err": "flux_err",
          "photom_roll_angle_vect": "roll", "photom_centroid_x_vect": "x", "photom_centroid_y_vect": "y",
          "photom_background_vect": "bg", "photom_conta_lc_vect": "contam", "photom_event_vect": "event"}
FLAG_ARRAYS = ("photom_event_saa_flag", "photom_event_temp_flag", "photom_event_earth_flag", "photom_event_moon_flag",
               "photom_event_sun_flag", "photom_event_cosmic_flag")


@dataclass
class CheopsVisit:
    """One visit's DRP photometry (aperture as fetched), on BTJD, with its archive record."""

    meta: dict
    time: np.ndarray            # BTJD (BJD_TDB - 2457000)
    flux: np.ndarray
    flux_err: np.ndarray
    roll: np.ndarray            # degrees
    x: np.ndarray
    y: np.ndarray
    bg: np.ndarray
    contam: np.ndarray
    flags: np.ndarray           # non-zero: a DRP event or flag on that cadence
    aperture: str = "default"
    extra: dict = field(default_factory=dict)

    @property
    def cadence_s(self) -> float:
        return float(np.median(np.diff(self.time)) * 86400.0) if self.time.size > 1 else float("nan")

    def provenance(self) -> dict:
        return {"mission": "CHEOPS", "product": "DRP light curve", "aperture": self.aperture, "time_unit": "BTJD",
                **{k: self.meta.get(k) for k in ("file_key", "obs_id", "visit_id", "pi_name", "data_pipe_version",
                                                 "obj_id_catname")},
                "programme": programme_id(self.meta.get("file_key")), "n_points": int(self.time.size),
                "sha256": self.extra.get("sha256"), **credit([self.meta])}


def _visit_from_arrays(meta: dict, arr: dict, aperture: str) -> CheopsVisit:
    flags = np.zeros(len(arr["obj_date_bjd_vect"]), dtype=np.int64)
    for i, k in enumerate(("photom_event_vect",) + FLAG_ARRAYS):
        if k in arr:
            v = np.nan_to_num(np.asarray(arr[k], float))
            flags |= (v != 0).astype(np.int64) << i
    get = lambda k: np.asarray(arr.get(k, np.full(flags.size, np.nan)), float)  # noqa: E731
    return CheopsVisit(meta=meta, time=to_btjd(get("obj_date_bjd_vect")), flux=get("photom_flux_vect"),
                       flux_err=get("photom_flux_vect_err"), roll=get("photom_roll_angle_vect"),
                       x=get("photom_centroid_x_vect"), y=get("photom_centroid_y_vect"), bg=get("photom_background_vect"),
                       contam=get("photom_conta_lc_vect"), flags=flags, aperture=aperture)


def fetch_visit(visit: dict, *, aperture: str = "default", cache_dir: str | Path = CACHE, offline: bool = False,
                fetch=None) -> CheopsVisit:
    """One public visit's DRP light curve (from the cache when there, else from DACE, politely). ``visit`` is a row
    of :func:`list_visits`. A visit the archive does not mark public is refused before any request."""
    if not visit.get("status_published"):
        raise CheopsUnavailable(f"{visit.get('file_key')}: not marked public in the archive; SetuHQ fetches public data only")
    fk = visit["file_key"]
    path = Path(cache_dir) / "visits" / f"{fk}_{aperture}.json.gz"
    if path.exists():
        payload = json.loads(gzip.decompress(path.read_bytes()))
    else:
        if offline:
            raise CheopsUnavailable(f"{fk}: not in the cache and offline")
        if fetch is None:
            Cheops = _client()

            def fetch(name, file_key, ap):
                return Cheops.get_lightcurve(name, aperture=ap, filters={"file_key": {"equal": [file_key]}})
        from setuhq.sweep import polite

        try:
            raw = polite(fetch, visit.get("obj_id_catname"), fk, aperture, throttle=_throttle(), tries=3)
        except Exception as exc:  # noqa: BLE001
            raise CheopsUnavailable(f"{fk}: DACE did not return the light curve: {exc}") from exc
        keep = list(ARRAYS) + list(FLAG_ARRAYS)
        arr = {k: np.asarray(raw[k]).tolist() for k in keep if k in raw}
        if not arr.get("obj_date_bjd_vect"):
            raise CheopsUnavailable(f"{fk}: DACE returned no photometry")
        payload = {"meta": {k: _plain(visit.get(k)) for k in LIST_FIELDS}, "aperture": aperture, "arrays": arr}
        path.parent.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(json.dumps(payload).encode(), mtime=0)
        path.write_bytes(data)
    import hashlib

    v = _visit_from_arrays(payload["meta"], payload["arrays"], payload.get("aperture", aperture))
    v.extra["sha256"] = hashlib.sha256(json.dumps(payload["arrays"], sort_keys=True).encode()).hexdigest()
    v.extra["cache"] = str(path)
    return v


def read_drp_fits(path: str | Path, meta: dict | None = None) -> CheopsVisit:
    """A CHEOPS DRP light-curve FITS file already on disk (``CH_PR*_SCI_COR_Lightcurve-*.fits``), offline."""
    from astropy.io import fits

    path = Path(path)
    with fits.open(path) as hdul:
        h0, d = hdul[0].header, hdul[1].data
        names = {n.upper(): n for n in d.columns.names}

        def col(*cands):
            for c in cands:
                if c in names:
                    return np.asarray(d[names[c]], float)
            return np.full(len(d), np.nan)

        bjd = col("BJD_TIME")
        flags = np.zeros(len(d), np.int64)
        for i, c in enumerate(("STATUS", "EVENT")):
            if c in names:
                flags |= (np.nan_to_num(np.asarray(d[names[c]], float)) != 0).astype(np.int64) << i
        meta = {"file_key": h0.get("FILENAME") or path.stem, "obs_id": h0.get("OBSID"), "pi_name": h0.get("PI_NAME"),
                "obj_id_catname": h0.get("TARGNAME"), "data_pipe_version": h0.get("PIPE_VER"),
                "status_published": True, **(meta or {})}
    t = bjd - BTJD_EPOCH if np.nanmedian(bjd) > 2_000_000 else bjd
    return CheopsVisit(meta=meta, time=t, flux=col("FLUX"), flux_err=col("FLUXERR"), roll=col("ROLL_ANGLE"),
                       x=col("CENTROID_X"), y=col("CENTROID_Y"), bg=col("BACKGROUND"), contam=col("CONTA_LC"), flags=flags,
                       aperture="as delivered")


# ---------------------------------------------------------------- detrending


CANDIDATE_TERMS = ("sin1", "cos1", "sin2", "cos2", "sin3", "cos3", "t", "t2", "bg", "x", "y", "x2", "y2", "xy", "contam")


def bad_data(v: CheopsVisit, *, low_sigma: float = 5.0) -> np.ndarray:
    """True where a cadence is unusable: a DRP event or flag, a non-finite value, or a low outlier (5σ below the
    running median; upward excursions are kept, they may be flares)."""
    from setuhq.flares import _robust_sigma

    bad = (v.flags != 0) | ~np.isfinite(v.time) | ~np.isfinite(v.flux) | ~np.isfinite(v.roll)
    ok = ~bad
    if ok.sum() > 10:
        from scipy.ndimage import median_filter

        med = np.full(v.flux.size, np.nan)
        med[ok] = median_filter(v.flux[ok], size=min(31, ok.sum() // 2 * 2 - 1), mode="nearest")
        r = v.flux - med
        s = _robust_sigma(r[ok])
        bad |= ok & (r < -low_sigma * s)
    return bad


def _design(v: CheopsVisit, terms) -> np.ndarray:
    phi = np.deg2rad(v.roll)
    tt = v.time - np.nanmean(v.time)
    span = np.nanmax(np.abs(tt)) or 1.0

    def z(a):
        a = np.asarray(a, float)
        s = np.nanstd(a)
        return (a - np.nanmean(a)) / s if s > 0 else np.zeros_like(a)

    cols = {"sin1": np.sin(phi), "cos1": np.cos(phi), "sin2": np.sin(2 * phi), "cos2": np.cos(2 * phi),
            "sin3": np.sin(3 * phi), "cos3": np.cos(3 * phi), "t": tt / span, "t2": (tt / span) ** 2, "bg": z(v.bg),
            "x": z(v.x), "y": z(v.y), "x2": z(v.x) ** 2, "y2": z(v.y) ** 2, "xy": z(v.x) * z(v.y), "contam": z(v.contam)}
    return np.column_stack([np.ones(v.time.size)] + [np.nan_to_num(cols[k]) for k in terms])


def _bic(resid, k):
    n = resid.size
    return n * math.log(max(float(np.sum(resid ** 2)) / n, 1e-300)) + k * math.log(n)


def detrend_visit(v: CheopsVisit, *, terms=None, protect_upward: bool = True, clip_sigma: float = 4.0,
                  min_delta_bic: float = 2.0, signal=None) -> dict:
    """Decorrelate one visit (see the module docstring). ``terms`` None selects by BIC from
    :data:`CANDIDATE_TERMS`; a list fixes them. ``signal`` (relative flux, mean 1, one value per cadence) is an
    astrophysical model (for example a pulsator's sinusoids from TESS) divided out before the systematics are
    fitted and kept in the output, so the decorrelation does not absorb it. Returns the detrended flux (flux / model), the model, the chosen
    terms and coefficients, the bad-data mask, and the scatter before and after."""
    from setuhq.flares import _robust_sigma

    bad = bad_data(v)
    ok = ~bad
    f0 = v.flux / np.nanmedian(v.flux[ok])
    sig = np.ones_like(f0) if signal is None else np.asarray(signal, float)
    f = f0 / sig
    fit_mask = ok.copy()
    if protect_upward:
        r = f - np.nanmedian(f[ok])
        s = _robust_sigma(r[ok])
        fit_mask &= ~(r > 3.0 * s)

    def solve(names, mask):
        A = _design(v, names)
        for _ in range(3):
            coef, *_ = np.linalg.lstsq(A[mask], f[mask], rcond=None)
            res = f - A @ coef
            s = _robust_sigma(res[mask])
            new = mask & (np.abs(res) < clip_sigma * s)
            if new.sum() == mask.sum():
                break
            mask = new
        return coef, A @ coef, mask

    if terms is None:
        chosen: list[str] = []
        coef, model, m = solve(chosen, fit_mask)
        cur = _bic((f - model)[m], 1)
        while True:
            best = None
            for k in CANDIDATE_TERMS:
                if k in chosen:
                    continue
                c2, mod2, m2 = solve(chosen + [k], m)
                b = _bic((f - mod2)[m], len(chosen) + 2)
                if best is None or b < best[0]:
                    best = (b, k)
            if best is None or cur - best[0] < min_delta_bic:
                break
            chosen.append(best[1])
            cur = best[0]
        terms = chosen
    coef, model, m = solve(list(terms), fit_mask)
    det = f0 / model
    det[bad] = np.nan
    return {"time": v.time, "flux": det, "flux_err": v.flux_err / np.nanmedian(v.flux[ok]), "model": model, "bad": bad,
            "terms": list(terms), "coefficients": dict(zip(["const"] + list(terms), map(float, coef))),
            "rms_raw_ppm": float(np.nanstd(f0[ok]) * 1e6), "signal_model": signal is not None, "rms_detrended_ppm": float(np.nanstd(det[ok]) * 1e6),
            "n_bad": int(bad.sum()), "n_used_in_fit": int(m.sum()), "provenance": v.provenance()}


# ---------------------------------------------------------------- one timeline with TESS


def common_timeline(cheops: list[dict] | None = None, tess: list | None = None) -> dict:
    """CHEOPS (detrended, :func:`detrend_visit` results) and TESS (:class:`~setuhq.lightcurve.LightCurve` with
    BTJD time) on one BTJD axis, each segment normalised to its own median and labelled by mission and band. The
    bands differ, so amplitudes are compared with care; the time axis is common (both BJD_TDB)."""
    segs = []
    for d in cheops or []:
        ok = np.isfinite(d["flux"])
        segs.append({"mission": "CHEOPS", "band": "CHEOPS (330-1100 nm)", "time": d["time"][ok].tolist(),
                     "flux": (d["flux"][ok] / np.median(d["flux"][ok])).tolist(), "label": d["provenance"].get("file_key")})
    for lc in tess or []:
        if lc.provenance.get("time_unit") not in (None, "BTJD"):
            raise ValueError("TESS light curves must be on BTJD")
        segs.append({"mission": "TESS", "band": "TESS (600-1000 nm)", "time": np.asarray(lc.time).tolist(),
                     "flux": (np.asarray(lc.flux) / np.median(lc.flux)).tolist(), "label": f"sector {lc.provenance.get('sector')}"})
    segs.sort(key=lambda s: s["time"][0] if s["time"] else 0)
    out = {"time_unit": "BTJD (BJD_TDB - 2457000)", "segments": segs}
    if cheops:
        out.update(credit([d["provenance"] for d in cheops]))
    return out


def get_cheops_lightcurve(target: str, *, file_key: str | None = None, max_visits: int = 3, detrend: bool = True,
                          cache_dir: str | Path = CACHE, offline: bool = False) -> dict:
    """The public CHEOPS visits of a target, fetched (cached) and detrended: the end-to-end call behind
    ``setuhq cheops`` and the MCP tool. ``file_key`` picks one visit; otherwise the first ``max_visits``."""
    if offline:
        lv_path = Path(cache_dir) / "visits" / (re.sub(r"[^A-Za-z0-9_.+-]+", "_", target.strip()) + ".json")
        if not lv_path.exists():
            raise CheopsUnavailable(f"{target!r}: no cached visit list and offline")
        listing = json.loads(lv_path.read_text())
    else:
        listing = list_visits(target, cache_dir=cache_dir)
    visits = listing["visits"]
    if file_key:
        visits = [v for v in visits if v["file_key"] == file_key or v["file_key"].startswith(file_key)]
        if not visits:
            raise CheopsUnavailable(f"{target!r}: no public visit {file_key!r}")
    out = []
    for vrow in visits[:max_visits]:
        v = fetch_visit(vrow, cache_dir=cache_dir, offline=offline)
        d = detrend_visit(v) if detrend else None
        out.append({"provenance": v.provenance(), "cadence_s": v.cadence_s,
                    "detrend": None if d is None else {k: d[k] for k in ("terms", "coefficients", "rms_raw_ppm",
                                                                       "rms_detrended_ppm", "n_bad", "n_used_in_fit")},
                    "_visit": v, "_detrended": d})
    return {"target": target, "n_public_visits": listing["n_public"], "n_not_public_dropped": listing["n_not_public_dropped"],
            "visits": out, **credit([o["provenance"] for o in out])}

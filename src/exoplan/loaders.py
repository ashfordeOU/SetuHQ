"""Loaders that turn archive files into :class:`~exoplan.lightcurve.LightCurve` objects.

Supported sources:

* TESS SPOC light curves, fetched from MAST through ``lightkurve`` (optional extra), or read from a SPOC
  ``*_lc.fits`` file on disk (:func:`load_spoc_file`). Both record the SPOC crowding keywords CROWDSAP and FLFRCSAP.
* CHEOPS light-curve FITS files (``SCI_COR_Lightcurve`` style products from the
  CHEOPS archive, or any FITS table with time, flux and flux error columns).
* Plain CSV files with ``time``, ``flux`` and optionally ``flux_err`` columns.

Each loader keeps the time system of its source. Nothing is converted, so
BTJD (TESS) and BJD_TDB (CHEOPS) are never mixed inside one object.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from exoplan.lightcurve import LightCurve

CHEOPS_TIME_COLUMNS = ("BJD_TIME", "TIME")
CHEOPS_FLUX_COLUMNS = ("FLUX",)
CHEOPS_ERR_COLUMNS = ("FLUXERR", "FLUX_ERR", "FLUXERROR")
CHEOPS_FLAG_COLUMNS = ("DATA_FLAG", "FLAG")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _plain(values) -> np.ndarray:
    """Convert astropy quantities and masked arrays to a plain float array with NaN for masked entries."""
    values = getattr(values, "value", values)
    return np.asarray(np.ma.filled(np.ma.asarray(values, dtype=float), np.nan), dtype=float)


def load_tess(
    target: str,
    sectors=None,
    *,
    author: str = "SPOC",
    exptime: int = 120,
    flux_column: str = "pdcsap_flux",
    download_dir: str | None = None,
) -> list[LightCurve]:
    """Download TESS light curves for ``target`` (for example ``"TIC 261136679"``), one per sector.

    Points whose TESS quality flag is non-zero are dropped. The time axis is BTJD.
    """
    try:
        import lightkurve as lk
    except ImportError as exc:
        raise ImportError("TESS loading needs the optional extra: pip install 'exoplan[tess]'") from exc

    search = lk.search_lightcurve(target, author=author, exptime=exptime)
    if len(search) == 0:
        raise LookupError(f"no {author} {exptime}s light curves found for {target!r}")

    rows = list(range(len(search)))
    if sectors is not None:
        wanted = {int(s) for s in sectors}
        rows = [i for i, seq in enumerate(search.table["sequence_number"]) if int(seq) in wanted]
        if not rows:
            raise LookupError(f"{target!r} has no requested sectors {sorted(wanted)}")

    curves: list[LightCurve] = []
    for i in rows:
        lc = search[i].download(flux_column=flux_column, download_dir=download_dir)
        time = _plain(lc.time)
        flux = _plain(lc.flux)
        flux_err = _plain(lc.flux_err)
        quality = _plain(lc.quality)
        good = (quality == 0) & np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
        sector = int(lc.sector)
        median = np.median(flux[good])
        flux = flux / median
        flux_err = flux_err / median
        curves.append(
            LightCurve(
                target=target,
                mission="TESS",
                time=time[good],
                flux=flux[good],
                flux_err=flux_err[good],
                provenance={
                    "source": "MAST",
                    "author": author,
                    "sector": sector,
                    "exptime_s": exptime,
                    "flux_column": flux_column,
                    "time_unit": "BTJD",
                    "lightkurve_version": lk.__version__,
                    **_file_provenance(lc),
                    **spoc_crowding(lc),
                },
            )
        )
    return curves


def _file_provenance(lc) -> dict:
    """The downloaded FITS file's name and sha256, so a later rebuild can show it read the same bytes."""
    path = (getattr(lc, "meta", None) or {}).get("FILENAME")
    if not path or not Path(path).exists():
        return {}
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {"file": Path(path).name, "file_sha256": digest}


CROWDING_KEYS = {"CROWDSAP": "crowdsap", "FLFRCSAP": "flfrcsap"}


def spoc_crowding(lc) -> dict:
    """CROWDSAP (the fraction of the aperture's flux that comes from the target) and FLFRCSAP (the fraction of the
    target's flux inside the aperture) from a SPOC light curve's header. lightkurve copies the header keywords into
    ``lc.meta``; when they are missing there, the downloaded file's LIGHTCURVE extension is read. Missing values are
    left out, never guessed."""
    meta = getattr(lc, "meta", None) or {}
    out = {}
    for key, name in CROWDING_KEYS.items():
        value = meta.get(key)
        if value is not None:
            out[name] = float(value)
    if len(out) < len(CROWDING_KEYS) and meta.get("FILENAME") and Path(meta["FILENAME"]).exists():
        from astropy.io import fits

        with fits.open(meta["FILENAME"]) as hdul:
            header = hdul[1].header
            for key, name in CROWDING_KEYS.items():
                if key in header and name not in out:
                    out[name] = float(header[key])
    return out


def load_spoc_file(path: str | Path, *, target: str | None = None, flux_column: str = "PDCSAP_FLUX") -> LightCurve:
    """Load a SPOC light-curve FITS file already on disk (``*_lc.fits``), offline and without lightkurve.

    The same choices as :func:`load_tess`: points with a non-zero quality flag or non-finite values are dropped, the
    flux is normalised to its median, the time axis is BTJD, and CROWDSAP and FLFRCSAP are recorded.
    """
    from astropy.io import fits

    path = Path(path)
    with fits.open(path) as hdul:
        primary, header, data = hdul[0].header, hdul[1].header, hdul[1].data
        time = np.asarray(data["TIME"], float)
        flux = np.asarray(data[flux_column], float)
        flux_err = np.asarray(data[flux_column + "_ERR"], float)
        quality = np.asarray(data["QUALITY"], int)
        crowd = {name: float(header[key]) for key, name in CROWDING_KEYS.items() if key in header}
        sector = primary.get("SECTOR")
        tic = primary.get("TICID")
    good = (quality == 0) & np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
    if not good.any():
        raise ValueError(f"{path.name}: no usable points after quality masking")
    median = np.median(flux[good])
    return LightCurve(
        target=target or (f"TIC {tic}" if tic is not None else path.stem),
        mission="TESS",
        time=time[good],
        flux=flux[good] / median,
        flux_err=flux_err[good] / median,
        provenance={"source": "SPOC file", "author": "SPOC", "sector": int(sector) if sector is not None else None,
                    "flux_column": flux_column.lower(), "time_unit": "BTJD", "file": path.name,
                    "file_sha256": sha256_file(path), **crowd},
    )


def _first_present(names: dict[str, str], candidates) -> str | None:
    for candidate in candidates:
        if candidate in names:
            return names[candidate]
    return None


def load_cheops(path: str | Path, *, target: str | None = None, flux_column: str | None = None) -> LightCurve:
    """Load a CHEOPS light-curve FITS file.

    The first binary table HDU containing time, flux and flux-error columns is used.
    Points with a non-zero data flag are dropped. Column names differ between
    CHEOPS products, so ``flux_column`` can override the default ``FLUX`` column.
    Flux is normalised to its median so it is relative, like the other missions.
    """
    from astropy.io import fits

    path = Path(path)
    with fits.open(path) as hdul:
        table_hdu = None
        names: dict[str, str] = {}
        for hdu in hdul[1:]:
            if not isinstance(hdu, fits.BinTableHDU):
                continue
            names = {n.upper(): n for n in hdu.columns.names}
            if flux_column is not None:
                flux_col = names.get(flux_column.upper())
            else:
                flux_col = _first_present(names, CHEOPS_FLUX_COLUMNS)
            time_col = _first_present(names, CHEOPS_TIME_COLUMNS)
            err_col = _first_present(names, CHEOPS_ERR_COLUMNS)
            if time_col and flux_col and err_col:
                table_hdu = hdu
                break
        if table_hdu is None:
            raise ValueError(f"{path.name}: no table with time, flux and flux-error columns")

        data = table_hdu.data
        time = np.asarray(data[time_col], dtype=float)
        flux = np.asarray(data[flux_col], dtype=float)
        flux_err = np.asarray(data[err_col], dtype=float)
        good = np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
        flag_col = _first_present(names, CHEOPS_FLAG_COLUMNS)
        if flag_col is not None:
            good &= np.asarray(data[flag_col]) == 0
        if not good.any():
            raise ValueError(f"{path.name}: no usable points after quality masking")

        median = np.median(flux[good])
        object_name = hdul[0].header.get("OBJECT", path.stem)

    return LightCurve(
        target=target or str(object_name),
        mission="CHEOPS",
        time=time[good],
        flux=flux[good] / median,
        flux_err=flux_err[good] / median,
        provenance={
            "source": path.name,
            "sha256": sha256_file(path),
            "time_column": time_col,
            "flux_column": flux_col,
            "error_column": err_col,
            "flag_column": flag_col,
            "time_unit": "BJD_TDB-2457000 (as delivered)",
        },
    )


def load_csv(path: str | Path, *, target: str, mission: str = "custom") -> LightCurve:
    """Load ``time,flux[,flux_err]`` from a CSV file with a header row."""
    path = Path(path)
    table = np.genfromtxt(path, delimiter=",", names=True, dtype=float, encoding="utf-8")
    columns = {name.lower(): name for name in table.dtype.names}
    if "time" not in columns or "flux" not in columns:
        raise ValueError(f"{path.name}: CSV needs 'time' and 'flux' columns")
    time = np.asarray(table[columns["time"]], dtype=float)
    flux = np.asarray(table[columns["flux"]], dtype=float)
    median = np.nanmedian(flux)
    flux = flux / median
    if "flux_err" in columns:
        flux_err = np.asarray(table[columns["flux_err"]], dtype=float) / median
    else:
        flux_err = np.full_like(flux, np.nanstd(flux))
    return LightCurve(
        target=target,
        mission=mission,
        time=time,
        flux=flux,
        flux_err=flux_err,
        provenance={"source": path.name, "sha256": sha256_file(path), "time_unit": "as supplied"},
    )

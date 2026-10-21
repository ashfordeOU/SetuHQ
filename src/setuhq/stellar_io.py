# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Inputs for the stellar tools (flares, pulsations): a TESS light curve from a TIC id, a SPOC FITS file or a CSV,
and the star's TIC values (Teff, radius, TESS magnitude, distance) for flare energies.

TESS files are fetched from MAST with lightkurve (``pip install 'setuhq[tess]'``) into ``cache/mast/stellar/`` and
read with :func:`setuhq.loaders.load_spoc_file`: PDCSAP flux, quality-0 cadences, normalised per sector, BTJD. The
TIC values come from :func:`setuhq.stellar.tic_params` (cached under ``cache/tic/``), plus the TIC distance.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

CACHE = "cache"


def parse_tic(target: str) -> int | None:
    m = re.fullmatch(r"\s*(?:TIC)?\s*(\d{3,})\s*", str(target), re.I)
    return int(m.group(1)) if m else None


def tic_star(tic: int, cache_root: str | Path = CACHE, *, offline: bool = False) -> dict | None:
    """Teff, radius, TESS magnitude and distance (pc) from TIC v8.2, or None. Missing values stay None."""
    from setuhq.stellar import tic_params

    p = tic_params(int(tic), Path(cache_root) / "tic", offline=offline)
    if p is None:
        return None
    path = Path(cache_root) / "tic" / f"{int(tic)}_distance.json"
    if path.exists():
        dist = json.loads(path.read_text()).get("distance_pc")
    elif offline:
        dist = None
    else:
        dist = None
        try:
            from astroquery.mast import Catalogs

            t = Catalogs.query_criteria(catalog="TIC", ID=int(tic))
            if len(t) and "d" in t.colnames and np.isfinite(float(t[0]["d"])):
                dist = float(t[0]["d"])
        except Exception:  # noqa: BLE001 (no distance: said so by the energy record)
            dist = None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tic": int(tic), "distance_pc": dist}))
    return {"tic": int(tic), "teff": p.get("teff"), "radius": p.get("radius"), "tmag": p.get("tmag"),
            "distance_pc": dist, "source": p.get("source", "TESS Input Catalog v8.2 (MAST)")}


def fetch_tess(tic: int, sectors=None, *, exptime: int = 120, cache_root: str | Path = CACHE) -> list:
    """SPOC light curves of a TIC star (one per sector), downloaded once into ``cache/mast/stellar``."""
    from setuhq.loaders import load_spoc_file

    folder = Path(cache_root) / "mast" / "stellar" / str(int(tic))
    index = folder / f"index_{exptime}.json"
    files: dict[str, str] = json.loads(index.read_text()) if index.exists() else {}
    want = None if sectors is None else {int(s) for s in sectors}
    have = {int(s) for s in files}
    if want is None or not want <= have:
        try:
            import lightkurve as lk
        except ImportError as exc:
            raise ImportError("TESS downloads need lightkurve: pip install 'setuhq[tess]'") from exc
        res = lk.search_lightcurve(f"TIC {int(tic)}", author="SPOC", exptime=exptime)
        if len(res) == 0:
            raise LookupError(f"no SPOC {exptime}-s light curves for TIC {tic}")
        for i in range(len(res)):
            sec = int(res.table["sequence_number"][i])
            if (want is not None and sec not in want) or str(sec) in files:
                continue
            lc = res[i].download(download_dir=str(folder / "lk"))
            files[str(sec)] = str(Path(lc.meta["FILENAME"]).resolve().relative_to(folder.resolve()))
        folder.mkdir(parents=True, exist_ok=True)
        index.write_text(json.dumps(files, indent=1))
    chosen = sorted(int(s) for s in files if want is None or int(s) in want)
    if not chosen:
        raise LookupError(f"TIC {tic} has none of the sectors {sorted(want or [])} at {exptime} s")
    return [load_spoc_file(folder / files[str(s)], target=f"TIC {int(tic)}") for s in chosen]


def load_input(target: str, *, sectors=None, exptime: int = 120, cache_root: str | Path = CACHE) -> tuple[list, dict | None, list[dict]]:
    """A TIC id, a SPOC ``*_lc.fits`` or a CSV (time, flux[, flux_err]) as light curves, the star's TIC values (TIC
    only) and the provenance of each input."""
    from setuhq.loaders import load_csv, load_spoc_file

    p = Path(target)
    if p.exists():
        if p.suffix.lower() in (".fits", ".fit", ".gz") and "fits" in p.name.lower():
            lc = load_spoc_file(p)
        else:
            lc = load_csv(p, target=p.stem)
        return [lc], None, [{"path": p.name, **{k: lc.provenance.get(k) for k in ("sha256", "file_sha256", "sector")}}]
    tic = parse_tic(target)
    if tic is None:
        raise ValueError(f"{target!r}: neither a file nor a TIC id")
    lcs = fetch_tess(tic, sectors, exptime=exptime, cache_root=cache_root)
    star = tic_star(tic, cache_root)
    return lcs, star, [{"path": lc.provenance.get("file"), "sha256": lc.provenance.get("file_sha256"),
                        "sector": lc.provenance.get("sector")} for lc in lcs]


# The code a stellar result depends on; its fingerprint is stored with every output (as the sweep's is).
CODE_FILES = ["flares.py", "pulsations.py", "cheops.py", "passbands.py", "stellar_io.py"]


def code_fingerprint() -> str:
    """sha256 over :data:`CODE_FILES` (path and canonical text, as :func:`setuhq.starsearch.code_fingerprint`)."""
    from setuhq.starsearch import _fingerprint

    return _fingerprint(CODE_FILES)


def provenance(inputs: list[dict], **extra) -> dict:
    from datetime import datetime, timezone

    from setuhq import __version__

    return {"setuhq_version": __version__, "code_fingerprint": code_fingerprint(), "code_files": CODE_FILES,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "inputs": inputs, **extra}

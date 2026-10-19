"""Stellar parameters for the transit fit: Teff and log g (limb darkening) and the density (ρ★ check).

From the TESS Input Catalog (TIC v8.2, via MAST), cached per star under ``cache/tic/`` so a re-run needs no
network. A run may also store them (``stellar.json`` in the run directory) or a config may give them; those
take precedence. Missing values stay ``None``; nothing is guessed.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

RHO_SUN = 1.40977  # g/cm³: the IAU nominal solar mass in a sphere of the nominal solar radius
FIELDS = {"Teff": "teff", "e_Teff": "teff_err", "logg": "logg", "e_logg": "logg_err", "rad": "radius", "e_rad": "radius_err",
          "mass": "mass", "e_mass": "mass_err", "rho": "rho_solar", "e_rho": "rho_solar_err", "Tmag": "tmag", "contratio": "contratio"}


def tic_id(target: str) -> int | None:
    m = re.fullmatch(r"\s*TIC\s*(\d+)\s*", str(target or ""), re.I)
    return int(m.group(1)) if m else None


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def with_density(p: dict) -> dict:
    """Add ρ★ in g/cm³ (``rho``, ``rho_err``) from the TIC's solar-unit density, or from mass and radius."""
    p = dict(p)
    if p.get("rho_solar") is not None:
        p["rho"] = p["rho_solar"] * RHO_SUN
        p["rho_err"] = p["rho_solar_err"] * RHO_SUN if p.get("rho_solar_err") is not None else None
    elif p.get("mass") and p.get("radius"):
        p["rho"] = p["mass"] / p["radius"] ** 3 * RHO_SUN
        p["rho_err"] = None
    return p


def tic_params(tic: int, cache_dir: str | Path | None = "cache/tic", *, offline: bool = False) -> dict | None:
    """TIC values for one star (``None`` when the star is unknown or MAST cannot be reached and nothing is cached)."""
    path = Path(cache_dir) / f"{tic}.json" if cache_dir else None
    if path and path.exists():
        return json.loads(path.read_text())
    if offline:
        return None
    try:
        from astroquery.mast import Catalogs

        table = Catalogs.query_criteria(catalog="TIC", ID=int(tic))
    except Exception:  # noqa: BLE001 (network or service failure: no values, said so by the caller)
        return None
    if len(table) == 0:
        return None
    row = table[0]
    out = {"tic": int(tic), "source": "TESS Input Catalog v8.2 (MAST)"}
    for col, key in FIELDS.items():
        out[key] = _num(row[col]) if col in table.colnames else None
    out = with_density(out)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1))
    return out

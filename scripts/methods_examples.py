#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Stored catalogue values for the Methods worked examples and the Galaxy's system views.

Reads an exoplanet.eu catalogue CSV and writes ``docs/results/methods_examples.json``: for each named
planet, the columns the explainers draw from (period, semi-major axis, eccentricity, inclination,
masses, radii, the star's Teff, radius, mass and spectral type, distance, impact parameter, the
published RV semi-amplitude K, the molecules exoplanet.eu lists), exactly as stored. A missing value
stays null. The notable planets of docs/results/notable_planets.json are always included.

    python scripts/methods_examples.py --csv exoplanet_eu.csv --fetched-at 2026-10-18T20:53:00Z
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

OUT = Path("docs/results/methods_examples.json")
NOTABLE = Path("docs/results/notable_planets.json")
EXAMPLES = ["51 Peg b", "pi Men c", "WASP-39 b", "HD 209458 b", "TRAPPIST-1 e", "Proxima Centauri b", "HR 8799 b",
            "HR 8799 c", "HR 8799 d", "HR 8799 e", "OGLE-2005-BLG-390L b", "Gaia-4 b", "beta Pic b", "HD 189733 Ab",
            "K2-18 b", "GJ 896 Ab", "GJ 1214 b", "HD 80606 b", "Kepler-16 (AB)b", "TRAPPIST-1 b",
            "Kepler-9 b", "Kepler-9 c", "TOI-700 d"]
NUM = ["orbital_period", "semi_major_axis", "eccentricity", "inclination", "omega", "mass", "mass_sini", "radius",
       "impact_parameter", "k", "temp_calculated", "star_teff", "star_radius", "star_mass", "star_distance", "mag_v"]
TEXT = ["star_name", "star_sp_type", "detection_type", "molecules"]


def _num(v):
    v = (v or "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", required=True)
    ap.add_argument("--fetched-at", required=True)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    names = list(EXAMPLES)
    if NOTABLE.exists():
        names += [e["name"] for e in json.loads(NOTABLE.read_text())["planets"] if e["name"] not in names]
    rows = {r["name"].strip(): r for r in csv.DictReader(open(args.csv, encoding="utf-8"))}
    out, missing = {}, []
    for n in names:
        r = rows.get(n)
        if r is None:
            missing.append(n)
            continue
        e = {c: _num(r.get(c)) for c in NUM}
        e.update({c: (r.get(c) or "").strip() or None for c in TEXT})
        e["discovered"] = int(_num(r.get("discovered"))) if _num(r.get("discovered")) else None
        out[n] = e
    doc = {"source": "The Extrasolar Planets Encyclopaedia (exoplanet.eu)", "url": "https://exoplanet.eu/catalog/",
           "fetched_at": args.fetched_at,
           "units": {"orbital_period": "day", "semi_major_axis": "AU", "inclination": "degree", "omega": "degree",
                     "mass": "Jupiter mass", "mass_sini": "Jupiter mass (m sin i)", "radius": "Jupiter radius",
                     "k": "m/s", "temp_calculated": "K", "star_teff": "K", "star_radius": "solar radius",
                     "star_mass": "solar mass", "star_distance": "parsec"},
           "missing": missing, "planets": out}
    Path(args.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    print(f"{args.out}: {len(out)} planets; not in the CSV: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

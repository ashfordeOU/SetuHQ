#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Population figures for the Methods chapter "Population", computed from the exoplanet.eu CSV.

* Radius valley: a histogram of planet radii (in Earth radii, log bins) for planets with a stored radius
  and an orbital period under 100 days, the sample range Fulton et al. 2017 used.
* Habitable zone: for every planet with a stored star Teff (2600–7200 K, the Kopparapu et al. 2014
  validity range), star radius and semi-major axis, its insolation S/S⊕ = (R★/R☉)² (Teff/5772 K)⁴ / (a/AU)²
  and where it falls against the Kopparapu 2014 conservative and optimistic limits for 1 M⊕.

Writes docs/results/population_stats.json. Nothing is filled in: a planet missing a value is not counted.

    python scripts/population_stats.py --csv exoplanet_eu.csv --fetched-at 2026-10-18T20:53:00Z
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

OUT = Path("docs/results/population_stats.json")
RJ_IN_RE = 11.209
# Kopparapu et al. 2014, Table 1 (1 M⊕): S_eff☉, a, b, c, d.
KOPPARAPU = {"recent_venus": (1.776, 2.136e-4, 2.533e-8, -1.332e-11, -3.097e-15),
             "runaway_greenhouse": (1.107, 1.332e-4, 1.58e-8, -8.308e-12, -1.931e-15),
             "maximum_greenhouse": (0.356, 6.171e-5, 1.698e-9, -3.198e-12, -5.575e-16),
             "early_mars": (0.32, 5.547e-5, 1.526e-9, -2.874e-12, -5.011e-16)}


def s_eff(limit: str, teff: float) -> float:
    s0, a, b, c, d = KOPPARAPU[limit]
    t = teff - 5780.0
    return s0 + a * t + b * t ** 2 + c * t ** 3 + d * t ** 4


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
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    edges = [10 ** (math.log10(0.5) + i * (math.log10(20) - math.log10(0.5)) / 40) for i in range(41)]
    hist = [0] * 40
    n_radius = 0
    for r in rows:
        rad, per = _num(r.get("radius")), _num(r.get("orbital_period"))
        if rad is None or per is None or per >= 100:
            continue
        re = rad * RJ_IN_RE
        if not edges[0] <= re < edges[-1]:
            continue
        n_radius += 1
        hist[min(39, int((math.log10(re) - math.log10(0.5)) / (math.log10(20) - math.log10(0.5)) * 40))] += 1
    hz, n_hz_sample = [], 0
    for r in rows:
        teff, rs, a = _num(r.get("star_teff")), _num(r.get("star_radius")), _num(r.get("semi_major_axis"))
        if teff is None or rs is None or a is None or not 2600 <= teff <= 7200 or a <= 0:
            continue
        n_hz_sample += 1
        s = rs ** 2 * (teff / 5772) ** 4 / a ** 2
        cons = s_eff("maximum_greenhouse", teff) <= s <= s_eff("runaway_greenhouse", teff)
        opt = s_eff("early_mars", teff) <= s <= s_eff("recent_venus", teff)
        if opt:
            rad = _num(r.get("radius"))
            hz.append({"name": r["name"].strip(), "teff": teff, "s": round(s, 3), "conservative": cons,
                       "radius_re": None if rad is None else round(rad * RJ_IN_RE, 2)})
    doc = {"source": "The Extrasolar Planets Encyclopaedia (exoplanet.eu)", "fetched_at": args.fetched_at,
           "valley": {"rule": "planets with a stored radius and period < 100 d; 40 log bins from 0.5 to 20 Earth radii",
                      "edges_re": [round(e, 4) for e in edges], "counts": hist, "n": n_radius},
           "hz": {"rule": ("S/S⊕ = (R★/R☉)² (Teff/5772 K)⁴ / (a/AU)², for stars of 2600–7200 K with stored Teff, radius and a; "
                           "limits from Kopparapu et al. 2014 Table 1 (1 M⊕)"),
                  "coefficients": KOPPARAPU, "sample": n_hz_sample,
                  "n_conservative": sum(1 for p in hz if p["conservative"]), "n_optimistic": len(hz),
                  "planets": sorted(hz, key=lambda p: (not p["conservative"], p["name"]))}}
    Path(args.out).write_text(json.dumps(doc, indent=0, ensure_ascii=False) + "\n")
    print(f"{args.out}: valley sample {n_radius}; HZ sample {n_hz_sample}, {doc['hz']['n_conservative']} conservative, {len(hz)} optimistic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

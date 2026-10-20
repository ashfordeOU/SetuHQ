#!/usr/bin/env python3
"""Where the transit surveys have looked: sky coverage for the Galaxy and Sky maps.

Writes ``docs/results/survey_coverage.json``:

* TESS: sectors observed per sky cell, from the ``tess-point`` package (Burke et al. 2020; MIT licence),
  counting sectors 1..N where N is the last sector begun before ``--as-of`` (sector 1 began on
  25 Jul 2018; sectors last about 27.4 days, so N is good to about one sector).
* Kepler: the prime field (four seasonal rolls of the 84 science channels) and K2 campaigns C0-C19,
  from the ``K2fov`` package's footprint model and its campaign pointing table.
* CoRoT: its two observing zones ("eyes", 10° radius around RA 6h50m and 18h50m on the equator),
  as described by Auvergne et al. 2009; zones, not individual field outlines.
* Microlensing: an approximate region toward the Galactic bulge (|l| <= 10°, -8° <= b <= +5°), where
  OGLE and KMTNet observe; approximate, not the survey field outlines.

The sky is cut into equal-area cells (a Fibonacci sphere); a fraction of the sky is the share of cells
whose centre lies in the footprint. Catalogue hosts (docs/results/exoplanet_map.json) are counted per
footprint by their own positions.

    python scripts/survey_coverage.py --as-of 2026-10-18
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

OUT = Path("docs/results/survey_coverage.json")
MAP = Path("docs/results/exoplanet_map.json")
TESS_START = date(2018, 7, 25)
SECTOR_DAYS = 27.4
FINE_N = 12288    # cells for the TESS and unmapped fractions (about 3.4 square degrees each)
SMALL_N = 196608  # cells for the small footprints: Kepler, K2, CoRoT, bulge (about 0.21 square degrees each)
DRAW_N = 3072     # cells drawn on the maps (about 13 square degrees each)
COROT_EYES = [(102.5, 0.0), (282.5, 0.0)]  # RA 6h50m and 18h50m, Dec 0
COROT_RADIUS = 10.0
BULGE = {"l": [-10.0, 10.0], "b": [-8.0, 5.0]}

SOURCES = {
    "tess": {"label": "tess-point (Burke et al. 2020), sector pointings", "url": "https://github.com/tessgi/tess-point",
             "ref": "https://doi.org/10.1117/1.JATIS.1.1.014003", "ref_label": "Ricker et al. 2015, JATIS 1, 014003 (TESS)"},
    "kepler": {"label": "K2fov footprint model; Kepler field centre RA 290.6667°, Dec +44.5°", "url": "https://github.com/KeplerGO/K2fov",
               "ref": "https://doi.org/10.1126/science.1185402", "ref_label": "Borucki et al. 2010, Science 327, 977 (Kepler)"},
    "k2": {"label": "K2fov campaign pointing table, C0-C19", "url": "https://github.com/KeplerGO/K2fov",
           "ref": "https://doi.org/10.1086/676406", "ref_label": "Howell et al. 2014, PASP 126, 398 (K2)"},
    "corot": {"label": "CoRoT observing zones, 10° radius at RA 6h50m and 18h50m", "url": "https://doi.org/10.1051/0004-6361/200810860",
              "ref": "https://doi.org/10.1051/0004-6361/200810860", "ref_label": "Auvergne et al. 2009, A&A 506, 411 (CoRoT)"},
    "bulge": {"label": "approximate bulge region observed by OGLE and KMTNet", "url": "https://doi.org/10.5303/jkas.2016.49.1.37",
              "ref": "https://doi.org/10.5303/jkas.2016.49.1.37", "ref_label": "Kim et al. 2016, JKAS 49, 37 (KMTNet)"},
}


def fibonacci(n: int) -> tuple[np.ndarray, np.ndarray]:
    i = np.arange(n) + 0.5
    dec = np.degrees(np.arcsin(1 - 2 * i / n))
    ra = np.degrees(np.pi * (1 + 5 ** 0.5) * i) % 360
    return ra, dec


def last_sector(as_of: date) -> int:
    return int((as_of - TESS_START).days // SECTOR_DAYS) + 1


def tess_counts(ra, dec, n_last: int) -> np.ndarray:
    import tess_stars2px as t

    ids = np.arange(len(ra))
    out = t.tess_stars2px_function_entry(ids, ra, dec)
    sid, sec = np.asarray(out[0]), np.asarray(out[3])
    counts = np.zeros(len(ra), dtype=int)
    seen = set()
    for i, s in zip(sid, sec):
        if i < 0 or s < 1 or s > n_last or (i, s) in seen:  # skip planned sectors and special pointings
            continue
        seen.add((i, s))
        counts[i] += 1
    return counts


def kepler_fovs():
    from K2fov import fields
    from K2fov.fov import KeplerFov

    info = fields.getFieldInfo(1000)
    # Four seasons: the footprint turns by 90° each quarter.
    return [KeplerFov(info["ra"], info["dec"], info["roll"] + 90 * s) for s in range(4)], info


def k2_fovs():
    from K2fov import fields

    out = []
    for c in range(0, 20):
        info = fields.getFieldInfo(c)
        out.append((c, info, fields.getKeplerFov(c)))
    return out


def on_silicon(fov, ra, dec) -> np.ndarray:
    """On a science channel; only points within 10° of the boresight are tested (the footprint is
    about 7° in radius, and the projection is undefined far from it)."""
    ra, dec = np.asarray(ra, float), np.asarray(dec, float)
    a0, d0, _ = fov.getBoresight()
    r = np.radians
    cosd = np.sin(r(dec)) * math.sin(r(d0)) + np.cos(r(dec)) * math.cos(r(d0)) * np.cos(r(ra - a0))
    near = np.flatnonzero(cosd >= math.cos(r(10.0)))
    out = np.zeros(len(ra), bool)
    for i in near:
        try:
            out[i] = bool(fov.isOnSilicon(ra[i], dec[i]))
        except ValueError:
            out[i] = False
    return out


def corners(fov) -> list[list[list[float]]]:
    """Each science channel's outline as [[ra, dec] x 4], rounded."""
    rows = fov.getCoordsOfChannelCorners()
    polys: dict[int, list] = {}
    for r in rows:
        ch = int(r[2])
        if ch > 84:  # fine-guidance sensors
            continue
        polys.setdefault(ch, []).append([round(float(r[3]) % 360, 3), round(float(r[4]), 3)])
    return [p for _, p in sorted(polys.items())]


def galactic_lb(ra, dec):
    from setuhq.galaxy import galactic_lb as lb

    return np.array([lb(a, d) for a, d in zip(ra, dec)])


def in_corot(ra, dec) -> np.ndarray:
    r = np.radians
    hit = np.zeros(len(ra), bool)
    for a0, d0 in COROT_EYES:
        cosd = np.sin(r(dec)) * math.sin(r(d0)) + np.cos(r(dec)) * math.cos(r(d0)) * np.cos(r(np.asarray(ra) - a0))
        hit |= cosd >= math.cos(r(COROT_RADIUS))
    return hit


def in_bulge(ra, dec) -> np.ndarray:
    lb = galactic_lb(ra, dec)
    lon = np.where(lb[:, 0] > 180, lb[:, 0] - 360, lb[:, 0])
    return (lon >= BULGE["l"][0]) & (lon <= BULGE["l"][1]) & (lb[:, 1] >= BULGE["b"][0]) & (lb[:, 1] <= BULGE["b"][1])


def coverage(ra, dec, n_last: int, kep, k2, with_tess: bool = True) -> dict:
    tess = tess_counts(ra, dec, n_last) if with_tess else None
    kepler = np.zeros(len(ra), bool)
    for f in kep:
        kepler |= on_silicon(f, ra, dec)
    k2hit = np.zeros(len(ra), bool)
    for _, _, f in k2:
        k2hit |= on_silicon(f, ra, dec)
    return {"tess": tess, "kepler": kepler, "k2": k2hit, "corot": in_corot(ra, dec), "bulge": in_bulge(ra, dec)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--as-of", default=date.today().isoformat(), help="count TESS sectors begun by this date (YYYY-MM-DD)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    as_of = date.fromisoformat(args.as_of)
    n_last = last_sector(as_of)
    kep, kinfo = kepler_fovs()
    k2 = k2_fovs()

    ra, dec = fibonacci(FINE_N)
    fine = coverage(ra, dec, n_last, kep, k2)
    transit_any = (fine["tess"] > 0) | fine["kepler"] | fine["k2"]
    sra, sdec = fibonacci(SMALL_N)
    small = coverage(sra, sdec, n_last, kep, k2, with_tess=False)
    frac = {"tess": float(np.mean(fine["tess"] > 0)), "tess_cvz_13plus": float(np.mean(fine["tess"] >= 13)),
            "kepler": float(np.mean(small["kepler"])), "k2": float(np.mean(small["k2"])),
            "corot": float(np.mean(small["corot"])), "bulge": float(np.mean(small["bulge"])),
            "unmapped": float(np.mean(~transit_any))}

    dra, ddec = fibonacci(DRAW_N)
    draw = coverage(dra, ddec, n_last, kep, k2)

    m = json.loads(MAP.read_text())
    P = m["planets"]
    hosts = {}
    for i, h in enumerate(P["host"]):
        hosts.setdefault(h, (P["ra"][i], P["dec"][i]))
    names = sorted(hosts)
    hra = np.array([hosts[h][0] for h in names])
    hdec = np.array([hosts[h][1] for h in names])
    hc = coverage(hra, hdec, n_last, kep, k2)
    host_counts = {"tess": int(np.sum(hc["tess"] > 0)), "kepler": int(np.sum(hc["kepler"])), "k2": int(np.sum(hc["k2"])),
                   "corot": int(np.sum(hc["corot"])), "bulge": int(np.sum(hc["bulge"])),
                   "none": int(np.sum(~((hc["tess"] > 0) | hc["kepler"] | hc["k2"]))), "all": len(names)}

    # How far each method reaches in this catalogue: the median and 90th percentile host distance.
    reach = {}
    for mt in m["methods"]:
        d = sorted({(P["host"][i], P["dist_pc"][i]) for i in range(len(P["name"])) if P["method"][i] == mt}, key=lambda x: x[1])
        if d:
            ds = [x[1] * 3.261563777 for x in d]
            reach[mt] = {"hosts": len(ds), "median_ly": round(ds[len(ds) // 2]), "p90_ly": round(ds[min(len(ds) - 1, int(len(ds) * 0.9))])}

    pi = coverage(np.array([84.2912083366]), np.array([-80.4691111224]), n_last, kep, k2)
    out = {
        "as_of": as_of.isoformat(), "tess_last_sector": n_last,
        "tess_rule": (f"TESS sectors 1-{n_last}: the last sector begun by {as_of.isoformat()}, counting {SECTOR_DAYS}-day "
                      f"sectors from 25 Jul 2018 (good to about one sector); planned sectors are not counted."),
        "method": (f"Fractions: the share of equal-area sky cells (Fibonacci sphere) whose centre lies in the footprint: "
                   f"{FINE_N:,} cells (about {41253 / FINE_N:.1f} square degrees each) for TESS and the unmapped sky, "
                   f"{SMALL_N:,} cells (about {41253 / SMALL_N:.2f} square degrees each) for Kepler, K2, CoRoT and the bulge."),
        "sources": SOURCES, "fractions": {k: round(v, 4) for k, v in frac.items()}, "hosts_in": host_counts,
        "hosts_from": str(MAP), "reach": reach,
        "pi_men_tess_sectors": int(pi["tess"][0]),
        "draw": {"n": DRAW_N, "ra": [round(float(x), 2) for x in dra], "dec": [round(float(x), 2) for x in ddec],
                 "tess": [int(x) for x in draw["tess"]], "kepler": [int(x) for x in np.flatnonzero(draw["kepler"])],
                 "k2": [int(x) for x in np.flatnonzero(draw["k2"])]},
        "kepler": {"ra": kinfo["ra"], "dec": kinfo["dec"], "channels": corners(kep[0])},
        "k2": [{"c": c, "ra": round(info["ra"] % 360, 3), "dec": round(info["dec"], 3), "start": info.get("start", ""),
                "stop": info.get("stop", ""), "channels": corners(f)} for c, info, f in k2],
        "corot": {"eyes": [{"ra": a, "dec": d} for a, d in COROT_EYES], "radius_deg": COROT_RADIUS},
        "bulge": BULGE,
        "gaia": "Gaia observes the whole sky; astrometry is not a footprint here.",
    }
    Path(args.out).write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"{args.out}: TESS sectors 1-{n_last}; sky fractions {out['fractions']}; hosts {host_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

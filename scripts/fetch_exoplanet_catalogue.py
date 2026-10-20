#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Every known exoplanet record, for the app's Catalogue, planet and star pages.

Source order, as for the Galaxy map: the NASA Exoplanet Archive (pscomppars) when it answers, otherwise
The Extrasolar Planets Encyclopaedia (exoplanet.eu) CSV. ``--csv PATH`` reads a CSV already downloaded from
exoplanet.eu. Writes ``docs/results/exoplanet_catalogue.json``: column arrays (one entry per planet, every
row kept, including planets with no distance), the source, its URL, the fetch time, row counts, and a
unique URL slug per planet and per star. A value the source does not give is stored as null.

    python scripts/fetch_exoplanet_catalogue.py --csv exoplanet.eu.csv --fetched-at 2026-10-18T20:53:00Z
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_exoplanet_map import NASA_TAP, SOURCES, method_of  # noqa: E402

OUT = Path("docs/results/exoplanet_catalogue.json")
# Column → (exoplanet.eu column, NASA pscomppars column). "_lo"/"_hi" columns hold the stored errors.
FIELDS = {
    "year": ("discovered", "disc_year"), "mass": ("mass", None), "msini": ("mass_sini", None),
    "radius": ("radius", "pl_radj"), "period": ("orbital_period", "pl_orbper"), "a": ("semi_major_axis", "pl_orbsmax"),
    "e": ("eccentricity", "pl_orbeccen"), "incl": ("inclination", "pl_orbincl"), "omega": ("omega", "pl_orblper"),
    "b": ("impact_parameter", "pl_imppar"), "k": ("k", "pl_rvamp"), "lambda": ("lambda_angle", "pl_projobliq"),
    "teq": ("temp_calculated", "pl_eqt"), "tmeas": ("temp_measured", None), "dist": ("star_distance", "sy_dist"),
    "smass": ("star_mass", "st_mass"), "srad": ("star_radius", "st_rad"), "steff": ("star_teff", "st_teff"),
    "smet": ("star_metallicity", "st_met"), "sage": ("star_age", "st_age"), "vmag": ("mag_v", "sy_vmag"),
    "ra": ("ra", "ra"), "dec": ("dec", "dec"),
}
ERRORS = ["mass", "msini", "radius", "period", "a", "e", "incl", "b", "k", "teq", "dist", "smass", "srad", "steff", "smet", "sage"]
TEXT = {"star": ("star_name", "hostname"), "method_raw": ("detection_type", "discoverymethod"), "status": ("publication", None),
        "updated": ("updated", "rowupdate"), "sptype": ("star_sp_type", "st_spectype"), "alt": ("alternate_names", None),
        "salt": ("star_alternate_names", None), "mass_type": ("mass_measurement_type", "pl_bmassprov"),
        "radius_type": ("radius_measurement_type", None)}


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "x"


def unique_slugs(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        s = slugify(n)
        if s in seen:
            seen[s] += 1
            s = f"{s}-{seen[s]}"
        else:
            seen[s] = 1
        out.append(s)
    return out


def _num(v):
    v = (v or "").strip()
    if not v or v.lower() == "nan":
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    if not math.isfinite(x):  # an "inf" error bar is an unbounded side, which is not a stored value
        return None
    return int(x) if x.is_integer() and abs(x) < 1e15 and "." not in v and "e" not in v.lower() else x


def _year(v):
    x = _num(v)
    return int(x) if x is not None else None


def rows_from_eu(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if (r.get("planet_status") or "Confirmed") != "Confirmed":
            continue
        row = {"name": r["name"].strip()}
        for k, (eu, _) in FIELDS.items():
            row[k] = _year(r.get(eu)) if k == "year" else _num(r.get(eu))
        for k in ERRORS:
            eu = FIELDS[k][0]
            row[k + "_lo"], row[k + "_hi"] = _num(r.get(eu + "_error_min")), _num(r.get(eu + "_error_max"))
        for k, (eu, _) in TEXT.items():
            row[k] = (r.get(eu) or "").strip() or None
        row["method"] = method_of(row["method_raw"] or "")
        out.append(row)
    return out


def rows_from_nasa(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        prov = (r.get("pl_bmassprov") or "").lower()
        mass = _num(r.get("pl_bmassj"))
        row = {"name": r["pl_name"].strip(), "mass": None if "sin" in prov else mass, "msini": mass if "sin" in prov else None}
        for k, (_, nasa) in FIELDS.items():
            if nasa:
                row[k] = _year(r.get(nasa)) if k == "year" else _num(r.get(nasa))
            else:
                row.setdefault(k, None)
        for k in ERRORS:
            nasa = FIELDS[k][1]
            row[k + "_lo"] = abs(_num(r.get(nasa + "err2")) or 0) or None if nasa else None
            row[k + "_hi"] = _num(r.get(nasa + "err1")) if nasa else None
        for k, (_, nasa) in TEXT.items():
            row[k] = ((r.get(nasa) or "").strip() or None) if nasa else None
        row["method"] = method_of(row["method_raw"] or "")
        out.append(row)
    return out


def build(rows: list[dict], source: str, fetched_at: str, note: str = "") -> dict:
    rows = sorted(rows, key=lambda r: r["name"].lower())
    cols = ["name", "slug", "star", "method", "method_raw", "status", "updated", "sptype", "alt", "salt", "mass_type", "radius_type"]
    cols += list(FIELDS) + [f"{k}_{s}" for k in ERRORS for s in ("lo", "hi")]
    slugs = unique_slugs([r["name"] for r in rows])
    for r, s in zip(rows, slugs):
        r["slug"] = s
    stars = sorted({r["star"] for r in rows if r["star"]}, key=str.lower)
    src = SOURCES[source]
    return {
        "source": source, "source_name": src["name"], "source_short": src["short"], "url": src["url"],
        "fetched_at": fetched_at, "definition": src["definition"], "note": note,
        "units": {"mass": "Jupiter mass", "msini": "Jupiter mass (m sin i)", "radius": "Jupiter radius", "period": "day",
                  "a": "AU", "incl": "degree", "omega": "degree", "lambda": "degree", "k": "m/s", "teq": "K", "tmeas": "K",
                  "dist": "parsec", "smass": "solar mass", "srad": "solar radius", "steff": "K", "smet": "dex", "sage": "Gyr",
                  "ra": "degree", "dec": "degree"},
        "counts": {"rows": len(rows), "with_distance": sum(1 for r in rows if r["dist"] is not None),
                   "with_radius": sum(1 for r in rows if r["radius"] is not None),
                   "with_mass": sum(1 for r in rows if r["mass"] is not None or r["msini"] is not None),
                   "without_star": sum(1 for r in rows if not r["star"]), "stars": len(stars)},
        "stars": {"names": stars, "slugs": unique_slugs(stars)},
        "columns": cols, "planets": {c: [r.get(c) for r in rows] for c in cols},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv")
    ap.add_argument("--fetched-at")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--skip-nasa", action="store_true")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    note, data = "", None
    if not args.skip_nasa:
        cols = ["pl_name", "hostname", "discoverymethod", "pl_bmassj", "pl_bmassprov", "rowupdate", "st_spectype"]
        for k, (_, nasa) in FIELDS.items():
            if nasa:
                cols.append(nasa)
                if k in ERRORS:
                    cols += [nasa + "err1", nasa + "err2"]
        url = NASA_TAP + "?" + urllib.parse.urlencode({"query": f"select {','.join(dict.fromkeys(cols))} from pscomppars", "format": "csv"})
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 (fixed https URL)
                text = resp.read().decode("utf-8")
            if not text.startswith("pl_name"):
                raise ValueError(text[:200].strip())
            data = build(rows_from_nasa(text), "nasa", now)
        except Exception as exc:
            note = f"NASA Exoplanet Archive not used: {str(exc).splitlines()[0][:160] if str(exc) else type(exc).__name__}"
            print(note, file=sys.stderr)
    if data is None:
        if not args.csv:
            print("exoplanet.eu fallback needs --csv (the catalogue CSV)", file=sys.stderr)
            return 2
        path = Path(args.csv)
        fetched = args.fetched_at or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = build(rows_from_eu(path.read_text(encoding="utf-8")), "eu", fetched, note)
    Path(args.out).write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    c = data["counts"]
    print(f"{args.out}: {c['rows']} planets, {c['stars']} stars from {data['source_short']} ({c['with_distance']} with a distance)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

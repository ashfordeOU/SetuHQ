#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Fetch every known exoplanet with a sky position and a distance, for the app's Galaxy map.

Source order:

1. The NASA Exoplanet Archive (TAP, table ``pscomppars``: pl_name, hostname, ra, dec, sy_dist,
   disc_year, discoverymethod, pl_orbper, pl_radj, pl_bmassj, pl_bmassprov, sy_vmag).
2. The Extrasolar Planets Encyclopaedia (exoplanet.eu) catalogue CSV, when the archive does not
   answer. ``--csv PATH`` reads a CSV already downloaded from exoplanet.eu instead of fetching it.

Writes ``docs/results/exoplanet_map.json``: column arrays (one entry per planet), the source and its
URL, when it was fetched, the row counts and the exact number of rows dropped for a missing distance
or position. Nothing is filled in: a value the source does not give is stored as null.

    python scripts/fetch_exoplanet_map.py                    # try NASA, then exoplanet.eu
    python scripts/fetch_exoplanet_map.py --csv exoplanet.eu.csv --fetched-at 2026-10-18T20:53:00Z
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NASA_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
NASA_QUERY = ("select pl_name,hostname,ra,dec,sy_dist,disc_year,discoverymethod,pl_orbper,pl_radj,"
              "pl_bmassj,pl_bmassprov,sy_vmag,pl_refname from pscomppars")
NASA_PAGE = "https://exoplanetarchive.ipac.caltech.edu/cgi-bin/TblView/nph-tblView?app=ExoTbls&config=PSCompPars"
EU_CSV = "https://exoplanet.eu/catalog/csv/"
EU_PAGE = "https://exoplanet.eu/catalog/"
OUT = Path("docs/results/exoplanet_map.json")

SOURCES = {
    "nasa": {"name": "NASA Exoplanet Archive (Planetary Systems Composite Parameters)", "short": "NASA Exoplanet Archive",
             "url": NASA_PAGE,
             "definition": ("The NASA Exoplanet Archive lists planets published in the refereed literature with a mass "
                            "(or minimum mass) of at most 30 Jupiter masses.")},
    "eu": {"name": "The Extrasolar Planets Encyclopaedia (exoplanet.eu)", "short": "exoplanet.eu", "url": EU_PAGE,
           "definition": ("exoplanet.eu lists as confirmed every object it treats as a planet: bodies up to 60 Jupiter "
                          "masses (within their uncertainty), published or announced. Its list is broader than the NASA "
                          "Exoplanet Archive's, which keeps objects up to 30 Jupiter masses from refereed papers.")},
}

# Detection methods, by the first method the source lists for a planet.
METHODS = ["transit", "rv", "imaging", "microlensing", "astrometry", "timing", "other"]
METHOD_LABEL = {"transit": "Transit", "rv": "Radial velocity", "imaging": "Imaging", "microlensing": "Microlensing",
                "astrometry": "Astrometry", "timing": "Timing", "other": "Other (TTV, kinematic, other)"}
_RAW_METHOD = {
    "primary transit": "transit", "transit": "transit", "radial velocity": "rv", "imaging": "imaging",
    "microlensing": "microlensing", "astrometry": "astrometry", "timing": "timing", "pulsar timing": "timing",
    "eclipse timing variations": "timing", "pulsation timing variations": "timing",
}

COLUMNS = ["name", "host", "ra", "dec", "dist_pc", "year", "method", "method_raw", "period_d", "radius_rj",
           "mass_mj", "mass_kind", "mag_v", "molecules"]


def method_of(raw: str) -> str:
    first = (raw or "").split(",")[0].strip().lower()
    return _RAW_METHOD.get(first, "other")


def _num(v: str | None, digits: int | None = None):
    if v is None:
        return None
    v = str(v).strip()
    if v == "" or v.lower() == "nan":
        return None
    try:
        x = float(v)
    except ValueError:
        return None
    return round(x, digits) if digits is not None else x


def _int(v):
    x = _num(v)
    return int(x) if x is not None else None


def rows_from_eu(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if (r.get("planet_status") or "Confirmed") != "Confirmed":
            continue
        mass, msini = _num(r.get("mass")), _num(r.get("mass_sini"))
        out.append({"name": r["name"].strip(), "host": (r.get("star_name") or "").strip(), "ra": _num(r.get("ra")),
                    "dec": _num(r.get("dec")), "dist_pc": _num(r.get("star_distance")), "year": _int(r.get("discovered")),
                    "method": method_of(r.get("detection_type", "")), "method_raw": (r.get("detection_type") or "").strip(),
                    "period_d": _num(r.get("orbital_period")), "radius_rj": _num(r.get("radius")),
                    "mass_mj": mass if mass is not None else msini,
                    "mass_kind": "mass" if mass is not None else ("msini" if msini is not None else None),
                    "mag_v": _num(r.get("mag_v")), "molecules": (r.get("molecules") or "").strip() or None})
    return out


def rows_from_nasa(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        prov = (r.get("pl_bmassprov") or "").strip().lower()
        mass = _num(r.get("pl_bmassj"))
        out.append({"name": r["pl_name"].strip(), "host": r["hostname"].strip(), "ra": _num(r.get("ra")),
                    "dec": _num(r.get("dec")), "dist_pc": _num(r.get("sy_dist")), "year": _int(r.get("disc_year")),
                    "method": method_of(r.get("discoverymethod", "")), "method_raw": (r.get("discoverymethod") or "").strip(),
                    "period_d": _num(r.get("pl_orbper")), "radius_rj": _num(r.get("pl_radj")), "mass_mj": mass,
                    "mass_kind": None if mass is None else ("msini" if "sin" in prov else "mass"),
                    "mag_v": _num(r.get("sy_vmag")), "molecules": None})
    return out


def build(rows: list[dict], source: str, fetched_at: str, note: str = "") -> dict:
    no_pos = [r for r in rows if r["ra"] is None or r["dec"] is None]
    no_dist = [r for r in rows if r not in no_pos and r["dist_pc"] is None]
    kept = sorted((r for r in rows if r["ra"] is not None and r["dec"] is not None and r["dist_pc"] is not None),
                  key=lambda r: (r["host"], r["name"]))
    src = SOURCES[source]
    return {
        "source": source, "source_name": src["name"], "source_short": src["short"], "url": src["url"],
        "fetched_at": fetched_at, "definition": src["definition"], "note": note,
        "method_rule": "Method: the first detection method the source lists for the planet.",
        "methods": METHODS, "method_label": METHOD_LABEL,
        "units": {"dist_pc": "parsec", "period_d": "day", "radius_rj": "Jupiter radius", "mass_mj": "Jupiter mass",
                  "ra": "degree (J2000)", "dec": "degree (J2000)"},
        "counts": {"rows": len(rows), "kept": len(kept), "dropped_no_distance": len(no_dist),
                   "dropped_no_position": len(no_pos), "hosts": len({r["host"] for r in kept})},
        "columns": COLUMNS,
        "planets": {c: [r[c] for r in kept] for c in COLUMNS},
    }


def fetch(url: str, timeout: float = 60) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (fixed https URLs)
        return resp.read().decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", help="an exoplanet.eu catalogue CSV already downloaded")
    ap.add_argument("--fetched-at", help="when that CSV was fetched (ISO 8601, UTC); default: the file's time")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--skip-nasa", action="store_true", help="do not try the NASA Exoplanet Archive first")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    note, data = "", None
    if not args.skip_nasa:
        url = NASA_TAP + "?" + urllib.parse.urlencode({"query": NASA_QUERY, "format": "csv"})
        try:
            text = fetch(url)
            if not text.startswith("pl_name"):
                raise ValueError(text[:200].strip())
            data = build(rows_from_nasa(text), "nasa", now)
        except Exception as exc:  # the archive is down or answered with an error
            note = f"NASA Exoplanet Archive not used: {str(exc).splitlines()[0][:160] if str(exc) else type(exc).__name__}"
            print(note, file=sys.stderr)
    if data is None:
        if args.csv:
            path = Path(args.csv)
            fetched = args.fetched_at or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            text = path.read_text(encoding="utf-8")
        else:
            text, fetched = fetch(EU_CSV), now
        data = build(rows_from_eu(text), "eu", fetched, note)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    c = data["counts"]
    print(f"{out}: {c['kept']} planets around {c['hosts']} stars from {data['source_short']} "
          f"({c['rows']} rows; {c['dropped_no_distance']} without a distance, {c['dropped_no_position']} without a position)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

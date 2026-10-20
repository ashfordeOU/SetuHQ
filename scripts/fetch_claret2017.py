#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Claret (2017) quadratic limb-darkening coefficients for TESS, for every log g and Teff in the table.

Source: VizieR J/A+A/600/A30/tableab (doi:10.26093/cds/vizier.36000030), the PHOENIX-COND ("PC") models,
quasi-spherical ("q") rows, [M/H] = 0, least-squares (LSM) fit. These are the rows the ATLAS (C2) quotes at
log g = 4.5. Writes ``docs/results/claret2017_tess_quadratic.json``: [log g, Teff, u1, u2] rows.

    python scripts/fetch_claret2017.py            # downloads (or reads cache/vizier/claret_ab.tsv)
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = ("https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source=J/A+A/600/A30/tableab&-out.max=unlimited"
       "&-out=logg,Teff,Z,L/HP,aLSM,bLSM,Type,Mod&Type=q")
CACHE = Path("cache/vizier/claret_ab.tsv")
OUT = Path("docs/results/claret2017_tess_quadratic.json")


def parse(text: str) -> list[list[float]]:
    rows = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) < 8 or cells[7] != "PC" or cells[6] != "q":
            continue
        try:
            logg, teff, z, aa, bb = float(cells[0]), float(cells[1]), float(cells[2]), float(cells[4]), float(cells[5])
        except ValueError:
            continue
        if z == 0.0:
            rows.append([logg, teff, aa, bb])
    return sorted(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="download even when the cache exists")
    args = ap.parse_args(argv)
    if args.refresh or not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=120) as resp:  # noqa: S310 (fixed https URL)
            CACHE.write_bytes(resp.read())
    fetched = datetime.fromtimestamp(CACHE.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = parse(CACHE.read_text())
    OUT.write_text(json.dumps({
        "source": "Claret 2017, A&A 600, A30: TESS limb darkening (VizieR J/A+A/600/A30/tableab)",
        "doi": "https://doi.org/10.1051/0004-6361/201629705", "vizier": "https://doi.org/10.26093/cds/vizier.36000030",
        "url": URL, "fetched_at": fetched,
        "selection": "PHOENIX-COND models (Mod = PC), quasi-spherical (Type = q), [M/H] = 0, LSM fit (aLSM = u1, bLSM = u2)",
        "columns": ["logg", "teff", "u1", "u2"], "rows": rows,
    }, separators=(",", ":")) + "\n")
    print(f"{OUT}: {len(rows)} rows, log g {min(r[0] for r in rows)}–{max(r[0] for r in rows)}, Teff {min(r[1] for r in rows):.0f}–{max(r[1] for r in rows):.0f} K")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

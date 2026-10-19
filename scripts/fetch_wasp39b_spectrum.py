#!/usr/bin/env python3
"""Fetch JWST's public WASP-39 b transmission spectrum (Carter et al. 2024) and store a trimmed copy.

Source: "Products and Models for 'A benchmark JWST near-infrared spectrum for the exoplanet WASP-39 b'",
Zenodo doi:10.5281/zenodo.10161743, licence CC-BY-4.0. The record is one 1.7 GB zip; this script reads
only the two small files it needs, with HTTP range requests:

* 4_TRANSMISSION_SPECTRA/Fixed_LimbDarkening/NIRSpec_PRISM/bins_scale5.csv: the NIRSpec PRISM spectrum
  in its coarsest binning, Rp/R★ per wavelength bin with lower and upper errors;
* 5_MODEL_SPECTRUM/BestFitModel.txt: the paper's best-fit model (transit depth against wavelength),
  thinned to every 8th point for the page.

Writes docs/results/wasp39b_jwst_spectrum.json with the source, licence, citation and the exact paths.
Depth = (Rp/R★)²; its error is 2 (Rp/R★) σ(Rp/R★), taking the larger of the two errors. Nothing else changes.

    python scripts/fetch_wasp39b_spectrum.py
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RECORD = "https://zenodo.org/api/records/10161743"
OUT = Path("docs/results/wasp39b_jwst_spectrum.json")
SPECTRUM = "ZENODO/4_TRANSMISSION_SPECTRA/Fixed_LimbDarkening/NIRSpec_PRISM/bins_scale5.csv"
MODEL = "ZENODO/5_MODEL_SPECTRUM/BestFitModel.txt"


class RangeFile(io.RawIOBase):
    """A read-only file over HTTP range requests, enough for zipfile to read the central directory."""

    def __init__(self, url: str, size: int):
        self.url, self.size, self.pos = url, size, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def readinto(self, b):
        n = len(b)
        if n == 0 or self.pos >= self.size:
            return 0
        end = min(self.size, self.pos + max(n, 1 << 16)) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        data = urllib.request.urlopen(req, timeout=120).read()[:n]  # noqa: S310 (fixed https URL)
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


def main() -> int:
    rec = json.loads(urllib.request.urlopen(RECORD, timeout=60).read())  # noqa: S310
    f = rec["files"][0]
    z = zipfile.ZipFile(io.BufferedReader(RangeFile(f["links"]["self"], f["size"]), buffer_size=1 << 16))
    rows = list(csv.DictReader(io.StringIO(z.read(SPECTRUM).decode())))
    points = []
    for r in rows:
        k, lo, hi = float(r["rp/rs"]), float(r["rp/rs_err_low"]), float(r["rp/rs_err_hih"])
        points.append([round(float(r["wave"]), 5), round(float(r["wave_low"]), 5), round(float(r["wave_hig"]), 5),
                       round(k * k * 1e6, 1), round(2 * k * max(lo, hi) * 1e6, 1)])
    model = []
    for i, line in enumerate(z.read(MODEL).decode().splitlines()):
        if line.startswith("#") or not line.strip() or i % 8:
            continue
        w, d = line.split()[:2]
        model.append([round(float(w), 4), round(float(d) * 1e6, 1)])
    doc = {
        "planet": "WASP-39 b", "instrument": "JWST NIRSpec PRISM",
        "source": rec["metadata"]["title"], "doi": "https://doi.org/10.5281/zenodo.10161743",
        "licence": rec["metadata"]["license"]["id"].upper(),
        "citation": "Carter et al. 2024, Nature Astronomy 8, 1008, doi:10.1038/s41550-024-02292-x",
        "paper": "https://doi.org/10.1038/s41550-024-02292-x",
        "files": {"spectrum": SPECTRUM, "model": MODEL + " (every 8th point)"},
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": ["wave_um", "wave_low_um", "wave_high_um", "depth_ppm", "depth_err_ppm"],
        "note": "Depth = (Rp/R★)²; error = 2·(Rp/R★)·σ, the larger of the published lower and upper errors.",
        "points": points, "model_columns": ["wave_um", "depth_ppm"], "model": model,
    }
    OUT.write_text(json.dumps(doc, indent=0, ensure_ascii=False) + "\n")
    print(f"{OUT}: {len(points)} points, {len(model)} model points from {doc['doi']} ({doc['licence']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

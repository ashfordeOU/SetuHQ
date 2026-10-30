#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Write docs/results/stellar_figures.json: the real TESS data behind the two figures on /evidence/stellar/.

Both figures are real data, cited: public TESS SPOC 2-minute light curves from MAST, read with
setuhq.loaders.load_spoc_file (PDCSAP flux, quality-0 cadences), analysed with the same code the validation runs
(setuhq.flares.detect_flares, setuhq.pulsations), with the published values beside them.

* **Flares**: TIC 150359500, TESS sector 2 (the star of the flare-energy check, Günther et al. 2020): the 1.5 days
  that hold the most flares SetuHQ detects, with each detected flare's span and each published flare peak from
  Günther et al. 2020 (VizieR J/AJ/159/60, table1).
* **Pulsations**: beta Pic, TESS sector 5 (one of the three sectors of the pulsation check): the amplitude spectrum
  from 5 to 60 d⁻¹, the frequencies SetuHQ's pre-whitening finds in that one sector, and the published frequencies
  of Zieba et al. 2019 (docs/results/stellar_validation_references.json).

Nothing here is a new measurement for the validation: the status on the page is read from
docs/results/stellar_validation.json. TESS data are public (MAST); no CHEOPS data are used.

    python scripts/stellar_figures.py --flare-fits tess2018234235059-s0002-0000000150359500-0121-s_lc.fits \
        --pulsation-fits tess2018319095959-s0005-0000000270577175-0125-s_lc.fits [--gunther gunther.tsv]

Without ``--gunther`` the published flare peaks are fetched from VizieR (one request). The TIC values come from
setuhq.stellar_io.tic_star (cached under cache/tic/).
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/results/stellar_figures.json"
REFS = ROOT / "docs/results/stellar_validation_references.json"
VIZIER = ("https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source=J/AJ/159/60/table1&TIC={tic}"
          "&-out=TIC,tpeak,Amp&-out.max=unlimited")
FLARE_TIC, PULSE_TIC = 150359500, 270577175
WINDOW_D = 1.5
FMIN, FMAX, DF = 5.0, 60.0, 0.05
MAST_DOI = "https://doi.org/10.17909/t9-nmc8-f686"  # TESS SPOC light curves at MAST


def _gunther(tic: int, path: str | None) -> list[float]:
    text = Path(path).read_text() if path else urllib.request.urlopen(VIZIER.format(tic=tic), timeout=60).read().decode()
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip() == str(tic):
            out.append(float(parts[1]) - 2457000.0)
    return sorted(out)


def flare_figure(fits: str, gunther: str | None) -> dict:
    from setuhq import flares as fl
    from setuhq.loaders import load_spoc_file
    from setuhq.stellar_io import tic_star

    lc = load_spoc_file(fits)
    star = tic_star(FLARE_TIC, ROOT / "cache")
    cad = float(np.median(np.diff(lc.time))) * 86400.0
    out = fl.detect_flares(lc.time, lc.flux, lc.flux_err, config=fl.config_for("TESS", cad), star=star, band="TESS")
    flares = out["flares"]
    peaks = np.array([f["t_peak"] for f in flares])
    # the window that holds the most detected flares (ties: the earliest)
    best = max((int(((peaks >= a) & (peaks < a + WINDOW_D)).sum()), -a) for a in np.arange(lc.time[0], lc.time[-1] - WINDOW_D, 0.05))
    a = round(-best[1], 3)
    b = a + WINDOW_D
    m = (lc.time >= a) & (lc.time < b)
    t, f = lc.time[m], lc.flux[m] / np.median(lc.flux)
    # one value per 2-minute cadence, in units of 0.1 ppt above or below the median; None in a gap
    step = cad / 86400.0
    idx = np.round((t - a) / step).astype(int)
    vals: list[int | None] = [None] * (int(idx.max()) + 1)
    for i, v in zip(idx, f):
        vals[i] = int(round((v - 1.0) * 1e4))
    pub = [round(x, 5) for x in _gunther(FLARE_TIC, gunther)]
    return {
        "star": "TIC 150359500", "tic": FLARE_TIC, "sector": lc.provenance.get("sector"),
        "file": lc.provenance.get("file"), "file_sha256": lc.provenance.get("file_sha256"),
        "tic_values": star, "t0_btjd": a, "step_d": round(step, 8), "unit": "0.1 ppt (relative flux - 1, x 1e4)",
        "flux": vals,
        "ours": [{"t_start": round(x["t_start"], 5), "t_end": round(x["t_end"], 5), "t_peak": round(x["t_peak"], 5),
                  "amplitude": round(x["amplitude"], 5), "n_components": x["n_components"]}
                 for x in flares if a <= x["t_peak"] < b],
        "published_peaks_btjd": [x for x in pub if a <= x < b],
        "sector_summary": {"n_flares": out["summary"]["n_flares"], "n_complex": out["summary"]["n_complex"],
                           "observing_days": round(out["summary"]["observing_days"], 2), "published_flares": len(pub)},
        "reference": "Günther et al. 2020, AJ 159, 60 (VizieR J/AJ/159/60, table1)",
        "source": (f"TESS sector {lc.provenance.get('sector')}, SPOC 2-minute PDCSAP flux of TIC {FLARE_TIC} from MAST "
                   f"({MAST_DOI}), file {lc.provenance.get('file')} (sha256 {str(lc.provenance.get('file_sha256'))[:12]}…), "
                   f"normalised to its median; flares detected by setuhq.flares.detect_flares with the TESS defaults; "
                   f"published peaks from Günther et al. 2020 (VizieR J/AJ/159/60)."),
    }


def pulsation_figure(fits: str) -> dict:
    from setuhq import pulsations as pu
    from setuhq.loaders import load_spoc_file
    from setuhq.stellar_io import tic_star

    lc = load_spoc_file(fits)
    star = tic_star(PULSE_TIC, ROOT / "cache")
    f = lc.flux / np.median(lc.flux)
    fr, amp = pu.amplitude_spectrum(lc.time, f, fmin=FMIN, fmax=FMAX)
    n = int(round((FMAX - FMIN) / DF))
    peak = [0] * n
    for x, y in zip(fr, amp):
        k = min(n - 1, int((x - FMIN) / DF))
        peak[k] = max(peak[k], int(round(y * 1e6)))
    pw = pu.prewhiten(lc.time, f, fmin=FMIN, fmax=FMAX, max_frequencies=15)
    refs = json.loads(REFS.read_text())["beta_pic"]
    return {
        "star": "beta Pic", "tic": PULSE_TIC, "sector": lc.provenance.get("sector"),
        "file": lc.provenance.get("file"), "file_sha256": lc.provenance.get("file_sha256"), "tic_values": star,
        "fmin": FMIN, "fmax": FMAX, "df": DF, "amp_ppm_max_per_bin": peak,
        "ours": [[round(x["frequency"], 4), int(round(x["amplitude"] * 1e6)), round(x["snr"], 1)] for x in pw["frequencies"]],
        "published": [[round(x["frequency_cd"], 4), x.get("amplitude_mmag")] for x in refs["frequencies"]
                      if FMIN <= x["frequency_cd"] <= FMAX],
        "reference": refs["source"],
        "source": (f"TESS sector {lc.provenance.get('sector')}, SPOC 2-minute PDCSAP flux of TIC {PULSE_TIC} (beta Pic) from "
                   f"MAST ({MAST_DOI}), file {lc.provenance.get('file')} (sha256 {str(lc.provenance.get('file_sha256'))[:12]}…); "
                   f"amplitude spectrum and pre-whitening (15 frequencies) by setuhq.pulsations on this one sector; "
                   f"published frequencies from {refs['source']} (sectors 5-7)."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--flare-fits", required=True)
    ap.add_argument("--pulsation-fits", required=True)
    ap.add_argument("--gunther", help="a VizieR TSV of J/AJ/159/60 table1 (TIC, tpeak, Amp) instead of fetching it")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    from setuhq import __version__

    doc = {"kind": "setuhq-stellar-figures/1", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "setuhq_version": __version__, "made_by": "scripts/stellar_figures.py",
           "label": "Real data, cited",
           "licence": "SetuHQ's derived numbers: CC BY 4.0. TESS data: public (MAST). No CHEOPS data.",
           "flare": flare_figure(args.flare_fits, args.gunther), "pulsation": pulsation_figure(args.pulsation_fits)}
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    Path(args.out).write_text(text + "\n")
    print(f"wrote {args.out} ({len(text):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

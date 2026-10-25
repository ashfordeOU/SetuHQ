#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Reproduce protocol v4's target draws from the catalogues' metadata (no light curve is read).

    python scripts/stellar_validation_v4_select.py           # fetch the three tables from VizieR, draw, compare
    python scripts/stellar_validation_v4_select.py --tsv DIR # the same from saved VizieR TSV files (prsa.tsv, canto.tsv,
                                                             # faus1.tsv, faus3.tsv)

It prints the draws and checks them, target by target, against docs/results/stellar_validation_protocol_v4.json
(the frozen file, which this script never writes). The rules are the protocol's "selection" texts. "Present", for
the eclipsing binaries' Dp-2g and Phip-2g, means a non-empty value (Dp-2g also non-zero); every such value in the
catalogue is positive, so the rule is Dp-2g > 0 and Phip-2g > 0.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "docs/results/stellar_validation_protocol_v4.json").read_text())
VIZIER = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-out.max=unlimited&-out.all&-source="
TABLES = {"prsa": "J/ApJS/258/16", "canto": "J/ApJS/250/20/table1", "faus1": "J/ApJ/956/108/table1",
          "faus3": "J/ApJ/956/108/table3"}


def _rows(text: str) -> list[dict]:
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    hdr = lines[0].split("\t")
    return [{h: x.strip() for h, x in zip(hdr, ln.split("\t"))} for ln in lines[3:]]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(tsv_dir: str | None) -> dict:
    out = {}
    for k, cat in TABLES.items():
        if tsv_dir:
            text = (Path(tsv_dir) / f"{k}.tsv").read_text()
        else:
            with urllib.request.urlopen(VIZIER + cat, timeout=120) as r:
                text = r.read().decode()
        out[k] = _rows(text)
    return out


def draw(t: dict) -> dict:
    seed = PROTOCOL["seed"]
    f = _f
    ok = [r for r in t["prsa"] if r["m_TIC"] == "1" and f(r["Per"]) and 0.3 <= f(r["Per"]) <= 8 and f(r["Tmag"]) is not None
          and f(r["Tmag"]) <= 12 and f(r["Dp-2g"]) and f(r["Phip-2g"]) is not None and f(r["Morph"]) is not None
          and 0 <= f(r["Morph"]) <= 1 and r["Sectors"]]
    det = sorted([r for r in ok if f(r["Morph"]) < 0.5], key=lambda r: int(r["TIC"]))
    nd = sorted([r for r in ok if f(r["Morph"]) >= 0.5], key=lambda r: int(r["TIC"]))
    rng = np.random.default_rng(seed)
    pd_ = [det[i] for i in rng.permutation(len(det))[:15]]
    pn = [nd[i] for i in rng.permutation(len(nd))[:15]]
    eb = [int(r["TIC"]) for pair in zip(pd_, pn) for r in pair]
    okc = sorted([r for r in t["canto"] if f(r["Prot"]) and 0.5 <= f(r["Prot"]) <= 12 and r["Sectors"]], key=lambda r: int(r["TIC"]))
    rng = np.random.default_rng(seed + 1)
    rot = [int(okc[i]["TIC"]) for i in rng.permutation(len(okc))[:30]]
    f3 = {r["Name"]: r for r in t["faus3"]}
    oks = sorted([r for r in t["faus1"] if f(r["tPeak"]) and r["Qual"].zfill(4)[0] == "0" and r["Qual"].zfill(4)[1] == "0"
                  and f(r["TmagP"]) <= 17.0 and r["Reduc"].zfill(3)[2] == "0" and r["Name"] in f3 and f(f3[r["Name"]]["tRise"])],
                 key=lambda r: r["Name"])
    rng = np.random.default_rng(seed + 2)
    sne = [oks[i]["Name"] for i in rng.permutation(len(oks))[:20]]
    return {"binaries": eb, "rotation": rot, "transients": sne,
            "pools": {"binaries": [len(ok), len(det), len(nd)], "rotation": len(okc), "transients": len(oks)}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tsv", help="a folder of saved VizieR TSV files instead of the network")
    a = ap.parse_args()
    d = draw(load(a.tsv))
    want = {"binaries": [x["tic"] for x in PROTOCOL["binaries"]["targets"]],
            "rotation": [x["tic"] for x in PROTOCOL["rotation"]["targets"]],
            "transients": [x["name"] for x in PROTOCOL["transients"]["targets"]]}
    ok = True
    for k in want:
        same = d[k] == want[k]
        ok &= same
        print(f"{k}: {len(d[k])} drawn; {'the same as' if same else 'DIFFERENT FROM'} the protocol's targets, in order")
    print("pools:", d["pools"])
    sys.exit(0 if ok else 1)

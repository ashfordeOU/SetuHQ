#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The archive records behind each dip's journey strip (setuhq.journey), for the example runs' stars.

Two NASA Exoplanet Archive tables, queried over TAP for the TICs in docs/results/targets.json:

* ``toi``: every TOI on those stars, with its ephemeris and the TFOP Working Group's disposition (the "Matches a
  TOI?" and "Follow-up" steps);
* ``ps`` (``default_flag = 1``): the archive's planets on those stars, with the reference that reported each (the
  "In the literature as a planet?" step).

Writes ``docs/results/showcase_archive.json`` with each table's query and fetch time. A build only reads it; the
journey strip says "as of" the fetch date.

    python scripts/fetch_showcase_archive.py
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TARGETS = Path("docs/results/targets.json")
OUT = Path("docs/results/showcase_archive.json")
TOI_COLS = "toi,tid,pl_orbper,pl_orbpererr1,pl_tranmid,pl_tranmiderr1,pl_trandurh,tfopwg_disp,rowupdate"
PS_COLS = "pl_name,hostname,tic_id,pl_orbper,pl_tranmid,tran_flag,disc_year,disc_refname"


def query(adql: str) -> list[dict]:
    url = TAP + "?" + urllib.parse.urlencode({"query": adql, "format": "csv"})
    with urllib.request.urlopen(url, timeout=120) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))
    return [{k: (v if v != "" else None) for k, v in row.items()} for row in rows]


def main() -> int:
    tics = sorted(int(t.split()[-1]) for t in json.loads(TARGETS.read_text())["targets"])
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    toi_q = f"select {TOI_COLS} from toi where tid in ({','.join(map(str, tics))}) order by toi"
    ps_q = f"select {PS_COLS} from ps where default_flag=1 and tic_id in ({','.join(repr(f'TIC {t}') for t in tics)}) order by pl_name"
    out = {"source": "NASA Exoplanet Archive (TAP)", "url": TAP, "tics": tics,
           "toi": {"table": "toi", "query": toi_q, "fetched_at": now, "rows": query(toi_q)},
           "ps": {"table": "ps (default_flag = 1)", "query": ps_q, "fetched_at": now, "rows": query(ps_q)}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}: {len(out['toi']['rows'])} TOIs, {len(out['ps']['rows'])} archive planets, fetched {now}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""TESS's published pointing schedule, for /explore/tess-now/.

Reads the TESS Science Office's public sector pages (https://tess.mit.edu/observations/sector-N/): each states the
dates a sector's observations extend over and the RA, Dec and roll of the spacecraft's and the four cameras'
boresights (J2000, degrees). Writes ``docs/results/tess_schedule.json`` with the source, each page's address and
the date the schedule was saved. This is the published plan, not live telemetry: the page says so.

    python scripts/fetch_tess_schedule.py --first 104 --last 121
    python scripts/fetch_tess_schedule.py --cafile bundle.pem   # see below

tess.mit.edu sends an incomplete certificate chain (its leaf's issuer, "InCommon Intermediate CA - DVG2C", is
missing from what the server presents). Browsers fetch the missing certificate themselves; Python does not. When
verification fails, download the intermediate named in the leaf's Authority Information Access field
(https://repository.emsign.com/certs/EEEMIncommonDVG2C.crt), append it to your CA bundle and pass ``--cafile``.
Verification stays on.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

OUT = Path("docs/results/tess_schedule.json")
PAGE = "https://tess.mit.edu/observations/sector-{n}/"
SOURCE = "TESS Science Office (MIT), public sector pages at tess.mit.edu/observations/"
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"), 1)}
ROW = r"{name}\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)"


def text_of(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def parse_dates(text: str) -> tuple[str, str]:
    """'Observations extend from September 7 through October 5, 2026' (or across a year end) as ISO dates."""
    m = re.search(r"extend from (\w+) (\d{1,2})(?:, (\d{4}))? through (\w+) (\d{1,2}), (\d{4})", text)
    if not m:
        raise ValueError("no observation dates on the page")
    m1, d1, y1, m2, d2, y2 = m.groups()
    y2 = int(y2)
    y1 = int(y1) if y1 else (y2 if MONTHS[m1] <= MONTHS[m2] else y2 - 1)
    return date(y1, MONTHS[m1], int(d1)).isoformat(), date(y2, MONTHS[m2], int(d2)).isoformat()


def parse_sector(n: int, page: str) -> dict:
    text = text_of(page)
    start, end = parse_dates(text)
    body = {}
    for key, name in (("spacecraft", "Spacecraft"), ("cam1", "Camera 1"), ("cam2", "Camera 2"), ("cam3", "Camera 3"), ("cam4", "Camera 4")):
        m = re.search(ROW.format(name=name), text)
        if not m:
            raise ValueError(f"sector {n}: no {name} boresight")
        body[key] = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
    return {"sector": n, "start": start, "end": end, **body, "page": PAGE.format(n=n)}


def fetch(url: str, ctx: ssl.SSLContext) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "SetuHQ schedule fetch (https://setuhq.com)"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--first", type=int, default=104)
    ap.add_argument("--last", type=int, default=121)
    ap.add_argument("--cafile", help="CA bundle that also holds tess.mit.edu's missing intermediate (see the module docstring)")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    ctx = ssl.create_default_context(cafile=a.cafile)
    sectors = []
    for n in range(a.first, a.last + 1):
        try:
            sectors.append(parse_sector(n, fetch(PAGE.format(n=n), ctx)))
        except Exception as exc:  # a sector not yet published, or a page that changed shape: say so, never guess
            print(f"sector {n}: skipped ({exc})", file=sys.stderr)
        time.sleep(1)
    if not sectors:
        print("no sector could be read; nothing written", file=sys.stderr)
        return 1
    saved = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = {"source": SOURCE, "url": "https://tess.mit.edu/observations/", "saved": saved,
           "note": "Pointing from the published schedule, not live telemetry. Boresights are J2000 RA, Dec and roll in degrees, "
                   "as each sector page states them; dates are the days each page says observations extend over.",
           "camera_fov_deg": 24.0, "sectors": sectors}
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {a.out}: sectors {sectors[0]['sector']} to {sectors[-1]['sector']}, saved {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

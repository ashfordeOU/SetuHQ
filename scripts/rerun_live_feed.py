#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Re-run the live discovery catalogue's targets on the current code, on the same sectors, into a new catalogue.

    python scripts/rerun_live_feed.py --sectors SECTORS.json --catalog docs/discoveries/catalog.json \\
        --work-dir runs/discovery-rerun --record docs/results/feed_rule_live_rerun_clipfix.json

``SECTORS.json`` maps each TIC to the SPOC 2-minute sectors its last live run reviewed (its latest two then), so a
sector released since does not change the inputs. The TOI table is the copy the last live run used
(cache/toi/toi.csv; the NASA Exoplanet Archive's TAP returned HTTP 526 that day), so the known/new classing is
compared like for like. The discovery config is unchanged (configs/discovery.toml: the Probes and the feed's weights
file; its Claude API Sentinel runs only with ANTHROPIC_API_KEY, which this re-run refuses to use, as before).
The catalogue is written from scratch: every entry in it is from this run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def cached_targets(toi_csv: Path):
    """discover.Target for every TIC in the cached TOI table (as discover.fetch_toi_targets builds them)."""
    from setuhq import benchmark_toi as B
    from setuhq import discover as Dv

    rows, fetched = B.fetch_toi_table(toi_csv)
    out = {}
    for r in rows:
        if not r.get("tid"):
            continue
        tic = int(float(r["tid"]))
        t = out.setdefault(tic, Dv.Target(tic))
        toi = Dv.Toi(name=r["toi"], period=B._num(r.get("pl_orbper")), tranmid=B._num(r.get("pl_tranmid")),
                     period_err=B._num(r.get("pl_orbpererr1")), tranmid_err=B._num(r.get("pl_tranmiderr1")),
                     duration_hours=B._num(r.get("pl_trandurh")), disposition=r.get("tfopwg_disp") or None)
        t.tois.append(toi)
        if toi.period is not None:
            t.toi_periods.append(toi.period)
        t.toi_names.append(toi.name)
    return out, fetched


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sectors", required=True, help="JSON {TIC: [sectors]} of the last live run")
    ap.add_argument("--catalog", required=True, help="the catalogue to write (overwritten)")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--record", required=True, help="the re-run's summary JSON")
    ap.add_argument("--toi-csv", default=str(ROOT / "cache/toi/toi.csv"))
    ap.add_argument("--download-dir", default=str(ROOT / "cache/mast"))
    args = ap.parse_args(argv)

    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        os.environ.pop(key, None)
    from setuhq import discover as Dv
    from setuhq import loaders
    from setuhq.config import build_reviewers, load_config

    config_path = ROOT / "configs/discovery.toml"
    sentinels = [r for r in build_reviewers(load_config(config_path).reviewers) if r.kind != "simulated"]
    if any(r.available() for r in sentinels):
        raise SystemExit("a Sentinel is available here; this re-run is Probes-only, as the live run it repeats")
    sectors = {int(k): [int(s) for s in v] for k, v in json.loads(Path(args.sectors).read_text()).items()}
    targets, fetched = cached_targets(Path(args.toi_csv))
    Dv.fetch_toi_targets = lambda: targets
    Dv.load_tess = lambda label: loaders.load_tess(label, sectors[int(label.split()[-1])], download_dir=args.download_dir)
    catalog = Path(args.catalog)
    if catalog.exists():
        catalog.unlink()
    log = Dv.run_discovery(config_path, catalog, tics=list(sectors), time_budget_s=8 * 3600, work_dir=args.work_dir,
                           cache_root=str(ROOT / "cache"))
    cat = json.loads(catalog.read_text())
    new = [c for c in cat["candidates"] if c["status"] == "new_candidate"]
    known = [c for c in cat["candidates"] if c["status"] == "known_toi"]
    record = {"when": log["time"], "targets": len(sectors),
              "rule": "two-sector rule, FAP < 0.001 over 2,000 trials (pre-registered 8909cda)",
              "toi_table": f"cache/toi/toi.csv fetched {fetched} (the copy the previous live run used)",
              "reviewers": "the three Probes with the feed's weights file (no Sentinel: no API key is used)",
              "sectors": {str(k): v for k, v in sectors.items()},
              "new_signals": len({(c["tic"], round(c.get("period_days") or 0, 3)) for c in new}), "new_entries": len(new),
              "known_signals": len({(c["tic"], c.get("toi_match")) for c in known}), "known_entries": len(known),
              "run_log": {k: v for k, v in log.items() if k not in ("tracebacks", "targets", "time")},
              "previous_run": "docs/results/feed_rule_live_rerun.json (pre-fix code)"}
    Path(args.record).write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

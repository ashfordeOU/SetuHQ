# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""``setuhq propose cheops <target>`` and ``setuhq propose lint FILE...``."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

from setuhq.propose.draft import DISCLAIMER


def _date(text: str) -> date:
    return date.fromisoformat(text)


def add_parser(sub) -> None:
    """Register ``propose`` on the main CLI's subparsers."""
    p = sub.add_parser("propose", help="prepare an observing proposal (a preparation pack; nothing is submitted)")
    psub = p.add_subparsers(dest="propose_command", required=True)

    c = psub.add_parser("cheops", help="CHEOPS Guest Observers Running Call: write a proposal preparation pack",
                        description=DISCLAIMER)
    c.add_argument("target", help="target name as SIMBAD knows it (e.g. 'TOI-1987', 'HD 39091', 'TIC 349088467')")
    c.add_argument("--programme", choices=("regular", "large", "fasttrack"), default="regular")
    c.add_argument("--orbits", type=int, help="orbits you intend to request (checked against the programme's limits)")
    c.add_argument("--cycle", help="submission cycle YYYY-MM (default: the next open one for the programme)")
    c.add_argument("--out", help="pack directory to create (default runs/propose/<name>; never overwritten)")
    c.add_argument("--name", help="pack name under runs/propose/ (default cheops-<target>-<cycle>)")
    c.add_argument("--ra", type=float, help="your RA in degrees (ICRS, J2000), instead of SIMBAD's")
    c.add_argument("--dec", type=float, help="your Dec in degrees (ICRS, J2000)")
    c.add_argument("--coord-source", choices=("target-checker", "simbad", "mast", "exofop", "gaia", "other"),
                   help="where --ra/--dec came from (ExoFOP and Gaia positions are refused: wrong epoch)")
    c.add_argument("--gmag", type=float, help="Gaia G magnitude (default: SIMBAD's)")
    c.add_argument("--event", choices=("transit", "eclipse", "flare"), default="transit")
    c.add_argument("--depth-ppm", type=float, help="event depth (transit, eclipse) or flare amplitude, ppm")
    c.add_argument("--duration-hours", type=float, help="event duration in hours")
    c.add_argument("--snr", type=float, default=10.0, help="target S/N on the event (default 10)")
    c.add_argument("--efficiency", type=float, default=0.7,
                   help="observing efficiency to assume (placeholder; take yours from the Visibility Tool)")
    c.add_argument("--flare-rate", type=float, help="flares per day above the amplitude (for --event flare)")
    c.add_argument("--t0", type=float, help="transit mid-time, BJD_TDB (or BTJD)")
    c.add_argument("--t0-err", type=float, help="its 1-sigma error, days")
    c.add_argument("--period", type=float, help="period, days")
    c.add_argument("--period-err", type=float, help="its 1-sigma error, days")
    c.add_argument("--window-start", type=_date, help="first date to observe (default: the cycle's earliest start)")
    c.add_argument("--window-end", type=_date, help="last date to observe (default 2029-12-31)")
    c.add_argument("--author-name", action="append", default=[],
                   help="a name the anonymity lint must flag (repeatable; never written into the pack)")
    c.add_argument("--offline", action="store_true", help="make no network request (cache only; checks then say 'not checked')")
    c.add_argument("--no-cache", action="store_true", help="do not read or write cache/cheops-propose/")
    c.add_argument("--today", type=_date, help=argparse_suppress())
    c.set_defaults(func=cmd_cheops)

    lint = psub.add_parser("lint", help="scan proposal text files for anything that breaks anonymity")
    lint.add_argument("files", nargs="+")
    lint.add_argument("--author-name", action="append", default=[], help="a name to flag (repeatable)")
    lint.set_defaults(func=cmd_lint)


def argparse_suppress():
    import argparse

    return argparse.SUPPRESS


def cmd_cheops(args) -> int:
    from setuhq.propose import pack, rules, sources
    from setuhq.tools import root

    print(DISCLAIMER, file=sys.stderr)
    base = root()
    now = (datetime(args.today.year, args.today.month, args.today.day, 12, tzinfo=timezone.utc)
           if args.today else datetime.now(timezone.utc))
    try:
        prog = rules.programme(args.programme)
        cy = rules.parse_cycle(args.cycle) if args.cycle else rules.next_cycle(now, prog)
    except ValueError as exc:
        print(f"setuhq propose cheops: {exc}", file=sys.stderr)
        return 2
    if cy is None:
        print("setuhq propose cheops: no open cycle left for this programme", file=sys.stderr)
        return 2
    cycle = f"{cy[0]}-{cy[1]:02d}"
    if args.out:
        out = Path(args.out)
    else:
        name = args.name or pack.default_name(args.target, cycle)
        out = Path("runs") / "propose" / name
    if out.exists() or out.is_symlink():
        print(f"setuhq propose cheops: {out} already exists; a pack is never overwritten", file=sys.stderr)
        return 2
    fetcher = sources.Fetcher(cache_dir=None if args.no_cache else base / "cache" / "cheops-propose", offline=args.offline)
    try:
        p = pack.build_pack(
            args.target, out, root=base, programme=args.programme, orbits=args.orbits, cycle=cycle, now=now,
            fetcher=fetcher, ra=args.ra, dec=args.dec, coord_source=args.coord_source, gmag=args.gmag,
            event=args.event, depth_ppm=args.depth_ppm, duration_hours=args.duration_hours, target_snr=args.snr,
            efficiency=args.efficiency, t0=args.t0, t0_err=args.t0_err, period=args.period, period_err=args.period_err,
            window_start=args.window_start, window_end=args.window_end, flare_rate=args.flare_rate,
            author_names=args.author_name, use_toi_table=not args.offline)
    except ValueError as exc:
        print(f"setuhq propose cheops: {exc}", file=sys.stderr)
        return 2
    c, st = p["cycle"], p["status"]
    print(f"pack written to {out}")
    print(f"cycle {c['cycle']}: deadline {c['deadline_local']} ({c['deadline_zone']}); earliest start {c['earliest_start']}")
    rtl = st["rtl"]
    print("RTL: " + ("not checked" if not rtl.get("checked") else "RESERVED" if rtl["reserved"] else "not on the public list"))
    arch = st["archive"]
    print("archive: " + ("not checked" if not arch.get("checked") else
                         f"already observed ({arch['n_public']} public visits)" if arch["already_observed"] else "no visits found"))
    problems = c["errors"] + p["programme"]["check"]["errors"] + p["window"]["errors"]
    for msg in problems:
        print(f"ERROR: {msg}")
    for msg in c["warnings"] + p["programme"]["check"]["warnings"] + p["target"]["coord_warnings"]:
        print(f"WARNING: {msg}")
    n_warn = sum(f["level"] == "warn" for f in p["anonymity_lint"])
    print(f"anonymity lint: {n_warn} warning(s) (see anonymity-lint.txt)")
    print("Estimates only. Confirm with ESA's Exposure Time Calculator, Visibility Tool and Scheduling Feasibility "
          "Checker; nothing was submitted.")
    return 1 if problems else 0


def cmd_lint(args) -> int:
    from setuhq.propose.draft import format_findings, lint_files

    findings = lint_files([Path(f) for f in args.files], author_names=args.author_name)
    print(format_findings(findings))
    return 1 if any(f["level"] == "warn" for f in findings) else 0

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Command-line interface: ``setuhq run``, ``setuhq benchmark``, ``setuhq calibrate``, ``setuhq site``, ``setuhq plate`` and more."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from setuhq.calibrate import calibrate_weights, calibration_path, calibration_record, identity, weights_from_skills
from setuhq.config import build_reviewers, load_config
from setuhq.loaders import load_cheops, load_tess
from setuhq.pipeline import run_pipeline


def _load_targets(config):
    lightcurves = []
    for target in config.targets:
        if target.mission == "TESS":
            if not target.id:
                raise SystemExit("TESS targets need an 'id' (for example 'TIC 261136679')")
            lightcurves.extend(load_tess(target.id, target.sectors))
        elif target.mission == "CHEOPS":
            if not target.path:
                raise SystemExit("CHEOPS targets need a 'path' to a light-curve FITS file")
            lightcurves.append(load_cheops(target.path, target=target.id))
        else:
            raise SystemExit(f"unsupported mission {target.mission!r}")
    return lightcurves


DEFAULT_WEIGHTS = "docs/results/reviewer_weights_full_panel.json"


def resolve_weights(config, explicit: str | None, default: str | None = DEFAULT_WEIGHTS) -> tuple[dict | None, str]:
    """The reviewer weights a run uses, and where they came from.

    An explicit ``--weights`` file always wins. Otherwise the calibrated
    weights in ``default`` are used when the file exists and covers every
    Probe in the config; a Sentinel it does not cover (a new provider or
    model) then gets the floor weight and is labelled uncalibrated
    (``calibrate.apply_calibration``). If not, every reviewer weighs 1.0.
    """
    from setuhq.config import SENTINEL_TYPES

    if explicit:
        return json.loads(Path(explicit).read_text()), str(explicit)
    if default and Path(default).exists():
        calibrated = json.loads(Path(default).read_text())
        ids = {str(spec.get("id")) for spec in config.reviewers}
        sentinels = {str(spec.get("id")) for spec in config.reviewers if spec.get("type") in SENTINEL_TYPES}
        if ids and set(calibrated) == ids:
            return {k: float(v) for k, v in calibrated.items()}, str(default)
        if ids and ids < set(calibrated) and not ids & sentinels:
            # A Probes-only run: the calibrated weights of the Probes it has, no Sentinel to weigh.
            return {k: float(v) for k, v in calibrated.items() if k in ids}, f"{default} (Probes only)"
        if ids & set(calibrated) and (ids - set(calibrated)) <= sentinels:
            new = ", ".join(sorted(ids - set(calibrated)))
            return ({k: float(v) for k, v in calibrated.items() if k in ids},
                    f"{default}; uncalibrated Sentinels at the floor weight: {new}")
        return None, f"uniform 1.0 ({default} reviewer ids do not match the config)"
    return None, "uniform 1.0 (no calibrated weights file)"


def load_calibration_record(weights_file: str | None) -> dict | None:
    """The calibration record stored next to a weights file, or None."""
    if not weights_file:
        return None
    path = calibration_path(weights_file)
    return json.loads(path.read_text()) if path.exists() else None


def cmd_run(args) -> int:
    config = load_config(args.config)
    reviewers = build_reviewers(config.reviewers, cache_root=args.cache)
    default = None if args.uniform_weights else args.calibrated_weights
    weights, source = resolve_weights(config, args.weights, default)
    print(f"reviewer weights: {source}")
    record = load_calibration_record(args.weights or (default if weights is not None else None))
    summary = run_pipeline(config, _load_targets(config), reviewers, args.out, weights=weights, weights_source=source,
                           calibration=record)
    print(f"light curves: {summary.n_light_curves}")
    print(f"subjects:     {summary.n_subjects}")
    print(f"classifications: {summary.n_classifications}")
    print(f"consensus events: {summary.n_consensus} ({summary.n_passed} pass vetting)")
    if summary.skipped_reviewers:
        reasons = {r.reviewer_id: (getattr(r, "unavailable_reason", lambda: None)() or "unavailable") for r in reviewers}
        print("skipped (unavailable) reviewers: " + ", ".join(f"{rid} ({reasons.get(rid)})" for rid in summary.skipped_reviewers))
    print(f"outputs in {summary.run_dir}")
    return 0


def cmd_rebuild(args) -> int:
    from setuhq.pipeline import rebuild_run

    config = load_config(args.config)
    candidates = rebuild_run(config, _load_targets(config), args.run_dir)
    print(f"rebuilt {len(candidates)} consensus events ({sum(c.passed for c in candidates)} pass vetting) in {args.run_dir}")
    return 0


def cmd_calibrate(args) -> int:
    config = load_config(args.config)
    reviewers = [r for r in build_reviewers(config.reviewers, cache_root=args.cache) if r.available()]
    skills = calibrate_weights(
        reviewers,
        n_injected=args.n_injected,
        n_empty=args.n_empty,
        seed=args.seed,
        image_dir=args.image_dir,
    )
    weights = weights_from_skills(skills)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(weights, indent=2, sort_keys=True))
    # The rates and sample sizes behind the weights, next to them, for the Panel's calibration plane.
    record = calibration_record(skills, weights_file=Path(args.out).name,
                                source=f"setuhq calibrate {args.config} (seed {args.seed})",
                                identities={r.reviewer_id: identity(r) for r in reviewers if identity(r)})
    calibration_path(args.out).write_text(json.dumps(record, indent=2))
    for skill in skills.values():
        print(f"{skill.reviewer_id:24s} TPR={skill.tpr:.3f} FPR={skill.fpr:.3f} weight={skill.weight:.3f}")
    print(f"weights written to {args.out}, rates to {calibration_path(args.out)}")
    return 0


def cmd_benchmark(args) -> int:
    from setuhq.benchmark import injection_recovery, to_markdown

    config = load_config(args.config)
    reviewers = [r for r in build_reviewers(config.reviewers, cache_root=args.cache) if r.available()]
    weights = json.loads(Path(args.weights).read_text()) if args.weights else None
    result = injection_recovery(
        reviewers,
        weights,
        config,
        depths_ppm=tuple(args.depths),
        durations_hours=tuple(args.durations),
        n_per_cell=args.n_per_cell,
        n_empty=args.n_empty,
        seed=args.seed,
        image_dir=args.image_dir,
    )
    text = to_markdown(result, title=args.title, weights=weights or {})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text)
    print(text)
    return 0


def cmd_report(args) -> int:
    from setuhq.report import build_report

    path = build_report(
        args.run_dir,
        args.out,
        title=args.title,
        validation_md=args.validation,
        benchmark_md=args.benchmark,
    )
    print(f"site written to {path}")
    return 0


def cmd_discover(args) -> int:
    from setuhq.discover import run_discovery
    from setuhq.report import build_discovery_site

    log = run_discovery(
        args.config,
        args.catalog,
        batch_size=args.batch_size,
        time_budget_s=args.time_budget_min * 60.0,
        work_dir=args.work_dir,
        cache_root=args.cache,
    )
    site = build_discovery_site(args.catalog, args.site)
    print(f"targets reviewed this run: {len(log['targets'])}, new candidates: {log['new']}, known: {log['known']}")
    for error in log["errors"]:
        print(f"error: {error}")
    print(f"catalogue {args.catalog}, site {site}")
    return 0


def _toi_targets(args):
    """The archive TOI table (TIC → Target) from a cached JSON file, or fetched (and cached) when allowed."""
    from setuhq.discover import Target, Toi, fetch_toi_targets

    path = Path(args.toi_cache)
    if path.exists():
        raw = json.loads(path.read_text())
        return {int(k): Target(int(k), tois=[Toi(**t) for t in v]) for k, v in raw.items()}
    try:
        targets = fetch_toi_targets()
    except Exception as exc:  # noqa: BLE001
        print(f"TOI table unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({str(k): [vars(t) for t in v.tois] for k, v in targets.items()}))
    return targets


def cmd_export(args) -> int:
    from setuhq.exofop import CTOI_FIELDS_STATUS, export_run

    tois = _toi_targets(args)
    if tois is None and not args.allow_unchecked:
        print("setuhq export: refusing to export without the TOI duplicate check (no TOI table); nothing written. "
              "Pass --allow-unchecked to export rows marked 'TOI check not done'.", file=sys.stderr)
        return 2
    summary = export_run(args.run_dir, args.out, tois=tois, allow_unchecked=args.allow_unchecked,
                         days=args.days)
    print(f"CTOI-style rows: {len(summary['rows'])}, excluded: {len(summary['excluded'])}, "
          f"predicted windows: {summary['windows']['count']}")
    for row in summary["excluded"]:
        print(f"  excluded {row['candidate_id']}: {row['reason']}")
    print(f"field list: {CTOI_FIELDS_STATUS}")
    print(f"outputs in {args.out}")
    return 0


def cmd_batch(args) -> int:
    from setuhq.batch import read_targets, run_batch

    targets = read_targets(args.targets) if args.targets else []
    targets += [int(t) for t in args.tic or []]
    if not targets:
        raise SystemExit("give --targets FILE or --tic N [N ...]")
    weights, source = resolve_weights(load_config(args.config), args.weights)
    print(f"reviewer weights: {source}")
    tois = _toi_targets(args) if args.toi_cache else None
    log = run_batch(args.config, targets, work_dir=args.work_dir, cache_root=args.cache,
                    sectors_per_target=args.sectors, retries=args.retries,
                    time_budget_s=args.time_budget_min * 60.0 if args.time_budget_min else None,
                    max_targets=args.max_targets, weights=weights, toi_targets=tois)
    print(f"done {log['done']}, no data {log['no_data']}, failed {log['failed']}, skipped (already done) "
          f"{log['skipped']}, remaining {log['remaining']}; {log['star_sectors_per_hour']:.1f} star-sectors per hour"
          + (f"; stopped: {log['stopped']}" if log["stopped"] else ""))
    return 0


def cmd_sweep(args) -> int:
    from setuhq.sweep import reclassify_sweep, run_sweep

    if args.reclassify:
        reclassify_sweep(args.config, args.sector, limit=args.limit, out_dir=args.out, cache_root=args.cache,
                         contributor=args.contributor, min_interval=args.min_interval, rule_changes=args.rule_change or [],
                         search_commit=args.search_commit, classified_commit=args.classified_commit)
        return 0

    res = run_sweep(args.config, args.sector, limit=args.limit, out_dir=args.out, cache_root=args.cache, workers=args.workers,
                    min_interval=args.min_interval, time_budget_s=args.time_budget_min * 60.0 if args.time_budget_min else None,
                    control=not args.no_control, contributor=args.contributor, weights_path=args.weights)
    print(f"sector {res.sector}: {res.done} of the slice done ({res.ran} this run, {res.skipped} done before)"
          + (f"; stopped: {res.stopped}, run the same command again to resume" if res.stopped else ""))
    for err in res.errors:
        print(f"error: {err}")
    print(f"record {res.record_path}; catalogue {Path(args.out) / 'catalogue.json'}")
    return 0


def cmd_bundle(args) -> int:
    from setuhq.contrib import make_bundle

    path = make_bundle(args.record, args.out, contributor=args.contributor)
    print(f"bundle written to {path}, sealed with sha256 content hashes (not a signature). Check it, then share the directory "
          "(or a zip of it) in a pull request. It holds no keys or credentials.")
    return 0


def cmd_ingest(args) -> int:
    from setuhq.contrib import BundleRefused, ingest_bundle

    try:
        result = ingest_bundle(args.bundle, sweep_dir=args.sweep_dir, verify_lightcurves=args.verify_lightcurves,
                               attested_by=args.attested_by, accept_sentinels=args.accept_sentinels, cache_root=args.cache)
    except BundleRefused as exc:
        print(f"setuhq ingest: refused: {exc}", file=sys.stderr)
        return 1
    v = result["verified"]
    print(f"ingested {result['bundle_id']} from {result['contributor']}: {result['star_sectors']} star-sectors "
          f"({result['new_star_sectors']} new, credited), {result['entries']} entries; light curves fetched again: "
          f"{len(v['lightcurves_refetched'])}, searched again: {len(v['searched_again'])}; catalogue rebuilt at {result['catalogue']}")
    return 0


def cmd_check_sweep(args) -> int:
    import os

    from setuhq.sweep import MISSING_BASE, build_catalogue, check_catalogue, check_ledger_append_only, default_ledger_base

    if args.fix:
        build_catalogue(args.sweep_dir)
    problems = check_catalogue(args.sweep_dir)
    if args.ledger_base:
        base = default_ledger_base(args.sweep_dir) if args.ledger_base == "auto" else args.ledger_base
        ledger = check_ledger_append_only(args.sweep_dir, base)
        if ledger and ledger[0].startswith(MISSING_BASE) and not os.environ.get("CI"):
            # Local runs only: hosted CI (CI set) fails on a missing base.
            print(f"setuhq check-sweep: note: {ledger[0]}; the ledger's append-only check is skipped (it fails when CI is set)")
            ledger = []
        problems += ledger
    for p in problems:
        print(f"setuhq check-sweep: {p}", file=sys.stderr)
    if not problems:
        print(f"{args.sweep_dir}: every contribution ingested and intact; catalogue.json matches its verified sources")
    return 1 if problems else 0


def cmd_dashboard(args) -> int:
    from setuhq.dashboard import build_dashboard

    path = build_dashboard(args.run_dir, args.out, title=args.title, catalog_path=args.catalog)
    print(f"dashboard written to {path}")
    return 0


def cmd_docket(args) -> int:
    from setuhq.docket import build_docket

    path = build_docket(args.run_dir, args.out, title=args.title, star=args.star, refresh_crossmatch=args.refresh_crossmatch,
                        require_crossmatch=not args.allow_missing_crossmatch)
    print(f"docket written to {path}")
    return 0


def cmd_site(args) -> int:
    from setuhq.site import build_site, check_asset_budget, check_budget

    runs = list(args.run_dir)
    path = build_site(runs[0], args.out, title=args.title, catalog_path=args.catalog,
                      weights_path=args.weights, star=args.star, require_crossmatch=not args.allow_missing_crossmatch,
                      sweep_path=args.sweep, validation_md=args.validation, benchmark_md=args.benchmark,
                      extras=not args.no_extras, extra_runs=runs[1:], showcase_path=args.showcase)
    print(f"site written to {path.parent}")
    over = check_budget(path.parent)
    for line in over:
        print(f"over the per-page budget: {line}", file=sys.stderr)
    assets = check_asset_budget(path.parent)
    for line in assets:
        print(f"over an asset budget: {line}", file=sys.stderr)
    return 1 if over or assets else 0


def cmd_plate(args) -> int:
    from setuhq.plate import build_plate

    path = build_plate(args.run_dir, args.out, title=args.title, catalog_path=args.catalog, star=args.star,
                       require_crossmatch=not args.allow_missing_crossmatch)
    print(f"plates written to {path}")
    return 0


def cmd_crossmatch(args) -> int:
    from setuhq.docket import CrossmatchUnavailable, run_crossmatch

    try:
        result = run_crossmatch(args.run_dir, args.star)
    except CrossmatchUnavailable as exc:
        print(f"setuhq crossmatch: {exc}", file=sys.stderr)
        return 1
    print(f"cross-match {result['status']}: {len(result['planets'])} archive planet(s) stored in {args.run_dir}/crossmatch.json")
    return 0


def cmd_leaderboard(args) -> int:
    """Score one submission on the frozen benchmark's held-out half, or rebuild the whole table."""
    from setuhq import leaderboard as L

    sample = L.load_sample()
    benchmark = json.loads(L.BENCHMARK.read_text())
    inputs = json.loads(L.INPUTS.read_text()) if L.INPUTS.exists() else L.public_inputs(sample)
    if L.inputs_sha256(inputs) != L.inputs_sha256(L.public_inputs(sample)):
        print(f"{L.INPUTS} does not match the frozen sample; run scripts/leaderboard_seed.py", file=sys.stderr)
        return 1
    if args.submission:
        try:
            sub = json.loads(Path(args.submission).read_text())
            scores = L.score(sub, sample, inputs, benchmark)
        except (ValueError, OSError) as exc:  # L.Refused is a ValueError, as is a JSON syntax error
            reasons = exc.reasons if isinstance(exc, L.Refused) else [f"not a readable JSON file: {exc}"]
            print(f"refused: {args.submission}", file=sys.stderr)
            for reason in reasons:
                print(f"  - {reason}", file=sys.stderr)
            return 2
        print(json.dumps({"id": sub["id"], "name": sub["name"], "scope": sub["scope"], "scores": scores}, indent=1))
        return 0
    res = L.build(sample, inputs, benchmark, L.load_submissions(args.submissions))
    L.write_results(res)
    print(f"{len(res['entries'])} entries scored, {len(res['refused'])} refused: {L.RESULTS_MD}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="setuhq", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the pipeline on the targets in a config file")
    run.add_argument("config")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--weights", help="JSON file of reviewer weights from 'setuhq calibrate' (overrides the default)")
    run.add_argument("--calibrated-weights", default=DEFAULT_WEIGHTS,
                     help="calibrated weights used by default when their reviewer ids match the config's")
    run.add_argument("--uniform-weights", action="store_true", help="weigh every reviewer 1.0")
    run.add_argument("--cache", default="cache", help="cache root for Claude responses")
    run.set_defaults(func=cmd_run)

    rebuild = sub.add_parser("rebuild", help="re-vet a stored run (fit, FAP, flags) from its stored classifications")
    rebuild.add_argument("run_dir")
    rebuild.add_argument("config")
    rebuild.set_defaults(func=cmd_rebuild)

    calibrate = sub.add_parser("calibrate", help="estimate reviewer weights by injection")
    calibrate.add_argument("config")
    calibrate.add_argument("--out", required=True, help="weights JSON to write")
    calibrate.add_argument("--n-injected", type=int, default=40)
    calibrate.add_argument("--n-empty", type=int, default=40)
    calibrate.add_argument("--seed", type=int, default=0)
    calibrate.add_argument("--image-dir", help="where to render calibration images, if reviewers need them")
    calibrate.add_argument("--cache", default="cache")
    calibrate.set_defaults(func=cmd_calibrate)

    bench = sub.add_parser("benchmark", help="injection-recovery benchmark for the configured panel")
    bench.add_argument("config")
    bench.add_argument("--out", required=True, help="markdown file to write")
    bench.add_argument("--title", default="Injection-recovery benchmark")
    bench.add_argument("--weights", help="weights JSON")
    bench.add_argument("--depths", type=float, nargs="+", default=[300.0, 1000.0, 3000.0])
    bench.add_argument("--durations", type=float, nargs="+", default=[1.0, 2.0, 4.0])
    bench.add_argument("--n-per-cell", type=int, default=20)
    bench.add_argument("--n-empty", type=int, default=40)
    bench.add_argument("--seed", type=int, default=0)
    bench.add_argument("--image-dir")
    bench.add_argument("--cache", default="cache")
    bench.set_defaults(func=cmd_benchmark)
    discover = sub.add_parser("discover", help="run one scheduled discovery batch and update the catalogue")
    discover.add_argument("config")
    discover.add_argument("--catalog", default="docs/discoveries/catalog.json")
    discover.add_argument("--site", default="site/discoveries")
    discover.add_argument("--batch-size", type=int, default=20)
    discover.add_argument("--time-budget-min", type=float, default=270.0)
    discover.add_argument("--work-dir", default="runs/discovery")
    discover.add_argument("--cache", default="cache")
    discover.set_defaults(func=cmd_discover)

    export = sub.add_parser("export", help="write an ExoFOP CTOI-style table and predicted transit windows for a run")
    export.add_argument("run_dir")
    export.add_argument("--out", required=True)
    export.add_argument("--toi-cache", default="cache/toi_table.json",
                        help="cached archive TOI table (fetched and written here when missing)")
    export.add_argument("--allow-unchecked", action="store_true",
                        help="export even when the TOI duplicate check cannot be done (rows say so)")
    export.add_argument("--days", type=float, default=365.25, help="how far ahead to predict transit windows")
    export.set_defaults(func=cmd_export)

    batch = sub.add_parser("batch", help="run the discover flow over a target list, cached and resumable")
    batch.add_argument("config")
    batch.add_argument("--targets", help="text file of TIC ids, one per line")
    batch.add_argument("--tic", nargs="+", help="TIC ids")
    batch.add_argument("--work-dir", default="runs/batch")
    batch.add_argument("--cache", default="cache")
    batch.add_argument("--sectors", type=int, default=2, help="latest sectors per target")
    batch.add_argument("--retries", type=int, default=1, help="retries of a failed target in later sessions")
    batch.add_argument("--time-budget-min", type=float, default=None)
    batch.add_argument("--max-targets", type=int, default=None, help="stop after this many targets this session")
    batch.add_argument("--weights", help="reviewer weights JSON")
    batch.add_argument("--toi-cache", help="cached archive TOI table, to tag feed entries known_toi or new_candidate")
    batch.set_defaults(func=cmd_batch)

    sweep = sub.add_parser("sweep", help="search a TESS sector's SPOC 2-minute targets (resumable) into the variability catalogue")
    sweep.add_argument("config", help="sweep config, e.g. configs/sweep.toml (Probes) or configs/sweep_sentinels.toml")
    sweep.add_argument("--sector", type=int, required=True)
    sweep.add_argument("--limit", type=int, required=True, help="how many targets of the sector, in sweep order")
    sweep.add_argument("--out", default="docs/sweep", help="where the sector record and catalogue.json go")
    sweep.add_argument("--cache", default="cache", help="cache root: target lists, light-curve files, per-star records")
    sweep.add_argument("--workers", type=int, default=1, help="processes searching stars at once (downloads stay one at a time)")
    sweep.add_argument("--min-interval", type=float, default=1.0, help="seconds between MAST requests (at least)")
    sweep.add_argument("--time-budget-min", type=float, default=None, help="stop starting new stars after this many minutes")
    sweep.add_argument("--no-control", action="store_true", help="skip the flux-inverted control run of each star")
    sweep.add_argument("--contributor", default="setuhq", help="the name credited for this sweep")
    sweep.add_argument("--reclassify", action="store_true",
                       help="re-apply the classification rules to the stored star-sectors (after a change to variables.py only)")
    sweep.add_argument("--rule-change", action="append", help="with --reclassify: what changed in the rules (repeat for each)")
    sweep.add_argument("--search-commit", help="with --reclassify: the git revision that searched records naming one code only")
    sweep.add_argument("--classified-commit", help="with --reclassify: the git revision that last classified such records")
    sweep.add_argument("--weights", default="docs/results/reviewer_weights_full_panel.json",
                       help="calibrated weights; a reviewer not in the file weighs 1.0")
    sweep.set_defaults(func=cmd_sweep)

    bundle = sub.add_parser("bundle", help="export a sweep's sector record as a contribution bundle, sealed with content hashes")
    bundle.add_argument("record", help="the sector record, e.g. my-sweep/sector_0005.json.gz")
    bundle.add_argument("--contributor", required=True, help="the name to credit (yours to choose; shown on the site)")
    bundle.add_argument("--out", required=True, help="bundle directory to write")
    bundle.set_defaults(func=cmd_bundle)

    ingest = sub.add_parser("ingest", help="validate a contribution bundle and merge it into the catalogue, with credit")
    ingest.add_argument("bundle", help="bundle directory or .zip")
    ingest.add_argument("--sweep-dir", default="docs/sweep")
    ingest.add_argument("--verify-lightcurves", type=int, default=None,
                        help="how many star-sectors to fetch and search again at random, beyond every one with a planet candidate "
                             "or an entry in a class that exceeds its null (default: max(3, 5%%)); every entry must agree")
    ingest.add_argument("--attested-by", help="the GitHub login of the person who sent the bundle (the pull request's author)")
    ingest.add_argument("--accept-sentinels", action="store_true",
                        help="accept a bundle with Sentinels, whose dips cannot be searched again here (the catalogue says so)")
    ingest.add_argument("--cache", default="cache")
    ingest.set_defaults(func=cmd_ingest)

    check = sub.add_parser("check-sweep", help="check that every contribution was ingested and is intact, and that the "
                                               "catalogue is what its verified sources rebuild to")
    check.add_argument("--sweep-dir", default="docs/sweep")
    check.add_argument("--fix", action="store_true", help="rebuild catalogue.json from the verified sources")
    check.add_argument("--ledger-base", help="a git ref whose ingest ledger this one must only extend; 'auto' is the merge-base with the base "
                       "branch (SETUHQ_BASE, GITHUB_BASE_REF or the remote's default). A missing base fails when CI is set")
    check.set_defaults(func=cmd_check_sweep)

    dash = sub.add_parser("dashboard", help="build the interactive dashboard from a run and optional discovery catalogue")
    dash.add_argument("run_dir")
    dash.add_argument("--out", required=True)
    dash.add_argument("--title", default="SetuHQ dashboard")
    dash.add_argument("--catalog", help="discovery catalogue JSON to include")
    dash.set_defaults(func=cmd_dashboard)

    docket = sub.add_parser("docket", help="build the candidate case-file view for a run")
    docket.add_argument("run_dir")
    docket.add_argument("--out", required=True)
    docket.add_argument("--title", default="SetuHQ docket")
    docket.add_argument("--star", help="star name for the archive cross-match (hostname or pl_name); TIC targets also match on tic_id")
    docket.add_argument("--refresh-crossmatch", action="store_true", help="run 'setuhq crossmatch' first: query the archive and store crossmatch.json")
    docket.add_argument("--allow-missing-crossmatch", action="store_true",
                     help="build even when no stored archive cross-match is usable; the page then prints the stored error")
    docket.set_defaults(func=cmd_docket)

    for name, helptext in (("site", "build the website (every page, the shared files, the reports, plates and case files) from one or more runs"),
                           ("app", "the same as 'setuhq site' (the old name, when the site was one app page)")):
        site = sub.add_parser(name, help=helptext)
        site.add_argument("run_dir", nargs="+", help="the stored runs: the lead run first (the sky map, the panel and the home "
                                                    "page's reference check), then any other example runs; each gets its dips' "
                                                    "pages, its case file, its plates and its report")
        site.add_argument("--showcase", default="docs/results/showcase.json",
                          help="the example runs' descriptions and literature comparisons (scripts/showcase_compare.py)")
        site.add_argument("--out", required=True, help="the site's root folder (site/ for setuhq.com)")
        site.add_argument("--title", default="SetuHQ")
        site.add_argument("--catalog", help="discovery catalogue JSON for the Candidates and Runs pages")
        site.add_argument("--weights", default="docs/results/reviewer_weights_full_panel.json",
                          help="calibrated reviewer weights JSON shown on the Evidence page")
        site.add_argument("--star", help="star name for the case file's archive cross-match, as in 'setuhq docket'")
        site.add_argument("--sweep", default="docs/sweep/catalogue.json",
                          help="the sweep catalogue (setuhq sweep) for Everything that dims, the home counter and the sky layer")
        site.add_argument("--validation", default="docs/results/pi_men_validation.md", help="validation notes for the run report")
        site.add_argument("--benchmark", default="docs/results/injection_recovery_simulated_panel.md",
                          help="benchmark notes for the run report")
        site.add_argument("--no-extras", action="store_true", help="leave out the run report, the plates and the stand-alone case file")
        site.add_argument("--allow-missing-crossmatch", action="store_true",
                          help="build even when no stored archive cross-match is usable; the page then prints the stored error")
        site.set_defaults(func=cmd_site)

    xmatch = sub.add_parser("crossmatch", help="query the NASA Exoplanet Archive for the run's targets and store crossmatch.json")
    xmatch.add_argument("run_dir")
    xmatch.add_argument("--star", help="star name (hostname or pl_name); TIC targets also match on tic_id")
    xmatch.set_defaults(func=cmd_crossmatch)

    plate = sub.add_parser("plate", help="build the print-ready plates page: one plate per star, with captions")
    plate.add_argument("run_dir")
    plate.add_argument("--out", required=True)
    plate.add_argument("--title", default="SetuHQ plates")
    plate.add_argument("--catalog", help="discovery catalogue JSON: its stars get plates and join the river of time")
    plate.add_argument("--star", help="star name for the archive cross-match, as in 'setuhq docket'")
    plate.add_argument("--allow-missing-crossmatch", action="store_true",
                     help="build even when no stored archive cross-match is usable; the page then prints the stored error")
    plate.set_defaults(func=cmd_plate)

    report = sub.add_parser("report", help="build a static HTML report site from a run directory")
    report.add_argument("run_dir")
    report.add_argument("--out", required=True, help="site directory to write")
    report.add_argument("--title", default="SetuHQ run")
    report.add_argument("--validation", help="validation markdown to embed")
    report.add_argument("--benchmark", help="benchmark markdown to embed")
    report.set_defaults(func=cmd_report)

    lb = sub.add_parser("leaderboard", help="score a submission on the frozen real-TOI benchmark's held-out half, "
                                            "or rebuild docs/leaderboard from every stored submission")
    lb.add_argument("submission", nargs="?", help="a submission JSON (docs/leaderboard/README.md); omit to rebuild the table")
    lb.add_argument("--submissions", default=str(Path(__file__).resolve().parents[2] / "docs/leaderboard/submissions"),
                    help="directory of submissions to score when rebuilding")
    lb.set_defaults(func=cmd_leaderboard)

    # Everything after 'mcp' goes to setuhq-mcp unchanged (main() hands it over before this parser runs), so
    # 'setuhq mcp --list-tools' and 'setuhq mcp --http 8080' mean what they mean for setuhq-mcp. It exists so a
    # launcher that runs the package's own command ('uvx --from "setuhq[mcp]" setuhq mcp', the MCP registry
    # entry in server.json) starts the server.
    mcp = sub.add_parser("mcp", add_help=False, help="start the MCP server over stdio, as setuhq-mcp does "
                                                     "(needs the mcp extra: pip install 'setuhq[mcp]')")
    mcp.add_argument("args", nargs=argparse.REMAINDER)
    mcp.set_defaults(func=lambda args: cmd_mcp(args.args))
    return parser


MCP_MISSING = ("setuhq mcp: the MCP server needs the MCP SDK, which is the 'mcp' extra: "
               "pip install 'setuhq[mcp]' (or, without installing, uvx --from 'setuhq[mcp]' setuhq mcp)")


def cmd_mcp(argv: list[str]) -> int:
    """``setuhq mcp [setuhq-mcp options]``: the MCP server, with a plain error when the SDK is not installed."""
    import importlib.util

    no_sdk_needed = {"--list-tools", "--version", "-h", "--help"}
    if importlib.util.find_spec("mcp") is None and not no_sdk_needed & set(argv):
        print(MCP_MISSING, file=sys.stderr)
        return 2
    from setuhq import mcp_server

    return mcp_server.main(argv)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["mcp"]:
        return cmd_mcp(argv[1:])
    args = build_parser().parse_args(argv)
    from setuhq.docket import CrossmatchUnavailable

    try:
        return args.func(args)
    except CrossmatchUnavailable as exc:
        print(f"setuhq {args.command}: {exc}. Run 'setuhq crossmatch {getattr(args, 'run_dir', '<run>')}', "
              "or pass --allow-missing-crossmatch to build a page that states the error.", file=sys.stderr)
        return 2


LEGACY_NOTICE = "exoplan: this command is now 'setuhq'; the 'exoplan' alias is deprecated and will be removed in a later release."


def legacy_main(argv=None) -> int:
    """The deprecated ``exoplan`` command: one line on stderr, then exactly ``setuhq``."""
    print(LEGACY_NOTICE, file=sys.stderr)
    return main(argv)


if __name__ == "__main__":
    sys.exit(main())

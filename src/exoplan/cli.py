"""Command-line interface: ``exoplan run``, ``exoplan benchmark``, ``exoplan calibrate``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from exoplan.calibrate import calibrate_weights, weights_from_skills
from exoplan.config import build_reviewers, load_config
from exoplan.loaders import load_cheops, load_tess
from exoplan.pipeline import run_pipeline


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


def cmd_run(args) -> int:
    config = load_config(args.config)
    reviewers = build_reviewers(config.reviewers, cache_root=args.cache)
    weights = None
    if args.weights:
        weights = json.loads(Path(args.weights).read_text())
    summary = run_pipeline(config, _load_targets(config), reviewers, args.out, weights=weights)
    print(f"light curves: {summary.n_light_curves}")
    print(f"subjects:     {summary.n_subjects}")
    print(f"classifications: {summary.n_classifications}")
    print(f"consensus events: {summary.n_consensus} ({summary.n_passed} pass vetting)")
    if summary.skipped_reviewers:
        print(f"skipped (unavailable) reviewers: {', '.join(summary.skipped_reviewers)}")
    print(f"outputs in {summary.run_dir}")
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
    for skill in skills.values():
        print(f"{skill.reviewer_id:24s} TPR={skill.tpr:.3f} FPR={skill.fpr:.3f} weight={skill.weight:.3f}")
    print(f"weights written to {args.out}")
    return 0


def cmd_benchmark(args) -> int:
    from exoplan.benchmark import injection_recovery, to_markdown

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
    from exoplan.report import build_report

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
    from exoplan.discover import run_discovery
    from exoplan.report import build_discovery_site

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="exoplan", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the pipeline on the targets in a config file")
    run.add_argument("config")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--weights", help="JSON file of reviewer weights from 'exoplan calibrate'")
    run.add_argument("--cache", default="cache", help="cache root for Claude responses")
    run.set_defaults(func=cmd_run)

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

    report = sub.add_parser("report", help="build a static HTML report site from a run directory")
    report.add_argument("run_dir")
    report.add_argument("--out", required=True, help="site directory to write")
    report.add_argument("--title", default="exoplan run")
    report.add_argument("--validation", help="validation markdown to embed")
    report.add_argument("--benchmark", help="benchmark markdown to embed")
    report.set_defaults(func=cmd_report)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

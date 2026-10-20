"""Command-line interface: ``exoplan run``, ``exoplan benchmark``, ``exoplan calibrate``, ``exoplan app``, ``exoplan plate`` and more."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from exoplan.calibrate import calibrate_weights, calibration_path, calibration_record, weights_from_skills
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


DEFAULT_WEIGHTS = "docs/results/reviewer_weights_full_panel.json"


def resolve_weights(config, explicit: str | None, default: str | None = DEFAULT_WEIGHTS) -> tuple[dict | None, str]:
    """The reviewer weights a run uses, and where they came from.

    An explicit ``--weights`` file always wins. Otherwise the calibrated
    weights in ``default`` are used when the file exists and its reviewer ids
    are exactly the config's reviewer ids. If not, every reviewer weighs 1.0.
    """
    if explicit:
        return json.loads(Path(explicit).read_text()), str(explicit)
    if default and Path(default).exists():
        calibrated = json.loads(Path(default).read_text())
        ids = {str(spec.get("id")) for spec in config.reviewers}
        if ids and set(calibrated) == ids:
            return {k: float(v) for k, v in calibrated.items()}, str(default)
        return None, f"uniform 1.0 ({default} reviewer ids do not match the config)"
    return None, "uniform 1.0 (no calibrated weights file)"


def cmd_run(args) -> int:
    config = load_config(args.config)
    reviewers = build_reviewers(config.reviewers, cache_root=args.cache)
    default = None if args.uniform_weights else args.calibrated_weights
    weights, source = resolve_weights(config, args.weights, default)
    print(f"reviewer weights: {source}")
    summary = run_pipeline(config, _load_targets(config), reviewers, args.out, weights=weights, weights_source=source)
    print(f"light curves: {summary.n_light_curves}")
    print(f"subjects:     {summary.n_subjects}")
    print(f"classifications: {summary.n_classifications}")
    print(f"consensus events: {summary.n_consensus} ({summary.n_passed} pass vetting)")
    if summary.skipped_reviewers:
        print(f"skipped (unavailable) reviewers: {', '.join(summary.skipped_reviewers)}")
    print(f"outputs in {summary.run_dir}")
    return 0


def cmd_rebuild(args) -> int:
    from exoplan.pipeline import rebuild_run

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
                                source=f"exoplan calibrate {args.config} (seed {args.seed})")
    calibration_path(args.out).write_text(json.dumps(record, indent=2))
    for skill in skills.values():
        print(f"{skill.reviewer_id:24s} TPR={skill.tpr:.3f} FPR={skill.fpr:.3f} weight={skill.weight:.3f}")
    print(f"weights written to {args.out}, rates to {calibration_path(args.out)}")
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


def cmd_dashboard(args) -> int:
    from exoplan.dashboard import build_dashboard

    path = build_dashboard(args.run_dir, args.out, title=args.title, catalog_path=args.catalog)
    print(f"dashboard written to {path}")
    return 0


def cmd_docket(args) -> int:
    from exoplan.docket import build_docket

    path = build_docket(args.run_dir, args.out, title=args.title, star=args.star, refresh_crossmatch=args.refresh_crossmatch,
                        require_crossmatch=not args.allow_missing_crossmatch)
    print(f"docket written to {path}")
    return 0


def cmd_app(args) -> int:
    from exoplan.app import build_app

    path = build_app(args.run_dir, args.out, title=args.title, catalog_path=args.catalog,
                     weights_path=args.weights, star=args.star, require_crossmatch=not args.allow_missing_crossmatch)
    print(f"app written to {path}")
    if args.landing:
        from exoplan.app import build_landing

        landing = build_landing(args.run_dir, args.landing, title=args.title, catalog_path=args.catalog,
                                weights_path=args.weights, app_href=args.landing_app_href)
        print(f"landing page written to {landing}")
    return 0


def cmd_plate(args) -> int:
    from exoplan.plate import build_plate

    path = build_plate(args.run_dir, args.out, title=args.title, catalog_path=args.catalog, star=args.star,
                       require_crossmatch=not args.allow_missing_crossmatch)
    print(f"plates written to {path}")
    return 0


def cmd_crossmatch(args) -> int:
    from exoplan.docket import CrossmatchUnavailable, run_crossmatch

    try:
        result = run_crossmatch(args.run_dir, args.star)
    except CrossmatchUnavailable as exc:
        print(f"exoplan crossmatch: {exc}", file=sys.stderr)
        return 1
    print(f"cross-match {result['status']}: {len(result['planets'])} archive planet(s) stored in {args.run_dir}/crossmatch.json")
    return 0


def cmd_leaderboard(args) -> int:
    """Score one submission on the frozen benchmark's held-out half, or rebuild the whole table."""
    from exoplan import leaderboard as L

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
    parser = argparse.ArgumentParser(prog="exoplan", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the pipeline on the targets in a config file")
    run.add_argument("config")
    run.add_argument("--out", required=True, help="output directory")
    run.add_argument("--weights", help="JSON file of reviewer weights from 'exoplan calibrate' (overrides the default)")
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

    dash = sub.add_parser("dashboard", help="build the interactive dashboard from a run and optional discovery catalogue")
    dash.add_argument("run_dir")
    dash.add_argument("--out", required=True)
    dash.add_argument("--title", default="exoplan dashboard")
    dash.add_argument("--catalog", help="discovery catalogue JSON to include")
    dash.set_defaults(func=cmd_dashboard)

    docket = sub.add_parser("docket", help="build the candidate case-file view for a run")
    docket.add_argument("run_dir")
    docket.add_argument("--out", required=True)
    docket.add_argument("--title", default="exoplan docket")
    docket.add_argument("--star", help="star name for the archive cross-match (hostname or pl_name); TIC targets also match on tic_id")
    docket.add_argument("--refresh-crossmatch", action="store_true", help="run 'exoplan crossmatch' first: query the archive and store crossmatch.json")
    docket.add_argument("--allow-missing-crossmatch", action="store_true",
                     help="build even when no stored archive cross-match is usable; the page then prints the stored error")
    docket.set_defaults(func=cmd_docket)

    app = sub.add_parser("app", help="build the sidebar app shell (overview, candidates, discoveries, planets, panel, runs)")
    app.add_argument("run_dir")
    app.add_argument("--out", required=True)
    app.add_argument("--title", default="exoplan")
    app.add_argument("--catalog", help="discovery catalogue JSON for the Discoveries, Planets and Runs sections")
    app.add_argument("--weights", default="docs/results/reviewer_weights_full_panel.json",
                     help="calibrated reviewer weights JSON shown in the Panel section")
    app.add_argument("--star", help="star name for the Docket's archive cross-match, as in 'exoplan docket'")
    app.add_argument("--landing", help="also write the site's entry page (the Overview, linking into the app) to this path")
    app.add_argument("--landing-app-href", default="app/", help="the app's address relative to the landing page")
    app.add_argument("--allow-missing-crossmatch", action="store_true",
                     help="build even when no stored archive cross-match is usable; the page then prints the stored error")
    app.set_defaults(func=cmd_app)

    xmatch = sub.add_parser("crossmatch", help="query the NASA Exoplanet Archive for the run's targets and store crossmatch.json")
    xmatch.add_argument("run_dir")
    xmatch.add_argument("--star", help="star name (hostname or pl_name); TIC targets also match on tic_id")
    xmatch.set_defaults(func=cmd_crossmatch)

    plate = sub.add_parser("plate", help="build the print-ready plates page: one plate per star, with captions")
    plate.add_argument("run_dir")
    plate.add_argument("--out", required=True)
    plate.add_argument("--title", default="exoplan plates")
    plate.add_argument("--catalog", help="discovery catalogue JSON: its stars get plates and join the river of time")
    plate.add_argument("--star", help="star name for the archive cross-match, as in 'exoplan docket'")
    plate.add_argument("--allow-missing-crossmatch", action="store_true",
                     help="build even when no stored archive cross-match is usable; the page then prints the stored error")
    plate.set_defaults(func=cmd_plate)

    report = sub.add_parser("report", help="build a static HTML report site from a run directory")
    report.add_argument("run_dir")
    report.add_argument("--out", required=True, help="site directory to write")
    report.add_argument("--title", default="exoplan run")
    report.add_argument("--validation", help="validation markdown to embed")
    report.add_argument("--benchmark", help="benchmark markdown to embed")
    report.set_defaults(func=cmd_report)

    lb = sub.add_parser("leaderboard", help="score a submission on the frozen real-TOI benchmark's held-out half, "
                                            "or rebuild docs/leaderboard from every stored submission")
    lb.add_argument("submission", nargs="?", help="a submission JSON (docs/leaderboard/README.md); omit to rebuild the table")
    lb.add_argument("--submissions", default=str(Path(__file__).resolve().parents[2] / "docs/leaderboard/submissions"),
                    help="directory of submissions to score when rebuilding")
    lb.set_defaults(func=cmd_leaderboard)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    from exoplan.docket import CrossmatchUnavailable

    try:
        return args.func(args)
    except CrossmatchUnavailable as exc:
        print(f"exoplan {args.command}: {exc}. Run 'exoplan crossmatch {getattr(args, 'run_dir', '<run>')}', "
              "or pass --allow-missing-crossmatch to build a page that states the error.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

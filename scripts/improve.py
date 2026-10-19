"""Automated improvement loop: sweep panel settings, keep a change only if it holds on fresh data.

Protocol, so the loop cannot quietly overfit:

1. Search: score every candidate setting on benchmark seed ``--search-seed``.
   Score = mean completeness over the injection grid, but a setting whose
   false-positive rate per empty subject exceeds ``--max-fp`` scores zero.
2. Hold out: the best setting is rerun on ``--holdout-seed``, which was never used
   for the search. It is promoted only if its held-out score beats the current
   default's held-out score.
3. Record every trial, including losers, in ``docs/threshold_sweep.md`` and ``docs/threshold_sweep.json`` (not the real-TOI
   leaderboard in ``docs/leaderboard/``, which scores methods on the frozen benchmark).

Run with: python scripts/improve.py --out docs
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from exoplan.benchmark import injection_recovery
from exoplan.config import RunConfig, load_config
from exoplan.reviewers import SimulatedVolunteer

DEFAULT = {"snr_threshold": 5.0, "miss_probability": 0.10}
GRID = [
    {"snr_threshold": 4.0, "miss_probability": 0.05},
    {"snr_threshold": 4.5, "miss_probability": 0.05},
    {"snr_threshold": 5.0, "miss_probability": 0.10},
    {"snr_threshold": 5.5, "miss_probability": 0.10},
    {"snr_threshold": 6.0, "miss_probability": 0.10},
]


def panel_for(setting: dict, seed: int) -> list[SimulatedVolunteer]:
    """Three volunteers that share one setting but differ in seed, like three independent people."""
    return [
        SimulatedVolunteer(f"vol-{i}", snr_threshold=setting["snr_threshold"], miss_probability=setting["miss_probability"], seed=seed * 10 + i)
        for i in range(3)
    ]


def score(setting: dict, config: RunConfig, seed: int, *, n_per_cell: int, n_empty: int, max_fp: float) -> dict:
    with tempfile.TemporaryDirectory() as scratch:
        result = injection_recovery(
            panel_for(setting, seed),
            None,
            config,
            depths_ppm=(1000.0, 3000.0),
            durations_hours=(2.0, 4.0),
            n_per_cell=n_per_cell,
            n_empty=n_empty,
            seed=seed,
            image_dir=scratch,
        )
    completeness = sum(row.completeness for row in result.rows) / len(result.rows)
    fp = result.false_positives_per_subject
    return {
        "setting": setting,
        "seed": seed,
        "completeness": round(completeness, 4),
        "false_positives_per_subject": round(fp, 4),
        "score": round(completeness if fp <= max_fp else 0.0, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/benchmark_simulated_panel.toml")
    parser.add_argument("--out", type=Path, default=Path("docs"))
    parser.add_argument("--search-seed", type=int, default=101)
    parser.add_argument("--holdout-seed", type=int, default=202)
    parser.add_argument("--n-per-cell", type=int, default=12)
    parser.add_argument("--n-empty", type=int, default=30)
    parser.add_argument("--max-fp", type=float, default=0.025)
    args = parser.parse_args()

    config = load_config(args.config)
    trials = []
    for setting in GRID:
        trial = score(setting, config, args.search_seed, n_per_cell=args.n_per_cell, n_empty=args.n_empty, max_fp=args.max_fp)
        trial["stage"] = "search"
        trials.append(trial)
        print(trial)

    best = max(trials, key=lambda t: t["score"])
    holdout = {}
    for setting in {json.dumps(best["setting"], sort_keys=True): best["setting"], json.dumps(DEFAULT, sort_keys=True): DEFAULT}.values():
        result = score(setting, config, args.holdout_seed, n_per_cell=args.n_per_cell, n_empty=args.n_empty, max_fp=args.max_fp)
        result["stage"] = "holdout"
        holdout[json.dumps(setting, sort_keys=True)] = result
        trials.append(result)
        print(result)

    best_holdout = holdout[json.dumps(best["setting"], sort_keys=True)]
    default_holdout = holdout[json.dumps(DEFAULT, sort_keys=True)]
    promote = best_holdout["score"] > default_holdout["score"] and best["setting"] != DEFAULT
    decision = {
        "promote": promote,
        "chosen": best["setting"] if promote else DEFAULT,
        "best_search_setting": best["setting"],
        "best_holdout_score": best_holdout["score"],
        "default_holdout_score": default_holdout["score"],
        "rule": "promote only if the best search setting beats the default on the held-out seed",
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "threshold_sweep.json").write_text(json.dumps({"decision": decision, "trials": trials}, indent=2))
    lines = [
        "# Threshold sweep: Probe settings on synthetic injections",
        "",
        "Not the real-TOI leaderboard: that one scores whole methods on the frozen benchmark, in "
        "[docs/leaderboard/leaderboard.md](leaderboard/leaderboard.md). This sweep tunes Probe thresholds on synthetic light curves.",
        "",
        "Score is mean completeness on the injection grid. A setting with false positives above the budget scores zero. "
        "Search and held-out seeds are different, and only a setting that wins on the held-out seed can be promoted.",
        "",
        "| stage | snr threshold | miss prob | seed | completeness | FP / empty subject | score |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for t in trials:
        lines.append(
            f"| {t['stage']} | {t['setting']['snr_threshold']} | {t['setting']['miss_probability']} | {t['seed']} | "
            f"{t['completeness']:.3f} | {t['false_positives_per_subject']:.3f} | {t['score']:.3f} |"
        )
    lines += ["", f"Decision: **{'promote' if promote else 'keep default'}** → `{decision['chosen']}`", ""]
    (args.out / "threshold_sweep.md").write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Re-run the stored pi Men run (configs/tess_pi_men_s1.toml) on the current code, with no new Sentinel call.

    python scripts/rerun_pi_men.py --out runs/tess-pi-men-s1-new [--prompt-dir DIR]

The pipeline runs from the start (preparation, review, consensus, vetting, fit, FAP). The Probes run afresh. The
Sentinels are answered only from their stored answers in cache/claude-code, and only where what they would be shown
is byte-identical to what they were shown: the same subject image and the same prompt text. Their cache key holds
the image's bytes and the prompt, and the prompt names the image's absolute path, so the path the first run used
(``--prompt-dir``) is put in the prompt in place of this run's scratch path. A Sentinel whose inputs changed is not
asked again: it has no stored answer for them, the call is refused, and the run records it as skipped for that
subject (warned, and absent from classifications.csv). Nothing is ever fabricated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

CONFIG = ROOT / "configs/tess_pi_men_s1.toml"
# Where the first run's subject images were when the Sentinels saw them (their prompts name this path).
FIRST_PROMPT_DIR = "/workspace/EXOPLAN/runs/tess-pi-men-s1/subjects"


def cache_only_reviewers(specs: list[dict], cache_dir: Path, prompt_dir: str) -> list:
    from setuhq.reviewers.claude_code import ClaudeCodeBackend, ClaudeCodeReviewer
    from setuhq.reviewers.task import NotRetried

    class StoredAnswersOnly(ClaudeCodeBackend):
        """The Claude Code backend's prompt, with the first run's image path; any real call is refused."""

        def __init__(self, model):
            super().__init__(model, runner=self.refuse)

        def request(self, system, user, image):
            return super().request(system, user, Path(prompt_dir) / Path(image).name)

        @staticmethod
        def refuse(cmd, cwd):
            raise NotRetried("no stored answer for these exact inputs; the Sentinel was not asked again")

    out = []
    for spec in specs:
        r = ClaudeCodeReviewer(reviewer_id=spec["id"], persona=spec.get("persona", "volunteer"), model=spec.get("model"),
                               cache_dir=str(cache_dir), retries=1)
        r.backend = StoredAnswersOnly(spec.get("model"))
        out.append(r)
    return out


# The candidate fields that carry a result (detection, vetting, fit, FAP); anything else is provenance or a new field.
RESULT_FIELDS = ("candidate_id", "subject_id", "t_start", "t_end", "t_center", "duration_hours", "score", "n_reviewers", "planet_fraction",
                 "reviewers", "passed", "flags", "depth_ppm", "snr", "period_days", "n_transits", "fap", "fap_label", "fap_trials",
                 "fap_exceed", "fap_tail", "fit_t0", "fit_depth_ppm", "fit_t14_hours", "fit_b", "fit_k", "fit_rho_star")


def compare(previous: Path, new: Path) -> dict:
    """The replaced run against this one: when it was made, its code note, and which result fields differ."""
    pm = json.loads((previous / "manifest.json").read_text())
    old, now = (json.loads((d / "candidates.json").read_text()) for d in (previous, new))
    diffs = []
    for a, b in zip(old, now):
        for k in RESULT_FIELDS:
            x, y = a.get(k), b.get(k)
            same = x == y or (isinstance(x, float) and isinstance(y, float) and abs(x - y) <= 1e-9 * max(1.0, abs(x)))
            if not same:
                diffs.append({"candidate": a.get("candidate_id"), "field": k, "before": x, "after": y})
    return {"created_at": pm.get("created_at"), "code_note": pm.get("code_note"), "candidates": [len(old), len(now)],
            "fields_compared": list(RESULT_FIELDS), "differences": diffs,
            "same_results": len(old) == len(now) and not diffs}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=str(ROOT / "cache/claude-code"), help="the Claude Code CLI answers cache")
    ap.add_argument("--prompt-dir", default=FIRST_PROMPT_DIR, help="the subject image directory the first run's prompts named")
    ap.add_argument("--previous", help="the run this one replaces: its candidates are compared field by field and recorded")
    args = ap.parse_args(argv)

    import benchmark_real_tois as BR
    from setuhq.cli import DEFAULT_WEIGHTS, load_calibration_record, resolve_weights
    from setuhq.config import build_reviewers, load_config
    from setuhq.pipeline import run_pipeline

    config = load_config(CONFIG)
    probes = build_reviewers([s for s in config.reviewers if s["type"] == "simulated"])
    sentinels = cache_only_reviewers([s for s in config.reviewers if s["type"] == "claude_code"], Path(args.cache), args.prompt_dir)
    weights, source = resolve_weights(config, None, str(ROOT / DEFAULT_WEIGHTS))
    record = load_calibration_record(str(ROOT / DEFAULT_WEIGHTS))
    # The run's own light curve: TESS SPOC sector 1 of TIC 261136679 from the download cache, read with the same
    # steps as setuhq.loaders.load_tess (benchmark_real_tois.load_cached).
    target = config.targets[0]
    lcs = [BR.load_cached(int(target.id.split()[-1]), s) for s in target.sectors]
    summary = run_pipeline(config, lcs, probes + sentinels, args.out, weights=weights,
                           weights_source=source.replace(str(ROOT) + "/", ""), calibration=record)
    out = Path(args.out)
    manifest = json.loads((out / "manifest.json").read_text())
    from setuhq.store import read_classifications_csv

    rows = read_classifications_csv(out / "classifications.csv")
    sentinel_ids = {r.reviewer_id for r in sentinels}
    answered = [c for c in rows if c.reviewer_id in sentinel_ids]
    expected = summary.n_subjects * len(sentinels)
    manifest["sentinel_answers"] = {
        "how": ("stored answers only (cache/claude-code), reused because each subject image and prompt are byte-identical "
                "to the first run's; no Sentinel was asked again"),
        "prompt_image_dir": args.prompt_dir,
        "answered_from_store": len(answered), "expected": expected,
        "not_answered": expected - len(answered),
    }
    from setuhq.pipeline import _git_describe

    manifest["code"] = _git_describe()
    if args.previous:
        manifest["replaces"] = compare(Path(args.previous), out)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"{summary.n_subjects} subjects, {summary.n_classifications} classifications "
          f"({len(answered)} of {expected} Sentinel reviews from stored answers), "
          f"{summary.n_consensus} consensus dips, {summary.n_passed} pass vetting -> {out}")
    return 0 if len(answered) == expected else 2


if __name__ == "__main__":
    raise SystemExit(main())

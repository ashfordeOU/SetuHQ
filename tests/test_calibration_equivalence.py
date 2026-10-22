# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The frozen Probe weights and the rates the same calibration gives on the current code make the same decisions.

The calibration record's Probe rates (TPR 0.6, 0.6, 0.4) were measured on the code of 2026-10-16 (commit 03f23bd);
since the injections became limb-darkened (fbc1ed9) the same seed gives 0.9, 0.8 and 0.6. The weights stay frozen
(they are a parameter of the benchmark protocol). With three Probes, min_score = 0.5 and min_planet_fraction = 0.5,
both weight sets accept exactly the dips at least two of the three Probes mark, from subjects at least two of them
call a potential planet, so every consensus decision is the same; only the stored score value differs."""

import itertools
import json
from pathlib import Path

from setuhq.aggregate import aggregate
from setuhq.reviewers.base import POTENTIAL_PLANET, Classification, Mark

ROOT = Path(__file__).resolve().parents[1]
PROBES = ("volunteer-sensitive", "volunteer-typical", "volunteer-cautious")
NOW = {"volunteer-sensitive": 0.9, "volunteer-typical": 0.8, "volunteer-cautious": 0.6}  # TPR - FPR on current code


def _decisions(weights):
    out = {}
    for marks, labels in itertools.product(itertools.product((0, 1), repeat=3), repeat=2):
        cls = [Classification(r, "s", POTENTIAL_PLANET if lab else "noise", (Mark(10.0, 10.1),) if m else ())
               for r, m, lab in zip(PROBES, marks, labels)]
        events = aggregate(cls, weights, min_score=0.5, min_planet_fraction=0.5)
        out[(marks, labels)] = [(e.reviewers, e.t_start, e.t_end) for e in events]
    return out


def test_frozen_and_current_code_weights_make_the_same_decisions():
    frozen = {k: v for k, v in json.loads((ROOT / "docs/results/reviewer_weights_full_panel.json").read_text()).items() if k in PROBES}
    assert frozen == {"volunteer-sensitive": 0.6, "volunteer-typical": 0.6, "volunteer-cautious": 0.4}
    a, b = _decisions(frozen), _decisions(NOW)
    assert a == b
    # the rule is two of three: a dip two Probes mark passes, one Probe alone does not
    assert a[((1, 1, 0), (1, 1, 1))] and not a[((1, 0, 0), (1, 1, 1))] and not a[((1, 1, 1), (1, 0, 0))]
    rec = json.loads((ROOT / "docs/results/reviewer_weights_full_panel.calibration.json").read_text())
    assert "03f23bd" in rec["source"] and "0.9, 0.8 and 0.6" in rec["current_code"]

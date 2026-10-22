# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The frozen Probe weights and the rates the same calibration gives on the current code make the same decisions.

The calibration record's Probe rates (TPR 0.6, 0.6, 0.4) were measured on the code of 2026-10-16 (commit 03f23bd);
since the injections became limb-darkened (fbc1ed9) the same seed gives 0.9, 0.8 and 0.6. The weights stay frozen
(they are a parameter of the benchmark protocol). With three Probes, min_score = 0.5 and min_planet_fraction = 0.5,
both weight sets accept exactly the dips at least two of the three Probes mark, from subjects at least two of them
call a potential planet, so every consensus decision is the same; only the stored score value differs.

The equivalence holds for a full three-Probe panel, which is what every stored benchmark and feed run has. Two edge
cases do not hold and do not occur in the stored runs: with only volunteer-sensitive and volunteer-typical present
(the third skipped), a single mark from either scores 0.6/1.2 = 0.5 under the frozen weights and passes the >= 0.5
cut, while under the current-code rates volunteer-typical's alone scores 0.8/1.7 = 0.47 and fails (the same holds for
the planet fraction); and aggregate._merge_duplicates keeps the higher-scoring of two overlapping events, so its choice
can differ when they score in a different order under the two weight sets."""

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
    # the two-Probe edge case the docstring names: not equivalent, and absent from every stored run
    two = {k: v for k, v in frozen.items() if k != "volunteer-cautious"}
    one = [Classification("volunteer-typical", "s", POTENTIAL_PLANET, (Mark(10.0, 10.1),)),
           Classification("volunteer-sensitive", "s", POTENTIAL_PLANET, ())]
    assert aggregate(one, two) and not aggregate(one, {k: NOW[k] for k in two})
    rec = json.loads((ROOT / "docs/results/reviewer_weights_full_panel.calibration.json").read_text())
    assert "03f23bd" in rec["source"] and "0.9, 0.8 and 0.6" in rec["current_code"]

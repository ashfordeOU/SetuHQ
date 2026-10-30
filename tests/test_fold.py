# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V05, the fold (setuhq.viz.fold): pi Men's stored light curve, binned from the stored subjects and folded on the
joint fit's period. Real data, cited; nothing synthetic."""
import json
import math
import re
from pathlib import Path

import pytest

from setuhq import design, viz
from setuhq.viz import fold as F
from setuhq.i18n import unkey

ROOT = Path(__file__).resolve().parents[1]
VAL = json.loads((ROOT / F.VALIDATION).read_text())
FD = F.fold_data()


def _subjects():
    return [json.loads(p.read_text()) for p in sorted((ROOT / VAL["run"] / "subjects").glob("*.json"))]


def test_the_bins_come_from_the_stored_subjects():
    subs = _subjects()
    assert FD["n_points"] == sum(len(s["time"]) for s in subs) == 3485
    assert FD["subjects"] == sorted(s["subject_id"] for s in subs)
    assert FD["span"] == [round(min(s["time"][0] for s in subs), 4), round(max(s["time"][-1] for s in subs), 4)]
    # Recompute three bins by hand: each subject normalised to its median, in ppm, then averaged per 30 minutes.
    pts = []
    for s in subs:
        f = sorted(s["flux"])
        n = len(f)
        med = f[n // 2] if n % 2 else 0.5 * (f[n // 2 - 1] + f[n // 2])
        pts += [(t, (x / med - 1) * 1e6) for t, x in zip(s["time"], s["flux"])]
    w = 30 / 1440
    by = {}
    for t, v in pts:
        by.setdefault(int((t - FD["t_start"]) // w), []).append(v)
    bins = {round(t, 6): v for t, v in F.bins(FD)}
    assert len(bins) == FD["n_bins"] == len(by)
    for i in sorted(by)[::400]:
        centre = round(FD["t_start"] + (i + 0.5) * w, 6)
        assert bins[centre] == round(sum(by[i]) / len(by[i]))


def test_the_period_and_epoch_are_the_joint_fits():
    jf = VAL["joint_fit"]
    assert FD["p"] == pytest.approx(jf["period_days"], abs=1e-6) and f"{FD['p']:.4f}" == "6.2680"
    assert FD["t0"] == pytest.approx(jf["t0"], abs=1e-6)
    assert FD["depth_ppm"] == pytest.approx(jf["depth_ppm"], abs=0.1) and FD["t14_h"] == pytest.approx(jf["t14_hours"], abs=1e-3)


def test_the_folded_minimum_is_the_transit():
    prof = F.folded_profile(FD)
    h, low, n = min(prof, key=lambda x: x[1])
    assert -340 <= low <= -240 and abs(h) <= FD["t14_h"] / 2 and n >= 4
    # Below the local level by about the fitted depth; out of transit the fold is flat.
    assert 240 <= FD["base_ppm"] - low <= 340
    assert all(abs(v) < 120 for ph, v, _ in prof if abs(ph) > 2.5)


def test_the_figure_states_its_numbers_label_and_source():
    with pytest.raises(ValueError):
        F.html({})
    h = unkey(F.html({"source": "SetuHQ's stored run of pi Men"}, where="methods"))
    assert '<span class="stage-tag">Real data, cited</span>' in h and 'class="stage foldfig"' in h
    assert "3,485 points over BTJD 1325.3–1351.3" in h and "Folded on 6.2680 d, a 292 ppm dip of 3.07 h appears" in h
    assert "Source: SetuHQ&#x27;s stored run runs/tess-pi-men-s1" in h and "pi_men_validation.json" in h
    assert h.count('<svg viewBox') == 2 and len(re.findall(r'role="img" aria-label="[^"]*\d[^"]*"', h)) == 3
    assert '<button class="btn foldbtn" type="button" aria-pressed="false" hidden>' in h
    small = F.html({"source": "x"}, where="home", compact=True)
    # The home page's figure fits its budget: the label and the numbers with the run; the rest comes with its bins.
    assert 'class="stage foldfig compact"' in small and "<svg" not in small and len(unkey(small)) < 230 and len(h) < 16_000
    assert "3,485 points folded on 6.2680 d: a 292 ppm, 3.07 h dip. Source: runs/tess-pi-men-s1." in small and "Real data, cited" in small
    assert "split = true" in F.JS and "foldsrc" in F.JS
    for word in ("habitable", "confirmed", "discovered", "synthetic", "illustrative"):
        assert word not in h.lower()


def test_without_the_run_there_is_no_band():
    assert F.fold_data("docs/results/no_such_validation.json") is None


def test_its_data_section_is_small_and_drawn_by_the_page():
    d = F.data({})
    assert set(d) == {"fold"} and d["fold"]["segs"]
    assert len(json.dumps(d, separators=(",", ":"))) < 8_000
    assert "fold" in viz.collect({})["stories"]
    assert "viz_files" in F.JS and "requestAnimationFrame" in F.JS and "visibilitychange" in F.JS
    assert "prefers-reduced-motion" in F.JS and "IntersectionObserver" in F.JS
    assert design.motion_problems(F.CSS, "fold") == []
    assert math.isfinite(FD["base_ppm"])

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V06, the panel ring (setuhq.viz.panelring): stored marks, calibrated weights and the stored panel score, from the
committed runs; a Probes-only run draws no Sentinel; the attribution goes wherever a Sentinel is drawn; the status
words are names.DIP_STATE's; and the page's script draws exactly what Python draws."""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import docket as docket_mod
from setuhq.names import ATTRIBUTION, PROBES_ONLY, dip_state
from setuhq.viz import panelring as P

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "docs/results/reviewer_weights_full_panel.json"


@pytest.fixture(scope="module")
def data():
    """The app's data from the stored pi Men run (Probes and Sentinels) and WASP-126 (Probes only)."""
    from setuhq.app import app_data

    keep = docket_mod.query_archive
    docket_mod.query_archive = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test"))
    try:
        return app_data(ROOT / "runs/tess-pi-men-s1", title="t", extra_runs=[ROOT / "runs/tess-wasp-126-s1"],
                        weights_path=WEIGHTS, showcase_path=ROOT / "docs/results/showcase.json")
    finally:
        docket_mod.query_archive = keep


def _dips(data):
    return data["story"]["dips"] + data["showcase_dips"]


def _counted(run: str, cid: str) -> set[str]:
    """Who the run's stored record counts for this dip: its candidate's reviewer list (classifications.csv, as the
    pipeline aggregated it into candidates.json)."""
    row = next(c for c in json.loads((ROOT / "runs" / run / "candidates.json").read_text()) if c["candidate_id"] == cid)
    who = row.get("reviewers") or []
    return set(who.split(";") if isinstance(who, str) else who)


def test_marks_weights_and_score_are_the_stored_ones(data):
    weights = {k: (v["weight"] if isinstance(v, dict) else v) for k, v in json.loads(WEIGHTS.read_text()).items()}
    assert len(_dips(data)) >= 15
    for d in _dips(data):
        m = P.for_dip(data, d["id"])
        stored = json.loads((ROOT / "runs" / d["run"] / "candidates.json").read_text())
        row = next(c for c in stored if c["candidate_id"] == d["id"])
        assert m["score"] == row["score"], d["id"]
        assert {r["id"] for r in m["reviewers"] if r["marked"]} <= _counted(d["run"], d["id"])
        assert {r["id"] for r in m["reviewers"] if r["marked"]} == {ln["id"] for ln in d["lanes"] if ln["counted"]}
        for r in m["reviewers"]:
            assert r["weight"] == weights.get(r["id"]), r["id"]
        page = P.html(m)
        # The table under the figure lists every reviewer with its stored mark and weight.
        rows = re.findall(r'<tr><th scope="row">.*?</tr>', page)
        assert len(rows) == len(m["reviewers"])
        for r, tr in zip(m["reviewers"], rows):
            assert f'<span class="mono">{r["id"]}</span>' in tr and f'<td>{"yes" if r["marked"] else "no"}</td>' in tr
            assert f'<td class="num">{P._w(r["weight"])}</td>' in tr


def test_the_marks_agree_with_the_runs_classifications(data):
    """Every Probe the ring calls marked has a stored mark on the dip's subject in classifications.csv."""
    for d in data["story"]["dips"]:
        with open(ROOT / "runs/tess-pi-men-s1/classifications.csv", newline="") as f:
            who = {r["user_name"] for r in csv.DictReader(f) if r["subject_ids"] == d["subject"] and r.get("annotations")}
        for r in P.for_dip(data, d["id"])["reviewers"]:
            if r["marked"]:
                assert r["id"] in who, (d["id"], r["id"])


def test_pi_men_shows_three_probes_and_two_sentinels_with_the_attribution(data):
    d = data["story"]["dips"][0]
    page = P.html(P.for_dip(data, d["id"]))
    assert page.count('class="prnode prb') == 3 and page.count('class="prnode sen') == 2
    assert ATTRIBUTION in page and PROBES_ONLY not in page
    assert '<span class="stage-tag">Real data, cited</span>' in page


def test_a_probes_only_run_draws_no_sentinel(data):
    d = data["showcase_dips"][0]
    assert data["run_ctx"][d["run"]]["probes_only"]
    page = P.html(P.for_dip(data, d["id"]))
    assert page.count('class="prnode prb') == 3 and 'prnode sen' not in page and "prline sen" not in page
    assert PROBES_ONLY in page and ATTRIBUTION not in page
    # Even a record that names Sentinels draws none of them when the run is Probes only: never greyed-out nodes.
    fake = {"source": "test", "probes_only": True, "score": 0.5, "outcome": "passed",
            "reviewers": [{"id": "s", "name": "Sentinel · S", "role": "sentinel", "marked": False, "weight": 0.5},
                          {"id": "p", "name": "Probe · P", "role": "probe", "marked": True, "weight": 0.4}]}
    page = P.html(fake)
    assert "prnode sen" not in page and ">Sentinel<" not in page


def test_the_status_words_are_dip_states(data):
    seen = set()
    for d in _dips(data):
        page = P.html(P.for_dip(data, d["id"]))
        word = re.search(r'data-verdict="([^"]*)"', page).group(1)
        assert word == dip_state(d["outcome"])[2]
        seen.add(d["outcome"])
        if d["outcome"] == "rejected":
            assert "candidate, unconfirmed" not in page.lower()
    assert {"passed", "rejected"} <= seen


def test_real_data_shows_its_source_and_panel_mode_has_no_score(data):
    with pytest.raises(ValueError):
        P.html({"reviewers": []})
    panel = P.for_panel(data)
    page = P.html(panel)
    assert "data-verdict" not in page and "panel score" not in page and 'data-panelring="panel"' in page
    assert str(WEIGHTS.relative_to(ROOT)) in page or "reviewer_weights_full_panel.json" in page
    assert ATTRIBUTION in page and page.count('class="prnode ') == len(panel["reviewers"])


def test_the_page_script_draws_what_python_draws(data, tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    models = [P.for_dip(data, d["id"]) for d in _dips(data)] + [P.for_panel(data)]
    # The script's own model builder, from the dip records the page holds, gives the same data.
    opts = [{"weights": P.weights_of(data), "provenance": data["reviewer_provenance"], "weights_path": data["weights_path"],
             "run": d["run"], "label": data["dips"][d["id"]]["label"], "probes_only": data["run_ctx"][d["run"]]["probes_only"]}
            for d in _dips(data)]
    script = ("global.window = global; global.document = {readyState: 'complete', querySelectorAll: () => []};"
              "global.matchMedia = () => ({matches: true});\n" + P.JS +
              f"\nconst M = {json.dumps(models)}, DIPS = {json.dumps(_dips(data))}, O = {json.dumps(opts)};"
              "\nconsole.log(JSON.stringify({html: M.map(m => SetuPanelRing.html(m)), models: DIPS.map((d, i) => SetuPanelRing.dipModel(d, O[i]))}));")
    f = tmp_path / "pr.js"
    f.write_text(script)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert out["html"] == [P.html(m) for m in models]
    assert out["models"] == models[:-1]

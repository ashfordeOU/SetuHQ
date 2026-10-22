# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
import json
import math
import re
import shutil
import subprocess

import pytest

from setuhq import docket as docket_mod
from setuhq.app import APP_CSS, APP_JS, app_data, build_app
from setuhq.story import decoration, mollweide, number_words, sky_geometry
from conftest import site_bundle


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def run_dir(story_run):
    return story_run


@pytest.fixture
def targets(tmp_path):
    path = tmp_path / "targets.json"
    path.write_text(json.dumps({"source": "test source", "targets": {"TIC STORY-1": {"name": "Story", "ra_deg": 84.2912, "dec_deg": -80.4691}}}))
    return path


def _data(run_dir, targets=None):
    return app_data(run_dir, title="t", targets_path=targets)


def test_dips_plot_the_stored_points_in_their_window(run_dir):
    data = _data(run_dir)
    st, subjects = data["story"], data["hero"]["subjects"]
    assert st["dips"], "the test run has dips"
    dock = docket_mod.docket_data(run_dir, title="t")
    for d in st["dips"]:
        subj = dock["subjects"][d["subject"]]
        stored = {(round(t - d["t"], 5), round((f - 1.0) * 1e6, 1)) for t, f in zip(subj["time"], subj["flux"])
                  if d["t"] - d["half"] <= t <= d["t"] + d["half"]}
        assert {tuple(p) for p in d["pts"]} == stored and len(stored) > 10
        assert d["half"] >= 0.25 and d["ratio"] == pytest.approx(math.sqrt(d["depth_ppm"] * 1e-6))
        # The model is the Docket's stored limb-darkened fit curve, shifted to the dip's mid-time; no box.
        c = next(c for c in dock["candidates"] if c["candidate_id"] == d["id"])
        assert d["model"] == [[round(t - c["t_center"], 5), round(p, 1)] for t, p in c["model"]] and "box" not in d
        assert d["fit_depth_ppm"] == (c["fit"] or {}).get("depth_ppm")
        # Marks are the stored spans that touch the window.
        for lane in d["lanes"]:
            for a, b in lane["spans"]:
                assert b >= -d["half"] and a <= d["half"]
    assert sum(len(s["t"]) for s in subjects) == data["hero"]["n_points"]


def test_every_dip_is_hedged_and_statuses_come_from_the_stored_outcome(run_dir):
    st = _data(run_dir)["story"]
    for d in st["dips"]:
        assert d["status"] in ("known", "open", "rejected")
        if d["status"] == "rejected":
            assert d["outcome"] == "rejected"
        assert ("unconfirmed" in d["verdict"].lower()) or d["outcome"] == "rejected"
        assert "confirmed planet" not in d["verdict"].lower()
    # No archive match in the test run, so nothing is called a known planet.
    assert st["planet"] is None and all(d["status"] != "known" for d in st["dips"])
    assert st["sky_title"][0] == "Twenty-six days of TIC STORY-1."


def test_sky_position_is_the_stored_coordinates_and_field_stars_are_decorative(run_dir, targets, tmp_path):
    data = _data(run_dir, targets)
    star = data["story"]["star"]
    assert (star["ra_deg"], star["dec_deg"], star["source"]) == (84.2912, -80.4691, "test source")
    x, y = mollweide(84.2912, -80.4691)
    assert data["sky_geo"]["x"] == round(x, 2) and data["sky_geo"]["y"] == round(y, 2)
    assert y > 200  # near the south celestial pole, at the bottom of the map
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    sky = re.search(r'<section class="route" id="route-sky".*?(?=<section class="route" id="route-)', page, re.S).group(0)
    assert "Field stars decorative" in sky and "feed stars not plotted (positions not stored)" in sky
    # Without stored coordinates the target is not plotted, and the map says so.
    assert sky_geometry(None, None)["x"] is None
    assert "The target&#x27;s sky position is not stored" in sky or "sky position is not stored" in sky
    # The decoration is the same on every build.
    assert decoration() == decoration()


def test_overview_labels_the_artists_impression_and_the_theatre_says_what_is_not_fitted(run_dir, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    assert "Artist's impression of a planet lit by its star. It shows no real planet; SetuHQ works from light curves, not images." in page
    theatre = re.search(r"function txTheatre\(d\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    # The playback is the shared system view; every stored-values honesty line stays.
    assert "impact parameter illustrative (b = 0)" in theatre and "Dashed: the limb-darkened fit stored for this dip." in theatre
    assert "No transit fit is stored for this dip." in theatre and "box" not in theatre
    assert "Rp/R★ = √depth" in theatre and "orbit and period illustrative" in theatre
    assert "it does not confirm the dip" in theatre and "The star's surface texture is decorative." in theatre
    assert "mxSystemView($('#txsysfig'), p, {dip: {pts: d.pts, model}" in theatre
    for cls in ("sweep", "reveal", "playhead"):
        assert f".{cls}{{" in APP_CSS and "10s linear infinite" in re.search(rf"\.{cls}\{{[^}}]*\}}", APP_CSS).group(0)


def test_reduced_motion_stops_every_animation():
    rm = APP_CSS[APP_CSS.index("@media (prefers-reduced-motion: reduce){"):]
    rm = rm[:rm.index("\n}\n")]
    animated = set(re.findall(r"^\.([a-z0-9]+)\{animation:", APP_CSS, re.M))
    animated |= {"route"}
    for cls in animated:
        assert f".{cls}" in rm, cls
    assert "animation:none!important" in rm and ".sweep{transform:none!important}" in rm and ".playhead{opacity:0}" in rm


def test_number_words():
    assert number_words(26) == "twenty-six" and number_words(5) == "five" and number_words(140) == "140"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_old_routes_redirect_and_unknown_dips_are_named():
    from setuhq.routes import from_hash

    # Old in-app names (#/discoveries, #/panel) and unknown ones forward to a clean address (tests/test_site.py has them all).
    assert from_hash("#/discoveries?sort=depth&filter=new") == "/candidates/?sort=depth&filter=new"
    assert from_hash("#/panel") == "/evidence/" and from_hash("#/nowhere") == "/" and from_hash("#/transit?dip=x") == "/candidates/x/"
    opener = re.search(r"function openTransit\(dip\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "No dip ${dip} in run ${D.run.name}; showing the lead dip ${S.lead_dip}." in opener
    assert "setHash(transitHref(dip), false)" in opener


def test_explorer_and_sentinels_read_the_stored_feed_and_calibration(run_dir, tmp_path):
    feed = [{"tic": 1, "candidate_id": "x-1", "period_days": 2.5, "depth_ppm": 900.0, "snr": 9.1, "duration_hours": 2.0,
             "status": "new_candidate", "sector_span": [3, 4], "t_center": 1500.0, "time_unit": "BTJD"}]
    cat = tmp_path / "c.json"
    cat.write_text(json.dumps({"candidates": feed, "runs": []}))
    data = app_data(run_dir, title="t", catalog_path=cat)
    ex = data["story"]["explorer"]
    assert ex[0]["tic"] == 1 and ex[0]["sectors"] == "3–4" and ex[0]["depth_ppm"] == 900.0
    revs = data["story"]["reviewers"]
    assert {r["id"] for r in revs} <= set(data["run"]["reviewer_kinds"])
    for r in revs:
        if r["tpr"] is not None and r["n_injected"]:
            assert r["hits"] == round(r["tpr"] * r["n_injected"])
    js = re.search(r"function renderSentinels\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "planted transits found" in js and "empty light curves marked" in js


def test_home_page_is_the_overview_linking_into_the_site(run_dir, tmp_path):
    from setuhq.app import FONTS_CSS
    from setuhq.cli import main

    assert main(["site", str(run_dir), "--out", str(tmp_path / "site"), "--title", "setuhq", "--no-extras", "--allow-missing-crossmatch"]) == 0
    page = (tmp_path / "site" / "index.html").read_text()
    assert "The sky, reviewed." in page and "What this page does not claim" in page
    assert 'href="/explore/"' in page and 'href="/candidates/" data-nav="candidates">Candidates</a>' in page
    assert f'href="{FONTS_CSS}"' in page and "fonts.googleapis" not in page
    assert "Artist&#x27;s impression" in page or "Artist's impression" in page
    assert 'href="/evidence/report/"' in page and "candidate, unconfirmed" in page
    # The run's arrangeable cards live on Candidates, not on the home page.
    assert "Your view" not in page and 'id="widgets"' not in page
    # Every script is the site's own.
    assert all(src.startswith("/assets/") for src in re.findall(r"<script[^>]+src=\"([^\"]+)\"", page))


def test_round_four_polish_in_the_framed_docket():
    FRAME_BRIDGE_JS, FRAME_PHONE_CSS = docket_mod.DOCKET_JS, docket_mod.DOCKET_CSS  # the phone block lives in the Docket now

    jump = re.search(r"function jumpToList\(\)\{.*?\n  \}\n", FRAME_BRIDGE_JS, re.S).group(0)
    # Focus lands on the header the view lands on.
    assert "target.setAttribute('tabindex', '-1')" in jump and "target.focus({preventScroll: true})" in jump
    acc = re.search(r"function accordion\(\)\{.*?\n  \}\n", FRAME_BRIDGE_JS, re.S).group(0)
    assert "h.setAttribute('role', 'button'); h.setAttribute('aria-expanded', String(cur))" in acc
    assert "'show ' + n + ' dip'" in acc and "e.key === 'Enter' || e.key === ' '" in acc
    assert "if (!phone.matches)" in acc  # only a phone's list is an accordion
    assert "#rows .sighead[role=button]{min-height:44px" in FRAME_PHONE_CSS
    css = docket_mod.DOCKET_CSS
    assert ".xm-prov summary{cursor:pointer;display:flex;align-items:center;min-height:28px" in css
    assert ".xm-prov summary:focus-visible{outline:2px solid var(--fit)" in css

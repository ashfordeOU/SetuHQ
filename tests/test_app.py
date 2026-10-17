import json
import re
import shutil
import subprocess

import numpy as np
import pytest

from exoplan import docket as docket_mod
from exoplan.app import (
    APP_JS,
    NO_DETECTION,
    SECTIONS,
    UNCONFIRMED,
    WIDGETS,
    app_data,
    build_app,
    radius_ratio,
    widget_layout,
)
from exoplan.cli import main
from exoplan.config import RunConfig
from exoplan.lightcurve import LightCurve
from exoplan.pipeline import run_pipeline
from exoplan.reviewers import SimulatedVolunteer

WIDGET_IDS = [w for w, _ in WIDGETS]


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    """No test reaches the network: the archive query fails as it would offline."""

    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    rng = np.random.default_rng(11)
    time = np.arange(0.0, 26.0, 10 / 1440)
    flux = 1 + rng.normal(0, 2e-4, time.size)
    for k in range(6):
        centre = 2.5 + 4.0 * k
        flux -= 2500e-6 * ((time > centre - 0.125) & (time < centre + 0.125))
    lc = LightCurve(
        target="TIC TEST-3", mission="TESS", time=time, flux=flux,
        flux_err=np.full(time.size, 2e-4), provenance={"sector": 1, "time_unit": "BTJD"},
    )
    reviewers = [
        SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1),
        SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.0, seed=2),
    ]
    config = RunConfig(name="app", subject_days=13.0, min_points=100, bin_minutes=10.0)
    out = tmp_path_factory.mktemp("run")
    run_pipeline(config, [lc], reviewers, out)
    return out


@pytest.fixture
def catalog(tmp_path):
    entry = {"tic": 1234, "sector_span": [1, 2], "t_center": 1500.25, "time_unit": "BTJD", "duration_hours": 2.0,
             "depth_ppm": 900.0, "snr": 9.5, "score": 1.0, "n_reviewers": 3, "period_days": 3.5, "n_transits": 4,
             "status": "new_candidate", "candidate_id": "tess-x-001", "found": "2026-10-17T00:00:00+00:00",
             "status_note": "candidate only, not confirmed"}
    known = dict(entry, tic=5678, candidate_id="tess-y-002", status="known_toi", depth_ppm=1600.0)
    data = {"candidates": [entry, known], "targets_reviewed": 2, "updated": "2026-10-17T00:00:00+00:00",
            "config": "discovery", "config_sha256": "abc",
            "runs": [{"time": "2026-10-17T00:00:00+00:00", "targets": [1234, 5678], "new": 1, "known": 1,
                      "errors": ["TIC 9: LookupError: no SPOC 120s light curves found for 'TIC 9'"]}]}
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data))
    return path


def _page_data(page: str) -> dict:
    raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
    return json.loads(raw.replace("<\\/", "</"))


def _route(page: str, sid: str) -> str:
    return re.search(rf'<section class="route" id="route-{sid}".*?(?=<section class="route" id="route-|</main>)', page, re.S).group(0)


def test_app_builds_from_run_dir_and_catalogue(run_dir, catalog, tmp_path):
    assert main(["app", str(run_dir), "--catalog", str(catalog), "--out", str(tmp_path / "app"), "--title", "exoplan"]) == 0
    page = (tmp_path / "app" / "index.html").read_text()
    data = _page_data(page)
    assert data["title"] == "exoplan"
    assert [c["candidate_id"] for c in data["catalog"]["candidates"]] == ["tess-x-001", "tess-y-002"]
    assert data["catalog"]["runs"][0]["errors"] == ["TIC 9: LookupError: no SPOC 120s light curves found for 'TIC 9'"]
    assert data["config"]["config_name"] == "app"
    assert {r["id"] for r in data["panel"]} == {"vol-a", "vol-b"}
    assert all(r["kind"] == "simulated" for r in data["panel"])
    # The Docket is embedded whole, rendered by docket.py.
    assert data["docket_html"].startswith("<!doctype html>")
    # One self-contained file: no external script.
    assert not re.search(r"<script[^>]+src=", page)


def test_app_builds_without_catalogue(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    data = _page_data(page)
    assert data["catalog"]["candidates"] == [] and data["catalog"]["runs"] == []


def test_all_six_routes_exist(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    assert [s for s, _ in SECTIONS] == ["overview", "candidates", "discoveries", "planets", "panel", "runs"]
    for sid, label in SECTIONS:
        assert f'id="route-{sid}"' in page
        assert f'href="#/{sid}"' in page
        assert f">{label}</h1>" in page
    assert '<nav class="nav" aria-label="Sections">' in page
    assert "aria-current" in APP_JS


def test_planet_cards_never_state_an_earth_or_jupiter_radius(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    data = _page_data(page)
    planets = _route(page, "planets")
    no_radius = re.compile(r"\d\s*(R⊕|R_⊕|R♃|R_?J\b|R_?E\b|R_?earth|R_?jup|Earth radi|Jupiter radi|M⊕)", re.I)
    assert not no_radius.search(planets)
    assert not no_radius.search(APP_JS)
    assert not no_radius.search(json.dumps(data["planets"], ensure_ascii=False))
    assert "No stellar radius is stored" in planets
    for card in data["planets"]:
        for e in card["entries"]:
            assert set(e) >= {"depth_ppm", "ratio"}
            assert not any("radius" in k or "rade" in k or "radj" in k for k in e)
            assert e["ratio"] == pytest.approx(radius_ratio(e["depth_ppm"]))
        for p in (card["archive"] or {}).get("planets", []):
            assert not any(k in p for k in ("pl_rade", "pl_radj", "pl_radius"))
    feed_star = next(c for c in data["planets"] if c["star"] == "TIC 1234")
    assert feed_star["entries"][0]["ratio"] == pytest.approx(0.03)  # sqrt(900 ppm)
    assert feed_star["archive"]["status"] == "not_stored"
    assert NO_DETECTION in planets


def test_radius_ratio_is_sqrt_depth():
    assert radius_ratio(10000.0) == pytest.approx(0.1)
    assert radius_ratio(0) is None and radius_ratio(None) is None and radius_ratio(-5) is None


def test_every_discovery_surface_says_unconfirmed(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    data = _page_data(page)
    assert data["unconfirmed"] == UNCONFIRMED == "candidate, unconfirmed"
    for sid in ("candidates", "discoveries", "planets"):
        assert UNCONFIRMED in _route(page, sid), sid
    # Rendered rows: the feed table status cell, the timeline dots, the top-candidates
    # widget, the discovery-count widget and every planet entry carry the wording.
    status_col = re.search(r"\['status', 'status'.*?\],\n", APP_JS, re.S).group(0)
    assert "D.unconfirmed" in status_col
    timeline = re.search(r"function timeline\(box\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "D.unconfirmed" in timeline
    widgets = re.search(r"function widgetBody\(id\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert widgets.count("D.unconfirmed") + widgets.count("${UNC}") >= 3
    planets = re.search(r"function renderPlanets\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "${UNC}" in planets and "D.no_detection" in planets
    assert "candidate, unconfirmed" in data["docket_html"]
    # The feed rule is shown as a rule, not a vetting result.
    disc = _route(page, "discoveries")
    assert "at most 5,000 ppm" in disc and "at least 2 transits" in disc
    assert "not a vetting result" in disc


def test_widget_layout_is_valid_when_storage_is_absent():
    expected = [{"id": w, "visible": True} for w in WIDGET_IDS]
    assert widget_layout(None) == expected
    assert widget_layout("not json") == expected
    assert widget_layout({"id": "kpis"}) == expected
    stored = [{"id": "top", "visible": False}, {"id": "nope"}, "x", {"id": "top"}, {"id": "kpis"}]
    out = widget_layout(stored)
    assert [x["id"] for x in out][:2] == ["top", "kpis"]
    assert sorted(x["id"] for x in out) == sorted(WIDGET_IDS)
    assert out[0]["visible"] is False and all(x["visible"] for x in out[1:])


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_page_layout_function_handles_missing_or_blocked_storage():
    funcs = re.search(r"function normaliseLayout.*?\n\}\nfunction readLayout.*?\n\}\n", APP_JS, re.S).group(0)
    script = funcs + f"""
const ids = {json.dumps(WIDGET_IDS)};
const blocked = {{ getItem(){{ throw new Error('blocked'); }} }};
const bad = {{ getItem(){{ return '{{not json'; }} }};
console.log(JSON.stringify([readLayout(undefined, 'k', ids), readLayout(null, 'k', ids), readLayout(blocked, 'k', ids), readLayout(bad, 'k', ids)]));
"""
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    expected = [{"id": w, "visible": True} for w in WIDGET_IDS]
    assert json.loads(out) == [expected] * 4


def test_app_data_keeps_docket_counts(run_dir, catalog):
    data = app_data(run_dir, title="t", catalog_path=catalog)
    counts = data["run"]["docket_counts"]
    assert counts["dips"] == len(json.loads((run_dir / "candidates.json").read_text()))
    assert counts["passed"] + counts["flagged"] + counts["rejected"] == counts["signals"]

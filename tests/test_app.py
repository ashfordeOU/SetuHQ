import json
import re
import shutil
import subprocess

import numpy as np
import pytest

from exoplan import docket as docket_mod
from exoplan.app import (
    APP_CSS,
    APP_JS,
    FRAME_BRIDGE_JS,
    FRAME_PHONE_CSS,
    DEFAULT_SIZE,
    NO_DETECTION,
    NO_STELLAR_RADIUS,
    SECTIONS,
    UNCONFIRMED,
    WIDGETS,
    ISO_WEIGHTS,
    app_data,
    build_app,
    calibration_plane,
    DEFAULT_FEED_VIEW,
    decode_feed_view,
    decode_layout,
    encode_feed_view,
    encode_layout,
    feed_view,
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
    expected = [{"id": w, "visible": True, "size": DEFAULT_SIZE[w]} for w in WIDGET_IDS]
    assert widget_layout(None) == expected
    assert widget_layout("not json") == expected
    assert widget_layout({"id": "kpis"}) == expected
    stored = [{"id": "top", "visible": False, "size": "XL"}, {"id": "nope"}, "x", {"id": "top"}, {"id": "kpis", "size": "S"}]
    out = widget_layout(stored)
    assert [x["id"] for x in out][:2] == ["top", "kpis"]
    assert sorted(x["id"] for x in out) == sorted(WIDGET_IDS)
    assert out[0]["visible"] is False and all(x["visible"] for x in out[1:])
    assert out[0]["size"] == DEFAULT_SIZE["top"] and out[1]["size"] == "S"


def test_layout_round_trips_through_the_url():
    layout = [{"id": "top", "visible": True, "size": "S"}, {"id": "runs", "visible": False, "size": "L"},
              {"id": "kpis", "visible": True, "size": "M"}, {"id": "discoveries", "visible": True, "size": "L"}]
    text = encode_layout(layout)
    assert text == "top.S,runs.L.hidden,kpis.M,discoveries.L"
    assert decode_layout(text) == layout
    assert decode_layout("") == widget_layout(None)
    assert decode_layout("junk,,top.Q.x") == widget_layout([{"id": "top"}])
    # The page reads and writes the same string in the hash query.
    assert "'#/overview?layout=' + encodeLayout(layout)" in APP_JS
    assert "p.params.get('layout')" in APP_JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_page_layout_function_handles_missing_or_blocked_storage():
    funcs = re.search(r"function normaliseLayout.*?\n\}\nfunction readLayout.*?\n\}\n", APP_JS, re.S).group(0)
    codec = re.search(r"function encodeLayout.*?\n\}\nfunction decodeLayout.*?\n\}\n", APP_JS, re.S).group(0)
    script = funcs + codec + f"""
const ids = {json.dumps(WIDGET_IDS)}, sizes = {json.dumps(DEFAULT_SIZE)};
const blocked = {{ getItem(){{ throw new Error('blocked'); }} }};
const bad = {{ getItem(){{ return '{{not json'; }} }};
const shared = decodeLayout('top.S,runs.L.hidden,kpis.M,discoveries.L', ids, sizes);
console.log(JSON.stringify([[readLayout(undefined, 'k', ids, sizes), readLayout(null, 'k', ids, sizes), readLayout(blocked, 'k', ids, sizes), readLayout(bad, 'k', ids, sizes)], encodeLayout(shared), shared]));
"""
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    expected = [{"id": w, "visible": True, "size": DEFAULT_SIZE[w]} for w in WIDGET_IDS]
    fallbacks, text, shared = json.loads(out)
    assert fallbacks == [expected] * 4
    assert text == "top.S,runs.L.hidden,kpis.M,discoveries.L"
    assert shared == decode_layout(text)


def test_dip_identifiers_link_to_the_dossier(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    data = _page_data(page)
    ids = [c["candidate_id"] for c in json.loads((run_dir / "candidates.json").read_text())]
    assert data["dossier_ids"] == ids
    # One link builder, in the ?dip= form, used by the Overview, the Planets, the Panel and the feed.
    assert "`#/candidates?dip=${encodeURIComponent(id)}" in APP_JS
    for fn in ("widgetBody", "renderPlanets", "renderPanel"):
        body = re.search(rf"function {fn}\(.*?\n\}}\n", APP_JS, re.S).group(0)
        assert "dipLink(" in body, fn
    assert "x => dipLink(x.candidate_id)" in APP_JS
    # The top-candidates widget is a list of links, not a table without anchors.
    top = re.search(r"function topBody.*?\n  \}\n", APP_JS, re.S).group(0)
    assert "<table" not in top and "dipLink(x.id)" in top
    # The shell forwards ?dip= to the Docket frame as the frame's location hash.
    assert "p.params.get('dip')" in APP_JS
    assert "docketBlob + (dip ? '#' + encodeURIComponent(dip) : '')" in APP_JS
    assert "fromHash = decodeURIComponent(location.hash.slice(1))" in data["docket_html"]


def test_skip_target_is_not_a_route(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    href = re.search(r'<a class="skip" href="#([^"]+)"', page).group(1)
    assert not href.startswith("/") and href not in [s for s, _ in SECTIONS]
    assert re.search(rf'<div id="{href}" tabindex="-1">', page)
    assert page.index('<main id="main">') < page.index(f'id="{href}"')
    # The router leaves non-route hashes alone.
    assert "if (!h.startsWith('#/')) return null;" in APP_JS
    assert "const p = parseHash(location.hash); if (!p) return;" in APP_JS


def test_drawer_is_a_dialog_with_a_close_button(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    side = re.search(r'<aside class="sidebar".*?</aside>', page, re.S).group(0)
    assert 'id="drawerclose"' in side and "Close menu" in side
    assert "side.setAttribute('role', 'dialog')" in APP_JS and "side.setAttribute('aria-modal', 'true')" in APP_JS
    # The lock is on html: with html's overflow-x:hidden, overflow on body alone does not stop the viewport.
    lock = re.search(r"function lockScroll\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    unlock = re.search(r"function unlockScroll\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "document.documentElement.style.overflow = 'hidden'" in lock and "lockedY = window.scrollY" in lock
    assert "document.documentElement.style.overflow = ''" in unlock and "window.scrollTo(0, y)" in unlock
    assert "lockScroll();" in re.search(r"function openDrawer\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "unlockScroll();" in re.search(r"function closeDrawer\(returnFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)


def test_shell_loads_the_docket_fonts(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    data = _page_data(page)
    link = re.search(r'<link rel="stylesheet" href="(https://fonts.googleapis.com/[^"]+)">', page).group(1)
    assert html_unescape(link) in data["docket_html"]
    assert "Inter+Tight" in link and "JetBrains+Mono" in link


def html_unescape(text: str) -> str:
    import html

    return html.unescape(text)


def test_planets_state_the_stellar_radius_limitation_once(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    planets = _route(page, "planets")
    assert planets.count(NO_STELLAR_RADIUS) == 1
    body = re.search(r"function renderPlanets\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "no_stellar_radius" not in body and "stellar radius" not in body
    # The size bar is a labelled ratio scale with a stated maximum, and the working is shown.
    assert "on a scale from 0 to" in body and "max</span>" in body and "√depth = √(" in body
    assert "ratio scale from 0 to 0.10" in planets


def test_panel_lists_marks_per_dip(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    data = _page_data(page)
    rows = json.loads((run_dir / "candidates.json").read_text())
    by_id = {r["candidate_id"]: set(filter(None, r["reviewers"].split(";"))) for r in rows}
    assert [a["id"] for a in data["agreement"]] == list(by_id)
    for a in data["agreement"]:
        assert set(a["reviewers"]) == by_id[a["id"]]
        assert a["n"] == len(by_id[a["id"]]) == a["n_sim"] + a["n_claude"]
        assert a["of"] == len(data["panel"]) and a["of_sim"] == 2
    for r in data["panel"]:
        assert r["marked_dips"] == [cid for cid, who in by_id.items() if r["id"] in who]
    body = re.search(r"function renderPanel\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "of ${a.of_sim} simulated" in body and "of ${a.of_claude} Claude" in body
    assert "dipHref(a.id, 'ledger')" in body and "Verdict ledger" in body
    assert "not a person" in body
    assert "Marks per dip" in _route(page, "panel")


ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def test_no_raw_iso_timestamp_in_overview_or_runs_headings(run_dir, catalog, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    for sid in ("overview", "runs"):
        assert not ISO.search(_route(page, sid)), sid
    # Rendered headings and footers pass stored times through when(), which keeps the ISO value in a title.
    for raw in ("esc(x.time)", "esc(r.created_at)", "esc(D.run.created_at)", "esc(D.catalog.updated", "esc(x.found)", "esc(ar.fetched_at)"):
        assert raw not in APP_JS, raw
    assert "<b>${when(x.time)}</b>" in APP_JS and "${when(r.created_at)}" in APP_JS
    assert 'title="${esc(iso)}"' in APP_JS
    # The feed has no repeated "found" column; the find time is stated once in the header.
    assert "['found'," not in APP_JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_when_formats_a_readable_date_with_the_iso_in_the_title():
    esc = re.search(r"const esc = .*?\n", APP_JS).group(0)
    fn = re.search(r"function when\(iso\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    script = esc + fn + "console.log(JSON.stringify([when('2026-10-17T17:24:19+00:00'), when(''), when('nonsense')]));"
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True,
                                    env={"TZ": "UTC", "PATH": "/usr/bin:/bin:/usr/local/bin"}).stdout)
    text = re.sub(r"<[^>]+>", "", out[0])
    assert "2026" in text and "Oct" in text and not ISO.search(text)
    assert 'title="2026-10-17T17:24:19+00:00"' in out[0]
    assert out[1] == "not stored" and out[2] == "nonsense"


def test_feed_is_named_for_what_it_holds(run_dir, catalog, tmp_path):
    data = app_data(run_dir, title="t", catalog_path=catalog)
    assert next(s for s in data["sections"] if s["id"] == "discoveries")["label"] == "Discoveries"
    mostly_known = json.loads(catalog.read_text())
    mostly_known["candidates"][0]["status"] = "known_toi"
    path = tmp_path / "known.json"
    path.write_text(json.dumps(mostly_known))
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=path).read_text()
    assert ">Feed</h1>" in page and 'data-route="discoveries"><svg' in page
    assert "2 of them match a known TOI period" in _route(page, "discoveries")


def test_top_candidates_name_the_archive_match(run_dir, catalog, tmp_path):
    body = re.search(r"function topBody.*?\n  \}\n", APP_JS, re.S).group(0)
    assert "consistent with <b>${esc(xm.consistent_with)}</b>" in body
    assert "not ${n === 1 ? 'a discovery' : n + ' discoveries'}" in body
    assert "D.no_detection" in body
    data = app_data(run_dir, title="t", catalog_path=catalog)
    for x in data["run"]["top"]:
        assert set(x) >= {"signal_id", "consistent_with", "signal_dips"}
        assert x["consistent_with"] is None  # the test run has no stored cross-match


def test_app_data_keeps_docket_counts(run_dir, catalog):
    data = app_data(run_dir, title="t", catalog_path=catalog)
    counts = data["run"]["docket_counts"]
    assert counts["dips"] == len(json.loads((run_dir / "candidates.json").read_text()))
    assert counts["passed"] + counts["flagged"] + counts["rejected"] == counts["signals"]


def test_docket_frame_reports_its_dip_and_section_to_the_shell(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    docket_html = _page_data(page)["docket_html"]
    # The shell's copy of the Docket carries the bridge; the standalone Docket page does not.
    assert FRAME_BRIDGE_JS in docket_html and docket_html.index(FRAME_BRIDGE_JS) < docket_html.index("</head>")
    standalone = docket_mod.docket_page(docket_mod.docket_data(run_dir, title="t"))
    assert FRAME_BRIDGE_JS not in standalone and "postMessage" not in standalone
    assert FRAME_PHONE_CSS not in standalone
    injected = f"<style>{FRAME_PHONE_CSS}</style><script>{FRAME_BRIDGE_JS}</script>"
    assert docket_html.replace(injected, "") == docket_mod.docket_page(
        docket_mod.docket_data(run_dir, title="t · candidates"))
    # The bridge reports every selection (the Docket selects by history.replaceState) and section anchors.
    assert "if (window.parent === window) return;" in FRAME_BRIDGE_JS
    assert "history.replaceState = function(){" in FRAME_BRIDGE_JS and "send({kind: 'dip'})" in FRAME_BRIDGE_JS
    assert "addEventListener('hashchange'" in FRAME_BRIDGE_JS and "kind: 'section'" in FRAME_BRIDGE_JS
    assert "P.postMessage(m, '*')" in FRAME_BRIDGE_JS
    # The shell takes messages only from its own frame and writes them to its URL and full-page links.
    listener = re.search(r"window.addEventListener\('message', e => \{.*?\n\}\);\n", APP_JS, re.S).group(0)
    assert "e.source !== f.contentWindow" in listener and "m.source !== 'exoplan-docket'" in listener
    sync = re.search(r"function syncShellURL\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "history.replaceState(null, '', h)" in sync and "setFullHrefs(frame.dip)" in sync
    assert "'#fullpage, #topfull, #blockedlink'" in APP_JS
    # A cross-origin frame (file://) is named in the page rather than failing silently.
    assert "frame.crossOrigin = true" in APP_JS and "separate origin" in APP_JS


def test_blocked_frame_shows_a_message_and_a_link(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    cand = _route(page, "candidates")
    msg = re.search(r'<p class="note blocked" id="frameblocked" role="alert" hidden>(.*?)</p>', cand).group(1)
    assert msg == 'The dossier could not load in this view. <a id="blockedlink" href="../docket/">Open it on its own page.</a>'
    # A frame that never reports ready falls back to srcdoc, then to the message; the frame is hidden.
    failed = re.search(r"function frameLoadFailed\(gen\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "loadDocket(frame.dip, frame.section, 'srcdoc')" in failed and "showBlocked()" in failed
    blocked = re.search(r"function showBlocked\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.hidden = true" in blocked and "$('#frameblocked').hidden = false" in blocked
    # About three seconds for the blob frame, then a shorter wait for the srcdoc copy, which needs no fetch.
    assert "setTimeout(() => frameLoadFailed(gen), url ? 3000 : 1500)" in APP_JS
    assert "6000" not in APP_JS
    assert ".frame[hidden]{display:none}" in APP_CSS


def _phone_css() -> str:
    start = APP_CSS.index("@media (max-width:699.98px){")
    return APP_CSS[start:APP_CSS.index("\n}\n", start)]


def test_phone_touch_targets_are_at_least_44px():
    phone = _phone_css()
    rules = dict(re.findall(r"^\s*([^{}\n]+)\{([^}]*)\}", phone, re.M))

    def has(selector, prop):
        return any(selector in [x.strip() for x in sel.split(",")] and prop in body for sel, body in rules.items())

    for sel in ("main a", "summary", ".btn", ".chip", ".nav a", "th button"):
        assert has(sel, "min-height:44px"), sel
    assert has("main a", "min-width:44px") and has("th button", "min-width:44px")
    assert has("main a", "padding:12px 0") and has("summary", "padding:12px 0")
    assert "min-height:44px" in re.search(r"\.skip\{[^}]*\}", APP_CSS).group(0)
    # Targets grow by min-height and padding, not by a larger font.
    assert "font-size" not in rules["main a"] and "font-size" not in rules["summary"]
    # Candidates fills the screen under the top bar and the feed table has no vertical scroller of its own.
    assert 'body[data-route="candidates"] #route-candidates' in phone and "calc(100dvh - var(--top))" in phone
    assert ".tablewrap.scrollbox{max-height:none}" in phone
    assert "document.body.dataset.route = r;" in APP_JS


def test_shared_layout_link_does_not_write_the_viewers_default():
    go = re.search(r"function go\(p, moveFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "decodeLayout(p.params.get('layout')" in go and "saveLayout" not in go
    assert "layout = ownLayout.map(x => ({...x}))" in go
    # Storage is written only by saveLayout, and saveLayout runs only after a layout control is used.
    # (The only other write is the Feed's own default, in saveFeedView.)
    assert APP_JS.count("setItem(") == 2 and APP_JS.count("setItem(LAYOUT_KEY") == 1
    assert "s.setItem(LAYOUT_KEY" in re.search(r"function saveLayout\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "s.setItem(FEED_KEY" in re.search(r"function saveFeedView\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    callers = [m.start() for m in re.finditer(r"saveLayout\(\);", APP_JS)]
    action = re.search(r"function layoutAction\(.*?\n\}\n", APP_JS, re.S)
    reset = re.search(r"\$\('#resetlayout'\)\.addEventListener.*?\n", APP_JS)
    assert callers and all(action.start() < c < action.end() or reset.start() < c < reset.end() for c in callers)
    # The page says when a shared layout is showing, and offers a link to copy the current one.
    assert "navigator.clipboard.writeText(url)" in APP_JS and "'#/overview?layout=' + encodeLayout(layout)" in APP_JS


def test_overview_has_shared_note_and_copy_link(run_dir, tmp_path):
    overview = _route(build_app(run_dir, tmp_path / "app", title="t").read_text(), "overview")
    assert 'id="copylayout"' in overview and "Copy link to this layout" in overview
    assert 'id="sharednote" hidden>This is a shared layout, shown for this view only.' in overview


def test_archive_box_states_no_detection_once():
    body = re.search(r"function renderPlanets\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    arch = re.findall(r"arch = `(.*?)`;\n", body)
    assert len(arch) == 3
    for line in arch:
        assert line.count("${esc(D.no_detection)}") == 1
        assert "archive values only" not in line.lower()
    assert NO_DETECTION.count("This page claims no detection.") == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_feed_says_when_rows_have_no_dossier():
    fn = re.search(r"function noDossierLine\(rows\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    script = "const DIP_IDS = new Set(['a']);\n" + fn + """
console.log(JSON.stringify([noDossierLine([{candidate_id: 'x'}, {candidate_id: 'y'}]), noDossierLine([{candidate_id: 'a'}]), noDossierLine([{candidate_id: 'a'}, {candidate_id: 'y'}])]));"""
    none, all_linked, some = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert ">No dossier stored for these rows in this run.<" in none
    assert all_linked == ""
    assert "No dossier stored for 1 of these rows in this run" in some
    assert "${noDossierLine(rows)}${archiveNote(rows)}</caption>" in APP_JS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_bridge_reports_the_dip_even_when_replace_state_throws():
    # A srcdoc frame: replaceState throws a SecurityError. The dip is still reported, flagged.
    script = """
    const sent = [];
    const parent = {postMessage: m => sent.push(m)};
    global.window = {parent, addEventListener(){}, innerHeight: 800, scrollY: 0};
    global.document = {addEventListener(){}, getElementById(){ return null; }};
    global.location = {hash: ''};
    global.state = {selected: 'D-1'};
    let mode = 'throw';
    global.history = {replaceState(){ if (mode === 'throw') { const e = new Error('blocked'); e.name = 'SecurityError'; throw e; } return 'ok'; }};
    """ + FRAME_BRIDGE_JS + """
    let threw = false;
    try { history.replaceState(null, '', '#D-2'); } catch (e) { threw = true; }
    mode = 'ok';
    const r = history.replaceState(null, '', '#D-3');
    console.log(JSON.stringify({sent, threw, r}));
    """
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out["threw"] is False and out["r"] == "ok"
    assert [m["kind"] for m in out["sent"]] == ["dip", "dip"]
    assert out["sent"][0]["urlFailed"] is True and out["sent"][0]["dip"] == "D-1"
    assert out["sent"][1]["urlFailed"] is False
    # The shell names the failure in the frame status line.
    listener = re.search(r"window.addEventListener\('message', e => \{.*?\n\}\);\n", APP_JS, re.S).group(0)
    assert "if (m.urlFailed) frame.frameURLFailed = true;" in listener and "readyStatus()" in listener
    status = re.search(r"function readyStatus\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "Address bar not updated in this view." in status and "frame.frameURLFailed" in status
    assert "frame.shellURLFailed = true" in APP_JS


def test_frame_shows_a_loading_status_while_it_loads():
    load = re.search(r"function loadDocket\(dip, section, mode\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "frameStatus(LOADING_TEXT);" in load
    assert "const LOADING_TEXT = 'Loading the Docket…';" in APP_JS
    # Once ready, the loading line is replaced (cleared, or a note on the frame's origin or address).
    ready = re.search(r"function onFrameReady\(m\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "readyStatus();" in ready


def test_phone_rule_in_the_framed_docket_makes_44px_targets(run_dir, tmp_path):
    assert FRAME_PHONE_CSS.startswith("@media (max-width:700px){")
    rules = dict(re.findall(r"([^{}]+)\{([^{}]*)\}", FRAME_PHONE_CSS[FRAME_PHONE_CSS.index("{") + 1:]))
    covered = {sel.strip(): body for sels, body in rules.items() for sel in sels.split(",")}
    for cls in (".dipbtn", ".chip", ".sectoggle", ".listtoggle"):
        assert "min-height:44px" in covered[cls] and "padding:" in covered[cls], cls
        assert "font-size" not in covered[cls]
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    docket_html = _page_data(page)["docket_html"]
    head = docket_html[:docket_html.index("</head>")]
    # After the Docket's own styles, so it wins at equal specificity.
    assert head.rindex(FRAME_PHONE_CSS) > head.index(".dipbtn{")


def test_desktop_frame_height_is_fitted_from_the_measured_header():
    frame_rule = re.search(r"\.frame\{[^}]*\}", APP_CSS).group(0)
    # The CSS fallback first, then the measured offset with the same fallback value.
    assert "height:calc(100vh - 190px);height:calc(100vh - var(--frame-offset, 190px))" in frame_rule
    fit = re.search(r"function fitFrame\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.getBoundingClientRect().top + window.scrollY" in fit and "paddingBottom" in fit
    assert "setProperty('--frame-offset'" in fit and "(max-width:699.98px)" in fit
    resize = re.search(r"window.addEventListener\('resize'.*", APP_JS).group(0)
    assert "fitFrame()" in resize
    assert "fitFrame();" in re.search(r"function frameStatus\(text\)\{.*", APP_JS).group(0)


def test_feed_sort_and_filter_round_trip_through_the_url():
    view = {"sort": "depth", "dir": "desc", "filter": "new"}
    assert encode_feed_view(view) == "sort=depth&filter=new"
    assert decode_feed_view("sort=depth&filter=new") == view
    # A direction that is not the column's default is kept in the URL.
    asc = {"sort": "depth", "dir": "asc", "filter": "known"}
    assert encode_feed_view(asc) == "sort=depth&dir=asc&filter=known"
    assert decode_feed_view(encode_feed_view(asc)) == asc
    assert decode_feed_view("?sort=status&filter=all") == {"sort": "status", "dir": "asc", "filter": "all"}
    # Anything malformed falls back to the default view.
    assert decode_feed_view("") == feed_view(None) == DEFAULT_FEED_VIEW
    assert decode_feed_view("sort=radius&dir=up&filter=planets") == DEFAULT_FEED_VIEW
    # The page reads the same query on load and writes it back when the viewer changes a control.
    assert "'#/discoveries?' + encodeFeedView(currentFeedView())" in APP_JS
    go = re.search(r"function go\(p, moveFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "decodeFeedView(p.params)" in go and "ownFeedView" in go and "syncFeedURL()" in go
    sort_click = re.search(r"\$\('#disctable'\).addEventListener.*?\n\}\);", APP_JS, re.S).group(0)
    chip_click = re.search(r"\$\('#discchips'\).addEventListener.*?\n\}\);", APP_JS, re.S).group(0)
    for handler in (sort_click, chip_click):
        assert "saveFeedView(); syncFeedURL();" in handler
    # localStorage keeps the viewer's default, read inside try/catch.
    assert "s.setItem(FEED_KEY, JSON.stringify(ownFeedView))" in APP_JS
    assert "JSON.parse(s.getItem(FEED_KEY))" in APP_JS


def test_feed_view_round_trips_in_the_page_script(run_dir, catalog, tmp_path):
    """The page's own encode and decode, run under Node, agree with the Python pair."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    page = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text()
    data = _page_data(page)
    funcs = re.search(r"const shortOf = .*?\nfunction decodeFeedView\(params\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    script = ("const D = " + json.dumps({"feed_view": data["feed_view"]}) + ";\n"
              "const FEED_SORTS = D.feed_view.sorts, FEED_FILTERS = D.feed_view.filters, FEED_NUMERIC = D.feed_view.numeric;\n"
              + funcs +
              "const cases = ['sort=depth&filter=new', 'sort=depth&dir=asc&filter=known', '', 'sort=x&filter=y', 'sort=status'];\n"
              "console.log(JSON.stringify(cases.map(c => { const v = decodeFeedView(new URLSearchParams(c)); return [v, encodeFeedView(v)]; })));\n")
    out = json.loads(subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout)
    for (view, text), case in zip(out, ["sort=depth&filter=new", "sort=depth&dir=asc&filter=known", "", "sort=x&filter=y", "sort=status"]):
        assert view == decode_feed_view(case)
        assert text == encode_feed_view(view)


def test_frame_is_hidden_until_the_docket_reports_ready(run_dir, tmp_path):
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    cand = _route(page, "candidates")
    # The frame starts hidden (no height, not visible) and the loading line holds its slot.
    assert '<iframe class="frame waiting" id="docketframe"' in cand
    rule = re.search(r"\.frame\.waiting,[^{]*\{([^}]*)\}", APP_CSS).group(1)
    assert "height:0" in rule and "visibility:hidden" in rule and "min-height:0" in rule
    load = re.search(r"function loadDocket\(dip, section, mode\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.classList.add('waiting')" in load
    ready = re.search(r"function onFrameReady\(m\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.classList.remove('waiting')" in ready
    # The blocked path still hides the frame and shows the message.
    blocked = re.search(r"function showBlocked\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.hidden = true" in blocked and "$('#frameblocked').hidden = false" in blocked
    fit = re.search(r"function fitFrame\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.classList.contains('waiting')" in fit


def test_top_candidate_rows_are_one_44px_line_on_a_phone():
    phone = _phone_css()
    row = re.search(r"\.toplist ul li\.toprow\{([^}]*)\}", phone).group(1)
    assert "height:44px" in row and "white-space:nowrap" in row and "align-items:center" in row
    link = re.search(r"\.toplist ul li\.toprow a\.dip\{([^}]*)\}", phone).group(1)
    assert "height:44px" in link and "padding:0" in link
    # The status keeps a word on the row, and the hedge moves to the signal line.
    assert ".toplist .unc{display:none}" in phone and ".phonehedge{display:inline}" in phone
    widgets = re.search(r"function widgetBody\(id\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert 'class="phonehedge"> · each a ${esc(D.unconfirmed)}' in widgets


def _weights_files(tmp_path, *, with_record=True):
    weights = tmp_path / "w.json"
    weights.write_text(json.dumps({"vol-a": 0.6, "vol-b": 0.05, "claude-x": 0.5}))
    if with_record:
        (tmp_path / "w.calibration.json").write_text(json.dumps({
            "floor": 0.05, "source": "test record",
            "reviewers": {"vol-a": {"tpr": 0.7, "fpr": 0.1, "weight": 0.6, "n_injected": 10, "n_empty": 10},
                          "vol-b": {"tpr": 0.2, "fpr": 0.3, "weight": 0.05, "n_injected": 10, "n_empty": 10},
                          "claude-x": {"tpr": 0.5, "fpr": 0.0, "weight": 0.5, "n_injected": 10, "n_empty": 10}}}))
    return weights


def test_calibration_plane_is_read_from_the_weights_file(run_dir, tmp_path):
    weights = _weights_files(tmp_path)
    page = build_app(run_dir, tmp_path / "app", title="t", weights_path=weights).read_text()
    cal = _page_data(page)["calibration"]
    pts = {p["id"]: p for p in cal["points"]}
    assert set(pts) == {"vol-a", "vol-b", "claude-x"}
    # Weight from the weights file; TPR, FPR and the sample size from the record stored next to it.
    assert pts["vol-a"]["weight"] == 0.6 and pts["vol-a"]["tpr"] == 0.7 and pts["vol-a"]["fpr"] == 0.1
    assert pts["vol-b"]["weight"] == 0.05 and pts["vol-b"]["consistent"] is True  # floored
    assert pts["claude-x"]["n_injected"] == 10 and pts["claude-x"]["n_empty"] == 10
    assert pts["vol-a"]["kind"] == "simulated" and pts["claude-x"]["kind"] == "not in this run"
    assert cal["iso"] == list(ISO_WEIGHTS) and cal["floor"] == 0.05
    assert cal["record_path"].endswith("w.calibration.json")
    # The page draws iso-weight lines, labels the sample size on the plane, and names the kinds.
    plane = re.search(r"function calPlane\(box\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "for (const w of C.iso)" in plane and "`weight ${w}`" in plane
    assert "`Claude: ${fmtN(cl[0])} only`" in plane
    assert "R = w => 3 + 10 * " in plane and "R(g.items[0].weight)" in plane  # size from the stored weight
    sample = re.search(r"function calSample\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "The Claude reviewers were calibrated on" in sample and "subjects only" in sample
    assert "not people" in sample
    panel = _route(page, "panel")
    assert "simulated detector, not a person" in panel and "Claude reviewer, not a person" in panel
    assert 'id="calplane"' in panel and "floored at 0.05" in panel


def test_calibration_plane_never_invents_rates(run_dir, tmp_path):
    # Weights alone: listed with their weight, no rates, nothing plotted.
    weights = _weights_files(tmp_path, with_record=False)
    cal = calibration_plane(json.loads(weights.read_text()), None, {"vol-a": "simulated"})
    assert all(p["tpr"] is None and p["fpr"] is None and p["n_injected"] is None for p in cal["points"])
    assert "nothing to plot" in re.search(r"function calPlane\(box\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    # A weights file whose entries carry their own rates is read directly.
    cal = calibration_plane({"c": {"weight": 0.4, "tpr": 0.5, "fpr": 0.1, "n_injected": 10, "n_empty": 10}}, None, {"c": "claude_code"})
    assert cal["points"][0] | {} == {"id": "c", "kind": "claude_code", "weight": 0.4, "tpr": 0.5, "fpr": 0.1,
                                      "n_injected": 10, "n_empty": 10, "consistent": True}
    # The Panel cards still read a flat weight from either form.
    page = build_app(run_dir, tmp_path / "app", title="t", weights_path=weights).read_text()
    assert {r["id"]: r["calibrated_weight"] for r in _page_data(page)["panel"]} == {"vol-a": 0.6, "vol-b": 0.05}


def test_repository_calibration_record_matches_the_weights_file():
    from exoplan.calibrate import calibration_path

    weights_path = "docs/results/reviewer_weights_full_panel.json"
    weights = json.loads(open(weights_path).read())
    record = json.loads(calibration_path(weights_path).read_text())
    assert set(record["reviewers"]) == set(weights)
    for rid, r in record["reviewers"].items():
        assert r["weight"] == weights[rid] == max(r["tpr"] - r["fpr"], record["floor"])
        assert (r["n_injected"], r["n_empty"]) == (10, 10)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_feed_states_no_detection_when_a_row_is_a_known_toi(run_dir, catalog, tmp_path):
    fn = re.search(r"function archiveNote\(rows\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    head = re.search(r"function renderDiscHead\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    when = re.search(r"function when\(iso\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    esc = re.search(r"const esc = .*\n", APP_JS).group(0)
    script = (esc + when + "const D = " + json.dumps({"no_detection": NO_DETECTION, "unconfirmed": UNCONFIRMED}) + ";\n"
              "let out = ''; const $ = () => ({set innerHTML(v){ out = v; }});\n" + fn + head + """
const known = {candidate_id: 'k', status: 'known_toi'}, fresh = {candidate_id: 'n', status: 'new_candidate'};
const heads = [];
for (const c of [[known, fresh], [fresh]]){ D.catalog = {candidates: c, found_times: []}; renderDiscHead(); heads.push(out); }
console.log(JSON.stringify([archiveNote([known, fresh]), archiveNote([fresh]), heads]));""")
    with_known, without, (head_known, head_new) = json.loads(
        subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert NO_DETECTION in with_known and "archive" in with_known
    assert without == ""
    assert NO_DETECTION in head_known and NO_DETECTION not in head_new
    assert "${noDossierLine(rows)}${archiveNote(rows)}</caption>" in APP_JS
    # The route's header line says it too when the catalogue holds a known TOI match.
    feed = _route(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog).read_text(), "discoveries")
    header = re.search(r"<header>.*?</header>", feed, re.S).group(0)
    assert "match a known TOI period" in header and NO_DETECTION in header


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_narrow_calibration_plane_keeps_weight_labels_level_and_inside():
    """On a phone the weight labels are level, sit above their line's right-hand end and inside the figure."""
    plane = re.search(r"function calPlane\(box\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    sample = re.search(r"function calSample\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    fmt = re.search(r"const fmt = .*\n", APP_JS).group(0)
    fmt_n = re.search(r"const fmtN = .*\n", APP_JS).group(0)
    esc = re.search(r"const esc = .*\n", APP_JS).group(0)
    claude = re.search(r"const isClaude = .*\n", APP_JS).group(0)
    points = [{"id": "a", "kind": "simulated", "weight": 0.6, "tpr": 0.7, "fpr": 0.1, "n_injected": 10, "n_empty": 10},
              {"id": "c", "kind": "claude_code", "weight": 0.5, "tpr": 0.6, "fpr": 0.1, "n_injected": 10, "n_empty": 10}]
    script = (esc + fmt + claude + "const D = " + json.dumps({"calibration": {"points": points, "iso": list(ISO_WEIGHTS), "floor": 0.05}}) + ";\n"
              """
function mk(tag){ const n = {tag, a: {}, kids: [], text: '', style: {}, setAttribute(k, v){ this.a[k] = String(v); }, appendChild(c){ this.kids.push(c); return c; }};
  Object.defineProperty(n, 'textContent', {get(){ return this.text; }, set(v){ this.text = v; }}); return n; }
function el(tag, a={}, p){ const e = mk(tag); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
function tx(svg, x, y, s, anchor='start', cls=''){ const t = el('text', {x, y, 'text-anchor': anchor, class: cls}, svg); t.textContent = s; return t; }
""" + fmt_n + sample + plane + """
const out = {};
for (const w of [330, 560]){
  const box = {clientWidth: w, kids: [], set innerHTML(v){ this.kids = []; }, appendChild(c){ this.kids.push(c); return c; }};
  calPlane(box);
  const svg = box.kids[0], vb = svg.a.viewBox.split(' ').map(Number);
  const iso = svg.kids.filter(k => k.tag === 'text' && (k.a.class || '').includes('isolbl'));
  out[w] = {vb, iso: iso.map(t => ({s: t.text, x: +t.a.x, y: +t.a.y, rot: 'transform' in t.a}))};
}
console.log(JSON.stringify(out));""")
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    narrow, wide = out["330"], out["560"]
    labels = {t["s"]: t for t in narrow["iso"]}
    for w in ISO_WEIGHTS:
        assert str(w) in labels and not labels[str(w)]["rot"]
    assert "0.05 is the floor" in labels
    for t in narrow["iso"]:
        assert t["y"] >= 11 and t["y"] <= narrow["vb"][3]  # a 10 px label whose baseline is at least 11 px down is not cut
    # Level labels left to right in the order their lines end on the top edge.
    xs = [labels[str(w)]["x"] for w in sorted(ISO_WEIGHTS, reverse=True)]
    assert xs == sorted(xs) and min(b - a for a, b in zip(xs, xs[1:])) > 25
    # A wide plane keeps the labels along the lines.
    assert all(t["rot"] for t in wide["iso"]) and len(wide["iso"]) == len(ISO_WEIGHTS)

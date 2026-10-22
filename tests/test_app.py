# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
import json
import re
import shutil
import subprocess

import pytest

from setuhq import docket as docket_mod
from setuhq.app import (
    APP_CSS,
    APP_JS,
    FRAME_BRIDGE_JS,
    FRAME_PHONE_CSS,
    FRAME_THEME_CSS,
    DOCKET_FONTS,
    FONTS_CSS,
    FRAME_FONTS_HREF,
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
    feed_label,
    feed_view,
    radius_ratio,
    widget_layout,
)
from setuhq.cli import main
from setuhq.docket import NO_STORED_CROSSMATCH
from conftest import site_bundle

WIDGET_IDS = [w for w, _ in WIDGETS]


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    """No test reaches the network: the archive query fails as it would offline."""

    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def run_dir(app_run):
    return app_run


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
    """The app's data (assets/data/app-*.json), with the case file's framed Docket (a file of its own) as docket_html."""
    raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
    data = json.loads(raw.replace("<\\/", "</"))
    frame = re.search(r'<template id="docket-frame">(.*)</template>', page, re.S)
    if frame:
        data["docket_html"] = frame.group(1)
    return data


def _route(page: str, sid: str) -> str:
    return re.search(rf'<section class="route" id="route-{sid}".*?(?=<section class="route" id="route-|</main>)', page, re.S).group(0)


def test_app_builds_from_run_dir_and_catalogue(run_dir, catalog, tmp_path):
    assert main(["app", str(run_dir), "--catalog", str(catalog), "--out", str(tmp_path / "app"), "--title", "setuhq",
                 "--allow-missing-crossmatch"]) == 0
    page = site_bundle(tmp_path / "app" / "index.html")
    data = _page_data(page)
    assert data["title"] == "setuhq"
    assert [c["candidate_id"] for c in data["catalog"]["candidates"]] == ["tess-x-001", "tess-y-002"]
    assert data["catalog"]["runs"][0]["errors"] == ["TIC 9: LookupError: no SPOC 120s light curves found for 'TIC 9'"]
    assert data["config"]["config_name"] == "app"
    assert {r["id"] for r in data["panel"]} == {"vol-a", "vol-b"}
    assert all(r["kind"] == "simulated" for r in data["panel"])
    # The Docket the case file frames is a file of its own, rendered by docket.py, beside the site.
    frame = tmp_path / "app" / data["docket_frame"].lstrip("/")
    assert data["docket_frame"].startswith("/assets/frame/") and frame.read_text().startswith("<!doctype html>")
    # Every script is the site's own: no script from another site.
    home = (tmp_path / "app" / "index.html").read_text()
    assert all(src.startswith("/assets/") for src in re.findall(r'<script[^>]+src="([^"]+)"', home))
    # The stand-alone pages the command also builds, and every old address forwarding.
    for sub in ("candidates/case-file", "evidence/plates", "evidence/report", "app", "docket", "plate", "report"):
        assert (tmp_path / "app" / sub / "index.html").exists(), sub


def test_app_builds_without_catalogue(run_dir, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    data = _page_data(page)
    assert data["catalog"]["candidates"] == [] and data["catalog"]["runs"] == []


def test_five_sections_and_every_view_exist(run_dir, catalog, tmp_path):
    from setuhq.app import ROUTE_ALIASES, ROUTE_META, SUBNAV

    index = build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog)
    page = site_bundle(index)
    assert SECTIONS == [("explore", "Explore"), ("candidates", "Candidates"), ("how", "How it works"), ("evidence", "Evidence"), ("docs", "Docs")]
    nav = re.search(r'<nav class="nav" aria-label="Main">.*?</nav>', index.read_text(), re.S).group(0)
    for sid, label in SECTIONS:
        assert f'data-nav="{sid}">{label}</a>' in nav
    assert "#/" not in nav
    # Every view of the app has its section and its heading, and belongs to one section of the top bar.
    views = [r for r in ROUTE_META if r != "notfound" and not ROUTE_META[r].get("page")]
    for sid in views:
        assert f'id="route-{sid}"' in page
        assert re.search(rf'<h1 [^>]*id="h-{sid}" tabindex="-1">', page), sid
        assert ROUTE_META[sid]["nav"] in (None, *dict(SECTIONS)), sid
    # Every view but the planet and star pages is listed in its section's sub-navigation or is the section's own page.
    listed = {r for items in SUBNAV.values() for _, _, rs in items for r in rs}
    assert set(views) - listed - {"overview", "methods", "docs"} == set()
    # Old addresses open the view that replaced them (setuhq.routes forwards them).
    assert ROUTE_ALIASES["discoveries"] == "explorer" and ROUTE_ALIASES["panel"] == "sentinels"
    assert _page_data(page)["routes"]["aliases"] == ROUTE_ALIASES
    assert "aria-current" in APP_JS


def test_planet_cards_never_state_an_earth_or_jupiter_radius(run_dir, catalog, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
    data = _page_data(page)
    planets = _route(page, "planets")
    no_radius = re.compile(r"\d\s*(R⊕|R_⊕|R♃|R_?J\b|R_?E\b|R_?earth|R_?jup|Earth radi|Jupiter radi|M⊕)", re.I)
    assert not no_radius.search(planets)
    # The Galaxy shows catalogue radii as the catalogue stores them; the run's own dips never get one.
    from setuhq.galaxy import GALAXY_JS
    from setuhq.methods import METHODS_JS
    from setuhq.catalogue import CATALOGUE_JS
    assert not no_radius.search(APP_JS.replace(GALAXY_JS, "").replace(METHODS_JS, "").replace(CATALOGUE_JS, ""))
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
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
    data = _page_data(page)
    assert data["unconfirmed"] == UNCONFIRMED == "candidate, unconfirmed"
    for sid in ("candidates", "explorer", "planets", "sky"):
        assert UNCONFIRMED in _route(page, sid), sid
    # The case file's intro names what is a candidate and what is not.
    assert f"Each signal that passed vetting is a {UNCONFIRMED}; a rejected or flagged one is named by its status." in _route(page, "candidates")
    assert "Every signal here is a" not in page
    # A dip's page says its own status (candidate, flagged or rejected), from its vetting outcome.
    assert "${DIPPHRASE(d.outcome)}" in re.search(r"function renderTransit\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "const DIPTAG = o =>" in APP_JS and "D.dip_state" in APP_JS
    # Rendered rows: the feed table status cell, the timeline dots, the top-candidates
    # widget and every planet entry carry the wording or the status tag.
    status_col = re.search(r"\['status', 'status'.*?\],\n", APP_JS, re.S).group(0)
    assert "FEEDTAG(x)" in status_col
    timeline = re.search(r"function timeline\(box\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "D.unconfirmed" in timeline
    widgets = re.search(r"function widgetBody\(id\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "${DIPTAG(x.outcome)}" in widgets  # the top dips: each tagged by its own outcome
    planets = re.search(r"function renderPlanets\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "DIPTAG(e.outcome) : UNC}" in planets and "D.no_detection" in planets  # a run dip by its outcome, a feed entry by the hedge
    assert "candidate, unconfirmed" in data["docket_html"]
    # The feed rule is shown as a rule, not a vetting result.
    disc = _route(page, "explorer")
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
    # The page reads the same string from a shared link's query (/candidates/?layout=...), and writes it only
    # into the link that "Copy link to this view" makes.
    assert "'layout=' + encodeLayout(layout)" in APP_JS
    assert "p.params.get('layout')" in APP_JS
    assert re.search(r"function syncLayoutURL\(\)\{ /\* nothing", APP_JS)


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
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
    data = _page_data(page)
    ids = [c["candidate_id"] for c in json.loads((run_dir / "candidates.json").read_text())]
    assert data["dossier_ids"] == ids
    # One link builder, to the dip's case file (/candidates/<dip>/case-file/), used by the widgets, the Planets, the Panel and the feed.
    assert "const dipHref = (id, section) => rtUrl('candidates', {dip: id, section: section || null});" in APP_JS
    for fn in ("widgetBody", "renderPlanets", "renderPanel"):
        body = re.search(rf"function {fn}\(.*?\n\}}\n", APP_JS, re.S).group(0)
        assert "dipLink(" in body, fn
    assert "x => dipLink(x.candidate_id)" in APP_JS
    # The top-candidates widget is a list of links, not a table without anchors.
    top = re.search(r"function topBody.*?\n  \}\n", APP_JS, re.S).group(0)
    assert "<table" not in top and "dipLink(x.id)" in top
    # The shell forwards the dip in its address to the Docket frame as the frame's location hash.
    assert "p.params.get('dip')" in APP_JS
    assert "return ((D.docket_frames || {})[runOf(dip)] || D.docket_frame) + (dip ? '#' + encodeURIComponent(dip) : '');" in APP_JS
    assert "fromHash = decodeURIComponent(location.hash.slice(1))" in data["docket_html"]


def test_skip_target_is_not_a_route(run_dir, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    href = re.search(r'<a class="skip" href="#([^"]+)"', page).group(1)
    assert not href.startswith("/") and href not in [s for s, _ in SECTIONS]
    assert re.search(rf'<div id="{href}" tabindex="-1">', page)
    assert page.index('<main id="main">') < page.index(f'id="{href}"')
    # The router reads the path; a plain hash on the same page (the skip link's) is left to the browser.
    assert "if (u.pathname === location.pathname && u.search === location.search && u.hash && current !== 'candidates') return;" in APP_JS
    assert "rtParse(location.pathname, location.search)" in APP_JS


def test_top_bar_has_five_sections_search_theme_and_a_phone_menu(run_dir, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    top = re.search(r'<header class="topbar">.*?</header>', page, re.S).group(0)
    assert '<nav class="nav" aria-label="Main">' in top and 'class="brand"' in top and "data-theme-toggle" in top
    assert 'id="gsearchbtn"' in top and 'id="menubtn" aria-expanded="false" aria-controls="menu"' in top and 'id="menu" hidden' in top
    # No run chip, no current-page label, no visible theme words: icons with accessible names.
    assert "Sector 1" not in top and 'id="curlabel"' not in top and "Dark (default)" not in top and "themelbl" not in top
    assert 'id="sidebar"' not in page and "openDrawer" not in APP_JS
    # The bar's height (two rows on a phone) is measured into --top for the case file's frame.
    assert "document.documentElement.style.setProperty('--top'" in APP_JS and "ResizeObserver" in APP_JS
    assert "-webkit-backdrop-filter:saturate(180%) blur(24px)" in APP_CSS


def test_shell_and_docket_use_only_self_hosted_fonts(run_dir, tmp_path):
    out = build_app(run_dir, tmp_path / "app", title="t")
    page = site_bundle(out)
    data = _page_data(page)
    assert "fonts.googleapis.com" not in page and "fonts.gstatic.com" not in page
    assert f'<link rel="stylesheet" href="{FONTS_CSS}">' in page
    css = (out.parent / FONTS_CSS.lstrip("/")).read_text()
    for family in ("Geist", "Geist Mono", "Unbounded"):
        assert f"font-family: '{family}'" in css
    for url in re.findall(r"url\((files/[^)]+)\)", css):
        assert (out.parent / "assets" / "fonts" / url).stat().st_size > 1000, url
    assert (out.parent / "assets" / "fonts" / "OFL-geist.txt").exists()
    # The framed copy, served from assets/frame/, links the site's one copy of the fonts.
    assert FRAME_FONTS_HREF == FONTS_CSS == "/assets/fonts/fonts.css"
    assert f'href="{FONTS_CSS}"' in data["docket_html"] and "fonts.googleapis.com" not in data["docket_html"]
    assert "Inter Tight" not in data["docket_html"] and "JetBrains Mono" not in data["docket_html"]
    # The standalone Docket loads its own copy of the same fonts, beside it.
    docket = docket_mod.build_docket(run_dir, tmp_path / "docket", title="t")
    standalone = docket.read_text()
    assert "fonts.googleapis.com" not in standalone and '<link rel="stylesheet" href="assets/fonts/fonts.css">' in standalone
    assert (docket.parent / "assets" / "fonts" / "fonts.css").exists() and '"Geist"' in standalone


def test_tokens_follow_the_approved_design():
    root = re.search(r":root\{color-scheme:dark;(.*?)\}", APP_CSS, re.S).group(1)
    for token in ("--bg:#000", "--ink:#F5F5F7", "--blue:#0A84FF", "--yellow:#FFD60A", "--red:#FF453A",
                  "--sen:#64D2FF", "--prb:#BF5AF2", "--star:#FFB340"):
        assert token in root, token
    # Dark first; light on request, or with the system when the viewer chooses "system".
    assert ':root[data-theme="light"]{color-scheme:light;' in APP_CSS
    assert '@media (prefers-color-scheme: light){:root[data-theme="system"]' in APP_CSS


def test_feed_no_detection_wording_matches_the_plate():
    from setuhq import plate

    assert NO_DETECTION == plate.NO_DETECTION == "Archive values only. This page claims no detection."


def test_overview_hero_states_the_argument_from_stored_values(run_dir, catalog, tmp_path):
    data = app_data(run_dir, title="t", catalog_path=catalog)
    hero = data["hero"]
    lead = hero["lead"]
    # The lead signal is a periodic signal; its depth is the median stored depth of its dips.
    assert lead is not None and lead["period_days"] > 0 and lead["n_dips"] >= 2
    assert f"{lead['depth_ppm']:,.0f} ppm dip every {lead['period_days']:,.2f} days" in hero["headline"]
    assert hero["accent"] == "Candidate, unconfirmed."
    # No claim of a planet, a radius or a detection; the archive line says the cross-match did not run.
    text = " ".join([hero["headline"], hero["lede"], hero["archive"]])
    assert not re.search(r"\b(planet found|discovered|confirmed planet|radius of)\b", text, re.I)
    assert "(no people)" in hero["lede"] and "2 Probes" in hero["lede"]
    assert "does not say whether" in hero["archive"]
    assert "Stored error, verbatim: " + NO_STORED_CROSSMATCH in hero["archive"] and "unreachable" not in hero["archive"]
    # Windows are lettered in time order and carry their outcome; the curve is the stored flux in ppm.
    assert [w["letter"] for w in hero["windows"]][:3] == ["1", "2", "3"][:len(hero["windows"])]
    assert [w["t_start"] for w in hero["windows"]] == sorted(w["t_start"] for w in hero["windows"])
    assert sum(len(s["t"]) for s in hero["subjects"]) == hero["n_points"]
    subj = hero["subjects"][0]
    assert len(subj["t"]) == len(subj["ppm"])
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
    overview = _route(page, "overview")
    assert "What this page does not claim" in overview and "No stellar radius is stored" in overview
    assert UNCONFIRMED in overview and NO_DETECTION.split(". ")[1] in overview
    # The Sky section carries the run's argument: the lede, its qualifier and the archive line.
    sky = _route(page, "sky")
    assert html_unescape(hero["lede"]) in html_unescape(sky) and "does not say whether" in html_unescape(sky)


def html_unescape(text: str) -> str:
    import html

    return html.unescape(text)


def test_planets_state_the_stellar_radius_limitation_once(run_dir, catalog, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
    planets = _route(page, "planets")
    assert planets.count(NO_STELLAR_RADIUS) == 1
    body = re.search(r"function renderPlanets\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "no_stellar_radius" not in body and "stellar radius" not in body
    # The size bar is a labelled ratio scale with a stated maximum, and the working is shown.
    assert "on a scale from 0 to" in body and "max</span>" in body and "√depth = √(" in body
    assert "ratio scale from 0 to 0.10" in planets


def test_panel_lists_marks_per_dip(run_dir, catalog, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
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
    assert "${a.n_claude} of ${plural(a.of_claude, 'Sentinel')}, ${a.n_sim} of ${plural(a.of_sim, 'Probe')}" in body
    assert "dipHref(a.id, 'ledger')" in body and "Verdict ledger" in body
    assert "not a person" in body
    assert "Marks per dip" in _route(page, "sentinels")


ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def test_no_raw_iso_timestamp_in_overview_or_runs_headings(run_dir, catalog, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
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
    assert feed_label(data["catalog"]["candidates"]) == "Discoveries"
    mostly_known = json.loads(catalog.read_text())
    mostly_known["candidates"][0]["status"] = "known_toi"
    path = tmp_path / "known.json"
    path.write_text(json.dumps(mostly_known))
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=path))
    assert '<h2 id="h-feedsec">From the search feed: ' in page
    assert re.search(r"2 of \d+ match a known TOI period", _route(page, "explorer"))


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
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    docket_html = _page_data(page)["docket_html"]
    # The shell's copy of the Docket carries the bridge; the standalone Docket page does not.
    assert FRAME_BRIDGE_JS in docket_html and docket_html.index(FRAME_BRIDGE_JS) < docket_html.index("</head>")
    standalone = docket_mod.docket_page(docket_mod.docket_data(run_dir, title="t"))
    assert FRAME_BRIDGE_JS not in standalone and "postMessage" not in standalone
    assert FRAME_PHONE_CSS == ""  # the phone rules ship in the Docket itself now
    injected = f"<style>{FRAME_THEME_CSS}{FRAME_PHONE_CSS}</style><script>{FRAME_BRIDGE_JS}</script>"
    # Apart from the injected block, the copy differs from the Docket only in its font families.
    expected = (docket_mod.docket_page(docket_mod.docket_data(run_dir, title="t · candidates"))
                .replace(DOCKET_FONTS, FRAME_FONTS_HREF).replace('"Inter Tight"', '"Geist"').replace('"JetBrains Mono"', '"Geist Mono"'))
    assert docket_html.replace(injected, "") == expected
    assert FRAME_THEME_CSS not in standalone
    # The bridge reports every selection (the Docket selects by history.replaceState) and section anchors.
    assert "if (window.parent === window) return;" in FRAME_BRIDGE_JS
    assert "history.replaceState = function(){" in FRAME_BRIDGE_JS and "send({kind: 'dip'})" in FRAME_BRIDGE_JS
    assert "addEventListener('hashchange'" in FRAME_BRIDGE_JS and "kind: 'section'" in FRAME_BRIDGE_JS
    assert "P.postMessage(m, '*')" in FRAME_BRIDGE_JS
    # The shell takes messages only from its own frame and writes them to its URL and full-page links.
    listener = re.search(r"window.addEventListener\('message', e => \{.*?\n\}\);\n", APP_JS, re.S).group(0)
    assert "e.source !== f.contentWindow" in listener and "m.source !== 'setuhq-docket'" in listener
    sync = re.search(r"function syncShellURL\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "setHash(h, push)" in sync and "setFullHrefs(frame.dip)" in sync
    assert "'#fullpage, #topfull, #blockedlink'" in APP_JS
    # A cross-origin frame (file://) is named in the page rather than failing silently.
    assert "frame.crossOrigin = true" in APP_JS and "separate origin" in APP_JS


def test_blocked_frame_shows_a_message_and_a_link(run_dir, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    cand = _route(page, "candidates")
    msg = re.search(r'<p class="note blocked" id="frameblocked" role="alert" hidden>(.*?)</p>', cand).group(1)
    assert msg == 'The case file could not load in this view. <a id="blockedlink" href="/candidates/case-file/">Open it on its own page.</a>'
    # A frame that never reports ready is replaced by the message; the frame is hidden.
    failed = re.search(r"function frameLoadFailed\(gen\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "showBlocked()" in failed
    blocked = re.search(r"function showBlocked\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "f.hidden = true" in blocked and "$('#frameblocked').hidden = false" in blocked
    # The frame is a same-origin file: six seconds to report ready before the message shows.
    assert "setTimeout(() => frameLoadFailed(gen), 6000)" in APP_JS
    assert ".frame[hidden]{display:none}" in APP_CSS


def _phone_css() -> str:
    start = APP_CSS.index("@media (max-width:699.98px){")
    return APP_CSS[start:APP_CSS.index("\n}\n", start)]


def test_phone_touch_targets_are_at_least_44px():
    phone = _phone_css()
    rules = dict(re.findall(r"^\s*([^{}\n]+)\{([^}]*)\}", phone, re.M))

    def has(selector, prop):
        return any(selector in [x.strip() for x in sel.split(",")] and prop in body for sel, body in rules.items())

    for sel in ("main a", "summary", ".btn", ".chip", "th button"):
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
    # (and the theme choice, in applyTheme, and the Learn path's progress, in learnSave).
    # (and Mission Control's saved default, in its "Save as my default" handler).
    # (and, in sessionStorage only, that the Sky's or Galaxy's survey-scan intro has played, in mxIntroEnd).
    assert APP_JS.count("setItem(") == 5 and APP_JS.count("setItem(LAYOUT_KEY") == 1 and APP_JS.count("s.setItem(MC_KEY") == 1
    assert "sessionStorage.setItem('setuhq-intro-' + I.key, 'done')" in re.search(r"function mxIntroEnd\(I, skipped\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "s.setItem(LEARN_KEY" in re.search(r"function learnSave\(\)\{.*?\}\s*\}", APP_JS, re.S).group(0)
    from setuhq.site import SHELL_JS

    assert "localStorage.setItem('setuhq-theme', t)" in re.search(r"function applyTheme\(t, announce\)\{.*?\n\}\n", SHELL_JS, re.S).group(0)
    assert "s.setItem(LAYOUT_KEY" in re.search(r"function saveLayout\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "s.setItem(FEED_KEY" in re.search(r"function saveFeedView\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    callers = [m.start() for m in re.finditer(r"saveLayout\(\);", APP_JS)]
    action = re.search(r"function layoutAction\(.*?\n\}\n", APP_JS, re.S)
    reset = re.search(r"\$\('#resetlayout'\)\.addEventListener.*?\n", APP_JS)
    assert callers and all(action.start() < c < action.end() or reset.start() < c < reset.end() for c in callers)
    # The page says when a shared layout is showing, and offers a link to copy the current one.
    assert "navigator.clipboard.writeText(url)" in APP_JS and "'layout=' + encodeLayout(layout)" in APP_JS


def test_candidates_have_shared_note_and_copy_link(run_dir, tmp_path):
    cands = _route(site_bundle(build_app(run_dir, tmp_path / "app", title="t")), "explorer")
    # One "Copy link to this view" (the page's own, beside the breadcrumbs); the card controls wait behind Customise.
    assert 'id="copylayout"' not in cands and "Copy link to this view" not in cands
    assert '<button class="btn" id="customise" type="button" aria-pressed="false" aria-controls="widgets layouttools">Customise</button>' in cands
    assert '<div class="layoutbar" id="layouttools" role="group" aria-label="Arrange the cards" hidden>' in cands
    assert 'id="sharednote" hidden>This is a shared view, shown for this visit only.' in cands


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
    assert "frame.shellURLFailed = !setHash(h, push)" in APP_JS


def test_frame_shows_a_loading_status_while_it_loads():
    load = re.search(r"function loadDocket\(dip, section, mode\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "frameStatus(LOADING_TEXT);" in load
    assert "const LOADING_TEXT = 'Loading the Docket…';" in APP_JS
    # Once ready, the loading line is replaced (cleared, or a note on the frame's origin or address).
    ready = re.search(r"function onFrameReady\(m\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "readyStatus();" in ready


def test_phone_rule_in_the_docket_makes_44px_targets(run_dir, tmp_path):
    css = docket_mod.DOCKET_CSS
    block = css[css.index("@media (max-width:700px){"):]
    block = block[:block.index("\n}\n")]
    assert ".jumplist,.dippick{display:none}" in css
    rules = dict(re.findall(r"([^{}]+)\{([^{}]*)\}", block[block.index("{") + 1:]))
    covered = {sel.strip(): body for sels, body in rules.items() for sel in sels.split(",")}
    for cls in (".dipbtn", ".chip", ".sectoggle", ".listtoggle"):
        assert "min-height:44px" in covered[cls] and "padding:" in covered[cls], cls
        assert "font-size" not in covered[cls]
    # After the Docket's own rules, so it wins at equal specificity; in both the standalone page and the shell's copy.
    assert css.index("@media (max-width:700px){") > css.index(".dipbtn{")
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    assert "@media (max-width:700px){" in _page_data(page)["docket_html"]


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
    assert "fv === encodeFeedView(D.feed_view.default) ? '' : fv" in APP_JS and "'#/explorer' + (q ? '?' + q : '')" in APP_JS
    go = re.search(r"function go\(p, moveFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    # Opening the page never writes the view into the address; a change tidies the address to the page's own.
    assert "decodeFeedView(p.params)" in go and "ownFeedView" in go and "syncFeedURL()" not in go
    sort_click = re.search(r"\$\('#disctable'\).addEventListener.*?\n\}\);", APP_JS, re.S).group(0)
    chip_click = re.search(r"\$\('#discchips'\).addEventListener.*?\n\}\);", APP_JS, re.S).group(0)
    for handler in (sort_click, chip_click):
        assert "saveFeedView(); syncFeedURL(true);" in handler  # a viewer's change is a new history entry
    # localStorage keeps the viewer's default, read inside try/catch.
    assert "s.setItem(FEED_KEY, JSON.stringify(ownFeedView))" in APP_JS
    assert "JSON.parse(s.getItem(FEED_KEY))" in APP_JS


def test_feed_view_round_trips_in_the_page_script(run_dir, catalog, tmp_path):
    """The page's own encode and decode, run under Node, agree with the Python pair."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
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
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
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
    # The status keeps a word on the row, with the dip's own status tag (no blanket hedge on the signal line).
    widgets = re.search(r"function widgetBody\(id\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "phonehedge" not in widgets and "${DIPTAG(x.outcome)}</li>" in widgets


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
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", weights_path=weights))
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
    assert "`Sentinels: ${fmtN(cl[0])} only`" in plane
    assert "R = w => 3 + 10 * " in plane and "R(g.items[0].weight)" in plane  # size from the stored weight
    sample = re.search(r"function calSample\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "The Sentinels were calibrated on" in sample and "subjects only" in sample
    assert "Calibrated weights: ${cl.length ? `Sentinels ${range(cl)}`" in sample
    assert "not people" in sample
    panel = _route(page, "sentinels")
    assert "Probe (deterministic detector), not a person" in panel and "Sentinel (Claude), not a person" in panel
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
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", weights_path=weights))
    assert {r["id"]: r["calibrated_weight"] for r in _page_data(page)["panel"]} == {"vol-a": 0.6, "vol-b": 0.05}


def test_repository_calibration_record_matches_the_weights_file():
    from setuhq.calibrate import calibration_path

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
    feed = _route(site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog)), "explorer")
    header = re.search(r'<div class="secthead"><h2 id="h-feedsec">.*?</div>', feed, re.S).group(0)
    assert "match a known TOI period" in header and NO_DETECTION in header


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_narrow_calibration_plane_keeps_weight_labels_level_and_inside():
    """On a phone the weight labels are level, sit above their line's right-hand end and inside the figure."""
    plane = re.search(r"function calPlane\(box\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    sample = re.search(r"function calSample\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    fmt = re.search(r"const fmt = .*\n", APP_JS).group(0)
    fmt_n = re.search(r"const fmtN = .*\n", APP_JS).group(0)
    esc = re.search(r"const esc = .*\n", APP_JS).group(0)
    sentinel = "".join(re.search(rf"const {name} = .*\n", APP_JS).group(0) for name in ("SENTINEL_KINDS", "isSentinel", "PROVIDER_OF"))
    claude = "const D0 = {};\n" + re.search(r"const plural = .*\n", APP_JS).group(0) + "const NAME = id => id;\n"
    points = [{"id": "a", "kind": "simulated", "weight": 0.6, "tpr": 0.7, "fpr": 0.1, "n_injected": 10, "n_empty": 10},
              {"id": "c", "kind": "claude_code", "weight": 0.5, "tpr": 0.6, "fpr": 0.1, "n_injected": 10, "n_empty": 10}]
    script = (esc + fmt + claude + "const D = " + json.dumps({"calibration": {"points": points, "iso": list(ISO_WEIGHTS), "floor": 0.05}}) + ";\n"
              + sentinel +
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


def test_overview_names_the_archive_match_from_the_stored_fallback(run_dir, tmp_path):
    """A run whose own cross-match did not run uses the repository's stored one, and says so."""
    target = json.loads((run_dir / "candidates.json").read_text())[0]["target"]
    data0 = app_data(run_dir, title="t")
    period = data0["hero"]["lead"]["period_days"]
    fb = {"status": "matched", "targets": [target], "star": None, "source": "test fallback",
          "fetched_at": "2026-10-16T22:59:37+00:00",
          "planets": [{"pl_name": "Test c", "hostname": "Test", "pl_orbper": period * 1.0005, "pl_tranmid": None,
                       "tran_flag": True, "rv_flag": None, "tic_id": target}]}
    path = tmp_path / "fb.json"
    path.write_text(json.dumps(fb))
    stored = {"status": "not_run", "targets": [target], "star": None, "planets": [],
              "error": "ModuleNotFoundError: No module named 'astroquery'"}
    (run_dir / "crossmatch.json").write_text(json.dumps(stored))
    try:
        dock = docket_mod.docket_data(run_dir, title="t", crossmatch_fallback=path)
        assert dock["crossmatch"]["fallback_from"] == str(path) and dock["crossmatch"]["run_error"] == stored["error"]
        from setuhq import app as app_mod

        hero = app_mod.overview_hero(dock, [{"signal_id": dock["candidates"][0]["signal_id"], "consistent_with": "Test c"}])
        assert hero["headline"].endswith(", consistent with Test c.") and hero["accent"] == "A known planet, not a discovery."
        assert "consistent with Test c, a published planet: a known planet, not a discovery." in hero["archive"]
        assert "(the repository's stored copy)" in hero["archive"] and str(path) not in hero["archive"] and NO_DETECTION in hero["archive"]
    finally:
        (run_dir / "crossmatch.json").unlink()


def test_repository_pi_men_crossmatch_states_its_source():
    from pathlib import Path

    from setuhq.docket import DEFAULT_CROSSMATCH

    stored = json.loads(Path(DEFAULT_CROSSMATCH).read_text())
    assert stored["status"] == "matched" and stored["targets"] == ["TIC 261136679"]
    assert [p["pl_name"] for p in stored["planets"]] == ["pi Men c"]
    assert stored["planets"][0]["pl_orbper"] == 6.26784  # as docs/results/pi_men_validation.md records it
    assert "pi_men_validation.md" in stored["source"] and "setuhq crossmatch runs/tess-pi-men-s1" in stored["source"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_unknown_dip_shows_a_notice_and_rewrites_to_the_lead_dip():
    open_dip = re.search(r"function openDip\(dip, section\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    status = re.search(r"function frameStatus\(text\)\{.*?\}\n", APP_JS, re.S).group(0)
    lead = re.search(r"const leadDip = .*\n", APP_JS).group(0)
    script = ("const D = {run: {name: 'run-1'}, dossier_ids: ['a', 'b'], hero: {lead: {dip: 'b'}}};\n"
              "const DIP_IDS = new Set(D.dossier_ids), DOCKET_SECTIONS = ['ledger'], LOADING_TEXT = 'Loading';\n"
              "const frame = {ready: true, notice: ''}; const said = [], hashes = [], told = [];\n"
              "const el = {dataset: {loaded: '1'}, textContent: '', hidden: true};\n"
              "const $ = () => el; const say = m => said.push(m); const fitFrame = () => {};\n"
              "const setAddress = (h, push) => { hashes.push([h, push]); return true; };\n"
              "const dipHref = id => '/candidates/' + id + '/case-file/';\n"
              "const readyStatus = () => frameStatus(''); const tellFrame = d => told.push(d);\n"
              "const loadDocket = () => {}; const setFullHrefs = () => {}; const syncShellURL = () => {};\n"
              + lead + status + open_dip +
              "openDip('zzz', null);\n"
              "console.log(JSON.stringify({said, hashes, told, status: el.textContent, hidden: el.hidden}));")
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out["status"] == "No dip zzz in run run-1; showing the lead dip b." and out["hidden"] is False
    assert out["hashes"] == [["/candidates/b/case-file/", False]]  # replaced, not a new history entry
    assert out["told"] == ["b"] and out["said"][0].startswith("No dip zzz")
    # An address no view has shows the Page not found view (404.html is served for it).
    assert "if (!$('#route-' + p.route)) p.route = 'notfound';" in APP_JS


def test_viewer_changes_are_history_entries_and_back_is_followed():
    hist = re.search(r"function setAddress\(url, push\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "history.pushState(null, '', url)" in hist and "history.replaceState(null, '', url)" in hist
    # The views name places in the old form; the address bar gets the clean path, without view state.
    assert "rtFromHash(url, false)" in hist and "const setHash = setAddress;" in APP_JS
    sync = re.search(r"function syncShellURL\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "const push = !!frame.dip && !!shown && shown !== frame.dip;" in sync
    # A link to another page of the app is a new history entry made in place; Back and Forward are followed.
    nav = re.search(r"function navTo\(href\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "history.pushState(null, '', u.pathname + u.search + u.hash)" in nav and "go(parseLoc(), true)" in nav
    assert "window.addEventListener('popstate', () => {" in APP_JS


def test_theme_control_meta_and_first_paint(run_dir, tmp_path):
    from setuhq.site import SHELL_JS, SITE_CSS

    index = build_app(run_dir, tmp_path / "app", title="t")
    page = index.read_text()
    head = page[:page.index("</head>")]
    assert '<meta name="description" content="' in head and "candidate, unconfirmed" in head
    assert '<meta name="color-scheme" content="dark light">' in head
    assert head.count('<meta name="theme-color"') == 1
    # The stored choice is applied by an inline script before the stylesheet: no flash of the wrong theme.
    assert head.index("localStorage.getItem('setuhq-theme')") < head.index('<link rel="stylesheet" href="/assets/site-')
    assert "try{" in head and "catch(e){}" in head
    # One control, in the top bar: an icon, a 44 px target, named for screen readers (no visible words).
    assert page.count('<button class="iconbtn themebtn" type="button" data-theme-toggle aria-label="Colour theme: dark. Switch to light"') == 1
    assert ".iconbtn{width:44px;height:44px" in SITE_CSS
    apply = re.search(r"function applyTheme\(t, announce\)\{.*?\n\}\n", SHELL_JS, re.S).group(0)
    assert "setAttribute('data-theme', t)" in apply and "try {" in apply and "new CustomEvent('setuhq-theme'" in apply
    assert "postMessage({source: 'setuhq-shell', theme: e.detail}" in APP_JS
    assert "SETUHQ_THEMES = ['dark', 'light', 'system']" in SHELL_JS and "var t='dark'" in head
    # The framed Docket follows the theme.
    assert "document.documentElement.setAttribute('data-theme', m.theme)" in FRAME_BRIDGE_JS
    assert ':root[data-theme=\"light\"]' in FRAME_THEME_CSS and "--paper:#000" in FRAME_THEME_CSS


def test_phone_feed_is_three_line_cards_with_a_distinct_sort_group(run_dir, catalog, tmp_path):
    phone = _phone_css()
    # The table's caption (with the no-detection line) stays; its head and body give way to cards.
    assert "#disctable thead,#disctable tbody{display:none}" in phone and "#disctable table,#disctable caption{display:block}" in phone
    assert ".feedcards{display:grid" in phone and ".sortbar{display:flex" in phone
    # Sort buttons are outlined (dashed), unlike the filled filter chips, inside a labelled group.
    assert "border:1px dashed var(--line-3)" in re.search(r"\.sortbtn\{[^}]*\}", phone).group(0)
    bar = re.search(r"function feedSortBar\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert 'role="group" aria-label="Sort by"' in bar and '<span class="sortlbl" aria-hidden="true">Sort</span>' in bar
    assert "aria-pressed" in bar
    cards = re.search(r"function feedCards\(rows\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert cards.count('<div class="fc') == 3 and "${FEEDTAG(x)}" in cards
    assert "${ticLink(x.tic)} · P ${fmt(x.period_days,3)} d · ${fmt(x.depth_ppm,0)} ppm · SNR ${fmt(x.snr,1)}" in cards
    assert "#caltable{display:none}" in phone and ".calcards{display:grid" in phone
    cal = re.search(r"function renderCalibration\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "$('#calcards').innerHTML" in cal and "<dl class=\"kv calcard\">" in cal
    # Desktop: every feed row shows (no clipped scroll box), and the region's name says so.
    assert ".tablewrap.scrollbox{overflow-x:auto}" in APP_CSS and "max-height:70vh" not in APP_CSS
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t", catalog_path=catalog))
    assert 'aria-label="Feed table, every entry shown; scrolls sideways when wider than the screen"' in page


def test_hero_qualifies_an_archive_match_in_the_lede_and_the_box(run_dir, tmp_path):
    from setuhq import app as app_mod

    dock = docket_mod.docket_data(run_dir, title="t")
    sig = dock["candidates"][0]["signal_id"]
    matched = app_mod.overview_hero(dock, [{"signal_id": sig, "consistent_with": "Test c"}])
    assert matched["qualifier"] == app_mod.MATCH_QUALIFIER and matched["match"] == "Test c"
    assert "unconfirmed as an independent detection" in matched["qualifier"]
    assert "not that this run confirmed it" in matched["qualifier"]
    plain = app_mod.overview_hero(dock, [])
    assert plain["qualifier"] == f"Every one is a {UNCONFIRMED}." and plain["match"] is None
    data = app_data(run_dir, title="t")
    data["hero"] = matched
    page = "".join(app_mod.route_sections(data).values())
    lede = re.search(r'<p class="muted" style="margin:0;max-width:80ch">(.*?)</p>', page, re.S).group(1)
    assert "not that this run confirmed it." in lede
    box = re.search(r"<li><b>No confirmed planet.</b>(.*?)</li>", page, re.S).group(1)
    assert "The match with Test c says the planet is already known, not that this run confirmed it." in box


def test_runs_page_names_the_cross_match_file_and_the_runs_own_error(run_dir, tmp_path):
    fn = re.search(r"function xmConfig\(x\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "(fallback; run's own: " in fn and "esc(x.run_error)" in fn
    assert "<dt>archive cross-match</dt><dd>${xmConfig(D.crossmatch_info)}</dd>" in APP_JS
    target = json.loads((run_dir / "candidates.json").read_text())[0]["target"]
    fb = tmp_path / "fb.json"
    fb.write_text(json.dumps({"status": "matched", "targets": [target], "star": None, "source": "s", "planets": []}))
    (run_dir / "crossmatch.json").write_text(json.dumps({"status": "not_run", "error": "E: verbatim"}))
    try:
        from unittest import mock

        with mock.patch.object(docket_mod, "DEFAULT_CROSSMATCH", str(fb)):
            dock = docket_mod.docket_data(run_dir, title="t", crossmatch_fallback=fb)
        assert dock["crossmatch"]["run_error"] == "E: verbatim"
    finally:
        (run_dir / "crossmatch.json").unlink()
    info = app_data(run_dir, title="t")["crossmatch_info"]
    assert info["fallback"] is False and info["status"] == "not_run" and NO_STORED_CROSSMATCH in info["error"]
    if shutil.which("node"):
        esc = re.search(r"const esc = .*\n", APP_JS).group(0)
        out = subprocess.run(["node", "-e", esc + fn + "console.log(xmConfig({file: 'docs/results/pi_men_crossmatch.json', fallback: true, run_status: 'not_run', run_error: \"ModuleNotFoundError: No module named 'astroquery'\"}))"],
                             capture_output=True, text=True, check=True).stdout.strip()
        assert out == "docs/results/pi_men_crossmatch.json (fallback; run's own: not_run, ModuleNotFoundError: No module named &#39;astroquery&#39;)"


def test_signals_button_lands_on_the_current_signal_header():
    js = re.search(r"function jumpToList\(\)\{.*?\n  \}\n", docket_mod.DOCKET_JS, re.S).group(0)
    assert "querySelector('.row[aria-selected=\"true\"]')" in js and ".querySelector('.sighead')" in js
    assert "target.style.scrollMarginTop = margin + 'px'" in js and "stickyHeight(document.body) + 8" in js
    assert "scrollIntoView(" not in js


def test_phone_dip_picker_lists_every_dip_with_its_outcome(run_dir, tmp_path):
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    cand = _route(page, "candidates")
    assert '<select id="dippick"' in cand and '<label for="dippick">' in cand
    pick = re.search(r"function renderDipPicker\(\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "(D.showcase || []).map" in pick and "c.dips.map" in pick and "w.outcome" in pick
    assert "$('#dippick').addEventListener('change', e => navTo(dipHref(e.target.value)));" in APP_JS
    assert ".dippicker select{flex:1;min-width:0;min-height:44px" in _phone_css()
    # Inside the framed Docket, a fixed "Signals" button jumps back to the list on a phone.
    assert "jumpToList" in docket_mod.DOCKET_JS and ".jumplist{display:inline-flex" in docket_mod.DOCKET_CSS


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_times_are_shown_in_utc_and_say_so():
    esc = re.search(r"const esc = .*?\n", APP_JS).group(0)
    fn = re.search(r"function when\(iso\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    script = esc + fn + "console.log(JSON.stringify(when('2026-10-17T17:24:19+00:00')));"
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True,
                                    env={"TZ": "Asia/Kolkata", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/node22/bin"}).stdout)
    text = re.sub(r"<[^>]+>", "", out)
    assert text.endswith("17:24 UTC") and 'title="2026-10-17T17:24:19+00:00"' in out


def test_no_ui_text_below_11px():
    sizes = [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)px", " ".join(re.findall(r"font(?:-size)?:[^;}]*", APP_CSS)))]
    assert sizes and min(sizes) >= 11
    assert "const fs = 11;" in docket_mod.DOCKET_JS


def test_reviewer_display_names_are_sentinels_and_probes():
    from setuhq.names import display_name, panel_phrase, reviewer_names, short_name

    kinds = {"claude-volunteer": "claude_code", "claude-skeptic": "claude_code", "volunteer-sensitive": "simulated",
             "volunteer-typical": "simulated", "volunteer-cautious": "simulated"}
    names = reviewer_names(kinds)
    assert [names[r]["name"] for r in kinds] == ["Sentinel · Volunteer", "Sentinel · Skeptic", "Probe · Sensitive",
                                                  "Probe · Typical", "Probe · Cautious"]
    assert [names[r]["short"] for r in kinds] == ["SEN Volunteer", "SEN Skeptic", "PRB Sensitive", "PRB Typical", "PRB Cautious"]
    assert all(names[r]["id"] == r for r in kinds)  # ids unchanged
    assert panel_phrase(2, 3) == "2 Sentinels and 3 Probes" and panel_phrase(0, 1) == "1 Probe"
    assert display_name("someone", "human") == short_name("someone", "human") == "someone"
    # Another provider keeps the persona name; the provider goes beside it, not into it.
    mixed = reviewer_names({"gpt-skeptic": "openai", "gemini-volunteer": "gemini", "claude-skeptic": "claude"})
    assert mixed["gpt-skeptic"]["name"] == "Sentinel · Skeptic" and mixed["gpt-skeptic"]["provider"] == "OpenAI"
    assert mixed["gemini-volunteer"]["name"] == "Sentinel · Volunteer" and mixed["gemini-volunteer"]["provider"] == "Google Gemini"
    assert mixed["claude-skeptic"]["provider"] == "Claude (Anthropic API)"
    assert names["volunteer-typical"]["provider"] is None


def test_panel_page_attribution_and_ids_unchanged_in_data(run_dir, tmp_path):
    from setuhq.names import ATTRIBUTION

    assert ATTRIBUTION == ("Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. "
                           "Probes are deterministic matched-filter detectors.")
    page = site_bundle(build_app(run_dir, tmp_path / "app", title="t"))
    assert ATTRIBUTION in _route(page, "sentinels")
    assert "superintelligence" not in page.lower()
    data = _page_data(page)
    # Ids stay as stored: the panel, calibration and agreement keep them; names are a separate map.
    assert {r["id"] for r in data["panel"]} == {"vol-a", "vol-b"} == set(data["reviewer_names"])
    assert data["reviewer_names"]["vol-a"]["name"] == "Probe · Vol A"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert {r["id"] for r in manifest["reviewers"]} == {"vol-a", "vol-b"}
    # The Docket shows the attribution in its provenance and names lanes by short display name.
    assert _page_data_docket(data["docket_html"])["attribution"] == ATTRIBUTION
    js = docket_mod.DOCKET_JS
    assert "${esc(D.attribution)}${D.panel_note ? ` ${esc(D.panel_note)}.` : ''}<br>run" in js and "SHORT_NAME(n)" in js and "NAME(n)} (id ${n})" in js
    # The reviewer cards and the calibration rows show the name with the id beside it.
    assert "nameWithId(p.id)" in APP_JS and '<span class="sub mono" title="reviewer id">${esc(r.id)}</span>' in APP_JS
    for word in ("Claude reviewers were", "simulated detector, not", "SIM = simulated"):
        assert word not in APP_JS + js, word


def _page_data_docket(html_text: str) -> dict:
    raw = re.search(r'<script id="data" type="application/json">(.*?)</script>', html_text, re.S).group(1)
    return json.loads(raw.replace("<\\/", "</"))


def test_signals_button_targets_the_current_signal_in_the_list():
    js = re.search(r"function jumpToList\(\)\{.*?\n  \}\n", docket_mod.DOCKET_JS, re.S).group(0)
    assert "l.querySelector('.sig.cur .sighead')" in js and "data-collapsed') === 'true' && t) t.click()" in js
    assert "document.querySelector('.dipbtn.cur')" in js and "room = vh - 52" in js
    # First in the document, so it is the first "Signals" button a reader or a test finds.
    assert "document.body.insertBefore(b, document.body.firstChild)" in docket_mod.DOCKET_JS
    # On a phone the list is an accordion, so the list and the current dip's buttons fit one screen.
    assert "#rows .sig:not(.cur) .row{display:none}" in docket_mod.DOCKET_CSS


def test_the_sentinels_page_states_the_benchmark_as_measured_not_discovered(tmp_path):
    from setuhq.app import _benchmark_card, _load_benchmark

    assert "has not been run" in _benchmark_card(None)
    assert _load_benchmark(tmp_path / "missing.json") is None
    rate = {"k": 3, "n": 4, "rate": 0.75, "lo": 0.3, "hi": 0.95}
    ctl = {"vetted_false_alarms": 2, "star_sectors": 40, "per_1000_star_sectors": 50.0}
    b = {"sample": {"counts": {"positive": 300, "fp": 300, "fa": 62}, "fetched_at": "2026-10-19T11:00:16Z", "seed": 20261019},
         "panel": "the Probes <test>", "summary": {"held_out": {"completeness": rate, "fp_seen": rate, "fp_flagged_of_seen": rate,
                                                                "controls": {"inverted": ctl, "scrambled": ctl}}},
         "sentinels": {"n_stars": 40, "personas": {"Sentinel": {"cp_kp_marked": rate}}}}
    path = tmp_path / "b.json"
    path.write_text(json.dumps(dict(b, per_star=[{"toi": "1"}])))
    loaded = _load_benchmark(path)
    assert "per_star" not in loaded
    card = _benchmark_card(loaded)
    assert "Measured on a stated benchmark, not discoveries." in card and "discovered" not in card.lower()
    assert "75% <span class='muted'>(3/4; 95% CI 30–95%)" in card and "50 per 1,000 star-sectors" in card
    assert "&lt;test&gt;" in card and "subsample of 40 stars" in card and "fetched 2026-10-19" in card
    assert "Headline: planets recovered on searchable stars" in card and "consistent with noise" not in card
    held = b["summary"]["held_out"]
    held.update(completeness_all_stars=rate, not_searchable={"positive": 2, "fp": 1, "fa": 0},
                feed={v: {"new_signals_per_1000": 25.0, "new_signals": 1, "star_sectors": 40} for v in ("real", "inverted", "scrambled")})
    bad = _benchmark_card(dict(b, feed_implication={"bad": True, "expected_false_per_100_targets": 5.0, "live_new_signals_per_100_targets": 15.8}))
    assert "3 stars <span class='muted'>(2 CP/KP, 1 FP, 0 FA)" in bad and "skewed toward FP" not in bad and "at the feed&#x27;s level" in bad
    assert "The live feed&#x27;s new signals are consistent with noise." in bad
    assert bad.index("consistent with noise") < bad.index("Measured on a stated benchmark") < bad.index("<table class=\"bench\">") and "more likely noise than a signal" in bad and "15.8 per 100" in bad
    clipped = _benchmark_card(dict(b, unaffected_held_out={"completeness": rate},
                                   clipping={"ratio": 8.0, "held_out": {"affected": {"positive": 27, "fp": 11, "fa": 0}, "cp_kp_misses_explained": 3}}))
    assert "Known bug in the code that measured this." in clipped and "27 CP/KP, 11 FP and 0 FA held-out stars are exposed" in clipped
    assert "stars exposed to the clipping bug excluded" in clipped
    rule = {"validation": {"evaluated_at": "2026-10-20T00:00:00Z", "rule": {"fap_cut": 0.001, "fap_trials": 2000},
                           "held_out": {"expected_false_per_100_targets": 6.1, "expected_false_ci_per_100_targets": [4.0, 9.4],
                                        "real_new_per_100_targets": 0.3, "completeness": {"rate": 0.17}},
                           "held_out_old_rule": {"expected_false_per_100_targets": 23.0, "expected_false_ci_per_100_targets": [18.6, 28.0],
                                                 "completeness": {"rate": 0.39}}},
            "live": {"new_signals": 0, "old_new_signals": 3}}
    upd = _benchmark_card(dict(b, feed_rule=rule))
    assert "pre-registered and tested once" in upd and "still dominated by false alarms" in upd and "6.1 false signals per 100 targets" in upd
    assert "a lead for human or follow-up review, not a candidate of any confirmed status" in upd and "0 of the live feed&#x27;s 3" in upd
    assert "reliable" not in upd.lower() and " clean" not in upd.lower()
    assert "table.bench th,table.bench td{white-space:normal" in APP_CSS  # labels wrap; nothing hides off to the side
    # The re-run on the fixed code: the first run beside it, the bug stated as fixed, the feed rule measured again.
    first = {"k": 2, "n": 4, "rate": 0.5, "lo": 0.15, "hi": 0.85}
    path.write_text(json.dumps(dict(b, edition="clipfix", per_star=[], clipping={"ratio": 8.0, "held_out": {"affected": {"positive": 27, "fp": 11, "fa": 0}}},
                                    against_first_run={"rows": [{"first": first}], "clipping": {"n": 27, "first_recovered": 21, "now_recovered": 25}},
                                    feed_rule=dict(rule, edition="clipfix", live={"targets": 19, "new_signals": 0}))))
    fixed = _benchmark_card(_load_benchmark(path))
    assert "Planets recovered in the first run, on the pre-fix code" in fixed and "50% <span class='muted'>(2/4" in fixed
    assert "The clipping bug is fixed in the code that measured this." in fixed and "25 of the 27 exposed CP/KP are recovered now, against 21" in fixed
    assert "Known bug" not in fixed and "measured again on this code" in fixed and "the live feed&#x27;s 19 targets admit 0 new signals" in fixed
    assert "benchmark_real_tois_clipfix.md" in fixed

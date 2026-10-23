# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The home page (setuhq.home) and its own components: the hero (V01), the gallery (V03), the temperature strip
(V09), the counters (V10) and the stories.json sections. Built from the stored runs, showcase.json and the
catalogue; every number on the page must come from them."""

from __future__ import annotations

import copy
import html as html_mod
import json
import re
from pathlib import Path

import pytest

from setuhq import viz
from setuhq.looks import teff_rgb
from setuhq.names import ATTRIBUTION, PROBES_ONLY, dip_count

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "docs/results/showcase.json"
LEAD = "runs/tess-pi-men-s1"
EXTRA = ["runs/tess-wasp-126-s1", "runs/tess-toi-270-s5", "runs/tess-hd-15337-s4", "runs/tess-toi-236-s2"]


def _build_data(showcase_path=SHOWCASE):
    import setuhq.docket as dm
    from setuhq.app import app_data

    keep = dm.query_archive
    dm.query_archive = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test"))
    try:
        return app_data(ROOT / LEAD, title="SetuHQ", catalog_path=ROOT / "docs/discoveries/catalog.json",
                        extra_runs=[ROOT / r for r in EXTRA], showcase_path=showcase_path)
    finally:
        dm.query_archive = keep


@pytest.fixture(scope="module")
def data():
    return _build_data()


def _overview(d) -> str:
    from setuhq.home import _overview

    return _overview(d)


def _text(page: str) -> str:
    page = re.sub(r"<(script|style|template)\b.*?</\1>", " ", page, flags=re.S)
    return html_mod.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))


# ---------------------------------------------------------------- band order


def test_the_bands_come_in_the_order_of_the_design(data, monkeypatch):
    from setuhq import home

    # The bands other phases draw are stubs until they merge; give each a marker so the order can be checked.
    for name in ("lineup", "fold", "panelring", "skyyears", "timeline"):
        mod = __import__(f"setuhq.viz.{name}", fromlist=["html"])
        monkeypatch.setattr(mod, "html", lambda d, _n=name, **o: (viz.require_source(d), f'<div class="stub-{_n}"></div>')[1])
    page = _overview(data)
    ids = re.findall(r'id="band-(\w+)"', page)
    assert page.lstrip().startswith('<header class="launch">') and '<h1 id="h-overview"' in page.split("</header>")[0]
    assert ids == [b for b in home.BANDS if b not in ("hero", "gallery")]
    assert page.index('class="herostage"') < page.index('id="examples"') < page.index('id="band-tempstrip"')
    assert page.index('stub-skyyears') < page.index('stub-timeline') < page.index('id="band-counters"')
    # The panel band carries the attribution word for word, and the lead run is not Probes-only.
    panel = re.search(r'<section class="band" id="band-panel".*?</section>', page, re.S).group(0)
    assert html_mod.escape(ATTRIBUTION) in panel and PROBES_ONLY not in panel
    # What the home page no longer shows.
    assert 'class="planetfig"' not in page and "gxteaser" not in page


def test_a_band_whose_module_is_a_stub_is_left_out(data):
    page = _overview(data)
    for band, name in (("lineup", "lineup"), ("fold", "fold"), ("sky", "skyyears")):
        mod = __import__(f"setuhq.viz.{name}", fromlist=["html"])
        if mod.html({"source": "x", "app": data}, where="home") == "" and (name != "skyyears" or viz.timeline.html({"source": "x", "app": data}) == ""):
            assert f'id="band-{band}"' not in page
    # The panel band is the lead dip's own ring; with no lead dip there is no band.
    nolead = {**data, "story": {**data["story"], "lead_dip": None}}
    assert 'id="band-panel"' not in _overview(nolead)


# ---------------------------------------------------------------- who reviews (V06): the lead dip's stored panel


def _ring_numbers(fragment: str) -> dict:
    t = _text(fragment)
    m = re.search(r"(\d+) of (\d+) marked it · panel score ([\d.]+|not stored), as stored", t)
    body = re.search(r"<tbody>(.*?)</tbody>", fragment, re.S)
    return {"marked": int(m.group(1)), "of": int(m.group(2)), "score": m.group(3),
            "rows": len(re.findall(r"<tr>", body.group(1))) if body else 0, "label": "Real data, cited" in t}


def test_the_home_ring_is_the_lead_dips_stored_panel(data):
    from setuhq.viz import panelring

    lead = data["story"]["lead_dip"]
    band = re.search(r'<section class="band" id="band-panel".*?</section>', _overview(data), re.S).group(0)
    dip_page = panelring.html(panelring.for_dip(data, lead))  # exactly what the dip's own page draws
    home, page = _ring_numbers(band), _ring_numbers(dip_page)
    d = next(x for x in data["story"]["dips"] if x["id"] == lead)
    stored = sum(1 for ln in d["lanes"] if ln["counted"])
    # The home page sends the ring in its smallest form (the script draws it in full from the same record).
    assert f'data-pr-dip="{lead}"' in band and home["rows"] == 0
    assert {k: home[k] for k in ("marked", "of", "score", "label")} == {k: page[k] for k in ("marked", "of", "score", "label")}
    assert home["of"] == page["rows"] == len(data["story"]["reviewers"]) > 0
    assert home["marked"] == stored > 0 and home["score"] != "not stored"
    assert home["score"] == panelring._f2(d["score"]) and home["label"]
    assert "0 of 0" not in _text(band) and "score not stored" not in _text(band)


# ---------------------------------------------------------------- counters (V10)


def test_counters_are_read_from_the_stored_data(data):
    from setuhq.home import _counters_band, counters
    from setuhq.methods import CHAPTERS

    cs = {c["key"]: c for c in counters(data)}
    assert cs["catalogue"]["value"] == data["catalogue"]["counts"]["rows"]
    assert cs["benchmark"]["value"] == sum(data["benchmark"]["sample"]["counts"].values())
    assert cs["chapters"]["value"] == len(CHAPTERS)
    band = _counters_band(data)
    assert "(52–67%)" in band and "90 of 150" in band  # a rate is never shown without its interval
    for c in cs.values():
        assert f'data-odo="{c["text"]}"' in band and html_mod.escape(c["source"]) in band
    # A changed fixture changes the numbers.
    d = copy.deepcopy({k: data[k] for k in ("catalogue", "benchmark")})
    d["catalogue"]["counts"]["rows"] = 1234
    d["benchmark"]["sample"]["counts"] = {"positive": 10, "fp": 5}
    d["benchmark"]["summary"]["held_out"]["completeness"].update(k=3, n=10, lo=0.1078, hi=0.6032)
    band = _counters_band(d)
    assert 'data-odo="1,234"' in band and 'data-odo="15"' in band and 'data-odo="30%"' in band and "3 of 10 (11–60%)" in band
    # Without an interval the completeness counter is left out, never shown bare.
    del d["benchmark"]["summary"]["held_out"]["completeness"]["lo"]
    assert "completeness" not in {c["key"] for c in counters(d)}


# ---------------------------------------------------------------- the gallery (V03)


def test_the_gallery_has_the_showcase_runs_in_order_with_their_counts_and_labels(data):
    from setuhq.viz import gallery

    runs = [r["run"] for r in json.loads(SHOWCASE.read_text())["runs"]]
    page = _overview(data)
    sec = re.search(r'<section class="examples".*?</section>', page, re.S).group(0)
    cards = re.findall(r'<article class="excard".*?</article>', sec, re.S)
    assert len(cards) == len(runs) == 5
    by_run = {c["run"]: c for c in data["showcase"]}
    for art, run in zip(cards, runs):
        c = by_run[run]
        assert html_mod.escape(c["star"]) in art
        assert c["count"] == dip_count([d["outcome"] for d in c["dips"]]) and html_mod.escape(c["count"]) in art
        assert (PROBES_ONLY in art) == (c["panel"] == "probes_only")
        assert "Model from stored values" in art and 'class="stage gstage"' in art
    # The caveats stay visible wherever those runs appear.
    meta = {r["run"]: r for r in json.loads(SHOWCASE.read_text())["runs"]}
    for run in ("tess-hd-15337-s4", "tess-toi-270-s5"):
        assert meta[run]["caveat"] and html_mod.escape(meta[run]["caveat"]) in cards[runs.index(run)]
    # TOI-236, the known false positive: an unidentified occulter, no planet silhouette.
    st = gallery.from_app(data)["stages"]
    assert [b["kind"] for b in st["tess-toi-236-s2"]["bodies"]] == ["occ"]
    toi236 = cards[runs.index("tess-toi-236-s2")]
    assert "occulter not identified" in toi236 and "secondary eclipse at SNR 10.9" in toi236.replace("Secondary", "secondary")
    assert "all 6 dips rejected by vetting" in toi236 and 'fill="#030406"' not in toi236
    # TOI-270 b, which the run did not recover, is a dashed outline; c and d are the run's own fits.
    t270 = {b["name"]: b for b in st["tess-toi-270-s5"]["bodies"]}
    assert t270["TOI-270 b"]["kind"] == "missed" and t270["TOI-270 c"]["kind"] == t270["TOI-270 d"]["kind"] == "sil"
    assert t270["TOI-270 c"]["k"] == 0.06592 and "not recovered by this run" in cards[runs.index("tess-toi-270-s5")]
    # pi Men's silhouette is the joint fit's Rp/R★.
    v = json.loads((ROOT / "docs/results/pi_men_validation.json").read_text())["joint_fit"]["k"]
    assert st["tess-pi-men-s1"]["bodies"][0]["k"] == round(v, 5)
    # Every star disc is at the run's stored Teff.
    for run, s in st.items():
        assert s["teff"] == round(data["run_ctx"][run]["star_params"]["teff"], 1)


def test_no_candidate_gets_planet_art_on_the_home_page(data):
    page = _overview(data)
    # Planet art is only the hero's known catalogue planet; every gallery stage is a model from stored values.
    assert page.count('data-render="planet"') == 0
    assert len(re.findall(r'data-render="transit"', page)) == 1


# ---------------------------------------------------------------- the hero (V01)


def test_the_hero_states_the_featured_star_its_depth_and_its_source(data):
    from setuhq.methods import ld_coeffs, transit_flux
    from setuhq.viz import hero

    h = hero.from_app(data)
    m = h["lead"]
    assert m["run"] == "tess-pi-men-s1" and m["planet"] == "pi Men c"
    sp = data["run_ctx"]["tess-pi-men-s1"]["star_params"]
    assert m["teff"] == round(sp["teff"], 1) and m["rstar"] == round(sp["radius"], 4)
    depth = (1 - transit_flux(m["b"], m["k"], *ld_coeffs(sp["teff"]))) * 1e6
    assert abs(m["depth_ppm"] - depth) < 0.1
    assert f"{round(sp['teff']):,} K" in m["alt"] and f"depth {depth:,.0f} ppm" in m["alt"] and "artist's impression" in m["alt"]
    page = _overview(data)
    fig = re.search(r'<figure class="stage rfig herofig".*?</figure>', page, re.S).group(0)
    assert html_mod.escape(m["alt"]) in fig and "exoplanet.eu" in fig and "TESS Input Catalog v8.2" in fig
    assert 'data-priority="first"' in fig and "data:image/svg+xml," in fig and '"animate":false' in fig
    assert 'href="/docs/pictures/"' in fig and "data-hero-pause" in page
    # The rotation: every eligible run in showcase.json order, never the false positive.
    rot = json.loads(html_mod.unescape(re.search(r"data-rotate='([^']*)'", page).group(1)))
    assert [r["run"] for r in rot] == ["tess-wasp-126-s1", "tess-toi-270-s5", "tess-hd-15337-s4", "tess-pi-men-s1"]
    planets = [x["planet"] for x in hero.runs(data)]
    assert planets == ["WASP-126 b", "TOI-270 c", "HD 15337 b", "pi Men c"]


def test_the_hero_follows_the_stored_star(data):
    from setuhq.viz import hero

    d = copy.deepcopy({k: data[k] for k in ("run_ctx", "catalogue", "showcase", "run", "showcase_source")})
    d["run_ctx"]["tess-pi-men-s1"]["star_params"]["teff"] = 4000.0
    m = hero.from_app(d)["lead"]
    assert "(4,000 K," in m["alt"] and m["teff"] == 4000.0
    d["run_ctx"]["tess-pi-men-s1"]["star_params"]["radius"] = None
    assert hero.from_app(d)["lead"]["run"] != "tess-pi-men-s1"  # no stored radius: that run is not featured


def test_t14_matches_a_hand_calculation():
    from setuhq.viz.hero import t14_hours

    import math
    assert t14_hours(10.0, 20.0, 0.1, 0.0) == pytest.approx(10 / math.pi * math.asin(1.1 / 20) * 24)
    assert t14_hours(10.0, 0.5, 0.1, 0.0) is None


# ---------------------------------------------------------------- the temperature strip (V09)


def test_the_strip_has_31_blackbody_stops_and_the_stored_teffs(data):
    from setuhq.viz import tempstrip

    g = tempstrip.gradient()
    assert g.count("%") == 31
    r, gg, b = teff_rgb(5750)
    assert f"#{r:02x}{gg:02x}{b:02x} 43.3333%" in g
    page = _overview(data)
    band = re.search(r'<section class="band" id="band-tempstrip".*?</section>', page, re.S).group(0)
    teffs = sorted(int(x) for x in re.findall(r'<li data-teff="(\d+)"', band))
    want = sorted([round(c["star_params"]["teff"]) for c in data["run_ctx"].values()] + [5772])
    assert teffs == want
    assert "TESS Input Catalog v8.2" in band and 'role="img"' in band


def test_the_strip_filter_mode_has_two_range_inputs():
    from setuhq.viz import tempstrip

    out = tempstrip.html({"source": "x", "markers": [{"name": "A", "teff": 4000}]}, filter=True, lo=3000, hi=7000)
    assert 'data-filter="1"' in out and out.count('type="range"') == 2 and 'value="3000"' in out and 'value="7000"' in out
    assert "setu:teff-range" in tempstrip.JS
    assert tempstrip.rows([10, 12, 30, 31, 32]) == [0, 1, 0, 1, 2]


@pytest.mark.parametrize("name", ["hero", "gallery", "tempstrip"])
def test_each_component_needs_a_source(name):
    mod = __import__(f"setuhq.viz.{name}", fromlist=["html"])
    with pytest.raises(ValueError):
        mod.html({})
    with pytest.raises(ValueError):
        mod.html({"source": ""})


# ---------------------------------------------------------------- stories.json, honesty, a changed showcase.json


def test_stories_json_holds_the_gallery_and_the_counters(data):
    body = viz.collect(data)["stories"]
    assert {"gallery", "counters"} <= set(body)
    assert [c["run"] for c in body["gallery"]["cards"]] == [c["run"] for c in data["showcase"]]
    assert len(json.dumps(body, separators=(",", ":"), ensure_ascii=False)) <= viz.DATA_BUDGET["stories"]


def test_no_claim_of_discovery_confirmation_or_habitability(data):
    from test_honesty_lint import claims

    page = _overview(data)
    text = _text(page)
    assert claims(text) == []
    assert not re.search(r"habitable", page, re.I) and "SuperIntelligence" not in page
    for fn in ("hero", "gallery", "tempstrip"):
        mod = __import__(f"setuhq.viz.{fn}", fromlist=["CSS"])
        assert "habitable" not in (mod.CSS + mod.JS).lower()


def test_a_changed_showcase_file_changes_the_page(tmp_path):
    sc = json.loads(SHOWCASE.read_text())
    sc["runs"].reverse()
    sc["runs"][0]["kind"] = "A test kind of example"
    for r in sc["runs"]:
        if r["run"] == "tess-toi-270-s5":
            r["planets"][1]["setuhq"]["rp_rs"] = 0.0777
    p = tmp_path / "showcase.json"
    p.write_text(json.dumps(sc))
    d = _build_data(p)
    page = _overview(d)
    sec = re.search(r'<section class="examples".*?</section>', page, re.S).group(0)
    stars = re.findall(r'<h3 id="ex-[^"]+">(?:<a [^>]+>)?([^<]+)', sec)
    assert stars == [html_mod.escape(r["star"]) for r in sc["runs"]]
    assert "A test kind of example" in sec and "Rp/R★ 0.0777 (run fit)" in sec


def test_the_built_home_page_stays_within_its_budget(tmp_path):
    import setuhq.docket as dm
    from setuhq.site import build_site, check_asset_budget

    keep = dm.query_archive
    dm.query_archive = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test"))
    try:
        out = tmp_path / "site"
        build_site(ROOT / LEAD, out, title="SetuHQ", catalog_path=ROOT / "docs/discoveries/catalog.json",
                   extra_runs=[ROOT / r for r in EXTRA], extras=False)
    finally:
        dm.query_archive = keep
    home = (out / "index.html").read_text()
    assert len(home) <= 90_000
    assert check_asset_budget(out) == []
    assert list((out / "assets" / "data").glob("stories-*.json"))
    css = next(out.glob("assets/site-*.css")).read_text()
    from setuhq.design import motion_problems

    assert motion_problems(css, "site css") == []

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Phase 2 of the redesign: the sky by year (V04), the timeline (V12), the line-up (V07), the orbits (V08), and the
planet and star pages' pictures, pre-rendered and deploy-time (docs/SITE.md, "The visual system")."""

from __future__ import annotations

import json
import math
import re

import pytest

from setuhq import renderer, stubs
from setuhq.catalogue import load_catalogue, planet_extras, portrait, star_extras
from setuhq.design import METHOD
from setuhq.looks import RJ_IN_RE, find_planet, kepler_a, look, row, seed
from setuhq.methods import CLARET_TESS
from setuhq.viz import lineup, orbits, skyyears, timeline

SRC = "The Extrasolar Planets Encyclopaedia (exoplanet.eu), fetched 2026-10-18"
SHOWCASE = [{"star": "pi Men", "planet": "pi Men c", "kind": "Reference check"},
            {"star": "WASP-126", "planet": "WASP-126 b", "kind": "Hot Jupiter"},
            {"star": "TOI-270", "planet": "TOI-270 c", "kind": "Multi-planet system"},
            {"star": "HD 15337", "planet": "HD 15337 b", "kind": "Small planets near the limit"},
            {"star": "TOI-236", "planet": None, "kind": "Known false positive"}]


@pytest.fixture(scope="module")
def cat():
    c = load_catalogue()
    assert c is not None
    return c


@pytest.fixture(scope="module")
def app(cat):
    return {"catalogue": cat, "showcase": SHOWCASE, "viz_files": {"sky": "/assets/data/sky-test.json"}}


def _rows(cat, star):
    P = cat["planets"]
    return [{"name": P["name"][i], "slug": P["slug"][i], "k": P["k"][i], **row(cat, i)} for i, s in enumerate(P["star"]) if s == star]


# ---------------------------------------------------------------- every component names its source
@pytest.mark.parametrize("mod", [skyyears, timeline, lineup, orbits])
def test_a_component_without_its_source_raises(mod):
    with pytest.raises(ValueError):
        mod.html({"app": {}})


# ---------------------------------------------------------------- V04 sky by year
def test_sky_file_covers_every_record_with_a_position(cat, app):
    d = skyyears.data(app)
    P = cat["planets"]
    with_pos = [i for i in range(len(P["name"])) if P["ra"][i] is not None and P["dec"][i] is not None]
    assert len(d["p"]) == len(with_pos) == cat["counts"]["rows"] == 8376
    assert d["m"] == list(METHOD)  # the method index is design.METHOD's order
    for (ra, dec, m, y), i in zip(d["p"], with_pos):
        assert ra == round(P["ra"][i] * 10) and dec == round(P["dec"][i] * 10) and d["m"][m] == P["method"][i] and y == P["year"][i]
    assert d["source"].startswith("The Extrasolar Planets Encyclopaedia") and d["fetched_at"] == cat["fetched_at"]
    assert len(json.dumps(d, separators=(",", ":"), ensure_ascii=False)) <= 160_000


def test_sky_map_without_javascript(app):
    h = skyyears.html({"source": SRC, "app": app}, where="explore")
    assert SRC in h and "Real data, cited" in h and 'data-src="/assets/data/sky-test.json"' in h
    svg = re.search(r'<svg class="skybase".*?</svg>', h, re.S).group(0)
    assert svg.count("h0") <= skyyears.STATIC_MAX and len(svg) <= 25_000
    assert re.search(r'<input type="range" data-sky="year" min="\d{4}" max="2026"[^>]*aria-valuetext="2026: 8,376 planets"', h)
    assert 'data-sky="transit"' in h and "Transits only" in h and 'aria-live="polite"' in h and "<details" in h
    assert "8,376 planets shown · transit 4,958" in h
    assert "SetuHQ did not discover these planets" in h


# ---------------------------------------------------------------- V12 timeline
def test_timeline_counts_equal_a_direct_count(cat):
    t = timeline.by_year(cat)
    P = cat["planets"]
    for y, c in zip(t["years"], t["counts"]):
        for k, m in enumerate(t["methods"]):
            assert c[k] == sum(1 for yy, mm in zip(P["year"], P["method"]) if yy == y and mm == m)
    assert sum(map(sum, t["counts"])) + t["no_year"] == len(P["name"])


def test_timeline_is_a_small_static_svg_with_its_table(app):
    h = timeline.html({"source": SRC, "app": app}, where="explore")
    svg = re.search(r'<svg class="tlsvg".*?</svg>', h, re.S).group(0)
    assert len(svg) <= 12_000 and 'role="img"' in svg
    assert SRC in h and "Real data, cited" in h and "<table" in h and 'data-viz="timeline"' in h
    words = re.search(r'data-counts="([^"]*)"', h).group(1).split(" ")
    t = timeline.by_year(app["catalogue"])
    assert [[int(x) for x in w.split(".")] for w in words] == [c[:len(w.split("."))] for c, w in zip(t["counts"], words)]
    assert sum(int(x) for w in words for x in w.split(".")) == sum(map(sum, t["counts"]))


# ---------------------------------------------------------------- V07 line-up
def test_lineup_radii_are_the_catalogues(cat, app):
    es = lineup.showcase_entries(app)
    P = cat["planets"]
    for en in es:
        i = P["name"].index(en["catalogue_name"])
        assert en["rp_re"] == round(P["radius"][i] * RJ_IN_RE, 3)
    names = [e["name"] for e in es]
    # HD 15337's planets are exoplanet.eu's TOI-402 Ab and Ac, found by the alias-aware lookup and shown by SetuHQ's names.
    assert "HD 15337 b" in names and "HD 15337 c" in names and find_planet(cat, "HD 15337 b") == P["name"].index("TOI-402 Ab")
    assert "pi Men c" in names and "WASP-126 b" in names and {"TOI-270 b", "TOI-270 c", "TOI-270 d"} <= set(names)
    assert not any(n.startswith("TOI-236") for n in names)  # a known false positive has no planet to draw
    assert [e["rp_re"] for e in es] == sorted(e["rp_re"] for e in es)
    pm = next(e for e in es if e["name"] == "pi Men c")
    assert abs(pm["rp_re"] - 1.874) < 0.001 and pm["look"] == "envelope-hot"


def test_lineup_html_draws_earth_only_as_the_reference(app):
    h = lineup.html({"source": SRC, "app": app})
    assert "Artist's impression" in h and 'href="/docs/pictures/"' in h and SRC in h
    for ref in ("Earth", "Neptune", "Jupiter"):
        assert f"<b>{ref}</b>" in h
    # Earth (the only look with oceans) is drawn once, as the reference; every other picture is an exoplanet look.
    assert h.count("/ref-earth-") == 1 and set(re.findall(r"/(ref-[a-z]+)-", h)) == {"ref-earth", "ref-neptune", "ref-jupiter"}
    assert "habitable" not in h.lower()


# ---------------------------------------------------------------- V08 orbits
def test_orbits_a_from_the_catalogue_or_keplers_law_and_depth_k_squared(cat):
    rows = _rows(cat, "TOI-270")
    ps = orbits.system(rows)
    assert [p["name"] for p in ps] == ["TOI-270 b", "TOI-270 c", "TOI-270 d"]
    for p, r in zip(ps, sorted(rows, key=lambda r: r["period"])):
        assert p["a"] == r["a"] and p["a_src"] == "catalogue"
        k = r["radius"] * 71492 / 695700 / r["srad"]
        assert math.isclose(p["depth_ppm"], k * k * 1e6)
    # Without a stored a, Kepler's third law from the period and the star's mass.
    no_a = [dict(r, a=None) for r in rows]
    for p, r in zip(orbits.system(no_a), sorted(rows, key=lambda r: r["period"])):
        assert p["a_src"] == "Kepler's third law" and math.isclose(p["a"], kepler_a(r["smass"], r["period"]))
    # The catalogue's k is the RV semi-amplitude (m/s), never read as Rp/R★.
    assert orbits.system([dict(r, k=0.5) for r in rows])[0]["depth_ppm"] == ps[0]["depth_ppm"]


def test_orbits_html_has_its_label_table_and_source(cat):
    h = orbits.html({"source": SRC, "star": "TOI-270", "teff": 3506, "planets": _rows(cat, "TOI-270"), "inset": True, "uid": "tx-toi-270"})
    assert 'data-viz="orbits"' in h and 'id="tx-toi-270"' in h and "Model from stored values" in h and SRC in h
    assert "Depth k² (ppm)" in h and "3,161" in h and "phases illustrative" in h
    assert orbits.html({"source": SRC, "star": "x", "planets": _rows(cat, "TOI-270")[:1]}) == ""


# ---------------------------------------------------------------- planet and star pages
def test_pre_rendered_planet_page_pictures(cat):
    P = cat["planets"]
    i = P["name"].index("pi Men c")
    h = planet_extras(cat, i)
    assert 'data-render="planet"' in h and "envelope-hot-512.webp" in h and "Artist&#x27;s impression of pi Men c" in h
    assert 'data-render="star"' in h and "6,037 K" in h and 'class="lineup"' in h and "luitem focus" in h
    hd = portrait(cat, find_planet(cat, "HD 15337 b"))
    assert "Teq 989 K" in hd and "stored value (3,109 K) differs" in hd and "envelope-warm" in hd
    assert star_extras(cat, "TOI-270", [j for j, s in enumerate(P["star"]) if s == "TOI-270"]).count('data-viz="orbits"') == 1


def _edge(cat):
    """A mass-only planet, one with neither radius nor mass, and one with a radius but no irradiation."""
    P = cat["planets"]
    n = len(P["name"])
    mass_only = next(i for i in range(n) if not P["radius"][i] and (P["mass"][i] or P["msini"][i]))
    nothing = next(i for i in range(n) if not P["radius"][i] and not P["mass"][i] and not P["msini"][i])
    neutral = next(i for i in range(n) if P["radius"][i] and look(row(cat, i))["neutral"])
    return mass_only, nothing, neutral


def test_stub_planet_pages_carry_the_portrait(cat):
    tpl = "<html>{{TITLE}}{{DESC}}{{PATH}}{{H1}}{{FACTS}}{{NOSCRIPT}}{{PORTRAIT}}</html>"
    base = "/assets/render/abcd1234/"
    P = cat["planets"]
    for name in ("pi Men c", "WASP-126 b", "TOI-270 c", "HD 15337 b", "HD 15337 c"):
        i = find_planet(cat, name)
        lk = look(row(cat, i))
        _, page = stubs.planet_page(tpl, cat, i, base)
        assert f'src="{base}{lk["name"]}-512.webp"' in page and 'data-render="planet"' in page
        assert re.search(r'alt="Artist&#x27;s impression: [a-z]+, [a-z]+, \d+\.\d\d Earth radii, Teq [\d,]+ K\."', page)
        assert 'href="/docs/pictures/">Artist\'s impression</a>' in page
        params = json.loads(re.search(r"data-params='([^']*)'", page).group(1))
        assert params["look"] == lk["name"] and params["seed"] == seed(P["slug"][i])
    mass_only, nothing, neutral = _edge(cat)
    _, page = stubs.planet_page(tpl, cat, mass_only, base)
    assert "radius not measured" in page
    _, page = stubs.planet_page(tpl, cat, nothing, base)
    assert "No radius or mass stored, so no planet is drawn." in page and "data-render" not in page
    _, page = stubs.planet_page(tpl, cat, neutral, base)
    assert '"neutral":true' in page and "irradiation not computable" in page
    assert "habitable" not in page.lower()


def test_stub_star_disc_is_the_renderers(cat):
    assert [tuple(r) for r in stubs.CLARET_TESS] == [tuple(r) for r in CLARET_TESS]
    for t in (2800, 3386, 5772, 6421, 9000, 12000):
        assert stubs.star_svg(t, 48, uid="s", label="x") == renderer.star_svg(t, 48, uid="s", label="x")
    assert len(stubs.star_svg(3386, 48, uid="s")) <= 700 + 100


def test_planet_extras_say_why_there_is_no_planet(cat):
    _, nothing, _ = _edge(cat)
    h = planet_extras(cat, nothing)
    assert "No radius or mass stored, so no planet is drawn." in h and 'data-render="planet"' not in h and 'class="lineup"' not in h

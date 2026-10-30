# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The redesign's integration pass: every visual component draws (no module is left a stub), the home page claims
only what its examples span, the hero's loop and a portrait's spin run through the renderer's scheduler, the dead
Galaxy teaser is gone, a catalogue fetch error reads as a plain sentence, and the panel ring is drawn at a readable
size."""

from __future__ import annotations

import html as html_mod
import re

import pytest

from setuhq import viz
from setuhq.viz import fold, gallery, hero, lineup, orbits, panelring, skyyears, tempstrip, timeline

from test_home import _build_data, _overview, _text  # noqa: F401  (the home page's data, built once)


@pytest.fixture(scope="module")
def data():
    return _build_data()


def test_every_component_draws_from_the_stored_data(data):
    src = {"source": "test"}
    drawn = {
        "hero": hero.html(hero.from_app(data)),
        "gallery": gallery.html(gallery.from_app(data)),
        "tempstrip": tempstrip.html({**src, "markers": [{"name": "pi Men", "teff": 5992.1}]}),
        "skyyears": skyyears.html({**src, "app": data}, where="t"),
        "timeline": timeline.html({**src, "app": data}),
        "lineup": lineup.html({**src, "app": data}),
        "fold": fold.html(src, where="t"),
        "panelring": panelring.html({**panelring.for_dip(data, data["story"]["lead_dip"]), "uid": "t"}),
        "orbits": orbits.html({**src, "planets": [r for r in _toi270(data)], "star": "TOI-270"}),
    }
    assert set(drawn) == set(viz.ORDER)
    for name, h in drawn.items():
        assert h and ('data-viz="' in h or 'class="stage' in h), name  # a figure drawn, not ""


def _toi270(data):
    from setuhq.looks import row

    cat = data["catalogue"]
    P = cat["planets"]
    return [{"name": P["name"][i], "slug": P["slug"][i], "k": P["k"][i], **row(cat, i)} for i, s in enumerate(P["star"]) if s == "TOI-270"]


def test_the_home_page_claims_only_the_stars_it_has(data):
    page = _overview(data)
    head = re.search(r'<section class="band" id="band-tempstrip".*?</h2>', page, re.S).group(0)
    t = _text(head)
    assert "Five example stars: 3,532\u00a0K to 6,422\u00a0K, one pipeline" in html_mod.unescape(head)  # the unit stays with its number
    assert "Any star" not in t and "Every kind of star" not in t and "every kind" not in t.lower()


def test_the_home_line_up_has_every_showcase_planet_with_a_radius(data):
    page = _overview(data)
    band = re.search(r'<section class="band" id="band-lineup".*?</section>', page, re.S).group(0)
    names = re.findall(r"<b>(?:<a [^>]*>)?([^<]+)", band)
    assert {"HD 15337 b", "HD 15337 c", "pi Men c", "WASP-126 b", "TOI-270 b", "TOI-270 c", "TOI-270 d"} <= set(names)
    assert not any(n.startswith("TOI-236") for n in names)


def test_the_hero_and_the_portrait_spin_run_in_the_renderers_scheduler():
    from setuhq import catalogue, renderer

    js = renderer.render_js()
    assert "function play(el, on, o)" in js and "play, playing, stats" in js
    # The hero has no loop of its own: SetuRender.play runs it, and its frames are counted there.
    assert "requestAnimationFrame" not in hero.JS and "SetuRender.play(fig, !S.paused" in hero.JS
    spin = re.search(r"function ctSpin\(root\)\{.*?\n\}\n", catalogue.CATALOGUE_JS if hasattr(catalogue, "CATALOGUE_JS") else "", re.S)
    src = spin.group(0) if spin else open(catalogue.__file__).read()
    assert "SetuRender.play(fig, S.on, {user: S.user})" in src
    assert "requestAnimationFrame" not in re.search(r"function ctSpin\(root\)\{.*?\n\}\n", src, re.S).group(0)


def test_the_galaxy_teaser_is_gone(tmp_path):
    from setuhq import app, galaxy, site

    assert not hasattr(galaxy, "TEASER_JS") and not hasattr(galaxy, "teaser_points") and not hasattr(galaxy, "teaser_html")
    assert "teaser" not in open(site.__file__).read() and "galaxy_teaser" not in open(app.__file__).read()
    assert ".gxteaser" not in galaxy.GALAXY_CSS


def test_a_fetch_error_is_a_plain_sentence_with_its_detail_folded():
    from setuhq.galaxy import source_note

    say, detail = source_note("NASA Exoplanet Archive not used: HTTP Error 400: Bad Request")
    assert "HTTP" not in say and "could not be reached" in say and "exoplanet.eu alone" in say
    assert detail.startswith('<details class="srcnote"><summary>') and "HTTP Error 400: Bad Request" in detail
    assert source_note("") == ("", "") and source_note(None) == ("", "")


def test_the_catalogue_page_shows_no_raw_error(data):
    from setuhq.catalogue import catalogue_section

    sec = catalogue_section(data.get("catalogue_meta"), "")
    visible = _text(re.sub(r"<details\b.*?</details>", " ", sec, flags=re.S))
    assert "HTTP Error" not in visible and "Bad Request" not in visible
    if (data.get("catalogue_meta") or {}).get("note"):
        assert "HTTP Error 400" in sec and '<details class="srcnote">' in sec


def test_the_panel_ring_is_drawn_at_a_readable_size():
    assert ".prfig svg{display:block;width:100%;max-width:520px;" in panelring.CSS
    # The ring's own coordinates are 360 wide; at 520 px its 10.5-unit labels are about 15 px.
    assert 10.5 * 520 / 360 < 16


def test_gallery_captions_are_short_and_the_cards_line_up(data):
    g = gallery.from_app(data)
    caps = [gallery.caption(s) for s in g["stages"].values()]
    assert all(len(c) < 200 for c in caps), [len(c) for c in caps]
    assert all(c.startswith("Star ") for c in caps)
    assert "grid-template-rows:subgrid" in gallery.CSS
    assert gallery.STAGE_NOTE in gallery.html(g)  # a keyed message: its text as written

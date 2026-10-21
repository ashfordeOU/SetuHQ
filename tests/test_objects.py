# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Round 11, chunk 1: one object model. Every planet and star mention links to its canonical page, the
pages link back, and the system view and honesty label have one renderer each."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import catalogue as C
from setuhq import methods as M
from setuhq import objects as O
from setuhq.app import APP_JS
from conftest import served, site_bundle

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_NODE = shutil.which("node") is not None
HAVE_BROWSER = HAVE_NODE and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()
CAT = C.load_catalogue()
NAMES = set(CAT["planets"]["name"])
STARS = set(CAT["stars"]["names"])


@pytest.fixture(scope="module")
def built(pi_men_app):
    return pi_men_app


def _page_data(page):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))


def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_page_slug_rule_gives_every_stored_slug():
    fn = re.search(r"const objSlug = .*?\n", APP_JS).group(0)
    script = fn + "const C = require(%s); console.log(JSON.stringify([C.planets.name.map(objSlug), C.stars.names.map(objSlug)]));" % json.dumps(
        str(Path(C.DEFAULT_CATALOGUE).resolve()))
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    planets, stars = json.loads(res.stdout)
    assert planets == CAT["planets"]["slug"] and stars == CAT["stars"]["slugs"]
    assert [O.slugify(n) for n in CAT["planets"]["name"]] == CAT["planets"]["slug"]  # no collisions, so no suffixes


def test_every_name_setuhq_links_is_in_the_catalogue():
    for cid, names in M.CHAPTER_PLANETS.items():
        assert cid in dict(M.CHAPTERS)
        assert set(names) <= NAMES, cid
    notable = json.loads(Path("docs/results/notable_planets.json").read_text())["planets"]
    assert {n["name"] for n in notable} <= NAMES
    ex = M.load_examples()["planets"]
    assert set(ex) <= NAMES and {p["star_name"] for p in ex.values()} <= STARS
    assert "pi Men" in STARS and "pi Men c" in NAMES


def test_one_renderer_for_the_system_view_and_the_honesty_label():
    src = {p: Path(p).read_text() for p in ("src/setuhq/app.py", "src/setuhq/catalogue.py", "src/setuhq/methods.py", "src/setuhq/galaxy.py")}
    # The stage markup and the label badge are written once, in methods._stage and methods.honesty_label.
    assert sum(t.count('class="btn mxplay"') for t in src.values()) == 1
    assert sum(len(re.findall(r'<span class="mxlabel [a-z]+">', t)) for t in src.values()) == 0
    assert sum(t.count('<span class="mxlabel {lab_cls}">') for t in src.values()) == 1
    # Every system view (Transit, the Galaxy's sheet, planet and star pages) goes through mxSystemView.
    js = APP_JS
    assert js.count("mxSystemParams(") == 3  # its definition, mxSystemView's call, MXV.system's own default
    for caller in ("function txTheatre(d)", "function mxOpenSystem(", "function plSystem("):
        body = js[js.index(caller):js.index("\n}\n", js.index(caller))]
        assert "mxSystemView(" in body, caller


def test_mentions_link_back_from_the_canonical_pages(built):
    data = _page_data(site_bundle(built))
    seen = data["catalogue_meta"]["mentions"]
    assert ["SetuHQ's own Transit case", "#/transit"] in seen["pi Men c"]
    assert ["The run's sky map", "#/sky"] in seen["pi Men"]
    notable = json.loads(Path("docs/results/notable_planets.json").read_text())["planets"]
    for k, n in enumerate(notable):
        assert [f"Galaxy tour, stop {k + 1}", f"#/galaxy?tour={k + 1}"] in seen[n["name"]]
    assert ["Methods: Blocking starlight", "#/methods?ch=imaging"] in seen["HR 8799 b"]
    assert "function ctSeen(name, skip)" in APP_JS and "${ctSeen(P.name[i]" in APP_JS and "ctSeen(name, R('#/sky'))" in APP_JS


def test_static_mentions_are_links(built):
    page = site_bundle(built)
    sky = _route(page, "sky")
    assert O.obj_link("star", "pi Men", "pi Men ›") in sky and O.obj_link("planet", "pi Men c", "pi Men c ›") in sky
    gal = _route(page, "galaxy")
    assert O.obj_link("planet", "51 Peg b", "Planet page ›", "gxref") in gal
    table = re.search(r"<table class='gxtable'>.*?</table>", gal, re.S).group(0)
    assert O.obj_link("star", "Proxima Centauri") in table and O.obj_link("planet", "Proxima Centauri b") in table
    meth = _route(page, "methods")
    for cid, names in M.CHAPTER_PLANETS.items():
        art = re.search(rf'<article class="mxch" id="mx-{cid}".*?(?=<article class="mxch"|$)', meth, re.S).group(0)
        for n in names:
            assert O.obj_link("planet", n, n + " ›") in art, (cid, n)
    assert '<template id="mxsystpl">' in page and 'id="txlinks"' in _route(page, "transit")
    # Dynamic views use the page's twin renderer.
    for snippet in ("objLink('star', H.n[h], 'Star page ›')", "objLink('planet', p.pl_name)", "objLink('star', p.hostname)",
                    "objLink('planet', S.planet, S.planet + ' ›')", "objLink('planet', name, name + ' ›')", "${ticLink(x.tic)}"):
        assert snippet in APP_JS, snippet
    assert _page_data(page)["tic_names"] == {"261136679": "pi Men"}


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_every_object_link_opens_its_page(built, tmp_path):
    url = served(built)
    script = tmp_path / "links.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1360, height: 900 } }), errs = [], hrefs = new Set();
  p.on('pageerror', e => errs.push(e.message));
  const grab = async () => (await p.evaluate(() => [...document.querySelectorAll('a[href^="/planets/"],a[href^="/stars/"]')].map(a => a.getAttribute('href')))).forEach(h => hrefs.add(h));
  for (const r of ['sky', 'transit', 'explorer', 'planets', 'methods']) { await p.goto(%s + '#/' + r); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(600); await grab(); }
  await p.evaluate(() => mxOpenSystem('51 Peg b')); await p.waitForTimeout(300); await grab();
  const sheet = await p.evaluate(() => [...document.querySelectorAll('#mxsheetnote a')].map(a => a.getAttribute('href')));
  await p.keyboard.press('Escape');
  const bad = [], seen = [];
  for (const h of hrefs) { await p.goto(new URL(h, %s).href); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(250);
    const t = await p.evaluate(() => document.querySelector('.route:not([hidden]) h1').textContent); seen.push(t); if (/not found/.test(t)) bad.push(h); }
  console.log(JSON.stringify({n: hrefs.size, bad, errs, sheet})); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(url), json.dumps(url)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["n"] > 80 and out["bad"] == [] and out["errs"] == []
    assert out["sheet"] == ["/planets/51-peg-b/", "/stars/51-peg/"]

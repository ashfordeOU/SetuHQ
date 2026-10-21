# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Round 10: the Catalogue, the planet and star pages, and the global search."""

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import catalogue as C
from setuhq import docket as docket_mod
from setuhq.app import APP_JS, ROUTE_META, SECTIONS, SUBNAV
from setuhq.methods import CHAPTERS
from conftest import served, site_bundle

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_NODE = shutil.which("node") is not None
HAVE_BROWSER = HAVE_NODE and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()
CAT = C.load_catalogue()
P = CAT["planets"]
N = len(P["name"])


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def built(pi_men_app):
    return pi_men_app


def _page_data(page):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))


def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


def _node(script: str):
    res = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


# ---------- the data ----------
def test_counts_match_the_dataset():
    c = CAT["counts"]
    assert c["rows"] == N == 8376
    assert all(len(v) == N for v in P.values()) and set(P) == set(CAT["columns"])
    assert c["with_distance"] == sum(1 for x in P["dist"] if x is not None) == 8049
    assert c["with_radius"] == sum(1 for x in P["radius"] if x is not None)
    assert c["with_mass"] == sum(1 for m, s in zip(P["mass"], P["msini"]) if m is not None or s is not None)
    assert c["without_star"] == sum(1 for s in P["star"] if not s)
    assert c["stars"] == len(CAT["stars"]["names"]) == len({s for s in P["star"] if s}) == 5684
    # Same source, same fetch, same definition as the Galaxy, which places the 8,049 with a distance.
    g = json.loads(Path("docs/results/exoplanet_map.json").read_text())
    assert (CAT["source"], CAT["fetched_at"], CAT["definition"], CAT["url"]) == (g["source"], g["fetched_at"], g["definition"], g["url"])
    assert g["counts"]["kept"] == c["with_distance"]
    meta = C.catalogue_meta(CAT)
    assert sum(meta["per_method"].values()) == N


def test_values_are_finite_or_null_and_the_file_is_strict_json():
    for k, col in P.items():
        for x in col:
            assert x is None or isinstance(x, (str, int)) or math.isfinite(x), k
    json.dumps(CAT, allow_nan=False)


def test_slugs_are_unique_url_safe_and_round_trip():
    slugs = P["slug"]
    assert len(set(slugs)) == N and all(re.fullmatch(r"[a-z0-9-]{1,120}", s) for s in slugs)
    for name, slug in zip(P["name"], slugs):
        base = C.slugify(name)
        assert slug == base or re.fullmatch(re.escape(base) + r"-\d+", slug)
    by = {s: i for i, s in enumerate(slugs)}
    assert all(P["slug"][by[s]] == s for s in slugs)
    assert P["name"][by["pi-men-c"]] == "pi Men c" and P["name"][by["wasp-39-b"]] == "WASP-39 b"
    ss = CAT["stars"]["slugs"]
    assert len(set(ss)) == len(ss) and all(re.fullmatch(r"[a-z0-9-]{1,120}", s) for s in ss)
    assert CAT["stars"]["names"][ss.index("pi-men")] == "pi Men"
    # The router takes exactly these slugs.
    from setuhq.routes import ROUTES_CORE_JS, SLUG_RE

    # The address of a planet or star page takes any slug: /planets/<slug>/ and /stars/<slug>/.
    assert "/^[a-z0-9][a-z0-9-]{0,119}$/.test(parts[1])" in ROUTES_CORE_JS and all(SLUG_RE.match(s) for s in P["slug"])


def test_python_filter_handles_missing_values():
    view = {"radius": (None, 0.2)}
    idx = C.catalogue_filter(CAT, view)
    assert idx and all(P["radius"][i] is not None and P["radius"][i] <= 0.2 for i in idx)
    # A missing value never passes a range; mass falls back to m sin i.
    no_mass = [i for i in range(N) if P["mass"][i] is None and P["msini"][i] is not None][0]
    assert no_mass in C.catalogue_filter(CAT, {"mass": (P["msini"][no_mass], P["msini"][no_mass])})
    assert len(C.catalogue_filter(CAT, {"hasdist": True})) == CAT["counts"]["with_distance"]
    assert len(C.catalogue_filter(CAT, {})) == N


# ---------- the page ----------
def test_catalogue_route_pages_and_lazy_data(built):
    page = site_bundle(built)
    assert ("explore", "Explore") in SECTIONS and ("Catalogue", "#/catalogue", ["catalogue", "planet", "star"]) in SUBNAV["explore"]
    assert ROUTE_META["planet"]["nav"] == ROUTE_META["star"]["nav"] == "explore"
    sec = _route(page, "catalogue")
    assert "Data: The Extrasolar Planets Encyclopaedia (exoplanet.eu), fetched 2026-10-18." in sec
    assert CAT["definition"].split(".")[0] in sec.replace("&#x27;", "'")
    assert "8,376 records" in sec and 'reads "not stored"' in sec.replace("&quot;", '"')
    for m in C.catalogue_meta(CAT)["methods"]:
        assert f'data-cm="{m}"' in sec
    for _, _, _, key in C.RANGES:
        assert f'data-rk="{key}" data-end="lo"' in sec and f'data-rk="{key}" data-end="hi"' in sec
    for k in C.SORTS:
        assert f'data-sort="{k}"' in sec
    # The records are a separate file, fetched (same origin) when needed; the page carries only the meta.
    data = _page_data(page)
    assert "catalogue" not in data and data["catalogue_meta"]["counts"] == CAT["counts"]
    assert "fetch('/assets/data/catalogue.json')" in APP_JS
    assert json.loads((built.parent / C.CATALOGUE_JSON).read_text()) == CAT
    from setuhq.site import check_budget

    assert check_budget(built.parent) == [] and "ZTF J1840-1742" not in page and "Kepler-1649 c" not in page
    # No request leaves the page's own folder.
    assert not re.search(r"""(?:src|href)=["']https?://(?!doi\.org)""", re.sub(r'<a [^>]*rel="noopener"[^>]*>|<link rel="canonical"[^>]*>', "", page))  # a canonical link is not a request
    assert not re.search(r"fetch\(['\"`]https?:", APP_JS)


def test_method_chapters_exist_and_pi_men_links_its_transit_case(built):
    ids = {c for c, _ in CHAPTERS}
    assert set(C.METHOD_CHAPTER.values()) <= ids
    data = _page_data(site_bundle(built))
    meta = data["catalogue_meta"]
    assert meta["refs"]["pi Men c"][0] == "https://doi.org/10.3847/2041-8213/aaef91"
    assert data["story"]["planet"] == "pi Men c"
    assert ["SetuHQ's own Transit case", "#/transit"] in meta["mentions"]["pi Men c"] and "ctSeen(P.name[i]" in APP_JS
    assert "S.planet && P.name[i] === S.planet" in APP_JS
    planet = _route(site_bundle(built), "planet")
    assert 'data-vis="system"' in planet and '<span class="mxlabel model">Model from stored values</span>' in planet
    for h in ("h-plparams", "h-plhost", "h-plwhere", "h-plref"):
        assert f'id="{h}"' in planet


def test_search_button_and_dialog_are_in_the_shell(built):
    page = site_bundle(built)
    top = re.search(r'<header class="topbar">.*?</header>', page, re.S).group(0)
    assert 'id="gsearchbtn"' in top and 'aria-haspopup="dialog"' in top
    assert '<dialog class="gsearch" id="gsearch"' in page and 'role="listbox"' in page
    assert "MX.labels[id], href: R('#/methods?ch=' + id)" in APP_JS


# ---------- JS against Python ----------
def _js_core():
    js = C.CATALOGUE_JS
    return js[js.index("function decodeCatView"):js.index("const ct = {")]


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_js_filter_equals_python_filter_and_the_url_round_trips(tmp_path):
    g = json.loads(Path("docs/results/exoplanet_map.json").read_text())
    meta = C.catalogue_meta(CAT, g["methods"], g["method_label"])  # the method order the app uses
    views = [
        {}, {"q": "kepler"}, {"q": "HD 39091"}, {"methods": ["transit", "rv"]}, {"radius": (None, 0.2)},
        {"mass": (1, 13), "period": (None, 10)}, {"year": (2000, 2005), "dist": (None, 50)}, {"teq": (1500, None)},
        {"teff": (3000, 4000), "multi": True}, {"hasdist": True, "methods": ["imaging"]}, {"q": "trappist", "multi": True},
    ]
    script = ("const CTM = %s; const C = require(%s); const P = C.planets; const starN = {};\n"
              "P.star.forEach(s => { if (s) starN[s] = (starN[s] || 0) + 1; });\n%s\n"
              "const views = %s; const out = views.map(w => { const v = decodeCatView(new URLSearchParams()); Object.assign(v, w);\n"
              "  for (const k of Object.keys(w)) if (Array.isArray(w[k]) && k !== 'methods') v[k] = w[k];\n"
              "  const enc = encodeCatView(v), back = decodeCatView(new URLSearchParams(enc));\n"
              "  return {idx: ctFilter(P, v, starN), enc, same: JSON.stringify(back) === JSON.stringify(v)}; });\n"
              "const s = ctSort(P, ctFilter(P, decodeCatView(new URLSearchParams('radius=~0.3')), starN), 'radius', 'desc');\n"
              "const m = ctSort(P, P.name.map((_, i) => i), 'mass', 'asc');\n"
              "console.log(JSON.stringify({out, top: P.radius[s[0]], sortedDesc: s.every((i, k) => k === 0 || P.radius[s[k - 1]] >= P.radius[i]),\n"
              "  nullsLast: m.slice(-5).every(i => P.mass[i] === null && P.msini[i] === null)}));") % (
        json.dumps(meta), json.dumps(str(Path(C.DEFAULT_CATALOGUE).resolve())), _js_core(),
        json.dumps([{k: (list(v) if isinstance(v, tuple) else v) for k, v in w.items()} for w in views]))
    res = _node(script)
    for w, r in zip(views, res["out"]):
        assert r["idx"] == C.catalogue_filter(CAT, w), w
        assert r["same"], (w, r["enc"])
    assert res["out"][0]["enc"] == "" and res["out"][4]["enc"] == "radius=~0.2"
    assert res["out"][3]["enc"] == "method=transit,rv"
    assert res["sortedDesc"] and res["top"] <= 0.3 and res["nullsLast"]


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_null_values_read_not_stored():
    js = C.CATALOGUE_JS
    fmt = re.search(r"const ctFmt = .*?\n", js).group(0)
    val = js[js.index("function ctVal("):js.index("function ctMoll(")]
    script = ("const esc = s => String(s); const ct = {P: {mass: [null, 2.5], mass_lo: [null, 0.1], mass_hi: [null, 0.2], e: [0, null], e_lo: [null, null], e_hi: [null, null]}};\n"
              + fmt + val + "console.log(JSON.stringify([ctVal(0, 'mass', 'MJ'), ctVal(1, 'mass', 'MJ'), ctVal(0, 'e', ''), ctVal(1, 'e', '')]));")
    out = _node(script)
    assert out[0] == '<td class="v na">not stored</td>'
    assert out[1] == '<td class="v">2.5 −0.1 / +0.2 MJ</td>'
    assert out[2] == '<td class="v">0</td>'  # a stored zero is a value, not a gap
    assert out[3] == '<td class="v na">not stored</td>'


# ---------- in the browser ----------
@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_catalogue_planet_star_and_search_in_the_browser(built, tmp_path):
    url = served(built)
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const out = [], ext = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) for (const theme of ['dark', 'light']) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
    await c.addInitScript(t => { try { localStorage.setItem('setuhq-theme', t); } catch (e) {} }, theme);
    const p = await c.newPage(), errs = [];
    p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    p.on('request', r => { if (!/^(file|data|blob):|^http:..127.0.0.1:/.test(r.url())) ext.push(r.url()); });
    const look = async route => { await p.goto(%s + route); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(1200); return p.evaluate(() => {
      const vw = document.documentElement.clientWidth, sec = document.querySelector('.route:not([hidden])');
      const small = [...sec.querySelectorAll('a,button,select,input,summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.width < 44 || r.height < 44) && !e.closest('p,td,dd,figcaption'); }).map(e => e.className || e.tagName);
      const wide = [...sec.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > vw + 1 && !e.closest('.ctscroll') && !e.closest('.cthead'); }).map(e => e.tagName + '.' + e.className);
      const cells = [...document.querySelectorAll('#ctspacer [role=row]')].map(row => row.querySelectorAll(':scope > [role=cell], :scope > [role=rowheader]').length);
      const heads = document.querySelectorAll('#cttable [role=columnheader]').length, colcount = (document.querySelector('#cttable') || {getAttribute: () => null}).getAttribute('aria-colcount');
      const rows = [...document.querySelectorAll('#ctspacer > a')].map(a => Math.round(a.getBoundingClientRect().height));
      return {cells, heads, colcount, id: sec.id, h1: sec.querySelector('h1').textContent, small, wide, rows, count: (document.querySelector('#ctcount') || {}).textContent,
        params: (document.querySelector('#plparams') || {}).textContent, links: [...sec.querySelectorAll('.pllinks a')].map(a => a.getAttribute('href'))}; }); };
    const r = {w, theme, errs};
    r.cat = await look('#/catalogue');
    r.filtered = await look('#/catalogue?method=transit&radius=~0.2');
    r.planet = await look('#/planet/pi-men-c');
    r.star = await look('#/star/pi-men');
    r.missing = await look('#/planet/no-such-planet');
    await p.click('#gsearchbtn'); await p.keyboard.type('wasp-39'); await p.waitForTimeout(300); await p.keyboard.press('Enter'); await p.waitForTimeout(800);
    r.search = await p.evaluate(() => [location.pathname, document.querySelector('#h-planet').textContent, document.querySelector('#gsearch').open]);
    // Escape closes the search even with text typed.
    await p.click('#gsearchbtn'); await p.keyboard.type('kepler'); await p.waitForTimeout(150); await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    r.escOpen = await p.evaluate(() => document.querySelector('#gsearch').open);
    // Ranges apply as typed; no match shows a message with a way out; scrolling adds rows one by one.
    await p.goto(%s + '#/catalogue'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(800);
    await p.evaluate(() => { document.querySelector('#route-catalogue .ctmore').open = true; });
    await p.fill('[data-rk="radius"][data-end="hi"]', '0.05'); await p.waitForTimeout(400);
    r.range = await p.evaluate(() => [encodeCatView(ct.view), location.search, document.querySelector('#ctcount').textContent]);
    await p.fill('[data-rk="radius"][data-end="hi"]', '-1'); await p.waitForTimeout(400);
    r.empty = await p.evaluate(() => [document.querySelector('#ctempty').hidden, document.querySelector('#ctscroll').hidden]);
    await p.click('#ctempty a'); await p.waitForTimeout(500);
    r.cleared = await p.evaluate(() => [encodeCatView(ct.view), document.querySelector('#ctempty').hidden]);
    r.scroll = await p.evaluate(async () => { const sc = document.querySelector('#ctscroll'), sp = document.querySelector('#ctspacer'); let adds = 0;
      const mo = new MutationObserver(ms => ms.forEach(m => adds += m.addedNodes.length)); mo.observe(sp, {childList: true});
      for (let k = 1; k <= 20; k++){ sc.scrollTop = k * ct.rowH; sc.dispatchEvent(new Event('scroll')); await new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res))); }
      mo.disconnect(); return {adds, ordered: [...sp.children].every((e, i, a) => !i || +a[i - 1].getAttribute('aria-rowindex') < +e.getAttribute('aria-rowindex'))}; });
    out.push(r); await c.close();
  }
  console.log(JSON.stringify({out, ext})); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(url), json.dumps(url)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout.strip().splitlines()[-1])
    assert data["ext"] == []  # no external requests
    n_small = len(C.catalogue_filter(CAT, {"methods": ["transit"], "radius": (None, 0.2)}))
    for r in data["out"]:
        assert r["errs"] == [], r
        for k in ("cat", "filtered", "planet", "star", "missing"):
            assert r[k]["wide"] == [], (k, r)
            if r["w"] == 390:
                assert r[k]["small"] == [], (k, r)
        assert r["cat"]["count"] == "Showing 8,376 of 8,376 planets"
        assert r["filtered"]["count"] == f"Showing {n_small:,} of 8,376 planets"
        assert 0 < len(r["cat"]["rows"]) < 60  # only the rows in view are in the page
        assert set(r["cat"]["rows"]) == ({128} if r["w"] == 390 else {44})
        # Table semantics at both widths: one cell (or the row header) per column header, and aria-colcount.
        assert r["cat"]["heads"] == 10 and r["cat"]["colcount"] == "10" and set(r["cat"]["cells"]) == {10}, r["cat"]
        assert r["escOpen"] is False
        # The view's settings stay out of the address (Copy link to this view makes a link with them).
        assert r["range"] == ["radius=~0.05", "", f"Showing {len(C.catalogue_filter(CAT, {'radius': (None, 0.05)})):,} of 8,376 planets"]
        assert r["empty"] == [False, True] and r["cleared"] == ["", True]
        assert r["scroll"]["adds"] == 20 and r["scroll"]["ordered"]  # one new row per row scrolled, none re-rendered
        assert r["planet"]["h1"] == "pi Men c" and "not stored" in r["planet"]["params"]
        assert "/candidates/tess-fa3483ce6f83-000/" in r["planet"]["links"] and "/how-it-works/transits/" in r["planet"]["links"]
        assert "/explore/galaxy/?focus=pi+Men" in r["planet"]["links"] and "/explore/" in r["planet"]["links"]
        assert r["star"]["h1"] == "pi Men" and r["missing"]["h1"] == "Planet not found"
        assert r["search"] == ["/planets/wasp-39-b/", "WASP-39 b", False]


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_galaxy_focus_deep_link_round_trips():
    from setuhq.galaxy import GALAXY_JS, galaxy_data, galaxy_meta

    js = GALAXY_JS[GALAXY_JS.index("function decodeGalaxyView"):GALAXY_JS.index("// Which planets the filters keep")]
    script = ("const GXM = %s;\n" % json.dumps(galaxy_meta(galaxy_data()))) + js + """
const v = decodeGalaxyView(new URLSearchParams('focus=' + encodeURIComponent('pi Men')));
console.log(JSON.stringify([v.focus, encodeGalaxyView(v), encodeGalaxyView(decodeGalaxyView(new URLSearchParams()))]));"""
    assert _node(script) == ["pi Men", "focus=pi%20Men", ""]
    assert "function gxFocus(name)" in GALAXY_JS and "if (gx.view.focus) gxFocus(gx.view.focus);" in GALAXY_JS
    # Every catalogue host with a distance is a Galaxy host, so the deep link always finds its star.
    hosts = set(galaxy_data()["hosts"]["n"])
    assert all((P["star"][i] or P["name"][i]) in hosts for i in range(N) if P["dist"][i] is not None)


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_galaxy_focus_on_an_unknown_star_says_so(built, tmp_path):
    script = tmp_path / "gx.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--allow-file-access-from-files'] });
  const p = await b.newPage(), errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(%s + '#/galaxy?focus=Nowhere%%20Star'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForFunction(() => typeof gx !== 'undefined' && gx.ready, null, {timeout: 20000}); await p.waitForTimeout(300);
  const bad = await p.evaluate(() => { const n = document.querySelector('#gxfocusnote'); return [n.hidden, n.getAttribute('role'), n.textContent, n.querySelector('a').getAttribute('href')]; });
  await p.goto(%s + '#/galaxy?focus=pi%%20Men'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(500);
  const good = await p.evaluate(() => [document.querySelector('#gxfocusnote').hidden, gx.G.hosts.n[gx.sel]]);
  console.log(JSON.stringify({bad, good, errs})); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(served(built)), json.dumps(served(built))))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errs"] == []
    assert out["bad"] == [False, "status", "No star “Nowhere Star” on the map (no stored distance or not in the catalogue). Search the Catalogue ›",
                          "/catalogue/?q=Nowhere+Star"]
    assert out["good"] == [True, "pi Men"]


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_typing_both_ends_of_a_range_without_pausing_keeps_both(built, tmp_path):
    script = tmp_path / "range.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1360, height: 900 } }), errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(%s + '#/catalogue'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(1200);
  await p.evaluate(() => { document.querySelector('#route-catalogue .ctmore').open = true; });
  // No pause between the boxes: each range has its own timer and reads both of its boxes.
  await p.click('[data-rk="mass"][data-end="lo"]'); await p.keyboard.type('1'); await p.keyboard.press('Tab'); await p.keyboard.type('2');
  await p.click('[data-rk="year"][data-end="lo"]', {delay: 0}); await p.keyboard.type('2000'); await p.keyboard.press('Tab'); await p.keyboard.type('2005');
  await p.waitForTimeout(600);
  const out = await p.evaluate(() => ({hash: encodeCatView(ct.view), boxes: [...document.querySelectorAll('[data-rk="mass"],[data-rk="year"]')].map(i => i.value),
    seen: null}));
  await p.goto(%s + '#/planet/pi-men-c'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(800);
  out.seen = await p.evaluate(() => [document.querySelector('#plref .plseen .pllab').textContent, [...document.querySelectorAll('#plref .plseen a')].map(a => a.getAttribute('href'))]);
  out.errs = errs; console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(served(built)), json.dumps(served(built))))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errs"] == []
    assert "year=2000~2005" in out["hash"] and "mass=1~2" in out["hash"], out["hash"]
    assert out["boxes"] == ["2000", "2005", "1", "2"]  # year first: it comes first in the page
    assert out["seen"][0] == "Where SetuHQ shows it:" and "/candidates/tess-fa3483ce6f83-000/" in out["seen"][1]


def test_phone_cards_are_cheap_to_lay_out():
    css, js = C.CATALOGUE_CSS, C.CATALOGUE_JS
    card = re.search(r"\.ctcard\{[^}]*\}", css).group(0)
    assert "display:flex" in card and "contain" not in card and "grid" not in card  # measured: containment doubled style time
    assert "text-overflow" not in re.search(r"\.ctcard>span\{[^}]*\}", css).group(0)
    # A value not stored stays a cell, in flow, taking no room (and cancelling its gap); no pseudo-element labels.
    assert ".ctcard>span.na{flex:0 0 0;width:0;height:0;overflow:hidden;margin-left:-12px}" in css
    assert "::before{content:attr" not in css and "::after{content:attr" not in css
    assert '<span role="cell" class="${cls} na" aria-label="not stored">—</span>' in js
    # 12 rows of margin normally, 2 during a fling; a jump swaps the window in with one replaceChildren.
    assert "Math.abs(top - (ct.prevTop ?? top)) > H ? 2 : 12" in js and "sp.replaceChildren(...els)" in js
    assert "if (top === ct.lastTop) return;" in js


def test_generic_object_links_carry_the_name():
    from setuhq.objects import obj_link
    assert obj_link("planet", "pi Men c", "Planet page ›") == '<a class="objlink" data-planet="pi Men c" href="/planets/pi-men-c/" aria-label="pi Men c, planet page">Planet page ›</a>'
    assert "aria-label" not in obj_link("star", "pi Men", "pi Men ›")
    assert "` aria-label=\"${esc(n)}, ${kind} page\"`" in APP_JS



@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_a_fling_rebuilds_the_window_once_per_frame_and_keeps_the_cells(built, tmp_path):
    script = tmp_path / "fling.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); const p = await c.newPage(), errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(%s + '#/catalogue'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(1200);
  const out = await p.evaluate(async () => { const sc = document.querySelector('#ctscroll'), sp = document.querySelector('#ctspacer'); let swaps = 0, removed = 0;
    const real = sp.replaceChildren.bind(sp); sp.replaceChildren = (...a) => { swaps++; return real(...a); };
    const mo = new MutationObserver(ms => ms.forEach(m => removed += m.removedNodes.length)); mo.observe(sp, {childList: true});
    for (let k = 1; k <= 10; k++){ sc.scrollTop += 2500; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); }
    mo.disconnect();
    const rows = [...sp.querySelectorAll('[role=row]')], vis = rows.filter(r => { const q = r.getBoundingClientRect(), s = sc.getBoundingClientRect(); return q.bottom > s.top && q.top < s.bottom; });
    return {swaps, rows: rows.length, visible: vis.length, cells: [...new Set(rows.map(r => r.querySelectorAll(':scope > [role=cell], :scope > [role=rowheader]').length))],
      na: [...sp.querySelectorAll('.na')].every(e => e.getAttribute('aria-label') === 'not stored'), first: +rows[0].getAttribute('aria-rowindex')}; });
  console.log(JSON.stringify(Object.assign(out, {errs}))); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(served(built))))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errs"] == [] and out["swaps"] == 10  # one swap per jump, not node-by-node
    assert out["cells"] == [10] and out["na"] is True
    assert out["rows"] <= 12 and out["visible"] >= 4  # the rows in view, plus two each side, during a fling
    assert out["first"] > 150  # 10 × 2,500 px down at 128 px a card

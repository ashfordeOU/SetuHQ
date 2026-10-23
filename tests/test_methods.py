# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
import json
import math
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import docket as docket_mod
from setuhq import methods as M
from setuhq.app import APP_JS, build_app
from setuhq.galaxy import DEFAULT_COVERAGE, galaxy_data, load_coverage

from test_story import run_dir  # noqa: F401  (fixture)
from conftest import served, site_bundle

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_NODE = shutil.which("node") is not None
HAVE_BROWSER = HAVE_NODE and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()
EX = M.load_examples()


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


# ---------- physics against closed forms and published values ----------
def test_rv_semi_amplitude_matches_published_values():
    peg = EX["planets"]["51 Peg b"]
    k = M.rv_semi_amplitude(peg["orbital_period"], peg["mass_sini"], peg["star_mass"], peg["eccentricity"])
    assert k == pytest.approx(peg["k"], rel=0.05) and k == pytest.approx(56, rel=0.05)  # published ≈ 56 m/s
    assert M.rv_semi_amplitude(11.862 * 365.25, 1.0, 1.0, 0.049) == pytest.approx(12.5, rel=0.05)  # Jupiter–Sun
    assert M.rv_semi_amplitude(365.25, M.GM_EARTH / M.GM_JUP, 1.0) == pytest.approx(0.089, rel=0.05)  # Earth–Sun
    # K scales as sin i and as 1/√(1 − e²).
    assert M.rv_semi_amplitude(10, 1, 1, 0, 0.5) == pytest.approx(0.5 * M.rv_semi_amplitude(10, 1, 1))
    assert M.rv_semi_amplitude(10, 1, 1, 0.6) == pytest.approx(M.rv_semi_amplitude(10, 1, 1) / 0.8)


def test_barycentre_and_kepler_equation():
    a_star, a_pl = M.barycentre_offsets(1.0, 1.0, 1.0)
    q = M.GM_JUP / (M.GM_SUN + M.GM_JUP)
    assert a_star == pytest.approx(q) and a_pl == pytest.approx(1 - q) and a_star + a_pl == pytest.approx(1)
    assert M.barycentre_offsets(5.204 * M.AU, 1.0, 1.0)[0] / M.R_SUN == pytest.approx(1.07, abs=0.01)  # just outside the Sun
    assert M.barycentre_offsets(M.AU, M.GM_EARTH / M.GM_JUP, 1.0)[0] < M.R_SUN  # Earth's lies inside
    rng = random.Random(1)
    for _ in range(500):
        e, Mean = rng.uniform(0, 0.97), rng.uniform(0, 2 * math.pi)
        E = M.kepler_E(Mean, e)
        assert E - e * math.sin(E) == pytest.approx(Mean, abs=1e-10)
    # Star, barycentre and planet stay on one line, on opposite sides, at every time.
    for _ in range(200):
        t, e, mp = rng.random(), rng.uniform(0, 0.9), rng.uniform(0.001, 20)
        (px, py), (sx, sy) = M.orbit_positions(t, 1.0, 1.0, e, mp, 1.0)
        assert px * sy - py * sx == pytest.approx(0, abs=1e-12) and px * sx + py * sy <= 0
        qq = mp * M.GM_JUP / (M.GM_SUN + mp * M.GM_JUP)
        assert math.hypot(sx, sy) / (math.hypot(sx, sy) + math.hypot(px, py)) == pytest.approx(qq)
    # Fastest at periastron: equal time steps cover more angle there.
    d_peri = M.true_anomaly(0.01, 0.6) - M.true_anomaly(0, 0.6)
    d_apo = M.true_anomaly(math.pi + 0.01, 0.6) - M.true_anomaly(math.pi, 0.6)
    assert d_peri > 5 * d_apo


def test_transit_model_and_durations():
    pm = EX["planets"]["pi Men c"]
    u1, u2 = M.ld_coeffs(pm["star_teff"])
    assert (u1, u2) == (pytest.approx(0.333, abs=0.003), pytest.approx(0.228, abs=0.003))  # Claret 2017 near 6037 K
    k = 0.01703
    # Without limb darkening the depth is exactly k²; with it, a central crossing gives k² I(0)/<I>.
    assert 1 - M.transit_flux(0, k, 0, 0) == pytest.approx(k * k, rel=1e-9)
    assert 1 - M.transit_flux(0, k, u1, u2) == pytest.approx(k * k / (1 - u1 / 3 - u2 / 6), rel=1e-9)
    assert (1 - M.transit_flux(0.59, k, 0.33, 0.23)) * 1e6 == pytest.approx(315, abs=3)  # atlas C3
    assert M.transit_flux(1 + k + 1e-6, k, u1, u2) == 1.0
    # Depth = (Rp/R★)² from the stored radii (no limb darkening).
    kr = pm["radius"] * M.R_JUP / (pm["star_radius"] * M.R_SUN)
    assert 1 - M.transit_flux(0.3, kr, 0, 0) == pytest.approx(kr ** 2, rel=1e-9)
    t14, t23 = M.transit_durations(6.2679, 13.38, 0.01703, 0.59, 87.456)
    assert t14 * 24 == pytest.approx(2.953, rel=0.01) and t23 * 24 == pytest.approx(2.82, abs=0.01)
    assert M.overlap_area(0.5, 0.1) == pytest.approx(math.pi * 0.01) and M.overlap_area(2, 0.1) == 0


def test_microlensing_astrometry_atmospheres_and_doppler():
    assert M.paczynski(1.0) == pytest.approx(1.342, abs=5e-4)
    assert M.paczynski(0.1) == pytest.approx(10.04, abs=0.01)
    assert M.einstein_angle_mas(0.3, 0.125) == pytest.approx(0.55, abs=0.01)
    assert M.astrometric_signature_uas(1, 1, 5.204, 10) == pytest.approx(497, abs=2)
    assert M.astrometric_signature_uas(M.GM_EARTH / M.GM_JUP, 1, 1, 10) == pytest.approx(0.30, abs=0.01)
    w = EX["planets"]["WASP-39 b"]
    assert M.scale_height_m(1116, 2.3, w["mass"], w["radius"]) / 1e3 == pytest.approx(930, rel=0.03)
    assert M.depth_per_scale_height(1116, 2.3, w["mass"], w["radius"], w["star_radius"]) * 1e6 == pytest.approx(440, rel=0.03)
    assert M.doppler_ratio(55.77) == pytest.approx(1.86e-7, rel=0.01)
    assert M.transit_probability(1.0, 1.0) == pytest.approx(0.00465, rel=0.01)


def test_band_positions_match_the_cited_table():
    bands = {(m, l) for m, l, _ in M.BANDS}
    for expected in (("Na", 0.589), ("K", 0.767), ("H₂O", 1.4), ("H₂O", 1.9), ("H₂O", 2.7), ("CO₂", 4.26), ("CO", 4.67)):
        assert expected in bands
    assert "false colour: infrared is invisible to the eye" in M.METHODS_JS


def test_teff_colour_and_spectral_class():
    hot, sun, cool = M.teff_rgb(20000), M.teff_rgb(5772), M.teff_rgb(3000)
    assert hot[2] == 255 and hot[0] < hot[2]  # blue-white
    assert cool[0] == 255 and cool[2] < 140  # orange-red
    assert sun[0] == 255 and min(sun) > 225  # near white, slightly warm
    assert min(M.teff_rgb(6500)) > 245  # D65 white point
    assert [M.spectral_class(t)[0] for t in (30000, 15000, 9000, 7000, 6037, 5300, 3900, 2600)] == list("BBAFGKMM")
    assert M.spectral_class(6037) == ("G", "G0V")


# ---------- the JavaScript twins give the same numbers ----------
def _js_prelude(ex):
    js = M.METHODS_JS[:M.METHODS_JS.index("// ---------- stages")]
    meta = {"claret": M.CLARET_TESS, "mamajek": M.MAMAJEK, "examples": ex}
    return f"const D = {{methods: {json.dumps(meta)}}};\n{js}\n"


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_js_physics_twins_match_python(tmp_path):
    peg = EX["planets"]["51 Peg b"]
    script = _js_prelude(EX["planets"]) + """
const out = {};
out.K = [mxK(4.2307966, 0.46, 1.03, 0.0069, 1), mxK(11.862 * 365.25, 1, 1, 0.049, 1), mxK(365.25, 3.986004e14 / 1.2668653e17, 1, 0, 1)];
out.E = [mxKeplerE(1.234, 0.3), mxKeplerE(5.5, 0.9)];
out.A = mxPacz(1); out.ld = mxLd(6037); out.flux = [mxFlux(0, 0.01703, 0.33, 0.23), mxFlux(0.59, 0.01703, 0.33, 0.23), mxFlux(1.0, 0.1, 0.33, 0.23)];
out.rgb = [mxTeffRGB(3000), mxTeffRGB(5772), mxTeffRGB(20000)]; out.cls = [mxClass(6037), mxClass(3000)];
out.col = []; for (let i = 0; i < 100; i++){ const t = i / 100, B = mxBodies(t, 0.6, 0.001, 0.7); out.col.push([B.star[0] * B.planet[1] - B.star[1] * B.planet[0], B.star[0] * B.planet[0] + B.star[1] * B.planet[1], Math.hypot(...B.star) / (Math.hypot(...B.star) + Math.hypot(...B.planet))]); }
out.scale = [mxWobbleScale(0.000954, 150, 5.204, 1), mxWobbleScale(3e-6, 150, 1, 1), mxWobbleScale(0.3, 150, 1, 1), mxWobbleScale(0.001, 0, 1, 1)];
console.log(JSON.stringify(out));"""
    f = tmp_path / "t.js"
    f.write_text(script)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    assert out["K"][0] == pytest.approx(M.rv_semi_amplitude(peg["orbital_period"], peg["mass_sini"], peg["star_mass"], peg["eccentricity"]), rel=1e-9)
    assert out["K"][1] == pytest.approx(M.rv_semi_amplitude(11.862 * 365.25, 1, 1, 0.049), rel=1e-9)
    assert out["K"][2] == pytest.approx(0.0895, abs=0.001)
    assert out["E"] == [pytest.approx(M.kepler_E(1.234, 0.3)), pytest.approx(M.kepler_E(5.5, 0.9))]
    assert out["A"] == pytest.approx(M.paczynski(1))
    assert out["ld"] == [pytest.approx(v) for v in M.ld_coeffs(6037)]
    assert out["flux"] == [pytest.approx(M.transit_flux(z, k, 0.33, 0.23), abs=1e-12) for z, k in ((0, 0.01703), (0.59, 0.01703), (1.0, 0.1))]
    assert [tuple(c) for c in out["rgb"]] == [M.teff_rgb(3000), M.teff_rgb(5772), M.teff_rgb(20000)]
    assert out["cls"] == [["G", "G0V"], ["M", "M5V"]]
    for cross, dot, ratio in out["col"]:  # collinear, opposite sides, a★/(a★ + a_p) = q
        assert abs(cross) < 1e-12 and dot <= 0 and ratio == pytest.approx(0.001)
    jup, earth, big, hidden = out["scale"]
    assert hidden == {"N": 1, "label": ""}  # a hidden (zero-size) stage never loops
    # The exaggeration label is there whenever the factor is above 1, and says what is true.
    assert jup["N"] > 1 and "exaggerated ×" in jup["label"] and "true a★" in jup["label"] and "R★" in jup["label"]
    assert earth["N"] > jup["N"] and "exaggerated ×" in earth["label"]
    assert big["N"] == 1 and big["label"] == ""


# ---------- the page ----------
@pytest.fixture(scope="module")
def page_html(tmp_path_factory, run_dir):  # noqa: F811
    return site_bundle(build_app(run_dir, tmp_path_factory.mktemp("app") / "app", title="t"))


def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


def test_every_chapter_has_a_labelled_visual_and_sources(page_html):
    sec = _route(page_html, "methods")
    for cid, title in M.CHAPTERS:
        art = sec.split(f'<article class="mxch" id="mx-{cid}"', 1)[1].split('<article class="mxch"', 1)[0]
        from setuhq.routes import url_for

        assert f'href="{url_for("methods", {"ch": cid})}"' in sec
        for fig in re.findall(r'<figure class="mxstage.*?</figure>', art, re.S):
            label = re.search(r'<span class="mxlabel (\w+)">([^<]+)</span>', fig)
            assert label and label.group(2) in (M.LABEL_ILL, M.LABEL_MODEL, M.LABEL_DATA, M.LABEL_SPEC)
            assert re.search(r'<canvas role="img" aria-label="[^"]{40,}"', fig)  # a text description
            assert 'class="mxdesc"' in fig
        if cid != "history":
            assert "<details class=\"mxsources\">" in art
    assert "SetuHQ does not do spectroscopy" in sec and "This is what SetuHQ does" in sec
    for href in re.findall(r'href="(https?://[^"]+)"', sec):
        assert href.startswith("https://")


def test_method_counts_equal_the_dataset(page_html):
    g = galaxy_data()
    sec = _route(page_html, "methods")
    for method in ("transit", "rv", "astrometry", "microlensing", "imaging"):
        n = g["per_method"][method]
        assert f"<b>{n:,}</b> of the {g['counts']['kept']:,} planets" in sec, method
    assert sum(sum(v.values()) for v in M.per_year(g).values()) == g["counts"]["kept"]


def test_biosignature_honesty_and_history(page_html):
    sec = _route(page_html, "methods")
    assert "Life has not been detected anywhere beyond Earth." in sec
    assert not re.search(r"(?i)(life (has been|was) detected|evidence of life|alien)", sec.replace("Life has not been detected", ""))
    for k in ("greaves", "snellen20", "villanueva", "madhu23", "madhu25", "schmidt", "luque"):
        assert M.SOURCES[k][1] in sec
    assert "contested" in sec and "Not established" in sec
    years = [y for y, *_ in M.HISTORY]
    assert years == sorted(years)
    for y, au, title, key, summary, why, link in M.HISTORY:
        url = M.SOURCES[key][1]
        assert url.startswith("https://doi.org/") or "kva.se" in url
        assert len(summary.split()) <= 50 and len(why.split()) <= 50
    assert "this is a recovery, not a discovery" in sec


def test_molecule_cards_have_geometry_bands_and_sources():
    for m in M.MOLECULES:
        assert m["bands"] and m["who"] and m["why"] and m["abiotic"]
        for _, key in m["seen"]:
            assert M.SOURCES[key][1].startswith("https://")
        g = m["geom"]
        assert g["shape"] == "atom" or g["r"] > 0.9
    water = next(m for m in M.MOLECULES if m["id"] == "H2O")["geom"]
    assert (water["r"], water["angle"]) == (0.958, 104.48)


def test_reduced_motion_and_no_external_requests():
    js = M.METHODS_JS
    act = re.search(r"function mxActivate\(article, on\)\{.*?\n\}\n", js, re.S).group(0)
    assert "if (!mxRM.matches && !st.started)" in act and "mxDraw(st)" in act  # a still key frame; play only on request
    for name in re.findall(r"^MXV\.(\w+) = \{key: ([\d.]+)", js, re.M):
        assert 0 <= float(name[1]) < 1
    assert set(re.findall(r"^MXV\.(\w+) = ", js, re.M)) >= {"system", "scan", "doppler", "wobble", "astrometry", "lens", "coronagraph", "transmission", "molecule"}
    assert "fetch(" not in js and "XMLHttpRequest" not in js and not re.search(r"https?://", js)
    assert "mxShown(r === 'methods')" in APP_JS and "mxShowChapter(p.params.get('ch'))" in APP_JS


def test_methods_examples_are_stored_values():
    peg = EX["planets"]["51 Peg b"]
    assert EX["source"] == "The Extrasolar Planets Encyclopaedia (exoplanet.eu)" and EX["fetched_at"].startswith("2026-10-18")
    assert (peg["orbital_period"], peg["mass_sini"], peg["star_mass"], peg["k"]) == (4.2307966, 0.46, 1.03, 55.77)
    notable = json.loads(Path("docs/results/notable_planets.json").read_text())["planets"]
    assert all(n["name"] in EX["planets"] for n in notable) and EX["missing"] == []


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_methods_chapters_draw_without_errors_and_fit_a_phone(run_dir, tmp_path):  # noqa: F811
    page = build_app(run_dir, tmp_path / "app", title="t")
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const out = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob }); const p = await c.newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    for (const ch of %s) {
      await p.goto(%s + '#/methods?ch=' + ch); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(500);
      out.push(Object.assign({w, ch, errs: errs.slice()}, await p.evaluate(ch => {
        const art = document.querySelector('#mx-' + ch), vw = document.documentElement.clientWidth;
        // The chapter's own stages: the shared components it places (the sky by year, the timeline, the orbits) draw when
        // they come on screen, and their own tests check them.
        const lit = [...art.querySelectorAll('.mxstage canvas')].map(cv => { const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let n = 0; for (let i = 0; i < d.length; i += 4 * 97) if (d[i] + d[i + 1] + d[i + 2] > 60) n++; return n; });
        const small = [...art.querySelectorAll('a,button,select,input,summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.width < 44 || r.height < 44) && !e.closest('p,li,dd'); }).map(e => e.className || e.tagName);
        const wide = [...art.querySelectorAll('*')].filter(e => !e.closest('.tablewrap') && e.getBoundingClientRect().right > vw + 1).map(e => e.tagName + '.' + e.className);
        const shown = [...document.querySelectorAll('.mxch')].filter(a => getComputedStyle(a).display !== 'none').length;
        // Every numbers-table value is on screen, and no two contrast-ladder labels overlap.
        const cut = [...art.querySelectorAll('.mxnums td.num')].filter(td => { const r = td.getBoundingClientRect(); return r.width && (r.right > vw + 1 || r.left < -1); }).map(td => td.textContent.slice(0, 20));
        const labs = [...art.querySelectorAll('.mxcontrast li .lab')].map(l => l.getBoundingClientRect()), clash = [];
        for (let i = 0; i < labs.length; i++) for (let j = i + 1; j < labs.length; j++){ const a = labs[i], b = labs[j]; if (a.left < b.right && a.right > b.left && a.top < b.bottom - 0.5 && a.bottom > b.top + 0.5) clash.push([i, j]); }
        return {hidden: art.hidden, lit, small, wide: wide.slice(0, 4), shown, cut, clash};
      }, ch)));
    }
    await c.close();
  }
  console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps([c for c, _ in M.CHAPTERS]), json.dumps(served(page))))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=240)
    assert res.returncode == 0, res.stderr
    for r in json.loads(res.stdout.strip().splitlines()[-1]):
        assert r["errs"] == [] and r["hidden"] is False and r["shown"] == 1, r  # one chapter at a time
        assert r["cut"] == [] and r["clash"] == [], r
        assert all(n > 5 for n in r["lit"]), json.dumps(r)  # every canvas drew something
        assert r["wide"] == [], r
        if r["w"] == 390:
            assert r["small"] == [], r


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_every_route_loads_and_the_galaxy_opens_a_system_view(run_dir, tmp_path):  # noqa: F811
    page = build_app(run_dir, tmp_path / "app", title="t")
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--allow-file-access-from-files'] });
  const p = await b.newPage(), errs = [], loaded = {};
  p.on('pageerror', e => errs.push(e.message));
  for (const r of ['overview', 'sky', 'galaxy', 'transit', 'explorer', 'sentinels', 'methods', 'mission']) {
    const t0 = Date.now(); await p.goto(%s + '#/' + r, {timeout: 15000}); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); loaded[r] = Date.now() - t0;
  }
  await p.goto(%s + '#/galaxy'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForFunction(() => typeof gx !== 'undefined' && gx.ready, null, {timeout: 20000});
  const name = await p.evaluate(() => { const nt = gx.G.notable.find(n => MX.examples[n.name]); gxSelect(nt.host, nt.planet); return nt.name; });
  await p.click(`#gxcard button[data-gxsys="${name}"]`); await p.waitForTimeout(500);
  const sheet = await p.evaluate(() => ({open: document.querySelector('#mxsheet').open, title: document.querySelector('#mxsheettitle').textContent}));
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);
  sheet.closed = await p.evaluate(() => !document.querySelector('#mxsheet').open);
  console.log(JSON.stringify({errs, loaded, sheet, name})); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(served(page)), json.dumps(served(page))))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=240)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errs"] == [] and len(out["loaded"]) == 8
    assert out["sheet"] == {"open": True, "title": out["name"], "closed": True}


def test_transit_theatre_is_the_shared_system_view(page_html):
    fn = re.search(r"function txTheatre\(d\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "known && star" in fn and "what a planet this deep would cast" in fn and "it does not confirm the dip" in fn
    assert "function theatre(d)" not in APP_JS  # one drawing of a dip, not two
    tx = _route(page_html, "transit")
    assert tx.count('data-vis="system"') == 1 and 'id="txtheatre"' in tx
    assert '<span class="mxlabel model">Model from stored values</span>' in tx

# ---------- round 9b: a real spectrum and the Atmosphere Lab ----------
def test_jwst_spectrum_is_the_cited_public_data():
    J = M.load_jwst()
    assert J["licence"] == "CC-BY-4.0" and J["doi"] == "https://doi.org/10.5281/zenodo.10161743"
    assert "Carter et al. 2024" in J["citation"] and J["files"]["spectrum"].endswith("NIRSpec_PRISM/bins_scale5.csv")
    assert len(J["points"]) == 36 and all(p[4] > 0 and p[1] < p[0] < p[2] for p in J["points"])
    peak = max(J["points"], key=lambda p: p[3])
    assert 4.2 < peak[0] < 4.5  # the CO₂ band (JWST ERS Team 2023)
    # The baseline depth is (Rp/R★)² from the catalogue's radii, within a few per cent.
    w = EX["planets"]["WASP-39 b"]
    base = (w["radius"] * M.R_JUP / (w["star_radius"] * M.R_SUN)) ** 2 * 1e6
    med = sorted(p[3] for p in J["points"])[len(J["points"]) // 2]
    assert med == pytest.approx(base, rel=0.03)
    # The feature is a few scale heights: the CO₂ peak sits 2–5 × Δδ_H above the continuum.
    dH = M.depth_per_scale_height(1116, 2.3, w["mass"], w["radius"], w["star_radius"]) * 1e6
    assert 2 < (peak[3] - min(p[3] for p in J["points"])) / dH < 5


def test_atmosphere_lab_model():
    assert M.atm_model(3.0, 21000, 400, {}) == 21000
    # At an isolated band centre one molecule adds exactly n scale heights.
    assert M.atm_model(0.589, 21000, 400, {"Na": 2.5}) == pytest.approx(21000 + 2.5 * 400)
    assert M.atm_model(4.26, 0, 1, {"CO2": 1}) == pytest.approx(1.0)
    for mol, bands in M.LAB_BANDS.items():
        for c, w in bands:
            assert 0.5 < c < 5.4 and 0 < w < 0.2
    assert {b[1] for b in M.LAB_BANDS["H2O"]} and (4.26, 0.08) in M.LAB_BANDS["CO2"] and (4.67, 0.08) in M.LAB_BANDS["CO"]


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_atmosphere_lab_js_matches_python(tmp_path):
    script = _js_prelude(EX["planets"]).replace("const D = {methods: {", "const D = {methods: {lab_bands: " + json.dumps(M.LAB_BANDS) + ", ", 1)
    script += (M.METHODS_JS[M.METHODS_JS.index("function mxAtm("):M.METHODS_JS.index("function mxSpecChart(")]
               + "console.log(JSON.stringify([0.589, 1.4, 2.7, 4.26, 4.6].map(l => mxAtm(l, 21000, 430, {H2O: 2, CO2: 3, Na: 1, CO: 0.5}))));")
    f = tmp_path / "t.js"
    f.write_text(script)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    S = {"H2O": 2, "CO2": 3, "Na": 1, "CO": 0.5}
    assert out == [pytest.approx(M.atm_model(l, 21000, 430, S)) for l in (0.589, 1.4, 2.7, 4.26, 4.6)]



# ---------- round 9b: timing, false positives, population, equations of life ----------
def test_timing_and_false_positive_physics():
    assert M.rm_amplitude(3.5, 0.157) == pytest.approx(88, rel=0.03)  # HD 189733 b, Gaudi & Winn 2007
    assert M.rm_amplitude(4.7, 0.121) == pytest.approx(70, rel=0.03)  # HD 209458 b
    # Thermal eclipse: k² times the Planck ratio; equal temperatures give exactly k².
    assert M.thermal_eclipse_depth(0.1, 3000, 3000, 15) == pytest.approx(0.01)
    assert M.planck(15, 503) / M.planck(15, 2566) == pytest.approx(
        math.expm1(1.4387769e-2 / (15e-6 * 2566)) / math.expm1(1.4387769e-2 / (15e-6 * 503)))
    assert M.diluted_depth(0.5, 1e-3) == pytest.approx(500e-6)
    t14, t23 = M.transit_durations(6.2679, 13.38, 0.01703, 0.59, 87.456)
    assert t23 / t14 == pytest.approx(0.95, abs=0.01)  # U-shaped
    assert M.transit_durations(6.2679, 13.38, 0.01703, 1 - 0.01703 + 1e-6, 87.456)[1] is None  # grazing: no T23
    k9 = EX["planets"]
    assert k9["Kepler-9 c"]["orbital_period"] / k9["Kepler-9 b"]["orbital_period"] == pytest.approx(2.03, abs=0.01)


def test_habitable_zone_and_population():
    assert [round(M.hz_distance_au(l, 5780, 1.0), 2) for l in M.KOPPARAPU] == [0.75, 0.95, 1.68, 1.77]  # atlas H4
    L = 1.10 ** 2 * (6037 / 5772) ** 4
    assert (round(M.hz_distance_au("runaway_greenhouse", 6037, L), 2), round(M.hz_distance_au("maximum_greenhouse", 6037, L), 2)) == (1.13, 1.97)
    pop = M.load_population()
    v = pop["valley"]
    assert sum(v["counts"]) == v["n"] and len(v["edges_re"]) == len(v["counts"]) + 1
    assert pop["hz"]["n_conservative"] == sum(1 for p in pop["hz"]["planets"] if p["conservative"]) <= pop["hz"]["n_optimistic"]
    for p in pop["hz"]["planets"]:
        lo, hi = M.hz_seff("early_mars", p["teff"]), M.hz_seff("recent_venus", p["teff"])
        assert lo * 0.999 <= p["s"] <= hi * 1.001
    import importlib.util
    spec = importlib.util.spec_from_file_location("population_stats", "scripts/population_stats.py")
    ps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ps)
    assert ps.KOPPARAPU == M.KOPPARAPU  # the page and the script use the same coefficients


def test_drake_monte_carlo_is_reproducible_and_honest():
    a, b = M.drake_mc(5000, 7), M.drake_mc(5000, 7)
    assert a == b and M.drake_mc(5000, 8) != a
    r = M.drake_mc()
    assert sum(r["share"].values()) == pytest.approx(1)
    widths = {k: (hi - lo) for k, _, lo, hi in M.DRAKE_TERMS}
    assert r["share"]["L"] == pytest.approx(widths["L"] ** 2 / sum(w * w for w in widths.values()))
    # The mean of log10 N is the sum of the range midpoints, so the median sits near it.
    mid = sum((lo + hi) / 2 for _, _, lo, hi in M.DRAKE_TERMS)
    assert r["median_log10"] == pytest.approx(mid, abs=0.3)
    assert 0 < r["p_lt_1"] < 1 and r["p05_log10"] < r["median_log10"] < r["p95_log10"]


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_drake_js_matches_python(tmp_path):
    script = _js_prelude(EX["planets"]).replace("const D = {methods: {", "const D = {methods: {drake_terms: " + json.dumps(M.DRAKE_TERMS) + ", ", 1)
    js = M.METHODS_JS
    script += js[js.index("function mxRand("):js.index("function mxSetup(")] + js[js.index("function mxDrakeMC("):js.index("MXV.drake = ")]
    script += "const r = mxDrakeMC(20000, 42, 10); console.log(JSON.stringify({median: r.median, p05: r.p05, p95: r.p95, pLt1: r.pLt1, share: r.share}));"
    f = tmp_path / "t.js"
    f.write_text(script)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    py = M.drake_mc()
    assert out["median"] == pytest.approx(py["median_log10"], abs=1e-9) and out["pLt1"] == py["p_lt_1"]
    assert out["p05"] == pytest.approx(py["p05_log10"], abs=1e-9) and out["share"] == pytest.approx(py["share"])


def test_new_chapters_state_their_limits(page_html):
    sec = _route(page_html, "methods")
    assert "speculative frameworks, not predictions" in sec and 'class="mxlabel spec">Speculative model' in sec
    assert "raw catalogue counts" in sec and "not occurrence rates" in sec
    assert "necessary, not sufficient" in sec and "drawn ten times deeper" in sec
    for flag in ("odd_even_mismatch", "secondary_eclipse", "low_snr", "too_short", "edge_event", "insufficient_points"):
        assert f"<code>{flag}</code>" in sec
    import setuhq.vet as vet
    src = Path(vet.__file__).read_text()
    for flag in ("odd_even_mismatch", "secondary_eclipse", "low_snr", "too_short", "edge_event", "insufficient_points"):
        assert f'"{flag}"' in src  # the page names flags vet.py really raises


def test_rv_jitter_view_uses_sourced_numbers(page_html):
    sec = _route(page_html, "methods")
    rv = sec.split('<article class="mxch" id="mx-rv"', 1)[1].split('<article class="mxch"', 1)[0]
    assert 'data-vis="jitter"' in rv and "ESPRESSO instrument floor, 10 cm/s" in rv and "a night at ESPRESSO, 25 cm/s" in rv
    assert "Pepe et al. 2021" in rv and "Fischer et al. 2016" in rv
    js = re.search(r"MXV\.jitter = .*?\n  \}\};", M.METHODS_JS, re.S).group(0)
    assert "mxK(365.25, 3.986004e14 / 1.2668653e17, 1, 0, 1)" in js  # the Earth twin's K from the formula
    assert "noise points illustrative" in js


# ---------- review of 5433c97: N1–N4 ----------
def test_rm_rows_name_their_sources(page_html):
    sec = _route(page_html, "methods")
    assert "both from Gaudi &amp; Winn 2007 Table 1, which lists 88 m/s" in sec
    # Triaud et al. 2009 Table 2: V sin I = 3.316 +0.017/−0.067 km/s, Rp/R★ = 0.15812, so K_R ≈ 83 m/s.
    assert M.rm_amplitude(3.316, 0.15812) == pytest.approx(82.9, abs=0.1)
    assert "V sin I = 3.316 +0.017/−0.067 km/s and k = 0.15812, measured by Triaud et al. 2009" in sec
    assert M.SOURCES["triaud09"][1] == "https://doi.org/10.1051/0004-6361/200911897" and M.SOURCES["triaud09"][1] in sec


def test_zenodo_anchor_is_short_and_both_fetch_dates_print(page_html):
    sec = _route(page_html, "methods")
    J, pop = M.load_jwst(), M.load_population()
    assert '<a href="https://doi.org/10.5281/zenodo.10161743" rel="noopener">Zenodo record 10161743</a>' in sec
    assert "Products and Models for &quot;A benchmark JWST near-infrared spectrum" in sec  # the full title stays in the sentence
    dates = re.search(r'<p class="note mxdates">.*?</p>', sec, re.S).group(0)
    assert f"fetched {pop['fetched_at'][:10]}" in dates and "population statistics" in dates
    assert f"Zenodo record 10161743, fetched {J['fetched_at'][:10]}" in dates


def test_phone_rv_ladder_axis_sits_below_the_rungs():
    css = M.METHODS_CSS
    base = css.index(".mxladder .mxaxis{position:absolute")
    phone = css.index(".mxladder .mxaxis{position:relative;width:60%;height:24px;margin-top:14px")
    assert phone > base  # later in the sheet, so it wins under 500 px
    assert "@media (max-width:499.98px)" in css[base:phone]


def test_the_stored_run_is_committed():
    # The site build (scripts/ci_local.sh) and the Sky test read this run, so a clean checkout must have it:
    # it is on disk and .gitignore re-includes it (no git needed, so this never skips).
    rules = Path(".gitignore").read_text().splitlines()
    assert "runs/*" in rules and "!runs/tess-pi-men-s1/" in rules and "runs/" not in rules
    for f in ("manifest.json", "candidates.json", "candidates.csv", "classifications.csv", "crossmatch.json"):
        assert Path("runs/tess-pi-men-s1", f).is_file(), f
    assert list(Path("runs/tess-pi-men-s1/subjects").glob("*.json"))


# ---------- round 11: the Radio chapter ----------
def test_radio_physics_and_its_js_twin():
    assert M.cyclotron_mhz(1) == pytest.approx(2.7992, abs=1e-4)  # eB/(2π m_e), the textbook 2.8 MHz/G
    assert M.field_for_mhz(M.cyclotron_mhz(123.4)) == pytest.approx(123.4)
    # PSR B1257+12 c: 0.013 MJ at 0.36 AU around 1.4 M☉ moves the pulsar's light-travel time by ~1.6 ms.
    assert M.pulsar_timing_ms(0.013, 0.36) == pytest.approx(0.013 * M.GM_JUP / (1.4 * M.GM_SUN) * 0.36 * M.AU / M.C_LIGHT * 1e3)
    assert 1.4 < M.pulsar_timing_ms(0.013, 0.36) < 1.8
    if HAVE_NODE:
        fn = re.search(r"function mxFce\(B\)\{.*?\}", M.METHODS_JS).group(0)
        out = subprocess.run(["node", "-e", fn + "console.log(JSON.stringify([1, 7.5, 1000].map(mxFce)))"], capture_output=True, text=True).stdout
        assert json.loads(out) == [pytest.approx(M.cyclotron_mhz(b), rel=1e-12) for b in (1, 7.5, 1000)]


def test_radio_chapter_labels_every_claim_and_keeps_seti_apart(page_html):
    sec = _route(page_html, "methods")
    art = re.search(r'<article class="mxch" id="mx-radio".*?(?=<article class="mxch"|$)', sec, re.S).group(0)
    assert "No exoplanet's own radio emission has been confirmed." in art.replace("&#x27;", "'")
    assert '<span class="mxlabel ill">Illustration</span>' in art and 'data-vis="radio"' in art
    claims = re.findall(r'<p class="mxstatus (\w+)">(.*?)</p><h4>(.*?)</h4>', art)
    assert [(c, h) for c, _, h in claims] == [("tent", "τ Boötis b · LOFAR"), ("cont", "GJ 1151 · LOFAR"), ("cand", "YZ Ceti · VLA")]
    assert "Tentative" in claims[0][1] and "Contested" in claims[1][1] and "Candidate" in claims[2][1]
    # The τ Boötis follow-up found nothing; GJ 1151's planet cannot be the source.
    assert "showed no bursty or slow emission (Turner et al. 2024)" in art and "very unlikely to be the source" in art
    seti = re.search(r'<section class="mxseti".*?</section>', art, re.S).group(0)
    assert "Not an exoplanet detection method" in seti and "zero candidates" in seti and "1,327 nearby stars" in seti
    for k in ("turner21", "turner24", "vedantham20", "blancopozo23", "pineda23", "wolszczan92", "price20", "isaacson17", "treumann06", "zarka98", "zarka07", "vanhaarlem13"):
        assert M.SOURCES[k][1].startswith("https://doi.org/10.") and M.SOURCES[k][1] in art, k
    # Numbers: the cut-off per gauss and the fields implied by each band, computed.
    assert f"{M.cyclotron_mhz(1):.3f} MHz" in art and f"≥ {M.field_for_mhz(14):.1f}–{M.field_for_mhz(21):.1f} G" in art
    # Pulsar timing, linked to the PSR B1257+12 card on the Galaxy tour.
    notable = [n["name"] for n in json.loads(Path("docs/results/notable_planets.json").read_text())["planets"]]
    assert f'<a href="/explore/galaxy/?tour={notable.index("PSR B1257+12 b") + 1}">Its card on the Galaxy tour ›</a>' in art
    assert "an assumed 1.4 M☉ pulsar (its mass is not stored) [calc]" in art
    assert ("radio", "Radio") in M.CHAPTERS



def test_radio_slider_announces_its_starting_value(page_html):
    art = re.search(r'<article class="mxch" id="mx-radio".*?(?=<article class="mxch"|$)', _route(page_html, "methods"), re.S).group(0)
    assert f'aria-valuetext="7.5 gauss, cyclotron cut-off {M.cyclotron_mhz(7.5):.1f} MHz"' in art
    assert "init(st){ st.opt.mode = 'aurora'; st.opt.B = 7.5; mxRadioLabel(st); }" in M.METHODS_JS


def test_every_time_scrubber_speaks_in_its_visuals_unit(page_html):
    sec = _route(page_html, "methods")
    figs = re.findall(r'<figure class="mxstage[^"]*" data-vis="(\w+)".*?</figure>', sec, re.S)
    bodies = re.findall(r'<figure class="mxstage[^"]*" data-vis="\w+".*?</figure>', sec, re.S)
    scrubs = [(v, re.search(r'class="mxscrub"[^>]*aria-valuetext="([^"]+)"', f).group(1)) for v, f in zip(figs, bodies) if 'class="mxscrub"' in f]
    assert len(scrubs) > 10 and all(t == f"t = 0.00 of the {M.TUNIT.get(v, 'cycle')}" for v, t in scrubs), scrubs
    animated = set(re.findall(r'data-vis="(\w+)"', sec)) - {"jwst", "atmlab", "valley", "hz", "drake"}
    assert animated <= set(M.TUNIT), animated - set(M.TUNIT)
    assert "sc.setAttribute('aria-valuetext', vt)" in M.METHODS_JS


# ---------- the redesign (phase 4): labels, the chapter cards, the fold, the false-positive case ----------
def test_label_art_exists_and_every_stage_call_passes_a_label():
    import ast

    assert M.LABEL_ART == "Artist's impression" and M.honesty_label(M.LABEL_ART) == '<span class="mxlabel art">Artist&#x27;s impression</span>'
    assert set(M.LABELS) == {M.LABEL_ART, M.LABEL_MODEL, M.LABEL_DATA, M.LABEL_ILL, M.LABEL_SPEC}
    tree = ast.parse(Path(M.__file__).read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_stage"]
    assert len(calls) >= 15
    for c in calls:
        lab = c.args[1] if len(c.args) > 1 else next((k.value for k in c.keywords if k.arg == "label"), None)
        assert isinstance(lab, ast.Name) and lab.id in ("LABEL_ILL", "LABEL_MODEL", "LABEL_DATA", "LABEL_SPEC", "LABEL_ART"), ast.dump(c)[:200]


def test_the_chapter_list_is_cards_with_the_chapters_star(page_html):
    sec = _route(page_html, "methods")
    toc = re.search(r'<nav class="mxtoc".*?</nav>', sec, re.S).group(0)
    cards = re.findall(r'<li><a href="[^"]+" data-ch="(\w+)">(.*?)</a></li>', toc, re.S)
    assert [c for c, _ in cards] == [c for c, _ in M.CHAPTERS]
    pm = EX["planets"]["pi Men c"]
    transit = dict(cards)["transit"]
    assert 'class="stardisc"' in transit and f"pi Men · {pm['star_teff']:,.0f} K" in transit


def test_the_transit_chapter_folds_pi_mens_light_curve_above_the_lab(page_html):
    art = re.search(r'<article class="mxch" id="mx-transit".*?(?=<article class="mxch")', _route(page_html, "methods"), re.S).group(0)
    assert art.index('class="stage foldfig"') < art.index('data-vis="system"')
    assert "Real data, cited" in art and "How a planet hides in the noise" in art


def test_the_false_positive_chapter_shows_toi_236():
    sec = M.methods_section(EX, None, {}, None, "", app={})
    art = re.search(r'<article class="mxch" id="mx-falsepos".*?(?=<article class="mxch")', sec, re.S).group(0)
    assert "TOI-236: secondary eclipse at SNR 10.9; all 6 dips rejected by vetting." in art
    assert "occulter not identified" in art and '<span class="stage-tag">Illustration</span>' in art
    assert "6,422 K" in art or "6,421 K" in art
    assert "confirmed" not in art.split("TOI-236", 1)[1].split("</figure>", 1)[0].replace("not confirmed", "")

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The deferred visuals: coronagraph families, per-mode molecular vibrations, the survey-scan intro on Sky and
Galaxy, the zoom lens into a system view, and astrometry's stated limits. Physics against closed forms first, then
the JavaScript twins, then the page and the browser."""
import json
import math
import re
import subprocess
from pathlib import Path

import pytest
from scipy.integrate import quad
from scipy.special import j1 as sp_j1, jv

from setuhq import docket as docket_mod
from setuhq import methods as M
from setuhq.app import APP_JS

from test_methods import CHROMIUM, HAVE_BROWSER, HAVE_NODE, PLAYWRIGHT, _route


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def page_html(pi_men_app):
    """The app built from the committed pi Men run: its star has a sky position and a known planet to zoom into."""
    return Path(pi_men_app).read_text()


def _chapter(page, cid):
    sec = _route(page, "methods")
    return sec.split(f'<article class="mxch" id="mx-{cid}"', 1)[1].split('<article class="mxch"', 1)[0]


# ---------- optics: closed forms ----------
def test_bessel_functions_and_the_airy_pattern():
    for n in range(5):
        for x in (0.0, 0.01, 0.7, 2.4048, 3.0, 4.9, 7.99, 8.01, 12.6, 31.4):
            assert M.bessel_j(n, x) == pytest.approx(jv(n, x), abs=2e-7), (n, x)
    # First dark ring of a clear circular pupil at 1.2197 λ/D (the first zero of J1 is 3.8317), first bright ring
    # at 1.635 λ/D with 1.75% of the peak.
    assert M.airy_intensity(3.831706 / math.pi) == pytest.approx(0, abs=1e-12)
    ring = max(M.airy_intensity(1.5 + i / 1000) for i in range(300))
    assert ring == pytest.approx(0.0175, abs=2e-4)
    assert M.airy_intensity(0) == 1.0


def test_sonine_apodiser_matches_its_hankel_transform_and_throughput():
    for n in (0, 1, 2, 3):
        # Field = the normalised Hankel transform of (1 − ρ²)ⁿ, done numerically.
        for u in (0.5, 1.3, 2.7, 5.0):
            k = math.pi * u
            num = quad(lambda r: (1 - r * r) ** n * jv(0, k * r) * r, 0, 1, limit=200)[0] / quad(lambda r: (1 - r * r) ** n * r, 0, 1)[0]
            assert M.sonine_field(u, n) == pytest.approx(num, abs=1e-7), (n, u)
        # Throughput 1/(2n + 1) and on-axis intensity 1/(n + 1)² of the clear pupil's.
        assert M.sonine_throughput(n) == pytest.approx(2 * quad(lambda r: (1 - r * r) ** (2 * n) * r, 0, 1)[0])
        assert M.sonine_intensity(0, n) == pytest.approx(1 / (n + 1) ** 2)
    assert M.sonine_field(1.0, 0) ** 2 == pytest.approx(M.airy_intensity(1.0))   # n = 0 is the clear pupil
    # The point of apodising: the brightest ring near 5 λ/D falls by more than 100×.
    _, _, _, airy5, son5 = M.coronagraph_numbers()
    assert airy5 / son5 > 100


def test_lyot_plane_is_bright_at_the_rim_and_the_stop_removes_it():
    m = M.MX_LYOT_MASK
    # On axis the Lyot-plane field is exactly J0(πm): 1 − ∫₀^{πm} J1 dk.
    assert M.lyot_pupil_field(0.0, m) == pytest.approx(jv(0, math.pi * m), abs=1e-6)
    rim = sum(M.lyot_pupil_field(r, m) ** 2 for r in (0.97, 0.98, 0.99, 1.01, 1.02, 1.03)) / 6
    inner = sum(M.lyot_pupil_field(r / 20, m) ** 2 for r in range(16)) / 16
    assert rim > 5 * inner
    # Without a mask nothing is removed: the field is the pupil.
    assert M.lyot_pupil_field(0.5, 0) == pytest.approx(1.0) and M.lyot_pupil_field(1.2, 0) == pytest.approx(0.0)
    lyot_open, lyot_closed, airy8, _, _ = M.coronagraph_numbers()
    assert lyot_closed < lyot_open / 100   # the stop does the work beside the mask
    assert lyot_open < 2 * airy8           # the mask alone barely helps at 8 λ/D
    assert airy8 == pytest.approx(M.airy_intensity(8))


def test_vortex_lyot_plane_is_dark_inside_the_pupil():
    for rho in (0.3, 0.6, 0.85, 1.3, 1.6, 2.2):
        num = quad(lambda k: sp_j1(k) * jv(2, k * rho), 0, 400, limit=4000)[0]
        assert M.vortex_pupil_field(rho) == pytest.approx(num, abs=0.012), rho
    with pytest.raises(ValueError):
        M.vortex_pupil_field(0.5, charge=4)


def _js_physics():
    js = M.METHODS_JS
    rand = js[js.index("function mxRand("):js.index("\n", js.index("function mxRand("))]
    return "const D = {methods: null};\n" + js[:js.index("// ---------- stages")] + rand + "\n"


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_js_optics_and_adi_twins(tmp_path):
    script = _js_physics() + """
const out = {J: [], airy: [], son: [], lp: [], lf: []};
for (let n = 0; n < 5; n++) for (const x of [0.01, 0.7, 3.0, 7.99, 8.01, 12.6]) out.J.push(mxJn(n, x));
for (const u of [0, 0.7, 1.2197, 3.3, 8]) out.airy.push(mxAiry(u));
for (const n of [0, 1, 2]) for (const u of [0, 1.1, 2.5, 5]) out.son.push(mxSonineI(u, n));
for (const r of [0, 0.4, 0.95, 1.05, 1.3]) out.lp.push(mxLyotPupil(r, 4));
const T = mxLyotTable(4); for (const [u, s] of [[2, 1.5], [6, 1.0], [8, 1.5], [8, 0.8], [10, 0.9]]) out.lf.push(mxLyotFinal(T, u, s));
const A = mxAdi(17); out.adi = {raw: A.snrRaw, last: A.snr[A.N - 1], first: A.snr[0], N: A.N, rot: A.ang[A.N - 1], px: A.px, py: A.py, G: A.G};
let best = -1e9, at = [0, 0]; const S = A.stacks[A.N - 1]; for (let j = 0; j < A.G; j++) for (let i = 0; i < A.G; i++) if (S[j * A.G + i] > best){ best = S[j * A.G + i]; at = [i, j]; }
out.adi.peak = at;
console.log(JSON.stringify(out));"""
    f = tmp_path / "t.js"
    f.write_text(script)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    xs = [(n, x) for n in range(5) for x in (0.01, 0.7, 3.0, 7.99, 8.01, 12.6)]
    assert out["J"] == [pytest.approx(M.bessel_j(n, x), abs=1e-12) for n, x in xs]
    assert out["airy"] == [pytest.approx(M.airy_intensity(u), abs=1e-12) for u in (0, 0.7, 1.2197, 3.3, 8)]
    assert out["son"] == [pytest.approx(M.sonine_intensity(u, n), abs=1e-12) for n in (0, 1, 2) for u in (0, 1.1, 2.5, 5)]
    assert out["lp"] == [pytest.approx(M.lyot_pupil_field(r, 4), abs=1e-9) for r in (0, 0.4, 0.95, 1.05, 1.3)]
    # The page draws the final image from a tabulated Lyot plane: within 5% of the direct integral.
    for v, (u, s) in zip(out["lf"], [(2, 1.5), (6, 1.0), (8, 1.5), (8, 0.8), (10, 0.9)]):
        assert v == pytest.approx(M.lyot_final_intensity(u, 4, s), rel=0.05, abs=1e-8), (u, s)
    # ADI on the synthetic frames: the planet emerges where it belongs, far above one raw frame.
    a = out["adi"]
    assert a["N"] == 24 and a["rot"] == pytest.approx(60)
    assert a["last"] > 8 and a["last"] > 5 * a["raw"] and a["last"] > a["first"]
    assert math.hypot(a["peak"][0] - a["px"], a["peak"][1] - a["py"]) < 2
    assert re.search(r"lyotMask: (\d+)", M.METHODS_JS).group(1) == str(M.MX_LYOT_MASK)


# ---------- molecules: modes, bands, amplitudes ----------
ATLAS_M1 = {  # the atlas's M1 fundamentals (µm), as tabulated there
    "H2O": [2.73, 6.27, 2.66], "CO2": [7.50, 15.0, 4.26], "CO": [4.67], "O2": [6.43], "O3": [9.01, 14.2, 9.60],
    "SO2": [8.69, 19.3, 7.34], "N2O": [4.50, 7.78, 17.0], "NH3": [3.00, 10.5, 2.90, 6.15], "PH3": [4.30, 10.1, 4.30, 8.94],
    "CH4": [None, None, 3.31, 7.66],
}


def test_mode_counts_bands_and_infrared_activity():
    mols = {m["id"]: m for m in M.MOLECULES}
    assert set(M.MODES) == set(ATLAS_M1)
    for mid, modes in M.MODES.items():
        m = mols[mid]
        n_atoms = len(M.atom_positions(m["geom"]))
        linear = m["geom"]["shape"] in ("linear", "diatomic")
        assert sum(d[4] for d in modes) == 3 * n_atoms - (5 if linear else 6), mid
        assert [d[2] for d in modes] == ATLAS_M1[mid], mid
        nums = [float(x) for x in re.findall(r"\d+\.\d+|\d+", m["bands"])]
        for _, _, um, _, _, _ in modes:
            if um is not None:   # every animated band is on the molecule's card, too
                assert any(abs(um - v) <= 0.05 for v in nums), (mid, um, m["bands"])
    silent = {(mid, d[0]) for mid, ms in M.MODES.items() for d in ms if not d[3]}
    assert silent == {("CO2", "ν₁"), ("O2", "ν"), ("CH4", "ν₁"), ("CH4", "ν₂")}
    assert "DMS" not in M.MODES and "Na" not in M.MODES   # no modes invented where the atlas gives none


def test_modes_link_to_the_bands_reading_atmospheres_draws():
    links = {(mid, d[2]): M.mode_band_link(mid, d[2]) for mid, ms in M.MODES.items() for d in ms}
    assert links[("H2O", 2.73)][0] == 2.7 and links[("H2O", 2.66)][0] == 2.7
    assert links[("CH4", 3.31)][0] == 3.3 and links[("CO2", 4.26)][0] == 4.26 and links[("CO", 4.67)][0] == 4.67
    assert links[("CO2", 15.0)] is None and links[("H2O", 6.27)] is None
    # Every infrared fundamental band that chapter draws is made by a mode here.
    for sp, lam, note in M.BANDS:
        if "fundamental" in note or "ν₃" in note:
            assert any(v and v[0] == lam for v in links.values()), (sp, lam)


def test_mode_displacements_are_internal_vibrations():
    for m in (m for m in M.MOLECULES if m["id"] in M.MODES):
        P = M.atom_positions(m["geom"])
        mass = [M.ATOM_MASS[p[0]] for p in P]
        tot = sum(mass)
        com = [sum(mass[i] * P[i][k + 1] for i in range(len(P))) / tot for k in range(3)]
        for row in M.mode_table(m):
            d = row["disp"]
            assert max(math.sqrt(sum(x * x for x in v)) for v in d) == pytest.approx(1, abs=1e-5)
            for k in range(3):   # no translation
                assert abs(sum(mass[i] * d[i][k] for i in range(len(P)))) < 1e-4, (m["id"], row["name"])
            ang = [0.0, 0.0, 0.0]   # no rotation (about the centre of mass)
            for i in range(len(P)):
                r = [P[i][k + 1] - com[k] for k in range(3)]
                ang[0] += mass[i] * (r[1] * d[i][2] - r[2] * d[i][1])
                ang[1] += mass[i] * (r[2] * d[i][0] - r[0] * d[i][2])
                ang[2] += mass[i] * (r[0] * d[i][1] - r[1] * d[i][0])
            assert max(abs(a) for a in ang) < 1e-4, (m["id"], row["name"])
    co2 = {r["nu"]: r["disp"] for r in M.mode_table(next(m for m in M.MOLECULES if m["id"] == "CO2"))}
    assert co2["ν₁"][0] == pytest.approx([0, 0, 0], abs=1e-6)          # the carbon stays put in the symmetric stretch
    assert co2["ν₁"][1][0] == pytest.approx(-co2["ν₁"][2][0])          # the oxygens move apart
    assert co2["ν₃"][1][0] == pytest.approx(co2["ν₃"][2][0])           # ...and together in the asymmetric stretch
    h2o = {r["nu"]: r["disp"] for r in M.mode_table(M.MOLECULES[0])}
    assert h2o["ν₁"][1][0] == pytest.approx(-h2o["ν₁"][2][0]) and h2o["ν₁"][1][1] == pytest.approx(h2o["ν₁"][2][1])  # mirror-symmetric


def test_zero_point_amplitude_and_stated_exaggeration():
    # A diatomic in closed form: the bond's zero-point RMS is √(ħ/2μω); the carbon carries m_O/M of it.
    co = next(m for m in M.MOLECULES if m["id"] == "CO")
    row = M.mode_table(co)[0]
    mc, mo = M.ATOM_MASS["C"] * M.AMU, M.ATOM_MASS["O"] * M.AMU
    mu, w = mc * mo / (mc + mo), 2 * math.pi * M.C_LIGHT / 4.67e-6
    assert row["rms"] == pytest.approx(math.sqrt(M.HBAR / (2 * mu * w)) * mo / (mc + mo) * 1e10, abs=6e-5)   # stored to 4 decimals
    assert row["atom"] == "C" and row["exag"] == round(M.MODE_DRAW_A / row["rms"])
    for m in M.MOLECULES:
        for r in M.mode_table(m):
            if r["um"] is None:
                assert "exag" not in r
            else:   # zero-point motion is a few hundredths of an ångström; the drawing says by how much it is enlarged
                assert 0.01 < r["rms"] < 0.1 and 2 <= r["exag"] <= 20, (m["id"], r)


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_js_atom_positions_match_python(tmp_path):
    js = M.METHODS_JS
    atoms_fn = js[js.index("function mxAtoms(g){"):js.index("// Each normal mode (methods.py: mode_table)")]
    script = atoms_fn + f"\nconsole.log(JSON.stringify({json.dumps([m['geom'] for m in M.MOLECULES])}.map(mxAtoms)));"
    f = tmp_path / "a.js"
    f.write_text(script)
    out = json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)
    for m, got in zip(M.MOLECULES, out):
        want = M.atom_positions(m["geom"])
        assert [g[0] for g in got] == [w[0] for w in want]
        for g, w in zip(got, want):
            assert g[1:] == [pytest.approx(v, abs=1e-12) for v in w[1:]]


# ---------- the page ----------
def test_blocking_starlight_has_the_four_families_and_a_plate(page_html):
    art = _chapter(page_html, "imaging")
    fig = re.search(r'<figure class="mxstage tall" data-vis="cgfam">.*?</figure>', art, re.S).group(0)
    assert '<span class="mxlabel ill">Illustration</span>' in fig
    for v in ("lyot", "apod", "vortex", "adi"):
        assert f'<option value="{v}">' in fig
    plate = re.search(r'<figure class="mxplate">.*?</figure>', art, re.S).group(0)
    assert plate.count("<svg") == 2 and plate.count('role="img"') == 2   # wide and phone drawings
    assert '<span class="mxlabel ill">Illustration</span>' in plate and "not to scale" in plate
    for t in ("A · objective", "B · occulting disc", "D · Lyot stop", "F · image"):
        assert plate.count(t) == 2
    lyot_open, lyot_closed, airy8, airy5, son5 = M.coronagraph_numbers()
    for x in (lyot_open, lyot_closed, airy8, airy5, son5):
        assert M.sci(x) in art
    assert M.sci(1.83e-7) == "1.8×10⁻⁷" and M.sci(6.68e-5) == "6.7×10⁻⁵" and M.sci(9.97e-3) == "1.0×10⁻²"
    assert not re.search(r"\d\.\de[-+]\d", art)   # no e-notation in the chapter's prose
    assert "Marois et al. 2006" in art and "Bailey et al. 2016" in art and "Lyot 1939" in art
    assert "synthetic" in art and "illustrative" in art
    assert not re.search(r"0\.9 λ/D|1\.75 λ/D", art)   # the atlas flags the vortex IWA figures as unchecked
    # Every drawing states its stretch and that its sizes are illustrative.
    js = M.METHODS_JS[M.METHODS_JS.index("MXV.cgfam = "):M.METHODS_JS.index("// ---------- reading atmospheres")]
    assert js.count("st.exag = ") == 4 and "log intensity stretch" in js and "synthetic frames" in js


def test_molecules_chapter_animates_modes_linked_to_bands(page_html):
    art = _chapter(page_html, "molecules")
    sel = re.search(r'<select data-ctl="mode">(.*?)</select>', art, re.S).group(1)
    assert sel.count("<option") == 3 and "ν₁ symmetric stretch · 2.73 µm" in sel and "ν₂ bend · 6.27 µm" in sel
    co2 = art.split('data-mol="CO2"', 1)[1].split("</article>", 1)[0]
    assert "ν₁ symmetric stretch</b> · 7.50 µm · infrared-silent" in co2
    assert '<a href="#/methods?ch=spectroscopy">the 4.26 µm band in Reading atmospheres ›</a>' in co2
    assert "beyond the 0.5–5.1 µm window" in co2
    h2o = art.split('data-mol="H2O"', 1)[1].split("</article>", 1)[0]
    assert h2o.count("the 2.7 µm band in Reading atmospheres") == 2
    assert "3N − 6" in art and "zero-point" in art and "not a force-field calculation" in art
    meta = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page_html, re.S).group(1))
    assert meta["methods"]["molecules"][0]["modes"] == json.loads(json.dumps(M.mode_table(M.MOLECULES[0])))
    spec = _chapter(page_html, "spectroscopy")
    assert 'href="#/methods?ch=molecules">Which vibration makes each band ›' in spec


def test_astrometry_quotes_no_gaia_precision(page_html):
    art = _chapter(page_html, "astrometry")
    assert "holds no sourced per-measurement figure for Gaia DR3" in art
    assert '<span class="mxlabel ill">Illustration</span>' in art
    assert not re.search(r"(?i)DR3[^.<]{0,60}\d+(\.\d+)?\s*(µas|mas)", art)


def test_intro_and_zoom_contract():
    js = M.METHODS_JS
    start = re.search(r"function mxIntroStart\(key, host\)\{.*?\n\}\n", js, re.S).group(0)
    assert "mxRM.matches" in start.split("\n")[1]   # never under reduced motion
    assert "Skip intro" in start and "sessionStorage" in start
    live = re.search(r"const mxIntroLive = .*", js).group(0)
    assert "I.visible" in live and "document.hidden" in live and "current === I.key" in live   # on-screen, shown routes only
    css = M.METHODS_CSS
    assert re.search(r"\.mxintro\{[^}]*pointer-events:none", css) and re.search(r"\.mxintro \.mxskip\{[^}]*pointer-events:auto;min-height:44px", css)
    assert "@media (prefers-reduced-motion: reduce){.mxintro{display:none}" in css
    assert "if (from && !mxRM.matches && dlg.animate) mxZoomLens(dlg, from, z);" in js
    assert "an illustration of scale, not continuous data</span>" in js and "The zoom between them is an illustration of scale, not continuous data." in js
    assert "mxIntroRoute(r);" in APP_JS and "gxScreenPoint(gx.sel)" in APP_JS and "kind: 'sky'" in APP_JS


def test_sky_marker_is_a_zoom_target(page_html):
    sky = _route(page_html, "sky")
    assert '<g class="skymark" data-zoom="pi Men c">' in sky
    assert re.search(r'<button class="btn skyzoom" type="button" data-zoom="pi Men c" hidden>Zoom into the pi Men c system ›</button>', sky)


# ---------- the browser ----------
@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_intro_zoom_and_new_stages_in_the_browser(pi_men_app, tmp_path):
    page = pi_men_app   # read only
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist', '--allow-file-access-from-files'] });
  const url = %s, out = {};
  const ctx = async (o) => { const c = await b.newContext(o); const p = await c.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); return [c, p, errs]; };
  // 1. The intro on the Sky: shown, skippable, no pointer capture, and it stops when the section is left.
  {
    const [c, p, errs] = await ctx({viewport: {width: 1360, height: 900}});
    await p.goto(url + '#/sky'); await p.waitForTimeout(700);
    out.sky = await p.evaluate(() => { const el = document.querySelector('#route-sky .mxintro'), I = mxIntros.sky, sk = el.querySelector('.mxskip').getBoundingClientRect();
      const cv = el.querySelector('canvas'), d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data; let lit = 0; for (let i = 0; i < d.length; i += 4 * 97) if (d[i] + d[i + 1] + d[i + 2] > 60) lit++;
      return {there: !!el, frames: I.frames, pe: getComputedStyle(el).pointerEvents, cvpe: getComputedStyle(cv).pointerEvents, skip: [sk.width, sk.height], lit, label: el.querySelector('.mxlabel').textContent}; });
    await p.goto(url + '#/overview'); await p.waitForTimeout(300);
    out.left = await p.evaluate(() => ({done: mxIntros.sky.done, raf: mxIntros.sky.raf, f: mxIntros.sky.frames}));
    await p.waitForTimeout(400);
    out.left.f2 = await p.evaluate(() => mxIntros.sky.frames);
    await p.goto(url + '#/sky'); await p.waitForTimeout(300);
    out.again = await p.evaluate(() => !!document.querySelector('#route-sky .mxintro'));   // once per session
    // The zoom from the sky marker: a lens animation into the system view, labelled.
    await p.click('#route-sky .skyzoom'); await p.waitForTimeout(120);
    out.zoom = await p.evaluate(() => { const d = document.querySelector('#mxsheet'); return {open: d.open, anim: d.getAnimations().length, lens: !!d.querySelector('.mxlens'), label: (d.querySelector('.mxlens span') || {}).textContent, note: document.querySelector('#mxsheetzoom').textContent, title: document.querySelector('#mxsheettitle').textContent}; });
    await p.keyboard.press('Escape'); await p.waitForTimeout(1200);
    out.zoom.after = await p.evaluate(() => ({lens: !!document.querySelector('#mxsheet .mxlens'), open: document.querySelector('#mxsheet').open}));
    out.skyErrs = errs; await c.close();
  }
  // 2. The Galaxy intro is skipped by its button; the Galaxy's zoom starts at the selected star.
  {
    const [c, p, errs] = await ctx({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true});
    await p.goto(url + '#/galaxy'); await p.waitForFunction(() => typeof gx !== 'undefined' && gx.ready, null, {timeout: 20000}); await p.waitForTimeout(300);
    const before = await p.evaluate(() => !!document.querySelector('#gxstage .mxintro'));
    await p.click('#gxstage .mxskip'); await p.waitForTimeout(600);
    out.gal = {before, after: await p.evaluate(() => ({gone: !document.querySelector('#gxstage .mxintro'), done: mxIntros.galaxy.done, wide: document.documentElement.scrollWidth > document.documentElement.clientWidth}))};
    await p.evaluate(() => { const nt = gx.G.notable.find(n => n.name === 'pi Men c') || gx.G.notable.find(n => MX.examples[n.name]); gxSelect(nt.host, nt.planet); });
    await p.waitForTimeout(200);
    const name = await p.evaluate(() => document.querySelector('#gxcard button[data-gxsys]').dataset.gxsys);
    await p.click(`#gxcard button[data-gxsys="${name}"]`); await p.waitForTimeout(150);
    out.gal.zoom = await p.evaluate(() => ({open: document.querySelector('#mxsheet').open, anim: document.querySelector('#mxsheet').getAnimations().length, note: document.querySelector('#mxsheetzoom').textContent}));
    out.galErrs = errs; await c.close();
  }
  // 2b. Skip intro announces, by mouse and by keyboard.
  out.skip = {};
  for (const how of ['click', 'enter']) {
    const [c, p] = await ctx({viewport: {width: 1360, height: 900}});
    await p.goto(url + '#/sky'); await p.waitForTimeout(400);
    if (how === 'click') await p.click('#route-sky .mxskip'); else { await p.focus('#route-sky .mxskip'); await p.keyboard.press('Enter'); }
    await p.waitForTimeout(300);
    out.skip[how] = await p.evaluate(() => document.querySelector('#announce').textContent);
    await c.close();
  }
  // 3. Reduced motion: no intro at all, and the sheet opens without the lens (the note still says what the zoom is).
  {
    const [c, p, errs] = await ctx({viewport: {width: 1360, height: 900}, reducedMotion: 'reduce'});
    await p.goto(url + '#/sky'); await p.waitForTimeout(500);
    out.rm = {intro: await p.evaluate(() => !!document.querySelector('.mxintro'))};
    await p.click('#route-sky .skyzoom'); await p.waitForTimeout(150);
    Object.assign(out.rm, await p.evaluate(() => { const d = document.querySelector('#mxsheet'); return {open: d.open, anim: d.getAnimations().length, lens: !!d.querySelector('.mxlens'), note: document.querySelector('#mxsheetzoom').hidden ? '' : document.querySelector('#mxsheetzoom').textContent}; }));
    await p.goto(url + '#/galaxy'); await p.waitForTimeout(800);
    out.rm.galIntro = await p.evaluate(() => !!document.querySelector('.mxintro'));
    out.rmErrs = errs; await c.close();
  }
  // 4. Every coronagraph family and every molecule's modes draw at both widths without errors.
  out.stages = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) {
    const [c, p, errs] = await ctx({viewport: {width: w, height: h}, isMobile: mob, hasTouch: mob});
    await p.goto(url + '#/methods?ch=imaging'); await p.waitForTimeout(500);
    const cg = await p.evaluate(() => { const fig = document.querySelector('#mx-imaging figure[data-vis="cgfam"]'), sel = fig.querySelector('.mxctl select:not(.mxspeed select)'), st = fig._mx, r = [];
      for (const f of ['lyot', 'apod', 'vortex', 'adi']) for (const t of [0.05, 0.3, 0.55, 0.85]) { sel.value = f; sel.dispatchEvent(new Event('change')); st.t = t; mxDraw(st);
        const d = st.ctx.getImageData(0, 0, st.cv.width, st.cv.height).data; let lit = 0; for (let i = 0; i < d.length; i += 4 * 97) if (d[i] + d[i + 1] + d[i + 2] > 60) lit++; r.push([f, t, lit, st.exag]); }
      return r; });
    await p.goto(url + '#/methods?ch=molecules'); await p.waitForTimeout(400);
    const mol = await p.evaluate(() => { const fig = document.querySelector('#mx-molecules figure[data-vis="molecule"]'), st = fig._mx, ms = fig.querySelector('select[data-ctl="mode"]'), mm = fig.querySelector('.mxctl select:not(.mxspeed select):not([data-ctl])'), r = [];
      for (const m of MX.molecules){ mm.value = m.id; mm.dispatchEvent(new Event('change'));
        const n = (m.modes || []).length; if (ms.options.length !== Math.max(1, n) || ms.disabled !== !n) r.push(['options', m.id, ms.options.length]);
        for (let k = 0; k < Math.max(1, n); k++){ ms.value = String(k); ms.dispatchEvent(new Event('change')); for (const t of [0.15, 0.4]){ st.t = t; mxDraw(st); }
          const md = (m.modes || [])[k]; if (md && md.exag && !st.exag.includes('amplitude ×' + md.exag)) r.push(['exag', m.id, k, st.exag]); } }
      // The chosen mode index survives a change of molecule where the new one has it (H2O ν₃ → CO2 ν₃), else resets.
      mm.value = 'H2O'; mm.dispatchEvent(new Event('change')); ms.value = '2'; ms.dispatchEvent(new Event('change'));
      mm.value = 'CO2'; mm.dispatchEvent(new Event('change')); if (st.opt.mode !== 2 || ms.value !== '2') r.push(['keep', st.opt.mode, ms.value]);
      mm.value = 'CO'; mm.dispatchEvent(new Event('change')); if (st.opt.mode !== 0 || ms.value !== '0') r.push(['reset', st.opt.mode, ms.value]);
      return r; });
    out.stages.push({w, cg, mol, errs, wide: await p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)});
    await c.close();
  }
  console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(Path(page).resolve().as_uri())))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    s = out["sky"]
    assert s["there"] and s["frames"] > 3 and s["lit"] > 5 and s["label"] == "Illustration"
    assert s["pe"] == "none" and s["cvpe"] == "none" and s["skip"][0] >= 44 and s["skip"][1] >= 44
    assert out["left"]["done"] is True and out["left"]["raf"] == 0 and out["left"]["f2"] == out["left"]["f"]   # no frames off its route
    assert out["again"] is False
    z = out["zoom"]
    assert z["open"] and z["anim"] >= 1 and z["lens"] and z["title"] == "pi Men c"
    assert "an illustration of scale, not continuous data" in z["label"] and "zoom ≈ ×4×10⁸ · " in z["label"]   # 3.6×10⁸, one significant figure
    assert "From the sky map to this orbit is a jump of about 4×10⁸ in scale" in z["note"] and "not continuous data" in z["note"]
    assert z["after"] == {"lens": False, "open": False}
    g = out["gal"]
    assert g["before"] and g["after"] == {"gone": True, "done": True, "wide": False}
    assert g["zoom"]["open"] and g["zoom"]["anim"] >= 1 and "From the Galaxy map to this orbit is a jump of about 6×10⁷ in scale" in g["zoom"]["note"]
    assert out["skip"] == {"click": "Intro skipped.", "enter": "Intro skipped."}
    rm = out["rm"]
    assert rm["intro"] is False and rm["galIntro"] is False
    assert rm["open"] and rm["anim"] == 0 and rm["lens"] is False and "not continuous data" in rm["note"]
    assert out["skyErrs"] == [] and out["galErrs"] == [] and out["rmErrs"] == []
    for st in out["stages"]:
        assert st["errs"] == [] and st["wide"] is False, st
        assert all(lit > 5 and exag for _, _, lit, exag in st["cg"]), st["cg"]
        assert st["mol"] == [], st["mol"]

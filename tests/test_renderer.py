# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""setuhq.renderer: the page's twins of the Python physics and look rules agree exactly, the static star disc is
teff_rgb x I(r), the element contract holds, and the committed stills were drawn by the current code and table."""

import hashlib
import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import looks as L
from setuhq import methods as M
from setuhq import renderer as R
from setuhq.i18n import unkey

ROOT = Path(__file__).resolve().parents[1]
HAVE_NODE = shutil.which("node") is not None
CAT = json.loads((ROOT / "docs/results/exoplanet_catalogue.json").read_text())

# Just enough of a browser for the renderer to load in node (no canvas: it never draws here).
SHIM = """
globalThis.window = globalThis;
const noop = () => {};
globalThis.matchMedia = () => ({matches: false});
globalThis.addEventListener = noop;
globalThis.document = {createElement: () => ({getContext: () => null, addEventListener: noop}), addEventListener: noop,
  readyState: 'complete', querySelectorAll: () => [], documentElement: {dataset: {}}, hidden: false};
globalThis.requestIdleCallback = noop;
"""


def _node(tmp_path, body: str):
    f = tmp_path / "t.js"
    f.write_text(SHIM + R.render_js() + "\n" + body)
    out = subprocess.run(["node", str(f)], capture_output=True, text=True, check=True, timeout=120).stdout
    return json.loads(out)


def _mx_teff_js() -> str:
    js = M.METHODS_JS
    g = js[js.index("function mxG("):js.index("\n", js.index("function mxG("))]
    a = js.index("function mxTeffRGB(")
    return g + "\n" + js[a:js.index("\n}\n", a) + 3]


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_star_colour_twins_agree_exactly(tmp_path):
    temps = list(range(1000, 40001, 100))
    out = _node(tmp_path, _mx_teff_js() + f"""
const T = {json.dumps(temps)};
console.log(JSON.stringify({{r: T.map(t => SetuRender.teffRGB(t)), mx: T.map(t => mxTeffRGB(t))}}));""")
    py = [list(L.teff_rgb(t)) for t in temps]
    assert out["r"] == py and out["mx"] == py
    assert M.teff_rgb is L.teff_rgb
    ratio = [L.teff_rgb(t)[2] / L.teff_rgb(t)[0] for t in range(2500, 10001, 100)]
    assert all(b > a for a, b in zip(ratio, ratio[1:]) if a < 1 and b < 1) and ratio[-1] > ratio[0]
    br = [L.teff_rgb(t)[2] / max(1, L.teff_rgb(t)[0]) for t in range(2500, 10001, 100)]
    assert all(b >= a for a, b in zip(br, br[1:])) and br[-1] > br[0]  # bluer as it gets hotter


def _rows() -> list[dict]:
    P = CAT["planets"]
    rng = random.Random(20261022)
    idx = rng.sample(range(len(P["name"])), 500)
    rows = [L.row(CAT, i) for i in idx]
    # Every boundary, by radius, mass, minimum mass and Teq, and the missing-input cases.
    for re_ in (1.5999, 1.6, 3.999, 4.0, 9.999, 10.0):
        rows.append({"radius": re_ / L.RJ_IN_RE, "teq": 500})
    for me in (1.99, 2, 9.99, 10, 49.9, 50):
        rows += [{"mass": me / L.MJ_IN_ME, "teq": 300}, {"msini": me / L.MJ_IN_ME}]
    for t in (199.9, 200, 349.9, 350, 999.9, 1000, 1999.9, 2000):
        rows.append({"radius": 0.3, "teq": t})
    rows += [{}, {"radius": None, "mass": None}, {"radius": 0.1, "srad": 1, "steff": 5772, "smass": 1, "period": 365.25},
             {"radius": "x"}, {"radius": 0}, {"radius": -1, "mass": 0.01}]
    return rows


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_look_twin_agrees_on_catalogue_rows_and_every_boundary(tmp_path):
    rows = _rows()
    out = _node(tmp_path, f"const rows = {json.dumps(rows)};\nconsole.log(JSON.stringify(rows.map(r => SetuRender.look(r))));")
    for row, js in zip(rows, out):
        py = L.look(row)
        for k in ("name", "composition", "band", "by", "teq_source", "to_scale", "neutral", "reasons"):
            assert js[k] == py[k], (row, k, js[k], py[k])
        # Rounded for the page (to 4, 3, 4 and 1 decimals): the last digit may round either way.
        for k, d in (("rp_re", 4), ("mp_me", 3), ("s", 4), ("teq", 1)):
            assert (js[k] is None) == (py[k] is None) and (js[k] is None or js[k] == pytest.approx(py[k], abs=1.01 * 10 ** -d)), (row, k)


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_transit_flux_and_limb_darkening_twins(tmp_path):
    grid = [(z, k, u1, u2) for z in (0, 0.3, 0.8, 0.95, 1.0, 1.05, 1.2, 2.0) for k in (0.01, 0.1, 0.3)
            for u1, u2 in ((0.3, 0.2), (0.5, 0.15), (0.17, 0.5))]
    teffs = [2500, 3000, 3386, 4400, 5772, 6421, 9000, 12000]
    out = _node(tmp_path, f"""const G = {json.dumps(grid)}, T = {json.dumps(teffs)};
console.log(JSON.stringify({{f: G.map(g => SetuRender.transitFlux(...g)), ld: T.map(t => SetuRender.ldCoeffs(t)), fnv: SetuRender.fnv('pi-men-c')}}));""")
    for v, g in zip(out["f"], grid):
        assert v == pytest.approx(M.transit_flux(*g), abs=1e-12)
    for v, t in zip(out["ld"], teffs):
        assert v == pytest.approx(list(M.ld_coeffs(t)), abs=1e-12)
    assert out["fnv"] == L.seed("pi-men-c")


def test_the_static_star_disc_is_teff_rgb_times_limb_darkening():
    teff = 5992
    stops = R.star_svg_stops(teff)
    rgb, (u1, u2) = L.teff_rgb(teff), M.ld_coeffs(teff)
    for i, s in enumerate(stops):
        assert s == tuple(round(c * M.ld_intensity(min(i / 10, 0.999), u1, u2)) for c in rgb)
    svg = R.star_svg(teff, 28, uid="t")
    assert len(svg) <= 700 and 'aria-hidden="true"' in svg and svg.count("<stop ") == 11
    assert f'stop-color="#{"".join(f"{c:02x}" for c in stops[0])}"' in svg
    assert 'role="img" aria-label="A star"' in R.star_svg(teff, 28, uid="t", label="A star")


def test_the_element_contract():
    fig = R.figure("planet", {"look": "envelope-hot", "seed": L.seed("pi-men-c"), "rp_re": 1.874, "teq": 1179},
                   "Artist's impression of pi Men c: an envelope planet in the hot band, 1.87 Earth radii, 1,179 K.",
                   "Artist's impression · envelope, hot · …", uid="x")
    fig = unkey(fig)
    assert fig.startswith('<figure class="stage rfig" data-render="planet" data-params=') and 'aria-labelledby="cap-x"' in fig
    assert re.search(r'<img class="rstill" src="/assets/render/[0-9a-f]{8}/envelope-hot-512\.webp" width="512" height="512" loading="lazy" decoding="async" alt="Artist', fig)
    assert '<a class="stage-tag" href="/docs/pictures/">Artist&#x27;s impression</a>' in fig and '<figcaption id="cap-x" class="readout">' in fig
    params = json.loads(re.search(r"data-params='([^']*)'", fig).group(1).replace("&quot;", '"'))
    assert params["look"] == "envelope-hot"
    other = unkey(R.figure("transit", {"teff": 5772, "k": 0.1}, "alt", "cap", label="Illustration", uid="y", still="data:,"))
    assert '<span class="stage-tag">Illustration</span>' in other and "/docs/pictures/" not in other


def test_the_renderer_fits_its_budget_and_exposes_its_api():
    js = R.render_js()
    assert len(js.encode()) <= R.RENDER_BUDGET
    for name in ("mount", "star", "planet", "transit", "starfield", "teffRGB", "look", "transitFlux", "drawStar2D", "drawPlanet2D", "stats"):
        assert re.search(rf"\b{name}[,}}:]", js[js.index("window.SetuRender = {"):]), name
    assert "console.error" not in js  # the e2e suite fails on console errors; the renderer uses console.info at most
    assert "getContext('webgl'" in js and "OffscreenCanvas" not in js  # WebGL1, one shared canvas (Safari)


def test_the_stills_were_drawn_by_the_current_code_and_table():
    m = R.stills_manifest()
    assert m["render_js_sha256"] == R.render_js_sha(), "the renderer changed: run node tools/render_stills.mjs"
    assert m["looks_sha256"] == R.looks_sha(), "the look table changed: run node tools/render_stills.mjs"
    total = 0
    for look in L.LOOKS:
        for px, cap in ((512, 40_000), (160, 8_000)):
            f = R.STILLS_DIR / f"{look}-{px}.webp"
            b = f.read_bytes()
            assert hashlib.sha256(b).hexdigest() == m["files"][look][str(px)] and b[:4] == b"RIFF" and b[8:12] == b"WEBP"
            assert len(b) <= cap, f.name
            total += len(b)
    assert total <= 850_000

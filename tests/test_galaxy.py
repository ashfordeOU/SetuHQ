import json
import math
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from exoplan import docket as docket_mod
from exoplan.app import APP_JS, build_app, build_landing
from exoplan.galaxy import (CLASSES, DEFAULT_MAP, DEFAULT_NOTABLE, GALAXY_JS, LY_PER_PC, TEASER_JS, galactic_lb,
                            galactic_xyz, galaxy_data, galaxy_meta, planet_class)

from test_story import run_dir  # noqa: F401  (fixture)

CSV = Path("/tmp/claude-0/-workspace-EXOPLAN/de5be2d1-4ad3-581c-88d5-10c9b521436f/scratchpad/data/exoplanet_eu_2026-10-18.csv")
PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_BROWSER = shutil.which("node") is not None and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def G():
    return galaxy_data(DEFAULT_MAP, DEFAULT_NOTABLE, lead_dip="tess-x-001")


def test_transform_matches_astropy():
    from astropy import units as u
    from astropy.coordinates import SkyCoord

    # The Galactic centre direction is +x; pi Men sits at l ≈ 292.5°, b ≈ -29.8°.
    gc = SkyCoord(l=0 * u.deg, b=0 * u.deg, frame="galactic").icrs
    x, y, z = galactic_xyz(gc.ra.deg, gc.dec.deg, 1.0)
    assert x == pytest.approx(1.0, abs=1e-9) and abs(y) < 1e-6 and abs(z) < 1e-6  # astropy's matrix differs by ~1e-7
    lon, lat = galactic_lb(84.2912083366, -80.4691111224)
    assert lon == pytest.approx(292.5, abs=0.1) and lat == pytest.approx(-29.8, abs=0.1)
    rng = random.Random(3)
    for _ in range(200):
        ra, dec, d = rng.uniform(0, 360), math.degrees(math.asin(rng.uniform(-1, 1))), rng.uniform(1, 20000)
        c = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, distance=d * u.pc, frame="icrs").galactic
        ref = c.cartesian
        got = galactic_xyz(ra, dec, d)
        assert got == pytest.approx((ref.x.value, ref.y.value, ref.z.value), abs=1e-6 * d)
        assert galactic_lb(ra, dec)[1] == pytest.approx(c.b.deg, abs=1e-4)


def test_dataset_counts_and_columns():
    m = json.loads(Path(DEFAULT_MAP).read_text())
    c = m["counts"]
    assert m["source"] == "eu" and m["source_name"] == "The Extrasolar Planets Encyclopaedia (exoplanet.eu)"
    assert m["fetched_at"].startswith("2026-10-18")
    assert c["rows"] == c["kept"] + c["dropped_no_distance"] + c["dropped_no_position"]
    assert (c["rows"], c["kept"], c["dropped_no_distance"]) == (8376, 8049, 327)
    assert all(len(v) == c["kept"] for v in m["planets"].values())
    assert len(set(m["planets"]["host"])) == c["hosts"]
    assert all(v is not None for k in ("ra", "dec", "dist_pc") for v in m["planets"][k])
    pi = m["planets"]["name"].index("pi Men c")
    assert m["planets"]["dist_pc"][pi] == 18.37 and m["planets"]["year"][pi] == 2018
    if CSV.exists():  # the CSV the JSON was built from: recount it independently
        import csv

        rows = list(csv.DictReader(CSV.open()))
        assert len(rows) == c["rows"]
        assert sum(1 for r in rows if r["ra"] and r["dec"] and r["star_distance"]) == c["kept"]


def test_year_counter_totals_equal_the_data(G):
    years = G["planets"]["y"]
    assert G["cum"][str(G["years"][1])] == len(years) == G["counts"]["kept"]
    for y in (1995, 2000, 2010, 2020):
        assert G["cum"][str(y)] == sum(1 for v in years if v <= y)
    assert sum(G["per_method"].values()) == G["counts"]["kept"]


def _node(script: str, tmp_path=None):
    if tmp_path is None:
        return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    f = tmp_path / "t.js"
    f.write_text(script)
    return json.loads(subprocess.run(["node", str(f)], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_filter_counts_match_a_python_reference(G, tmp_path):
    fn = re.search(r"function gxFilterCount\(G, v\)\{.*?\n\}\n", GALAXY_JS, re.S).group(0)
    views = [{"year": 2026, "methods": G["methods"], "dist": 0, "multi": False},
             {"year": 2000, "methods": G["methods"], "dist": 0, "multi": False},
             {"year": 2015, "methods": ["transit", "rv"], "dist": 250, "multi": True},
             {"year": 2026, "methods": ["imaging"], "dist": 1000, "multi": False}]
    out = _node(f"const G = {json.dumps(G)};\n{fn}\nconsole.log(JSON.stringify({json.dumps(views)}.map(v => {{ const r = gxFilterCount(G, v); return [r.planets, r.hosts]; }})));", tmp_path)
    P, H = G["planets"], G["hosts"]
    for v, got in zip(views, out):
        on = {G["methods"].index(m) for m in v["methods"]}
        lim = v["dist"] / LY_PER_PC if v["dist"] else math.inf
        keep = [i for i in range(len(P["n"])) if P["y"][i] <= v["year"] and P["m"][i] in on and H["d"][P["h"][i]] <= lim
                and (not v["multi"] or G["host_n"][P["h"][i]] >= 2)]
        assert got == [len(keep), len({P["h"][i] for i in keep})]
    assert out[0][0] == G["counts"]["kept"] and out[1][0] == G["cum"]["2000"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_galaxy_url_state_round_trips(G):
    meta = galaxy_meta(G)
    fns = re.search(r"function decodeGalaxyView\(params\)\{.*?\n\}\nfunction encodeGalaxyView\(v\)\{.*?\n\}\n", GALAXY_JS, re.S).group(0)
    cases = ["", "year=2010&method=transit,rv&dist=250&multi=1&view=kepler", "year=1800&method=zzz&dist=7&view=nowhere&tour=99",
             "method=none", "method=rv,transit", "view=pimen&tour=3", "year=2026&view=near&dist=0&multi=0", "cards=methods&multi=1"]
    out = _node(f"const GXM = {json.dumps(meta)};\n{fns}\nconsole.log(JSON.stringify({json.dumps(cases)}.map(c => {{ const v = decodeGalaxyView(new URLSearchParams(c)); return [v, encodeGalaxyView(v)]; }})));")
    assert out[0][1] == "" and out[0][0]["year"] == G["years"][1] and out[0][0]["view"] == "near"
    assert out[1][1] == "year=2010&method=transit,rv&dist=250&multi=1&view=kepler"
    assert out[2][1] == ""  # out of range or unknown: the defaults
    assert out[3][1] == "method=none" and out[3][0]["methods"] == []
    assert out[4][1] == "method=transit,rv"  # order normalised
    assert out[5][1] == "view=pimen&tour=3"
    assert out[6][1] == ""  # defaults written out are left out again
    assert out[7][1] == "multi=1&cards=methods" and out[7][0]["showcase"] is True
    go = re.search(r"function go\(p, moveFocus\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    assert "applyGalaxy(decodeGalaxyView(p.params))" in go and "syncGalaxyURL(false)" in go


def test_class_rule():
    re_ = lambda r: r / 11.209  # noqa: E731  (Earth radii to Jupiter radii)
    me = lambda m: m / 317.83  # noqa: E731
    assert [planet_class(re_(r), None) for r in (1.0, 1.25, 1.9, 2.0, 3.9, 4.0, 9.9, 10.0, 15)] == [0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert [planet_class(None, me(m)) for m in (1.0, 2.0, 9.9, 10, 49, 50, 300)] == [0, 1, 1, 3, 3, 4, 4]
    assert planet_class(None, None) is None and planet_class(0, None) is None
    assert planet_class(re_(1.0), me(300)) == 0  # radius first
    assert CLASSES == ["Earth-size", "Super-Earth", "Sub-Neptune", "Neptune-like", "Gas giant"]


def test_notable_cards_come_from_the_dataset(G):
    src = json.loads(Path(DEFAULT_NOTABLE).read_text())["planets"]
    assert len(G["notable"]) == len(src) == 17  # every name matches a row
    # One showcase per detection method, each found by that method.
    show = {nt["method"]: nt["name"] for nt in G["notable"] if nt["showcase"]}
    assert sorted(show) == sorted(["transit", "rv", "imaging", "microlensing", "astrometry", "timing"])
    assert sum(nt["showcase"] for nt in G["notable"]) == 6
    m = json.loads(Path(DEFAULT_MAP).read_text())["planets"]
    for e in src:
        assert e["tagline"] and e["ref"].startswith("https://") and e["ref_label"]
    for nt in G["notable"]:
        i = m["name"].index(nt["name"])
        h = nt["host"]
        assert G["planets"]["n"][nt["planet"]] == nt["name"]
        assert G["hosts"]["d"][h] == m["dist_pc"][i] and G["planets"]["y"][nt["planet"]] == m["year"][i]
        assert G["methods"][G["planets"]["m"][nt["planet"]]] == m["method"][i]
    # The cards read distance, year and method from those arrays, not from the notable file.
    call = re.search(r"gx\.calls = G\.notable\.map\(.*?\n  \}\);", GALAXY_JS, re.S).group(0)
    assert "gxLy(H.d[h])" in call and "P.y[i]" in call and "gxMethod(i)" in call and "gxClass(i)" in call
    pi = next(nt for nt in G["notable"] if nt["exoplan"])
    assert pi["name"] == "pi Men c" and G["star"]["host"] == pi["host"]


def test_page_states_source_definition_and_what_is_not_plotted(run_dir, tmp_path):  # noqa: F811
    page = build_app(run_dir, tmp_path / "app", title="t").read_text()
    sec = re.search(r'<section class="route" id="route-galaxy".*?(?=<section class="route" id="route-transit")', page, re.S).group(0)
    assert "Data: The Extrasolar Planets Encyclopaedia (exoplanet.eu), fetched 18 Oct 2026; 8,049 planets with a stored distance" in sec
    assert "broader than the NASA Exoplanet Archive" in sec and "exoplan did not find these planets" in sec
    assert "TIC 348835438, TIC 349088467, TIC 348770361" in sec and "not on this map" in sec
    assert "Milky Way: artist's impression; Sun's position approximate (~26,000 ly from the centre)" in sec.replace("&#x27;", "'")
    assert 'role="img"' in sec and "View as table: the 50 nearest systems" in sec and "How we classify" in sec
    assert sec.count("<tr>") == 51
    csv_text = (tmp_path / "app" / "assets" / "data" / "exoplanet_map.csv").read_text()
    assert csv_text.count("\n") == 8049 + 1
    assert 'href="assets/data/exoplanet_map.csv" download' in sec
    nav = re.search(r'<nav class="nav" aria-label="Sections">.*?</nav>', page, re.S).group(0)
    assert nav.index("#/sky") < nav.index("#/galaxy") < nav.index("#/transit")
    landing = build_landing(run_dir, tmp_path / "index.html", title="t").read_text()
    assert 'href="app/#/galaxy">Explore every known exoplanet ›</a>' in landing and "teaser-data" in landing


def test_no_external_requests_and_reduced_motion():
    for js in (GALAXY_JS, TEASER_JS):
        assert "fetch(" not in js and "XMLHttpRequest" not in js and "import(" not in js and "new Image" not in js
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", js)
    # Under reduced motion: no drift, no animated intro (a cut), the timeline only on a click; the teaser holds still.
    frame = re.search(r"function gxFrame\(t\)\{.*?\n\}\n", GALAXY_JS, re.S).group(0)
    assert "!gxRM.matches && gx.auto" in frame
    fly = re.search(r"function gxFly\(to, ms\)\{.*?\n\}\n", GALAXY_JS, re.S).group(0)
    assert "if (gxRM.matches || !ms" in fly
    assert "gx.play = {" in re.search(r"function gxPlay\(\)\{.*?\n\}\n", GALAXY_JS, re.S).group(0)
    assert "if (!rm.matches) raf = requestAnimationFrame(tick)" in TEASER_JS


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_galaxy_renders_without_errors_requests_or_card_overlap(run_dir, tmp_path):  # noqa: F811
    page = build_app(run_dir, tmp_path / "app", title="t")
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const out = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
    const p = await c.newPage(); const errs = [], reqs = [];
    p.on('pageerror', e => errs.push(e.message));
    p.on('request', r => { if (!/^(file|data|blob):/.test(r.url())) reqs.push(r.url()); });
    await p.goto(%s + '#/galaxy'); await p.waitForTimeout(1500);
    const r = { errs, reqs, gl: await p.evaluate(() => !!gx.gl), overlap: [] };
    for (const v of ['near', 'kepler', 'pimen']) {
      await p.evaluate(v => { gx.auto = false; gxFly(gxPresetCam(v), 0); }, v); await p.waitForTimeout(300);
      r.overlap.push(await p.evaluate(() => { const cs = [...document.querySelectorAll('.gxcall')].filter(e => e.style.display !== 'none').map(e => e.getBoundingClientRect()); let n = 0;
        for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++) { const a = cs[i], q = cs[j]; if (a.left < q.right && a.right > q.left && a.top < q.bottom && a.bottom > q.top) n++; } return n; }));
    }
    r.small = mob ? await p.evaluate(() => [...document.querySelectorAll('#route-galaxy a,#route-galaxy button,#route-galaxy select,#route-galaxy input,#route-galaxy summary')]
      .filter(e => { const q = e.getBoundingClientRect(); return q.width && q.height && (q.width < 44 || q.height < 44); }).map(e => e.id || e.className)) : [];
    r.hs = await p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    out.push(r); await c.close();
  }
  console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(Path(page).resolve().as_uri())))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr
    for r in json.loads(res.stdout.strip().splitlines()[-1]):
        assert r["errs"] == [] and r["reqs"] == [] and r["gl"], r
        assert r["overlap"] == [0, 0, 0] and r["small"] == [] and not r["hs"], r

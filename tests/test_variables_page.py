"""Everything that dims on the site: the counter, the page, the Sky layer, search and Mission Control, from the committed sweep."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import docket as docket_mod
from setuhq.everything import DEFAULT_SWEEP, VARIABLES_JS, load_sweep, sweep_meta, variables_filter

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_NODE = shutil.which("node") is not None
HAVE_BROWSER = HAVE_NODE and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()
CAT = load_sweep()
pytestmark = pytest.mark.skipif(CAT is None, reason=f"{DEFAULT_SWEEP} is not committed")


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    monkeypatch.setattr(docket_mod, "query_archive", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test")))


def _page(built):
    return built.read_text()


def _data(page):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))


def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


def test_every_figure_comes_from_the_committed_catalogue(pi_men_app):
    page = _page(pi_men_app)
    d = _data(page)["sweep"]
    assert d["counts"] == {k: v for k, v in CAT["counts"].items() if k != "null"}
    assert d["classes"] == [{"id": c["id"], "label": c["label"]} for c in CAT["classes"]]
    # The full catalogue (with the nulls and each class's rule text) is a separate file, fetched when needed;
    # the page's script carries only the counts and labels.
    assert "null" not in d["counts"] and "vs" not in d and "sky" not in d
    assert json.loads((pi_men_app.parent / "assets/data/variables.json").read_text()) == CAT
    assert "entries" not in d and "coverage" not in d
    over = _route(page, "overview")
    c = CAT["counts"]
    for n, label in ((c["stars_searched"], "stars searched"), (c["star_sectors_searched"], "star-sectors"),
                     (c["dips_reviewed"], "dips reviewed"), (c["entries"], "catalogue entries")):
        assert f'<b class="mono">{n:,}</b><span>{label}</span>' in over
    for k, n in c["by_class"].items():
        assert f'#/variables?class={k}"' in over and f"<b class=\"mono\">{n:,}</b>" in over
        if k != "unclassified":
            assert f'null {c["null"]["by_class"][k]["null"]:,} · excess' in over
    for k in c["null"]["noise_like"]:
        seg = over.split(f'#/variables?class={k}"')[1].split("</li>")[0]
        assert "not distinguishable from noise in this slice" in seg and "var(--ink-3)" in over.split(f'#/variables?class={k}"')[1][:40]
    assert "nothing is extrapolated" in over and "No entry is a new planet" in over
    src = CAT["sources"][0]
    assert f"{src['searched']:,} of the {src['targets_in_sector']:,} SPOC 2-minute targets" in over


def test_the_page_states_the_slice_the_rules_the_control_and_the_attribution(pi_men_app):
    page = _page(pi_men_app)
    v = _route(page, "variables")
    from setuhq.names import ATTRIBUTION

    assert 'id="h-variables"' in v and ATTRIBUTION in v
    assert "Nothing here is a new or confirmed planet." in v and "separate from the discovery feed" in v
    for k in CAT["classes"]:
        assert k["rule"].replace("'", "&#x27;") in v
    nul = CAT["counts"]["null"]
    assert f"measured on the same {nul['searches']:,} star-sectors" in v
    # No claim that the inverted copy is empty of real signals; each class names its own null.
    assert "where no real dip exists" not in page and "nothing real can dim" not in page
    assert "a real flare or pulsation maximum becomes a dip" in v
    for k, c in nul["by_class"].items():
        if k != "unclassified":
            assert f'<td class="num mono">{c["null"]:,}</td><td>{c["null_kind"]}</td>' in v, k
    # A class whose excess interval reaches zero says so, on the page and on every one of its cards.
    for k in nul["noise_like"]:
        assert next(x["label"] for x in CAT["classes"] if x["id"] == k) in v.split("not distinguishable from noise in this slice:")[1].split("</p>")[0]
    assert "VA_NOISE.has(e.class)" in page and "Planet-candidate rule" in page
    assert '<a href="#/catalogue">Known planets</a>' in v and 'aria-current=page>Everything that dims' in v
    assert 'href="#/variables">Everything that dims</a>' in _route(page, "catalogue")
    assert "superintelligence" not in page.lower()
    assert "confirmed planet" not in re.sub(r"(new or confirmed planet|not a confirmed planet)", "", v.lower())


def test_sky_layer_and_mission_telemetry(pi_men_app):
    page = _page(pi_men_app)
    sky = _route(page, "sky")
    n = sum(1 for r in CAT["coverage"] if r["status"] == "searched" and r["ra"] is not None)
    assert 'data-layer="sweep"' in sky and f"setuhq sweep ({n:,} star-sectors)" in sky
    assert sky.count('data-layer="sweep"') == 1
    assert "D.sweep" in page and "Sweep <b>" in page


def test_the_coherence_counts_and_limits_come_from_the_data(pi_men_app):
    var = [e for e in CAT["entries"] if e["kind"] == "variability"]
    why = [e.get("why") or "" for e in var if e["class"] == "unclassified"]
    untested = sum("coherence not tested" in w for w in why)
    check = json.loads((Path(DEFAULT_SWEEP).parent / "variability_rule_check.json").read_text())
    case = check["cases"]["sinusoid_in_strong_red_noise"]
    meta = sweep_meta(CAT, None, DEFAULT_SWEEP)
    assert meta["coherence"]["not_tested"] == untested and meta["coherence"]["coherent"] == sum(e["class"] == "variable" for e in var)
    sec = _route(_page(pi_men_app), "variables").replace("&#x27;", "'")
    assert f"{untested:,} longer than a half can test (coherence not tested)" in sec
    assert f"in strong red noise only {case['variable']}/{check['n']} times" in sec
    assert f"longer than about {meta['coherence']['testable_max_days']:g} d in one sector" in sec


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_the_page_filter_matches_python(tmp_path):
    meta = sweep_meta(CAT)
    js = VARIABLES_JS[VARIABLES_JS.index("function decodeVarView"):VARIABLES_JS.index("function vaSort")]
    views = [{}, {"class": "variable"}, {"class": "flare,systematic", "conf": "high"}, {"q": "tic 1"}, {"toi": "1"}, {"q": "setuhq"}]
    script = (f"const VA = {json.dumps(meta)}; const VA_CLASSES = VA.classes.map(c => c.id); const VA_CONF = ['high','medium','low','n/a'];\n"
              f"const E = {json.dumps(CAT['entries'])};\n" + js +
              f"\nconsole.log(JSON.stringify({json.dumps(views)}.map(q => {{ const v = decodeVarView(new URLSearchParams(q)); "
              "return [vaFilter(E, v).map(e => e.id), encodeVarView(v)]; })));")
    (tmp_path / "filter.js").write_text(script)
    out = subprocess.run(["node", str(tmp_path / "filter.js")], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    for q, (ids, enc) in zip(views, got):
        v = {"cls": (q.get("class") or "").split(",") if q.get("class") else [], "conf": [q["conf"]] if q.get("conf") else [],
             "q": q.get("q", ""), "toi": q.get("toi") == "1"}
        assert ids == variables_filter(CAT, v), q
        assert enc == "&".join(f"{k}={v.replace(' ', '%20')}" for k, v in q.items())


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_everything_that_dims_in_the_browser(pi_men_app, tmp_path):
    url = pi_men_app.resolve().as_uri()
    ent = next(e for e in CAT["entries"] if e["kind"] == "dip")
    tic = ent["tic"]
    n_tic = sum(1 for e in CAT["entries"] if e["tic"] == tic)
    cls = max(CAT["counts"]["by_class"], key=CAT["counts"]["by_class"].get)
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const out = [], ext = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) for (const theme of ['dark', 'light']) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob, reducedMotion: 'reduce' });
    await c.addInitScript(t => { try { localStorage.setItem('setuhq-theme', t); } catch (e) {} }, theme);
    const p = await c.newPage(), errs = [];
    p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    p.on('request', r => { if (!/^(file|data|blob):/.test(r.url())) ext.push(r.url()); });
    const look = async route => { await p.goto(%s + route); await p.waitForTimeout(1200); return p.evaluate(() => {
      const vw = document.documentElement.clientWidth, sec = document.querySelector('.route:not([hidden])');
      const small = [...sec.querySelectorAll('a,button,select,input,summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.width < 44 || r.height < 44) && !e.closest('p,td,dd,figcaption'); }).map(e => e.className || e.tagName);
      const wide = [...sec.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > vw + 1 && !e.closest('.tablewrap'); }).map(e => e.tagName + '.' + e.className);
      return {id: sec.id, small, wide, hash: location.hash, count: (document.querySelector('#vacount') || {}).textContent,
        cards: document.querySelectorAll('#valist .vaent').length, obj: document.querySelector('#vaobj') ? !document.querySelector('#vaobj').hidden : null,
        objh: (document.querySelector('#h-vaobj') || {}).textContent, focus: document.activeElement && document.activeElement.id,
        open: [...document.querySelectorAll('#valist details[open]')].length, scrollW: document.documentElement.scrollWidth, vw}; }); };
    const r = {w, theme, errs};
    r.list = await look('#/variables');
    await p.click('#vaclasses [data-vc="%s"]'); await p.waitForTimeout(300);
    r.filtered = await p.evaluate(() => [location.hash, document.querySelector('#vacount').textContent]);
    r.tic = await look('#/variables?tic=%s&id=%s');
    r.overview = await look('#/overview');
    r.counter = await p.evaluate(() => [...document.querySelectorAll('.sweeptiles b')].map(b => b.textContent));
    r.sky = await look('#/sky?layers=sweep');
    r.skyLayer = await p.evaluate(() => document.querySelector('#route-sky .covl[data-layer="sweep"]').style.display);
    r.mission = await look('#/mission');
    r.tele = await p.evaluate(() => document.querySelector('#mctele').textContent);
    await p.click('#gsearchbtn'); await p.keyboard.type('tic %s'); await p.waitForTimeout(800);
    r.search = await p.evaluate(() => [...document.querySelectorAll('#gsresults [role=option]')].map(li => li.textContent));
    out.push(r); await c.close();
  }
  console.log(JSON.stringify({out, ext})); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(url), cls, tic, ent["id"], str(tic)[:6]))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=400)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout.strip().splitlines()[-1])
    assert data["ext"] == []
    total = len(CAT["entries"])
    n_cls = CAT["counts"]["by_class"][cls]
    c = CAT["counts"]
    for r in data["out"]:
        assert r["errs"] == [], r
        for k in ("list", "tic", "overview", "sky", "mission"):
            assert r[k]["scrollW"] <= r[k]["vw"], (k, r[k])
        for k in ("list", "tic"):
            assert r[k]["wide"] == [], (k, r[k])
            if r["w"] == 390:
                assert r[k]["small"] == [], (k, r[k])
        assert r["list"]["id"] == "route-variables" and r["list"]["obj"] is False
        assert r["list"]["count"] == f"Showing {min(60, total):,} of {total:,} matching · {total:,} entries in all"
        assert r["list"]["cards"] == min(60, total)
        assert r["filtered"] == [f"#/variables?class={cls}", f"Showing {min(60, n_cls):,} of {n_cls:,} matching · {total:,} entries in all"]
        assert r["tic"]["obj"] is True and r["tic"]["objh"].startswith(f"TIC {tic}") and r["tic"]["cards"] == n_tic
        assert r["tic"]["focus"] == "h-vaobj" and r["tic"]["open"] == 1
        assert r["counter"] == [f"{c['stars_searched']:,}", f"{c['star_sectors_searched']:,}", f"{c['dips_reviewed']:,}", f"{c['entries']:,}"]
        assert r["skyLayer"] == ""
        assert f"Sweep {c['stars_searched']:,} stars" in r["tele"]
        assert any(f"TIC {tic}" in s for s in r["search"]), r["search"]

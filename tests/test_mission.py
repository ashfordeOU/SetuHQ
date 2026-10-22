# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Round 11: Mission Control. Panes of SetuHQ's own views, linked by one selected star."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import mission as MC
from setuhq.app import APP_JS
from conftest import served, site_bundle

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_NODE = shutil.which("node") is not None
HAVE_BROWSER = HAVE_NODE and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()


@pytest.fixture(scope="module")
def built(pi_men_app):
    return pi_men_app


def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


def test_six_panes_each_with_its_tools_and_no_insignia(built):
    sec = _route(site_bundle(built), "mission")
    assert [p for p, _ in MC.PANES] == ["galaxy", "sky", "lc", "cat", "sys", "feed"]
    for pid, label in MC.PANES:
        pane = re.search(rf'<section class="mcpane" id="mcp-{pid}".*?</section>', sec, re.S).group(0)
        assert f'aria-labelledby="mch-{pid}"' in pane and 'tabindex="-1"' in pane and 'draggable="true"' in pane
        for act in ("prev", "next", "focus", "pop", "hide"):
            assert f'data-mc="{act}"' in pane, (pid, act)
    # The system pane is the shared component; telemetry is computed, and there is no agency insignia.
    assert 'id="mcsys"' in sec and '<span class="mxlabel model">Model from stored values</span>' in sec
    assert "nothing is simulated" in sec and "<img" not in sec and "NASA" not in sec and "insignia" not in sec.lower()
    keys = re.search(r'<details class="small mckeys"><summary>Keyboard</summary>.*?</details>', sec, re.S).group(0)
    assert 'role="status"' in sec and "F6 and Shift+F6 move between panes" in keys and "Ctrl+Alt+1 to 6" in keys
    assert "With a pane focused, Alt+← and Alt+→ move it" in keys and "arrow buttons" in keys
    # A phone stacks the panes in one column and offers no pop-out windows.
    phone = MC.MISSION_CSS[MC.MISSION_CSS.index("@media (max-width:699.98px)"):]
    assert "grid-template-columns:minmax(0,1fr)" in phone and ".mcpopbtn" in phone


@pytest.mark.skipif(not HAVE_NODE, reason="node is not installed")
def test_layout_url_round_trips_and_cleans_bad_input():
    js = MC.MISSION_JS
    core = js[js.index("function mcDefault()"):js.index("function syncMissionURL")]
    script = ("const D = {mission: %s, story: {star: {name: 'pi Men'}}}; const getStorage = () => null;\n"
              "const MC_PANES = D.mission.panes.map(p => p[0]), MC_GRIDS = D.mission.grids.map(g => g[0]), MC_KEY = 'x';\n"
              "const mc = {star: 'pi Men'};\n%s\n"
              "const cases = ['', 'panes=sky,galaxy&grid=tile', 'panes=zzz,feed,feed&hide=lc,qq&grid=nope', 'hide=galaxy,sky,lc,cat,sys,feed', 'pop=sys&star=HR%%208799'];\n"
              "console.log(JSON.stringify(cases.map(c => { const v = decodeMission(new URLSearchParams(c)); if (v.star) mc.star = v.star; else mc.star = 'pi Men'; return [v, encodeMission(v)]; })));"
              ) % (json.dumps({"panes": MC.PANES, "grids": MC.GRIDS}), core)
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out[0][0]["panes"] == ["galaxy", "sky", "lc", "cat", "sys", "feed"] and out[0][0]["grid"] == "focus" and out[0][1] == ""
    assert out[1][0]["panes"][:2] == ["sky", "galaxy"] and out[1][1] == "panes=sky,galaxy,lc,cat,sys,feed&grid=tile"
    assert out[2][0]["panes"][0] == "feed" and out[2][0]["hidden"] == ["lc"] and out[2][0]["grid"] == "focus"
    assert out[3][0]["hidden"] == []  # hiding every pane is not a layout: all shown
    assert out[4][0]["pop"] == "sys" and out[4][1] == "star=HR%208799&pop=sys"


def test_galaxy_selection_feeds_the_linked_selection():
    from setuhq.galaxy import GALAXY_JS
    sel = GALAXY_JS[GALAXY_JS.index("function gxSelect(h, planet){"):GALAXY_JS.index("function gxTip(")]
    assert "if (typeof mcBrush === 'function') mcBrush(H.n[h], 'galaxy');" in sel
    assert "missionShown(r === 'mission');" in APP_JS and "applyMission(decodeMission(p.params))" in APP_JS
    assert "new BroadcastChannel('setuhq-mission')" in MC.MISSION_JS and "try { if ('BroadcastChannel' in window) mcBC = new BroadcastChannel" in MC.MISSION_JS


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_mission_control_in_the_browser(built, tmp_path):
    url = served(built)
    script = tmp_path / "mc.js"
    script.write_text("""
const { chromium } = require(%s);
const U = %s;
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const out = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) for (const theme of ['dark', 'light']) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
    await c.addInitScript(t => { try { localStorage.setItem('setuhq-theme', t); } catch (e) {} }, theme);
    const p = await c.newPage(), errs = [], ext = [];
    p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    p.on('request', r => { if (!/^(file|data|blob):|^http:..127.0.0.1:/.test(r.url())) ext.push(r.url()); });
    await p.goto(U + '#/mission'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForFunction(() => typeof gx !== 'undefined' && gx.ready && gx.sel >= 0, null, {timeout: 30000}); await p.waitForTimeout(500);
    const r = {w, theme, errs, ext};
    r.init = await p.evaluate(() => ({star: mc.star, gx: gx.G.hosts.n[gx.sel], inPane: !!document.querySelector('#mcb-galaxy #gxstage'), sys: document.querySelector('#mcsyspick').selectedOptions[0].textContent,
      lc: !!document.querySelector('#mclc svg'), tele: document.querySelector('#mctele').textContent,
      cols: [...new Set([...document.querySelectorAll('.mcpane:not([hidden])')].map(e => Math.round(e.getBoundingClientRect().left)))].length}));
    await p.fill('#mcq', 'HR 8799'); await p.waitForTimeout(250); await p.click('[data-mcstar="HR 8799"]'); await p.waitForTimeout(1500);
    r.brush = await p.evaluate(() => ({star: mc.star, hash: ('#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : '')), gx: gx.sel >= 0 ? gx.G.hosts.n[gx.sel] : null, sys: document.querySelector('#mcsyspick').selectedOptions[0].textContent,
      sky: document.querySelector('#mcsky svg').getAttribute('aria-label').startsWith('HR 8799'), lc: document.querySelector('#mclcnote').textContent, tele: document.querySelector('#mctele').textContent}));
    r.small = await p.evaluate(() => [...document.querySelectorAll('#route-mission a, #route-mission button, #route-mission select, #route-mission input')].filter(e => { const q = e.getBoundingClientRect(); return q.width && (q.height < 44 || q.width < 44) && !e.closest('p,li,td,dd,figcaption,.gxstage'); }).length);
    r.wide = await p.evaluate(() => { const vw = document.documentElement.clientWidth; return [...document.querySelectorAll('#route-mission *')].filter(e => { const q = e.getBoundingClientRect(); return q.width && q.right > vw + 1 && !e.closest('.gxstage'); }).length; });
    if (!mob){
      await p.click('#mcp-sky [data-mc="prev"]'); await p.click('#mcp-feed [data-mc="hide"]'); await p.click('[data-mcgrid="tile"]'); await p.waitForTimeout(200);
      r.url = await p.evaluate(() => ('#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : '')));
      await p.keyboard.press('F6'); const f1 = await p.evaluate(() => document.activeElement.id); await p.keyboard.press('Alt+3'); r.keys = [f1, await p.evaluate(() => document.activeElement.id)];
      await p.click('#mcsave'); r.saved = await p.evaluate(() => JSON.parse(localStorage.getItem('setuhq-mission')));
      const [pop] = await Promise.all([c.waitForEvent('page'), p.click('#mcp-sys [data-mc="pop"]')]); await pop.waitForTimeout(2500);
      r.pop = await pop.evaluate(() => [mc.pop, mc.star, [...document.querySelectorAll('.mcpane')].filter(x => !x.hidden).map(x => x.id)]);
      await p.fill('#mcq', 'TRAPPIST'); await p.waitForTimeout(250); await p.click('[data-mcstar="TRAPPIST-1"]'); await p.waitForTimeout(1200);
      r.popFollows = await pop.evaluate(() => [mc.star, document.querySelector('#mcsyspick').selectedOptions[0].textContent]);
      await pop.close(); await p.waitForTimeout(800); r.back = await p.evaluate(() => document.querySelector('#mcp-sys .mcpopped').hidden);
      await p.goto(U + '#/galaxy'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(800); r.home = await p.evaluate(() => !!document.querySelector('#route-galaxy #gxstage'));
      // Leaving before the catalogue arrives must not pull the map back into the pane.
      const q = await c.newPage(); await q.goto(U + '#/mission'); await q.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await q.goto(U + '#/galaxy'); await q.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await q.waitForTimeout(2000);
      r.fast = await q.evaluate(() => !!document.querySelector('#route-galaxy #gxstage')); await q.close();
    }
    out.push(r); await c.close();
  }
  console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(url), json.dumps(CHROMIUM)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=400)
    assert res.returncode == 0, res.stderr
    cat = json.loads(Path("docs/results/exoplanet_catalogue.json").read_text())["counts"]
    for r in json.loads(res.stdout.strip().splitlines()[-1]):
        assert r["errs"] == [] and r["ext"] == [], r
        i = r["init"]
        assert i["star"] == "pi Men" and i["gx"] == "pi Men" and i["inPane"] and i["sys"] == "pi Men c" and i["lc"]
        # Telemetry is the data's own counts.
        assert f"Catalogue {cat['rows']:,} planets · {cat['stars']:,} stars" in i["tele"] and "Selected pi Men · 3 planets · 18.37 pc" in i["tele"]
        assert (i["cols"] == 1) == (r["w"] == 390)  # a phone stacks the panes
        bsh = r["brush"]
        assert bsh["star"] == bsh["gx"] == "HR 8799" and bsh["hash"] == "#/mission?star=HR%208799" and bsh["sys"].startswith("HR 8799 ") and bsh["sky"]
        n_hr = sum(1 for x in json.loads(Path("docs/results/exoplanet_catalogue.json").read_text())["planets"]["star"] if x == "HR 8799")
        assert "It has none for HR 8799." in bsh["lc"] and f"Selected HR 8799 · {n_hr} planets" in bsh["tele"]
        assert r["small"] == 0 and r["wide"] == 0
        if r["w"] == 1360:
            assert r["url"] == "#/mission?panes=sky,galaxy,lc,cat,sys,feed&hide=feed&grid=tile&star=HR%208799"
            assert r["keys"] == ["mcp-sky", "mcp-lc"]
            assert r["saved"] == {"panes": ["sky", "galaxy", "lc", "cat", "sys", "feed"], "hidden": ["feed"], "grid": "tile"}
            assert r["pop"] == ["sys", "HR 8799", ["mcp-sys"]]
            assert r["popFollows"] == ["TRAPPIST-1", "TRAPPIST-1 b"]  # BroadcastChannel keeps the windows on one star
            assert r["back"] is True and r["home"] is True and r["fast"] is True


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_review_fixes_galaxy_alive_feed_shown_popups_keyboard_storage(built, tmp_path):
    script = tmp_path / "fix.js"
    script.write_text("""
const { chromium } = require(%s);
const U = %s;
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files', '--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] });
  const c = await b.newContext({ viewport: { width: 1360, height: 900 } }); const p = await c.newPage(), errs = [], r = {};
  p.on('pageerror', e => errs.push(e.message));
  // B1: a fresh tab on #/mission: the map is on and a drag turns the camera.
  await p.goto(U + '#/mission'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForFunction(() => typeof gx !== 'undefined' && gx.ready, null, {timeout: 30000}); await p.waitForTimeout(2600);
  await p.$eval('#gxcanvas', e => e.scrollIntoView({block: 'center'})); await p.waitForTimeout(200);
  const bx = await (await p.$('#mcb-galaxy #gxcanvas')).boundingBox(), x = bx.x + bx.width * 0.75, y = bx.y + bx.height * 0.5;
  const yaw0 = await p.evaluate(() => gx.cam.yaw);
  await p.mouse.move(x, y); await p.mouse.down(); await p.mouse.move(x - 200, y - 40, {steps: 8}); await p.mouse.up(); await p.waitForTimeout(200);
  r.b1 = await p.evaluate(y0 => [gx.on, Math.abs(gx.cam.yaw - y0) > 0.1], yaw0);
  // B2: the feed's cards are shown at desktop width.
  r.b2 = await p.evaluate(() => { const l = document.querySelector('#mcfeed .feedcards'); return [getComputedStyle(l).display !== 'none', l.getBoundingClientRect().height > 0, document.querySelector('#mcfeednote').textContent]; });
  // B4: a star with no catalogue planets.
  await p.evaluate(() => mcBrush('Nowhere star', 'test')); await p.waitForTimeout(300);
  r.b4 = await p.evaluate(() => [document.querySelector('#mcsysnote').textContent, document.querySelector('#mcsys').hidden, document.querySelector('.mcpick').hidden]);
  await p.evaluate(() => mcBrush('pi Men', 'test')); await p.waitForTimeout(300);
  r.b4back = await p.evaluate(() => [document.querySelector('#mcsysnote').hidden, document.querySelector('#mcsys').hidden]);
  // B6: Enter on Hide moves focus to its Show button; numbers count shown panes; Ctrl+Alt+N and Alt+← work.
  await p.focus('#mcp-sky [data-mc="hide"]'); await p.keyboard.press('Enter'); await p.waitForTimeout(200);
  r.b6a = await p.evaluate(() => [document.activeElement.dataset.mcshow, document.activeElement === document.body]);
  r.b6b = await p.evaluate(() => [...document.querySelectorAll('.mcpane')].map(x => x.querySelector('.mcnum').textContent));
  await p.keyboard.press('Control+Alt+Digit2'); r.ctrlalt = await p.evaluate(() => document.activeElement.id);
  await p.keyboard.press('Alt+ArrowLeft'); r.altLeft = await p.evaluate(() => ('#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : '')));
  for (const id of ['galaxy', 'lc', 'cat', 'sys', 'feed']) { const bt = await p.$(`#mcp-${id} [data-mc="hide"]`); if (await bt.isEnabled()) await bt.click(); }
  r.oneLeft = await p.evaluate(() => document.querySelectorAll('.mcpane:not([hidden])').length);
  await p.click('#mcreset'); await p.waitForTimeout(400); r.resetOn = await p.evaluate(() => gx.on);
  // Drag a title bar onto another pane with real mouse events: they swap.
  await p.$eval('#mcp-sky', e => e.scrollIntoView({block: 'center'}));
  const a = await (await p.$('#mcp-sky .mchead h2')).boundingBox(), t = await (await p.$('#mcp-lc .mcbody')).boundingBox();
  await p.mouse.move(a.x + 20, a.y + a.height / 2); await p.mouse.down(); await p.mouse.move(a.x + 40, a.y + 30, {steps: 5}); await p.mouse.move(t.x + 50, t.y + 50, {steps: 10}); await p.mouse.up(); await p.waitForTimeout(300);
  r.dnd = await p.evaluate(() => ('#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : ''))); await p.click('#mcreset'); await p.waitForTimeout(300);
  // B3 and B5: a popped Sky window fits its window, sleeps the map, and the main pane catches up when it closes.
  const [pop] = await Promise.all([c.waitForEvent('page'), p.click('#mcp-sky [data-mc="pop"]')]); await pop.waitForTimeout(2500);
  r.b5 = await pop.evaluate(() => [document.documentElement.scrollHeight === window.innerHeight, gx.on]);
  await p.fill('#mcq', 'HD 209458'); await p.waitForTimeout(250); await p.click('[data-mcstar="HD 209458"]'); await p.waitForTimeout(600);
  await pop.close(); await p.waitForTimeout(1200);
  r.b3 = await p.evaluate(() => [document.querySelector('#mcsky svg').getAttribute('aria-label').startsWith('HD 209458'), document.querySelector('#mcp-sky .mcpopped').hidden]);
  // A popped Galaxy window runs the map; the main window's copy sleeps.
  const [g] = await Promise.all([c.waitForEvent('page'), p.click('#mcp-galaxy [data-mc="pop"]')]); await g.waitForFunction(() => typeof gx !== 'undefined' && gx.ready, null, {timeout: 30000}); await g.waitForTimeout(600);
  r.gpop = await g.evaluate(() => [gx.on, document.documentElement.scrollHeight === window.innerHeight]); r.mainOff = await p.evaluate(() => gx.on === false);
  await g.close();
  r.tele = await p.evaluate(() => document.querySelector('#mctele').hasAttribute('aria-live') || document.querySelector('#mctele').hasAttribute('role'));
  // B7: storage blocked: Save says so.
  const c2 = await b.newContext({ viewport: { width: 1360, height: 900 } }); await c2.addInitScript(() => { Object.defineProperty(window, 'localStorage', {get(){ throw new Error('blocked'); }}); });
  const q = await c2.newPage(); await q.goto(U + '#/mission'); await q.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await q.waitForTimeout(1500); await q.click('#mcsave'); await q.waitForTimeout(200);
  r.b7 = await q.evaluate(() => document.querySelector('#announce').textContent);
  r.errs = errs; console.log(JSON.stringify(r)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(served(built)), json.dumps(CHROMIUM)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["errs"] == []
    assert r["b1"] == [True, True]
    n_feed = len(json.loads(Path("docs/discoveries/catalog.json").read_text())["candidates"])
    assert r["b2"][:2] == [True, True] and r["b2"][2].startswith(f"The feed is the catalogue run's {n_feed} candidates; none is pi Men.")
    assert r["b4"] == ["Nowhere star is not in the catalogue; there is no system to draw.", True, True] and r["b4back"] == [True, False]
    assert r["b6a"] == ["sky", False] and r["b6b"] == ["1", "", "2", "3", "4", "5"]
    assert r["ctrlalt"] == "mcp-lc" and r["altLeft"].startswith("#/mission?panes=galaxy,lc,sky")
    assert r["oneLeft"] == 1 and r["resetOn"] is True
    assert r["dnd"].startswith("#/mission?panes=galaxy,lc,sky")
    assert r["b5"] == [True, False] and r["b3"] == [True, True]
    assert r["gpop"] == [True, True] and r["mainOff"] is True and r["tele"] is False
    assert r["b7"] == "This browser does not allow storage; the layout lasts for this visit."

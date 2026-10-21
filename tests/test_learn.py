# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Round 11: the Learn path. Optional, any visit counts, progress kept in this browser."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import learn as L
from setuhq.app import APP_JS
from setuhq.methods import CHAPTERS
from conftest import served, site_bundle

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_BROWSER = shutil.which("node") is not None and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()


@pytest.fixture(scope="module")
def built(pi_men_app):
    return pi_men_app


def test_the_path_covers_every_chapter_in_order_then_the_galaxy_and_catalogue():
    steps = L.learn_steps()
    ids = [s["id"] for s in steps]
    assert [i for i in ids if i.startswith("ch:")] == ["ch:" + c for c, _ in CHAPTERS]
    assert ids.index("transit") == ids.index("ch:transit") + 1  # SetuHQ's own case right after the chapter
    assert ids[-2:] == ["galaxy", "catalogue"] and len(ids) == len(set(ids)) == len(CHAPTERS) + 3
    assert all(s["href"].startswith("#/") for s in steps)


def test_the_card_and_bar_are_in_the_shell_and_progress_is_guarded(built):
    page = site_bundle(built)
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1))
    assert data["learn"] == L.learn_steps()
    ov = re.search(r'<section class="route" id="route-overview".*?(?=<section class="route" id="route-)', page, re.S).group(0)
    assert 'id="learncard"' in ov and "Optional: go in order or skip around" in ov and 'role="progressbar"' in ov
    assert '<nav class="learnbar" id="learnbar" aria-label="Learn path" hidden>' in page
    # Every storage access is inside try/catch, and the bar shows only after the viewer starts the path.
    js = L.LEARN_JS
    for fn in ("function learnRead(){", "function learnSave(){"):
        body = js[js.index(fn):js.index("\n}", js.index(fn))] if fn == "function learnRead(){" else js[js.index(fn):js.index("\n", js.index(fn))]
        assert "try {" in body and "catch (e)" in body, fn
    assert "on = learn.active && i >= 0" in js and "learnVisit(p);" in APP_JS
    # Only the app has it: the static landing page has no script to keep progress.
    assert "learn_card() if with_view" in Path("src/setuhq/app.py").read_text()


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_learn_path_in_the_browser(built, tmp_path):
    url = served(built)
    script = tmp_path / "learn.js"
    script.write_text("""
const { chromium } = require(%s);
const U = %s;
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const out = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) for (const theme of ['dark', 'light']) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
    await c.addInitScript(t => { try { localStorage.setItem('setuhq-theme', t); } catch (e) {} }, theme);
    const p = await c.newPage(), errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    const r = {w, theme, errs};
    await p.goto(U + '#/overview'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(700);
    r.card0 = await p.evaluate(() => [document.querySelector('#learngo').textContent, document.querySelector('#learncount').textContent, document.querySelector('#learnbar').hidden]);
    // Visiting a page without starting the path counts, but shows no bar.
    await p.goto(U + '#/galaxy'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(300); r.noBar = await p.evaluate(() => document.querySelector('#learnbar').hidden);
    await p.goto(U + '#/overview'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(300);
    await p.click('#learngo'); await p.waitForTimeout(600);
    r.step1 = await p.evaluate(() => [location.pathname, document.querySelector('#learnbar').hidden, document.querySelector('#learnpos').textContent]);
    // The bar is fixed; under a heavily loaded machine the methods stages' animation can stall Playwright's stability wait.
    await p.click('#learnnext', {force: true}); await p.waitForTimeout(400); await p.click('#learnnext', {force: true}); await p.waitForTimeout(600);
    r.step3 = await p.evaluate(() => [location.pathname, document.querySelector('#learnpos').textContent]);
    r.small = await p.evaluate(() => [...document.querySelectorAll('#learnbar a, #learnbar button')].filter(e => { const q = e.getBoundingClientRect(); return q.width && (q.height < 44 || q.width < 44); }).length);
    r.docW = await p.evaluate(() => document.documentElement.scrollWidth);
    await p.reload(); await p.waitForTimeout(700);
    r.reload = await p.evaluate(() => [document.querySelector('#learnbar').hidden, JSON.parse(localStorage.getItem('setuhq-learn')).seen]);
    await p.click('#learnleave'); await p.waitForTimeout(200); r.left = await p.evaluate(() => document.querySelector('#learnbar').hidden);
    await p.goto(U + '#/overview'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(400);
    r.card1 = await p.evaluate(() => [document.querySelector('#learngo').textContent, document.querySelector('#learncount').textContent, document.querySelector('.learnmeter').getAttribute('aria-valuenow')]);
    await p.click('#learnreset'); await p.waitForTimeout(200);
    r.reset = await p.evaluate(() => document.querySelector('#learncount').textContent);
    out.push(r); await c.close();
  }
  // Storage blocked: the path still works for the visit.
  const c = await b.newContext(); await c.addInitScript(() => { Object.defineProperty(window, 'localStorage', {get(){ throw new Error('blocked'); }}); });
  const p = await c.newPage(), errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.goto(U + '#/overview'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(700); await p.click('#learngo'); await p.waitForTimeout(500);
  const blocked = {state: await p.evaluate(() => [location.pathname, document.querySelector('#learnbar').hidden]), errs};
  console.log(JSON.stringify({out, blocked})); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(url), json.dumps(CHROMIUM)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout.strip().splitlines()[-1])
    n = len(L.learn_steps())
    for r in data["out"]:
        assert r["errs"] == [], r
        assert r["card0"] == ["Start the path", f"0 of {n} visited", True]
        assert r["noBar"] is True
        assert r["step1"] == ["/how-it-works/", False, f"Learn path · 1 of {n} · How a survey works"]
        assert r["step3"] == ["/candidates/tess-fa3483ce6f83-000/", f"Learn path · 3 of {n} · SetuHQ's own transit: the case file"]
        assert r["small"] == 0 and r["docW"] == r["w"]
        assert r["reload"][0] is False and set(r["reload"][1]) == {"galaxy", "ch:survey", "ch:transit", "transit"}
        assert r["left"] is True
        assert r["card1"] == ["Continue: Toward and away", f"4 of {n} visited", "4"]
        assert r["reset"] == f"0 of {n} visited"
    assert data["blocked"] == {"state": ["/how-it-works/", False], "errs": []}


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_keyboard_focus_never_drops_to_body(built, tmp_path):
    script = tmp_path / "focus.js"
    script.write_text("""
const { chromium } = require(%s);
const U = %s;
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const out = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob }); const p = await c.newPage(), errs = [];
    p.on('pageerror', e => errs.push(e.message));
    const r = {w, errs};
    await p.goto(U + '#/overview'); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(600);
    await p.focus('#learngo'); await p.keyboard.press('Enter'); await p.waitForTimeout(500);
    r.step1Prev = await p.evaluate(() => document.querySelector('#learnprev').hidden);
    await p.focus('#learnnext'); await p.keyboard.press('Enter'); await p.waitForTimeout(500);
    r.step2Prev = await p.evaluate(() => [document.querySelector('#learnprev').hidden, location.pathname]);
    // Back from step 2 to step 1 with the keyboard: Back disappears, focus goes to Next.
    await p.focus('#learnprev'); await p.keyboard.press('Enter'); await p.waitForTimeout(500);
    r.back = await p.evaluate(() => [location.pathname, document.activeElement.id, document.activeElement === document.body, document.querySelector('#learnprev').hidden]);
    // Leave with the keyboard: the bar goes, focus goes to the page's heading.
    await p.focus('#learnleave'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
    r.leave = await p.evaluate(() => [document.querySelector('#learnbar').hidden, document.activeElement === document.body, document.activeElement.tagName, document.activeElement.id]);
    out.push(r); await c.close();
  }
  console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(served(built)), json.dumps(CHROMIUM)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=200)
    assert res.returncode == 0, res.stderr
    for r in json.loads(res.stdout.strip().splitlines()[-1]):
        assert r["errs"] == []
        assert r["step1Prev"] is True and r["step2Prev"] == [False, "/how-it-works/transits/"]
        assert r["back"] == ["/how-it-works/", "learnnext", False, True]
        assert r["leave"][0] is True and r["leave"][1] is False and r["leave"][2] == "H1" and r["leave"][3] == "h-methods"


def test_the_bar_never_covers_the_catalogue_or_the_galaxy_sheet():
    css = L.LEARN_CSS
    assert "body.learning .ctscroll{height:min(calc(64vh - 76px),640px)}" in css
    phone = css[css.index("@media (max-width:699.98px)"):]
    assert "body.learning .ctscroll{height:calc(70vh - 100px)}" in phone
    assert "body.learning .gxsheet{bottom:calc(98px + env(safe-area-inset-bottom,0px))}" in phone
    assert ".learnbar .lnt,.learnbar .lpre{display:none}" in phone and '<span class="lpre">Learn path · </span>' in L.LEARN_JS

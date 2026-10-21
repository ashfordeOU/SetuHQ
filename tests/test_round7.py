# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import docket as docket_mod
from setuhq.app import APP_JS, FRAME_BRIDGE_JS, FRAME_PHONE_CSS
from setuhq.plate import build_plate
from setuhq.report import build_report

from test_story import run_dir  # noqa: F401  (fixture)
from conftest import served

PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_BROWSER = shutil.which("node") is not None and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


def test_the_docket_itself_ships_the_phone_block():
    css, js = docket_mod.DOCKET_CSS, docket_mod.DOCKET_JS
    phone = css[css.index("@media (max-width:700px){\n  .jumplist"):]
    for rule in (".dipbtn,.chip,.listtoggle{min-height:44px", ".sectoggle{min-height:44px",
                 "#rows .sighead[role=button]{min-height:44px", ".dippick select{", "min-height:44px"):
        assert rule in phone, rule
    assert "html.framed .dippick{display:none}" in phone  # the shell has its own dip picker
    assert "jump.className = 'jumplist'" in js or "className = 'jumplist'" in js
    assert "dippicksel" in js and "aria-controls" in js and "'show ' + n + ' dip'" in js
    # The shell's frame bridge no longer carries its own copy.
    assert FRAME_PHONE_CSS == ""
    for gone in ("function accordion", "function jumpToList", "jumplist"):
        assert gone not in FRAME_BRIDGE_JS, gone


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_standalone_docket_at_390px_has_no_control_under_44px(run_dir, tmp_path):  # noqa: F811
    page = docket_mod.build_docket(run_dir, tmp_path / "docket", title="t")
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s });
  const c = await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await c.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(%s, { waitUntil: 'load' }); await p.waitForFunction(() => document.documentElement.dataset.ready === '1', null, {timeout: 30000}).catch(() => {}); await p.waitForTimeout(600);
  const out = await p.evaluate(() => {
    const small = [];
    for (const e of document.querySelectorAll('a,button,summary,select,input,[tabindex="0"],[role="button"]')) {
      const r = e.getBoundingClientRect(); if (!r.width || !r.height) continue;
      if (getComputedStyle(e).visibility === 'hidden') continue;
      if (r.width < 44 || r.height < 44) small.push(`${e.tagName}.${e.className} ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
    const heads = [...document.querySelectorAll('#rows .sighead[role=button]')];
    return { small, hs: document.documentElement.scrollWidth > document.documentElement.clientWidth,
             jump: !!document.querySelector('.jumplist') && getComputedStyle(document.querySelector('.jumplist')).display !== 'none',
             picker: !!document.querySelector('#dippicksel') && document.querySelector('#dippicksel').getBoundingClientRect().height >= 44,
             heads: heads.length, controlled: heads.filter(h => h.hasAttribute('aria-expanded')).length };
  });
  out.errs = errs; console.log(JSON.stringify(out)); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(served(page))))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120, env={**os.environ})
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["small"] == [], out["small"]
    assert not out["hs"] and out["errs"] == []
    assert out["jump"] and out["picker"]
    assert out["heads"] and out["heads"] == out["controlled"]


def test_archived_report_nav_wraps_and_summaries_are_44px(run_dir, tmp_path):  # noqa: F811
    page = Path(build_report(run_dir, tmp_path / "report", title="t")).read_text()
    assert "<nav class='report-nav' aria-label='Sections'>" in page
    assert re.search(r"nav \.wrap\{display:flex;flex-wrap:wrap;gap:4px 14px", page)
    assert re.search(r"nav a\{[^}]*min-height:44px[^}]*min-width:44px|nav a\{[^}]*min-width:44px[^}]*min-height:44px", page)
    assert "summary{display:flex;align-items:center;min-height:44px" in page
    for label in ("Benchmark", "Provenance"):
        assert re.search(rf"<a href='#[^']+'>{label}</a>", page), label


def test_plate_labels_are_at_least_11px(run_dir, tmp_path):  # noqa: F811
    page = Path(build_plate(run_dir, tmp_path / "plate", title="t")).read_text()
    assert "svg text{font:11px" in page and "10.5px" not in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_plain_explorer_hash_stays_plain():
    sync = re.search(r"function syncFeedURL\(push\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    fns = re.search(r"const EX_SNR = .*?\nfunction encodeExView\(v\)\{.*?\n\}\n", APP_JS, re.S).group(0)
    script = ("const TICS = [1, 2]; let hash = null; const current = 'explorer';\n" + fns +
              "const setHash = (h, push) => { hash = h; };\n"
              "const encodeFeedView = v => `sort=${v.sort}&filter=${v.filter}`;\n"
              "const D = {feed_view: {default: {sort: 'snr', filter: 'all'}}};\n"
              "let FV = D.feed_view.default, EX = decodeExView(new URLSearchParams(''));\n"
              "const currentFeedView = () => FV, currentEx = () => EX;\n" + sync +
              "const out = []; syncFeedURL(false); out.push(hash);\n"
              "EX = Object.assign({}, EX, {snr: 8}); syncFeedURL(true); out.push(hash);\n"
              "FV = {sort: 'depth', filter: 'all'}; EX = decodeExView(new URLSearchParams('')); syncFeedURL(true); out.push(hash);\n"
              "console.log(JSON.stringify(out));")
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert out == ["#/explorer", "#/explorer?snr=8", "#/explorer?sort=depth&filter=all"]

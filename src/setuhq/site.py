# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The public site (https://setuhq.com): one pre-rendered page per address, sharing one stylesheet, one script
and one data file.

``setuhq site <run> --catalog <catalogue> --out site`` writes the whole of ``site/``:

* one directory per page with its own ``index.html`` (the map is in :mod:`setuhq.routes` and docs/SITE.md),
  each with its own title, description, canonical address and Open Graph tags, and its own view rendered in the
  HTML, so it reads without JavaScript;
* ``assets/``: the stylesheet, the script, the app's data and every view's markup (one file, so a page can switch
  to another view in place, by the History API), each named by its content hash so a browser may cache it for
  good; the fonts, the brand files and the data downloads;
* the run report, the plates and the stand-alone case file under /evidence/ and /candidates/;
* forwarding pages at every old address (/app/, /docket/, /plate/, /report/, /dashboard/, /discoveries/), a
  styled ``404.html`` that forwards old ``/app/#/...`` links too, ``sitemap.xml`` and ``robots.txt``.

Planet and star pages are pre-rendered for every planet and star the site names (the Methods chapters, the
Galaxy tour, the run's star); any other catalogue planet's address is drawn by the app from ``404.html``.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from pathlib import Path

from setuhq import brand, renderer
from setuhq.design import CROSSHAIR_JS, FONT_PRELOAD, MOTION_JS, tokens_css
from setuhq import i18n_auto
from setuhq.i18n import N_
from setuhq.minify import strip_css, strip_js
from setuhq.app import (APP_CSS, APP_JS, DEFAULT_SHOWCASE, DEFAULT_SWEEP, DEFAULT_WEIGHTS, FONTS_DIR, GALAXY_JSON, NAV, ROUTE_META, SUBNAV,
                        UNCONFIRMED, app_data, app_payload, dip_state, galaxy_json, route_sections)
from setuhq.catalogue import CATALOGUE_JSON, SEARCH_BUTTON, SEARCH_DIALOG
from setuhq.codenote import technical_note_html
from setuhq.galaxy import CSV_NAME, map_csv
from setuhq.learn import LEARN_BAR
from setuhq.methods import CHAPTER_PLANETS, CHAPTERS, system_stage
from setuhq.names import ATTRIBUTION
from setuhq.objects import slugify
from setuhq.everything import VARIABLES_JSON
from setuhq.routes import CHAPTER_SLUGS, LEGACY_PAGES, ROUTE_PATHS, ROUTES_APP_JS, from_hash, legacy_js, url_for
from setuhq.stubs import stored
from setuhq.looks import BANDS, COMPOSITION_RULES, LOOKS, rule_words
from setuhq import editions, features, i18n, journey, stellarpages, tessnow, vetter, viz

REPO_URL = brand.REPO_URL
# Each page's HTML (its own view, the shell, the head) stays under this many characters; everything shared is a
# cached file. The old single app page was about 1.4 million.
PAGE_BUDGET = 200_000
THEME_KEY = "setuhq-theme"
# Before first paint: the stored theme choice (system, light or dark), so the page never flashes.
THEME_HEAD_JS = ("(function(){var t='dark';try{var s=localStorage.getItem('" + THEME_KEY + "');"
                 "if(s==='light'||s==='system')t=s;}catch(e){}document.documentElement.setAttribute('data-theme',t);})();")

ICON_THEME = ('<svg class="ti ti-dark" viewBox="0 0 20 20" aria-hidden="true"><path d="M15.5 12.6A6.5 6.5 0 0 1 7.4 4.5a6.5 6.5 0 1 0 8.1 8.1z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>'
              '<svg class="ti ti-light" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="3.6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
              '<path d="M10 1.8v2.4M10 15.8v2.4M1.8 10h2.4M15.8 10h2.4M4.2 4.2l1.7 1.7M14.1 14.1l1.7 1.7M4.2 15.8l1.7-1.7M14.1 5.9l1.7-1.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
              '<svg class="ti ti-system" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="6.6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
              '<path d="M10 3.4a6.6 6.6 0 0 1 0 13.2z" fill="currentColor"/></svg>')
ICON_MENU = ('<svg class="mi-open" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>'
             '<svg class="mi-close" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>')

SITE_CSS = r"""
/* ---------- the site shell: top bar, menu, breadcrumbs, sub-navigation, footer ---------- */
.topbar{display:block;position:sticky;top:0;z-index:40;padding:env(safe-area-inset-top,0px) max(16px,env(safe-area-inset-right,0px)) 0 max(16px,env(safe-area-inset-left,0px));background:color-mix(in oklab,var(--bg) 78%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);border-bottom:1px solid var(--line)}
.tbin{max-width:1280px;margin:0 auto;display:flex;align-items:center;gap:12px;min-height:60px}
.tbin .brand{flex:none;padding:0;align-self:center;transform:none}
.brand .brandname{line-height:1.2}
.nav{flex:1 1 auto;display:flex;justify-content:center;min-width:0}
.nav ul{padding:3px}
.nav a{min-height:38px;padding:0 16px;font-size:14px}
.nav a[aria-current="page"]{background:var(--seg-bg);color:var(--seg-ink)}
.tools{display:flex;align-items:center;gap:2px;margin-left:auto;flex:none}
.iconbtn{width:44px;height:44px;border-radius:999px;border:1px solid transparent;background:transparent;color:var(--ink-2);display:inline-grid;place-items:center;cursor:pointer;padding:0;transition:background-color var(--d-1) var(--ease),color var(--d-1) var(--ease)}
.iconbtn:hover{color:var(--ink);background:var(--panel-2)}
.iconbtn svg{width:20px;height:20px;display:block}
.iconbtn kbd{display:none}
.themebtn .ti{display:none}
:root[data-theme="dark"] .themebtn .ti-dark,:root[data-theme="light"] .themebtn .ti-light,:root[data-theme="system"] .themebtn .ti-system{display:block}
.menubtn{display:none}
.menubtn .mi-close,.menubtn[aria-expanded="true"] .mi-open{display:none}
.menubtn[aria-expanded="true"] .mi-close{display:block}
.menu{position:absolute;left:0;right:0;top:100%;background:var(--bg-2);border-bottom:1px solid var(--line-2);box-shadow:0 24px 40px -24px rgba(0,0,0,.6);max-height:calc(100vh - var(--top,60px));max-height:calc(100dvh - var(--top,60px));overflow-y:auto;overscroll-behavior:contain;padding:8px max(16px,env(safe-area-inset-right,0px)) max(16px,env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px))}
.menu[hidden]{display:none}
.menu ul{list-style:none;margin:0;padding:0}
.menu>nav>ul{display:grid;gap:4px}
.menu .msec{border-top:1px solid var(--line);padding:6px 0 10px}
.menu .msec:first-child{border-top:0}
.menu .msec>a{display:flex;align-items:center;min-height:48px;padding:0 8px;border-radius:12px;color:var(--ink);text-decoration:none;font-size:18px;font-weight:600;letter-spacing:-.02em}
.menu .msec>a[aria-current="page"]{color:var(--cyan)}
.menu .msub{display:flex;flex-wrap:wrap;gap:6px;padding:0 8px}
.menu .msub a{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid var(--line);border-radius:999px;color:var(--ink-2);text-decoration:none;font-size:14px}
.pagebar{padding:14px clamp(16px,3vw,40px) 0}
.pbin{max-width:1280px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px}
.crumbs{flex:1 1 100%}
.crumbs[hidden]{display:none}
.crumbs ol{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;align-items:center;font-size:13px;color:var(--ink-3)}
.crumbs li{display:inline-flex;align-items:center;min-width:0}
.crumbs li+li::before{content:"›";margin:0 8px;color:var(--ink-3)}
.crumbs a{color:var(--ink-2);text-decoration:none;display:inline-flex;align-items:center;min-height:32px}
.crumbs a:hover{color:var(--ink);text-decoration:underline}
.crumbs li[aria-current]{color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:40ch}
.subnav{display:flex;flex-wrap:wrap;gap:6px;min-width:0}
.subnav[hidden]{display:none}
.subnav a{display:inline-flex;align-items:center;min-height:36px;padding:0 14px;border-radius:999px;border:1px solid var(--line);color:var(--ink-2);text-decoration:none;font-size:13px;font-weight:500;white-space:nowrap}
.subnav a:hover{color:var(--ink);border-color:var(--line-3)}
.subnav a[aria-current="page"]{background:var(--seg-bg);color:var(--seg-ink);border-color:transparent}
.pagetools{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.pagetools .btn[hidden]{display:none}
main{padding-top:24px}
body[data-route="overview"] main{padding-top:8px}
.provnote{margin:0;max-width:90ch;color:var(--ink-2)}
.proof b{color:var(--c)}
:root[data-theme="light"] .proof b{color:color-mix(in oklab,var(--c) 42%,#000)}
@media (prefers-color-scheme: light){:root[data-theme="system"] .proof b{color:color-mix(in oklab,var(--c) 42%,#000)}}
.provnote a{color:var(--ink-2)}
/* the home page */
.route>header.launch{padding:28px 0 0}
.launch h1{margin:0;font-size:clamp(44px,7vw,96px)}
.route>header.launch .sub{margin:16px auto 0}
.launch .ctas{margin-top:24px}
.sweepline{margin:0;font-size:17px;line-height:1.5;color:var(--ink-2);max-width:72ch}
.sweepline a{white-space:nowrap}
.proof{margin:0 auto}
.dohere{display:grid;gap:14px}
.dohere h2{font-size:15px;color:var(--ink-3);font-weight:500}
.docards{list-style:none;margin:0;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr))}
.docard{position:relative;display:flex;flex-direction:column;gap:6px;height:100%;padding:18px 40px 18px 18px;border-radius:20px;border:1px solid var(--line);background:var(--glass);-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px);color:var(--ink);text-decoration:none;transition:border-color var(--d-1) var(--ease),transform var(--d-2) var(--ease)}
.docard:hover{border-color:var(--line-3);color:var(--ink);transform:translateY(-2px)}
.docard b{font-size:17px;font-weight:600;letter-spacing:-.02em}
.docard span{font-size:13.5px;line-height:1.45;color:var(--ink-2)}
.docard i{position:absolute;right:16px;top:16px;font-style:normal;font-size:20px;color:var(--cyan)}
/* the home page's worked examples: one card per stored run */
.examples{display:grid;gap:14px}
.excards{list-style:none;margin:0;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))}
.excard{display:flex;flex-direction:column;gap:6px;height:100%;padding:18px;border-radius:20px;border:1px solid var(--line);background:var(--glass);-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px)}
.excard p{margin:0}
.excard h3{margin:0;font-size:22px;font-weight:600;letter-spacing:-.02em}
.excard h3 a{color:var(--ink);text-decoration:none;display:inline-flex;align-items:center;min-height:32px}
.excard h3 a:hover{text-decoration:underline}
.exkind{font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--cyan)}
:root[data-theme="light"] .exkind{color:color-mix(in oklab,var(--cyan) 45%,#000)}
@media (prefers-color-scheme: light){:root[data-theme="system"] .exkind{color:color-mix(in oklab,var(--cyan) 45%,#000)}}
.exsum{font-size:14px;line-height:1.45;color:var(--ink-2)}
.excount{font-size:14px;font-weight:600;color:var(--ink)}
.exmeta{font-size:12.5px;color:var(--ink-3)}
.exlinks{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:auto!important;padding-top:6px}
.exlinks a,.runlinks a{display:inline-flex;align-items:center;min-height:32px;font-size:13.5px}
.runlinks{display:flex;flex-wrap:wrap;gap:4px 16px}
.refcheck{display:grid;gap:14px}
.excaveat{font-size:13px;line-height:1.45;color:var(--ink-2);border-left:2px solid var(--yellow);padding-left:8px}
/* Candidates: the dips a visitor can open, the cards behind Customise, the feed's compact table */
.rundiplist{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.rundiplist li{display:flex;align-items:stretch;gap:8px}
.rundip{flex:1;min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;align-items:center;padding:10px 14px;border:1px solid var(--line);border-radius:14px;color:var(--ink);text-decoration:none;background:var(--panel-2)}
.rundip:hover{border-color:var(--line-3);color:var(--ink)}
.rundip b{font-weight:600;font-size:15px}
.rundip .muted{grid-column:1;font-size:13px}
.rundip .tag{grid-row:1/3;grid-column:2}
.rundipcf{display:inline-flex;align-items:center;padding:0 14px;border:1px solid var(--line);border-radius:14px;text-decoration:none;font-size:13px;white-space:nowrap}
.tag.cand{color:var(--yellow);border-color:color-mix(in oklab,var(--yellow) 35%,transparent);background:color-mix(in oklab,var(--yellow) 8%,transparent)}
.tag.rej{color:var(--red);border-color:color-mix(in oklab,var(--red) 35%,transparent);background:color-mix(in oklab,var(--red) 8%,transparent)}
.tag.open{color:var(--ink-2)}
.secthead #customise{margin-left:auto}
#widgets:not(.customising) .wctl{display:none}
#layouttools[hidden]{display:none}
.feedsec{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;min-width:0}
.feedsec>*,.feedsec .row2>*{min-width:0}
.feedsec .row2{align-items:start}
.exfilters{align-items:flex-start}
.exfilters>div{justify-content:flex-start}
.scatter.astable{padding-bottom:0}
table.excompact{font:13px var(--sans);color:var(--ink)}
table.excompact th,table.excompact td{border-bottom:1px solid var(--line)}
table.excompact th button{display:inline-flex;align-items:center;gap:8px;min-height:44px;background:none;border:0;padding:0;color:var(--ink);font:500 14px var(--sans);cursor:pointer;text-transform:none;letter-spacing:0}
table.excompact th button i{width:9px;height:9px;border-radius:50%;background:var(--c)}
table.excompact th button[aria-pressed="true"]{text-decoration:underline;text-underline-offset:4px}
/* prose pages: Docs and Page not found */
.prose{display:grid;gap:10px;max-width:880px}
.prose h2{font-size:22px;margin-top:22px}
.prose p,.prose li{color:var(--ink-2);line-height:1.6;max-width:75ch}
.prose ul,.prose ol{margin:0;padding-left:22px;display:grid;gap:6px}
.prose pre{margin:0;padding:12px 14px;border-radius:12px;background:var(--panel);border:1px solid var(--line);overflow-x:auto;font-size:13px;line-height:1.5;white-space:pre}
.prose code{font-size:.92em}
.docgrid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr))}
.docgrid .card h2{font-size:17px;margin:0 0 6px}
.docgrid .card p{margin:0 0 8px;font-size:14px}
.technote{margin:0;padding:12px 16px;border-left:3px solid var(--line-3);background:var(--panel-2);border-radius:0 12px 12px 0}
.technote p{margin:0;font:13px/1.55 var(--mono);color:var(--ink-2)}
.nfsearch{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
/* How the pictures are drawn: the look grid and the rule tables */
.lookintro{margin:0 0 12px;max-width:90ch;color:var(--ink-2)}
.lookgrid{list-style:none;margin:0;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(min(100%,180px),1fr))}
.lookgrid .rfig{border-radius:var(--r-m)}
.lookgrid .readout{font-size:12px}
.lookgrid .readout b{display:block;color:var(--stage-ink);font:600 13px/1.3 var(--sans);margin-bottom:2px}
.rendrow{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))}
.rendrow .rbox{aspect-ratio:4/3}
.looktable td,.looktable th{white-space:normal;font-family:var(--sans);font-size:13px}
.looktable th code{font:var(--t-data)}
.swatch{display:inline-block;width:18px;height:18px;border-radius:50%;margin-right:8px;vertical-align:-4px;border:1px solid var(--line-2)}
.nfcards .docard span{font-size:13.5px}
/* the footer */
.sitefoot{border-top:1px solid var(--line);margin-top:24px;padding:28px max(16px,env(safe-area-inset-right,0px)) max(28px,env(safe-area-inset-bottom,0px)) max(16px,env(safe-area-inset-left,0px));background:color-mix(in oklab,var(--bg) 86%,transparent)}
.fin{max-width:1280px;margin:0 auto;display:grid;gap:18px}
.footnav{display:grid;gap:18px 24px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.footnav h2{font-size:13px;font-weight:600;color:var(--ink);margin:0 0 6px}
.footnav ul{list-style:none;margin:0;padding:0;display:grid;gap:0}
.footnav a{display:inline-flex;align-items:center;min-height:32px;color:var(--ink-2);text-decoration:none;font-size:13px}
.footnav a:hover{color:var(--ink);text-decoration:underline}
.sitefoot p{margin:0;font-size:12.5px;color:var(--ink-3);max-width:100ch}
.sitefoot .attribution{color:var(--ink-2)}
@media (max-width:899.98px){
  .nav{display:none}
  .menubtn{display:inline-grid}
  .tbin{min-height:56px;gap:4px}
}
@media (max-width:699.98px){
  .topbar{padding-top:env(safe-area-inset-top,0px)}
  .pagebar{padding:10px 16px 0}
  .pbin{gap:8px}
  body[data-route="candidates"] #route-candidates>.provnote{margin:8px 16px;flex:none}
  main a.rundip{display:grid;padding:10px 14px;line-height:1.4}
  main a.rundipcf{display:inline-flex;padding:0 12px}
  .rundiplist li{flex-direction:column}
  .rundipcf{min-height:44px;justify-content:center}
  .scatter.astable{overflow-x:auto}
  main .provnote a{display:inline;min-height:0;min-width:0;padding:0;line-height:inherit}
  main{padding-top:16px}
  .subnav{gap:6px}
  .subnav a{min-height:44px;padding:0 12px}
  .crumbs a{min-height:44px}
  .footnav a{min-height:44px}
  .route>header.launch{padding-top:12px}
  .proof{margin-top:0}
  .docard{padding:16px 40px 16px 16px}
  main a.docard{display:flex;padding:16px 40px 16px 16px;line-height:1.45}
  main .subnav a,main .pagetools .btn{display:inline-flex;padding-top:0;padding-bottom:0}
}
"""

SHELL_JS = r"""
// ---------- the shell: theme, menu, and the app's start ----------
// Runs on every page before the app's data arrives, so the header works at once.
const SETUHQ_THEMES = ['dark', 'light', 'system'], TT = (id, en, a) => (window.SetuI18n ? SetuI18n.T(id, en, a) : en).replace(/&#(\d+);/g, (x, d) => String.fromCharCode(d));
const THEME_SAY = {get dark(){ return TT('shell.theme.dark', 'dark'); }, get light(){ return TT('shell.theme.light', 'light'); }, get system(){ return TT('shell.theme.system', 'your device\'s setting'); }};
function currentTheme(){ const t = document.documentElement.getAttribute('data-theme'); return SETUHQ_THEMES.includes(t) ? t : 'dark'; }
function applyTheme(t, announce){
  document.documentElement.setAttribute('data-theme', t);
  try { if (t === 'dark') localStorage.removeItem('setuhq-theme'); else localStorage.setItem('setuhq-theme', t); } catch (e) { /* storage blocked: the theme lasts for this visit */ }
  const next = SETUHQ_THEMES[(SETUHQ_THEMES.indexOf(t) + 1) % SETUHQ_THEMES.length];
  const say = TT('shell.theme.title', 'Theme: {t}', {t: THEME_SAY[t]});
  for (const b of document.querySelectorAll('[data-theme-toggle]')){ b.setAttribute('aria-label', TT('shell.theme.label', 'Colour theme: {t}. Switch to {next}', {t: THEME_SAY[t], next: THEME_SAY[next]})); b.title = say; }
  if (announce){ const a = document.getElementById('announce'); if (a){ a.textContent = ''; setTimeout(() => { a.textContent = say + '.'; }, 30); } }
  document.dispatchEvent(new CustomEvent('setuhq-theme', {detail: t}));
}
function closeMenu(focusButton){
  const m = document.getElementById('menu'), b = document.getElementById('menubtn');
  if (!m || m.hidden) return;
  m.hidden = true; b.setAttribute('aria-expanded', 'false'); b.setAttribute('aria-label', TT('shell.menu_open', 'Open the menu'));
  if (focusButton) b.focus();
}
function openMenu(){
  const m = document.getElementById('menu'), b = document.getElementById('menubtn');
  m.hidden = false; b.setAttribute('aria-expanded', 'true'); b.setAttribute('aria-label', TT('shell.menu_close', 'Close the menu'));
  const first = m.querySelector('a'); if (first) first.focus();
}
function initShell(){
  for (const b of document.querySelectorAll('[data-theme-toggle]')) b.addEventListener('click', () => applyTheme(SETUHQ_THEMES[(SETUHQ_THEMES.indexOf(currentTheme()) + 1) % SETUHQ_THEMES.length], true));
  applyTheme(currentTheme(), false);
  const mb = document.getElementById('menubtn'), m = document.getElementById('menu');
  if (mb && m){
    mb.addEventListener('click', () => { if (m.hidden) openMenu(); else closeMenu(true); });
    document.addEventListener('keydown', e => {
      if (m.hidden) return;
      if (e.key === 'Escape'){ e.preventDefault(); closeMenu(true); return; }
      if (e.key === 'Tab'){  // keep the keyboard inside the open menu and its button
        const items = [mb, ...m.querySelectorAll('a')], i = items.indexOf(document.activeElement);
        if (e.shiftKey && i <= 0){ e.preventDefault(); items[items.length - 1].focus(); }
        else if (!e.shiftKey && i === items.length - 1){ e.preventDefault(); items[0].focus(); }
      }
    });
    document.addEventListener('click', e => { if (!m.hidden && !m.contains(e.target) && !mb.contains(e.target)) closeMenu(false); });
    m.addEventListener('click', e => { if (e.target.closest('a')) setTimeout(() => closeMenu(false), 0); });
    window.addEventListener('resize', () => { if (window.innerWidth >= 900) closeMenu(false); });
  }
}
function bootApp(){
  // The app: its data and every view's markup are two shared files (cached across pages). The page's own view
  // is already here, rendered at build time; the others join it hidden, so a link can change the view in place.
  const b = document.body.dataset;
  if (!b.data || !b.routes || !b.app) return;
  Promise.all([fetch(b.data).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }),
               fetch(b.routes).then(r => { if (!r.ok) throw new Error(r.status); return r.text(); }), window.SetuI18n && SetuI18n.ready]).then(([D, routes]) => {
    const tpl = document.createElement('template'); tpl.innerHTML = routes;
    const content = document.getElementById('content');
    const sys = tpl.content.querySelector('template#mxsystpl');
    if (sys && !document.getElementById('mxsystpl')) document.body.appendChild(sys);
    for (const sec of Array.from(tpl.content.querySelectorAll('section.route'))){
      const mine = document.getElementById(sec.id);
      if (mine && !mine.hasAttribute('data-partial')) continue;
      if (mine){ sec.hidden = mine.hidden; mine.replaceWith(sec); }
      else { sec.hidden = true; content.appendChild(sec); }
      if (window.SetuI18n) SetuI18n.apply(sec);
    }
    // The app's code reads D; it runs as a script of its own (cached across pages, and its names stay global).
    window.D = D;
    const s = document.createElement('script');
    s.src = b.app;
    s.onload = () => { document.documentElement.dataset.ready = '1'; };
    s.onerror = () => { const n = document.getElementById('bootnote'); if (n) n.hidden = false; };
    document.body.appendChild(s);
  }).catch(err => {
    // The page's own text stays readable; only the interactive parts are missing.
    const n = document.getElementById('bootnote'); if (n) n.hidden = false;
    console.warn('SetuHQ: the interactive views could not load', err);
  });
}
(function(){
  // A small page (a catalogue planet or star written at deploy time, setuhq.stubs) carries no header or footer of
  // its own: the shared chrome file (cached like the rest) is put in place first.
  const c = document.body.dataset.chrome;
  if (!c){ initShell(); bootApp(); if (window.SetuI18n) SetuI18n.ready.then(() => applyTheme(currentTheme(), false)); return; }
  // A small page loads the languages' script itself (its template stays within the stubs' budget).
  (window.SetuI18n || typeof I18N_SRC === 'undefined' ? Promise.resolve() : new Promise(ok => { const s = document.createElement('script'); s.src = I18N_SRC; s.onload = s.onerror = ok; document.head.appendChild(s); }))
  .then(() => fetch(c)).then(r => { if (!r.ok) throw new Error(r.status); return r.text(); }).then(t => {
    const tpl = document.createElement('template'); tpl.innerHTML = t;
    const top = tpl.content.querySelector('[data-chrome-part="top"]'), bottom = tpl.content.querySelector('[data-chrome-part="bottom"]');
    if (top) document.getElementById('chrome-top').replaceWith(...top.childNodes);
    if (bottom) document.getElementById('chrome-bottom').replaceWith(...bottom.childNodes);
  }).catch(err => console.warn('SetuHQ: the header could not load', err)).then(() => (window.SetuI18n && SetuI18n.ready)).then(() => {
    if (window.SetuI18n){ SetuI18n.apply(document.body); if (SetuI18n.lang !== 'en') for (const n of document.querySelectorAll('.mtnote')) n.hidden = false; }
    initShell(); bootApp(); });
})();
""" + MOTION_JS + CROSSHAIR_JS + features.SHELL_JS


def _sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()[:10]


def clean_links(markup: str, lead: str | None = None) -> str:
    """Every ``href="#/..."`` (the views' internal names for a place) as its clean address."""
    return re.sub(r'href="#/([^"]*)"', lambda m: f'href="{html.escape(from_hash("#/" + html.unescape(m.group(1)), lead=lead))}"', markup)


# ---------------------------------------------------------------------------------------------------------
# The shell: head, top bar, menu, page bar, footer
# ---------------------------------------------------------------------------------------------------------

def _nav_html() -> str:
    items = "".join(f'<li><a href="{from_hash(h)}" data-nav="{k}"{i18n.k("nav." + k)}>{html.escape(label)}</a></li>' for k, label, h in NAV)
    return f'<nav class="nav" aria-label="{i18n.t("shell.nav_main", "Main")}"{i18n.ka(aria_label="shell.nav_main")}><ul>{items}</ul></nav>'


def _menu_html(lead: str | None) -> str:
    secs = []
    for k, label, h in NAV:
        subs = "".join(f'<li><a href="{html.escape(from_hash(sh, lead=lead) if sh.startswith("#/") else sh)}"{i18n.k("subnav." + rs[0])}>{html.escape(sl)}</a></li>'
                       for sl, sh, rs in SUBNAV.get(k, []))
        secs.append(f'<li class="msec"><a href="{from_hash(h)}" data-nav="{k}"{i18n.k("nav." + k)}>{html.escape(label)}</a>'
                    + (f'<ul class="msub">{subs}</ul>' if subs else "") + "</li>")
    return f'<div class="menu" id="menu" hidden><nav aria-label="Main"{i18n.ka(aria_label="shell.nav_main")}><ul>{"".join(secs)}</ul></nav></div>'


def _footer_html(lead: str | None) -> str:
    cols = []
    for k, label, h in NAV:
        links = [(("subnav.docs", i18n.t("subnav.docs", "Get started")) if k == "docs" else ("footer.overview", i18n.t("footer.overview", "Overview")), from_hash(h))] if k in ("how", "docs") else []
        links += [(("subnav." + rs[0], sl), from_hash(sh, lead=lead) if sh.startswith("#/") else sh) for sl, sh, rs in SUBNAV.get(k, []) if sh != h and sh != "#/pictures"]
        if k == "how":
            links += [(("chapter." + c, t), url_for("methods", {"ch": c})) for c, t in CHAPTERS[1:5]]
            links += [(("footer.all_chapters", i18n.t("footer.all_chapters", "All {n} chapters", n=len(CHAPTERS)), {"n": len(CHAPTERS)}), from_hash(h))]
        if k == "docs":
            links += [(("footer.pictures", i18n.t("footer.pictures", "How the pictures are drawn ›")), "/docs/pictures/"),
                      (("footer.source", i18n.t("footer.source", "Source code")), REPO_URL),
                      (("footer.contribute", i18n.t("footer.contribute", "Contributing a sweep")), "/docs/#contribute"),
                      (("footer.data", i18n.t("footer.data", "Data downloads")), "/docs/#data")]
        rel = ' rel="noopener"'
        lis = "".join(f'<li><a{rel if u.startswith("http") else ""} href="{html.escape(u)}"{i18n.k(m[0], **(m[2] if len(m) > 2 else {}))}>{html.escape(m[1])}</a></li>' for m, u in links)
        cols.append(f'<div><h2{i18n.k("nav." + k)}>{html.escape(label)}</h2><ul>{lis}</ul></div>')
    return f"""<footer class="sitefoot"><div class="fin">
  <nav class="footnav" aria-label="{i18n.t("footer.nav", "Site")}"{i18n.ka(aria_label="footer.nav")}>{"".join(cols)}</nav>
  <p class="attribution"{i18n.k("honesty.attribution")}>{html.escape(ATTRIBUTION)}</p>
  <p{i18n.k("honesty.footer")}>{i18n.t("honesty.footer", 'Every SetuHQ result on this site is a candidate, never a confirmed planet. Open source under the AGPL-3.0; SetuHQ\'s data under CC BY 4.0. "SetuHQ" and the Setu mark are trademarks of Ashforde OÜ.', note="The footer's honesty line. Keep 'a candidate, never a confirmed planet' exactly as strong; licence names stay as written.")}</p>
  <p class="mtnote"{i18n.k("i18n.mtnote")} hidden>{i18n.t("i18n.mtnote", 'This translation is machine-assisted and has not yet been reviewed by a native speaker. <a rel="noopener" href="https://github.com/ashfordeOU/SetuHQ/blob/main/docs/TRANSLATING.md">Corrections are welcome</a>.', note="Shown on every translated page. Say plainly that the translation was made with machine assistance and is not yet reviewed.")}</p>
</div></footer>"""


def _head(title: str, description: str, path: str | None, assets: dict, *, extra: str = "", noindex: bool = False,
          keys: tuple | None = None) -> str:
    """The head. ``keys`` (title id, its arguments, description id, its arguments) keys the title and description
    to their messages; a page with an address in every language (MAIN_PATHS) lists them all (hreflang)."""
    meta = brand.head(title, description, path or "/", prefix="/")
    if path is None:  # a page with no address of its own (404, a forwarding page): no canonical
        meta = re.sub(r'<link rel="canonical"[^>]*>\n?', "", meta)
    tkey = ""
    if keys:
        tid, targs, did, dargs = keys
        tkey = i18n.k(tid, **targs) if tid else ""
        dk = (' data-i18n-attr="content:' + did + '"' + i18n.kargs(**dargs)) if did else ""
        tk = (' data-i18n-attr="content:' + tid + '"' + i18n.kargs(**targs)) if tid else ""
        meta = re.sub(r'(<meta (?:name|property)="(?:description|og:description|twitter:description)" content="[^"]*")>', lambda m: m.group(1) + dk + ">", meta)
        meta = re.sub(r'(<meta (?:property|name)="(?:og:title|twitter:title)" content="[^"]*")>', lambda m: m.group(1) + tk + ">", meta)
    if path in MAIN_PATHS:
        meta += "\n" + alternates(path)
    return f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title{tkey}>{html.escape(title)}</title>
{meta}
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#04060B">
<meta name="view-transition" content="same-origin">
{extra}<script>{THEME_HEAD_JS}</script>
<link rel="preload" href="{FONT_PRELOAD}" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/fonts/fonts.css">
<link rel="stylesheet" href="{assets['css']}">
<link rel="preload" href="{assets['data']}" as="fetch" crossorigin="anonymous">
<link rel="preload" href="{assets['app']}" as="script">
<script src="{assets['render']}" defer></script>
<script src="{assets['i18n']}" defer></script>
<script src="{assets['js']}" defer></script>
<script type="speculationrules">{SPECULATION}</script>
</head>"""


# S03: the stand-alone pages (case files, plates, reports) are fetched ahead when a link to one is likely; the
# app's own views need nothing, as they share the loaded data.
SPECULATION = json.dumps({"prefetch": [{"where": {"href_matches": ["/candidates/*/case-file/", "/evidence/plates/*", "/evidence/report/*"]},
                                        "eagerness": "moderate"}]}, separators=(",", ":"))


def starfield_html(src: str) -> str:
    """V11: the background starfield. The SVG is the still (no JavaScript, reduced motion); the renderer draws the
    seeded canvas field over the top of the page. Decorative."""
    return (f'<div class="starfield" data-render="starfield" data-params=\'{{"seed":314}}\' aria-hidden="true">'
            f'<img class="rstill" src="{src}" alt=""></div>')


ICON_LANG = ('<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.2" fill="none" stroke="currentColor" stroke-width="1.5"/>'
             '<path d="M2.8 10h14.4M10 2.8c2.2 2.2 2.9 4.6 2.9 7.2s-.7 5-2.9 7.2c-2.2-2.2-2.9-4.6-2.9-7.2s.7-5 2.9-7.2z" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>')
# The pages with an address in every language: every section page and every chapter. The others (a dip, a case file,
# a planet, a star, the reports) keep one address and are translated in the browser, with the visitor's choice.
MAIN_PATHS = tuple(sorted(set(ROUTE_PATHS.values()) | {url_for("methods", {"ch": c}) for c, _ in CHAPTERS}))


def lang_path(path: str, lang: str) -> str:
    """A page's address in ``lang``: English at the root, every other language under /<lang>/."""
    return path if lang == i18n.SOURCE else f"/{lang}{path}"


def alternates(path: str) -> str:
    """The hreflang links of a page that has an address in every language (and x-default, the English)."""
    links = [f'<link rel="alternate" hreflang="{l}" href="{brand.SITE_URL}{lang_path(path, l)}">' for l in i18n.LOCALES]
    return "".join(links) + f'<link rel="alternate" hreflang="x-default" href="{brand.SITE_URL}{path}">'


def _langcode(lang: str) -> str:
    return "ZH" if lang == "zh-Hans" else lang.upper()


def langpick(path: str | None, lang: str = "en") -> str:
    """The language picker: every language by its own name, linking to this page in it (a page with one address
    links to itself; the choice then applies in the browser), and the machine-translation note."""
    e = html.escape
    items = "".join(f'<li><a href="{e(lang_path(path, l) if path in MAIN_PATHS else (path or "/"))}" data-lang="{l}" hreflang="{l}" lang="{l}"'
                    f'{" aria-current=" + chr(34) + "true" + chr(34) if l == lang else ""}>{e(i18n.NATIVE[l])}</a></li>' for l in i18n.LOCALES)
    with i18n.use(lang):
        label = i18n.t("i18n.picker.label", "Language: {name}", name=i18n.NATIVE[lang])
        note = i18n.th("i18n.picker.note", 'Every language but English is machine-assisted and not yet reviewed by a native speaker. <a rel="noopener" href="https://github.com/ashfordeOU/SetuHQ/blob/main/docs/TRANSLATING.md">Corrections are welcome</a>.',
                       note="In the language picker, in each language. Plain: machine-assisted, not yet reviewed by a native speaker.")
    return (f'<details class="langpick"><summary class="iconbtn" aria-label="{e(label)}" title="{e(label)}"{i18n.ka(aria_label="i18n.picker.label", title="i18n.picker.label")}'
            f"{i18n.kargs(name=i18n.NATIVE[lang])}>"
            f'{ICON_LANG}<span class="langcode">{_langcode(lang)}</span></summary>'
            f'<div class="langmenu"><ul>{items}</ul><p class="langnote">{note}</p></div></details>')


def _topbar(lead: str | None, path: str | None = None) -> str:
    return f"""<a class="skip" href="#content"{i18n.k("shell.skip")}>{i18n.t("shell.skip", "Skip to content")}</a>
<header class="topbar">
  <div class="tbin">
    <a class="brand" href="/" aria-label="{i18n.t("shell.home", "SetuHQ, home")}"{i18n.ka(aria_label="shell.home")}>{brand.logo("/")}</a>
    {_nav_html()}
    <div class="tools">
      {SEARCH_BUTTON}
      {langpick(path)}
      <button class="iconbtn themebtn" type="button" data-theme-toggle aria-label="Colour theme: dark. Switch to light" title="Theme: dark">{ICON_THEME}</button>
      <button class="iconbtn menubtn" type="button" id="menubtn" aria-expanded="false" aria-controls="menu" aria-label="{i18n.t("shell.menu_open", "Open the menu")}"{i18n.ka(aria_label="shell.menu_open")}>{ICON_MENU}</button>
    </div>
  </div>
  {_menu_html(lead)}
</header>"""


def _crumbs(route: str, name: str | None, params: dict, lead: str | None) -> str:
    m = ROUTE_META.get(route, {})
    chain = [(label, from_hash(h, lead=lead), CRUMB_IDS.get(label)) for label, h in m.get("crumbs", [])]
    if route == "methods" and params.get("ch") and params["ch"] != CHAPTERS[0][0]:
        chain.append(("How it works", "/how-it-works/", "nav.how"))
    if route == "candidates" and params.get("dip"):
        chain.append((name_of_dip(params["dip"]), url_for("transit", {"dip": params["dip"]}), None))
    bc = f'aria-label="{i18n.t("shell.breadcrumb", "Breadcrumb")}"{i18n.ka(aria_label="shell.breadcrumb")}'
    if not chain:
        return f'<nav class="crumbs" id="crumbs" {bc} hidden></nav>'
    here = "Case file" if route == "candidates" else (name or m.get("label", ""))
    hid = "route.candidates.label" if route == "candidates" else (None if name else f"route.{route}.label")
    if route == "methods" and params.get("ch"):
        hid = "chapter." + params["ch"]
    lis = "".join(f'<li><a href="{html.escape(u)}"{i18n.k(c) if c else ""}>{html.escape(t)}</a></li>' for t, u, c in chain)
    return (f'<nav class="crumbs" id="crumbs" {bc}><ol>{lis}'
            f'<li aria-current="page"{i18n.k(hid) if hid else ""}>{html.escape(here)}</li></ol></nav>')


CRUMB_IDS = {"Explore": "nav.explore", "Candidates": "nav.candidates", "Evidence": "nav.evidence", "Docs": "nav.docs",
             "Catalogue": "route.catalogue.label", "How it works": "nav.how"}


def _subnav(route: str, lead: str | None) -> str:
    items = SUBNAV.get(ROUTE_META.get(route, {}).get("nav") or "", [])
    lab = f'aria-label="{i18n.t("shell.in_section", "In this section")}"{i18n.ka(aria_label="shell.in_section")}'
    if not items:
        return f'<nav class="subnav" id="subnav" {lab} hidden></nav>'
    cur = ' aria-current="page"'
    links = "".join(f'<a href="{html.escape(from_hash(h, lead=lead) if h.startswith("#/") else h)}"'
                    f'{cur if route in rs else ""}{i18n.k("subnav." + rs[0])}>{html.escape(label)}</a>' for label, h, rs in items)
    return f'<nav class="subnav" id="subnav" {lab}>{links}</nav>'


DIP_LABELS: dict[str, str] = {}


def name_of_dip(dip: str) -> str:
    return DIP_LABELS.get(dip, dip)


VIEW_STATE_ROUTES = ("explorer", "sky", "galaxy", "catalogue", "variables")


def _pagebar(route: str, name: str | None, params: dict, lead: str | None) -> str:
    tools = (f'<div class="pagetools"><button class="btn" type="button" id="copyview"{"" if route in VIEW_STATE_ROUTES else " hidden"}{i18n.k("shell.copy_view")}>{i18n.t("shell.copy_view", "Copy link to this view")}</button>'
             '<span class="muted" id="copyviewstate" role="status"></span>'
             f'<input class="copyfallback" id="copyviewbox" type="text" readonly aria-label="{i18n.t("shell.view_link", "Link to this view")}"{i18n.ka(aria_label="shell.view_link")} hidden></div>')
    return f'<div class="pagebar"><div class="pbin">{_crumbs(route, name, params, lead)}{_subnav(route, lead)}{tools}</div></div>'


def page(*, route: str, title: str, description: str, path: str | None, body: str, assets: dict, lead: str | None,
         name: str | None = None, params: dict | None = None, extra_head: str = "", extra_body: str = "",
         partial: bool = False, noindex: bool = False, app: bool = True, keys: tuple | None = None, auto: bool = False) -> str:
    """One page of the site: the head, the top bar, the page bar, this page's view, the footer. ``keys``: the title's
    and description's messages (see _head). ``auto``: a page with one address, translated in the browser to the
    visitor's chosen language."""
    params = params or {}
    section = (f'<section class="route" id="route-{route}" data-route="{route}" aria-labelledby="h-{route}"'
               f'{" data-partial" if partial else ""}>\n{body}\n</section>')
    boot = f' data-data="{assets["data"]}" data-routes="{assets["routes"]}" data-app="{assets["app"]}"' if app else ""
    out = f"""{_head(title, description, path, assets, extra=extra_head, noindex=noindex, keys=keys)}
<body class="page-{route}" data-page="{route}" data-route="{route}"{boot}{" data-i18n-auto" if auto or path not in MAIN_PATHS else ""}>
{starfield_html(assets['starfield'])}
{_topbar(lead, path)}
{_pagebar(route, name, params, lead)}
<main id="main">
 <div id="content" tabindex="-1">
{section}
 </div>
 <p class="note" id="bootnote"{i18n.k("shell.bootnote")} hidden>{i18n.t("shell.bootnote", "The interactive parts of this page could not load. Its text above is complete; reload to try again.")}</p>
</main>
{_footer_html(lead)}
<div id="announce" class="sr" aria-live="polite" aria-atomic="true"></div>
{SEARCH_DIALOG}
{LEARN_BAR}
{extra_body}
</body></html>
"""
    return clean_links(out, lead)


# ---------------------------------------------------------------------------------------------------------
# Pages of their own: Docs, Page not found, the forwarding pages
# ---------------------------------------------------------------------------------------------------------

def python_floor() -> str:
    """The oldest Python SetuHQ supports, as pyproject.toml's requires-python states it (e.g. "3.11")."""
    spec = ""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject.is_file():
        m = re.search(r'^requires-python\s*=\s*"([^"]*)"', pyproject.read_text(), re.M)
        spec = m.group(1) if m else ""
    if not spec:
        try:
            from importlib.metadata import metadata
            spec = metadata("setuhq").get("Requires-Python") or ""
        except Exception:  # not installed: the checkout's floor below
            spec = ""
    m = re.search(r">=\s*(\d+\.\d+)", spec)
    return m.group(1) if m else "3.11"


def docs_section(data: dict) -> str:
    """The Docs page: get started, contribute, connect an assistant, the data, and the technical details."""
    e = html.escape
    run = data["run"]
    note = data.get("code_note")
    prov = (f"<p>The candidate pages show figures from the stored run <code>{e(run['name'])}</code>, made with an earlier "
            f"version of the pipeline. Later fixes change default results, and this run has not been re-run on the "
            f"current code. The run's own record says:</p>{technical_note_html(note)}") if note else (
            f"<p>The candidate pages show figures from the stored runs ({', '.join('<code>' + e(c['run']) + '</code>' for c in data.get('showcase') or []) or '<code>' + e(run['name']) + '</code>'}), made with the current code.</p>")
    T = i18n.t
    cards = [("start", T("docs.start", "Get started"), T("docs.start.p", "Install, then search any TESS star's light curve, as each of this site's example runs did."), "#start", T("docs.start.a", "Install and first run ›")),
             ("contribute", T("docs.contribute", "Contribute a sweep"), T("docs.contribute.p", "Search a slice of a TESS sector on your own machine and send the result, with credit."), "#contribute", T("docs.contribute.a", "How to contribute ›")),
             ("mcp", T("docs.mcp", "Use it from an assistant"), T("docs.mcp.p", "The MCP server lets an assistant run SetuHQ's own code and read its results."), "#mcp", T("docs.mcp.a", "Connect over MCP ›")),
             ("data", T("docs.data", "Data and files"), T("docs.data.p", "Every catalogue on this site as a download, and the reports behind the evidence."), "#data", T("docs.data.a", "Downloads ›")),
             ("pictures", T("docs.pictures", "How the pictures are drawn"), T("docs.pictures.p", "Stars in their blackbody colour; planets as artist's impressions chosen from measured radius and irradiation. Every rule and source."), "/docs/pictures/", T("docs.pictures.a", "The pictures ›")),
             ("editions", T("docs.editions", "Editions"), T("docs.editions.p", "The open core is free. SetuHQ Pro (in development) and custom studies are under contract, with no prices: each starts with a message."), "/editions/", T("docs.editions.a", "Compare the editions ›"))]
    grid = "\n".join(f'        <section class="card"><h2{i18n.k("docs." + c)}>{h}</h2><p{i18n.k("docs." + c + ".p")}>{p}</p><a href="{u}"{i18n.k("docs." + c + ".a")}>{a}</a></section>' for c, h, p, u, a in cards)
    return f"""<header><h1 class="lead-h" id="h-docs" tabindex="-1"{i18n.k("docs.h1")}>{T("docs.h1", "Run it yourself.")}</h1>
        <p{i18n.k("docs.intro")}>{T("docs.intro", "SetuHQ is open source. Install it, search a star's light curve with the same panel this site shows, contribute a sweep of the sky, or let your AI assistant use it.")}</p></header>
      <div class="docgrid">
{grid}
      </div>
      <div class="prose">
        <h2 id="start"{i18n.k("docs.install")}>{T("docs.install", "Install and first run")}</h2>
        <p{i18n.k("docs.python", v=python_floor())}>{T("docs.python", "SetuHQ needs Python {v} or newer.", v=python_floor())}</p>
        <pre tabindex="0"><code>pip install "setuhq[tess] @ git+{REPO_URL}"
setuhq run configs/showcase/tess-wasp-126-s1.toml --out runs/tess-wasp-126-s1   # or any star: copy a config, change its TIC and sectors
setuhq crossmatch runs/tess-wasp-126-s1          # the NASA Exoplanet Archive's planets for the star
setuhq site runs/tess-wasp-126-s1 --out site     # a website from your run (several runs: list them all)</code></pre>
        <p>Every example on this site has its configuration in <code>configs/</code> and its one-line command in <a rel="noopener" href="{REPO_URL}/blob/main/docs/SHOWCASE.md">docs/SHOWCASE.md</a>. The run downloads the light curve from MAST, cleans it, lets the panel mark dips, vets each signal and writes every result with its provenance. The Probes run with no account; the Sentinels need an API key for their provider. {e(ATTRIBUTION)}</p>
        <h2 id="contribute"{i18n.k("docs.contribute")}>{T("docs.contribute", "Contribute a sweep")}</h2>
        <p>A sweep searches every 2-minute target of a TESS sector and keeps every dip it finds, classified, with nothing thrown away. You can run a slice and send it in:</p>
        <pre tabindex="0"><code>setuhq sweep configs/sweep.toml --sector 5 --limit 200 --workers 3
setuhq bundle my-sweep/sector_0005.json.gz --contributor "Your Name" --out bundle/</code></pre>
        <p>Open a pull request with the bundle. A maintainer checks it and merges it into <a href="/catalogue/everything-that-dims/">Everything that dims</a>, with your name on every entry it brings. See <a rel="noopener" href="{REPO_URL}/blob/main/CONTRIBUTING.md">CONTRIBUTING.md</a>.</p>
        <h2 id="mcp"{i18n.k("docs.mcp.h")}>{T("docs.mcp.h", "Use it from an AI assistant (MCP)")}</h2>
        <pre tabindex="0"><code>pip install "setuhq[tess,mcp] @ git+{REPO_URL}"
setuhq-mcp --list-tools</code></pre>
        <p>Set-up for each assistant is in <a rel="noopener" href="{REPO_URL}/blob/main/docs/MCP-INSTALL.md">docs/MCP-INSTALL.md</a>.</p>
        <h2 id="data"{i18n.k("docs.data")}>{T("docs.data", "Data and files")}</h2>
        <ul>
          <li><a href="/{CATALOGUE_JSON}">The catalogue of known planets (JSON)</a> and <a href="/assets/data/{CSV_NAME}">every planet on the Galaxy map (CSV)</a>, from exoplanet.eu.</li>
          <li><a href="/{VARIABLES_JSON}">Everything that dims (JSON)</a>: every entry of SetuHQ's sweep, with its credit.</li>
          {"".join(f'<li>{e(c["star"])} ({e(c["kind"] or c["run"])}): ' + i18n.span("docs.runfiles", '<a href="{report}">the run report</a>, <a href="{plates}">the plates</a> and <a href="{cf}">the case file</a> of run {run}.', report=c["report"], plates=c["plates"], cf=c["case_file"], run=c["run"]) + '</li>' for c in data.get("showcase") or [])}
          <li>The benchmark, the leaderboard and the paper: <a rel="noopener" href="{REPO_URL}/tree/main/docs">docs/ in the repository</a>.</li>
        </ul>
        <p>SetuHQ's own data, benchmark, leaderboard and paper are under CC BY 4.0; the code is under the AGPL-3.0 (a commercial licence is available). Cite it with <a rel="noopener" href="{REPO_URL}/blob/main/CITATION.cff">CITATION.cff</a>.</p>
        <h2 id="provenance"{i18n.k("docs.prov")}>{T("docs.prov", "Technical details: where the figures come from")}</h2>
        {prov}
        <p>Every number on the candidate and evidence pages is read from stored files: the run directory, the search catalogue and the calibrated reviewer weights. <a href="/evidence/runs/">Runs and configuration</a> lists the files, the configuration and its hash.</p>
      </div>"""


def pictures_section() -> str:
    """How the pictures are drawn (/docs/pictures/): the renderer's honesty page. Phase 0 writes its skeleton: what a
    picture is and is not, the look table from setuhq.looks.LOOKS with every still, and the rules with their sources.
    Every "Artist's impression" tag on the site links here."""
    from urllib.parse import quote

    e = html.escape
    cards = []
    for name, L in LOOKS.items():
        bands = ", ".join(L["bands"]) or "Solar System reference"
        cap = f"<b>{e(name)}</b>{e(L['composition'])} · {e(bands)}<br>{e(L['surface'])}"
        alt = f"Artist's impression: the {name} look, for {rule_words(name)}: {L['surface']}. A still of the look, not of a particular planet."
        ref = name.startswith("ref-")  # the Solar System's own planets: illustrations, not impressions of an exoplanet
        alt = alt.replace("Artist's impression:", "Illustration:", 1) if ref else alt
        cards.append("<li>" + renderer.figure("planet", {"look": name, "seed": 1}, alt, cap, size=160, uid=f"lk-{name}",
                                              label="Illustration" if ref else renderer.LABEL_ART) + "</li>")
    rad = "".join(f"<tr><td>{e(c)}</td><td>{'below ' + format(edge, 'g') + ' R⊕' if edge != float('inf') else '10 R⊕ or more'}</td><td>{e(why)}</td></tr>"
                  for edge, c, why in COMPOSITION_RULES["radius"])
    mass = "".join(f"<tr><td>{e(c)}</td><td>{'below ' + format(edge, 'g') + ' M⊕' if edge != float('inf') else '50 M⊕ or more'}</td><td>{e(why)}</td></tr>"
                   for edge, c, why in COMPOSITION_RULES["mass"])
    bands = "".join(f"<tr><td>{e(b)}</td><td>{'below ' + format(edge, ',.0f') + ' K' if edge != float('inf') else '2,000 K or more'}</td><td>{e(why)}</td></tr>"
                    for edge, b, why in BANDS)
    sun = renderer.star_svg(5772, 60, uid="pic-sun")
    sun_src = "data:image/svg+xml," + quote(sun.replace('class="stardisc" ', 'xmlns="http://www.w3.org/2000/svg" '))
    star = renderer.figure("star", {"teff": 5772, "seed": 1}, "The Sun's disc, 5,772 K, in its blackbody colour with limb darkening.",
                           "The Sun, 5,772 K (IAU 2015 nominal), in its blackbody colour; limb darkening from Claret (2017), TESS band. The surface texture is decorative.",
                           label="Illustration", uid="pic-star", still=sun_src)
    tr = renderer.figure("transit", {"teff": 5772, "k": 0.1, "b": 0.3, "look": "giant-hot", "seed": 1, "layout": "theatre"},
                         "An illustration of a transit: a planet with Rp/R★ = 0.1 crossing a Sun-like star at b = 0.3, and the limb-darkened model light curve it causes.",
                         "Illustration: Rp/R★ = 0.1, b = 0.3, a 5,772 K star; the curve is the small-planet Mandel & Agol (2002) model with quadratic limb darkening.",
                         label="Illustration", uid="pic-transit", still=sun_src)
    from setuhq.looks import teff_rgb
    from setuhq.methods import LABELS

    looktable = "".join(f'<tr data-look="{e(r["look"])}"><th scope="row"><code>{e(r["look"])}</code></th><td>{e(r["composition"])}</td>'
                        f'<td>{e(", ".join(r["bands"]) or "Solar System reference")}</td><td>{e(rule_words(r["look"]))}</td><td>{e(r["surface"])}</td></tr>'
                        for r in renderer.look_table_rows())
    swatches = "".join(f'<tr><th scope="row">{t:,} K</th><td><span class="swatch" style="background:rgb{teff_rgb(t)}"></span>'
                       f'<code>rgb({", ".join(map(str, teff_rgb(t)))})</code></td><td>{e(w)}</td></tr>'
                       for t, w in ((3532, "a cool M dwarf"), (5175, "a K dwarf"), (5772, "the Sun (IAU 2015 nominal)"), (6421, "TOI-236, an F star (TIC v8.2)"), (10000, "an A star")))
    label_what = {"Artist's impression": "Planet art: a look chosen from the measured radius (or mass) and irradiation. The tag links here.",
                  "Model from stored values": "A drawing computed from stored numbers (catalogue values, a fit): a model light curve, an orbit, a star disc at its Teff.",
                  "Real data, cited": "Measured data plotted as stored, with its source printed under it: SetuHQ's light curves, the catalogue's counts.",
                  "Illustration": "A schematic to explain an idea; its scales are chosen to show it, and say so.",
                  "Speculative model": "A framework with unknown terms (the Drake equation): not a prediction."}
    labels = "".join(f'<tr><th scope="row">{e(lab)}</th><td>{e(label_what[lab])}</td></tr>' for lab in LABELS)
    surfaces = "".join(f'<tr><th scope="row">{e(a)}</th><td>{e(b)}</td><td>{e(c)}</td></tr>' for a, b, c in (
        ("Planet pictures (planet pages, the gallery, the line-up)", "an artist's impression from the look table; size to scale only when a radius is stored", "radius, mass, a, R★, Teff, Teq from exoplanet.eu"),
        ("Star discs (everywhere)", "the star's blackbody colour and limb darkening; granulation is texture", "Teff (TIC v8.2 for the example runs, exoplanet.eu otherwise)"),
        ("A dip's silhouette (candidates, radius ratios)", "a black disc at Rp/R★ = √depth, if it were a planet: never planet art", "the stored depth"),
        ("Light curves, folds and dip strips", "plotted as stored; nothing smoothed except stated bins", "the runs' stored subjects and fits"),
        ("Methods drawings", "illustrations or models, each labelled, with its exaggeration stated", "the catalogue and cited papers, numbers in each chapter's table"),
        ("The background starfield", "decorative, seeded so every visitor sees the same field; hidden from screen readers", "none")))
    stills = "".join(f'<tr><th scope="row">{e(a)}</th><td>{e(b)}</td></tr>' for a, b in (
        ("The home page's transit", "the planet at mid-transit, the light curve drawn to the end of egress, the depth labelled"),
        ("A planet portrait", "the planet turned 0.6 radians, lit from the upper left"),
        ("The sky by year", "the final year, every host, with a Play button"),
        ("The fold", "two panels side by side: the light curve in time order and folded on the period"),
        ("The panel ring", "the marks, weights and score at their stored values, the verdict word shown"),
        ("Orbits", "the planets at their phases for t = 0, one at conjunction with its dip marked"),
        ("Counters and timelines", "the final numbers and the full bars"),
        ("The starfield", "its static image")))
    T = i18n.t
    return f"""<header><h1 class="lead-h" id="h-pictures" tabindex="-1"{i18n.k("pic.h1")}>{T("pic.h1", "How the pictures are drawn.")}</h1>
        <p{i18n.k("pic.intro")}>{T("pic.intro", "Every star on SetuHQ is drawn in its blackbody colour from its stored temperature. Every planet is an artist's impression: its look is chosen from two measured things, its radius (or, without one, its mass) and the light it gets from its star. Nothing in a picture is measured beyond those numbers, and composition never is.")}</p></header>
      <section class="prose" aria-labelledby="h-pic-rules"><h2 id="h-pic-rules"{i18n.k("pic.rules")}>{T("pic.rules", "The rules")}</h2>
        <p>Composition, from the radius in Earth radii (1 RJ = 11.209 R⊕):</p>
        <div class="tablewrap"><table><thead><tr><th scope="col">Drawn as</th><th scope="col">Radius</th><th scope="col">Why</th></tr></thead><tbody>{rad}</tbody></table></div>
        <p>Without a radius, from the mass (or m sin i, a minimum mass) in Earth masses; such a planet is drawn at a fixed size, marked not to scale. With neither, no planet is drawn.</p>
        <div class="tablewrap"><table><thead><tr><th scope="col">Drawn as</th><th scope="col">Mass</th><th scope="col">Why</th></tr></thead><tbody>{mass}</tbody></table></div>
        <p>Temperature band, from the equilibrium temperature Teq = 278.3 K × S<sup>1/4</sup>, where S = R★² (Teff / 5,772 K)⁴ / a² is the light the planet gets relative to Earth (zero albedo, full redistribution). Without a, a comes from Kepler's third law; without R★ or Teff, the catalogue's stored Teq is used; without that, the colours are neutral.</p>
        <div class="tablewrap"><table><thead><tr><th scope="col">Band</th><th scope="col">Teq</th><th scope="col">Why</th></tr></thead><tbody>{bands}</tbody></table></div>
        <p>A star's colour: a Planck spectrum from 380 to 780 nm, through the CIE 1931 colour-matching functions (the multi-lobe fit of Wyman, Sloan and Shirley 2013), to sRGB, normalised so the colour is a hue, not a brightness. Limb darkening is the quadratic law with Claret's (2017) TESS-band coefficients, applied to a visible disc. Granulation and planet surfaces are texture only: decorative, never data.</p>
      </section>
      <section class="prose" aria-labelledby="h-pic-table"><h2 id="h-pic-table"{i18n.k("pic.table")}>{T("pic.table", "The look table")}</h2>
        <p>One row per look: what it is drawn for, by the rules above, and what its surface shows. The same table (setuhq.looks.LOOKS) drives the pictures, so a picture can only be one of these.</p>
        <div class="tablewrap" tabindex="0" role="region" aria-labelledby="h-pic-table"><table class="looktable"><thead><tr><th scope="col">Look</th><th scope="col">Composition</th><th scope="col">Bands</th><th scope="col">Drawn for</th><th scope="col">Surface</th></tr></thead><tbody>{looktable}</tbody></table></div>
      </section>
      <section aria-labelledby="h-pic-looks"><h2 id="h-pic-looks">The {len(LOOKS)} looks</h2>
        <p class="lookintro">Each look as its still (seed 1). Oceans and continents are drawn only for Earth itself, the Solar System reference; no exoplanet is given water.</p>
        <ul class="lookgrid">{"".join(cards)}</ul>
      </section>
      <section class="prose" aria-labelledby="h-pic-labels"><h2 id="h-pic-labels"{i18n.k("pic.labels")}>{T("pic.labels", "The five labels")}</h2>
        <p{i18n.k("pic.labels.p")}>{T("pic.labels.p", "Every picture on the site carries one of these, on the picture itself.")}</p>
        <div class="tablewrap" tabindex="0" role="region" aria-labelledby="h-pic-labels"><table><tbody>{labels}</tbody></table></div>
        <h2 id="h-pic-real"{i18n.k("pic.real")}>{T("pic.real", "What is real and what is drawn")}</h2>
        <div class="tablewrap" tabindex="0" role="region" aria-labelledby="h-pic-real"><table><thead><tr><th scope="col">Where</th><th scope="col">What is drawn</th><th scope="col">What is measured in it</th></tr></thead><tbody>{surfaces}</tbody></table></div>
        <h2 id="h-pic-colour"{i18n.k("pic.colour")}>{T("pic.colour", "Star colour")}</h2>
        <p>The colour is computed, not picked: Planck's law at the star's Teff, sampled from 380 to 780 nm in 5 nm steps, weighted by the CIE 1931 colour-matching functions (the multi-lobe fit of Wyman, Sloan and Shirley 2013), converted from XYZ to linear sRGB, normalised to the brightest channel and gamma-encoded. Teff is clamped to 1,000–40,000 K. Because of the normalisation every star is equally bright on screen: the colour is a hue, not a luminosity. The limb darkening is the quadratic law with Claret's (2017) coefficients for the TESS band, a red-optical law applied to a visible disc.</p>
        <div class="tablewrap" tabindex="0" role="region" aria-labelledby="h-pic-colour"><table><thead><tr><th scope="col">Teff</th><th scope="col">Colour</th><th scope="col">For example</th></tr></thead><tbody>{swatches}</tbody></table></div>
      </section>
      <section aria-labelledby="h-pic-draw"><h2 id="h-pic-draw"{i18n.k("pic.draw")}>{T("pic.draw", "The star and the transit")}</h2>
        <div class="rendrow">{star}{tr}</div>
      </section>
      <section class="prose" aria-labelledby="h-pic-still"><h2 id="h-pic-still"{i18n.k("pic.still")}>{T("pic.still", "With reduced motion")}</h2>
        <p{i18n.k("pic.still.p")}>{T("pic.still.p", "When your device asks for reduced motion, nothing loops: each drawing shows one designed frame, and anything that plays waits for its button.")}</p>
        <div class="tablewrap" tabindex="0" role="region" aria-labelledby="h-pic-still"><table><thead><tr><th scope="col">Drawing</th><th scope="col">Its still</th></tr></thead><tbody>{stills}</tbody></table></div>
      </section>"""


NOTFOUND_LINES = {"explore": N_("nf.explore", "The sky, the Galaxy and every catalogued planet."), "candidates": N_("nf.candidates", "Every dip the example runs found, with its checks."),
                  "how": N_("nf.how", "Fifteen chapters on how planets are found."), "evidence": N_("nf.evidence", "The reviewers, the benchmark and the runs."),
                  "docs": N_("nf.docs", "Install SetuHQ and run it yourself.")}


def notfound_section() -> str:
    cards = "".join(f'<li><a class="docard" href="{from_hash(h)}"><b{i18n.k("nav." + k)}>{html.escape(label)}</b>'
                    + (f'<span{i18n.k("nf." + k)}>{html.escape(NOTFOUND_LINES[k])}</span>' if k in NOTFOUND_LINES else "")
                    + '<i aria-hidden="true">›</i></a></li>' for k, label, h in NAV)
    T = i18n.t
    return f"""<header><h1 class="lead-h" id="h-notfound" tabindex="-1"{i18n.k("nf.h1")}>{T("nf.h1", "This page is not here.")}</h1>
        <p{i18n.k("nf.intro")}>{T("nf.intro", "The address may be mistyped, or the page may have moved when the site was reorganised. Old addresses forward on their own; this one has no new home.")}</p></header>
      <div class="nfsearch"><a class="btn primary" href="/"{i18n.k("nf.home")}>{T("nf.home", "Go to the home page")}</a><button class="btn" type="button" data-open-search{i18n.k("nf.search")}>{T("nf.search", "Search planets, stars and pages")}</button></div>
      <ul class="docards nfcards">{cards}</ul>"""


def forward_css() -> str:
    """The forwarding page's inline style, from the design tokens' dark values (no external file)."""
    from setuhq.design import TOKENS

    t = {k: v[0] for k, v in TOKENS.items()}
    return (f"html{{background:{t['bg']};color:{t['ink']};font:16px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}}"
            f"body{{margin:0 auto;padding:48px max(16px,env(safe-area-inset-left,0px));max-width:640px}}"
            f"main{{border:1px solid {t['line']};border-radius:20px;background:{t['panel']};padding:24px}}"
            f"h1{{font-size:24px;letter-spacing:-.02em;margin:0 0 8px}}p{{margin:0;color:{t['ink-2']}}}a{{color:{t['sen']}}}")


def forward_page(target: str, title: str, lead: str | None = None) -> str:
    """A page at an old address: it forwards (keeping a dip named in the hash) and says where to."""
    e = html.escape
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} has moved · SetuHQ</title><meta name="robots" content="noindex">
<link rel="canonical" href="{brand.SITE_URL}{e(target)}">
<script>{legacy_js(lead)}</script>
<noscript><meta http-equiv="refresh" content="0; url={e(target)}"></noscript>
<style>{forward_css()}</style>
</head><body><main><h1>This page has moved.</h1><p>{e(title)} is now at <a href="{e(target)}">{e(brand.SITE_URL + target)}</a>.</p></main></body></html>
"""


# ---------------------------------------------------------------------------------------------------------
# Server-rendered views that the app also draws: a dip, a planet, a star, a chapter
# ---------------------------------------------------------------------------------------------------------

def _dip_header(section: str, d: dict, label: str, caveat: str = "", panel: dict | None = None) -> tuple[str, str]:
    """The Transit view with its header filled in for one dip, as the app draws it (the app redraws it, with the
    playback). ``panel`` is the dip's panel ring data (setuhq.viz.panelring.for_dip): the reviewers converging on
    its stored score, readable without JavaScript. Returns the section and the heading's text: the dip's plain name,
    "pi Men, dip 2 (6.27 d)"."""
    e = html.escape
    out = section.replace('<p class="eyebrow" id="txkicker"></p>', f'<p class="eyebrow" id="txkicker">{e(d["status_label"])}</p>', 1)
    out = out.replace('<h1 class="lead-h" id="h-transit" tabindex="-1"></h1>', f'<h1 class="lead-h" id="h-transit" tabindex="-1">{e(label)}</h1>', 1)
    out = out.replace('<p id="txsub"></p>', f'<p id="txsub">{e(d["time_unit"])} {d["t"]:.2f} · {d["depth_ppm"]:,.0f} ppm · {d["duration_hours"]:.2f} hours · SNR {d["snr"]:.1f} · {e(dip_state(d.get("outcome"))[2])}</p>', 1)
    if caveat:  # what the dip's run did not recover, stated on each of its dips' pages
        out = out.replace('<p class="note" id="txcaveat" hidden></p>', f'<p class="note" id="txcaveat">What this run did not recover: {e(caveat)}</p>', 1)
    if d.get("outcome") == "rejected":  # a rejected dip is not called a transit
        out = out.replace('<span id="txcapword">The transit, played back</span>', '<span id="txcapword">The dip, played back</span>', 1)
    out = out.replace('<div id="txjourney"></div>', f'<div id="txjourney">{d.get("journey") or ""}</div>', 1)
    out = out.replace('<p class="small" id="txlight"></p>', f'<p class="small" id="txlight">{e(d.get("light") or "")}</p>', 1)
    out = out.replace('<p class="casefile" id="txcase"></p>', f'<p class="casefile" id="txcase"><a class="btn primary" href="{e(url_for("candidates", {"dip": d["id"]}))}">Open the full case file ›</a></p>', 1)
    ring = viz.panelring.html(panel) if panel else ""
    verdict = f'<p class="txverdict">{e(d["verdict"])}</p>' if d.get("verdict") else ""
    if ring or verdict:
        out = out.replace('<section class="glass scorecard" id="txscore" aria-label="Panel score and verdict"></section>',
                          f'<section class="glass scorecard" id="txscore" aria-label="Panel score and verdict">{ring}{verdict}</section>', 1)
    run = d.get("run") or ""
    if run:  # a multi-planet example's dips show its orbits inset (V08); the others' stay hidden
        out = out.replace(f'<div class="txinset" data-run="{e(run)}" hidden>', f'<div class="txinset" data-run="{e(run)}">', 1)
    return out, label


def _title(route: str, name: str | None = None) -> str:
    """A page's title, by the same rule the app uses when it changes view (ROUTE_META)."""
    m = ROUTE_META[route]
    tpl = m.get("title_tpl") or m.get("title") or f"{m['label']} · SetuHQ"
    return tpl.replace("{name}", name or m["label"])


def _planet_section(section: str, cat: dict, i: int) -> tuple[str, str, str]:
    """A pre-rendered planet page: its heading, facts and stored values, its portrait beside its star and its place in
    the line-up (setuhq.catalogue.planet_extras); the app adds the rest."""
    from setuhq.catalogue import planet_extras

    e = html.escape
    P = cat["planets"]
    name, star = P["name"][i], P["star"][i]
    method = (P.get("method_raw") or P["method"])[i] or "not stored"
    year = P["year"][i]
    host = f'<a href="/stars/{slugify(star)}/">{e(star)}</a>' if star else "host not stored"
    sub = f'{host} · {e(str(method))} · discovered {year if year else "year not stored"}'
    rows = [("Orbital period", stored(P, "period", i, 4, "days")), ("Radius", stored(P, "radius", i, 3, "Jupiter radii")),
            ("Mass", stored(P, "mass", i, 4, "Jupiter masses")), ("Semi-major axis", stored(P, "a", i, 4, "AU")),
            ("Distance", stored(P, "dist", i, 2, "pc")), ("Star temperature", stored(P, "steff", i, 0, "K"))]
    table = "".join(f'<tr><th scope="row">{e(k)}</th><td>{e(v)}</td></tr>' for k, v in rows if v)
    table = (f'<table class="pltable"><tbody>{table}</tbody></table><p class="small">Stored values from {e(cat["source_short"])}, '
             f'fetched {e(cat["fetched_at"][:10])}. SetuHQ did not discover this planet.</p>')
    out = section.replace('<h1 class="lead-h" id="h-planet" tabindex="-1">Planet</h1><p id="plsub"></p>',
                          f'<h1 class="lead-h" id="h-planet" tabindex="-1">{e(name)}</h1><p id="plsub">{sub}</p>', 1)
    out = out.replace('<div id="plparams"></div>', f'<div id="plparams">{table}</div>', 1)
    out = out.replace('<div class="plextra" id="plextra"></div>', f'<div class="plextra" id="plextra">{planet_extras(cat, i)}</div>', 1)
    desc = (f"{name}: a planet found by {method}{f' in {year}' if year else ''}"
            f"{f', orbiting {star}' if star else ''}. Its stored parameters from {cat['source_short']}, drawn to scale.")
    return out, name, desc


def _star_section(section: str, cat: dict, name: str, idx: list[int]) -> tuple[str, str]:
    """A pre-rendered star page: the star in its blackbody colour, the orbits of its planets (two or more with a period)
    and its planets with their pictures (setuhq.catalogue.star_extras, still_list)."""
    from setuhq.catalogue import star_extras, still_list

    e = html.escape
    P = cat["planets"]
    out = section.replace('<h1 class="lead-h" id="h-star" tabindex="-1">Star</h1><p id="stsub"></p>',
                          f'<h1 class="lead-h" id="h-star" tabindex="-1">{e(name)}</h1><p id="stsub">{len(idx)} known planet{"s" if len(idx) != 1 else ""} in {e(cat["source_short"])}</p>', 1)
    first = sorted(idx, key=lambda j: P["period"][j] if P["period"][j] is not None else 1e99)[0]  # the page's script reads the innermost
    light = journey.light_line(P["dist"][first], f"{cat['source_short']}, fetched {str(cat['fetched_at'])[:10]}", what="this star")
    out = out.replace('<p class="small" id="stlight"></p>', f'<p class="small" id="stlight">{e(light)}</p>', 1)
    out = out.replace('<div id="stplanets"></div>', f'<div id="stplanets">{still_list(cat, idx)}</div>', 1)
    out = out.replace('<div class="plextra" id="stextra"></div>', f'<div class="plextra" id="stextra">{star_extras(cat, name, idx)}</div>', 1)
    return out, f"{name}: a star with {len(idx)} known planet{'s' if len(idx) != 1 else ''}, from {cat['source_short']}."


def _chapter_section(section: str, cid: str) -> str:
    """The Methods view with only one chapter, shown (the page marks itself partial; the app adds the others)."""
    marker = '<article class="mxch" id="mx-'
    head, *chapters = section.split(marker)
    keep = next(c for c in chapters if c.startswith(cid + '"')).replace(" hidden>", ">", 1)
    head = head.replace(f'data-ch="{cid}">', f'data-ch="{cid}" aria-current="step">', 1)
    if cid != CHAPTERS[0][0]:  # a chapter's page opens with its own title, not the section's introduction
        title = dict(CHAPTERS)[cid]
        head = head.replace('<header class="headrow">', '<header class="headrow deep">', 1)
        head = re.sub(r'(<h1 class="lead-h" id="h-methods" tabindex="-1">).*?(</h1>)', lambda m: m.group(1) + html.escape(title) + m.group(2), head, count=1, flags=re.S)
    return head + marker + keep


def _named_objects(data: dict) -> list[str]:
    """Every planet the site names: the Methods chapters, the Galaxy tour and notables, the catalogue's mentions, the run's planet."""
    names = [n for ns in CHAPTER_PLANETS.values() for n in ns]
    names += [x["name"] for x in (data.get("galaxy") or {}).get("notable", [])]
    names += list(((data.get("catalogue_meta") or {}).get("mentions") or {}).keys())
    names += [ctx["planet"] for ctx in (data.get("run_ctx") or {}).values() if ctx.get("planet")]
    if data["story"].get("planet"):
        names.append(data["story"]["planet"])
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


# ---------------------------------------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------------------------------------

STARFIELD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 1100" preserveAspectRatio="xMidYMid slice">'
             '<style>@keyframes t{{0%,100%{{opacity:.25}}50%{{opacity:.75}}}}.a{{animation:t 6s cubic-bezier(.2,.7,.2,1) infinite}}.b{{animation:t 9s cubic-bezier(.2,.7,.2,1) infinite 2s}}'
             '@media (prefers-reduced-motion: reduce){{.a,.b{{animation:none}}}}</style>'
             '<path class="a" d="{dust}" stroke="#FFFFFF" stroke-width="1" stroke-linecap="round" opacity=".5"/>'
             '<path class="b" d="{bright}" stroke="#E8EEFF" stroke-width="1.8" stroke-linecap="round"/></svg>')
STARFIELD_CSS = renderer.RENDER_CSS  # the starfield's rules live with the renderer (V11)


# The language picker, the suggestion and the machine-translation note; and type for Japanese and Chinese, which the
# self-hosted Latin fonts do not cover: the visitor's own system fonts, in each language's order (nothing is fetched).
I18N_CSS = """
.langpick{position:relative;flex:none}
.langpick>summary{list-style:none;width:auto;min-width:44px;padding:0 8px;gap:4px;font:500 11.5px var(--mono);letter-spacing:.04em}
.langpick>summary::-webkit-details-marker{display:none}
.langpick>summary svg{width:18px;height:18px}
.langmenu{position:absolute;right:0;top:calc(100% + 8px);z-index:60;width:min(320px,calc(100vw - 32px));padding:10px;border-radius:18px;border:1px solid var(--line-2);background:var(--bg-2);box-shadow:0 24px 40px -24px rgba(0,0,0,.6)}
.langmenu ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:2px}
.langmenu a{display:flex;align-items:center;min-height:44px;padding:0 10px;border-radius:10px;color:var(--ink-2);text-decoration:none;font-size:14px}
.langmenu a:hover{background:var(--panel-2);color:var(--ink)}
.langmenu a[aria-current]{background:var(--seg-bg);color:var(--seg-ink)}
.langnote{margin:8px 6px 4px;font-size:12px;line-height:1.45;color:var(--ink-3)}
.langnote a,.mtnote a{color:var(--ink-2)}
.langhint{position:relative;z-index:45;display:flex;align-items:center;justify-content:center;gap:12px;padding:6px max(16px,env(safe-area-inset-right,0px)) 6px max(16px,env(safe-area-inset-left,0px));background:var(--bg-2);border-bottom:1px solid var(--line)}
.langhint p{margin:0;font-size:14px;color:var(--ink-2)}
.langhint .btn{min-height:44px;min-width:44px;padding:0}
.sitefoot .mtnote{color:var(--ink-2)}
:root:lang(ja){--sans:"Geist","Geist Fallback","Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic UI","Yu Gothic",Meiryo,"Noto Sans CJK JP","Noto Sans JP","IPAexGothic","IPAGothic",system-ui,sans-serif}
:root:lang(zh-Hans){--sans:"Geist","Geist Fallback","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC","Noto Sans SC","Source Han Sans SC",system-ui,sans-serif}
:lang(ja) *,:lang(zh-Hans) *{letter-spacing:0!important;word-break:normal;line-break:strict;overflow-wrap:anywhere}
:lang(ja) h1,:lang(ja) h2,:lang(zh-Hans) h1,:lang(zh-Hans) h2{line-height:1.25}
/* Headings break between phrases (the catalogues mark them with <wbr>), never inside a word; a phrase too wide for its line still wraps. */
:lang(ja) :is(h1,h2,h3,h4,.lead-h),:lang(zh-Hans) :is(h1,h2,h3,h4,.lead-h){word-break:keep-all;overflow-wrap:anywhere}
@media (max-width:420px){.langpick>summary .langcode{display:none}}
"""
# Messages the shell's script declares (the suggestion bar, the theme and menu buttons).
N_("i18n.suggest.label", "Language")
N_("i18n.suggest.text", "This page is also in English.", note="Said in the language it offers: 'This page is also in German.' in German.")
N_("i18n.suggest.go", "Read it in English", note="In the language it offers.")
N_("i18n.suggest.dismiss", "Dismiss")


def write_i18n_assets(out: Path) -> dict[str, str]:
    """Each language's catalogue for the browser (assets/i18n/<lang>-<hash>.json); returns their addresses."""
    d = out / "assets" / "i18n"
    d.mkdir(parents=True, exist_ok=True)
    urls = {}
    for lang in i18n.TRANSLATIONS:
        text = json.dumps(i18n.client_catalogue(lang), ensure_ascii=False, separators=(",", ":"))
        name = f"{lang}-{_sha(text)}.json"
        (d / name).write_text(text, encoding="utf-8")
        urls[lang] = f"/assets/i18n/{name}"
    return urls


def i18n_auto_script(out: Path) -> str:
    """The script that puts the page text the scripts draw in the reader's language (assets/i18n-auto-*.js); its address."""
    text = strip_js(i18n.AUTO_JS)
    rel = f"assets/i18n-auto-{_sha(text)}.js"
    (out / rel).write_text(text)
    return "/" + rel


def i18n_script(cat_urls: dict[str, str], auto: str = "") -> str:
    """The languages' script (i18n-*.js, before the shell's on every page): its configuration (the languages, the
    catalogues' addresses and the pages that have an address in every language), then setuhq.i18n.SHELL_JS."""
    conf = {"locales": list(i18n.LOCALES), "cat": cat_urls, "main": list(MAIN_PATHS), "auto": auto}
    return "const I18N_CONF = " + json.dumps(conf, separators=(",", ":")) + ";\n" + i18n.SHELL_JS


def localize_page(src: str, lang: str, path: str) -> str:
    """The English page at ``path`` as its /<lang>/ twin: every keyed element in ``lang``, links to pages that have
    an address in every language kept in it, its own canonical address, the picker, and the machine-translation
    note shown."""
    new = lang_path(path, lang)

    def link(h: str) -> str:
        if not h.startswith("/") or h.startswith("//"):
            return h
        base = re.split(r"(?=[?#])", h, maxsplit=1)
        return lang_path(base[0], lang) + (h[len(base[0]):]) if base[0] in MAIN_PATHS else h

    out = i18n.localize_html(src, lang, link=link)
    out = i18n_auto.localize(out, lang, i18n.messages(lang), link=link)  # the page's prose, by its text
    out = out.replace('<html lang="en"', f'<html lang="{lang}"', 1)
    url, nurl = html.escape(brand.SITE_URL + path), html.escape(brand.SITE_URL + new)
    out = out.replace(f'<link rel="canonical" href="{url}">', f'<link rel="canonical" href="{nurl}">', 1)
    out = out.replace(f'<meta property="og:url" content="{url}">', f'<meta property="og:url" content="{nurl}"><meta property="og:locale" content="{i18n.OG_LOCALE[lang]}">', 1)
    out = re.sub(r'<details class="langpick">.*?</details>', lambda m: langpick(path, lang), out, count=1, flags=re.S)
    return out.replace('<p class="mtnote" data-i18n="i18n.mtnote" hidden>', '<p class="mtnote" data-i18n="i18n.mtnote">', 1)


def write_lang_pages(out: Path, main_pages: dict[str, str]) -> list[str]:
    """Every page that has an address in every language, written under /<lang>/; returns their addresses."""
    done = []
    for lang in i18n.TRANSLATIONS:
        for path, text in sorted(main_pages.items()):
            new = lang_path(path, lang)
            d = out / new.strip("/")
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(localize_page(text, lang, path))
            done.append(new)
    return done


def _clear(out: Path) -> None:
    """Empty the output folder, keeping CNAME (the custom domain) and .nojekyll."""
    if not out.exists():
        return
    for p in out.iterdir():
        if p.name in ("CNAME", ".nojekyll"):
            continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()


def build_site(*args, **kwargs) -> Path:
    """Write the whole site (see _build_site). The site's own pages are written in English and in every language
    of setuhq.i18n, whatever language the command itself speaks."""
    with i18n.use(i18n.SOURCE):
        return _build_site(*args, **kwargs)


def _build_site(run_dir: str | Path, out_dir: str | Path, *, title: str = "SetuHQ", catalog_path: str | Path | None = None,
               weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None, require_crossmatch: bool = False,
               sweep_path: str | Path | None = DEFAULT_SWEEP, validation_md: str | Path | None = None,
               benchmark_md: str | Path | None = None, extras: bool = True, extra_runs: list | tuple = (),
               showcase_path: str | Path | None = DEFAULT_SHOWCASE) -> Path:
    """Write the whole site into ``out_dir``; returns the home page's path. ``extras`` also builds the run report,
    the plates and the stand-alone case file (the tests leave them out when they only need the app).

    ``run_dir`` is the lead run; ``extra_runs`` are the other stored example runs, each with its dips' pages, its
    case file at /candidates/<star>/case-file/, its plates at /evidence/plates/<star>/ and its report at
    /evidence/report/<star>/."""
    out = Path(out_dir)
    data = app_data(run_dir, title=title, catalog_path=catalog_path, weights_path=weights_path, star=star,
                    require_crossmatch=require_crossmatch, sweep_path=sweep_path, extra_runs=extra_runs,
                    showcase_path=showcase_path)
    _clear(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("")
    lead = data["routes"].get("lead")
    DIP_LABELS.clear()
    DIP_LABELS.update({i: d["label"] for i, d in data["dips"].items()})
    adir = out / "assets"
    (adir / "data").mkdir(parents=True, exist_ok=True)
    (adir / "frame").mkdir(parents=True, exist_ok=True)

    # Shared, cached files, named by content: the renderer and its stills first (the views' figures point at them).
    assets = dict(renderer.write_assets(out))
    data["viz_files"] = viz.write_data(out, data)
    frame_html = data["docket_html"]
    frame_name = f"assets/frame/case-file-{_sha(frame_html)}.html"
    (out / frame_name).write_text(frame_html)
    data["docket_frame"] = "/" + frame_name
    data["docket_frames"] = {data["run"]["name"]: data["docket_frame"]}
    for rname, fhtml in data["extra_docket_html"].items():
        fname = f"assets/frame/case-file-{_sha(fhtml)}.html"
        (out / fname).write_text(fhtml)
        data["docket_frames"][rname] = "/" + fname
    sections = {k: clean_links(v, lead) for k, v in route_sections(data).items()}
    sections["docs"] = clean_links(docs_section(data), lead)
    sections["pictures"] = clean_links(pictures_section(), lead)
    sections["stellar"] = clean_links(stellarpages.evidence_section(), lead)
    sections["stellardocs"] = clean_links(stellarpages.docs_stellar_section(), lead)
    sections["propose"] = clean_links(stellarpages.docs_propose_section(), lead)
    sections["tessnow"] = clean_links(tessnow.section(data), lead)
    sections["vetter"] = clean_links(vetter.section(data), lead)
    sections["editions"] = clean_links(editions.section(), lead)
    payload = json.dumps(app_payload(data), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    app_js = APP_JS.replace("const RT = D.routes;\n", "const RT = D.routes;\n" + ROUTES_APP_JS, 1)
    css = strip_css(APP_CSS + brand.LOGO_CSS + renderer.RENDER_CSS + SITE_CSS + I18N_CSS + viz.VIZ_CSS + stellarpages.CSS + journey.CSS + features.CSS)
    app_js = strip_js(app_js)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    i18n_js = strip_js(i18n_script(write_i18n_assets(out), i18n_auto_script(out)))
    shell_js = strip_js(f"const I18N_SRC = '/assets/i18n-{_sha(i18n_js)}.js';\n" + SHELL_JS)
    routes_html = "".join(f'<section class="route" id="route-{k}" data-route="{k}" aria-labelledby="h-{k}" hidden>{v}</section>'
                          for k, v in sections.items())
    # The shared system view's markup (the Galaxy's sheet copies it) rides in the shared views file, not in every page.
    routes_html += f'<template id="mxsystpl">{system_stage()}</template>'

    chrome = (f'<div data-chrome-part="top">{_topbar(lead)}\n{_pagebar("planet", None, {}, lead)}</div>'
              f'<div data-chrome-part="bottom">{_footer_html(lead)}<div id="announce" class="sr" aria-live="polite" aria-atomic="true"></div>'
              f'{SEARCH_DIALOG}{LEARN_BAR}<template id="mxsystpl">{system_stage()}</template></div>')
    chrome = clean_links(chrome, lead)
    starfield = STARFIELD.format(dust=data["deco"]["dust"], bright=data["deco"]["bright"])
    for key, name, text in (("shell", "shell", shell_css()), ("css", "site", css), ("js", "site", shell_js), ("i18n", "i18n", i18n_js), ("app", "app", app_js), ("data", "data/app", payload),
                            ("routes", "views", routes_html), ("starfield", "starfield", starfield), ("chrome", "chrome", chrome)):
        ext = {"shell": "css", "css": "css", "js": "js", "i18n": "js", "app": "js", "data": "json", "routes": "html", "starfield": "svg", "chrome": "html"}[key]
        rel = f"assets/{name}-{_sha(text)}.{ext}"
        (out / rel).write_text(text)
        assets[key] = "/" + rel

    brand.copy_assets(out, social_card=True)
    shutil.copytree(FONTS_DIR, adir / "fonts", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    if data.get("galaxy"):
        (adir / "data" / CSV_NAME).write_text(map_csv(data["galaxy"]))
        (out / GALAXY_JSON).write_text(galaxy_json(data))
    if data.get("catalogue"):
        (out / CATALOGUE_JSON).write_text(json.dumps(data["catalogue"], separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    if data.get("sweep_full"):
        (out / VARIABLES_JSON).write_text(json.dumps(data["sweep_full"], separators=(",", ":"), ensure_ascii=False, allow_nan=False))

    pages: list[str] = []
    main_pages: dict[str, str] = {}

    def write(path: str, text: str) -> None:
        d = out / path.strip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(text)
        pages.append(path)
        if path in MAIN_PATHS:
            main_pages[path] = text

    def view(route, title_, desc, path, body=None, *, did=None, dargs=None, targs=None, **kw):
        tid = f"route.{route}.title"
        if targs is None and "{name}" in (ROUTE_META[route].get("title_tpl") or ""):
            targs = {"name": kw.get("name") or ROUTE_META[route]["label"]}
        write(path, page(route=route, title=title_, description=desc, path=path, body=body if body is not None else sections[route],
                         assets=assets, lead=lead, keys=(tid, targs or {}, did, dargs or {}), **kw))

    run, hero = data["run"], data["hero"]
    t = i18n.t
    view("overview", _title("overview"),
         t("desc.overview", "{tagline} A calibrated panel of Sentinels and Probes reads TESS light curves and explains every verdict. "
           "Every SetuHQ result is a {status}.", tagline=brand.TAGLINE, status=UNCONFIRMED), "/",
         did="desc.overview", dargs={"tagline": brand.TAGLINE, "status": UNCONFIRMED, "status@": "honesty.unconfirmed"})
    view("sky", _title("sky"), t("desc.sky", "The run's star on an all-sky map, with the dips the panel marked and where surveys have looked. {headline}", headline=hero["headline"]),
         "/explore/", did="desc.sky", dargs={"headline": hero["headline"]})
    view("galaxy", _title("galaxy"), t("desc.galaxy", "Every known exoplanet with a stored distance, placed in 3D around the Sun, by discovery method and year."), "/explore/galaxy/", name="Galaxy", did="desc.galaxy")
    view("mission", _title("mission"), t("desc.mission", "A tiling workspace of SetuHQ's views, linked by one selected star: the Galaxy, the sky, the light curve, the catalogue and the panel's feed."), "/explore/mission-control/", name="Mission Control", did="desc.mission")
    view("catalogue", _title("catalogue"), t("desc.catalogue", "Every planet in exoplanet.eu, searchable and sortable, each with its own page. SetuHQ did not discover these planets."), "/catalogue/", name="Catalogue", did="desc.catalogue")
    view("variables", _title("variables"), t("desc.variables", "SetuHQ's sweep of TESS sectors: every dip found and classified, each class set against its own null."), "/catalogue/everything-that-dims/", name="Everything that dims", did="desc.variables")
    feed = data["catalog"]["candidates"]
    view("explorer", _title("explorer"), t("desc.explorer", "The run's dips and their case files, and {n, plural, one {# entry} other {# entries}} of the search feed. Candidates are unconfirmed; none is a confirmed planet.", n=len(feed)),
         "/candidates/", did="desc.explorer", dargs={"n": len(feed)})
    view("planets", _title("planets"), t("desc.planets", "What each candidate's depth would imply if it were a planet: the planet-to-star radius ratio, and why no planet size is stated."), "/candidates/radius-ratios/", name="Radius ratios", did="desc.planets")
    target = hero.get("target") or "the run's star"
    for d in data["story"]["dips"] + data["showcase_dips"]:
        sec, h1 = _dip_header(sections["transit"], d, data["dips"][d["id"]]["label"],
                              (data["showcase_meta"].get(d.get("run")) or {}).get("caveat", ""), viz.panelring.for_dip(data, d["id"]))
        what = "dip" if d.get("outcome") == "rejected" else "transit"
        view("transit", _title("transit", h1), f"{h1}. The {what} played back from stored values, who on the panel marked it, and its vetting: {dip_state(d.get('outcome'))[2]}.",
             url_for("transit", {"dip": d["id"]}), body=sec, name=h1, params={"dip": d["id"]})
        view("candidates", _title("candidates", data["dips"][d["id"]]["label"]), f"Every check behind the verdict on {data['dips'][d['id']]['label']}: the transit strip, the measurements and the verdict ledger.",
             url_for("candidates", {"dip": d["id"]}), name="Case file", params={"dip": d["id"]}, targs={"name": data["dips"][d["id"]]["label"]})
    for i, (cid, ctitle) in enumerate(CHAPTERS):
        path = url_for("methods", {"ch": cid})
        view("methods", _title("methods", ctitle),
             t("desc.methods", "Chapter {i} of {n} of How it works: {title}. An animated explainer with its physics and sources.", i=i + 1, n=len(CHAPTERS), title=ctitle),
             path, body=_chapter_section(sections["methods"], cid), name=ctitle, params={"ch": cid}, partial=True,
             did="desc.methods", dargs={"i": i + 1, "n": len(CHAPTERS), "title": ctitle, "title@": "chapter." + cid}, targs={"name": ctitle, "name@": "chapter." + cid})
    view("sentinels", _title("sentinels"), t("desc.sentinels", "The reviewers behind every verdict, their calibration, and how the panel scores blind on real TESS Objects of Interest. {attribution}", attribution=ATTRIBUTION),
         "/evidence/", did="desc.sentinels", dargs={"attribution": ATTRIBUTION, "attribution@": "honesty.attribution"})
    view("leaderboard", _title("leaderboard"), t("desc.leaderboard", "Methods scored blind on the held-out half of the real-TOI benchmark, with Wilson 95% intervals."), "/evidence/leaderboard/", name="Leaderboard", did="desc.leaderboard")
    view("runs", _title("runs"), t("desc.runs", "Every search run, its errors as stored, and the configuration behind the candidate pages."), "/evidence/runs/", name="Runs", did="desc.runs")
    view("docs", _title("docs"), t("desc.docs", "Install SetuHQ, search a star, contribute a sweep, connect an AI assistant over MCP, and download the data."), "/docs/", did="desc.docs")
    view("stellar", _title("stellar"), t("desc.stellar", "Flares, pulsations, CHEOPS light curves, eclipsing binaries, rotation and transients: how far each of SetuHQ's stellar tools is validated, with every counted check and figures of real TESS data."), "/evidence/stellar/", name="Stars", did="desc.stellar")
    view("stellardocs", _title("stellardocs"), t("desc.stellardocs", "Run SetuHQ's stellar commands: flares, pulsations, public CHEOPS light curves, eclipsing binaries, rotation and transients, with their validation status and ESA's terms for CHEOPS data."), "/docs/stellar/", name="Flares and pulsations", did="desc.stellardocs")
    view("propose", _title("propose"), t("desc.propose", "Prepare a CHEOPS Guest Observers proposal with setuhq propose cheops: a drafting aid that checks the rules and the target and never submits anything."), "/docs/cheops-proposals/", name="CHEOPS proposals", did="desc.propose")
    view("tessnow", _title("tessnow"), t("desc.tessnow", "Where the TESS satellite points, sector by sector, from its published schedule: the four camera fields on the sky map and the catalogued stars inside them. Not live telemetry."), "/explore/tess-now/", name="Where TESS is now", did="desc.tessnow")
    view("vetter", _title("vetter"), t("desc.vetter", "Look at a real stored dip from SetuHQ's example runs, call it pass, flag or reject, then see what the vetting decided. A learning exercise; answers are not collected."), "/candidates/be-the-vetter/", name="Be the vetter", did="desc.vetter")
    view("editions", _title("editions"), t("desc.editions", "SetuHQ's editions: the free open core (AGPL-3.0 or a commercial licence), SetuHQ Pro (in development, under contract) and custom studies. No prices; every paid route starts with a message."), "/editions/", name="Editions", did="desc.editions")
    view("pictures", _title("pictures"), t("desc.pictures", "How SetuHQ draws its pictures: stars in their blackbody colour, and planets as artist's impressions chosen from measured radius and irradiation, with every rule and source."), "/docs/pictures/", name="How the pictures are drawn", did="desc.pictures")

    # Planet and star pages for every object the site names.
    cat = data.get("catalogue")
    if cat:
        P = cat["planets"]
        by_name = {n: k for k, n in enumerate(P["name"])}
        stars: dict[str, list[int]] = {}
        for n in _named_objects(data):
            k = by_name.get(n)
            if k is None:
                continue
            sec, nm, desc = _planet_section(sections["planet"], cat, k)
            view("planet", _title("planet", nm), desc, f"/planets/{P['slug'][k]}/", body=sec, name=nm, params={"id": P["slug"][k]})
            if P["star"][k]:
                stars.setdefault(P["star"][k], [])
        for ctx in data["run_ctx"].values():  # every example run's star
            if ctx["star"].get("name"):
                stars.setdefault(ctx["star"]["name"], [])
        for k, s in enumerate(P["star"]):
            if s in stars:
                stars[s].append(k)
        for s, idx in stars.items():
            if not idx:
                continue
            sec, desc = _star_section(sections["star"], cat, s, idx)
            view("star", _title("star", s), desc, f"/stars/{slugify(s)}/", body=sec, name=s, params={"id": slugify(s)})

    # Page not found (GitHub Pages serves it for any unknown address): it forwards old addresses, and draws any
    # catalogue planet or star the build did not pre-render.
    nf = page(route="notfound", title="Page not found · SetuHQ", description="This page is not on SetuHQ.", path=None,
              body=notfound_section(), assets=assets, lead=lead, noindex=True,
              extra_head=f"<script>{legacy_js(lead)}</script>\n")
    (out / "404.html").write_text(nf)

    # The stand-alone pages built by their own modules.
    if extras:
        from setuhq.docket import build_docket
        from setuhq.plate import build_plate
        from setuhq.report import build_report

        build_docket(run_dir, out / "candidates" / "case-file", title=f"{title}: case file, {target}", star=star,
                     require_crossmatch=require_crossmatch)
        plate_links = [(c["star"], c["plates"]) for c in data["showcase"]]
        build_plate(run_dir, out / "evidence" / "plates", title=f"{title} plates", catalog_path=catalog_path, star=star,
                    require_crossmatch=require_crossmatch, others=[x for x in plate_links if x[1] != "/evidence/plates/"])
        build_report(run_dir, out / "evidence" / "report", title=f"{title}: {target}", validation_md=validation_md,
                     benchmark_md=benchmark_md, path="/evidence/report/")
        wrap = [("evidence/plates", "plates", "Plates"), ("evidence/report", "report", "Run report")]
        standalone = ["/candidates/case-file/", "/evidence/plates/", "/evidence/report/"]
        # Every other example run: its own case file, plates and report, under its star's address.
        for x in data["extra_runs"]:
            card = next(c for c in data["showcase"] if c["run"] == x["run"])
            build_docket(x["dir"], out / card["case_file"].strip("/"), title=f"{title}: case file, {x['star']}",
                         require_crossmatch=require_crossmatch, path=card["case_file"], caveat=card["caveat"],
                         period_wrong=data["run_ctx"][x["run"]]["period_wrong"])
            build_plate(x["dir"], out / card["plates"].strip("/"), title=f"{title} plates: {x['star']}", catalog_path=None,
                        require_crossmatch=require_crossmatch, path=card["plates"], caveat=card["caveat"],
                        period_wrong=data["run_ctx"][x["run"]]["period_wrong"],
                        others=[x for x in plate_links if x[1] != card["plates"]])
            build_report(x["dir"], out / card["report"].strip("/"), title=f"{title}: {x['star']}",
                         validation_md=_showcase_md(x["run"]), benchmark_md=benchmark_md, path=card["report"])
            wrap += [(card["plates"].strip("/"), "plates", f"Plates: {x['star']}"), (card["report"].strip("/"), "report", f"Run report: {x['star']}")]
            standalone += [card["case_file"], card["plates"], card["report"]]
        for sub, route, label in wrap:
            f = out / sub / "index.html"
            f.write_text(wrap_standalone(f.read_text(), route, label, assets, lead))
        pages += standalone
        (out / "assets" / "standalone.json").write_text(json.dumps(standalone, indent=0) + "\n")

    # Old addresses.
    names = {"/app/": "The app", "/docket/": "The Docket", "/plate/": "The plates", "/report/": "The run report",
             "/dashboard/": "The dashboard", "/discoveries/": "The search feed"}
    for old, new in LEGACY_PAGES.items():
        d = out / old.strip("/")
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(forward_page(new, names[old], lead))

    # Every page with an address in every language, in each: /<lang>/... (docs/TRANSLATING.md).
    lang_pages = write_lang_pages(out, main_pages)
    (out / "assets" / "pages-i18n.json").write_text(json.dumps(lang_pages, indent=0) + "\n")

    # sitemap.xml (an index; setuhq.stubs adds the catalogue's planets and stars at deploy time) and robots.txt
    def urlset(paths):
        urls = "".join(f"<url><loc>{html.escape(brand.SITE_URL + p)}</loc></url>" for p in paths)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'

    (out / "sitemap-pages.xml").write_text(urlset(pages))
    maps = ["sitemap-pages.xml"]
    for lang in i18n.TRANSLATIONS:
        (out / f"sitemap-lang-{lang}.xml").write_text(urlset(sorted(lang_path(p, lang) for p in main_pages)))
        maps.append(f"sitemap-lang-{lang}.xml")
    maps.sort(key=lambda m: m != "sitemap-pages.xml")
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                     + "".join(f"<sitemap><loc>{brand.SITE_URL}/{m}</loc></sitemap>" for m in maps) + "</sitemapindex>\n")
    # The small pages for the rest of the catalogue: their template and the header and footer they borrow.
    (out / "assets" / "stub-template.html").write_text(stub_template(assets, lead))
    (out / "robots.txt").write_text(f"User-agent: *\nDisallow: /assets/frame/\nAllow: /\n\nSitemap: {brand.SITE_URL}/sitemap.xml\n")
    (out / "assets" / "pages.json").write_text(json.dumps(sorted(set(pages)), indent=0) + "\n")
    return out / "index.html"


# The stand-alone pages (the case file, the plates, the run report) carry their own data and code inline, so they
# work saved to disk or printed; they have a budget of their own.
STANDALONE = ("candidates/case-file", "evidence/plates", "evidence/report")
STANDALONE_BUDGET = 400_000
# Each example run's comparison with the literature (scripts/showcase_compare.py), embedded in its run report.
SHOWCASE_MD_DIR = "docs/results/showcase"


def _showcase_md(run: str) -> str | None:
    path = Path(SHOWCASE_MD_DIR) / f"{run}.md"
    return str(path) if path.exists() else None


def _standalone(rel: str) -> bool:
    """A stand-alone page: the lead run's (candidates/case-file, evidence/plates, evidence/report) or another example
    run's (candidates/<star>/case-file, evidence/plates/<star>, evidence/report/<star>)."""
    parts = rel.split("/")
    return rel in STANDALONE or (len(parts) == 3 and parts[0] == "candidates" and parts[2] == "case-file") or \
        (len(parts) == 3 and "/".join(parts[:2]) in ("evidence/plates", "evidence/report"))


# ---------------------------------------------------------------------------------------------------------
# The stand-alone pages (the run report, the plates) in the site's header and footer
# ---------------------------------------------------------------------------------------------------------

def stub_template(assets: dict, lead: str | None) -> str:
    """The page setuhq.stubs fills in for each catalogue planet and star: its own head, a heading and a line of
    facts, and the shared files, which bring the header, the footer and the full page."""
    return f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{{{TITLE}}}}</title>
{brand.head("{{TITLE}}", "{{DESC}}", "{{PATH}}", prefix="/")}
<meta name="color-scheme" content="dark light">
<script>{THEME_HEAD_JS}</script>
<link rel="stylesheet" href="/assets/fonts/fonts.css"><link rel="stylesheet" href="{assets['css']}">
<script src="{assets['render']}" defer></script><script src="{assets['js']}" defer></script>
</head>
<body data-page="{{{{ROUTE}}}}" data-route="{{{{ROUTE}}}}" data-data="{assets['data']}" data-routes="{assets['routes']}" data-app="{assets['app']}" data-chrome="{assets['chrome']}">
{starfield_html(assets['starfield'])}
<div id="chrome-top"></div>
<main id="main"><div id="content" tabindex="-1"><section class="route" id="route-{{{{ROUTE}}}}" data-route="{{{{ROUTE}}}}" aria-labelledby="h-{{{{ROUTE}}}}" data-partial>
<header><h1 class="lead-h" id="h-{{{{ROUTE}}}}" tabindex="-1">{{{{H1}}}}</h1><p>{{{{FACTS}}}}</p></header>
{{{{PORTRAIT}}}}
<noscript><p>{{{{NOSCRIPT}}}} <a href="/catalogue/">The catalogue of known planets</a> · <a href="/">SetuHQ home</a></p></noscript>
</section></div></main>
<div id="chrome-bottom"></div>
</body></html>
"""


def shell_css() -> str:
    """The header's, menu's, page bar's and footer's styles for a page with its own stylesheet: the colour tokens
    scoped to those parts (.shellscope), so the page's own tokens and layout are untouched."""
    tokens = tokens_css(".shellscope")
    base = ("\n.shellscope,.shellscope *{box-sizing:border-box}"
            ".shellscope{font:400 15px/1.5 var(--sans);letter-spacing:-.01em;color:var(--ink);-webkit-font-smoothing:antialiased}"
            ".shellscope a{color:var(--cyan)}.shellscope :focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:8px}"
            ".shellscope .sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}"
            ".shellscope .brand{display:inline-flex;align-items:center;gap:9px;height:44px;min-height:44px;line-height:0;color:var(--ink);text-decoration:none}"
            ".shellscope .nav ul{list-style:none;margin:0;display:flex;gap:2px;padding:3px;border-radius:999px;background:var(--panel-2);border:1px solid var(--line)}"
            ".shellscope .nav a{display:flex;align-items:center;min-height:38px;padding:0 16px;border-radius:999px;color:var(--ink-2);text-decoration:none;font-size:14px;font-weight:500;white-space:nowrap}"
            ".shellscope .nav a:hover{color:var(--ink)}.shellscope .nav a[aria-current=\"page\"]{background:var(--seg-bg);color:var(--seg-ink)}"
            ".sitefoot.shellscope{margin-top:0}"
            # The pages' own element rules (a sticky, filled <nav>, a spaced <footer>) do not reach the shell.
            ".shellscope nav{position:static;background:transparent;border:0;z-index:auto;top:auto}"
            ".shellscope .footnav h2{letter-spacing:0}"
            "nav.report-nav{top:60px}\n")
    site = "\n".join(l for l in SITE_CSS.split("\n") if not l.strip().startswith(("main{", "main ", "body[data-route")))
    return tokens + base + brand.LOGO_CSS + site + I18N_CSS


def wrap_standalone(page_html: str, route: str, name: str, assets: dict, lead: str | None) -> str:
    """A page built by its own module (the report, the plates), with the site's header, breadcrumbs, section links
    and footer, and the theme control (their stylesheets follow data-theme already). Search needs the app, so it is
    left out; the page's own logo link goes, since the header has it."""
    page_html = re.sub(r'<a href="/" aria-label="SetuHQ, home">.*?</a>', "", page_html, count=1, flags=re.S)
    head = (f'<script>{THEME_HEAD_JS}</script><link rel="stylesheet" href="/assets/fonts/fonts.css">'
            f'<link rel="stylesheet" href="{assets["shell"]}"><script src="{assets["i18n"]}" defer></script><script src="{assets["js"]}" defer></script>')
    top = (_topbar(lead).replace(SEARCH_BUTTON, "").replace('<header class="topbar">', '<header class="topbar shellscope">', 1)
           .replace('<a class="skip" href="#content">Skip to content</a>\n', ""))
    bar = _pagebar(route, name, {}, lead).replace('<div class="pagebar">', '<div class="pagebar shellscope">', 1)
    bar = re.sub(r'<div class="pagetools">.*?</div></div></div>$', "</div></div>", bar, flags=re.S)
    foot = _footer_html(lead).replace('<footer class="sitefoot">', '<footer class="sitefoot shellscope">', 1)
    page_html = page_html.replace("</head>", head + "</head>", 1)
    page_html = re.sub(r"(<body[^>]*)>", lambda m: m.group(1) + " data-i18n-auto>\n" + top + "\n" + bar, page_html, count=1)
    return page_html.replace("</body>", foot + '<div id="announce" class="sr" aria-live="polite"></div></body>', 1)


# The shared files' budgets (bytes), and two pages' own (characters), on top of PAGE_BUDGET and STANDALONE_BUDGET.
# The shell's script (site-*.js: the header, menu and theme, and SetuUI's figure utilities) runs on every page, the
# stand-alone pages and deploy-time stubs included, so it stays small.
SHELL_BUDGET = 16_000
# The languages' script (i18n-*.js: the picker, the suggestion and the formatting) runs on every page too; the
# catalogues themselves are separate files, one per language (assets/i18n/<lang>-*.json), fetched only when used.
I18N_BUDGET = 10_000
CATALOGUE_BUDGET = 160_000
ASSET_BUDGET = {"site-*.css": 140_000, "app-*.js": 430_000, "site-*.js": SHELL_BUDGET, "i18n-*.js": I18N_BUDGET, "i18n/*.json": CATALOGUE_BUDGET,
                "render-*.js": renderer.RENDER_BUDGET,
                "data/sky-*.json": viz.DATA_BUDGET["sky"], "data/stories-*.json": viz.DATA_BUDGET["stories"]}
PAGE_BUDGETS = {"index.html": 90_000, "explore/index.html": 160_000}
PAGE_BUDGETS.update({f"{lang}/{rel}": cap for lang in i18n.TRANSLATIONS for rel, cap in list(PAGE_BUDGETS.items())})
STILL_BUDGET = {512: 40_000, 160: 8_000, "all": 850_000}
STUB_BUDGET = 4_096


def check_asset_budget(out_dir: str | Path) -> list[str]:
    """The shared files over their budgets (the stylesheet, the app's script, the shell's script, the renderer, the data files, each
    still and all of them) and the home and Explore pages over theirs, as 'path: size' lines."""
    out, bad = Path(out_dir), []
    for pattern, cap in ASSET_BUDGET.items():
        for f in sorted((out / "assets").glob(pattern)):
            if f.stat().st_size > cap:
                bad.append(f"{f.relative_to(out)}: {f.stat().st_size:,} bytes (budget {cap:,})")
    for rel, cap in PAGE_BUDGETS.items():
        f = out / rel
        if f.exists() and len(f.read_text()) > cap:
            bad.append(f"{rel}: {len(f.read_text()):,} characters (budget {cap:,})")
    total = 0
    for f in sorted((out / "assets" / "render").glob("*/*.webp")):
        n = f.stat().st_size
        total += n
        px = 160 if f.stem.endswith("-160") else 512
        if n > STILL_BUDGET[px]:
            bad.append(f"{f.relative_to(out)}: {n:,} bytes (budget {STILL_BUDGET[px]:,})")
    if total > STILL_BUDGET["all"]:
        bad.append(f"assets/render: {total:,} bytes of stills (budget {STILL_BUDGET['all']:,})")
    return bad


def check_budget(out_dir: str | Path, budget: int = PAGE_BUDGET) -> list[str]:
    """Pages over the per-page budget (characters of HTML), as 'path: size' lines."""
    bad = []
    for p in sorted(Path(out_dir).rglob("*.html")):
        if p.parent.name in ("frame",) or p.name.startswith("views-"):
            continue  # shared, cached files, not pages
        n = len(p.read_text())
        rel = p.parent.relative_to(out_dir).as_posix()
        if n > (STANDALONE_BUDGET if _standalone(rel) else budget):
            bad.append(f"{p.relative_to(out_dir)}: {n:,}")
    return bad

"""The Docket: a case file for each signal and its dips.

The unit of analysis is the signal: one per (subject, BLS period), with the
dips at its epochs as children; a dip with no BLS period is its own signal.
The list on the left groups dips under their signal and the run header counts
both ("N signals · M dips").

Each dip gets one three-state vetting outcome, computed here in Python
(``outcome``): rejected by vetting (any disqualifying flag), flagged for review
(a non-disqualifying flag, or any check not measured), passed vetting (every
check measured and passing). A check whose value is missing is "not measured",
never a pass. Feed admission rules from discover.py are shown apart from vetting.

The dossier leads with that outcome, the feed-rule result and a known-planet
line from the NASA Exoplanet Archive (fetched at build time and stored in the
run directory as crossmatch.json, or stored as "not run" when offline). Then the
transit strip: binned flux with stored ±1σ, the box model at measured depth and
duration (nothing is fitted), and one lane per reviewer, each labelled with its
kind (simulated detector or Claude). Then the signal's dips, the subject in
context, comparisons, the verdict ledger, the reviewers and provenance.

BLS periods and epochs are per subject (a fixed-length cut of a sector), not
per sector, and every candidate is unconfirmed.

Keyboard: j and k move through the dips, ↑ and ↓ too when the list has focus;
1, 2, 3 and 0 filter signals by outcome; s collapses the strip. With the strip
focused, ← and → step through bins and the readout is announced. The filter,
the selected dip and each section's collapsed state persist in localStorage
when it is available.
"""

from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from exoplan.dashboard import _load_run
from exoplan.discover import MAX_FEED_DEPTH_PPM, MIN_FEED_TRANSITS
from exoplan.vet import DISQUALIFYING

DOCKET_CSS = """
:root{--paper:#f7f6f2;--ink:#16181d;--rule:#d9d7d0;--muted:#6b6e76;--fit:#1f5fbf;--pass:#2e7d4f;--flag:#946c00;--reject:#b23a3a;--panel:#fcfbf8;--sel:#ebe9e1;
--l-det:#8a7e57;--l-det2:#5c7f8f;--l-cl1:#7b5ea7;--l-cl2:#b0623a;--cons:#16181d}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--paper:#121317;--ink:#ecebe6;--rule:#2a2c33;--muted:#9a9ca4;--fit:#6fa0ff;--pass:#5cc08a;--flag:#e0b243;--reject:#ef7070;--panel:#17181d;--sel:#22242b;--l-det:#b5a777;--l-det2:#8bb0c0;--l-cl1:#a98bd6;--l-cl2:#d88a62;--cons:#ecebe6;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#121317;--ink:#ecebe6;--rule:#2a2c33;--muted:#9a9ca4;--fit:#6fa0ff;--pass:#5cc08a;--flag:#e0b243;--reject:#ef7070;--panel:#17181d;--sel:#22242b;--l-det:#b5a777;--l-det2:#8bb0c0;--l-cl1:#a98bd6;--l-cl2:#d88a62;--cons:#ecebe6;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 "Inter Tight",system-ui,sans-serif;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));min-width:0}
:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.mono{font-family:"JetBrains Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--fit);outline-offset:2px}
.app{display:grid;grid-template-columns:340px minmax(0,1fr);min-height:100vh;min-width:0}
.list{border-right:1px solid var(--rule);padding:18px 0;overflow:auto;max-height:100vh;position:sticky;top:0;min-width:0}
.run{padding:0 16px 14px;border-bottom:1px solid var(--rule);margin-bottom:8px}
.run h1{font:600 17px/1.2 "Inter Tight",sans-serif;margin:0 0 6px}
.counts{margin:0 0 8px;font:13px/1.5 "JetBrains Mono",monospace}
.revcount{color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:12px "JetBrains Mono",monospace;border:1px solid var(--rule);background:none;color:var(--muted);padding:3px 8px;border-radius:999px;cursor:pointer}
.chip[aria-pressed="true"]{color:var(--ink);border-color:var(--ink)}
.listtoggle{display:none;margin-top:10px;font:12px "JetBrains Mono",monospace;background:none;border:1px solid var(--rule);color:var(--ink);border-radius:4px;padding:4px 10px;cursor:pointer}
#rows:focus-visible{outline:2px solid var(--fit);outline-offset:-2px}
.sig{border-bottom:1px solid var(--rule);padding:4px 0 6px}
.sighead{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 16px 4px;cursor:pointer}
.sighead small,.row small{display:block;font:11px "JetBrains Mono",monospace;color:var(--muted)}
.signame{font-weight:600;font-size:13px}
.row{display:grid;grid-template-columns:90px minmax(0,1fr) auto;gap:10px;align-items:center;padding:6px 16px 6px 28px;cursor:pointer;border-left:3px solid transparent}
.row:hover{background:var(--sel)}
.row[aria-selected="true"]{border-left-color:var(--ink);background:var(--sel)}
#rows:focus-visible .row[aria-selected="true"]{outline:2px solid var(--fit);outline-offset:-2px}
.glyph{font:600 12px "JetBrains Mono",monospace;white-space:nowrap}
.word{font-weight:500}
.badge{font:600 11px "JetBrains Mono",monospace;white-space:nowrap}
.g-pass{color:var(--pass)}.g-flag{color:var(--flag)}.g-fail{color:var(--reject)}.g-nm{color:var(--muted)}
.dossier{padding:22px 28px 40px;min-width:0;display:grid;gap:22px;align-content:start}
#dtop,#drest{display:grid;gap:22px;min-width:0;align-content:start}
#listslot:empty{display:none}
.outcome{border:1px solid currentColor;border-left-width:6px;border-radius:6px;padding:12px 14px;display:grid;gap:4px;background:var(--panel)}
.out-main{font:600 20px/1.2 "Inter Tight",sans-serif}
.out-main .glyph{font:inherit}
.out-why,.out-feed,.xm{margin:0;font:13px/1.5 "Inter Tight",sans-serif;color:var(--ink)}
.xm-k{color:var(--muted)}
.head{display:flex;flex-wrap:wrap;gap:8px 24px;align-items:baseline;justify-content:space-between;border-bottom:1px solid var(--rule);padding-bottom:12px}
.head h2{font:600 22px/1.25 "Inter Tight",sans-serif;margin:0}
.dipid{font:500 14px "JetBrains Mono",monospace;color:var(--muted);overflow-wrap:anywhere}
.sigout{font:12px "JetBrains Mono",monospace;color:var(--muted)}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;font:13px "JetBrains Mono",monospace}
.facts span{color:var(--muted);margin-right:6px}
.sec{display:grid;gap:8px;min-width:0}
.sec>header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 12px}
.sec>header h3{margin:0}
.sectoggle{font:600 12px/1 "JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);background:none;border:0;padding:4px 0;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.sectoggle:hover{color:var(--ink)}
.caret{display:inline-block;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid currentColor;transition:transform .15s}
.sectoggle[aria-expanded="false"] .caret{transform:rotate(-90deg)}
.sec>header em{font:12px "Inter Tight",sans-serif;color:var(--muted);font-style:normal}
.secbody{display:grid;gap:8px;min-width:0}
.secbody[hidden]{display:none}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{font:11px "JetBrains Mono",monospace;fill:var(--muted)}
svg .grid{stroke:var(--rule);stroke-width:1}
svg .hl{fill:var(--ink)}
.hero-wrap{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:8px}
.dips{display:flex;flex-wrap:wrap;gap:6px}
.dipbtn{font:12px "JetBrains Mono",monospace;background:var(--panel);color:var(--ink);border:1px solid var(--rule);border-radius:4px;padding:5px 9px;cursor:pointer}
.dipbtn.cur{border-color:var(--ink);background:var(--sel)}
.compare{display:grid;gap:12px;grid-template-columns:repeat(3,minmax(0,1fr))}
.compare>div{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:8px;min-width:0}
.compare p{margin:4px 0 0;font:12px "Inter Tight",sans-serif;color:var(--muted)}
.scroll{min-width:0}
.ledger{width:100%;border-collapse:collapse;font:13px "JetBrains Mono",monospace}
.ledger td{padding:7px 8px;border-bottom:1px solid var(--rule);vertical-align:top;min-width:0;overflow-wrap:anywhere}
.ledger td.c-name{white-space:nowrap}
.ledger tr.chk:focus-visible{outline:2px solid var(--fit);outline-offset:-2px}
.ledger tr.chk-not_measured td.c-val{color:var(--muted)}
.ledger th.grp{text-align:left;font:600 11px "JetBrains Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding:14px 8px 6px;border-bottom:1px solid var(--rule)}
.ledger .why{font:13px "Inter Tight",sans-serif;color:var(--muted)}
.rat{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));min-width:0}
.rat>div{border-top:2px solid var(--rule);padding-top:8px;min-width:0}
.rat b{font:600 12px "JetBrains Mono",monospace}
.rat p{margin:6px 0 0;color:var(--muted);font-size:13px}
.kind{display:inline-block;font:600 11px "JetBrains Mono",monospace;border-radius:3px;padding:0 5px;border:1px solid currentColor}
.kind-sim{color:var(--l-det)}.kind-cl{color:var(--l-cl1)}
.prov{font:11px/1.6 "JetBrains Mono",monospace;color:var(--muted);border-top:1px solid var(--rule);padding-top:10px;overflow-wrap:anywhere}
.empty{color:var(--muted);font-style:italic;padding:12px 0}
.hint{font:12px "JetBrains Mono",monospace;color:var(--muted)}
kbd{font:11px "JetBrains Mono",monospace;border:1px solid var(--rule);border-radius:4px;padding:0 4px}
.strip{position:relative;padding:8px;min-width:0;overflow:hidden}
.strip svg{width:100%;touch-action:pan-y}
.strip .lanelbl,.strip .halo{paint-order:stroke;stroke:var(--panel);stroke-width:3px;stroke-linejoin:round}
.tip{position:absolute;z-index:2;max-width:min(340px,80%);background:var(--paper);border:1px solid var(--rule);border-radius:4px;padding:6px 8px;font:11px/1.45 "JetBrains Mono",monospace;color:var(--ink);pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.readout{margin-top:6px;min-height:3em;font:11px/1.45 "JetBrains Mono",monospace;color:var(--ink);overflow-wrap:anywhere}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font:12px "Inter Tight",sans-serif;color:var(--muted)}
.legend i{display:inline-block;vertical-align:middle;margin-right:6px}
.legend .k-pt{width:6px;height:6px;border-radius:50%;background:var(--ink)}
.legend .k-box{width:16px;height:0;border-top:2px solid var(--fit)}
.legend .k-band{width:12px;height:10px;background:var(--fit);opacity:.25}
.legend .k-lane{width:14px;height:8px;border-radius:2px;background:var(--l-det)}
.scope{margin:0;font:12px/1.5 "Inter Tight",sans-serif;color:var(--muted)}
.epochs{margin:6px 0 0;padding-left:16px;font:12px "JetBrains Mono",monospace;color:var(--ink)}
@media (max-width:900px){
  .app{grid-template-columns:minmax(0,1fr)}
  .list{display:none}
  .dossier{padding:16px 0}
  .compare{grid-template-columns:minmax(0,1fr)}
  .listpanel{border:1px solid var(--rule);border-radius:6px;padding:14px 0 6px;background:var(--panel)}
  .listtoggle{display:inline-block}
  #listbody[data-collapsed="true"]{display:none}
  .out-main{font-size:18px}
  .head h2{font-size:19px}
  #sec-strip{order:2}
  #dtop .facts{order:3}
}
@media (max-width:640px){
  .ledger,.ledger tbody{display:block}
  .ledger tr{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) minmax(0,1fr);border-bottom:1px solid var(--rule)}
  .ledger th.grp{display:block;grid-column:1/-1}
  .ledger td{border-bottom:0;padding:6px 6px 2px}
  .ledger td.c-name{white-space:normal}
  .ledger td.why{grid-column:1/-1;padding:0 6px 8px}
  .row{grid-template-columns:70px minmax(0,1fr) auto;padding-left:20px}
}
"""

DOCKET_JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const $ = (s, e=document) => e.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (x, d=2) => (x === null || x === undefined || Number.isNaN(x)) ? '–' : Number(x).toFixed(d);
const NS = 'http://www.w3.org/2000/svg';
function el(tag, a={}, p){ const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
function tx(svg, x, y, s, anchor='start', cls=''){ const t = el('text', {x, y, 'text-anchor': anchor, class: cls}, svg); t.textContent = s; return t; }
const REV_COLOUR = {'volunteer-sensitive':'var(--l-det)','volunteer-typical':'var(--l-det2)','volunteer-cautious':'var(--l-det2)','claude-volunteer':'var(--l-cl1)','claude-skeptic':'var(--l-cl2)'};
const colourOf = name => REV_COLOUR[name] || 'var(--muted)';
// Reviewer kind, always shown beside the name: a simulated detector is not a person.
const isClaude = k => k === 'claude' || k === 'claude_code';
const KIND_TAG = k => k === 'simulated' ? 'SIM' : isClaude(k) ? 'CLAUDE' : String(k || '?').toUpperCase();
const KIND_LONG = k => k === 'simulated' ? 'simulated detector (not a person)' : isClaude(k) ? `Claude model reviewer (${k})` : String(k || 'unknown kind');
// Outcome of a dip or signal: three states, decided in Python (docket.outcome).
const OUT_LABEL = D.outcome_label;
const OUT_GLYPH = {passed:'✓', flagged:'!', rejected:'✕'};
const OUT_CLS = {passed:'g-pass', flagged:'g-flag', rejected:'g-fail'};
// State of one check: a missing value is "not measured", shown as a neutral dash, never a pass.
const CHK_GLYPH = {pass:'✓', flag:'!', fail:'✕', not_measured:'–'};
const CHK_WORD = {pass:'pass', flag:'flag', fail:'fail', not_measured:'not measured'};
const CHK_CLS = {pass:'g-pass', flag:'g-flag', fail:'g-fail', not_measured:'g-nm'};
const outBadge = o => o ? `<span class="badge ${OUT_CLS[o]}"><span class="glyph" aria-hidden="true">${OUT_GLYPH[o]}</span> ${esc(OUT_LABEL[o])}</span>` : '';
const byId = Object.fromEntries(D.candidates.map(c => [c.candidate_id, c]));
const sigById = Object.fromEntries(D.signals.map(s => [s.signal_id, s]));
const FILTERS = ['all', 'passed', 'flagged', 'rejected'];
const SECTIONS = ['strip', 'signal', 'ctx', 'cmp', 'ledger', 'rev'];
const narrowMQ = window.matchMedia('(max-width: 900px)');

// ---------- persisted view (localStorage, optional) ----------
const STORE_KEY = 'exoplan-docket:' + D.title;
function loadView(){ try { const v = JSON.parse(localStorage.getItem(STORE_KEY) || '{}'); return (v && typeof v === 'object') ? v : {}; } catch (e) { return {}; } }
const saved = loadView();
const state = {
  filter: FILTERS.includes(saved.filter) ? saved.filter : 'all',
  selected: (saved.dip && byId[saved.dip]) ? saved.dip : null,
  collapsed: (saved.collapsed && typeof saved.collapsed === 'object') ? saved.collapsed : {},
  listCollapsed: !!saved.listCollapsed,
};
function saveView(){
  try { localStorage.setItem(STORE_KEY, JSON.stringify({filter: state.filter, dip: state.selected, signal: state.selected ? byId[state.selected].signal_id : null, collapsed: state.collapsed, listCollapsed: state.listCollapsed})); } catch (e) { /* storage unavailable: the page works without it */ }
}

function sigLabel(s){ return s.period_days ? `P ${fmt(s.period_days,3)} d` : 'single dip, no BLS period'; }
function epochOf(c){ return (c.period_days && c.bls_t0 !== null && c.bls_t0 !== undefined) ? Math.round((c.t_center - c.bls_t0)/c.period_days) : null; }
function visibleSignals(){ return D.signals.filter(s => state.filter === 'all' || s.outcome === state.filter); }
function visibleDips(){ return visibleSignals().flatMap(s => s.dips); }
function reviewerSummary(names){
  const kinds = names.map(n => D.reviewers[n]);
  const sim = kinds.filter(k => k === 'simulated').length, cl = kinds.filter(isClaude).length, other = kinds.length - sim - cl;
  return [sim ? `${sim} simulated` : '', cl ? `${cl} Claude` : '', other ? `${other} other` : ''].filter(Boolean).join(', ') || 'none';
}

function renderRunHeader(){
  const c = D.counts, box = $('#run');
  const chips = [['all', 'all'], ['passed', `${c.passed} passed`], ['flagged', `${c.flagged} flagged`], ['rejected', `${c.rejected} rejected`]];
  box.innerHTML = `<h1>${esc(D.title)}</h1>
    <p class="counts"><b>${c.signals} signal${c.signals===1?'':'s'} · ${c.dips} dip${c.dips===1?'':'s'}</b><br>
    <span class="revcount">${c.reviewers} reviewers: ${reviewerSummary(Object.keys(D.reviewers))}</span></p>
    <div class="chips" role="group" aria-label="Filter signals by vetting outcome">${chips.map(([k,l]) => `<button class="chip" data-f="${k}" aria-pressed="${state.filter===k}">${l}</button>`).join('')}</div>
    <div class="hint" style="margin-top:8px"><kbd>j</kbd>/<kbd>k</kbd> move · <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> filter, <kbd>0</kbd> all · <kbd>s</kbd> strip</div>
    <button class="listtoggle" id="listtoggle" aria-expanded="${!state.listCollapsed}" aria-controls="listbody">${state.listCollapsed ? 'Show' : 'Hide'} the signal list</button>`;
  box.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => setFilter(b.dataset.f)));
  $('#listtoggle').addEventListener('click', () => { state.listCollapsed = !state.listCollapsed; applyListCollapse(); saveView(); });
  applyListCollapse();
}
function applyListCollapse(){
  const t = $('#listtoggle'); if (!t) return;
  t.setAttribute('aria-expanded', String(!state.listCollapsed));
  t.textContent = `${state.listCollapsed ? 'Show' : 'Hide'} the signal list`;
  $('#listbody').dataset.collapsed = String(state.listCollapsed);
}
function setFilter(f){ state.filter = f; renderRunHeader(); renderList(); saveView(); }

function miniSpark(c){
  const subj = D.subjects[c.subject_id]; if (!subj) return '';
  const W=90, H=24, t0 = c.t_center - 0.25, t1 = c.t_center + 0.25;
  const pts = subj.time.map((t,i)=>[t,subj.flux[i]]).filter(([t]) => t>=t0 && t<=t1);
  if (pts.length < 2) return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true"></svg>`;
  const lo = Math.min(...pts.map(p=>p[1])), hi = Math.max(...pts.map(p=>p[1])), span = (hi-lo)||1e-5;
  const d = pts.map(([t,f],i)=> (i?'L':'M')+((t-t0)/(t1-t0)*W).toFixed(1)+','+((1-(f-lo)/span)*(H-4)+2).toFixed(1)).join('');
  return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><path d="${d}" fill="none" stroke="var(--ink)" stroke-width="1.2"/></svg>`;
}

const optId = id => 'opt-' + id;
function renderList(){
  const box = $('#rows'), sigs = visibleSignals();
  box.innerHTML = '';
  if (!sigs.length){ box.innerHTML = '<div class="empty" style="padding:16px">No signals with this outcome in this run.</div>'; box.removeAttribute('aria-activedescendant'); return; }
  for (const s of sigs){
    const g = document.createElement('div'); g.setAttribute('role','group'); g.className = 'sig';
    g.setAttribute('aria-labelledby', 'lbl-' + s.signal_id);
    const head = document.createElement('div'); head.className = 'sighead'; head.id = 'lbl-' + s.signal_id;
    head.innerHTML = `<div><div class="mono signame">${esc(sigLabel(s))}</div><small>subject ${esc(s.subject_id)} · ${s.dips.length} dip${s.dips.length===1?'':'s'}${s.period_days ? ` · ${s.n_transits} BLS transits` : ''}</small></div>${outBadge(s.outcome)}`;
    head.addEventListener('click', () => select(s.dips[0]));
    g.appendChild(head);
    for (const id of s.dips){
      const c = byId[id], e = epochOf(c), d = document.createElement('div');
      d.className = 'row'; d.setAttribute('role','option'); d.id = optId(id); d.dataset.id = id;
      d.setAttribute('aria-selected', String(state.selected === id));
      d.setAttribute('aria-label', `${id}${e !== null ? ', epoch ' + e : ''}, ${fmt(c.t_center,3)} ${c.time_unit}, ${fmt(c.depth_ppm,0)} ppm, SNR ${fmt(c.snr,1)}, ${OUT_LABEL[c.outcome]}`);
      d.innerHTML = `${miniSpark(c)}<div><div class="mono" style="font-size:12px">${e !== null ? 'epoch E'+e+' · ' : ''}${esc(id.split('-').pop())}</div><small>${fmt(c.t_center,3)} ${esc(c.time_unit)} · ${fmt(c.depth_ppm,0)} ppm · SNR ${fmt(c.snr,1)}</small></div><span class="glyph ${OUT_CLS[c.outcome]}"><span aria-hidden="true">${OUT_GLYPH[c.outcome]}</span> <span class="word">${esc(c.outcome)}</span></span>`;
      d.addEventListener('click', () => { select(id); box.focus({preventScroll:true}); });
      g.appendChild(d);
    }
    box.appendChild(g);
  }
  syncActive();
}
function syncActive(){
  const box = $('#rows');
  document.querySelectorAll('.row').forEach(r => r.setAttribute('aria-selected', String(r.dataset.id === state.selected)));
  if (state.selected && document.getElementById(optId(state.selected))) box.setAttribute('aria-activedescendant', optId(state.selected));
  else box.removeAttribute('aria-activedescendant');
}

function select(id, announce=true){
  if (!byId[id]) return;
  state.selected = id;
  syncActive();
  renderDossier();
  try { history.replaceState(null, '', '#' + id); } catch (e) {}
  saveView();
  const c = byId[id];
  // The listbox announces through aria-activedescendant; elsewhere (j/k) say it once.
  if (announce && document.activeElement !== $('#rows')) $('#announce').textContent = `Selected ${id}, ${OUT_LABEL[c.outcome]}, signal ${sigLabel(sigById[c.signal_id])}.`;
}

function moveSelection(step){
  const ids = visibleDips(); if (!ids.length) return;
  const i = ids.indexOf(state.selected);
  const next = ids[i < 0 ? 0 : Math.min(ids.length-1, Math.max(0, i + step))];
  select(next);
  document.getElementById(optId(next))?.scrollIntoView({block:'nearest'});
}

// ---------- dossier ----------
function niceTicks(lo, hi, n){
  const raw = (hi-lo)/Math.max(1,n), mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo/step)*step; v <= hi + 1e-12; v += step) out.push(+v.toPrecision(12));
  return out;
}

// The transit strip: stored binned flux with stored ±1σ, the box model at the
// measured depth and duration (c.box, built in Python, nothing fitted), and one
// lane per reviewer on the same time axis. The consensus band runs through both.
// Keyboard: with the strip focused, ← and → step through the stored bins
// (Shift for ten), Home and End jump; the readout below is an aria-live region.
function strip(c, subj, marks, decisions, wrap){
  wrap.innerHTML = '';
  const narrow = wrap.clientWidth < 600;
  const W = Math.max(240, Math.round(wrap.clientWidth - 16)), H = narrow ? 280 : 440;
  const names = Object.keys(D.reviewers), lh = narrow ? 15 : 22;
  const pl = narrow ? 42 : 190, pr = narrow ? 8 : 18, pt = 16, gap = narrow ? 10 : 18, axisH = narrow ? 24 : 30;
  const lanesTop = H - axisH - names.length*lh, upperBottom = lanesTop - gap;
  const dur = c.t_end - c.t_start, half = Math.max(4*dur, 0.25);
  const t0 = c.t_center - half, t1 = c.t_center + half;
  const hasErr = Array.isArray(subj.flux_err) && subj.flux_err.length === subj.flux.length;
  const pts = [];
  subj.time.forEach((t,i) => { if (t >= t0 && t <= t1) pts.push({t, p:(subj.flux[i]-1)*1e6, e: hasErr ? subj.flux_err[i]*1e6 : null}); });
  const depth = c.depth_ppm;
  let lo = Math.min(0, -depth), hi = Math.max(0, -depth);
  for (const q of pts){ lo = Math.min(lo, q.p - (q.e||0)); hi = Math.max(hi, q.p + (q.e||0)); }
  const yr = (hi - lo) || 100; lo -= 0.22*yr; hi += 0.08*yr;
  const X = t => pl + (t-t0)/(t1-t0)*(W-pl-pr), Y = p => pt + (hi-p)/(hi-lo)*(upperBottom-pt);
  const svg = el('svg', {viewBox:`0 0 ${W} ${H}`, role:'img', class:'stripsvg',
    'aria-label': `Transit strip for ${c.candidate_id}: ${pts.length} binned points, box model at measured depth ${fmt(depth,0)} ppm and duration ${fmt(c.duration_hours,2)} h, ${names.length} reviewer lanes (${reviewerSummary(names)})`}, wrap);
  svg.style.height = H + 'px';
  const fs = narrow ? 9 : 11;
  const T = (x, y, s, a='start', cls='') => { const t = tx(svg, x, y, s, a, cls); t.style.fontSize = fs + 'px'; return t; };
  if (t0 < subj.start) el('rect', {x:pl, y:pt, width:Math.max(0,X(subj.start)-pl), height:H-axisH-pt, fill:'var(--sel)'}, svg);
  if (t1 > subj.end) el('rect', {x:X(subj.end), y:pt, width:Math.max(0,W-pr-X(subj.end)), height:H-axisH-pt, fill:'var(--sel)'}, svg);
  el('rect', {x:X(c.t_start), y:pt, width:Math.max(2,X(c.t_end)-X(c.t_start)), height:H-axisH-pt, fill:'var(--fit)', opacity:.09}, svg);
  for (const t of [c.t_start, c.t_end]) el('line', {x1:X(t), x2:X(t), y1:pt, y2:H-axisH, stroke:'var(--fit)', 'stroke-dasharray':'3 3', opacity:.6}, svg);
  for (const p of niceTicks(lo, hi, narrow ? 3 : 5)){ el('line', {x1:pl,x2:W-pr,y1:Y(p),y2:Y(p),class:'grid'}, svg); T(pl-6, Y(p)+3, Math.round(p), 'end'); }
  for (const t of niceTicks(t0, t1, narrow ? 3 : 6)){ el('line', {x1:X(t),x2:X(t),y1:H-axisH,y2:H-axisH+4,stroke:'var(--muted)'}, svg); T(X(t), H-axisH+(narrow?13:16), t.toFixed(2), 'middle'); }
  T(pl, pt-5, 'ppm vs 1.0', 'start');
  T(W-pr, pt-5, `time (${c.time_unit})`, 'end');
  el('line', {x1:pl,x2:W-pr,y1:upperBottom,y2:upperBottom,stroke:'var(--rule)'}, svg);
  for (const q of pts){
    if (q.e !== null) el('line', {x1:X(q.t), x2:X(q.t), y1:Y(q.p-q.e), y2:Y(q.p+q.e), stroke:'var(--ink)', opacity:.45}, svg);
    el('circle', {cx:X(q.t), cy:Y(q.p), r:narrow ? 2 : 2.6, fill:'var(--ink)'}, svg);
  }
  const box = c.box || [];
  if (box.length){
    let d = `M${X(t0).toFixed(1)},${Y(0).toFixed(1)}`;
    for (const [t, p] of box) d += `L${X(t).toFixed(1)},${Y(p).toFixed(1)}`;
    d += `L${X(t1).toFixed(1)},${Y(0).toFixed(1)}`;
    el('path', {d, fill:'none', stroke:'var(--fit)', 'stroke-width':1.8}, svg);
  }
  const xd = X(c.t_end) + (narrow ? 8 : 12), y0 = Y(0), yd = Y(-depth);
  el('line', {x1:xd, x2:xd, y1:y0, y2:yd, stroke:'var(--ink)'}, svg);
  for (const y of [y0, yd]) el('line', {x1:xd-4, x2:xd+4, y1:y, y2:y, stroke:'var(--ink)'}, svg);
  T(xd+6, (y0+yd)/2+4, fmt(depth,0)+' ppm', 'start', 'hl halo');
  const yb = yd + (narrow ? 12 : 16);
  el('line', {x1:X(c.t_start), x2:X(c.t_end), y1:yb, y2:yb, stroke:'var(--ink)'}, svg);
  for (const t of [c.t_start, c.t_end]) el('line', {x1:X(t), x2:X(t), y1:yb-4, y2:yb+4, stroke:'var(--ink)'}, svg);
  T((X(c.t_start)+X(c.t_end))/2, yb+(narrow?11:14), fmt(c.duration_hours,2)+' h', 'middle', 'hl halo');
  if (pts.length < 12) T(pl+6, pt+14, `only ${pts.length} binned points in this window`, 'start');
  // reviewer lanes: each label carries the reviewer's kind (SIM or CLAUDE)
  const inWin = n => (marks[n] || []).filter(([a,b]) => b >= t0 && a <= t1);
  names.forEach((n, i) => {
    const y = lanesTop + i*lh, col = colourOf(n), spans = inWin(n);
    el('line', {x1:pl, x2:W-pr, y1:y+lh-1, y2:y+lh-1, class:'grid'}, svg);
    const lbl = decisions[n]?.label || '';
    const strong = lbl === 'potential planet' || lbl === 'potential_planet';
    for (const [a,b] of spans){
      const xa = X(Math.max(a,t0)), xb = X(Math.min(b,t1));
      el('rect', {x:xa, y:y+2, width:Math.max(3, xb-xa), height:lh-5, rx:2, fill:col, opacity: strong ? .85 : .45}, svg);
    }
    const label = `${KIND_TAG(D.reviewers[n])} ${n}`;
    if (narrow){ const t = T(pl+3, y+lh-4, label, 'start', 'lanelbl'); t.setAttribute('fill', col); }
    else { const t = T(pl-10, y+lh/2+4, label, 'end'); t.setAttribute('fill', col); }
    if (!spans.length) T(W-pr-4, y+lh-4, 'no mark in window', 'end');
  });
  // crosshair snapped to a stored bin: pointer (hover or tap) and keyboard
  const tip = document.createElement('div'); tip.className = 'tip'; tip.hidden = true; tip.setAttribute('aria-hidden', 'true');
  if (!narrow) wrap.appendChild(tip);
  const readout = document.createElement('div'); readout.className = 'readout'; readout.tabIndex = 0;
  readout.setAttribute('role', 'status'); readout.setAttribute('aria-live', 'polite'); readout.setAttribute('aria-label', 'Strip readout');
  readout.textContent = narrow ? 'Tap or drag on the strip, or focus it and use the arrow keys, to read a bin.' : 'Hover the strip, or focus it and use ← →, to read a bin.';
  wrap.appendChild(readout);
  const cross = el('g', {visibility:'hidden', 'pointer-events':'none'}, svg);
  const vx = el('line', {y1:pt, y2:H-axisH, stroke:'var(--ink)', 'stroke-width':1, opacity:.7}, cross);
  const hy = el('line', {x1:pl, x2:W-pr, stroke:'var(--ink)', 'stroke-width':1, opacity:.4, 'stroke-dasharray':'2 3'}, cross);
  const dot = el('circle', {r:4.5, fill:'none', stroke:'var(--fit)', 'stroke-width':2}, cross);
  const hit = el('rect', {x:pl, y:pt, width:W-pl-pr, height:H-axisH-pt, fill:'transparent'}, svg);
  let cur = -1;
  const show = (i, viaKey) => {
    if (!pts.length) return;
    cur = Math.max(0, Math.min(pts.length-1, i));
    const q = pts[cur];
    vx.setAttribute('x1', X(q.t)); vx.setAttribute('x2', X(q.t));
    hy.setAttribute('y1', Y(q.p)); hy.setAttribute('y2', Y(q.p));
    dot.setAttribute('cx', X(q.t)); dot.setAttribute('cy', Y(q.p));
    cross.setAttribute('visibility', 'visible');
    const at = names.map(n => [n, (marks[n]||[]).filter(([a,b]) => q.t >= a && q.t <= b)]).filter(([,s]) => s.length);
    const inside = q.t >= c.t_start && q.t <= c.t_end;
    const lines = [`bin ${cur+1} of ${pts.length} · ${fmt(q.t,4)} ${c.time_unit}`,
      `flux ${fmt(q.p,0)}${q.e!==null ? ' ± '+fmt(q.e,0) : ''} ppm${q.e===null ? ' (no stored error)' : ''}`,
      `${inside ? 'inside' : 'outside'} the consensus window`,
      ...(at.length ? at.map(([n,s]) => `${KIND_TAG(D.reviewers[n])} ${n}: ${s.map(([a,b]) => fmt(a,3)+'–'+fmt(b,3)).join(', ')}`) : ['no reviewer span at this time'])];
    if (narrow || viaKey){ readout.textContent = lines.join(' · '); }
    if (narrow) return;
    tip.innerHTML = lines.map((l,k) => k ? esc(l) : `<b>${esc(l)}</b>`).join('<br>');
    tip.hidden = false;
    const r = svg.getBoundingClientRect(), px = X(q.t) * r.width / W, w = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(px + 14, r.width - w - 4)) + 'px';
    tip.style.top = '18px';
  };
  const nearest = t => { let k = 0; pts.forEach((o,j) => { if (Math.abs(o.t-t) < Math.abs(pts[k].t-t)) k = j; }); return k; };
  const move = e => {
    if (!pts.length) return;
    const r = svg.getBoundingClientRect(), sx = (e.clientX - r.left) * W / r.width;
    show(nearest(t0 + (sx - pl)/(W-pl-pr)*(t1-t0)), false);
  };
  hit.addEventListener('pointermove', move);
  hit.addEventListener('pointerdown', move);
  hit.addEventListener('pointerleave', e => { if (e.pointerType !== 'mouse' || narrow) return; cross.setAttribute('visibility','hidden'); tip.hidden = true; });
  wrap.onkeydown = e => {
    if (!pts.length) return;
    const step = e.shiftKey ? 10 : 1;
    let i = null;
    if (e.key === 'ArrowRight') i = (cur < 0 ? nearest(c.t_center) : cur + step);
    else if (e.key === 'ArrowLeft') i = (cur < 0 ? nearest(c.t_center) : cur - step);
    else if (e.key === 'Home') i = 0;
    else if (e.key === 'End') i = pts.length - 1;
    else if (e.key === 'Escape'){ cross.setAttribute('visibility','hidden'); tip.hidden = true; cur = -1; return; }
    if (i === null) return;
    e.preventDefault(); e.stopPropagation();
    show(i, true);
  };
  wrap.onblur = () => { tip.hidden = true; };
  return svg;
}

function context(c, subj){
  const W=900, H=64, pl=72, pr=18, pt=6;
  const svg = el('svg', {viewBox:`0 0 ${W} ${H}`, role:'img', 'aria-label': `Whole subject ${c.subject_id} with this dip and the other dips in it highlighted`});
  const X = t => pl + (t-subj.start)/(subj.end-subj.start)*(W-pl-pr);
  const f = subj.flux.map(v => (v-1)*1e6), lo = Math.min(...f), hi = Math.max(...f), span = (hi-lo)||1;
  const Y = v => pt + (1-(v-lo)/span)*(H-pt-6);
  for (const other of D.candidates.filter(x => x.subject_id === c.subject_id)){
    const cur = other.candidate_id === c.candidate_id, same = other.signal_id === c.signal_id;
    el('rect', {x:X(other.t_start), y:pt, width:Math.max(2,X(other.t_end)-X(other.t_start)), height:H-pt-6, fill: cur ? 'var(--fit)' : same ? 'var(--fit)' : 'var(--muted)', opacity: cur ? .32 : same ? .14 : .14}, svg);
  }
  let d=''; subj.time.forEach((t,i)=>{ d += (i?'L':'M')+X(t).toFixed(1)+','+Y(f[i]).toFixed(1); });
  el('path', {d, fill:'none', stroke:'var(--ink)', 'stroke-width':.9, opacity:.8}, svg);
  tx(svg, pl-8, H-6, 'subject', 'end');
  return svg;
}

function epochList(rows, what){
  if (!rows || !rows.length) return '<p>No stored per-epoch measurement for this candidate.</p>';
  return '<ul class="epochs">' + rows.map(r => r.depth_ppm === null || r.depth_ppm === undefined
    ? `<li>epoch ${r.epoch}${what}: no stored points in window (${r.n_points} points)</li>`
    : `<li>measured: ${fmt(r.depth_ppm,0)} ± ${fmt(r.sigma_ppm,0)} ppm at epoch ${r.epoch}${what}</li>`).join('') + '</ul>';
}

function epochPlot(rows, title, depth, colour){
  const W=300, H=200, pl=44, pr=10, pt=14, pb=26, svg = el('svg', {viewBox:`0 0 ${W} ${H}`, 'aria-hidden':'true'});
  const vals = rows.filter(r => r.depth_ppm !== null && r.depth_ppm !== undefined);
  let lo = 0, hi = depth;
  for (const v of vals){ lo = Math.min(lo, v.depth_ppm - (v.sigma_ppm||0)); hi = Math.max(hi, v.depth_ppm + (v.sigma_ppm||0)); }
  const pad = 0.15*((hi-lo)||1); lo -= pad; hi += pad;
  const Y = p => pt + (hi-p)/(hi-lo)*(H-pt-pb), X = i => pl + (i+.5)*(W-pl-pr)/Math.max(1,rows.length);
  for (const p of niceTicks(lo, hi, 4)){ el('line', {x1:pl,x2:W-pr,y1:Y(p),y2:Y(p),class:'grid'}, svg); tx(svg, pl-6, Y(p)+4, Math.round(p), 'end'); }
  el('line', {x1:pl,x2:W-pr,y1:Y(depth),y2:Y(depth),stroke:'var(--fit)','stroke-dasharray':'3 3'}, svg);
  rows.forEach((r,i) => {
    tx(svg, X(i), H-8, 'E'+r.epoch, 'middle');
    if (r.depth_ppm === null || r.depth_ppm === undefined) return;
    if (r.sigma_ppm !== null) el('line', {x1:X(i),x2:X(i),y1:Y(r.depth_ppm-r.sigma_ppm),y2:Y(r.depth_ppm+r.sigma_ppm),stroke:'var(--ink)'}, svg);
    el('circle', {cx:X(i), cy:Y(r.depth_ppm), r:4.5, fill: colour(r)}, svg);
  });
  tx(svg, pl, pt-4, title);
  return svg;
}

function comparisons(c, subj){
  const out = {fold: null, oddeven: null, secondary: null};
  const P = c.period_days;
  if (!P){
    for (const k of Object.keys(out)) out[k] = Object.assign(document.createElement('div'), {className:'empty', textContent:'no ephemeris in this subject: single event, not measured'});
    return out;
  }
  const W=300, H=200, pl=44, pr=10, pt=14, pb=26, win = c.duration_hours/24 * 3;
  const ref = (c.bls_t0 !== null && c.bls_t0 !== undefined) ? c.bls_t0 : c.t_center;
  {
    const svg = el('svg', {viewBox:`0 0 ${W} ${H}`, role:'img', 'aria-label': `Stored binned points folded on the BLS period ${fmt(P,3)} days`}), ylo=-1.6*c.depth_ppm, yhi=0.6*c.depth_ppm;
    const X = ph => pl + (ph+win)/(2*win)*(W-pl-pr), Y = p => pt + (yhi-p)/(yhi-ylo)*(H-pt-pb);
    for (const q of subj.time.map((t,i)=>[t,(subj.flux[i]-1)*1e6])){ const ph = (((q[0]-ref + P/2) % P) + P) % P - P/2; if (Math.abs(ph) <= win) el('circle', {cx:X(ph), cy:Y(q[1]), r:1.6, fill:'var(--muted)', opacity:.6}, svg); }
    el('line', {x1:pl,x2:W-pr,y1:Y(0),y2:Y(0),class:'grid'}, svg);
    el('line', {x1:pl,x2:W-pr,y1:Y(-c.depth_ppm),y2:Y(-c.depth_ppm),stroke:'var(--fit)','stroke-dasharray':'3 3'}, svg);
    tx(svg, pl, pt-4, `phase fold · P ${fmt(P,3)} d`);
    out.fold = svg;
  }
  const oe = document.createElement('div');
  if (c.epochs && c.epochs.length) oe.appendChild(epochPlot(c.epochs, 'depth per epoch · ink odd, blue even', c.depth_ppm, r => (Math.abs(r.epoch)%2) ? 'var(--ink)' : 'var(--fit)'));
  oe.insertAdjacentHTML('beforeend', epochList(c.epochs, ''));
  out.oddeven = oe;
  const se = document.createElement('div');
  if (c.secondary_epochs && c.secondary_epochs.length) se.appendChild(epochPlot(c.secondary_epochs, 'stored depth at phase 0.5', 0, () => 'var(--muted)'));
  se.insertAdjacentHTML('beforeend', epochList(c.secondary_epochs, ' + 0.5'));
  out.secondary = se;
  return out;
}

// Ledger rows come from Python (docket.vetting_checks, docket.feed_rules): every
// state is spelled out in text, and a missing value reads "not measured", never a pass.
function checkRow(k){
  const value = (k.value === null || k.value === undefined) ? '–' : k.value;
  const why = k.why + (k.note ? ` (${k.note})` : '') + (k.state === 'not_measured' ? ' This check did not run, so it is not a pass.' : '');
  return `<tr tabindex="0" class="chk chk-${k.state}" aria-label="${esc(k.name)}: ${esc(CHK_WORD[k.state])}. value ${esc(value)}. rule ${esc(k.rule)}. ${esc(why)}">`
    + `<td class="c-name"><span class="glyph ${CHK_CLS[k.state]}"><span aria-hidden="true">${CHK_GLYPH[k.state]}</span> <span class="word">${esc(CHK_WORD[k.state])}</span></span> ${esc(k.name)}</td>`
    + `<td class="c-val">${esc(value)}</td><td class="c-rule">${esc(k.rule)}</td><td class="why">${esc(why)}</td></tr>`;
}
function ledger(c){
  return `<tr><th colspan="4" class="grp" scope="colgroup">Vetting checks (light curve only) · outcome: ${esc(OUT_LABEL[c.outcome])}</th></tr>${c.checks.map(checkRow).join('')}`
    + `<tr><th colspan="4" class="grp" scope="colgroup">Feed admission rules (discover.py), not vetting · ${esc(c.feed.result)}</th></tr>${c.feed.rules.map(checkRow).join('')}`;
}

function rationales(c){
  const dec = D.decisions[c.subject_id] || {}, marks = D.marks[c.subject_id] || {};
  return Object.keys(D.reviewers).map(n => {
    const d = dec[n] || {}, k = (marks[n] || []).length;
    const kind = D.reviewers[n];
    const body = isClaude(kind)
      ? esc(d.rationale || 'no rationale recorded')
      : `Simulated detector, not a person: ${k} mark${k===1?'':'s'} in this subject from an SNR threshold and a miss rate set in its config.`;
    const label = (d.label || '').replace(/_/g,' ');
    return `<div tabindex="0"><b style="color:${colourOf(n)}">${esc(n)}</b> <span class="kind kind-${kind === 'simulated' ? 'sim' : 'cl'}">${esc(KIND_LONG(kind))}</span> <span class="hint">${esc(label)} · ${k} mark${k===1?'':'s'}</span><p>${body}</p></div>`;
  }).join('');
}

let redraw = null;
let resizeTimer = 0;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => redraw && redraw(), 120); });

function scopeNote(c){
  const days = D.subject_days ? `${fmt(D.subject_days,0)}-day` : 'per-subject';
  const eph = c.period_days ? `BLS period ${fmt(c.period_days,3)} d, t0 ${fmt(c.bls_t0,4)}, duration ${fmt((c.bls_duration_days||0)*24,1)} h; ${(c.epochs||[]).length} predicted epochs measured in this subject.` : 'No BLS ephemeris covers this dip.';
  return `Scope: the BLS search and its epochs are per ${days} subject, not per TESS sector. ${eph} Depth and duration are the consensus window's measured values. This is a candidate, unconfirmed.`;
}

function crossmatchLine(){
  const x = D.crossmatch || {};
  const when = x.fetched_at ? ` stored ${esc(x.fetched_at.slice(0,10))}` : '';
  const cls = x.status === 'matched' ? 'xm-hit' : x.status === 'no_match' ? 'xm-none' : 'xm-notrun';
  const ran = x.status === 'matched' || x.status === 'no_match';
  const text = ran ? esc(x.line) + '.' : 'Known-planet cross-match not run: the archive was unreachable when this page was built.';
  return `<p class="xm ${cls}"><span class="xm-k">NASA Exoplanet Archive${when}:</span> ${text} <span class="hint">Archive values only; this page claims no detection either way.</span></p>`;
}

function sec(key, title, sub, body){
  const open = !state.collapsed[key];
  return `<section class="sec" id="sec-${key}" aria-labelledby="h-${key}"><header><h3 id="h-${key}"><button class="sectoggle" aria-expanded="${open}" aria-controls="body-${key}" data-sec="${key}"><span class="caret" aria-hidden="true"></span>${title}</button></h3><em>${sub}</em></header><div class="secbody" id="body-${key}"${open ? '' : ' hidden'}>${body}</div></section>`;
}
function toggleSection(key){
  state.collapsed[key] = !state.collapsed[key];
  const b = document.querySelector(`.sectoggle[data-sec="${key}"]`), body = document.getElementById('body-' + key);
  if (b) b.setAttribute('aria-expanded', String(!state.collapsed[key]));
  if (body) body.hidden = !!state.collapsed[key];
  saveView();
  if (!state.collapsed[key] && redraw) redraw(true);
  $('#announce').textContent = `${b ? b.textContent : key} ${state.collapsed[key] ? 'collapsed' : 'expanded'}.`;
}

function renderDossier(){
  redraw = null;
  const top = $('#dtop'), rest = $('#drest');
  const c = byId[state.selected];
  if (!c){ top.innerHTML = '<div class="empty">Choose a signal from the list. Use j and k to move.</div>'; rest.innerHTML = ''; return; }
  const s = sigById[c.signal_id], subj = D.subjects[c.subject_id], marks = D.marks[c.subject_id] || {}, dec = D.decisions[c.subject_id] || {};
  const reasons = [...c.flags.map(f => `flag ${f}`), ...c.checks.filter(k => k.state === 'not_measured').map(k => `${k.name} not measured`)];
  const feedFail = c.feed.rules.filter(r => r.state !== 'pass').map(r => r.name);
  const e = epochOf(c), nAll = Object.keys(D.reviewers).length;
  top.innerHTML = `
    <section class="outcome ${OUT_CLS[c.outcome]}" tabindex="0" aria-label="Vetting outcome for ${esc(c.candidate_id)}: ${esc(OUT_LABEL[c.outcome])}">
      <div class="out-main"><span class="glyph" aria-hidden="true">${OUT_GLYPH[c.outcome]}</span> ${esc(OUT_LABEL[c.outcome])}</div>
      <div class="out-why">${reasons.length ? 'because: ' + esc(reasons.join(' · ')) : 'every vetting check measured and passing'}</div>
      <div class="out-feed"><span class="xm-k">Feed admission rule (discover.py), not vetting:</span> ${esc(c.feed.result)}${feedFail.length ? ' · ' + esc(feedFail.join(', ')) : ''}</div>
      ${crossmatchLine()}
    </section>
    <div class="head">
      <div><div class="hint">candidate, unconfirmed · ${esc(c.target)} · ${esc(c.mission)} · subject ${esc(c.subject_id)}</div>
      <h2>Signal ${esc(sigLabel(s))} <span class="dipid">· dip ${e !== null ? 'E'+e+' · ' : ''}${esc(c.candidate_id)}</span></h2></div>
      <div class="sigout">signal: ${outBadge(s.outcome)}</div>
    </div>
    <div class="facts">
      <div><span>mid-time</span>${fmt(c.t_center,3)} ${esc(c.time_unit)}</div>
      <div><span>duration</span>${fmt(c.duration_hours,2)} h</div>
      <div><span>depth</span>${fmt(c.depth_ppm,0)} ppm</div>
      <div><span>SNR</span>${fmt(c.snr,1)}</div>
      <div><span>panel</span>${fmt(c.score,2)} · marked by ${c.n_reviewers} of ${nAll} reviewers: ${esc(reviewerSummary(c.reviewers))} (panel: ${esc(reviewerSummary(Object.keys(D.reviewers)))})</div>
      <div><span>BLS period</span>${c.period_days ? fmt(c.period_days,3)+' d (this subject)' : 'none'}</div>
      <div><span>BLS t0</span>${(c.bls_t0 !== null && c.bls_t0 !== undefined) ? fmt(c.bls_t0,4) : '–'}</div>
    </div>
    ${sec('strip', 'Transit strip', 'stored measurements only · nothing is fitted · <kbd>s</kbd> collapses', `<div class="hero-wrap strip" id="strip" tabindex="0" role="group" aria-label="Transit strip for ${esc(c.candidate_id)}. Use left and right arrow keys to step through the stored bins, Shift for ten, Home and End for the ends."></div>
      <div class="legend"><span><i class="k-pt"></i>binned flux ±1σ (stored)</span><span><i class="k-box"></i>box model at measured depth and duration</span><span><i class="k-band"></i>consensus window</span><span><i class="k-lane"></i>reviewer marks, one lane each · SIM = simulated detector (not a person), CLAUDE = Claude model</span></div>
      <p class="scope">${scopeNote(c)}</p>`)}`;
  const dipBtns = s.dips.map(id => { const d = byId[id], ep = epochOf(d); return `<button class="dipbtn${id===c.candidate_id?' cur':''}" data-dip="${esc(id)}" aria-current="${id===c.candidate_id}">${ep !== null ? 'E'+ep+' · ' : ''}${fmt(d.t_center,3)} · ${fmt(d.depth_ppm,0)} ppm · <span class="${OUT_CLS[d.outcome]}"><span aria-hidden="true">${OUT_GLYPH[d.outcome]}</span> ${esc(d.outcome)}</span></button>`; }).join('');
  rest.innerHTML = `
    ${sec('signal', `Signal · ${s.dips.length} dip${s.dips.length===1?'':'s'}`, s.period_days ? `one BLS period in subject ${esc(s.subject_id)}; each dip vetted on its own` : 'no BLS period: this dip is its own signal', `<div class="dips">${dipBtns}</div>`)}
    ${sec('ctx', 'Subject in context', 'blue: this dip · pale blue: same signal · grey: other dips here', '<div class="hero-wrap" id="ctx"></div>')}
    ${sec('cmp', 'Comparisons', 'phase fold · stored per-epoch depths · secondary window', '<div class="compare" id="cmp"></div>')}
    ${sec('ledger', 'Verdict ledger', 'every check, measured value, rule', `<div class="scroll"><table class="ledger"><tbody>${ledger(c)}</tbody></table></div>`)}
    ${sec('rev', 'Reviewers', `${nAll} reviewers: ${esc(reviewerSummary(Object.keys(D.reviewers)))}`, `<div class="rat">${rationales(c)}</div>`)}
    <div class="prov">run ${esc(D.provenance.run_time)} · config ${esc(D.provenance.config_sha256.slice(0,16))} · pipeline ${esc(D.provenance.exoplan_version)} · ${esc(D.provenance.claude_prompt_version || '')}<br>candidate ${esc(c.candidate_id)} · signal ${esc(s.signal_id)} · subject ${esc(c.subject_id)}<br>cross-match: ${esc((D.crossmatch||{}).source || '')} · status ${esc((D.crossmatch||{}).status || 'not_run')}</div>`;
  document.querySelectorAll('.sectoggle').forEach(b => b.addEventListener('click', () => toggleSection(b.dataset.sec)));
  rest.querySelectorAll('.dipbtn').forEach(b => b.addEventListener('click', () => select(b.dataset.dip)));
  if (subj){
    const sw = $('#strip');
    let lastW = -1;
    redraw = force => { if (sw.isConnected && !$('#body-strip').hidden && (force || sw.clientWidth !== lastW)){ lastW = sw.clientWidth; strip(c, subj, marks, dec, sw); } };
    redraw(true);
    $('#ctx').appendChild(context(c, subj));
    const cmp = comparisons(c, subj);
    for (const k of ['fold','oddeven','secondary']){ const wrap = document.createElement('div'); wrap.appendChild(cmp[k]); if (k==='fold') wrap.insertAdjacentHTML('beforeend','<p>Every transit folded on the period. A planet repeats at one phase.</p>'); if (k==='oddeven') wrap.insertAdjacentHTML('beforeend','<p>Alternating depths point to a binary at twice the period. Each value is stored by the pipeline at a BLS-predicted epoch.</p>'); if (k==='secondary') wrap.insertAdjacentHTML('beforeend','<p>A dip here would point to an eclipsing binary.</p>'); $('#cmp').appendChild(wrap); }
  } else {
    $('#strip').outerHTML = '<div class="empty">No plot data stored for this subject.</div>';
  }
}

// On a phone the outcome and the strip come first; the list follows as a collapsible section.
const listPanel = $('#listpanel');
function placeList(){
  const target = narrowMQ.matches ? $('#listslot') : $('#listhome');
  if (listPanel.parentElement !== target) target.appendChild(listPanel);
  if (redraw) redraw();
}
if (narrowMQ.addEventListener) narrowMQ.addEventListener('change', placeList);

$('#rows').addEventListener('keydown', e => {
  if (e.key === 'ArrowDown') { moveSelection(1); e.preventDefault(); e.stopPropagation(); }
  else if (e.key === 'ArrowUp') { moveSelection(-1); e.preventDefault(); e.stopPropagation(); }
  else if (e.key === 'Home') { const ids = visibleDips(); if (ids.length){ select(ids[0]); e.preventDefault(); } }
  else if (e.key === 'End') { const ids = visibleDips(); if (ids.length){ select(ids[ids.length-1]); e.preventDefault(); } }
});
$('#rows').addEventListener('focus', () => { if (!state.selected || !document.getElementById(optId(state.selected))){ const ids = visibleDips(); if (ids.length) select(ids[0]); } });

document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'j') moveSelection(1);
  else if (e.key === 'k') moveSelection(-1);
  else if (e.key === '1') setFilter('passed');
  else if (e.key === '2') setFilter('flagged');
  else if (e.key === '3') setFilter('rejected');
  else if (e.key === '0') setFilter('all');
  else if (e.key === 's' || e.key === 'S') toggleSection('strip');
});

renderRunHeader(); renderList();
const fromHash = decodeURIComponent(location.hash.slice(1));
const first = byId[fromHash] ? fromHash : (state.selected || visibleDips()[0] || (D.candidates[0] || {}).candidate_id);
placeList();
if (first) select(first, false); else renderDossier();
"""


def box_model(row: dict) -> list[list[float]]:
    """Box model at measured depth and duration, as (time, ppm) vertices.

    Zero outside the consensus window, minus the measured depth inside it.
    Nothing is fitted: the edges are the stored ``t_start`` and ``t_end`` and the
    level is the stored ``depth_ppm``.
    """
    t_start, t_end, depth = float(row["t_start"]), float(row["t_end"]), float(row["depth_ppm"])
    return [[t_start, 0.0], [t_start, -depth], [t_end, -depth], [t_end, 0.0]]


# ---------- checks and the three-state outcome ----------

PASS, FAIL, FLAG, NOT_MEASURED = "pass", "fail", "flag", "not_measured"
PASSED, FLAGGED, REJECTED = "passed", "flagged", "rejected"
OUTCOME_LABEL = {PASSED: "passed vetting", FLAGGED: "flagged for review", REJECTED: "rejected by vetting"}
_SEVERITY = {PASSED: 0, FLAGGED: 1, REJECTED: 2}


def _num(value):
    """A stored number, or None when it is missing or not finite."""
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _check(key, name, value, rule, state, why, note=""):
    return {"key": key, "name": name, "value": value, "rule": rule, "state": state, "why": why, "note": note}


def vetting_checks(c: dict) -> list[dict]:
    """Every vetting check for one dip, from stored metrics and flags only.

    The state of a measured check comes from the flags the vetting code set, so
    the page cannot disagree with the code. A check whose input is missing is
    ``not_measured``: the check never ran, which is not a pass.
    """
    m = c.get("metrics") or {}
    flags = set(c.get("flags") or [])
    out = []

    def flagged(flag, measured, disqualifying):
        if not measured:
            return NOT_MEASURED
        if flag in flags:
            return FAIL if disqualifying else FLAG
        return PASS

    snr = _num(m.get("snr"))
    out.append(_check("snr", "SNR", None if snr is None else f"{snr:.1f}", "≥ 7",
                      flagged("low_snr", snr is not None, True), "Dip is strong enough to trust."))
    dur = _num(m.get("duration_minutes"))
    out.append(_check("duration", "duration", None if dur is None else f"{dur:.0f} min", "≥ 15 min",
                      flagged("too_short", dur is not None, True), "Too short to be a transit otherwise."))
    n_in = _num(m.get("n_in_transit"))
    out.append(_check("points", "points in transit", None if n_in is None else f"{n_in:.0f}", "≥ 2",
                      flagged("insufficient_points", n_in is not None, True), "Enough samples inside the dip to measure it."))
    # The edge test runs only once a dip has at least two points (vet.py returns early otherwise).
    edge_measured = _num(m.get("depth")) is not None
    out.append(_check("edge", "edge", None if not edge_measured else ("within 0.1 d of edge" if "edge_event" in flags else "interior"),
                      "not at edge", flagged("edge_event", edge_measured, False), "A partly observed dip is flagged, not rejected."))
    # Odd/even is compared only when both parities show a dip at ≥ 5σ (vet.py); otherwise it never ran.
    od, ev, oe, ee = (_num(m.get(k)) for k in ("odd_depth", "even_depth", "odd_err", "even_err"))
    oe_ran = None not in (od, ev, oe, ee) and oe > 0 and ee > 0 and min(od / oe, ev / ee) >= 5.0
    oe_value = None if None in (od, ev) else f"{od * 1e6:.0f} / {ev * 1e6:.0f} ppm"
    oe_note = "" if oe_ran or oe_value is None else "one parity has no dip at ≥ 5σ, so the comparison did not run"
    out.append(_check("oddeven", "odd / even", oe_value, "agree within 3σ",
                      flagged("odd_even_mismatch", oe_ran, True), "Alternating depths would mean a binary at twice the period.", oe_note))
    sd, se = _num(m.get("secondary_depth")), _num(m.get("secondary_err"))
    sec_ran = sd is not None and se is not None and se > 0
    out.append(_check("secondary", "secondary eclipse", None if sd is None else f"{sd * 1e6:.0f} ppm", "not significant",
                      flagged("secondary_eclipse", sec_ran, True), "A dip at phase 0.5 would mean an eclipsing binary."))
    # Ephemeris: measured when the dip sits on a BLS ephemeris, or the code flagged it off one.
    eph_measured = _num(c.get("period_days")) is not None or "off_ephemeris" in flags
    out.append(_check("ephemeris", "ephemeris", None if not eph_measured else ("off" if "off_ephemeris" in flags else "on"),
                      "on ephemeris", flagged("off_ephemeris", eph_measured, False), "Not explained by the strong periodic signal of its star."))
    return out


def outcome(checks: list[dict], flags=(), passed: bool = True) -> str:
    """One three-state outcome, decided in order.

    1. rejected by vetting: any disqualifying flag (or a failed check);
    2. flagged for review: any non-disqualifying flag, or any check not measured;
    3. passed vetting: every vetting check measured and passing.
    An unmeasured check can never produce a pass.
    """
    flags = {f for f in flags if f}
    if (flags & DISQUALIFYING) or not passed or any(k["state"] == FAIL for k in checks):
        return REJECTED
    if flags or any(k["state"] in (FLAG, NOT_MEASURED) for k in checks):
        return FLAGGED
    return PASSED


def feed_rules(c: dict) -> dict:
    """The feed admission rules of discover.py, kept apart from vetting."""
    flags = set(c.get("flags") or [])
    depth = _num(c.get("depth_ppm"))
    period = _num(c.get("period_days"))
    n_tr = int(c.get("n_transits") or 0)
    rules = [
        _check("vetting", "no disqualifying flag, on ephemeris", "yes" if c.get("passed") and "off_ephemeris" not in flags else "no",
               "passed and not off_ephemeris", PASS if c.get("passed") and "off_ephemeris" not in flags else FAIL,
               "The feed takes only dips the code passed and that sit on their star's periodic signal."),
        _check("depth_cap", "depth cap", None if depth is None else f"{depth:.0f} ppm", f"≤ {MAX_FEED_DEPTH_PPM:,.0f} ppm",
               NOT_MEASURED if depth is None else (PASS if depth <= MAX_FEED_DEPTH_PPM else FAIL),
               "Deeper dips are almost always binaries; kept out of the feed."),
        _check("periodic", "periodic support", f"{n_tr} transits" if period is not None else "no BLS period",
               f"≥ {MIN_FEED_TRANSITS} transits", PASS if period is not None and n_tr >= MIN_FEED_TRANSITS else FAIL,
               "A repeated dip is needed for the feed."),
    ]
    states = {r["state"] for r in rules}
    admitted = "admitted" if states == {PASS} else ("not decided" if NOT_MEASURED in states and FAIL not in states else "not admitted")
    return {"rules": rules, "result": admitted}


def group_signals(candidates: list[dict]) -> list[dict]:
    """Group dips into signals: one per (subject, BLS period), epochs as children.

    A dip with no BLS period is its own signal. Signal outcome is the most
    severe outcome among its dips, so a signal never reads better than a dip in it.
    """
    groups: dict = {}
    for c in candidates:
        period = _num(c.get("period_days"))
        key = (c["subject_id"], round(period, 9)) if period is not None else (c["subject_id"], "dip", c["candidate_id"])
        groups.setdefault(key, []).append(c)
    signals = []
    for key, dips in groups.items():
        dips = sorted(dips, key=lambda d: d["t_center"])
        first = dips[0]
        period = _num(first.get("period_days"))
        sid = f"{first['subject_id']}-P{period:.4f}" if period is not None else f"{first['candidate_id']}-single"
        outcomes = [d.get("outcome") for d in dips if d.get("outcome")]
        sig_outcome = max(outcomes, key=_SEVERITY.__getitem__) if outcomes else None
        signals.append({
            "signal_id": sid,
            "subject_id": first["subject_id"],
            "period_days": period,
            "bls_t0": first.get("bls_t0"),
            "n_transits": first.get("n_transits"),
            "dips": [d["candidate_id"] for d in dips],
            "outcome": sig_outcome,
        })
    first_t = {c["candidate_id"]: c["t_center"] for c in candidates}
    signals.sort(key=lambda s: (s["period_days"] is None, first_t[s["dips"][0]]))
    return signals


# ---------- known-planet cross-match (NASA Exoplanet Archive) ----------

CROSSMATCH_FILE = "crossmatch.json"


def query_archive(target: str, star: str | None = None) -> list[dict]:
    """Published planets for this star from the NASA Exoplanet Archive 'ps' table.

    Matches tic_id for a TIC target, and hostname or pl_name on the star name
    when one is known. Raises on any network or service error.
    """
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive, conf

    conf.timeout = 60
    clauses = []
    if target.upper().startswith("TIC"):
        clauses.append("tic_id = '{}'".format("TIC " + target[3:].strip().replace("'", "")))
    if star:
        name = star.replace("'", "''")
        clauses.append(f"hostname = '{name}'")
        clauses.append(f"pl_name like '{name} %'")
    if not clauses:
        return []
    where = "default_flag = 1 and (" + " or ".join(clauses) + ")"
    table = NasaExoplanetArchive.query_criteria(table="ps", select="pl_name,hostname,pl_orbper,tic_id", where=where)
    planets = []
    for row in table:
        per = row["pl_orbper"]
        per = getattr(per, "value", per)
        planets.append({
            "pl_name": str(row["pl_name"]),
            "hostname": str(row["hostname"]),
            "pl_orbper": _num(per),
            "tic_id": str(row["tic_id"]),
        })
    planets.sort(key=lambda p: (p["pl_orbper"] is None, p["pl_orbper"] or 0))
    return planets


def crossmatch(run_dir: Path, targets: list[str], star: str | None = None, *, refresh: bool = False) -> dict:
    """Fetch (or reuse) the stored cross-match for the run's targets.

    The result is stored in the run directory, so the page rebuilds offline.
    When the archive cannot be reached the stored status is ``not_run``,
    which the page states; it is never a silent blank.
    """
    path = Path(run_dir) / CROSSMATCH_FILE
    if path.exists() and not refresh:
        try:
            stored = json.loads(path.read_text())
            if stored.get("status") in ("matched", "no_match") and stored.get("targets") == targets and stored.get("star") == star:
                return stored
        except (OSError, ValueError):
            pass
    result = {"source": "NASA Exoplanet Archive, table ps (default_flag = 1)", "targets": targets, "star": star,
              "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "planets": []}
    try:
        for target in targets:
            result["planets"].extend(query_archive(target, star))
        result["status"] = "matched" if result["planets"] else "no_match"
    except Exception as exc:  # network, DNS, service or missing package: the cross-match did not run
        result["status"] = "not_run"
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    path.write_text(json.dumps(result, indent=2))
    return result


def crossmatch_line(result: dict) -> str:
    status = result.get("status")
    if status == "matched":
        planets = result.get("planets") or []
        parts = [f"{p['pl_name']} (P {p['pl_orbper']:.3f} d)" if p.get("pl_orbper") is not None else p["pl_name"] for p in planets]
        noun = "planet" if len(parts) == 1 else "planets"
        return f"Host of published {noun} {', '.join(parts)}"
    if status == "no_match":
        return "No published planet matched in the archive"
    return "Known-planet cross-match not run (archive unreachable at docket build time)"


def build_docket(run_dir: str | Path, out_dir: str | Path, *, title: str, star: str | None = None,
                 refresh_crossmatch: bool = False) -> Path:
    run_dir = Path(run_dir)
    run = _load_run(run_dir)
    rows = json.loads((run_dir / "candidates.json").read_text())
    by_id = {r["candidate_id"]: r for r in rows}
    for c in run["candidates"]:
        row = by_id[c["candidate_id"]]
        c["metrics"] = row.get("metrics", {})
        c["target"] = row.get("target", "")
        c["mission"] = row.get("mission", "")
        c["flags"] = [f for f in c["flags"] if f]
        c["bls_t0"] = row.get("bls_t0")
        c["bls_duration_days"] = row.get("bls_duration_days")
        c["epochs"] = row.get("epochs") or []
        c["secondary_epochs"] = row.get("secondary_epochs") or []
        c["box"] = box_model(c)
        c["checks"] = vetting_checks(c)
        c["outcome"] = outcome(c["checks"], c["flags"], c["passed"])
        c["feed"] = feed_rules(c)
    signals = group_signals(run["candidates"])
    for s in signals:
        for cid in s["dips"]:
            next(c for c in run["candidates"] if c["candidate_id"] == cid)["signal_id"] = s["signal_id"]
    kinds = list(run["reviewers"].values())
    n_sim = sum(1 for k in kinds if k == "simulated")
    n_claude = sum(1 for k in kinds if k in ("claude", "claude_code"))
    targets = sorted({c["target"] for c in run["candidates"] if c["target"]})
    xm = crossmatch(run_dir, targets, star, refresh=refresh_crossmatch)
    xm["line"] = crossmatch_line(xm)
    data = {
        "title": title,
        "candidates": run["candidates"],
        "signals": signals,
        "subjects": run["subjects"],
        "marks": run["marks"],
        "decisions": run["reviewerDecisions"],
        "reviewers": run["reviewers"],
        "subject_days": run["manifest"].get("subject_days"),
        "counts": {
            "signals": len(signals),
            "dips": len(run["candidates"]),
            **{o: sum(1 for s in signals if s["outcome"] == o) for o in (PASSED, FLAGGED, REJECTED)},
            "reviewers": len(kinds), "simulated": n_sim, "claude": n_claude, "other": len(kinds) - n_sim - n_claude,
        },
        "outcome_label": OUTCOME_LABEL,
        "crossmatch": xm,
        "provenance": {
            "run_time": run["manifest"]["created_at"],
            "config_sha256": run["manifest"]["config_sha256"],
            "exoplan_version": run["manifest"]["exoplan_version"],
            "claude_prompt_version": run["manifest"].get("claude_prompt_version", ""),
        },
    }
    payload = json.dumps(data).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>{DOCKET_CSS}</style></head>
<body>
<div class="app">
  <aside class="list" id="listhome">
    <section class="listpanel" id="listpanel" aria-label="Signals and dips">
      <div class="run" id="run"></div>
      <div id="listbody">
        <div id="rows" role="listbox" tabindex="0" aria-label="Signals and their dips"></div>
      </div>
    </section>
  </aside>
  <main class="dossier" id="dossier"><div id="dtop"></div><div id="listslot"></div><div id="drest"></div></main>
</div>
<div id="announce" class="sr" aria-live="polite" aria-atomic="true"></div>
<script id="data" type="application/json">{payload}</script>
<script>{DOCKET_JS}</script>
</body></html>
"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(page)
    return path

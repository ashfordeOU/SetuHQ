"""The Docket: a case file for each signal and its dips.

The unit of analysis is the signal: one per (subject, BLS period), with the
dips at its epochs as children; a dip with no BLS period is its own signal.
Per-subject results of the same target whose periods agree within 1 percent
and whose predicted epochs line up are merged into one signal, each subject's
BLS result kept under it as provenance.
The list on the left groups dips under their signal and the run header counts
both ("N signals · M dips").

Each dip gets one three-state vetting outcome, computed here in Python
(``outcome``): rejected by vetting (any disqualifying flag), flagged for review
(a non-disqualifying flag, or any check not measured), passed vetting (every
check measured and passing). A check whose value is missing is "not measured",
never a pass. Feed admission rules from discover.py are shown apart from vetting.

The dossier leads with that outcome, the feed-rule result and a known-planet
line from the NASA Exoplanet Archive (fetched at build time and stored in the
run directory as crossmatch.json, or stored as "not run" when offline), with a
per-dip comparison (ΔP and nearest archive epoch offset) stored there too. Then the
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
.legend .k-hatch{width:14px;height:8px;border-radius:2px;border:1px solid var(--muted);background:repeating-linear-gradient(45deg,var(--muted) 0 2px,transparent 2px 4px)}
.panelfact{flex-basis:100%;min-width:0;overflow-wrap:anywhere}
.countrule{margin:4px 0 0;font:12px/1.5 "Inter Tight",sans-serif;color:var(--muted)}
.countlist{color:var(--muted)}
.scope{margin:0;font:12px/1.5 "Inter Tight",sans-serif;color:var(--muted)}
.filternote{margin:0;border:1px dashed var(--flag);border-radius:6px;padding:8px 12px;font:13px/1.5 "Inter Tight",sans-serif}
.filternote[hidden]{display:none}
.xm-cmp{display:block;margin-top:2px}
.ledger thead th{text-align:left;font:600 11px "JetBrains Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding:6px 8px;border-bottom:1px solid var(--ink)}
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
}
@media (max-width:640px){
  .ledger,.ledger thead,.ledger tbody{display:block}
  .ledger thead th{padding:4px 6px}
  .ledger thead th:last-child{grid-column:1/-1}
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

// A merged signal names every subject's BLS period: they are separate per-subject results, not one fit.
function sigLabel(s){
  if (!s.period_days) return 'single dip, no BLS period';
  const ps = (s.bls || []).map(b => b.period_days).filter(p => p);
  return ps.length > 1 ? `P ${ps.map(p => fmt(p,3)).join(' / ')} d` : `P ${fmt(s.period_days,3)} d`;
}
function sigSubjects(s){ const ids = s.subject_ids || [s.subject_id]; return `${ids.length > 1 ? 'subjects' : 'subject'} ${ids.join(', ')}`; }
// Epoch on the signal's reference ephemeris (Python: docket.signal_epoch), one count across subjects.
function epochOf(c){ return (c.signal_epoch === null || c.signal_epoch === undefined) ? null : c.signal_epoch; }
function visibleSignals(){ return D.signals.filter(s => state.filter === 'all' || s.outcome === state.filter); }
function visibleDips(){ return visibleSignals().flatMap(s => s.dips); }
function reviewerSummary(names){
  const kinds = names.map(n => D.reviewers[n]);
  const sim = kinds.filter(k => k === 'simulated').length, cl = kinds.filter(isClaude).length, other = kinds.length - sim - cl;
  return [sim ? `${sim} simulated` : '', cl ? `${cl} Claude` : '', other ? `${other} other` : ''].filter(Boolean).join(', ') || 'none';
}

function renderRunHeader(){
  const c = D.counts, box = $('#run');
  const n = k => `${k} signal${k===1?'':'s'}`;
  const chips = [['all', `all ${n(c.signals)}`], ['passed', `${n(c.passed)} passed`], ['flagged', `${n(c.flagged)} flagged`], ['rejected', `${n(c.rejected)} rejected`]];
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
function setFilter(f){
  state.filter = f; renderRunHeader(); renderList(); saveView(); updateFilterNote();
  const n = visibleSignals().length;
  $('#filterlive').textContent = `Showing ${n} signal${n===1?'':'s'}, filter: ${f}.` + (hiddenBySelection() ? ` The selected dip ${state.selected} is hidden by this filter; the dossier stays on it.` : '');
  const b = document.querySelector(`.chip[data-f="${f}"]`); if (b && document.activeElement?.classList?.contains('chip')) b.focus();
}
function hiddenBySelection(){ return !!(state.selected && !visibleDips().includes(state.selected)); }
// When the filter hides the selected dip, the dossier stays on that dip and says so.
function updateFilterNote(){
  const note = $('#filternote'); if (!note) return;
  if (hiddenBySelection()){ note.hidden = false; note.textContent = `The filter "${state.filter}" hides this dip's signal in the list; the dossier stays on the selected dip. Press 0 to show all signals.`; }
  else { note.hidden = true; note.textContent = ''; }
}

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
    head.innerHTML = `<div><div class="mono signame">${esc(sigLabel(s))}</div><small>${esc(sigSubjects(s))} · ${s.dips.length} dip${s.dips.length===1?'':'s'}${s.period_days ? ` · ${(s.bls||[]).map(b => b.n_transits).join(' + ')} BLS transits` : ''}</small></div>${outBadge(s.outcome)}`;
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
  // Hatched fill for a span that did not count toward this dip (stored in c.mark_audit).
  const defs = el('defs', {}, svg);
  names.forEach((n, i) => {
    const pat = el('pattern', {id:`hatch-${i}`, width:5, height:5, patternUnits:'userSpaceOnUse', patternTransform:'rotate(45)'}, defs);
    el('rect', {width:5, height:5, fill:'var(--panel)'}, pat);
    el('line', {x1:0, y1:0, x2:0, y2:5, stroke:colourOf(n), 'stroke-width':2.4}, pat);
  });
  const countedSpan = (n, a, b) => (c.mark_audit || []).some(r => r.reviewer_id === n && (r.marks || []).some(m => m.counted && Math.abs(m.t_start - a) < 1e-9 && Math.abs(m.t_end - b) < 1e-9));
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
      const xa = X(Math.max(a,t0)), xb = X(Math.min(b,t1)), ok = countedSpan(n, a, b);
      el('rect', {x:xa, y:y+2, width:Math.max(3, xb-xa), height:lh-5, rx:2, fill: ok ? col : `url(#hatch-${i})`, stroke: ok ? 'none' : col, 'stroke-width':1, opacity: ok ? (strong ? .85 : .45) : .9, 'data-counted': String(ok)}, svg);
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
      ...(at.length ? at.map(([n,s]) => `${KIND_TAG(D.reviewers[n])} ${n}: ${s.map(([a,b]) => fmt(a,3)+'–'+fmt(b,3) + (countedSpan(n,a,b) ? ' (counted)' : ' (not counted)')).join(', ')}`) : ['no reviewer span at this time'])];
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

// "signal epoch E3 (S2 epoch 0, even)": the signal's count, then the subject's own number and parity.
function epochName(r, what){
  if (r.signal_epoch === null || r.signal_epoch === undefined) return `epoch ${r.epoch}${what}`;
  return `signal epoch E${r.signal_epoch}${what} (${esc(r.subject_label || 'subject')} epoch ${r.epoch}${what}, ${r.subject_parity} in its subject)`;
}
function epochList(rows, what){
  if (!rows || !rows.length) return '<p>No stored per-epoch measurement for this candidate.</p>';
  return '<ul class="epochs">' + rows.map(r => r.depth_ppm === null || r.depth_ppm === undefined
    ? `<li>${epochName(r, what)}: no stored points in window (${r.n_points} points)</li>`
    : `<li>measured: ${fmt(r.depth_ppm,0)} ± ${fmt(r.sigma_ppm,0)} ppm at ${epochName(r, what)}</li>`).join('') + '</ul>';
}

// Axis: signal epoch E (one count across subjects) and, under it, the subject's own label and parity.
function epochPlot(rows, title, depth, colour){
  const W=300, H=212, pl=44, pr=10, pt=14, pb=38, svg = el('svg', {viewBox:`0 0 ${W} ${H}`, 'aria-hidden':'true'});
  const vals = rows.filter(r => r.depth_ppm !== null && r.depth_ppm !== undefined);
  let lo = 0, hi = depth;
  for (const v of vals){ lo = Math.min(lo, v.depth_ppm - (v.sigma_ppm||0)); hi = Math.max(hi, v.depth_ppm + (v.sigma_ppm||0)); }
  const pad = 0.15*((hi-lo)||1); lo -= pad; hi += pad;
  const Y = p => pt + (hi-p)/(hi-lo)*(H-pt-pb), X = i => pl + (i+.5)*(W-pl-pr)/Math.max(1,rows.length);
  for (const p of niceTicks(lo, hi, 4)){ el('line', {x1:pl,x2:W-pr,y1:Y(p),y2:Y(p),class:'grid'}, svg); tx(svg, pl-6, Y(p)+4, Math.round(p), 'end'); }
  el('line', {x1:pl,x2:W-pr,y1:Y(depth),y2:Y(depth),stroke:'var(--fit)','stroke-dasharray':'3 3'}, svg);
  rows.forEach((r,i) => {
    const hasSig = r.signal_epoch !== null && r.signal_epoch !== undefined;
    tx(svg, X(i), H-22, 'E'+(hasSig ? r.signal_epoch : r.epoch), 'middle', 'hl');
    if (hasSig){ const t = tx(svg, X(i), H-8, `${r.subject_label || ''} ${r.subject_parity}`.trim(), 'middle'); t.style.fontSize = '9px'; }
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
  // A merged signal plots every subject's stored epochs on one axis; colour is the subject's own parity.
  const s = sigById[c.signal_id], merged = s && (s.bls||[]).length > 1, rowsOE = merged && (s.epoch_rows||[]).length ? s.epoch_rows : c.epochs;
  if (rowsOE && rowsOE.length) oe.appendChild(epochPlot(rowsOE, 'depth per epoch · ink odd, blue even', c.depth_ppm, r => (Math.abs(r.epoch)%2) ? 'var(--ink)' : 'var(--fit)'));
  oe.insertAdjacentHTML('beforeend', epochList(rowsOE, ''));
  out.oddeven = oe;
  const se = document.createElement('div');
  if (c.secondary_epochs && c.secondary_epochs.length) se.appendChild(epochPlot(c.secondary_epochs, 'stored depth at phase 0.5 · E + 0.5', 0, () => 'var(--muted)'));
  se.insertAdjacentHTML('beforeend', epochList(c.secondary_epochs, ' + 0.5'));
  out.secondary = se;
  return out;
}

// Ledger rows come from Python (docket.vetting_checks, docket.feed_rules): every
// state is spelled out in text, and a missing value reads "not measured", never a pass.
function checkRow(k){
  const value = (k.value === null || k.value === undefined) ? '–' : k.value;
  const why = k.why + (k.note ? ` (${k.note})` : '') + (k.state === 'not_measured' ? ' This check did not run, so it is not a pass.' : '');
  return `<tr role="row" tabindex="0" class="chk chk-${k.state}" aria-label="${esc(k.name)}: ${esc(CHK_WORD[k.state])}. value ${esc(value)}. rule ${esc(k.rule)}. ${esc(why)}">`
    + `<td role="cell" class="c-name"><span class="glyph ${CHK_CLS[k.state]}"><span aria-hidden="true">${CHK_GLYPH[k.state]}</span> <span class="word">${esc(CHK_WORD[k.state])}</span></span> ${esc(k.name)}</td>`
    + `<td role="cell" class="c-val">${esc(value)}</td><td role="cell" class="c-rule">${esc(k.rule)}</td><td role="cell" class="why">${esc(why)}</td></tr>`;
}
function ledger(c){
  return `<tr role="row"><th role="cell" colspan="4" class="grp" scope="colgroup">Vetting checks (light curve only) · outcome: ${esc(OUT_LABEL[c.outcome])}</th></tr>${c.checks.map(checkRow).join('')}`
    + `<tr role="row"><th role="cell" colspan="4" class="grp" scope="colgroup">Feed admission rules (discover.py), not vetting · ${esc(c.feed.result)}</th></tr>${c.feed.rules.map(checkRow).join('')}`;
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

// Provenance of a merged signal: each subject's own BLS result, as stored.
function blsTable(s){
  if (!s.bls || !s.bls.length) return '';
  return `<ul class="epochs" aria-label="Per-subject BLS results">${s.bls.map(b => `<li>subject ${esc(b.subject_id)}: BLS P ${fmt(b.period_days,4)} d, t0 ${fmt(b.bls_t0,4)}, duration ${fmt((b.bls_duration_days||0)*24,1)} h, ${b.n_transits} transits, ${b.dips.length} dip${b.dips.length===1?'':'s'}${b.reference ? ' · reference for epoch numbers' : ''}</li>`).join('')}</ul>`
    + (s.bls.length > 1 ? `<p class="scope">Merged because these per-subject results are on the same target, their periods agree within 1 percent, and each one's predicted epochs fall within one transit duration of the other's. Each BLS result is kept as is; no combined period is fitted.</p>` : '');
}

// Why a mark did or did not count, from stored values only (c.count_rule, c.mark_audit).
function notCountedLegend(c){
  const g = (c.count_rule || {}).gap_days;
  return g === undefined ? 'not counted for this dip' : `not counted: centre more than ${g} d from every counted mark (clustering gap)`;
}
function countNote(c){
  const rule = c.count_rule || {}, audit = c.mark_audit || [];
  if (!rule.text && !audit.length) return '';
  const pct = x => (x === null || x === undefined) ? '–' : Math.round(x*100) + '%';
  const items = audit.map(r => {
    const m = (r.marks || []).find(x => x.counted) || (r.marks || []).slice().sort((p,q) => (q.overlap_frac||0) - (p.overlap_frac||0))[0];
    const gap = m && m.centre_gap_days !== null && m.centre_gap_days !== undefined ? `, centre gap ${fmt(m.centre_gap_days,3)} d` : '';
    return `<li>${esc(KIND_TAG(D.reviewers[r.reviewer_id]))} ${esc(r.reviewer_id)}: overlap ${pct(r.overlap_frac)} of the window${m ? gap : ', no mark over the window'} · ${r.counted ? 'counted' : 'not counted'}</li>`;
  }).join('');
  return `<p class="countrule"><b>Counting rule:</b> ${esc(rule.text || 'not stored')}.</p>${items ? `<ul class="epochs countlist" aria-label="Overlap of each reviewer with the consensus window">${items}</ul>` : ''}`;
}

function scopeNote(c){
  const days = D.subject_days ? `${fmt(D.subject_days,0)}-day` : 'per-subject';
  const eph = c.period_days ? `BLS period ${fmt(c.period_days,3)} d, t0 ${fmt(c.bls_t0,4)}, duration ${fmt((c.bls_duration_days||0)*24,1)} h; ${(c.epochs||[]).length} predicted epochs measured in this subject.` : 'No BLS ephemeris covers this dip.';
  const s = sigById[c.signal_id], merged = s && (s.bls||[]).length > 1 ? ` This signal merges ${s.bls.length} per-subject BLS results; epoch numbers E count on the reference subject's ephemeris.` : '';
  return `Scope: the BLS search and its epochs are per ${days} subject, not per TESS sector. ${eph}${merged} Depth and duration are the consensus window's measured values. This is a candidate, unconfirmed.`;
}

function crossmatchLine(c){
  const x = D.crossmatch || {};
  const cmp = ((x.comparison || {}).by_candidate || {})[c.candidate_id];
  const when = x.fetched_at ? ` stored ${esc(x.fetched_at.slice(0,10))}` : '';
  const cls = x.status === 'matched' ? 'xm-hit' : x.status === 'no_match' ? 'xm-none' : 'xm-notrun';
  const ran = x.status === 'matched' || x.status === 'no_match';
  const text = ran ? esc(x.line) + '.' + (cmp ? ` <span class="xm-cmp"><b>Comparison for this dip:</b> ${esc(cmp.line)}.</span>` : '') : 'Known-planet cross-match not run: the archive was unreachable when this page was built.';
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
      ${crossmatchLine(c)}
    </section>
    <p class="filternote" id="filternote" hidden></p>
    <div class="head">
      <div><div class="hint">candidate, unconfirmed · ${esc(c.target)} · ${esc(c.mission)} · subject ${esc(c.subject_id)}</div>
      <h2>Signal ${esc(sigLabel(s))} <span class="dipid">· dip ${e !== null ? 'E'+e+' · ' : ''}${esc(c.candidate_id)}</span></h2></div>
      <div class="sigout">signal: ${outBadge(s.outcome)}</div>
    </div>
    ${sec('strip', 'Transit strip', 'stored measurements only · nothing is fitted · <kbd>s</kbd> collapses', `<div class="hero-wrap strip" id="strip" tabindex="0" role="group" aria-label="Transit strip for ${esc(c.candidate_id)}. Use left and right arrow keys to step through the stored bins, Shift for ten, Home and End for the ends."></div>
      <div class="legend"><span><i class="k-pt"></i>binned flux ±1σ (stored)</span><span><i class="k-box"></i>box model at measured depth and duration</span><span><i class="k-band"></i>consensus window</span><span><i class="k-lane"></i>reviewer marks, one lane each · SIM = simulated detector (not a person), CLAUDE = Claude model</span><span><i class="k-hatch"></i>${esc(notCountedLegend(c))}</span></div>
      <p class="scope">${scopeNote(c)}</p>`)}
    <div class="facts">
      <div><span>mid-time</span>${fmt(c.t_center,3)} ${esc(c.time_unit)}</div>
      <div><span>duration</span>${fmt(c.duration_hours,2)} h</div>
      <div><span>depth</span>${fmt(c.depth_ppm,0)} ppm</div>
      <div><span>SNR</span>${fmt(c.snr,1)}</div>
      <div class="panelfact"><span>panel</span>${fmt(c.score,2)} · marked by ${c.n_reviewers} of ${nAll} reviewers: ${esc(reviewerSummary(c.reviewers))} (panel: ${esc(reviewerSummary(Object.keys(D.reviewers)))})${countNote(c)}</div>
      <div><span>BLS period</span>${c.period_days ? fmt(c.period_days,3)+' d (this subject)' : 'none'}</div>
      <div><span>BLS t0</span>${(c.bls_t0 !== null && c.bls_t0 !== undefined) ? fmt(c.bls_t0,4) : '–'}</div>
    </div>`;
  const dipBtns = s.dips.map(id => { const d = byId[id], ep = epochOf(d); return `<button class="dipbtn${id===c.candidate_id?' cur':''}" data-dip="${esc(id)}" aria-current="${id===c.candidate_id}">${ep !== null ? 'E'+ep+' · ' : ''}${fmt(d.t_center,3)} · ${fmt(d.depth_ppm,0)} ppm · <span class="${OUT_CLS[d.outcome]}"><span aria-hidden="true">${OUT_GLYPH[d.outcome]}</span> ${esc(d.outcome)}</span></button>`; }).join('');
  rest.innerHTML = `
    ${sec('signal', `Signal · ${s.dips.length} dip${s.dips.length===1?'':'s'}`, s.period_days ? ((s.bls||[]).length > 1 ? `one signal from ${s.bls.length} per-subject BLS results that agree; each dip vetted on its own` : `one BLS period in subject ${esc(s.subject_id)}; each dip vetted on its own`) : 'no BLS period: this dip is its own signal', `<div class="dips">${dipBtns}</div>${blsTable(s)}`)}
    ${sec('ctx', 'Subject in context', 'blue: this dip · pale blue: same signal · grey: other dips here', '<div class="hero-wrap" id="ctx"></div>')}
    ${sec('cmp', 'Comparisons', 'phase fold · stored per-epoch depths · secondary window', '<div class="compare" id="cmp"></div>')}
    ${sec('ledger', 'Verdict ledger', 'every check, measured value, rule', `<div class="scroll"><table class="ledger" role="table" aria-label="Verdict ledger for ${esc(c.candidate_id)}"><thead role="rowgroup"><tr role="row" class="lhead"><th role="columnheader" scope="col">Check</th><th role="columnheader" scope="col">Value</th><th role="columnheader" scope="col">Rule</th><th role="columnheader" scope="col">Why</th></tr></thead><tbody role="rowgroup">${ledger(c)}</tbody></table></div><p class="scope">Rows marked signal-level are measured once per BLS ephemeris over all its epochs in the subject, not per dip, so every dip from that subject shows the same value (a merged signal shows each subject's own value). σ values are the stored errors; Δ uses √(σ_odd² + σ_even²), as the vetting code does.${(s.bls||[]).length > 1 ? ' <b>' + esc(D.cross_subject_note) + '</b>' : ''}</p>`)}
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
    for (const k of ['fold','oddeven','secondary']){ const wrap = document.createElement('div'); wrap.appendChild(cmp[k]); if (k==='fold') wrap.insertAdjacentHTML('beforeend','<p>Every transit folded on the period. A planet repeats at one phase.</p>'); if (k==='oddeven') wrap.insertAdjacentHTML('beforeend', `<p>Alternating depths point to a binary at twice the period. Each value is stored by the pipeline at a BLS-predicted epoch of its subject. The axis numbers signal epochs E on the reference ephemeris; under each is the subject (S1, S2 in time order) and the epoch's parity in that subject, which the odd/even test uses.${(sigById[c.signal_id].bls||[]).length > 1 ? ' ' + esc(D.cross_subject_note) : ''}</p>`); if (k==='secondary') wrap.insertAdjacentHTML('beforeend','<p>A dip here would point to an eclipsing binary.</p>'); $('#cmp').appendChild(wrap); }
  } else {
    $('#strip').outerHTML = '<div class="empty">No plot data stored for this subject.</div>';
  }
  updateFilterNote();
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


def _ppm(x: float) -> str:
    """A depth in ppm, with a true minus sign."""
    return f"{x * 1e6:.0f}".replace("-", "−")


def _sig(x: float) -> str:
    return f"{x:.1f}".replace("-", "−")


def odd_even_value(od, ev, oe, ee) -> str | None:
    """'251 ± 12 / 247 ± 8 ppm, Δ = 0.3σ' from the stored depths and errors.

    The σ of the difference is √(odd_err² + even_err²), as vet.py uses it.
    """
    if od is None or ev is None:
        return None
    if oe is None or ee is None:
        return f"{_ppm(od)} / {_ppm(ev)} ppm (no stored errors)"
    text = f"{_ppm(od)} ± {_ppm(oe)} / {_ppm(ev)} ± {_ppm(ee)} ppm"
    sigma = math.hypot(oe, ee)
    return text + (f", Δ = {_sig(abs(od - ev) / sigma)}σ" if sigma > 0 else "")


def secondary_value(sd, se) -> str | None:
    """'−10 ± 8 ppm (−1.2σ)' from the stored secondary depth and error."""
    if sd is None:
        return None
    if se is None or se <= 0:
        return f"{_ppm(sd)} ppm (no stored error)"
    return f"{_ppm(sd)} ± {_ppm(se)} ppm ({_sig(sd / se)}σ)"


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
    out.append(_check("oddeven", "odd / even (signal-level)", odd_even_value(od, ev, oe, ee), "|Δ| ≤ 3σ, σ = √(σ_odd² + σ_even²)",
                      flagged("odd_even_mismatch", oe_ran, True),
                      "Alternating depths would mean a binary at twice the period. Measured once per BLS ephemeris over all its epochs in the subject, not per dip.",
                      "" if oe_ran or None in (od, ev) else "one parity has no dip at ≥ 5σ, so the comparison did not run"))
    sd, se = _num(m.get("secondary_depth")), _num(m.get("secondary_err"))
    sec_ran = sd is not None and se is not None and se > 0
    out.append(_check("secondary", "secondary eclipse (signal-level)", secondary_value(sd, se), "depth ≤ 3σ (one-sided)",
                      flagged("secondary_eclipse", sec_ran, True),
                      "A dip at phase 0.5 would mean an eclipsing binary. Measured once per BLS ephemeris at phase 0.5 in the subject, not per dip."))
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


MERGE_PERIOD_TOL = 0.01  # periods of one signal agree within 1 percent


def _bls_duration(dips: list[dict]) -> float | None:
    """The stored BLS duration of a subject's ephemeris, else the widest stored window."""
    d = _num(dips[0].get("bls_duration_days"))
    if d is not None and d > 0:
        return d
    widths = [_num(x.get("t_end")) - _num(x.get("t_start")) for x in dips
              if _num(x.get("t_end")) is not None and _num(x.get("t_start")) is not None]
    return max(widths) if widths else None


def _predicted_offset(t0: float, period: float, t: float) -> float:
    """Distance (days) from time t to the nearest epoch predicted by (t0, period)."""
    n = round((t - t0) / period)
    return abs(t0 + n * period - t)


def same_ephemeris(a: dict, b: dict, tol: float = MERGE_PERIOD_TOL) -> bool:
    """Whether two per-subject BLS results describe one signal.

    Both must be on the same target, their periods must agree within ``tol``
    (relative to the shorter), and each one's predicted epochs must land within
    one transit duration of the other's epochs (its stored t0 and its dips).
    """
    if not a.get("target") or a.get("target") != b.get("target"):
        return False
    pa, pb = a["period_days"], b["period_days"]
    if abs(pa - pb) / min(pa, pb) >= tol:
        return False
    dur = max(x for x in (a.get("duration_days"), b.get("duration_days"), 0.0) if x is not None)
    if dur <= 0:
        return False
    for x, y in ((a, b), (b, a)):
        times = [y["t0"], *y["dip_times"]]
        if any(_predicted_offset(x["t0"], x["period_days"], t) > dur for t in times):
            return False
    return True


def group_signals(candidates: list[dict]) -> list[dict]:
    """Group dips into signals, epochs as children.

    First one group per (subject, BLS period). The BLS runs per subject, so one
    planet seen in two subjects gives two slightly different periods; groups of
    the same target whose ephemerides agree (``same_ephemeris``) are merged into
    one signal, and each subject's BLS result is kept under ``bls`` as provenance.
    Groups of different targets never merge. A dip with no BLS period is its own
    signal. Signal outcome is the most severe outcome among its dips, so a signal
    never reads better than a dip in it.
    """
    groups: dict = {}
    for c in candidates:
        period = _num(c.get("period_days"))
        key = (c["subject_id"], round(period, 9)) if period is not None else (c["subject_id"], "dip", c["candidate_id"])
        groups.setdefault(key, []).append(c)

    # One BLS result per periodic group, then merge agreeing ones (union-find).
    results = []
    for key, dips in groups.items():
        dips = sorted(dips, key=lambda d: d["t_center"])
        first = dips[0]
        period = _num(first.get("period_days"))
        t0 = _num(first.get("bls_t0"))
        results.append({
            "subject_id": first["subject_id"],
            "target": first.get("target") or "",
            "period_days": period,
            "t0": t0 if t0 is not None else (first["t_center"] if period is not None else None),
            "bls_t0": first.get("bls_t0"),
            "duration_days": _bls_duration(dips) if period is not None else None,
            "n_transits": first.get("n_transits"),
            "dip_times": [d["t_center"] for d in dips],
            "dips": dips,
        })
    parent = list(range(len(results)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(results):
        for j in range(i + 1, len(results)):
            b = results[j]
            if a["period_days"] is not None and b["period_days"] is not None and same_ephemeris(a, b):
                parent[root(j)] = root(i)
    merged: dict = {}
    for i, r in enumerate(results):
        merged.setdefault(root(i), []).append(r)

    signals = []
    for parts in merged.values():
        parts.sort(key=lambda r: r["dip_times"][0])
        dips = sorted((d for r in parts for d in r["dips"]), key=lambda d: d["t_center"])
        outcomes = [d.get("outcome") for d in dips if d.get("outcome")]
        sig_outcome = max(outcomes, key=_SEVERITY.__getitem__) if outcomes else None
        # Reference ephemeris: the subject result with the most BLS transits (ties: the earliest).
        ref = max(parts, key=lambda r: (r["n_transits"] or 0, -r["dip_times"][0]))
        period = ref["period_days"]
        if period is not None:
            sid = f"{ref['subject_id']}-P{period:.4f}" + (f"+{len(parts) - 1}" if len(parts) > 1 else "")
        else:
            sid = f"{dips[0]['candidate_id']}-single"
        signals.append({
            "signal_id": sid,
            "target": ref["target"],
            "subject_id": ref["subject_id"],
            "subject_ids": [r["subject_id"] for r in parts],
            "period_days": period,
            "bls_t0": ref["bls_t0"],
            "n_transits": sum(r["n_transits"] or 0 for r in parts) if period is not None else ref["n_transits"],
            "bls": [{
                "subject_id": r["subject_id"],
                "period_days": r["period_days"],
                "bls_t0": r["bls_t0"],
                "bls_duration_days": r["duration_days"],
                "n_transits": r["n_transits"],
                "dips": [d["candidate_id"] for d in r["dips"]],
                "reference": r is ref,
            } for r in parts] if period is not None else [],
            "dips": [d["candidate_id"] for d in dips],
            "outcome": sig_outcome,
        })
    signals.sort(key=lambda s: (s["period_days"] is None, min(c["t_center"] for c in candidates if c["candidate_id"] in s["dips"])))
    return signals


def signal_epoch(c: dict, signal: dict) -> int | None:
    """Epoch number of a dip on its signal's reference ephemeris (one count across subjects)."""
    period, t0 = _num(signal.get("period_days")), _num(signal.get("bls_t0"))
    if period is None or t0 is None or _num(c.get("period_days")) is None:
        return None
    return int(round((c["t_center"] - t0) / period))


CROSS_SUBJECT_NOTE = ("Odd/even and secondary were tested within each subject only; parity is numbered per subject. "
                      "No cross-subject test ran.")


def parity(k: int) -> str:
    return "odd" if abs(int(k)) % 2 else "even"


def annotate_signal_epochs(signal: dict, cands: dict) -> None:
    """Number every stored per-epoch row on the signal's reference ephemeris.

    The pipeline numbers epochs within each subject (``epoch``), and the
    odd/even and secondary tests use that numbering, so one signal epoch can be
    even in one subject and odd in another. Each row keeps its subject epoch and
    parity and gains ``signal_epoch`` (E on the reference ephemeris) and the
    subject's short label (S1, S2, ... in time order). ``signal["epoch_rows"]``
    collects the rows of every subject, one row per predicted epoch.
    """
    period, t0 = _num(signal.get("period_days")), _num(signal.get("bls_t0"))
    signal["epoch_rows"] = []
    if period is None or t0 is None:
        return
    for i, part in enumerate(signal.get("bls") or []):
        label = f"S{i + 1}"
        part["label"] = label
        for k, cid in enumerate(part["dips"]):
            c = cands[cid]
            c["subject_label"] = label
            for rows, phase in ((c.get("epochs") or [], 0.0), (c.get("secondary_epochs") or [], 0.5)):
                for r in rows:
                    r["signal_epoch"] = int(round((r["t_mid"] - t0) / period - phase))
                    r["subject_parity"] = parity(r["epoch"])
                    r["subject_id"] = c["subject_id"]
                    r["subject_label"] = label
            if k == 0:
                signal["epoch_rows"].extend(dict(r) for r in c.get("epochs") or [])
    signal["epoch_rows"].sort(key=lambda r: r["t_mid"])


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
    table = NasaExoplanetArchive.query_criteria(
        table="ps", select="pl_name,hostname,pl_orbper,pl_tranmid,tran_flag,rv_flag,tic_id", where=where)
    planets = []
    for row in table:
        per = row["pl_orbper"]
        per = getattr(per, "value", per)
        mid = row["pl_tranmid"]
        mid = getattr(mid, "value", mid)
        planets.append({
            "pl_name": str(row["pl_name"]),
            "hostname": str(row["hostname"]),
            "pl_orbper": _num(per),
            "pl_tranmid": _num(mid),
            "tran_flag": _flag(row["tran_flag"]),
            "rv_flag": _flag(row["rv_flag"]),
            "tic_id": str(row["tic_id"]),
        })
    planets.sort(key=lambda p: (p["pl_orbper"] is None, p["pl_orbper"] or 0))
    return planets


def _flag(value) -> bool | None:
    """An archive 0/1 flag as True or False, or None when it is masked or missing."""
    x = _num(getattr(value, "value", value))
    return None if x is None else bool(x)


def crossmatch(run_dir: Path, targets: list[str], star: str | None = None, *, refresh: bool = False) -> dict:
    """Fetch (or reuse) the stored cross-match for the run's targets.

    The result is stored in the run directory, so the page rebuilds offline.
    When the archive cannot be reached the stored status is ``not_run``,
    which the page states; it is never a silent blank.
    """
    path = Path(run_dir) / CROSSMATCH_FILE
    stored = None
    if path.exists():
        try:
            stored = json.loads(path.read_text())
        except (OSError, ValueError):
            stored = None
        if not (stored and stored.get("status") in ("matched", "no_match")
                and stored.get("targets") == targets and stored.get("star") == star):
            stored = None
    # A stored result from before the transit flag was queried is fetched again once;
    # if the archive is unreachable it is kept, and its planets get no epoch offset.
    has_flags = stored is not None and all("tran_flag" in p for p in stored.get("planets") or [])
    if stored is not None and not refresh and has_flags:
        return stored
    result = {"source": "NASA Exoplanet Archive, table ps (default_flag = 1)", "targets": targets, "star": star,
              "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "planets": []}
    try:
        for target in targets:
            result["planets"].extend(query_archive(target, star))
        result["status"] = "matched" if result["planets"] else "no_match"
    except Exception as exc:  # network, DNS, service or missing package: the cross-match did not run
        if stored is not None:
            return stored
        result["status"] = "not_run"
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    path.write_text(json.dumps(result, indent=2))
    return result


# Offsets from a mission time system to BJD (TDB), the archive's pl_tranmid system.
TIME_OFFSETS_BJD = {"BTJD": 2457000.0, "BKJD": 2454833.0, "BJD": 0.0}


# A transit mid-time outside this BJD range (1858 to 2405) is not a usable ephemeris.
PLAUSIBLE_TRANMID_BJD = (2400000.0, 2600000.0)
NO_TRANSIT_EPHEMERIS = "no transit ephemeris to compare"


def transit_ephemeris(p: dict) -> tuple[bool, str]:
    """Whether an archive planet has a transit ephemeris to compare, and why not.

    Only a planet the archive flags as transiting (tran_flag true) with a
    plausible transit mid-time has one. A radial-velocity planet's pl_tranmid,
    when stored, is a predicted conjunction, not an observed transit.
    """
    flag = p.get("tran_flag")
    if flag is None:
        return False, "transit flag not stored"
    if not flag:
        return False, "non-transiting"
    mid = _num(p.get("pl_tranmid"))
    if mid is None:
        return False, "no transit mid-time stored"
    if not PLAUSIBLE_TRANMID_BJD[0] <= mid <= PLAUSIBLE_TRANMID_BJD[1]:
        return False, "transit mid-time implausible"
    return True, ""


def planet_label(p: dict) -> str:
    """'pi Men c (P 6.268 d)', or 'pi Men d (RV, non-transiting)' when the archive says it does not transit."""
    if p.get("tran_flag") is False:
        return f"{p['pl_name']} ({'RV, ' if p.get('rv_flag') else ''}non-transiting)"
    return f"{p['pl_name']} (P {p['pl_orbper']:.3f} d)" if p.get("pl_orbper") is not None else p["pl_name"]


def compare_with_archive(planets: list[dict], dips: list[dict], tol: float = MERGE_PERIOD_TOL) -> dict:
    """Compare each dip with each archive planet, from stored values only.

    For every archive planet with a period: ΔP = |P_bls - P_archive| / P_archive
    (percent of the archive period). For a planet with a transit ephemeris
    (``transit_ephemeris``: flagged transiting, plausible pl_tranmid), also the
    offset in minutes of the nearest transit predicted by pl_tranmid and
    pl_orbper from the dip's stored mid-time (positive: the predicted transit
    comes later). Any other planet gets no offset: there is no transit
    ephemeris to compare. A planet is consistent when ΔP is below ``tol``.
    Archive values only; this claims no detection either way.
    """
    out = {}
    for c in dips:
        P = _num(c.get("period_days"))
        t = _num(c.get("t_center"))
        offset = TIME_OFFSETS_BJD.get(str(c.get("time_unit") or "").upper())
        rows = []
        for p in planets:
            pa = _num(p.get("pl_orbper"))
            if pa is None or pa <= 0:
                continue
            has_eph, why = transit_ephemeris(p)
            row = {"pl_name": p["pl_name"], "pl_orbper": pa, "dP_pct": None, "epoch_offset_min": None,
                   "transit_ephemeris": has_eph, "offset_note": "" if has_eph else f"{NO_TRANSIT_EPHEMERIS} ({why})"}
            if P is not None:
                row["dP_pct"] = abs(P - pa) / pa * 100.0
            mid = _num(p.get("pl_tranmid"))
            if has_eph and t is not None and offset is not None:
                t_bjd = t + offset
                n = round((t_bjd - mid) / pa)
                row["epoch_offset_min"] = (mid + n * pa - t_bjd) * 1440.0
            rows.append(row)
        hits = sorted((r for r in rows if r["dP_pct"] is not None and r["dP_pct"] < tol * 100), key=lambda r: r["dP_pct"])
        if hits:
            h = hits[0]
            if not h["transit_ephemeris"]:
                off = NO_TRANSIT_EPHEMERIS
            elif h["epoch_offset_min"] is None:
                off = "nearest epoch offset not computed (time system unknown)"
            else:
                off = "nearest epoch offset " + f"{h['epoch_offset_min']:.0f} min".replace("-", "−")
            line = f"consistent with {h['pl_name']}: ΔP {h['dP_pct']:.2f}%, {off}"
        elif P is None:
            line = "no archive planet within tolerance (this dip has no BLS period to compare)"
        else:
            line = "no archive planet within tolerance"
        no_eph = [r["pl_name"] for r in rows if not r["transit_ephemeris"] and not (hits and r is hits[0])]
        if no_eph:
            line += f"; {', '.join(no_eph)}: {NO_TRANSIT_EPHEMERIS}"
        out[c["candidate_id"]] = {"planets": rows, "consistent_with": hits[0]["pl_name"] if hits else None, "line": line}
    return {"tolerance_dP_pct": tol * 100, "time_offsets_bjd": TIME_OFFSETS_BJD, "by_candidate": out}


def crossmatch_line(result: dict) -> str:
    status = result.get("status")
    if status == "matched":
        planets = result.get("planets") or []
        parts = [planet_label(p) for p in planets]
        noun = "planet" if len(parts) == 1 else "planets"
        return f"Host of published {noun} {', '.join(parts)}"
    if status == "no_match":
        return "No published planet matched in the archive"
    return "Known-planet cross-match not run (archive unreachable at docket build time)"


def docket_data(run_dir: str | Path, *, title: str, star: str | None = None,
                refresh_crossmatch: bool = False) -> dict:
    """The Docket's page data for a run: candidates with checks and outcomes, signals, cross-match."""
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
        c["mark_audit"] = row.get("mark_audit") or []
        c["count_rule"] = row.get("count_rule") or {}
        c["checks"] = vetting_checks(c)
        c["outcome"] = outcome(c["checks"], c["flags"], c["passed"])
        c["feed"] = feed_rules(c)
    signals = group_signals(run["candidates"])
    cands = {c["candidate_id"]: c for c in run["candidates"]}
    for s in signals:
        for cid in s["dips"]:
            cands[cid]["signal_id"] = s["signal_id"]
            cands[cid]["signal_epoch"] = signal_epoch(cands[cid], s)
        annotate_signal_epochs(s, cands)
    kinds = list(run["reviewers"].values())
    n_sim = sum(1 for k in kinds if k == "simulated")
    n_claude = sum(1 for k in kinds if k in ("claude", "claude_code"))
    targets = sorted({c["target"] for c in run["candidates"] if c["target"]})
    xm = crossmatch(run_dir, targets, star, refresh=refresh_crossmatch)
    xm["line"] = crossmatch_line(xm)
    if xm.get("status") in ("matched", "no_match"):
        # Stored with the archive values, so the page rebuilds offline.
        xm["comparison"] = compare_with_archive(xm.get("planets") or [], run["candidates"])
        stored = {k: v for k, v in xm.items() if k != "line"}
        (run_dir / CROSSMATCH_FILE).write_text(json.dumps(stored, indent=2))
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
        "cross_subject_note": CROSS_SUBJECT_NOTE,
        "outcome_label": OUTCOME_LABEL,
        "crossmatch": xm,
        "provenance": {
            "run_time": run["manifest"]["created_at"],
            "config_sha256": run["manifest"]["config_sha256"],
            "exoplan_version": run["manifest"]["exoplan_version"],
            "claude_prompt_version": run["manifest"].get("claude_prompt_version", ""),
        },
    }
    return data


def docket_page(data: dict) -> str:
    """The Docket as one self-contained HTML page for the given ``docket_data``."""
    title = data["title"]
    payload = json.dumps(data).replace("</", "<\\/")
    return f"""<!doctype html>
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
<div id="filterlive" class="sr" role="status" aria-live="polite" aria-atomic="true"></div>
<script id="data" type="application/json">{payload}</script>
<script>{DOCKET_JS}</script>
</body></html>
"""


def build_docket(run_dir: str | Path, out_dir: str | Path, *, title: str, star: str | None = None,
                 refresh_crossmatch: bool = False) -> Path:
    data = docket_data(run_dir, title=title, star=star, refresh_crossmatch=refresh_crossmatch)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(docket_page(data))
    return path

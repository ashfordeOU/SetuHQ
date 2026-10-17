"""The Docket: a case file for each candidate.

A candidate list sits on the left. The dossier on the right stacks the evidence
on one shared time axis: a context strip for the whole subject, the dip itself
at a size where its shape reads, a panel strip showing each reviewer's marks, and
a row of comparisons (phase fold, odd and even depths, secondary window). Below
them: a verdict ledger of named checks with measured values, the reviewers'
decisions, and provenance.

Keyboard: j and k move through the list, 1, 2 and 3 filter by status.
Every key has a click equivalent.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from exoplan.dashboard import _load_run

DOCKET_CSS = """
:root{--paper:#f7f6f2;--ink:#16181d;--rule:#d9d7d0;--muted:#6b6e76;--fit:#1f5fbf;--pass:#2e7d4f;--flag:#b8860b;--reject:#b23a3a;--panel:#fcfbf8;--sel:#ebe9e1;
--l-det:#8a7e57;--l-det2:#5c7f8f;--l-cl1:#7b5ea7;--l-cl2:#b0623a;--cons:#16181d}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--paper:#121317;--ink:#ecebe6;--rule:#2a2c33;--muted:#9a9ca4;--fit:#6fa0ff;--pass:#5cc08a;--flag:#e0b243;--reject:#ef7070;--panel:#17181d;--sel:#22242b;--l-det:#b5a777;--l-det2:#8bb0c0;--l-cl1:#a98bd6;--l-cl2:#d88a62;--cons:#ecebe6;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#121317;--ink:#ecebe6;--rule:#2a2c33;--muted:#9a9ca4;--fit:#6fa0ff;--pass:#5cc08a;--flag:#e0b243;--reject:#ef7070;--panel:#17181d;--sel:#22242b;--l-det:#b5a777;--l-det2:#8bb0c0;--l-cl1:#a98bd6;--l-cl2:#d88a62;--cons:#ecebe6;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.5 "Inter Tight",system-ui,sans-serif;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));min-width:0}
:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
.mono{font-family:"JetBrains Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.app{display:grid;grid-template-columns:320px minmax(0,1fr);min-height:100vh;min-width:0}
.list{border-right:1px solid var(--rule);padding:18px 0;overflow:auto;max-height:100vh;position:sticky;top:0;min-width:0}
.run{padding:0 16px 14px;border-bottom:1px solid var(--rule);margin-bottom:8px}
.run h1{font:600 17px/1.2 "Inter Tight",sans-serif;margin:0 0 6px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:12px "JetBrains Mono",monospace;border:1px solid var(--rule);background:none;color:var(--muted);padding:3px 8px;border-radius:999px;cursor:pointer}
.chip[aria-pressed="true"]{color:var(--ink);border-color:var(--ink)}
.row{display:grid;grid-template-columns:110px 1fr auto;gap:10px;align-items:center;padding:8px 16px;cursor:pointer;border-left:3px solid transparent}
.row:hover{background:var(--sel)}
.row[aria-selected="true"]{border-left-color:var(--ink);background:var(--sel)}
.row:focus-visible{outline:2px solid var(--fit);outline-offset:-2px}
.row small{display:block;font:11px "JetBrains Mono",monospace;color:var(--muted)}
.glyph{font:600 12px "JetBrains Mono",monospace}
.g-pass{color:var(--pass)}.g-flag{color:var(--flag)}.g-fail{color:var(--reject)}
.dossier{padding:22px 28px 40px;min-width:0;display:grid;gap:22px;align-content:start}
.head{display:flex;flex-wrap:wrap;gap:12px 24px;align-items:baseline;justify-content:space-between;border-bottom:1px solid var(--rule);padding-bottom:12px}
.head h2{font:600 22px/1.2 "Inter Tight",sans-serif;margin:0}
.verdict{font:600 13px "JetBrains Mono",monospace}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;font:13px "JetBrains Mono",monospace}
.facts span{color:var(--muted);margin-right:6px}
.sec{display:grid;gap:8px;min-width:0}
.sec>header{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.sec>header h3{font:600 12px/1 "JetBrains Mono",monospace;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0}
.sec>header em{font:12px "Inter Tight",sans-serif;color:var(--muted);font-style:normal}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{font:11px "JetBrains Mono",monospace;fill:var(--muted)}
svg .grid{stroke:var(--rule);stroke-width:1}
svg .hl{fill:var(--ink)}
.hero-wrap{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:8px}
.compare{display:grid;gap:12px;grid-template-columns:repeat(3,minmax(0,1fr))}
.compare>div{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:8px;min-width:0}
.compare p{margin:4px 0 0;font:12px "Inter Tight",sans-serif;color:var(--muted)}
.scroll{overflow-x:auto;min-width:0}
.ledger{width:100%;border-collapse:collapse;font:13px "JetBrains Mono",monospace}
.ledger td{padding:7px 8px;border-bottom:1px solid var(--rule);vertical-align:top}
.ledger td{min-width:0}
.ledger td:nth-child(1){white-space:nowrap}
.ledger .why{font:13px "Inter Tight",sans-serif;color:var(--muted)}
.rat{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));min-width:0}
.rat>div{border-top:2px solid var(--rule);padding-top:8px;min-width:0}
.rat b{font:600 12px "JetBrains Mono",monospace}
.rat p{margin:6px 0 0;color:var(--muted);font-size:13px}
.prov{font:11px/1.6 "JetBrains Mono",monospace;color:var(--muted);border-top:1px solid var(--rule);padding-top:10px;overflow-wrap:anywhere}
.empty{color:var(--muted);font-style:italic;padding:12px 0}
.hint{font:12px "JetBrains Mono",monospace;color:var(--muted)}
kbd{font:11px "JetBrains Mono",monospace;border:1px solid var(--rule);border-radius:4px;padding:0 4px}
@media (max-width:900px){.app{grid-template-columns:minmax(0,1fr)}.list{position:static;max-height:none;border-right:0;border-bottom:1px solid var(--rule)}.compare{grid-template-columns:minmax(0,1fr)}.dossier{padding:16px}}
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
const STATUS = {pass:'passed', flag:'flagged', fail:'rejected'};
const GLYPH = {pass:'✓', flag:'!', fail:'✕'};
const state = {filter:'all', selected: null};

function statusOf(c){ if (!c.passed) return 'fail'; if (c.flags.length) return 'flag'; return 'pass'; }
function visible(){ return D.candidates.filter(c => state.filter === 'all' || statusOf(c) === state.filter); }

function renderRunHeader(){
  const c = D.counts, box = $('#run');
  const chips = [['all', `${c.consensus} dips`], ['pass', `${c.passed} passed`], ['flag', `${c.flagged} flagged`], ['fail', `${c.rejected} rejected`]];
  box.innerHTML = `<h1>${esc(D.title)}</h1><div class="chips">${chips.map(([k,l]) => `<button class="chip" data-f="${k}" aria-pressed="${state.filter===k}">${l}</button>`).join('')}</div><div class="hint" style="margin-top:8px"><kbd>j</kbd>/<kbd>k</kbd> move · <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> filter</div>`;
  box.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => { state.filter = b.dataset.f; renderList(); }));
}

function miniSpark(c){
  const subj = D.subjects[c.subject_id]; if (!subj) return '';
  const W=110, H=26, t0 = c.t_center - 0.25, t1 = c.t_center + 0.25;
  const pts = subj.time.map((t,i)=>[t,subj.flux[i]]).filter(([t]) => t>=t0 && t<=t1);
  if (pts.length < 2) return `<svg viewBox="0 0 ${W} ${H}"></svg>`;
  const lo = Math.min(...pts.map(p=>p[1])), hi = Math.max(...pts.map(p=>p[1])), span = (hi-lo)||1e-5;
  const d = pts.map(([t,f],i)=> (i?'L':'M')+((t-t0)/(t1-t0)*W).toFixed(1)+','+((1-(f-lo)/span)*(H-4)+2).toFixed(1)).join('');
  return `<svg viewBox="0 0 ${W} ${H}"><path d="${d}" fill="none" stroke="var(--ink)" stroke-width="1.2"/></svg>`;
}

function renderList(){
  const box = $('#rows'), rows = visible();
  box.innerHTML = '';
  if (!rows.length){ box.innerHTML = '<div class="empty" style="padding:16px">No candidates with this status in this run.</div>'; return; }
  for (const c of rows){
    const s = statusOf(c), d = document.createElement('div');
    d.className = 'row'; d.setAttribute('role','option'); d.tabIndex = 0; d.dataset.id = c.candidate_id;
    d.setAttribute('aria-selected', String(state.selected === c.candidate_id));
    d.innerHTML = `${miniSpark(c)}<div><div class="mono" style="font-size:12px">${esc(c.candidate_id)}</div><small>${fmt(c.t_center,3)} BTJD · ${fmt(c.depth_ppm,0)} ppm · SNR ${fmt(c.snr,1)}</small></div><span class="glyph g-${s}" title="${STATUS[s]}">${GLYPH[s]}</span>`;
    d.addEventListener('click', () => select(c.candidate_id));
    d.addEventListener('keydown', e => { if (e.key === 'Enter') select(c.candidate_id); });
    box.appendChild(d);
  }
}

function select(id){
  state.selected = id;
  document.querySelectorAll('.row').forEach(r => r.setAttribute('aria-selected', String(r.dataset.id === id)));
  renderDossier();
  history.replaceState(null, '', '#' + id);
}

function moveSelection(step){
  const rows = visible(); if (!rows.length) return;
  const i = rows.findIndex(c => c.candidate_id === state.selected);
  const next = rows[Math.min(rows.length-1, Math.max(0, i + step))];
  select(next.candidate_id);
  document.querySelector(`.row[data-id="${next.candidate_id}"]`)?.scrollIntoView({block:'nearest'});
}

// ---------- dossier ----------
function trapezoid(t, t0, dur, depthPpm){
  const half = dur/2, tau = 0.1*dur, x = Math.abs(t - t0);
  if (x >= half) return 0;
  return x <= half - tau ? depthPpm : depthPpm * (half - x)/tau;
}

function hero(c, subj, marks){
  const W=900, H=360, pl=72, pr=18, pt=18, pb=34;
  const D2 = c.duration_hours/24, span = 3*D2 + D2;
  const t0 = c.t_center - span, t1 = c.t_center + span;
  const pts = subj.time.map((t,i)=>({t, p:(subj.flux[i]-1)*1e6})).filter(q => q.t >= t0 && q.t <= t1);
  const base = pts.length ? [...pts].map(q=>q.p).sort((a,b)=>a-b)[Math.floor(pts.length/2)] : 0;
  const depth = Math.max(c.depth_ppm, 50);
  const ylo = -1.6*depth, yhi = 0.6*depth;
  const X = t => pl + (t-t0)/(t1-t0)*(W-pl-pr), Y = p => pt + (yhi - p)/(yhi-ylo)*(H-pt-pb);
  const svg = el('svg', {viewBox:`0 0 ${W} ${H}`, role:'img', 'aria-label': `Dip ${c.candidate_id}`});
  // edge of subject shading
  if (t0 < subj.start) el('rect', {x:pl, y:pt, width:X(subj.start)-pl, height:H-pt-pb, fill:'var(--sel)'}, svg);
  if (t1 > subj.end) el('rect', {x:X(subj.end), y:pt, width:W-pr-X(subj.end), height:H-pt-pb, fill:'var(--sel)'}, svg);
  // dip window and consensus
  el('rect', {x:X(c.t_start), y:pt, width:Math.max(2,X(c.t_end)-X(c.t_start)), height:H-pt-pb, fill:'var(--fit)', opacity:.07}, svg);
  for (let k=0;k<=4;k++){ const p = ylo + (yhi-ylo)*k/4; el('line', {x1:pl,x2:W-pr,y1:Y(p),y2:Y(p),class:'grid'}, svg); tx(svg, pl-8, Y(p)+4, Math.round(p), 'end'); }
  for (let k=0;k<=6;k++){ const t = t0 + (t1-t0)*k/6; tx(svg, X(t), H-12, t.toFixed(2), 'middle'); }
  tx(svg, pl, pt-6, 'ppm vs baseline', 'start');
  // points with error bars
  for (const q of pts){ el('circle', {cx:X(q.t), cy:Y(q.p-base), r:2.6, fill:'var(--ink)'}, svg); }
  // fit
  let d=''; for (let i=0;i<=200;i++){ const t = t0 + (t1-t0)*i/200; d += (i?'L':'M')+X(t).toFixed(1)+','+Y(-trapezoid(t, c.t_center, D2, c.depth_ppm)).toFixed(1); }
  el('path', {d, fill:'none', stroke:'var(--fit)', 'stroke-width':1.6}, svg);
  // dimension lines: duration at -depth, depth at right edge
  const yd = Y(-c.depth_ppm);
  el('line', {x1:X(c.t_center-D2/2), x2:X(c.t_center+D2/2), y1:yd-14, y2:yd-14, stroke:'var(--ink)'}, svg);
  el('line', {x1:X(c.t_center-D2/2), x2:X(c.t_center-D2/2), y1:yd-18, y2:yd-10, stroke:'var(--ink)'}, svg);
  el('line', {x1:X(c.t_center+D2/2), x2:X(c.t_center+D2/2), y1:yd-18, y2:yd-10, stroke:'var(--ink)'}, svg);
  tx(svg, X(c.t_center), yd-20, fmt(c.duration_hours,2)+' h', 'middle', 'hl');
  const xr = X(t1) - 6;
  el('line', {x1:xr, x2:xr, y1:Y(0), y2:Y(-c.depth_ppm), stroke:'var(--ink)'}, svg);
  tx(svg, xr-6, (Y(0)+Y(-c.depth_ppm))/2+4, fmt(c.depth_ppm,0)+' ppm', 'end', 'hl');
  if (pts.length < 12) tx(svg, pl+8, pt+16, `only ${pts.length} binned points in this window`, 'start');
  return svg;
}

function context(c, subj){
  const W=900, H=64, pl=72, pr=18, pt=6;
  const svg = el('svg', {viewBox:`0 0 ${W} ${H}`});
  const X = t => pl + (t-subj.start)/(subj.end-subj.start)*(W-pl-pr);
  const f = subj.flux.map(v => (v-1)*1e6), lo = Math.min(...f), hi = Math.max(...f), span = (hi-lo)||1;
  const Y = v => pt + (1-(v-lo)/span)*(H-pt-6);
  for (const other of D.candidates.filter(x => x.subject_id === c.subject_id)){
    const cur = other.candidate_id === c.candidate_id;
    el('rect', {x:X(other.t_start), y:pt, width:Math.max(2,X(other.t_end)-X(other.t_start)), height:H-pt-6, fill: cur ? 'var(--fit)' : 'var(--muted)', opacity: cur ? .28 : .14}, svg);
  }
  let d=''; subj.time.forEach((t,i)=>{ d += (i?'L':'M')+X(t).toFixed(1)+','+Y(f[i]).toFixed(1); });
  el('path', {d, fill:'none', stroke:'var(--ink)', 'stroke-width':.9, opacity:.8}, svg);
  tx(svg, pl-8, H-6, 'subject', 'end');
  return svg;
}

function panels(c, subj, marks, decisions){
  const names = Object.keys(D.reviewers), W=900, lh=24, pl=150, pr=18;
  const D2 = c.duration_hours/24, t0 = c.t_center - 4*D2, t1 = c.t_center + 4*D2;
  const H = names.length*lh + 30;
  const svg = el('svg', {viewBox:`0 0 ${W} ${H}`});
  const X = t => pl + (t-t0)/(t1-t0)*(W-pl-pr);
  // consensus bracket
  el('line', {x1:X(c.t_start), x2:X(c.t_end), y1:12, y2:12, stroke:'var(--cons)', 'stroke-width':1.5}, svg);
  el('line', {x1:X(c.t_start), x2:X(c.t_start), y1:12, y2:18, stroke:'var(--cons)'}, svg);
  el('line', {x1:X(c.t_end), x2:X(c.t_end), y1:12, y2:18, stroke:'var(--cons)'}, svg);
  names.forEach((n, i) => {
    const y = 22 + i*lh, col = colourOf(n), spans = (marks[n] || []).filter(([a,b]) => b>=t0 && a<=t1);
    tx(svg, pl-10, y+15, n, 'end').setAttribute('fill', col);
    el('line', {x1:pl, x2:W-pr, y1:y+lh-2, y2:y+lh-2, class:'grid'}, svg);
    if (!spans.length){
      const r = el('rect', {x:pl, y:y+3, width:W-pl-pr, height:lh-8, fill:'url(#hatch)', opacity:.7}, svg);
      tx(svg, pl+8, y+15, 'no mark', 'start');
      void r;
    }
    for (const [a,b] of spans){
      const w = (decisions[n]?.label === 'potential planet' || decisions[n]?.label === 'potential_planet') ? .85 : .45;
      el('rect', {x:X(a), y:y+3, width:Math.max(3, X(b)-X(a)), height:lh-8, rx:3, fill:col, opacity:w}, svg);
    }
  });
  const defs = el('defs', {}, svg);
  const pat = el('pattern', {id:'hatch', width:6, height:6, patternUnits:'userSpaceOnUse', patternTransform:'rotate(45)'}, defs);
  el('line', {x1:0,y1:0,x2:0,y2:6,stroke:'var(--rule)','stroke-width':1.5}, pat);
  return svg;
}

function comparisons(c, subj){
  const out = {fold: null, oddeven: null, secondary: null};
  const P = c.period_days;
  if (!P){
    for (const k of Object.keys(out)) out[k] = Object.assign(document.createElement('div'), {className:'empty', textContent:'no ephemeris: single event'});
    return out;
  }
  const W=300, H=200, pl=44, pr=10, pt=14, pb=26, win = c.duration_hours/24 * 3;
  const epochs = [];
  for (let k=-30; k<=30; k++){ const tc = c.t_center + k*P; if (tc>=subj.start && tc<=subj.end) epochs.push({k, tc}); }
  const depthAt = (tc) => { const m = subj.time.map((t,i)=>[t,(subj.flux[i]-1)*1e6]).filter(([t]) => Math.abs(t-tc) <= (c.duration_hours/24)/2); return m.length ? -(m.reduce((s,q)=>s+q[1],0)/m.length) : null; };
  // fold
  {
    const svg = el('svg', {viewBox:`0 0 ${W} ${H}`}), ylo=-1.6*c.depth_ppm, yhi=0.6*c.depth_ppm;
    const X = ph => pl + (ph+win)/(2*win)*(W-pl-pr), Y = p => pt + (yhi-p)/(yhi-ylo)*(H-pt-pb);
    for (const q of subj.time.map((t,i)=>[t,(subj.flux[i]-1)*1e6])){ const ph = ((q[0]-c.t_center + P/2) % P) - P/2; if (Math.abs(ph) <= win) el('circle', {cx:X(ph), cy:Y(q[1]), r:1.6, fill:'var(--muted)', opacity:.6}, svg); }
    el('line', {x1:pl,x2:W-pr,y1:Y(0),y2:Y(0),class:'grid'}, svg);
    el('line', {x1:pl,x2:W-pr,y1:Y(-c.depth_ppm),y2:Y(-c.depth_ppm),stroke:'var(--fit)','stroke-dasharray':'3 3'}, svg);
    tx(svg, pl, pt-4, `phase fold · P ${fmt(P,3)} d`);
    out.fold = svg;
  }
  // odd / even
  {
    const svg = el('svg', {viewBox:`0 0 ${W} ${H}`}), vals = epochs.map(e => ({k:e.k, d: depthAt(e.tc)})).filter(v => v.d !== null);
    const mx = Math.max(c.depth_ppm*1.5, ...vals.map(v=>Math.abs(v.d)));
    const Y = p => pt + (1-p/mx)*(H-pt-pb), X = i => pl + (i+.5)*(W-pl-pr)/Math.max(1,vals.length);
    el('line', {x1:pl,x2:W-pr,y1:Y(0),y2:Y(0),class:'grid'}, svg);
    vals.forEach((v,i) => el('circle', {cx:X(i), cy:Y(v.d), r:5, fill: (Math.abs(v.k)%2) ? 'var(--ink)' : 'var(--fit)'}, svg));
    tx(svg, pl, pt-4, 'per-epoch depth · ink odd, blue even');
    out.oddeven = svg;
  }
  // secondary
  {
    const svg = el('svg', {viewBox:`0 0 ${W} ${H}`}), sec = epochs.map(e => depthAt(e.tc + P/2)).filter(v => v !== null);
    const mx = Math.max(c.depth_ppm*1.5, ...sec.map(Math.abs), 1);
    const Y = p => pt + (1-p/mx)*(H-pt-pb), X = i => pl + (i+.5)*(W-pl-pr)/Math.max(1,sec.length);
    el('line', {x1:pl,x2:W-pr,y1:Y(0),y2:Y(0),class:'grid'}, svg);
    sec.forEach((v,i) => el('circle', {cx:X(i), cy:Y(v), r:4, fill:'var(--muted)'}, svg));
    tx(svg, pl, pt-4, 'phase 0.5 · secondary window');
    out.secondary = svg;
  }
  return out;
}

function ledger(c){
  const m = c.metrics || {}, f = new Set(c.flags);
  const rows = [
    ['SNR', fmt(c.snr,1), '≥ 7', c.snr >= 7, true, 'Dip is strong enough to trust.'],
    ['duration', fmt((m.duration_minutes||0),0)+' min', '≥ 15 min', (m.duration_minutes||0) >= 15, true, 'Too short to be a transit otherwise.'],
    ['points in transit', fmt(m.n_in_transit,0), '≥ 2', (m.n_in_transit||0) >= 2, true, 'Enough samples inside the dip to measure it.'],
    ['edge', f.has('edge_event') ? 'within 0.1 d of edge' : 'interior', 'not at edge', !f.has('edge_event'), false, 'A partly observed dip is flagged, not rejected.'],
    ['odd / even', (m.odd_depth!==undefined) ? `${fmt(m.odd_depth*1e6,0)} / ${fmt(m.even_depth*1e6,0)} ppm` : '–', 'agree within 3σ', !f.has('odd_even_mismatch'), true, 'Alternating depths would mean a binary at twice the period.'],
    ['secondary eclipse', (m.secondary_depth!==undefined) ? `${fmt(m.secondary_depth*1e6,0)} ppm` : '–', 'not significant', !f.has('secondary_eclipse'), true, 'A dip at phase 0.5 would mean an eclipsing binary.'],
    ['depth cap', fmt(c.depth_ppm,0)+' ppm', '≤ 5,000 ppm', c.depth_ppm <= 5000, true, 'Deeper dips are almost always binaries; kept out of the feed.'],
    ['periodic support', c.n_transits ? `${c.n_transits} transits` : 'none', '≥ 2', (c.n_transits||0) >= 2, true, 'A repeated dip is needed for the feed.'],
    ['ephemeris', f.has('off_ephemeris') ? 'off' : 'on', 'on ephemeris', !f.has('off_ephemeris'), false, 'Not explained by the strong periodic signal of its star.'],
  ];
  return rows.map(([name, value, rule, ok, disq, why]) => {
    const g = ok ? 'pass' : (disq ? 'fail' : 'flag');
    return `<tr><td><span class="glyph g-${g}">${GLYPH[g]}</span> ${esc(name)}</td><td>${esc(value)}</td><td>${esc(rule)}</td><td class="why">${esc(why)}</td></tr>`;
  }).join('');
}

function rationales(c){
  const dec = D.decisions[c.subject_id] || {}, marks = D.marks[c.subject_id] || {};
  return Object.keys(D.reviewers).map(n => {
    const d = dec[n] || {}, k = (marks[n] || []).length;
    const kind = D.reviewers[n];
    const body = kind === 'claude' || kind === 'claude_code'
      ? esc(d.rationale || 'no rationale recorded')
      : `Detector: ${k} mark${k===1?'':'s'} in this subject, threshold and miss rate from its config.`;
    const label = (d.label || '').replace(/_/g,' ');
    return `<div><b style="color:${colourOf(n)}">${esc(n)}</b> <span class="hint">${esc(kind)} · ${esc(label)} · ${k} mark${k===1?'':'s'}</span><p>${body}</p></div>`;
  }).join('');
}

function renderDossier(){
  const box = $('#dossier');
  const c = D.candidates.find(x => x.candidate_id === state.selected);
  if (!c){ box.innerHTML = '<div class="empty">Choose a candidate from the list. Use j and k to move.</div>'; return; }
  const subj = D.subjects[c.subject_id], marks = D.marks[c.subject_id] || {}, dec = D.decisions[c.subject_id] || {};
  const s = statusOf(c), siblings = D.candidates.filter(x => x.subject_id === c.subject_id && x.candidate_id !== c.candidate_id).length;
  box.innerHTML = `
    <div class="head">
      <div><div class="hint">${esc(c.target)} · ${esc(c.mission)} · subject ${esc(c.subject_id)}</div><h2>${esc(c.candidate_id)}</h2></div>
      <div class="verdict g-${s}">${GLYPH[s]} ${STATUS[s]}${c.flags.length ? ' · '+esc(c.flags.join(', ')) : ''}</div>
    </div>
    <div class="facts">
      <div><span>mid-time</span>${fmt(c.t_center,3)} ${esc(c.time_unit)}</div>
      <div><span>duration</span>${fmt(c.duration_hours,2)} h</div>
      <div><span>depth</span>${fmt(c.depth_ppm,0)} ppm</div>
      <div><span>SNR</span>${fmt(c.snr,1)}</div>
      <div><span>panel</span>${fmt(c.score,2)} · ${c.n_reviewers} of ${Object.keys(D.reviewers).length}</div>
      <div><span>period</span>${c.period_days ? fmt(c.period_days,3)+' d' : 'none'}</div>
      <div><span>same subject</span>${siblings} other dip${siblings===1?'':'s'}</div>
    </div>
    <section class="sec"><header><h3>Subject in context</h3><em>highlighted: this dip · grey: other dips here</em></header><div class="hero-wrap" id="ctx"></div></section>
    <section class="sec"><header><h3>The dip</h3><em>points: binned flux · blue: fit · the bars show depth and duration</em></header><div class="hero-wrap" id="hero"></div></section>
    <section class="sec"><header><h3>Panel</h3><em>each lane is one reviewer's marks, on the same time axis as the dip</em></header><div class="hero-wrap" id="panel"></div></section>
    <section class="sec"><header><h3>Comparisons</h3><em>phase fold · odd and even depths · secondary window</em></header><div class="compare" id="cmp"></div></section>
    <section class="sec"><header><h3>Verdict</h3><em>every check, measured value, rule</em></header><div class="scroll"><table class="ledger"><tbody>${ledger(c)}</tbody></table></div></section>
    <section class="sec"><header><h3>Reviewers</h3><em>decisions and reasons, as recorded</em></header><div class="rat">${rationales(c)}</div></section>
    <div class="prov">run ${esc(D.provenance.run_time)} · config ${esc(D.provenance.config_sha256.slice(0,16))} · pipeline ${esc(D.provenance.exoplan_version)} · ${esc(D.provenance.claude_prompt_version || '')}<br>candidate ${esc(c.candidate_id)} · subject ${esc(c.subject_id)}</div>`;
  if (subj){
    $('#ctx').appendChild(context(c, subj));
    $('#hero').appendChild(hero(c, subj, marks));
    $('#panel').appendChild(panels(c, subj, marks, dec));
    const cmp = comparisons(c, subj);
    for (const k of ['fold','oddeven','secondary']){ const wrap = document.createElement('div'); wrap.appendChild(cmp[k]); if (k==='fold') wrap.insertAdjacentHTML('beforeend','<p>Every transit folded on the period. A planet repeats at one phase.</p>'); if (k==='oddeven') wrap.insertAdjacentHTML('beforeend','<p>Alternating depths point to a binary at twice the period.</p>'); if (k==='secondary') wrap.insertAdjacentHTML('beforeend','<p>A dip here would point to an eclipsing binary.</p>'); $('#cmp').appendChild(wrap); }
  } else {
    box.insertAdjacentHTML('beforeend', '<div class="empty">No plot data stored for this subject.</div>');
  }
}

document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea')) return;
  if (e.key === 'j' || e.key === 'ArrowDown') { moveSelection(1); e.preventDefault(); }
  else if (e.key === 'k' || e.key === 'ArrowUp') { moveSelection(-1); e.preventDefault(); }
  else if (e.key === '1') { state.filter='pass'; renderRunHeader(); renderList(); }
  else if (e.key === '2') { state.filter='flag'; renderRunHeader(); renderList(); }
  else if (e.key === '3') { state.filter='fail'; renderRunHeader(); renderList(); }
  else if (e.key === '0') { state.filter='all'; renderRunHeader(); renderList(); }
});

renderRunHeader(); renderList();
const fromHash = location.hash.slice(1);
const first = D.candidates.find(c => c.candidate_id === fromHash) || visible()[0] || D.candidates[0];
if (first) select(first.candidate_id); else renderDossier();
"""


def build_docket(run_dir: str | Path, out_dir: str | Path, *, title: str) -> Path:
    run_dir = Path(run_dir)
    run = _load_run(run_dir)
    rows = json.loads((run_dir / "candidates.json").read_text())
    by_id = {r["candidate_id"]: r for r in rows}
    for c in run["candidates"]:
        c["metrics"] = by_id[c["candidate_id"]].get("metrics", {})
        c["target"] = by_id[c["candidate_id"]].get("target", "")
        c["mission"] = by_id[c["candidate_id"]].get("mission", "")
        c["flags"] = [f for f in c["flags"] if f]
    counts = run["manifest"]["counts"]
    passed = sum(1 for c in run["candidates"] if c["passed"] and not c["flags"])
    flagged = sum(1 for c in run["candidates"] if c["passed"] and c["flags"])
    rejected = sum(1 for c in run["candidates"] if not c["passed"])
    data = {
        "title": title,
        "candidates": run["candidates"],
        "subjects": run["subjects"],
        "marks": run["marks"],
        "decisions": run["reviewerDecisions"],
        "reviewers": run["reviewers"],
        "counts": {"consensus": counts["consensus_events"], "passed": passed, "flagged": flagged, "rejected": rejected},
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
<title>{title}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>{DOCKET_CSS}</style></head>
<body>
<div class="app">
  <aside class="list">
    <div class="run" id="run"></div>
    <div id="rows" role="listbox" aria-label="Candidates"></div>
  </aside>
  <main class="dossier" id="dossier"></main>
</div>
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs></defs></svg>
<script id="data" type="application/json">{payload}</script>
<script>{DOCKET_JS}</script>
</body></html>
"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(page)
    return path

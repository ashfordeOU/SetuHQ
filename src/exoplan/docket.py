"""The Docket: a case file for each candidate.

A candidate list sits on the left. The dossier on the right leads with the
transit strip: the dip at a scale where its shape reads, drawn from stored
measurements only. Its upper panel shows the binned flux with the stored ±1σ
of each bin and the box model at the measured depth and duration (nothing is
fitted); its lower panel gives each reviewer a lane of marks on the same time
axis, and the consensus band runs through both. Below it: a context strip for
the whole subject, comparisons (phase fold, stored per-epoch depths, secondary
window), a verdict ledger that keeps vetting checks apart from feed admission
rules, the reviewers' decisions, and provenance.

BLS periods and epochs are per subject (a fixed-length cut of a sector), not
per sector, and every candidate is unconfirmed.

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
.ledger th.grp{text-align:left;font:600 11px "JetBrains Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding-top:14px;border-bottom:1px solid var(--rule)}
.ledger .why{font:13px "Inter Tight",sans-serif;color:var(--muted)}
.rat{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));min-width:0}
.rat>div{border-top:2px solid var(--rule);padding-top:8px;min-width:0}
.rat b{font:600 12px "JetBrains Mono",monospace}
.rat p{margin:6px 0 0;color:var(--muted);font-size:13px}
.prov{font:11px/1.6 "JetBrains Mono",monospace;color:var(--muted);border-top:1px solid var(--rule);padding-top:10px;overflow-wrap:anywhere}
.empty{color:var(--muted);font-style:italic;padding:12px 0}
.hint{font:12px "JetBrains Mono",monospace;color:var(--muted)}
kbd{font:11px "JetBrains Mono",monospace;border:1px solid var(--rule);border-radius:4px;padding:0 4px}
.strip{position:relative;padding:8px;min-width:0;overflow:hidden}
.strip svg{width:100%;touch-action:pan-y}
.strip .lanelbl,.strip .halo{paint-order:stroke;stroke:var(--panel);stroke-width:3px;stroke-linejoin:round}
.tip{position:absolute;z-index:2;max-width:min(320px,80%);background:var(--paper);border:1px solid var(--rule);border-radius:4px;padding:6px 8px;font:11px/1.45 "JetBrains Mono",monospace;color:var(--ink);pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.12)}
.readout{margin-top:6px;min-height:6.2em;font:11px/1.45 "JetBrains Mono",monospace;color:var(--ink);overflow-wrap:anywhere}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font:12px "Inter Tight",sans-serif;color:var(--muted)}
.legend i{display:inline-block;vertical-align:middle;margin-right:6px}
.legend .k-pt{width:6px;height:6px;border-radius:50%;background:var(--ink)}
.legend .k-box{width:16px;height:0;border-top:2px solid var(--fit)}
.legend .k-band{width:12px;height:10px;background:var(--fit);opacity:.25}
.legend .k-lane{width:14px;height:8px;border-radius:2px;background:var(--l-det)}
.scope{margin:0;font:12px/1.5 "Inter Tight",sans-serif;color:var(--muted)}
.epochs{margin:6px 0 0;padding-left:16px;font:12px "JetBrains Mono",monospace;color:var(--ink)}
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
function niceTicks(lo, hi, n){
  const raw = (hi-lo)/Math.max(1,n), mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo/step)*step; v <= hi + 1e-12; v += step) out.push(+v.toPrecision(12));
  return out;
}

// The transit strip: stored binned flux with stored ±1σ, the box model at the
// measured depth and duration (c.box, built in Python, nothing fitted), and one
// lane per reviewer on the same time axis. The consensus band runs through both.
function strip(c, subj, marks, decisions, wrap){
  wrap.innerHTML = '';
  const narrow = wrap.clientWidth < 600;
  const W = Math.max(240, Math.round(wrap.clientWidth - 16)), H = narrow ? 280 : 440;
  const names = Object.keys(D.reviewers), lh = narrow ? 15 : 22;
  const pl = narrow ? 42 : 150, pr = narrow ? 8 : 18, pt = 16, gap = narrow ? 10 : 18, axisH = narrow ? 24 : 30;
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
    'aria-label': `Transit strip for ${c.candidate_id}: ${pts.length} binned points, box model at measured depth ${fmt(depth,0)} ppm and duration ${fmt(c.duration_hours,2)} h, ${names.length} reviewer lanes`}, wrap);
  svg.style.height = H + 'px';
  const fs = narrow ? 9 : 11;
  const T = (x, y, s, a='start', cls='') => { const t = tx(svg, x, y, s, a, cls); t.style.fontSize = fs + 'px'; return t; };
  // subject edges: outside the subject there is no data, shaded so it is not read as flat flux
  if (t0 < subj.start) el('rect', {x:pl, y:pt, width:Math.max(0,X(subj.start)-pl), height:H-axisH-pt, fill:'var(--sel)'}, svg);
  if (t1 > subj.end) el('rect', {x:X(subj.end), y:pt, width:Math.max(0,W-pr-X(subj.end)), height:H-axisH-pt, fill:'var(--sel)'}, svg);
  // consensus band through both panels
  el('rect', {x:X(c.t_start), y:pt, width:Math.max(2,X(c.t_end)-X(c.t_start)), height:H-axisH-pt, fill:'var(--fit)', opacity:.09}, svg);
  for (const t of [c.t_start, c.t_end]) el('line', {x1:X(t), x2:X(t), y1:pt, y2:H-axisH, stroke:'var(--fit)', 'stroke-dasharray':'3 3', opacity:.6}, svg);
  // axes
  for (const p of niceTicks(lo, hi, narrow ? 3 : 5)){ el('line', {x1:pl,x2:W-pr,y1:Y(p),y2:Y(p),class:'grid'}, svg); T(pl-6, Y(p)+3, Math.round(p), 'end'); }
  for (const t of niceTicks(t0, t1, narrow ? 3 : 6)){ el('line', {x1:X(t),x2:X(t),y1:H-axisH,y2:H-axisH+4,stroke:'var(--muted)'}, svg); T(X(t), H-axisH+(narrow?13:16), t.toFixed(2), 'middle'); }
  T(pl, pt-5, 'ppm vs 1.0', 'start');
  T(W-pr, pt-5, `time (${c.time_unit})`, 'end');
  el('line', {x1:pl,x2:W-pr,y1:upperBottom,y2:upperBottom,stroke:'var(--rule)'}, svg);
  // binned points with stored ±1σ
  for (const q of pts){
    if (q.e !== null) el('line', {x1:X(q.t), x2:X(q.t), y1:Y(q.p-q.e), y2:Y(q.p+q.e), stroke:'var(--ink)', opacity:.45}, svg);
    el('circle', {cx:X(q.t), cy:Y(q.p), r:narrow ? 2 : 2.6, fill:'var(--ink)'}, svg);
  }
  // box model at measured depth and duration
  const box = c.box || [];
  if (box.length){
    let d = `M${X(t0).toFixed(1)},${Y(0).toFixed(1)}`;
    for (const [t, p] of box) d += `L${X(t).toFixed(1)},${Y(p).toFixed(1)}`;
    d += `L${X(t1).toFixed(1)},${Y(0).toFixed(1)}`;
    el('path', {d, fill:'none', stroke:'var(--fit)', 'stroke-width':1.8}, svg);
  }
  // dimension lines: depth beside the box, duration below it
  const xd = X(c.t_end) + (narrow ? 8 : 12), y0 = Y(0), yd = Y(-depth);
  el('line', {x1:xd, x2:xd, y1:y0, y2:yd, stroke:'var(--ink)'}, svg);
  for (const y of [y0, yd]) el('line', {x1:xd-4, x2:xd+4, y1:y, y2:y, stroke:'var(--ink)'}, svg);
  T(xd+6, (y0+yd)/2+4, fmt(depth,0)+' ppm', 'start', 'hl halo');
  const yb = yd + (narrow ? 12 : 16);
  el('line', {x1:X(c.t_start), x2:X(c.t_end), y1:yb, y2:yb, stroke:'var(--ink)'}, svg);
  for (const t of [c.t_start, c.t_end]) el('line', {x1:X(t), x2:X(t), y1:yb-4, y2:yb+4, stroke:'var(--ink)'}, svg);
  T((X(c.t_start)+X(c.t_end))/2, yb+(narrow?11:14), fmt(c.duration_hours,2)+' h', 'middle', 'hl halo');
  if (pts.length < 12) T(pl+6, pt+14, `only ${pts.length} binned points in this window`, 'start');
  // reviewer lanes, marks as bars
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
    if (narrow){ const t = T(pl+3, y+lh-4, n, 'start', 'lanelbl'); t.setAttribute('fill', col); }
    else { const t = T(pl-10, y+lh/2+4, n, 'end'); t.setAttribute('fill', col); }
    if (!spans.length) T(W-pr-4, y+lh-4, 'no mark in window', 'end');
  });
  // hover: crosshair snapped to the nearest stored bin, with its value ± error and the reviewer spans there
  // On a phone the readout sits under the strip so it never covers the dip.
  const tip = document.createElement('div'); tip.className = narrow ? 'readout' : 'tip'; wrap.appendChild(tip);
  const idle = 'Tap or drag on the strip to read a bin.';
  if (narrow) tip.textContent = idle; else tip.hidden = true;
  const cross = el('g', {visibility:'hidden', 'pointer-events':'none'}, svg);
  const vx = el('line', {y1:pt, y2:H-axisH, stroke:'var(--ink)', 'stroke-width':1, opacity:.7}, cross);
  const hy = el('line', {x1:pl, x2:W-pr, stroke:'var(--ink)', 'stroke-width':1, opacity:.4, 'stroke-dasharray':'2 3'}, cross);
  const dot = el('circle', {r:4.5, fill:'none', stroke:'var(--fit)', 'stroke-width':2}, cross);
  const hit = el('rect', {x:pl, y:pt, width:W-pl-pr, height:H-axisH-pt, fill:'transparent'}, svg);
  const move = e => {
    if (!pts.length) return;
    const r = svg.getBoundingClientRect(), sx = (e.clientX - r.left) * W / r.width;
    const t = t0 + (sx - pl)/(W-pl-pr)*(t1-t0);
    let q = pts[0]; for (const o of pts) if (Math.abs(o.t-t) < Math.abs(q.t-t)) q = o;
    vx.setAttribute('x1', X(q.t)); vx.setAttribute('x2', X(q.t));
    hy.setAttribute('y1', Y(q.p)); hy.setAttribute('y2', Y(q.p));
    dot.setAttribute('cx', X(q.t)); dot.setAttribute('cy', Y(q.p));
    cross.setAttribute('visibility', 'visible');
    const at = names.map(n => [n, (marks[n]||[]).filter(([a,b]) => q.t >= a && q.t <= b)]).filter(([,s]) => s.length);
    const inside = q.t >= c.t_start && q.t <= c.t_end;
    tip.innerHTML = `<b>${fmt(q.t,4)} ${esc(c.time_unit)}</b><br>bin: ${fmt(q.p,0)}${q.e!==null ? ' ± '+fmt(q.e,0) : ''} ppm${q.e===null ? ' (no stored error)' : ''}`
      + `<br>${inside ? 'inside' : 'outside'} the consensus window`
      + (at.length ? at.map(([n,s]) => `<br><span style="color:${colourOf(n)}">${esc(n)}</span> ${s.map(([a,b]) => fmt(a,3)+'–'+fmt(b,3)).join(', ')}`).join('') : '<br>no reviewer span at this time');
    if (narrow) return;
    tip.hidden = false;
    const px = X(q.t) * r.width / W, w = tip.offsetWidth;
    tip.style.left = Math.max(4, Math.min(px + 14, r.width - w - 4)) + 'px';
    tip.style.top = '18px';
  };
  hit.addEventListener('pointermove', move);
  hit.addEventListener('pointerdown', move);
  // A touch keeps its last reading; a mouse leaving the strip clears it.
  hit.addEventListener('pointerleave', e => { if (e.pointerType !== 'mouse') return; cross.setAttribute('visibility','hidden'); if (narrow) tip.textContent = idle; else tip.hidden = true; });
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

function epochList(rows, what){
  if (!rows || !rows.length) return '<p>No stored per-epoch measurement for this candidate.</p>';
  return '<ul class="epochs">' + rows.map(r => r.depth_ppm === null || r.depth_ppm === undefined
    ? `<li>epoch ${r.epoch}${what}: no stored points in window (${r.n_points} points)</li>`
    : `<li>measured: ${fmt(r.depth_ppm,0)} ± ${fmt(r.sigma_ppm,0)} ppm at epoch ${r.epoch}${what}</li>`).join('') + '</ul>';
}

function epochPlot(rows, title, depth, colour){
  const W=300, H=200, pl=44, pr=10, pt=14, pb=26, svg = el('svg', {viewBox:`0 0 ${W} ${H}`});
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
    for (const k of Object.keys(out)) out[k] = Object.assign(document.createElement('div'), {className:'empty', textContent:'no ephemeris in this subject: single event'});
    return out;
  }
  const W=300, H=200, pl=44, pr=10, pt=14, pb=26, win = c.duration_hours/24 * 3;
  const ref = (c.bls_t0 !== null && c.bls_t0 !== undefined) ? c.bls_t0 : c.t_center;
  // fold: the stored binned points, folded on the stored BLS period and t0
  {
    const svg = el('svg', {viewBox:`0 0 ${W} ${H}`}), ylo=-1.6*c.depth_ppm, yhi=0.6*c.depth_ppm;
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
  const line = ([name, value, rule, ok, disq, why]) => {
    const g = ok ? 'pass' : (disq ? 'fail' : 'flag');
    return `<tr><td><span class="glyph g-${g}">${GLYPH[g]}</span> ${esc(name)}</td><td>${esc(value)}</td><td>${esc(rule)}</td><td class="why">${esc(why)}</td></tr>`;
  };
  const feed = new Set(['depth cap', 'periodic support']);
  const vetting = rows.filter(r => !feed.has(r[0])).map(line).join('');
  const admission = rows.filter(r => feed.has(r[0])).map(line).join('');
  return `<tr><th colspan="4" class="grp">Vetting checks (light curve only)</th></tr>${vetting}<tr><th colspan="4" class="grp">Feed admission rules (discover.py)</th></tr>${admission}`;
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

let redraw = null;
let resizeTimer = 0;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => redraw && redraw(), 120); });

function scopeNote(c){
  const days = D.subject_days ? `${fmt(D.subject_days,0)}-day` : 'per-subject';
  const eph = c.period_days ? `BLS period ${fmt(c.period_days,3)} d, t0 ${fmt(c.bls_t0,4)}, duration ${fmt((c.bls_duration_days||0)*24,1)} h; ${(c.epochs||[]).length} predicted epochs measured in this subject.` : 'No BLS ephemeris covers this dip.';
  return `Scope: the BLS search and its epochs are per ${days} subject, not per TESS sector. ${eph} Depth and duration are the consensus window's measured values. This is a candidate, unconfirmed.`;
}

function renderDossier(){
  redraw = null;
  const box = $('#dossier');
  const c = D.candidates.find(x => x.candidate_id === state.selected);
  if (!c){ box.innerHTML = '<div class="empty">Choose a candidate from the list. Use j and k to move.</div>'; return; }
  const subj = D.subjects[c.subject_id], marks = D.marks[c.subject_id] || {}, dec = D.decisions[c.subject_id] || {};
  const s = statusOf(c), siblings = D.candidates.filter(x => x.subject_id === c.subject_id && x.candidate_id !== c.candidate_id).length;
  box.innerHTML = `
    <div class="head">
      <div><div class="hint">candidate, unconfirmed · ${esc(c.target)} · ${esc(c.mission)} · subject ${esc(c.subject_id)}</div><h2>${esc(c.candidate_id)}</h2></div>
      <div class="verdict g-${s}">${GLYPH[s]} ${s==='pass' ? 'passed vetting' : s==='flag' ? 'passed, flagged for review' : 'rejected by vetting'}${c.flags.length ? ' · '+esc(c.flags.join(', ')) : ''}</div>
    </div>
    <div class="facts">
      <div><span>mid-time</span>${fmt(c.t_center,3)} ${esc(c.time_unit)}</div>
      <div><span>duration</span>${fmt(c.duration_hours,2)} h</div>
      <div><span>depth</span>${fmt(c.depth_ppm,0)} ppm</div>
      <div><span>SNR</span>${fmt(c.snr,1)}</div>
      <div><span>panel</span>${fmt(c.score,2)} · ${c.n_reviewers} of ${Object.keys(D.reviewers).length}</div>
      <div><span>BLS period</span>${c.period_days ? fmt(c.period_days,3)+' d (this subject)' : 'none'}</div>
      <div><span>BLS t0</span>${(c.bls_t0 !== null && c.bls_t0 !== undefined) ? fmt(c.bls_t0,4) : '–'}</div>
      <div><span>same subject</span>${siblings} other dip${siblings===1?'':'s'}</div>
    </div>
    <section class="sec"><header><h3>Transit strip</h3><em>stored measurements only · nothing is fitted</em></header>
      <div class="hero-wrap strip" id="strip"></div>
      <div class="legend"><span><i class="k-pt"></i>binned flux ±1σ (stored)</span><span><i class="k-box"></i>box model at measured depth and duration</span><span><i class="k-band"></i>consensus window</span><span><i class="k-lane"></i>reviewer marks, one lane each</span></div>
      <p class="scope">${scopeNote(c)}</p></section>
    <section class="sec"><header><h3>Subject in context</h3><em>highlighted: this dip · grey: other dips here</em></header><div class="hero-wrap" id="ctx"></div></section>
    <section class="sec"><header><h3>Comparisons</h3><em>phase fold · stored per-epoch depths · secondary window</em></header><div class="compare" id="cmp"></div></section>
    <section class="sec"><header><h3>Verdict</h3><em>every check, measured value, rule</em></header><div class="scroll"><table class="ledger"><tbody>${ledger(c)}</tbody></table></div></section>
    <section class="sec"><header><h3>Reviewers</h3><em>decisions and reasons, as recorded</em></header><div class="rat">${rationales(c)}</div></section>
    <div class="prov">run ${esc(D.provenance.run_time)} · config ${esc(D.provenance.config_sha256.slice(0,16))} · pipeline ${esc(D.provenance.exoplan_version)} · ${esc(D.provenance.claude_prompt_version || '')}<br>candidate ${esc(c.candidate_id)} · subject ${esc(c.subject_id)}</div>`;
  if (subj){
    const sw = $('#strip');
    strip(c, subj, marks, dec, sw);
    let lastW = sw.clientWidth;
    redraw = () => { if (sw.isConnected && sw.clientWidth !== lastW){ lastW = sw.clientWidth; strip(c, subj, marks, dec, sw); } };
    $('#ctx').appendChild(context(c, subj));
    const cmp = comparisons(c, subj);
    for (const k of ['fold','oddeven','secondary']){ const wrap = document.createElement('div'); wrap.appendChild(cmp[k]); if (k==='fold') wrap.insertAdjacentHTML('beforeend','<p>Every transit folded on the period. A planet repeats at one phase.</p>'); if (k==='oddeven') wrap.insertAdjacentHTML('beforeend','<p>Alternating depths point to a binary at twice the period. Each value is stored by the pipeline at a BLS-predicted epoch.</p>'); if (k==='secondary') wrap.insertAdjacentHTML('beforeend','<p>A dip here would point to an eclipsing binary.</p>'); $('#cmp').appendChild(wrap); }
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


def box_model(row: dict) -> list[list[float]]:
    """Box model at measured depth and duration, as (time, ppm) vertices.

    Zero outside the consensus window, minus the measured depth inside it.
    Nothing is fitted: the edges are the stored ``t_start`` and ``t_end`` and the
    level is the stored ``depth_ppm``.
    """
    t_start, t_end, depth = float(row["t_start"]), float(row["t_end"]), float(row["depth_ppm"])
    return [[t_start, 0.0], [t_start, -depth], [t_end, -depth], [t_end, 0.0]]


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
        row = by_id[c["candidate_id"]]
        c["bls_t0"] = row.get("bls_t0")
        c["bls_duration_days"] = row.get("bls_duration_days")
        c["epochs"] = row.get("epochs") or []
        c["secondary_epochs"] = row.get("secondary_epochs") or []
        c["box"] = box_model(c)
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
        "subject_days": run["manifest"].get("subject_days"),
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

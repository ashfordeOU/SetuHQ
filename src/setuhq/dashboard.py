# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Interactive dashboard: one self-contained HTML file with charts drawn as inline SVG.

The data is embedded as JSON, so the page works offline and needs no build step
or external library. It contains:

* KPI tiles for the run and the discovery feed
* a candidate table with filters, search and sorting
* a detail view per candidate: the blind-coded light curve with every reviewer's
  marked intervals, the consensus interval, and the vetting flags
* a depth-versus-SNR scatter, a score histogram, and a reviewer-by-subject
  agreement matrix
* the discovery timeline and status breakdown, when a discovery catalogue is given

It is drawn in the site's visual system: the report's token sheet (setuhq.design tokens under the report's names, the
light set for print, self-hosted Geist copied beside the page), charts in the status colours (a candidate yellow, a
rejected dip red, the panel's agreement blue), and the shared crosshair (``design.CROSSHAIR_JS``, inline: no renderer)
on the light curve, which answers on hover and on the arrow keys. Each dip is named by its vetting outcome as the
case file decides it (``names.DIP_STATE``): only a dip that passed vetting is a candidate.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from setuhq import brand
from setuhq.design import CROSSHAIR_JS
from setuhq.names import ATTRIBUTION, DIP_STATE
from setuhq.report import FONTS_HREF, _head, _outcomes, _pl

DASHBOARD_CSS = """
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:18px 0}
.toolbar input,.toolbar select{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line-2);border-radius:var(--r-s);padding:8px 12px;min-height:40px}
.toolbar input{flex:1 1 220px}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.tab{cursor:pointer;font:500 13px/1 var(--sans);border:1px solid var(--line-2);background:var(--panel);color:var(--ink-2);padding:0 14px;min-height:36px;border-radius:var(--r-pill);transition:background-color var(--d-1) var(--ease),color var(--d-1) var(--ease)}
.tab[aria-pressed="true"]{color:var(--seg-ink);background:var(--seg-bg);border-color:var(--seg-bg)}
.split{display:grid;gap:16px;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr)}
.split>*,.charts>*{min-width:0}
@media (max-width:900px){.split{grid-template-columns:minmax(0,1fr)}}
.charts{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.chart h3{margin-bottom:2px}
.chart .note{margin:0 0 6px}
.card svg text{fill:var(--ink-3);font:400 11px var(--mono)}
.card svg .axis{stroke:var(--line-2)}
.lcbox{position:relative}
.lcbox svg text{font-size:16px}
#cands td:first-child{font:var(--t-data);overflow-wrap:anywhere}
tr.row{cursor:pointer}
tr.row:hover td{background:var(--panel-2)}
tr.row.sel td{background:color-mix(in srgb,var(--blue) 14%,transparent)}
.pill{display:inline-flex;align-items:center;font:500 12px/1.2 var(--sans);padding:3px 9px;border-radius:var(--r-pill);border:1px solid var(--line-2);color:var(--ink-2);margin:2px 4px 2px 0}
.pill.pass{color:var(--yellow);border-color:var(--yellow)}
.pill.fail{color:var(--red);border-color:var(--red)}
.pill.flag{color:var(--ink-2);border-color:var(--line-3)}
.xhair{position:absolute;top:0;bottom:0;width:1px;background:var(--ink-2);pointer-events:none}
.xhair[hidden]{display:none}
.xread{font:var(--t-data);color:var(--ink-2);min-height:1.4em;margin:4px 0 0}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink-3);margin:6px 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:middle}
.heat td{text-align:center;font-size:12px;padding:6px;color:var(--ink)}
.heat td .note{color:var(--ink-2)}
.empty{color:var(--ink-3);padding:24px;text-align:center}
footer,.note{overflow-wrap:anywhere}
"""

DASHBOARD_JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
// Status colours as the site's tags use them (design.STATUS): a candidate yellow, flagged grey, rejected red.
const C = {pass:'var(--yellow)', fail:'var(--red)', flag:'var(--ink-2)', accent:'var(--blue)', teal:'var(--sen)', muted:'var(--ink-3)'};
const LANES = ['var(--sen)','var(--prb-ink)','var(--green)','var(--amber)','var(--coral)','var(--blue)','var(--yellow)','var(--magenta)'];
const WORD = D.words;  // names.DIP_STATE: {pass: [tag word, phrase], flag: [...], fail: [...]}
const $ = (s, el=document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (x, d=2) => (x === null || x === undefined || Number.isNaN(x)) ? '–' : Number(x).toFixed(d);
const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs={}, parent){ const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
// The dip's vetting outcome as the case file decides it: passed (a candidate), flagged (open) or rejected.
function statusOf(c){ return c.outcome === 'passed' ? 'pass' : c.outcome === 'rejected' ? 'fail' : 'flag'; }

// ---------- KPIs ----------
function renderKpis(){
  const k = D.kpis, wrap = $('#kpis'); wrap.innerHTML = '';
  for (const [v, label, color] of k){
    const d = document.createElement('div'); d.className = 'card stat';
    d.innerHTML = `<span style="${color?`color:${color}`:''}">${esc(v)}</span><small>${esc(label)}</small>`;
    wrap.appendChild(d);
  }
}

// ---------- candidate table ----------
let state = {filter:'all', q:'', sort:'score', selected:null};
function visibleCandidates(){
  let rows = D.candidates.slice();
  if (state.filter !== 'all') rows = rows.filter(c => statusOf(c) === state.filter);
  if (state.q) { const q = state.q.toLowerCase(); rows = rows.filter(c => (c.candidate_id + ' ' + c.reviewers.join(' ') + ' ' + c.flags.join(' ')).toLowerCase().includes(q)); }
  const key = {score:c=>-c.score, snr:c=>-c.snr, depth:c=>-c.depth_ppm, time:c=>c.t_center}[state.sort];
  rows.sort((a,b) => key(a) - key(b));
  return rows;
}
function renderTable(){
  const rows = visibleCandidates(), body = $('#cands tbody');
  body.innerHTML = '';
  if (!rows.length){ body.innerHTML = `<tr><td colspan="7" class="empty">No candidates match this filter.</td></tr>`; return; }
  for (const c of rows){
    const tr = document.createElement('tr'); tr.className = 'row' + (state.selected === c.candidate_id ? ' sel' : '');
    tr.dataset.id = c.candidate_id;
    const st = statusOf(c);
    tr.innerHTML = `<td>${esc(c.candidate_id)}</td>
      <td>${fmt(c.t_center,3)}</td><td>${fmt(c.duration_hours)}</td><td>${fmt(c.depth_ppm,0)}</td>
      <td>${fmt(c.snr,1)}</td><td>${fmt(c.score,2)}</td>
      <td><span class="pill ${st}">${esc(WORD[st][0])}</span></td>`;
    tr.tabIndex = 0; tr.setAttribute('aria-selected', String(state.selected === c.candidate_id));
    const pick = () => { state.selected = c.candidate_id; renderTable(); renderDetail(); };
    tr.addEventListener('click', pick); tr.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); pick(); } });
    body.appendChild(tr);
  }
}

// ---------- light curve with reviewer lanes ----------
function lightcurve(c){
  const subj = D.subjects[c.subject_id];
  const W = 760, H = 420, pad = {l:92, r:14, t:14, b:44}, lanes = Object.keys(D.reviewers).length;
  const svg = el('svg', {viewBox:`0 0 ${W} ${H}`, width:'100%', role:'img', 'aria-label':`Light curve for ${c.candidate_id}`});
  svg.style.display = 'block';
  if (!subj){ svg.appendChild(Object.assign(el('text',{x:10,y:20}), {textContent:'No plot data for this subject.'})); return svg; }
  const x0 = subj.start, x1 = subj.end;
  const ys = subj.flux.slice().sort((a,b)=>a-b);
  const lo = ys[Math.floor(ys.length*0.005)], hi = ys[Math.floor(ys.length*0.995)];
  const span = (hi - lo) || 1e-4, y0 = lo - 0.1*span, y1 = hi + 0.1*span;
  const X = t => pad.l + (t - x0)/(x1 - x0) * (W - pad.l - pad.r);
  // The data range at the svg's own left and right edges (the crosshair maps the element's width to these).
  const per = (x1 - x0) / (W - pad.l - pad.r); svg._x = [x0 - pad.l * per, x1 + pad.r * per];
  const LANE_H = 20, lanesTop = H - pad.b - lanes*LANE_H - 6;
  const Y = f => pad.t + (1 - (f - y0)/(y1 - y0)) * (lanesTop - pad.t - 4);
  // consensus band
  el('rect', {x:X(c.t_start), y:pad.t, width:Math.max(2, X(c.t_end)-X(c.t_start)), height:H-pad.t-pad.b, fill:'var(--accent)', opacity:0.12}, svg);
  // axes
  for (let i=0;i<=4;i++){ const f = y0 + (y1-y0)*i/4, y = Y(f);
    el('line', {x1:pad.l, x2:W-pad.r, y1:y, y2:y, class:'axis'}, svg);
    const tx = el('text', {x:pad.l-6, y:y+4, 'text-anchor':'end'}, svg); tx.textContent = (f).toFixed(4); }
  for (let i=0;i<=4;i++){ const t = x0 + (x1-x0)*i/4, x = X(t);
    const tx = el('text', {x:x, y:H-pad.b+20, 'text-anchor':'middle'}, svg); tx.textContent = t.toFixed(2); }
  const lbl = el('text', {x:W/2, y:H-4, 'text-anchor':'middle'}, svg); lbl.textContent = `time (${subj.time_unit})`;
  // flux path, downsampled to pixels
  let d = '';
  for (let i=0;i<subj.time.length;i++){ d += (i?'L':'M') + X(subj.time[i]).toFixed(1) + ',' + Y(subj.flux[i]).toFixed(1); }
  el('path', {d, fill:'none', stroke:'var(--ink)', 'stroke-width':1, opacity:0.75}, svg);
  // reviewer lanes
  const names = Object.keys(D.reviewers);
  names.forEach((name, li) => {
    const colour = LANES[li % LANES.length], yl = lanesTop + li*LANE_H;
    const lab = el('text', {x:pad.l-6, y:yl+15, 'text-anchor':'end', fill:colour}, svg); lab.textContent = name.length > 9 ? name.slice(0,8)+'…' : name;
    el('line', {x1:pad.l, x2:W-pad.r, y1:yl+LANE_H/2, y2:yl+LANE_H/2, class:'axis', opacity:0.4}, svg);
    for (const m of (D.marks[c.subject_id]?.[name] || [])){
      const w = Math.max(3, X(m[1])-X(m[0]));
      const r = el('rect', {x:X(m[0]), y:yl+2, width:w, height:LANE_H-4, rx:3, fill:colour, opacity:0.9}, svg);
      el('title', {}, r).textContent = `${name}: ${fmt(m[0],3)} to ${fmt(m[1],3)}`;
    }
  });
  // consensus edges
  for (const t of [c.t_start, c.t_end]) el('line', {x1:X(t), x2:X(t), y1:pad.t, y2:H-pad.b, stroke:'var(--accent)', 'stroke-dasharray':'3 3'}, svg);
  return svg;
}

function renderDetail(){
  const box = $('#detail');
  const c = D.candidates.find(x => x.candidate_id === state.selected);
  if (!c){ box.innerHTML = `<div class="empty">Select a candidate to see its light curve, the panel's marks and the vetting decision.</div>`; return; }
  const st = statusOf(c);
  box.innerHTML = `
    <h3>${esc(c.candidate_id)}</h3>
    <span class="pill ${st}">${esc(WORD[st][1])}</span>
    ${(c.flags||[]).map(f=>`<span class="pill">${esc(f.replace(/_/g, ' '))}</span>`).join('')}
    <div class="legend" id="lg"></div>
    <div id="lc" class="lcbox"></div>
    <div class="kv" style="margin-top:12px">
      <div>Mid-time</div><div>${fmt(c.t_center,3)} ${esc(c.time_unit)}</div>
      <div>Duration</div><div>${fmt(c.duration_hours)} h</div>
      <div>Depth</div><div>${fmt(c.depth_ppm,0)} ppm</div>
      <div>SNR</div><div>${fmt(c.snr,1)}</div>
      <div>Panel score</div><div>${fmt(c.score,2)} (${c.n_reviewers} reviewers marked it)</div>
      <div>Says planet</div><div>${fmt(c.planet_fraction*100,0)}% of weighted panel</div>
      <div>Periodic hint</div><div>${c.period_days ? fmt(c.period_days,3)+' d, '+c.n_transits+' transits' : 'none'}</div>
    </div>`;
  const lg = $('#lg', box);
  lg.innerHTML = `<span><i style="background:var(--accent);opacity:.35"></i>consensus interval</span>` +
    Object.keys(D.reviewers).map((n,li)=>`<span><i style="background:${LANES[li%LANES.length]}"></i>${esc(n)}</span>`).join('');
  const lc = lightcurve(c); $('#lc', box).appendChild(lc);
  // S06: the light curve answers on hover and on the arrow keys (design.CROSSHAIR_JS), with the time and flux read.
  const subj = D.subjects[c.subject_id];
  if (subj && lc._x){ const step = Math.max(1, Math.floor(subj.time.length / 400)), idx = [];
    for (let i = 0; i < subj.time.length; i += step) idx.push(i);
    lc.setAttribute('aria-label', `Light curve for ${c.candidate_id}; arrow keys move a readout along it`);
    SetuUI.crosshair(lc, {x0: lc._x[0], x1: lc._x[1], xs: idx.map(i => subj.time[i]),
      fmt: k => `${subj.time_unit} ${fmt(subj.time[idx[k]], 3)} · flux ${fmt(subj.flux[idx[k]], 5)}`}); }
  const rv = D.marks[c.subject_id] || {};
  const rows = Object.keys(D.reviewers).map(n => {
    const info = (D.reviewerDecisions[c.subject_id] || {})[n];
    if (!info) return '';
    return `<tr><td>${esc(n)}</td><td>${esc(info.label.replace(/_/g,' '))}</td><td>${(rv[n]||[]).length}</td><td class="note">${esc(info.rationale||'')}</td></tr>`;
  }).join('');
  box.insertAdjacentHTML('beforeend', `<h3 style="margin-top:16px">Panel decisions for this subject</h3>
    <div class="scroll" tabindex="0" role="region" aria-label="Panel decisions for this subject"><table><thead><tr><th>reviewer</th><th>label</th><th>marks</th><th>rationale</th></tr></thead><tbody>${rows}</tbody></table></div>`);
}

// ---------- charts ----------
function scatter(){
  const W=560,H=300,pad={l:50,r:14,t:12,b:34}, box=$('#c-scatter'); box.innerHTML='';
  const pts = D.candidates; if (!pts.length){ box.innerHTML='<div class="empty">No candidates yet.</div>'; return; }
  const sx=Math.max(...pts.map(p=>p.snr))*1.05;
  const dmin=Math.min(...pts.map(p=>p.depth_ppm))*0.8, dmax=Math.max(...pts.map(p=>p.depth_ppm))*1.2;
  const lo=Math.log10(dmin), hi=Math.log10(dmax);
  const X=v=>pad.l+v/sx*(W-pad.l-pad.r), Y=v=>pad.t+(1-(Math.log10(v)-lo)/(hi-lo))*(H-pad.t-pad.b);
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,width:'100%'},box);
  for(let i=0;i<=4;i++){ const yv=Math.pow(10, lo+(hi-lo)*i/4), xv=sx*i/4;
    el('line',{x1:pad.l,x2:W-pad.r,y1:Y(yv),y2:Y(yv),class:'axis'},svg);
    el('text',{x:pad.l-6,y:Y(yv)+4,'text-anchor':'end'},svg).textContent=Math.round(yv);
    el('text',{x:X(xv),y:H-pad.b+16,'text-anchor':'middle'},svg).textContent=xv.toFixed(0); }
  el('text',{x:W/2,y:H-4,'text-anchor':'middle'},svg).textContent='SNR';
  el('text',{x:12,y:H/2,transform:`rotate(-90 12 ${H/2})`,'text-anchor':'middle'},svg).textContent='depth (ppm, log)';
  for(const p of pts){ const s=statusOf(p);
    const c=el('circle',{cx:X(p.snr),cy:Y(p.depth_ppm),r:6,fill:C[s],opacity:.8,stroke:'var(--panel)','stroke-width':1.5,style:'cursor:pointer'},svg);
    const t=el('title',{},c); t.textContent=`${p.candidate_id}: ${fmt(p.depth_ppm,0)} ppm, SNR ${fmt(p.snr,1)}`;
    c.addEventListener('click',()=>{state.selected=p.candidate_id;renderTable();renderDetail();}); }
}
function histogram(){
  const W=560,H=260,pad={l:40,r:14,t:12,b:34}, box=$('#c-hist'); box.innerHTML='';
  const bins=10, counts=Array(bins).fill(0);
  for(const p of D.candidates){ counts[Math.min(bins-1, Math.floor(p.score*bins))]++; }
  const m=Math.max(1,...counts), svg=el('svg',{viewBox:`0 0 ${W} ${H}`,width:'100%'},box);
  const bw=(W-pad.l-pad.r)/bins;
  counts.forEach((n,i)=>{ const h=(H-pad.t-pad.b)*n/m, x=pad.l+i*bw;
    el('rect',{x:x+3,y:H-pad.b-h,width:bw-6,height:h,rx:4,fill:'var(--accent)',opacity:.85},svg);
    if(n) el('text',{x:x+bw/2,y:H-pad.b-h-4,'text-anchor':'middle'},svg).textContent=n;
    el('text',{x:x+bw/2,y:H-pad.b+16,'text-anchor':'middle'},svg).textContent=(i/bins).toFixed(1); });
  el('text',{x:W/2,y:H-4,'text-anchor':'middle'},svg).textContent='consensus score';
}
function agreement(){
  const box=$('#c-agree'); box.innerHTML='';
  const names=Object.keys(D.reviewers), subs=Object.keys(D.reviewerDecisions);
  if(!subs.length){ box.innerHTML='<div class="empty">No subjects reviewed.</div>'; return; }
  let html='<div class="scroll" tabindex="0" role="region" aria-label="Reviewer agreement by subject"><table class="heat"><thead><tr><th>subject</th>'+names.map(n=>`<th>${esc(n)}</th>`).join('')+'</tr></thead><tbody>';
  for(const s of subs){
    html+=`<tr><td style="text-align:left">${esc(s)}</td>`;
    for(const n of names){ const info=(D.reviewerDecisions[s]||{})[n]; const k=(D.marks[s]||{})[n]||[];
      if(!info){ html+='<td>–</td>'; continue; }
      const planet=info.label==='potential_planet';
      const bg=planet?'color-mix(in srgb,var(--green) '+(k.length?'26':'12')+'%,transparent)':'color-mix(in srgb,var(--red) 14%,transparent)';
      html+=`<td style="background:${bg}">${planet?'planet':'noise'}<br><span class="note">${k.length} marks</span></td>`; }
    html+='</tr>'; }
  box.innerHTML=html+'</tbody></table></div>';
}

// ---------- discovery feed ----------
function discovery(){
  const F = D.discovery; if (!F){ $('#disc').style.display='none'; return; }
  const box=$('#c-timeline'); box.innerHTML='';
  const W=560,H=260,pad={l:46,r:14,t:12,b:34};
  const rows=F.candidates; if(!rows.length){ box.innerHTML='<div class="empty">No feed entries yet.</div>'; }
  else {
    const tmin=Math.min(...rows.map(r=>r.t_center)), tmax=Math.max(...rows.map(r=>r.t_center));
    const tics=[...new Set(rows.map(r=>r.tic))].sort((a,b)=>a-b), ti=new Map(tics.map((t,i)=>[t,i]));
    const X=t=>pad.l+(t-tmin)/((tmax-tmin)||1)*(W-pad.l-pad.r), Y=tic=>pad.t+ti.get(tic)/Math.max(1,tics.length-1)*(H-pad.t-pad.b);
    const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,width:'100%'},box);
    tics.forEach(t=>{ el('line',{x1:pad.l,x2:W-pad.r,y1:Y(t),y2:Y(t),class:'axis'},svg); el('text',{x:pad.l-6,y:Y(t)+4,'text-anchor':'end'},svg).textContent=t; });
    for(const r of rows){ const c=el('circle',{cx:X(r.t_center),cy:Y(r.tic),r:Math.max(4,Math.min(12,Math.sqrt(r.snr)*1.6)),fill:r.status==='new_candidate'?'var(--yellow)':'var(--blue)',opacity:.85},svg);
      el('title',{},c).textContent=`TIC ${r.tic} at ${fmt(r.t_center,2)} BTJD, SNR ${fmt(r.snr,1)}, ${r.status}`; }
    el('text',{x:W/2,y:H-4,'text-anchor':'middle'},svg).textContent='mid-time (BTJD); yellow: new candidate, blue: known TOI';
  }
  const bs=$('#c-status'); bs.innerHTML='';
  const groups=[['new candidate (unconfirmed)',F.candidates.filter(r=>r.status==='new_candidate').length,'var(--yellow)'],['known TOI match',F.candidates.filter(r=>r.status==='known_toi').length,'var(--blue)']];
  const total=Math.max(1,groups.reduce((a,g)=>a+g[1],0));
  bs.innerHTML = groups.map(([l,n,c])=>`<div style="margin:8px 0"><div style="display:flex;justify-content:space-between"><span>${l}</span><span>${n}</span></div><div class="bar"><i style="width:${(n/total*100).toFixed(0)}%;background:${c}"></i></div></div>`).join('') +
    `<p class="note">${F.targets_reviewed} target${F.targets_reviewed === 1 ? "" : "s"} reviewed in total. Every entry is an unconfirmed candidate.</p>`;
}

// ---------- wiring ----------
function setup(){
  renderKpis();
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x=>x.setAttribute('aria-pressed', 'false')); t.setAttribute('aria-pressed', 'true');
    state.filter = t.dataset.f; renderTable(); }));
  $('#q').addEventListener('input', e => { state.q = e.target.value; renderTable(); });
  $('#sort').addEventListener('change', e => { state.sort = e.target.value; renderTable(); });
  renderTable(); renderDetail(); scatter(); histogram(); agreement(); discovery();
  const first = visibleCandidates()[0]; if (first){ state.selected = first.candidate_id; renderTable(); renderDetail(); }
}
setup();
"""


def _load_run(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    candidates = []
    for row in json.loads((run_dir / "candidates.json").read_text()):
        candidates.append(
            {
                "candidate_id": row["candidate_id"],
                "subject_id": row["subject_id"],
                "t_start": float(row["t_start"]),
                "t_end": float(row["t_end"]),
                "t_center": float(row["t_center"]),
                "time_unit": row["time_unit"],
                "duration_hours": float(row["duration_hours"]),
                "depth_ppm": float(row["depth_ppm"]),
                "snr": float(row["snr"]),
                "score": float(row["score"]),
                "n_reviewers": int(row["n_reviewers"]),
                "planet_fraction": float(row["planet_fraction"]),
                "reviewers": [r for r in row["reviewers"].split(";") if r],
                "passed": row["passed"] in (True, "True"),
                "flags": [f for f in row["flags"].split(";") if f],
                "period_days": float(row["period_days"]) if row.get("period_days") else None,
                "n_transits": int(row.get("n_transits") or 0),
            }
        )
    subjects, marks, decisions = {}, {}, {}
    for path in (run_dir / "subjects").glob("*.json"):
        subjects[path.stem] = json.loads(path.read_text())
    with (run_dir / "classifications.csv").open() as handle:
        for row in csv.DictReader(handle):
            subject = row["subject_ids"]
            annotations = json.loads(row["annotations"])
            metadata = json.loads(row["metadata"])
            reviewer = row["user_name"]
            spans = [[m["t_start"], m["t_end"]] for m in annotations[0]["value"]]
            marks.setdefault(subject, {})[reviewer] = spans
            decisions.setdefault(subject, {})[reviewer] = {
                "label": row["label"],
                "rationale": (metadata.get("rationale") or "")[:300],
            }
    reviewers = {r["id"]: r["kind"] for r in manifest.get("reviewers", [])}
    return {"manifest": manifest, "candidates": candidates, "subjects": subjects, "marks": marks,
            "reviewerDecisions": decisions, "reviewers": reviewers}


def _load_discovery(catalog_path: Path | None) -> dict | None:
    if catalog_path is None or not catalog_path.exists():
        return None
    catalog = json.loads(catalog_path.read_text())
    return {
        "candidates": [
            {"tic": r["tic"], "t_center": r["t_center"], "snr": r["snr"], "status": r["status"],
             "period_days": r["period_days"], "found": r["found"]}
            for r in catalog.get("candidates", [])
        ],
        "targets_reviewed": catalog.get("targets_reviewed", 0),
        "updated": catalog.get("updated", "never"),
    }


def build_dashboard(run_dir: str | Path, out_dir: str | Path, *, title: str, catalog_path: str | Path | None = None) -> Path:
    import html as _html

    run = _load_run(Path(run_dir))
    rows = [{"candidate_id": c["candidate_id"], "passed": "True" if c["passed"] else "False"} for c in run["candidates"]]
    outcome, _star = _outcomes(Path(run_dir), rows)
    for c in run["candidates"]:
        c["outcome"] = outcome.get(c["candidate_id"]) or ("passed" if c["passed"] else "rejected")
    discovery = _load_discovery(Path(catalog_path) if catalog_path else None)
    n_cand = sum(c["outcome"] == "passed" for c in run["candidates"])
    counts = run["manifest"]["counts"]
    kpis = [
        [str(counts["light_curves"]), _pl(counts["light_curves"], "light curve"), None],
        [str(counts["subjects"]), "blind-coded " + _pl(counts["subjects"], "subject"), None],
        [str(counts["classifications"]), "independent " + _pl(counts["classifications"], "review"), None],
        [str(len(run["candidates"])), _pl(len(run["candidates"]), "dip") + " the panel agreed on", None],
        [str(n_cand), _pl(n_cand, "candidate") + " (passed vetting, unconfirmed)", "var(--yellow)"],
    ]
    if discovery:
        kpis.append([str(sum(1 for r in discovery["candidates"] if r["status"] == "new_candidate")),
                     "new feed candidates (no TOI match)", "var(--yellow)"])
    words = {"pass": DIP_STATE["passed"][1:], "flag": DIP_STATE["flagged"][1:], "fail": DIP_STATE["rejected"][1:]}
    data = {**run, "kpis": kpis, "discovery": discovery, "words": words}
    data.pop("manifest")
    payload = json.dumps(data).replace("</", "<\\/")
    t = _html.escape(title)

    body = f"""
<header class='hero'><div class='wrap'>
 <div class='stage herostage' style='grid-template-columns:minmax(0,1fr)'><div>
  <a href="/" aria-label="SetuHQ, home">{brand.logo(themed=False, height=24)}</a>
  <p class='kick'>Dashboard · {_html.escape(run["manifest"].get("config_name") or Path(run_dir).name)}</p>
  <h1>{t}</h1>
  <p class='lead'>Blind-coded light curves, a panel of Sentinels (AI reviewers) and Probes (deterministic detectors), skill-weighted consensus, and vetting. Select a dip to see its light curve and each reviewer's marks. Only a dip that passed vetting is a candidate, and a candidate is unconfirmed.</p>
 </div></div>
</div></header>
<main class='wrap'>
<section class='grid' id='kpis' style='margin-top:24px' aria-label='The run in numbers'></section>

<div class='toolbar'>
  <div class='tabs' role='group' aria-label='Show'>
    <button class='tab' type='button' data-f='all' aria-pressed='true'>all</button>
    <button class='tab' type='button' data-f='pass' aria-pressed='false'>candidates</button>
    <button class='tab' type='button' data-f='flag' aria-pressed='false'>flagged</button>
    <button class='tab' type='button' data-f='fail' aria-pressed='false'>rejected</button>
  </div>
  <input id='q' type='search' placeholder='search dip, reviewer or flag' aria-label='Search dip, reviewer or flag'>
  <select id='sort' aria-label='Sort by'>
    <option value='score'>sort: panel score</option>
    <option value='snr'>sort: SNR</option>
    <option value='depth'>sort: depth</option>
    <option value='time'>sort: mid-time</option>
  </select>
</div>

<section class='split'>
  <div class='card'>
    <div class='scroll' style='border:none;padding:0' tabindex='0' role='region' aria-label='Dips'>
      <table id='cands'><thead><tr><th>dip</th><th>mid-time</th><th>dur h</th><th>ppm</th><th>SNR</th><th>score</th><th>status</th></tr></thead><tbody></tbody></table>
    </div>
  </div>
  <div class='card' id='detail'></div>
</section>

<section class='charts' style='margin-top:20px'>
  <div class='card chart'><h3>Depth versus SNR</h3><p class='note'>Colour is the vetting outcome: yellow a candidate, grey flagged, red rejected. Click a point to open the dip.</p><div id='c-scatter'></div></div>
  <div class='card chart'><h3>Panel score distribution</h3><p class='note'>How strongly the weighted panel agrees on each dip.</p><div id='c-hist'></div></div>
  <div class='card chart'><h3>Reviewer agreement</h3><p class='note'>Each reviewer's label and mark count, per subject.</p><div id='c-agree'></div></div>
</section>

<section id='disc' style='margin-top:28px'>
  <h2>Search feed</h2>
  <p class='note'>Candidates from scheduled batches of TESS targets. Unconfirmed: a candidate is a dip that passed the pipeline's vetting, not a confirmed planet.</p>
  <div class='charts'>
    <div class='card chart'><h3>Feed timeline</h3><div id='c-timeline'></div></div>
    <div class='card chart'><h3>Status</h3><div id='c-status'></div></div>
  </div>
</section>
<footer>{_html.escape(ATTRIBUTION)} Generated by SetuHQ. Results on synthetic data are not claims about real sky data.</footer>
</main>
<script id='data' type='application/json'>{payload}</script>
<script>window.SetuUI = window.SetuUI || {{}};{CROSSHAIR_JS}</script>
<script>{DASHBOARD_JS}</script>
"""
    head = _head(title, "SetuHQ's dashboard of the stored run: light curves, every reviewer's marks and the panel's agreement. Candidates, never confirmations.",
                 brand.page_path(out_dir), FONTS_HREF)
    head = head.replace("</style></head>", DASHBOARD_CSS + "</style></head>", 1)
    html_text = f"{head}\n<body>{body}</body></html>\n"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    from setuhq.codenote import code_note, with_code_note
    from setuhq.docket import copy_page_fonts

    note = code_note(run_dir)
    if not note and catalog_path and Path(catalog_path).exists():
        note = json.loads(Path(catalog_path).read_text()).get("code_note")
    path = out / "index.html"
    path.write_text(with_code_note(html_text, note))
    copy_page_fonts(out)
    brand.copy_assets(out)
    return path

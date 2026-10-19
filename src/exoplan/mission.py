"""Mission Control (#/mission): a tiling workspace of exoplan's own views, linked by one selected star.

Panes: the Galaxy (the live map itself, moved into its pane while Mission Control is open), the star's
sky position, the run's light curve, a catalogue slice, the shared system view and the Sentinel feed.
Selecting a star in any pane selects it in all of them, including panes popped out into their own windows
(kept in step over BroadcastChannel). The layout is in the URL and can be saved as this browser's default.
Every number on the telemetry strip is computed from the stored data on the page; nothing is simulated.
On a phone the panes become a stacked list.
"""

from __future__ import annotations

import html

from exoplan.methods import system_stage

PANES = [("galaxy", "Galaxy"), ("sky", "Sky position"), ("lc", "Light curve"), ("cat", "Catalogue"),
         ("sys", "System view"), ("feed", "Sentinel feed")]
GRIDS = [("focus", "Main and side"), ("tile", "Tiles")]
MISSION_KEY = "exoplan-mission"


def mission_section(eyebrow: str) -> str:
    e = html.escape
    panes = "".join(
        f'<section class="mcpane" id="mcp-{pid}" data-pane="{pid}" tabindex="-1" aria-labelledby="mch-{pid}">'
        f'<header class="mchead" draggable="true"><h2 id="mch-{pid}"><span class="mcnum mono" aria-hidden="true"></span>{e(label)}</h2>'
        f'<div class="mctools" role="group" aria-label="{e(label)} pane">'
        f'<button class="btn mcbtn" type="button" data-mc="prev" aria-label="Move {e(label)} earlier">‹</button>'
        f'<button class="btn mcbtn" type="button" data-mc="next" aria-label="Move {e(label)} later">›</button>'
        f'<button class="btn mcbtn" type="button" data-mc="focus" aria-label="Make {e(label)} the main pane">Main</button>'
        f'<button class="btn mcbtn mcpopbtn" type="button" data-mc="pop" aria-label="Open {e(label)} in its own window">Pop out</button>'
        f'<button class="btn mcbtn" type="button" data-mc="hide" aria-label="Hide {e(label)}">Hide</button></div></header>'
        f'<div class="mcbody" id="mcb-{pid}">{_pane_body(pid)}</div>'
        f'<p class="mcpopped" hidden>Open in its own window. <button class="btn" type="button" data-mc="back">Bring it back</button></p></section>'
        for pid, label in PANES)
    grids = "".join(f'<button class="btn" type="button" data-mcgrid="{k}" aria-pressed="false">{e(v)}</button>' for k, v in GRIDS)
    return f"""<header class="headrow mchero">
        <div>{eyebrow}<h1 class="lead-h" id="h-mission" tabindex="-1">Mission Control.</h1>
        <p>exoplan's views side by side, linked: pick a star in any pane and every pane follows. Drag a pane's title bar onto another to swap them, or use its arrow buttons (Alt+← and Alt+→ move the focused pane); pop a pane out into its own window and it stays in step. F6 moves between panes; Alt+1 to Alt+6 (or Ctrl+Alt+1 to 6, where Alt+number switches browser tabs) jumps to one.</p></div>
      </header>
      <div class="mctele mono" id="mctele"></div>
      <div class="mctoolbar" role="toolbar" aria-label="Layout">
        <div class="segctl" role="group" aria-label="Arrangement">{grids}</div>
        <div class="mchidden" id="mchidden"></div>
        <button class="btn" type="button" id="mcsave">Save as my default</button>
        <button class="btn" type="button" id="mccopy">Copy link to this layout</button>
        <button class="btn" type="button" id="mcreset">Reset</button>
      </div>
      <div class="mcgrid" id="mcgrid" data-grid="focus">{panes}</div>
      <p class="small">Every figure here is computed from the data on this page (the catalogue, the map, the run and the feed); nothing is simulated. exoplan has reviewed one star's light curve, so the light-curve pane is empty for other stars and says so.</p>"""


def _pane_body(pid: str) -> str:
    if pid == "galaxy":
        return '<p class="mcnote" id="mcgxnote" role="status"></p>'
    if pid == "sky":
        return '<div id="mcsky"></div>'
    if pid == "lc":
        return '<div class="mccap" id="mclccap"></div><div id="mclc"></div><p class="mcnote" id="mclcnote"></p>'
    if pid == "cat":
        return ('<label class="mcfind"><span class="sr">Find a star</span><input type="search" id="mcq" placeholder="Find a star" autocomplete="off"></label>'
                '<ul class="mcfound" id="mcfound"></ul><div id="mccat"></div>')
    if pid == "sys":
        return ('<p class="mcnote" id="mcsysnote" hidden></p><label class="mcpick"><span>Planet</span><select id="mcsyspick"></select></label>'
                + system_stage("mcsys", "The selected planet and its star, drawn from stored values."))
    if pid == "feed":
        return '<p class="mcnote" id="mcfeednote"></p><div id="mcfeed"></div>'
    return ""


MISSION_CSS = r"""
/* ---------- Mission Control ---------- */
#route-mission{grid-template-columns:minmax(0,1fr)}
#route-mission>*{min-width:0}
.mctele{display:flex;flex-wrap:wrap;gap:6px 18px;padding:10px 14px;border:1px solid var(--line);border-radius:14px;background:var(--glass-2);font-size:12px;color:var(--ink-2)}
.mctele b{color:var(--ink);font-weight:600}
.mctoolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.mctoolbar .btn{min-height:44px}
.mchidden{display:flex;flex-wrap:wrap;gap:6px}
.mcgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:400px;gap:12px}
.mcgrid[data-grid="focus"] .mcpane:first-child{grid-column:span 2;grid-row:span 2}
.mcpane{display:flex;flex-direction:column;min-width:0;min-height:0;border:1px solid var(--line-2);border-radius:18px;background:var(--glass-2);overflow:hidden}
.mcpane[hidden]{display:none}
.mcpane:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
.mcpane.drop{outline:2px dashed var(--blue);outline-offset:-4px}
.mchead{display:flex;align-items:center;justify-content:space-between;gap:6px;padding:4px 4px 4px 12px;border-bottom:1px solid var(--line);cursor:grab}
.mchead h2{margin:0;font-size:14px;display:flex;align-items:center;gap:8px;min-width:0;white-space:nowrap;overflow:hidden}
.mcnum{font-size:11px;color:var(--ink-3)}
.mctools{display:flex;gap:2px;flex:none}
.mcbtn{min-height:44px;min-width:44px;padding:0 10px;font-size:12px}
.mcbody{flex:1;min-height:0;overflow:auto;padding:10px 12px;display:flex;flex-direction:column;gap:8px}
.mcbody[hidden]{display:none}
.mcpane[data-pane="galaxy"] .mcbody{padding:0;overflow:hidden;position:relative}
.mcpane .gxstage{height:100%;min-height:0;border-radius:0;flex:1}
.mcpane[data-pane="galaxy"] .mcnote{position:absolute;right:10px;bottom:10px;z-index:7;margin:0;max-width:calc(100% - 20px);padding:6px 10px;border-radius:12px;background:rgba(18,18,20,.85);color:#F5F5F7;font-size:12px}
.mcpane[data-pane="galaxy"] .mcnote:empty{display:none}
.mcpane .mxstage{margin:0}
.mcpane .mxstage .mxcanvas{min-height:220px}
.mcnote{margin:0;font-size:12.5px;color:var(--ink-3)}
.mccap{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 10px;font-size:11px;color:var(--ink-3)}
.mccap:empty{display:none}
.mcpopped{margin:auto;padding:16px;text-align:center;color:var(--ink-2);font-size:13px}
.mcpopped[hidden]{display:none}
.mcpick[hidden],.mcpane .mxstage[hidden],.mcnote[hidden]{display:none}
.mcpopped .btn{min-height:44px;margin-top:8px}
.mcfind input{width:100%;min-height:44px;padding:0 12px;border-radius:12px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 14px var(--sans)}
.mcfound{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.mcfound button,.mccat button{min-height:44px}
.mccat{display:grid;gap:4px}
.mcpick{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)}
.mcpick select{min-height:44px;padding:0 10px;border-radius:12px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);max-width:100%}
.mcpane .feedcards{margin:0;display:grid;gap:8px}
.mcsel{color:var(--ink);font-weight:600}
/* A popped-out window: only its pane, full size. */
body.mcpop .topbar,body.mcpop .skip,body.mcpop .mchero,body.mcpop .mctoolbar,body.mcpop .mctele,body.mcpop #route-mission>.small,body.mcpop .learnbar{display:none}
body.mcpop main{padding:8px}
body.mcpop .mcgrid,body.mcpop .mcgrid[data-grid="focus"]{grid-template-columns:minmax(0,1fr);grid-auto-rows:calc(100vh - 16px)}
body.mcpop .mcpane,body.mcpop .mcgrid[data-grid="focus"] .mcpane:first-child{grid-column:auto;grid-row:auto}
body.mcpop .mctools .btn:not([data-mc="close"]){display:none}
@media (max-width:999.98px){.mcgrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
/* Phone: a stacked list, one pane after another; no pop-out windows. */
@media (max-width:699.98px){
  .mcgrid,.mcgrid[data-grid="focus"]{grid-template-columns:minmax(0,1fr);grid-auto-rows:auto}
  .mcgrid[data-grid="focus"] .mcpane:first-child{grid-column:auto;grid-row:auto}
  .mcpane{min-height:0}
  .mcpane[data-pane="galaxy"] .mcbody{height:380px;flex:none}
  .mcbody{max-height:none;overflow:visible}
  .mchead{cursor:default}
  .mcpopbtn,[data-mc="focus"]{display:none}
}
"""


MISSION_JS = r"""
// ---------- Mission Control: tiling panes linked by one selected star ----------
const MC_PANES = D.mission ? D.mission.panes.map(p => p[0]) : [];
const MC_LABEL = D.mission ? Object.fromEntries(D.mission.panes) : {};
const MC_GRIDS = D.mission ? D.mission.grids.map(g => g[0]) : [];
const MC_KEY = 'exoplan-mission';
const mc = {star: D.story.star.name || null, sys: null, layout: null, mounted: false, popped: new Set(), pop: null, win: Math.random().toString(36).slice(2)};
function mcDefault(){ return {panes: MC_PANES.slice(), hidden: [], grid: 'focus'}; }
function mcClean(v){
  const panes = (v && Array.isArray(v.panes) ? v.panes : []).filter((p, i, a) => MC_PANES.includes(p) && a.indexOf(p) === i);
  for (const p of MC_PANES) if (!panes.includes(p)) panes.push(p);
  const hidden = (v && Array.isArray(v.hidden) ? v.hidden : []).filter(p => MC_PANES.includes(p));
  return {panes, hidden: hidden.length === MC_PANES.length ? [] : hidden, grid: v && MC_GRIDS.includes(v.grid) ? v.grid : 'focus'};
}
function mcRead(){ try { const s = getStorage(), raw = s && s.getItem(MC_KEY); if (raw) return mcClean(JSON.parse(raw)); } catch (e) { /* blocked or malformed */ } return null; }
// URL: panes (order), hide, grid, star; pop=<pane> for a popped-out window. Defaults are left out.
function decodeMission(p){
  const has = p.has('panes') || p.has('hide') || p.has('grid');
  const v = has ? mcClean({panes: (p.get('panes') || '').split(','), hidden: (p.get('hide') || '').split(','), grid: p.get('grid')}) : (mcRead() || mcDefault());
  v.star = (p.get('star') || '').slice(0, 120) || null; v.pop = MC_PANES.includes(p.get('pop')) ? p.get('pop') : null;
  return v;
}
function encodeMission(v){
  const d = mcDefault(), out = [];
  if (v.panes.join(',') !== d.panes.join(',')) out.push('panes=' + v.panes.join(','));
  if (v.hidden.length) out.push('hide=' + v.hidden.join(','));
  if (v.grid !== 'focus') out.push('grid=' + v.grid);
  if (mc.star && mc.star !== D.story.star.name) out.push('star=' + encodeURIComponent(mc.star));
  if (v.pop) out.push('pop=' + v.pop);
  return out.join('&');
}
function syncMissionURL(push){ if (current === 'mission' && mc.layout) setHash('#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : ''), !!push); }

// ---------- linked selection: one star, every pane, every window ----------
let mcBC = null;
try { if ('BroadcastChannel' in window) mcBC = new BroadcastChannel('exoplan-mission'); } catch (e) { mcBC = null; }
function mcBrush(star, src, remote){
  if (!star || star === mc.star && src !== 'init') return;
  mc.star = star; mc.sys = null;
  if (current === 'mission') mcRenderPanes(src);
  if (!remote && mcBC) try { mcBC.postMessage({t: 'select', star, from: mc.win}); } catch (e) { /* closed */ }
  if (current === 'mission') syncMissionURL(false);
}
if (mcBC) mcBC.onmessage = e => {
  const m = e.data || {}; if (m.from === mc.win) return;
  if (m.t === 'select') mcBrush(m.star, 'remote', true);
  if (m.t === 'hello' && !mc.pop && mcBC) mcBC.postMessage({t: 'select', star: mc.star, from: mc.win});
  if (m.t === 'close' && mc.pop === m.pane) window.close();
  if (m.t === 'popped' && !mc.pop){ if (m.open) mc.popped.add(m.pane); else mc.popped.delete(m.pane);
    // A pane coming back from its window is redrawn for the star selected now, not the one it left with.
    if (current === 'mission'){ mcLayout(); if (!m.open && MC_RENDER[m.pane]) (CTM ? ctLoad() : Promise.resolve()).then(() => MC_RENDER[m.pane]()); } }
};

// ---------- the panes ----------
function mcStarPlanets(star){ return ct.P && ct.byStar[star] ? ct.byStar[star].slice().sort((a, b) => (ct.P.period[a] ?? 1e99) - (ct.P.period[b] ?? 1e99)) : []; }
function mcTele(){
  const P = ct.P, s = mc.star, ps = mcStarPlanets(s), i = ps[0], bits = [];
  if (CTM) bits.push(`<span>Catalogue <b>${CTM.counts.rows.toLocaleString('en-GB')}</b> planets · <b>${CTM.counts.stars.toLocaleString('en-GB')}</b> stars (${esc(CTM.source_short)}, ${esc(CTM.fetched_at.slice(0, 10))})</span>`);
  if (GXM) bits.push(`<span>Map <b>${GXM.n_planets.toLocaleString('en-GB')}</b> planets placed</span>`);
  bits.push(`<span>Run ${esc(D.run.name)} · <b>${D.story.dips.length}</b> dips</span>`, `<span>Feed <b>${D.catalog.candidates.length}</b> entries</span>`);
  if (s) bits.push(`<span>Selected <b class="mcsel">${esc(s)}</b>${P && i !== undefined ? ` · ${ps.length} planet${ps.length === 1 ? '' : 's'}${P.dist[i] !== null ? ` · ${ctFmt(P.dist[i], 4)} pc` : ' · distance not stored'}${P.steff[i] !== null ? ` · ${Math.round(P.steff[i]).toLocaleString('en-GB')} K` : ''}` : ''}</span>`);
  $('#mctele').innerHTML = bits.join('');
}
const MC_RENDER = {
  galaxy(){
    const note = $('#mcgxnote'); if (!GXM){ note.textContent = 'The map is not in this build.'; return; }
    if (!rendered.has('galaxy')){ renderGalaxy(); rendered.add('galaxy'); }
    const home = $('#mcb-galaxy'), st = $('#gxstage');
    if (st && st.parentNode !== home){ if (!$('#gxhome')){ const ph = document.createElement('div'); ph.id = 'gxhome'; ph.hidden = true; st.before(ph); } home.prepend(st); }
    gxLoad().then(() => { const go = () => { if (!gx.ready) return setTimeout(go, 100); gxResize(); const h = gx.G.hosts.n.indexOf(mc.star);
      note.textContent = h < 0 ? `${mc.star} is not on the map (no stored distance).` : '';
      if (h >= 0 && gx.sel !== h){ gxSelect(h); gxFly(Object.assign(gxHostCam(h), {dist: 140}), 1600); } }; go(); }).catch(() => { note.textContent = 'The map data could not be loaded here.'; });
  },
  sky(){
    const box = $('#mcsky'), ps = mcStarPlanets(mc.star);
    box.innerHTML = ps.length ? ctSky(ps[0], mc.star) + `<div class="pllinks">${objLink('star', mc.star, mc.star + ' ›')}</div>` : `<p class="mcnote">${esc(mc.star)} is not in the catalogue.</p>`;
  },
  lc(){
    const own = mc.star === D.story.star.name;
    $('#mclcnote').textContent = own ? `The run's stored light curve of ${D.story.star.name} (${D.story.star.target}); ticks mark its dips.` : `exoplan has reviewed one light curve, ${D.story.star.name}'s (${D.story.star.target}). It has none for ${mc.star}.`;
    if (own) skyTimeline($('#mclc'), $('#mclccap')); else { $('#mclc').innerHTML = ''; $('#mclccap').innerHTML = ''; }
  },
  cat(){
    const ps = mcStarPlanets(mc.star), P = ct.P;
    $('#mccat').innerHTML = ps.length ? `<p class="mcnote">${esc(mc.star)} in ${esc(ct.C.source_short)}:</p><ul class="pllist">${ps.map(j => `<li><a href="${ctPlanetHref(j)}"><span>${esc(P.name[j])}</span><span class="mono">${esc(CTM.method_label[P.method[j]] || P.method[j])} · ${ctFmt(P.period[j], 5) ? ctFmt(P.period[j], 5) + ' d' : 'period not stored'}</span></a></li>`).join('')}</ul>`
      : `<p class="mcnote">${esc(mc.star)} is not in the catalogue.</p>`;
  },
  sys(){
    const ps = mcStarPlanets(mc.star), pick = $('#mcsyspick'), fig = $('#mcsys'), none = !ps.length;
    // No planets in the catalogue: say so instead of a blank stage, and stop its loop.
    $('#mcsysnote').hidden = !none; pick.closest('.mcpick').hidden = none; fig.hidden = none;
    if (none){ $('#mcsysnote').textContent = `${mc.star} is not in the catalogue; there is no system to draw.`; pick.innerHTML = ''; if (fig._mx) fig._mx.on = false; return; }
    if (mc.sys === null || !ps.includes(mc.sys)) mc.sys = ps[0];
    pick.innerHTML = ps.map(j => `<option value="${j}"${j === mc.sys ? ' selected' : ''}>${esc(ct.P.name[j])}</option>`).join('');
    plSystem($('#mcsys'), mc.sys, current === 'mission' && !mc.popped.has('sys'));
  },
  feed(){
    const tics = Object.entries(D.tic_names || {}).filter(([, n]) => n === mc.star).map(([t]) => t);
    const rows = D.catalog.candidates.filter(x => tics.includes(String(x.tic)));
    const named = D.catalog.candidates.some(x => (D.tic_names || {})[String(x.tic)]);
    $('#mcfeednote').textContent = rows.length ? `${rows.length} feed entr${rows.length === 1 ? 'y' : 'ies'} for ${mc.star}.`
      : `The feed is the catalogue run's ${D.catalog.candidates.length} candidates; none is ${mc.star}.` + (named ? ' A TIC with a known name selects its star.' : '');
    const all = rows.length ? rows : D.catalog.candidates, shown = all.slice(0, 12);
    $('#mcfeed').innerHTML = feedCards(shown) + (all.length > shown.length ? `<p class="mcnote">${all.length - shown.length} more in <a href="#/explorer">the Explorer ›</a></p>` : '');
  },
};
function mcRenderPanes(src){
  // The catalogue may arrive after the viewer has left: then nothing moves (the Galaxy's stage stays home).
  const run = () => { if (current !== 'mission') return; mcTele(); for (const p of MC_PANES) if (p !== src && MC_RENDER[p] && !mc.layout.hidden.includes(p) && !(mc.popped.has(p) && !mc.pop) && (!mc.pop || mc.pop === p)) MC_RENDER[p](); };
  if (CTM) ctLoad().then(run).catch(run); else run();
}
// The arrangement: order, hidden panes, popped-out panes, tiles or a main pane.
function mcLayout(){
  const v = mc.layout, grid = $('#mcgrid');
  grid.dataset.grid = v.grid;
  for (const p of v.panes) grid.appendChild($('#mcp-' + p));
  // Only shown panes are numbered, so the numbers match Alt+N and F6.
  let n = 0;
  v.panes.forEach(p => { const el = $('#mcp-' + p), hid = v.hidden.includes(p) || (mc.pop && mc.pop !== p), out = mc.popped.has(p) && !mc.pop;
    el.hidden = hid; el.querySelector('.mcbody').hidden = out; el.querySelector('.mcpopped').hidden = !out; el.querySelector('.mcnum').textContent = hid ? '' : String(++n); });
  const last = v.panes.filter(p => !v.hidden.includes(p)).length <= 1;
  $$('#mcgrid [data-mc="hide"]').forEach(b => { b.disabled = last; b.title = last ? 'One pane always stays shown' : ''; });
  $$('[data-mcgrid]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mcgrid === v.grid)));
  $('#mchidden').innerHTML = v.hidden.map(p => `<button class="btn" type="button" data-mcshow="${p}">Show ${esc(MC_LABEL[p])}</button>`).join('');
  document.body.classList.toggle('mcpop', !!mc.pop);
  if (typeof gxShown === 'function' && GXM) gxShown(gxWanted());
}
function mcMove(p, d){ const a = mc.layout.panes, i = a.indexOf(p), j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; mcLayout(); syncMissionURL(true); }
function mcSwap(p, q){ const a = mc.layout.panes, i = a.indexOf(p), j = a.indexOf(q); if (i < 0 || j < 0 || i === j) return; [a[i], a[j]] = [a[j], a[i]]; mcLayout(); syncMissionURL(true); }
function renderMission(){
  if (mc.mounted || !$('#mcgrid')) return; mc.mounted = true;
  const grid = $('#mcgrid');
  grid.addEventListener('click', e => {
    const b = e.target.closest('[data-mc]'); if (!b) return; const p = b.closest('.mcpane').dataset.pane, act = b.dataset.mc;
    if (act === 'prev') mcMove(p, -1); else if (act === 'next') mcMove(p, 1);
    else if (act === 'focus'){ const a = mc.layout.panes; a.splice(a.indexOf(p), 1); a.unshift(p); mc.layout.grid = 'focus'; mcLayout(); syncMissionURL(true); }
    else if (act === 'hide'){
      if (mc.layout.panes.filter(x => !mc.layout.hidden.includes(x)).length <= 1){ say('One pane always stays shown.'); return; }
      mc.layout.hidden.push(p); mcLayout(); syncMissionURL(true); say(`${MC_LABEL[p]} hidden.`);
      // The hidden pane's Show button takes the focus, so it never falls to the page.
      const sb = $(`#mchidden [data-mcshow="${p}"]`); if (sb) sb.focus(); }
    else if (act === 'pop') mcPopOut(p);
    else if (act === 'back'){ mc.popped.delete(p); if (mcBC) mcBC.postMessage({t: 'close', pane: p, from: mc.win}); mcLayout(); MC_RENDER[p](); }
  });
  // Drag a pane's title bar onto another pane to swap them.
  grid.addEventListener('dragstart', e => { const h = e.target.closest('.mchead'); if (!h) return; e.dataTransfer.setData('text/plain', h.closest('.mcpane').dataset.pane); e.dataTransfer.effectAllowed = 'move'; });
  grid.addEventListener('dragover', e => { const t = e.target.closest('.mcpane'); if (!t) return; e.preventDefault(); $$('.mcpane.drop').forEach(x => x !== t && x.classList.remove('drop')); t.classList.add('drop'); });
  grid.addEventListener('dragleave', e => { const t = e.target.closest('.mcpane'); if (t && !t.contains(e.relatedTarget)) t.classList.remove('drop'); });
  grid.addEventListener('drop', e => { const t = e.target.closest('.mcpane'); if (!t) return; e.preventDefault(); t.classList.remove('drop'); mcSwap(e.dataTransfer.getData('text/plain'), t.dataset.pane); });
  $$('[data-mcgrid]').forEach(b => b.addEventListener('click', () => { mc.layout.grid = b.dataset.mcgrid; mcLayout(); syncMissionURL(true); }));
  $('#mchidden').addEventListener('click', e => { const b = e.target.closest('[data-mcshow]'); if (!b) return; const p = b.dataset.mcshow; mc.layout.hidden = mc.layout.hidden.filter(x => x !== p); mcLayout(); MC_RENDER[p](); syncMissionURL(true); $('#mcp-' + p).focus(); });
  $('#mcsave').addEventListener('click', () => { try { const s = getStorage(); if (!s) throw new Error('storage blocked'); s.setItem(MC_KEY, JSON.stringify({panes: mc.layout.panes, hidden: mc.layout.hidden, grid: mc.layout.grid})); say('Saved as your default layout in this browser.'); } catch (e) { say('This browser does not allow storage; the layout lasts for this visit.'); } });
  $('#mccopy').addEventListener('click', () => { const url = location.href.split('#')[0] + '#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : ''); try { navigator.clipboard.writeText(url).then(() => say('Link copied.'), () => say(url)); } catch (e) { say(url); } });
  $('#mcreset').addEventListener('click', () => { mc.layout = mcDefault(); mcLayout(); mcRenderPanes(); syncMissionURL(true); });
  // Selecting a star: the catalogue pane's finder, the feed (a TIC with a name), the system view's planet.
  $('#mcq').addEventListener('input', () => { const q = $('#mcq').value.trim().toLowerCase(); if (!q || !ct.C){ $('#mcfound').innerHTML = ''; return; }
    const hits = ct.C.stars.names.filter(s => s.toLowerCase().includes(q)).slice(0, 8);
    $('#mcfound').innerHTML = hits.map(s => `<li><button class="btn" type="button" data-mcstar="${esc(s)}">${esc(s)}</button></li>`).join('') || '<li class="mcnote">No star matches.</li>'; });
  $('#route-mission').addEventListener('click', e => { const b = e.target.closest('[data-mcstar]'); if (b){ mcBrush(b.dataset.mcstar, 'cat'); MC_RENDER.cat(); $('#mcfound').innerHTML = ''; $('#mcq').value = ''; say(`Selected ${b.dataset.mcstar} in every pane.`); } });
  $('#mcsyspick').addEventListener('change', e => { mc.sys = Number(e.target.value); MC_RENDER.sys(); });
  // In the feed, a star's name selects it here instead of leaving for its page.
  $('#mcb-feed').addEventListener('click', e => { const a = e.target.closest('a[data-star]'); if (!a) return; e.preventDefault(); mcBrush(a.dataset.star, 'feed'); say(`Selected ${a.dataset.star} in every pane.`); });
  // Keyboard: F6 / Shift+F6 move between panes; Alt+1 … Alt+6 jump to one.
  document.addEventListener('keydown', e => {
    if (current !== 'mission') return;
    const shown = mc.layout.panes.filter(p => !$('#mcp-' + p).hidden);
    let k = -1;
    if (e.key === 'F6'){ const at = shown.indexOf((document.activeElement.closest('.mcpane') || {}).dataset?.pane); k = (at + (e.shiftKey ? -1 : 1) + shown.length) % shown.length; if (at < 0 && e.shiftKey) k = shown.length - 1; }
    else if (e.altKey && /^Digit[1-9]$/.test(e.code)) k = Number(e.code.slice(5)) - 1;   // Alt+N, or Ctrl+Alt+N
    else if (e.altKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')){
      const pane = document.activeElement.closest('.mcpane'); if (!pane) return;
      e.preventDefault(); mcMove(pane.dataset.pane, e.key === 'ArrowLeft' ? -1 : 1); pane.focus(); say(`${MC_LABEL[pane.dataset.pane]} moved ${e.key === 'ArrowLeft' ? 'earlier' : 'later'}.`); return;
    }
    if (k < 0 || k >= shown.length) return;
    e.preventDefault(); const el = $('#mcp-' + shown[k]); el.focus(); el.scrollIntoView({block: 'nearest'}); say(`${MC_LABEL[shown[k]]} pane.`);
  });
}
// Pop a pane out into its own window; both windows stay on the same star over BroadcastChannel.
function mcPopOut(p){
  const url = location.href.split('#')[0] + '#/mission?pop=' + p + (mc.star ? '&star=' + encodeURIComponent(mc.star) : '');
  const w = window.open(url, 'exoplan-' + p, 'popup,width=960,height=680');
  if (!w){ say('The browser blocked the new window.'); return; }
  mc.popped.add(p); mcLayout();
}
if (mcBC) window.addEventListener('pagehide', () => { if (mc.pop) try { mcBC.postMessage({t: 'popped', pane: mc.pop, open: false, from: mc.win}); } catch (e) { /* closing */ } });
function applyMission(v){
  mc.layout = {panes: v.panes, hidden: v.hidden, grid: v.grid, pop: v.pop};
  mc.pop = v.pop;
  if (v.star) mc.star = v.star;
  renderMission(); mcLayout(); mcRenderPanes();
  if (mc.pop && mcBC){ mcBC.postMessage({t: 'popped', pane: mc.pop, open: true, from: mc.win}); if (!v.star) mcBC.postMessage({t: 'hello', from: mc.win}); }
}
// Leaving Mission Control: the Galaxy's stage goes back to its own page.
function missionShown(on){
  const st = $('#gxstage'), home = $('#gxhome');
  if (!on && st && home && st.parentNode !== home.parentNode){ home.after(st); if (current === 'galaxy' && gx.ready) gxResize(); }
  const fig = $('#mcsys'); if (fig && fig._mx){ fig._mx.on = on; if (on) mxKick(fig._mx); }
  if (!on) document.body.classList.remove('mcpop');
}
"""

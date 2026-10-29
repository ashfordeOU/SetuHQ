
const $ = (s, e=document) => e.querySelector(s);
const $$ = (s, e=document) => Array.from(e.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// ---------- one object model: every planet and star has one canonical page ----------
// The slug rule is catalogue.slugify's (the tests check every catalogue name gives its stored slug).
const objSlug = n => String(n).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'x';
const planetHref = n => '/planets/' + objSlug(n) + '/';
const starHref = n => '/stars/' + objSlug(n) + '/';
// The one renderer for a link to a planet or star; data-star / data-planet let any view select it.
// A generic label ("Star page ›") gets the object's name in its accessible name.
const objLink = (kind, n, label) => { label = label ?? n; return `<a class="objlink" data-${kind}="${esc(n)}" href="${kind === 'star' ? starHref(n) : planetHref(n)}"${String(label).includes(n) ? '' : ` aria-label="${esc(n)}, ${kind} page"`}>${esc(label)}</a>`; };
// A TIC with a catalogue name (the run's target, or a TIC in a star's stored alternate names) links to its star page.
const ticLink = tic => (D.tic_names || {})[tic] ? `TIC ${esc(tic)} · ${objLink('star', D.tic_names[tic])}` : `TIC ${esc(tic)}`;
const fmt = (x, d=2) => (x === null || x === undefined || Number.isNaN(Number(x))) ? '–' : Number(x).toFixed(d);
const NS = 'http://www.w3.org/2000/svg';
function el(tag, a={}, p){ const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
function tx(svg, x, y, s, anchor='start', cls=''){ const t = el('text', {x, y, 'text-anchor': anchor, class: cls}, svg); t.textContent = s; return t; }
const UNC = `<span class="tag unc">${esc(D.unconfirmed)}</span>`;
// A run dip's status from its vetting outcome (app.py DIP_STATE): a tag, and the phrase. Only a passed dip is a candidate.
const DIPSTATE = o => (D.dip_state || {})[o] || (D.dip_state || {}).flagged || ['cand', 'candidate', D.unconfirmed];
const DIPTAG = o => { const [c, w, p] = DIPSTATE(o); return `<span class="tag ${c}" title="${esc(p)}">${esc(w)}</span>`; };
const DIPPHRASE = o => DIPSTATE(o)[2];
// A feed entry passed vetting (discover.py admits only those), so it is a candidate; a stored outcome would say otherwise.
const FEEDTAG = x => DIPTAG(x.outcome || 'passed');
const say = msg => { const a = $('#announce'); a.textContent = ''; setTimeout(() => { a.textContent = msg; }, 30); };
// A Sentinel is an AI reviewer on any provider (Claude by default); PROV(id) is its provider, model and calibration.
const SENTINEL_KINDS = D.sentinel_kinds || ['claude', 'claude_code'];
const isSentinel = k => SENTINEL_KINDS.includes(k);
const PROVIDER_OF = k => (D.provider_by_kind || {})[k] || k;
const PROV = id => { const p = (D.reviewer_provenance || {})[id]; return p ? `${p.provider_label} · ${p.model}${p.calibration === 'uncalibrated' ? ' · uncalibrated' : ''}` : ''; };
const OUTCOME_SHORT = {passed: 'passed', flagged: 'flagged', rejected: 'rejected'};
// The panel's display names (the Sentinels and the Probes); ids stay in the data and show beside the names.
const NAME = id => ((D.reviewer_names || {})[id] || {}).name || id;
const nameWithId = id => `${esc(NAME(id))} <span class="mono idtag" title="reviewer id">${esc(id)}</span>`;
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const kindTag = k => k === 'simulated' ? '<span class="tag sim">Probe · not a person</span>' : isSentinel(k) ? `<span class="tag cl">Sentinel · ${esc(PROVIDER_OF(k))}</span>` : `<span class="tag">${esc(k || 'unknown')}</span>`;
function niceTicks(lo, hi, n){
  if (!(hi > lo)) return [lo];
  const raw = (hi-lo)/Math.max(1,n), mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo/step)*step; v <= hi + 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

// ---------- addresses and history ----------
// Every page has one clean address (/explore/galaxy/, /candidates/<dip>/, /planets/<slug>/); routes.py holds the
// table, and RT is the page's copy. The views still name places in the app's old form ('#/galaxy?focus=x'):
// R() turns that into the clean link (a deep link keeps its query), and setHash() into the address bar,
// where view state (filters, sorts, layouts) is left out: the address names the page, never its settings.
// A change of page made by the viewer is a new history entry; a tidy-up of the address replaces the current one.
// Returns false when the browser refuses (a sandboxed context), so the caller can say so.
const RT = D.routes;

function rtUrl(route, params, keepQuery){
  params = Object.assign({}, params || {}); for (const k of Object.keys(params)) if (params[k] === null || params[k] === undefined || params[k] === '') delete params[k];
  route = RT.aliases[route] || route;
  const key = RT.identity[route]; let ident = null, section = null, path;
  if (key){ ident = params[key] || null; delete params[key]; }
  if (route === 'candidates'){ section = params.section || null; delete params.section; }
  if (route === 'transit' || route === 'candidates'){
    const slug = ident ? ((RT.dips || {})[ident] || encodeURIComponent(ident)) : null;
    path = slug ? '/candidates/' + slug + '/' + (route === 'candidates' ? 'case-file/' : '') : (route === 'candidates' ? '/candidates/case-file/' : '/candidates/');
  } else if (route === 'planet' || route === 'star'){
    path = (route === 'planet' ? '/planets/' : '/stars/') + (ident ? ident + '/' : '');
  } else if (route === 'methods'){
    const slug = RT.chapters[ident || 'survey'] || '';
    path = '/how-it-works/' + (slug ? slug + '/' : '');
  } else path = RT.paths[route] || '/';
  const q = keepQuery === false ? '' : new URLSearchParams(params).toString();
  return path + (q ? '?' + q : '') + (section ? '#' + section : '');
}
function rtFromHash(h, keepQuery){
  const body = String(h || '').replace(/^#/, '').replace(/^\//, ''), i = body.indexOf('?');
  let route = i < 0 ? body : body.slice(0, i);
  try { route = decodeURIComponent(route); } catch (e) { /* keep as typed */ }
  const params = Object.fromEntries(new URLSearchParams(i < 0 ? '' : body.slice(i + 1)));
  const m = /^(planet|star)\/([a-z0-9-]{1,120})$/.exec(route);
  if (m){ route = m[1]; params.id = m[2]; }
  if (!(route in RT.paths) && !(route in RT.identity) && !(route in RT.aliases)) return '/';
  if (route === 'overview') return '/';
  if (['transit', 'candidates'].includes(RT.aliases[route] || route) && !params.dip && RT.lead) params.dip = RT.lead;
  return rtUrl(route, params, keepQuery);
}
function rtParse(pathname, search){
  const parts = String(pathname || '/').split('/').filter(Boolean), params = Object.fromEntries(new URLSearchParams(search || ''));
  const norm = '/' + parts.join('/') + (parts.length ? '/' : '');
  for (const r in RT.paths) if (RT.paths[r] === norm && norm !== '/how-it-works/') return {route: r, params};
  if (parts[0] === 'how-it-works' && parts.length <= 2){
    const slug = parts[1] || ''; const ch = Object.keys(RT.chapters).find(c => RT.chapters[c] === slug);
    return ch ? {route: 'methods', params: Object.assign(params, {ch})} : null;
  }
  if (parts.length === 2 && (parts[0] === 'planets' || parts[0] === 'stars') && /^[a-z0-9][a-z0-9-]{0,119}$/.test(parts[1]))
    return {route: parts[0] === 'planets' ? 'planet' : 'star', params: Object.assign(params, {id: parts[1]})};
  if (parts[0] === 'candidates' && (parts.length === 3 || parts.length === 4) && /^[a-z0-9][a-z0-9-]{0,119}$/.test(parts[1]) && /^dip-\d{1,4}$/.test(parts[2])){
    const want = parts[1] + '/' + parts[2], dip = Object.keys(RT.dips || {}).find(i => RT.dips[i] === want) || want;
    if (parts.length === 3) return {route: 'transit', params: Object.assign(params, {dip})};
    if (parts[3] === 'case-file') return {route: 'candidates', params: Object.assign(params, {dip})};
  }
  return null;
}
const R = h => String(h).startsWith('#/') ? rtFromHash(h, true) : h;
function setAddress(url, push){
  url = String(url).startsWith('#/') ? rtFromHash(url, false) : url;
  if (location.pathname + location.search + location.hash === url) return true;
  try { if (push) history.pushState(null, '', url); else history.replaceState(null, '', url); return true; } catch (e) { return false; }
}
const setHash = setAddress;

// ---------- links and dates ----------
const DIP_IDS = new Set(D.dossier_ids);
const dipHref = (id, section) => rtUrl('candidates', {dip: id, section: section || null});
// A dip identifier: a link to its dossier in the Docket when the run has one, plain text otherwise.
// A dip's plain name: "pi Men, dip 2 (6.27 d)" for one of the run's dips; a search-feed entry is "entry 4" beside
// its TIC. The stored id stays in the title, for anyone matching it to a file.
const DIP_NAME = id => ((D.dips || {})[id] || {}).label || null;
const entryNo = id => { const m = /-(\d+)$/.exec(String(id)); return m ? 'entry ' + (Number(m[1]) + 1) : String(id); };
const dipLink = id => DIP_IDS.has(id) ? `<a class="dip" href="${dipHref(id)}" title="Open its case file (stored id ${esc(id)})">${esc(DIP_NAME(id) || id)}</a>` : `<span class="dip" title="Stored id ${esc(id)}; no case file in this run">${esc(entryNo(id))}</span>`;
// A stored ISO-8601 time as a readable local date; the full stored value stays in the title.
function when(iso){
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return esc(iso || 'not stored');
  let s;
  // Shown in UTC, and said so, whatever the viewer's zone; the stored ISO value stays in the title.
  try { s = d.toLocaleString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC'}) + ' UTC'; } catch (e) { s = d.toUTCString(); }
  return `<time datetime="${esc(iso)}" title="${esc(iso)}">${esc(s)}</time>`;
}

// ---------- widget layout (URL first, then localStorage, then the default) ----------
const WIDGET_IDS = D.widgets.map(w => w.id);
const WIDGET_LABEL = Object.fromEntries(D.widgets.map(w => [w.id, w.label]));
const SIZES = ['S', 'M', 'L'], SIZE_NAME = {S: 'small', M: 'medium', L: 'large'};
const LAYOUT_KEY = 'setuhq-app:layout:' + D.title;
// Same rule as app.widget_layout in Python: each known widget exactly once, unknown ids dropped, unknown sizes defaulted.
function normaliseLayout(raw, ids, sizes){
  const out = [], seen = new Set(), def = id => (sizes && sizes[id]) || 'M';
  if (Array.isArray(raw)) for (const it of raw){
    if (!it || typeof it !== 'object') continue;
    if (!ids.includes(it.id) || seen.has(it.id)) continue;
    seen.add(it.id); out.push({id: it.id, visible: it.visible !== false, size: ['S','M','L'].includes(it.size) ? it.size : def(it.id)});
  }
  for (const id of ids) if (!seen.has(id)) out.push({id, visible: true, size: def(id)});
  return out;
}
function readLayout(storage, key, ids, sizes){
  let raw = null;
  try { raw = storage ? JSON.parse(storage.getItem(key)) : null; } catch (e) { raw = null; }
  return normaliseLayout(raw, ids, sizes);
}
// Same format as app.encode_layout / app.decode_layout: "kpis.L,top.L,runs.M.hidden,...".
function encodeLayout(lay){
  return lay.map(x => `${x.id}.${x.size}${x.visible ? '' : '.hidden'}`).join(',');
}
function decodeLayout(text, ids, sizes){
  const items = String(text || '').split(',').map(p => p.trim().split('.')).filter(b => b[0]).map(b => ({id: b[0], size: b[1], visible: !(b.length > 2 && b[2] === 'hidden')}));
  return normaliseLayout(items, ids, sizes);
}
function getStorage(){ try { return window.localStorage; } catch (e) { return null; } }
// ownLayout is the viewer's default. A layout from a shared link is shown for that view only and is
// never written to storage; the default changes only when the viewer uses a layout control.
let ownLayout = readLayout(getStorage(), LAYOUT_KEY, WIDGET_IDS, D.default_size);
let layout = ownLayout.map(x => ({...x})), sharedView = false;
function saveLayout(){
  ownLayout = layout.map(x => ({...x})); sharedView = false;
  try { const s = getStorage(); if (s) s.setItem(LAYOUT_KEY, JSON.stringify(ownLayout)); } catch (e) { /* storage blocked: the layout lasts for this visit */ }
}
// The layout lives in this browser (localStorage); the address never carries it. "Copy link to this view"
// makes a link that does: /candidates/?layout=kpis.L,top.L,... (plus the feed's sort and filter when not the default).
function syncLayoutURL(){ /* nothing: the address names the page only */ }

// ---------- overview ----------
function widgetBody(id){
  function topBody(r){
    // Group the top dips by signal so repeat transits of one signal read as one signal, not several discoveries.
    const groups = [];
    for (const x of r.top){ let g = groups.find(g => g.signal_id === x.signal_id); if (!g){ g = {signal_id: x.signal_id, dips: []}; groups.push(g); } g.dips.push(x); }
    return `<ul class="toplist">${groups.map(g => {
      const f = g.dips[0], n = g.dips.length, xm = g.dips.find(x => x.consistent_with);
      const tic = String(f.target).replace(/^TIC\s*/, ''), star = (D.tic_names || {})[tic];
      const head = `<div><b>${star ? esc(star) : esc(f.target)}</b> <span class="muted">${star ? `· ${esc(f.target)} ` : ''}· signal ${f.period_days ? 'P ' + fmt(f.period_days,3) + ' d' : 'with no period (one transit)'} · ${n} of the top dips${f.signal_dips > n ? `, ${f.signal_dips} dips in the run` : ''}</span></div>`;
      const note = xm ? `<p class="note">Archive cross-match: ${n === 1 ? 'this dip is' : `these ${n} dips are`} consistent with <b>${esc(xm.consistent_with)}</b>, a published planet${xm.dP_pct !== null && xm.dP_pct !== undefined ? ` (period difference ${fmt(xm.dP_pct,2)}%)` : ''}. ${n === 1 ? 'It is a transit' : 'They are repeat transits'} of one known planet, not ${n === 1 ? 'a discovery' : n + ' discoveries'}. ${esc(D.no_detection)}</p>` : '';
      // One line per dip. On a phone the status shows as its short word and the hedge moves to the
      // signal line above, so each row stays one 44 px line; the full words stay for screen readers.
      return `<li>${head}${note}<ul>${g.dips.map(x => `<li class="toprow">${dipLink(x.id)}<span class="mono">SNR ${fmt(x.snr,1)}</span><span class="mono">${fmt(x.depth_ppm,0)} ppm</span><span class="st"><span class="long">${esc(x.outcome_label)}</span><span class="short" aria-hidden="true">${esc(OUTCOME_SHORT[x.outcome] || x.outcome_label)}</span></span>${DIPTAG(x.outcome)}</li>`).join('')}</ul></li>`;
    }).join('')}</ul>`;
  }
  const r = D.run, c = r.counts || {}, dc = r.docket_counts || {};
  if (id === 'kpis'){
    const kinds = Object.values(r.reviewer_kinds), sim = kinds.filter(k => k === 'simulated').length, cl = kinds.filter(isSentinel).length;
    const tiles = [[c.subjects, 'subjects'], [c.classifications, 'reviews'], [dc.signals, 'signals'], [dc.dips, 'dips'], [dc.passed, 'signals passed vetting'], [dc.flagged, 'signals flagged for review']];
    return `<div class="kpis">${tiles.map(([v,l]) => `<div class="kpi"><b>${esc(v ?? '–')}</b><span>${esc(l)}</span></div>`).join('')}</div>
      <p class="muted" style="margin:0;font-size:12px">Run ${esc(r.name)}, ${when(r.created_at)}. ${esc(dc.rejected ?? 0)} signal${dc.rejected===1?'':'s'} rejected by vetting. The light curves are measured (${esc((D.config.inputs[0]||{}).source || 'stored input')}); the reviews come from ${plural(cl, 'Sentinel')} and ${plural(sim, 'Probe')}, no people.</p>`;
  }
  if (id === 'discoveries'){
    const f = D.catalog.candidates, nNew = f.filter(x => x.status === 'new_candidate').length, nKnown = f.filter(x => x.status === 'known_toi').length;
    if (!D.catalog.path) return '<p class="empty">No search catalogue was given to this build.</p>';
    return `<div><span class="big">${f.length}</span> <span class="muted">feed entries</span></div>
      <p style="margin:0">${nKnown} match a known TOI period · ${D.catalog.embargo ? '' : `${nNew} new candidate${nNew===1?'':'s'} · `}${esc(D.catalog.targets_reviewed)} targets reviewed</p>
      ${D.catalog.embargo ? `<p class="muted" style="margin:0">${esc(D.catalog.held_line)}</p>` : ''}
      <p class="muted" style="margin:0;font-size:12px">Catalogue updated ${when(D.catalog.updated)}.</p>`;
  }
  if (id === 'runs'){
    const runs = D.catalog.runs.slice(-5).reverse();
    if (!runs.length) return '<p class="empty">No search runs are stored in the catalogue.</p>';
    return `<ul class="runlist">${runs.map(x => `<li><b>${when(x.time)}</b><span>${x.n_targets ?? (x.targets||[]).length} targets · ${x.new == null ? '' : `${esc(x.new)} new · `}${esc(x.known ?? '–')} known · ${(x.errors||[]).length} error${(x.errors||[]).length===1?'':'s'}</span></li>`).join('')}</ul>
      <p class="muted" style="margin:0;font-size:12px">This page's run: ${esc(r.name)}, ${when(r.created_at)}.</p>`;
  }
  if (id === 'top'){
    if (!r.top.length) return '<p class="empty">This run stored no candidates.</p>';
    return `${topBody(r)}
      <p class="muted" style="margin:0;font-size:12px">The run's dips with the highest stored SNR, grouped by signal; the tag is each dip's vetting status. Select a dip to open its dossier.</p>`;
  }
  return '';
}
const WIDGET_LINK = {kpis: ['#/transit', 'Open the lead candidate'], discoveries: ['#h-feed', 'Go to the feed table'], runs: ['#/runs', 'Open Runs'], top: ['#/transit', 'Open the lead candidate']};
function widgetControls(x, pos, nShown){
  const name = esc(WIDGET_LABEL[x.id]);
  return `<div class="wctl" role="group" aria-label="Arrange ${name}">
    <button class="btn" data-act="up" data-id="${x.id}" aria-label="Move ${name} up" aria-disabled="${pos === 0}">↑</button>
    <button class="btn" data-act="down" data-id="${x.id}" aria-label="Move ${name} down" aria-disabled="${pos === nShown - 1}">↓</button>
    <span class="seg" role="group" aria-label="Size of ${name}">${SIZES.map(z => `<button class="btn" data-act="size" data-size="${z}" data-id="${x.id}" aria-pressed="${x.size === z}" aria-label="${SIZE_NAME[z]}" title="${SIZE_NAME[z]}">${z}</button>`).join('')}</span>
    <button class="btn" data-act="hide" data-id="${x.id}" aria-label="Hide ${name}">Hide</button></div>`;
}
function renderWidgets(){
  const grid = $('#widgets');
  const shown = layout.filter(x => x.visible);
  grid.innerHTML = shown.length ? shown.map((x, i) => `<section class="card widget size-${x.size}" data-widget="${x.id}" aria-labelledby="w-${x.id}">
    <header><h2 id="w-${x.id}">${esc(WIDGET_LABEL[x.id])}</h2>${widgetControls(x, i, shown.length)}</header>${widgetBody(x.id)}
    <a class="wopen" href="${esc(R(WIDGET_LINK[x.id][0]))}">${esc(WIDGET_LINK[x.id][1])}</a></section>`).join('')
    : '<p class="empty">Every widget is hidden. Show one above, or reset the layout.</p>';
  const hidden = layout.filter(x => !x.visible);
  $('#hiddenlist').innerHTML = hidden.length ? `<span>Hidden:</span>${hidden.map(x => `<button class="btn" data-act="show" data-id="${x.id}">Show ${esc(WIDGET_LABEL[x.id])}</button>`).join('')}` : '<span class="muted">All four widgets shown.</span>';
}
function renderOverview(){
  renderWidgets(); syncLayoutURL();
  $('#sharednote').hidden = !sharedView;
}
function layoutAction(act, id, size){
  const i = layout.findIndex(x => x.id === id); if (i < 0) return;
  const name = WIDGET_LABEL[id];
  let focusSel = `[data-act="${act}"][data-id="${id}"]${act === 'size' ? `[data-size="${size}"]` : ''}`;
  if (act === 'hide'){ layout[i].visible = false; say(`${name} hidden. Use Show ${name} to bring it back.`); focusSel = `[data-act="show"][data-id="${id}"]`; }
  else if (act === 'show'){ layout[i].visible = true; say(`${name} shown.`); focusSel = `[data-act="hide"][data-id="${id}"]`; }
  else if (act === 'size'){ if (!SIZES.includes(size)) return; layout[i].size = size; say(`${name} size ${SIZE_NAME[size]}.`); }
  else if (act === 'up' || act === 'down'){
    // Move past the neighbouring shown widget; hidden ones keep their place in the list.
    const vis = layout.map((x, k) => x.visible ? k : -1).filter(k => k >= 0), p = vis.indexOf(i), q = act === 'up' ? p - 1 : p + 1;
    if (p < 0 || q < 0 || q >= vis.length){ say(`${name} is already ${act === 'up' ? 'first' : 'last'}.`); return; }
    const j = vis[q]; [layout[i], layout[j]] = [layout[j], layout[i]];
    say(`${name} moved to position ${q+1} of ${vis.length}.`);
  }
  saveLayout(); renderOverview();
  const back = $('#route-explorer ' + focusSel); if (back) back.focus();
}
$('#route-explorer').addEventListener('click', e => { const b = e.target.closest('button[data-act]'); if (b) layoutAction(b.dataset.act, b.dataset.id, b.dataset.size); });
$('#ownlayout').addEventListener('click', () => { layout = ownLayout.map(x => ({...x})); sharedView = false; renderOverview(); $('#customise').focus(); say('Showing your own layout.'); });
// The cards' controls stay out of the way until the viewer asks to customise.
$('#customise').addEventListener('click', () => {
  const on = $('#customise').getAttribute('aria-pressed') !== 'true';
  $('#customise').setAttribute('aria-pressed', String(on)); $('#customise').textContent = on ? 'Done' : 'Customise';
  $('#widgets').classList.toggle('customising', on); $('#layouttools').hidden = !on;
  say(on ? 'Customise: each card can be hidden, moved or resized.' : 'Done customising.');
});
$('#resetlayout').addEventListener('click', () => { layout = normaliseLayout(null, WIDGET_IDS, D.default_size); saveLayout(); renderOverview(); $('#resetlayout').focus(); say('Layout reset: every widget shown in the default order and size.'); });

// ---------- candidates (the Docket) ----------
const DOCKET_SECTIONS = ['strip', 'signal', 'ctx', 'cmp', 'ledger', 'rev'];
// The Docket reads a dip id from its own location hash on load, so the frame loads the shell's copy of the
// Docket (a file beside the site) with the dip as that hash.
// The shell's copy of the Docket carries a small bridge: it reports the selected dip and the section
// in view by postMessage, and takes the same from the shell, so the address bar follows the frame.
const BLOCKED_TEXT = 'The dossier could not load in this view.';
const LOADING_TEXT = 'Loading the Docket…';
const frame = {ready: false, mode: null, dip: null, section: null, pending: null, crossOrigin: false, timer: null, gen: 0,
  frameURLFailed: false, shellURLFailed: false};
// The shell's copy of the Docket is a file of its own (D.docket_frame, same origin); the dip is its hash.
// Each example run has its own case file; a dip opens its own run's (D.docket_frames, by run name).
const runOf = dip => ((D.dips || {})[dip] || {}).run || D.run.name;
const RUNCTX = dip => (D.run_ctx || {})[runOf(dip)] || {};
function docketURL(dip){ return ((D.docket_frames || {})[runOf(dip)] || D.docket_frame) + (dip ? '#' + encodeURIComponent(dip) : ''); }
const fullHref = dip => (RUNCTX(dip).case_file || '/candidates/case-file/') + (dip ? '#' + encodeURIComponent(dip) : '');
function setFullHrefs(dip){ for (const a of $$('#fullpage, #topfull, #blockedlink')) a.href = fullHref(dip); showDipStar(dip || leadDip()); }
// Keep the shell URL and the full-page links on the dip (and section) the frame shows.
function showDipStar(dip){ const run = runOf(dip); for (const s of $$('#route-candidates .dipstar')) s.hidden = s.dataset.run !== run; }
function syncShellURL(){
  setFullHrefs(frame.dip);
  const pick = $('#dippick'); if (pick && frame.dip && pick.value !== frame.dip) pick.value = frame.dip;
  if (current !== 'candidates' || !frame.dip) return;
  const h = dipHref(frame.dip, frame.section);
  if (location.pathname + location.hash !== h){
    // A new dip is a new history entry (Back returns to the last dip); a section change only replaces.
    const shown = (rtParse(location.pathname, location.search) || {params: {}}).params.dip;
    const push = !!frame.dip && !!shown && shown !== frame.dip;
    frame.shellURLFailed = !setHash(h, push);
    if (frame.ready) readyStatus();
  }
}
function tellFrame(dip, section){
  if (dip) { frame.dip = dip; frame.section = section || null; }
  else if (section) frame.section = section;
  try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', dip, section}, '*'); } catch (e) { /* frame gone */ }
  syncShellURL();
}
// The status line: a notice about the address (an unknown dip, say) comes first, then the frame's state.
function frameStatus(text){ const t = [frame.notice, text].filter(Boolean).join(' '); const s = $('#framestatus'); s.textContent = t; s.hidden = !t; fitFrame(); }
// The status line once the Docket is showing: say when an address cannot follow the selected dip.
function readyStatus(){
  frameStatus(frame.shellURLFailed ? 'Address bar not updated in this view. Open full page goes to the selected dip.'
    : frame.crossOrigin ? 'The Docket runs in a separate origin here (as when this page is opened from a file), so this view follows it by messages only. If the address bar stops following the selected dip, use Open full page.'
    : frame.frameURLFailed ? 'Address bar not updated inside the Docket in this view (a fallback frame cannot change its own address). The address bar above and Open full page follow the selected dip by messages.'
    : '');
}
// Desktop: the frame takes the viewport height less what sits above it (the route header, the tools,
// the status line) and the page's bottom padding, so the page itself does not scroll.
// The CSS keeps calc(100vh - 190px) as the fallback until this has run.
function fitFrame(){
  const f = $('#docketframe');
  if (!f || f.hidden || f.classList.contains('waiting') || $('#route-candidates').hidden || matchMedia('(max-width:699.98px)').matches) return;
  const top = f.getBoundingClientRect().top + window.scrollY;
  const below = parseFloat(getComputedStyle($('#main')).paddingBottom) || 0;
  document.documentElement.style.setProperty('--frame-offset', Math.ceil(top + below) + 'px');
}
function showBlocked(){
  clearTimeout(frame.timer);
  const f = $('#docketframe'); f.hidden = true; f.classList.remove('waiting');
  $('#frameblocked').hidden = false; frameStatus('');
  document.documentElement.style.removeProperty('--frame-offset');
  setFullHrefs(frame.dip);
  say(BLOCKED_TEXT + ' Open it on its own page.');
}
function frameLoadFailed(gen){
  if (gen !== frame.gen || frame.ready) return;
  showBlocked();
}
function onFrameReady(m){
  frame.ready = true; clearTimeout(frame.timer);
  const f = $('#docketframe'); f.hidden = false; f.classList.remove('waiting'); $('#frameblocked').hidden = true;
  try { void f.contentWindow.document.body; frame.crossOrigin = false; } catch (e) { frame.crossOrigin = true; }
  readyStatus();
  const p = frame.pending; frame.pending = null;
  if (p && ((p.dip && p.dip !== m.dip) || p.section)) tellFrame(p.dip, p.section);
  else { frame.dip = m.dip || frame.dip; syncShellURL(); }
  try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', theme: currentTheme()}, '*'); } catch (e) { /* frame gone */ }
}
window.addEventListener('message', e => {
  const f = $('#docketframe'), m = e.data;
  if (!f || e.source !== f.contentWindow || !m || m.source !== 'setuhq-docket') return;
  if (m.urlFailed) frame.frameURLFailed = true;
  if (m.kind === 'ready'){ onFrameReady(m); return; }
  if (!frame.ready) return;  // the Docket's own first pick, before the shell's dip is applied
  if (m.kind === 'dip' && m.dip){ if (m.dip !== frame.dip){ frame.section = null; if (frame.notice){ frame.notice = ''; readyStatus(); } } frame.dip = m.dip; }
  else if (m.kind === 'section'){ frame.section = DOCKET_SECTIONS.includes(m.section) ? m.section : null; if (m.dip) frame.dip = m.dip; }
  syncShellURL();
  if (m.urlFailed) readyStatus();
});
function loadDocket(dip, section, mode){
  const f = $('#docketframe'), url = docketURL(dip), gen = ++frame.gen;
  frame.run = runOf(dip);
  Object.assign(frame, {ready: false, mode: 'file', dip, section: section || null, pending: {dip, section: section || null},
    frameURLFailed: false});
  // Not shown until it reports ready: an empty bordered box would sit under the loading line.
  f.hidden = false; f.classList.add('waiting'); $('#frameblocked').hidden = true;
  frameStatus(LOADING_TEXT);
  clearTimeout(frame.timer);
  // A frame that never reports ready did not load (blocked by frame-src, say): try srcdoc, then say so.
  // The srcdoc copy needs no fetch, so its wait is shorter.
  frame.timer = setTimeout(() => frameLoadFailed(gen), 6000);
  const onload = () => {
    let blank = false;
    try { blank = f.contentWindow.location.href === 'about:blank'; } catch (e) { /* cross-origin: an error page or file:// */ }
    if (blank) { f.addEventListener('load', onload, {once: true}); return; }
    setTimeout(() => frameLoadFailed(gen), 800);
  };
  f.addEventListener('load', onload, {once: true});
  f.src = url;
}
function openDip(dip, section){
  const f = $('#docketframe');
  if (dip && !DIP_IDS.has(dip)){
    // An unknown dip id: say so, and rewrite the address to the lead dip (replace, not a new entry).
    const lead = leadDip();
    frame.notice = `No dip ${dip} in run ${D.run.name}; showing the lead dip${lead ? ' ' + lead : ''}.`;
    say(frame.notice); dip = lead;
    if (lead) setAddress(dipHref(lead), false);
    if (frame.ready) readyStatus(); else frameStatus(f.dataset.loaded ? LOADING_TEXT : '');
  } else if (dip) frame.notice = '';
  if (!DOCKET_SECTIONS.includes(section)) section = null;
  if (!f.dataset.loaded || (dip && frame.run && runOf(dip) !== frame.run)){ f.dataset.loaded = '1'; loadDocket(dip, section); setFullHrefs(dip); }
  else if (!frame.ready){ if (dip || section) frame.pending = {dip: dip || frame.dip, section}; setFullHrefs(dip || frame.dip); }
  else if (dip || section) tellFrame(dip, section);
  else syncShellURL();
  if (dip) say(`Docket open on dip ${dip}${section === 'ledger' ? ', verdict ledger' : ''}.`);
}
// The lead dip: the highest-SNR dip of the Overview's lead signal, else the first dossier.
const leadDip = () => (D.hero && D.hero.lead && D.hero.lead.dip) || D.dossier_ids[0] || null;
// The phone dip picker above the frame: every dip in time order, with its letter and outcome.
function renderDipPicker(){
  const sel = $('#dippick'); if (!sel) return;
  // Grouped by star: the lead run's dips first, then each other example run's.
  sel.innerHTML = (D.showcase || []).map(c => `<optgroup label="${esc(c.star)}">${c.dips.map(w => `<option value="${esc(w.id)}">${esc(w.label)} · ${esc(w.outcome)}</option>`).join('')}</optgroup>`).join('');
  if (frame.dip) sel.value = frame.dip;
}
function renderCandidates(){ renderDipPicker(); /* the frame loads in openDip, with the dip from the URL */ }

// ---------- discoveries (the feed) ----------
const disc = {sort: 'snr', dir: -1, filter: 'all'};
// The Feed's sort and filter live in the URL (#/explorer?sort=depth&filter=new) like the Overview
// layout, and in localStorage as the viewer's default. A view opened from a link is shown for that
// view only; storage is written only when the viewer changes the sort or the filter.
const FEED_SORTS = D.feed_view.sorts, FEED_FILTERS = D.feed_view.filters, FEED_NUMERIC = D.feed_view.numeric;
const FEED_KEY = 'setuhq-app:feed:' + D.title;
const shortOf = (map, key) => Object.keys(map).find(k => map[k] === key);
// Same rule as app.feed_view in Python.
function normaliseFeedView(raw){
  raw = raw && typeof raw === 'object' ? raw : {};
  const sort = Object.prototype.hasOwnProperty.call(FEED_SORTS, raw.sort) ? raw.sort : D.feed_view.default.sort;
  const defDir = FEED_NUMERIC.includes(sort) ? 'desc' : 'asc';
  const dir = raw.dir === 'asc' || raw.dir === 'desc' ? raw.dir : defDir;
  const filter = Object.prototype.hasOwnProperty.call(FEED_FILTERS, raw.filter) ? raw.filter : D.feed_view.default.filter;
  return {sort, dir, filter};
}
// Same format as app.encode_feed_view / app.decode_feed_view.
function encodeFeedView(v){
  v = normaliseFeedView(v);
  const defDir = FEED_NUMERIC.includes(v.sort) ? 'desc' : 'asc';
  return `sort=${v.sort}${v.dir === defDir ? '' : '&dir=' + v.dir}&filter=${v.filter}`;
}
function decodeFeedView(params){
  const get = k => params.get(k) || undefined;
  return normaliseFeedView({sort: get('sort'), dir: get('dir'), filter: get('filter')});
}
const currentFeedView = () => ({sort: shortOf(FEED_SORTS, disc.sort), dir: disc.dir > 0 ? 'asc' : 'desc', filter: shortOf(FEED_FILTERS, disc.filter)});
function applyFeedView(v){ v = normaliseFeedView(v); disc.sort = FEED_SORTS[v.sort]; disc.dir = v.dir === 'asc' ? 1 : -1; disc.filter = FEED_FILTERS[v.filter]; }
let ownFeedView = (() => { let raw = null; try { const s = getStorage(); raw = s ? JSON.parse(s.getItem(FEED_KEY)) : null; } catch (e) { raw = null; } return normaliseFeedView(raw); })();
function saveFeedView(){
  ownFeedView = currentFeedView();
  try { const s = getStorage(); if (s) s.setItem(FEED_KEY, JSON.stringify(ownFeedView)); } catch (e) { /* storage blocked: the view lasts for this visit */ }
}
// push: the viewer changed the sort or the filter, so Back returns to the previous view.
function syncFeedURL(push){
  if (current !== 'explorer') return;
  // The Feed table's sort and filter, then the scatter's filters; each left out when it is the default.
  const fv = encodeFeedView(currentFeedView()), q = [fv === encodeFeedView(D.feed_view.default) ? '' : fv, encodeExView(currentEx())].filter(Boolean).join('&');
  setHash('#/explorer' + (q ? '?' + q : ''), !!push);
}
applyFeedView(ownFeedView);
const COLS = [
  ['tic', 'TIC', x => x.tic, x => (D.tic_names || {})[x.tic] ? `${esc(x.tic)} · ${objLink('star', D.tic_names[x.tic])}` : esc(x.tic)],
  ['candidate_id', 'entry', x => x.candidate_id, x => dipLink(x.candidate_id)],
  ['t_center', 'mid-time', x => x.t_center, x => `${fmt(x.t_center,3)}<small>${esc(x.time_unit)}</small>`],
  ['period_days', 'period (d)', x => x.period_days, x => fmt(x.period_days,4)],
  ['depth_ppm', 'depth (ppm)', x => x.depth_ppm, x => fmt(x.depth_ppm,0)],
  ['snr', 'SNR', x => x.snr, x => fmt(x.snr,1)],
  ['status', 'status', x => x.status, x => `${esc(D.status_label[x.status] || x.status)} ${FEEDTAG(x)}`],
];
const NUMERIC = new Set(['tic','t_center','period_days','depth_ppm','snr']);
function discRows(){
  const f = D.catalog.candidates.filter(x => disc.filter === 'all' || x.status === disc.filter);
  const col = COLS.find(c => c[0] === disc.sort), key = col[2];
  return f.slice().sort((a, b) => { const va = key(a), vb = key(b); return (va < vb ? -1 : va > vb ? 1 : 0) * disc.dir; });
}
// Dip ids link to the Docket only when this run stored a dossier for them; say so when a row has none.
function noDossierLine(rows){
  const missing = rows.filter(x => !DIP_IDS.has(x.candidate_id)).length;
  if (!missing) return '';
  const text = missing === rows.length ? 'No dossier stored for these rows in this run.' : `No dossier stored for ${missing} of these rows in this run; their dip ids are plain text.`;
  return `<span class="capnote" id="nodossier">${text}</span>`;
}
// A known TOI match is an archive comparison: wherever one is shown, say this page claims no detection.
function archiveNote(rows){
  if (!rows.some(x => x.status === 'known_toi')) return '';
  return `<span class="capnote" id="archivenote">A known TOI match compares a stored BLS period with archive values. ${esc(D.no_detection)}</span>`;
}
function renderDiscTable(){
  const rows = discRows();
  $('#disctable').innerHTML = `<table><caption><span class="sr">Feed, sorted by ${esc(disc.sort)} ${disc.dir > 0 ? 'ascending' : 'descending'}. Every entry is a ${esc(D.unconfirmed)}.</span>${noDossierLine(rows)}${archiveNote(rows)}</caption>
    <thead><tr>${COLS.map(c => `<th scope="col" class="${NUMERIC.has(c[0]) ? 'num' : ''}" aria-sort="${disc.sort === c[0] ? (disc.dir > 0 ? 'ascending' : 'descending') : 'none'}"><button data-sort="${c[0]}">${esc(c[1])}<span aria-hidden="true">${disc.sort === c[0] ? (disc.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`).join('')}</tr></thead>
    <tbody>${rows.length ? rows.map(x => `<tr>${COLS.map((c, k) => k === 0 ? `<th scope="row" class="num" data-label="${esc(c[1])}">${c[3](x)}</th>` : `<td class="${NUMERIC.has(c[0]) ? 'num' : ''} c-${c[0]}" data-label="${esc(c[1])}">${c[3](x)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${COLS.length}" class="empty">No feed entries with this status.</td></tr>`}</tbody></table>`;
  // Phone: a labelled "Sort" group (outlined, unlike the filled filter chips) and one three-line card per entry.
  $('#disctable').insertAdjacentHTML('beforeend', feedSortBar() + feedCards(rows));
  $('#disccount').textContent = `${rows.length} of ${D.catalog.candidates.length} entries shown.`;
}
function feedSortBar(){
  return `<div class="sortbar" role="group" aria-label="Sort by"><span class="sortlbl" aria-hidden="true">Sort</span>${COLS.filter(c => c[0] !== 't_center').map(c => `<button class="sortbtn" data-sort="${c[0]}" aria-pressed="${disc.sort === c[0]}">${esc(c[1])}${disc.sort === c[0] ? `<span aria-hidden="true"> ${disc.dir > 0 ? '▲' : '▼'}</span><span class="sr">, ${disc.dir > 0 ? 'ascending' : 'descending'}</span>` : ''}</button>`).join('')}</div>`;
}
// One card per entry, three lines: the dip and its status; TIC · P · depth · SNR on one mono line; the hedge.
function feedCards(rows){
  if (!rows.length) return '<p class="empty feedcards">No feed entries with this status.</p>';
  return `<ol class="feedcards">${rows.map(x => `<li><div class="fc1">${dipLink(x.candidate_id)}<span class="fcst">${esc(D.status_label[x.status] || x.status)}</span></div><div class="fc2 mono">${ticLink(x.tic)} · P ${fmt(x.period_days,3)} d · ${fmt(x.depth_ppm,0)} ppm · SNR ${fmt(x.snr,1)}</div><div class="fc3">${FEEDTAG(x)} mid-time ${fmt(x.t_center,2)} ${esc(x.time_unit)}</div></li>`).join('')}</ol>`;
}
function renderDiscHead(){
  const f = D.catalog.candidates, n = s => f.filter(x => x.status === s).length, ft = D.catalog.found_times;
  const found = !ft.length ? 'no stored find time' : ft.length === 1 ? `found in the catalogue run of ${when(ft[0])}` : `found between ${when(ft[0])} and ${when(ft[ft.length-1])}`;
  $('#feedhead').innerHTML = (f.length ? `${f.length} entries, ${found}. <b>${n('known_toi')} match a known TOI period</b>${D.catalog.embargo ? '' : `; ${n('new_candidate')} are new candidates`}. Every entry is a ${esc(D.unconfirmed)}.${n('known_toi') ? ` A TOI match is an archive comparison. ${esc(D.no_detection)}` : ''}` : 'The feed is empty.') + (D.catalog.embargo ? ` ${esc(D.catalog.held_line)}` : '');
}
function renderDiscChips(){
  const f = D.catalog.candidates, n = s => f.filter(x => x.status === s).length;
  const chips = [['all', `all ${f.length}`], ['new_candidate', `new ${n('new_candidate')}`], ['known_toi', `known TOI ${n('known_toi')}`]].filter(c => !(D.catalog.embargo && c[0] === 'new_candidate'));
  $('#discchips').innerHTML = chips.map(([k, l]) => `<button class="chip" data-f="${k}" aria-pressed="${disc.filter === k}">${esc(l)}</button>`).join('');
}

$('#disctable').addEventListener('click', e => {
  const b = e.target.closest('button[data-sort]'); if (!b) return;
  const k = b.dataset.sort;
  if (disc.sort === k) disc.dir = -disc.dir; else { disc.sort = k; disc.dir = NUMERIC.has(k) ? -1 : 1; }
  saveFeedView(); syncFeedURL(true);
  renderDiscTable();
  const again = $(`#disctable ${b.closest('.sortbar') ? '.sortbar' : 'thead'} button[data-sort="${k}"]`); if (again) again.focus();
  say(`Sorted by ${b.textContent.replace(/[▲▼]/g,'')}, ${disc.dir > 0 ? 'ascending' : 'descending'}.`);
});
$('#discchips').addEventListener('click', e => {
  const b = e.target.closest('button[data-f]'); if (!b) return;
  disc.filter = b.dataset.f; saveFeedView(); syncFeedURL(true); renderDiscChips(); renderDiscTable();
  $(`#discchips button[data-f="${disc.filter}"]`).focus();
  say($('#disccount').textContent);
});
function histogram(box, values, label, unit, maxRule){
  box.innerHTML = '';
  const vals = values.filter(v => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
  const W = 340, H = 190, pl = 34, pr = 10, pt = 14, pb = 34;
  const h3 = document.createElement('h3'); h3.textContent = label; box.appendChild(h3);
  if (!vals.length){ box.insertAdjacentHTML('beforeend', '<p class="empty">No stored values.</p>'); return; }
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (maxRule !== undefined) hi = Math.max(hi, maxRule);
  if (hi === lo){ lo -= 1; hi += 1; }
  const ticks = niceTicks(lo, hi, 6), step = ticks.length > 1 ? ticks[1] - ticks[0] : (hi - lo);
  const a = Math.floor(lo / step) * step, b = Math.max(a + step, Math.ceil(hi / step) * step);
  const nb = Math.max(1, Math.round((b - a) / step));
  const counts = new Array(nb).fill(0);
  for (const v of vals) counts[Math.min(nb - 1, Math.floor((v - a) / step))]++;
  const cmax = Math.max(...counts);
  const X = v => pl + (v - a) / (b - a) * (W - pl - pr), Y = c => pt + (1 - c / cmax) * (H - pt - pb);
  const summary = counts.map((c, i) => `${fmt(a + i*step, step < 1 ? 2 : 0)} to ${fmt(a + (i+1)*step, step < 1 ? 2 : 0)}: ${c}`).join('; ');
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Histogram of ${label}, ${vals.length} feed entries. ${summary}.`}, box);
  for (const c of niceTicks(0, cmax, 3)){ el('line', {x1: pl, x2: W - pr, y1: Y(c), y2: Y(c), class: 'grid'}, svg); tx(svg, pl - 6, Y(c) + 4, String(c), 'end'); }
  counts.forEach((c, i) => {
    if (!c) return;
    const x0 = X(a + i*step) + 1, x1 = X(a + (i+1)*step) - 1;
    el('rect', {x: x0, y: Y(c), width: Math.max(1, x1 - x0), height: Y(0) - Y(c), class: 'bar'}, svg);
    tx(svg, (x0 + x1) / 2, Y(c) - 3, String(c), 'middle', 'lbl');
  });
  el('line', {x1: pl, x2: W - pr, y1: Y(0), y2: Y(0), stroke: 'var(--muted)'}, svg);
  const every = Math.ceil((nb + 1) / 6);
  for (let i = 0; i <= nb; i += every){ const v = a + i*step; tx(svg, X(v), H - pb + 14, Number(v.toPrecision(6)).toString(), 'middle'); }
  tx(svg, W - pr, H - 4, unit, 'end');
  if (maxRule !== undefined){
    el('line', {x1: X(maxRule), x2: X(maxRule), y1: pt, y2: Y(0), stroke: 'var(--flag)', 'stroke-dasharray': '4 3'}, svg);
    tx(svg, X(maxRule) - 4, pt + 10, 'feed rule', 'end');
  }
  box.insertAdjacentHTML('beforeend', `<p class="muted" style="margin:4px 0 0;font-size:12px">${vals.length} feed entries, stored values, bin width ${Number(step.toPrecision(6))} ${esc(unit)}.</p>`);
}
function timeline(box){
  box.innerHTML = '';
  const f = D.catalog.candidates;
  if (!f.length){ box.innerHTML = '<p class="empty">The feed is empty.</p>'; return; }
  const tics = [...new Set(f.map(x => x.tic))].sort((p, q) => p - q);
  const narrow = box.clientWidth < 560;
  const W = Math.max(280, box.clientWidth || 600), rh = narrow ? 34 : 26, pl = narrow ? 8 : 120, pr = 14, pt = 8, pb = 34;
  const H = pt + tics.length * rh + pb;
  const ts = f.map(x => x.t_center), lo = Math.min(...ts), hi = Math.max(...ts), pad = (hi - lo) * 0.03 || 1;
  const a = lo - pad, b = hi + pad;
  const X = t => pl + (t - a) / (b - a) * (W - pl - pr);
  const unit = f[0].time_unit || '';
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Timeline by star: ${f.length} feed entries on ${tics.length} stars, mid-time in ${unit}. The table above lists the same entries.`}, box);
  svg.style.height = H + 'px';
  tics.forEach((tic, i) => {
    const y = pt + i*rh + rh/2 + (narrow ? 6 : 0);
    el('line', {x1: pl, x2: W - pr, y1: y, y2: y, class: 'grid'}, svg);
    const n = f.filter(x => x.tic === tic).length;
    if (narrow) tx(svg, pl, y - 8, `TIC ${tic} · ${n}`, 'start');
    else tx(svg, pl - 8, y + 4, `TIC ${tic}`, 'end');
    for (const x of f.filter(x => x.tic === tic)){
      const isNew = x.status === 'new_candidate';
      const c = el('circle', {cx: X(x.t_center), cy: y, r: isNew ? 5 : 4, fill: isNew ? 'var(--fit)' : 'var(--panel)', stroke: isNew ? 'var(--fit)' : 'var(--muted)', 'stroke-width': 1.6}, svg);
      const t = el('title', {}, c); t.textContent = `TIC ${tic} · ${fmt(x.t_center,3)} ${unit} · ${D.status_label[x.status] || x.status} · ${D.unconfirmed}`;
    }
  });
  for (const t of niceTicks(a, b, narrow ? 3 : 6)){ if (t < a || t > b) continue; el('line', {x1: X(t), x2: X(t), y1: H - pb, y2: H - pb + 4, stroke: 'var(--muted)'}, svg); tx(svg, X(t), H - pb + 16, String(t), 'middle'); }
  tx(svg, W - pr, H - 4, `mid-time (${unit})`, 'end');
  // S06: a rule and a readout follow the pointer (or the arrow keys, with the chart focused) to the nearest entry.
  if (window.SetuUI && SetuUI.crosshair){
    const k = (b - a) / (W - pl - pr), sorted = f.slice().sort((p, q) => p.t_center - q.t_center);
    SetuUI.crosshair(svg, {x0: a - pl * k, x1: b + pr * k, xs: sorted.map(x => x.t_center), readout: $('#tlread'),
      fmt: i => { const x = sorted[i]; return `${unit} ${fmt(x.t_center, 3)} · TIC ${x.tic} · ${D.status_label[x.status] || x.status} · depth ${fmt(x.depth_ppm, 0)} ppm · ${D.unconfirmed}`; }});
  }
}
let discWidth = -1;
function renderDiscCharts(force){
  const box = $('#timeline');
  if (!force && box.clientWidth === discWidth) return;
  discWidth = box.clientWidth;
  const f = D.catalog.candidates;
  histogram($('#h-depth'), f.map(x => x.depth_ppm), 'Depth', 'ppm', D.feed_rule.max_depth_ppm);
  histogram($('#h-snr'), f.map(x => x.snr), 'SNR', 'SNR');
  histogram($('#h-period'), f.map(x => x.period_days), 'Period', 'days');
  timeline(box);
}
function renderDiscoveries(){ renderDiscHead(); renderDiscChips(); renderDiscTable(); renderDiscCharts(true); }

// ---------- planets ----------
// The star (its TIC Teff, a static disc from the page's template; grey where no temperature is stored) and a black
// silhouette disc at Rp/R* = sqrt(depth): what the dip would cast if it were a planet. Never planet art.
let rrN = 0;
function ratioDisc(star, k){
  const t = $('#rrdiscs'), src = t && t.content.querySelector(`[data-star="${CSS.escape(star)}"]`), R = 20, rk = Math.max(0.6, k * R), id = 'rrd' + (rrN++);
  const disc = src ? src.innerHTML.replace(/sd-(rr\d+)/g, `sd-$1-${id}`) : `<svg class="stardisc" viewBox="0 0 40 40" width="40" height="40" aria-hidden="true"><circle cx="20" cy="20" r="20" fill="#5E6472"/></svg>`;
  const teff = src ? Number(src.dataset.teff) : null;
  return `<figure class="rrfig" role="img" aria-label="Silhouette at Rp/R★ ${fmt(k, 4)} = √depth, if it were a planet, on ${esc(star)}${teff ? ` in its blackbody colour, ${teff.toLocaleString('en-GB')} K` : ', whose temperature is not stored (drawn grey)'}"><span class="rrdisc" aria-hidden="true">${disc}<svg class="rrsil" viewBox="0 0 40 40" width="40" height="40"><circle cx="${(R + R * 0.18).toFixed(2)}" cy="20" r="${rk.toFixed(2)}" fill="#000"/></svg></span></figure>`;
}
function renderPlanets(){
  const cards = D.planets, MAX = D.ratio_scale_max;
  $('#planetcards').innerHTML = cards.length ? cards.map(s => {
    const rowHtml = e => `<div class="ratio">
      <div>${dipLink(e.id)} ${e.source === 'run' ? DIPTAG(e.outcome) : UNC}</div>
      <div class="muted" style="font-size:12px">${e.source === 'run' ? 'this run' : 'feed'} · ${esc(e.status)} · ${e.period_days ? 'P ' + fmt(e.period_days,3) + ' d' : 'no period'}${e.n_transits ? ' · ' + e.n_transits + ' transits' : ''}</div>
      ${e.ratio === null ? '<div class="formula">No positive stored depth, so no ratio.</div>' : `<div class="rrrow">${ratioDisc(s.star, e.ratio)}<div class="formula">Rp/R* = √depth = √(${fmt(e.depth_ppm,1)} ppm × 10⁻⁶) = <b>${fmt(e.ratio,4)}</b></div></div>
      <div class="scale" role="img" aria-label="Rp/R* ${fmt(e.ratio,4)} on a scale from 0 to ${fmt(MAX,2)}"><i style="width:${Math.min(100, e.ratio / MAX * 100).toFixed(2)}%"></i></div>
      <div class="scalecap" aria-hidden="true"><span>0</span><span>${e.ratio > MAX ? 'beyond ' : ''}${fmt(MAX,2)} max</span></div>`}
      ${e.archive_line ? `<div class="muted" style="font-size:12px">Archive comparison: ${esc(e.archive_line)}. ${esc(D.no_detection)}</div>` : ''}
    </div>`;
    const SHOW = 3, more = s.entries.slice(SHOW);
    const rows = s.entries.slice(0, SHOW).map(rowHtml).join('') + (more.length ? `<details class="ratio"><summary>Show ${more.length} more entr${more.length===1?'y':'ies'} for ${esc(s.star)}</summary>${more.map(rowHtml).join('')}</details>` : '');
    const ar = s.archive || {status: 'not_stored', planets: []};
    // Stars with no stored cross-match get no box; the section header says so once.
    let arch = '';
    if (ar.status === 'not_run') arch = `<p style="margin:0">The archive cross-match did not run. Stored error, verbatim: <code>${esc(ar.error || 'none stored')}</code>. ${esc(D.no_detection)}</p>`;
    else if (ar.status !== 'not_stored' && !ar.planets.length) arch = `<p style="margin:0">No published planet matched in the archive. ${esc(D.no_detection)}</p>`;
    else if (ar.status !== 'not_stored') arch = `<p style="margin:0"><b>Published planets.</b> ${esc(D.no_detection)}</p><ul>${ar.planets.map(p => `<li><b>${objLink('planet', p.pl_name)}</b> · host ${objLink('star', p.hostname)} · P ${p.pl_orbper !== null && p.pl_orbper !== undefined ? esc(p.pl_orbper) + ' d' : 'not listed'} · ${p.tran_flag ? 'transiting' : 'not known to transit'}${p.rv_flag ? ' · radial-velocity detection' : ''}</li>`).join('')}</ul><p class="muted" style="margin:4px 0 0;font-size:12px">${esc(ar.source)}, ${ar.fallback_from ? `recorded ${when(ar.fetched_at)}${ar.recorded_commit ? ` (commit ${esc(ar.recorded_commit)})` : ''} in ${esc(ar.fallback_from)}; this run's own cross-match ${ar.run_status === 'not_run' ? 'did not run' : 'is not stored'}${ar.run_error ? ` (stored error, verbatim: <code>${esc(ar.run_error)}</code>)` : ''}` : `fetched ${when(ar.fetched_at)}`}.</p>`;
    const hid = 'pl-' + String(s.star).replace(/\W/g,'_');
    return `<article class="card" aria-labelledby="${hid}"><h2 id="${hid}">${esc(s.star)}${(D.tic_names || {})[String(s.star).replace(/^TIC /, '')] ? ' · ' + objLink('star', D.tic_names[String(s.star).replace(/^TIC /, '')]) : ''} <span class="muted" style="font:500 11px var(--mono)">${esc(s.sources.join(' · '))} · ${s.entries.length} entr${s.entries.length===1?'y':'ies'}</span></h2>${rows}${arch ? `<div class="archive">${arch}</div>` : ''}</article>`;
  }).join('') : '<p class="empty">No stars in the run or the feed.</p>';
}

// ---------- panel ----------
function renderPanel(){
  renderCalibration(); calWidth = $('#calplane').clientWidth;
  const ag = D.agreement;
  $('#agreement').innerHTML = ag.length ? `<ul class="agree">${ag.map(a => `<li>
      <span>${dipLink(a.id)}<small class="muted" style="display:block;font-size:11px">${esc(a.target)} · ${esc(DIPPHRASE(a.outcome))}</small></span>
      <span><b>${a.n} of ${a.of} reviewers</b> marked it: ${a.n_claude} of ${plural(a.of_claude, 'Sentinel')}, ${a.n_sim} of ${plural(a.of_sim, 'Probe')}<small class="muted" style="display:block;font-size:11px">${a.reviewers.map(r => `<span title="reviewer id ${esc(r)}">${esc(NAME(r))}</span>`).join(', ') || 'none'}</small></span>
      <a href="${dipHref(a.id, 'ledger')}">Verdict ledger</a></li>`).join('')}</ul>` : '<p class="empty">The run stored no dips.</p>';
  $('#panelcards').innerHTML = D.panel.length ? D.panel.map(r => `<article class="card"><h2>${esc(NAME(r.id))} <span class="sub mono" title="reviewer id">${esc(r.id)}</span></h2>
    <p style="margin:6px 0 0">${kindTag(r.kind)}</p>
    <p class="muted" style="margin:6px 0 0;font-size:13px">${r.kind === 'simulated' ? 'A Probe: a deterministic matched-filter detector that marks dips above an SNR threshold in the light curve. It is not a person.' : isSentinel(r.kind) ? `A Sentinel: an AI model (${esc(PROV(r.id) || PROVIDER_OF(r.kind))}) that reads the plotted light curve and marks dips. It is not a person.${(D.reviewer_provenance[r.id] || {}).calibration === 'uncalibrated' ? ' <b>Uncalibrated:</b> it votes at the floor weight until it is calibrated on this provider and model.' : ''}` : ''}</p>
    <dl class="kv">
      <dt>weight in this run</dt><dd>${r.run_weight === null || r.run_weight === undefined ? 'not stored' : esc(r.run_weight)} <span class="muted">(manifest.json)</span></dd>
      <dt>calibrated weight</dt><dd>${r.calibrated_weight === null || r.calibrated_weight === undefined ? 'not in the weights file' : fmt(r.calibrated_weight,3)}${D.weights_path ? `<small class="muted" style="display:block;font-size:11px">${esc(D.weights_path)}</small>` : ''}</dd>
      <dt>marks</dt><dd>${r.n_marks} span${r.n_marks===1?'':'s'} on ${r.n_subjects} subject${r.n_subjects===1?'':'s'}</dd>
      <dt>labels</dt><dd>${Object.entries(r.labels).map(([k,v]) => `${esc(k.replace(/_/g,' '))} ${v}`).join(' · ') || 'none'}</dd>
      <dt>dips marked</dt><dd>${r.marked_dips.length} of ${D.dossier_ids.length}<div class="marks">${r.marked_dips.map(dipLink).join('') || '<span class="muted">none</span>'}</div></dd>
    </dl></article>`).join('') : '<p class="empty">The manifest lists no reviewers.</p>';
}

// ---------- calibration plane ----------
// x = false-alarm rate (FPR on empty subjects), y = recall (TPR on injected transits), point size =
// calibrated weight, with the lines of constant weight = TPR − FPR (floored). Stored values only.
const fmtN = p => (p.n_injected !== null && p.n_injected !== undefined) ? `${p.n_injected} injected, ${p.n_empty} empty` : 'sample size not stored';
function calSample(){
  const pts = D.calibration.points, cl = pts.filter(p => isSentinel(p.kind) && !p.uncalibrated), sim = pts.filter(p => p.kind === 'simulated');
  const sizes = list => [...new Set(list.map(fmtN))];
  const parts = [];
  // The scores themselves, in one line: the Sentinels' weights and the Probes' range.
  const range = list => { const w = list.map(p => p.weight).filter(x => x !== null && x !== undefined); if (!w.length) return 'not stored'; const lo = Math.min(...w), hi = Math.max(...w); return lo === hi ? fmt(lo,2) : `${fmt(lo,2)} to ${fmt(hi,2)}`; };
  if (cl.length || sim.length) parts.push(`Calibrated weights: ${cl.length ? `Sentinels ${range(cl)}` : ''}${cl.length && sim.length ? '; ' : ''}${sim.length ? `Probes ${range(sim)}` : ''}.`);
  if (cl.length) parts.push(`<b>The Sentinels were calibrated on ${esc(sizes(cl).join(' / '))} subjects only.</b>`);
  if (sim.length) parts.push(`The Probes (code, not people) on ${esc(sizes(sim).join(' / '))}.`);
  const n = Math.max(0, ...pts.map(p => p.n_injected || 0));
  if (n) parts.push(`With ${n} injected subjects a recall moves in steps of ${fmt(1 / n, 2)}, so one subject more or less changes a weight by that much. These weights are rough.`);
  return parts.join(' ');
}
function calPlane(box){
  box.innerHTML = '';
  const C = D.calibration, pts = C.points.filter(p => p.tpr !== null && p.tpr !== undefined && p.fpr !== null && p.fpr !== undefined);
  if (!C.points.length){ box.innerHTML = '<p class="empty">No weights file was given to this build.</p>'; return; }
  if (!pts.length){ box.innerHTML = '<p class="empty">The weights file stores no recall or false-alarm rates, so there is nothing to plot.</p>'; return; }
  // pad keeps a point at FPR 0 clear of the axis labels. Narrow drops the floor-region note and the rotated
  // weight labels: each weight is written level, above the right-hand end of its line, in a top band of its own.
  const W = Math.min(560, Math.max(260, box.clientWidth || 520)), narrow = W < 420, pl = 46, pr = 14, pt = narrow ? 40 : 12, pb = 42;
  const pad = 14, side = W - pl - pr - pad, H = pt + side + pb;
  const X = v => pl + pad + v * side, Y = v => pt + (1 - v) * side, R = w => 3 + 10 * Math.max(0, Number(w) || 0);
  const groups = [];
  for (const p of pts){ let g = groups.find(g => g.fpr === p.fpr && g.tpr === p.tpr && g.kind === (isSentinel(p.kind) ? 'claude' : p.kind)); if (!g){ g = {fpr: p.fpr, tpr: p.tpr, kind: isSentinel(p.kind) ? 'claude' : p.kind, items: []}; groups.push(g); } g.items.push(p); }
  const label = `Calibration plane: ${pts.length} reviewers by false-alarm rate and recall. ` + groups.map(g => `${g.items.map(p => NAME(p.id)).join(' and ')}: recall ${fmt(g.tpr,2)}, false-alarm rate ${fmt(g.fpr,2)}, weight ${fmt(g.items[0].weight,2)}`).join('; ') + '. ' + calSample().replace(/<[^>]+>/g, '');
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': label, class: 'calplane'}, box);
  svg.style.maxWidth = W + 'px';
  // The floor: below TPR − FPR = floor every reviewer gets the floor weight.
  const f = C.floor;
  el('polygon', {points: `${X(0) - pad},${Y(f)} ${X(0)},${Y(f)} ${X(1-f)},${Y(1)} ${X(1)},${Y(1)} ${X(1)},${Y(0)} ${X(0) - pad},${Y(0)}`, class: 'floor'}, svg);
  for (const t of [0, 0.2, 0.4, 0.6, 0.8, 1]){
    el('line', {x1: X(t), x2: X(t), y1: Y(0), y2: Y(0) + 4, stroke: 'var(--ink-3)'}, svg); tx(svg, X(t), Y(0) + 16, String(t), 'middle');
    el('line', {x1: X(0) - pad - 4, x2: X(0) - pad, y1: Y(t), y2: Y(t), stroke: 'var(--ink-3)'}, svg); tx(svg, X(0) - pad - 7, Y(t) + 4, String(t), 'end');
  }
  el('rect', {x: X(0) - pad, y: Y(1), width: side + pad, height: side, fill: 'none', stroke: 'var(--line-2)'}, svg);
  tx(svg, X(0.5), H - 6, 'false-alarm rate (FPR, empty subjects)', 'middle', 'lbl');
  const yl = tx(svg, 12, Y(0.5), 'recall (TPR, injected transits)', 'middle', 'lbl'); yl.setAttribute('transform', `rotate(-90 12 ${Y(0.5)})`);
  // Lines of constant weight: TPR = FPR + w. Wide: labelled along the line. Narrow: the weight sits level above
  // the line's right-hand end (every line ends on the top edge), with one heading line above them.
  if (narrow){
    tx(svg, X(0) - pad, pt - 24, 'lines of weight:', 'start', 'isolbl');
    if (C.iso.includes(f)) tx(svg, X(1) + pr - 2, pt - 24, `${f} is the floor`, 'end', 'isolbl floorlbl');
  }
  for (const w of C.iso){
    el('line', {x1: X(0), y1: Y(w), x2: X(1 - w), y2: Y(1), class: w === f ? 'iso floorline' : 'iso'}, svg);
    if (narrow){
      el('line', {x1: X(1 - w), x2: X(1 - w), y1: Y(1) - 4, y2: Y(1), class: w === f ? 'iso floorline' : 'iso'}, svg);
      tx(svg, X(1 - w), pt - 7, String(w), 'middle', w === f ? 'isolbl floorlbl' : 'isolbl');
      continue;
    }
    const a = w === f ? 0.55 : 0.72, lx = X(a * (1 - w)), ly = Y(w + a * (1 - w));
    const t = tx(svg, lx, ly - 5, w === f ? `weight ${w} (floor)` : `weight ${w}`, 'middle', 'isolbl'); t.setAttribute('transform', `rotate(-45 ${lx} ${ly})`);
  }
  if (!narrow) tx(svg, X(0.97), Y(0.30), `below the floor line: weight ${f}`, 'end');
  // The sample size, on the plane.
  const cl = pts.filter(p => isSentinel(p.kind));
  if (cl.length) tx(svg, X(0.97), Y(0.08), `Sentinels: ${fmtN(cl[0])} only`, 'end', 'samplelbl');
  if (pts.some(p => p.kind === 'simulated')) tx(svg, X(0.97), Y(0.08) + 14, `Probes: ${fmtN(pts.find(p => p.kind === 'simulated'))}`, 'end');
  for (const g of groups){
    const r = R(g.items[0].weight), cx = X(g.fpr), cy = Y(g.tpr);
    const c = el('circle', {cx, cy, r, class: g.kind === 'claude' ? 'pt cl' : 'pt sim'}, svg);
    el('title', {}, c).textContent = g.items.map(p => `${NAME(p.id)} (id ${p.id}; ${p.kind === 'simulated' ? 'Probe, not a person' : isSentinel(p.kind) ? `Sentinel, ${PROVIDER_OF(p.kind)}` : p.kind}): TPR ${fmt(p.tpr,2)}, FPR ${fmt(p.fpr,2)}, weight ${fmt(p.weight,2)}, ${fmtN(p)}`).join('\n');
    const word = g.kind === 'claude' ? 'Sentinel' : g.kind === 'simulated' ? 'Probe' : g.kind;
    tx(svg, cx + r + 6, cy + 4, `${plural(g.items.length, word)} · w ${fmt(g.items[0].weight,2)}`, 'start', 'lbl');
  }
  // S06: the plane answers on hover and on the arrow keys: the reviewers at the nearest false-alarm rate.
  if (typeof SetuUI !== 'undefined' && SetuUI.crosshair){
    const byX = groups.slice().sort((a, b) => a.fpr - b.fpr);
    svg.setAttribute('tabindex', '0');
    SetuUI.crosshair(svg, {x0: -(pl + pad) / side, x1: (W - pl - pad) / side, xs: byX.map(g => g.fpr), readout: $('#calread') || undefined,
      fmt: i => byX[i].items.map(p => `${NAME(p.id)}: false-alarm rate ${fmt(p.fpr,2)} · recall ${fmt(p.tpr,2)} · weight ${fmt(p.weight,2)}`).join('; ')});
  }
}
function renderCalibration(){
  const C = D.calibration;
  $('#calsample').innerHTML = C.points.some(p => p.n_injected) ? calSample() : 'The sample size is not stored with these weights.';
  calPlane($('#calplane'));
  const kindWord = k => k === 'simulated' ? 'Probe · not a person' : isSentinel(k) ? `Sentinel · ${esc(PROVIDER_OF(k))}` : esc(k);
  $('#caltable').innerHTML = C.points.length ? `<table><caption class="sr">Calibration rates and weights per reviewer, as stored</caption><thead><tr><th scope="col">reviewer</th><th scope="col">kind</th><th scope="col" class="num">recall (TPR)</th><th scope="col" class="num">false alarms (FPR)</th><th scope="col" class="num">weight</th><th scope="col">sample</th></tr></thead><tbody>${C.points.map(p => `<tr><th scope="row">${nameWithId(p.id)}</th><td>${kindWord(p.kind)}</td><td class="num">${fmt(p.tpr,2)}</td><td class="num">${fmt(p.fpr,2)}</td><td class="num">${p.uncalibrated ? `<b>uncalibrated</b><small>floor weight ${fmt(C.floor,2)} in a run</small>` : fmt(p.weight,2)}${p.consistent === false ? '<small>not max(TPR − FPR, floor)</small>' : ''}</td><td>${esc(fmtN(p))}</td></tr>`).join('')}</tbody></table>` : '';
  // On a phone the same rows read as one card per reviewer (the table is hidden there, the cards elsewhere).
  $('#calcards').innerHTML = C.points.map(p => `<dl class="kv calcard"><dt>reviewer</dt><dd><b>${nameWithId(p.id)}</b></dd><dt>kind</dt><dd>${kindWord(p.kind)}</dd><dt>recall (TPR)</dt><dd>${fmt(p.tpr,2)}</dd><dt>false alarms (FPR)</dt><dd>${fmt(p.fpr,2)}</dd><dt>weight</dt><dd>${p.uncalibrated ? `uncalibrated (floor weight ${fmt(C.floor,2)} in a run)` : fmt(p.weight,2)}${p.consistent === false ? ' (not max(TPR − FPR, floor))' : ''}</dd><dt>sample</dt><dd>${esc(fmtN(p))}</dd></dl>`).join('');
  $('#calsource').textContent = C.source ? `Rates: ${C.record_path || 'the weights file'}. ${C.source}` : (C.record_path ? `Rates: ${C.record_path}.` : '');
}
let calWidth = -1;
function resizeCalibration(){ const box = $('#calplane'); if (!box || $('#route-sentinels').hidden || box.clientWidth === calWidth) return; calWidth = box.clientWidth; calPlane(box); }

// ---------- runs ----------
function renderRuns(){
  const runs = D.catalog.runs.slice().reverse();
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  $('#runtable').innerHTML = runs.length ? `<ol class="runlines">${runs.map(x => { const ne = (x.errors||[]).length; return `<li>
      <div class="line"><b>${when(x.time)}</b><span>${plural(x.n_targets ?? (x.targets||[]).length, 'target')}</span>${x.new == null ? '' : `<span>${esc(x.new)} new</span>`}<span>${esc(x.known ?? '–')} known TOI</span><span>${esc(x.filtered_deep ?? '–')} filtered as too deep</span><span>${esc(x.filtered_single ?? '–')} filtered for too few transits</span><span class="${ne ? 'err' : 'muted'}">${ne ? plural(ne, 'error') : 'no errors'}</span></div>
      ${ne ? x.errors.map(e => `<pre class="err">${esc(e)}</pre>`).join('') : ''}
      ${(x.targets||[]).length ? `<details><summary>Targets</summary><p class="mono" style="margin:4px 0 0;font-size:12px">${(x.targets||[]).map(t => 'TIC ' + esc(t)).join(', ')}</p></details>` : ''}
      ${(x.tracebacks||[]).length ? `<details><summary>${plural(x.tracebacks.length, 'traceback')} (verbatim)</summary>${x.tracebacks.map(t => `<pre class="err">${esc(t)}</pre>`).join('')}</details>` : ''}</li>`; }).join('')}</ol>` : '<p class="empty">No search runs are stored in the catalogue.</p>';
  const c = D.config;
  const pk = Object.entries(c.packages || {});
  $('#runconfig').innerHTML = `<dl class="kv">
    <dt>config name</dt><dd>${esc(c.config_name)}</dd>
    <dt>config hash (sha256)</dt><dd>${esc(c.config_sha256)}</dd>
    <dt>created</dt><dd>${when(D.run.created_at)}</dd>
    <dt>SetuHQ</dt><dd>${esc(c.setuhq_version)}</dd>
    <dt>python</dt><dd>${esc(c.python)}</dd>
    <dt>platform</dt><dd>${esc(c.platform)}</dd>
    <dt>Sentinel prompt version</dt><dd>${esc(c.claude_prompt_version || 'not stored')}</dd>
    <dt>Sentinel providers</dt><dd>${Object.entries(D.reviewer_provenance || {}).map(([id, p]) => `${esc(NAME(id))}: ${esc(p.provider_label)} · ${esc(p.model)} · ${esc(p.calibration || 'calibration not stored')}`).join('<br>') || 'none in this run'}</dd>
    <dt>subject length</dt><dd>${esc(c.subject_days)} d</dd>
    <dt>skipped reviewers</dt><dd>${(c.skipped_reviewers_detail||[]).length ? c.skipped_reviewers_detail.map(s => `${esc(s.id)} (${esc(s.reason || 'unavailable')})`).join(', ') : (c.skipped_reviewers||[]).length ? esc(c.skipped_reviewers.join(', ')) : 'none'}</dd>
    <dt>archive cross-match</dt><dd>${xmConfig(D.crossmatch_info)}</dd>
    ${pk.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
  </dl>
  <h3 style="margin-top:14px">Measured inputs</h3>
  ${(c.inputs||[]).map(x => `<p style="margin:4px 0 0" class="mono">${esc(Object.entries(x).map(([k,v]) => k + ' ' + v).join(' · '))}</p>`).join('') || '<p class="empty">No inputs stored.</p>'}`;
  $('#catconfig').innerHTML = D.catalog.path ? `<dl class="kv"><dt>catalogue</dt><dd>${esc(D.catalog.path)}</dd><dt>config</dt><dd>${esc(D.catalog.config)}</dd><dt>config hash (sha256)</dt><dd>${esc(D.catalog.config_sha256)}</dd><dt>updated</dt><dd>${when(D.catalog.updated)}</dd><dt>targets reviewed</dt><dd>${esc(D.catalog.targets_reviewed)}</dd></dl>` : '<p class="empty">No search catalogue was given to this build.</p>';
}

// The archive cross-match this page was built from: the file, and when it is the repository's fallback,
// what the run's own cross-match stored (its status and its error, verbatim).
function xmConfig(x){
  if (!x) return 'not stored';
  if (x.fallback) return `${esc(x.file)} (fallback; run's own: ${esc(x.run_status || 'not stored')}${x.run_error ? ', ' + esc(x.run_error) : ''})`;
  if (x.status === 'not_run') return `not run (${esc(x.error || 'no error stored')})`;
  return `${esc(x.file)} (${esc(x.status)})`;
}


// ---------- the five sections' figures (Sky, Transit, Explorer, Sentinels) ----------
// Stored values only: the points are the run's stored flux, the marks the reviewers' stored spans,
// the scores, flags, rationales and confidences as stored. Decorative art is labelled as such.
const S = D.story;
// DIPS: the lead run's dips (the sky map and the panel read them); ALL_DIPS adds every other example run's.
const DIPS = S.dips, ALL_DIPS = DIPS.concat(D.showcase_dips || []), DIP_BY = Object.fromEntries(ALL_DIPS.map(d => [d.id, d]));
const CTX = d => (D.run_ctx || {})[d.run] || {star: S.star, planet: S.planet, lead: D.hero.lead};
const STC = {known: 'var(--blue)', open: 'var(--yellow)', rejected: 'var(--red)'};
const STC_SPACE = S.colours;  // the same colours as hex, for the space panels (dark in both themes)
const fmtSigned = (x, d) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d);
const dotPath = (pts, X, Y) => pts.map(p => `M${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}h0`).join('');
const transitHref = id => rtUrl('transit', {dip: id});
const tval = x => fmt(x, 2);
// The y range of a dip's window: from its depth and the scatter of its stored points outside the window.
function dipRange(list){
  let depth = 0, noise = 0;
  for (const d of list){
    depth = Math.max(depth, d.depth_ppm || 0);
    const out = d.pts.filter(p => p[0] < d.t_start - d.t || p[0] > d.t_end - d.t).map(p => p[1]);
    if (out.length > 3){ const m = out.reduce((a, b) => a + b, 0) / out.length; noise = Math.max(noise, Math.sqrt(out.reduce((a, b) => a + (b - m) * (b - m), 0) / out.length)); }
  }
  const D0 = Math.max(depth, 3 * noise, 80);
  return [-1.9 * D0, 1.1 * D0];
}

// ---------- Sky ----------
const sky = {known: true, open: true, rejected: true, rev: 'all'};
const REV_FILTERS = [['all', 'All'], ['sentinels', 'Sentinels'], ['probes', 'Probes only'], ['split', 'Split']];
function revOk(d){
  const w = d.who;
  if (sky.rev === 'sentinels') return w.sentinels > 0;
  if (sky.rev === 'probes') return w.sentinels === 0 && w.probes > 0;
  if (sky.rev === 'split') return (w.sentinels + w.probes) < (w.of_sentinels + w.of_probes);
  return true;
}
const skyShown = d => sky[d.status] && revOk(d);
// The Sky's filters live in the URL (#/sky?status=known,open&who=probes), like the Feed's sort: a viewer's
// change is a new history entry, a link opens the same view, and anything malformed falls back to the default.
const SKY_STATUS = ['known', 'open', 'rejected'], SKY_WHO = ['all', 'sentinels', 'probes', 'split'];
function decodeSkyView(params){
  const st = params.get('status'), who = params.get('who');
  let on = SKY_STATUS.slice();
  if (st === 'none') on = [];
  else if (st !== null){ const want = st.split(','); const ok = SKY_STATUS.filter(k => want.includes(k)); if (ok.length) on = ok; }
  return {status: on, who: SKY_WHO.includes(who) ? who : 'all'};
}
const encodeSkyView = v => `status=${v.status.length ? SKY_STATUS.filter(k => v.status.includes(k)).join(',') : 'none'}&who=${v.who}`;
const currentSky = () => ({status: SKY_STATUS.filter(k => sky[k]), who: sky.rev});
function applySky(v){ for (const k of SKY_STATUS) sky[k] = v.status.includes(k); sky.rev = v.who; }
// Survey-coverage layers on the sky map, kept in the URL as layers=... beside the filters.
const COVL = ((D.galaxy_meta && D.galaxy_meta.layers) || []).concat(D.sweep && D.sweep.n_sky ? ['sweep'] : []);
let skyLayers = [];
const decodeLayers = p => { const ls = (p.get('layers') || '').split(','); return COVL.filter(k => ls.includes(k)); };
function applySkyLayers(ls){
  skyLayers = ls;
  $$('#route-sky .covl').forEach(g => { g.style.display = ls.includes(g.dataset.layer) ? '' : 'none'; });
  $$('#skycov [data-cov]').forEach(b => b.setAttribute('aria-pressed', String(ls.includes(b.dataset.cov))));
}
function syncSkyURL(push){ if (current === 'sky') setHash('#/sky?' + encodeSkyView(currentSky()) + (skyLayers.length ? '&layers=' + skyLayers.join(',') : ''), !!push); }
if ($('#skycov')) $('#skycov').addEventListener('click', e => {
  const b = e.target.closest('button[data-cov]'); if (!b) return;
  const k = b.dataset.cov, on = skyLayers.includes(k);
  applySkyLayers(COVL.filter(x => x === k ? !on : skyLayers.includes(x))); syncSkyURL(true);
});
function renderSky(){
  const n = k => S.counts[k];
  // The zoom into the run star's system needs its stored example; without one the button stays hidden.
  $$('#route-sky [data-zoom]').forEach(el => { if (!(MX && MX.examples[el.dataset.zoom])) return; el.hidden = false; el.classList.add('on'); });
  $('#skychips').innerHTML = [['known', S.planet ? S.planet : 'Known'], ['open', 'Open'], ['rejected', 'Rejected']].map(([k, l]) =>
    `<button type="button" class="pill" data-st="${k}" aria-pressed="${sky[k]}" style="--c:${STC[k]}"><i></i>${esc(l)} <span class="n">${n(k)}</span></button>`).join('');
  $('#skyrev').innerHTML = REV_FILTERS.map(([k, l]) => `<button type="button" data-rev="${k}" aria-pressed="${sky.rev === k}">${esc(l)}</button>`).join('');
  const shown = DIPS.filter(skyShown);
  $('#skycount').textContent = `${shown.length} of ${DIPS.length}`;
  $('#skydips').innerHTML = shown.length ? shown.map(d => `<a class="dipitem" href="${transitHref(d.id)}" style="--c:${STC[d.status]}"><i></i><b>${esc(d.time_unit)} ${tval(d.t)}</b><span class="st">${esc(d.status_label)}</span><span class="sub">${fmt(d.depth_ppm, 0)} ppm · ${fmt(d.duration_hours, 2)} h · ${d.who.sentinels === d.who.of_sentinels && d.who.probes === d.who.of_probes ? `all ${d.who.of_sentinels + d.who.of_probes} reviewers` : `${d.who.probes} Probes, ${d.who.sentinels} Sentinels`} · ${esc(DIPPHRASE(d.outcome))}</span></a>`).join('')
    : '<p class="empty" style="margin:12px">No dips match.</p>';
  skyTimeline();
}
function skyTimeline(box = $('#skytimeline'), capEl = $('#skytlcap'), read = $('#skytlread')){
  if (!box) return;
  const subs = D.hero.subjects; if (!subs.length){ box.innerHTML = '<p class="empty">No light curve is stored.</p>'; return; }
  const a = subs[0].start, b = subs[subs.length - 1].end, W = 1000, H = 84;
  const [lo, hi] = [-700, 400], X = t => (t - a) / (b - a) * W, Y = v => 6 + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * 56;
  const pts = subs.map(s => s.t.map((t, i) => `M${X(t).toFixed(1)} ${Y(s.ppm[i]).toFixed(1)}h0`).join('')).join('');
  let ticks = '';
  for (const d of DIPS){ const on = skyShown(d), x = X(d.t).toFixed(1); ticks += `<path d="M${x} 66 V82" stroke="${on ? STC[d.status] : 'var(--line-2)'}" stroke-width="${on ? 2.5 : 1.5}" stroke-linecap="round"><title>${esc(d.time_unit)} ${tval(d.t)} · ${esc(d.status_label)}</title></path>`; }
  capEl.innerHTML = `<span>${esc(D.hero.time_unit)} ${fmt(a, 1)}</span><span>Stored brightness over the run, ${D.hero.n_points.toLocaleString('en-GB')} points; ticks: the dips shown above</span><span>${fmt(b, 1)}</span>`;
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Light curve of run ${esc(D.run.name)}: ${D.hero.n_points} stored points from ${esc(D.hero.time_unit)} ${fmt(a, 1)} to ${fmt(b, 1)}, with ${DIPS.filter(skyShown).length} of ${DIPS.length} dips ticked."><path d="${pts}" stroke="var(--ink)" stroke-width="1.1" stroke-linecap="round" opacity=".45"/>${ticks}</svg>`;
  // S06: the curve answers on hover and on the arrow keys, one stored point at a time (every 4th, for the keys).
  const xs = [], ys = [];
  if (read && window.SetuUI && SetuUI.crosshair){
    subs.forEach(s => s.t.forEach((t, i) => { if (i % 4 === 0){ xs.push(t); ys.push(s.ppm[i]); } }));
    SetuUI.crosshair(box.querySelector('svg'), {x0: a, x1: b, xs, readout: read, fmt: i => `${D.hero.time_unit} ${fmt(xs[i], 2)} · ${ys[i] < 0 ? '−' : '+'}${fmt(Math.abs(ys[i]), 0)} ppm`});
  }
}
// Zoom from the run star's marker into its system view (a magnifier; an illustration of scale).
function skyZoom(name, back){
  const m = $('#route-sky .skymark .skydot'), r = m ? m.getBoundingClientRect() : back.getBoundingClientRect();
  mxOpenSystem(name, back, {x: r.left + r.width / 2, y: r.top + r.height / 2, kind: 'sky'});
}
$('#route-sky').addEventListener('click', e => {
  const z = e.target.closest('.on[data-zoom]'); if (z){ skyZoom(z.dataset.zoom, z.tagName === 'BUTTON' ? z : $('#route-sky .skyzoom') || z); return; }
  const s = e.target.closest('button[data-st]'), r = e.target.closest('button[data-rev]');
  if (s){ sky[s.dataset.st] = !sky[s.dataset.st]; syncSkyURL(true); renderSky(); $(`#skychips button[data-st="${s.dataset.st}"]`).focus(); say(`${DIPS.filter(skyShown).length} of ${DIPS.length} dips shown.`); }
  if (r){ sky.rev = r.dataset.rev; syncSkyURL(true); renderSky(); $(`#skyrev button[data-rev="${r.dataset.rev}"]`).focus(); say(`${DIPS.filter(skyShown).length} of ${DIPS.length} dips shown.`); }
});

// ---------- Transit (the per-dip cockpit) ----------
const txs = {dip: null, cmp: []};
const PR_WEIGHTS = Object.fromEntries(((D.calibration || {}).points || []).map(p => [p.id, p.weight]));
// The transit, played back with the shared system view: the star from the catalogue (blackbody colour from its
// Teff, limb darkening), the planet crossing it, a limb-darkened model curve, and this dip's stored points and its
// stored limb-darkened fit.
// A dip matched to a known planet uses that planet's stored radii and orbit; any other dip shows what a planet
// as deep as the stored depth would cast, with the orbit and the impact parameter illustrative (b = 0).
function txTheatre(d){
  const known = d.status === 'known', k = d.ratio || 0, C = CTX(d), planet = C.planet;
  let starNote = 'the star is the target as the catalogue stores it', k2 = k;
  const star = typeof MX !== 'undefined' && MX && planet ? MX.examples[planet] || null : null;
  const model = (d.model || []).map(p => [p[0], p[1]]);
  let p, bNote;
  if (known && star){ p = Object.assign({name: planet}, star); bNote = `impact parameter ${star.impact_parameter != null ? 'as stored' : 'illustrative'}`; }
  else {
    // This dip's own shape: the stored fit's Rp/R★, b and limb darkening when a fit is stored, else Rp/R★ = √depth and
    // b = 0. The star is the run's own (its TIC Teff and radius as the run stored them); the period is illustrative.
    // The fit is the signal's joint fit, shared by all of its dips; where it stores a mid-time and a T14, the model is
    // drawn there (its own t0, its own duration), so it lies on the dashed stored fit.
    const SP = C.star_params || {}, kk = d.fit_k || k, fitted = !!d.fit_k, timed = fitted && d.fit_dt0 != null && !!d.fit_t14_hours;
    const teff = (star && star.star_teff) || SP.teff || null, rs = (star && star.star_radius) || SP.radius || null;
    const P = (!wrongP(d) && d.period_days) || (C.lead && !wrongP(d) && C.lead.period_days) || 6;
    const bb = fitted && d.fit_b != null ? d.fit_b : 0, chord = Math.sqrt(Math.max(1e-4, (1 + kk) ** 2 - bb * bb));
    const T14 = Math.max(0.02, (d.fit_t14_hours || d.duration_hours || 2) / 24), ars = P / (Math.PI * T14) * chord;
    p = {name: 'a planet this deep', star_teff: teff, star_radius: rs || 1, radius: kk * (rs || 1) * 6.957e8 / 7.1492e7,
      orbital_period: P, semi_major_axis: ars * (rs || 1) * 6.957e8 / 1.495978707e11,
      impact_parameter: bb, ld: fitted ? d.fit_ld : null, t0_offset_days: timed ? d.fit_dt0 : 0,
      look: 'silhouette'};  // a candidate is drawn as a silhouette at Rp/R★, never as planet art
    bNote = timed ? 'Rp/R★, b, limb darkening, mid-time and T14 from the signal\'s stored fit'
      : fitted ? 'Rp/R★, b and limb darkening from the signal\'s stored fit; only its depth is the fit\'s, the mid-time and duration are illustrative'
      : 'impact parameter illustrative (b = 0), not fitted';
    starNote = teff ? `the star: ${Math.round(teff).toLocaleString('en-GB')} K${rs ? ', ' + fmt(rs, 2) + ' R☉' : ''} (${SP.source || 'as stored'})` : 'the star\'s temperature is not stored (drawn at the Sun\'s)';
    k2 = kk;
  }
  $('#txcap').textContent = known && star ? `${planet}, from stored values` : 'what a planet this deep would cast';
  $('#txfoot').textContent = (known && star
      ? `${planet} and its star as ${MX.source} stores them (fetched ${MX.fetched_at.slice(0, 10)}): the line is a limb-darkened model from those values, not a fit to this dip; ${bNote}. The match says the planet is already known; it does not confirm the dip.`
      : `If it were a planet: Rp/R★ = ${d.fit_k ? fmt(k2, 4) + ' from the signal\'s stored fit' : '√depth = ' + fmt(k2, 4) + ', from the stored depth ' + fmt(d.depth_ppm, 0) + ' ppm'}; ${starNote}; orbit and period illustrative; ${bNote}.`)
    + ` Dots: the ${d.pts.length} stored flux values within ${fmt(d.half * 24, 1)} hours of mid-time (${esc(d.time_unit)} ${fmt(d.t, 3)}). ${model.length ? 'Dashed: the signal\'s stored limb-darkened fit, at this dip.' : 'No transit fit is stored for this dip.'} The star's surface texture is decorative.`;
  const {st, S: SS} = mxSystemView($('#txsysfig'), p, {dip: {pts: d.pts, model}, on: current === 'transit', caption: false});
  if (!(known && star)){ st.opt.sys.bSrc = d.fit_k ? 'stored fit' : 'illustrative'; mxKick(st); }
  // What the drawing shows, for the tests: the star's temperature and the model's depth at mid-transit (ppm).
  const fig = $('#txsysfig'), [lu1, lu2] = SS.ld || mxLd(SS.teff);
  fig.dataset.teff = String(Math.round(SS.teff)); fig.dataset.modelDepthPpm = String(Math.round((1 - mxFlux(SS.b, SS.k, lu1, lu2)) * 1e6));
  // The canonical pages for the planet (when the dip matches one) and the star.
  $('#txlinks').innerHTML = (known && planet && C.planet_page !== false ? objLink('planet', planet, planet + ' ›') : '') + (C.star && C.star.name && C.star_page !== false ? objLink('star', C.star.name, C.star.name + ' ›') : '');
}
function lanesHTML(d){
  const pct = v => Math.max(0, Math.min(100, (v + d.half) / (2 * d.half) * 100));
  const w0 = pct(d.t_start - d.t), w1 = pct(d.t_end - d.t);
  return `<span class="small">Who marked it · stored spans in this window; dashed outline: the consensus window</span>` + d.lanes.map(l => {
    const c = l.role === 'sentinel' ? 'var(--sen)' : 'var(--prb)';
    const spans = l.spans.map(([a, b]) => `<i class="${l.counted ? '' : 'uncounted'}" style="left:${pct(a).toFixed(1)}%;width:${Math.max(1.5, pct(b) - pct(a)).toFixed(1)}%"></i>`).join('');
    return `<div class="lane" style="--c:${c}"><span style="color:${l.role === 'sentinel' ? 'var(--sen)' : 'var(--prb-ink)'}" title="reviewer id ${esc(l.id)}">${esc(l.name)}</span><div class="track" role="img" aria-label="${esc(l.name)}: ${l.spans.length ? `${l.spans.length} span${l.spans.length === 1 ? '' : 's'} in this window, ${l.counted ? 'counted for this dip' : 'not counted'}` : 'no mark in this window'}"><span class="win" style="left:${w0.toFixed(1)}%;width:${Math.max(.5, w1 - w0).toFixed(1)}%"></span>${spans || '<em>no mark</em>'}</div></div>`;
  }).join('');
}
function quoteHTML(d){
  const q = d.quotes[0];
  if (!q && CTX(d).probes_only) return `<div class="quote"><p style="font-size:14px">${esc(D.probes_only_label)}: the Probes marked this run, and no Sentinel was in its configuration, so no Sentinel's words are stored.</p></div>`;
  if (!q) return `<div class="quote"><p style="font-size:14px">No Sentinel rationale is stored for this subject.</p></div>`;
  return `<div class="quote"><div class="who"><b title="reviewer id ${esc(q.id)}">${esc(q.name)}</b><span>${q.confidence === null || q.confidence === undefined ? 'confidence not stored' : 'confidence ' + fmt(q.confidence, 1)}</span></div>
    <p>“${esc(q.text)}”</p><small>Its stored rationale for subject ${esc(d.subject_label || d.subject)} (${esc(d.time_unit)} ${fmt(d.subject_start, 1)} to ${fmt(d.subject_end, 1)}), one per subject, not per dip. It ${q.marked ? 'marked' : 'did not mark'} this dip. A Sentinel is an AI model${PROV(q.id || '') ? ` (${esc(PROV(q.id))})` : ''}, not a person.</small></div>`;
}
// A dip whose stored BLS period is known not to be its planet's (docs/results/showcase.json): no period is drawn for it.
const wrongP = d => (CTX(d).period_wrong || []).includes(d.id);
function orbitHTML(d){
  const C = CTX(d), L = C.lead; if (!L || d.phase === null || d.phase === undefined) return '';
  if (wrongP(d) || (C.period_wrong || []).includes(L.dip)) return '';
  const ang = Math.PI / 2 + d.phase * 2 * Math.PI, px = 100 + 80 * Math.cos(ang), py = 100 + 80 * Math.sin(ang);
  const who = C.planet ? `${esc(C.planet)}'s orbit` : "the lead signal's orbit";
  const near = Math.abs(d.phase) < 0.02;
  return `<figure class="glass orbitfig"><svg viewBox="0 0 200 200" role="img" aria-label="Orbit seen from above, with this dip at phase ${fmtSigned(d.phase, 2)} of the lead signal; the transit point faces us (bottom).">
      <circle cx="100" cy="100" r="80" fill="none" stroke="var(--line-2)" stroke-width=".8"/>
      <line x1="100" y1="100" x2="100" y2="196" stroke="var(--line-2)" stroke-dasharray="2 4"/>
      <circle cx="100" cy="100" r="10" fill="var(--star)"/>
      <g class="orbitfast" style="transform-origin:100px 100px"><circle cx="100" cy="20" r="4" fill="var(--ink)"/></g>
      <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="6" fill="none" stroke="${STC[d.status]}" stroke-width="1.6"/>
    </svg><figcaption><b>Where this dip sits on ${who}.</b><br>Phase ${fmtSigned(d.phase, 2)} on the lead signal's stored BLS period (${fmt(L.period_days, 3)} d), t0 ${fmt(L.t0, 3)}. ${near ? 'At the transit point, facing us.' : 'Not at the transit point, so it is not a transit of that signal.'} The orbit is drawn to show phase only; not to scale.</figcaption></figure>`;
}
function trayHTML(){
  if (!txs.cmp.length) return '';
  const list = txs.cmp.map(id => DIP_BY[id]).filter(Boolean), [lo, hi] = dipRange(list), half = Math.max(...list.map(d => d.half));
  const W = 300, H = 100, X = dt => (dt + half) / (2 * half) * W, Y = v => 6 + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * (H - 12);
  return `<div class="glass tray"><div class="cap"><span>Compare · same scale (±${fmt(half * 24, 1)} h, ${fmt(lo, 0)} to ${fmt(hi, 0)} ppm)</span><button type="button" class="btn" id="cmpclear">Clear</button></div><div class="grid">${list.map(d => {
    const model = (d.model || []).length ? d.model.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('') : '';
    return `<a href="${transitHref(d.id)}" aria-current="${d.id === txs.dip}" style="--c:${STC_SPACE[d.status]}"><span class="h"><span style="color:#F5F5F7">${esc(d.time_unit)} ${tval(d.t)}</span><span>${esc(d.planet || d.status)}</span></span><svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><path d="${dotPath(d.pts, X, Y)}" stroke="#F5F5F7" stroke-width="2.4" stroke-linecap="round" opacity=".8"/><path d="${model}" stroke="${STC_SPACE[d.status]}" stroke-width="1.2" fill="none"/></svg></a>`; }).join('')}</div></div>`;
}
function renderTransit(){
  const d = DIP_BY[txs.dip] || DIP_BY[S.lead_dip]; if (!d) return;
  txs.dip = d.id;
  // The chips, Previous and Next stay within the dip's own run (its star).
  const RD = ALL_DIPS.filter(x => x.run === d.run), i = RD.indexOf(d), prev = RD[(i + RD.length - 1) % RD.length], next = RD[(i + 1) % RD.length], inCmp = txs.cmp.includes(d.id);
  $('#txkicker').textContent = d.status_label; $('#txkicker').style.color = STC[d.status];
  $('#h-transit').textContent = DIP_NAME(d.id) || `dip ${d.letter}`;
  $('#txsub').textContent = `${d.time_unit} ${tval(d.t)} · ${fmt(d.depth_ppm, 0)} ppm · ${fmt(d.duration_hours, 2)} hours · SNR ${fmt(d.snr, 1)} · ${DIPPHRASE(d.outcome)}`;
  $('#txcapword').textContent = d.outcome === 'rejected' ? 'The dip, played back' : 'The transit, played back';
  $('#txnav').innerHTML = `<a class="roundbtn" href="${transitHref(prev.id)}" aria-label="Previous dip, ${esc(prev.time_unit)} ${tval(prev.t)}">‹</a><a class="roundbtn" href="${transitHref(next.id)}" aria-label="Next dip, ${esc(next.time_unit)} ${tval(next.t)}">›</a><button type="button" class="cmpbtn" id="cmptoggle" aria-pressed="${inCmp}">${inCmp ? 'In compare' : 'Add to compare'}</button>`;
  $('#txchips').innerHTML = RD.map(x => `<a href="${transitHref(x.id)}" aria-current="${x.id === d.id}" style="--c:${STC[x.status]}" title="${esc(x.id)} · ${esc(x.status_label)}"><i></i>${esc(x.letter)} · ${tval(x.t)}</a>`).join('');
  // Keep the current dip's chip in view in the sideways-scrolling row (without moving the page).
  const row = $('#txchips'), chip = $('#txchips a[aria-current="true"]');
  if (row && chip) row.scrollLeft = chip.offsetLeft - (row.clientWidth - chip.offsetWidth) / 2;
  txTheatre(d);
  // V06: who marked it, each by its calibrated weight, converging on the stored panel score (setuhq.viz.panelring).
  const C = CTX(d);
  $('#txscore').innerHTML = SetuPanelRing.html(SetuPanelRing.dipModel(d, {weights: PR_WEIGHTS, provenance: D.reviewer_provenance, weights_path: D.weights_path,
    run: d.run || D.run.name, label: DIP_NAME(d.id) || '', probes_only: !!C.probes_only})) + `<p class="txverdict">${esc(d.verdict)}</p>`;
  SetuPanelRing.mount($('#txscore'));
  for (const f of $$('#route-transit .txinset')) f.hidden = f.dataset.run !== (d.run || D.run.name);
  $('#txlanes').innerHTML = lanesHTML(d);
  $('#txquote').innerHTML = quoteHTML(d);
  $('#txorbit').innerHTML = orbitHTML(d) + trayHTML();
  $('#txcase').innerHTML = `<a class="btn primary" href="${esc(dipHref(d.id))}">Open the full case file ›</a><span>Every check, the stored measurements, the verdict ledger and the archive provenance.</span>`;
  $('#txarchive').textContent = d.archive_line ? `Archive comparison: ${d.archive_line}. ${D.no_detection}` : '';
  $('#txjourney').innerHTML = d.journey || ''; $('#txlight').textContent = d.light || '';
  const cv = CTX(d).caveat; $('#txcaveat').hidden = !cv; $('#txcaveat').textContent = cv ? `What this run did not recover: ${cv}` + (wrongP(d) ? ' This dip\'s stored BLS period is not its planet\'s, so no period is given for it.' : '') : '';
}
function openTransit(dip){
  const n = $('#txnotice');
  if (dip && !DIP_BY[dip]){
    // An unknown dip id: say so, and rewrite the address to the lead dip (replace, not a new entry).
    n.textContent = `No dip ${dip} in run ${D.run.name}; showing the lead dip ${S.lead_dip}.`; n.hidden = false; say(n.textContent);
    dip = S.lead_dip; setHash(transitHref(dip), false);
  } else n.hidden = true;
  txs.dip = dip || txs.dip || S.lead_dip;
  if (!dip) setHash(transitHref(txs.dip), false);
  renderTransit();
}
function txSysShown(on){ const fig = $('#txsysfig'); if (fig && fig._mx){ fig._mx.on = on; if (on) mxKick(fig._mx); } }
$('#route-transit').addEventListener('click', e => {
  if (e.target.closest('#cmptoggle')){ const k = txs.cmp.indexOf(txs.dip); if (k >= 0) txs.cmp.splice(k, 1); else txs.cmp.push(txs.dip); renderTransit(); $('#cmptoggle').focus(); say(k >= 0 ? 'Removed from compare.' : 'Added to compare.'); }
  if (e.target.closest('#cmpclear')){ txs.cmp = []; renderTransit(); $('#cmptoggle').focus(); say('Compare cleared.'); }
});

// ---------- Explorer (the feed scatter) ----------
const EXF = S.explorer, STAR_COL = ['#FF9F0A', '#0A84FF', '#BF5AF2', '#30D158', '#FF375F', '#64D2FF'];
const TICS = [...new Set(EXF.map(f => f.tic))];
const ex = {stars: Object.fromEntries(TICS.map(t => [t, true])), fNew: true, fKnown: true, snrMin: 0, sel: EXF.length ? EXF[0].i : null};
const starColour = tic => STAR_COL[TICS.indexOf(tic) % STAR_COL.length];
const exShown = f => ex.stars[f.tic] && (f.status === 'new_candidate' ? ex.fNew : ex.fKnown) && (f.snr || 0) >= ex.snrMin;
// The Explorer's filters live in the URL beside the Feed table's sort and filter:
// #/explorer?sort=snr&filter=all&stars=all&snr=8&new=1&known=1 (stars: all, none or a list of TIC ids).
const EX_SNR = [0, 7, 8, 9, 10];
function decodeExView(params){
  const st = params.get('stars'), snr = Number(params.get('snr'));
  let stars = TICS.map(String);
  if (st === 'none') stars = [];
  else if (st !== null && st !== 'all'){ const want = st.split(','); const ok = TICS.map(String).filter(t => want.includes(t)); if (ok.length) stars = ok; }
  return {stars, snr: EX_SNR.includes(snr) ? snr : 0, new: params.get('new') !== '0', known: params.get('known') !== '0'};
}
// Parameters equal to their defaults are left out (all stars, any SNR, both statuses), so a plain
// #/explorer stays plain; decodeExView still reads them, so older, longer links keep working.
function encodeExView(v){
  const all = TICS.map(String), on = all.filter(t => v.stars.includes(t)), out = [];
  if (on.length !== all.length) out.push(`stars=${on.length ? on.join(',') : 'none'}`);
  if (v.snr) out.push(`snr=${v.snr}`);
  if (!v.new) out.push('new=0');
  if (!v.known) out.push('known=0');
  return out.join('&');
}
const currentEx = () => ({stars: TICS.map(String).filter(t => ex.stars[t]), snr: ex.snrMin, new: ex.fNew, known: ex.fKnown});
function applyEx(v){ for (const t of TICS) ex.stars[t] = v.stars.includes(String(t)); ex.snrMin = v.snr; ex.fNew = v.new; ex.fKnown = v.known; }
function renderExplorer(){
  if (!EXF.length){ $('#exscatter').innerHTML = '<p class="empty">No search catalogue was given to this build.</p>'; return; }
  const nNew = EXF.filter(f => f.status === 'new_candidate').length, nKnown = EXF.length - nNew;
  $('#exstars').innerHTML = TICS.map(t => `<button type="button" class="pill" data-tic="${t}" aria-pressed="${ex.stars[t]}" style="--c:${starColour(t)}"><i></i>TIC ${esc(t)}</button>`).join('');
  $('#exstatus').innerHTML = `<button type="button" data-f="fNew" aria-pressed="${ex.fNew}">New ${nNew}</button><button type="button" data-f="fKnown" aria-pressed="${ex.fKnown}">Known TOI ${nKnown}</button>`;
  const snrs = [0, 7, 8, 9, 10].filter(v => v === 0 || EXF.some(f => f.snr >= v));
  $('#exsnr').innerHTML = snrs.map(v => `<button type="button" data-snr="${v}" aria-pressed="${ex.snrMin === v}">${v ? 'SNR ' + v + '+' : 'Any SNR'}</button>`).join('');
  const shown = EXF.filter(exShown);
  $('#excount').textContent = `${shown.length} of ${EXF.length} shown`;
  // Fewer than three distinct periods make an almost empty plot: a compact table says the same, readably.
  // Distinct periods: values within 2 per cent of each other are one period (one signal's repeat transits).
  const periods = []; for (const p of shown.map(f => f.period_days || 0).sort((a, b) => a - b)) if (!periods.length || p > periods[periods.length - 1] * 1.02) periods.push(p);
  const box = $('#exscatter'), compact = periods.length < 3;
  box.classList.toggle('astable', compact);
  $('#h-scatter').textContent = compact ? `Entries by star and period (${periods.length} period${periods.length === 1 ? '' : 's'}: too few for a plot)` : 'Depth against period (period on a log scale)';
  $('#exfoot').hidden = compact;
  if (compact){
    const groups = []; for (const f of shown){ const k = f.tic + '|' + periods.findIndex(p => Math.abs((f.period_days || 0) - p) <= p * 0.02 + 1e-9); let g = groups.find(x => x.k === k); if (!g){ g = {k, f, list: []}; groups.push(g); } g.list.push(f); }
    const rng = (a, d) => { const lo = Math.min(...a), hi = Math.max(...a); return lo === hi ? fmt(lo, d) : `${fmt(lo, d)}–${fmt(hi, d)}`; };
    box.innerHTML = groups.length ? `<table class="excompact"><thead><tr><th scope="col">Star</th><th scope="col" class="num">Period (d)</th><th scope="col" class="num">Entries</th><th scope="col" class="num">Depth (ppm)</th><th scope="col" class="num">SNR</th><th scope="col">Status</th></tr></thead><tbody>${groups.map(g => `<tr><th scope="row"><button type="button" data-i="${g.list[0].i}" aria-pressed="${g.list.some(f => f.i === ex.sel)}" style="--c:${g.f.status === 'new_candidate' ? '#FFD60A' : starColour(g.f.tic)}"><i></i>TIC ${esc(g.f.tic)}</button></th><td class="num">${fmt(g.f.period_days, 3)}</td><td class="num">${g.list.length}</td><td class="num">${rng(g.list.map(f => f.depth_ppm), 0)}</td><td class="num">${rng(g.list.map(f => f.snr), 1)}</td><td>${esc(D.status_label[g.f.status] || g.f.status)}</td></tr>`).join('')}</tbody></table>`
      : '<p class="empty">No entry matches these filters.</p>';
    renderExSel(); return;
  }
  const per = shown.map(f => f.period_days).filter(p => p > 0), dep = shown.map(f => f.depth_ppm).filter(x => x > 0);
  // Log axis: the range widened to whole 1-2-5 steps, with a tick at each.
  const steps = []; for (let k = -2; k <= 4; k++) for (const m of [1, 1.5, 2, 3, 5, 7]) steps.push(m * Math.pow(10, k));
  const p0 = steps.filter(v => v <= Math.min(...per) / 1.1).pop() || 0.01, p1 = steps.find(v => v >= Math.max(...per) * 1.1) || 1e4;
  const dticks = niceTicks(0, Math.max(...dep) * 1.1, 4), d1 = dticks[dticks.length - 1] >= Math.max(...dep) ? dticks[dticks.length - 1] : Math.max(...dep) * 1.1;
  const X = p => (Math.log(p) - Math.log(p0)) / (Math.log(p1) - Math.log(p0)) * 100, Yp = dp => (1 - dp / d1) * 100;
  const pticks = steps.filter(p => p >= p0 && p <= p1);
  const grid = pticks.map(p => `M${X(p).toFixed(2)} 0V52`).join('') + dticks.map(v => `M0 ${(Yp(v) * .52).toFixed(2)}H100`).join('');
  box.innerHTML = `<svg viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true"><path d="${grid}" stroke="rgba(255,255,255,.07)" stroke-width="1" vector-effect="non-scaling-stroke"/></svg>`
    + shown.map(f => { const s = Math.round(7 + Math.max(0, (f.snr || 7) - 7) * 1.4), c = f.status === 'new_candidate' ? '#FFD60A' : starColour(f.tic);
      return `<button type="button" data-i="${f.i}" aria-pressed="${f.i === ex.sel}" aria-label="TIC ${esc(f.tic)}, period ${fmt(f.period_days, 3)} days, depth ${fmt(f.depth_ppm, 0)} ppm, SNR ${fmt(f.snr, 1)}, ${esc(D.status_label[f.status] || f.status)}, ${esc(D.unconfirmed)}" style="left:${X(f.period_days).toFixed(2)}%;top:${Yp(f.depth_ppm).toFixed(2)}%;--s:${s}px;--c:${c};--g:${Math.round(Math.max(0, (f.snr || 6) - 6) * 2)}px"><i></i></button>`; }).join('')
    + pticks.map(p => `<span class="ax" style="left:${X(p).toFixed(1)}%;bottom:-18px;transform:translateX(-50%)">${+p.toPrecision(3)}${p === pticks[pticks.length - 1] ? ' d' : ''}</span>`).join('')
    + dticks.map(v => `<span class="ax" style="left:2px;top:calc(${Yp(v).toFixed(1)}% - 14px)">${v.toLocaleString('en-GB')}${v === dticks[dticks.length - 1] ? ' ppm' : ''}</span>`).join('');
  renderExSel();
}
function renderExSel(){
  const f = EXF.find(x => x.i === ex.sel); if (!f){ $('#exsel').innerHTML = '<p class="empty">Pick a signal.</p>'; return; }
  const k = f.depth_ppm > 0 ? Math.sqrt(f.depth_ppm * 1e-6) : 0, isNew = f.status === 'new_candidate', c = isNew ? 'var(--yellow)' : 'var(--blue)';
  $('#exsel').innerHTML = `<p class="st" style="--c:${c}">${isNew ? 'New candidate · unconfirmed' : 'At a known TOI period · ' + esc(D.unconfirmed)}</p><h2>${ticLink(f.tic)}</h2>
    <svg viewBox="-110 -110 220 220" role="img" aria-label="Sketch: a star and a planet disc to scale from the stored depth (Rp/R* ${fmt(k, 4)}); the orbit is not to scale."><defs><radialGradient id="exs" cx="40%" cy="35%" r="70%"><stop offset="0" stop-color="#FFF4DA"/><stop offset=".7" stop-color="#FFC46B"/><stop offset="1" stop-color="#C2620F"/></radialGradient></defs>
      <circle r="100" fill="none" stroke="var(--line-2)" stroke-width=".8"/><circle r="46" fill="url(#exs)"/>
      <g class="orbit" style="transform-origin:0 0"><circle cx="100" cy="0" r="${Math.max(1.2, 46 * k).toFixed(2)}" fill="var(--ink)"/><circle cx="100" cy="0" r="10" fill="none" stroke="var(--line-3)" stroke-width=".8"/></g></svg>
    <p class="small" style="text-align:center">Planet disc to scale from depth: Rp/R* ${fmt(k, 4)} · orbit not to scale · no stellar radius stored</p>
    <dl class="statgrid"><div><dt>Period</dt><dd>${fmt(f.period_days, 3)} d</dd></div><div><dt>Depth</dt><dd>${fmt(f.depth_ppm, 0)} ppm</dd></div><div><dt>Duration</dt><dd>${fmt(f.duration_hours, 2)} h</dd></div><div><dt>SNR</dt><dd>${fmt(f.snr, 1)}</dd></div></dl>
    <p class="small">TESS sectors ${esc(f.sectors || 'not stored')}. Feed ${esc(entryNo(f.id))} for this star (stored id <span class="mono">${esc(f.id)}</span>). ${isNew ? '' : 'A TOI match compares a stored period with archive values. '}${esc(D.no_detection)}</p>`;
}
const _cap = s => s.charAt(0).toUpperCase() + s.slice(1);
$('#route-explorer').addEventListener('click', e => {
  const t = e.target.closest('#exstars button[data-tic]'), f = e.target.closest('#exstatus button[data-f]'), n = e.target.closest('button[data-snr]'), p = e.target.closest('#exscatter button[data-i]');
  if (t){ ex.stars[t.dataset.tic] = !ex.stars[t.dataset.tic]; syncFeedURL(true); renderExplorer(); $(`#exstars button[data-tic="${t.dataset.tic}"]`).focus(); say($('#excount').textContent); }
  else if (f){ ex[f.dataset.f] = !ex[f.dataset.f]; syncFeedURL(true); renderExplorer(); $(`#exstatus button[data-f="${f.dataset.f}"]`).focus(); say($('#excount').textContent); }
  else if (n){ ex.snrMin = +n.dataset.snr; syncFeedURL(true); renderExplorer(); $(`#exsnr button[data-snr="${n.dataset.snr}"]`).focus(); say($('#excount').textContent); }
  else if (p){ ex.sel = +p.dataset.i; for (const b of $$('#exscatter button[data-i]')) b.setAttribute('aria-pressed', String(+b.dataset.i === ex.sel)); renderExSel(); }
});

// ---------- Sentinels (the panel) ----------
const sen = {filter: 'all', sel: S.reviewers.length ? S.reviewers[0].id : null};
function renderSentinels(){
  const R = S.reviewers, probes = R.filter(r => r.role === 'probe'), sents = R.filter(r => r.role === 'sentinel');
  const ring = (list, rad, cls, col) => list.map((r, i) => { const a = (-90 + i * 360 / list.length) * Math.PI / 180, x = 180 + rad * Math.cos(a), y = 180 + rad * Math.sin(a), s = 4 + 14 * (r.weight || 0);
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${s.toFixed(1)}" fill="${col}"><title>${esc(r.name)} (id ${esc(r.id)}): weight ${fmt(r.weight, 2)}</title></circle>`; }).join('');
  $('#senring').innerHTML = `<svg viewBox="0 0 360 360" role="img" aria-label="The panel as an orbital diagram: ${probes.length} Probes on the inner ring and ${sents.length} Sentinels on the outer ring, each sized by its calibrated weight (${R.map(r => `${r.name} ${fmt(r.weight, 2)}`).join(', ')}).">
      <circle cx="180" cy="180" r="18" fill="#FFB340"/><circle cx="180" cy="180" r="80" fill="none" stroke="rgba(191,90,242,.35)" stroke-width=".8"/><circle cx="180" cy="180" r="150" fill="none" stroke="rgba(100,210,255,.35)" stroke-width=".8"/>
      <g class="orbit" style="transform-origin:180px 180px">${ring(probes, 80, 'p', '#BF5AF2')}</g>
      <g class="orbitslow" style="transform-origin:180px 180px">${ring(sents, 150, 's', '#64D2FF')}</g></svg>
    <figcaption>Inner ring: Probes. Outer ring: Sentinels. Size is calibrated weight. The motion is decorative.</figcaption>`;
  $('#senfilter').innerHTML = [['all', 'All'], ['sentinel', 'Sentinels'], ['probe', 'Probes']].map(([k, l]) => `<button type="button" data-sf="${k}" aria-pressed="${sen.filter === k}">${l}</button>`).join('');
  $('#sencards').innerHTML = R.filter(r => sen.filter === 'all' || r.role === sen.filter).map(r => {
    const c = r.role === 'sentinel' ? 'var(--sen)' : 'var(--prb-ink)', n = r.n_injected || 0;
    const sq = Array.from({length: n}, (_, q) => `<i class="${q < (r.hits || 0) ? 'on' : ''}"></i>`).join('');
    return `<button type="button" class="revcard" data-rev="${esc(r.id)}" aria-pressed="${sen.sel === r.id}" style="--c:${c}"><span><span class="nm">${esc(r.name)}</span><span class="kd">${r.role === 'sentinel' ? 'Sentinel, runs on Claude (Anthropic)' : 'Probe, deterministic matched filter'} · <span class="mono">${esc(r.id)}</span></span></span><span class="w" title="calibrated weight">${fmt(r.weight, 2)}</span>
      <span class="hits" role="img" aria-label="${r.hits ?? '–'} hits in ${n} planted transits; ${r.false_alarms ?? '–'} false alarms in ${r.n_empty ?? '–'} empty light curves">${sq}</span><span class="hitcap">${r.hits ?? '–'} of ${n} planted transits found · ${r.false_alarms ?? '–'} of ${r.n_empty ?? '–'} empty light curves marked</span></button>`; }).join('');
  const r = R.find(x => x.id === sen.sel) || R[0];
  if (r) $('#senmarked').innerHTML = `<span class="small">${esc(r.name)}: what it marked in this run (counted for the dip)</span><div class="grid">${DIPS.map(d => { const on = r.marked.includes(d.id);
    return `<a href="${transitHref(d.id)}" class="${on ? 'on' : ''}" style="--c:${on ? (r.role === 'sentinel' ? 'var(--sen)' : 'var(--prb-ink)') : 'var(--ink-3)'}"><b>${esc(d.letter)} · ${tval(d.t)}</b><span>${on ? 'marked' : 'no mark'}</span></a>`; }).join('')}</div>`;
}
$('#route-sentinels').addEventListener('click', e => {
  const f = e.target.closest('button[data-sf]'), c = e.target.closest('button.revcard');
  if (f){ sen.filter = f.dataset.sf; renderSentinels(); $(`#senfilter button[data-sf="${f.dataset.sf}"]`).focus(); }
  else if (c){ sen.sel = c.dataset.rev; renderSentinels(); $(`#sencards button[data-rev="${c.dataset.rev}"]`).focus(); }
});


// ---------- galaxy: every known exoplanet around the Sun (hand-written WebGL) ----------
const GXM = D.galaxy_meta || null;
const GX_FOV = 50 * Math.PI / 180;
// URL state: year, method, dist, multi, view (camera preset) and tour (stop); defaults are left out.
function decodeGalaxyView(params){
  const M = GXM.methods;
  let methods = M.slice();
  const ms = params.get('method');
  if (ms === 'none') methods = [];
  else if (ms){ const want = ms.split(',').filter(x => M.includes(x)); if (want.length) methods = M.filter(x => want.includes(x)); }
  let year = parseInt(params.get('year'), 10);
  if (!(year >= GXM.years[0] && year <= GXM.years[1])) year = GXM.years[1];
  let dist = Number(params.get('dist'));
  if (!GXM.dist_steps.includes(dist)) dist = 0;
  let view = params.get('view');
  if (!GXM.presets.includes(view)) view = GXM.presets[0];
  let tour = parseInt(params.get('tour'), 10);
  if (!(tour >= 1 && tour <= GXM.tour.length)) tour = 0;
  const ls = (params.get('layers') || '').split(',');
  return {year, methods, dist, multi: params.get('multi') === '1', view, tour, showcase: params.get('cards') === 'methods',
    layers: (GXM.layers || []).filter(k => ls.includes(k)), focus: (params.get('focus') || '').slice(0, 120)};
}
function encodeGalaxyView(v){
  const out = [];
  if (v.year !== GXM.years[1]) out.push('year=' + v.year);
  if (v.methods.length !== GXM.methods.length) out.push('method=' + (v.methods.length ? GXM.methods.filter(m => v.methods.includes(m)).join(',') : 'none'));
  if (v.dist) out.push('dist=' + v.dist);
  if (v.multi) out.push('multi=1');
  if (v.showcase) out.push('cards=methods');
  if (v.layers && v.layers.length) out.push('layers=' + GXM.layers.filter(k => v.layers.includes(k)).join(','));
  if (v.view !== GXM.presets[0]) out.push('view=' + v.view);
  if (v.tour) out.push('tour=' + v.tour);
  if (v.focus) out.push('focus=' + encodeURIComponent(v.focus));
  return out.join('&');
}
// Which planets the filters keep: discovered by the year, by a chosen method, within the distance,
// and (optionally) around a star with two or more planets in the dataset. Returns the counts and,
// per star, how many of its planets are shown.
function gxFilterCount(G, v){
  const P = G.planets, H = G.hosts, on = new Set(v.methods.map(m => G.methods.indexOf(m)));
  const lim = v.dist ? v.dist / G.ly_per_pc : Infinity, per = new Int32Array(H.n.length);
  let planets = 0, hosts = 0;
  for (let i = 0; i < P.n.length; i++){
    const h = P.h[i];
    if ((P.y[i] || 0) > v.year || !on.has(P.m[i]) || H.d[h] > lim || (v.multi && G.host_n[h] < 2)) continue;
    if (!per[h]) hosts++;
    per[h]++; planets++;
  }
  return {planets, hosts, per};
}

const gx = {G: null, ready: false, on: false, gl: null, view: null, cam: null, flight: null, raf: 0, last: 0, interacted: -1e9,
  play: null, tour: null, sel: -1, selPlanet: -1, hover: -1, aim: -1, dirty: true, frames: 0, per: null, shown: null,
  pointers: new Map(), drag: null, visible: false, auto: true, labels: null, cards: null, mw: 0, telAt: 0, byHost: null};
const gxRM = window.matchMedia('(prefers-reduced-motion: reduce)');
const gxPhone = window.matchMedia('(max-width: 699.98px)');
// The map's arrays live in assets/data/galaxy.json (same origin), fetched on the first visit.
function gxLoad(){
  if (!gx.loading) gx.loading = fetch('/assets/data/galaxy.json').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(G => { gx.G = G; return G; });
  return gx.loading;
}
const gxFmt = (x, d) => x == null ? '—' : x.toLocaleString('en-GB', {maximumFractionDigits: d, minimumFractionDigits: 0});
const gxSig = x => x == null ? '—' : (Math.abs(x) >= 100 ? gxFmt(x, 0) : Number(x.toPrecision(3)).toString());
function gxLy(pc){ const ly = pc * gx.G.ly_per_pc; return ly < 100 ? gxFmt(ly, 1) : gxFmt(ly, 0); }
function gxSmooth(a, b, x){ const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); }
const gxEase = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

// ---------- matrices (column-major, as WebGL reads them) ----------
function m4persp(fy, asp, n, f){ const t = 1 / Math.tan(fy / 2), nf = 1 / (n - f); return [t / asp, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) * nf, -1, 0, 0, 2 * f * n * nf, 0]; }
function v3norm(v){ const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
function v3cross(a, b){ return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function m4look(e, c, up){
  const z = v3norm([e[0] - c[0], e[1] - c[1], e[2] - c[2]]), x = v3norm(v3cross(up, z)), y = v3cross(z, x);
  return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
    -(x[0] * e[0] + x[1] * e[1] + x[2] * e[2]), -(y[0] * e[0] + y[1] * e[1] + y[2] * e[2]), -(z[0] * e[0] + z[1] * e[1] + z[2] * e[2]), 1];
}
function m4mul(a, b){ const o = new Float32Array(16); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++){ let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s; } return o; }
function gxEye(c){ c = c || gx.cam; const cp = Math.cos(c.pitch); return [c.tx + c.dist * cp * Math.cos(c.yaw), c.ty + c.dist * cp * Math.sin(c.yaw), c.tz + c.dist * Math.sin(c.pitch)]; }
function gxProject(x, y, z){
  const m = gx.mvp, cw = m[3] * x + m[7] * y + m[11] * z + m[15];
  if (cw <= 1e-6) return null;
  const cx = m[0] * x + m[4] * y + m[8] * z + m[12], cy = m[1] * x + m[5] * y + m[9] * z + m[13];
  return [(cx / cw * .5 + .5) * gx.cssW, (.5 - cy / cw * .5) * gx.cssH, cw];
}

// ---------- shaders ----------
const GX_PT_VS = 'attribute vec3 a_pos;attribute float a_size;attribute vec3 a_col;uniform mat4 u_mvp;uniform float u_px;uniform float u_scale;uniform vec3 u_eye;varying float v_face;uniform float u_alpha;varying vec3 v_col;varying float v_a;' +
  'void main(){gl_Position=u_mvp*vec4(a_pos*u_scale,1.0);v_face=dot(a_pos,u_eye-a_pos*u_scale);gl_PointSize=a_size*u_px;v_col=a_col;v_a=u_alpha;if(a_size<=0.0){gl_Position=vec4(2.0,2.0,2.0,1.0);gl_PointSize=0.0;}}';
const GX_PT_FS = 'precision mediump float;varying vec3 v_col;varying float v_a;varying float v_face;uniform float u_flat;' +
  'void main(){vec2 q=gl_PointCoord*2.0-1.0;float r=dot(q,q);if(r>1.0)discard;if(u_flat>0.5){if(v_face<0.0)discard;gl_FragColor=vec4(v_col,1.0);return;}float core=1.0-smoothstep(0.0,0.42,r);float halo=exp(-r*3.5)*0.55;gl_FragColor=vec4(v_col*(core+halo)*v_a,1.0);}';
const GX_LN_VS = 'attribute vec3 a_pos;uniform mat4 u_mvp;uniform float u_scale;uniform vec3 u_off;uniform float u_fade;varying float v_f;' +
  'void main(){vec3 p=a_pos*u_scale+u_off;gl_Position=u_mvp*vec4(p,1.0);v_f=u_fade>0.0?1.0-smoothstep(0.5,1.0,length(a_pos.xy)/u_fade):1.0;}';
const GX_LN_FS = 'precision mediump float;uniform vec4 u_col;varying float v_f;void main(){gl_FragColor=vec4(u_col.rgb*u_col.a*v_f,1.0);}';
const GX_MESH_VS = 'attribute vec3 a_pos;attribute vec3 a_col;uniform mat4 u_mvp;uniform float u_scale;uniform vec3 u_eye;varying vec3 v_col;varying float v_face;' +
  'void main(){gl_Position=u_mvp*vec4(a_pos*u_scale,1.0);v_col=a_col;v_face=dot(a_pos,u_eye-a_pos*u_scale);}';
const GX_MESH_FS = 'precision mediump float;varying vec3 v_col;varying float v_face;uniform float u_inside;' +
  'void main(){if((u_inside>0.5&&v_face>0.0)||(u_inside<0.5&&v_face<0.0))discard;gl_FragColor=vec4(v_col,1.0);}';
const GX_MW_VS = 'attribute vec2 a_q;uniform mat4 u_mvp;uniform vec3 u_gc;uniform float u_R;varying vec2 v_p;' +
  'void main(){v_p=a_q*u_R/1000.0;gl_Position=u_mvp*vec4(u_gc+vec3(a_q*u_R,0.0),1.0);}';
const GX_MW_FS = 'precision mediump float;varying vec2 v_p;uniform float u_alpha;' +
  'void main(){float r=length(v_p);float c=cos(0.47),s=sin(0.47);vec2 b=vec2(v_p.x*c+v_p.y*s,-v_p.x*s+v_p.y*c);' +
  'float bulge=exp(-(b.x*b.x/22.0+b.y*b.y/6.0));float core=exp(-r*r/1.5);float disc=exp(-r/12.0)*(1.0-smoothstep(40.0,52.0,r))*0.2;' +
  'vec3 col=vec3(1.0,0.74,0.45)*(bulge*0.5+core*0.65)+vec3(0.5,0.62,0.85)*disc;gl_FragColor=vec4(col*u_alpha,1.0);}';

function gxProgram(gl, vs, fs, attrs, unis){
  const p = gl.createProgram();
  for (const [t, s] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]){
    const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
    gl.attachShader(p, sh);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const o = {p, a: {}, u: {}};
  for (const a of attrs) o.a[a] = gl.getAttribLocation(p, a);
  for (const u of unis) o.u[u] = gl.getUniformLocation(p, u);
  return o;
}
function gxBuf(gl, data, usage){ const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, usage || gl.STATIC_DRAW); return b; }
function gxHex(c){ return [parseInt(c.slice(1, 3), 16) / 255, parseInt(c.slice(3, 5), 16) / 255, parseInt(c.slice(5, 7), 16) / 255]; }

// ---------- geometry ----------
function gxLines(){
  const G = gx.G, out = {};
  // The Galactic-plane grid: 21 lines each way from -10 to 10, scaled per level.
  const grid = [];
  for (let k = -10; k <= 10; k++){ grid.push(k, -10, 0, k, 10, 0, -10, k, 0, 10, k, 0); }
  out.grid = new Float32Array(grid);
  // The celestial sphere: RA meridians every 30° and Dec parallels every 30°, rotated into galactic axes.
  const R = [[-0.0548755604162154, -0.8734370902348850, -0.4838350155487132], [0.4941094278755837, -0.4448296299600112, 0.7469822444972189], [-0.8676661490190047, -0.1980763734312015, 0.4559837761750669]];
  const gal = (ra, dec) => { const a = ra * Math.PI / 180, d = dec * Math.PI / 180, v = [Math.cos(d) * Math.cos(a), Math.cos(d) * Math.sin(a), Math.sin(d)]; return R.map(r => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]); };
  const sph = [], eq = [];
  for (let ra = 0; ra < 360; ra += 30) for (let d = -90; d < 90; d += 5) sph.push(...gal(ra, d), ...gal(ra, d + 5));
  for (const dec of [-60, -30, 30, 60]) for (let ra = 0; ra < 360; ra += 5) sph.push(...gal(ra, dec), ...gal(ra + 5, dec));
  for (let ra = 0; ra < 360; ra += 4) eq.push(...gal(ra, 0), ...gal(ra + 4, 0));
  out.sphere = new Float32Array(sph); out.equator = new Float32Array(eq);
  const ring = [];
  for (let a = 0; a < 360; a += 3){ const t = a * Math.PI / 180, u = (a + 3) * Math.PI / 180; ring.push(Math.cos(t), Math.sin(t), 0, Math.cos(u), Math.sin(u), 0); }
  out.ring = new Float32Array(ring);
  out.axes = new Float32Array([-1, 0, 0, 1, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, -1, 0, 0, 1]);
  return out;
}
// The Milky Way, procedural: four logarithmic arms (pitch 12°) placed so the Sun sits between two of
// them on a short spur, plus a bar. An artist's impression, labelled as one; not data.
function gxMilkyWay(){
  let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const gcx = gx.G.sun_to_gc_ly, b = Math.tan(12 * Math.PI / 180), r0 = 4000, pos = [], size = [], col = [];
  const push = (x, y, z, s, c) => { pos.push(gcx + x, y, z); size.push(s); col.push(...c); };
  const phase0 = Math.PI - Math.log(22000 / r0) / b;
  for (let arm = 0; arm < 4; arm++){
    const ph = phase0 + arm * Math.PI / 2;
    for (let i = 0; i < 5200; i++){
      const th = rnd() * Math.log(52000 / r0) / b, r = r0 * Math.exp(b * th) * (1 + gauss() * 0.06), a = th + ph + gauss() * 0.05;
      const k = Math.min(1, r / 30000), c = [0.55 + 0.25 * (1 - k), 0.62 + 0.18 * (1 - k), 0.95];
      push(r * Math.cos(a), r * Math.sin(a), gauss() * 280, 1.2 + rnd() * 1.6, c.map(v => v * (0.35 + rnd() * 0.5)));
    }
  }
  // The Orion spur through the Sun's place (the Sun is at angle 180°, 26,000 ly from the centre here).
  const phs = Math.PI - Math.log(gcx / r0) / b;
  for (let i = 0; i < 1600; i++){
    const th = Math.log(gcx / r0) / b + (rnd() - .5) * 0.5, r = r0 * Math.exp(b * th) * (1 + gauss() * 0.03), a = th + phs + gauss() * 0.03;
    push(r * Math.cos(a), r * Math.sin(a), gauss() * 200, 1.1 + rnd() * 1.2, [0.42, 0.5, 0.72].map(v => v * (0.5 + rnd() * 0.4)));
  }
  for (let i = 0; i < 5000; i++){
    const x = gauss() * 9000, y = gauss() * 3200, c = Math.cos(0.47), s = Math.sin(0.47);
    push(x * c - y * s, x * s + y * c, gauss() * 700, 1.4 + rnd() * 1.8, [1.0, 0.72, 0.42].map(v => v * (0.25 + rnd() * 0.45)));
  }
  return {pos: new Float32Array(pos), size: new Float32Array(size), col: new Float32Array(col), n: size.length};
}

function gxInitGL(){
  const cv = $('#gxcanvas');
  let gl = null;
  try { gl = cv.getContext('webgl', {antialias: true, alpha: false, depth: false, powerPreference: 'high-performance'}); } catch (e) { gl = null; }
  if (!gl) return false;
  gx.gl = gl;
  gx.pt = gxProgram(gl, GX_PT_VS, GX_PT_FS, ['a_pos', 'a_size', 'a_col'], ['u_mvp', 'u_px', 'u_alpha', 'u_scale', 'u_flat', 'u_eye']);
  gx.ln = gxProgram(gl, GX_LN_VS, GX_LN_FS, ['a_pos'], ['u_mvp', 'u_scale', 'u_off', 'u_fade', 'u_col']);
  gx.mwp = gxProgram(gl, GX_MW_VS, GX_MW_FS, ['a_q'], ['u_mvp', 'u_gc', 'u_R', 'u_alpha']);
  gx.mesh = gxProgram(gl, GX_MESH_VS, GX_MESH_FS, ['a_pos', 'a_col'], ['u_mvp', 'u_scale', 'u_eye', 'u_inside']);
  const H = gx.G.hosts, n = H.n.length, pos = new Float32Array(n * 3);
  for (let h = 0; h < n; h++){ pos[h * 3] = H.x[h]; pos[h * 3 + 1] = H.y[h]; pos[h * 3 + 2] = H.z[h]; }
  gx.hostPos = pos;
  gx.bHostPos = gxBuf(gl, pos);
  gx.bHostSize = gxBuf(gl, new Float32Array(n), gl.DYNAMIC_DRAW);
  gx.bHostCol = gxBuf(gl, new Float32Array(n * 3), gl.DYNAMIC_DRAW);
  gx.bSun = [gxBuf(gl, new Float32Array([0, 0, 0])), gxBuf(gl, new Float32Array([9])), gxBuf(gl, new Float32Array(gxHex('#FFB340')))];
  const L = gxLines();
  gx.lines = {};
  for (const k of Object.keys(L)) gx.lines[k] = {b: gxBuf(gl, L[k]), n: L[k].length / 3};
  gx.bQuad = gxBuf(gl, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]));
  // Survey coverage: filled patches on the celestial sphere (TESS sectors, and the sky no transit survey
  // has covered), and footprint outlines (Kepler with its cone from the Sun, K2, CoRoT, the bulge).
  const C = gx.G.coverage;
  if (C){
    // Filled patches: two triangles per 4° quad, one shade per TESS sector bucket, and the never-observed sky in grey.
    const blue = gxHex(C.colours.tess), grey = gxHex(C.colours.unmapped), M = C.mesh, st = M.step;
    const R = [[-0.0548755604162154, -0.8734370902348850, -0.4838350155487132], [0.4941094278755837, -0.4448296299600112, 0.7469822444972189], [-0.8676661490190047, -0.1980763734312015, 0.4559837761750669]];
    const gal = (ra, dec) => { const a = ra * Math.PI / 180, d = dec * Math.PI / 180, v = [Math.cos(d) * Math.cos(a), Math.cos(d) * Math.sin(a), Math.sin(d)]; return R.map(r => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]); };
    const tri = (want) => {
      const pos = [], col = [];
      for (let j = 0; j < 180 / st; j++) for (let i = 0; i < 360 / st; i++){
        const c = want(j * (360 / st) + i); if (!c) continue;
        const ra0 = i * st, ra1 = ra0 + st, d0 = -90 + j * st, d1 = d0 + st, A = gal(ra0, d0), B = gal(ra1, d0), Cc = gal(ra1, d1), Dd = gal(ra0, d1);
        pos.push(...A, ...B, ...Cc, ...A, ...Cc, ...Dd); for (let k = 0; k < 6; k++) col.push(...c);
      }
      return {pos: gxBuf(gl, new Float32Array(pos)), col: gxBuf(gl, new Float32Array(col)), n: pos.length / 3};
    };
    gx.cov = {tess: tri(q => { const n = M.tess[q]; return n ? blue.map(v => v * (n >= 13 ? .34 : n >= 3 ? .2 : .1)) : null; }),
      unmapped: tri(q => M.unmapped[q] ? grey.map(v => v * .42) : null), lines: {}};
    for (const k of ['kepler', 'k2', 'corot', 'bulge']){ const a = new Float32Array(C.lines[k]); gx.lines['cov_' + k] = {b: gxBuf(gl, a), n: a.length / 3}; }
  }
  gx.mwData = null;
  return true;
}
function gxPoints(prog, pos, size, col, n, alpha, scale, px, flat){
  const gl = gx.gl;
  gl.useProgram(prog.p);
  gl.uniform1f(prog.u.u_flat, flat ? 1 : 0);
  gl.uniform3fv(prog.u.u_eye, gxEye());
  gl.uniformMatrix4fv(prog.u.u_mvp, false, gx.mvp);
  gl.uniform1f(prog.u.u_px, px || gx.dpr);
  gl.uniform1f(prog.u.u_scale, scale || 1);
  gl.uniform1f(prog.u.u_alpha, alpha);
  for (const [b, a, k] of [[pos, 'a_pos', 3], [size, 'a_size', 1], [col, 'a_col', 3]]){
    gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(prog.a[a]); gl.vertexAttribPointer(prog.a[a], k, gl.FLOAT, false, 0, 0);
  }
  gl.drawArrays(gl.POINTS, 0, n);
}
function gxLine(name, scale, off, rgba, fade){
  const gl = gx.gl, L = gx.lines[name], p = gx.ln;
  gl.useProgram(p.p);
  gl.uniformMatrix4fv(p.u.u_mvp, false, gx.mvp);
  gl.uniform1f(p.u.u_scale, scale); gl.uniform3fv(p.u.u_off, off); gl.uniform1f(p.u.u_fade, fade || 0); gl.uniform4fv(p.u.u_col, rgba);
  gl.bindBuffer(gl.ARRAY_BUFFER, L.b); gl.enableVertexAttribArray(p.a.a_pos); gl.vertexAttribPointer(p.a.a_pos, 3, gl.FLOAT, false, 0, 0);
  gl.drawArrays(gl.LINES, 0, L.n);
}
function gxResize(){
  const cv = $('#gxcanvas'), r = cv.getBoundingClientRect();
  gx.dpr = Math.min(window.devicePixelRatio || 1, gxPhone.matches ? 1.5 : 2);
  gx.cssW = r.width; gx.cssH = r.height;
  const w = Math.max(1, Math.round(r.width * gx.dpr)), h = Math.max(1, Math.round(r.height * gx.dpr));
  if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
  gx.cards = null;
  gxKick();
}
function gxDraw(){
  const gl = gx.gl, cv = gl.canvas, c = gx.cam, d = c.dist, eye = gxEye();
  gl.viewport(0, 0, cv.width, cv.height);
  gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
  const proj = m4persp(GX_FOV, cv.width / cv.height, Math.max(0.05, d * 0.002), d * 40 + 400000);
  gx.mvp = m4mul(proj, m4look(eye, [c.tx, c.ty, c.tz], [0, 0, 1]));
  // Survey coverage first: the cells are opaque, and everything else is drawn on top of them.
  if (gx.cov && gx.view.layers.length){
    const ly = gx.view.layers, R = d * 0.62, inside = Math.hypot(...eye) < R;
    // One layer of the sphere only (the near half from outside, the far half from inside), drawn opaque
    // without blending, so the shading is even and nothing doubles up.
    gl.disable(gl.BLEND);
    const m = gx.mesh; gl.useProgram(m.p); gl.uniformMatrix4fv(m.u.u_mvp, false, gx.mvp); gl.uniform1f(m.u.u_scale, R); gl.uniform3fv(m.u.u_eye, eye); gl.uniform1f(m.u.u_inside, inside ? 1 : 0);
    for (const k of ['tess', 'unmapped']) if (ly.includes(k)){
      const c = gx.cov[k];
      gl.bindBuffer(gl.ARRAY_BUFFER, c.pos); gl.enableVertexAttribArray(m.a.a_pos); gl.vertexAttribPointer(m.a.a_pos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, c.col); gl.enableVertexAttribArray(m.a.a_col); gl.vertexAttribPointer(m.a.a_col, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, c.n);
    }
    gl.enable(gl.BLEND);
    for (const k of ['kepler', 'k2', 'corot', 'bulge']) if (ly.includes(k)) gxLine('cov_' + k, R, [0, 0, 0], gxHex(gx.G.coverage.colours[k]).concat([0.85]));
  }
  // The Milky Way fades in as the camera pulls out past ~9,000 ly; drawn only while it shows (culled otherwise).
  gx.mw = gxSmooth(9000, 42000, d);
  if (gx.mw > 0.01){
    if (!gx.mwData){
      const M = gxMilkyWay();
      gx.mwData = {n: M.n, pos: gxBuf(gl, M.pos), size: gxBuf(gl, M.size), col: gxBuf(gl, M.col)};
    }
    const p = gx.mwp;
    gl.useProgram(p.p); gl.uniformMatrix4fv(p.u.u_mvp, false, gx.mvp);
    gl.uniform3fv(p.u.u_gc, [gx.G.sun_to_gc_ly, 0, 0]); gl.uniform1f(p.u.u_R, 56000); gl.uniform1f(p.u.u_alpha, gx.mw * 0.9);
    gl.bindBuffer(gl.ARRAY_BUFFER, gx.bQuad); gl.enableVertexAttribArray(p.a.a_q); gl.vertexAttribPointer(p.a.a_q, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gxPoints(gx.pt, gx.mwData.pos, gx.mwData.size, gx.mwData.col, gx.mwData.n, gx.mw);
  }
  // Grid levels of 10, 100, 1,000 and 10,000 ly, each shown while its spacing suits the zoom.
  for (const s of [10, 100, 1000, 10000]){
    const r = d / s, a = gxSmooth(2.2, 6, r) * (1 - gxSmooth(30, 110, r));
    if (a > 0.01) gxLine('grid', s, [0, 0, 0], [1, 1, 1, 0.075 * a], 10);
  }
  const sa = 1 - gxSmooth(18000, 70000, d), R = d * 0.62;
  if (sa > 0.01){
    gxLine('sphere', R, [0, 0, 0], [1, 1, 1, 0.055 * sa]);
    gxLine('equator', R, [0, 0, 0], [1, 1, 1, 0.16 * sa]);
    gxLine('ring', R, [0, 0, 0], [0.39, 0.82, 1, 0.42 * sa]);
  }
  gxLine('axes', Math.min(27000, d * 2.6), [0, 0, 0], [0.39, 0.82, 1, 0.55]);
  gxPoints(gx.pt, gx.bHostPos, gx.bHostSize, gx.bHostCol, gx.G.hosts.n.length, 1 - 0.55 * gx.mw);
  gxPoints(gx.pt, gx.bSun[0], gx.bSun[1], gx.bSun[2], 1, 1);
}

// ---------- filters ----------
function gxRefilter(){
  const G = gx.G, v = gx.view, r = gxFilterCount(G, v), H = G.hosts, n = H.n.length, P = G.planets;
  gx.per = r.per; gx.shown = r;
  const size = new Float32Array(n), col = new Float32Array(n * 3), first = new Int32Array(n).fill(-1), on = new Set(v.methods.map(m => G.methods.indexOf(m)));
  const lim = v.dist ? v.dist / G.ly_per_pc : Infinity;
  for (let i = 0; i < P.n.length; i++){
    const h = P.h[i];
    if (!r.per[h] || (P.y[i] || 0) > v.year || !on.has(P.m[i]) || H.d[h] > lim) continue;
    if (first[h] < 0 || (P.y[i] || 0) < (P.y[first[h]] || 0)) first[h] = i;
  }
  const cols = G.methods.map(m => gxHex(G.method_colour[m]));
  for (let h = 0; h < n; h++){
    if (!r.per[h]) continue;
    size[h] = 2.6 + 1.5 * Math.sqrt(r.per[h] - 1);
    const c = cols[P.m[first[h]]];
    col[h * 3] = c[0]; col[h * 3 + 1] = c[1]; col[h * 3 + 2] = c[2];
  }
  gx.first = first;
  if (gx.gl){
    const gl = gx.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, gx.bHostSize); gl.bufferSubData(gl.ARRAY_BUFFER, 0, size);
    gl.bindBuffer(gl.ARRAY_BUFFER, gx.bHostCol); gl.bufferSubData(gl.ARRAY_BUFFER, 0, col);
  }
  $('#gxcyear').textContent = v.year;
  $('#gxccount').textContent = r.planets.toLocaleString('en-GB');
  $('#gxyearout').textContent = `${v.year} // ${r.planets.toLocaleString('en-GB')} planets`;
  $('#gxsum').textContent = `${v.year} // ${r.planets.toLocaleString('en-GB')}`;
  if (gx.sel >= 0 && !r.per[gx.sel]) gxSelect(-1);
  gx.cards = null;
  gxKick();
}
function gxControls(){
  const v = gx.view;
  $('#gxyear').value = v.year;
  $$('#gxmethods [data-gxm]').forEach(b => b.setAttribute('aria-pressed', String(v.methods.includes(b.dataset.gxm))));
  $('#gxdist').value = String(v.dist);
  $('#gxmulti').setAttribute('aria-pressed', String(v.multi));
  $('#gxshowcase').setAttribute('aria-pressed', String(!!v.showcase));
  $$('#gxcov [data-cov]').forEach(b => b.setAttribute('aria-pressed', String(v.layers.includes(b.dataset.cov))));
  $$('#gxpresets [data-gxview]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.gxview === v.view)));
}

// ---------- camera ----------
function gxPresetCam(id){
  const G = gx.G, H = G.hosts, K = G.kepler;
  if (id === 'kepler') return {tx: K.x * .55, ty: K.y * .55, tz: K.z * .55, yaw: Math.atan2(-K.y, -K.x) + 0.5, pitch: 0.32, dist: K.median_ly * 2.1};
  if (id === 'galaxy') return {tx: G.sun_to_gc_ly * 0.5, ty: 0, tz: 0, yaw: -2.5, pitch: 0.95, dist: 125000};
  if (id === 'pimen' && G.star.host != null){ const h = G.star.host; return {tx: H.x[h], ty: H.y[h], tz: H.z[h], yaw: Math.atan2(H.y[h], H.x[h]) + 0.4, pitch: 0.28, dist: 140}; }
  return {tx: 0, ty: 0, tz: 0, yaw: -2.2, pitch: 0.42, dist: 820};
}
function gxFly(to, ms){
  if (gxRM.matches || !ms || !gx.cam){ gx.cam = Object.assign({}, to); gx.flight = null; gx.cards = null; gxKick(); return; }
  const from = Object.assign({}, gx.cam);
  let dy = to.yaw - from.yaw; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
  gx.flight = {from, to: Object.assign({}, to, {yaw: from.yaw + dy}), t0: performance.now(), ms};
  gxKick();
}
function gxFlightStep(t){
  const f = gx.flight, k = Math.min(1, (t - f.t0) / f.ms), e = gxEase(k), a = f.from, b = f.to;
  // Distance moves on a log scale, so the flight passes through every zoom level smoothly; it lifts out mid-way.
  const lift = Math.sin(Math.PI * e) * Math.log(Math.max(1, Math.hypot(b.tx - a.tx, b.ty - a.ty, b.tz - a.tz) / Math.max(a.dist, b.dist))) * 0.5;
  gx.cam = {tx: a.tx + (b.tx - a.tx) * e, ty: a.ty + (b.ty - a.ty) * e, tz: a.tz + (b.tz - a.tz) * e, yaw: a.yaw + (b.yaw - a.yaw) * e,
    pitch: a.pitch + (b.pitch - a.pitch) * e, dist: Math.exp(Math.log(a.dist) + (Math.log(b.dist) - Math.log(a.dist)) * e + lift)};
  gx.dirty = true;
  if (k >= 1){ gx.flight = null; return false; }
  return true;
}
function gxZoom(f){ gx.cam.dist = Math.max(15, Math.min(260000, gx.cam.dist * f)); gx.flight = null; gxTouch(); }
function gxOrbit(dx, dy){ gx.cam.yaw -= dx; gx.cam.pitch = Math.max(-1.5, Math.min(1.5, gx.cam.pitch + dy)); gx.flight = null; gxTouch(); }
function gxTouch(){ gx.interacted = performance.now(); gx.driftAcc = 0; gx.cards = null; gxKick(); }

// ---------- picking ----------
function gxPick(px, py, maxPx){
  const H = gx.G.hosts, per = gx.per; let best = -1, bd = maxPx * maxPx, bz = Infinity;
  for (let h = 0; h < H.n.length; h++){
    if (!per[h]) continue;
    const p = gxProject(H.x[h], H.y[h], H.z[h]); if (!p) continue;
    const dd = (p[0] - px) ** 2 + (p[1] - py) ** 2;
    if (dd < bd - 1 || (Math.abs(dd - bd) <= 1 && p[2] < bz)){ bd = dd; best = h; bz = p[2]; }
  }
  return best;
}
function gxNearAim(k){
  const H = gx.G.hosts, per = gx.per, cx = gx.cssW / 2, cy = gx.cssH / 2, list = [];
  for (let h = 0; h < H.n.length; h++){
    if (!per[h]) continue;
    const p = gxProject(H.x[h], H.y[h], H.z[h]); if (!p) continue;
    list.push([(p[0] - cx) ** 2 + (p[1] - cy) ** 2, h]);
  }
  list.sort((a, b) => a[0] - b[0]);
  return list.slice(0, k).map(x => x[1]);
}
function gxHostPlanets(h){
  if (!gx.byHost){ gx.byHost = new Map(); const P = gx.G.planets; for (let i = 0; i < P.n.length; i++){ if (!gx.byHost.has(P.h[i])) gx.byHost.set(P.h[i], []); gx.byHost.get(P.h[i]).push(i); } }
  const P = gx.G.planets;
  return gx.byHost.get(h).slice().sort((a, b) => (P.y[a] || 0) - (P.y[b] || 0) || P.n[a].localeCompare(P.n[b]));
}
const gxMethod = i => gx.G.method_label[gx.G.methods[gx.G.planets.m[i]]];
const gxClass = i => { const P = gx.G.planets; if (P.c[i] == null) return '—'; return gx.G.classes[P.c[i]] + (P.r[i] == null ? (P.mk[i] === 1 ? ' (by m sin i; no radius stored)' : ' (by mass; no radius stored)') : ''); };

// ---------- overlay: labels, ticks, callouts, reticle, telemetry ----------
function gxEl(cls, html){ const e = document.createElement('div'); e.className = cls; if (html != null) e.innerHTML = html; $('#gxlayer').appendChild(e); return e; }
function gxBuildLabels(){
  const G = gx.G, L = {ticks: [], axes: [], fixed: []};
  for (const [ax, name] of [[0, 'x'], [1, 'y'], [2, 'z']]) for (const t of [250, 500, 1000, 2500, 10000, 25000]){
    const p = [0, 0, 0]; p[ax] = t;
    L.ticks.push({p, t, el: gxEl('gxlbl tick', `<span>${t.toLocaleString('en-GB')} ly</span>`)});
  }
  for (const [p, text] of [[[1, 0, 0], '→ Galactic centre'], [[0, 1, 0], 'l = 90°'], [[0, 0, 1], 'North Galactic pole']])
    L.axes.push({p, el: gxEl('gxlbl axis', text)});
  L.sun = gxEl('gxlbl sun', 'Sun');
  L.gc = gxEl('gxlbl axis', 'Galactic centre (approximate)');
  const K = G.kepler;
  L.kepler = gxEl('gxlbl region', `Kepler field · Cygnus–Lyra<small>${K.hosts.toLocaleString('en-GB')} stars · ${K.planets.toLocaleString('en-GB')} planets (${K.radius_deg}° disc)</small><small>Kepler's single deep field, not a real structure.</small>`);
  const ML = G.lensing;
  if (ML) L.lensing = gxEl('gxlbl region', `Microlensing planets<small>${ML.planets.toLocaleString('en-GB')} planets · found toward the Galactic bulge,</small><small>where the most background stars are. Distances model-dependent.</small>`);
  gx.labels = L;
  // Callout cards for the notable planets.
  gx.calls = G.notable.map((nt, k) => {
    const i = nt.planet, h = nt.host, P = G.planets, H = G.hosts;
    const el = gxEl('gxcall' + (nt.setuhq ? ' ex' : ''), `<b><i style="background:${G.method_colour[nt.method]}"></i>${esc(nt.name)}</b><p>${esc(nt.tagline)}</p><dl><dt>CLASS</dt><dd>${esc(gxClass(i))}</dd><dt>DISTANCE</dt><dd title="${gxFmt(H.d[h], 3)} pc, as listed in ${esc(G.source_short)}">${gxLy(H.d[h])} ly</dd><dt>DISCOVERED</dt><dd>${P.y[i] || '—'}</dd><dt>METHOD</dt><dd>${esc(gxMethod(i))}</dd></dl>`);
    el.dataset.stop = k + 1;
    el.style.borderLeft = `3px solid ${G.method_colour[nt.method]}`;
    el.addEventListener('click', () => { gxSelect(h, i); gxFly(gxHostCam(h), 1800); });
    el.title = 'Select; the host card opens its system view';
    const ring = gxEl('gxring' + (nt.setuhq ? ' ex' : ''));
    ring.dataset.stop = k + 1;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); $('#gxleaders').appendChild(line);
    return {nt, k, el, ring, line, w: 0, h: 0};
  });
}
function gxPlace(el, x, y, show, alpha){
  if (!show){ if (el.style.display !== 'none') el.style.display = 'none'; return; }
  if (el.style.display === 'none') el.style.display = '';
  el.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
  if (alpha != null) el.style.opacity = alpha.toFixed(2);
}
function gxOverlay(){
  if (!gx.labels) gxBuildLabels();
  const L = gx.labels, d = gx.cam.dist, W = gx.cssW, Hh = gx.cssH, on = (p) => p && p[0] > -40 && p[0] < W + 40 && p[1] > -20 && p[1] < Hh + 20;
  // Labels are placed in priority order (centre, Sun, survey regions, axis names, then ticks). Each must
  // sit wholly inside the stage and clear of the HUD panels, the selected-system card, the tour bar and
  // every label placed before it: it tries the four sides of its anchor and is hidden if none is free.
  $('#gxmw').hidden = gx.mw < 0.25;
  gxRadar();
  const now = performance.now();
  if (now - gx.telAt > 150){ gx.telAt = now; gxTelemetry(); }
  // Notable cards come first (they carry the most); labels then avoid them as well as the HUD.
  gxCallouts();
  const placed = gxHudRects().concat((gx.cardRects || []).map(r => r.slice())), mwEl = $('#gxmw');
  if (!mwEl.hidden){ const st = $('#gxstage').getBoundingClientRect(), b = mwEl.getBoundingClientRect(); if (b.width) placed.push([b.left - st.left, b.top - st.top, b.right - st.left, b.bottom - st.top]); }
  const size = el => { if (!el._w){ const disp = el.style.display; el.style.display = ''; const sp = el.querySelector('span'); el._w = Math.max(el.offsetWidth, sp ? sp.offsetWidth + 8 : 0) || 80; el._h = Math.max(el.offsetHeight, sp ? sp.offsetHeight + 4 : 0) || 14; el.style.display = disp; } return [el._w, el._h]; };
  const free = r => { if (r[0] < 2 || r[1] < 2 || r[2] > W - 2 || r[3] > Hh - 2) return false; for (const q of placed) if (r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]) return false; return true; };
  const SIDES = [[8, 6], [8, -6], [-8, 6], [-8, -6]];
  const put = (el, p, show, alpha, offs) => {
    if (!p || !show){ gxPlace(el, 0, 0, false); return false; }
    const [w, h] = size(el);
    for (const [dx, dy] of offs || SIDES){
      const x = p[0] + (dx < 0 ? dx - w : dx), y = p[1] + (dy < 0 ? dy - h : dy), r = [x - 3, y - 3, x + w + 3, y + h + 3];
      if (free(r)){ placed.push(r); gxPlace(el, x, y, true, alpha); return true; }
    }
    gxPlace(el, 0, 0, false); return false;
  };
  const len = Math.min(27000, d * 2.6);
  const gp = gxProject(gx.G.sun_to_gc_ly, 0, 0), gcOn = put(L.gc, gp, gx.mw > 0.3, gx.mw);
  put(L.sun, gxProject(0, 0, 0), true);
  const K = gx.G.kepler, ka = gxSmooth(500, 1400, d) * (1 - gxSmooth(30000, 60000, d));
  put(L.kepler, gxProject(K.x, K.y, K.z), ka > 0.05, ka, [[14, -30], [14, 10], [-14, -30], [-14, 10]]);
  if (L.lensing){
    const M = gx.G.lensing, ma = gxSmooth(4000, 12000, d) * (1 - gxSmooth(160000, 250000, d));
    put(L.lensing, gxProject(M.x, M.y, M.z), ma > 0.05 && gx.view.methods.includes('microlensing'), ma, [[14, 10], [14, -10], [-14, 10], [-14, -10]]);
  }
  // With the Milky Way drawn, its centre is labelled at the bulge; the axis arrow label would repeat it.
  for (const a of L.axes) put(a.el, gxProject(a.p[0] * len * .97, a.p[1] * len * .97, a.p[2] * len * .97), !(gcOn && a.p[0]), null, [[6, -6], [6, 6], [-6, -6], [-6, 6]]);
  for (const t of L.ticks){
    const p = gxProject(t.p[0], t.p[1], t.p[2]);
    // A tick label stays on its tick (the dot marks the distance), so it is shown there or not at all.
    put(t.el, p, t.t >= d * 0.05 && t.t <= len, null, [[0, 0]]);
  }
  // The reticle's target: the shown star nearest the centre of the view, within 44 px.
  const aim = gxPick(W / 2, Hh / 2, 44);
  gx.aim = aim;
  const box = $('#gxaim');
  if (aim >= 0){ const H = gx.G.hosts, p = gxProject(H.x[aim], H.y[aim], H.z[aim]); box.hidden = false; box.style.transform = `translate(${p[0]}px,${p[1]}px)`; }
  else box.hidden = true;
}
function gxCallouts(){
  const G = gx.G, H = G.hosts, d = gx.cam.dist, eye = gxEye(), W = gx.cssW, Hh = gx.cssH, zoomA = 1 - gxSmooth(2500, 6000, d);
  const svg = $('#gxleaders'), hudR = gxHudRects();
  svg.setAttribute('viewBox', `0 0 ${W} ${Hh}`);
  const items = [];
  for (const c of gx.calls){
    const h = c.nt.host, shown = gx.per[h] > 0 && G.planets.y[c.nt.planet] <= gx.view.year && (!gx.view.showcase || c.nt.showcase || gx.selPlanet === c.nt.planet);
    const p = shown ? gxProject(H.x[h], H.y[h], H.z[h]) : null;
    const dist = Math.hypot(H.x[h] - eye[0], H.y[h] - eye[1], H.z[h] - eye[2]);
    // Cards fade with their distance from the camera, and as the camera pulls out past a few thousand ly.
    const alpha = zoomA * Math.max(0, Math.min(1, 1.6 - dist / (2.2 * d)));
    const pri = (gx.selPlanet === c.nt.planet ? 0 : gx.tour && gx.tour.k === c.k ? 1 : c.nt.setuhq ? 2 : 3) * 1e9 + dist;
    items.push({c, p, alpha, pri});
  }
  items.sort((a, b) => a.pri - b.pri);
  // Every candidate's ring is an obstacle for the other cards, and a ring must sit wholly inside the stage.
  const rings = items.filter(it => it.p && it.alpha > 0.34).map(it => [it.p[0] - 14, it.p[1] - 14, it.p[0] + 14, it.p[1] + 14, it]);
  const taken = [];
  for (const it of items){
    const c = it.c;
    // No ghosts: a card fainter than a third is hidden outright, and cards rest while the camera flies.
    let ok = it.p && it.alpha > 0.34 && !gx.flight && it.p[0] > 14 && it.p[0] < W - 14 && it.p[1] > 14 && it.p[1] < Hh - 14;
    let x = 0, y = 0;
    if (ok){
      if (!c.w){ c.el.style.display = ''; c.w = c.el.offsetWidth; c.h = c.el.offsetHeight; }
      x = it.p[0] + 26; y = it.p[1] - 26 - c.h;
      if (x + c.w > W - 8) x = it.p[0] - 26 - c.w;
      if (y < 8) y = it.p[1] + 26;
      const r = [x - 4, y - 4, x + c.w + 4, y + c.h + 4];
      if (x < 4 || y < 4 || x + c.w > W - 4 || y + c.h > Hh - 4) ok = false;
      // Never overlap: a card that would cover a higher-priority card (or the HUD) is hidden.
      for (const q of taken) if (r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]){ ok = false; break; }
      if (ok) for (const q of rings) if (q[4] !== it && r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]){ ok = false; break; }
      if (ok) for (const q of hudR) if (r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]){ ok = false; break; }
      if (ok) taken.push(r);
    }
    c.el.classList.toggle('sel', gx.selPlanet === c.nt.planet);
    gxPlace(c.el, x, y, ok, it.alpha);
    gxPlace(c.ring, it.p ? it.p[0] : 0, it.p ? it.p[1] : 0, ok, it.alpha);
    if (ok){
      const ax = x > it.p[0] ? x : x + c.w, ay = y > it.p[1] ? y : y + c.h;
      c.line.setAttribute('x1', it.p[0] + (ax > it.p[0] ? 9 : -9)); c.line.setAttribute('y1', it.p[1] + (ay > it.p[1] ? 9 : -9));
      c.line.setAttribute('x2', ax); c.line.setAttribute('y2', ay); c.line.style.opacity = it.alpha; c.line.style.display = '';
    } else c.line.style.display = 'none';
  }
  gx.cardRects = taken;
}
function gxHudRects(){
  // Measured every frame: the telemetry panel grows and shrinks with its text.
  const st = $('#gxstage').getBoundingClientRect(), r = [];
  for (const sel of ['.gxtr', '.gxbl', '#gxtourbar', '#gxcard']){
    const el = $(sel); if (!el || el.hidden) continue;
    const b = el.getBoundingClientRect(); if (!b.width) continue;
    r.push([b.left - st.left - 2, b.top - st.top - 2, b.right - st.left + 2, b.bottom - st.top + 2]);
  }
  return r;
}
function gxRadar(){
  // The camera looks along -(cos yaw, sin yaw): its heading in galactic longitude, shown on the radar.
  const c = gx.cam, l = (Math.atan2(-Math.sin(c.yaw), -Math.cos(c.yaw)) * 180 / Math.PI + 360) % 360;
  // Radar is drawn heading-up: the Galactic centre (l = 0) sits at -l from the top.
  $('#gxgc').setAttribute('transform', `rotate(${(-l).toFixed(1)})`);
  gx.heading = l;
}
function gxTelemetry(){
  const G = gx.G, H = G.hosts, P = G.planets, pad = (k, v) => k.padEnd(8) + v;
  const c = gx.cam, lines = [`<b>HDG</b> l ${gx.heading.toFixed(0).padStart(3, '0')}°  <b>ELV</b> ${(c.pitch * 180 / Math.PI).toFixed(0)}°`,
    `<b>FIELD</b> ${gxFmt(Math.round(2 * c.dist * Math.tan(GX_FOV / 2)), 0)} ly across`];
  if (gx.selPlanet >= 0){
    const i = gx.selPlanet, h = P.h[i], r = P.r[i], m = P.ms[i];
    lines.push('', `<b>${esc(P.n[i])}</b>`,
      pad('PERIOD', P.p[i] == null ? '—' : gxSig(P.p[i]) + ' d'),
      pad('RADIUS', r == null ? '—' : `${gxSig(r * G.rj_in_re)} R⊕ · ${gxSig(r)} RJ`),
      pad(P.mk[i] === 1 ? 'M SIN I' : 'MASS', m == null ? '—' : `${gxSig(m * G.mj_in_me)} M⊕ · ${gxSig(m)} MJ`),
      pad('CLASS', gxClass(i)), pad('HOST', esc(H.n[h])), pad('HOST V', H.v[h] == null ? '—' : gxSig(H.v[h]) + ' mag'),
      pad('DIST', `${gxLy(H.d[h])} ly · ${gxFmt(H.d[h], 3)} pc`));
  } else {
    if (gx.aim >= 0){
      const h = gx.aim;
      lines.push('', '<b>AIM</b>', pad('RA', gxFmt(H.ra[h], 3) + '°') + '  ' + 'DEC ' + gxFmt(H.dec[h], 3) + '°', pad('DIST', `${gxLy(H.d[h])} ly · ${gxFmt(H.d[h], 3)} pc`));
    }
    lines.push('', '<b>NEAR AIM</b>');
    for (const h of gxNearAim(4)) lines.push(`SYS ${esc(H.n[h].slice(0, 16))} // ${String(G.host_n[h]).padStart(2, '0')} PLANET${G.host_n[h] === 1 ? '' : 'S'}`);
  }
  $('#gxtel').innerHTML = lines.join('\n');
}

// ---------- selection: the host card and the tooltip ----------
function gxHostCam(h){ const H = gx.G.hosts; return {tx: H.x[h], ty: H.y[h], tz: H.z[h], yaw: gx.cam.yaw, pitch: gx.cam.pitch, dist: Math.max(60, Math.min(gx.cam.dist, 400))}; }
function gxSelect(h, planet){
  const card = $('#gxcard'), G = gx.G, H = G.hosts, P = G.planets;
  if (gx.view && gx.view.focus && (h < 0 || H.n[h] !== gx.view.focus)){ gx.view.focus = ''; syncGalaxyURL(false); $('#gxfocusnote').hidden = true; }
  gx.sel = h; gx.selPlanet = h >= 0 ? (planet != null ? planet : gxHostPlanets(h)[0]) : -1;
  $('#gxstage').classList.toggle('sel', h >= 0);
  gx.hud = null; gx.cards = null;
  if (h < 0){ card.hidden = true; gxKick(); return; }
  const ps = gxHostPlanets(h), star = G.star;
  const lensNote = ps.some(i => G.methods[P.m[i]] === 'microlensing') ? '<p>Found by microlensing; the distance comes from a model of the event. <a href="' + R('#/methods?ch=microlensing') + '">How microlensing works ›</a></p>' : '';
  const exo = star.host === h ? `<p>SetuHQ's run reviewed this star's TESS light curve: ${esc(star.planet || '')} is the planet it recovered. <a href="${R(`#/transit${star.lead_dip ? '?dip=' + encodeURIComponent(star.lead_dip) : ''}`)}">Open the Transit case ›</a></p>` : '';
  card.innerHTML = `<button class="btn x" type="button" aria-label="Close">×</button><h3>${esc(H.n[h])}</h3>
    <p class="mono">${gxLy(H.d[h])} ly · ${gxFmt(H.d[h], 3)} pc · RA ${gxFmt(H.ra[h], 3)}° Dec ${gxFmt(H.dec[h], 3)}° · V ${H.v[h] == null ? '—' : gxSig(H.v[h])}</p>
    <p>${G.host_n[h]} planet${G.host_n[h] === 1 ? '' : 's'} in ${esc(G.source_short)}${G.host_n[h] > gx.per[h] ? `, ${gx.per[h]} shown by the filters` : ''}.</p>
    ${gxLinks(h)}<ul>${ps.map(i => `<li><button type="button" data-gxp="${i}" aria-pressed="${i === gx.selPlanet}">${esc(P.n[i])}<span>${P.y[i] || '—'} · ${esc(gxMethod(i))} · ${esc(gxClass(i))}</span></button>${typeof MX !== 'undefined' && MX && MX.examples[P.n[i]] ? `<button class="btn gxsys" type="button" data-gxsys="${esc(P.n[i])}">Open the system view ›</button>` : ''}</li>`).join('')}</ul>${exo}${lensNote}`;
  card.hidden = false;
  gxPic(card);
  gxKick();
  // Mission Control's linked selection: the star picked here is selected in every pane and window.
  if (typeof mcBrush === 'function') mcBrush(H.n[h], 'galaxy');
}
// The selected system's sheet: the star in its blackbody colour and the selected planet as its look (SetuRender),
// from the catalogue's row; the planet is an artist's impression, and the two are not to scale.
function gxPic(card){
  const P0 = gx.G.planets, name = gx.selPlanet >= 0 ? P0.n[gx.selPlanet] : null;
  if (!name || !window.SetuRender || typeof ctLoad !== 'function' || !CTM) return;
  ctLoad().then(() => {
    const P = ct.P, i = P.name.indexOf(name); if (i < 0 || card.hidden || P0.n[gx.selPlanet] !== name) return;
    const lk = SetuRender.look(ctRow(i)), teff = P.steff[i]; if (!teff && !lk.name) return;
    let box = card.querySelector('.gxpic'); if (!box){ box = document.createElement('div'); box.className = 'gxpic'; card.querySelector('h3').after(box); }
    const alt = `${teff ? `The star in its blackbody colour, ${Math.round(teff).toLocaleString('en-US')} K` : 'Star temperature not stored'}; ${name}: ${lk.name ? `an artist's impression, ${lk.composition}, ${lk.band || 'irradiation not computable'}` : 'no radius or mass stored, so no planet is drawn'}. Not to scale.`;
    box.innerHTML = `<canvas role="img" aria-label="${esc(alt)}"></canvas><a class="gxpictag" href="/docs/pictures/">${lk.name ? "Artist's impression" : 'Model from stored values'}</a>`;
    const cv = box.querySelector('canvas'), d = Math.min(2, devicePixelRatio || 1), w = cv.clientWidth || 288, h = 88;
    cv.width = w * d; cv.height = h * d; const c = cv.getContext('2d'); c.scale(d, d); c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
    if (teff) SetuRender.drawStar2D(c, 52, h / 2, 30, teff, 0, {flat: true, glow: 1.6});
    if (lk.name) SetuRender.drawPlanet2D(c, w - 64, h / 2, 26, lk.name, true, {seed: SetuRender.fnv(P.slug[i]), neutral: lk.neutral, sync: true});
  }).catch(() => {});
}
// Where a host is on screen (for the zoom lens into its system view), or null when it is behind the camera.
function gxScreenPoint(h){
  if (h < 0 || !gx.mvp) return null;
  const H = gx.G.hosts, p = gxProject(H.x[h], H.y[h], H.z[h]), r = $('#gxcanvas').getBoundingClientRect();
  return p ? {x: r.left + p[0], y: r.top + p[1], kind: 'galaxy'} : null;
}
const gxElPoint = el => { const r = el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, kind: 'galaxy'}; };
// The canonical pages for the selected star and planet (a free-floating planet is its own host: no star page).
function gxLinks(h){
  const G = gx.G, H = G.hosts, P = G.planets, ps = gxHostPlanets(h), starless = ps.length === 1 && P.n[ps[0]] === H.n[h];
  return `<div class="pllinks gxlinks">${starless ? '' : objLink('star', H.n[h], 'Star page ›')}${gx.selPlanet >= 0 ? objLink('planet', P.n[gx.selPlanet], P.n[gx.selPlanet] + ' ›') : ''}</div>`;
}
function gxTip(h, x, y){
  const tip = $('#gxtip');
  if (h < 0){ tip.hidden = true; return; }
  const G = gx.G, H = G.hosts, P = G.planets, ps = gxHostPlanets(h);
  const lens = ps.some(i => G.methods[P.m[i]] === 'microlensing') ? '<br><span class="mono">distance model-dependent (microlensing)</span>' : '';
  tip.innerHTML = `<b>${esc(H.n[h])}</b> · ${G.host_n[h]} planet${G.host_n[h] === 1 ? '' : 's'}<br><span class="mono">${gxLy(H.d[h])} ly (${gxFmt(H.d[h], 3)} pc)</span>${lens}<br>` +
    ps.slice(0, 4).map(i => `${esc(P.n[i])} <span class="mono">· ${P.y[i] || '—'} · ${esc(gxMethod(i))}</span>`).join('<br>') + (ps.length > 4 ? `<br><span class="mono">and ${ps.length - 4} more</span>` : '');
  tip.hidden = false;
  const w = tip.offsetWidth, hh = tip.offsetHeight;
  tip.style.transform = `translate(${Math.min(x + 14, gx.cssW - w - 8)}px,${Math.max(8, Math.min(y + 14, gx.cssH - hh - 8))}px)`;
}

// ---------- timeline and tour ----------
function gxPlay(){
  if (gx.play){ gx.play = null; $('#gxplay').textContent = `Play ${GXM.years[0]}–${GXM.years[1]}`; syncGalaxyURL(false); return; }
  gx.view.year = GXM.years[0]; gxRefilter(); gxControls();
  gx.play = {t0: performance.now(), per: gxRM.matches ? 650 : 380};
  $('#gxplay').textContent = 'Pause';
  gxKick();
}
function gxPlayStep(t){
  const p = gx.play, y = Math.min(GXM.years[1], GXM.years[0] + Math.floor((t - p.t0) / p.per));
  if (y !== gx.view.year){ gx.view.year = y; gxRefilter(); $('#gxyear').value = y; }
  if (y >= GXM.years[1]){ gx.play = null; $('#gxplay').textContent = `Play ${GXM.years[0]}–${GXM.years[1]}`; syncGalaxyURL(false); say(`${y}: ${gx.shown.planets.toLocaleString('en-GB')} planets.`); return false; }
  return true;
}
function gxTourGo(k, push){
  const G = gx.G, n = G.notable.length; if (!n) return;
  k = ((k % n) + n) % n;
  const nt = G.notable[k];
  if (!gx.tour) gx.tour = {k, paused: false, t0: 0};
  gx.tour.k = k; gx.tour.t0 = performance.now();
  $('#gxtourbar').hidden = false; gx.hud = null;
  $('#gxtlabel').textContent = `${k + 1} of ${n} · ${nt.name}`;
  $('#gxtpause').textContent = gx.tour.paused ? 'Resume' : 'Pause';
  // A stop must be visible: the tour shows every year, method and distance.
  if (gx.view.year !== GXM.years[1] || gx.view.methods.length !== GXM.methods.length || gx.view.dist || gx.view.multi){
    Object.assign(gx.view, {year: GXM.years[1], methods: GXM.methods.slice(), dist: 0, multi: false}); gxRefilter(); gxControls();
  }
  gx.view.tour = k + 1;
  gxSelect(nt.host, nt.planet);
  const H = G.hosts, h = nt.host;
  gxFly({tx: H.x[h], ty: H.y[h], tz: H.z[h], yaw: Math.atan2(H.y[h], H.x[h]) + 0.5 + k * 0.3, pitch: 0.3, dist: 120}, 2200);
  syncGalaxyURL(!!push);
}
function gxTourStep(t){ if (t - gx.tour.t0 > 6000){ gxTourGo(gx.tour.k + 1, false); } return true; }
function gxTourEnd(){ gx.tour = null; $('#gxtourbar').hidden = true; gx.hud = null; gx.view.tour = 0; syncGalaxyURL(true); gxKick(); }

// ---------- the loop: runs only while the section is on screen and the tab is visible ----------
function gxLive(){ const st = $('#gxstage'); return gx.on && gx.visible && !document.hidden && !!st && st.getClientRects().length > 0; }
function gxKick(){ gx.dirty = true; if (gxLive() && !gx.raf) gx.raf = requestAnimationFrame(gxFrame); }
function gxFrame(t){
  gx.raf = 0;
  if (!gxLive()){ gx.last = 0; return; }
  const dt = gx.last ? Math.min(100, t - gx.last) : 16; gx.last = t;
  let anim = false;
  if (gx.flight) anim = gxFlightStep(t) || anim;
  // A slow drift when nobody is steering (never under reduced motion, never during the tour).
  // The drift rests after one full turn, or 30 s after the last touch, whichever comes first.
  const idle = t - gx.interacted, drift = !gxRM.matches && gx.auto && !gx.tour && !gx.drag && (gx.driftAcc || 0) < 2 * Math.PI && idle < 36000;
  if (drift){ anim = true; if (!gx.flight && idle > 6000){ const dy = dt * 0.00005; gx.cam.yaw += dy; gx.driftAcc = (gx.driftAcc || 0) + dy; gx.dirty = true; } }
  if (gx.play) anim = gxPlayStep(t) || anim;
  if (gx.tour && !gx.tour.paused) anim = gxTourStep(t) || anim;
  if (gx.dirty){ gx.dirty = false; gxDraw(); gxOverlay(); gx.frames++; }
  if (anim || gx.dirty) gx.raf = requestAnimationFrame(gxFrame);
  else gx.last = 0;
}
// The map runs on its own page, and in Mission Control while its pane is shown (in this window, or as this
// popped-out window); anywhere else it sleeps.
function gxWanted(){
  if (current === 'galaxy') return true;
  if (current !== 'mission' || typeof mc === 'undefined' || !mc.layout || mc.layout.hidden.includes('galaxy')) return false;
  return mc.pop ? mc.pop === 'galaxy' : !mc.popped.has('galaxy');
}
function gxShown(on){
  gx.on = on;
  if (on && gx.ready){ gxResize(); gxKick(); }
  if (!on && gx.play) gxPlay();
}

function applyGalaxy(v){
  const prev = gx.view; gx.view = v;
  if (!gx.ready) return;
  gxRefilter(); gxControls();
  if (v.tour){ if (!prev || prev.tour !== v.tour) gxTourGo(v.tour - 1, false); }
  else if (gx.tour) { gx.tour = null; $('#gxtourbar').hidden = true; }
  if (!v.tour && (!prev || prev.view !== v.view)) gxFly(gxPresetCam(v.view), 2400);
  if (v.focus && (!prev || prev.focus !== v.focus)) gxFocus(v.focus);
  if (!v.focus) $('#gxfocusnote').hidden = true;
}
// A deep link from a planet or star page (#/galaxy?focus=<host name>): select that star and fly to it.
function gxFocus(name){
  const h = gx.G.hosts.n.indexOf(name), note = $('#gxfocusnote');
  note.hidden = h >= 0;
  if (h < 0){ note.innerHTML = `No star “${esc(name)}” on the map (no stored distance or not in the catalogue). <a href="${R(`#/catalogue?q=${encodeURIComponent(name)}`)}">Search the Catalogue ›</a>`; return; }
  gxSelect(h); gxFly(Object.assign(gxHostCam(h), {dist: 140}), 2400);
}
function syncGalaxyURL(push){ if (current !== 'galaxy' || !gx.view) return; const q = encodeGalaxyView(gx.view); setHash('#/galaxy' + (q ? '?' + q : ''), !!push); }

function renderGalaxy(){
  if (!GXM) return;
  const note = $('#gxload'); note.hidden = false;
  gxLoad().then(() => { note.hidden = true; gxStart(); gxShown(gxWanted()); }).catch(() => {
    note.textContent = 'The map data could not be loaded here. The table below lists the nearest systems, and the CSV holds every plotted planet.';
  });
}
function gxStart(){
  const cv = $('#gxcanvas');
  let ok = false;
  try { ok = gxInitGL(); } catch (e) { ok = false; }
  if (!ok){ $('#gxnogl').hidden = false; cv.removeAttribute('tabindex'); return; }
  if (!gx.view) gx.view = decodeGalaxyView(new URLSearchParams());
  // First view: a short pull-in to the preset (a cut under reduced motion).
  const target = gxPresetCam(gx.view.view);
  gx.cam = gxRM.matches ? Object.assign({}, target) : Object.assign({}, target, {dist: target.dist * 4, yaw: target.yaw - 0.6});
  gx.ready = true;
  gxRefilter(); gxControls();
  if (gx.view.tour) gxTourGo(gx.view.tour - 1, false); else gxFly(target, 2600);
  if (gx.view.focus) gxFocus(gx.view.focus);
  if (gxPhone.matches) $('#gxsheet').open = false;
  // Pointer: drag to orbit, two fingers to pinch-zoom, click to select, double-click to centre.
  cv.addEventListener('pointerdown', e => {
    cv.setPointerCapture(e.pointerId);
    gx.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    gx.drag = {x: e.clientX, y: e.clientY, moved: 0, pinch: gx.pointers.size === 2 ? gxPinch() : 0};
    gxTip(-1); gxTouch();
  });
  cv.addEventListener('pointermove', e => {
    const r = cv.getBoundingClientRect();
    if (!gx.pointers.has(e.pointerId)){
      if (e.pointerType === 'mouse' && gx.mvp){ const h = gxPick(e.clientX - r.left, e.clientY - r.top, 12); gx.hover = h; gxTip(h, e.clientX - r.left, e.clientY - r.top); cv.style.cursor = h >= 0 ? 'pointer' : ''; }
      return;
    }
    const last = gx.pointers.get(e.pointerId); gx.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (gx.pointers.size === 2){ const p = gxPinch(); if (gx.drag.pinch) gxZoom(gx.drag.pinch / p); gx.drag.pinch = p; gx.drag.moved += 10; return; }
    const dx = e.clientX - last[0], dy = e.clientY - last[1];
    gx.drag.moved += Math.abs(dx) + Math.abs(dy);
    gxOrbit(dx * 0.006, dy * 0.006);
  });
  const up = e => {
    if (!gx.pointers.has(e.pointerId)) return;
    gx.pointers.delete(e.pointerId);
    if (gx.drag && gx.drag.moved < 6 && e.type === 'pointerup' && gx.mvp){
      const r = cv.getBoundingClientRect(), h = gxPick(e.clientX - r.left, e.clientY - r.top, e.pointerType === 'mouse' ? 12 : 22);
      if (h >= 0) gxSelect(h); else if (gx.sel >= 0) gxSelect(-1);
    }
    if (!gx.pointers.size) gx.drag = null; else if (gx.drag) gx.drag.pinch = gx.pointers.size === 2 ? gxPinch() : 0;
    gxTouch();
  };
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('pointerleave', () => { if (!gx.pointers.size) gxTip(-1); });
  cv.addEventListener('wheel', e => { e.preventDefault(); gxZoom(Math.exp(Math.max(-1, Math.min(1, e.deltaY * (e.deltaMode ? 0.05 : 0.0015))))); }, {passive: false});
  cv.addEventListener('dblclick', e => {
    const r = cv.getBoundingClientRect(), h = gxPick(e.clientX - r.left, e.clientY - r.top, 16);
    if (h >= 0){ gxSelect(h); gxFly(gxHostCam(h), 1600); } else gxFly(Object.assign({}, gx.cam, {tx: 0, ty: 0, tz: 0}), 1200);
    gxTouch();
  });
  cv.addEventListener('keydown', e => {
    const k = e.key, s = 0.08;
    if (k === 'ArrowLeft') gxOrbit(-s, 0); else if (k === 'ArrowRight') gxOrbit(s, 0);
    else if (k === 'ArrowUp') gxOrbit(0, s); else if (k === 'ArrowDown') gxOrbit(0, -s);
    else if (k === '+' || k === '=') gxZoom(0.8); else if (k === '-' || k === '_') gxZoom(1.25);
    else if (k === 'Enter'){ if (gx.aim >= 0){ gxSelect(gx.aim); say(`Selected ${gx.G.hosts.n[gx.aim]}.`); } }
    else if (k === 'Escape'){ if (gx.tour) gxTourEnd(); else gxSelect(-1); }
    else if (k === 'Home' || k === '0') gxFly(gxPresetCam(gx.view.view), 1400);
    else return;
    e.preventDefault();
  });
  $('#gxcard').addEventListener('click', e => {
    if (e.target.closest('.x')){ gxSelect(-1); cv.focus({preventScroll: true}); return; }
    const sys = e.target.closest('button[data-gxsys]'); if (sys){ mxOpenSystem(sys.dataset.gxsys, sys, gxScreenPoint(gx.sel) || gxElPoint(sys)); return; }
    const b = e.target.closest('button[data-gxp]'); if (!b) return;
    gxSelect(gx.sel, Number(b.dataset.gxp)); const nb = $(`#gxcard button[data-gxp="${b.dataset.gxp}"]`); if (nb) nb.focus();
  });
  $('#gxcam').addEventListener('click', e => { const b = e.target.closest('[data-gc]'), o = b && b.dataset.gc; if (!o) return; if (gx.tour) gxTourEnd();
    if (o === 'in' || o === 'out') gxZoom(o === 'in' ? .8 : 1.25); else if (o === 'star'){ if (gx.sel >= 0) gxFly(gxHostCam(gx.sel), 1400); else say('Select a star on the map first.'); }
    else gxFly(gxPresetCam(o === 'all' ? 'galaxy' : gx.view.view), 1400); });
  $('#gxpresets').addEventListener('click', e => {
    const b = e.target.closest('button[data-gxview]'); if (!b) return;
    if (gx.tour) gxTourEnd();
    gx.view.view = b.dataset.gxview; gxControls(); gxFly(gxPresetCam(gx.view.view), 2600); syncGalaxyURL(true);
    say(`View: ${GXM.preset_label[gx.view.view]}.`);
  });
  $('#gxyear').addEventListener('input', e => { if (gx.play) gxPlay(); gx.view.year = Number(e.target.value); gxRefilter(); });
  $('#gxyear').addEventListener('change', () => syncGalaxyURL(true));
  $('#gxplay').addEventListener('click', gxPlay);
  $('#gxmethods').addEventListener('click', e => {
    const b = e.target.closest('button[data-gxm]'); if (!b) return;
    const m = b.dataset.gxm, on = gx.view.methods.includes(m);
    gx.view.methods = on ? gx.view.methods.filter(x => x !== m) : GXM.methods.filter(x => x === m || gx.view.methods.includes(x));
    gxRefilter(); gxControls(); syncGalaxyURL(true);
  });
  $('#gxdist').addEventListener('change', e => { gx.view.dist = Number(e.target.value); gxRefilter(); syncGalaxyURL(true); });
  $('#gxmulti').addEventListener('click', () => { gx.view.multi = !gx.view.multi; gxRefilter(); gxControls(); syncGalaxyURL(true); });
  const cov = $('#gxcov');
  if (cov) cov.addEventListener('click', e => {
    const b = e.target.closest('button[data-cov]'); if (!b) return;
    const k = b.dataset.cov, on = gx.view.layers.includes(k);
    gx.view.layers = GXM.layers.filter(x => x === k ? !on : gx.view.layers.includes(x));
    gxControls(); gxKick(); syncGalaxyURL(true);
  });
  $('#gxshowcase').addEventListener('click', () => { gx.view.showcase = !gx.view.showcase; gxControls(); gx.cards = null; gxKick(); syncGalaxyURL(true); });
  $('#gxtour').addEventListener('click', () => { if (gx.tour) gx.tour.paused = false; gxTourGo(gx.tour ? gx.tour.k : 0, true); $('#gxtpause').focus(); });
  $('#gxtprev').addEventListener('click', () => gxTourGo(gx.tour.k - 1, true));
  $('#gxtnext').addEventListener('click', () => gxTourGo(gx.tour.k + 1, true));
  $('#gxtpause').addEventListener('click', () => { gx.tour.paused = !gx.tour.paused; gx.tour.t0 = performance.now(); $('#gxtpause').textContent = gx.tour.paused ? 'Resume' : 'Pause'; gxKick(); });
  $('#gxtexit').addEventListener('click', () => { gxTourEnd(); $('#gxtour').focus(); });
  $$('.gxnot').forEach(b => b.addEventListener('click', () => { if (gx.tour) gx.tour.paused = true; gxTourGo(Number(b.dataset.gxstop) - 1, true); if (gx.tour) $('#gxtpause').textContent = 'Resume'; $('#gxstage').scrollIntoView({block: 'nearest', behavior: gxRM.matches ? 'auto' : 'smooth'}); }));
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { gx.visible = es[0].isIntersecting; gxKick(); }).observe($('#gxstage'));
  else gx.visible = true;
  document.addEventListener('visibilitychange', () => { gx.last = 0; gxKick(); });
  if (window.ResizeObserver) new ResizeObserver(() => { gx.hud = null; gxResize(); }).observe($('#gxstage'));
  gxRM.addEventListener && gxRM.addEventListener('change', gxKick);
  gxResize();
}
function gxPinch(){ const p = [...gx.pointers.values()]; return Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) || 1; }

// ---------- methods: physics twins of methods.py (the tests compare them) ----------
const MX = D.methods || null;
const MX_GM = {sun: 1.3271244e20, jup: 1.2668653e17, earth: 3.986004e14}, MX_R = {sun: 6.957e8, jup: 7.1492e7, earth: 6.3781e6};
const MX_AU = 1.495978707e11, MX_DAY = 86400, MX_C = 299792458;
function mxK(P, mp, ms, e, sini){ const gmp = mp * MX_GM.jup, gms = ms * MX_GM.sun; return Math.cbrt(2 * Math.PI / (P * MX_DAY)) * gmp * (sini == null ? 1 : sini) / Math.pow(gms + gmp, 2 / 3) / Math.sqrt(1 - (e || 0) ** 2); }
function mxKeplerE(M, e){
  M = M % (2 * Math.PI); let E = e < 0.8 ? M : Math.PI;
  for (let i = 0; i < 60; i++){ const d = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E)); E -= d; if (Math.abs(d) < 1e-12) break; }
  return E;
}
function mxNu(M, e){ const E = mxKeplerE(M, e); return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2)); }
// Star, barycentre (origin) and planet in the orbital plane at phase t (0 = periastron), orbit rotated by w.
function mxBodies(t, e, q, w){
  const nu = mxNu(2 * Math.PI * t, e), r = (1 - e * e) / (1 + e * Math.cos(nu)), th = nu + (w || 0);
  const px = r * (1 - q) * Math.cos(th), py = r * (1 - q) * Math.sin(th);
  return {planet: [px, py], star: [-r * q * Math.cos(th), -r * q * Math.sin(th)], bary: [0, 0], nu};
}
const mxPacz = u => (u * u + 2) / (u * Math.sqrt(u * u + 4));
function mxLd(teff){
  const T = MX.claret;
  if (teff <= T[0][0]) return [T[0][1], T[0][2]];
  if (teff >= T[T.length - 1][0]) return [T[T.length - 1][1], T[T.length - 1][2]];
  for (let i = 0; i < T.length - 1; i++) if (teff >= T[i][0] && teff <= T[i + 1][0]){ const f = (teff - T[i][0]) / (T[i + 1][0] - T[i][0]); return [T[i][1] + f * (T[i + 1][1] - T[i][1]), T[i][2] + f * (T[i + 1][2] - T[i][2])]; }
}
function mxI(r, u1, u2){ const mu = Math.sqrt(Math.max(0, 1 - r * r)); return 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2; }
function mxOverlap(z, k){
  if (z >= 1 + k) return 0;
  if (z <= 1 - k) return Math.PI * k * k;
  if (z <= k - 1) return Math.PI;
  const c = x => Math.max(-1, Math.min(1, x));
  const k0 = Math.acos(c((k * k + z * z - 1) / (2 * k * z))), k1 = Math.acos(c((1 - k * k + z * z) / (2 * z)));
  return k * k * k0 + k1 - 0.5 * Math.sqrt(Math.max(0, 4 * z * z - (1 + z * z - k * k) ** 2));
}
function mxFlux(z, k, u1, u2){
  const A = mxOverlap(z, k); if (A <= 0) return 1;
  const r = z <= 1 - k ? Math.min(z, 1) : Math.min(1, (z - k + 1) / 2);
  return 1 - A * mxI(r, u1, u2) / (Math.PI * (1 - u1 / 3 - u2 / 6));
}
function mxG(x, mu, s1, s2){ const t = (x - mu) / (x < mu ? s1 : s2); return Math.exp(-0.5 * t * t); }
function mxTeffRGB(T){
  let X = 0, Y = 0, Z = 0;
  for (let lam = 380; lam <= 780; lam += 5){
    const l = lam * 1e-9, b = 1 / (l ** 5 * (Math.exp(1.4387769e-2 / (l * T)) - 1));
    X += b * (1.056 * mxG(lam, 599.8, 37.9, 31.0) + 0.362 * mxG(lam, 442.0, 16.0, 26.7) - 0.065 * mxG(lam, 501.1, 20.4, 26.2));
    Y += b * (0.821 * mxG(lam, 568.8, 46.9, 40.5) + 0.286 * mxG(lam, 530.9, 16.3, 31.1));
    Z += b * (1.217 * mxG(lam, 437.0, 11.8, 36.0) + 0.681 * mxG(lam, 459.0, 26.0, 13.8));
  }
  const r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z, g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z, bl = 0.0557 * X - 0.2040 * Y + 1.0570 * Z, m = Math.max(r, g, bl);
  return [r, g, bl].map(c => { c = Math.max(0, c / m); c = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055; return Math.round(255 * Math.min(1, c)); });
}
function mxClass(T){ let best = MX.mamajek[0]; for (const r of MX.mamajek) if (Math.abs(r[1] - T) < Math.abs(best[1] - T)) best = r; return [best[0][0], best[0]]; }
// The star's motion on screen: if its true orbit would be under a few pixels, it is multiplied by a
// stated power of ten. Returns the factor and the label that must accompany it.
function mxWobbleScale(q, Rpx, aAU, rstar){
  const px = Rpx * q; let N = 1;
  if (!(px > 0)) return {N: 1, label: ''};
  while (px * N < 14 && N < 1e12) N *= 10;
  const km = aAU * MX_AU * q / 1000, inR = rstar ? km * 1000 / (rstar * MX_R.sun) : null;
  const label = N > 1 ? `star's motion exaggerated ×${N.toLocaleString('en-GB')}; true a★ = ${km < 10 ? km.toFixed(2) : Math.round(km).toLocaleString('en-GB')} km${inR != null ? ` ≈ ${inR < 0.01 ? inR.toExponential(1) : inR.toFixed(2)} R★` : ''}` : '';
  return {N, label};
}

// ---------- blocking starlight: Fraunhofer optics of a circular pupil (coronagraph families) ----------
// The pupil radius is 1 and a focal-plane angle u is in λ/D, so the transform variable is k = πu. Fields are
// radially symmetric, so each 2-D Fourier transform is a Hankel transform with a J0 kernel.
function mxJ0(x){
  const ax = Math.abs(x);
  if (ax < 8){ const y = x * x;
    return (57568490574.0 + y * (-13362590354.0 + y * (651619640.7 + y * (-11214424.18 + y * (77392.33017 + y * -184.9052456))))) /
      (57568490411.0 + y * (1029532985.0 + y * (9494680.718 + y * (59272.64853 + y * (267.8532712 + y))))); }
  const z = 8 / ax, y = z * z, xx = ax - 0.785398164;
  const a = 1 + y * (-0.1098628627e-2 + y * (0.2734510407e-4 + y * (-0.2073370639e-5 + y * 0.2093887211e-6)));
  const b = -0.1562499995e-1 + y * (0.1430488765e-3 + y * (-0.6911147651e-5 + y * (0.7621095161e-6 - y * 0.934935152e-7)));
  return Math.sqrt(0.636619772 / ax) * (Math.cos(xx) * a - z * Math.sin(xx) * b);
}
function mxJ1(x){
  const ax = Math.abs(x);
  if (ax < 8){ const y = x * x;
    return x * (72362614232.0 + y * (-7895059235.0 + y * (242396853.1 + y * (-2972611.439 + y * (15704.48260 + y * -30.16036606))))) /
      (144725228442.0 + y * (2300535178.0 + y * (18583304.74 + y * (99447.43394 + y * (376.9991397 + y))))); }
  const z = 8 / ax, y = z * z, xx = ax - 2.356194491;
  const a = 1 + y * (0.183105e-2 + y * (-0.3516396496e-4 + y * (0.2457520174e-5 + y * -0.240337019e-6)));
  const b = 0.04687499995 + y * (-0.2002690873e-3 + y * (0.8449199096e-5 + y * (-0.88228987e-6 + y * 0.105787412e-6)));
  const v = Math.sqrt(0.636619772 / ax) * (Math.cos(xx) * a - z * Math.sin(xx) * b);
  return x < 0 ? -v : v;
}
function mxJn(n, x){
  if (n === 0) return mxJ0(x); if (n === 1) return mxJ1(x);
  if (Math.abs(x) < n + 1){ const h = x / 2; let f = 1; for (let i = 2; i <= n; i++) f *= i; let term = Math.pow(h, n) / f, s = 0;
    for (let m = 0; m < 30; m++){ s += term; term *= -h * h / ((m + 1) * (m + 1 + n)); } return s; }
  let jm = mxJ0(x), j = mxJ1(x); for (let k = 1; k < n; k++){ const t = 2 * k / x * j - jm; jm = j; j = t; } return j;
}
const mxAiry = u => { const k = Math.PI * u; return Math.abs(k) < 1e-9 ? 1 : (2 * mxJ1(k) / k) ** 2; };
function mxSonine(u, n){ const k = Math.PI * u; if (Math.abs(k) < 1e-6) return 1; let f = 1; for (let i = 2; i <= n + 1; i++) f *= i; return Math.pow(2, n + 1) * f * mxJn(n + 1, k) / Math.pow(k, n + 1); }
const mxSonineI = (u, n) => (mxSonine(u, n) / (n + 1)) ** 2;
function mxSimpson(f, a, b, n){ n += n % 2; const h = (b - a) / n; let s = f(a) + f(b); for (let i = 1; i < n; i++) s += (i % 2 ? 4 : 2) * f(a + i * h); return s * h / 3; }
// The Lyot plane: the pupil minus what the occulting mask (radius m λ/D) removed. Bright at the rim.
function mxLyotPupil(rho, m){ return (rho < 1 ? 1 : 0) - mxSimpson(k => mxJ1(k) * mxJ0(k * rho), 0, Math.PI * m, 400); }
// Tabulated once per mask (inside and outside the rim, where the field jumps), then the final image for any stop:
// I(u) = [2 ∫₀^s E(ρ) J0(πuρ) ρ dρ]², relative to the unblocked star's peak.
function mxLyotTable(m){
  const A = [], B = [], NA = 300, NB = 100;
  for (let i = 0; i <= NA; i++){ const r = i / NA * (1 - 1e-9); A.push([r, mxLyotPupil(r, m)]); }
  for (let i = 0; i <= NB; i++){ const r = 1 + 1e-9 + i / NB * 0.5; B.push([r, mxLyotPupil(r, m)]); }
  return {m, A, B};
}
function mxLyotFinal(T, u, s){
  const k = Math.PI * u, seg = (P, lim) => { let v = 0; for (let i = 1; i < P.length && P[i - 1][0] < lim; i++){
    const r0 = P[i - 1][0], r1 = Math.min(lim, P[i][0]), e1 = P[i - 1][1] + (P[i][1] - P[i - 1][1]) * (r1 - r0) / (P[i][0] - r0);
    v += 0.5 * (r1 - r0) * (P[i - 1][1] * mxJ0(k * r0) * r0 + e1 * mxJ0(k * r1) * r1); } return v; };
  const v = seg(T.A, Math.min(s, 1)) + (s > 1 ? seg(T.B, s) : 0);
  return (2 * v) ** 2;
}
// The ideal charge-2 vortex: no light inside the re-imaged pupil, (1/ρ)² outside it (methods.py: vortex_pupil_field).
const mxVortexPupil = rho => rho < 1 ? 0 : 1 / (rho * rho);
// Synthetic ADI (seeded with mxRand, below): quasi-static speckles fixed to the instrument, a planet turning with the sky. The median of the
// sequence models the speckles; each frame minus the median, turned back by its field rotation and averaged,
// keeps the planet (Marois et al. 2006). All synthetic: speckle pattern, noise and planet brightness are illustrative.
function mxAdi(seed, o){
  o = Object.assign({G: 64, N: 24, rot: 60, lod: 3, rp: 16, pa: 20, planet: 0.6, noise: 0.04, jitter: 0.12}, o || {});
  const {G, N} = o, rnd = mxRand(seed), c0 = (G - 1) / 2, sig = o.lod / 2.355, gauss = () => { let s = 0; for (let i = 0; i < 6; i++) s += rnd(); return (s - 3) / Math.SQRT2; };
  const sp = []; for (let i = 0; i < 110; i++){ const r = 5 + rnd() * 24, a = rnd() * 2 * Math.PI; sp.push([c0 + r * Math.cos(a), c0 + r * Math.sin(a), Math.exp(-r / 10) * (0.3 + rnd())]); }
  const blob = (F, x, y, A) => { for (let j = Math.max(0, Math.floor(y - 4 * sig)); j <= Math.min(G - 1, Math.ceil(y + 4 * sig)); j++) for (let i = Math.max(0, Math.floor(x - 4 * sig)); i <= Math.min(G - 1, Math.ceil(x + 4 * sig)); i++) F[j * G + i] += A * Math.exp(-((i - x) ** 2 + (j - y) ** 2) / (2 * sig * sig)); };
  // The planet's brightness is set against the typical speckle at its radius.
  const ring = sp.filter(s => Math.abs(Math.hypot(s[0] - c0, s[1] - c0) - o.rp) < 3).map(s => s[2]), Ap = o.planet * (ring.length ? ring.reduce((a, b) => a + b, 0) / ring.length : 0.2);
  const frames = [], ang = [];
  for (let k = 0; k < N; k++){
    const F = new Float32Array(G * G), th = o.rot * k / (N - 1); ang.push(th);
    for (const s of sp) blob(F, s[0], s[1], s[2] * (1 + o.jitter * gauss()));
    const a = (o.pa + th) * Math.PI / 180; blob(F, c0 + o.rp * Math.cos(a), c0 + o.rp * Math.sin(a), Ap);
    for (let p = 0; p < G * G; p++) F[p] += o.noise * gauss();
    frames.push(F);
  }
  const med = new Float32Array(G * G), col = new Float32Array(N);
  for (let p = 0; p < G * G; p++){ for (let k = 0; k < N; k++) col[k] = frames[k][p]; col.sort(); med[p] = N % 2 ? col[(N - 1) / 2] : 0.5 * (col[N / 2 - 1] + col[N / 2]); }
  // Turn each residual back by its field rotation (bilinear), then average the first n of them.
  const derot = (R, th) => { const out = new Float32Array(G * G), ca = Math.cos(th * Math.PI / 180), sa = Math.sin(th * Math.PI / 180);
    for (let j = 0; j < G; j++) for (let i = 0; i < G; i++){ const x = i - c0, y = j - c0, xs = c0 + ca * x - sa * y, ys = c0 + sa * x + ca * y, i0 = Math.floor(xs), j0 = Math.floor(ys);
      if (i0 < 0 || j0 < 0 || i0 >= G - 1 || j0 >= G - 1) continue; const fx = xs - i0, fy = ys - j0;
      out[j * G + i] = R[j0 * G + i0] * (1 - fx) * (1 - fy) + R[j0 * G + i0 + 1] * fx * (1 - fy) + R[(j0 + 1) * G + i0] * (1 - fx) * fy + R[(j0 + 1) * G + i0 + 1] * fx * fy; }
    return out; };
  const stacks = [], acc = new Float32Array(G * G);
  for (let k = 0; k < N; k++){ const R = new Float32Array(G * G); for (let p = 0; p < G * G; p++) R[p] = frames[k][p] - med[p];
    const D = derot(R, ang[k]); for (let p = 0; p < G * G; p++) acc[p] += D[p]; stacks.push(Float32Array.from(acc, v => v / (k + 1))); }
  // Signal-to-noise at the planet's (de-rotated) place against the rest of its annulus.
  const a0 = o.pa * Math.PI / 180, px = c0 + o.rp * Math.cos(a0), py = c0 + o.rp * Math.sin(a0);
  const snr = F => { let s = 0, n = 0, m = 0, q = 0, nn = 0;
    for (let j = 0; j < G; j++) for (let i = 0; i < G; i++){ const d = Math.hypot(i - px, j - py), r = Math.hypot(i - c0, j - c0);
      if (d < 1.5){ s += F[j * G + i]; n++; } else if (d > 6 && Math.abs(r - o.rp) < 3){ m += F[j * G + i]; q += F[j * G + i] ** 2; nn++; } }
    const mu = m / nn, sd = Math.sqrt(Math.max(1e-12, q / nn - mu * mu)); return (s / n - mu) / sd; };
  return {G, N, frames, med, stacks, ang, snrRaw: snr(frames[0]), snr: stacks.map(snr), c0, sig, Ap, o, px, py};
}

// ---------- stages: a canvas with play, speed and a time scrubber; still under reduced motion ----------
const mxRM = window.matchMedia('(prefers-reduced-motion: reduce)');
const MXV = {};
const mxStages = [];
function mxRgb(c, a){ return `rgba(${c[0]},${c[1]},${c[2]},${a == null ? 1 : a})`; }
function mxRand(seed){ let s = seed >>> 0 || 1; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
function mxSetup(fig, extra){
  if (fig._mx) return fig._mx;
  const vis = MXV[fig.dataset.vis]; if (!vis) return null;
  const cv = fig.querySelector('canvas'), st = {fig, cv, ctx: cv.getContext('2d'), vis, t: vis.key || 0, playing: false, speed: 1, on: false, visible: false, last: 0, raf: 0, opt: Object.assign({}, extra || {}), exag: ''};
  fig._mx = st; mxStages.push(st);
  if (vis.init) vis.init(st);
  const play = fig.querySelector('.mxplay'), scrub = fig.querySelector('.mxscrub'), speed = fig.querySelector('.mxspeed select');
  st.still = !play;   // a static view (a chart or a lab): no clock, redrawn when a control changes
  if (play) play.addEventListener('click', () => { mxPlay(st, !st.playing); });
  if (speed) speed.addEventListener('change', () => { st.speed = Number(speed.value); });
  if (scrub) scrub.addEventListener('input', () => { st.t = Number(scrub.value) / 1000; mxDraw(st); });
  fig.querySelectorAll('.mxctl select:not(.mxspeed select), .mxctl input[type=range]:not(.mxscrub), .mxctl .mxsize, .mxctl .mxtog').forEach(c => {
    const ev = c.tagName === 'BUTTON' ? 'click' : (c.type === 'range' ? 'input' : 'change');
    c.addEventListener(ev, () => { if (c.tagName === 'BUTTON') c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true')); if (vis.control) vis.control(st, c); mxDraw(st); });
  });
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { st.visible = es[0].isIntersecting; mxKick(st); }).observe(cv);
  else st.visible = true;
  if (window.ResizeObserver) new ResizeObserver(() => mxDraw(st)).observe(fig.querySelector('.mxcanvas'));
  return st;
}
function mxPlay(st, on){
  if (st.still) return;
  st.playing = on;
  const b = st.fig.querySelector('.mxplay'); b.textContent = on ? 'Pause' : 'Play'; b.setAttribute('aria-pressed', String(on));
  mxKick(st);
}
function mxKick(st){ if (st.playing && st.on && st.visible && !document.hidden && !st.raf){ st.last = 0; st.raf = requestAnimationFrame(ts => mxFrame(st, ts)); } }
function mxFrame(st, ts){
  st.raf = 0;
  if (!st.playing || !st.on || !st.visible || document.hidden) return;
  const dt = st.last ? Math.min(100, ts - st.last) : 16; st.last = ts;
  st.t = (st.t + dt / 1000 * st.speed / (st.vis.period || 10)) % 1;
  mxDraw(st);
  st.raf = requestAnimationFrame(t2 => mxFrame(st, t2));
}
function mxDraw(st){
  const box = st.cv.parentNode.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
  if (box.width < 2 || box.height < 2) return;   // hidden: nothing to draw
  const w = Math.round(box.width), h = Math.round(box.height);
  if (st.cv.width !== Math.round(w * dpr) || st.cv.height !== Math.round(h * dpr)){ st.cv.width = Math.round(w * dpr); st.cv.height = Math.round(h * dpr); }
  const c = st.ctx; c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
  c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
  st.exag = '';
  st.vis.draw(c, w, h, st.t, st);
  const ex = st.fig.querySelector('.mxexag'); if (ex.textContent !== st.exag) ex.textContent = st.exag;
  ex.hidden = !st.exag;
  const sc = st.fig.querySelector('.mxscrub');
  if (sc){ if (document.activeElement !== sc) sc.value = Math.round(st.t * 1000);
    // The scrubber's spoken value, in the visual's own cycle (written only when it changes).
    const vt = `t = ${st.t.toFixed(2)} of the ${(MX && MX.tunit && MX.tunit[st.fig.dataset.vis]) || 'cycle'}`; if (sc.getAttribute('aria-valuetext') !== vt) sc.setAttribute('aria-valuetext', vt); }
}
// Shown or hidden with its chapter: only the open chapter's stages run. Under reduced motion nothing
// plays by itself; each stage shows its key frame and plays only when asked.
function mxActivate(article, on){
  article.querySelectorAll('.mxstage').forEach(fig => {
    if (!on && !fig._mx) return;   // stages are set up the first time their chapter opens
    const st = mxSetup(fig); if (!st) return;
    st.on = on;
    if (on){ mxDraw(st); if (!mxRM.matches && !st.started){ st.started = true; mxPlay(st, true); } else mxKick(st); }
  });
}
document.addEventListener('visibilitychange', () => mxStages.forEach(mxKick));
document.addEventListener('setu-render-ready', () => mxStages.forEach(mxKick));  // the renderer finished a surface in idle time

// ---------- shared drawing pieces ----------
function mxText(c, s, x, y, o){ o = o || {}; c.font = `${o.w || 500} ${o.size || 11}px ${o.mono ? '"Geist Mono",ui-monospace,monospace' : '"Geist",system-ui,sans-serif'}`; c.fillStyle = o.color || '#A1A1A6'; c.textAlign = o.align || 'left'; c.textBaseline = o.base || 'alphabetic'; c.fillText(s, x, y); }
// The star and the planet are drawn by the shared renderer (setuhq.renderer, window.SetuRender) when it is loaded:
// the same blackbody colour and limb darkening, the planet's look from its measured values. Below each adapter is
// the drawing it falls back to when the renderer is missing.
function mxStar(c, x, y, R, teff, t, opt){
  if (window.SetuRender) return SetuRender.drawStar2D(c, x, y, R, teff, t, opt);
  opt = opt || {};
  const rgb = mxTeffRGB(teff), [u1, u2] = mxLd(teff);
  // Corona glow.
  const g0 = c.createRadialGradient(x, y, R * 0.9, x, y, R * (opt.glow || 2.1));
  g0.addColorStop(0, mxRgb(rgb, 0.32)); g0.addColorStop(1, mxRgb(rgb, 0));
  c.fillStyle = g0; c.beginPath(); c.arc(x, y, R * (opt.glow || 2.1), 0, 2 * Math.PI); c.fill();
  // Limb darkening from the quadratic law at this Teff (Claret 2017).
  const g = c.createRadialGradient(x, y, 0, x, y, R);
  for (let i = 0; i <= 10; i++){ const r = i / 10, I = mxI(Math.min(r, 0.999), u1, u2); g.addColorStop(r, mxRgb(rgb.map(v => v * I))); }
  c.fillStyle = g; c.beginPath(); c.arc(x, y, R, 0, 2 * Math.PI); c.fill();
  // Granulation: cells that drift and flicker (texture only; not to scale).
  if (R > 14 && !opt.flat){
    c.save(); c.beginPath(); c.arc(x, y, R, 0, 2 * Math.PI); c.clip();
    const rnd = mxRand(11), n = Math.min(260, Math.round(R * R / 18));
    for (let i = 0; i < n; i++){
      const a = rnd() * 2 * Math.PI + t * 0.6, rr = Math.sqrt(rnd()) * R, s = R * (0.035 + rnd() * 0.04);
      const cx = x + rr * Math.cos(a), cy = y + rr * Math.sin(a), f = 0.5 + 0.5 * Math.sin(t * 40 + i);
      c.fillStyle = `rgba(255,255,255,${0.035 + 0.05 * f})`; c.beginPath(); c.arc(cx, cy, s, 0, 2 * Math.PI); c.fill();
      c.fillStyle = `rgba(0,0,0,${0.05 * (1 - f)})`; c.beginPath(); c.arc(cx + s * 0.9, cy + s * 0.4, s * 0.5, 0, 2 * Math.PI); c.fill();
    }
    c.restore();
  }
  return rgb;
}
function mxPlanet(c, x, y, r, cls, lit){
  // cls: a look's name (setuhq.looks), "silhouette" (a candidate: never planet art), or an old class number.
  if (window.SetuRender) return SetuRender.drawPlanet2D(c, x, y, r, cls, lit);
  if (typeof cls === 'string') cls = cls === 'silhouette' ? 2 : /giant|jupiter/.test(cls) ? 4 : /neptune/.test(cls) ? 3 : /envelope|ambiguous/.test(cls) ? 2 : 0;
  // Look by class: 0 Earth-size, 1 super-Earth (rocky); 2 sub-Neptune, 3 Neptune-like (haze); 4 gas giant (bands).
  c.save(); c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.clip();
  const base = cls >= 4 ? [196, 160, 120] : cls >= 2 ? [120, 170, 214] : [150, 128, 110];
  c.fillStyle = mxRgb(base); c.fillRect(x - r, y - r, 2 * r, 2 * r);
  if (cls >= 4) for (let i = -3; i <= 3; i++){ c.fillStyle = i % 2 ? 'rgba(90,60,40,.35)' : 'rgba(255,240,220,.18)'; c.fillRect(x - r, y + i * r / 3.5, 2 * r, r / 5); }
  else if (cls >= 2){ const h = c.createRadialGradient(x, y, r * 0.2, x, y, r); h.addColorStop(0, 'rgba(255,255,255,.15)'); h.addColorStop(1, 'rgba(180,220,255,.5)'); c.fillStyle = h; c.fillRect(x - r, y - r, 2 * r, 2 * r); }
  else { c.fillStyle = 'rgba(60,45,35,.35)'; c.beginPath(); c.arc(x - r * 0.3, y + r * 0.2, r * 0.4, 0, 2 * Math.PI); c.fill(); }
  // Shading: lit from the star's side, dark when silhouetted against it.
  const s = c.createLinearGradient(x - r, y, x + r, y);
  s.addColorStop(0, `rgba(0,0,0,${lit ? 0.1 : 0.85})`); s.addColorStop(1, `rgba(0,0,0,${lit ? 0.75 : 0.92})`);
  c.fillStyle = s; c.fillRect(x - r, y - r, 2 * r, 2 * r);
  c.restore();
  if (cls >= 2){ c.strokeStyle = 'rgba(150,200,255,.35)'; c.lineWidth = 1; c.beginPath(); c.arc(x, y, r + 0.5, 0, 2 * Math.PI); c.stroke(); }
}
function mxAxes(c, x, y, w, h, o){
  c.strokeStyle = 'rgba(255,255,255,.14)'; c.lineWidth = 1; c.strokeRect(x + .5, y + .5, w, h);
  mxText(c, o.y, x, y - 6, {size: 11, w: 600, color: '#C7C7CC', mono: true});
  mxText(c, o.x, x + w - 6, y + h - 6, {size: 11, w: 600, color: '#8E8E93', mono: true, align: 'right'});
}
function mxGlassPanel(c, x, y, w, h){ c.fillStyle = 'rgba(28,28,30,.72)'; c.strokeStyle = 'rgba(255,255,255,.12)'; c.lineWidth = 1; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, 14) : c.rect(x, y, w, h); c.fill(); c.stroke(); }
// The planet's look from its stored values (setuhq.looks.look, by way of SetuRender.look); null without the renderer.
const mxLookOf = p => window.SetuRender ? SetuRender.look({radius: p.radius, mass: p.mass, msini: p.mass_sini, a: p.semi_major_axis, period: p.orbital_period,
  srad: p.star_radius, smass: p.star_mass, steff: p.star_teff, teq: p.temp_calculated}).name : null;
const mxClassOf = (rp, mp) => { if (rp){ const re = rp * 11.209; return re < 1.25 ? 0 : re < 2 ? 1 : re < 4 ? 2 : re < 10 ? 3 : 4; } if (mp){ const me = mp * 317.83; return me < 2 ? 0 : me < 10 ? 1 : me < 50 ? 3 : 4; } return null; };

// ---------- the animated system: star (Teff colour, limb darkening, granulation), orbit, planet, light curve ----------
function mxSystemParams(p, dip){
  const teff = p.star_teff || 5772, rs = p.star_radius, rp = p.radius, a = p.semi_major_axis, P = p.orbital_period;
  const scale = !!(rs && rp), k = scale ? rp * MX_R.jup / (rs * MX_R.sun) : 0.1;
  const ars = (a && rs) ? a * MX_AU / (rs * MX_R.sun) : 12;
  let b = p.impact_parameter, bSrc = 'stored';
  if (b == null && p.inclination != null && a && rs){ b = ars * Math.cos(p.inclination * Math.PI / 180); bSrc = 'from a/R★ and i'; }
  if (b == null || b > 1 + k){ b = 0.3; bSrc = 'illustrative'; }
  return {teff, rs, rp, a, P, k, ars, b, bSrc, scale, cls: mxClassOf(rp, p.mass || p.mass_sini), name: p.name || '', dip: dip || null, inc: p.inclination,
    ld: p.ld && p.ld[0] != null ? p.ld : null, dt0: p.t0_offset_days || 0, look: p.look || mxLookOf(p)};
}
function mxDurations(P, ars, k, b){
  const inc = Math.acos(Math.min(1, b / ars)), si = Math.sin(inc), f = x => P / Math.PI * Math.asin(Math.min(1, x / (ars * si)));
  return [f(Math.sqrt(Math.max(0, (1 + k) ** 2 - b * b))), (1 - k) ** 2 - b * b > 0 ? f(Math.sqrt((1 - k) ** 2 - b * b)) : null];
}
function mxDrawSystem(c, w, h, t, st){
  const S = st.opt.sys; if (!S) return;
  const P = S.P || 10, [u1, u2] = S.ld || mxLd(S.teff), [t14] = mxDurations(P, S.ars, S.k, S.b);
  const win = Math.min(0.24, 0.9 * t14 / P);   // half-window of the chart, as a fraction of the orbit
  // Time runs slowly through the transit window and faster for the rest of the orbit (stated on screen).
  const phi = t < 0.5 ? -win + t / 0.5 * 2 * win : win + (t - 0.5) / 0.5 * (1 - 2 * win);
  const sceneH = h * 0.56, cx = w / 2, cy = sceneH * 0.52, Rs = Math.min(sceneH * 0.26, w * 0.13);
  const A = Math.min(w * 0.42, Rs * 5.2), By = S.b * Rs;     // orbit not to scale; crossing at the stored b
  const ang = 2 * Math.PI * phi, px = cx + A * Math.sin(ang), py = cy + By * Math.cos(ang), front = Math.cos(ang) > 0;
  const big = !!st.opt.big, rpx = Math.max(1.5, S.k * Rs * (big ? 5 : 1));
  c.setLineDash([4, 6]); c.strokeStyle = 'rgba(255,255,255,.28)'; c.lineWidth = 1;
  c.beginPath(); c.ellipse(cx, cy, A, Math.max(0.5, By), 0, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
  const cls = S.look || (S.cls == null ? 2 : S.cls);
  if (!front) mxPlanet(c, px, py, rpx, cls, true);
  mxStar(c, cx, cy, Rs, S.teff, t);
  if (front){ const over = Math.hypot(px - cx, py - cy) < Rs + rpx; mxPlanet(c, px, py, rpx, cls, !over); }
  const [cl, row] = mxClass(S.teff);
  mxText(c, `${cl} · ≈${row} · ${Math.round(S.teff).toLocaleString('en-GB')} K`, 14, 22, {size: 12, w: 600, color: '#F5F5F7'});
  mxText(c, S.scale ? `star and planet sizes to scale${big ? '; planet ×5' : ''}` : 'sizes not to scale (radius not stored)', 14, 40, {size: 11});
  if (w < 600){
    mxText(c, `orbit not to scale (a = ${S.ars.toFixed(1)} R★)`, 14, 56, {size: 11});
    mxText(c, `crosses at b = ${S.b.toFixed(2)} (${S.bSrc})`, 14, 72, {size: 11});
    if (t >= 0.5) mxText(c, 'outside the transit: time runs faster', w - 14, sceneH - 6, {size: 11, align: 'right'});
  } else {
    mxText(c, `orbit not to scale (a = ${S.ars.toFixed(1)} R★); crosses at b = ${S.b.toFixed(2)} (${S.bSrc})`, 14, 56, {size: 11});
    if (t >= 0.5) mxText(c, 'outside the transit: time runs faster', w - 14, 22, {size: 11, align: 'right'});
  }
  if (big) st.exag = 'planet drawn ×5; depth and times true';
  // Light curve: model from stored values, limb-darkened (small-planet Mandel & Agol 2002).
  const gx0 = 54, gy0 = sceneH + 26, gw = w - gx0 - 18, gh = h - gy0 - 40;
  mxGlassPanel(c, 10, sceneH + 6, w - 20, h - sceneH - 12);
  // A dip page draws the model at its fit's mid-time (S.dt0 days from the dip's own), so it lies on the stored fit.
  const f0 = (S.dt0 || 0) / P, zOf = f => { f -= f0; return S.ars * Math.sqrt(Math.sin(2 * Math.PI * f) ** 2 + (S.b / S.ars) ** 2 * Math.cos(2 * Math.PI * f) ** 2); };
  const depth = 1 - mxFlux(S.b / 1, S.k, u1, u2), floor = Math.min(1 - 1.35 * Math.max(depth, 1e-5), ...(S.dip && S.dip.pts ? S.dip.pts.map(p => 1 + p[1] * 1e-6 - 0.00002) : [1]), ...(S.dip && S.dip.model ? S.dip.model.map(p => 1 + p[1] * 1e-6 - 0.00002) : [1]));
  const X = f => gx0 + (f + win) / (2 * win) * gw, Y = v => gy0 + (1 - v) / (1 - floor) * gh * 0.86 + 6;
  mxAxes(c, gx0, gy0, gw, gh, {y: 'BRIGHTNESS (%)', x: 'TIME FROM MID-TRANSIT (h)'});
  for (const v of [1, 1 - depth]){ c.strokeStyle = 'rgba(255,255,255,.08)'; c.beginPath(); c.moveTo(gx0, Y(v)); c.lineTo(gx0 + gw, Y(v)); c.stroke(); mxText(c, (v * 100).toFixed(depth < 0.001 ? 3 : 2), gx0 - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
  for (const hh of [-1, 0, 1]){ const f = hh * win * 0.8, xx = X(f); mxText(c, (f * P * 24).toFixed(1), xx, gy0 + gh + 13, {size: 11, mono: true, align: 'center'}); }
  if (S.dip && S.dip.model && S.dip.model.length){
    c.save(); c.beginPath(); c.rect(gx0, gy0, gw, gh); c.clip();
    c.setLineDash([5, 4]); c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 1.2; c.beginPath();
    S.dip.model.forEach((p, i) => { const x = X(p[0] / P), y = Y(1 + p[1] * 1e-6); i ? c.lineTo(x, y) : c.moveTo(x, y); }); c.stroke(); c.setLineDash([]);
    c.restore();
  }
  if (S.dip && S.dip.pts){
    c.fillStyle = 'rgba(100,210,255,.55)';
    c.save(); c.beginPath(); c.rect(gx0, gy0, gw, gh); c.clip();
    for (const p of S.dip.pts){ const f = p[0] / P; if (Math.abs(f) > win) continue; c.fillRect(X(f) - 1.2, Y(1 + p[1] * 1e-6) - 1.2, 2.4, 2.4); }
    c.restore();
  }
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.8; c.beginPath();
  const upto = t < 0.5 ? phi : win;
  for (let i = 0; i <= 240; i++){ const f = -win + 2 * win * i / 240; if (f > upto) break; const v = mxFlux(zOf(f), S.k, u1, u2); i ? c.lineTo(X(f), Y(v)) : c.moveTo(X(f), Y(v)); }
  c.stroke();
  if (t < 0.5){ const v = mxFlux(zOf(phi), S.k, u1, u2); c.fillStyle = '#FFB340'; c.beginPath(); c.arc(X(phi), Y(v), 3.5, 0, 2 * Math.PI); c.fill(); }
  const cap = S.dip ? 'line: model from stored values · dots: SetuHQ’s stored points' + (S.dip.model && S.dip.model.length ? ' · dashed: stored fit' : '') : 'line: model from stored values, not observed data';
  // On a narrow stage the key goes on its own lines in the free band under the dip, clear of the curve and the axis title.
  if (w < 600) cap.split(' · ').forEach((t, i, all) => mxText(c, t, gx0 + 6, gy0 + gh * 0.74 + i * 14 - (all.length - 2) * 7, {size: 11}));
  else mxText(c, cap, gx0 + gw, gy0 - 6, {size: 11, align: 'right'});
}
MXV.system = {key: 0.25, period: 12, init(st){
  const ex = MX.examples['pi Men c'] || {};
  st.opt.sys = mxSystemParams(Object.assign({name: 'pi Men c'}, ex), MX.lead_dip ? {pts: MX.lead_dip.pts} : null);
  st.opt.b0 = st.opt.sys.b;
}, control(st, el){
  if (el.classList.contains('mxsize')) st.opt.big = el.getAttribute('aria-pressed') === 'true';
  if (el.type === 'range'){ st.opt.sys.b = Number(el.value) / 1000 * (1 + st.opt.sys.k); st.opt.sys.bSrc = 'slider'; }
}, draw: mxDrawSystem};

// ---------- a survey scan ----------
MXV.scan = {key: 0.62, period: 16, init(st){
  const rnd = mxRand(5), teffs = [3200, 3500, 3900, 4400, 5000, 5600, 5900, 6400, 7200, 9000, 15000];
  st.opt.stars = Array.from({length: 320}, () => ({x: rnd(), y: rnd(), m: rnd(), teff: teffs[Math.floor(Math.pow(rnd(), 1.6) * teffs.length)]}));
  st.opt.cols = {}; for (const T of teffs) st.opt.cols[T] = mxTeffRGB(T);
  st.opt.locks = Array.from({length: 26}, (_, i) => Math.floor(rnd() * 320));
  // About R★/a of random orbits transit: for a pi Men c-like orbit, 7.5% (see the table).
  st.opt.aligned = st.opt.locks.map((s, i) => ((i * 0.075 + 0.04) % 1) < 0.075);
}, draw(c, w, h, t, st){
  const S = st.opt;
  for (const s of S.stars){ const r = 0.6 + 1.8 * s.m ** 3; c.fillStyle = mxRgb(S.cols[s.teff], 0.55 + 0.45 * s.m); c.beginPath(); c.arc(s.x * w, s.y * h, r, 0, 2 * Math.PI); c.fill(); }
  c.strokeStyle = 'rgba(100,210,255,.12)'; c.lineWidth = 1;
  for (let i = 1; i < 4; i++){ c.beginPath(); c.moveTo(i * w / 4, 0); c.lineTo(i * w / 4, h); c.stroke(); c.beginPath(); c.moveTo(0, i * h / 4); c.lineTo(w, i * h / 4); c.stroke(); }
  const n = S.locks.length, cur = Math.floor(t * n), frac = t * n - cur;
  let seen = 0, hits = 0;
  for (let i = 0; i <= cur && i < n; i++){
    const s = S.stars[S.locks[i]], x = s.x * w, y = s.y * h, done = i < cur;
    if (done){ seen++; if (S.aligned[i]) hits++; }
    const r = done ? 9 : 9 + 34 * (1 - Math.min(1, frac / 0.5));
    c.strokeStyle = done ? (S.aligned[i] ? '#64D2FF' : 'rgba(255,255,255,.28)') : '#F5F5F7'; c.lineWidth = done ? 1 : 1.5;
    c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.stroke();
    if (!done){ for (let k = 0; k < 4; k++){ const a = k * Math.PI / 2; c.beginPath(); c.moveTo(x + Math.cos(a) * (r + 3), y + Math.sin(a) * (r + 3)); c.lineTo(x + Math.cos(a) * (r + 10), y + Math.sin(a) * (r + 10)); c.stroke(); } }
    if (done && S.aligned[i]) mxText(c, 'orbit aligned: transits', x > w - 160 ? x - 12 : x + 12, y + 4, {size: 11, color: '#64D2FF', align: x > w - 160 ? 'right' : 'left'});
  }
  mxGlassPanel(c, 10, h - 52, 290, 42);
  mxText(c, `targets checked ${String(seen).padStart(2, '0')} · aligned ${hits}`, 22, h - 34, {size: 12, mono: true, color: '#F5F5F7'});
  mxText(c, 'expected ≈ R★/a = 7.5% for a pi Men c-like orbit', 22, h - 18, {size: 11});
  if (!S.intro) mxText(c, 'star positions illustrative; colours from temperature', w - 12, 18, {size: 11, align: 'right'});
}};

// ---------- toward and away: Doppler shift ----------
const MX_LINES = [[486.1, 'Hβ'], [517.3, 'Mg'], [589.0, 'Na'], [656.3, 'Hα'], [527.0, 'Fe']];
function mxSpectrum(c, x, y, w, h, shiftNm, label){
  const g = c.createLinearGradient(x, 0, x + w, 0), stops = [[400, '#7A3CFF'], [450, '#2E6BFF'], [490, '#22C1E6'], [530, '#3EDB62'], [575, '#F2E43A'], [610, '#FF9F2E'], [700, '#E0302F']];
  for (const [l, col] of stops) g.addColorStop((l - 400) / 300, col);
  c.fillStyle = g; c.fillRect(x, y, w, h);
  for (const [l, n] of MX_LINES){
    const x0 = x + (l - 400) / 300 * w, x1 = x + (l + shiftNm - 400) / 300 * w;
    c.strokeStyle = 'rgba(255,255,255,.7)'; c.setLineDash([2, 2]); c.beginPath(); c.moveTo(x0, y - 5); c.lineTo(x0, y); c.stroke(); c.setLineDash([]);
    c.fillStyle = '#000'; c.fillRect(x1 - 1.5, y, 3, h);
    mxText(c, n, x0, y - 8, {size: 11, align: 'center'});
  }
  mxText(c, '400 nm', x, y + h + 13, {size: 11, mono: true}); mxText(c, '700 nm', x + w, y + h + 13, {size: 11, mono: true, align: 'right'});
  if (label) mxText(c, label, x + w / 2, y + h + 13, {size: 11, align: 'center', color: '#C7C7CC'});
}
function mxEye(c, x, y){ c.strokeStyle = '#F5F5F7'; c.lineWidth = 1.5; c.beginPath(); c.ellipse(x, y, 14, 7, 0, 0, 2 * Math.PI); c.stroke(); c.fillStyle = '#F5F5F7'; c.beginPath(); c.arc(x, y, 3.5, 0, 2 * Math.PI); c.fill(); mxText(c, 'observer', x + 22, y + 4, {size: 11}); }
// ---------- radio: cyclotron-maser emission, beamed in a hollow cone, and its frequency cut-off ----------
function mxFce(B){ return 1.602176634e-19 * B * 1e-4 / (2 * Math.PI * 9.1093837015e-31) / 1e6; }   // MHz for B in gauss (cyclotron_mhz)
const MX_BLOG = [-1, 3.5];   // the field slider: 0.1 G to ~3 kG, log scale
// The field slider announces its value and the cut-off it sets (from the start, not only after a change).
function mxRadioLabel(st){ const r = st.fig.querySelector('.mxbfield input'); if (r) r.setAttribute('aria-valuetext', `${st.opt.B.toPrecision(2)} gauss, cyclotron cut-off ${mxFce(st.opt.B).toPrecision(3)} MHz`); }
MXV.radio = {key: 0.1, period: 10, init(st){ st.opt.mode = 'aurora'; st.opt.B = 7.5; mxRadioLabel(st); },
  control(st, el){
    if (el.tagName === 'SELECT'){ st.opt.mode = el.value; const B = el.value === 'spi' ? 1000 : 7.5, r = st.fig.querySelector('.mxbfield input');
      st.opt.B = B; if (r) r.value = String(Math.round((Math.log10(B) - MX_BLOG[0]) / (MX_BLOG[1] - MX_BLOG[0]) * 1000)); }
    else if (el.type === 'range') st.opt.B = Math.pow(10, MX_BLOG[0] + Number(el.value) / 1000 * (MX_BLOG[1] - MX_BLOG[0]));
    mxRadioLabel(st);
  },
  draw(c, w, h, t, st){
    const spi = st.opt.mode === 'spi', B = st.opt.B, fce = mxFce(B);
    const sceneH = h * 0.56, cy = sceneH * 0.52, ox = w - 40, oy = cy;
    // The body that emits: the planet's own pole (aurora) or the star's footpoint (interaction).
    const sx = w * 0.3, sR = Math.min(sceneH * 0.2, w * 0.1), orbR = Math.min(w * 0.22, sceneH * 0.8), ang = 2 * Math.PI * t;
    const px = sx + orbR * Math.cos(ang), py = cy + orbR * 0.32 * Math.sin(ang);
    mxStar(c, sx, cy, sR, spi ? 3100 : 5400, t, {flat: true});
    c.strokeStyle = 'rgba(255,255,255,.18)'; c.setLineDash([3, 5]); c.beginPath(); c.ellipse(sx, cy, orbR, orbR * 0.32, 0, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
    // Dipole field lines: around the star (interaction) or the planet (aurora).
    const fx = spi ? sx : px, fy = spi ? cy : py, fR = spi ? sR : 9;
    c.strokeStyle = 'rgba(100,210,255,.35)'; c.lineWidth = 1;
    for (const L of spi ? [1.8, 2.6, 3.6] : [2.2, 3.4, 4.8]){ for (const sgn of [-1, 1]){ c.beginPath();
      for (let k = 0; k <= 40; k++){ const th = 0.15 + (Math.PI - 0.3) * k / 40, r = fR * L * Math.sin(th) ** 2, x = fx + sgn * r * Math.sin(th), y = fy - r * Math.cos(th); k ? c.lineTo(x, y) : c.moveTo(x, y); }
      c.stroke(); } }
    mxPlanet(c, px, py, 7, 4, true);
    // The flux tube from the planet to the star's footpoint (interaction only).
    const foot = [sx + sR * 0.35, cy - sR * 0.94];
    if (spi){ c.strokeStyle = 'rgba(255,179,64,.75)'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(px, py); c.quadraticCurveTo((px + foot[0]) / 2, Math.min(py, foot[1]) - 40, foot[0], foot[1]); c.stroke(); }
    // The hollow emission cone from the source, turning with the orbit; a burst when its wall crosses the observer.
    const src = spi ? foot : [px, py - 9], axis = -Math.PI / 2 + 0.9 * Math.cos(ang), half = 1.1, toObs = Math.atan2(oy - src[1], ox - src[0]);
    const off = Math.abs(Math.atan2(Math.sin(toObs - axis), Math.cos(toObs - axis))), hit = Math.abs(off - half) < 0.08;
    c.fillStyle = hit ? 'rgba(255,214,10,.28)' : 'rgba(255,214,10,.12)';
    for (const sgn of [-1, 1]){ const a = axis + sgn * half; c.beginPath(); c.moveTo(src[0], src[1]); c.arc(src[0], src[1], w * 0.6, a - 0.05, a + 0.05); c.closePath(); c.fill(); }
    mxEye(c, ox - 30, oy + 30);
    mxText(c, spi ? 'star–planet interaction: emission at the star’s footpoint' : 'planet aurora: emission from the planet’s pole', 14, 22, {size: 12, w: 600, color: '#F5F5F7'});
    const Bs = B >= 10 ? Math.round(B).toLocaleString('en-GB') : B.toPrecision(2);
    mxText(c, `B = ${Bs} G → f_ce = ${fce >= 1000 ? (fce / 1000).toPrecision(3) + ' GHz' : fce.toPrecision(3) + ' MHz'}`, 14, 40, {size: 11, mono: true});
    // Dynamic spectrum: time across, frequency up (log, 1 MHz–10 GHz); bursts reach up to f_ce.
    const gx0 = 64, gy0 = sceneH + 26, gw = w - gx0 - 18, gh = h - gy0 - 36;
    mxGlassPanel(c, 10, sceneH + 6, w - 20, h - sceneH - 12);
    mxAxes(c, gx0, gy0, gw, gh, {y: 'FREQUENCY', x: 'TIME (ONE ORBIT)'});
    const Y = f => gy0 + gh - (Math.log10(f) - 0) / 4 * gh;
    for (const [f, lab] of [[1, '1 MHz'], [10, '10 MHz'], [100, '100 MHz'], [1000, '1 GHz'], [10000, '10 GHz']]) mxText(c, lab, gx0 - 6, Y(f) + 4, {size: 11, mono: true, align: 'right'});
    c.fillStyle = 'rgba(100,210,255,.08)'; c.fillRect(gx0, Y(240), gw, Y(10) - Y(240)); mxText(c, 'LOFAR 10–240 MHz', gx0 + gw - 4, Y(240) + 12, {size: 11, align: 'right', color: '#64D2FF'});
    c.fillStyle = 'rgba(191,90,242,.10)'; c.fillRect(gx0, Y(4000), gw, Y(2000) - Y(4000)); mxText(c, 'VLA 2–4 GHz', gx0 + gw - 4, Y(4000) + 12, {size: 11, align: 'right', color: '#BF5AF2'});
    const yc = Y(Math.min(9999, Math.max(1, fce)));
    c.strokeStyle = '#FFD60A'; c.setLineDash([4, 4]); c.beginPath(); c.moveTo(gx0, yc); c.lineTo(gx0 + gw, yc); c.stroke(); c.setLineDash([]);
    mxText(c, 'f_ce', gx0 + 6, yc - 4, {size: 11, mono: true, color: '#FFD60A'});
    // Bursts happen where the cone wall met the observer, at the same orbital phases each orbit (computed from the geometry above).
    c.fillStyle = 'rgba(255,214,10,.85)';
    for (let k = 0; k <= 200; k++){ const tt = k / 200; if (tt > t) break; const aa = -Math.PI / 2 + 0.9 * Math.cos(2 * Math.PI * tt);
      const pxx = sx + orbR * Math.cos(2 * Math.PI * tt), pyy = cy + orbR * 0.32 * Math.sin(2 * Math.PI * tt), s2 = spi ? foot : [pxx, pyy - 9];
      const o2 = Math.atan2(oy - s2[1], ox - s2[0]), d2 = Math.abs(Math.atan2(Math.sin(o2 - aa), Math.cos(o2 - aa)));
      if (Math.abs(d2 - half) < 0.08){ const x = gx0 + tt * gw; c.fillRect(x - 1, yc, 2.5, Math.max(0, Y(Math.max(1, fce / 8)) - yc)); } }
    c.fillStyle = '#F5F5F7'; c.fillRect(gx0 + t * gw - 0.5, gy0, 1, gh);
    st.exag = 'field lines, cone and orbit not to scale; burst times illustrative; cut-off computed';
  }};

MXV.doppler = {key: 0.25, period: 8, init(st){ st.opt.mode = 'los'; st.opt.K = (MX.examples['51 Peg b'] || {}).k || 55.77; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const los = st.opt.mode === 'los', K = st.opt.K, v = K * Math.sin(2 * Math.PI * t);   // + = away
    const cx = w / 2, top = 40, bot = h - 120, ex = cx, ey = h - 92;
    mxEye(c, ex, ey);
    c.strokeStyle = 'rgba(255,255,255,.15)'; c.setLineDash([3, 5]); c.beginPath(); c.moveTo(cx, top); c.lineTo(cx, ey - 12); c.stroke(); c.setLineDash([]);
    mxText(c, 'line of sight', cx + 8, top + 8, {size: 11});
    let sx = cx, sy = (top + bot) / 2;
    if (los) sy = (top + bot) / 2 - Math.cos(2 * Math.PI * t) * (bot - top) * 0.32; else sx = cx + Math.cos(2 * Math.PI * t) * w * 0.3;
    mxStar(c, sx, sy, 18, 5758, t, {flat: true, glow: 1.8});
    const vel = los ? v : 0;
    const col = vel > 0.5 ? '#FF6961' : vel < -0.5 ? '#0A84FF' : '#A1A1A6';
    if (los){ c.strokeStyle = col; c.lineWidth = 2; const L = 26 * Math.sign(-vel) * Math.min(1, Math.abs(vel) / K); c.beginPath(); c.moveTo(sx + 30, sy); c.lineTo(sx + 30, sy + L); c.stroke(); }
    mxText(c, los ? (vel < -0.5 ? 'approaching: blueshift' : vel > 0.5 ? 'receding: redshift' : 'turning') : 'moving across: no Doppler shift', sx + 40, sy + 4, {size: 12, w: 600, color: los ? col : '#C7C7CC'});
    // The shift, exaggerated: true Δλ/λ = v/c.
    const F = 1e5, shift = vel / MX_C * 589 * F;
    mxSpectrum(c, 24, h - 52, w - 48, 22, shift, '');
    mxText(c, `v_r = ${vel >= 0 ? '+' : '−'}${Math.abs(vel).toFixed(1)} m/s   Δλ/λ = ${(vel / MX_C).toExponential(2)}`, 24, h - 66, {size: 12, mono: true, color: '#F5F5F7'});
    st.exag = `line shift ×${F.toLocaleString('en-GB')} (true Δλ/λ ≤ ${(K / MX_C).toExponential(1)}); star colour unchanged`;
    mxText(c, 'K = 51 Peg b’s stored value; motion path illustrative', w - 14, 20, {size: 11, align: 'right'});
  }};

// ---------- the wobble: barycentre, Kepler's equation, the RV curve ----------
const MX_SYS = {
  'jupiter': {name: 'Jupiter–Sun', P: 11.862 * 365.25, mp: 1, ms: 1, e: 0.049, w: 0, a: 5.204, rs: 1, kind: 'mass', inset: true},
  'earth': {name: 'Earth–Sun', P: 365.25, mp: 3.986004e14 / 1.2668653e17, ms: 1, e: 0.0167, w: 0, a: 1, rs: 1, kind: 'mass', inset: true}};
function mxRvSystem(id){
  if (MX_SYS[id]) return MX_SYS[id];
  const p = MX.examples[id] || {};
  const mp = p.mass_sini != null ? p.mass_sini : p.mass, kind = p.mass_sini != null ? 'msini' : 'mass';
  const sini = kind === 'mass' && p.inclination != null ? Math.sin(p.inclination * Math.PI / 180) : 1;
  const a = p.semi_major_axis || Math.cbrt(MX_GM.sun * (p.star_mass || 1) * ((p.orbital_period || 1) * MX_DAY / (2 * Math.PI)) ** 2) / MX_AU;
  return {name: id, P: p.orbital_period, mp, ms: p.star_mass, e: p.eccentricity || 0, w: (p.omega || 0) * Math.PI / 180, a, rs: p.star_radius, kind, sini, Kstored: p.k, teff: p.star_teff};
}
MXV.wobble = {key: 0.3, period: 10, init(st){ st.opt.sys = mxRvSystem('51 Peg b'); mxPrepRv(st); },
  control(st, el){ if (el.tagName === 'SELECT'){ st.opt.sys = mxRvSystem(el.value); mxPrepRv(st); } },
  draw(c, w, h, t, st){
    const S = st.opt.sys, q = st.opt.q, K = st.opt.K;
    // Side by side when there is room; stacked (orbit, then the curve, then the lines) on a narrow screen.
    const narrow = w < 600, side = narrow ? Math.min(w - 20, h * 0.46) : Math.min(w * 0.5, h - 40);
    const ox = narrow ? w / 2 : side / 2 + 14, oy = narrow ? side / 2 + 16 : h / 2 - 6, R = side * 0.36;
    const sc = mxWobbleScale(q, R, S.a, S.rs); st.exag = sc.label;
    const B = mxBodies(t, S.e, q, S.w), pl = [ox + B.planet[0] * R, oy - B.planet[1] * R], sr = [ox + B.star[0] * R * sc.N, oy - B.star[1] * R * sc.N];
    // Orbits: the planet's ellipse and the star's (scaled by N), around the barycentre.
    c.setLineDash([3, 5]); c.strokeStyle = 'rgba(255,255,255,.25)';
    c.beginPath(); for (let i = 0; i <= 120; i++){ const b = mxBodies(i / 120, S.e, q, S.w); const x = ox + b.planet[0] * R, y = oy - b.planet[1] * R; i ? c.lineTo(x, y) : c.moveTo(x, y); } c.stroke();
    c.beginPath(); for (let i = 0; i <= 120; i++){ const b = mxBodies(i / 120, S.e, q, S.w); const x = ox + b.star[0] * R * sc.N, y = oy - b.star[1] * R * sc.N; i ? c.lineTo(x, y) : c.moveTo(x, y); } c.stroke();
    c.setLineDash([]);
    // The line through star, barycentre and planet stays straight.
    c.strokeStyle = 'rgba(255,255,255,.3)'; c.beginPath(); c.moveTo(sr[0], sr[1]); c.lineTo(pl[0], pl[1]); c.stroke();
    mxStar(c, sr[0], sr[1], 11, S.teff || 5772, t, {flat: true, glow: 1.7});
    mxPlanet(c, pl[0], pl[1], 4.5, mxClassOf(null, S.mp) == null ? 4 : mxClassOf(null, S.mp), true);
    c.strokeStyle = '#F5F5F7'; c.lineWidth = 1.2; c.beginPath(); c.moveTo(ox - 5, oy); c.lineTo(ox + 5, oy); c.moveTo(ox, oy - 5); c.lineTo(ox, oy + 5); c.stroke();
    mxText(c, 'barycentre', ox + 8, oy - 8, {size: 11, color: '#F5F5F7'});
    mxEye(c, ox - 20, oy + side / 2 - (narrow ? 10 : -4));
    // Velocity of the star: radial part (toward the observer, down the page) and the dimmed tangential part.
    const dt = 1e-3, B2 = mxBodies((t + dt) % 1, S.e, q, S.w), vx = (B2.star[0] - B.star[0]), vy = (B2.star[1] - B.star[1]);
    const vr = -vy * st.opt.vscale;   // m/s, positive = away (up the page)
    const L = 30 / Math.max(1e-9, st.opt.vmax);
    c.strokeStyle = vr > 0 ? '#FF6961' : '#0A84FF'; c.lineWidth = 2; c.beginPath(); c.moveTo(sr[0], sr[1]); c.lineTo(sr[0], sr[1] + vy * L * 1); c.stroke();
    c.strokeStyle = 'rgba(255,255,255,.25)'; c.beginPath(); c.moveTo(sr[0], sr[1]); c.lineTo(sr[0] + vx * L, sr[1]); c.stroke();
    mxText(c, 'across: invisible to Doppler', 14, narrow ? oy + side / 2 + 4 : h - 14, {size: 11});
    mxText(c, S.name, 14, 20, {size: 13, w: 600, color: '#F5F5F7'});
    mxText(c, `e = ${S.e}${S.e > 0.3 ? ': fastest at periastron' : ''}`, 14, 36, {size: 11});
    if (S.inset){
      // The Sun drawn to scale with the barycentre: Jupiter's lies just outside the surface, Earth's deep inside.
      const ix = narrow ? w - 40 : ox + side / 2 - 40, iy = 46, r0 = 22, off = q * S.a * MX_AU / MX_R.sun * r0;
      c.fillStyle = mxRgb(mxTeffRGB(5772)); c.beginPath(); c.arc(ix, iy, r0, 0, 2 * Math.PI); c.fill();
      c.strokeStyle = '#000'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(ix + off - 4, iy); c.lineTo(ix + off + 4, iy); c.moveTo(ix + off, iy - 4); c.lineTo(ix + off, iy + 4); c.stroke();
      c.strokeStyle = '#F5F5F7'; c.beginPath(); c.moveTo(ix + off - 4, iy); c.lineTo(ix + off + 4, iy); c.moveTo(ix + off, iy - 4); c.lineTo(ix + off, iy + 4); c.stroke();
      mxText(c, 'to scale: barycentre ' + (off > r0 ? 'outside' : 'inside') + ' the Sun', ix, iy + r0 + 14, {size: 11, align: 'center', color: '#C7C7CC'});
    }
    // RV curve, live.
    const gx = narrow ? 52 : side + 52, gy = narrow ? side + 50 : 34, gw = w - gx - 14, gh = narrow ? Math.max(80, h - gy - 110) : (h - 120) * 0.62;
    mxAxes(c, gx, gy, gw, gh, {y: 'RADIAL VELOCITY (m/s)', x: 'ORBITAL PHASE'});
    const Y = v => gy + gh / 2 - v / (K * 1.25) * gh / 2, X = f => gx + f * gw;
    c.strokeStyle = 'rgba(255,255,255,.1)'; c.beginPath(); c.moveTo(gx, Y(0)); c.lineTo(gx + gw, Y(0)); c.stroke();
    for (const v of [K, -K]) mxText(c, (v > 0 ? '+' : '−') + (Math.abs(v) < 1 ? Math.abs(v).toFixed(3) : Math.abs(v).toFixed(1)), gx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'});
    c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
    for (let i = 0; i <= 200; i++){ const f = i / 200, v = st.opt.curve[i]; i ? c.lineTo(X(f), Y(v)) : c.moveTo(X(f), Y(v)); } c.stroke();
    c.fillStyle = vr > 0 ? '#FF6961' : '#0A84FF'; c.beginPath(); c.arc(X(t), Y(vr), 4, 0, 2 * Math.PI); c.fill();
    mxText(c, `K = ${K < 1 ? K.toFixed(3) : K.toFixed(1)} m/s${S.kind === 'msini' ? ' (from m sin i)' : ''}${S.Kstored ? ` · stored ${S.Kstored} m/s` : ''}`, gx + gw, gy - (narrow ? 20 : 6), {size: 11, align: 'right', color: '#C7C7CC', mono: true});
    // Spectral lines shift with the star's velocity (exaggerated, stated).
    const F = Math.pow(10, Math.ceil(Math.log10(8 / (K / MX_C * 589))));
    mxSpectrum(c, gx, h - 58, gw, 20, vr / MX_C * 589 * F, '');
    mxText(c, `lines shifted ×${F.toExponential(0).replace('e+', 'e')} · ${vr > 0 ? 'redshift (away)' : 'blueshift (toward)'}`, gx + gw / 2, h - 25, {size: 11, color: '#C7C7CC', align: 'center'});
  }};
function mxPrepRv(st){
  const S = st.opt.sys, q = S.mp * MX_GM.jup / (S.ms * MX_GM.sun + S.mp * MX_GM.jup);
  st.opt.q = q; st.opt.K = mxK(S.P, S.mp, S.ms, S.e, S.sini == null ? 1 : S.sini);
  // The radial velocity is the star's velocity along the line of sight; its semi-amplitude is K.
  const n = 200, vy = [];
  for (let i = 0; i <= n; i++){ const a = mxBodies(i / n, S.e, q, S.w), b = mxBodies((i / n + 1e-3) % 1, S.e, q, S.w); vy.push(-(b.star[1] - a.star[1])); }
  const amp = (Math.max(...vy) - Math.min(...vy)) / 2, mid = (Math.max(...vy) + Math.min(...vy)) / 2;
  st.opt.vscale = st.opt.K / amp; st.opt.curve = vy.map(v => (v - mid) * st.opt.vscale); st.opt.vmax = amp;
}


// ---------- RV precision: granulation close-up and an Earth twin's signal in the noise ----------
MXV.jitter = {key: 0.4, period: 12, init(st){ st.opt.sig = 1; const rnd = mxRand(9); st.opt.cells = Array.from({length: 70}, () => ({x: rnd(), y: rnd(), r: 0.035 + rnd() * 0.04, ph: rnd() * 6.28}));
  const g = mxRand(21), n = 80; st.opt.noise = Array.from({length: n}, () => { let u = 0, v = 0; while (!u) u = g(); v = g(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }); },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.sig = Number(el.value); },
  draw(c, w, h, t, st){
    const narrow = w < 600, sw = narrow ? w : w * 0.42, sh = narrow ? h * 0.42 : h;
    // Granulation: bright rising cells, dark sinking lanes; markers move with the flow (texture, not to scale).
    c.save(); c.beginPath(); c.rect(0, 0, sw, sh); c.clip();
    c.fillStyle = '#5a3a14'; c.fillRect(0, 0, sw, sh);
    for (const cl of st.opt.cells){ const x = cl.x * sw, y = cl.y * sh, r = cl.r * Math.max(sw, sh) * (1 + 0.12 * Math.sin(t * 12 + cl.ph));
      const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, '#FFE6B0'); g.addColorStop(0.7, '#E8A050'); g.addColorStop(1, 'rgba(90,58,20,0)'); c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill();
      const up = Math.sin(t * 12 + cl.ph) > 0; c.strokeStyle = up ? '#0A84FF' : '#FF453A'; c.lineWidth = 1.4; c.beginPath(); c.moveTo(x - 4, y); c.lineTo(x + 4, y); c.moveTo(x, y - 4); c.lineTo(x, y + 4); c.stroke(); }
    c.restore();
    mxText(c, 'granulation close-up · blue: rising (toward us) · red: sinking', 10, sh - 10, {size: 11, color: '#F5F5F7'});
    // An Earth twin's signal with the chosen per-point noise.
    const K = mxK(365.25, 3.986004e14 / 1.2668653e17, 1, 0, 1), sig = st.opt.sig, n = st.opt.noise.length;
    const gx = narrow ? 50 : sw + 60, gy = narrow ? sh + 40 : 40, gw = w - gx - 16, gh = narrow ? h - gy - 40 : h - 90, lim = Math.max(0.15, 3 * sig);
    const X = f => gx + f * gw, Y = v => gy + gh / 2 - v / lim * gh / 2;
    mxAxes(c, gx, gy, gw, gh, {y: 'RADIAL VELOCITY (m/s)', x: 'TWO YEARS'});
    c.strokeStyle = 'rgba(255,255,255,.12)'; c.beginPath(); c.moveTo(gx, Y(0)); c.lineTo(gx + gw, Y(0)); c.stroke();
    const shown = Math.floor(t * n) + 1;
    c.fillStyle = 'rgba(100,210,255,.85)';
    for (let i = 0; i < shown && i < n; i++){ const f = i / (n - 1), v = K * Math.sin(2 * Math.PI * 2 * f) + sig * st.opt.noise[i]; c.beginPath(); c.arc(X(f), Y(v), 2.6, 0, 2 * Math.PI); c.fill(); }
    c.strokeStyle = '#FFB340'; c.lineWidth = 1.8; c.beginPath(); for (let i = 0; i <= 200; i++){ const f = i / 200; i ? c.lineTo(X(f), Y(K * Math.sin(4 * Math.PI * f))) : c.moveTo(X(f), Y(K * Math.sin(4 * Math.PI * f))); } c.stroke();
    for (const v of [lim, 0, -lim]) mxText(c, (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2), gx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'});
    mxText(c, `RADIAL VELOCITY: K = ${K.toFixed(3)} ± ${sig.toFixed(2)} m/s per point`, gx + 8, gy + 16, {size: 12, mono: true, color: '#F5F5F7'});
    st.exag = 'noise points illustrative (a seeded random draw); granulation texture not to scale';
  }};

// ---------- astrometry ----------
MXV.astrometry = {key: 0.55, period: 14, init(st){ st.opt.mode = 'all'; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, yrs = 6, N = 100;
    const pos = f => { const T = f * yrs, pm = (m === 'all' || m === 'pm') ? [T / yrs * 0.8 - 0.4, T / yrs * 0.3 - 0.15] : [0, 0];
      const pl = (m === 'all' || m === 'plx') ? [0.09 * Math.cos(2 * Math.PI * T), 0.05 * Math.sin(2 * Math.PI * T)] : [0, 0];
      const rf = (m === 'all' || m === 'reflex') ? [0.0003 * N * Math.cos(2 * Math.PI * T / 0.78), 0.0002 * N * Math.sin(2 * Math.PI * T / 0.78)] : [0, 0];
      return [w / 2 + (pm[0] + pl[0] + rf[0]) * w * 0.9, h / 2 - (pm[1] + pl[1] + rf[1]) * h * 1.4]; };
    c.strokeStyle = 'rgba(255,255,255,.07)'; for (let i = 1; i < 8; i++){ c.beginPath(); c.moveTo(i * w / 8, 0); c.lineTo(i * w / 8, h); c.stroke(); c.beginPath(); c.moveTo(0, i * h / 8); c.lineTo(w, i * h / 8); c.stroke(); }
    c.strokeStyle = 'rgba(100,210,255,.85)'; c.lineWidth = 1.4; c.beginPath();
    for (let i = 0; i <= 600; i++){ const f = i / 600; if (f > t) break; const p = pos(f); i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); } c.stroke();
    const p = pos(t); mxStar(c, p[0], p[1], 7, 3500, t, {flat: true, glow: 2.4});
    mxText(c, `year ${(t * yrs).toFixed(1)}`, 14, 20, {size: 12, mono: true, color: '#F5F5F7'});
    mxText(c, 'proper motion and parallax drawn to an illustrative scale', 14, h - 30, {size: 11});
    mxText(c, 'Wobble consistent with an orbiting companion', 14, h - 14, {size: 11, color: '#64D2FF'});
    if (m === 'all' || m === 'reflex') st.exag = `planet wobble ×${N} relative to parallax (GJ 896 Ab: α ≈ 0.5 mas against a parallax of about 160 mas)`;
  }};

// ---------- microlensing ----------
MXV.lens = {key: 0.5, period: 12, draw(c, w, h, t, st){
  const sceneH = h * 0.58, lx = -1.4 + 2.8 * t, u0 = 0.3;
  // A perspective grid dented under the lens and its planet (the source sits far behind).
  const proj = (x, z, y) => { const d = 3.2 + z, s = w * 0.42 / d; return [w / 2 + x * s, sceneH * 0.32 + (1.3 - y) * s * 0.55 + z * 10]; };
  const depth = (x, z) => -0.55 / (1 + ((x - lx) ** 2 + (z - u0) ** 2) / 0.08) - 0.12 / (1 + ((x - lx - 0.35) ** 2 + (z - u0 + 0.05) ** 2) / 0.006);
  c.strokeStyle = 'rgba(100,210,255,.35)'; c.lineWidth = 1;
  for (let i = 0; i <= 18; i++){ const z = -0.4 + i * 0.12; c.beginPath(); for (let j = 0; j <= 60; j++){ const x = -2 + j / 15; const p = proj(x, z, depth(x, z)); j ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); } c.stroke(); }
  for (let j = 0; j <= 24; j++){ const x = -2 + j / 6; c.beginPath(); for (let i = 0; i <= 40; i++){ const z = -0.4 + i * 0.054; const p = proj(x, z, depth(x, z)); i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); } c.stroke(); }
  const L = proj(lx, u0, depth(lx, u0) + 0.08), Pp = proj(lx + 0.35, u0 - 0.05, 0.02);
  mxStar(c, L[0], L[1], 7, 3300, t, {flat: true, glow: 2});
  c.fillStyle = '#C7A27C'; c.beginPath(); c.arc(Pp[0], Pp[1], 2.5, 0, 2 * Math.PI); c.fill();
  mxText(c, w < 600 ? 'lens star (often unseen)' : 'lens star (often unseen) and its planet', L[0] + 12, L[1] - 10, {size: 11});
  const src = [w / 2, 18]; mxStar(c, src[0], src[1], 4, 9000, t, {flat: true, glow: 3});
  mxText(c, 'source star, far behind', src[0] + 10, src[1] + 4, {size: 11});
  const tel = [w / 2, sceneH - 10];
  c.fillStyle = '#C7C7CC'; c.beginPath(); c.moveTo(tel[0] - 10, tel[1]); c.lineTo(tel[0] + 10, tel[1]); c.lineTo(tel[0] + 6, tel[1] - 14); c.lineTo(tel[0] - 6, tel[1] - 14); c.closePath(); c.fill();
  mxText(c, 'telescope', tel[0] + 14, tel[1] - 2, {size: 11});
  // Bent rays from the source past the lens to the telescope (bending exaggerated).
  c.strokeStyle = 'rgba(255,255,255,.35)'; for (const s of [-1, 1]){ c.beginPath(); c.moveTo(src[0], src[1]); c.quadraticCurveTo(L[0] + s * 26, L[1], tel[0], tel[1] - 14); c.stroke(); }
  st.exag = 'ray bending ×1,000,000; grid depth illustrative';
  // The magnification curve A(u), with a schematic planetary spike.
  const gx = 54, gy = sceneH + 24, gw = w - gx - 18, gh = h - gy - 38, tE = 0.5;
  mxGlassPanel(c, 10, sceneH + 4, w - 20, h - sceneH - 10);
  mxAxes(c, gx, gy, gw, gh, {y: 'MAGNIFICATION A', x: 'TIME (Einstein crossing times)'});
  const Af = f => { const u = Math.hypot(u0, (f - 0.5) / tE * 2); return mxPacz(u) + 0.45 * Math.exp(-0.5 * ((f - 0.625) / 0.008) ** 2); };
  const Amax = Af(0.5) + 0.5, X = f => gx + f * gw, Y = A => gy + gh - (A - 1) / (Amax - 1) * gh * 0.92;
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
  for (let i = 0; i <= 400; i++){ const f = i / 400; if (f > t) break; i ? c.lineTo(X(f), Y(Af(f))) : c.moveTo(X(f), Y(Af(f))); } c.stroke();
  for (const A of [1, 2, 3]) if (A < Amax) mxText(c, String(A), gx - 6, Y(A) + 4, {size: 11, mono: true, align: 'right'});
  mxText(c, `u₀ = ${u0}; A(u) = (u² + 2)/(u√(u² + 4))`, gx + 8, gy + 14, {size: 11, mono: true, color: '#C7C7CC'});
  if (t > 0.63) mxText(c, 'planetary spike: schematic', X(0.64) + 6, Y(Af(0.625)) - 4, {size: 11});
  if (w < 600) mxText(c, 'This event will never repeat', gx + 8, gy + 30, {size: 12, w: 600, color: '#F5F5F7'});
  else mxText(c, 'This event will never repeat', gx + gw, gy + 14, {size: 12, w: 600, align: 'right', color: '#F5F5F7'});
}};

// ---------- blocking starlight ----------
MXV.coronagraph = {key: 0.7, period: 16, init(st){ st.opt.mode = 'mask'; const rnd = mxRand(3); st.opt.speckles = Array.from({length: 60}, () => ({a: rnd() * 2 * Math.PI, r: 0.18 + rnd() * 0.5, s: 0.5 + rnd()})); },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.46;
    if (m === 'sun'){
      // An illustration based on SOHO LASCO: an occulting disc, the solar disc outline, streamers.
      for (let i = 0; i < 14; i++){ const a = i / 14 * 2 * Math.PI + t * 0.3 + Math.sin(i * 7) * 0.3, len = R * (0.6 + 0.4 * Math.abs(Math.sin(i * 3.1)));
        const g = c.createLinearGradient(cx, cy, cx + Math.cos(a) * len, cy + Math.sin(a) * len); g.addColorStop(0, 'rgba(255,200,140,.5)'); g.addColorStop(1, 'rgba(255,200,140,0)');
        c.fillStyle = g; c.beginPath(); c.moveTo(cx + Math.cos(a - 0.12) * R * 0.2, cy + Math.sin(a - 0.12) * R * 0.2); c.lineTo(cx + Math.cos(a) * len, cy + Math.sin(a) * len); c.lineTo(cx + Math.cos(a + 0.12) * R * 0.2, cy + Math.sin(a + 0.12) * R * 0.2); c.fill(); }
      const g = c.createRadialGradient(cx, cy, R * 0.2, cx, cy, R); g.addColorStop(0, 'rgba(255,190,120,.5)'); g.addColorStop(1, 'rgba(255,190,120,0)'); c.fillStyle = g; c.beginPath(); c.arc(cx, cy, R, 0, 2 * Math.PI); c.fill();
      c.fillStyle = '#111'; c.beginPath(); c.arc(cx, cy, R * 0.22, 0, 2 * Math.PI); c.fill();
      c.strokeStyle = '#F5F5F7'; c.lineWidth = 1; c.beginPath(); c.arc(cx, cy, R * 0.1, 0, 2 * Math.PI); c.stroke();
      mxText(c, 'Illustration based on SOHO LASCO, not a LASCO image. Real images: SOHO (ESA & NASA).', 14, h - 14, {size: 11});
      mxText(c, 'occulting disc · white circle: the Sun’s disc', 14, 20, {size: 11, color: '#C7C7CC'});
      return;
    }
    if (m === 'shade'){
      const sy = cy, bob = Math.sin(t * 2 * Math.PI) * 3;
      mxStar(c, 40, sy, 14, 5772, t, {flat: true});
      const shx = w * 0.45, sr = Math.min(70, h * 0.22);
      c.fillStyle = 'rgba(0,0,0,.6)'; c.beginPath(); c.moveTo(shx, sy - sr * 0.4 + bob); c.lineTo(w - 50, sy - 10); c.lineTo(w - 50, sy + 10); c.lineTo(shx, sy + sr * 0.4 + bob); c.fill();
      c.save(); c.translate(shx, sy + bob); c.scale(0.18, 1); c.fillStyle = '#C7C7CC';
      c.beginPath(); for (let i = 0; i < 16; i++){ const a0 = i / 16 * 2 * Math.PI, a1 = (i + 0.5) / 16 * 2 * Math.PI; c.lineTo(Math.cos(a0) * sr * 0.45, Math.sin(a0) * sr * 0.45); c.lineTo(Math.cos(a1) * sr, Math.sin(a1) * sr); } c.closePath(); c.fill(); c.restore();
      c.strokeStyle = 'rgba(255,255,255,.25)'; c.beginPath(); c.moveTo(54, sy); c.lineTo(shx, sy - sr * 0.4 + bob); c.moveTo(54, sy); c.lineTo(shx, sy + sr * 0.4 + bob); c.stroke();
      c.strokeStyle = '#64D2FF'; c.beginPath(); c.moveTo(54, sy - 40); c.lineTo(w - 50, sy - 6); c.stroke();
      mxText(c, 'planet light passes the edge', w * 0.62, sy - 38, {size: 11, color: '#64D2FF'});
      c.fillStyle = '#F5F5F7'; c.fillRect(w - 50, sy - 12, 22, 24); mxText(c, 'telescope', w - 39, sy + 30, {size: 11, align: 'center'});
      mxText(c, 'starshade (petals shape the shadow)', shx, sy - sr - 8, {size: 11, align: 'center', color: '#C7C7CC'});
      mxText(c, 'Roman concept: 26 m at 26,000 km · HabEx: 52 m at ≈76,600 km', 14, h - 14, {size: 11});
      st.exag = 'not to scale: true ratio 26 m : 26,000 km = 1 : 10⁶';
      return;
    }
    if (m === 'null'){
      const rot = t * 2 * Math.PI, fr = 26;
      c.save(); c.translate(cx, cy * 0.8); c.rotate(rot);
      for (let x = -w; x < w; x += 2){ const v = Math.sin(Math.PI * x / fr) ** 2; c.fillStyle = `rgba(100,210,255,${0.25 * v})`; c.fillRect(x, -h, 2, 2 * h); }
      c.restore();
      mxStar(c, cx, cy * 0.8, 8, 5772, t, {flat: true, glow: 1.3});
      mxText(c, 'star on the dark fringe', cx + 12, cy * 0.8 - 10, {size: 11});
      const ppx = cx + 70, ppy = cy * 0.8 - 30; c.fillStyle = '#C7A27C'; c.beginPath(); c.arc(ppx, ppy, 3, 0, 2 * Math.PI); c.fill();
      const dx = (ppx - cx) * Math.cos(-rot) - (ppy - cy * 0.8) * Math.sin(-rot), sig = Math.sin(Math.PI * dx / fr) ** 2;
      mxText(c, 'planet', ppx + 8, ppy - 4, {size: 11});
      for (const s of [-1, 1]){ c.fillStyle = '#C7C7CC'; c.beginPath(); c.arc(cx + s * 60, h - 34, 9, 0, 2 * Math.PI); c.fill(); }
      mxText(c, 'two telescopes, combined half a wave apart', cx, h - 12, {size: 11, align: 'center'});
      mxGlassPanel(c, w - 170, 12, 158, 54); mxText(c, 'planet signal', w - 160, 30, {size: 11});
      c.fillStyle = '#64D2FF'; c.fillRect(w - 160, 40, 138 * sig, 10);
      mxText(c, 'Bracewell 1978; LIFE concept', 14, 20, {size: 11, color: '#C7C7CC'});
      st.exag = 'fringe spacing illustrative';
      return;
    }
    // The coronagraph: the mask slides in, the glare collapses to speckles, HR 8799's planets appear.
    const mask = Math.min(1, t / 0.25), clear = Math.max(0, Math.min(1, (t - 0.3) / 0.3));
    const g = c.createRadialGradient(cx, cy, 0, cx, cy, R); g.addColorStop(0, `rgba(255,248,235,${1 - 0.92 * clear})`); g.addColorStop(0.08, `rgba(255,240,215,${0.7 - 0.6 * clear})`); g.addColorStop(1, 'rgba(255,240,215,0)');
    c.fillStyle = g; c.beginPath(); c.arc(cx, cy, R, 0, 2 * Math.PI); c.fill();
    for (let k = 1; k < 7; k++){ c.strokeStyle = `rgba(255,240,220,${(0.2 - 0.17 * clear) / k})`; c.beginPath(); c.arc(cx, cy, R * 0.07 * k, 0, 2 * Math.PI); c.stroke(); }
    for (const s of st.opt.speckles){ const tw = 0.5 + 0.5 * Math.sin(t * 30 + s.a * 9); c.fillStyle = `rgba(255,230,200,${(0.35 - 0.27 * clear) * tw})`; c.beginPath(); c.arc(cx + Math.cos(s.a) * s.r * R, cy + Math.sin(s.a) * s.r * R, 2.2 * s.s, 0, 2 * Math.PI); c.fill(); }
    const mx = cx - (1 - mask) * w * 0.6; c.fillStyle = '#050505'; c.strokeStyle = 'rgba(255,255,255,.35)'; c.beginPath(); c.arc(mx, cy, R * 0.12, 0, 2 * Math.PI); c.fill(); c.stroke();
    c.setLineDash([3, 4]); c.strokeStyle = 'rgba(100,210,255,.6)'; c.beginPath(); c.arc(cx, cy, R * 0.16, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
    mxText(c, 'inner working angle (a few λ/D)', cx, cy - R * 0.16 - 8, {size: 11, color: '#64D2FF', align: 'center'});
    const planets = ['HR 8799 e', 'HR 8799 d', 'HR 8799 c', 'HR 8799 b'].map(n => [n, MX.examples[n]]).filter(p => p[1]);
    const amax = Math.max(...planets.map(p => p[1].semi_major_axis || 1)), ci = Math.cos(25 * Math.PI / 180);
    planets.forEach(([n, p], i) => {
      const a = p.semi_major_axis / amax * R * 0.92, e = p.eccentricity || 0, f = (t * 4 * (amax / p.semi_major_axis) ** 1.5 + i * 0.27) % 1;
      const nu = mxNu(2 * Math.PI * f, e), r = a * (1 - e * e) / (1 + e * Math.cos(nu)), x = cx + r * Math.cos(nu), y = cy + r * Math.sin(nu) * ci;
      c.strokeStyle = `rgba(255,255,255,${0.12 * clear})`; c.beginPath(); c.ellipse(cx - a * e, cy, a, a * Math.sqrt(1 - e * e) * ci, 0, 0, 2 * Math.PI); c.stroke();
      c.fillStyle = `rgba(255,170,120,${clear})`; c.beginPath(); c.arc(x, y, 3.2, 0, 2 * Math.PI); c.fill();
      if (clear > 0.5) mxText(c, n.replace('HR 8799 ', ''), x + 6, y - 4, {size: 11, color: '#F5F5F7'});
    });
    mxText(c, 'HR 8799 (schematic orbits: a and e from exoplanet.eu; orientation illustrative)', 14, h - 14, {size: 11});
    st.exag = 'log brightness stretch; orbital time compressed; planets drawn as dots';
  }};

// ---------- coronagraph families: four optical trains drawn from the functions above ----------
// A log-intensity colour ramp (0 = the stretch's floor, 1 = its top), the same in both themes (the stage is dark).
const MX_HEAT = [[0, [0, 0, 0]], [0.2, [20, 24, 82]], [0.45, [94, 42, 140]], [0.7, [230, 110, 60]], [0.88, [255, 190, 90]], [1, [255, 250, 235]]];
function mxHeat(v){ v = Math.max(0, Math.min(1, v)); for (let i = 1; i < MX_HEAT.length; i++) if (v <= MX_HEAT[i][0]){ const [a, ca] = MX_HEAT[i - 1], [b, cb] = MX_HEAT[i], f = (v - a) / (b - a); return ca.map((x, j) => Math.round(x + f * (cb[j] - x))); } return MX_HEAT[MX_HEAT.length - 1][1]; }
const mxLogV = (I, decades) => 1 + Math.log10(Math.max(I, 1e-30)) / decades;
// A radially symmetric image on an offscreen canvas, cached by key; fn(r, angle) returns [r, g, b].
const MX_IMG = new Map();
function mxRadialImage(key, N, ext, fn){
  if (MX_IMG.has(key)) return MX_IMG.get(key);
  const cv = document.createElement('canvas'); cv.width = cv.height = N;
  const cx = cv.getContext('2d'), im = cx.createImageData(N, N);
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++){
    const x = (i + 0.5) / N * 2 - 1, y = (j + 0.5) / N * 2 - 1, c = fn(Math.hypot(x, y) * ext, Math.atan2(y, x)), o = 4 * (j * N + i);
    im.data[o] = c[0]; im.data[o + 1] = c[1]; im.data[o + 2] = c[2]; im.data[o + 3] = 255;
  }
  cx.putImageData(im, 0, 0);
  if (MX_IMG.size > 80) MX_IMG.clear();
  MX_IMG.set(key, cv); return cv;
}
// Same for a square grid of values (the ADI frames), with its own stretch.
function mxGridImage(vals, G, tone){
  const cv = document.createElement('canvas'); cv.width = cv.height = G;
  const cx = cv.getContext('2d'), im = cx.createImageData(G, G);
  for (let p = 0; p < G * G; p++){ const c = mxHeat(tone(vals[p])); im.data[4 * p] = c[0]; im.data[4 * p + 1] = c[1]; im.data[4 * p + 2] = c[2]; im.data[4 * p + 3] = 255; }
  cx.putImageData(im, 0, 0); return cv;
}
// Text wrapped by words to a width, at most `max` lines (the last one is cut with an ellipsis).
function mxWrap(c, s, x, y, maxW, max, o){
  o = o || {}; c.font = `${o.w || 500} ${o.size || 11}px "Geist",system-ui,sans-serif`;
  const words = String(s).split(' '), lines = []; let cur = '';
  for (const wd of words){ const tr = cur ? cur + ' ' + wd : wd; if (c.measureText(tr).width > maxW && cur){ lines.push(cur); cur = wd; } else cur = tr; }
  if (cur) lines.push(cur);
  if (lines.length > max){ lines.length = max; let l = lines[max - 1]; while (l.length > 1 && c.measureText(l + '…').width > maxW) l = l.slice(0, -1); lines[max - 1] = l + '…'; }
  lines.forEach((l, i) => mxText(c, l, x, y + i * ((o.size || 11) + 3), o));
  return lines.length;
}
// The stage's headline: one line on a wide stage, up to two on a phone.
const mxHead = (c, w, s) => mxWrap(c, s, 14, 22, w - 28, 2, {size: w < 600 ? 11 : 12, w: 600, color: '#F5F5F7'});
// The four scenes: Lyot (mask + stop), an apodised pupil, a vortex phase mask, and AO with ADI.
const MX_CG = {lyotMask: 4, lyotStops: [1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 0.95, 0.9, 0.85, 0.8], up: 8, cp: 1e-3};
function mxCgPanels(w, h){
  const narrow = w < 600, cols = narrow ? 2 : 4, gap = narrow ? 12 : 14, top = narrow ? 62 : 56;
  const s = Math.max(60, Math.min((w - gap * (cols + 1)) / cols, narrow ? h * 0.22 : h * 0.4));
  const rowW = cols * s + (cols - 1) * gap, x0 = (w - rowW) / 2, ps = [];
  for (let i = 0; i < 4; i++){ const r = Math.floor(i / cols), cI = i % cols; ps.push({x: x0 + cI * (s + gap), y: top + r * (s + 52), s}); }
  const bottom = ps[3].y + s + 36;
  return {ps, bottom, narrow};
}
function mxCgFrame(c, p, title, sub, img, on){
  c.save(); c.beginPath(); c.roundRect ? c.roundRect(p.x, p.y, p.s, p.s, 12) : c.rect(p.x, p.y, p.s, p.s); c.clip();
  if (img){ c.imageSmoothingEnabled = true; c.drawImage(img, p.x, p.y, p.s, p.s); }
  c.restore();
  c.strokeStyle = on ? 'rgba(100,210,255,.85)' : 'rgba(255,255,255,.16)'; c.lineWidth = on ? 1.5 : 1;
  c.beginPath(); c.roundRect ? c.roundRect(p.x + .5, p.y + .5, p.s - 1, p.s - 1, 12) : c.rect(p.x + .5, p.y + .5, p.s - 1, p.s - 1); c.stroke();
  mxText(c, title, p.x + 2, p.y - 8, {size: 11, w: 600, color: on ? '#F5F5F7' : '#C7C7CC'});
  if (sub) mxWrap(c, sub, p.x + 2, p.y + p.s + 15, p.s, 2, {size: 11});
}
function mxCgArrows(c, ps, narrow){ if (narrow) return; c.strokeStyle = 'rgba(255,255,255,.3)'; c.fillStyle = 'rgba(255,255,255,.3)';
  for (let i = 0; i < 3; i++){ const a = ps[i], b = ps[i + 1], y = a.y + a.s / 2, x0 = a.x + a.s + 2, x1 = b.x - 2; c.beginPath(); c.moveTo(x0, y); c.lineTo(x1 - 4, y); c.stroke(); c.beginPath(); c.moveTo(x1, y); c.lineTo(x1 - 6, y - 4); c.lineTo(x1 - 6, y + 4); c.fill(); } }
// A log-intensity profile: lines of [u, I] against u (λ/D), from 10⁰ down to 10⁻⁸. The key sits above the plot,
// in as many rows as the width needs, so it never covers a curve.
function mxCgKey(c, x, y0, w, keys){
  c.font = '500 11px "Geist",system-ui,sans-serif';
  const rows = [[]]; let rw = 0;
  keys.forEach(k => { const kw = 26 + c.measureText(k.label).width + 14; if (rw + kw > w && rows[rows.length - 1].length){ rows.push([]); rw = 0; } rows[rows.length - 1].push([k, rw]); rw += kw; });
  rows.forEach((r, i) => r.forEach(([k, dx]) => { const kx = x + dx, ky = y0 + i * 15;
    if (k.planet){ c.fillStyle = '#64D2FF'; c.beginPath(); c.arc(kx + 9, ky - 4, 3.5, 0, 2 * Math.PI); c.fill(); }
    else { c.strokeStyle = k.color; c.lineWidth = 2; c.setLineDash(k.dash || []); c.beginPath(); c.moveTo(kx, ky - 4); c.lineTo(kx + 18, ky - 4); c.stroke(); c.setLineDash([]); }
    mxText(c, k.label, kx + 24, ky, {size: 11}); }));
  return rows.length * 15;
}
function mxCgPlot(c, x, y, w, h, lines, o){
  o = o || {};
  const keys = lines.filter(l => l.label).concat(o.planet ? [{planet: true, label: o.planetLabel || 'planet'}] : []);
  const top = y - 22;
  mxGlassPanel(c, x - 44, top, w + 56, h + 50);
  const kh = mxCgKey(c, x, top + 16, w, keys) + 4;
  y += kh; h -= kh + 14;   // the last 14 px: a row under the tick labels for the axis title and the mask's label
  const umax = o.umax || 12, dec = 8, X = u => x + u / umax * w, Y = I => y + Math.min(1, -Math.log10(Math.max(I, 1e-12)) / dec) * h;
  mxAxes(c, x, y, w, h, {y: 'STARLIGHT, LOG (PEAK = 1)', x: ''});
  mxText(c, 'ANGLE FROM THE STAR (λ/D)', x + w, y + h + 27, {size: 11, w: 600, color: '#8E8E93', mono: true, align: 'right'});
  if (o.mask){ c.fillStyle = 'rgba(255,255,255,.05)'; c.fillRect(x, y, X(o.mask) - x, h); mxText(c, `shaded: ${o.maskLabel || 'behind the mask'}`, x, y + h + 27, {size: 11}); }
  for (const e of [0, 2, 4, 6, 8]){ const yy = Y(Math.pow(10, -e)); c.strokeStyle = 'rgba(255,255,255,.07)'; c.lineWidth = 1; c.beginPath(); c.moveTo(x, yy); c.lineTo(x + w, yy); c.stroke(); mxText(c, e ? `10⁻${'⁰¹²³⁴⁵⁶⁷⁸'[e]}` : '1', x - 6, yy + 4, {size: 11, mono: true, align: 'right'}); }
  for (const u of [0, 4, 8, 12]) if (u <= umax) mxText(c, String(u), X(u), y + h + 13, {size: 11, mono: true, align: 'center'});
  c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip();
  for (const L of lines){ c.strokeStyle = L.color; c.lineWidth = L.width || 1.6; c.setLineDash(L.dash || []); c.beginPath(); L.pts.forEach((p, i) => { const xx = X(p[0]), yy = Y(p[1]); i ? c.lineTo(xx, yy) : c.moveTo(xx, yy); }); c.stroke(); c.setLineDash([]); }
  if (o.planet){ c.fillStyle = '#64D2FF'; c.beginPath(); c.arc(X(o.planet[0]), Y(o.planet[1]), 4, 0, 2 * Math.PI); c.fill(); }
  c.restore();
}
// 1.8×10⁻⁷, for numbers spoken on the stage.
function mxSci(x){ if (!(x > 0)) return '0'; const e = Math.floor(Math.log10(x)), m = x / Math.pow(10, e); return `${m.toFixed(1)}×10${mxSup(e)}`; }
const mxPhase = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
MXV.cgfam = {key: 0.85, period: 14, init(st){ st.opt.mode = 'lyot'; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, L = mxCgPanels(w, h), ps = L.ps, N = L.narrow ? 72 : 96;
    const lw = Math.min(w - 90, 760), lx = (w - lw) / 2 + 30, ly = L.bottom + 22, lh = Math.max(60, h - ly - 40);
    const planetDot = (p, u, pa, I, decades, ext) => { const r = u / ext * p.s / 2, a = pa * Math.PI / 180, v = mxLogV(I, decades); if (v <= 0) return;
      c.fillStyle = mxRgb(mxHeat(v)); c.beginPath(); c.arc(p.x + p.s / 2 + r * Math.cos(a), p.y + p.s / 2 - r * Math.sin(a), Math.max(2, p.s / 2 / ext * 0.6), 0, 2 * Math.PI); c.fill(); };
    if (m === 'adi'){ this.adi(c, w, h, t, st, L, lx, ly, lw, lh); return; }
    const ext = 10, airyImg = mxRadialImage('airy' + N, N, ext, r => mxHeat(mxLogV(mxAiry(r), 6)));
    const pupil = (key, fn) => mxRadialImage(key + N, N, 1.5, r => fn(r));
    // A clear pupil is drawn as a vector disc, so its edge stays sharp at any size.
    const clearPupil = (p, title, sub, on) => { mxCgFrame(c, p, title, sub, null, on); c.fillStyle = 'rgb(235,235,240)'; c.beginPath(); c.arc(p.x + p.s / 2, p.y + p.s / 2, p.s / 3, 0, 2 * Math.PI); c.fill(); };
    if (m === 'apod'){
      // The apodiser's strength steps n = 0 (clear), 1, 2: (1 − ρ²)ⁿ.
      const n = t < 0.3 ? 0 : t < 0.6 ? 1 : 2;
      clearPupil(ps[0], 'Clear pupil', 'transmission 1', n === 0);
      mxCgFrame(c, ps[1], 'Its image', 'the Airy pattern: rings', airyImg, n === 0);
      mxCgFrame(c, ps[2], `Apodised pupil, n = ${n}`, `transmission (1 − ρ²)${n ? '' : '⁰'}${n === 1 ? '¹' : n === 2 ? '²' : ''}`, pupil('apod' + n, r => { const a = r < 1 ? Math.pow(1 - r * r, n) : 0; return [Math.round(235 * a), Math.round(235 * a), Math.round(240 * a)]; }), n > 0);
      mxCgFrame(c, ps[3], 'Its image', n ? 'rings suppressed; core wider' : 'same as clear', mxRadialImage('son' + n + N, N, ext, r => mxHeat(mxLogV(mxSonineI(r, n), 6))), n > 0);
      planetDot(ps[3], 5, 35, 1e-4 / (n + 1) ** 2, 6, ext);
      mxCgArrows(c, ps, L.narrow);
      const pts = (f) => Array.from({length: 241}, (_, i) => [i / 20, f(i / 20)]);
      mxCgPlot(c, lx, ly, lw, lh, [{pts: pts(mxAiry), color: 'rgba(255,255,255,.5)', dash: [4, 4], label: 'clear pupil (Airy)'}, {pts: pts(u => mxSonineI(u, n)), color: '#FFB340', label: `apodised, n = ${n}`}], {planet: [5, 1e-4 / (n + 1) ** 2], planetLabel: 'planet: illustrative 10⁻⁴, dimmed with the star'});
      mxHead(c, w, `throughput 1/(2n + 1) = ${Math.round(100 / (2 * n + 1))}% · peak 1/(n + 1)² = ${Math.round(100 / (n + 1) ** 2)}% of the clear pupil’s`);
      st.exag = 'log intensity stretch (1 to 10⁻⁶); planet at an illustrative 10⁻⁴; ideal monochromatic optics';
      return;
    }
    if (m === 'vortex'){
      // Phase ramp e^{2iθ} winds on, then the stop closes from 150% to 95% of the pupil.
      const wind = mxPhase(t, 0.15, 0.45), s = 1.5 - 0.55 * mxPhase(t, 0.5, 0.7);
      clearPupil(ps[0], 'Entrance pupil', 'the telescope', t < 0.15);
      mxCgFrame(c, ps[1], 'Focal plane: vortex', 'phase ramp, charge 2', airyImg, t >= 0.15 && t < 0.5);
      if (wind > 0){ // the mask's phase, as hue: two full turns around the centre (charge 2)
        const ramp = mxRadialImage('vortexhue' + N, N, ext, (r, a) => { const hh = ((2 * a / (2 * Math.PI)) % 1 + 1) % 1, k = Math.floor(hh * 6), f = hh * 6 - k, q = 1 - f;
          const rgb = [[1, f, 0], [q, 1, 0], [0, 1, f], [0, q, 1], [f, 0, 1], [1, 0, q]][k % 6]; return rgb.map(x => Math.round(60 + 160 * x)); });
        c.save(); c.globalAlpha = 0.45 * wind; c.beginPath(); c.roundRect ? c.roundRect(ps[1].x, ps[1].y, ps[1].s, ps[1].s, 12) : c.rect(ps[1].x, ps[1].y, ps[1].s, ps[1].s); c.clip(); c.drawImage(ramp, ps[1].x, ps[1].y, ps[1].s, ps[1].s); c.restore();
      }
      const lyIn = mxRadialImage('vortexlyot' + N, N, 1.5, r => mxHeat(mxLogV(mxVortexPupil(r) ** 2, 4)));
      const clear = pupil('clearlog', r => mxHeat(r < 1 ? 1 : 0));
      mxCgFrame(c, ps[2], 'Lyot plane', wind < 1 ? 'starlight moving outward' : 'star: all outside the pupil', wind < 0.5 ? clear : lyIn, t >= 0.45 && t < 0.75);
      const stopPx = s / 1.5 * ps[2].s / 2; c.save(); c.beginPath(); c.rect(ps[2].x, ps[2].y, ps[2].s, ps[2].s); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI, true); c.fillStyle = 'rgba(40,40,44,.92)'; c.fill('evenodd'); c.restore();
      c.strokeStyle = '#64D2FF'; c.setLineDash([3, 3]); c.beginPath(); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
      const done = wind >= 1 && s < 1, fin = done ? mxRadialImage('black' + N, N, 1, () => [0, 0, 0]) : airyImg;
      mxCgFrame(c, ps[3], 'Final image', done ? 'star removed (ideal)' : 'star still there', fin, t >= 0.7);
      planetDot(ps[3], 3, 35, MX_CG.cp * Math.min(1, s) ** 4, 6, ext);
      mxCgArrows(c, ps, L.narrow);
      const pts = (f) => Array.from({length: 241}, (_, i) => [i / 20, f(i / 20)]);
      mxCgPlot(c, lx, ly, lw, lh, [{pts: pts(mxAiry), color: 'rgba(255,255,255,.5)', dash: [4, 4], label: 'no coronagraph (Airy)'}, {pts: pts(u => done ? 1e-12 : mxAiry(u)), color: '#FFB340', label: done ? 'vortex: zero (ideal)' : 'vortex not yet working'}], {planet: [3, MX_CG.cp * Math.min(1, s) ** 4], planetLabel: 'planet: illustrative 10⁻³, through the stop'});
      mxHead(c, w, `ideal charge-2 vortex: Lyot-plane field 0 inside the pupil, (1/ρ)² outside · stop ${Math.round(s * 100)}% of the pupil`);
      st.exag = 'log intensity stretch (1 to 10⁻⁶); planet at an illustrative 10⁻³; ideal optics: real vortices leave residuals from aberrations and the star’s size';
      return;
    }
    // Lyot: the occulting mask fades in, then the Lyot stop closes from 150% to 80% of the pupil.
    const T = st.opt.lyot || (st.opt.lyot = mxLyotTable(MX_CG.lyotMask));
    if (!st.opt.lyotFinal){ // the final image's profile for each stop, once
      st.opt.lyotFinal = MX_CG.lyotStops.map(s => ({s, pts: Array.from({length: 121}, (_, i) => [i / 10, mxLyotFinal(T, i / 10, s)])})); }
    const mask = mxPhase(t, 0.15, 0.35), s = 1.5 - 0.7 * mxPhase(t, 0.42, 0.75);
    const F = st.opt.lyotFinal, i1 = F.findIndex(f => f.s <= s), j = Math.max(1, i1 < 0 ? F.length - 1 : i1), A = F[j - 1], B = F[j], f = (A.s - s) / ((A.s - B.s) || 1);
    const now = A.pts.map((p, i) => [p[0], Math.pow(10, (1 - f) * Math.log10(Math.max(p[1], 1e-14)) + f * Math.log10(Math.max(B.pts[i][1], 1e-14)))]);
    const prof = u => { const x = Math.min(119.999, u * 10), i = Math.floor(x), g = x - i; return now[i][1] * (1 - g) + now[i + 1][1] * g; };
    clearPupil(ps[0], 'Entrance pupil', 'the telescope', t < 0.15);
    mxCgFrame(c, ps[1], 'Focal plane + mask', `occulting disc, ${MX_CG.lyotMask} λ/D`, airyImg, t >= 0.15 && t < 0.42);
    planetDot(ps[1], MX_CG.up, 35, MX_CG.cp, 6, ext);
    if (mask > 0){ const mr = MX_CG.lyotMask / ext * ps[1].s / 2; c.fillStyle = `rgba(8,8,10,${mask})`; c.beginPath(); c.arc(ps[1].x + ps[1].s / 2, ps[1].y + ps[1].s / 2, mr, 0, 2 * Math.PI); c.fill(); c.strokeStyle = `rgba(255,255,255,${0.5 * mask})`; c.stroke(); }
    const lyotImg = mxRadialImage('lyotplane' + N, N, 1.5, r => { const i = r < 1 ? Math.min(T.A.length - 1, Math.round(r * 300)) : Math.min(T.B.length - 1, Math.round((r - 1) * 200)); const e = r < 1 ? T.A[i][1] : r <= 1.5 ? T.B[i][1] : 0; return mxHeat(mxLogV(e * e, 4)); });
    const clearLog = pupil('clearlog', r => mxHeat(r < 1 ? 1 : 0));
    mxCgFrame(c, ps[2], 'Lyot plane + stop', mask < 1 ? 'the pupil again' : 'bright rim: light the mask diffracted', mask < 0.5 ? clearLog : lyotImg, t >= 0.42 && t < 0.75);
    const stopPx = s / 1.5 * ps[2].s / 2; c.save(); c.beginPath(); c.rect(ps[2].x, ps[2].y, ps[2].s, ps[2].s); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI, true); c.fillStyle = 'rgba(40,40,44,.92)'; c.fill('evenodd'); c.restore();
    c.strokeStyle = '#64D2FF'; c.setLineDash([3, 3]); c.beginPath(); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
    const sKey = 'lyotfinal' + N + '_' + Math.round(s * 40) + '_' + (mask >= 1 ? 1 : 0);
    const finImg = mask < 1 ? airyImg : mxRadialImage(sKey, N, ext, r => mxHeat(mxLogV(prof(r), 6)));
    mxCgFrame(c, ps[3], 'Final image', mask < 1 ? 'no mask yet: the full star' : `stop ${Math.round(s * 100)}% of the pupil`, finImg, t >= 0.75);
    planetDot(ps[3], MX_CG.up, 35, MX_CG.cp * Math.min(1, s) ** 4, 6, ext);
    mxCgArrows(c, ps, L.narrow);
    const lines = [{pts: Array.from({length: 241}, (_, i) => [i / 20, mxAiry(i / 20)]), color: 'rgba(255,255,255,.5)', dash: [4, 4], label: 'no coronagraph (Airy)'}];
    if (mask >= 1) lines.push({pts: now, color: '#FFB340', label: `Lyot, stop ${Math.round(s * 100)}%`});
    mxCgPlot(c, lx, ly, lw, lh, lines, {mask: MX_CG.lyotMask, planet: [MX_CG.up, MX_CG.cp * Math.min(1, s) ** 4], planetLabel: 'planet: illustrative 10⁻³, through the stop'});
    const at8 = prof(MX_CG.up), air8 = mxAiry(MX_CG.up);
    mxHead(c, w, mask < 1 ? 'the star’s image, rings and all' : `starlight at ${MX_CG.up} λ/D: ${mxSci(at8)} of the star’s peak (no coronagraph: ${mxSci(air8)})`);
    st.exag = 'log intensity stretch (1 to 10⁻⁶); planet at an illustrative 10⁻³; ideal monochromatic optics; mask and stop sizes illustrative';
  },
  adi(c, w, h, t, st, L, lx, ly, lw, lh){
    const A = st.opt.adi || (st.opt.adi = mxAdi(17)), ps = L.ps, G = A.G;
    const ao = mxPhase(t, 0.02, 0.18), k = Math.max(0, Math.min(A.N - 1, Math.floor(mxPhase(t, 0.22, 0.97) * A.N)));
    const smax = Math.max(...A.med);
    const logTone = v => mxLogV(Math.max(v, 1e-6) / smax, 3);
    // AO: a seeing halo (no correction) blends into the corrected frame (core under the mask, speckles).
    const key = 'ao' + Math.round(ao * 10);
    if (!st.opt.aoImg || st.opt.aoKey !== key){
      const F0 = A.frames[0], mix = new Float32Array(G * G), sd = 11;
      for (let j = 0; j < G; j++) for (let i = 0; i < G; i++){ const r2 = (i - A.c0) ** 2 + (j - A.c0) ** 2; mix[j * G + i] = (1 - ao) * 1.6 * smax * Math.exp(-r2 / (2 * sd * sd)) + ao * F0[j * G + i]; }
      st.opt.aoImg = mxGridImage(mix, G, logTone); st.opt.aoKey = key; }
    if (st.opt.adiK !== k){ st.opt.adiK = k;
      st.opt.frameImg = mxGridImage(A.frames[k], G, logTone);
      const top = Math.max(1e-6, A.Ap * 0.8); st.opt.stackImg = mxGridImage(A.stacks[k], G, v => Math.max(0, v) / top * 0.9); }
    if (!st.opt.medImg) st.opt.medImg = mxGridImage(A.med, G, logTone);
    mxCgFrame(c, ps[0], ao < 1 ? 'Adaptive optics: on' : 'AO on', ao < 1 ? 'deformable mirror switching on' : 'core and speckles, λ/D wide', st.opt.aoImg, t < 0.22);
    mxCgFrame(c, ps[1], `Frame ${k + 1} of ${A.N}`, `field rotation ${A.ang[k].toFixed(0)}°`, st.opt.frameImg, t >= 0.22);
    mxCgFrame(c, ps[2], 'Median of the frames', 'speckles only: the model', st.opt.medImg, t >= 0.22);
    mxCgFrame(c, ps[3], `Stack of ${k + 1}`, 'frame − median, turned back', st.opt.stackImg, t >= 0.22);
    // The planet's track on the raw frame (it turns with the sky) and its place in the stack.
    const sc = ps[1].s / G, a0 = (A.o.pa + A.ang[k]) * Math.PI / 180;
    c.strokeStyle = 'rgba(100,210,255,.6)'; c.setLineDash([2, 3]); c.beginPath(); c.arc(ps[1].x + (A.c0 + .5) * sc, ps[1].y + (A.c0 + .5) * sc, A.o.rp * sc, A.o.pa * Math.PI / 180, a0); c.stroke(); c.setLineDash([]);
    if (t >= 0.22){ const r = A.o.rp * sc; c.strokeStyle = '#64D2FF'; c.beginPath(); c.arc(ps[1].x + (A.c0 + .5) * sc + r * Math.cos(a0), ps[1].y + (A.c0 + .5) * sc + r * Math.sin(a0), 3 * A.sig * sc + 3, 0, 2 * Math.PI); c.stroke(); }
    if (k >= 4){ c.strokeStyle = '#64D2FF'; c.beginPath(); c.arc(ps[3].x + (A.px + .5) * sc, ps[3].y + (A.py + .5) * sc, 3 * A.sig * sc + 3, 0, 2 * Math.PI); c.stroke(); }
    mxCgArrows(c, ps, L.narrow);
    // Signal-to-noise against frames stacked.
    mxGlassPanel(c, lx - 44, ly - 22, lw + 56, lh + 50);
    const kh = mxCgKey(c, lx, ly - 6, lw, [{label: 'stack of the first n frames', color: '#FFB340'}, {label: `one raw frame: S/N ${A.snrRaw.toFixed(1)}`, color: 'rgba(255,255,255,.6)', dash: [4, 4]}]);
    ly += kh + 14; lh -= kh + 14;
    mxAxes(c, lx, ly, lw, lh, {y: 'PLANET SIGNAL-TO-NOISE', x: 'FRAMES STACKED'});
    const smaxN = Math.max(...A.snr, A.snrRaw, 5) * 1.1, X = i => lx + (i + 0.5) / A.N * lw, Y = v => ly + lh - Math.max(0, v) / smaxN * lh;
    for (const v of [0, 5, 10, 15, 20, 25]) if (v < smaxN){ c.strokeStyle = 'rgba(255,255,255,.07)'; c.lineWidth = 1; c.beginPath(); c.moveTo(lx, Y(v)); c.lineTo(lx + lw, Y(v)); c.stroke(); mxText(c, String(v), lx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
    for (const i of [0, 11, 23]) mxText(c, String(i + 1), X(i), ly + lh + 13, {size: 11, mono: true, align: 'center'});
    for (let i = 0; i <= k; i++){ c.fillStyle = i === k ? '#FFB340' : 'rgba(255,179,64,.45)'; const bw = Math.max(2, lw / A.N - 3); c.fillRect(X(i) - bw / 2, Y(A.snr[i]), bw, ly + lh - Y(A.snr[i])); }
    c.strokeStyle = 'rgba(255,255,255,.5)'; c.setLineDash([4, 4]); c.beginPath(); c.moveTo(lx, Y(A.snrRaw)); c.lineTo(lx + lw, Y(A.snrRaw)); c.stroke(); c.setLineDash([]);
    mxHead(c, w, `speckles stay, the planet turns · stack of ${k + 1}: S/N ${A.snr[k].toFixed(1)}`);
    st.exag = 'synthetic frames: speckle pattern, noise and planet brightness illustrative; log stretch on the raw frames';
  }};

// ---------- reading atmospheres: transmission ----------
const MX_RAMP = [[0.6, '#3B2A8C'], [1.2, '#2E6BFF'], [2.0, '#22C1E6'], [2.8, '#3EDB62'], [3.6, '#F2E43A'], [4.4, '#FF9F2E'], [5.0, '#E0302F']];
MXV.transmission = {key: 0.5, period: 12, draw(c, w, h, t, st){
  const sceneH = h * 0.5, sx = w * 0.18, sy = sceneH / 2, SR = sceneH * 0.9;
  mxStar(c, sx - SR * 0.45, sy, SR * 0.62, 5400, t, {flat: true, glow: 1.25});
  // The planet crosses the star's limb; its atmosphere annulus is drawn ten times too thick.
  const pxp = sx - SR * 0.45 + (t * 2.2 - 0.6) * SR * 0.8, py = sy, pr = sceneH * 0.16;
  const over = Math.max(0, Math.min(1, 1 - Math.abs(pxp - (sx - SR * 0.45)) / (SR * 0.62 + pr)));
  c.fillStyle = 'rgba(120,170,214,.25)'; c.beginPath(); c.arc(pxp, py, pr * 1.18, 0, 2 * Math.PI); c.fill();
  mxPlanet(c, pxp, py, pr, 4, false);
  c.strokeStyle = 'rgba(255,240,200,.35)'; c.lineWidth = 1;
  for (let i = -3; i <= 3; i++){ const yy = py + i * pr * 0.35; if (Math.abs(i) < 3) continue; c.beginPath(); c.moveTo(pxp, yy); c.lineTo(w - 20, yy * 0.98 + sy * 0.02); c.stroke(); }
  for (const s of [-1, 1]){ c.beginPath(); c.moveTo(pxp, py + s * pr * 1.09); c.lineTo(w - 20, py + s * pr * 0.6); c.stroke(); }
  mxText(c, 'starlight through the limb', w - 20, sy - pr - 10, {size: 11, align: 'right'});
  st.exag = 'atmosphere drawn ×10 thicker; planet and star not to scale';
  // Two spectrum bars in false colour, 0.6–5 µm, with the real band positions.
  const L0 = 0.5, L1 = 5.1, bx = 24, bw = w - 48, X = l => bx + (l - L0) / (L1 - L0) * bw;
  const bar = (y, label, absorb) => {
    const g = c.createLinearGradient(bx, 0, bx + bw, 0); for (const [l, col] of MX_RAMP) g.addColorStop(Math.max(0, Math.min(1, (l - L0) / (L1 - L0))), col);
    c.fillStyle = g; c.fillRect(bx, y, bw, 36);
    if (absorb > 0) for (const [mol, l] of MX.bands){ const wd = mol === 'Na' || mol === 'K' ? 2 : 7; c.fillStyle = `rgba(0,0,0,${0.85 * absorb})`; c.fillRect(X(l) - wd / 2, y, wd, 36); }
    mxText(c, label, bx, y - 6, {size: 11, w: 600, color: '#C7C7CC', mono: true});
  };
  const y1 = sceneH + 30, y2 = y1 + 70;
  bar(y1, 'STARLIGHT ONLY', 0);
  bar(y2, 'DURING TRANSIT', over);
  let last = -1;
  for (const [mol, l] of MX.bands){ const x = X(l); if (x - last < 24) continue; last = x; mxText(c, mol, x, y2 + 54, {size: 11, align: 'center', color: '#F5F5F7'}); }
  for (const l of [1, 2, 3, 4, 5]) mxText(c, l + ' µm', X(l), y2 + 72, {size: 11, mono: true, align: 'center'});
  mxText(c, 'false colour: infrared is invisible to the eye · schematic, band positions real', bx, h - 8, {size: 11});
}};

// ---------- a real spectrum and the Atmosphere Lab ----------
function mxAtm(lam, base, dH, S){ let v = base; for (const m in S) for (const [c, w] of MX.lab_bands[m]) v += S[m] * dH * Math.exp(-0.5 * ((lam - c) / w) ** 2); return v; }
function mxSpecChart(c, w, h, o){
  // A depth-against-wavelength chart, 0.5–5.4 µm, with the band positions marked along the bottom.
  const L0 = 0.5, L1 = 5.4, gx = 64, gy = 34, gw = w - gx - 16, gh = h - gy - 58;
  const X = l => gx + (l - L0) / (L1 - L0) * gw, Y = v => gy + gh - (v - o.lo) / (o.hi - o.lo) * gh;
  mxAxes(c, gx, gy, gw, gh, {y: 'TRANSIT DEPTH (ppm)', x: 'WAVELENGTH (µm)'});
  for (let k = 0; k <= 4; k++){ const v = o.lo + (o.hi - o.lo) * k / 4; c.strokeStyle = 'rgba(255,255,255,.06)'; c.beginPath(); c.moveTo(gx, Y(v)); c.lineTo(gx + gw, Y(v)); c.stroke(); mxText(c, Math.round(v).toLocaleString('en-GB'), gx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
  for (const l of [1, 2, 3, 4, 5]) mxText(c, l + ' µm', X(l), gy + gh + 14, {size: 11, mono: true, align: 'center'});
  let last = -1; for (const [mol, l] of MX.bands){ const x = X(l); c.strokeStyle = 'rgba(255,255,255,.12)'; c.setLineDash([2, 4]); c.beginPath(); c.moveTo(x, gy); c.lineTo(x, gy + gh); c.stroke(); c.setLineDash([]); if (x - last < 26) continue; last = x; mxText(c, mol, x, gy + gh + 30, {size: 11, align: 'center', color: '#C7C7CC'}); }
  return {X, Y, gx, gy, gw, gh};
}
function mxJwstPoints(c, A, J){
  c.strokeStyle = 'rgba(100,210,255,.8)'; c.fillStyle = '#64D2FF'; c.lineWidth = 1;
  for (const [l, lo, hi, d, e] of J.points){ const x = A.X(l), y = A.Y(d);
    c.beginPath(); c.moveTo(x, A.Y(d - e)); c.lineTo(x, A.Y(d + e)); c.moveTo(A.X(lo), y); c.lineTo(A.X(hi), y); c.stroke();
    c.beginPath(); c.arc(x, y, 2.6, 0, 2 * Math.PI); c.fill(); }
}
MXV.jwst = {key: 0, period: 1, draw(c, w, h, t, st){
  const J = MX.jwst; if (!J) return;
  const ds = J.points.map(p => p[3]), lo = Math.min(...ds) - 400, hi = Math.max(...ds) + 400;
  const A = mxSpecChart(c, w, h, {lo, hi});
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.4; c.beginPath(); let on = false;
  for (const [l, d] of J.model){ if (l < 0.5 || l > 5.4) continue; on ? c.lineTo(A.X(l), A.Y(d)) : c.moveTo(A.X(l), A.Y(d)); on = true; } c.stroke();
  mxJwstPoints(c, A, J);
  const cap = `dots: JWST NIRSpec PRISM, ${J.licence} · line: the paper's best-fit model`;
  mxText(c, 'WASP-39 b', A.gx + 8, A.gy + 16, {size: 13, w: 600, color: '#F5F5F7'});
  if (w < 600) mxText(c, cap, A.gx + 8, A.gy + 32, {size: 11}); else mxText(c, cap, A.gx + A.gw, A.gy - 6, {size: 11, align: 'right'});
}};
MXV.atmlab = {key: 0, period: 1, init(st){
  const w = MX.examples['WASP-39 b'] || {};
  st.opt.lab = {mols: {H2O: 1, CO2: 1, Na: 1, K: 1}, n: 2, T: 1116, mu: 2.3, real: false, p: w};
}, control(st, el){
  const L = st.opt.lab;
  if (el.dataset.mol){ const on = el.getAttribute('aria-pressed') === 'true'; if (on) L.mols[el.dataset.mol] = 1; else delete L.mols[el.dataset.mol]; }
  else if (el.dataset.ctl === 'real') L.real = el.getAttribute('aria-pressed') === 'true';
  else if (el.dataset.ctl === 'n') L.n = Number(el.value) / 10;
  else if (el.dataset.ctl === 'T') L.T = Number(el.value);
  else if (el.dataset.ctl === 'mu') L.mu = Number(el.value);
}, draw(c, w, h, t, st){
  const L = st.opt.lab, p = L.p, kB = 1.380649e-23, mH = 1.6735575e-27;
  const g = p.mass * MX_GM.jup / (p.radius * MX_R.jup) ** 2, H = kB * L.T / (L.mu * mH * g), Rp = p.radius * MX_R.jup, Rs = p.star_radius * MX_R.sun;
  const dH = 2 * H * Rp / (Rs * Rs) * 1e6, base = (Rp / Rs) ** 2 * 1e6, S = {};
  for (const m in L.mols) S[m] = L.n;
  const vals = []; for (let i = 0; i <= 500; i++){ const l = 0.5 + 4.9 * i / 500; vals.push([l, mxAtm(l, base, dH, S)]); }
  let lo = base - 200, hi = Math.max(...vals.map(v => v[1])) + 300;
  if (L.real && MX.jwst){ const ds = MX.jwst.points.map(q => q[3]); lo = Math.min(lo, Math.min(...ds) - 300); hi = Math.max(hi, Math.max(...ds) + 300); }
  const A = mxSpecChart(c, w, h, {lo, hi});
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.8; c.beginPath(); vals.forEach(([l, v], i) => i ? c.lineTo(A.X(l), A.Y(v)) : c.moveTo(A.X(l), A.Y(v))); c.stroke();
  if (L.real && MX.jwst) mxJwstPoints(c, A, MX.jwst);
  const narrow = w < 600;
  mxText(c, `H = ${Math.round(H / 1000).toLocaleString('en-GB')} km · 1 H = ${Math.round(dH)} ppm` + (narrow ? '' : ` · baseline (Rp/R★)² = ${Math.round(base).toLocaleString('en-GB')} ppm`), A.gx + 8, A.gy + 16, {size: 11, mono: true, color: '#F5F5F7'});
  const cap = L.real ? 'line: model (toy) · dots: JWST data, cited' : 'line: model (toy), not data';
  if (narrow) mxText(c, cap, A.gx + 8, A.gy + 32, {size: 11}); else mxText(c, cap, A.gx + A.gw, A.gy - 6, {size: 11, align: 'right'});
}};


// ---------- timing and phase ----------
MXV.timing = {key: 0.35, period: 14, init(st){ st.opt.mode = 'ttv'; st.opt.lam = 0; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; if (el.type === 'range') st.opt.lam = Number(el.value); },
  draw(c, w, h, t, st){
    const m = st.opt.mode, sceneH = h * 0.5, cx = w * 0.3, cy = sceneH / 2 + 10;
    const gx = 56, gy = sceneH + 30, gw = w - gx - 18, gh = h - gy - 36;
    mxGlassPanel(c, 10, sceneH + 8, w - 20, h - sceneH - 14);
    if (m === 'ttv'){
      // Two planets near 2:1: the inner one's transits drift early and late (amplitude illustrative).
      const P1 = 1, P2 = 2.1, T = t * 24, r1 = sceneH * 0.22, r2 = sceneH * 0.35;
      mxStar(c, cx, cy, 14, 5774, t, {flat: true});
      for (const [r, P] of [[r1, P1], [r2, P2]]){ c.strokeStyle = 'rgba(255,255,255,.2)'; c.setLineDash([3, 5]); c.beginPath(); c.ellipse(cx, cy, r, r * 0.35, 0, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
        const a = 2 * Math.PI * T / P; mxPlanet(c, cx + r * Math.sin(a), cy + r * 0.35 * Math.cos(a), 4, 4, true); }
      c.strokeStyle = 'rgba(100,210,255,.5)'; c.beginPath(); c.moveTo(cx, cy + 20); c.lineTo(cx, sceneH); c.stroke(); mxText(c, 'to observer', cx + 6, sceneH - 4, {size: 11});
      const sup = 1 / Math.abs(2 / P2 - 1 / P1), n = Math.floor(T / P1);
      mxAxes(c, gx, gy, gw, gh, {y: 'O − C (illustrative)', x: 'TRANSIT NUMBER'});
      c.fillStyle = '#FFB340';
      for (let k = 0; k <= Math.min(n, 23); k++){ const v = Math.sin(2 * Math.PI * k * P1 / sup); c.beginPath(); c.arc(gx + (k + 0.5) / 24 * gw, gy + gh / 2 - v * gh * 0.38, 3.5, 0, 2 * Math.PI); c.fill(); }
      c.strokeStyle = 'rgba(255,255,255,.12)'; c.beginPath(); c.moveTo(gx, gy + gh / 2); c.lineTo(gx + gw, gy + gh / 2); c.stroke();
      mxText(c, 'early / late against a strict period; Kepler-9: minutes per orbit (Holman et al. 2010)', gx + 6, gy + 14, {size: 11});
      st.exag = 'O−C amplitude illustrative; orbits not to scale';
    } else if (m === 'eclipse' || m === 'phase'){
      // One orbit: transit at phase 0, secondary eclipse at 0.5; the planet's own light rises toward occultation.
      const ph = t, a = 2 * Math.PI * ph, R = sceneH * 0.36, px = cx + R * Math.sin(a), py = cy + R * 0.3 * Math.cos(a), front = Math.cos(a) > 0;
      if (!front) mxPlanet(c, px, py, 7, 4, true);
      mxStar(c, cx, cy, 22, 4900, t, {flat: true});
      if (front) mxPlanet(c, px, py, 7, 4, Math.abs(px - cx) > 29);
      // Day side facing the star: show it as the lit hemisphere seen from the observer.
      const off = m === 'phase' ? 16 * Math.PI / 180 : 0;
      const F = f => { const A = 2 * Math.PI * f; let v = 0.5 * (1 - Math.cos(A - off)) * 0.25;            // planet light (fraction of day side)
        const z = Math.abs(Math.sin(A)) * 8;
        if (Math.cos(A) > 0 && z < 1.15) v -= 1;                     // transit (drawn to the panel scale)
        if (Math.cos(A) < 0 && z < 1.15) v -= 0.5 * (1 - Math.cos(A - off)) * 0.25;   // occultation hides the planet's light
        return v; };
      mxAxes(c, gx, gy, gw, gh, {y: m === 'phase' ? 'BRIGHTNESS (planet light ×10)' : 'BRIGHTNESS (secondary ×10)', x: 'ORBITAL PHASE'});
      const Y = v => gy + gh * 0.25 - v * gh * 0.6;
      c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
      for (let i = 0; i <= 400; i++){ const f = i / 400 - 0.25; const x = gx + i / 400 * gw; i ? c.lineTo(x, Y(F(f))) : c.moveTo(x, Y(F(f))); } c.stroke();
      c.fillStyle = '#FFB340'; const fx = ((ph + 0.25) % 1); c.beginPath(); c.arc(gx + fx * gw, Y(F(ph)), 3.5, 0, 2 * Math.PI); c.fill();
      mxText(c, 'transit', gx + 0.25 * gw, gy + gh - 6, {size: 11, align: 'center'}); mxText(c, 'occultation', gx + 0.75 * gw, gy + gh - 6, {size: 11, align: 'center'});
      if (m === 'phase') mxText(c, 'peak shifted by winds (HD 189733 b: 16° before occultation)', gx + 6, gy + 14, {size: 11});
      st.exag = m === 'phase' ? 'planet light drawn ×10 against the transit; offset 16° as measured' : 'secondary eclipse drawn ×10 deeper than true; transit depth not to scale';
    } else {
      // Rossiter–McLaughlin: the star's disc coloured by its rotation (a velocity map), the planet crossing at λ.
      const R = sceneH * 0.38, lam = st.opt.lam * Math.PI / 180;
      for (let x = -R; x <= R; x += 2){ const v = x / R, hc = Math.sqrt(Math.max(0, R * R - x * x)); c.fillStyle = v < 0 ? `rgba(10,132,255,${0.25 + 0.6 * -v})` : `rgba(255,105,97,${0.25 + 0.6 * v})`; c.fillRect(cx + x, cy - hc, 2, 2 * hc); }
      mxText(c, 'approaching', cx - R, cy + R + 14, {size: 11, color: '#64D2FF'}); mxText(c, 'receding', cx + R, cy + R + 14, {size: 11, color: '#FF6961', align: 'right'});
      const b = 0.3, path = f => { const u = -1.3 + 2.6 * f; return [u * Math.cos(lam) - b * Math.sin(lam), u * Math.sin(lam) + b * Math.cos(lam)]; };
      const [ux, uy] = path(t); c.fillStyle = '#111'; c.beginPath(); c.arc(cx + ux * R, cy + uy * R, R * 0.13, 0, 2 * Math.PI); c.fill();
      c.setLineDash([3, 4]); c.strokeStyle = 'rgba(255,255,255,.4)'; c.beginPath(); const p0 = path(0), p1 = path(1); c.moveTo(cx + p0[0] * R, cy + p0[1] * R); c.lineTo(cx + p1[0] * R, cy + p1[1] * R); c.stroke(); c.setLineDash([]);
      mxText(c, `λ = ${st.opt.lam}°`, 14, 22, {size: 13, w: 600, color: '#F5F5F7'});
      // Anomaly: minus the blocked light's velocity (velocity ∝ x on the disc), only while on the disc.
      const anom = f => { const [x, y] = path(f); return x * x + y * y < 1 ? -x : 0; };
      mxAxes(c, gx, gy, gw, gh, {y: 'RV ANOMALY (shape)', x: 'TIME THROUGH TRANSIT'});
      c.strokeStyle = 'rgba(255,255,255,.12)'; c.beginPath(); c.moveTo(gx, gy + gh / 2); c.lineTo(gx + gw, gy + gh / 2); c.stroke();
      c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
      for (let i = 0; i <= 300; i++){ const f = i / 300, y = gy + gh / 2 - anom(f) * gh * 0.4; i ? c.lineTo(gx + f * gw, y) : c.moveTo(gx + f * gw, y); } c.stroke();
      c.fillStyle = '#FFB340'; c.beginPath(); c.arc(gx + t * gw, gy + gh / 2 - anom(t) * gh * 0.4, 3.5, 0, 2 * Math.PI); c.fill();
      mxText(c, 'amplitude ≈ V sin I · k²: tens of m/s for hot Jupiters', gx + 6, gy + 14, {size: 11});
      st.exag = 'colour = velocity map, not a colour change; planet drawn larger';
    }
  }};

// ---------- false positives ----------
MXV.falsepos = {key: 0.5, period: 10, init(st){ st.opt.mode = 'eb'; }, control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, narrow = w < 600, px = narrow ? Math.min(w - 40, 200) : Math.min(w * 0.36, h - 120);
    const ox = narrow ? (w - px) / 2 : 24, oy = narrow ? 34 : 50, cell = px / 5;
    // A 5×5 patch of TESS pixels (21″ each), drawn to scale with the stars on it.
    c.strokeStyle = 'rgba(255,255,255,.18)';
    for (let i = 0; i <= 5; i++){ c.beginPath(); c.moveTo(ox + i * cell, oy); c.lineTo(ox + i * cell, oy + px); c.stroke(); c.beginPath(); c.moveTo(ox, oy + i * cell); c.lineTo(ox + px, oy + i * cell); c.stroke(); }
    c.strokeStyle = '#FFB340'; c.strokeRect(ox + cell, oy + cell, 3 * cell, 3 * cell);
    mxText(c, 'TESS pixels, 21″ each · aperture in amber', ox, oy - 8, {size: 11});
    const tx = ox + px / 2, ty = oy + px / 2;
    mxStar(c, tx, ty, 9, 5800, t, {flat: true, glow: 1.6}); mxText(c, 'target', tx + 12, ty - 10, {size: 11, color: '#F5F5F7'});
    const nb = m === 'beb' ? [tx + cell * 1.1, ty - cell * 0.8] : m === 'heb' ? [tx + cell * 0.12, ty + cell * 0.08] : null;
    if (nb){ mxStar(c, nb[0], nb[1], m === 'heb' ? 4 : 3.5, 3800, t, {flat: true, glow: 1.8}); mxText(c, m === 'heb' ? 'bound eclipsing pair, unresolved' : 'faint background binary', nb[0] + 8, nb[1] - 6, {size: 11}); }
    // The light curve each scenario makes.
    const gx = narrow ? 50 : ox + px + 60, gy = narrow ? oy + px + 40 : 50, gw = w - gx - 18, gh = narrow ? h - gy - 40 : h - 110;
    const shape = (f, kind) => {
      const x = f - 0.5;
      if (kind === 'eb') return Math.abs(x) < 0.06 ? 1 - 0.8 * (1 - Math.abs(x) / 0.06) : (Math.abs(Math.abs(x) - 0.5) < 0.06 ? 1 - 0.3 * (1 - Math.abs(Math.abs(x) - 0.5) / 0.06) : 1);
      if (kind === 'beb' || kind === 'heb') return Math.abs(x) < 0.05 ? 1 - 0.5 * 0.002 * (1 - Math.abs(x) / 0.05) * 6 : 1;
      if (kind === 'oddeven') { const k = Math.round(f * 4); const d = k % 2 ? 0.6 : 0.4; return Math.abs(f * 4 - k) < 0.08 ? 1 - d * (1 - Math.abs(f * 4 - k) / 0.08) * 0.5 : 1; }
      return f > 0.45 && f < 0.47 ? 0.6 : (f >= 0.47 ? 1 - 0.15 * Math.exp(-(f - 0.47) * 25) : 1);
    };
    mxAxes(c, gx, gy, gw, gh, {y: 'BRIGHTNESS (shape, illustrative)', x: m === 'oddeven' ? 'TIME (four events)' : 'ORBITAL PHASE'});
    c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
    for (let i = 0; i <= 400; i++){ const f = i / 400; if (f > t + 0.0001) break; const y = gy + 10 + (1 - shape(f, m)) * (gh - 20); i ? c.lineTo(gx + f * gw, y) : c.moveTo(gx + f * gw, y); } c.stroke();
    const note = {eb: 'V-shaped and with a deep secondary: a grazing binary, not a planet',
      beb: 'a 50% eclipse diluted ×1,000 looks like a 500 ppm "planet"',
      heb: 'the pair and the target share a pixel: depth diluted, shape can look planetary',
      oddeven: 'alternate depths differ: two stars, period really twice as long (SetuHQ flags odd_even_mismatch)',
      sys: 'a jump and recovery from the spacecraft, not an orbit'}[m];
    mxText(c, note, gx + 6, gy + 14, {size: 11, color: '#C7C7CC'});
    st.exag = 'curves are shapes, not to a common depth scale; pixel grid to scale';
  }};

// ---------- population: real catalogue data ----------
MXV.valley = {key: 0, period: 1, draw(c, w, h, t, st){
  const V = MX.population && MX.population.valley; if (!V) return;
  const gx = 56, gy = 30, gw = w - gx - 16, gh = h - gy - 48, n = V.counts.length, mx = Math.max(...V.counts);
  const lx = r => gx + (Math.log10(r) - Math.log10(V.edges_re[0])) / (Math.log10(V.edges_re[n]) - Math.log10(V.edges_re[0])) * gw;
  c.fillStyle = 'rgba(255,214,10,.12)'; c.fillRect(lx(1.5), gy, lx(2.0) - lx(1.5), gh);
  mxText(c, 'valley 1.5–2.0 R⊕ (Fulton et al. 2017)', lx(1.5) + 4, gy + 14, {size: 11, color: '#FFD60A'});
  mxAxes(c, gx, gy, gw, gh, {y: 'PLANETS PER BIN (catalogue counts)', x: 'RADIUS (R⊕)'});
  for (let i = 0; i < n; i++){ const x0 = lx(V.edges_re[i]), x1 = lx(V.edges_re[i + 1]), hh = V.counts[i] / mx * (gh - 20); c.fillStyle = '#64D2FF'; c.fillRect(x0 + 0.5, gy + gh - hh, x1 - x0 - 1, hh); }
  for (const r of [0.5, 1, 2, 4, 10, 20]) mxText(c, String(r), lx(r), gy + gh + 14, {size: 11, mono: true, align: 'center'});
  for (const v of [0, Math.round(mx / 2), mx]) mxText(c, String(v), gx - 6, gy + gh - v / mx * (gh - 20) + 4, {size: 11, mono: true, align: 'right'});
  const pm = MX.examples['pi Men c']; if (pm && pm.radius){ const x = lx(pm.radius * 11.209); c.strokeStyle = '#FFB340'; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(x, gy + 20); c.lineTo(x, gy + gh); c.stroke(); c.setLineDash([]); mxText(c, 'pi Men c', x + 4, gy + 30, {size: 11, color: '#FFB340'}); }
}};
function mxSeff(limit, teff){ const [s0, a, b, cc, d] = MX.kopparapu[limit], t = teff - 5780; return s0 + a * t + b * t * t + cc * t ** 3 + d * t ** 4; }
MXV.hz = {key: 0, period: 1, draw(c, w, h, t, st){
  const P = MX.population; if (!P) return;
  const gx = 60, gy = 30, gw = w - gx - 16, gh = h - gy - 48;
  // x: insolation (log, falling to the right like distance from the star); y: stellar temperature.
  const S0 = 3, S1 = 0.1, X = s => gx + (Math.log10(S0) - Math.log10(s)) / (Math.log10(S0) - Math.log10(S1)) * gw, Y = T => gy + gh - (T - 2600) / 4600 * gh;
  mxAxes(c, gx, gy, gw, gh, {y: 'STAR TEMPERATURE (K)', x: 'STARLIGHT RECEIVED (× EARTH)'});
  const band = (a, b, col) => { c.fillStyle = col; c.beginPath(); for (let T = 2600; T <= 7200; T += 50) c.lineTo(X(mxSeff(a, T)), Y(T)); for (let T = 7200; T >= 2600; T -= 50) c.lineTo(X(mxSeff(b, T)), Y(T)); c.closePath(); c.fill(); };
  band('recent_venus', 'early_mars', 'rgba(48,209,88,.10)'); band('runaway_greenhouse', 'maximum_greenhouse', 'rgba(48,209,88,.22)');
  for (const p of P.hz){ c.fillStyle = p[2] ? '#30D158' : 'rgba(48,209,88,.55)'; c.beginPath(); c.arc(X(p[1]), Y(p[0]), 2.6, 0, 2 * Math.PI); c.fill(); }
  c.fillStyle = '#64D2FF'; c.beginPath(); c.arc(X(1), Y(5772), 4.5, 0, 2 * Math.PI); c.fill(); mxText(c, 'Earth', X(1) + 7, Y(5772) - 6, {size: 11, color: '#64D2FF'});
  for (const s of [3, 1, 0.3, 0.1]) mxText(c, String(s), X(s), gy + gh + 14, {size: 11, mono: true, align: 'center'});
  for (const T of [3000, 4000, 5000, 6000, 7000]) mxText(c, T.toLocaleString('en-GB'), gx - 6, Y(T) + 4, {size: 11, mono: true, align: 'right'});
  mxText(c, `dark band: conservative · light: optimistic (Kopparapu et al. 2014) · ${P.hz.length} catalogue planets`, gx + gw, gy - 6, {size: 11, align: 'right'});
}};

// ---------- equations of life ----------
function mxDrakeMC(n, seed, flOrders){
  const rnd = mxRand(seed), ranges = MX.drake_terms.map(([k, , lo, hi]) => k === 'fl' ? [k, -flOrders, 0] : [k, lo, hi]), logs = new Float64Array(n);
  for (let i = 0; i < n; i++){ let s = 0; for (const [, lo, hi] of ranges) s += lo + rnd() * (hi - lo); logs[i] = s; }
  logs.sort();
  const q = f => logs[Math.min(n - 1, Math.floor(f * n))], vars = ranges.map(([k, lo, hi]) => [k, (hi - lo) ** 2 / 12]), tot = vars.reduce((a, v) => a + v[1], 0);
  let below = 0; for (const v of logs) if (v < 0) below++;
  return {logs, median: q(0.5), p05: q(0.05), p95: q(0.95), pLt1: below / n, share: Object.fromEntries(vars.map(([k, v]) => [k, v / tot]))};
}
MXV.drake = {key: 0, period: 1, init(st){ st.opt.fl = 10; st.opt.mc = mxDrakeMC(20000, 42, 10); },
  control(st, el){ if (el.dataset.ctl === 'fl'){ st.opt.fl = Number(el.value); st.opt.mc = mxDrakeMC(20000, 42, st.opt.fl); } },
  draw(c, w, h, t, st){
    const R = st.opt.mc, narrow = w < 600, gx = 50, gy = 30, gw = (narrow ? w : w * 0.62) - gx - 16, gh = narrow ? h * 0.5 - 40 : h - gy - 46;
    const lo = Math.floor(R.logs[0]), hi = Math.ceil(R.logs[R.logs.length - 1]), nb = 60, bins = new Array(nb).fill(0);
    for (const v of R.logs) bins[Math.min(nb - 1, Math.floor((v - lo) / (hi - lo) * nb))]++;
    const mx = Math.max(...bins), X = v => gx + (v - lo) / (hi - lo) * gw;
    mxAxes(c, gx, gy, gw, gh, {y: 'DRAWS', x: 'log10 N'});
    c.fillStyle = 'rgba(48,209,88,.10)'; c.fillRect(X(R.p05), gy, X(R.p95) - X(R.p05), gh);
    for (let i = 0; i < nb; i++){ const hh = bins[i] / mx * (gh - 20); c.fillStyle = (lo + (i + 0.5) * (hi - lo) / nb) < 0 ? '#8E8E93' : '#64D2FF'; c.fillRect(gx + i * gw / nb + 0.5, gy + gh - hh, gw / nb - 1, hh); }
    c.strokeStyle = '#FFB340'; c.beginPath(); c.moveTo(X(R.median), gy); c.lineTo(X(R.median), gy + gh); c.stroke();
    for (const v of [lo, 0, hi]) if (v >= lo && v <= hi) mxText(c, String(v), X(v), gy + gh + 14, {size: 11, mono: true, align: 'center'});
    mxText(c, `median 10^${R.median.toFixed(1)} · 90% in 10^${R.p05.toFixed(1)}–10^${R.p95.toFixed(1)} · P(N < 1) = ${(R.pLt1 * 100).toFixed(0)}%`, gx + 6, gy + 14, {size: 11, mono: true, color: '#F5F5F7'});
    // Each term's share of the spread in log10 N (exact for independent log-uniform terms).
    const tx = narrow ? gx : w * 0.62 + 20, ty = narrow ? gy + gh + 40 : gy, tw = narrow ? w - tx - 20 : w - tx - 20, rows = MX.drake_terms;
    mxText(c, 'SHARE OF THE SPREAD', tx, ty, {size: 11, w: 600, mono: true, color: '#C7C7CC'});
    rows.forEach(([k, label], i) => { const y = ty + 14 + i * 22, f = R.share[k]; c.fillStyle = k === 'fl' || k === 'L' ? '#FF9F0A' : '#64D2FF'; c.fillRect(tx + 70, y, Math.max(1, f * (tw - 120)), 12);
      mxText(c, label.split(' ')[0], tx, y + 10, {size: 11, mono: true}); mxText(c, (f * 100).toFixed(0) + '%', tx + 76 + f * (tw - 120), y + 10, {size: 11, mono: true}); });
  }};
const MX_DRAKE_PRESETS = {
  drake_lo: {R: 1, fp: 0.2, ne: 1, fl: 1, fi: 1, fc: 0.1, L: 1000}, drake_hi: {R: 1, fp: 0.5, ne: 5, fl: 1, fi: 1, fc: 0.2, L: 1e8},
  alt: {R: 10, fp: 0.5, ne: 2, fl: 1, fi: 0.01, fc: 0.01, L: 1e4}, data: {R: 7, fp: 1, ne: 0.37}};
const MX_SEAGER = [['Ns', 'N★ (stars observed)', 1, 6, 30000], ['FQHZ', 'F_Q · F_HZ', -3, 0, 0.15], ['FO', 'F_O (observable)', -5, 0, 0.001], ['FL', 'F_L (life; assumed)', -6, 0, 1], ['FS', 'F_S (detectable gas)', -3, 0, 0.5]];
function mxTermSliders(box, terms, vals, onchange){
  box.innerHTML = terms.map(([k, label, lo, hi]) => `<label class="mxterm"><span>${esc(label)}</span><input type="range" data-k="${k}" min="${lo * 20}" max="${hi * 20}" value="${Math.round(Math.log10(vals[k]) * 20)}" aria-label="${esc(label)}, log scale"><output class="mono" data-o="${k}"></output></label>`).join('');
  const upd = () => { for (const [k] of terms){ const v = Math.pow(10, Number(box.querySelector(`[data-k="${k}"]`).value) / 20); vals[k] = v; box.querySelector(`[data-o="${k}"]`).textContent = v >= 1000 ? Math.round(v).toLocaleString('en-GB') : Number(v.toPrecision(2)).toString(); } onchange(); };
  box.addEventListener('input', upd); upd();
  return v => { for (const k in v){ const el = box.querySelector(`[data-k="${k}"]`); if (el){ el.value = Math.round(Math.log10(v[k]) * 20); } } upd(); };
}
function mxEquationsInit(){
  const box = $('#mxdrake'); if (!box || box.dataset.ready) return; box.dataset.ready = '1';
  const terms = [['R', 'R★ (stars/yr)', 0, 2], ['fp', 'f_p', -1, 0], ['ne', 'n_e', -2, 1], ['fl', 'f_l', -10, 0], ['fi', 'f_i', -6, 0], ['fc', 'f_c', -6, 0], ['L', 'L (years)', 1, 10]];
  const vals = {R: 1, fp: 0.5, ne: 1, fl: 1, fi: 0.01, fc: 0.1, L: 1e4};
  const set = mxTermSliders(box, terms, vals, () => { const N = Object.values(vals).reduce((a, v) => a * v, 1); $('#mxdrakeN').textContent = `N = ${N >= 1 ? Math.round(N).toLocaleString('en-GB') : N.toExponential(1)} (one set of guesses, not a prediction)`; });
  $$('.mxpresets [data-preset]').forEach(b => b.addEventListener('click', () => set(MX_DRAKE_PRESETS[b.dataset.preset])));
  const sv = Object.fromEntries(MX_SEAGER.map(t => [t[0], t[4]]));
  mxTermSliders($('#mxseager'), MX_SEAGER, sv, () => { const N = Object.values(sv).reduce((a, v) => a * v, 1); $('#mxseagerN').textContent = `N = ${N < 10 ? N.toFixed(2) : Math.round(N).toLocaleString('en-GB')} planets with a detectable biosignature gas (on these assumptions)`; });
}

// ---------- molecules: ball-and-stick at measured geometry ----------
const MX_CPK = {H: '#F5F5F7', C: '#8E8E93', N: '#0A84FF', O: '#FF453A', P: '#FF9F0A', S: '#FFD60A', Na: '#BF5AF2', K: '#AF52DE'};
function mxAtoms(g){
  const r = g.r || 1, A = (g.angle || 180) * Math.PI / 180;
  if (g.shape === 'atom') return [[g.atoms[0], 0, 0, 0]];
  if (g.shape === 'diatomic') return [[g.atoms[0], -r / 2, 0, 0], [g.atoms[1], r / 2, 0, 0]];
  if (g.shape === 'linear') return g.r2 ? [[g.atoms[0], -r, 0, 0], [g.atoms[1], 0, 0, 0], [g.atoms[2], g.r2, 0, 0]] : [[g.atoms[0], 0, 0, 0], [g.atoms[1], -r, 0, 0], [g.atoms[2], r, 0, 0]];
  if (g.shape === 'bent' || g.shape === 'dms') return [[g.atoms[0], 0, 0, 0], [g.atoms[1], r * Math.sin(A / 2), -r * Math.cos(A / 2), 0], [g.atoms[2], -r * Math.sin(A / 2), -r * Math.cos(A / 2), 0]];
  if (g.shape === 'pyramidal'){ const cb = Math.sqrt((Math.cos(A) + 0.5) / 1.5), sb = Math.sqrt(1 - cb * cb); return [[g.atoms[0], 0, 0, 0], ...[0, 1, 2].map(i => [g.atoms[i + 1], r * sb * Math.cos(i * 2 * Math.PI / 3), -r * cb, r * sb * Math.sin(i * 2 * Math.PI / 3)])]; }
  if (g.shape === 'tetrahedral'){ const s = r / Math.sqrt(3); return [[g.atoms[0], 0, 0, 0], ...[[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]].map((v, i) => [g.atoms[i + 1], v[0] * s, v[1] * s, v[2] * s])]; }
  return [];
}
// Each normal mode (methods.py: mode_table) carries its displacement pattern, its band and its stated
// exaggeration: the drawn peak displacement (MX_MODE_A) against the zero-point RMS of the atom that moves most.
const MX_MODE_A = 0.2, MX_VIB_CYCLES = 12;
function mxModeOptions(m){ return (m.modes || []).map((d, i) => `<option value="${i}">${esc(mxModeName(d))}${d.um ? ` · ${d.um.toFixed(2)} µm` : ''}${d.ir ? '' : ' · IR-silent'}</option>`).join(''); }
const mxModeName = d => (d.nu ? d.nu + ' ' : '') + d.name;
// A log wavelength axis, 0.5 to 25 µm: the molecule's modes (filled: infrared-active; hollow: silent) and the window
// the Reading-atmospheres chapter draws (0.5 to 5.1 µm).
function mxBandAxis(c, x, y, w, m, cur){
  const lo = Math.log10(0.5), hi = Math.log10(25), X = um => x + (Math.log10(um) - lo) / (hi - lo) * w;
  c.fillStyle = 'rgba(100,210,255,.10)'; c.fillRect(X(0.5), y - 10, X(5.1) - X(0.5), 20);
  mxText(c, 'drawn in Reading atmospheres', x + 4, y - 14, {size: 11, color: '#64D2FF'});
  c.strokeStyle = 'rgba(255,255,255,.35)'; c.lineWidth = 1; c.beginPath(); c.moveTo(x, y); c.lineTo(x + w, y); c.stroke();
  for (const um of [0.5, 1, 2, 5, 10, 20]){ c.beginPath(); c.moveTo(X(um), y - 3); c.lineTo(X(um), y + 3); c.stroke(); mxText(c, um === 0.5 ? '0.5 µm' : `${um}`, X(um), y + 16, {size: 11, mono: true, align: um === 0.5 ? 'left' : 'center'}); }
  (m.modes || []).forEach((d, i) => { if (!d.um) return; const xx = X(d.um), on = i === cur;
    c.strokeStyle = on ? '#FFB340' : 'rgba(255,255,255,.7)'; c.fillStyle = on ? '#FFB340' : 'rgba(255,255,255,.7)'; c.lineWidth = on ? 2 : 1.2;
    c.beginPath(); c.arc(xx, y, on ? 5.5 : 4, 0, 2 * Math.PI); d.ir ? c.fill() : c.stroke(); });
}
MXV.molecule = {key: 0.15, period: 14, init(st){ st.opt.mol = MX.molecules[0]; st.opt.mode = 0; },
  control(st, el){
    if (el.tagName !== 'SELECT') return;
    if (el.dataset.ctl === 'mode'){ st.opt.mode = Number(el.value) || 0; return; }
    st.opt.mol = MX.molecules.find(m => m.id === el.value) || MX.molecules[0];
    if (st.opt.mode >= (st.opt.mol.modes || []).length) st.opt.mode = 0;   // keep the chosen mode where this molecule has it
    document.querySelectorAll('.mxmol').forEach(a => a.classList.toggle('on', a.dataset.mol === st.opt.mol.id));
    const ms = st.fig.querySelector('select[data-ctl="mode"]');
    if (ms){ const has = (st.opt.mol.modes || []).length; ms.innerHTML = has ? mxModeOptions(st.opt.mol) : '<option value="0">No vibrations drawn</option>'; ms.disabled = !has; ms.value = String(st.opt.mode); }
  },
  draw(c, w, h, t, st){
    const m = st.opt.mol, atoms = mxAtoms(m.geom), narrow = w < 600, sc = Math.min(w, h) * (narrow ? 0.2 : 0.22), ry = t * 2 * Math.PI, rx = 0.35;
    const mode = (m.modes || [])[st.opt.mode] || null, ph = Math.sin(t * 2 * Math.PI * MX_VIB_CYCLES);
    const cy = h * (narrow ? 0.46 : 0.48);
    const P = atoms.map(([el, x, y, z], i) => { const d = mode ? mode.disp[i] : [0, 0, 0]; x += MX_MODE_A * ph * d[0]; y += MX_MODE_A * ph * d[1]; z += MX_MODE_A * ph * d[2];
      const x1 = x * Math.cos(ry) + z * Math.sin(ry), z1 = -x * Math.sin(ry) + z * Math.cos(ry), y1 = y * Math.cos(rx) - z1 * Math.sin(rx), z2 = y * Math.sin(rx) + z1 * Math.cos(rx);
      // The displacement direction, turned the same way, for the arrow.
      const dx1 = d[0] * Math.cos(ry) + d[2] * Math.sin(ry), dz1 = -d[0] * Math.sin(ry) + d[2] * Math.cos(ry), dy1 = d[1] * Math.cos(rx) - dz1 * Math.sin(rx);
      return {el, x: w / 2 + x1 * sc, y: cy - y1 * sc, z: z2, ax: dx1, ay: -dy1, mag: Math.hypot(d[0], d[1], d[2])}; });
    if (P.length > 1){ c.strokeStyle = 'rgba(255,255,255,.5)'; c.lineWidth = 5; for (let i = 1; i < P.length; i++){ const j = m.geom.shape === 'linear' && m.geom.r2 && i === 2 ? 1 : 0; c.beginPath(); c.moveTo(P[j].x, P[j].y); c.lineTo(P[i].x, P[i].y); c.stroke(); } }
    for (const a of P.slice().sort((p, q) => p.z - q.z)){
      const rad = (a.el === 'H' ? 0.22 : a.el.length > 1 || a.el === 'K' ? 0.5 : 0.34) * sc, col = MX_CPK[a.el] || '#C7C7CC';
      const g = c.createRadialGradient(a.x - rad * 0.3, a.y - rad * 0.3, rad * 0.1, a.x, a.y, rad); g.addColorStop(0, '#FFFFFF'); g.addColorStop(0.35, col); g.addColorStop(1, '#111');
      c.fillStyle = g; c.beginPath(); c.arc(a.x, a.y, rad, 0, 2 * Math.PI); c.fill();
      mxText(c, a.el, a.x, a.y + 4, {size: 11, w: 700, align: 'center', color: a.el === 'H' || a.el === 'S' ? '#000' : '#FFF'});
      if (mode && a.mag > 0.05){ // where this atom moves (both ways), drawn over it
        const L = sc * 0.55 * a.mag, ux = a.ax / (Math.hypot(a.ax, a.ay) || 1), uy = a.ay / (Math.hypot(a.ax, a.ay) || 1);
        c.strokeStyle = 'rgba(255,179,64,.85)'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(a.x - ux * L, a.y - uy * L); c.lineTo(a.x + ux * L, a.y + uy * L); c.stroke();
        for (const s of [-1, 1]){ const tx = a.x + s * ux * L, ty = a.y + s * uy * L; c.beginPath(); c.moveTo(tx, ty); c.lineTo(tx - s * (ux * 6 - uy * 4), ty - s * (uy * 6 + ux * 4)); c.moveTo(tx, ty); c.lineTo(tx - s * (ux * 6 + uy * 4), ty - s * (uy * 6 - ux * 4)); c.stroke(); }
      }
    }
    mxText(c, `${m.f} · ${m.name}`, 14, 22, {size: 14, w: 600, color: '#F5F5F7'});
    const g = m.geom; mxText(c, g.shape === 'atom' ? 'single atom' : `${g.shape === 'dms' ? 'C–S–C core (hydrogens not drawn)' : g.shape}: bond ${g.r} Å${g.angle ? `, angle ${g.angle}°` : ''} (NIST CCCBDB)`, 14, 40, {size: 11});
    if (mode){
      mxText(c, `${mxModeName(mode)}${mode.deg > 1 ? ` (one of ${mode.deg})` : ''}`, 14, 58, {size: 12, w: 600, color: '#FFB340'});
      mxText(c, mode.um ? `${mode.um.toFixed(2)} µm · ${mode.ir ? 'infrared-active' : 'infrared-silent: the dipole does not change'}` : `${mode.ir ? 'infrared-active' : 'infrared-silent'}; the atlas lists no wavelength`, 14, 74, {size: 11});
    } else mxText(c, g.shape === 'atom' ? 'a single atom has no vibrations; its lines are electronic' : 'its 21 modes are not drawn: the atlas gives band regions only', 14, 58, {size: 11});
    c.strokeStyle = '#C7C7CC'; c.lineWidth = 1; c.beginPath(); c.moveTo(14, h - 70); c.lineTo(14 + sc, h - 70); c.stroke(); mxText(c, '1 Å', 14 + sc / 2, h - 76, {size: 11, align: 'center'});
    if (m.modes && m.modes.length) mxBandAxis(c, 24, h - 26, w - 48, m, st.opt.mode);
    if (P.length > 1){
      if (mode && mode.exag){ const slow = (st.vis.period / MX_VIB_CYCLES / (st.speed || 1)) / (mode.um * 1e-6 / MX_C);
        st.exag = `amplitude ×${mode.exag} (zero-point RMS of ${mode.atom} ≈ ${mode.rms.toFixed(3)} Å); time slowed ≈10${mxSup(Math.round(Math.log10(slow)))}×; sizes of atoms illustrative`; }
      else if (mode) st.exag = 'amplitude and time illustrative (no frequency in the atlas); sizes of atoms illustrative';
      else st.exag = 'sizes of atoms illustrative';
    }
  }};

// ---------- the section ----------
function mxShowChapter(ch){
  if (!MX) return;
  if (!MX.chapters.includes(ch)) ch = MX.chapters[0];
  $$('#route-methods .mxch').forEach(a => { const on = a.dataset.ch === ch; if (a.hidden === on){ a.hidden = !on; } mxActivate(a, on && current === 'methods'); });
  $$('#route-methods .mxtoc a').forEach(a => { if (a.dataset.ch === ch) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current'); });
  mxCurrent = ch;
  // A chapter's own page opens with its title (the section's introduction is the first chapter's page only).
  const hd = $('#route-methods > header.headrow'), h1 = $('#h-methods'), deep = ch !== MX.chapters[0];
  if (h1){ if (!h1.dataset.intro) h1.dataset.intro = h1.innerHTML; h1.innerHTML = deep ? esc(MX.labels[ch]) : h1.dataset.intro; }
  if (hd) hd.classList.toggle('deep', deep);
  if (ch === 'equations') mxEquationsInit();
}
let mxCurrent = null;
function mxShown(on){ if (!MX) return; $$('#route-methods .mxch').forEach(a => mxActivate(a, on && !a.hidden)); }
function renderMethods(){ /* the chapters are static HTML; stages start when their chapter opens */ }
// Every system view (Methods, the Transit case, the Galaxy's sheet, planet and star pages) goes through here:
// it draws from the stored values given, and says in the caption which values are not stored.
const MX_KEYS = [['star temperature', 'star_teff'], ['star radius', 'star_radius'], ['planet radius', 'radius'], ['orbital period', 'orbital_period'], ['semi-major axis', 'semi_major_axis'], ['inclination', 'inclination']];
function mxSystemView(fig, p, o){
  o = o || {};
  const st = mxSetup(fig), S = mxSystemParams(p, o.dip || null);
  st.opt.sys = S;
  const missing = MX_KEYS.filter(([, k]) => p[k] == null).map(([l]) => l);
  const nonTransit = p.inclination != null && p.semi_major_axis && p.star_radius && S.ars * Math.cos(p.inclination * Math.PI / 180) > 1 + S.k;
  const note = `Drawn from stored values only (${o.source || MX.source}${o.fetched ? ', fetched ' + o.fetched.slice(0, 10) : ''}).` + (missing.length ? ` Not stored: ${missing.join(', ')}; those parts are illustrative and say so on the drawing.` : '')
    + (p.star_teff == null ? ' Star colour: the Sun’s, as the temperature is not stored.' : '') + (p.orbital_period == null ? ' Period not stored: the time axis is illustrative.' : '')
    + (nonTransit ? ' At the stored inclination this planet does not transit; the view shows a transit to explain the method.' : '');
  const desc = `${p.name}: a ${Math.round(S.teff).toLocaleString('en-GB')} K star drawn in its blackbody colour, the planet crossing at b = ${S.b.toFixed(2)} (${S.bSrc}), and a limb-darkened model light curve from the stored values.`;
  fig.querySelector('canvas').setAttribute('aria-label', o.desc || desc);
  const art = fig.querySelector('.mxart'); if (art) art.hidden = S.look === 'silhouette';  // a candidate is a silhouette, not art
  if (o.caption !== false) fig.querySelector('figcaption').textContent = note;
  st.on = !!o.on; st.t = MXV.system.key; mxDraw(st);
  if (st.on && !mxRM.matches && !st.started){ st.started = true; mxPlay(st, true); } else mxKick(st);
  return {st, S, note, desc};
}
// The Galaxy's "system view" sheet: the same animated system for any stored example planet. Opened from a point on
// a map (from = {x, y, kind}), it arrives through a magnifier: a lens that opens from that point.
function mxOpenSystem(name, back, from){
  const p = MX && MX.examples[name]; if (!p) return;
  let dlg = $('#mxsheet');
  if (!dlg){
    dlg = document.createElement('dialog'); dlg.id = 'mxsheet'; dlg.className = 'mxsheet';
    dlg.innerHTML = `<div class="mxsheethead"><h2 id="mxsheettitle"></h2><button class="btn" type="button" id="mxsheetclose">Close</button></div>${$('#mxsystpl').innerHTML}<p class="mxsheetzoom" id="mxsheetzoom" hidden></p><p class="mxsheetnote" id="mxsheetnote"></p>`;
    document.body.appendChild(dlg);
    $('#mxsheetclose').addEventListener('click', () => dlg.close());
    dlg.addEventListener('close', () => { const st = dlg.querySelector('.mxstage')._mx; if (st){ st.on = false; }
      // A zoom still under way when the sheet closes is cut short: no lens is left behind.
      dlg.getAnimations().forEach(a => a.cancel()); const ln = dlg.querySelector('.mxlens'); if (ln) ln.remove();
      if (dlg._back) dlg._back.focus(); });
  }
  dlg._back = back || null;
  const fig = dlg.querySelector('.mxstage');
  $('#mxsheettitle').textContent = name;
  const z = from ? mxZoomInfo(p, from.kind) : null, zn = $('#mxsheetzoom');
  zn.hidden = !from;
  if (from) zn.textContent = (z ? `From the ${from.kind === 'sky' ? 'sky map' : 'Galaxy map'} to this orbit is a jump of about ${z.v} in scale (${z.what}). ` : '')
    + 'The zoom between them is an illustration of scale, not continuous data.';
  if (!dlg.open) dlg.showModal();
  mxSystemView(fig, Object.assign({name}, p), {dip: name === 'pi Men c' && MX.lead_dip ? {pts: MX.lead_dip.pts} : null, on: true, fetched: MX.fetched_at});
  // The canonical pages for this planet and its star.
  $('#mxsheetnote').innerHTML = `${objLink('planet', name, name + ' ›')} ${p.star_name ? objLink('star', p.star_name, p.star_name + ' ›') : ''}`;
  $('#mxsheetclose').focus();
  if (from && !mxRM.matches && dlg.animate) mxZoomLens(dlg, from, z);
}
const mxSup = n => String(n).split('').map(d => '⁰¹²³⁴⁵⁶⁷⁸⁹'['0123456789'.indexOf(d)] || (d === '-' ? '⁻' : d)).join('');
// How far the zoom jumps, from stored values: on the Galaxy map, from the star's distance to its orbit (both
// lengths); on the sky map, from the whole sky (2π radians) to the orbit's angle on the sky, a/d.
function mxZoomInfo(p, kind){
  const d = p.star_distance, a = p.semi_major_axis; if (!(d > 0 && a > 0)) return null;
  const dAU = d * 206264.806, ly = d * 3.26156;
  if (kind === 'sky') return {v: mxSig1(2 * Math.PI / (a / dAU)), what: `the whole sky, then an orbit of ${a} AU seen from ${ly.toFixed(1)} light-years, ${(a / dAU * 206264806).toPrecision(2)} milliarcseconds across`};
  return {v: mxSig1(dAU / a), what: `${ly.toFixed(1)} light-years to the star, ${a} AU from star to planet`};
}
// A number to one significant figure, as 4×10⁸.
function mxSig1(x){ let e = Math.floor(Math.log10(x)), m = Math.round(x / Math.pow(10, e)); if (m === 10){ m = 1; e++; } return `${m}×10${mxSup(e)}`; }
// The magnifier: the sheet is revealed through a growing circle centred on the point that was chosen, with a lens rim
// and a label that says what the zoom is. Never under reduced motion (the sheet simply opens).
function mxZoomLens(dlg, from, z){
  const r = dlg.getBoundingClientRect(), x = from.x - r.left, y = from.y - r.top;
  const R = Math.hypot(Math.max(x, r.width - x), Math.max(y, r.height - y)) + 4, dur = 950, ease = 'cubic-bezier(.2,.8,.2,1)';
  dlg.animate([{clipPath: `circle(28px at ${x}px ${y}px)`}, {clipPath: `circle(28px at ${x}px ${y}px)`, offset: 0.2}, {clipPath: `circle(${R}px at ${x}px ${y}px)`}], {duration: dur, easing: ease});
  const old = dlg.querySelector('.mxlens'); if (old) old.remove();
  const lens = document.createElement('div'); lens.className = 'mxlens'; lens.setAttribute('aria-hidden', 'true');
  lens.innerHTML = `<i style="left:${x}px;top:${y}px"></i><span>${z ? `zoom ≈ ×${z.v} · ` : ''}an illustration of scale, not continuous data</span>`;
  dlg.appendChild(lens);
  lens.querySelector('i').animate([{width: '56px', height: '56px', opacity: 1}, {width: '56px', height: '56px', opacity: 1, offset: 0.2}, {width: `${2 * R}px`, height: `${2 * R}px`, opacity: 0.15}], {duration: dur, easing: ease, fill: 'forwards'});
  lens.querySelector('span').animate([{opacity: 0}, {opacity: 1, offset: 0.12}, {opacity: 1, offset: 0.75}, {opacity: 0}], {duration: dur + 900, fill: 'forwards'});
  setTimeout(() => lens.remove(), dur + 950);
}

// ---------- the survey-scan intro on the Sky and Galaxy maps ----------
// The Methods "survey scan", played once over a map the first time its section opens in a session: about five
// seconds, a Skip button, and no pointer capture, so the map underneath stays live; the first touch, wheel or key
// on the map ends it. It draws only while its section is shown, on screen and the tab visible, and never under
// reduced motion.
const MX_INTRO_MS = 5200, MX_INTRO_T = 0.62;
const mxIntros = {};
function mxIntroStart(key, host){
  if (!MX || !host || mxRM.matches || mxIntros[key]) return;
  let seen = false; try { seen = sessionStorage.getItem('setuhq-intro-' + key) === 'done'; } catch (e) { /* storage blocked: play it */ }
  if (seen){ mxIntros[key] = {done: true}; return; }
  const el = document.createElement('div'); el.className = 'mxintro';
  el.innerHTML = '<canvas aria-hidden="true"></canvas><div class="mxintrobar" role="group" aria-label="Introduction animation">'
    + MX.ill_badge + '<span class="mxintrocap">A survey checks stars one at a time · star positions illustrative</span>'
    + '<button class="btn mxskip" type="button">Skip intro</button></div>';
  host.appendChild(el);
  const I = {key, host, el, cv: el.querySelector('canvas'), st: {opt: {intro: true}, vis: MXV.scan, exag: ''}, ms: 0, last: 0, raf: 0, visible: false, done: false, frames: 0};
  MXV.scan.init(I.st); I.st.opt.intro = true;
  mxIntros[key] = I;
  el.querySelector('.mxskip').addEventListener('click', () => mxIntroEnd(I, true));
  I.touch = e => { if (e && e.target && e.target.closest && e.target.closest('.mxskip')) return; mxIntroEnd(I, false); };
  for (const ev of ['pointerdown', 'wheel', 'keydown']) host.addEventListener(ev, I.touch, {passive: true});
  if ('IntersectionObserver' in window){ I.io = new IntersectionObserver(es => { I.visible = es[es.length - 1].isIntersecting; mxIntroKick(I); }); I.io.observe(host); }
  else I.visible = true;
  mxIntroDraw(I, 0);
  mxIntroKick(I);
}
const mxIntroLive = I => !I.done && I.visible && !document.hidden && current === I.key;
function mxIntroKick(I){ if (I && !I.done && !I.raf && mxIntroLive(I)){ I.last = 0; I.raf = requestAnimationFrame(ts => mxIntroFrame(I, ts)); } }
function mxIntroFrame(I, ts){
  I.raf = 0;
  if (!mxIntroLive(I)) return;
  I.ms += I.last ? Math.min(100, ts - I.last) : 16; I.last = ts; I.frames++;
  const f = Math.min(1, I.ms / MX_INTRO_MS);
  mxIntroDraw(I, f);
  if (f >= 1){ mxIntroEnd(I, false); return; }
  I.raf = requestAnimationFrame(t2 => mxIntroFrame(I, t2));
}
function mxIntroDraw(I, f){
  const box = I.el.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1), w = Math.round(box.width), h = Math.round(box.height);
  if (w < 2 || h < 2) return;
  if (I.cv.width !== Math.round(w * dpr) || I.cv.height !== Math.round(h * dpr)){ I.cv.width = Math.round(w * dpr); I.cv.height = Math.round(h * dpr); }
  const c = I.cv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
  c.fillStyle = 'rgba(0,0,0,.66)'; c.fillRect(0, 0, w, h);
  MXV.scan.draw(c, w, h, f * MX_INTRO_T, I.st);
}
function mxIntroEnd(I, skipped){
  if (!I || I.done) return;
  I.done = true;
  if (I.raf){ cancelAnimationFrame(I.raf); I.raf = 0; }
  if (I.io) I.io.disconnect();
  for (const ev of ['pointerdown', 'wheel', 'keydown']) I.host.removeEventListener(ev, I.touch);
  try { sessionStorage.setItem('setuhq-intro-' + I.key, 'done'); } catch (e) { /* storage blocked */ }
  I.el.classList.add('out'); setTimeout(() => I.el.remove(), 420);
  if (skipped && typeof say === 'function') say('Intro skipped.');
}
// The router calls this on every section change: an intro starts on its own section and ends when it is left.
function mxIntroRoute(r){
  if (r === 'sky') mxIntroStart('sky', $('#route-sky .skymap'));
  if (r === 'galaxy') mxIntroStart('galaxy', $('#gxstage'));
  for (const k in mxIntros){ const I = mxIntros[k]; if (I.done) continue; if (k !== r) mxIntroEnd(I, false); else mxIntroKick(I); }
}
document.addEventListener('visibilitychange', () => { for (const k in mxIntros) mxIntroKick(mxIntros[k]); });

// ---------- catalogue: every record, planet and star pages, global search ----------
const CTM = D.catalogue_meta || null;
// URL state: q, method (list), year/mass/radius/period/teq/dist/teff ranges as lo~hi, multi, hasdist, sort, dir.
function decodeCatView(p){
  const v = {q: (p.get('q') || '').slice(0, 120), methods: [], sort: 'name', dir: 'asc', multi: p.get('multi') === '1', hasdist: p.get('hasdist') === '1'};
  const ms = (p.get('method') || '').split(',');
  if (CTM) v.methods = CTM.methods.filter(m => ms.includes(m));
  for (const [, , , key] of (CTM ? CTM.ranges : [])){
    const raw = p.get(key); v[key] = [null, null];
    if (raw){ const [a, b] = raw.split('~'); const lo = a === '' || a === undefined ? null : Number(a), hi = b === '' || b === undefined ? null : Number(b);
      v[key] = [Number.isFinite(lo) ? lo : null, Number.isFinite(hi) ? hi : null]; }
  }
  if (CTM && CTM.sorts.includes(p.get('sort'))) v.sort = p.get('sort');
  if (p.get('dir') === 'desc') v.dir = 'desc';
  return v;
}
function encodeCatView(v){
  const out = [];
  if (v.q) out.push('q=' + encodeURIComponent(v.q));
  if (v.methods.length) out.push('method=' + CTM.methods.filter(m => v.methods.includes(m)).join(','));
  for (const [, , , key] of CTM.ranges){ const r = v[key] || [null, null]; if (r[0] !== null || r[1] !== null) out.push(`${key}=${r[0] === null ? '' : r[0]}~${r[1] === null ? '' : r[1]}`); }
  if (v.multi) out.push('multi=1');
  if (v.hasdist) out.push('hasdist=1');
  if (v.sort !== 'name') out.push('sort=' + v.sort);
  if (v.dir === 'desc') out.push('dir=desc');
  return out.join('&');
}
// The filter (tests compare it with catalogue.catalogue_filter in Python): a missing value never passes a range.
function ctFilter(P, v, starN, skipMethods){
  const n = P.name.length, q = (v.q || '').trim().toLowerCase(), ms = new Set(skipMethods ? [] : v.methods), out = [];
  const ranges = CTM.ranges.map(([col, , , key]) => [col, v[key] || [null, null]]).filter(([, r]) => r[0] !== null || r[1] !== null);
  for (let i = 0; i < n; i++){
    if (q){ const hay = [P.name[i], P.star[i], P.alt[i], P.salt[i]].filter(Boolean).join(' ').toLowerCase(); if (!hay.includes(q)) continue; }
    if (ms.size && !ms.has(P.method[i])) continue;
    let ok = true;
    for (const [col, [lo, hi]] of ranges){ let x = P[col][i]; if (col === 'mass' && x === null) x = P.msini[i];
      if (x === null || x === undefined || (lo !== null && x < lo) || (hi !== null && x > hi)){ ok = false; break; } }
    if (!ok) continue;
    if (v.multi && !(P.star[i] && starN[P.star[i]] >= 2)) continue;
    if (v.hasdist && P.dist[i] === null) continue;
    out.push(i);
  }
  return out;
}
function ctSort(P, idx, key, dir){
  const col = key === 'mass' ? P.mass.map((m, i) => m === null ? P.msini[i] : m) : P[key], s = dir === 'desc' ? -1 : 1;
  return idx.slice().sort((a, b) => { const x = col[a], y = col[b];
    if (x === null || x === undefined) return (y === null || y === undefined) ? a - b : 1;   // missing values last, either way
    if (y === null || y === undefined) return -1;
    if (typeof x === 'string') return s * x.localeCompare(y, 'en', {sensitivity: 'base'}) || a - b;
    return s * (x - y) || a - b; });
}

const ct = {rangeT: {}, P: null, loading: null, view: null, idx: [], starN: {}, bySlug: {}, starBySlug: {}, byStar: {}, rendered: false, rowH: 44};
function ctLoad(){
  if (!ct.loading) ct.loading = fetch('/assets/data/catalogue.json').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(C => {
    ct.C = C; ct.P = C.planets;
    const P = ct.P;
    P.name.forEach((nm, i) => { ct.bySlug[P.slug[i]] = i; const s = P.star[i]; if (s){ ct.starN[s] = (ct.starN[s] || 0) + 1; (ct.byStar[s] = ct.byStar[s] || []).push(i); } });
    C.stars.names.forEach((s, k) => { ct.starBySlug[C.stars.slugs[k]] = s; });
    return C;
  });
  return ct.loading;
}
const ctFmt = (x, d) => x === null || x === undefined ? null : (Math.abs(x) >= 1000 ? Math.round(x).toLocaleString('en-GB') : Number(x.toPrecision(d || 4)).toString());
const ctPlanetHref = i => planetHref(ct.P.name[i]);
const ctStarHref = s => starHref(s);

// ---------- the table: only the rows in view are in the page ----------
function renderCatalogue(){
  if (!CTM) return;
  ctLoad().then(() => { ct.rendered = true; ctBind(); ctApply(); }).catch(() => { $('#ctcount').textContent = 'The catalogue file (assets/data/catalogue.json) could not be loaded here.'; });
}
const CT_CARD_H = 128;
function ctPhone(){ return window.matchMedia('(max-width: 699.98px)').matches; }
function ctApply(){
  if (!ct.P || !ct.view) return;
  const v = ct.view;
  ct.idx = ctSort(ct.P, ctFilter(ct.P, v, ct.starN), v.sort, v.dir);
  // Faceted counts: each method's count under every other filter.
  const base = ctFilter(ct.P, v, ct.starN, true), cnt = {};
  for (const i of base) cnt[ct.P.method[i]] = (cnt[ct.P.method[i]] || 0) + 1;
  $$('#ctmethods [data-cmn]').forEach(s => { s.textContent = (cnt[s.dataset.cmn] || 0).toLocaleString('en-GB'); });
  $('#ctcount').textContent = `Showing ${ct.idx.length.toLocaleString('en-GB')} of ${ct.P.name.length.toLocaleString('en-GB')} planets`;
  $('#cttable').setAttribute('aria-rowcount', String(ct.idx.length));
  ctControls();
  ct.rowH = ctPhone() ? CT_CARD_H : 44;
  $('#ctspacer').style.height = ct.idx.length * ct.rowH + 'px';
  $('#ctscroll').scrollTop = 0;
  // No match: say so, with a way out, instead of an empty box.
  $('#ctempty').hidden = ct.idx.length > 0; $('#ctscroll').hidden = !ct.idx.length;
  ctRows(true);
}
// The host's colour (its stored Teff as a blackbody, SetuRender.teffRGB; cached by 50 K) and the size class (CLASS_RULE).
const ctDotC = {};
function ctDot(teff){
  if (!(teff > 0) || !window.SetuRender) return '<i class="ctdot none" aria-hidden="true"></i>';
  const k = Math.round(teff / 50) * 50, c = ctDotC[k] || (ctDotC[k] = SetuRender.teffRGB(k).join(','));
  return `<i class="ctdot" style="background:rgb(${c})" aria-hidden="true"></i>`;
}
const CT_CLASSES = ['Earth-size', 'Super-Earth', 'Sub-Neptune', 'Neptune-like', 'Gas giant'];
function ctCls(i){ const P = ct.P, c = typeof mxClassOf === 'function' ? mxClassOf(P.radius[i], P.mass[i] !== null ? P.mass[i] : P.msini[i]) : null; return c === null || c === undefined ? '' : CT_CLASSES[c]; }
// One row: the planet's name is the row header, then one cell per column header (10 in all, at every width).
// On a phone the same cells wrap into a card, each with its label shown.
const CT_COLS = [['star', 'Host', ''], ['year', 'Year', ''], ['method', 'Method', ''], ['mass', 'Mass', 'MJ'], ['radius', 'Radius', 'RJ'],
  ['period', 'Period', 'd'], ['teq', 'Teq', 'K'], ['dist', 'Distance', 'pc'], ['steff', 'Host Teff', 'K']];
function ctRowHTML(r){
  const P = ct.P, i = ct.idx[r], h = ct.rowH, phone = h > 50, col = m => GXM && GXM.method_colour ? GXM.method_colour[m] : '#8E8E93';
  const cell = (k, lab, unit) => {
    let v, cls = 'num';
    if (k === 'star'){ v = P.star[i] ? ctDot(P.steff[i]) + esc(P.star[i]) : null; cls = ''; }
    else if (k === 'method'){ v = `<i style="background:${col(P.method[i])}"></i>${esc(CTM.method_label[P.method[i]] || P.method[i])}`; cls = ''; }
    else if (k === 'year') v = P.year[i] || null;
    else if (k === 'mass') v = P.mass[i] !== null ? ctLim(i, 'mass') + ctFmt(P.mass[i], 3) : (P.msini[i] !== null ? ctLim(i, 'msini') + ctFmt(P.msini[i], 3) + ' sin i' : null);
    else v = P[k][i] === null || P[k][i] === undefined ? null : ctLim(i, k) + ctFmt(P[k][i], k === 'period' ? 5 : k === 'radius' ? 3 : 4);
    // On a phone card each cell carries its label and unit as plain text (no extra boxes to style or lay out).
    if (v === null) return `<span role="cell" class="${cls} na" aria-label="not stored">—</span>`;
    return phone ? `<span role="cell">${k === 'star' || k === 'method' ? '' : lab + ' '}${v}${unit ? ' ' + unit : ''}</span>` : `<span role="cell" class="${cls}">${v}</span>`;
  };
  return `<a class="${h > 50 ? 'ctcard' : 'ctrow'}" role="row" aria-rowindex="${r + 1}" href="${ctPlanetHref(i)}" style="top:${r * h}px"><span role="rowheader"><b>${esc(P.name[i])}</b>${ctCls(i) ? ` <span class="ctcls">${esc(ctCls(i))}</span>` : ''}</span>${CT_COLS.map(c => cell(...c)).join('')}</a>`;
}
// Only the rows in view (plus a margin) are in the page. Scrolling keeps the rows already there and adds or
// removes only those entering or leaving the window, in order.
function ctRows(force){
  const sc = $('#ctscroll'), sp = $('#ctspacer'), H = sc.clientHeight, top = sc.scrollTop, h = ct.rowH;
  // A 12-row margin while scrolling normally; during a fling (more than a screen per frame) only the rows in
  // view, plus two, since the margin would be gone before anyone saw it.
  const m = Math.abs(top - (ct.prevTop ?? top)) > H ? 2 : 12; ct.prevTop = top;
  const a = Math.max(0, Math.floor(top / h) - m), b = Math.min(ct.idx.length, Math.ceil((top + H) / h) + m);
  if (force || !ct.nodes){ sp.textContent = ''; ct.nodes = new Map(); ct.win = null; ct.lastTop = top; }
  if (ct.win && ct.win[0] === a && ct.win[1] === b) return;
  const old = ct.win; ct.win = [a, b];
  const add = []; for (let r = a; r < b; r++) if (!ct.nodes.has(r)) add.push(r);
  if (!add.length){ for (const [r, el] of ct.nodes) if (r < a || r >= b){ el.remove(); ct.nodes.delete(r); } return; }
  // A jump (a fling, or a window that keeps under half its rows): render the whole window and swap it in with
  // one replaceChildren, instead of removing and inserting node by node.
  const jump = !old || add.length * 2 > b - a, rows = jump ? Array.from({length: b - a}, (_, k) => a + k) : add;
  const t = document.createElement('template'); t.innerHTML = rows.map(ctRowHTML).join('');
  const els = [...t.content.children];
  if (jump){ ct.nodes = new Map(rows.map((r, k) => [r, els[k]])); sp.replaceChildren(...els); return; }
  // A small step: drop the rows that left, add the new ones in order.
  for (const [r, el] of ct.nodes) if (r < a || r >= b){ el.remove(); ct.nodes.delete(r); }
  els.forEach((el, k) => ct.nodes.set(rows[k], el));
  const first = sp.firstElementChild, firstR = first ? Number(first.getAttribute('aria-rowindex')) - 1 : Infinity;
  if (rows[0] < firstR) sp.prepend(...els); else sp.append(...els);
}
function ctControls(){
  const v = ct.view;
  $('#ctq').value !== v.q && document.activeElement !== $('#ctq') && ($('#ctq').value = v.q);
  $$('#ctmethods [data-cm]').forEach(b => b.setAttribute('aria-pressed', String(v.methods.includes(b.dataset.cm))));
  // Never overwrite a box being typed in, or one whose range is still waiting to apply.
  $$('#route-catalogue [data-rk]').forEach(inp => { if (document.activeElement === inp || ct.rangeT[inp.dataset.rk]) return; const r = v[inp.dataset.rk] || [null, null], x = r[inp.dataset.end === 'lo' ? 0 : 1]; inp.value = x === null ? '' : x; });
  const tr = v.teff || [null, null];
  $$('#route-catalogue [data-ts]').forEach(inp => { if (document.activeElement === inp) return; const x = inp.dataset.ts === 'lo' ? (tr[0] ?? 2500) : (tr[1] ?? 10000); inp.value = x; inp.setAttribute('aria-valuetext', Number(x).toLocaleString('en-US') + ' K'); });
  $('#ctmulti').setAttribute('aria-pressed', String(v.multi)); $('#cthasdist').setAttribute('aria-pressed', String(v.hasdist));
  $$('#cttable .cth').forEach(h => h.setAttribute('aria-sort', h.dataset.sort === v.sort ? (v.dir === 'desc' ? 'descending' : 'ascending') : 'none'));
  if (Object.keys(v).some(k => Array.isArray(v[k]) && v[k].length === 2 && (v[k][0] !== null || v[k][1] !== null) && k !== 'methods')) $('#route-catalogue .ctmore').open = true;
}
function syncCatURL(push){ if (current === 'catalogue' && ct.view) setHash('#/catalogue' + (encodeCatView(ct.view) ? '?' + encodeCatView(ct.view) : ''), !!push); }
function ctBind(){
  if (ct.bound) return; ct.bound = true;
  let qt = null;
  $('#ctq').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { ct.view.q = e.target.value.slice(0, 120); ctApply(); syncCatURL(false); }, 120); });
  $('#ctmethods').addEventListener('click', e => { const b = e.target.closest('[data-cm]'); if (!b) return; const m = b.dataset.cm, on = ct.view.methods.includes(m);
    ct.view.methods = CTM.methods.filter(x => x === m ? !on : ct.view.methods.includes(x)); ctApply(); syncCatURL(true); });
  // Ranges apply as you type, with the same debounce as the text search (the address is replaced, not pushed).
  // Each range has its own timer, and when it fires it reads both of its boxes, so typing "from", Tab, "to"
  // quickly keeps both ends.
  $$('#route-catalogue [data-rk]').forEach(inp => inp.addEventListener('input', () => {
    const k = inp.dataset.rk; clearTimeout(ct.rangeT[k]);
    ct.rangeT[k] = setTimeout(() => { delete ct.rangeT[k];
      const val = end => { const el = $(`#route-catalogue [data-rk="${k}"][data-end="${end}"]`), x = el.value === '' ? null : Number(el.value); return Number.isFinite(x) ? x : null; };
      ct.view[k] = [val('lo'), val('hi')]; ctApply(); syncCatURL(false); }, 120);
  }));
  $('#ctmulti').addEventListener('click', () => { ct.view.multi = !ct.view.multi; ctApply(); syncCatURL(true); });
  $('#cthasdist').addEventListener('click', () => { ct.view.hasdist = !ct.view.hasdist; ctApply(); syncCatURL(true); });
  $('#ctreset').addEventListener('click', () => { ct.view = decodeCatView(new URLSearchParams()); ctApply(); syncCatURL(true); });
  $$('#cttable .cth').forEach(h => h.addEventListener('click', () => { const k = h.dataset.sort; ct.view.dir = ct.view.sort === k && ct.view.dir === 'asc' ? 'desc' : 'asc'; ct.view.sort = k; ctApply(); syncCatURL(true); }));
  // One update per frame however many scroll events arrive, and none when the top has not moved: a fling's
  // big jump rebuilds once.
  $('#ctscroll').addEventListener('scroll', () => { if (!ct.raf) ct.raf = requestAnimationFrame(() => { ct.raf = 0; const top = $('#ctscroll').scrollTop; if (top === ct.lastTop) return; ct.lastTop = top; ctRows(false); }); }, {passive: true});
  // A resize (or the phone breakpoint) changes the window of rows and, at the breakpoint, the row height.
  const relayout = () => { if (current !== 'catalogue' || !ct.P) return; const h = ctPhone() ? CT_CARD_H : 44; if (h !== ct.rowH){ ct.rowH = h; $('#ctspacer').style.height = ct.idx.length * h + 'px'; } ctRows(true); };
  if (window.ResizeObserver) new ResizeObserver(relayout).observe($('#ctscroll'));
  $('#ctcsv').addEventListener('click', ctCsv);
  // V09: the temperature strip's two handles set the host-temperature range (the strip's ends mean no limit).
  $('#route-catalogue').addEventListener('setu:teff-range', e => { const d = e.detail || {}, lo = Number(d.lo), hi = Number(d.hi);
    ct.view.teff = [lo > 2500 ? lo : null, hi < 10000 ? hi : null]; ctApply(); syncCatURL(false); });
}
// CSV of the filtered, sorted view: every stored column with its errors; empty where not stored.
function ctCsv(){
  const P = ct.P, cols = ct.C.columns.filter(c => c !== 'slug'), q = x => x === null || x === undefined ? '' : (/[",\n]/.test(String(x)) ? '"' + String(x).replace(/"/g, '""') + '"' : String(x));
  const lines = [cols.join(',')]; for (const i of ct.idx) lines.push(cols.map(c => q(P[c][i])).join(','));
  lines.push(`# ${ct.idx.length} rows from ${ct.C.source_name}, fetched ${ct.C.fetched_at}; filters: ${encodeCatView(ct.view) || 'none'}`);
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n') + '\n'], {type: 'text/csv'}));
  a.download = 'setuhq-catalogue.csv'; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  say(`Downloading ${ct.idx.length} rows as CSV.`);
}
function applyCatalogue(v){ ct.view = v; if (ct.rendered) ctApply(); }

// ---------- planet and star pages ----------
const CT_ROWS = [
  ['Mass', 'mass', 'MJ'], ['Minimum mass (m sin i)', 'msini', 'MJ'], ['Radius', 'radius', 'RJ'], ['Orbital period', 'period', 'd'],
  ['Semi-major axis', 'a', 'AU'], ['Eccentricity', 'e', ''], ['Inclination', 'incl', '°'], ['Impact parameter', 'b', ''],
  ['RV semi-amplitude K', 'k', 'm/s'], ['Equilibrium temperature', 'teq', 'K'], ['Measured temperature', 'tmeas', 'K'], ['Spin–orbit angle λ', 'lambda', '°']];
const CT_STAR_ROWS = [['Effective temperature', 'steff', 'K'], ['Radius', 'srad', 'R☉'], ['Mass', 'smass', 'M☉'], ['Metallicity [Fe/H]', 'smet', 'dex'],
  ['Age', 'sage', 'Gyr'], ['Distance', 'dist', 'pc'], ['V magnitude', 'vmag', ''], ['RA (J2000)', 'ra', '°'], ['Dec (J2000)', 'dec', '°']];
// A stored value's error as the page shows it. exoplanet.eu stores an upper limit as lower error = value and upper
// error = 0, the range from 0 to the value: that reads "≤ value", with no error. Both errors 0 means none was
// stored: none is shown. Otherwise ± or − / +. (The planet stubs and pre-rendered pages: setuhq.stubs.is_upper_limit.)
function ctErr(x, lo, hi){
  const has = v => v !== null && v !== undefined;
  if (!has(lo) || !has(hi) || (lo === 0 && hi === 0)) return {limit: false, err: ''};
  if (hi === 0 && lo > 0 && Math.abs(lo - x) <= 1e-9 * Math.max(Math.abs(x), 1e-30)) return {limit: true, err: ''};
  return {limit: false, err: lo === hi ? ` ± ${ctFmt(lo)}` : ` −${ctFmt(lo)} / +${ctFmt(hi)}`};
}
// "≤ " before a stored upper limit, in the table as on the planet's page.
const ctLim = (i, k) => { const P = ct.P; return P[k + '_lo'] && P[k + '_hi'] && ctErr(P[k][i], P[k + '_lo'][i], P[k + '_hi'][i]).limit ? '≤ ' : ''; };
const CT_TYPE = {mass: 'mass_type', radius: 'radius_type'};  // how the value was obtained; "Theoretical" is said so
function ctVal(i, k, unit){
  const P = ct.P, x = P[k][i]; if (x === null || x === undefined) return '<td class="v na">not stored</td>';
  const lo = P[k + '_lo'] ? P[k + '_lo'][i] : null, hi = P[k + '_hi'] ? P[k + '_hi'][i] : null, r = ctErr(x, lo, hi);
  const lim = r.limit ? '<span class="lim" title="Upper limit from the stored range (0 to this value)">≤ </span>' : '';
  const theory = CT_TYPE[k] && P[CT_TYPE[k]] && P[CT_TYPE[k]][i] === 'Theoretical' ? ' <span class="na">· theoretical estimate</span>' : '';
  return `<td class="v">${lim}${ctFmt(x, 6)}${r.err}${unit ? ' ' + unit : ''}${theory}</td>`;
}
function ctTable(i, rows){
  const P = ct.P, limits = rows.some(([, k]) => P[k][i] !== null && P[k][i] !== undefined && P[k + '_lo'] && P[k + '_hi'] && ctErr(P[k][i], P[k + '_lo'][i], P[k + '_hi'][i]).limit);
  return `<table class="pltable"><tbody>${rows.map(([lab, k, u]) => `<tr><th scope="row">${esc(lab)}</th>${ctVal(i, k, u)}</tr>`).join('')}</tbody></table>`
    + (limits ? '<p class="small">≤: an upper limit, from the stored range (0 to the value).</p>' : '');
}
function ctMoll(ra, dec){ // Mollweide, 400 × 200 units, centred on RA 0°, RA increasing to the left
  let lam = -((ra > 180 ? ra - 360 : ra) * Math.PI / 180), phi = dec * Math.PI / 180, th = phi;
  for (let k = 0; k < 30; k++){ const f = 2 * th + Math.sin(2 * th) - Math.PI * Math.sin(phi); th -= f / (2 + 2 * Math.cos(2 * th) + 1e-12); }
  return [200 / Math.PI * lam * Math.cos(th), -100 * Math.sin(th)];
}
function ctSky(i, label){
  const ra = ct.P.ra[i], dec = ct.P.dec[i];
  if (ra === null || dec === null) return '<p>Sky position not stored.</p>';
  const [x, y] = ctMoll(ra, dec);
  return `<svg class="plsky" viewBox="-210 -110 420 240" role="img" aria-label="${esc(label)} on an all-sky map at RA ${ctFmt(ra, 6)}°, Dec ${ctFmt(dec, 6)}°.">
    <ellipse rx="200" ry="100" fill="rgba(255,255,255,.03)" stroke="var(--line-2)"/><line x1="-200" x2="200" y1="0" y2="0" stroke="var(--line)"/><line x1="0" x2="0" y1="-100" y2="100" stroke="var(--line)"/>
    <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="9" fill="none" stroke="var(--cyan)"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="var(--cyan)"/>
    <text x="0" y="124" text-anchor="middle">all sky · centre RA 0° · RA increases to the left</text></svg><p class="mono" style="margin:4px 0 0">RA ${ctFmt(ra, 7)}° · Dec ${ctFmt(dec, 7)}° (J2000)</p>`;
}
function ctWhere(i, star){
  const P = ct.P, links = [];
  if (P.dist[i] !== null) links.push(`<a href="${R(`#/galaxy?focus=${encodeURIComponent(star || P.name[i])}`)}">Show on the Galaxy map ›</a>`);
  links.push(`<a href="${R(`#/sky`)}">The run's sky map ›</a>`);
  const dist = P.dist[i] === null ? 'Distance not stored, so the Galaxy map cannot place it.' : `${ctFmt(P.dist[i], 5)} pc · ${ctFmt(P.dist[i] * 3.261563777, 5)} ly`;
  return ctSky(i, star || P.name[i]) + `<p>${dist}</p><div class="pllinks">${links.join('')}</div>`;
}
function plShow(slug){
  if (!CTM) return;
  ctLoad().then(() => {
    const i = ct.bySlug[slug], note = $('#plnote');
    const body = $$('#route-planet .plgrid, #route-planet .plmore, #route-planet #plref').map(x => x.closest('.plgrid, .plmore, section.card'));
    if (i === undefined){ note.innerHTML = `No planet "${esc(slug)}" in the catalogue. <a href="${R(`#/catalogue?q=${encodeURIComponent(slug.replace(/-/g, ' '))}`)}">Search the Catalogue ›</a>`; note.hidden = false;
      $('#h-planet').textContent = 'Planet not found'; $('#plsub').textContent = ''; $('#plextra').innerHTML = ''; body.forEach(x => { x.hidden = true; }); plShown(false); return; }
    note.hidden = true; body.forEach(x => { x.hidden = false; });
    const P = ct.P, star = P.star[i], cls = mxClassOf(P.radius[i], P.mass[i] !== null ? P.mass[i] : P.msini[i]);
    const clsName = cls === null ? 'class not determinable (no radius or mass stored)' : ['Earth-size', 'Super-Earth', 'Sub-Neptune', 'Neptune-like', 'Gas giant'][cls] + (P.radius[i] === null ? ' (by mass)' : '');
    $('#h-planet').textContent = P.name[i]; if (current === 'planet') pageChrome('planet', new URLSearchParams({id: slug}));
    $('#plsub').innerHTML = `${star ? `<a href="${ctStarHref(star)}">${esc(star)}</a>` : 'host not stored'} · ${esc(CTM.method_label[P.method[i]] || P.method[i])} · discovered ${P.year[i] || 'year not stored'} · ${esc(clsName)}`;
    const ex = $('#plextra'), hero = ex && ex.querySelector('#plhero');
    if (ex && !(hero && hero.dataset.slug === slug)){ ex.innerHTML = ctPlanetExtras(i); if (window.SetuRender) SetuRender.mount(ex); SetuUI.limits(ex); }
    ctSpin(ex);
    $('#plparams').innerHTML = ctTable(i, CT_ROWS) + `<p class="small">Units as stored by ${esc(ct.C.source_short)}. Errors are the stored lower and upper bounds; none is shown where none is stored.</p>`;
    const sibs = star ? ct.byStar[star].slice().sort((a, b) => (P.period[a] ?? 1e99) - (P.period[b] ?? 1e99)) : [i];
    $('#plhost').innerHTML = (star ? `<p><a href="${ctStarHref(star)}">${esc(star)}</a>${P.sptype[i] ? ' · ' + esc(P.sptype[i]) : ''}${P.steff[i] !== null ? ' · ' + ctFmt(P.steff[i]) + ' K' : ''}</p>` : '<p>Host star not stored.</p>')
      + `<ul class="pllist">${sibs.map(j => `<li><a href="${ctPlanetHref(j)}"${j === i ? ' aria-current="page"' : ''}><span>${esc(P.name[j])}</span><span class="mono">${ctFmt(P.period[j], 5) ? ctFmt(P.period[j], 5) + ' d' : 'period —'}</span></a></li>`).join('')}</ul>`;
    $('#plwhere').innerHTML = ctWhere(i, star);
    const ch = CTM.method_chapter[P.method[i]];
    const ref = CTM.refs[P.name[i]];
    $('#plref').innerHTML = `<p>${esc(ct.C.source_short)} lists it as "${esc(P.status[i] || 'status not stored')}"${P.method_raw[i] ? `, found by ${esc(P.method_raw[i])}` : ''}${P.year[i] ? ` in ${P.year[i]}` : ''}; record updated ${esc(P.updated[i] || 'not stored')}.${P.alt[i] ? ` Also known as ${esc(P.alt[i])}.` : ''}</p>
      <p>${ref ? `Discovery paper: <a href="${esc(ref[0])}" rel="noopener">${esc(ref[1])}</a> (from SetuHQ's checked list of notable planets; ${esc(ct.C.source_short)} stores no DOI).` : `${esc(ct.C.source_short)} stores no DOI or reference for the discovery paper, so none is shown.`}</p>
      <div class="pllinks">${ch ? `<a href="${R(`#/methods?ch=${ch}`)}">How ${esc((CTM.method_label[P.method[i]] || '').toLowerCase())} works ›</a>` : ''}</div>${ctSeen(P.name[i], ch ? R('#/methods?ch=' + ch) : '')}`;
    plSystem($('#plsys'), i, current === 'planet');
  }).catch(() => { $('#plnote').textContent = 'The catalogue file could not be loaded here.'; $('#plnote').hidden = false; });
}
// ---------- the portrait, its star, the line-up and the orbits (twins of catalogue.planet_extras and star_extras) ----------
const CT_PIC = '/docs/pictures/', CT_GIF = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', CT_RE = 11.209;
const CT_SPIN = '<div class="stage-ctrls"><button class="btn" type="button" data-spin aria-pressed="false" hidden>Spin</button></div>';
const ctStill = (lk, px) => (CTM.stills || '') + lk + '-' + px + '.webp';
const ctSrc = () => `${ct.C.source_short}, fetched ${String(ct.C.fetched_at).slice(0, 10)}`;
const ctN0 = x => Math.round(x).toLocaleString('en-US');
function ctRow(i){ const o = {}; for (const k of ['radius', 'mass', 'msini', 'a', 'period', 'srad', 'smass', 'steff', 'teq']) o[k] = ct.P[k][i]; return o; }
function ctFig(kind, params, alt, cap, label, still, extra){
  const tag = kind === 'planet' ? `<a class="stage-tag" href="${CT_PIC}">${esc(label)}</a>` : `<span class="stage-tag">${esc(label)}</span>`;
  return `<figure class="stage rfig" data-render="${kind}" data-params='${esc(JSON.stringify(params))}' aria-label="${esc(alt)}"><div class="rbox"><img class="rstill" src="${esc(still)}" width="512" height="512" alt="${esc(alt)}">${extra || ''}</div>${tag}<figcaption class="readout">${cap}</figcaption></figure>`;
}
function ctPortrait(i){
  const P = ct.P, lk = window.SetuRender ? SetuRender.look(ctRow(i)) : {name: null}; if (!lk.name) return '';
  const comp = {envelope: 'an envelope planet', rock: 'a rocky planet', neptune: 'a Neptune-like planet', giant: 'a gas giant', ambiguous: 'a planet of unknown make-up'}[lk.composition];
  const size = lk.rp_re !== null ? `${lk.rp_re.toFixed(2)} Earth radii` : `radius not measured (${lk.mp_me.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1})} Earth masses)`;
  const alt = `Artist's impression of ${P.name[i]}: ${comp}${lk.band ? ` in the ${lk.band} band` : ''}, ${size}, ${lk.teq !== null ? ctN0(lk.teq) + ' K' : 'irradiation not computable'}.`;
  const cap = esc(`Artist's impression · ${lk.composition}${lk.band ? ', ' + lk.band : ', irradiation not computable'} · ${lk.reasons.join(' ')}`) + ` Source: ${esc(ctSrc())}. <a href="${CT_PIC}">How the pictures are drawn ›</a>`;
  const params = {look: lk.name, seed: SetuRender.fnv(P.slug[i]), rp_re: lk.rp_re, teq: lk.teq, animate: false}; if (lk.neutral) params.neutral = true;
  return ctFig('planet', params, alt, cap, "Artist's impression", ctStill(lk.name, 512), CT_SPIN);
}
function ctStarFig(name, teff, srad){
  if (!teff) return '';
  const rad = srad ? `, radius ${srad.toFixed(2)} R☉` : '';
  return ctFig('star', {teff, rstar_rsun: srad, animate: false}, `${name} drawn in its blackbody colour, ${ctN0(teff)} K${rad}.`,
    `${esc(name)} in its blackbody colour: ${ctN0(teff)} K${esc(rad)} (${esc(ctSrc())}). Brightness normalised; the surface texture is decorative.`, 'Model from stored values', CT_GIF);
}
function ctLineup(i){
  const P = ct.P; if (!P.radius[i] || !window.SetuRender) return '';
  const fr = r => r < 6 ? `${r.toFixed(2)} R⊕` : `${(r / CT_RE).toFixed(2)} RJ`;
  const its = [['Earth', 1, 'ref-earth'], ['Neptune', 3.88, 'ref-neptune'], ['Jupiter', CT_RE, 'ref-jupiter']].map(([name, re, look]) => ({name, re, look, ref: 1}))
    .concat([{name: P.name[i], re: Math.round(P.radius[i] * CT_RE * 1000) / 1000, look: SetuRender.look(ctRow(i)).name, focus: 1}]).sort((a, b) => a.re - b.re);
  const big = its[its.length - 1], small = its[0];
  const lis = its.map(q => `<li class="luitem${q.ref ? ' ref' : ''}${q.focus ? ' focus' : ''}" style="--re:${q.re.toFixed(3)}"><img src="${ctStill(q.look, q.re / big.re * 90 > 40 ? 512 : 160)}" width="160" height="160" loading="lazy" alt=""><b>${esc(q.name)}</b><span>${fr(q.re)}</span></li>`).join('');
  return `<section class="pllineup" aria-label="${esc(P.name[i])} in the line-up"><figure class="lineup" data-viz="lineup" aria-label="${esc(P.name[i])} to scale"><div class="stage lustage" style="--rmax:${big.re.toFixed(3)}"><ol class="lurow">${lis}</ol><a class="stage-tag" href="${CT_PIC}">Artist's impression</a></div>`
    + `<figcaption class="skysrc">To scale: one Earth radius is the same width all along the row, so ${esc(big.name)} is ${(big.re / small.re).toFixed(1)} times as wide as ${esc(small.name)}. Each picture is an artist's impression chosen from the measured radius and the computed irradiation; composition is not measured. Earth, Neptune and Jupiter are the Solar System references (only Earth is drawn with oceans). Radii: ${esc(ctSrc())} (1 RJ = 11.209 R⊕). <a href="${CT_PIC}">How the pictures are drawn ›</a></figcaption></figure></section>`;
}
function ctPlanetExtras(i){
  const P = ct.P, pic = ctPortrait(i), st = ctStarFig(P.star[i] || 'The host star', P.steff[i], P.srad[i]);
  return `<div class="plhero${pic ? '' : ' solo'}" id="plhero" data-slug="${esc(P.slug[i])}">${pic}${st}${pic ? '' : '<p class="plnone">No radius or mass stored, so no planet is drawn.</p>'}</div>` + ctLineup(i);
}
// V08 on a star page (twin of viz.orbits.system and html): a from the catalogue or Kepler's third law, depth (Rp/R★)².
function ctOrbits(name, ps){
  const P = ct.P, hex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
  const pl = ps.filter(j => P.period[j] > 0).map(j => {
    let a = P.a[j] > 0 ? P.a[j] : null, src = 'catalogue';
    if (a === null){ a = P.smass[j] > 0 ? Math.cbrt(P.smass[j] * (P.period[j] / 365.25) ** 2) : null; src = "Kepler's third law"; }
    const rp = P.radius[j] > 0 ? P.radius[j] : null, rs = P.srad[j] > 0 ? P.srad[j] : null, k = rp && rs ? rp * 71492 / 695700 / rs : null;
    const lk = window.SetuRender ? SetuRender.look(ctRow(j)).name : null, L = lk && SetuRender.LOOKS[lk];
    return a === null ? null : {name: P.name[j], slug: P.slug[j], P: P.period[j], a, src, re: rp && rp * CT_RE, d: k && k * k * 1e6,
      w: rs ? P.period[j] / Math.PI * Math.asin(Math.min(1, rs * 695700 / 149597870.7 / a)) * 24 : null, c: hex(L ? L.pal[2] : [170, 182, 204])};
  }).filter(Boolean).sort((x, y) => x.P - y.P);
  if (pl.length < 2) return '';
  const short = n => { const t = n.toLowerCase().startsWith(name.toLowerCase()) ? n.slice(name.length).trim() : ''; return t.length > 0 && t.length <= 3 ? t : n; };
  const T = pl[pl.length - 1].P, f2 = (x, d) => x.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
  const params = {teff: P.steff[ps[0]], speed: Math.max(1.6, Math.min(T / 12, pl[0].P / 1.5)), planets: pl.map((q, i) => ({n: short(q.name), P: q.P, a: q.a, d: q.d, w: q.w, c: q.c, f: i ? (i * .4) % 1 : 0}))};
  const label = `The ${pl.length} planets of ${name} seen from above, with their dips over one ${T.toFixed(2)}-day period of the outermost: ` + pl.map(q => `${q.name} every ${q.P.toFixed(2)} d at ${q.a.toFixed(4)} AU` + (q.d ? `, ${f2(q.d, 0)} ppm deep` : '')).join('; ') + '.';
  const rows = pl.map(q => `<tr><th scope="row"><a href="/planets/${esc(q.slug)}/">${esc(q.name)}</a></th><td>${f2(q.P, 4)}</td><td>${q.a.toFixed(4)}${q.src === 'catalogue' ? '' : '*'}</td><td>${q.re ? q.re.toFixed(2) : '—'}</td><td>${q.d ? f2(q.d, 0) : '—'}</td></tr>`).join('');
  return `<figure class="orbits" data-viz="orbits" data-params='${esc(JSON.stringify(params))}'><div class="stage orbstage"><div class="orbbox"><svg class="orbsvg" role="img" aria-label="${esc(label)}"></svg></div><span class="stage-tag">Model from stored values</span><div class="stage-ctrls"><button class="btn" type="button" data-orb="play" aria-pressed="false" hidden>Play</button></div></div>`
    + `<figcaption class="skysrc">The ${esc(name)} system from above: each planet dips the star's light when it crosses the line of sight to the observer. Orbit sizes are the stored semi-major axes (or Kepler's third law from the period and the star's mass); dip depth is (Rp/R★)² from the stored radii. Circular orbits, star and planets not to scale, phases illustrative (no transit times are stored). Source: ${esc(ctSrc())}.</figcaption>`
    + `<details class="orbtable"><summary>The planets: period, orbit and dip depth</summary><div class="tablewrap" tabindex="0" role="region" aria-label="${esc(name)}: period, orbit and dip depth"><table class="pltable"><thead><tr><th scope="col">Planet</th><th scope="col">P (d)</th><th scope="col">a (AU)</th><th scope="col">Rp (R⊕)</th><th scope="col">Depth k² (ppm)</th></tr></thead><tbody>${rows}</tbody></table></div><p class="small">a from ${esc(ct.C.source_short)}; * from Kepler's third law (period and the star's mass). — : radius not stored.</p></details></figure>`;
}
// The portrait turns (0.12 rad/s) through the renderer's scheduler (SetuRender.play): only while on screen and the
// tab is visible, within the page's animation budget and frame governor. Under reduced motion it holds its still
// until Spin is pressed; Pause stops it.
function ctSpin(root){
  const fig = root && root.querySelector('[data-render="planet"]'), btn = fig && fig.querySelector('[data-spin]');
  if (!btn || fig._spin) return; fig._spin = 1;
  const S = {on: false, user: false}, ok = () => fig._sr && fig._sr.cv && window.SetuRender && SetuRender.play;
  const set = () => { btn.hidden = !ok(); btn.textContent = S.on ? 'Pause' : 'Spin'; btn.setAttribute('aria-pressed', String(S.on)); };
  const sync = () => { if (ok()) SetuRender.play(fig, S.on, {user: S.user}); };
  btn.addEventListener('click', () => { S.on = !S.on; S.user = S.on; set(); sync(); });
  let n = 0; const wait = () => { if (ok()){ S.on = !matchMedia('(prefers-reduced-motion: reduce)').matches; set(); sync(); } else if (n++ < 60) setTimeout(wait, 250); };
  wait();
}
// The shared animated system, from planet i's stored values only; the caption says what is not stored.
// Back-links: where SetuHQ itself shows this planet or star (the Transit case, Galaxy tour stops, Methods chapters).
function ctSeen(name, skip){ const ls = (CTM.mentions[name] || []).filter(([, href]) => R(href) !== skip).map(([lab, href]) => `<a href="${esc(R(href))}">${esc(lab)} ›</a>`).join('');
  return ls ? `<div class="pllinks plseen"><span class="pllab">Where SetuHQ shows it:</span>${ls}</div>` : ''; }
function plSystem(fig, i, on){
  const P = ct.P, pimen = typeof S !== 'undefined' && S.planet && P.name[i] === S.planet;
  const p = {name: P.name[i], star_teff: P.steff[i], star_radius: P.srad[i], radius: P.radius[i], semi_major_axis: P.a[i], orbital_period: P.period[i],
    inclination: P.incl[i], impact_parameter: P.b[i], mass: P.mass[i], mass_sini: P.msini[i], eccentricity: P.e[i]};
  return mxSystemView(fig, p, {dip: pimen && MX && MX.lead_dip ? {pts: MX.lead_dip.pts} : null, on, source: ct.C.source_short});
}
function stShow(slug){
  if (!CTM) return;
  ctLoad().then(() => {
    const name = ct.starBySlug[slug], note = $('#stnote');
    const body = $$('#route-star .plgrid, #route-star .plmore');
    if (!name){ note.innerHTML = `No star "${esc(slug)}" in the catalogue. <a href="${R(`#/catalogue?q=${encodeURIComponent(slug.replace(/-/g, ' '))}`)}">Search the Catalogue ›</a>`; note.hidden = false;
      $('#h-star').textContent = 'Star not found'; $('#stsub').textContent = ''; $('#stextra').innerHTML = ''; body.forEach(x => { x.hidden = true; }); return; }
    note.hidden = true; body.forEach(x => { x.hidden = false; });
    const P = ct.P, ps = ct.byStar[name].slice().sort((a, b) => (P.period[a] ?? 1e99) - (P.period[b] ?? 1e99)), i = ps[0];
    $('#h-star').textContent = name; if (current === 'star') pageChrome('star', new URLSearchParams({id: slug}));
    const teff = P.steff[i];
    const [cl, row] = teff !== null ? mxClass(teff) : [null, null];
    $('#stsub').textContent = `${ps.length} planet${ps.length === 1 ? '' : 's'} in ${ct.C.source_short}` + (P.sptype[i] ? ` · stored type ${P.sptype[i]}` : '') + (cl ? ` · class ${cl} from Teff (nearest ${row})` : '');
    const pc = P.dist[i], ly = pc * 3.261563777, k = 10 ** Math.max(0, String(Math.trunc(ly)).length - 2);
    $('#stlight').textContent = pc > 0 ? `The light from this star left it about ${Math.max(1, Math.round(ly / k) * k).toLocaleString('en-GB')} years ago (distance ${+pc.toPrecision(6)} pc, ${ctSrc()}).` : '';
    $('#stparams').innerHTML = ctTable(i, CT_STAR_ROWS) + (P.salt[i] ? `<p class="small">Also known as ${esc(P.salt[i])}.</p>` : '');
    const thumb = j => { const lk = window.SetuRender && SetuRender.look(ctRow(j)).name; return lk ? `<img class="plthumb" src="${ctStill(lk, 160)}" width="40" height="40" loading="lazy" alt="">` : '<span class="plthumb none" aria-hidden="true"></span>'; };
    $('#stplanets').innerHTML = `<ul class="pllist plthumbs">${ps.map(j => `<li><a href="${ctPlanetHref(j)}">${thumb(j)}<span>${esc(P.name[j])}</span><span class="mono">${esc(CTM.method_label[P.method[j]] || P.method[j])} · ${P.year[j] || '—'}</span></a></li>`).join('')}</ul><p class="small">Pictures: artist's impressions from the measured radius and irradiation. <a href="${CT_PIC}">How the pictures are drawn ›</a></p>`;
    const sx = $('#stextra'), sh = sx && sx.querySelector('#sthero');
    if (sx && !(sh && sh.dataset.star === name)){ const f = ctStarFig(name, P.steff[i], P.srad[i]) + ctOrbits(name, ps); sx.innerHTML = f ? `<div class="sthero" id="sthero" data-star="${esc(name)}">${f}</div>` : ''; if (window.SetuRender) SetuRender.mount(sx); SetuUI.limits(sx); }
    if (window.SetuOrbits) SetuOrbits.wire(sx);
    $('#stwhere').innerHTML = ctWhere(i, name) + ctSeen(name, R('#/sky'));
    if (typeof vaForStar === 'function') vaForStar(P.salt[i]);
    // The system view with one of its planets (the innermost first); the picker switches planet.
    const pick = $('#stpick');
    pick.innerHTML = ps.map(j => `<option value="${j}">${esc(P.name[j])}</option>`).join('');
    pick.onchange = () => plSystem($('#stsys'), Number(pick.value), current === 'star');
    plSystem($('#stsys'), i, current === 'star');
  }).catch(() => { $('#stnote').textContent = 'The catalogue file could not be loaded here.'; $('#stnote').hidden = false; });
}
function plShown(r){ for (const [id, route] of [['#plsys', 'planet'], ['#stsys', 'star']]){ const fig = $(id); if (fig && fig._mx){ fig._mx.on = r === route; if (fig._mx.on) mxKick(fig._mx); } } }

// ---------- global search: planets, stars, chapters and sections ----------
const gs = {sel: 0, items: []};
function gsIndexStatic(){
  const out = [];
  for (const n of D.nav){ out.push({kind: 'section', label: n.label, href: n.href}); for (const [label, h] of (D.subnav[n.id] || [])) if (label !== n.label) out.push({kind: n.label, label, href: R(h)}); }
  if (MX) for (const id of MX.chapters) out.push({kind: 'chapter', label: MX.labels[id], href: R('#/methods?ch=' + id)});
  return out;
}
function gsSearch(q){
  q = q.trim().toLowerCase();
  const st = gsIndexStatic().filter(x => !q || x.label.toLowerCase().includes(q)), res = [];
  if (q && ct.P){
    const P = ct.P, starts = [], has = [];
    for (let i = 0; i < P.name.length && starts.length < 40; i++){ const n = P.name[i].toLowerCase(), a = (P.alt[i] || '').toLowerCase(); if (n.startsWith(q)) starts.push(i); else if ((n.includes(q) || a.includes(q)) && has.length < 40) has.push(i); }
    for (const i of starts.concat(has).slice(0, 12)) res.push({kind: 'planet', label: P.name[i], sub: P.star[i] || '', href: ctPlanetHref(i), teff: P.steff[i], cls: ctCls(i)});
    let n = 0; for (const s of ct.C.stars.names){ if (s.toLowerCase().includes(q)){ res.push({kind: 'star', label: s, sub: `${ct.byStar[s].length} planet${ct.byStar[s].length === 1 ? '' : 's'}`, href: ctStarHref(s), teff: P.steff[ct.byStar[s][0]]}); if (++n >= 6) break; } }
  }
  if (q && typeof vaSearch === 'function') res.push(...vaSearch(q));
  return st.slice(0, q ? 6 : 20).concat(res);
}
function gsRender(){
  const q = $('#gsq').value; gs.items = gsSearch(q); gs.sel = Math.min(gs.sel, Math.max(0, gs.items.length - 1));
  $('#gsresults').innerHTML = gs.items.length ? gs.items.map((x, k) => `<li role="option" id="gs-${k}" aria-selected="${k === gs.sel}"><a href="${x.href}" tabindex="-1"><span>${x.kind === 'planet' || x.kind === 'star' ? ctDot(x.teff) : ''}${esc(x.label)}${x.cls ? ` <span class="ctcls">${esc(x.cls)}</span>` : ''}${x.sub ? ` <span class="kind">${esc(x.sub)}</span>` : ''}</span><span class="kind">${x.kind}</span></a></li>`).join('')
    : `<li class="gshint">${ct.P ? 'Nothing matches.' : 'Loading the catalogue…'}</li>`;
  $('#gsq').setAttribute('aria-activedescendant', gs.items.length ? 'gs-' + gs.sel : '');
  const cur = $('#gs-' + gs.sel); if (cur) cur.scrollIntoView({block: 'nearest'});
}
function gsOpen(){
  const dlg = $('#gsearch'); if (!dlg) return;
  if (!dlg.open) dlg.showModal();
  $('#gsq').value = ''; gs.sel = 0; gsRender(); $('#gsq').focus();
  if (CTM) ctLoad().then(gsRender).catch(() => {});
  if (typeof VA !== 'undefined' && VA) vaLoad().then(gsRender).catch(() => {});
}
if ($('#gsearch')){
  $('#gsearchbtn').addEventListener('click', gsOpen);
  $('#gsq').addEventListener('input', () => { gs.sel = 0; gsRender(); });
  $('#gsq').addEventListener('keydown', e => {
    // Escape closes the dialog whatever is typed (a search field would otherwise only clear itself).
    if (e.key === 'Escape'){ e.preventDefault(); $('#gsearch').close(); return; }
    if (e.key === 'ArrowDown'){ gs.sel = Math.min(gs.items.length - 1, gs.sel + 1); gsRender(); e.preventDefault(); }
    else if (e.key === 'ArrowUp'){ gs.sel = Math.max(0, gs.sel - 1); gsRender(); e.preventDefault(); }
    else if (e.key === 'Enter' && gs.items[gs.sel]){ e.preventDefault(); $('#gsearch').close(); navTo(gs.items[gs.sel].href); }
  });
  $('#gsresults').addEventListener('click', e => { if (e.target.closest('a')) $('#gsearch').close(); });
  $('#gsearch').addEventListener('click', e => { if (e.target === $('#gsearch')) $('#gsearch').close(); });
  document.addEventListener('keydown', e => {
    if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))){ e.preventDefault(); gsOpen(); }
  });
}

// ---------- everything that dims: the sweep catalogue (#/variables) ----------
const VA = D.sweep || null;
const VA_NOISE = new Set(VA ? VA.noise_like : []);
// A class that does not exceed its null keeps its rule's name but is not presented as a finding: the planet
// candidates become "planet-candidate rule" until they exceed their control.
const VA_LABEL = VA ? Object.fromEntries(VA.classes.map(c => [c.id, c.id === 'planet_candidate' && VA_NOISE.has(c.id) ? 'Planet-candidate rule' : c.label])) : {};
// Classes that exceed their null first, then the noise-like ones, then unclassified (sweep_meta's order).
const VA_CLASSES = VA ? VA.order : [];
const VA_CONF = ['high', 'medium', 'low', 'n/a'];
const va = {E: null, C: null, loading: null, view: null, shown: 60, byId: {}, byTic: {}, cov: {}, bound: false, rendered: false};
function vaLoad(){
  if (!VA) return Promise.reject(new Error('no sweep'));
  if (!va.loading) va.loading = fetch(VA.json).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(C => {
    va.C = C; va.E = C.entries;
    for (const e of va.E){ va.byId[e.id] = e; (va.byTic[e.tic] = va.byTic[e.tic] || []).push(e); }
    for (const r of C.coverage) (va.cov[r.tic] = va.cov[r.tic] || []).push(r);
    return C;
  });
  return va.loading;
}
// URL: class, conf (lists), q, toi=1, sort, tic, id. Defaults are left out.
function decodeVarView(p){
  const cl = (p.get('class') || '').split(','), cf = (p.get('conf') || '').split(',');
  const tic = /^\d{1,12}$/.test(p.get('tic') || '') ? Number(p.get('tic')) : null;
  return {cls: VA_CLASSES.filter(c => cl.includes(c)), conf: VA_CONF.filter(c => cf.includes(c)), q: (p.get('q') || '').slice(0, 80),
          toi: p.get('toi') === '1', sort: VA && VA.sorts.includes(p.get('sort')) ? p.get('sort') : 'class', tic, id: (p.get('id') || '').slice(0, 120) || null};
}
function encodeVarView(v){
  const out = [];
  if (v.cls.length) out.push('class=' + v.cls.join(','));
  if (v.conf.length) out.push('conf=' + v.conf.map(encodeURIComponent).join(','));
  if (v.q) out.push('q=' + encodeURIComponent(v.q));
  if (v.toi) out.push('toi=1');
  if (v.sort !== 'class') out.push('sort=' + v.sort);
  if (v.tic !== null) out.push('tic=' + v.tic);
  if (v.id) out.push('id=' + encodeURIComponent(v.id));
  return out.join('&');
}
// The filter (tests compare it with everything.variables_filter in Python).
function vaFilter(E, v){
  let q = (v.q || '').trim().toLowerCase(); if (q.startsWith('tic')) q = q.slice(3).trim();
  const cls = new Set(v.cls), conf = new Set(v.conf);
  return E.filter(e => (!cls.size || cls.has(e.class)) && (!conf.size || conf.has(e.confidence)) && (!v.toi || e.toi_match)
    && (!q || String(e.tic).includes(q) || (e.toi_match || '').toLowerCase().includes(q) || (e.credit || []).some(c => c.name.toLowerCase().includes(q))));
}
function vaSort(rows, key){
  const by = {class: e => [VA_CLASSES.indexOf(e.class), e.tic, e.t_center || 0], tic: e => [e.tic, e.t_center || 0], time: e => [e.t_center || 0, e.tic],
    depth: e => [-(e.depth_ppm ?? e.amplitude_ppm ?? -1e99), e.tic], confidence: e => [VA_CONF.indexOf(e.confidence), VA_CLASSES.indexOf(e.class), e.tic]}[key];
  return rows.slice().sort((a, b) => { const x = by(a), y = by(b); for (let i = 0; i < x.length; i++){ if (x[i] < y[i]) return -1; if (x[i] > y[i]) return 1; } return 0; });
}
const vaNum = (x, d) => x === null || x === undefined ? '—' : Number(x).toLocaleString('en-GB', {maximumFractionDigits: d, minimumFractionDigits: d});
const vaTicHref = (tic, id) => R(`#/variables?tic=${tic}` + (id ? '&id=' + encodeURIComponent(id) : ''));
function vaFigures(e){
  const bits = e.kind === 'variability' ? ['whole sector'] : [`${esc(e.time_unit || 'BTJD')} ${vaNum(e.t_center, 3)}`];
  if (e.kind === 'variability') bits.push(`period ${vaNum(e.period_days, 4)} d`, `semi-amplitude ${vaNum(e.amplitude_ppm, 0)} ppm`);
  else {
    bits.push(`${vaNum(e.duration_hours, 1)} h`);
    if (e.kind === 'dip') bits.push(`${vaNum(e.depth_ppm, 0)} ppm deep`, `SNR ${vaNum(e.snr, 1)}`); else bits.push(`+${vaNum(e.amplitude_ppm, 0)} ppm`, `${vaNum(e.peak_sigma, 1)}σ`);
    if (e.period_days) bits.push(`P ${vaNum(e.period_days, 4)} d (${e.n_transits || 0} transits)`);
  }
  return bits.join(' · ');
}
// The old project name in stored credits reads as SetuHQ (names.public_name).
const PUB = n => /^\s*exoplan\s*$/i.test(String(n)) ? 'SetuHQ' : String(n);
function vaCredit(e){ return `<p class="vacredit">Searched by ${(e.credit || []).map(c => `<b>${esc(PUB(c.name))}</b>`).join(', ') || 'not stored'}</p>`; }
function vaDetail(e){
  const kind = Object.fromEntries((e.panel || []).map(p => [p.id, p.kind]));
  const w = e.weights || {};
  const ids = Object.keys(w).sort();
  const marks = e.marks || [];
  const mrows = ids.map(id => { const ms = marks.filter(m => m[0] === id);
    return `<tr><th scope="row">${nameWithId(id)} ${kindTag(kind[id])}</th><td class="num mono">${vaNum(w[id], 2)}</td><td class="mono">${ms.length ? ms.map(m => `${vaNum(m[1], 3)}–${vaNum(m[2], 3)}${m[3] ? ' ✓' : ''}`).join('<br>') : 'no mark'}</td></tr>`; }).join('');
  const marksHTML = e.kind === 'dip' ? `<h3>Marks and weights</h3><div class="tablewrap" tabindex="0" role="region" aria-label="Marks by reviewer"><table class="vatable"><thead><tr><th scope="col">Reviewer</th><th scope="col" class="num">Weight</th><th scope="col">Marks (✓ counted)</th></tr></thead><tbody>${mrows}</tbody></table></div>`
    + (e.shares && Object.keys(e.shares).length ? `<p>Panel's weighted labels: ${Object.entries(e.shares).map(([k, v]) => `${esc(k.replace(/_/g, ' '))} ${Math.round(v * 100)}%`).join(' · ')}</p>` : '')
    : `<p>${esc(e.note || '')}</p>`;
  const sentinels = ids.filter(id => isSentinel(kind[id]));
  const words = (e.words || []).length ? `<h3>The Sentinels' own words</h3>` + e.words.map(x => `<blockquote class="vawords">${esc(x.rationale)}<cite>${esc(NAME(x.reviewer))} · ${esc(x.label.replace('_', ' '))}${x.reason ? ' · ' + esc(x.reason.replace(/_/g, ' ')) : ''}</cite></blockquote>`).join('')
    : (e.kind === 'dip' ? `<p class="muted">${sentinels.length ? 'The Sentinels left no words on this subject.' : 'No Sentinel reviewed this star: this sweep ran the Probes only, which give no reasons.'}</p>` : '');
  const flags = (e.flags || []).length ? `<p>Vetting flags: <span class="mono">${e.flags.map(esc).join(', ')}</span> · ${e.passed ? 'passed vetting' : 'failed vetting'}</p>` : (e.kind === 'dip' ? `<p>No vetting flags · ${e.passed ? 'passed vetting' : 'failed vetting'}</p>` : '');
  const prov = `<p class="vaprov">id ${esc(e.id)}${e.subject_id ? ' · subject ' + esc(e.subject_id) : ''}<br>light curve sha256 ${esc(e.file_sha256 || 'not stored')}<br>code ${esc(String(e.code || '').slice(0, 16))}… · config ${esc(String(e.config_sha256 || '').slice(0, 16))}…${(e.credit || []).map(c => `<br>source ${esc(c.source)}${c.bundle ? ' (bundle ' + esc(c.bundle) + ')' : ''}`).join('')}</p>`;
  return `<details><summary>Marks, weights, words and provenance</summary><div>${flags}${marksHTML}${words}<h3>Provenance</h3>${prov}</div></details>`;
}
function vaCard(e, sel){
  const toi = e.toi_match ? ` · matches TOI ${esc(e.toi_match)}${e.toi_disposition ? ' (' + esc(e.toi_disposition) + ')' : ''}` : '';
  const why = e.class === 'unclassified' ? esc(e.why || '') : (e.cues || []).map(c => esc(c.text)).join('; ');
  const unc = VA_NOISE.has(e.class) ? ` <span class="tag vanoisetag">${esc(VA.noise_text)}</span>` : e.class === 'planet_candidate' ? ' ' + UNC : '';
  return `<article class="vaent${sel ? ' sel' : ''}" id="va-${esc(e.id)}" style="--c:${VA.colours[e.class]}" aria-label="${esc(VA_LABEL[e.class])}, TIC ${e.tic}">
    <header><span class="vacls"><i aria-hidden="true"></i>${esc(VA_LABEL[e.class])}</span><span class="tag">confidence: ${esc(e.confidence)}</span>${unc}
      <a href="${vaTicHref(e.tic, e.id)}">TIC ${e.tic}</a><span class="muted">sector ${e.sector} · ${esc(e.kind)}${toi}</span></header>
    <p class="vanum mono">${vaFigures(e)}</p>${vaStrip(e)}<p>${why}</p>${vaDetail(e)}${vaCredit(e)}</article>`;
}
// Each dip's strip: the subject's time span, the dip's window, and every reviewer's stored marks, one lane each. It
// answers on hover and on the arrow keys (S06): how many reviewers marked that moment.
function vaStrip(e){
  const ms = e.marks || [], a = e.t_start, b = e.t_end;
  if (e.kind !== 'dip' || !ms.length || a === null || a === undefined || !(b > a)) return '';
  const ids = [...new Set(ms.map(m => m[0]))].sort(), W = 600, lane = 5, H = 8 + ids.length * (lane + 2), cl = t => Math.max(a, Math.min(b, t));
  // A span [t0, t1] inside the strip: at least `min` wide, and never past either end.
  const span = (t0, t1, min) => { const w = Math.min(W, Math.max(min, (cl(t1) - cl(t0)) / (b - a) * W)), x = Math.min(W - w, (cl(t0) - a) / (b - a) * W); return `x="${x.toFixed(1)}" width="${w.toFixed(1)}"`; };
  const win = e.t_center !== null && e.duration_hours ? `<rect ${span(e.t_center - e.duration_hours / 48, e.t_center + e.duration_hours / 48, 1)} y="0" height="${H}" fill="var(--c)" opacity=".22"/>` : '';
  const bars = ms.map(m => `<rect ${span(m[1], m[2], 1.5)} y="${4 + ids.indexOf(m[0]) * (lane + 2)}" height="${lane}" rx="1.5" fill="${m[3] ? 'var(--ink)' : 'var(--ink-3)'}"/>`).join('');
  return `<div class="vastrip"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" data-a="${a}" data-b="${b}" aria-label="Marks over the subject, ${esc(e.time_unit || 'BTJD')} ${vaNum(a, 2)} to ${vaNum(b, 2)}: ${ids.length} reviewer${ids.length === 1 ? '' : 's'} marked it; the shaded band is the dip's window.">${win}${bars}</svg><p class="xread"></p></div>`;
}
function vaXhair(root){
  if (!window.SetuUI || !SetuUI.crosshair) return;
  root.querySelectorAll('.vastrip svg').forEach(svg => {
    const card = svg.closest('.vaent'), e = va.byId[card.id.slice(3)]; if (!e) return;
    const a = +svg.dataset.a, b = +svg.dataset.b, xs = Array.from({length: 121}, (_, k) => a + (b - a) * k / 120), n = new Set(e.marks.map(m => m[0])).size;
    SetuUI.crosshair(svg, {x0: a, x1: b, xs, readout: svg.parentElement.querySelector('.xread'), fmt: i => { const t = xs[i], k = new Set(e.marks.filter(m => m[1] <= t && t <= m[2]).map(m => m[0])).size;
      return `${e.time_unit || 'BTJD'} ${vaNum(t, 3)} · ${k} of ${n} reviewer${n === 1 ? '' : 's'} marked this moment`; }});
  });
}
function vaObject(tic, id){
  const box = $('#vaobj'), es = va.byTic[tic] || [], cov = va.cov[tic] || [];
  box.hidden = false;
  const name = (VA.tic_names || {})[tic];
  $('#h-vaobj').textContent = `TIC ${tic}` + (name ? ` · ${name}` : '');
  if (!cov.length){ $('#vaobjbody').innerHTML = `<p>TIC ${tic} is not in the sweep yet.</p><div class="pllinks"><a class="vaall" href="${R(`#/variables`)}">All entries ›</a></div>`; return; }
  const r = cov[0], rej = r.rejected || {};
  const dl = [['Position (RA, Dec)', r.ra !== null && r.ra !== undefined ? `${vaNum(r.ra, 3)}°, ${vaNum(r.dec, 3)}°` : 'not stored'], ['TESS magnitude', vaNum(r.tmag, 2)],
    ['Sectors searched', cov.filter(x => x.status === 'searched').map(x => x.sector).join(', ') || 'none'], ['Searched by', cov.flatMap(x => x.searched_by).map(PUB).join(', ') || '—'],
    ['Light-curve points', vaNum(r.n_points, 0)], ['Consensus dips', vaNum(r.n_dips, 0)],
    ['Rejected', `${rej.below_consensus ?? 0} mark clusters below consensus · ${rej.failed_vetting ?? 0} dips failed vetting`],
    ['Known TOIs on this TIC', (r.tois || []).map(t => `${t.toi}${t.disposition ? ' (' + t.disposition + ')' : ''}`).join(', ') || 'none in the cached TOI table']];
  $('#vaobjbody').innerHTML = `<dl class="vaobjgrid">${dl.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`
    + (name ? `<div class="pllinks">${objLink('star', name, name + ' in the planet catalogue ›')}</div>` : '')
    + `<p class="small">${es.length} entr${es.length === 1 ? 'y' : 'ies'} below, every one shown. Light curve sha256 <span class="mono">${esc(r.file_sha256 || 'not stored')}</span>.</p><div class="pllinks"><a class="vaall" href="${R(`#/variables`)}">All entries ›</a></div>`;
}
function vaApply(){
  if (!va.E || !va.view) return;
  const v = va.view;
  $$('#vaclasses [data-vc]').forEach(b => b.setAttribute('aria-pressed', String(v.cls.includes(b.dataset.vc))));
  $$('#vaconf [data-vf]').forEach(b => b.setAttribute('aria-pressed', String(v.conf.includes(b.dataset.vf))));
  $('#vatoi').setAttribute('aria-pressed', String(v.toi));
  if ($('#vaq').value !== v.q) $('#vaq').value = v.q;
  $('#vasort').value = v.sort;
  let tic = v.tic;
  if (tic === null && v.id && va.byId[v.id]) tic = va.byId[v.id].tic;
  if (tic !== null){ vaObject(tic, v.id); } else { $('#vaobj').hidden = true; }
  // Opening a TIC from a link moves the focus to its heading, so a keyboard or screen-reader user lands on it.
  const opened = tic !== null && va.lastTic !== tic;
  va.lastTic = tic;
  const rows = tic !== null ? vaSort(va.byTic[tic] || [], 'time') : vaSort(vaFilter(va.E, v), v.sort);
  va.rows = rows;
  const shown = tic !== null ? rows : rows.slice(0, va.shown);
  $('#valist').innerHTML = shown.map(e => vaCard(e, e.id === v.id)).join('');
  vaXhair($('#valist'));
  $('#vaempty').hidden = rows.length > 0 || tic !== null;
  $('#vamore').hidden = shown.length >= rows.length;
  $('#vamore').textContent = `Show ${Math.min(60, rows.length - shown.length)} more of ${rows.length - shown.length}`;
  $('#vacount').textContent = tic !== null ? `TIC ${tic}: ${rows.length} of ${va.E.length.toLocaleString('en-GB')} entries` : `Showing ${shown.length.toLocaleString('en-GB')} of ${rows.length.toLocaleString('en-GB')} matching · ${va.E.length.toLocaleString('en-GB')} entries in all`;
  if (v.id){ const el = document.getElementById('va-' + v.id); if (el){ const d = el.querySelector('details'); if (d) d.open = true; } }
  if (opened){ $('#h-vaobj').focus({preventScroll: true}); $('#vaobj').scrollIntoView({block: 'start'}); }
}
function syncVarURL(push){ if (current === 'variables' && va.view) setHash('#/variables' + (encodeVarView(va.view) ? '?' + encodeVarView(va.view) : ''), !!push); }
function vaSet(change){ va.view = {...va.view, ...change}; va.shown = 60; vaApply(); syncVarURL(true); }
function vaBind(){
  if (va.bound) return; va.bound = true;
  $('#vaclasses').addEventListener('click', e => { const b = e.target.closest('[data-vc]'); if (!b) return; const k = b.dataset.vc, on = va.view.cls.includes(k);
    vaSet({cls: VA_CLASSES.filter(c => c === k ? !on : va.view.cls.includes(c)), tic: null, id: null}); say($('#vacount').textContent); });
  $('#vaconf').addEventListener('click', e => { const b = e.target.closest('[data-vf]'); if (!b) return; const k = b.dataset.vf, on = va.view.conf.includes(k);
    vaSet({conf: VA_CONF.filter(c => c === k ? !on : va.view.conf.includes(c)), tic: null, id: null}); });
  $('#vatoi').addEventListener('click', () => vaSet({toi: !va.view.toi, tic: null, id: null}));
  $('#vasort').addEventListener('change', e => vaSet({sort: e.target.value}));
  let qt = null;
  $('#vaq').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { va.view = {...va.view, q: e.target.value.slice(0, 80), tic: null, id: null}; va.shown = 60; vaApply(); syncVarURL(false); }, 200); });
  $('#vareset').addEventListener('click', () => { va.view = decodeVarView(new URLSearchParams()); va.shown = 60; vaApply(); syncVarURL(true); });
  $('#vamore').addEventListener('click', () => { const n = va.shown; va.shown += 60; vaApply(); const el = $$('#valist .vaent')[n]; if (el){ const a = el.querySelector('a'); if (a) a.focus(); } });
  $('#vacsv').addEventListener('click', vaCsv);
}
function vaCsv(){
  const cols = ['id', 'class', 'confidence', 'kind', 'tic', 'sector', 't_center', 'duration_hours', 'depth_ppm', 'amplitude_ppm', 'period_days', 'toi_match', 'cues', 'credit', 'file_sha256', 'code'];
  const q = x => { const s = x === null || x === undefined ? '' : String(x); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const rows = (va.rows || []).map(e => cols.map(c => c === 'cues' ? (e.class === 'unclassified' ? e.why : (e.cues || []).map(x => x.text).join('; ')) : c === 'credit' ? (e.credit || []).map(x => x.name).join('; ') : e[c]).map(q).join(','));
  const blob = new Blob([cols.join(',') + '\n' + rows.join('\n') + '\n'], {type: 'text/csv'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'setuhq-everything-that-dims.csv'; document.body.appendChild(a); a.click(); a.remove();
  say(`Downloading ${rows.length} entries as CSV.`);
}
function renderVariables(){
  if (!VA) return;
  vaLoad().then(() => { va.rendered = true; vaBind(); vaApply(); }).catch(() => { $('#vacount').textContent = `The sweep catalogue (${VA.json}) could not be loaded here.`; });
}
function applyVariables(v){ va.view = v; if (va.rendered) vaApply(); }
// The global search: a TIC the sweep searched ("tic 2615", "26151"), and the classes by name.
function vaSearch(q){
  if (!VA) return [];
  const out = [];
  for (const c of VA.classes) if (c.label.toLowerCase().includes(q)) out.push({kind: 'class', label: c.label, sub: `${VA.counts.by_class[c.id].toLocaleString('en-GB')} in the sweep`, href: R('#/variables?class=' + c.id)});
  const d = q.replace(/^tic\s*/, '');
  if (va.C && /^\d{2,}$/.test(d)){
    let n = 0;
    for (const t of Object.keys(va.cov)){ if (t.startsWith(d)){ const es = va.byTic[t] || []; out.push({kind: 'TIC', label: 'TIC ' + t, sub: `sweep · ${es.length} entr${es.length === 1 ? 'y' : 'ies'}`, href: vaTicHref(t)}); if (++n >= 6) break; } }
  }
  return out;
}
// A star page: the sweep's entries for any TIC the star's stored alternate names list.
function vaForStar(salt){
  const box = $('#stsweep'); if (!box) return;
  box.hidden = true;
  if (!VA) return;
  const tics = [...String(salt || '').matchAll(/TIC[ -]?(\d+)/g)].map(m => Number(m[1]));
  if (!tics.length) return;
  vaLoad().then(() => {
    const hit = tics.filter(t => va.cov[t]);
    if (!hit.length) return;
    $('#stsweepbody').innerHTML = hit.map(t => { const es = va.byTic[t] || [], r = va.cov[t][0];
      return `<p><a href="${vaTicHref(t)}">TIC ${t} in the sweep ›</a> ${es.length} entr${es.length === 1 ? 'y' : 'ies'} (${es.map(e => VA_LABEL[e.class]).filter((x, i, a) => a.indexOf(x) === i).join(', ') || 'none'}); searched by ${esc(va.cov[t].flatMap(x => x.searched_by).map(PUB).join(', '))}, sector ${va.cov[t].map(x => x.sector).join(', ')}.</p>`; }).join('');
    box.hidden = false;
  }).catch(() => {});
}

// ---------- the Learn path: optional, any visit counts, progress kept in this browser ----------
const LEARN = D.learn || [];
const LEARN_KEY = 'setuhq-learn';
function learnRead(){
  try { const s = getStorage(), raw = s && s.getItem(LEARN_KEY), v = raw ? JSON.parse(raw) : null;
    if (v && Array.isArray(v.seen)) return {seen: v.seen.filter(id => LEARN.some(x => x.id === id)), active: !!v.active}; } catch (e) { /* blocked or malformed */ }
  return {seen: [], active: false};
}
const learn = learnRead();
function learnSave(){ try { const s = getStorage(); if (s) s.setItem(LEARN_KEY, JSON.stringify({v: 1, seen: learn.seen, active: learn.active})); } catch (e) { /* storage blocked: progress lasts this visit */ } }
// Which step a route is: a Methods chapter, the Transit case, the Galaxy or the Catalogue.
function learnStepOf(p){
  if (!p) return null;
  if (p.route === 'methods') return 'ch:' + (MX && MX.chapters.includes(p.params.get('ch')) ? p.params.get('ch') : (MX ? MX.chapters[0] : ''));
  return ['transit', 'galaxy', 'catalogue'].includes(p.route) ? p.route : null;
}
function learnNext(){ return LEARN.find(x => !learn.seen.includes(x.id)) || null; }
function learnRender(){
  const card = $('#learncard'), n = LEARN.length, k = learn.seen.length;
  if (card){
    const nx = learnNext();
    $('#learnfill').style.width = (k / n * 100) + '%';
    card.querySelector('.learnmeter').setAttribute('aria-valuenow', String(k));
    $('#learncount').textContent = `${k} of ${n} visited` + (k === n ? ' · path complete' : '');
    const go = $('#learngo');
    go.textContent = !k ? 'Start the path' : nx ? `Continue: ${nx.label}` : 'Start again from step 1';
    go.setAttribute('href', R((nx || LEARN[0]).href));
    $$('#learnsteps li').forEach(li => { const seen = learn.seen.includes(li.dataset.step); li.dataset.seen = seen ? '1' : '0'; li.dataset.next = nx && nx.id === li.dataset.step ? '1' : '0';
      li.querySelector('.lseen').textContent = seen ? ', visited' : ', not visited yet'; });
  }
}
// The path bar: shown on a step's page once the viewer has started the path, with Back, Next and Leave.
function learnBar(step){
  const bar = $('#learnbar'), i = LEARN.findIndex(x => x.id === step), on = learn.active && i >= 0;
  bar.hidden = !on; document.body.classList.toggle('learning', on);
  if (!on) return;
  $('#learnpos').innerHTML = `<span class="lpre">Learn path · </span>${i + 1} of ${LEARN.length} · ${esc(LEARN[i].label)}`;
  const prev = LEARN[i - 1], next = LEARN[i + 1];
  // Never hide the button that has focus: on step 1, Back hands focus to Next first.
  if (!prev && document.activeElement === $('#learnprev')) $('#learnnext').focus();
  $('#learnprev').hidden = !prev; if (prev) $('#learnprev').setAttribute('href', R(prev.href));
  $('#learnnext').innerHTML = next ? `Next<span class="lnt">: ${esc(next.label)}</span> ›` : 'Finish ›';
  $('#learnnext').setAttribute('aria-label', next ? `Next: ${next.label}` : 'Finish the path'); $('#learnnext').setAttribute('href', next ? R(next.href) : '/');
}
function learnVisit(p){
  const step = learnStepOf(p);
  if (step && !learn.seen.includes(step)){ learn.seen.push(step); learnSave(); }
  if (p && p.route === 'overview') learnRender();
  learnBar(step);
}
if ($('#learncard')){
  $('#learngo').addEventListener('click', () => { learn.active = true; if (learn.seen.length === LEARN.length) learn.seen = []; learnSave(); });
  $('#learnsteps').addEventListener('click', e => { if (e.target.closest('a')){ learn.active = true; learnSave(); } });
  $('#learnreset').addEventListener('click', () => { learn.seen = []; learn.active = false; learnSave(); learnRender(); say('Learn path progress cleared.'); });
}
if ($('#learnbar')){
  // Leaving hides the bar, so focus moves to the page's heading (or main), not to <body>.
  $('#learnleave').addEventListener('click', () => { learn.active = false; learnSave(); learnBar(null);
    const h = $(`#route-${current} h1`) || $('#main'); if (h){ if (!h.hasAttribute('tabindex')) h.setAttribute('tabindex', '-1'); h.focus({preventScroll: true}); }
    say('Left the Learn path. Your progress is kept.'); });
  $('#learnnext').addEventListener('click', () => { if ($('#learnnext').getAttribute('href') === '/'){ learn.active = false; learnSave(); } });
}

// ---------- Mission Control: tiling panes linked by one selected star ----------
const MC_PANES = D.mission ? D.mission.panes.map(p => p[0]) : [];
const MC_LABEL = D.mission ? Object.fromEntries(D.mission.panes) : {};
const MC_GRIDS = D.mission ? D.mission.grids.map(g => g[0]) : [];
const MC_KEY = 'setuhq-mission';
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
function syncMissionURL(push){ if (current === 'mission' && mc.layout && !mc.pop) setHash('#/mission' + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : ''), !!push); }

// ---------- linked selection: one star, every pane, every window ----------
let mcBC = null;
try { if ('BroadcastChannel' in window) mcBC = new BroadcastChannel('setuhq-mission'); } catch (e) { mcBC = null; }
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
  // The sweep's counter, from the committed sweep catalogue (the same figures as the Overview's).
  if (D.sweep){ const c = D.sweep.counts, n = k => c.by_class[k].toLocaleString('en-GB');
    bits.push(`<span>Sweep <b>${c.stars_searched.toLocaleString('en-GB')}</b> stars · <b>${c.star_sectors_searched.toLocaleString('en-GB')}</b> star-sectors · <b>${c.dips_reviewed.toLocaleString('en-GB')}</b> dips reviewed · <b>${c.entries.toLocaleString('en-GB')}</b> entries: ${D.sweep.classes.map(k => `${esc(k.label.toLowerCase())} ${n(k.id)}`).join(', ')}</span>`); }
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
    $('#mclcnote').textContent = own ? `The run's stored light curve of ${D.story.star.name} (${D.story.star.target}); ticks mark its dips.` : `SetuHQ has reviewed one light curve, ${D.story.star.name}'s (${D.story.star.target}). It has none for ${mc.star}.`;
    if (own) skyTimeline($('#mclc'), $('#mclccap'), $('#mclcread')); else { $('#mclc').innerHTML = ''; $('#mclccap').innerHTML = ''; $('#mclcread').textContent = ''; }
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
    $('#mcfeed').innerHTML = feedCards(shown) + (all.length > shown.length ? `<p class="mcnote">${all.length - shown.length} more in <a href="${R(`#/explorer`)}">the Explorer ›</a></p>` : '');
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
  $('#mccopy').addEventListener('click', () => { const url = location.origin + rtUrl('mission') + (encodeMission(mc.layout) ? '?' + encodeMission(mc.layout) : ''); try { navigator.clipboard.writeText(url).then(() => say('Link copied.'), () => say(url)); } catch (e) { say(url); } });
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
  const url = location.origin + rtUrl('mission') + '?pop=' + p + (mc.star ? '&star=' + encodeURIComponent(mc.star) : '');
  const w = window.open(url, 'SetuHQ-' + p, 'popup,width=960,height=680');
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

// ---------- viz.hero (V01): the featured star's transit, looped while on screen through the renderer's scheduler; Pause; a still under reduced motion ----------
window.SetuHero = window.SetuHero || {frames: 0};
(function(){
  const RMq = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  function setup(st){
    if (st._hero) return; st._hero = true;
    const fig = st.querySelector('.herofig'), btn = st.querySelector('[data-hero-pause]'); if (!fig) return;
    let rot = []; try { rot = JSON.parse(st.dataset.rotate || '[]'); } catch (e) { rot = []; }
    // paused: the visitor's choice (pressed under reduced motion); user: the visitor pressed play, so it may run then.
    const S = {paused: RMq(), user: false, p: null};
    try { S.p = JSON.parse(fig.dataset.params || '{}'); } catch (e) { S.p = {}; }
    const T = () => fig._sr;
    // The loop itself is SetuRender's (on screen only, the tab visible, the frame governor); this only counts its frames.
    Object.defineProperty(window.SetuHero, 'playing', {configurable: true, get: () => !!(window.SetuRender && SetuRender.playing && SetuRender.playing(fig))});
    function still(){ const t = T(); if (!t) return; t.p = S.p; try { SetuRender.transit(t.cv, Object.assign({}, S.p, {t: null})); } catch (e) { /* the frame stays */ } }
    // One featured run per UTC day (the same for every visitor that day); the page itself is rendered with the lead.
    if (!RMq() && rot.length > 1){
      const pick = rot[Math.floor(Date.now() / 864e5) % rot.length];
      if (pick && pick.run !== st.dataset.run){
        S.p = pick.p; st.dataset.run = pick.run; fig.dataset.params = JSON.stringify(pick.p);
        const img = fig.querySelector('img.rstill'), cap = fig.querySelector('figcaption');
        if (img) img.alt = pick.alt; if (cap) cap.innerHTML = pick.caption;
      }
    }
    function setBtn(){ if (!btn) return; btn.setAttribute('aria-pressed', S.paused ? 'true' : 'false'); btn.hidden = !T(); }
    function sync(){ if (!T() || !window.SetuRender || !SetuRender.play) return;
      SetuRender.play(fig, !S.paused, {user: S.user, onframe: () => { window.SetuHero.frames++; }}); }
    function ensure(){
      if (!T() && window.SetuRender && !fig.closest('[hidden]')) { try { SetuRender.mount(fig.parentElement); } catch (e) { /* the still stays */ } }
      const t = T(), img = fig.querySelector('img.rstill');
      if (t && img && t.cv.getAttribute('aria-label') !== img.alt){ t.cv.setAttribute('aria-label', img.alt); still(); }
      if (t && !t._hero){ t._hero = true; t.p = S.p; sync(); }
      setBtn();
    }
    if (btn) btn.addEventListener('click', () => { S.paused = !S.paused; S.user = !S.paused; setBtn(); sync(); });
    if ('IntersectionObserver' in window) new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) ensure(); }), {rootMargin: '80px'}).observe(fig);
    // The renderer's script may arrive after this one: look again for a few seconds.
    let n = 0; const wait = () => { ensure(); if (!T() && n++ < 40) setTimeout(wait, 250); }; wait();
  }
  const all = () => document.querySelectorAll('.herostage[data-viz="hero"]').forEach(setup);
  window.SetuHero.setup = all;
  all();
})();

// ---------- viz.gallery (V03): each card's stage, drawn once on a canvas with the renderer's star when it comes on screen ----------
(function(){
  function draw(fig){
    if (fig._g || !window.SetuRender) return; const box = fig.querySelector('.gbox'), sv = box && box.querySelector('svg'); if (!sv) return;
    if (SetuRender.path() === 'still') return;
    let p = {}; try { p = JSON.parse(fig.dataset.params || '{}'); } catch (e) { return; }
    const cv = document.createElement('canvas'), r = box.getBoundingClientRect(), d = Math.min(2, window.devicePixelRatio || 1);
    const W = Math.max(2, Math.round(r.width * d)), H = Math.max(2, Math.round(r.height * d)), S = Math.min(W, H);
    cv.width = W; cv.height = H; cv.setAttribute('aria-hidden', 'true');
    const c = cv.getContext('2d'); if (!c) return;
    try {
      c.fillStyle = '#000'; c.fillRect(0, 0, W, H);
      const cx = W / 2, cy = H / 2, R = S * 0.30, u = S / 240;
      SetuRender.drawStar2D(c, cx, cy, R, p.teff || 5772, 0, {glow: 1.55, sync: true, gl: true, granulation: !!p.teff});
      c.font = `600 ${11 * u}px ${getComputedStyle(document.body).fontFamily}`; c.textAlign = 'center';
      for (const b of p.bodies || []){
        const x = cx + b.x * R, y = cy + b.y * R, rr = Math.max(0.8 * u, b.k * R);
        if (b.kind === 'occ'){
          c.fillStyle = '#2A2E36'; c.beginPath(); c.arc(x, y, rr, 0, 7); c.fill(); c.setLineDash([3 * u, 3 * u]); c.strokeStyle = '#9AA3B5'; c.lineWidth = u; c.stroke(); c.setLineDash([]);
          c.font = `400 ${10.5 * u}px ui-monospace,monospace`; c.fillStyle = '#9AA3B5'; c.fillText('occulter not identified', cx, cy + R + 26 * u); continue;
        }
        if (b.kind === 'missed'){ c.setLineDash([2 * u, 2 * u]); c.strokeStyle = '#ECEFF5'; c.lineWidth = .9 * u; c.beginPath(); c.arc(x, y, rr, 0, 7); c.stroke(); c.setLineDash([]); }
        else SetuRender.drawPlanet2D(c, x, y, rr, 'silhouette');
        if (rr < 3 * u){ c.strokeStyle = 'rgba(4,6,11,.55)'; c.lineWidth = u; c.beginPath(); c.arc(x, y, 7 * u, 0, 7); c.stroke(); }
        c.fillStyle = '#04060B'; c.fillText(b.l, x, y - Math.max(rr, 7 * u) - 5 * u);
      }
    } catch (e) { return; }
    box.appendChild(cv); sv.hidden = true; fig._g = true;
  }
  const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting && !en.target.closest('[hidden]')){ io.unobserve(en.target); draw(en.target); } }), {rootMargin: '120px'}) : null;
  function all(){ document.querySelectorAll('figure.gstage[data-viz="gstage"]').forEach(f => { if (f._gq) return; f._gq = true; if (io) io.observe(f); else draw(f); }); }
  window.SetuGallery = {setup: all};
  all();
})();

// ---------- viz.tempstrip (V09): in filter mode the two handles announce {lo, hi} as setu:teff-range ----------
(function(){
  function wire(root){
    if (root._ts) return; root._ts = true;
    const lo = root.querySelector('[data-ts="lo"]'), hi = root.querySelector('[data-ts="hi"]'); if (!lo || !hi) return;
    const send = src => {
      let a = Number(lo.value), b = Number(hi.value);
      if (a > b){ if (src === lo) lo.value = a = b; else hi.value = b = a; }
      lo.setAttribute('aria-valuetext', a.toLocaleString('en-US') + ' K'); hi.setAttribute('aria-valuetext', b.toLocaleString('en-US') + ' K');
      root.dispatchEvent(new CustomEvent('setu:teff-range', {bubbles: true, detail: {lo: a, hi: b}}));
    };
    lo.addEventListener('input', () => send(lo)); hi.addEventListener('input', () => send(hi));
  }
  window.SetuTempstrip = {wire: root => Array.from(root ? [root] : document.querySelectorAll('[data-viz="tempstrip"][data-filter="1"]')).forEach(wire)};
  window.SetuTempstrip.wire();
})();

// ---------- viz.skyyears (V04): the sky by discovery year; fetched near the screen, played while on screen ----------
(function(){
  const RM = () => matchMedia('(prefers-reduced-motion: reduce)').matches, PER = 0.42 * 1000, HOLD = 3000;
  const R = 159.80613254815972, S2 = Math.SQRT2, COLS = ["#64D2FF", "#FF6961", "#30D158", "#BF5AF2", "#FFD60A", "#7D7AFF", "#A1A1A6"], LABELS = ["transit", "radial velocity", "imaging", "microlensing", "astrometry", "timing", "other"];  // the sky file's method order (design.METHOD)
  function moll(ra, dec){
    ra = ra > 180 ? ra - 360 : ra; const lam = -ra * Math.PI / 180, phi = dec * Math.PI / 180; let th = phi;
    for (let k = 0; k < 30; k++){ const f = 2 * th + Math.sin(2 * th) - Math.PI * Math.sin(phi); th -= f / (2 + 2 * Math.cos(2 * th) + 1e-12); }
    return [(R * 2 * S2 / Math.PI * lam * Math.cos(th) + 460) / 920, (235 - R * S2 * Math.sin(th)) / 470];
  }
  const fmtN = n => n.toLocaleString('en-GB');
  function wire(fig){
    if (fig._sky || !fig.dataset.src || !window.fetch) return;
    const S = fig._sky = {vis: false, pts: null, playing: false, year: +fig.dataset.y1, tonly: false, t: 0, last: 0, said: 0, raf: 0, held: 0};
    const y0 = +fig.dataset.y0, y1 = +fig.dataset.y1, cols = COLS, labels = LABELS;
    const q = s => fig.querySelector(s), box = q('.skybox'), play = q('[data-sky="play"]'), tr = q('[data-sky="transit"]'), rng = q('[data-sky="year"]');
    const out = q('.skyread'), live = q('[data-sky="live"]'), tag = q('.skyyear');
    let cv = null;
    function load(){
      if (S.loading) return; S.loading = true;
      fetch(fig.dataset.src).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(j => {
        S.pts = j.p.map(a => [a[0] / 10, a[1] / 10, a[2], a[3] || y1]).sort((a, b) => a[3] - b[3]).map(a => moll(a[0], a[1]).concat([a[2], a[3]]));
        S.tr = j.m.indexOf('transit');
        cv = document.createElement('canvas'); cv.setAttribute('aria-hidden', 'true');
        const over = box.querySelector('.skyover'); if (over) box.insertBefore(cv, over); else box.appendChild(cv);
        q('.skydots').setAttribute('hidden', ''); const nj = q('.skynojs'); if (nj) nj.remove();
        [play, tr, rng.closest('label')].forEach(el => { el.hidden = false; });
        S.playing = !RM(); if (S.playing) S.year = y0;
        setPlay(); draw(); kick();
      }).catch(() => { /* the static map stays */ });
    }
    function summary(){
      const c = cols.map(() => 0); let n = 0;
      for (const a of S.pts){ if (a[3] > S.year) break; if (S.tonly && a[2] !== S.tr) continue; c[a[2]]++; n++; }
      const top = c.map((v, k) => [v, k]).filter(a => a[0]).sort((a, b) => b[0] - a[0]).slice(0, 4);
      return [n, `${fmtN(n)} planets shown${S.tonly ? ' (transits only)' : ''} · ` + top.map(([v, k]) => `${labels[k]} ${fmtN(v)}`).join(' · ')];
    }
    function draw(){
      if (!cv || !S.pts) return;
      const r = box.getBoundingClientRect(), d = Math.min(2, devicePixelRatio || 1), w = Math.max(2, Math.round(r.width * d)), h = Math.max(2, Math.round(r.height * d));
      if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
      const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, w, h);
      const sm = Math.max(1.3 * d, w / 700), bg = sm * 1.9;
      for (const a of S.pts){
        if (a[3] > S.year) break; if (S.tonly && a[2] !== S.tr) continue;
        const fresh = S.year - a[3] < 1, s = fresh ? bg : sm;
        ctx.globalAlpha = fresh ? 1 : .72; ctx.fillStyle = cols[a[2]]; ctx.fillRect(a[0] * w - s / 2, a[1] * h - s / 2, s, s);
      }
      ctx.globalAlpha = 1;
      const [n, t] = summary(); out.textContent = t; tag.textContent = String(S.year);
      rng.value = String(S.year); rng.setAttribute('aria-valuetext', `${S.year}: ${fmtN(n)} planets`);
      // The live region speaks only while playing, at most once every 2 s; a scrubbed year is read from the slider.
      const now = performance.now(); if (S.playing && now - S.said > 2000){ S.said = now; live.textContent = t; }
    }
    function setPlay(){ play.textContent = S.playing ? 'Pause' : 'Play'; play.setAttribute('aria-pressed', String(S.playing)); }
    function frame(now){
      S.raf = 0; if (!S.playing || !S.vis || document.hidden) return;
      const dt = Math.min(100, now - (S.last || now)); S.last = now;
      if (S.year >= y1){ S.held += dt; if (S.held >= HOLD){ S.held = 0; S.year = y0; S.t = 0; draw(); } }
      else { S.t += dt; if (S.t >= PER){ S.t = 0; S.year++; draw(); } }
      S.raf = requestAnimationFrame(frame);
    }
    function kick(){ if (!S.raf && S.playing && S.vis && !document.hidden){ S.last = 0; S.raf = requestAnimationFrame(frame); } }
    play.addEventListener('click', () => { S.playing = !S.playing; if (S.playing && S.year >= y1){ S.year = y0; S.t = 0; draw(); } setPlay(); kick(); });
    tr.addEventListener('click', () => { S.tonly = !S.tonly; tr.setAttribute('aria-pressed', String(S.tonly)); draw(); });
    rng.addEventListener('input', () => { S.playing = false; setPlay(); S.year = +rng.value; draw(); });
    if ('IntersectionObserver' in window){
      new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) load(); }), {rootMargin: '600px'}).observe(fig);
      new IntersectionObserver(es => es.forEach(e => { S.vis = e.isIntersecting; if (S.vis) kick(); }), {rootMargin: '80px'}).observe(box);
    } else { S.vis = true; load(); }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) kick(); });
    let rz = 0; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(draw, 150); });
  }
  window.SetuSky = {wire: root => (root || document).querySelectorAll('[data-viz="skyyears"]').forEach(wire)};
  window.SetuSky.wire();
})();

// ---------- viz.timeline (V12): the bars answer on hover and on the arrow keys (SetuUI.crosshair, S06) ----------
(function(){
  function wire(fig){
    if (fig._tl || !window.SetuUI || !SetuUI.crosshair) return; fig._tl = true;
    const y0 = +fig.dataset.y0, rows = fig.dataset.counts.split(' ').map((w, i) => { const c = w.split('.').map(Number); return [y0 + i, c.reduce((a, b) => a + b, 0)].concat(c); }), labels = ["transit", "radial velocity", "imaging", "microlensing", "astrometry", "timing", "other"], svg = fig.querySelector('.tlsvg');
    const f = n => n.toLocaleString('en-GB');
    SetuUI.crosshair(svg, {x0: +fig.dataset.x0, x1: +fig.dataset.x1, xs: rows.map(r => r[0]), readout: fig.querySelector('.tlread'),
      fmt: i => { const r = rows[i]; return `${r[0]}: ${f(r[1])} planet${r[1] === 1 ? '' : 's'}` + (r[1] ? ' · ' + r.slice(2).map((v, k) => [v, k]).filter(a => a[0]).sort((a, b) => b[0] - a[0]).map(([v, k]) => `${labels[k]} ${f(v)}`).join(' · ') : ''); }});
  }
  window.SetuTimeline = {wire: root => (root || document).querySelectorAll('[data-viz="timeline"]').forEach(wire)};
  window.SetuTimeline.wire();
})();

// ---------- viz.orbits (V08): the system from above; the dips in a strip; played while on screen, with Pause ----------
(function(){
  const RM = () => matchMedia('(prefers-reduced-motion: reduce)').matches, TAU = Math.PI * 2;
  function wire(fig){
    if (fig._orb) return;
    let p; try { p = JSON.parse(fig.dataset.params); } catch (e) { return; }
    const box = fig.querySelector('.orbbox'), btn = fig.querySelector('[data-orb="play"]'), svg = box.querySelector('svg');
    const cv = document.createElement('canvas'); if (!cv.getContext) return;
    cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', svg.getAttribute('aria-label'));
    box.classList.add('cv'); box.appendChild(cv); svg.setAttribute('hidden', '');
    const S = fig._orb = {t: 0, playing: !RM(), vis: false, raf: 0, last: 0, fo: 'all', zm: 1}, cam = fig.querySelector('.orbcam');
    const ps = p.planets, T = ps[ps.length - 1].P, amax = Math.max(...ps.map(q => q.a)), dmax = Math.max(1, ...ps.map(q => q.d || 0));
    const rgb = window.SetuRender ? SetuRender.teffRGB(p.teff || 5772) : [255, 241, 234];
    function draw(){
      const r = box.getBoundingClientRect(), d = Math.min(2, devicePixelRatio || 1), w = Math.max(2, Math.round(r.width * d)), h = Math.max(2, Math.round(r.height * d));
      if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
      const c = cv.getContext('2d'), narrow = w / d < 600, days = S.t * p.speed, ph = (days % T) / T;
      c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
      const R = narrow ? Math.min(w * .4, h * .18) : Math.min(h * .42, w * .2), k = S.zm * (S.fo === 'all' ? 1 : Math.min(40, amax / ps[S.fo === 'star' ? 0 : S.fo].a * (S.fo === 'star' ? .8 : 2.5)));
      const pos = (q, i) => { const a = Math.PI / 2 + TAU * (days / q.P + q.f), r = R * q.a / amax * k; return [r * Math.cos(a), r * Math.sin(a), a, r]; }, fp = S.fo > -1 && ps[S.fo] ? pos(ps[S.fo], S.fo) : [0, 0];
      const cx = (narrow ? w * .5 : w * .23) - fp[0], cy = (narrow ? h * .25 : h * .48) - fp[1];
      c.save(); c.beginPath(); c.rect(0, 0, narrow ? w : w * .47, narrow ? h * .5 : h); c.clip();
      c.font = `${11 * d}px ${getComputedStyle(fig).fontFamily}`; c.lineWidth = d;
      c.strokeStyle = 'rgba(255,179,64,.5)'; c.setLineDash([4 * d, 5 * d]); c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx, cy + R + 22 * d); c.stroke(); c.setLineDash([]);
      c.fillStyle = '#FFB340'; c.fillText('to the observer', cx + 8 * d, cy + R + 20 * d);
      const sR = Math.max(5 * d, R * .06);
      if (window.SetuRender) SetuRender.drawStar2D(c, cx, cy, sR, p.teff || 5772, 0, {flat: true, glow: 2.2}); else { c.fillStyle = `rgb(${rgb})`; c.beginPath(); c.arc(cx, cy, sR, 0, TAU); c.fill(); }
      const ons = ps.map((q, i) => {
        const [px, py, th, rr] = pos(q, i), x = cx + px, y = cy + py;
        c.strokeStyle = 'rgba(255,255,255,.14)'; c.beginPath(); c.arc(cx, cy, rr, 0, TAU); c.stroke();
        const off = Math.abs(Math.atan2(Math.sin(th - Math.PI / 2), Math.cos(th - Math.PI / 2))), on = off < Math.max(.05, Math.PI * (q.w || 1) / 24 / q.P);
        c.fillStyle = q.c; c.beginPath(); c.arc(x, y, 4.5 * d, 0, TAU); c.fill();
        if (on){ c.strokeStyle = q.c; c.beginPath(); c.arc(x, y, 10 * d, 0, TAU); c.stroke(); }
        c.fillStyle = '#ECEFF5'; c.fillText(q.n, x + 8 * d, y - 7 * d);
        return on;
      });
      c.restore();
      const gx = narrow ? w * .06 : w * .5, gw = narrow ? w * .88 : w * .46, top = narrow ? h * .58 : h * .14, lane = Math.min(64 * d, (narrow ? h * .27 : h * .78) / ps.length);
      c.font = `${11 * d}px ${getComputedStyle(fig).fontFamily}`; c.fillStyle = '#9AA3B5'; c.fillText(`one ${T.toFixed(2)}-day period · depth k² (ppm), one scale`, gx, top - 8 * d);
      ps.forEach((q, i) => {
        const on = ons[i], base = top + 18 * d + i * lane, hh = q.d ? Math.max(2 * d, q.d / dmax * (lane - 30 * d)) : 0, ww = Math.max(2 * d, (q.w || 1) / 24 / T * gw);
        c.strokeStyle = q.c; c.lineWidth = 1.6 * d; c.beginPath(); c.moveTo(gx, base);
        for (let n = Math.ceil(q.f - 1e-9); (n - q.f) * q.P <= T; n++){ const tc = (n - q.f) * q.P; if (tc < 0 || !q.d) continue; const xc = gx + tc / T * gw; c.lineTo(xc - ww / 2, base); c.lineTo(xc - ww / 2, base + hh); c.lineTo(xc + ww / 2, base + hh); c.lineTo(xc + ww / 2, base); }
        c.lineTo(gx + gw, base); c.stroke(); c.lineWidth = d;
        c.fillStyle = on ? '#ECEFF5' : '#9AA3B5'; c.fillText(`${q.n} · ${q.P.toFixed(2)} d · ${q.d ? Math.round(q.d).toLocaleString('en-GB') + ' ppm' : 'radius not stored'}`, gx, base - 6 * d);
      });
      const hx = gx + ph * gw; c.strokeStyle = 'rgba(236,239,245,.55)'; c.beginPath(); c.moveTo(hx, top + 4 * d); c.lineTo(hx, top + 18 * d + ps.length * lane - 10 * d); c.stroke();
    }
    function setBtn(){ btn.hidden = false; btn.textContent = S.playing ? 'Pause' : 'Play'; btn.setAttribute('aria-pressed', String(S.playing)); }
    function frame(now){ S.raf = 0; if (!S.playing || !S.vis || document.hidden) return; S.t += Math.min(.1, (now - (S.last || now)) / 1000); S.last = now; draw(); S.raf = requestAnimationFrame(frame); }
    function kick(){ if (!S.raf && S.playing && S.vis && !document.hidden){ S.last = 0; S.raf = requestAnimationFrame(frame); } }
    btn.addEventListener('click', () => { S.playing = !S.playing; setBtn(); kick(); });
    if (cam){ cam.hidden = false; cam.addEventListener('click', e => { const b = e.target.closest('[data-oc]'); if (!b) return; const o = b.dataset.oc;
      if (o === 'in' || o === 'out') S.zm = Math.max(.5, Math.min(8, S.zm * (o === 'in' ? 1.5 : 1 / 1.5))); else { S.fo = o === 'reset' ? 'all' : isNaN(o) ? o : +o; S.zm = 1; }
      cam.querySelectorAll('[aria-pressed]').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.oc === String(S.fo)))); draw(); }); }
    if ('IntersectionObserver' in window) new IntersectionObserver(es => es.forEach(e => { S.vis = e.isIntersecting; if (S.vis){ draw(); kick(); } }), {rootMargin: '80px'}).observe(box);
    else { S.vis = true; kick(); }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) kick(); });
    let rz = 0; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(draw, 150); });
    setBtn(); draw();
  }
  window.SetuOrbits = {wire: root => (root || document).querySelectorAll('[data-viz="orbits"]').forEach(wire)};
  window.SetuOrbits.wire();
})();

// ---------- viz/panelring (V06): the markup of setuhq.viz.panelring.html, and a one-time convergence on screen ----------
window.SetuPanelRing = (function(){
  const W = 360, H = 240, CX = 180, CY = 120, RING = 46, COL = {left: 56, right: 304};
  const STATE = {"passed": ["cand", "candidate", "candidate, unconfirmed"], "flagged": ["open", "flagged", "flagged for review, open"], "rejected": ["rej", "rejected", "rejected by vetting, not a candidate"]}, FEED = ['new_candidate', 'known_toi'], PROBES_ONLY = "Probes only; Sentinels not run on this example", ATTRIBUTION = "Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.";
  const state = o => STATE[FEED.includes(o) ? 'passed' : (o || '')] || STATE.flagged;
  const n = x => String(Math.floor(x * 10 + 0.5) / 10);
  const e = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  const wf = w => (w === null || w === undefined) ? 'not stored' : w.toFixed(2);
  const cl = v => Math.max(0, Math.min(1, v));
  const has = v => v !== null && v !== undefined;
  function layout(rs){
    const roles = new Set(rs.map(r => r.role)), sides = {left: [], right: []};
    rs.forEach((r, i) => sides[roles.size > 1 ? (r.role === 'sentinel' ? 'left' : 'right') : (i % 2 === 0 ? 'right' : 'left')].push(r));
    const out = [];
    for (const side of ['left', 'right']){
      const list = sides[side], k = list.length, step = Math.min(64, 190 / Math.max(k, 1));
      list.forEach((r, i) => { const off = i - (k - 1) / 2;
        out.push(Object.assign({}, r, {side, x: COL[side], y: CY + off * step, rad: 9 + 9 * cl(r.weight || 0), ty: CY + off * 10})); });
    }
    return out;
  }
  function aria(d, rs){
    const panel = d.mode === 'panel', who = rs.map(r => `${r.name}, weight ${wf(r.weight)}` + (panel ? '' : (r.marked ? ', marked it' : ', no mark'))).join('; ');
    if (panel) return `The panel: ${rs.length} reviewers, each with its calibrated weight: ${who}.`;
    return `${d.label || 'This dip'}: ${rs.filter(r => r.marked).length} of ${rs.length} reviewers marked it (${who}). Panel score ${has(d.score) ? d.score.toFixed(2) : 'not stored'} as stored: ${state(d.outcome)[2]}.`;
  }
  function html(d){
    const mode = d.mode || 'dip', uid = e(d.uid || 'pr');
    if (!(d.reviewers || []).filter(r => !(d.probes_only && r.role === 'sentinel')).length && (mode !== 'dip' || !has(d.score))) return '';  // nothing stored: no ring
    const rs = (d.reviewers || []).filter(r => !(d.probes_only && r.role === 'sentinel'));
    const score = mode === 'dip' && has(d.score) ? d.score : null, circ = 2 * Math.PI * RING, lines = [], dots = [];
    layout(rs).forEach((r, i) => {
      const left = r.side === 'left', x1 = r.x + (left ? r.rad : -r.rad), x2 = left ? CX - (RING + 8) : CX + (RING + 8), mx = (x1 + x2) / 2;
      const on = mode === 'panel' || !!r.marked, cls = (r.role === 'sentinel' ? 'sen' : 'prb') + (on ? '' : ' off'), sw = 1 + 3 * cl(r.weight || 0);
      lines.push(`<path class="prline ${cls}" d="M${n(x1)} ${n(r.y)}C${n(mx)} ${n(r.y)} ${n(mx)} ${n(r.ty)} ${n(x2)} ${n(r.ty)}" stroke-width="${n(sw)}" pathLength="100" style="transition-delay:${i * 60}ms"/>`);
      const name = r.name || r.id, k = name.indexOf(' · '), head = k >= 0 ? name.slice(0, k) : name, tail = k >= 0 ? name.slice(k + 3) : '', ly = r.y + r.rad + 12;
      dots.push(`<g class="prnode ${cls}"><circle cx="${n(r.x)}" cy="${n(r.y)}" r="${n(r.rad)}"/><text x="${n(r.x)}" y="${n(ly)}">${e(head)}</text><text x="${n(r.x)}" y="${n(ly + 12)}">${e(tail)}${tail ? ' · ' : ''}${wf(r.weight)}</text></g>`);
    });
    const track = `<circle class="prtrack" cx="${CX}" cy="${CY}" r="${RING}"/>`;
    const ring = score !== null
      ? `${track}<circle class="prring" cx="${CX}" cy="${CY}" r="${RING}" stroke-dasharray="${n(circ)}" style="--off:${n(circ * (1 - cl(score)))};--c:${n(circ)}" transform="rotate(-90 ${CX} ${CY})"/><text class="prnum" x="${CX}" y="${CY + 7}">${score.toFixed(2)}</text><text class="prsub" x="${CX}" y="${CY + 22}">panel score</text>`
      : mode === 'dip' ? `${track}<text class="prsub" x="${CX}" y="${CY + 4}">score not stored</text>`
      : `${track}<text class="prnum" x="${CX}" y="${CY + 7}">${rs.length}</text><text class="prsub" x="${CX}" y="${CY + 22}">reviewers</text>`;
    let verdict = '', what = 'Every reviewer in the panel, sized by its calibrated weight; no dip is selected, so no score is drawn.';
    if (mode === 'dip'){
      const [c, , phrase] = state(d.outcome);
      verdict = `<p class="prverdict"><span>${rs.filter(r => r.marked).length} of ${rs.length} marked it · panel score ${score !== null ? score.toFixed(2) : 'not stored'}, as stored</span><strong class="prword ${e(c)}" data-verdict="${e(phrase)}">${e(phrase)}</strong></p>`;
      what = "Each reviewer's stored mark on this dip (a solid line: it marked the dip; dashed: no mark), each sized by its calibrated weight; the ring fills to the panel score as the run stored it.";
    }
    const note = (d.probes_only ? ` ${e(PROBES_ONLY)}.` : '') + (rs.some(r => r.role === 'sentinel') ? ` ${e(ATTRIBUTION)}` : '');
    const rows = rs.map(r => `<tr><th scope="row">${e(r.name || r.id)} <span class="mono">${e(r.id)}</span></th><td>${r.role === 'sentinel' ? 'Sentinel' : 'Probe'}</td><td>${e(r.provider || '')}</td>` + (mode === 'panel' ? '' : `<td>${r.marked ? 'yes' : 'no'}</td>`) + `<td class="num">${wf(r.weight)}</td></tr>`).join('');
    const head = '<tr><th scope="col">Reviewer</th><th scope="col">Role</th><th scope="col">Provider</th>' + (mode === 'panel' ? '' : '<th scope="col">Marked this dip</th>') + '<th scope="col" class="num">Calibrated weight</th></tr>';
    return `<div class="panelring" data-panelring="${e(mode)}"><figure class="stage prfig" aria-labelledby="prcap-${uid}"><span class="stage-tag">Real data, cited</span><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(aria(Object.assign({}, d, {mode}), rs))}"><g class="prlines" aria-hidden="true">${lines.join('')}</g>${ring}<g class="prnodes">${dots.join('')}</g></svg>${verdict}<figcaption class="readout" id="prcap-${uid}">${what} Source: ${e(d.source)}.${note}</figcaption></figure><details class="prtable"><summary>The marks and weights as a table</summary><div class="tablewrap"><table><thead>${head}</thead><tbody>${rows}</tbody></table></div></details></div>`;
  }
  // The data for one dip, as setuhq.viz.panelring.dip_model builds it.
  function dipModel(dip, o){
    const prov = o.provenance || {}, w = o.weights || {}, rs = [];
    for (const ln of dip.lanes || []){
      if (ln.role !== 'sentinel' && ln.role !== 'probe') continue;
      rs.push({id: ln.id, name: ln.name || ln.id, role: ln.role, marked: !!ln.counted, weight: has(w[ln.id]) ? w[ln.id] : null,
        provider: ln.role === 'sentinel' ? ((prov[ln.id] || {}).provider_label || 'provider not recorded') : 'deterministic matched filter'});
    }
    return {source: `run ${o.run || 'as stored'}, its stored marks and panel score; calibrated weights from ${o.weights_path || 'no weights file'}`,
      mode: 'dip', reviewers: rs, score: has(dip.score) ? dip.score : null, outcome: dip.outcome, label: o.label || '', probes_only: !!o.probes_only, uid: dip.id || 'pr'};
  }
  // Once, when it comes on screen: the lines draw in, the nodes fill and the ring fills to the score. Still under
  // reduced motion (the markup is already at its final values).
  let io = null;
  function mount(root){
    const figs = Array.from((root || document).querySelectorAll('.prfig:not([data-pr])'));
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window);
    figs.forEach(f => {
      f.dataset.pr = '1'; if (still) return;
      f.classList.add('pr-pre');
      io = io || new IntersectionObserver(es => es.forEach(en => { if (!en.isIntersecting) return; io.unobserve(en.target);
        requestAnimationFrame(() => requestAnimationFrame(() => en.target.classList.remove('pr-pre'))); }), {rootMargin: '0px 0px -10% 0px'});
      io.observe(f);
    });
  }
  // A ring sent in its smallest form (setuhq.viz.panelring.summary) is drawn in full from the app's stored record.
  function fill(root){
    const A = window.D; if (!A) return;
    (root || document).querySelectorAll('[data-pr-dip]').forEach(el => {
      const d = [...((A.story || {}).dips || []), ...(A.showcase_dips || [])].find(x => x.id === el.dataset.prDip); if (!d) return;
      const run = d.run || (A.run || {}).name, w = Object.fromEntries(((A.calibration || {}).points || []).map(p => [p.id, p.weight]));
      const m = dipModel(d, {weights: w, provenance: A.reviewer_provenance, weights_path: A.weights_path, run, label: ((A.dips || {})[d.id] || {}).label || '',
        probes_only: !!(((A.run_ctx || {})[run] || {}).probes_only)});
      m.uid = el.dataset.prUid || m.uid;
      const t = document.createElement('div'); t.innerHTML = html(m); if (t.firstElementChild) el.replaceWith(t.firstElementChild);
    });
  }
  const init = () => { fill(document); mount(document); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  return {html, dipModel, mount, layout, fill};
})();

// ---------- V05 the fold (setuhq.viz.fold): pi Men's stored light curve, folded on the joint-fit period ----------
(function(){
  const figs = Array.from(document.querySelectorAll('figure.foldfig'));
  if (!figs.length) return;
  const RM = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  let loading = null;
  const load = () => loading || (loading = new Promise((res, rej) => {
    const url = ((window.D || {}).viz_files || {}).stories;
    if (!url) return rej(new Error('no stories file'));
    fetch(url).then(r => r.ok ? r.json() : Promise.reject(new Error(r.status))).then(j => j && j.fold ? res(j.fold) : rej(new Error('no fold'))).catch(rej);
  }));
  const mix = (a, b, t) => a + (b - a) * t, ease = k => k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
  // Each bin: [x in time order, x in phase within the window (outside 0..1 leaves the frame), ppm].
  function prep(F){
    const w = F.bin_min / 1440, P = F.p, W = F.window_h, span = F.span[1] - F.span[0], pts = [];
    for (const [i0, vals] of F.segs) vals.forEach((v, k) => { const t = F.t_start + (i0 + k + .5) * w, ph = ((t - F.t0 + P / 2) % P + P) % P - P / 2;
      pts.push([(t - F.span[0]) / span, (ph * 24 + W) / (2 * W), v]); });
    const vals = pts.map(p => p[2]).sort((a, b) => a - b);
    let lo = Math.min(vals[Math.floor(.003 * vals.length)], -1.7 * F.depth_ppm), hi = Math.max(vals[Math.floor(.997 * vals.length) - 1], .8 * F.depth_ppm);
    const step = hi - lo > 700 ? 200 : 100; lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const acc = {};
    for (const p of pts) if (p[1] >= 0 && p[1] <= 1){ const k = Math.floor((p[1] * 2 * W - W) / .5 + .5); (acc[k] = acc[k] || []).push(p[2]); }
    const mean = Object.keys(acc).map(Number).sort((a, b) => a - b).map(k => [(k * .5 + W) / (2 * W), acc[k].reduce((a, b) => a + b, 0) / acc[k].length]);
    return {pts, lo, hi, step, mean};
  }
  figs.forEach(fig => {
    // The compact figure (the home page) arrives as its label and caption: the canvas and the toggle are added here.
    if (!fig.querySelector('.foldlive')){ const cap = fig.querySelector('figcaption');
      cap.id = cap.id || 'fold-cap-' + Math.random().toString(36).slice(2, 8);
      // Its full source line arrives with the bins (stories.json).
      load().then(d => { if (!cap.querySelector('.foldsrc')) cap.insertAdjacentHTML('beforeend', ` <span class="foldsrc">${d.source.replace(/[<&>]/g, '')}</span>`); }).catch(() => {});
      cap.insertAdjacentHTML('beforebegin', `<div class="foldlive" hidden><canvas role="img" aria-labelledby="${cap.id}"></canvas></div>`
        + '<div class="foldctl"><button class="btn foldbtn" type="button" aria-pressed="false" hidden>Fold on the period</button><span class="foldstate" aria-live="polite"></span></div>'); }
    const btn = fig.querySelector('.foldbtn'), live = fig.querySelector('.foldlive'), cv = live && live.querySelector('canvas'), state = fig.querySelector('.foldstate');
    if (!btn || !cv) return;
    let F = null, G = null, k = 0, target = 0, raf = 0, vis = false, touched = false, last = 0, font = '', split = false;
    const compact = fig.classList.contains('compact');
    // One panel of the plot inside the rectangle (ox, oy, W, H) of the canvas, at fold progress e (0 time order, 1 folded).
    function panel(c, dpr, ox, oy, W, H, e, title){
      const L = ox + 46 * dpr, R = 12 * dpr, T = oy + (title ? 44 : 30) * dpr, B = 30 * dpr, pw = ox + W - L - R;
      const Y = v => T + (oy + H - T - B) * (1 - (v - G.lo) / (G.hi - G.lo));
      c.font = `${11 * dpr}px ${font}`; c.lineWidth = dpr;
      if (title){ c.fillStyle = '#ECEFF5'; c.textAlign = 'left'; c.fillText(title, ox + 4 * dpr, oy + 14 * dpr); }
      for (let v = G.lo; v <= G.hi + 1e-9; v += G.step){ const y = Y(v); c.strokeStyle = 'rgba(255,255,255,.08)'; c.beginPath(); c.moveTo(L, y); c.lineTo(ox + W - R, y); c.stroke();
        c.fillStyle = '#9AA3B5'; c.textAlign = 'right'; c.fillText((v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v), L - 6 * dpr, y + 4 * dpr); }
      c.textAlign = 'left'; c.fillText('ppm', ox + 4 * dpr, T - 16 * dpr);
      c.textAlign = 'right'; c.fillText(e < .5 ? `BTJD ${F.span[0].toFixed(1)}–${F.span[1].toFixed(1)}, in time order` : `hours from mid-transit, folded on ${F.p.toFixed(4)} d`, ox + W - R, oy + H - 9 * dpr);
      c.fillStyle = e > .6 ? 'rgba(100,210,255,.75)' : 'rgba(236,239,245,.6)';
      const s = 2.2 * dpr;
      for (const [tx, px, v] of G.pts){ const f = mix(tx, Math.max(-.2, Math.min(1.2, px)), e); if (f < 0 || f > 1) continue; c.fillRect(L + f * pw - s / 2, Y(v) - s / 2, s, s); }
      if (e > .85){
        const a = (e - .85) / .15, yd = Y((F.base_ppm || 0) - F.depth_ppm);
        c.strokeStyle = `rgba(255,179,64,${a})`; c.lineWidth = 2.2 * dpr; c.beginPath();
        G.mean.forEach(([f, v], i) => { const x = L + f * pw, y = Y(v); if (i) c.lineTo(x, y); else c.moveTo(x, y); }); c.stroke();
        c.fillStyle = `rgba(255,179,64,${a})`; c.textAlign = 'right'; c.fillText(`${Math.round(F.depth_ppm)} ppm deep, ${F.t14_h.toFixed(2)} h (joint fit)`, ox + W - R - 4 * dpr, yd + 18 * dpr);
        c.setLineDash([4 * dpr, 4 * dpr]); c.lineWidth = dpr; c.beginPath(); c.moveTo(L, yd); c.lineTo(ox + W - R, yd); c.stroke(); c.setLineDash([]);
      }
    }
    function draw(){
      const dpr = Math.min(2, window.devicePixelRatio || 1), r = cv.getBoundingClientRect();
      const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
      if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
      const c = cv.getContext('2d'); if (!c) return;
      font = font || getComputedStyle(document.body).getPropertyValue('--mono').trim() || 'monospace';
      c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
      if (!split) return panel(c, dpr, 0, 0, w, h, ease(k), '');
      // The reduced-motion still drawn from the bins (the compact figure carries no static panels): both panels at once.
      const wide = w > 1.4 * h, a = 'Unfolded: in time order', b = `Folded on the ${F.p.toFixed(4)}-day period`;
      if (wide){ panel(c, dpr, 0, 0, w / 2, h, 0, a); panel(c, dpr, w / 2, 0, w / 2, h, 1, b); }
      else { panel(c, dpr, 0, 0, w, h / 2, 0, a); panel(c, dpr, 0, h / 2, w, h / 2, 1, b); }
    }
    function frame(now){
      raf = 0;
      const dt = Math.min(.05, Math.max(0, (now - (last || now)) / 1000)); last = now;
      k += (target - k) * Math.min(1, dt * 2.6);
      if (Math.abs(target - k) < .002) k = target;
      draw();
      if (k !== target && vis && !document.hidden) raf = requestAnimationFrame(frame);
    }
    const run = () => { if (raf || !F) return; if (RM() || !vis || document.hidden){ k = target; draw(); return; } last = 0; raf = requestAnimationFrame(frame); };
    const setTarget = (t, say) => { target = t; btn.setAttribute('aria-pressed', String(!!t)); btn.textContent = t ? 'Unfold to time' : 'Fold on the period';
      if (say && state) state.textContent = t ? `Folded on ${F.p.toFixed(4)} days: the dip appears at zero hours.` : 'In time order: each transit is a handful of points among the rest.'; run(); };
    const goLive = () => { fig.classList.add('live'); fig.classList.toggle('split', split); live.hidden = false; draw(); };
    btn.hidden = false;
    btn.addEventListener('click', () => { touched = true;
      load().then(d => { if (!F){ F = d; G = prep(F); } const next = target ? 0 : 1;
        split = false; fig.classList.remove('split');
        if (!fig.classList.contains('live')){ k = RM() ? next : 0; goLive(); }
        setTarget(next, true); }).catch(() => { btn.hidden = true; }); });
    if (!('IntersectionObserver' in window)) return;
    // Near the viewport: fetch the bins and (with motion allowed) swap the still for the canvas.
    const near = new IntersectionObserver(es => { if (!es.some(x => x.isIntersecting)) return; near.disconnect();
      // Reduced motion: the full figure keeps its static panels; the compact one draws the same two panels once.
      if (RM()){ if (compact) load().then(d => { F = F || d; G = G || prep(F); if (!fig.classList.contains('live')){ split = true; goLive(); } }).catch(() => {}); return; }
      load().then(d => { F = F || d; G = G || prep(F); if (!fig.classList.contains('live')){ k = target; goLive(); } if (vis) arm(); }).catch(() => {}); }, {rootMargin: '600px'});
    near.observe(fig);
    // On screen: fold once on its own (unless the visitor already used the toggle); off screen: stop where it is headed.
    const arm = () => { if (!touched && !RM() && F && target === 0) setTimeout(() => { if (!touched && vis && target === 0){ touched = true; setTarget(1, false); } }, 900); };
    const io = new IntersectionObserver(es => { vis = es.some(x => x.isIntersecting);
      if (!vis){ if (raf){ cancelAnimationFrame(raf); raf = 0; k = target; if (F) draw(); } return; }
      arm(); run(); }, {rootMargin: '80px', threshold: .3});
    io.observe(fig);
    document.addEventListener('visibilitychange', () => { if (document.hidden){ if (raf){ cancelAnimationFrame(raf); raf = 0; } } else run(); });
    let rz = 0; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (F && fig.classList.contains('live')) draw(); }, 150); });
  });
})();

function tnWire(){
  const f = $('#tnow'), r = $('#tnrange'); if (!f || f._w) return; f._w = 1;
  const M = JSON.parse(f.dataset.meta), day = new Date().toISOString().slice(0, 10), now = M.findIndex(m => m.a <= day && day < m.b);
  const set = i => { $$('.tnsec', f).forEach(g => g.classList.toggle('on', +g.dataset.i === i)); const m = M[i], t = `Sector ${m.s}: ${m.a} to ${m.b} · ${m.n} catalogued stars with known planets in its fields` + (m.x.length ? ' · in its fields: ' + m.x.join(', ') : ''); $('#tnread').textContent = t; r.setAttribute('aria-valuetext', t); };
  if (now >= 0){ r.value = now; set(now); }
  r.oninput = () => set(+r.value);
}

function vtWire(){
  const root = $('#route-vetter'); if (!root || root._w) return; root._w = 1;
  let A = {}; try { A = JSON.parse(localStorage.getItem('setuhq-vetter')) || {}; } catch (e) {}
  const C = $$('.vtcard', root), W = {passed: 'pass', flagged: 'flag', rejected: 'reject'};
  const show = (c, o) => { $$('[data-vt]', c).forEach(b => b.setAttribute('aria-pressed', b.dataset.vt === o)); $('.vtsay', c).textContent = o ? `You called it: ${W[o]}. The vetting: ${W[c.dataset.out]}.` : ''; $('.vtreveal', c).open = !!o; };
  const score = () => { const a = C.filter(c => A[c.dataset.dip]); try { localStorage.setItem('setuhq-vetter', JSON.stringify(A)); } catch (e) {}
    $('.vtscore', root).hidden = !a.length; $('#vtscore').textContent = `Your calls match the vetting on ${a.filter(c => A[c.dataset.dip] === c.dataset.out).length} of ${a.length} dips. Kept in this browser only.`; };
  C.forEach(c => { $('.vtpick', c).hidden = false; show(c, A[c.dataset.dip]); });
  root.addEventListener('click', e => { const b = e.target.closest('[data-vt]'), c = b && b.closest('.vtcard');
    if (c){ A[c.dataset.dip] = b.dataset.vt; show(c, b.dataset.vt); score(); } else if (e.target.id === 'vtreset'){ A = {}; C.forEach(c => show(c)); score(); } });
  score();
}
// ---------- router ----------
const RENDER = {overview: () => {}, sky: renderSky, galaxy: renderGalaxy, methods: renderMethods, mission: renderMission, catalogue: renderCatalogue, planet: () => {}, star: () => {}, variables: renderVariables, transit: renderTransit,
  explorer: () => { renderExplorer(); renderDiscoveries(); }, sentinels: () => { renderSentinels(); renderPanel(); }, candidates: renderCandidates, planets: renderPlanets, runs: renderRuns,
  leaderboard: () => {}, docs: () => {}, pictures: () => {}, stellar: () => {}, stellardocs: () => {}, propose: () => {}, tessnow: tnWire, vetter: vtWire, editions: () => {}, notfound: () => {}};
const rendered = new Set();
const META = D.route_meta, MX_FIRST = Object.keys(D.chapter_titles)[0];
const ROUTES = () => $$('#content > .route').map(s => s.dataset.route);
// The page the address names: a clean path, its query (a deep link's view), and for a case file the section in its hash.
function parseLoc(){
  const p = rtParse(location.pathname, location.search) || {route: document.body.dataset.page === 'notfound' ? 'notfound' : (document.body.dataset.page || 'overview'), params: {}};
  if (!$('#route-' + p.route)) p.route = 'notfound';
  // A dip address the run does not hold is not found: never another dip in its place. One the run once held says so.
  let gone = '';
  if ((p.route === 'transit' || p.route === 'candidates') && p.params.dip && !((D.routes.dips || {})[p.params.dip])){
    gone = (D.routes.gone || []).includes(p.params.dip) ? p.params.dip : ''; p.route = 'notfound';
  }
  nfSay(gone);
  const params = new URLSearchParams(p.params);
  if (p.route === 'candidates' && location.hash.length > 1 && !params.has('section')) params.set('section', location.hash.slice(1));
  return {route: p.route, params};
}
// The not-found page, or "this dip is no longer in the run" for an address a dip once had (D.routes.gone).
function nfSay(gone){
  const h = $('#h-notfound'), p = h && h.closest('header').querySelector('p'); if (!h || !p) return;
  if (!h.dataset.plain) { h.dataset.plain = h.textContent; p.dataset.plain = p.textContent; }
  h.textContent = gone ? 'This dip is no longer in the run.' : h.dataset.plain;
  p.innerHTML = gone ? `The address /candidates/${esc(gone)}/ belonged to a dip that a later version of the run no longer holds. Its number is not given to another dip. <a href="${esc(rtUrl('explorer'))}">See the dips the run holds now ›</a>` : esc(p.dataset.plain);
}
let current = null;
// The header follows the page: the section it belongs to, its breadcrumbs (deep pages only), its sub-navigation and title.
function pageChrome(r, params){
  const m = META[r] || {}, h1 = $('#route-' + r + ' h1');
  $$('.nav a[data-nav], .menu a[data-nav]').forEach(a => { if (a.dataset.nav === m.nav) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const win = r === 'candidates' ? (D.dips || {})[params.get('dip')] : null;
  const name = r === 'methods' ? (D.chapter_titles[params.get('ch')] || m.label) : win ? win.label : (r === 'planet' || r === 'star' || r === 'transit') && h1 ? h1.textContent.trim() : m.label;
  document.title = m.title_tpl ? m.title_tpl.replace('{name}', name) : `${m.label} · SetuHQ`;
  const crumbs = $('#crumbs');
  if (crumbs){
    const chain = (m.crumbs || []).map(([label, href]) => `<li><a href="${esc(href)}">${esc(label)}</a></li>`);
    if (r === 'methods' && params.get('ch') && params.get('ch') !== MX_FIRST) chain.push(`<li><a href="${esc(rtUrl('methods'))}">How it works</a></li>`);
    if (r === 'candidates' && params.get('dip')) chain.push(`<li><a href="${esc(transitHref(params.get('dip')))}">${esc(DIP_NAME(params.get('dip')) || params.get('dip'))}</a></li>`);
    crumbs.hidden = !chain.length;
    crumbs.innerHTML = chain.length ? `<ol>${chain.join('')}<li aria-current="page">${esc(r === 'candidates' ? 'Case file' : name)}</li></ol>` : '';
  }
  const sub = $('#subnav');
  if (sub){
    const items = (D.subnav[m.nav] || []);
    sub.hidden = !items.length;
    sub.innerHTML = items.map(([label, route, routes]) => `<a href="${esc(R(route))}"${routes.includes(r) ? ' aria-current="page"' : ''}>${esc(label)}</a>`).join('');
  }
  const cv = $('#copyview'); if (cv) cv.hidden = !VIEW_QUERY[r];
}
function show(r, moveFocus, params){
  for (const id of ROUTES()) $('#route-' + id).hidden = id !== r;
  document.body.dataset.route = r;
  if (!rendered.has(r)){ RENDER[r](); rendered.add(r); }
  else if (r === 'explorer'){ renderOverview(); renderDiscCharts(false); }
  if (r === 'explorer' && !rendered.has('widgets')){ renderOverview(); rendered.add('widgets'); }
  if (moveFocus){ const h = $('#route-' + r + ' h1'); if (h) h.focus({preventScroll: true}); window.scrollTo(0, 0); }
  if (r === 'candidates') fitFrame();
  missionShown(r === 'mission');
  gxShown(gxWanted());
  mxShown(r === 'methods');
  mxIntroRoute(r);
  txSysShown(r === 'transit');
  plShown(r);
  // The shared renderer upgrades the view's pictures; the header settles; counters roll (setuhq.design, setuhq.renderer).
  const sec = $('#route-' + r);
  if (window.SetuRender && sec) SetuRender.mount(sec);
  if (window.SetuUI){ SetuUI.settle(); SetuUI.odometer(sec); SetuUI.limits(sec); }
}
// A change of view in place is a view transition (V13), except under reduced motion or on the first draw.
function viewTransition(f){
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches || document.hidden) return f();
  try { const t = document.startViewTransition(f); [t.ready, t.finished, t.updateCallbackDone].forEach(q => q && q.catch(() => {})); }
  catch (e) { f(); }
}
function go(p, moveFocus){
  // A new page moves focus to its heading; a new chapter keeps focus where it is (the Learn bar, the contents) and scrolls up.
  const changed = p.route !== current || ['planet', 'star', 'transit'].includes(p.route);
  if (p.route === 'methods' && current === 'methods' && moveFocus) window.scrollTo(0, 0);
  if (p.route === 'explorer'){
    if (p.params.has('layout')){
      layout = decodeLayout(p.params.get('layout'), WIDGET_IDS, D.default_size);
      sharedView = encodeLayout(layout) !== encodeLayout(ownLayout);
    } else if (p.route !== current){ layout = ownLayout.map(x => ({...x})); sharedView = false; }
  }
  if (p.route === 'sky'){
    applySky(decodeSkyView(p.params));
    applySkyLayers(decodeLayers(p.params));
    if (rendered.has('sky')) renderSky();
  }
  if (p.route === 'galaxy' && GXM) applyGalaxy(decodeGalaxyView(p.params));
  if (p.route === 'catalogue' && CTM) applyCatalogue(decodeCatView(p.params));
  if (p.route === 'variables' && VA) applyVariables(decodeVarView(p.params));
  if (p.route === 'explorer'){
    const beforeEx = encodeExView(currentEx());
    applyEx(decodeExView(p.params));
    if (rendered.has('explorer') && beforeEx !== encodeExView(currentEx())) renderExplorer();
    const fromURL = ['sort', 'dir', 'filter'].some(k => p.params.has(k));
    const before = currentFeedView();
    applyFeedView(fromURL ? decodeFeedView(p.params) : ownFeedView);
    if (rendered.has('explorer') && encodeFeedView(before) !== encodeFeedView(currentFeedView())){ renderDiscChips(); renderDiscTable(); }
  }
  current = p.route;
  show(p.route, moveFocus && changed, p.params);
  if (p.route === 'methods') mxShowChapter(p.params.get('ch'));
  if (p.route === 'planet') plShow(p.params.get('id') || '');
  if (p.route === 'star') stShow(p.params.get('id') || '');
  if (p.route === 'mission'){ applyMission(decodeMission(p.params)); gxShown(gxWanted()); }
  learnVisit(p);
  if (p.route === 'transit') openTransit(p.params.get('dip'));
  if (p.route === 'candidates') openDip(p.params.get('dip'), p.params.get('section'));
  if (p.route === 'explorer') $('#sharednote').hidden = !sharedView;
  pageChrome(p.route, p.params);
}
// In-app links: a click on a link to another page of the app changes the page in place (History API), so the
// header, the loaded data and the theme stay; the address is the page's own, and Back and Forward work as usual.
document.addEventListener('click', e => {
  const a = e.target.closest('a[href]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target || a.hasAttribute('download')) return;
  let u; try { u = new URL(a.getAttribute('href').startsWith('#/') ? R(a.getAttribute('href')) : a.href, location.href); } catch (err) { return; }
  if (u.origin !== location.origin) return;
  if (u.pathname === location.pathname && u.search === location.search && u.hash && current !== 'candidates') return;  // an anchor on this page
  const p = rtParse(u.pathname, u.search);
  if (!p || !$('#route-' + p.route)) return;  // a page outside the app (the report, the plates): a normal load
  e.preventDefault();
  navTo(u.href);
});
// Open an address: in place when it is a page of the app, else by a normal load.
function navTo(href){
  const u = new URL(R(href), location.href), p = u.origin === location.origin ? rtParse(u.pathname, u.search) : null;
  const gsd = $('#gsearch'); if (gsd && gsd.open) gsd.close();
  closeMenu();
  if (!p || !$('#route-' + p.route)){ location.href = u.href; return; }
  try { history.pushState(null, '', u.pathname + u.search + u.hash); } catch (err) { location.href = u.href; return; }
  viewTransition(() => go(parseLoc(), true));
}
// Back and Forward change the view at once (a page restored from the back-forward cache must not wait on a transition).
window.addEventListener('popstate', () => { const gsd = $('#gsearch'); if (gsd && gsd.open) gsd.close(); closeMenu(); go(parseLoc(), true); });
$('.skip').addEventListener('click', e => { e.preventDefault(); const c = $('#content'); c.focus({preventScroll: true}); c.scrollIntoView(); });
// ---------- "Copy link to this view": the one way view settings reach an address ----------
const VIEW_QUERY = {
  explorer: () => [layoutIsDefault() ? '' : 'layout=' + encodeLayout(layout), encodeFeedView(currentFeedView()) === encodeFeedView(D.feed_view.default) ? '' : encodeFeedView(currentFeedView()), encodeExView(currentEx())].filter(Boolean).join('&'),
  sky: () => encodeSkyView(currentSky()) + (skyLayers.length ? '&layers=' + skyLayers.join(',') : ''),
  galaxy: () => (typeof gx !== 'undefined' && gx.view) ? encodeGalaxyView(gx.view) : '',
  catalogue: () => (typeof ct !== 'undefined' && ct.view) ? encodeCatView(ct.view) : '',
  variables: () => (typeof va !== 'undefined' && va.view) ? encodeVarView(va.view) : '',
};
function layoutIsDefault(){ return encodeLayout(layout) === encodeLayout(normaliseLayout(null, WIDGET_IDS, D.default_size)); }
function viewLink(r){ const q = (VIEW_QUERY[r] || (() => ''))(); return location.origin + location.pathname + (q ? '?' + q : ''); }
async function copyViewLink(r, state, box){
  const url = viewLink(r);
  try { await navigator.clipboard.writeText(url); if (box) box.hidden = true; say('Link to this view copied.'); if (state) state.textContent = 'Link copied.'; }
  catch (e) { if (box){ box.hidden = false; box.value = url; box.focus(); box.select(); } say('Copy the selected link to share this view.'); if (state) state.textContent = box ? '' : url; }
  if (state) setTimeout(() => { state.textContent = ''; }, 4000);
}
document.addEventListener('click', e => { if (e.target.closest('[data-open-search]')) gsOpen(); });
if ($('#copyview')) $('#copyview').addEventListener('click', () => copyViewLink(current, $('#copyviewstate'), $('#copyviewbox')));
// The sticky top bar's height sets --top, which the case file's frame uses.
function measureTop(){ const t = $('.topbar'); if (t) document.documentElement.style.setProperty('--top', Math.ceil(t.getBoundingClientRect().height) + 'px'); }
measureTop();
if (window.ResizeObserver) new ResizeObserver(measureTop).observe($('.topbar'));
let rt = null;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if ($('#route-explorer') && !$('#route-explorer').hidden) renderDiscCharts(false); resizeCalibration(); fitFrame(); }, 120); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { measureTop(); fitFrame(); });  // web fonts can rewrap the header
try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', theme: currentTheme()}, '*'); } catch (e) { /* no frame yet */ }
document.addEventListener('setuhq-theme', e => { try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', theme: e.detail}, '*'); } catch (err) { /* no frame yet */ } });
$('#dippick').addEventListener('change', e => navTo(dipHref(e.target.value)));
// An old in-app address (#/galaxy?focus=x), typed, bookmarked or followed, lands on its page.
function fromOldHash(){ if (!location.hash.startsWith('#/')) return false; setAddress(rtFromHash(location.hash, true), false); return true; }
window.addEventListener('hashchange', () => { if (fromOldHash()) go(parseLoc(), true); });
fromOldHash();
go(parseLoc(), false);

const I18N_SRC = '/assets/i18n-a967e539f3.js';
const SETUHQ_THEMES = ['dark', 'light', 'system'], TT = (id, en, a) => (window.SetuI18n ? SetuI18n.T(id, en, a) : en).replace(/&#(\d+);/g, (x, d) => String.fromCharCode(d));
const THEME_SAY = {get dark(){ return TT('shell.theme.dark', 'dark'); }, get light(){ return TT('shell.theme.light', 'light'); }, get system(){ return TT('shell.theme.system', 'your device\'s setting'); }};
function currentTheme(){ const t = document.documentElement.getAttribute('data-theme'); return SETUHQ_THEMES.includes(t) ? t : 'dark'; }
function applyTheme(t, announce){
document.documentElement.setAttribute('data-theme', t);
try { if (t === 'dark') localStorage.removeItem('setuhq-theme'); else localStorage.setItem('setuhq-theme', t); } catch (e) {  }
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
if (e.key === 'Tab'){
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
window.D = D;
const s = document.createElement('script');
s.src = b.app;
s.onload = () => { document.documentElement.dataset.ready = '1'; };
s.onerror = () => { const n = document.getElementById('bootnote'); if (n) n.hidden = false; };
document.body.appendChild(s);
}).catch(err => {
const n = document.getElementById('bootnote'); if (n) n.hidden = false;
console.warn('SetuHQ: the interactive views could not load', err);
});
}
(function(){
const c = document.body.dataset.chrome;
if (!c){ initShell(); bootApp(); if (window.SetuI18n) SetuI18n.ready.then(() => applyTheme(currentTheme(), false)); return; }
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
window.SetuUI = window.SetuUI || {};
SetuUI.rm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
(function(){
let raf = 0;
const settle = () => { raf = 0; const t = document.querySelector('.topbar'); if (!t) return;
const home = document.body.dataset.route === 'overview'; t.classList.toggle('settled', !home || window.scrollY > 40); };
addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(settle); }, {passive: true});
SetuUI.settle = settle;
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', settle); else settle();
})();
SetuUI.odometer = function(root){
const els = (root || document).querySelectorAll('.odo[data-odo]:not([data-odo-on])');
if (SetuUI.rm() || !('IntersectionObserver' in window)) return;
const io = new IntersectionObserver(es => es.forEach(en => { if (!en.isIntersecting) return; io.unobserve(en.target); roll(en.target); }), {rootMargin: '0px 0px -10% 0px'});
els.forEach(el => { el.dataset.odoOn = '1'; io.observe(el); });
function roll(el){
const text = el.dataset.odo; el.setAttribute('aria-label', el.getAttribute('aria-label') || text);
el.innerHTML = Array.from(text).map(ch => /\d/.test(ch) ? `<span class="odd" aria-hidden="true"><span>${'0123456789'.split('').map(d => `<span>${d}</span>`).join('')}</span></span>` : `<span aria-hidden="true">${ch.replace(/[<&]/g, '')}</span>`).join('');
const cols = el.querySelectorAll('.odd>span'), digits = text.replace(/\D/g, '');
cols.forEach((c, i) => { c.style.transitionDelay = Math.min(1200 - 600, i * 60) + 'ms'; });
requestAnimationFrame(() => requestAnimationFrame(() => cols.forEach((c, i) => { c.style.transform = `translateY(-${Number(digits[i])}em)`; })));
}
};
SetuUI.crosshair = function(el, o){
if (!el || el._xh) return; el._xh = true;
const box = el.parentElement; if (getComputedStyle(box).position === 'static') box.style.position = 'relative';
const rule = document.createElement('span'); rule.className = 'xhair'; rule.hidden = true; box.appendChild(rule);
const out = o.readout || (() => { const p = document.createElement('p'); p.className = 'xread'; p.setAttribute('aria-live', 'polite'); box.after(p); return p; })();
el.tabIndex = 0;
let i = -1;
const xs = o.xs || [];
const place = k => { if (!xs.length) return; i = Math.max(0, Math.min(xs.length - 1, k));
const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(), f = (xs[i] - o.x0) / ((o.x1 - o.x0) || 1);
rule.style.left = (r.left - b.left + f * r.width) + 'px'; rule.hidden = false; out.textContent = o.fmt(i); };
const nearest = px => { const r = el.getBoundingClientRect(), x = o.x0 + (px - r.left) / r.width * (o.x1 - o.x0); let best = 0;
xs.forEach((v, k) => { if (Math.abs(v - x) < Math.abs(xs[best] - x)) best = k; }); return best; };
el.addEventListener('pointermove', e => place(nearest(e.clientX)));
el.addEventListener('pointerleave', () => { rule.hidden = true; });
el.addEventListener('keydown', e => { if (e.key === 'ArrowRight' || e.key === 'ArrowLeft'){ e.preventDefault(); place((i < 0 ? 0 : i) + (e.key === 'ArrowRight' ? 1 : -1)); } });
el.addEventListener('blur', () => { rule.hidden = true; });
};
(function(){
const LIM = {"real data, cited": "Stored measurements, binned or folded as stored.", "model from stored values": "A model drawn from stored numbers; not an image of the object.", "artist's impression": "Not an observation: a look chosen from measured radius and irradiation.", "illustration": "Explains an idea; not data.", "speculative model": "Beyond what is measured: a possibility, not a result."}, LID = {"label.real": "real data, cited", "label.model": "model from stored values", "label.art": "artist's impression", "label.illustration": "illustration", "label.speculative": "speculative model"}, K = 'setuhq-hints', q = (s, e) => Array.from((e || document).querySelectorAll(s));
const TT = (id, en, a) => window.SetuI18n ? SetuI18n.T(id, en, a) : en;
const esc = s => String(s).replace(/[&<>"]/g, c => '&#' + c.charCodeAt(0) + ';'), seen = () => { try { return JSON.parse(localStorage.getItem(K)) || []; } catch (e) { return []; } };
SetuUI.limits = root => q('.stage-tag', root).forEach(tag => {
if (window.SetuI18n) SetuI18n.apply(tag);
const st = tag.closest('.stage'); if (!st || st._sl || (st.offsetWidth && st.offsetWidth < 200)) return; st._sl = 1;
const id = tag.dataset.i18n, en = LID[id] || tag.textContent.trim().toLowerCase(), fig = st.closest('figure') || st, lab = tag.textContent.trim(), cap = fig.querySelector('figcaption') || document.getElementById(fig.getAttribute('aria-labelledby') || '-'), h = fig.dataset.hint;
const src = ((cap && cap.textContent.match(/Sources?:\s*([^]*?)(?:\.\s+(?=[A-Z])|\.?\s*$)/)) || [])[1];
const lim = LIM[en] ? TT('limits.' + (id || '').slice(6), LIM[en]) : '', s = src ? esc(src) : TT('limits.caption', 'as the caption states');
requestAnimationFrame(() => { const b = st.querySelector('.srclim>summary'); if (b && b.offsetWidth) st.style.setProperty('--slw', (b.offsetWidth + 16) + 'px'); });
st.insertAdjacentHTML('beforeend', `<details class="srclim"><summary>${TT('limits.summary', 'Source / limits')}</summary><div><p><b>${esc(lab)}.</b> ${lim}</p><p>${TT('limits.source', 'Source: {s}.', {s})}</p></div></details>`
+ (h && !seen().includes(h) ? `<p class="fxhint">${esc(TT('hint.orbits', h))} <button type="button" class="btn" data-fxh="${esc(h)}" aria-label="${TT('hint.dismiss', 'Dismiss the hint: {h}', {h: TT('hint.orbits', h)})}">×</button></p>` : ''));
});
addEventListener('click', e => {
const b = e.target.closest('[data-fxh]'), c = e.target.closest('[data-copy]');
if (b){ const s = seen(), m = b.closest('.stage').querySelector('summary'); s.push(b.dataset.fxh); try { localStorage.setItem(K, JSON.stringify(s)); } catch (x) {}
q('.fxhint').forEach(p => p.lastChild.dataset.fxh === b.dataset.fxh && p.remove()); m.focus(); }
if (c){ const say = c.parentNode.querySelector('[role=status]'), no = () => { getSelection().selectAllChildren(c.previousElementSibling); say.textContent = 'Address selected: press Ctrl or Cmd C'; };
navigator.clipboard ? navigator.clipboard.writeText(c.dataset.copy).then(() => { say.textContent = 'Copied ' + c.dataset.copy; }, no) : no(); }
});
addEventListener('keydown', e => { const d = e.key === 'Escape' && e.target.closest && e.target.closest('.srclim[open]'); if (d){ d.open = false; d.firstChild.focus(); } });
})();

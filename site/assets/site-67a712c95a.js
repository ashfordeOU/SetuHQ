
// ---------- the shell: theme, menu, and the app's start ----------
// Runs on every page before the app's data arrives, so the header works at once.
const SETUHQ_THEMES = ['dark', 'light', 'system'], THEME_SAY = {dark: 'dark', light: 'light', system: "your device's setting"};
function currentTheme(){ const t = document.documentElement.getAttribute('data-theme'); return SETUHQ_THEMES.includes(t) ? t : 'dark'; }
function applyTheme(t, announce){
  document.documentElement.setAttribute('data-theme', t);
  try { if (t === 'dark') localStorage.removeItem('setuhq-theme'); else localStorage.setItem('setuhq-theme', t); } catch (e) { /* storage blocked: the theme lasts for this visit */ }
  const next = SETUHQ_THEMES[(SETUHQ_THEMES.indexOf(t) + 1) % SETUHQ_THEMES.length];
  for (const b of document.querySelectorAll('[data-theme-toggle]')){ b.setAttribute('aria-label', `Colour theme: ${THEME_SAY[t]}. Switch to ${THEME_SAY[next]}`); b.title = `Theme: ${THEME_SAY[t]}`; }
  if (announce){ const a = document.getElementById('announce'); if (a){ a.textContent = ''; setTimeout(() => { a.textContent = `Theme: ${THEME_SAY[t]}.`; }, 30); } }
  document.dispatchEvent(new CustomEvent('setuhq-theme', {detail: t}));
}
function closeMenu(focusButton){
  const m = document.getElementById('menu'), b = document.getElementById('menubtn');
  if (!m || m.hidden) return;
  m.hidden = true; b.setAttribute('aria-expanded', 'false'); b.setAttribute('aria-label', 'Open the menu');
  if (focusButton) b.focus();
}
function openMenu(){
  const m = document.getElementById('menu'), b = document.getElementById('menubtn');
  m.hidden = false; b.setAttribute('aria-expanded', 'true'); b.setAttribute('aria-label', 'Close the menu');
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
               fetch(b.routes).then(r => { if (!r.ok) throw new Error(r.status); return r.text(); })]).then(([D, routes]) => {
    const tpl = document.createElement('template'); tpl.innerHTML = routes;
    const content = document.getElementById('content');
    const sys = tpl.content.querySelector('template#mxsystpl');
    if (sys && !document.getElementById('mxsystpl')) document.body.appendChild(sys);
    for (const sec of Array.from(tpl.content.querySelectorAll('section.route'))){
      const mine = document.getElementById(sec.id);
      if (mine && !mine.hasAttribute('data-partial')) continue;
      if (mine){ sec.hidden = mine.hidden; mine.replaceWith(sec); }
      else { sec.hidden = true; content.appendChild(sec); }
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
  if (!c){ initShell(); bootApp(); return; }
  fetch(c).then(r => { if (!r.ok) throw new Error(r.status); return r.text(); }).then(t => {
    const tpl = document.createElement('template'); tpl.innerHTML = t;
    const top = tpl.content.querySelector('[data-chrome-part="top"]'), bottom = tpl.content.querySelector('[data-chrome-part="bottom"]');
    if (top) document.getElementById('chrome-top').replaceWith(...top.childNodes);
    if (bottom) document.getElementById('chrome-bottom').replaceWith(...bottom.childNodes);
  }).catch(err => console.warn('SetuHQ: the header could not load', err)).then(() => { initShell(); bootApp(); });
})();

// ---------- design.MOTION_JS: the header settles; counters roll; still under reduced motion ----------
window.SetuUI = window.SetuUI || {};
SetuUI.rm = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
(function(){
  // S01: on the home page the bar is clear over the hero and fills after 40 px of scroll; elsewhere it is filled.
  let raf = 0;
  const settle = () => { raf = 0; const t = document.querySelector('.topbar'); if (!t) return;
    const home = document.body.dataset.route === 'overview'; t.classList.toggle('settled', !home || window.scrollY > 40); };
  addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(settle); }, {passive: true});
  SetuUI.settle = settle;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', settle); else settle();
})();
// V10: roll each [data-odo] counter to its value when it comes into view (60 ms per digit, at most 1.2 s in all).
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

// ---------- design.CROSSHAIR_JS (S06): a chart answers on hover, and on the arrow keys when it has focus ----------
// SetuUI.crosshair(el, {x0, x1, xs: [x values in data units], fmt(i) -> text, readout: element})
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

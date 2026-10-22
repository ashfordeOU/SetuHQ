
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

const I18N_CONF = {"locales":["en","nl","pl","pt","fi","sv","da","nb","cs","uk","ru","de","fr","es","et","ja","zh-Hans"],"cat":{"nl":"/assets/i18n/nl-d9ad87bd0b.json","pl":"/assets/i18n/pl-d442c22bf5.json","pt":"/assets/i18n/pt-78804adf78.json","fi":"/assets/i18n/fi-94e01bb627.json","sv":"/assets/i18n/sv-2f4043ce5d.json","da":"/assets/i18n/da-ab064368c9.json","nb":"/assets/i18n/nb-c3dcfbe6bd.json","cs":"/assets/i18n/cs-3dd855e093.json","uk":"/assets/i18n/uk-94fdd3882b.json","ru":"/assets/i18n/ru-03a90992b2.json","de":"/assets/i18n/de-1961b44c42.json","fr":"/assets/i18n/fr-af37f65ab1.json","es":"/assets/i18n/es-8c98d5d9d1.json","et":"/assets/i18n/et-a1b655f027.json","ja":"/assets/i18n/ja-68eb9a35e5.json","zh-Hans":"/assets/i18n/zh-Hans-342ae8e80e.json"},"main":["/","/candidates/","/candidates/be-the-vetter/","/candidates/radius-ratios/","/catalogue/","/catalogue/everything-that-dims/","/docs/","/docs/cheops-proposals/","/docs/pictures/","/docs/stellar/","/editions/","/evidence/","/evidence/leaderboard/","/evidence/runs/","/evidence/stellar/","/explore/","/explore/galaxy/","/explore/mission-control/","/explore/tess-now/","/how-it-works/","/how-it-works/astrometry/","/how-it-works/atmospheres/","/how-it-works/direct-imaging/","/how-it-works/doppler-shift/","/how-it-works/equations-of-life/","/how-it-works/false-positives/","/how-it-works/history/","/how-it-works/microlensing/","/how-it-works/molecules-and-life/","/how-it-works/population/","/how-it-works/radial-velocity/","/how-it-works/radio/","/how-it-works/timing/","/how-it-works/transits/"],"auto":"/assets/i18n-auto-2d102e3b12.js"};
(function(){
const C = I18N_CONF, H = document.documentElement, K = 'setuhq-lang', st = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } };
const P = C.locales.includes(H.lang) ? H.lang : 'en', auto = document.body && (document.body.hasAttribute('data-i18n-auto') || document.body.hasAttribute('data-chrome')), S = st(K);
const lang = P !== 'en' ? P : (auto && C.locales.includes(S) ? S : 'en');
const esc = s => String(s).replace(/[&<>"]/g, c => '&#' + c.charCodeAt(0) + ';');
function fmt(m, a, L){
a = a || {}; let i = 0;
const num = (v, s) => { const o = {}; if (s === 'integer') o.maximumFractionDigits = 0; else if (s === 'percent' || s === '::percent') o.style = 'percent';
else { const d = /^::\s*\.(0*)$/.exec(s || ''); if (d) o.minimumFractionDigits = o.maximumFractionDigits = d[1].length; else o.maximumFractionDigits = 3; }
return L === 'en' && o.style !== 'percent' ? new Intl.NumberFormat('en-US', o).format(v) : new Intl.NumberFormat(L, o).format(v); };
const date = v => { const d = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v)); if (!d) return esc(v); if (L === 'en') return d[0];
return new Intl.DateTimeFormat(L, {year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC'}).format(new Date(Date.UTC(+d[1], d[2] - 1, +d[3]))); };
function text(pl, n){
let o = '';
while (i < m.length){
const c = m[i], d = m[i + 1];
if (c === "'"){ if (d === "'"){ o += c; i += 2; continue; }
if ('{}|'.includes(d) || (pl && d === '#')){ const j = m.indexOf("'", i + 1); o += m.slice(i + 1, j); i = j + 1; continue; } }
if (c === '}') return o;
if (c === '#' && pl){ o += num(n); i++; continue; }
if (c === '{'){ i++; o += arg(); continue; }
o += c; i++;
}
return o;
}
function arg(){
const h = /^\s*(\w+)\s*(?:,\s*(\w+)\s*,?)?/.exec(m.slice(i)); i += h[0].length;
const v = a[h[1]], ty = h[2];
if (!ty){ i = m.indexOf('}', i) + 1; return v === undefined ? '{' + h[1] + '}' : esc(v); }
if (ty === 'number' || ty === 'date'){ const j = m.indexOf('}', i), s = m.slice(i, j).trim(); i = j + 1; return ty === 'date' ? date(v) : num(v, s); }
const of = /^\s*offset:\s*(\d+)/.exec(m.slice(i)); let off = 0; if (of){ off = +of[1]; i += of[0].length; }
const n = +v - off, cat = ty === 'plural' ? new Intl.PluralRules(L).select(n) : String(v); let ex = null, hit = null, oth = '';
for (;;){ const b = /^\s*(=?[\w-]+)\s*\{/.exec(m.slice(i)); if (!b) break; i += b[0].length; const body = text(ty === 'plural', n); i++;
if (b[1] === '=' + v) ex = body; else if (b[1] === cat) hit = body; if (b[1] === 'other') oth = body; }
i = m.indexOf('}', i) + 1;
return ex !== null ? ex : hit !== null ? hit : oth;
}
return text(false);
}
const SI = window.SetuI18n = {lang, page: P, cat: null, conf: C,
T: (id, en, a) => { const m = (SI.cat && SI.cat[id]) || en || id; return lang === 'en' && !a && m.indexOf('{') < 0 ? m : fmt(m, a, lang); },
fmt: (m, a, L) => fmt(m, a, L || lang),
href: h => { if (lang === 'en' || !h || h[0] !== '/' || h[1] === '/') return h; const u = h.split(/(?=[?#])/), p = u.shift(); return C.main.includes(p) ? '/' + lang + p + u.join('') : h; },
apply(root){
if (!SI.cat || !root) return;
const els = [...(root.querySelectorAll ? root.querySelectorAll('[data-i18n],[data-i18n-attr],a[href^="/"]') : [])];
if (root.matches && root.matches('[data-i18n],[data-i18n-attr]')) els.push(root);
for (const el of els){
let a; try { a = JSON.parse(el.dataset.i18nArgs || '{}'); } catch (e) { a = {}; }
for (const k in a) if (k.endsWith('@') && SI.cat[a[k]]) a[k.slice(0, -1)] = fmt(SI.cat[a[k]], {}, lang);
const id = el.dataset.i18n; if (id && SI.cat[id]){ el.innerHTML = fmt(SI.cat[id], a, lang); for (const x of el.querySelectorAll('a[href^="/"]')) x.setAttribute('href', SI.href(x.getAttribute('href'))); }
for (const s of (el.dataset.i18nAttr || '').split('|').filter(Boolean)){ const [n, k] = s.split(':'); if (SI.cat[k]) el.setAttribute(n, fmt(SI.cat[k], a, lang).replace(/&#(\d+);/g, (x, d) => String.fromCharCode(d))); }
if (el.tagName === 'A'){ const h = el.getAttribute('href'), n = SI.href(h); if (n !== h) el.setAttribute('href', n); }
}
marks(root);
if (SI.auto) SI.auto(root);
}};
function marks(root){
if (!root.querySelectorAll) return;
for (const n of root.querySelectorAll('.mtnote')) n.hidden = false;
for (const n of root.querySelectorAll('.langcode')) n.textContent = lang === 'zh-Hans' ? 'ZH' : lang.toUpperCase();
for (const a of root.querySelectorAll('.langmenu a[data-lang]')) if (a.dataset.lang === lang) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
}
const load = L => fetch(C.cat[L]).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
SI.ready = lang === 'en' ? Promise.resolve() : load(lang).then(c => { SI.cat = c; H.lang = lang; SI.apply(document);
if (C.auto){ const x = document.createElement('script'); x.src = C.auto; document.head.appendChild(x); }
}).catch(e => console.warn('SetuHQ: the translation could not load', e));
document.addEventListener('click', e => {
const a = e.target.closest('a[data-lang]'); if (!a) return;
st(K, a.dataset.lang); st(K + '-hint', '1');
if (a.getAttribute('href') === location.pathname || auto){ e.preventDefault(); location.reload(); }
});
const alt = l => { const x = document.querySelector('link[rel=alternate][hreflang="' + l + '"]'); return x ? new URL(x.href).pathname : null; };
let want = C.locales.includes(S) ? S : null;
if (!want && !st(K + '-hint')) for (const l of navigator.languages || []){ const b = l.toLowerCase(), c = b.startsWith('zh') ? (/hant|tw|hk|mo/.test(b) ? null : 'zh-Hans') : /^n[on]\b/.test(b) ? 'nb' : b.split('-')[0]; if (C.locales.includes(c)){ want = c; break; } }
if (want && want !== lang && (alt(want) || auto)){
const go = alt(want) || location.pathname;
(want === 'en' ? Promise.resolve({}) : load(want)).then(c => {
const f = (id, en) => fmt(c[id] || en, {}, want), b = document.createElement('div');
b.className = 'langhint'; b.lang = want; b.setAttribute('role', 'region'); b.setAttribute('aria-label', f('i18n.suggest.label', 'Language'));
b.innerHTML = `<p>${f('i18n.suggest.text', 'This page is also in English.')} <a href="${esc(go)}" data-lang="${esc(want)}">${f('i18n.suggest.go', 'Read it in English')}</a></p><button type="button" class="btn" aria-label="${f('i18n.suggest.dismiss', 'Dismiss')}">×</button>`;
b.querySelector('button').onclick = () => { st(K + '-hint', '1'); if (!S) st(K, lang); b.remove(); };
document.body.prepend(b);
}).catch(() => {});
}
})();

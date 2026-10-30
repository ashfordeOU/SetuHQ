(function(){
const SI = window.SetuI18n; if (!SI) return;
const BL = /^(P|LI|H[1-6]|FIGCAPTION|TD|TH|DT|DD|SUMMARY|CAPTION|LABEL|BUTTON|LEGEND|BLOCKQUOTE|A|DIV|SPAN|B|STRONG|EM|SMALL|HEADER|FOOTER|SECTION|ASIDE|FIGURE|OPTION|TEXT|TSPAN)$/,
IL = /^(A|B|STRONG|I|EM|CODE|SPAN|SUB|SUP|ABBR|SMALL|BR|WBR|KBD|MARK|TIME|Q|CITE|S|U|VAR|BDI|DATA)$/i,
SKX = 'script,style,svg,template,pre,canvas,noscript,textarea,select,[data-i18n],[translate=no],.langpick,.langhint',
NUM = /(?<![\w.\-−])[-−+]?\d+(?:[.,:]\d+)*(?!\w)|(?<=[-–−])\d+(?:[.,]\d+)*(?!\w)/g, ATS = ['aria-label', 'alt', 'title', 'placeholder'],
DONE = new WeakMap();
const h53 = s => { let a = 0xdeadbeef, b = 0x41c6ce57; for (let i = 0; i < s.length; i++){ const c = s.charCodeAt(i); a = Math.imul(a ^ c, 2654435761); b = Math.imul(b ^ c, 1597334677); }
a = Math.imul(a ^ (a >>> 16), 2246822507) ^ Math.imul(b ^ (b >>> 13), 3266489909); b = Math.imul(b ^ (b >>> 16), 2246822507) ^ Math.imul(a ^ (a >>> 13), 3266489909);
return 'js.' + (4294967296 * (2097151 & b) + (a >>> 0)).toString(36); };
const prose = t => { t = t.replace(/<[^>]*>|\{\w+\}/g, ' '); return /(^|[^\w-])[a-z][a-z']{2,}\b/.test(t) || (/\b[A-Z][a-z]{2,}\b/.test(t) && !/\d/.test(t) && t.trim().split(/\s+/).length <= 4); };
const q = s => s.replace(/'([{}])/g, "''$1").replace(/[{}]/g, "'$&'");
function tpl(html, names){
const a = {}; let k = 0, j = 0;
const t = html.split(/(<[^>]*>)/).map(p => {
if (p[0] === '<') return q(p);
let o = '', pos = 0;
const parts = [];
for (const n of names){ let i; while ((i = p.indexOf(n, pos)) >= 0 && n){ parts.push([i, n]); pos = i + n.length; } pos = 0; }
parts.sort((x, y) => x[0] - y[0]);
let last = 0;
const num = s => s.replace(NUM, m => { const key = 'n' + k++; a[key] = m; return '\u0001' + key + '\u0002'; });
for (const [i, n] of parts){ if (i < last) continue; o += num(p.slice(last, i)); const key = 's' + j++; a[key] = n; o += '\u0001' + key + '\u0002'; last = i + n.length; }
o += num(p.slice(last));
return q(o).replace(/\u0001(\w+)\u0002/g, '{$1}');
}).join('').replace(/\s+/g, ' ').trim();
return [t, a];
}
function fill(m, a){
m = m.replace(/''/g, '\u0003').replace(/'([{}])'/g, '$1').replace(/\u0003/g, "'");
return m.replace(/\{(\w+)\}/g, (x, key, at) => { const v = a[key]; if (v === undefined) return x;
if (key[0] !== 'n' || SI.lang === 'en' || /(\bBY|[A-Za-z]-|\bv|Python|DR)\s?$/.test(m.slice(0, at))) return v;
const d = /^[-−]?\d{1,3}(,\d{3})+(\.\d+)?$|^[-−]?\d+\.\d+$/.exec(v); if (!d) return v;
const f = (v.split('.')[1] || '').length; return new Intl.NumberFormat(SI.lang, {minimumFractionDigits: f, maximumFractionDigits: f}).format(+v.replace(/[,−]/g, x => x === '−' ? '-' : '')); });
}
function auto(root){
if (SI.lang === 'en' || !SI.cat || !root || !root.querySelectorAll) return;
const p = location.pathname.replace(/^\/[^/]+(?=\/)/, x => SI.conf.locales.includes(x.slice(1)) ? '' : x);
const names = SI.conf.main.includes(p) ? [] : [...new Set([...document.querySelectorAll('h1, a[href^="/planets/"], a[href^="/stars/"]')].map(e => e.textContent.trim()).filter(n => n.length > 2 && n.length < 60))].sort((x, y) => y.length - x.length);
const walk = el => {
for (const c of el.children){
if (c.matches(SKX)) continue;
for (const at of ATS){ const v = c.getAttribute(at); if (v && DONE.get(c) !== at + v && prose(v)){ const [t, a] = tpl(v.replace(/&/g, '&amp;').replace(/</g, '&lt;'), names), m = SI.cat[SI.hash(t, v)]; if (m){ const n = fill(m, a).replace(/<[^>]*>/g, '').replace(/&lt;/g, '<').replace(/&amp;/g, '&'); c.setAttribute(at, n); DONE.set(c, at + n); } } }
if (BL.test(c.tagName.toUpperCase()) && [...c.childNodes].some(n => n.nodeType === 3 && /[A-Za-z]{2}/.test(n.data)) && [...c.children].every(function ok(x){ return IL.test(x.tagName) && !x.matches('[data-i18n]') && [...x.children].every(ok); })){
const h = c.innerHTML; if (DONE.get(c) === h) continue;
const [t, a] = tpl(h, names);
if (prose(t)){ const m = SI.cat[SI.hash(t, h)]; if (m){ c.innerHTML = fill(m, a); DONE.set(c, c.innerHTML); } continue; }
}
walk(c);
}
};
walk(root.body || root);
}
let pend = null;
new MutationObserver(ms => { if (SI.lang === 'en' || !SI.cat) return; for (const x of ms){ const e = x.target.nodeType === 1 ? x.target : x.target.parentElement, t = e && (e.parentElement || e); if (t) (pend = pend || new Set()).add(t); }
if (pend && !pend.t){ pend.t = setTimeout(() => { const s = pend; pend = null; for (const t of s) if (t.isConnected) auto(t); }, 60); } }).observe(document.documentElement, {childList: true, subtree: true, characterData: true});
Object.assign(SI, {auto, tpl, prose, h53, fill, hash: h53});
const seg = location.pathname.split('/').filter(Boolean); if (SI.conf.locales.includes(seg[0])) seg.shift();
const get = s => fetch('/assets/i18n/js-1498c7949b/' + SI.lang + '/' + s + '.json').then(r => r.ok ? r.json() : {}).catch(() => ({}));
Promise.all([get('common'), get(seg[0] || 'home')]).then(cs => { if (SI.cat) Object.assign(SI.cat, ...cs); auto(document); });
})();

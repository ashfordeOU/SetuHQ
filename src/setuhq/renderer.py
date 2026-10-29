# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The shared, self-hosted renderer: stars in their blackbody colour, planets as artist's impressions chosen from
measured values (setuhq.looks), the transit, and the background starfield.

* ``RENDER_JS`` is ``window.SetuRender`` (served as /assets/render-<hash>.js, loaded with ``defer``): one WebGL1
  context per page (a hidden 512 x 512 canvas whose result is copied into each target's 2D canvas), a Canvas2D
  per-pixel fallback, and the server-rendered still ``<img>`` when neither runs. Planet surfaces are computed once
  on the CPU (equirectangular 256 x 128 per look and seed, value noise and fbm ported from the approved mock-up), so
  both paths draw the same planet; the GPU only shades the sphere.
* :func:`figure` writes the element ``SetuRender.mount`` upgrades: a ``<figure data-render>`` holding its still
  image (with alt text), its "Artist's impression" tag and its caption. Without JavaScript the still shows.
* :func:`star_svg` is a static limb-darkened disc for pages that never load the renderer (the stand-alone pages,
  the deploy-time stubs, the CLI outputs).
* The stills (``data/stills/<look>-{512,160}.webp``) are drawn by tools/render_stills.mjs on the Canvas2D path;
  ``stills.json`` records the hashes of the code and the look table that drew them, and a test fails when either
  has changed since.

Motion: an animated target runs only while on screen and the page is visible, at most 4 at once (2 on a small
touch screen), under one frame governor (30 fps when the median frame passes 20 ms, stills past 33 ms); under reduced
motion each draws its designed still once and runs no loop. A component with its own control (the home page's hero
and its Pause, a planet portrait and its Spin) runs through the same scheduler with ``SetuRender.play(el, on)``, so
``SetuRender.stats()`` counts it.
"""

from __future__ import annotations

from setuhq.i18n import lk

import hashlib
import html
import json
import shutil
from pathlib import Path

from setuhq.looks import LOOKS, STILL_SEED, teff_rgb

STILLS_DIR = Path(__file__).parent / "data" / "stills"
STILL_SIZES = (512, 160)
RENDER_BUDGET = 64_000
PICTURES = "/docs/pictures/"
LABEL_ART = "Artist's impression"


def _claret() -> list:
    from setuhq.methods import CLARET_TESS

    return [list(r) for r in CLARET_TESS]


def looks_json() -> str:
    return json.dumps(LOOKS, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def looks_sha() -> str:
    return hashlib.sha256(looks_json().encode()).hexdigest()


RENDER_JS_SRC = r"""/* SetuRender: SetuHQ's shared renderer (setuhq.renderer). Stars in their blackbody colour; planets as artist's
   impressions chosen from measured values; WebGL1 with a Canvas2D fallback and a still image beneath. */
(function(){
'use strict';
if (window.SetuRender) return;
const LOOKS = __LOOKS__, CLARET = __CLARET__;
const TAU = Math.PI * 2, RJ = 11.209, MJ = 317.83, TSUN = 5772;
const clamp = (v, a, b) => v < a ? a : v > b ? b : v, mix = (a, b, t) => a + (b - a) * t;
const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const DPR = () => Math.min(2, window.devicePixelRatio || 1);
// Deferred work waits 200 ms after it is asked for (the form Safari needs). requestIdleCallback is not used: an idle
// callback still pending holds back frames in headless Chromium, which the tests measure.
const idle = f => setTimeout(f, 200);
const mm = q => { try { return matchMedia(q).matches; } catch (e) { return false; } };
const RM = () => mm('(prefers-reduced-motion: reduce)');
const COARSE = () => mm('(pointer:coarse) and (max-width:700px)');

// ---------- noise: the mock-up's hash, value noise and fbm ----------
function h3(i, j, k){ let h = (Math.imul(i, 374761393) + Math.imul(j, 668265263) + Math.imul(k, 1274126177)) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16; return (h >>> 0) / 4294967296; }
function vn(x, y, z){
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z), xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
  return mix(mix(mix(h3(xi, yi, zi), h3(xi + 1, yi, zi), u), mix(h3(xi, yi + 1, zi), h3(xi + 1, yi + 1, zi), u), v),
             mix(mix(h3(xi, yi, zi + 1), h3(xi + 1, yi, zi + 1), u), mix(h3(xi, yi + 1, zi + 1), h3(xi + 1, yi + 1, zi + 1), u), v), w);
}
function fbm(x, y, z, o){ let a = .5, f = 1, s = 0, n = 0; for (let i = 0; i < o; i++){ s += a * vn(x * f, y * f, z * f); n += a; a *= .5; f *= 2.03; } return s / n; }
function rng(seed){ let s = seed >>> 0 || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }
function fnv(str){ let h = 0x811c9dc5; for (const b of new TextEncoder().encode(String(str))){ h ^= b; h = Math.imul(h, 0x01000193) >>> 0; } return h >>> 0; }

// ---------- physics twins (setuhq.looks.teff_rgb, setuhq.methods.ld_coeffs and transit_flux) ----------
function g(x, mu, s1, s2){ const t = (x - mu) / (x < mu ? s1 : s2); return Math.exp(-0.5 * t * t); }
function teffRGB(T){
  T = Math.min(40000, Math.max(1000, Number(T)));
  let X = 0, Y = 0, Z = 0;
  for (let lam = 380; lam <= 780; lam += 5){
    const l = lam * 1e-9, b = 1 / (l ** 5 * (Math.exp(1.4387769e-2 / (l * T)) - 1));
    X += b * (1.056 * g(lam, 599.8, 37.9, 31.0) + 0.362 * g(lam, 442.0, 16.0, 26.7) - 0.065 * g(lam, 501.1, 20.4, 26.2));
    Y += b * (0.821 * g(lam, 568.8, 46.9, 40.5) + 0.286 * g(lam, 530.9, 16.3, 31.1));
    Z += b * (1.217 * g(lam, 437.0, 11.8, 36.0) + 0.681 * g(lam, 459.0, 26.0, 13.8));
  }
  const r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z, gg = -0.9689 * X + 1.8758 * Y + 0.0415 * Z, bl = 0.0557 * X - 0.2040 * Y + 1.0570 * Z, m = Math.max(r, gg, bl);
  return [r, gg, bl].map(c => { c = Math.max(0, c / m); c = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055; return Math.round(255 * Math.min(1, c)); });
}
function ldCoeffs(teff){
  const T = CLARET, n = T.length - 1;
  if (teff <= T[0][0]) return [T[0][1], T[0][2]];
  if (teff >= T[n][0]) return [T[n][1], T[n][2]];
  for (let i = 0; i < n; i++) if (teff >= T[i][0] && teff <= T[i + 1][0]){ const f = (teff - T[i][0]) / (T[i + 1][0] - T[i][0]); return [T[i][1] + f * (T[i + 1][1] - T[i][1]), T[i][2] + f * (T[i + 1][2] - T[i][2])]; }
  return [T[n][1], T[n][2]];
}
function ldI(r, u1, u2){ const mu = Math.sqrt(Math.max(0, 1 - r * r)); return 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2; }
function overlap(z, k){
  if (z >= 1 + k) return 0;
  if (z <= 1 - k) return Math.PI * k * k;
  if (z <= k - 1) return Math.PI;
  const c = x => Math.max(-1, Math.min(1, x)), k0 = Math.acos(c((k * k + z * z - 1) / (2 * k * z))), k1 = Math.acos(c((1 - k * k + z * z) / (2 * z)));
  return k * k * k0 + k1 - 0.5 * Math.sqrt(Math.max(0, 4 * z * z - (1 + z * z - k * k) ** 2));
}
function transitFlux(z, k, u1, u2){
  const A = overlap(z, k); if (A <= 0) return 1;
  const r = z <= 1 - k ? Math.min(z, 1) : Math.min(1, (z - k + 1) / 2);
  return 1 - A * ldI(r, u1, u2) / (Math.PI * (1 - u1 / 3 - u2 / 6));
}

// ---------- the look (twin of setuhq.looks.look) ----------
const num = v => { if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null; const x = Number(v); return isFinite(x) && x > 0 ? x : null; };
function fmt(x, d){ const s = x.toFixed(d || 0), i = s.indexOf('.'), a = i < 0 ? s : s.slice(0, i); return a.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (i < 0 ? '' : s.slice(i)); }
const BANDS = [[200, 'cold'], [350, 'temperate'], [1000, 'warm'], [2000, 'hot'], [Infinity, 'ultrahot']];
const COMP = {radius: [[1.6, 'rock'], [4.0, 'envelope'], [10.0, 'neptune'], [Infinity, 'giant']], mass: [[2.0, 'rock'], [10.0, 'ambiguous'], [50.0, 'neptune'], [Infinity, 'giant']]};
function lookName(c, b){
  if (c === null) return null; if (c === 'ambiguous') return 'ambiguous'; b = b || 'warm';
  if (c === 'rock') return {cold: 'rock-cold', temperate: 'rock-temperate', warm: 'rock-warm'}[b] || 'rock-hot';
  if (c === 'giant') return {cold: 'giant-cool', temperate: 'giant-cool', warm: 'giant-warm', hot: 'giant-hot'}[b] || 'giant-ultrahot';
  return c + '-' + ({cold: 'cool', temperate: 'cool', warm: 'warm'}[b] || 'hot');
}
function look(p){
  p = p || {};
  const rj = num(p.radius), mj = num(p.mass), ms = num(p.msini);
  const rp = rj !== null ? rj * RJ : null, mp = mj !== null ? mj * MJ : (ms !== null ? ms * MJ : null);
  let comp = null, by = null;
  if (rp !== null){ by = 'radius'; comp = COMP.radius.find(e => rp < e[0])[1]; } else if (mp !== null){ by = 'mass'; comp = COMP.mass.find(e => mp < e[0])[1]; }
  let a = num(p.a), aSrc = 'a';
  if (a === null){ aSrc = 'kepler'; const M = num(p.smass), P = num(p.period); a = M !== null && P !== null ? Math.pow(M * (P / 365.25) ** 2, 1 / 3) : null; }
  const sr = num(p.srad), st = num(p.steff), s = sr !== null && st !== null && a !== null ? sr ** 2 * (st / TSUN) ** 4 / a ** 2 : null;
  const stored = num(p.teq);
  let teq = null, src = null;
  if (s !== null){ teq = 278.3 * s ** 0.25; src = 'computed'; } else if (stored !== null){ teq = stored; src = 'stored'; }
  const band = teq === null ? null : BANDS.find(e => teq < e[0])[1];
  const reasons = [];
  if (comp === null) reasons.push('No radius or mass stored, so no planet is drawn.');
  else if (by === 'radius') reasons.push(`Radius ${fmt(rp, 2)} R⊕ (exoplanet.eu) ${{rock: 'is below 1.6 R⊕, so it is drawn as rock', envelope: 'is at least 1.6 R⊕, so it is drawn with a gaseous envelope', neptune: 'is 4 to 10 R⊕, so it is drawn as a Neptune-like planet', giant: 'is at least 10 R⊕, so it is drawn as a gas giant'}[comp]}.`);
  else reasons.push(`No radius stored; ${mj !== null ? 'mass' : 'minimum mass (m sin i)'} ${fmt(mp, 1)} M⊕ (exoplanet.eu) ${{rock: 'is below 2 M⊕, so it is drawn as rock', ambiguous: 'is 2 to 10 M⊕: rock or envelope, unknown', neptune: 'is 10 to 50 M⊕, so it is drawn as a Neptune-like planet', giant: 'is at least 50 M⊕, so it is drawn as a gas giant'}[comp]}. Radius not measured: not to scale.`);
  if (comp !== null){
    if (teq === null) reasons.push('Irradiation not computable: neutral colours.');
    else {
      const how = src === 'computed' ? (aSrc === 'a' ? 'computed from a, R★ and Teff' : 'computed from the period, M★, R★ and Teff') : 'as the catalogue stores it';
      reasons.push(`Teq ${fmt(teq, 0)} K, ${how}, is in the ${band} band.`);
      if (src === 'computed' && stored !== null && Math.abs(stored - teq) > 0.3 * teq) reasons.push(`Teq computed from a, R★ and Teff; the catalogue's stored value (${fmt(stored, 0)} K) differs.`);
    }
    reasons.push('Composition is not measured.');
  }
  const r = (x, d) => x === null ? null : Math.round(x * 10 ** d) / 10 ** d;
  return {name: lookName(comp, band), composition: comp, band, by, rp_re: r(rp, 4), mp_me: r(mp, 3), s: r(s, 4), teq: r(teq, 1), teq_source: src,
          to_scale: by === 'radius', neutral: comp !== null && band === null, reasons};
}

// ---------- planet surfaces: equirectangular 256 x 128 per (look, seed), the same for both paths ----------
const TW = 256, TH = 128, TEX = new Map();
function ramp(pal, t){ t = clamp(t, 0, 1) * 3; const i = Math.min(2, Math.floor(t)), f = t - i, a = pal[i], b = pal[i + 1]; return [mix(a[0], b[0], f), mix(a[1], b[1], f), mix(a[2], b[2], f)]; }
function texture(name, seed){
  const key = name + '|' + seed; if (TEX.has(key)) return TEX.get(key);
  const L = LOOKS[name] || LOOKS['ambiguous'], d = new Uint8ClampedArray(TW * TH * 4), so = (seed % 9973) * 0.0137;
  for (let v = 0; v < TH; v++){
    const lat = (.5 - (v + .5) / TH) * Math.PI, cl = Math.cos(lat), sl = Math.sin(lat), latd = Math.abs(lat) * 180 / Math.PI;
    for (let u = 0; u < TW; u++){
      const lon = (u + .5) / TW * TAU, x = cl * Math.cos(lon), y = sl, z = cl * Math.sin(lon);
      const n = fbm(x * 2.2 + so, y * 2.2, z * 2.2, 5), m = fbm(x * 1.1 - so, y * 1.1 + 3, z * 1.1, 3);
      let col, ex = 0;
      if (L.clouds){  // the Solar System's Earth only: oceans, land, ice and clouds
        const land = n > .53;
        if (latd > L.ice + (m - .5) * 18) col = [236, 242, 248];
        else if (land){ const t = sstep(.53, .7, n); col = [mix(L.pal[2][0], L.pal[3][0], t), mix(L.pal[2][1], L.pal[3][1], t), mix(L.pal[2][2], L.pal[3][2], t)]; }
        else { const t = sstep(.3, .53, n); col = [mix(L.pal[0][0], L.pal[1][0], t), mix(L.pal[0][1], L.pal[1][1], t), mix(L.pal[0][2], L.pal[1][2], t)]; }
        ex = sstep(.55, .72, fbm(x * 3.1 + 40, y * 3.1, z * 3.1, 4));
      } else {
        let t = L.freq ? .5 + .5 * Math.sin(lat * L.freq + n * L.turb + so) : n;
        t = mix(n, t, L.amp); t = mix(t, .55, L.haze);
        col = ramp(L.pal, t);
        if (L.crater){ const c = fbm(x * 5 + 7 + so, y * 5, z * 5, 3), pit = L.crater * .45 * sstep(.55, .72, c); col = col.map(q => q * (1 - pit)); }
        if (L.ice && latd > L.ice + (m - .5) * 12) col = col.map((q, i) => mix(q, [226, 230, 236][i], .9));
        if (L.spot === 1){ const sp = sstep(.74, .8, m) * (Math.abs(lat + .35) < .18 ? 1 : 0); col = col.map(q => q * (1 - sp * .5)); }
        if (L.spot === 2){ const red = Math.exp(-((lat + .38) ** 2) / .004) * sstep(.62, .7, m); col = [col[0] + red * 40, col[1] - red * 60, col[2] - red * 70]; }
        if (L.crack) ex = sstep(.89, .97, 1 - Math.abs(2 * fbm(x * 5 + 9, y * 5, z * 5, 3) - 1));
      }
      const i = (v * TW + u) * 4; d[i] = col[0]; d[i + 1] = col[1]; d[i + 2] = col[2]; d[i + 3] = ex * 255;
    }
  }
  const t = {d, L}; if (TEX.size > 24) TEX.delete(TEX.keys().next().value); TEX.set(key, t); return t;
}
// The star's granulation (texture only, not to scale): one fbm tile shared by every star.
let GRAN = null;
function gran(){ if (GRAN) return GRAN; const N = 256, d = new Uint8ClampedArray(N * N * 4);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++){ const v = fbm(x / 9 * 2.3 + 3, y / 9 * 2.3, 9, 3) * 255, i = (y * N + x) * 4; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; }
  return (GRAN = {d, N}); }

// ---------- shading: one formula for the CPU loop and the shader ----------
function shadePixel(x, y, o, tx, out){
  const d2 = x * x + y * y; if (d2 >= 1) return 0;
  const nz = Math.sqrt(1 - d2), ny = -y, y2 = ny * o.ct - nz * o.st, z2 = ny * o.st + nz * o.ct;
  const lat = Math.asin(clamp(y2, -1, 1)), lon = Math.atan2(x, z2) + o.rot;
  const u = (((lon / TAU) % 1) + 1) % 1 * TW | 0, v = clamp((.5 - lat / Math.PI) * TH | 0, 0, TH - 1), i = (v * TW + u) * 4, L = tx.L;
  let r = tx.d[i], g2 = tx.d[i + 1], b = tx.d[i + 2]; const ex = tx.d[i + 3] / 255;
  if (o.sil){ const rim = L.atmo ? Math.pow(1 - nz, 3) * .45 : 0; out[0] = 3 + (L.atmo ? L.atmo[0] : 0) * rim; out[1] = 4 + (L.atmo ? L.atmo[1] : 0) * rim; out[2] = 6 + (L.atmo ? L.atmo[2] : 0) * rim; return 1; }
  const dot = x * o.L[0] + ny * o.L[1] + nz * o.L[2], lam = sstep(-.06, 1, dot), sh = .018 + 1.04 * Math.pow(lam, .9);
  if (L.clouds){ r = mix(r, 250, ex * .85); g2 = mix(g2, 250, ex * .85); b = mix(b, 252, ex * .85); }
  if (o.neutral){ const q = (r + g2 + b) / 3; r = mix(r, q, .5); g2 = mix(g2, q, .5); b = mix(b, q, .5); }
  r *= sh; g2 *= sh; b *= sh;
  if (L.crack){ const e = ex * (.35 + .65 * lam); r += e * 255; g2 += e * 96; b += e * 24; }
  if (L.night){ const nt = (1 - sstep(-.25, .25, dot)) * .3; r += L.night[0] * nt; g2 += L.night[1] * nt; b += L.night[2] * nt; }
  if (L.atmo){ const rim = Math.pow(1 - nz, 2.4) * sstep(-.3, .55, dot) * .95; r += L.atmo[0] * rim; g2 += L.atmo[1] * rim; b += L.atmo[2] * rim; }
  out[0] = r; out[1] = g2; out[2] = b; return 1;
}
function opts(p){ const t = p.tilt === undefined ? .2 : p.tilt, Lv = p.light || [-.62, .32, .72], ll = Math.hypot(Lv[0], Lv[1], Lv[2]) || 1;
  return {rot: p.rotation || 0, ct: Math.cos(t), st: Math.sin(t), L: [Lv[0] / ll, Lv[1] / ll, Lv[2] / ll], sil: !!p.silhouette, neutral: !!p.neutral}; }

// ---------- WebGL1: one hidden context per page ----------
const VS = 'attribute vec2 aP;varying vec2 vP;void main(){vP=aP;gl_Position=vec4(aP,0.,1.);}';
const FS = `precision highp float;varying vec2 vP;uniform int uKind;uniform sampler2D uTex;uniform vec3 uL;uniform float uRot,uCt,uSt,uPx,uSil,uNeutral,uClouds,uCrack,uGran;
uniform vec3 uAtmo,uNight,uStar;uniform float uHasAtmo,uHasNight;uniform vec2 uLd,uDrift;
float ss(float a,float b,float x){float t=clamp((x-a)/(b-a),0.,1.);return t*t*(3.-2.*t);}
void main(){vec2 p=vec2(vP.x,-vP.y);float d2=dot(p,p);if(d2>=1.){gl_FragColor=vec4(0.);return;}
float nz=sqrt(1.-d2),ny=-p.y,e=clamp((1.-sqrt(d2))*uPx*1.2,0.,1.);
if(uKind==0){float mu=nz;float I=1.-uLd.x*(1.-mu)-uLd.y*(1.-mu)*(1.-mu);float gr=texture2D(uTex,p*.42+.5+uDrift).r;I*=mix(1.,.94+.1*gr,uGran);
vec3 c=clamp(uStar/255.*I*vec3(1.04,1.,.97),0.,1.);gl_FragColor=vec4(c*e,e);return;}
float y2=ny*uCt-nz*uSt,z2=ny*uSt+nz*uCt;float lat=asin(clamp(y2,-1.,1.)),lon=atan(p.x,z2)+uRot;
vec4 tx=texture2D(uTex,vec2(fract(lon/6.2831853),clamp(.5-lat/3.1415927,0.,1.)));vec3 c=tx.rgb*255.;float ex=tx.a;
if(uSil>.5){float rim=uHasAtmo*pow(1.-nz,3.)*.45;c=vec3(3.,4.,6.)+uAtmo*rim;gl_FragColor=vec4(clamp(c/255.,0.,1.)*e,e);return;}
float dt=p.x*uL.x+ny*uL.y+nz*uL.z,lam=ss(-.06,1.,dt),sh=.018+1.04*pow(lam,.9);
if(uClouds>.5)c=mix(c,vec3(250.,250.,252.),ex*.85);
if(uNeutral>.5){float q=(c.r+c.g+c.b)/3.;c=mix(c,vec3(q),.5);}
c*=sh;if(uCrack>.5)c+=ex*(.35+.65*lam)*vec3(255.,96.,24.);
if(uHasNight>.5)c+=uNight*(1.-ss(-.25,.25,dt))*.3;
if(uHasAtmo>.5)c+=uAtmo*pow(1.-nz,2.4)*ss(-.3,.55,dt)*.95;
gl_FragColor=vec4(clamp(c/255.,0.,1.)*e,e);}`;
const G = {path: null, gl: null, cv: null, prog: null, loc: {}, tex: new Map(), granTex: null};
function glInit(){
  const cv = document.createElement('canvas'); cv.width = cv.height = 512;
  let gl = null; try { gl = cv.getContext('webgl', {premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false}); } catch (e) { gl = null; }
  if (!gl) return false;
  const sh = (t, s) => { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; };
  const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error('link');
  gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const a = gl.getAttribLocation(pr, 'aP'); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
  for (const n of ['uKind', 'uTex', 'uL', 'uRot', 'uCt', 'uSt', 'uPx', 'uSil', 'uNeutral', 'uClouds', 'uCrack', 'uGran', 'uAtmo', 'uNight', 'uStar', 'uHasAtmo', 'uHasNight', 'uLd', 'uDrift']) G.loc[n] = gl.getUniformLocation(pr, n);
  cv.addEventListener('webglcontextlost', e => { e.preventDefault(); G.gl = null; setPath('canvas2d'); try { console.info('SetuRender: WebGL context lost; drawing on the CPU for this visit.'); } catch (err) { /* none */ } });
  Object.assign(G, {gl, cv, prog: pr});
  // A one-frame test: a star must come out lit.
  const out = glStar(8, 5772, 0, 0); const px = new Uint8Array(4); gl.readPixels(8, 8, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
  return !!out && px[0] > 40;
}
function glTexture(key, data, w, h, repeat){
  const gl = G.gl; let t = G.tex.get(key); if (t) return t;
  t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, repeat ? gl.REPEAT : gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  if (G.tex.size > 24){ const k = G.tex.keys().next().value; gl.deleteTexture(G.tex.get(k)); G.tex.delete(k); }
  G.tex.set(key, t); return t;
}
function glBegin(px){ const gl = G.gl, s = Math.max(2, Math.min(512, Math.ceil(px))); gl.viewport(0, 0, s, s); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); return s; }
function glStar(rpx, teff, t, granOn){
  const gl = G.gl; if (!gl) return null; const s = glBegin(rpx * 2), L = G.loc, rgb = teffRGB(teff), ld = ldCoeffs(teff), gt = gran();
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, glTexture('gran', gt.d, gt.N, gt.N, false));
  gl.uniform1i(L.uTex, 0); gl.uniform1i(L.uKind, 0); gl.uniform1f(L.uPx, s / 2); gl.uniform3f(L.uStar, rgb[0], rgb[1], rgb[2]);
  gl.uniform2f(L.uLd, ld[0], ld[1]); gl.uniform1f(L.uGran, granOn ? 1 : 0); gl.uniform2f(L.uDrift, Math.sin(t * .05) * .02, Math.cos(t * .04) * .02);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); return s;
}
function glPlanet(rpx, name, seed, o){
  const gl = G.gl; if (!gl) return null; const s = glBegin(rpx * 2), L = G.loc, tx = texture(name, seed), Lk = tx.L;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, glTexture(name + '|' + seed, tx.d, TW, TH, true));
  gl.uniform1i(L.uTex, 0); gl.uniform1i(L.uKind, 1); gl.uniform1f(L.uPx, s / 2);
  gl.uniform3f(L.uL, o.L[0], o.L[1], o.L[2]); gl.uniform1f(L.uRot, o.rot); gl.uniform1f(L.uCt, o.ct); gl.uniform1f(L.uSt, o.st);
  gl.uniform1f(L.uSil, o.sil ? 1 : 0); gl.uniform1f(L.uNeutral, o.neutral ? 1 : 0); gl.uniform1f(L.uClouds, Lk.clouds ? 1 : 0); gl.uniform1f(L.uCrack, Lk.crack ? 1 : 0);
  const at = Lk.atmo || [0, 0, 0], nt = Lk.night || [0, 0, 0];
  gl.uniform3f(L.uAtmo, at[0], at[1], at[2]); gl.uniform3f(L.uNight, nt[0], nt[1], nt[2]); gl.uniform1f(L.uHasAtmo, Lk.atmo ? 1 : 0); gl.uniform1f(L.uHasNight, Lk.night ? 1 : 0);
  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); return s;
}

// ---------- the path: webgl, else canvas2d, else the still stays ----------
function setPath(p){ G.path = p; try { document.documentElement.dataset.render = p; } catch (e) { /* no document */ } }
// drawStar2D and drawPlanet2D use WebGL only when asked (opt.gl: the mounted figures). The Methods drawings redraw
// every frame from cached CPU rasters: a per-frame GPU read-back gains them nothing, and on a software GPU the first
// shader compile holds frames back for half a second.
const ready2d = () => G.path === 'still' ? 'still' : 'canvas2d';
// Surfaces and the granulation tile take tens of milliseconds each: a caller that must not block (opt.sync unset)
// gets null now, the work is done in idle time, and 'setu-render-ready' asks the page's drawings to redraw.
const queued = new Set(), jobs = [];
let running = false;
function later(key, make){
  if (queued.has(key)) return null; queued.add(key); jobs.push(make);
  if (!running){ running = true; idle(work); }
  return null;
}
// One job per task, so frames keep coming between them; the page is told once, when the queue is empty.
function work(){
  const make = jobs.shift();
  try { make(); } catch (e) { /* drawn plain */ }
  if (jobs.length){ setTimeout(work, 16); return; }
  running = false; queued.clear();
  try { document.dispatchEvent(new Event('setu-render-ready')); } catch (e) { /* none */ }
}
const texNow = (name, seed, sync) => TEX.get(name + '|' + seed) || (sync ? texture(name, seed) : later('t' + name + seed, () => texture(name, seed)));
const granNow = sync => GRAN || (sync ? gran() : later('gran', gran));
function path(){
  if (G.path) return G.path;
  let ok = false; try { ok = glInit(); } catch (e) { ok = false; G.gl = null; }
  if (ok){ setPath('webgl'); return G.path; }
  let c2 = null; try { c2 = document.createElement('canvas').getContext('2d'); } catch (e) { c2 = null; }
  setPath(c2 ? 'canvas2d' : 'still'); return G.path;
}

// ---------- drawing into a 2D context (both paths) ----------
const OFF = document.createElement('canvas'), offc = OFF.getContext('2d');
const RASTER = new Map();
function cache(key, make){ let v = RASTER.get(key); if (v) return v; v = make(); if (RASTER.size > 64) RASTER.delete(RASTER.keys().next().value); RASTER.set(key, v); return v; }
function cpuDisc(rpx, fill){
  const D = Math.ceil(rpx * 2) + 2, c = document.createElement('canvas'); c.width = c.height = D; const x = c.getContext('2d'), img = x.createImageData(D, D), p = img.data, out = [0, 0, 0];
  for (let py = 0; py < D; py++) for (let px = 0; px < D; px++){
    const dx = (px + .5 - D / 2) / rpx, dy = (py + .5 - D / 2) / rpx, d2 = dx * dx + dy * dy; if (d2 >= 1) continue;
    if (!fill(dx, dy, out)) continue; const e = clamp((1 - Math.sqrt(d2)) * rpx * 1.2, 0, 1), o = (py * D + px) * 4;
    p[o] = clamp(out[0], 0, 255); p[o + 1] = clamp(out[1], 0, 255); p[o + 2] = clamp(out[2], 0, 255); p[o + 3] = 255 * e;
  }
  x.putImageData(img, 0, 0); return {c, D};
}
function scaleOf(ctx){ try { const m = ctx.getTransform(); return Math.hypot(m.a, m.b) || 1; } catch (e) { return 1; } }
function glow(ctx, x, y, R, rgb, k, a){ const gr = ctx.createRadialGradient(x, y, R * .9, x, y, R * k); gr.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`); gr.addColorStop(.35, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a * .25})`); gr.addColorStop(1, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},0)`); ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(x, y, R * k, 0, TAU); ctx.fill(); }
function drawStar2D(ctx, x, y, R, teff, t, opt){
  opt = opt || {}; teff = teff || TSUN; const rgb = teffRGB(teff), [u1, u2] = opt.ld || ldCoeffs(teff), k = opt.glow || 2.1;
  if (k > 1) glow(ctx, x, y, R, rgb, Math.min(k, 3.2), .32);
  const dev = R * scaleOf(ctx), granOn = opt.granulation !== false;
  if (opt.flat || dev < 14 || ready2d() === 'still' || (granOn && !granNow(opt.sync))){
    const gr = ctx.createRadialGradient(x, y, 0, x, y, R);
    for (let i = 0; i <= 10; i++){ const r = i / 10, I = ldI(Math.min(r, .999), u1, u2); gr.addColorStop(r, `rgb(${Math.round(rgb[0] * I)},${Math.round(rgb[1] * I)},${Math.round(rgb[2] * I)})`); }
    ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(x, y, R, 0, TAU); ctx.fill(); return rgb;
  }
  if (opt.gl && G.path === 'webgl' && G.gl){
    const s = glStar(Math.min(256, dev), teff, t || 0, granOn); if (s){ ctx.drawImage(G.cv, 0, 512 - s, s, s, x - R, y - R, 2 * R, 2 * R); return rgb; }
  }
  const rp = Math.min(160, Math.round(dev)), img = cache(`s|${Math.round(teff)}|${rp}|${granOn}`, () => { const gt = gran(); return cpuDisc(rp, (dx, dy, out) => {
    const I0 = ldI(Math.sqrt(dx * dx + dy * dy), u1, u2), gx = clamp(Math.floor((dx * .42 + .5) * gt.N), 0, gt.N - 1), gy = clamp(Math.floor((dy * .42 + .5) * gt.N), 0, gt.N - 1);
    const I = I0 * (granOn ? .94 + .1 * gt.d[(gy * gt.N + gx) * 4] / 255 : 1); out[0] = rgb[0] * I * 1.04; out[1] = rgb[1] * I; out[2] = rgb[2] * I * .97; return 1; }); });
  ctx.drawImage(img.c, x - R * img.D / (2 * rp), y - R * img.D / (2 * rp), R * img.D / rp, R * img.D / rp);
  return rgb;
}
// Old class numbers from the Methods stages: 0 Earth-size, 1 super-Earth, 2 sub-Neptune, 3 Neptune-like, 4 gas giant.
const CLASS_LOOK = ['rock-warm', 'rock-warm', 'envelope-warm', 'neptune-warm', 'giant-cool'];
function drawPlanet2D(ctx, x, y, r, lk, lit, opt){
  opt = opt || {};
  if (lk === 'silhouette'){  // a candidate's shadow at Rp/R★: a dark disc, never planet art
    ctx.fillStyle = '#030406'; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
    ctx.strokeStyle = 'rgba(170,210,255,.5)'; ctx.lineWidth = Math.max(.75, r * .04); ctx.beginPath(); ctx.arc(x, y, r + ctx.lineWidth / 2, 0, TAU); ctx.stroke(); return;
  }
  const name = typeof lk === 'number' ? CLASS_LOOK[lk] || 'envelope-warm' : (LOOKS[lk] ? lk : 'ambiguous'), L = LOOKS[name];
  const o = opts({rotation: opt.rotation === undefined ? .6 : opt.rotation, tilt: opt.tilt, light: opt.light, silhouette: lit === false, neutral: opt.neutral}), dev = r * scaleOf(ctx), seed = opt.seed || 1;
  if (dev < (opt.sync ? 5 : 12) || ready2d() === 'still' || !texNow(name, seed, opt.sync)){
    const c = lit === false ? [4, 5, 8] : ramp(L.pal, .6), gr = ctx.createRadialGradient(x - r * .35, y - r * .35, r * .1, x, y, r);
    gr.addColorStop(0, `rgb(${c.map(v => Math.round(Math.min(255, v * 1.15))).join(',')})`); gr.addColorStop(1, `rgb(${c.map(v => Math.round(v * (lit === false ? 1 : .35))).join(',')})`);
    ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
    if (lit === false && L.atmo){ ctx.strokeStyle = `rgba(${L.atmo.join(',')},.45)`; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, r + .5, 0, TAU); ctx.stroke(); }
    return;
  }
  if (lit !== false && L.atmo && opt.halo !== false){ const gx = x + o.L[0] * r * .18, gy = y - o.L[1] * r * .18, gr = ctx.createRadialGradient(gx, gy, r * .96, gx, gy, r * 1.16); gr.addColorStop(0, `rgba(${L.atmo.join(',')},.32)`); gr.addColorStop(1, `rgba(${L.atmo.join(',')},0)`); ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(x, y, r * 1.18, 0, TAU); ctx.fill(); }
  if (opt.gl && G.path === 'webgl' && G.gl){
    const s = glPlanet(Math.min(256, dev), name, seed, o); if (s){ ctx.drawImage(G.cv, 0, 512 - s, s, s, x - r, y - r, 2 * r, 2 * r); return; }
  }
  const rp = Math.min(opt.cpuMax || 160, Math.round(dev)), tx = texture(name, seed);
  const img = cache(`p|${name}|${seed}|${rp}|${o.sil}|${o.neutral}|${o.rot.toFixed(3)}|${o.L.join(',')}`, () => cpuDisc(rp, (dx, dy, out) => shadePixel(dx, dy, o, tx, out)));
  ctx.drawImage(img.c, x - r * img.D / (2 * rp), y - r * img.D / (2 * rp), r * img.D / rp, r * img.D / rp);
}

// ---------- the public drawers: a canvas and its parameters ----------
let FONT = null;
const font = () => FONT || (FONT = (() => { try { return getComputedStyle(document.body).fontFamily; } catch (e) { return 'system-ui,sans-serif'; } })());
function fit(cv){ const r = cv.getBoundingClientRect(), d = DPR(), w = Math.max(2, Math.round((r.width || cv.width) * d)), h = Math.max(2, Math.round((r.height || cv.height) * d)); if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; } return [w, h, d]; }
function star(cv, p){
  p = p || {}; const ctx = cv.getContext('2d'), [w, h] = fit(cv), R = Math.min(w, h) * .3;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
  drawStar2D(ctx, w / 2, h / 2, R, p.teff || TSUN, p.t || 0, {ld: p.ld, glow: 1.5 * (p.glow === undefined ? 1 : p.glow), granulation: p.granulation !== false, sync: true, gl: true});
}
function planet(cv, p){
  p = p || {}; const ctx = cv.getContext('2d'), [w, h, d] = fit(cv), cap = (COARSE() ? 384 : 512) / 2;
  const R = Math.min(p.scale_px ? p.scale_px * d : Math.min(w, h) * .36, cap);
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
  drawPlanet2D(ctx, w / 2, h / 2, R, p.look || 'ambiguous', !p.silhouette, {seed: p.seed || 1, rotation: (p.rotation === undefined ? .6 : p.rotation) + (p.t || 0) * .12, tilt: p.tilt, light: p.light, neutral: p.neutral, cpuMax: p.cpu_max, sync: true, gl: true});
}
function transit(cv, p){
  p = p || {}; const ctx = cv.getContext('2d'), [w, h, d] = fit(cv), hero = p.layout === 'hero', narrow = w / d < 820;
  const teff = p.teff || TSUN, [u1, u2] = p.ld || ldCoeffs(teff), k = p.k || (p.depth_ppm ? Math.sqrt(p.depth_ppm * 1e-6) : .1), b = p.b || 0;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
  const R = Math.round((hero ? (narrow ? .27 : .3) : .26) * h), cx = hero && !narrow ? w * .69 : w * .5, cy = hero ? (narrow ? h * .36 : h * .41) : h * .34;
  const loop = p.loop_s || 7.5, still = p.t === null || p.t === undefined, ph = still ? .5 : ((p.t / loop) % 1), X = (ph - .5) * 3.2;
  drawStar2D(ctx, cx, cy, R, teff, p.t || 0, {ld: [u1, u2], glow: 1.5, sync: true, gl: true});
  const px = cx + X * R, py = cy + b * R, rp = Math.max(1.5 * d, R * k), on = Math.hypot(px - cx, py - cy) < R + rp;
  drawPlanet2D(ctx, px, py, rp, p.look || 'ambiguous', !on, {seed: p.seed || 1, light: [(cx - px) / R, .2, .5], sync: true, gl: true});
  // The light curve: model from stored values, with the stored points over it when given.
  const gx = hero && !narrow ? w * .06 : w * .08, gw = hero && !narrow ? w * .43 : w * .84, gy = hero ? (narrow ? h * .74 : h * .78) : h * .7, gh = hero ? h * .15 : h * .22;
  const depth = 1 - transitFlux(b, k, u1, u2), lo = 1 - 1.4 * Math.max(depth, 1e-5), Y = v => gy + (1 - v) / (1 - lo) * gh, Xc = z => gx + (z + 1.6) / 3.2 * gw;
  ctx.strokeStyle = 'rgba(255,255,255,.14)'; ctx.lineWidth = d; ctx.beginPath(); ctx.moveTo(gx, Y(1)); ctx.lineTo(gx + gw, Y(1)); ctx.stroke();
  if (p.points && p.t14_h){ ctx.fillStyle = 'rgba(100,210,255,.55)'; for (const q of p.points){ const z = q[0] / (p.t14_h / 2) * (1 + k); if (Math.abs(z) > 1.6) continue; ctx.fillRect(Xc(z) - d, Y(1 + q[1] * 1e-6) - d, 2 * d, 2 * d); } }
  ctx.strokeStyle = '#FFB340'; ctx.lineWidth = 1.8 * d; ctx.beginPath();
  for (let i = 0; i <= 200; i++){ const z = -1.6 + 3.2 * i / 200; if (!still && z > X) break; const v = transitFlux(Math.hypot(z, b), k, u1, u2); i ? ctx.lineTo(Xc(z), Y(v)) : ctx.moveTo(Xc(z), Y(v)); }
  ctx.stroke();
  ctx.fillStyle = '#9AA3B5'; ctx.font = `${11 * d}px ${font()}`; ctx.textAlign = 'left';
  ctx.fillText(window.SetuI18n ? SetuI18n.T('hero.depth', 'depth {d, number, integer} ppm (model)', {d: Math.round(depth * 1e6)}) : `depth ${fmt(depth * 1e6, 0)} ppm (model)`, gx, gy - 6 * d);
}
function starfieldDraw(cv, p){
  const ctx = cv.getContext('2d'), [w, h, d] = fit(cv), r = rng(p.seed || 314), n = Math.round(w * h / (d * d) * (p.density || 1 / 2600)), par = p.par || [0, 0], layers = p.layers || 3;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, w, h);
  for (let i = 0; i < n; i++){
    const layer = i % layers, x = (r() * w + par[0] * (layer + 1) / layers * d + w) % w, y = (r() * h + par[1] * (layer + 1) / layers * d + h) % h;
    const bt = Math.pow(r(), 3.2), s = (.35 + bt * 1.5 + layer * .2) * d, t = r(), c = t < .15 ? [255, 214, 170] : t < .3 ? [190, 214, 255] : [235, 240, 255];
    ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${.25 + bt * .75})`; ctx.beginPath(); ctx.arc(x, y, s, 0, TAU); ctx.fill();
  }
}

// ---------- mount, scheduling, the budget ----------
const ST = {mounted: 0, frames: 0, stills: 0, governor: 'full', times: []};
const targets = [], active = [], waiting = [];
let raf = 0, last = 0;
const maxActive = () => COARSE() ? 2 : 4;
// A target the visitor started (a Play or Spin button) may run under reduced motion; nothing runs once the governor
// has dropped the page to stills.
function canAnimate(T){ return (!RM() || T.user) && ST.governor !== 'stills'; }
function want(T){ if (T.wanted || T.paused || !canAnimate(T) || !T.anim) return; T.wanted = true;
  // The page's first target (the hero) never waits behind others: it takes the last running target's place.
  if (active.length >= maxActive() && T.el.dataset.priority === 'first') waiting.unshift(active.pop());
  if (active.length < maxActive()){ active.push(T); kick(); } else waiting.push(T); }
function unwant(T){ T.wanted = false; T.at = 0; let i = active.indexOf(T); if (i >= 0) active.splice(i, 1); i = waiting.indexOf(T); if (i >= 0) waiting.splice(i, 1);
  while (active.length < maxActive() && waiting.length) active.push(waiting.shift()); if (active.length) kick(); }
function kick(){ if (!raf && active.length && !document.hidden) raf = requestAnimationFrame(loop); }
function loop(now){
  raf = 0; if (document.hidden || !active.length) return;
  const fps = ST.governor === '30fps' ? 30 : 60, slow = G.path === 'canvas2d' ? 15 : fps;
  const t0 = performance.now();
  // Each target keeps its own clock, which stops while it is paused or off screen (it resumes where it was).
  for (const T of active){ const min = 1000 / (T.kind === 'starfield' ? fps : slow); if (T.at && now - T.at < min - 1) continue;
    T.t += T.at ? Math.min(100, now - T.at) / 1000 : 0; T.at = now; try { T.draw(T.t); if (T.onframe) T.onframe(); } catch (e) { T.anim = false; } }
  ST.frames++;
  const dt = performance.now() - t0; ST.times.push(dt); if (ST.times.length > 60) ST.times.shift();
  if (ST.times.length === 60){ const m = ST.times.slice().sort((a, b) => a - b)[30]; if (m > 33){ ST.governor = 'stills'; active.forEach(T => { try { T.draw(STILL_T[T.kind]); } catch (e) { /* kept */ } }); active.splice(0); waiting.splice(0); return; } if (m > 20) ST.governor = '30fps'; }
  if (G.path === 'canvas2d' && dt > 24 && active.length === 1 && active[0].kind !== 'starfield'){ const T = active[0]; T.anim = false; unwant(T); }
  kick();
}
document.addEventListener('visibilitychange', () => { if (document.hidden){ cancelAnimationFrame(raf); raf = 0; } else kick(); });
let io = null;
const observe = T => { if (!('IntersectionObserver' in window)){ want(T); return; } io = io || new IntersectionObserver(es => es.forEach(e => { const T2 = e.target._sr; if (!T2) return; T2.vis = e.isIntersecting; if (e.isIntersecting) want(T2); else unwant(T2); }), {rootMargin: '80px'}); io.observe(T.el); };
const DRAW = {planet, star, transit};
// The designed stills under reduced motion (and the first frame of every target).
const STILL_T = {planet: 0, star: 0, transit: null};
function upgrade(el){
  if (el._sr) return; const kind = el.dataset.render;
  let p = {}; try { p = JSON.parse(el.dataset.params || '{}'); } catch (e) { p = {}; }
  if (kind === 'starfield') return mountStarfield(el, p);
  if (!DRAW[kind] || path() === 'still') return;
  const box = el.querySelector('.rbox') || el, img = box.querySelector('img.rstill');
  const cv = document.createElement('canvas'); cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', (img && img.alt) || el.getAttribute('aria-label') || '');
  box.appendChild(cv);
  const T = {el, cv, kind, p, at: 0, t: 0, anim: p.animate !== false, draw: t => DRAW[kind](cv, Object.assign({}, T.p, {t}))};
  try { DRAW[kind](cv, Object.assign({}, p, {t: STILL_T[kind]})); ST.stills++; } catch (e) { cv.remove(); try { console.info('SetuRender: kept the still image', e && e.message); } catch (err) { /* none */ } return; }
  if (img){ img.hidden = true; }
  el._sr = T; targets.push(T); ST.mounted++;
  if (T.anim){ T.obs = true; observe(T); }
}
function mountStarfield(el, p){
  if (RM() || el._sr) return; let cv = null;
  try { cv = document.createElement('canvas'); if (!cv.getContext('2d')) return; } catch (e) { return; }
  cv.setAttribute('aria-hidden', 'true'); el.appendChild(cv);
  const T = {el, cv, kind: 'starfield', p, at: 0, t: 0, anim: true, par: [0, 0], aim: [0, 0], draw(){
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') return;
    const f = Math.min(1, window.scrollY / Math.max(1, innerHeight)); cv.style.opacity = String(1 - f); if (f >= 1) return;
    T.par[0] += (T.aim[0] - T.par[0]) * .08; T.par[1] += (T.aim[1] - T.par[1]) * .08;
    starfieldDraw(cv, Object.assign({}, p, {par: T.par}));
    if (Math.abs(T.aim[0] - T.par[0]) < .05 && Math.abs(T.aim[1] - T.par[1]) < .05) unwant(T);
  }};
  starfieldDraw(cv, p); const img = el.querySelector('img'); if (img) img.hidden = true;
  el._sr = T; targets.push(T); ST.mounted++;
  if (!mm('(pointer:coarse)')) addEventListener('pointermove', e => { const m = p.parallax_px === undefined ? 8 : p.parallax_px; T.aim = [(e.clientX / innerWidth - .5) * 2 * m, (e.clientY / innerHeight - .5) * 2 * m]; if (window.scrollY < innerHeight) want(T); }, {passive: true});
  addEventListener('scroll', () => { if (window.scrollY < innerHeight * 1.1) T.draw(); }, {passive: true});
  addEventListener('resize', () => starfieldDraw(cv, Object.assign({}, p, {par: T.par})));
}
function mount(root){
  root = root || document;
  const els = Array.from(root.querySelectorAll ? root.querySelectorAll('[data-render]') : []);
  if (root.dataset && root.dataset.render) els.unshift(root);
  // A figure in a hidden view (every view's markup is in the page) waits: the router mounts a view when it shows it.
  els.filter(el => !el.closest('[hidden]')).forEach(el => { try { upgrade(el); } catch (e) { try { console.info('SetuRender: kept the still image', e && e.message); } catch (err) { /* none */ } } });
}
// A component's own controls (the hero's Pause, a portrait's Spin) run its figure through this scheduler, so it obeys the
// same budget: on screen only, the tab visible, at most 4 at once, the frame governor. on: play or pause; user: the
// visitor asked (it may then run under reduced motion); onframe: called after each frame drawn.
function play(el, on, o){
  const T = el && el._sr; if (!T || T.kind === 'starfield') return false; o = o || {};
  if (o.onframe) T.onframe = o.onframe; if (o.user !== undefined) T.user = !!o.user;
  T.paused = !on; T.anim = true;
  if (!T.obs){ T.obs = true; observe(T); }
  if (on && (T.vis || !('IntersectionObserver' in window))) want(T); else if (!on) unwant(T);
  return true;
}
const playing = el => !!(el && el._sr && active.includes(el._sr));
function stats(){ return {path: G.path || path(), mounted: ST.mounted, animating: active.length, frames: ST.frames, stills: ST.stills, contexts: G.gl ? 1 : 0, governor: ST.governor}; }
let rz = 0;
addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => targets.forEach(T => { if (T.kind !== 'starfield' && !T.wanted) try { T.draw(T.t || STILL_T[T.kind]); } catch (e) { /* kept */ } }), 150); });
window.SetuRender = {mount, star, planet, transit, starfield: starfieldDraw, teffRGB, look, transitFlux, ldCoeffs, drawStar2D, drawPlanet2D, play, playing, stats, fnv, LOOKS, path};
// Nothing renders until 200 ms after the page is parsed, except a target marked data-priority="first" (the hero).
const start = () => { document.querySelectorAll('[data-render][data-priority="first"]').forEach(el => { try { upgrade(el); } catch (e) { /* kept */ } }); idle(() => mount(document)); };
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
"""


def render_js() -> str:
    return (RENDER_JS_SRC.replace("__LOOKS__", looks_json(), 1)
            .replace("__CLARET__", json.dumps(_claret(), separators=(",", ":")), 1))


RENDER_CSS = """
/* ---------- setuhq.renderer: the starfield and the rendered figures ---------- */
.starfield{position:fixed;inset:0;z-index:-1;pointer-events:none;overflow:hidden}
.starfield>img,.starfield>canvas{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.starfield>img[hidden]{display:none}
:root[data-theme="light"] .starfield{display:none}
@media (prefers-color-scheme: light){:root[data-theme="system"] .starfield{display:none}}
"""


def _sha(text: str | bytes, n: int = 10) -> str:
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()[:n]


def render_js_sha() -> str:
    return hashlib.sha256(render_js().encode()).hexdigest()


def stills_manifest() -> dict:
    path = STILLS_DIR / "stills.json"
    return json.loads(path.read_text()) if path.exists() else {}


def stills_hash() -> str:
    """The stills folder's name on the site: a hash of stills.json, so a new set is a new address."""
    path = STILLS_DIR / "stills.json"
    return _sha(path.read_bytes(), 8) if path.exists() else "none"


def still_href(look: str, px: int = 512) -> str:
    return f"/assets/render/{stills_hash()}/{look}-{px}.webp"


def write_assets(out: str | Path) -> dict:
    """Write render-<hash>.js and the stills into a built site; returns their addresses."""
    out = Path(out)
    js = render_js()
    rel = f"assets/render-{_sha(js)}.js"
    (out / rel).parent.mkdir(parents=True, exist_ok=True)
    (out / rel).write_text(js)
    sdir = out / "assets" / "render" / stills_hash()
    sdir.mkdir(parents=True, exist_ok=True)
    for f in sorted(STILLS_DIR.glob("*.webp")):
        shutil.copyfile(f, sdir / f.name)
    return {"render": "/" + rel, "stills": f"/assets/render/{stills_hash()}/"}


def figure(kind: str, params: dict, alt: str, caption: str, label: str = LABEL_ART, size: int = 512, *,
           uid: str = "", still: str | None = None, priority: bool = False) -> str:
    """The server-rendered element SetuRender.mount upgrades: the still image (alt text), the honesty tag (an
    "Artist's impression" tag links to /docs/pictures/), and a visible caption with the numbers and the source."""
    e = html.escape
    uid = uid or _sha(kind + json.dumps(params, sort_keys=True) + caption, 8)
    src = still or (still_href(params["look"], 512 if size > 160 else 160) if params.get("look") else "")
    # A planet's tag always links to the page that explains the pictures (an artist's impression, or the Solar
    # System references, which are illustrations).
    tag = (f'<a class="stage-tag" href="{PICTURES}"{lk(label)}>{e(label)}</a>' if label == LABEL_ART or kind == "planet" else f'<span class="stage-tag"{lk(label)}>{e(label)}</span>')
    img = (f'<img class="rstill" src="{e(src)}" width="{size}" height="{size}" loading="lazy" decoding="async" alt="{e(alt)}">'
           if src else f'<img class="rstill" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="{size}" height="{size}" alt="{e(alt)}">')
    pri = ' data-priority="first"' if priority else ""
    return (f"<figure class=\"stage rfig\" data-render=\"{e(kind)}\" data-params='{e(json.dumps(params, separators=(',', ':')), quote=False)}'"
            f' aria-labelledby="cap-{uid}"{pri}><div class="rbox">{img}</div>{tag}'
            f'<figcaption id="cap-{uid}" class="readout">{caption}</figcaption></figure>')


def star_svg(teff: float, r_px: float, *, uid: str, label: str | None = None) -> str:
    """A static star disc in its blackbody colour with quadratic limb darkening (Claret 2017, TESS band): 11
    radial-gradient stops, teff_rgb x I(r). Decorative (aria-hidden) unless a label is given."""
    from setuhq.methods import ld_coeffs, ld_intensity

    rgb, (u1, u2) = teff_rgb(teff), ld_coeffs(teff)
    stops = "".join(f'<stop offset="{i / 10:g}" stop-color="#{"".join(f"{round(c * ld_intensity(min(i / 10, 0.999), u1, u2)):02x}" for c in rgb)}"/>'
                    for i in range(11))
    d = f"{2 * r_px:g}"
    a11y = f'role="img" aria-label="{html.escape(label)}"' if label else 'aria-hidden="true"'
    return (f'<svg class="stardisc" viewBox="0 0 {d} {d}" width="{d}" height="{d}" {a11y}><defs><radialGradient id="sd-{uid}">{stops}'
            f'</radialGradient></defs><circle cx="{r_px:g}" cy="{r_px:g}" r="{r_px:g}" fill="url(#sd-{uid})"/></svg>')


def star_svg_stops(teff: float) -> list[tuple[int, int, int]]:
    """The 11 stop colours star_svg writes (for the tests)."""
    from setuhq.methods import ld_coeffs, ld_intensity

    rgb, (u1, u2) = teff_rgb(teff), ld_coeffs(teff)
    return [tuple(round(c * ld_intensity(min(i / 10, 0.999), u1, u2)) for c in rgb) for i in range(11)]


def look_table_rows() -> list[dict]:
    """One row per look for /docs/pictures/: name, composition, bands, surface words, and its stills."""
    return [{"look": k, "composition": v["composition"], "bands": v["bands"], "surface": v["surface"],
             "still_512": still_href(k, 512), "still_160": still_href(k, 160)} for k, v in LOOKS.items()]


def _dump() -> None:
    import sys

    sys.stdout.write(json.dumps({"js": render_js(), "js_sha256": render_js_sha(), "looks_sha256": looks_sha(),
                                 "looks": list(LOOKS), "seed": STILL_SEED, "sizes": list(STILL_SIZES)}))


if __name__ == "__main__":
    _dump()

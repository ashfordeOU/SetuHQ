# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V04 sky by year: every catalogue planet at its host star's sky position (RA, Dec), coloured by discovery method,
filling in year by year.

Used on: /explore/ (full size, under the coverage layers and the run star's pin), Home (compact), Methods population.
Owner: P2 (docs/SITE.md, "The visual system").

The data are the site's own catalogue (exoplanet.eu, ``docs/results/exoplanet_catalogue.json``), where every record
has RA and Dec. :func:`data` writes them to ``assets/data/sky-<hash>.json`` as ``{m: [methods], p: [[ra×10, dec×10,
m, year]]}`` with the source and fetch date (at most 160,000 bytes); a page fetches it only when the map comes within
600 px of the screen. Without JavaScript the map is a static SVG of the final year, decimated to at most 1,500 points,
with the per-method counts in a table. With it, a canvas draws every point; the map plays the years at 0.42 s each
while it is on screen and the tab is visible (with Pause, a keyboard-operable year scrubber and "Transits only");
under reduced motion it shows the final year and plays only when asked.
"""

from __future__ import annotations

import html as _html
import json
import math

from setuhq.design import METHOD
from setuhq.story import SKY_R, SQRT2, mollweide
from setuhq.viz import require_source

METHODS = list(METHOD)  # the sky file's method index: design.METHOD's order
LABEL = {"transit": "transit", "rv": "radial velocity", "imaging": "imaging", "microlensing": "microlensing",
         "astrometry": "astrometry", "timing": "timing", "other": "other"}
STATIC_MAX = 1500  # points in the map drawn without JavaScript
STATIC_COMPACT = 100  # the same, in the compact band (the home page keeps to its budget)
YEAR_S = 0.42      # seconds per year while playing
FRAME = (-460, -235, 920, 470)  # the Mollweide frame of setuhq.story.mollweide (RA increasing to the left)


def _cat(data: dict) -> dict | None:
    return data.get("catalogue") or (data.get("app") or {}).get("catalogue")


def rows(cat: dict) -> list[list]:
    """Every catalogue record with RA and Dec: [ra×10, dec×10, method index, year], in catalogue order."""
    P = cat["planets"]
    out = []
    for ra, dec, m, y in zip(P["ra"], P["dec"], P["method"], P["year"]):
        if ra is None or dec is None:
            continue
        out.append([round(ra * 10), round(dec * 10), METHODS.index(m if m in METHODS else "other"), y])
    return out


def source_text(cat: dict) -> str:
    return f"{cat.get('source_name') or cat.get('source_short') or 'the catalogue'}, fetched {str(cat.get('fetched_at') or '')[:10]}"


def data(app_data: dict) -> dict:
    """The sky file (sky.json): every record with a position, its method and its year, and where they come from."""
    cat = (app_data or {}).get("catalogue")
    if not cat:
        return {}
    return {"m": METHODS, "p": rows(cat), "source": source_text(cat), "fetched_at": cat.get("fetched_at")}


def graticule(meridians: bool = True) -> str:
    """Parallels every 30° and meridians every 60° (the compact band: three parallels and the central meridian), in whole frame units with relative steps (faint: the map is the dots)."""
    def line(pts):
        pts = [tuple(round(v) for v in mollweide(ra, dec)) for ra, dec in pts]
        return f"M{pts[0][0]} {pts[0][1]}" + "".join(f"l{x - px} {y - py}" for (px, py), (x, y) in zip(pts, pts[1:]))
    out = [line([(ra, dec) for ra in range(-180, 181, 15)]) for dec in ((-60, -30, 0, 30, 60) if meridians else (-30, 0, 30))]
    out += [line([(ra, d) for d in range(-90, 91, 15)]) for ra in (-120, -60, 60, 120)] if meridians else []
    return "".join(out) + f"M0 {round(mollweide(0, -90)[1])}V{round(mollweide(0, 90)[1])}"


def counts(rs: list[list], year: int | None = None) -> dict[str, int]:
    """Records per method up to and including ``year`` (all of them when None)."""
    c = {m: 0 for m in METHODS}
    for r in rs:
        if year is None or (r[3] or 9999) <= year:
            c[METHODS[r[2]]] += 1
    return c


def readout_text(c: dict[str, int]) -> str:
    top = sorted(((v, k) for k, v in c.items() if v), reverse=True)[:4]
    return f"{sum(c.values()):,} planets shown · " + " · ".join(f"{LABEL[k]} {v:,}" for v, k in top)


def html(data: dict, **opts) -> str:
    """The map. ``data``: ``source`` (printed) and the app data as ``app`` (its ``catalogue``, and the sky file's
    address in ``viz_files``), or the catalogue itself as ``catalogue``. ``compact=True``: the home page's and Methods'
    smaller band. ``overlay``: markup laid over the map in the same frame (/explore/'s coverage layers and pin)."""
    require_source(data)
    cat = _cat(data)
    rs = rows(cat) if cat else []
    if not rs:
        return ""
    e = _html.escape
    uid = e(opts.get("uid") or f"skyy-{opts.get('where') or 'x'}")
    years = [r[3] for r in rs if r[3]]
    y0, y1 = min(years), max(years)
    src = ((data.get("app") or {}).get("viz_files") or {}).get("sky", "")
    c = counts(rs)
    n = sum(c.values())
    step = max(1, math.ceil(len(rs) / (STATIC_COMPACT if opts.get("compact") else STATIC_MAX)))
    from setuhq.galaxy import dots_path

    paths: dict[str, list] = {m: [] for m in METHODS}
    for r in rs[::step]:
        paths[METHODS[r[2]]].append(mollweide(r[0] / 10, r[1] / 10))
    dots = "".join(f'<path d="{dots_path(p)}" stroke="{METHOD[m][0]}"/>' for m, p in paths.items() if p)
    shown = sum(len(p) for p in paths.values())
    compact = bool(opts.get("compact"))
    aria = (f"All-sky map (Mollweide, RA increasing to the left) of the {n:,} catalogued planets at their host stars' "
            f"positions, coloured by discovery method, as of {y1}: " + ", ".join(f"{LABEL[k]} {v:,}" for k, v in c.items() if v) + ".")
    legend = "".join(f'<li><i style="background:{METHOD[m][0]}"></i>{e(LABEL[m])}</li>' for m in METHODS if c[m])
    table = "".join(f'<tr><th scope="row">{e(LABEL[m])}</th><td>{c[m]:,}</td></tr>' for m in METHODS if c[m])
    tools = (f'<div class="skytools"><button class="btn" type="button" data-sky="play" aria-pressed="false" hidden>Play</button>'
             f'<button class="btn" type="button" data-sky="transit" aria-pressed="false" hidden>Transits only</button>'
             f'<label class="skyscrub" hidden><span>Year</span><input type="range" data-sky="year" min="{y0}" max="{y1}" step="1" '
             f'value="{y1}" aria-valuetext="{y1}: {n:,} planets"></label></div>')
    nojs = f'<span class="skynojs"> This still shows {shown:,} of them (every {step}th); the full map draws when the page\'s script runs.</span>' if step > 1 else ""
    cap = (f'<ul class="skylegend" aria-label="Discovery method">{legend}</ul>'
           f'<p class="skysrc">Each dot is a catalogued planet at its host star\'s position (RA and Dec, J2000), coloured by the method that '
           f'found it, appearing in its discovery year.{nojs} SetuHQ did not discover these planets. Source: {e(data["source"])}.</p>')
    return (f'<figure class="skyyears{" compact" if opts.get("compact") else ""}" id="{uid}" data-viz="skyyears" data-src="{e(src)}" '
            f'data-y0="{y0}" data-y1="{y1}">'
            f'<div class="stage skystage"><div class="skybox">'
            f'<svg class="skybase" viewBox="{" ".join(map(str, FRAME))}" role="img" aria-label="{e(aria)}">'
            f'<ellipse rx="{round(SKY_R * 2 * SQRT2)}" ry="{round(SKY_R * SQRT2)}" fill="rgba(255,255,255,.015)" stroke="rgba(120,140,180,.3)" stroke-width=".8"/>'
            f'<path d="{graticule(not compact)}" stroke="rgba(120,140,180,.13)" stroke-width=".8" fill="none"/>'
            f'<g class="skydots" stroke-width="2.4" stroke-linecap="round">{dots}</g></svg>'
            f'{opts.get("overlay") or ""}</div>'
            f'<span class="stage-tag" data-i18n="label.real">Real data, cited</span><span class="skyyear" aria-hidden="true">{y1}</span></div>'
            f'{tools}<p class="readout skyread">{e(readout_text(c))}</p><p class="sr" data-sky="live" aria-live="polite"></p>'
            f'<figcaption>{cap}</figcaption>'
            + ("" if compact else  # the compact band's counts by method are in the map's label and the readout
               f'<details class="skytable"><summary>Planets by discovery method, as of {y1}</summary><table class="pltable"><thead><tr>'
               f'<th scope="col">Method</th><th scope="col">Planets</th></tr></thead><tbody>{table}<tr><th scope="row">All</th><td>{n:,}</td></tr>'
               f'</tbody></table></details>') + '</figure>')


CSS = """
/* ---------- viz.skyyears (V04): the sky by discovery year ---------- */
.skyyears{margin:0;display:grid;gap:8px;min-width:0}
.skystage{padding:12px}
.skybox{position:relative;aspect-ratio:920/470;width:100%}
.skybox>svg,.skybox>canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.skybase .skydots[hidden]{display:none}
.skyyear{position:absolute;left:14px;top:10px;font:600 clamp(18px,2.4vw,30px)/1 var(--mono);color:var(--stage-ink);letter-spacing:-.02em}
.skytools{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.skytools .btn{min-height:44px}
.skyscrub{display:flex;align-items:center;gap:10px;flex:1 1 220px;font:var(--t-data);color:var(--ink-3)}
.skyscrub input{flex:1;min-width:0;min-height:44px;accent-color:var(--blue)}
.skytools [hidden]{display:none}
.skyread{padding:0;margin:0}
.skylegend{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:4px 14px;font:var(--t-data);color:var(--ink-2)}
.skylegend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.skysrc{margin:6px 0 0;font-size:12.5px;line-height:1.45;color:var(--ink-3);max-width:96ch}
.skytable summary,.tltable summary,.orbtable summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-size:13px;color:var(--ink-2)}
.skytable table{max-width:420px}
.skyyears.compact .skystage{padding:8px}
@media (max-width:699.98px){.skystage{padding:6px}.skyyear{left:8px;top:6px}}
"""

JS = r"""
// ---------- viz.skyyears (V04): the sky by discovery year; fetched near the screen, played while on screen ----------
(function(){
  const RM = () => matchMedia('(prefers-reduced-motion: reduce)').matches, PER = __YEAR_S__ * 1000, HOLD = 3000;
  const R = __SKY_R__, S2 = Math.SQRT2, COLS = __COLS__, LABELS = __LABELS__;  // the sky file's method order (design.METHOD)
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
""".replace("__YEAR_S__", str(YEAR_S)).replace("__SKY_R__", repr(SKY_R)).replace(
    "__COLS__", json.dumps([METHOD[m][0] for m in METHODS])).replace("__LABELS__", json.dumps([LABEL[m] for m in METHODS]))

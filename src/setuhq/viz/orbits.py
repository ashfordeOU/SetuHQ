# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V08 orbits: a system's planets seen from above, with the dip each makes when it crosses the line of sight.

Used on: star pages (two or more planets with a period), the TOI-270 dip pages (P3 places it), Methods timing (P4).
Owner: P2 (docs/SITE.md, "The visual system").

Model from stored values: each orbit's size is the catalogue's semi-major axis a, or Kepler's third law from the
period and the star's mass when a is not stored; each dip's depth is k² with k = Rp/R★ from the stored planet and
star radii (in ppm, on one axis for every lane). Orbits are drawn circular, the star and planets not to scale, and the
phases are illustrative (the catalogue stores no transit times). The strip covers one period of the outermost planet.
Without JavaScript it is a static SVG of t = 0 (the innermost planet at conjunction, its dip marked); with it a canvas
plays the orbits at 1.6 days a second (faster for a long outer period, up to a 12 s loop, while the innermost planet
takes at least 1.5 s a lap) while on screen, with
Pause; under reduced motion it holds the t = 0 still and plays only when asked. The per-planet table is the text
alternative.

Input (``html``): ``source``, ``star``, ``teff`` (K; else the planets' stored host Teff), ``planets``: catalogue rows
with ``name``, ``period``, ``a``, ``radius`` (RJ), ``srad`` (R☉), ``smass`` (M☉), optional ``slug``. A ``k`` key is
not read: the catalogue's ``k`` column is the radial-velocity semi-amplitude (m/s), not Rp/R★. ``inset=True`` is
the compact form beside a dip; ``uid`` names the element.
"""

from __future__ import annotations

import html as _html
import json
import math

from setuhq.looks import LOOKS, RJ_IN_RE, kepler_a, look, teff_rgb
from setuhq.viz import require_source

RJ_PER_RSUN = 71492 / 695700   # Jupiter's equatorial radius in solar radii
AU_PER_RSUN = 695700 / 149597870.7
DAYS_PER_S = 1.6
LOOP_MAX_S = 12.0
INNER_MIN_S = 1.5
LETTERS = "bcdefghijklmnop"


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def system(rows: list[dict]) -> list[dict]:
    """The drawable planets, innermost first: name, period P (d), a (AU) and where it came from, k = Rp/R★, depth k²
    in ppm, and the central transit duration (h, circular orbit: P/π · asin(R★/a)). A planet without a period, or
    without a stored a and a star mass for Kepler's law, is left out."""
    out = []
    for r in rows:
        P = _num(r.get("period"))
        if P is None:
            continue
        a, a_src = _num(r.get("a")), "catalogue"
        if a is None:
            a, a_src = kepler_a(r.get("smass"), P), "Kepler's third law"
        if a is None:
            continue
        rp, rs = _num(r.get("radius")), _num(r.get("srad"))
        k = rp * RJ_PER_RSUN / rs if rp is not None and rs is not None else None
        dur = P / math.pi * math.asin(min(1.0, rs * AU_PER_RSUN / a)) * 24 if rs is not None else None
        lk = look(r)["name"]
        out.append({"name": r.get("name") or "", "slug": r.get("slug"), "P": P, "a": a, "a_src": a_src,
                    "rp_re": None if rp is None else rp * RJ_IN_RE, "k": k, "depth_ppm": None if k is None else k * k * 1e6,
                    "dur_h": dur, "look": lk})
    return sorted(out, key=lambda p: p["P"])


def _short(name: str, star: str) -> str:
    """"TOI-270 c" → "c" when the planet is named after its star."""
    tail = name[len(star):].strip() if star and name.lower().startswith(star.lower()) else ""
    return tail if 0 < len(tail) <= 3 else name


def _colour(lk: str | None) -> str:
    c = LOOKS[lk]["pal"][2] if lk in LOOKS else [170, 182, 204]
    return "#%02x%02x%02x" % tuple(c)


def phase0(i: int) -> float:
    """The illustrative phase of planet i at t = 0, in turns past conjunction: the innermost planet at conjunction."""
    return 0.0 if i == 0 else (i * 0.4) % 1.0


def static_svg(ps: list[dict], teff: float, star: str, label: str) -> str:
    """The t = 0 drawing: orbits from above and one period of the outermost planet in stacked lanes."""
    e = _html.escape
    cx, cy, R = 210, 210, 180
    amax = max(p["a"] for p in ps)
    rgb = teff_rgb(teff) if teff else (255, 241, 234)
    out = [f'<path d="M{cx} {cy}V418" stroke="#FFB340" stroke-opacity=".5" stroke-dasharray="4 5"/>',
           f'<text x="{cx + 8}" y="412" fill="#FFB340">to the observer</text>',
           f'<circle cx="{cx}" cy="{cy}" r="9" fill="#{"".join(f"{v:02x}" for v in rgb)}"/>']
    T = ps[-1]["P"]
    gx, gw, lane = 470, 500, min(64, 360 / len(ps))
    dmax = max((p["depth_ppm"] or 0) for p in ps) or 1
    for i, p in enumerate(ps):
        r = R * p["a"] / amax
        th = math.pi / 2 + 2 * math.pi * phase0(i)
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        col = _colour(p["look"])
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="rgba(255,255,255,.14)"/>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{col}"/><text x="{x + 8:.1f}" y="{y - 7:.1f}">{e(_short(p["name"], star))}</text>')
        base = 40 + i * lane
        d = []
        if p["depth_ppm"]:
            h = max(2.0, p["depth_ppm"] / dmax * (lane - 26))
            w = max(2.0, (p["dur_h"] or 1) / 24 / T * gw)
            n0 = math.ceil(phase0(i) - 1e-9)
            for n in range(n0, n0 + int(T / p["P"]) + 2):
                tc = (n - phase0(i)) * p["P"]  # conjunction: days / P + phase is a whole number
                if 0 <= tc <= T:
                    xc = gx + tc / T * gw
                    d.append(f"L{xc - w / 2:.1f} {base:.1f}V{base + h:.1f}H{xc + w / 2:.1f}V{base:.1f}")
        lab = f'{e(_short(p["name"], star))} · {p["P"]:.2f} d · ' + (f'{p["depth_ppm"]:,.0f} ppm' if p["depth_ppm"] else "radius not stored")
        out.append(f'<path d="M{gx} {base:.1f}{"".join(d)}H{gx + gw}" stroke="{col}" stroke-width="1.6" fill="none"/>'
                   f'<text x="{gx}" y="{base - 6:.1f}">{lab}</text>')
    out.append(f'<text x="{gx}" y="22" fill="#9AA3B5">One {T:.2f}-day period · depth k² (ppm), one scale</text>')
    return (f'<svg class="orbsvg" viewBox="0 0 1000 430" role="img" aria-label="{e(label)}"><g font-size="15" fill="#ECEFF5" '
            f'font-family="var(--mono)">{"".join(out)}</g></svg>')


def html(data: dict, **opts) -> str:
    """The figure, or "" with fewer than two drawable planets. ``data`` as the module docstring says."""
    require_source(data)
    e = _html.escape
    rows = data.get("planets") or []
    ps = system(rows)
    if len(ps) < 2:
        return ""
    star = data.get("star") or ""
    teff = _num(data.get("teff")) or next((_num(r.get("steff")) for r in rows if _num(r.get("steff"))), None)
    inset = bool(data.get("inset") or opts.get("inset"))
    uid = e(data.get("uid") or opts.get("uid") or "orb")
    T = ps[-1]["P"]
    # 1.6 days a second; faster for a long outer period (a loop of at most 12 s), but never so fast that the innermost
    # planet laps in under 1.5 s.
    speed = max(DAYS_PER_S, min(T / LOOP_MAX_S, ps[0]["P"] / INNER_MIN_S))
    label = (f"The {len(ps)} planets of {star} seen from above, with their dips over one {T:.2f}-day period of the outermost: "
             + "; ".join(f"{p['name']} every {p['P']:.2f} d at {p['a']:.4f} AU" + (f", {p['depth_ppm']:,.0f} ppm deep" if p["depth_ppm"] else "")
                         for p in ps) + ".")
    params = {"teff": teff, "speed": round(speed, 3), "planets": [
        {"n": _short(p["name"], star), "P": round(p["P"], 6), "a": round(p["a"], 6), "d": None if p["depth_ppm"] is None else round(p["depth_ppm"], 1),
         "w": None if p["dur_h"] is None else round(p["dur_h"], 3), "c": _colour(p["look"]), "f": phase0(i)} for i, p in enumerate(ps)]}
    def tr_row(p: dict) -> str:
        name = f'<a href="/planets/{e(p["slug"])}/">{e(p["name"])}</a>' if p.get("slug") else e(p["name"])
        rp = "—" if p["rp_re"] is None else "%.2f" % p["rp_re"]
        dep = "—" if p["depth_ppm"] is None else "{:,.0f}".format(p["depth_ppm"])
        kep = "*" if p["a_src"] != "catalogue" else ""
        return f'<tr><th scope="row">{name}</th><td>{p["P"]:,.4f}</td><td>{p["a"]:.4f}{kep}</td><td>{rp}</td><td>{dep}</td></tr>'

    tr = "".join(tr_row(p) for p in ps)
    left = [r.get("name") for r in rows if r.get("name") not in {p["name"] for p in ps}]
    note = f" Not drawn (no period, or no a and no star mass): {e(', '.join(n for n in left if n))}." if left else ""
    return (f'<figure class="orbits{" inset" if inset else ""}" id="{uid}" data-hint="Sizes not to scale · phases illustrative" data-viz="orbits" data-params=\'{e(json.dumps(params, separators=(",", ":")), quote=False)}\'>'
            f'<div class="stage orbstage"><div class="orbbox">{static_svg(ps, teff or 0, star, label)}</div>'
            f'<span class="stage-tag" data-i18n="label.model">Model from stored values</span>'
            f'<div class="stage-ctrls"><button class="btn" type="button" data-orb="play" aria-pressed="false" hidden>Play</button></div></div>'
            f'<div class="orbcam" role="group" aria-label="Camera: focus and zoom" hidden>'
            + "".join(f'<button class="chip" type="button" data-oc="{k}" aria-pressed="{str(k == "all").lower()}">{e(t)}</button>'
                      for k, t in [("all", "All"), ("star", "Star")] + [(str(i), _short(p["name"], star)) for i, p in enumerate(ps)])
            + '<button class="chip" type="button" data-oc="in" aria-label="Zoom in">+</button><button class="chip" type="button" data-oc="out" '
            'aria-label="Zoom out">−</button><button class="chip" type="button" data-oc="reset">Reset</button></div>'
            f'<figcaption class="skysrc">The {e(star)} system from above: each planet dips the star\'s light when it crosses the line of sight to the '
            f'observer. Orbit sizes are the stored semi-major axes (or Kepler\'s third law from the period and the star\'s mass); dip depth is '
            f'(Rp/R★)² from the stored radii. Circular orbits, star and planets not to scale, phases illustrative (no transit times are '
            f'stored).{note} Source: {e(data["source"])}.</figcaption>'
            f'<details class="orbtable"><summary>The planets: period, orbit and dip depth</summary><div class="tablewrap" tabindex="0" role="region" '
            f'aria-label="{e(star)}: period, orbit and dip depth"><table class="pltable"><thead><tr><th scope="col">Planet</th><th scope="col">P (d)</th>'
            f'<th scope="col">a (AU)</th><th scope="col">Rp (R⊕)</th><th scope="col">Depth k² (ppm)</th></tr></thead><tbody>{tr}</tbody></table></div>'
            f'<p class="small">a from {e(data["source"].split(",")[0])}; * from Kepler\'s third law (period and the star\'s mass). — : radius not stored.</p>'
            f'</details></figure>')


CSS = """
/* ---------- viz.orbits (V08): a system from above, and its dips ---------- */
.orbits{margin:0;display:grid;gap:8px;min-width:0}
.orbbox{position:relative;aspect-ratio:1000/430}
.orbbox>svg,.orbbox>canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.orbbox>svg[hidden]{display:none}
.orbstage .stage-ctrls [hidden]{display:none}
.orbcam{display:flex;flex-wrap:wrap;gap:6px}.orbcam[hidden]{display:none}.orbcam .chip,.gxcam .chip{min-width:44px}
.orbtable table{width:100%;table-layout:fixed;font-size:12.5px}
.orbtable th,.orbtable td{overflow-wrap:anywhere}
.orbtable td{font-family:var(--mono);font-variant-numeric:tabular-nums}
@media (max-width:699.98px){.orbbox.cv{aspect-ratio:4/5.4}}
"""

JS = r"""
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
"""

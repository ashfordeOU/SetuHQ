# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V01 hero: the featured run's star (TIC Teff and radius, stellar.json) with its catalogue planet crossing it, and the model light curve.

Used on: Home. Owner: P1 (docs/SITE.md, "The visual system").

What is drawn, and from what:

* the star in its blackbody colour (``looks.teff_rgb``) at the Teff the run stores (stellar.json: TESS Input Catalog
  v8.2), limb-darkened with ``methods.ld_coeffs`` (Claret 2017, TESS band);
* the run's known planet (the catalogue's, never a candidate) crossing it at Rp/R★ = the catalogue radius over the
  stored stellar radius, at the catalogue's impact parameter b (0.3, said to be illustrative, when none is stored);
  off the disc it is an artist's impression (``looks.look``), on the disc a silhouette;
* the light curve that crossing makes, with ``methods.transit_flux``: its depth and duration (T14 from the period,
  a and R★) are printed in the caption and the alt text.

The page is rendered with the lead run (stable for search engines and screenshots). With motion allowed, the script
features one eligible run per UTC day (a run with a catalogue planet; a false positive never is), loops the crossing
every 7.5 s while the hero is on screen and the tab is visible, and has a Pause button. Under reduced motion it shows
the designed still: mid-transit, the curve drawn in full, the depth labelled, the lead run.

Without JavaScript the still is an SVG image written here: the same star, planet silhouette and model curve.
"""

from __future__ import annotations

import html as _html
import json
import math
from urllib.parse import quote

from setuhq.looks import RJ_IN_RE, find_planet, look, row, seed, teff_rgb
from setuhq.renderer import LABEL_ART, PICTURES, figure
from setuhq.viz import require_source

RSUN_IN_RE = 109.076      # the Sun's radius in Earth radii (695,700 km / 6,378.137 km, the R⊕ that RJ_IN_RE uses)
AU_IN_RSUN = 215.032      # 1 AU in solar radii (149,597,870.7 km / 695,700 km)
B_ILLUSTRATIVE = 0.3      # the impact parameter drawn when the catalogue stores none (said so in the caption)
LOOP_S = 7.5


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def t14_hours(period_d: float, a_rs: float, k: float, b: float) -> float | None:
    """Total transit duration for a circular orbit (Seager & Mallén-Ornelas 2003, eq. 3)."""
    if not (period_d and a_rs and a_rs > 1):
        return None
    sin_i = math.sqrt(max(0.0, 1 - (b / a_rs) ** 2))
    x = math.sqrt(max(0.0, (1 + k) ** 2 - b * b)) / (a_rs * sin_i)
    return period_d / math.pi * math.asin(min(1.0, x)) * 24 if x > 0 else None


def _planet_name(ctx: dict, meta: dict) -> str | None:
    """The run's featured planet: the one its dips match, else the first known planet the worked example names."""
    if ctx.get("planet"):
        return ctx["planet"]
    for p in meta.get("planets") or []:
        if p.get("planet"):
            return p["planet"]
    return None


def featured(app: dict, run: str, meta: dict | None = None) -> dict | None:
    """The hero's model for one run, or None when it cannot be drawn honestly (no catalogue planet with a radius and
    a period, no stored star, or a known false positive)."""
    cat = app.get("catalogue")
    ctx = (app.get("run_ctx") or {}).get(run) or {}
    if meta is None:
        from setuhq.viz.gallery import showcase

        meta = showcase(app).get(run) or {}
    sp = ctx.get("star_params") or {}
    teff, rstar = _num(sp.get("teff")), _num(sp.get("radius"))
    name = _planet_name(ctx, meta)
    if not (cat and name and teff and rstar) or meta.get("false_positive"):
        return None
    i = find_planet(cat, name)
    if i is None:
        return None
    P = cat["planets"]
    rj, period, a = _num(P["radius"][i]), _num(P["period"][i]), _num(P["a"][i])
    if not (rj and period):
        return None
    from setuhq.methods import ld_coeffs, transit_flux

    rp_re = rj * RJ_IN_RE
    k = rp_re / (rstar * RSUN_IN_RE)
    b_cat = P.get("b", [None] * (i + 1))[i]
    b = float(b_cat) if isinstance(b_cat, (int, float)) and 0 <= b_cat < 1 + k else B_ILLUSTRATIVE
    b_src = "catalogue" if b == b_cat else "illustrative"
    if a is None:
        smass = _num(P["smass"][i])
        a = (smass * (period / 365.25) ** 2) ** (1 / 3) if smass else None
    a_rs = a * AU_IN_RSUN / rstar if a else None
    u1, u2 = ld_coeffs(teff)
    depth = (1 - transit_flux(b, k, u1, u2)) * 1e6
    t14 = t14_hours(period, a_rs, k, b) if a_rs else None
    lk = look(row(cat, i))
    slug = P["slug"][i]
    star = (ctx.get("star") or {}).get("name") or meta.get("star") or run
    shown = name if name == P["name"][i] else f"{name} ({P['name'][i]} in exoplanet.eu)"
    dur = f", {t14:.2f} h" if t14 else ""
    alt = (f"Model of {name} crossing {star} ({round(teff):,} K, {rstar:.2f} R☉): depth {depth:,.0f} ppm{dur}. "
           f"The planet is an artist's impression.")
    fetched = (cat.get("fetched_at") or "")[:10]
    src = f"{cat.get('source_short') or 'exoplanet.eu'}{', fetched ' + fetched if fetched else ''}"
    e = _html.escape
    bword = f"b {b:.2f} ({'exoplanet.eu' if b_src == 'catalogue' else 'not stored: illustrative'})"
    caption = (f"<b>Model from stored values.</b> {e(shown)}: Rp {rp_re:.2f} R⊕ ({e(src)}) over R★ {rstar:.2f} R☉ "
               f"and Teff {round(teff):,} K ({e(sp.get('source') or 'stellar.json')}) give Rp/R★ {k:.4f}; {e(bword)}, "
               f"P {period:.3f} d. Depth {depth:,.0f} ppm{dur} (quadratic limb darkening, Claret 2017). "
               f"{e(star)}'s star disc is in its blackbody colour; the planet is an artist's impression "
               f"({e(lk['composition'] or 'not drawn')}{', ' + e(lk['band']) if lk['band'] else ''}). "
               f'<a href="{PICTURES}">How the pictures are drawn ›</a>')
    return {"run": run, "star": star, "planet": name, "slug": slug, "teff": round(teff, 1), "rstar": round(rstar, 4),
            "rp_re": round(rp_re, 4), "k": round(k, 6), "b": round(b, 4), "b_src": b_src, "period_d": round(period, 6),
            "a_rs": round(a_rs, 3) if a_rs else None, "t14_h": round(t14, 3) if t14 else None, "depth_ppm": round(depth, 1),
            "ld": [round(u1, 4), round(u2, 4)], "look": lk["name"] or "ambiguous", "seed": seed(slug), "alt": alt,
            "caption": caption, "href": f"/planets/{slug}/"}


def runs(app: dict) -> list[dict]:
    """Every run the hero can feature, in the worked examples' order (docs/results/showcase.json)."""
    order = [c["run"] for c in app.get("showcase") or []] or list(app.get("run_ctx") or {})
    from setuhq.viz.gallery import showcase

    meta = showcase(app)
    out = [featured(app, r, meta.get(r) or {}) for r in order]
    return [x for x in out if x]


def from_app(app: dict) -> dict:
    """The hero's input: the lead run's model first, the others it rotates through, and the source line."""
    rs = runs(app)
    lead = (app.get("run") or {}).get("name")
    first = next((x for x in rs if x["run"] == lead), rs[0] if rs else None)
    cat = app.get("catalogue") or {}
    return {"source": f"{cat.get('source_name') or 'exoplanet.eu'} (fetched {(cat.get('fetched_at') or '')[:10]}); "
                      "the runs' stellar.json (TESS Input Catalog v8.2)" if rs else "",
            "lead": first, "runs": rs}


def still_svg(m: dict) -> str:
    """The no-JavaScript still (2.5.6): the star, the planet's silhouette at mid-transit and the model curve, drawn
    where the canvas draws them (its wide layout), as an SVG data URI."""
    from setuhq.methods import ld_intensity, transit_flux

    W, H = 1600, 840
    cx, cy, R = W * .69, H * .41, H * .3
    k, b, (u1, u2) = m["k"], m["b"], m["ld"]
    rgb = teff_rgb(m["teff"])
    stops = "".join(f'<stop offset="{i / 10:g}" stop-color="#{"".join(f"{round(c * ld_intensity(min(i / 10, .999), u1, u2)):02x}" for c in rgb)}"/>'
                    for i in range(11))
    hexc = "#" + "".join(f"{c:02x}" for c in rgb)
    gx, gw, gy, gh = W * .06, W * .43, H * .78, H * .15
    depth = 1 - transit_flux(b, k, u1, u2)
    lo = 1 - 1.4 * max(depth, 1e-5)
    pts = []
    for j in range(201):
        z = -1.6 + 3.2 * j / 200
        v = transit_flux(math.hypot(z, b), k, u1, u2)
        pts.append(f"{gx + (z + 1.6) / 3.2 * gw:.1f},{gy + (1 - v) / (1 - lo) * gh:.1f}")
    rp = max(2.0, R * k)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#000"/>'
           f'<defs><radialGradient id="g"><stop offset=".3" stop-color="{hexc}" stop-opacity=".32"/><stop offset="1" stop-color="{hexc}" stop-opacity="0"/></radialGradient>'
           f'<radialGradient id="s">{stops}</radialGradient></defs>'
           f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{R * 1.5:.0f}" fill="url(#g)"/><circle cx="{cx:.0f}" cy="{cy:.0f}" r="{R:.0f}" fill="url(#s)"/>'
           f'<circle cx="{cx:.0f}" cy="{cy + b * R:.1f}" r="{rp:.1f}" fill="#030406" stroke="rgba(170,210,255,.5)" stroke-width="1"/>'
           f'<path d="M{gx:.0f} {gy:.1f}H{gx + gw:.0f}" stroke="rgba(255,255,255,.14)" stroke-width="2"/>'
           f'<polyline points="{" ".join(pts)}" fill="none" stroke="#FFB340" stroke-width="3.2"/>'
           f'<text x="{gx:.0f}" y="{gy - 12:.0f}" fill="#9AA3B5" font-family="sans-serif" font-size="20">depth {depth * 1e6:,.0f} ppm (model)</text></svg>')
    return "data:image/svg+xml," + quote(svg, safe=" ,.:;=/#()-'\"")


def params(m: dict) -> dict:
    """What SetuRender.transit draws for this run (data-params)."""
    return {"teff": m["teff"], "ld": m["ld"], "k": m["k"], "b": m["b"], "period_d": m["period_d"], "t14_h": m["t14_h"],
            "depth_ppm": m["depth_ppm"], "look": m["look"], "seed": m["seed"], "loop_s": LOOP_S, "layout": "hero",
            "animate": False}


def html(data: dict, **opts) -> str:
    """The hero stage: the transit figure (still image, canvas once upgraded), its tag, its caption with the numbers
    and the source, and the Pause button. ``opts["copy"]`` is the heading block laid over the stage's left side."""
    require_source(data)
    m = data.get("lead")
    if not m:
        return ""
    e = _html.escape
    rot = [{"run": x["run"], "p": params(x), "alt": x["alt"], "caption": x["caption"]} for x in data.get("runs") or [m]]
    fig = figure("transit", params(m), m["alt"], m["caption"], label=LABEL_ART, size=512, uid="hero",
                 still=still_svg(m), priority=True)
    fig = fig.replace('class="stage rfig"', 'class="stage rfig herofig"', 1)
    fig = fig.replace('loading="lazy" ', "", 1)
    ctrls = '<div class="stage-ctrls heroctrls"><button class="btn" type="button" data-hero-pause aria-pressed="false" hidden>Pause</button></div>'
    fig = fig.replace('<div class="rbox">', '<div class="rbox">' + ctrls, 1)
    rotj = e(json.dumps(rot, separators=(",", ":"), ensure_ascii=False))
    return (f'<div class="herostage" data-viz="hero" data-run="{e(m["run"])}" data-rotate=\'{rotj}\'>'
            f'{opts.get("copy", "")}{fig}</div>')


def data(app_data: dict) -> dict:
    """The hero writes no section of stories.json: its runs ride in the page (data-rotate), so it never waits for a file."""
    return {}


CSS = """
/* ---------- viz.hero (V01): a live transit of the featured star behind the heading ---------- */
#route-overview>header.launch{display:block;text-align:left;padding:0;gap:0}
.herostage{position:relative;border-radius:var(--r-l);overflow:hidden;background:var(--stage);border:1px solid var(--stage-line)}
.herostage .herofig{border:0;border-radius:0}
.herostage .herofig .rbox{aspect-ratio:16/8.4;border-radius:0}
.herostage .herofig .rbox>img.rstill{object-fit:cover;object-position:75% 50%}
.herostage .herofig .readout{border-top:1px solid var(--stage-line);padding:10px 16px 12px;font-size:12px;line-height:1.5}
.herostage .herofig .readout b{color:var(--stage-ink);font-weight:600}
.herostage .stage-tag{top:14px;right:14px}
.herocopy{position:absolute;left:0;top:0;width:100%;z-index:1;padding-bottom:28px!important;display:flex;flex-direction:column;justify-content:flex-start;gap:16px;
  padding:clamp(28px,5.5%,72px) 0 0 clamp(20px,5%,64px);background:linear-gradient(90deg,#000 0 38%,transparent 70%);-webkit-mask:linear-gradient(180deg,#000 calc(100% - 28px),transparent);mask:linear-gradient(180deg,#000 calc(100% - 28px),transparent);color:var(--stage-ink);pointer-events:none}
.herocopy>*{pointer-events:auto;max-width:min(46%,540px)}
#route-overview .herocopy h1{margin:0;font:var(--t-hero);font-size:clamp(40px,5.2vw,76px);letter-spacing:-.045em;color:var(--stage-ink);text-wrap:balance}
#route-overview>header.launch .herocopy .sub{margin:0;font-size:clamp(15px,1.2vw,17px);line-height:1.5;color:#C9CFDB}
#route-overview .herocopy .ctas{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-start;margin:4px 0 0}
#route-overview .herocopy .btn.primary{background:var(--stage-ink);color:#04060B}
#route-overview .herocopy .btn.ghost{color:#64D2FF}
#route-overview .herocopy .btn.ghost:hover{color:#fff}
.herostage .heroctrls{left:auto;right:14px;bottom:14px}
.herostage .heroctrls .btn{min-height:36px;padding:0 14px;font-size:12.5px}
.herostage .heroctrls .btn[aria-pressed="true"]{background:var(--stage-ink);color:#04060B;border-color:transparent}
.herostage .heroctrls .btn[hidden]{display:none}
@media (max-width:899.98px){
  .herocopy{position:static;width:auto;aspect-ratio:auto;padding:28px 18px 8px;background:var(--stage)}
  .herocopy>*{max-width:none}
  .herostage .herofig .rbox{aspect-ratio:4/3.3}
  #route-overview .herocopy h1{font-size:clamp(36px,9vw,56px)}
  #route-overview .herocopy .ctas{flex-direction:column;align-items:stretch}
  .herostage .heroctrls{top:10px;left:10px;right:auto;bottom:auto}
  .herostage .heroctrls .btn{min-height:44px}
}
"""

JS = r"""
// ---------- viz.hero (V01): the featured star's transit, looped while on screen; Pause; a still under reduced motion ----------
window.SetuHero = window.SetuHero || {frames: 0, playing: false};
(function(){
  const RMq = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  function setup(st){
    if (st._hero) return; st._hero = true;
    const fig = st.querySelector('.herofig'), btn = st.querySelector('[data-hero-pause]'); if (!fig) return;
    let rot = []; try { rot = JSON.parse(st.dataset.rotate || '[]'); } catch (e) { rot = []; }
    const S = {vis: false, paused: RMq(), raf: 0, t0: 0, el: 0, last: 0, times: [], slow: false, p: null};
    try { S.p = JSON.parse(fig.dataset.params || '{}'); } catch (e) { S.p = {}; }
    const cv = () => fig._sr && fig._sr.cv;
    function draw(t){ const c = cv(); if (!c || !window.SetuRender) return false; SetuRender.transit(c, Object.assign({}, S.p, {t})); return true; }
    // One featured run per UTC day (the same for every visitor that day); the page itself is rendered with the lead.
    if (!RMq() && rot.length > 1){
      const pick = rot[Math.floor(Date.now() / 864e5) % rot.length];
      if (pick && pick.run !== st.dataset.run){
        S.p = pick.p; st.dataset.run = pick.run; fig.dataset.params = JSON.stringify(pick.p);
        const img = fig.querySelector('img.rstill'), cap = fig.querySelector('figcaption');
        if (img) img.alt = pick.alt; if (cap) cap.innerHTML = pick.caption;
        if (fig._sr){ fig._sr.p = pick.p; fig._sr.cv.setAttribute('aria-label', pick.alt); draw(null); }
      }
    }
    function setBtn(){ if (!btn) return; btn.setAttribute('aria-pressed', S.paused ? 'true' : 'false'); btn.hidden = !cv(); }
    function frame(now){
      S.raf = 0; if (!want()) return;
      const fps = S.slow ? 30 : 60; if (now - S.last < 1000 / fps - 1){ S.raf = requestAnimationFrame(frame); return; }
      S.el += Math.min(100, now - (S.last || now)); S.last = now;
      const a = performance.now(); if (!draw(S.el / 1000)) return; const dt = performance.now() - a;
      SetuHero.frames++; S.times.push(dt); if (S.times.length > 60) S.times.shift();
      if (S.times.length === 60){ const m = S.times.slice().sort((x, y) => x - y)[30]; if (m > 33){ S.paused = true; S.dead = true; draw(null); setBtn(); return; } S.slow = m > 20; }
      S.raf = requestAnimationFrame(frame);
    }
    const want = () => S.vis && !S.paused && !document.hidden && !S.dead && !!cv();
    function kick(){ SetuHero.playing = want(); if (SetuHero.playing && !S.raf){ S.last = 0; S.raf = requestAnimationFrame(frame); } if (!SetuHero.playing && S.raf){ cancelAnimationFrame(S.raf); S.raf = 0; } }
    function ensure(){ if (!fig._sr && window.SetuRender && !fig.closest('[hidden]')) { try { SetuRender.mount(fig.parentElement); } catch (e) { /* the still stays */ } }
      if (fig._sr && rot.length && fig._sr.cv.getAttribute('aria-label') !== (fig.querySelector('img.rstill') || {}).alt){ fig._sr.p = S.p; fig._sr.cv.setAttribute('aria-label', fig.querySelector('img.rstill').alt); draw(null); } setBtn(); }
    if (btn) btn.addEventListener('click', () => { S.paused = !S.paused; S.dead = false; S.times = []; setBtn(); kick(); });
    document.addEventListener('visibilitychange', kick);
    if ('IntersectionObserver' in window) new IntersectionObserver(es => es.forEach(en => { S.vis = en.isIntersecting; if (S.vis) ensure(); kick(); }), {rootMargin: '80px'}).observe(fig);
    else { S.vis = true; ensure(); kick(); }
    ensure();
  }
  const all = () => document.querySelectorAll('.herostage[data-viz="hero"]').forEach(setup);
  window.SetuHero.setup = all;
  all();
})();
"""

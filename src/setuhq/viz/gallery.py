# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V03 gallery: one 1:1 render stage per worked example (showcase.json order), star disc and silhouettes.

Used on: Home. Owner: P1 (docs/SITE.md, "The visual system").

Each card's stage is a model from stored values, never planet art:

* the star disc in its blackbody colour at the Teff the run stores (stellar.json: TESS Input Catalog v8.2);
* a silhouette for each planet the run measured, at the run's own fitted Rp/R★ (docs/results/showcase.json, and for
  pi Men the joint fit in docs/results/pi_men_validation.json): what SetuHQ measured is a shadow, not a world;
* a planet the run did not recover as a dashed outline at the catalogue's Rp/R★, labelled so (TOI-270 b);
* a known false positive (TOI-236) as a neutral, unlit occulter at √depth, labelled "occulter not identified", with
  what vetting found (showcase.json ``false_positive``).

Sizes are to scale against the disc; where on the disc each sits is illustrative, and the caption says both. The
server writes the stage as SVG (the still, and all a page without JavaScript shows); the script redraws it once on a
canvas with the shared renderer's star (granulation and glow) when it comes on screen. Nothing on it animates.
"""

from __future__ import annotations

import html as _html
import json
import math
from pathlib import Path

from setuhq.looks import teff_rgb
from setuhq.viz import require_source

LABEL = "Model from stored values"
SIZE = 240          # the SVG stage's side, in its own units
R_FRAC = 0.30       # the star's radius as a fraction of the side
LOCATE_PX = 3.0     # a silhouette smaller than this (stage units) gets a locator ring
NEUTRAL = (150, 150, 150)
TIC = "TIC v8.2"


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def _validation_k(meta: dict, planet: str | None) -> float | None:
    """The joint fit's Rp/R★ for a run checked in full (pi Men: its validation JSON beside the stored Markdown)."""
    path = meta.get("validation")
    if not path:
        return None
    p = Path(path).with_suffix(".json")
    try:
        v = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return _num((v.get("joint_fit") or {}).get("k"))


def showcase(app: dict) -> dict[str, dict]:
    """The worked examples' full records (docs/results/showcase.json, the file the build read), by run name."""
    path = app.get("showcase_source")
    if not path:
        return {}
    try:
        return {r["run"]: r for r in json.loads(Path(path).read_text()).get("runs") or []}
    except (OSError, ValueError):
        return {}


def _letter(name: str) -> str:
    return name.rsplit(" ", 1)[-1] if " " in name else name


def stage(card: dict, app: dict, meta: dict | None = None) -> dict:
    """What one card's stage draws, with the source of each number (``meta``: the run's showcase.json record)."""
    run = card["run"]
    ctx = (app.get("run_ctx") or {}).get(run) or {}
    meta = meta if meta is not None else showcase(app).get(run) or {}
    sp = ctx.get("star_params") or {}
    teff = _num(sp.get("teff"))
    bodies: list[dict] = []
    note = ""
    fp = meta.get("false_positive")
    if fp:
        s = fp.get("setuhq") or {}
        depth = _num(s.get("depth_ppm"))
        if depth:
            bodies.append({"name": "occulter not identified", "k": math.sqrt(depth * 1e-6), "kind": "occ", "src": "√depth, run fit"})
        rej = (fp.get("outcomes") or {}).get("rejected")
        snr = _num(s.get("secondary_snr"))
        bits = []
        if snr:
            bits.append(f"secondary eclipse at SNR {snr:.1f}")
        if rej:
            n = fp.get("dips_on_ephemeris") or rej
            bits.append(f"all {rej} dips rejected by vetting" if rej == n else f"{rej} of {n} dips rejected by vetting")
        note = "; ".join(bits)
    else:
        cat = app.get("catalogue")
        for p in meta.get("planets") or []:
            name = p.get("planet") or ""
            k = _num((p.get("setuhq") or {}).get("rp_rs"))
            if k:
                bodies.append({"name": name, "k": k, "kind": "sil", "src": "run fit"})
            elif not p.get("recovered_transits") and cat:
                from setuhq.looks import RJ_IN_RE, find_planet

                i = find_planet(cat, name)
                if i is not None:
                    rj, srad = _num(cat["planets"]["radius"][i]), _num(cat["planets"]["srad"][i])
                    if rj and srad:
                        bodies.append({"name": name, "k": rj * RJ_IN_RE / (srad * 109.076), "kind": "missed",
                                       "src": f"{cat.get('source_short') or 'exoplanet.eu'}, not recovered by this run"})
        if not bodies:
            k = _validation_k(meta, ctx.get("planet"))
            if k and ctx.get("planet"):
                bodies.append({"name": ctx["planet"], "k": k, "kind": "sil", "src": "run fit"})
        if not bodies:
            lead = ctx.get("lead") or {}
            depth = _num(lead.get("depth_ppm"))
            if depth:
                bodies.append({"name": "lead signal", "k": math.sqrt(depth * 1e-6), "kind": "sil", "src": "√depth of the lead signal"})
    n = len(bodies)
    for j, b in enumerate(bodies):  # where each sits on the disc is illustrative; only the sizes are to scale
        b["x"] = 0.0 if n == 1 and b["kind"] == "occ" else (0.32 if n == 1 else -0.5 + j / (n - 1))
        b["y"] = 0.0 if b["kind"] == "occ" else (0.12 if j % 2 == 0 else -0.16)
        b["k"] = round(b["k"], 5)
    return {"run": run, "star": card["star"], "teff": round(teff, 1) if teff else None, "teff_src": sp.get("source") or "",
            "bodies": bodies, "note": note}


def caption(st: dict) -> str:
    """The card stage's visible caption, short and the same shape on every card: the star's Teff and its source, then
    each body drawn with its Rp/R★ and where that number comes from. What is common to every stage (the disc is in its
    blackbody colour; sizes to scale, positions illustrative) is said once, under the gallery (:data:`STAGE_NOTE`)."""
    t = f"Star {round(st['teff']):,} K ({TIC})" if st["teff"] else "No Teff stored: neutral grey disc"
    parts = []
    for b in st["bodies"]:
        if b["kind"] == "occ":
            parts.append(f"occulter not identified, √depth {b['k']:.3f} (run fit)")
        elif b["kind"] == "missed":
            parts.append(f"{_letter(b['name'])} dashed, Rp/R★ {b['k']:.4f} ({b['src']})")
        else:
            parts.append(f"{_letter(b['name'])} Rp/R★ {b['k']:.4f} ({b['src']})")
    body = " · ".join([t] + parts)
    if st["note"]:
        body += f" · {st['note']}"
    return body + "."


# What every stage shares, said once under the cards rather than on each.
STAGE_NOTE = ("Each stage: the star's disc in its blackbody colour at the Teff its run stores, and what the run measured "
              "as a shadow at its fitted Rp/R★ (a planet the run missed is a dashed outline). Sizes are to scale against "
              "the disc; where each sits on it is illustrative.")


def svg(st: dict, uid: str) -> str:
    """The stage as SVG: the still a page without JavaScript shows (aria-hidden; the caption carries the numbers)."""
    from setuhq.methods import ld_coeffs, ld_intensity

    W = SIZE
    c, R = W / 2, W * R_FRAC
    rgb = teff_rgb(st["teff"]) if st["teff"] else NEUTRAL
    u1, u2 = ld_coeffs(st["teff"] or 5772)
    stops = "".join(f'<stop offset="{i / 10:g}" stop-color="#{"".join(f"{round(v * ld_intensity(min(i / 10, .999), u1, u2)):02x}" for v in rgb)}"/>'
                    for i in range(11))
    hexc = "#" + "".join(f"{v:02x}" for v in rgb)
    out = [f'<svg class="gsvg" viewBox="0 0 {W} {W}" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false"><defs>'
           f'<radialGradient id="gg-{uid}"><stop offset=".45" stop-color="{hexc}" stop-opacity=".3"/><stop offset="1" stop-color="{hexc}" stop-opacity="0"/></radialGradient>'
           f'<radialGradient id="gs-{uid}">{stops}</radialGradient></defs>'
           f'<circle cx="{c:g}" cy="{c:g}" r="{R * 1.55:.1f}" fill="url(#gg-{uid})"/><circle cx="{c:g}" cy="{c:g}" r="{R:g}" fill="url(#gs-{uid})"/>']
    for b in st["bodies"]:
        x, y, r = c + b["x"] * R, c + b["y"] * R, max(0.8, b["k"] * R)
        if b["kind"] == "occ":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#2A2E36" stroke="#9AA3B5" stroke-width="1" stroke-dasharray="3 3"/>'
                       f'<text x="{c:g}" y="{c + R + 26:.0f}" text-anchor="middle" fill="#9AA3B5" font-size="10.5" font-family="monospace">occulter not identified</text>')
        elif b["kind"] == "missed":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" stroke="#ECEFF5" stroke-width=".9" stroke-dasharray="2 2"/>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#030406" stroke="rgba(170,210,255,.5)" stroke-width=".6"/>')
        if b["kind"] != "occ":
            if r < LOCATE_PX:
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="none" stroke="rgba(4,6,11,.55)" stroke-width="1"/>')
            out.append(f'<text x="{x:.1f}" y="{y - max(r, 7) - 5:.1f}" text-anchor="middle" fill="#04060B" font-size="11" font-weight="600" font-family="sans-serif">{_html.escape(_letter(b["name"]))}</text>')
    return "".join(out) + "</svg>"


def figure(st: dict, uid: str) -> str:
    e = _html.escape
    cap = caption(st)
    p = {"teff": st["teff"], "bodies": [{k: b[k] for k in ("x", "y", "k", "kind")} | {"l": _letter(b["name"])} for b in st["bodies"]]}
    return (f"<figure class=\"stage gstage\" data-viz=\"gstage\" data-params='{e(json.dumps(p, separators=(',', ':')))}' "
            f'aria-labelledby="gcap-{uid}"><div class="gbox">{svg(st, uid)}</div><span class="stage-tag">{LABEL}</span>'
            f'<figcaption id="gcap-{uid}" class="readout">{e(cap)}</figcaption></figure>')


def from_app(app: dict) -> dict:
    """The gallery's input: the worked examples in showcase.json order, each with its stage."""
    cards = app.get("showcase") or []
    meta = showcase(app)
    return {"source": (app.get("showcase_source") or "docs/results/showcase.json") + "; each run's stellar.json (TESS Input Catalog v8.2)"
            if cards else "", "cards": cards, "stages": {c["run"]: stage(c, app, meta.get(c["run"]) or {}) for c in cards}}


def html(data: dict, **opts) -> str:
    """The worked examples: one card per stored run, its stage on top of its text (kind, summary, dip count, caveat,
    panel, pages). ``data``: ``source``, ``cards`` (app_data["showcase"]), ``stages`` (from :func:`stage`)."""
    require_source(data)
    e = _html.escape
    cards = data.get("cards") or []
    if not cards:
        return ""
    items = []
    for c in cards:
        first = c["lead_dip"]
        sectors = ", ".join(str(x) for x in c["sectors"]) or "not stored"
        links = (f'<a href="{e(c["case_file"])}">Case file</a><a href="{e(c["plates"])}">Plates</a>'
                 f'<a href="{e(c["report"])}">Run report</a>')
        st = (data.get("stages") or {}).get(c["run"])
        items.append(f"""<li><article class="excard" aria-labelledby="ex-{e(c["slug"])}">{figure(st, e(c["slug"])) if st else ""}
          <div class="exbody"><p class="exkind">{e(c["kind"] or "Example run")}</p>
          <h3 id="ex-{e(c["slug"])}">{f'<a href="#/transit?dip={e(first)}">{e(c["star"])}</a>' if first else e(c["star"])}</h3>
          <p class="exsum">{e(c["summary"])}</p>
          <p class="excount">{e(c["count"])}</p>{f'<p class="excaveat">{e(c["caveat"])}</p>' if c["caveat"] else ""}
          <p class="exmeta">{e(c["mission"])} sector{"s" if len(c["sectors"]) != 1 else ""} {e(sectors)} · {e(c["panel_label"])}</p>
          <p class="exlinks">{links}</p></div>
        </article></li>""")
    return f"""<section class="examples" id="examples" aria-labelledby="h-examples">
        <div class="secthead"><h2 id="h-examples">Worked examples: {len(cards)} stars, one pipeline</h2>
        <p>Each is a stored run on public TESS light curves from MAST, with its data, configuration and code hashed. Every dip is counted by its vetting outcome; a candidate stays unconfirmed, and a rejected dip is not a candidate.</p></div>
        <ul class="excards">{"".join(items)}</ul>
        <p class="bandsrc">{e(STAGE_NOTE)} No candidate is given planet art. Stages: {e(data["source"])}.</p>
      </section>"""


def data(app_data: dict) -> dict:
    """The home page's sections of stories.json: the gallery's stages and the evidence counters (both phase 1)."""
    from setuhq.home import counters

    g = from_app(app_data)
    out = {}
    if g["cards"]:
        out["gallery"] = {"source": g["source"], "cards": [g["stages"][c["run"]] for c in g["cards"]]}
    cs = counters(app_data)
    if cs:
        out["counters"] = cs
    return out


CSS = """
/* ---------- viz.gallery (V03): each worked example's star in its colour, what the run measured as shadows ---------- */
#route-overview .excards{grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr));row-gap:16px}
/* Every card in a row has the same shape: its stage, caption and text sit on shared row lines (subgrid). */
#route-overview .excards>li{display:grid;grid-row:span 3;grid-template-rows:subgrid}
#route-overview .excard{grid-row:span 3;display:grid;grid-template-rows:subgrid;padding:0;overflow:hidden;gap:0;background:var(--bg-2);-webkit-backdrop-filter:none;backdrop-filter:none;transition:transform var(--d-2) var(--ease),border-color var(--d-2) var(--ease)}
#route-overview .excard .gstage{grid-row:span 2;grid-template-rows:subgrid}
#route-overview .excard:hover{transform:translateY(-2px);border-color:var(--line-3)}
.exbody{display:flex;flex-direction:column;gap:6px;padding:14px 16px 16px;flex:1}
.exbody p{margin:0}
.gstage{margin:0;border:0;border-bottom:1px solid var(--line);border-radius:0;display:grid}
.gbox{position:relative;aspect-ratio:1/1;background:var(--stage)}
.gbox>svg,.gbox>canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.gbox>svg[hidden]{display:none}
.gstage .stage-tag{font-size:10px;min-height:22px;padding:2px 7px}
.gstage .readout{background:var(--stage);color:var(--stage-dim);padding:8px 12px 10px;margin:0;font:var(--t-data);letter-spacing:0;font-size:11.5px}
@media (max-width:699.98px){
  .gbox{aspect-ratio:16/10}
  .gstage .readout{font-size:11.5px}
}
.bandsrc{margin:0;font-size:12px;line-height:1.45;color:var(--ink-3);max-width:90ch}
"""

JS = r"""
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
"""

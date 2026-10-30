# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V09 temperature strip: teff_rgb from 2,500 to 10,000 K with the showcase stars' TIC Teff and the Sun marked; a two-handle filter mode.

Used on: Home, catalogue filter, Methods equations. Owner: P1 (docs/SITE.md, "The visual system").

The strip is a CSS ``linear-gradient`` of 31 stops (every 250 K), each ``looks.teff_rgb``: a Planck spectrum through
the CIE 1931 colour-matching functions, in sRGB, normalised to the brightest channel (a hue, not a brightness). It is
written at build time and needs no JavaScript. Each marker is a star's Teff as stored (the runs' stellar.json, from
the TESS Input Catalog v8.2) or the Sun at 5,772 K; the same markers are listed under the strip, which is also its
text alternative.

Filter mode (``html(data, filter=True)``; the catalogue wires it): two ``<input type=range>`` handles over the strip.
Moving either dispatches a bubbling ``setu:teff-range`` CustomEvent with ``{lo, hi}`` in kelvin from the strip's root
(``[data-viz="tempstrip"][data-filter="1"]``).
"""

from __future__ import annotations

import html as _html

from setuhq.looks import T_SUN, teff_rgb
from setuhq.i18n import N_, k as ik, ka
from setuhq.viz import require_source

LO, HI, STEP = 2500, 10000, 250
AXIS = (2500, 4000, 5500, 7000, 8500, 10000)
SUN = {"name": N_("ts.sun", "the Sun"), "teff": T_SUN, "sun": True}
GAP = 9.0  # % of the strip that two labels on one row keep between them (desktop)


def gradient(lo: int = LO, hi: int = HI, step: int = STEP) -> str:
    """The strip's CSS gradient: one stop per ``step`` kelvin, each in its blackbody colour (31 stops by default)."""
    stops = []
    for t in range(lo, hi + 1, step):
        r, g, b = teff_rgb(t)
        stops.append(f"#{r:02x}{g:02x}{b:02x} {100 * (t - lo) / (hi - lo):g}%")
    return "linear-gradient(90deg," + ",".join(stops) + ")"


def pos(teff: float, lo: int = LO, hi: int = HI) -> float:
    """A temperature's place along the strip, in percent (clamped to the strip)."""
    return max(0.0, min(100.0, 100 * (teff - lo) / (hi - lo)))


def rows(xs: list[float], gap: float = GAP) -> list[int]:
    """A label row for each marker (given sorted by position), so labels on one row keep ``gap`` apart."""
    last: list[float] = []
    out = []
    for x in xs:
        for i, prev in enumerate(last):
            if x - prev >= gap:
                last[i] = x
                out.append(i)
                break
        else:
            last.append(x)
            out.append(len(last) - 1)
    return out


def html(data: dict, **opts) -> str:
    """The strip with its markers and their list. ``data``: ``source`` (required, printed), ``markers`` [{name, teff,
    href?, note?}] (the Sun is added unless ``data["sun"]`` is False), optional ``title``. ``filter=True`` adds the
    two range handles (``lo``/``hi`` set where they start)."""
    require_source(data)
    e = _html.escape
    marks = [dict(m) for m in data.get("markers") or [] if m.get("teff")]
    if data.get("sun", True):
        marks.append(dict(SUN))
    if not marks:
        return ""
    marks.sort(key=lambda m: m["teff"])
    xs = [pos(m["teff"]) for m in marks]
    lv = rows(xs)
    pins, items = [], []
    for m, x, r in zip(marks, xs, lv):
        rgb = teff_rgb(m["teff"])
        t = f"{round(m['teff']):,} K"
        pins.append(f'<span class="tsmark{" sun" if m.get("sun") else ""}" style="left:{x:.2f}%;--row:{r}" aria-hidden="true">'
                    f'<b{ik("ts.sun") if m.get("sun") else ""}>{e(m["name"])}</b><i>{t}</i></span>')
        name = f'<a href="{e(m["href"])}">{e(m["name"])}</a>' if m.get("href") else (f'<span{ik("ts.sun")}>{e(m["name"])}</span>' if m.get("sun") else e(m["name"]))
        note = f' <span class="tsnote">{e(m["note"])}</span>' if m.get("note") else ""
        items.append(f'<li data-teff="{round(m["teff"])}"><i class="tsdot" style="background:#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}" aria-hidden="true"></i>'
                     f'<span>{name} <span class="tsk">{t}</span>{note}</span></li>')
    axis = "".join(f'<span style="left:{pos(t):g}%">{t:,} K</span>' for t in AXIS)
    filt, flag = "", ""
    if opts.get("filter"):
        lo, hi = int(opts.get("lo", LO)), int(opts.get("hi", HI))
        flag = ' data-filter="1"'
        filt = (f'<div class="tsfilter"><label class="sr" for="ts-lo"{ik("ts.lo")}>{N_("ts.lo", "Coolest star, in kelvin")}</label>'
                f'<input id="ts-lo" type="range" min="{LO}" max="{HI}" step="50" value="{lo}" data-ts="lo" aria-valuetext="{lo:,} K">'
                f'<label class="sr" for="ts-hi"{ik("ts.hi")}>{N_("ts.hi", "Hottest star, in kelvin")}</label>'
                f'<input id="ts-hi" type="range" min="{LO}" max="{HI}" step="50" value="{hi}" data-ts="hi" aria-valuetext="{hi:,} K"></div>')
    title = data.get("title") or N_("ts.title", "Star colour from 2,500 K to 10,000 K, with each star marked at its temperature")
    tk = "" if data.get("title") else ka(aria_label="ts.title")
    ticks = "".join(f'<span class="tstick" style="left:{x:.2f}%" aria-hidden="true"></span>' for x in xs)
    return (f'<figure class="tstrip" data-viz="tempstrip"{flag} style="--rows:{max(lv) + 1}">'
            f'<div class="tsmarks">{"".join(pins)}</div>'
            f'<div class="tsbar" role="img" aria-label="{e(title)}"{tk} style="background:{gradient()}">{ticks}{filt}</div>'
            f'<div class="tsaxis" aria-hidden="true">{axis}</div>'
            f'<figcaption><ul class="tslist">{"".join(items)}</ul><p class="tssrc">{data["source"]}</p></figcaption></figure>')


CSS = """
/* ---------- viz.tempstrip (V09): star colour from 2,500 K to 10,000 K ---------- */
.tstrip{margin:0;display:grid;gap:8px;min-width:0}
.tsmarks{position:relative;height:calc(var(--rows,1) * 30px + 34px)}
.tsmark{position:absolute;bottom:0;transform:translateX(-50%);display:grid;justify-items:center;gap:1px;font:500 11px/1.2 var(--mono);color:var(--ink-2);white-space:nowrap;padding-bottom:calc(var(--row) * 30px + 8px)}
.tsmark::after{content:"";position:absolute;left:50%;bottom:0;width:1px;height:calc(var(--row) * 30px + 6px);background:var(--line-3)}
.tsmark b{font-weight:600;color:var(--ink)}
.tsmark i{font-style:normal;color:var(--ink-3)}
.tsmark.sun b{color:var(--ink-2);font-weight:500}
.tsbar{position:relative;height:40px;border-radius:var(--r-s);border:1px solid var(--line)}
.tstick{position:absolute;top:-4px;bottom:-4px;width:2px;margin-left:-1px;background:#04060B;box-shadow:0 0 0 1px rgba(255,255,255,.7);border-radius:2px}
.tsaxis{position:relative;height:16px;font:400 11px/1 var(--mono);color:var(--ink-3)}
.tsaxis span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}
.tsaxis span:first-child{transform:none}
.tsaxis span:last-child{transform:translateX(-100%)}
.tstrip figcaption{display:grid;gap:10px}
.tslist{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px 20px;font-size:13.5px;color:var(--ink-2)}
.tslist li{display:inline-flex;align-items:center;gap:8px}
.tslist a{color:var(--ink)}
.tsk{font:var(--t-data);color:var(--ink-3)}
.tsnote{color:var(--ink-3);font-size:12.5px}
.tsdot{width:12px;height:12px;border-radius:50%;border:1px solid var(--line-2);flex:none}
.tssrc{margin:0;font-size:12px;line-height:1.45;color:var(--ink-3);max-width:90ch}
.tsfilter{position:absolute;inset:0}
.tsfilter input{position:absolute;inset:0;width:100%;height:100%;margin:0;background:none;pointer-events:none;-webkit-appearance:none;appearance:none}
.tsfilter input::-webkit-slider-thumb{pointer-events:auto;-webkit-appearance:none;width:22px;height:44px;border-radius:8px;background:var(--ink);border:2px solid var(--bg);cursor:ew-resize}
.tsfilter input::-moz-range-thumb{pointer-events:auto;width:22px;height:44px;border-radius:8px;background:var(--ink);border:2px solid var(--bg);cursor:ew-resize}
@media (max-width:699.98px){
  .tsmarks{display:none}
  .tsaxis span:nth-child(even){display:none}
}
"""

JS = r"""
// ---------- viz.tempstrip (V09): in filter mode the two handles announce {lo, hi} as setu:teff-range ----------
(function(){
  function wire(root){
    if (root._ts) return; root._ts = true;
    const lo = root.querySelector('[data-ts="lo"]'), hi = root.querySelector('[data-ts="hi"]'); if (!lo || !hi) return;
    const send = src => {
      let a = Number(lo.value), b = Number(hi.value);
      if (a > b){ if (src === lo) lo.value = a = b; else hi.value = b = a; }
      lo.setAttribute('aria-valuetext', a.toLocaleString('en-US') + ' K'); hi.setAttribute('aria-valuetext', b.toLocaleString('en-US') + ' K');
      root.dispatchEvent(new CustomEvent('setu:teff-range', {bubbles: true, detail: {lo: a, hi: b}}));
    };
    lo.addEventListener('input', () => send(lo)); hi.addEventListener('input', () => send(hi));
  }
  window.SetuTempstrip = {wire: root => Array.from(root ? [root] : document.querySelectorAll('[data-viz="tempstrip"][data-filter="1"]')).forEach(wire)};
  window.SetuTempstrip.wire();
})();
"""

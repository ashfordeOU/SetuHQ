# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The one source of SetuHQ's look: colour tokens (dark and light), type, space, radius, motion, the stage
component, the odometer and the chart crosshair.

Every page reads these: the app's stylesheet (:func:`tokens_css` at its top), the header and footer around the
stand-alone pages (``.shellscope``), the stand-alone case file, plates and report (through aliases, so their own
CSS keeps its names), and the README figures (tools/gen_readme_assets.py). Accent hues are the ones the logo, the
figures and the plates already use; the surfaces, ink, type and motion are the approved redesign's.

Motion has one curve (``--ease``) and three durations (``--d-1`` 150 ms, ``--d-2`` 350 ms, ``--d-3`` 600 ms); under
``prefers-reduced-motion: reduce`` the durations are 0 ms. :func:`motion_problems` is the lint the tests run over
every stylesheet.
"""

from __future__ import annotations

import html
import re

# ---------- colour: {name: (dark, light)} ----------
TOKENS: dict[str, tuple[str, str]] = {
    "bg": ("#04060B", "#F5F5F7"),
    "bg-2": ("#080B12", "#FFFFFF"),
    "bg-3": ("#121826", "#E8E8ED"),
    "panel": ("#0B0F18", "#FFFFFF"),
    "glass": ("rgba(11,15,24,.72)", "rgba(255,255,255,.72)"),
    "glass-2": ("rgba(11,15,24,.55)", "rgba(255,255,255,.6)"),
    "panel-2": ("rgba(255,255,255,.05)", "rgba(0,0,0,.05)"),
    "line": ("#1B2232", "rgba(0,0,0,.08)"),
    "line-2": ("#262F44", "rgba(0,0,0,.14)"),
    "line-3": ("#39435A", "rgba(0,0,0,.26)"),
    "ink": ("#ECEFF5", "#1D1D1F"),
    "ink-2": ("#AEB6C6", "#424245"),
    "ink-3": ("#8A93A6", "#5E5E63"),
    "blue": ("#0A84FF", "#0066CC"),
    "sen": ("#64D2FF", "#006E99"),
    "prb": ("#BF5AF2", "#8944AB"),
    "prb-ink": ("#D0A8FF", "#8944AB"),
    "yellow": ("#FFD60A", "#7A5600"),
    "red": ("#FF453A", "#C9001B"),
    "green": ("#30D158", "#1F7A35"),
    "star": ("#FFB340", "#A05A00"),
    "amber": ("#FFB340", "#A05A00"),
    "cyan": ("#64D2FF", "#0066CC"),
    "lime": ("#30D158", "#1F7A35"),
    "coral": ("#FF6961", "#C9001B"),
    "magenta": ("#BF5AF2", "#8944AB"),
    "cyan-soft": ("rgba(100,210,255,.12)", "rgba(0,102,204,.1)"),
    "lime-soft": ("rgba(48,209,88,.14)", "rgba(31,122,53,.12)"),
    "amber-soft": ("rgba(255,179,64,.14)", "rgba(160,90,0,.12)"),
    "coral-soft": ("rgba(255,69,58,.16)", "rgba(201,0,27,.1)"),
    "seg-bg": ("#F5F5F7", "#1D1D1F"),
    "seg-ink": ("#000000", "#FFFFFF"),
    "btn-bg": ("#0071E3", "#0071E3"),
    "btn-ink": ("#FFFFFF", "#FFFFFF"),
    # The stage: the same in both themes (planet art and space panels keep a black ground in light mode).
    "stage": ("#000000", "#000000"),
    "stage-ink": ("#ECEFF5", "#ECEFF5"),
    "stage-dim": ("#9AA3B5", "#9AA3B5"),
    "stage-line": ("rgba(255,255,255,.08)", "rgba(255,255,255,.08)"),
    "stage-grid": ("rgba(120,140,180,.22)", "rgba(120,140,180,.22)"),
    "stage-tag-bg": ("rgba(0,0,0,.55)", "rgba(0,0,0,.55)"),
}
SCHEME = ("dark", "light")

# ---------- type, space, radius, motion: the same in both themes ----------
SANS = '"Geist","Geist Fallback",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif'
MONO = '"Geist Mono","Geist Mono Fallback",ui-monospace,"SF Mono",Menlo,monospace'
EASE = "cubic-bezier(.2,.7,.2,1)"
DURATIONS = {"d-1": 150, "d-2": 350, "d-3": 600}  # ms: hover and press; reveal and lift; view change and fills
STAGGER_MS, STAGGER_MAX_MS = 60, 1200
CONST: dict[str, str] = {
    "sans": SANS, "mono": MONO, "display": "var(--sans)",
    "ease": EASE, **{k: f"{v}ms" for k, v in DURATIONS.items()},
    **{f"s-{i}": f"{v}px" for i, v in enumerate((4, 8, 12, 16, 24, 32, 48, 64, 96), 1)},
    "r-xs": "6px", "r-s": "10px", "r-m": "14px", "r-l": "20px", "r-pill": "999px", "r": "var(--r-l)",
    "t-hero": "700 clamp(40px,6.4vw,88px)/1 var(--sans)",
    "t-h1": "700 clamp(32px,4.4vw,60px)/1.02 var(--sans)",
    "t-h2": "700 clamp(22px,2.6vw,32px)/1.1 var(--sans)",
    "t-h3": "600 17px/1.3 var(--sans)",
    "t-body": "400 15px/1.55 var(--sans)",
    "t-lede": "400 clamp(16px,1.3vw,18px)/1.5 var(--sans)",
    "t-small": "400 13px/1.45 var(--sans)",
    "t-eyebrow": "500 12px/1 var(--mono)",
    "t-data": "400 12.5px/1.4 var(--mono)",
    "shadow": "none", "gloss": "none",
    # Older names the app's and the case file frame's CSS still use.
    "paper": "var(--bg)", "rule": "var(--line-2)", "muted": "var(--ink-3)", "fit": "var(--blue)", "pass": "var(--green)",
    "flag": "var(--yellow)", "reject": "var(--red)", "sel": "var(--panel-2)", "side": "var(--bg-2)", "top": "60px",
}
TRACKING = {"hero": "-.045em", "h1": "-.04em", "h2": "-.02em", "h3": "-.01em", "body": "-.01em", "eyebrow": ".14em"}

# ---------- semantic colours ----------
# Discovery method (the Galaxy, the sky map, the README figures): (dark, light). On a stage, always the dark value.
METHOD: dict[str, tuple[str, str]] = {
    "transit": ("#64D2FF", "#006E99"), "rv": ("#FF6961", "#C9001B"), "imaging": ("#30D158", "#1F7A35"),
    "microlensing": ("#BF5AF2", "#8944AB"), "astrometry": ("#FFD60A", "#8A6100"), "timing": ("#7D7AFF", "#5856D6"),
    "other": ("#A1A1A6", "#6E6E73"),
}
# A dip's vetting outcome and a known planet, as the tags show them.
STATUS: dict[str, str] = {"passed": "var(--yellow)", "flagged": "var(--ink-2)", "rejected": "var(--red)", "known": "var(--blue)"}

# ---------- aliases: the stand-alone pages keep their own CSS names ----------
DOCKET_ALIASES = {"paper": "bg", "panel": "panel", "rule": "line-2", "muted": "ink-3", "fit": "blue", "pass": "green",
                  "flag": "yellow", "reject": "red", "sel": "bg-3", "l-det": "prb", "l-det2": "prb", "l-cl1": "sen",
                  "l-cl2": "sen", "cons": "ink"}
PLATE_ALIASES = {**DOCKET_ALIASES, "hair": "line", "pt": "ink-3", "win": "bg-3", "new": "blue", "known": "ink-3"}
REPORT_ALIASES = {"accent": "blue", "accent-2": "sen", "good": "green", "bad": "red", "warn": "yellow", "muted": "ink-3"}

# ---------- fonts: metric-matched local fallbacks (tools/font_fallback.py computes these; a test recomputes) ----------
FONT_FALLBACK = {
    "Geist Fallback": {"src": ['local("Arial")', 'local("Helvetica Neue")', 'local("Helvetica")'],
                       "size_adjust": 105.8, "ascent_override": 94.99, "descent_override": 27.88},
    "Geist Mono Fallback": {"src": ['local("Menlo")', 'local("Consolas")', 'local("DejaVu Sans Mono")'],
                            "size_adjust": 99.66, "ascent_override": 100.84, "descent_override": 29.6},
}
FONT_PRELOAD = "/assets/fonts/files/geist-gyByhwUxId8gMEwcGFWNOITd.woff2"  # Geist, Latin: the only font preloaded


def fallback_faces_css() -> str:
    """The @font-face rules of the fallbacks, as fonts/fonts.css carries them."""
    return "".join(f'@font-face{{font-family:"{face}";src:{",".join(v["src"])};size-adjust:{v["size_adjust"]}%;'
                   f'ascent-override:{v["ascent_override"]}%;descent-override:{v["descent_override"]}%;line-gap-override:0%}}\n'
                   for face, v in FONT_FALLBACK.items())


def _block(theme: int, aliases: dict | None, const: bool) -> str:
    body = "".join(f"--{k}:{v[theme]};" for k, v in TOKENS.items())
    if const and theme == 0:
        body += "".join(f"--{k}:{v};" for k, v in CONST.items())
    if aliases:
        body += "".join(f"--{k}:var(--{v});" for k, v in aliases.items() if k != v)
    return f"color-scheme:{SCHEME[theme]};{body}"


def tokens_css(scope: str = ":root", aliases: dict | None = None, *, const: bool = True) -> str:
    """The token sheet: the dark block on ``scope``, the light block under :root[data-theme="light"], and the light
    block for data-theme="system" when the device prefers light. ``aliases`` maps a page's own names to tokens."""
    def under(sel: str) -> str:
        return sel if scope == ":root" else f"{sel} {scope}"
    light = _block(1, aliases, False)
    lsel, ssel = under(':root[data-theme="light"]'), under(':root[data-theme="system"]')
    return (f"{scope}{{{_block(0, aliases, const)}}}\n"
            f"{lsel}{{{light}}}\n"
            f"@media (prefers-color-scheme: light){{{ssel}{{{light}}}}}\n")


def light_values() -> dict[str, str]:
    return {k: v[1] for k, v in TOKENS.items()}


def dark_values() -> dict[str, str]:
    return {k: v[0] for k, v in TOKENS.items()}


# Print: always the light set on white paper (the plates, the case file, the report).
PRINT_CSS = "@media print{:root{" + "".join(f"--{k}:{v[1]};" for k, v in TOKENS.items() if not k.startswith("stage")) + "--bg:#fff;color-scheme:light}}\n"

# ---------- the shared base: type classes, the stage, skeletons ----------
BASE_CSS = """
/* ---------- design.BASE_CSS: type, the stage, skeleton rows ---------- */
.t-hero{font:var(--t-hero);letter-spacing:-.045em;text-wrap:balance}
.t-h1{font:var(--t-h1);letter-spacing:-.04em}
.t-h2{font:var(--t-h2);letter-spacing:-.02em}
.t-h3{font:var(--t-h3);letter-spacing:-.01em}
.t-lede{font:var(--t-lede)}
.t-small{font:var(--t-small)}
.eyebrow,.t-eyebrow{font:var(--t-eyebrow);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.t-data{font:var(--t-data);font-variant-numeric:tabular-nums}
.stage{position:relative;overflow:hidden;background:var(--stage);border:1px solid var(--line);border-radius:var(--r-m);color:var(--stage-ink);
  --ink:var(--stage-ink);--ink-2:var(--stage-dim);--ink-3:var(--stage-dim);--line:var(--stage-line);--line-2:rgba(255,255,255,.14);--line-3:rgba(255,255,255,.24);
  --panel:#11151F;--panel-2:rgba(255,255,255,.06);--cyan:#64D2FF;--blue:#0A84FF;--amber:#FFB340;--star:#FFB340;--green:#30D158;--magenta:#BF5AF2;--yellow:#FFD60A;--red:#FF453A;--sen:#64D2FF;--prb-ink:#D0A8FF}
.stage-tag{position:absolute;top:10px;right:10px;z-index:2;display:inline-flex;align-items:center;min-height:24px;padding:3px 9px;border-radius:var(--r-xs);background:var(--stage-tag-bg);color:var(--stage-dim);font:500 11px/1.2 var(--mono);letter-spacing:.1em;text-transform:uppercase;text-decoration:none}
a.stage-tag{color:var(--stage-ink)}
a.stage-tag:hover{color:#fff;text-decoration:underline}
.stage-tag .mxlabel{border:0;padding:0;font:inherit;letter-spacing:inherit;background:none}
.stage-ctrls{position:absolute;left:10px;bottom:10px;z-index:2;display:flex;gap:6px}
.stage-ctrls .btn{background:var(--stage-tag-bg);color:var(--stage-ink);border-color:rgba(255,255,255,.18)}
.readout{font:var(--t-data);font-variant-numeric:tabular-nums;color:var(--ink-2);padding:8px 2px 0}
.rfig{margin:0;display:grid}
.rfig .rbox{position:relative;background:var(--stage);border-radius:inherit;aspect-ratio:1/1}
.rfig .rbox>img.rstill,.rfig .rbox>canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.rfig .rbox>img.rstill[hidden]{display:none}
.rfig .readout{background:var(--stage);color:var(--stage-dim);padding:8px 12px 10px;margin:0}
.rfig .readout a{color:var(--stage-ink)}
.skel{display:block;height:14px;margin:8px 0;border-radius:var(--r-xs);background:linear-gradient(90deg,var(--bg-3) 0 40%,var(--line-2) 50%,var(--bg-3) 60% 100%);background-size:300% 100%;animation:skel 1.2s linear infinite}
@keyframes skel{from{background-position:100% 0}to{background-position:0 0}}
.odo{display:inline-flex;font-variant-numeric:tabular-nums}
.odo .odd{display:inline-block;height:1em;overflow:hidden;line-height:1}
.odo .odd>span{display:block;transition:transform var(--d-3) var(--ease)}
.odo .odd>span>span{display:block;height:1em}
.xhair{position:absolute;top:0;bottom:0;width:1px;background:var(--ink-2);pointer-events:none}
.xhair[hidden]{display:none}
.xread{font:var(--t-data);color:var(--ink-2);min-height:1.4em}
"""

# Motion and view transitions (S04, V13), and the header that settles over the home page's hero (S01).
MOTION_CSS = """
/* ---------- design.MOTION_CSS: one curve, three durations; still under reduced motion ---------- */
@view-transition{navigation:auto}
::view-transition-old(root),::view-transition-new(root){animation-duration:var(--d-3);animation-timing-function:var(--ease)}
.subnav a[aria-current="page"]{view-transition-name:subnav-current}
body[data-route="overview"] .topbar:not(.settled){background:transparent;-webkit-backdrop-filter:none;backdrop-filter:none;border-color:transparent}
.topbar{transition:background-color var(--d-2) var(--ease),border-color var(--d-2) var(--ease)}
@media (prefers-reduced-motion:reduce){
  :root{--d-1:0ms;--d-2:0ms;--d-3:0ms}
  .skel{animation:none}
  ::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important}
}
"""

# Infinite decorative loops: their own periods, not the three durations. Off under reduced motion.
LOOP_ALLOW = ("twinkle", "twinkle2", "orbit", "drift", "pulse", "breathe", "sweep", "reveal", "head", "skel", "gxsweep",
              "gxspin", "t", "spin")
_TIMING = re.compile(r"(?<![-\w])(ease|ease-in|ease-out|ease-in-out)(?![-\w])")
_DECL = re.compile(r"\b(transition|animation)(-duration|-timing-function|-delay)?\s*:\s*([^;}\"]*)")


def motion_problems(css: str, where: str = "") -> list[str]:
    """The motion lint (S04): a cubic-bezier other than --ease's, a keyword easing, or a transition or animation
    duration that is not one of the three (150, 350, 600 ms, or a --d-* token). Loops in LOOP_ALLOW keep their own
    period; 0 and "none" are always allowed."""
    out = []
    for m in re.finditer(r"cubic-bezier\(([^)]*)\)", css):
        if m.group(0).replace(" ", "") != EASE:
            out.append(f"{where}: {m.group(0)} is not --ease")
    for m in _DECL.finditer(css):
        prop, value = m.group(1) + (m.group(2) or ""), m.group(3)
        if _TIMING.search(value):
            out.append(f"{where}: {prop}:{value} uses a keyword easing, not var(--ease)")
        if prop == "animation" and any(re.match(rf"\s*{re.escape(n)}\b", value) for n in LOOP_ALLOW):
            continue
        for t in re.findall(r"(?<![\w.-])(\d*\.?\d+)(ms|s)\b", value):
            ms = float(t[0]) * (1000 if t[1] == "s" else 1)
            if ms and ms not in (150, 350, 600):
                out.append(f"{where}: {prop}:{value.strip()} has {t[0]}{t[1]}")
    return out


# ---------- V10: the odometer ----------

def odometer_html(text: str, *, label: str | None = None, rate: tuple[int, int, float, float] | None = None,
                  is_rate: bool = False) -> str:
    """A counter that rolls to its value: the real number is in the HTML (a screen reader and a page without
    JavaScript read it); the digit columns are decoration. A rate must come with its interval: ``rate`` is
    (k, n, lo, hi) and prints "k of n (lo–hi%)"; ``is_rate`` without it raises ValueError."""
    if is_rate and rate is None:
        raise ValueError("a rate is never shown without its interval: pass rate=(k, n, lo, hi)")
    e = html.escape
    tail = ""
    if rate is not None:
        k, n, lo, hi = rate
        tail = f' <span class="odoci">{k:,} of {n:,} ({lo * 100:.0f}–{hi * 100:.0f}%)</span>'
    aria = f' aria-label="{e(label)}"' if label else ""
    return f'<span class="odo" data-odo="{e(text)}"{aria}>{e(text)}</span>{tail}'


# The shared page behaviour, on every page (it is appended to the site's shell script): the header that settles,
# the odometer, the crosshair (S06) and the reduced-motion flag.
MOTION_JS = r"""
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
"""

CROSSHAIR_JS = r"""
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
"""


def css_all() -> str:
    """The token sheet with the base and motion rules, for a page of the app."""
    return tokens_css() + BASE_CSS + MOTION_CSS

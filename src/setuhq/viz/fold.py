# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V05 fold: pi Men's stored light curve folded on the joint-fit period (real data, cited).

Used on: Home ("How a planet hides in the noise") and the Transits chapter of How it works. Owner: P4.

The data are SetuHQ's own: the two subjects the run ``runs/tess-pi-men-s1`` stored (TESS sector 1, SPOC 2-minute
PDCSAP flux, as the run read it), each normalised to its median and binned to 30 minutes, folded on the period and
mid-transit time of the joint fit in ``docs/results/pi_men_validation.json``. Nothing is synthetic: when the run or
the fit is not in this build the component draws nothing and its caller leaves the band out.

* :func:`html` is the server-rendered figure: two static SVG panels (unfolded and folded), which are the no-JS
  fallback and the reduced-motion still, a fold toggle (``aria-pressed``), and a caption with the numbers and source.
  The compact figure (the home page) leaves the SVG panels out for its page budget: under reduced motion its canvas
  draws the same two panels once from stories.json, and without JavaScript its caption carries the numbers.
* :data:`JS` turns the panels into one canvas on which the points slide from time to phase when the figure comes
  into view (or when the toggle is pressed). It animates only while on screen and the page is visible; under
  reduced motion it runs no loop and draws one frame, only when the toggle asks for it.
* :func:`data` is the ``fold`` section of ``stories.json``: the 30-minute bins the canvas draws.
"""

from __future__ import annotations

import html as _html
import json
import math
from functools import lru_cache
from pathlib import Path

from setuhq.viz import require_source

VALIDATION = "docs/results/pi_men_validation.json"
BIN_MIN = 30          # minutes per bin
WINDOW_H = 10.0       # the folded panel spans ±10 hours around mid-transit
LABEL = "Real data, cited"


def _root_path(p: str | Path) -> Path:
    """A repository path, from the working directory or else from the checkout this module sits in."""
    p = Path(p)
    if p.is_absolute() or p.exists():
        return p
    alt = Path(__file__).resolve().parents[3] / p
    return alt if alt.exists() else p


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


@lru_cache(maxsize=4)
def fold_data(validation: str = VALIDATION) -> dict | None:
    """The fold's data from the stored files, or None when the run or the fit is not in this build.

    Each stored subject is normalised to its median, in ppm, then binned to 30 minutes on one clock that starts at
    the first stored point. ``segs`` holds runs of consecutive bins as [first bin index, [ppm, ...]]."""
    vpath = _root_path(validation)
    if not vpath.exists():
        return None
    v = json.loads(vpath.read_text())
    fit = v.get("joint_fit") or {}
    if not fit.get("period_days") or fit.get("t0") is None:
        return None
    run = _root_path(v.get("run") or "")
    subj = sorted((run / "subjects").glob("*.json")) if v.get("run") and run.exists() else []
    if not subj:
        return None
    series = []
    for f in subj:
        s = json.loads(f.read_text())
        t, fl = s.get("time") or [], s.get("flux") or []
        good = [(a, b) for a, b in zip(t, fl) if a is not None and b is not None and math.isfinite(a) and math.isfinite(b)]
        if not good:
            continue
        med = _median([b for _, b in good])
        series.append((s.get("subject_id") or f.stem, [(a, (b / med - 1.0) * 1e6) for a, b in good]))
    if not series:
        return None
    pts = sorted(p for _, ps in series for p in ps)
    t_start, t_end = pts[0][0], pts[-1][0]
    width = BIN_MIN / 1440.0
    acc: dict[int, list[float]] = {}
    for t, ppm in pts:
        acc.setdefault(int((t - t_start) // width), []).append(ppm)
    segs: list[list] = []
    for i in sorted(acc):
        val = round(sum(acc[i]) / len(acc[i]))
        if segs and segs[-1][0] + len(segs[-1][1]) == i:
            segs[-1][1].append(val)
        else:
            segs.append([i, [val]])
    manifest = json.loads((run / "manifest.json").read_text()) if (run / "manifest.json").exists() else {}
    inputs = manifest.get("inputs") or []
    sectors = sorted({i.get("sector") for i in inputs if i.get("sector") is not None})
    star = v.get("star") or {}
    run_rel = v.get("run") or str(run)
    sha = (manifest.get("config_sha256") or "")[:12]
    source = (f"SetuHQ's stored run {run_rel} (TESS sector{'s' if len(sectors) != 1 else ''} {', '.join(map(str, sectors)) or 'not stored'}, "
              f"SPOC 2-minute PDCSAP flux, TIC {star.get('tic', 'not stored')}"
              + (f"; config sha256 {sha}…" if sha else "") + "): "
              f"{len(pts):,} stored points, each subject normalised to its median and binned to {BIN_MIN} minutes. "
              f"Period and mid-transit time from the joint fit in {validation}.")
    fd = {"p": fit["period_days"], "t0": fit["t0"]}
    near = [v for i, vals in segs for k2, v in enumerate(vals)
            if 2.0 <= abs(phase_h(t_start + (i + k2 + 0.5) * width, {**fd, "window_h": WINDOW_H})) <= 6.0]
    base = round(sum(near) / len(near), 1) if near else 0.0
    return {"source": source, "run": run_rel, "base_ppm": base, "subjects": [n for n, _ in series], "n_points": len(pts),
            "span": [round(t_start, 4), round(t_end, 4)], "t_start": round(t_start, 6), "bin_min": BIN_MIN,
            "n_bins": len(acc), "p": round(fit["period_days"], 6), "t0": round(fit["t0"], 6),
            "depth_ppm": round(fit.get("depth_ppm") or 0, 1), "t14_h": round(fit.get("t14_hours") or 0, 3),
            "window_h": WINDOW_H, "fit_file": validation, "segs": segs}


def _dots(xy: list[tuple[float, float]]) -> str:
    """A compact SVG path of dots (zero-length segments with round caps), in relative moves on whole units."""
    out, px, py = [], None, None
    for x, y in xy:
        x, y = round(x), round(y)
        if px is None:
            out.append(f"M{x} {y}h0")
        else:
            dx, dy = x - px, y - py
            out.append(f"m{dx}{'' if dy < 0 else ' '}{dy}h0")
        px, py = x, y
    return "".join(out)


def bins(fd: dict) -> list[tuple[float, int]]:
    """Every 30-minute bin as (BTJD at its centre, ppm)."""
    w = fd["bin_min"] / 1440.0
    return [(fd["t_start"] + (i0 + k + 0.5) * w, v) for i0, vals in fd["segs"] for k, v in enumerate(vals)]


def phase_h(t: float, fd: dict) -> float:
    """Hours from the nearest mid-transit on the joint-fit ephemeris."""
    p = fd["p"]
    return ((t - fd["t0"] + p / 2) % p - p / 2) * 24.0


def folded_profile(fd: dict, width_h: float = 0.5) -> list[tuple[float, float, int]]:
    """The folded curve inside the window: (phase in hours at the step's centre, mean ppm, bins averaged)."""
    acc: dict[int, list[int]] = {}
    for t, v in bins(fd):
        ph = phase_h(t, fd)
        if abs(ph) <= fd["window_h"]:
            acc.setdefault(math.floor(ph / width_h + 0.5), []).append(v)
    return [(k * width_h, sum(vs) / len(vs), len(vs)) for k, vs in sorted(acc.items())]


def text_alternative(fd: dict) -> str:
    return (f"{fd['n_points']:,} points over BTJD {fd['span'][0]:.1f}–{fd['span'][1]:.1f}, binned to {fd['bin_min']} minutes. "
            f"Folded on {fd['p']:.4f} d, a {fd['depth_ppm']:.0f} ppm dip of {fd['t14_h']:.2f} h appears. "
            f"Real data, SetuHQ's stored run.")


# ---------- the static panels (no JavaScript, and the reduced-motion still) ----------
_W, _H, _L, _R, _T, _B = 600, 246, 46, 12, 22, 40


def _yrange(fd: dict) -> tuple[float, float, int]:
    vals = sorted(v for _, vals in fd["segs"] for v in vals)
    lo = min(vals[int(0.003 * len(vals))], -1.7 * fd["depth_ppm"])
    hi = max(vals[int(0.997 * len(vals)) - 1], 0.8 * fd["depth_ppm"])
    step = 200 if hi - lo > 700 else 100
    return math.floor(lo / step) * step, math.ceil(hi / step) * step, step


def _axes(lo: float, hi: float, step: int, xlabels: list[tuple[float, str]], xtitle: str) -> str:
    Y = lambda v: _T + (_H - _T - _B) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    out = []
    v = lo
    while v <= hi + 1e-9:
        y = Y(v)
        out.append(f'<line x1="{_L}" x2="{_W - _R}" y1="{y:.1f}" y2="{y:.1f}" class="fg"/>'
                   f'<text x="{_L - 6}" y="{y + 3.5:.1f}" text-anchor="end">{"+" if v > 0 else "−" if v < 0 else ""}{abs(v):.0f}</text>')
        v += step
    for x, lab in xlabels:
        out.append(f'<text x="{x:.1f}" y="{_H - _B + 16}" text-anchor="middle">{_html.escape(lab)}</text>')
    out.append(f'<text x="4" y="{_T - 9}" text-anchor="start">ppm</text>'
               f'<text x="{_W - _R}" y="{_H - 1}" text-anchor="end">{_html.escape(xtitle)}</text>')
    return "".join(out)


def _panels(fd: dict) -> tuple[str, str]:
    lo, hi, step = _yrange(fd)
    Y = lambda v: _T + (_H - _T - _B) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    t0, t1 = fd["span"]
    X = lambda t: _L + (_W - _L - _R) * (t - t0) / (t1 - t0)  # noqa: E731
    bs = bins(fd)
    d1 = _dots([(X(t), Y(v)) for t, v in bs])
    first = math.ceil((t0 - fd["t0"]) / fd["p"])
    mids = [fd["t0"] + n * fd["p"] for n in range(first, first + 40) if t0 <= fd["t0"] + n * fd["p"] <= t1]
    ticks = "".join(f'<path d="M{X(m):.1f} {_H - _B + 1}v6" class="mk"/>' for m in mids)
    xl = [(X(d), f"{d:.0f}") for d in range(math.ceil(t0 / 5) * 5, int(t1) + 1, 5)]
    a1 = (f"Unfolded: {fd['n_points']:,} stored points of pi Men in TESS, BTJD {t0:.1f} to {t1:.1f}, binned to {fd['bin_min']} minutes. "
          f"Each of the {len(mids)} transits, {fd['depth_ppm']:.0f} ppm deep, is a handful of points among the rest; ticks under the axis mark their predicted times.")
    un = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{_html.escape(a1)}" class="foldsvg">'
          f'{_axes(lo, hi, step, xl, "BTJD (days)")}<path d="{d1}" class="pt"/>{ticks}</svg>')
    w = fd["window_h"]
    XP = lambda h: _L + (_W - _L - _R) * (h + w) / (2 * w)  # noqa: E731
    inwin = [(phase_h(t, fd), v) for t, v in bs if abs(phase_h(t, fd)) <= w]
    d2 = _dots([(XP(h), Y(v)) for h, v in sorted(inwin)])
    prof = folded_profile(fd)
    line = "M" + " L".join(f"{XP(h):.1f} {Y(v):.1f}" for h, v, _ in prof)
    dy = Y(fd.get("base_ppm", 0) - fd["depth_ppm"])
    xl2 = [(XP(h), f"{h:+.0f}" if h else "0") for h in range(-int(w), int(w) + 1, 5)]
    a2 = (f"Folded on {fd['p']:.4f} days: the same points by hours from mid-transit, {-w:.0f} to +{w:.0f} h. "
          f"A dip {fd['depth_ppm']:.0f} ppm deep and {fd['t14_h']:.2f} hours long appears at zero; the line is the mean of the points in half-hour steps.")
    fo = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{_html.escape(a2)}" class="foldsvg">'
          f'{_axes(lo, hi, step, xl2, "hours from mid-transit")}'
          f'<line x1="{_L}" x2="{_W - _R}" y1="{dy:.1f}" y2="{dy:.1f}" class="dp"/>'
          f'<text x="{_W - _R - 4}" y="{dy + 14:.1f}" text-anchor="end" class="dl">{fd["depth_ppm"]:.0f} ppm below the local level (joint fit)</text>'
          f'<path d="{d2}" class="pt"/><path d="{line}" class="mean"/></svg>')
    return un, fo


def html(data: dict, **opts) -> str:
    """The fold figure. ``data`` needs ``source`` (the caller's statement of where it comes from); the figure prints
    its own full source line from the stored files. ``where`` names the page (an id suffix); ``compact`` makes it
    shorter for the home page. Returns "" when the stored run or the fit is not in this build."""
    require_source(data)
    fd = data.get("fold") or fold_data()
    if not fd:
        return ""
    e = _html.escape
    where = "".join(c for c in str(opts.get("where") or "page") if c.isalnum() or c == "-") or "page"
    compact = bool(opts.get("compact"))
    # The compact figure (the home page, which has a tight budget) carries no static panels: its canvas draws the
    # same two panels from stories.json under reduced motion, and without JavaScript its caption states the numbers.
    un, fo = ("", "") if compact else _panels(fd)
    alt = text_alternative(fd)
    cap = f"fold-cap-{where}"
    if compact:
        # The home page's budget is tight: the figure is its label and caption; the script adds the canvas and the
        # toggle (and, under reduced motion, draws the two panels on it once).
        return (f'<figure class="stage foldfig compact"><span class="stage-tag" data-i18n="label.real">{LABEL}</span>'
                f'<figcaption>{e(_short_caption(fd))}</figcaption></figure>')
    return (f'<figure class="stage foldfig" data-fold="{e(where)}" aria-labelledby="{cap}">'
            f'<span class="stage-tag" data-i18n="label.real">{LABEL}</span>'
            f'<div class="foldpanels">'
            f'<div class="foldpanel"><p class="foldlbl"><b>Unfolded</b> · {fd["span"][1] - fd["span"][0]:.0f} days in time order</p>{un}</div>'
            f'<div class="foldpanel"><p class="foldlbl"><b>Folded</b> on the {fd["p"]:.4f}-day period</p>{fo}</div></div>'
            f'<div class="foldlive" hidden><canvas role="img" aria-label="{e(alt)}"></canvas></div>'
            f'<div class="foldctl"><button class="btn foldbtn" type="button" aria-pressed="false" hidden>Fold on the period</button>'
            f'<span class="foldstate" aria-live="polite"></span></div>'
            f'<figcaption id="{cap}" class="readout">{e(alt)} <span class="foldsrc">Source: {e(fd["source"])}</span></figcaption></figure>')


def _short_caption(fd: dict) -> str:
    """The compact figure's caption: its numbers and its source in one line."""
    return f"{fd['n_points']:,} points folded on {fd['p']:.4f} d: a {fd['depth_ppm']:.0f} ppm, {fd['t14_h']:.2f} h dip. Source: {fd['run']}."


def data(app_data: dict) -> dict:
    """The ``fold`` section of stories.json: the 30-minute bins and the ephemeris the canvas draws ({} when the
    stored run or the fit is not in this build)."""
    fd = fold_data()
    return {"fold": fd} if fd else {}


CSS = """
/* ---------- V05 the fold (setuhq.viz.fold) ---------- */
.foldfig{margin:0;display:grid;gap:10px;padding:42px 12px 12px}
.foldpanels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.foldpanel{margin:0;background:var(--stage);min-width:0}
.foldlbl{margin:0 0 4px;font:var(--t-data);color:var(--stage-dim)}
.foldlbl b{color:var(--stage-ink);font-weight:600}
.foldsvg{display:block;width:100%;height:auto;font:11px var(--mono);fill:var(--stage-dim)}
.foldsvg .fg{stroke:var(--stage-line)}
.foldsvg .pt{fill:none;stroke:rgba(236,239,245,.62);stroke-width:2.6;stroke-linecap:round}
.foldsvg .mean{fill:none;stroke:#FFB340;stroke-width:2.2;stroke-linejoin:round}
.foldsvg .dp{stroke:#FFB340;stroke-dasharray:4 4;opacity:.7}
.foldsvg .dl{fill:#FFB340}
.foldsvg .mk{stroke:#FFB340;stroke-width:2}
.foldlive{position:relative;aspect-ratio:16/7;background:var(--stage)}
.foldfig.compact .foldlive{aspect-ratio:16/6}
.foldlive[hidden]{display:none}
.foldlive canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.foldfig.live .foldpanels{display:none}
.foldctl{display:flex;flex-wrap:wrap;align-items:center;gap:10px;background:var(--stage)}
.foldctl .btn{min-height:44px;background:var(--stage-tag-bg);color:var(--stage-ink);border-color:rgba(255,255,255,.18)}
.foldctl .btn[hidden]{display:none}
.foldctl .btn[aria-pressed="true"]{background:#0A84FF;border-color:#0A84FF;color:#fff}
.foldstate{font:var(--t-data);color:var(--stage-dim)}
.foldfig .readout,.foldfig.compact figcaption{background:var(--stage);color:var(--stage-dim);padding:2px 2px 0;margin:0;font:var(--t-data)}
.foldsrc{display:block;margin-top:4px}
@media (max-width:699.98px){
  .foldpanels{grid-template-columns:minmax(0,1fr)}
  .foldsvg{font-size:17px}
  .foldsvg .pt{stroke-width:3.4}
  .foldlive,.foldfig.compact .foldlive{aspect-ratio:4/3}
  .foldfig.split .foldlive{aspect-ratio:4/5}
}
"""

JS = r"""
// ---------- V05 the fold (setuhq.viz.fold): pi Men's stored light curve, folded on the joint-fit period ----------
(function(){
  const figs = Array.from(document.querySelectorAll('figure.foldfig'));
  if (!figs.length) return;
  const RM = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
  let loading = null;
  const load = () => loading || (loading = new Promise((res, rej) => {
    const url = ((window.D || {}).viz_files || {}).stories;
    if (!url) return rej(new Error('no stories file'));
    fetch(url).then(r => r.ok ? r.json() : Promise.reject(new Error(r.status))).then(j => j && j.fold ? res(j.fold) : rej(new Error('no fold'))).catch(rej);
  }));
  const mix = (a, b, t) => a + (b - a) * t, ease = k => k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
  // Each bin: [x in time order, x in phase within the window (outside 0..1 leaves the frame), ppm].
  function prep(F){
    const w = F.bin_min / 1440, P = F.p, W = F.window_h, span = F.span[1] - F.span[0], pts = [];
    for (const [i0, vals] of F.segs) vals.forEach((v, k) => { const t = F.t_start + (i0 + k + .5) * w, ph = ((t - F.t0 + P / 2) % P + P) % P - P / 2;
      pts.push([(t - F.span[0]) / span, (ph * 24 + W) / (2 * W), v]); });
    const vals = pts.map(p => p[2]).sort((a, b) => a - b);
    let lo = Math.min(vals[Math.floor(.003 * vals.length)], -1.7 * F.depth_ppm), hi = Math.max(vals[Math.floor(.997 * vals.length) - 1], .8 * F.depth_ppm);
    const step = hi - lo > 700 ? 200 : 100; lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const acc = {};
    for (const p of pts) if (p[1] >= 0 && p[1] <= 1){ const k = Math.floor((p[1] * 2 * W - W) / .5 + .5); (acc[k] = acc[k] || []).push(p[2]); }
    const mean = Object.keys(acc).map(Number).sort((a, b) => a - b).map(k => [(k * .5 + W) / (2 * W), acc[k].reduce((a, b) => a + b, 0) / acc[k].length]);
    return {pts, lo, hi, step, mean};
  }
  figs.forEach(fig => {
    // The compact figure (the home page) arrives as its label and caption: the canvas and the toggle are added here.
    if (!fig.querySelector('.foldlive')){ const cap = fig.querySelector('figcaption');
      cap.id = cap.id || 'fold-cap-' + Math.random().toString(36).slice(2, 8);
      // Its full source line arrives with the bins (stories.json).
      load().then(d => { if (!cap.querySelector('.foldsrc')) cap.insertAdjacentHTML('beforeend', ` <span class="foldsrc">${d.source.replace(/[<&>]/g, '')}</span>`); }).catch(() => {});
      cap.insertAdjacentHTML('beforebegin', `<div class="foldlive" hidden><canvas role="img" aria-labelledby="${cap.id}"></canvas></div>`
        + '<div class="foldctl"><button class="btn foldbtn" type="button" aria-pressed="false" hidden>Fold on the period</button><span class="foldstate" aria-live="polite"></span></div>'); }
    const btn = fig.querySelector('.foldbtn'), live = fig.querySelector('.foldlive'), cv = live && live.querySelector('canvas'), state = fig.querySelector('.foldstate');
    if (!btn || !cv) return;
    let F = null, G = null, k = 0, target = 0, raf = 0, vis = false, touched = false, last = 0, font = '', split = false;
    const compact = fig.classList.contains('compact');
    // One panel of the plot inside the rectangle (ox, oy, W, H) of the canvas, at fold progress e (0 time order, 1 folded).
    function panel(c, dpr, ox, oy, W, H, e, title){
      const L = ox + 46 * dpr, R = 12 * dpr, T = oy + (title ? 44 : 30) * dpr, B = 30 * dpr, pw = ox + W - L - R;
      const Y = v => T + (oy + H - T - B) * (1 - (v - G.lo) / (G.hi - G.lo));
      c.font = `${11 * dpr}px ${font}`; c.lineWidth = dpr;
      if (title){ c.fillStyle = '#ECEFF5'; c.textAlign = 'left'; c.fillText(title, ox + 4 * dpr, oy + 14 * dpr); }
      for (let v = G.lo; v <= G.hi + 1e-9; v += G.step){ const y = Y(v); c.strokeStyle = 'rgba(255,255,255,.08)'; c.beginPath(); c.moveTo(L, y); c.lineTo(ox + W - R, y); c.stroke();
        c.fillStyle = '#9AA3B5'; c.textAlign = 'right'; c.fillText((v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v), L - 6 * dpr, y + 4 * dpr); }
      c.textAlign = 'left'; c.fillText('ppm', ox + 4 * dpr, T - 16 * dpr);
      c.textAlign = 'right'; c.fillText(e < .5 ? `BTJD ${F.span[0].toFixed(1)}–${F.span[1].toFixed(1)}, in time order` : `hours from mid-transit, folded on ${F.p.toFixed(4)} d`, ox + W - R, oy + H - 9 * dpr);
      c.fillStyle = e > .6 ? 'rgba(100,210,255,.75)' : 'rgba(236,239,245,.6)';
      const s = 2.2 * dpr;
      for (const [tx, px, v] of G.pts){ const f = mix(tx, Math.max(-.2, Math.min(1.2, px)), e); if (f < 0 || f > 1) continue; c.fillRect(L + f * pw - s / 2, Y(v) - s / 2, s, s); }
      if (e > .85){
        const a = (e - .85) / .15, yd = Y((F.base_ppm || 0) - F.depth_ppm);
        c.strokeStyle = `rgba(255,179,64,${a})`; c.lineWidth = 2.2 * dpr; c.beginPath();
        G.mean.forEach(([f, v], i) => { const x = L + f * pw, y = Y(v); if (i) c.lineTo(x, y); else c.moveTo(x, y); }); c.stroke();
        c.fillStyle = `rgba(255,179,64,${a})`; c.textAlign = 'right'; c.fillText(`${Math.round(F.depth_ppm)} ppm deep, ${F.t14_h.toFixed(2)} h (joint fit)`, ox + W - R - 4 * dpr, yd + 18 * dpr);
        c.setLineDash([4 * dpr, 4 * dpr]); c.lineWidth = dpr; c.beginPath(); c.moveTo(L, yd); c.lineTo(ox + W - R, yd); c.stroke(); c.setLineDash([]);
      }
    }
    function draw(){
      const dpr = Math.min(2, window.devicePixelRatio || 1), r = cv.getBoundingClientRect();
      const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
      if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
      const c = cv.getContext('2d'); if (!c) return;
      font = font || getComputedStyle(document.body).getPropertyValue('--mono').trim() || 'monospace';
      c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
      if (!split) return panel(c, dpr, 0, 0, w, h, ease(k), '');
      // The reduced-motion still drawn from the bins (the compact figure carries no static panels): both panels at once.
      const wide = w > 1.4 * h, a = 'Unfolded: in time order', b = `Folded on the ${F.p.toFixed(4)}-day period`;
      if (wide){ panel(c, dpr, 0, 0, w / 2, h, 0, a); panel(c, dpr, w / 2, 0, w / 2, h, 1, b); }
      else { panel(c, dpr, 0, 0, w, h / 2, 0, a); panel(c, dpr, 0, h / 2, w, h / 2, 1, b); }
    }
    function frame(now){
      raf = 0;
      const dt = Math.min(.05, Math.max(0, (now - (last || now)) / 1000)); last = now;
      k += (target - k) * Math.min(1, dt * 2.6);
      if (Math.abs(target - k) < .002) k = target;
      draw();
      if (k !== target && vis && !document.hidden) raf = requestAnimationFrame(frame);
    }
    const run = () => { if (raf || !F) return; if (RM() || !vis || document.hidden){ k = target; draw(); return; } last = 0; raf = requestAnimationFrame(frame); };
    const setTarget = (t, say) => { target = t; btn.setAttribute('aria-pressed', String(!!t)); btn.textContent = t ? 'Unfold to time' : 'Fold on the period';
      if (say && state) state.textContent = t ? `Folded on ${F.p.toFixed(4)} days: the dip appears at zero hours.` : 'In time order: each transit is a handful of points among the rest.'; run(); };
    const goLive = () => { fig.classList.add('live'); fig.classList.toggle('split', split); live.hidden = false; draw(); };
    btn.hidden = false;
    btn.addEventListener('click', () => { touched = true;
      load().then(d => { if (!F){ F = d; G = prep(F); } const next = target ? 0 : 1;
        split = false; fig.classList.remove('split');
        if (!fig.classList.contains('live')){ k = RM() ? next : 0; goLive(); }
        setTarget(next, true); }).catch(() => { btn.hidden = true; }); });
    if (!('IntersectionObserver' in window)) return;
    // Near the viewport: fetch the bins and (with motion allowed) swap the still for the canvas.
    const near = new IntersectionObserver(es => { if (!es.some(x => x.isIntersecting)) return; near.disconnect();
      // Reduced motion: the full figure keeps its static panels; the compact one draws the same two panels once.
      if (RM()){ if (compact) load().then(d => { F = F || d; G = G || prep(F); if (!fig.classList.contains('live')){ split = true; goLive(); } }).catch(() => {}); return; }
      load().then(d => { F = F || d; G = G || prep(F); if (!fig.classList.contains('live')){ k = target; goLive(); } if (vis) arm(); }).catch(() => {}); }, {rootMargin: '600px'});
    near.observe(fig);
    // On screen: fold once on its own (unless the visitor already used the toggle); off screen: stop where it is headed.
    const arm = () => { if (!touched && !RM() && F && target === 0) setTimeout(() => { if (!touched && vis && target === 0){ touched = true; setTarget(1, false); } }, 900); };
    const io = new IntersectionObserver(es => { vis = es.some(x => x.isIntersecting);
      if (!vis){ if (raf){ cancelAnimationFrame(raf); raf = 0; k = target; if (F) draw(); } return; }
      arm(); run(); }, {rootMargin: '80px', threshold: .3});
    io.observe(fig);
    document.addEventListener('visibilitychange', () => { if (document.hidden){ if (raf){ cancelAnimationFrame(raf); raf = 0; } } else run(); });
    let rz = 0; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (F && fig.classList.contains('live')) draw(); }, 150); });
  });
})();
"""

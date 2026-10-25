# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The site's pages for the stellar tools: what they measure, how far each is validated, and the CHEOPS helpers.

* ``/evidence/stellar/`` (:func:`evidence_section`): the status of each capability under protocol v3, read from
  ``docs/results/stellar_validation.json`` (flares partly validated, 5 of 8 checks pass; pulsations partly
  validated, 7 of 9; CHEOPS not validated, 2 of 5), every counted check, and two figures of real TESS data
  (``docs/results/stellar_figures.json``, written by ``scripts/stellar_figures.py``): a flaring M dwarf and a
  δ Scuti star's amplitude spectrum, each labelled "Real data, cited" with its source, beside the star drawn by
  the renderer at its TIC Teff ("Model from stored values"). Then protocol v4's capabilities
  (``docs/results/stellar_validation_v4.json``): eclipsing binaries, rotation and transients, their status, one figure
  of real TESS data each (``docs/results/stellar_figures_v4.json``: the first held-out target of each, whatever its
  result; the binary and the rotator beside their stars, the supernova with none) and every counted check. The CHEOPS part carries ESA's acknowledgement, each
  programme's credit line, the three papers, DACE's acknowledgement, the disclaimer and the licence carve-out.
* ``/docs/stellar/`` (:func:`docs_stellar_section`): the commands, what they write, and the CHEOPS terms.
* ``/docs/cheops-proposals/`` (:func:`docs_propose_section`): ``setuhq propose cheops``, a drafting aid.

The figures are static SVG on a stage: they are their own reduced-motion still, need no script, and load nothing
from another site. When a stored file is not in the build the page says so instead of drawing an empty frame.
"""

from __future__ import annotations

import html
import json
import math
from functools import lru_cache
from pathlib import Path

from setuhq import renderer

VALIDATION = "docs/results/stellar_validation.json"
CHEOPS_RESULTS = "docs/results/stellar_validation_cheops.json"
FIGURES = "docs/results/stellar_figures.json"
REPO = "https://github.com/ashfordeOU/SetuHQ"
LABEL_DATA = "Real data, cited"
LABEL_MODEL = "Model from stored values"
VALIDATION_V4 = "docs/results/stellar_validation_v4.json"
FIGURES_V4 = "docs/results/stellar_figures_v4.json"
CAPS = (("flares", "Flares"), ("pulsations", "Pulsations"), ("cheops", "CHEOPS light curves"))
CAPS_V4 = (("binaries", "Eclipsing binaries"), ("rotation", "Rotation"), ("transients", "Transients"))
# The status words, shown with their counts; never "validated" for a capability that is not.
STATUS_CLASS = {"validated": "ok", "partly validated": "part", "not validated": "no"}


def _root_path(p: str) -> Path:
    q = Path(p)
    if q.exists():
        return q
    alt = Path(__file__).resolve().parents[2] / p
    return alt if alt.exists() else q


@lru_cache(maxsize=4)
def _load(rel: str) -> dict | None:
    path = _root_path(rel)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def status() -> dict:
    """{capability: {"status", "label", "passed", "of", ...}} from the stored validations (protocol v3's and v4's), or {}."""
    return {**((_load(VALIDATION) or {}).get("capabilities") or {}), **((_load(VALIDATION_V4) or {}).get("capabilities") or {})}


def status_label(cap: str) -> str:
    """The capability's status with its count, e.g. "partly validated (5 of 8 checks pass)"."""
    s = status().get(cap)
    return s["label"] if s else "validation results not in this build"


def protocol_line() -> str:
    v = _load(VALIDATION) or {}
    p = v.get("protocol") or {}
    return (f"Protocol v{v.get('protocol_file', '').rsplit('_v', 1)[-1].split('.')[0] or '?'} ({v.get('protocol_file', '')}, "
            f"sha256 {str(v.get('protocol_sha256', ''))[:12]}…), frozen {p.get('frozen', 'not stored')}, committed in "
            f"{str(v.get('protocol_commit', ''))[:12]} before its run")


def protocol_v4_line() -> str:
    v = _load(VALIDATION_V4) or {}
    if not v:
        return "Protocol v4's results are not in this build"
    return (f"Protocol v4 ({v.get('protocol_file', '')}, sha256 {str(v.get('protocol_sha256', ''))[:12]}…), frozen "
            f"{v.get('protocol_frozen', 'not stored')}, committed on its own in {str(v.get('protocol_commit', ''))[:12]} before any v4 "
            "code or run; targets drawn by seeded rules from the catalogues, a tuning split used while the methods were written "
            "and a held-out split run once, which alone is counted")


def _status_cards(e, caps=CAPS) -> str:
    out = []
    for cap, name in caps:
        s = status().get(cap) or {}
        word = s.get("status", "not in this build")
        extra = []
        if s.get("inconclusive"):
            extra.append(f"{s['inconclusive']} comparison{'s' if s['inconclusive'] != 1 else ''} inconclusive (gated)")
        if s.get("tuning_set"):
            extra.append(f"{s['tuning_set']} tuning-set result not counted")
        out.append(f'<li class="card stcard"><h3>{e(name)}</h3><p class="stword {STATUS_CLASS.get(word, "no")}">{e(word)}</p>'
                   f'<p class="small">{s.get("passed", 0)} of {s.get("of", 0)} counted checks pass'
                   + (f"; {e('; '.join(extra))}" if extra else "") + "</p></li>")
    return f'<ul class="stcards">{"".join(out)}</ul>'


def _checks_table(e, rel=VALIDATION, version="v3", hid="h-st-checks") -> str:
    v = _load(rel) or {}
    rows = []
    for c in v.get("checks") or []:
        val = c.get("value")
        if c["capability"] == "cheops":
            shown = "in the CHEOPS file"
        elif isinstance(val, list):
            shown = "[" + ", ".join(f"{x:.2f}" for x in val) + "]"
        elif isinstance(val, float):
            shown = f"{val:.3g}"
        else:
            shown = e(str(val))
        res = c.get("result", "")
        if c.get("computed_result") and res != c.get("computed_result"):
            res = f"{res} (computed: {c['computed_result']})"
        rows.append(f'<tr><td>{e(c["capability"])}</td><td>{e(c.get("text", ""))}</td><td class="mono">{shown}</td>'
                    f'<td class="stres {e(c.get("result", "").split()[0])}">{e(res)}</td></tr>')
    return (f'<div class="tablewrap" tabindex="0" role="region" aria-labelledby="{hid}"><table class="sttable"><thead><tr>'
            f'<th scope="col">Capability</th><th scope="col">Check (protocol {version})</th><th scope="col">Value</th>'
            f'<th scope="col">Result</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _star(teff: float | None, name: str, tic: int, uid: str) -> str:
    """The star in its blackbody colour at its TIC Teff (the renderer, with a static disc as its still)."""
    from urllib.parse import quote

    if not teff:
        return f'<p class="small">TIC v8.2 lists no Teff for {html.escape(name)}, so no star disc is drawn.</p>'
    still = "data:image/svg+xml," + quote(renderer.star_svg(teff, 60, uid=uid).replace('class="stardisc" ', 'xmlns="http://www.w3.org/2000/svg" '))
    return renderer.figure("star", {"teff": round(teff), "seed": 1},
                           f"{name} drawn in its blackbody colour at its TIC v8.2 Teff of {teff:,.0f} K.",
                           f"{html.escape(name)}{'' if name.startswith('TIC') else f' (TIC {tic})'} at {teff:,.0f} K, its TIC v8.2 Teff, in its blackbody colour. The surface texture is decorative.",
                           label=LABEL_MODEL, size=160, uid=uid, still=still)


_W, _H, _L, _R, _T, _B = 640, 250, 50, 12, 26, 38


def _ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=mag * 10)
    first = math.ceil(lo / step) * step
    return [round(first + i * step, 6) for i in range(int((hi - first) / step) + 1)]


def _frame(xs, ys, X, Y, xfmt, yfmt, xtitle, ytitle) -> str:
    out = []
    for v in ys:
        out.append(f'<line x1="{_L}" x2="{_W - _R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="g"/>'
                   f'<text x="{_L - 6}" y="{Y(v) + 3.5:.1f}" text-anchor="end">{yfmt(v)}</text>')
    for v in xs:
        out.append(f'<text x="{X(v):.1f}" y="{_H - _B + 16}" text-anchor="middle">{xfmt(v)}</text>')
    out.append(f'<text x="4" y="{_T - 10}">{html.escape(ytitle)}</text>'
               f'<text x="{_W - _R}" y="{_H - 3}" text-anchor="end">{html.escape(xtitle)}</text>')
    return "".join(out)


def flare_svg(f: dict) -> tuple[str, str]:
    """The flare figure (SVG) and its text alternative."""
    step, t0 = f["step_d"], f["t0_btjd"]
    vals = f["flux"]
    span_h = len(vals) * step * 24
    good = [v for v in vals if v is not None]
    lo, hi = min(good) / 10, max(good) / 10  # ppt
    lo, hi = math.floor(min(lo, -2) / 5) * 5, math.ceil(hi / 10) * 10
    X = lambda h: _L + (_W - _L - _R) * h / span_h  # noqa: E731
    Y = lambda p: _T + (_H - _T - _B) * (1 - (p - lo) / (hi - lo))  # noqa: E731
    shades = "".join(f'<rect x="{X((x["t_start"] - t0) * 24):.1f}" y="{_T}" width="{max(2.0, X((x["t_end"] - t0) * 24) - X((x["t_start"] - t0) * 24)):.1f}" '
                     f'height="{_H - _T - _B}" class="ours"/>' for x in f["ours"])
    pub = "".join(f'<path d="M{X((p - t0) * 24):.1f} {_T - 2}v-8" class="pub"/>' for p in f["published_peaks_btjd"])
    d, pen = [], False
    for i, v in enumerate(vals):
        if v is None:
            pen = False
            continue
        d.append(f"{'L' if pen else 'M'}{X(i * step * 24):.1f} {Y(v / 10):.1f}")
        pen = True
    frame = _frame(_ticks(0, span_h, 6), _ticks(lo, hi, 4), X, Y, lambda h: f"{h:g}", lambda p: f"{p:+g}" if p else "0",
                   "hours from BTJD " + f"{t0:.2f}", "ppt")
    n_o, n_p = len(f["ours"]), len(f["published_peaks_btjd"])
    peak = max(good) / 10
    alt = (f"TESS light curve of {f['star']}, sector {f['sector']}, over {span_h:.0f} hours from BTJD {t0:.2f}: brightness in "
           f"parts per thousand about its median, with flares rising to +{peak:.0f} ppt. Shaded: the {n_o} flares SetuHQ "
           f"detects in this window; ticks above the plot: the {n_p} flare peaks Günther et al. (2020) list in it.")
    svg = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{html.escape(alt)}" class="stsvg">{frame}{shades}'
           f'<path d="{"".join(d)}" class="lc"/>{pub}</svg>')
    return svg, alt


def pulsation_svg(p: dict) -> tuple[str, str]:
    """The amplitude-spectrum figure (SVG) and its text alternative."""
    amps, f0, df = p["amp_ppm_max_per_bin"], p["fmin"], p["df"]
    hi = math.ceil(max(amps) / 200) * 200
    X = lambda fr: _L + (_W - _L - _R) * (fr - f0) / (p["fmax"] - f0)  # noqa: E731
    Y = lambda a: _T + (_H - _T - _B) * (1 - a / hi)  # noqa: E731
    d = "M" + "L".join(f"{X(f0 + (i + 0.5) * df):.1f} {Y(a):.1f}" for i, a in enumerate(amps))
    ours = "".join(f'<circle cx="{X(fr):.1f}" cy="{Y(a):.1f}" r="3.6" class="ours"/>' for fr, a, _ in p["ours"])
    pub = "".join(f'<path d="M{X(fr):.1f} {_T - 2}v-8" class="pub"/>' for fr, _ in p["published"])
    frame = _frame(_ticks(f0, p["fmax"], 6), _ticks(0, hi, 4), X, Y, lambda v: f"{v:g}", lambda v: f"{v:g}",
                   "frequency (cycles per day)", "ppm")
    top = max(p["ours"], key=lambda r: r[1])
    alt = (f"Amplitude spectrum of {p['star']} in TESS sector {p['sector']}, {p['fmin']:g} to {p['fmax']:g} cycles per day: "
           f"δ Scuti pulsations between about 20 and 60 cycles per day, the strongest at {top[0]:.2f} per day and {top[1]:,} ppm. "
           f"Dots: the {len(p['ours'])} frequencies SetuHQ's pre-whitening finds in this one sector; ticks above the plot: "
           f"the {len(p['published'])} frequencies Zieba et al. (2019) list in this range from sectors 5 to 7.")
    svg = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{html.escape(alt)}" class="stsvg">{frame}'
           f'<path d="{d}" class="lc"/>{ours}{pub}</svg>')
    return svg, alt


def _figure(kind: str, svg: str, caption: str, star: str, uid: str) -> str:
    return (f'<div class="stfigrow">{star}<figure class="stage stfig" data-fig="{kind}" aria-labelledby="cap-{uid}">'
            f'<span class="stage-tag">{LABEL_DATA}</span>{svg}<figcaption id="cap-{uid}" class="readout">{caption}</figcaption></figure></div>')


def figures_html() -> str:
    e = html.escape
    fig = _load(FIGURES)
    if not fig:
        return '<p class="note">The figures\' stored data (docs/results/stellar_figures.json) are not in this build.</p>'
    f, p = fig["flare"], fig["pulsation"]
    fsvg, _ = flare_svg(f)
    psvg, _ = pulsation_svg(p)
    s = f["sector_summary"]
    fcap = (f'<b>Flares in a TESS light curve.</b> {e(f["star"])}, an M dwarf, over 1.5 days of sector {f["sector"]}. '
            f'<span class="key ours">Shaded</span>: flares SetuHQ detects ({len(f["ours"])} here; {s["n_flares"]} in the '
            f'sector, {s["n_complex"]} complex, in {s["observing_days"]:.1f} days). <span class="key pub">Ticks</span>: '
            f'flare peaks Günther et al. (2020) list ({len(f["published_peaks_btjd"])} here; {s["published_flares"]} in the sector, '
            f'counted as components). Flare detection is {e(status_label("flares"))}: detected at the stated significance, '
            f'never confirmed. <span class="stsrc">Source: {e(f["source"])}</span>')
    pcap = (f'<b>Pulsations in a TESS light curve.</b> {e(p["star"])}, a δ Scuti star, sector {p["sector"]}. '
            f'<span class="key ours">Dots</span>: the {len(p["ours"])} strongest frequencies SetuHQ\'s pre-whitening finds in '
            f'this sector. <span class="key pub">Ticks</span>: the {len(p["published"])} frequencies Zieba et al. (2019) list '
            f'in this range. Frequency analysis is {e(status_label("pulsations"))}; a type is heuristic. '
            f'<span class="stsrc">Source: {e(p["source"])}</span>')
    return (_figure("flare", fsvg, fcap, _star((f.get("tic_values") or {}).get("teff"), f["star"], f["tic"], "st-flare-star"), "st-flare")
            + _figure("pulsation", psvg, pcap, _star((p.get("tic_values") or {}).get("teff"), p["star"], p["tic"], "st-puls-star"), "st-puls"))


def _path(points, X, Y) -> str:
    d, pen = [], False
    for x, y in points:
        if y is None:
            pen = False
            continue
        d.append(f"{'L' if pen else 'M'}{X(x):.1f} {Y(y):.1f}")
        pen = True
    return "".join(d)


def binary_svg(b: dict) -> tuple[str, str]:
    """The eclipsing-binary figure: the phase curve folded on SetuHQ's period, drawn from phase -0.5 to 0.5 so the
    primary eclipse sits in the middle (SVG), and its text alternative."""
    w = lambda p: (p + 0.5) % 1.0 - 0.5  # noqa: E731  (phase about the primary)
    pts = sorted((w(p), v) for p, v in zip(b["phase"], b["flux"]))
    good = [v for _, v in pts if v is not None]
    lo, hi = min(good), max(good)
    pad = (hi - lo) * 0.08 or 0.001
    lo, hi = lo - pad, hi + pad
    X = lambda p: _L + (_W - _L - _R) * (p + 0.5)  # noqa: E731
    Y = lambda v: _T + (_H - _T - _B) * (1 - (v - lo) / (hi - lo))  # noqa: E731
    o, c = b["ours"], b["catalogue"]
    marks = [f'<path d="M{X(0.0):.1f} {_T - 2}v-8" class="pub"/>']
    if c.get("phase_s_2g") is not None:
        marks.append(f'<path d="M{X(w(c["phase_s_2g"] - c["phase_p_2g"])):.1f} {_T - 2}v-8" class="pub"/>')
    sec = o.get("secondary")
    for x in [0.0] + ([w(sec["phase"])] if sec else []):
        marks.append(f'<path d="M{X(x):.1f} {_H - _B + 2}v6" class="ours-t"/>')
    frame = _frame(_ticks(-0.5, 0.5, 4), _ticks(lo, hi, 4), X, Y, lambda v: f"{v:g}", lambda v: f"{v:.3g}",
                   "orbital phase (primary eclipse at 0)", "relative flux")
    alt = (f"Phase curve of TIC {b['tic']}, TESS sector {b['sector']}, folded on SetuHQ's period of {o['period']:.5f} days "
           f"(Prša et al. 2022 list {c['period_d']:.5f} days), from phase -0.5 to 0.5: the primary eclipse at phase 0 is "
           f"{o['primary']['depth']:.3f} deep "
           + (f"and a secondary eclipse sits at phase {sec['phase']:.3f}" if sec else "and no secondary eclipse is found")
           + f"; morphology class {o['morphology']}. Ticks above the plot: the catalogue's eclipse phases; below it: SetuHQ's.")
    svg = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{html.escape(alt)}" class="stsvg">{frame}'
           f'<path d="{_path(pts, X, Y)}" class="lc"/>{"".join(marks)}</svg>')
    return svg, alt


def rotation_svg(r: dict) -> tuple[str, str]:
    """The rotation figure: the 2-hour light curve with the measured period marked (SVG) and its text alternative."""
    t, f = r["lc_2h"]["time"], r["lc_2h"]["flux"]
    t0 = t[0]
    ppt = [(x - t0, (v - 1) * 1e3) for x, v in zip(t, f)]
    vals = [v for _, v in ppt]
    lo, hi = math.floor(min(vals)), math.ceil(max(vals))
    span = t[-1] - t0
    X = lambda d: _L + (_W - _L - _R) * d / span  # noqa: E731
    Y = lambda v: _T + (_H - _T - _B) * (1 - (v - lo) / (hi - lo or 1))  # noqa: E731
    pts, prev = [], None
    for d, v in ppt:
        if prev is not None and d - prev > 0.5:
            pts.append((d, None))
        pts.append((d, v))
        prev = d
    o = r["ours"]
    P = o.get("period")
    ticks = ""
    if P:
        ticks = "".join(f'<path d="M{X(k * P):.1f} {_T - 2}v-8" class="ours-t"/>' for k in range(int(span / P) + 1))
    pub = "".join(f'<path d="M{X(k * r["published"]):.1f} {_H - _B + 2}v6" class="pub"/>' for k in range(int(span / r["published"]) + 1))
    frame = _frame(_ticks(0, span, 6), _ticks(lo, hi, 4), X, Y, lambda v: f"{v:g}", lambda v: f"{v:+g}" if v else "0",
                   f"days from BTJD {t0:.2f}", "ppt")
    alt = (f"TESS light curve of TIC {r['tic']}, sector {r['sector']}, in 2-hour bins, in parts per thousand about its median, "
           f"over {span:.0f} days. " + (f"SetuHQ measures a rotation period of {P:.2f} ± {o['period_err']:.2f} days (ticks above the plot, one per rotation)"
                                       if P else "SetuHQ reports no rotation period for it")
           + f"; Canto Martins et al. (2020) give {r['published']} ± {r['published_err']} days (ticks below the plot).")
    svg = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{html.escape(alt)}" class="stsvg">{frame}'
           f'<path d="{_path(pts, X, Y)}" class="lc"/>{ticks}{pub}</svg>')
    return svg, alt


def transient_svg(s: dict) -> tuple[str, str]:
    """The supernova figure: the difference light curve in 6-hour bins (SVG) and its text alternative."""
    t, f = s["lc_6h"]["time"], s["lc_6h"]["flux_e_s"]
    t0 = t[0]
    lo, hi = math.floor(min(f) / 10) * 10, math.ceil(max(f) / 10) * 10
    span = t[-1] - t0
    X = lambda d: _L + (_W - _L - _R) * d / span  # noqa: E731
    Y = lambda v: _T + (_H - _T - _B) * (1 - (v - lo) / (hi - lo or 1))  # noqa: E731
    pts, prev = [], None
    for x, v in zip(t, f):
        if prev is not None and x - prev > 1.0:
            pts.append((x - t0, None))
        pts.append((x - t0, v))
        prev = x
    p = s["published"]
    pub = ""
    for key in ("t_peak_btjd", "t_first_light_btjd"):
        if t0 <= p[key] <= t[-1]:
            pub += f'<path d="M{X(p[key] - t0):.1f} {_T - 2}v-8" class="pub"/>'
    m = s.get("matched") or {}
    ours = ""
    if m.get("t_peak") is not None:
        ours = f'<circle cx="{X(m["t_peak"] - t0):.1f}" cy="{Y(m["peak"]):.1f}" r="4" class="ours"/>'
    frame = _frame(_ticks(0, span, 6), _ticks(lo, hi, 4), X, Y, lambda v: f"{v:g}", lambda v: f"{v:g}",
                   f"days from BTJD {t0:.2f}", "e⁻/s")
    alt = (f"Difference light curve at the position of {s['name']} ({s['other']}), TESS sector {s['sector']} full-frame images, "
           f"6-hour bins, in electrons per second over {span:.0f} days. "
           + (f"SetuHQ's matched transient candidate peaks at BTJD {m['t_peak']:.2f} (the dot), class hint {m['class_hint']}"
              if m else "SetuHQ finds no transient candidate within 10 days of the published peak")
           + f"; Fausnaugh et al. (2023) give the peak at BTJD {p['t_peak_btjd']:.2f} and first light at {p['t_first_light_btjd']:.2f} "
           "(ticks above the plot, where they fall inside the sector).")
    svg = (f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{html.escape(alt)}" class="stsvg">{frame}'
           f'<path d="{_path(pts, X, Y)}" class="lc"/>{pub}{ours}</svg>')
    return svg, alt


def figures_v4_html() -> str:
    """One figure of real TESS data per protocol v4 capability: the first held-out target of each, whatever its result."""
    e = html.escape
    fig = _load(FIGURES_V4)
    if not fig:
        return '<p class="note">The protocol v4 figures\' stored data (docs/results/stellar_figures_v4.json) are not in this build.</p>'
    out = []
    b = fig.get("binary")
    if b:
        svg, _ = binary_svg(b)
        o, c = b["ours"], b["catalogue"]
        cap = (f'<b>An eclipsing binary.</b> TIC {b["tic"]}, folded on SetuHQ\'s period of {o["period"]:.5f} d '
               f'(Prša et al. 2022: {c["period_d"]:.5f} d; {"a match within 0.5%" if o.get("period_match") else "not a match within 0.5%"}). '
               f'SetuHQ {"flags it as an eclipsing-binary candidate" if o.get("eb_candidate") else "does not flag it"}; morphology class '
               f'{e(str(o.get("morphology")))} (catalogue coefficient {c["morph"]}). <span class="key pub">Ticks above</span>: the catalogue\'s eclipse phases; <span class="key ours">below</span>: SetuHQ\'s. '
               f'Eclipsing-binary analysis is {e(status_label("binaries"))}; a binary SetuHQ finds is a candidate, never new. '
               f'<span class="stsrc">Source: {e(b["source"])}</span>')
        out.append(_figure("binary", svg, cap, _star((b.get("tic_values") or {}).get("teff"), f"TIC {b['tic']}", b["tic"], "st-eb-star"), "st-eb"))
    r = fig.get("rotation")
    if r:
        svg, _ = rotation_svg(r)
        o = r["ours"]
        cap = (f'<b>Spot modulation.</b> TIC {r["tic"]}, sector {r["sector"]}. '
               + (f'<span class="key ours">Ticks above</span>: SetuHQ\'s period, {o["period"]:.2f} ± {o["period_err"]:.2f} d. ' if o.get("period")
                  else "SetuHQ reports no period for this star. ")
               + f'<span class="key pub">Ticks below</span>: Canto Martins et al. (2020), {r["published"]} ± {r["published_err"]} d. '
               f'One sector cannot measure periods beyond about 13 days. Rotation measurement is {e(status_label("rotation"))}. '
               f'<span class="stsrc">Source: {e(r["source"])}</span>')
        out.append(_figure("rotation", svg, cap, _star((r.get("tic_values") or {}).get("teff"), f"TIC {r['tic']}", r["tic"], "st-rot-star"), "st-rot"))
    s = fig.get("transient")
    if s:
        svg, _ = transient_svg(s)
        m = s.get("matched") or {}
        cap = (f'<b>A supernova in the full-frame images.</b> {e(s["name"])} ({e(s["other"])}), a type Ia supernova, sector {s["sector"]}. '
               + (f'<span class="key ours">Dot</span>: SetuHQ\'s matched transient candidate, class hint {e(m["class_hint"])}. ' if m
                  else "SetuHQ finds no candidate within 10 days of the published peak. ")
               + '<span class="key pub">Ticks</span>: Fausnaugh et al. (2023)\'s peak and first light. '
               f'Transient detection is {e(status_label("transients"))}; a transient SetuHQ finds is a candidate, never new. '
               f'{e(_search_aid())} '
               f'<span class="stsrc">Source: {e(s["source"])}</span>')
        note = ('<p class="small stnodisc">A supernova shines in a distant galaxy, not in a catalogued star, so no star disc is '
                'drawn beside it.</p>')
        out.append(_figure("transient", svg, cap, note, "st-tr"))
    return "".join(out)


def _search_aid() -> str:
    from setuhq.stellar_tools import TRANSIENT_SEARCH_AID

    return TRANSIENT_SEARCH_AID


def v4_section(e) -> str:
    """The protocol v4 part of /evidence/stellar/: status cards, the figures, every counted check, what is not validated."""
    v = _load(VALIDATION_V4) or {}
    unval = "".join(f"<li>{e(x)}</li>" for x in v.get("unvalidated") or [])
    return f"""<section aria-labelledby="h-st-v4"><h2 id="h-st-v4">Binaries, rotation and transients</h2>
        <p>Three more capabilities were tested under protocol v4, written and committed before any of their code existed. Their targets were drawn from published catalogues by seeded rules; part of each sample tuned the methods, and only the held-out rest, run once, is counted.</p>
        {_status_cards(e, CAPS_V4)}
        <p class="note">{e(_search_aid())}</p>
        <p class="small">{e(protocol_v4_line())}.</p>
        {figures_v4_html()}
      </section>
      <section class="prose" aria-labelledby="h-st-checks4"><h2 id="h-st-checks4">Every counted check, protocol v4</h2>
        <p>Misses stay on this list as misses. An eclipsing binary or a transient SetuHQ finds is a candidate, never new and never confirmed; class and morphology hints are heuristic.</p>
        {_checks_table(e, VALIDATION_V4, "v4", "h-st-checks4")}
        <h3>Not validated</h3><ul>{unval}</ul>
        <p>Full results: <a rel="noopener" href="{REPO}/blob/main/docs/results/stellar_validation_v4.md">stellar_validation_v4.md</a>. Data: public TESS light curves and full-frame-image cutouts from MAST; published values from Prša et al. (2022), Canto Martins et al. (2020), Fausnaugh et al. (2023) and Medina et al. (2020) through VizieR.</p>
      </section>"""


def cheops_block(e) -> str:
    """ESA's acknowledgement, each programme's credit line, the papers, DACE's acknowledgement, the disclaimer and
    the terms (setuhq.cheops.credit), with the programmes read from the CHEOPS results file."""
    from setuhq import cheops as ch

    c = (_load(CHEOPS_RESULTS) or {}).get("cheops_credit") or {}
    progs: dict[str, set] = {}
    for r in c.get("credits") or []:
        progs.setdefault(r.get("programme") or "", set()).add(r.get("credit") or "Credit: ESA")
    plist = "".join(f"<li><code>{e(k)}</code>: {e('; '.join(sorted(v)))}</li>" for k, v in sorted(progs.items()) if k)
    return f"""<section class="prose stcheops" aria-labelledby="h-st-cheops"><h2 id="h-st-cheops">CHEOPS: {e(status_label("cheops"))}</h2>
        <p>SetuHQ reads public CHEOPS light curves (the Data Reduction Pipeline's photometry) through DACE, the University of Geneva's public API in front of the CHEOPS Mission Archive; ESA does not designate DACE. Only visits the archive marks as public are read, with no credentials, and no raw CHEOPS file is stored in this repository or shipped in the package. The CHEOPS capability is <b>not validated</b>: its null and injection gates failed, so two comparisons are inconclusive, and the end-to-end match with pycheops' product failed. The CHEOPS-derived numbers are not on this page: they are in <a rel="noopener" href="{REPO}/blob/main/{CHEOPS_RESULTS.replace('.json', '.md')}">stellar_validation_cheops.md</a>, under ESA's terms.</p>
        <p class="note"><b>Licence.</b> {e(ch.COMMERCIAL_NOTE)}</p>
        <p class="note"><b>{e(ch.DISCLAIMER)}</b> No ESA logo, template or figure is used, and nothing here automates an ESA system.</p>
        <details><summary>ESA's acknowledgement, the programmes and their credit lines, and the papers</summary>
          <p>{e(ch.ACKNOWLEDGEMENT)}</p>
          <p>Programmes whose public visits the validation used:</p><ul>{plist or "<li>none stored in this build</li>"}</ul>
          <p>Cite: {e("; ".join(ch.CITATIONS))}.</p>
          <p>{e(ch.DACE_ACKNOWLEDGEMENT)}</p>
        </details>
      </section>"""


def evidence_section() -> str:
    """/evidence/stellar/: the stellar capabilities' validation (protocols v3 and v4), with five figures of real TESS data."""
    e = html.escape
    v = _load(VALIDATION) or {}
    unval = "".join(f"<li>{e(x)}</li>" for x in v.get("unvalidated") or [])
    return f"""<header><h1 class="lead-h" id="h-stellar" tabindex="-1">Stars, measured.</h1>
        <p>Beyond planets, SetuHQ detects stellar flares, extracts pulsation frequencies, reads public CHEOPS light curves, and finds eclipsing binaries, rotation periods and transients. Each capability was compared with published results under a protocol committed before its run, and each page and tool output says how far its validation went.</p></header>
      {_status_cards(e)}
      <p class="small">{e(protocol_line())}. Rule: validated when every counted check passes; partly validated when more than half do; otherwise not validated. Protocol v3 re-tests the targets earlier versions used, so it is a re-test after review fixes, not an independent validation.</p>
      <section aria-labelledby="h-st-figs"><h2 id="h-st-figs">What the detectors see</h2>
        {figures_html()}
      </section>
      <section class="prose" aria-labelledby="h-st-checks"><h2 id="h-st-checks">Every counted check</h2>
        <p>Each check compares SetuHQ with a published result; where they disagree, the check fails and stays on this list. A tuning-set result was used to set a threshold and is not counted; a gated comparison whose gate failed is inconclusive.</p>
        {_checks_table(e)}
        <h3>Not validated</h3><ul>{unval}</ul>
        <p>Full results: <a rel="noopener" href="{REPO}/blob/main/docs/results/stellar_validation.md">stellar_validation.md</a>. Run the tools yourself: <a href="/docs/stellar/">Flares, pulsations and CHEOPS ›</a></p>
      </section>
      {v4_section(e)}
      {cheops_block(e)}"""


def docs_stellar_section() -> str:
    """/docs/stellar/: the stellar commands and their terms."""
    e = html.escape
    from setuhq import cheops as ch

    return f"""<header><h1 class="lead-h" id="h-stellardocs" tabindex="-1">Flares, pulsations and CHEOPS.</h1>
        <p>Six commands look at the star rather than its planets. Each writes one JSON record with its result, its provenance (version, code fingerprint, every input's sha256) and its labels. A flare or a frequency is detected at a stated significance, never confirmed; a variability type is likely or a candidate.</p></header>
      <div class="docgrid">
        <section class="card"><h2>Flares</h2><p>Detection, template fits with multi-component models, energies for a 9000 K blackbody, completeness and nulls.</p><p class="stword part">{e(status_label("flares"))}</p></section>
        <section class="card"><h2>Pulsations</h2><p>Pre-whitening, combination flags, the granulation background, numax and Δν, a heuristic type.</p><p class="stword part">{e(status_label("pulsations"))}</p></section>
        <section class="card"><h2>CHEOPS light curves</h2><p>Public CHEOPS visits, detrended against roll angle, on one timeline with TESS.</p><p class="stword no">{e(status_label("cheops"))}</p></section>
        <section class="card"><h2>Eclipsing binaries</h2><p>Period, primary and secondary eclipses, the secondary's phase with an e·cosω hint, a morphology class, and a candidate flag with its reasons.</p><p class="stword {STATUS_CLASS.get(status().get("binaries", {}).get("status"), "no")}">{e(status_label("binaries"))}</p></section>
        <section class="card"><h2>Rotation</h2><p>Spot-modulation periods from a periodogram and the autocorrelation function, with uncertainties and half/double handling; up to about 13 days in one sector.</p><p class="stword {STATUS_CLASS.get(status().get("rotation", {}).get("status"), "no")}">{e(status_label("rotation"))}</p></section>
        <section class="card"><h2>Transients</h2><p>Brightenings that do not repeat: rise, decay and amplitude, a flare-like or supernova-like hint, and screens for momentum dumps, scattered light and asteroids. {e(_search_aid())}</p><p class="stword {STATUS_CLASS.get(status().get("transients", {}).get("status"), "no")}">{e(status_label("transients"))}</p></section>
      </div>
      <div class="prose">
        <h2 id="st-run">Run them</h2>
        <pre tabindex="0"><code>pip install "setuhq[tess,wavelets,cheops]"     # lightkurve (MAST), PyWavelets (denoising), DACE's client (CHEOPS)
setuhq flares "TIC 150359500" --sector 2 --out flares.json
setuhq pulsations "TIC 270577175" --sector 5 --out beta-pic.json
setuhq cheops "HR 10" --max-visits 1 --out hr10_cheops.json
setuhq binaries "TIC 79225651" --sector 1 --out eb.json
setuhq rotation "TIC 44797824" --sector 4 --out rotation.json
setuhq transients --ra 64.52583 --dec -63.61567 --time 1360.4 --out transient.json   # a TESScut cutout, 11 x 11 pixels</code></pre>
        <p>An eclipsing binary or a transient these commands find is a candidate, never new and never confirmed. <code>setuhq binaries</code> also gives advisory hints for a transit candidate's ephemeris (<code>--transit-period</code>, <code>--transit-epoch</code>); SetuHQ's planet vetting does not use them. <code>setuhq rotation</code> works on one sector at a time and reports periods beyond about 13 days as beyond its limit. <code>setuhq transients</code> reads a SPOC light curve, or with <code>--ra</code> and <code>--dec</code> a small cutout of the full-frame images from MAST's TESScut, deleted after use unless <code>--keep-cutout</code>.</p>
        <p>The same tools are available to an AI assistant over MCP: <code>find_flares</code>, <code>pulsation_spectrum</code>, <code>get_cheops_lightcurve</code>, <code>find_eclipsing_binary</code>, <code>rotation_period</code> and <code>find_transients</code>. Every answer carries its capability's validation status. The methods, their sources and every limit are in <a rel="noopener" href="{REPO}/blob/main/docs/STELLAR.md">docs/STELLAR.md</a>; the checks are on <a href="/evidence/stellar/">Evidence: stars, measured</a>.</p>
        <h2 id="st-cheops">CHEOPS data and its terms</h2>
        <ul>
          <li><b>Public data only.</b> Visits are read through DACE (dace.unige.ch), the University of Geneva's public API in front of the CHEOPS Mission Archive, in public mode with no key. ESA does not designate DACE; each record names the source that served it. Proprietary visits are skipped and never cached; no raw CHEOPS file is stored in the repository or shipped in the package.</li>
          <li><b>Credit on every output.</b> Each CHEOPS record and summary carries ESA's acknowledgement, each visit's programme ID and file key, the archive's credit line "Credit: ESA, &lt;proposal PI&gt;", and the papers to cite: {e("; ".join(ch.CITATIONS))}.</li>
          <li><b>Licence.</b> {e(ch.COMMERCIAL_NOTE)}</li>
          <li><b>{e(ch.DISCLAIMER)}</b> No ESA logo, template or copied figure is used.</li>
        </ul>
        <p>Preparing an observing proposal instead? <a href="/docs/cheops-proposals/">CHEOPS proposals ›</a></p>
      </div>"""


def docs_propose_section() -> str:
    """/docs/cheops-proposals/: the proposal preparation pack."""
    e = html.escape
    from setuhq.propose.draft import DISCLAIMER, PREP_ONLY

    return f"""<header><h1 class="lead-h" id="h-propose" tabindex="-1">Prepare a CHEOPS proposal.</h1>
        <p><code>setuhq propose cheops</code> writes a preparation pack for the CHEOPS Guest Observers Running Call: the rules checked, the target's status, planning estimates, anonymised drafts and ESA's seven steps as a checklist. You run ESA's tools and submit yourself.</p></header>
      <p class="note"><b>{e(DISCLAIMER)}</b></p>
      <div class="prose">
        <pre tabindex="0"><code>setuhq propose cheops "TOI-1987" --orbits 30
setuhq propose lint my-justification.md --author-name "Your Name"</code></pre>
        <p>{e(PREP_ONLY)}</p>
        <h2 id="pr-pack">What a pack holds</h2>
        <ul>
          <li><b>The rules</b> of the Running Call: cycles and deadlines in Paris time, programme sizes, visit limits.</li>
          <li><b>The target's status</b>: SIMBAD coordinates, a match against ESA's Reserved Target List (downloaded at run time and never committed to the repository), and prior public visits from DACE's public metadata (the University of Geneva's public API, not designated by ESA). ESA's Target Checker and Mission Archive stay definitive.</li>
          <li><b>Planning estimates</b> from published in-flight performance (Fortier et al. 2024): estimates for drafting only, to confirm with ESA's Exposure Time Calculator, Visibility Tool and Scheduling Feasibility Checker.</li>
          <li><b>Anonymised drafts</b> with generic headings, and an <b>anonymity lint</b>: an aid, not a guarantee.</li>
        </ul>
        <h2 id="pr-limits">What it never does</h2>
        <ul>
          <li>It never logs in, submits, or automates any ESA system; there is no form submission and no Proposal Handling Tool interaction.</li>
          <li>It stores no proprietary data and no PI name or id: archive answers are filtered in memory before anything reaches disk, and the names you give the lint are never written into the pack.</li>
          <li>It reproduces no ESA template, logo or figure. CHEOPS data stay under ESA's terms (CC BY-NC 3.0 IGO), outside SetuHQ's CC BY 4.0, its commercial licence and Pro.</li>
        </ul>
        <p>Every rule, source and limit: <a rel="noopener" href="{REPO}/blob/main/docs/CHEOPS-PROPOSALS.md">docs/CHEOPS-PROPOSALS.md</a>. Questions about the call go to ESA; questions about this helper go to SetuHQ's issue tracker.</p>
      </div>"""


CSS = """
/* ---------- stellar pages (setuhq.stellarpages): /evidence/stellar/, /docs/stellar/, /docs/cheops-proposals/ ---------- */
.stcards{list-style:none;margin:0 0 16px;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr))}
.stcard h3{margin:0 0 4px}
.stword{margin:0 0 4px;font:600 15px/1.3 var(--sans)}
.stword.part{color:var(--yellow)}.stword.no{color:var(--red)}.stword.ok{color:var(--green)}
.stfigrow{display:grid;gap:12px;grid-template-columns:minmax(0,180px) minmax(0,1fr);align-items:start;margin:0 0 24px}
.stfig{margin:0;padding:40px 10px 0}
.stsvg{display:block;width:100%;height:auto;font:11px var(--mono);fill:var(--stage-dim)}
.stsvg .g{stroke:var(--stage-line)}
.stsvg .lc{fill:none;stroke:rgba(236,239,245,.78);stroke-width:1.2;stroke-linejoin:round}
.stsvg .ours{fill:rgba(255,179,64,.16);stroke:#FFB340}
.stsvg .pub{stroke:#64D2FF;stroke-width:2}
.stfig .readout{background:var(--stage);color:var(--stage-dim);padding:8px 2px 10px;margin:0}
.stfig .readout b{color:var(--stage-ink)}
.stfig .key.ours{color:#FFB340}.stfig .key.pub{color:#64D2FF}
.stsrc{display:block;margin-top:4px}
.stsvg .ours-t{stroke:#FFB340;stroke-width:2}
.sttable td{vertical-align:top}.stres.pass{color:var(--green)}.stres.fail{color:var(--red)}
@media (max-width:699.98px){.stfigrow{grid-template-columns:minmax(0,1fr)}.stfigrow>.rfig{max-width:150px}.stsvg{font-size:22px}}
"""

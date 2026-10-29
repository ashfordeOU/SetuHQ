# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V12 timeline: catalogued planets per discovery year, stacked by method.

Used on: /explore/ (under the sky map), Home (compact), Methods population and history. Owner: P2 (docs/SITE.md,
"The visual system").

The bars are a static SVG written at build time from the catalogue's ``year`` and ``method`` columns (exoplanet.eu),
readable without JavaScript, with the counts by year in a ``<details>`` table. With JavaScript the chart answers on
hover and on the arrow keys (the shared crosshair, S06): the year and its counts by method. :func:`data` writes the
same counts to ``stories.json`` (``timeline``).
"""

from __future__ import annotations

import html as _html
import json

from setuhq.design import METHOD
from setuhq.viz import require_source
from setuhq.viz.skyyears import LABEL, METHODS, source_text

W, H_FULL, H_COMPACT = 1000, 300, 220
L, R_, T, B = 48, 10, 14, 26  # plot margins in SVG units


def _cat(data: dict) -> dict | None:
    return data.get("catalogue") or (data.get("app") or {}).get("catalogue")


def by_year(cat: dict) -> dict:
    """{years, methods, counts}: counts[i][k] is the number of records of method k discovered in years[i]
    (every year from the first to the last, zeros included); records without a year are left out and counted."""
    P = cat["planets"]
    ys = [y for y in P["year"] if y]
    y0, y1 = min(ys), max(ys)
    counts = [[0] * len(METHODS) for _ in range(y0, y1 + 1)]
    for y, m in zip(P["year"], P["method"]):
        if y:
            counts[y - y0][METHODS.index(m if m in METHODS else "other")] += 1
    return {"years": list(range(y0, y1 + 1)), "methods": METHODS, "counts": counts,
            "no_year": sum(1 for y in P["year"] if not y)}


def data(app_data: dict) -> dict:
    """The timeline's section of stories.json: the counts by year and method, with their source."""
    cat = (app_data or {}).get("catalogue")
    if not cat:
        return {}
    return {"timeline": {**by_year(cat), "source": source_text(cat)}}


def _nice(v: int) -> int:
    for s in (1, 2, 5, 10, 20, 50, 100, 200, 250, 500, 1000):
        if v / s <= 5:
            return s
    return 2000


def html(data: dict, **opts) -> str:
    """The stacked bars. ``data``: ``source`` (printed) and the app data as ``app`` (or ``catalogue``).
    ``compact=True`` is the shorter band of the home page and Methods."""
    require_source(data)
    cat = _cat(data)
    if not cat:
        return ""
    e = _html.escape
    t = by_year(cat)
    years, cs = t["years"], t["counts"]
    tot = [sum(c) for c in cs]
    H = H_COMPACT if opts.get("compact") else H_FULL
    step = _nice(max(tot))
    top = -(-max(tot) // step) * step
    bw = (W - L - R_) / len(years)
    sy = (H - T - B) / top
    grid, paths = [], {m: [] for m in METHODS}
    for v in range(0, top + 1, step):
        yy = H - B - v * sy
        grid.append(f'<path d="M{L} {yy:.0f}H{W - R_}"/><text x="{L - 6}" y="{yy + 4:.0f}" text-anchor="end">{v:,}</text>')
    for i, (y, c) in enumerate(zip(years, cs)):
        acc, x = 0, L + i * bw + bw * .14
        for k, v in enumerate(c):
            if not v:
                continue
            paths[METHODS[k]].append(f"M{x:.0f} {H - B - (acc + v) * sy:.0f}h{bw * .72:.0f}v{round(H - B - acc * sy) - round(H - B - (acc + v) * sy)}h{-round(bw * .72)}z")
            acc += v
    xl = "".join(f'<text x="{L + i * bw + bw / 2:.0f}" y="{H - 8}" text-anchor="middle">{y}</text>' for i, y in enumerate(years) if y % (10 if opts.get("compact") else 5) == 0)
    bars = "".join(f'<path d="{"".join(p)}" fill="{METHOD[m][0]}"/>' for m, p in paths.items() if p)
    peak = max(range(len(years)), key=lambda i: tot[i])
    aria = (f"Bar chart of the {sum(tot):,} catalogued planets by discovery year, {years[0]}–{years[-1]}, stacked by method; "
            f"the most in one year: {tot[peak]:,} in {years[peak]}.")
    # The crosshair maps the SVG's width linearly to years: its left edge and right edge in year units.
    x0, x1 = years[0] - .5 - L / bw, years[-1] + .5 + R_ / bw
    # The counts for the crosshair, compactly: one word per year from the first, each method's count joined by dots
    # (trailing zeros left out).
    def word(c: list[int]) -> str:
        while c and not c[-1]:
            c = c[:-1]
        return ".".join(map(str, c)) or "0"
    counts_attr = " ".join(word(list(c)) for c in cs)
    legend = "".join(f'<li><i style="background:{METHOD[m][0]}"></i>{e(LABEL[m])}</li>' for k, m in enumerate(METHODS) if any(c[k] for c in cs))
    head = "".join(f'<th scope="col">{e(LABEL[m])}</th>' for m in METHODS)
    body = "".join(f'<tr><th scope="row">{y}</th><td>{tot[i]:,}</td>' + "".join(f"<td>{v:,}</td>" for v in cs[i]) + "</tr>" for i, y in enumerate(years))
    noyear = f" {t['no_year']:,} records without a year are not drawn." if t["no_year"] else ""
    # The compact band (the home page) leaves the table to the full chart on /explore/.
    table = ('<p class="skysrc"><a href="/explore/#timeline">The counts by year and method, as a table ›</a></p>' if opts.get("compact") else
             f'<details class="tltable"><summary>Planets by year and method</summary><div class="tablewrap" tabindex="0" role="region" '
             f'aria-label="Planets by year and method"><table class="pltable"><thead><tr><th scope="col">Year</th><th scope="col">All</th>{head}</tr></thead>'
             f'<tbody>{body}</tbody></table></div></details>')
    uid = e(opts.get("uid") or f"tl-{opts.get('where') or 'x'}")
    return (f'<figure class="timeline{" compact" if opts.get("compact") else ""}" id="{uid}" data-viz="timeline" data-x0="{x0:.4f}" data-x1="{x1:.4f}" '
            f'data-y0="{years[0]}" data-counts="{counts_attr}">'
            f'<div class="stage tlstage"><svg class="tlsvg" viewBox="0 0 {W} {H}" role="img" aria-label="{e(aria)}">'
            f'<g class="tlgrid">{"".join(grid)}</g><g>{bars}</g><g class="tlx">{xl}</g></svg>'
            f'<span class="stage-tag" data-i18n="label.real">Real data, cited</span></div>'
            f'<p class="xread tlread" aria-live="polite">Point at a year, or focus the chart and use the arrow keys.</p>'
            f'<figcaption><ul class="skylegend" aria-label="Discovery method">{legend}</ul>'
            f'<p class="skysrc">Planets per discovery year, stacked by the method that found them.{noyear} SetuHQ did not discover these planets. '
            f'Source: {e(data["source"])}.</p></figcaption>'
            f'{table}</figure>')


CSS = """
/* ---------- viz.timeline (V12): planets per discovery year ---------- */
.timeline{margin:0;display:grid;gap:6px;min-width:0}
.tlstage{padding:10px 8px 4px}
.tlsvg{display:block;width:100%;height:auto}
.tlsvg text{fill:var(--stage-dim);font:500 11px var(--mono)}
.tlgrid path{stroke:rgba(255,255,255,.08);stroke-width:1}
.timeline.compact .tlsvg text{font-size:13px}
.tlread{margin:0}
.tltable .tablewrap{max-height:340px;overflow:auto}
.tltable table td{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
@media (max-width:699.98px){.tlsvg text{font-size:16px}.tlsvg .tlx text:nth-child(even){display:none}}
"""

JS = r"""
// ---------- viz.timeline (V12): the bars answer on hover and on the arrow keys (SetuUI.crosshair, S06) ----------
(function(){
  function wire(fig){
    if (fig._tl || !window.SetuUI || !SetuUI.crosshair) return; fig._tl = true;
    const y0 = +fig.dataset.y0, rows = fig.dataset.counts.split(' ').map((w, i) => { const c = w.split('.').map(Number); return [y0 + i, c.reduce((a, b) => a + b, 0)].concat(c); }), labels = __LABELS__, svg = fig.querySelector('.tlsvg');
    const f = n => n.toLocaleString('en-GB');
    SetuUI.crosshair(svg, {x0: +fig.dataset.x0, x1: +fig.dataset.x1, xs: rows.map(r => r[0]), readout: fig.querySelector('.tlread'),
      fmt: i => { const r = rows[i]; return `${r[0]}: ${f(r[1])} planet${r[1] === 1 ? '' : 's'}` + (r[1] ? ' · ' + r.slice(2).map((v, k) => [v, k]).filter(a => a[0]).sort((a, b) => b[0] - a[0]).map(([v, k]) => `${labels[k]} ${f(v)}`).join(' · ') : ''); }});
  }
  window.SetuTimeline = {wire: root => (root || document).querySelectorAll('[data-viz="timeline"]').forEach(wire)};
  window.SetuTimeline.wire();
})();
""".replace("__LABELS__", json.dumps([LABEL[m] for m in METHODS]))

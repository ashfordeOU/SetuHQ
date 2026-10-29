# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""/explore/tess-now/: where TESS points, sector by sector, from its published schedule.

The schedule is ``docs/results/tess_schedule.json`` (``scripts/fetch_tess_schedule.py`` saves it from the TESS Science
Office's sector pages, with the date it was saved). The page draws each sector's four camera fields on the sky map's
Mollweide projection (:func:`setuhq.story.mollweide`, as on /explore/), with the catalogue's host stars (exoplanet.eu)
and those inside the selected sector's fields highlighted. Each field is a 24° × 24° square around its camera's
published boresight, aligned with the line of the four cameras: the edges are approximate. A scrubber steps through the
saved sectors; the page opens on the sector that holds the day the schedule was saved, and the script moves it to the
sector that holds today, when the saved schedule reaches today. It is the published plan, never live telemetry.

Everything is server-rendered SVG: without JavaScript the page shows the saved day's sector and the table of all of
them; the script only switches which sector's group is shown.
"""

from __future__ import annotations

import html
import json
import math
from functools import lru_cache
from pathlib import Path

from setuhq.story import SKY_R, SQRT2, mollweide

SCHEDULE = "docs/results/tess_schedule.json"
HALF = math.radians(12.0)  # half the side of a camera's 24° field
FRAME = (-460, -235, 920, 470)
LABEL = "Pointing from the published schedule, not live telemetry"


def _root_path(p: str) -> Path:
    q = Path(p)
    if q.exists():
        return q
    alt = Path(__file__).resolve().parents[2] / p
    return alt if alt.exists() else q


@lru_cache(maxsize=2)
def load(path: str = SCHEDULE) -> dict:
    try:
        return json.loads(_root_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _vec(ra: float, dec: float) -> tuple[float, float, float]:
    a, d = math.radians(ra), math.radians(dec)
    return (math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d))


def _radec(v) -> tuple[float, float]:
    x, y, z = v
    return math.degrees(math.atan2(y, x)) % 360, math.degrees(math.asin(max(-1.0, min(1.0, z))))


def _frame(ra: float, dec: float, toward: tuple[float, float]):
    """Unit vectors (c, u, v) at a boresight: c the boresight, u along the camera line (toward ``toward``), v across."""
    c = _vec(ra, dec)
    t = _vec(*toward)
    dot = sum(a * b for a, b in zip(c, t))
    u = [b - dot * a for a, b in zip(c, t)]
    n = math.sqrt(sum(x * x for x in u)) or 1.0
    u = [x / n for x in u]
    v = [c[1] * u[2] - c[2] * u[1], c[2] * u[0] - c[0] * u[2], c[0] * u[1] - c[1] * u[0]]
    return c, u, v


def cameras(sec: dict) -> list[tuple]:
    """Each camera's (c, u, v) frame; camera 4's line direction continues away from camera 3."""
    cams = [sec[f"cam{i}"] for i in range(1, 5)]
    out = []
    for i, (ra, dec, _roll) in enumerate(cams):
        if i < 3:
            out.append(_frame(ra, dec, (cams[i + 1][0], cams[i + 1][1])))
        else:
            c, u, v = _frame(ra, dec, (cams[2][0], cams[2][1]))
            out.append((c, [-x for x in u], [-x for x in v]))
    return out


def in_field(ra: float, dec: float, cams: list[tuple]) -> bool:
    """Whether a sky position falls in one of the four camera squares (gnomonic projection about each boresight)."""
    p = _vec(ra, dec)
    lim = math.tan(HALF)
    for c, u, v in cams:
        w = sum(a * b for a, b in zip(p, c))
        if w <= 0:
            continue
        x, y = sum(a * b for a, b in zip(p, u)) / w, sum(a * b for a, b in zip(p, v)) / w
        if abs(x) <= lim and abs(y) <= lim:
            return True
    return False


def outline(cam: tuple, n: int = 8) -> str:
    """A camera square's edge, projected (a new subpath where it wraps the map's edge)."""
    c, u, v = cam
    lim = math.tan(HALF)
    pts = []
    for sx, sy, dx, dy in ((-1, -1, 1, 0), (1, -1, 0, 1), (1, 1, -1, 0), (-1, 1, 0, -1)):
        for k in range(n):
            x, y = lim * (sx + 2 * dx * k / n), lim * (sy + 2 * dy * k / n)
            w = [ci + x * ui + y * vi for ci, ui, vi in zip(c, u, v)]
            m = math.sqrt(sum(q * q for q in w))
            pts.append(mollweide(*_radec([q / m for q in w])))
    pts.append(pts[0])
    out, prev = [], None
    for x, y in pts:
        out.append(("M" if prev is None or abs(x - prev[0]) > 200 else "L") + f"{x:.0f} {y:.0f}")
        prev = (x, y)
    return "".join(out)


def host_positions(cat: dict | None) -> list[tuple[str, float, float]]:
    """Each catalogue host star once, with its RA and Dec."""
    if not cat:
        return []
    P, seen, out = cat["planets"], set(), []
    for s, ra, dec in zip(P["star"], P["ra"], P["dec"]):
        if s and s not in seen and ra is not None and dec is not None:
            seen.add(s)
            out.append((s, ra, dec))
    return out


def current_index(sectors: list[dict], day: str) -> int:
    """The sector whose dates hold ``day`` (ISO), else the last that started before it, else the first."""
    best = 0
    for i, s in enumerate(sectors):
        if s["start"] <= day:
            best = i
        if s["start"] <= day < s["end"]:
            return i
    return best


def section(data: dict) -> str:
    """The page's view. ``data``: the app data (its catalogue and its example runs' stars)."""
    e = html.escape
    sch = load()
    sectors = sch.get("sectors") or []
    head = ('<header><p class="eyebrow">Explore</p><h1 class="lead-h" id="h-tessnow" tabindex="-1">Where TESS is looking.</h1>'
            '<p>The NASA TESS satellite watches one strip of sky for about four weeks (a sector), with four cameras of 24° by 24° each. '
            'This map shows the strips from the published schedule, and the stars with known planets inside them.</p></header>')
    if not sectors:
        return head + '<p class="note">The saved TESS schedule is not in this build, so no pointing is drawn.</p>'
    from setuhq.galaxy import dots_path
    from setuhq.viz.skyyears import graticule

    cat = data.get("catalogue")
    hosts = host_positions(cat)
    examples = [(c["star"]["name"], c["star"]["ra_deg"], c["star"]["dec_deg"]) for c in (data.get("run_ctx") or {}).values()
                if c.get("star", {}).get("ra_deg") is not None]
    cur = current_index(sectors, sch["saved"])
    groups, rows, meta = [], [], []
    for i, s in enumerate(sectors):
        cams = cameras(s)
        inside = [(n, ra, dec) for n, ra, dec in hosts if in_field(ra, dec, cams)]
        ex = [n for n, ra, dec in examples if in_field(ra, dec, cams)]
        meta.append({"s": s["sector"], "a": s["start"], "b": s["end"], "n": len(inside), "x": ex})
        polys = "".join(f'<path d="{outline(c)}"/>' for c in cams)
        dots = dots_path([mollweide(ra, dec) for _, ra, dec in inside])
        groups.append(f'<g class="tnsec{" on" if i == cur else ""}" data-i="{i}"><g class="tncam">{polys}</g>'
                      f'<path class="tnin" d="{dots}"/></g>')
        camtxt = "; ".join(f"{k + 1}: {s[f'cam{k + 1}'][0]:.1f}°, {s[f'cam{k + 1}'][1]:+.1f}°" for k in range(4))
        rows.append(f'<tr><th scope="row"><a rel="noopener" href="{e(s["page"])}">{s["sector"]}</a></th><td>{s["start"]} to {s["end"]}</td>'
                    f'<td>{e(camtxt)}</td><td>{len(inside):,}</td></tr>')
    base = dots_path([mollweide(ra, dec) for _, ra, dec in hosts[::3]])
    pins = "".join(f'<g class="tnpin"><circle cx="{x:.0f}" cy="{y:.0f}" r="4" fill="none"/><text x="{x + 7:.0f}" y="{y + 4:.0f}" stroke="none">{e(n)}</text></g>'
                   for n, ra, dec in examples for x, y in [mollweide(ra, dec)])
    s0, m0 = sectors[cur], meta[cur]
    read = _readout(m0)
    aria = (f"All-sky map (Mollweide, RA increasing to the left) with the four camera fields of each TESS sector from {sectors[0]['sector']} "
            f"to {sectors[-1]['sector']}, from the schedule saved on {sch['saved']}; shown: sector {s0['sector']}, {s0['start']} to {s0['end']}, "
            f"with {m0['n']:,} catalogue stars with known planets inside its fields.")
    svg = (f'<svg class="tnsvg" viewBox="{" ".join(map(str, FRAME))}" role="img" aria-label="{e(aria)}">'
           f'<ellipse rx="{round(SKY_R * 2 * SQRT2)}" ry="{round(SKY_R * SQRT2)}" fill="rgba(255,255,255,.015)" stroke="rgba(120,140,180,.3)"/>'
           f'<path d="{graticule(True)}" stroke="rgba(120,140,180,.13)" fill="none"/>'
           f'<path class="tnbase" d="{base}"/>{"".join(groups)}{pins}</svg>')
    src = (f'{e(sch.get("source", ""))}: <a rel="noopener" href="{e(sch.get("url", ""))}">{e(sch.get("url", ""))}</a>, schedule saved on '
           f'{e(sch["saved"])}. Stars: {e((cat or {}).get("source_short") or "the catalogue")}, fetched {e(str((cat or {}).get("fetched_at") or "")[:10])}')
    scrub = (f'<div class="skytools"><label class="skyscrub tnscrub"><span>Sector</span><input type="range" id="tnrange" min="0" '
             f'max="{len(sectors) - 1}" step="1" value="{cur}" aria-valuetext="{e(read)}"></label></div>')
    return (head + f'<p class="note"><b>{LABEL}.</b> Schedule saved on {e(sch["saved"])}; sectors {sectors[0]["sector"]} to '
            f'{sectors[-1]["sector"]}. The satellite can change plans; the TESS Science Office\'s pages are the authority.</p>'
            f'<figure class="tnow" id="tnow" data-meta=\'{e(json.dumps(meta, separators=(",", ":")), quote=False)}\' data-saved="{e(sch["saved"])}">'
            f'<div class="stage skystage"><div class="skybox">{svg}</div><span class="stage-tag">Model from stored values</span></div>'
            f'{scrub}<p class="readout" id="tnread" aria-live="polite">{e(read)}</p>'
            f'<figcaption class="skysrc">Each outlined square is one camera\'s 24° × 24° field, drawn around the boresight the schedule '
            f'publishes and aligned with the line of the four cameras, so its edges are approximate. Highlighted dots: catalogued stars with '
            f'known planets inside the shown sector\'s fields; faint dots: every third catalogued host elsewhere; labelled: SetuHQ\'s example '
            f'stars. Source: {src}.</figcaption>'
            f'<details class="skytable"><summary>The saved schedule: every sector and its cameras</summary><div class="tablewrap" tabindex="0" '
            f'role="region" aria-label="The saved TESS schedule"><table class="pltable"><thead><tr><th scope="col">Sector</th><th scope="col">Dates</th>'
            f'<th scope="col">Camera boresights (RA, Dec)</th><th scope="col">Stars in field</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'</details></figure>'
            '<p class="small">SetuHQ\'s own runs use TESS data already public at MAST; this page only shows where the satellite is scheduled to look. '
            '<a href="/explore/">The sky map ›</a></p>')


def _readout(m: dict) -> str:
    ex = f" · in its fields: {', '.join(m['x'])}" if m["x"] else ""
    return f"Sector {m['s']}: {m['a']} to {m['b']} · {m['n']} catalogued stars with known planets in its fields{ex}"


CSS = """
.tnsvg{display:block;width:100%;height:auto}.tnsec{display:none}.tnsec.on{display:inline}.tncam path{fill:rgba(100,210,255,.1);stroke:#64D2FF}
@media (max-width:699.98px){.tnow .skystage{padding-bottom:60px}}
.tnbase,.tnin{stroke:rgba(170,182,204,.35);stroke-width:2;stroke-linecap:round}.tnin{stroke:#FFD60A;stroke-width:3.4}.tnpin{fill:#ECEFF5;stroke:#FFB340;font:13px var(--mono)}
"""

JS = r"""
function tnWire(){
  const f = $('#tnow'), r = $('#tnrange'); if (!f || f._w) return; f._w = 1;
  const M = JSON.parse(f.dataset.meta), day = new Date().toISOString().slice(0, 10), now = M.findIndex(m => m.a <= day && day < m.b);
  const set = i => { $$('.tnsec', f).forEach(g => g.classList.toggle('on', +g.dataset.i === i)); const m = M[i], t = `Sector ${m.s}: ${m.a} to ${m.b} · ${m.n} catalogued stars with known planets in its fields` + (m.x.length ? ' · in its fields: ' + m.x.join(', ') : ''); $('#tnread').textContent = t; r.setAttribute('aria-valuetext', t); };
  if (now >= 0){ r.value = now; set(now); }
  r.oninput = () => set(+r.value);
}
"""

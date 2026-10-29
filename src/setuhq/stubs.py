# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A small page for every catalogue planet and star that the site does not pre-render.

The site pre-renders a planet or star page for every object it names (setuhq.site). The other ~8,300 planets
and ~5,600 stars would add some 14,000 folders to the repository at every rebuild, so they are written at
deploy time instead, by ``.github/workflows/pages.yml`` just before the upload, and never committed:

    PYTHONPATH=src python3 -m setuhq.stubs site

Each page is a few kilobytes: its own title, description, canonical address and Open Graph tags, a heading and
one line of facts (readable without JavaScript), and the site's shared stylesheet and script, which add the
header and footer (assets/chrome-*.html) and draw the full planet or star page. The template is
``assets/stub-template.html``, written by the site build. ``sitemap.xml`` becomes an index of the build's own
``sitemap-pages.xml`` and one sitemap each for the planets and the stars (each well under 50,000 addresses).

Each planet page also carries its portrait in the template's ``{{PORTRAIT}}`` slot: the still of its look (an
artist's impression chosen by setuhq.looks from the measured radius or mass and the irradiation) with alt text that
gives the look and its numbers, and the ``data-render`` parameters the renderer upgrades it with. A planet with neither
radius nor mass gets a line saying no planet is drawn. Each star page carries a static disc in its blackbody colour.
Every page stays at most 4,096 bytes.

Standard library only (setuhq.looks is too), so the deploy job needs no install.
"""

from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

from setuhq import looks

SITE_URL = "https://setuhq.com"
TEMPLATE = "assets/stub-template.html"
CATALOGUE = "assets/data/catalogue.json"
SITEMAP_MAX = 50_000
STUB_MAX = 4096
PICTURES = "/docs/pictures/"
# Claret (2017) quadratic limb darkening for TESS by Teff: the twin of setuhq.methods.CLARET_TESS (a test pins it).
CLARET_TESS = [(3000, 0.1693, 0.5023), (3500, 0.1959, 0.4178), (4000, 0.3390, 0.2994), (4500, 0.5037, 0.1581),
               (5500, 0.3862, 0.2061), (6000, 0.3345, 0.2282), (6500, 0.3079, 0.2295), (7000, 0.2847, 0.2310),
               (8000, 0.2331, 0.2353), (10000, 0.1602, 0.2331)]


def _fmt(v, d: int, unit: str) -> str | None:
    try:
        return f"{float(v):,.{d}f} {unit}"
    except (TypeError, ValueError):
        return None


def is_upper_limit(x, lo, hi) -> bool:
    """exoplanet.eu stores an upper limit as lower error = value and upper error = 0 (the range from 0 to the value).
    Both errors 0 means no error was stored, which is not a limit. The page's twin is ctErr in catalogue.py."""
    try:
        x, lo, hi = float(x), float(lo), float(hi)
    except (TypeError, ValueError):
        return False
    return hi == 0 and lo > 0 and abs(lo - x) <= 1e-9 * max(abs(x), 1e-30)


def stored(P: dict, k: str, i: int, d: int, unit: str) -> str | None:
    """One stored value as words: "≤ 0.029 Jupiter masses" for an upper limit, "(theoretical estimate)" when the
    catalogue says the mass or radius is a theoretical one."""
    s = _fmt(P[k][i], d, unit)
    if s is None:
        return None
    if is_upper_limit(P[k][i], (P.get(k + "_lo") or [None] * (i + 1))[i], (P.get(k + "_hi") or [None] * (i + 1))[i]):
        s = "≤ " + s
    if (P.get(k + "_type") or [None] * (i + 1))[i] == "Theoretical":
        s += " (theoretical estimate)"
    return s


def _ld(teff: float) -> tuple[float, float]:
    rows = CLARET_TESS
    if teff <= rows[0][0]:
        return rows[0][1], rows[0][2]
    if teff >= rows[-1][0]:
        return rows[-1][1], rows[-1][2]
    for (t0, a0, b0), (t1, a1, b1) in zip(rows, rows[1:]):
        if t0 <= teff <= t1:
            f = (teff - t0) / (t1 - t0)
            return a0 + f * (a1 - a0), b0 + f * (b1 - b0)
    return rows[-1][1], rows[-1][2]


def star_svg(teff: float, r_px: float, *, uid: str, label: str | None = None) -> str:
    """The twin of setuhq.renderer.star_svg (a test pins them equal): a disc in its blackbody colour with quadratic limb
    darkening, as 11 radial-gradient stops."""
    rgb, (u1, u2) = looks.teff_rgb(teff), _ld(teff)

    def inten(r: float) -> float:
        mu = math.sqrt(max(0.0, 1 - r * r))
        return 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2
    stops = "".join(f'<stop offset="{i / 10:g}" stop-color="#{"".join(f"{round(c * inten(min(i / 10, 0.999))):02x}" for c in rgb)}"/>'
                    for i in range(11))
    d = f"{2 * r_px:g}"
    a11y = f'role="img" aria-label="{html.escape(label)}"' if label else 'aria-hidden="true"'
    return (f'<svg class="stardisc" viewBox="0 0 {d} {d}" width="{d}" height="{d}" {a11y}><defs><radialGradient id="sd-{uid}">{stops}'
            f'</radialGradient></defs><circle cx="{r_px:g}" cy="{r_px:g}" r="{r_px:g}" fill="url(#sd-{uid})"/></svg>')


def stills_base(site: str | Path) -> str:
    """The stills' folder on the site (assets/render/<hash>/, written by the build)."""
    d = Path(site) / "assets" / "render"
    sub = sorted(p.name for p in d.iterdir() if p.is_dir()) if d.is_dir() else []
    return f"/assets/render/{sub[0]}/" if sub else ""


def portrait(cat: dict, i: int, stills: str) -> str:
    """The planet's portrait figure (the renderer's element contract): its look's 512 px still, the "Artist's
    impression" tag linking to /docs/pictures/, the parameters, and a caption with the look and its numbers."""
    P = cat["planets"]
    row = {k: P[k][i] for k in ("radius", "mass", "msini", "a", "period", "srad", "smass", "steff", "teq") if k in P}
    lk = looks.look(row)
    if lk["name"] is None:
        return '<p class="plnone">No radius or mass stored, so no planet is drawn.</p>'
    e = html.escape
    size = f"{lk['rp_re']:.2f} Earth radii" if lk["rp_re"] is not None else f"radius not measured, {lk['mp_me']:,.1f} Earth masses"
    temp = f"Teq {lk['teq']:,.0f} K" if lk["teq"] is not None else "irradiation not computable"
    alt = f"Artist's impression: {lk['composition']}, {lk['band'] or 'neutral colours'}, {size}, {temp}."
    params = {"look": lk["name"], "seed": looks.seed(P["slug"][i]), "rp_re": lk["rp_re"], "teq": lk["teq"], "animate": False}
    if lk["neutral"]:
        params["neutral"] = True
    cap = f"{e(size)}, {e(temp)} ({e(cat['source_short'])}); composition not measured."
    return (f"<figure class=\"stage rfig stubfig\" data-render=\"planet\" data-params='{json.dumps(params, separators=(',', ':'))}' aria-labelledby=\"pcap\">"
            f'<div class="rbox"><img class="rstill" src="{stills}{lk["name"]}-512.webp" width="512" height="512" alt="{e(alt)}"></div>'
            f'<a class="stage-tag" href="{PICTURES}">Artist\'s impression</a><figcaption id="pcap" class="readout">{cap}</figcaption></figure>')


def _page(tpl: str, **kw: str) -> str:
    kw.setdefault("PORTRAIT", "")  # the planet's portrait figure (the template's slot; empty until a page passes one)
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def planet_page(tpl: str, cat: dict, i: int, stills: str = "") -> tuple[str, str]:
    P, e = cat["planets"], html.escape
    name, star, year = P["name"][i], P["star"][i], P["year"][i]
    method = (P.get("method_raw") or P["method"])[i] or "a method not stored"
    facts = [f"orbiting {star}" if star else "host star not stored", f"found by {method}" + (f" in {year}" if year else "")]
    facts += [x for x in (stored(P, "period", i, 3, "day orbit"), stored(P, "radius", i, 3, "Jupiter radii"),
                          stored(P, "dist", i, 1, "parsecs away")) if x]
    line = "; ".join(facts) + "."
    # The description is the name and how it was found (the numbers are in the page's facts): the page stays small.
    desc = f"{name}, a planet {'; '.join(facts[:2])}. Stored values from {cat['source_short']}; SetuHQ did not discover it."
    path = f"/planets/{P['slug'][i]}/"
    return path, _page(tpl, TITLE=e(f"{name} · Planets · SetuHQ"), DESC=e(desc), PATH=path, ROUTE="planet", H1=e(name),
                       FACTS=e(line[0].upper() + line[1:]), NOSCRIPT=e(f"{name}: the full page needs JavaScript."),
                       PORTRAIT=portrait(cat, i, stills) if stills else "")


def star_page(tpl: str, cat: dict, name: str, slug: str, idx: list[int]) -> tuple[str, str]:
    P, e = cat["planets"], html.escape
    names = ", ".join(P["name"][i] for i in idx[:4]) + (f" and {len(idx) - 4} more" if len(idx) > 4 else "")
    line = f"{len(idx)} known planet{'s' if len(idx) != 1 else ''} in {cat['source_short']}: {names}."
    desc = f"{name}, a star with {line}"
    path = f"/stars/{slug}/"
    teff = next((P["steff"][i] for i in idx if P["steff"][i]), None)
    disc = (f'<p class="stubstar">{star_svg(teff, 48, uid="s")} Drawn in its blackbody colour: {teff:,.0f} K '
            f'({e(cat["source_short"])}).</p>') if teff else ""
    return path, _page(tpl, TITLE=e(f"{name} · Stars · SetuHQ"), DESC=e(desc), PATH=path, ROUTE="star", H1=e(name),
                       FACTS=e(line), NOSCRIPT=e(f"{name}: the full page needs JavaScript."), PORTRAIT=disc)


def _urlset(paths: list[str]) -> str:
    urls = "".join(f"<url><loc>{html.escape(SITE_URL + p)}</loc></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


def write_stubs(site: str | Path) -> dict:
    """Write a page for every catalogue planet and star without one, and the sitemaps; returns counts and sizes."""
    site = Path(site)
    tpl = (site / TEMPLATE).read_text()
    cat = json.loads((site / CATALOGUE).read_text())
    P = cat["planets"]
    out = {"planets": [], "stars": []}
    sizes = []

    def write(path: str, text: str, kind: str) -> None:
        d = site / path.strip("/")
        if (d / "index.html").exists():  # a pre-rendered page wins
            return
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(text)
        out[kind].append(path)
        sizes.append(len(text.encode()))

    stills = stills_base(site)
    for i in range(len(P["name"])):
        write(*planet_page(tpl, cat, i, stills), "planets")
    by_star: dict[str, list[int]] = {}
    for i, s in enumerate(P["star"]):
        if s:
            by_star.setdefault(s, []).append(i)
    for name, slug in zip(cat["stars"]["names"], cat["stars"]["slugs"]):
        if by_star.get(name):
            write(*star_page(tpl, cat, name, slug, by_star[name]), "stars")
    # The sitemaps: the build's own pages, then the planets and the stars, in files of at most 50,000 addresses.
    files = ["sitemap-pages.xml"] + sorted(p.name for p in site.glob("sitemap-lang-*.xml"))
    for kind in ("planets", "stars"):
        every = sorted(out[kind])  # the pre-rendered ones are in sitemap-pages.xml
        for k in range(0, len(every), SITEMAP_MAX):
            name = f"sitemap-{kind}-{k // SITEMAP_MAX + 1}.xml"
            (site / name).write_text(_urlset(every[k:k + SITEMAP_MAX]))
            files.append(name)
    entries = "".join(f"<sitemap><loc>{SITE_URL}/{f}</loc></sitemap>" for f in files)
    (site / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</sitemapindex>\n')
    sizes.sort()
    return {"planets": len(out["planets"]), "stars": len(out["stars"]), "sitemaps": files,
            "bytes_median": sizes[len(sizes) // 2] if sizes else 0, "bytes_max": sizes[-1] if sizes else 0,
            "bytes_total": sum(sizes)}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    site = argv[0] if argv else "site"
    r = write_stubs(site)
    print(f"stubs: {r['planets']:,} planet and {r['stars']:,} star pages in {site} (median {r['bytes_median']:,} bytes, "
          f"largest {r['bytes_max']:,}, {r['bytes_total'] / 1e6:.1f} MB in all); sitemaps: {', '.join(r['sitemaps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

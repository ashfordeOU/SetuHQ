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

Standard library only, so the deploy job needs no install.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

SITE_URL = "https://setuhq.com"
TEMPLATE = "assets/stub-template.html"
CATALOGUE = "assets/data/catalogue.json"
SITEMAP_MAX = 50_000


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


def _page(tpl: str, **kw: str) -> str:
    kw.setdefault("PORTRAIT", "")  # the planet's portrait figure (the template's slot; empty until a page passes one)
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def planet_page(tpl: str, cat: dict, i: int) -> tuple[str, str]:
    P, e = cat["planets"], html.escape
    name, star, year = P["name"][i], P["star"][i], P["year"][i]
    method = (P.get("method_raw") or P["method"])[i] or "a method not stored"
    facts = [f"orbiting {star}" if star else "host star not stored", f"found by {method}" + (f" in {year}" if year else "")]
    facts += [x for x in (stored(P, "period", i, 3, "day orbit"), stored(P, "radius", i, 3, "Jupiter radii"),
                          stored(P, "dist", i, 1, "parsecs away")) if x]
    line = "; ".join(facts) + "."
    desc = f"{name}, a planet {line} Stored parameters from {cat['source_short']}, drawn to scale. SetuHQ did not discover it."
    path = f"/planets/{P['slug'][i]}/"
    return path, _page(tpl, TITLE=e(f"{name} · Planets · SetuHQ"), DESC=e(desc), PATH=path, ROUTE="planet", H1=e(name),
                       FACTS=e(line[0].upper() + line[1:]), NOSCRIPT=e(f"{name}: {line}"))


def star_page(tpl: str, cat: dict, name: str, slug: str, idx: list[int]) -> tuple[str, str]:
    P, e = cat["planets"], html.escape
    names = ", ".join(P["name"][i] for i in idx[:6]) + (f" and {len(idx) - 6} more" if len(idx) > 6 else "")
    line = f"{len(idx)} known planet{'s' if len(idx) != 1 else ''} in {cat['source_short']}: {names}."
    desc = f"{name}, a star with {line}"
    path = f"/stars/{slug}/"
    return path, _page(tpl, TITLE=e(f"{name} · Stars · SetuHQ"), DESC=e(desc), PATH=path, ROUTE="star", H1=e(name),
                       FACTS=e(line), NOSCRIPT=e(f"{name}: {line}"))


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

    for i in range(len(P["name"])):
        write(*planet_page(tpl, cat, i), "planets")
    by_star: dict[str, list[int]] = {}
    for i, s in enumerate(P["star"]):
        if s:
            by_star.setdefault(s, []).append(i)
    for name, slug in zip(cat["stars"]["names"], cat["stars"]["slugs"]):
        if by_star.get(name):
            write(*star_page(tpl, cat, name, slug, by_star[name]), "stars")
    # The sitemaps: the build's own pages, then the planets and the stars, in files of at most 50,000 addresses.
    files = ["sitemap-pages.xml"]
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

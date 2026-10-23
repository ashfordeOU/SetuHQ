# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The Catalogue: every record in the exoplanet dataset, with planet and star pages and a global search.

The data is ``docs/results/exoplanet_catalogue.json`` (scripts/fetch_exoplanet_catalogue.py), copied beside
the app as ``assets/data/catalogue.json`` and fetched the first time the Catalogue, a planet or star page,
or the search box needs it. The page shows only stored values: a value the source does not give reads
"not stored", never a guess. SetuHQ did not discover these planets; it catalogues them.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from setuhq.methods import system_stage
from setuhq.objects import obj_link, planet_href, slugify, star_href  # noqa: F401  (re-exported)

DEFAULT_CATALOGUE = "docs/results/exoplanet_catalogue.json"
CATALOGUE_JSON = "assets/data/catalogue.json"
# Range filters: column, label, unit, URL key.
RANGES = [("year", "Discovered", "", "year"), ("mass", "Mass or m sin i", "MJ", "mass"), ("radius", "Radius", "RJ", "radius"),
          ("period", "Period", "d", "period"), ("teq", "Equilibrium temperature", "K", "teq"), ("dist", "Distance", "pc", "dist"),
          ("steff", "Host temperature", "K", "teff")]
SORTS = ["name", "star", "year", "method", "mass", "radius", "period", "teq", "dist", "steff"]
METHOD_CHAPTER = {"transit": "transit", "rv": "rv", "imaging": "imaging", "microlensing": "microlensing",
                  "astrometry": "astrometry", "timing": "history"}


def tic_names(cat: dict | None, tics: list, story_star: dict | None = None) -> dict:
    """TIC → catalogue star name, for the TICs the page shows: the run's own target (named from SIMBAD in
    targets.json) and any TIC listed in a star's stored alternate names. Unknown TICs stay bare numbers."""
    out = {}
    if story_star and story_star.get("target", "").startswith("TIC ") and story_star.get("name"):
        out[story_star["target"][4:]] = story_star["name"]
    if cat:
        want = {str(t) for t in tics}
        P = cat["planets"]
        for s, alt in zip(P["star"], P["salt"]):
            for t in re.findall(r"TIC[ -]?(\d+)", alt or ""):
                if t in want and s:
                    out.setdefault(t, s)
    return out


def load_catalogue(path: str | Path | None = DEFAULT_CATALOGUE) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def mentions(notable: list | None, chapters: list, chapter_planets: dict, story: dict | None) -> dict:
    """Where SetuHQ itself shows each planet or star: name → [[label, href], ...], for the back-links on
    the canonical pages. Galaxy tour stops, Methods chapters, and the run's own star and planet."""
    out: dict[str, list] = {}
    add = lambda n, lab, href: out.setdefault(n, []).append([lab, href]) if n else None
    if story and story.get("planet"):
        add(story["planet"], "SetuHQ's own Transit case", "#/transit")
    if story and (story.get("star") or {}).get("name"):
        add(story["star"]["name"], "SetuHQ's Transit case", "#/transit")
        add(story["star"]["name"], "The run's sky map", "#/sky")
    for k, nt in enumerate(notable or []):
        add(nt["name"], f"Galaxy tour, stop {k + 1}", f"#/galaxy?tour={k + 1}")
    titles = dict(chapters)
    for cid, names in chapter_planets.items():
        for n in names:
            add(n, f"Methods: {titles[cid]}", f"#/methods?ch={cid}")
    return out


def catalogue_meta(cat: dict | None, methods: list[str] | None = None, method_label: dict | None = None,
                   refs: dict | None = None, seen: dict | None = None) -> dict | None:
    """The small part the shell needs before the data file arrives: counts, the source line and the filters.
    ``refs`` maps a planet name to [URL, label] of its discovery paper, from SetuHQ's own checked list
    (docs/results/notable_planets.json): the catalogue dataset itself stores no DOI."""
    from setuhq.renderer import stills_hash

    if cat is None:
        return None
    P = cat["planets"]
    m = methods or sorted(set(P["method"]))
    per = {k: sum(1 for v in P["method"] if v == k) for k in m}
    years = [y for y in P["year"] if y is not None]
    return {"counts": cat["counts"], "source_name": cat["source_name"], "source_short": cat["source_short"],
            "url": cat["url"], "fetched_at": cat["fetched_at"], "definition": cat["definition"], "note": cat.get("note", ""),
            "methods": m, "method_label": method_label or {k: k for k in m}, "per_method": per,
            "years": [min(years), max(years)], "ranges": [[k, lab, unit, key] for k, lab, unit, key in RANGES],
            "sorts": SORTS, "method_chapter": METHOD_CHAPTER, "units": cat["units"], "refs": refs or {}, "mentions": seen or {},
            "stills": f"/assets/render/{stills_hash()}/"}


def catalogue_filter(cat: dict, v: dict) -> list[int]:
    """The reference filter the page's JavaScript must match: text in planet or star name (or alternate names),
    chosen methods, numeric ranges (a missing value never passes a range), multi-planet systems, has distance."""
    P = cat["planets"]
    n = len(P["name"])
    q = (v.get("q") or "").strip().lower()
    methods = set(v.get("methods") or [])
    star_n: dict[str, int] = {}
    for s in P["star"]:
        if s:
            star_n[s] = star_n.get(s, 0) + 1
    out = []
    for i in range(n):
        if q:
            hay = " ".join(x for x in (P["name"][i], P["star"][i], P["alt"][i], P["salt"][i]) if x).lower()
            if q not in hay:
                continue
        if methods and P["method"][i] not in methods:
            continue
        ok = True
        for col, _, _, key in RANGES:
            lo, hi = (v.get(key) or (None, None))
            if lo is None and hi is None:
                continue
            x = P[col][i]
            if col == "mass" and x is None:
                x = P["msini"][i]
            if x is None or (lo is not None and x < lo) or (hi is not None and x > hi):
                ok = False
                break
        if not ok:
            continue
        if v.get("multi") and not (P["star"][i] and star_n[P["star"][i]] >= 2):
            continue
        if v.get("hasdist") and P["dist"][i] is None:
            continue
        out.append(i)
    return out


def catalogue_section(meta: dict | None, eyebrow: str) -> str:
    e = html.escape
    if meta is None:
        return (f'<header>{eyebrow}<h1 class="lead-h" id="h-catalogue" tabindex="-1">Every known exoplanet.</h1>'
                "<p>The catalogue (docs/results/exoplanet_catalogue.json) is not in this build.</p></header>")
    c = meta["counts"]
    chips = "".join(f'<button class="chip" type="button" data-cm="{m}" aria-pressed="false">{e(meta["method_label"].get(m, m))} '
                    f'<span class="mono" data-cmn="{m}">{meta["per_method"][m]:,}</span></button>' for m in meta["methods"])
    ranges = "".join(f'<fieldset class="ctrange"><legend>{e(lab)}{(" (" + e(unit) + ")") if unit else ""}</legend>'
                     f'<input type="number" inputmode="decimal" step="any" data-rk="{key}" data-end="lo" aria-label="{e(lab)} from" placeholder="from">'
                     f'<input type="number" inputmode="decimal" step="any" data-rk="{key}" data-end="hi" aria-label="{e(lab)} to" placeholder="to"></fieldset>'
                     for _, lab, unit, key in RANGES)
    note = f" {e(meta['note'])}." if meta.get("note") else ""
    from setuhq.viz import tempstrip

    # V09 as the host-temperature filter: two handles over the blackbody strip (the number boxes below stay too).
    strip = tempstrip.html({"source": f"Star colour: a Planck spectrum through the CIE 1931 colour-matching functions; host Teff: {meta['source_short']}",
                            "markers": [], "sun": True, "title": "Host star temperature, 2,500 K to 10,000 K: drag either handle to filter"}, filter=True)
    strip = f'<div class="ctstrip"><p class="ctstriplab">Host temperature</p>{strip}</div>' if strip else ""
    return f"""<header class="headrow">
        <div>{eyebrow}<h1 class="lead-h" id="h-catalogue" tabindex="-1">Every known exoplanet.<br><span class="grey">{c['rows']:,} records, searchable.</span></h1>
        <p>All {c['rows']:,} planets in {e(meta['source_short'])}, including the {c['rows'] - c['with_distance']:,} with no stored distance that the Galaxy map cannot place. SetuHQ did not discover these planets; it catalogues them.</p></div>
      </header>
      <p class="note"><b>Data: {e(meta['source_name'])}, fetched {e(meta['fetched_at'][:10])}.</b> <a href="{e(meta['url'])}" rel="noopener">{e(meta['url'])}</a>.{note} {e(meta['definition'])} A value the source does not give reads "not stored".</p>
      <section class="card ctfilters" aria-label="Search and filters">
        <label class="ctsearch"><span class="sr">Search planets and stars</span><input type="search" id="ctq" placeholder="Search {c['rows']:,} planets and {c['stars']:,} stars" autocomplete="off"></label>
        <div class="chips" id="ctmethods" role="group" aria-label="Detection method">{chips}</div>
        <details class="ctmore"><summary>Ranges and more</summary>
          {strip}<div class="ctranges">{ranges}</div>
          <div class="ctchecks"><button class="chip" type="button" id="ctmulti" aria-pressed="false">Multi-planet systems</button><button class="chip" type="button" id="cthasdist" aria-pressed="false">Has a distance</button></div>
        </details>
        <div class="ctbar"><p class="mono" id="ctcount" role="status" aria-live="polite">Loading the catalogue…</p>
          <button class="btn" type="button" id="ctreset">Clear filters</button>
          <button class="btn" type="button" id="ctcsv">Download CSV of this view</button></div>
      </section>
      <div class="cttable" id="cttable" role="table" aria-label="Catalogue of planets" aria-rowcount="0" aria-colcount="10">
        <div class="cthead" role="row">{''.join(f'<button class="cth{" num" if k not in ("name", "star", "method") else ""}" type="button" role="columnheader" data-sort="{k}" aria-sort="none">{e(lab)}</button>' for k, lab in (("name", "Planet"), ("star", "Host"), ("year", "Year"), ("method", "Method"), ("mass", "Mass (MJ)"), ("radius", "Radius (RJ)"), ("period", "Period (d)"), ("teq", "Teq (K)"), ("dist", "Distance (pc)"), ("steff", "Host Teff (K)")))}</div>
        <div class="ctscroll" id="ctscroll" tabindex="0" role="rowgroup" aria-label="Rows; scroll to see more"><div class="ctspacer" id="ctspacer"></div></div>
      </div>
      <p class="ctempty" id="ctempty" role="status" hidden>No planets match these filters. <a href="#/catalogue">Clear filters</a></p>
      <p class="small">Mass shows the true mass when stored, otherwise m sin i (marked "sin i"), a minimum. Units as the source stores them: Jupiter masses and radii, days, kelvin, parsecs.</p>"""


def planet_page(eyebrow_html: str) -> str:
    return f"""<header>{eyebrow_html}<h1 class="lead-h" id="h-planet" tabindex="-1">Planet</h1><p id="plsub"></p></header>
      <p class="note" id="plnote" role="status" hidden></p>
      <div class="plextra" id="plextra"></div>
      <div class="plgrid">
        {system_stage("plsys", "The planet's system, drawn from stored values.")}
        <section class="card plparams" aria-labelledby="h-plparams"><h2 id="h-plparams">Stored parameters</h2><div id="plparams"></div></section>
      </div>
      <div class="plmore">
        <section class="card" aria-labelledby="h-plhost"><h2 id="h-plhost">Its star and other planets</h2><div id="plhost"></div></section>
        <section class="card" aria-labelledby="h-plwhere"><h2 id="h-plwhere">Where it is</h2><div id="plwhere"></div></section>
      </div>
      <section class="card" aria-labelledby="h-plref"><h2 id="h-plref">Discovery and references</h2><div id="plref"></div></section>"""


def star_page(eyebrow_html: str) -> str:
    return f"""<header>{eyebrow_html}<h1 class="lead-h" id="h-star" tabindex="-1">Star</h1><p id="stsub"></p></header>
      <p class="note" id="stnote" role="status" hidden></p>
      <div class="plextra" id="stextra"></div>
      <div class="plgrid">
        <div class="stsysw"><label class="stpick"><span>System view of</span><select id="stpick"></select></label>
        {system_stage("stsys", "The star and one of its planets, drawn from stored values.")}</div>
        <section class="card plparams" aria-labelledby="h-stparams"><h2 id="h-stparams">Stored parameters</h2><div id="stparams"></div></section>
      </div>
      <div class="plmore">
        <section class="card" aria-labelledby="h-stplanets"><h2 id="h-stplanets">Its planets</h2><div id="stplanets"></div></section>
        <section class="card" aria-labelledby="h-stwhere"><h2 id="h-stwhere">Where it is</h2><div id="stwhere"></div></section>
      </div>"""


# ---------- planet and star pages: the portrait, the star, the line-up and the orbits (pre-rendered pages) ----------

def _src(cat: dict) -> str:
    return f"{cat.get('source_short') or 'exoplanet.eu'}, fetched {str(cat.get('fetched_at') or '')[:10]}"


SPIN_BTN = '<div class="stage-ctrls"><button class="btn" type="button" data-spin aria-pressed="false" hidden>Spin</button></div>'


def portrait(cat: dict, i: int) -> str:
    """V02: the planet's artist's impression from its measured radius (or mass) and irradiation (setuhq.looks), with
    its look, the reasons and the source in the caption; "" when neither radius nor mass is stored."""
    from setuhq import looks, renderer

    P = cat["planets"]
    lk = looks.look(looks.row(cat, i))
    if lk["name"] is None:
        return ""
    name = P["name"][i]
    size = f"{lk['rp_re']:.2f} Earth radii" if lk["rp_re"] is not None else f"radius not measured ({lk['mp_me']:,.1f} Earth masses)"
    temp = f"{lk['teq']:,.0f} K" if lk["teq"] is not None else "irradiation not computable"
    comp = {"envelope": "an envelope planet", "rock": "a rocky planet", "neptune": "a Neptune-like planet", "giant": "a gas giant",
            "ambiguous": "a planet of unknown make-up"}[lk["composition"]]
    alt = f"Artist's impression of {name}: {comp}" + (f" in the {lk['band']} band" if lk["band"] else "") + f", {size}, {temp}."
    params = {"look": lk["name"], "seed": looks.seed(P["slug"][i]), "rp_re": lk["rp_re"], "teq": lk["teq"], "animate": False}
    if lk["neutral"]:
        params["neutral"] = True
    cap = (html.escape(looks.caption(looks.row(cat, i), lk)) + f" Source: {html.escape(_src(cat))}. "
           f'<a href="{renderer.PICTURES}">How the pictures are drawn ›</a>')
    fig = renderer.figure("planet", params, alt, cap, uid=f"pl-{P['slug'][i]}", priority=True)
    return fig.replace('</div><a class="stage-tag"', SPIN_BTN + '</div><a class="stage-tag"', 1)


def star_figure(name: str, teff: float | None, srad: float | None, source: str, uid: str) -> str:
    """The host star in its blackbody colour from its stored Teff (setuhq.looks.teff_rgb, Claret 2017 limb darkening);
    the still is the same disc as an SVG, so it shows without JavaScript."""
    from urllib.parse import quote

    from setuhq import renderer

    if not teff:
        return ""
    svg = renderer.star_svg(teff, 64, uid=uid).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    rad = f", radius {srad:.2f} R☉" if srad else ""
    alt = f"{name} drawn in its blackbody colour, {teff:,.0f} K{rad}."
    cap = (f"{html.escape(name)} in its blackbody colour: {teff:,.0f} K{rad} ({html.escape(source)}). Brightness normalised; "
           "the surface texture is decorative.")
    return renderer.figure("star", {"teff": teff, "rstar_rsun": srad, "animate": False}, alt, cap, label="Model from stored values",
                           size=256, uid=uid, still="data:image/svg+xml," + quote(svg))


def planet_extras(cat: dict, i: int) -> str:
    """The planet page's opening: the portrait beside its host star (or the star alone, saying why there is no planet),
    then the planet in the line-up beside Earth, Neptune and Jupiter when its radius is stored (V07)."""
    from setuhq.viz import lineup

    P = cat["planets"]
    star = P["star"][i] or ""
    pic = portrait(cat, i)
    st = star_figure(star or "The host star", P["steff"][i], P["srad"][i], _src(cat), f"st-{P['slug'][i]}")
    none = "" if pic else '<p class="plnone">No radius or mass stored, so no planet is drawn.</p>'
    hero = f'<div class="plhero{" solo" if not pic else ""}" id="plhero" data-slug="{html.escape(P["slug"][i])}">{pic}{st}{none}</div>'
    en = lineup.entry(cat, i)
    lu = lineup.html({"source": _src(cat), "planets": [en], "focus": en["name"], "title": f"{P['name'][i]} to scale"}) if en else ""
    lu = f'<section class="pllineup" aria-label="{html.escape(P["name"][i])} in the line-up">{lu}</section>' if lu else ""
    return hero + lu


def star_extras(cat: dict, name: str, idx: list[int]) -> str:
    """The star page's opening: the star in its blackbody colour, its place on the temperature strip (V09, when that
    module draws), and the orbits of its planets when two or more have a period (V08)."""
    from setuhq.looks import row
    from setuhq.objects import slugify as _slug
    from setuhq.viz import orbits, tempstrip

    P = cat["planets"]
    i = idx[0]
    teff = P["steff"][i]
    fig = star_figure(name, teff, P["srad"][i], _src(cat), f"st-{_slug(name)}")
    strip = tempstrip.html({"source": f"Teff: {_src(cat)}; star colour: a Planck spectrum through the CIE 1931 colour-matching functions",
                            "markers": [{"name": name, "teff": teff}]}) if teff else ""
    rows = [{"name": P["name"][j], "slug": P["slug"][j], **row(cat, j)} for j in idx]
    orb = orbits.html({"source": _src(cat), "star": name, "teff": teff, "planets": rows, "uid": f"orb-{_slug(name)}"})
    if not (fig or strip or orb):
        return ""
    return f'<div class="sthero" id="sthero" data-star="{html.escape(name)}">{fig}{strip}{orb}</div>'


def still_list(cat: dict, idx: list[int]) -> str:
    """The star's planets, each with its look's 160 px still (an artist's impression) or none without radius or mass."""
    from setuhq import looks, renderer

    P = cat["planets"]
    out = []
    for j in idx:
        lk = looks.look(looks.row(cat, j))["name"]
        img = (f'<img class="plthumb" src="{renderer.still_href(lk, 160)}" width="40" height="40" loading="lazy" alt="">' if lk
               else '<span class="plthumb none" aria-hidden="true"></span>')
        out.append(f'<li><a href="/planets/{P["slug"][j]}/">{img}<span>{html.escape(P["name"][j])}</span></a></li>')
    return f'<ul class="pllist plthumbs">{"".join(out)}</ul><p class="small">Pictures: artist\'s impressions from the measured radius and irradiation. <a href="/docs/pictures/">How the pictures are drawn ›</a></p>'


# The top bar's search: an icon button that opens the search overlay (also on / and Ctrl or Cmd K).
SEARCH_BUTTON = ('<button class="iconbtn searchbtn" type="button" id="gsearchbtn" aria-label="Search planets, stars and pages (press /)" '
                 'aria-haspopup="dialog" title="Search (/)"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" '
                 'fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12.8 12.8L17 17" stroke="currentColor" stroke-width="1.7" '
                 'stroke-linecap="round"/></svg></button>')
SEARCH_DIALOG = """<dialog class="gsearch" id="gsearch" aria-labelledby="gsearchlbl">
  <label class="gsfield"><span class="sr" id="gsearchlbl">Search planets, stars and pages</span>
    <input type="search" id="gsq" role="combobox" aria-expanded="true" aria-controls="gsresults" aria-autocomplete="list" placeholder="Search planets, stars, pages" autocomplete="off"></label>
  <ul class="gsresults" id="gsresults" role="listbox" aria-label="Results"></ul>
  <p class="gshint">↑ ↓ to move · Enter to open · Esc to close</p>
</dialog>"""


CATALOGUE_CSS = r"""
/* ---------- catalogue ---------- */
#route-catalogue,#route-planet,#route-star{grid-template-columns:minmax(0,1fr)}
#route-catalogue>*,#route-planet>*,#route-star>*{min-width:0}
.ctfilters{display:grid;gap:12px}
.ctsearch input{width:100%;min-height:48px;padding:0 16px;border-radius:14px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 16px var(--sans)}
.ctmore summary{display:flex;align-items:center;gap:8px;min-height:44px;cursor:pointer;font-weight:600;list-style:none}
.ctmore summary::-webkit-details-marker{display:none}
.ctmore summary::before{content:"›";display:inline-block;transition:transform var(--d-1) var(--ease);color:var(--ink-3)}
.ctmore[open] summary::before{transform:rotate(90deg)}
.ctranges{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin-top:6px}
.ctrange{border:1px solid var(--line);border-radius:12px;padding:6px 10px 10px;display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:0;min-width:0}
.ctrange legend{font-size:12px;color:var(--ink-3);padding:0 4px}
.ctrange input{min-width:0;min-height:44px;padding:0 10px;border-radius:10px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 14px var(--mono)}
.ctchecks{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.ctbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.ctbar p{margin:0 auto 0 0;font-size:13px}
.ctbar .btn,.ctfilters .chip{min-height:44px}
.ctfilters .chip .mono{color:var(--ink-3);margin-left:6px;font-size:12px}
.cttable{border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--glass-2)}
.cthead,.ctrow{display:grid;grid-template-columns:minmax(150px,1.6fr) minmax(120px,1.3fr) 64px minmax(110px,1fr) repeat(6,minmax(84px,.8fr));align-items:center}
.cthead{border-bottom:1px solid var(--line-2);background:var(--panel)}
.cth{all:unset;box-sizing:border-box;min-height:44px;padding:0 10px;font:600 12px var(--sans);color:var(--ink-2);cursor:pointer;display:flex;align-items:center}
.cth.num{justify-content:flex-end}
.cth:focus-visible{outline:2px solid var(--blue);outline-offset:-2px}
.cth[aria-sort="ascending"]::after{content:" ▲";font-size:11px}
.cth[aria-sort="descending"]::after{content:" ▼";font-size:11px}
.ctscroll{position:relative;height:min(64vh,640px);overflow:auto;contain:strict}
.ctspacer{position:relative;width:100%}
.ctrow{position:absolute;left:0;right:0;height:44px;border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:13px}
.ctrow:hover,.ctrow:focus-visible{background:var(--panel-2)}
.ctrow>span{padding:0 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.ctrow .num{font-family:var(--mono);font-variant-numeric:tabular-nums;text-align:right}
.ctrow .na{color:var(--ink-3)}
.ctrow b{font-weight:600}
.ctrow>span>i[style],.ctcard>span>i[style]{font-style:normal;display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.ctscroll[hidden],.ctempty[hidden]{display:none}
.ctempty{margin:0;padding:24px;border:1px solid var(--line);border-radius:var(--r);background:var(--glass-2);display:flex;flex-wrap:wrap;align-items:center;gap:12px}
.ctempty a{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border-radius:999px;border:1px solid var(--line-2);text-decoration:none}
/* A phone card: the same ten cells, in flex rows (cheaper to lay out than a grid). Containment on each card
   was measured too: at 4× CPU throttle it doubled style time, so only the scroller is contained. */
.ctcard{position:absolute;left:0;right:0;height:128px;padding:8px 14px;border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none;display:flex;flex-wrap:wrap;align-content:center;column-gap:12px;row-gap:1px;overflow:hidden}
.ctcard>span{flex:0 0 calc(50% - 6px);font-size:12px;line-height:17px;color:var(--ink-2);white-space:nowrap;overflow:hidden}
.ctcard>span[role="rowheader"],.ctcard>span:nth-child(2){flex-basis:100%}
.ctcard>span[role="rowheader"]{font-size:15px;line-height:21px;color:var(--ink)}
/* A value that is not stored stays in the table for screen readers, but takes no room on the card. */
.ctcard>span.na{flex:0 0 0;width:0;height:0;overflow:hidden;margin-left:-12px}


.ctcard .na{color:var(--ink-3)}
.plgrid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:16px;align-items:start}
.plmore{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:16px;align-items:stretch}
.plmore>.card{min-width:0}
.plgrid[hidden],.plmore[hidden],#route-planet .card[hidden]{display:none}
.plparams{display:grid;gap:8px}
.plparams h2,.plmore h2,#route-planet .card>h2{margin:0 0 6px;font-size:17px}
.pltable{width:100%;border-collapse:collapse;font-size:13px}
.pltable th,.pltable td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.pltable td.v{font-family:var(--mono);font-variant-numeric:tabular-nums}
.pltable .na{color:var(--ink-3)}
.pllist{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.pllist a{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:44px;padding:0 10px;border-radius:10px;text-decoration:none;color:var(--ink)}
.pllist a:hover{background:var(--panel-2)}
.pllist a[aria-current="page"]{background:var(--panel-2);font-weight:600}
.pllist .mono{font-size:12px;color:var(--ink-3)}
.pllinks{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.pllab{flex-basis:100%;font-size:12px;color:var(--ink-3)}
.pllinks a{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border-radius:999px;border:1px solid var(--line-2);text-decoration:none}
.plsky{width:100%;max-width:420px;height:auto;display:block}
.plsky text{fill:var(--ink-3);font:500 11px var(--mono)}
.stsysw{display:grid;gap:10px;min-width:0}
.stpick{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px;color:var(--ink-2)}
.stpick select{min-height:44px;padding:0 12px;border-radius:12px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 14px var(--sans);max-width:100%}
.gsearch{width:min(640px,calc(100vw - 24px));margin-top:10vh;padding:12px;border-radius:20px;border:1px solid var(--line-2);background:var(--bg-2);color:var(--ink)}
.gsearch::backdrop{background:rgba(0,0,0,.55);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.gsfield input{width:100%;min-height:52px;padding:0 16px;border-radius:14px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 17px var(--sans)}
.gsresults{list-style:none;margin:10px 0 0;padding:0;max-height:min(60vh,520px);overflow:auto;display:grid;gap:2px}
.gsresults a{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:48px;padding:0 12px;border-radius:12px;text-decoration:none;color:var(--ink)}
.gsresults [aria-selected="true"] a{background:var(--seg-bg);color:var(--seg-ink)}
.gsresults .kind{font:500 11px var(--mono);color:var(--ink-3);text-transform:uppercase}
.gsresults [aria-selected="true"] .kind{color:inherit;opacity:.7}
.gshint{margin:8px 4px 0;font-size:12px;color:var(--ink-3)}
.ctrow{content-visibility:auto;contain-intrinsic-size:auto 44px}
.ctcard{content-visibility:auto;contain-intrinsic-size:auto 128px}
.ctdot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:baseline;box-shadow:0 0 0 1px var(--line-2)}
.ctdot.none{background:transparent}
.ctcls{display:inline-block;margin-left:6px;padding:0 6px;border-radius:var(--r-pill);border:1px solid var(--line-2);font:500 11px/1.4 var(--mono);color:var(--ink-3);vertical-align:1px}
.ctrow .ctcls{display:none}
@media (min-width:1100px){.ctrow .ctcls{display:inline-block}}
.ctstrip{display:grid;gap:6px;margin:6px 0 10px}
.ctstriplab{margin:0;font-size:12px;color:var(--ink-3)}
.gsresults .ctdot{width:16px;height:16px;vertical-align:-3px}
.plextra{display:grid;gap:16px}
.stubfig{max-width:420px}
.stubstar{display:flex;align-items:center;gap:14px;margin:0;color:var(--ink-2);font-size:14px}
.stubstar svg{flex:none}
.plextra:empty{display:none}
.plhero{display:grid;grid-template-columns:minmax(0,520px) minmax(0,300px);gap:16px;align-items:start}
.plhero.solo{grid-template-columns:minmax(0,300px) minmax(0,1fr)}
.plnone{margin:0;align-self:center;color:var(--ink-2)}
.plhero .readout,.sthero .readout{font-size:12px;line-height:1.45}
.sthero{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:16px;align-items:start}
.sthero>.orbits,.sthero>.tstrip{grid-column:1/-1}
.plthumbs a{justify-content:flex-start}
.plthumbs .mono{margin-left:auto}
.plthumb{width:40px;height:40px;border-radius:50%;flex:none;background:#000}
.plthumb.none{display:inline-block;border:1px dashed var(--line-2);background:none}
@media (prefers-reduced-motion: reduce){.ctmore summary::before{transition:none}}
@media (max-width:699.98px){.plhero,.plhero.solo,.sthero{grid-template-columns:minmax(0,1fr)}.plextra a.stage-tag{min-height:44px;min-width:44px}}
@media (max-width:699.98px){
  /* Phone: the column headers stay (one per cell) as a row of sort buttons that scrolls sideways. */
  .cthead{display:flex;gap:6px;padding:6px;overflow-x:auto;overscroll-behavior-x:contain}
  .cth{flex:none;padding:0 12px;border:1px solid var(--line-2);border-radius:999px}
  .ctscroll{height:70vh}
  .plgrid,.plmore{grid-template-columns:minmax(0,1fr)}
}
"""


CATALOGUE_JS = r"""
// ---------- catalogue: every record, planet and star pages, global search ----------
const CTM = D.catalogue_meta || null;
// URL state: q, method (list), year/mass/radius/period/teq/dist/teff ranges as lo~hi, multi, hasdist, sort, dir.
function decodeCatView(p){
  const v = {q: (p.get('q') || '').slice(0, 120), methods: [], sort: 'name', dir: 'asc', multi: p.get('multi') === '1', hasdist: p.get('hasdist') === '1'};
  const ms = (p.get('method') || '').split(',');
  if (CTM) v.methods = CTM.methods.filter(m => ms.includes(m));
  for (const [, , , key] of (CTM ? CTM.ranges : [])){
    const raw = p.get(key); v[key] = [null, null];
    if (raw){ const [a, b] = raw.split('~'); const lo = a === '' || a === undefined ? null : Number(a), hi = b === '' || b === undefined ? null : Number(b);
      v[key] = [Number.isFinite(lo) ? lo : null, Number.isFinite(hi) ? hi : null]; }
  }
  if (CTM && CTM.sorts.includes(p.get('sort'))) v.sort = p.get('sort');
  if (p.get('dir') === 'desc') v.dir = 'desc';
  return v;
}
function encodeCatView(v){
  const out = [];
  if (v.q) out.push('q=' + encodeURIComponent(v.q));
  if (v.methods.length) out.push('method=' + CTM.methods.filter(m => v.methods.includes(m)).join(','));
  for (const [, , , key] of CTM.ranges){ const r = v[key] || [null, null]; if (r[0] !== null || r[1] !== null) out.push(`${key}=${r[0] === null ? '' : r[0]}~${r[1] === null ? '' : r[1]}`); }
  if (v.multi) out.push('multi=1');
  if (v.hasdist) out.push('hasdist=1');
  if (v.sort !== 'name') out.push('sort=' + v.sort);
  if (v.dir === 'desc') out.push('dir=desc');
  return out.join('&');
}
// The filter (tests compare it with catalogue.catalogue_filter in Python): a missing value never passes a range.
function ctFilter(P, v, starN, skipMethods){
  const n = P.name.length, q = (v.q || '').trim().toLowerCase(), ms = new Set(skipMethods ? [] : v.methods), out = [];
  const ranges = CTM.ranges.map(([col, , , key]) => [col, v[key] || [null, null]]).filter(([, r]) => r[0] !== null || r[1] !== null);
  for (let i = 0; i < n; i++){
    if (q){ const hay = [P.name[i], P.star[i], P.alt[i], P.salt[i]].filter(Boolean).join(' ').toLowerCase(); if (!hay.includes(q)) continue; }
    if (ms.size && !ms.has(P.method[i])) continue;
    let ok = true;
    for (const [col, [lo, hi]] of ranges){ let x = P[col][i]; if (col === 'mass' && x === null) x = P.msini[i];
      if (x === null || x === undefined || (lo !== null && x < lo) || (hi !== null && x > hi)){ ok = false; break; } }
    if (!ok) continue;
    if (v.multi && !(P.star[i] && starN[P.star[i]] >= 2)) continue;
    if (v.hasdist && P.dist[i] === null) continue;
    out.push(i);
  }
  return out;
}
function ctSort(P, idx, key, dir){
  const col = key === 'mass' ? P.mass.map((m, i) => m === null ? P.msini[i] : m) : P[key], s = dir === 'desc' ? -1 : 1;
  return idx.slice().sort((a, b) => { const x = col[a], y = col[b];
    if (x === null || x === undefined) return (y === null || y === undefined) ? a - b : 1;   // missing values last, either way
    if (y === null || y === undefined) return -1;
    if (typeof x === 'string') return s * x.localeCompare(y, 'en', {sensitivity: 'base'}) || a - b;
    return s * (x - y) || a - b; });
}

const ct = {rangeT: {}, P: null, loading: null, view: null, idx: [], starN: {}, bySlug: {}, starBySlug: {}, byStar: {}, rendered: false, rowH: 44};
function ctLoad(){
  if (!ct.loading) ct.loading = fetch('/assets/data/catalogue.json').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(C => {
    ct.C = C; ct.P = C.planets;
    const P = ct.P;
    P.name.forEach((nm, i) => { ct.bySlug[P.slug[i]] = i; const s = P.star[i]; if (s){ ct.starN[s] = (ct.starN[s] || 0) + 1; (ct.byStar[s] = ct.byStar[s] || []).push(i); } });
    C.stars.names.forEach((s, k) => { ct.starBySlug[C.stars.slugs[k]] = s; });
    return C;
  });
  return ct.loading;
}
const ctFmt = (x, d) => x === null || x === undefined ? null : (Math.abs(x) >= 1000 ? Math.round(x).toLocaleString('en-GB') : Number(x.toPrecision(d || 4)).toString());
const ctPlanetHref = i => planetHref(ct.P.name[i]);
const ctStarHref = s => starHref(s);

// ---------- the table: only the rows in view are in the page ----------
function renderCatalogue(){
  if (!CTM) return;
  ctLoad().then(() => { ct.rendered = true; ctBind(); ctApply(); }).catch(() => { $('#ctcount').textContent = 'The catalogue file (assets/data/catalogue.json) could not be loaded here.'; });
}
const CT_CARD_H = 128;
function ctPhone(){ return window.matchMedia('(max-width: 699.98px)').matches; }
function ctApply(){
  if (!ct.P || !ct.view) return;
  const v = ct.view;
  ct.idx = ctSort(ct.P, ctFilter(ct.P, v, ct.starN), v.sort, v.dir);
  // Faceted counts: each method's count under every other filter.
  const base = ctFilter(ct.P, v, ct.starN, true), cnt = {};
  for (const i of base) cnt[ct.P.method[i]] = (cnt[ct.P.method[i]] || 0) + 1;
  $$('#ctmethods [data-cmn]').forEach(s => { s.textContent = (cnt[s.dataset.cmn] || 0).toLocaleString('en-GB'); });
  $('#ctcount').textContent = `Showing ${ct.idx.length.toLocaleString('en-GB')} of ${ct.P.name.length.toLocaleString('en-GB')} planets`;
  $('#cttable').setAttribute('aria-rowcount', String(ct.idx.length));
  ctControls();
  ct.rowH = ctPhone() ? CT_CARD_H : 44;
  $('#ctspacer').style.height = ct.idx.length * ct.rowH + 'px';
  $('#ctscroll').scrollTop = 0;
  // No match: say so, with a way out, instead of an empty box.
  $('#ctempty').hidden = ct.idx.length > 0; $('#ctscroll').hidden = !ct.idx.length;
  ctRows(true);
}
// The host's colour (its stored Teff as a blackbody, SetuRender.teffRGB; cached by 50 K) and the size class (CLASS_RULE).
const ctDotC = {};
function ctDot(teff){
  if (!(teff > 0) || !window.SetuRender) return '<i class="ctdot none" aria-hidden="true"></i>';
  const k = Math.round(teff / 50) * 50, c = ctDotC[k] || (ctDotC[k] = SetuRender.teffRGB(k).join(','));
  return `<i class="ctdot" style="background:rgb(${c})" aria-hidden="true"></i>`;
}
const CT_CLASSES = ['Earth-size', 'Super-Earth', 'Sub-Neptune', 'Neptune-like', 'Gas giant'];
function ctCls(i){ const P = ct.P, c = typeof mxClassOf === 'function' ? mxClassOf(P.radius[i], P.mass[i] !== null ? P.mass[i] : P.msini[i]) : null; return c === null || c === undefined ? '' : CT_CLASSES[c]; }
// One row: the planet's name is the row header, then one cell per column header (10 in all, at every width).
// On a phone the same cells wrap into a card, each with its label shown.
const CT_COLS = [['star', 'Host', ''], ['year', 'Year', ''], ['method', 'Method', ''], ['mass', 'Mass', 'MJ'], ['radius', 'Radius', 'RJ'],
  ['period', 'Period', 'd'], ['teq', 'Teq', 'K'], ['dist', 'Distance', 'pc'], ['steff', 'Host Teff', 'K']];
function ctRowHTML(r){
  const P = ct.P, i = ct.idx[r], h = ct.rowH, phone = h > 50, col = m => GXM && GXM.method_colour ? GXM.method_colour[m] : '#8E8E93';
  const cell = (k, lab, unit) => {
    let v, cls = 'num';
    if (k === 'star'){ v = P.star[i] ? ctDot(P.steff[i]) + esc(P.star[i]) : null; cls = ''; }
    else if (k === 'method'){ v = `<i style="background:${col(P.method[i])}"></i>${esc(CTM.method_label[P.method[i]] || P.method[i])}`; cls = ''; }
    else if (k === 'year') v = P.year[i] || null;
    else if (k === 'mass') v = P.mass[i] !== null ? ctLim(i, 'mass') + ctFmt(P.mass[i], 3) : (P.msini[i] !== null ? ctLim(i, 'msini') + ctFmt(P.msini[i], 3) + ' sin i' : null);
    else v = P[k][i] === null || P[k][i] === undefined ? null : ctLim(i, k) + ctFmt(P[k][i], k === 'period' ? 5 : k === 'radius' ? 3 : 4);
    // On a phone card each cell carries its label and unit as plain text (no extra boxes to style or lay out).
    if (v === null) return `<span role="cell" class="${cls} na" aria-label="not stored">—</span>`;
    return phone ? `<span role="cell">${k === 'star' || k === 'method' ? '' : lab + ' '}${v}${unit ? ' ' + unit : ''}</span>` : `<span role="cell" class="${cls}">${v}</span>`;
  };
  return `<a class="${h > 50 ? 'ctcard' : 'ctrow'}" role="row" aria-rowindex="${r + 1}" href="${ctPlanetHref(i)}" style="top:${r * h}px"><span role="rowheader"><b>${esc(P.name[i])}</b>${ctCls(i) ? ` <span class="ctcls">${esc(ctCls(i))}</span>` : ''}</span>${CT_COLS.map(c => cell(...c)).join('')}</a>`;
}
// Only the rows in view (plus a margin) are in the page. Scrolling keeps the rows already there and adds or
// removes only those entering or leaving the window, in order.
function ctRows(force){
  const sc = $('#ctscroll'), sp = $('#ctspacer'), H = sc.clientHeight, top = sc.scrollTop, h = ct.rowH;
  // A 12-row margin while scrolling normally; during a fling (more than a screen per frame) only the rows in
  // view, plus two, since the margin would be gone before anyone saw it.
  const m = Math.abs(top - (ct.prevTop ?? top)) > H ? 2 : 12; ct.prevTop = top;
  const a = Math.max(0, Math.floor(top / h) - m), b = Math.min(ct.idx.length, Math.ceil((top + H) / h) + m);
  if (force || !ct.nodes){ sp.textContent = ''; ct.nodes = new Map(); ct.win = null; ct.lastTop = top; }
  if (ct.win && ct.win[0] === a && ct.win[1] === b) return;
  const old = ct.win; ct.win = [a, b];
  const add = []; for (let r = a; r < b; r++) if (!ct.nodes.has(r)) add.push(r);
  if (!add.length){ for (const [r, el] of ct.nodes) if (r < a || r >= b){ el.remove(); ct.nodes.delete(r); } return; }
  // A jump (a fling, or a window that keeps under half its rows): render the whole window and swap it in with
  // one replaceChildren, instead of removing and inserting node by node.
  const jump = !old || add.length * 2 > b - a, rows = jump ? Array.from({length: b - a}, (_, k) => a + k) : add;
  const t = document.createElement('template'); t.innerHTML = rows.map(ctRowHTML).join('');
  const els = [...t.content.children];
  if (jump){ ct.nodes = new Map(rows.map((r, k) => [r, els[k]])); sp.replaceChildren(...els); return; }
  // A small step: drop the rows that left, add the new ones in order.
  for (const [r, el] of ct.nodes) if (r < a || r >= b){ el.remove(); ct.nodes.delete(r); }
  els.forEach((el, k) => ct.nodes.set(rows[k], el));
  const first = sp.firstElementChild, firstR = first ? Number(first.getAttribute('aria-rowindex')) - 1 : Infinity;
  if (rows[0] < firstR) sp.prepend(...els); else sp.append(...els);
}
function ctControls(){
  const v = ct.view;
  $('#ctq').value !== v.q && document.activeElement !== $('#ctq') && ($('#ctq').value = v.q);
  $$('#ctmethods [data-cm]').forEach(b => b.setAttribute('aria-pressed', String(v.methods.includes(b.dataset.cm))));
  // Never overwrite a box being typed in, or one whose range is still waiting to apply.
  $$('#route-catalogue [data-rk]').forEach(inp => { if (document.activeElement === inp || ct.rangeT[inp.dataset.rk]) return; const r = v[inp.dataset.rk] || [null, null], x = r[inp.dataset.end === 'lo' ? 0 : 1]; inp.value = x === null ? '' : x; });
  const tr = v.teff || [null, null];
  $$('#route-catalogue [data-ts]').forEach(inp => { if (document.activeElement === inp) return; const x = inp.dataset.ts === 'lo' ? (tr[0] ?? 2500) : (tr[1] ?? 10000); inp.value = x; inp.setAttribute('aria-valuetext', Number(x).toLocaleString('en-US') + ' K'); });
  $('#ctmulti').setAttribute('aria-pressed', String(v.multi)); $('#cthasdist').setAttribute('aria-pressed', String(v.hasdist));
  $$('#cttable .cth').forEach(h => h.setAttribute('aria-sort', h.dataset.sort === v.sort ? (v.dir === 'desc' ? 'descending' : 'ascending') : 'none'));
  if (Object.keys(v).some(k => Array.isArray(v[k]) && v[k].length === 2 && (v[k][0] !== null || v[k][1] !== null) && k !== 'methods')) $('#route-catalogue .ctmore').open = true;
}
function syncCatURL(push){ if (current === 'catalogue' && ct.view) setHash('#/catalogue' + (encodeCatView(ct.view) ? '?' + encodeCatView(ct.view) : ''), !!push); }
function ctBind(){
  if (ct.bound) return; ct.bound = true;
  let qt = null;
  $('#ctq').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { ct.view.q = e.target.value.slice(0, 120); ctApply(); syncCatURL(false); }, 120); });
  $('#ctmethods').addEventListener('click', e => { const b = e.target.closest('[data-cm]'); if (!b) return; const m = b.dataset.cm, on = ct.view.methods.includes(m);
    ct.view.methods = CTM.methods.filter(x => x === m ? !on : ct.view.methods.includes(x)); ctApply(); syncCatURL(true); });
  // Ranges apply as you type, with the same debounce as the text search (the address is replaced, not pushed).
  // Each range has its own timer, and when it fires it reads both of its boxes, so typing "from", Tab, "to"
  // quickly keeps both ends.
  $$('#route-catalogue [data-rk]').forEach(inp => inp.addEventListener('input', () => {
    const k = inp.dataset.rk; clearTimeout(ct.rangeT[k]);
    ct.rangeT[k] = setTimeout(() => { delete ct.rangeT[k];
      const val = end => { const el = $(`#route-catalogue [data-rk="${k}"][data-end="${end}"]`), x = el.value === '' ? null : Number(el.value); return Number.isFinite(x) ? x : null; };
      ct.view[k] = [val('lo'), val('hi')]; ctApply(); syncCatURL(false); }, 120);
  }));
  $('#ctmulti').addEventListener('click', () => { ct.view.multi = !ct.view.multi; ctApply(); syncCatURL(true); });
  $('#cthasdist').addEventListener('click', () => { ct.view.hasdist = !ct.view.hasdist; ctApply(); syncCatURL(true); });
  $('#ctreset').addEventListener('click', () => { ct.view = decodeCatView(new URLSearchParams()); ctApply(); syncCatURL(true); });
  $$('#cttable .cth').forEach(h => h.addEventListener('click', () => { const k = h.dataset.sort; ct.view.dir = ct.view.sort === k && ct.view.dir === 'asc' ? 'desc' : 'asc'; ct.view.sort = k; ctApply(); syncCatURL(true); }));
  // One update per frame however many scroll events arrive, and none when the top has not moved: a fling's
  // big jump rebuilds once.
  $('#ctscroll').addEventListener('scroll', () => { if (!ct.raf) ct.raf = requestAnimationFrame(() => { ct.raf = 0; const top = $('#ctscroll').scrollTop; if (top === ct.lastTop) return; ct.lastTop = top; ctRows(false); }); }, {passive: true});
  // A resize (or the phone breakpoint) changes the window of rows and, at the breakpoint, the row height.
  const relayout = () => { if (current !== 'catalogue' || !ct.P) return; const h = ctPhone() ? CT_CARD_H : 44; if (h !== ct.rowH){ ct.rowH = h; $('#ctspacer').style.height = ct.idx.length * h + 'px'; } ctRows(true); };
  if (window.ResizeObserver) new ResizeObserver(relayout).observe($('#ctscroll'));
  $('#ctcsv').addEventListener('click', ctCsv);
  // V09: the temperature strip's two handles set the host-temperature range (the strip's ends mean no limit).
  $('#route-catalogue').addEventListener('setu:teff-range', e => { const d = e.detail || {}, lo = Number(d.lo), hi = Number(d.hi);
    ct.view.teff = [lo > 2500 ? lo : null, hi < 10000 ? hi : null]; ctApply(); syncCatURL(false); });
}
// CSV of the filtered, sorted view: every stored column with its errors; empty where not stored.
function ctCsv(){
  const P = ct.P, cols = ct.C.columns.filter(c => c !== 'slug'), q = x => x === null || x === undefined ? '' : (/[",\n]/.test(String(x)) ? '"' + String(x).replace(/"/g, '""') + '"' : String(x));
  const lines = [cols.join(',')]; for (const i of ct.idx) lines.push(cols.map(c => q(P[c][i])).join(','));
  lines.push(`# ${ct.idx.length} rows from ${ct.C.source_name}, fetched ${ct.C.fetched_at}; filters: ${encodeCatView(ct.view) || 'none'}`);
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n') + '\n'], {type: 'text/csv'}));
  a.download = 'setuhq-catalogue.csv'; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  say(`Downloading ${ct.idx.length} rows as CSV.`);
}
function applyCatalogue(v){ ct.view = v; if (ct.rendered) ctApply(); }

// ---------- planet and star pages ----------
const CT_ROWS = [
  ['Mass', 'mass', 'MJ'], ['Minimum mass (m sin i)', 'msini', 'MJ'], ['Radius', 'radius', 'RJ'], ['Orbital period', 'period', 'd'],
  ['Semi-major axis', 'a', 'AU'], ['Eccentricity', 'e', ''], ['Inclination', 'incl', '°'], ['Impact parameter', 'b', ''],
  ['RV semi-amplitude K', 'k', 'm/s'], ['Equilibrium temperature', 'teq', 'K'], ['Measured temperature', 'tmeas', 'K'], ['Spin–orbit angle λ', 'lambda', '°']];
const CT_STAR_ROWS = [['Effective temperature', 'steff', 'K'], ['Radius', 'srad', 'R☉'], ['Mass', 'smass', 'M☉'], ['Metallicity [Fe/H]', 'smet', 'dex'],
  ['Age', 'sage', 'Gyr'], ['Distance', 'dist', 'pc'], ['V magnitude', 'vmag', ''], ['RA (J2000)', 'ra', '°'], ['Dec (J2000)', 'dec', '°']];
// A stored value's error as the page shows it. exoplanet.eu stores an upper limit as lower error = value and upper
// error = 0, the range from 0 to the value: that reads "≤ value", with no error. Both errors 0 means none was
// stored: none is shown. Otherwise ± or − / +. (The planet stubs and pre-rendered pages: setuhq.stubs.is_upper_limit.)
function ctErr(x, lo, hi){
  const has = v => v !== null && v !== undefined;
  if (!has(lo) || !has(hi) || (lo === 0 && hi === 0)) return {limit: false, err: ''};
  if (hi === 0 && lo > 0 && Math.abs(lo - x) <= 1e-9 * Math.max(Math.abs(x), 1e-30)) return {limit: true, err: ''};
  return {limit: false, err: lo === hi ? ` ± ${ctFmt(lo)}` : ` −${ctFmt(lo)} / +${ctFmt(hi)}`};
}
// "≤ " before a stored upper limit, in the table as on the planet's page.
const ctLim = (i, k) => { const P = ct.P; return P[k + '_lo'] && P[k + '_hi'] && ctErr(P[k][i], P[k + '_lo'][i], P[k + '_hi'][i]).limit ? '≤ ' : ''; };
const CT_TYPE = {mass: 'mass_type', radius: 'radius_type'};  // how the value was obtained; "Theoretical" is said so
function ctVal(i, k, unit){
  const P = ct.P, x = P[k][i]; if (x === null || x === undefined) return '<td class="v na">not stored</td>';
  const lo = P[k + '_lo'] ? P[k + '_lo'][i] : null, hi = P[k + '_hi'] ? P[k + '_hi'][i] : null, r = ctErr(x, lo, hi);
  const lim = r.limit ? '<span class="lim" title="Upper limit from the stored range (0 to this value)">≤ </span>' : '';
  const theory = CT_TYPE[k] && P[CT_TYPE[k]] && P[CT_TYPE[k]][i] === 'Theoretical' ? ' <span class="na">· theoretical estimate</span>' : '';
  return `<td class="v">${lim}${ctFmt(x, 6)}${r.err}${unit ? ' ' + unit : ''}${theory}</td>`;
}
function ctTable(i, rows){
  const P = ct.P, limits = rows.some(([, k]) => P[k][i] !== null && P[k][i] !== undefined && P[k + '_lo'] && P[k + '_hi'] && ctErr(P[k][i], P[k + '_lo'][i], P[k + '_hi'][i]).limit);
  return `<table class="pltable"><tbody>${rows.map(([lab, k, u]) => `<tr><th scope="row">${esc(lab)}</th>${ctVal(i, k, u)}</tr>`).join('')}</tbody></table>`
    + (limits ? '<p class="small">≤: an upper limit, from the stored range (0 to the value).</p>' : '');
}
function ctMoll(ra, dec){ // Mollweide, 400 × 200 units, centred on RA 0°, RA increasing to the left
  let lam = -((ra > 180 ? ra - 360 : ra) * Math.PI / 180), phi = dec * Math.PI / 180, th = phi;
  for (let k = 0; k < 30; k++){ const f = 2 * th + Math.sin(2 * th) - Math.PI * Math.sin(phi); th -= f / (2 + 2 * Math.cos(2 * th) + 1e-12); }
  return [200 / Math.PI * lam * Math.cos(th), -100 * Math.sin(th)];
}
function ctSky(i, label){
  const ra = ct.P.ra[i], dec = ct.P.dec[i];
  if (ra === null || dec === null) return '<p>Sky position not stored.</p>';
  const [x, y] = ctMoll(ra, dec);
  return `<svg class="plsky" viewBox="-210 -110 420 240" role="img" aria-label="${esc(label)} on an all-sky map at RA ${ctFmt(ra, 6)}°, Dec ${ctFmt(dec, 6)}°.">
    <ellipse rx="200" ry="100" fill="rgba(255,255,255,.03)" stroke="var(--line-2)"/><line x1="-200" x2="200" y1="0" y2="0" stroke="var(--line)"/><line x1="0" x2="0" y1="-100" y2="100" stroke="var(--line)"/>
    <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="9" fill="none" stroke="var(--cyan)"/><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" fill="var(--cyan)"/>
    <text x="0" y="124" text-anchor="middle">all sky · centre RA 0° · RA increases to the left</text></svg><p class="mono" style="margin:4px 0 0">RA ${ctFmt(ra, 7)}° · Dec ${ctFmt(dec, 7)}° (J2000)</p>`;
}
function ctWhere(i, star){
  const P = ct.P, links = [];
  if (P.dist[i] !== null) links.push(`<a href="${R(`#/galaxy?focus=${encodeURIComponent(star || P.name[i])}`)}">Show on the Galaxy map ›</a>`);
  links.push(`<a href="${R(`#/sky`)}">The run's sky map ›</a>`);
  const dist = P.dist[i] === null ? 'Distance not stored, so the Galaxy map cannot place it.' : `${ctFmt(P.dist[i], 5)} pc · ${ctFmt(P.dist[i] * 3.261563777, 5)} ly`;
  return ctSky(i, star || P.name[i]) + `<p>${dist}</p><div class="pllinks">${links.join('')}</div>`;
}
function plShow(slug){
  if (!CTM) return;
  ctLoad().then(() => {
    const i = ct.bySlug[slug], note = $('#plnote');
    const body = $$('#route-planet .plgrid, #route-planet .plmore, #route-planet #plref').map(x => x.closest('.plgrid, .plmore, section.card'));
    if (i === undefined){ note.innerHTML = `No planet "${esc(slug)}" in the catalogue. <a href="${R(`#/catalogue?q=${encodeURIComponent(slug.replace(/-/g, ' '))}`)}">Search the Catalogue ›</a>`; note.hidden = false;
      $('#h-planet').textContent = 'Planet not found'; $('#plsub').textContent = ''; $('#plextra').innerHTML = ''; body.forEach(x => { x.hidden = true; }); plShown(false); return; }
    note.hidden = true; body.forEach(x => { x.hidden = false; });
    const P = ct.P, star = P.star[i], cls = mxClassOf(P.radius[i], P.mass[i] !== null ? P.mass[i] : P.msini[i]);
    const clsName = cls === null ? 'class not determinable (no radius or mass stored)' : ['Earth-size', 'Super-Earth', 'Sub-Neptune', 'Neptune-like', 'Gas giant'][cls] + (P.radius[i] === null ? ' (by mass)' : '');
    $('#h-planet').textContent = P.name[i]; if (current === 'planet') pageChrome('planet', new URLSearchParams({id: slug}));
    $('#plsub').innerHTML = `${star ? `<a href="${ctStarHref(star)}">${esc(star)}</a>` : 'host not stored'} · ${esc(CTM.method_label[P.method[i]] || P.method[i])} · discovered ${P.year[i] || 'year not stored'} · ${esc(clsName)}`;
    const ex = $('#plextra'), hero = ex && ex.querySelector('#plhero');
    if (ex && !(hero && hero.dataset.slug === slug)){ ex.innerHTML = ctPlanetExtras(i); if (window.SetuRender) SetuRender.mount(ex); }
    ctSpin(ex);
    $('#plparams').innerHTML = ctTable(i, CT_ROWS) + `<p class="small">Units as stored by ${esc(ct.C.source_short)}. Errors are the stored lower and upper bounds; none is shown where none is stored.</p>`;
    const sibs = star ? ct.byStar[star].slice().sort((a, b) => (P.period[a] ?? 1e99) - (P.period[b] ?? 1e99)) : [i];
    $('#plhost').innerHTML = (star ? `<p><a href="${ctStarHref(star)}">${esc(star)}</a>${P.sptype[i] ? ' · ' + esc(P.sptype[i]) : ''}${P.steff[i] !== null ? ' · ' + ctFmt(P.steff[i]) + ' K' : ''}</p>` : '<p>Host star not stored.</p>')
      + `<ul class="pllist">${sibs.map(j => `<li><a href="${ctPlanetHref(j)}"${j === i ? ' aria-current="page"' : ''}><span>${esc(P.name[j])}</span><span class="mono">${ctFmt(P.period[j], 5) ? ctFmt(P.period[j], 5) + ' d' : 'period —'}</span></a></li>`).join('')}</ul>`;
    $('#plwhere').innerHTML = ctWhere(i, star);
    const ch = CTM.method_chapter[P.method[i]];
    const ref = CTM.refs[P.name[i]];
    $('#plref').innerHTML = `<p>${esc(ct.C.source_short)} lists it as "${esc(P.status[i] || 'status not stored')}"${P.method_raw[i] ? `, found by ${esc(P.method_raw[i])}` : ''}${P.year[i] ? ` in ${P.year[i]}` : ''}; record updated ${esc(P.updated[i] || 'not stored')}.${P.alt[i] ? ` Also known as ${esc(P.alt[i])}.` : ''}</p>
      <p>${ref ? `Discovery paper: <a href="${esc(ref[0])}" rel="noopener">${esc(ref[1])}</a> (from SetuHQ's checked list of notable planets; ${esc(ct.C.source_short)} stores no DOI).` : `${esc(ct.C.source_short)} stores no DOI or reference for the discovery paper, so none is shown.`}</p>
      <div class="pllinks">${ch ? `<a href="${R(`#/methods?ch=${ch}`)}">How ${esc((CTM.method_label[P.method[i]] || '').toLowerCase())} works ›</a>` : ''}</div>${ctSeen(P.name[i], ch ? R('#/methods?ch=' + ch) : '')}`;
    plSystem($('#plsys'), i, current === 'planet');
  }).catch(() => { $('#plnote').textContent = 'The catalogue file could not be loaded here.'; $('#plnote').hidden = false; });
}
// ---------- the portrait, its star, the line-up and the orbits (twins of catalogue.planet_extras and star_extras) ----------
const CT_PIC = '/docs/pictures/', CT_GIF = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=', CT_RE = 11.209;
const CT_SPIN = '<div class="stage-ctrls"><button class="btn" type="button" data-spin aria-pressed="false" hidden>Spin</button></div>';
const ctStill = (lk, px) => (CTM.stills || '') + lk + '-' + px + '.webp';
const ctSrc = () => `${ct.C.source_short}, fetched ${String(ct.C.fetched_at).slice(0, 10)}`;
const ctN0 = x => Math.round(x).toLocaleString('en-US');
function ctRow(i){ const o = {}; for (const k of ['radius', 'mass', 'msini', 'a', 'period', 'srad', 'smass', 'steff', 'teq']) o[k] = ct.P[k][i]; return o; }
function ctFig(kind, params, alt, cap, label, still, extra){
  const tag = kind === 'planet' ? `<a class="stage-tag" href="${CT_PIC}">${esc(label)}</a>` : `<span class="stage-tag">${esc(label)}</span>`;
  return `<figure class="stage rfig" data-render="${kind}" data-params='${esc(JSON.stringify(params))}' aria-label="${esc(alt)}"><div class="rbox"><img class="rstill" src="${esc(still)}" width="512" height="512" alt="${esc(alt)}">${extra || ''}</div>${tag}<figcaption class="readout">${cap}</figcaption></figure>`;
}
function ctPortrait(i){
  const P = ct.P, lk = window.SetuRender ? SetuRender.look(ctRow(i)) : {name: null}; if (!lk.name) return '';
  const comp = {envelope: 'an envelope planet', rock: 'a rocky planet', neptune: 'a Neptune-like planet', giant: 'a gas giant', ambiguous: 'a planet of unknown make-up'}[lk.composition];
  const size = lk.rp_re !== null ? `${lk.rp_re.toFixed(2)} Earth radii` : `radius not measured (${lk.mp_me.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1})} Earth masses)`;
  const alt = `Artist's impression of ${P.name[i]}: ${comp}${lk.band ? ` in the ${lk.band} band` : ''}, ${size}, ${lk.teq !== null ? ctN0(lk.teq) + ' K' : 'irradiation not computable'}.`;
  const cap = esc(`Artist's impression · ${lk.composition}${lk.band ? ', ' + lk.band : ', irradiation not computable'} · ${lk.reasons.join(' ')}`) + ` Source: ${esc(ctSrc())}. <a href="${CT_PIC}">How the pictures are drawn ›</a>`;
  const params = {look: lk.name, seed: SetuRender.fnv(P.slug[i]), rp_re: lk.rp_re, teq: lk.teq, animate: false}; if (lk.neutral) params.neutral = true;
  return ctFig('planet', params, alt, cap, "Artist's impression", ctStill(lk.name, 512), CT_SPIN);
}
function ctStarFig(name, teff, srad){
  if (!teff) return '';
  const rad = srad ? `, radius ${srad.toFixed(2)} R☉` : '';
  return ctFig('star', {teff, rstar_rsun: srad, animate: false}, `${name} drawn in its blackbody colour, ${ctN0(teff)} K${rad}.`,
    `${esc(name)} in its blackbody colour: ${ctN0(teff)} K${esc(rad)} (${esc(ctSrc())}). Brightness normalised; the surface texture is decorative.`, 'Model from stored values', CT_GIF);
}
function ctLineup(i){
  const P = ct.P; if (!P.radius[i] || !window.SetuRender) return '';
  const fr = r => r < 6 ? `${r.toFixed(2)} R⊕` : `${(r / CT_RE).toFixed(2)} RJ`;
  const its = [['Earth', 1, 'ref-earth'], ['Neptune', 3.88, 'ref-neptune'], ['Jupiter', CT_RE, 'ref-jupiter']].map(([name, re, look]) => ({name, re, look, ref: 1}))
    .concat([{name: P.name[i], re: Math.round(P.radius[i] * CT_RE * 1000) / 1000, look: SetuRender.look(ctRow(i)).name, focus: 1}]).sort((a, b) => a.re - b.re);
  const big = its[its.length - 1], small = its[0];
  const lis = its.map(q => `<li class="luitem${q.ref ? ' ref' : ''}${q.focus ? ' focus' : ''}" style="--re:${q.re.toFixed(3)}"><img src="${ctStill(q.look, 160)}" srcset="${ctStill(q.look, 160)} 160w, ${ctStill(q.look, 512)} 512w" sizes="(max-width:700px) 120px, 200px" width="160" height="160" loading="lazy" decoding="async" alt="${esc(q.name)}, ${fr(q.re)}: ${q.ref ? 'a Solar System reference' : 'an artist&#39;s impression'}"><b>${esc(q.name)}</b><span>${fr(q.re)}</span></li>`).join('');
  return `<section class="pllineup" aria-label="${esc(P.name[i])} in the line-up"><figure class="lineup" data-viz="lineup" aria-label="${esc(P.name[i])} to scale"><div class="stage lustage" style="--rmax:${big.re.toFixed(3)}"><ol class="lurow">${lis}</ol><a class="stage-tag" href="${CT_PIC}">Artist's impression</a></div>`
    + `<figcaption class="skysrc">To scale: one Earth radius is the same width all along the row, so ${esc(big.name)} is ${(big.re / small.re).toFixed(1)} times as wide as ${esc(small.name)}. Each picture is an artist's impression chosen from the measured radius and the computed irradiation; composition is not measured. Earth, Neptune and Jupiter are the Solar System references (only Earth is drawn with oceans). Radii: ${esc(ctSrc())} (1 RJ = 11.209 R⊕). <a href="${CT_PIC}">How the pictures are drawn ›</a></figcaption></figure></section>`;
}
function ctPlanetExtras(i){
  const P = ct.P, pic = ctPortrait(i), st = ctStarFig(P.star[i] || 'The host star', P.steff[i], P.srad[i]);
  return `<div class="plhero${pic ? '' : ' solo'}" id="plhero" data-slug="${esc(P.slug[i])}">${pic}${st}${pic ? '' : '<p class="plnone">No radius or mass stored, so no planet is drawn.</p>'}</div>` + ctLineup(i);
}
// V08 on a star page (twin of viz.orbits.system and html): a from the catalogue or Kepler's third law, depth (Rp/R★)².
function ctOrbits(name, ps){
  const P = ct.P, hex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
  const pl = ps.filter(j => P.period[j] > 0).map(j => {
    let a = P.a[j] > 0 ? P.a[j] : null, src = 'catalogue';
    if (a === null){ a = P.smass[j] > 0 ? Math.cbrt(P.smass[j] * (P.period[j] / 365.25) ** 2) : null; src = "Kepler's third law"; }
    const rp = P.radius[j] > 0 ? P.radius[j] : null, rs = P.srad[j] > 0 ? P.srad[j] : null, k = rp && rs ? rp * 71492 / 695700 / rs : null;
    const lk = window.SetuRender ? SetuRender.look(ctRow(j)).name : null, L = lk && SetuRender.LOOKS[lk];
    return a === null ? null : {name: P.name[j], slug: P.slug[j], P: P.period[j], a, src, re: rp && rp * CT_RE, d: k && k * k * 1e6,
      w: rs ? P.period[j] / Math.PI * Math.asin(Math.min(1, rs * 695700 / 149597870.7 / a)) * 24 : null, c: hex(L ? L.pal[2] : [170, 182, 204])};
  }).filter(Boolean).sort((x, y) => x.P - y.P);
  if (pl.length < 2) return '';
  const short = n => { const t = n.toLowerCase().startsWith(name.toLowerCase()) ? n.slice(name.length).trim() : ''; return t.length > 0 && t.length <= 3 ? t : n; };
  const T = pl[pl.length - 1].P, f2 = (x, d) => x.toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
  const params = {teff: P.steff[ps[0]], speed: Math.max(1.6, Math.min(T / 12, pl[0].P / 1.5)), planets: pl.map((q, i) => ({n: short(q.name), P: q.P, a: q.a, d: q.d, w: q.w, c: q.c, f: i ? (i * .4) % 1 : 0}))};
  const label = `The ${pl.length} planets of ${name} seen from above, with their dips over one ${T.toFixed(2)}-day period of the outermost: ` + pl.map(q => `${q.name} every ${q.P.toFixed(2)} d at ${q.a.toFixed(4)} AU` + (q.d ? `, ${f2(q.d, 0)} ppm deep` : '')).join('; ') + '.';
  const rows = pl.map(q => `<tr><th scope="row"><a href="/planets/${esc(q.slug)}/">${esc(q.name)}</a></th><td>${f2(q.P, 4)}</td><td>${q.a.toFixed(4)}${q.src === 'catalogue' ? '' : '*'}</td><td>${q.re ? q.re.toFixed(2) : '—'}</td><td>${q.d ? f2(q.d, 0) : '—'}</td></tr>`).join('');
  return `<figure class="orbits" data-viz="orbits" data-params='${esc(JSON.stringify(params))}'><div class="stage orbstage"><div class="orbbox"><svg class="orbsvg" role="img" aria-label="${esc(label)}"></svg></div><span class="stage-tag">Model from stored values</span><div class="stage-ctrls"><button class="btn" type="button" data-orb="play" aria-pressed="false" hidden>Play</button></div></div>`
    + `<figcaption class="skysrc">The ${esc(name)} system from above: each planet dips the star's light when it crosses the line of sight to the observer. Orbit sizes are the stored semi-major axes (or Kepler's third law from the period and the star's mass); dip depth is (Rp/R★)² from the stored radii. Circular orbits, star and planets not to scale, phases illustrative (no transit times are stored). Source: ${esc(ctSrc())}.</figcaption>`
    + `<details class="orbtable"><summary>The planets: period, orbit and dip depth</summary><div class="tablewrap" tabindex="0" role="region" aria-label="${esc(name)}: period, orbit and dip depth"><table class="pltable"><thead><tr><th scope="col">Planet</th><th scope="col">P (d)</th><th scope="col">a (AU)</th><th scope="col">Rp (R⊕)</th><th scope="col">Depth k² (ppm)</th></tr></thead><tbody>${rows}</tbody></table></div><p class="small">a from ${esc(ct.C.source_short)}; * from Kepler's third law (period and the star's mass). — : radius not stored.</p></details></figure>`;
}
// The portrait turns (0.12 rad/s) while on screen, the tab visible and the viewer has not paused it; under reduced motion
// it holds its still until Spin is pressed. Its own loop, at 30 fps (15 on the Canvas2D path).
function ctSpin(root){
  const fig = root && root.querySelector('[data-render="planet"]'), btn = fig && fig.querySelector('[data-spin]');
  if (!btn || fig._spin) return; fig._spin = 1;
  const S = {on: false, t: 0, raf: 0, vis: true, last: 0, at: 0}, ok = () => fig._sr && fig._sr.cv && window.SetuRender;
  const set = () => { btn.hidden = !ok(); btn.textContent = S.on ? 'Pause' : 'Spin'; btn.setAttribute('aria-pressed', String(S.on)); };
  const frame = now => { S.raf = 0; if (!S.on || !S.vis || document.hidden || !ok() || !fig.isConnected) return;
    const dt = Math.min(.1, (now - (S.last || now)) / 1000); S.last = now; S.t += dt;
    if (now - S.at >= (SetuRender.stats().path === 'canvas2d' ? 66 : 33)){ S.at = now; try { SetuRender.planet(fig._sr.cv, Object.assign({}, fig._sr.p, {t: S.t})); } catch (e) { S.on = false; set(); return; } }
    S.raf = requestAnimationFrame(frame); };
  const kick = () => { if (!S.raf && S.on && S.vis && !document.hidden){ S.last = 0; S.raf = requestAnimationFrame(frame); } };
  btn.addEventListener('click', () => { S.on = !S.on; set(); kick(); });
  if ('IntersectionObserver' in window) new IntersectionObserver(es => es.forEach(e => { S.vis = e.isIntersecting; kick(); }), {rootMargin: '80px'}).observe(fig);
  document.addEventListener('visibilitychange', kick);
  let n = 0; const wait = () => { if (ok()){ S.on = !matchMedia('(prefers-reduced-motion: reduce)').matches; set(); kick(); } else if (n++ < 60) setTimeout(wait, 250); };
  wait();
}
// The shared animated system, from planet i's stored values only; the caption says what is not stored.
// Back-links: where SetuHQ itself shows this planet or star (the Transit case, Galaxy tour stops, Methods chapters).
function ctSeen(name, skip){ const ls = (CTM.mentions[name] || []).filter(([, href]) => R(href) !== skip).map(([lab, href]) => `<a href="${esc(R(href))}">${esc(lab)} ›</a>`).join('');
  return ls ? `<div class="pllinks plseen"><span class="pllab">Where SetuHQ shows it:</span>${ls}</div>` : ''; }
function plSystem(fig, i, on){
  const P = ct.P, pimen = typeof S !== 'undefined' && S.planet && P.name[i] === S.planet;
  const p = {name: P.name[i], star_teff: P.steff[i], star_radius: P.srad[i], radius: P.radius[i], semi_major_axis: P.a[i], orbital_period: P.period[i],
    inclination: P.incl[i], impact_parameter: P.b[i], mass: P.mass[i], mass_sini: P.msini[i], eccentricity: P.e[i]};
  return mxSystemView(fig, p, {dip: pimen && MX && MX.lead_dip ? {pts: MX.lead_dip.pts} : null, on, source: ct.C.source_short});
}
function stShow(slug){
  if (!CTM) return;
  ctLoad().then(() => {
    const name = ct.starBySlug[slug], note = $('#stnote');
    const body = $$('#route-star .plgrid, #route-star .plmore');
    if (!name){ note.innerHTML = `No star "${esc(slug)}" in the catalogue. <a href="${R(`#/catalogue?q=${encodeURIComponent(slug.replace(/-/g, ' '))}`)}">Search the Catalogue ›</a>`; note.hidden = false;
      $('#h-star').textContent = 'Star not found'; $('#stsub').textContent = ''; $('#stextra').innerHTML = ''; body.forEach(x => { x.hidden = true; }); return; }
    note.hidden = true; body.forEach(x => { x.hidden = false; });
    const P = ct.P, ps = ct.byStar[name].slice().sort((a, b) => (P.period[a] ?? 1e99) - (P.period[b] ?? 1e99)), i = ps[0];
    $('#h-star').textContent = name; if (current === 'star') pageChrome('star', new URLSearchParams({id: slug}));
    const teff = P.steff[i];
    const [cl, row] = teff !== null ? mxClass(teff) : [null, null];
    $('#stsub').textContent = `${ps.length} planet${ps.length === 1 ? '' : 's'} in ${ct.C.source_short}` + (P.sptype[i] ? ` · stored type ${P.sptype[i]}` : '') + (cl ? ` · class ${cl} from Teff (nearest ${row})` : '');
    $('#stparams').innerHTML = ctTable(i, CT_STAR_ROWS) + (P.salt[i] ? `<p class="small">Also known as ${esc(P.salt[i])}.</p>` : '');
    const thumb = j => { const lk = window.SetuRender && SetuRender.look(ctRow(j)).name; return lk ? `<img class="plthumb" src="${ctStill(lk, 160)}" width="40" height="40" loading="lazy" alt="">` : '<span class="plthumb none" aria-hidden="true"></span>'; };
    $('#stplanets').innerHTML = `<ul class="pllist plthumbs">${ps.map(j => `<li><a href="${ctPlanetHref(j)}">${thumb(j)}<span>${esc(P.name[j])}</span><span class="mono">${esc(CTM.method_label[P.method[j]] || P.method[j])} · ${P.year[j] || '—'}</span></a></li>`).join('')}</ul><p class="small">Pictures: artist's impressions from the measured radius and irradiation. <a href="${CT_PIC}">How the pictures are drawn ›</a></p>`;
    const sx = $('#stextra'), sh = sx && sx.querySelector('#sthero');
    if (sx && !(sh && sh.dataset.star === name)){ const f = ctStarFig(name, P.steff[i], P.srad[i]) + ctOrbits(name, ps); sx.innerHTML = f ? `<div class="sthero" id="sthero" data-star="${esc(name)}">${f}</div>` : ''; if (window.SetuRender) SetuRender.mount(sx); }
    if (window.SetuOrbits) SetuOrbits.wire(sx);
    $('#stwhere').innerHTML = ctWhere(i, name) + ctSeen(name, R('#/sky'));
    if (typeof vaForStar === 'function') vaForStar(P.salt[i]);
    // The system view with one of its planets (the innermost first); the picker switches planet.
    const pick = $('#stpick');
    pick.innerHTML = ps.map(j => `<option value="${j}">${esc(P.name[j])}</option>`).join('');
    pick.onchange = () => plSystem($('#stsys'), Number(pick.value), current === 'star');
    plSystem($('#stsys'), i, current === 'star');
  }).catch(() => { $('#stnote').textContent = 'The catalogue file could not be loaded here.'; $('#stnote').hidden = false; });
}
function plShown(r){ for (const [id, route] of [['#plsys', 'planet'], ['#stsys', 'star']]){ const fig = $(id); if (fig && fig._mx){ fig._mx.on = r === route; if (fig._mx.on) mxKick(fig._mx); } } }

// ---------- global search: planets, stars, chapters and sections ----------
const gs = {sel: 0, items: []};
function gsIndexStatic(){
  const out = [];
  for (const n of D.nav){ out.push({kind: 'section', label: n.label, href: n.href}); for (const [label, h] of (D.subnav[n.id] || [])) if (label !== n.label) out.push({kind: n.label, label, href: R(h)}); }
  if (MX) for (const id of MX.chapters) out.push({kind: 'chapter', label: MX.labels[id], href: R('#/methods?ch=' + id)});
  return out;
}
function gsSearch(q){
  q = q.trim().toLowerCase();
  const st = gsIndexStatic().filter(x => !q || x.label.toLowerCase().includes(q)), res = [];
  if (q && ct.P){
    const P = ct.P, starts = [], has = [];
    for (let i = 0; i < P.name.length && starts.length < 40; i++){ const n = P.name[i].toLowerCase(), a = (P.alt[i] || '').toLowerCase(); if (n.startsWith(q)) starts.push(i); else if ((n.includes(q) || a.includes(q)) && has.length < 40) has.push(i); }
    for (const i of starts.concat(has).slice(0, 12)) res.push({kind: 'planet', label: P.name[i], sub: P.star[i] || '', href: ctPlanetHref(i), teff: P.steff[i], cls: ctCls(i)});
    let n = 0; for (const s of ct.C.stars.names){ if (s.toLowerCase().includes(q)){ res.push({kind: 'star', label: s, sub: `${ct.byStar[s].length} planet${ct.byStar[s].length === 1 ? '' : 's'}`, href: ctStarHref(s), teff: P.steff[ct.byStar[s][0]]}); if (++n >= 6) break; } }
  }
  if (q && typeof vaSearch === 'function') res.push(...vaSearch(q));
  return st.slice(0, q ? 6 : 20).concat(res);
}
function gsRender(){
  const q = $('#gsq').value; gs.items = gsSearch(q); gs.sel = Math.min(gs.sel, Math.max(0, gs.items.length - 1));
  $('#gsresults').innerHTML = gs.items.length ? gs.items.map((x, k) => `<li role="option" id="gs-${k}" aria-selected="${k === gs.sel}"><a href="${x.href}" tabindex="-1"><span>${x.kind === 'planet' || x.kind === 'star' ? ctDot(x.teff) : ''}${esc(x.label)}${x.cls ? ` <span class="ctcls">${esc(x.cls)}</span>` : ''}${x.sub ? ` <span class="kind">${esc(x.sub)}</span>` : ''}</span><span class="kind">${x.kind}</span></a></li>`).join('')
    : `<li class="gshint">${ct.P ? 'Nothing matches.' : 'Loading the catalogue…'}</li>`;
  $('#gsq').setAttribute('aria-activedescendant', gs.items.length ? 'gs-' + gs.sel : '');
  const cur = $('#gs-' + gs.sel); if (cur) cur.scrollIntoView({block: 'nearest'});
}
function gsOpen(){
  const dlg = $('#gsearch'); if (!dlg) return;
  if (!dlg.open) dlg.showModal();
  $('#gsq').value = ''; gs.sel = 0; gsRender(); $('#gsq').focus();
  if (CTM) ctLoad().then(gsRender).catch(() => {});
  if (typeof VA !== 'undefined' && VA) vaLoad().then(gsRender).catch(() => {});
}
if ($('#gsearch')){
  $('#gsearchbtn').addEventListener('click', gsOpen);
  $('#gsq').addEventListener('input', () => { gs.sel = 0; gsRender(); });
  $('#gsq').addEventListener('keydown', e => {
    // Escape closes the dialog whatever is typed (a search field would otherwise only clear itself).
    if (e.key === 'Escape'){ e.preventDefault(); $('#gsearch').close(); return; }
    if (e.key === 'ArrowDown'){ gs.sel = Math.min(gs.items.length - 1, gs.sel + 1); gsRender(); e.preventDefault(); }
    else if (e.key === 'ArrowUp'){ gs.sel = Math.max(0, gs.sel - 1); gsRender(); e.preventDefault(); }
    else if (e.key === 'Enter' && gs.items[gs.sel]){ e.preventDefault(); $('#gsearch').close(); navTo(gs.items[gs.sel].href); }
  });
  $('#gsresults').addEventListener('click', e => { if (e.target.closest('a')) $('#gsearch').close(); });
  $('#gsearch').addEventListener('click', e => { if (e.target === $('#gsearch')) $('#gsearch').close(); });
  document.addEventListener('keydown', e => {
    if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))){ e.preventDefault(); gsOpen(); }
  });
}
"""

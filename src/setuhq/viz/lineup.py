# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V07 line-up: planets drawn to one scale beside Earth, Neptune and Jupiter, from the catalogue's radii.

Used on: Home (the showcase planets), planet pages ("this planet in the line-up"), the README figure. Owner: P2
(docs/SITE.md, "The visual system").

Each planet's radius is exoplanet.eu's (Jupiter radii × 11.209 = Earth radii), and its picture is its look's still
(setuhq.looks, an artist's impression chosen from the measured radius and irradiation); Earth, Neptune and Jupiter
are the Solar System references (Earth is the only one drawn with oceans). One Earth radius is the same width
everywhere in the row, so the sizes compare; a planet without a stored radius is never in a line-up. The row is
plain HTML: the stills sized by CSS, each with its name and radius, which is also the text alternative.
"""

from __future__ import annotations

import html as _html

from setuhq.looks import REFERENCES, RJ_IN_RE, find_planet, look, row
from setuhq.renderer import PICTURES, still_href
from setuhq.i18n import N_, k as ik, span
from setuhq.viz import require_source

REF_ORDER = ("ref-earth", "ref-neptune", "ref-jupiter")
FALSE_POSITIVE = "false positive"  # a showcase kind with this in it has no planet to draw


def _shown_name(cat: dict, i: int, star: str) -> str:
    """The name SetuHQ uses: the catalogue's, or an alternative name that starts with the example's star
    (exoplanet.eu's TOI-402 Ab is shown as HD 15337 b)."""
    P = cat["planets"]
    alts = (P.get("alt") or [None] * len(P["name"]))[i] or ""
    for a in (x.strip() for x in alts.split(",")):
        if star and a.lower().startswith(star.lower() + " "):
            return a
    # The star is listed under the example's name (exoplanet.eu's TOI-402 A is also HD 15337): its letter after that name.
    salts = [x.strip().lower() for x in ((P.get("salt") or [None] * len(P["name"]))[i] or "").split(",")]
    letter = P["name"][i].rsplit(" ", 1)[-1][-1:]
    if star and star.lower() in salts and letter.isalpha() and P["name"][i].lower() != star.lower():
        return f"{star} {letter}"
    return P["name"][i]


def entry(cat: dict, i: int, name: str | None = None) -> dict | None:
    """One catalogue planet as the line-up draws it, or None without a stored radius."""
    P = cat["planets"]
    if not P["radius"][i]:
        return None
    lk = look(row(cat, i))
    return {"name": name or P["name"][i], "catalogue_name": P["name"][i], "slug": P["slug"][i], "rp_re": round(P["radius"][i] * RJ_IN_RE, 3),
            "radius_rj": P["radius"][i], "look": lk["name"]}


def showcase_entries(app: dict) -> list[dict]:
    """The worked examples' known planets with a stored radius (each example's star, found by its name or, through
    looks.find_planet, by its planet's), smallest first. A known false positive has none to draw."""
    cat = app.get("catalogue")
    if not cat:
        return []
    P = cat["planets"]
    out, seen = [], set()
    for c in app.get("showcase") or []:
        if FALSE_POSITIVE in (c.get("kind") or "").lower():
            continue
        star = c.get("star") or ""
        hosts = {star.lower()}
        # The run's own planet, and the known planets showcase.json lists for it (HD 15337's are TOI-402 A's).
        for name in [c.get("planet")] + list(c.get("planets") or []):
            j = find_planet(cat, name) if name else None
            if j is not None and P["star"][j]:
                hosts.add(P["star"][j].lower())
        for i, s in enumerate(P["star"]):
            if s and s.lower() in hosts and i not in seen:
                en = entry(cat, i, _shown_name(cat, i, star))
                if en:
                    seen.add(i)
                    out.append(en)
    return sorted(out, key=lambda x: x["rp_re"])


def data(app_data: dict) -> dict:
    """The line-up's section of stories.json: the showcase planets and the references, with their source."""
    cat = (app_data or {}).get("catalogue")
    es = showcase_entries(app_data or {})
    if not cat or not es:
        return {}
    return {"lineup": {"planets": es, "refs": [{"name": REFERENCES[k][0], "rp_re": REFERENCES[k][1], "look": k} for k in REF_ORDER],
                       "source": f"{cat.get('source_name')}, fetched {str(cat.get('fetched_at'))[:10]}"}}


def fmt_r(re_: float) -> str:
    """A radius as the line-up labels it: Earth radii below 6, Jupiter radii above."""
    return f"{re_:.2f} R⊕" if re_ < 6 else f"{re_ / RJ_IN_RE:.2f} RJ"


def items(planets: list[dict], refs: bool = True) -> list[dict]:
    out = [dict(p) for p in planets]
    if refs:
        out += [{"name": REFERENCES[k][0], "rp_re": REFERENCES[k][1], "look": k, "ref": True} for k in REF_ORDER]
    return sorted(out, key=lambda x: x["rp_re"])


def html(data: dict, **opts) -> str:
    """The row. ``data``: ``source`` (printed) and either the app data as ``app`` (the showcase planets) or
    ``planets`` [{name, rp_re, look, slug?}] (a planet page: ``focus`` names the planet that steps in)."""
    require_source(data)
    planets = data.get("planets")
    if planets is None:
        planets = showcase_entries(data.get("app") or {})
    planets = [p for p in planets if p.get("rp_re") and p.get("look")]
    if not planets:
        return ""
    e = _html.escape
    its = items(planets, refs=opts.get("refs", True))
    rmax = max(p["rp_re"] for p in its)
    focus = data.get("focus")
    lis = []
    for p in its:
        lk = p["look"]
        name = e(p["name"])
        if p.get("slug") and p["name"] != focus:
            name = f'<a href="/planets/{e(p["slug"])}/">{name}</a>'
        cls = "luitem" + (" ref" if p.get("ref") else "") + (" focus" if p["name"] == focus else "")
        # The 160 px still, or the 512 px one for a disc drawn wider than 80 px (at one Earth radius per 8 px).
        px = 512 if p["rp_re"] / rmax * 90 > 40 else 160
        lis.append(f'<li class="{cls}" style="--re:{p["rp_re"]:.3f}"><img src="{still_href(lk, px)}" width="160" height="160" loading="lazy" '
                   f'alt=""><b{ik("lu." + p["name"].lower()) if p.get("ref") and p["name"] in ("Earth", "Neptune", "Jupiter") else ""}>{name}</b><span>{e(fmt_r(p["rp_re"]))}</span></li>')  # the name and radius beside it are the text
    big = max(its, key=lambda p: p["rp_re"])
    small = min(its, key=lambda p: p["rp_re"])
    title = e(data.get("title") or "Planets to scale")
    cap = span("lu.cap", "To scale: one Earth radius is the same width all along the row, so {big} is {x} times as wide as {small}. Each picture is an artist\'s impression chosen from the measured radius and the computed irradiation; composition is not measured. Earth, Neptune and Jupiter are the Solar System references (only Earth is drawn with oceans). Radii: {src} (1 RJ = 11.209 R⊕).", x=format(big["rp_re"] / small["rp_re"], ".1f"), src=data["source"], **_ref("big", big["name"]), **_ref("small", small["name"]))
    return (f'<figure class="lineup" data-viz="lineup" aria-label="{title}">'
            f'<div class="stage lustage" style="--rmax:{rmax:.3f}"><ol class="lurow">{"".join(lis)}</ol>'
            f'<a class="stage-tag" href="{PICTURES}" data-i18n="label.art">Artist\'s impression</a></div>'
            f'<figcaption class="skysrc">{cap} '
            f'<a href="{PICTURES}"{ik("footer.pictures")}>How the pictures are drawn ›</a></figcaption></figure>')


REF_NAMES = {"Earth": N_("lu.earth", "Earth"), "Neptune": N_("lu.neptune", "Neptune"), "Jupiter": N_("lu.jupiter", "Jupiter")}


def _ref(arg: str, name: str) -> dict:
    """A planet name as a message argument; a Solar System reference also names its own message (translated)."""
    return {arg: name, arg + "@": "lu." + name.lower()} if name in REF_NAMES else {arg: name}


CSS = """
/* ---------- viz.lineup (V07): planets to one scale ---------- */
.lineup{margin:0;display:grid;gap:8px;min-width:0}
.lustage{padding:44px 16px 14px;--u:min(8px,calc(90px / var(--rmax)))}
.lurow{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:center;gap:18px 10px}
.luitem{display:grid;justify-items:center;align-content:end;gap:4px;min-width:76px;text-align:center}
.luitem img{display:block;width:calc(var(--re) * var(--u) * 2);height:auto;max-width:none;border-radius:50%}
.luitem b{font:600 12px/1.25 var(--sans);color:var(--stage-ink);margin-top:6px}
.luitem b a{color:var(--stage-ink)}
.luitem span{font:500 11px/1.2 var(--mono);color:var(--stage-dim)}
.luitem.ref b{color:var(--stage-dim);font-weight:500}
.luitem.focus b{color:#64D2FF}
@media (max-width:699.98px){.lustage{--u:min(5px,calc(56px / var(--rmax)));padding:40px 8px 12px}.luitem{min-width:64px}}
"""

JS = ""

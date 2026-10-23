# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The home page (/), in this order (docs/SITE.md, "The visual system"; the redesign's section 1.2):

1. the hero (V01, setuhq.viz.hero): a live transit of the featured run's star under the heading;
2. the worked examples (V03, setuhq.viz.gallery), one card per run in docs/results/showcase.json order;
3. the temperature strip (V09, setuhq.viz.tempstrip): each example star at its stored Teff, and the Sun;
4. the showcase planets to scale (V07, setuhq.viz.lineup);
5. the fold (V05, setuhq.viz.fold): pi Men's real light curve, folded;
6. who reviews (V06, setuhq.viz.panelring): the lead dip's panel, with the attribution line;
7. the sky by year (V04, setuhq.viz.skyyears) and the timeline (V12, setuhq.viz.timeline);
8. the evidence counters (V10, design.odometer_html), every number read from the build's data;
9. the reference check, the sweep line and what a visitor can do here;
10. what this page does not claim.

Bands 4 to 7 are drawn by modules other phases own; each is called through its fixed signature
(``html(data, **opts)``, with ``data = {"source", "app", ...}`` and ``where="home"``) and a band whose module
returns "" is left out. Every number on the page comes from stored files: the runs, showcase.json, the catalogue,
the benchmark JSON and the chapter list.
"""

from __future__ import annotations

import html
import importlib

from setuhq.app import BENCHMARK_JSON, NO_DETECTION, UNCONFIRMED
from setuhq.design import odometer_html
from setuhq.everything import sweep_line
from setuhq.learn import learn_card
from setuhq.names import ATTRIBUTION, PROBES_ONLY, panel_phrase
from setuhq.renderer import PICTURES
from setuhq.story import number_words
from setuhq.viz import gallery, hero, tempstrip

# The bands, in page order (a test pins it); each key is also the band's id ("band-<key>").
BANDS = ("hero", "gallery", "tempstrip", "lineup", "fold", "panel", "sky", "counters", "refcheck", "sweep", "dohere", "honest")


def _honest(data: dict) -> str:
    e = html.escape
    h = data["hero"]
    dc = data["run"].get("docket_counts") or {}
    cal = data.get("calibration") or {}
    n_inj = max([p.get("n_injected") or 0 for p in cal.get("points") or []] or [0])
    weights = f" Their weights rest on calibration with {n_inj} planted and {n_inj} empty light curves each, so they are rough." if n_inj else ""
    match = f" The match with {e(h['match'])} says the planet is already known, not that this run confirmed it." if h.get("match") else ""
    return f"""<section class="honest" id="band-honest" aria-labelledby="h-honest">
        <h2 id="h-honest">What this page does not claim</h2>
        <ul>
          <li><b>No confirmed planet.</b> Every dip, signal and feed entry here is a {UNCONFIRMED}. Passing vetting is not a confirmation.{match}</li>
          <li><b>No planet sizes.</b> No stellar radius is stored, so a depth gives only a planet-to-star radius ratio. The radius-ratio page shows the working.</li>
          <li><b>No people on the panel.</b> The panel is the Sentinels and the Probes: {e(panel_phrase(dc.get('claude', 0), dc.get('simulated', 0), dc.get('other', 0)))}. {e(ATTRIBUTION)}{e(weights)}</li>
          <li><b>{e(NO_DETECTION.split(". ")[0])}.</b> {e(NO_DETECTION.split(". ", 1)[1])} A TOI or archive match compares a stored period with published values.</li>
          <li><b>No image of the planet.</b> Planet pictures are artist's impressions, chosen from measured radius and irradiation; <a href="{PICTURES}">How the pictures are drawn ›</a></li>
        </ul>
      </section>"""


# The home page's "what you can do here" row: one card per section of the site, in plain words.
DO_HERE = [
    ("#/sky", "Explore the sky", "Every known exoplanet on a 3D map of the Galaxy, the sky TESS has covered, and a searchable catalogue of known planets."),
    ("#/explorer", "See the candidates", "Dips the panel marked in the example stars' TESS light curves, each with its full case file. Candidates, never confirmed planets."),
    ("#/methods", "Learn how it works", "Fifteen illustrated chapters on how planets are found, from a star's wobble to reading an atmosphere."),
    ("#/sentinels", "Check the evidence", "How the panel scores on real, known objects: the blind benchmark, the public leaderboard and the calibration."),
    ("#/docs", "Run it yourself", "Install SetuHQ, search a star, contribute a sweep of the sky, or connect your AI assistant over MCP."),
]


def _do_here() -> str:
    e = html.escape
    cards = "".join(f'<li><a class="docard" href="{e(h)}"><b>{e(t)}</b><span>{e(d)}</span><i aria-hidden="true">›</i></a></li>'
                    for h, t, d in DO_HERE)
    return f"""<section class="dohere" id="band-dohere" aria-labelledby="h-dohere">
        <h2 id="h-dohere">What you can do here</h2>
        <ul class="docards">{cards}</ul>
      </section>"""


def _date(iso: str | None) -> str:
    return (iso or "")[:10]


def counters(data: dict) -> list[dict]:
    """The evidence counters (V10), each read from the build's data with its source and its proof page: the catalogue's
    rows, the real-TOI benchmark's sample, its held-out completeness (always with its Wilson interval) and the
    chapters of How it works. A counter whose data is not stored is left out."""
    from setuhq.methods import CHAPTERS

    out = []
    cat = data.get("catalogue") or {}
    rows = (cat.get("counts") or {}).get("rows")
    if rows:
        out.append({"key": "catalogue", "value": rows, "text": f"{rows:,}", "label": "planets in the catalogue SetuHQ checks against",
                    "source": f"{cat.get('source_name') or cat.get('source_short') or 'exoplanet.eu'}, fetched {_date(cat.get('fetched_at'))}",
                    "href": "#/catalogue"})
    b = data.get("benchmark") or {}
    sample = b.get("sample") or {}
    n_toi = sum((sample.get("counts") or {}).values())
    if n_toi:
        out.append({"key": "benchmark", "value": n_toi, "text": f"{n_toi:,}", "label": "real TESS Objects of Interest in the blind benchmark",
                    "source": f"{sample.get('source') or 'NASA Exoplanet Archive'}, fetched {_date(sample.get('fetched_at'))} ({BENCHMARK_JSON})",
                    "href": "#/leaderboard"})
    comp = (((b.get("summary") or {}).get("held_out") or {}).get("completeness")) or {}
    if all(comp.get(x) is not None for x in ("k", "n", "lo", "hi")) and comp["n"]:
        rate = comp["k"] / comp["n"]
        out.append({"key": "completeness", "value": round(100 * rate), "text": f"{100 * rate:.0f}%", "rate": [comp["k"], comp["n"], comp["lo"], comp["hi"]],
                    "label": "of the held-out known planets found blind (Wilson 95% interval)",
                    "source": f"held-out half of the benchmark ({BENCHMARK_JSON})", "href": "#/sentinels"})
    out.append({"key": "chapters", "value": len(CHAPTERS), "text": f"{len(CHAPTERS):,}", "label": "illustrated chapters on how planets are found",
                "source": "How it works", "href": "#/methods"})
    return out


def _counters_band(data: dict) -> str:
    e = html.escape
    items = []
    for c in counters(data):
        num = odometer_html(c["text"], label=f'{c["text"]} {c["label"]}', rate=tuple(c["rate"]) if c.get("rate") else None,
                            is_rate=c["key"] == "completeness")
        items.append(f'<li class="ctr" data-key="{e(c["key"])}"><a href="{e(c["href"])}"><b class="ctrn">{num}</b>'
                     f'<span class="ctrl">{e(c["label"])}</span><span class="ctrs">{e(c["source"])}</span><i aria-hidden="true">›</i></a></li>')
    if not items:
        return ""
    return _band("counters", "The evidence, counted", f'<ul class="ctrlist">{"".join(items)}</ul>', eyebrow="Every number links to its proof")


def _band(key: str, title: str, body: str, *, eyebrow: str = "", more: str = "") -> str:
    e = html.escape
    eb = f'<p class="bandeyebrow">{e(eyebrow)}</p>' if eyebrow else ""
    return (f'<section class="band" id="band-{key}" aria-labelledby="h-{key}"><div class="bandhead">{eb}'
            f'<h2 id="h-{key}">{e(title)}</h2></div>{body}{more}</section>')


def _placed(name: str, data: dict, source: str, **extra) -> str:
    """A band drawn by another phase's module, through its fixed signature; "" while that module is a stub."""
    mod = importlib.import_module(f"setuhq.viz.{name}")
    return mod.html({"source": source, "app": data, **extra}, where="home", compact=True) or ""


def _cat_source(data: dict) -> str:
    cat = data.get("catalogue") or {}
    return f"{cat.get('source_name') or 'exoplanet.eu'}, fetched {_date(cat.get('fetched_at'))}" if cat else ""


def _temps(data: dict) -> str:
    cards = data.get("showcase") or []
    marks = []
    for c in cards:
        sp = ((data.get("run_ctx") or {}).get(c["run"]) or {}).get("star_params") or {}
        if sp.get("teff"):
            marks.append({"name": c["star"], "teff": sp["teff"], "href": f"#ex-{c['slug']}"})
    if not marks:
        return ""
    src = (f"Star colour: a Planck spectrum through the CIE 1931 colour-matching functions, in sRGB, normalised to its "
           f"brightest channel (a hue, not a brightness). Teff: each run's stellar.json (TESS Input Catalog v8.2, MAST); "
           f'the Sun 5,772 K (IAU 2015 nominal). <a href="{PICTURES}">How the pictures are drawn ›</a>')
    body = tempstrip.html({"source": src, "markers": marks})
    lo, hi = min(m["teff"] for m in marks), max(m["teff"] for m in marks)
    title = f"Any star: from {round(lo):,} K to {round(hi):,} K, one pipeline" if len(marks) > 1 else "The example star's colour"
    return _band("tempstrip", title, body, eyebrow="Every kind of star")


def _hero_copy(n_ex: int) -> str:
    more = f'<a class="btn ghost" href="#examples">See {number_words(n_ex)} worked examples ›</a>' if n_ex > 1 else ""
    return (f'<h1 id="h-overview" tabindex="-1">The sky, reviewed.</h1>'
            f'<p class="sub">SetuHQ searches any TESS star\'s public light curve for transits. A calibrated panel of Sentinels (AI reviewers) and Probes (deterministic detectors) marks the dips, and vetting explains every verdict. Nothing is called a planet until it is one.</p>'
            f'<div class="ctas"><a class="btn primary" href="#/sky">Explore the sky</a>{more}</div>')


def _overview(data: dict, with_view: bool = True) -> str:
    e = html.escape
    st = data["story"]
    planet = st.get("planet")
    n_ex = len(data.get("showcase") or [])
    copy = _hero_copy(n_ex)
    stage = hero.html(hero.from_app(data), copy=f'<div class="herocopy">{copy}</div>') if hero.runs(data) else ""
    head = f'<header class="launch">{stage}</header>' if stage else f'<header class="launch">{copy}</header>'
    g = gallery.from_app(data)
    gal = gallery.html(g) if g["cards"] else ""

    lineup = _placed("lineup", data, _cat_source(data)) if data.get("catalogue") else ""
    fold = _placed("fold", data, "pi Men's stored light curve (runs/tess-pi-men-s1/subjects), folded on the joint-fit period in docs/results/pi_men_validation.json")
    run = data["run"]["name"]
    ring = _placed("panelring", data, f"run {run}: the stored marks and the calibrated weights ({data.get('weights_path') or 'not stored'})",
                   dip=st.get("lead_dip"), run=run)
    probes_only = ((data.get("run_ctx") or {}).get(run) or {}).get("probes_only")
    sky = (_placed("skyyears", data, _cat_source(data)) + _placed("timeline", data, _cat_source(data))) if data.get("catalogue") else ""
    bands = [
        head,
        gal,
        _temps(data),
        _band("lineup", "The showcase planets, to scale", lineup, eyebrow="Planets to scale") if lineup else "",
        _band("fold", "How a planet hides in the noise", fold, eyebrow="Real data",
              more='<p class="bandmore"><a href="#/methods?ch=transit">How transits are found ›</a></p>') if fold else "",
        _band("panel", "Who reviews a dip", ring, eyebrow="The panel",
              more=f'<p class="bandnote">{e(ATTRIBUTION)}</p>' + (f'<p class="bandnote">{e(PROBES_ONLY)}</p>' if probes_only else "")) if ring else "",
        _band("sky", "Every known planet's star, by the year it was found", sky, eyebrow="The sky",
              more='<p class="bandmore"><a href="#/sky">Explore the sky ›</a></p>') if sky else "",
        _counters_band(data),
    ]
    proof = "".join(f'<div><b style="--c:{p["colour"]}">{e(p["big"])}</b><span>{e(p["text"])}</span></div>' for p in st["proof"])
    ref = (f"The reference check: {e(planet)}, a known planet, found again in run {e(run)}" if planet
           else f"The reference run: {e(run)}")
    bands.append(f'<section class="refcheck" id="band-refcheck" aria-labelledby="h-refcheck"><div class="secthead"><h2 id="h-refcheck">{ref}</h2></div>'
                 f'<div class="proof" role="list" aria-label="What the reference run shows">{proof.replace("<div>", "<div role=" + chr(34) + "listitem" + chr(34) + ">")}</div></section>')
    sweep = sweep_line(data.get("sweep"))
    bands.append(f'<div class="homesweep" id="band-sweep">{sweep}</div>' if sweep else "")
    bands.append(_do_here())
    bands.append(_honest(data))
    bands.append(learn_card() if with_view else "")
    return "\n      ".join(b for b in bands if b)


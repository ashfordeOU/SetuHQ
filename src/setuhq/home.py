# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The home page (/): its hero, what a visitor can do here, the worked examples, the reference check, the sweep
line and what the page does not claim. Moved here from setuhq.app unchanged, so the home page has one owner."""

from __future__ import annotations

import html

from setuhq.app import NO_DETECTION, UNCONFIRMED
from setuhq.everything import sweep_line
from setuhq.galaxy import teaser_html
from setuhq.learn import learn_card
from setuhq.names import ATTRIBUTION, panel_phrase
from setuhq.story import number_words


def _honest(data: dict) -> str:
    e = html.escape
    h = data["hero"]
    dc = data["run"].get("docket_counts") or {}
    cal = data.get("calibration") or {}
    n_inj = max([p.get("n_injected") or 0 for p in cal.get("points") or []] or [0])
    weights = f" Their weights rest on calibration with {n_inj} planted and {n_inj} empty light curves each, so they are rough." if n_inj else ""
    match = f" The match with {e(h['match'])} says the planet is already known, not that this run confirmed it." if h.get("match") else ""
    return f"""<section class="honest" aria-labelledby="h-honest">
        <h2 id="h-honest">What this page does not claim</h2>
        <ul>
          <li><b>No confirmed planet.</b> Every dip, signal and feed entry here is a {UNCONFIRMED}. Passing vetting is not a confirmation.{match}</li>
          <li><b>No planet sizes.</b> No stellar radius is stored, so a depth gives only a planet-to-star radius ratio. The radius-ratio page shows the working.</li>
          <li><b>No people on the panel.</b> The panel is the Sentinels and the Probes: {e(panel_phrase(dc.get('claude', 0), dc.get('simulated', 0), dc.get('other', 0)))}. {e(ATTRIBUTION)}{e(weights)}</li>
          <li><b>{e(NO_DETECTION.split(". ")[0])}.</b> {e(NO_DETECTION.split(". ", 1)[1])} A TOI or archive match compares a stored period with published values.</li>
          <li><b>No image of the planet.</b> The planet on the home page is an artist's impression; the field stars on the sky map are decorative.</li>
        </ul>
      </section>"""


def _planet_figure(deco: dict) -> str:
    """The home page's artist's impression: a planet's limb lit by its star, cropped to the lit limb, with its
    caption directly under it. Decorative, and labelled so."""
    return f"""<figure class="planetfig">
        <svg viewBox="0 120 1440 360" preserveAspectRatio="xMidYMax slice" role="img" aria-label="Artist's impression of a planet's limb lit by its star. It shows no real planet." style="display:block;width:100%;height:auto">
          <defs>
            <radialGradient id="pBody" cx="35%" cy="15%" r="85%"><stop offset="0" stop-color="#3C5E8C"/><stop offset=".35" stop-color="#1D3352"/><stop offset=".7" stop-color="#0A1222"/><stop offset="1" stop-color="#000"/></radialGradient>
            <radialGradient id="pAtm" cx="50%" cy="100%" r="62%"><stop offset=".86" stop-color="#64D2FF" stop-opacity="0"/><stop offset=".92" stop-color="#64D2FF" stop-opacity=".55"/><stop offset=".97" stop-color="#0A84FF" stop-opacity=".18"/><stop offset="1" stop-color="#0A84FF" stop-opacity="0"/></radialGradient>
            <radialGradient id="sGlow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#FFF4D6"/><stop offset=".08" stop-color="#FFD28A" stop-opacity=".9"/><stop offset=".3" stop-color="#FF9F2E" stop-opacity=".18"/><stop offset="1" stop-color="#FF9F2E" stop-opacity="0"/></radialGradient>
            <filter id="soft"><feGaussianBlur stdDeviation="9"/></filter>
            <clipPath id="pClip"><circle cx="720" cy="1290" r="1000"/></clipPath>
          </defs>
          <rect x="0" y="120" width="1440" height="360" fill="#000"/>
          <path class="twinkle" d="{deco['bright']}" stroke="#E8EEFF" stroke-width="1.6" stroke-linecap="round"/>
          <circle class="breathe" cx="1090" cy="200" r="210" fill="url(#sGlow)"/>
          <circle cx="1090" cy="200" r="9" fill="#FFFBEF"/>
          <circle cx="720" cy="1290" r="1060" fill="url(#pAtm)"/>
          <circle cx="720" cy="1290" r="1000" fill="url(#pBody)"/>
          <g clip-path="url(#pClip)"><g class="clouds" filter="url(#soft)" opacity=".35"><path d="{deco['bands']}" stroke="#BFD6F2" stroke-width="16" fill="none" stroke-linecap="round"/></g></g>
          <path d="M-280 1290 A1000 1000 0 0 1 1720 1290" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.2"/>
        </svg>
        <figcaption>Artist's impression of a planet lit by its star. It shows no real planet; SetuHQ works from light curves, not images.</figcaption>
      </figure>"""


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
    return f"""<section class="dohere" aria-labelledby="h-dohere">
        <h2 id="h-dohere">What you can do here</h2>
        <ul class="docards">{cards}</ul>
      </section>"""


def _gallery(data: dict) -> str:
    """The home page's worked examples: one card per stored run, in a fixed order (docs/results/showcase.json),
    with its star, what kind of example it is, its dips counted by outcome, its panel and its pages."""
    e = html.escape
    cards = data.get("showcase") or []
    if not cards:
        return ""
    items = []
    for c in cards:
        first = c["lead_dip"]
        sectors = ", ".join(str(x) for x in c["sectors"]) or "not stored"
        links = (f'<a href="{e(c["case_file"])}">Case file</a><a href="{e(c["plates"])}">Plates</a>'
                 f'<a href="{e(c["report"])}">Run report</a>')
        items.append(f"""<li><article class="excard" aria-labelledby="ex-{e(c["slug"])}">
          <p class="exkind">{e(c["kind"] or "Example run")}</p>
          <h3 id="ex-{e(c["slug"])}">{f'<a href="#/transit?dip={e(first)}">{e(c["star"])}</a>' if first else e(c["star"])}</h3>
          <p class="exsum">{e(c["summary"])}</p>
          <p class="excount">{e(c["count"])}</p>{f'<p class="excaveat">{e(c["caveat"])}</p>' if c["caveat"] else ""}
          <p class="exmeta">{e(c["mission"])} sector{"s" if len(c["sectors"]) != 1 else ""} {e(sectors)} · {e(c["panel_label"])}</p>
          <p class="exlinks">{links}</p>
        </article></li>""")
    return f"""<section class="examples" id="examples" aria-labelledby="h-examples">
        <div class="secthead"><h2 id="h-examples">Worked examples: {len(cards)} stars, one pipeline</h2>
        <p>Each is a stored run on public TESS light curves from MAST, with its data, configuration and code hashed. Every dip is counted by its vetting outcome; a candidate stays unconfirmed, and a rejected dip is not a candidate.</p></div>
        <ul class="excards">{"".join(items)}</ul>
      </section>"""


def _overview(data: dict, with_view: bool = True) -> str:
    e = html.escape
    st = data["story"]
    planet = st.get("planet")
    n_ex = len(data.get("showcase") or [])
    more = f'<a class="btn ghost" href="#examples">See {number_words(n_ex)} worked examples ›</a>' if n_ex > 1 else ""
    proof = "".join(f'<div><b style="--c:{p["colour"]}">{e(p["big"])}</b><span>{e(p["text"])}</span></div>' for p in st["proof"])
    ref = (f"The reference check: {e(planet)}, a known planet, found again in run {e(data['run']['name'])}" if planet
           else f"The reference run: {e(data['run']['name'])}")
    return f"""<header class="launch">
        <h1 id="h-overview" tabindex="-1">The sky, reviewed.</h1>
        <p class="sub">SetuHQ searches any TESS star's public light curve for transits. A calibrated panel of Sentinels (AI reviewers) and Probes (deterministic detectors) marks the dips, and vetting explains every verdict. Nothing is called a planet until it is one.</p>
        <div class="ctas"><a class="btn primary" href="#/sky">Explore the sky</a>{more}</div>
      </header>
      {_planet_figure(data["deco"])}
      {_do_here()}
      {_gallery(data)}
      <section class="refcheck" aria-labelledby="h-refcheck"><div class="secthead"><h2 id="h-refcheck">{ref}</h2></div>
      <div class="proof" role="list" aria-label="What the reference run shows">{proof.replace('<div>', '<div role="listitem">')}</div></section>
      {sweep_line(data.get("sweep"))}
      {teaser_html(data.get("galaxy"), data.get("galaxy_teaser"))}
      {_honest(data)}
      {learn_card() if with_view else ""}"""

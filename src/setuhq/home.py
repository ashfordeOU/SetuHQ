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

Bands 4 to 7 are drawn by the other components' modules, each called through its fixed signature
(``html(data, **opts)``, with ``data = {"source", "app", ...}`` and ``where="home"``); a module returns "" only when
its stored input is not in the build (no catalogue, no stored run or fit), and that band is then left out. Every number on the page comes from stored files: the runs, showcase.json, the catalogue,
the benchmark JSON and the chapter list.
"""

from __future__ import annotations

import html
import importlib

from setuhq.app import BENCHMARK_JSON, NO_DETECTION, UNCONFIRMED
from setuhq.i18n import N_, k as ik, ka, span, t, th
from setuhq.design import odometer_html
from setuhq.everything import sweep_line
from setuhq.learn import learn_card
from setuhq.names import ATTRIBUTION, PROBES_ONLY, panel_phrase
from setuhq.renderer import PICTURES
from setuhq.story import number_words
from setuhq.viz import gallery, hero, panelring, tempstrip

# The bands, in page order (a test pins it); each key is also the band's id ("band-<key>").
BANDS = ("hero", "gallery", "tempstrip", "lineup", "fold", "panel", "sky", "counters", "refcheck", "sweep", "dohere", "honest")


def _honest(data: dict) -> str:
    e = html.escape
    h = data["hero"]
    dc = data["run"].get("docket_counts") or {}
    cal = data.get("calibration") or {}
    n_inj = max([p.get("n_injected") or 0 for p in cal.get("points") or []] or [0])
    weights = span("home.honest.weights", " Their weights rest on calibration with {n} planted and {n} empty light curves each, so they are rough.", n=n_inj) if n_inj else ""
    match = h.get("match") or "none"
    ns, np_, no = dc.get('claude', 0), dc.get('simulated', 0), dc.get('other', 0)
    phrase = e(panel_phrase(ns, np_, no))
    if not no and (ns or np_):
        pid = "panel.both" if ns and np_ else "panel.sentinels" if ns else "panel.probes"
        phrase = span(pid, {"panel.both": "{s, plural, one {# Sentinel} other {# Sentinels}} and {p, plural, one {# Probe} other {# Probes}}",
                            "panel.sentinels": "{s, plural, one {# Sentinel} other {# Sentinels}}",
                            "panel.probes": "{p, plural, one {# Probe} other {# Probes}}"}[pid], s=ns, p=np_)
    N_("panel.both", "{s, plural, one {# Sentinel} other {# Sentinels}} and {p, plural, one {# Probe} other {# Probes}}", note="How many reviewers of each kind. Sentinel and Probe stay as written.")
    N_("panel.sentinels", "{s, plural, one {# Sentinel} other {# Sentinels}}")
    N_("panel.probes", "{p, plural, one {# Probe} other {# Probes}}")
    honest_image = t("home.honest.image", '<b>No image of the planet.</b> Planet pictures are artist\'s impressions, chosen from measured radius and irradiation; <a href="/docs/pictures/">How the pictures are drawn ›</a>')
    return f"""<section class="honest" id="band-honest" aria-labelledby="h-honest">
        <h2 id="h-honest"{ik("home.honest.h")}>{t("home.honest.h", "What this page does not claim")}</h2>
        <ul>
          <li{ik("home.honest.planet", status=UNCONFIRMED, match=match, **{"status@": "honesty.unconfirmed"})}>{th("home.honest.planet", "<b>No confirmed planet.</b> Every dip, signal and feed entry here is a {status}. Passing vetting is not a confirmation.{match, select, none {} other { The match with {match} says the planet is already known, not that this run confirmed it.}}", status=UNCONFIRMED, match=match)}</li>
          <li{ik("home.honest.sizes")}>{t("home.honest.sizes", "<b>No planet sizes.</b> No stellar radius is stored, so a depth gives only a planet-to-star radius ratio. The radius-ratio page shows the working.")}</li>
          <li><b{ik("home.honest.people")}>{t("home.honest.people", "No people on the panel.")}</b> {span("home.honest.panel", "The panel is the Sentinels and the Probes:")} {phrase}. <span{ik("honesty.attribution")}>{e(ATTRIBUTION)}</span>{weights}</li>
          <li{ik("home.honest.archive")}>{t("home.honest.archive", "<b>Archive values only.</b> This page claims no detection. A TOI or archive match compares a stored period with published values.")}</li>
          <li{ik("home.honest.image")}>{honest_image}</li>
        </ul>
      </section>"""


# The home page's "what you can do here" row: one card per section of the site, in plain words.
DO_HERE = [
    ("#/sky", N_("home.do.sky", "Explore the sky"), N_("home.do.sky.d", "Every known exoplanet on a 3D map of the Galaxy, the sky TESS has covered, and a searchable catalogue of known planets.")),
    ("#/explorer", N_("home.do.explorer", "See the candidates"), N_("home.do.explorer.d", "Dips the panel marked in the example stars' TESS light curves, each with its full case file. Candidates, never confirmed planets.")),
    ("#/methods", N_("home.do.methods", "Learn how it works"), N_("home.do.methods.d", "Fifteen illustrated chapters on how planets are found, from a star's wobble to reading an atmosphere.")),
    ("#/sentinels", N_("home.do.sentinels", "Check the evidence"), N_("home.do.sentinels.d", "How the panel scores on real, known objects: the blind benchmark, the public leaderboard and the calibration.")),
    ("#/docs", N_("home.do.docs", "Run it yourself"), N_("home.do.docs.d", "Install SetuHQ, search a star, contribute a sweep of the sky, or connect your AI assistant over MCP.")),
]


def _do_here() -> str:
    e = html.escape
    key = lambda h: "home.do." + h[2:]  # noqa: E731
    cards = "".join(f'<li><a class="docard" href="{e(h)}"><b{ik(key(h))}>{e(t)}</b><span{ik(key(h) + ".d")}>{e(d)}</span><i aria-hidden="true">›</i></a></li>'
                    for h, t, d in DO_HERE)
    return f"""<section class="dohere" id="band-dohere" aria-labelledby="h-dohere">
        <h2 id="h-dohere"{ik("home.dohere")}>{t("home.dohere", "What you can do here")}</h2>
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
        out.append({"key": "catalogue", "value": rows, "text": f"{rows:,}", "label": N_("home.ctr.catalogue", "planets in the catalogue SetuHQ checks against"),
                    "source": f"{cat.get('source_name') or cat.get('source_short') or 'exoplanet.eu'}, fetched {_date(cat.get('fetched_at'))}",
                    "sk": ("home.ctr.fetched", {"source": cat.get('source_name') or cat.get('source_short') or 'exoplanet.eu', "date": _date(cat.get('fetched_at'))}),
                    "href": "#/catalogue"})
    b = data.get("benchmark") or {}
    sample = b.get("sample") or {}
    n_toi = sum((sample.get("counts") or {}).values())
    if n_toi:
        out.append({"key": "benchmark", "value": n_toi, "text": f"{n_toi:,}", "label": N_("home.ctr.benchmark", "real TESS Objects of Interest in the blind benchmark"),
                    "source": f"{sample.get('source') or 'NASA Exoplanet Archive'}, fetched {_date(sample.get('fetched_at'))} ({BENCHMARK_JSON})",
                    "sk": ("home.ctr.fetched_file", {"source": sample.get('source') or 'NASA Exoplanet Archive', "date": _date(sample.get('fetched_at')), "file": BENCHMARK_JSON}),
                    "href": "#/leaderboard"})
    comp = (((b.get("summary") or {}).get("held_out") or {}).get("completeness")) or {}
    if all(comp.get(x) is not None for x in ("k", "n", "lo", "hi")) and comp["n"]:
        rate = comp["k"] / comp["n"]
        out.append({"key": "completeness", "value": round(100 * rate), "text": f"{100 * rate:.0f}%", "rate": [comp["k"], comp["n"], comp["lo"], comp["hi"]],
                    "label": N_("home.ctr.completeness", "of the held-out known planets found blind (Wilson 95% interval)"),
                    "source": f"held-out half of the benchmark ({BENCHMARK_JSON})", "sk": ("home.ctr.heldout", {"file": BENCHMARK_JSON}), "href": "#/sentinels"})
    out.append({"key": "chapters", "value": len(CHAPTERS), "text": f"{len(CHAPTERS):,}", "label": N_("home.ctr.chapters", "illustrated chapters on how planets are found"),
                "source": "How it works", "sk": ("nav.how", {}), "href": "#/methods"})
    N_("home.ctr.fetched", "{source}, fetched {date, date}")
    N_("home.ctr.fetched_file", "{source}, fetched {date, date} ({file})")
    N_("home.ctr.heldout", "held-out half of the benchmark ({file})")
    return out


def _counters_band(data: dict) -> str:
    e = html.escape
    items = []
    for c in counters(data):
        num = odometer_html(c["text"], label=f'{c["text"]} {c["label"]}', rate=tuple(c["rate"]) if c.get("rate") else None,
                            is_rate=c["key"] == "completeness")
        items.append(f'<li class="ctr" data-key="{e(c["key"])}"><a href="{e(c["href"])}"><b class="ctrn">{num}</b>'
                     f'<span class="ctrl"{ik("home.ctr." + c["key"])}>{e(c["label"])}</span><span class="ctrs"{ik(c["sk"][0], **c["sk"][1]) if c.get("sk") else ""}>{e(c["source"])}</span><i aria-hidden="true">›</i></a></li>')
    if not items:
        return ""
    return _band("counters", t("home.band.counters", "The evidence, counted"), f'<ul class="ctrlist">{"".join(items)}</ul>',
                 eyebrow=t("home.band.counters.e", "Every number links to its proof"))


def _band(key: str, title: str, body: str, *, eyebrow: str = "", more: str = "", targs: dict | None = None) -> str:
    e = html.escape
    eb = f'<p class="bandeyebrow"{ik("home.band." + key + ".e")}>{e(eyebrow)}</p>' if eyebrow else ""
    return (f'<section class="band" id="band-{key}" aria-labelledby="h-{key}"><div class="bandhead">{eb}'
            f'<h2 id="h-{key}"{ik("home.band." + key, **(targs or {}))}>{e(title)}</h2></div>{body}{more}</section>')


def _placed(name: str, data: dict, source: str, **extra) -> str:
    """A band drawn by another component's module, through its fixed signature; "" when its stored input is missing."""
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
    src = (span("ts.src", "Star colour: a Planck spectrum through the CIE 1931 colour-matching functions, in sRGB, normalised to its "
                "brightest channel (a hue, not a brightness). Teff: each run's stellar.json (TESS Input Catalog v8.2, MAST); "
                "the Sun 5,772 K (IAU 2015 nominal).")
           + f' <a href="{PICTURES}"{ik("footer.pictures")}>How the pictures are drawn ›</a>')
    body = tempstrip.html({"source": src, "markers": marks})
    lo, hi = min(m["teff"] for m in marks), max(m["teff"] for m in marks)
    # Only as wide as the stored examples: n stars from the coolest to the hottest Teff stored, never "any star".
    n = len(marks)
    title = (f"{number_words(n).capitalize()} example stars: {round(lo):,}\u00a0K to {round(hi):,}\u00a0K, one pipeline" if n > 1
             else "The example star's colour")
    N_("home.band.tempstrip", "{n, plural, =1 {The example star's colour} =2 {Two example stars: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline} "
       "=3 {Three example stars: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline} =4 {Four example stars: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline} "
       "=5 {Five example stars: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline} =6 {Six example stars: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline} "
       "one {# example star: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline} other {# example stars: {lo, number, integer}\u00a0K to {hi, number, integer}\u00a0K, one pipeline}}",
       note="The temperature strip's heading: how many example stars and their range of temperature (K, kelvin). Never 'every star'.")
    N_("home.band.tempstrip.e", "The example stars' colours")
    return _band("tempstrip", title, body, eyebrow="The example stars' colours", targs={"n": n, "lo": round(lo), "hi": round(hi)})


def _hero_copy(n_ex: int) -> str:
    N_("home.hero.more", "{n, plural, =2 {See two worked examples ›} =3 {See three worked examples ›} =4 {See four worked examples ›} =5 {See five worked examples ›} =6 {See six worked examples ›} one {See # worked example ›} other {See # worked examples ›}}")
    sub = t("home.hero.sub", "SetuHQ searches any TESS star's public light curve for transits. A calibrated panel of Sentinels (AI reviewers) and Probes "
            "(deterministic detectors) marks the dips, and vetting explains every verdict. Nothing is called a planet until it is one.",
            note="The home page promise. Nothing stronger: no planet is claimed.")
    more = f'<a class="btn ghost" href="#examples"{ik("home.hero.more", n=n_ex)}>See {number_words(n_ex)} worked examples ›</a>' if n_ex > 1 else ""
    return (f'<h1 id="h-overview" tabindex="-1"{ik("home.hero.h1")}>{t("home.hero.h1", "The sky, reviewed.")}</h1>'
            f'<p class="sub"{ik("home.hero.sub")}>{sub}</p>'
            f'<div class="ctas"><a class="btn primary" href="#/sky"{ik("home.do.sky")}>Explore the sky</a>{more}</div>')


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
    # The lead dip's own panel, as its dip page draws it (setuhq.viz.panelring.for_dip): its stored marks, calibrated
    # weights and stored score. No dip, or no stored record, leaves the band out; it never shows an empty ring.
    lead_ring = panelring.for_dip(data, st["lead_dip"]) if st.get("lead_dip") else None
    # In its smallest form (the page's budget is tight): the stored counts, score and status in words; the script
    # draws the full ring from the same record.
    ring = panelring.summary({**lead_ring, "uid": "home"}, st["lead_dip"]) if lead_ring else ""
    probes_only = ((data.get("run_ctx") or {}).get(run) or {}).get("probes_only")
    sky = (_placed("skyyears", data, _cat_source(data)) + _placed("timeline", data, _cat_source(data))) if data.get("catalogue") else ""
    bands = [
        head,
        gal,
        _temps(data),
        _band("lineup", t("home.band.lineup", "The showcase planets, to scale"), lineup, eyebrow=t("home.band.lineup.e", "Planets to scale")) if lineup else "",
        _band("fold", t("home.band.fold", "How a planet hides in the noise"), fold, eyebrow=t("home.band.fold.e", "Real data"),
              more=f'<p class="bandmore"><a href="#/methods?ch=transit"{ik("home.more.transit")}>{t("home.more.transit", "How transits are found ›")}</a></p>') if fold else "",
        _band("panel", t("home.band.panel", "Who reviews a dip"), ring, eyebrow=t("home.band.panel.e", "The panel"),
              more=f'<p class="bandnote"{ik("honesty.attribution")}>{e(ATTRIBUTION)}</p>' + (f'<p class="bandnote"{ik("honesty.probes_only")}>{e(PROBES_ONLY)}</p>' if probes_only else "")) if ring else "",
        _band("sky", t("home.band.sky", "Every known planet's star, by the year it was found"), sky, eyebrow=t("home.band.sky.e", "The sky"),
              more=f'<p class="bandmore"><a href="#/sky"{ik("home.more.sky")}>{t("home.more.sky", "Explore the sky ›")}</a></p>') if sky else "",
        _counters_band(data),
    ]
    N_("home.proof", "What the reference run shows")
    proof = "".join(f'<div><b style="--c:{p["colour"]}">{e(p["big"])}</b><span>{p.get("html") or e(p["text"])}</span></div>' for p in st["proof"])
    ref = (th("home.refcheck", "The reference check: {planet}, a known planet, found again in run {run}", planet=planet, run=run) if planet
           else th("home.refrun", "The reference run: {run}", run=run))
    rk = ik("home.refcheck", planet=planet, run=run) if planet else ik("home.refrun", run=run)
    bands.append(f'<section class="refcheck" id="band-refcheck" aria-labelledby="h-refcheck"><div class="secthead"><h2 id="h-refcheck"{rk}>{ref}</h2></div>'
                 f'<div class="proof" role="list" aria-label="What the reference run shows"{ka(aria_label="home.proof")}>{proof.replace("<div>", "<div role=" + chr(34) + "listitem" + chr(34) + ">")}</div></section>')
    sweep = sweep_line(data.get("sweep"))
    bands.append(f'<div class="homesweep" id="band-sweep">{sweep}</div>' if sweep else "")
    bands.append(_do_here())
    bands.append(_honest(data))
    bands.append(learn_card() if with_view else "")
    return "\n      ".join(b for b in bands if b)


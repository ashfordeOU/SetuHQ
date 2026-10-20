"""Everything that dims (#/variables): the sweep's variability and event catalogue on the site.

The data is ``docs/sweep/catalogue.json`` (:func:`exoplan.sweep.build_catalogue`), copied beside the app as
``assets/data/variables.json`` and fetched the first time the page, a star page, Mission Control or the search
needs it. The page is built from :func:`sweep_meta`, and its script's payload carries only
:func:`sweep_payload`: the counts, the class labels, the sources and the contributors, so the Overview's counter
needs no fetch. The rule text and the nulls are in the built HTML and in the fetched file, not in the payload.

Every number here is read from that file. Nothing is extrapolated: the counter says how many stars were
searched, not how many could be. A class is a light-curve classification by a stated rule, never a
confirmation; a planet candidate is a candidate, unconfirmed, and the page puts the same rules' count on
flux-inverted copies of the same stars beside every class.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from exoplan.names import ATTRIBUTION
from exoplan.variables import LS_EDGE_FRACTION

DEFAULT_SWEEP = "docs/sweep/catalogue.json"
RULE_CHECK_JSON = "variability_rule_check.json"  # scripts/variability_rule_check.py, beside the catalogue
VARIABLES_JSON = "assets/data/variables.json"
# Class colours from the system tokens, distinct in both themes and at least 3:1 on the page in each: yellow for
# a candidate, purple for a binary, coral for a flare, green for a variable star. A class that does not exceed
# its null in the catalogue is drawn grey instead (NOISE_COLOUR), whatever its name.
CLASS_COLOUR = {"planet_candidate": "var(--yellow)", "eclipsing_binary": "var(--magenta)", "flare": "var(--coral)",
                "variable": "var(--green)", "systematic": "var(--ink-3)", "unclassified": "var(--line-3)"}
NOISE_COLOUR = "var(--ink-3)"
NOISE_LIKE = "not distinguishable from noise in this slice"
SKY_SWEEP_COLOUR = "#30D158"
SKY_FOUND_COLOUR = "#FFB340"
SORTS = [("class", "Class"), ("tic", "TIC"), ("time", "Time"), ("depth", "Depth or amplitude"), ("confidence", "Confidence")]
CONF_ORDER = ["high", "medium", "low", "n/a"]


def load_sweep(path: str | Path | None = DEFAULT_SWEEP) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def _slice_line(src: dict) -> str:
    kinds = set(src.get("kinds") or [])
    sen, prb = bool(kinds & {"claude", "claude_code"}), bool(kinds & {"simulated"})
    who = "Probes and Sentinels" if sen and prb else "Sentinels only" if sen else "Probes only"
    return (f"Sector {src['sector']}: {src.get('searched', 0):,} of the {src.get('targets_in_sector') or 0:,} SPOC 2-minute targets "
            f"searched ({who}; by {src['name']})")


def class_view(cat: dict) -> dict:
    """Per class: real, null, excess and its interval, whether it is noise-like, its colour and its place in the
    order (classes that exceed their null first, then the noise-like ones, then unclassified)."""
    vs = ((cat["counts"].get("null") or {}).get("by_class")) or {}
    noise = set((cat["counts"].get("null") or {}).get("noise_like") or [])
    ids = [k["id"] for k in cat["classes"]]
    order = [c for c in ids if c not in noise and c != "unclassified"] + [c for c in ids if c in noise] + ["unclassified"]
    colours = {c: (NOISE_COLOUR if c in noise else CLASS_COLOUR[c]) for c in ids}
    return {"vs": vs, "noise_like": sorted(noise), "order": order, "colours": colours}


def sweep_meta(cat: dict | None, catalogue: dict | None = None, path: str = DEFAULT_SWEEP) -> dict | None:
    """The small part of the sweep catalogue the page carries: counts with each class against its null, classes
    with rules, sources, contributors, the slice in words, star names for TICs the planet catalogue knows, and
    the Sky layer's points."""
    if cat is None:
        return None
    from exoplan.catalogue import tic_names

    view = class_view(cat)
    cov = cat.get("coverage") or []
    tics = sorted({r["tic"] for r in cov})
    names = tic_names(catalogue, tics) if catalogue else {}
    real = {c for c in view["order"] if c not in view["noise_like"] and c not in ("systematic", "unclassified")}
    found = {(e["tic"], e["sector"]) for e in cat.get("entries") or [] if e["class"] in real}
    sky = [[r["ra"], r["dec"], 1 if (r["tic"], r["sector"]) in found else 0] for r in cov
           if r.get("status") == "searched" and r.get("ra") is not None and r.get("dec") is not None]
    # The coherent-variable rule's reach, from the catalogue and from the synthetic check beside it.
    var = [e for e in cat.get("entries") or [] if e.get("kind") == "variability"]
    why = [e.get("why") or "" for e in var if e["class"] == "unclassified"]
    tops = sorted(LS_EDGE_FRACTION * e["half_period_max_days"] for e in var if e.get("half_period_max_days"))
    check_path = Path(path).parent / RULE_CHECK_JSON if path else None
    coherence = {"coherent": sum(1 for e in var if e["class"] == "variable"),
                 "not_tested": sum("coherence not tested" in w for w in why),
                 "grid_edge": sum("longest period searched" in w for w in why),
                 "incoherent": sum("not a coherent period" in w for w in why),
                 "testable_max_days": round(tops[len(tops) // 2], 1) if tops else None,
                 "check": json.loads(check_path.read_text()) if check_path and check_path.exists() else None}
    return {"path": path, "generated_at": cat.get("generated_at", ""), "counts": cat["counts"], "classes": cat["classes"],
            "colours": view["colours"], "order": view["order"], "noise_like": view["noise_like"], "vs": view["vs"],
            "noise_text": NOISE_LIKE, "sky_found_classes": sorted(real),
            "sources": cat.get("sources") or [], "contributors": cat.get("contributors") or [],
            "slices": [_slice_line(s) for s in cat.get("sources") or []], "tic_names": names, "sky": sky, "n_sky": len(sky),
            "sorts": [k for k, _ in SORTS], "sort_labels": dict(SORTS), "json": VARIABLES_JSON, "coherence": coherence}


def sweep_payload(meta: dict) -> dict:
    """What the page's script needs of :func:`sweep_meta`, embedded in every page. The rest is read at build
    time or comes with the lazily fetched catalogue (variables.json): the Sky points (drawn into the SVG), the
    per-class nulls and comparisons, and each class's rule, confidence and null text."""
    drop = ("sky", "vs", "coherence")
    return {**{k: v for k, v in meta.items() if k not in drop},
            "counts": {k: v for k, v in meta["counts"].items() if k != "null"},
            "classes": [{"id": c["id"], "label": c["label"]} for c in meta["classes"]]}


def variables_filter(cat: dict, v: dict) -> list[str]:
    """The reference filter the page's JavaScript must match (tests compare them): classes, confidences, a TIC
    or text query, the TOI-match toggle; returns entry ids in catalogue order."""
    q = (v.get("q") or "").strip().lower().removeprefix("tic").strip()
    cls, conf = set(v.get("cls") or []), set(v.get("conf") or [])
    out = []
    for e in cat["entries"]:
        if cls and e["class"] not in cls:
            continue
        if conf and e["confidence"] not in conf:
            continue
        if v.get("toi") and not e.get("toi_match"):
            continue
        if q and q not in str(e["tic"]) and q not in (e.get("toi_match") or "").lower() and not any(q in c["name"].lower() for c in e.get("credit") or []):
            continue
        out.append(e["id"])
    return out


def excess_text(v: dict) -> str:
    """'+41 (95%: +12 to +70)' or '+2 (95%: −3 to +7)'."""
    sign = lambda x: f"+{x:,.0f}" if x > 0 else f"−{-x:,.0f}" if x < 0 else "0"  # noqa: E731
    return f"{sign(v['excess'])} (95%: {sign(v['lo'])} to {sign(v['hi'])})"


def overview_counter(meta: dict | None, app_href: str = "") -> str:
    """The Overview's live, honest counter: every figure from the committed sweep catalogue, each class beside
    its own null."""
    e = html.escape
    if not meta:
        return ""
    c = meta["counts"]
    labels = {k["id"]: k["label"] for k in meta["classes"]}
    big = [(c["stars_searched"], "stars searched"), (c["star_sectors_searched"], "star-sectors"), (c["dips_reviewed"], "dips reviewed"),
           (c["entries"], "catalogue entries")]
    tiles = "".join(f'<div role="listitem"><b class="mono">{n:,}</b><span>{e(t)}</span></div>' for n, t in big)
    vs = meta.get("vs") or {}
    rows = ""
    for k in meta["order"]:
        v = vs.get(k)
        note = ""
        if v and k != "unclassified":
            note = (f'<em class="mono">null {v["null"]:,} · excess {e(excess_text(v))}</em>'
                    + (f'<em class="vanoise">{e(NOISE_LIKE)}</em>' if k in meta["noise_like"] else ""))
        rows += (f'<li><a href="{app_href}#/variables?class={k}" style="--c:{meta["colours"][k]}"><i aria-hidden="true"></i><span>{e(labels[k])}</span>'
                 f'<b class="mono">{c["by_class"][k]:,}</b>{note}</a></li>')
    slices = "; ".join(e(s) for s in meta["slices"])
    n_null = (c.get("null") or {}).get("searches", 0)
    real = [labels[k] for k in meta["order"] if k not in meta["noise_like"] and k != "unclassified"]
    return f"""<section class="sweepctr card" aria-labelledby="h-sweepctr">
        <div class="sweephead"><h2 id="h-sweepctr">The sweep so far</h2><a class="btn" href="{app_href}#/variables">Everything that dims ›</a></div>
        <p class="muted">Every star searched, every dip kept and classified, nothing thrown away. So far: {slices}. A first slice, not the sky.</p>
        <div class="sweeptiles" role="list" aria-label="Sweep figures">{tiles}</div>
        <ul class="sweepcls" aria-label="Catalogue entries by class, each against its null">{rows}</ul>
        <p class="small">Read from {e(meta['path'])} (built {e(meta['generated_at'][:16].replace('T', ' '))} UTC); nothing is extrapolated. {f"Each class is set against its own null on the same {n_null:,} star-sectors (what its rule finds where its signal cannot be; the rules table says which). " + (f"In this slice only {e(', '.join(real))} {'exceeds its null' if len(real) == 1 else 'exceed their nulls'}; the rest are {e(NOISE_LIKE)}. "
       if real else f"In this slice no class exceeds its null: every one is {e(NOISE_LIKE)}. ") if n_null else ""}No entry is a new planet.</p>
      </section>"""


def sky_layer_svg(meta: dict | None) -> str:
    """The sweep's coverage on the Sky map: one dot per searched star-sector, amber where it has an entry in a
    class that exceeds its null."""
    if not meta or not meta.get("sky"):
        return ""
    from exoplan.story import mollweide

    plain, found = [], []
    for ra, dec, f in meta["sky"]:
        x, y = mollweide(ra, dec)
        (found if f else plain).append(f"M{x:.1f} {y:.1f}h0")
    return (f'<g class="covl" data-layer="sweep" style="display:none">'
            f'<path d="{"".join(plain)}" stroke="{SKY_SWEEP_COLOUR}" stroke-width="3" stroke-linecap="round" stroke-opacity=".8"/>'
            f'<path d="{"".join(found)}" stroke="{SKY_FOUND_COLOUR}" stroke-width="5" stroke-linecap="round"/></g>')


def sky_chip(meta: dict | None) -> str:
    if not meta or not meta.get("sky"):
        return ""
    n = len(meta["sky"])
    return (f'<button class="chip" type="button" data-cov="sweep" aria-pressed="false"><i style="background:{SKY_SWEEP_COLOUR}"></i>'
            f'exoplan sweep ({n:,} star-sectors)</button>')


def tabs(active: str) -> str:
    """The two catalogues, as a tab bar at the top of each: known planets, and everything that dims."""
    items = [("catalogue", "Known planets"), ("variables", "Everything that dims")]
    return ('<nav class="cattabs" aria-label="Catalogues">'
            + "".join(f'<a href="#/{k}"{" aria-current=page" if k == active else ""}>{html.escape(v)}</a>' for k, v in items) + "</nav>")


def variables_section(meta: dict | None, eyebrow: str) -> str:
    e = html.escape
    if not meta:
        return (f'<header>{eyebrow}<h1 class="lead-h" id="h-variables" tabindex="-1">Everything that dims.</h1>'
                f'<p>The sweep catalogue ({DEFAULT_SWEEP}) is not in this build. Run <code>exoplan sweep</code>.</p></header>{tabs("variables")}')
    c = meta["counts"]
    vs = meta.get("vs") or {}
    labels = {k["id"]: k for k in meta["classes"]}
    noise = set(meta["noise_like"])
    chips = "".join(f'<button class="chip vachip" type="button" data-vc="{k}" aria-pressed="false" style="--c:{meta["colours"][k]}"><i aria-hidden="true"></i>'
                    f'{e(labels[k]["label"])} <span class="mono">{c["by_class"][k]:,}'
                    + (f' · null {vs[k]["null"]:,}' if k in vs and k != "unclassified" else "") + "</span></button>" for k in meta["order"])
    confs = "".join(f'<button class="chip" type="button" data-vf="{k}" aria-pressed="false">{e(k)}</button>' for k in CONF_ORDER)
    sorts = "".join(f'<option value="{k}">{e(v)}</option>' for k, v in SORTS)

    def rule_row(k):
        cl, v = labels[k], vs.get(k)
        nul = (f'<td class="num mono">{v["null"]:,}</td><td>{e(cl.get("null", ""))}</td><td class="num mono">{e(excess_text(v))}'
               + (f'<br><span class="vanoise">{e(NOISE_LIKE)}</span>' if k in noise else "") + "</td>") if v and k != "unclassified" else '<td class="num">—</td><td>—</td><td class="num">—</td>'
        return (f'<tr><th scope="row"><span class="vacls" style="--c:{meta["colours"][k]}"><i aria-hidden="true"></i>{e(cl["label"])}</span></th>'
                f'<td>{e(cl["rule"])}</td><td>{e(cl["confidence"])}</td><td class="num mono">{v["real"] if v else c["by_class"][k]:,}</td>{nul}</tr>')

    rules = "".join(rule_row(k) for k in meta["order"])
    comps = "".join(f'<tr><th scope="row">{e(x["label"])}</th><td class="num mono">{x["real"]:,}</td><td class="num mono">{x["null"]:,}</td>'
                    f'<td class="num mono">{e(excess_text(x))}</td><td class="num mono">{x["stars_real"]:,} / {x["stars_null"]:,}</td>'
                    f'<td class="num mono">{x["mcnemar_p"]:.3g}</td><td>{"exceeds its null" if x["significant"] else e(NOISE_LIKE)}</td></tr>'
                    for x in (c.get("null") or {}).get("comparisons") or [])
    unc = (c.get("null") or {}).get("uncompared") or {}
    uncompared = ("Not compared, for want of a null of the same kind: "
                  + ", ".join(f"{n:,} {labels[k]['label'].lower()} entries of another kind" for k, n in unc.items()) + ".") if unc else ""
    contributors = "".join(f'<li><b>{e(x["name"])}</b> <span class="muted">{x["star_sectors"]:,} star-sectors'
                           + (f' · attested by {e(", ".join(x["attested_by"]))}' if x.get("attested_by") else "")
                           + (f' · {x["duplicates_not_credited"]:,} identical re-submissions not credited' if x.get("duplicates_not_credited") else "")
                           + (f' · {x["superseded"]:,} earlier searches since replaced by a later one (kept as provenance)' if x.get("superseded") else "")
                           + f' · {e(", ".join(x["sources"]))}</span></li>' for x in meta["contributors"])
    ns = c.get("not_searched") or {}
    n_null = (c.get("null") or {}).get("searches", 0)
    pc = vs.get("planet_candidate")
    verdict = ""
    if pc:
        verdict = (f' The planet-candidate rule found {pc["real"]:,} on the real light curves and {pc["null"]:,} on flux-inverted copies of the '
                   f'same stars (dips turned into bumps, so real dips cannot pass): an excess of {excess_text(pc)}. '
                   + ("They are not distinguishable from noise in this slice, so they are not presented as candidates."
                      if "planet_candidate" in noise else "The excess is what a follow-up would look at first.")
                   + f' {c.get("planet_candidates_matching_toi", 0):,} match a known TOI.')
    shape = (c.get("null") or {}).get("flare_shape") or {}
    shape_txt = (f' Of the {sum(shape.values()):,} flare-class brightenings, {shape.get("fast_rise", 0):,} rise faster than they decay and '
                 f'{shape.get("slow_rise", 0):,} the other way ({shape.get("equal", 0):,} equal); real flares rise fast, noise has no preferred '
                 'direction.') if shape and sum(shape.values()) else ""
    coh = meta.get("coherence") or {}
    coh_txt = (f' Of its periodogram peaks not at a binary\'s period, {coh.get("coherent", 0):,} are coherent; unclassified are '
               f'{coh.get("not_tested", 0):,} longer than a half can test (coherence not tested), {coh.get("grid_edge", 0):,} at the '
               f'edge of the period grid and {coh.get("incoherent", 0):,} that wander between halves.') if any(coh.get(k) for k in ("coherent", "not_tested", "grid_edge", "incoherent")) else ""
    case = ((coh.get("check") or {}).get("cases") or {}).get("sinusoid_in_strong_red_noise")
    if case and coh.get("testable_max_days"):
        chk = coh["check"]
        coh_txt += (f' Limits: it finds a {chk["sinusoid_ppm"]:,.0f} ppm sinusoid in strong red noise only {case["variable"]}/{chk["n"]} '
                    f'times ({chk["script"]}), and cannot test periods longer than about {coh["testable_max_days"]:g} d in one sector.')
    return f"""<header class="headrow">
        <div>{eyebrow}<h1 class="lead-h" id="h-variables" tabindex="-1">Everything that dims.<br><span class="grey">{c['entries']:,} entries, none thrown away.</span></h1>
        <p>Every consensus dip of the panel, every brightening and every star's variability from the sweep, each classified by a stated rule, with its confidence, its cues and its provenance: the marks, the weights and the Sentinels' own words. {e(ATTRIBUTION)}</p></div>
      </header>
      {tabs("variables")}
      <p class="note"><b>A first slice, stated plainly.</b> {"; ".join(e(s) for s in meta["slices"])}. {c['stars_searched']:,} stars searched, {c['star_sectors_searched']:,} star-sectors, {c['dips_reviewed']:,} consensus dips reviewed{f", {sum(ns.values()):,} star-sectors recorded but not searched ({ns.get('no_data', 0)} no data, {ns.get('error', 0)} errors, {ns.get('pending', 0)} pending)" if sum(ns.values()) else ""}. This catalogue is separate from the discovery feed. <b>Nothing here is a new or confirmed planet.</b> A class is what the light curve's cues suggest; there is no pixel or centroid check, so a blended binary can look like anything.{e(verdict)}</p>
      <p class="note"><b>Each class against its own null</b>, measured on the same {n_null:,} star-sectors: what its rule finds where its signal cannot be. Dips: the flux turned upside down (a real dip becomes a bump; a real flare or pulsation maximum becomes a dip, so this null is not empty of real signals). Flares: downward events with the real dips masked. Variability: a red-noise copy of the star (AR(1) fitted to its bins) through the same rule, which needs the same best period (within 10%) in both halves of the light curve.{e(coh_txt)} Kind is compared with kind, star-sector is the unit: the 95% interval is a paired bootstrap over star-sectors, beside McNemar's test. A class that does not pass both is {e(NOISE_LIKE)}: {e(", ".join(labels[k]["label"] for k in meta["order"] if k in noise) or "none")}.{e(shape_txt)}</p>
      <section class="card vafilters" aria-label="Filters">
        <label class="vasearch"><span class="sr">Find a TIC, a TOI or a contributor</span><input type="search" id="vaq" placeholder="Find a TIC, a TOI or a contributor" autocomplete="off" inputmode="search"></label>
        <div class="chips" id="vaclasses" role="group" aria-label="Class (entries · null)">{chips}</div>
        <div class="varow"><div class="chips" id="vaconf" role="group" aria-label="Confidence"><span class="valab">Confidence</span>{confs}</div>
          <button class="chip" type="button" id="vatoi" aria-pressed="false">Matches a known TOI</button>
          <label class="vasort"><span>Sort</span><select id="vasort">{sorts}</select></label></div>
        <div class="ctbar"><p class="mono" id="vacount" role="status" aria-live="polite">Loading the sweep catalogue…</p>
          <button class="btn" type="button" id="vareset">Clear filters</button>
          <button class="btn" type="button" id="vacsv">Download CSV of this view</button>
          <a class="btn" href="{VARIABLES_JSON}" download="exoplan-everything-that-dims.json">Download the catalogue (JSON)</a></div>
      </section>
      <section class="card vaobj" id="vaobj" aria-labelledby="h-vaobj" hidden><h2 id="h-vaobj" tabindex="-1">TIC</h2><div id="vaobjbody"></div></section>
      <div class="valist" id="valist" aria-label="Entries"></div>
      <p class="ctempty" id="vaempty" role="status" hidden>No entries match these filters. <a href="#/variables">Clear filters</a></p>
      <div class="vamore"><button class="btn" type="button" id="vamore" hidden>Show more</button></div>
      <section class="card" aria-labelledby="h-varules" style="display:grid;gap:8px">
        <h2 id="h-varules">The rules, and each class against its null</h2>
        <p class="muted" style="margin:0;font-size:13px">First match wins, in this order: systematic, eclipsing binary, variable, then planet candidate; a brightening is a flare unless it is systematic. The rules are in src/exoplan/variables.py and are re-applied to every contributed entry on ingest. Excess: real minus null over the same star-sectors, with a 95% interval from a paired bootstrap over star-sectors (10,000 resamples). The second table has every comparison, kind by kind.</p>
        <div class="tablewrap" tabindex="0" role="region" aria-label="Classification rules and nulls"><table class="vatable"><thead><tr><th scope="col">Class</th><th scope="col">Rule</th><th scope="col">Confidence</th><th scope="col" class="num">Real</th><th scope="col" class="num">Null</th><th scope="col">Null measured on</th><th scope="col" class="num">Excess</th></tr></thead><tbody>{rules}</tbody></table></div>
        <div class="tablewrap" tabindex="0" role="region" aria-label="Every comparison with its null"><table class="vatable"><thead><tr><th scope="col">Comparison</th><th scope="col" class="num">Real</th><th scope="col" class="num">Null</th><th scope="col" class="num">Excess (95%)</th><th scope="col" class="num">Star-sectors with any: real / null</th><th scope="col" class="num">McNemar p</th><th scope="col">In this slice</th></tr></thead><tbody>{comps}</tbody></table></div>
        <p class="small">{e(uncompared)}</p>
      </section>
      <section class="card" aria-labelledby="h-vacred" style="display:grid;gap:8px">
        <h2 id="h-vacred">Who searched</h2>
        <ul class="vacred">{contributors}</ul>
        <p class="small">Anyone can add a sector with their own reviewers and be credited by a name they choose: see CONTRIBUTING.md (keys stay in your environment, never in a bundle). A bundle is sealed with content hashes, not signed; ingest searches a sample again and credits only searches that are new.</p>
      </section>"""


VARIABLES_CSS = r"""
/* ---------- everything that dims (#/variables) and the sweep counter ---------- */
#route-variables{grid-template-columns:minmax(0,1fr)}
#route-variables>*{min-width:0}
.cattabs{display:inline-flex;flex-wrap:wrap;gap:2px;padding:3px;border-radius:999px;background:var(--panel-2);border:1px solid var(--line);justify-self:start;max-width:100%}
.cattabs a{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:999px;color:var(--ink-2);text-decoration:none;font-weight:500;font-size:14px}
.cattabs a[aria-current="page"]{background:var(--seg-bg);color:var(--seg-ink)}
.vafilters{display:grid;gap:12px}
.vasearch input{width:100%;min-height:48px;padding:0 16px;border-radius:14px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 16px var(--sans)}
.vafilters .chip,.vafilters .btn,.vasort select{min-height:44px}
.vachip i,.vacls i,.sweepcls i{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--c);margin-right:6px;flex:none}
.vafilters .chip .mono{color:var(--ink-3);margin-left:4px;font-size:12px}
.vafilters .chip[aria-pressed="true"] .mono{color:inherit;opacity:.7}
.varow{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px}
.valab{align-self:center;font-size:12px;color:var(--ink-3);margin-right:2px}
.vasort{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-3)}
.vasort select{padding:0 10px;border-radius:12px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 14px var(--sans)}
.valist{display:grid;gap:10px}
.vaent{display:grid;gap:6px;padding:14px 16px;border:1px solid var(--line);border-left:3px solid var(--c);border-radius:16px;background:var(--glass-2);min-width:0}
.vaent:target,.vaent.sel{outline:2px solid var(--blue);outline-offset:2px}
.vaent header{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px}
.vacls{display:inline-flex;align-items:center;font-weight:600}
.vaent header a{display:inline-flex;align-items:center;min-height:44px}
.vaent p{margin:0;font-size:13.5px;color:var(--ink-2);overflow-wrap:anywhere}
.vanum{font-size:12.5px!important;color:var(--ink)!important}
.vaent details summary{display:flex;align-items:center;gap:8px;min-height:44px;cursor:pointer;font-size:13px;font-weight:600;list-style:none;color:var(--cyan)}
.vaent details summary::-webkit-details-marker{display:none}
.vaent details summary::before{content:"›";display:inline-block;transition:transform .2s;color:var(--ink-3)}
.vaent details[open] summary::before{transform:rotate(90deg)}
.vaent details>div{display:grid;gap:10px;padding-top:4px}
.vaent h3{margin:0;font-size:12px;font-weight:600;color:var(--ink-3);text-transform:uppercase;letter-spacing:.04em}
.vatable{width:100%;border-collapse:collapse;font-size:13px}
.vatable th,.vatable td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.vatable td.num,.vatable th.num{text-align:right;font-variant-numeric:tabular-nums}
.vatable thead th{font-size:12px;color:var(--ink-3);font-weight:500}
.vawords{margin:0;padding:10px 12px;border-radius:12px;background:var(--cyan-soft);font-size:13.5px;color:var(--ink)}
.vawords cite{display:block;font-style:normal;font-size:12px;color:var(--ink-3);margin-top:4px}
.vaprov{font:12px/1.5 var(--mono);color:var(--ink-3);overflow-wrap:anywhere}
.vacredit{font-size:12.5px;color:var(--ink-3)}
.vacredit b{color:var(--ink);font-weight:600}
.vamore{display:flex;justify-content:center}
.vamore .btn{min-height:44px}
.vaobj{display:grid;gap:10px;grid-template-columns:minmax(0,1fr)}
.vaobj[hidden]{display:none}
.vaobj>*{min-width:0}
.vaobj p{overflow-wrap:anywhere}
.vaall{display:inline-flex;align-items:center;min-height:44px}
.vaobj h2{margin:0;font-size:22px}
.vaobj h2:focus{outline:none}
.vaobjgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:8px 18px;margin:0}
.vaobjgrid div{display:grid;gap:2px;align-content:start}
.vaobjgrid dt{font-size:12px;color:var(--ink-3)}
.vaobjgrid dd{margin:0;font:500 14px var(--mono);overflow-wrap:anywhere}
.vacred{list-style:none;margin:0;padding:0;display:grid;gap:6px;font-size:14px}
.sweepctr{display:grid;gap:12px}
.sweephead{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px}
.sweephead h2{margin:0;font-size:20px}
.sweephead .btn{min-height:44px}
.sweepctr>p{margin:0}
.sweeptiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:1px;background:var(--line);border-radius:16px;overflow:hidden}
.sweeptiles>div{background:var(--panel);padding:14px 16px}
.sweeptiles b{display:block;font-size:30px;font-weight:600;letter-spacing:-.02em;line-height:1.1}
.sweeptiles span{font-size:13px;color:var(--ink-2)}
.sweepcls{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:6px}
.sweepcls a{display:grid;grid-template-columns:8px minmax(0,1fr) auto;align-items:center;column-gap:10px;row-gap:0;min-height:52px;padding:6px 14px;border:1px solid var(--line);border-radius:12px;color:var(--ink);text-decoration:none;font-size:14px}
.sweepcls a:hover{border-color:var(--line-3)}
.sweepcls i{margin:0}
.sweepcls b{font-size:17px;font-weight:600;text-align:right}
.sweepcls em{grid-column:2 / 4;font-style:normal;font-size:11.5px;color:var(--ink-3)}
.vanoise{font-style:normal;font-size:11.5px;color:var(--ink-2)}
.tag.vanoisetag{color:var(--ink-2);border-style:dashed}
.route>header .eyebrow .parent a{display:inline-flex;align-items:center;min-height:44px}
.stsweep[hidden]{display:none}
@media (prefers-reduced-motion: reduce){.vaent details summary::before{transition:none}}
@media (max-width:699.98px){
  .cattabs a{padding:0 14px}
  .vaent{padding:12px}
  .vatable{font-size:12px}
}
"""


VARIABLES_JS = r"""
// ---------- everything that dims: the sweep catalogue (#/variables) ----------
const VA = D.sweep || null;
const VA_NOISE = new Set(VA ? VA.noise_like : []);
// A class that does not exceed its null keeps its rule's name but is not presented as a finding: the planet
// candidates become "planet-candidate rule" until they exceed their control.
const VA_LABEL = VA ? Object.fromEntries(VA.classes.map(c => [c.id, c.id === 'planet_candidate' && VA_NOISE.has(c.id) ? 'Planet-candidate rule' : c.label])) : {};
// Classes that exceed their null first, then the noise-like ones, then unclassified (sweep_meta's order).
const VA_CLASSES = VA ? VA.order : [];
const VA_CONF = ['high', 'medium', 'low', 'n/a'];
const va = {E: null, C: null, loading: null, view: null, shown: 60, byId: {}, byTic: {}, cov: {}, bound: false, rendered: false};
function vaLoad(){
  if (!VA) return Promise.reject(new Error('no sweep'));
  if (!va.loading) va.loading = fetch(VA.json).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(C => {
    va.C = C; va.E = C.entries;
    for (const e of va.E){ va.byId[e.id] = e; (va.byTic[e.tic] = va.byTic[e.tic] || []).push(e); }
    for (const r of C.coverage) (va.cov[r.tic] = va.cov[r.tic] || []).push(r);
    return C;
  });
  return va.loading;
}
// URL: class, conf (lists), q, toi=1, sort, tic, id. Defaults are left out.
function decodeVarView(p){
  const cl = (p.get('class') || '').split(','), cf = (p.get('conf') || '').split(',');
  const tic = /^\d{1,12}$/.test(p.get('tic') || '') ? Number(p.get('tic')) : null;
  return {cls: VA_CLASSES.filter(c => cl.includes(c)), conf: VA_CONF.filter(c => cf.includes(c)), q: (p.get('q') || '').slice(0, 80),
          toi: p.get('toi') === '1', sort: VA && VA.sorts.includes(p.get('sort')) ? p.get('sort') : 'class', tic, id: (p.get('id') || '').slice(0, 120) || null};
}
function encodeVarView(v){
  const out = [];
  if (v.cls.length) out.push('class=' + v.cls.join(','));
  if (v.conf.length) out.push('conf=' + v.conf.map(encodeURIComponent).join(','));
  if (v.q) out.push('q=' + encodeURIComponent(v.q));
  if (v.toi) out.push('toi=1');
  if (v.sort !== 'class') out.push('sort=' + v.sort);
  if (v.tic !== null) out.push('tic=' + v.tic);
  if (v.id) out.push('id=' + encodeURIComponent(v.id));
  return out.join('&');
}
// The filter (tests compare it with everything.variables_filter in Python).
function vaFilter(E, v){
  let q = (v.q || '').trim().toLowerCase(); if (q.startsWith('tic')) q = q.slice(3).trim();
  const cls = new Set(v.cls), conf = new Set(v.conf);
  return E.filter(e => (!cls.size || cls.has(e.class)) && (!conf.size || conf.has(e.confidence)) && (!v.toi || e.toi_match)
    && (!q || String(e.tic).includes(q) || (e.toi_match || '').toLowerCase().includes(q) || (e.credit || []).some(c => c.name.toLowerCase().includes(q))));
}
function vaSort(rows, key){
  const by = {class: e => [VA_CLASSES.indexOf(e.class), e.tic, e.t_center || 0], tic: e => [e.tic, e.t_center || 0], time: e => [e.t_center || 0, e.tic],
    depth: e => [-(e.depth_ppm ?? e.amplitude_ppm ?? -1e99), e.tic], confidence: e => [VA_CONF.indexOf(e.confidence), VA_CLASSES.indexOf(e.class), e.tic]}[key];
  return rows.slice().sort((a, b) => { const x = by(a), y = by(b); for (let i = 0; i < x.length; i++){ if (x[i] < y[i]) return -1; if (x[i] > y[i]) return 1; } return 0; });
}
const vaNum = (x, d) => x === null || x === undefined ? '—' : Number(x).toLocaleString('en-GB', {maximumFractionDigits: d, minimumFractionDigits: d});
const vaTicHref = (tic, id) => `#/variables?tic=${tic}` + (id ? '&id=' + encodeURIComponent(id) : '');
function vaFigures(e){
  const bits = e.kind === 'variability' ? ['whole sector'] : [`${esc(e.time_unit || 'BTJD')} ${vaNum(e.t_center, 3)}`];
  if (e.kind === 'variability') bits.push(`period ${vaNum(e.period_days, 4)} d`, `semi-amplitude ${vaNum(e.amplitude_ppm, 0)} ppm`);
  else {
    bits.push(`${vaNum(e.duration_hours, 1)} h`);
    if (e.kind === 'dip') bits.push(`${vaNum(e.depth_ppm, 0)} ppm deep`, `SNR ${vaNum(e.snr, 1)}`); else bits.push(`+${vaNum(e.amplitude_ppm, 0)} ppm`, `${vaNum(e.peak_sigma, 1)}σ`);
    if (e.period_days) bits.push(`P ${vaNum(e.period_days, 4)} d (${e.n_transits || 0} transits)`);
  }
  return bits.join(' · ');
}
function vaCredit(e){ return `<p class="vacredit">Searched by ${(e.credit || []).map(c => `<b>${esc(c.name)}</b>`).join(', ') || 'not stored'}</p>`; }
function vaDetail(e){
  const kind = Object.fromEntries((e.panel || []).map(p => [p.id, p.kind]));
  const w = e.weights || {};
  const ids = Object.keys(w).sort();
  const marks = e.marks || [];
  const mrows = ids.map(id => { const ms = marks.filter(m => m[0] === id);
    return `<tr><th scope="row">${nameWithId(id)} ${kindTag(kind[id])}</th><td class="num mono">${vaNum(w[id], 2)}</td><td class="mono">${ms.length ? ms.map(m => `${vaNum(m[1], 3)}–${vaNum(m[2], 3)}${m[3] ? ' ✓' : ''}`).join('<br>') : 'no mark'}</td></tr>`; }).join('');
  const marksHTML = e.kind === 'dip' ? `<h3>Marks and weights</h3><div class="tablewrap" tabindex="0" role="region" aria-label="Marks by reviewer"><table class="vatable"><thead><tr><th scope="col">Reviewer</th><th scope="col" class="num">Weight</th><th scope="col">Marks (✓ counted)</th></tr></thead><tbody>${mrows}</tbody></table></div>`
    + (e.shares && Object.keys(e.shares).length ? `<p>Panel's weighted labels: ${Object.entries(e.shares).map(([k, v]) => `${esc(k.replace(/_/g, ' '))} ${Math.round(v * 100)}%`).join(' · ')}</p>` : '')
    : `<p>${esc(e.note || '')}</p>`;
  const sentinels = ids.filter(id => isSentinel(kind[id]));
  const words = (e.words || []).length ? `<h3>The Sentinels' own words</h3>` + e.words.map(x => `<blockquote class="vawords">${esc(x.rationale)}<cite>${esc(NAME(x.reviewer))} · ${esc(x.label.replace('_', ' '))}${x.reason ? ' · ' + esc(x.reason.replace(/_/g, ' ')) : ''}</cite></blockquote>`).join('')
    : (e.kind === 'dip' ? `<p class="muted">${sentinels.length ? 'The Sentinels left no words on this subject.' : 'No Sentinel reviewed this star: this sweep ran the Probes only, which give no reasons.'}</p>` : '');
  const flags = (e.flags || []).length ? `<p>Vetting flags: <span class="mono">${e.flags.map(esc).join(', ')}</span> · ${e.passed ? 'passed vetting' : 'failed vetting'}</p>` : (e.kind === 'dip' ? `<p>No vetting flags · ${e.passed ? 'passed vetting' : 'failed vetting'}</p>` : '');
  const prov = `<p class="vaprov">id ${esc(e.id)}${e.subject_id ? ' · subject ' + esc(e.subject_id) : ''}<br>light curve sha256 ${esc(e.file_sha256 || 'not stored')}<br>code ${esc(String(e.code || '').slice(0, 16))}… · config ${esc(String(e.config_sha256 || '').slice(0, 16))}…${(e.credit || []).map(c => `<br>source ${esc(c.source)}${c.bundle ? ' (bundle ' + esc(c.bundle) + ')' : ''}`).join('')}</p>`;
  return `<details><summary>Marks, weights, words and provenance</summary><div>${flags}${marksHTML}${words}<h3>Provenance</h3>${prov}</div></details>`;
}
function vaCard(e, sel){
  const toi = e.toi_match ? ` · matches TOI ${esc(e.toi_match)}${e.toi_disposition ? ' (' + esc(e.toi_disposition) + ')' : ''}` : '';
  const why = e.class === 'unclassified' ? esc(e.why || '') : (e.cues || []).map(c => esc(c.text)).join('; ');
  const unc = VA_NOISE.has(e.class) ? ` <span class="tag vanoisetag">${esc(VA.noise_text)}</span>` : e.class === 'planet_candidate' ? ' ' + UNC : '';
  return `<article class="vaent${sel ? ' sel' : ''}" id="va-${esc(e.id)}" style="--c:${VA.colours[e.class]}" aria-label="${esc(VA_LABEL[e.class])}, TIC ${e.tic}">
    <header><span class="vacls"><i aria-hidden="true"></i>${esc(VA_LABEL[e.class])}</span><span class="tag">confidence: ${esc(e.confidence)}</span>${unc}
      <a href="${vaTicHref(e.tic, e.id)}">TIC ${e.tic}</a><span class="muted">sector ${e.sector} · ${esc(e.kind)}${toi}</span></header>
    <p class="vanum mono">${vaFigures(e)}</p><p>${why}</p>${vaDetail(e)}${vaCredit(e)}</article>`;
}
function vaObject(tic, id){
  const box = $('#vaobj'), es = va.byTic[tic] || [], cov = va.cov[tic] || [];
  box.hidden = false;
  const name = (VA.tic_names || {})[tic];
  $('#h-vaobj').textContent = `TIC ${tic}` + (name ? ` · ${name}` : '');
  if (!cov.length){ $('#vaobjbody').innerHTML = `<p>TIC ${tic} is not in the sweep yet.</p><div class="pllinks"><a class="vaall" href="#/variables">All entries ›</a></div>`; return; }
  const r = cov[0], rej = r.rejected || {};
  const dl = [['Position (RA, Dec)', r.ra !== null && r.ra !== undefined ? `${vaNum(r.ra, 3)}°, ${vaNum(r.dec, 3)}°` : 'not stored'], ['TESS magnitude', vaNum(r.tmag, 2)],
    ['Sectors searched', cov.filter(x => x.status === 'searched').map(x => x.sector).join(', ') || 'none'], ['Searched by', cov.flatMap(x => x.searched_by).join(', ') || '—'],
    ['Light-curve points', vaNum(r.n_points, 0)], ['Consensus dips', vaNum(r.n_dips, 0)],
    ['Rejected', `${rej.below_consensus ?? 0} mark clusters below consensus · ${rej.failed_vetting ?? 0} dips failed vetting`],
    ['Known TOIs on this TIC', (r.tois || []).map(t => `${t.toi}${t.disposition ? ' (' + t.disposition + ')' : ''}`).join(', ') || 'none in the cached TOI table']];
  $('#vaobjbody').innerHTML = `<dl class="vaobjgrid">${dl.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`
    + (name ? `<div class="pllinks">${objLink('star', name, name + ' in the planet catalogue ›')}</div>` : '')
    + `<p class="small">${es.length} entr${es.length === 1 ? 'y' : 'ies'} below, every one shown. Light curve sha256 <span class="mono">${esc(r.file_sha256 || 'not stored')}</span>.</p><div class="pllinks"><a class="vaall" href="#/variables">All entries ›</a></div>`;
}
function vaApply(){
  if (!va.E || !va.view) return;
  const v = va.view;
  $$('#vaclasses [data-vc]').forEach(b => b.setAttribute('aria-pressed', String(v.cls.includes(b.dataset.vc))));
  $$('#vaconf [data-vf]').forEach(b => b.setAttribute('aria-pressed', String(v.conf.includes(b.dataset.vf))));
  $('#vatoi').setAttribute('aria-pressed', String(v.toi));
  if ($('#vaq').value !== v.q) $('#vaq').value = v.q;
  $('#vasort').value = v.sort;
  let tic = v.tic;
  if (tic === null && v.id && va.byId[v.id]) tic = va.byId[v.id].tic;
  if (tic !== null){ vaObject(tic, v.id); } else { $('#vaobj').hidden = true; }
  // Opening a TIC from a link moves the focus to its heading, so a keyboard or screen-reader user lands on it.
  const opened = tic !== null && va.lastTic !== tic;
  va.lastTic = tic;
  const rows = tic !== null ? vaSort(va.byTic[tic] || [], 'time') : vaSort(vaFilter(va.E, v), v.sort);
  va.rows = rows;
  const shown = tic !== null ? rows : rows.slice(0, va.shown);
  $('#valist').innerHTML = shown.map(e => vaCard(e, e.id === v.id)).join('');
  $('#vaempty').hidden = rows.length > 0 || tic !== null;
  $('#vamore').hidden = shown.length >= rows.length;
  $('#vamore').textContent = `Show ${Math.min(60, rows.length - shown.length)} more of ${rows.length - shown.length}`;
  $('#vacount').textContent = tic !== null ? `TIC ${tic}: ${rows.length} of ${va.E.length.toLocaleString('en-GB')} entries` : `Showing ${shown.length.toLocaleString('en-GB')} of ${rows.length.toLocaleString('en-GB')} matching · ${va.E.length.toLocaleString('en-GB')} entries in all`;
  if (v.id){ const el = document.getElementById('va-' + v.id); if (el){ const d = el.querySelector('details'); if (d) d.open = true; } }
  if (opened){ $('#h-vaobj').focus({preventScroll: true}); $('#vaobj').scrollIntoView({block: 'start'}); }
}
function syncVarURL(push){ if (current === 'variables' && va.view) setHash('#/variables' + (encodeVarView(va.view) ? '?' + encodeVarView(va.view) : ''), !!push); }
function vaSet(change){ va.view = {...va.view, ...change}; va.shown = 60; vaApply(); syncVarURL(true); }
function vaBind(){
  if (va.bound) return; va.bound = true;
  $('#vaclasses').addEventListener('click', e => { const b = e.target.closest('[data-vc]'); if (!b) return; const k = b.dataset.vc, on = va.view.cls.includes(k);
    vaSet({cls: VA_CLASSES.filter(c => c === k ? !on : va.view.cls.includes(c)), tic: null, id: null}); say($('#vacount').textContent); });
  $('#vaconf').addEventListener('click', e => { const b = e.target.closest('[data-vf]'); if (!b) return; const k = b.dataset.vf, on = va.view.conf.includes(k);
    vaSet({conf: VA_CONF.filter(c => c === k ? !on : va.view.conf.includes(c)), tic: null, id: null}); });
  $('#vatoi').addEventListener('click', () => vaSet({toi: !va.view.toi, tic: null, id: null}));
  $('#vasort').addEventListener('change', e => vaSet({sort: e.target.value}));
  let qt = null;
  $('#vaq').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { va.view = {...va.view, q: e.target.value.slice(0, 80), tic: null, id: null}; va.shown = 60; vaApply(); syncVarURL(false); }, 200); });
  $('#vareset').addEventListener('click', () => { va.view = decodeVarView(new URLSearchParams()); va.shown = 60; vaApply(); syncVarURL(true); });
  $('#vamore').addEventListener('click', () => { const n = va.shown; va.shown += 60; vaApply(); const el = $$('#valist .vaent')[n]; if (el){ const a = el.querySelector('a'); if (a) a.focus(); } });
  $('#vacsv').addEventListener('click', vaCsv);
}
function vaCsv(){
  const cols = ['id', 'class', 'confidence', 'kind', 'tic', 'sector', 't_center', 'duration_hours', 'depth_ppm', 'amplitude_ppm', 'period_days', 'toi_match', 'cues', 'credit', 'file_sha256', 'code'];
  const q = x => { const s = x === null || x === undefined ? '' : String(x); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  const rows = (va.rows || []).map(e => cols.map(c => c === 'cues' ? (e.class === 'unclassified' ? e.why : (e.cues || []).map(x => x.text).join('; ')) : c === 'credit' ? (e.credit || []).map(x => x.name).join('; ') : e[c]).map(q).join(','));
  const blob = new Blob([cols.join(',') + '\n' + rows.join('\n') + '\n'], {type: 'text/csv'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'exoplan-everything-that-dims.csv'; document.body.appendChild(a); a.click(); a.remove();
  say(`Downloading ${rows.length} entries as CSV.`);
}
function renderVariables(){
  if (!VA) return;
  vaLoad().then(() => { va.rendered = true; vaBind(); vaApply(); }).catch(() => { $('#vacount').textContent = `The sweep catalogue (${VA.json}) could not be loaded here.`; });
}
function applyVariables(v){ va.view = v; if (va.rendered) vaApply(); }
// The global search: a TIC the sweep searched ("tic 2615", "26151"), and the classes by name.
function vaSearch(q){
  if (!VA) return [];
  const out = [];
  for (const c of VA.classes) if (c.label.toLowerCase().includes(q)) out.push({kind: 'class', label: c.label, sub: `${VA.counts.by_class[c.id].toLocaleString('en-GB')} in the sweep`, href: '#/variables?class=' + c.id});
  const d = q.replace(/^tic\s*/, '');
  if (va.C && /^\d{2,}$/.test(d)){
    let n = 0;
    for (const t of Object.keys(va.cov)){ if (t.startsWith(d)){ const es = va.byTic[t] || []; out.push({kind: 'TIC', label: 'TIC ' + t, sub: `sweep · ${es.length} entr${es.length === 1 ? 'y' : 'ies'}`, href: vaTicHref(t)}); if (++n >= 6) break; } }
  }
  return out;
}
// A star page: the sweep's entries for any TIC the star's stored alternate names list.
function vaForStar(salt){
  const box = $('#stsweep'); if (!box) return;
  box.hidden = true;
  if (!VA) return;
  const tics = [...String(salt || '').matchAll(/TIC[ -]?(\d+)/g)].map(m => Number(m[1]));
  if (!tics.length) return;
  vaLoad().then(() => {
    const hit = tics.filter(t => va.cov[t]);
    if (!hit.length) return;
    $('#stsweepbody').innerHTML = hit.map(t => { const es = va.byTic[t] || [], r = va.cov[t][0];
      return `<p><a href="${vaTicHref(t)}">TIC ${t} in the sweep ›</a> ${es.length} entr${es.length === 1 ? 'y' : 'ies'} (${es.map(e => VA_LABEL[e.class]).filter((x, i, a) => a.indexOf(x) === i).join(', ') || 'none'}); searched by ${esc(va.cov[t].flatMap(x => x.searched_by).join(', '))}, sector ${va.cov[t].map(x => x.sector).join(', ')}.</p>`; }).join('');
    box.hidden = false;
  }).catch(() => {});
}
"""

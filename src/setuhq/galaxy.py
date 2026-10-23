# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The Galaxy section: every known exoplanet with a stored distance, in 3D around the Sun.

The data is ``docs/results/exoplanet_map.json``, written by ``scripts/fetch_exoplanet_map.py`` from
the NASA Exoplanet Archive or, when the archive does not answer, from exoplanet.eu. The page says which.
Positions are heliocentric galactic Cartesian coordinates (x toward the Galactic centre, y toward
l = 90°, z toward the north Galactic pole) from RA, Dec and distance, with the standard ICRS-to-Galactic
rotation. Nothing is fitted or filled in: a value the source does not give is shown as a dash.

The Milky Way behind the map is drawn procedurally and is labelled as an artist's impression.
"""

from __future__ import annotations

import csv
import html
import io
import json
import math
from pathlib import Path

from setuhq.looks import CLASS_RULE, CLASSES, MJ_IN_ME, RJ_IN_RE, planet_class  # noqa: F401 (the size classes live in setuhq.looks)
from setuhq.objects import obj_link

DEFAULT_MAP = "docs/results/exoplanet_map.json"
DEFAULT_NOTABLE = "docs/results/notable_planets.json"
LY_PER_PC = 3.261563777
SUN_TO_GC_LY = 26000  # the Sun's distance from the Galactic centre, approximately, as the page states
# The Kepler field: centre RA 19h22m40s, Dec +44°30′; a disc of 7° holds the whole field of view.
KEPLER_FIELD = {"ra": 290.6667, "dec": 44.5, "radius_deg": 7.0}
# The ICRS (J2000) to Galactic rotation (Hipparcos, ESA 1997 vol. 1 §1.5.3; as used by astropy).
ICRS_TO_GAL = (
    (-0.0548755604162154, -0.8734370902348850, -0.4838350155487132),
    (+0.4941094278755837, -0.4448296299600112, +0.7469822444972189),
    (-0.8676661490190047, -0.1980763734312015, +0.4559837761750669),
)
METHOD_COLOUR = {"transit": "#64D2FF", "rv": "#FF6961", "imaging": "#30D158", "microlensing": "#BF5AF2",
                 "astrometry": "#FFD60A", "timing": "#7D7AFF", "other": "#A1A1A6"}
PRESETS = [("near", "Solar neighbourhood"), ("kepler", "Kepler field"), ("galaxy", "Whole galaxy"), ("pimen", "pi Men")]
DIST_STEPS = [0, 50, 100, 250, 500, 1000, 2500, 10000]  # light-years; 0 = every distance
TICKS_LY = [250, 500, 1000, 2500, 10000, 25000]
FEED_TICS = ("348835438", "349088467", "348770361")


def _unit(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    return math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)


def _rot(v):
    return tuple(sum(ICRS_TO_GAL[i][j] * v[j] for j in range(3)) for i in range(3))


def galactic_lb(ra_deg: float, dec_deg: float) -> tuple[float, float]:
    """Galactic longitude and latitude in degrees of an ICRS (J2000) direction."""
    x, y, z = _rot(_unit(ra_deg, dec_deg))
    return math.degrees(math.atan2(y, x)) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, z))))


def galactic_xyz(ra_deg: float, dec_deg: float, dist: float) -> tuple[float, float, float]:
    """Heliocentric galactic Cartesian coordinates, in the unit of ``dist``: x toward the Galactic
    centre, y toward l = 90°, z toward the north Galactic pole."""
    x, y, z = _rot(_unit(ra_deg, dec_deg))
    return x * dist, y * dist, z * dist


def load_map(path: str | Path | None = DEFAULT_MAP) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def _r(x, n):
    return None if x is None else round(x, n)


def galaxy_data(map_path: str | Path | None = DEFAULT_MAP, notable_path: str | Path | None = DEFAULT_NOTABLE,
                *, coverage_path: str | Path | None = None, setuhq_star: str = "pi Men", setuhq_planet: str | None = "pi Men c",
                lead_dip: str | None = None) -> dict | None:
    """The Galaxy section's data: hosts with galactic positions (light-years), planets as columns,
    notable planets resolved against the dataset, and the counts the page states."""
    m = load_map(map_path)
    if m is None:
        return None
    P = m["planets"]
    n = len(P["name"])
    methods = m["methods"]
    host_ix: dict[str, int] = {}
    hosts = {"n": [], "x": [], "y": [], "z": [], "d": [], "ra": [], "dec": [], "v": [], "l": [], "b": []}
    planets = {"n": [], "h": [], "y": [], "m": [], "p": [], "r": [], "ms": [], "mk": [], "c": []}
    for i in range(n):
        host = P["host"][i] or P["name"][i]
        if host not in host_ix:
            host_ix[host] = len(hosts["n"])
            ra, dec, d = P["ra"][i], P["dec"][i], P["dist_pc"][i]
            x, y, z = galactic_xyz(ra, dec, d * LY_PER_PC)
            lon, lat = galactic_lb(ra, dec)
            for k, v in (("n", host), ("x", round(x, 1)), ("y", round(y, 1)), ("z", round(z, 1)), ("d", d),
                         ("ra", round(ra, 4)), ("dec", round(dec, 4)), ("v", P["mag_v"][i]), ("l", round(lon, 2)),
                         ("b", round(lat, 2))):
                hosts[k].append(v)
        h = host_ix[host]
        if hosts["v"][h] is None and P["mag_v"][i] is not None:
            hosts["v"][h] = P["mag_v"][i]
        planets["n"].append(P["name"][i])
        planets["h"].append(h)
        planets["y"].append(P["year"][i])
        planets["m"].append(methods.index(P["method"][i]))
        planets["p"].append(P["period_d"][i])
        planets["r"].append(P["radius_rj"][i])
        planets["ms"].append(P["mass_mj"][i])
        planets["mk"].append({"mass": 0, "msini": 1}.get(P["mass_kind"][i]))
        planets["c"].append(planet_class(P["radius_rj"][i], P["mass_mj"][i]))
    host_n = [0] * len(hosts["n"])
    for h in planets["h"]:
        host_n[h] += 1
    years = sorted(y for y in planets["y"] if y is not None)
    y0, y1 = years[0], years[-1]
    cum, run = {}, 0
    for y in range(y0, y1 + 1):
        run += sum(1 for v in years if v == y)
        cum[str(y)] = run
    per_method = {mt: sum(1 for v in planets["m"] if v == k) for k, mt in enumerate(methods)}

    # The Kepler field: the hosts within the field's disc, and the point the callout pins to.
    kx, ky, kz = _rot(_unit(KEPLER_FIELD["ra"], KEPLER_FIELD["dec"]))
    cosr = math.cos(math.radians(KEPLER_FIELD["radius_deg"]))
    in_field = []
    for h in range(len(hosts["n"])):
        ux, uy, uz = _rot(_unit(hosts["ra"][h], hosts["dec"][h]))
        if ux * kx + uy * ky + uz * kz >= cosr:
            in_field.append(h)
    dists = sorted(hosts["d"][h] * LY_PER_PC for h in in_field)
    kd = dists[len(dists) // 2] if dists else 2000.0
    kepler = {"hosts": len(in_field), "planets": sum(host_n[h] for h in in_field), "median_ly": round(kd),
              "x": round(kx * kd, 1), "y": round(ky * kd, 1), "z": round(kz * kd, 1), **KEPLER_FIELD}

    # The microlensing streak toward the bulge: where those hosts sit (their distances are model-dependent).
    ml = methods.index("microlensing") if "microlensing" in methods else -1
    ml_hosts = sorted({planets["h"][i] for i in range(n) if planets["m"][i] == ml})
    if ml_hosts:
        md = sorted(hosts["d"][h] * LY_PER_PC for h in ml_hosts)[len(ml_hosts) // 2]
        mx = sorted(hosts["x"][h] for h in ml_hosts)[len(ml_hosts) // 2]
        my = sorted(hosts["y"][h] for h in ml_hosts)[len(ml_hosts) // 2]
        mz = sorted(hosts["z"][h] for h in ml_hosts)[len(ml_hosts) // 2]
        lensing = {"hosts": len(ml_hosts), "planets": sum(1 for v in planets["m"] if v == ml), "median_ly": round(md),
                   "x": mx, "y": my, "z": mz}
    else:
        lensing = None
    name_ix = {nm: i for i, nm in enumerate(planets["n"])}
    notable = []
    if notable_path is not None and Path(notable_path).exists():
        for e in json.loads(Path(notable_path).read_text())["planets"]:
            i = name_ix.get(e["name"])
            if i is None:
                continue
            notable.append({"name": e["name"], "tagline": e["tagline"], "ref": e["ref"], "ref_label": e["ref_label"],
                            "planet": i, "host": planets["h"][i], "setuhq": bool(e.get("setuhq", e.get("exoplan"))),
                            "showcase": bool(e.get("showcase")), "method": methods[planets["m"][i]]})
    star_h = host_ix.get(setuhq_star)
    exocomets = sum(1 for nm in planets["n"] if nm.lower().startswith("exocomet"))
    return {
        "source": m["source"], "source_name": m["source_name"], "source_short": m["source_short"], "url": m["url"],
        "fetched_at": m["fetched_at"], "definition": m["definition"], "note": m.get("note", ""),
        "method_rule": m["method_rule"], "methods": methods, "method_label": m["method_label"],
        "method_colour": METHOD_COLOUR, "counts": m["counts"], "per_method": per_method,
        "ly_per_pc": LY_PER_PC, "rj_in_re": RJ_IN_RE, "mj_in_me": MJ_IN_ME, "sun_to_gc_ly": SUN_TO_GC_LY,
        "classes": CLASSES, "class_rule": CLASS_RULE,
        "hosts": hosts, "host_n": host_n, "planets": planets,
        "years": [y0, y1], "cum": cum, "kepler": kepler, "lensing": lensing, "notable": notable, "exocomets": exocomets,
        "star": {"host": star_h, "name": setuhq_star, "planet": setuhq_planet, "lead_dip": lead_dip},
        "feed_tics": list(FEED_TICS),
        "coverage": coverage_gl(load_coverage(coverage_path)),
    }


def galaxy_meta(g: dict | None) -> dict | None:
    """The small part the router needs (URL state) without parsing the map's arrays."""
    if g is None:
        return None
    return {"methods": g["methods"], "method_label": g["method_label"], "method_colour": g["method_colour"],
            "years": g["years"], "dist_steps": DIST_STEPS, "presets": [p for p, _ in PRESETS],
            "preset_label": dict(PRESETS), "tour": [e["name"] for e in g["notable"]],
            "n_planets": g["counts"]["kept"], "n_hosts": g["counts"]["hosts"],
            "layers": [k for k, _ in COV_LAYERS] if g.get("coverage") else []}


def teaser_points(g: dict | None, n: int = 1400) -> dict | None:
    """The nearest ``n`` hosts, for the Overview's small rotating render: [x, y, z] in ly and a method index."""
    if g is None:
        return None
    H = g["hosts"]
    first = {}
    for i, h in enumerate(g["planets"]["h"]):
        y = g["planets"]["y"][i] or 9999
        if h not in first or y < first[h][0]:
            first[h] = (y, g["planets"]["m"][i])
    order = sorted(range(len(H["n"])), key=lambda h: H["d"][h])[:n]
    return {"p": [[round(H["x"][h]), round(H["y"][h]), round(H["z"][h]), first[h][1]] for h in order],
            "colours": [g["method_colour"][mt] for mt in g["methods"]], "n": len(order),
            "reach_ly": round(H["d"][order[-1]] * LY_PER_PC) if order else 0}


def fmt_date(iso: str) -> str:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        y, mo, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
        return f"{d} {months[mo - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def source_line(g: dict) -> str:
    return (f"Data: {g['source_name']}, fetched {fmt_date(g['fetched_at'])}; {g['counts']['kept']:,} planets with a "
            f"stored distance, around {g['counts']['hosts']:,} stars.")


def fmt_ly(pc: float) -> str:
    ly = pc * LY_PER_PC
    return f"{ly:,.1f}" if ly < 100 else f"{ly:,.0f}"


def _first(g, h):
    P = g["planets"]
    ix = [i for i, v in enumerate(P["h"]) if v == h]
    return ix


def nearest_table(g: dict, n: int = 50) -> str:
    e = html.escape
    H, P = g["hosts"], g["planets"]
    by_host: dict[int, list[int]] = {}
    for i, h in enumerate(P["h"]):
        by_host.setdefault(h, []).append(i)
    order = sorted(range(len(H["n"])), key=lambda h: H["d"][h])[:n]
    rows = []
    for h in order:
        ps = sorted(by_host[h], key=lambda i: (P["y"][i] or 0, P["n"][i]))
        names = ", ".join(obj_link("planet", P["n"][i]) for i in ps)
        starless = len(ps) == 1 and P["n"][ps[0]] == H["n"][h]  # a free-floating planet is its own "host"
        meths = ", ".join(dict.fromkeys(g["method_label"][g["methods"][P["m"][i]]] for i in ps))
        rows.append(f"<tr><th scope='row'>{e(H['n'][h]) if starless else obj_link('star', H['n'][h])}</th><td class='num'>{fmt_ly(H['d'][h])}</td>"
                    f"<td class='num'>{H['d'][h]:g}</td><td>{names}</td><td class='num'>{P['y'][ps[0]] or '—'}</td><td>{e(meths)}</td></tr>")
    return ("<table class='gxtable'><caption class='sr'>The 50 nearest planetary systems in the dataset</caption>"
            "<thead><tr><th scope='col'>System</th><th scope='col' class='num'>Distance (ly)</th><th scope='col' class='num'>Distance (pc)</th>"
            "<th scope='col'>Planets</th><th scope='col' class='num'>First found</th><th scope='col'>Methods</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


CSV_NAME = "exoplanet_map.csv"


def map_csv(g: dict) -> str:
    """Every plotted planet, one row each, derived from exoplanet_map.json (the table the page draws)."""
    H, P = g["hosts"], g["planets"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["planet", "host", "distance_ly", "distance_pc", "ra_deg", "dec_deg", "gal_l_deg", "gal_b_deg",
                "x_ly", "y_ly", "z_ly", "discovered", "method", "period_d", "radius_rj", "mass_mj", "mass_kind",
                "class", "host_v_mag"])
    for i in range(len(P["n"])):
        h = P["h"][i]
        c = P["c"][i]
        w.writerow([P["n"][i], H["n"][h], round(H["d"][h] * LY_PER_PC, 2), H["d"][h], H["ra"][h], H["dec"][h],
                    H["l"][h], H["b"][h], H["x"][h], H["y"][h], H["z"][h], P["y"][i], g["methods"][P["m"][i]],
                    P["p"][i], P["r"][i], P["ms"][i], {0: "mass", 1: "msini"}.get(P["mk"][i], ""),
                    "" if c is None else CLASSES[c], H["v"][h]])
    return buf.getvalue()


def galaxy_section(g: dict | None, eyebrow: str, unconfirmed: str, cov: dict | None = None) -> str:
    """The Galaxy route's HTML (header, stage, HUD, controls, notes, notable list and table)."""
    e = html.escape
    if g is None:
        return (f"<header>{eyebrow}<h1 class='lead-h' id='h-galaxy' tabindex='-1'>Every known exoplanet.</h1>"
                "<p>The exoplanet map (docs/results/exoplanet_map.json) is not in this build, so there is nothing to plot.</p></header>")
    c = g["counts"]
    presets = "".join(f'<button class="btn" type="button" data-gxview="{k}" aria-pressed="false">{e(v)}</button>' for k, v in PRESETS)
    methods = "".join(
        f'<button class="chip gxm" type="button" data-gxm="{mt}" aria-pressed="true"><i style="background:{g["method_colour"][mt]}"></i>'
        f'{e(g["method_label"][mt])} <span class="mono">{g["per_method"][mt]:,}</span></button>' for mt in g["methods"])
    dist = "".join(f'<option value="{d}">{"every distance" if not d else f"within {d:,} ly"}</option>' for d in DIST_STEPS)
    star = g["star"]
    kep = g["kepler"]
    summary = (f"3D map of {c['kept']:,} known exoplanets around {c['hosts']:,} stars, placed around the Sun in galactic "
               f"coordinates from their sky position and distance. Colour shows the detection method; larger points are "
               f"stars with more planets. The densest streak, toward Cygnus and Lyra, is the Kepler field "
               f"({kep['hosts']:,} stars within a 7° disc). The table below lists the 50 nearest systems.")
    notable = "".join(
        f'<li style="border-left:3px solid {g["method_colour"][nt["method"]]}"><button class="gxnot" type="button" data-gxstop="{k + 1}"><b>{e(nt["name"])}</b>'
        f'<span>{e(nt["tagline"])}</span><span class="mono">{e(g["method_label"][nt["method"]])}{" · method showcase" if nt["showcase"] else ""}</span></button>'
        f'<a class="gxref" href="{e(nt["ref"])}" rel="noopener">{e(nt["ref_label"])}</a>{obj_link("planet", nt["name"], "Planet page ›", "gxref")}</li>'
        for k, nt in enumerate(g["notable"]))
    note = f" {e(g['note'])}." if g.get("note") else ""
    feed = ", ".join(f"TIC {t}" for t in g["feed_tics"])
    return f"""<header class="headrow">
        <div>{eyebrow}<h1 class="lead-h" id="h-galaxy" tabindex="-1">Every known exoplanet,<br><span class="grey">around the Sun.</span></h1>
        <p>{c['kept']:,} planets around {c['hosts']:,} stars, placed where they are. SetuHQ did not find these planets; it maps them from {e(g['source_short'])}.</p></div>
        <div class="segctl gxpresets" id="gxpresets" role="group" aria-label="Camera view">{presets}</div>
      </header>
      <div class="gxstage space" id="gxstage">
        <canvas id="gxcanvas" tabindex="0" role="img" aria-label="{e(summary)}" aria-describedby="gxkeys"></canvas>
        <svg class="gxleaders" id="gxleaders" aria-hidden="true"></svg>
        <div class="gxlayer" id="gxlayer" aria-hidden="true"></div>
        <div class="gxreticle" aria-hidden="true"><i></i></div>
        <div class="gxaim" id="gxaim" aria-hidden="true" hidden></div>
        <div class="gxhud gxtr" aria-hidden="true">
          <svg class="gxradar" id="gxradar" viewBox="-50 -50 100 100"><circle r="46" class="r1"/><circle r="30" class="r2"/><circle r="14" class="r2"/>
            <path class="cross" d="M-46 0H46M0-46V46"/><g class="sweep"><path d="M0 0L0-46" class="sw"/><path d="M0 0L0-46A46 46 0 0 1 22-40Z" class="swf"/></g>
            <g id="gxheading"><path d="M0 0L-13-40A42 42 0 0 1 13-40Z" class="fov"/></g><g id="gxgc"><text y="-36" text-anchor="middle">GC</text></g><circle r="2.6" class="sun"/></svg>
          <pre class="gxtel mono" id="gxtel"></pre>
        </div>
        <div class="gxhud gxbl" aria-hidden="true">
          <svg class="gxorbit" viewBox="-20 -20 40 40"><circle r="17" class="o"/><circle r="10" class="o"/><circle r="3.2" class="s"/><g class="spin1"><circle cx="10" r="1.6"/></g><g class="spin2"><circle cx="-17" r="2"/></g></svg>
          <p class="gxcounter mono"><span id="gxcyear">{g['years'][1]}</span> <i>//</i> <span id="gxccount">{c['kept']:,}</span><small>planets shown</small></p>
        </div>
        <div class="gxtip glass" id="gxtip" hidden></div>
        <section class="gxcard glass" id="gxcard" aria-label="Selected system" hidden></section>
        <p class="gxmw" id="gxmw" hidden>Milky Way: artist's impression; Sun's position approximate (~{SUN_TO_GC_LY:,} ly from the centre)</p>
        <p class="gxfocusnote" id="gxfocusnote" role="status" hidden></p>
        <p class="gxnogl" id="gxload" role="status" hidden>Loading the map of {c['kept']:,} planets…</p>
        <p class="gxnogl" id="gxnogl" hidden>This browser did not start WebGL, so the 3D map cannot be drawn. The table below lists the nearest systems, and the CSV holds every plotted planet.</p>
        <div class="gxtourbar glass" id="gxtourbar" role="group" aria-label="Tour" hidden>
          <button class="btn" type="button" id="gxtprev" aria-label="Previous stop">‹</button>
          <button class="btn" type="button" id="gxtpause">Pause</button>
          <button class="btn" type="button" id="gxtnext" aria-label="Next stop">›</button>
          <span class="mono" id="gxtlabel" aria-live="polite"></span>
          <button class="btn" type="button" id="gxtexit">End tour</button>
        </div>
      </div>
      <details class="gxsheet" id="gxsheet" open>
        <summary><span>Timeline and filters</span><span class="mono" id="gxsum"></span></summary>
        <div class="gxcontrols">
          <div class="gxtime">
            <button class="btn primary" type="button" id="gxplay">Play {g['years'][0]}–{g['years'][1]}</button>
            <input type="range" id="gxyear" min="{g['years'][0]}" max="{g['years'][1]}" step="1" value="{g['years'][1]}" aria-label="Show planets discovered up to this year">
            <output class="mono" id="gxyearout" for="gxyear"></output>
          </div>
          <div class="chips gxmethods" id="gxmethods" role="group" aria-label="Detection method">{methods}</div>
          <div class="gxrow">
            <label class="gxsel"><span>Distance</span><select id="gxdist">{dist}</select></label>
            <button class="chip" type="button" id="gxmulti" aria-pressed="false">Multi-planet systems only</button>
            <button class="chip" type="button" id="gxshowcase" aria-pressed="false">Cards: one per method</button>
            <button class="btn" type="button" id="gxtour">Take the tour</button>
          </div>
          {coverage_chips(cov, "gx")}
        </div>
      </details>
      <p class="gxkeys muted" id="gxkeys">Drag to orbit · scroll or pinch to zoom · double-click a star to centre on it · arrow keys orbit · + and − zoom · Enter selects the star under the reticle · Esc clears.</p>
      <div class="gxnotes">
        <p class="note"><b>{e(source_line(g))}</b> <a href="{e(g['url'])}" rel="noopener">{e(g['url'])}</a>.{note} {e(g['definition'])} The list includes {g['exocomets']} entries exoplanet.eu names as exocomets. {c['dropped_no_distance']:,} of its {c['rows']:,} planets have no stored distance and are not plotted.</p>
        <p class="note"><b>Not plotted.</b> The feed's stars ({e(feed)}) have no stored positions, so they are not on this map. {e(star['name'])} is placed from the dataset, like every other star; {e(star['planet'] or star['name'])} is the planet SetuHQ's run {('recovered') if star['planet'] else 'reviewed'}.</p>
        <p class="note"><b>How to read it.</b> Positions: heliocentric galactic coordinates from RA, Dec (J2000) and distance; x points to the Galactic centre and the grid is the Galactic plane. Axis ticks are in light-years (1 pc = {LY_PER_PC:.3f} ly). Colour: the detection method of the earliest planet shown for each star ({e(g['method_rule'])}). Size: planets per star. Microlensing distances come from models of each event and are uncertain (<a href="#/methods?ch=microlensing">how microlensing works</a>). The bias in the cloud is where surveys looked and what each method can see, not where planets are. The Milky Way is an artist's impression drawn by the page, not data; the Sun's position in it is approximate.</p>
        <p class="note">{e(CLASS_RULE)}</p>
      </div>
      {coverage_panel(cov, g)}
      <section class="card gxnotable" aria-labelledby="h-gxnot">
        <h2 id="h-gxnot">Notable planets</h2>
        <p class="muted">Pinned on the map. Distance, year and method come from the dataset; each line has the reference that supports it.</p>
        <ol>{notable}</ol>
      </section>
      <details class="card gxtablecard"><summary>View as table: the 50 nearest systems</summary>
        <div class="tablewrap" tabindex="0" role="region" aria-label="The 50 nearest systems">{nearest_table(g)}</div>
        <p><a href="/assets/data/{CSV_NAME}" download>Download every plotted planet (CSV, {c['kept']:,} rows)</a>, derived from the stored exoplanet.eu map.</p>
      </details>"""


def teaser_html(g: dict | None, t: dict | None) -> str:
    e = html.escape
    if g is None or t is None:
        return ""
    c = g["counts"]
    return f"""<section class="gxteaser space" aria-labelledby="h-gxteaser">
        <canvas class="gxtcanvas" data-teaser role="img" aria-label="A slowly turning 3D view of the {t['n']:,} nearest planet-hosting stars around the Sun, coloured by detection method."></canvas>
        <div class="gxtcopy">
          <p class="kick">Galaxy</p>
          <h2 id="h-gxteaser">{c['kept']:,} known exoplanets, around the Sun.</h2>
          <p>Every planet with a stored distance, placed in 3D, from the Sun out to the Milky Way's bulge. Fly to the Kepler field, scrub the discovery years from {g['years'][0]}, or take the tour.</p>
          <a class="btn primary" href="#/galaxy">Explore every known exoplanet ›</a>
          <p class="small">{e(source_line(g))} SetuHQ did not discover these planets.</p>
        </div>
      </section>"""


GALAXY_CSS = r"""
/* ---------- galaxy ---------- */
.gxpresets{flex-wrap:wrap}
.gxstage{position:relative;height:min(76vh,780px);min-height:460px;background:#000;touch-action:none;user-select:none;-webkit-user-select:none}
.gxstage canvas{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;outline:none}
.gxstage canvas:active{cursor:grabbing}
.gxstage canvas:focus-visible{box-shadow:inset 0 0 0 2px #0A84FF}
.gxleaders,.gxlayer{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:hidden}
.gxleaders line{stroke:rgba(255,255,255,.42);stroke-width:1;stroke-dasharray:3 4}
.gxlbl{position:absolute;left:0;top:0;font:500 11px/1 var(--mono);color:#A1A1A6;white-space:nowrap;will-change:transform}
.gxlbl.tick{color:#64D2FF}
.gxlbl.tick::before{content:"";position:absolute;left:-3px;top:-3px;width:5px;height:5px;border-radius:50%;background:#64D2FF}
.gxlbl.tick span{position:absolute;left:6px;top:4px}
.gxlbl.axis{color:#64D2FF;font:600 12px/1 var(--sans)}
.gxlbl.sun{color:#FFB340;font:600 12px/1 var(--sans)}
.gxlbl.region{color:#F5F5F7;font:500 12px/1.3 var(--sans);background:rgba(28,28,30,.6);border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:6px 9px;-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
.gxlbl.region small{display:block;color:#A1A1A6;font:500 11px/1.3 var(--mono)}
.gxring{position:absolute;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;border:1px solid rgba(255,255,255,.7);box-shadow:0 0 14px 3px rgba(100,210,255,.45),inset 0 0 8px rgba(100,210,255,.4)}
.gxring.ex{border-color:#FFB340;box-shadow:0 0 14px 3px rgba(255,179,64,.5),inset 0 0 8px rgba(255,179,64,.4)}
.gxcall{position:absolute;left:0;top:0;width:224px;padding:10px 12px;border-radius:14px;background:rgba(18,18,20,.72);border:1px solid rgba(255,255,255,.14);color:#F5F5F7;-webkit-backdrop-filter:blur(16px) saturate(160%);backdrop-filter:blur(16px) saturate(160%);pointer-events:auto;cursor:pointer;transition:opacity .25s var(--ease)}
.gxcall.ex{border-color:rgba(255,179,64,.55)}
.gxcall.sel{border-color:#64D2FF}
.gxcall b{display:flex;align-items:center;gap:7px;font:600 14px/1.25 var(--sans)}
.gxcall b i{flex:none;width:8px;height:8px;border-radius:50%}
.gxcall p{margin:3px 0 7px;font:400 12px/1.35 var(--sans);color:#C7C7CC}
.gxcall dl{display:grid;grid-template-columns:auto 1fr;gap:1px 10px;margin:0;font:500 11px/1.45 var(--mono)}
.gxcall dt{color:#8E8E93}
.gxcall dd{margin:0;color:#F5F5F7}
.gxreticle{position:absolute;left:50%;top:50%;width:38px;height:38px;margin:-19px 0 0 -19px;pointer-events:none;opacity:.55}
.gxreticle::before,.gxreticle::after{content:"";position:absolute;background:rgba(255,255,255,.75)}
.gxreticle::before{left:18px;top:0;width:1px;height:38px;-webkit-mask:linear-gradient(#000 0 13px,transparent 13px 25px,#000 25px);mask:linear-gradient(#000 0 13px,transparent 13px 25px,#000 25px)}
.gxreticle::after{top:18px;left:0;height:1px;width:38px;-webkit-mask:linear-gradient(90deg,#000 0 13px,transparent 13px 25px,#000 25px);mask:linear-gradient(90deg,#000 0 13px,transparent 13px 25px,#000 25px)}
.gxaim{position:absolute;left:0;top:0;width:26px;height:26px;margin:-13px 0 0 -13px;pointer-events:none;border:1px solid #64D2FF;border-radius:4px;-webkit-mask:conic-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);clip-path:polygon(0 0,35% 0,35% 4%,65% 4%,65% 0,100% 0,100% 35%,96% 35%,96% 65%,100% 65%,100% 100%,65% 100%,65% 96%,35% 96%,35% 100%,0 100%,0 65%,4% 65%,4% 35%,0 35%)}
.gxhud{position:absolute;pointer-events:none;color:#F5F5F7}
.gxtr{right:14px;top:14px;display:grid;justify-items:end;gap:8px;max-width:270px}
.gxradar{width:104px;height:104px;overflow:visible}
.gxradar circle{fill:none}
.gxradar .r1{stroke:rgba(100,210,255,.55);fill:rgba(0,0,0,.35)}
.gxradar .r2{stroke:rgba(100,210,255,.18)}
.gxradar .cross{stroke:rgba(100,210,255,.18)}
.gxradar .sw{stroke:rgba(100,210,255,.6)}
.gxradar .swf{fill:rgba(100,210,255,.12)}
.gxradar .fov{fill:rgba(255,255,255,.14);stroke:rgba(255,255,255,.55)}
.gxradar text{fill:#64D2FF;font:600 11px var(--mono)}
.gxradar .sun{fill:#FFB340}
.gxradar .sweep{transform-origin:0 0;animation:gxsweep 4s linear infinite}
@keyframes gxsweep{to{transform:rotate(360deg)}}
.gxtel{margin:0;padding:8px 10px;border-radius:12px;background:rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.1);font:500 11px/1.5 var(--mono);color:#C7C7CC;white-space:pre;min-width:220px;max-width:270px;overflow:hidden;text-overflow:ellipsis}
.gxtel b{color:#64D2FF;font-weight:600}
.gxbl{left:14px;bottom:14px;display:flex;align-items:center;gap:10px}
.gxorbit{width:40px;height:40px}
.gxorbit .o{fill:none;stroke:rgba(255,255,255,.22)}
.gxorbit .s{fill:#FFB340}
.gxorbit circle:not(.o):not(.s){fill:#64D2FF}
.gxorbit .spin1{animation:gxspin 6s linear infinite}
.gxorbit .spin2{animation:gxspin 14s linear infinite}
@keyframes gxspin{to{transform:rotate(360deg)}}
.gxcounter{margin:0;font:600 22px/1 var(--mono);letter-spacing:.02em;color:#F5F5F7}
.gxcounter i{font-style:normal;color:#64D2FF;margin:0 4px}
.gxcounter small{display:block;margin-top:4px;font:500 11px/1 var(--sans);color:#A1A1A6;letter-spacing:0}
.gxtip{position:absolute;left:0;top:0;z-index:4;pointer-events:none;padding:8px 10px;border-radius:12px;font:500 12px/1.45 var(--sans);color:#F5F5F7;background:rgba(18,18,20,.85);border:1px solid rgba(255,255,255,.14);max-width:260px}
.gxtip .mono{font-size:11px;color:#A1A1A6}
.gxcard{position:absolute;left:14px;top:14px;z-index:5;width:min(320px,calc(100% - 28px));max-height:calc(100% - 120px);overflow:auto;padding:14px;border-radius:18px;background:rgba(18,18,20,.82);border:1px solid rgba(255,255,255,.14);color:#F5F5F7;-webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px)}
.gxcard h3{margin:0 40px 2px 0;font:600 17px/1.25 var(--sans)}
.gxcard .mono{font-size:12px;color:#A1A1A6}
.gxcard ul{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:4px}
.gxcard li button{all:unset;box-sizing:border-box;display:grid;gap:1px;width:100%;min-height:44px;padding:6px 10px;border-radius:10px;cursor:pointer;color:#F5F5F7;font:500 13px/1.3 var(--sans)}
.gxcard li button span{font:500 11px/1.3 var(--mono);color:#A1A1A6}
.gxcard li button:hover,.gxcard li button[aria-pressed="true"]{background:rgba(255,255,255,.08)}
.gxcard li button:focus-visible{outline:2px solid #0A84FF}
.gxcard .x{position:absolute;right:8px;top:8px;width:44px;height:44px;min-height:44px;padding:0;justify-content:center;border-radius:50%}
.gxcard a{color:#64D2FF}
.gxcard p{margin:8px 0 0;font-size:12px;color:#C7C7CC}
.gxmw{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);margin:0;padding:6px 12px;border-radius:999px;background:rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.12);font:500 12px/1.3 var(--sans);color:#C7C7CC;text-align:center;max-width:calc(100% - 300px)}
.gxnogl{position:absolute;inset:auto 20px 50% 20px;margin:0;text-align:center;color:#C7C7CC}
.gxfocusnote{position:absolute;left:50%;top:14px;transform:translateX(-50%);z-index:6;width:max-content;max-width:calc(100% - 28px);margin:0;padding:6px 6px 6px 14px;border-radius:16px;background:rgba(18,18,20,.9);border:1px solid rgba(255,255,255,.14);color:#F5F5F7;font-size:13px;display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.gxfocusnote a{display:inline-flex;align-items:center;min-height:44px;padding:0 12px;color:#64D2FF}
.gxfocusnote[hidden]{display:none}
.gxtourbar{position:absolute;left:50%;top:14px;transform:translateX(-50%);z-index:6;display:flex;align-items:center;gap:6px;padding:6px;border-radius:999px;background:rgba(18,18,20,.82);border:1px solid rgba(255,255,255,.14);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);color:#F5F5F7}
.gxtourbar[hidden],.gxcard[hidden],.gxtip[hidden],.gxaim[hidden],.gxmw[hidden],.gxnogl[hidden]{display:none}
.gxtourbar .btn{min-height:44px;min-width:44px;justify-content:center}
.gxtourbar .mono{font-size:12px;padding:0 6px;white-space:nowrap;max-width:240px;overflow:hidden;text-overflow:ellipsis}
.gxsheet{border:1px solid var(--line);border-radius:var(--r);background:var(--glass);-webkit-backdrop-filter:saturate(180%) blur(20px);backdrop-filter:saturate(180%) blur(20px)}
.gxsheet>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;padding:4px 16px;cursor:pointer;font-weight:600;font-size:14px;list-style:none}
.gxsheet>summary::-webkit-details-marker{display:none}
.gxsheet>summary .mono{font-weight:500;color:var(--ink-2);font-size:13px}
.gxcontrols{display:grid;gap:12px;padding:0 16px 16px}
.gxtime{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.gxtime input{flex:1 1 240px;min-width:0;min-height:44px;accent-color:#0A84FF}
.gxtime output{font-size:14px;min-width:150px}
.covchips .chip i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:7px}
.covchips .chip[aria-pressed="false"] i{opacity:.4}
.covpanel{display:grid;gap:10px}
.covpanel h3{margin:6px 0 0;font-size:15px}
.covpanel p{margin:0}
.gxmethods .chip i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}
.gxmethods .chip .mono{color:var(--ink-3);margin-left:6px;font-size:12px}
.gxmethods .chip[aria-pressed="true"] .mono{color:inherit}
.gxmethods .chip[aria-pressed="false"]{color:var(--ink-3)}
.gxmethods .chip[aria-pressed="false"] i{background:transparent!important;box-shadow:inset 0 0 0 1px var(--ink-3)}
.gxrow{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.gxsel{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)}
.gxsel select{min-height:44px;padding:0 12px;border-radius:12px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 14px var(--sans)}
.gxkeys{margin:0;font-size:12px}
.gxnotes{display:grid;gap:8px}
.gxnotes .note{margin:0}
.gxnotes a{overflow-wrap:anywhere}
.gxnotable ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}
.gxnotable li{display:grid;gap:2px;border:1px solid var(--line);border-radius:14px;padding:4px}
.gxnot{all:unset;box-sizing:border-box;display:grid;gap:2px;min-height:44px;padding:8px 10px;border-radius:10px;cursor:pointer}
.gxnot:hover{background:var(--panel-2)}
.gxnot:focus-visible{outline:2px solid var(--blue)}
.gxnot b{font-size:14px}
.gxnot span{font-size:13px;color:var(--ink-2)}
.gxref{display:inline-flex;align-items:center;min-height:44px;padding:0 10px;font-size:12px}
.gxtablecard summary{display:flex;align-items:center;min-height:44px;cursor:pointer;font-weight:600}
.gxtable{width:100%;border-collapse:collapse;font-size:13px}
.gxtable th,.gxtable td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.gxtable .num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.gxtablecard a{display:inline-flex;align-items:center;min-height:44px}
/* the Overview's teaser */
.gxteaser{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);align-items:center;min-height:360px;background:#000}
.gxtcanvas{width:100%;height:100%;min-height:360px;display:block}
.gxtcopy{padding:28px 32px 28px 8px;display:grid;gap:10px;justify-items:start}
.gxtcopy h2{margin:0;font:600 clamp(24px,3vw,34px)/1.1 var(--sans);letter-spacing:-.02em;color:#F5F5F7}
.gxtcopy p{margin:0;color:#A1A1A6}
.gxtcopy .small{font-size:12px}
@media (max-width:699.98px){
  .gxstage{height:64vh;min-height:380px;border-radius:20px}
  .gxtr{right:8px;top:8px;gap:6px}
  .gxradar{width:68px;height:68px}
  .gxtel{display:none}
  .gxstage.sel .gxtr,.gxstage.sel .gxbl{display:none}
  .gxbl{left:10px;bottom:10px}
  .gxorbit{display:none}
  .gxcounter{font-size:17px}
  .gxcall{width:150px;padding:7px 9px}
  .gxcall p,.gxcall dl dt:nth-of-type(n+3),.gxcall dl dd:nth-of-type(n+3){display:none}
  .gxcard{left:8px;right:8px;top:auto;bottom:8px;width:auto;max-height:55%}
  .gxmw{bottom:auto;top:84px;max-width:calc(100% - 100px);left:10px;transform:none;text-align:left;font-size:11px}
  .gxtourbar{top:auto;bottom:62px;max-width:calc(100% - 16px)}
  .gxtourbar .mono{max-width:96px}
  .gxtourbar #gxtexit{padding:0 10px}
  .gxsheet{position:sticky;bottom:max(8px,env(safe-area-inset-bottom,0px));z-index:15;box-shadow:0 -12px 30px -16px rgba(0,0,0,.6)}
  .gxsheet[open] .gxcontrols{max-height:52vh;overflow:auto}
  .gxtime output{min-width:0}
  .gxmethods .chip,.gxsheet .chip,.gxsheet .btn{min-height:44px}
  .gxteaser{grid-template-columns:1fr}
  .gxtcanvas{min-height:260px;height:260px}
  .gxtcopy{padding:0 18px 22px}
  .gxkeys{display:none}
}
@media (prefers-reduced-motion: reduce){
  .gxradar .sweep,.gxorbit .spin1,.gxorbit .spin2{animation:none!important}
  .gxcall{transition:none}
}
"""


TEASER_JS = r"""
// The Overview's Galaxy teaser: the nearest planet hosts, turning slowly (still under reduced motion).
(function(){
  var src = document.getElementById('teaser-data'); if (!src) return;
  var T = JSON.parse(src.textContent), rm = window.matchMedia('(prefers-reduced-motion: reduce)');
  Array.prototype.forEach.call(document.querySelectorAll('canvas[data-teaser]'), function(cv){
    var ctx = cv.getContext('2d'); if (!ctx) return;
    var reach = T.reach_ly || 1, a = -0.6, seen = false, raf = 0, last = 0;
    // Runs only while the canvas is on screen (seen by the observer and laid out) and the tab is visible.
    function live(){ return seen && !document.hidden && cv.getClientRects().length > 0; }
    function size(){ var r = cv.getBoundingClientRect(), k = Math.min(2, window.devicePixelRatio || 1); cv.width = Math.max(1, Math.round(r.width * k)); cv.height = Math.max(1, Math.round(r.height * k)); return k; }
    var k = size();
    function draw(){
      var w = cv.width, h = cv.height, s = Math.min(w, h) * 0.46 / reach, ca = Math.cos(a), sa = Math.sin(a), tilt = 0.42, ct = Math.cos(tilt), st = Math.sin(tilt);
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = 'rgba(100,210,255,.22)'; ctx.lineWidth = k;
      for (var r = 1; r <= 3; r++){ ctx.beginPath(); ctx.ellipse(w / 2, h / 2, reach * s * r / 3, reach * s * r / 3 * st, 0, 0, 2 * Math.PI); ctx.stroke(); }
      for (var i = 0; i < T.p.length; i++){
        var p = T.p[i], x = p[0] * ca - p[1] * sa, y = p[0] * sa + p[1] * ca, z = p[2];
        var sy = y * st - z * ct, depth = y * ct + z * st, f = 1 + depth / reach * 0.25;
        ctx.globalAlpha = Math.max(.25, Math.min(1, .75 + depth / reach * .4));
        ctx.fillStyle = T.colours[p[3]];
        ctx.fillRect(w / 2 + x * s * f - k, h / 2 + sy * s * f - k, 2 * k, 2 * k);
      }
      ctx.globalAlpha = 1; ctx.fillStyle = '#FFB340'; ctx.beginPath(); ctx.arc(w / 2, h / 2, 3.5 * k, 0, 2 * Math.PI); ctx.fill();
    }
    function tick(t){ raf = 0; if (!live()){ last = 0; return; } if (last) a += Math.min(50, t - last) * 0.00006; last = t; draw(); if (!rm.matches) raf = requestAnimationFrame(tick); }
    function start(){ if (!live() || raf) return; last = 0; raf = requestAnimationFrame(tick); }
    if ('IntersectionObserver' in window) new IntersectionObserver(function(es){ seen = es[0].isIntersecting; start(); }).observe(cv);
    else { seen = true; start(); }
    document.addEventListener('visibilitychange', start);
    window.addEventListener('hashchange', function(){ setTimeout(start, 0); });
    window.addEventListener('resize', function(){ k = size(); draw(); });
    draw();
  });
})();
"""


GALAXY_JS = r"""
// ---------- galaxy: every known exoplanet around the Sun (hand-written WebGL) ----------
const GXM = D.galaxy_meta || null;
const GX_FOV = 50 * Math.PI / 180;
// URL state: year, method, dist, multi, view (camera preset) and tour (stop); defaults are left out.
function decodeGalaxyView(params){
  const M = GXM.methods;
  let methods = M.slice();
  const ms = params.get('method');
  if (ms === 'none') methods = [];
  else if (ms){ const want = ms.split(',').filter(x => M.includes(x)); if (want.length) methods = M.filter(x => want.includes(x)); }
  let year = parseInt(params.get('year'), 10);
  if (!(year >= GXM.years[0] && year <= GXM.years[1])) year = GXM.years[1];
  let dist = Number(params.get('dist'));
  if (!GXM.dist_steps.includes(dist)) dist = 0;
  let view = params.get('view');
  if (!GXM.presets.includes(view)) view = GXM.presets[0];
  let tour = parseInt(params.get('tour'), 10);
  if (!(tour >= 1 && tour <= GXM.tour.length)) tour = 0;
  const ls = (params.get('layers') || '').split(',');
  return {year, methods, dist, multi: params.get('multi') === '1', view, tour, showcase: params.get('cards') === 'methods',
    layers: (GXM.layers || []).filter(k => ls.includes(k)), focus: (params.get('focus') || '').slice(0, 120)};
}
function encodeGalaxyView(v){
  const out = [];
  if (v.year !== GXM.years[1]) out.push('year=' + v.year);
  if (v.methods.length !== GXM.methods.length) out.push('method=' + (v.methods.length ? GXM.methods.filter(m => v.methods.includes(m)).join(',') : 'none'));
  if (v.dist) out.push('dist=' + v.dist);
  if (v.multi) out.push('multi=1');
  if (v.showcase) out.push('cards=methods');
  if (v.layers && v.layers.length) out.push('layers=' + GXM.layers.filter(k => v.layers.includes(k)).join(','));
  if (v.view !== GXM.presets[0]) out.push('view=' + v.view);
  if (v.tour) out.push('tour=' + v.tour);
  if (v.focus) out.push('focus=' + encodeURIComponent(v.focus));
  return out.join('&');
}
// Which planets the filters keep: discovered by the year, by a chosen method, within the distance,
// and (optionally) around a star with two or more planets in the dataset. Returns the counts and,
// per star, how many of its planets are shown.
function gxFilterCount(G, v){
  const P = G.planets, H = G.hosts, on = new Set(v.methods.map(m => G.methods.indexOf(m)));
  const lim = v.dist ? v.dist / G.ly_per_pc : Infinity, per = new Int32Array(H.n.length);
  let planets = 0, hosts = 0;
  for (let i = 0; i < P.n.length; i++){
    const h = P.h[i];
    if ((P.y[i] || 0) > v.year || !on.has(P.m[i]) || H.d[h] > lim || (v.multi && G.host_n[h] < 2)) continue;
    if (!per[h]) hosts++;
    per[h]++; planets++;
  }
  return {planets, hosts, per};
}

const gx = {G: null, ready: false, on: false, gl: null, view: null, cam: null, flight: null, raf: 0, last: 0, interacted: -1e9,
  play: null, tour: null, sel: -1, selPlanet: -1, hover: -1, aim: -1, dirty: true, frames: 0, per: null, shown: null,
  pointers: new Map(), drag: null, visible: false, auto: true, labels: null, cards: null, mw: 0, telAt: 0, byHost: null};
const gxRM = window.matchMedia('(prefers-reduced-motion: reduce)');
const gxPhone = window.matchMedia('(max-width: 699.98px)');
// The map's arrays live in assets/data/galaxy.json (same origin), fetched on the first visit.
function gxLoad(){
  if (!gx.loading) gx.loading = fetch('/assets/data/galaxy.json').then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(G => { gx.G = G; return G; });
  return gx.loading;
}
const gxFmt = (x, d) => x == null ? '—' : x.toLocaleString('en-GB', {maximumFractionDigits: d, minimumFractionDigits: 0});
const gxSig = x => x == null ? '—' : (Math.abs(x) >= 100 ? gxFmt(x, 0) : Number(x.toPrecision(3)).toString());
function gxLy(pc){ const ly = pc * gx.G.ly_per_pc; return ly < 100 ? gxFmt(ly, 1) : gxFmt(ly, 0); }
function gxSmooth(a, b, x){ const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); }
const gxEase = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

// ---------- matrices (column-major, as WebGL reads them) ----------
function m4persp(fy, asp, n, f){ const t = 1 / Math.tan(fy / 2), nf = 1 / (n - f); return [t / asp, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) * nf, -1, 0, 0, 2 * f * n * nf, 0]; }
function v3norm(v){ const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
function v3cross(a, b){ return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function m4look(e, c, up){
  const z = v3norm([e[0] - c[0], e[1] - c[1], e[2] - c[2]]), x = v3norm(v3cross(up, z)), y = v3cross(z, x);
  return [x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
    -(x[0] * e[0] + x[1] * e[1] + x[2] * e[2]), -(y[0] * e[0] + y[1] * e[1] + y[2] * e[2]), -(z[0] * e[0] + z[1] * e[1] + z[2] * e[2]), 1];
}
function m4mul(a, b){ const o = new Float32Array(16); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++){ let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s; } return o; }
function gxEye(c){ c = c || gx.cam; const cp = Math.cos(c.pitch); return [c.tx + c.dist * cp * Math.cos(c.yaw), c.ty + c.dist * cp * Math.sin(c.yaw), c.tz + c.dist * Math.sin(c.pitch)]; }
function gxProject(x, y, z){
  const m = gx.mvp, cw = m[3] * x + m[7] * y + m[11] * z + m[15];
  if (cw <= 1e-6) return null;
  const cx = m[0] * x + m[4] * y + m[8] * z + m[12], cy = m[1] * x + m[5] * y + m[9] * z + m[13];
  return [(cx / cw * .5 + .5) * gx.cssW, (.5 - cy / cw * .5) * gx.cssH, cw];
}

// ---------- shaders ----------
const GX_PT_VS = 'attribute vec3 a_pos;attribute float a_size;attribute vec3 a_col;uniform mat4 u_mvp;uniform float u_px;uniform float u_scale;uniform vec3 u_eye;varying float v_face;uniform float u_alpha;varying vec3 v_col;varying float v_a;' +
  'void main(){gl_Position=u_mvp*vec4(a_pos*u_scale,1.0);v_face=dot(a_pos,u_eye-a_pos*u_scale);gl_PointSize=a_size*u_px;v_col=a_col;v_a=u_alpha;if(a_size<=0.0){gl_Position=vec4(2.0,2.0,2.0,1.0);gl_PointSize=0.0;}}';
const GX_PT_FS = 'precision mediump float;varying vec3 v_col;varying float v_a;varying float v_face;uniform float u_flat;' +
  'void main(){vec2 q=gl_PointCoord*2.0-1.0;float r=dot(q,q);if(r>1.0)discard;if(u_flat>0.5){if(v_face<0.0)discard;gl_FragColor=vec4(v_col,1.0);return;}float core=1.0-smoothstep(0.0,0.42,r);float halo=exp(-r*3.5)*0.55;gl_FragColor=vec4(v_col*(core+halo)*v_a,1.0);}';
const GX_LN_VS = 'attribute vec3 a_pos;uniform mat4 u_mvp;uniform float u_scale;uniform vec3 u_off;uniform float u_fade;varying float v_f;' +
  'void main(){vec3 p=a_pos*u_scale+u_off;gl_Position=u_mvp*vec4(p,1.0);v_f=u_fade>0.0?1.0-smoothstep(0.5,1.0,length(a_pos.xy)/u_fade):1.0;}';
const GX_LN_FS = 'precision mediump float;uniform vec4 u_col;varying float v_f;void main(){gl_FragColor=vec4(u_col.rgb*u_col.a*v_f,1.0);}';
const GX_MESH_VS = 'attribute vec3 a_pos;attribute vec3 a_col;uniform mat4 u_mvp;uniform float u_scale;uniform vec3 u_eye;varying vec3 v_col;varying float v_face;' +
  'void main(){gl_Position=u_mvp*vec4(a_pos*u_scale,1.0);v_col=a_col;v_face=dot(a_pos,u_eye-a_pos*u_scale);}';
const GX_MESH_FS = 'precision mediump float;varying vec3 v_col;varying float v_face;uniform float u_inside;' +
  'void main(){if((u_inside>0.5&&v_face>0.0)||(u_inside<0.5&&v_face<0.0))discard;gl_FragColor=vec4(v_col,1.0);}';
const GX_MW_VS = 'attribute vec2 a_q;uniform mat4 u_mvp;uniform vec3 u_gc;uniform float u_R;varying vec2 v_p;' +
  'void main(){v_p=a_q*u_R/1000.0;gl_Position=u_mvp*vec4(u_gc+vec3(a_q*u_R,0.0),1.0);}';
const GX_MW_FS = 'precision mediump float;varying vec2 v_p;uniform float u_alpha;' +
  'void main(){float r=length(v_p);float c=cos(0.47),s=sin(0.47);vec2 b=vec2(v_p.x*c+v_p.y*s,-v_p.x*s+v_p.y*c);' +
  'float bulge=exp(-(b.x*b.x/22.0+b.y*b.y/6.0));float core=exp(-r*r/1.5);float disc=exp(-r/12.0)*(1.0-smoothstep(40.0,52.0,r))*0.2;' +
  'vec3 col=vec3(1.0,0.74,0.45)*(bulge*0.5+core*0.65)+vec3(0.5,0.62,0.85)*disc;gl_FragColor=vec4(col*u_alpha,1.0);}';

function gxProgram(gl, vs, fs, attrs, unis){
  const p = gl.createProgram();
  for (const [t, s] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]){
    const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh));
    gl.attachShader(p, sh);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const o = {p, a: {}, u: {}};
  for (const a of attrs) o.a[a] = gl.getAttribLocation(p, a);
  for (const u of unis) o.u[u] = gl.getUniformLocation(p, u);
  return o;
}
function gxBuf(gl, data, usage){ const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, usage || gl.STATIC_DRAW); return b; }
function gxHex(c){ return [parseInt(c.slice(1, 3), 16) / 255, parseInt(c.slice(3, 5), 16) / 255, parseInt(c.slice(5, 7), 16) / 255]; }

// ---------- geometry ----------
function gxLines(){
  const G = gx.G, out = {};
  // The Galactic-plane grid: 21 lines each way from -10 to 10, scaled per level.
  const grid = [];
  for (let k = -10; k <= 10; k++){ grid.push(k, -10, 0, k, 10, 0, -10, k, 0, 10, k, 0); }
  out.grid = new Float32Array(grid);
  // The celestial sphere: RA meridians every 30° and Dec parallels every 30°, rotated into galactic axes.
  const R = [[-0.0548755604162154, -0.8734370902348850, -0.4838350155487132], [0.4941094278755837, -0.4448296299600112, 0.7469822444972189], [-0.8676661490190047, -0.1980763734312015, 0.4559837761750669]];
  const gal = (ra, dec) => { const a = ra * Math.PI / 180, d = dec * Math.PI / 180, v = [Math.cos(d) * Math.cos(a), Math.cos(d) * Math.sin(a), Math.sin(d)]; return R.map(r => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]); };
  const sph = [], eq = [];
  for (let ra = 0; ra < 360; ra += 30) for (let d = -90; d < 90; d += 5) sph.push(...gal(ra, d), ...gal(ra, d + 5));
  for (const dec of [-60, -30, 30, 60]) for (let ra = 0; ra < 360; ra += 5) sph.push(...gal(ra, dec), ...gal(ra + 5, dec));
  for (let ra = 0; ra < 360; ra += 4) eq.push(...gal(ra, 0), ...gal(ra + 4, 0));
  out.sphere = new Float32Array(sph); out.equator = new Float32Array(eq);
  const ring = [];
  for (let a = 0; a < 360; a += 3){ const t = a * Math.PI / 180, u = (a + 3) * Math.PI / 180; ring.push(Math.cos(t), Math.sin(t), 0, Math.cos(u), Math.sin(u), 0); }
  out.ring = new Float32Array(ring);
  out.axes = new Float32Array([-1, 0, 0, 1, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, -1, 0, 0, 1]);
  return out;
}
// The Milky Way, procedural: four logarithmic arms (pitch 12°) placed so the Sun sits between two of
// them on a short spur, plus a bar. An artist's impression, labelled as one; not data.
function gxMilkyWay(){
  let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const gauss = () => { let u = 0, v = 0; while (!u) u = rnd(); while (!v) v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const gcx = gx.G.sun_to_gc_ly, b = Math.tan(12 * Math.PI / 180), r0 = 4000, pos = [], size = [], col = [];
  const push = (x, y, z, s, c) => { pos.push(gcx + x, y, z); size.push(s); col.push(...c); };
  const phase0 = Math.PI - Math.log(22000 / r0) / b;
  for (let arm = 0; arm < 4; arm++){
    const ph = phase0 + arm * Math.PI / 2;
    for (let i = 0; i < 5200; i++){
      const th = rnd() * Math.log(52000 / r0) / b, r = r0 * Math.exp(b * th) * (1 + gauss() * 0.06), a = th + ph + gauss() * 0.05;
      const k = Math.min(1, r / 30000), c = [0.55 + 0.25 * (1 - k), 0.62 + 0.18 * (1 - k), 0.95];
      push(r * Math.cos(a), r * Math.sin(a), gauss() * 280, 1.2 + rnd() * 1.6, c.map(v => v * (0.35 + rnd() * 0.5)));
    }
  }
  // The Orion spur through the Sun's place (the Sun is at angle 180°, 26,000 ly from the centre here).
  const phs = Math.PI - Math.log(gcx / r0) / b;
  for (let i = 0; i < 1600; i++){
    const th = Math.log(gcx / r0) / b + (rnd() - .5) * 0.5, r = r0 * Math.exp(b * th) * (1 + gauss() * 0.03), a = th + phs + gauss() * 0.03;
    push(r * Math.cos(a), r * Math.sin(a), gauss() * 200, 1.1 + rnd() * 1.2, [0.42, 0.5, 0.72].map(v => v * (0.5 + rnd() * 0.4)));
  }
  for (let i = 0; i < 5000; i++){
    const x = gauss() * 9000, y = gauss() * 3200, c = Math.cos(0.47), s = Math.sin(0.47);
    push(x * c - y * s, x * s + y * c, gauss() * 700, 1.4 + rnd() * 1.8, [1.0, 0.72, 0.42].map(v => v * (0.25 + rnd() * 0.45)));
  }
  return {pos: new Float32Array(pos), size: new Float32Array(size), col: new Float32Array(col), n: size.length};
}

function gxInitGL(){
  const cv = $('#gxcanvas');
  let gl = null;
  try { gl = cv.getContext('webgl', {antialias: true, alpha: false, depth: false, powerPreference: 'high-performance'}); } catch (e) { gl = null; }
  if (!gl) return false;
  gx.gl = gl;
  gx.pt = gxProgram(gl, GX_PT_VS, GX_PT_FS, ['a_pos', 'a_size', 'a_col'], ['u_mvp', 'u_px', 'u_alpha', 'u_scale', 'u_flat', 'u_eye']);
  gx.ln = gxProgram(gl, GX_LN_VS, GX_LN_FS, ['a_pos'], ['u_mvp', 'u_scale', 'u_off', 'u_fade', 'u_col']);
  gx.mwp = gxProgram(gl, GX_MW_VS, GX_MW_FS, ['a_q'], ['u_mvp', 'u_gc', 'u_R', 'u_alpha']);
  gx.mesh = gxProgram(gl, GX_MESH_VS, GX_MESH_FS, ['a_pos', 'a_col'], ['u_mvp', 'u_scale', 'u_eye', 'u_inside']);
  const H = gx.G.hosts, n = H.n.length, pos = new Float32Array(n * 3);
  for (let h = 0; h < n; h++){ pos[h * 3] = H.x[h]; pos[h * 3 + 1] = H.y[h]; pos[h * 3 + 2] = H.z[h]; }
  gx.hostPos = pos;
  gx.bHostPos = gxBuf(gl, pos);
  gx.bHostSize = gxBuf(gl, new Float32Array(n), gl.DYNAMIC_DRAW);
  gx.bHostCol = gxBuf(gl, new Float32Array(n * 3), gl.DYNAMIC_DRAW);
  gx.bSun = [gxBuf(gl, new Float32Array([0, 0, 0])), gxBuf(gl, new Float32Array([9])), gxBuf(gl, new Float32Array(gxHex('#FFB340')))];
  const L = gxLines();
  gx.lines = {};
  for (const k of Object.keys(L)) gx.lines[k] = {b: gxBuf(gl, L[k]), n: L[k].length / 3};
  gx.bQuad = gxBuf(gl, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]));
  // Survey coverage: filled patches on the celestial sphere (TESS sectors, and the sky no transit survey
  // has covered), and footprint outlines (Kepler with its cone from the Sun, K2, CoRoT, the bulge).
  const C = gx.G.coverage;
  if (C){
    // Filled patches: two triangles per 4° quad, one shade per TESS sector bucket, and the never-observed sky in grey.
    const blue = gxHex(C.colours.tess), grey = gxHex(C.colours.unmapped), M = C.mesh, st = M.step;
    const R = [[-0.0548755604162154, -0.8734370902348850, -0.4838350155487132], [0.4941094278755837, -0.4448296299600112, 0.7469822444972189], [-0.8676661490190047, -0.1980763734312015, 0.4559837761750669]];
    const gal = (ra, dec) => { const a = ra * Math.PI / 180, d = dec * Math.PI / 180, v = [Math.cos(d) * Math.cos(a), Math.cos(d) * Math.sin(a), Math.sin(d)]; return R.map(r => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]); };
    const tri = (want) => {
      const pos = [], col = [];
      for (let j = 0; j < 180 / st; j++) for (let i = 0; i < 360 / st; i++){
        const c = want(j * (360 / st) + i); if (!c) continue;
        const ra0 = i * st, ra1 = ra0 + st, d0 = -90 + j * st, d1 = d0 + st, A = gal(ra0, d0), B = gal(ra1, d0), Cc = gal(ra1, d1), Dd = gal(ra0, d1);
        pos.push(...A, ...B, ...Cc, ...A, ...Cc, ...Dd); for (let k = 0; k < 6; k++) col.push(...c);
      }
      return {pos: gxBuf(gl, new Float32Array(pos)), col: gxBuf(gl, new Float32Array(col)), n: pos.length / 3};
    };
    gx.cov = {tess: tri(q => { const n = M.tess[q]; return n ? blue.map(v => v * (n >= 13 ? .34 : n >= 3 ? .2 : .1)) : null; }),
      unmapped: tri(q => M.unmapped[q] ? grey.map(v => v * .42) : null), lines: {}};
    for (const k of ['kepler', 'k2', 'corot', 'bulge']){ const a = new Float32Array(C.lines[k]); gx.lines['cov_' + k] = {b: gxBuf(gl, a), n: a.length / 3}; }
  }
  gx.mwData = null;
  return true;
}
function gxPoints(prog, pos, size, col, n, alpha, scale, px, flat){
  const gl = gx.gl;
  gl.useProgram(prog.p);
  gl.uniform1f(prog.u.u_flat, flat ? 1 : 0);
  gl.uniform3fv(prog.u.u_eye, gxEye());
  gl.uniformMatrix4fv(prog.u.u_mvp, false, gx.mvp);
  gl.uniform1f(prog.u.u_px, px || gx.dpr);
  gl.uniform1f(prog.u.u_scale, scale || 1);
  gl.uniform1f(prog.u.u_alpha, alpha);
  for (const [b, a, k] of [[pos, 'a_pos', 3], [size, 'a_size', 1], [col, 'a_col', 3]]){
    gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(prog.a[a]); gl.vertexAttribPointer(prog.a[a], k, gl.FLOAT, false, 0, 0);
  }
  gl.drawArrays(gl.POINTS, 0, n);
}
function gxLine(name, scale, off, rgba, fade){
  const gl = gx.gl, L = gx.lines[name], p = gx.ln;
  gl.useProgram(p.p);
  gl.uniformMatrix4fv(p.u.u_mvp, false, gx.mvp);
  gl.uniform1f(p.u.u_scale, scale); gl.uniform3fv(p.u.u_off, off); gl.uniform1f(p.u.u_fade, fade || 0); gl.uniform4fv(p.u.u_col, rgba);
  gl.bindBuffer(gl.ARRAY_BUFFER, L.b); gl.enableVertexAttribArray(p.a.a_pos); gl.vertexAttribPointer(p.a.a_pos, 3, gl.FLOAT, false, 0, 0);
  gl.drawArrays(gl.LINES, 0, L.n);
}
function gxResize(){
  const cv = $('#gxcanvas'), r = cv.getBoundingClientRect();
  gx.dpr = Math.min(window.devicePixelRatio || 1, gxPhone.matches ? 1.5 : 2);
  gx.cssW = r.width; gx.cssH = r.height;
  const w = Math.max(1, Math.round(r.width * gx.dpr)), h = Math.max(1, Math.round(r.height * gx.dpr));
  if (cv.width !== w || cv.height !== h){ cv.width = w; cv.height = h; }
  gx.cards = null;
  gxKick();
}
function gxDraw(){
  const gl = gx.gl, cv = gl.canvas, c = gx.cam, d = c.dist, eye = gxEye();
  gl.viewport(0, 0, cv.width, cv.height);
  gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
  const proj = m4persp(GX_FOV, cv.width / cv.height, Math.max(0.05, d * 0.002), d * 40 + 400000);
  gx.mvp = m4mul(proj, m4look(eye, [c.tx, c.ty, c.tz], [0, 0, 1]));
  // Survey coverage first: the cells are opaque, and everything else is drawn on top of them.
  if (gx.cov && gx.view.layers.length){
    const ly = gx.view.layers, R = d * 0.62, inside = Math.hypot(...eye) < R;
    // One layer of the sphere only (the near half from outside, the far half from inside), drawn opaque
    // without blending, so the shading is even and nothing doubles up.
    gl.disable(gl.BLEND);
    const m = gx.mesh; gl.useProgram(m.p); gl.uniformMatrix4fv(m.u.u_mvp, false, gx.mvp); gl.uniform1f(m.u.u_scale, R); gl.uniform3fv(m.u.u_eye, eye); gl.uniform1f(m.u.u_inside, inside ? 1 : 0);
    for (const k of ['tess', 'unmapped']) if (ly.includes(k)){
      const c = gx.cov[k];
      gl.bindBuffer(gl.ARRAY_BUFFER, c.pos); gl.enableVertexAttribArray(m.a.a_pos); gl.vertexAttribPointer(m.a.a_pos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, c.col); gl.enableVertexAttribArray(m.a.a_col); gl.vertexAttribPointer(m.a.a_col, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, c.n);
    }
    gl.enable(gl.BLEND);
    for (const k of ['kepler', 'k2', 'corot', 'bulge']) if (ly.includes(k)) gxLine('cov_' + k, R, [0, 0, 0], gxHex(gx.G.coverage.colours[k]).concat([0.85]));
  }
  // The Milky Way fades in as the camera pulls out past ~9,000 ly; drawn only while it shows (culled otherwise).
  gx.mw = gxSmooth(9000, 42000, d);
  if (gx.mw > 0.01){
    if (!gx.mwData){
      const M = gxMilkyWay();
      gx.mwData = {n: M.n, pos: gxBuf(gl, M.pos), size: gxBuf(gl, M.size), col: gxBuf(gl, M.col)};
    }
    const p = gx.mwp;
    gl.useProgram(p.p); gl.uniformMatrix4fv(p.u.u_mvp, false, gx.mvp);
    gl.uniform3fv(p.u.u_gc, [gx.G.sun_to_gc_ly, 0, 0]); gl.uniform1f(p.u.u_R, 56000); gl.uniform1f(p.u.u_alpha, gx.mw * 0.9);
    gl.bindBuffer(gl.ARRAY_BUFFER, gx.bQuad); gl.enableVertexAttribArray(p.a.a_q); gl.vertexAttribPointer(p.a.a_q, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gxPoints(gx.pt, gx.mwData.pos, gx.mwData.size, gx.mwData.col, gx.mwData.n, gx.mw);
  }
  // Grid levels of 10, 100, 1,000 and 10,000 ly, each shown while its spacing suits the zoom.
  for (const s of [10, 100, 1000, 10000]){
    const r = d / s, a = gxSmooth(2.2, 6, r) * (1 - gxSmooth(30, 110, r));
    if (a > 0.01) gxLine('grid', s, [0, 0, 0], [1, 1, 1, 0.075 * a], 10);
  }
  const sa = 1 - gxSmooth(18000, 70000, d), R = d * 0.62;
  if (sa > 0.01){
    gxLine('sphere', R, [0, 0, 0], [1, 1, 1, 0.055 * sa]);
    gxLine('equator', R, [0, 0, 0], [1, 1, 1, 0.16 * sa]);
    gxLine('ring', R, [0, 0, 0], [0.39, 0.82, 1, 0.42 * sa]);
  }
  gxLine('axes', Math.min(27000, d * 2.6), [0, 0, 0], [0.39, 0.82, 1, 0.55]);
  gxPoints(gx.pt, gx.bHostPos, gx.bHostSize, gx.bHostCol, gx.G.hosts.n.length, 1 - 0.55 * gx.mw);
  gxPoints(gx.pt, gx.bSun[0], gx.bSun[1], gx.bSun[2], 1, 1);
}

// ---------- filters ----------
function gxRefilter(){
  const G = gx.G, v = gx.view, r = gxFilterCount(G, v), H = G.hosts, n = H.n.length, P = G.planets;
  gx.per = r.per; gx.shown = r;
  const size = new Float32Array(n), col = new Float32Array(n * 3), first = new Int32Array(n).fill(-1), on = new Set(v.methods.map(m => G.methods.indexOf(m)));
  const lim = v.dist ? v.dist / G.ly_per_pc : Infinity;
  for (let i = 0; i < P.n.length; i++){
    const h = P.h[i];
    if (!r.per[h] || (P.y[i] || 0) > v.year || !on.has(P.m[i]) || H.d[h] > lim) continue;
    if (first[h] < 0 || (P.y[i] || 0) < (P.y[first[h]] || 0)) first[h] = i;
  }
  const cols = G.methods.map(m => gxHex(G.method_colour[m]));
  for (let h = 0; h < n; h++){
    if (!r.per[h]) continue;
    size[h] = 2.6 + 1.5 * Math.sqrt(r.per[h] - 1);
    const c = cols[P.m[first[h]]];
    col[h * 3] = c[0]; col[h * 3 + 1] = c[1]; col[h * 3 + 2] = c[2];
  }
  gx.first = first;
  if (gx.gl){
    const gl = gx.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, gx.bHostSize); gl.bufferSubData(gl.ARRAY_BUFFER, 0, size);
    gl.bindBuffer(gl.ARRAY_BUFFER, gx.bHostCol); gl.bufferSubData(gl.ARRAY_BUFFER, 0, col);
  }
  $('#gxcyear').textContent = v.year;
  $('#gxccount').textContent = r.planets.toLocaleString('en-GB');
  $('#gxyearout').textContent = `${v.year} // ${r.planets.toLocaleString('en-GB')} planets`;
  $('#gxsum').textContent = `${v.year} // ${r.planets.toLocaleString('en-GB')}`;
  if (gx.sel >= 0 && !r.per[gx.sel]) gxSelect(-1);
  gx.cards = null;
  gxKick();
}
function gxControls(){
  const v = gx.view;
  $('#gxyear').value = v.year;
  $$('#gxmethods [data-gxm]').forEach(b => b.setAttribute('aria-pressed', String(v.methods.includes(b.dataset.gxm))));
  $('#gxdist').value = String(v.dist);
  $('#gxmulti').setAttribute('aria-pressed', String(v.multi));
  $('#gxshowcase').setAttribute('aria-pressed', String(!!v.showcase));
  $$('#gxcov [data-cov]').forEach(b => b.setAttribute('aria-pressed', String(v.layers.includes(b.dataset.cov))));
  $$('#gxpresets [data-gxview]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.gxview === v.view)));
}

// ---------- camera ----------
function gxPresetCam(id){
  const G = gx.G, H = G.hosts, K = G.kepler;
  if (id === 'kepler') return {tx: K.x * .55, ty: K.y * .55, tz: K.z * .55, yaw: Math.atan2(-K.y, -K.x) + 0.5, pitch: 0.32, dist: K.median_ly * 2.1};
  if (id === 'galaxy') return {tx: G.sun_to_gc_ly * 0.5, ty: 0, tz: 0, yaw: -2.5, pitch: 0.95, dist: 125000};
  if (id === 'pimen' && G.star.host != null){ const h = G.star.host; return {tx: H.x[h], ty: H.y[h], tz: H.z[h], yaw: Math.atan2(H.y[h], H.x[h]) + 0.4, pitch: 0.28, dist: 140}; }
  return {tx: 0, ty: 0, tz: 0, yaw: -2.2, pitch: 0.42, dist: 820};
}
function gxFly(to, ms){
  if (gxRM.matches || !ms || !gx.cam){ gx.cam = Object.assign({}, to); gx.flight = null; gx.cards = null; gxKick(); return; }
  const from = Object.assign({}, gx.cam);
  let dy = to.yaw - from.yaw; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
  gx.flight = {from, to: Object.assign({}, to, {yaw: from.yaw + dy}), t0: performance.now(), ms};
  gxKick();
}
function gxFlightStep(t){
  const f = gx.flight, k = Math.min(1, (t - f.t0) / f.ms), e = gxEase(k), a = f.from, b = f.to;
  // Distance moves on a log scale, so the flight passes through every zoom level smoothly; it lifts out mid-way.
  const lift = Math.sin(Math.PI * e) * Math.log(Math.max(1, Math.hypot(b.tx - a.tx, b.ty - a.ty, b.tz - a.tz) / Math.max(a.dist, b.dist))) * 0.5;
  gx.cam = {tx: a.tx + (b.tx - a.tx) * e, ty: a.ty + (b.ty - a.ty) * e, tz: a.tz + (b.tz - a.tz) * e, yaw: a.yaw + (b.yaw - a.yaw) * e,
    pitch: a.pitch + (b.pitch - a.pitch) * e, dist: Math.exp(Math.log(a.dist) + (Math.log(b.dist) - Math.log(a.dist)) * e + lift)};
  gx.dirty = true;
  if (k >= 1){ gx.flight = null; return false; }
  return true;
}
function gxZoom(f){ gx.cam.dist = Math.max(15, Math.min(260000, gx.cam.dist * f)); gx.flight = null; gxTouch(); }
function gxOrbit(dx, dy){ gx.cam.yaw -= dx; gx.cam.pitch = Math.max(-1.5, Math.min(1.5, gx.cam.pitch + dy)); gx.flight = null; gxTouch(); }
function gxTouch(){ gx.interacted = performance.now(); gx.driftAcc = 0; gx.cards = null; gxKick(); }

// ---------- picking ----------
function gxPick(px, py, maxPx){
  const H = gx.G.hosts, per = gx.per; let best = -1, bd = maxPx * maxPx, bz = Infinity;
  for (let h = 0; h < H.n.length; h++){
    if (!per[h]) continue;
    const p = gxProject(H.x[h], H.y[h], H.z[h]); if (!p) continue;
    const dd = (p[0] - px) ** 2 + (p[1] - py) ** 2;
    if (dd < bd - 1 || (Math.abs(dd - bd) <= 1 && p[2] < bz)){ bd = dd; best = h; bz = p[2]; }
  }
  return best;
}
function gxNearAim(k){
  const H = gx.G.hosts, per = gx.per, cx = gx.cssW / 2, cy = gx.cssH / 2, list = [];
  for (let h = 0; h < H.n.length; h++){
    if (!per[h]) continue;
    const p = gxProject(H.x[h], H.y[h], H.z[h]); if (!p) continue;
    list.push([(p[0] - cx) ** 2 + (p[1] - cy) ** 2, h]);
  }
  list.sort((a, b) => a[0] - b[0]);
  return list.slice(0, k).map(x => x[1]);
}
function gxHostPlanets(h){
  if (!gx.byHost){ gx.byHost = new Map(); const P = gx.G.planets; for (let i = 0; i < P.n.length; i++){ if (!gx.byHost.has(P.h[i])) gx.byHost.set(P.h[i], []); gx.byHost.get(P.h[i]).push(i); } }
  const P = gx.G.planets;
  return gx.byHost.get(h).slice().sort((a, b) => (P.y[a] || 0) - (P.y[b] || 0) || P.n[a].localeCompare(P.n[b]));
}
const gxMethod = i => gx.G.method_label[gx.G.methods[gx.G.planets.m[i]]];
const gxClass = i => { const P = gx.G.planets; if (P.c[i] == null) return '—'; return gx.G.classes[P.c[i]] + (P.r[i] == null ? (P.mk[i] === 1 ? ' (by m sin i; no radius stored)' : ' (by mass; no radius stored)') : ''); };

// ---------- overlay: labels, ticks, callouts, reticle, telemetry ----------
function gxEl(cls, html){ const e = document.createElement('div'); e.className = cls; if (html != null) e.innerHTML = html; $('#gxlayer').appendChild(e); return e; }
function gxBuildLabels(){
  const G = gx.G, L = {ticks: [], axes: [], fixed: []};
  for (const [ax, name] of [[0, 'x'], [1, 'y'], [2, 'z']]) for (const t of [250, 500, 1000, 2500, 10000, 25000]){
    const p = [0, 0, 0]; p[ax] = t;
    L.ticks.push({p, t, el: gxEl('gxlbl tick', `<span>${t.toLocaleString('en-GB')} ly</span>`)});
  }
  for (const [p, text] of [[[1, 0, 0], '→ Galactic centre'], [[0, 1, 0], 'l = 90°'], [[0, 0, 1], 'North Galactic pole']])
    L.axes.push({p, el: gxEl('gxlbl axis', text)});
  L.sun = gxEl('gxlbl sun', 'Sun');
  L.gc = gxEl('gxlbl axis', 'Galactic centre (approximate)');
  const K = G.kepler;
  L.kepler = gxEl('gxlbl region', `Kepler field · Cygnus–Lyra<small>${K.hosts.toLocaleString('en-GB')} stars · ${K.planets.toLocaleString('en-GB')} planets (${K.radius_deg}° disc)</small><small>Kepler's single deep field, not a real structure.</small>`);
  const ML = G.lensing;
  if (ML) L.lensing = gxEl('gxlbl region', `Microlensing planets<small>${ML.planets.toLocaleString('en-GB')} planets · found toward the Galactic bulge,</small><small>where the most background stars are. Distances model-dependent.</small>`);
  gx.labels = L;
  // Callout cards for the notable planets.
  gx.calls = G.notable.map((nt, k) => {
    const i = nt.planet, h = nt.host, P = G.planets, H = G.hosts;
    const el = gxEl('gxcall' + (nt.setuhq ? ' ex' : ''), `<b><i style="background:${G.method_colour[nt.method]}"></i>${esc(nt.name)}</b><p>${esc(nt.tagline)}</p><dl><dt>CLASS</dt><dd>${esc(gxClass(i))}</dd><dt>DISTANCE</dt><dd title="${gxFmt(H.d[h], 3)} pc, as listed in ${esc(G.source_short)}">${gxLy(H.d[h])} ly</dd><dt>DISCOVERED</dt><dd>${P.y[i] || '—'}</dd><dt>METHOD</dt><dd>${esc(gxMethod(i))}</dd></dl>`);
    el.dataset.stop = k + 1;
    el.style.borderLeft = `3px solid ${G.method_colour[nt.method]}`;
    el.addEventListener('click', () => { gxSelect(h, i); gxFly(gxHostCam(h), 1800); });
    el.title = 'Select; the host card opens its system view';
    const ring = gxEl('gxring' + (nt.setuhq ? ' ex' : ''));
    ring.dataset.stop = k + 1;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); $('#gxleaders').appendChild(line);
    return {nt, k, el, ring, line, w: 0, h: 0};
  });
}
function gxPlace(el, x, y, show, alpha){
  if (!show){ if (el.style.display !== 'none') el.style.display = 'none'; return; }
  if (el.style.display === 'none') el.style.display = '';
  el.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`;
  if (alpha != null) el.style.opacity = alpha.toFixed(2);
}
function gxOverlay(){
  if (!gx.labels) gxBuildLabels();
  const L = gx.labels, d = gx.cam.dist, W = gx.cssW, Hh = gx.cssH, on = (p) => p && p[0] > -40 && p[0] < W + 40 && p[1] > -20 && p[1] < Hh + 20;
  // Labels are placed in priority order (centre, Sun, survey regions, axis names, then ticks). Each must
  // sit wholly inside the stage and clear of the HUD panels, the selected-system card, the tour bar and
  // every label placed before it: it tries the four sides of its anchor and is hidden if none is free.
  $('#gxmw').hidden = gx.mw < 0.25;
  gxRadar();
  const now = performance.now();
  if (now - gx.telAt > 150){ gx.telAt = now; gxTelemetry(); }
  // Notable cards come first (they carry the most); labels then avoid them as well as the HUD.
  gxCallouts();
  const placed = gxHudRects().concat((gx.cardRects || []).map(r => r.slice())), mwEl = $('#gxmw');
  if (!mwEl.hidden){ const st = $('#gxstage').getBoundingClientRect(), b = mwEl.getBoundingClientRect(); if (b.width) placed.push([b.left - st.left, b.top - st.top, b.right - st.left, b.bottom - st.top]); }
  const size = el => { if (!el._w){ const disp = el.style.display; el.style.display = ''; const sp = el.querySelector('span'); el._w = Math.max(el.offsetWidth, sp ? sp.offsetWidth + 8 : 0) || 80; el._h = Math.max(el.offsetHeight, sp ? sp.offsetHeight + 4 : 0) || 14; el.style.display = disp; } return [el._w, el._h]; };
  const free = r => { if (r[0] < 2 || r[1] < 2 || r[2] > W - 2 || r[3] > Hh - 2) return false; for (const q of placed) if (r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]) return false; return true; };
  const SIDES = [[8, 6], [8, -6], [-8, 6], [-8, -6]];
  const put = (el, p, show, alpha, offs) => {
    if (!p || !show){ gxPlace(el, 0, 0, false); return false; }
    const [w, h] = size(el);
    for (const [dx, dy] of offs || SIDES){
      const x = p[0] + (dx < 0 ? dx - w : dx), y = p[1] + (dy < 0 ? dy - h : dy), r = [x - 3, y - 3, x + w + 3, y + h + 3];
      if (free(r)){ placed.push(r); gxPlace(el, x, y, true, alpha); return true; }
    }
    gxPlace(el, 0, 0, false); return false;
  };
  const len = Math.min(27000, d * 2.6);
  const gp = gxProject(gx.G.sun_to_gc_ly, 0, 0), gcOn = put(L.gc, gp, gx.mw > 0.3, gx.mw);
  put(L.sun, gxProject(0, 0, 0), true);
  const K = gx.G.kepler, ka = gxSmooth(500, 1400, d) * (1 - gxSmooth(30000, 60000, d));
  put(L.kepler, gxProject(K.x, K.y, K.z), ka > 0.05, ka, [[14, -30], [14, 10], [-14, -30], [-14, 10]]);
  if (L.lensing){
    const M = gx.G.lensing, ma = gxSmooth(4000, 12000, d) * (1 - gxSmooth(160000, 250000, d));
    put(L.lensing, gxProject(M.x, M.y, M.z), ma > 0.05 && gx.view.methods.includes('microlensing'), ma, [[14, 10], [14, -10], [-14, 10], [-14, -10]]);
  }
  // With the Milky Way drawn, its centre is labelled at the bulge; the axis arrow label would repeat it.
  for (const a of L.axes) put(a.el, gxProject(a.p[0] * len * .97, a.p[1] * len * .97, a.p[2] * len * .97), !(gcOn && a.p[0]), null, [[6, -6], [6, 6], [-6, -6], [-6, 6]]);
  for (const t of L.ticks){
    const p = gxProject(t.p[0], t.p[1], t.p[2]);
    // A tick label stays on its tick (the dot marks the distance), so it is shown there or not at all.
    put(t.el, p, t.t >= d * 0.05 && t.t <= len, null, [[0, 0]]);
  }
  // The reticle's target: the shown star nearest the centre of the view, within 44 px.
  const aim = gxPick(W / 2, Hh / 2, 44);
  gx.aim = aim;
  const box = $('#gxaim');
  if (aim >= 0){ const H = gx.G.hosts, p = gxProject(H.x[aim], H.y[aim], H.z[aim]); box.hidden = false; box.style.transform = `translate(${p[0]}px,${p[1]}px)`; }
  else box.hidden = true;
}
function gxCallouts(){
  const G = gx.G, H = G.hosts, d = gx.cam.dist, eye = gxEye(), W = gx.cssW, Hh = gx.cssH, zoomA = 1 - gxSmooth(2500, 6000, d);
  const svg = $('#gxleaders'), hudR = gxHudRects();
  svg.setAttribute('viewBox', `0 0 ${W} ${Hh}`);
  const items = [];
  for (const c of gx.calls){
    const h = c.nt.host, shown = gx.per[h] > 0 && G.planets.y[c.nt.planet] <= gx.view.year && (!gx.view.showcase || c.nt.showcase || gx.selPlanet === c.nt.planet);
    const p = shown ? gxProject(H.x[h], H.y[h], H.z[h]) : null;
    const dist = Math.hypot(H.x[h] - eye[0], H.y[h] - eye[1], H.z[h] - eye[2]);
    // Cards fade with their distance from the camera, and as the camera pulls out past a few thousand ly.
    const alpha = zoomA * Math.max(0, Math.min(1, 1.6 - dist / (2.2 * d)));
    const pri = (gx.selPlanet === c.nt.planet ? 0 : gx.tour && gx.tour.k === c.k ? 1 : c.nt.setuhq ? 2 : 3) * 1e9 + dist;
    items.push({c, p, alpha, pri});
  }
  items.sort((a, b) => a.pri - b.pri);
  // Every candidate's ring is an obstacle for the other cards, and a ring must sit wholly inside the stage.
  const rings = items.filter(it => it.p && it.alpha > 0.34).map(it => [it.p[0] - 14, it.p[1] - 14, it.p[0] + 14, it.p[1] + 14, it]);
  const taken = [];
  for (const it of items){
    const c = it.c;
    // No ghosts: a card fainter than a third is hidden outright, and cards rest while the camera flies.
    let ok = it.p && it.alpha > 0.34 && !gx.flight && it.p[0] > 14 && it.p[0] < W - 14 && it.p[1] > 14 && it.p[1] < Hh - 14;
    let x = 0, y = 0;
    if (ok){
      if (!c.w){ c.el.style.display = ''; c.w = c.el.offsetWidth; c.h = c.el.offsetHeight; }
      x = it.p[0] + 26; y = it.p[1] - 26 - c.h;
      if (x + c.w > W - 8) x = it.p[0] - 26 - c.w;
      if (y < 8) y = it.p[1] + 26;
      const r = [x - 4, y - 4, x + c.w + 4, y + c.h + 4];
      if (x < 4 || y < 4 || x + c.w > W - 4 || y + c.h > Hh - 4) ok = false;
      // Never overlap: a card that would cover a higher-priority card (or the HUD) is hidden.
      for (const q of taken) if (r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]){ ok = false; break; }
      if (ok) for (const q of rings) if (q[4] !== it && r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]){ ok = false; break; }
      if (ok) for (const q of hudR) if (r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]){ ok = false; break; }
      if (ok) taken.push(r);
    }
    c.el.classList.toggle('sel', gx.selPlanet === c.nt.planet);
    gxPlace(c.el, x, y, ok, it.alpha);
    gxPlace(c.ring, it.p ? it.p[0] : 0, it.p ? it.p[1] : 0, ok, it.alpha);
    if (ok){
      const ax = x > it.p[0] ? x : x + c.w, ay = y > it.p[1] ? y : y + c.h;
      c.line.setAttribute('x1', it.p[0] + (ax > it.p[0] ? 9 : -9)); c.line.setAttribute('y1', it.p[1] + (ay > it.p[1] ? 9 : -9));
      c.line.setAttribute('x2', ax); c.line.setAttribute('y2', ay); c.line.style.opacity = it.alpha; c.line.style.display = '';
    } else c.line.style.display = 'none';
  }
  gx.cardRects = taken;
}
function gxHudRects(){
  // Measured every frame: the telemetry panel grows and shrinks with its text.
  const st = $('#gxstage').getBoundingClientRect(), r = [];
  for (const sel of ['.gxtr', '.gxbl', '#gxtourbar', '#gxcard']){
    const el = $(sel); if (!el || el.hidden) continue;
    const b = el.getBoundingClientRect(); if (!b.width) continue;
    r.push([b.left - st.left - 2, b.top - st.top - 2, b.right - st.left + 2, b.bottom - st.top + 2]);
  }
  return r;
}
function gxRadar(){
  // The camera looks along -(cos yaw, sin yaw): its heading in galactic longitude, shown on the radar.
  const c = gx.cam, l = (Math.atan2(-Math.sin(c.yaw), -Math.cos(c.yaw)) * 180 / Math.PI + 360) % 360;
  // Radar is drawn heading-up: the Galactic centre (l = 0) sits at -l from the top.
  $('#gxgc').setAttribute('transform', `rotate(${(-l).toFixed(1)})`);
  gx.heading = l;
}
function gxTelemetry(){
  const G = gx.G, H = G.hosts, P = G.planets, pad = (k, v) => k.padEnd(8) + v;
  const c = gx.cam, lines = [`<b>HDG</b> l ${gx.heading.toFixed(0).padStart(3, '0')}°  <b>ELV</b> ${(c.pitch * 180 / Math.PI).toFixed(0)}°`,
    `<b>FIELD</b> ${gxFmt(Math.round(2 * c.dist * Math.tan(GX_FOV / 2)), 0)} ly across`];
  if (gx.selPlanet >= 0){
    const i = gx.selPlanet, h = P.h[i], r = P.r[i], m = P.ms[i];
    lines.push('', `<b>${esc(P.n[i])}</b>`,
      pad('PERIOD', P.p[i] == null ? '—' : gxSig(P.p[i]) + ' d'),
      pad('RADIUS', r == null ? '—' : `${gxSig(r * G.rj_in_re)} R⊕ · ${gxSig(r)} RJ`),
      pad(P.mk[i] === 1 ? 'M SIN I' : 'MASS', m == null ? '—' : `${gxSig(m * G.mj_in_me)} M⊕ · ${gxSig(m)} MJ`),
      pad('CLASS', gxClass(i)), pad('HOST', esc(H.n[h])), pad('HOST V', H.v[h] == null ? '—' : gxSig(H.v[h]) + ' mag'),
      pad('DIST', `${gxLy(H.d[h])} ly · ${gxFmt(H.d[h], 3)} pc`));
  } else {
    if (gx.aim >= 0){
      const h = gx.aim;
      lines.push('', '<b>AIM</b>', pad('RA', gxFmt(H.ra[h], 3) + '°') + '  ' + 'DEC ' + gxFmt(H.dec[h], 3) + '°', pad('DIST', `${gxLy(H.d[h])} ly · ${gxFmt(H.d[h], 3)} pc`));
    }
    lines.push('', '<b>NEAR AIM</b>');
    for (const h of gxNearAim(4)) lines.push(`SYS ${esc(H.n[h].slice(0, 16))} // ${String(G.host_n[h]).padStart(2, '0')} PLANET${G.host_n[h] === 1 ? '' : 'S'}`);
  }
  $('#gxtel').innerHTML = lines.join('\n');
}

// ---------- selection: the host card and the tooltip ----------
function gxHostCam(h){ const H = gx.G.hosts; return {tx: H.x[h], ty: H.y[h], tz: H.z[h], yaw: gx.cam.yaw, pitch: gx.cam.pitch, dist: Math.max(60, Math.min(gx.cam.dist, 400))}; }
function gxSelect(h, planet){
  const card = $('#gxcard'), G = gx.G, H = G.hosts, P = G.planets;
  if (gx.view && gx.view.focus && (h < 0 || H.n[h] !== gx.view.focus)){ gx.view.focus = ''; syncGalaxyURL(false); $('#gxfocusnote').hidden = true; }
  gx.sel = h; gx.selPlanet = h >= 0 ? (planet != null ? planet : gxHostPlanets(h)[0]) : -1;
  $('#gxstage').classList.toggle('sel', h >= 0);
  gx.hud = null; gx.cards = null;
  if (h < 0){ card.hidden = true; gxKick(); return; }
  const ps = gxHostPlanets(h), star = G.star;
  const lensNote = ps.some(i => G.methods[P.m[i]] === 'microlensing') ? '<p>Found by microlensing; the distance comes from a model of the event. <a href="' + R('#/methods?ch=microlensing') + '">How microlensing works ›</a></p>' : '';
  const exo = star.host === h ? `<p>SetuHQ's run reviewed this star's TESS light curve: ${esc(star.planet || '')} is the planet it recovered. <a href="${R(`#/transit${star.lead_dip ? '?dip=' + encodeURIComponent(star.lead_dip) : ''}`)}">Open the Transit case ›</a></p>` : '';
  card.innerHTML = `<button class="btn x" type="button" aria-label="Close">×</button><h3>${esc(H.n[h])}</h3>
    <p class="mono">${gxLy(H.d[h])} ly · ${gxFmt(H.d[h], 3)} pc · RA ${gxFmt(H.ra[h], 3)}° Dec ${gxFmt(H.dec[h], 3)}° · V ${H.v[h] == null ? '—' : gxSig(H.v[h])}</p>
    <p>${G.host_n[h]} planet${G.host_n[h] === 1 ? '' : 's'} in ${esc(G.source_short)}${G.host_n[h] > gx.per[h] ? `, ${gx.per[h]} shown by the filters` : ''}.</p>
    ${gxLinks(h)}<ul>${ps.map(i => `<li><button type="button" data-gxp="${i}" aria-pressed="${i === gx.selPlanet}">${esc(P.n[i])}<span>${P.y[i] || '—'} · ${esc(gxMethod(i))} · ${esc(gxClass(i))}</span></button>${typeof MX !== 'undefined' && MX && MX.examples[P.n[i]] ? `<button class="btn gxsys" type="button" data-gxsys="${esc(P.n[i])}">Open the system view ›</button>` : ''}</li>`).join('')}</ul>${exo}${lensNote}`;
  card.hidden = false;
  gxKick();
  // Mission Control's linked selection: the star picked here is selected in every pane and window.
  if (typeof mcBrush === 'function') mcBrush(H.n[h], 'galaxy');
}
// Where a host is on screen (for the zoom lens into its system view), or null when it is behind the camera.
function gxScreenPoint(h){
  if (h < 0 || !gx.mvp) return null;
  const H = gx.G.hosts, p = gxProject(H.x[h], H.y[h], H.z[h]), r = $('#gxcanvas').getBoundingClientRect();
  return p ? {x: r.left + p[0], y: r.top + p[1], kind: 'galaxy'} : null;
}
const gxElPoint = el => { const r = el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, kind: 'galaxy'}; };
// The canonical pages for the selected star and planet (a free-floating planet is its own host: no star page).
function gxLinks(h){
  const G = gx.G, H = G.hosts, P = G.planets, ps = gxHostPlanets(h), starless = ps.length === 1 && P.n[ps[0]] === H.n[h];
  return `<div class="pllinks gxlinks">${starless ? '' : objLink('star', H.n[h], 'Star page ›')}${gx.selPlanet >= 0 ? objLink('planet', P.n[gx.selPlanet], P.n[gx.selPlanet] + ' ›') : ''}</div>`;
}
function gxTip(h, x, y){
  const tip = $('#gxtip');
  if (h < 0){ tip.hidden = true; return; }
  const G = gx.G, H = G.hosts, P = G.planets, ps = gxHostPlanets(h);
  const lens = ps.some(i => G.methods[P.m[i]] === 'microlensing') ? '<br><span class="mono">distance model-dependent (microlensing)</span>' : '';
  tip.innerHTML = `<b>${esc(H.n[h])}</b> · ${G.host_n[h]} planet${G.host_n[h] === 1 ? '' : 's'}<br><span class="mono">${gxLy(H.d[h])} ly (${gxFmt(H.d[h], 3)} pc)</span>${lens}<br>` +
    ps.slice(0, 4).map(i => `${esc(P.n[i])} <span class="mono">· ${P.y[i] || '—'} · ${esc(gxMethod(i))}</span>`).join('<br>') + (ps.length > 4 ? `<br><span class="mono">and ${ps.length - 4} more</span>` : '');
  tip.hidden = false;
  const w = tip.offsetWidth, hh = tip.offsetHeight;
  tip.style.transform = `translate(${Math.min(x + 14, gx.cssW - w - 8)}px,${Math.max(8, Math.min(y + 14, gx.cssH - hh - 8))}px)`;
}

// ---------- timeline and tour ----------
function gxPlay(){
  if (gx.play){ gx.play = null; $('#gxplay').textContent = `Play ${GXM.years[0]}–${GXM.years[1]}`; syncGalaxyURL(false); return; }
  gx.view.year = GXM.years[0]; gxRefilter(); gxControls();
  gx.play = {t0: performance.now(), per: gxRM.matches ? 650 : 380};
  $('#gxplay').textContent = 'Pause';
  gxKick();
}
function gxPlayStep(t){
  const p = gx.play, y = Math.min(GXM.years[1], GXM.years[0] + Math.floor((t - p.t0) / p.per));
  if (y !== gx.view.year){ gx.view.year = y; gxRefilter(); $('#gxyear').value = y; }
  if (y >= GXM.years[1]){ gx.play = null; $('#gxplay').textContent = `Play ${GXM.years[0]}–${GXM.years[1]}`; syncGalaxyURL(false); say(`${y}: ${gx.shown.planets.toLocaleString('en-GB')} planets.`); return false; }
  return true;
}
function gxTourGo(k, push){
  const G = gx.G, n = G.notable.length; if (!n) return;
  k = ((k % n) + n) % n;
  const nt = G.notable[k];
  if (!gx.tour) gx.tour = {k, paused: false, t0: 0};
  gx.tour.k = k; gx.tour.t0 = performance.now();
  $('#gxtourbar').hidden = false; gx.hud = null;
  $('#gxtlabel').textContent = `${k + 1} of ${n} · ${nt.name}`;
  $('#gxtpause').textContent = gx.tour.paused ? 'Resume' : 'Pause';
  // A stop must be visible: the tour shows every year, method and distance.
  if (gx.view.year !== GXM.years[1] || gx.view.methods.length !== GXM.methods.length || gx.view.dist || gx.view.multi){
    Object.assign(gx.view, {year: GXM.years[1], methods: GXM.methods.slice(), dist: 0, multi: false}); gxRefilter(); gxControls();
  }
  gx.view.tour = k + 1;
  gxSelect(nt.host, nt.planet);
  const H = G.hosts, h = nt.host;
  gxFly({tx: H.x[h], ty: H.y[h], tz: H.z[h], yaw: Math.atan2(H.y[h], H.x[h]) + 0.5 + k * 0.3, pitch: 0.3, dist: 120}, 2200);
  syncGalaxyURL(!!push);
}
function gxTourStep(t){ if (t - gx.tour.t0 > 6000){ gxTourGo(gx.tour.k + 1, false); } return true; }
function gxTourEnd(){ gx.tour = null; $('#gxtourbar').hidden = true; gx.hud = null; gx.view.tour = 0; syncGalaxyURL(true); gxKick(); }

// ---------- the loop: runs only while the section is on screen and the tab is visible ----------
function gxLive(){ const st = $('#gxstage'); return gx.on && gx.visible && !document.hidden && !!st && st.getClientRects().length > 0; }
function gxKick(){ gx.dirty = true; if (gxLive() && !gx.raf) gx.raf = requestAnimationFrame(gxFrame); }
function gxFrame(t){
  gx.raf = 0;
  if (!gxLive()){ gx.last = 0; return; }
  const dt = gx.last ? Math.min(100, t - gx.last) : 16; gx.last = t;
  let anim = false;
  if (gx.flight) anim = gxFlightStep(t) || anim;
  // A slow drift when nobody is steering (never under reduced motion, never during the tour).
  // The drift rests after one full turn, or 30 s after the last touch, whichever comes first.
  const idle = t - gx.interacted, drift = !gxRM.matches && gx.auto && !gx.tour && !gx.drag && (gx.driftAcc || 0) < 2 * Math.PI && idle < 36000;
  if (drift){ anim = true; if (!gx.flight && idle > 6000){ const dy = dt * 0.00005; gx.cam.yaw += dy; gx.driftAcc = (gx.driftAcc || 0) + dy; gx.dirty = true; } }
  if (gx.play) anim = gxPlayStep(t) || anim;
  if (gx.tour && !gx.tour.paused) anim = gxTourStep(t) || anim;
  if (gx.dirty){ gx.dirty = false; gxDraw(); gxOverlay(); gx.frames++; }
  if (anim || gx.dirty) gx.raf = requestAnimationFrame(gxFrame);
  else gx.last = 0;
}
// The map runs on its own page, and in Mission Control while its pane is shown (in this window, or as this
// popped-out window); anywhere else it sleeps.
function gxWanted(){
  if (current === 'galaxy') return true;
  if (current !== 'mission' || typeof mc === 'undefined' || !mc.layout || mc.layout.hidden.includes('galaxy')) return false;
  return mc.pop ? mc.pop === 'galaxy' : !mc.popped.has('galaxy');
}
function gxShown(on){
  gx.on = on;
  if (on && gx.ready){ gxResize(); gxKick(); }
  if (!on && gx.play) gxPlay();
}

function applyGalaxy(v){
  const prev = gx.view; gx.view = v;
  if (!gx.ready) return;
  gxRefilter(); gxControls();
  if (v.tour){ if (!prev || prev.tour !== v.tour) gxTourGo(v.tour - 1, false); }
  else if (gx.tour) { gx.tour = null; $('#gxtourbar').hidden = true; }
  if (!v.tour && (!prev || prev.view !== v.view)) gxFly(gxPresetCam(v.view), 2400);
  if (v.focus && (!prev || prev.focus !== v.focus)) gxFocus(v.focus);
  if (!v.focus) $('#gxfocusnote').hidden = true;
}
// A deep link from a planet or star page (#/galaxy?focus=<host name>): select that star and fly to it.
function gxFocus(name){
  const h = gx.G.hosts.n.indexOf(name), note = $('#gxfocusnote');
  note.hidden = h >= 0;
  if (h < 0){ note.innerHTML = `No star “${esc(name)}” on the map (no stored distance or not in the catalogue). <a href="${R(`#/catalogue?q=${encodeURIComponent(name)}`)}">Search the Catalogue ›</a>`; return; }
  gxSelect(h); gxFly(Object.assign(gxHostCam(h), {dist: 140}), 2400);
}
function syncGalaxyURL(push){ if (current !== 'galaxy' || !gx.view) return; const q = encodeGalaxyView(gx.view); setHash('#/galaxy' + (q ? '?' + q : ''), !!push); }

function renderGalaxy(){
  if (!GXM) return;
  const note = $('#gxload'); note.hidden = false;
  gxLoad().then(() => { note.hidden = true; gxStart(); gxShown(gxWanted()); }).catch(() => {
    note.textContent = 'The map data could not be loaded here. The table below lists the nearest systems, and the CSV holds every plotted planet.';
  });
}
function gxStart(){
  const cv = $('#gxcanvas');
  let ok = false;
  try { ok = gxInitGL(); } catch (e) { ok = false; }
  if (!ok){ $('#gxnogl').hidden = false; cv.removeAttribute('tabindex'); return; }
  if (!gx.view) gx.view = decodeGalaxyView(new URLSearchParams());
  // First view: a short pull-in to the preset (a cut under reduced motion).
  const target = gxPresetCam(gx.view.view);
  gx.cam = gxRM.matches ? Object.assign({}, target) : Object.assign({}, target, {dist: target.dist * 4, yaw: target.yaw - 0.6});
  gx.ready = true;
  gxRefilter(); gxControls();
  if (gx.view.tour) gxTourGo(gx.view.tour - 1, false); else gxFly(target, 2600);
  if (gx.view.focus) gxFocus(gx.view.focus);
  if (gxPhone.matches) $('#gxsheet').open = false;
  // Pointer: drag to orbit, two fingers to pinch-zoom, click to select, double-click to centre.
  cv.addEventListener('pointerdown', e => {
    cv.setPointerCapture(e.pointerId);
    gx.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    gx.drag = {x: e.clientX, y: e.clientY, moved: 0, pinch: gx.pointers.size === 2 ? gxPinch() : 0};
    gxTip(-1); gxTouch();
  });
  cv.addEventListener('pointermove', e => {
    const r = cv.getBoundingClientRect();
    if (!gx.pointers.has(e.pointerId)){
      if (e.pointerType === 'mouse' && gx.mvp){ const h = gxPick(e.clientX - r.left, e.clientY - r.top, 12); gx.hover = h; gxTip(h, e.clientX - r.left, e.clientY - r.top); cv.style.cursor = h >= 0 ? 'pointer' : ''; }
      return;
    }
    const last = gx.pointers.get(e.pointerId); gx.pointers.set(e.pointerId, [e.clientX, e.clientY]);
    if (gx.pointers.size === 2){ const p = gxPinch(); if (gx.drag.pinch) gxZoom(gx.drag.pinch / p); gx.drag.pinch = p; gx.drag.moved += 10; return; }
    const dx = e.clientX - last[0], dy = e.clientY - last[1];
    gx.drag.moved += Math.abs(dx) + Math.abs(dy);
    gxOrbit(dx * 0.006, dy * 0.006);
  });
  const up = e => {
    if (!gx.pointers.has(e.pointerId)) return;
    gx.pointers.delete(e.pointerId);
    if (gx.drag && gx.drag.moved < 6 && e.type === 'pointerup' && gx.mvp){
      const r = cv.getBoundingClientRect(), h = gxPick(e.clientX - r.left, e.clientY - r.top, e.pointerType === 'mouse' ? 12 : 22);
      if (h >= 0) gxSelect(h); else if (gx.sel >= 0) gxSelect(-1);
    }
    if (!gx.pointers.size) gx.drag = null; else if (gx.drag) gx.drag.pinch = gx.pointers.size === 2 ? gxPinch() : 0;
    gxTouch();
  };
  cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
  cv.addEventListener('pointerleave', () => { if (!gx.pointers.size) gxTip(-1); });
  cv.addEventListener('wheel', e => { e.preventDefault(); gxZoom(Math.exp(Math.max(-1, Math.min(1, e.deltaY * (e.deltaMode ? 0.05 : 0.0015))))); }, {passive: false});
  cv.addEventListener('dblclick', e => {
    const r = cv.getBoundingClientRect(), h = gxPick(e.clientX - r.left, e.clientY - r.top, 16);
    if (h >= 0){ gxSelect(h); gxFly(gxHostCam(h), 1600); } else gxFly(Object.assign({}, gx.cam, {tx: 0, ty: 0, tz: 0}), 1200);
    gxTouch();
  });
  cv.addEventListener('keydown', e => {
    const k = e.key, s = 0.08;
    if (k === 'ArrowLeft') gxOrbit(-s, 0); else if (k === 'ArrowRight') gxOrbit(s, 0);
    else if (k === 'ArrowUp') gxOrbit(0, s); else if (k === 'ArrowDown') gxOrbit(0, -s);
    else if (k === '+' || k === '=') gxZoom(0.8); else if (k === '-' || k === '_') gxZoom(1.25);
    else if (k === 'Enter'){ if (gx.aim >= 0){ gxSelect(gx.aim); say(`Selected ${gx.G.hosts.n[gx.aim]}.`); } }
    else if (k === 'Escape'){ if (gx.tour) gxTourEnd(); else gxSelect(-1); }
    else if (k === 'Home' || k === '0') gxFly(gxPresetCam(gx.view.view), 1400);
    else return;
    e.preventDefault();
  });
  $('#gxcard').addEventListener('click', e => {
    if (e.target.closest('.x')){ gxSelect(-1); cv.focus({preventScroll: true}); return; }
    const sys = e.target.closest('button[data-gxsys]'); if (sys){ mxOpenSystem(sys.dataset.gxsys, sys, gxScreenPoint(gx.sel) || gxElPoint(sys)); return; }
    const b = e.target.closest('button[data-gxp]'); if (!b) return;
    gxSelect(gx.sel, Number(b.dataset.gxp)); const nb = $(`#gxcard button[data-gxp="${b.dataset.gxp}"]`); if (nb) nb.focus();
  });
  $('#gxpresets').addEventListener('click', e => {
    const b = e.target.closest('button[data-gxview]'); if (!b) return;
    if (gx.tour) gxTourEnd();
    gx.view.view = b.dataset.gxview; gxControls(); gxFly(gxPresetCam(gx.view.view), 2600); syncGalaxyURL(true);
    say(`View: ${GXM.preset_label[gx.view.view]}.`);
  });
  $('#gxyear').addEventListener('input', e => { if (gx.play) gxPlay(); gx.view.year = Number(e.target.value); gxRefilter(); });
  $('#gxyear').addEventListener('change', () => syncGalaxyURL(true));
  $('#gxplay').addEventListener('click', gxPlay);
  $('#gxmethods').addEventListener('click', e => {
    const b = e.target.closest('button[data-gxm]'); if (!b) return;
    const m = b.dataset.gxm, on = gx.view.methods.includes(m);
    gx.view.methods = on ? gx.view.methods.filter(x => x !== m) : GXM.methods.filter(x => x === m || gx.view.methods.includes(x));
    gxRefilter(); gxControls(); syncGalaxyURL(true);
  });
  $('#gxdist').addEventListener('change', e => { gx.view.dist = Number(e.target.value); gxRefilter(); syncGalaxyURL(true); });
  $('#gxmulti').addEventListener('click', () => { gx.view.multi = !gx.view.multi; gxRefilter(); gxControls(); syncGalaxyURL(true); });
  const cov = $('#gxcov');
  if (cov) cov.addEventListener('click', e => {
    const b = e.target.closest('button[data-cov]'); if (!b) return;
    const k = b.dataset.cov, on = gx.view.layers.includes(k);
    gx.view.layers = GXM.layers.filter(x => x === k ? !on : gx.view.layers.includes(x));
    gxControls(); gxKick(); syncGalaxyURL(true);
  });
  $('#gxshowcase').addEventListener('click', () => { gx.view.showcase = !gx.view.showcase; gxControls(); gx.cards = null; gxKick(); syncGalaxyURL(true); });
  $('#gxtour').addEventListener('click', () => { if (gx.tour) gx.tour.paused = false; gxTourGo(gx.tour ? gx.tour.k : 0, true); $('#gxtpause').focus(); });
  $('#gxtprev').addEventListener('click', () => gxTourGo(gx.tour.k - 1, true));
  $('#gxtnext').addEventListener('click', () => gxTourGo(gx.tour.k + 1, true));
  $('#gxtpause').addEventListener('click', () => { gx.tour.paused = !gx.tour.paused; gx.tour.t0 = performance.now(); $('#gxtpause').textContent = gx.tour.paused ? 'Resume' : 'Pause'; gxKick(); });
  $('#gxtexit').addEventListener('click', () => { gxTourEnd(); $('#gxtour').focus(); });
  $$('.gxnot').forEach(b => b.addEventListener('click', () => { if (gx.tour) gx.tour.paused = true; gxTourGo(Number(b.dataset.gxstop) - 1, true); if (gx.tour) $('#gxtpause').textContent = 'Resume'; $('#gxstage').scrollIntoView({block: 'nearest', behavior: gxRM.matches ? 'auto' : 'smooth'}); }));
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { gx.visible = es[0].isIntersecting; gxKick(); }).observe($('#gxstage'));
  else gx.visible = true;
  document.addEventListener('visibilitychange', () => { gx.last = 0; gxKick(); });
  if (window.ResizeObserver) new ResizeObserver(() => { gx.hud = null; gxResize(); }).observe($('#gxstage'));
  gxRM.addEventListener && gxRM.addEventListener('change', gxKick);
  gxResize();
}
function gxPinch(){ const p = [...gx.pointers.values()]; return Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) || 1; }
"""


# ---------- survey coverage (scripts/survey_coverage.py writes it) ----------
DEFAULT_COVERAGE = "docs/results/survey_coverage.json"
COV_LAYERS = [("tess", "TESS sectors"), ("kepler", "Kepler field"), ("k2", "K2 campaigns"), ("corot", "CoRoT zones"),
              ("bulge", "Bulge microlensing"), ("unmapped", "Unmapped by transit surveys")]
COV_COLOUR = {"tess": "#0A84FF", "kepler": "#FFB340", "k2": "#30D158", "corot": "#BF5AF2", "bulge": "#FF6961",
              "unmapped": "#8E8E93"}


def load_coverage(path: str | Path | None = DEFAULT_COVERAGE) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def _gal_unit(ra: float, dec: float) -> list[float]:
    return [round(v, 4) for v in _rot(_unit(ra, dec))]


def _ring(ra0: float, dec0: float, radius_deg: float, n: int = 72) -> list[tuple[float, float]]:
    """Points on a small circle of the sky, as (ra, dec)."""
    c = _unit(ra0, dec0)
    # Two axes perpendicular to the centre.
    a = (-math.sin(math.radians(ra0)), math.cos(math.radians(ra0)), 0.0)
    b = (c[1] * a[2] - c[2] * a[1], c[2] * a[0] - c[0] * a[2], c[0] * a[1] - c[1] * a[0])
    r = math.radians(radius_deg)
    out = []
    for k in range(n + 1):
        t = 2 * math.pi * k / n
        v = [math.cos(r) * c[i] + math.sin(r) * (math.cos(t) * a[i] + math.sin(t) * b[i]) for i in range(3)]
        out.append((math.degrees(math.atan2(v[1], v[0])) % 360, math.degrees(math.asin(max(-1, min(1, v[2]))))))
    return out


def _bulge_outline(b: dict, n: int = 24) -> list[tuple[float, float]]:
    """The bulge box (galactic l, b) as ICRS (ra, dec) points."""
    l0, l1 = b["l"]
    b0, b1 = b["b"]
    pts = ([(l0 + (l1 - l0) * k / n, b0) for k in range(n)] + [(l1, b0 + (b1 - b0) * k / n) for k in range(n)]
           + [(l1 - (l1 - l0) * k / n, b1) for k in range(n)] + [(l0, b1 - (b1 - b0) * k / n) for k in range(n + 1)])
    out = []
    for lon, lat in pts:
        g = _unit(lon, lat)  # galactic unit vector; the transpose rotates it back to ICRS
        v = [sum(ICRS_TO_GAL[j][i] * g[j] for j in range(3)) for i in range(3)]
        out.append((math.degrees(math.atan2(v[1], v[0])) % 360, math.degrees(math.asin(max(-1, min(1, v[2]))))))
    return out


def modules(channels: list) -> list:
    """Kepler's 84 science channels, four per CCD module, merged into 21 module outlines (convex hulls)."""
    out = []
    for k in range(0, len(channels), 4):
        pts = [pt for c in channels[k:k + 4] for pt in c]
        ra0 = pts[0][0]
        loc = sorted({(((p[0] - ra0 + 180) % 360 - 180), p[1]) for p in pts})
        cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
        lower, upper = [], []
        for q in loc:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
                lower.pop()
            lower.append(q)
        for q in reversed(loc):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
                upper.pop()
            upper.append(q)
        out.append([[round((x + ra0) % 360, 3), y] for x, y in lower[:-1] + upper[:-1]])
    return out


def coverage_gl(cov: dict | None) -> dict | None:
    """What the 3D map draws: sky cells as galactic unit vectors with their TESS count and flags, and the
    footprint outlines as unit-vector line segments."""
    if cov is None:
        return None
    dr = cov["draw"]
    cells = [_gal_unit(a, d) for a, d in zip(dr["ra"], dr["dec"])]
    kep, k2 = set(dr["kepler"]), set(dr["k2"])

    def segs(polys):
        out = []
        for p in polys:
            for k in range(len(p)):
                a, b = p[k], p[(k + 1) % len(p)]
                out += _gal_unit(*a) + _gal_unit(*b)
        return out

    def strip(pts):
        out = []
        for a, b in zip(pts, pts[1:]):
            out += _gal_unit(*a) + _gal_unit(*b)
        return out

    kc = cov["kepler"]["channels"]
    # The cone: lines from the Sun to the four corner points of the field farthest from its centre.
    centre = _unit(cov["kepler"]["ra"], cov["kepler"]["dec"])
    corners = sorted((pt for p in kc for pt in p), key=lambda q: sum(x * y for x, y in zip(_unit(*q), centre)))[:40]
    picks = []
    for q in corners:
        if all(sum(x * y for x, y in zip(_unit(*q), _unit(*r))) < math.cos(math.radians(5)) for r in picks):
            picks.append(q)
        if len(picks) == 4:
            break
    cone = []
    for q in picks:
        cone += [0, 0, 0] + _gal_unit(*q)
    # A 4° × 4° RA/Dec mesh for the 3D sphere: each quad takes the TESS sector count of the nearest
    # drawn cell (0 = never observed), so the layer is drawn as filled patches, not dots.
    import numpy as np

    cu = np.array([_unit(a, d) for a, d in zip(dr["ra"], dr["dec"])])
    centres = [(4 * i + 2, -88 + 4 * j) for j in range(45) for i in range(90)]
    qu = np.array([_unit(a, d) for a, d in centres])
    near = np.argmax(qu @ cu.T, axis=1)
    mesh_tess = [int(dr["tess"][k]) for k in near]
    mesh_unm = [int(dr["tess"][k] == 0 and k not in kep and k not in k2) for k in near]
    return {
        "mesh": {"step": 4, "tess": mesh_tess, "unmapped": mesh_unm},
        "tess_n": len(dr["tess"]),
        "lines": {"kepler": segs(modules(kc)) + cone, "k2": segs([p for c in cov["k2"] for p in modules(c["channels"])]),
                  "corot": [v for e in cov["corot"]["eyes"] for v in strip(_ring(e["ra"], e["dec"], cov["corot"]["radius_deg"]))],
                  "bulge": strip(_bulge_outline(cov["bulge"]))},
        "colours": COV_COLOUR, "layers": [k for k, _ in COV_LAYERS],
    }


def _moll_path(pts, close=False) -> str:
    from setuhq.story import mollweide

    out, last = [], None
    for ra, dec in pts:
        x, y = mollweide(ra, dec)
        out.append(("M" if last is None or abs(x - last[0]) > 300 else "L") + f"{x:.1f} {y:.1f}")
        last = (x, y)
    s = "".join(out)
    return s + ("Z" if close and "M" not in s[1:] else "")


def sky_layers_svg(cov: dict | None) -> str:
    """The coverage layers on the Sky section's Mollweide map, each a group the page shows or hides."""
    if cov is None:
        return ""
    from setuhq.story import mollweide

    dr = cov["draw"]
    kep, k2 = set(dr["kepler"]), set(dr["k2"])
    buckets = {1: [], 3: [], 13: []}
    unm = []
    for i, (a, d) in enumerate(zip(dr["ra"], dr["dec"])):
        x, y = mollweide(a, d)
        n = dr["tess"][i]
        if n >= 13:
            buckets[13].append((x, y))
        elif n >= 3:
            buckets[3].append((x, y))
        elif n >= 1:
            buckets[1].append((x, y))
        elif i not in kep and i not in k2:
            unm.append((x, y))
    dots = lambda pts: "".join(f"M{x:.1f} {y:.1f}h0" for x, y in pts)  # noqa: E731
    tess = "".join(f'<path d="{dots(buckets[k])}" stroke="#0A84FF" stroke-opacity="{o}" stroke-width="17" stroke-linecap="round"/>'
                   for k, o in ((1, .14), (3, .28), (13, .55)))
    polys = lambda ps, c: "".join(f'<path d="{_moll_path(p, True)}" fill="{c}" fill-opacity=".35" stroke="{c}" stroke-width=".5"/>' for p in ps)  # noqa: E731
    corot = "".join(f'<path d="{_moll_path(_ring(e["ra"], e["dec"], cov["corot"]["radius_deg"]))}" fill="none" stroke="{COV_COLOUR["corot"]}" stroke-width="1.2"/>'
                    for e in cov["corot"]["eyes"])
    bulge = f'<path d="{_moll_path(_bulge_outline(cov["bulge"]))}" fill="{COV_COLOUR["bulge"]}" fill-opacity=".18" stroke="{COV_COLOUR["bulge"]}" stroke-dasharray="3 3" stroke-width="1"/>'
    return (f'<g class="covl" data-layer="tess" style="display:none">{tess}</g>'
            f'<g class="covl" data-layer="kepler" style="display:none">{polys(modules(cov["kepler"]["channels"]), COV_COLOUR["kepler"])}</g>'
            f'<g class="covl" data-layer="k2" style="display:none">{polys([p for c in cov["k2"] for p in modules(c["channels"])], COV_COLOUR["k2"])}</g>'
            f'<g class="covl" data-layer="corot" style="display:none">{corot}</g>'
            f'<g class="covl" data-layer="bulge" style="display:none">{bulge}</g>'
            f'<g class="covl" data-layer="unmapped" style="display:none"><path d="{dots(unm)}" stroke="{COV_COLOUR["unmapped"]}" stroke-opacity=".55" stroke-width="17" stroke-linecap="round"/></g>')


def coverage_chips(cov: dict | None, scope: str) -> str:
    if cov is None:
        return ""
    return (f'<div class="chips covchips" id="{scope}cov" role="group" aria-label="Survey coverage layers">'
            + "".join(f'<button class="chip" type="button" data-cov="{k}" aria-pressed="false"><i style="background:{COV_COLOUR[k]}"></i>{html.escape(v)}</button>'
                      for k, v in COV_LAYERS) + "</div>")


def coverage_panel(cov: dict | None, g: dict | None) -> str:
    """The coverage figures: sky fraction and catalogue hosts inside each footprint, with how they were computed."""
    if cov is None:
        return ""
    e = html.escape
    f, h, s = cov["fractions"], cov["hosts_in"], cov["sources"]
    rows = [("TESS (1 sector or more)", f["tess"], h["tess"], s["tess"]),
            ("TESS, 13 sectors or more (near the ecliptic poles)", f["tess_cvz_13plus"], None, s["tess"]),
            ("Kepler prime field (CCD footprint)", f["kepler"], h["kepler"], s["kepler"]), ("K2 campaigns C0–C19", f["k2"], h["k2"], s["k2"]),
            ("CoRoT observing zones", f["corot"], h["corot"], s["corot"]),
            ("Bulge microlensing region (approximate)", f["bulge"], h["bulge"], s["bulge"]),
            ("Never in a TESS, Kepler or K2 footprint", f["unmapped"], h["none"], None)]
    def row(n, fr, hh, src):
        link = f"<a href='{e(src['ref'])}' rel='noopener'>{e(src['ref_label'])}</a>" if src else ""
        hosts = "" if hh is None else f"{hh:,}"
        return (f"<tr><th scope='row'>{e(n)}</th><td class='num'>{fr * 100:.1f}%</td><td class='num'>{fr * 41253:,.0f}</td>"
                f"<td class='num'>{hosts}</td><td>{link}</td></tr>")

    body = "".join(row(*r) for r in rows)
    reach = ""
    if g is not None:
        reach = "".join(f"<tr><th scope='row'>{e(g['method_label'][m])}</th><td class='num'>{r['hosts']:,}</td><td class='num'>{r['median_ly']:,}</td>"
                        f"<td class='num'>{r['p90_ly']:,}</td></tr>" for m, r in cov["reach"].items())
    return f"""<section class="card covpanel" aria-labelledby="h-cov">
        <h2 id="h-cov">Where we have looked</h2>
        <p class="muted">The cloud's shape is where surveys looked and what each method can see, not where planets are. {e(cov['tess_rule'])} {e(cov['method'])} Catalogue hosts: {h['all']:,} stars in the stored exoplanet.eu map, each tested at its own position. {e(cov['gaia'])}</p>
        <div class="tablewrap" tabindex="0" role="region" aria-label="Survey coverage"><table class="gxtable"><thead><tr><th scope="col">Footprint</th><th scope="col" class="num">Sky</th><th scope="col" class="num">Square degrees</th><th scope="col" class="num">Catalogue hosts inside</th><th scope="col">Source</th></tr></thead><tbody>{body}</tbody></table></div>
        <h3>How far each method reaches in this catalogue</h3>
        <p class="muted">Distances of the stars each method found planets around, from the dataset: half lie within the median, nine in ten within the 90th percentile. Microlensing distances are model-dependent.</p>
        <div class="tablewrap" tabindex="0" role="region" aria-label="Reach by method"><table class="gxtable"><thead><tr><th scope="col">Method</th><th scope="col" class="num">Stars</th><th scope="col" class="num">Median (ly)</th><th scope="col" class="num">90th percentile (ly)</th></tr></thead><tbody>{reach}</tbody></table></div>
      </section>"""

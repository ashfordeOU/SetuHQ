# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""How a planet or a star is drawn, from measured values only: standard library, so the deploy-time page writer
(:mod:`setuhq.stubs`) can use it without an install.

* A star's colour is its blackbody colour (:func:`teff_rgb`, Planck x CIE 1931, sRGB).
* A planet's look ("artist's impression") is chosen from two measured things: its radius (or, without one, its
  mass), which sets a composition class, and the light it gets from its star, which sets a temperature band. Every
  rule and threshold is in :data:`COMPOSITION_RULES`, :data:`BANDS` and :data:`LOOKS`, with its source, and the page
  /docs/pictures/ prints them. Composition is never measured; captions say so. Nothing here says "habitable".

The JavaScript twin (``SetuRender.look`` and ``SetuRender.teffRGB`` in :mod:`setuhq.renderer`) returns exactly the
same answers; tests/test_renderer.py checks both on catalogue rows and every boundary.
"""

from __future__ import annotations

import math

# ---------- the star: blackbody colour ----------

# CIE 1931 colour-matching functions, multi-lobe Gaussian fit (Wyman, Sloan & Shirley 2013, JCGT 2(2), 1).
def _g(x, mu, s1, s2):
    t = (x - mu) / (s1 if x < mu else s2)
    return math.exp(-0.5 * t * t)


def cmf(lam_nm: float) -> tuple[float, float, float]:
    x = 1.056 * _g(lam_nm, 599.8, 37.9, 31.0) + 0.362 * _g(lam_nm, 442.0, 16.0, 26.7) - 0.065 * _g(lam_nm, 501.1, 20.4, 26.2)
    y = 0.821 * _g(lam_nm, 568.8, 46.9, 40.5) + 0.286 * _g(lam_nm, 530.9, 16.3, 31.1)
    z = 1.217 * _g(lam_nm, 437.0, 11.8, 36.0) + 0.681 * _g(lam_nm, 459.0, 26.0, 13.8)
    return x, y, z


TEFF_MIN, TEFF_MAX = 1000.0, 40000.0  # K: the range a colour is computed for; outside it, the nearest end


def teff_rgb(teff: float) -> tuple[int, int, int]:
    """A blackbody's colour as sRGB (D65 white), normalised to its brightest channel: Planck spectrum x
    CIE 1931 colour matching, XYZ -> linear sRGB, clipped at zero, gamma-encoded. Teff is clamped to
    [1,000, 40,000] K."""
    teff = min(TEFF_MAX, max(TEFF_MIN, float(teff)))
    X = Y = Z = 0.0
    for lam in range(380, 781, 5):
        l = lam * 1e-9
        b = 1 / (l ** 5 * (math.exp(1.4387769e-2 / (l * teff)) - 1))
        x, y, z = cmf(lam)
        X, Y, Z = X + b * x, Y + b * y, Z + b * z
    r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z
    g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z
    bl = 0.0557 * X - 0.2040 * Y + 1.0570 * Z
    m = max(r, g, bl)
    out = []
    for c in (r, g, bl):
        c = max(0.0, c / m)
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(round(255 * min(1.0, c)))
    return tuple(out)


# ---------- the size class (the catalogue's and the Galaxy's label; not the look) ----------

RJ_IN_RE = 11.209   # Jupiter's equatorial radius in Earth radii (71,492 km / 6,378 km)
MJ_IN_ME = 317.83   # Jupiter's mass in Earth masses
CLASSES = ["Earth-size", "Super-Earth", "Sub-Neptune", "Neptune-like", "Gas giant"]
CLASS_RULE = ("How we classify: by radius when exoplanet.eu gives one, in Earth radii (1 RJ = 11.21 R⊕): "
              "Earth-size below 1.25, super-Earth 1.25–2, sub-Neptune 2–4, Neptune-like 4–10, gas giant 10 or more. "
              "Without a radius, by mass (or m sin i, a minimum mass) in Earth masses (1 MJ = 317.8 M⊕): "
              "Earth-size below 2, super-Earth 2–10, Neptune-like 10–50, gas giant 50 or more. "
              "With neither, the class is shown as a dash.")


def planet_class(radius_rj: float | None, mass_mj: float | None) -> int | None:
    """Index into CLASSES by the rule in CLASS_RULE; None when neither radius nor mass is given."""
    if radius_rj is not None and radius_rj > 0:
        re = radius_rj * RJ_IN_RE
        for i, cut in enumerate((1.25, 2.0, 4.0, 10.0)):
            if re < cut:
                return i
        return 4
    if mass_mj is not None and mass_mj > 0:
        me = mass_mj * MJ_IN_ME
        return 0 if me < 2 else 1 if me < 10 else 3 if me < 50 else 4
    return None


# ---------- the planet's look: composition x temperature band ----------

T_SUN = 5772.0      # K, IAU 2015 nominal solar effective temperature
TEQ_EARTH = 278.3   # K: Teq at S = 1 with zero Bond albedo and full redistribution
YEAR_DAYS = 365.25
TEQ_DISAGREE = 0.30  # a stored Teq more than 30% from the computed one is named in the caption

# Composition from radius (R⊕); without a radius, from mass (M⊕, true mass else m sin i, a minimum).
COMPOSITION_RULES = {
    "radius": [(1.6, "rock", "Rogers 2015, ApJ 801, 41: most planets larger than about 1.6 R⊕ are not rocky"),
               (4.0, "envelope", "the radius valley at 1.5–2.0 R⊕ (Fulton et al. 2017, AJ 154, 109); sub-Neptunes up to 4 R⊕"),
               (10.0, "neptune", "the catalogue's size-class boundary (Neptune-like 4–10 R⊕)"),
               (math.inf, "giant", "the catalogue's size-class boundary (gas giant 10 R⊕ or more)")],
    "mass": [(2.0, "rock", "below 2 M⊕"),
             (10.0, "ambiguous", "2–10 M⊕: rock or envelope, not decidable from mass"),
             (50.0, "neptune", "10–50 M⊕"),
             (math.inf, "giant", "50 M⊕ or more")],
}
# Temperature band from Teq (K): (upper edge, band, why).
BANDS = [(200.0, "cold", "water ice is stable at the surface"),
         (350.0, "temperate", "spans the conservative habitable-zone fluxes; named temperate, not habitable"),
         (1000.0, "warm", "between temperate and hot"),
         (2000.0, "hot", "the substellar point reaches √2·Teq ≥ 1,414 K, about the basalt solidus; hot Jupiters are conventionally ≥ 1,000 K"),
         (math.inf, "ultrahot", "ultra-hot Jupiters (Parmentier et al. 2018, A&A 617, A110)")]

# The 18 looks, each one still. Colours are sRGB 0–255; "pal" runs dark to light. The drawing reads only these
# numbers (setuhq.renderer): no look has oceans or continents except the Solar System's Earth (ref-earth).
#   bands: latitude frequency of cloud bands (0: none); amp: how much the bands show; turb: band waviness
#   haze: flattening toward the third colour; crater: dark pits; crack: glowing day-side cracks (alpha channel)
#   ice: ice-cap latitude in degrees (0: none); spot: 1 a dark storm, 2 a red storm (Jupiter); atmo: rim colour
#   night: night-side thermal glow colour (hot and ultra-hot only); clouds: cloud cover (ref-earth only)
LOOKS: dict[str, dict] = {
    "rock-cold": {"composition": "rock", "bands": ["cold"], "surface": "pale grey rock, ice caps to latitude 40°, no atmosphere",
                  "pal": [[92, 94, 100], [138, 140, 146], [176, 178, 184], [214, 216, 222]], "freq": 0, "amp": 0, "turb": 0,
                  "haze": 0, "crater": 0.5, "crack": 0, "ice": 40, "spot": 0, "atmo": None, "night": None, "clouds": 0},
    "rock-temperate": {"composition": "rock", "bands": ["temperate"], "surface": "grey-brown rock and a thin neutral rim; no oceans, continents or clouds",
                       "pal": [[74, 66, 58], [112, 100, 88], [146, 134, 118], [184, 172, 156]], "freq": 0, "amp": 0, "turb": 0,
                       "haze": 0.05, "crater": 0.35, "crack": 0, "ice": 0, "spot": 0, "atmo": [190, 196, 206], "night": None, "clouds": 0},
    "rock-warm": {"composition": "rock", "bands": ["warm"], "surface": "bare dark rock with craters, no rim",
                  "pal": [[44, 40, 38], [78, 72, 66], [112, 104, 96], [148, 140, 130]], "freq": 0, "amp": 0, "turb": 0,
                  "haze": 0, "crater": 0.8, "crack": 0, "ice": 0, "spot": 0, "atmo": None, "night": None, "clouds": 0},
    "rock-hot": {"composition": "rock", "bands": ["hot", "ultrahot"], "surface": "dark rock with glowing day-side cracks",
                 "pal": [[40, 32, 28], [70, 56, 48], [104, 86, 74], [132, 112, 96]], "freq": 0, "amp": 0, "turb": 0,
                 "haze": 0, "crater": 0.4, "crack": 1, "ice": 0, "spot": 0, "atmo": None, "night": [255, 96, 24], "clouds": 0},
    "envelope-cool": {"composition": "envelope", "bands": ["cold", "temperate"], "surface": "pale blue-white haze, faint bands",
                      "pal": [[150, 176, 204], [184, 204, 224], [210, 224, 238], [234, 242, 250]], "freq": 6, "amp": 0.35, "turb": 3,
                      "haze": 0.55, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [170, 210, 255], "night": None, "clouds": 0},
    "envelope-warm": {"composition": "envelope", "bands": ["warm"], "surface": "blue-grey haze",
                      "pal": [[96, 124, 150], [124, 152, 178], [156, 182, 204], [196, 214, 230]], "freq": 7, "amp": 0.5, "turb": 4,
                      "haze": 0.4, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [150, 200, 255], "night": None, "clouds": 0},
    "envelope-hot": {"composition": "envelope", "bands": ["hot", "ultrahot"], "surface": "tan haze and a warm rim",
                     "pal": [[128, 104, 80], [168, 140, 108], [196, 170, 136], [226, 204, 172]], "freq": 7, "amp": 0.45, "turb": 4,
                     "haze": 0.45, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [255, 196, 150], "night": [255, 120, 60], "clouds": 0},
    "neptune-cool": {"composition": "neptune", "bands": ["cold", "temperate"], "surface": "deep blue bands and a dark spot",
                     "pal": [[30, 60, 150], [48, 96, 196], [74, 132, 222], [110, 166, 238]], "freq": 5, "amp": 0.8, "turb": 2.5,
                     "haze": 0.1, "crater": 0, "crack": 0, "ice": 0, "spot": 1, "atmo": [120, 170, 255], "night": None, "clouds": 0},
    "neptune-warm": {"composition": "neptune", "bands": ["warm"], "surface": "teal haze",
                     "pal": [[38, 104, 112], [60, 138, 144], [90, 168, 170], [140, 200, 198]], "freq": 6, "amp": 0.55, "turb": 3,
                     "haze": 0.35, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [140, 230, 230], "night": None, "clouds": 0},
    "neptune-hot": {"composition": "neptune", "bands": ["hot", "ultrahot"], "surface": "orange-grey haze",
                    "pal": [[110, 88, 76], [150, 118, 96], [184, 148, 118], [214, 182, 152]], "freq": 6, "amp": 0.5, "turb": 3,
                    "haze": 0.4, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [255, 180, 130], "night": [255, 110, 50], "clouds": 0},
    "giant-cool": {"composition": "giant", "bands": ["cold", "temperate"], "surface": "cream and tan cloud bands",
                   "pal": [[150, 112, 80], [196, 160, 120], [224, 200, 164], [240, 226, 200]], "freq": 11, "amp": 1, "turb": 5,
                   "haze": 0, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [255, 214, 170], "night": None, "clouds": 0},
    "giant-warm": {"composition": "giant", "bands": ["warm"], "surface": "white cloud bands",
                   "pal": [[168, 172, 180], [204, 208, 214], [228, 230, 234], [246, 247, 250]], "freq": 10, "amp": 0.8, "turb": 5,
                   "haze": 0.1, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [220, 230, 255], "night": None, "clouds": 0},
    "giant-hot": {"composition": "giant", "bands": ["hot"], "surface": "rust cloud bands",
                  "pal": [[110, 62, 40], [160, 96, 62], [206, 144, 100], [232, 190, 146]], "freq": 15, "amp": 1, "turb": 7,
                  "haze": 0, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [255, 186, 140], "night": [255, 90, 40], "clouds": 0},
    "giant-ultrahot": {"composition": "giant", "bands": ["ultrahot"], "surface": "dark, low-contrast and glowing on the day side; no bands",
                       "pal": [[40, 26, 24], [58, 36, 30], [74, 46, 36], [92, 58, 44]], "freq": 0, "amp": 0, "turb": 0,
                       "haze": 0.3, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [255, 140, 80], "night": [255, 80, 30], "clouds": 0},
    "ambiguous": {"composition": "ambiguous", "bands": ["cold", "temperate", "warm", "hot", "ultrahot"],
                  "surface": "a neutral grey-blue disc and a soft rim: rock or envelope, unknown",
                  "pal": [[96, 104, 118], [120, 128, 142], [144, 152, 166], [168, 176, 190]], "freq": 0, "amp": 0, "turb": 0,
                  "haze": 0.7, "crater": 0, "crack": 0, "ice": 0, "spot": 0, "atmo": [170, 182, 204], "night": None, "clouds": 0},
    "ref-earth": {"composition": "reference", "bands": [], "surface": "Earth, the Solar System reference: oceans, land and clouds",
                  "pal": [[10, 36, 92], [28, 92, 150], [78, 110, 52], [150, 120, 72]], "freq": 0, "amp": 0, "turb": 0,
                  "haze": 0, "crater": 0, "crack": 0, "ice": 64, "spot": 0, "atmo": [110, 165, 255], "night": None, "clouds": 1},
    "ref-neptune": {"composition": "reference", "bands": [], "surface": "Neptune, the Solar System reference",
                    "pal": [[34, 70, 170], [52, 104, 210], [80, 140, 232], [118, 172, 244]], "freq": 5, "amp": 0.8, "turb": 2.5,
                    "haze": 0.1, "crater": 0, "crack": 0, "ice": 0, "spot": 1, "atmo": [120, 170, 255], "night": None, "clouds": 0},
    "ref-jupiter": {"composition": "reference", "bands": [], "surface": "Jupiter, the Solar System reference, with its Great Red Spot",
                    "pal": [[150, 112, 80], [196, 160, 120], [226, 204, 170], [240, 228, 204]], "freq": 11, "amp": 1, "turb": 5,
                    "haze": 0, "crater": 0, "crack": 0, "ice": 0, "spot": 2, "atmo": [255, 214, 170], "night": None, "clouds": 0},
}
REFERENCES = {"ref-earth": ("Earth", 1.0), "ref-neptune": ("Neptune", 3.88), "ref-jupiter": ("Jupiter", RJ_IN_RE)}
STILL_SEED = 1  # every still is drawn with this seed


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def insolation(srad: float | None, steff: float | None, a: float | None) -> float | None:
    """S/S⊕ = R★² (Teff / 5772 K)⁴ / a², with R★ in R☉ and a in AU; None when an input is missing."""
    srad, steff, a = _num(srad), _num(steff), _num(a)
    if srad is None or steff is None or a is None:
        return None
    return srad ** 2 * (steff / T_SUN) ** 4 / a ** 2


def kepler_a(smass: float | None, period_days: float | None) -> float | None:
    """a in AU from Kepler's third law, a³ = M★ P² (M★ in M☉, P in years); None when an input is missing."""
    smass, period_days = _num(smass), _num(period_days)
    if smass is None or period_days is None:
        return None
    return (smass * (period_days / YEAR_DAYS) ** 2) ** (1 / 3)


def teq_k(s: float | None) -> float | None:
    """Teq = 278.3 K × S^(1/4): zero Bond albedo, full redistribution (Earth: 278 K)."""
    return None if s is None else TEQ_EARTH * s ** 0.25


def band(teq: float | None) -> str | None:
    """The temperature band of a Teq in K (BANDS), or None when it is not known."""
    if teq is None:
        return None
    return next(b for edge, b, _ in BANDS if teq < edge)


def composition(rp_re: float | None, mp_me: float | None) -> tuple[str | None, str | None]:
    """(composition, "radius" | "mass") by COMPOSITION_RULES, or (None, None) with neither."""
    for value, kind in ((rp_re, "radius"), (mp_me, "mass")):
        if value is not None:
            return next(c for edge, c, _ in COMPOSITION_RULES[kind] if value < edge), kind
    return None, None


def look_name(comp: str | None, b: str | None) -> str | None:
    """The look for a composition and a band (a band not known draws the warm look, desaturated)."""
    if comp is None:
        return None
    if comp == "ambiguous":
        return "ambiguous"
    b = b or "warm"
    if comp == "rock":
        return {"cold": "rock-cold", "temperate": "rock-temperate", "warm": "rock-warm"}.get(b, "rock-hot")
    if comp == "giant":
        return {"cold": "giant-cool", "temperate": "giant-cool", "warm": "giant-warm", "hot": "giant-hot"}.get(b, "giant-ultrahot")
    return f"{comp}-" + {"cold": "cool", "temperate": "cool", "warm": "warm"}.get(b, "hot")


def fmt(x: float, d: int = 0) -> str:
    """A number with thousands separators and d decimals (the JavaScript twin formats the same way)."""
    return f"{x:,.{d}f}"


def look(p: dict) -> dict:
    """A planet's look from its catalogue row (exoplanet.eu units: radius RJ, mass and msini MJ, a AU, period d,
    srad R☉, smass M☉, steff K, teq K). Returns the look's name (None: no planet is drawn), its composition and band,
    the numbers it used, whether it is drawn to scale, and the reasons in words."""
    rj, mj = _num(p.get("radius")), _num(p.get("mass"))
    msini = _num(p.get("msini"))
    rp_re = rj * RJ_IN_RE if rj is not None else None
    mp_me = mj * MJ_IN_ME if mj is not None else (msini * MJ_IN_ME if msini is not None else None)
    comp, by = composition(rp_re, mp_me)
    a, a_src = _num(p.get("a")), "a"
    if a is None:
        a, a_src = kepler_a(p.get("smass"), p.get("period")), "kepler"
    s = insolation(p.get("srad"), p.get("steff"), a)
    stored = _num(p.get("teq"))
    teq, teq_src = (teq_k(s), "computed") if s is not None else ((stored, "stored") if stored is not None else (None, None))
    b = band(teq)
    reasons = []
    if comp is None:
        reasons.append("No radius or mass stored, so no planet is drawn.")
    elif by == "radius":
        edge = {"rock": "is below 1.6 R⊕, so it is drawn as rock",
                "envelope": "is at least 1.6 R⊕, so it is drawn with a gaseous envelope",
                "neptune": "is 4 to 10 R⊕, so it is drawn as a Neptune-like planet",
                "giant": "is at least 10 R⊕, so it is drawn as a gas giant"}[comp]
        reasons.append(f"Radius {fmt(rp_re, 2)} R⊕ (exoplanet.eu) {edge}.")
    else:
        which = "mass" if mj is not None else "minimum mass (m sin i)"
        edge = {"rock": "is below 2 M⊕, so it is drawn as rock",
                "ambiguous": "is 2 to 10 M⊕: rock or envelope, unknown",
                "neptune": "is 10 to 50 M⊕, so it is drawn as a Neptune-like planet",
                "giant": "is at least 50 M⊕, so it is drawn as a gas giant"}[comp]
        reasons.append(f"No radius stored; {which} {fmt(mp_me, 1)} M⊕ (exoplanet.eu) {edge}. Radius not measured: not to scale.")
    if comp is not None:
        if teq is None:
            reasons.append("Irradiation not computable: neutral colours.")
        else:
            how = ("computed from a, R★ and Teff" if a_src == "a" else "computed from the period, M★, R★ and Teff") if teq_src == "computed" else "as the catalogue stores it"
            reasons.append(f"Teq {fmt(teq)} K, {how}, is in the {b} band.")
            if teq_src == "computed" and stored is not None and abs(stored - teq) > TEQ_DISAGREE * teq:
                reasons.append(f"Teq computed from a, R★ and Teff; the catalogue's stored value ({fmt(stored)} K) differs.")
        reasons.append("Composition is not measured.")
    return {"name": look_name(comp, b), "composition": comp, "band": b, "by": by,
            "rp_re": None if rp_re is None else round(rp_re, 4), "mp_me": None if mp_me is None else round(mp_me, 3),
            "s": None if s is None else round(s, 4), "teq": None if teq is None else round(teq, 1), "teq_source": teq_src,
            "to_scale": by == "radius", "neutral": comp is not None and b is None, "reasons": reasons}


def caption(p: dict, lk: dict | None = None) -> str:
    """The visible caption of a planet's portrait: "Artist's impression · envelope, hot · <reasons>"."""
    lk = lk or look(p)
    if lk["name"] is None:
        return "No radius or mass stored, so no planet is drawn."
    kind = lk["composition"] + (f", {lk['band']}" if lk["band"] else ", irradiation not computable")
    return f"Artist's impression · {kind} · " + " ".join(lk["reasons"])


def seed(slug: str) -> int:
    """FNV-1a 32 of the planet's slug: every visitor sees the same planet."""
    h = 0x811C9DC5
    for byte in slug.encode("utf-8"):
        h ^= byte
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def find_planet(cat: dict, name: str) -> int | None:
    """The catalogue row of a planet named as SetuHQ names it: by its name, then an alternative name, then a star's
    alternative name plus the letter (HD 15337 b is exoplanet.eu's TOI-402 Ab)."""
    P = cat["planets"]
    if name in P["name"]:
        return P["name"].index(name)
    key = name.strip().lower()
    for i, alt in enumerate(P.get("alt") or []):
        if alt and key in [a.strip().lower() for a in alt.split(",")]:
            return i
    star, _, letter = name.strip().rpartition(" ")
    if star and letter:
        for i, salt in enumerate(P.get("salt") or []):
            if salt and star.lower() in [a.strip().lower() for a in salt.split(",")] and P["name"][i].lower().endswith(letter.lower()):
                return i
    return None


def row(cat: dict, i: int) -> dict:
    """One catalogue row as the dict :func:`look` reads."""
    P = cat["planets"]
    return {k: P[k][i] for k in ("radius", "mass", "msini", "a", "period", "srad", "smass", "steff", "teq") if k in P}

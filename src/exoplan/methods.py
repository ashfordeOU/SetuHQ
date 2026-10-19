"""The Methods section: how planets are found, as animated explainers built on stated physics.

Every equation here has a JavaScript twin in :data:`METHODS_JS` (the page draws with it) and a Python
version (the tests check both against closed forms and published numbers). Numbers on the page come
from three places, and say which: the exoplanet.eu catalogue (docs/results/exoplanet_map.json and
docs/results/methods_examples.json), the research atlas's cited values (each with its DOI), or a
calculation from those with the equation shown. Drawings that cannot be to scale say by how much
they are exaggerated. Only the transit chapter is something exoplan itself does.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

# ---------- constants: IAU 2015 Resolution B3 nominal values (Prša et al. 2016) ----------
GM_SUN = 1.3271244e20
GM_JUP = 1.2668653e17
GM_EARTH = 3.986004e14
R_SUN = 6.957e8
R_JUP = 7.1492e7
R_EARTH = 6.3781e6
AU = 1.495978707e11
PC = 3.0856775814913673e16
DAY = 86400.0
YEAR = 365.25 * DAY
C_LIGHT = 299792458.0
K_B = 1.380649e-23
M_H = 1.6735575e-27
DEFAULT_EXAMPLES = "docs/results/methods_examples.json"
DEFAULT_JWST = "docs/results/wasp39b_jwst_spectrum.json"
# The Atmosphere Lab's bands: centres from the atlas table (µm); Gaussian widths are chosen for display.
LAB_BANDS = {"H2O": [(1.15, 0.05), (1.4, 0.08), (1.9, 0.10), (2.7, 0.15)], "CH4": [(1.65, 0.05), (2.4, 0.08), (3.3, 0.12)],
             "CO2": [(4.26, 0.08)], "CO": [(4.67, 0.08)], "SO2": [(4.05, 0.05)], "Na": [(0.589, 0.006)], "K": [(0.767, 0.008)]}

# Claret 2017 TESS quadratic limb-darkening coefficients (log g 4.5, [M/H] 0, PHOENIX-COND, LSM),
# as tabulated in the atlas (VizieR J/A+A/600/A30, queried 2026-10-18).
CLARET_TESS = [(3000, 0.1693, 0.5023), (3500, 0.1959, 0.4178), (4000, 0.3390, 0.2994), (4500, 0.5037, 0.1581),
               (5500, 0.3862, 0.2061), (6000, 0.3345, 0.2282), (6500, 0.3079, 0.2295), (7000, 0.2847, 0.2310),
               (8000, 0.2331, 0.2353), (10000, 0.1602, 0.2331)]
# Mamajek's mean dwarf sequence (v2022.04.16; Pecaut & Mamajek 2013), the rows the atlas lists.
MAMAJEK = [("O9V", 33300), ("B0V", 31400), ("B5V", 15700), ("A0V", 9700), ("A5V", 8100), ("F0V", 7220), ("F5V", 6550),
           ("G0V", 5930), ("G2V", 5770), ("G5V", 5660), ("K0V", 5270), ("K5V", 4440), ("M0V", 3850), ("M2V", 3560),
           ("M4V", 3210), ("M5V", 3060), ("M8V", 2570), ("L0V", 2270)]
# Infrared and optical band centres for the transmission-spectrum chapter (µm), from the atlas M1 table.
BANDS = [("Na", 0.589, "Na D lines (≈589.0 and 589.6 nm)"), ("K", 0.767, "K lines (≈766.5 and 769.9 nm)"),
         ("H₂O", 1.15, "water overtone band"), ("H₂O", 1.4, "water band (HST/WFC3)"), ("H₂O", 1.9, "water band"),
         ("H₂O", 2.7, "water fundamentals (2.66, 2.73 µm)"), ("CH₄", 3.3, "methane ν₃"), ("CO₂", 4.26, "carbon dioxide ν₃"),
         ("CO", 4.67, "carbon monoxide fundamental")]


# ---------- physics ----------
def rv_semi_amplitude(period_days: float, mp_mj: float, mstar_msun: float, e: float = 0.0, sini: float = 1.0) -> float:
    """K in m/s: (2πG/P)^(1/3) · Mp sin i / (M★ + Mp)^(2/3) / √(1 − e²), with masses as GM values."""
    gmp, gms = mp_mj * GM_JUP, mstar_msun * GM_SUN
    return (2 * math.pi / (period_days * DAY)) ** (1 / 3) * gmp * sini / (gms + gmp) ** (2 / 3) / math.sqrt(1 - e * e)


def barycentre_offsets(a: float, mp_mj: float, mstar_msun: float) -> tuple[float, float]:
    """(a★, a_p): the star's and the planet's distances from the barycentre, in the unit of a."""
    q = mp_mj * GM_JUP / (mstar_msun * GM_SUN + mp_mj * GM_JUP)
    return a * q, a * (1 - q)


def semi_major_axis_au(period_days: float, mstar_msun: float, mp_mj: float = 0.0) -> float:
    gm = mstar_msun * GM_SUN + mp_mj * GM_JUP
    return (gm * (period_days * DAY / (2 * math.pi)) ** 2) ** (1 / 3) / AU


def kepler_E(M: float, e: float, tol: float = 1e-12) -> float:
    """Eccentric anomaly from the mean anomaly: M = E − e sin E, by Newton's method."""
    M = math.fmod(M, 2 * math.pi)
    E = M if e < 0.8 else math.pi
    for _ in range(60):
        f = E - e * math.sin(E) - M
        d = f / (1 - e * math.cos(E))
        E -= d
        if abs(d) < tol:
            break
    return E


def true_anomaly(M: float, e: float) -> float:
    E = kepler_E(M, e)
    return 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2), math.sqrt(1 - e) * math.cos(E / 2))


def orbit_positions(t: float, period: float, a: float, e: float, mp_mj: float, mstar_msun: float):
    """Planet and star positions (x, y) in the orbital plane, about the barycentre at the origin, at time t
    (t = 0 at periastron). The star is always opposite the planet, scaled by the mass ratio."""
    nu = true_anomaly(2 * math.pi * t / period, e)
    r = a * (1 - e * e) / (1 + e * math.cos(nu))
    a_star, a_pl = barycentre_offsets(1.0, mp_mj, mstar_msun)
    px, py = r * a_pl * math.cos(nu), r * a_pl * math.sin(nu)
    sx, sy = -r * a_star * math.cos(nu), -r * a_star * math.sin(nu)
    return (px, py), (sx, sy)


def rv_curve(t: float, period: float, K: float, e: float, omega_deg: float, gamma: float = 0.0) -> float:
    """v_r = γ + K [cos(ν + ω) + e cos ω]; positive = away (redshift)."""
    w = math.radians(omega_deg)
    nu = true_anomaly(2 * math.pi * t / period, e)
    return gamma + K * (math.cos(nu + w) + e * math.cos(w))


def paczynski(u: float) -> float:
    """Point-lens magnification A(u) = (u² + 2) / (u √(u² + 4))."""
    return (u * u + 2) / (u * math.sqrt(u * u + 4))


def einstein_angle_mas(lens_msun: float, pi_rel_mas: float) -> float:
    """θ_E = √(κ M π_rel), κ ≈ 8.14 mas/M☉ (Gaudi 2012)."""
    return math.sqrt(8.14 * lens_msun * pi_rel_mas)


def ld_coeffs(teff: float) -> tuple[float, float]:
    """Quadratic LD (u1, u2) for TESS at this Teff, linear in Teff between the tabulated rows, clamped."""
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


def ld_intensity(r: float, u1: float, u2: float) -> float:
    """I(r)/I(centre) at projected radius r (in stellar radii), quadratic law, μ = √(1 − r²)."""
    mu = math.sqrt(max(0.0, 1 - r * r))
    return 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2


def overlap_area(z: float, k: float) -> float:
    """Area of a disc of radius k centred z from the centre of the unit disc, inside the unit disc."""
    if z >= 1 + k:
        return 0.0
    if z <= 1 - k:
        return math.pi * k * k
    if z <= k - 1:
        return math.pi
    k0 = math.acos(max(-1, min(1, (k * k + z * z - 1) / (2 * k * z))))
    k1 = math.acos(max(-1, min(1, (1 - k * k + z * z) / (2 * z))))
    return k * k * k0 + k1 - 0.5 * math.sqrt(max(0.0, 4 * z * z - (1 + z * z - k * k) ** 2))


def transit_flux(z: float, k: float, u1: float, u2: float) -> float:
    """Relative flux with quadratic limb darkening, in the small-planet approximation of Mandel & Agol
    (2002, §5): the blocked area times the local intensity, over the disc-integrated flux π(1 − u1/3 − u2/6)."""
    area = overlap_area(z, k)
    if area <= 0:
        return 1.0
    # The local intensity at the middle of the covered part of the disc.
    r = min(z, 1.0) if z <= 1 - k else min(1.0, (z - k + 1) / 2)
    return 1 - area * ld_intensity(r, u1, u2) / (math.pi * (1 - u1 / 3 - u2 / 6))


def transit_durations(period: float, a_rs: float, k: float, b: float, inc_deg: float) -> tuple[float, float | None]:
    """T14 and T23 (same unit as the period), circular orbit (Winn 2010, eqs. 14 and 15)."""
    si = math.sin(math.radians(inc_deg))
    t14 = period / math.pi * math.asin(min(1.0, math.sqrt(max(0.0, (1 + k) ** 2 - b * b)) / (a_rs * si)))
    inner = (1 - k) ** 2 - b * b
    t23 = period / math.pi * math.asin(min(1.0, math.sqrt(inner) / (a_rs * si))) if inner > 0 else None
    return t14, t23


def scale_height_m(teq: float, mu: float, mp_mj: float, rp_rj: float) -> float:
    g = mp_mj * GM_JUP / (rp_rj * R_JUP) ** 2
    return K_B * teq / (mu * M_H * g)


def depth_per_scale_height(teq: float, mu: float, mp_mj: float, rp_rj: float, rstar_rsun: float) -> float:
    """Δδ ≈ 2 H Rp / R★² (one scale height of annulus)."""
    return 2 * scale_height_m(teq, mu, mp_mj, rp_rj) * rp_rj * R_JUP / (rstar_rsun * R_SUN) ** 2


def astrometric_signature_uas(mp_mj: float, mstar_msun: float, a_au: float, d_pc: float) -> float:
    """α = (Mp/M★)(a/d), in micro-arcseconds (a in AU, d in pc gives arcseconds)."""
    return (mp_mj * GM_JUP / (mstar_msun * GM_SUN)) * a_au / d_pc * 1e6


def transit_probability(rstar_rsun: float, a_au: float) -> float:
    return rstar_rsun * R_SUN / (a_au * AU)


# CIE 1931 colour-matching functions, multi-lobe Gaussian fit (Wyman, Sloan & Shirley 2013, JCGT 2(2), 1).
def _g(x, mu, s1, s2):
    t = (x - mu) / (s1 if x < mu else s2)
    return math.exp(-0.5 * t * t)


def cmf(lam_nm: float) -> tuple[float, float, float]:
    x = 1.056 * _g(lam_nm, 599.8, 37.9, 31.0) + 0.362 * _g(lam_nm, 442.0, 16.0, 26.7) - 0.065 * _g(lam_nm, 501.1, 20.4, 26.2)
    y = 0.821 * _g(lam_nm, 568.8, 46.9, 40.5) + 0.286 * _g(lam_nm, 530.9, 16.3, 31.1)
    z = 1.217 * _g(lam_nm, 437.0, 11.8, 36.0) + 0.681 * _g(lam_nm, 459.0, 26.0, 13.8)
    return x, y, z


def teff_rgb(teff: float) -> tuple[int, int, int]:
    """A blackbody's colour as sRGB (D65 white), normalised to its brightest channel: Planck spectrum ×
    CIE 1931 colour matching, XYZ → linear sRGB, clipped at zero, gamma-encoded."""
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


def spectral_class(teff: float) -> tuple[str, str]:
    """(class letter, nearest tabulated dwarf type) from Mamajek's sequence: the row nearest in Teff."""
    row = min(MAMAJEK, key=lambda r: abs(r[1] - teff))
    return row[0][0], row[0]


def doppler_ratio(v_ms: float) -> float:
    """Δλ/λ = v_r / c (non-relativistic)."""
    return v_ms / C_LIGHT


def atm_model(lam_um: float, base_ppm: float, dH_ppm: float, strengths: dict) -> float:
    """The Atmosphere Lab's toy spectrum: the baseline depth plus, for each molecule switched on, its
    strength (in scale heights) times the depth change per scale height, spread over Gaussian bands."""
    v = base_ppm
    for mol, n in strengths.items():
        for c, w in LAB_BANDS[mol]:
            v += n * dH_ppm * math.exp(-0.5 * ((lam_um - c) / w) ** 2)
    return v


def rm_amplitude(vsini_kms: float, k: float) -> float:
    """Rossiter–McLaughlin semi-amplitude, K_R ≈ V sin I · k² (Gaudi & Winn 2007, eq. 6), in m/s."""
    return vsini_kms * 1000 * k * k


def planck(lam_um: float, T: float) -> float:
    lam = lam_um * 1e-6
    return 1 / (lam ** 5 * (math.exp(1.4387769e-2 / (lam * T)) - 1))


def thermal_eclipse_depth(k: float, t_day: float, t_star: float, lam_um: float) -> float:
    """Occultation depth with blackbodies: δ ≈ k² B_λ(T_day)/B_λ(T★) (Winn 2010)."""
    return k * k * planck(lam_um, t_day) / planck(lam_um, t_star)


def diluted_depth(depth: float, f_target: float) -> float:
    """δ_obs = δ_true · F_target / F_total."""
    return depth * f_target


KOPPARAPU = {"recent_venus": (1.776, 2.136e-4, 2.533e-8, -1.332e-11, -3.097e-15),
             "runaway_greenhouse": (1.107, 1.332e-4, 1.58e-8, -8.308e-12, -1.931e-15),
             "maximum_greenhouse": (0.356, 6.171e-5, 1.698e-9, -3.198e-12, -5.575e-16),
             "early_mars": (0.32, 5.547e-5, 1.526e-9, -2.874e-12, -5.011e-16)}


def hz_seff(limit: str, teff: float) -> float:
    """Kopparapu et al. 2014 (1 M⊕): S_eff = S☉ + a T + b T² + c T³ + d T⁴, T = Teff − 5780 K."""
    s0, a, b, c, d = KOPPARAPU[limit]
    t = teff - 5780.0
    return s0 + a * t + b * t ** 2 + c * t ** 3 + d * t ** 4


def hz_distance_au(limit: str, teff: float, lum_lsun: float) -> float:
    return math.sqrt(lum_lsun / hz_seff(limit, teff))


# Equations of life: the Drake terms' log10 ranges for the Monte Carlo, after Sandberg, Drexler & Ord 2018
# (log-uniform priors). Their f_l uses a log-normal abiogenesis-rate model; the page uses a log-uniform
# stand-in from 10^-k to 1 with k on a slider, and says so.
DRAKE_TERMS = [("R", "R★ (stars formed per year)", 0, 2), ("fp", "f_p", -1, 0), ("ne", "n_e", -1, 0), ("fl", "f_l", -10, 0),
               ("fi", "f_i", -3, 0), ("fc", "f_c", -2, 0), ("L", "L (years)", 2, 10)]


def lcg(seed: int):
    """The page's seeded generator (also mxRand in the page): s ← (1664525 s + 1013904223) mod 2³²."""
    s = seed & 0xFFFFFFFF or 1
    while True:
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
        yield s / 4294967296


def drake_mc(n: int = 20000, seed: int = 42, fl_orders: float = 10) -> dict:
    """Monte Carlo over log-uniform term ranges: the median, the 5–95% interval and P(N < 1) of N, and each
    term's share of the variance of log10 N (exact for independent log-uniform terms: width²/12 each)."""
    rnd = lcg(seed)
    ranges = [(k, lo, hi) if k != "fl" else (k, -fl_orders, 0) for k, _, lo, hi in DRAKE_TERMS]
    logs = []
    for _ in range(n):
        logs.append(sum(lo + next(rnd) * (hi - lo) for _, lo, hi in ranges))
    logs.sort()
    q = lambda f: logs[min(n - 1, int(f * n))]  # noqa: E731
    var = {k: (hi - lo) ** 2 / 12 for k, lo, hi in ranges}
    tot = sum(var.values())
    return {"median_log10": q(0.5), "p05_log10": q(0.05), "p95_log10": q(0.95),
            "p_lt_1": sum(1 for v in logs if v < 0) / n, "share": {k: v / tot for k, v in var.items()}}


def load_population(path: str | Path | None = None) -> dict | None:
    path = path or DEFAULT_POPULATION
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def load_jwst(path: str | Path | None = DEFAULT_JWST) -> dict | None:
    if path is None or not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def load_examples(path: str | Path | None = DEFAULT_EXAMPLES) -> dict:
    if path is None or not Path(path).exists():
        return {"planets": {}}
    return json.loads(Path(path).read_text())


# ---------- sources (DOIs as the atlas gives them; resolved against Crossref 2026-10-18) ----------
SOURCES = {
    "winn": ("Winn 2010, Transits and occultations", "https://arxiv.org/abs/1001.2010"),
    "mandel": ("Mandel & Agol 2002, ApJ 580, L171", "https://doi.org/10.1086/345520"),
    "claret": ("Claret 2017, A&A 600, A30 (TESS limb darkening)", "https://doi.org/10.1051/0004-6361/201629705"),
    "huang": ("Huang et al. 2018, ApJL 868, L39 (pi Men c)", "https://doi.org/10.3847/2041-8213/aaef91"),
    "gaudiwinn": ("Gaudi & Winn 2007, ApJ 655, 550", "https://doi.org/10.1086/509910"),
    "fischer": ("Fischer et al. 2016, PASP 128, 066001 (precise RV)", "https://doi.org/10.1088/1538-3873/128/964/066001"),
    "pepe": ("Pepe et al. 2021, A&A 645, A96 (ESPRESSO)", "https://doi.org/10.1051/0004-6361/202038306"),
    "mayor": ("Mayor & Queloz 1995, Nature 378, 355", "https://doi.org/10.1038/378355a0"),
    "prsa": ("Prša et al. 2016, AJ 152, 41 (IAU 2015 B3 nominal values)", "https://doi.org/10.3847/0004-6256/152/2/41"),
    "perryman": ("Perryman et al. 2014, ApJ 797, 14 (Gaia planet yield)", "https://doi.org/10.1088/0004-637X/797/1/14"),
    "stefansson": ("Stefánsson et al. 2025, AJ 169, 107 (Gaia-4b)", "https://doi.org/10.3847/1538-3881/ada9e1"),
    "curiel": ("Curiel et al. 2022, AJ 164, 93 (GJ 896 Ab)", "https://doi.org/10.3847/1538-3881/ac7c66"),
    "gaudi12": ("Gaudi 2012, ARA&A 50, 411 (microlensing)", "https://doi.org/10.1146/annurev-astro-081811-125518"),
    "gaudi10": ("Gaudi 2010, Exoplanetary microlensing", "https://arxiv.org/abs/1002.0332"),
    "bond": ("Bond et al. 2004, ApJ 606, L155", "https://doi.org/10.1086/420928"),
    "beaulieu": ("Beaulieu et al. 2006, Nature 439, 437", "https://doi.org/10.1038/nature04441"),
    "marois08": ("Marois et al. 2008, Science 322, 1348 (HR 8799)", "https://doi.org/10.1126/science.1166585"),
    "marois06": ("Marois et al. 2006, ApJ 641, 556 (ADI)", "https://doi.org/10.1086/500401"),
    "lawson": ("Lawson et al. 2013, SPIE 8864 (Earth-twin contrast)", "https://doi.org/10.1117/12.2021302"),
    "mawet": ("Mawet et al. 2012, SPIE 8442 (coronagraph review)", "https://doi.org/10.1117/12.927245"),
    "lyot": ("Lyot 1939, MNRAS 99, 580", "https://doi.org/10.1093/mnras/99.8.580"),
    "bailey": ("Bailey et al. 2016 (GPI on-sky contrast)", "https://arxiv.org/abs/1609.08689"),
    "carter23": ("Carter et al. 2023, ApJL 951, L20 (JWST coronagraphy)", "https://doi.org/10.3847/2041-8213/acd93e"),
    "roman": ("Roman Coronagraph requirement (arXiv:2207.03607)", "https://arxiv.org/abs/2207.03607"),
    "cash": ("Cash 2006, Nature 442, 51 (starshade)", "https://doi.org/10.1038/nature04930"),
    "habex": ("HabEx Final Report (arXiv:2001.06683)", "https://arxiv.org/abs/2001.06683"),
    "bracewell": ("Bracewell 1978, Nature 274, 780", "https://doi.org/10.1038/274780a0"),
    "life": ("Quanz et al. 2022, A&A 664, A21 (LIFE)", "https://doi.org/10.1051/0004-6361/202140366"),
    "lasco": ("Brueckner et al. 1995, Solar Physics 162, 357 (LASCO)", "https://doi.org/10.1007/BF00733434"),
    "seager": ("Seager & Sasselov 2000, ApJ 537, 916", "https://doi.org/10.1086/309088"),
    "faedi": ("Faedi et al. 2011, A&A 531, A40 (WASP-39 b)", "https://doi.org/10.1051/0004-6361/201116671"),
    "ers": ("JWST ERS Team 2023, Nature 614, 649 (CO₂ in WASP-39 b)", "https://doi.org/10.1038/s41586-022-05269-w"),
    "carter24": ("Carter et al. 2024, Nat. Astron. 8, 1008 (WASP-39 b benchmark spectrum)", "https://doi.org/10.1038/s41550-024-02292-x"),
    "carter24data": ("Carter et al. 2024 data products, CC-BY-4.0 (Zenodo)", "https://doi.org/10.5281/zenodo.10161743"),
    "tsai": ("Tsai et al. 2023, Nature 617, 483 (SO₂ in WASP-39 b)", "https://doi.org/10.1038/s41586-023-05902-2"),
    "charb02": ("Charbonneau et al. 2002, ApJ 568, 377 (sodium)", "https://doi.org/10.1086/338770"),
    "schwieterman": ("Schwieterman et al. 2018, Astrobiology 18, 663 (biosignatures)", "https://doi.org/10.1089/ast.2017.1729"),
    "meadows": ("Meadows et al. 2018, Astrobiology 18, 630 (O₂ in context)", "https://doi.org/10.1089/ast.2017.1727"),
    "catling": ("Catling et al. 2018, Astrobiology 18, 709 (assessment framework)", "https://doi.org/10.1089/ast.2017.1737"),
    "krissansen": ("Krissansen-Totton et al. 2018, Sci. Adv. 4, eaao5747", "https://doi.org/10.1126/sciadv.aao5747"),
    "cccbdb": ("NIST CCCBDB experimental geometries and fundamentals", "https://cccbdb.nist.gov"),
    "greaves": ("Greaves et al. 2020, Nat. Astron. 5, 655 (phosphine on Venus)", "https://doi.org/10.1038/s41550-020-1174-4"),
    "snellen20": ("Snellen et al. 2020, A&A 644, L2 (re-analysis)", "https://doi.org/10.1051/0004-6361/202039717"),
    "villanueva": ("Villanueva et al. 2021, Nat. Astron. 5, 631", "https://doi.org/10.1038/s41550-021-01422-z"),
    "greaves21": ("Greaves et al. 2021, reply", "https://doi.org/10.1038/s41550-021-01424-x"),
    "madhu23": ("Madhusudhan et al. 2023, ApJL 956, L13 (K2-18 b)", "https://doi.org/10.3847/2041-8213/acf577"),
    "madhu25": ("Madhusudhan et al. 2025, ApJL 983, L40", "https://doi.org/10.3847/2041-8213/adc1c8"),
    "schmidt": ("Schmidt et al. 2025, re-analysis (arXiv:2501.18477)", "https://arxiv.org/abs/2501.18477"),
    "luque": ("Luque et al. 2025, joint analysis (arXiv:2505.13407)", "https://arxiv.org/abs/2505.13407"),
    "bell": ("Bell et al. 2023, Nature 623, 709 (methane in WASP-80 b)", "https://doi.org/10.1038/s41586-023-06687-0"),
    "deming13": ("Deming et al. 2013, ApJ 774, 95 (water with WFC3)", "https://doi.org/10.1088/0004-637X/774/2/95"),
    "snellen10": ("Snellen et al. 2010, Nature 465, 1049 (CO, HD 209458 b)", "https://doi.org/10.1038/nature09111"),
    "powell": ("Powell et al. 2024, Nature 626, 979 (mid-IR SO₂)", "https://doi.org/10.1038/s41586-024-07040-9"),
    "sing11": ("Sing et al. 2011, A&A 527, A73 (potassium, XO-2 b)", "https://doi.org/10.1051/0004-6361/201015579"),
    "bains": ("Bains et al. 2021, Astrobiology 21, 1277", "https://doi.org/10.1089/ast.2020.2352"),
    "wyman": ("Wyman, Sloan & Shirley 2013, JCGT 2(2) (CIE fit)", "https://jcgt.org/published/0002/02/01/"),
    "mamajek": ("Pecaut & Mamajek 2013, ApJS 208, 9 (dwarf sequence, v2022.04.16)", "https://doi.org/10.1088/0067-0049/208/1/9"),
    "ricker": ("Ricker et al. 2015, JATIS 1, 014003 (TESS)", "https://doi.org/10.1117/1.JATIS.1.1.014003"),
    "borucki": ("Borucki et al. 2010, Science 327, 977 (Kepler)", "https://doi.org/10.1126/science.1185402"),
    "wolszczan": ("Wolszczan & Frail 1992, Nature 355, 145", "https://doi.org/10.1038/355145a0"),
    "charb00": ("Charbonneau et al. 2000, ApJ 529, L45 (HD 209458 b)", "https://doi.org/10.1086/312457"),
    "henry00": ("Henry et al. 2000, ApJ 529, L41 (HD 209458 b)", "https://doi.org/10.1086/312458"),
    "kalas": ("Kalas et al. 2008, Science 322, 1345 (Fomalhaut b)", "https://doi.org/10.1126/science.1166609"),
    "gaspar": ("Gáspár & Rieke 2020, PNAS 117, 9712 (Fomalhaut b as dust)", "https://doi.org/10.1073/pnas.1912506117"),
    "lissauer14": ("Lissauer et al. 2014, ApJ 784, 44 (multiplicity validation)", "https://doi.org/10.1088/0004-637X/784/1/44"),
    "rowe14": ("Rowe et al. 2014, ApJ 784, 45 (851 planets validated)", "https://doi.org/10.1088/0004-637X/784/1/45"),
    "nobel": ("Royal Swedish Academy of Sciences, Nobel Prize in Physics 2019", "https://www.kva.se/en/news/nobelpriset-i-fysik-2019-2/"),
    "kovacs": ("Kovács et al. 2002, A&A 391, 369 (BLS)", "https://doi.org/10.1051/0004-6361:20020802"),
    "gilliland": ("Gilliland et al. 2011, stellar noise in Kepler", "https://arxiv.org/abs/1107.5207"),
    "licquia": ("Licquia & Newman 2015, ApJ 806, 96 (Milky Way star formation rate)", "https://doi.org/10.1088/0004-637X/806/1/96"),
    "burke15": ("Burke et al. 2015, ApJ 809, 8 (Kepler occurrence)", "https://doi.org/10.1088/0004-637X/809/1/8"),
    "dressing15": ("Dressing & Charbonneau 2015, ApJ 807, 45 (M-dwarf occurrence)", "https://doi.org/10.1088/0004-637X/807/1/45"),
    "bryson": ("Bryson et al. 2021, AJ 161, 36 (η⊕)", "https://doi.org/10.3847/1538-3881/abc418"),
    "petigura": ("Petigura, Howard & Marcy 2013, PNAS 110, 19273", "https://doi.org/10.1073/pnas.1319909110"),
    "sandberg": ("Sandberg, Drexler & Ord 2018, Dissolving the Fermi Paradox", "https://arxiv.org/abs/1806.02404"),
    "seager18": ("Seager 2018, Int. J. Astrobiology 17, 294 (Seager equation)", "https://doi.org/10.1017/S1473550417000052"),
    "kopparapu": ("Kopparapu et al. 2014, ApJL 787, L29 (habitable zones)", "https://doi.org/10.1088/2041-8205/787/2/L29"),
    "fulton": ("Fulton et al. 2017, AJ 154, 109 (radius gap)", "https://doi.org/10.3847/1538-3881/aa80eb"),
    "vaneylen": ("Van Eylen et al. 2018, MNRAS 479, 4786", "https://doi.org/10.1093/mnras/sty1783"),
    "owen": ("Owen & Wu 2017, ApJ 847, 29 (photoevaporation)", "https://doi.org/10.3847/1538-4357/aa890a"),
    "gupta": ("Gupta & Schlichting 2019, MNRAS 487, 24 (core-powered mass loss)", "https://doi.org/10.1093/mnras/stz1230"),
    "fressin": ("Fressin et al. 2013, ApJ 766, 81 (Kepler false-positive rate)", "https://doi.org/10.1088/0004-637X/766/2/81"),
    "guerrero": ("Guerrero et al. 2021, ApJS 254, 39 (TOI catalogue)", "https://doi.org/10.3847/1538-4365/abefe1"),
    "twicken": ("Twicken et al. 2018, PASP 130, 064502 (Kepler DV tests)", "https://doi.org/10.1088/1538-3873/aab694"),
    "holman": ("Holman et al. 2010, Science 330, 51 (Kepler-9 TTVs)", "https://doi.org/10.1126/science.1195778"),
    "agol": ("Agol et al. 2021, PSJ 2, 1 (TRAPPIST-1)", "https://doi.org/10.3847/PSJ/abd022"),
    "greene": ("Greene et al. 2023, Nature 618, 39 (TRAPPIST-1 b at 15 µm)", "https://doi.org/10.1038/s41586-023-05951-7"),
    "knutson": ("Knutson et al. 2007, Nature 447, 183 (HD 189733 b map)", "https://doi.org/10.1038/nature05782"),
    "albrecht": ("Albrecht, Dawson & Winn 2022, PASP 134, 082001 (obliquities)", "https://doi.org/10.1088/1538-3873/ac6c09"),
    "deming05": ("Deming et al. 2005, Nature 434, 740 (first thermal emission)", "https://doi.org/10.1038/nature03507"),
}
LABEL_ILL = "Illustration"
LABEL_MODEL = "Model from stored values"
LABEL_DATA = "Real data, cited"
LABEL_SPEC = "Speculative model"


def _src(keys) -> str:
    e = html.escape
    return "".join(f'<li><a href="{e(SOURCES[k][1])}" rel="noopener">{e(SOURCES[k][0])}</a></li>' for k in keys)


def _num_rows(rows) -> str:
    e = html.escape
    out = []
    for label, value, how in rows:
        out.append(f"<tr><th scope='row'>{e(label)}</th><td class='num'>{e(value)}</td><td>{e(how)}</td></tr>")
    return ("<div class='tablewrap' tabindex='0' role='region' aria-label='Numbers in this chapter'><table class='mxnums'>"
            "<thead><tr><th scope='col'>Quantity</th><th scope='col' class='num'>Value</th><th scope='col'>From</th></tr></thead>"
            f"<tbody>{''.join(out)}</tbody></table></div>")


def _fmt(x, d=2):
    return f"{x:,.{d}f}"


def per_year(g: dict | None) -> dict:
    """Discoveries per year for each method, from the map's planets (the year the dataset lists)."""
    if not g:
        return {}
    out: dict[str, dict[int, int]] = {m: {} for m in g["methods"]}
    for y, m in zip(g["planets"]["y"], g["planets"]["m"]):
        if y is None:
            continue
        mt = g["methods"][m]
        out[mt][y] = out[mt].get(y, 0) + 1
    return out


def year_chart(g: dict | None, method: str) -> str:
    """A small bar chart of planets found per year by one method (SVG, built from the dataset)."""
    if not g:
        return ""
    py = per_year(g)[method]
    y0, y1 = g["years"]
    peak = max(py.values() or [1])
    n = y1 - y0 + 1
    bw = 300 / n
    bars = "".join(f'<rect x="{(y - y0) * bw:.2f}" y="{60 - 56 * c / peak:.2f}" width="{max(1.0, bw - 1):.2f}" height="{56 * c / peak:.2f}"/>'
                   for y, c in sorted(py.items()))
    best = max(py.items(), key=lambda kv: kv[1]) if py else (y0, 0)
    total = sum(py.values())
    label = (f"Planets found by {g['method_label'][method].lower()} per year, {y0}–{y1}: {total:,} in all; "
             f"the most in one year was {best[1]:,} in {best[0]}.")
    return (f'<figure class="mxyears"><p class="mxyrs"><span>peak {best[1]:,} ({best[0]})</span></p>'
            f'<svg viewBox="0 0 300 62" preserveAspectRatio="none" role="img" aria-label="{html.escape(label)}">'
            f'<g fill="{g["method_colour"][method]}">{bars}</g></svg>'
            f'<p class="mxyrs"><span>{y0}</span><span>{y1}</span></p>'
            f'<figcaption>{html.escape(label)} Source: {html.escape(g["source_short"])}, fetched {html.escape(g["fetched_at"][:10])}.</figcaption></figure>')


def _stage(vis: str, label: str, desc: str, controls: str = "", tall: bool = False, static: bool = False) -> str:
    """A visual: a canvas with its honesty label, a text description for screen readers, and controls."""
    e = html.escape
    lab_cls = {LABEL_ILL: "ill", LABEL_MODEL: "model", LABEL_DATA: "data", LABEL_SPEC: "spec"}[label]
    return f"""<figure class="mxstage{' tall' if tall else ''}" data-vis="{vis}">
          <div class="mxcanvas"><canvas role="img" aria-label="{e(desc)}"></canvas></div>
          <div class="mxbadges"><span class="mxlabel {lab_cls}">{e(label)}</span><span class="mxexag" aria-live="polite"></span></div>
          <div class="mxctl" role="group" aria-label="{'Controls' if static else 'Animation controls'}">
            {'' if static else '<button class="btn mxplay" type="button" aria-pressed="false">Play</button><label class="mxspeed"><span>Speed</span><select><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label><input class="mxscrub" type="range" min="0" max="1000" value="0" aria-label="Time">'}
            {controls}
          </div>
          <figcaption class="mxdesc">{e(desc)}</figcaption>
        </figure>"""


CHAPTERS = [("survey", "How a survey works"), ("transit", "Transit"), ("doppler", "Toward and away"),
            ("rv", "Radial velocity"), ("astrometry", "Astrometry"), ("microlensing", "Microlensing"),
            ("imaging", "Blocking starlight"), ("timing", "Timing and phase"), ("falsepos", "False positives"),
            ("spectroscopy", "Reading atmospheres"), ("molecules", "Molecules and life"), ("population", "Population"),
            ("equations", "Equations of life"), ("history", "History and papers")]
DEFAULT_POPULATION = "docs/results/population_stats.json"
METHOD_OF = {"transit": "transit", "rv": "rv", "doppler": "rv", "astrometry": "astrometry", "microlensing": "microlensing",
             "imaging": "imaging"}

# Molecule geometry (NIST CCCBDB, as tabulated in the atlas M1), bands (µm) and what the atlas cites for each.
MOLECULES = [
    {"id": "H2O", "name": "Water", "f": "H₂O", "geom": {"shape": "bent", "r": 0.958, "angle": 104.48, "atoms": ["O", "H", "H"]},
     "bands": "1.4, 1.9, 2.7 (fundamentals 2.66 and 2.73), 6.27", "who": "HST/WFC3 near 1.4 µm; JWST NIRISS, NIRSpec, MIRI",
     "seen": [("HD 209458 b and XO-1 b with WFC3", "deming13"), ("WASP-39 b with JWST", "ers")],
     "why": "The commonest molecule in warm planet atmospheres; sets the shape of most spectra.",
     "abiotic": "Made everywhere by ordinary chemistry and outgassing. Not a biosignature."},
    {"id": "CO2", "name": "Carbon dioxide", "f": "CO₂", "geom": {"shape": "linear", "r": 1.162, "atoms": ["C", "O", "O"]},
     "bands": "4.26 (very strong), 15.0; the 7.50 µm symmetric stretch is IR-silent", "who": "JWST NIRSpec G395H/PRISM (4.3 µm), MIRI (15 µm)",
     "seen": [("WASP-39 b, 26σ at 4.3 µm", "ers"), ("K2-18 b, 3σ", "madhu23")],
     "why": "Traces the planet's metal content and chemistry; a context gas for any biosignature claim.",
     "abiotic": "Volcanism and thermochemistry make it readily."},
    {"id": "CO", "name": "Carbon monoxide", "f": "CO", "geom": {"shape": "diatomic", "r": 1.128, "atoms": ["C", "O"]},
     "bands": "4.67 fundamental", "who": "JWST NIRSpec; ground high-resolution spectrographs near 2.3 µm",
     "seen": [("HD 209458 b, with its orbital motion", "snellen10")],
     "why": "With CO₂ and H₂O it fixes the carbon-to-oxygen balance of hot atmospheres.",
     "abiotic": "CO₂ photolysis and hot thermochemistry; often read as a sign against life, not for it."},
    {"id": "CH4", "name": "Methane", "f": "CH₄", "geom": {"shape": "tetrahedral", "r": 1.087, "angle": 109.47, "atoms": ["C", "H", "H", "H", "H"]},
     "bands": "1.65, 2.4, 3.3 (ν₃ 3.31), 7.66", "who": "JWST NIRSpec, NIRISS, MIRI",
     "seen": [("WASP-80 b", "bell"), ("K2-18 b, 5σ", "madhu23")],
     "why": "With O₂ it is the classic disequilibrium pair that a biosphere could sustain.",
     "abiotic": "Serpentinisation of ultramafic rock (the main abiotic source on Earth today) and thermochemistry in cool H₂ atmospheres."},
    {"id": "O2", "name": "Oxygen", "f": "O₂", "geom": {"shape": "diatomic", "r": 1.208, "atoms": ["O", "O"]},
     "bands": "0.76 (A band), 0.69, 0.63; O₂–O₂ pairs at 1.06 and 1.27; vibrational fundamental IR-silent", "who": "Reflected light (future HWO); ground high-resolution at 0.76 µm",
     "seen": [],
     "why": "Earth's most prominent biosignature gas, but only meaningful in context.",
     "abiotic": "CO₂ photolysis around some stars, or massive hydrogen escape after water loss."},
    {"id": "O3", "name": "Ozone", "f": "O₃", "geom": {"shape": "bent", "r": 1.278, "angle": 116.8, "atoms": ["O", "O", "O"]},
     "bands": "0.25 (UV), 0.5–0.7 (Chappuis), 9.65 (strongest mid-IR)", "who": "HWO in UV/visible; mid-IR missions such as LIFE at 9.6 µm",
     "seen": [],
     "why": "A sensitive tracer of O₂, visible even when O₂ itself is hard to see.",
     "abiotic": "Photochemistry from abiotic O₂, favoured around some M and F dwarfs."},
    {"id": "N2O", "name": "Nitrous oxide", "f": "N₂O", "geom": {"shape": "linear", "r": 1.128, "r2": 1.184, "atoms": ["N", "N", "O"]},
     "bands": "3.7, 4.5, 7.8, 8.6, 17", "who": "JWST MIRI; LIFE",
     "seen": [],
     "why": "Made by life on Earth, with few abiotic sources at that level.",
     "abiotic": "Flares, energetic particles and lightning; these make far more NOₓ than N₂O, which is diagnostic."},
    {"id": "NH3", "name": "Ammonia", "f": "NH₃", "geom": {"shape": "pyramidal", "r": 1.012, "angle": 106.67, "atoms": ["N", "H", "H", "H"]},
     "bands": "2.90, 3.00, 6.15, 10.5", "who": "JWST MIRI (10.5 µm), NIRSpec",
     "seen": [],
     "why": "Abundant in cool giant planets; its depletion has been used to infer internal heat.",
     "abiotic": "Thermochemistry deep in hydrogen atmospheres; destroyed quickly by UV."},
    {"id": "PH3", "name": "Phosphine", "f": "PH₃", "geom": {"shape": "pyramidal", "r": 1.421, "angle": 93.3, "atoms": ["P", "H", "H", "H"]},
     "bands": "4.30, 8.94, 10.1; the Venus claim used a millimetre line at 267 GHz", "who": "JWST MIRI; ALMA and JCMT for Venus",
     "seen": [],
     "why": "Proposed as a biosignature for rocky planets, where it is hard to make without life.",
     "abiotic": "Deep, hot chemistry in giant planets; otherwise thought hard to make abiotically on rocky worlds (Bains et al. 2021)."},
    {"id": "DMS", "name": "Dimethyl sulfide", "f": "DMS", "geom": {"shape": "dms", "r": 1.802, "angle": 98.9, "atoms": ["S", "C", "C"]},
     "bands": "3.3–3.4 (C–H stretches), 6–7, ≈10, ≈15", "who": "JWST MIRI LRS; NIRSpec (3.3 µm overlaps methane)",
     "seen": [("K2-18 b: tentative and contested (see below)", "madhu25")],
     "why": "On Earth it is made almost only by marine life.",
     "abiotic": "Few known abiotic sources on modern Earth; broken apart quickly by starlight."},
    {"id": "SO2", "name": "Sulfur dioxide", "f": "SO₂", "geom": {"shape": "bent", "r": 1.432, "angle": 119.5, "atoms": ["S", "O", "O"]},
     "bands": "≈4.05 (combination band), 7.34, 8.69, 19.3", "who": "JWST NIRSpec G395H/PRISM, MIRI LRS",
     "seen": [("WASP-39 b: photochemical SO₂", "tsai"), ("WASP-39 b in the mid-IR", "powell")],
     "why": "The first photochemical product seen in an exoplanet atmosphere: starlight driving chemistry.",
     "abiotic": "Photochemistry and volcanism."},
    {"id": "Na", "name": "Sodium", "f": "Na", "geom": {"shape": "atom", "atoms": ["Na"]},
     "bands": "0.589 (D lines, 589.0 and 589.6 nm)", "who": "Optical transmission (HST, ground high-resolution)",
     "seen": [("HD 209458 b: the first exoplanet atmosphere", "charb02")],
     "why": "Predicted by Seager & Sasselov 2000 and the first atmosphere ever detected.",
     "abiotic": "Atomic sodium in hot atmospheres; not a biosignature."},
    {"id": "K", "name": "Potassium", "f": "K", "geom": {"shape": "atom", "atoms": ["K"]},
     "bands": "0.767 (766.5 and 769.9 nm)", "who": "Optical transmission",
     "seen": [("XO-2 b", "sing11")],
     "why": "With sodium, a probe of clouds and temperature in hot giants.",
     "abiotic": "As sodium; not a biosignature."},
]

HISTORY = [
    (1992, "Wolszczan & Frail", "A planetary system around the millisecond pulsar PSR B1257+12", "wolszczan",
     "Two planets found from tiny delays in a dead star's radio pulses.", "The first confirmed planets beyond the Solar System.", "#/galaxy?method=timing"),
    (1995, "Mayor & Queloz", "A Jupiter-mass companion to a solar-type star", "mayor",
     "51 Pegasi b, a giant on a 4-day orbit, found from its star's wobble.", "The first planet around a Sun-like star; Nobel Prize 2019.", "#/methods?ch=rv"),
    (2000, "Charbonneau et al.; Henry et al.", "HD 209458 b seen in transit", "charb00",
     "Two teams independently caught the same planet crossing its star.", "The first transiting planet: a radius, a density, and a way into atmospheres.", "#/methods?ch=transit"),
    (2000, "Seager & Sasselov", "Theoretical transmission spectra during extrasolar giant planet transits", "seager",
     "Predicted how starlight filtered through a planet's limb would carry sodium and potassium features.", "The blueprint for transmission spectroscopy.", "#/methods?ch=spectroscopy"),
    (2002, "Charbonneau et al.", "Detection of an extrasolar planet atmosphere", "charb02",
     "Sodium absorption in HD 209458 b during transit, 2.3 × 10⁻⁴ deeper than the continuum.", "The first exoplanet atmosphere detected.", "#/methods?ch=molecules"),
    (2004, "Bond et al.", "OGLE 2003-BLG-235/MOA 2003-BLG-53", "bond",
     "A planet with 0.4% of its star's mass revealed by a short extra brightening in a lensing event.", "The first planet found by microlensing.", "#/methods?ch=microlensing"),
    (2008, "Marois et al.", "Direct imaging of multiple planets orbiting the star HR 8799", "marois08",
     "Three giant planets photographed around a young star (a fourth followed in 2010).", "The first directly imaged multi-planet system.", "#/methods?ch=imaging"),
    (2008, "Kalas et al.; Gáspár & Rieke 2020", "Fomalhaut b, then reinterpreted", "kalas",
     "An optical image of a 'planet' later explained as an expanding dust cloud from a collision.", "A caution: an image can be dust.", "#/methods?ch=imaging"),
    (2010, "Borucki et al.", "Kepler planet-detection mission: introduction and first results", "borucki",
     "Kepler (launched 2009) stared at one field for four years.", "The start of the statistical era of exoplanets.", "#/galaxy?view=kepler"),
    (2014, "Lissauer et al.; Rowe et al.", "Validation of Kepler's multiple-planet candidates", "rowe14",
     "Showed that candidates in multi-planet systems are almost always real, validating 851 planets in 340 systems.", "Statistical validation at scale.", "#/galaxy?view=kepler"),
    (2015, "Ricker et al.", "Transiting Exoplanet Survey Satellite", "ricker",
     "The mission design of TESS, which began observing in 2018.", "The survey exoplan reads.", "#/methods?ch=survey"),
    (2019, "Royal Swedish Academy of Sciences", "Nobel Prize in Physics", "nobel",
     "Half the prize to Michel Mayor and Didier Queloz for 51 Pegasi b.", "Recognition of the field.", "#/methods?ch=rv"),
    (2023, "JWST Transiting Exoplanet Community ERS Team", "Identification of carbon dioxide in an exoplanet atmosphere", "ers",
     "A 26σ CO₂ feature at 4.3 µm in WASP-39 b.", "The first definitive CO₂ in an exoplanet atmosphere.", "#/methods?ch=spectroscopy"),
]


def _ex(ex: dict, name: str) -> dict:
    return (ex.get("planets") or {}).get(name) or {}


def methods_meta(ex: dict, g: dict | None, story: dict, coverage: dict | None) -> dict:
    """The small part of the Methods data the page's code needs: chapter ids and the stored example
    systems the animated views draw (as the catalogue gives them)."""
    keep = ["pi Men c", "51 Peg b", "HD 80606 b", "WASP-39 b", "TRAPPIST-1 b", "Kepler-9 b", "Kepler-9 c", "HR 8799 b", "HR 8799 c", "HR 8799 d", "HR 8799 e", "GJ 896 Ab",
            "Gaia-4 b", "TRAPPIST-1 e", "Proxima Centauri b"]
    notable = [n for n in (ex.get("planets") or {}) if n not in keep]
    lead = story.get("lead_dip")
    dip = next((d for d in story.get("dips") or [] if d.get("id") == lead), None)
    return {"chapters": [c for c, _ in CHAPTERS], "labels": dict(CHAPTERS),
            "examples": {n: _ex(ex, n) for n in keep + notable if _ex(ex, n)},
            "source": ex.get("source", ""), "fetched_at": ex.get("fetched_at", ""),
            "claret": CLARET_TESS, "mamajek": MAMAJEK, "bands": BANDS,
            "lead_dip": {"id": lead, "depth_ppm": dip.get("depth_ppm"), "pts": dip.get("pts"), "half": dip.get("half")} if dip else None,
            "molecules": [{k: m[k] for k in ("id", "name", "f", "geom")} for m in MOLECULES],
            "lab_bands": LAB_BANDS, "jwst": load_jwst(),
            "population": _pop_meta(), "drake_terms": DRAKE_TERMS, "kopparapu": KOPPARAPU}


def _pop_meta() -> dict | None:
    pop = load_population()
    if not pop:
        return None
    return {"valley": pop["valley"], "hz": [[p["teff"], p["s"], int(p["conservative"]), p["name"], p["radius_re"]] for p in pop["hz"]["planets"]]}


def methods_section(ex: dict, g: dict | None, story: dict, coverage: dict | None, eyebrow: str) -> str:
    e = html.escape
    P = ex.get("planets") or {}
    pm, peg, w39 = _ex(ex, "pi Men c"), _ex(ex, "51 Peg b"), _ex(ex, "WASP-39 b")
    src_line = f"{ex.get('source', 'exoplanet.eu')}, fetched {ex.get('fetched_at', '')[:10]}"
    counts = (g or {}).get("per_method") or {}
    total = (g or {}).get("counts", {}).get("kept", 0)

    def count_line(method: str) -> str:
        if not g:
            return ""
        n = counts.get(method, 0)
        return (f'<p class="mxcount"><b>{n:,}</b> of the {total:,} planets with a stored distance in {e(g["source_short"])} were found by '
                f'{e(g["method_label"][method].lower())} (the first method listed). <a href="#/galaxy?method={method}">Show them on the Galaxy map ›</a></p>'
                f'{year_chart(g, method)}')

    toc = "".join(f'<li><a href="#/methods?ch={c}" data-ch="{c}"><span class="mono">{i + 1:02d}</span>{e(t)}</a></li>' for i, (c, t) in enumerate(CHAPTERS))

    # ----- worked numbers -----
    k_pm = rv_semi_amplitude(pm["orbital_period"], pm["mass"], pm["star_mass"], pm.get("eccentricity") or 0, math.sin(math.radians(pm["inclination"]))) if pm else None
    k_peg = rv_semi_amplitude(peg["orbital_period"], peg["mass_sini"], peg["star_mass"], peg.get("eccentricity") or 0) if peg else None
    k_jup = rv_semi_amplitude(11.862 * 365.25, 1.0, 1.0, 0.049)
    k_earth = rv_semi_amplitude(365.25, GM_EARTH / GM_JUP, 1.0)
    bary_jup = barycentre_offsets(5.204 * AU, 1.0, 1.0)[0] / R_SUN
    bary_earth = barycentre_offsets(AU, GM_EARTH / GM_JUP, 1.0)[0] / 1e3
    k_pm_true = pm.get("k") if pm else None
    u1, u2 = ld_coeffs(pm.get("star_teff") or 6000)
    k_ratio = pm["radius"] * R_JUP / (pm["star_radius"] * R_SUN) if pm else 0.017
    a_rs = pm["semi_major_axis"] * AU / (pm["star_radius"] * R_SUN) if pm else 13.4
    b_pm = pm.get("impact_parameter") or 0.59
    t14, t23 = transit_durations(pm["orbital_period"], a_rs, k_ratio, b_pm, pm["inclination"]) if pm else (0.12, 0.11)
    depth0 = (1 - transit_flux(0, k_ratio, u1, u2)) * 1e6
    depth_b = (1 - transit_flux(b_pm, k_ratio, u1, u2)) * 1e6
    lead = story.get("lead_dip")
    dip = next((d for d in story.get("dips") or [] if d.get("id") == lead), {})
    cls, row = spectral_class(pm.get("star_teff") or 6037)
    rgb = teff_rgb(pm.get("star_teff") or 6037)
    p_tr = transit_probability(pm["star_radius"], pm["semi_major_axis"]) if pm else 0.075
    p_earth = transit_probability(1.0, 1.0)
    dlam = doppler_ratio(k_peg or 56)
    tess_frac = (coverage or {}).get("fractions", {}).get("tess")
    w39_dH = depth_per_scale_height(1116, 2.3, w39["mass"], w39["radius"], w39["star_radius"]) * 1e6 if w39 else 440
    w39_H = scale_height_m(1116, 2.3, w39["mass"], w39["radius"]) / 1e3 if w39 else 930
    pm_teq = pm.get("temp_calculated") or 1147
    pm_dH_h2 = depth_per_scale_height(pm_teq, 2.3, pm["mass"], pm["radius"], pm["star_radius"]) * 1e6 if pm else 16
    pm_dH_steam = depth_per_scale_height(pm_teq, 18, pm["mass"], pm["radius"], pm["star_radius"]) * 1e6 if pm else 2
    gj = _ex(ex, "GJ 896 Ab")
    alpha_gj = astrometric_signature_uas(gj["mass"], gj["star_mass"], gj["semi_major_axis"], gj["star_distance"]) if gj else None
    alpha_jup10 = astrometric_signature_uas(1.0, 1.0, 5.204, 10)
    alpha_earth10 = astrometric_signature_uas(GM_EARTH / GM_JUP, 1.0, 1.0, 10)
    theta_e = einstein_angle_mas(0.3, 0.125)

    ch = {}
    ch["survey"] = f"""
      <p class="mxlede">A survey points a camera at many stars at once and measures each one's brightness again and again. Most stars never show a planet. Only planets whose orbits happen to line up with us can cross their star's face.</p>
      {_stage("scan", LABEL_ILL, "A star field. Reticle rings lock onto stars one at a time, as a survey checks each target. Each locked star shows whether its imagined planet's orbit lines up with us; about one in thirteen do for a pi Men c-like orbit. Star colours follow each star's temperature.")}
      <div class="mxtext">
        <h3>Why only a few transit</h3>
        <p>A planet transits only if its orbit is aligned closely enough with our line of sight. For random orientations the chance is about R★/a, the star's radius over the orbit's size (Winn 2010). Close-in planets around large stars transit more often.</p>
        {_num_rows([("Chance pi Men c's orbit transits", f"{p_tr * 100:.1f}%", f"R★/a from exoplanet.eu R★ = {pm.get('star_radius')} R☉, a = {pm.get('semi_major_axis')} AU [calc]"),
                    ("Chance an Earth–Sun orbit transits", f"{p_earth * 100:.2f}%", "R☉/1 AU, IAU nominal values [calc]"),
                    ("Sky TESS had observed by 18 Oct 2026", f"{tess_frac * 100:.1f}%" if tess_frac else "—", "survey_coverage.json from tess-point (Galaxy coverage panel)")])}
        <p>exoplan reads TESS light curves: one star at a time, about 27 days per sector. <a href="#/galaxy?layers=tess">See TESS's sky coverage ›</a></p>
      </div>"""
    ch["transit"] = f"""
      <p class="mxlede">When a planet crosses its star, it blocks a little light. The dip's depth gives the planet's size relative to the star; its repetition gives the period. <b>This is what exoplan does</b>: its run found pi Men c's transits in TESS sector 1. <a href="#/transit{('?dip=' + e(lead)) if lead else ''}">Open exoplan's Transit case ›</a></p>
      {_stage("system", LABEL_MODEL, f"pi Men, a {e(row)}-like star ({pm.get('star_teff', 6037):.0f} K, drawn in its blackbody colour) with pi Men c crossing it at impact parameter {b_pm}. Below, a limb-darkened model light curve drawn from the stored radii, with exoplan's stored points for its lead dip overlaid as dots.",
               '<button class="btn mxsize" type="button" aria-pressed="false">Planet ×5</button><label class="mxb"><span>b</span><input type="range" min="0" max="1000" value="' + str(round(b_pm / (1 + k_ratio) * 1000)) + '" aria-label="Impact parameter"></label>', tall=True)}
      <div class="mxtext">
        <h3>What shapes the dip</h3>
        <p>The depth is roughly (Rp/R★)². The star is brighter at its centre than its edge (limb darkening), so the bottom of the dip is rounded, not flat, and a central crossing dips deeper than k² (Mandel & Agol 2002; Claret 2017 coefficients for TESS). The four contact points set the total duration T14 and the flat-bottom duration T23 (Winn 2010).</p>
        {_num_rows([("Rp/R★ (k)", f"{k_ratio:.4f}", f"exoplanet.eu Rp = {pm.get('radius')} RJ, R★ = {pm.get('star_radius')} R☉ [calc]"),
                    ("k² (depth with no limb darkening)", f"{k_ratio ** 2 * 1e6:.0f} ppm", "[calc]"),
                    ("Model depth at the stored b", f"{depth_b:.0f} ppm", f"quadratic limb darkening u₁ = {u1:.3f}, u₂ = {u2:.3f} (Claret 2017, {pm.get('star_teff', 6037):.0f} K) [calc]"),
                    ("Model depth for a central crossing", f"{depth0:.0f} ppm", "[calc]"),
                    ("exoplan's stored depth, lead dip", f"{dip.get('depth_ppm', 0):.0f} ppm" if dip else "—", "exoplan run, box fit (real data)"),
                    ("T14 / T23", f"{t14 * 24:.2f} h / {(t23 or 0) * 24:.2f} h", f"Winn 2010 eqs. 14–15 from a/R★ = {a_rs:.2f}, b = {b_pm} [calc]; Huang 2018 publish 2.953 ± 0.047 h"),
                    ("Star", f"{cls} · ≈{row} · rgb({rgb[0]}, {rgb[1]}, {rgb[2]})", "nearest row of Mamajek's sequence; blackbody colour from the CIE 1931 fit")])}
        <p class="note">The curve is a model drawn from stored values (small-planet approximation of Mandel & Agol 2002, circular orbit), not observed data. The dots are exoplan's own stored points for its lead dip. The orbit is not to scale; its tilt is set so the planet crosses at the stored impact parameter.</p>
      </div>"""
    ch["doppler"] = f"""
      <p class="mxlede">Light from a star moving toward us arrives slightly bluer; moving away, slightly redder. Only the motion along our line of sight shifts the light. Motion across the sky (proper motion) shifts nothing.</p>
      {_stage("doppler", LABEL_ILL, "An observer at the bottom. A star moves toward and away from the observer along the line of sight, then across it. Below, a strip of five absorption lines slides blueward when the star approaches and redward when it recedes, and stays put when it moves across. The shift is exaggerated a million-fold and labelled.",
               '<label class="mxmode"><span>Motion</span><select><option value="los">Along the line of sight</option><option value="across">Across the sky</option></select></label>')}
      <div class="mxtext">
        <h3>How small the shift is</h3>
        <p>Δλ/λ = v_r/c, with v_r positive for motion away (redshift). For a wobble of tens of m/s the shift is a ten-millionth of the wavelength, so spectrographs measure it by cross-correlating thousands of lines (Fischer et al. 2016). The star's colour does not visibly change.</p>
        {_num_rows([("51 Peg b's K", f"{peg.get('k')} m/s" if peg.get("k") else "—", f"exoplanet.eu ({src_line})"),
                    ("Δλ/λ for that K", f"{dlam:.1e}", "v/c [calc]"),
                    ("Shift at 500 nm", f"{dlam * 500e-9 * 1e15:.0f} fm", "[calc]")])}
      </div>"""
    ch["rv"] = f"""
      <p class="mxlede">A planet and its star both orbit their shared centre of mass, the barycentre. The star's small orbit makes its light shift back and forth: the radial-velocity curve. Its amplitude K gives the planet's minimum mass, m sin i.</p>
      {_stage("wobble", LABEL_MODEL, "Top-down view with the observer at the bottom. A star and its planet orbit their barycentre, always on a straight line through it, at the same period and opposite phase; the star's motion is exaggerated and labelled. Eccentric orbits speed up near periastron (Kepler's equation). Beside it, the radial-velocity curve is drawn live and a strip of spectral lines shifts blue and red in step.",
               '<label class="mxsys"><span>System</span><select><option value="51 Peg b">51 Peg b</option><option value="HD 80606 b">HD 80606 b (e = 0.93)</option><option value="jupiter">Jupiter–Sun</option><option value="earth">Earth–Sun</option><option value="pi Men c">pi Men c</option></select></label>', tall=True)}
      <div class="mxtext">
        <h3>The numbers</h3>
        <p>K = (2πG/P)^⅓ · Mp sin i / (M★ + Mp)^⅔ / √(1 − e²) (Gaudi & Winn 2007). The star's orbit is a★ = a · Mp/(M★ + Mp); the planet's is a · M★/(M★ + Mp). Eccentric orbits follow Kepler's equation, M = E − e sin E. Masses use the IAU nominal GM values (Prša et al. 2016).</p>
        {_num_rows([("51 Peg b: K from our formula", f"{k_peg:.1f} m/s" if k_peg else "—", f"exoplanet.eu P = {peg.get('orbital_period')} d, m sin i = {peg.get('mass_sini')} MJ, M★ = {peg.get('star_mass')} M☉, e = {peg.get('eccentricity')} [calc]"),
                    ("51 Peg b: K published", f"{peg.get('k')} m/s" if peg.get("k") else "—", "exoplanet.eu; about 56 m/s"),
                    ("Difference", f"{(k_peg / peg['k'] - 1) * 100:+.1f}%" if k_peg and peg.get("k") else "—", "ours vs published; the catalogue mixes values from different papers"),
                    ("Jupiter–Sun K", f"{k_jup:.1f} m/s", "P = 11.862 yr, e = 0.049, IAU nominal masses [calc]"),
                    ("Jupiter–Sun barycentre", f"{bary_jup:.2f} R☉ from the Sun's centre", "just outside the surface [calc]"),
                    ("Earth–Sun K", f"{k_earth * 100:.1f} cm/s", "[calc]"),
                    ("Earth–Sun barycentre", f"{bary_earth:.0f} km from the Sun's centre", "deep inside the Sun [calc]"),
                    ("pi Men c: K from our formula", f"{k_pm:.2f} m/s" if k_pm else "—", f"exoplanet.eu stored K = {k_pm_true} m/s; Huang et al. 2018 values (4.82 M⊕) give 1.57 m/s [calc]"),
                    ("Best spectrograph stability", "< 25 cm/s in a night", "ESPRESSO (Pepe et al. 2021)")])}
        <h3>Why Earth twins are hard</h3>
        <p>An Earth twin moves its Sun-like star by about {k_earth * 100:.0f} cm/s. ESPRESSO holds better than 25 cm/s within a night and about 50 cm/s over months (Pepe et al. 2021). The star's own surface (granulation, oscillations, spots) adds RV noise of order m/s (Fischer et al. 2016), larger than the signal itself.</p>
        {_stage("jitter", LABEL_ILL, "A close-up of a Sun-like star's surface: granulation cells rise (blueshifted) and sink (redshifted), with tracked markers. Beside it, an Earth twin's radial-velocity signal of about 9 centimetres per second over two years, with each point scattered by the chosen noise level, showing the signal buried in the star's own motion.",
               '<label class="mxmode"><span>Noise per point</span><select><option value="1">stellar surface, order of 1 m/s</option><option value="0.25">a night at ESPRESSO, 25 cm/s</option><option value="0.1">ESPRESSO instrument floor, 10 cm/s</option></select></label>')}
        <div class="mxladder" role="img" aria-label="Radial-velocity scale: Earth twin about 9 centimetres per second; ESPRESSO within a night under 25 centimetres per second; stellar surface noise of order 1 metre per second; pi Men c about 1.6 metres per second; Jupiter twin 12.5 metres per second; 51 Peg b 56 metres per second.">
          {''.join(f'<div style="--x:{(math.log10(v) + 2) / 4 * 100:.1f}%" class="{"l" if (math.log10(v) + 2) / 4 < 0.15 else "r" if (math.log10(v) + 2) / 4 > 0.8 else ""}"><i></i><span>{e(t)}</span></div>' for v, t in ((k_earth, f"Earth twin {k_earth * 100:.0f} cm/s"), (0.25, "ESPRESSO night < 25 cm/s"), (1.0, "stellar noise ~1 m/s"), (k_pm or 1.5, f"pi Men c {k_pm or 0:.1f} m/s"), (k_jup, f"Jupiter twin {k_jup:.1f} m/s"), (k_peg or 56, f"51 Peg b {k_peg or 0:.0f} m/s")))}
          <p class="mxaxis"><span>1 cm/s</span><span>10 cm/s</span><span>1 m/s</span><span>10 m/s</span><span>100 m/s</span></p>
        </div>
      </div>"""
    ch["astrometry"] = f"""
      <p class="mxlede">The star's small orbit also moves its position on the sky. Astrometry measures that tiny loop, which gives the orbit's tilt and so the planet's true mass. The signal grows with the planet's mass and orbit and shrinks with distance.</p>
      {_stage("astrometry", LABEL_ILL, "The sky plane. A star drifts in a straight line (proper motion), loops once a year (parallax), and traces a small extra ellipse from its planet's pull, exaggerated and labelled. Toggles separate the three motions.",
               '<label class="mxmode"><span>Show</span><select><option value="all">All three motions</option><option value="pm">Proper motion only</option><option value="plx">Parallax only</option><option value="reflex">Planet wobble only</option></select></label>')}
      <div class="mxtext">
        <p>α = (Mp/M★)(a/d): the star's angular orbit, in arcseconds for a in AU and d in parsecs (Perryman et al. 2014). A wobble consistent with an orbiting companion becomes a planet only when its mass is pinned below the planetary limit, usually with RV as well, as for Gaia-4b (Stefánsson et al. 2025). Gaia ended science observations in January 2025; its fourth data release, planned for December 2026, carries the epoch astrometry.</p>
        {_num_rows([("Jupiter twin at 10 pc", f"{alpha_jup10:.0f} µas", "[calc]"),
                    ("Earth twin at 10 pc", f"{alpha_earth10:.2f} µas", "[calc]"),
                    ("GJ 896 Ab", f"{alpha_gj:.0f} µas" if alpha_gj else "—", f"exoplanet.eu Mp = {gj.get('mass')} MJ, M★ = {gj.get('star_mass')} M☉, a = {gj.get('semi_major_axis')} AU, d = {gj.get('star_distance')} pc [calc]; found by astrometry (Curiel et al. 2022)")])}
        {count_line("astrometry")}
      </div>"""
    ch["microlensing"] = f"""
      <p class="mxlede">When a foreground star (the lens) passes almost in front of a background star (the source), its gravity bends and magnifies the source's light for days to weeks. A planet around the lens adds a short extra spike. The lens itself is often too faint to see.</p>
      {_stage("lens", LABEL_ILL, "A perspective grid of space, dented under a foreground lens star and its planet, with a distant source star behind and a telescope in front. The lens drifts across the line of sight; below, the source's brightness rises and falls in a symmetric magnification curve with a short planetary spike. The bending is exaggerated a million-fold.", tall=True)}
      <div class="mxtext">
        <p>Point-lens magnification: A(u) = (u² + 2)/(u√(u² + 4)), with u the lens–source separation in Einstein radii; A(1) = 1.342. The Einstein angle is θ_E = √(κ M π_rel), κ ≈ 8.14 mas/M☉ (Gaudi 2012). A planetary spike lasts about √q · t_E, where q is the planet-to-star mass ratio. <b>An event never repeats</b>, so the planet cannot be re-observed this way.</p>
        {_num_rows([("A(u = 1)", f"{paczynski(1.0):.3f}", "[calc]"),
                    ("θ_E for 0.3 M☉ and π_rel = 125 µas", f"{theta_e:.2f} mas", "Gaudi 2010 example [calc]"),
                    ("Typical Einstein crossing time", "≈ 19 days", "Gaudi 2010"),
                    ("First microlensing planet", "2004", "Bond et al. 2004")])}
        {count_line("microlensing")}
      </div>"""
    ch["imaging"] = f"""
      <p class="mxlede">To photograph a planet, the starlight must be blocked. A Jupiter twin reflects about a billionth of its Sun's visible light; an Earth twin about 10⁻¹⁰ (Lawson et al. 2013). Young giant planets glow in the infrared and are far easier, which is why imaging finds young, wide, massive planets.</p>
      {_stage("coronagraph", LABEL_ILL, "Starlight blocking, in four scenes. A sun-like occulter (an illustration based on SOHO LASCO); a coronagraph mask sliding over a star so the glare collapses into residual speckles and the four HR 8799 planets appear on schematic orbits; a starshade flying far in front of a telescope, not to scale; and a two-telescope nulling interferometer whose dark fringe cancels the star.",
               '<label class="mxmode"><span>Scene</span><select><option value="mask">Coronagraph and HR 8799</option><option value="sun">The Sun&#x27;s corona</option><option value="shade">Starshade</option><option value="null">Nulling</option></select></label>', tall=True)}
      <div class="mxtext">
        <h3>Blocking starlight</h3>
        <ol class="mxsteps">
          <li><b>History.</b> Bernard Lyot invented the coronagraph in 1930 to study the Sun's corona without an eclipse; a focal-plane mask blocks the disc and a "Lyot stop" removes the diffracted light (Lyot 1939). SOHO's LASCO coronagraphs show the same idea every day (Brueckner et al. 1995). The Sun scene above is an illustration based on LASCO, not a LASCO image.</li>
          <li><b>Coronagraph families.</b> Lyot-type amplitude masks, apodised pupils and phase masks such as the vortex. The key figure is the inner working angle, in units of λ/D (Mawet et al. 2012). Earth at 10 pc sits 0.1″ from its star: about 5.3 λ/D for a 6 m telescope at 550 nm [calc].</li>
          <li><b>Adaptive optics and speckles.</b> A deformable mirror flattens the turbulent wavefront hundreds of times a second. What remains are speckles; angular differential imaging lets the sky rotate while speckles stay fixed, so they can be subtracted (Marois et al. 2006).</li>
          <li><b>Starshade.</b> A flower-shaped screen flown far in front of a telescope (Cash 2006). The Roman Starshade Rendezvous concept: 26 m at 26,000 km; HabEx: 52 m at about 76,600 km (HabEx Final Report).</li>
          <li><b>Nulling interferometry.</b> Two telescopes combined half a wave out of phase cancel the star on a dark fringe while an off-axis planet sits on a bright one (Bracewell 1978; the LIFE concept, Quanz et al. 2022).</li>
        </ol>
        <h3>The contrast ladder</h3>
        {contrast_ladder()}
        <p class="note">HR 8799's planets on the canvas use exoplanet.eu's semi-major axes and eccentricities; their orientation on the sky is illustrative, and time is compressed. Contrasts from different instruments are measured at different separations, wavelengths and significances, so the rungs are not directly comparable.</p>
        {count_line("imaging")}
      </div>"""
    jw = load_jwst()
    if jw:
        peak = max(jw["points"], key=lambda p: p[3])
        jwst_stage = _stage("jwst", LABEL_DATA, f"JWST NIRSpec PRISM transmission spectrum of WASP-39 b: {len(jw['points'])} binned points with error bars and the paper's best-fit model; the deepest point is at {peak[0]:.2f} micrometres, the carbon dioxide band.", static=True)
        jwst_note = (f'<p class="note"><b>Real data, cited.</b> {e(jw["citation"])}; data: <a href="{e(jw["doi"])}" rel="noopener">{e(jw["source"])}</a>, '
                     f'licence {e(jw["licence"])}. File {e(jw["files"]["spectrum"])}, fetched {e(jw["fetched_at"][:10])}; {e(jw["note"])} The line is the paper\'s best-fit model, not exoplan\'s.</p>')
    else:
        jwst_stage = ""
        jwst_note = '<p class="note">The JWST WASP-39 b spectrum (Zenodo doi:10.5281/zenodo.10161743) is not in this build, so no real spectrum is plotted.</p>'
    lab_controls = ('<span class="mxtogs" role="group" aria-label="Molecules">' + "".join(
        f'<button class="btn mxtog" type="button" data-mol="{m}" aria-pressed="{"true" if m in ("H2O", "CO2", "Na", "K") else "false"}">{e(lab)}</button>'
        for m, lab in (("H2O", "H₂O"), ("CO2", "CO₂"), ("CO", "CO"), ("CH4", "CH₄"), ("SO2", "SO₂"), ("Na", "Na"), ("K", "K"))) + "</span>"
        '<label class="mxlab"><span>Band strength</span><input type="range" data-ctl="n" min="0" max="60" value="20" aria-label="Band strength in scale heights"></label>'
        '<label class="mxlab"><span>Temperature</span><input type="range" data-ctl="T" min="300" max="2000" step="10" value="1116" aria-label="Temperature in kelvin"></label>'
        '<label class="mxlab"><span>μ</span><select data-ctl="mu"><option value="2.3" selected>2.3 (H₂-rich)</option><option value="4">4</option><option value="10">10</option><option value="18">18 (steam)</option><option value="44">44 (CO₂)</option></select></label>'
        + ('<button class="btn mxtog" type="button" data-ctl="real" aria-pressed="false">Load real example: WASP-39 b</button>' if jw else ""))
    ch["spectroscopy"] = f"""
      <p class="mxlede">During a transit, a sliver of starlight passes through the planet's atmosphere at its edge. Where molecules absorb, the atmosphere is opaque higher up, so the planet looks slightly bigger at those wavelengths. <b>exoplan does not do spectroscopy</b>: this explains how JWST-class telescopes read atmospheres.</p>
      {_stage("transmission", LABEL_ILL, "A planet's limb with its thin atmosphere drawn ten times too thick, starlight passing through it. Two spectrum bars from 0.5 to 5.1 micrometres in false colour: starlight only, and during transit, which gains dark absorption bands at the real positions of sodium, potassium, water, methane, carbon dioxide and carbon monoxide as the planet crosses.", tall=True)}
      <div class="mxtext">
        <p>One scale height H = k_B T/(μ m_H g) of atmosphere changes the transit depth by about 2 H Rp/R★². Strong features span a few scale heights. Hot, puffy, hydrogen-rich planets around small stars give the biggest signals (Seager & Sasselov 2000; Winn 2010).</p>
        {_num_rows([("WASP-39 b scale height (μ = 2.3)", f"{w39_H:.0f} km", f"exoplanet.eu Mp = {w39.get('mass')} MJ, Rp = {w39.get('radius')} RJ; Teq 1116 K (Faedi et al. 2011) [calc]"),
                    ("WASP-39 b: depth change per scale height", f"{w39_dH:.0f} ppm", f"R★ = {w39.get('star_radius')} R☉ [calc]"),
                    ("WASP-39 b: CO₂ at 4.3 µm", "26σ", "JWST ERS Team 2023"),
                    ("pi Men c: per scale height, H₂-rich", f"{pm_dH_h2:.0f} ppm", f"Teq {pm_teq:.0f} K (exoplanet.eu) [calc]"),
                    ("pi Men c: per scale height, steam (μ = 18)", f"{pm_dH_steam:.1f} ppm", "[calc]"),
                    ("pi Men c: exoplan's stored transit depth", f"{dip.get('depth_ppm', 0):.0f} ppm" if dip else "—", "exoplan run (real data)")])}
        <p class="note">The bars are schematic: band positions are real (NIST CCCBDB fundamentals and Schwieterman et al. 2018), shapes and strengths are not. False colour: infrared is invisible to the eye.</p>
        <h3>A real spectrum: WASP-39 b with JWST</h3>
      </div>
      {jwst_stage}
      <div class="mxtext">
        {jwst_note}
        <h3>Atmosphere Lab</h3>
        <p>Switch molecules on and off and change the temperature, the mean molecular weight and how strong the bands are. The lab computes the scale height and the depth per scale height from WASP-39 b's stored mass and radii, then adds each molecule's bands. It is a toy model, not a radiative-transfer calculation: band centres are real, band widths are chosen for display, and strengths are in scale heights set by the slider.</p>
      </div>
      {_stage("atmlab", LABEL_MODEL, "The Atmosphere Lab: a model transmission spectrum from 0.5 to 5.4 micrometres for the molecules switched on, at the chosen temperature, mean molecular weight and band strength, with WASP-39 b's JWST points overlaid when loaded.", lab_controls, static=True)}"""
    cards = "".join(_molecule_card(m) for m in MOLECULES)
    ch["molecules"] = f"""
      <p class="mxlede">Each gas absorbs at its own wavelengths. A molecule's shape sets how it vibrates, and its vibrations set where it absorbs in the infrared. No single gas proves life; a biosignature needs context.</p>
      {_stage("molecule", LABEL_ILL, "A rotating ball-and-stick model of the selected molecule at its measured bond lengths and angles (NIST CCCBDB).",
               '<label class="mxmode"><span>Molecule</span><select>' + "".join(f'<option value="{m["id"]}">{e(m["f"])} · {e(m["name"])}</option>' for m in MOLECULES) + '</select></label>')}
      <div class="mxmols">{cards}</div>
      <section class="mxcheck" aria-labelledby="h-biocheck">
        <h3 id="h-biocheck">Biosignature checklist</h3>
        <ol>
          <li><b>Detection significance.</b> How many sigma, from how many independent analyses?</li>
          <li><b>Context.</b> The star, the planet's temperature and the other gases present (Meadows et al. 2018).</li>
          <li><b>Disequilibrium.</b> Gases that would react away without a source, such as O₂ with CH₄ (Krissansen-Totton et al. 2018).</li>
          <li><b>Abiotic sources ruled out.</b> Every non-living way to make the gas, checked (Schwieterman et al. 2018; Catling et al. 2018).</li>
        </ol>
        <p>No gas has passed this checklist on any planet. Life has not been detected anywhere beyond Earth.</p>
        <div class="mxcases">
          <article><h4>Phosphine on Venus: contested</h4><p>2020: phosphine reported in Venus's clouds from JCMT and ALMA (Greaves et al. 2020). Re-analyses found no significant detection (Snellen et al. 2020; Villanueva et al. 2021), with a reply by the original team (Greaves et al. 2021). Still disputed.</p><ul class="mxsrc">{_src(["greaves", "snellen20", "villanueva", "greaves21", "bains"])}</ul></article>
          <article><h4>DMS on K2-18 b: tentative, debated</h4><p>2023: methane and CO₂ in an H₂-rich atmosphere, with "potential signs" of DMS (Madhusudhan et al. 2023). 2025: a ~3σ MIRI feature consistent with DMS and/or DMDS (Madhusudhan et al. 2025). Independent analyses found insufficient evidence (Schmidt et al. 2025; Luque et al. 2025). Not established.</p><ul class="mxsrc">{_src(["madhu23", "madhu25", "schmidt", "luque"])}</ul></article>
        </div>
      </section>"""
    hist = "".join(
        f'<li class="mxpaper"><span class="mono yr">{y}</span><div><p class="au">{e(au)}</p><h4>{e(t)}</h4><p>{e(s)}</p><p class="why">{e(w)}</p>'
        f'<p class="links"><a href="{e(SOURCES[k][1])}" rel="noopener">{e(SOURCES[k][0])}</a><a href="{e(link)}">Related ›</a></p></div></li>'
        for y, au, t, k, s, w, link in HISTORY)
    run_year = (story.get("run_created") or "")[:4]
    hist += (f'<li class="mxpaper own"><span class="mono yr">{e(run_year or "2026")}</span><div><p class="au">exoplan (this project)</p><h4>pi Men c recovered in a blind search of TESS sector 1</h4>'
             f'<p>exoplan\'s run found dips at pi Men c\'s period without being told where to look. pi Men c was already known (Huang et al. 2018); this is a recovery, not a discovery.</p>'
             f'<p class="links"><a href="#/transit{("?dip=" + e(lead)) if lead else ""}">Open the Transit case ›</a></p></div></li>')
    ch["history"] = f"""
      <p class="mxlede">Key papers and milestones, summarised in our own words. Each links to its paper (DOI) and to the part of exoplan it relates to.</p>
      <ol class="mxtimeline">{hist}</ol>"""


    # ----- timing and phase -----
    t1b, k9b, k9c, hd189 = _ex(ex, "TRAPPIST-1 b"), _ex(ex, "Kepler-9 b"), _ex(ex, "Kepler-9 c"), _ex(ex, "HD 189733 Ab")
    k_t1b = t1b["radius"] * R_JUP / (t1b["star_radius"] * R_SUN) if t1b else 0.087
    occ_bb = thermal_eclipse_depth(k_t1b, 503, t1b.get("star_teff") or 2566, 15) * 1e6
    ch["timing"] = f"""
      <p class="mxlede">A transit is one moment in an orbit. The rest of the orbit carries information too: when transits arrive, how the planet glows as it turns, when it slips behind its star, and which half of the spinning star it covers.</p>
      {_stage("timing", LABEL_ILL, "Four scenes. Transit timing: two planets near a 2:1 period ratio tug each other, so the inner planet's transits arrive early and late and an O−C diagram builds up. Secondary eclipse: the planet slips behind its star half an orbit after transit, a much smaller dip, drawn ten times deeper. Phase curve: a tidally locked planet shows more of its hot day side towards occultation, with its peak shifted by winds. Rossiter–McLaughlin: the planet covers the approaching and then the receding half of the rotating star, so the star's measured velocity swings during transit.",
               '<label class="mxmode"><span>Scene</span><select><option value="ttv">Transit timing (TTV)</option><option value="eclipse">Secondary eclipse</option><option value="phase">Phase curve</option><option value="rm">Rossiter–McLaughlin</option></select></label><label class="mxlam"><span>Spin–orbit angle λ</span><input type="range" min="0" max="180" value="0" aria-label="Projected spin–orbit angle in degrees"></label>', tall=True)}
      <div class="mxtext">
        <h3>The numbers</h3>
        {_num_rows([("Kepler-9 b and c periods", f"{k9b.get('orbital_period')} d and {k9c.get('orbital_period')} d", "exoplanet.eu; near 2:1, so their transits shift by minutes per orbit (Holman et al. 2010)"),
                    ("TRAPPIST-1 b eclipse at 15 µm, measured", "861 ± 99 ppm", "JWST MIRI (Greene et al. 2023); dayside 503 K, as expected for bare rock"),
                    ("Same, blackbody star and planet", f"{occ_bb:.0f} ppm", f"δ ≈ k² B(503 K)/B({t1b.get('star_teff', 2566):.0f} K) at 15 µm, k from exoplanet.eu radii [calc]; real analyses use a stellar model spectrum, not a blackbody"),
                    ("HD 189733 b hot-spot offset", "16 ± 6° before opposition", "Spitzer 8 µm phase curve (Knutson et al. 2007)"),
                    ("Rossiter–McLaughlin, HD 189733 b", f"{rm_amplitude(3.5, 0.157):.0f} m/s", "K_R ≈ V sin I · k² with V sin I = 3.5 km/s, k = 0.157 (Gaudi & Winn 2007, which lists 88 m/s) [calc]"),
                    ("Rossiter–McLaughlin, HD 209458 b", f"{rm_amplitude(4.7, 0.121):.0f} m/s", "V sin I = 4.7 km/s, k = 0.121 (Gaudi & Winn 2007 list 70 m/s) [calc]")])}
        <p class="note">exoplan measures each dip's time and checks the odd and even dips against each other; it does not fit timing variations, phase curves or eclipses. The secondary-eclipse depth on the canvas is drawn ten times deeper and says so; the TTV amplitude is illustrative. Spin–orbit angles span aligned, polar and retrograde orbits (Albrecht et al. 2022).</p>
      </div>"""

    # ----- false positives -----
    ch["falsepos"] = f"""
      <p class="mxlede">Many transit-like dips are not planets on the target star. A dip is evidence; vetting asks what else could make it. This is where exoplan's own checks live.</p>
      {_stage("falsepos", LABEL_ILL, "Five ways to fake a planet, each with its sky geometry on a grid of TESS pixels (21 arcseconds each, drawn to scale) and the light curve it makes: an eclipsing binary with a V-shaped grazing eclipse; a background eclipsing binary diluted by the target's light; a hierarchical triple; odd and even eclipses of different depth when the period is half the true one; and an instrumental jump such as a momentum dump.",
               '<label class="mxmode"><span>Scenario</span><select><option value="eb">Eclipsing binary (grazing, V-shaped)</option><option value="beb">Background eclipsing binary</option><option value="heb">Hierarchical triple</option><option value="oddeven">Odd and even depths differ</option><option value="sys">Systematics</option></select></label>', tall=True)}
      <div class="mxtext">
        <h3>How often, and what exoplan checks</h3>
        {_num_rows([("Kepler candidates that were false positives", "9.4%", "overall; 17.7% for giants (Fressin et al. 2013)"),
                    ("TESS prime-mission TOIs found false by follow-up", "565 of 2,241 (≈25%)", "Guerrero et al. 2021"),
                    ("A 50% binary eclipse diluted 1,000 times", f"{diluted_depth(0.5, 1e-3) * 1e6:.0f} ppm", "δ_obs = δ_true · F_target/F_total [calc]: the depth of a small planet"),
                    ("pi Men c's shape, T23/T14", f"{(t23 or 0) / t14:.2f}", "flat-bottomed (U), not V [calc from the transit chapter]")])}
        <p>exoplan's vetting (vet.py) flags, from the light curve alone: <code>odd_even_mismatch</code> (odd and even depths differ), <code>secondary_eclipse</code> (a dip at phase 0.5), <code>low_snr</code>, <code>too_short</code>, <code>edge_event</code> and <code>insufficient_points</code>. It has no pixel-level centroid or difference-image check and no statistical validation, so a blended background binary can pass. <a href="#/sentinels">See the reviewers ›</a> · <a href="#/transit">See a vetted case ›</a></p>
      </div>"""

    # ----- population -----
    pop = load_population()
    if pop:
        v, hzd = pop["valley"], pop["hz"]
        pm_re = pm["radius"] * 11.209 if pm else None
        L_pm = (pm["star_radius"] ** 2 * (pm["star_teff"] / 5772) ** 4) if pm else 1.45
        hz_pm = [hz_distance_au(l, pm.get("star_teff", 6037), L_pm) for l in ("runaway_greenhouse", "maximum_greenhouse")]
        s_pm = L_pm / pm["semi_major_axis"] ** 2 if pm else 309
        pop_html = f"""
      {_stage("valley", LABEL_DATA, f"Histogram of {v['n']:,} planet radii from exoplanet.eu (period under 100 days), on log bins from 0.5 to 20 Earth radii, with the 1.5–2 Earth-radius valley marked and pi Men c's radius shown.", static=True)}
      <div class="mxtext">
        <p>Small close-in planets come in two groups: rocky super-Earths below about 1.5 R⊕ and gas-wrapped sub-Neptunes around 2–3 R⊕, with fewer in between (Fulton et al. 2017 found at least a factor-of-two deficit at 1.5–2.0 R⊕ in a carefully measured sample). The leading explanations strip thin envelopes from small cores: photoevaporation (Owen & Wu 2017) or core-powered mass loss (Gupta & Schlichting 2019).</p>
        <p class="note">These are raw catalogue counts ({e(v['rule'])}), not occurrence rates: nothing corrects for which planets are easier to find, and catalogue radii carry the stars' radius errors. The dip is shallower here than in Fulton et al.'s corrected, precise sample. pi Men c's stored radius is {pm_re:.2f} R⊕.</p>
      </div>
      {_stage("hz", LABEL_DATA, f"Stellar temperature against the starlight each planet receives, for the {hzd['n_optimistic']} catalogue planets inside the optimistic habitable zone, with the conservative and optimistic limits of Kopparapu et al. 2014 drawn as curves.", static=True)}
      <div class="mxtext">
        <p>The habitable zone is the range of starlight in which an Earth-like planet could keep liquid surface water. Its limits come from climate models as a flux that depends on the star's temperature (Kopparapu et al. 2014). Being in it is necessary, not sufficient: it says nothing about a planet's atmosphere, and many planets inside it are giants.</p>
        {_num_rows([("Sun's conservative habitable zone", f"{hz_distance_au('runaway_greenhouse', 5780, 1):.2f}–{hz_distance_au('maximum_greenhouse', 5780, 1):.2f} AU", "Kopparapu et al. 2014, Table 1 [calc]"),
                    ("pi Men's conservative habitable zone", f"{hz_pm[0]:.2f}–{hz_pm[1]:.2f} AU", f"L = {L_pm:.2f} L☉ from exoplanet.eu R★ and Teff [calc]"),
                    ("Starlight on pi Men c", f"{s_pm:.0f} × Earth's", f"a = {pm.get('semi_major_axis')} AU: far inside, a hot planet [calc]"),
                    ("Catalogue planets in the conservative zone", f"{hzd['n_conservative']:,}", f"of {hzd['sample']:,} with the needed stored values (exoplanet.eu) [calc]"),
                    ("…in the optimistic zone", f"{hzd['n_optimistic']:,}", "[calc]"),
                    ("Earth-size planets in the zone per Sun-like star (η⊕)", "0.37–0.60", "conservative zone, 0.5–1.5 R⊕, with wide errors (Bryson et al. 2021)")])}
      </div>"""
    else:
        pop_html = '<p class="note">The population figures (docs/results/population_stats.json) are not in this build.</p>'
    ch["population"] = f"""
      <p class="mxlede">With thousands of planets, patterns appear. Two of them: a valley in the sizes of small planets, and the zone around each star where liquid water could last.</p>{pop_html}"""

    # ----- equations of life -----
    mc = drake_mc()
    ch["equations"] = f"""
      <p class="mxlede">The Drake and Seager equations are ways to organise what we do not know. They are speculative frameworks, not predictions: no number on this page is an estimate of real civilisations or of life.</p>
      <div class="mxeq" role="group" aria-label="Drake equation calculator">
        <p class="mono mxeqf">N = R★ · f_p · n_e · f_l · f_i · f_c · L</p>
        <div class="mxterms" id="mxdrake"></div>
        <div class="mxpresets" role="group" aria-label="Presets"><button class="btn" type="button" data-preset="drake_lo">Drake 1961 (low end)</button><button class="btn" type="button" data-preset="drake_hi">Drake 1961 (high end)</button><button class="btn" type="button" data-preset="alt">A commonly quoted set</button><button class="btn" type="button" data-preset="data">Data where we have it</button></div>
        <p class="mxresult" aria-live="polite" id="mxdrakeN"></p>
        <p class="note">Presets: the 1961 Green Bank values and the "commonly quoted set" are repeated in secondary sources; the meeting's own record was not checked. "Data where we have it" uses the measured terms below and leaves the unknown ones where you set them. R★ is stars per year; the measured Milky Way rate of 1.65 ± 0.19 M☉ per year (Licquia & Newman 2015) is a mass, not a count.</p>
      </div>
      <table class="mxnums mxknown"><thead><tr><th scope="col">Term</th><th scope="col">How well we know it</th><th scope="col">Value and source</th></tr></thead><tbody>
        <tr><th scope="row">R★</th><td><span class="kn measured">Measured</span></td><td>1.65 ± 0.19 M☉/yr star formation (Licquia & Newman 2015); stars per year needs an initial mass function</td></tr>
        <tr><th scope="row">f_p</th><td><span class="kn measured">Measured</span></td><td>≈ 1: 0.77 small planets per GK star at 50–300 d (Burke et al. 2015); ≈ 2.5 per M dwarf at P &lt; 200 d (Dressing & Charbonneau 2015)</td></tr>
        <tr><th scope="row">n_e</th><td><span class="kn constrained">Constrained</span></td><td>η⊕ = 0.37–0.60 for 0.5–1.5 R⊕ in the conservative zone around 4800–6300 K stars (Bryson et al. 2021); 11 ± 4% for 1–2 R⊕ at 1–4 × Earth's flux (Petigura et al. 2013)</td></tr>
        <tr><th scope="row">f_l, f_i, f_c, L</th><td><span class="kn unknown">Unknown</span></td><td>No data. Any value is an opinion.</td></tr>
      </tbody></table>
      {_stage("drake", LABEL_SPEC, f"A histogram of log10 N from {20000:,} Monte Carlo draws of the Drake terms over log-uniform ranges, with the median and the 90% interval marked, and a bar for each term's share of the spread.", '<label class="mxlab"><span>Range of f_l (orders of magnitude)</span><input type="range" data-ctl="fl" min="1" max="40" value="10" aria-label="Orders of magnitude spanned by f_l"></label>', static=True)}
      <div class="mxtext">
        <p>One number hides the uncertainty. Following Sandberg, Drexler & Ord (2018), each term is drawn from a range instead: R★ 1–100, f_p 0.1–1, n_e 0.1–1, f_i 0.001–1, f_c 0.01–1, L 100–10¹⁰ years, all log-uniform. Their f_l comes from a log-normal model of the rate at which life starts; here f_l is a log-uniform stand-in from 10⁻ᵏ to 1, with k on the slider. Draws are seeded, so the result repeats.</p>
        {_num_rows([("This page, k = 10: median N", f"{10 ** mc['median_log10']:.2g}", f"90% of draws between 10^{mc['p05_log10']:.1f} and 10^{mc['p95_log10']:.1f} [calc]"),
                    ("This page, k = 10: P(N < 1)", f"{mc['p_lt_1'] * 100:.0f}%", "[calc]"),
                    ("Sandberg et al. 2018: median N", "0.32", "with their f_l model; the mean is about 27 million, which is why a single average misleads"),
                    ("Sandberg et al. 2018: P(N < 1)", "≈ 52%", "their priors")])}
        <h3>The Seager equation</h3>
        <p class="mono mxeqf">N = N★ · F_Q · F_HZ · F_O · F_L · F_S</p>
        <p>It counts planets where a biosignature gas could be detected, not civilisations (Seager 2018): stars observed, the fraction quiet, with rocky planets in the habitable zone, observable, with life, and whose life makes a detectable gas.</p>
        <div class="mxterms" id="mxseager"></div>
        <p class="mxresult" aria-live="polite" id="mxseagerN"></p>
        <p class="note">Starting values: N★ = 30,000 M dwarfs bright enough for JWST, F_Q · F_HZ = 0.15, F_O = 0.001, F_L = 1, F_S = 0.5, giving N ≈ 2. They come from secondary summaries of Seager's talk and paper, not checked against the paper here; F_L = 1 is an assumption, not a measurement. The habitable-zone fraction links to the Population chapter's figures.</p>
      </div>"""

    sources = {
        "timing": ["holman", "agol", "greene", "deming05", "knutson", "gaudiwinn", "albrecht", "winn"],
        "falsepos": ["fressin", "guerrero", "twicken", "winn"],
        "population": ["fulton", "vaneylen", "owen", "gupta", "kopparapu", "bryson"],
        "equations": ["sandberg", "seager18", "licquia", "burke15", "dressing15", "bryson", "petigura"],
        "survey": ["winn", "ricker", "borucki", "mamajek", "wyman"], "transit": ["winn", "mandel", "claret", "huang", "mamajek", "wyman", "prsa"],
        "doppler": ["fischer", "mayor"], "rv": ["gaudiwinn", "mayor", "pepe", "fischer", "prsa"], "astrometry": ["perryman", "stefansson", "curiel"],
        "microlensing": ["gaudi12", "gaudi10", "bond", "beaulieu"],
        "imaging": ["lawson", "lyot", "lasco", "mawet", "marois06", "marois08", "cash", "habex", "bracewell", "life", "bailey", "carter23", "roman"],
        "spectroscopy": ["seager", "winn", "faedi", "ers", "carter24", "carter24data", "schwieterman", "cccbdb"],
        "molecules": ["cccbdb", "schwieterman", "meadows", "catling", "krissansen"], "history": [],
    }
    tags = {"transit": "exoplan does this", "spectroscopy": "explainer: exoplan does not do this"}
    sections = []
    for i, (cid, title) in enumerate(CHAPTERS):
        prev = CHAPTERS[i - 1] if i else None
        nxt = CHAPTERS[i + 1] if i + 1 < len(CHAPTERS) else None
        cnt = count_line(METHOD_OF[cid]) if cid in ("transit", "rv") else ""
        srcs = f'<details class="mxsources"><summary>Sources</summary><ul class="mxsrc">{_src(sources[cid])}</ul></details>' if sources[cid] else ""
        nav = (f'<nav class="mxnav" aria-label="Chapters">'
               + (f'<a class="btn" href="#/methods?ch={prev[0]}">‹ {e(prev[1])}</a>' if prev else "<span></span>")
               + (f'<a class="btn primary" href="#/methods?ch={nxt[0]}">{e(nxt[1])} ›</a>' if nxt else "") + "</nav>")
        sections.append(f'<article class="mxch" id="mx-{cid}" data-ch="{cid}" aria-labelledby="h-mx-{cid}" hidden>'
                        f'<header><p class="eyebrow">Chapter {i + 1} of {len(CHAPTERS)}{(" · " + e(tags[cid])) if cid in tags else ""}</p>'
                        f'<h2 id="h-mx-{cid}">{e(title)}</h2></header>{ch[cid]}{cnt}{srcs}{nav}</article>')
    return f"""<header class="headrow">
        <div>{eyebrow}<h1 class="lead-h" id="h-methods" tabindex="-1">How planets are found.<br><span class="grey">And how exoplan finds them.</span></h1>
        <p>{len(CHAPTERS)} chapters, each an animated explainer with its physics and sources. Every drawing says whether it is an illustration, a model from stored values, or real data, and by how much it is exaggerated. Only the transit chapter is something exoplan itself does.</p></div>
      </header>
      <nav class="mxtoc" aria-label="Methods chapters"><ol>{toc}</ol></nav>
      {''.join(sections)}"""


def _molecule_card(m: dict) -> str:
    e = html.escape
    seen = "".join(f'<li>{e(t)} (<a href="{e(SOURCES[k][1])}" rel="noopener">{e(SOURCES[k][0].split(",")[0])}</a>)</li>' for t, k in m["seen"]) or "<li>None in exoplanets so far.</li>"
    g = m["geom"]
    geo = ("an atom" if g["shape"] == "atom" else f"{g['shape']}, bond {g['r']} Å" + (f", angle {g['angle']}°" if g.get("angle") else ""))
    return (f'<article class="mxmol" data-mol="{m["id"]}"><h4>{e(m["f"])} <span>{e(m["name"])}</span></h4>'
            f'<dl><dt>Geometry</dt><dd>{e(geo)} (CCCBDB)</dd><dt>Bands (µm)</dt><dd>{e(m["bands"])}</dd><dt>Seen by</dt><dd>{e(m["who"])}</dd>'
            f'<dt>Exoplanet detections</dt><dd><ul>{seen}</ul></dd><dt>Why it matters</dt><dd>{e(m["why"])}</dd>'
            f'<dt>Without life?</dt><dd>{e(m["abiotic"])}</dd></dl></article>')


CONTRAST = [  # (label, contrast, conditions, status, source key)
    ("Ground AO (GPI), raw", 1e-4, "5σ at 0.4″, H band, 60 s", "achieved", "bailey"),
    ("JWST NIRCam coronagraph", 1e-5, "5σ at 1″, 4.4 µm (HIP 65426)", "achieved", "carter23"),
    ("JWST MIRI coronagraph", 2e-4, "at 1″, 11.3 µm (HIP 65426)", "achieved", "carter23"),
    ("Roman Coronagraph", 1e-7, "requirement at 6–9 λ/D; goal 10⁻⁹", "requirement", "roman"),
    ("HWO", 1e-10, "Earth twins around Sun-like stars", "goal", "lawson"),
    ("Earth twin, reflected light", 1.2e-10, "Sun-like star, visible light", "target", "lawson"),
]


def contrast_ladder() -> str:
    """A ladder of rungs, one row each, sorted from bright to faint; each row's dot sits at its true place on a
    shared log axis from 10⁻² to 10⁻¹¹, so labels never collide however close two contrasts are."""
    e = html.escape
    pos = lambda c: (-math.log10(c) - 2) / 9 * 100  # noqa: E731
    rows = []
    for label, c, cond, status, k in sorted(CONTRAST, key=lambda r: -r[1]):
        rows.append(f'<li class="{status}"><div class="lab"><b>{e(label)}</b> <span class="mono">{c:.0e}</span>'
                    f'<span class="cond">{e(cond)} · {e(status)} · <a href="{e(SOURCES[k][1])}" rel="noopener">{e(SOURCES[k][0].split(" (")[0])}</a></span></div>'
                    f'<div class="track" aria-hidden="true"><i style="left:{pos(c):.1f}%"></i></div></li>')
    ticks = "".join(f'<span style="left:{(p - 2) / 9 * 100:.1f}%">10⁻{p}</span>' for p in range(2, 12))
    return (f'<div class="mxcontrast" role="img" aria-label="Contrast ladder on a log scale from 1e-2 to 1e-11: '
            + "; ".join(f"{lab} {c:.0e} ({st})" for lab, c, _, st, _ in CONTRAST)
            + f'"><div class="ax" aria-hidden="true"><div class="lab"></div><div class="track">{ticks}</div></div><ol>{"".join(rows)}</ol></div>')


METHODS_JS = r"""
// ---------- methods: physics twins of methods.py (the tests compare them) ----------
const MX = D.methods || null;
const MX_GM = {sun: 1.3271244e20, jup: 1.2668653e17, earth: 3.986004e14}, MX_R = {sun: 6.957e8, jup: 7.1492e7, earth: 6.3781e6};
const MX_AU = 1.495978707e11, MX_DAY = 86400, MX_C = 299792458;
function mxK(P, mp, ms, e, sini){ const gmp = mp * MX_GM.jup, gms = ms * MX_GM.sun; return Math.cbrt(2 * Math.PI / (P * MX_DAY)) * gmp * (sini == null ? 1 : sini) / Math.pow(gms + gmp, 2 / 3) / Math.sqrt(1 - (e || 0) ** 2); }
function mxBary(a, mp, ms){ const q = mp * MX_GM.jup / (ms * MX_GM.sun + mp * MX_GM.jup); return [a * q, a * (1 - q)]; }
function mxKeplerE(M, e){
  M = M % (2 * Math.PI); let E = e < 0.8 ? M : Math.PI;
  for (let i = 0; i < 60; i++){ const d = (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E)); E -= d; if (Math.abs(d) < 1e-12) break; }
  return E;
}
function mxNu(M, e){ const E = mxKeplerE(M, e); return 2 * Math.atan2(Math.sqrt(1 + e) * Math.sin(E / 2), Math.sqrt(1 - e) * Math.cos(E / 2)); }
// Star, barycentre (origin) and planet in the orbital plane at phase t (0 = periastron), orbit rotated by w.
function mxBodies(t, e, q, w){
  const nu = mxNu(2 * Math.PI * t, e), r = (1 - e * e) / (1 + e * Math.cos(nu)), th = nu + (w || 0);
  const px = r * (1 - q) * Math.cos(th), py = r * (1 - q) * Math.sin(th);
  return {planet: [px, py], star: [-r * q * Math.cos(th), -r * q * Math.sin(th)], bary: [0, 0], nu};
}
const mxPacz = u => (u * u + 2) / (u * Math.sqrt(u * u + 4));
function mxLd(teff){
  const T = MX.claret;
  if (teff <= T[0][0]) return [T[0][1], T[0][2]];
  if (teff >= T[T.length - 1][0]) return [T[T.length - 1][1], T[T.length - 1][2]];
  for (let i = 0; i < T.length - 1; i++) if (teff >= T[i][0] && teff <= T[i + 1][0]){ const f = (teff - T[i][0]) / (T[i + 1][0] - T[i][0]); return [T[i][1] + f * (T[i + 1][1] - T[i][1]), T[i][2] + f * (T[i + 1][2] - T[i][2])]; }
}
function mxI(r, u1, u2){ const mu = Math.sqrt(Math.max(0, 1 - r * r)); return 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2; }
function mxOverlap(z, k){
  if (z >= 1 + k) return 0;
  if (z <= 1 - k) return Math.PI * k * k;
  if (z <= k - 1) return Math.PI;
  const c = x => Math.max(-1, Math.min(1, x));
  const k0 = Math.acos(c((k * k + z * z - 1) / (2 * k * z))), k1 = Math.acos(c((1 - k * k + z * z) / (2 * z)));
  return k * k * k0 + k1 - 0.5 * Math.sqrt(Math.max(0, 4 * z * z - (1 + z * z - k * k) ** 2));
}
function mxFlux(z, k, u1, u2){
  const A = mxOverlap(z, k); if (A <= 0) return 1;
  const r = z <= 1 - k ? Math.min(z, 1) : Math.min(1, (z - k + 1) / 2);
  return 1 - A * mxI(r, u1, u2) / (Math.PI * (1 - u1 / 3 - u2 / 6));
}
function mxG(x, mu, s1, s2){ const t = (x - mu) / (x < mu ? s1 : s2); return Math.exp(-0.5 * t * t); }
function mxTeffRGB(T){
  let X = 0, Y = 0, Z = 0;
  for (let lam = 380; lam <= 780; lam += 5){
    const l = lam * 1e-9, b = 1 / (l ** 5 * (Math.exp(1.4387769e-2 / (l * T)) - 1));
    X += b * (1.056 * mxG(lam, 599.8, 37.9, 31.0) + 0.362 * mxG(lam, 442.0, 16.0, 26.7) - 0.065 * mxG(lam, 501.1, 20.4, 26.2));
    Y += b * (0.821 * mxG(lam, 568.8, 46.9, 40.5) + 0.286 * mxG(lam, 530.9, 16.3, 31.1));
    Z += b * (1.217 * mxG(lam, 437.0, 11.8, 36.0) + 0.681 * mxG(lam, 459.0, 26.0, 13.8));
  }
  const r = 3.2406 * X - 1.5372 * Y - 0.4986 * Z, g = -0.9689 * X + 1.8758 * Y + 0.0415 * Z, bl = 0.0557 * X - 0.2040 * Y + 1.0570 * Z, m = Math.max(r, g, bl);
  return [r, g, bl].map(c => { c = Math.max(0, c / m); c = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055; return Math.round(255 * Math.min(1, c)); });
}
function mxClass(T){ let best = MX.mamajek[0]; for (const r of MX.mamajek) if (Math.abs(r[1] - T) < Math.abs(best[1] - T)) best = r; return [best[0][0], best[0]]; }
// The star's motion on screen: if its true orbit would be under a few pixels, it is multiplied by a
// stated power of ten. Returns the factor and the label that must accompany it.
function mxWobbleScale(q, Rpx, aAU, rstar){
  const px = Rpx * q; let N = 1;
  if (!(px > 0)) return {N: 1, label: ''};
  while (px * N < 14 && N < 1e12) N *= 10;
  const km = aAU * MX_AU * q / 1000, inR = rstar ? km * 1000 / (rstar * MX_R.sun) : null;
  const label = N > 1 ? `star's motion exaggerated ×${N.toLocaleString('en-GB')}; true a★ = ${km < 10 ? km.toFixed(2) : Math.round(km).toLocaleString('en-GB')} km${inR != null ? ` ≈ ${inR < 0.01 ? inR.toExponential(1) : inR.toFixed(2)} R★` : ''}` : '';
  return {N, label};
}

// ---------- stages: a canvas with play, speed and a time scrubber; still under reduced motion ----------
const mxRM = window.matchMedia('(prefers-reduced-motion: reduce)');
const MXV = {};
const mxStages = [];
function mxRgb(c, a){ return `rgba(${c[0]},${c[1]},${c[2]},${a == null ? 1 : a})`; }
function mxRand(seed){ let s = seed >>> 0 || 1; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }
function mxSetup(fig, extra){
  if (fig._mx) return fig._mx;
  const vis = MXV[fig.dataset.vis]; if (!vis) return null;
  const cv = fig.querySelector('canvas'), st = {fig, cv, ctx: cv.getContext('2d'), vis, t: vis.key || 0, playing: false, speed: 1, on: false, visible: false, last: 0, raf: 0, opt: Object.assign({}, extra || {}), exag: ''};
  fig._mx = st; mxStages.push(st);
  if (vis.init) vis.init(st);
  const play = fig.querySelector('.mxplay'), scrub = fig.querySelector('.mxscrub'), speed = fig.querySelector('.mxspeed select');
  st.still = !play;   // a static view (a chart or a lab): no clock, redrawn when a control changes
  if (play) play.addEventListener('click', () => { mxPlay(st, !st.playing); });
  if (speed) speed.addEventListener('change', () => { st.speed = Number(speed.value); });
  if (scrub) scrub.addEventListener('input', () => { st.t = Number(scrub.value) / 1000; mxDraw(st); });
  fig.querySelectorAll('.mxctl select:not(.mxspeed select), .mxctl input[type=range]:not(.mxscrub), .mxctl .mxsize, .mxctl .mxtog').forEach(c => {
    const ev = c.tagName === 'BUTTON' ? 'click' : (c.type === 'range' ? 'input' : 'change');
    c.addEventListener(ev, () => { if (c.tagName === 'BUTTON') c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true')); if (vis.control) vis.control(st, c); mxDraw(st); });
  });
  if ('IntersectionObserver' in window) new IntersectionObserver(es => { st.visible = es[0].isIntersecting; mxKick(st); }).observe(cv);
  else st.visible = true;
  if (window.ResizeObserver) new ResizeObserver(() => mxDraw(st)).observe(fig.querySelector('.mxcanvas'));
  return st;
}
function mxPlay(st, on){
  if (st.still) return;
  st.playing = on;
  const b = st.fig.querySelector('.mxplay'); b.textContent = on ? 'Pause' : 'Play'; b.setAttribute('aria-pressed', String(on));
  mxKick(st);
}
function mxKick(st){ if (st.playing && st.on && st.visible && !document.hidden && !st.raf){ st.last = 0; st.raf = requestAnimationFrame(ts => mxFrame(st, ts)); } }
function mxFrame(st, ts){
  st.raf = 0;
  if (!st.playing || !st.on || !st.visible || document.hidden) return;
  const dt = st.last ? Math.min(100, ts - st.last) : 16; st.last = ts;
  st.t = (st.t + dt / 1000 * st.speed / (st.vis.period || 10)) % 1;
  mxDraw(st);
  st.raf = requestAnimationFrame(t2 => mxFrame(st, t2));
}
function mxDraw(st){
  const box = st.cv.parentNode.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
  if (box.width < 2 || box.height < 2) return;   // hidden: nothing to draw
  const w = Math.round(box.width), h = Math.round(box.height);
  if (st.cv.width !== Math.round(w * dpr) || st.cv.height !== Math.round(h * dpr)){ st.cv.width = Math.round(w * dpr); st.cv.height = Math.round(h * dpr); }
  const c = st.ctx; c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
  c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
  st.exag = '';
  st.vis.draw(c, w, h, st.t, st);
  const ex = st.fig.querySelector('.mxexag'); if (ex.textContent !== st.exag) ex.textContent = st.exag;
  ex.hidden = !st.exag;
  const sc = st.fig.querySelector('.mxscrub'); if (sc && document.activeElement !== sc) sc.value = Math.round(st.t * 1000);
}
// Shown or hidden with its chapter: only the open chapter's stages run. Under reduced motion nothing
// plays by itself; each stage shows its key frame and plays only when asked.
function mxActivate(article, on){
  article.querySelectorAll('.mxstage').forEach(fig => {
    if (!on && !fig._mx) return;   // stages are set up the first time their chapter opens
    const st = mxSetup(fig); if (!st) return;
    st.on = on;
    if (on){ mxDraw(st); if (!mxRM.matches && !st.started){ st.started = true; mxPlay(st, true); } else mxKick(st); }
  });
}
document.addEventListener('visibilitychange', () => mxStages.forEach(mxKick));

// ---------- shared drawing pieces ----------
function mxText(c, s, x, y, o){ o = o || {}; c.font = `${o.w || 500} ${o.size || 11}px ${o.mono ? '"Geist Mono",ui-monospace,monospace' : '"Geist",system-ui,sans-serif'}`; c.fillStyle = o.color || '#A1A1A6'; c.textAlign = o.align || 'left'; c.textBaseline = o.base || 'alphabetic'; c.fillText(s, x, y); }
function mxStar(c, x, y, R, teff, t, opt){
  opt = opt || {};
  const rgb = mxTeffRGB(teff), [u1, u2] = mxLd(teff);
  // Corona glow.
  const g0 = c.createRadialGradient(x, y, R * 0.9, x, y, R * (opt.glow || 2.1));
  g0.addColorStop(0, mxRgb(rgb, 0.32)); g0.addColorStop(1, mxRgb(rgb, 0));
  c.fillStyle = g0; c.beginPath(); c.arc(x, y, R * (opt.glow || 2.1), 0, 2 * Math.PI); c.fill();
  // Limb darkening from the quadratic law at this Teff (Claret 2017).
  const g = c.createRadialGradient(x, y, 0, x, y, R);
  for (let i = 0; i <= 10; i++){ const r = i / 10, I = mxI(Math.min(r, 0.999), u1, u2); g.addColorStop(r, mxRgb(rgb.map(v => v * I))); }
  c.fillStyle = g; c.beginPath(); c.arc(x, y, R, 0, 2 * Math.PI); c.fill();
  // Granulation: cells that drift and flicker (texture only; not to scale).
  if (R > 14 && !opt.flat){
    c.save(); c.beginPath(); c.arc(x, y, R, 0, 2 * Math.PI); c.clip();
    const rnd = mxRand(11), n = Math.min(260, Math.round(R * R / 18));
    for (let i = 0; i < n; i++){
      const a = rnd() * 2 * Math.PI + t * 0.6, rr = Math.sqrt(rnd()) * R, s = R * (0.035 + rnd() * 0.04);
      const cx = x + rr * Math.cos(a), cy = y + rr * Math.sin(a), f = 0.5 + 0.5 * Math.sin(t * 40 + i);
      c.fillStyle = `rgba(255,255,255,${0.035 + 0.05 * f})`; c.beginPath(); c.arc(cx, cy, s, 0, 2 * Math.PI); c.fill();
      c.fillStyle = `rgba(0,0,0,${0.05 * (1 - f)})`; c.beginPath(); c.arc(cx + s * 0.9, cy + s * 0.4, s * 0.5, 0, 2 * Math.PI); c.fill();
    }
    c.restore();
  }
  return rgb;
}
function mxPlanet(c, x, y, r, cls, lit){
  // Look by class: 0 Earth-size, 1 super-Earth (rocky); 2 sub-Neptune, 3 Neptune-like (haze); 4 gas giant (bands).
  c.save(); c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.clip();
  const base = cls >= 4 ? [196, 160, 120] : cls >= 2 ? [120, 170, 214] : [150, 128, 110];
  c.fillStyle = mxRgb(base); c.fillRect(x - r, y - r, 2 * r, 2 * r);
  if (cls >= 4) for (let i = -3; i <= 3; i++){ c.fillStyle = i % 2 ? 'rgba(90,60,40,.35)' : 'rgba(255,240,220,.18)'; c.fillRect(x - r, y + i * r / 3.5, 2 * r, r / 5); }
  else if (cls >= 2){ const h = c.createRadialGradient(x, y, r * 0.2, x, y, r); h.addColorStop(0, 'rgba(255,255,255,.15)'); h.addColorStop(1, 'rgba(180,220,255,.5)'); c.fillStyle = h; c.fillRect(x - r, y - r, 2 * r, 2 * r); }
  else { c.fillStyle = 'rgba(60,45,35,.35)'; c.beginPath(); c.arc(x - r * 0.3, y + r * 0.2, r * 0.4, 0, 2 * Math.PI); c.fill(); }
  // Shading: lit from the star's side, dark when silhouetted against it.
  const s = c.createLinearGradient(x - r, y, x + r, y);
  s.addColorStop(0, `rgba(0,0,0,${lit ? 0.1 : 0.85})`); s.addColorStop(1, `rgba(0,0,0,${lit ? 0.75 : 0.92})`);
  c.fillStyle = s; c.fillRect(x - r, y - r, 2 * r, 2 * r);
  c.restore();
  if (cls >= 2){ c.strokeStyle = 'rgba(150,200,255,.35)'; c.lineWidth = 1; c.beginPath(); c.arc(x, y, r + 0.5, 0, 2 * Math.PI); c.stroke(); }
}
function mxAxes(c, x, y, w, h, o){
  c.strokeStyle = 'rgba(255,255,255,.14)'; c.lineWidth = 1; c.strokeRect(x + .5, y + .5, w, h);
  mxText(c, o.y, x, y - 6, {size: 11, w: 600, color: '#C7C7CC', mono: true});
  mxText(c, o.x, x + w - 6, y + h - 6, {size: 11, w: 600, color: '#8E8E93', mono: true, align: 'right'});
}
function mxGlassPanel(c, x, y, w, h){ c.fillStyle = 'rgba(28,28,30,.72)'; c.strokeStyle = 'rgba(255,255,255,.12)'; c.lineWidth = 1; c.beginPath(); c.roundRect ? c.roundRect(x, y, w, h, 14) : c.rect(x, y, w, h); c.fill(); c.stroke(); }
const mxClassOf = (rp, mp) => { if (rp){ const re = rp * 11.209; return re < 1.25 ? 0 : re < 2 ? 1 : re < 4 ? 2 : re < 10 ? 3 : 4; } if (mp){ const me = mp * 317.83; return me < 2 ? 0 : me < 10 ? 1 : me < 50 ? 3 : 4; } return null; };

// ---------- the animated system: star (Teff colour, limb darkening, granulation), orbit, planet, light curve ----------
function mxSystemParams(p, dip){
  const teff = p.star_teff || 5772, rs = p.star_radius, rp = p.radius, a = p.semi_major_axis, P = p.orbital_period;
  const scale = !!(rs && rp), k = scale ? rp * MX_R.jup / (rs * MX_R.sun) : 0.1;
  const ars = (a && rs) ? a * MX_AU / (rs * MX_R.sun) : 12;
  let b = p.impact_parameter, bSrc = 'stored';
  if (b == null && p.inclination != null && a && rs){ b = ars * Math.cos(p.inclination * Math.PI / 180); bSrc = 'from a/R★ and i'; }
  if (b == null || b > 1 + k){ b = 0.3; bSrc = 'illustrative'; }
  return {teff, rs, rp, a, P, k, ars, b, bSrc, scale, cls: mxClassOf(rp, p.mass || p.mass_sini), name: p.name || '', dip: dip || null, inc: p.inclination};
}
function mxDurations(P, ars, k, b){
  const inc = Math.acos(Math.min(1, b / ars)), si = Math.sin(inc), f = x => P / Math.PI * Math.asin(Math.min(1, x / (ars * si)));
  return [f(Math.sqrt(Math.max(0, (1 + k) ** 2 - b * b))), (1 - k) ** 2 - b * b > 0 ? f(Math.sqrt((1 - k) ** 2 - b * b)) : null];
}
function mxDrawSystem(c, w, h, t, st){
  const S = st.opt.sys; if (!S) return;
  const P = S.P || 10, [u1, u2] = mxLd(S.teff), [t14] = mxDurations(P, S.ars, S.k, S.b);
  const win = Math.min(0.24, 0.9 * t14 / P);   // half-window of the chart, as a fraction of the orbit
  // Time runs slowly through the transit window and faster for the rest of the orbit (stated on screen).
  const phi = t < 0.5 ? -win + t / 0.5 * 2 * win : win + (t - 0.5) / 0.5 * (1 - 2 * win);
  const sceneH = h * 0.56, cx = w / 2, cy = sceneH * 0.52, Rs = Math.min(sceneH * 0.26, w * 0.13);
  const A = Math.min(w * 0.42, Rs * 5.2), By = S.b * Rs;     // orbit not to scale; crossing at the stored b
  const ang = 2 * Math.PI * phi, px = cx + A * Math.sin(ang), py = cy + By * Math.cos(ang), front = Math.cos(ang) > 0;
  const big = !!st.opt.big, rpx = Math.max(1.5, S.k * Rs * (big ? 5 : 1));
  c.setLineDash([4, 6]); c.strokeStyle = 'rgba(255,255,255,.28)'; c.lineWidth = 1;
  c.beginPath(); c.ellipse(cx, cy, A, Math.max(0.5, By), 0, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
  const cls = S.cls == null ? 2 : S.cls;
  if (!front) mxPlanet(c, px, py, rpx, cls, true);
  mxStar(c, cx, cy, Rs, S.teff, t);
  if (front){ const over = Math.hypot(px - cx, py - cy) < Rs + rpx; mxPlanet(c, px, py, rpx, cls, !over); }
  const [cl, row] = mxClass(S.teff);
  mxText(c, `${cl} · ≈${row} · ${Math.round(S.teff).toLocaleString('en-GB')} K`, 14, 22, {size: 12, w: 600, color: '#F5F5F7'});
  mxText(c, S.scale ? `star and planet sizes to scale${big ? '; planet ×5' : ''}` : 'sizes not to scale (radius not stored)', 14, 40, {size: 11});
  if (w < 600){
    mxText(c, `orbit not to scale (a = ${S.ars.toFixed(1)} R★)`, 14, 56, {size: 11});
    mxText(c, `crosses at b = ${S.b.toFixed(2)} (${S.bSrc})`, 14, 72, {size: 11});
    if (t >= 0.5) mxText(c, 'outside the transit: time runs faster', w - 14, sceneH - 6, {size: 11, align: 'right'});
  } else {
    mxText(c, `orbit not to scale (a = ${S.ars.toFixed(1)} R★); crosses at b = ${S.b.toFixed(2)} (${S.bSrc})`, 14, 56, {size: 11});
    if (t >= 0.5) mxText(c, 'outside the transit: time runs faster', w - 14, 22, {size: 11, align: 'right'});
  }
  if (big) st.exag = 'planet drawn ×5; depth and times true';
  // Light curve: model from stored values, limb-darkened (small-planet Mandel & Agol 2002).
  const gx0 = 54, gy0 = sceneH + 26, gw = w - gx0 - 18, gh = h - gy0 - 40;
  mxGlassPanel(c, 10, sceneH + 6, w - 20, h - sceneH - 12);
  const zOf = f => S.ars * Math.sqrt(Math.sin(2 * Math.PI * f) ** 2 + (S.b / S.ars) ** 2 * Math.cos(2 * Math.PI * f) ** 2);
  const depth = 1 - mxFlux(S.b / 1, S.k, u1, u2), floor = Math.min(1 - 1.35 * Math.max(depth, 1e-5), ...(S.dip && S.dip.pts ? S.dip.pts.map(p => 1 + p[1] * 1e-6 - 0.00002) : [1]), ...(S.dip && S.dip.box ? S.dip.box.map(p => 1 + p[1] * 1e-6 - 0.00002) : [1]));
  const X = f => gx0 + (f + win) / (2 * win) * gw, Y = v => gy0 + (1 - v) / (1 - floor) * gh * 0.86 + 6;
  mxAxes(c, gx0, gy0, gw, gh, {y: 'BRIGHTNESS (%)', x: 'TIME FROM MID-TRANSIT (h)'});
  for (const v of [1, 1 - depth]){ c.strokeStyle = 'rgba(255,255,255,.08)'; c.beginPath(); c.moveTo(gx0, Y(v)); c.lineTo(gx0 + gw, Y(v)); c.stroke(); mxText(c, (v * 100).toFixed(depth < 0.001 ? 3 : 2), gx0 - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
  for (const hh of [-1, 0, 1]){ const f = hh * win * 0.8, xx = X(f); mxText(c, (f * P * 24).toFixed(1), xx, gy0 + gh + 13, {size: 11, mono: true, align: 'center'}); }
  if (S.dip && S.dip.box && S.dip.box.length){
    c.save(); c.beginPath(); c.rect(gx0, gy0, gw, gh); c.clip();
    c.setLineDash([5, 4]); c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 1.2; c.beginPath();
    S.dip.box.forEach((p, i) => { const x = X(p[0] / P), y = Y(1 + p[1] * 1e-6); i ? c.lineTo(x, y) : c.moveTo(x, y); }); c.stroke(); c.setLineDash([]);
    c.restore();
  }
  if (S.dip && S.dip.pts){
    c.fillStyle = 'rgba(100,210,255,.55)';
    c.save(); c.beginPath(); c.rect(gx0, gy0, gw, gh); c.clip();
    for (const p of S.dip.pts){ const f = p[0] / P; if (Math.abs(f) > win) continue; c.fillRect(X(f) - 1.2, Y(1 + p[1] * 1e-6) - 1.2, 2.4, 2.4); }
    c.restore();
  }
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.8; c.beginPath();
  const upto = t < 0.5 ? phi : win;
  for (let i = 0; i <= 240; i++){ const f = -win + 2 * win * i / 240; if (f > upto) break; const v = mxFlux(zOf(f), S.k, u1, u2); i ? c.lineTo(X(f), Y(v)) : c.moveTo(X(f), Y(v)); }
  c.stroke();
  if (t < 0.5){ const v = mxFlux(zOf(phi), S.k, u1, u2); c.fillStyle = '#FFB340'; c.beginPath(); c.arc(X(phi), Y(v), 3.5, 0, 2 * Math.PI); c.fill(); }
  const cap = S.dip ? 'line: model from stored values · dots: exoplan’s stored points' + (S.dip.box ? ' · dashed: stored box' : '') : 'line: model from stored values, not observed data';
  if (w < 600) mxText(c, cap, gx0 + 6, gy0 + 14, {size: 11}); else mxText(c, cap, gx0 + gw, gy0 - 6, {size: 11, align: 'right'});
}
MXV.system = {key: 0.25, period: 12, init(st){
  const ex = MX.examples['pi Men c'] || {};
  st.opt.sys = mxSystemParams(Object.assign({name: 'pi Men c'}, ex), MX.lead_dip ? {pts: MX.lead_dip.pts} : null);
  st.opt.b0 = st.opt.sys.b;
}, control(st, el){
  if (el.classList.contains('mxsize')) st.opt.big = el.getAttribute('aria-pressed') === 'true';
  if (el.type === 'range'){ st.opt.sys.b = Number(el.value) / 1000 * (1 + st.opt.sys.k); st.opt.sys.bSrc = 'slider'; }
}, draw: mxDrawSystem};

// ---------- a survey scan ----------
MXV.scan = {key: 0.62, period: 16, init(st){
  const rnd = mxRand(5), teffs = [3200, 3500, 3900, 4400, 5000, 5600, 5900, 6400, 7200, 9000, 15000];
  st.opt.stars = Array.from({length: 320}, () => ({x: rnd(), y: rnd(), m: rnd(), teff: teffs[Math.floor(Math.pow(rnd(), 1.6) * teffs.length)]}));
  st.opt.cols = {}; for (const T of teffs) st.opt.cols[T] = mxTeffRGB(T);
  st.opt.locks = Array.from({length: 26}, (_, i) => Math.floor(rnd() * 320));
  // About R★/a of random orbits transit: for a pi Men c-like orbit, 7.5% (see the table).
  st.opt.aligned = st.opt.locks.map((s, i) => ((i * 0.075 + 0.04) % 1) < 0.075);
}, draw(c, w, h, t, st){
  const S = st.opt;
  for (const s of S.stars){ const r = 0.6 + 1.8 * s.m ** 3; c.fillStyle = mxRgb(S.cols[s.teff], 0.55 + 0.45 * s.m); c.beginPath(); c.arc(s.x * w, s.y * h, r, 0, 2 * Math.PI); c.fill(); }
  c.strokeStyle = 'rgba(100,210,255,.12)'; c.lineWidth = 1;
  for (let i = 1; i < 4; i++){ c.beginPath(); c.moveTo(i * w / 4, 0); c.lineTo(i * w / 4, h); c.stroke(); c.beginPath(); c.moveTo(0, i * h / 4); c.lineTo(w, i * h / 4); c.stroke(); }
  const n = S.locks.length, cur = Math.floor(t * n), frac = t * n - cur;
  let seen = 0, hits = 0;
  for (let i = 0; i <= cur && i < n; i++){
    const s = S.stars[S.locks[i]], x = s.x * w, y = s.y * h, done = i < cur;
    if (done){ seen++; if (S.aligned[i]) hits++; }
    const r = done ? 9 : 9 + 34 * (1 - Math.min(1, frac / 0.5));
    c.strokeStyle = done ? (S.aligned[i] ? '#64D2FF' : 'rgba(255,255,255,.28)') : '#F5F5F7'; c.lineWidth = done ? 1 : 1.5;
    c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.stroke();
    if (!done){ for (let k = 0; k < 4; k++){ const a = k * Math.PI / 2; c.beginPath(); c.moveTo(x + Math.cos(a) * (r + 3), y + Math.sin(a) * (r + 3)); c.lineTo(x + Math.cos(a) * (r + 10), y + Math.sin(a) * (r + 10)); c.stroke(); } }
    if (done && S.aligned[i]) mxText(c, 'orbit aligned: transits', x > w - 160 ? x - 12 : x + 12, y + 4, {size: 11, color: '#64D2FF', align: x > w - 160 ? 'right' : 'left'});
  }
  mxGlassPanel(c, 10, h - 52, 290, 42);
  mxText(c, `targets checked ${String(seen).padStart(2, '0')} · aligned ${hits}`, 22, h - 34, {size: 12, mono: true, color: '#F5F5F7'});
  mxText(c, 'expected ≈ R★/a = 7.5% for a pi Men c-like orbit', 22, h - 18, {size: 11});
  mxText(c, 'star positions illustrative; colours from temperature', w - 12, 18, {size: 11, align: 'right'});
}};

// ---------- toward and away: Doppler shift ----------
const MX_LINES = [[486.1, 'Hβ'], [517.3, 'Mg'], [589.0, 'Na'], [656.3, 'Hα'], [527.0, 'Fe']];
function mxSpectrum(c, x, y, w, h, shiftNm, label){
  const g = c.createLinearGradient(x, 0, x + w, 0), stops = [[400, '#7A3CFF'], [450, '#2E6BFF'], [490, '#22C1E6'], [530, '#3EDB62'], [575, '#F2E43A'], [610, '#FF9F2E'], [700, '#E0302F']];
  for (const [l, col] of stops) g.addColorStop((l - 400) / 300, col);
  c.fillStyle = g; c.fillRect(x, y, w, h);
  for (const [l, n] of MX_LINES){
    const x0 = x + (l - 400) / 300 * w, x1 = x + (l + shiftNm - 400) / 300 * w;
    c.strokeStyle = 'rgba(255,255,255,.7)'; c.setLineDash([2, 2]); c.beginPath(); c.moveTo(x0, y - 5); c.lineTo(x0, y); c.stroke(); c.setLineDash([]);
    c.fillStyle = '#000'; c.fillRect(x1 - 1.5, y, 3, h);
    mxText(c, n, x0, y - 8, {size: 11, align: 'center'});
  }
  mxText(c, '400 nm', x, y + h + 13, {size: 11, mono: true}); mxText(c, '700 nm', x + w, y + h + 13, {size: 11, mono: true, align: 'right'});
  if (label) mxText(c, label, x + w / 2, y + h + 13, {size: 11, align: 'center', color: '#C7C7CC'});
}
function mxEye(c, x, y){ c.strokeStyle = '#F5F5F7'; c.lineWidth = 1.5; c.beginPath(); c.ellipse(x, y, 14, 7, 0, 0, 2 * Math.PI); c.stroke(); c.fillStyle = '#F5F5F7'; c.beginPath(); c.arc(x, y, 3.5, 0, 2 * Math.PI); c.fill(); mxText(c, 'observer', x + 22, y + 4, {size: 11}); }
MXV.doppler = {key: 0.25, period: 8, init(st){ st.opt.mode = 'los'; st.opt.K = (MX.examples['51 Peg b'] || {}).k || 55.77; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const los = st.opt.mode === 'los', K = st.opt.K, v = K * Math.sin(2 * Math.PI * t);   // + = away
    const cx = w / 2, top = 40, bot = h - 120, ex = cx, ey = h - 92;
    mxEye(c, ex, ey);
    c.strokeStyle = 'rgba(255,255,255,.15)'; c.setLineDash([3, 5]); c.beginPath(); c.moveTo(cx, top); c.lineTo(cx, ey - 12); c.stroke(); c.setLineDash([]);
    mxText(c, 'line of sight', cx + 8, top + 8, {size: 11});
    let sx = cx, sy = (top + bot) / 2;
    if (los) sy = (top + bot) / 2 - Math.cos(2 * Math.PI * t) * (bot - top) * 0.32; else sx = cx + Math.cos(2 * Math.PI * t) * w * 0.3;
    mxStar(c, sx, sy, 18, 5758, t, {flat: true, glow: 1.8});
    const vel = los ? v : 0;
    const col = vel > 0.5 ? '#FF6961' : vel < -0.5 ? '#0A84FF' : '#A1A1A6';
    if (los){ c.strokeStyle = col; c.lineWidth = 2; const L = 26 * Math.sign(-vel) * Math.min(1, Math.abs(vel) / K); c.beginPath(); c.moveTo(sx + 30, sy); c.lineTo(sx + 30, sy + L); c.stroke(); }
    mxText(c, los ? (vel < -0.5 ? 'approaching: blueshift' : vel > 0.5 ? 'receding: redshift' : 'turning') : 'moving across: no Doppler shift', sx + 40, sy + 4, {size: 12, w: 600, color: los ? col : '#C7C7CC'});
    // The shift, exaggerated: true Δλ/λ = v/c.
    const F = 1e5, shift = vel / MX_C * 589 * F;
    mxSpectrum(c, 24, h - 52, w - 48, 22, shift, '');
    mxText(c, `v_r = ${vel >= 0 ? '+' : '−'}${Math.abs(vel).toFixed(1)} m/s   Δλ/λ = ${(vel / MX_C).toExponential(2)}`, 24, h - 66, {size: 12, mono: true, color: '#F5F5F7'});
    st.exag = `line shift ×${F.toLocaleString('en-GB')} (true Δλ/λ ≤ ${(K / MX_C).toExponential(1)}); star colour unchanged`;
    mxText(c, 'K = 51 Peg b’s stored value; motion path illustrative', w - 14, 20, {size: 11, align: 'right'});
  }};

// ---------- the wobble: barycentre, Kepler's equation, the RV curve ----------
const MX_SYS = {
  'jupiter': {name: 'Jupiter–Sun', P: 11.862 * 365.25, mp: 1, ms: 1, e: 0.049, w: 0, a: 5.204, rs: 1, kind: 'mass', inset: true},
  'earth': {name: 'Earth–Sun', P: 365.25, mp: 3.986004e14 / 1.2668653e17, ms: 1, e: 0.0167, w: 0, a: 1, rs: 1, kind: 'mass', inset: true}};
function mxRvSystem(id){
  if (MX_SYS[id]) return MX_SYS[id];
  const p = MX.examples[id] || {};
  const mp = p.mass_sini != null ? p.mass_sini : p.mass, kind = p.mass_sini != null ? 'msini' : 'mass';
  const sini = kind === 'mass' && p.inclination != null ? Math.sin(p.inclination * Math.PI / 180) : 1;
  const a = p.semi_major_axis || Math.cbrt(MX_GM.sun * (p.star_mass || 1) * ((p.orbital_period || 1) * MX_DAY / (2 * Math.PI)) ** 2) / MX_AU;
  return {name: id, P: p.orbital_period, mp, ms: p.star_mass, e: p.eccentricity || 0, w: (p.omega || 0) * Math.PI / 180, a, rs: p.star_radius, kind, sini, Kstored: p.k, teff: p.star_teff};
}
MXV.wobble = {key: 0.3, period: 10, init(st){ st.opt.sys = mxRvSystem('51 Peg b'); mxPrepRv(st); },
  control(st, el){ if (el.tagName === 'SELECT'){ st.opt.sys = mxRvSystem(el.value); mxPrepRv(st); } },
  draw(c, w, h, t, st){
    const S = st.opt.sys, q = st.opt.q, K = st.opt.K;
    // Side by side when there is room; stacked (orbit, then the curve, then the lines) on a narrow screen.
    const narrow = w < 600, side = narrow ? Math.min(w - 20, h * 0.46) : Math.min(w * 0.5, h - 40);
    const ox = narrow ? w / 2 : side / 2 + 14, oy = narrow ? side / 2 + 16 : h / 2 - 6, R = side * 0.36;
    const sc = mxWobbleScale(q, R, S.a, S.rs); st.exag = sc.label;
    const B = mxBodies(t, S.e, q, S.w), pl = [ox + B.planet[0] * R, oy - B.planet[1] * R], sr = [ox + B.star[0] * R * sc.N, oy - B.star[1] * R * sc.N];
    // Orbits: the planet's ellipse and the star's (scaled by N), around the barycentre.
    c.setLineDash([3, 5]); c.strokeStyle = 'rgba(255,255,255,.25)';
    c.beginPath(); for (let i = 0; i <= 120; i++){ const b = mxBodies(i / 120, S.e, q, S.w); const x = ox + b.planet[0] * R, y = oy - b.planet[1] * R; i ? c.lineTo(x, y) : c.moveTo(x, y); } c.stroke();
    c.beginPath(); for (let i = 0; i <= 120; i++){ const b = mxBodies(i / 120, S.e, q, S.w); const x = ox + b.star[0] * R * sc.N, y = oy - b.star[1] * R * sc.N; i ? c.lineTo(x, y) : c.moveTo(x, y); } c.stroke();
    c.setLineDash([]);
    // The line through star, barycentre and planet stays straight.
    c.strokeStyle = 'rgba(255,255,255,.3)'; c.beginPath(); c.moveTo(sr[0], sr[1]); c.lineTo(pl[0], pl[1]); c.stroke();
    mxStar(c, sr[0], sr[1], 11, S.teff || 5772, t, {flat: true, glow: 1.7});
    mxPlanet(c, pl[0], pl[1], 4.5, mxClassOf(null, S.mp) == null ? 4 : mxClassOf(null, S.mp), true);
    c.strokeStyle = '#F5F5F7'; c.lineWidth = 1.2; c.beginPath(); c.moveTo(ox - 5, oy); c.lineTo(ox + 5, oy); c.moveTo(ox, oy - 5); c.lineTo(ox, oy + 5); c.stroke();
    mxText(c, 'barycentre', ox + 8, oy - 8, {size: 11, color: '#F5F5F7'});
    mxEye(c, ox - 20, oy + side / 2 - (narrow ? 10 : -4));
    // Velocity of the star: radial part (toward the observer, down the page) and the dimmed tangential part.
    const dt = 1e-3, B2 = mxBodies((t + dt) % 1, S.e, q, S.w), vx = (B2.star[0] - B.star[0]), vy = (B2.star[1] - B.star[1]);
    const vr = -vy * st.opt.vscale;   // m/s, positive = away (up the page)
    const L = 30 / Math.max(1e-9, st.opt.vmax);
    c.strokeStyle = vr > 0 ? '#FF6961' : '#0A84FF'; c.lineWidth = 2; c.beginPath(); c.moveTo(sr[0], sr[1]); c.lineTo(sr[0], sr[1] + vy * L * 1); c.stroke();
    c.strokeStyle = 'rgba(255,255,255,.25)'; c.beginPath(); c.moveTo(sr[0], sr[1]); c.lineTo(sr[0] + vx * L, sr[1]); c.stroke();
    mxText(c, 'across: invisible to Doppler', 14, narrow ? oy + side / 2 + 4 : h - 14, {size: 11});
    mxText(c, S.name, 14, 20, {size: 13, w: 600, color: '#F5F5F7'});
    mxText(c, `e = ${S.e}${S.e > 0.3 ? ': fastest at periastron' : ''}`, 14, 36, {size: 11});
    if (S.inset){
      // The Sun drawn to scale with the barycentre: Jupiter's lies just outside the surface, Earth's deep inside.
      const ix = narrow ? w - 40 : ox + side / 2 - 40, iy = 46, r0 = 22, off = q * S.a * MX_AU / MX_R.sun * r0;
      c.fillStyle = mxRgb(mxTeffRGB(5772)); c.beginPath(); c.arc(ix, iy, r0, 0, 2 * Math.PI); c.fill();
      c.strokeStyle = '#000'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(ix + off - 4, iy); c.lineTo(ix + off + 4, iy); c.moveTo(ix + off, iy - 4); c.lineTo(ix + off, iy + 4); c.stroke();
      c.strokeStyle = '#F5F5F7'; c.beginPath(); c.moveTo(ix + off - 4, iy); c.lineTo(ix + off + 4, iy); c.moveTo(ix + off, iy - 4); c.lineTo(ix + off, iy + 4); c.stroke();
      mxText(c, 'to scale: barycentre ' + (off > r0 ? 'outside' : 'inside') + ' the Sun', ix, iy + r0 + 14, {size: 11, align: 'center', color: '#C7C7CC'});
    }
    // RV curve, live.
    const gx = narrow ? 52 : side + 52, gy = narrow ? side + 50 : 34, gw = w - gx - 14, gh = narrow ? Math.max(80, h - gy - 110) : (h - 120) * 0.62;
    mxAxes(c, gx, gy, gw, gh, {y: 'RADIAL VELOCITY (m/s)', x: 'ORBITAL PHASE'});
    const Y = v => gy + gh / 2 - v / (K * 1.25) * gh / 2, X = f => gx + f * gw;
    c.strokeStyle = 'rgba(255,255,255,.1)'; c.beginPath(); c.moveTo(gx, Y(0)); c.lineTo(gx + gw, Y(0)); c.stroke();
    for (const v of [K, -K]) mxText(c, (v > 0 ? '+' : '−') + (Math.abs(v) < 1 ? Math.abs(v).toFixed(3) : Math.abs(v).toFixed(1)), gx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'});
    c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
    for (let i = 0; i <= 200; i++){ const f = i / 200, v = st.opt.curve[i]; i ? c.lineTo(X(f), Y(v)) : c.moveTo(X(f), Y(v)); } c.stroke();
    c.fillStyle = vr > 0 ? '#FF6961' : '#0A84FF'; c.beginPath(); c.arc(X(t), Y(vr), 4, 0, 2 * Math.PI); c.fill();
    mxText(c, `K = ${K < 1 ? K.toFixed(3) : K.toFixed(1)} m/s${S.kind === 'msini' ? ' (from m sin i)' : ''}${S.Kstored ? ` · stored ${S.Kstored} m/s` : ''}`, gx + gw, gy - (narrow ? 20 : 6), {size: 11, align: 'right', color: '#C7C7CC', mono: true});
    // Spectral lines shift with the star's velocity (exaggerated, stated).
    const F = Math.pow(10, Math.ceil(Math.log10(8 / (K / MX_C * 589))));
    mxSpectrum(c, gx, h - 58, gw, 20, vr / MX_C * 589 * F, '');
    mxText(c, `lines shifted ×${F.toExponential(0).replace('e+', 'e')} · ${vr > 0 ? 'redshift (away)' : 'blueshift (toward)'}`, gx + gw / 2, h - 25, {size: 11, color: '#C7C7CC', align: 'center'});
  }};
function mxPrepRv(st){
  const S = st.opt.sys, q = S.mp * MX_GM.jup / (S.ms * MX_GM.sun + S.mp * MX_GM.jup);
  st.opt.q = q; st.opt.K = mxK(S.P, S.mp, S.ms, S.e, S.sini == null ? 1 : S.sini);
  // The radial velocity is the star's velocity along the line of sight; its semi-amplitude is K.
  const n = 200, vy = [];
  for (let i = 0; i <= n; i++){ const a = mxBodies(i / n, S.e, q, S.w), b = mxBodies((i / n + 1e-3) % 1, S.e, q, S.w); vy.push(-(b.star[1] - a.star[1])); }
  const amp = (Math.max(...vy) - Math.min(...vy)) / 2, mid = (Math.max(...vy) + Math.min(...vy)) / 2;
  st.opt.vscale = st.opt.K / amp; st.opt.curve = vy.map(v => (v - mid) * st.opt.vscale); st.opt.vmax = amp;
}


// ---------- RV precision: granulation close-up and an Earth twin's signal in the noise ----------
MXV.jitter = {key: 0.4, period: 12, init(st){ st.opt.sig = 1; const rnd = mxRand(9); st.opt.cells = Array.from({length: 70}, () => ({x: rnd(), y: rnd(), r: 0.035 + rnd() * 0.04, ph: rnd() * 6.28}));
  const g = mxRand(21), n = 80; st.opt.noise = Array.from({length: n}, () => { let u = 0, v = 0; while (!u) u = g(); v = g(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }); },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.sig = Number(el.value); },
  draw(c, w, h, t, st){
    const narrow = w < 600, sw = narrow ? w : w * 0.42, sh = narrow ? h * 0.42 : h;
    // Granulation: bright rising cells, dark sinking lanes; markers move with the flow (texture, not to scale).
    c.save(); c.beginPath(); c.rect(0, 0, sw, sh); c.clip();
    c.fillStyle = '#5a3a14'; c.fillRect(0, 0, sw, sh);
    for (const cl of st.opt.cells){ const x = cl.x * sw, y = cl.y * sh, r = cl.r * Math.max(sw, sh) * (1 + 0.12 * Math.sin(t * 12 + cl.ph));
      const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, '#FFE6B0'); g.addColorStop(0.7, '#E8A050'); g.addColorStop(1, 'rgba(90,58,20,0)'); c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, 2 * Math.PI); c.fill();
      const up = Math.sin(t * 12 + cl.ph) > 0; c.strokeStyle = up ? '#0A84FF' : '#FF453A'; c.lineWidth = 1.4; c.beginPath(); c.moveTo(x - 4, y); c.lineTo(x + 4, y); c.moveTo(x, y - 4); c.lineTo(x, y + 4); c.stroke(); }
    c.restore();
    mxText(c, 'granulation close-up · blue: rising (toward us) · red: sinking', 10, sh - 10, {size: 11, color: '#F5F5F7'});
    // An Earth twin's signal with the chosen per-point noise.
    const K = mxK(365.25, 3.986004e14 / 1.2668653e17, 1, 0, 1), sig = st.opt.sig, n = st.opt.noise.length;
    const gx = narrow ? 50 : sw + 60, gy = narrow ? sh + 40 : 40, gw = w - gx - 16, gh = narrow ? h - gy - 40 : h - 90, lim = Math.max(0.15, 3 * sig);
    const X = f => gx + f * gw, Y = v => gy + gh / 2 - v / lim * gh / 2;
    mxAxes(c, gx, gy, gw, gh, {y: 'RADIAL VELOCITY (m/s)', x: 'TWO YEARS'});
    c.strokeStyle = 'rgba(255,255,255,.12)'; c.beginPath(); c.moveTo(gx, Y(0)); c.lineTo(gx + gw, Y(0)); c.stroke();
    const shown = Math.floor(t * n) + 1;
    c.fillStyle = 'rgba(100,210,255,.85)';
    for (let i = 0; i < shown && i < n; i++){ const f = i / (n - 1), v = K * Math.sin(2 * Math.PI * 2 * f) + sig * st.opt.noise[i]; c.beginPath(); c.arc(X(f), Y(v), 2.6, 0, 2 * Math.PI); c.fill(); }
    c.strokeStyle = '#FFB340'; c.lineWidth = 1.8; c.beginPath(); for (let i = 0; i <= 200; i++){ const f = i / 200; i ? c.lineTo(X(f), Y(K * Math.sin(4 * Math.PI * f))) : c.moveTo(X(f), Y(K * Math.sin(4 * Math.PI * f))); } c.stroke();
    for (const v of [lim, 0, -lim]) mxText(c, (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2), gx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'});
    mxText(c, `RADIAL VELOCITY: K = ${K.toFixed(3)} ± ${sig.toFixed(2)} m/s per point`, gx + 8, gy + 16, {size: 12, mono: true, color: '#F5F5F7'});
    st.exag = 'noise points illustrative (a seeded random draw); granulation texture not to scale';
  }};

// ---------- astrometry ----------
MXV.astrometry = {key: 0.55, period: 14, init(st){ st.opt.mode = 'all'; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, yrs = 6, N = 100;
    const pos = f => { const T = f * yrs, pm = (m === 'all' || m === 'pm') ? [T / yrs * 0.8 - 0.4, T / yrs * 0.3 - 0.15] : [0, 0];
      const pl = (m === 'all' || m === 'plx') ? [0.09 * Math.cos(2 * Math.PI * T), 0.05 * Math.sin(2 * Math.PI * T)] : [0, 0];
      const rf = (m === 'all' || m === 'reflex') ? [0.0003 * N * Math.cos(2 * Math.PI * T / 0.78), 0.0002 * N * Math.sin(2 * Math.PI * T / 0.78)] : [0, 0];
      return [w / 2 + (pm[0] + pl[0] + rf[0]) * w * 0.9, h / 2 - (pm[1] + pl[1] + rf[1]) * h * 1.4]; };
    c.strokeStyle = 'rgba(255,255,255,.07)'; for (let i = 1; i < 8; i++){ c.beginPath(); c.moveTo(i * w / 8, 0); c.lineTo(i * w / 8, h); c.stroke(); c.beginPath(); c.moveTo(0, i * h / 8); c.lineTo(w, i * h / 8); c.stroke(); }
    c.strokeStyle = 'rgba(100,210,255,.85)'; c.lineWidth = 1.4; c.beginPath();
    for (let i = 0; i <= 600; i++){ const f = i / 600; if (f > t) break; const p = pos(f); i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); } c.stroke();
    const p = pos(t); mxStar(c, p[0], p[1], 7, 3500, t, {flat: true, glow: 2.4});
    mxText(c, `year ${(t * yrs).toFixed(1)}`, 14, 20, {size: 12, mono: true, color: '#F5F5F7'});
    mxText(c, 'proper motion and parallax drawn to an illustrative scale', 14, h - 30, {size: 11});
    mxText(c, 'Wobble consistent with an orbiting companion', 14, h - 14, {size: 11, color: '#64D2FF'});
    if (m === 'all' || m === 'reflex') st.exag = `planet wobble ×${N} relative to parallax (GJ 896 Ab: α ≈ 0.5 mas against a parallax of about 160 mas)`;
  }};

// ---------- microlensing ----------
MXV.lens = {key: 0.5, period: 12, draw(c, w, h, t, st){
  const sceneH = h * 0.58, lx = -1.4 + 2.8 * t, u0 = 0.3;
  // A perspective grid dented under the lens and its planet (the source sits far behind).
  const proj = (x, z, y) => { const d = 3.2 + z, s = w * 0.42 / d; return [w / 2 + x * s, sceneH * 0.32 + (1.3 - y) * s * 0.55 + z * 10]; };
  const depth = (x, z) => -0.55 / (1 + ((x - lx) ** 2 + (z - u0) ** 2) / 0.08) - 0.12 / (1 + ((x - lx - 0.35) ** 2 + (z - u0 + 0.05) ** 2) / 0.006);
  c.strokeStyle = 'rgba(100,210,255,.35)'; c.lineWidth = 1;
  for (let i = 0; i <= 18; i++){ const z = -0.4 + i * 0.12; c.beginPath(); for (let j = 0; j <= 60; j++){ const x = -2 + j / 15; const p = proj(x, z, depth(x, z)); j ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); } c.stroke(); }
  for (let j = 0; j <= 24; j++){ const x = -2 + j / 6; c.beginPath(); for (let i = 0; i <= 40; i++){ const z = -0.4 + i * 0.054; const p = proj(x, z, depth(x, z)); i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); } c.stroke(); }
  const L = proj(lx, u0, depth(lx, u0) + 0.08), Pp = proj(lx + 0.35, u0 - 0.05, 0.02);
  mxStar(c, L[0], L[1], 7, 3300, t, {flat: true, glow: 2});
  c.fillStyle = '#C7A27C'; c.beginPath(); c.arc(Pp[0], Pp[1], 2.5, 0, 2 * Math.PI); c.fill();
  mxText(c, w < 600 ? 'lens star (often unseen)' : 'lens star (often unseen) and its planet', L[0] + 12, L[1] - 10, {size: 11});
  const src = [w / 2, 18]; mxStar(c, src[0], src[1], 4, 9000, t, {flat: true, glow: 3});
  mxText(c, 'source star, far behind', src[0] + 10, src[1] + 4, {size: 11});
  const tel = [w / 2, sceneH - 10];
  c.fillStyle = '#C7C7CC'; c.beginPath(); c.moveTo(tel[0] - 10, tel[1]); c.lineTo(tel[0] + 10, tel[1]); c.lineTo(tel[0] + 6, tel[1] - 14); c.lineTo(tel[0] - 6, tel[1] - 14); c.closePath(); c.fill();
  mxText(c, 'telescope', tel[0] + 14, tel[1] - 2, {size: 11});
  // Bent rays from the source past the lens to the telescope (bending exaggerated).
  c.strokeStyle = 'rgba(255,255,255,.35)'; for (const s of [-1, 1]){ c.beginPath(); c.moveTo(src[0], src[1]); c.quadraticCurveTo(L[0] + s * 26, L[1], tel[0], tel[1] - 14); c.stroke(); }
  st.exag = 'ray bending ×1,000,000; grid depth illustrative';
  // The magnification curve A(u), with a schematic planetary spike.
  const gx = 54, gy = sceneH + 24, gw = w - gx - 18, gh = h - gy - 38, tE = 0.5;
  mxGlassPanel(c, 10, sceneH + 4, w - 20, h - sceneH - 10);
  mxAxes(c, gx, gy, gw, gh, {y: 'MAGNIFICATION A', x: 'TIME (Einstein crossing times)'});
  const Af = f => { const u = Math.hypot(u0, (f - 0.5) / tE * 2); return mxPacz(u) + 0.45 * Math.exp(-0.5 * ((f - 0.625) / 0.008) ** 2); };
  const Amax = Af(0.5) + 0.5, X = f => gx + f * gw, Y = A => gy + gh - (A - 1) / (Amax - 1) * gh * 0.92;
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
  for (let i = 0; i <= 400; i++){ const f = i / 400; if (f > t) break; i ? c.lineTo(X(f), Y(Af(f))) : c.moveTo(X(f), Y(Af(f))); } c.stroke();
  for (const A of [1, 2, 3]) if (A < Amax) mxText(c, String(A), gx - 6, Y(A) + 4, {size: 11, mono: true, align: 'right'});
  mxText(c, `u₀ = ${u0}; A(u) = (u² + 2)/(u√(u² + 4))`, gx + 8, gy + 14, {size: 11, mono: true, color: '#C7C7CC'});
  if (t > 0.63) mxText(c, 'planetary spike: schematic', X(0.64) + 6, Y(Af(0.625)) - 4, {size: 11});
  if (w < 600) mxText(c, 'This event will never repeat', gx + 8, gy + 30, {size: 12, w: 600, color: '#F5F5F7'});
  else mxText(c, 'This event will never repeat', gx + gw, gy + 14, {size: 12, w: 600, align: 'right', color: '#F5F5F7'});
}};

// ---------- blocking starlight ----------
MXV.coronagraph = {key: 0.7, period: 16, init(st){ st.opt.mode = 'mask'; const rnd = mxRand(3); st.opt.speckles = Array.from({length: 60}, () => ({a: rnd() * 2 * Math.PI, r: 0.18 + rnd() * 0.5, s: 0.5 + rnd()})); },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.46;
    if (m === 'sun'){
      // An illustration based on SOHO LASCO: an occulting disc, the solar disc outline, streamers.
      for (let i = 0; i < 14; i++){ const a = i / 14 * 2 * Math.PI + t * 0.3 + Math.sin(i * 7) * 0.3, len = R * (0.6 + 0.4 * Math.abs(Math.sin(i * 3.1)));
        const g = c.createLinearGradient(cx, cy, cx + Math.cos(a) * len, cy + Math.sin(a) * len); g.addColorStop(0, 'rgba(255,200,140,.5)'); g.addColorStop(1, 'rgba(255,200,140,0)');
        c.fillStyle = g; c.beginPath(); c.moveTo(cx + Math.cos(a - 0.12) * R * 0.2, cy + Math.sin(a - 0.12) * R * 0.2); c.lineTo(cx + Math.cos(a) * len, cy + Math.sin(a) * len); c.lineTo(cx + Math.cos(a + 0.12) * R * 0.2, cy + Math.sin(a + 0.12) * R * 0.2); c.fill(); }
      const g = c.createRadialGradient(cx, cy, R * 0.2, cx, cy, R); g.addColorStop(0, 'rgba(255,190,120,.5)'); g.addColorStop(1, 'rgba(255,190,120,0)'); c.fillStyle = g; c.beginPath(); c.arc(cx, cy, R, 0, 2 * Math.PI); c.fill();
      c.fillStyle = '#111'; c.beginPath(); c.arc(cx, cy, R * 0.22, 0, 2 * Math.PI); c.fill();
      c.strokeStyle = '#F5F5F7'; c.lineWidth = 1; c.beginPath(); c.arc(cx, cy, R * 0.1, 0, 2 * Math.PI); c.stroke();
      mxText(c, 'Illustration based on SOHO LASCO, not a LASCO image. Real images: SOHO (ESA & NASA).', 14, h - 14, {size: 11});
      mxText(c, 'occulting disc · white circle: the Sun’s disc', 14, 20, {size: 11, color: '#C7C7CC'});
      return;
    }
    if (m === 'shade'){
      const sy = cy, bob = Math.sin(t * 2 * Math.PI) * 3;
      mxStar(c, 40, sy, 14, 5772, t, {flat: true});
      const shx = w * 0.45, sr = Math.min(70, h * 0.22);
      c.fillStyle = 'rgba(0,0,0,.6)'; c.beginPath(); c.moveTo(shx, sy - sr * 0.4 + bob); c.lineTo(w - 50, sy - 10); c.lineTo(w - 50, sy + 10); c.lineTo(shx, sy + sr * 0.4 + bob); c.fill();
      c.save(); c.translate(shx, sy + bob); c.scale(0.18, 1); c.fillStyle = '#C7C7CC';
      c.beginPath(); for (let i = 0; i < 16; i++){ const a0 = i / 16 * 2 * Math.PI, a1 = (i + 0.5) / 16 * 2 * Math.PI; c.lineTo(Math.cos(a0) * sr * 0.45, Math.sin(a0) * sr * 0.45); c.lineTo(Math.cos(a1) * sr, Math.sin(a1) * sr); } c.closePath(); c.fill(); c.restore();
      c.strokeStyle = 'rgba(255,255,255,.25)'; c.beginPath(); c.moveTo(54, sy); c.lineTo(shx, sy - sr * 0.4 + bob); c.moveTo(54, sy); c.lineTo(shx, sy + sr * 0.4 + bob); c.stroke();
      c.strokeStyle = '#64D2FF'; c.beginPath(); c.moveTo(54, sy - 40); c.lineTo(w - 50, sy - 6); c.stroke();
      mxText(c, 'planet light passes the edge', w * 0.62, sy - 38, {size: 11, color: '#64D2FF'});
      c.fillStyle = '#F5F5F7'; c.fillRect(w - 50, sy - 12, 22, 24); mxText(c, 'telescope', w - 39, sy + 30, {size: 11, align: 'center'});
      mxText(c, 'starshade (petals shape the shadow)', shx, sy - sr - 8, {size: 11, align: 'center', color: '#C7C7CC'});
      mxText(c, 'Roman concept: 26 m at 26,000 km · HabEx: 52 m at ≈76,600 km', 14, h - 14, {size: 11});
      st.exag = 'not to scale: true ratio 26 m : 26,000 km = 1 : 10⁶';
      return;
    }
    if (m === 'null'){
      const rot = t * 2 * Math.PI, fr = 26;
      c.save(); c.translate(cx, cy * 0.8); c.rotate(rot);
      for (let x = -w; x < w; x += 2){ const v = Math.sin(Math.PI * x / fr) ** 2; c.fillStyle = `rgba(100,210,255,${0.25 * v})`; c.fillRect(x, -h, 2, 2 * h); }
      c.restore();
      mxStar(c, cx, cy * 0.8, 8, 5772, t, {flat: true, glow: 1.3});
      mxText(c, 'star on the dark fringe', cx + 12, cy * 0.8 - 10, {size: 11});
      const ppx = cx + 70, ppy = cy * 0.8 - 30; c.fillStyle = '#C7A27C'; c.beginPath(); c.arc(ppx, ppy, 3, 0, 2 * Math.PI); c.fill();
      const dx = (ppx - cx) * Math.cos(-rot) - (ppy - cy * 0.8) * Math.sin(-rot), sig = Math.sin(Math.PI * dx / fr) ** 2;
      mxText(c, 'planet', ppx + 8, ppy - 4, {size: 11});
      for (const s of [-1, 1]){ c.fillStyle = '#C7C7CC'; c.beginPath(); c.arc(cx + s * 60, h - 34, 9, 0, 2 * Math.PI); c.fill(); }
      mxText(c, 'two telescopes, combined half a wave apart', cx, h - 12, {size: 11, align: 'center'});
      mxGlassPanel(c, w - 170, 12, 158, 54); mxText(c, 'planet signal', w - 160, 30, {size: 11});
      c.fillStyle = '#64D2FF'; c.fillRect(w - 160, 40, 138 * sig, 10);
      mxText(c, 'Bracewell 1978; LIFE concept', 14, 20, {size: 11, color: '#C7C7CC'});
      st.exag = 'fringe spacing illustrative';
      return;
    }
    // The coronagraph: the mask slides in, the glare collapses to speckles, HR 8799's planets appear.
    const mask = Math.min(1, t / 0.25), clear = Math.max(0, Math.min(1, (t - 0.3) / 0.3));
    const g = c.createRadialGradient(cx, cy, 0, cx, cy, R); g.addColorStop(0, `rgba(255,248,235,${1 - 0.92 * clear})`); g.addColorStop(0.08, `rgba(255,240,215,${0.7 - 0.6 * clear})`); g.addColorStop(1, 'rgba(255,240,215,0)');
    c.fillStyle = g; c.beginPath(); c.arc(cx, cy, R, 0, 2 * Math.PI); c.fill();
    for (let k = 1; k < 7; k++){ c.strokeStyle = `rgba(255,240,220,${(0.2 - 0.17 * clear) / k})`; c.beginPath(); c.arc(cx, cy, R * 0.07 * k, 0, 2 * Math.PI); c.stroke(); }
    for (const s of st.opt.speckles){ const tw = 0.5 + 0.5 * Math.sin(t * 30 + s.a * 9); c.fillStyle = `rgba(255,230,200,${(0.35 - 0.27 * clear) * tw})`; c.beginPath(); c.arc(cx + Math.cos(s.a) * s.r * R, cy + Math.sin(s.a) * s.r * R, 2.2 * s.s, 0, 2 * Math.PI); c.fill(); }
    const mx = cx - (1 - mask) * w * 0.6; c.fillStyle = '#050505'; c.strokeStyle = 'rgba(255,255,255,.35)'; c.beginPath(); c.arc(mx, cy, R * 0.12, 0, 2 * Math.PI); c.fill(); c.stroke();
    c.setLineDash([3, 4]); c.strokeStyle = 'rgba(100,210,255,.6)'; c.beginPath(); c.arc(cx, cy, R * 0.16, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
    mxText(c, 'inner working angle (a few λ/D)', cx, cy - R * 0.16 - 8, {size: 11, color: '#64D2FF', align: 'center'});
    const planets = ['HR 8799 e', 'HR 8799 d', 'HR 8799 c', 'HR 8799 b'].map(n => [n, MX.examples[n]]).filter(p => p[1]);
    const amax = Math.max(...planets.map(p => p[1].semi_major_axis || 1)), ci = Math.cos(25 * Math.PI / 180);
    planets.forEach(([n, p], i) => {
      const a = p.semi_major_axis / amax * R * 0.92, e = p.eccentricity || 0, f = (t * 4 * (amax / p.semi_major_axis) ** 1.5 + i * 0.27) % 1;
      const nu = mxNu(2 * Math.PI * f, e), r = a * (1 - e * e) / (1 + e * Math.cos(nu)), x = cx + r * Math.cos(nu), y = cy + r * Math.sin(nu) * ci;
      c.strokeStyle = `rgba(255,255,255,${0.12 * clear})`; c.beginPath(); c.ellipse(cx - a * e, cy, a, a * Math.sqrt(1 - e * e) * ci, 0, 0, 2 * Math.PI); c.stroke();
      c.fillStyle = `rgba(255,170,120,${clear})`; c.beginPath(); c.arc(x, y, 3.2, 0, 2 * Math.PI); c.fill();
      if (clear > 0.5) mxText(c, n.replace('HR 8799 ', ''), x + 6, y - 4, {size: 11, color: '#F5F5F7'});
    });
    mxText(c, 'HR 8799 (schematic orbits: a and e from exoplanet.eu; orientation illustrative)', 14, h - 14, {size: 11});
    st.exag = 'log brightness stretch; orbital time compressed; planets drawn as dots';
  }};

// ---------- reading atmospheres: transmission ----------
const MX_RAMP = [[0.6, '#3B2A8C'], [1.2, '#2E6BFF'], [2.0, '#22C1E6'], [2.8, '#3EDB62'], [3.6, '#F2E43A'], [4.4, '#FF9F2E'], [5.0, '#E0302F']];
MXV.transmission = {key: 0.5, period: 12, draw(c, w, h, t, st){
  const sceneH = h * 0.5, sx = w * 0.18, sy = sceneH / 2, SR = sceneH * 0.9;
  mxStar(c, sx - SR * 0.45, sy, SR * 0.62, 5400, t, {flat: true, glow: 1.25});
  // The planet crosses the star's limb; its atmosphere annulus is drawn ten times too thick.
  const pxp = sx - SR * 0.45 + (t * 2.2 - 0.6) * SR * 0.8, py = sy, pr = sceneH * 0.16;
  const over = Math.max(0, Math.min(1, 1 - Math.abs(pxp - (sx - SR * 0.45)) / (SR * 0.62 + pr)));
  c.fillStyle = 'rgba(120,170,214,.25)'; c.beginPath(); c.arc(pxp, py, pr * 1.18, 0, 2 * Math.PI); c.fill();
  mxPlanet(c, pxp, py, pr, 4, false);
  c.strokeStyle = 'rgba(255,240,200,.35)'; c.lineWidth = 1;
  for (let i = -3; i <= 3; i++){ const yy = py + i * pr * 0.35; if (Math.abs(i) < 3) continue; c.beginPath(); c.moveTo(pxp, yy); c.lineTo(w - 20, yy * 0.98 + sy * 0.02); c.stroke(); }
  for (const s of [-1, 1]){ c.beginPath(); c.moveTo(pxp, py + s * pr * 1.09); c.lineTo(w - 20, py + s * pr * 0.6); c.stroke(); }
  mxText(c, 'starlight through the limb', w - 20, sy - pr - 10, {size: 11, align: 'right'});
  st.exag = 'atmosphere drawn ×10 thicker; planet and star not to scale';
  // Two spectrum bars in false colour, 0.6–5 µm, with the real band positions.
  const L0 = 0.5, L1 = 5.1, bx = 24, bw = w - 48, X = l => bx + (l - L0) / (L1 - L0) * bw;
  const bar = (y, label, absorb) => {
    const g = c.createLinearGradient(bx, 0, bx + bw, 0); for (const [l, col] of MX_RAMP) g.addColorStop(Math.max(0, Math.min(1, (l - L0) / (L1 - L0))), col);
    c.fillStyle = g; c.fillRect(bx, y, bw, 36);
    if (absorb > 0) for (const [mol, l] of MX.bands){ const wd = mol === 'Na' || mol === 'K' ? 2 : 7; c.fillStyle = `rgba(0,0,0,${0.85 * absorb})`; c.fillRect(X(l) - wd / 2, y, wd, 36); }
    mxText(c, label, bx, y - 6, {size: 11, w: 600, color: '#C7C7CC', mono: true});
  };
  const y1 = sceneH + 30, y2 = y1 + 70;
  bar(y1, 'STARLIGHT ONLY', 0);
  bar(y2, 'DURING TRANSIT', over);
  let last = -1;
  for (const [mol, l] of MX.bands){ const x = X(l); if (x - last < 24) continue; last = x; mxText(c, mol, x, y2 + 54, {size: 11, align: 'center', color: '#F5F5F7'}); }
  for (const l of [1, 2, 3, 4, 5]) mxText(c, l + ' µm', X(l), y2 + 72, {size: 11, mono: true, align: 'center'});
  mxText(c, 'false colour: infrared is invisible to the eye · schematic, band positions real', bx, h - 8, {size: 11});
}};

// ---------- a real spectrum and the Atmosphere Lab ----------
function mxAtm(lam, base, dH, S){ let v = base; for (const m in S) for (const [c, w] of MX.lab_bands[m]) v += S[m] * dH * Math.exp(-0.5 * ((lam - c) / w) ** 2); return v; }
function mxSpecChart(c, w, h, o){
  // A depth-against-wavelength chart, 0.5–5.4 µm, with the band positions marked along the bottom.
  const L0 = 0.5, L1 = 5.4, gx = 64, gy = 34, gw = w - gx - 16, gh = h - gy - 58;
  const X = l => gx + (l - L0) / (L1 - L0) * gw, Y = v => gy + gh - (v - o.lo) / (o.hi - o.lo) * gh;
  mxAxes(c, gx, gy, gw, gh, {y: 'TRANSIT DEPTH (ppm)', x: 'WAVELENGTH (µm)'});
  for (let k = 0; k <= 4; k++){ const v = o.lo + (o.hi - o.lo) * k / 4; c.strokeStyle = 'rgba(255,255,255,.06)'; c.beginPath(); c.moveTo(gx, Y(v)); c.lineTo(gx + gw, Y(v)); c.stroke(); mxText(c, Math.round(v).toLocaleString('en-GB'), gx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
  for (const l of [1, 2, 3, 4, 5]) mxText(c, l + ' µm', X(l), gy + gh + 14, {size: 11, mono: true, align: 'center'});
  let last = -1; for (const [mol, l] of MX.bands){ const x = X(l); c.strokeStyle = 'rgba(255,255,255,.12)'; c.setLineDash([2, 4]); c.beginPath(); c.moveTo(x, gy); c.lineTo(x, gy + gh); c.stroke(); c.setLineDash([]); if (x - last < 26) continue; last = x; mxText(c, mol, x, gy + gh + 30, {size: 11, align: 'center', color: '#C7C7CC'}); }
  return {X, Y, gx, gy, gw, gh};
}
function mxJwstPoints(c, A, J){
  c.strokeStyle = 'rgba(100,210,255,.8)'; c.fillStyle = '#64D2FF'; c.lineWidth = 1;
  for (const [l, lo, hi, d, e] of J.points){ const x = A.X(l), y = A.Y(d);
    c.beginPath(); c.moveTo(x, A.Y(d - e)); c.lineTo(x, A.Y(d + e)); c.moveTo(A.X(lo), y); c.lineTo(A.X(hi), y); c.stroke();
    c.beginPath(); c.arc(x, y, 2.6, 0, 2 * Math.PI); c.fill(); }
}
MXV.jwst = {key: 0, period: 1, draw(c, w, h, t, st){
  const J = MX.jwst; if (!J) return;
  const ds = J.points.map(p => p[3]), lo = Math.min(...ds) - 400, hi = Math.max(...ds) + 400;
  const A = mxSpecChart(c, w, h, {lo, hi});
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.4; c.beginPath(); let on = false;
  for (const [l, d] of J.model){ if (l < 0.5 || l > 5.4) continue; on ? c.lineTo(A.X(l), A.Y(d)) : c.moveTo(A.X(l), A.Y(d)); on = true; } c.stroke();
  mxJwstPoints(c, A, J);
  const cap = `dots: JWST NIRSpec PRISM, ${J.licence} · line: the paper's best-fit model`;
  mxText(c, 'WASP-39 b', A.gx + 8, A.gy + 16, {size: 13, w: 600, color: '#F5F5F7'});
  if (w < 600) mxText(c, cap, A.gx + 8, A.gy + 32, {size: 11}); else mxText(c, cap, A.gx + A.gw, A.gy - 6, {size: 11, align: 'right'});
}};
MXV.atmlab = {key: 0, period: 1, init(st){
  const w = MX.examples['WASP-39 b'] || {};
  st.opt.lab = {mols: {H2O: 1, CO2: 1, Na: 1, K: 1}, n: 2, T: 1116, mu: 2.3, real: false, p: w};
}, control(st, el){
  const L = st.opt.lab;
  if (el.dataset.mol){ const on = el.getAttribute('aria-pressed') === 'true'; if (on) L.mols[el.dataset.mol] = 1; else delete L.mols[el.dataset.mol]; }
  else if (el.dataset.ctl === 'real') L.real = el.getAttribute('aria-pressed') === 'true';
  else if (el.dataset.ctl === 'n') L.n = Number(el.value) / 10;
  else if (el.dataset.ctl === 'T') L.T = Number(el.value);
  else if (el.dataset.ctl === 'mu') L.mu = Number(el.value);
}, draw(c, w, h, t, st){
  const L = st.opt.lab, p = L.p, kB = 1.380649e-23, mH = 1.6735575e-27;
  const g = p.mass * MX_GM.jup / (p.radius * MX_R.jup) ** 2, H = kB * L.T / (L.mu * mH * g), Rp = p.radius * MX_R.jup, Rs = p.star_radius * MX_R.sun;
  const dH = 2 * H * Rp / (Rs * Rs) * 1e6, base = (Rp / Rs) ** 2 * 1e6, S = {};
  for (const m in L.mols) S[m] = L.n;
  const vals = []; for (let i = 0; i <= 500; i++){ const l = 0.5 + 4.9 * i / 500; vals.push([l, mxAtm(l, base, dH, S)]); }
  let lo = base - 200, hi = Math.max(...vals.map(v => v[1])) + 300;
  if (L.real && MX.jwst){ const ds = MX.jwst.points.map(q => q[3]); lo = Math.min(lo, Math.min(...ds) - 300); hi = Math.max(hi, Math.max(...ds) + 300); }
  const A = mxSpecChart(c, w, h, {lo, hi});
  c.strokeStyle = '#FFB340'; c.lineWidth = 1.8; c.beginPath(); vals.forEach(([l, v], i) => i ? c.lineTo(A.X(l), A.Y(v)) : c.moveTo(A.X(l), A.Y(v))); c.stroke();
  if (L.real && MX.jwst) mxJwstPoints(c, A, MX.jwst);
  const narrow = w < 600;
  mxText(c, `H = ${Math.round(H / 1000).toLocaleString('en-GB')} km · 1 H = ${Math.round(dH)} ppm` + (narrow ? '' : ` · baseline (Rp/R★)² = ${Math.round(base).toLocaleString('en-GB')} ppm`), A.gx + 8, A.gy + 16, {size: 11, mono: true, color: '#F5F5F7'});
  const cap = L.real ? 'line: model (toy) · dots: JWST data, cited' : 'line: model (toy), not data';
  if (narrow) mxText(c, cap, A.gx + 8, A.gy + 32, {size: 11}); else mxText(c, cap, A.gx + A.gw, A.gy - 6, {size: 11, align: 'right'});
}};


// ---------- timing and phase ----------
MXV.timing = {key: 0.35, period: 14, init(st){ st.opt.mode = 'ttv'; st.opt.lam = 0; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; if (el.type === 'range') st.opt.lam = Number(el.value); },
  draw(c, w, h, t, st){
    const m = st.opt.mode, sceneH = h * 0.5, cx = w * 0.3, cy = sceneH / 2 + 10;
    const gx = 56, gy = sceneH + 30, gw = w - gx - 18, gh = h - gy - 36;
    mxGlassPanel(c, 10, sceneH + 8, w - 20, h - sceneH - 14);
    if (m === 'ttv'){
      // Two planets near 2:1: the inner one's transits drift early and late (amplitude illustrative).
      const P1 = 1, P2 = 2.1, T = t * 24, r1 = sceneH * 0.22, r2 = sceneH * 0.35;
      mxStar(c, cx, cy, 14, 5774, t, {flat: true});
      for (const [r, P] of [[r1, P1], [r2, P2]]){ c.strokeStyle = 'rgba(255,255,255,.2)'; c.setLineDash([3, 5]); c.beginPath(); c.ellipse(cx, cy, r, r * 0.35, 0, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
        const a = 2 * Math.PI * T / P; mxPlanet(c, cx + r * Math.sin(a), cy + r * 0.35 * Math.cos(a), 4, 4, true); }
      c.strokeStyle = 'rgba(100,210,255,.5)'; c.beginPath(); c.moveTo(cx, cy + 20); c.lineTo(cx, sceneH); c.stroke(); mxText(c, 'to observer', cx + 6, sceneH - 4, {size: 11});
      const sup = 1 / Math.abs(2 / P2 - 1 / P1), n = Math.floor(T / P1);
      mxAxes(c, gx, gy, gw, gh, {y: 'O − C (illustrative)', x: 'TRANSIT NUMBER'});
      c.fillStyle = '#FFB340';
      for (let k = 0; k <= Math.min(n, 23); k++){ const v = Math.sin(2 * Math.PI * k * P1 / sup); c.beginPath(); c.arc(gx + (k + 0.5) / 24 * gw, gy + gh / 2 - v * gh * 0.38, 3.5, 0, 2 * Math.PI); c.fill(); }
      c.strokeStyle = 'rgba(255,255,255,.12)'; c.beginPath(); c.moveTo(gx, gy + gh / 2); c.lineTo(gx + gw, gy + gh / 2); c.stroke();
      mxText(c, 'early / late against a strict period; Kepler-9: minutes per orbit (Holman et al. 2010)', gx + 6, gy + 14, {size: 11});
      st.exag = 'O−C amplitude illustrative; orbits not to scale';
    } else if (m === 'eclipse' || m === 'phase'){
      // One orbit: transit at phase 0, secondary eclipse at 0.5; the planet's own light rises toward occultation.
      const ph = t, a = 2 * Math.PI * ph, R = sceneH * 0.36, px = cx + R * Math.sin(a), py = cy + R * 0.3 * Math.cos(a), front = Math.cos(a) > 0;
      if (!front) mxPlanet(c, px, py, 7, 4, true);
      mxStar(c, cx, cy, 22, 4900, t, {flat: true});
      if (front) mxPlanet(c, px, py, 7, 4, Math.abs(px - cx) > 29);
      // Day side facing the star: show it as the lit hemisphere seen from the observer.
      const off = m === 'phase' ? 16 * Math.PI / 180 : 0;
      const F = f => { const A = 2 * Math.PI * f; let v = 0.5 * (1 - Math.cos(A - off)) * 0.25;            // planet light (fraction of day side)
        const z = Math.abs(Math.sin(A)) * 8;
        if (Math.cos(A) > 0 && z < 1.15) v -= 1;                     // transit (drawn to the panel scale)
        if (Math.cos(A) < 0 && z < 1.15) v -= 0.5 * (1 - Math.cos(A - off)) * 0.25;   // occultation hides the planet's light
        return v; };
      mxAxes(c, gx, gy, gw, gh, {y: m === 'phase' ? 'BRIGHTNESS (planet light ×10)' : 'BRIGHTNESS (secondary ×10)', x: 'ORBITAL PHASE'});
      const Y = v => gy + gh * 0.25 - v * gh * 0.6;
      c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
      for (let i = 0; i <= 400; i++){ const f = i / 400 - 0.25; const x = gx + i / 400 * gw; i ? c.lineTo(x, Y(F(f))) : c.moveTo(x, Y(F(f))); } c.stroke();
      c.fillStyle = '#FFB340'; const fx = ((ph + 0.25) % 1); c.beginPath(); c.arc(gx + fx * gw, Y(F(ph)), 3.5, 0, 2 * Math.PI); c.fill();
      mxText(c, 'transit', gx + 0.25 * gw, gy + gh - 6, {size: 11, align: 'center'}); mxText(c, 'occultation', gx + 0.75 * gw, gy + gh - 6, {size: 11, align: 'center'});
      if (m === 'phase') mxText(c, 'peak shifted by winds (HD 189733 b: 16° before occultation)', gx + 6, gy + 14, {size: 11});
      st.exag = m === 'phase' ? 'planet light drawn ×10 against the transit; offset 16° as measured' : 'secondary eclipse drawn ×10 deeper than true; transit depth not to scale';
    } else {
      // Rossiter–McLaughlin: the star's disc coloured by its rotation (a velocity map), the planet crossing at λ.
      const R = sceneH * 0.38, lam = st.opt.lam * Math.PI / 180;
      for (let x = -R; x <= R; x += 2){ const v = x / R, hc = Math.sqrt(Math.max(0, R * R - x * x)); c.fillStyle = v < 0 ? `rgba(10,132,255,${0.25 + 0.6 * -v})` : `rgba(255,105,97,${0.25 + 0.6 * v})`; c.fillRect(cx + x, cy - hc, 2, 2 * hc); }
      mxText(c, 'approaching', cx - R, cy + R + 14, {size: 11, color: '#64D2FF'}); mxText(c, 'receding', cx + R, cy + R + 14, {size: 11, color: '#FF6961', align: 'right'});
      const b = 0.3, path = f => { const u = -1.3 + 2.6 * f; return [u * Math.cos(lam) - b * Math.sin(lam), u * Math.sin(lam) + b * Math.cos(lam)]; };
      const [ux, uy] = path(t); c.fillStyle = '#111'; c.beginPath(); c.arc(cx + ux * R, cy + uy * R, R * 0.13, 0, 2 * Math.PI); c.fill();
      c.setLineDash([3, 4]); c.strokeStyle = 'rgba(255,255,255,.4)'; c.beginPath(); const p0 = path(0), p1 = path(1); c.moveTo(cx + p0[0] * R, cy + p0[1] * R); c.lineTo(cx + p1[0] * R, cy + p1[1] * R); c.stroke(); c.setLineDash([]);
      mxText(c, `λ = ${st.opt.lam}°`, 14, 22, {size: 13, w: 600, color: '#F5F5F7'});
      // Anomaly: minus the blocked light's velocity (velocity ∝ x on the disc), only while on the disc.
      const anom = f => { const [x, y] = path(f); return x * x + y * y < 1 ? -x : 0; };
      mxAxes(c, gx, gy, gw, gh, {y: 'RV ANOMALY (shape)', x: 'TIME THROUGH TRANSIT'});
      c.strokeStyle = 'rgba(255,255,255,.12)'; c.beginPath(); c.moveTo(gx, gy + gh / 2); c.lineTo(gx + gw, gy + gh / 2); c.stroke();
      c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
      for (let i = 0; i <= 300; i++){ const f = i / 300, y = gy + gh / 2 - anom(f) * gh * 0.4; i ? c.lineTo(gx + f * gw, y) : c.moveTo(gx + f * gw, y); } c.stroke();
      c.fillStyle = '#FFB340'; c.beginPath(); c.arc(gx + t * gw, gy + gh / 2 - anom(t) * gh * 0.4, 3.5, 0, 2 * Math.PI); c.fill();
      mxText(c, 'amplitude ≈ V sin I · k²: tens of m/s for hot Jupiters', gx + 6, gy + 14, {size: 11});
      st.exag = 'colour = velocity map, not a colour change; planet drawn larger';
    }
  }};

// ---------- false positives ----------
MXV.falsepos = {key: 0.5, period: 10, init(st){ st.opt.mode = 'eb'; }, control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, narrow = w < 600, px = narrow ? Math.min(w - 40, 200) : Math.min(w * 0.36, h - 120);
    const ox = narrow ? (w - px) / 2 : 24, oy = narrow ? 34 : 50, cell = px / 5;
    // A 5×5 patch of TESS pixels (21″ each), drawn to scale with the stars on it.
    c.strokeStyle = 'rgba(255,255,255,.18)';
    for (let i = 0; i <= 5; i++){ c.beginPath(); c.moveTo(ox + i * cell, oy); c.lineTo(ox + i * cell, oy + px); c.stroke(); c.beginPath(); c.moveTo(ox, oy + i * cell); c.lineTo(ox + px, oy + i * cell); c.stroke(); }
    c.strokeStyle = '#FFB340'; c.strokeRect(ox + cell, oy + cell, 3 * cell, 3 * cell);
    mxText(c, 'TESS pixels, 21″ each · aperture in amber', ox, oy - 8, {size: 11});
    const tx = ox + px / 2, ty = oy + px / 2;
    mxStar(c, tx, ty, 9, 5800, t, {flat: true, glow: 1.6}); mxText(c, 'target', tx + 12, ty - 10, {size: 11, color: '#F5F5F7'});
    const nb = m === 'beb' ? [tx + cell * 1.1, ty - cell * 0.8] : m === 'heb' ? [tx + cell * 0.12, ty + cell * 0.08] : null;
    if (nb){ mxStar(c, nb[0], nb[1], m === 'heb' ? 4 : 3.5, 3800, t, {flat: true, glow: 1.8}); mxText(c, m === 'heb' ? 'bound eclipsing pair, unresolved' : 'faint background binary', nb[0] + 8, nb[1] - 6, {size: 11}); }
    // The light curve each scenario makes.
    const gx = narrow ? 50 : ox + px + 60, gy = narrow ? oy + px + 40 : 50, gw = w - gx - 18, gh = narrow ? h - gy - 40 : h - 110;
    const shape = (f, kind) => {
      const x = f - 0.5;
      if (kind === 'eb') return Math.abs(x) < 0.06 ? 1 - 0.8 * (1 - Math.abs(x) / 0.06) : (Math.abs(Math.abs(x) - 0.5) < 0.06 ? 1 - 0.3 * (1 - Math.abs(Math.abs(x) - 0.5) / 0.06) : 1);
      if (kind === 'beb' || kind === 'heb') return Math.abs(x) < 0.05 ? 1 - 0.5 * 0.002 * (1 - Math.abs(x) / 0.05) * 6 : 1;
      if (kind === 'oddeven') { const k = Math.round(f * 4); const d = k % 2 ? 0.6 : 0.4; return Math.abs(f * 4 - k) < 0.08 ? 1 - d * (1 - Math.abs(f * 4 - k) / 0.08) * 0.5 : 1; }
      return f > 0.45 && f < 0.47 ? 0.6 : (f >= 0.47 ? 1 - 0.15 * Math.exp(-(f - 0.47) * 25) : 1);
    };
    mxAxes(c, gx, gy, gw, gh, {y: 'BRIGHTNESS (shape, illustrative)', x: m === 'oddeven' ? 'TIME (four events)' : 'ORBITAL PHASE'});
    c.strokeStyle = '#FFB340'; c.lineWidth = 1.6; c.beginPath();
    for (let i = 0; i <= 400; i++){ const f = i / 400; if (f > t + 0.0001) break; const y = gy + 10 + (1 - shape(f, m)) * (gh - 20); i ? c.lineTo(gx + f * gw, y) : c.moveTo(gx + f * gw, y); } c.stroke();
    const note = {eb: 'V-shaped and with a deep secondary: a grazing binary, not a planet',
      beb: 'a 50% eclipse diluted ×1,000 looks like a 500 ppm "planet"',
      heb: 'the pair and the target share a pixel: depth diluted, shape can look planetary',
      oddeven: 'alternate depths differ: two stars, period really twice as long (exoplan flags odd_even_mismatch)',
      sys: 'a jump and recovery from the spacecraft, not an orbit'}[m];
    mxText(c, note, gx + 6, gy + 14, {size: 11, color: '#C7C7CC'});
    st.exag = 'curves are shapes, not to a common depth scale; pixel grid to scale';
  }};

// ---------- population: real catalogue data ----------
MXV.valley = {key: 0, period: 1, draw(c, w, h, t, st){
  const V = MX.population && MX.population.valley; if (!V) return;
  const gx = 56, gy = 30, gw = w - gx - 16, gh = h - gy - 48, n = V.counts.length, mx = Math.max(...V.counts);
  const lx = r => gx + (Math.log10(r) - Math.log10(V.edges_re[0])) / (Math.log10(V.edges_re[n]) - Math.log10(V.edges_re[0])) * gw;
  c.fillStyle = 'rgba(255,214,10,.12)'; c.fillRect(lx(1.5), gy, lx(2.0) - lx(1.5), gh);
  mxText(c, 'valley 1.5–2.0 R⊕ (Fulton et al. 2017)', lx(1.5) + 4, gy + 14, {size: 11, color: '#FFD60A'});
  mxAxes(c, gx, gy, gw, gh, {y: 'PLANETS PER BIN (catalogue counts)', x: 'RADIUS (R⊕)'});
  for (let i = 0; i < n; i++){ const x0 = lx(V.edges_re[i]), x1 = lx(V.edges_re[i + 1]), hh = V.counts[i] / mx * (gh - 20); c.fillStyle = '#64D2FF'; c.fillRect(x0 + 0.5, gy + gh - hh, x1 - x0 - 1, hh); }
  for (const r of [0.5, 1, 2, 4, 10, 20]) mxText(c, String(r), lx(r), gy + gh + 14, {size: 11, mono: true, align: 'center'});
  for (const v of [0, Math.round(mx / 2), mx]) mxText(c, String(v), gx - 6, gy + gh - v / mx * (gh - 20) + 4, {size: 11, mono: true, align: 'right'});
  const pm = MX.examples['pi Men c']; if (pm && pm.radius){ const x = lx(pm.radius * 11.209); c.strokeStyle = '#FFB340'; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(x, gy + 20); c.lineTo(x, gy + gh); c.stroke(); c.setLineDash([]); mxText(c, 'pi Men c', x + 4, gy + 30, {size: 11, color: '#FFB340'}); }
}};
function mxSeff(limit, teff){ const [s0, a, b, cc, d] = MX.kopparapu[limit], t = teff - 5780; return s0 + a * t + b * t * t + cc * t ** 3 + d * t ** 4; }
MXV.hz = {key: 0, period: 1, draw(c, w, h, t, st){
  const P = MX.population; if (!P) return;
  const gx = 60, gy = 30, gw = w - gx - 16, gh = h - gy - 48;
  // x: insolation (log, falling to the right like distance from the star); y: stellar temperature.
  const S0 = 3, S1 = 0.1, X = s => gx + (Math.log10(S0) - Math.log10(s)) / (Math.log10(S0) - Math.log10(S1)) * gw, Y = T => gy + gh - (T - 2600) / 4600 * gh;
  mxAxes(c, gx, gy, gw, gh, {y: 'STAR TEMPERATURE (K)', x: 'STARLIGHT RECEIVED (× EARTH)'});
  const band = (a, b, col) => { c.fillStyle = col; c.beginPath(); for (let T = 2600; T <= 7200; T += 50) c.lineTo(X(mxSeff(a, T)), Y(T)); for (let T = 7200; T >= 2600; T -= 50) c.lineTo(X(mxSeff(b, T)), Y(T)); c.closePath(); c.fill(); };
  band('recent_venus', 'early_mars', 'rgba(48,209,88,.10)'); band('runaway_greenhouse', 'maximum_greenhouse', 'rgba(48,209,88,.22)');
  for (const p of P.hz){ c.fillStyle = p[2] ? '#30D158' : 'rgba(48,209,88,.55)'; c.beginPath(); c.arc(X(p[1]), Y(p[0]), 2.6, 0, 2 * Math.PI); c.fill(); }
  c.fillStyle = '#64D2FF'; c.beginPath(); c.arc(X(1), Y(5772), 4.5, 0, 2 * Math.PI); c.fill(); mxText(c, 'Earth', X(1) + 7, Y(5772) - 6, {size: 11, color: '#64D2FF'});
  for (const s of [3, 1, 0.3, 0.1]) mxText(c, String(s), X(s), gy + gh + 14, {size: 11, mono: true, align: 'center'});
  for (const T of [3000, 4000, 5000, 6000, 7000]) mxText(c, T.toLocaleString('en-GB'), gx - 6, Y(T) + 4, {size: 11, mono: true, align: 'right'});
  mxText(c, `dark band: conservative · light: optimistic (Kopparapu et al. 2014) · ${P.hz.length} catalogue planets`, gx + gw, gy - 6, {size: 11, align: 'right'});
}};

// ---------- equations of life ----------
function mxDrakeMC(n, seed, flOrders){
  const rnd = mxRand(seed), ranges = MX.drake_terms.map(([k, , lo, hi]) => k === 'fl' ? [k, -flOrders, 0] : [k, lo, hi]), logs = new Float64Array(n);
  for (let i = 0; i < n; i++){ let s = 0; for (const [, lo, hi] of ranges) s += lo + rnd() * (hi - lo); logs[i] = s; }
  logs.sort();
  const q = f => logs[Math.min(n - 1, Math.floor(f * n))], vars = ranges.map(([k, lo, hi]) => [k, (hi - lo) ** 2 / 12]), tot = vars.reduce((a, v) => a + v[1], 0);
  let below = 0; for (const v of logs) if (v < 0) below++;
  return {logs, median: q(0.5), p05: q(0.05), p95: q(0.95), pLt1: below / n, share: Object.fromEntries(vars.map(([k, v]) => [k, v / tot]))};
}
MXV.drake = {key: 0, period: 1, init(st){ st.opt.fl = 10; st.opt.mc = mxDrakeMC(20000, 42, 10); },
  control(st, el){ if (el.dataset.ctl === 'fl'){ st.opt.fl = Number(el.value); st.opt.mc = mxDrakeMC(20000, 42, st.opt.fl); } },
  draw(c, w, h, t, st){
    const R = st.opt.mc, narrow = w < 600, gx = 50, gy = 30, gw = (narrow ? w : w * 0.62) - gx - 16, gh = narrow ? h * 0.5 - 40 : h - gy - 46;
    const lo = Math.floor(R.logs[0]), hi = Math.ceil(R.logs[R.logs.length - 1]), nb = 60, bins = new Array(nb).fill(0);
    for (const v of R.logs) bins[Math.min(nb - 1, Math.floor((v - lo) / (hi - lo) * nb))]++;
    const mx = Math.max(...bins), X = v => gx + (v - lo) / (hi - lo) * gw;
    mxAxes(c, gx, gy, gw, gh, {y: 'DRAWS', x: 'log10 N'});
    c.fillStyle = 'rgba(48,209,88,.10)'; c.fillRect(X(R.p05), gy, X(R.p95) - X(R.p05), gh);
    for (let i = 0; i < nb; i++){ const hh = bins[i] / mx * (gh - 20); c.fillStyle = (lo + (i + 0.5) * (hi - lo) / nb) < 0 ? '#8E8E93' : '#64D2FF'; c.fillRect(gx + i * gw / nb + 0.5, gy + gh - hh, gw / nb - 1, hh); }
    c.strokeStyle = '#FFB340'; c.beginPath(); c.moveTo(X(R.median), gy); c.lineTo(X(R.median), gy + gh); c.stroke();
    for (const v of [lo, 0, hi]) if (v >= lo && v <= hi) mxText(c, String(v), X(v), gy + gh + 14, {size: 11, mono: true, align: 'center'});
    mxText(c, `median 10^${R.median.toFixed(1)} · 90% in 10^${R.p05.toFixed(1)}–10^${R.p95.toFixed(1)} · P(N < 1) = ${(R.pLt1 * 100).toFixed(0)}%`, gx + 6, gy + 14, {size: 11, mono: true, color: '#F5F5F7'});
    // Each term's share of the spread in log10 N (exact for independent log-uniform terms).
    const tx = narrow ? gx : w * 0.62 + 20, ty = narrow ? gy + gh + 40 : gy, tw = narrow ? w - tx - 20 : w - tx - 20, rows = MX.drake_terms;
    mxText(c, 'SHARE OF THE SPREAD', tx, ty, {size: 11, w: 600, mono: true, color: '#C7C7CC'});
    rows.forEach(([k, label], i) => { const y = ty + 14 + i * 22, f = R.share[k]; c.fillStyle = k === 'fl' || k === 'L' ? '#FF9F0A' : '#64D2FF'; c.fillRect(tx + 70, y, Math.max(1, f * (tw - 120)), 12);
      mxText(c, label.split(' ')[0], tx, y + 10, {size: 11, mono: true}); mxText(c, (f * 100).toFixed(0) + '%', tx + 76 + f * (tw - 120), y + 10, {size: 11, mono: true}); });
  }};
const MX_DRAKE_PRESETS = {
  drake_lo: {R: 1, fp: 0.2, ne: 1, fl: 1, fi: 1, fc: 0.1, L: 1000}, drake_hi: {R: 1, fp: 0.5, ne: 5, fl: 1, fi: 1, fc: 0.2, L: 1e8},
  alt: {R: 10, fp: 0.5, ne: 2, fl: 1, fi: 0.01, fc: 0.01, L: 1e4}, data: {R: 7, fp: 1, ne: 0.37}};
const MX_SEAGER = [['Ns', 'N★ (stars observed)', 1, 6, 30000], ['FQHZ', 'F_Q · F_HZ', -3, 0, 0.15], ['FO', 'F_O (observable)', -5, 0, 0.001], ['FL', 'F_L (life; assumed)', -6, 0, 1], ['FS', 'F_S (detectable gas)', -3, 0, 0.5]];
function mxTermSliders(box, terms, vals, onchange){
  box.innerHTML = terms.map(([k, label, lo, hi]) => `<label class="mxterm"><span>${esc(label)}</span><input type="range" data-k="${k}" min="${lo * 20}" max="${hi * 20}" value="${Math.round(Math.log10(vals[k]) * 20)}" aria-label="${esc(label)}, log scale"><output class="mono" data-o="${k}"></output></label>`).join('');
  const upd = () => { for (const [k] of terms){ const v = Math.pow(10, Number(box.querySelector(`[data-k="${k}"]`).value) / 20); vals[k] = v; box.querySelector(`[data-o="${k}"]`).textContent = v >= 1000 ? Math.round(v).toLocaleString('en-GB') : Number(v.toPrecision(2)).toString(); } onchange(); };
  box.addEventListener('input', upd); upd();
  return v => { for (const k in v){ const el = box.querySelector(`[data-k="${k}"]`); if (el){ el.value = Math.round(Math.log10(v[k]) * 20); } } upd(); };
}
function mxEquationsInit(){
  const box = $('#mxdrake'); if (!box || box.dataset.ready) return; box.dataset.ready = '1';
  const terms = [['R', 'R★ (stars/yr)', 0, 2], ['fp', 'f_p', -1, 0], ['ne', 'n_e', -2, 1], ['fl', 'f_l', -10, 0], ['fi', 'f_i', -6, 0], ['fc', 'f_c', -6, 0], ['L', 'L (years)', 1, 10]];
  const vals = {R: 1, fp: 0.5, ne: 1, fl: 1, fi: 0.01, fc: 0.1, L: 1e4};
  const set = mxTermSliders(box, terms, vals, () => { const N = Object.values(vals).reduce((a, v) => a * v, 1); $('#mxdrakeN').textContent = `N = ${N >= 1 ? Math.round(N).toLocaleString('en-GB') : N.toExponential(1)} (one set of guesses, not a prediction)`; });
  $$('.mxpresets [data-preset]').forEach(b => b.addEventListener('click', () => set(MX_DRAKE_PRESETS[b.dataset.preset])));
  const sv = Object.fromEntries(MX_SEAGER.map(t => [t[0], t[4]]));
  mxTermSliders($('#mxseager'), MX_SEAGER, sv, () => { const N = Object.values(sv).reduce((a, v) => a * v, 1); $('#mxseagerN').textContent = `N = ${N < 10 ? N.toFixed(2) : Math.round(N).toLocaleString('en-GB')} planets with a detectable biosignature gas (on these assumptions)`; });
}

// ---------- molecules: ball-and-stick at measured geometry ----------
const MX_CPK = {H: '#F5F5F7', C: '#8E8E93', N: '#0A84FF', O: '#FF453A', P: '#FF9F0A', S: '#FFD60A', Na: '#BF5AF2', K: '#AF52DE'};
function mxAtoms(g){
  const r = g.r || 1, A = (g.angle || 180) * Math.PI / 180;
  if (g.shape === 'atom') return [[g.atoms[0], 0, 0, 0]];
  if (g.shape === 'diatomic') return [[g.atoms[0], -r / 2, 0, 0], [g.atoms[1], r / 2, 0, 0]];
  if (g.shape === 'linear') return g.r2 ? [[g.atoms[0], -r, 0, 0], [g.atoms[1], 0, 0, 0], [g.atoms[2], g.r2, 0, 0]] : [[g.atoms[0], 0, 0, 0], [g.atoms[1], -r, 0, 0], [g.atoms[2], r, 0, 0]];
  if (g.shape === 'bent' || g.shape === 'dms') return [[g.atoms[0], 0, 0, 0], [g.atoms[1], r * Math.sin(A / 2), -r * Math.cos(A / 2), 0], [g.atoms[2], -r * Math.sin(A / 2), -r * Math.cos(A / 2), 0]];
  if (g.shape === 'pyramidal'){ const cb = Math.sqrt((Math.cos(A) + 0.5) / 1.5), sb = Math.sqrt(1 - cb * cb); return [[g.atoms[0], 0, 0, 0], ...[0, 1, 2].map(i => [g.atoms[i + 1], r * sb * Math.cos(i * 2 * Math.PI / 3), -r * cb, r * sb * Math.sin(i * 2 * Math.PI / 3)])]; }
  if (g.shape === 'tetrahedral'){ const s = r / Math.sqrt(3); return [[g.atoms[0], 0, 0, 0], ...[[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]].map((v, i) => [g.atoms[i + 1], v[0] * s, v[1] * s, v[2] * s])]; }
  return [];
}
MXV.molecule = {key: 0.15, period: 14, init(st){ st.opt.mol = MX.molecules[0]; },
  control(st, el){ if (el.tagName === 'SELECT'){ st.opt.mol = MX.molecules.find(m => m.id === el.value) || MX.molecules[0]; document.querySelectorAll('.mxmol').forEach(a => a.classList.toggle('on', a.dataset.mol === st.opt.mol.id)); } },
  draw(c, w, h, t, st){
    const m = st.opt.mol, atoms = mxAtoms(m.geom), sc = Math.min(w, h) * 0.22, ry = t * 2 * Math.PI, rx = 0.35;
    const stretch = 1 + 0.06 * Math.sin(t * 2 * Math.PI * 12);   // ×10 exaggerated symmetric stretch (≈0.6% in reality)
    const P = atoms.map(([el, x, y, z], i) => { const s = i && atoms.length > 1 ? stretch : 1; x *= s; y *= s; z *= s;
      const x1 = x * Math.cos(ry) + z * Math.sin(ry), z1 = -x * Math.sin(ry) + z * Math.cos(ry), y1 = y * Math.cos(rx) - z1 * Math.sin(rx), z2 = y * Math.sin(rx) + z1 * Math.cos(rx);
      return {el, x: w / 2 + x1 * sc, y: h / 2 - y1 * sc + 10, z: z2}; });
    if (P.length > 1){ c.strokeStyle = 'rgba(255,255,255,.5)'; c.lineWidth = 5; for (let i = 1; i < P.length; i++){ const j = m.geom.shape === 'linear' && m.geom.r2 && i === 2 ? 1 : 0; c.beginPath(); c.moveTo(P[j].x, P[j].y); c.lineTo(P[i].x, P[i].y); c.stroke(); } }
    for (const a of P.slice().sort((p, q) => p.z - q.z)){
      const rad = (a.el === 'H' ? 0.22 : a.el.length > 1 || a.el === 'K' ? 0.5 : 0.34) * sc, col = MX_CPK[a.el] || '#C7C7CC';
      const g = c.createRadialGradient(a.x - rad * 0.3, a.y - rad * 0.3, rad * 0.1, a.x, a.y, rad); g.addColorStop(0, '#FFFFFF'); g.addColorStop(0.35, col); g.addColorStop(1, '#111');
      c.fillStyle = g; c.beginPath(); c.arc(a.x, a.y, rad, 0, 2 * Math.PI); c.fill();
      mxText(c, a.el, a.x, a.y + 4, {size: 11, w: 700, align: 'center', color: a.el === 'H' || a.el === 'S' ? '#000' : '#FFF'});
    }
    mxText(c, `${m.f} · ${m.name}`, 14, 22, {size: 14, w: 600, color: '#F5F5F7'});
    const g = m.geom; mxText(c, g.shape === 'atom' ? 'single atom' : `${g.shape === 'dms' ? 'C–S–C core (hydrogens not drawn)' : g.shape}: bond ${g.r} Å${g.angle ? `, angle ${g.angle}°` : ''} (NIST CCCBDB)`, 14, 40, {size: 11});
    c.strokeStyle = '#C7C7CC'; c.beginPath(); c.moveTo(14, h - 18); c.lineTo(14 + sc, h - 18); c.stroke(); mxText(c, '1 Å', 14 + sc / 2, h - 24, {size: 11, align: 'center'});
    if (P.length > 1) st.exag = 'bond stretch exaggerated ×10; sizes of atoms illustrative';
  }};

// ---------- the section ----------
function mxShowChapter(ch){
  if (!MX) return;
  if (!MX.chapters.includes(ch)) ch = MX.chapters[0];
  $$('#route-methods .mxch').forEach(a => { const on = a.dataset.ch === ch; if (a.hidden === on){ a.hidden = !on; } mxActivate(a, on && current === 'methods'); });
  $$('#route-methods .mxtoc a').forEach(a => { if (a.dataset.ch === ch) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current'); });
  mxCurrent = ch;
  if (ch === 'equations') mxEquationsInit();
}
let mxCurrent = null;
function mxShown(on){ if (!MX) return; $$('#route-methods .mxch').forEach(a => mxActivate(a, on && !a.hidden)); }
function renderMethods(){ /* the chapters are static HTML; stages start when their chapter opens */ }
// The Galaxy's "system view" sheet: the same animated system for any stored example planet.
function mxOpenSystem(name, back){
  const p = MX && MX.examples[name]; if (!p) return;
  let dlg = $('#mxsheet');
  if (!dlg){
    dlg = document.createElement('dialog'); dlg.id = 'mxsheet'; dlg.className = 'mxsheet';
    dlg.innerHTML = `<div class="mxsheethead"><h2 id="mxsheettitle"></h2><button class="btn" type="button" id="mxsheetclose">Close</button></div>
      <figure class="mxstage tall" data-vis="system"><div class="mxcanvas"><canvas role="img"></canvas></div><div class="mxbadges"><span class="mxlabel model">Model from stored values</span><span class="mxexag" aria-live="polite"></span></div>
      <div class="mxctl" role="group" aria-label="Animation controls"><button class="btn mxplay" type="button" aria-pressed="false">Play</button><label class="mxspeed"><span>Speed</span><select><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label><input class="mxscrub" type="range" min="0" max="1000" value="0" aria-label="Time"><button class="btn mxsize" type="button" aria-pressed="false">Planet ×5</button></div>
      <figcaption class="mxdesc" id="mxsheetdesc"></figcaption></figure><p class="mxsheetnote" id="mxsheetnote"></p>`;
    document.body.appendChild(dlg);
    $('#mxsheetclose').addEventListener('click', () => dlg.close());
    dlg.addEventListener('close', () => { const st = dlg.querySelector('.mxstage')._mx; if (st){ st.on = false; } if (dlg._back) dlg._back.focus(); });
  }
  dlg._back = back || null;
  const fig = dlg.querySelector('.mxstage'), S = mxSystemParams(Object.assign({name}, p), name === 'pi Men c' && MX.lead_dip ? {pts: MX.lead_dip.pts} : null);
  $('#mxsheettitle').textContent = name;
  const missing = ['star_teff', 'star_radius', 'radius', 'orbital_period', 'semi_major_axis', 'inclination'].filter(k => p[k] == null);
  const desc = `${name}: a ${Math.round(S.teff)} K star drawn in its blackbody colour, the planet crossing at b = ${S.b.toFixed(2)}, and a limb-darkened model light curve from the stored values.`;
  $('#mxsheetdesc').textContent = desc; fig.querySelector('canvas').setAttribute('aria-label', desc);
  $('#mxsheetnote').textContent = `Stored values from ${MX.source}, fetched ${MX.fetched_at.slice(0, 10)}. ` + (missing.length ? `Not stored: ${missing.join(', ').replace(/_/g, ' ')}; those parts are drawn illustratively and say so. ` : '') +
    (p.inclination != null && S.ars * Math.cos(p.inclination * Math.PI / 180) > 1 + S.k ? 'At the stored inclination this planet does not transit; the view shows a transit to explain the method.' : '');
  const st = mxSetup(fig); st.opt.sys = S; st.t = MXV.system.key; st.on = true;
  if (!dlg.open) dlg.showModal();
  mxDraw(st); if (!mxRM.matches) mxPlay(st, true);
  $('#mxsheetclose').focus();
}
"""


METHODS_CSS = r"""
/* ---------- methods ---------- */
#route-methods{grid-template-columns:minmax(0,1fr)}
#route-methods>*{min-width:0}
.mxtoc ol{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.mxtoc a{display:inline-flex;align-items:center;gap:8px;min-height:44px;padding:0 14px;border-radius:999px;border:1px solid var(--line);background:var(--panel-2);color:var(--ink-2);text-decoration:none;font-size:13px;font-weight:500}
.mxtoc a .mono{font-size:11px;color:var(--ink-3)}
.mxtoc a[aria-current="step"]{background:var(--seg-bg);color:var(--seg-ink);border-color:transparent}
.mxtoc a[aria-current="step"] .mono{color:inherit;opacity:.7}
.mxch{display:grid;gap:16px}
.mxch[hidden]{display:none}
.mxch>header h2{margin:0;font:600 clamp(26px,3.4vw,40px)/1.08 var(--sans);letter-spacing:-.02em}
.mxch>header .eyebrow{margin:0 0 6px}
.mxlede{margin:0;max-width:78ch;font-size:17px;line-height:1.55;color:var(--ink)}
.mxstage{margin:0;display:grid;grid-template-columns:minmax(0,1fr);gap:8px;min-width:0}
.mxch{grid-template-columns:minmax(0,1fr)}
.mxch>*{min-width:0}
.mxcanvas{position:relative;height:clamp(300px,52vh,520px);border-radius:24px;overflow:hidden;background:#000;border:1px solid rgba(255,255,255,.08)}
.mxstage.tall .mxcanvas{height:clamp(420px,66vh,640px)}
.mxcanvas canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.mxbadges{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-width:0}
.mxlabel{padding:4px 10px;border-radius:999px;font:600 11px/1.4 var(--sans);letter-spacing:.02em;border:1px solid}
.mxlabel.ill{color:var(--ink-2);border-color:var(--line-3)}
.mxlabel.model{color:var(--amber);border-color:var(--amber)}
.mxlabel.data{color:var(--green);border-color:var(--green)}
.mxlabel.spec{color:var(--magenta);border-color:var(--magenta)}
.mxexag{min-width:0;padding:4px 10px;border-radius:10px;font:500 11px/1.4 var(--mono);color:var(--ink);background:var(--panel-2);border:1px solid var(--line-2)}
.mxexag[hidden],.mxexag:empty{display:none}
.mxctl{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.mxctl .btn{min-height:44px}
.mxctl label{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)}
.mxctl select{min-height:44px;padding:0 10px;border-radius:12px;border:1px solid var(--line-2);background:var(--panel);color:var(--ink);font:500 14px var(--sans)}
.mxctl input[type=range]{min-height:44px;accent-color:#0A84FF}
.mxscrub{flex:1 1 200px;min-width:0}
.mxeq{display:grid;gap:10px;border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
.mxeqf{margin:0;font-size:16px}
.mxterms{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px 18px}
.mxterm{display:grid;grid-template-columns:110px 1fr 64px;align-items:center;gap:8px;font-size:13px;color:var(--ink-2)}
.mxterm input{min-height:44px;accent-color:#0A84FF;min-width:0}
.mxpresets{display:flex;flex-wrap:wrap;gap:8px}
.mxpresets .btn{min-height:44px}
.mxresult{margin:0;font:600 18px var(--sans)}
.mxknown .kn{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid}
.kn.measured{color:var(--green);border-color:var(--green)}
.kn.constrained{color:var(--amber);border-color:var(--amber)}
.kn.unknown{color:var(--ink-3);border-color:var(--line-3)}
.mxlam input{width:140px}
.mxtogs{display:inline-flex;flex-wrap:wrap;gap:6px}
.mxtog{min-width:44px;justify-content:center}
.mxtog[aria-pressed="true"]{background:var(--btn-bg);color:var(--btn-ink)}
.mxlab input[type=range]{width:140px}
.mxdesc{font-size:13px;color:var(--ink-3);max-width:90ch}
.mxtext{display:grid;gap:12px;max-width:100ch}
.mxtext h3,.mxcheck h3{margin:6px 0 0;font-size:18px}
.mxtext p{margin:0;line-height:1.6;overflow-wrap:anywhere}
.mxtext{min-width:0}
.mxnums{width:100%;border-collapse:collapse;font-size:13px}
.mxnums th,.mxnums td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.mxnums .num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.mxnums td:last-child{color:var(--ink-3)}
.mxcount{margin:0}
.mxyears{margin:0;max-width:520px}
.mxyears svg{width:100%;height:90px;display:block}
.mxyrs{margin:0;display:flex;justify-content:space-between;font:500 11px var(--mono);color:var(--ink-3)}
.mxyears figcaption{font-size:12px;color:var(--ink-3)}
.mxladder{position:relative;height:150px;margin:8px 0 0;border-top:1px solid var(--line)}
.mxladder div{position:absolute;left:var(--x);top:0;height:100%}
.mxladder div i{position:absolute;left:-1px;top:0;width:2px;height:24px;background:var(--cyan)}
.mxladder div:nth-child(odd) span{top:28px}
.mxladder div:nth-child(even) span{top:76px}
.mxladder .mxaxis span{position:static;transform:none}
@media (max-width:499.98px){
  .mxladder{height:auto;border-top:0;display:grid;gap:6px}
  .mxladder div{position:relative;left:0;height:auto;padding-left:calc(var(--x) * 0.6 + 12px)}
  .mxladder div i{top:3px;left:calc(var(--x) * 0.6);height:12px}
  .mxladder div span,.mxladder div:nth-child(odd) span,.mxladder div:nth-child(even) span,.mxladder div.l span,.mxladder div.r span{position:static;transform:none;white-space:normal}
  .mxladder .mxaxis{display:none}
}
.mxladder div span{position:absolute;left:0;transform:translateX(-50%);white-space:nowrap;font-size:12px;color:var(--ink-2)}
.mxladder div.l span{transform:none}
.mxladder div.r span{transform:translateX(-100%)}
.mxladder .mxaxis{position:absolute;left:0;right:0;bottom:0;margin:0;display:flex;justify-content:space-between;font:500 11px var(--mono);color:var(--ink-3)}
.mxsteps{margin:0;padding-left:20px;display:grid;gap:10px;line-height:1.55}
.mxcontrast{display:grid;gap:4px;margin:6px 0}
.mxcontrast ol{list-style:none;margin:0;padding:0;display:grid;gap:2px}
.mxcontrast li,.mxcontrast .ax{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:12px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)}
.mxcontrast .ax{border:0;padding:0}
.mxcontrast .lab{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 8px;font-size:12px;color:var(--ink-3);min-width:0}
.mxcontrast .lab b{color:var(--ink);font-size:13px}
.mxcontrast .lab .mono{color:var(--ink-2)}
.mxcontrast .cond{flex-basis:100%}
.mxcontrast .track{position:relative;height:20px;border-left:1px solid var(--line-2);border-right:1px solid var(--line-2);background:linear-gradient(var(--line-2),var(--line-2)) center/100% 1px no-repeat}
.mxcontrast .ax .track{background:none;border:0;height:16px}
.mxcontrast .ax .track span{position:absolute;top:0;transform:translateX(-50%);font:500 11px var(--mono);color:var(--ink-3);white-space:nowrap}
.mxcontrast .ax .track span:nth-child(even){display:none}
.mxcontrast .track i{position:absolute;top:50%;width:11px;height:11px;margin:-5.5px 0 0 -5.5px;border-radius:50%;background:var(--cyan)}
.mxcontrast li.goal .track i,.mxcontrast li.requirement .track i{background:transparent;border:2px solid var(--cyan)}
.mxcontrast li.target .track i{background:var(--amber)}
.mxmols{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.mxmol{border:1px solid var(--line);border-radius:16px;padding:12px 14px;background:var(--glass-2)}
.mxmol.on{border-color:var(--cyan)}
.mxmol h4{margin:0 0 6px;font-size:16px}
.mxmol h4 span{font-weight:500;color:var(--ink-3);font-size:13px;margin-left:6px}
.mxmol dl{margin:0;display:grid;gap:4px;font-size:12.5px}
.mxmol dt{color:var(--ink-3);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.mxmol dd{margin:0 0 4px}
.mxmol ul{margin:0;padding-left:16px}
.mxcheck{display:grid;gap:10px;border:1px solid var(--line);border-radius:var(--r);padding:16px 18px}
.mxcheck ol{margin:0;padding-left:20px;display:grid;gap:6px}
.mxcheck p{margin:0}
.mxcases{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}
.mxcases article{border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.mxcases h4{margin:0 0 6px}
.mxcases p{font-size:13px;line-height:1.55}
.mxsrc{margin:0;padding-left:18px;display:grid;gap:2px;font-size:12.5px}
.mxsrc a{display:inline-flex;align-items:center;min-height:32px}
.mxsources summary{display:flex;align-items:center;min-height:44px;cursor:pointer;font-weight:600}
.mxnav{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:14px}
.mxnav .btn{min-height:44px}
.mxtimeline{list-style:none;margin:0;padding:0 0 0 18px;border-left:1px solid var(--line-2);display:grid;gap:14px}
.mxpaper{position:relative;display:grid;grid-template-columns:64px 1fr;gap:12px;padding:14px 16px;border:1px solid var(--line);border-radius:16px;background:var(--glass-2)}
.mxpaper::before{content:"";position:absolute;left:-24px;top:22px;width:11px;height:11px;border-radius:50%;background:var(--cyan)}
.mxpaper.own{border-color:var(--amber)}
.mxpaper.own::before{background:var(--amber)}
.mxpaper .yr{font-size:18px;font-weight:600;color:var(--ink)}
.mxpaper h4{margin:2px 0 4px;font:600 15px/1.35 var(--sans)}
.mxpaper p{margin:0;font-size:13px;line-height:1.5}
.mxpaper .au{color:var(--ink-3);font-size:12px}
.mxpaper .why{color:var(--ink-2)}
.mxpaper .links{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:4px}
.mxpaper .links a{display:inline-flex;align-items:center;min-height:44px}
.mxsheet{width:min(920px,calc(100vw - 24px));max-height:calc(100vh - 24px);padding:16px;border-radius:24px;border:1px solid var(--line-2);background:var(--bg-2);color:var(--ink)}
.mxsheet::backdrop{background:rgba(0,0,0,.6);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}
.mxsheethead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.mxsheethead h2{margin:0;font-size:20px}
.mxsheethead .btn{min-height:44px}
.mxsheetnote{margin:8px 0 0;font-size:12.5px;color:var(--ink-3)}
.gxsys{margin-top:4px}
@media (max-width:699.98px){
  .mxcanvas{height:min(62vh,440px)}
  .mxstage.tall .mxcanvas{height:min(76vh,560px)}
  .mxtoc ol{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;padding-bottom:2px}
  .mxtoc ol::-webkit-scrollbar{display:none}
  .mxtoc a{white-space:nowrap}
  .mxpaper{grid-template-columns:1fr}
  /* Numbers tables become cards on a phone: one block per row, the value left-aligned under its name. */
  .mxnums thead{display:none}
  .mxnums,.mxnums tbody,.mxnums tr,.mxnums th,.mxnums td{display:block;width:auto}
  .mxnums tr{padding:10px 0;border-bottom:1px solid var(--line)}
  .mxnums th,.mxnums td{border:0;padding:2px 0;text-align:left}
  .mxnums .num{text-align:left;white-space:normal;font-size:15px;color:var(--ink)}
  .mxnums td:last-child{font-size:12px}
  .mxcontrast li,.mxcontrast .ax{grid-template-columns:1fr}
  .mxcontrast .ax .lab{display:none}
  .mxsrc a{min-height:44px}
}
"""

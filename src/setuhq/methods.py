# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The Methods section: how planets are found, as animated explainers built on stated physics.

Every equation here has a JavaScript twin in :data:`METHODS_JS` (the page draws with it) and a Python
version (the tests check both against closed forms and published numbers). Numbers on the page come
from three places, and say which: the exoplanet.eu catalogue (docs/results/exoplanet_map.json and
docs/results/methods_examples.json), the research atlas's cited values (each with its DOI), or a
calculation from those with the equation shown. Drawings that cannot be to scale say by how much
they are exaggerated. Only the transit chapter is something SetuHQ itself does.
"""

from __future__ import annotations

import functools
import html
import json
import math
from pathlib import Path

from setuhq.objects import obj_link

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


E_CHARGE = 1.602176634e-19   # C (exact, SI 2019)
M_ELECTRON = 9.1093837015e-31  # kg (CODATA 2018)


def cyclotron_mhz(b_gauss: float) -> float:
    """Electron-cyclotron frequency f_ce = eB/(2π m_e), in MHz, for a field in gauss: the highest frequency the
    cyclotron maser emits at a source with that field (Treumann 2006). About 2.8 MHz per gauss."""
    return E_CHARGE * b_gauss * 1e-4 / (2 * math.pi * M_ELECTRON) / 1e6


def field_for_mhz(f_mhz: float) -> float:
    """The field (gauss) whose cyclotron frequency is f_mhz: the least field at a source emitting up to f_mhz."""
    return f_mhz / cyclotron_mhz(1.0)


def pulsar_timing_ms(mp_mj: float, a_au: float, mpsr_msun: float = 1.4) -> float:
    """Light-travel-time semi-amplitude of a pulsar tugged by a planet on a circular orbit, in ms:
    (Mp/M_psr) · a / c (Mp ≪ M_psr; sin i taken as 1, so for m sin i this is the amplitude itself)."""
    return mp_mj * GM_JUP / (mpsr_msun * GM_SUN) * a_au * AU / C_LIGHT * 1e3


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


# ---------- blocking starlight: Fraunhofer optics of a circular pupil (the coronagraph-family stage) ----------
# Units: the pupil radius is 1; a focal-plane angle u is in λ/D, so the transform variable is k = π u.
# Every field is radially symmetric, so a 2-D Fourier transform is a Hankel transform (J0 kernel).
def _j0(x: float) -> float:
    """Bessel J0 (rational approximations of Numerical Recipes, |error| < 1e-8); mxJ0 is its twin."""
    ax = abs(x)
    if ax < 8.0:
        y = x * x
        a = 57568490574.0 + y * (-13362590354.0 + y * (651619640.7 + y * (-11214424.18 + y * (77392.33017 + y * -184.9052456))))
        b = 57568490411.0 + y * (1029532985.0 + y * (9494680.718 + y * (59272.64853 + y * (267.8532712 + y))))
        return a / b
    z = 8.0 / ax
    y, xx = z * z, ax - 0.785398164
    a = 1.0 + y * (-0.1098628627e-2 + y * (0.2734510407e-4 + y * (-0.2073370639e-5 + y * 0.2093887211e-6)))
    b = -0.1562499995e-1 + y * (0.1430488765e-3 + y * (-0.6911147651e-5 + y * (0.7621095161e-6 - y * 0.934935152e-7)))
    return math.sqrt(0.636619772 / ax) * (math.cos(xx) * a - z * math.sin(xx) * b)


def _j1(x: float) -> float:
    ax = abs(x)
    if ax < 8.0:
        y = x * x
        a = x * (72362614232.0 + y * (-7895059235.0 + y * (242396853.1 + y * (-2972611.439 + y * (15704.48260 + y * -30.16036606)))))
        b = 144725228442.0 + y * (2300535178.0 + y * (18583304.74 + y * (99447.43394 + y * (376.9991397 + y))))
        return a / b
    z = 8.0 / ax
    y, xx = z * z, ax - 2.356194491
    a = 1.0 + y * (0.183105e-2 + y * (-0.3516396496e-4 + y * (0.2457520174e-5 + y * -0.240337019e-6)))
    b = 0.04687499995 + y * (-0.2002690873e-3 + y * (0.8449199096e-5 + y * (-0.88228987e-6 + y * 0.105787412e-6)))
    v = math.sqrt(0.636619772 / ax) * (math.cos(xx) * a - z * math.sin(xx) * b)
    return -v if x < 0 else v


def bessel_j(n: int, x: float) -> float:
    """J_n(x) for n ≥ 0: J0 and J1 above; higher orders by the power series below x = n + 1 and by upward
    recurrence (stable there) above it."""
    if n == 0:
        return _j0(x)
    if n == 1:
        return _j1(x)
    if abs(x) < n + 1:
        h, s, term = x / 2, 0.0, (x / 2) ** n / math.factorial(n)
        for m in range(30):
            s += term
            term *= -h * h / ((m + 1) * (m + 1 + n))
        return s
    jm, j = _j0(x), _j1(x)
    for k in range(1, n):
        jm, j = j, 2 * k / x * j - jm
    return j


def airy_intensity(u: float) -> float:
    """The clear circular pupil's image, I(u)/I(0) = [2 J1(πu)/(πu)]², u in λ/D (first dark ring at 1.22 λ/D)."""
    k = math.pi * u
    return 1.0 if abs(k) < 1e-9 else (2 * _j1(k) / k) ** 2


def sonine_field(u: float, n: int) -> float:
    """Field of a pupil apodised as A(ρ) = (1 − ρ²)ⁿ, normalised to 1 on axis: 2ⁿ⁺¹ (n+1)! J_{n+1}(πu)/(πu)ⁿ⁺¹
    (the Hankel transform of (1 − ρ²)ⁿ). n = 0 is the clear pupil (the Airy pattern)."""
    k = math.pi * u
    if abs(k) < 1e-6:
        return 1.0
    return 2 ** (n + 1) * math.factorial(n + 1) * bessel_j(n + 1, k) / k ** (n + 1)


def sonine_intensity(u: float, n: int) -> float:
    """The apodised image relative to the clear pupil's peak: its on-axis field is ∫A ρ dρ / ∫ρ dρ = 1/(n+1)."""
    return (sonine_field(u, n) / (n + 1)) ** 2


def sonine_throughput(n: int) -> float:
    """Fraction of the light an apodiser (1 − ρ²)ⁿ transmits: ∫A² ρ dρ / ∫ρ dρ = 1/(2n + 1)."""
    return 1 / (2 * n + 1)


def _simpson(f, a: float, b: float, n: int = 400) -> float:
    n += n % 2
    h = (b - a) / n
    return h / 3 * (f(a) + f(b) + sum((4 if i % 2 else 2) * f(a + i * h) for i in range(1, n)))


def lyot_pupil_field(rho: float, mask_lod: float) -> float:
    """Field in the re-imaged pupil (the Lyot plane) of an ideal Lyot coronagraph with an opaque focal mask of radius
    mask_lod (λ/D), for a unit on-axis beam: the pupil minus the light the mask removed,
    E(ρ) = P(ρ) − ∫₀^{πm} J1(k) J0(kρ) dk. The removed part is smooth, so what remains is bright near the rim."""
    p = 1.0 if rho < 1 else 0.0
    return p - _simpson(lambda k: _j1(k) * _j0(k * rho), 0.0, math.pi * mask_lod, 400)


def lyot_final_intensity(u: float, mask_lod: float, stop: float, n: int = 240) -> float:
    """The final image of the on-axis star, relative to the unblocked star's peak, behind a Lyot stop of radius
    `stop` (in pupil radii): I = [2 ∫₀^s E(ρ) J0(πuρ) ρ dρ]² (the unblocked peak's field is 1/2). The integral is
    split at the rim, where E jumps."""
    k = math.pi * u
    f = lambda r: lyot_pupil_field(r, mask_lod) * _j0(k * r) * r  # noqa: E731
    v = _simpson(f, 0.0, min(stop, 1.0) - 1e-9, n)
    if stop > 1:
        v += _simpson(f, 1.0 + 1e-9, stop, n)
    return (2 * v) ** 2


def sci(x: float) -> str:
    """1.8×10⁻⁷: a number as the stages print it (mxSci in the page)."""
    e = math.floor(math.log10(x))
    m = round(x / 10 ** e, 1)
    if m >= 10:
        m, e = m / 10, e + 1
    return f"{m:.1f}×10" + str(e).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))


MX_LYOT_MASK = 4   # λ/D: the occulting disc drawn in the Lyot scene (MX_CG.lyotMask in the page)


@functools.lru_cache(maxsize=1)
def coronagraph_numbers() -> tuple[float, float, float, float, float]:
    """The figures the Blocking-starlight text quotes: Lyot starlight at 8 λ/D with the stop open (150%) and closed
    (80%), the clear pupil's there, and the brightest ring between 4.5 and 5.5 λ/D for the clear pupil and for the
    (1 − ρ²)² apodiser."""
    ring = lambda f: max(f(4.5 + i / 100) for i in range(101))  # noqa: E731
    return (lyot_final_intensity(8, MX_LYOT_MASK, 1.5), lyot_final_intensity(8, MX_LYOT_MASK, 0.8), airy_intensity(8),
            ring(airy_intensity), ring(lambda u: sonine_intensity(u, 2)))


def vortex_pupil_field(rho: float, charge: int = 2) -> float:
    """Amplitude in the Lyot plane behind an ideal charge-2 vortex phase mask, for a unit on-axis beam on a clear
    circular pupil: 0 inside the pupil and (1/ρ)² outside it (the integral ∫₀^∞ J1(k) J2(kρ) dk), so a Lyot stop
    slightly smaller than the pupil removes all of the star's light. Only charge 2 is drawn."""
    if charge != 2:
        raise ValueError("only the charge-2 vortex is modelled")
    return 0.0 if rho < 1 else 1 / (rho * rho)


# ---------- molecules: normal modes at measured geometry ----------
HBAR = 1.054571817e-34
AMU = 1.66053906660e-27
ATOM_MASS = {"H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "P": 30.974, "S": 32.06}
MODE_DRAW_A = 0.2   # Å: the peak displacement drawn for the atom that moves most, in every mode
# Fundamentals as the atlas M1 table gives them (NIST CCCBDB experimental cm⁻¹ → λ = 10⁴/ν̃ µm). Each mode:
# (label, what moves, µm or None when the atlas lists no position, infrared-active, degeneracy, pattern).
# Degeneracies add up to 3N − 5 (linear) or 3N − 6, which a test checks.
MODES = {
    "H2O": [("ν₁", "symmetric stretch", 2.73, True, 1, "sym"), ("ν₂", "bend", 6.27, True, 1, "bend"),
            ("ν₃", "asymmetric stretch", 2.66, True, 1, "asym")],
    "CO2": [("ν₁", "symmetric stretch", 7.50, False, 1, "sym"), ("ν₂", "bend (two, at right angles)", 15.0, True, 2, "bend"),
            ("ν₃", "asymmetric stretch", 4.26, True, 1, "asym")],
    "CO": [("ν", "stretch", 4.67, True, 1, "stretch")],
    "O2": [("ν", "stretch", 6.43, False, 1, "stretch")],
    "O3": [("ν₁", "symmetric stretch", 9.01, True, 1, "sym"), ("ν₂", "bend", 14.2, True, 1, "bend"),
           ("ν₃", "asymmetric stretch", 9.60, True, 1, "asym")],
    "SO2": [("ν₁", "symmetric stretch", 8.69, True, 1, "sym"), ("ν₂", "bend", 19.3, True, 1, "bend"),
            ("ν₃", "asymmetric stretch", 7.34, True, 1, "asym")],
    "N2O": [("", "N–N stretch, mostly", 4.50, True, 1, "nn"), ("", "N–O stretch, mostly", 7.78, True, 1, "no"),
            ("", "bend (two, at right angles)", 17.0, True, 2, "bend")],
    "NH3": [("ν₁", "symmetric stretch", 3.00, True, 1, "sym"), ("ν₂", "umbrella", 10.5, True, 1, "umbrella"),
            ("ν₃", "asymmetric stretch (two)", 2.90, True, 2, "asym"), ("ν₄", "asymmetric bend (two)", 6.15, True, 2, "abend")],
    "PH3": [("ν₁", "symmetric stretch", 4.30, True, 1, "sym"), ("ν₂", "umbrella", 10.1, True, 1, "umbrella"),
            ("ν₃", "asymmetric stretch (two)", 4.30, True, 2, "asym"), ("ν₄", "asymmetric bend (two)", 8.94, True, 2, "abend")],
    "CH4": [("ν₁", "symmetric stretch", None, False, 1, "sym"), ("ν₂", "bend (two)", None, False, 2, "ebend"),
            ("ν₃", "asymmetric stretch (three)", 3.31, True, 3, "asym"), ("ν₄", "asymmetric bend (three)", 7.66, True, 3, "tbend")],
}


def atom_positions(geom: dict) -> list[tuple[str, float, float, float]]:
    """The ball-and-stick coordinates in Å (mxAtoms in the page is the twin): the first atom is the centre."""
    r, A = geom.get("r", 1.0), math.radians(geom.get("angle", 180))
    a, sh = geom["atoms"], geom["shape"]
    if sh == "atom":
        return [(a[0], 0.0, 0.0, 0.0)]
    if sh == "diatomic":
        return [(a[0], -r / 2, 0.0, 0.0), (a[1], r / 2, 0.0, 0.0)]
    if sh == "linear":
        if geom.get("r2"):
            return [(a[0], -r, 0.0, 0.0), (a[1], 0.0, 0.0, 0.0), (a[2], geom["r2"], 0.0, 0.0)]
        return [(a[0], 0.0, 0.0, 0.0), (a[1], -r, 0.0, 0.0), (a[2], r, 0.0, 0.0)]
    if sh in ("bent", "dms"):
        s, c = r * math.sin(A / 2), r * math.cos(A / 2)
        return [(a[0], 0.0, 0.0, 0.0), (a[1], s, -c, 0.0), (a[2], -s, -c, 0.0)]
    if sh == "pyramidal":
        cb = math.sqrt((math.cos(A) + 0.5) / 1.5)
        sb = math.sqrt(1 - cb * cb)
        return [(a[0], 0.0, 0.0, 0.0)] + [(a[i + 1], r * sb * math.cos(i * 2 * math.pi / 3), -r * cb, r * sb * math.sin(i * 2 * math.pi / 3)) for i in range(3)]
    if sh == "tetrahedral":
        s = r / math.sqrt(3)
        return [(a[0], 0.0, 0.0, 0.0)] + [(a[i + 1], v[0] * s, v[1] * s, v[2] * s) for i, v in enumerate([(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)])]
    return []


def _v(a, b, f=1.0):
    return [a[0] + f * b[0], a[1] + f * b[1], a[2] + f * b[2]]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return [a[0] / n, a[1] / n, a[2] / n]


def _perp(v, b):
    """The part of v at right angles to the unit vector b."""
    return _v(v, b, -_dot(v, b))


def mode_displacements(geom: dict, pattern: str) -> list[list[float]]:
    """A normal-mode displacement pattern: the symmetry-correct sketch named by `pattern`, with every rigid-body
    translation and rotation projected out (mass-weighted, so the centre of mass stays put and there is no net
    spin), scaled so that the atom that moves most moves 1. A sketch, not a force-field calculation."""
    P = atom_positions(geom)
    xyz = [list(p[1:]) for p in P]
    m = [ATOM_MASS[p[0]] for p in P]
    n = len(P)
    b = [_unit(_v(xyz[i], xyz[0], -1)) if i else [0.0, 0.0, 0.0] for i in range(n)]
    z3 = [0.0, 0.0, 0.0]
    d = [z3[:] for _ in range(n)]
    if pattern == "stretch":
        u = _unit(_v(xyz[1], xyz[0], -1))
        d = [[-x for x in u], u]
    elif pattern == "sym":
        d = [z3[:]] + [b[i] for i in range(1, n)]
    elif pattern == "asym":
        coef = {3: [1, -1], 4: [1, -0.5, -0.5], 5: [1, 1, -1, -1]}[n]
        d = [z3[:]] + [[c * x for x in b[i + 1]] for i, c in enumerate(coef)]
    elif pattern == "bend":
        if geom["shape"] == "linear":
            d = [[0.0, 1.0, 0.0] if i != (1 if geom.get("r2") else 0) else z3[:] for i in range(n)]
        else:   # XY2 bent: each outer atom swings towards the other, at right angles to its bond
            d = [z3[:], _unit(_perp(_v(xyz[2], xyz[1], -1), b[1])), _unit(_perp(_v(xyz[1], xyz[2], -1), b[2]))]
    elif pattern == "nn":
        d = [[-1.0, 0, 0], [1.0, 0, 0], z3[:]]
    elif pattern == "no":
        d = [z3[:], [-1.0, 0, 0], [1.0, 0, 0]]
    elif pattern == "umbrella":
        d = [z3[:]] + [[0.0, 1.0, 0.0] for _ in range(n - 1)]
    elif pattern == "abend":
        d = [z3[:], _unit(_perp(_v(xyz[2], xyz[1], -1), b[1])), _unit(_perp(_v(xyz[1], xyz[2], -1), b[2])), z3[:]]
    elif pattern == "ebend":   # one H–C–H angle closes while the opposite one opens
        toward = lambda i, j: _unit(_perp(_v(xyz[j], xyz[i], -1), b[i]))  # noqa: E731
        d = [z3[:], toward(1, 2), toward(2, 1), [-x for x in toward(3, 4)], [-x for x in toward(4, 3)]]
    elif pattern == "tbend":
        d = [z3[:]] + [_perp([1.0, 0.0, 0.0], b[i]) for i in range(1, n)]
    else:
        raise ValueError(pattern)
    # Project out rigid-body motion in mass-weighted coordinates (Gram–Schmidt over 3 translations, 3 rotations).
    M = sum(m)
    com = [sum(m[i] * xyz[i][k] for i in range(n)) / M for k in range(3)]
    rel = [_v(xyz[i], com, -1) for i in range(n)]
    sq = [math.sqrt(x) for x in m]
    flat = lambda vs: [sq[i] * vs[i][k] for i in range(n) for k in range(3)]  # noqa: E731
    rigid = []
    for k in range(3):
        e = [0.0, 0.0, 0.0]
        e[k] = 1.0
        rigid.append(flat([e] * n))
        w = [0.0, 0.0, 0.0]
        w[k] = 1.0
        rigid.append(flat([[w[1] * r[2] - w[2] * r[1], w[2] * r[0] - w[0] * r[2], w[0] * r[1] - w[1] * r[0]] for r in rel]))
    basis = []
    for v in rigid:
        for q in basis:
            c = sum(x * y for x, y in zip(v, q))
            v = [x - c * y for x, y in zip(v, q)]
        nv = math.sqrt(sum(x * x for x in v))
        if nv > 1e-9:
            basis.append([x / nv for x in v])
    q = flat(d)
    for bv in basis:
        c = sum(x * y for x, y in zip(q, bv))
        q = [x - c * y for x, y in zip(q, bv)]
    out = [[q[3 * i + k] / sq[i] for k in range(3)] for i in range(n)]
    top = max(math.sqrt(_dot(o, o)) for o in out) or 1.0
    return [[round(x / top, 6) for x in o] for o in out]


def zero_point_rms(geom: dict, disp: list[list[float]], lam_um: float) -> tuple[float, int]:
    """Root-mean-square zero-point displacement (Å) of the atom that moves most in this mode, and its index: for a
    mass-weighted unit vector L, atom i moves L_i/√m_i · Q with ⟨Q²⟩ = ħ/(2ω) and ω = 2πc/λ."""
    m = [ATOM_MASS[p[0]] * AMU for p in atom_positions(geom)]
    norm = math.sqrt(sum(m[i] * _dot(disp[i], disp[i]) for i in range(len(m))))
    q = math.sqrt(HBAR / (2 * 2 * math.pi * C_LIGHT / (lam_um * 1e-6)))
    amps = [math.sqrt(_dot(disp[i], disp[i])) / norm * q * 1e10 for i in range(len(m))]
    i = max(range(len(m)), key=lambda j: amps[j])
    return amps[i], i


def mode_table(mol: dict) -> list[dict]:
    """The modes the Molecules stage animates, each with its band, its drawn displacement pattern and its stated
    amplitude exaggeration (the drawn peak MODE_DRAW_A against the zero-point RMS of the atom that moves most)."""
    out = []
    for label, name, um, ir, deg, pattern in MODES.get(mol["id"], []):
        disp = mode_displacements(mol["geom"], pattern)
        row = {"nu": label, "name": name, "um": um, "ir": ir, "deg": deg, "disp": disp}
        if um:
            rms, i = zero_point_rms(mol["geom"], disp, um)
            row.update(rms=round(rms, 4), atom=mol["geom"]["atoms"][i], exag=max(1, round(MODE_DRAW_A / rms)))
        out.append(row)
    return out


def mode_options(mol: dict) -> str:
    """The Mode select's options for one molecule (mxModeOptions in the page builds the same)."""
    out = []
    for i, d in enumerate(mode_table(mol)):
        um = f" · {d['um']:.2f} µm" if d["um"] else ""
        out.append(f'<option value="{i}">{html.escape((d["nu"] + " " if d["nu"] else "") + d["name"])}{um}{"" if d["ir"] else " · IR-silent"}</option>')
    return "".join(out)


def mode_band_link(mol_id: str, um: float | None) -> tuple[float, str] | None:
    """The Reading-atmospheres band (BANDS) that a mode's wavelength falls in, if that chapter draws it: same species,
    centre within 0.06 µm."""
    if um is None:
        return None
    f = next((m["f"] for m in MOLECULES if m["id"] == mol_id), None)
    hit = [(lam, note) for sp, lam, note in BANDS if sp == f and abs(lam - um) <= 0.06]
    return hit[0] if hit else None


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
    "treumann06": ("Treumann 2006, A&ARv 13, 229 (the electron-cyclotron maser)", "https://doi.org/10.1007/s00159-006-0001-y"),
    "zarka98": ("Zarka 1998, JGR 103, 20159 (auroral radio emission at the outer planets)", "https://doi.org/10.1029/98JE01323"),
    "zarka07": ("Zarka 2007, Planet. Space Sci. 55, 598 (star–planet plasma interactions and radio)", "https://doi.org/10.1016/j.pss.2006.05.045"),
    "vanhaarlem13": ("van Haarlem et al. 2013, A&A 556, A2 (LOFAR)", "https://doi.org/10.1051/0004-6361/201220873"),
    "turner21": ("Turner et al. 2021, A&A 645, A59 (τ Boötis with LOFAR)", "https://doi.org/10.1051/0004-6361/201937201"),
    "turner24": ("Turner et al. 2024, A&A 688, A66 (LOFAR follow-up of τ Boötis)", "https://doi.org/10.1051/0004-6361/202450095"),
    "vedantham20": ("Vedantham et al. 2020, Nature Astronomy 4, 577 (GJ 1151)", "https://doi.org/10.1038/s41550-020-1011-9"),
    "blancopozo23": ("Blanco-Pozo et al. 2023, A&A 671, A50 (GJ 1151 radial velocities)", "https://doi.org/10.1051/0004-6361/202245053"),
    "pineda23": ("Pineda & Villadsen 2023, Nature Astronomy 7, 569 (YZ Ceti)", "https://doi.org/10.1038/s41550-023-01914-0"),
    "wolszczan92": ("Wolszczan & Frail 1992, Nature 355, 145 (PSR B1257+12)", "https://doi.org/10.1038/355145a0"),
    "isaacson17": ("Isaacson et al. 2017, PASP 129, 054501 (Breakthrough Listen targets)", "https://doi.org/10.1088/1538-3873/aa5800"),
    "price20": ("Price et al. 2020, AJ 159, 86 (Breakthrough Listen: 1,327 nearby stars)", "https://doi.org/10.3847/1538-3881/ab65f1"),
    "triaud09": ("Triaud et al. 2009, A&A 506, 377 (Rossiter–McLaughlin effect of HD 189733 b)", "https://doi.org/10.1051/0004-6361/200911897"),
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


def _catalogue_rows(names: list[str], path: str = "docs/results/exoplanet_catalogue.json") -> dict:
    """Stored values for a few named planets from the catalogue file (empty when it is not in this build)."""
    if not Path(path).exists():
        return {}
    P = json.loads(Path(path).read_text())["planets"]
    idx = {n: i for i, n in enumerate(P["name"]) if n in set(names)}
    return {n: {k: P[k][i] for k in ("mass", "msini", "period", "a", "star")} for n, i in idx.items()}


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


# What the Time scrubber runs through, for its spoken value ("t = 0.42 of the orbit").
TUNIT = {"system": "orbit", "scan": "survey sweep", "cgfam": "sequence", "radio": "orbit", "doppler": "orbit", "wobble": "orbit", "jitter": "sequence",
         "astrometry": "orbit", "lens": "event", "coronagraph": "sequence", "transmission": "transit", "timing": "cycle",
         "falsepos": "orbit", "molecule": "vibration cycle"}


def honesty_label(label: str) -> str:
    """The one badge every drawing carries: illustration, model from stored values, real data, or speculative."""
    lab_cls = {LABEL_ILL: "ill", LABEL_MODEL: "model", LABEL_DATA: "data", LABEL_SPEC: "spec"}[label]
    return f'<span class="mxlabel {lab_cls}">{html.escape(label)}</span>'


def _stage(vis: str, label: str, desc: str, controls: str = "", tall: bool = False, static: bool = False, fid: str = "") -> str:
    """A visual: a canvas with its honesty label, a text description for screen readers, and controls."""
    e = html.escape
    return f"""<figure class="mxstage{' tall' if tall else ''}" data-vis="{vis}"{f' id="{fid}"' if fid else ''}>
          <div class="mxcanvas"><canvas role="img" aria-label="{e(desc)}"></canvas></div>
          <div class="mxbadges">{honesty_label(label)}<span class="mxexag" aria-live="polite"></span></div>
          <div class="mxctl" role="group" aria-label="{'Controls' if static else 'Animation controls'}">
            {'' if static else '<button class="btn mxplay" type="button" aria-pressed="false">Play</button><label class="mxspeed"><span>Speed</span><select><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label><input class="mxscrub" type="range" min="0" max="1000" value="0" aria-label="Time" aria-valuetext="t = 0.00 of the ' + TUNIT.get(vis, "cycle") + '">'}
            {controls}
          </div>
          <figcaption class="mxdesc">{e(desc)}</figcaption>
        </figure>"""


SIZE_BUTTON = '<button class="btn mxsize" type="button" aria-pressed="false">Planet ×5</button>'


def system_stage(fid: str = "", desc: str = "A star and its planet, drawn from stored values.", extra: str = "") -> str:
    """The shared animated system (MXV.system): Methods, the Transit case, the Galaxy's sheet, planet and star pages."""
    return _stage("system", LABEL_MODEL, desc, SIZE_BUTTON + extra, tall=True, fid=fid)


CHAPTERS = [("survey", "How a survey works"), ("transit", "Transit"), ("doppler", "Toward and away"),
            ("rv", "Radial velocity"), ("astrometry", "Astrometry"), ("microlensing", "Microlensing"),
            ("imaging", "Blocking starlight"), ("timing", "Timing and phase"), ("radio", "Radio"), ("falsepos", "False positives"),
            ("spectroscopy", "Reading atmospheres"), ("molecules", "Molecules and life"), ("population", "Population"),
            ("equations", "Equations of life"), ("history", "History and papers")]
DEFAULT_POPULATION = "docs/results/population_stats.json"
# The planets each chapter draws on or names; each links to its canonical page, and each page links back.
CHAPTER_PLANETS = {
    "survey": ["pi Men c"], "transit": ["pi Men c", "TRAPPIST-1 b", "WASP-39 b"], "doppler": ["51 Peg b"],
    "rv": ["51 Peg b", "HD 80606 b", "pi Men c"], "astrometry": ["GJ 896 Ab", "Gaia-4 b"], "microlensing": ["OGLE-2005-BLG-390L b"],
    "imaging": ["HR 8799 b", "HR 8799 c", "HR 8799 d", "HR 8799 e"], "timing": ["Kepler-9 b", "Kepler-9 c", "HD 189733 Ab", "HD 209458 b"],
    "radio": ["tau Boo Ab", "GJ 1151 c", "YZ Cet b", "PSR B1257+12 b", "PSR B1257+12 c", "PSR B1257+12 d"],
    "falsepos": [], "spectroscopy": ["WASP-39 b", "HD 209458 b", "HD 189733 Ab", "K2-18 b"], "molecules": ["K2-18 b", "WASP-39 b"],
    "population": ["pi Men c"], "equations": ["TRAPPIST-1 e", "Proxima Centauri b"],
    "history": ["PSR B1257+12 b", "PSR B1257+12 c", "51 Peg b", "HD 209458 b", "Kepler-9 b"],
}
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
     "bands": "0.76 (A band), 0.69, 0.63; O₂–O₂ pairs at 1.06 and 1.27; the 6.43 µm vibrational fundamental is IR-silent", "who": "Reflected light (future HWO); ground high-resolution at 0.76 µm",
     "seen": [],
     "why": "Earth's most prominent biosignature gas, but only meaningful in context.",
     "abiotic": "CO₂ photolysis around some stars, or massive hydrogen escape after water loss."},
    {"id": "O3", "name": "Ozone", "f": "O₃", "geom": {"shape": "bent", "r": 1.278, "angle": 116.8, "atoms": ["O", "O", "O"]},
     "bands": "0.25 (UV), 0.5–0.7 (Chappuis), 9.65 (strongest mid-IR); fundamentals 9.01, 9.60 and 14.2", "who": "HWO in UV/visible; mid-IR missions such as LIFE at 9.6 µm",
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
     "The mission design of TESS, which began observing in 2018.", "The survey SetuHQ reads.", "#/methods?ch=survey"),
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
            "molecules": [dict({k: m[k] for k in ("id", "name", "f", "geom")}, modes=mode_table(m)) for m in MOLECULES],
            "lab_bands": LAB_BANDS, "jwst": load_jwst(),
            "population": _pop_meta(), "drake_terms": DRAKE_TERMS, "ill_badge": honesty_label(LABEL_ILL), "kopparapu": KOPPARAPU, "tunit": TUNIT}


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
                    ("Sky TESS had observed by 18 Oct 2026", f"{tess_frac * 100:.1f}%" if tess_frac else "—", "computed with tess-point (the Galaxy's coverage panel)")])}
        <p>SetuHQ reads TESS light curves: one star at a time, about 27 days per sector. <a href="#/galaxy?layers=tess">See TESS's sky coverage ›</a></p>
      </div>"""
    ch["transit"] = f"""
      <p class="mxlede">When a planet crosses its star, it blocks a little light. The dip's depth gives the planet's size relative to the star; its repetition gives the period. <b>This is what SetuHQ does</b>: its run found pi Men c's transits in TESS sector 1. <a href="#/transit{('?dip=' + e(lead)) if lead else ''}">Open SetuHQ's Transit case ›</a></p>
      {system_stage("", f"pi Men, a {e(row)}-like star ({pm.get('star_teff', 6037):.0f} K, drawn in its blackbody colour) with pi Men c crossing it at impact parameter {b_pm}. Below, a limb-darkened model light curve drawn from the stored radii, with SetuHQ's stored points for its lead dip overlaid as dots.",
               '<label class="mxb"><span>b</span><input type="range" min="0" max="1000" value="' + str(round(b_pm / (1 + k_ratio) * 1000)) + '" aria-label="Impact parameter"></label>')}
      <div class="mxtext">
        <h3>What shapes the dip</h3>
        <p>The depth is roughly (Rp/R★)². The star is brighter at its centre than its edge (limb darkening), so the bottom of the dip is rounded, not flat, and a central crossing dips deeper than k² (Mandel & Agol 2002; Claret 2017 coefficients for TESS). The four contact points set the total duration T14 and the flat-bottom duration T23 (Winn 2010).</p>
        {_num_rows([("Rp/R★ (k)", f"{k_ratio:.4f}", f"exoplanet.eu Rp = {pm.get('radius')} RJ, R★ = {pm.get('star_radius')} R☉ [calc]"),
                    ("k² (depth with no limb darkening)", f"{k_ratio ** 2 * 1e6:.0f} ppm", "[calc]"),
                    ("Model depth at the stored b", f"{depth_b:.0f} ppm", f"quadratic limb darkening u₁ = {u1:.3f}, u₂ = {u2:.3f} (Claret 2017, {pm.get('star_teff', 6037):.0f} K) [calc]"),
                    ("Model depth for a central crossing", f"{depth0:.0f} ppm", "[calc]"),
                    ("SetuHQ's fitted depth, lead dip", f"{dip['fit_depth_ppm']:.0f} ppm" if dip and dip.get("fit_depth_ppm") else "—", "setuhq run, limb-darkened fit, mid-transit depth (real data)"),
                    ("T14 / T23", f"{t14 * 24:.2f} h / {(t23 or 0) * 24:.2f} h", f"Winn 2010 eqs. 14–15 from a/R★ = {a_rs:.2f}, b = {b_pm} [calc]; Huang 2018 publish 2.953 ± 0.047 h"),
                    ("Star", f"{cls} · ≈{row} · rgb({rgb[0]}, {rgb[1]}, {rgb[2]})", "nearest row of Mamajek's sequence; blackbody colour from the CIE 1931 fit")])}
        <p class="note">The curve is a model drawn from stored values (small-planet approximation of Mandel & Agol 2002, circular orbit), not observed data. The dots are SetuHQ's own stored points for its lead dip. The orbit is not to scale; its tilt is set so the planet crosses at the stored impact parameter.</p>
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
        <p class="note">The drawing is an illustration: its scales are chosen to show the three motions apart, and the planet's wobble is enlarged and labelled. It quotes no Gaia measurement precision: the project's research atlas holds no sourced per-measurement figure for Gaia DR3, so none is given here.</p>
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
    lyot_open, lyot_closed, airy8, airy5, son5 = coronagraph_numbers()
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
        <h3 id="mx-cgfam">Coronagraph families, plane by plane</h3>
        <p>Each family below is drawn as four planes of one optical train. The intensities are computed, not painted: Fraunhofer optics of an ideal, monochromatic telescope with a clear circular pupil, shown on a log stretch from the star's peak down to a millionth. The mask and stop sizes, the apodiser and the planets' brightness are illustrative and say so.</p>
        {lyot_plate()}
      </div>
      {_stage("cgfam", LABEL_ILL, "Four coronagraph families as optical trains, each in four planes with a log-intensity profile below. Lyot: an occulting disc blocks the star's image, the light it diffracts lands on the rim of the re-imaged pupil, and a closing Lyot stop removes that rim so the starlight beside the mask falls by a factor of hundreds. Apodised pupil: the pupil's transmission tapers to its edge, the image's rings fade and the core widens. Vortex: a phase ramp that winds twice around the centre throws all of an on-axis star's light outside the pupil, where the stop removes it. Adaptive optics with angular differential imaging: synthetic frames in which speckles stay fixed while the planet turns with the sky; the median of the frames is subtracted, each frame is turned back and the stack reveals the planet.",
               '<label class="mxmode"><span>Family</span><select><option value="lyot">Lyot: mask and stop</option><option value="apod">Apodised pupil</option><option value="vortex">Vortex phase mask</option><option value="adi">Adaptive optics and ADI</option></select></label>', tall=True)}
      <div class="mxtext">
        <ol class="mxsteps">
          <li><b>Lyot coronagraph.</b> An opaque disc in the focal plane blocks the core of the star's image. What it does not remove is the light its edge diffracts, which the next lens sends to the rim of the re-imaged pupil; a Lyot stop slightly smaller than the pupil catches that rim (Lyot 1939). With a {MX_LYOT_MASK} λ/D disc, closing the stop from 150% to 80% of the pupil cuts the starlight at 8 λ/D from {sci(lyot_open)} to {sci(lyot_closed)} of the star's peak (no coronagraph: {sci(airy8)}) [calc], while a planet well outside the disc keeps 64% of its light, the stop's area.</li>
          <li><b>Apodised pupil.</b> Instead of a mask, the pupil's transmission tapers to its edge, so the image has no sharp edge to ring from. For A(ρ) = (1 − ρ²)² the brightest ring near 5 λ/D falls from {sci(airy5)} to {sci(son5)} of the clear pupil's peak [calc], but only 1/(2n + 1) = 20% of the light gets through and the core is wider. Real apodisers (shaped pupils, prolate and APLC designs) are optimised numerically; this taper is illustrative.</li>
          <li><b>Vortex phase mask.</b> A transparent mask whose phase winds around its centre (e^(2iθ), charge 2) moves an on-axis star's light outside the re-imaged pupil: for an ideal charge-2 vortex on a clear circular aperture the field there is exactly zero inside the pupil and (1/ρ)² outside it [calc], so a stop just inside the pupil removes the star. Phase masks are the family that works closest to the star (Mawet et al. 2012); real vortices leave residuals from wavefront errors and the star's finite size.</li>
          <li><b>Adaptive optics and ADI.</b> A deformable mirror turns the seeing halo into a sharp core, but quasi-static speckles λ/D wide remain. With the instrument's pupil fixed, the sky and the planet turn through the night while the speckles stay; the median of the sequence models the speckles, and each frame minus it, turned back by its field rotation and stacked, keeps the planet (Marois et al. 2006). The frames on the stage are synthetic. On the sky, GPI reaches about 10⁻⁴ raw contrast at 0.4″ in 60 s and more than ten times deeper after an hour of ADI (Bailey et al. 2016).</li>
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
        jwst_note = (f'<p class="note"><b>Real data, cited.</b> {e(jw["citation"])}; data: {e(jw["source"])}, <a href="{e(jw["doi"])}" rel="noopener">Zenodo record {e(jw["doi"].rsplit(".", 1)[-1])}</a>, '
                     f'licence {e(jw["licence"])}. File {e(jw["files"]["spectrum"])}, fetched {e(jw["fetched_at"][:10])}; {e(jw["note"])} The line is the paper\'s best-fit model, not SetuHQ\'s.</p>')
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
      <p class="mxlede">During a transit, a sliver of starlight passes through the planet's atmosphere at its edge. Where molecules absorb, the atmosphere is opaque higher up, so the planet looks slightly bigger at those wavelengths. <b>SetuHQ does not do spectroscopy</b>: this explains how JWST-class telescopes read atmospheres.</p>
      {_stage("transmission", LABEL_ILL, "A planet's limb with its thin atmosphere drawn ten times too thick, starlight passing through it. Two spectrum bars from 0.5 to 5.1 micrometres in false colour: starlight only, and during transit, which gains dark absorption bands at the real positions of sodium, potassium, water, methane, carbon dioxide and carbon monoxide as the planet crosses.", tall=True)}
      <div class="mxtext">
        <p>One scale height H = k_B T/(μ m_H g) of atmosphere changes the transit depth by about 2 H Rp/R★². Strong features span a few scale heights. Hot, puffy, hydrogen-rich planets around small stars give the biggest signals (Seager & Sasselov 2000; Winn 2010).</p>
        {_num_rows([("WASP-39 b scale height (μ = 2.3)", f"{w39_H:.0f} km", f"exoplanet.eu Mp = {w39.get('mass')} MJ, Rp = {w39.get('radius')} RJ; Teq 1116 K (Faedi et al. 2011) [calc]"),
                    ("WASP-39 b: depth change per scale height", f"{w39_dH:.0f} ppm", f"R★ = {w39.get('star_radius')} R☉ [calc]"),
                    ("WASP-39 b: CO₂ at 4.3 µm", "26σ", "JWST ERS Team 2023"),
                    ("pi Men c: per scale height, H₂-rich", f"{pm_dH_h2:.0f} ppm", f"Teq {pm_teq:.0f} K (exoplanet.eu) [calc]"),
                    ("pi Men c: per scale height, steam (μ = 18)", f"{pm_dH_steam:.1f} ppm", "[calc]"),
                    ("pi Men c: SetuHQ's stored transit depth", f"{dip.get('depth_ppm', 0):.0f} ppm" if dip else "—", "setuhq run (real data)")])}
        <p class="note">The bars are schematic: band positions are real (NIST CCCBDB fundamentals and Schwieterman et al. 2018), shapes and strengths are not. False colour: infrared is invisible to the eye. <a href="#/methods?ch=molecules">Which vibration makes each band ›</a></p>
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
    h2o_nu1 = mode_table(MOLECULES[0])[0]
    h2o_rms, h2o_exag = h2o_nu1["rms"], h2o_nu1["exag"]
    ch["molecules"] = f"""
      <p class="mxlede">Each gas absorbs at its own wavelengths. A molecule's shape sets how it vibrates, and its vibrations set where it absorbs in the infrared. No single gas proves life; a biosignature needs context.</p>
      {_stage("molecule", LABEL_ILL, "A rotating ball-and-stick model of the selected molecule at its measured bond lengths and angles (NIST CCCBDB), vibrating in the chosen normal mode: arrows show which way each atom moves. A wavelength axis below marks the molecule's fundamental bands, filled when infrared sees them and hollow when the mode is infrared-silent, with the range the Reading atmospheres chapter draws shaded.",
               '<label class="mxmode"><span>Molecule</span><select>' + "".join(f'<option value="{m["id"]}">{e(m["f"])} · {e(m["name"])}</option>' for m in MOLECULES) + '</select></label>'
               '<label class="mxmode mxvib"><span>Mode</span><select data-ctl="mode">' + mode_options(MOLECULES[0]) + '</select></label>')}
      <div class="mxtext">
        <p>A molecule with N atoms has 3N − 6 ways to vibrate (3N − 5 if it is straight): water has three, carbon dioxide four (its bend comes twice, at right angles), methane nine. A mode absorbs infrared light only if it changes the molecule's dipole. That is why CO₂'s symmetric stretch (7.50 µm), O₂'s stretch and two of methane's four fundamentals are silent in the infrared. The bands the modes make are the ones the Reading atmospheres chapter marks: water's two stretches at 2.66 and 2.73 µm make its 2.7 µm band, methane's ν₃ the 3.3 µm band, CO₂'s asymmetric stretch the 4.26 µm band, and CO's stretch the 4.67 µm band.</p>
        <p class="note">Band positions: the atlas's NIST CCCBDB fundamentals, λ = 10⁴/ν̃. Displacements are symmetry-correct sketches with the centre of mass fixed and no net spin, not a force-field calculation. In every mode the atom that moves most swings {MODE_DRAW_A} Å, and the stage states how much that exaggerates its zero-point motion, the root-mean-square displacement from ħ/2ω at the mode's frequency: for water's hydrogens in ν₁ that is {h2o_rms:.3f} Å, so they are drawn ×{h2o_exag}. Time is slowed 10¹³ to 10¹⁴ times, and the stage gives the factor for each mode.</p>
      </div>
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
    hist += (f'<li class="mxpaper own"><span class="mono yr">{e(run_year or "2026")}</span><div><p class="au">SetuHQ (this project)</p><h4>pi Men c recovered in a blind search of TESS sector 1</h4>'
             f'<p>SetuHQ\'s run found dips at pi Men c\'s period without being told where to look. pi Men c was already known (Huang et al. 2018); this is a recovery, not a discovery.</p>'
             f'<p class="links"><a href="#/transit{("?dip=" + e(lead)) if lead else ""}">Open the Transit case ›</a></p></div></li>')
    ch["history"] = f"""
      <p class="mxlede">Key papers and milestones, summarised in our own words. Each links to its paper (DOI) and to the part of SetuHQ it relates to.</p>
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
                    ("Rossiter–McLaughlin, HD 189733 b", f"{rm_amplitude(3.5, 0.157):.0f} m/s", "K_R ≈ V sin I · k² with V sin I = 3.5 km/s and k = 0.157, both from Gaudi & Winn 2007 Table 1, which lists 88 m/s [calc]"),
                    ("Rossiter–McLaughlin, HD 189733 b (measured V sin I)", f"{rm_amplitude(3.316, 0.15812):.0f} m/s", "V sin I = 3.316 +0.017/−0.067 km/s and k = 0.15812, measured by Triaud et al. 2009 (Table 2) [calc]"),
                    ("Rossiter–McLaughlin, HD 209458 b", f"{rm_amplitude(4.7, 0.121):.0f} m/s", "V sin I = 4.7 km/s, k = 0.121 (Gaudi & Winn 2007 list 70 m/s) [calc]")])}
        <p class="note">SetuHQ measures each dip's time and checks the odd and even dips against each other; it does not fit timing variations, phase curves or eclipses. The secondary-eclipse depth on the canvas is drawn ten times deeper and says so; the TTV amplitude is illustrative. Spin–orbit angles span aligned, polar and retrograde orbits (Albrecht et al. 2022).</p>
      </div>"""

    # ----- radio -----
    cat = _catalogue_rows(["tau Boo Ab", "GJ 1151 c", "YZ Cet b", "PSR B1257+12 b", "PSR B1257+12 c", "PSR B1257+12 d"])
    psr = [(n, cat.get(n) or {}) for n in ("PSR B1257+12 b", "PSR B1257+12 c", "PSR B1257+12 d")]
    psr_rows = [(f"{n}: timing amplitude", f"{pulsar_timing_ms(r['mass'], r['a']):.3g} ms" if r.get("mass") and r.get("a") else "—",
                 f"(Mp/M_psr)·a/c with exoplanet.eu's mass {r.get('mass')} MJ, a = {r.get('a')} AU, sin i = 1, and an assumed 1.4 M☉ pulsar (its mass is not stored) [calc]")
                for n, r in psr]
    stop = next((k + 1 for k, nt in enumerate((g or {}).get("notable") or []) if nt["name"] == "PSR B1257+12 b"), None)
    tour = f' <a href="#/galaxy?tour={stop}">Its card on the Galaxy tour ›</a>' if stop else ""
    tb, yz = cat.get("tau Boo Ab") or {}, cat.get("YZ Cet b") or {}
    claim = lambda status, cls, who, body, refs: (f'<article class="mxclaim"><p class="mxstatus {cls}">{e(status)}</p><h4>{who}</h4><p>{body}</p>'
                                                  f'<p class="small">{" · ".join(f"<a href={chr(34)}{e(SOURCES[k][1])}{chr(34)} rel={chr(34)}noopener{chr(34)}>{e(SOURCES[k][0].split(chr(44))[0])}</a>" for k in refs)}</p></article>')
    ch["radio"] = f"""
      <p class="mxlede">Magnetised planets shine at radio wavelengths: electrons spiralling down field lines into the auroral zones emit by the cyclotron maser, beamed in a hollow cone, up to the local cyclotron frequency (Zarka 1998; Treumann 2006). A close-in planet can also drive such emission on its star, as Io does on Jupiter (Zarka 2007). <b>No exoplanet's own radio emission has been confirmed.</b> Every claim below is tentative or contested, and says so.</p>
      {_stage("radio", LABEL_ILL, "Two scenes. Planet aurora: a planet's magnetic field lines, with emission beamed in a hollow cone from its pole; when the cone sweeps across the observer, a burst appears in the dynamic spectrum below, reaching up to the cyclotron frequency set by the field. Star–planet interaction: the planet orbits inside its star's magnetic field, a flux tube links it to the star, and the emission comes from the star's footpoint. The field slider sets the cyclotron cut-off, computed as 2.8 MHz per gauss.",
               '<label class="mxmode"><span>Scene</span><select><option value="aurora">Planet aurora</option><option value="spi">Star–planet interaction</option></select></label>'
               '<label class="mxbfield"><span>Field at the source</span><input type="range" min="0" max="1000" value="' + str(round((math.log10(7.5) + 1) / 4.5 * 1000)) + '" aria-label="Magnetic field at the emitting source, log scale from 0.1 gauss to 3 kilogauss" aria-valuetext="7.5 gauss, cyclotron cut-off ' + f"{cyclotron_mhz(7.5):.1f}" + ' MHz"></label>')}
      <div class="mxtext">
        <h3>The frequency scale</h3>
        <p>The cyclotron maser emits at, and just below, f_ce = eB/(2π m_e) ≈ {cyclotron_mhz(1):.2f} MHz per gauss of field at the source, so the highest frequency seen gives the field there. A weak planetary field emits below tens of MHz, where only low-frequency arrays such as LOFAR (10–240 MHz; van Haarlem et al. 2013) can listen; an M dwarf's kilogauss field reaches GHz.</p>
        {_num_rows([("Cyclotron frequency per gauss", f"{cyclotron_mhz(1):.3f} MHz", "eB/(2π m_e) with SI 2019 e and CODATA 2018 m_e [calc]"),
                    ("τ Boötis, tentative bursts at 14–21 MHz", f"≥ {field_for_mhz(14):.1f}–{field_for_mhz(21):.1f} G", "least field at the source for that band, if it is cyclotron emission (Turner et al. 2021 band) [calc]"),
                    ("YZ Ceti bursts at 2–4 GHz", f"≥ {field_for_mhz(2000) / 1000:.2f}–{field_for_mhz(4000) / 1000:.2f} kG", "least field at the source, on the star (Pineda & Villadsen 2023 band) [calc]"),
                    ("LOFAR band", "10–240 MHz", "van Haarlem et al. 2013"),
                    ("τ Boo Ab, stored mass and period", f"{tb.get('mass')} MJ · {tb.get('period')} d", "exoplanet.eu"),
                    ("YZ Cet b, stored m sin i and period", f"{yz.get('msini')} MJ · {yz.get('period')} d", "exoplanet.eu")])}
        <h3>The claims, and where they stand</h3>
        <div class="mxclaims">
          {claim("Tentative, not confirmed", "tent", "τ Boötis b · LOFAR", "Circularly polarised bursty emission at 14–21 MHz, about 3σ, with nothing in the off-beams; a slowly varying 21–30 MHz signal was also reported, with the authors' own doubts (Turner et al. 2021). Follow-up LOFAR observations covering 70% of the orbit, including the earlier orbital phases, showed no bursty or slow emission (Turner et al. 2024).", ["turner21", "turner24"])}
          {claim("Contested: no planet yet explains it", "cont", "GJ 1151 · LOFAR", "Low-frequency emission from a quiet red dwarf, with the character of a planetary aurora, interpreted as the star interacting with an Earth-size planet on a 1–5 day orbit (Vedantham et al. 2020). Radial velocities then found a planet on a 390-day orbit that is very unlikely to be the source, and no short-period planet (minimum mass below 1.2 Earth masses) (Blanco-Pozo et al. 2023).", ["vedantham20", "blancopozo23"])}
          {claim("Candidate", "cand", "YZ Ceti · VLA", "Coherent bursts at 2–4 GHz, two of them at similar orbital phases of YZ Ceti b, which could plausibly power them; stellar activity is not ruled out, so YZ Ceti is a candidate star–planet-interaction system (Pineda & Villadsen 2023).", ["pineda23"])}
        </div>
        <h3>Radio found the first planets, another way</h3>
        <p>In 1992, Wolszczan and Frail found planets around the millisecond pulsar PSR B1257+12 from the regular wobble in its pulses' arrival times (Wolszczan & Frail 1992): the planets tug the pulsar, and the light-travel time changes by milliseconds. That is radio timing, not radio from a planet.{tour}</p>
        {_num_rows(psr_rows)}
        <section class="mxseti" aria-labelledby="h-mxseti"><p class="mxstatus seti">Not an exoplanet detection method</p>
          <h4 id="h-mxseti">Technosignature searches (SETI)</h4>
          <p>These look for engineered signals, not for planets or their aurorae, and are kept separate here. Breakthrough Listen observed 1,327 nearby stars at 1.10–3.45 GHz with Green Bank and Parkes and, after excluding terrestrial interference, found zero candidates; the upper limits on a transmitter's power are 2×10¹² W and 9×10¹² W (Price et al. 2020; targets from Isaacson et al. 2017).</p></section>
        <p class="note">SetuHQ does not observe in radio. The scene is an illustration: field lines, cone and orbit are not to scale, and burst times are illustrative; only the cut-off frequency is computed.</p>
      </div>"""

    # ----- false positives -----
    ch["falsepos"] = f"""
      <p class="mxlede">Many transit-like dips are not planets on the target star. A dip is evidence; vetting asks what else could make it. This is where SetuHQ's own checks live.</p>
      {_stage("falsepos", LABEL_ILL, "Five ways to fake a planet, each with its sky geometry on a grid of TESS pixels (21 arcseconds each, drawn to scale) and the light curve it makes: an eclipsing binary with a V-shaped grazing eclipse; a background eclipsing binary diluted by the target's light; a hierarchical triple; odd and even eclipses of different depth when the period is half the true one; and an instrumental jump such as a momentum dump.",
               '<label class="mxmode"><span>Scenario</span><select><option value="eb">Eclipsing binary (grazing, V-shaped)</option><option value="beb">Background eclipsing binary</option><option value="heb">Hierarchical triple</option><option value="oddeven">Odd and even depths differ</option><option value="sys">Systematics</option></select></label>', tall=True)}
      <div class="mxtext">
        <h3>How often, and what SetuHQ checks</h3>
        {_num_rows([("Kepler candidates that were false positives", "9.4%", "overall; 17.7% for giants (Fressin et al. 2013)"),
                    ("TESS prime-mission TOIs found false by follow-up", "565 of 2,241 (≈25%)", "Guerrero et al. 2021"),
                    ("A 50% binary eclipse diluted 1,000 times", f"{diluted_depth(0.5, 1e-3) * 1e6:.0f} ppm", "δ_obs = δ_true · F_target/F_total [calc]: the depth of a small planet"),
                    ("pi Men c's shape, T23/T14", f"{(t23 or 0) / t14:.2f}", "flat-bottomed (U), not V [calc from the transit chapter]")])}
        <p>SetuHQ's vetting flags, from the light curve alone: <code>odd_even_mismatch</code> (odd and even depths differ), <code>secondary_eclipse</code> (a dip at phase 0.5), <code>low_snr</code>, <code>too_short</code>, <code>edge_event</code> and <code>insufficient_points</code>. It has no pixel-level centroid or difference-image check and no statistical validation, so a blended background binary can pass. <a href="#/sentinels">See the reviewers ›</a> · <a href="#/transit">See a vetted case ›</a></p>
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
        "timing": ["holman", "agol", "greene", "deming05", "knutson", "gaudiwinn", "triaud09", "albrecht", "winn"],
        "radio": ["treumann06", "zarka98", "zarka07", "vanhaarlem13", "turner21", "turner24", "vedantham20", "blancopozo23", "pineda23", "wolszczan92", "isaacson17", "price20"],
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
    tags = {"transit": "SetuHQ does this", "spectroscopy": "explainer: SetuHQ does not do this"}
    sections = []
    for i, (cid, title) in enumerate(CHAPTERS):
        prev = CHAPTERS[i - 1] if i else None
        nxt = CHAPTERS[i + 1] if i + 1 < len(CHAPTERS) else None
        cnt = count_line(METHOD_OF[cid]) if cid in ("transit", "rv") else ""
        pls = CHAPTER_PLANETS.get(cid) or []
        planets = (f'<div class="pllinks mxplanets"><span>Planets in this chapter</span>{"".join(obj_link("planet", n, n + " ›") for n in pls)}</div>' if pls else "")
        srcs = f'<details class="mxsources"><summary>Sources</summary><ul class="mxsrc">{_src(sources[cid])}</ul></details>' if sources[cid] else ""
        nav = (f'<nav class="mxnav" aria-label="Chapters">'
               + (f'<a class="btn" href="#/methods?ch={prev[0]}">‹ {e(prev[1])}</a>' if prev else "<span></span>")
               + (f'<a class="btn primary" href="#/methods?ch={nxt[0]}">{e(nxt[1])} ›</a>' if nxt else "") + "</nav>")
        sections.append(f'<article class="mxch" id="mx-{cid}" data-ch="{cid}" aria-labelledby="h-mx-{cid}" hidden>'
                        f'<header><p class="eyebrow">Chapter {i + 1} of {len(CHAPTERS)}{(" · " + e(tags[cid])) if cid in tags else ""}</p>'
                        f'<h2 id="h-mx-{cid}">{e(title)}</h2></header>{ch[cid]}{cnt}{planets}{srcs}{nav}</article>')
    return f"""<header class="headrow">
        <div>{eyebrow}<h1 class="lead-h" id="h-methods" tabindex="-1">How planets are found.<br><span class="grey">And how SetuHQ finds them.</span></h1>
        <p>{len(CHAPTERS)} chapters, each an animated explainer with its physics and sources. Every drawing says whether it is an illustration, a model from stored values, or real data, and by how much it is exaggerated. Only the transit chapter is something SetuHQ itself does.</p></div>
      </header>
      <nav class="mxtoc" aria-label="Methods chapters"><ol>{toc}</ol></nav>
      {''.join(sections)}
      {_data_dates(ex, g)}"""


def _data_dates(ex: dict, g: dict | None) -> str:
    """One line with every dataset the chapters draw from and the date each was fetched."""
    e = html.escape
    parts = []
    if ex.get("fetched_at"):
        parts.append(f"planet examples from {e(ex.get('source', 'exoplanet.eu'))}, fetched {e(ex['fetched_at'][:10])}")
    if g:
        parts.append(f"survey counts from {e(g['source_short'])}, fetched {e(g['fetched_at'][:10])}")
    pop = load_population()
    if pop:
        parts.append(f"population statistics from {e(pop['source'])}, fetched {e(pop['fetched_at'][:10])}")
    jw = load_jwst()
    if jw:
        parts.append(f"the WASP-39 b JWST extract from Zenodo record {e(jw['doi'].rsplit('.', 1)[-1])}, fetched {e(jw['fetched_at'][:10])}")
    return f'<p class="note mxdates"><b>Data and fetch dates:</b> {"; ".join(parts)}.</p>' if parts else ""


SPEC_WINDOW = (0.5, 5.1)   # µm: the range the Reading-atmospheres chapter draws


def _mode_items(m: dict) -> str:
    """One line per vibration: its band, whether infrared sees it, and where that band is in Reading atmospheres."""
    e = html.escape
    rows = []
    for d in mode_table(m):
        name = (d["nu"] + " " if d["nu"] else "") + d["name"]
        ir = "infrared-active" if d["ir"] else "infrared-silent (the dipole does not change)"
        if d["um"] is None:
            where, band = "no wavelength in the atlas", ""
        else:
            band = f'{d["um"]:.2f} µm · '
            link = mode_band_link(m["id"], d["um"])
            if link:
                where = f'<a href="#/methods?ch=spectroscopy">the {link[0]:g} µm band in Reading atmospheres ›</a>'
            elif SPEC_WINDOW[0] <= d["um"] <= SPEC_WINDOW[1]:
                where = "not drawn in Reading atmospheres"
            else:
                where = f"beyond the {SPEC_WINDOW[0]}–{SPEC_WINDOW[1]} µm window of Reading atmospheres"
        exag = f' · drawn ×{d["exag"]}' if d.get("exag") else ""
        rows.append(f'<li data-um="{d["um"] if d["um"] is not None else ""}"><b>{e(name)}</b> · {band}{e(ir)}{exag} · {where if "<a " in where else e(where)}</li>')
    return f'<ul class="mxmodes">{"".join(rows)}</ul>' if rows else ""


def _molecule_card(m: dict) -> str:
    e = html.escape
    seen = "".join(f'<li>{e(t)} (<a href="{e(SOURCES[k][1])}" rel="noopener">{e(SOURCES[k][0].split(",")[0])}</a>)</li>' for t, k in m["seen"]) or "<li>None in exoplanets so far.</li>"
    g = m["geom"]
    geo = ("an atom" if g["shape"] == "atom" else f"{g['shape']}, bond {g['r']} Å" + (f", angle {g['angle']}°" if g.get("angle") else ""))
    modes = _mode_items(m)
    vib = f"<dt>Vibrations</dt><dd>{modes}</dd>" if modes else ""
    return (f'<article class="mxmol" data-mol="{m["id"]}"><h4>{e(m["f"])} <span>{e(m["name"])}</span></h4>'
            f'<dl><dt>Geometry</dt><dd>{e(geo)} (CCCBDB)</dd><dt>Bands (µm)</dt><dd>{e(m["bands"])}</dd>{vib}<dt>Seen by</dt><dd>{e(m["who"])}</dd>'
            f'<dt>Exoplanet detections</dt><dd><ul>{seen}</ul></dd><dt>Why it matters</dt><dd>{e(m["why"])}</dd>'
            f'<dt>Without life?</dt><dd>{e(m["abiotic"])}</dd></dl></article>')


PLATE_DESC = ("Stylised plate of Lyot's coronagraph, in order: parallel starlight enters an objective lens and is focused onto a "
              "small opaque occulting disc, which blocks the star's image; a field lens re-images the telescope's pupil, where the "
              "light the disc diffracted lands on the pupil's rim; a slightly smaller Lyot stop removes that rim; a camera lens forms "
              "the final image, in which a faint companion's light, which missed the disc, survives. Insets show the star's image "
              "with the disc, the pupil with its bright rim inside the stop, and the final image with the companion.")


def _plate_svg(vertical: bool) -> str:
    """One drawing of the plate. Geometry is written along the optical axis (s) and across it (q); the wide plate draws
    s to the right, the phone's plate draws it downwards, so both say the same thing at a legible size."""
    ax = 130
    pt = (lambda s_, q: f"{q:.1f} {s_:.1f}") if vertical else (lambda s_, q: f"{s_:.1f} {q:.1f}")  # noqa: E731
    path = lambda cls, pts: f'<path class="{cls}" d="M' + "L".join(pt(*xy) for xy in pts) + '"/>'  # noqa: E731
    star = "".join(path("st", [(20, y), (110, y), (250, ax + (y - ax) * 0.1)]) for y in (82, 106, 154, 178))
    diff = "".join(path("df", [(250, ax + k * 6), (330, ax + k * 40), (470, ax + k * 38)]) for k in (-1, 1))
    comp = (path("cp", [(20, 62), (110, 83), (250, 104), (330, 112), (470, 100), (560, 98), (690, 112)])
            + path("cp", [(20, 156), (110, 177), (250, 104), (330, 128), (470, 160), (560, 162), (690, 112)]))

    def lens(x, h):
        a_, b_, c_ = pt(x, ax - h), pt(x + 12, ax), pt(x, ax + h)
        d_ = pt(x - 12, ax)
        return f'<path class="ln" d="M{a_}Q{b_} {c_}Q{d_} {a_}Z"/>'

    disc = (f'<rect x="{ax - 7}" y="246" width="14" height="8" rx="4" class="disc"/>' if vertical
            else f'<rect x="246" y="{ax - 7}" width="8" height="14" rx="4" class="disc"/>') + path("rod", [(250, ax - 7), (250, 66)])
    stop = path("stop", [(470, 40), (470, ax - 32)]) + path("stop", [(470, ax + 32), (470, 220)])
    det = path("det", [(690, 70), (690, 190)])
    names = [(110, "A · objective"), (250, "B · occulting disc"), (330, "C · field lens"), (470, "D · Lyot stop"), (560, "E · camera lens"), (690, "F · image")]
    if vertical:   # labels to the right of the train, insets beside the planes they show
        labs = "".join(f'<text x="232" y="{s_ + 4}">{t}</text>' for s_, t in names)
        labs += '<text x="58" y="16" text-anchor="middle">companion</text><text x="182" y="16" text-anchor="middle">starlight</text>'
        ins = lambda s_, body, t: (f'<g transform="translate(290 {s_ + 30})"><circle r="24" class="im"/>{body}<circle r="24" class="fr"/></g>'  # noqa: E731
                                   f'<text x="290" y="{s_ + 68}" text-anchor="middle" class="sm">{t.split(": ")[1]}</text>')
        size, frame = 'viewBox="0 0 360 770"', '<rect x="4" y="4" width="352" height="762" rx="10" class="pf"/>'
    else:
        labs = "".join(f'<text x="{s_}" y="{56 if i % 3 == 1 or s_ == 690 else 30}" text-anchor="middle">{t}</text>' for i, (s_, t) in enumerate(names))
        labs += '<text x="34" y="56" text-anchor="start">companion</text><text x="34" y="196" text-anchor="start">starlight</text>'
        ins = lambda s_, body, t: (f'<g transform="translate({s_} 258)"><circle r="27" class="im"/>{body}<circle r="27" class="fr"/></g>'  # noqa: E731
                                   f'<text x="{s_}" y="302" text-anchor="middle" class="sm">{t}</text>')
        size, frame = 'viewBox="0 0 760 312"', '<rect x="4" y="4" width="752" height="304" rx="10" class="pf"/><rect x="10" y="10" width="740" height="292" rx="6" class="pf2"/>'
    insets = (ins(250, '<circle r="18" class="g2"/><circle r="11" class="g1"/><circle r="5.5" class="g0"/><circle r="8" class="blk"/>', "B: star image, disc on it")
              + ins(470, '<circle r="18" class="rim"/><circle r="14.5" class="blk"/><circle r="13.5" class="stp"/>', "D: bright rim; stop inside")
              + ins(690, '<circle r="12" class="g3"/><circle r="2.6" cx="-9" cy="-8" class="pl"/>', "F: the companion survives"))
    return (f'<svg class="{"v" if vertical else "h"}" {size} role="img" aria-label="{html.escape(PLATE_DESC)}">{frame}'
            f'{path("axis", [(20, ax), (720, ax)])}{star}{diff}{comp}{lens(110, 66)}{lens(330, 70)}{lens(560, 52)}{disc}{stop}{det}{labs}{insets}</svg>')


def lyot_plate() -> str:
    """A stylised plate of Lyot's coronagraph: the optical train, with what each plane would show. Plain SVG drawn in
    the page's ink, so it follows both themes; the inset 'images' are dark, as images of the sky are. A wide drawing for
    the desktop and a vertical one for a phone, so the labels stay legible."""
    return f"""<figure class="mxplate">
          {_plate_svg(False)}{_plate_svg(True)}
          <div class="mxbadges">{honesty_label(LABEL_ILL)}<span class="mxexag">not to scale; after Lyot 1939</span></div>
          <figcaption class="mxdesc">Plate: Lyot's coronagraph (1930), stylised. Starlight (amber) is stopped at the disc (B); the light the disc's edge diffracts (dashed) reaches the rim of the pupil image and is caught by the stop (D); a companion's light (blue) misses the disc and passes. Ray paths are schematic.</figcaption>
        </figure>"""


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
    return (f'<div class="mxcontrast" role="figure" aria-label="Contrast ladder on a log scale from 1e-2 to 1e-11: '
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

// ---------- blocking starlight: Fraunhofer optics of a circular pupil (coronagraph families) ----------
// The pupil radius is 1 and a focal-plane angle u is in λ/D, so the transform variable is k = πu. Fields are
// radially symmetric, so each 2-D Fourier transform is a Hankel transform with a J0 kernel.
function mxJ0(x){
  const ax = Math.abs(x);
  if (ax < 8){ const y = x * x;
    return (57568490574.0 + y * (-13362590354.0 + y * (651619640.7 + y * (-11214424.18 + y * (77392.33017 + y * -184.9052456))))) /
      (57568490411.0 + y * (1029532985.0 + y * (9494680.718 + y * (59272.64853 + y * (267.8532712 + y))))); }
  const z = 8 / ax, y = z * z, xx = ax - 0.785398164;
  const a = 1 + y * (-0.1098628627e-2 + y * (0.2734510407e-4 + y * (-0.2073370639e-5 + y * 0.2093887211e-6)));
  const b = -0.1562499995e-1 + y * (0.1430488765e-3 + y * (-0.6911147651e-5 + y * (0.7621095161e-6 - y * 0.934935152e-7)));
  return Math.sqrt(0.636619772 / ax) * (Math.cos(xx) * a - z * Math.sin(xx) * b);
}
function mxJ1(x){
  const ax = Math.abs(x);
  if (ax < 8){ const y = x * x;
    return x * (72362614232.0 + y * (-7895059235.0 + y * (242396853.1 + y * (-2972611.439 + y * (15704.48260 + y * -30.16036606))))) /
      (144725228442.0 + y * (2300535178.0 + y * (18583304.74 + y * (99447.43394 + y * (376.9991397 + y))))); }
  const z = 8 / ax, y = z * z, xx = ax - 2.356194491;
  const a = 1 + y * (0.183105e-2 + y * (-0.3516396496e-4 + y * (0.2457520174e-5 + y * -0.240337019e-6)));
  const b = 0.04687499995 + y * (-0.2002690873e-3 + y * (0.8449199096e-5 + y * (-0.88228987e-6 + y * 0.105787412e-6)));
  const v = Math.sqrt(0.636619772 / ax) * (Math.cos(xx) * a - z * Math.sin(xx) * b);
  return x < 0 ? -v : v;
}
function mxJn(n, x){
  if (n === 0) return mxJ0(x); if (n === 1) return mxJ1(x);
  if (Math.abs(x) < n + 1){ const h = x / 2; let f = 1; for (let i = 2; i <= n; i++) f *= i; let term = Math.pow(h, n) / f, s = 0;
    for (let m = 0; m < 30; m++){ s += term; term *= -h * h / ((m + 1) * (m + 1 + n)); } return s; }
  let jm = mxJ0(x), j = mxJ1(x); for (let k = 1; k < n; k++){ const t = 2 * k / x * j - jm; jm = j; j = t; } return j;
}
const mxAiry = u => { const k = Math.PI * u; return Math.abs(k) < 1e-9 ? 1 : (2 * mxJ1(k) / k) ** 2; };
function mxSonine(u, n){ const k = Math.PI * u; if (Math.abs(k) < 1e-6) return 1; let f = 1; for (let i = 2; i <= n + 1; i++) f *= i; return Math.pow(2, n + 1) * f * mxJn(n + 1, k) / Math.pow(k, n + 1); }
const mxSonineI = (u, n) => (mxSonine(u, n) / (n + 1)) ** 2;
function mxSimpson(f, a, b, n){ n += n % 2; const h = (b - a) / n; let s = f(a) + f(b); for (let i = 1; i < n; i++) s += (i % 2 ? 4 : 2) * f(a + i * h); return s * h / 3; }
// The Lyot plane: the pupil minus what the occulting mask (radius m λ/D) removed. Bright at the rim.
function mxLyotPupil(rho, m){ return (rho < 1 ? 1 : 0) - mxSimpson(k => mxJ1(k) * mxJ0(k * rho), 0, Math.PI * m, 400); }
// Tabulated once per mask (inside and outside the rim, where the field jumps), then the final image for any stop:
// I(u) = [2 ∫₀^s E(ρ) J0(πuρ) ρ dρ]², relative to the unblocked star's peak.
function mxLyotTable(m){
  const A = [], B = [], NA = 300, NB = 100;
  for (let i = 0; i <= NA; i++){ const r = i / NA * (1 - 1e-9); A.push([r, mxLyotPupil(r, m)]); }
  for (let i = 0; i <= NB; i++){ const r = 1 + 1e-9 + i / NB * 0.5; B.push([r, mxLyotPupil(r, m)]); }
  return {m, A, B};
}
function mxLyotFinal(T, u, s){
  const k = Math.PI * u, seg = (P, lim) => { let v = 0; for (let i = 1; i < P.length && P[i - 1][0] < lim; i++){
    const r0 = P[i - 1][0], r1 = Math.min(lim, P[i][0]), e1 = P[i - 1][1] + (P[i][1] - P[i - 1][1]) * (r1 - r0) / (P[i][0] - r0);
    v += 0.5 * (r1 - r0) * (P[i - 1][1] * mxJ0(k * r0) * r0 + e1 * mxJ0(k * r1) * r1); } return v; };
  const v = seg(T.A, Math.min(s, 1)) + (s > 1 ? seg(T.B, s) : 0);
  return (2 * v) ** 2;
}
// The ideal charge-2 vortex: no light inside the re-imaged pupil, (1/ρ)² outside it (methods.py: vortex_pupil_field).
const mxVortexPupil = rho => rho < 1 ? 0 : 1 / (rho * rho);
// Synthetic ADI (seeded with mxRand, below): quasi-static speckles fixed to the instrument, a planet turning with the sky. The median of the
// sequence models the speckles; each frame minus the median, turned back by its field rotation and averaged,
// keeps the planet (Marois et al. 2006). All synthetic: speckle pattern, noise and planet brightness are illustrative.
function mxAdi(seed, o){
  o = Object.assign({G: 64, N: 24, rot: 60, lod: 3, rp: 16, pa: 20, planet: 0.6, noise: 0.04, jitter: 0.12}, o || {});
  const {G, N} = o, rnd = mxRand(seed), c0 = (G - 1) / 2, sig = o.lod / 2.355, gauss = () => { let s = 0; for (let i = 0; i < 6; i++) s += rnd(); return (s - 3) / Math.SQRT2; };
  const sp = []; for (let i = 0; i < 110; i++){ const r = 5 + rnd() * 24, a = rnd() * 2 * Math.PI; sp.push([c0 + r * Math.cos(a), c0 + r * Math.sin(a), Math.exp(-r / 10) * (0.3 + rnd())]); }
  const blob = (F, x, y, A) => { for (let j = Math.max(0, Math.floor(y - 4 * sig)); j <= Math.min(G - 1, Math.ceil(y + 4 * sig)); j++) for (let i = Math.max(0, Math.floor(x - 4 * sig)); i <= Math.min(G - 1, Math.ceil(x + 4 * sig)); i++) F[j * G + i] += A * Math.exp(-((i - x) ** 2 + (j - y) ** 2) / (2 * sig * sig)); };
  // The planet's brightness is set against the typical speckle at its radius.
  const ring = sp.filter(s => Math.abs(Math.hypot(s[0] - c0, s[1] - c0) - o.rp) < 3).map(s => s[2]), Ap = o.planet * (ring.length ? ring.reduce((a, b) => a + b, 0) / ring.length : 0.2);
  const frames = [], ang = [];
  for (let k = 0; k < N; k++){
    const F = new Float32Array(G * G), th = o.rot * k / (N - 1); ang.push(th);
    for (const s of sp) blob(F, s[0], s[1], s[2] * (1 + o.jitter * gauss()));
    const a = (o.pa + th) * Math.PI / 180; blob(F, c0 + o.rp * Math.cos(a), c0 + o.rp * Math.sin(a), Ap);
    for (let p = 0; p < G * G; p++) F[p] += o.noise * gauss();
    frames.push(F);
  }
  const med = new Float32Array(G * G), col = new Float32Array(N);
  for (let p = 0; p < G * G; p++){ for (let k = 0; k < N; k++) col[k] = frames[k][p]; col.sort(); med[p] = N % 2 ? col[(N - 1) / 2] : 0.5 * (col[N / 2 - 1] + col[N / 2]); }
  // Turn each residual back by its field rotation (bilinear), then average the first n of them.
  const derot = (R, th) => { const out = new Float32Array(G * G), ca = Math.cos(th * Math.PI / 180), sa = Math.sin(th * Math.PI / 180);
    for (let j = 0; j < G; j++) for (let i = 0; i < G; i++){ const x = i - c0, y = j - c0, xs = c0 + ca * x - sa * y, ys = c0 + sa * x + ca * y, i0 = Math.floor(xs), j0 = Math.floor(ys);
      if (i0 < 0 || j0 < 0 || i0 >= G - 1 || j0 >= G - 1) continue; const fx = xs - i0, fy = ys - j0;
      out[j * G + i] = R[j0 * G + i0] * (1 - fx) * (1 - fy) + R[j0 * G + i0 + 1] * fx * (1 - fy) + R[(j0 + 1) * G + i0] * (1 - fx) * fy + R[(j0 + 1) * G + i0 + 1] * fx * fy; }
    return out; };
  const stacks = [], acc = new Float32Array(G * G);
  for (let k = 0; k < N; k++){ const R = new Float32Array(G * G); for (let p = 0; p < G * G; p++) R[p] = frames[k][p] - med[p];
    const D = derot(R, ang[k]); for (let p = 0; p < G * G; p++) acc[p] += D[p]; stacks.push(Float32Array.from(acc, v => v / (k + 1))); }
  // Signal-to-noise at the planet's (de-rotated) place against the rest of its annulus.
  const a0 = o.pa * Math.PI / 180, px = c0 + o.rp * Math.cos(a0), py = c0 + o.rp * Math.sin(a0);
  const snr = F => { let s = 0, n = 0, m = 0, q = 0, nn = 0;
    for (let j = 0; j < G; j++) for (let i = 0; i < G; i++){ const d = Math.hypot(i - px, j - py), r = Math.hypot(i - c0, j - c0);
      if (d < 1.5){ s += F[j * G + i]; n++; } else if (d > 6 && Math.abs(r - o.rp) < 3){ m += F[j * G + i]; q += F[j * G + i] ** 2; nn++; } }
    const mu = m / nn, sd = Math.sqrt(Math.max(1e-12, q / nn - mu * mu)); return (s / n - mu) / sd; };
  return {G, N, frames, med, stacks, ang, snrRaw: snr(frames[0]), snr: stacks.map(snr), c0, sig, Ap, o, px, py};
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
  const sc = st.fig.querySelector('.mxscrub');
  if (sc){ if (document.activeElement !== sc) sc.value = Math.round(st.t * 1000);
    // The scrubber's spoken value, in the visual's own cycle (written only when it changes).
    const vt = `t = ${st.t.toFixed(2)} of the ${(MX && MX.tunit && MX.tunit[st.fig.dataset.vis]) || 'cycle'}`; if (sc.getAttribute('aria-valuetext') !== vt) sc.setAttribute('aria-valuetext', vt); }
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
  const depth = 1 - mxFlux(S.b / 1, S.k, u1, u2), floor = Math.min(1 - 1.35 * Math.max(depth, 1e-5), ...(S.dip && S.dip.pts ? S.dip.pts.map(p => 1 + p[1] * 1e-6 - 0.00002) : [1]), ...(S.dip && S.dip.model ? S.dip.model.map(p => 1 + p[1] * 1e-6 - 0.00002) : [1]));
  const X = f => gx0 + (f + win) / (2 * win) * gw, Y = v => gy0 + (1 - v) / (1 - floor) * gh * 0.86 + 6;
  mxAxes(c, gx0, gy0, gw, gh, {y: 'BRIGHTNESS (%)', x: 'TIME FROM MID-TRANSIT (h)'});
  for (const v of [1, 1 - depth]){ c.strokeStyle = 'rgba(255,255,255,.08)'; c.beginPath(); c.moveTo(gx0, Y(v)); c.lineTo(gx0 + gw, Y(v)); c.stroke(); mxText(c, (v * 100).toFixed(depth < 0.001 ? 3 : 2), gx0 - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
  for (const hh of [-1, 0, 1]){ const f = hh * win * 0.8, xx = X(f); mxText(c, (f * P * 24).toFixed(1), xx, gy0 + gh + 13, {size: 11, mono: true, align: 'center'}); }
  if (S.dip && S.dip.model && S.dip.model.length){
    c.save(); c.beginPath(); c.rect(gx0, gy0, gw, gh); c.clip();
    c.setLineDash([5, 4]); c.strokeStyle = 'rgba(255,255,255,.55)'; c.lineWidth = 1.2; c.beginPath();
    S.dip.model.forEach((p, i) => { const x = X(p[0] / P), y = Y(1 + p[1] * 1e-6); i ? c.lineTo(x, y) : c.moveTo(x, y); }); c.stroke(); c.setLineDash([]);
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
  const cap = S.dip ? 'line: model from stored values · dots: SetuHQ’s stored points' + (S.dip.model && S.dip.model.length ? ' · dashed: stored fit' : '') : 'line: model from stored values, not observed data';
  // On a narrow stage the key goes on its own lines in the free band under the dip, clear of the curve and the axis title.
  if (w < 600) cap.split(' · ').forEach((t, i, all) => mxText(c, t, gx0 + 6, gy0 + gh * 0.74 + i * 14 - (all.length - 2) * 7, {size: 11}));
  else mxText(c, cap, gx0 + gw, gy0 - 6, {size: 11, align: 'right'});
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
  if (!S.intro) mxText(c, 'star positions illustrative; colours from temperature', w - 12, 18, {size: 11, align: 'right'});
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
// ---------- radio: cyclotron-maser emission, beamed in a hollow cone, and its frequency cut-off ----------
function mxFce(B){ return 1.602176634e-19 * B * 1e-4 / (2 * Math.PI * 9.1093837015e-31) / 1e6; }   // MHz for B in gauss (cyclotron_mhz)
const MX_BLOG = [-1, 3.5];   // the field slider: 0.1 G to ~3 kG, log scale
// The field slider announces its value and the cut-off it sets (from the start, not only after a change).
function mxRadioLabel(st){ const r = st.fig.querySelector('.mxbfield input'); if (r) r.setAttribute('aria-valuetext', `${st.opt.B.toPrecision(2)} gauss, cyclotron cut-off ${mxFce(st.opt.B).toPrecision(3)} MHz`); }
MXV.radio = {key: 0.1, period: 10, init(st){ st.opt.mode = 'aurora'; st.opt.B = 7.5; mxRadioLabel(st); },
  control(st, el){
    if (el.tagName === 'SELECT'){ st.opt.mode = el.value; const B = el.value === 'spi' ? 1000 : 7.5, r = st.fig.querySelector('.mxbfield input');
      st.opt.B = B; if (r) r.value = String(Math.round((Math.log10(B) - MX_BLOG[0]) / (MX_BLOG[1] - MX_BLOG[0]) * 1000)); }
    else if (el.type === 'range') st.opt.B = Math.pow(10, MX_BLOG[0] + Number(el.value) / 1000 * (MX_BLOG[1] - MX_BLOG[0]));
    mxRadioLabel(st);
  },
  draw(c, w, h, t, st){
    const spi = st.opt.mode === 'spi', B = st.opt.B, fce = mxFce(B);
    const sceneH = h * 0.56, cy = sceneH * 0.52, ox = w - 40, oy = cy;
    // The body that emits: the planet's own pole (aurora) or the star's footpoint (interaction).
    const sx = w * 0.3, sR = Math.min(sceneH * 0.2, w * 0.1), orbR = Math.min(w * 0.22, sceneH * 0.8), ang = 2 * Math.PI * t;
    const px = sx + orbR * Math.cos(ang), py = cy + orbR * 0.32 * Math.sin(ang);
    mxStar(c, sx, cy, sR, spi ? 3100 : 5400, t, {flat: true});
    c.strokeStyle = 'rgba(255,255,255,.18)'; c.setLineDash([3, 5]); c.beginPath(); c.ellipse(sx, cy, orbR, orbR * 0.32, 0, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
    // Dipole field lines: around the star (interaction) or the planet (aurora).
    const fx = spi ? sx : px, fy = spi ? cy : py, fR = spi ? sR : 9;
    c.strokeStyle = 'rgba(100,210,255,.35)'; c.lineWidth = 1;
    for (const L of spi ? [1.8, 2.6, 3.6] : [2.2, 3.4, 4.8]){ for (const sgn of [-1, 1]){ c.beginPath();
      for (let k = 0; k <= 40; k++){ const th = 0.15 + (Math.PI - 0.3) * k / 40, r = fR * L * Math.sin(th) ** 2, x = fx + sgn * r * Math.sin(th), y = fy - r * Math.cos(th); k ? c.lineTo(x, y) : c.moveTo(x, y); }
      c.stroke(); } }
    mxPlanet(c, px, py, 7, 4, true);
    // The flux tube from the planet to the star's footpoint (interaction only).
    const foot = [sx + sR * 0.35, cy - sR * 0.94];
    if (spi){ c.strokeStyle = 'rgba(255,179,64,.75)'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(px, py); c.quadraticCurveTo((px + foot[0]) / 2, Math.min(py, foot[1]) - 40, foot[0], foot[1]); c.stroke(); }
    // The hollow emission cone from the source, turning with the orbit; a burst when its wall crosses the observer.
    const src = spi ? foot : [px, py - 9], axis = -Math.PI / 2 + 0.9 * Math.cos(ang), half = 1.1, toObs = Math.atan2(oy - src[1], ox - src[0]);
    const off = Math.abs(Math.atan2(Math.sin(toObs - axis), Math.cos(toObs - axis))), hit = Math.abs(off - half) < 0.08;
    c.fillStyle = hit ? 'rgba(255,214,10,.28)' : 'rgba(255,214,10,.12)';
    for (const sgn of [-1, 1]){ const a = axis + sgn * half; c.beginPath(); c.moveTo(src[0], src[1]); c.arc(src[0], src[1], w * 0.6, a - 0.05, a + 0.05); c.closePath(); c.fill(); }
    mxEye(c, ox - 30, oy + 30);
    mxText(c, spi ? 'star–planet interaction: emission at the star’s footpoint' : 'planet aurora: emission from the planet’s pole', 14, 22, {size: 12, w: 600, color: '#F5F5F7'});
    const Bs = B >= 10 ? Math.round(B).toLocaleString('en-GB') : B.toPrecision(2);
    mxText(c, `B = ${Bs} G → f_ce = ${fce >= 1000 ? (fce / 1000).toPrecision(3) + ' GHz' : fce.toPrecision(3) + ' MHz'}`, 14, 40, {size: 11, mono: true});
    // Dynamic spectrum: time across, frequency up (log, 1 MHz–10 GHz); bursts reach up to f_ce.
    const gx0 = 64, gy0 = sceneH + 26, gw = w - gx0 - 18, gh = h - gy0 - 36;
    mxGlassPanel(c, 10, sceneH + 6, w - 20, h - sceneH - 12);
    mxAxes(c, gx0, gy0, gw, gh, {y: 'FREQUENCY', x: 'TIME (ONE ORBIT)'});
    const Y = f => gy0 + gh - (Math.log10(f) - 0) / 4 * gh;
    for (const [f, lab] of [[1, '1 MHz'], [10, '10 MHz'], [100, '100 MHz'], [1000, '1 GHz'], [10000, '10 GHz']]) mxText(c, lab, gx0 - 6, Y(f) + 4, {size: 11, mono: true, align: 'right'});
    c.fillStyle = 'rgba(100,210,255,.08)'; c.fillRect(gx0, Y(240), gw, Y(10) - Y(240)); mxText(c, 'LOFAR 10–240 MHz', gx0 + gw - 4, Y(240) + 12, {size: 11, align: 'right', color: '#64D2FF'});
    c.fillStyle = 'rgba(191,90,242,.10)'; c.fillRect(gx0, Y(4000), gw, Y(2000) - Y(4000)); mxText(c, 'VLA 2–4 GHz', gx0 + gw - 4, Y(4000) + 12, {size: 11, align: 'right', color: '#BF5AF2'});
    const yc = Y(Math.min(9999, Math.max(1, fce)));
    c.strokeStyle = '#FFD60A'; c.setLineDash([4, 4]); c.beginPath(); c.moveTo(gx0, yc); c.lineTo(gx0 + gw, yc); c.stroke(); c.setLineDash([]);
    mxText(c, 'f_ce', gx0 + 6, yc - 4, {size: 11, mono: true, color: '#FFD60A'});
    // Bursts happen where the cone wall met the observer, at the same orbital phases each orbit (computed from the geometry above).
    c.fillStyle = 'rgba(255,214,10,.85)';
    for (let k = 0; k <= 200; k++){ const tt = k / 200; if (tt > t) break; const aa = -Math.PI / 2 + 0.9 * Math.cos(2 * Math.PI * tt);
      const pxx = sx + orbR * Math.cos(2 * Math.PI * tt), pyy = cy + orbR * 0.32 * Math.sin(2 * Math.PI * tt), s2 = spi ? foot : [pxx, pyy - 9];
      const o2 = Math.atan2(oy - s2[1], ox - s2[0]), d2 = Math.abs(Math.atan2(Math.sin(o2 - aa), Math.cos(o2 - aa)));
      if (Math.abs(d2 - half) < 0.08){ const x = gx0 + tt * gw; c.fillRect(x - 1, yc, 2.5, Math.max(0, Y(Math.max(1, fce / 8)) - yc)); } }
    c.fillStyle = '#F5F5F7'; c.fillRect(gx0 + t * gw - 0.5, gy0, 1, gh);
    st.exag = 'field lines, cone and orbit not to scale; burst times illustrative; cut-off computed';
  }};

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

// ---------- coronagraph families: four optical trains drawn from the functions above ----------
// A log-intensity colour ramp (0 = the stretch's floor, 1 = its top), the same in both themes (the stage is dark).
const MX_HEAT = [[0, [0, 0, 0]], [0.2, [20, 24, 82]], [0.45, [94, 42, 140]], [0.7, [230, 110, 60]], [0.88, [255, 190, 90]], [1, [255, 250, 235]]];
function mxHeat(v){ v = Math.max(0, Math.min(1, v)); for (let i = 1; i < MX_HEAT.length; i++) if (v <= MX_HEAT[i][0]){ const [a, ca] = MX_HEAT[i - 1], [b, cb] = MX_HEAT[i], f = (v - a) / (b - a); return ca.map((x, j) => Math.round(x + f * (cb[j] - x))); } return MX_HEAT[MX_HEAT.length - 1][1]; }
const mxLogV = (I, decades) => 1 + Math.log10(Math.max(I, 1e-30)) / decades;
// A radially symmetric image on an offscreen canvas, cached by key; fn(r, angle) returns [r, g, b].
const MX_IMG = new Map();
function mxRadialImage(key, N, ext, fn){
  if (MX_IMG.has(key)) return MX_IMG.get(key);
  const cv = document.createElement('canvas'); cv.width = cv.height = N;
  const cx = cv.getContext('2d'), im = cx.createImageData(N, N);
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++){
    const x = (i + 0.5) / N * 2 - 1, y = (j + 0.5) / N * 2 - 1, c = fn(Math.hypot(x, y) * ext, Math.atan2(y, x)), o = 4 * (j * N + i);
    im.data[o] = c[0]; im.data[o + 1] = c[1]; im.data[o + 2] = c[2]; im.data[o + 3] = 255;
  }
  cx.putImageData(im, 0, 0);
  if (MX_IMG.size > 80) MX_IMG.clear();
  MX_IMG.set(key, cv); return cv;
}
// Same for a square grid of values (the ADI frames), with its own stretch.
function mxGridImage(vals, G, tone){
  const cv = document.createElement('canvas'); cv.width = cv.height = G;
  const cx = cv.getContext('2d'), im = cx.createImageData(G, G);
  for (let p = 0; p < G * G; p++){ const c = mxHeat(tone(vals[p])); im.data[4 * p] = c[0]; im.data[4 * p + 1] = c[1]; im.data[4 * p + 2] = c[2]; im.data[4 * p + 3] = 255; }
  cx.putImageData(im, 0, 0); return cv;
}
// Text wrapped by words to a width, at most `max` lines (the last one is cut with an ellipsis).
function mxWrap(c, s, x, y, maxW, max, o){
  o = o || {}; c.font = `${o.w || 500} ${o.size || 11}px "Geist",system-ui,sans-serif`;
  const words = String(s).split(' '), lines = []; let cur = '';
  for (const wd of words){ const tr = cur ? cur + ' ' + wd : wd; if (c.measureText(tr).width > maxW && cur){ lines.push(cur); cur = wd; } else cur = tr; }
  if (cur) lines.push(cur);
  if (lines.length > max){ lines.length = max; let l = lines[max - 1]; while (l.length > 1 && c.measureText(l + '…').width > maxW) l = l.slice(0, -1); lines[max - 1] = l + '…'; }
  lines.forEach((l, i) => mxText(c, l, x, y + i * ((o.size || 11) + 3), o));
  return lines.length;
}
// The stage's headline: one line on a wide stage, up to two on a phone.
const mxHead = (c, w, s) => mxWrap(c, s, 14, 22, w - 28, 2, {size: w < 600 ? 11 : 12, w: 600, color: '#F5F5F7'});
// The four scenes: Lyot (mask + stop), an apodised pupil, a vortex phase mask, and AO with ADI.
const MX_CG = {lyotMask: 4, lyotStops: [1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 0.95, 0.9, 0.85, 0.8], up: 8, cp: 1e-3};
function mxCgPanels(w, h){
  const narrow = w < 600, cols = narrow ? 2 : 4, gap = narrow ? 12 : 14, top = narrow ? 62 : 56;
  const s = Math.max(60, Math.min((w - gap * (cols + 1)) / cols, narrow ? h * 0.22 : h * 0.4));
  const rowW = cols * s + (cols - 1) * gap, x0 = (w - rowW) / 2, ps = [];
  for (let i = 0; i < 4; i++){ const r = Math.floor(i / cols), cI = i % cols; ps.push({x: x0 + cI * (s + gap), y: top + r * (s + 52), s}); }
  const bottom = ps[3].y + s + 36;
  return {ps, bottom, narrow};
}
function mxCgFrame(c, p, title, sub, img, on){
  c.save(); c.beginPath(); c.roundRect ? c.roundRect(p.x, p.y, p.s, p.s, 12) : c.rect(p.x, p.y, p.s, p.s); c.clip();
  if (img){ c.imageSmoothingEnabled = true; c.drawImage(img, p.x, p.y, p.s, p.s); }
  c.restore();
  c.strokeStyle = on ? 'rgba(100,210,255,.85)' : 'rgba(255,255,255,.16)'; c.lineWidth = on ? 1.5 : 1;
  c.beginPath(); c.roundRect ? c.roundRect(p.x + .5, p.y + .5, p.s - 1, p.s - 1, 12) : c.rect(p.x + .5, p.y + .5, p.s - 1, p.s - 1); c.stroke();
  mxText(c, title, p.x + 2, p.y - 8, {size: 11, w: 600, color: on ? '#F5F5F7' : '#C7C7CC'});
  if (sub) mxWrap(c, sub, p.x + 2, p.y + p.s + 15, p.s, 2, {size: 11});
}
function mxCgArrows(c, ps, narrow){ if (narrow) return; c.strokeStyle = 'rgba(255,255,255,.3)'; c.fillStyle = 'rgba(255,255,255,.3)';
  for (let i = 0; i < 3; i++){ const a = ps[i], b = ps[i + 1], y = a.y + a.s / 2, x0 = a.x + a.s + 2, x1 = b.x - 2; c.beginPath(); c.moveTo(x0, y); c.lineTo(x1 - 4, y); c.stroke(); c.beginPath(); c.moveTo(x1, y); c.lineTo(x1 - 6, y - 4); c.lineTo(x1 - 6, y + 4); c.fill(); } }
// A log-intensity profile: lines of [u, I] against u (λ/D), from 10⁰ down to 10⁻⁸. The key sits above the plot,
// in as many rows as the width needs, so it never covers a curve.
function mxCgKey(c, x, y0, w, keys){
  c.font = '500 11px "Geist",system-ui,sans-serif';
  const rows = [[]]; let rw = 0;
  keys.forEach(k => { const kw = 26 + c.measureText(k.label).width + 14; if (rw + kw > w && rows[rows.length - 1].length){ rows.push([]); rw = 0; } rows[rows.length - 1].push([k, rw]); rw += kw; });
  rows.forEach((r, i) => r.forEach(([k, dx]) => { const kx = x + dx, ky = y0 + i * 15;
    if (k.planet){ c.fillStyle = '#64D2FF'; c.beginPath(); c.arc(kx + 9, ky - 4, 3.5, 0, 2 * Math.PI); c.fill(); }
    else { c.strokeStyle = k.color; c.lineWidth = 2; c.setLineDash(k.dash || []); c.beginPath(); c.moveTo(kx, ky - 4); c.lineTo(kx + 18, ky - 4); c.stroke(); c.setLineDash([]); }
    mxText(c, k.label, kx + 24, ky, {size: 11}); }));
  return rows.length * 15;
}
function mxCgPlot(c, x, y, w, h, lines, o){
  o = o || {};
  const keys = lines.filter(l => l.label).concat(o.planet ? [{planet: true, label: o.planetLabel || 'planet'}] : []);
  const top = y - 22;
  mxGlassPanel(c, x - 44, top, w + 56, h + 50);
  const kh = mxCgKey(c, x, top + 16, w, keys) + 4;
  y += kh; h -= kh + 14;   // the last 14 px: a row under the tick labels for the axis title and the mask's label
  const umax = o.umax || 12, dec = 8, X = u => x + u / umax * w, Y = I => y + Math.min(1, -Math.log10(Math.max(I, 1e-12)) / dec) * h;
  mxAxes(c, x, y, w, h, {y: 'STARLIGHT, LOG (PEAK = 1)', x: ''});
  mxText(c, 'ANGLE FROM THE STAR (λ/D)', x + w, y + h + 27, {size: 11, w: 600, color: '#8E8E93', mono: true, align: 'right'});
  if (o.mask){ c.fillStyle = 'rgba(255,255,255,.05)'; c.fillRect(x, y, X(o.mask) - x, h); mxText(c, `shaded: ${o.maskLabel || 'behind the mask'}`, x, y + h + 27, {size: 11}); }
  for (const e of [0, 2, 4, 6, 8]){ const yy = Y(Math.pow(10, -e)); c.strokeStyle = 'rgba(255,255,255,.07)'; c.lineWidth = 1; c.beginPath(); c.moveTo(x, yy); c.lineTo(x + w, yy); c.stroke(); mxText(c, e ? `10⁻${'⁰¹²³⁴⁵⁶⁷⁸'[e]}` : '1', x - 6, yy + 4, {size: 11, mono: true, align: 'right'}); }
  for (const u of [0, 4, 8, 12]) if (u <= umax) mxText(c, String(u), X(u), y + h + 13, {size: 11, mono: true, align: 'center'});
  c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip();
  for (const L of lines){ c.strokeStyle = L.color; c.lineWidth = L.width || 1.6; c.setLineDash(L.dash || []); c.beginPath(); L.pts.forEach((p, i) => { const xx = X(p[0]), yy = Y(p[1]); i ? c.lineTo(xx, yy) : c.moveTo(xx, yy); }); c.stroke(); c.setLineDash([]); }
  if (o.planet){ c.fillStyle = '#64D2FF'; c.beginPath(); c.arc(X(o.planet[0]), Y(o.planet[1]), 4, 0, 2 * Math.PI); c.fill(); }
  c.restore();
}
// 1.8×10⁻⁷, for numbers spoken on the stage.
function mxSci(x){ if (!(x > 0)) return '0'; const e = Math.floor(Math.log10(x)), m = x / Math.pow(10, e); return `${m.toFixed(1)}×10${mxSup(e)}`; }
const mxPhase = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
MXV.cgfam = {key: 0.85, period: 14, init(st){ st.opt.mode = 'lyot'; },
  control(st, el){ if (el.tagName === 'SELECT') st.opt.mode = el.value; },
  draw(c, w, h, t, st){
    const m = st.opt.mode, L = mxCgPanels(w, h), ps = L.ps, N = L.narrow ? 72 : 96;
    const lw = Math.min(w - 90, 760), lx = (w - lw) / 2 + 30, ly = L.bottom + 22, lh = Math.max(60, h - ly - 40);
    const planetDot = (p, u, pa, I, decades, ext) => { const r = u / ext * p.s / 2, a = pa * Math.PI / 180, v = mxLogV(I, decades); if (v <= 0) return;
      c.fillStyle = mxRgb(mxHeat(v)); c.beginPath(); c.arc(p.x + p.s / 2 + r * Math.cos(a), p.y + p.s / 2 - r * Math.sin(a), Math.max(2, p.s / 2 / ext * 0.6), 0, 2 * Math.PI); c.fill(); };
    if (m === 'adi'){ this.adi(c, w, h, t, st, L, lx, ly, lw, lh); return; }
    const ext = 10, airyImg = mxRadialImage('airy' + N, N, ext, r => mxHeat(mxLogV(mxAiry(r), 6)));
    const pupil = (key, fn) => mxRadialImage(key + N, N, 1.5, r => fn(r));
    // A clear pupil is drawn as a vector disc, so its edge stays sharp at any size.
    const clearPupil = (p, title, sub, on) => { mxCgFrame(c, p, title, sub, null, on); c.fillStyle = 'rgb(235,235,240)'; c.beginPath(); c.arc(p.x + p.s / 2, p.y + p.s / 2, p.s / 3, 0, 2 * Math.PI); c.fill(); };
    if (m === 'apod'){
      // The apodiser's strength steps n = 0 (clear), 1, 2: (1 − ρ²)ⁿ.
      const n = t < 0.3 ? 0 : t < 0.6 ? 1 : 2;
      clearPupil(ps[0], 'Clear pupil', 'transmission 1', n === 0);
      mxCgFrame(c, ps[1], 'Its image', 'the Airy pattern: rings', airyImg, n === 0);
      mxCgFrame(c, ps[2], `Apodised pupil, n = ${n}`, `transmission (1 − ρ²)${n ? '' : '⁰'}${n === 1 ? '¹' : n === 2 ? '²' : ''}`, pupil('apod' + n, r => { const a = r < 1 ? Math.pow(1 - r * r, n) : 0; return [Math.round(235 * a), Math.round(235 * a), Math.round(240 * a)]; }), n > 0);
      mxCgFrame(c, ps[3], 'Its image', n ? 'rings suppressed; core wider' : 'same as clear', mxRadialImage('son' + n + N, N, ext, r => mxHeat(mxLogV(mxSonineI(r, n), 6))), n > 0);
      planetDot(ps[3], 5, 35, 1e-4 / (n + 1) ** 2, 6, ext);
      mxCgArrows(c, ps, L.narrow);
      const pts = (f) => Array.from({length: 241}, (_, i) => [i / 20, f(i / 20)]);
      mxCgPlot(c, lx, ly, lw, lh, [{pts: pts(mxAiry), color: 'rgba(255,255,255,.5)', dash: [4, 4], label: 'clear pupil (Airy)'}, {pts: pts(u => mxSonineI(u, n)), color: '#FFB340', label: `apodised, n = ${n}`}], {planet: [5, 1e-4 / (n + 1) ** 2], planetLabel: 'planet: illustrative 10⁻⁴, dimmed with the star'});
      mxHead(c, w, `throughput 1/(2n + 1) = ${Math.round(100 / (2 * n + 1))}% · peak 1/(n + 1)² = ${Math.round(100 / (n + 1) ** 2)}% of the clear pupil’s`);
      st.exag = 'log intensity stretch (1 to 10⁻⁶); planet at an illustrative 10⁻⁴; ideal monochromatic optics';
      return;
    }
    if (m === 'vortex'){
      // Phase ramp e^{2iθ} winds on, then the stop closes from 150% to 95% of the pupil.
      const wind = mxPhase(t, 0.15, 0.45), s = 1.5 - 0.55 * mxPhase(t, 0.5, 0.7);
      clearPupil(ps[0], 'Entrance pupil', 'the telescope', t < 0.15);
      mxCgFrame(c, ps[1], 'Focal plane: vortex', 'phase ramp, charge 2', airyImg, t >= 0.15 && t < 0.5);
      if (wind > 0){ // the mask's phase, as hue: two full turns around the centre (charge 2)
        const ramp = mxRadialImage('vortexhue' + N, N, ext, (r, a) => { const hh = ((2 * a / (2 * Math.PI)) % 1 + 1) % 1, k = Math.floor(hh * 6), f = hh * 6 - k, q = 1 - f;
          const rgb = [[1, f, 0], [q, 1, 0], [0, 1, f], [0, q, 1], [f, 0, 1], [1, 0, q]][k % 6]; return rgb.map(x => Math.round(60 + 160 * x)); });
        c.save(); c.globalAlpha = 0.45 * wind; c.beginPath(); c.roundRect ? c.roundRect(ps[1].x, ps[1].y, ps[1].s, ps[1].s, 12) : c.rect(ps[1].x, ps[1].y, ps[1].s, ps[1].s); c.clip(); c.drawImage(ramp, ps[1].x, ps[1].y, ps[1].s, ps[1].s); c.restore();
      }
      const lyIn = mxRadialImage('vortexlyot' + N, N, 1.5, r => mxHeat(mxLogV(mxVortexPupil(r) ** 2, 4)));
      const clear = pupil('clearlog', r => mxHeat(r < 1 ? 1 : 0));
      mxCgFrame(c, ps[2], 'Lyot plane', wind < 1 ? 'starlight moving outward' : 'star: all outside the pupil', wind < 0.5 ? clear : lyIn, t >= 0.45 && t < 0.75);
      const stopPx = s / 1.5 * ps[2].s / 2; c.save(); c.beginPath(); c.rect(ps[2].x, ps[2].y, ps[2].s, ps[2].s); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI, true); c.fillStyle = 'rgba(40,40,44,.92)'; c.fill('evenodd'); c.restore();
      c.strokeStyle = '#64D2FF'; c.setLineDash([3, 3]); c.beginPath(); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
      const done = wind >= 1 && s < 1, fin = done ? mxRadialImage('black' + N, N, 1, () => [0, 0, 0]) : airyImg;
      mxCgFrame(c, ps[3], 'Final image', done ? 'star removed (ideal)' : 'star still there', fin, t >= 0.7);
      planetDot(ps[3], 3, 35, MX_CG.cp * Math.min(1, s) ** 4, 6, ext);
      mxCgArrows(c, ps, L.narrow);
      const pts = (f) => Array.from({length: 241}, (_, i) => [i / 20, f(i / 20)]);
      mxCgPlot(c, lx, ly, lw, lh, [{pts: pts(mxAiry), color: 'rgba(255,255,255,.5)', dash: [4, 4], label: 'no coronagraph (Airy)'}, {pts: pts(u => done ? 1e-12 : mxAiry(u)), color: '#FFB340', label: done ? 'vortex: zero (ideal)' : 'vortex not yet working'}], {planet: [3, MX_CG.cp * Math.min(1, s) ** 4], planetLabel: 'planet: illustrative 10⁻³, through the stop'});
      mxHead(c, w, `ideal charge-2 vortex: Lyot-plane field 0 inside the pupil, (1/ρ)² outside · stop ${Math.round(s * 100)}% of the pupil`);
      st.exag = 'log intensity stretch (1 to 10⁻⁶); planet at an illustrative 10⁻³; ideal optics: real vortices leave residuals from aberrations and the star’s size';
      return;
    }
    // Lyot: the occulting mask fades in, then the Lyot stop closes from 150% to 80% of the pupil.
    const T = st.opt.lyot || (st.opt.lyot = mxLyotTable(MX_CG.lyotMask));
    if (!st.opt.lyotFinal){ // the final image's profile for each stop, once
      st.opt.lyotFinal = MX_CG.lyotStops.map(s => ({s, pts: Array.from({length: 121}, (_, i) => [i / 10, mxLyotFinal(T, i / 10, s)])})); }
    const mask = mxPhase(t, 0.15, 0.35), s = 1.5 - 0.7 * mxPhase(t, 0.42, 0.75);
    const F = st.opt.lyotFinal, i1 = F.findIndex(f => f.s <= s), j = Math.max(1, i1 < 0 ? F.length - 1 : i1), A = F[j - 1], B = F[j], f = (A.s - s) / ((A.s - B.s) || 1);
    const now = A.pts.map((p, i) => [p[0], Math.pow(10, (1 - f) * Math.log10(Math.max(p[1], 1e-14)) + f * Math.log10(Math.max(B.pts[i][1], 1e-14)))]);
    const prof = u => { const x = Math.min(119.999, u * 10), i = Math.floor(x), g = x - i; return now[i][1] * (1 - g) + now[i + 1][1] * g; };
    clearPupil(ps[0], 'Entrance pupil', 'the telescope', t < 0.15);
    mxCgFrame(c, ps[1], 'Focal plane + mask', `occulting disc, ${MX_CG.lyotMask} λ/D`, airyImg, t >= 0.15 && t < 0.42);
    planetDot(ps[1], MX_CG.up, 35, MX_CG.cp, 6, ext);
    if (mask > 0){ const mr = MX_CG.lyotMask / ext * ps[1].s / 2; c.fillStyle = `rgba(8,8,10,${mask})`; c.beginPath(); c.arc(ps[1].x + ps[1].s / 2, ps[1].y + ps[1].s / 2, mr, 0, 2 * Math.PI); c.fill(); c.strokeStyle = `rgba(255,255,255,${0.5 * mask})`; c.stroke(); }
    const lyotImg = mxRadialImage('lyotplane' + N, N, 1.5, r => { const i = r < 1 ? Math.min(T.A.length - 1, Math.round(r * 300)) : Math.min(T.B.length - 1, Math.round((r - 1) * 200)); const e = r < 1 ? T.A[i][1] : r <= 1.5 ? T.B[i][1] : 0; return mxHeat(mxLogV(e * e, 4)); });
    const clearLog = pupil('clearlog', r => mxHeat(r < 1 ? 1 : 0));
    mxCgFrame(c, ps[2], 'Lyot plane + stop', mask < 1 ? 'the pupil again' : 'bright rim: light the mask diffracted', mask < 0.5 ? clearLog : lyotImg, t >= 0.42 && t < 0.75);
    const stopPx = s / 1.5 * ps[2].s / 2; c.save(); c.beginPath(); c.rect(ps[2].x, ps[2].y, ps[2].s, ps[2].s); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI, true); c.fillStyle = 'rgba(40,40,44,.92)'; c.fill('evenodd'); c.restore();
    c.strokeStyle = '#64D2FF'; c.setLineDash([3, 3]); c.beginPath(); c.arc(ps[2].x + ps[2].s / 2, ps[2].y + ps[2].s / 2, stopPx, 0, 2 * Math.PI); c.stroke(); c.setLineDash([]);
    const sKey = 'lyotfinal' + N + '_' + Math.round(s * 40) + '_' + (mask >= 1 ? 1 : 0);
    const finImg = mask < 1 ? airyImg : mxRadialImage(sKey, N, ext, r => mxHeat(mxLogV(prof(r), 6)));
    mxCgFrame(c, ps[3], 'Final image', mask < 1 ? 'no mask yet: the full star' : `stop ${Math.round(s * 100)}% of the pupil`, finImg, t >= 0.75);
    planetDot(ps[3], MX_CG.up, 35, MX_CG.cp * Math.min(1, s) ** 4, 6, ext);
    mxCgArrows(c, ps, L.narrow);
    const lines = [{pts: Array.from({length: 241}, (_, i) => [i / 20, mxAiry(i / 20)]), color: 'rgba(255,255,255,.5)', dash: [4, 4], label: 'no coronagraph (Airy)'}];
    if (mask >= 1) lines.push({pts: now, color: '#FFB340', label: `Lyot, stop ${Math.round(s * 100)}%`});
    mxCgPlot(c, lx, ly, lw, lh, lines, {mask: MX_CG.lyotMask, planet: [MX_CG.up, MX_CG.cp * Math.min(1, s) ** 4], planetLabel: 'planet: illustrative 10⁻³, through the stop'});
    const at8 = prof(MX_CG.up), air8 = mxAiry(MX_CG.up);
    mxHead(c, w, mask < 1 ? 'the star’s image, rings and all' : `starlight at ${MX_CG.up} λ/D: ${mxSci(at8)} of the star’s peak (no coronagraph: ${mxSci(air8)})`);
    st.exag = 'log intensity stretch (1 to 10⁻⁶); planet at an illustrative 10⁻³; ideal monochromatic optics; mask and stop sizes illustrative';
  },
  adi(c, w, h, t, st, L, lx, ly, lw, lh){
    const A = st.opt.adi || (st.opt.adi = mxAdi(17)), ps = L.ps, G = A.G;
    const ao = mxPhase(t, 0.02, 0.18), k = Math.max(0, Math.min(A.N - 1, Math.floor(mxPhase(t, 0.22, 0.97) * A.N)));
    const smax = Math.max(...A.med);
    const logTone = v => mxLogV(Math.max(v, 1e-6) / smax, 3);
    // AO: a seeing halo (no correction) blends into the corrected frame (core under the mask, speckles).
    const key = 'ao' + Math.round(ao * 10);
    if (!st.opt.aoImg || st.opt.aoKey !== key){
      const F0 = A.frames[0], mix = new Float32Array(G * G), sd = 11;
      for (let j = 0; j < G; j++) for (let i = 0; i < G; i++){ const r2 = (i - A.c0) ** 2 + (j - A.c0) ** 2; mix[j * G + i] = (1 - ao) * 1.6 * smax * Math.exp(-r2 / (2 * sd * sd)) + ao * F0[j * G + i]; }
      st.opt.aoImg = mxGridImage(mix, G, logTone); st.opt.aoKey = key; }
    if (st.opt.adiK !== k){ st.opt.adiK = k;
      st.opt.frameImg = mxGridImage(A.frames[k], G, logTone);
      const top = Math.max(1e-6, A.Ap * 0.8); st.opt.stackImg = mxGridImage(A.stacks[k], G, v => Math.max(0, v) / top * 0.9); }
    if (!st.opt.medImg) st.opt.medImg = mxGridImage(A.med, G, logTone);
    mxCgFrame(c, ps[0], ao < 1 ? 'Adaptive optics: on' : 'AO on', ao < 1 ? 'deformable mirror switching on' : 'core and speckles, λ/D wide', st.opt.aoImg, t < 0.22);
    mxCgFrame(c, ps[1], `Frame ${k + 1} of ${A.N}`, `field rotation ${A.ang[k].toFixed(0)}°`, st.opt.frameImg, t >= 0.22);
    mxCgFrame(c, ps[2], 'Median of the frames', 'speckles only: the model', st.opt.medImg, t >= 0.22);
    mxCgFrame(c, ps[3], `Stack of ${k + 1}`, 'frame − median, turned back', st.opt.stackImg, t >= 0.22);
    // The planet's track on the raw frame (it turns with the sky) and its place in the stack.
    const sc = ps[1].s / G, a0 = (A.o.pa + A.ang[k]) * Math.PI / 180;
    c.strokeStyle = 'rgba(100,210,255,.6)'; c.setLineDash([2, 3]); c.beginPath(); c.arc(ps[1].x + (A.c0 + .5) * sc, ps[1].y + (A.c0 + .5) * sc, A.o.rp * sc, A.o.pa * Math.PI / 180, a0); c.stroke(); c.setLineDash([]);
    if (t >= 0.22){ const r = A.o.rp * sc; c.strokeStyle = '#64D2FF'; c.beginPath(); c.arc(ps[1].x + (A.c0 + .5) * sc + r * Math.cos(a0), ps[1].y + (A.c0 + .5) * sc + r * Math.sin(a0), 3 * A.sig * sc + 3, 0, 2 * Math.PI); c.stroke(); }
    if (k >= 4){ c.strokeStyle = '#64D2FF'; c.beginPath(); c.arc(ps[3].x + (A.px + .5) * sc, ps[3].y + (A.py + .5) * sc, 3 * A.sig * sc + 3, 0, 2 * Math.PI); c.stroke(); }
    mxCgArrows(c, ps, L.narrow);
    // Signal-to-noise against frames stacked.
    mxGlassPanel(c, lx - 44, ly - 22, lw + 56, lh + 50);
    const kh = mxCgKey(c, lx, ly - 6, lw, [{label: 'stack of the first n frames', color: '#FFB340'}, {label: `one raw frame: S/N ${A.snrRaw.toFixed(1)}`, color: 'rgba(255,255,255,.6)', dash: [4, 4]}]);
    ly += kh + 14; lh -= kh + 14;
    mxAxes(c, lx, ly, lw, lh, {y: 'PLANET SIGNAL-TO-NOISE', x: 'FRAMES STACKED'});
    const smaxN = Math.max(...A.snr, A.snrRaw, 5) * 1.1, X = i => lx + (i + 0.5) / A.N * lw, Y = v => ly + lh - Math.max(0, v) / smaxN * lh;
    for (const v of [0, 5, 10, 15, 20, 25]) if (v < smaxN){ c.strokeStyle = 'rgba(255,255,255,.07)'; c.lineWidth = 1; c.beginPath(); c.moveTo(lx, Y(v)); c.lineTo(lx + lw, Y(v)); c.stroke(); mxText(c, String(v), lx - 6, Y(v) + 4, {size: 11, mono: true, align: 'right'}); }
    for (const i of [0, 11, 23]) mxText(c, String(i + 1), X(i), ly + lh + 13, {size: 11, mono: true, align: 'center'});
    for (let i = 0; i <= k; i++){ c.fillStyle = i === k ? '#FFB340' : 'rgba(255,179,64,.45)'; const bw = Math.max(2, lw / A.N - 3); c.fillRect(X(i) - bw / 2, Y(A.snr[i]), bw, ly + lh - Y(A.snr[i])); }
    c.strokeStyle = 'rgba(255,255,255,.5)'; c.setLineDash([4, 4]); c.beginPath(); c.moveTo(lx, Y(A.snrRaw)); c.lineTo(lx + lw, Y(A.snrRaw)); c.stroke(); c.setLineDash([]);
    mxHead(c, w, `speckles stay, the planet turns · stack of ${k + 1}: S/N ${A.snr[k].toFixed(1)}`);
    st.exag = 'synthetic frames: speckle pattern, noise and planet brightness illustrative; log stretch on the raw frames';
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
      oddeven: 'alternate depths differ: two stars, period really twice as long (SetuHQ flags odd_even_mismatch)',
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
// Each normal mode (methods.py: mode_table) carries its displacement pattern, its band and its stated
// exaggeration: the drawn peak displacement (MX_MODE_A) against the zero-point RMS of the atom that moves most.
const MX_MODE_A = 0.2, MX_VIB_CYCLES = 12;
function mxModeOptions(m){ return (m.modes || []).map((d, i) => `<option value="${i}">${esc(mxModeName(d))}${d.um ? ` · ${d.um.toFixed(2)} µm` : ''}${d.ir ? '' : ' · IR-silent'}</option>`).join(''); }
const mxModeName = d => (d.nu ? d.nu + ' ' : '') + d.name;
// A log wavelength axis, 0.5 to 25 µm: the molecule's modes (filled: infrared-active; hollow: silent) and the window
// the Reading-atmospheres chapter draws (0.5 to 5.1 µm).
function mxBandAxis(c, x, y, w, m, cur){
  const lo = Math.log10(0.5), hi = Math.log10(25), X = um => x + (Math.log10(um) - lo) / (hi - lo) * w;
  c.fillStyle = 'rgba(100,210,255,.10)'; c.fillRect(X(0.5), y - 10, X(5.1) - X(0.5), 20);
  mxText(c, 'drawn in Reading atmospheres', x + 4, y - 14, {size: 11, color: '#64D2FF'});
  c.strokeStyle = 'rgba(255,255,255,.35)'; c.lineWidth = 1; c.beginPath(); c.moveTo(x, y); c.lineTo(x + w, y); c.stroke();
  for (const um of [0.5, 1, 2, 5, 10, 20]){ c.beginPath(); c.moveTo(X(um), y - 3); c.lineTo(X(um), y + 3); c.stroke(); mxText(c, um === 0.5 ? '0.5 µm' : `${um}`, X(um), y + 16, {size: 11, mono: true, align: um === 0.5 ? 'left' : 'center'}); }
  (m.modes || []).forEach((d, i) => { if (!d.um) return; const xx = X(d.um), on = i === cur;
    c.strokeStyle = on ? '#FFB340' : 'rgba(255,255,255,.7)'; c.fillStyle = on ? '#FFB340' : 'rgba(255,255,255,.7)'; c.lineWidth = on ? 2 : 1.2;
    c.beginPath(); c.arc(xx, y, on ? 5.5 : 4, 0, 2 * Math.PI); d.ir ? c.fill() : c.stroke(); });
}
MXV.molecule = {key: 0.15, period: 14, init(st){ st.opt.mol = MX.molecules[0]; st.opt.mode = 0; },
  control(st, el){
    if (el.tagName !== 'SELECT') return;
    if (el.dataset.ctl === 'mode'){ st.opt.mode = Number(el.value) || 0; return; }
    st.opt.mol = MX.molecules.find(m => m.id === el.value) || MX.molecules[0];
    if (st.opt.mode >= (st.opt.mol.modes || []).length) st.opt.mode = 0;   // keep the chosen mode where this molecule has it
    document.querySelectorAll('.mxmol').forEach(a => a.classList.toggle('on', a.dataset.mol === st.opt.mol.id));
    const ms = st.fig.querySelector('select[data-ctl="mode"]');
    if (ms){ const has = (st.opt.mol.modes || []).length; ms.innerHTML = has ? mxModeOptions(st.opt.mol) : '<option value="0">No vibrations drawn</option>'; ms.disabled = !has; ms.value = String(st.opt.mode); }
  },
  draw(c, w, h, t, st){
    const m = st.opt.mol, atoms = mxAtoms(m.geom), narrow = w < 600, sc = Math.min(w, h) * (narrow ? 0.2 : 0.22), ry = t * 2 * Math.PI, rx = 0.35;
    const mode = (m.modes || [])[st.opt.mode] || null, ph = Math.sin(t * 2 * Math.PI * MX_VIB_CYCLES);
    const cy = h * (narrow ? 0.46 : 0.48);
    const P = atoms.map(([el, x, y, z], i) => { const d = mode ? mode.disp[i] : [0, 0, 0]; x += MX_MODE_A * ph * d[0]; y += MX_MODE_A * ph * d[1]; z += MX_MODE_A * ph * d[2];
      const x1 = x * Math.cos(ry) + z * Math.sin(ry), z1 = -x * Math.sin(ry) + z * Math.cos(ry), y1 = y * Math.cos(rx) - z1 * Math.sin(rx), z2 = y * Math.sin(rx) + z1 * Math.cos(rx);
      // The displacement direction, turned the same way, for the arrow.
      const dx1 = d[0] * Math.cos(ry) + d[2] * Math.sin(ry), dz1 = -d[0] * Math.sin(ry) + d[2] * Math.cos(ry), dy1 = d[1] * Math.cos(rx) - dz1 * Math.sin(rx);
      return {el, x: w / 2 + x1 * sc, y: cy - y1 * sc, z: z2, ax: dx1, ay: -dy1, mag: Math.hypot(d[0], d[1], d[2])}; });
    if (P.length > 1){ c.strokeStyle = 'rgba(255,255,255,.5)'; c.lineWidth = 5; for (let i = 1; i < P.length; i++){ const j = m.geom.shape === 'linear' && m.geom.r2 && i === 2 ? 1 : 0; c.beginPath(); c.moveTo(P[j].x, P[j].y); c.lineTo(P[i].x, P[i].y); c.stroke(); } }
    for (const a of P.slice().sort((p, q) => p.z - q.z)){
      const rad = (a.el === 'H' ? 0.22 : a.el.length > 1 || a.el === 'K' ? 0.5 : 0.34) * sc, col = MX_CPK[a.el] || '#C7C7CC';
      const g = c.createRadialGradient(a.x - rad * 0.3, a.y - rad * 0.3, rad * 0.1, a.x, a.y, rad); g.addColorStop(0, '#FFFFFF'); g.addColorStop(0.35, col); g.addColorStop(1, '#111');
      c.fillStyle = g; c.beginPath(); c.arc(a.x, a.y, rad, 0, 2 * Math.PI); c.fill();
      mxText(c, a.el, a.x, a.y + 4, {size: 11, w: 700, align: 'center', color: a.el === 'H' || a.el === 'S' ? '#000' : '#FFF'});
      if (mode && a.mag > 0.05){ // where this atom moves (both ways), drawn over it
        const L = sc * 0.55 * a.mag, ux = a.ax / (Math.hypot(a.ax, a.ay) || 1), uy = a.ay / (Math.hypot(a.ax, a.ay) || 1);
        c.strokeStyle = 'rgba(255,179,64,.85)'; c.lineWidth = 1.5; c.beginPath(); c.moveTo(a.x - ux * L, a.y - uy * L); c.lineTo(a.x + ux * L, a.y + uy * L); c.stroke();
        for (const s of [-1, 1]){ const tx = a.x + s * ux * L, ty = a.y + s * uy * L; c.beginPath(); c.moveTo(tx, ty); c.lineTo(tx - s * (ux * 6 - uy * 4), ty - s * (uy * 6 + ux * 4)); c.moveTo(tx, ty); c.lineTo(tx - s * (ux * 6 + uy * 4), ty - s * (uy * 6 - ux * 4)); c.stroke(); }
      }
    }
    mxText(c, `${m.f} · ${m.name}`, 14, 22, {size: 14, w: 600, color: '#F5F5F7'});
    const g = m.geom; mxText(c, g.shape === 'atom' ? 'single atom' : `${g.shape === 'dms' ? 'C–S–C core (hydrogens not drawn)' : g.shape}: bond ${g.r} Å${g.angle ? `, angle ${g.angle}°` : ''} (NIST CCCBDB)`, 14, 40, {size: 11});
    if (mode){
      mxText(c, `${mxModeName(mode)}${mode.deg > 1 ? ` (one of ${mode.deg})` : ''}`, 14, 58, {size: 12, w: 600, color: '#FFB340'});
      mxText(c, mode.um ? `${mode.um.toFixed(2)} µm · ${mode.ir ? 'infrared-active' : 'infrared-silent: the dipole does not change'}` : `${mode.ir ? 'infrared-active' : 'infrared-silent'}; the atlas lists no wavelength`, 14, 74, {size: 11});
    } else mxText(c, g.shape === 'atom' ? 'a single atom has no vibrations; its lines are electronic' : 'its 21 modes are not drawn: the atlas gives band regions only', 14, 58, {size: 11});
    c.strokeStyle = '#C7C7CC'; c.lineWidth = 1; c.beginPath(); c.moveTo(14, h - 70); c.lineTo(14 + sc, h - 70); c.stroke(); mxText(c, '1 Å', 14 + sc / 2, h - 76, {size: 11, align: 'center'});
    if (m.modes && m.modes.length) mxBandAxis(c, 24, h - 26, w - 48, m, st.opt.mode);
    if (P.length > 1){
      if (mode && mode.exag){ const slow = (st.vis.period / MX_VIB_CYCLES / (st.speed || 1)) / (mode.um * 1e-6 / MX_C);
        st.exag = `amplitude ×${mode.exag} (zero-point RMS of ${mode.atom} ≈ ${mode.rms.toFixed(3)} Å); time slowed ≈10${mxSup(Math.round(Math.log10(slow)))}×; sizes of atoms illustrative`; }
      else if (mode) st.exag = 'amplitude and time illustrative (no frequency in the atlas); sizes of atoms illustrative';
      else st.exag = 'sizes of atoms illustrative';
    }
  }};

// ---------- the section ----------
function mxShowChapter(ch){
  if (!MX) return;
  if (!MX.chapters.includes(ch)) ch = MX.chapters[0];
  $$('#route-methods .mxch').forEach(a => { const on = a.dataset.ch === ch; if (a.hidden === on){ a.hidden = !on; } mxActivate(a, on && current === 'methods'); });
  $$('#route-methods .mxtoc a').forEach(a => { if (a.dataset.ch === ch) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current'); });
  mxCurrent = ch;
  // A chapter's own page opens with its title (the section's introduction is the first chapter's page only).
  const hd = $('#route-methods > header.headrow'), h1 = $('#h-methods'), deep = ch !== MX.chapters[0];
  if (h1){ if (!h1.dataset.intro) h1.dataset.intro = h1.innerHTML; h1.innerHTML = deep ? esc(MX.labels[ch]) : h1.dataset.intro; }
  if (hd) hd.classList.toggle('deep', deep);
  if (ch === 'equations') mxEquationsInit();
}
let mxCurrent = null;
function mxShown(on){ if (!MX) return; $$('#route-methods .mxch').forEach(a => mxActivate(a, on && !a.hidden)); }
function renderMethods(){ /* the chapters are static HTML; stages start when their chapter opens */ }
// Every system view (Methods, the Transit case, the Galaxy's sheet, planet and star pages) goes through here:
// it draws from the stored values given, and says in the caption which values are not stored.
const MX_KEYS = [['star temperature', 'star_teff'], ['star radius', 'star_radius'], ['planet radius', 'radius'], ['orbital period', 'orbital_period'], ['semi-major axis', 'semi_major_axis'], ['inclination', 'inclination']];
function mxSystemView(fig, p, o){
  o = o || {};
  const st = mxSetup(fig), S = mxSystemParams(p, o.dip || null);
  st.opt.sys = S;
  const missing = MX_KEYS.filter(([, k]) => p[k] == null).map(([l]) => l);
  const nonTransit = p.inclination != null && p.semi_major_axis && p.star_radius && S.ars * Math.cos(p.inclination * Math.PI / 180) > 1 + S.k;
  const note = `Drawn from stored values only (${o.source || MX.source}${o.fetched ? ', fetched ' + o.fetched.slice(0, 10) : ''}).` + (missing.length ? ` Not stored: ${missing.join(', ')}; those parts are illustrative and say so on the drawing.` : '')
    + (p.star_teff == null ? ' Star colour: the Sun’s, as the temperature is not stored.' : '') + (p.orbital_period == null ? ' Period not stored: the time axis is illustrative.' : '')
    + (nonTransit ? ' At the stored inclination this planet does not transit; the view shows a transit to explain the method.' : '');
  const desc = `${p.name}: a ${Math.round(S.teff).toLocaleString('en-GB')} K star drawn in its blackbody colour, the planet crossing at b = ${S.b.toFixed(2)} (${S.bSrc}), and a limb-darkened model light curve from the stored values.`;
  fig.querySelector('canvas').setAttribute('aria-label', o.desc || desc);
  if (o.caption !== false) fig.querySelector('figcaption').textContent = note;
  st.on = !!o.on; st.t = MXV.system.key; mxDraw(st);
  if (st.on && !mxRM.matches && !st.started){ st.started = true; mxPlay(st, true); } else mxKick(st);
  return {st, S, note, desc};
}
// The Galaxy's "system view" sheet: the same animated system for any stored example planet. Opened from a point on
// a map (from = {x, y, kind}), it arrives through a magnifier: a lens that opens from that point.
function mxOpenSystem(name, back, from){
  const p = MX && MX.examples[name]; if (!p) return;
  let dlg = $('#mxsheet');
  if (!dlg){
    dlg = document.createElement('dialog'); dlg.id = 'mxsheet'; dlg.className = 'mxsheet';
    dlg.innerHTML = `<div class="mxsheethead"><h2 id="mxsheettitle"></h2><button class="btn" type="button" id="mxsheetclose">Close</button></div>${$('#mxsystpl').innerHTML}<p class="mxsheetzoom" id="mxsheetzoom" hidden></p><p class="mxsheetnote" id="mxsheetnote"></p>`;
    document.body.appendChild(dlg);
    $('#mxsheetclose').addEventListener('click', () => dlg.close());
    dlg.addEventListener('close', () => { const st = dlg.querySelector('.mxstage')._mx; if (st){ st.on = false; }
      // A zoom still under way when the sheet closes is cut short: no lens is left behind.
      dlg.getAnimations().forEach(a => a.cancel()); const ln = dlg.querySelector('.mxlens'); if (ln) ln.remove();
      if (dlg._back) dlg._back.focus(); });
  }
  dlg._back = back || null;
  const fig = dlg.querySelector('.mxstage');
  $('#mxsheettitle').textContent = name;
  const z = from ? mxZoomInfo(p, from.kind) : null, zn = $('#mxsheetzoom');
  zn.hidden = !from;
  if (from) zn.textContent = (z ? `From the ${from.kind === 'sky' ? 'sky map' : 'Galaxy map'} to this orbit is a jump of about ${z.v} in scale (${z.what}). ` : '')
    + 'The zoom between them is an illustration of scale, not continuous data.';
  if (!dlg.open) dlg.showModal();
  mxSystemView(fig, Object.assign({name}, p), {dip: name === 'pi Men c' && MX.lead_dip ? {pts: MX.lead_dip.pts} : null, on: true, fetched: MX.fetched_at});
  // The canonical pages for this planet and its star.
  $('#mxsheetnote').innerHTML = `${objLink('planet', name, name + ' ›')} ${p.star_name ? objLink('star', p.star_name, p.star_name + ' ›') : ''}`;
  $('#mxsheetclose').focus();
  if (from && !mxRM.matches && dlg.animate) mxZoomLens(dlg, from, z);
}
const mxSup = n => String(n).split('').map(d => '⁰¹²³⁴⁵⁶⁷⁸⁹'['0123456789'.indexOf(d)] || (d === '-' ? '⁻' : d)).join('');
// How far the zoom jumps, from stored values: on the Galaxy map, from the star's distance to its orbit (both
// lengths); on the sky map, from the whole sky (2π radians) to the orbit's angle on the sky, a/d.
function mxZoomInfo(p, kind){
  const d = p.star_distance, a = p.semi_major_axis; if (!(d > 0 && a > 0)) return null;
  const dAU = d * 206264.806, ly = d * 3.26156;
  if (kind === 'sky') return {v: mxSig1(2 * Math.PI / (a / dAU)), what: `the whole sky, then an orbit of ${a} AU seen from ${ly.toFixed(1)} light-years, ${(a / dAU * 206264806).toPrecision(2)} milliarcseconds across`};
  return {v: mxSig1(dAU / a), what: `${ly.toFixed(1)} light-years to the star, ${a} AU from star to planet`};
}
// A number to one significant figure, as 4×10⁸.
function mxSig1(x){ let e = Math.floor(Math.log10(x)), m = Math.round(x / Math.pow(10, e)); if (m === 10){ m = 1; e++; } return `${m}×10${mxSup(e)}`; }
// The magnifier: the sheet is revealed through a growing circle centred on the point that was chosen, with a lens rim
// and a label that says what the zoom is. Never under reduced motion (the sheet simply opens).
function mxZoomLens(dlg, from, z){
  const r = dlg.getBoundingClientRect(), x = from.x - r.left, y = from.y - r.top;
  const R = Math.hypot(Math.max(x, r.width - x), Math.max(y, r.height - y)) + 4, dur = 950, ease = 'cubic-bezier(.2,.8,.2,1)';
  dlg.animate([{clipPath: `circle(28px at ${x}px ${y}px)`}, {clipPath: `circle(28px at ${x}px ${y}px)`, offset: 0.2}, {clipPath: `circle(${R}px at ${x}px ${y}px)`}], {duration: dur, easing: ease});
  const old = dlg.querySelector('.mxlens'); if (old) old.remove();
  const lens = document.createElement('div'); lens.className = 'mxlens'; lens.setAttribute('aria-hidden', 'true');
  lens.innerHTML = `<i style="left:${x}px;top:${y}px"></i><span>${z ? `zoom ≈ ×${z.v} · ` : ''}an illustration of scale, not continuous data</span>`;
  dlg.appendChild(lens);
  lens.querySelector('i').animate([{width: '56px', height: '56px', opacity: 1}, {width: '56px', height: '56px', opacity: 1, offset: 0.2}, {width: `${2 * R}px`, height: `${2 * R}px`, opacity: 0.15}], {duration: dur, easing: ease, fill: 'forwards'});
  lens.querySelector('span').animate([{opacity: 0}, {opacity: 1, offset: 0.12}, {opacity: 1, offset: 0.75}, {opacity: 0}], {duration: dur + 900, fill: 'forwards'});
  setTimeout(() => lens.remove(), dur + 950);
}

// ---------- the survey-scan intro on the Sky and Galaxy maps ----------
// The Methods "survey scan", played once over a map the first time its section opens in a session: about five
// seconds, a Skip button, and no pointer capture, so the map underneath stays live; the first touch, wheel or key
// on the map ends it. It draws only while its section is shown, on screen and the tab visible, and never under
// reduced motion.
const MX_INTRO_MS = 5200, MX_INTRO_T = 0.62;
const mxIntros = {};
function mxIntroStart(key, host){
  if (!MX || !host || mxRM.matches || mxIntros[key]) return;
  let seen = false; try { seen = sessionStorage.getItem('setuhq-intro-' + key) === 'done'; } catch (e) { /* storage blocked: play it */ }
  if (seen){ mxIntros[key] = {done: true}; return; }
  const el = document.createElement('div'); el.className = 'mxintro';
  el.innerHTML = '<canvas aria-hidden="true"></canvas><div class="mxintrobar" role="group" aria-label="Introduction animation">'
    + MX.ill_badge + '<span class="mxintrocap">A survey checks stars one at a time · star positions illustrative</span>'
    + '<button class="btn mxskip" type="button">Skip intro</button></div>';
  host.appendChild(el);
  const I = {key, host, el, cv: el.querySelector('canvas'), st: {opt: {intro: true}, vis: MXV.scan, exag: ''}, ms: 0, last: 0, raf: 0, visible: false, done: false, frames: 0};
  MXV.scan.init(I.st); I.st.opt.intro = true;
  mxIntros[key] = I;
  el.querySelector('.mxskip').addEventListener('click', () => mxIntroEnd(I, true));
  I.touch = e => { if (e && e.target && e.target.closest && e.target.closest('.mxskip')) return; mxIntroEnd(I, false); };
  for (const ev of ['pointerdown', 'wheel', 'keydown']) host.addEventListener(ev, I.touch, {passive: true});
  if ('IntersectionObserver' in window){ I.io = new IntersectionObserver(es => { I.visible = es[es.length - 1].isIntersecting; mxIntroKick(I); }); I.io.observe(host); }
  else I.visible = true;
  mxIntroDraw(I, 0);
  mxIntroKick(I);
}
const mxIntroLive = I => !I.done && I.visible && !document.hidden && current === I.key;
function mxIntroKick(I){ if (I && !I.done && !I.raf && mxIntroLive(I)){ I.last = 0; I.raf = requestAnimationFrame(ts => mxIntroFrame(I, ts)); } }
function mxIntroFrame(I, ts){
  I.raf = 0;
  if (!mxIntroLive(I)) return;
  I.ms += I.last ? Math.min(100, ts - I.last) : 16; I.last = ts; I.frames++;
  const f = Math.min(1, I.ms / MX_INTRO_MS);
  mxIntroDraw(I, f);
  if (f >= 1){ mxIntroEnd(I, false); return; }
  I.raf = requestAnimationFrame(t2 => mxIntroFrame(I, t2));
}
function mxIntroDraw(I, f){
  const box = I.el.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1), w = Math.round(box.width), h = Math.round(box.height);
  if (w < 2 || h < 2) return;
  if (I.cv.width !== Math.round(w * dpr) || I.cv.height !== Math.round(h * dpr)){ I.cv.width = Math.round(w * dpr); I.cv.height = Math.round(h * dpr); }
  const c = I.cv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h);
  c.fillStyle = 'rgba(0,0,0,.66)'; c.fillRect(0, 0, w, h);
  MXV.scan.draw(c, w, h, f * MX_INTRO_T, I.st);
}
function mxIntroEnd(I, skipped){
  if (!I || I.done) return;
  I.done = true;
  if (I.raf){ cancelAnimationFrame(I.raf); I.raf = 0; }
  if (I.io) I.io.disconnect();
  for (const ev of ['pointerdown', 'wheel', 'keydown']) I.host.removeEventListener(ev, I.touch);
  try { sessionStorage.setItem('setuhq-intro-' + I.key, 'done'); } catch (e) { /* storage blocked */ }
  I.el.classList.add('out'); setTimeout(() => I.el.remove(), 420);
  if (skipped && typeof say === 'function') say('Intro skipped.');
}
// The router calls this on every section change: an intro starts on its own section and ends when it is left.
function mxIntroRoute(r){
  if (r === 'sky') mxIntroStart('sky', $('#route-sky .skymap'));
  if (r === 'galaxy') mxIntroStart('galaxy', $('#gxstage'));
  for (const k in mxIntros){ const I = mxIntros[k]; if (I.done) continue; if (k !== r) mxIntroEnd(I, false); else mxIntroKick(I); }
}
document.addEventListener('visibilitychange', () => { for (const k in mxIntros) mxIntroKick(mxIntros[k]); });
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
#route-methods>header.deep p,#route-methods>header.deep~.mxch>header h2{display:none}
#route-methods>header.deep~.mxch>header .eyebrow{margin:0}
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
}
.mxladder div span{position:absolute;left:0;transform:translateX(-50%);white-space:nowrap;font-size:12px;color:var(--ink-2)}
.mxladder div.l span{transform:none}
.mxladder div.r span{transform:translateX(-100%)}
.mxladder .mxaxis{position:absolute;left:0;right:0;bottom:0;margin:0;display:flex;justify-content:space-between;font:500 11px var(--mono);color:var(--ink-3)}
@media (max-width:499.98px){
  /* Phone: the axis sits below the last rung, with room, at the rungs' 0.6 scale (after the rule above, so it wins). */
  .mxladder .mxaxis{position:relative;width:60%;height:24px;margin-top:14px;border-top:1px solid var(--line)}
  .mxladder .mxaxis span{position:absolute;top:6px;white-space:nowrap}
  .mxladder .mxaxis span:nth-child(2),.mxladder .mxaxis span:nth-child(4){display:none}
  .mxladder .mxaxis span:nth-child(1){left:0}
  .mxladder .mxaxis span:nth-child(3){left:50%;transform:translateX(-50%)}
  .mxladder .mxaxis span:nth-child(5){right:0}
}
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
.mxclaims{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px;margin:8px 0 14px}
.mxclaim,.mxseti{border:1px solid var(--line);border-radius:16px;padding:12px 14px;background:var(--glass-2);min-width:0}
.mxclaim h4,.mxseti h4{margin:4px 0 6px;font-size:16px}
.mxclaim p,.mxseti p{margin:0 0 6px;font-size:13.5px;line-height:1.5}
.mxseti{margin:14px 0;border-style:dashed}
.mxstatus{display:inline-block;margin:0;padding:3px 10px;border-radius:999px;border:1px solid;font:600 11px/1.4 var(--sans);letter-spacing:.02em}
.mxstatus.tent{color:var(--amber);border-color:var(--amber)}
.mxstatus.cont{color:var(--coral);border-color:var(--coral)}
.mxstatus.cand{color:var(--cyan);border-color:var(--cyan)}
.mxstatus.seti{color:var(--ink-2);border-color:var(--line-3)}
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
.mxsheetzoom{margin:8px 0 0;font-size:12.5px;color:var(--ink-2)}
/* the zoom lens: a rim that opens from the chosen point, and its label (the sheet's clip-path does the reveal) */
.mxlens{position:absolute;inset:0;pointer-events:none;overflow:hidden;border-radius:inherit;z-index:3}
.mxlens i{position:absolute;display:block;transform:translate(-50%,-50%);border-radius:50%;border:2px solid rgba(255,255,255,.75);box-shadow:0 0 0 1px rgba(0,0,0,.45),inset 0 0 24px rgba(100,210,255,.35)}
.mxlens span{position:absolute;left:50%;top:64px;transform:translateX(-50%);max-width:calc(100% - 24px);padding:6px 12px;border-radius:999px;background:rgba(28,28,30,.86);border:1px solid rgba(255,255,255,.16);color:#F5F5F7;font:500 12px/1.4 var(--sans);text-align:center}
/* the survey-scan intro over the Sky and Galaxy maps: no pointer capture except its Skip button */
.mxintro{position:absolute;inset:0;z-index:6;pointer-events:none;transition:opacity .4s var(--ease)}
.mxintro.out{opacity:0}
.mxintro canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.mxintrobar{position:absolute;right:12px;top:12px;display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;max-width:calc(100% - 24px);color:#F5F5F7}
.mxintrobar .mxlabel.ill{color:#C7C7CC;border-color:rgba(255,255,255,.3);background:rgba(0,0,0,.5)}
.mxintrocap{font-size:12px;color:#C7C7CC;padding:4px 10px;border-radius:999px;background:rgba(0,0,0,.5)}
.mxintro .mxskip{pointer-events:auto;min-height:44px;color:#F5F5F7;background:rgba(28,28,30,.86);border-color:rgba(255,255,255,.22)}
@media (max-width:599.98px){.mxintrocap{display:none}}
@media (prefers-reduced-motion: reduce){.mxintro{display:none}.mxintro,.mxlens i,.mxlens span{transition:none;animation:none}}
/* the stylised Lyot plate: drawn in the page's ink, so it follows the theme */
.mxplate{margin:4px 0 0;display:grid;gap:8px;max-width:900px}
.mxplate svg{width:100%;height:auto;display:block;color:var(--ink-2);font:500 11px var(--sans)}
.mxplate svg.v{display:none;max-width:420px}
@media (max-width:599.98px){.mxplate svg.h{display:none}.mxplate svg.v{display:block}}
.mxplate svg text{fill:var(--ink-2);font-family:var(--sans);font-size:11px;letter-spacing:0}
.mxplate svg text.sm{fill:var(--ink-3)}
.mxplate .pf{fill:var(--panel-2);stroke:var(--line-3)}
.mxplate .pf2{fill:none;stroke:var(--line-2)}
.mxplate .axis{stroke:var(--line-3);stroke-dasharray:2 5;fill:none}
.mxplate .st{stroke:var(--amber);stroke-width:1.3;fill:none}
.mxplate .df{stroke:var(--amber);stroke-width:1;stroke-dasharray:3 3;fill:none;opacity:.8}
.mxplate .cp{stroke:var(--cyan);stroke-width:1.2;fill:none}
.mxplate .ln{fill:var(--cyan-soft);stroke:var(--ink-2);stroke-width:1.1}
.mxplate .disc{fill:var(--ink)}
.mxplate .rod{stroke:var(--ink-3);stroke-width:1}
.mxplate .stop{stroke:var(--ink);stroke-width:5;stroke-linecap:round}
.mxplate .det{stroke:var(--ink-2);stroke-width:3}
.mxplate .im{fill:#000}
.mxplate .fr{fill:none;stroke:var(--line-3)}
.mxplate .g0{fill:#FFF8E7}.mxplate .g1{fill:rgba(255,190,90,.75)}.mxplate .g2{fill:rgba(94,42,140,.7)}.mxplate .g3{fill:none;stroke:rgba(255,190,90,.25);stroke-width:5}
.mxplate .blk{fill:#000}
.mxplate .rim{fill:rgba(255,190,90,.9)}
.mxplate .stp{fill:none;stroke:#64D2FF;stroke-dasharray:2 2}
.mxplate .pl{fill:#64D2FF}
.mxmodes{margin:0;padding-left:16px;display:grid;gap:4px}
.mxmodes a{display:inline-flex;align-items:center}
@media (max-width:699.98px){
  .mxcanvas{height:min(62vh,440px)}
  .mxstage.tall .mxcanvas{height:min(76vh,560px)}
  .mxstage[data-vis="cgfam"] .mxcanvas{height:min(84vh,660px)}
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
  .mxsrc a,.mxmodes a{min-height:44px}
}
"""

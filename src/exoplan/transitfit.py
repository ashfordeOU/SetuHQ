"""A limb-darkened transit model and fit, replacing the box: depth, duration, impact parameter and mid-time
with uncertainties, plus the stellar-density and V-shape tests.

Model. A circular orbit; the planet is a dark disc of radius k (in stellar radii) at sky separation z(t).
The star has the quadratic limb-darkening law I(μ)/I(1) = 1 − u1(1 − μ) − u2(1 − μ)² with Claret (2017) TESS
coefficients interpolated in Teff and log g (``docs/results/claret2017_tess_quadratic.json``). The blocked
flux is integrated numerically over the covered part of the disc (in radius, with the covered arc at each
radius), which is exact up to quadrature error for any k, so the same code models planets and grazing
eclipsing binaries. Long cadences are supersampled.

Parameters. Mid-time t0, radius ratio k, total duration T14, impact parameter b, and a linear baseline. Given
the period P, a/R★ follows from T14, b and k (Winn 2010, eq. 14); for a single transit with no period, P is set
long (the chord is then straight and a/R★ is not reported). The fit is least squares with bounds; the 1σ
errors come from the covariance, scaled up by √χ²ᵣ when the scatter exceeds the stated errors.

Tests built on the fit:
* ``rho_star``: ρ★ = 3π/(GP²)(a/R★)³ (Seager & Mallén-Ornelas 2003), compared with the catalogue value
  (``rho_ratio``). A ratio outside 0.3–3 is flagged; those bounds are illustrative (ATLAS C4), not published.
* ``v_shape``: the best fit is grazing (b > 1 − k) and forcing a full transit costs Δχ² > 9 (ATLAS E4). A
  V shape is evidence for an eclipsing binary, not proof: grazing planets exist.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

LD_TABLE = Path(__file__).resolve().parents[2] / "docs" / "results" / "claret2017_tess_quadratic.json"
G_SI = 6.67430e-11  # m³ kg⁻¹ s⁻² (CODATA 2018)
DAY = 86400.0
SUN_TEFF, SUN_LOGG = 5772.0, 4.438
RHO_BOUNDS = (0.3, 3.0)  # illustrative bounds on ρ★(transit)/ρ★(catalogue) (ATLAS C4), not a published threshold
V_SHAPE_DCHI2 = 9.0     # a forced full transit worse by more than this (3σ for one parameter) marks a V shape


# ---------- limb darkening ----------
@lru_cache(maxsize=1)
def _ld_grid() -> dict:
    data = json.loads(LD_TABLE.read_text())
    grid: dict[float, list[tuple[float, float, float]]] = {}
    for logg, teff, u1, u2 in data["rows"]:
        grid.setdefault(float(logg), []).append((float(teff), float(u1), float(u2)))
    for rows in grid.values():
        rows.sort()
    return grid


def _interp_teff(rows, teff: float) -> tuple[float, float]:
    if teff <= rows[0][0]:
        return rows[0][1], rows[0][2]
    if teff >= rows[-1][0]:
        return rows[-1][1], rows[-1][2]
    for (t0, a0, b0), (t1, a1, b1) in zip(rows, rows[1:]):
        if t0 <= teff <= t1:
            f = (teff - t0) / (t1 - t0)
            return a0 + f * (a1 - a0), b0 + f * (b1 - b0)
    return rows[-1][1], rows[-1][2]


def ld_coeffs(teff: float | None, logg: float | None) -> tuple[float, float]:
    """Claret (2017) TESS quadratic (u1, u2): linear in Teff within each tabulated log g, then linear in log g;
    clamped at the table's edges. Missing values fall back to the Sun's."""
    teff = SUN_TEFF if teff is None or not np.isfinite(teff) else float(teff)
    logg = SUN_LOGG if logg is None or not np.isfinite(logg) else float(logg)
    grid = _ld_grid()
    gs = sorted(grid)
    if logg <= gs[0]:
        return _interp_teff(grid[gs[0]], teff)
    if logg >= gs[-1]:
        return _interp_teff(grid[gs[-1]], teff)
    for g0, g1 in zip(gs, gs[1:]):
        if g0 <= logg <= g1:
            a0, b0 = _interp_teff(grid[g0], teff)
            a1, b1 = _interp_teff(grid[g1], teff)
            f = (logg - g0) / (g1 - g0)
            return a0 + f * (a1 - a0), b0 + f * (b1 - b0)
    return _interp_teff(grid[gs[-1]], teff)


# ---------- the model ----------
_NODES, _WEIGHTS = np.polynomial.legendre.leggauss(24)


def occulted_flux(z, k: float, u1: float, u2: float) -> np.ndarray:
    """Relative flux of a quadratically limb-darkened star occulted by a dark disc of radius k at separation z.

    The blocked light is ∫ I(r) · 2α(r) · r dr over the covered radii, with α the covered half-angle of the
    annulus at r. The substitution r = r₀ + (r₁ − r₀)(1 − cos θ)/2 removes the square-root endpoint
    behaviour so 24-point Gauss–Legendre is accurate to ~10⁻⁷ of the stellar flux."""
    z = np.atleast_1d(np.asarray(z, float))
    out = np.ones_like(z)
    hit = z < 1 + k
    if not np.any(hit) or k <= 0:
        return out
    zz = z[hit][:, None]
    r0 = np.maximum(0.0, zz - k)
    r1 = np.minimum(1.0, zz + k)
    # When the planet covers the disc centre (z < k), the covered arc is the whole annulus out to r = k − z
    # and a partial arc beyond: the integrand has a kink there, so the two pieces are integrated apart.
    rm = np.clip(k - zz, r0, r1)
    theta = 0.5 * math.pi * (_NODES + 1.0)          # Gauss–Legendre nodes on [0, π]
    w = 0.5 * math.pi * _WEIGHTS

    def piece(a, b):
        r = a + (b - a) * 0.5 * (1 - np.cos(theta))
        dr = (b - a) * 0.5 * np.sin(theta)
        with np.errstate(invalid="ignore", divide="ignore"):
            c = (r * r + zz * zz - k * k) / (2 * r * np.maximum(zz, 1e-12))
        alpha = np.where(r <= k - zz, math.pi, np.arccos(np.clip(c, -1.0, 1.0)))
        alpha = np.where(zz <= 1e-12, np.where(r <= k, math.pi, 0.0), alpha)
        mu = np.sqrt(np.clip(1 - r * r, 0.0, 1.0))
        intensity = 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2
        return np.sum(w * intensity * 2 * alpha * r * dr, axis=1)

    blocked = piece(r0, rm) + piece(rm, r1)
    out[hit] = 1 - blocked / (math.pi * (1 - u1 / 3 - u2 / 6))
    return out


def a_over_r(t14: float, b: float, k: float, period: float) -> float:
    """a/R★ from the total duration, impact parameter and radius ratio, circular orbit (Winn 2010, eq. 14)."""
    s = math.sin(math.pi * t14 / period)
    if s <= 0 or b >= 1 + k:
        return float("nan")
    return math.sqrt(((1 + k) ** 2 - b * b) / (s * s) + b * b)


def transit_model(t, t0: float, k: float, t14: float, b: float, period: float, u1: float, u2: float,
                  exptime: float = 0.0, supersample: int = 1) -> np.ndarray:
    """Relative flux of a circular-orbit transit; exptime (days) with ``supersample`` sub-samples per cadence."""
    t = np.asarray(t, float)
    if supersample > 1 and exptime > 0:
        off = (np.arange(supersample) + 0.5) / supersample - 0.5
        tt = (t[:, None] + off[None, :] * exptime).ravel()
        return transit_model(tt, t0, k, t14, b, period, u1, u2).reshape(t.size, supersample).mean(axis=1)
    ars = a_over_r(t14, b, k, period)
    if not np.isfinite(ars) or ars <= 1:
        return np.ones_like(t)
    cosi = b / ars
    phi = 2 * math.pi * (t - t0) / period
    z = ars * np.sqrt(np.sin(phi) ** 2 + (cosi * np.cos(phi)) ** 2)
    flux = occulted_flux(np.where(np.cos(phi) > 0, z, 10.0), k, u1, u2)
    return flux


def model_depth(k: float, b: float, u1: float, u2: float) -> float:
    """The depth at mid-transit (1 − flux at z = b)."""
    return float(1 - occulted_flux(np.array([b]), k, u1, u2)[0])


def t23(t14: float, b: float, k: float, period: float) -> float:
    """Flat-bottom duration T23 (0 for a grazing transit), circular orbit (Winn 2010, eq. 15)."""
    ars = a_over_r(t14, b, k, period)
    if not np.isfinite(ars) or b >= 1 - k:
        return 0.0
    sini = math.sqrt(max(0.0, 1 - (b / ars) ** 2))
    return period / math.pi * math.asin(min(1.0, math.sqrt((1 - k) ** 2 - b * b) / (ars * sini)))


def rho_star(ars: float, period_days: float) -> float:
    """Mean stellar density (g/cm³) from a/R★ and P: 3π(a/R★)³/(GP²) (the planet's term neglected)."""
    return 3 * math.pi * ars ** 3 / (G_SI * (period_days * DAY) ** 2) / 1000.0


def rho_catalogue(mass_msun: float | None, radius_rsun: float | None) -> float | None:
    """ρ★ (g/cm³) from catalogue mass and radius (IAU nominal solar values)."""
    if not mass_msun or not radius_rsun:
        return None
    m = mass_msun * 1.98840987e30  # GM☉/G with the IAU nominal GM☉ and CODATA G
    r = radius_rsun * 6.957e8
    return m / (4 / 3 * math.pi * r ** 3) / 1000.0


# ---------- the fit ----------
@dataclass(frozen=True)
class TransitFit:
    t0: float
    t0_err: float
    k: float
    k_err: float
    depth_ppm: float
    depth_err_ppm: float
    t14_hours: float
    t14_err_hours: float
    b: float
    b_err: float
    t23_hours: float
    period_days: float | None
    a_rs: float | None
    rho_star: float | None
    rho_star_err: float | None
    u1: float
    u2: float
    chi2: float
    dof: int
    n_points: int
    n_epochs: int
    grazing: bool
    v_shape_dchi2: float | None
    v_shape: bool
    rho_catalogue: float | None = None
    rho_ratio: float | None = None
    rho_flag: bool = False
    notes: tuple = field(default_factory=tuple)
    # 1σ ranges from the profile over b (the errors above are their half-widths).
    b_range: tuple | None = None
    rho_range: tuple | None = None
    depth_range_ppm: tuple | None = None
    t14_range_hours: tuple | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["notes"] = list(self.notes)
        for key in ("b_range", "rho_range", "depth_range_ppm", "t14_range_hours"):
            d[key] = list(d[key]) if d[key] is not None else None
        return d


def _cadence(time: np.ndarray) -> float:
    return float(np.median(np.diff(time))) if time.size > 1 else 0.0


def fit_transit(time, flux, flux_err, *, t0: float, duration: float, depth: float, period: float | None = None,
                u1: float, u2: float, epochs: list[float] | None = None, window: float = 2.5,
                stellar_density: float | None = None, fit_t0: bool = True) -> TransitFit | None:
    """Fit the limb-darkened model around one transit, or jointly around every epoch in ``epochs`` (same shape,
    fixed period, one free reference mid-time). ``duration`` and ``depth`` are the starting guesses (days, and
    a fraction). Returns ``None`` when there are too few points to fit."""
    time, flux, flux_err = (np.asarray(a, float) for a in (time, flux, flux_err))
    centres = list(epochs) if epochs else [t0]
    half = window * max(duration, 1 / 24)
    sel = np.zeros(time.size, bool)
    for c in centres:
        sel |= np.abs(time - c) <= half
    sel &= np.isfinite(flux) & np.isfinite(flux_err) & (flux_err > 0)
    t, f, e = time[sel], flux[sel], flux_err[sel]
    if t.size < 12:
        return None
    cad = _cadence(t)
    ss = 5 if cad > 4 / 1440 else 1
    p_model = period if period else max(100.0 * duration, 30.0)
    # Each epoch's offset from the reference: the reference mid-time t0 moves, the epochs follow it.
    if epochs and period:
        n_ep = np.round((t - t0) / period)
    else:
        n_ep = np.zeros_like(t)
    tref = float(np.median(t))

    def unpack(x):
        tc, k, t14, s, c0, c1 = x
        return tc, k, t14, s * (1 + k), c0, c1

    def model(x, tt=t, nn=n_ep):
        tc, k, t14, b, c0, c1 = unpack(x)
        local = tt - nn * (period or 0.0)
        return transit_model(local, tc, k, t14, b, p_model, u1, u2, exptime=cad, supersample=ss) * (c0 + c1 * (tt - tref))

    def resid(x):
        return (f - model(x)) / e

    k0 = math.sqrt(max(depth, 1e-6))
    dt = 0.5 * duration if fit_t0 else 1e-9
    lo = [t0 - dt, 1e-3, max(2 * cad, 0.25 * duration), 0.0, 0.9, -1.0]
    hi = [t0 + dt + 1e-9, 0.9, min(4.0 * duration, 0.45 * p_model), 0.999, 1.1, 1.0]
    best = None
    for s0 in (0.1, 0.45, 0.8):
        x0 = [t0, min(max(k0, 1.1e-3), 0.85), min(max(duration, lo[2] * 1.01), hi[2] * 0.99), s0, 1.0, 0.0]
        try:
            r = least_squares(resid, x0, bounds=(lo, hi), x_scale="jac", max_nfev=400)
        except ValueError:
            continue
        if best is None or r.cost < best.cost:
            best = r
    if best is None:
        return None
    x = best.x
    chi2 = float(2 * best.cost)
    dof = max(1, t.size - len(x))
    scale = max(1.0, chi2 / dof)

    def derived(xx):
        tc_, k_, t14_, b_, _, _ = unpack(xx)
        ars_ = a_over_r(t14_, b_, k_, period) if period else float("nan")
        return {"depth": model_depth(k_, b_, u1, u2), "b": b_, "t14": t14_, "k": k_,
                "rho": rho_star(ars_, period) if period and np.isfinite(ars_) and ars_ > 1 else float("nan")}

    # The impact parameter trades off against a/R★ and k at modest S/N, so its error (and those of the depth,
    # duration and ρ★ that depend on it) comes from a profile: b is stepped across [0, 1 + k), the other
    # parameters refit at each step, and the 1σ range is where χ² is within 1 (× χ²ᵣ when > 1) of the best.
    prof = []
    warm = list(x)
    for s_fix in np.linspace(0.0, 0.995, 15):
        def resid_s(y, s_fix=s_fix):
            return resid([y[0], y[1], y[2], s_fix, y[3], y[4]])
        lo5, hi5 = [lo[0], lo[1], lo[2], lo[4], lo[5]], [hi[0], hi[1], hi[2], hi[4], hi[5]]
        r = None
        # Start from the neighbouring step's solution; if that lands well above the best free fit, try again
        # from the best free fit's solution.
        for y0 in ([warm[0], warm[1], warm[2], warm[4], warm[5]], [x[0], x[1], x[2], x[4], x[5]]):
            y0 = [min(max(v, a + 1e-12), b_ - 1e-12) for v, a, b_ in zip(y0, lo5, hi5)]
            try:
                rr = least_squares(resid_s, y0, bounds=(lo5, hi5), x_scale="jac", max_nfev=300)
            except ValueError:
                continue
            if r is None or rr.cost < r.cost:
                r = rr
            if r.cost <= best.cost + 2.0:
                break
        if r is None:
            continue
        xs = [r.x[0], r.x[1], r.x[2], s_fix, r.x[3], r.x[4]]
        prof.append((float(2 * r.cost), xs))
        warm = xs
    if prof and min(c for c, _ in prof) < chi2:
        chi2, x = min(prof, key=lambda p: p[0])
        x = np.asarray(x)
    tc, k, t14, b, _, _ = unpack(x)
    base = derived(x)
    near = [derived(np.asarray(xs)) for c, xs in prof if c <= chi2 + scale] + [base]
    near3 = [derived(np.asarray(xs)) for c, xs in prof if c <= chi2 + 9 * scale] + [base]

    def span(key, pts=None):
        vals = [d[key] for d in (pts or near) if np.isfinite(d[key])]
        return (min(vals), max(vals)) if vals else (float("nan"), float("nan"))

    # Statistical errors at the best fit (the covariance, scaled by χ²ᵣ when above 1), carried to the derived
    # quantities by finite differences; the profile's spread along b is added in quadrature below.
    try:
        fin = least_squares(resid, np.clip(x, np.asarray(lo) + 1e-12, np.asarray(hi) - 1e-12), bounds=(lo, hi), x_scale="jac", max_nfev=50)
        cov = np.linalg.pinv(fin.jac.T @ fin.jac) * scale
    except (ValueError, np.linalg.LinAlgError):
        cov = np.full((len(x), len(x)), np.nan)
    t0_err = float(np.sqrt(max(cov[0, 0], 0))) if np.isfinite(cov[0, 0]) else float("nan")
    keys = ("depth", "t14", "k", "b", "rho")
    vec = lambda xx: np.array([derived(xx)[kk] for kk in keys], float)
    v0 = vec(x)
    dj = np.zeros((len(keys), len(x)))
    for i in range(len(x)):
        h = max(1e-8, 1e-4 * abs(x[i]) + 1e-9)
        xp = np.array(x, float)
        xp[i] = x[i] + h if x[i] + h <= hi[i] else x[i] - h
        dj[:, i] = (vec(xp) - v0) / (xp[i] - x[i])
    stat = dict(zip(keys, np.sqrt(np.clip(np.diag(np.nan_to_num(dj) @ np.nan_to_num(cov) @ np.nan_to_num(dj).T), 0, None))))
    d_lo, d_hi = span("depth")
    t_lo, t_hi = span("t14")
    b_lo, b_hi = span("b")
    k_lo, k_hi = span("k")
    r_lo, r_hi = span("rho")

    # The V-shape test: the best fit is grazing, and the best full transit (b ≤ 1 − k) is worse by Δχ² > 9.
    grazing = b > 1 - k
    full = [c for c, xs in prof if xs[3] * (1 + xs[1]) <= 1 - xs[1]]
    dchi2 = (min(full) - chi2) / scale if full else None
    v_shape = bool(grazing and dchi2 is not None and dchi2 > V_SHAPE_DCHI2)
    ars = a_over_r(t14, b, k, period) if period else None
    rho = base["rho"] if period and np.isfinite(base["rho"]) else None
    ratio = rho / stellar_density if rho is not None and stellar_density else None
    # Flag the density only when its whole 3σ range (Δχ² ≤ 9 on the b profile) lies outside the illustrative
    # band around the catalogue value: b is often weakly constrained, and a 1σ range would flag noise.
    r3_lo, r3_hi = span("rho", near3)
    rho_flag = bool(rho is not None and stellar_density and np.isfinite(r3_lo) and np.isfinite(r3_hi)
                    and (r3_lo > RHO_BOUNDS[1] * stellar_density or r3_hi < RHO_BOUNDS[0] * stellar_density))
    notes = []
    if not period:
        notes.append("single transit: no period, so a/R★ and ρ★ are not constrained")
    def half_w(a, b_, key=None):
        prof_hw = float(0.5 * (b_ - a)) if np.isfinite(a) and np.isfinite(b_) else 0.0
        st = float(stat.get(key, 0.0)) if key else 0.0
        return float(math.hypot(prof_hw, st if np.isfinite(st) else 0.0))
    return TransitFit(
        t0=float(tc), t0_err=t0_err, k=float(k), k_err=half_w(k_lo, k_hi, "k"),
        depth_ppm=float(base["depth"]) * 1e6, depth_err_ppm=half_w(d_lo, d_hi, "depth") * 1e6,
        t14_hours=float(t14) * 24, t14_err_hours=half_w(t_lo, t_hi, "t14") * 24,
        b=float(b), b_err=half_w(b_lo, b_hi, "b"), t23_hours=t23(t14, b, k, p_model) * 24,
        period_days=period, a_rs=float(ars) if ars is not None and np.isfinite(ars) else None,
        rho_star=rho, rho_star_err=half_w(r_lo, r_hi, "rho") if rho is not None else None, u1=u1, u2=u2,
        chi2=float(chi2), dof=int(dof), n_points=int(t.size), n_epochs=len(centres), grazing=bool(grazing),
        v_shape_dchi2=float(dchi2) if dchi2 is not None else None, v_shape=v_shape,
        rho_catalogue=stellar_density, rho_ratio=ratio, rho_flag=rho_flag, notes=tuple(notes),
        b_range=(float(b_lo), float(b_hi)), rho_range=(float(r_lo), float(r_hi)) if rho is not None else None,
        depth_range_ppm=(float(d_lo) * 1e6, float(d_hi) * 1e6), t14_range_hours=(float(t_lo) * 24, float(t_hi) * 24),
    )


def inject_transit(time, t_mid: float, depth: float, duration: float, *, b: float = 0.3, u1: float | None = None,
                   u2: float | None = None, period: float | None = None, exptime: float = 0.0) -> np.ndarray:
    """Relative flux of a limb-darkened transit with the given mid-transit depth (fraction) and total duration
    (days): the same model the fit uses, for injection. k is solved so the model depth equals ``depth``."""
    if u1 is None or u2 is None:
        u1, u2 = ld_coeffs(SUN_TEFF, SUN_LOGG)
    k = math.sqrt(depth)
    for _ in range(30):
        d = model_depth(k, b, u1, u2)
        if d <= 0:
            k *= 1.5
            continue
        k_new = k * math.sqrt(depth / d)
        if abs(k_new - k) < 1e-10:
            break
        k = k_new
    p = period if period else max(100.0 * duration, 30.0)
    ss = 5 if exptime > 4 / 1440 else 1
    return transit_model(np.asarray(time, float), t_mid, k, duration, b, p, u1, u2, exptime=exptime, supersample=ss)

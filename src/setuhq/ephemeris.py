"""Ephemeris propagation with its uncertainty cone, and predicted transit windows (ATLAS G5).

A transit n orbits after the reference epoch is at T_n = T0 + n P, with
σ(T_n)² = σ_T0² + n² σ_P² + 2 n cov(T0, P). The covariance term is used when it is known and taken as zero
otherwise (the published TOI table gives no covariance). The uncertainty grows linearly with n: the cone.
:func:`setuhq.discover.match_toi` uses the same propagation to match dips to published ephemerides.

A predicted window is the transit (T14) widened by ``n_sigma`` σ(T_n) on each side, so an observer covering the
window sees the whole transit with that confidence, if the ephemeris holds (no TTVs, no decay).

Times. SetuHQ's reference times are BTJD (BJD_TDB − 2457000). The windows also give BJD_TDB and, for scheduling,
UTC at the geocentre: with the star's RA and Dec the barycentric light-travel time is removed (astropy, built-in
solar-system ephemeris, offline); without them the UTC time is only the TDB time relabelled, wrong by up to about
8.3 minutes, and marked approximate.
"""

from __future__ import annotations

import math

BTJD_OFFSET = 2457000.0


def propagate(t0: float, t0_err: float | None, period: float, period_err: float | None, n: int | float,
              cov: float | None = None) -> tuple[float, float]:
    """(T_n, σ(T_n)) for epoch ``n``. Missing errors count as zero; ``cov`` is cov(T0, P) in day²."""
    s0 = float(t0_err or 0.0)
    sp = float(period_err or 0.0)
    var = s0 * s0 + (n * sp) ** 2 + 2.0 * n * float(cov or 0.0)
    return t0 + n * period, math.sqrt(max(var, 0.0))


def _utc(bjd_tdb: float, ra: float | None, dec: float | None) -> tuple[str, bool]:
    """UTC ISO time at the geocentre of a BJD_TDB instant, and whether it is exact (light-travel time removed)."""
    from astropy.time import Time

    t = Time(bjd_tdb, format="jd", scale="tdb")
    if ra is None or dec is None:
        return t.utc.isot, False
    from astropy import units as u
    from astropy.coordinates import EarthLocation, SkyCoord

    coord = SkyCoord(ra * u.deg, dec * u.deg)
    geocentre = EarthLocation.from_geocentric(0 * u.m, 0 * u.m, 0 * u.m)
    guess = Time(bjd_tdb, format="jd", scale="tdb", location=geocentre)
    for _ in range(2):  # the light-travel time depends on the (geocentric) time itself: two iterations converge
        ltt = guess.light_travel_time(coord, kind="barycentric")
        guess = Time(bjd_tdb - ltt.to_value("day"), format="jd", scale="tdb", location=geocentre)
    return guess.utc.isot, True


def transit_windows(*, t0: float, t0_err: float | None, period: float, period_err: float | None,
                    duration_hours: float, start: float, end: float, cov: float | None = None, n_sigma: float = 3.0,
                    ra: float | None = None, dec: float | None = None, with_utc: bool = True) -> list[dict]:
    """Every predicted transit with mid-time between ``start`` and ``end`` (BTJD), with σ and the window.

    Each row: epoch n (from ``t0``), mid-time in BTJD and BJD_TDB, σ in hours, the window start and end
    (mid ∓ (T14/2 + ``n_sigma`` σ)) in BTJD, and the UTC mid-time and window (see the module docstring)."""
    if period <= 0:
        return []
    out = []
    for n in range(math.ceil((start - t0) / period), math.floor((end - t0) / period) + 1):
        mid, sig = propagate(t0, t0_err, period, period_err, n, cov)
        half = 0.5 * duration_hours / 24.0 + n_sigma * sig
        row = {"epoch": n, "t_mid_btjd": mid, "t_mid_bjd_tdb": mid + BTJD_OFFSET, "sigma_hours": sig * 24.0,
               "window_start_btjd": mid - half, "window_end_btjd": mid + half, "window_hours": 2 * half * 24.0,
               "n_sigma": n_sigma}
        if with_utc:
            row["t_mid_utc"], exact = _utc(mid + BTJD_OFFSET, ra, dec)
            row["window_start_utc"], _ = _utc(mid - half + BTJD_OFFSET, ra, dec)
            row["window_end_utc"], _ = _utc(mid + half + BTJD_OFFSET, ra, dec)
            row["utc_exact"] = exact
        out.append(row)
    return out


def cone(*, t0: float, t0_err: float | None, period: float, period_err: float | None, cov: float | None = None,
         at: float) -> dict:
    """The ephemeris uncertainty at time ``at`` (BTJD): the nearest epoch and its σ in hours."""
    n = round((at - t0) / period)
    mid, sig = propagate(t0, t0_err, period, period_err, n, cov)
    return {"at_btjd": at, "epoch": n, "t_mid_btjd": mid, "sigma_hours": sig * 24.0}

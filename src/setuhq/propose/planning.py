# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Rough planning numbers: ESTIMATES for drafting, never a replacement for ESA's tools.

Precision. White noise per hour of integration, as a function of Gaia G, interpolated in log space between
measured in-flight values from Fortier et al. 2024, "CHEOPS in-flight performance: A comprehensive look at the
first 3.5 years of operations", A&A 687, A302 (arXiv:2406.01716):

* bright anchor: HD 88111 (G = 8.97), 12.8 ppm in a 6-hour bin in 2023 (section 5.2, Fig. 18), which is
  31.4 ppm in one hour if the noise is white. The paper's ETC example for G = 9 (13 ppm in 6 h, 237.2 ppm in
  1 minute) gives 31.8 and 30.6 ppm in one hour: the white-noise scaling holds there.
* faint anchor, conservative: G = 12, 120 ppm in 3 h (section 4.4, read from Fig. 17), 208 ppm in one hour.
* faint anchor, optimistic: G = 12, 85 ppm in 3 h (Science Requirement 1.2, met by the measured light curves of
  TYC 5502-1037-1, G = 11.98, in some years: 68-117 ppm in 3 h, section 5.2), 147 ppm in one hour.

The model ignores red noise, stellar granulation and activity, contamination, stray light, SAA and Earth
occultation gaps beyond the efficiency factor, and the instrument's ageing after 2023. It is not calibrated
outside 8.5 <= G <= 12.5 and says so. A CHEOPS orbit is 98.7 minutes (Fortier et al. 2024, section 2).

Orbits for a signal-to-noise. For a transit or eclipse of depth d (ppm) and duration T (h), observed with a
baseline of B hours outside the event and an observing efficiency e, the depth error from one visit is
sigma_1h * sqrt(1/(T e) + 1/(B e)); the number of events is the square of target S/N over one event's S/N, rounded up.
For a flare of peak amplitude A and duration T the per-flare S/N is A sqrt(T e) / sigma_1h; with a flare rate the
orbits needed to expect a number of flares follow.

Ephemeris. The mid-time uncertainty propagated to the window, sigma(T_n)^2 = sigma_T0^2 + n^2 sigma_P^2
(``setuhq.ephemeris``), is added on both sides of each visit at ``n_sigma``.

Sky. The Sun must be more than 117 degrees from the line of sight (a hard constraint, ESA's CHEOPS Sky Visibility
page). The Sun is on the ecliptic, so a target at ecliptic latitude beta is never more than 180 - |beta| degrees
from it: beyond |beta| = 63 degrees that constraint can never be met. This is one geometric screen; passing it
says nothing about visibility, which only ESA's Visibility Tool or Scheduling Feasibility Checker can establish.
"""

from __future__ import annotations

import math

ORBIT_MINUTES = 98.7
REFERENCE = ("Fortier, A., et al. 2024, A&A 687, A302, 'CHEOPS in-flight performance: A comprehensive look at the "
             "first 3.5 years of operations' (arXiv:2406.01716)")
G_BRIGHT, SIGMA1H_BRIGHT = 8.97, 12.8 * math.sqrt(6.0)
G_FAINT = 12.0
SIGMA1H_FAINT = {"conservative": 120.0 * math.sqrt(3.0), "optimistic": 85.0 * math.sqrt(3.0)}
CALIBRATED_RANGE = (8.5, 12.5)
SUN_EXCLUSION_DEG = 117.0
SKY_PAGE = "https://www.cosmos.esa.int/web/cheops/the-cheops-sky"

ESA_TOOLS = {
    "Exposure Time Calculator": "https://cheops.unige.ch/pht2/exposure-time-calculator/",
    "Visibility Tool and Scheduling Feasibility Checker (ESA Datalabs)":
        "https://www.cosmos.esa.int/web/cheops-guest-observers-programme/visibility-checks",
    "Target Checker": "https://cheops.unige.ch/pht2/search-reserved-targets/",
}
CONFIRM = ("Confirm with ESA's Exposure Time Calculator, Visibility Tool and Scheduling Feasibility Checker: "
           + "; ".join(f"{k} <{v}>" for k, v in ESA_TOOLS.items()) + ".")
ESTIMATE_LABEL = ("ESTIMATE for drafting only, from a simple model of published in-flight performance; not an ESA "
                  "tool output and not a feasibility or visibility statement.")


def sigma_1h(gmag: float, case: str = "conservative") -> float:
    """White-noise precision in ppm for one hour of integration at Gaia magnitude ``gmag`` (see module text)."""
    slope = math.log10(SIGMA1H_FAINT[case] / SIGMA1H_BRIGHT) / (G_FAINT - G_BRIGHT)
    return 10 ** (math.log10(SIGMA1H_BRIGHT) + slope * (gmag - G_BRIGHT))


def precision(gmag: float | None, efficiency: float = 0.7) -> dict:
    """Precision per hour, per 3 h, per 6 h and per CHEOPS orbit, in both cases, with caveats."""
    if gmag is None:
        return {"available": False, "note": "No Gaia G magnitude: give --gmag (the ETC needs it too).",
                "label": ESTIMATE_LABEL, "confirm": CONFIRM}
    if not 0 < efficiency <= 1:
        raise ValueError("efficiency must be in (0, 1]")
    orbit_h = ORBIT_MINUTES / 60.0
    out = {"available": True, "gmag": gmag, "efficiency_assumed": efficiency, "orbit_minutes": ORBIT_MINUTES,
           "label": ESTIMATE_LABEL, "reference": REFERENCE, "confirm": CONFIRM, "cases": {}}
    for case in ("conservative", "optimistic"):
        s = sigma_1h(gmag, case)
        out["cases"][case] = {"ppm_1h": s, "ppm_3h": s / math.sqrt(3), "ppm_6h": s / math.sqrt(6),
                              "ppm_per_orbit": s / math.sqrt(orbit_h * efficiency)}
    lo, hi = CALIBRATED_RANGE
    if not lo <= gmag <= hi:
        out["warning"] = (f"G = {gmag:.2f} is outside {lo}-{hi}, where the anchors lie: the extrapolation is "
                          "unreliable" + (" (bright stars approach photon noise; saturation and exposure settings "
                                          "matter)" if gmag < lo else
                                          "; beyond G ~ 12 precision varies a lot with stray light and contamination, "
                                          "and the TAC decides on much fainter targets (P&P section 4.6)") + ".")
    out["efficiency_note"] = ("The efficiency is a placeholder: take the value for your window from the Visibility "
                              "Tool or SFC (SAA crossings and Earth occultations).")
    return out


def orbits_needed(*, gmag: float, depth_ppm: float, duration_hours: float, target_snr: float, event: str = "transit",
                  efficiency: float = 0.7, ephemeris_sigma_hours: float = 0.0, n_sigma: float = 3.0,
                  baseline_hours: float | None = None, flare_rate_per_day: float | None = None,
                  n_flares: int = 1, case: str = "conservative", min_orbits_per_visit: int = 5) -> dict:
    """Orbits to reach ``target_snr`` on an event, with the visit layout; an ESTIMATE (see the module text)."""
    if min(depth_ppm, duration_hours, target_snr) <= 0:
        raise ValueError("depth, duration and target S/N must be positive")
    orbit_h = ORBIT_MINUTES / 60.0
    s1 = sigma_1h(gmag, case)
    out = {"event": event, "case": case, "depth_ppm": depth_ppm, "duration_hours": duration_hours,
           "target_snr": target_snr, "efficiency_assumed": efficiency, "label": ESTIMATE_LABEL, "confirm": CONFIRM}
    if event == "flare":
        snr1 = depth_ppm * math.sqrt(duration_hours * efficiency) / s1
        out |= {"snr_per_event": snr1, "detectable_per_flare": snr1 >= target_snr}
        if flare_rate_per_day and flare_rate_per_day > 0:
            hours = n_flares / flare_rate_per_day * 24.0
            out |= {"flare_rate_per_day": flare_rate_per_day, "n_flares_expected": n_flares,
                    "on_target_hours": hours, "orbits_total": math.ceil(hours / (orbit_h * efficiency))}
        else:
            out["note"] = "Give --flare-rate (flares per day above this amplitude) to turn this into orbits."
        return out
    pad = n_sigma * max(ephemeris_sigma_hours, 0.0)
    base = baseline_hours if baseline_hours is not None else max(duration_hours, 2 * orbit_h)
    visit_h = duration_hours + 2 * pad + base
    needed = max(1, math.ceil(visit_h / orbit_h))
    per_visit = max(min_orbits_per_visit, needed)  # P&P 4.4: at least 5 orbits per visit for high precision
    base_actual = per_visit * orbit_h - duration_hours  # the visit is whole orbits; the rest is baseline
    sig_depth = s1 * math.sqrt(1 / (duration_hours * efficiency) + 1 / (base_actual * efficiency))
    snr1 = depth_ppm / sig_depth
    n_events = max(1, math.ceil((target_snr / snr1) ** 2))
    out |= {"sigma_depth_ppm_per_event": sig_depth, "snr_per_event": snr1, "events_needed": n_events,
            "orbits_per_visit": per_visit, "orbits_total": n_events * per_visit, "orbits_for_layout": needed,
            "visit_minimum_applied": per_visit > needed,
            "visit_layout_hours": {"event": duration_hours, "ephemeris_pad_each_side": pad,
                                   "baseline_requested": base, "visit": per_visit * orbit_h},
            "ephemeris_sigma_hours": ephemeris_sigma_hours, "n_sigma": n_sigma}
    if event == "eclipse":
        out["note"] = "Secondary eclipse: the depth is the planet's dayside signal in the CHEOPS band, your input."
    return out


def ephemeris_in_window(*, t0: float, t0_err: float | None, period: float, period_err: float | None,
                        start_jd: float, end_jd: float, source: str) -> dict:
    """The mid-time uncertainty at the start and end of a window (BJD_TDB in, hours out)."""
    from setuhq.ephemeris import BTJD_OFFSET, cone

    t0_btjd = t0 - BTJD_OFFSET if t0 > 2.4e6 else t0
    a = cone(t0=t0_btjd, t0_err=t0_err, period=period, period_err=period_err, at=start_jd - BTJD_OFFSET)
    b = cone(t0=t0_btjd, t0_err=t0_err, period=period, period_err=period_err, at=end_jd - BTJD_OFFSET)
    n_in = max(0, math.floor((end_jd - BTJD_OFFSET - t0_btjd) / period) - math.ceil((start_jd - BTJD_OFFSET - t0_btjd) / period) + 1)
    out = {"source": source, "t0_btjd": t0_btjd, "t0_err_days": t0_err, "period_days": period,
           "period_err_days": period_err, "window_start": a, "window_end": b,
           "sigma_hours_max": max(a["sigma_hours"], b["sigma_hours"]), "transits_in_window": n_in,
           "note": "sigma(T_n)^2 = sigma_T0^2 + n^2 sigma_P^2; covariance taken as zero (not published)."}
    if not t0_err or not period_err:
        out["warning"] = ("No uncertainty for T0 or P in this source: the propagated sigma is a lower bound. "
                          "Give --t0-err and --period-err.")
    return out


def sun_screen(ra: float | None, dec: float | None) -> dict:
    """The one geometric check SetuHQ makes: can the 117-degree Sun exclusion ever be met? Not a visibility check."""
    if ra is None or dec is None:
        return {"checked": False}
    from astropy import units as u
    from astropy.coordinates import BarycentricMeanEcliptic, SkyCoord

    beta = float(SkyCoord(ra * u.deg, dec * u.deg, frame="icrs").transform_to(BarycentricMeanEcliptic()).lat.deg)
    max_sun = 180.0 - abs(beta)
    ok = bool(max_sun > SUN_EXCLUSION_DEG)
    return {"checked": True, "ecliptic_latitude_deg": beta, "max_sun_angle_deg": max_sun,
            "sun_exclusion_deg": SUN_EXCLUSION_DEG, "can_meet_sun_constraint": ok, "source": SKY_PAGE,
            "statement": ("Passes this single geometric screen only. That is NOT a visibility result: Earth stray "
                          "light, the Moon, the SAA and the season decide when (and whether) the target is "
                          "observable. Use ESA's Visibility Tool or SFC.") if ok else
                         (f"At ecliptic latitude {beta:.1f} deg the Sun is never more than {max_sun:.1f} deg from "
                          f"the target, so ESA's stated {SUN_EXCLUSION_DEG:g} deg Sun-exclusion hard constraint "
                          "cannot be met at any time of year. The target is very likely not observable; check "
                          "the Visibility Tool before investing further.")}

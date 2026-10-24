# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The stellar tools for an AI assistant (MCP): flares, a pulsation spectrum, CHEOPS light curves, eclipsing
binaries, rotation periods and transients.

Thin wrappers over :mod:`setuhq.flares`, :mod:`setuhq.pulsations`, :mod:`setuhq.cheops`, :mod:`setuhq.binaries`,
:mod:`setuhq.rotation` and :mod:`setuhq.transients`, answering in the same
envelope as every tool of :mod:`setuhq.tools` (result, provenance, honesty labels). Each carries the validation
status of its capability as measured in ``docs/results/stellar_validation.json`` or, for the protocol v4
capabilities, ``docs/results/stellar_validation_v4.json`` ("not validated" when the file does not say otherwise),
and every answer built on CHEOPS data carries ESA's acknowledgement, the programme and visit ids, the credit line,
the citations and SetuHQ's independence disclaimer.
"""

from __future__ import annotations

import json

DETECTED = ("Flares and frequencies are detected at the significance stated with each one; a detection is not a "
            "confirmation, and a variability type is a heuristic label (likely or candidate), not a classification.")
ENERGY = ("Flare energies assume a 9000 K blackbody flare and use TIC Teff and radius; without them the energy is "
          "reported as unavailable, never guessed.")
VALIDATION_FILE = "docs/results/stellar_validation.json"
# Protocol v4's capabilities (eclipsing binaries, rotation, transients) have their own record beside it.
VALIDATION_FILE_V4 = "docs/results/stellar_validation_v4.json"
V4_CAPABILITIES = ("binaries", "rotation", "transients")
MAX_POINTS = 200_000
NO_RECORD = "not validated (no validation record)"


def validation_file(capability: str) -> str:
    return VALIDATION_FILE_V4 if capability in V4_CAPABILITIES else VALIDATION_FILE


def validation_status(capability: str) -> str:
    """The capability's status from the committed validation record, with its count: 'validated (n of n checks
    pass)', 'partly validated (k of n …)' when more than half pass, otherwise 'not validated (k of n …)'."""
    from setuhq.tools import _path

    try:
        data = json.loads(_path(validation_file(capability)).read_text())
    except Exception:  # noqa: BLE001 (no record: not validated)
        return NO_RECORD
    cap = (data.get("capabilities") or {}).get(capability) or {}
    return cap.get("label") or cap.get("status") or NO_RECORD


def _arrays(csv_path, time, flux, flux_err, target):
    from setuhq.tools import ToolError, _lightcurve

    if time is not None and len(time) > MAX_POINTS:
        raise ToolError(f"at most {MAX_POINTS} points per call")
    lc, sources = _lightcurve(csv_path, time, flux, flux_err, target)
    return lc, sources


def find_flares(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                flux_err: list[float] | None = None, mission: str = "TESS", denoise: bool = False,
                teff: float | None = None, radius_rsun: float | None = None, tmag: float | None = None,
                distance_pc: float | None = None, target: str = "custom") -> dict:
    """Detect and characterise stellar flares in a light curve (``flares.detect_flares``): flare-preserving
    detrend, sigma-clipping candidates (Chang et al. 2015 criteria), optional wavelet denoising (Poyatos et al.
    2025), Mendoza et al. 2022 template fits with multi-component models chosen by BIC, rise/decay times,
    amplitude, FWHM, equivalent duration, and energies (9000 K blackbody) when Teff and radius are given. Also
    runs the flux-inverted null. Time in days (BTJD for TESS); mission TESS or CHEOPS sets the defaults."""
    from setuhq import flares as fl
    from setuhq.tools import COMPUTED, ToolError, envelope

    if mission.upper() not in ("TESS", "CHEOPS"):
        raise ToolError("mission must be TESS or CHEOPS")
    if denoise and not fl.have_pywavelets():
        raise ToolError("denoise=True needs PyWavelets on the server: pip install 'setuhq[wavelets]'")
    lc, sources = _arrays(csv_path, time, flux, flux_err, target)
    star = {"teff": teff, "radius": radius_rsun, "tmag": tmag, "distance_pc": distance_pc}
    band = mission.upper()
    cfg = fl.config_for(band, (lc.time[1] - lc.time[0]) * 86400.0 if len(lc) > 1 else None, denoise=denoise)
    out = fl.detect_flares(lc.time, lc.flux, lc.flux_err, config=cfg, star=star, band=band)
    null = fl.inverted_null(lc.time, lc.flux, lc.flux_err, config=cfg, band=band)
    for f in out["flares"]:
        f.pop("models", None)
    status = validation_status("flares")
    result = {"flares": out["flares"], "summary": out["summary"], "config": out["config"], "template": out["template"],
              "inverted_null": {k: null[k] for k in ("false_positives", "observing_days", "rate_per_day")},
              "validation_status": status}
    honesty = [COMPUTED, DETECTED, ENERGY, f"Flare detection is {status} (see {VALIDATION_FILE})."]
    if band == "CHEOPS":
        from setuhq.cheops import ACKNOWLEDGEMENT, DISCLAIMER

        honesty += [ACKNOWLEDGEMENT, DISCLAIMER]
    return envelope("find_flares", result, sources=sources, honesty=honesty)


def pulsation_spectrum(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                       flux_err: list[float] | None = None, teff: float | None = None, fmin: float | None = None,
                       fmax: float | None = None, max_frequencies: int = 40, n_surrogates: int = 0,
                       target: str = "custom") -> dict:
    """Frequency analysis of a light curve (``pulsations.analyse``): Lomb-Scargle amplitude spectrum, iterative
    pre-whitening with a non-linear multi-sine refit down to S/N 4 (Breger et al. 1993), combination-frequency
    flags, a Harvey-profile granulation background, numax/Δν for solar-like oscillators, and a heuristic
    variability type with its uncertainty. Frequencies in d⁻¹ and µHz; time in days. n_surrogates > 0 runs the
    red-noise null (at most 20)."""
    from setuhq import pulsations as pu
    from setuhq.tools import COMPUTED, ToolError, envelope

    if not 1 <= int(max_frequencies) <= 100:
        raise ToolError("max_frequencies must be 1 to 100")
    if not 0 <= int(n_surrogates) <= 20:
        raise ToolError("n_surrogates must be 0 to 20")
    lc, sources = _arrays(csv_path, time, flux, flux_err, target)
    out = pu.analyse(lc.time, lc.flux, teff=teff, fmin=fmin, fmax=fmax, max_frequencies=int(max_frequencies),
                     n_surrogates=int(n_surrogates), n_boot=30)
    out.pop("_time", None)
    out.pop("_residual", None)
    status = validation_status("pulsations")
    out["validation_status"] = status
    honesty = [COMPUTED, DETECTED, "S/N is the peak amplitude over the mean residual amplitude in a 2 d⁻¹ box; a "
               "white-noise false-alarm level is optimistic on red noise, so read the surrogate null when given.",
               f"Pulsation analysis is {status} (see {VALIDATION_FILE})."]
    return envelope("pulsation_spectrum", out, sources=sources, honesty=honesty)


def get_cheops_lightcurve(target: str, file_key: str | None = None, max_visits: int = 1, include_points: bool = False,
                          offline: bool = False) -> dict:
    """Public CHEOPS DRP light curves of a target from the CHEOPS archive through DACE (``cheops.get_cheops_lightcurve``;
    needs ``pip install 'setuhq[cheops]'`` and network unless cached): visits listed by position, proprietary ones
    skipped, each fetched once and cached, roll-angle/background/centroid systematics decorrelated (terms chosen
    by BIC). Returns each visit's provenance (programme, file key, obs id, credit), the detrend summary and,
    with include_points, the detrended points on BTJD. Carries ESA's acknowledgement and SetuHQ's disclaimer."""
    import numpy as np

    from setuhq import cheops as ch
    from setuhq.tools import COMPUTED, ToolError, envelope, root

    if not 1 <= int(max_visits) <= 5:
        raise ToolError("max_visits must be 1 to 5")
    try:
        out = ch.get_cheops_lightcurve(target, file_key=file_key, max_visits=int(max_visits),
                                       cache_dir=root() / ch.CACHE, offline=offline)
    except ch.CheopsUnavailable as exc:
        raise ToolError(str(exc)) from None
    visits = []
    for v in out["visits"]:
        row = {k: v[k] for k in ("provenance", "cadence_s", "detrend")}
        if include_points and v["_detrended"] is not None:
            d = v["_detrended"]
            ok = np.isfinite(d["flux"])
            row["points"] = {"time_btjd": d["time"][ok].tolist(), "flux": d["flux"][ok].tolist()}
        visits.append(row)
    status = validation_status("cheops")
    result = {"target": target, "n_public_visits": out["n_public_visits"], "visits": visits,
              "validation_status": status, **ch.credit([v["provenance"] for v in visits])}
    sources = [{"path": v["provenance"].get("file_key"), "sha256": v["provenance"].get("sha256")} for v in visits]
    honesty = [COMPUTED, ch.ACKNOWLEDGEMENT, ch.DISCLAIMER, ch.COMMERCIAL_NOTE,
               "Public CHEOPS data only; proprietary visits are skipped.", f"CHEOPS detrending is {status}."]
    return envelope("get_cheops_lightcurve", result, sources=sources, honesty=honesty)


def find_eclipsing_binary(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                          flux_err: list[float] | None = None, transit_period: float | None = None,
                          transit_epoch: float | None = None, transit_duration_days: float | None = None,
                          target: str = "custom") -> dict:
    """Eclipsing binaries and ellipsoidal or reflection variables in a light curve (``binaries.analyse``): the
    orbital period from a box search and a periodogram (doubled on an odd/even difference or for equal minima, and
    said to be ambiguous then), the primary and secondary eclipses (phase, depth, width, significance), the
    secondary's phase with its e·cosω hint, a heuristic morphology class and an eclipsing-binary candidate flag
    with its reasons. With a transit candidate's period, epoch and duration it also returns advisory vetting hints
    (odd/even depths, a secondary at any phase, ellipsoidal and reflection amplitudes) that SetuHQ's vetting does
    not use. Time in days (BTJD for TESS)."""
    from setuhq import binaries as eb
    from setuhq.tools import COMPUTED, ToolError, envelope

    lc, sources = _arrays(csv_path, time, flux, flux_err, target)
    out = eb.analyse(lc.time, lc.flux, lc.flux_err)
    out.pop("phase_curve", None)
    if transit_period is not None:
        if transit_epoch is None or not transit_duration_days:
            raise ToolError("vetting hints need transit_period, transit_epoch and transit_duration_days together")
        out["vetting_hints"] = eb.vetting_hints(lc.time, lc.flux, transit_period, transit_epoch, transit_duration_days,
                                                flux_err=lc.flux_err)
    status = validation_status("binaries")
    out["validation_status"] = status
    honesty = [COMPUTED, eb.LABEL, eb.VETTING_NOTE, f"Eclipsing-binary analysis is {status} (see {VALIDATION_FILE_V4})."]
    return envelope("find_eclipsing_binary", out, sources=sources, honesty=honesty)


def rotation_period(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                    flux_err: list[float] | None = None, target: str = "custom") -> dict:
    """A stellar rotation period from spot modulation (``rotation.measure``): a Lomb-Scargle periodogram and the
    autocorrelation function, with an uncertainty, half/double alias handling and a detected flag. One TESS sector
    cannot measure periods longer than about 13 days; those are reported as beyond the limit. Pass one sector (or
    a light curve you stitched yourself, with care for sector-to-sector offsets). Time in days."""
    from setuhq import rotation as ro
    from setuhq.tools import COMPUTED, envelope

    lc, sources = _arrays(csv_path, time, flux, flux_err, target)
    out = ro.measure(lc.time, lc.flux)
    out.pop("periodogram", None)
    status = validation_status("rotation")
    out["validation_status"] = status
    honesty = [COMPUTED, ro.LABEL, f"Rotation measurement is {status} (see {VALIDATION_FILE_V4})."]
    return envelope("rotation_period", out, sources=sources, honesty=honesty)


def find_transients(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                    flux_err: list[float] | None = None, difference_flux: bool = False,
                    momentum_dump_times: list[float] | None = None, scattered_light_times: list[float] | None = None,
                    target: str = "custom") -> dict:
    """Non-periodic brightenings in a light curve (``transients.find_transients``) on three time scales, each
    with its peak, amplitude, rise and decay times, FWHM and a class hint (flare-like, extragalactic-transient-like,
    asteroid-crossing-like, momentum-dump-like, scattered-light-like or periodic-variability-like) with its reasons;
    the last four are likely false alarms. difference_flux=True for a difference-imaging light curve in e-/s.
    Momentum-dump and scattered-light times (TESS quality bits 32, 2048, 4096) sharpen the screens. Every event is
    a transient candidate, never a new or confirmed object. Time in days (BTJD for TESS)."""
    from setuhq import transients as tr
    from setuhq.tools import COMPUTED, envelope

    lc, sources = _arrays(csv_path, time, flux, flux_err, target)
    quality = {"momentum_dump": list(momentum_dump_times or []), "scattered_light": list(scattered_light_times or [])}
    out = tr.find_transients(lc.time, lc.flux, lc.flux_err, mode="difference" if difference_flux else "relative",
                             quality=quality)
    status = validation_status("transients")
    out["validation_status"] = status
    honesty = [COMPUTED, tr.LABEL, f"Transient detection is {status} (see {VALIDATION_FILE_V4})."]
    return envelope("find_transients", out, sources=sources, honesty=honesty)


# (function, read_only): get_cheops_lightcurve reaches the network and writes the cache.
STELLAR_TOOLS = [(find_flares, True), (pulsation_spectrum, True), (get_cheops_lightcurve, False),
                 (find_eclipsing_binary, True), (rotation_period, True), (find_transients, True)]

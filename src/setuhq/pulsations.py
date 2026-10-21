# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Pulsations and asteroseismology: frequency extraction, a heuristic variability type, the granulation
background, numax and Δν for solar-like oscillators, and a red-noise null for false frequencies.

Methods reimplemented from their published descriptions:

* **Amplitude spectrum**: the Lomb-Scargle periodogram (astropy) scaled to semi-amplitude, A = √(4P/N), on a grid
  oversampled ten times the Rayleigh resolution 1/T.
* **Iterative pre-whitening** (Deeming 1975; as Period04 and FELIX do): take the residual spectrum's peak of
  highest S/N (amplitude over the local noise, so the red-noise rise at low frequency does not end the extraction
  while significant peaks remain elsewhere), fit it, refit every amplitude and phase, and every ten peaks and at
  the end refit every sinusoid together by non-linear least squares (frequency, amplitude, phase); subtract,
  repeat. Extraction stops when no peak has S/N ≥ 4 (Breger et al. 1993), the noise being the mean amplitude of
  the residual spectrum in a box around the peak (2 d⁻¹ wide by default, and at least 25/T). Every frequency's
  final S/N is measured on the final residual. Uncertainties follow Montgomery & O'Donoghue (1999). Peaks closer
  than 1.5/T to a stronger one are flagged unresolved (Loumos & Deeming 1978).
* **Combination frequencies**: a frequency within the Rayleigh resolution of n·f_i + m·f_j (|n|, |m| ≤ 2) or a
  harmonic (up to 4·f_i) of stronger ones is flagged as a likely combination.
* **Variability type** (heuristic, never certain): δ Scuti, γ Doradus, hybrid, solar-like or rotation, from where
  the significant amplitude lies (5 d⁻¹ as the p/g boundary; Grigahcène et al. 2010), harmonic structure, the
  detection of a solar-like power excess, and Teff when given. The result is ``likely`` or ``candidate`` with the
  reasons and the alternatives.
* **Granulation background**: Harvey-like profiles a/(1 + (ν/b)^c) plus white noise (Harvey 1985; as Salmon et al.
  2024 fit to HR 10), fitted by maximum likelihood to the periodogram, whose bins scatter as χ² with two degrees of
  freedom (Anderson et al. 1990), one or two components chosen by BIC.
* **numax and Δν** for solar-like oscillators: a Gaussian envelope on the background (numax), and the
  autocorrelation of the background-divided spectrum around numax near the Δν that the Stello et al. (2009)
  scaling predicts; uncertainties from a bootstrap of the spectrum (each bin redrawn as the smoothed spectrum
  times χ²₂/2).
* **Null**: the whole extraction on red-noise surrogates of the residual (an AR(1) process with its variance and
  lag-one correlation, as :func:`setuhq.variables.red_noise_copy` builds for the sweep, here at the native
  cadence; and Gaussian noise with the fitted background's spectrum): the number of 'frequencies' found per
  surrogate is the false-frequency rate.

Frequencies are *detected* at a stated S/N; a type is a heuristic label, never a classification by spectroscopy
or mode identification.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import optimize

DAY_TO_UHZ = 1e6 / 86400.0  # 1 d⁻¹ = 11.574 µHz
SNR_STOP = 4.0
NOISE_BOX = 2.0           # d⁻¹, width of the box for the local noise
OVERSAMPLE = 10
P_G_BOUNDARY = 5.0        # d⁻¹
DSCT_TEFF = (6300.0, 8800.0)
SOLAR_TEFF_MAX = 7000.0


def _prep(time, flux):
    t = np.asarray(time, float)
    y = np.asarray(flux, float)
    ok = np.isfinite(t) & np.isfinite(y)
    t, y = t[ok], y[ok]
    order = np.argsort(t)
    t, y = t[order], y[order]
    y = y / np.median(y) - 1.0 if abs(np.median(y)) > 0.1 else y - np.mean(y)
    return t, y


def nyquist(time) -> float:
    """Nyquist frequency (d⁻¹) of the median cadence."""
    d = np.diff(np.asarray(time, float))
    return 0.5 / float(np.median(d[d > 0]))


def frequency_grid(time, fmin: float | None = None, fmax: float | None = None, oversample: int = OVERSAMPLE) -> np.ndarray:
    t = np.asarray(time, float)
    T = float(t[-1] - t[0])
    fmax = fmax or nyquist(t)
    fmin = fmin if fmin is not None else 1.0 / T
    df = 1.0 / (T * oversample)
    return np.arange(max(fmin, df), fmax, df)


def amplitude_spectrum(time, flux, freq=None, *, fmin=None, fmax=None, oversample: int = OVERSAMPLE):
    """(frequency in d⁻¹, semi-amplitude in the flux unit) by Lomb-Scargle, A = √(4 P_psd / N)."""
    from astropy.timeseries import LombScargle

    t = np.asarray(time, float)
    y = np.asarray(flux, float)
    if freq is None:
        freq = frequency_grid(t, fmin, fmax, oversample)
    p = LombScargle(t, y, fit_mean=False, center_data=True, normalization="psd").power(freq, method="fast")
    return freq, np.sqrt(np.maximum(4.0 * p / t.size, 0.0))


def _sines(params, t, n):
    y = np.zeros_like(t)
    for k in range(n):
        f, a, ph = params[3 * k: 3 * k + 3]
        y += a * np.sin(2 * math.pi * (f * t + ph))
    return y


def _sines_jac(params, t, n):
    J = np.empty((t.size, 3 * n))
    for k in range(n):
        f, a, ph = params[3 * k: 3 * k + 3]
        arg = 2 * math.pi * (f * t + ph)
        c = np.cos(arg)
        J[:, 3 * k] = a * c * 2 * math.pi * t
        J[:, 3 * k + 1] = np.sin(arg)
        J[:, 3 * k + 2] = a * c * 2 * math.pi
    return J


def _noise_curve(freq, amp, box) -> np.ndarray:
    """The mean amplitude in a box of width ``box`` centred on every frequency of the grid (running mean)."""
    df = float(freq[1] - freq[0]) if freq.size > 1 else 1.0
    w = max(1, int(round(box / df)))
    c = np.concatenate([[0.0], np.cumsum(amp)])
    i = np.arange(amp.size)
    lo = np.clip(i - w // 2, 0, amp.size)
    hi = np.clip(i + w // 2 + 1, 0, amp.size)
    return (c[hi] - c[lo]) / (hi - lo)


def _local_noise(freq, amp, f0, box) -> float:
    m = np.abs(freq - f0) <= box / 2
    return float(np.mean(amp[m])) if m.any() else float("nan")


def _linear_refit(params, tt, y):
    """Amplitudes and phases of every sinusoid at fixed frequencies, by linear least squares."""
    n = len(params) // 3
    f = np.asarray(params[0::3], float)
    arg = 2 * math.pi * np.outer(tt, f)
    A = np.hstack([np.sin(arg), np.cos(arg)])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    bs, bc = coef[:n], coef[n:]
    out = []
    for k in range(n):
        out += [float(f[k]), float(math.hypot(bs[k], bc[k])), float(math.atan2(bc[k], bs[k]) / (2 * math.pi))]
    return out


def _nonlinear_refit(params, tt, y, T, max_nfev=30):
    n = len(params) // 3
    p0 = np.asarray(params, float)
    df = 1.0 / T
    lo = np.concatenate([[p0[3 * i] - df, 0.0, -np.inf] for i in range(n)])
    hi = np.concatenate([[p0[3 * i] + df, np.inf, np.inf] for i in range(n)])
    sol = optimize.least_squares(lambda p: _sines(p, tt, n) - y, np.clip(p0, lo + 1e-12, hi - 1e-12), bounds=(lo, hi),
                                 jac=lambda p: _sines_jac(p, tt, n), x_scale="jac", max_nfev=max_nfev,
                                 tr_solver="lsmr" if n > 3 else "exact")
    return list(sol.x)


def prewhiten(time, flux, *, fmin: float | None = None, fmax: float | None = None, snr_stop: float = SNR_STOP,
              noise_box: float = NOISE_BOX, max_frequencies: int = 80, oversample: int = OVERSAMPLE,
              refit_every: int = 10) -> dict:
    """Iterative pre-whitening with non-linear multi-sine refits (see the module docstring).

    Each new peak is first fitted alone (frequency, amplitude, phase) on the residual, then every amplitude and phase
    is refitted linearly at fixed frequencies; every ``refit_every`` extractions, and at the end, all frequencies,
    amplitudes and phases are refitted together by non-linear least squares (a full refit at every step, as FELIX
    and Period04 allow, gives the same list and is many times slower on long light curves).

    Frequencies in d⁻¹ (×11.574 for µHz), amplitudes in the flux unit (relative flux: ×1e6 for ppm), phases in
    cycles at the first time stamp. Returns the frequency list (in extraction order) with S/N, uncertainties,
    combination and resolution flags, the residual, and the stopping reason."""
    t, y = _prep(time, flux)
    t0 = float(t[0])
    tt = t - t0
    T = float(tt[-1])
    freq = frequency_grid(tt, fmin, fmax, oversample)
    # The noise box spans at least 25 resolution elements, so a short light curve's own window function (a peak's
    # sidelobes and aliases) does not pass for noise around that peak.
    noise_box = max(noise_box, 25.0 / T)
    resid = y.copy()
    params: list[float] = []
    reason = f"reached {max_frequencies} frequencies"
    for n in range(1, max_frequencies + 1):
        fr, amp = amplitude_spectrum(tt, resid, freq)
        snr = amp / _noise_curve(fr, amp, noise_box)
        k = int(np.nanargmax(snr))
        if not np.isfinite(snr[k]) or snr[k] < snr_stop:
            reason = f"highest S/N left is {snr[k]:.2f} < {snr_stop:g} (at {fr[k]:.5f} d⁻¹)"
            break
        new = _linear_refit([fr[k], 0.0, 0.0], tt, resid)
        new = _nonlinear_refit(new, tt, resid, T, max_nfev=20)
        params = _linear_refit(params + new, tt, y)
        if n % refit_every == 0:
            params = _nonlinear_refit(params, tt, y, T)
        resid = y - _sines(np.asarray(params), tt, n)
    if params:
        params = _nonlinear_refit(params, tt, y, T, max_nfev=50)
        resid = y - _sines(np.asarray(params), tt, len(params) // 3)
    nf = len(params) // 3
    fr, amp = amplitude_spectrum(tt, resid, freq)
    sig_res = float(np.std(resid))
    N = tt.size
    out = []
    for i in range(nf):
        f, a, ph = params[3 * i: 3 * i + 3]
        noise = _local_noise(fr, amp, f, noise_box)
        out.append({"id": f"f{i + 1}", "frequency": f, "frequency_uhz": f * DAY_TO_UHZ, "amplitude": a,
                    "phase": ph % 1.0, "snr": a / noise if noise else None, "noise": noise,
                    "sigma_frequency": math.sqrt(6.0 / N) * sig_res / (math.pi * T * a) if a > 0 else None,
                    "sigma_amplitude": math.sqrt(2.0 / N) * sig_res,
                    "sigma_phase": sig_res / (a * math.sqrt(2.0 * N)) / (2 * math.pi) if a > 0 else None})
    flag_combinations(out, resolution=1.0 / T)
    for x in out:
        x["significant"] = bool(x["snr"] is not None and x["snr"] >= snr_stop)
    return {"frequencies": out, "n": nf, "n_significant": sum(x["significant"] for x in out), "stop": reason,
            "baseline_days": T, "rayleigh": 1.0 / T, "n_points": int(N), "nyquist": nyquist(t), "t0": t0,
            "residual": resid, "time": t, "residual_rms": sig_res, "snr_stop": snr_stop, "noise_box": noise_box,
            "range": [float(freq[0]), float(freq[-1])]}


def flag_combinations(freqs: list[dict], resolution: float, max_order: int = 2, max_harmonic: int = 4) -> None:
    """Mark each frequency that sits within ``resolution`` of a harmonic or a two-term combination of stronger
    ones (in place: ``combination`` names the match, ``unresolved`` marks a peak within 1.5/T of a stronger one)."""
    for k, x in enumerate(freqs):
        x["combination"] = None
        x["unresolved"] = False
        stronger = [y for y in freqs[:k] if y["amplitude"] >= x["amplitude"]] or freqs[:k]
        for y in stronger:
            if abs(x["frequency"] - y["frequency"]) < 1.5 * resolution:
                x["unresolved"] = True
        best = None
        for i, a in enumerate(stronger):
            for h in range(2, max_harmonic + 1):
                d = abs(x["frequency"] - h * a["frequency"])
                if d < resolution and (best is None or d < best[0]):
                    best = (d, f"{h}{a['id']}")
            for b in stronger[i + 1:]:
                for n in range(-max_order, max_order + 1):
                    for m in range(-max_order, max_order + 1):
                        if n == 0 or m == 0:
                            continue
                        v = n * a["frequency"] + m * b["frequency"]
                        if v <= 0:
                            continue
                        d = abs(x["frequency"] - v)
                        if d < resolution and (best is None or d < best[0]):
                            sign = "+" if m > 0 else "-"
                            best = (d, f"{'' if n == 1 else n}{a['id']}{sign}{'' if abs(m) == 1 else abs(m)}{b['id']}")
        if best:
            x["combination"] = best[1]
            x["combination_offset_rayleigh"] = best[0] / resolution


# ---------------------------------------------------------------- power density and the background


def power_density(time, flux, *, fmax: float | None = None, oversample: int = 1):
    """One-sided power density in (flux unit)² per µHz, normalised so its integral is the variance (Parseval), on
    the natural grid (``oversample`` = 1). Frequencies in µHz."""
    from astropy.timeseries import LombScargle

    t = np.asarray(time, float)
    y = np.asarray(flux, float) - np.mean(flux)
    T = float(t[-1] - t[0])
    fmax = fmax or nyquist(t)
    f = np.arange(1.0 / T, fmax, 1.0 / (T * oversample))
    p = LombScargle(t, y, fit_mean=False, center_data=True, normalization="psd").power(f, method="fast")
    df_uhz = (f[1] - f[0]) * DAY_TO_UHZ
    scale = np.var(y) / (np.sum(p) * df_uhz * oversample) if np.sum(p) > 0 else 1.0
    return f * DAY_TO_UHZ, p * scale


def harvey(nu, a, b, c):
    return a / (1.0 + (nu / b) ** c)


def _ex(x: float) -> float:
    return math.exp(min(max(float(x), -700.0), 700.0))


def _bg_model(theta, nu, ncomp, envelope):
    w = _ex(theta[0])
    m = np.full_like(nu, w)
    for k in range(ncomp):
        la, lb, c = theta[1 + 3 * k: 4 + 3 * k]
        c = min(max(float(c), 0.1), 20.0)  # the profile's exponent, kept in a physical range
        with np.errstate(over="ignore"):
            m = m + harvey(nu, _ex(la), _ex(lb), c)
    if envelope:
        lh, numax, lsig = theta[1 + 3 * ncomp: 4 + 3 * ncomp]
        m = m + _ex(lh) * np.exp(-0.5 * ((nu - numax) / _ex(lsig)) ** 2)
    return m


def _nll(theta, nu, p, ncomp, envelope):
    m = _bg_model(theta, nu, ncomp, envelope)
    if not np.all(np.isfinite(m)) or np.any(m <= 0):
        return 1e300
    return float(np.sum(np.log(m) + p / m))


def fit_background(nu, p, *, ncomp: int | None = None, envelope: bool = False, numax_guess: float | None = None,
                   fmin_uhz: float | None = None) -> dict:
    """Harvey profiles plus white noise (and optionally a Gaussian envelope) by maximum likelihood on a χ²₂
    periodogram. ``ncomp`` None tries one and two components and keeps the lower BIC."""
    nu = np.asarray(nu, float)
    p = np.asarray(p, float)
    keep = nu >= (fmin_uhz or nu[0])
    nu, p = nu[keep], p[keep]
    hi = nu > 0.8 * nu[-1]
    white = float(np.median(p[hi])) / math.log(2) if hi.any() else float(np.median(p))
    choices = [ncomp] if ncomp else [1, 2]
    fits = []
    for nc in choices:
        # starting points: characteristic frequencies spread over decades of the range
        bs = np.geomspace(max(nu[0] * 3, 1.0), nu[-1] / 5, nc + 2)[1:-1] if nc > 1 else [math.sqrt(nu[0] * nu[-1]) / 3]
        theta0 = [math.log(max(white, 1e-30))]
        for b in bs:
            lowp = float(np.median(p[nu < b])) if np.any(nu < b) else float(np.median(p))
            theta0 += [math.log(max(lowp, white * 2, 1e-30)), math.log(b), 2.0]
        if envelope:
            nm = numax_guess or math.sqrt(nu[0] * nu[-1])
            theta0 += [math.log(max(white, 1e-30)), nm, math.log(max(0.1 * nm, 2 * (nu[1] - nu[0])))]
        best = None
        for start_c in (2.0, 4.0):
            th = np.array(theta0, float)
            for k in range(nc):
                th[3 + 3 * k] = start_c
            r = optimize.minimize(_nll, th, args=(nu, p, nc, envelope), method="Nelder-Mead",
                                  options={"maxiter": 20000, "maxfev": 20000, "xatol": 1e-5, "fatol": 1e-4})
            if best is None or r.fun < best.fun:
                best = r
        k = len(theta0)
        fits.append({"ncomp": nc, "theta": best.x, "nll": float(best.fun), "bic": 2 * best.fun + k * math.log(nu.size),
                     "converged": bool(best.success)})
    best = min(fits, key=lambda f: f["bic"])
    th = best["theta"]
    comps = [{"a": _ex(th[1 + 3 * k]), "b_uhz": _ex(th[2 + 3 * k]), "c": min(max(float(th[3 + 3 * k]), 0.1), 20.0)}
             for k in range(best["ncomp"])]
    comps.sort(key=lambda c: c["b_uhz"])
    out = {"white": _ex(th[0]), "components": comps, "ncomp": best["ncomp"], "bic": best["bic"],
           "nll": best["nll"], "converged": best["converged"], "tried": [{k: v for k, v in f.items() if k != "theta"} for f in fits],
           "theta": th.tolist(), "envelope": None, "fmin_uhz": float(nu[0]), "fmax_uhz": float(nu[-1])}
    if envelope:
        nc = best["ncomp"]
        out["envelope"] = {"height": _ex(th[1 + 3 * nc]), "numax_uhz": float(th[2 + 3 * nc]),
                           "sigma_uhz": _ex(th[3 + 3 * nc])}
    return out


def background_model(fit: dict, nu) -> np.ndarray:
    return _bg_model(np.asarray(fit["theta"]), np.asarray(nu, float), fit["ncomp"], fit["envelope"] is not None)


def dnu_scaling(numax_uhz: float) -> float:
    """Δν ≈ 0.263 numax^0.772 µHz (Stello et al. 2009)."""
    return 0.263 * numax_uhz ** 0.772


def _boxcar(x, n):
    n = max(1, int(n))
    if n == 1:
        return np.asarray(x, float)
    k = np.ones(n) / n
    return np.convolve(x, k, mode="same")


def measure_dnu(nu, snr_spec, numax: float, *, width: float | None = None) -> dict | None:
    """Δν from the autocorrelation of the background-divided spectrum within numax ± ``width`` (default 3 × the
    scaling Δν), its highest peak between 0.7 and 1.4 × the scaling value."""
    nu = np.asarray(nu, float)
    exp = dnu_scaling(numax)
    width = width or 3.0 * exp
    m = np.abs(nu - numax) <= width
    if m.sum() < 20:
        return None
    x = snr_spec[m] - np.mean(snr_spec[m])
    d = nu[1] - nu[0]
    ac = np.correlate(x, x, mode="full")[x.size - 1:]
    ac = ac / ac[0]
    lags = np.arange(ac.size) * d
    w = (lags >= 0.7 * exp) & (lags <= 1.4 * exp)
    if not w.any():
        return None
    k = int(np.flatnonzero(w)[np.argmax(ac[w])])
    # parabolic refinement
    if 0 < k < ac.size - 1:
        y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
        den = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
    else:
        off = 0.0
    return {"dnu_uhz": float((k + off) * d), "acf_peak": float(ac[k]), "expected_uhz": exp}


def solar_like(time, flux, *, numax_range=(5.0, None), n_boot: int = 100, seed: int = 0, fmin_uhz: float = 3.0) -> dict:
    """numax and Δν of a solar-like oscillator, with bootstrap uncertainties, or a statement that no power
    excess is detected (the envelope must lower the BIC by 10 or more)."""
    t, y = _prep(time, flux)
    nu, p = power_density(t, y)
    nyq = nu[-1]
    lo, hi = numax_range[0], numax_range[1] or 0.9 * nyq
    # coarse numax guess: where the smoothed background-normalised power peaks
    bg0 = fit_background(nu, p, fmin_uhz=fmin_uhz)
    ratio = p / background_model(bg0, nu)
    smooth = _boxcar(ratio, max(3, int(len(nu) / 200)))
    band = (nu >= lo) & (nu <= hi)
    if not band.any():
        return {"detected": False, "why": "the numax range lies above the Nyquist frequency"}
    guess = float(nu[band][np.argmax(smooth[band])])
    env = fit_background(nu, p, ncomp=bg0["ncomp"], envelope=True, numax_guess=guess, fmin_uhz=fmin_uhz)
    dbic = bg0["bic"] - env["bic"]
    out = {"nyquist_uhz": float(nyq), "background": {k: v for k, v in bg0.items() if k != "theta"},
           "envelope_fit": env["envelope"], "delta_bic_envelope": float(dbic), "numax_guess_uhz": guess}
    if dbic < 10 or not (lo <= env["envelope"]["numax_uhz"] <= hi):
        return {**out, "detected": False, "why": f"no power excess: the envelope lowers the BIC by {dbic:.1f} (< 10) "
                                                 "or falls outside the searched range"}
    numax = env["envelope"]["numax_uhz"]
    snr_spec = p / background_model({**env, "envelope": None, "theta": env["theta"][: 1 + 3 * env["ncomp"]]}, nu)
    dnu = measure_dnu(nu, snr_spec, numax)
    # bootstrap: the spectrum smoothed over Δν/10 times χ²₂/2, refit (envelope only, background fixed), Δν again
    rng = np.random.default_rng(seed)
    dres = nu[1] - nu[0]
    sm = _boxcar(p, max(1, int((dnu["dnu_uhz"] if dnu else dnu_scaling(numax)) / 10 / dres)))
    nm_b, dn_b = [], []
    bg_only = background_model({**env, "envelope": None, "theta": env["theta"][: 1 + 3 * env["ncomp"]]}, nu)
    win = np.abs(nu - numax) <= 4 * max(env["envelope"]["sigma_uhz"], dnu_scaling(numax))
    for _ in range(n_boot):
        pb = sm * rng.chisquare(2, nu.size) / 2.0
        ex = pb / bg_only
        try:
            def nll(th):
                h, c, s = _ex(th[0]), th[1], _ex(th[2])
                m = bg_only[win] + h * np.exp(-0.5 * ((nu[win] - c) / s) ** 2)
                return float(np.sum(np.log(m) + pb[win] / m))
            r = optimize.minimize(nll, [math.log(env["envelope"]["height"]), numax, math.log(env["envelope"]["sigma_uhz"])],
                                  method="Nelder-Mead", options={"maxiter": 2000})
            nm_b.append(float(r.x[1]))
        except (ValueError, FloatingPointError):
            pass
        d = measure_dnu(nu, ex, numax)
        if d:
            dn_b.append(d["dnu_uhz"])
    return {**out, "detected": True, "numax_uhz": numax,
            "numax_err_uhz": float(np.std(nm_b)) if len(nm_b) > 2 else None,
            "dnu_uhz": dnu["dnu_uhz"] if dnu else None,
            "dnu_err_uhz": float(np.std(dn_b)) if len(dn_b) > 2 else None,
            "dnu_expected_uhz": dnu_scaling(numax), "n_boot": n_boot, "seed": seed,
            "method": "Gaussian envelope on a Harvey background (MLE); Δν from the autocorrelation of the "
                      "background-divided spectrum; bootstrap over χ²₂ redraws of the smoothed spectrum"}


# ---------------------------------------------------------------- classification


def classify(freqs: list[dict], *, teff: float | None = None, solar: dict | None = None) -> dict:
    """A heuristic variability type with its uncertainty: ``label`` (likely δ Scuti, γ Doradus, hybrid
    δ Scuti/γ Doradus, solar-like, rotation, or unclear), ``confidence`` (medium or low, never high: a light curve
    alone cannot settle a type), the reasons and the alternatives."""
    sig = [f for f in freqs if f.get("significant") and not f.get("combination")]
    reasons, alternatives = [], []
    if solar and solar.get("detected"):
        reasons.append(f"a solar-like power excess at numax {solar['numax_uhz']:.0f} µHz (envelope ΔBIC "
                       f"{solar['delta_bic_envelope']:.0f})")
        conf = "medium" if (teff is None or teff < SOLAR_TEFF_MAX) and len(sig) < 5 else "low"
        if teff and teff >= SOLAR_TEFF_MAX:
            reasons.append(f"but Teff {teff:.0f} K is hot for solar-like oscillations")
        return {"label": "solar-like", "confidence": conf, "reasons": reasons,
                "alternatives": ["granulation or activity without oscillations"] if conf == "low" else []}
    if not sig:
        return {"label": "unclear", "confidence": "low", "reasons": ["no independent frequency with S/N ≥ 4"],
                "alternatives": ["constant at this precision", "stochastic variability (granulation, red noise)"]}
    amp_p = sum(f["amplitude"] for f in sig if f["frequency"] >= P_G_BOUNDARY)
    amp_g = sum(f["amplitude"] for f in sig if f["frequency"] < P_G_BOUNDARY)
    n_p = sum(1 for f in sig if f["frequency"] >= P_G_BOUNDARY)
    n_g = len(sig) - n_p
    tot = amp_p + amp_g
    harm = sum(1 for f in freqs if f.get("significant") and (f.get("combination") or "")[:1].isdigit()
               and not any(s in (f.get("combination") or "") for s in "+-"))
    reasons.append(f"{n_p} independent frequencies at ≥ {P_G_BOUNDARY:g} d⁻¹ ({amp_p / tot:.0%} of the amplitude), "
                   f"{n_g} below")
    in_strip = teff is not None and DSCT_TEFF[0] <= teff <= DSCT_TEFF[1]
    if teff is not None:
        reasons.append(f"Teff {teff:.0f} K is {'inside' if in_strip else 'outside'} the δ Scuti/γ Doradus range "
                       f"({DSCT_TEFF[0]:.0f}-{DSCT_TEFF[1]:.0f} K)")
    if n_p >= 3 and amp_p / tot >= 0.7:
        label = "δ Scuti"
        if n_g >= 3 and amp_g / tot >= 0.1:
            label = "hybrid δ Scuti/γ Doradus"
            alternatives.append("δ Scuti with rotational modulation or combination frequencies at low frequency")
        alternatives.append("a contaminating pulsator in the aperture")
    elif n_g >= 3 and amp_g / tot >= 0.7 and harm < max(1, n_g // 2):
        label = "γ Doradus"
        alternatives += ["rotational modulation of an evolving spotted star", "SPB star (if hotter)"]
    elif n_g >= 1 and amp_g / tot >= 0.7:
        label = "rotation"
        if harm:
            reasons.append(f"{harm} harmonics of the main low frequency")
        alternatives += ["γ Doradus pulsation", "ellipsoidal or reflection variation of a binary"]
    elif n_p and n_g:
        label = "hybrid δ Scuti/γ Doradus"
        alternatives += ["δ Scuti with rotational modulation", "two stars in the aperture"]
    else:
        label = "unclear"
    conf = "medium" if (label != "unclear" and len(sig) >= 5 and (teff is None or in_strip or label == "rotation")) else "low"
    return {"label": label, "confidence": conf, "reasons": reasons, "alternatives": alternatives}


# ---------------------------------------------------------------- the null


def ar1_surrogate(time, resid, *, seed: int = 0) -> np.ndarray:
    """An AR(1) copy of a residual at its native cadence: its variance and lag-one correlation, with a gap of n
    cadences correlating as ρⁿ (the same process as variables.red_noise_copy, which works on 10-minute bins)."""
    t = np.asarray(time, float)
    x = np.asarray(resid, float) - float(np.mean(resid))
    s = float(np.std(x))
    rho = float(np.clip(np.corrcoef(x[:-1], x[1:])[0, 1], 0.0, 0.9999)) if x.size > 2 and s > 0 else 0.0
    cad = float(np.median(np.diff(t)))
    steps = np.maximum(1.0, np.round(np.diff(t) / cad))
    rng = np.random.default_rng(seed)
    e = rng.normal(0.0, 1.0, x.size)
    y = np.empty(x.size)
    y[0] = s * e[0]
    a = rho ** steps
    sc = np.sqrt(np.maximum(0.0, 1.0 - a * a)) * s
    for i in range(1, x.size):
        y[i] = a[i - 1] * y[i - 1] + sc[i - 1] * e[i]
    return y


def background_surrogate(time, bg_fit: dict, *, seed: int = 0) -> np.ndarray:
    """Gaussian noise with the fitted background's power density (random phases, χ²₂ powers), sampled at the
    light curve's times by summing sinusoids on the natural grid (exact for any sampling, slower)."""
    t = np.asarray(time, float)
    T = float(t[-1] - t[0])
    nyq = nyquist(t)
    f = np.arange(1.0 / T, nyq, 1.0 / T)
    nu = f * DAY_TO_UHZ
    psd = background_model({**bg_fit, "envelope": None, "theta": bg_fit["theta"][: 1 + 3 * bg_fit["ncomp"]]}, nu)
    rng = np.random.default_rng(seed)
    var_k = psd * (1.0 / T) * DAY_TO_UHZ  # power in each bin
    a = np.sqrt(var_k) * np.sqrt(rng.chisquare(2, f.size) / 2.0) * math.sqrt(2.0)
    ph = rng.uniform(0, 2 * math.pi, f.size)
    y = np.zeros_like(t)
    tt = t - t[0]
    for k0 in range(0, f.size, 2000):
        sl = slice(k0, k0 + 2000)
        y += np.sum(a[sl, None] * np.sin(2 * math.pi * f[sl, None] * tt[None, :] + ph[sl, None]), axis=0)
    return y


def false_frequency_rate(time, resid, *, n_surrogates: int = 10, seed: int = 0, kind: str = "ar1",
                         bg_fit: dict | None = None, **prewhiten_kw) -> dict:
    """The pre-whitening on ``n_surrogates`` noise copies of the residual: mean frequencies extracted per copy
    (each one is false by construction) and the fraction of copies with at least one."""
    counts = []
    for k in range(n_surrogates):
        if kind == "background" and bg_fit is not None:
            y = background_surrogate(time, bg_fit, seed=seed + k)
        else:
            y = ar1_surrogate(time, resid, seed=seed + k)
        r = prewhiten(time, 1.0 + y, **prewhiten_kw)
        counts.append(r["n_significant"])
    n = len(counts)
    return {"kind": kind, "n_surrogates": n, "seed": seed, "counts": counts,
            "mean_false_per_lightcurve": float(np.mean(counts)) if n else None,
            "fraction_with_any": float(np.mean([c > 0 for c in counts])) if n else None}


# ---------------------------------------------------------------- comparison with a published list


def match_frequencies(ours: list[float], published: list[float], tolerance) -> dict:
    """Greedy one-to-one matching of frequency lists (same unit): each published frequency to the nearest unused
    one of ours within its tolerance (a number, or a list per published frequency)."""
    tol = list(tolerance) if np.ndim(tolerance) else [float(tolerance)] * len(published)
    used: set[int] = set()
    pairs = []
    for j, (pf, tl) in enumerate(sorted(zip(published, tol), key=lambda x: x[0])):
        best = None
        for i, of in enumerate(ours):
            if i in used:
                continue
            d = abs(of - pf)
            if d <= tl and (best is None or d < best[1]):
                best = (i, d)
        if best:
            used.add(best[0])
            pairs.append({"published": pf, "ours": ours[best[0]], "difference": ours[best[0]] - pf, "tolerance": tl})
        else:
            pairs.append({"published": pf, "ours": None, "difference": None, "tolerance": tl})
    matched = sum(1 for p in pairs if p["ours"] is not None)
    return {"matched": matched, "published": len(published), "ours": len(ours),
            "recall": matched / len(published) if published else None,
            "ours_matched_fraction": matched / len(ours) if ours else None, "pairs": pairs}


def analyse(time, flux, *, teff: float | None = None, fmin: float | None = None, fmax: float | None = None,
            snr_stop: float = SNR_STOP, noise_box: float = NOISE_BOX, max_frequencies: int = 80,
            solar: bool | None = None, n_surrogates: int = 0, seed: int = 0, n_boot: int = 50) -> dict:
    """Everything for one light curve: pre-whitening, the background of the residual, numax/Δν when asked (or when
    Teff < 7000 K and no coherent frequencies dominate), the type, and optionally the surrogate null."""
    pw = prewhiten(time, flux, fmin=fmin, fmax=fmax, snr_stop=snr_stop, noise_box=noise_box, max_frequencies=max_frequencies)
    nu, p = power_density(pw["time"], pw["residual"])
    bg = fit_background(nu, p, fmin_uhz=max(nu[0], 3.0 * (nu[1] - nu[0])))
    want_solar = solar if solar is not None else (pw["n_significant"] < 5 and (teff is None or teff < SOLAR_TEFF_MAX))
    sol = solar_like(time, flux, n_boot=n_boot, seed=seed) if want_solar else None
    out = {"prewhitening": {k: v for k, v in pw.items() if k not in ("residual", "time")},
           "background": {k: v for k, v in bg.items()}, "solar_like": sol,
           "type": classify(pw["frequencies"], teff=teff, solar=sol)}
    if n_surrogates:
        kw = {"fmin": fmin, "fmax": fmax, "snr_stop": snr_stop, "noise_box": noise_box, "max_frequencies": max_frequencies}
        out["null"] = [false_frequency_rate(pw["time"], pw["residual"], n_surrogates=n_surrogates, seed=seed, kind="ar1", **kw),
                       false_frequency_rate(pw["time"], pw["residual"], n_surrogates=n_surrogates, seed=seed + 1000,
                                            kind="background", bg_fit=bg, **kw)]
    return out

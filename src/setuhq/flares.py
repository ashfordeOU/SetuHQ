# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Stellar flares: detection, morphology, energies, the flare frequency distribution, completeness and nulls.

Methods reimplemented from their published descriptions (no code or text copied):

* **Detrending** that keeps flares: an iterated running median (or, for CHEOPS-like visits, a Savitzky-Golay
  filter whose polynomial degree is chosen by AIC, as Poyatos et al. 2025 describe) with upward excursions masked
  and their tails protected before the trend is recomputed. Each stretch of data between gaps is detrended on
  its own, and a flare never spans a gap.
* **Candidates** by the three criteria of Chang et al. (2015), as AltaiPony applies them (Davenport 2016;
  Ilin et al. 2022): ``N1`` (residual over local scatter), ``N2`` (residual less its photometric error, over
  local scatter) and ``N3`` (consecutive points). TESS 2-min defaults 3, 2, 3; CHEOPS (Poyatos et al. 2025) 3, 2, 5.
* **Wavelet denoising** (optional, needs PyWavelets): a stationary wavelet transform per stretch, Donoho &
  Johnstone's universal threshold with the median absolute deviation in place of the standard deviation, hard
  thresholding, Daubechies-18 by default (Poyatos et al. 2025). Candidates are found on the denoised flux;
  amplitudes, equivalent durations and energies are always measured on the original detrended flux.
* **Morphology**: each candidate is fitted with the empirical flare template of Mendoza et al. (2022) (a Gaussian
  convolved with a double exponential, fixed shape constants fitted on GJ 1243; Davenport et al. 2014 is available
  too), integrated over the exposure, plus a linear baseline. A candidate is kept only when one flare beats a
  quadratic by ΔBIC ≥ 6, and the chosen templates beat as many symmetric Gaussian bumps by ΔBIC ≥ 10 (a flare
  rises faster than it decays; noise, residual spots and inverted transits do not: this test was set on AU Mic
  sector 1 and its flux-inverted null, then frozen); further components are added one at a time while each lowers the BIC by 6 or more, up to
  five (Davenport et al. 2014; Bruno et al. 2024 and Poyatos et al. 2025 use the same scheme with the AIC). The BIC
  uses an effective number of points for the noise's lag-one correlation, and an extra component must also be a
  visible peak (3σ and a tenth of the strongest component); the false-split rate on injected single flares is
  measured and reported.
  Rise and decay times, amplitude, FWHM and the equivalent duration (ED) are recorded for the flare and for
  each component.
* **Energies**: E_band = ED × L★,band, the star's quiescent luminosity in the band from the TESS magnitude and
  distance with Sullivan et al. (2015)'s zero point (as Medina et al. 2020 do) when both are known, else from Teff
  and radius (Planck spectrum through the instrument response, :mod:`setuhq.passbands`); both routes are reported
  side by side. E_bol assumes the flare is a 9000 K blackbody (Shibayama et al. 2013; Günther et al. 2020). Without
  either route the energies are ``None`` and labelled unavailable; nothing is guessed.
* **Flare frequency distribution**: the maximum-likelihood power-law index above a completeness limit, with its
  uncertainty (Clauset, Shalizi & Newman 2009), and the Vuong likelihood-ratio comparison with a truncated
  log-normal (as Bruno et al. 2024 and Poyatos et al. 2025 do after Verbeeck et al. 2019).
* **Completeness** from injecting synthetic Mendoza flares into the star's own light curve and running the whole
  detection again; **nulls** on the flux-inverted light curve (no star makes a downward flare) and on quiet stars.

Nothing here is a disposition: a flare is *detected* with its stated significance, and a morphology is a
fitted model, not a physical claim.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

import numpy as np
from scipy import optimize, special
from scipy.ndimage import median_filter

from setuhq.passbands import PC_CM, R_SUN_CM, SIGMA_SB, band_integral

# ---------------------------------------------------------------- templates

# Mendoza et al. (2022, AJ 164, 17), Table 2: the shape constants of the continuous flare template, fitted on
# single-peak GJ 1243 flares (Kepler short cadence). Time is in units of the FWHM about the peak.
MENDOZA_2022 = (0.9687734504375167, -0.251299705922117, 0.22675974948468916, 0.15551880775110513,
                1.2150539528490194, 0.12695865022878844)  # A, B, C, D1, D2, f1
# Davenport et al. (2014, ApJ 797, 122), eqs. 1 and 4: rise polynomial and double-exponential decay.
DAVENPORT_2014_RISE = (1.0, 1.941, -0.175, -2.246, -1.125)
DAVENPORT_2014_DECAY = (0.6890, -1.600, 0.3030, -0.2783)
FLARE_TEMPERATURE_K = 9000.0
TEMPLATE_REF = {"mendoza2022": "Mendoza et al. 2022, AJ 164, 17 (continuous flare template, GJ 1243)",
                "davenport2014": "Davenport et al. 2014, ApJ 797, 122 (empirical flare template, GJ 1243)"}


def _mendoza_term(x, d, a, b, c, f):
    """One cooling phase of the Mendoza template, evaluated without overflow (erfcx on the rise side)."""
    z = (b - x) / c + c * d / 2.0
    out = np.empty_like(x)
    pos = z >= 0
    # exp(-d x + (b/c + c d/2)^2) erfc(z) = erfcx(z) exp(z^2 - d x + (b/c + c d/2)^2 - z^2) ... rewritten stably:
    out[pos] = special.erfcx(z[pos]) * np.exp((b * b - (x[pos] - b) ** 2) / (c * c))
    k = (b / c + c * d / 2.0) ** 2
    out[~pos] = np.exp(-d * x[~pos] + k) * special.erfc(z[~pos])
    return 0.5 * math.sqrt(math.pi) * a * c * f * out


def mendoza_template(t, tpeak: float, fwhm: float, ampl: float) -> np.ndarray:
    """The Mendoza et al. (2022) flare profile at times ``t`` (same units as ``tpeak`` and ``fwhm``)."""
    a, b, c, d1, d2, f1 = MENDOZA_2022
    x = (np.asarray(t, float) - tpeak) / fwhm
    return ampl * (_mendoza_term(x, d1, a, b, c, f1) + _mendoza_term(x, d2, a, b, c, 1.0 - f1))


def davenport_template(t, tpeak: float, fwhm: float, ampl: float) -> np.ndarray:
    """The Davenport et al. (2014) flare profile: a quartic rise over one FWHM and a double-exponential decay."""
    x = (np.asarray(t, float) - tpeak) / fwhm
    out = np.zeros_like(x)
    r = (x > -1) & (x <= 0)
    c0, c1, c2, c3, c4 = DAVENPORT_2014_RISE
    out[r] = c0 + c1 * x[r] + c2 * x[r] ** 2 + c3 * x[r] ** 3 + c4 * x[r] ** 4
    dcy = x > 0
    a1, k1, a2, k2 = DAVENPORT_2014_DECAY
    out[dcy] = a1 * np.exp(k1 * x[dcy]) + a2 * np.exp(k2 * x[dcy])
    return ampl * out


TEMPLATES = {"mendoza2022": mendoza_template, "davenport2014": davenport_template}


def integrated_template(t, tpeak, fwhm, ampl, *, exposure: float, template: str = "mendoza2022", supersample: int = 7):
    """The template averaged over each exposure (``exposure`` in the time unit), so a flare shorter than a cadence
    keeps its equivalent duration."""
    fn = TEMPLATES[template]
    t = np.asarray(t, float)
    if supersample <= 1 or exposure <= 0:
        return fn(t, tpeak, fwhm, ampl)
    off = (np.arange(supersample) + 0.5) / supersample - 0.5
    tt = t[:, None] + off[None, :] * exposure
    return fn(tt.ravel(), tpeak, fwhm, ampl).reshape(tt.shape).mean(axis=1)


_TEMPLATE_AREA: dict[str, float] = {}


def template_area(template: str = "mendoza2022") -> float:
    """∫ profile dt for unit amplitude and unit FWHM (the ED of a flare is this × amplitude × FWHM)."""
    if template not in _TEMPLATE_AREA:
        x = np.linspace(-5.0, 400.0, 400_001)
        y = TEMPLATES[template](x, 0.0, 1.0, 1.0)
        _TEMPLATE_AREA[template] = float(np.trapezoid(y, x))
    return _TEMPLATE_AREA[template]


# ---------------------------------------------------------------- configuration


@dataclass(frozen=True)
class FlareConfig:
    """Every knob of the detection, stored with each result so it can be reproduced."""

    detrend: str = "median"            # "median" (iterated running median) or "savgol" (degree by AIC)
    window_days: float = 0.25          # trend window: long against a flare, short against rotation
    adaptive_window: bool = True       # a fast rotator (P < 2 d) gets a window of P/8 (at least 20 min) instead
    mask_sigma: float = 2.5            # upward points this far above the trend are masked before refitting it
    n1: float = 3.0                    # Chang et al. 2015 criteria (AltaiPony): residual / local scatter
    n2: float = 2.0                    # (residual - error) / local scatter
    n3: int = 3                        # consecutive points
    tail_sigma: float = 0.5            # a candidate is extended while the residual stays above this × scatter
    gap_cadences: float = 5.0          # a stretch ends at a gap longer than this many cadences
    denoise: bool = False              # stationary-wavelet denoising before the candidate search
    wavelet: str = "db18"
    level: int = 2                     # SWT decomposition level (capped by each stretch's length)
    template: str = "mendoza2022"
    min_delta_bic: float = 6.0         # a flare must beat a quadratic, and each extra component the last model
    min_component_sigma: float = 3.0     # an extra component's amplitude: at least this × the local scatter
    min_component_fraction: float = 0.1  # and this fraction of the strongest component's
    ar1_correction: bool = True        # the BIC uses an effective number of points for the residual's lag-one correlation
    min_shape_delta_bic: float = 10.0  # and the chosen templates must beat as many symmetric Gaussian bumps by this much
    max_components: int = 5
    min_fwhm_cadences: float = 0.25    # a fitted component narrower than this fraction of a cadence is rejected
    flare_temperature_k: float = FLARE_TEMPERATURE_K

    def as_dict(self) -> dict:
        return asdict(self)


def config_for(mission: str = "TESS", cadence_s: float | None = None, **overrides) -> FlareConfig:
    """Defaults by mission: TESS (2-min or 20-s, 6 h trend window, N3 = 3) and CHEOPS (Poyatos et al. 2025:
    20-minute Savitzky-Golay trend, N3 = 5)."""
    m = (mission or "TESS").upper()
    if m == "CHEOPS":
        cfg = FlareConfig(detrend="savgol", window_days=20.0 / 1440.0, n3=5, gap_cadences=3.0)
    elif cadence_s is not None and cadence_s < 60:
        cfg = FlareConfig(n3=5)  # 20-s TESS: five points span 100 s, the 2-min case's span is 6 min
    else:
        cfg = FlareConfig()
    return replace(cfg, **overrides) if overrides else cfg


# ---------------------------------------------------------------- detrending


def rotation_period(time, flux) -> float | None:
    """The dominant period (0.05 to 10 d) of the light curve's 30-minute bins (upper outliers clipped), when its
    Lomb-Scargle peak is clear (Baluev FAP < 1e-3) and its semi-amplitude is at least 5 × a bin's white noise, else
    None. Used only to size the detrending window."""
    from astropy.timeseries import LombScargle

    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    ok = np.isfinite(t) & np.isfinite(f)
    t, f = t[ok], f[ok]
    if t.size < 100 or t[-1] - t[0] < 0.5:
        return None
    w = 30.0 / 1440.0
    idx = np.floor((t - t[0]) / w).astype(int)
    cnt = np.bincount(idx)
    use = cnt >= 3
    tb = (np.bincount(idx, t) / np.maximum(cnt, 1))[use]
    fb = (np.bincount(idx, f) / np.maximum(cnt, 1))[use]
    if tb.size < 30:
        return None
    # white noise of a bin, from the unbinned point-to-point scatter (a rotating star's bins drift, so their own
    # differences would overstate it)
    s = _robust_sigma(np.diff(f)) / math.sqrt(2) / math.sqrt(max(float(np.median(cnt[use])), 1.0))
    med = np.median(fb)
    keep = fb < med + 5 * max(s, 1e-12) + 3 * np.std(fb)
    tb, fb = tb[keep], fb[keep]
    pmax = min(10.0, (tb[-1] - tb[0]) / 2)
    if pmax <= 0.1:
        return None
    ls = LombScargle(tb, fb)
    freq = np.linspace(1 / pmax, 1 / 0.05, 20000)
    pw = ls.power(freq)
    k = int(np.argmax(pw))
    if ls.false_alarm_probability(pw[k], method="baluev", minimum_frequency=freq[0], maximum_frequency=freq[-1]) > 1e-3:
        return None
    theta = ls.model_parameters(freq[k])
    if math.hypot(theta[1], theta[2]) < 5.0 * s:
        return None  # a period, but too shallow to bend the trend within a window
    return float(1 / freq[k])


def window_for(time, flux, config: "FlareConfig") -> tuple[float, float | None]:
    """The detrending window: the configured one, or P/8 (at least 20 minutes) for a star rotating in under 2 d."""
    if not config.adaptive_window:
        return config.window_days, None
    p = rotation_period(time, flux)
    if p is not None and p < 2.0:
        return min(config.window_days, max(p / 8.0, 20.0 / 1440.0)), p
    return config.window_days, p


def segments(time, gap: float) -> list[slice]:
    """Index slices of the stretches of ``time`` (sorted) separated by gaps longer than ``gap``."""
    t = np.asarray(time, float)
    if t.size == 0:
        return []
    cut = np.flatnonzero(np.diff(t) > gap) + 1
    edges = np.concatenate([[0], cut, [t.size]])
    return [slice(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:]) if b > a]


def cadence_of(time) -> float:
    d = np.diff(np.asarray(time, float))
    d = d[d > 0]
    return float(np.median(d)) if d.size else float("nan")


def _robust_sigma(x) -> float:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if x.size < 3:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def _dilate(mask, before: int, after: int) -> np.ndarray:
    out = mask.copy()
    idx = np.flatnonzero(mask)
    for i in idx:
        out[max(0, i - before): i + after + 1] = True
    return out


def _median_trend(flux, keep, width: int) -> np.ndarray:
    """Running median over ``width`` points with the masked points filled by interpolation from the kept ones."""
    x = np.arange(flux.size)
    f = flux.copy()
    if keep.sum() >= 2 and (~keep).any():
        f[~keep] = np.interp(x[~keep], x[keep], flux[keep])
    width = max(3, min(int(width) | 1, flux.size - (1 - flux.size % 2)))
    return median_filter(f, size=width, mode="nearest")


def _savgol_trend(flux, keep, width: int) -> tuple[np.ndarray, int]:
    """Savitzky-Golay trend; the polynomial degree (2 to 10, below the window) minimising the AIC of the
    residuals of the kept points (Poyatos et al. 2025, after Bruno et al. 2024)."""
    from scipy.signal import savgol_filter

    x = np.arange(flux.size)
    f = flux.copy()
    if keep.sum() >= 2 and (~keep).any():
        f[~keep] = np.interp(x[~keep], x[keep], flux[keep])
    width = int(width) | 1
    width = min(width, flux.size if flux.size % 2 else flux.size - 1)
    best, best_aic, best_deg = None, np.inf, 2
    m = int(keep.sum())
    for deg in range(2, 11):
        if deg >= width or m < 5:
            break
        tr = savgol_filter(f, width, deg, mode="interp")
        rss = float(np.sum((flux[keep] - tr[keep]) ** 2))
        # Effective parameters of a local polynomial smoother: about (deg + 1) × (n / window).
        k = (deg + 1) * flux.size / width
        aic = m * math.log(max(rss, 1e-300) / m) + 2 * k
        if aic < best_aic:
            best, best_aic, best_deg = tr, aic, deg
    if best is None:
        return _median_trend(flux, keep, width), 0
    return best, best_deg


def detrend(time, flux, config: FlareConfig = FlareConfig(), *, iterations: int = 3) -> dict:
    """The flare-preserving trend of each stretch, the residual (flux / trend − 1), and the local robust scatter.

    Upward excursions (``mask_sigma`` × scatter) are masked, together with the next points out to a quarter of
    the window (a flare's decay) and two points before, and the trend recomputed, ``iterations`` times."""
    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    cad = cadence_of(t)
    trend = np.ones_like(f)
    keep_all = np.ones(f.size, bool)
    degs = []
    width = max(5, int(round(config.window_days / cad)))
    for sl in segments(t, config.gap_cadences * cad):
        fs = f[sl]
        keep = np.isfinite(fs)
        if keep.sum() < 5:
            trend[sl] = np.nanmedian(fs) if keep.any() else 1.0
            keep_all[sl] = False
            continue
        tr = np.full(fs.size, np.nanmedian(fs))
        deg = 0
        for _ in range(iterations):
            if config.detrend == "savgol" and fs.size > 7:
                tr, deg = _savgol_trend(np.where(np.isfinite(fs), fs, tr), keep, min(width, fs.size))
            else:
                tr = _median_trend(np.where(np.isfinite(fs), fs, tr), keep, min(width, fs.size))
            r = fs / tr - 1.0
            s = _robust_sigma(r[keep])
            up = np.isfinite(r) & (r > config.mask_sigma * s)
            keep = np.isfinite(fs) & ~_dilate(up, 2, max(3, width // 4))
            if keep.sum() < 5:
                keep = np.isfinite(fs)
        trend[sl] = tr
        keep_all[sl] = keep
        degs.append(deg)
    resid = f / trend - 1.0
    sigma = local_sigma(t, resid, keep_all, config, cad)
    return {"trend": trend, "resid": resid, "sigma": sigma, "quiet": keep_all, "cadence": cad,
            "savgol_degrees": degs if config.detrend == "savgol" else None}


def local_sigma(time, resid, keep, config: FlareConfig, cadence: float) -> np.ndarray:
    """Robust scatter of the masked residual in a running window (the detrend window), per stretch."""
    t = np.asarray(time, float)
    out = np.full(resid.size, np.nan)
    width = max(15, int(round(config.window_days / cadence)))
    for sl in segments(t, config.gap_cadences * cadence):
        r = resid[sl]
        k = keep[sl] & np.isfinite(r)
        glob = _robust_sigma(r[k]) if k.sum() >= 5 else _robust_sigma(r)
        if k.sum() < 15 or r.size < 15:
            out[sl] = glob
            continue
        x = np.arange(r.size)
        med = np.interp(x, x[k], r[k])
        dev = np.abs(r - med)
        dev[~k] = np.interp(x[~k], x[k], dev[k]) if (~k).any() else dev[~k]
        w = min(width | 1, r.size if r.size % 2 else r.size - 1)
        loc = 1.4826 * median_filter(dev, size=w, mode="nearest")
        out[sl] = np.where(np.isfinite(loc) & (loc > 0), np.maximum(loc, 0.5 * glob), glob)
    return out


# ---------------------------------------------------------------- wavelet denoising


def have_pywavelets() -> bool:
    try:
        import pywt  # noqa: F401
    except ImportError:
        return False
    return True


def swt_denoise(x, *, wavelet: str = "db18", level: int = 2) -> np.ndarray:
    """Stationary-wavelet denoising of one evenly sampled stretch (Poyatos et al. 2025): the series is padded by
    reflection to a multiple of 2^level, each detail level's coefficients are hard-thresholded at
    λ = σ √(2 ln N) with σ = MAD / 0.6745 of that level, and the inverse transform is cropped back."""
    try:
        import pywt
    except ImportError as exc:
        raise ImportError("wavelet denoising needs PyWavelets: pip install 'setuhq[wavelets]'") from exc
    x = np.asarray(x, float)
    n = x.size
    filt = pywt.Wavelet(wavelet).dec_len
    level = int(max(1, min(level, int(math.floor(math.log2(max(n, 2)))))))  # the padding below makes any length work
    if n < max(filt, 2 ** level) or level < 1:
        return x.copy()
    block = 2 ** level
    total = int(math.ceil(n / block) * block)
    pad = total - n
    left = pad // 2
    y = np.pad(x, (left, pad - left), mode="reflect") if pad else x.copy()
    mean = float(np.mean(y))
    coeffs = pywt.swt(y - mean, wavelet, level=level, trim_approx=True, norm=True)
    lam_n = math.sqrt(2.0 * math.log(total))
    out = [coeffs[0]]
    for d in coeffs[1:]:
        s = float(np.median(np.abs(d - np.median(d)))) / 0.6745
        out.append(pywt.threshold(d, s * lam_n, mode="hard") if s > 0 else d)
    rec = pywt.iswt(out, wavelet, norm=True) + mean
    return rec[left:left + n]


def denoise_residual(time, resid, config: FlareConfig, cadence: float) -> np.ndarray:
    out = np.array(resid, float)
    for sl in segments(np.asarray(time, float), config.gap_cadences * cadence):
        r = out[sl]
        ok = np.isfinite(r)
        if ok.sum() < 8:
            continue
        r2 = r.copy()
        if (~ok).any():
            x = np.arange(r.size)
            r2[~ok] = np.interp(x[~ok], x[ok], r[ok])
        out[sl] = np.where(ok, swt_denoise(r2, wavelet=config.wavelet, level=config.level), np.nan)
    return out


# ---------------------------------------------------------------- candidates


def find_candidates(time, resid, sigma, err, config: FlareConfig, cadence: float) -> list[tuple[int, int]]:
    """Runs of at least N3 consecutive points with resid/σ ≥ N1 and (resid − err)/σ ≥ N2, extended while the
    residual stays above ``tail_sigma`` σ, merged when they touch; never across a gap. Index pairs [i, j]."""
    t = np.asarray(time, float)
    r = np.asarray(resid, float)
    s = np.asarray(sigma, float)
    e = np.zeros_like(r) if err is None else np.nan_to_num(np.asarray(err, float))
    with np.errstate(invalid="ignore", divide="ignore"):
        hit = np.isfinite(r) & (r / s >= config.n1) & ((r - e) / s >= config.n2)
    out: list[tuple[int, int]] = []
    for sl in segments(t, config.gap_cadences * cadence):
        a0, b0 = sl.start, sl.stop
        i = a0
        while i < b0:
            if not hit[i]:
                i += 1
                continue
            j = i
            while j + 1 < b0 and hit[j + 1]:
                j += 1
            if j - i + 1 >= config.n3:
                lo, hi = i, j
                while lo - 1 >= a0 and np.isfinite(r[lo - 1]) and r[lo - 1] > config.tail_sigma * s[lo - 1]:
                    lo -= 1
                while hi + 1 < b0 and np.isfinite(r[hi + 1]) and r[hi + 1] > config.tail_sigma * s[hi + 1]:
                    hi += 1
                if out and lo <= out[-1][1] + 2 and out[-1][0] >= a0:
                    out[-1] = (out[-1][0], max(out[-1][1], hi))
                else:
                    out.append((lo, hi))
            i = j + 1
    return out


# ---------------------------------------------------------------- morphology


def _model(params, t, n, exposure, template):
    c0, c1 = params[0], params[1]
    t_ref = t[0]
    y = c0 + c1 * (t - t_ref)
    for k in range(n):
        tp, lf, la = params[2 + 3 * k: 5 + 3 * k]
        y = y + integrated_template(t, tp, math.exp(lf), math.exp(la), exposure=exposure, template=template)
    return y


def _bic(rss: float, m: int, k: int, rho: float = 0.0) -> float:
    """BIC with the noise variance estimated from the fit: N ln(RSS / M) + k ln N, with N the effective number of
    independent points, M (1 − ρ) / (1 + ρ) for a lag-one correlation ρ of the noise (ρ = 0: the usual M). Red
    noise makes every extra component look more significant than it is; this takes that back."""
    n_eff = m * (1.0 - rho) / (1.0 + rho) if rho > 0 else m
    n_eff = max(n_eff, k + 2.0)
    return n_eff * math.log(max(rss, 1e-300) / m) + k * math.log(n_eff)


def _aic(rss: float, m: int, k: int) -> float:
    return m * math.log(max(rss, 1e-300) / m) + 2 * k


def fit_flare(t, r, *, t_start: float, t_end: float, cadence: float, config: FlareConfig, rho: float = 0.0,
              sigma: float | None = None) -> dict:
    """Fit 0..max_components flare templates (plus a linear baseline) to the residual ``r`` in a window, and pick
    the number of components by BIC (each one must lower it by ``min_delta_bic``). The null is a quadratic.

    Returns the chosen model with its components (t_peak, FWHM, amplitude, ED), the BIC and AIC of every model
    tried, and ``validated`` (one flare beat the quadratic by ``min_delta_bic``)."""
    t = np.asarray(t, float)
    r = np.asarray(r, float)
    m = t.size
    dur = max(t_end - t_start, cadence)
    tt = t - t[0]
    quad = np.polyfit(tt, r, 2)
    rss0 = float(np.sum((r - np.polyval(quad, tt)) ** 2))
    rho = rho if config.ar1_correction else 0.0
    tried = [{"n": 0, "bic": _bic(rss0, m, 3, rho), "aic": _aic(rss0, m, 3), "rss": rss0}]
    fwhm_lo = max(config.min_fwhm_cadences * cadence * 0.5, 1e-6)
    fwhm_hi = max(2.0 * dur, 4 * cadence)
    best = None
    params = np.array([0.0, 0.0])
    for n in range(1, config.max_components + 1):
        if m <= 2 + 3 * n + 2:
            break
        cur = _model(params, t, n - 1, cadence, config.template) if n > 1 else np.zeros_like(r)
        inwin = (t >= t_start - cadence) & (t <= t_end)
        res = r - cur
        k = int(np.argmax(np.where(inwin, res, -np.inf)))
        amp0 = max(float(res[k]), 1e-6)
        fw0 = float(np.clip(0.15 * dur, max(cadence, fwhm_lo * 2), fwhm_hi / 2))
        p0 = np.concatenate([params, [t[k], math.log(fw0), math.log(amp0)]])
        lo = [-np.inf, -np.inf] + sum(([t_start - 2 * cadence, math.log(fwhm_lo), math.log(1e-7)] for _ in range(n)), [])
        hi = [np.inf, np.inf] + sum(([t_end + cadence, math.log(fwhm_hi), math.log(10.0)] for _ in range(n)), [])
        p0 = np.clip(p0, np.array(lo) + 1e-12, np.array(hi) - 1e-12)
        try:
            sol = optimize.least_squares(lambda p: _model(p, t, n, cadence, config.template) - r, p0,
                                         bounds=(lo, hi), max_nfev=400 * (n + 1), x_scale="jac")
        except (ValueError, FloatingPointError):
            break
        rss = float(np.sum(sol.fun ** 2))
        kpar = 2 + 3 * n
        entry = {"n": n, "bic": _bic(rss, m, kpar, rho), "aic": _aic(rss, m, kpar), "rss": rss, "params": sol.x}
        tried.append(entry)
        prev = tried[-2]
        if prev["bic"] - entry["bic"] < config.min_delta_bic:
            break
        if n > 1:
            # An extra component must also be a visible peak: at least min_component_sigma × the local scatter and
            # min_component_fraction of the strongest component. A bright flare's small departures from the template
            # (or from the trend under it) otherwise pass the BIC as a stream of tiny components.
            amps = np.exp(np.asarray(sol.x[4::3]))
            noise = sigma if sigma else _robust_sigma(r - _model(sol.x, t, n, cadence, config.template))
            if amps.min() < max(config.min_component_sigma * noise, config.min_component_fraction * amps.max()):
                entry["rejected"] = "a component below the visibility limits"
                break
        best = entry
        params = sol.x
    shape = None
    if best is not None:
        # The same number of symmetric Gaussian bumps, started at the template components' peaks: a flare must fit
        # better as a fast rise and slow decay than as symmetric bumps.
        nb = best["n"]
        pb = best["params"]

        def gauss(p):
            y = p[0] + p[1] * (t - t[0])
            for q in range(nb):
                a, c, w = p[2 + 3 * q: 5 + 3 * q]
                y = y + a * np.exp(-0.5 * ((t - c) / w) ** 2)
            return y
        g0 = [0.0, 0.0]
        lo_g, hi_g = [-np.inf, -np.inf], [np.inf, np.inf]
        for q in range(nb):
            tp, lf, la = pb[2 + 3 * q: 5 + 3 * q]
            g0 += [math.exp(la), tp, max(math.exp(lf) / 1.5, cadence / 5)]
            lo_g += [0.0, t_start - 2 * cadence, cadence / 10]
            hi_g += [10.0, t_end + cadence, fwhm_hi]
        g0 = np.clip(g0, np.array(lo_g) + 1e-12, np.array(hi_g) - 1e-12)
        try:
            gs = optimize.least_squares(lambda p: gauss(p) - r, g0, bounds=(lo_g, hi_g), max_nfev=400 * (nb + 1))
            shape = _bic(float(np.sum(gs.fun ** 2)), m, 2 + 3 * nb, rho) - best["bic"]
        except (ValueError, FloatingPointError):
            shape = None
    validated = best is not None and shape is not None and shape >= config.min_shape_delta_bic
    comps = []
    if best is not None:
        p = best["params"]
        area = template_area(config.template)
        for k in range(best["n"]):
            tp, lf, la = p[2 + 3 * k: 5 + 3 * k]
            fw, am = math.exp(lf), math.exp(la)
            comps.append({"t_peak": float(tp), "fwhm_days": fw, "amplitude": am,
                          "ed_s": am * fw * area * 86400.0, "too_narrow": fw < config.min_fwhm_cadences * cadence})
        comps.sort(key=lambda c: c["t_peak"])
    return {"validated": validated, "beats_quadratic": best is not None, "rho": round(float(rho), 4),
            "delta_bic_shape": None if shape is None else round(shape, 3), "n_components": len(comps), "components": comps,
            "params": None if best is None else best["params"],
            "models": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in e.items() if k != "params"} for e in tried],
            "delta_bic_vs_quadratic": None if best is None else round(tried[0]["bic"] - best["bic"], 3),
            "delta_aic_vs_quadratic": None if best is None else round(tried[0]["aic"] - best["aic"], 3)}


def _half_max_width(t, y) -> float:
    """Width at half maximum of a sampled profile (linear interpolation), in the time unit."""
    if y.size < 3 or not np.isfinite(y).all():
        return float("nan")
    k = int(np.argmax(y))
    h = y[k] / 2.0
    i = k
    while i > 0 and y[i] > h:
        i -= 1
    j = k
    while j < y.size - 1 and y[j] > h:
        j += 1
    tl = t[i] if y[i] > h or i == k else np.interp(h, [y[i], y[i + 1]], [t[i], t[i + 1]])
    tr = t[j] if y[j] > h or j == k else np.interp(h, [y[j], y[j - 1]], [t[j], t[j - 1]])
    return float(tr - tl)


def _lag1(r, keep) -> float:
    """Lag-one autocorrelation of the quiet residual of one stretch (pairs of consecutive quiet points), at least 0."""
    r = np.asarray(r, float)
    ok = np.asarray(keep, bool) & np.isfinite(r)
    pair = ok[:-1] & ok[1:]
    if pair.sum() < 10:
        return 0.0
    a, b = r[:-1][pair], r[1:][pair]
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.clip(np.corrcoef(a, b)[0, 1], 0.0, 0.95))


# ---------------------------------------------------------------- energies


# Sullivan et al. (2015, ApJ 809, 77, §6.1): a T = 0 star gives 4.03e-6 erg s^-1 cm^-2 integrated over the TESS band
# (an A0V template through the TESS response, Vega at 3.44e-9 erg s^-1 cm^-2 Å^-1 at 5556 Å). Medina et al. (2020,
# §3.3) and most TESS flare studies use it for the stars' TESS-band luminosity.
TESS_ZERO_POINT_ERG_S_CM2 = 4.03e-6


def stellar_band_luminosity(star: dict | None, band: str = "TESS") -> dict:
    """The star's quiescent luminosity in the band, by two routes reported side by side:

    * **magnitude** (TESS only): 4πd² × 4.03e-6 erg s⁻¹ cm⁻² × 10^(−0.4 Tmag) (Sullivan et al. 2015's zero point), from
      the TESS magnitude and the distance;
    * **Teff and radius**: 4πR² · π∫R B_λ(Teff) dλ, a Planck spectrum through the instrument response.

    The magnitude route is the primary one when Tmag and the distance are known (it needs no model of the star's
    spectrum); otherwise Teff and radius. Missing inputs give ``None`` with the reason; nothing is guessed. A
    ``teff_source`` in ``star`` (for example "Teff from the CHEOPS archive") is carried into the result."""
    star = star or {}
    teff, rad = star.get("teff"), star.get("radius")
    mag, d = star.get("tmag"), star.get("distance_pc")
    out = {"band": band, "teff": teff, "teff_source": star.get("teff_source", "TIC v8.2" if teff else None),
           "radius_rsun": rad, "tmag": mag, "distance_pc": d,
           "l_band_teff_radius_erg_s": None, "l_band_magnitude_erg_s": None, "l_band_erg_s": None, "route": None}
    if teff and rad and teff > 0 and rad > 0:
        r_cm = rad * R_SUN_CM
        out["l_band_teff_radius_erg_s"] = 4.0 * math.pi * r_cm ** 2 * math.pi * band_integral(teff, band)
    if band.upper() == "TESS" and mag is not None and d and d > 0:
        out["l_band_magnitude_erg_s"] = 4.0 * math.pi * (d * PC_CM) ** 2 * TESS_ZERO_POINT_ERG_S_CM2 * 10 ** (-0.4 * mag)
    if out["l_band_magnitude_erg_s"]:
        out["l_band_erg_s"], out["route"] = out["l_band_magnitude_erg_s"], "magnitude and distance (Sullivan et al. 2015 zero point)"
    elif out["l_band_teff_radius_erg_s"]:
        out["l_band_erg_s"], out["route"] = out["l_band_teff_radius_erg_s"], f"Teff ({out['teff_source']}) and radius, Planck spectrum"
    else:
        out["why_unavailable"] = ("neither a TESS magnitude and distance nor a Teff and radius: the band luminosity, and so the "
                                  "flare energies, are unavailable")
    return out


def flare_energies(ed_s: float, star: dict | None, band: str = "TESS", temperature: float = FLARE_TEMPERATURE_K) -> dict:
    """E_band = ED × L★,band (the primary route of :func:`stellar_band_luminosity`) and E_bol for a ``temperature``
    blackbody flare, E_bol = E_band σT⁴ / (4π ∫R B_λ(T) dλ) (Shibayama et al. 2013; Günther et al. 2020: with L★,band
    from Teff and radius this is their ED · πR★²σT⁴ ∫R B(Teff) / ∫R B(T)). Both routes are reported side by side;
    ``None`` with the reason when neither is possible."""
    lum = stellar_band_luminosity(star, band)
    if lum["l_band_erg_s"] is None or ed_s is None or not np.isfinite(ed_s):
        return {"e_band_erg": None, "e_bol_erg": None, "status": "unavailable",
                "why": lum.get("why_unavailable", "no equivalent duration")}
    conv = SIGMA_SB * temperature ** 4 / (4.0 * math.pi * band_integral(temperature, band))
    e_band = ed_s * lum["l_band_erg_s"]
    out = {"e_band_erg": e_band, "e_bol_erg": e_band * conv, "status": "computed", "luminosity_route": lum["route"],
           "assumption": f"the flare radiates as a {temperature:.0f} K blackbody (Shibayama et al. 2013; Günther et al. 2020)"}
    if lum["l_band_magnitude_erg_s"]:
        out["e_band_magnitude_erg"] = ed_s * lum["l_band_magnitude_erg_s"]
    if lum["l_band_teff_radius_erg_s"]:
        out["e_band_teff_radius_erg"] = ed_s * lum["l_band_teff_radius_erg_s"]
        out["e_bol_teff_radius_erg"] = out["e_band_teff_radius_erg"] * conv
        out["teff_source"] = lum["teff_source"]
    return out


# ---------------------------------------------------------------- detection, end to end


def detect_flares(time, flux, flux_err=None, *, config: FlareConfig | None = None, star: dict | None = None,
                  band: str = "TESS", mission: str | None = None) -> dict:
    """Detect and characterise flares in one light curve (relative flux, any time unit in days).

    Returns ``{"flares": [...], "rejected": [...], "summary": {...}, "config": {...}}``. Each flare has its window,
    peak time, amplitude (relative flux), FWHM, rise and decay times, the ED in seconds (``ed_s``, the integral of
    the fitted model, which keeps the tail below the noise; ``ed_data_s`` sums the data inside the detection window),
    the number of components and each component, the BIC evidence, the peak significance, and its energies (or
    why they are unavailable). ``rejected`` lists candidates the template did not validate."""
    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    e = None if flux_err is None else np.asarray(flux_err, float)
    ok = np.isfinite(t) & np.isfinite(f)
    if e is not None:
        ok &= np.isfinite(e)
    order = np.argsort(t[ok])
    t, f = t[ok][order], f[ok][order]
    e = e[ok][order] if e is not None else None
    med = float(np.median(f)) if f.size else 1.0
    f = f / med
    if e is not None:
        e = e / med
    cad = cadence_of(t)
    if config is None:
        config = config_for(mission or band, cad * 86400.0)
    if t.size < 20 or not np.isfinite(cad):
        return {"flares": [], "rejected": [], "summary": {"n_points": int(t.size), "observing_days": 0.0,
                                                          "n_flares": 0, "note": "too few points"}, "config": config.as_dict()}
    window, prot = window_for(t, f, config)
    if window != config.window_days:
        config = replace(config, window_days=window, adaptive_window=False)
    det = detrend(t, f, config)
    resid, sigma = det["resid"], det["sigma"]
    search, search_sigma = resid, sigma
    if config.denoise:
        # As AltaiPony does on a denoised light curve, the local scatter is measured on the series searched.
        search = denoise_residual(t, resid, config, cad)
        search_sigma = local_sigma(t, search, det["quiet"], config, cad)
    cands = find_candidates(t, search, search_sigma, None if config.denoise else e, config, cad)
    flares, rejected = [], []
    segs = segments(t, config.gap_cadences * cad)
    seg_of = np.empty(t.size, int)
    for k, sl in enumerate(segs):
        seg_of[sl] = k
    rho_of = [_lag1(resid[sl], det["quiet"][sl]) for sl in segs]
    for i, j in cands:
        sl = segs[seg_of[i]]
        dur = t[j] - t[i] + cad
        lo_t = t[i] - max(5 * cad, 0.5 * dur)
        hi_t = t[j] + max(10 * cad, 1.0 * dur)
        w = np.flatnonzero((t >= lo_t) & (t <= hi_t))
        w = w[(w >= sl.start) & (w < sl.stop)]
        fit = fit_flare(t[w], resid[w], t_start=t[i], t_end=t[j], cadence=cad, config=config, rho=rho_of[seg_of[i]],
                        sigma=float(np.nanmedian(sigma[w])))
        peak_k = i + int(np.argmax(resid[i:j + 1]))
        sig = float(resid[peak_k] / sigma[peak_k]) if sigma[peak_k] > 0 else float("nan")
        base = {"t_start": float(t[i]), "t_end": float(t[j]), "n_points": int(j - i + 1),
                "peak_sigma": round(sig, 2), "detected_on": "denoised" if config.denoise else "original"}
        good = [c for c in fit["components"] if not c["too_narrow"]]
        if not fit["validated"] or not good:
            if not fit["beats_quadratic"]:
                why = "no flare template beats a quadratic by ΔBIC ≥ %g" % config.min_delta_bic
            elif not fit["validated"]:
                why = ("a symmetric bump fits about as well as a flare (ΔBIC %s < %g): no fast rise and slow decay"
                       % (fit["delta_bic_shape"], config.min_shape_delta_bic))
            else:
                why = "every fitted component is narrower than the cadence allows"
            rejected.append({**base, "why": why, "delta_bic_shape": fit["delta_bic_shape"], "models": fit["models"]})
            continue
        win = slice(i, j + 1)
        ed_data = float(np.trapezoid(resid[win], t[win]) * 86400.0) if j > i else float(resid[i] * cad * 86400.0)
        ed_err = float(math.sqrt(np.sum(sigma[win] ** 2)) * cad * 86400.0)
        model_flare = sum(integrated_template(t[w], c["t_peak"], c["fwhm_days"], c["amplitude"], exposure=cad,
                                              template=config.template) for c in fit["components"])
        fine = np.linspace(t[w][0], t[w][-1], max(200, 20 * w.size))
        fine_model = sum(TEMPLATES[config.template](fine, c["t_peak"], c["fwhm_days"], c["amplitude"]) for c in fit["components"])
        kpk = int(np.argmax(fine_model))
        amp_model = float(fine_model[kpk])
        tpk = float(fine[kpk])
        ed_model = float(sum(c["ed_s"] for c in fit["components"]))
        energies = flare_energies(ed_model, star, band, config.flare_temperature_k)
        comp_out = []
        for c in fit["components"]:
            ce = flare_energies(c["ed_s"], star, band, config.flare_temperature_k)
            comp_out.append({"t_peak": round(c["t_peak"], 6), "fwhm_minutes": round(c["fwhm_days"] * 1440, 3),
                             "amplitude": round(c["amplitude"], 7), "ed_s": round(c["ed_s"], 4),
                             "e_bol_erg": ce["e_bol_erg"]})
        flares.append({
            **base, "t_peak": round(tpk, 6), "amplitude": round(amp_model, 7),
            "amplitude_data": round(float(resid[peak_k]), 7),
            "fwhm_minutes": round(_half_max_width(fine, fine_model) * 1440, 3),
            "rise_minutes": round((tpk - t[i]) * 1440, 3), "decay_minutes": round((t[j] - tpk) * 1440, 3),
            "duration_minutes": round(dur * 1440, 3),
            "ed_s": round(ed_model, 4), "ed_data_s": round(ed_data, 4), "ed_err_s": round(ed_err, 4),
            "n_components": len(fit["components"]), "morphology": "complex" if len(fit["components"]) > 1 else "simple",
            "components": comp_out, "delta_bic_vs_quadratic": fit["delta_bic_vs_quadratic"],
            "delta_aic_vs_quadratic": fit["delta_aic_vs_quadratic"], "delta_bic_shape": fit["delta_bic_shape"],
            "models": fit["models"],
            "delta_bic_components": [round(a["bic"] - b["bic"], 3) for a, b in zip(fit["models"][1:], fit["models"][2:])],
            "model_rms": round(float(np.std(resid[w] - model_flare)), 7), **energies,
        })
    days = float(sum(t[sl][-1] - t[sl][0] + cad for sl in segs))
    summary = {"n_points": int(t.size), "cadence_s": round(cad * 86400.0, 3), "observing_days": round(days, 4),
               "n_candidates": len(cands), "n_flares": len(flares), "n_rejected": len(rejected),
               "n_complex": sum(1 for x in flares if x["n_components"] > 1),
               "rate_per_day": round(len(flares) / days, 4) if days > 0 else None,
               "median_sigma": float(np.nanmedian(sigma)), "band": band,
               "noise_lag1_correlation": [round(x, 4) for x in rho_of], "window_days_used": config.window_days,
               "rotation_period_days": prot,
               "savgol_degrees": det["savgol_degrees"],
               "energy_basis": stellar_band_luminosity(star, band)}
    return {"flares": flares, "rejected": rejected, "summary": summary, "config": config.as_dict(),
            "template": TEMPLATE_REF[config.template]}


# ---------------------------------------------------------------- flare frequency distribution


def powerlaw_mle(energies, e_min: float) -> dict:
    """Maximum-likelihood index of dN/dE ∝ E^-α above ``e_min`` (Clauset et al. 2009, eq. 3.1), its standard error
    (α − 1)/√n, and the small-sample unbiased value ((n − 2)/n)(α − 1) + 1 (e.g. Ilin et al. 2021)."""
    x = np.asarray([v for v in energies if v is not None and np.isfinite(v) and v >= e_min], float)
    n = x.size
    if n < 2 or e_min <= 0:
        return {"n": int(n), "alpha": None, "alpha_err": None, "alpha_unbiased": None, "e_min": e_min}
    s = float(np.sum(np.log(x / e_min)))
    a = 1.0 + n / s if s > 0 else float("nan")
    return {"n": int(n), "e_min": e_min, "alpha": a, "alpha_err": (a - 1.0) / math.sqrt(n),
            "alpha_unbiased": (n - 2) / n * (a - 1.0) + 1.0 if n > 2 else None}


def _lognormal_trunc_nll(params, logx, log_xmin):
    mu, log_s = params
    s = math.exp(log_s)
    z = (logx - mu) / s
    norm = special.ndtr(-(log_xmin - mu) / s)
    if norm <= 0:
        return 1e300
    return float(np.sum(0.5 * z ** 2 + math.log(s * math.sqrt(2 * math.pi)) + logx) + logx.size * math.log(norm))


def compare_lognormal(energies, e_min: float) -> dict:
    """The power law against a log-normal truncated at ``e_min``, both fitted by maximum likelihood: the
    log-likelihood ratio R (positive favours the power law), its normalised value and the two-sided p-value of
    Vuong's test (Clauset et al. 2009, appendix C)."""
    x = np.asarray([v for v in energies if v is not None and np.isfinite(v) and v >= e_min], float)
    n = x.size
    pl = powerlaw_mle(x, e_min)
    if n < 5 or not pl["alpha"]:
        return {"n": int(n), "R": None, "p_value": None, "preferred": None, "note": "fewer than 5 flares above E_min"}
    a = pl["alpha"]
    lpl = math.log(a - 1.0) - math.log(e_min) - a * np.log(x / e_min)
    logx = np.log(x)
    lmin = math.log(e_min)
    best = optimize.minimize(_lognormal_trunc_nll, [float(np.mean(logx)), math.log(max(float(np.std(logx)), 0.1))],
                             args=(logx, lmin), method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-8, "maxiter": 4000})
    mu, s = best.x[0], math.exp(best.x[1])
    norm = special.ndtr(-(lmin - mu) / s)
    lln = -0.5 * ((logx - mu) / s) ** 2 - np.log(s * math.sqrt(2 * math.pi)) - logx - math.log(norm)
    d = lpl - lln
    r = float(np.sum(d))
    sd = float(np.std(d))
    p = float(special.erfc(abs(r) / (math.sqrt(2 * n) * sd))) if sd > 0 else 1.0
    return {"n": int(n), "R": r, "R_normalised": r / (math.sqrt(n) * sd) if sd > 0 else None, "p_value": p,
            "preferred": ("power law" if r > 0 else "log-normal") if p < 0.1 else "neither (p ≥ 0.1)",
            "lognormal_mu_ln_erg": float(mu), "lognormal_sigma": float(s), "alpha": a}


def ffd(energies, observing_days: float) -> dict:
    """The cumulative flare frequency distribution: energy and rate (per day) of flares at or above it."""
    x = np.sort(np.asarray([v for v in energies if v is not None and np.isfinite(v)], float))[::-1]
    if not observing_days or observing_days <= 0:
        return {"energy": [], "rate_per_day": []}
    return {"energy": x.tolist(), "rate_per_day": (np.arange(1, x.size + 1) / observing_days).tolist()}


# ---------------------------------------------------------------- completeness: injection and recovery


def inject_recover(time, flux, flux_err=None, *, config: FlareConfig | None = None, star: dict | None = None,
                   band: str = "TESS", n_trials: int = 10, per_trial: int = 10, seed: int = 0,
                   amp_range=(1e-4, 1e-1), fwhm_minutes=(1.0, 60.0), mission: str | None = None,
                   real_flares: list[dict] | None = None, second: dict | None = None) -> dict:
    """Completeness of the whole detection on this star's own light curve.

    Each trial injects ``per_trial`` Mendoza flares at random observed times; it multiplies the flux and runs
    :func:`detect_flares` again. Amplitude and FWHM are drawn once per injection (log-uniform) and only the position
    is redrawn, so the placed FWHM follows the drawn distribution instead of favouring short flares that fit between
    gaps. A flare is placed when its start (one FWHM before the peak) and its peak plus three FWHM lie inside one
    stretch of data (cf. Poyatos et al. 2025, Sect. 2.3: only flares whose start and stop fall within one visit are
    counted); a wider span (two FWHM before to eight after) must not overlap another injection or a detected real
    flare. Injections with no valid position after 200 tries are counted as ``unplaced`` with their FWHM.

    ``second`` (e.g. ``{"ratio": (0.05, 0.5), "separation_fwhm": (1, 5)}``) adds a second Mendoza component of the
    same FWHM after the first, its amplitude a log-uniform fraction of the first and its peak a uniform number of
    FWHM later; each row then says whether the detected flare holding the first peak also holds the second and came
    back as one component (``merged``).

    A flare is recovered when a detected flare's window contains its peak (within one cadence). Returns every
    injection (amplitude, FWHM, true ED, energy if the star has Teff and radius, recovered, recovered ED), the
    placed and unplaced FWHM, and completeness curves against amplitude, ED and energy."""
    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    rng = np.random.default_rng(seed)
    cad = cadence_of(t)
    if config is None:
        config = config_for(mission or band, cad * 86400.0)
    busy = [(fl["t_start"] - 10 * cad, fl["t_end"] + max(4 * (fl["t_end"] - fl["t_start"]), 0.1)) for fl in (real_flares or [])]
    stretches = segments(t, config.gap_cadences * cad)
    seg_id = np.empty(t.size, int)
    for q, sl in enumerate(stretches):
        seg_id[sl] = q
    rows = []
    unplaced = []
    area = template_area("mendoza2022")
    for trial in range(n_trials):
        f2 = f / np.median(f)
        placed = []
        for _ in range(per_trial):
            amp = float(10 ** rng.uniform(*np.log10(amp_range)))
            fw = float(10 ** rng.uniform(*np.log10(fwhm_minutes))) / 1440.0
            ratio = sep = None
            if second:
                ratio = float(10 ** rng.uniform(*np.log10(second.get("ratio", (0.05, 0.5)))))
                sep = float(rng.uniform(*second.get("separation_fwhm", (1.0, 5.0))))
            extra = (sep or 0.0) * fw
            for _try in range(200):
                ix = int(rng.integers(t.size))
                tp = float(t[ix] + rng.uniform(-0.5, 0.5) * cad)  # on the data, not in a gap
                sl = stretches[seg_id[ix]]
                need = (tp - fw - 2 * cad, tp + extra + 3 * fw + 3 * cad)
                if need[0] < t[sl.start] or need[1] > t[sl.stop - 1]:
                    continue  # start or peak + 3 FWHM across a gap: try another position
                span = (tp - 2 * fw - 2 * cad, tp + extra + 8 * fw + 3 * cad)
                if any(a < span[1] and b > span[0] for a, b in busy + [p["span"] for p in placed]):
                    continue
                placed.append({"tp": tp, "fw": fw, "amp": amp, "span": span, "ratio": ratio, "sep": sep})
                break
            else:
                unplaced.append(fw * 1440.0)
        model = np.zeros_like(f2)
        for p in placed:
            model += integrated_template(t, p["tp"], p["fw"], p["amp"], exposure=cad)
            if second:
                model += integrated_template(t, p["tp"] + p["sep"] * p["fw"], p["fw"], p["ratio"] * p["amp"], exposure=cad)
        out = detect_flares(t, f2 * (1.0 + model), flux_err, config=config, star=star, band=band)
        for p in placed:
            tp, fw, amp = p["tp"], p["fw"], p["amp"]
            ed = amp * fw * area * 86400.0 * (1.0 + (p["ratio"] or 0.0))
            hit = [fl for fl in out["flares"] if fl["t_start"] - cad <= tp <= fl["t_end"] + cad]
            en = flare_energies(ed, star, band, config.flare_temperature_k)["e_bol_erg"]
            row = {"trial": trial, "t_peak": tp, "amplitude": amp, "fwhm_minutes": fw * 1440, "ed_s": ed,
                   "e_bol_erg": en, "recovered": bool(hit),
                   "ed_recovered_s": hit[0]["ed_s"] if hit else None,
                   "amplitude_recovered": hit[0]["amplitude"] if hit else None,
                   "n_components_recovered": hit[0]["n_components"] if hit else None,
                   "delta_bic_components": hit[0].get("delta_bic_components") if hit else None,
                   "snr": amp / float(out["summary"]["median_sigma"]) if out["summary"].get("median_sigma") else None}
            if second:
                t2 = tp + p["sep"] * fw
                same = bool(hit) and hit[0]["t_start"] - cad <= t2 <= hit[0]["t_end"] + cad
                # another injection's peak inside the same detected flare: a blend of two injections
                shared = bool(hit) and any(q is not p and hit[0]["t_start"] - cad <= q["tp"] <= hit[0]["t_end"] + cad
                                           for q in placed)
                row.update({"second_ratio": p["ratio"], "separation_fwhm": p["sep"], "second_in_same_flare": same,
                            "blend": shared, "merged": bool(same and hit[0]["n_components"] == 1)})
            rows.append(row)
    return {"injections": rows, "n": len(rows), "seed": seed, "config": config.as_dict(),
            "placement": placement_summary([r["fwhm_minutes"] for r in rows], unplaced, fwhm_minutes),
            "by_amplitude": completeness_curve(rows, "amplitude"), "by_ed": completeness_curve(rows, "ed_s"),
            "by_energy": completeness_curve(rows, "e_bol_erg") if any(r["e_bol_erg"] for r in rows) else None}


def placement_summary(placed_fwhm, unplaced_fwhm, fwhm_minutes, bins_per_decade: int = 4) -> dict:
    """Placed against expected FWHM: counts in equal logarithmic bins (about ``bins_per_decade`` per decade) next to
    what a log-uniform draw over ``fwhm_minutes`` gives, plus the injections that found no position."""
    lo, hi = np.log10(fwhm_minutes[0]), np.log10(fwhm_minutes[1])
    edges = np.linspace(lo, hi, max(1, round((hi - lo) * bins_per_decade)) + 1)  # equal in log: equal expected shares
    v = np.log10(np.asarray(placed_fwhm, float)) if len(placed_fwhm) else np.array([])
    n = int(v.size)
    hist = []
    for a, b in zip(edges[:-1], edges[1:]):
        k = int(((v >= a) & ((v < b) if b < edges[-1] else (v <= b + 1e-12))).sum())
        hist.append({"lo_min": float(10 ** a), "hi_min": float(10 ** b), "placed": k,
                     "placed_fraction": k / n if n else None, "expected_fraction": float((b - a) / (hi - lo))})
    return {"n_placed": n, "n_unplaced": len(unplaced_fwhm), "unplaced_fwhm_minutes": [float(x) for x in unplaced_fwhm],
            "histogram": hist}


def merge_rate(injections: list[dict]) -> dict:
    """Of the recovered two-component injections, the fraction that came back as one single-component flare holding
    both peaks (merged), overall and by secondary ratio and separation, with Wilson 95% intervals. Detected flares
    holding another injection's peak too (blends of two injections) are left out and counted. Secondaries below
    ``min_component_fraction`` of the primary cannot be kept as components by construction."""
    allrec = [x for x in injections if x.get("recovered") and "merged" in x]
    rec = [x for x in allrec if not x.get("blend")]

    def _cell(sub):
        k = sum(1 for x in sub if x["merged"])
        return {"n": len(sub), "merged": k, "rate": k / len(sub) if sub else None, "ci95": wilson(k, len(sub))}

    out = _cell(rec)
    out["blends_excluded"] = len(allrec) - len(rec)
    out["by_ratio"] = [dict(lo=a, hi=b, **_cell([x for x in rec if a <= x["second_ratio"] < b]))
                       for a, b in ((0.05, 0.1), (0.1, 0.2), (0.2, 0.5))]
    out["by_separation_fwhm"] = [dict(lo=a, hi=b, **_cell([x for x in rec if a <= x["separation_fwhm"] < b]))
                                 for a, b in ((1, 2), (2, 3), (3, 5))]
    out["by_ratio_ge_0p1_and_sep"] = [dict(lo=a, hi=b, **_cell([x for x in rec if x["second_ratio"] >= 0.1
                                                                 and a <= x["separation_fwhm"] < b]))
                                      for a, b in ((1, 2), (2, 3), (3, 5))]
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def completeness_curve(rows, key: str, bins_per_decade: int = 4) -> list[dict]:
    """Recovered fraction (with a Wilson 95% interval) in logarithmic bins of ``key``."""
    v = np.array([r[key] for r in rows if r.get(key)], float)
    rec = np.array([r["recovered"] for r in rows if r.get(key)], bool)
    if v.size == 0:
        return []
    lo, hi = math.floor(np.log10(v.min()) * bins_per_decade), math.ceil(np.log10(v.max()) * bins_per_decade)
    out = []
    for b in range(lo, hi):
        a, z = 10 ** (b / bins_per_decade), 10 ** ((b + 1) / bins_per_decade)
        m = (v >= a) & (v < z)
        n = int(m.sum())
        if n == 0:
            continue
        k = int(rec[m].sum())
        out.append({"lo": a, "hi": z, "n": n, "recovered": k, "fraction": k / n, "ci95": wilson(k, n)})
    return out


def completeness_limit(curve: list[dict], level: float = 0.9) -> float | None:
    """The lower edge of the first bin from which every bin's recovered fraction is at least ``level``."""
    for i, b in enumerate(curve):
        if all(c["fraction"] >= level for c in curve[i:]) and b["n"] >= 3:
            return b["lo"]
    return None


# ---------------------------------------------------------------- nulls


def inverted_null(time, flux, flux_err=None, *, config: FlareConfig | None = None, band: str = "TESS",
                  mission: str | None = None, real_flares: list[dict] | None = None) -> dict:
    """The detection on the flux turned upside down (2 − flux), with the real flares' windows (detected first, or
    given) left out: every 'flare' it finds is a false positive of the method on this star's own noise. Without the
    masking a real flare becomes a deep dip that drags the trend down and leaves bumps beside it. A real dip (a
    transit, an eclipse) still becomes a bump, so this null is an upper bound. Returns the count and the rate per day."""
    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    e = None if flux_err is None else np.asarray(flux_err, float)
    if real_flares is None:
        real_flares = detect_flares(t, f, e, config=config, band=band, mission=mission)["flares"]
    cad = cadence_of(t)
    keep = np.ones(t.size, bool)
    for fl in real_flares:
        dur = fl["t_end"] - fl["t_start"]
        keep &= ~((t >= fl["t_start"] - 5 * cad) & (t <= fl["t_end"] + max(10 * cad, dur)))
    out = detect_flares(t[keep], 2.0 * np.nanmedian(f) - f[keep], None if e is None else e[keep], config=config,
                        band=band, mission=mission)
    s = out["summary"]
    return {"false_positives": s["n_flares"], "observing_days": s["observing_days"], "masked_real_flares": len(real_flares),
            "rate_per_day": s.get("rate_per_day"), "events": [{k: x[k] for k in ("t_peak", "amplitude", "ed_s", "peak_sigma")}
                                                              for x in out["flares"]]}


def false_split_rate(injections: list[dict]) -> dict:
    """Of the injected single flares that were recovered, the fraction that came back as two or more components
    (each injection is one Mendoza template, so every split is false), with a Wilson 95% interval."""
    rec = [x for x in injections if x.get("recovered") and x.get("n_components_recovered")]
    # a recovered ED well above the injected one means the injection merged with a real flare or noise: a blend
    blend = [x for x in rec if x.get("ed_recovered_s") and x["ed_s"] > 0 and x["ed_recovered_s"] / x["ed_s"] > 1.5]
    clean = [x for x in rec if x not in blend]
    k = sum(1 for x in clean if x["n_components_recovered"] >= 2)
    return {"split": k, "recovered_clean": len(clean), "blends_excluded": len(blend),
            "rate": k / len(clean) if clean else None, "ci95": wilson(k, len(clean))}


def tune_denoising(time, flux, flux_err=None, *, wavelets=("haar", "db4", "db18"), levels=(1, 2, 3, 4),
                   mission: str = "TESS", band: str = "TESS", n_trials: int = 3, per_trial: int = 10, seed: int = 0,
                   amp_range=(1e-4, 1e-1), fwhm_minutes=(1.0, 60.0)) -> list[dict]:
    """Poyatos et al. (2025) chose the wavelet and decomposition level by injection and recovery; this does the
    same on a given light curve: for each (wavelet, level), and without denoising, the recovered fraction of the
    same injected flares (same seed) and the false positives on the flux-inverted light curve."""
    t = np.asarray(time, float)
    cad = cadence_of(t)
    grid = [(None, None)] + [(w, lv) for w in wavelets for lv in levels]
    out = []
    for w, lv in grid:
        cfg = config_for(mission, cad * 86400.0, denoise=w is not None, **({"wavelet": w, "level": lv} if w else {}))
        r = inject_recover(t, flux, flux_err, config=cfg, band=band, n_trials=n_trials, per_trial=per_trial, seed=seed,
                           amp_range=amp_range, fwhm_minutes=fwhm_minutes)
        k = sum(x["recovered"] for x in r["injections"])
        nul = inverted_null(t, flux, flux_err, config=cfg, band=band)
        out.append({"wavelet": w, "level": lv, "recovered": k, "injected": r["n"], "fraction": k / r["n"] if r["n"] else None,
                    "ci95": wilson(k, r["n"]), "inverted_false_positives": nul["false_positives"],
                    "by_amplitude": r["by_amplitude"]})
    return out

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Pixel-level vetting from TESS SPOC target pixel files (TPFs), after the Kepler/SPOC Data Validation (DV)
centroid tests (Twicken et al. 2018, doi:10.1088/1538-3873/aab694; ATLAS E5, E6, C9).

A transit on a neighbouring star, diluted in the target's aperture, can look like a small planet on the target.
The pixels say where the light was lost:

* **Difference image.** For every transit, the mean in-transit image is subtracted from the mean of the
  out-of-transit cadences on both sides; the per-transit differences are averaged. The difference image peaks on
  the star that dimmed. Its centroid is measured two ways: a 2-D Gaussian PSF fit (the primary measure, with errors
  from the fit covariance scaled by √χ²ᵣ) and a flux-weighted centroid inside the SPOC aperture (linear error
  propagation). Offsets are given relative to the out-of-transit centroid measured the same way (DV's "control"
  offset, robust to WCS errors) and to the catalogue position of the target (DV's "TIC" offset), in pixels and
  arcseconds, with the 2-D significance χ²₂ = Δᵀ C⁻¹ Δ and its p-value.
* **Fit quality.** As in DV, the correlation between the difference image and its PSF model is the quality metric;
  DV counts a measurement as reliable above 0.7 (ATLAS E6). A saturated target (a plateau of three or more pixels
  in one column near the brightest value: charge bleeding along the column) makes difference-image centroids
  unreliable, because the transit changes the length of the bleed trail, not the shape of a PSF. Both cases are
  reported as ``centroid_unreliable`` and do not raise ``centroid_offset``.
* **Centroid motion test.** The flux-weighted centroid of each cadence inside the aperture; its mean shift in
  transit (δx, δy) with errors, χ²₂ and p, and the implied source offset Δφ = −δφ(1 − D)/D for depth D.
* **Ghost diagnostic.** The transit's detection statistic in the aperture (core) and in a two-pixel ring around it
  (halo). A halo statistic above the core's suggests scattered light or a ghost (DV §III.7).
* **Momentum dumps.** Transits within half a duration of a reaction-wheel desaturation (TESS quality bit 32).
* **Neighbours.** For each catalogued star near the target (TIC, or Gaia DR3 when the TIC cannot be reached), the
  share of the aperture's flux it supplies (Gaussian PSF integrated over the aperture pixels), the eclipse depth it
  would need to produce the observed depth, and whether it is ruled out: a needed depth above 100% (ATLAS C9), or
  the difference-image centroid more than 3σ from it when the centroid is reliable. ``delta_mag_limit`` =
  −2.5 log₁₀(depth) is the faintest a star in the aperture can be and still produce the depth.

PSF. A circular Gaussian (σ = 1 pixel by default) stands in for the SPOC pixel response function. It is good
enough to locate an isolated source to a fraction of a pixel in the tests, not to model a crowded field; the
neighbour fluxes are an approximation and say so.

Everything here runs offline on a :class:`TargetPixels` object. :func:`load_tpf` reads a SPOC TPF FITS file;
:func:`fetch_tpf` downloads one into ``cache/tpf`` (gitignored) via lightkurve, or when the MAST search service
fails, from the public STScI bucket that MAST's download links redirect to. :func:`synthetic_tpf` makes test data.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.special import erf
from scipy.stats import chi2 as chi2_dist
from scipy.stats import norm

TESS_PIXEL_ARCSEC = 21.0       # nominal TESS pixel (ATLAS C9); the TPF's WCS gives the local scale when present
QUALITY_MIN = 0.7              # DV reliability threshold on the difference-image fit quality (ATLAS E6)
CENTROID_SIGMA = 3.0           # offset significance (Gaussian-equivalent σ) that raises centroid_offset
MOMENTUM_DUMP_BIT = 32         # TESS quality flag: reaction wheel desaturation event
SATURATION_PLATEAU = 0.95      # a pixel within 5% of the brightest one counts toward a saturation plateau
PSF_SIGMA_BOUNDS = (0.3, 5.0)  # the PSF fit's bounds on σ (pixels); a fit at the lower bound has collapsed
PSF_SIGMA_RATIO_MAX = 2.0      # difference and out-of-transit PSF widths differing by more: the fit is not a star
TMAG_ERR_DEFAULT = 0.25        # TESS-magnitude error assumed when the catalogue gives none (3σ ≈ a factor 2 in flux)
S3_BUCKET = "https://stpubdata.s3.amazonaws.com"
DISQUALIFYING = frozenset({"centroid_offset"})


@dataclass
class TargetPixels:
    """A target pixel file's time series of images. Images are indexed [cadence, row, column]."""

    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    quality: np.ndarray
    aperture: np.ndarray                 # bool [row, column]: the SPOC optimal aperture
    wcs: object | None = None            # astropy WCS of the image (pixel 0 = first column/row)
    header: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return self.flux.shape[1], self.flux.shape[2]

    def pixel_scale_arcsec(self) -> float:
        if self.wcs is not None:
            try:
                from astropy.wcs.utils import proj_plane_pixel_scales

                return float(np.mean(proj_plane_pixel_scales(self.wcs)) * 3600.0)
            except Exception:  # noqa: BLE001 (a malformed WCS falls back to the nominal scale)
                pass
        return TESS_PIXEL_ARCSEC

    def world_to_pixel(self, ra: float, dec: float) -> tuple[float, float] | None:
        """(column, row) of a sky position, 0-based in this image, or None without a WCS."""
        if self.wcs is None:
            return None
        x, y = self.wcs.all_world2pix([[ra, dec]], 0)[0]
        return float(x), float(y)

    def target_position(self) -> tuple[float, float] | None:
        """The target's (column, row): its catalogue position at the observation epoch. SPOC writes the
        proper-motion-propagated position into the aperture extension's RA_OBJ/DEC_OBJ; when only a J2000 position
        and proper motion are known, it is propagated here (:func:`propagate_position`)."""
        h = self.header
        if h.get("ra_epoch") is not None and h.get("dec_epoch") is not None:
            return self.world_to_pixel(h["ra_epoch"], h["dec_epoch"])
        if h.get("ra") is None or h.get("dec") is None:
            return None
        ra, dec = propagate_position(h["ra"], h["dec"], h.get("pmra"), h.get("pmdec"), years=h.get("years_since_2000"))
        return self.world_to_pixel(ra, dec)


def propagate_position(ra: float, dec: float, pmra_mas: float | None, pmdec_mas: float | None, *,
                       years: float | None) -> tuple[float, float]:
    """Move a J2000 position by its proper motion (mas/yr; pmRA includes cos δ) over ``years``. Linear in angle,
    which is accurate to well under a TESS pixel for decades of motion away from the poles."""
    if not years or pmra_mas is None or pmdec_mas is None:
        return ra, dec
    dec2 = dec + pmdec_mas * years / 3.6e6
    ra2 = ra + pmra_mas * years / 3.6e6 / max(math.cos(math.radians(dec)), 1e-6)
    return ra2, dec2


# ---------------------------------------------------------------- loading
def sha256_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hnum(header, key):
    value = header.get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def load_tpf(path: str | Path) -> TargetPixels:
    """Read a SPOC target pixel file (PIXELS table, APERTURE image). Cadences with non-finite times are dropped;
    the quality flags are kept, so callers choose what to mask (in- and out-of-transit images use quality 0)."""
    from astropy.io import fits
    from astropy.wcs import WCS

    path = Path(path)
    with fits.open(path) as hdul:
        primary = hdul[0].header
        table = hdul[1].data
        h1 = hdul[1].header
        aperture_hdu = hdul[2] if len(hdul) > 2 else None
        time = np.asarray(table["TIME"], float)
        keep = np.isfinite(time)
        flux = np.asarray(table["FLUX"], float)[keep]
        flux_err = np.asarray(table["FLUX_ERR"], float)[keep]
        quality = np.asarray(table["QUALITY"], int)[keep]
        if aperture_hdu is not None:
            amask = np.asarray(aperture_hdu.data, int)
            aperture = (amask & 2) > 0
            wcs = WCS(aperture_hdu.header)
            ah = aperture_hdu.header
        else:
            aperture = np.zeros(flux.shape[1:], bool)
            wcs, ah = None, {}
        tstart = _hnum(h1, "TSTART")
        header = {
            "tic": int(primary["TICID"]) if primary.get("TICID") is not None else None,
            "sector": primary.get("SECTOR"), "camera": primary.get("CAMERA"), "ccd": primary.get("CCD"),
            "tessmag": _hnum(primary, "TESSMAG"), "teff": _hnum(primary, "TEFF"),
            "ra": _hnum(primary, "RA_OBJ"), "dec": _hnum(primary, "DEC_OBJ"),
            "pmra": _hnum(primary, "PMRA"), "pmdec": _hnum(primary, "PMDEC"),
            # SPOC's aperture extension carries the position propagated to the observation epoch
            "ra_epoch": _hnum(ah, "RA_OBJ"), "dec_epoch": _hnum(ah, "DEC_OBJ"),
            "crowdsap": _hnum(h1, "CROWDSAP"), "flfrcsap": _hnum(h1, "FLFRCSAP"),
            "col0": h1.get("1CRV4P"), "row0": h1.get("2CRV4P"), "tstart": tstart,
            # BTJD 0 is BJD 2457000.0 = 2014-12-08.5; J2000 is JD 2451545.0
            "years_since_2000": ((tstart + 2457000.0 - 2451545.0) / 365.25) if tstart is not None else None,
        }
    return TargetPixels(time=time[keep], flux=flux, flux_err=flux_err, quality=quality, aperture=aperture, wcs=wcs,
                        header=header, provenance={"file": path.name, "file_sha256": sha256_bytes(path)})


def s3_prefix(tic: int, sector: int) -> str:
    """The public bucket's folder for one TIC and sector, as MAST's download links resolve it."""
    t = f"{int(tic):016d}"
    return f"tess/public/tid/s{int(sector):04d}/{t[0:4]}/{t[4:8]}/{t[8:12]}/{t[12:16]}/"


def _s3_list(prefix: str, timeout: float = 60.0) -> list[str]:
    url = f"{S3_BUCKET}/?list-type=2&prefix={prefix}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (fixed https host)
        text = response.read().decode()
    return re.findall(r"<Key>([^<]+)</Key>", text)


def _s3_get(key: str, dest: Path, timeout: float = 600.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(f"{S3_BUCKET}/{key}", timeout=timeout) as response, open(tmp, "wb") as out:  # noqa: S310
        for chunk in iter(lambda: response.read(1 << 20), b""):
            out.write(chunk)
    tmp.replace(dest)
    return dest


def fetch_spoc_product(tic: int, sector: int, suffix: str, cache_dir: str | Path = "cache/tpf") -> Path:
    """A SPOC 2-minute product for one TIC and sector (``suffix`` "tp.fits", "lc.fits" or "dvr.xml"), cached.

    Looks in ``cache_dir`` first. Then asks MAST through lightkurve (TPF and light curve only); when that fails (the
    MAST search API was returning errors on 2026-10-19), lists the public STScI bucket folder that MAST's download
    links redirect to and fetches the file from there. Raises LookupError when no such product exists.
    """
    cache = Path(cache_dir)
    pattern = f"*s{int(sector):04d}*{int(tic):016d}*{suffix}"
    found = sorted(cache.glob(pattern)) if cache.exists() else []
    if found:
        return found[-1]
    errors = []
    if suffix in ("tp.fits", "lc.fits"):
        try:
            import lightkurve as lk

            search = (lk.search_targetpixelfile if suffix == "tp.fits" else lk.search_lightcurve)(
                f"TIC {tic}", author="SPOC", exptime=120, sector=int(sector))
            if len(search):
                product = search[0].download(download_dir=str(cache / "lightkurve"))
                path = Path(product.path if hasattr(product, "path") else product.meta["FILENAME"])
                dest = cache / path.name
                dest.write_bytes(path.read_bytes())
                return dest
        except Exception as exc:  # noqa: BLE001 (fall through to the bucket)
            errors.append(f"lightkurve: {type(exc).__name__}: {exc}")
    try:
        listed = _s3_list(s3_prefix(tic, sector))
        # 2-minute TPFs and light curves carry "-0120-" in the name; DV reports do not
        keys = [k for k in listed if k.endswith(suffix) and ("-0120-" in k or suffix == "dvr.xml")]
    except Exception as exc:  # noqa: BLE001
        raise LookupError(f"TIC {tic} sector {sector} {suffix}: MAST and the public bucket failed: {errors} {exc}") from exc
    if not keys:
        raise LookupError(f"TIC {tic} sector {sector}: no SPOC 2-minute {suffix} ({'; '.join(errors) or 'none listed'})")
    key = sorted(keys)[-1]
    return _s3_get(key, cache / Path(key).name)


def fetch_tpf(tic: int, sector: int, cache_dir: str | Path = "cache/tpf") -> TargetPixels:
    return load_tpf(fetch_spoc_product(tic, sector, "tp.fits", cache_dir))


# ---------------------------------------------------------------- images
def transit_windows(time, *, period: float, t0: float, duration: float, in_fraction: float = 0.75,
                    gap: float = 0.75, width: float = 1.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Epoch number, in-transit mask and out-of-transit mask for every cadence.

    In transit: within ``in_fraction`` × T14/2 of mid-transit (the central part, clear of ingress and egress).
    Out of transit: from ``gap`` × T14 to (``gap`` + ``width``) × T14 from mid-transit, on both sides.
    """
    time = np.asarray(time, float)
    epoch = np.round((time - t0) / period).astype(int)
    dt = np.abs(time - (t0 + epoch * period))
    inside = dt <= 0.5 * in_fraction * duration
    outside = (dt >= gap * duration) & (dt <= (gap + width) * duration)
    return epoch, inside, outside


@dataclass
class DifferenceImage:
    diff: np.ndarray          # out-of-transit minus in-transit, mean over transits
    diff_err: np.ndarray
    oot: np.ndarray           # mean out-of-transit image
    oot_err: np.ndarray
    n_transits: int
    n_in: int
    n_out: int
    error_scale: float        # factor applied to the formal errors from the scatter between transits
    epochs: list = field(default_factory=list)


def difference_image(tpf: TargetPixels, *, period: float, t0: float, duration: float, min_cadences: int = 5,
                     **windows) -> DifferenceImage | None:
    """Mean out-of-transit minus in-transit image over every transit with enough good cadences (quality 0) on both
    sides. Per-pixel errors propagate FLUX_ERR; with three or more transits they are scaled up by the scatter of
    the per-transit difference images about their mean (the median over pixels of χ²/(K − 1), when above 1)."""
    good = (tpf.quality == 0) & np.all(np.isfinite(tpf.flux), axis=(1, 2))
    epoch, inside, outside = transit_windows(tpf.time, period=period, t0=t0, duration=duration, **windows)
    diffs, errs, oots, oot_errs, used = [], [], [], [], []
    n_in = n_out = 0
    for k in np.unique(epoch[good & inside]):
        ii = good & inside & (epoch == k)
        oo = good & outside & (epoch == k)
        times = tpf.time[oo]
        mid = t0 + k * period
        if ii.sum() < min_cadences or (times < mid).sum() < min_cadences or (times > mid).sum() < min_cadences:
            continue
        fin, fout = tpf.flux[ii].mean(axis=0), tpf.flux[oo].mean(axis=0)
        ein = np.sqrt(np.sum(tpf.flux_err[ii] ** 2, axis=0)) / ii.sum()
        eout = np.sqrt(np.sum(tpf.flux_err[oo] ** 2, axis=0)) / oo.sum()
        diffs.append(fout - fin)
        errs.append(np.hypot(ein, eout))
        oots.append(fout)
        oot_errs.append(eout)
        used.append(int(k))
        n_in += int(ii.sum())
        n_out += int(oo.sum())
    if not diffs:
        return None
    d, e = np.array(diffs), np.array(errs)
    k = len(diffs)
    diff = d.mean(axis=0)
    diff_err = np.sqrt(np.sum(e ** 2, axis=0)) / k
    scale = 1.0
    if k >= 3:
        chi = np.sum((d - diff) ** 2 / np.where(e > 0, e ** 2, np.inf), axis=0) / (k - 1)
        scale = float(max(1.0, math.sqrt(np.nanmedian(chi))))
    oot = np.array(oots).mean(axis=0)
    oot_err = np.sqrt(np.sum(np.array(oot_errs) ** 2, axis=0)) / k
    return DifferenceImage(diff=diff, diff_err=diff_err * scale, oot=oot, oot_err=oot_err * scale, n_transits=k,
                           n_in=n_in, n_out=n_out, error_scale=scale, epochs=used)


def flux_weighted_centroid(image, err, mask) -> tuple[float, float, np.ndarray] | None:
    """(column, row) centroid of ``image`` inside ``mask`` and its 2×2 covariance, by linear error propagation:
    ∂x_c/∂I_i = (x_i − x_c)/ΣI, so var(x_c) = Σ (x_i − x_c)² σ_i² / (ΣI)². None when the masked flux is not
    positive."""
    image = np.asarray(image, float)
    mask = np.asarray(mask, bool) & np.isfinite(image)
    rows, cols = np.nonzero(mask)
    values = image[rows, cols]
    total = values.sum()
    if not np.isfinite(total) or total <= 0:
        return None
    xc = float((cols * values).sum() / total)
    yc = float((rows * values).sum() / total)
    sig = np.asarray(err, float)[rows, cols]
    dx, dy = (cols - xc) / total, (rows - yc) / total
    cov = np.array([[np.sum(dx * dx * sig ** 2), np.sum(dx * dy * sig ** 2)],
                    [np.sum(dx * dy * sig ** 2), np.sum(dy * dy * sig ** 2)]])
    return xc, yc, cov


def gaussian_psf(shape, x0: float, y0: float, sigma: float, sigma_y: float | None = None) -> np.ndarray:
    """A unit-flux Gaussian integrated over each pixel (pixel (i, j) covers [j − ½, j + ½] in column); circular unless
    ``sigma_y`` (the row-direction width) is given, which the synthetic data use to model an elongated PSF."""
    ny, nx = shape
    sx = math.sqrt(2.0) * sigma
    sy = math.sqrt(2.0) * (sigma if sigma_y is None else sigma_y)
    ex = 0.5 * (erf((np.arange(nx) + 0.5 - x0) / sx) - erf((np.arange(nx) - 0.5 - x0) / sx))
    ey = 0.5 * (erf((np.arange(ny) + 0.5 - y0) / sy) - erf((np.arange(ny) - 0.5 - y0) / sy))
    return np.outer(ey, ex)


@dataclass
class PsfFit:
    x: float
    y: float
    cov: np.ndarray
    flux: float
    sigma: float
    background: float
    chi2_red: float
    quality: float           # correlation between the data and the model over the fitted pixels (DV-like)
    n_pixels: int


def fit_psf(image, err, mask, *, x0: float | None = None, y0: float | None = None, sigma0: float = 1.0) -> PsfFit | None:
    """Least-squares fit of a pixel-integrated circular Gaussian plus a constant to ``image`` inside ``mask``.
    The position covariance comes from the Jacobian, scaled by χ²ᵣ when above 1."""
    image = np.asarray(image, float)
    err = np.asarray(err, float)
    mask = np.asarray(mask, bool) & np.isfinite(image) & np.isfinite(err) & (err > 0)
    if mask.sum() < 6:
        return None
    if x0 is None or y0 is None:
        r, c = np.unravel_index(np.nanargmax(np.where(mask, image, -np.inf)), image.shape)
        x0, y0 = float(c), float(r)
    amp0 = float(np.nansum(np.where(mask, image, 0.0)))
    if amp0 <= 0:
        amp0 = float(np.nanmax(np.where(mask, image, 0.0))) or 1.0
    ny, nx = image.shape

    def resid(p):
        x, y, s, a, b = p
        return ((a * gaussian_psf(image.shape, x, y, s) + b - image) / err)[mask]

    lo = [-0.5, -0.5, PSF_SIGMA_BOUNDS[0], 0.0, -np.inf]
    hi = [nx - 0.5, ny - 0.5, PSF_SIGMA_BOUNDS[1], np.inf, np.inf]
    start = [min(max(x0, lo[0] + 1e-3), hi[0] - 1e-3), min(max(y0, lo[1] + 1e-3), hi[1] - 1e-3), sigma0, amp0, 0.0]
    try:
        res = least_squares(resid, start, bounds=(lo, hi), x_scale="jac")
    except (ValueError, np.linalg.LinAlgError):
        return None
    dof = max(int(mask.sum()) - 5, 1)
    chi2_red = float(np.sum(res.fun ** 2) / dof)
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * max(1.0, chi2_red)
    except np.linalg.LinAlgError:
        return None
    x, y, s, a, b = res.x
    model = (a * gaussian_psf(image.shape, x, y, s) + b)[mask]
    data = image[mask]
    quality = float(np.corrcoef(data, model)[0, 1]) if np.std(data) > 0 and np.std(model) > 0 else 0.0
    return PsfFit(x=float(x), y=float(y), cov=cov[:2, :2], flux=float(a), sigma=float(s), background=float(b),
                  chi2_red=chi2_red, quality=quality, n_pixels=int(mask.sum()))


def offset_significance(dx: float, dy: float, cov: np.ndarray) -> dict:
    """2-D offset significance: χ²₂ = Δᵀ C⁻¹ Δ, p = exp(−χ²₂/2), and the Gaussian-equivalent σ (two-sided)."""
    try:
        chi = float(np.array([dx, dy]) @ np.linalg.solve(cov, np.array([dx, dy])))
    except np.linalg.LinAlgError:
        return {"chi2": None, "p_value": None, "sigma": None}
    p = float(chi2_dist.sf(chi, 2))
    sigma = float(norm.isf(p / 2.0)) if p > 0 else float("inf")
    return {"chi2": chi, "p_value": p, "sigma": sigma}


def detect_saturation(image, *, plateau: float = SATURATION_PLATEAU, min_run: int = 3) -> dict:
    """A saturated star bleeds charge along its column, which flattens the brightest column into a plateau. Flags
    saturation when ``min_run`` or more contiguous pixels in one column are within (1 − ``plateau``) of the
    brightest pixel. An unsaturated PSF never puts three pixels in a row that close to its peak."""
    image = np.asarray(image, float)
    peak = np.nanmax(image)
    if not np.isfinite(peak) or peak <= 0:
        return {"saturated": False, "plateau_pixels": 0, "column": None}
    high = image >= plateau * peak
    best, best_col = 0, None
    for col in range(image.shape[1]):
        run = longest = 0
        for v in high[:, col]:
            run = run + 1 if v else 0
            longest = max(longest, run)
        if longest > best:
            best, best_col = longest, col
    return {"saturated": bool(best >= min_run), "plateau_pixels": int(best), "column": best_col}


def dilate(mask, n: int = 1) -> np.ndarray:
    """Grow a boolean mask by ``n`` pixels (8-connected)."""
    out = np.asarray(mask, bool).copy()
    for _ in range(n):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        grown[1:, 1:] |= out[:-1, :-1]
        grown[:-1, :-1] |= out[1:, 1:]
        grown[1:, :-1] |= out[:-1, 1:]
        grown[:-1, 1:] |= out[1:, :-1]
        out = grown
    return out


def centroid_test(tpf: TargetPixels, *, period: float, t0: float, duration: float,
                  sigma_threshold: float = CENTROID_SIGMA, quality_min: float = QUALITY_MIN) -> dict:
    """Difference-image centroids and their offsets (see the module docstring). Returns a JSON-ready dict with
    ``flags`` (``centroid_offset``, ``centroid_unreliable``, ``saturated``) and the numbers behind them."""
    out: dict = {"flags": []}
    di = difference_image(tpf, period=period, t0=t0, duration=duration)
    if di is None:
        out["error"] = "no transit with enough good in- and out-of-transit cadences"
        return out
    scale = tpf.pixel_scale_arcsec()
    aperture = tpf.aperture if tpf.aperture.any() else (di.oot >= 0.05 * np.nanmax(di.oot))
    region = dilate(aperture, 1)
    sat = detect_saturation(di.oot)
    out.update(n_transits=di.n_transits, transits=di.epochs, n_in=di.n_in, n_out=di.n_out,
               error_scale=di.error_scale, pixel_scale_arcsec=scale, saturation=sat,
               depth_in_aperture=float(np.nansum(di.diff[aperture]) / np.nansum(di.oot[aperture])))
    target = tpf.target_position()
    out["target_pixel"] = list(target) if target else None

    fw_diff = flux_weighted_centroid(di.diff, di.diff_err, aperture)
    fw_oot = flux_weighted_centroid(di.oot, di.oot_err, aperture)
    if fw_diff and fw_oot:
        dx, dy = fw_diff[0] - fw_oot[0], fw_diff[1] - fw_oot[1]
        out["flux_weighted"] = {"diff": [fw_diff[0], fw_diff[1]], "oot": [fw_oot[0], fw_oot[1]],
                                "offset_px": [dx, dy], "offset_arcsec": math.hypot(dx, dy) * scale,
                                **offset_significance(dx, dy, fw_diff[2] + fw_oot[2])}
    p_diff = fit_psf(di.diff, di.diff_err, region)
    p_oot = fit_psf(di.oot, di.oot_err, region)
    if p_diff and p_oot:
        dx, dy = p_diff.x - p_oot.x, p_diff.y - p_oot.y
        control = {"diff": [p_diff.x, p_diff.y], "diff_err": [math.sqrt(p_diff.cov[0, 0]), math.sqrt(p_diff.cov[1, 1])],
                   "oot": [p_oot.x, p_oot.y], "offset_px": [dx, dy], "offset_total_px": math.hypot(dx, dy),
                   "offset_arcsec": math.hypot(dx, dy) * scale, "quality": p_diff.quality,
                   "psf_sigma_px": p_diff.sigma, "chi2_red": p_diff.chi2_red,
                   **offset_significance(dx, dy, p_diff.cov + p_oot.cov)}
        out["psf_control"] = control
        test = control
        out["diff_cov"] = p_diff.cov.tolist()
        if target:
            tx, ty = p_diff.x - target[0], p_diff.y - target[1]
            # Systematic floor: how far the out-of-transit PSF centroid sits from the catalogue position. It absorbs
            # WCS error and the pull of unmodelled neighbours on the single-Gaussian fit (conservative).
            floor = math.hypot(p_oot.x - target[0], p_oot.y - target[1])
            cov = p_diff.cov + np.eye(2) * floor ** 2
            out["psf_target"] = test = {"offset_px": [tx, ty], "offset_total_px": math.hypot(tx, ty),
                                        "offset_arcsec": math.hypot(tx, ty) * scale, "systematic_floor_px": floor,
                                        **offset_significance(tx, ty, cov)}
            out["diff_cov"] = cov.tolist()
        out["flag_reference"] = "catalogue position" if target else "out-of-transit centroid"
        at_bound = p_diff.sigma <= PSF_SIGMA_BOUNDS[0] * 1.001
        ratio = max(p_diff.sigma, p_oot.sigma) / max(min(p_diff.sigma, p_oot.sigma), 1e-9)
        out["psf_sigma_ratio"] = ratio
        reasons = []
        if sat["saturated"]:
            reasons.append(f"saturated: a {sat['plateau_pixels']}-pixel plateau in column {sat['column']}")
        if p_diff.quality < quality_min:
            reasons.append(f"difference-image fit quality {p_diff.quality:.2f} < {quality_min}")
        if at_bound:
            reasons.append(f"difference-image PSF width at its {PSF_SIGMA_BOUNDS[0]} px bound")
        if ratio > PSF_SIGMA_RATIO_MAX:
            reasons.append(f"difference and out-of-transit PSF widths differ by {ratio:.1f}x (> {PSF_SIGMA_RATIO_MAX:g}x)")
        reliable = not reasons
        out["reliable"] = bool(reliable)
        out["unreliable_reasons"] = reasons
        if sat["saturated"]:
            out["flags"].append("saturated")
        if not reliable:
            out["flags"].append("centroid_unreliable")
        elif test["sigma"] is not None and test["sigma"] >= sigma_threshold:
            out["flags"].append("centroid_offset")
    else:
        out["error"] = "the PSF fit to the difference or out-of-transit image failed"
        out["reliable"] = False
        out["flags"].append("centroid_unreliable")
    return out


def centroid_motion_test(tpf: TargetPixels, *, period: float, t0: float, duration: float) -> dict:
    """DV centroid motion test: per-cadence flux-weighted centroids inside the aperture; the in-transit minus
    out-of-transit mean shift δφ per axis with its error (the out-of-transit scatter over √n, or the scatter between
    transits when that is larger), χ²₂ = Σ (δ/σ)², p, and the source offset Δφ = −δφ(1 − D)/D (ATLAS E5), with D
    the fractional depth of the summed aperture flux (the same pixels as the centroid). The aperture truncates the
    source's PSF, so Δφ underestimates the distance to a source near or beyond the aperture's edge."""
    good = (tpf.quality == 0) & np.all(np.isfinite(tpf.flux), axis=(1, 2))
    aperture = tpf.aperture if tpf.aperture.any() else np.ones(tpf.shape, bool)
    rows, cols = np.nonzero(aperture)
    f = tpf.flux[:, rows, cols]
    total = f.sum(axis=1)
    cx = (f * cols).sum(axis=1) / total
    cy = (f * rows).sum(axis=1) / total
    epoch, inside, outside = transit_windows(tpf.time, period=period, t0=t0, duration=duration)
    ii, oo = good & inside, good & outside
    if ii.sum() < 3 or oo.sum() < 10:
        return {"error": "too few cadences"}
    depth = float(1.0 - total[ii].mean() / total[oo].mean())
    shifts, errs = [], []
    for c in (cx, cy):
        delta = float(c[ii].mean() - c[oo].mean())
        white = float(np.std(c[oo], ddof=1) * math.sqrt(1 / ii.sum() + 1 / oo.sum()))
        per = [c[ii & (epoch == k)].mean() - c[oo & (epoch == k)].mean() for k in np.unique(epoch[ii])
               if (ii & (epoch == k)).sum() and (oo & (epoch == k)).sum()]
        spread = float(np.std(per, ddof=1) / math.sqrt(len(per))) if len(per) >= 3 else 0.0
        shifts.append(delta)
        errs.append(max(white, spread))
    chi = sum((d / e) ** 2 for d, e in zip(shifts, errs) if e > 0)
    p = float(chi2_dist.sf(chi, 2))
    source = [(-d * (1 - depth) / depth) if depth > 0 else None for d in shifts]
    scale = tpf.pixel_scale_arcsec()
    return {"shift_px": shifts, "shift_err_px": errs, "chi2": float(chi), "p_value": p,
            "sigma": float(norm.isf(p / 2)) if p > 0 else float("inf"), "depth": depth,
            "source_offset_px": source,
            "source_offset_arcsec": (math.hypot(*source) * scale) if None not in source else None}


def _detection_statistic(series, inside, outside) -> float:
    """Matched-filter statistic of a box dip: mean drop in transit over its error, from the out-of-transit scatter."""
    norm_series = series / np.median(series[outside])
    sigma = float(np.std(norm_series[outside], ddof=1))
    if sigma <= 0 or inside.sum() == 0:
        return 0.0
    return float((1.0 - norm_series[inside].mean()) / (sigma / math.sqrt(inside.sum())))


def ghost_test(tpf: TargetPixels, *, period: float, t0: float, duration: float) -> dict:
    """DV optical ghost diagnostic: the transit's detection statistic in the aperture (core) and in a ring of
    pixels 1 to 2 pixels outside it (halo). ``ghost_suspect`` when the halo's is above 3 and above the core's: the
    dip is stronger outside the aperture than in it, which a ghost or scattered light does, and so does an eclipse
    on a star in the halo ring. Either way the source is not the target."""
    good = (tpf.quality == 0) & np.all(np.isfinite(tpf.flux), axis=(1, 2))
    aperture = tpf.aperture if tpf.aperture.any() else np.ones(tpf.shape, bool)
    halo = dilate(aperture, 2) & ~aperture
    if not halo.any():
        return {"core": None, "halo": None, "ghost_suspect": False}
    _, inside, outside = transit_windows(tpf.time, period=period, t0=t0, duration=duration)
    core_series = tpf.flux[good][:, aperture].sum(axis=1)
    halo_series = tpf.flux[good][:, halo].sum(axis=1)
    core = _detection_statistic(core_series, inside[good], outside[good])
    halo_stat = _detection_statistic(halo_series, inside[good], outside[good])
    return {"core": core, "halo": halo_stat, "n_halo_pixels": int(halo.sum()),
            "ghost_suspect": bool(halo_stat > 3.0 and halo_stat > core)}


def momentum_dumps(tpf: TargetPixels, *, period: float, t0: float, duration: float) -> dict:
    """Transit epochs whose mid-time lies within half a duration (plus one cadence) of a momentum dump."""
    dumps = tpf.time[(tpf.quality & MOMENTUM_DUMP_BIT) > 0]
    cadence = float(np.median(np.diff(tpf.time))) if tpf.time.size > 1 else 0.0
    hits = []
    for k in range(int(np.ceil((tpf.time.min() - t0) / period)), int(np.floor((tpf.time.max() - t0) / period)) + 1):
        mid = t0 + k * period
        near = dumps[np.abs(dumps - mid) <= 0.5 * duration + cadence]
        if near.size:
            hits.append({"epoch": k, "t_mid": float(mid), "dump_times": [float(x) for x in near]})
    return {"n_dumps": int(dumps.size), "epochs_with_dump": hits}


# ---------------------------------------------------------------- neighbours
def aperture_fraction(shape, aperture, x: float, y: float, psf_sigma: float) -> float:
    """Share of a star's flux that falls in the aperture pixels, for a Gaussian PSF at (x, y)."""
    return float(gaussian_psf(shape, x, y, psf_sigma)[np.asarray(aperture, bool)].sum())


def neighbour_table(tpf: TargetPixels, stars: list[dict], *, depth: float, crowdsap: float | None = None,
                    psf_sigma: float = 1.0, centroid: tuple[float, float, np.ndarray] | None = None,
                    centroid_reliable: bool = False, sigma_threshold: float = CENTROID_SIGMA) -> dict:
    """Which catalogued stars could produce the observed depth.

    ``stars`` are dicts with ``id``, ``ra``, ``dec`` and ``tmag`` (or ``x``/``y`` pixel positions), the target
    first. ``depth`` is the fractional depth in PDCSAP flux; PDCSAP is crowding-corrected, so the depth in the raw
    aperture is depth × CROWDSAP when CROWDSAP is known. For star i the needed eclipse depth is
    δ_i = δ_aperture × F_aperture / F_i,aperture, where F_i,aperture is its flux times its aperture fraction and
    F_aperture sums over all stars. A star is ruled out when δ_i > 1, or, when the difference-image centroid
    ``centroid`` (x, y, covariance) is reliable, when it lies more than ``sigma_threshold`` from the star.
    """
    shape = tpf.shape
    aperture = tpf.aperture if tpf.aperture.any() else np.ones(shape, bool)
    rows = []
    for s in stars:
        if "x" in s and "y" in s:
            x, y = float(s["x"]), float(s["y"])
        else:
            pos = tpf.world_to_pixel(s["ra"], s["dec"])
            if pos is None:
                continue
            x, y = pos
        flux = 10 ** (-0.4 * float(s["tmag"]))
        frac = aperture_fraction(shape, aperture, x, y, psf_sigma)
        err = _float(s.get("tmag_err"))
        rows.append({"id": s.get("id"), "tmag": float(s["tmag"]), "x": x, "y": y, "flux": flux,
                     "tmag_err": err if err else TMAG_ERR_DEFAULT, "tmag_err_assumed": not err,
                     "aperture_fraction": frac, "source": s.get("source")})
    if not rows:
        return {"stars": [], "delta_mag_limit": None}
    total = sum(r["flux"] * r["aperture_fraction"] for r in rows)
    depth_ap = depth * crowdsap if crowdsap else depth
    scale = tpf.pixel_scale_arcsec()
    t = rows[0]
    for r in rows:
        share = r["flux"] * r["aperture_fraction"] / total if total > 0 else 0.0
        r["flux_share"] = share
        r["needed_depth"] = depth_ap / share if share > 0 else float("inf")
        r["separation_arcsec"] = math.hypot(r["x"] - t["x"], r["y"] - t["y"]) * scale
        r["delta_mag"] = r["tmag"] - t["tmag"]
        reasons = []
        if r["needed_depth"] > 1.0:
            # marginal when brightening the star by 3σ of its catalogue magnitude would let it reach the depth
            r["marginal"] = bool(r["needed_depth"] * 10 ** (-0.4 * 3.0 * r["tmag_err"]) <= 1.0)
            reasons.append("needs a depth above 100%" + (
                f" (marginal: within 3σ of its Tmag uncertainty, ±{r['tmag_err']:.2f} mag"
                + (", assumed" if r["tmag_err_assumed"] else "") + ")" if r["marginal"] else ""))
        if centroid is not None and centroid_reliable:
            sig = offset_significance(centroid[0] - r["x"], centroid[1] - r["y"], centroid[2])
            r["centroid_sigma"] = sig["sigma"]
            if sig["sigma"] is not None and sig["sigma"] > sigma_threshold:
                reasons.append(f"difference-image centroid {sig['sigma']:.1f}σ away")
        r["ruled_out"] = bool(reasons)
        r["ruled_out_by"] = reasons
        r.pop("flux")
    return {"stars": rows, "depth_aperture": depth_ap, "psf_sigma_px": psf_sigma,
            "delta_mag_limit": -2.5 * math.log10(depth_ap) if depth_ap > 0 else None,
            "n_possible_sources": sum(not r["ruled_out"] for r in rows)}


def fetch_neighbours(ra: float, dec: float, *, radius_arcsec: float = 150.0, cache_dir: str | Path = "cache/neighbours",
                     epoch_years_since_2000: float | None = None, key: str | None = None) -> dict:
    """Catalogued stars within ``radius_arcsec``: the TIC through MAST, or Gaia DR3 through the ESA archive when MAST
    fails (then Gaia G stands in for the TESS magnitude, colour terms ignored, and the source says so). Positions are
    moved to the observation epoch with their proper motions (TIC: J2000; Gaia DR3: J2016.0). Cached as JSON."""
    path = Path(cache_dir) / f"{key or f'{ra:.5f}_{dec:.5f}'}_{int(radius_arcsec)}.json"
    if path.exists():
        return json.loads(path.read_text())
    errors, stars, source = [], [], None
    try:
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        from astroquery.mast import Catalogs

        table = Catalogs.query_region(SkyCoord(ra, dec, unit="deg"), radius=radius_arcsec * u.arcsec, catalog="TIC")
        for row in table:
            r, d = propagate_position(float(row["ra"]), float(row["dec"]), _float(row["pmRA"]), _float(row["pmDEC"]),
                                      years=epoch_years_since_2000)
            stars.append({"id": f"TIC {row['ID']}", "ra": r, "dec": d, "tmag": float(row["Tmag"]),
                          "tmag_err": _float(row["e_Tmag"]) if "e_Tmag" in table.colnames else None, "source": "TIC"})
        source = "TIC v8.2 (MAST)"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"TIC: {type(exc).__name__}: {str(exc)[:200]}")
        try:
            from astroquery.gaia import Gaia

            query = ("SELECT source_id, ra, dec, pmra, pmdec, phot_g_mean_mag FROM gaiadr3.gaia_source WHERE "
                     f"1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius_arcsec / 3600.0}))")
            table = Gaia.launch_job(query).get_results()
            years = None if epoch_years_since_2000 is None else epoch_years_since_2000 - 16.0
            for row in table:
                if not np.isfinite(_float(row["phot_g_mean_mag"]) or np.nan):
                    continue
                r, d = propagate_position(float(row["ra"]), float(row["dec"]), _float(row["pmra"]), _float(row["pmdec"]),
                                          years=years)
                stars.append({"id": f"Gaia DR3 {row['source_id']}", "ra": r, "dec": d,
                              "tmag": float(row["phot_g_mean_mag"]), "source": "Gaia DR3 (G as a proxy for T)"})
            source = "Gaia DR3 (ESA); G magnitude used as a proxy for the TESS magnitude"
        except Exception as exc2:  # noqa: BLE001
            errors.append(f"Gaia: {type(exc2).__name__}: {str(exc2)[:200]}")
    result = {"source": source, "stars": stars, "errors": errors, "radius_arcsec": radius_arcsec}
    if stars:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=1))
    return result


def _float(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def order_target_first(stars: list[dict], ra: float, dec: float) -> list[dict]:
    """The catalogue star nearest (ra, dec) first, then the rest by brightness."""
    if not stars:
        return []
    cosd = math.cos(math.radians(dec))
    dist = [math.hypot((s["ra"] - ra) * cosd, s["dec"] - dec) for s in stars]
    i = int(np.argmin(dist))
    return [stars[i]] + sorted((s for j, s in enumerate(stars) if j != i), key=lambda s: s["tmag"])


# ---------------------------------------------------------------- all together
def pixel_vet(tpf: TargetPixels, *, period: float, t0: float, duration: float, depth: float,
              stars: list[dict] | None = None, sigma_threshold: float = CENTROID_SIGMA,
              quality_min: float = QUALITY_MIN, psf_sigma: float = 1.0) -> dict:
    """Every pixel-level test for one transit signal. ``depth`` is fractional (PDCSAP). Returns a JSON-ready dict
    with ``flags``; the flags only inform unless the run config's ``[vetting] decide`` is set."""
    report = {"tpf": tpf.provenance, "header": {k: v for k, v in tpf.header.items()},
              "ephemeris": {"period": period, "t0": t0, "duration_days": duration, "depth": depth}}
    cent = centroid_test(tpf, period=period, t0=t0, duration=duration, sigma_threshold=sigma_threshold,
                         quality_min=quality_min)
    report["centroid"] = cent
    report["motion"] = centroid_motion_test(tpf, period=period, t0=t0, duration=duration)
    report["ghost"] = ghost_test(tpf, period=period, t0=t0, duration=duration)
    report["momentum_dumps"] = momentum_dumps(tpf, period=period, t0=t0, duration=duration)
    flags = list(cent.get("flags", []))
    if report["ghost"]["ghost_suspect"]:
        flags.append("ghost_suspect")
    if report["momentum_dumps"]["epochs_with_dump"]:
        flags.append("momentum_dump")
    if stars:
        centroid = None
        if "psf_control" in cent:
            centroid = (cent["psf_control"]["diff"][0], cent["psf_control"]["diff"][1], np.array(cent["diff_cov"]))
        report["neighbours"] = neighbour_table(tpf, stars, depth=depth, crowdsap=tpf.header.get("crowdsap"),
                                               psf_sigma=psf_sigma, centroid=centroid,
                                               centroid_reliable=bool(cent.get("reliable")),
                                               sigma_threshold=sigma_threshold)
    report["flags"] = flags
    return report


# ---------------------------------------------------------------- DV report (SPOC's own numbers, for comparison)
def parse_dv_xml(path: str | Path) -> list[dict]:
    """SPOC's difference-image centroid offsets and binary-discrimination statistics from a DV XML report, per
    planet candidate. Element names as found in SPOC DV XML files of 2018 and later (namespace
    http://www.nasa.gov/2018/TESS/DV)."""
    import xml.etree.ElementTree as ET

    ns = {"dv": "http://www.nasa.gov/2018/TESS/DV"}
    root = ET.parse(path).getroot()

    def val(node, tag):
        el = node.find(tag, ns) if node is not None else None
        if el is None:
            return None
        return {"value": _float(el.get("value")), "uncertainty": _float(el.get("uncertainty"))}

    out = []
    for planet in root.findall("dv:planetResults", ns):
        row = {"planet": planet.get("planetNumber"), "toi": planet.get("toiId")}
        dir_ = planet.find("dv:differenceImageResults", ns)
        if dir_ is not None:
            q = dir_.find("dv:qualityMetric", ns)
            row["sector"] = dir_.get("sector")
            row["n_transits"] = dir_.get("numberOfTransits")
            row["quality"] = _float(q.get("value")) if q is not None else None
            for name in ("ticCentroidOffsets", "controlCentroidOffsets"):
                node = dir_.find(f"dv:{name}", ns)
                row[name] = {k: val(node, f"dv:{k}") for k in ("rowOffset", "columnOffset", "skyOffset")}
        bd = planet.find("dv:binaryDiscriminationResults", ns)
        if bd is not None:
            node = bd.find("dv:oddEvenTransitDepthComparisonStatistic", ns)
            row["odd_even"] = {"value": _float(node.get("value")), "significance": _float(node.get("significance"))} if node is not None else None
        out.append(row)
    return out


# ---------------------------------------------------------------- synthetic data for tests
def synthetic_tpf(*, stars: list[dict], shape: tuple[int, int] = (11, 11), psf_sigma: float = 1.0,
                  psf_sigma_y: float | None = None,
                  days: float = 13.0, cadence_minutes: float = 2.0, period: float = 3.0, t0: float = 1.5,
                  duration: float = 0.125, background: float = 50.0, exptime_s: float = 120.0,
                  read_noise: float = 30.0, seed: int = 0, aperture_threshold: float = 0.05,
                  saturate_at: float | None = None, dumps: tuple = (), halo_dim: float = 0.0,
                  pixel_scale_arcsec: float = TESS_PIXEL_ARCSEC, ra: float = 100.0, dec: float = -30.0) -> TargetPixels:
    """Synthetic target pixel file. ``stars`` are dicts with ``x``, ``y`` (column, row), ``flux`` (e⁻/s) and an
    optional box ``eclipse`` depth (fractional) at the given ephemeris; the first star is the target. Noise is
    photon plus read noise per 2-minute cadence. ``saturate_at`` clips pixels and spreads the excess along the
    column (a crude bleed trail); ``halo_dim`` dims the pixels outside the aperture in transit (a ghost).
    The aperture is every pixel where the target's model image exceeds ``aperture_threshold`` of its peak.
    """
    from astropy.wcs import WCS

    rng = np.random.default_rng(seed)
    time = np.arange(0.0, days, cadence_minutes / 1440.0) + 1000.0
    phase = np.abs(((time - t0 + 0.5 * period) % period) - 0.5 * period)
    in_transit = phase <= 0.5 * duration
    cube = np.full((time.size,) + tuple(shape), background, float)
    images = [gaussian_psf(shape, s["x"], s["y"], psf_sigma, psf_sigma_y) * s["flux"] for s in stars]
    for s, img in zip(stars, images):
        series = np.ones(time.size)
        series[in_transit] -= s.get("eclipse", 0.0)
        cube += series[:, None, None] * img[None]
    target_img = images[0]
    aperture = target_img >= aperture_threshold * target_img.max()
    if halo_dim:
        ring = dilate(aperture, 2) & ~aperture
        factor = np.where(in_transit, 1.0 - halo_dim, 1.0)
        cube[:, ring] *= factor[:, None]
    if saturate_at is not None:
        for i in range(time.size):
            img = cube[i]
            for col in range(shape[1]):
                column = img[:, col]
                excess = np.clip(column - saturate_at, 0, None).sum()
                column = np.minimum(column, saturate_at)
                peak = int(np.argmax(column))
                up, down = peak - 1, peak + 1
                while excess > 0 and (up >= 0 or down < shape[0]):
                    for j in (up, down):
                        if 0 <= j < shape[0] and excess > 0:
                            add = min(saturate_at - column[j], excess)
                            column[j] += add
                            excess -= add
                    up, down = up - 1, down + 1
                img[:, col] = column
    electrons = np.clip(cube, 0, None) * exptime_s
    err = np.sqrt(electrons + read_noise ** 2) / exptime_s
    flux = cube + rng.normal(0.0, 1.0, cube.shape) * err
    quality = np.zeros(time.size, int)
    for d in dumps:
        quality[np.argmin(np.abs(time - d))] |= MOMENTUM_DUMP_BIT
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [stars[0]["x"] + 1.0, stars[0]["y"] + 1.0]   # FITS 1-based: the target sits at CRVAL
    w.wcs.cdelt = [-pixel_scale_arcsec / 3600.0, pixel_scale_arcsec / 3600.0]
    header = {"tic": 0, "sector": 1, "tessmag": None, "ra": ra, "dec": dec, "ra_epoch": ra, "dec_epoch": dec,
              "crowdsap": None, "flfrcsap": None}
    return TargetPixels(time=time, flux=flux, flux_err=err, quality=quality, aperture=aperture, wcs=w,
                        header=header, provenance={"file": "synthetic", "seed": seed})


def write_tpf_fits(tpf: TargetPixels, path: str | Path, *, extra_header: dict | None = None) -> Path:
    """Write a TargetPixels in the SPOC TPF layout (PIXELS table, APERTURE image with bit 2 for the optimal
    aperture), so :func:`load_tpf` can be tested on a real file."""
    from astropy.io import fits

    n, ny, nx = tpf.flux.shape
    primary = fits.PrimaryHDU()
    for k, v in {"TICID": tpf.header.get("tic") or 0, "SECTOR": tpf.header.get("sector") or 1,
                 "RA_OBJ": tpf.header.get("ra"), "DEC_OBJ": tpf.header.get("dec"),
                 "TESSMAG": tpf.header.get("tessmag")}.items():
        if v is not None:
            primary.header[k] = v
    cols = [fits.Column("TIME", "D", array=tpf.time), fits.Column("QUALITY", "J", array=tpf.quality),
            fits.Column("FLUX", f"{ny * nx}E", dim=f"({nx},{ny})", array=tpf.flux.astype(np.float32)),
            fits.Column("FLUX_ERR", f"{ny * nx}E", dim=f"({nx},{ny})", array=tpf.flux_err.astype(np.float32))]
    table = fits.BinTableHDU.from_columns(cols, name="PIXELS")
    table.header["TSTART"] = float(tpf.time[0])
    for k, v in (extra_header or {}).items():
        table.header[k] = v
    ap_header = tpf.wcs.to_header() if tpf.wcs is not None else fits.Header()
    if tpf.header.get("ra_epoch") is not None:
        ap_header["RA_OBJ"] = tpf.header["ra_epoch"]
        ap_header["DEC_OBJ"] = tpf.header["dec_epoch"]
    aperture = fits.ImageHDU(np.where(tpf.aperture, 3, 1).astype(np.int32), header=ap_header, name="APERTURE")
    path = Path(path)
    fits.HDUList([primary, table, aperture]).writeto(path, overwrite=True)
    return path

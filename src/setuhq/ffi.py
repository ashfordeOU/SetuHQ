# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Light curves of any sky position from TESS full-frame images: a TESScut cutout and difference photometry.

SPOC's 2-minute light curves exist only for stars chosen before each sector, so a supernova or other transient in
a galaxy is seen only in the full-frame images. :func:`fetch_cutout` asks MAST's TESScut service for a small
cutout (11 × 11 pixels by default, a few megabytes per sector) of the SPOC full-frame images, cached under
``cache/tesscut/``; :func:`difference_lightcurve` then

1. keeps cadences with quality 0 and finite pixels;
2. builds a reference image, per pixel the median of the quarter of cadences in which the target aperture is
   faintest (a 1-day running median of its sum decides), so an event that brightens part of the sector is not in
   the reference;
3. subtracts it, and removes each cadence's residual background, a plane fitted to the difference image's pixels
   away from the target and outside the control apertures (the most variable pixels, stars, refitted out);
4. sums a 3 × 3 aperture at the target's position (its WCS pixel) and at control positions about four pixels away
   (the first two of east, west, north and south that fit), with errors from FLUX_ERR;
5. measures the difference image's flux-weighted centroid near the target each cadence (a moving asteroid shifts
   it) and an aperture correction, the median 3 × 3 share of a 7 × 7 sum for the brightest stars of the reference
   image (when no star is bright enough, 0.85, a Gaussian of FWHM 2 pixels, labelled as assumed).

Fluxes are in e⁻/s; a TESS magnitude is 20.44 − 2.5 log₁₀(flux) (TESS Instrument Handbook). Only derived numbers
are kept; the cutout files stay in the local cache and can be deleted (``keep=False``).

Data: TESScut (Brasseur et al. 2019, ascl:1905.007) cutouts of TESS full-frame images calibrated by the SPOC
pipeline at NASA Ames (Jenkins et al. 2016), served by MAST at STScI.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

CACHE = "cache/tesscut"
# The 3 x 3 share of a point source's flux used when no star in the cutout can measure it: a Gaussian of FWHM 2
# pixels (about the TESS PSF's core) puts 0.85 of its flux in 3 x 3 pixels; stated as assumed where used.
ASSUMED_APERTURE_SHARE = 0.85
CREDIT = ("TESS full-frame images (SPOC, Jenkins et al. 2016) through MAST's TESScut service (Brasseur et al. 2019); "
          "TESS is funded by NASA's Science Mission Directorate.")


def _approx_mid(sector: int) -> float:
    """A rough mid-time (BTJD) of a sector for ordering the probes; exact ranges come from the cutouts themselves."""
    return 1338.5 + 27.35 * (int(sector) - 1)


def sector_range(ra: float, dec: float, sector: int, cache_dir: str | Path = CACHE) -> tuple[float, float]:
    """First and last cadence time (BTJD) of a sector at a position, from a 1 × 1 pixel cutout (cached)."""
    from astropy.io import fits

    cache = Path(cache_dir)
    idx = cache / "sector_ranges.json"
    known = json.loads(idx.read_text()) if idx.exists() else {}
    if str(sector) in known:
        return tuple(known[str(sector)])
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Tesscut

    probe = cache / "probe"
    probe.mkdir(parents=True, exist_ok=True)
    m = Tesscut.download_cutouts(coordinates=SkyCoord(ra, dec, unit="deg"), size=1, sector=int(sector), path=str(probe))
    rng = None
    for p in m["Local Path"]:
        with fits.open(p) as h:
            tt = np.asarray(h[1].data["TIME"], float)
            tt = tt[np.isfinite(tt)]
            rng = (float(tt.min()), float(tt.max()))
        Path(p).unlink(missing_ok=True)
    known[str(sector)] = rng
    idx.write_text(json.dumps(known, indent=1))
    return rng


def choose_sector(ra: float, dec: float, t_event: float, cache_dir: str | Path = CACHE) -> dict:
    """The sector whose time range contains ``t_event``, else the last sector that ends before it (protocol v4's
    rule), probing at most the three sectors nearest in time."""
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Tesscut

    sectors = sorted({int(s) for s in Tesscut.get_sectors(coordinates=SkyCoord(ra, dec, unit="deg"))["sector"]})
    near = sorted(sectors, key=lambda s: abs(_approx_mid(s) - t_event))[:3]
    ranges = {s: sector_range(ra, dec, s, cache_dir) for s in near}
    inside = [s for s, (a, b) in ranges.items() if a <= t_event <= b]
    if inside:
        return {"sector": inside[0], "range": ranges[inside[0]], "rule": "contains the event time", "probed": ranges}
    before = [s for s, (a, b) in ranges.items() if b < t_event]
    if before:
        s = max(before, key=lambda x: ranges[x][1])
        return {"sector": s, "range": ranges[s], "rule": "the last sector ending before the event time", "probed": ranges}
    return {"sector": None, "range": None, "rule": "no sector contains or precedes the event time", "probed": ranges}


def fetch_cutout(ra: float, dec: float, sector: int, size: int = 11, cache_dir: str | Path = CACHE) -> Path:
    """A TESScut cutout of the SPOC full-frame images (``size`` × ``size`` pixels, one sector), downloaded once."""
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Tesscut

    folder = Path(cache_dir) / f"{ra:.5f}_{dec:+.5f}"
    folder.mkdir(parents=True, exist_ok=True)
    have = sorted(folder.glob(f"tess-s{int(sector):04d}-*_{size}x{size}_astrocut.fits"))
    if have:
        return have[0]
    m = Tesscut.download_cutouts(coordinates=SkyCoord(ra, dec, unit="deg"), size=size, sector=int(sector), path=str(folder))
    return Path(m["Local Path"][0])


def _aperture(cx: int, cy: int, shape, half: int = 1):
    ny, nx = shape
    if cx - half < 0 or cy - half < 0 or cx + half >= nx or cy + half >= ny:
        return None
    m = np.zeros(shape, bool)
    m[cy - half:cy + half + 1, cx - half:cx + half + 1] = True
    return m


def difference_lightcurve(path: str | Path, ra: float, dec: float, *, offset: int = 4) -> dict:
    """Difference photometry of a cutout at (ra, dec), with two control apertures; see the module docstring."""
    from astropy.io import fits
    from astropy.wcs import WCS

    from setuhq.preprocess import running_median

    with fits.open(path) as h:
        d = h[1].data
        time = np.asarray(d["TIME"], float)
        flux = np.asarray(d["FLUX"], float)
        ferr = np.asarray(d["FLUX_ERR"], float)
        qual = np.asarray(d["QUALITY"], int)
        wcs = WCS(h[2].header)
        hdr = dict(h[0].header)
    from setuhq.transients import quality_times

    qt = quality_times(time, qual)
    good = np.isfinite(time) & (qual == 0) & np.all(np.isfinite(flux), axis=(1, 2))
    time, flux, ferr = time[good], flux[good], ferr[good]
    ny, nx = flux.shape[1:]
    px, py = wcs.all_world2pix([[ra, dec]], 0)[0]
    cx, cy = int(round(px)), int(round(py))
    target = _aperture(cx, cy, (ny, nx))
    if target is None or len(time) < 50:
        raise ValueError("the target aperture does not fit in the cutout, or too few good cadences")
    controls = []
    for name, dx, dy in (("east", offset, 0), ("west", -offset, 0), ("north", 0, offset), ("south", 0, -offset)):
        a = _aperture(cx + dx, cy + dy, (ny, nx))
        if a is not None:
            controls.append((name, a))
        if len(controls) == 2:
            break
    raw_sum = flux[:, target].sum(axis=1)
    smooth = running_median(time, raw_sum, 1.0)
    faint = smooth <= np.percentile(smooth, 25)
    ref = np.median(flux[faint], axis=0)
    diff = flux - ref
    used = target.copy()
    for _, a in controls:
        used |= a
    # residual background: a plane fitted each cadence to the pixels away from the target (more than two pixels) and
    # outside the control apertures, refitted without the pixels that vary most (stars), so a scattered-light
    # gradient across the cutout is removed
    yy, xx = np.mgrid[0:ny, 0:nx]
    far = (np.hypot(xx - cx, yy - cy) > 2.5) & ~used
    if far.sum() >= 10:
        A = np.vstack([np.ones(far.sum()), xx[far] - cx, yy[far] - cy]).T
        D = diff[:, far]
        coef = np.linalg.lstsq(A, D.T, rcond=None)[0]
        res = D - (A @ coef).T
        quiet = np.median(np.abs(res), axis=0)
        keep = quiet <= np.percentile(quiet, 70)
        coef = np.linalg.lstsq(A[keep], D[:, keep].T, rcond=None)[0]
        plane = coef[0][:, None, None] + coef[1][:, None, None] * (xx - cx)[None] + coef[2][:, None, None] * (yy - cy)[None]
        diff = diff - plane
    lc = diff[:, target].sum(axis=1)
    err = np.sqrt((ferr[:, target] ** 2).sum(axis=1))
    ctrl = {name: diff[:, a].sum(axis=1) for name, a in controls}
    # centroid of the positive difference flux in a 5 x 5 box around the target
    box = _aperture(cx, cy, (ny, nx), half=2)
    if box is None:
        box = target
    w = np.clip(diff[:, box], 0, None)
    xs, ys = xx[box], yy[box]
    tot = w.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cen = np.stack([(w * xs).sum(axis=1) / tot, (w * ys).sum(axis=1) / tot], axis=1)
    cen[tot <= 0] = np.nan
    # aperture correction: the 3 x 3 share of a 7 x 7 sum for the brightest stars of the reference image (local
    # maxima away from the target whose 7 x 7 box fits), less a background from the faintest pixels
    corr = None
    bg = float(np.percentile(ref, 20))
    rs = ref - bg
    peaks = []
    for j in range(3, ny - 3):
        for i in range(3, nx - 3):
            v = rs[j, i]
            if v > 0 and v == rs[j - 1:j + 2, i - 1:i + 2].max() and np.hypot(i - cx, j - cy) > 2.5:
                peaks.append((v, i, j))
    shares = []
    for v, i, j in sorted(peaks, reverse=True)[:3]:
        s3, s7 = rs[j - 1:j + 2, i - 1:i + 2].sum(), rs[j - 3:j + 4, i - 3:i + 4].sum()
        if s7 > 0 and v > 20 * np.std(rs[rs < np.percentile(rs, 50)]):
            shares.append(s3 / s7)
    corr_source = None
    if shares:
        corr, corr_source = float(np.clip(np.median(shares), 0.5, 1.0)), f"median of {len(shares)} reference-image stars"
    else:
        corr, corr_source = ASSUMED_APERTURE_SHARE, "assumed (no star in the cutout bright enough to measure it)"
    return {"time": time, "flux": lc, "flux_err": err, "controls": ctrl, "centroid": cen, "quality_times": qt,
            "pixel": [float(px), float(py)], "aperture_pixel": [cx, cy], "controls_used": [n for n, _ in controls],
            "aperture_correction": corr, "aperture_correction_source": corr_source, "n_reference_cadences": int(faint.sum()), "sector": hdr.get("SECTOR"),
            "camera": hdr.get("CAMERA"), "ccd": hdr.get("CCD"), "cadence_days": float(np.median(np.diff(time)))}

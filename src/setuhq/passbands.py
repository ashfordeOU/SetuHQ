# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Instrument passbands for flare energies: TESS and CHEOPS response curves, and blackbody integrals over them.

The curves are the SVO Filter Profile Service's (Rodrigo et al. 2012, 2020) ``TESS/TESS.Red`` and
``CHEOPS/CHEOPS.band``, fetched 2026-10-21 and resampled here to 10 nm steps (linear interpolation), so the
package needs no network for them. The source files' sha256 are in :data:`PASSBANDS`. TESS's curve is an
energy-counting response and CHEOPS's a photon-counting one (SVO ``DetectorType``); :func:`band_integral` weights
by wavelength for a photon counter, as SVO does.
"""

from __future__ import annotations

import math

import numpy as np

H = 6.62607015e-27     # erg s
C = 2.99792458e10      # cm/s
K_B = 1.380649e-16     # erg/K
SIGMA_SB = 5.670374419e-5  # erg cm^-2 s^-1 K^-4
R_SUN_CM = 6.957e10    # IAU 2015 nominal solar radius
PC_CM = 3.0856775814913673e18

_TESS = [
    0.0002, 0.0085, 0.4596, 0.8949, 0.9137, 0.9187, 0.9249, 0.9312, 0.9358, 0.9413, 0.9442, 0.9494, 0.9528, 0.9545,
    0.9575, 0.9557, 0.9618, 0.9718, 0.9758, 0.9800, 0.9875, 0.9923, 0.9888, 0.9885, 0.9926, 0.9936, 0.9929, 0.9955,
    0.9992, 0.9999, 0.9932, 0.9886, 0.9728, 0.9558, 0.9281, 0.9006, 0.8593, 0.8185, 0.7685, 0.7180, 0.6568, 0.5958,
    0.5182, 0.4401, 0.3583, 0.2819, 0.2158, 0.1587, 0.1236, 0.0889, 0.0669, 0.0499, 0.0404, 0.0292, 0.0179, 0.0069
]
_CHEOPS = [
    0.0000, 0.0148, 0.0489, 0.1481, 0.2666, 0.3753, 0.4586, 0.5235, 0.5829, 0.6394, 0.6929, 0.7413, 0.7756, 0.8014,
    0.8263, 0.8518, 0.8775, 0.9036, 0.9292, 0.9530, 0.9726, 0.9840, 0.9925, 0.9965, 0.9965, 0.9961, 0.9889, 0.9804,
    0.9701, 0.9554, 0.9394, 0.9225, 0.9033, 0.8842, 0.8651, 0.8460, 0.8281, 0.8111, 0.7936, 0.7732, 0.7525, 0.7279,
    0.7033, 0.6779, 0.6490, 0.6204, 0.5927, 0.5649, 0.5373, 0.5100, 0.4827, 0.4545, 0.4247, 0.3952, 0.3657, 0.3363,
    0.3066, 0.2769, 0.2500, 0.2235, 0.1990, 0.1746, 0.1521, 0.1305, 0.1105, 0.0914, 0.0754, 0.0595, 0.0460, 0.0344,
    0.0246, 0.0195, 0.0170, 0.0146, 0.0127, 0.0116, 0.0000
]

PASSBANDS = {
    "TESS": {"start_nm": 570.0, "step_nm": 10.0, "response": _TESS, "photon_counting": False,
              "svo_id": "TESS/TESS.Red", "zero_point_jy": 2631.8836657594, "width_eff_angstrom": 3898.6464608748,
              "wavelength_eff_angstrom": 7452.6363423211,
              "source_sha256": "be517b2135733f16b01aea75c01f61b50752d634f3ae33d6c09965979ad49038"},
    "CHEOPS": {"start_nm": 340.0, "step_nm": 10.0, "response": _CHEOPS, "photon_counting": True,
                "svo_id": "CHEOPS/CHEOPS.band", "zero_point_jy": 3264.0957620195, "width_eff_angstrom": 4336.7003320516,
                "wavelength_eff_angstrom": 5809.9192606908,
                "source_sha256": "f9521c284df857b00c5c7dfb9bd70c71773df4efc215f39f5bf583ea7a2ad2a1"},
}
SOURCE = ("SVO Filter Profile Service (Rodrigo et al. 2012; Rodrigo & Solano 2020), fetched 2026-10-21, "
          "resampled to 10 nm")


def response(band: str) -> tuple[np.ndarray, np.ndarray]:
    """(wavelength in cm, response) of a passband on its 10 nm grid."""
    try:
        p = PASSBANDS[band.upper()]
    except KeyError:
        raise ValueError(f"unknown passband {band!r}; known: {sorted(PASSBANDS)}") from None
    r = np.asarray(p["response"], float)
    lam_nm = p["start_nm"] + p["step_nm"] * np.arange(r.size)
    return lam_nm * 1e-7, r


def planck_lambda(lam_cm, temperature: float) -> np.ndarray:
    """Blackbody specific intensity B_λ(T) in erg s^-1 cm^-2 cm^-1 sr^-1."""
    lam = np.asarray(lam_cm, float)
    x = H * C / (lam * K_B * float(temperature))
    return 2.0 * H * C ** 2 / lam ** 5 / np.expm1(np.minimum(x, 700.0))


def band_integral(temperature: float, band: str) -> float:
    """∫ R(λ) w(λ) B_λ(T) dλ over the passband (w = λ/λ_ref for a photon counter, 1 otherwise), in
    erg s^-1 cm^-2 sr^-1 (the photon weight is normalised at the band's effective wavelength, so ratios and
    the energy-counting case are in the same units)."""
    lam, r = response(band)
    p = PASSBANDS[band.upper()]
    w = lam / (p["wavelength_eff_angstrom"] * 1e-8) if p["photon_counting"] else 1.0
    y = r * w * planck_lambda(lam, temperature)
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(lam)))


def band_fraction(temperature: float, band: str) -> float:
    """The fraction of a blackbody's bolometric surface flux σT⁴ that the passband records: π ∫R w B_λ dλ / σT⁴."""
    return math.pi * band_integral(temperature, band) / (SIGMA_SB * float(temperature) ** 4)

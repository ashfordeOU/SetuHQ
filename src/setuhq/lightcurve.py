"""The light-curve container used by every stage of the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, eq=False)
class LightCurve:
    """A single light curve in one time system.

    Times are sorted on construction. ``provenance`` records where the data came
    from and every processing step applied to it, so a candidate can always be
    traced back to its input.
    """

    target: str
    mission: str
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    provenance: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        time = np.asarray(self.time, dtype=float)
        flux = np.asarray(self.flux, dtype=float)
        flux_err = np.asarray(self.flux_err, dtype=float)
        if time.ndim != 1 or not (time.shape == flux.shape == flux_err.shape):
            raise ValueError("time, flux and flux_err must be 1-D arrays of equal length")
        order = np.argsort(time, kind="stable")
        object.__setattr__(self, "time", time[order])
        object.__setattr__(self, "flux", flux[order])
        object.__setattr__(self, "flux_err", flux_err[order])

    def __len__(self) -> int:
        return self.time.size

    def with_data(self, time, flux, flux_err, **provenance) -> "LightCurve":
        """Return a copy with new arrays and extra provenance entries."""
        return LightCurve(
            target=self.target,
            mission=self.mission,
            time=time,
            flux=flux,
            flux_err=flux_err,
            provenance={**self.provenance, **provenance},
        )

    def masked(self, mask: np.ndarray, **provenance) -> "LightCurve":
        """Return a copy keeping only the points where ``mask`` is true."""
        return self.with_data(self.time[mask], self.flux[mask], self.flux_err[mask], **provenance)

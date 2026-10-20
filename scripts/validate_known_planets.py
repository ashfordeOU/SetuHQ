# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Compare a run's vetted candidates with the NASA Exoplanet Archive ephemeris of a known host.

Usage:
    python scripts/validate_known_planets.py RUN_DIR "pi Men" --out docs/results/pi_men_validation.md

For each confirmed planet of the host with a period, the script predicts transit
epochs inside the run's time span and matches the vetted candidates to them. It
reports timing offset, depth ratio and duration ratio. Those ratios show how
faithful the box-shaped detection is to the published transit.

This needs network access to exoplanetarchive.ipac.caltech.edu.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

BJD_OFFSET = 2457000.0  # NASA archive times are BJD_TDB; TESS BTJD = BJD_TDB - 2457000


def load_candidates(run_dir: Path) -> list[dict]:
    with (run_dir / "candidates.csv").open() as handle:
        return [row for row in csv.DictReader(handle) if row["passed"] == "True"]


def _num(value) -> float:
    """Archive values arrive as masked astropy quantities. Missing values become NaN."""
    if value is None or np.ma.is_masked(value):
        return math.nan
    return float(getattr(value, "value", value))


def fetch_planets(host: str):
    table = NasaExoplanetArchive.query_criteria(
        table="ps",
        select="pl_name,pl_orbper,pl_tranmid,pl_trandur,pl_trandep,default_flag",
        where=f"(hostname='{host}' or pl_name like '{host} %') and default_flag=1",
    )
    return [row for row in table if not math.isnan(_num(row["pl_orbper"]))]


def match(planet, candidates, t_min: float, t_max: float, tolerance_days: float = 0.1):
    period = _num(planet["pl_orbper"])
    if math.isnan(_num(planet["pl_tranmid"])):
        return None
    t_mid = _num(planet["pl_tranmid"]) - BJD_OFFSET
    first = math.ceil((t_min - t_mid) / period)
    last = math.floor((t_max - t_mid) / period)
    matches = []
    n_expected = max(0, last - first + 1)
    for k in range(first, last + 1):
        expected = t_mid + k * period
        for row in candidates:
            if abs(float(row["t_center"]) - expected) <= tolerance_days:
                matches.append((k, expected, row))
    return period, matches, n_expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("host")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidates = load_candidates(args.run_dir)
    times = [float(c["t_center"]) for c in candidates] or [0.0]
    planets = fetch_planets(args.host)

    lines = [
        f"# Validation against NASA Exoplanet Archive: {args.host}",
        "",
        f"Run: `{args.run_dir}`. Vetted candidates: {len(candidates)}. "
        f"Time span searched: {min(times):.2f} to {max(times):.2f} BTJD.",
        "",
        "| planet | P (d) | predicted epochs in span | recovered | mean timing offset (min) | depth ratio (ours/catalogue) | duration ratio (ours/catalogue) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for planet in planets:
        result = match(planet, candidates, min(times) - 0.5, max(times) + 0.5)
        if result is None:
            continue
        period, matches, predicted = result
        epochs = len({k for k, _, _ in matches}) if matches else 0
        offsets = [(float(row["t_center"]) - expected) * 1440.0 for _, expected, row in matches]
        depth_ratio = _ratio(
            [float(row["depth_ppm"]) for _, _, row in matches],
            _num(planet["pl_trandep"]) * 1e4,
        )
        dur_ratio = _ratio(
            [float(row["duration_hours"]) for _, _, row in matches],
            _num(planet["pl_trandur"]),
        )
        mean_offset = f"{sum(offsets) / len(offsets):+.1f}" if offsets else "n/a"
        lines.append(
            f"| {planet['pl_name']} | {period:.5f} | {predicted} | {epochs} | {mean_offset} | {depth_ratio} | {dur_ratio} |"
        )
    lines += [
        "",
        "Depth is in ppm (catalogue depth is a percentage, converted by x 10^4). Duration is in hours.",
        "A ratio near 1 means the detection matches the published transit. Box fits are expected to be somewhat shallower and shorter than published trapezoid fits.",
        "",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


def _ratio(ours: list[float], catalogue: float) -> str:
    if not ours or math.isnan(catalogue) or catalogue == 0:
        return "n/a"
    return f"{(sum(ours) / len(ours)) / catalogue:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())

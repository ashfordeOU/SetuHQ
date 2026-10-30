# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The standard review panel, for code that uses SetuHQ as a library.

* :func:`standard_probes`: the three Probes of the standard panel (deterministic matched-filter detectors), exactly as
  ``configs/sweep.toml`` lists them (a test keeps the two in step). Pass them as a config's ``reviewers`` or to
  :func:`setuhq.config.build_reviewers`.
* :func:`default_weights`, :func:`default_calibration` and :func:`packaged_weights_path`: the calibrated reviewer weights
  and their calibration record. The wheel ships a copy of
  ``docs/results/reviewer_weights_full_panel.json`` (and its ``.calibration.json`` record) as package data, so a run
  from an installed package uses the calibrated weights by default, as a run from a checkout does.

Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic
matched-filter detectors.
"""

from __future__ import annotations

import copy
import json
from importlib.resources import files
from pathlib import Path

WEIGHTS_NAME = "reviewer_weights_full_panel.json"
CHECKOUT_WEIGHTS = "docs/results/" + WEIGHTS_NAME

# configs/sweep.toml's [[reviewers]], in its order.
_STANDARD_PROBES = (
    {"type": "simulated", "id": "volunteer-sensitive", "snr_threshold": 4.5, "miss_probability": 0.05, "seed": 11},
    {"type": "simulated", "id": "volunteer-typical", "snr_threshold": 5.0, "miss_probability": 0.10, "seed": 12},
    {"type": "simulated", "id": "volunteer-cautious", "snr_threshold": 5.5, "miss_probability": 0.15, "seed": 13},
)


def standard_probes() -> list[dict]:
    """The standard Probe panel as reviewer specs (fresh copies, safe to change)."""
    return copy.deepcopy(list(_STANDARD_PROBES))


def packaged_weights_path() -> Path | None:
    """The calibrated weights file shipped in the package, or None when this install lacks it."""
    p = Path(str(files("setuhq") / "data" / WEIGHTS_NAME))
    return p if p.is_file() else None


def default_weights_path(checkout: str | Path = CHECKOUT_WEIGHTS, *, packaged_only: bool = False) -> str | None:
    """The weights file a run uses by default: the checkout's ``docs/results`` copy when it exists (a run from the
    repository), else the packaged copy (an installed wheel), else None. With ``packaged_only=True`` the packaged
    copy only, whatever the current directory holds (for a service)."""
    if not packaged_only and Path(checkout).exists():
        return str(checkout)
    p = packaged_weights_path()
    return str(p) if p else None


def default_weights(*, packaged_only: bool = False) -> dict[str, float]:
    """The calibrated weight of each reviewer of the full panel ({reviewer id: weight}); {} when none is shipped."""
    path = default_weights_path(packaged_only=packaged_only)
    return {k: float(v) for k, v in json.loads(Path(path).read_text()).items()} if path else {}


def default_calibration(*, packaged_only: bool = False) -> dict | None:
    """The calibration record stored next to :func:`default_weights_path` (``x.json`` -> ``x.calibration.json``):
    each reviewer's measured rates, provider and model, for ``run_pipeline(calibration=...)``. None without one."""
    from setuhq.calibrate import calibration_path

    path = default_weights_path(packaged_only=packaged_only)
    record = calibration_path(path) if path else None
    return json.loads(record.read_text()) if record and record.is_file() else None

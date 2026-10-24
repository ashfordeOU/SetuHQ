# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""SetuHQ's stable public API: the names code outside this repository may rely on.

Everything listed in :data:`__all__` keeps its name, its call signature (existing parameters keep their meaning;
new ones are keyword-only with a default) and its documented behaviour across minor releases. A name leaves only
after a minor release that deprecates it with a warning, and only in a later major release (0.x: the next minor
version counts as the major one). docs/API.md lists these names, and what is internal: every other module, function
and constant of the package may change in any release. tests/test_api.py pins the list.

    from setuhq.api import load_config, build_reviewers, load_tess, run_pipeline, default_weights

Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic
matched-filter detectors. Every result is a candidate, never a confirmed planet.
"""

from __future__ import annotations

from setuhq import __version__
from setuhq.aggregate import aggregate
from setuhq.calibrate import apply_calibration
from setuhq.config import RunConfig, build_reviewers, load_config
from setuhq.lightcurve import LightCurve
from setuhq.loaders import load_csv, load_spoc_file, load_tess
from setuhq.names import ATTRIBUTION, PROBES_ONLY, dip_count, dip_state
from setuhq.panel import default_weights, default_weights_path, packaged_weights_path, standard_probes
from setuhq.pipeline import run_pipeline
from setuhq.reviewers.claude import ClaudeReviewer
from setuhq.reviewers.gemini import GeminiReviewer
from setuhq.reviewers.openai_compat import OpenAICompatibleReviewer, OpenAIReviewer
from setuhq.reviewers.sentinel import Secret
from setuhq.reviewers.simulated import SimulatedVolunteer
from setuhq.transitfit import fit_transit, transit_model

__all__ = [
    "__version__",
    # configuration and the panel
    "RunConfig", "load_config", "build_reviewers", "standard_probes",
    "default_weights", "default_weights_path", "packaged_weights_path", "apply_calibration",
    # reviewers: Probes and Sentinels (a key may be passed in code as api_key=; never from a config file)
    "SimulatedVolunteer", "ClaudeReviewer", "OpenAIReviewer", "OpenAICompatibleReviewer", "GeminiReviewer", "Secret",
    # light curves
    "LightCurve", "load_tess", "load_spoc_file", "load_csv",
    # the run and its pieces
    "run_pipeline", "aggregate", "fit_transit", "transit_model",
    # wording every output must use
    "ATTRIBUTION", "PROBES_ONLY", "dip_state", "dip_count",
]

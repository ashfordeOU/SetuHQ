# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""SetuHQ's stable public API: the names code outside this repository may rely on.

Everything listed in :data:`__all__` keeps its name, its call signature (existing parameters keep their meaning;
new ones are keyword-only with a default) and its documented behaviour across minor releases. A name leaves only
after a minor release that deprecates it with a warning, and only in a later major release (0.x: the next minor
version counts as the major one). docs/API.md lists these names, and what is internal: every other module, function
and constant of the package may change in any release. tests/test_api.py pins the list.

    from setuhq.api import load_config, build_reviewers, load_tess, run_pipeline, default_weights

The stellar capabilities (flares, pulsations, eclipsing binaries, rotation, transients) answer with a
:class:`StellarResult` that carries its honesty labels and validation status; callers carry those words verbatim
(:data:`HONESTY_LABELS`). :func:`use_lang` sets the language of the localised wording for one call, thread or task.
CHEOPS stays out of this API: its data are under ESA's CC BY-NC 3.0 IGO terms.

Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic
matched-filter detectors. Every result is a candidate, never a confirmed planet.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType

from setuhq import __version__
from setuhq import i18n as _i18n
from setuhq.aggregate import aggregate
from setuhq.binaries import LABEL as BINARIES_LABEL
from setuhq.binaries import VETTING_NOTE as BINARIES_VETTING_NOTE
from setuhq.calibrate import apply_calibration
from setuhq.config import RunConfig, build_reviewers, load_config
from setuhq.lightcurve import LightCurve
from setuhq.loaders import load_csv, load_spoc_file, load_tess
from setuhq.names import ATTRIBUTION, DIP_STATE, PROBES_ONLY, dip_count, dip_state
from setuhq.panel import (default_calibration, default_weights, default_weights_path, packaged_weights_path,
                          standard_probes)
from setuhq.pipeline import Candidate, RunSummary, run_pipeline
from setuhq.reviewers.claude import DEFAULT_MODEL as _CLAUDE_DEFAULT_MODEL
from setuhq.reviewers.claude import ClaudeReviewer
from setuhq.reviewers.gemini import GeminiReviewer
from setuhq.reviewers.http import Transport
from setuhq.reviewers.openai_compat import OpenAICompatibleReviewer, OpenAIReviewer
from setuhq.reviewers.sentinel import KEY_ENV as _KEY_ENV
from setuhq.reviewers.sentinel import Secret
from setuhq.reviewers.simulated import SimulatedVolunteer
from setuhq.rotation import LABEL as ROTATION_LABEL
from setuhq.stellar_tools import DETECTED as STELLAR_DETECTION_LABEL
from setuhq.stellar_tools import ENERGY as FLARE_ENERGY_LABEL
from setuhq.stellar_tools import TRANSIENT_SEARCH_AID
from setuhq.transients import LABEL as TRANSIENTS_LABEL
from setuhq.transitfit import fit_transit, transit_model

# ---------------------------------------------------------------------------------------------------------------
# Sentinels: the provider key variables and the default models (docs/API.md)
# ---------------------------------------------------------------------------------------------------------------

#: The environment variable each provider's key is read from when no ``api_key=`` is passed (and ``env_fallback`` is
#: not False). An OpenAI-compatible endpoint names its own with ``api_key_env=``.
PROVIDER_KEY_ENV = MappingProxyType(dict(_KEY_ENV))
#: The model each Sentinel uses when none is given. OpenAI, OpenAI-compatible and Gemini Sentinels have none: they
#: need ``model=``.
DEFAULT_SENTINEL_MODELS = MappingProxyType({"claude": _CLAUDE_DEFAULT_MODEL})

# ---------------------------------------------------------------------------------------------------------------
# Honesty labels: carried verbatim
# ---------------------------------------------------------------------------------------------------------------

#: Every honesty label and wording constant of this API, exactly as written. A caller carries them verbatim; an output
#: filter that withholds words such as "confirmed" exempts an exact match of one of these strings, because each says
#: what a result is not ("never a confirmed or new binary").
HONESTY_LABELS = frozenset({
    ATTRIBUTION, PROBES_ONLY, STELLAR_DETECTION_LABEL, FLARE_ENERGY_LABEL, BINARIES_LABEL, BINARIES_VETTING_NOTE,
    ROTATION_LABEL, TRANSIENTS_LABEL, TRANSIENT_SEARCH_AID,
    *(text for _cls, tag, phrase in DIP_STATE.values() for text in (tag, phrase)),
})

# ---------------------------------------------------------------------------------------------------------------
# Language per call
# ---------------------------------------------------------------------------------------------------------------

#: The languages SetuHQ speaks (BCP 47 tags); English is the source.
SUPPORTED_LANGS = tuple(_i18n.LOCALES)


@contextlib.contextmanager
def use_lang(lang: str | None = None):
    """Inside the block, SetuHQ's human-facing words are in ``lang`` (a BCP 47 tag or POSIX locale; English for one
    SetuHQ does not speak), and the block yields the language used. ``None`` means the process default: ``SETUHQ_LANG``,
    then the locale variables, else English. It sets a context variable, never the environment, so each thread and
    each asyncio task has its own language; outside every block the language is what it was (English in a library,
    ``--lang`` or ``SETUHQ_LANG`` in the CLI and the MCP server)."""
    code = (_i18n.normalise(lang) or _i18n.SOURCE) if lang else _i18n.resolve_lang()
    with _i18n.use(code):
        yield code


def current_lang() -> str:
    """The language SetuHQ's words are in here and now (this thread or task)."""
    return _i18n.current()


def _say(msg_id: str, en: str, lang: str | None) -> str:
    if lang is None:
        return _i18n.t(msg_id, en)
    with use_lang(lang):
        return _i18n.t(msg_id, en)


def attribution_text(lang: str | None = None) -> str:
    """:data:`ATTRIBUTION` in ``lang`` (default: the current language, :func:`use_lang`)."""
    return _say("honesty.attribution", ATTRIBUTION, lang)


def probes_only_text(lang: str | None = None) -> str:
    """:data:`PROBES_ONLY` in ``lang`` (default: the current language, :func:`use_lang`)."""
    return _say("honesty.probes_only", PROBES_ONLY, lang)


def dip_state_text(outcome: str | None, lang: str | None = None) -> tuple[str, str, str]:
    """:func:`dip_state` with its tag and phrase in ``lang`` (default: the current language): (css class, tag,
    phrase), for example ("cand", "candidate", "candidate, unconfirmed") in English. The class stays English."""
    cls, tag, phrase = dip_state(outcome)
    return cls, _say(f"dip.tag.{cls}", tag, lang), _say(f"dip.state.{cls}", phrase, lang)


# ---------------------------------------------------------------------------------------------------------------
# The stellar capabilities (CHEOPS is not here: its data are CC BY-NC 3.0 IGO)
# ---------------------------------------------------------------------------------------------------------------

STELLAR_CAPABILITIES = ("flares", "pulsations", "binaries", "rotation", "transients")
_STATUS_FILE = "stellar_validation_status.json"


@dataclass(frozen=True)
class StellarResult:
    """One stellar analysis: ``result`` (JSON-safe, the same fields the MCP tool returns), the honesty ``labels`` the
    result must be shown with (English, verbatim, each in :data:`HONESTY_LABELS`), and the capability's
    ``validation_status`` as its committed record states it ("partly validated (5 of 8 checks pass)", "not validated
    (1 of 9 checks pass)"), with the ``validation_record`` it comes from. A detection is a candidate, never a
    confirmation."""

    capability: str
    result: dict
    labels: tuple[str, ...]
    validation_status: str
    validation_record: str
    setuhq_version: str = __version__
    sources: tuple = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"capability": self.capability, "result": self.result, "labels": list(self.labels),
                "validation_status": self.validation_status, "validation_record": self.validation_record,
                "setuhq_version": self.setuhq_version, "sources": list(self.sources)}


def stellar_validation_status(capability: str) -> str:
    """A stellar capability's validation status, with its count of checks: from the checkout's record in
    docs/results, else the copy the package ships. "not validated (no validation record)" when neither has it."""
    from setuhq.stellar_tools import NO_RECORD, validation_status

    if capability not in STELLAR_CAPABILITIES:
        raise ValueError(f"capability must be one of {', '.join(STELLAR_CAPABILITIES)}")
    status = validation_status(capability)
    if status != NO_RECORD:
        return status
    try:
        shipped = json.loads(Path(str(files("setuhq") / "data" / _STATUS_FILE)).read_text())
        return shipped["capabilities"][capability]["label"]
    except (OSError, KeyError, ValueError):
        return NO_RECORD


def _stellar(capability: str, envelope: dict, labels: tuple[str, ...]) -> StellarResult:
    from setuhq.stellar_tools import validation_file

    status = stellar_validation_status(capability)
    result = dict(envelope["result"])
    result["validation_status"] = status
    return StellarResult(capability, result, labels, status, validation_file(capability),
                         sources=tuple(envelope["provenance"]["sources"]))


def _arrays(time, flux, flux_err):
    import numpy as np

    as_list = lambda a: None if a is None else np.asarray(a, float).tolist()  # noqa: E731
    return {"time": as_list(time), "flux": as_list(flux), "flux_err": as_list(flux_err)}


def find_flares(time, flux, flux_err=None, *, denoise: bool = False, teff: float | None = None,
                radius_rsun: float | None = None, tmag: float | None = None,
                distance_pc: float | None = None) -> StellarResult:
    """Stellar flares in a TESS light curve (time in BTJD days): each flare's peak, amplitude, rise and decay, FWHM,
    equivalent duration and, with Teff and radius, its energy (9000 K blackbody); and the flux-inverted null."""
    from setuhq import stellar_tools as st

    env = st.find_flares(**_arrays(time, flux, flux_err), mission="TESS", denoise=denoise, teff=teff,
                         radius_rsun=radius_rsun, tmag=tmag, distance_pc=distance_pc)
    return _stellar("flares", env, (STELLAR_DETECTION_LABEL, FLARE_ENERGY_LABEL))


def pulsation_spectrum(time, flux, flux_err=None, *, teff: float | None = None, fmin: float | None = None,
                       fmax: float | None = None, max_frequencies: int = 40, n_surrogates: int = 0) -> StellarResult:
    """Frequency analysis (time in days): pre-whitened frequencies down to S/N 4, combination flags, the granulation
    background, numax and Δν for solar-like oscillators, and a heuristic variability type."""
    from setuhq import stellar_tools as st

    env = st.pulsation_spectrum(**_arrays(time, flux, flux_err), teff=teff, fmin=fmin, fmax=fmax,
                                max_frequencies=max_frequencies, n_surrogates=n_surrogates)
    return _stellar("pulsations", env, (STELLAR_DETECTION_LABEL,))


def find_eclipsing_binary(time, flux, flux_err=None, *, transit_period: float | None = None,
                          transit_epoch: float | None = None,
                          transit_duration_days: float | None = None) -> StellarResult:
    """Eclipsing-binary analysis (time in days): period, eclipses, morphology and a candidate flag; with a transit
    candidate's period, epoch and duration, advisory vetting hints that SetuHQ's own vetting does not use."""
    from setuhq import stellar_tools as st

    env = st.find_eclipsing_binary(**_arrays(time, flux, flux_err), transit_period=transit_period,
                                   transit_epoch=transit_epoch, transit_duration_days=transit_duration_days)
    return _stellar("binaries", env, (BINARIES_LABEL, BINARIES_VETTING_NOTE))


def rotation_period(time, flux, flux_err=None) -> StellarResult:
    """A rotation period from spot modulation (time in days; one TESS sector measures up to about 13 days)."""
    from setuhq import stellar_tools as st

    env = st.rotation_period(**_arrays(time, flux, flux_err))
    return _stellar("rotation", env, (ROTATION_LABEL,))


def find_transients(time, flux, flux_err=None, *, difference_flux: bool = False,
                    momentum_dump_times=None, scattered_light_times=None) -> StellarResult:
    """Non-periodic brightenings (time in days) with class hints and false-alarm screens: a search aid, not validated.
    Every event is a transient candidate, never a new object."""
    from setuhq import stellar_tools as st

    env = st.find_transients(**_arrays(time, flux, flux_err), difference_flux=difference_flux,
                             momentum_dump_times=momentum_dump_times, scattered_light_times=scattered_light_times)
    return _stellar("transients", env, (TRANSIENTS_LABEL, TRANSIENT_SEARCH_AID))


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
    # added in 0.2: weights and their calibration record
    "default_calibration",
    # added in 0.2: Sentinels' key variables, default models and transport type; the run's results
    "PROVIDER_KEY_ENV", "DEFAULT_SENTINEL_MODELS", "Transport", "RunSummary", "Candidate",
    # added in 0.2: language per call
    "SUPPORTED_LANGS", "use_lang", "current_lang", "attribution_text", "probes_only_text", "dip_state_text",
    # added in 0.2: the stellar capabilities and their honesty labels (never CHEOPS)
    "StellarResult", "STELLAR_CAPABILITIES", "stellar_validation_status", "find_flares", "pulsation_spectrum",
    "find_eclipsing_binary", "rotation_period", "find_transients",
    "HONESTY_LABELS", "TRANSIENT_SEARCH_AID", "TRANSIENTS_LABEL", "BINARIES_LABEL", "BINARIES_VETTING_NOTE",
    "ROTATION_LABEL", "STELLAR_DETECTION_LABEL", "FLARE_ENERGY_LABEL",
]

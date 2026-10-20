"""Run configuration, read from TOML. Every value that changes a result lives here, so a run is reproducible from its config file."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from exoplan.reviewers import (
    ClaudeCodeReviewer,
    ClaudeReviewer,
    GeminiReviewer,
    OpenAICompatibleReviewer,
    OpenAIReviewer,
    SimulatedVolunteer,
)

# Sentinel config types: the reviewer class and its cache folder under the cache root. Each provider keeps
# its own folder, and every cache key also holds the provider and the model.
SENTINEL_TYPES = {
    "claude": (ClaudeReviewer, "claude"),
    "claude_code": (ClaudeCodeReviewer, "claude-code"),
    "openai": (OpenAIReviewer, "openai"),
    "gemini": (GeminiReviewer, "gemini"),
    "openai_compatible": (OpenAICompatibleReviewer, "openai-compatible"),
}


@dataclass(frozen=True)
class TargetConfig:
    mission: str
    id: str | None = None
    path: str | None = None
    sectors: tuple[int, ...] | None = None


@dataclass(frozen=True)
class RunConfig:
    name: str
    subject_days: float = 13.0
    min_points: int = 300
    bin_minutes: float = 10.0
    detrend_window_days: float = 1.0
    # "subject": BLS runs on each subject alone (periods up to half a subject).
    # "sector": BLS runs once per target on all its sectors stitched together.
    search: str = "subject"
    min_period: float = 0.5
    fap_trials: int = 20       # block-bootstrap trials for the periodic signal's false-alarm probability
    fap_cache: str | None = None  # null maxima cached here (None: no cache); config files set cache/fap
    # The limb-darkened transit fit of every consensus dip (transitfit.py), and where stellar parameters
    # come from: "tic" (TESS Input Catalog via MAST, cached in cache/tic) or "none" (Sun-like LD, no ρ★ check).
    fit_transits: bool = True
    stellar: str = "none"
    cluster_gap_days: float = 0.05
    min_score: float = 0.5
    min_planet_fraction: float = 0.5
    targets: tuple[TargetConfig, ...] = ()
    reviewers: tuple[dict, ...] = ()
    raw: dict = field(default_factory=dict, compare=False)

    def digest(self) -> str:
        """Hash of the full config. It goes into the run manifest."""
        return hashlib.sha256(json.dumps(self.raw, sort_keys=True, default=str).encode()).hexdigest()


def load_config(path: str | Path) -> RunConfig:
    path = Path(path)
    raw = tomllib.loads(path.read_text())
    run = raw.get("run", {})
    search = raw.get("search", {})
    aggregate = raw.get("aggregate", {})
    search_scope = str(run.get("search", "subject")).lower()
    if search_scope not in ("subject", "sector"):
        raise ValueError(f"run.search must be 'subject' or 'sector', not {search_scope!r}")
    targets = tuple(
        TargetConfig(
            mission=str(t["mission"]).upper(),
            id=t.get("id"),
            path=t.get("path"),
            sectors=tuple(t["sectors"]) if "sectors" in t else None,
        )
        for t in raw.get("targets", [])
    )
    return RunConfig(
        name=run.get("name", path.stem),
        subject_days=float(run.get("subject_days", 13.0)),
        min_points=int(run.get("min_points", 300)),
        bin_minutes=float(run.get("bin_minutes", 10.0)),
        detrend_window_days=float(run.get("detrend_window_days", 1.0)),
        search=search_scope,
        min_period=float(search.get("min_period", 0.5)),
        fap_trials=int(search.get("fap_trials", 20)),
        fap_cache=search.get("fap_cache", "cache/fap") or None,
        fit_transits=bool(search.get("fit_transits", True)),
        stellar=str(search.get("stellar", "none")).lower(),
        cluster_gap_days=float(aggregate.get("cluster_gap_days", 0.05)),
        min_score=float(aggregate.get("min_score", 0.5)),
        min_planet_fraction=float(aggregate.get("min_planet_fraction", 0.5)),
        targets=targets,
        reviewers=tuple(raw.get("reviewers", [])),
        raw=raw,
    )


def build_reviewers(specs, *, cache_root: str | Path = "cache") -> list:
    """Create reviewer objects from ``[[reviewers]]`` entries.

    ``type`` is ``simulated`` (a Probe) or a Sentinel provider: ``claude`` (Anthropic API),
    ``claude_code`` (Claude Code CLI), ``openai``, ``gemini`` or ``openai_compatible``. One panel
    can mix them. Keys are never read from the config, only from the environment.
    """
    reviewers = []
    for spec in specs:
        spec = dict(spec)
        kind = spec.pop("type")
        reviewer_id = spec.pop("id")
        if any(k in spec for k in ("api_key", "key", "token")):
            raise ValueError(f"reviewer {reviewer_id!r}: keys are read from the environment only, never from a "
                             "config file; for an OpenAI-compatible endpoint name the variable with api_key_env")
        if kind == "simulated":
            reviewers.append(SimulatedVolunteer(reviewer_id=reviewer_id, **spec))
        elif kind in SENTINEL_TYPES:
            cls, folder = SENTINEL_TYPES[kind]
            spec.setdefault("cache_dir", str(Path(cache_root) / folder))
            reviewers.append(cls(reviewer_id=reviewer_id, **spec))
        else:
            raise ValueError(f"unknown reviewer type {kind!r}; choose 'simulated' or one of {sorted(SENTINEL_TYPES)}")
    return reviewers

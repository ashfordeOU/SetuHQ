# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""SetuHQ as tools for an AI assistant: the functions the MCP server (``setuhq-mcp``) and the agent example expose.

Each tool is a thin wrapper over a public function of this package (named in its docstring) and returns
one JSON-ready dict:

    {"tool": name, "result": {...}, "provenance": {...}, "honesty": [...]}

``provenance`` says which code ran (version, git describe) and which stored files were read (path and
SHA-256), with the time; ``honesty`` carries the labels a reader needs: a candidate is not a confirmed
planet, a Sentinel is an AI model and not a person (only Claude has been benchmarked), a catalogue
value is someone else's measurement, a FAP is never smaller than its trials resolve. The MCP server adds
no logic of its own; it registers :data:`TOOLS`.

Paths are relative to the data root, ``SETUHQ_ROOT`` (default: this checkout), and must stay inside it:
the server can be reached over HTTP, so a tool never reads or writes outside the root. No tool calls a
paid AI API unless asked to run Sentinels explicitly, and then only with that provider's key in the
environment.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from setuhq import __version__

# ---------------------------------------------------------------- honesty labels

CANDIDATE = ("A candidate, not a discovery: SetuHQ finds and vets dips in public TESS data. Confirming a planet "
             "needs follow-up (radial velocities, imaging, statistical validation) by others.")
PANEL = ("Sentinels are AI models, not people (Claude by default; other providers are labelled). Only Claude has "
         "been benchmarked. Probes are deterministic matched-filter detectors.")
STORED = "Read from stored files; nothing was recomputed."
COMPUTED = "Computed now by SetuHQ's own code from the inputs given; not a stored, reviewed result."
CATALOGUE = ("Catalogue values are the source's measurements, shown as stored; a missing value is not a guess. "
             "SetuHQ did not discover these planets.")
FORMULA = "A textbook formula evaluated as stated; it describes an idealised case, not a measurement."
UNREVIEWED = "No reviewer panel looked at this: it is a detector and vetting output only."

DEFAULT_RUN = "runs/tess-pi-men-s1"
# Where the tools write: one new directory per run, never an existing one, so a stored, reviewed run
# (runs/tess-pi-men-s1) or anything else in the data root can never be overwritten.
TOOL_RUNS = "runs/mcp"
DEFAULT_CATALOGUE = "docs/results/exoplanet_catalogue.json"
MAX_FAP_TRIALS = 2000  # the tool's bound on bootstrap trials, so one call stays minutes, not hours
MAX_ROWS = 200

BENCHMARKS = {
    "real_tois": ("docs/results/benchmark_real_tois_clipfix.json", "Blind benchmark on 662 real TOIs (held-out half), with controls, on the current code."),
    "injection": ("docs/results/injection_recovery_simulated_panel.md", "Injection-recovery of the Probes on synthetic light curves."),
    "pi_men_validation": ("docs/results/pi_men_validation.json", "pi Men c recovered from the stored run, against the archive."),
    "weights": ("docs/results/reviewer_weights_full_panel.calibration.json", "Calibrated reviewer weights and the rates behind them."),
    "leaderboard": ("docs/leaderboard/leaderboard.json", "The real-TOI leaderboard: methods scored on the held-out half, "
                    "ranked by Youden's J, with the metadata-only floor."),
    "threshold_sweep": ("docs/threshold_sweep.json", "The Probe threshold sweep on synthetic injections (search and held-out seeds)."),
}


class ToolError(ValueError):
    """A request the tool cannot serve (a bad path, a missing file, an argument out of range)."""


# ---------------------------------------------------------------- root, paths, provenance


def root() -> Path:
    """The data root: ``SETUHQ_ROOT`` (or the deprecated ``EXOPLAN_ROOT``), else this checkout (where docs/results
    lives), else the working directory."""
    env = os.environ.get("SETUHQ_ROOT") or os.environ.get("EXOPLAN_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parents[2]
    return here if (here / "docs" / "results").is_dir() else Path.cwd().resolve()


def _path(rel: str | os.PathLike, *, must_exist: bool = True) -> Path:
    """A path under the data root; anything that resolves outside it is refused."""
    base = root()
    p = (base / Path(rel)).resolve()
    if p != base and base not in p.parents:
        raise ToolError(f"{rel}: outside the data root; set SETUHQ_ROOT to work elsewhere")
    if must_exist and not p.exists():
        raise ToolError(f"{rel}: no such file in the data root")
    return p


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(root()))
    except ValueError:
        return str(p)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _source(p: Path) -> dict:
    return {"path": _rel(p), "sha256": _sha256(p)} if p.is_file() else {"path": _rel(p)}


@functools.lru_cache(maxsize=1)
def _code() -> str | None:
    from setuhq.pipeline import _git_describe

    return _git_describe()


def envelope(tool: str, result, *, sources: list[dict] = (), honesty: list[str] = ()) -> dict:
    """The one shape every tool returns: the result, where it came from, and how far to trust it."""
    return {
        "tool": tool,
        "result": _plain(result),
        "provenance": {"setuhq_version": __version__, "code": _code(),
                       "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sources": list(sources)},
        "honesty": list(honesty),
    }


def _plain(x):
    """JSON-safe: numpy scalars to floats, NaN and infinities to None, tuples to lists."""
    try:
        import numpy as np

        if isinstance(x, np.generic):
            x = x.item()
        if isinstance(x, np.ndarray):
            x = x.tolist()
    except ImportError:  # pragma: no cover
        pass
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


# ---------------------------------------------------------------- the catalogue


@functools.lru_cache(maxsize=2)
def _catalogue(path: str) -> dict:
    from setuhq.catalogue import load_catalogue

    cat = load_catalogue(_path(path))
    if cat is None:
        raise ToolError(f"{path}: no catalogue")
    return cat


PLANET_FIELDS = ("name", "star", "method", "status", "year", "mass", "msini", "radius", "period", "a", "e", "incl",
                 "teq", "dist", "alt")
STAR_FIELDS = ("star", "sptype", "smass", "srad", "steff", "smet", "sage", "vmag", "dist", "ra", "dec", "salt")


def _row(cat: dict, i: int, fields) -> dict:
    P = cat["planets"]
    return {f: P[f][i] for f in fields if f in P}


def _catalogue_meta(cat: dict, path: str) -> tuple[list[dict], list[str]]:
    src = [_source(_path(path)) | {"source": cat.get("source_name"), "url": cat.get("url"), "fetched_at": cat.get("fetched_at")}]
    return src, [CATALOGUE, f"Units: {json.dumps(cat.get('units', {}))}"]


def search_catalogue(query: str = "", method: str | None = None, limit: int = 20,
                     catalogue_path: str = DEFAULT_CATALOGUE) -> dict:
    """Search the exoplanet catalogue by planet or star name (or alternate name, e.g. a TIC id), optionally by
    discovery method (transit, rv, imaging, microlensing, astrometry, timing). Wraps ``catalogue.catalogue_filter``."""
    from setuhq.catalogue import catalogue_filter

    cat = _catalogue(catalogue_path)
    limit = max(1, min(int(limit), MAX_ROWS))
    hits = catalogue_filter(cat, {"q": query, "methods": [method] if method else []})
    src, honesty = _catalogue_meta(cat, catalogue_path)
    rows = [_row(cat, i, ("name", "star", "method", "year", "period", "radius", "mass", "msini")) for i in hits[:limit]]
    return envelope("search_catalogue", {"query": query, "method": method, "matches": len(hits), "shown": len(rows), "rows": rows},
                    sources=src, honesty=honesty)


def _find(cat: dict, column: str, name: str) -> list[int]:
    want = name.strip().lower()
    col = cat["planets"][column]
    exact = [i for i, v in enumerate(col) if v and v.lower() == want]
    return exact


def get_planet(name: str, catalogue_path: str = DEFAULT_CATALOGUE) -> dict:
    """One planet's stored catalogue record and its host star's (exact name match; use search_catalogue first)."""
    cat = _catalogue(catalogue_path)
    hits = _find(cat, "name", name)
    if not hits:
        raise ToolError(f"no planet named {name!r} in the catalogue; try search_catalogue")
    i = hits[0]
    src, honesty = _catalogue_meta(cat, catalogue_path)
    return envelope("get_planet", {"planet": _row(cat, i, PLANET_FIELDS), "star": _row(cat, i, STAR_FIELDS)},
                    sources=src, honesty=honesty)


def get_star(name: str, catalogue_path: str = DEFAULT_CATALOGUE) -> dict:
    """A host star's stored record and every catalogued planet around it (exact star name)."""
    cat = _catalogue(catalogue_path)
    hits = _find(cat, "star", name)
    if not hits:
        raise ToolError(f"no star named {name!r} in the catalogue; try search_catalogue")
    src, honesty = _catalogue_meta(cat, catalogue_path)
    planets = [_row(cat, i, ("name", "method", "year", "period", "radius", "mass", "msini", "a", "e")) for i in hits]
    return envelope("get_star", {"star": _row(cat, hits[0], STAR_FIELDS), "planets": planets}, sources=src, honesty=honesty)


# ---------------------------------------------------------------- a stored run


def _run_files(run_dir: str) -> tuple[Path, dict, list[dict]]:
    run = _path(run_dir)
    manifest_p, cands_p = run / "manifest.json", run / "candidates.json"
    if not manifest_p.exists() or not cands_p.exists():
        raise ToolError(f"{run_dir}: not a run directory (no manifest.json and candidates.json)")
    return run, json.loads(manifest_p.read_text()), json.loads(cands_p.read_text())


def _run_provenance(manifest: dict) -> dict:
    from setuhq.names import reviewer_provenance

    keys = ("setuhq_version", "created_at", "config_name", "config_sha256", "search_scope", "claude_prompt_version",
            "weights_source", "skipped_reviewers")
    out = {k: manifest.get(k) for k in keys if k in manifest}
    if "setuhq_version" not in out and "exoplan_version" in manifest:  # a run from before the rename
        out["setuhq_version"] = manifest["exoplan_version"]
    out["inputs"] = manifest.get("inputs", [])  # each light curve as the run recorded it (source, sector, file hash)
    out["reviewers"] = [{k: r.get(k) for k in ("id", "kind", "weight", "calibration", "provider", "model", "persona") if k in r}
                        for r in manifest.get("reviewers", [])]
    out["sentinels"] = reviewer_provenance(manifest)
    return out


CANDIDATE_FIELDS = ("candidate_id", "target", "mission", "time_unit", "t_center", "duration_hours", "depth_ppm", "snr",
                    "period_days", "n_transits", "passed", "flags", "score", "n_reviewers", "planet_fraction", "reviewers",
                    "fap", "fap_label", "fap_tail_label")


def list_candidates(run_dir: str = DEFAULT_RUN, passed_only: bool = False) -> dict:
    """The consensus dips of a stored run, with whether each passed vetting and its flags (``candidates.json``)."""
    run, manifest, cands = _run_files(run_dir)
    rows = [{k: c.get(k) for k in CANDIDATE_FIELDS} for c in cands if c.get("passed") or not passed_only]
    return envelope("list_candidates", {"run": _rel(run), "n": len(rows), "candidates": rows},
                    sources=[_source(run / "candidates.json"), _source(run / "manifest.json")],
                    honesty=[STORED, CANDIDATE, PANEL])


def get_candidate(candidate_id: str, run_dir: str = DEFAULT_RUN) -> dict:
    """One consensus dip with its full provenance: the stored candidate (vetting, fit, FAP, each reviewer's mark
    audit), the run manifest (code, config hash, inputs with SHA-256, reviewers with provider and model) and every
    reviewer's stored classification of its subject (label, marks, rationale, provider, model)."""
    import csv

    run, manifest, cands = _run_files(run_dir)
    c = next((x for x in cands if x.get("candidate_id") == candidate_id), None)
    if c is None:
        raise ToolError(f"no candidate {candidate_id!r} in {run_dir}; see list_candidates")
    reviews = []
    cl = run / "classifications.csv"
    if cl.exists():
        with cl.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row["subject_ids"] != c["subject_id"]:
                    continue
                meta = json.loads(row["metadata"] or "{}")
                tasks = {t["task"]: t["value"] for t in json.loads(row["annotations"])}
                reviews.append({"reviewer": row["user_name"], "label": row["label"],
                                "marks": [[m["t_start"], m["t_end"]] for m in tasks.get("T0", [])],
                                "reason": meta.get("reason"), "confidence": meta.get("confidence"),
                                "rationale": meta.get("rationale"),
                                **{k: meta[k] for k in ("provider", "model", "called_at", "prompt_version") if k in meta}})
    sources = [_source(run / "candidates.json"), _source(run / "manifest.json")] + ([_source(cl)] if cl.exists() else [])
    honesty = [STORED, CANDIDATE, PANEL]
    if c.get("passed") is False:
        honesty.append("This dip did not pass vetting: " + (c.get("flags") or "see flags"))
    return envelope("get_candidate", {"candidate": c, "run": _run_provenance(manifest), "reviews": reviews},
                    sources=sources, honesty=honesty)


# ---------------------------------------------------------------- light curves in


def _lightcurve(csv_path: str | None, time, flux, flux_err, target: str):
    import numpy as np

    from setuhq.lightcurve import LightCurve
    from setuhq.loaders import load_csv

    if csv_path:
        p = _path(csv_path)
        return load_csv(p, target=target), [_source(p)]
    if time is None or flux is None:
        raise ToolError("give csv_path (columns time, flux[, flux_err]) or the time and flux arrays")
    t, f = np.asarray(time, float), np.asarray(flux, float)
    if t.shape != f.shape or t.size < 20:
        raise ToolError("time and flux must be arrays of the same length, at least 20 points")
    level = float(np.nanmedian(f))
    e = np.asarray(flux_err, float) / level if flux_err is not None else np.full_like(f, float(np.nanstd(f / level)))
    digest = hashlib.sha256(t.tobytes() + f.tobytes()).hexdigest()
    lc = LightCurve(target=target, mission="custom", time=t, flux=f / level, flux_err=e,
                    provenance={"source": "arrays passed to the tool", "sha256": digest, "time_unit": "as supplied"})
    return lc, [{"path": "arrays passed to the tool", "sha256": digest}]


def _subject(lc, *, detrend_window_days: float, bin_minutes: float):
    """The light curve prepared as the pipeline prepares it (clean, normalise, detrend, bin), as one series."""
    from setuhq.config import RunConfig
    from setuhq.pipeline import prepare_lightcurves
    from setuhq.search import stitch

    cfg = RunConfig(name="tool", detrend_window_days=detrend_window_days, bin_minutes=bin_minutes)
    prepared = [p for p in prepare_lightcurves([lc], cfg) if len(p)]
    if not prepared:
        raise ToolError("no usable points after cleaning")
    return stitch(prepared, subject_id=f"tool-{lc.target}")


def _signal_dict(s) -> dict | None:
    if s is None:
        return None
    return {"period_days": s.period, "t0": s.t0, "duration_hours": s.duration * 24, "depth_ppm": s.depth * 1e6, "snr": s.snr,
            "n_transits": s.n_transits, "odd_depth_ppm": s.odd_depth * 1e6, "even_depth_ppm": s.even_depth * 1e6,
            "secondary_depth_ppm": s.secondary_depth * 1e6}


FLAG_MEANINGS = {
    "insufficient_points": "fewer than two points inside the dip",
    "low_snr": "the dip's SNR is below 7",
    "too_short": "shorter than 15 minutes",
    "edge_event": "within 0.1 d of a data edge (reported, not disqualifying)",
    "odd_even_mismatch": "odd and even transits differ in depth by more than 3σ (an eclipsing binary at twice the period?)",
    "secondary_eclipse": "a dip at phase 0.5 above 3σ (an eclipsing binary?)",
}


def vet_lightcurve(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                   flux_err: list[float] | None = None, t_start: float | None = None, t_end: float | None = None,
                   target: str = "custom", min_period: float = 0.5, detrend_window_days: float = 1.0,
                   bin_minutes: float = 10.0) -> dict:
    """Search a light curve for a periodic transit (BLS, ``search.bls_search``) and vet one dip with SetuHQ's
    vetting (``vet.vet_event``: SNR, duration, edges, odd/even depths, secondary eclipse). Give the dip as
    t_start/t_end, or leave them out to vet the strongest periodic signal's first transit. The light curve is
    prepared as the pipeline prepares it (clean, detrend, bin)."""
    from setuhq.search import bls_search
    from setuhq.vet import vet_event

    lc, sources = _lightcurve(csv_path, time, flux, flux_err, target)
    subject = _subject(lc, detrend_window_days=detrend_window_days, bin_minutes=bin_minutes)
    signal = bls_search(subject, min_period=min_period)
    if t_start is None or t_end is None:
        if signal is None:
            raise ToolError("no periodic signal to vet; give t_start and t_end of the dip")
        first = signal.t0 + math.ceil((subject.start - signal.t0) / signal.period) * signal.period
        t_start, t_end = first - signal.duration / 2, first + signal.duration / 2
    if not t_end > t_start:
        raise ToolError("t_end must be after t_start")
    centre = 0.5 * (t_start + t_end)
    periodic = signal if signal is not None and signal.covers(centre) else None
    v = vet_event(t_start, t_end, subject, periodic)
    result = {"window": [t_start, t_end], "passed": v.passed, "flags": list(v.flags),
              "flag_meanings": {f: FLAG_MEANINGS.get(f, f) for f in v.flags}, "metrics": v.metrics,
              "periodic_signal": _signal_dict(signal), "on_periodic_ephemeris": periodic is not None,
              "n_points": len(subject), "time_unit": lc.provenance.get("time_unit")}
    return envelope("vet_lightcurve", result, sources=sources, honesty=[COMPUTED, UNREVIEWED, CANDIDATE])


def fit_transit(t0: float, duration_hours: float, depth_ppm: float, csv_path: str | None = None,
                time: list[float] | None = None, flux: list[float] | None = None, flux_err: list[float] | None = None,
                period_days: float | None = None, teff: float | None = None, logg: float | None = None,
                stellar_density: float | None = None, target: str = "custom", detrend_window_days: float = 1.0,
                bin_minutes: float = 10.0) -> dict:
    """Fit SetuHQ's limb-darkened transit model (``transitfit.fit_transit``) around one transit: depth, T14,
    impact parameter b, mid-time, Rp/R★ and the transit density ρ★, each with its error and range. Limb darkening
    from Claret 2017 for the star's Teff and log g (Sun-like when not given). t0, duration and depth are guesses."""
    from setuhq.transitfit import fit_transit as _fit
    from setuhq.transitfit import ld_coeffs

    lc, sources = _lightcurve(csv_path, time, flux, flux_err, target)
    subject = _subject(lc, detrend_window_days=detrend_window_days, bin_minutes=bin_minutes)
    u1, u2 = ld_coeffs(teff, logg)
    fit = _fit(subject.time, subject.flux, subject.flux_err, t0=t0, duration=duration_hours / 24.0,
               depth=max(depth_ppm, 20.0) * 1e-6, period=period_days, u1=u1, u2=u2, stellar_density=stellar_density)
    result = {"fit": fit.as_dict() if fit is not None else None, "limb_darkening": {"u1": u1, "u2": u2,
              "source": "Claret 2017 TESS (log g, Teff)" if teff else "Sun-like default (no Teff given)"}}
    if fit is None:
        result["note"] = "too few points around t0 to fit"
    return envelope("fit_transit", result, sources=sources,
                    honesty=[COMPUTED, "Fit errors come from the fit's covariance; ranges show where the likelihood allows more.",
                             CANDIDATE])


def compute_fap(csv_path: str | None = None, time: list[float] | None = None, flux: list[float] | None = None,
                flux_err: list[float] | None = None, n_trials: int = 200, min_period: float = 0.5, seed: int = 0,
                target: str = "custom", detrend_window_days: float = 1.0, bin_minutes: float = 10.0) -> dict:
    """The empirical false-alarm probability of the strongest periodic signal (``search.false_alarm_probability``):
    block-bootstrap BLS reruns that keep red noise. Bounded: with N trials it is never reported below 1/(N + 1),
    and the Gumbel tail is labelled indicative. N is capped at 2000 per call."""
    from setuhq.search import bls_search, false_alarm_probability, fap_label, fap_tail_label

    n = int(n_trials)
    if not 1 <= n <= MAX_FAP_TRIALS:
        raise ToolError(f"n_trials must be 1 to {MAX_FAP_TRIALS}")
    lc, sources = _lightcurve(csv_path, time, flux, flux_err, target)
    subject = _subject(lc, detrend_window_days=detrend_window_days, bin_minutes=bin_minutes)
    signal = bls_search(subject, min_period=min_period)
    if signal is None:
        raise ToolError("no periodic signal to test (the light curve is too short for the period range)")
    r = false_alarm_probability(subject, signal, min_period=min_period, n_trials=n, seed=seed, workers=1)
    result = {"signal": _signal_dict(signal), "fap": r.fap, "fap_label": fap_label(r.fap, r.n_trials, r.bound),
              "upper_bound": r.bound, "trials": r.n_trials, "trials_at_or_above": r.exceed,
              "gumbel_tail": r.tail, "gumbel_tail_label": fap_tail_label(r.tail), "method": r.method}
    honesty = [COMPUTED, "The FAP is (k + 1)/(N + 1) over N block-bootstrap trials: never reported below 1/(N + 1)."]
    if r.bound:
        honesty.append(f"No trial reached the signal: the FAP is an upper bound (< {r.fap:.1e}), not a value.")
    return envelope("compute_fap", result, sources=sources, honesty=honesty)


# ---------------------------------------------------------------- running the pipeline


def _panel(config_path: str, sentinels: bool):
    from setuhq.config import SENTINEL_TYPES, build_reviewers, load_config

    config = load_config(_path(config_path))
    specs = [s for s in config.reviewers if sentinels or s.get("type") not in SENTINEL_TYPES]
    if not specs:
        raise ToolError(f"{config_path}: no reviewers left (Probes only, and the config has none)")
    return config, build_reviewers(specs, cache_root=root() / "cache")


def _new_run_dir(run_name: str, base_rel: str = TOOL_RUNS) -> Path:
    """A fresh directory <base_rel>/<run_name> (runs/mcp by default) under the data root. Refused if the name is
    not a plain name or the directory already exists: a tool run adds, it never replaces."""
    import re

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", run_name or "") or ".." in run_name:
        raise ToolError("run_name must be a plain name (letters, digits, '.', '_', '-'), not a path")
    base = root()
    # Never follow a link: a symlinked runs/ or runs/mcp/, or anything already at the name (a dangling
    # symlink included), could redirect the run outside runs/mcp.
    for rel in ("runs", base_rel):
        try:
            st = os.lstat(base / rel)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise ToolError(f"{rel} is a link or not a directory; tool runs are refused until it is a plain directory")
    try:
        os.lstat(base / base_rel / run_name)
    except FileNotFoundError:
        pass
    else:
        raise ToolError(f"{base_rel}/{run_name} already exists; a tool run never overwrites, pick a new run_name")
    out = _path(f"{base_rel}/{run_name}", must_exist=False)
    try:
        out.mkdir(parents=True, exist_ok=False)  # atomic: two calls cannot both claim one directory
    except FileExistsError:
        raise ToolError(f"{base_rel}/{run_name} already exists; a tool run never overwrites, pick a new run_name") from None
    return out


def _run_summary(summary, out: Path, config_path: str) -> dict:
    manifest = json.loads((out / "manifest.json").read_text())
    return {
        "run_dir": _rel(out), "config": config_path,
        "counts": manifest["counts"], "skipped_reviewers": manifest.get("skipped_reviewers_detail", []),
        "reviewers": [{k: r.get(k) for k in ("id", "kind", "weight", "calibration", "provider", "model") if k in r}
                      for r in manifest["reviewers"]],
        "candidates": [{k: c.as_row().get(k) for k in CANDIDATE_FIELDS} for c in summary.candidates],
    }


def run_pipeline_csv(csv_path: str, run_name: str, target: str = "custom", config_path: str = "configs/default.toml",
                     sentinels: bool = False) -> dict:
    """Run the full pipeline (``pipeline.run_pipeline``) on a CSV light curve (time, flux[, flux_err]) and write
    a new run directory, runs/mcp/<run_name> (refused if it exists: nothing is ever overwritten). Probes only
    unless sentinels=True; Sentinels then run only where their key, SDK or CLI is present (the manifest lists
    the skipped ones and why)."""
    from setuhq.loaders import load_csv
    from setuhq.pipeline import run_pipeline

    p = _path(csv_path)
    out = _new_run_dir(run_name)
    config, reviewers = _panel(config_path, sentinels)
    summary = run_pipeline(config, [load_csv(p, target=target)], reviewers, out, weights_source="uniform 1.0 (tool run)")
    return envelope("run_pipeline_csv", _run_summary(summary, out, config_path),
                    sources=[_source(p), _source(_path(config_path))],
                    honesty=[COMPUTED, CANDIDATE, PANEL, "Uniform weights: no calibrated weights were applied to this run."])


def run_pipeline_tess(tic: str, run_name: str, sectors: list[int] | None = None, config_path: str = "configs/default.toml",
                      sentinels: bool = False) -> dict:
    """Download a TESS SPOC light curve from MAST (``loaders.load_tess``; needs network and ``pip install -e '.[tess]'``)
    for a TIC id and sectors, and run the pipeline on it into a new runs/mcp/<run_name> (never an existing
    directory). Probes only unless sentinels=True."""
    from setuhq.loaders import load_tess
    from setuhq.pipeline import run_pipeline

    tic_id = tic if str(tic).upper().startswith("TIC") else f"TIC {tic}"
    out = _new_run_dir(run_name)
    config, reviewers = _panel(config_path, sentinels)
    try:
        lightcurves = load_tess(tic_id, tuple(sectors) if sectors else None)
    except ImportError as exc:
        raise ToolError(f"TESS downloads need lightkurve: pip install -e '.[tess]' ({exc})") from exc
    summary = run_pipeline(config, lightcurves, reviewers, out, weights_source="uniform 1.0 (tool run)")
    inputs = [{"path": lc.provenance.get("file"), "sha256": lc.provenance.get("file_sha256"), "sector": lc.provenance.get("sector")}
              for lc in lightcurves]
    return envelope("run_pipeline_tess", _run_summary(summary, out, config_path), sources=inputs + [_source(_path(config_path))],
                    honesty=[COMPUTED, CANDIDATE, PANEL, "Uniform weights: no calibrated weights were applied to this run."])


# ---------------------------------------------------------------- Methods physics


def rv_semi_amplitude(period_days: float, planet_mass_mjup: float, star_mass_msun: float, eccentricity: float = 0.0,
                      sin_i: float = 1.0) -> dict:
    """The radial-velocity semi-amplitude K (m/s) of a star with one planet (``methods.rv_semi_amplitude``)."""
    from setuhq.methods import rv_semi_amplitude as _k

    if not (period_days > 0 and planet_mass_mjup > 0 and star_mass_msun > 0 and 0 <= eccentricity < 1):
        raise ToolError("need period > 0, masses > 0 and 0 <= e < 1")
    k = _k(period_days, planet_mass_mjup, star_mass_msun, eccentricity, sin_i)
    return envelope("rv_semi_amplitude", {"K_m_s": k, "equation": "K = (2πG/P)^(1/3) · Mp sin i / (M★ + Mp)^(2/3) / √(1 − e²)"},
                    honesty=[FORMULA, "IAU 2015 nominal GM values (Prša et al. 2016)."])


def transit_depth(radius_ratio: float | None = None, planet_radius_rearth: float | None = None,
                  star_radius_rsun: float | None = None, teff: float | None = None) -> dict:
    """The depth of a central transit: (Rp/R★)² geometrically, and with TESS quadratic limb darkening for the
    star's Teff (``methods.transit_flux`` at z = 0, Claret 2017 coefficients). Give Rp/R★, or Rp in Earth radii
    and R★ in solar radii."""
    from setuhq.methods import R_EARTH, R_SUN, ld_coeffs, transit_flux

    if radius_ratio is None:
        if not (planet_radius_rearth and star_radius_rsun):
            raise ToolError("give radius_ratio, or planet_radius_rearth and star_radius_rsun")
        radius_ratio = planet_radius_rearth * R_EARTH / (star_radius_rsun * R_SUN)
    if not 0 < radius_ratio < 1:
        raise ToolError("Rp/R★ must be between 0 and 1")
    result = {"radius_ratio": radius_ratio, "geometric_depth_ppm": radius_ratio ** 2 * 1e6}
    if teff:
        u1, u2 = ld_coeffs(teff)
        result |= {"limb_darkened_depth_ppm": (1 - transit_flux(0.0, radius_ratio, u1, u2)) * 1e6, "u1": u1, "u2": u2}
    return envelope("transit_depth", result, honesty=[FORMULA, "Small-planet approximation (Mandel & Agol 2002, §5)."])


def microlensing_magnification(u: float) -> dict:
    """The point-lens magnification A(u) = (u² + 2) / (u √(u² + 4)) at impact parameter u, in Einstein radii
    (``methods.paczynski``)."""
    from setuhq.methods import paczynski

    if not u > 0:
        raise ToolError("u must be > 0")
    return envelope("microlensing_magnification", {"u": u, "A": paczynski(u)}, honesty=[FORMULA])


def habitable_zone(teff: float, luminosity_lsun: float) -> dict:
    """The habitable zone's edges in AU for a star (``methods.hz_distance_au``, Kopparapu et al. 2014, 1 M⊕):
    recent Venus and runaway greenhouse (inner), maximum greenhouse and early Mars (outer)."""
    from setuhq.methods import KOPPARAPU, hz_distance_au, hz_seff

    if not (2600 <= teff <= 7200 and luminosity_lsun > 0):
        raise ToolError("the fit holds for 2600 K <= Teff <= 7200 K; luminosity must be > 0")
    limits = {k: {"distance_au": hz_distance_au(k, teff, luminosity_lsun), "s_eff": hz_seff(k, teff)} for k in KOPPARAPU}
    return envelope("habitable_zone", {"teff": teff, "luminosity_lsun": luminosity_lsun, "limits": limits},
                    honesty=[FORMULA, "For a 1 Earth-mass planet; says nothing about whether a planet there is habitable."])


# ---------------------------------------------------------------- results and the panel


def benchmark_results(which: str = "real_tois") -> dict:
    """A stored benchmark or validation result: real_tois (the blind 662-TOI benchmark), leaderboard (the real-TOI
    leaderboard), injection (Probes' injection-recovery), pi_men_validation, weights (calibration) or
    threshold_sweep (synthetic, not the leaderboard). Returned as stored."""
    if which not in BENCHMARKS:
        raise ToolError(f"which must be one of {sorted(BENCHMARKS)}")
    rel, what = BENCHMARKS[which]
    p = _path(rel)
    data = json.loads(p.read_text()) if p.suffix == ".json" else {"markdown": p.read_text()}
    if which == "real_tois":  # the summary and the Sentinels, not 662 per-star rows
        data = {k: data.get(k) for k in ("generated_at", "sample", "panel", "stars_run", "summary", "sentinels",
                                         "feed_implication", "code_commit", "threshold_audit")}
    return envelope("benchmark_results", {"which": which, "what": what, "data": data}, sources=[_source(p)],
                    honesty=[STORED, PANEL, "Benchmarks state their sample and method; read them before quoting a rate."])


def sentinel_providers() -> dict:
    """The Sentinel providers SetuHQ supports, how each is configured, and whether it can run here (its key
    variable is set, its SDK or CLI is present). Never returns a key."""
    import importlib.util
    import shutil

    from setuhq.reviewers import KEY_ENV, PROVIDER_LABELS

    rows = [
        {"type": "claude", "provider": "anthropic", "key_env": KEY_ENV["anthropic"], "needs": "pip install -e '.[claude]'",
         "ready": bool(os.environ.get(KEY_ENV["anthropic"])) and importlib.util.find_spec("anthropic") is not None},
        {"type": "claude_code", "provider": "claude-code", "key_env": None, "needs": "the claude CLI, signed in",
         "ready": shutil.which("claude") is not None},
        {"type": "openai", "provider": "openai", "key_env": KEY_ENV["openai"], "needs": "nothing (plain HTTPS)",
         "ready": bool(os.environ.get(KEY_ENV["openai"]))},
        {"type": "gemini", "provider": "gemini", "key_env": KEY_ENV["gemini"], "needs": "nothing (plain HTTPS)",
         "ready": bool(os.environ.get(KEY_ENV["gemini"]))},
        {"type": "openai_compatible", "provider": "openai-compatible", "key_env": "named by api_key_env (none for a local server)",
         "needs": "base_url of the endpoint", "ready": None},
    ]
    for r in rows:
        r["label"] = PROVIDER_LABELS[r["provider"]]
    return envelope("sentinel_providers", {"providers": rows, "default": "claude_code (Claude, Anthropic)",
                                           "benchmarked": ["Claude (Claude Code CLI): two personas on the 40-star subsample"]},
                    honesty=[PANEL, "An uncalibrated provider votes at the floor weight until 'setuhq calibrate' measures it."])


# ---------------------------------------------------------------- proposal preparation

PROPOSE_RUNS = "runs/propose"


def cheops_proposal_pack(target: str, run_name: str, programme: str = "regular", orbits: int | None = None,
                         cycle: str | None = None, gmag: float | None = None, event: str = "transit",
                         depth_ppm: float | None = None, duration_hours: float | None = None, target_snr: float = 10.0,
                         efficiency: float = 0.7, offline: bool = False) -> dict:
    """Write a CHEOPS Guest Observers proposal PREPARATION pack (``propose.pack.build_pack``) into a new
    runs/propose/<run_name> (refused if it exists; nothing outside it is written, no cache): the Running Call's rules
    check (orbit limits, April/October rule for Large programmes, the next deadline in Paris time, earliest start),
    the target's status (public Reserved Target List, public CHEOPS archive metadata, SIMBAD/MAST J2000
    coordinates), SetuHQ's stored evidence, rough precision and orbit ESTIMATES, anonymised drafts with an anonymity
    lint, and ESA's step-by-step checklist. Reads public pages only; never logs in or submits. SetuHQ is independent
    of ESA and the CHEOPS mission: the official call and ESA's tools govern."""
    from setuhq.propose import draft, pack, rules, sources

    try:
        rules.programme(programme)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    if event not in ("transit", "eclipse", "flare"):
        raise ToolError("event must be transit, eclipse or flare")
    out = _new_run_dir(run_name, PROPOSE_RUNS)  # claimed atomically; build_pack fills the empty directory
    try:
        p = pack.build_pack(target, out, root=root(), claimed=True, programme=programme, orbits=orbits, cycle=cycle,
                            fetcher=sources.Fetcher(cache_dir=None, offline=offline), gmag=gmag, event=event,
                            depth_ppm=depth_ppm, duration_hours=duration_hours, target_snr=target_snr,
                            efficiency=efficiency, use_toi_table=not offline)
    except ValueError as exc:
        if out.is_dir() and not any(out.iterdir()):
            out.rmdir()  # nothing was written: give the name back
        raise ToolError(str(exc)) from None
    result = {"pack_dir": _rel(out), "files": sorted(_rel(f) for f in out.rglob("*") if f.is_file()),
              "cycle": p["cycle"], "programme": p["programme"], "target": p["target"], "status": p["status"],
              "planning": p["planning"], "anonymity_warnings": sum(f["level"] == "warn" for f in p["anonymity_lint"]),
              "network_errors": p["network_errors"]}
    return envelope("cheops_proposal_pack", result, sources=p["sources"],
                    honesty=[draft.DISCLAIMER, draft.PREP_ONLY, CANDIDATE, *p["honesty"][3:]])


# What the MCP server registers, in this order. read_only: the tool writes nothing.
TOOLS = [
    (search_catalogue, True), (get_planet, True), (get_star, True),
    (list_candidates, True), (get_candidate, True),
    (vet_lightcurve, True), (fit_transit, True), (compute_fap, True),
    (run_pipeline_csv, False), (run_pipeline_tess, False),
    (rv_semi_amplitude, True), (transit_depth, True), (microlensing_magnification, True), (habitable_zone, True),
    (benchmark_results, True), (sentinel_providers, True),
    (cheops_proposal_pack, False),
]

# The stellar tools (flares, pulsations, CHEOPS): setuhq.stellar_tools, imported last (it uses the helpers above).
from setuhq.stellar_tools import STELLAR_TOOLS  # noqa: E402

TOOLS += STELLAR_TOOLS

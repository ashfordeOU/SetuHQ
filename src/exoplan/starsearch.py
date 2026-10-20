"""One star-sector of the all-sky sweep: read the SPOC file, run the panel, classify everything that dims.

This is the part of the sweep whose code changes results, so it is in the code fingerprint
(:data:`CODE_FILES`, :func:`code_fingerprint`) that every sweep record and contribution bundle carries.
The orchestration (target lists, downloads, resuming) is in :mod:`exoplan.sweep` and is not.

Per star-sector:

1. Read the SPOC 2-minute light-curve file: PDCSAP flux, points with TESS quality 0 only, normalised to
   the median (the same rule as ``loaders.load_tess``), and the instrumental cues from the full cadence
   list (momentum dumps, scattered-light flags, gaps; :func:`exoplan.variables.quality_events`).
2. Run the pipeline with the sweep config, which sets ``aggregate.min_planet_fraction = 0`` so every
   consensus dip is kept, whatever the panel's label (the classifier applies the potential-planet share).
3. Classify every dip, brightening and the out-of-transit variability (:mod:`exoplan.variables`).
4. Measure each class's null on this exact star (:func:`null_counts`): the dip classes on the flux-inverted
   copy, flares as downward events with the real dips masked, variability on a block-shuffled copy.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from exoplan import __version__
from exoplan.lightcurve import LightCurve
from exoplan.variables import quality_events, star_entries

ROOT = Path(__file__).resolve().parents[2]
# The code a sweep result depends on: the pipeline (as the benchmark's fingerprint), the reviewers and the
# image they see, the classification store, the classifier and this file.
CODE_FILES = ["discover.py", "aggregate.py", "config.py", "lightcurve.py", "loaders.py", "pipeline.py", "preprocess.py",
              "search.py", "subjects.py", "transitfit.py", "vet.py", "render.py", "store.py", "variables.py", "starsearch.py",
              "reviewers/base.py", "reviewers/simulated.py", "reviewers/claude.py", "reviewers/claude_code.py"]
DEFAULT_WEIGHTS = "docs/results/reviewer_weights_full_panel.json"


# Two parts, so a change to the rules alone can be re-applied to stored runs with honest provenance: the search
# (everything up to the panel's consensus dips and their vetting) and the classification (the rules).
CLASSIFY_FILES = ["variables.py"]
SEARCH_FILES = [f for f in CODE_FILES if f not in CLASSIFY_FILES]


def _fingerprint(files, src=None, read=None) -> str:
    src = Path(src) if src else Path(__file__).resolve().parent
    h = hashlib.sha256()
    for f in files:
        h.update(f.encode() + b"\0" + (read(f) if read else (src / f).read_bytes()) + b"\0")
    return h.hexdigest()


def code_fingerprint(src: str | Path | None = None, read=None) -> str:
    """sha256 over :data:`CODE_FILES` (path and bytes of each), as in this checkout (or as ``read(f)`` returns them)."""
    return _fingerprint(CODE_FILES, src, read)


def search_fingerprint(src: str | Path | None = None, read=None) -> str:
    """sha256 over :data:`SEARCH_FILES`: the code that made the dips, marks and vetting."""
    return _fingerprint(SEARCH_FILES, src, read)


def classify_fingerprint(src: str | Path | None = None, read=None) -> str:
    """sha256 over :data:`CLASSIFY_FILES`: the classification rules."""
    return _fingerprint(CLASSIFY_FILES, src, read)


def record_codes(rec: dict) -> tuple[str | None, str | None]:
    """A record's (search code, classification code); a record from before the split names one code for both."""
    return rec.get("search_code") or rec.get("code"), rec.get("classify_code") or rec.get("code")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_spoc(path: str | Path, tic: int, sector: int) -> tuple[LightCurve, dict, dict]:
    """A SPOC light-curve file as a normalised :class:`LightCurve` (quality 0 only), its instrumental cues,
    and the header's star values (TIC Teff, log g, radius, Tmag, position), read offline."""
    from astropy.io import fits

    path = Path(path)
    with fits.open(path) as hdul:
        hdr0 = hdul[0].header
        d = hdul[1].data
        t = np.asarray(d["TIME"], dtype=float)
        fl = np.asarray(d["PDCSAP_FLUX"], dtype=float)
        fe = np.asarray(d["PDCSAP_FLUX_ERR"], dtype=float)
        q = np.asarray(d["QUALITY"], dtype=np.int64)
    good = (q == 0) & np.isfinite(t) & np.isfinite(fl) & np.isfinite(fe)
    if good.sum() < 100:
        raise ValueError(f"only {int(good.sum())} good cadences")
    median = float(np.median(fl[good]))
    star = {k: _hv(hdr0, h) for k, h in (("teff", "TEFF"), ("logg", "LOGG"), ("radius", "RADIUS"), ("tmag", "TESSMAG"),
                                         ("ra", "RA_OBJ"), ("dec", "DEC_OBJ"))}
    lc = LightCurve(target=f"TIC {int(tic)}", mission="TESS", time=t[good], flux=fl[good] / median, flux_err=fe[good] / median,
                    provenance={"source": "MAST", "author": "SPOC", "sector": int(sector), "exptime_s": 120, "flux_column": "pdcsap_flux",
                                "time_unit": "BTJD", "file": path.name, "file_sha256": sha256_file(path)})
    return lc, quality_events(t, q, good), star


def _hv(hdr, key):
    v = hdr.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def stellar_json(star: dict, target: str) -> dict:
    """The fit's stellar parameters from the file header: Teff and log g for limb darkening, and ρ★ from
    log g and R★ (no error, so no density prior). Written as the run's stellar.json, so no TIC query is made."""
    out = {"teff": star.get("teff"), "logg": star.get("logg"), "radius": star.get("radius"), "source": "SPOC file header (TIC)"}
    if star.get("logg") and star.get("radius"):
        g = 10 ** star["logg"] / 100.0
        r = star["radius"] * 6.957e8
        out["rho"] = 3 * g / (4 * math.pi * 6.67430e-11 * r) / 1000.0
    return {target: out}


def panel_weights(config, path: str | Path | None = DEFAULT_WEIGHTS) -> tuple[dict, str]:
    """Each reviewer's calibrated weight from ``path`` where it has one, else 1.0; and where they came from."""
    stored = json.loads(Path(path).read_text()) if path and Path(path).exists() else {}
    ids = [str(s["id"]) for s in config.reviewers]
    w = {i: float(stored[i]) if i in stored else 1.0 for i in ids}
    have = [i for i in ids if i in stored]
    src = (f"{path} for {', '.join(have)}" if have else "") + ("; " if have and len(have) < len(ids) else "") + \
          (f"uniform 1.0 for {', '.join(i for i in ids if i not in stored)}" if len(have) < len(ids) else "")
    return w, src


def search_star(path: str | Path, *, tic: int, sector: int, config, reviewers, weights: dict, weights_source: str,
                run_root: str | Path, toi_target=None, control: bool = True, codes: tuple | None = None) -> dict:
    """Run one star-sector and return its sweep record (coverage, entries, rejections, control)."""
    from exoplan.aggregate import aggregate
    from exoplan.benchmark_toi import inverted
    from exoplan.pipeline import run_pipeline
    from exoplan.store import read_classifications_csv

    started = time.monotonic()
    lc, events, star = read_spoc(path, tic, sector)
    run_dir = Path(run_root) / f"tic{int(tic)}-s{int(sector)}"
    for sub in ("real", "inverted"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
        # The pipeline reads a run directory's stellar.json before any TIC query (pipeline.star_parameters).
        (run_dir / sub / "stellar.json").write_text(json.dumps(stellar_json(star, lc.target), indent=1))
    summary = run_pipeline(config, [lc], reviewers, run_dir / "real", weights=weights, weights_source=weights_source)
    res = star_entries(run_dir / "real", tic=tic, sector=sector, time=lc.time, flux=lc.flux, events=events)
    clfs = read_classifications_csv(run_dir / "real" / "classifications.csv")
    clusters = aggregate(clfs, weights, gap_days=config.cluster_gap_days, min_score=0.0, min_planet_fraction=0.0)
    below = sum(1 for c in clusters if c.score < config.min_score)
    entries = res["entries"]
    _match_tois(entries, toi_target)
    record = {
        "tic": int(tic), "sector": int(sector), "status": "searched",
        "ra": star.get("ra"), "dec": star.get("dec"), "tmag": star.get("tmag"), "teff": star.get("teff"), "radius": star.get("radius"),
        "file": lc.provenance["file"], "file_sha256": lc.provenance["file_sha256"], "n_points": int(len(lc)),
        "n_subjects": summary.n_subjects, "n_classifications": summary.n_classifications,
        "n_marks": sum(len(c.marks) for c in clfs), "n_dips": res["n_dips"],
        "rejected": {"below_consensus": below, "failed_vetting": sum(1 for e in entries if e["kind"] == "dip" and not e["passed"]),
                     "dips_not_planet_candidate": sum(1 for e in entries if e["kind"] == "dip" and e["class"] != "planet_candidate")},
        "counts": res["counts"], "events": events, "variability": res["variability"], "entries": entries,
        "tois": [{"toi": t.name, "disposition": t.disposition, "period_days": t.period} for t in (toi_target.tois if toi_target else [])],
        "reviewers": [{"id": r.reviewer_id, "kind": r.kind, "weight": weights.get(r.reviewer_id, 1.0),
                       **({"model": getattr(r, "model", None)} if getattr(r, "model", None) else {})} for r in reviewers if r.available()],
        "skipped_reviewers": summary.skipped_reviewers, "weights_source": weights_source,
        "config_sha256": config.digest(), "exoplan_version": __version__,
        "search_code": (codes or (search_fingerprint(),))[0], "classify_code": (codes or (None, classify_fingerprint()))[1],
    }
    if control:
        run_pipeline(config, [inverted(lc)], reviewers, run_dir / "inverted", weights=weights, weights_source=weights_source)
        record.update(null_counts(lc, events, entries, run_dir, record))
    record["elapsed_s"] = round(time.monotonic() - started, 1)
    record["searched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return record


def null_counts(lc, events: dict, entries: list[dict], run_dir: Path, rec: dict) -> dict:
    """Each class's null for one star-sector (variables.py says why each is the right one):

    * dip classes: the panel and the rules on the flux-inverted copy (its stored pipeline run), dips only;
    * flares: the flare rule on the upside-down flux with the real consensus dips masked, and the rise/decay
      shape of the real flares (a time-reversal test: noise rises as often as it decays);
    * variability: the variability rule on a block-shuffled copy (0.5-day blocks, seeded by the TIC).
    """
    from exoplan.benchmark_toi import inverted
    from exoplan.variables import CLASS_IDS, dip_windows, flare_null, flare_shape, variability_null

    out: dict = {"null": {}}
    if (Path(run_dir) / "inverted" / "candidates.json").exists():
        inv = inverted(lc)
        cres = star_entries(Path(run_dir) / "inverted", tic=rec["tic"], sector=rec["sector"], time=inv.time, flux=inv.flux, events=events)
        out["null"]["dip_inverted"] = {"n_dips": cres["n_dips"],
                                       "counts": {c: sum(1 for e in cres["entries"] if e["kind"] == "dip" and e["class"] == c) for c in CLASS_IDS}}
    dips = [e for e in entries if e["kind"] == "dip"]
    out["null"]["flare_downward"] = flare_null(lc.time, lc.flux, dip_windows(dips), events)
    out["null"]["flare_shape"] = flare_shape(entries)
    half = [(e["t_start"] - 0.5 * (e["t_end"] - e["t_start"]), e["t_end"] + 0.5 * (e["t_end"] - e["t_start"])) for e in dips]
    out["null"]["variability_shuffled"] = variability_null(lc.time, lc.flux, half, seed=int(rec["tic"]) % (2 ** 32))
    return out


def _match_tois(entries: list[dict], toi_target) -> None:
    if toi_target is None:
        return
    from exoplan.discover import match_toi

    for e in entries:
        if e["kind"] == "dip":
            m = match_toi({"t_center": e["t_center"], "time_unit": "BTJD", "duration_hours": e.get("duration_hours"),
                           "period_days": e.get("period_days")}, toi_target)
            if m:
                e["toi_match"] = m["toi"]
                e["toi_disposition"] = m.get("disposition")


def reclassify_record(rec: dict, path: str | Path, *, run_root: str | Path, toi_target=None, classify_code: str | None = None,
                      rule_changes: list[str] | None = None) -> dict:
    """A stored record with its entries classified again by the current rules, from the same file and the stored
    pipeline runs (classifications, candidates and their vetting are reused, not recomputed). Refuses a file
    whose sha256 differs from the record's. The search code stays the code that made the dips; the
    classification code becomes this checkout's, and ``reclassifications`` records the change and why."""
    lc, events, _ = read_spoc(path, rec["tic"], rec["sector"])
    if lc.provenance["file_sha256"] != rec["file_sha256"]:
        raise ValueError(f"TIC {rec['tic']}: the light-curve file is not the one the record was made from")
    run_dir = Path(run_root) / f"tic{int(rec['tic'])}-s{int(rec['sector'])}"
    res = star_entries(run_dir / "real", tic=rec["tic"], sector=rec["sector"], time=lc.time, flux=lc.flux, events=events)
    entries = res["entries"]
    _match_tois(entries, toi_target)
    search_code, old = record_codes(rec)
    new = classify_code or classify_fingerprint()
    out = {k: v for k, v in rec.items() if k not in ("code", "control")}
    out.update({"entries": entries, "counts": res["counts"], "variability": res["variability"], "events": events,
                "search_code": search_code, "classify_code": new})
    out["reclassifications"] = list(rec.get("reclassifications") or []) + [{
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "reclassified_from": old, "classify_code": new,
        "rule_changes": list(rule_changes or [])}]
    out.update(null_counts(lc, events, res["entries"], run_dir, rec))
    out["rejected"] = {**rec.get("rejected", {}), "failed_vetting": sum(1 for e in entries if e["kind"] == "dip" and not e["passed"]),
                       "dips_not_planet_candidate": sum(1 for e in entries if e["kind"] == "dip" and e["class"] != "planet_candidate")}
    return out

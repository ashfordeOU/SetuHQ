"""Bring your own reviewer: contribution bundles of sweep results, signed off with content hashes, and ingest.

A contributor runs ``exoplan sweep`` on a sector with their own reviewers (the Probes, plus Sentinels through
their own Claude subscription or API key, from their environment only), then

    exoplan bundle my-sweep/sector_0005.json --contributor "Ada L." --out ada-s5

writes a bundle directory:

* ``results.json``: the sector record, as the sweep wrote it (every star-sector, its entries and coverage).
* ``config.toml``: the sweep config that ran (its hash is the run's config hash).
* ``manifest.json``: who signs it off and the provenance: the code fingerprint of the result-making code
  (:func:`exoplan.starsearch.code_fingerprint`), the config hash, the sha256 of every light-curve file read,
  the reviewers, the sha256 of the two files above, and ``content_sha256`` over the manifest itself.

Signing off means content hashes, not keys: the hashes make any later change to the bundle visible, and the
sign-off line says who ran it. A bundle never holds a key, a token or an environment variable.

    exoplan ingest ada-s5

refuses a bundle when a file or the manifest does not match its hash, when its code fingerprint is not this
checkout's (the same code must have made it), when its config hash does not match its config, when a
light-curve hash is missing or malformed, when an entry's class is not what the classification rules give
for its stored inputs, or when anything in it looks like a credential. A valid bundle is copied to
``docs/sweep/contributions/<bundle_id>/`` and the catalogue is rebuilt with credit to the contributor's
chosen name, which the object pages and the export show.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from exoplan import __version__
from exoplan.variables import CLASS_IDS, CONFIDENCES, KINDS, LS_AMPLITUDE_RATIO, LS_FAP_MAX, classify_dip, classify_flare, classify_variability

FORMAT = "exoplan-contribution/1"
FILES = ("results.json", "config.toml")
NAME_RE = re.compile(r"^[\w .,'()\-]{1,60}$", re.UNICODE)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Things that must never be in a bundle: API keys, tokens and private keys.
SECRET_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                       r"-----BEGIN [A-Z ]*PRIVATE KEY-----|ANTHROPIC_API_KEY\s*=|xox[baprs]-[A-Za-z0-9-]{10,}")
SIGN_OFF = ("I ran this sweep with the exoplan code and config named in this manifest, on the light curves whose "
            "sha256 are listed, and I have not edited the results. Every entry is a light-curve classification, "
            "not a confirmed planet or star.")


class BundleRefused(ValueError):
    """The bundle failed validation; the message says why."""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def check_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name) or "http" in name.lower() or "@" in name:
        raise BundleRefused(f"contributor name {name!r}: use 1 to 60 letters, digits, spaces and . , ' ( ) - _ only (no links or e-mail)")
    return name


def make_bundle(record_path: str | Path, out_dir: str | Path, *, contributor: str, now: str | None = None) -> Path:
    """Write the bundle for one sector record. The record's own config text becomes config.toml."""
    record_path = Path(record_path)
    raw = record_path.read_bytes()
    rec = json.loads(raw)
    name = check_name(contributor)
    config_text = rec.get("config_text") or ""
    if not config_text:
        raise BundleRefused(f"{record_path}: the record holds no config text")
    for label, text in (("results", raw.decode()), ("config", config_text)):
        if SECRET_RE.search(text):
            raise BundleRefused(f"the {label} look like they contain a credential; remove it and run the sweep again")
    searched = [s for s in rec.get("stars", []) if s.get("status") == "searched"]
    codes = {s.get("code") for s in searched}
    if len(codes) != 1:
        raise BundleRefused(f"the record mixes results from {len(codes)} code versions; re-run the sweep with one checkout")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_bytes(raw)
    (out / "config.toml").write_text(config_text)
    reviewers = {}
    for s in searched:
        for r in s.get("reviewers") or []:
            reviewers[r["id"]] = {k: r.get(k) for k in ("id", "kind", "model") if r.get(k) is not None}
    manifest = {
        "format": FORMAT,
        "contributor": {"name": name},
        "signed_off": {"by": name, "statement": SIGN_OFF, "at": now or datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "exoplan_version": __version__,
        "code_fingerprint": next(iter(codes)),
        "config_name": rec.get("config_name"), "config_sha256": rec.get("config_sha256"),
        "sector": rec.get("sector"), "star_sectors": len(searched),
        "entries": sum(len(s.get("entries") or []) for s in searched),
        "reviewers": sorted(reviewers.values(), key=lambda r: r["id"]),
        "lightcurves": [{"tic": s["tic"], "sector": s["sector"], "file": s.get("file"), "sha256": s.get("file_sha256")} for s in searched],
        "files": {f: sha256_bytes((out / f).read_bytes()) for f in FILES},
    }
    manifest["bundle_id"] = "c-" + sha256_bytes(_canonical({"files": manifest["files"], "contributor": name}))[:16]
    manifest["content_sha256"] = sha256_bytes(_canonical(manifest))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    return out


def _open(bundle: Path) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """A bundle directory, or a zip of one (only the three bundle files, at the top level or in one folder)."""
    if bundle.is_dir():
        return bundle, None
    if bundle.suffix.lower() != ".zip" or not bundle.exists():
        raise BundleRefused(f"{bundle}: not a bundle directory or .zip")
    tmp = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(bundle) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if name not in FILES + ("manifest.json",) or ".." in info.filename or info.filename.startswith("/"):
                tmp.cleanup()
                raise BundleRefused(f"unexpected file in the zip: {info.filename}")
            if info.file_size > 50_000_000:
                tmp.cleanup()
                raise BundleRefused(f"{info.filename} is larger than 50 MB")
            (Path(tmp.name) / name).write_bytes(z.read(info))
    return Path(tmp.name), tmp


def validate_bundle(bundle: str | Path, *, code: str | None = None) -> dict:
    """Every check, in order; returns the manifest and the results on success, raises BundleRefused otherwise."""
    from exoplan.config import load_config
    from exoplan.starsearch import code_fingerprint

    path, tmp = _open(Path(bundle))
    try:
        names = sorted(p.name for p in path.iterdir())
        if names != sorted(FILES + ("manifest.json",)):
            raise BundleRefused(f"a bundle holds exactly manifest.json, results.json and config.toml; found {names}")
        man_text = (path / "manifest.json").read_text()
        for f in ("manifest.json",) + FILES:
            if SECRET_RE.search((path / f).read_text(errors="replace")):
                raise BundleRefused(f"{f} looks like it contains a credential; a bundle must never hold keys or tokens")
        try:
            man = json.loads(man_text)
        except json.JSONDecodeError as exc:
            raise BundleRefused(f"manifest.json is not JSON: {exc}") from None
        if man.get("format") != FORMAT:
            raise BundleRefused(f"manifest format {man.get('format')!r}, expected {FORMAT!r}")
        claimed = man.get("content_sha256")
        body = {k: v for k, v in man.items() if k != "content_sha256"}
        if claimed != sha256_bytes(_canonical(body)):
            raise BundleRefused("manifest hash mismatch: the manifest was changed after it was signed off")
        name = check_name((man.get("contributor") or {}).get("name", ""))
        if (man.get("signed_off") or {}).get("by") != name:
            raise BundleRefused("the sign-off is not by the named contributor")
        for f in FILES:
            got = sha256_bytes((path / f).read_bytes())
            if got != (man.get("files") or {}).get(f):
                raise BundleRefused(f"hash mismatch on {f}: the file was changed after it was signed off")
        if man.get("bundle_id") != "c-" + sha256_bytes(_canonical({"files": man["files"], "contributor": name}))[:16]:
            raise BundleRefused("bundle id does not match its files and contributor")
        here = code or code_fingerprint()
        if man.get("code_fingerprint") != here:
            raise BundleRefused(f"code fingerprint mismatch: the bundle was made with code {str(man.get('code_fingerprint'))[:16]}…, "
                                f"this checkout is {here[:16]}…; ingest it with the same exoplan commit the contributor ran")
        config_path = path / "config.toml"
        try:
            digest = load_config(config_path).digest()
        except Exception as exc:  # noqa: BLE001
            raise BundleRefused(f"config.toml does not load: {exc}") from None
        rec = json.loads((path / "results.json").read_text())
        if not (digest == man.get("config_sha256") == rec.get("config_sha256")):
            raise BundleRefused("config hash mismatch between config.toml, the manifest and the results")
        _check_results(rec, man, digest)
        return {"manifest": man, "results": rec, "path": path, "_tmp": tmp}
    except BundleRefused:
        if tmp:
            tmp.cleanup()
        raise


def _check_results(rec: dict, man: dict, digest: str) -> None:
    if rec.get("sector") != man.get("sector"):
        raise BundleRefused("sector differs between the manifest and the results")
    lcs = {(int(x["tic"]), int(x["sector"])): x.get("sha256") for x in man.get("lightcurves") or []}
    searched = [s for s in rec.get("stars") or [] if s.get("status") == "searched"]
    if len(searched) != man.get("star_sectors") or len(lcs) != len(searched):
        raise BundleRefused("the number of searched star-sectors differs between the manifest and the results")
    for s in rec.get("stars") or []:
        if s.get("status") not in ("searched", "no_data", "error", "pending"):
            raise BundleRefused(f"TIC {s.get('tic')}: unknown status {s.get('status')!r}")
        if s.get("status") != "searched":
            if s.get("entries"):
                raise BundleRefused(f"TIC {s.get('tic')}: entries on a star-sector that was not searched")
            continue
        key = (int(s["tic"]), int(s["sector"]))
        sha = s.get("file_sha256")
        if not isinstance(sha, str) or not HEX64.match(sha) or lcs.get(key) != sha:
            raise BundleRefused(f"TIC {s['tic']}: light-curve sha256 missing, malformed or not in the manifest")
        if s.get("code") != man["code_fingerprint"] or s.get("config_sha256") != digest:
            raise BundleRefused(f"TIC {s['tic']}: made with a different code or config than the manifest names")
        _check_entries(s)


def _check_entries(s: dict) -> None:
    """Every entry's class and confidence must be what the rules give for its stored inputs."""
    events = s.get("events") or {}
    var = s.get("variability")
    star_var = var if var and var.get("fap") is not None and var["fap"] < LS_FAP_MAX and var.get("amplitude_ratio", 0) >= LS_AMPLITUDE_RATIO else None
    eb_periods = []
    ids = [e.get("id") for e in s.get("entries") or []]
    if len(set(ids)) != len(ids):
        raise BundleRefused(f"TIC {s['tic']}: two entries share an id")
    for e in s.get("entries") or []:
        if e.get("tic") != s["tic"] or e.get("sector") != s["sector"]:
            raise BundleRefused(f"entry {e.get('id')}: star or sector differs from its record")
        if e.get("class") not in CLASS_IDS or e.get("kind") not in KINDS or e.get("confidence") not in CONFIDENCES:
            raise BundleRefused(f"entry {e.get('id')}: unknown class, kind or confidence")
        if e["kind"] == "dip":
            got = classify_dip(e, events, star_var)
            if got["class"] == "eclipsing_binary" and e.get("period_days"):
                eb_periods.append(e["period_days"])
        elif e["kind"] == "brightening":
            got = classify_flare({"t_start": e["t_start"], "t_end": e["t_end"], "n_points": e["n_points"], "peak_sigma": e["peak_sigma"],
                                  "amplitude_ppm": e["amplitude_ppm"], "rise_days": e["rise_minutes"] / 1440, "decay_days": e["decay_minutes"] / 1440}, events)
        else:
            continue
        if (got["class"], got["confidence"]) != (e["class"], e["confidence"]):
            raise BundleRefused(f"entry {e['id']}: stored class {e['class']} ({e['confidence']}), the rules give {got['class']} ({got['confidence']})")
    for e in s.get("entries") or []:
        if e["kind"] == "variability":
            got = classify_variability({"period_days": e["period_days"], "fap": e["ls_fap"], "amplitude_ratio": e["amplitude_ratio"],
                                        "amplitude_ppm": e["amplitude_ppm"]}, eb_periods)
            if not got or (got["class"], got["confidence"]) != (e["class"], e["confidence"]):
                raise BundleRefused(f"entry {e['id']}: the variability rule does not give {e['class']} ({e['confidence']})")


def check_at_mast(rec: dict, n: int, *, fetch=None, cache_root: str | Path = "cache", seed: int = 0) -> int:
    """Re-download ``n`` of the bundle's light curves (chosen with a fixed seed) and compare their sha256."""
    import random

    from exoplan.starsearch import sha256_file
    from exoplan.sweep import Throttle, fetch_file, sector_targets

    searched = [s for s in rec.get("stars") or [] if s.get("status") == "searched"]
    if not searched or n <= 0:
        return 0
    pick = random.Random(seed).sample(searched, min(n, len(searched)))
    targets, _ = sector_targets(rec["sector"], cache_root)
    by_tic = {t["tic"]: t for t in targets}
    throttle = Throttle(1.0)
    for s in pick:
        t = by_tic.get(s["tic"])
        if t is None:
            raise BundleRefused(f"TIC {s['tic']} is not a SPOC 2-minute target of sector {rec['sector']}")
        got = sha256_file(fetch_file(t, rec["sector"], cache_root, throttle=throttle, fetch=fetch))
        if got != s["file_sha256"]:
            raise BundleRefused(f"TIC {s['tic']}: the light curve at MAST hashes to {got[:16]}…, the bundle says {s['file_sha256'][:16]}…")
    return len(pick)


def ingest_bundle(bundle: str | Path, *, sweep_dir: str | Path = "docs/sweep", verify_lightcurves: int = 0, code: str | None = None,
                  fetch=None, cache_root: str | Path = "cache") -> dict:
    """Validate, copy into ``<sweep_dir>/contributions/<bundle_id>/`` and rebuild the catalogue."""
    from exoplan.sweep import build_catalogue

    v = validate_bundle(bundle, code=code)
    try:
        man, rec = v["manifest"], v["results"]
        if verify_lightcurves:
            check_at_mast(rec, verify_lightcurves, fetch=fetch, cache_root=cache_root)
        dest = Path(sweep_dir) / "contributions" / man["bundle_id"]
        if dest.exists():
            raise BundleRefused(f"bundle {man['bundle_id']} is already ingested")
        dest.mkdir(parents=True)
        for f in ("manifest.json",) + FILES:
            shutil.copyfile(v["path"] / f, dest / f)
        cat = build_catalogue(sweep_dir)
    finally:
        if v.get("_tmp"):
            v["_tmp"].cleanup()
    return {"bundle_id": man["bundle_id"], "contributor": man["contributor"]["name"], "star_sectors": man["star_sectors"],
            "entries": man["entries"], "catalogue": str(cat), "path": str(dest)}

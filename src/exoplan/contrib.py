"""Bring your own reviewer: contribution bundles of sweep results, sealed with content hashes, and ingest.

A contributor runs ``exoplan sweep`` on a sector with their own reviewers (the Probes, plus Sentinels through
their own Claude subscription or API key, from their environment only), then

    exoplan bundle my-sweep/sector_0005.json --contributor "Ada L." --out ada-s5

writes a bundle directory:

* ``results.json``: the sector record, as the sweep wrote it (every star-sector, its entries and coverage).
* ``config.toml``: the sweep config that ran (its hash is the run's config hash).
* ``manifest.json``: the contributor's chosen name and statement, and the provenance: the search and
  classification code fingerprints (:mod:`exoplan.starsearch`), the config hash, the sha256 of every light-curve
  file read, the reviewers, the sha256 of the two files above, and ``content_sha256`` over the manifest itself.

**Sealed, not signed.** The hashes make any later change to the bundle visible to someone who holds the
original hashes. They do not prove who made it: anyone can edit a bundle and recompute every hash. So ingest
trusts nothing in a bundle that it can check another way:

* every star-sector carrying a planet candidate or an entry in a class that exceeds its null, plus
  ``max(3, 5%)`` of the rest at random (seeded by a nonce the maintainer draws at ingest from os.urandom, so
  the contributor cannot steer which), is fetched again from MAST and must hash to the same bytes;
* those star-sectors are **searched again** with the bundle's config and this checkout's code, and every
  entry, count and null must agree exactly. The Probes are deterministic, so a Probes-only bundle is checked
  in full on its sample; a bundle with Sentinels cannot be re-run without their answers and is refused unless
  the maintainer accepts it explicitly (``--accept-sentinels``), which the catalogue then says;
* every entry's class is re-derived from its stored inputs by the rules;
* a star-sector already in the catalogue as an identical search (same light curve, search code and config)
  earns no credit and adds nothing to any counter; a bundle with nothing new is refused;
* the identity behind a contribution is the one the maintainer attests at ingest (``--attested-by``, for
  example the pull request's author), stored beside the bundle; the name in the manifest is the credit the
  contributor chose, not proof of identity.

A bundle never holds a key, a token or an environment variable, and ingest refuses one that looks like it does;
its config is written without comments, where a pasted key would hide. The catalogue reads only contribution
folders that ingest wrote (with ingest.json) and whose hashes still verify (``sweep.verify_contribution``).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from exoplan import __version__
from exoplan.variables import CLASS_IDS, CONFIDENCES, KINDS, LS_AMPLITUDE_RATIO, LS_FAP_MAX, classify_dip, classify_flare, classify_variability

FORMAT = "exoplan-contribution/2"
FILES = ("results.json", "config.toml")
NAME_RE = re.compile(r"^[\w .,'()\-]{1,60}$", re.UNICODE)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MIN_RANDOM = 3            # at least this many star-sectors searched again at random, or 5% of the bundle if more
RANDOM_FRACTION = 0.05
# Things that must never be in a bundle, anywhere: API keys (sk-ant-, sk-proj-, other sk- keys, Google AIza, Hugging
# Face hf_), GitHub, Slack and AWS credentials, bearer and x-api-key headers, JWTs, private keys, and a key variable
# given a value in any form.
SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9][A-Za-z0-9_\-]{19,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|aws_secret_access_key"
    r"|\bAIza[0-9A-Za-z_\-]{30,}|\bhf_[A-Za-z0-9]{30,}"
    r"|\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"
    r"|(?i:authorization)\s*[:=]?\s*(?i:bearer|basic|token)\s+\S{8,}|(?i:x-api-key)[\s:=\"']+\S{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|ANTHROPIC_API_KEY\s*[:=]")
# In the config (and the manifest), any key naming a credential with a value after it.
ASSIGN_RE = re.compile(r"(?i)\b[\w.-]*(api[_-]?key|token|secret|password|passwd)[\w.-]*[\"']?\s*[:=]\s*\S+")
# A bare AWS secret key (40 base64 characters) in the config.
AWS_SECRET_RE = re.compile(r"(?<![A-Za-z0-9/+=])(?=[A-Za-z0-9/+]*[A-Z])(?=[A-Za-z0-9/+]*[a-z])(?=[A-Za-z0-9/+]*[0-9])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])")
STATEMENT = ("I ran this sweep with the exoplan code and config named in this manifest, on the light curves whose sha256 "
             "are listed, and I have not edited the results. Every entry is a light-curve classification, not a confirmed "
             "planet or star. These hashes seal the bundle against later change; they are not a signature and do not "
             "prove who made it.")


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


def screen(label: str, text: str, *, assignments: bool) -> None:
    """Refuse text that looks like it holds a credential."""
    m = SECRET_RE.search(text) or (ASSIGN_RE.search(text) if assignments else None) or (AWS_SECRET_RE.search(text) if assignments else None)
    if m:
        raise BundleRefused(f"{label} looks like it contains a credential ({m.group(0)[:12]}…); a bundle must never hold keys, "
                            "tokens or passwords: keep them in your environment")


def _entropy(s: str) -> float:
    import math
    from collections import Counter

    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values()) if n else 0.0


def has_comment(text: str) -> bool:
    """True when TOML text has a comment (a '#' outside a quoted string) or a multi-line string, which a bundled
    config may not: a comment is where a pasted key hides."""
    if '"""' in text or "'''" in text:
        return True
    for line in text.splitlines():
        quote = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\" and quote == '"':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                return True
            i += 1
    return False


def dump_toml(d: dict) -> str:
    """A config as TOML without comments: scalars, then tables, then arrays of tables (the sweep configs' shape).
    Loading it back gives the same dictionary, so the config hash (over the parsed config) is unchanged."""
    def val(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
            return "[" + ", ".join(val(x) for x in v) + "]"
        raise BundleRefused(f"the config holds a value this bundle format does not carry: {v!r}")

    def table(prefix, t, out):
        out += [f"{k} = {val(v)}" for k, v in t.items() if not isinstance(v, dict) and not (isinstance(v, list) and v and isinstance(v[0], dict))]
        for k, v in t.items():
            if isinstance(v, dict):
                out += ["", f"[{prefix}{k}]"]
                table(f"{prefix}{k}.", v, out)
        for k, v in t.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for item in v:
                    out += ["", f"[[{prefix}{k}]]"]
                    table(f"{prefix}{k}.", item, out)
        return out

    return "\n".join(table("", d, [])).lstrip("\n") + "\n"


def screen_config(text: str) -> None:
    """A bundled config: no comments, no credential pattern, no long high-entropy string value."""
    import tomllib

    if has_comment(text):
        raise BundleRefused("config.toml has comments; a bundled config is written without them (exoplan bundle does this), "
                            "since a comment is where a pasted key hides")
    screen("config.toml", text, assignments=True)

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and len(v) >= 32 and " " not in v and _entropy(v) >= 3.5:
            raise BundleRefused(f"config.toml holds a long random-looking value ({v[:8]}…); a bundle must never hold keys or tokens")

    walk(tomllib.loads(text))


def make_bundle(record_path: str | Path, out_dir: str | Path, *, contributor: str, now: str | None = None) -> Path:
    """Write the bundle for one sector record. The record's own config text becomes config.toml."""
    from exoplan.starsearch import record_codes

    record_path = Path(record_path)
    from exoplan.sweep import read_record

    rec = read_record(record_path)
    name = check_name(contributor)
    config_text = rec.get("config_text") or ""
    if not config_text:
        raise BundleRefused(f"{record_path}: the record holds no config text")
    import tomllib

    from exoplan.config import load_config

    # The config is bundled without its comments (where a pasted key would hide); its hash, over the parsed
    # config, does not change, and the bundle's results carry the same comment-free text.
    try:
        parsed = tomllib.loads(config_text)
    except tomllib.TOMLDecodeError as exc:
        raise BundleRefused(f"the record's config does not parse: {exc}") from None
    screen("the config", config_text, assignments=True)   # comments included: a key there means the source holds one
    clean = dump_toml(parsed)
    tmp = Path(tempfile.mkdtemp(prefix="exoplan-bundle-")) / "config.toml"
    tmp.write_text(clean)
    if load_config(tmp).digest() != rec.get("config_sha256"):
        raise BundleRefused("the record's config text does not hash to its config_sha256")
    screen_config(clean)
    rec["config_text"] = clean
    raw = json.dumps(rec, separators=(",", ":"), ensure_ascii=False).encode()
    screen("the results", raw.decode(), assignments=False)
    config_text = clean
    searched = [s for s in rec.get("stars", []) if s.get("status") == "searched"]
    codes = {record_codes(s) for s in searched}
    if len(codes) != 1:
        raise BundleRefused(f"the record mixes results from {len(codes)} code versions; re-run the sweep with one checkout")
    search_code, classify_code = next(iter(codes))
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
        "statement": {"by": name, "text": STATEMENT, "at": now or datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "seal": "sha256 content hashes (files, manifest); not a signature",
        "exoplan_version": __version__,
        "search_code": search_code, "classify_code": classify_code,
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
    """A bundle directory, or a zip of one (only the three bundle files, each once, at the top level or in one folder)."""
    if bundle.is_dir():
        return bundle, None
    if bundle.suffix.lower() != ".zip" or not bundle.exists():
        raise BundleRefused(f"{bundle}: not a bundle directory or .zip")
    tmp = tempfile.TemporaryDirectory()
    seen: set = set()
    with zipfile.ZipFile(bundle) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            fn = info.filename
            name = fn.replace("\\", "/").rsplit("/", 1)[-1]
            bad = (name not in FILES + ("manifest.json",) or ".." in fn or fn.startswith(("/", "\\")) or ":" in fn
                   or fn.count("/") > 1 or name in seen)
            if bad:
                tmp.cleanup()
                raise BundleRefused(f"unexpected file in the zip: {fn}")
            if info.file_size > 50_000_000:
                tmp.cleanup()
                raise BundleRefused(f"{fn} is larger than 50 MB")
            seen.add(name)
            (Path(tmp.name) / name).write_bytes(z.read(info))
    return Path(tmp.name), tmp


def validate_bundle(bundle: str | Path, *, codes: tuple | None = None) -> dict:
    """Every check that needs no network, in order; returns the manifest and the results, or raises BundleRefused."""
    from exoplan.config import load_config
    from exoplan.starsearch import classify_fingerprint, search_fingerprint

    path, tmp = _open(Path(bundle))
    try:
        names = sorted(p.name for p in path.iterdir())
        if names != sorted(FILES + ("manifest.json",)):
            raise BundleRefused(f"a bundle holds exactly manifest.json, results.json and config.toml; found {names}")
        screen("results.json", (path / "results.json").read_text(errors="replace"), assignments=False)
        screen("manifest.json", (path / "manifest.json").read_text(errors="replace"), assignments=True)
        try:
            screen_config((path / "config.toml").read_text(errors="replace"))
        except BundleRefused:
            raise
        except Exception as exc:  # noqa: BLE001 (a config that does not parse)
            raise BundleRefused(f"config.toml does not load: {exc}") from None
        try:
            man = json.loads((path / "manifest.json").read_text())
        except json.JSONDecodeError as exc:
            raise BundleRefused(f"manifest.json is not JSON: {exc}") from None
        if man.get("format") != FORMAT:
            raise BundleRefused(f"manifest format {man.get('format')!r}, expected {FORMAT!r}")
        body = {k: v for k, v in man.items() if k != "content_sha256"}
        if man.get("content_sha256") != sha256_bytes(_canonical(body)):
            raise BundleRefused("manifest hash mismatch: the manifest was changed after it was sealed")
        name = check_name((man.get("contributor") or {}).get("name", ""))
        if (man.get("statement") or {}).get("by") != name:
            raise BundleRefused("the statement is not by the named contributor")
        for f in FILES:
            if sha256_bytes((path / f).read_bytes()) != (man.get("files") or {}).get(f):
                raise BundleRefused(f"hash mismatch on {f}: the file was changed after it was sealed")
        if man.get("bundle_id") != "c-" + sha256_bytes(_canonical({"files": man["files"], "contributor": name}))[:16]:
            raise BundleRefused("bundle id does not match its files and contributor")
        here = codes or (search_fingerprint(), classify_fingerprint())
        if (man.get("search_code"), man.get("classify_code")) != tuple(here):
            raise BundleRefused(f"code fingerprint mismatch: the bundle was made with search code {str(man.get('search_code'))[:16]}… and "
                                f"classification code {str(man.get('classify_code'))[:16]}…, this checkout is {here[0][:16]}… and "
                                f"{here[1][:16]}…; ingest it with the same exoplan commit the contributor ran")
        try:
            digest = load_config(path / "config.toml").digest()
        except Exception as exc:  # noqa: BLE001
            raise BundleRefused(f"config.toml does not load: {exc}") from None
        rec = json.loads((path / "results.json").read_text())
        if not (digest == man.get("config_sha256") == rec.get("config_sha256")):
            raise BundleRefused("config hash mismatch between config.toml, the manifest and the results")
        if rec.get("config_text") != (path / "config.toml").read_text():
            raise BundleRefused("the results' config text differs from config.toml")
        _check_results(rec, man, digest)
        return {"manifest": man, "results": rec, "path": path, "_tmp": tmp}
    except BundleRefused:
        if tmp:
            tmp.cleanup()
        raise


def _check_results(rec: dict, man: dict, digest: str) -> None:
    from exoplan.starsearch import record_codes

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
        if record_codes(s) != (man["search_code"], man["classify_code"]) or s.get("config_sha256") != digest:
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


# ---------- checks against the world: MAST, and a fresh search ----------
def sample(rec: dict, n: int, seed: str) -> list[dict]:
    """``n`` searched star-sectors of the record at random, chosen with ``seed``."""
    searched = [s for s in rec.get("stars") or [] if s.get("status") == "searched"]
    return random.Random(seed).sample(searched, min(max(n, 0), len(searched)))


def select_for_search(rec: dict, *, exceeding: set, nonce: str, min_random: int | None = None) -> tuple[list[dict], list[dict]]:
    """The star-sectors ingest fetches and searches again: every one that carries a planet candidate or an entry
    in a class that exceeds its null in the catalogue (they are what the site shows as findings, so they are
    always checked), plus ``max(3, 5%)`` of the rest at random. The random part is seeded with a nonce the
    maintainer draws at ingest (os.urandom), so the contributor cannot steer it by renaming or resealing."""
    import math

    searched = [s for s in rec.get("stars") or [] if s.get("status") == "searched"]
    flagged = {"planet_candidate"} | set(exceeding)
    forced = [s for s in searched if any(e.get("class") in flagged for e in s.get("entries") or [])]
    rest = [s for s in searched if not any(s is f for f in forced)]
    k = max(MIN_RANDOM, math.ceil(RANDOM_FRACTION * len(searched))) if min_random is None else max(0, min_random)
    return forced, random.Random(nonce).sample(rest, min(k, len(rest)))


def fetch_and_hash(rec: dict, picked: list[dict], *, fetch=None, cache_root: str | Path = "cache") -> list[dict]:
    """Fetch the picked light curves again from MAST and compare their sha256. Fetches go to a fresh directory,
    so a file already cached cannot stand in for MAST's."""
    from exoplan.starsearch import sha256_file
    from exoplan.sweep import Throttle, fetch_file, sector_targets

    if not picked:
        return []
    targets, _ = sector_targets(rec["sector"], cache_root)
    by_tic = {t["tic"]: t for t in targets}
    fresh = Path(tempfile.mkdtemp(prefix="exoplan-verify-"))
    throttle = Throttle(1.0)
    for s in picked:
        t = by_tic.get(s["tic"])
        if t is None:
            raise BundleRefused(f"TIC {s['tic']} is not a SPOC 2-minute target of sector {rec['sector']}")
        p = fetch_file(t, rec["sector"], fresh, throttle=throttle, fetch=fetch)
        got = sha256_file(p)
        if got != s["file_sha256"]:
            raise BundleRefused(f"TIC {s['tic']}: the light curve at MAST hashes to {got[:16]}…, the bundle says {s['file_sha256'][:16]}…")
        s["_path"] = str(p)
    return picked


def check_at_mast(rec: dict, n: int, *, fetch=None, cache_root: str | Path = "cache", seed: str = "") -> list[dict]:
    """Fetch ``n`` random light curves of the record again and compare their sha256."""
    return fetch_and_hash(rec, sample(rec, n, seed), fetch=fetch, cache_root=cache_root)


def _norm(x):
    """A record part as compared after a fresh search: floats to 9 significant digits, run-specific fields dropped."""
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in sorted(x.items()) if k not in RUN_SPECIFIC}
    if isinstance(x, list):
        return [_norm(v) for v in x]
    if isinstance(x, float):
        return float(f"{x:.9g}")
    return x


# Fields that differ between two honest runs: timings, dates, the local TOI table's annotations and paths.
RUN_SPECIFIC = {"elapsed_s", "searched_at", "reclassified_at", "reclassifications", "toi_match", "toi_disposition", "tois", "_path",
                "search_commit", "classify_commit", "search_time_classify_code", "weights_source"}
COMPARED = ("n_points", "n_subjects", "n_classifications", "n_marks", "n_dips", "rejected", "counts", "events", "variability", "entries", "null")


def rerun_check(rec: dict, config_path: str | Path, picked: list[dict], *, cache_root: str | Path = "cache") -> list[int]:
    """Search ``picked`` star-sectors again (from the files just fetched) with the bundle's config, the weights it
    recorded and this checkout's code, and require every compared field to agree exactly."""
    from exoplan.config import build_reviewers, load_config
    from exoplan.starsearch import search_star
    from exoplan.sweep import finite

    config = load_config(config_path)
    reviewers = build_reviewers(config.reviewers, cache_root=str(cache_root))
    if any(r.kind != "simulated" for r in reviewers):
        raise BundleRefused("the config has Sentinels, whose answers a fresh search cannot reproduce here")
    run_root = Path(tempfile.mkdtemp(prefix="exoplan-rerun-"))
    done = []
    for s in picked:
        weights = {r["id"]: float(r["weight"]) for r in s.get("reviewers") or []}
        new = finite(search_star(s["_path"], tic=s["tic"], sector=s["sector"], config=config, reviewers=reviewers, weights=weights,
                                 weights_source=s.get("weights_source", ""), run_root=run_root, control="null" in s))
        for k in COMPARED:
            if _norm(new.get(k)) != _norm(s.get(k)):
                raise BundleRefused(f"TIC {s['tic']}: a fresh search does not reproduce the bundle's {k}; the results were not made by "
                                    "this code and config, or were edited")
        done.append(s["tic"])
    shutil.rmtree(run_root, ignore_errors=True)
    return done


def ingest_bundle(bundle: str | Path, *, sweep_dir: str | Path = "docs/sweep", verify_lightcurves: int | None = None,
                  attested_by: str | None = None, accept_sentinels: bool = False, codes: tuple | None = None,
                  fetch=None, cache_root: str | Path = "cache", nonce: str | None = None) -> dict:
    """Validate; refuse a re-submission; fetch and search again every star-sector with a planet candidate or an
    entry in a class that exceeds its null, plus ``max(3, 5%)`` (or ``verify_lightcurves``) at random chosen by a
    fresh maintainer nonce; then copy into ``<sweep_dir>/contributions/<bundle_id>/`` with ``ingest.json`` (who
    attested it, the nonce, what was searched again, the manifest's hash) and rebuild the catalogue."""
    import os

    from exoplan.sweep import build_catalogue, load_sources, search_identity

    if attested_by is not None and not re.match(r"^[A-Za-z0-9-]{1,39}$", attested_by):
        raise BundleRefused(f"--attested-by {attested_by!r}: give the GitHub login of the person who sent the bundle")
    v = validate_bundle(bundle, codes=codes)
    try:
        man, rec = v["manifest"], v["results"]
        dest = Path(sweep_dir) / "contributions" / man["bundle_id"]
        if dest.exists():
            raise BundleRefused(f"bundle {man['bundle_id']} is already ingested")
        have = {search_identity(s) for src in load_sources(sweep_dir) for s in src["record"].get("stars", []) if s.get("status") == "searched"}
        mine = [search_identity(s) for s in rec.get("stars", []) if s.get("status") == "searched"]
        new = [i for i in mine if i not in have]
        if not new:
            raise BundleRefused(f"re-submission: all {len(mine)} star-sectors are already in the catalogue as identical searches "
                                "(same light curve, search code and config); nothing new to credit")
        sentinels = any(r.get("kind") != "simulated" for r in man.get("reviewers") or [])
        if sentinels and not accept_sentinels:
            raise BundleRefused("the bundle has Sentinels, so a fresh search cannot reproduce it here; a maintainer may accept it "
                                "with --accept-sentinels, and the catalogue will then say its dips were not re-run")
        cat_path = Path(sweep_dir) / "catalogue.json"
        exceeding: set = set()
        if cat_path.exists():
            comps = ((json.loads(cat_path.read_text())["counts"].get("null") or {}).get("comparisons")) or []
            exceeding = {c["class"] for c in comps if c.get("significant")}
        nonce = nonce or os.urandom(16).hex()
        forced, rand = select_for_search(rec, exceeding=exceeding, nonce=nonce, min_random=verify_lightcurves)
        picked = fetch_and_hash(rec, forced + rand, fetch=fetch, cache_root=cache_root)
        rerun = [] if sentinels else rerun_check(rec, v["path"] / "config.toml", picked, cache_root=cache_root)
        dest.mkdir(parents=True)
        for f in ("manifest.json",) + FILES:
            shutil.copyfile(v["path"] / f, dest / f)
        record = {"bundle_id": man["bundle_id"], "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "attested_by": attested_by, "contributor_name": man["contributor"]["name"],
                  "manifest_sha256": sha256_bytes((dest / "manifest.json").read_bytes()),
                  "nonce": nonce,
                  "verified": {"lightcurves_refetched": [s["tic"] for s in picked], "searched_again": rerun,
                               "always_searched": [s["tic"] for s in forced], "random": [s["tic"] for s in rand],
                               "exceeding_classes": sorted(exceeding), "rules_reapplied": "every entry",
                               "dips_searched_again": not sentinels},
                  "new_star_sectors": len(new), "already_in_catalogue": len(mine) - len(new)}
        (dest / "ingest.json").write_text(json.dumps(record, indent=1) + "\n")
        cat = build_catalogue(sweep_dir)
    finally:
        if v.get("_tmp"):
            v["_tmp"].cleanup()
    return {"bundle_id": man["bundle_id"], "contributor": man["contributor"]["name"], "star_sectors": man["star_sectors"],
            "new_star_sectors": len(new), "entries": man["entries"], "catalogue": str(cat), "path": str(dest), "verified": record["verified"]}

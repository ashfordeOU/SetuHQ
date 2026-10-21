# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Public sources the preparation pack reads, politely: the RTL CSV, coordinates, archive metadata, TOI ephemerides.

Every request is a single, read-only GET (or a TAP/name-lookup POST) to a public page or service. There is no
login, no form submission and nothing touches ESA's proposal tools (PHT1/PHT2). Requests to one host are spaced
at least :data:`MIN_INTERVAL_S` apart, retried at most twice, and identified by a User-Agent. There is no bulk
scraping: one pack makes a handful of requests (the call page, its RTL CSV links, one SIMBAD query, at most two
archive queries, one TOI query).

Each response is kept with its URL, fetch time (UTC) and SHA-256, so a pack can say exactly what it read. When
a cache directory is given, responses are reused for the same UTC day (the RTL is cached under its own file name
and fetch date); the cache lives under ``cache/`` (git-ignored), so no ESA file is committed to the repository.
The RTL is never vendored: ESA's pages give no redistribution terms for it, so it is downloaded at run time.

Archive metadata comes from DACE (Data and Analysis Center for Exoplanets, University of Geneva), the public
query interface of the CHEOPS Mission Archive. Only public metadata is kept: for visits whose data are not yet
public only their number is reported, and no PI names are stored from any visit.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from setuhq import __version__

USER_AGENT = f"SetuHQ-proposal-prep/{__version__} (+https://setuhq.com; read-only, cached)"
MIN_INTERVAL_S = 1.0
TIMEOUT_S = 30
RETRIES = 2

CALL_PAGE = "https://www.cosmos.esa.int/web/cheops-guest-observers-programme/cheops-running-call"
COSMOS = "https://www.cosmos.esa.int"
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
MAST_INVOKE = "https://mast.stsci.edu/api/v0/invoke"
DACE_CHEOPS = "https://cheops-webapp-pg.obsuksprd2.unige.ch/search"
NEA_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


class SourceError(RuntimeError):
    """A source could not be read (network, service, or an unexpected answer)."""


@dataclass
class Fetched:
    url: str
    body: bytes
    fetched_at: str
    cached: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    def record(self, saved_as: str | None = None) -> dict:
        out = {"url": self.url, "fetched_at": self.fetched_at, "sha256": self.sha256, "bytes": len(self.body),
               "from_cache": self.cached}
        if saved_as:
            out["saved_as"] = saved_as
        return out


@dataclass
class Fetcher:
    """Rate-limited, cached HTTP reads. ``cache_dir=None`` writes nothing outside the pack (the MCP tool's mode);
    ``offline=True`` makes no request at all (cache only)."""

    cache_dir: Path | None = None
    offline: bool = False
    log: list[Fetched] = field(default_factory=list)
    _last: dict = field(default_factory=dict)

    def _cache_path(self, key: str, suffix: str) -> Path | None:
        if self.cache_dir is None:
            return None
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        return Path(self.cache_dir) / f"{day}-{digest}{suffix}"

    def get(self, url: str, params: dict | None = None, *, data: dict | None = None, suffix: str = ".bin",
            cache_name: str | None = None) -> Fetched:
        full = url + ("?" + urllib.parse.urlencode(params) if params else "")
        key = full + ("\n" + json.dumps(data, sort_keys=True) if data else "")
        cpath = None
        if self.cache_dir is not None:
            if cache_name:
                day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                cpath = Path(self.cache_dir) / f"{Path(cache_name).stem}__fetched-{day}{Path(cache_name).suffix}"
            else:
                cpath = self._cache_path(key, suffix)
        if cpath and cpath.exists() and cpath.with_suffix(cpath.suffix + ".json").exists():
            meta = json.loads(cpath.with_suffix(cpath.suffix + ".json").read_text())
            got = Fetched(meta["url"], cpath.read_bytes(), meta["fetched_at"], cached=True)
            self.log.append(got)
            return got
        if self.offline:
            raise SourceError(f"offline and not cached: {full}")
        got = self._request(full, data)
        if cpath:
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_bytes(got.body)
            cpath.with_suffix(cpath.suffix + ".json").write_text(json.dumps(
                {"url": got.url, "fetched_at": got.fetched_at, "sha256": got.sha256}, indent=1))
        self.log.append(got)
        return got

    def _request(self, full: str, data: dict | None) -> Fetched:
        host = urllib.parse.urlsplit(full).netloc
        wait = MIN_INTERVAL_S - (time.monotonic() - self._last.get(host, -1e9))
        if wait > 0:
            time.sleep(wait)
        body = urllib.parse.urlencode(data).encode() if data else None
        error = None
        for attempt in range(RETRIES + 1):
            self._last[host] = time.monotonic()
            req = urllib.request.Request(full, data=body, headers={"User-Agent": USER_AGENT,
                                                                   "Accept": "application/json, text/csv, text/html, */*"})
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (fixed https hosts)
                    return Fetched(full, resp.read(), datetime.now(timezone.utc).isoformat(timespec="seconds"))
            except urllib.error.HTTPError as exc:
                if exc.code == 404:  # DACE answers 404 "Resource not found" for an empty result
                    return Fetched(full, b"", datetime.now(timezone.utc).isoformat(timespec="seconds"))
                error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                error = exc
            time.sleep(2.0 * (attempt + 1))
        raise SourceError(f"{full}: {error}")


# ---------------------------------------------------------------- the Reserved Target List


@dataclass
class RtlEntry:
    name: str
    gaia_id: str | None
    ra: float | None
    dec: float | None
    notes: str
    list_label: str


def _decimal(text: str) -> float | None:
    t = (text or "").strip().strip('"').strip().replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_rtl_csv(raw: bytes, list_label: str) -> tuple[str, list[RtlEntry]]:
    """ESA's RTL CSV: a title line ("CHEOPS GTO Reserved Target List as of DD-MM-YYYY"), a header, then
    ``name;Gaia id;RA [deg];Dec [deg];notes`` rows with semicolons and decimal commas."""
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    if len(rows) < 2:
        raise SourceError("RTL CSV: too few lines")
    title = (rows[0][0] if rows[0] else "").strip()
    entries = []
    for r in rows[2:]:
        if not r or not r[0].strip():
            continue
        r = r + [""] * (5 - len(r))
        gaia = r[1].strip() or None
        entries.append(RtlEntry(r[0].strip(), None if gaia in (None, "-", "N/A") else gaia, _decimal(r[2]),
                                _decimal(r[3]), r[4].strip().strip('"'), list_label))
    return title, entries


def rtl_links(call_html: str) -> list[tuple[str, str]]:
    """(absolute URL, link text) for every RTL CSV linked from the call page, deduplicated in page order."""
    seen, out = set(), []
    for href, label in re.findall(r'href="([^"]*RTL_[^"]*\.csv[^"]*)"[^>]*>(.*?)</a>', call_html, re.S):
        url = urllib.parse.urljoin(COSMOS, href.replace("&amp;", "&"))
        if url in seen:
            continue
        seen.add(url)
        out.append((url, re.sub(r"<[^>]+>|\s+", " ", label).strip()))
    return out


def rtl_file_name(url: str) -> str:
    m = re.search(r"(RTL_[A-Za-z0-9_]+\.csv)", url)
    return m.group(1) if m else "RTL.csv"


def load_rtl(fetcher: Fetcher) -> dict:
    """Every RTL the call page links, downloaded (or from today's cache), parsed, with provenance."""
    page = fetcher.get(CALL_PAGE, suffix=".html")
    links = rtl_links(page.body.decode("utf-8", errors="replace"))
    if not links:
        raise SourceError("no RTL CSV link found on the call page")
    lists = []
    for url, label in links:
        got = fetcher.get(url, cache_name=rtl_file_name(url))
        title, entries = parse_rtl_csv(got.body, rtl_file_name(url))
        lists.append({"file": rtl_file_name(url), "link_text": label, "title": title, "entries": entries,
                      "provenance": got.record(), "fetched": got})
    return {"call_page": page.record(), "lists": lists}


# ---------------------------------------------------------------- coordinates


@dataclass
class Resolved:
    name: str
    main_id: str | None
    ra: float | None
    dec: float | None
    source: str             # "SIMBAD", "MAST (resolver: …)" or "user"
    gmag: float | None = None
    vmag: float | None = None
    sptype: str | None = None
    pmra: float | None = None
    pmdec: float | None = None
    aliases: list[str] = field(default_factory=list)
    coo_ref: str | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("name", "main_id", "ra", "dec", "source", "gmag", "vmag", "sptype",
                                               "pmra", "pmdec", "coo_ref", "note")} | {"n_aliases": len(self.aliases)}


SIMBAD_QUERY = ("SELECT b.main_id, b.ra, b.dec, b.coo_bibcode, b.pmra, b.pmdec, b.sp_type, f.G, f.V, i.ids "
                "FROM basic AS b JOIN ident AS t ON t.oidref = b.oid LEFT JOIN allfluxes AS f ON f.oidref = b.oid "
                "LEFT JOIN ids AS i ON i.oidref = b.oid WHERE t.id = '{name}'")


def parse_simbad(raw: bytes, name: str) -> Resolved | None:
    if not raw:
        return None
    rows = json.loads(raw).get("data") or []
    if not rows:
        return None
    main_id, ra, dec, bib, pmra, pmdec, sp, g, v, ids = rows[0]
    aliases = [" ".join(a.split()) for a in (ids or "").split("|") if a.strip()]
    return Resolved(name, " ".join(str(main_id).split()), ra, dec, "SIMBAD", g, v, sp, pmra, pmdec, aliases, bib,
                    "ICRS, epoch J2000 (SIMBAD basic.ra/dec)")


def resolve_simbad(fetcher: Fetcher, name: str) -> tuple[Resolved | None, Fetched]:
    safe = name.replace("'", "''")
    got = fetcher.get(SIMBAD_TAP, data={"request": "doQuery", "lang": "adql", "format": "json",
                                        "query": SIMBAD_QUERY.format(name=safe)}, suffix=".json")
    return parse_simbad(got.body, name), got


def parse_mast(raw: bytes, name: str) -> Resolved | None:
    if not raw:
        return None
    hits = json.loads(raw).get("resolvedCoordinate") or []
    if not hits:
        return None
    h = hits[0]
    return Resolved(name, h.get("canonicalName"), h.get("ra"), h.get("decl"), f"MAST (resolver: {h.get('resolver')})",
                    note="MAST name lookup; J2000 ICRS position from the named resolver")


def resolve_mast(fetcher: Fetcher, name: str) -> tuple[Resolved | None, Fetched]:
    req = json.dumps({"service": "Mast.Name.Lookup", "params": {"input": name, "format": "json"}})
    got = fetcher.get(MAST_INVOKE, data={"request": req}, suffix=".json")
    return parse_mast(got.body, name), got


def tic_from_aliases(aliases: list[str]) -> int | None:
    for a in aliases:
        m = re.fullmatch(r"TIC\s*(\d+)", a.strip(), re.I)
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------- archive metadata (DACE)


def _dace_columns(raw: bytes) -> dict[str, list]:
    if not raw:
        return {}
    data = json.loads(raw)
    cols = {}
    for p in data.get("parameters", []):
        for k in ("intValues", "doubleValues", "floatValues", "stringValues", "boolValues"):
            if p.get(k) is not None:
                cols[p["variableName"]] = p[k]
                break
    return cols


KEEP_VISIT_FIELDS = ("visit_id", "file_key", "obj_id_catname", "full_program_name", "date_mjd_start", "date_mjd_end",
                     "status_published", "db_lc_available", "ra_deg", "dec_deg", "obj_mag_v")


def parse_dace_visits(raw: bytes) -> list[dict]:
    """Visits from a DACE CHEOPS search answer, keeping public metadata fields only (never the PI's name)."""
    cols = _dace_columns(raw)
    n = len(cols.get("visit_id", []))
    return [{k: cols[k][i] for k in KEEP_VISIT_FIELDS if k in cols and i < len(cols[k])} for i in range(n)]


def dace_cone(fetcher: Fetcher, ra: float, dec: float, radius_deg: float) -> tuple[list[dict], Fetched]:
    flt = json.dumps({"pos": {"ra": ra, "dec": dec, "radius": radius_deg}})
    got = fetcher.get(DACE_CHEOPS, {"limit": "2000", "filters": flt, "sort": "{}"}, suffix=".json")
    return parse_dace_visits(got.body), got


def dace_name(fetcher: Fetcher, name: str) -> tuple[list[dict], Fetched]:
    flt = json.dumps({"obj_id_catname": {"contains": [name]}})
    got = fetcher.get(DACE_CHEOPS, {"limit": "2000", "filters": flt, "sort": "{}"}, suffix=".json")
    return parse_dace_visits(got.body), got


# ---------------------------------------------------------------- published TOI ephemeris


def toi_ephemerides(fetcher: Fetcher, tic: int) -> tuple[list[dict], Fetched]:
    """The TOI table rows for one TIC from the NASA Exoplanet Archive (someone else's published measurement)."""
    q = ("select toi,tid,pl_orbper,pl_orbpererr1,pl_tranmid,pl_tranmiderr1,pl_trandurh,pl_trandep,tfopwg_disp "
         f"from toi where tid={int(tic)}")
    got = fetcher.get(NEA_TAP, {"query": q, "format": "json"}, suffix=".json")
    return (json.loads(got.body) if got.body else []), got

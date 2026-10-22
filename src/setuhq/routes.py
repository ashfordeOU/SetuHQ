# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The site's addresses: one clean path per page, and the map from every old address to its new one.

Every page has a directory of its own with an ``index.html`` (GitHub Pages serves ``/explore/galaxy/`` from
``site/explore/galaxy/index.html``). Inside the app each view is a *route* (``sky``, ``galaxy``, ``transit`` ...),
named as it was when the app lived at ``/app/#/<route>``; this module turns a route and its identifying
parameter (a dip, a planet, a chapter) into its path and back.

* Identity goes in the path: ``/candidates/<dip>/``, ``/planets/<slug>/``, ``/how-it-works/<chapter>/``.
* View state (filters, sorts, layouts) stays out of the address. A deep link may carry it as a short query
  (``/explore/galaxy/?focus=pi%20Men``), and "Copy link to this view" makes one on request.
* Old ``/app/#/...`` addresses (and the aliases the app already honoured) are forwarded by :data:`LEGACY_JS`,
  which runs on ``/app/`` and on ``404.html``; :func:`legacy_target` is its Python twin, used by the tests.

:data:`ROUTES_JS` is the page's copy of :func:`url_for` and :func:`parse_path`; both read the same tables,
which the build passes to the page as JSON.
"""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, quote, urlencode

from setuhq.methods import CHAPTERS

# Fixed paths. The routes with an identity in the path (transit, candidates, planet, star, methods) are below.
ROUTE_PATHS = {
    "overview": "/",
    "sky": "/explore/",
    "galaxy": "/explore/galaxy/",
    "mission": "/explore/mission-control/",
    "catalogue": "/catalogue/",
    "variables": "/catalogue/everything-that-dims/",
    "explorer": "/candidates/",
    "planets": "/candidates/radius-ratios/",
    "methods": "/how-it-works/",
    "sentinels": "/evidence/",
    "leaderboard": "/evidence/leaderboard/",
    "runs": "/evidence/runs/",
    "docs": "/docs/",
}
# The parameter that names the page (it goes in the path, never in the query).
IDENTITY = {"transit": "dip", "candidates": "dip", "planet": "id", "star": "id", "methods": "ch"}
# Readable chapter addresses. The first chapter is the section's own page, /how-it-works/.
CHAPTER_SLUGS = {"survey": "", "transit": "transits", "doppler": "doppler-shift", "rv": "radial-velocity",
                 "astrometry": "astrometry", "microlensing": "microlensing", "imaging": "direct-imaging",
                 "timing": "timing", "radio": "radio", "falsepos": "false-positives", "spectroscopy": "atmospheres",
                 "molecules": "molecules-and-life", "population": "population", "equations": "equations-of-life",
                 "history": "history"}
assert [c for c, _ in CHAPTERS] == list(CHAPTER_SLUGS), "every Methods chapter needs an address"
# Names the app used before (#/discoveries ...), honoured when an old link is forwarded.
ALIASES = {"discoveries": "explorer", "feed": "explorer", "panel": "sentinels", "home": "sky",
           "cockpit": "transit", "about": "overview"}
# Old standalone pages: their new home. A hash on /docket/ names a dip, which gets its own case file.
LEGACY_PAGES = {"/app/": "/", "/docket/": "/candidates/case-file/", "/plate/": "/evidence/plates/",
                "/report/": "/evidence/report/", "/dashboard/": "/candidates/", "/discoveries/": "/candidates/"}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
DIP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
# A dip's readable address, "<star>/dip-<n>" (/candidates/pi-men/dip-2/), by its stored candidate id. The build
# sets it from the run's pinned slugs (setuhq.dipslugs, runs/<run>/slugs.json); an id it does not know keeps its
# own id as the address. GONE_DIPS: addresses once given to a dip that is no longer in the run, which stay 404s.
DIP_SLUGS: dict[str, str] = {}
GONE_DIPS: list[str] = []


def set_dip_slugs(slugs: dict[str, str], gone: list[str] | tuple[str, ...] = ()) -> None:
    DIP_SLUGS.clear()
    DIP_SLUGS.update(slugs)
    GONE_DIPS[:] = sorted(gone)


def _dip_id(star: str, dip: str) -> str | None:
    want = f"{star}/{dip}"
    return next((i for i, s in DIP_SLUGS.items() if s == want), None)


def url_for(route: str, params: dict | None = None, *, keep_query: bool = True) -> str:
    """The clean address of ``route``. The identity parameter goes in the path; with ``keep_query`` the rest
    become a query string (a deep link into a view), otherwise they are dropped."""
    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    route = ALIASES.get(route, route)
    key = IDENTITY.get(route)
    ident = params.pop(key, None) if key else None
    section = params.pop("section", None) if route == "candidates" else None
    if route in ("transit", "candidates"):
        path = "/candidates/" + ((DIP_SLUGS.get(str(ident)) or quote(str(ident), safe="._-")) + "/" if ident else "")
        path += "case-file/" if route == "candidates" and ident else ""
        if route == "candidates" and not ident:
            path = "/candidates/case-file/"
    elif route in ("planet", "star"):
        path = ("/planets/" if route == "planet" else "/stars/") + (str(ident) + "/" if ident else "")
    elif route == "methods":
        slug = CHAPTER_SLUGS.get(str(ident or "survey"), "")
        path = "/how-it-works/" + (slug + "/" if slug else "")
    else:
        path = ROUTE_PATHS.get(route, "/")
    query = urlencode(params) if keep_query and params else ""
    return path + ("?" + query if query else "") + ("#" + str(section) if section else "")


def from_hash(h: str, *, keep_query: bool = True, lead: str | None = None) -> str:
    """An old in-app address (``#/galaxy?focus=x``, ``#/planet/pi-men-c``) as its clean path."""
    body = (h or "").lstrip("#").lstrip("/")
    route, _, query = body.partition("?")
    params = dict(parse_qsl(query, keep_blank_values=False))
    m = re.match(r"^(planet|star)/([a-z0-9-]{1,120})$", route)
    if m:
        route, params["id"] = m.group(1), m.group(2)
    if route not in ROUTE_PATHS and route not in IDENTITY and route not in ALIASES:
        return "/"
    if route == "overview":
        params = {}  # the old Overview carried only its widget layout, which now lives on /candidates/
    if ALIASES.get(route, route) in ("transit", "candidates") and not params.get("dip") and lead:
        params["dip"] = lead  # the old Transit and Case file opened on the lead dip
    return url_for(route, params, keep_query=keep_query)


def parse_path(path: str, query: str = "") -> dict | None:
    """The route and parameters of a clean address, or None when no page has it."""
    parts = [p for p in (path or "/").split("/") if p]
    params = dict(parse_qsl((query or "").lstrip("?")))
    slug_ch = {v: k for k, v in CHAPTER_SLUGS.items()}
    fixed = {v: k for k, v in ROUTE_PATHS.items()}
    norm = "/" + "/".join(parts) + ("/" if parts else "")
    if norm in fixed and norm != "/how-it-works/":
        return {"route": fixed[norm], "params": params}
    if parts[:1] == ["how-it-works"] and len(parts) <= 2:
        ch = slug_ch.get(parts[1] if len(parts) == 2 else "")
        return {"route": "methods", "params": {**params, "ch": ch}} if ch else None
    if len(parts) == 2 and parts[0] in ("planets", "stars") and SLUG_RE.match(parts[1]):
        return {"route": "planet" if parts[0] == "planets" else "star", "params": {**params, "id": parts[1]}}
    if parts[:1] == ["candidates"] and len(parts) in (3, 4) and SLUG_RE.match(parts[1]) and re.match(r"^dip-\d{1,4}$", parts[2]):
        dip = _dip_id(parts[1], parts[2]) or f"{parts[1]}/{parts[2]}"
        if len(parts) == 3:
            return {"route": "transit", "params": {**params, "dip": dip}}
        if parts[3] == "case-file":
            return {"route": "candidates", "params": {**params, "dip": dip}}
    return None


def legacy_target(path: str, hash_: str = "", lead: str | None = None) -> str | None:
    """Where an old address goes: ``/app/#/galaxy`` to ``/explore/galaxy/``, ``/docket/#<dip>`` to that dip's
    case file, ``/plate/`` to ``/evidence/plates/``. None for an address that was never a page."""
    path = path if path.endswith("/") else path + "/"
    if path == "/app/" or path == "/":
        if hash_.startswith("#/") or hash_ in ("#", "#/"):
            return from_hash(hash_, lead=lead)
        return "/" if path == "/app/" else None
    if path == "/docket/" and len(hash_) > 1 and DIP_RE.match(hash_[1:]):
        return url_for("candidates", {"dip": hash_[1:]})
    if path in LEGACY_PAGES:
        return LEGACY_PAGES[path] + (hash_ if hash_ not in ("", "#") else "")
    return None


def route_table(lead: str | None = None) -> dict:
    """The tables the page's copy of these functions reads (``lead``: the run's lead dip, for old links that named none)."""
    return {"paths": ROUTE_PATHS, "identity": IDENTITY, "chapters": CHAPTER_SLUGS, "aliases": ALIASES,
            "legacy": LEGACY_PAGES, "lead": lead, "dips": dict(DIP_SLUGS), "gone": list(GONE_DIPS)}


# The page's twin of url_for, from_hash, parse_path and legacy_target. It expects `RT`, the route table.
ROUTES_CORE_JS = r"""
function rtUrl(route, params, keepQuery){
  params = Object.assign({}, params || {}); for (const k of Object.keys(params)) if (params[k] === null || params[k] === undefined || params[k] === '') delete params[k];
  route = RT.aliases[route] || route;
  const key = RT.identity[route]; let ident = null, section = null, path;
  if (key){ ident = params[key] || null; delete params[key]; }
  if (route === 'candidates'){ section = params.section || null; delete params.section; }
  if (route === 'transit' || route === 'candidates'){
    const slug = ident ? ((RT.dips || {})[ident] || encodeURIComponent(ident)) : null;
    path = slug ? '/candidates/' + slug + '/' + (route === 'candidates' ? 'case-file/' : '') : (route === 'candidates' ? '/candidates/case-file/' : '/candidates/');
  } else if (route === 'planet' || route === 'star'){
    path = (route === 'planet' ? '/planets/' : '/stars/') + (ident ? ident + '/' : '');
  } else if (route === 'methods'){
    const slug = RT.chapters[ident || 'survey'] || '';
    path = '/how-it-works/' + (slug ? slug + '/' : '');
  } else path = RT.paths[route] || '/';
  const q = keepQuery === false ? '' : new URLSearchParams(params).toString();
  return path + (q ? '?' + q : '') + (section ? '#' + section : '');
}
function rtFromHash(h, keepQuery){
  const body = String(h || '').replace(/^#/, '').replace(/^\//, ''), i = body.indexOf('?');
  let route = i < 0 ? body : body.slice(0, i);
  try { route = decodeURIComponent(route); } catch (e) { /* keep as typed */ }
  const params = Object.fromEntries(new URLSearchParams(i < 0 ? '' : body.slice(i + 1)));
  const m = /^(planet|star)\/([a-z0-9-]{1,120})$/.exec(route);
  if (m){ route = m[1]; params.id = m[2]; }
  if (!(route in RT.paths) && !(route in RT.identity) && !(route in RT.aliases)) return '/';
  if (route === 'overview') return '/';
  if (['transit', 'candidates'].includes(RT.aliases[route] || route) && !params.dip && RT.lead) params.dip = RT.lead;
  return rtUrl(route, params, keepQuery);
}
function rtParse(pathname, search){
  const parts = String(pathname || '/').split('/').filter(Boolean), params = Object.fromEntries(new URLSearchParams(search || ''));
  const norm = '/' + parts.join('/') + (parts.length ? '/' : '');
  for (const r in RT.paths) if (RT.paths[r] === norm && norm !== '/how-it-works/') return {route: r, params};
  if (parts[0] === 'how-it-works' && parts.length <= 2){
    const slug = parts[1] || ''; const ch = Object.keys(RT.chapters).find(c => RT.chapters[c] === slug);
    return ch ? {route: 'methods', params: Object.assign(params, {ch})} : null;
  }
  if (parts.length === 2 && (parts[0] === 'planets' || parts[0] === 'stars') && /^[a-z0-9][a-z0-9-]{0,119}$/.test(parts[1]))
    return {route: parts[0] === 'planets' ? 'planet' : 'star', params: Object.assign(params, {id: parts[1]})};
  if (parts[0] === 'candidates' && (parts.length === 3 || parts.length === 4) && /^[a-z0-9][a-z0-9-]{0,119}$/.test(parts[1]) && /^dip-\d{1,4}$/.test(parts[2])){
    const want = parts[1] + '/' + parts[2], dip = Object.keys(RT.dips || {}).find(i => RT.dips[i] === want) || want;
    if (parts.length === 3) return {route: 'transit', params: Object.assign(params, {dip})};
    if (parts[3] === 'case-file') return {route: 'candidates', params: Object.assign(params, {dip})};
  }
  return null;
}
function rtLegacy(pathname, hash){
  let p = String(pathname || '/'); if (!p.endsWith('/')) p += '/';
  hash = hash || '';
  if (p === '/app/' || p === '/'){
    if (hash.startsWith('#/') || hash === '#') return rtFromHash(hash);
    return p === '/app/' ? '/' : null;
  }
  if (p === '/docket/' && hash.length > 1 && /^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/.test(hash.slice(1))) return rtUrl('candidates', {dip: hash.slice(1)});
  if (p in RT.legacy) return RT.legacy[p] + (hash && hash !== '#' ? hash : '');
  return null;
}
"""


def legacy_js(lead: str | None = None) -> str:
    """The forwarding script for /app/ and 404.html: an old address goes to its new page, keeping the history clean."""
    return ("(function(){var RT=" + json.dumps(route_table(lead), separators=(",", ":")) + ";" + ROUTES_CORE_JS
            + "var t=rtLegacy(location.pathname,location.hash);if(t&&t!==location.pathname+location.search+location.hash)"
            "{location.replace(t);}})();")

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The app: every view of the website, the data they read and the script that drives them.

The site (built by :mod:`setuhq.site`) gives each view a page of its own at a clean address (:mod:`setuhq.routes`):
the sky map, the Galaxy, the catalogue and planet and star pages, Everything that dims and Mission Control under
Explore; the candidates (the feed, the run at a glance, a page per dip and its case file, the radius ratios) under
Candidates; the Methods chapters under How it works; the panel, the leaderboard and the runs under Evidence. Inside
the code each view is still named by its old route (``sky``, ``transit``, ``explorer`` ...), and links between
views are written in the old ``#/route?query`` form, which :func:`setuhq.routes.from_hash` (and ``R()`` in the
page) turns into the clean address.

* Candidates: the run's cards (run figures, feed count, recent runs, top candidates). Each card's header hides it,
  moves it and sets its size; the layout lives in localStorage as the viewer's default. "Copy link to this view"
  makes a link that carries it (``/candidates/?layout=kpis.L,top.L,...``); a layout opened from such a link is shown
  for that visit only and never written to storage.
* Case file: the Docket, rendered by :mod:`setuhq.docket`, framed from a file of its own beside the site, with the
  dip as its hash. Its copy carries :data:`FRAME_BRIDGE_JS`, which reports the selected dip and section back, so
  the address follows in-frame navigation. A frame that never reports in is replaced by a message and a link.
* The feed: the discovery catalogue, with histograms and a timeline by star; the Planets view: the radius ratio
  sqrt(depth) per entry (no stellar radius is stored, so nothing is converted to Earth or Jupiter radii).
* The panel: a calibration plane (each reviewer's false-alarm rate against its recall, sized by calibrated weight,
  with lines of constant weight and the sample size stated), which reviewers marked each dip, one card per reviewer.
* Runs: one line per discovery run with its errors, and the configuration. Leaderboard: the real-TOI benchmark's
  public leaderboard (docs/leaderboard/leaderboard.json), its rules and the frozen sample's hash.

Every number on the page is read from the run directory, the catalogue or the reviewer-weights file. Nothing is
fitted or looked up at build time, apart from the Docket's archive cross-match, which reuses crossmatch.json when
it is stored.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

from setuhq import brand
from setuhq.design import BASE_CSS, MOTION_CSS, tokens_css
from setuhq.benchmark_toi import wilson
from setuhq.discover import MAX_FEED_DEPTH_PPM, MIN_FEED_TRANSITS
from setuhq.galaxy import (CSV_NAME, DEFAULT_COVERAGE, DEFAULT_MAP, DEFAULT_NOTABLE, coverage_chips, load_coverage, sky_layers_svg, GALAXY_CSS, GALAXY_JS, TEASER_JS, galaxy_data,
                            galaxy_meta, galaxy_section, map_csv, teaser_points)
from setuhq.catalogue import (CATALOGUE_CSS, CATALOGUE_JS, CATALOGUE_JSON, DEFAULT_CATALOGUE, SEARCH_BUTTON, SEARCH_DIALOG,
                               catalogue_meta, catalogue_section, load_catalogue, mentions, planet_page, star_page, tic_names)
from setuhq.objects import obj_link
from setuhq.everything import (DEFAULT_SWEEP, VARIABLES_CSS, VARIABLES_JS, VARIABLES_JSON, load_sweep, overview_counter, sky_chip, sweep_payload,
                               sky_layer_svg, sweep_meta, tabs as catalogue_tabs, variables_section)
from setuhq.learn import LEARN_BAR, LEARN_CSS, LEARN_JS, learn_steps
from setuhq.mission import GRIDS as MISSION_GRIDS, MISSION_CSS, MISSION_JS, PANES as MISSION_PANES, mission_section
from setuhq.methods import DEFAULT_EXAMPLES, METHODS_CSS, METHODS_JS, load_examples, methods_meta, methods_section, system_stage, CHAPTERS, CHAPTER_PLANETS
from setuhq.codenote import code_note
from setuhq.docket import DOCKET_FONTS_CSS, OUTCOME_LABEL, docket_data, docket_page
from setuhq import dipslugs
from setuhq.names import (ATTRIBUTION, DIP_STATE, PROBES_ONLY, PROVIDER_BY_KIND, dip_count, dip_state, panel_mode, public_text, SENTINEL_KINDS,
                          panel_phrase, reviewer_names, reviewer_provenance)
from setuhq.objects import slugify
from setuhq.routes import ALIASES, from_hash, route_table, set_dip_slugs
from setuhq.story import DEFAULT_TARGETS, decoration, number_words, sky_geometry, story_data
from setuhq.viz import VIZ_JS

# The site's five sections, in the top bar, for its three audiences: visitors (Explore, How it works), researchers
# (Candidates, Evidence) and contributors (Docs). docs/SITE.md gives the reasons. Each section's pages are listed in
# its sub-navigation; every view of the app belongs to one section (overview, the home page, to none).
NAV = [("explore", "Explore", "#/sky"), ("candidates", "Candidates", "#/explorer"), ("how", "How it works", "#/methods"),
       ("evidence", "Evidence", "#/sentinels"), ("docs", "Docs", "#/docs")]
SUBNAV = {
    "explore": [("Sky map", "#/sky", ["sky"]), ("Galaxy", "#/galaxy", ["galaxy"]),
                ("Catalogue", "#/catalogue", ["catalogue", "planet", "star"]),
                ("Everything that dims", "#/variables", ["variables"]), ("Mission Control", "#/mission", ["mission"])],
    "candidates": [("All candidates", "#/explorer", ["explorer"]), ("Dips", "#/transit", ["transit"]),
                   ("Case files", "#/candidates", ["candidates"]), ("Radius ratios", "#/planets", ["planets"])],
    "evidence": [("The panel", "#/sentinels", ["sentinels"]), ("Leaderboard", "#/leaderboard", ["leaderboard"]),
                 ("Runs", "#/runs", ["runs"]), ("Run report", "/evidence/report/", ["report"]), ("Plates", "/evidence/plates/", ["plates"])],
    "docs": [("Get started", "#/docs", ["docs"]), ("How the pictures are drawn", "#/pictures", ["pictures"])],
}
# Every view: its name, its section, its breadcrumbs (deep pages only: a list of (label, address)), and its title.
# A title template's {name} is the page's own heading (a planet, a star, a dip).
ROUTE_META = {
    "overview": {"label": "Home", "nav": None, "title": "SetuHQ: the sky, reviewed"},
    "sky": {"label": "Sky map", "nav": "explore", "title": "Explore the sky · SetuHQ"},
    "galaxy": {"label": "Galaxy", "nav": "explore", "title": "Galaxy · Explore · SetuHQ", "crumbs": [("Explore", "#/sky")]},
    "mission": {"label": "Mission Control", "nav": "explore", "title": "Mission Control · Explore · SetuHQ", "crumbs": [("Explore", "#/sky")]},
    "catalogue": {"label": "Catalogue", "nav": "explore", "title": "Catalogue of known exoplanets · SetuHQ", "crumbs": [("Explore", "#/sky")]},
    "variables": {"label": "Everything that dims", "nav": "explore", "title": "Everything that dims · Catalogue · SetuHQ", "crumbs": [("Explore", "#/sky"), ("Catalogue", "#/catalogue")]},
    "planet": {"label": "Planet", "nav": "explore", "title_tpl": "{name} · Planets · SetuHQ", "crumbs": [("Explore", "#/sky"), ("Catalogue", "#/catalogue")]},
    "star": {"label": "Star", "nav": "explore", "title_tpl": "{name} · Stars · SetuHQ", "crumbs": [("Explore", "#/sky"), ("Catalogue", "#/catalogue")]},
    "explorer": {"label": "Candidates", "nav": "candidates", "title": "Candidates · SetuHQ"},
    "transit": {"label": "Candidate", "nav": "candidates", "title_tpl": "{name} · Candidates · SetuHQ", "crumbs": [("Candidates", "#/explorer")]},
    "candidates": {"label": "Case file", "nav": "candidates", "title_tpl": "Case file for {name} · Candidates · SetuHQ", "crumbs": [("Candidates", "#/explorer")]},
    "planets": {"label": "Radius ratios", "nav": "candidates", "title": "Radius ratios · Candidates · SetuHQ", "crumbs": [("Candidates", "#/explorer")]},
    "methods": {"label": "How it works", "nav": "how", "title_tpl": "{name} · How it works · SetuHQ"},
    "sentinels": {"label": "The panel", "nav": "evidence", "title": "Evidence: the panel, measured · SetuHQ"},
    "leaderboard": {"label": "Leaderboard", "nav": "evidence", "title": "Leaderboard · Evidence · SetuHQ", "crumbs": [("Evidence", "#/sentinels")]},
    "runs": {"label": "Runs", "nav": "evidence", "title": "Runs · Evidence · SetuHQ", "crumbs": [("Evidence", "#/sentinels")]},
    # Pages of their own (built by report.py and plate.py), in the site's header: not views of the app.
    "report": {"label": "Run report", "nav": "evidence", "page": True, "crumbs": [("Evidence", "#/sentinels")]},
    "plates": {"label": "Plates", "nav": "evidence", "page": True, "crumbs": [("Evidence", "#/sentinels")]},
    "docs": {"label": "Docs", "nav": "docs", "title": "Docs: get started with SetuHQ · SetuHQ"},
    "pictures": {"label": "How the pictures are drawn", "nav": "docs", "title": "How the pictures are drawn · Docs · SetuHQ", "crumbs": [("Docs", "#/docs")]},
    "notfound": {"label": "Page not found", "nav": None, "title": "Page not found · SetuHQ"},
}
SECTIONS = [(k, label) for k, label, _ in NAV]
ROUTE_ALIASES = ALIASES  # old in-app names (#/discoveries ...), forwarded by setuhq.routes


def route_meta() -> dict:
    """ROUTE_META for the page's script: crumbs as clean addresses, a title or title template for every view."""
    from setuhq.routes import from_hash

    out = {}
    for r, m in ROUTE_META.items():
        out[r] = {"label": m["label"], "nav": m["nav"],
                  "title_tpl": m.get("title_tpl") or m.get("title") or f"{m['label']} · SetuHQ",
                  "crumbs": [[label, from_hash(h) if h.startswith("#/") else h] for label, h in m.get("crumbs", [])]}
    return out


WIDGETS = [
    ("kpis", "Run figures"),
    ("discoveries", "Feed count"),
    ("runs", "Recent runs"),
    ("top", "Top candidates"),
]
SIZES = ("S", "M", "L")
DEFAULT_SIZE = {"kpis": "L", "discoveries": "M", "runs": "M", "top": "L"}

UNCONFIRMED = "candidate, unconfirmed"


def dip_tag(outcome: str | None) -> str:
    cls, word, phrase = dip_state(outcome)
    return f'<span class="tag {cls}" title="{html.escape(phrase)}">{word}</span>'
NO_DETECTION = "Archive values only. This page claims no detection."
NO_STELLAR_RADIUS = ("No stellar radius is stored in the run or the catalogue, so this page does not "
                     "convert the ratio to a planet radius in Earth or Jupiter units.")
STATUS_LABEL = {"new_candidate": "new candidate", "known_toi": "period matches a known TOI"}
ARCHIVE_FIELDS = ("pl_name", "hostname", "pl_orbper", "tran_flag", "rv_flag", "tic_id")
DEFAULT_WEIGHTS = "docs/results/reviewer_weights_full_panel.json"
RATIO_SCALE_MAX = 0.1  # Planets: every ratio bar runs from 0 to this Rp/R* value, labelled on the page.
# Kshana's families (the Observatory system): Geist for text, Geist Mono for numbers, Unbounded for the
# wordmark. Self-hosted as Kshana does: build_app copies src/setuhq/fonts to <out>/assets/fonts.
FONTS_DIR = Path(__file__).parent / "fonts"
FONTS_CSS = "/assets/fonts/fonts.css"  # every page links the one copy at the site's root
# The shell's copy of the Docket (the case file's frame) is served from assets/frame/; it links the site's fonts.
FRAME_FONTS_HREF = FONTS_CSS


def default_layout() -> list[dict]:
    """Every widget, visible, in the default order, at its default size."""
    return [{"id": wid, "visible": True, "size": DEFAULT_SIZE[wid]} for wid, _ in WIDGETS]


def widget_layout(stored=None) -> list[dict]:
    """A valid layout from whatever storage or the URL held (or ``None`` when absent).

    Unknown ids and repeats are dropped, missing widgets are appended visible,
    unknown sizes fall back to the widget's default, so the result always lists
    each widget exactly once. The page's ``normaliseLayout`` applies the same rule
    in JavaScript.
    """
    ids = [wid for wid, _ in WIDGETS]
    out, seen = [], set()
    if isinstance(stored, list):
        for item in stored:
            if not isinstance(item, dict):
                continue
            wid = item.get("id")
            if wid not in ids or wid in seen:
                continue
            seen.add(wid)
            size = item.get("size") if item.get("size") in SIZES else DEFAULT_SIZE[wid]
            out.append({"id": wid, "visible": item.get("visible") is not False, "size": size})
    out.extend({"id": wid, "visible": True, "size": DEFAULT_SIZE[wid]} for wid in ids if wid not in seen)
    return out


def encode_layout(layout: list[dict]) -> str:
    """The layout as the ``layout=`` value of the URL hash: ``kpis.L,top.L,runs.M.hidden,...``."""
    return ",".join(f"{x['id']}.{x['size']}" + ("" if x["visible"] else ".hidden") for x in widget_layout(layout))


def decode_layout(text) -> list[dict]:
    """Inverse of :func:`encode_layout`; anything malformed falls back as in :func:`widget_layout`."""
    items = []
    for part in str(text or "").split(","):
        bits = part.strip().split(".")
        if not bits[0]:
            continue
        items.append({"id": bits[0], "size": bits[1] if len(bits) > 1 else None,
                      "visible": not (len(bits) > 2 and bits[2] == "hidden")})
    return widget_layout(items)


# The Feed's sort and filter in the URL hash, as #/discoveries?sort=depth&filter=new (with &dir=asc or
# &dir=desc only when the direction is not the column's default). Short names for the URL, keys for the table.
FEED_SORTS = {"tic": "tic", "dip": "candidate_id", "time": "t_center", "period": "period_days",
              "depth": "depth_ppm", "snr": "snr", "status": "status"}
FEED_FILTERS = {"all": "all", "new": "new_candidate", "known": "known_toi"}
FEED_NUMERIC = ("tic", "time", "period", "depth", "snr")
DEFAULT_FEED_VIEW = {"sort": "snr", "dir": "desc", "filter": "all"}


def feed_view(stored=None) -> dict:
    """A valid Feed view (sort, dir, filter) from whatever the URL or storage held.

    Unknown values fall back to the default; a missing direction is the column's default
    (descending for numbers, ascending for text). The page's ``normaliseFeedView`` applies
    the same rule in JavaScript.
    """
    stored = stored if isinstance(stored, dict) else {}
    sort = stored.get("sort") if stored.get("sort") in FEED_SORTS else DEFAULT_FEED_VIEW["sort"]
    default_dir = "desc" if sort in FEED_NUMERIC else "asc"
    direction = stored.get("dir") if stored.get("dir") in ("asc", "desc") else default_dir
    filt = stored.get("filter") if stored.get("filter") in FEED_FILTERS else DEFAULT_FEED_VIEW["filter"]
    return {"sort": sort, "dir": direction, "filter": filt}


def encode_feed_view(view: dict) -> str:
    """The view as the query of the Feed's hash: ``sort=depth&filter=new`` (``&dir=`` only when not the default)."""
    v = feed_view(view)
    default_dir = "desc" if v["sort"] in FEED_NUMERIC else "asc"
    return f"sort={v['sort']}" + ("" if v["dir"] == default_dir else f"&dir={v['dir']}") + f"&filter={v['filter']}"


def decode_feed_view(query) -> dict:
    """Inverse of :func:`encode_feed_view`; anything malformed falls back as in :func:`feed_view`."""
    from urllib.parse import parse_qs

    q = parse_qs(str(query or "").lstrip("?"))
    return feed_view({k: q[k][0] for k in ("sort", "dir", "filter") if q.get(k)})


def feed_label(feed: list[dict]) -> str:
    """'Feed' when most entries match a known TOI, so the name does not claim discovery."""
    known = sum(1 for r in feed if r.get("status") == "known_toi")
    return "Feed" if feed and known * 2 > len(feed) else "Discoveries"


def radius_ratio(depth_ppm) -> float | None:
    """Planet-to-star radius ratio from transit depth, Rp/R* = sqrt(depth); None for a missing or non-positive depth."""
    try:
        depth = float(depth_ppm)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(depth) or depth <= 0:
        return None
    return math.sqrt(depth * 1e-6)


def _tic_label(tic) -> str:
    text = str(tic)
    return text if text.upper().startswith("TIC") else f"TIC {text}"


def planet_cards(run_candidates: list[dict], run_name: str, feed: list[dict], crossmatch: dict) -> list[dict]:
    """One card per star: each stored dip or feed entry with its radius ratio, and the archive planets.

    Only stored values are used. Archive planets keep the fields in ``ARCHIVE_FIELDS``
    (no radii), and only the stars the stored cross-match covered get them.
    """
    stars: dict[str, dict] = {}

    def card(star: str) -> dict:
        return stars.setdefault(star, {"star": star, "sources": [], "entries": [], "archive": None})

    comparison = ((crossmatch or {}).get("comparison") or {}).get("by_candidate") or {}
    for c in run_candidates:
        star = c.get("target") or c["subject_id"]
        entry = card(star)
        if f"run {run_name}" not in entry["sources"]:
            entry["sources"].append(f"run {run_name}")
        entry["entries"].append({
            "source": "run", "id": c["candidate_id"], "depth_ppm": c["depth_ppm"],
            "ratio": radius_ratio(c["depth_ppm"]), "period_days": c.get("period_days"),
            "n_transits": c.get("n_transits"), "t_center": c["t_center"], "time_unit": c["time_unit"],
            "status": OUTCOME_LABEL.get(c.get("outcome"), ""), "outcome": c.get("outcome"),
            "archive_line": (comparison.get(c["candidate_id"]) or {}).get("line", ""),
        })
    for r in feed:
        star = _tic_label(r["tic"])
        entry = card(star)
        if "search feed" not in entry["sources"]:
            entry["sources"].append("search feed")
        entry["entries"].append({
            "source": "feed", "id": r["candidate_id"], "depth_ppm": r["depth_ppm"],
            "ratio": radius_ratio(r["depth_ppm"]), "period_days": r.get("period_days"),
            "n_transits": r.get("n_transits"), "t_center": r["t_center"], "time_unit": r["time_unit"],
            "status": STATUS_LABEL.get(r.get("status"), str(r.get("status", ""))), "archive_line": "",
        })
    status = (crossmatch or {}).get("status", "not_run")
    covered = {str(t).upper() for t in (crossmatch or {}).get("targets") or []}
    planets = (crossmatch or {}).get("planets") or []
    for star, entry in stars.items():
        if star.upper() not in covered:
            entry["archive"] = {"status": "not_stored", "planets": []}
            continue
        mine = [{k: p.get(k) for k in ARCHIVE_FIELDS} for p in planets
                if str(p.get("tic_id", "")).upper() == star.upper() or len(covered) == 1]
        entry["archive"] = {"status": status, "planets": mine, "source": (crossmatch or {}).get("source", ""),
                            "fetched_at": (crossmatch or {}).get("fetched_at", ""), "error": (crossmatch or {}).get("error", ""),
                            "fallback_from": (crossmatch or {}).get("fallback_from", ""),
                            "recorded_commit": (crossmatch or {}).get("recorded_commit", ""),
                            "run_error": (crossmatch or {}).get("run_error", ""),
                            "run_status": (crossmatch or {}).get("run_status", "")}
    for entry in stars.values():
        entry["entries"].sort(key=lambda e: (e["source"] != "run", e["period_days"] is None, e["period_days"] or 0, e["t_center"]))
    return sorted(stars.values(), key=lambda s: (not any(e["source"] == "run" for e in s["entries"]), s["star"]))


def panel_cards(manifest: dict, marks: dict, decisions: dict, calibrated: dict | None,
                dips: list[dict] | None = None) -> list[dict]:
    """One card per reviewer in the run: kind, weight used in the run, calibrated weight, marks.

    ``marked_dips`` lists the consensus dips whose stored reviewer list includes this reviewer.
    """
    out = []
    for r in manifest.get("reviewers", []):
        rid = r["id"]
        n_marks = sum(len(by_rev.get(rid) or []) for by_rev in marks.values())
        labels: dict[str, int] = {}
        for by_rev in decisions.values():
            if rid in by_rev:
                label = by_rev[rid].get("label") or "none"
                labels[label] = labels.get(label, 0) + 1
        out.append({
            "id": rid, "kind": r.get("kind", ""), "run_weight": r.get("weight"),
            "calibrated_weight": (calibrated or {}).get(rid), "n_marks": n_marks,
            "n_subjects": sum(labels.values()), "labels": labels,
            "marked_dips": [d["candidate_id"] for d in dips or [] if rid in (d.get("reviewers") or [])],
        })
    return out


ISO_WEIGHTS = (0.05, 0.2, 0.4, 0.6, 0.8)  # lines of constant weight drawn on the calibration plane


def calibration_plane(weights: dict | None, record: dict | None, kinds: dict[str, str]) -> dict:
    """Points for the Panel's calibration plane: x = false-alarm rate (FPR), y = recall (TPR).

    The weight is the calibrated weight in the weights file. TPR, FPR and the sample size
    are read from the same entry when it is a dict, else from the calibration record stored
    next to the weights file (``calibrate.calibration_path``). Nothing is estimated: a
    reviewer whose rates are not stored has ``tpr`` and ``fpr`` None and is listed, not plotted.
    """
    from setuhq.calibrate import WEIGHT_FLOOR

    rec = (record or {}).get("reviewers") or {}
    points = []
    for rid, entry in (weights or {}).items():
        stored = entry if isinstance(entry, dict) else rec.get(rid) or {}
        weight = entry.get("weight") if isinstance(entry, dict) else entry
        tpr, fpr = stored.get("tpr"), stored.get("fpr")
        floor = (record or {}).get("floor", WEIGHT_FLOOR)
        points.append({
            "id": rid, "kind": kinds.get(rid, "not in this run"), "weight": weight, "tpr": tpr, "fpr": fpr,
            "n_injected": stored.get("n_injected"), "n_empty": stored.get("n_empty"),
            # The stored weight should be max(TPR - FPR, floor); say so when it is not.
            "consistent": None if None in (tpr, fpr, weight) else abs(max(tpr - fpr, floor) - weight) < 1e-9,
        })
    # A Sentinel of this run that the weights file does not cover (a new provider or model) is listed as
    # uncalibrated, with no rates and no point on the plane: it votes at the floor weight until it is calibrated.
    for rid, kind in kinds.items():
        if rid not in (weights or {}) and kind in SENTINEL_KINDS:
            points.append({"id": rid, "kind": kind, "weight": None, "tpr": None, "fpr": None, "n_injected": None,
                           "n_empty": None, "consistent": None, "uncalibrated": True})
    points.sort(key=lambda p: (p["kind"] != "simulated", p["id"]))
    return {"points": points, "iso": list(ISO_WEIGHTS), "floor": (record or {}).get("floor", WEIGHT_FLOOR),
            "source": public_text((record or {}).get("source", "")), "rule": (record or {}).get("rule", "weight = max(TPR - FPR, floor)")}


def dip_agreement(dips: list[dict], kinds: dict[str, str]) -> list[dict]:
    """Per dip: which reviewers marked it, with simulated and Claude counts out of the panel."""
    sim_all = [r for r, k in kinds.items() if k == "simulated"]
    cl_all = [r for r, k in kinds.items() if k in SENTINEL_KINDS]  # every Sentinel, on any provider
    out = []
    for d in dips:
        who = [r for r in kinds if r in (d.get("reviewers") or [])]
        out.append({
            "id": d["candidate_id"], "target": d.get("target", ""), "outcome": d.get("outcome"), "outcome_label": OUTCOME_LABEL.get(d.get("outcome"), ""),
            "reviewers": who, "n": len(who), "of": len(kinds),
            "n_sim": sum(r in sim_all for r in who), "of_sim": len(sim_all),
            "n_claude": sum(r in cl_all for r in who), "of_claude": len(cl_all),
        })
    return out


OUTCOME_ORDER = {"passed": 0, "flagged": 1, "rejected": 2}
MATCH_QUALIFIER = ("Each dip is this pipeline's own candidate, unconfirmed as an independent detection; the archive "
                   "match says the planet is already known, not that this run confirmed it.")


def _letter(i: int) -> str:
    """The i-th marked window's number in time order (1, 2, 3 ...), as in story._letter."""
    return str(i + 1)


def dip_names(cands: list[dict], star_names: dict[str, str], pinned: list[dict] | None = None) -> tuple[dict[str, dict], list[str], list[dict]]:
    """Every dip of the run with its readable address and plain label, numbered per star under its star's name (or
    its TIC): {"tess-…-000": {"n": 2, "slug": "pi-men/dip-2", "label": "pi Men, dip 2 (6.27 d)"}}.

    ``pinned`` (runs/<run>/slugs.json, setuhq.dipslugs) wins: an address stays with its dip (by subject and mid-time,
    not by candidate id, which is a rank), a new dip gets the next free number of its star, and an address whose dip
    left the run is gone, never reused. Returns the names, the gone slugs and the entries to keep."""
    from setuhq.objects import slugify

    def star_of(c: dict) -> str:
        target = c.get("target") or c.get("subject_id") or "star"
        return star_names.get(target) or target

    slugs, gone, entries = dipslugs.pin(cands, pinned or [], lambda c: slugify(star_of(c)), star_of)
    out = {}
    for c in cands:
        slug = slugs[c["candidate_id"]]
        n = int(slug.rpartition("/dip-")[2])
        period = f" ({c['period_days']:.2f} d)" if c.get("period_days") else ""
        out[c["candidate_id"]] = {"n": n, "slug": slug, "label": f"{star_of(c)}, dip {n}{period}", "star": star_of(c)}
    return out, gone, entries


def pin_run_dips(run_dir: str | Path, cands: list[dict], star_names: dict[str, str]) -> tuple[dict[str, dict], list[str]]:
    """dip_names for a run folder: read runs/<run>/slugs.json, pin, and write it back when it changed."""
    pinned = dipslugs.load(run_dir)
    names, gone, entries = dip_names(cands, star_names, pinned)
    dipslugs.save(run_dir, entries, pinned)
    return names, gone


def _median(values: list[float]) -> float | None:
    v = sorted(x for x in values if x is not None and math.isfinite(x))
    if not v:
        return None
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2


def _fmt_num(x: float, d: int) -> str:
    return f"{x:,.{d}f}"


def overview_hero(dock: dict, top: list[dict] | None = None) -> dict:
    """The Overview's argument: the stored light curve, the marked windows and the lead signal.

    The lead signal is the periodic signal with the best vetting outcome, then the highest
    stored SNR. Its depth is the median stored depth of its dips; its period, t0 and duration
    are the stored BLS values. The headline and lede are built from these stored values only
    and always say the signal is a candidate, unconfirmed. Points are rounded for the page
    (time to 1e-5 d, flux to 0.1 ppm); nothing is fitted.
    """
    subjects = sorted(dock.get("subjects", {}).values(), key=lambda s: s["start"])
    cands = sorted(dock.get("candidates", []), key=lambda c: c["t_start"])
    by_id = {c["candidate_id"]: c for c in cands}
    letters = {c["candidate_id"]: _letter(i) for i, c in enumerate(cands)}
    counts = dock.get("counts", {})
    target = next((c.get("target") for c in cands if c.get("target")), "") or "this star"
    unit = (subjects[0].get("time_unit") if subjects else "") or (cands[0]["time_unit"] if cands else "")

    def best_snr(sig: dict) -> float:
        return max((by_id[d]["snr"] for d in sig["dips"] if d in by_id), default=0.0)

    periodic = [s for s in dock.get("signals", []) if s.get("period_days")]
    lead = min(periodic, key=lambda s: (OUTCOME_ORDER.get(s.get("outcome"), 3), -best_snr(s))) if periodic else None
    lead_out = None
    if lead:
        dips = [by_id[d] for d in lead["dips"] if d in by_id]
        ref = next((b for b in lead.get("bls") or [] if b.get("reference")), (lead.get("bls") or [{}])[0])
        top_dip = max(dips, key=lambda c: c["snr"]) if dips else None
        lead_out = {
            "signal_id": lead["signal_id"], "period_days": lead["period_days"], "t0": lead.get("bls_t0"),
            "duration_days": ref.get("bls_duration_days"),
            "depth_ppm": _median([c["depth_ppm"] for c in dips]),
            "n_dips": len(dips), "n_transits": lead.get("n_transits"),
            "outcome": lead.get("outcome"), "outcome_label": OUTCOME_LABEL.get(lead.get("outcome"), ""),
            "dip": top_dip["candidate_id"] if top_dip else None,
            "letters": [letters[c["candidate_id"]] for c in dips],
        }
    match = next((x for x in top or [] if lead_out and x.get("signal_id") == lead_out["signal_id"] and x.get("consistent_with")), None)
    xm = dock.get("crossmatch") or {}

    n_points = sum(len(s["time"]) for s in subjects)
    span = (subjects[-1]["end"] - subjects[0]["start"]) if subjects else 0.0
    accent = "Candidate, unconfirmed."
    if lead_out and lead_out["depth_ppm"]:
        headline = (f"A {_fmt_num(lead_out['depth_ppm'], 0)} ppm dip every "
                    f"{_fmt_num(lead_out['period_days'], 2)} days in {target}")
        if match:
            # The archive already lists a planet at this period: say so in the headline itself.
            headline += f", consistent with {match['consistent_with']}."
            accent = "A known planet, not a discovery."
        else:
            headline += "."
    else:
        headline = f"{len(cands)} marked dip{'s' if len(cands) != 1 else ''} in {target}."
    lede = (f"{n_points:,} stored brightness measurements over {span:.1f} days. "
            f"The panel, {panel_phrase(counts.get('claude', 0), counts.get('simulated', 0), counts.get('other', 0))} "
            f"(no people), marked {counts.get('dips', len(cands))} dips, "
            f"which the vetting code grouped into {counts.get('signals', 0)} signals: {counts.get('passed', 0)} passed, "
            f"{counts.get('flagged', 0)} flagged, {counts.get('rejected', 0)} rejected.")
    where = " (the repository's stored copy)" if xm.get("fallback_from") else ""
    if match:
        archive = (f"The stored archive cross-match{where} finds the lead signal consistent with {match['consistent_with']}, "
                   f"a published planet: a known planet, not a discovery. {NO_DETECTION}")
    elif xm.get("status") == "not_run":
        archive = (f"No archive cross-match is stored for this build, so this page does not say whether a published "
                   f"planet matches the lead signal. Stored error, verbatim: {xm.get('error') or 'none stored'}")
    elif xm.get("status") == "no_match":
        archive = f"No published planet in the stored archive cross-match matches the lead signal. {NO_DETECTION}"
    else:
        archive = "No archive cross-match is stored for this run."
    # With an archive match the headline names a known planet; the lede says what that does and does not mean.
    qualifier = (MATCH_QUALIFIER if match else f"Every one is a {UNCONFIRMED}.")
    return {
        "target": target, "time_unit": unit, "n_points": n_points, "span_days": span,
        "headline": headline, "accent": accent, "lede": lede, "archive": archive, "qualifier": qualifier,
        "match": match["consistent_with"] if match else None,
        "subjects": [{"id": s["subject_id"], "start": s["start"], "end": s["end"],
                      "t": [round(t, 5) for t in s["time"]],
                      "ppm": [round((f - 1.0) * 1e6, 1) for f in s["flux"]]} for s in subjects],
        "windows": [{"id": c["candidate_id"], "letter": letters[c["candidate_id"]], "t_start": c["t_start"],
                     "t_end": c["t_end"], "outcome": c.get("outcome"), "snr": c["snr"], "depth_ppm": c["depth_ppm"],
                     "lead": bool(lead_out and c.get("signal_id") == lead_out["signal_id"])} for c in cands],
        "lead": lead_out,
    }


# Added to the shell's copy of the Docket only (the standalone page in site/docket is untouched).
# Inside a frame it tells the shell which dip and section are showing, by postMessage, so the
# shell's address bar and "Open full page" link follow in-frame navigation even when the frame
# is cross-origin (file://). It also lets the shell select a dip and scroll to a section.
FRAME_BRIDGE_JS = r"""
(function(){
  if (window.parent === window) return;
  var P = window.parent, SECS = ['strip', 'signal', 'ctx', 'cmp', 'ledger', 'rev'], lastSec = null, timer = null;
  function selected(){ try { return typeof state !== 'undefined' ? state.selected : null; } catch (e) { return null; } }
  function send(m){ m.source = 'setuhq-docket'; m.dip = m.dip || selected(); try { P.postMessage(m, '*'); } catch (e) {} }
  // A srcdoc frame cannot change its own URL (replaceState throws a SecurityError). The Docket
  // catches that itself, so the wrapper swallows it too, and the dip is reported either way.
  var replace = history.replaceState;
  history.replaceState = function(){
    var r, failed = false;
    try { r = replace.apply(this, arguments); } catch (e) { failed = true; }
    send({kind: 'dip', urlFailed: failed});
    return r;
  };
  function scroller(el){
    for (var p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement){
      var s = getComputedStyle(p); if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight) return p;
    }
    return document.scrollingElement || document.documentElement;
  }
  function scrollToSection(key){
    var s = document.getElementById('sec-' + key); if (!s) return;
    var sc = scroller(s), top = s.getBoundingClientRect().top;
    if (sc !== document.scrollingElement && sc !== document.documentElement) top -= sc.getBoundingClientRect().top;
    sc.scrollTop += top;  // no scrollIntoView, which would also scroll the shell around the frame
  }
  // The section at the top of the view: null at the top of the page, else the first section header
  // in the upper three quarters, else the section the view is inside.
  function currentSection(){
    var h = window.innerHeight, inside = null;
    if (window.scrollY < 5) return null;
    for (var i = 0; i < SECS.length; i++){
      var s = document.getElementById('sec-' + SECS[i]); if (!s) continue;
      var t = s.getBoundingClientRect().top;
      if (t >= -10 && t < h * 0.75) return SECS[i];
      if (t < -10) inside = SECS[i];
    }
    return inside;
  }
  function reportSection(){ var k = currentSection(); if (k !== lastSec){ lastSec = k; send({kind: 'section', section: k}); } }
  window.addEventListener('scroll', function(){ clearTimeout(timer); timer = setTimeout(reportSection, 150); });
  window.addEventListener('hashchange', function(){
    var h = decodeURIComponent(location.hash.slice(1));
    if (h.indexOf('sec-') === 0 && SECS.indexOf(h.slice(4)) >= 0){ lastSec = h.slice(4); send({kind: 'section', section: lastSec}); }
    else send({kind: 'dip'});
  });
  window.addEventListener('message', function(e){
    var m = e.data; if (e.source !== P || !m || m.source !== 'setuhq-shell') return;
    if (m.dip && m.dip !== selected() && typeof select === 'function') select(m.dip, false);
    if (m.section && SECS.indexOf(m.section) >= 0){ scrollToSection(m.section); lastSec = m.section; }
    if (m.theme === 'light' || m.theme === 'dark' || m.theme === 'system') document.documentElement.setAttribute('data-theme', m.theme);
  });
  // The phone list (Signals jump, accordion, dip picker) is the Docket's own now, in both copies.
  document.addEventListener('DOMContentLoaded', function(){
    send({kind: 'ready'});
  });
})();
"""


# Also only in the shell's copy: on a phone-width frame the Docket's small controls become 44 px
# targets (min-height and padding, same font size). The standalone Docket page is unchanged.
# The phone rules (44 px targets, the Signals jump, the accordion) now ship in the Docket itself
# (docket.DOCKET_CSS), so the standalone page has them too; the shell adds nothing for phones.
FRAME_PHONE_CSS = ""


# Also only in the shell's copy: the Docket in the shell's family dress (Kshana's Observatory tokens and
# Geist type), so the framed page reads as part of the app. Same layout and rules; only colour and type change.
DOCKET_FONTS = DOCKET_FONTS_CSS  # the standalone Docket's own (self-hosted) font stylesheet
FRAME_THEME_CSS = (
    # The shell's dark-first palette: black ground, near-white ink, system colours; a light variant on request.
    ":root{--paper:#000;--ink:#F5F5F7;--rule:rgba(255,255,255,.14);--muted:#8E8E93;--fit:#0A84FF;--pass:#30D158;"
    "--flag:#FFD60A;--reject:#FF453A;--panel:#1C1C1E;--sel:rgba(255,255,255,.08);--cons:#F5F5F7;color-scheme:dark}"
    ":root[data-theme=\"light\"]{--paper:#F5F5F7;--ink:#1D1D1F;--rule:rgba(0,0,0,.14);--muted:#6E6E73;--fit:#0066CC;"
    "--pass:#1F7A35;--flag:#8A6100;--reject:#C9001B;--panel:#FFFFFF;--sel:rgba(0,0,0,.06);--cons:#1D1D1F;color-scheme:light}"
    "@media (prefers-color-scheme: light){:root[data-theme=\"system\"]{--paper:#F5F5F7;--ink:#1D1D1F;--rule:rgba(0,0,0,.14);"
    "--muted:#6E6E73;--fit:#0066CC;--pass:#1F7A35;--flag:#8A6100;--reject:#C9001B;--panel:#FFFFFF;--sel:rgba(0,0,0,.06);"
    "--cons:#1D1D1F;color-scheme:light}}"
    "body{-webkit-font-smoothing:antialiased;letter-spacing:-.01em}"
)


def with_frame_bridge(docket_html: str) -> str:
    """The Docket page with the shell's fonts and tokens, :data:`FRAME_PHONE_CSS` and :data:`FRAME_BRIDGE_JS`.

    The bridge does nothing outside a frame; the phone rule and the family dress apply to this copy only."""
    themed = (docket_html.replace(DOCKET_FONTS, FRAME_FONTS_HREF)
              .replace('"Inter Tight"', '"Geist"').replace('"JetBrains Mono"', '"Geist Mono"'))
    return themed.replace(
        "</head>", f"<style>{FRAME_THEME_CSS}{FRAME_PHONE_CSS}</style><script>{FRAME_BRIDGE_JS}</script></head>", 1)


DEFAULT_SHOWCASE = "docs/results/showcase.json"


def load_showcase(path: str | Path | None = DEFAULT_SHOWCASE) -> dict[str, dict]:
    """The example runs' descriptions (docs/results/showcase.json), by run name; {} when the file is absent."""
    if path is None or not Path(path).exists():
        return {}
    return {r["run"]: r for r in json.loads(Path(path).read_text()).get("runs") or []}


def _top_rows(dock: dict) -> list[dict]:
    """The run's five highest-SNR dips, each with its archive match, as the Candidates cards and the hero read them."""
    cands = dock["candidates"]
    comparison = ((dock.get("crossmatch") or {}).get("comparison") or {}).get("by_candidate") or {}
    per_signal: dict[str, int] = {}
    for c in cands:
        per_signal[c.get("signal_id", "")] = per_signal.get(c.get("signal_id", ""), 0) + 1

    def archive_match(cid: str) -> dict:
        cmp = comparison.get(cid) or {}
        name = cmp.get("consistent_with")
        hit = next((p for p in cmp.get("planets") or [] if p.get("pl_name") == name), {}) if name else {}
        return {"consistent_with": name, "dP_pct": hit.get("dP_pct"), "pl_orbper": hit.get("pl_orbper"),
                "archive_line": cmp.get("line", "")}

    return [{"id": c["candidate_id"], "target": c.get("target", ""), "depth_ppm": c["depth_ppm"], "snr": c["snr"],
             "period_days": c.get("period_days"), "outcome": c["outcome"],
             "outcome_label": OUTCOME_LABEL[c["outcome"]], "signal_id": c.get("signal_id", ""),
             "signal_dips": per_signal.get(c.get("signal_id", ""), 1), **archive_match(c["candidate_id"])}
            for c in sorted(cands, key=lambda c: -c["snr"])[:5]]


def example_run(run_dir: str | Path, *, title: str, require_crossmatch: bool = False,
                targets_path: str | Path | None = DEFAULT_TARGETS, calibrated: dict | None = None,
                record: dict | None = None) -> dict:
    """One more stored run for the site, beside the lead: its case file's data, its dips (named and pinned to their
    addresses, setuhq.dipslugs) and the same per-dip story the lead's dips have. Stored files only."""
    run_dir = Path(run_dir)
    dock = docket_data(run_dir, title=f"{title} · candidates", require_crossmatch=require_crossmatch)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    name = manifest.get("config_name") or run_dir.name
    hero = overview_hero(dock, _top_rows(dock))
    calib = calibration_plane(calibrated, record, dock["reviewers"])
    story = story_data(run_dir, dock, [], calib, hero, targets_path=targets_path)
    names, gone = pin_run_dips(run_dir, dock["candidates"],
                               {story["star"]["target"]: story["star"]["name"]} if story["star"].get("name") else {})
    for d in names.values():
        d["run"] = name
    for d in story["dips"]:
        d["letter"] = str(names[d["id"]]["n"]) if d["id"] in names else d["letter"]
        d["run"] = name
    star = story["star"]["name"] or story["star"]["target"] or name
    return {"run": name, "dir": str(run_dir), "manifest": manifest, "story": story, "hero": hero, "dock": dock,
            "names": names, "gone": gone, "slug": slugify(star), "lead": False}


def example_paths(x: dict) -> dict:
    """Where an example run's stand-alone pages live: the lead's at the site's first addresses, the others under
    their star's address."""
    if x.get("lead"):
        return {"case_file": "/candidates/case-file/", "plates": "/evidence/plates/", "report": "/evidence/report/"}
    slug = x.get("slug") or slugify(x["story"]["star"]["name"] or x["run"])
    return {"case_file": f"/candidates/{slug}/case-file/", "plates": f"/evidence/plates/{slug}/",
            "report": f"/evidence/report/{slug}/"}


def run_star(run_dir: str | Path, target: str) -> dict:
    """The run's star as its stellar.json stores it (the TIC's Teff and radius), or {} when it is not stored."""
    path = Path(run_dir) / "stellar.json"
    if not path.exists():
        return {}
    s = (json.loads(path.read_text()) or {}).get(target) or {}
    return {"teff": s.get("teff"), "radius": s.get("radius"), "source": s.get("source") or ""} if s else {}


def run_context(x: dict) -> dict:
    """What a dip's page needs from its own run: the star (its TIC Teff and radius), the planet the archive matches,
    the lead signal, what the run did not recover, which dips carry a BLS period that is not their planet's, and
    where its case file is."""
    st = x["story"]
    meta = x.get("meta") or {}
    return {"run": x["run"], "star": st["star"], "star_params": run_star(x["dir"], st["star"].get("target") or ""),
            "planet": st.get("planet"), "lead": x["hero"].get("lead"),
            "lead_dip": st.get("lead_dip"), "probes_only": panel_mode(x["manifest"]) == "probes_only",
            "caveat": meta.get("caveat") or "", "period_wrong": list(meta.get("bls_period_not_planets") or []),
            **example_paths(x)}


def example_card(x: dict, meta: dict) -> dict:
    """One example run as the home page's gallery and the Candidates page show it: the star, what kind of example it
    is (docs/results/showcase.json), its dips counted by outcome, its panel, and its addresses."""
    st, m = x["story"], x["manifest"]
    dips = sorted(st["dips"], key=lambda d: int(d.get("letter") or 0))
    outcomes = [d.get("outcome") for d in dips]
    sectors = sorted({i.get("sector") for i in m.get("inputs") or [] if i.get("sector") is not None})
    star = st["star"]["name"] or st["star"]["target"] or x["run"]
    lead_dip = st.get("lead_dip") or (dips[0]["id"] if dips else None)
    mode = panel_mode(m)
    return {
        "run": x["run"], "star": star, "target": st["star"]["target"], "slug": slugify(star),
        "kind": meta.get("kind") or "", "summary": meta.get("summary") or "", "why": meta.get("why") or "",
        "caveat": meta.get("caveat") or "",
        "outcome_line": meta.get("outcome") or "", "reference": meta.get("reference") or "",
        "planet": st.get("planet"), "sectors": sectors, "mission": "TESS",
        "n_dips": len(dips), "count": dip_count(outcomes),
        "counts": {k: sum(1 for o in outcomes if dip_state(o)[1] == w) for k, w in
                   (("candidates", "candidate"), ("flagged", "flagged"), ("rejected", "rejected"))},
        "panel": mode, "panel_label": PROBES_ONLY if mode == "probes_only" else "Probes and Sentinels",
        "lead": bool(x.get("lead")), "lead_dip": lead_dip,
        # Provenance: each input file's hash, the configuration's hash and the code that ran.
        "inputs": [{"file": i.get("file"), "file_sha256": i.get("file_sha256"), "sector": i.get("sector")} for i in m.get("inputs") or []],
        "config_sha256": m.get("config_sha256", ""), "code": m.get("code") or "", "created_at": m.get("created_at", ""),
        "dips": [{"id": d["id"], "n": int(d.get("letter") or 0), "outcome": d.get("outcome"), "status_label": d.get("status_label", ""),
                  "depth_ppm": d.get("depth_ppm"), "snr": d.get("snr"), "period_days": d.get("period_days"),
                  "label": (x["names"].get(d["id"]) or {}).get("label") or f"{star}, dip {d.get('letter')}"} for d in dips],
        **example_paths(x),
    }


def app_data(run_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
             weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None,
             require_crossmatch: bool = False, targets_path: str | Path | None = DEFAULT_TARGETS,
             map_path: str | Path | None = DEFAULT_MAP, notable_path: str | Path | None = DEFAULT_NOTABLE,
             coverage_path: str | Path | None = DEFAULT_COVERAGE, examples_path: str | Path | None = DEFAULT_EXAMPLES,
             catalogue_path: str | Path | None = DEFAULT_CATALOGUE, sweep_path: str | Path | None = DEFAULT_SWEEP,
             extra_runs: list[str | Path] | tuple = (), showcase_path: str | Path | None = DEFAULT_SHOWCASE) -> dict:
    """Everything the shell shows, read from stored files only.

    ``run_dir`` is the lead run (the sky map, the panel and the home page's reference check are drawn from it);
    ``extra_runs`` are the other stored example runs. Every run's dips get a page, a case file and a card in the
    home page's gallery, grouped by star; ``showcase_path`` (docs/results/showcase.json) describes each run.

    With ``require_crossmatch`` the build fails (``CrossmatchUnavailable``) when no stored archive
    cross-match is usable, instead of building a page that cannot say what the archive knows."""
    run_dir = Path(run_dir)
    dock = docket_data(run_dir, title=f"{title} · candidates", star=star, require_crossmatch=require_crossmatch)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    catalog = {"candidates": [], "runs": []}
    catalog_name = ""
    if catalog_path is not None and Path(catalog_path).exists():
        catalog = json.loads(Path(catalog_path).read_text())
        catalog_name = str(catalog_path)
    calibrated, weights_name, record, record_name = None, "", None, ""
    if weights_path is not None and Path(weights_path).exists():
        from setuhq.calibrate import calibration_path

        calibrated = json.loads(Path(weights_path).read_text())
        weights_name = str(weights_path)
        if calibration_path(weights_path).exists():
            record = json.loads(calibration_path(weights_path).read_text())
            record_name = str(calibration_path(weights_path))
    # A weights entry may be a bare weight or a dict holding it with its rates.
    flat = {k: (v.get("weight") if isinstance(v, dict) else v) for k, v in (calibrated or {}).items()} if calibrated else None
    from setuhq.dashboard import _load_run

    run = _load_run(run_dir)
    feed = catalog.get("candidates") or []
    run_name = manifest.get("config_name") or run_dir.name
    cands = dock["candidates"]
    crossmatch = dock.get("crossmatch") or {}
    top_rows = _top_rows(dock)
    hero = overview_hero(dock, top_rows)
    calib = {**calibration_plane(calibrated, record, dock["reviewers"]), "record_path": record_name}
    story = story_data(run_dir, dock, feed, calib, hero, targets_path=targets_path)
    dips, gone = pin_run_dips(run_dir, cands, {story["star"]["target"]: story["star"]["name"]} if story["star"].get("name") else {})
    for d in dips.values():
        d["run"] = run_name
    meta = load_showcase(showcase_path)
    extras = [example_run(r, title=title, require_crossmatch=require_crossmatch, targets_path=targets_path,
                          calibrated=calibrated, record=record) for r in extra_runs or ()]
    for x in extras:
        clash = {d["slug"] for d in x["names"].values()} & {d["slug"] for d in dips.values()}
        if clash:
            raise ValueError(f"run {x['run']}: dip addresses already taken by another run: {sorted(clash)}")
        dips.update(x["names"])
        gone = list(gone) + list(x["gone"])
    set_dip_slugs({i: d["slug"] for i, d in dips.items()}, gone)
    # The dip numbers the page shows (the chips, the picker) are the address numbers.
    for w in hero.get("windows") or []:
        if w["id"] in dips:
            w["letter"] = str(dips[w["id"]]["n"])
    for d in story.get("dips") or []:
        if d["id"] in dips:
            d["letter"] = str(dips[d["id"]]["n"])
        d["run"] = run_name
    # A dip whose stored BLS period is known not to be its planet's (docs/results/showcase.json) is named without it.
    for x in meta.values():
        for i in x.get("bls_period_not_planets") or []:
            if i in dips:
                dips[i]["label"] = f'{dips[i]["star"]}, dip {dips[i]["n"]}'
    lead_example = {"run": run_name, "dir": str(run_dir), "manifest": manifest, "story": story, "hero": hero, "dock": dock,
                    "names": {i: d for i, d in dips.items() if d.get("run") == run_name}, "lead": True}
    for x in [lead_example] + extras:
        x["meta"] = meta.get(x["run"]) or {}
        if x["meta"].get("caveat"):
            x["dock"]["caveat"] = x["meta"]["caveat"]
        if x["meta"].get("bls_period_not_planets"):
            x["dock"]["period_wrong"] = list(x["meta"]["bls_period_not_planets"])
    showcase = [example_card(x, meta.get(x["run"]) or {}) for x in [lead_example] + extras]
    # The order docs/results/showcase.json gives (a run it does not list keeps its place after those it does).
    order = list(meta)
    showcase.sort(key=lambda c: order.index(c["run"]) if c["run"] in order else len(order))
    galaxy = galaxy_data(map_path, notable_path, coverage_path=coverage_path, setuhq_star=story["star"]["name"] or "pi Men",
                         setuhq_planet=story.get("planet"), lead_dip=story.get("lead_dip"))
    out = {
        "title": title,
        "nav": [{"id": k, "label": label, "href": from_hash(h)} for k, label, h in NAV],
        "route_meta": route_meta(),
        "subnav": {k: [[label, h, routes] for label, h, routes in v] for k, v in SUBNAV.items()},
        "routes": route_table(lead=dock["candidates"] and (story.get("lead_dip") or dock["candidates"][0]["candidate_id"]) or None),
        "chapter_titles": dict(CHAPTERS),
        "widgets": [{"id": w, "label": label} for w, label in WIDGETS],
        "default_layout": default_layout(),
        "default_size": DEFAULT_SIZE,
        "unconfirmed": UNCONFIRMED,
        "dip_state": DIP_STATE,
        "no_detection": NO_DETECTION,
        "no_stellar_radius": NO_STELLAR_RADIUS,
        "ratio_scale_max": RATIO_SCALE_MAX,
        "dossier_ids": [c["candidate_id"] for c in cands] + [i for x in extras for i in x["names"]],
        "dips": dips,
        # Every stored example run, the lead first: its card (home page, Candidates), its dips and its case file.
        "showcase": showcase,
        "showcase_source": str(showcase_path) if meta else "",
        "showcase_dips": [d for x in extras for d in x["story"]["dips"]],
        "run_ctx": {x["run"]: run_context(x) for x in [lead_example] + extras},
        "docket_frames": {},  # each run's framed case file, by run name, set by the site builder
        "extra_docket_html": {x["run"]: with_frame_bridge(docket_page(x["dock"])) for x in extras},
        "showcase_meta": {x["run"]: {"caveat": x["meta"].get("caveat") or ""} for x in [lead_example] + extras},
        "extra_runs": [{"run": x["run"], "dir": x["dir"], "slug": x["slug"], "star": x["story"]["star"]["name"] or x["run"]} for x in extras],
        "run": {
            "name": run_name, "dir": str(run_dir), "created_at": manifest.get("created_at", ""),
            "counts": manifest.get("counts", {}),
            "docket_counts": dock["counts"],
            "reviewer_kinds": dock["reviewers"],
            "top": top_rows,
        },
        "config": {
            "config_name": manifest.get("config_name", ""), "config_sha256": manifest.get("config_sha256", ""),
            "setuhq_version": manifest.get("setuhq_version") or manifest.get("exoplan_version", ""), "python": manifest.get("python", ""),
            "platform": manifest.get("platform", ""), "packages": manifest.get("packages", {}),
            "claude_prompt_version": manifest.get("claude_prompt_version", ""),
            "subject_days": manifest.get("subject_days"), "inputs": manifest.get("inputs", []),
            "skipped_reviewers": manifest.get("skipped_reviewers", []),
            "skipped_reviewers_detail": manifest.get("skipped_reviewers_detail", []),
        },
        "catalog": {
            "path": catalog_name, "updated": catalog.get("updated", ""), "config": catalog.get("config", ""),
            "config_sha256": catalog.get("config_sha256", ""), "targets_reviewed": catalog.get("targets_reviewed", 0),
            "candidates": feed, "runs": catalog.get("runs") or [],
            "found_times": sorted({str(r["found"]) for r in feed if r.get("found")}),
        },
        "feed_rule": {"max_depth_ppm": MAX_FEED_DEPTH_PPM, "min_transits": MIN_FEED_TRANSITS},
        "feed_view": {"sorts": FEED_SORTS, "filters": FEED_FILTERS, "numeric": list(FEED_NUMERIC),
                      "default": DEFAULT_FEED_VIEW},
        "status_label": STATUS_LABEL,
        "hero": hero,
        "story": story,
        "galaxy": galaxy,
        "coverage": load_coverage(coverage_path),
        "examples": load_examples(examples_path),
        "galaxy_meta": galaxy_meta(galaxy),
        "learn": learn_steps(),
        "benchmark": _load_benchmark(),
        "leaderboard": _load_leaderboard(),
        "mission": {"panes": MISSION_PANES, "grids": MISSION_GRIDS},
        "catalogue": (cat := load_catalogue(catalogue_path)),
        "tic_names": tic_names(cat, [r["tic"] for r in feed], story["star"]),
        # The sweep's catalogue: the counts and rules in the page, every entry in assets/data/variables.json.
        "sweep_full": (sw := load_sweep(sweep_path)),
        "sweep": sweep_meta(sw, cat, str(sweep_path or "")),
        "catalogue_meta": catalogue_meta(cat, galaxy["methods"] if galaxy else None, galaxy["method_label"] if galaxy else None,
                                         {e["name"]: [e["ref"], e["ref_label"]] for e in (galaxy or {}).get("notable", [])},
                                         mentions((galaxy or {}).get("notable"), CHAPTERS, CHAPTER_PLANETS, story)),
        "galaxy_teaser": teaser_points(galaxy),
        "sky_geo": sky_geometry(story["star"]["ra_deg"], story["star"]["dec_deg"]),
        "deco": decoration(),
        "planets": planet_cards(cands, run_name, feed, crossmatch),
        "crossmatch_line": crossmatch.get("line", ""),
        "crossmatch_targets": crossmatch.get("targets") or [],
        "crossmatch_file": crossmatch.get("fallback_from") or "crossmatch.json in the run",
        "crossmatch_info": {"file": crossmatch.get("fallback_from") or str(run_dir / "crossmatch.json"),
                            "fallback": bool(crossmatch.get("fallback_from")), "status": crossmatch.get("status", "not_run"),
                            "run_status": crossmatch.get("run_status", ""), "run_error": crossmatch.get("run_error", ""),
                            "error": crossmatch.get("error", "")},
        "panel": panel_cards(manifest, run["marks"], run["reviewerDecisions"], flat, cands),
        "calibration": calib,
        "agreement": dip_agreement(cands, dock["reviewers"]),
        "reviewer_names": reviewer_names(dock["reviewers"]),
        "reviewer_provenance": reviewer_provenance(manifest),
        "sentinel_kinds": list(SENTINEL_KINDS),
        "provider_by_kind": PROVIDER_BY_KIND,
        "attribution": ATTRIBUTION,
        "probes_only_label": PROBES_ONLY,
        "weights_path": weights_name,
        "docket_html": with_frame_bridge(docket_page(dock)),
        "docket_frame": "",  # the address of the framed copy, set by the site builder
        "code_note": code_note(run_dir) or catalog.get("code_note"),
    }
    # A star or planet link only where the site has its page: the catalogue (exoplanet.eu) may not list every
    # example star (a false-positive host has no planet; a catalogue snapshot may lack one).
    stars = set(((cat or {}).get("stars") or {}).get("slugs") or [])
    planets = set(((cat or {}).get("planets") or {}).get("name") or [])
    for ctx in out["run_ctx"].values():
        ctx["star_page"] = bool(ctx["star"].get("name")) and slugify(ctx["star"]["name"]) in stars
        ctx["planet_page"] = bool(ctx.get("planet")) and ctx["planet"] in planets
    return out


APP_CSS = """
/* The approved design: an observatory-dark ground (light variant with the same names), hairlines, Geist with bold
   tight headlines and a grey second line, and system colours: blue for a known planet, yellow for open, red for
   rejected, cyan for the Sentinels, purple for the Probes, amber for the star. The tokens, the stage component and
   the motion rules come from setuhq.design (one source for the site, the stand-alone pages and the README figures);
   stages ("space" panels, planet art) stay black in both themes. */
""" + tokens_css() + BASE_CSS + MOTION_CSS + """*{box-sizing:border-box}
html{background:var(--bg);-webkit-text-size-adjust:100%;text-size-adjust:100%}
html,body{margin:0;overflow-x:hidden}
body{background:transparent;color:var(--ink);font:400 15px/1.5 var(--sans);letter-spacing:-.01em;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
.mono,code,pre{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:0}
:focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:8px}
::selection{background:var(--blue);color:#fff}
a{color:var(--cyan);text-underline-offset:3px;text-decoration-thickness:1px}
a:hover{color:var(--ink)}
.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:12px;top:-60px;background:var(--btn-bg);color:var(--btn-ink);padding:11px 14px;border-radius:999px;z-index:50;display:inline-flex;align-items:center;min-height:44px;text-decoration:none}
.skip:focus{top:12px}
#content:focus{outline:none}
/* the top bar: brand, the pill section switcher, the run, the theme control */
.topbar{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 18px;padding:8px clamp(16px,3vw,32px);background:color-mix(in oklab,var(--bg) 62%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);border-bottom:1px solid var(--line)}
.brand{display:inline-flex;align-items:center;gap:9px;height:44px;min-height:44px;line-height:0;position:relative;padding:0 4px;color:var(--ink);text-decoration:none;font-weight:600;font-size:17px;letter-spacing:-.02em}
.brand:hover{color:var(--ink)}
.nav ul{list-style:none;margin:0;display:flex;gap:2px;padding:3px;border-radius:999px;background:var(--panel-2);border:1px solid var(--line)}
.nav a{display:flex;align-items:center;min-height:36px;padding:0 16px;border-radius:999px;color:var(--ink-2);text-decoration:none;font-size:13px;font-weight:500;white-space:nowrap;transition:background-color var(--d-1) var(--ease),color var(--d-1) var(--ease)}
.nav a:hover{color:var(--ink)}
.nav a[aria-current="page"]{background:var(--seg-bg);color:var(--seg-ink)}
main{min-width:0;padding:36px clamp(16px,3vw,40px) 56px}
main:focus{outline:none}
.route{display:grid;grid-template-columns:minmax(0,1fr);gap:22px;min-width:0;max-width:1280px;margin:0 auto;animation:rise var(--d-2) var(--ease) both}
.route>*{min-width:0}
.route[hidden]{display:none}
.route>header{display:grid;gap:8px;padding-bottom:4px}
.route>header .eyebrow{margin:0;font:var(--t-eyebrow);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.route>header .eyebrow .idx{display:none}
.route>header .eyebrow .parent{color:var(--ink-3);font-weight:400}
.route>header .eyebrow .parent a{color:var(--ink-3);display:inline-block;padding:12px 0;margin:-12px 0;line-height:20px}
.route h1:focus{outline:none}
.route>header p{margin:0;color:var(--ink-2);max-width:72ch;font-size:clamp(15px,1.2vw,17px);line-height:1.5}
.route>header .lead-h,.headline{margin:0;font:var(--t-h1);letter-spacing:-.04em;color:var(--ink);max-width:22ch;text-wrap:balance}
.headline .grey,.lead-h .grey{color:var(--ink-3)}
#route-candidates>header .lead-h,#route-planets>header .lead-h,#route-runs>header .lead-h{font-size:clamp(28px,3vw,42px)}
.headrow{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:16px}
h2{font:600 19px/1.25 var(--sans);letter-spacing:-.02em;margin:0}
h3{font:600 15px/1.3 var(--sans);letter-spacing:-.01em;margin:0}
.note{margin:0;border-top:1px solid var(--line);padding:14px 0 0;font-size:14px;color:var(--ink-2);max-width:90ch}
.note b{color:var(--ink);font-weight:600}
.tag{display:inline-flex;align-items:center;gap:6px;font:500 11px/1 var(--sans);color:var(--ink-2);padding:5px 9px;border:1px solid var(--line);border-radius:999px;background:var(--panel-2);white-space:nowrap;vertical-align:1px}
.tag.unc{color:var(--yellow);border-color:color-mix(in oklab,var(--yellow) 35%,transparent);background:color-mix(in oklab,var(--yellow) 10%,transparent)}
.tag.unc::before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor}
.tag.sim{color:var(--prb-ink)}
.tag.cl{color:var(--sen);background:var(--cyan-soft);border-color:transparent}
.muted{color:var(--ink-3)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;font:500 13px/1.2 var(--sans);color:var(--ink);background:var(--panel-2);border:1px solid var(--line);border-radius:999px;padding:6px 14px;cursor:pointer;min-height:34px;text-decoration:none;transition:background-color var(--d-1) var(--ease),color var(--d-1) var(--ease),border-color var(--d-1) var(--ease),transform var(--d-2) var(--ease)}
.btn:hover{border-color:var(--line-3);color:var(--ink)}
.btn[aria-disabled="true"]{opacity:.45;cursor:default}
.btn.primary{background:var(--btn-bg);color:var(--btn-ink);border-color:transparent;min-height:48px;padding:0 24px;font-size:17px}
.btn.primary:hover{transform:translateY(-1px);color:var(--btn-ink)}
.btn.ghost{min-height:48px;padding:0 20px;font-size:17px;background:transparent;border-color:transparent;color:var(--cyan)}
.btn.ghost:hover{color:var(--ink)}
.chip{font:500 12px/1.2 var(--sans);border:1px solid var(--line);background:transparent;color:var(--ink-2);padding:6px 14px;border-radius:999px;cursor:pointer;min-height:34px}
.chip[aria-pressed="true"]{color:var(--seg-ink);background:var(--seg-bg);border-color:transparent}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.card{background:var(--glass);border:1px solid var(--line);border-radius:var(--r);padding:18px 20px;min-width:0;position:relative;-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px)}
.cards{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}
/* segmented controls (the prototype's grey track with a white pill) */
.segctl{display:inline-flex;flex-wrap:wrap;gap:2px;padding:3px;border-radius:12px;background:var(--panel-2)}
.segctl button{min-height:32px;padding:0 12px;border-radius:9px;border:0;background:transparent;color:var(--ink-2);font:500 12px var(--sans);cursor:pointer}
.segctl button[aria-pressed="true"]{background:var(--seg-bg);color:var(--seg-ink)}
/* status pills with a coloured dot */
.pill{display:inline-flex;align-items:center;gap:8px;min-height:36px;padding:0 14px;border-radius:999px;font:500 13px var(--sans);border:1px solid var(--line);background:transparent;color:var(--ink-3);cursor:pointer}
.pill i{width:7px;height:7px;border-radius:50%;background:var(--line-3)}
.pill[aria-pressed="true"]{border-color:var(--line-3);background:var(--panel-2);color:var(--ink)}
.pill[aria-pressed="true"] i{background:var(--c)}
.pill .n{color:var(--ink-3)}
/* space panels: dark in both themes */
.space{border-radius:28px;border:1px solid var(--stage-line);background-color:var(--stage);color:var(--stage-ink);overflow:hidden;position:relative;min-width:0;--ink:var(--stage-ink);--ink-2:#AEB6C6;--ink-3:var(--stage-dim);--line:var(--stage-line);--line-2:rgba(255,255,255,.14);--panel:#11151F;--panel-2:rgba(255,255,255,.06);--cyan:#64D2FF}
.space svg text{fill:#A1A1A6}
.glass{background:var(--glass);border:1px solid var(--line);border-radius:24px;-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px);min-width:0}
.row2{display:flex;flex-wrap:wrap;gap:18px;align-items:stretch}
.grow{flex:999 1 620px;min-width:0}
.side{flex:1 1 320px;min-width:0}
.small{margin:0;font-size:12px;color:var(--ink-3)}
/* motion: all of it decorative, all of it off under prefers-reduced-motion */
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes twinkle{0%,100%{opacity:.25}50%{opacity:.75}}
@keyframes orbit{to{transform:rotate(360deg)}}
@keyframes drift{from{transform:translateX(0)}to{transform:translateX(-400px)}}
@keyframes pulse{0%,100%{opacity:.35;transform:scale(1)}50%{opacity:.8;transform:scale(1.35)}}
@keyframes breathe{0%,100%{opacity:.55}50%{opacity:.9}}
@keyframes sweep{from{transform:translateX(var(--from))}to{transform:translateX(var(--to))}}
@keyframes reveal{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes head{from{transform:translateX(0)}to{transform:translateX(var(--w))}}
.twinkle{animation:twinkle 6s var(--ease) infinite}
.twinkle2{animation:twinkle 9s var(--ease) infinite 2s}
.orbit{animation:orbit 60s linear infinite}
.orbitfast{animation:orbit 14s linear infinite}
.orbitslow{animation:orbit 90s linear infinite reverse}
.clouds{animation:drift 90s linear infinite}
.pulse{animation:pulse 3.2s var(--ease) infinite;transform-box:fill-box;transform-origin:center}
.breathe{animation:breathe 7s var(--ease) infinite}
/* the transit theatre: one 10 s clock for the shadow, the curve drawing in and the playhead */
.sweep{animation:sweep 10s linear infinite}
.reveal{transform-box:fill-box;transform-origin:0 0;animation:reveal 10s linear infinite}
.playhead{animation:head 10s linear infinite}

/* Overview: the launch hero */
.route>header.launch{display:flex;flex-direction:column;align-items:center;text-align:center;padding:56px 0 0;gap:0}
.launch .kick{margin:0;font-size:17px;font-weight:500;color:var(--star)}
.launch h1{margin:10px 0 0;font-weight:700;font-size:clamp(52px,8.4vw,120px);line-height:1;letter-spacing:-.045em}
.route>header.launch .sub{margin:20px auto 0;max-width:620px;font-size:clamp(17px,1.6vw,21px);line-height:1.45;color:var(--ink-2)}
.launch .ctas{display:flex;gap:14px;flex-wrap:wrap;justify-content:center;margin-top:30px}
.planetfig{margin:44px 0 0;width:100%;position:relative;border-radius:28px;overflow:hidden;background:#000}
.planetfig figcaption{position:absolute;left:20px;top:16px;font-size:12px;color:#8E8E93}
.proof{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:1px;width:min(100%,1100px);margin:-70px auto 0;background:var(--line);border-radius:22px;overflow:hidden;position:relative;text-align:left}
.proof>div{background:color-mix(in oklab,var(--panel) 88%,transparent);-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px);padding:22px 24px}
.proof b{display:block;font-size:40px;font-weight:600;letter-spacing:-.03em;line-height:1.05}
.proof span{display:block;margin-top:8px;font-size:14px;line-height:1.45;color:var(--ink-2)}
.honest{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2.2fr);gap:12px 32px;border-top:1px solid var(--line);padding-top:22px}
.honest h2{font-size:15px;color:var(--ink-3);font-weight:500}
.honest ul{list-style:none;margin:0;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))}
.honest li{font-size:14px;color:var(--ink-2);line-height:1.5;padding-left:16px;position:relative}
.honest li::before{content:"";position:absolute;left:0;top:.55em;width:6px;height:6px;border-radius:50%;background:var(--yellow)}
.honest li b{color:var(--ink);font-weight:600}
.secthead{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px 16px;border-top:1px solid var(--line);padding-top:22px}
.secthead h2{font-size:15px;color:var(--ink-3);font-weight:500}
.secthead p{margin:0;font-size:13px;color:var(--ink-3);max-width:72ch}
/* Sky */
.skymap{flex:999 1 640px;display:grid;gap:10px;min-width:0;align-content:start}
.skyover{pointer-events:none}
.skyover .skymark{pointer-events:auto}
.skycov{display:grid;gap:8px;padding:14px 16px;border-radius:var(--r)}
.skycov p{margin:0;font-size:13px;color:var(--ink-2)}
.skycov a{display:inline-flex;align-items:center;min-height:44px}
.theatre .mxstage{padding:0 12px 4px}
.theatre .mxctl,.theatre .mxbadges{padding:0 2px}
.skypin{position:absolute;z-index:3;transform:translate(16px,-50%);min-height:44px;padding:8px 12px;border-radius:var(--r-s);border:1px solid rgba(255,255,255,.16);background:rgba(4,6,11,.82);color:var(--stage-ink);text-decoration:none;line-height:1.3;font-size:12px;white-space:nowrap}
.skypin b{font-size:14px;font-weight:600;display:block}
.skypin span{display:block;color:var(--stage-dim)}
.skypin em{font-style:normal;color:#64D2FF}
.skynote{margin:0;font-size:12px;color:var(--ink-3)}
.skymark.on{cursor:zoom-in}
.sktl{display:grid;gap:10px}
.secth{margin:0;font:var(--t-h3);letter-spacing:-.01em}
@media screen and (max-width:699.98px){main .skybox a.skypin{position:absolute;display:flex;align-items:center;margin:0;padding:4px 10px}.skybox .skypin span,.skybox .skypin em{display:none}.skybox .skypin b{font-size:12px}}
.skylinks .skyzoom{min-height:44px}
.dipsbox{flex:1 1 300px;max-width:380px;padding:10px;display:flex;flex-direction:column;gap:2px;border-radius:28px}
.dipsbox .dhead{display:flex;justify-content:space-between;align-items:center;padding:10px 12px 6px}
.dipsbox .dhead b{font-size:15px;font-weight:600}
.dipsbox .segctl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:4px 8px 8px}
.dipitem{display:grid;grid-template-columns:10px auto minmax(0,1fr);gap:2px 12px;align-items:center;min-height:56px;padding:8px 12px;border-radius:14px;color:var(--ink);text-decoration:none;border-top:1px solid var(--line)}
.dipitem:hover{background:var(--panel-2);color:var(--ink)}
.dipitem i{grid-row:span 2;width:8px;height:8px;border-radius:50%;background:var(--c)}
.dipitem b{font-size:15px;font-weight:500;white-space:nowrap}
.dipitem .st{font-size:12px;color:var(--c);text-align:right}
.dipitem .sub{grid-column:2/-1;font-size:13px;color:var(--ink-3)}
.runline{padding:14px 18px;background:var(--glass-2)}
.runline .cap{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:var(--ink-3);margin-bottom:6px}
.runline svg{display:block;width:100%;height:auto}
/* Transit cockpit */
.roundbtn{width:44px;height:44px;border-radius:50%;border:0;background:var(--panel-2);color:var(--ink);font:inherit;font-size:20px;cursor:pointer;display:inline-grid;place-items:center;text-decoration:none}
.cmpbtn{min-height:44px;padding:0 18px;border-radius:999px;border:0;background:var(--panel-2);color:var(--ink);font:500 15px var(--sans);cursor:pointer}
.cmpbtn[aria-pressed="true"]{background:var(--btn-bg);color:var(--btn-ink)}
.dipchips{display:flex;gap:2px;padding:3px;border-radius:14px;background:var(--panel-2);overflow-x:auto}
.dipchips a{flex:1 0 auto;display:flex;align-items:center;justify-content:center;gap:8px;min-height:40px;padding:0 14px;border-radius:11px;color:var(--ink-2);font-size:13px;text-decoration:none;white-space:nowrap}
.dipchips a i{width:6px;height:6px;border-radius:50%;background:var(--c)}
.dipchips a[aria-current="true"]{background:var(--seg-bg);color:var(--seg-ink)}
.theatre{flex:999 1 620px;padding:22px;display:flex;flex-direction:column;gap:12px;background:radial-gradient(90% 90% at 30% 20%,#1A1206 0%,#000 65%)}
.theatre .cap{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:13px;color:#8E8E93}
.theatre svg{display:block;width:100%;height:auto}
.theatre .foot{font-size:12px;color:#8E8E93;line-height:1.5;margin:0}
.axisrow{display:flex;justify-content:space-between;gap:8px;font:11px var(--mono);color:#8E8E93;margin-top:-6px}
.axisrow span:nth-child(2){text-align:center}
.tx-side{flex:1 1 340px;min-width:0;display:flex;flex-direction:column;gap:14px}
.scorecard{padding:18px 20px}
.scorecard .top{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.scorecard .top span{font-size:13px;color:var(--ink-3)}
.scorecard .top b{font-size:34px;font-weight:600;letter-spacing:-.03em}
.bar{height:4px;border-radius:2px;background:var(--panel-2);margin:10px 0 12px;overflow:hidden}
.bar i{display:block;height:4px;border-radius:2px;background:var(--c)}
.scorecard p{margin:0;font-size:15px;line-height:1.5;color:var(--ink-2)}
.lanes{padding:16px 20px;display:flex;flex-direction:column;gap:10px}
.lanes .lane{display:grid;grid-template-columns:150px minmax(0,1fr);gap:10px;align-items:center}
.lanes .lane span{font-size:13px}
.lanes .track{position:relative;height:8px;border-radius:4px;background:var(--panel-2)}
.lanes .track i{position:absolute;top:0;bottom:0;border-radius:4px;background:var(--c)}
.lanes .track i.uncounted{background:transparent;border:1px dashed var(--c)}
.lanes .track em{position:absolute;left:0;top:-5px;font-style:normal;font-size:11px;color:var(--ink-3)}
.lanes .win{position:absolute;top:-4px;bottom:-4px;border-left:1px dashed var(--line-3);border-right:1px dashed var(--line-3)}
.quote{padding:16px 20px;display:flex;flex-direction:column;gap:8px;border-radius:24px;background:linear-gradient(180deg,color-mix(in oklab,var(--sen) 14%,transparent),color-mix(in oklab,var(--sen) 4%,transparent));border:1px solid color-mix(in oklab,var(--sen) 26%,transparent)}
.quote .who{display:flex;justify-content:space-between;gap:10px;font-size:13px}
.quote .who b{color:var(--sen);font-weight:500}
.quote .who span{color:var(--ink-3)}
.quote p{margin:0;font-size:16px;line-height:1.45}
.quote small{font-size:12px;color:var(--ink-3)}
.orbitfig{flex:1 1 320px;margin:0;padding:16px;display:flex;gap:16px;align-items:center;background:var(--glass-2)}
.orbitfig svg{width:160px;height:160px;flex:0 0 auto}
.orbitfig figcaption{font-size:14px;line-height:1.5;color:var(--ink-2)}
.orbitfig figcaption b{color:var(--ink);font-weight:600}
.tray{flex:999 1 520px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;background:var(--glass-2)}
.tray .cap{display:flex;justify-content:space-between;align-items:center;font-size:13px;color:var(--ink-3)}
.tray .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.tray a{border-radius:16px;border:1px solid var(--line);background:rgba(0,0,0,.5);padding:10px;color:#F5F5F7;text-decoration:none;display:block}
.tray a[aria-current="true"]{border-color:var(--c)}
.tray a .h{display:flex;justify-content:space-between;font-size:12px}
.tray a .h span{color:var(--c)}
.tray svg{display:block;width:100%;height:auto}
.txnotice{margin:0;font-size:14px;color:var(--yellow)}
.txnotice[hidden]{display:none}
.casefile{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:13px;color:var(--ink-3)}
/* Explorer */
.scatterbox{flex:999 1 620px;padding:22px;background:radial-gradient(110% 110% at 50% 100%,#120A1E 0%,#000 60%)}
.scatterbox .cap{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:#8E8E93;margin-bottom:10px}
.scatter{position:relative;width:100%;padding-bottom:52%}
.scatter svg{position:absolute;inset:0;width:100%;height:100%}
.scatter .ax{position:absolute;font-size:11px;color:#8E8E93}
.scatter>button{position:absolute;width:44px;height:44px;margin:-22px 0 0 -22px;border:0;padding:0;background:transparent;border-radius:50%;cursor:pointer}
.scatter>button i{position:absolute;left:50%;top:50%;width:var(--s);height:var(--s);margin:calc(var(--s) / -2) 0 0 calc(var(--s) / -2);border-radius:50%;background:var(--c);box-shadow:0 0 var(--g) var(--c)}
.scatter>button[aria-pressed="true"] i{outline:2px solid #fff;outline-offset:2px}
.scatterbox .foot{margin-top:28px;font-size:12px;color:#8E8E93}
.selpanel{flex:1 1 320px;max-width:400px;padding:22px;display:flex;flex-direction:column;gap:14px;border-radius:28px}
.selpanel .st{margin:0;font-size:13px;font-weight:500;color:var(--c)}
.selpanel h2{font-size:28px;font-weight:600;letter-spacing:-.03em}
.selpanel svg{width:100%;max-width:260px;height:auto;align-self:center}
.statgrid{margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line);border-radius:16px;overflow:hidden}
.statgrid div{background:var(--panel);padding:12px}
.statgrid dt{font-size:12px;color:var(--ink-3)}
.statgrid dd{margin:4px 0 0;font-size:20px;font-weight:600}
.filters{display:flex;flex-direction:column;gap:8px;align-items:flex-end}
.filters>div{display:flex;gap:6px 10px;flex-wrap:wrap;justify-content:flex-end}
/* Sentinels */
.ringfig{flex:1 1 360px;margin:0;padding:18px;display:flex;flex-direction:column;align-items:center;gap:8px;background:radial-gradient(80% 80% at 50% 50%,#0B1220 0%,#000 70%)}
.ringfig svg{width:100%;max-width:380px;height:auto}
.ringfig figcaption{font-size:12px;color:#8E8E93;text-align:center}
.revcards{flex:999 1 520px;min-width:0;display:flex;flex-direction:column;gap:10px}
.revcard{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:6px 14px;align-items:center;border-radius:20px;border:1px solid var(--line);background:var(--glass-2);padding:14px 18px;color:var(--ink);font:inherit;text-align:left;cursor:pointer;width:100%}
.revcard[aria-pressed="true"]{border-color:var(--line-3);background:var(--panel-2)}
.revcard .nm{font-size:17px;font-weight:600;color:var(--c)}
.revcard .kd{display:block;font-size:12px;color:var(--ink-3)}
.revcard .w{font-size:28px;font-weight:600;letter-spacing:-.03em}
.revcard .hits{grid-column:1/-1;display:flex;gap:4px}
.revcard .hits i{flex:1;height:4px;border-radius:2px;background:var(--panel-2)}
.revcard .hits i.on{background:var(--c)}
.revcard .hitcap{grid-column:1/-1;font-size:12px;color:var(--ink-3)}
.marked{padding:16px 18px;display:flex;flex-direction:column;gap:10px;background:var(--glass-2)}
.marked .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}
.marked a{min-height:60px;border-radius:14px;border:1px solid var(--line);color:var(--ink);text-decoration:none;padding:8px 12px;display:block}
.marked a.on{border-color:var(--line-3);background:var(--panel-2)}
.marked a b{font-size:14px;font-weight:500;display:block}
.marked a span{font-size:12px;color:var(--c)}
.attribution{color:var(--ink-2)}
.layoutbar{display:flex;flex-wrap:wrap;gap:8px 11px;align-items:center;font-size:13px}
.layoutbar .muted{font-size:12px}
.widgets{display:grid;gap:16px;grid-template-columns:repeat(6,minmax(0,1fr));min-width:0}
.widget{display:grid;gap:12px;align-content:start}
.widget.size-S{grid-column:span 2}
.widget.size-M{grid-column:span 3}
.widget.size-L{grid-column:1/-1}
.widget>header{display:flex;justify-content:space-between;align-items:center;gap:6px 8px;flex-wrap:wrap}
.widget>header h2{display:flex;align-items:center;gap:11px}
.widget>header h2 .idx{font:500 11px/1 var(--display);color:var(--cyan)}
.wctl{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.wctl .btn{padding:2px 8px;min-height:30px;min-width:30px;font-size:12px;border-radius:8px}
.seg{display:inline-flex}
.seg .btn{border-radius:0;margin-left:-1px}
.seg .btn:first-child{border-radius:8px 0 0 8px;margin-left:0}
.seg .btn:last-child{border-radius:0 8px 8px 0}
.seg .btn[aria-pressed="true"]{background:var(--btn-bg);color:var(--btn-ink);border-color:var(--btn-bg)}
.wopen{font-size:13px;font-weight:500;justify-self:start}
.dip{font:500 12px var(--mono);white-space:nowrap}
.toplist,.toplist ul{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.toplist>li{border-top:1px solid var(--line);padding-top:11px;display:grid;gap:6px}
.toplist>li:first-child{border-top:0;padding-top:0}
.toplist ul li{display:flex;flex-wrap:wrap;gap:2px 12px;align-items:baseline;font-size:13px}
.toplist .st .short{display:none}
.toplist .note{font-size:12.5px}
.kpis{display:grid;gap:11px;grid-template-columns:repeat(auto-fit,minmax(110px,1fr))}
.kpi{border-top:1px solid var(--line-2);padding-top:8px}
.kpi b{display:block;font:500 26px/1.1 var(--mono);letter-spacing:-.03em}
.kpi span{font-size:12px;color:var(--ink-3)}
.big{font:500 44px/1 var(--mono);letter-spacing:-.04em}
.empty{color:var(--ink-3);font-style:italic}
.small{margin:0;font-size:12.5px;color:var(--ink-3)}
.runlist{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.runlist li{display:grid;gap:2px;border-top:1px solid var(--line);padding-top:8px;font-size:13px}
.runlines{list-style:none;margin:0;padding:0;display:grid;gap:0}
.runlines>li{border-top:1px solid var(--line);padding:11px 0;font-size:13px;display:grid;gap:4px}
.runlines>li:first-child{border-top:0}
.runlines .line{display:flex;flex-wrap:wrap;gap:2px 14px;align-items:baseline}
.runlines .err{color:var(--reject)}
.ratio summary{font-size:13px}
/* tables: Kshana's table treatment, mono uppercase heads over hairlines */
.tablewrap{overflow-x:auto;min-width:0;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.tablewrap.scrollbox{overflow-x:auto}  /* every row shows; only a table wider than its box scrolls, sideways */
/* The benchmark card: label and value side by side, both wrapping; stacked on a phone. */
table.bench{width:100%;border-collapse:collapse}
table.bench th,table.bench td{white-space:normal;text-align:left;vertical-align:top;padding:8px 12px;border-top:1px solid var(--line);font-size:14px;line-height:1.4;font-family:inherit;text-transform:none;letter-spacing:0;color:var(--ink)}
table.bench tr:first-child th,table.bench tr:first-child td{border-top:0}
table.bench th{width:48%;font-weight:600}
.scrollbox thead th{position:sticky;top:0;background:var(--panel);z-index:2}
.scrollbox th:first-child,.scrollbox td:first-child{position:sticky;left:0;background:var(--panel);z-index:1;box-shadow:1px 0 0 var(--line)}
.scrollbox thead th:first-child{z-index:3}
.scrollbox td,.scrollbox tbody th{white-space:nowrap}
.scrollbox tbody th{font:400 13px var(--mono);color:var(--ink);text-transform:none;letter-spacing:0}
td .dip{font-size:11.5px;display:inline-block;max-width:24ch;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
table{width:100%;border-collapse:collapse;font:13px var(--mono);font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font:600 11px/1.3 var(--mono);color:var(--ink-3);text-transform:uppercase;letter-spacing:.07em;white-space:nowrap}
tbody tr:hover td,tbody tr:hover th{background:color-mix(in oklab,var(--panel) 92%,var(--cyan))}
td.num,th.num{text-align:right}
th button{font:inherit;color:inherit;text-transform:inherit;letter-spacing:inherit;background:none;border:0;padding:2px 0;cursor:pointer;display:inline-flex;gap:4px;align-items:center}
th[aria-sort="ascending"] button,th[aria-sort="descending"] button{color:var(--ink)}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
td small{display:block;color:var(--ink-3);font-size:11px}
/* charts */
.charts{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))}
svg{display:block;width:100%;height:auto}
svg text{font:11px var(--mono);fill:var(--ink-3)}
svg .grid{stroke:var(--line)}
svg .bar{fill:var(--fit)}
svg .lbl{fill:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font:500 11.5px/1.5 var(--mono);color:var(--ink-3)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.legend .k-new{background:var(--fit)}
.legend .k-known{border:2px solid var(--muted)}
.legend .k-sim{border:2px solid var(--muted)}
.legend .k-cl{background:var(--fit)}
svg.calplane{margin:0 auto}
svg.calplane .floor{fill:var(--sel)}
svg.calplane .iso{stroke:var(--muted);stroke-dasharray:4 3}
svg.calplane .floorline{stroke:var(--flag)}
svg.calplane .isolbl{fill:var(--muted);font-size:11px}
svg.calplane .floorlbl{fill:var(--flag)}
svg.calplane .samplelbl{fill:var(--flag);font-weight:600}
svg.calplane .pt.sim{fill:var(--panel);fill-opacity:.85;stroke:var(--muted);stroke-width:2}
svg.calplane .lbl,svg.calplane .samplelbl,svg.calplane .isolbl{paint-order:stroke;stroke:var(--panel);stroke-width:7px;stroke-linejoin:round}
#caltable th,#caltable td{white-space:nowrap}
#caltable tbody th{font:400 13px var(--mono);text-transform:none;letter-spacing:0;color:var(--ink)}
svg.calplane .pt.cl{fill:var(--fit);fill-opacity:.85;stroke:var(--fit);stroke-width:1.5}
/* planets */
.ratio{display:grid;gap:5px;border-top:1px solid var(--line);padding-top:11px;margin-top:11px}
.ratio .formula{font:12px var(--mono);overflow-wrap:anywhere}
.scale{position:relative;height:8px;background:var(--bg-2);border-radius:999px;overflow:hidden}
.scale i{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,var(--cyan),color-mix(in oklab,var(--cyan) 60%,var(--lime)));border-radius:999px;min-width:3px}
.scalecap{display:flex;justify-content:space-between;font:11px var(--mono);color:var(--ink-3)}
.archive{margin-top:14px;border:1px dashed var(--line-2);border-radius:11px;padding:11px 12px;font-size:13px}
.archive ul{margin:6px 0 0;padding-left:18px}
.card h2{display:flex;flex-wrap:wrap;gap:6px 11px;align-items:baseline}
.card h2 .sub{font:500 11px/1.4 var(--mono);color:var(--ink-3);letter-spacing:.04em}
.idtag{font:400 11px var(--mono);color:var(--ink-3);margin-left:4px;text-transform:none;letter-spacing:0}
details summary{cursor:pointer}
/* panel, runs */
.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 16px;font-size:13px;margin:11px 0 0}
.kv dt{color:var(--ink-3)}
.kv dd{margin:0;font-family:var(--mono);overflow-wrap:anywhere;min-width:0}
.agree{list-style:none;margin:0;padding:0;display:grid}
.agree li{display:grid;grid-template-columns:minmax(0,15em) minmax(0,1fr) auto;gap:4px 14px;align-items:baseline;border-top:1px solid var(--line);padding:11px 0;font-size:13px}
.agree li:first-child{border-top:0}
.marks{display:flex;flex-wrap:wrap;gap:4px 11px;margin:4px 0 0}
details.cfg{padding:0}
details.cfg>summary{padding:14px 20px;font-weight:600}
details.cfg>div{padding:0 20px 16px;display:grid;gap:14px}
details.cfg .mono{overflow-wrap:anywhere}
.frametools{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13px}
pre.err{white-space:pre-wrap;overflow-wrap:anywhere;margin:4px 0;font-size:12px;background:var(--coral-soft);color:var(--ink);padding:8px 11px;border-radius:8px}
.frame{width:100%;height:calc(100vh - 190px);height:calc(100vh - var(--frame-offset, 190px));min-height:520px;border:1px solid var(--line-2);border-radius:var(--r);background:var(--bg);display:block;box-shadow:var(--shadow)}
.frame[hidden]{display:none}
/* Until the Docket reports ready the frame takes no space and the status line holds the slot. */
.frame.waiting,body[data-route="candidates"] .frame.waiting{height:0;min-height:0;flex:0 0 0;border:0;visibility:hidden}
.topfull{display:none}
.note.blocked{border-top-color:var(--reject);font-size:14px}
.copyfallback{font:12px var(--mono);width:min(100%,46ch);min-height:34px;padding:4px 8px;border:1px solid var(--line-2);border-radius:8px;background:var(--panel);color:var(--ink)}
#sharednote{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
#sharednote[hidden]{display:none}
#disctable{container-type:inline-size}
.dippicker{display:none}
.calcards{display:none}
.calcard{border-top:1px solid var(--line);padding-top:10px;margin:0}
.sortbar,.feedcards{display:none}
.feedcards{list-style:none;margin:0;padding:0}
#disctable caption{caption-side:top;text-align:left}
.capnote{position:sticky;left:0;display:block;max-width:min(100cqw,90ch);padding:11px 12px 0;font:12.5px/1.5 var(--sans);color:var(--ink-2)}
#archivenote{color:var(--amber);font-weight:500}
#archivenote+*,.capnote:last-child{padding-bottom:11px}
@media (max-width:1000px){
  .widget.size-S{grid-column:span 3}
  .agree li{grid-template-columns:minmax(0,1fr) auto}
  .agree li>:nth-child(2){grid-column:1/-1;grid-row:2}
  .honest{grid-template-columns:minmax(0,1fr)}
  .dipsbox,.selpanel{max-width:none}
}
@media (max-width:699.98px){
  .dipchips{flex-wrap:wrap;overflow-x:visible}
  .dipchips a{flex:1 0 30%}
  table.bench tr{display:block;border-top:1px solid var(--line);padding:6px 0}table.bench tr:first-child{border-top:0}table.bench th,table.bench td{display:block;width:auto;border:0;padding:2px 12px}
  main{padding:20px 16px 40px}
  .route{gap:18px}
  .launch{padding-top:28px}
  .launch .ctas{flex-direction:column;align-items:stretch;width:100%}
  .proof{margin-top:-30px}
  .proof b{font-size:34px}
  .skynote{position:static;max-width:none;text-align:left;margin-top:6px}
  .skypin{padding:8px 12px}
  .lanes .lane{grid-template-columns:118px minmax(0,1fr)}
  .orbitfig{flex-direction:column;align-items:flex-start}
  .filters{align-items:flex-start}
  .filters>div{justify-content:flex-start}
  .segctl button,.pill,.dipchips a,.cmpbtn{min-height:44px}
  .segctl button{min-width:44px}
  .widgets{grid-template-columns:minmax(0,1fr)}
  .widget.size-S,.widget.size-M,.widget.size-L{grid-column:1/-1}
  /* Candidates (the case file): a dip picker above the frame, so no dip is a long scroll away inside it. */
  body[data-route="candidates"] .dippicker{display:flex;align-items:center;gap:10px;margin:8px 16px 4px;flex:none}
  .dippicker label{font:500 12px/1 var(--sans);color:var(--ink-3)}
  .dippicker select{flex:1;min-width:0;min-height:44px;font:500 16px var(--mono);color:var(--ink);background:var(--panel);border:1px solid var(--line-2);border-radius:12px;padding:0 10px}
  /* Sentinels: the calibration rows as one card per reviewer. */
  #caltable{display:none}
  .calcards{display:grid;gap:4px}
  /* Feed: the table's caption stays; its rows become three-line cards, sorted from a labelled group. */
  #disctable{border:0;background:none;overflow:visible}
  #disctable table,#disctable caption{display:block}
  #disctable thead,#disctable tbody{display:none}
  #disctable caption .capnote{padding:0 0 8px;position:static}
  .sortbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:4px 0 10px}
  .sortlbl{font:500 12px/1 var(--sans);color:var(--ink-3);margin-right:4px}
  .sortbtn{min-height:44px;padding:0 10px;border:1px dashed var(--line-3);border-radius:8px;background:transparent;color:var(--ink-2);font:500 12px/1 var(--mono);text-transform:uppercase;letter-spacing:.05em;cursor:pointer}
  .sortbtn[aria-pressed="true"]{border-style:solid;border-color:var(--cyan);color:var(--cyan)}
  .feedcards{display:grid;gap:8px}
  .feedcards li{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:2px 12px 8px;display:grid;gap:2px}
  .fc1{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px}
  .fc1 .dip{font-size:12px;overflow:hidden;text-overflow:ellipsis;min-width:0}
  .fcst{font-size:12.5px;color:var(--ink-2);white-space:nowrap}
  .fc2{font-size:11px;letter-spacing:-.035em;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .fc3{font-size:11.5px;color:var(--yellow)}
  .frame{height:calc(100vh - var(--top));height:calc(100dvh - var(--top));min-height:0;border-radius:0;border-left:0;border-right:0;margin:0 -16px;width:calc(100% + 32px)}
  .btn,.chip,.wctl .btn{min-height:44px}
  .wctl .btn{min-width:44px}
  .seg{display:none}
  .frametools a{display:inline-flex;align-items:center;min-height:44px}
  th button{min-height:44px;min-width:44px}
  /* Every link and disclosure in the page is a 44 px target: min-height and padding, same font size. */
  main a{display:inline-block;min-height:44px;min-width:44px;padding:12px 0;line-height:20px;box-sizing:border-box}
  td a.dip{padding:12px 0;line-height:20px}
  summary{min-height:44px;padding:12px 0;line-height:20px;box-sizing:border-box}
  .copyfallback{min-height:44px}
  .toplist ul{gap:0}
  .toplist ul li.toprow{display:grid;grid-template-columns:auto auto auto minmax(0,1fr);gap:0 11px;align-items:center;height:44px;white-space:nowrap;border-top:1px solid var(--rule);font-size:12px}
  .toplist ul li.toprow:first-child{border-top:0}
  .toplist ul li.toprow a.dip{display:flex;align-items:center;height:44px;padding:0;font-size:11px}
  .toplist .st .long{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
  .toplist .st .short{display:inline;overflow:hidden;text-overflow:ellipsis}
  .toplist .st{min-width:0;overflow:hidden;text-overflow:ellipsis}
  /* The feed table scrolls sideways in its own region; the page alone scrolls vertically. */
  .tablewrap.scrollbox{max-height:none}
  /* Candidates: the header collapses and the Docket fills the screen under the top bar, so only the frame scrolls. */
  body[data-route="candidates"] main{padding:0}
  body[data-route="candidates"] #route-candidates{display:flex;flex-direction:column;gap:0;height:calc(100vh - var(--top));height:calc(100dvh - var(--top));max-width:none;animation:none}
  body[data-route="candidates"] #route-candidates>header{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
  body[data-route="candidates"] #route-candidates .frametools{display:none}
  body[data-route="candidates"] #route-candidates>.note{margin:8px 16px;flex:none}
  body[data-route="candidates"] .frame{flex:1 1 auto;height:auto;min-height:0;margin:0;width:100%;border:0;border-radius:0}
  /* Links styled as tiles or rows keep their own layout. */
  main a.dipitem{display:grid;padding:8px 12px}
  main a.btn{display:inline-flex;padding-top:0;padding-bottom:0}
  main a.roundbtn{display:inline-grid;place-items:center;padding:0;line-height:1}
  main .dipchips a,main .marked a,main .tray a{display:flex;padding:0 14px}
  main .marked a,main .tray a{display:block;padding:8px 12px}
  main a.skypin{display:block;position:static;margin-top:8px;padding:8px 12px;line-height:1.35}
}
/* Every animation is decorative; with reduced motion the page is still, and the theatre shows mid-transit. */
@media (prefers-reduced-motion: reduce){
  .route,.twinkle,.twinkle2,.orbit,.orbitfast,.orbitslow,.clouds,.pulse,.breathe,.sweep,.reveal,.playhead{animation:none!important}
  .sweep{transform:none!important}
  .reveal{transform:none!important}
  .playhead{opacity:0}
  .btn,.nav a,.pill{transition:none}
}
"""
APP_CSS += GALAXY_CSS + METHODS_CSS + CATALOGUE_CSS + LEARN_CSS + MISSION_CSS + VARIABLES_CSS

# The Leaderboard: one table per scope. On a phone each row becomes a card, every cell labelled, so nothing
# scrolls sideways at 390 px.
LEADERBOARD_CSS = """
#route-leaderboard>header .lead-h{font-size:clamp(28px,3vw,42px)}
.lb{display:grid;gap:10px}
.lb h2 .sub{font:500 12px/1.4 var(--mono);color:var(--ink-3)}
table.lbtable{font:14px var(--sans)}
table.lbtable th,table.lbtable td{white-space:normal;vertical-align:top;padding:10px 12px}
table.lbtable thead th{font:600 11px/1.35 var(--mono);color:var(--ink-3);text-transform:none;letter-spacing:.02em;white-space:normal}
table.lbtable tbody th{font:600 14px/1.35 var(--sans);color:var(--ink);text-transform:none;letter-spacing:0;white-space:normal;min-width:12ch}
table.lbtable .rk{font:600 15px var(--mono);color:var(--ink-2);width:11ch}
table.lbtable .v{display:block;font:600 15px/1.3 var(--mono);color:var(--ink)}
table.lbtable .ci,table.lbtable .kd{display:block;font:12px/1.35 var(--mono);color:var(--ink-3)}
table.lbtable .na{color:var(--ink-3);font-style:italic}
table.lbtable .ci{white-space:nowrap}
.lbrules{margin:0;padding-left:22px;display:grid;gap:8px;color:var(--ink-2);font-size:14px;line-height:1.5;max-width:96ch}
.lbhash dd{font-size:12px}
@media (max-width:699.98px){
  table.lbtable thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
  table.lbtable,table.lbtable tbody{display:block}
  table.lbtable tr{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px 12px;padding:12px;border-top:1px solid var(--line)}
  table.lbtable tbody tr:first-child{border-top:0}
  table.lbtable th,table.lbtable td{display:block;padding:0;border:0;min-width:0}
  table.lbtable tbody th{grid-column:1/-1;order:-1}
  table.lbtable .rk{grid-column:1/-1;order:-2;width:auto}
  table.lbtable td::before{content:attr(data-l);display:block;font:500 11px/1.35 var(--mono);color:var(--ink-3);margin-bottom:2px}
  table.lbtable .rk::before{display:inline;margin:0 6px 0 0}
  .kv.lbhash{grid-template-columns:minmax(0,1fr);gap:2px 0}
  .kv.lbhash dd{margin-bottom:8px}
}
"""
APP_CSS += LEADERBOARD_CSS

ICONS = {
    "overview": '<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/>',
    "candidates": '<path d="M3 2h7l3 3v9H3z"/><path d="M5 8h6M5 11h6"/>',
    "discoveries": '<path d="M2 12l4-5 3 3 5-7"/>',
    "planets": '<circle cx="8" cy="8" r="4"/><path d="M1.5 10.5c2 1.5 11 -2.5 13 -5"/>',
    "panel": '<circle cx="5" cy="6" r="2"/><circle cx="11" cy="6" r="2"/><path d="M1.5 13c.5-2.5 6.5-2.5 7 0M7.5 13c.5-2.5 6.5-2.5 7 0"/>',
    "runs": '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
}

APP_JS = r"""
const $ = (s, e=document) => e.querySelector(s);
const $$ = (s, e=document) => Array.from(e.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// ---------- one object model: every planet and star has one canonical page ----------
// The slug rule is catalogue.slugify's (the tests check every catalogue name gives its stored slug).
const objSlug = n => String(n).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'x';
const planetHref = n => '/planets/' + objSlug(n) + '/';
const starHref = n => '/stars/' + objSlug(n) + '/';
// The one renderer for a link to a planet or star; data-star / data-planet let any view select it.
// A generic label ("Star page ›") gets the object's name in its accessible name.
const objLink = (kind, n, label) => { label = label ?? n; return `<a class="objlink" data-${kind}="${esc(n)}" href="${kind === 'star' ? starHref(n) : planetHref(n)}"${String(label).includes(n) ? '' : ` aria-label="${esc(n)}, ${kind} page"`}>${esc(label)}</a>`; };
// A TIC with a catalogue name (the run's target, or a TIC in a star's stored alternate names) links to its star page.
const ticLink = tic => (D.tic_names || {})[tic] ? `TIC ${esc(tic)} · ${objLink('star', D.tic_names[tic])}` : `TIC ${esc(tic)}`;
const fmt = (x, d=2) => (x === null || x === undefined || Number.isNaN(Number(x))) ? '–' : Number(x).toFixed(d);
const NS = 'http://www.w3.org/2000/svg';
function el(tag, a={}, p){ const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
function tx(svg, x, y, s, anchor='start', cls=''){ const t = el('text', {x, y, 'text-anchor': anchor, class: cls}, svg); t.textContent = s; return t; }
const UNC = `<span class="tag unc">${esc(D.unconfirmed)}</span>`;
// A run dip's status from its vetting outcome (app.py DIP_STATE): a tag, and the phrase. Only a passed dip is a candidate.
const DIPSTATE = o => (D.dip_state || {})[o] || (D.dip_state || {}).flagged || ['cand', 'candidate', D.unconfirmed];
const DIPTAG = o => { const [c, w, p] = DIPSTATE(o); return `<span class="tag ${c}" title="${esc(p)}">${esc(w)}</span>`; };
const DIPPHRASE = o => DIPSTATE(o)[2];
// A feed entry passed vetting (discover.py admits only those), so it is a candidate; a stored outcome would say otherwise.
const FEEDTAG = x => DIPTAG(x.outcome || 'passed');
const say = msg => { const a = $('#announce'); a.textContent = ''; setTimeout(() => { a.textContent = msg; }, 30); };
// A Sentinel is an AI reviewer on any provider (Claude by default); PROV(id) is its provider, model and calibration.
const SENTINEL_KINDS = D.sentinel_kinds || ['claude', 'claude_code'];
const isSentinel = k => SENTINEL_KINDS.includes(k);
const PROVIDER_OF = k => (D.provider_by_kind || {})[k] || k;
const PROV = id => { const p = (D.reviewer_provenance || {})[id]; return p ? `${p.provider_label} · ${p.model}${p.calibration === 'uncalibrated' ? ' · uncalibrated' : ''}` : ''; };
const OUTCOME_SHORT = {passed: 'passed', flagged: 'flagged', rejected: 'rejected'};
// The panel's display names (the Sentinels and the Probes); ids stay in the data and show beside the names.
const NAME = id => ((D.reviewer_names || {})[id] || {}).name || id;
const nameWithId = id => `${esc(NAME(id))} <span class="mono idtag" title="reviewer id">${esc(id)}</span>`;
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const kindTag = k => k === 'simulated' ? '<span class="tag sim">Probe · not a person</span>' : isSentinel(k) ? `<span class="tag cl">Sentinel · ${esc(PROVIDER_OF(k))}</span>` : `<span class="tag">${esc(k || 'unknown')}</span>`;
function niceTicks(lo, hi, n){
  if (!(hi > lo)) return [lo];
  const raw = (hi-lo)/Math.max(1,n), mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo/step)*step; v <= hi + 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

// ---------- addresses and history ----------
// Every page has one clean address (/explore/galaxy/, /candidates/<dip>/, /planets/<slug>/); routes.py holds the
// table, and RT is the page's copy. The views still name places in the app's old form ('#/galaxy?focus=x'):
// R() turns that into the clean link (a deep link keeps its query), and setHash() into the address bar,
// where view state (filters, sorts, layouts) is left out: the address names the page, never its settings.
// A change of page made by the viewer is a new history entry; a tidy-up of the address replaces the current one.
// Returns false when the browser refuses (a sandboxed context), so the caller can say so.
const RT = D.routes;
const R = h => String(h).startsWith('#/') ? rtFromHash(h, true) : h;
function setAddress(url, push){
  url = String(url).startsWith('#/') ? rtFromHash(url, false) : url;
  if (location.pathname + location.search + location.hash === url) return true;
  try { if (push) history.pushState(null, '', url); else history.replaceState(null, '', url); return true; } catch (e) { return false; }
}
const setHash = setAddress;

// ---------- links and dates ----------
const DIP_IDS = new Set(D.dossier_ids);
const dipHref = (id, section) => rtUrl('candidates', {dip: id, section: section || null});
// A dip identifier: a link to its dossier in the Docket when the run has one, plain text otherwise.
// A dip's plain name: "pi Men, dip 2 (6.27 d)" for one of the run's dips; a search-feed entry is "entry 4" beside
// its TIC. The stored id stays in the title, for anyone matching it to a file.
const DIP_NAME = id => ((D.dips || {})[id] || {}).label || null;
const entryNo = id => { const m = /-(\d+)$/.exec(String(id)); return m ? 'entry ' + (Number(m[1]) + 1) : String(id); };
const dipLink = id => DIP_IDS.has(id) ? `<a class="dip" href="${dipHref(id)}" title="Open its case file (stored id ${esc(id)})">${esc(DIP_NAME(id) || id)}</a>` : `<span class="dip" title="Stored id ${esc(id)}; no case file in this run">${esc(entryNo(id))}</span>`;
// A stored ISO-8601 time as a readable local date; the full stored value stays in the title.
function when(iso){
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return esc(iso || 'not stored');
  let s;
  // Shown in UTC, and said so, whatever the viewer's zone; the stored ISO value stays in the title.
  try { s = d.toLocaleString('en-GB', {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC'}) + ' UTC'; } catch (e) { s = d.toUTCString(); }
  return `<time datetime="${esc(iso)}" title="${esc(iso)}">${esc(s)}</time>`;
}

// ---------- widget layout (URL first, then localStorage, then the default) ----------
const WIDGET_IDS = D.widgets.map(w => w.id);
const WIDGET_LABEL = Object.fromEntries(D.widgets.map(w => [w.id, w.label]));
const SIZES = ['S', 'M', 'L'], SIZE_NAME = {S: 'small', M: 'medium', L: 'large'};
const LAYOUT_KEY = 'setuhq-app:layout:' + D.title;
// Same rule as app.widget_layout in Python: each known widget exactly once, unknown ids dropped, unknown sizes defaulted.
function normaliseLayout(raw, ids, sizes){
  const out = [], seen = new Set(), def = id => (sizes && sizes[id]) || 'M';
  if (Array.isArray(raw)) for (const it of raw){
    if (!it || typeof it !== 'object') continue;
    if (!ids.includes(it.id) || seen.has(it.id)) continue;
    seen.add(it.id); out.push({id: it.id, visible: it.visible !== false, size: ['S','M','L'].includes(it.size) ? it.size : def(it.id)});
  }
  for (const id of ids) if (!seen.has(id)) out.push({id, visible: true, size: def(id)});
  return out;
}
function readLayout(storage, key, ids, sizes){
  let raw = null;
  try { raw = storage ? JSON.parse(storage.getItem(key)) : null; } catch (e) { raw = null; }
  return normaliseLayout(raw, ids, sizes);
}
// Same format as app.encode_layout / app.decode_layout: "kpis.L,top.L,runs.M.hidden,...".
function encodeLayout(lay){
  return lay.map(x => `${x.id}.${x.size}${x.visible ? '' : '.hidden'}`).join(',');
}
function decodeLayout(text, ids, sizes){
  const items = String(text || '').split(',').map(p => p.trim().split('.')).filter(b => b[0]).map(b => ({id: b[0], size: b[1], visible: !(b.length > 2 && b[2] === 'hidden')}));
  return normaliseLayout(items, ids, sizes);
}
function getStorage(){ try { return window.localStorage; } catch (e) { return null; } }
// ownLayout is the viewer's default. A layout from a shared link is shown for that view only and is
// never written to storage; the default changes only when the viewer uses a layout control.
let ownLayout = readLayout(getStorage(), LAYOUT_KEY, WIDGET_IDS, D.default_size);
let layout = ownLayout.map(x => ({...x})), sharedView = false;
function saveLayout(){
  ownLayout = layout.map(x => ({...x})); sharedView = false;
  try { const s = getStorage(); if (s) s.setItem(LAYOUT_KEY, JSON.stringify(ownLayout)); } catch (e) { /* storage blocked: the layout lasts for this visit */ }
}
// The layout lives in this browser (localStorage); the address never carries it. "Copy link to this view"
// makes a link that does: /candidates/?layout=kpis.L,top.L,... (plus the feed's sort and filter when not the default).
function syncLayoutURL(){ /* nothing: the address names the page only */ }

// ---------- overview ----------
function widgetBody(id){
  function topBody(r){
    // Group the top dips by signal so repeat transits of one signal read as one signal, not several discoveries.
    const groups = [];
    for (const x of r.top){ let g = groups.find(g => g.signal_id === x.signal_id); if (!g){ g = {signal_id: x.signal_id, dips: []}; groups.push(g); } g.dips.push(x); }
    return `<ul class="toplist">${groups.map(g => {
      const f = g.dips[0], n = g.dips.length, xm = g.dips.find(x => x.consistent_with);
      const tic = String(f.target).replace(/^TIC\s*/, ''), star = (D.tic_names || {})[tic];
      const head = `<div><b>${star ? esc(star) : esc(f.target)}</b> <span class="muted">${star ? `· ${esc(f.target)} ` : ''}· signal ${f.period_days ? 'P ' + fmt(f.period_days,3) + ' d' : 'with no period (one transit)'} · ${n} of the top dips${f.signal_dips > n ? `, ${f.signal_dips} dips in the run` : ''}</span></div>`;
      const note = xm ? `<p class="note">Archive cross-match: ${n === 1 ? 'this dip is' : `these ${n} dips are`} consistent with <b>${esc(xm.consistent_with)}</b>, a published planet${xm.dP_pct !== null && xm.dP_pct !== undefined ? ` (period difference ${fmt(xm.dP_pct,2)}%)` : ''}. ${n === 1 ? 'It is a transit' : 'They are repeat transits'} of one known planet, not ${n === 1 ? 'a discovery' : n + ' discoveries'}. ${esc(D.no_detection)}</p>` : '';
      // One line per dip. On a phone the status shows as its short word and the hedge moves to the
      // signal line above, so each row stays one 44 px line; the full words stay for screen readers.
      return `<li>${head}${note}<ul>${g.dips.map(x => `<li class="toprow">${dipLink(x.id)}<span class="mono">SNR ${fmt(x.snr,1)}</span><span class="mono">${fmt(x.depth_ppm,0)} ppm</span><span class="st"><span class="long">${esc(x.outcome_label)}</span><span class="short" aria-hidden="true">${esc(OUTCOME_SHORT[x.outcome] || x.outcome_label)}</span></span>${DIPTAG(x.outcome)}</li>`).join('')}</ul></li>`;
    }).join('')}</ul>`;
  }
  const r = D.run, c = r.counts || {}, dc = r.docket_counts || {};
  if (id === 'kpis'){
    const kinds = Object.values(r.reviewer_kinds), sim = kinds.filter(k => k === 'simulated').length, cl = kinds.filter(isSentinel).length;
    const tiles = [[c.subjects, 'subjects'], [c.classifications, 'reviews'], [dc.signals, 'signals'], [dc.dips, 'dips'], [dc.passed, 'signals passed vetting'], [dc.flagged, 'signals flagged for review']];
    return `<div class="kpis">${tiles.map(([v,l]) => `<div class="kpi"><b>${esc(v ?? '–')}</b><span>${esc(l)}</span></div>`).join('')}</div>
      <p class="muted" style="margin:0;font-size:12px">Run ${esc(r.name)}, ${when(r.created_at)}. ${esc(dc.rejected ?? 0)} signal${dc.rejected===1?'':'s'} rejected by vetting. The light curves are measured (${esc((D.config.inputs[0]||{}).source || 'stored input')}); the reviews come from ${plural(cl, 'Sentinel')} and ${plural(sim, 'Probe')}, no people.</p>`;
  }
  if (id === 'discoveries'){
    const f = D.catalog.candidates, nNew = f.filter(x => x.status === 'new_candidate').length, nKnown = f.filter(x => x.status === 'known_toi').length;
    if (!D.catalog.path) return '<p class="empty">No search catalogue was given to this build.</p>';
    return `<div><span class="big">${f.length}</span> <span class="muted">feed entries</span></div>
      <p style="margin:0">${nKnown} match a known TOI period · ${nNew} new candidate${nNew===1?'':'s'} · ${esc(D.catalog.targets_reviewed)} targets reviewed</p>
      <p class="muted" style="margin:0;font-size:12px">Catalogue updated ${when(D.catalog.updated)}.</p>`;
  }
  if (id === 'runs'){
    const runs = D.catalog.runs.slice(-5).reverse();
    if (!runs.length) return '<p class="empty">No search runs are stored in the catalogue.</p>';
    return `<ul class="runlist">${runs.map(x => `<li><b>${when(x.time)}</b><span>${(x.targets||[]).length} targets · ${esc(x.new ?? '–')} new · ${esc(x.known ?? '–')} known · ${(x.errors||[]).length} error${(x.errors||[]).length===1?'':'s'}</span></li>`).join('')}</ul>
      <p class="muted" style="margin:0;font-size:12px">This page's run: ${esc(r.name)}, ${when(r.created_at)}.</p>`;
  }
  if (id === 'top'){
    if (!r.top.length) return '<p class="empty">This run stored no candidates.</p>';
    return `${topBody(r)}
      <p class="muted" style="margin:0;font-size:12px">The run's dips with the highest stored SNR, grouped by signal; the tag is each dip's vetting status. Select a dip to open its dossier.</p>`;
  }
  return '';
}
const WIDGET_LINK = {kpis: ['#/transit', 'Open the lead candidate'], discoveries: ['#h-feed', 'Go to the feed table'], runs: ['#/runs', 'Open Runs'], top: ['#/transit', 'Open the lead candidate']};
function widgetControls(x, pos, nShown){
  const name = esc(WIDGET_LABEL[x.id]);
  return `<div class="wctl" role="group" aria-label="Arrange ${name}">
    <button class="btn" data-act="up" data-id="${x.id}" aria-label="Move ${name} up" aria-disabled="${pos === 0}">↑</button>
    <button class="btn" data-act="down" data-id="${x.id}" aria-label="Move ${name} down" aria-disabled="${pos === nShown - 1}">↓</button>
    <span class="seg" role="group" aria-label="Size of ${name}">${SIZES.map(z => `<button class="btn" data-act="size" data-size="${z}" data-id="${x.id}" aria-pressed="${x.size === z}" aria-label="${SIZE_NAME[z]}" title="${SIZE_NAME[z]}">${z}</button>`).join('')}</span>
    <button class="btn" data-act="hide" data-id="${x.id}" aria-label="Hide ${name}">Hide</button></div>`;
}
function renderWidgets(){
  const grid = $('#widgets');
  const shown = layout.filter(x => x.visible);
  grid.innerHTML = shown.length ? shown.map((x, i) => `<section class="card widget size-${x.size}" data-widget="${x.id}" aria-labelledby="w-${x.id}">
    <header><h2 id="w-${x.id}">${esc(WIDGET_LABEL[x.id])}</h2>${widgetControls(x, i, shown.length)}</header>${widgetBody(x.id)}
    <a class="wopen" href="${esc(R(WIDGET_LINK[x.id][0]))}">${esc(WIDGET_LINK[x.id][1])}</a></section>`).join('')
    : '<p class="empty">Every widget is hidden. Show one above, or reset the layout.</p>';
  const hidden = layout.filter(x => !x.visible);
  $('#hiddenlist').innerHTML = hidden.length ? `<span>Hidden:</span>${hidden.map(x => `<button class="btn" data-act="show" data-id="${x.id}">Show ${esc(WIDGET_LABEL[x.id])}</button>`).join('')}` : '<span class="muted">All four widgets shown.</span>';
}
function renderOverview(){
  renderWidgets(); syncLayoutURL();
  $('#sharednote').hidden = !sharedView;
}
function layoutAction(act, id, size){
  const i = layout.findIndex(x => x.id === id); if (i < 0) return;
  const name = WIDGET_LABEL[id];
  let focusSel = `[data-act="${act}"][data-id="${id}"]${act === 'size' ? `[data-size="${size}"]` : ''}`;
  if (act === 'hide'){ layout[i].visible = false; say(`${name} hidden. Use Show ${name} to bring it back.`); focusSel = `[data-act="show"][data-id="${id}"]`; }
  else if (act === 'show'){ layout[i].visible = true; say(`${name} shown.`); focusSel = `[data-act="hide"][data-id="${id}"]`; }
  else if (act === 'size'){ if (!SIZES.includes(size)) return; layout[i].size = size; say(`${name} size ${SIZE_NAME[size]}.`); }
  else if (act === 'up' || act === 'down'){
    // Move past the neighbouring shown widget; hidden ones keep their place in the list.
    const vis = layout.map((x, k) => x.visible ? k : -1).filter(k => k >= 0), p = vis.indexOf(i), q = act === 'up' ? p - 1 : p + 1;
    if (p < 0 || q < 0 || q >= vis.length){ say(`${name} is already ${act === 'up' ? 'first' : 'last'}.`); return; }
    const j = vis[q]; [layout[i], layout[j]] = [layout[j], layout[i]];
    say(`${name} moved to position ${q+1} of ${vis.length}.`);
  }
  saveLayout(); renderOverview();
  const back = $('#route-explorer ' + focusSel); if (back) back.focus();
}
$('#route-explorer').addEventListener('click', e => { const b = e.target.closest('button[data-act]'); if (b) layoutAction(b.dataset.act, b.dataset.id, b.dataset.size); });
$('#ownlayout').addEventListener('click', () => { layout = ownLayout.map(x => ({...x})); sharedView = false; renderOverview(); $('#customise').focus(); say('Showing your own layout.'); });
// The cards' controls stay out of the way until the viewer asks to customise.
$('#customise').addEventListener('click', () => {
  const on = $('#customise').getAttribute('aria-pressed') !== 'true';
  $('#customise').setAttribute('aria-pressed', String(on)); $('#customise').textContent = on ? 'Done' : 'Customise';
  $('#widgets').classList.toggle('customising', on); $('#layouttools').hidden = !on;
  say(on ? 'Customise: each card can be hidden, moved or resized.' : 'Done customising.');
});
$('#resetlayout').addEventListener('click', () => { layout = normaliseLayout(null, WIDGET_IDS, D.default_size); saveLayout(); renderOverview(); $('#resetlayout').focus(); say('Layout reset: every widget shown in the default order and size.'); });

// ---------- candidates (the Docket) ----------
const DOCKET_SECTIONS = ['strip', 'signal', 'ctx', 'cmp', 'ledger', 'rev'];
// The Docket reads a dip id from its own location hash on load, so the frame loads the shell's copy of the
// Docket (a file beside the site) with the dip as that hash.
// The shell's copy of the Docket carries a small bridge: it reports the selected dip and the section
// in view by postMessage, and takes the same from the shell, so the address bar follows the frame.
const BLOCKED_TEXT = 'The dossier could not load in this view.';
const LOADING_TEXT = 'Loading the Docket…';
const frame = {ready: false, mode: null, dip: null, section: null, pending: null, crossOrigin: false, timer: null, gen: 0,
  frameURLFailed: false, shellURLFailed: false};
// The shell's copy of the Docket is a file of its own (D.docket_frame, same origin); the dip is its hash.
// Each example run has its own case file; a dip opens its own run's (D.docket_frames, by run name).
const runOf = dip => ((D.dips || {})[dip] || {}).run || D.run.name;
const RUNCTX = dip => (D.run_ctx || {})[runOf(dip)] || {};
function docketURL(dip){ return ((D.docket_frames || {})[runOf(dip)] || D.docket_frame) + (dip ? '#' + encodeURIComponent(dip) : ''); }
const fullHref = dip => (RUNCTX(dip).case_file || '/candidates/case-file/') + (dip ? '#' + encodeURIComponent(dip) : '');
function setFullHrefs(dip){ for (const a of $$('#fullpage, #topfull, #blockedlink')) a.href = fullHref(dip); }
// Keep the shell URL and the full-page links on the dip (and section) the frame shows.
function syncShellURL(){
  setFullHrefs(frame.dip);
  const pick = $('#dippick'); if (pick && frame.dip && pick.value !== frame.dip) pick.value = frame.dip;
  if (current !== 'candidates' || !frame.dip) return;
  const h = dipHref(frame.dip, frame.section);
  if (location.pathname + location.hash !== h){
    // A new dip is a new history entry (Back returns to the last dip); a section change only replaces.
    const shown = (rtParse(location.pathname, location.search) || {params: {}}).params.dip;
    const push = !!frame.dip && !!shown && shown !== frame.dip;
    frame.shellURLFailed = !setHash(h, push);
    if (frame.ready) readyStatus();
  }
}
function tellFrame(dip, section){
  if (dip) { frame.dip = dip; frame.section = section || null; }
  else if (section) frame.section = section;
  try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', dip, section}, '*'); } catch (e) { /* frame gone */ }
  syncShellURL();
}
// The status line: a notice about the address (an unknown dip, say) comes first, then the frame's state.
function frameStatus(text){ const t = [frame.notice, text].filter(Boolean).join(' '); const s = $('#framestatus'); s.textContent = t; s.hidden = !t; fitFrame(); }
// The status line once the Docket is showing: say when an address cannot follow the selected dip.
function readyStatus(){
  frameStatus(frame.shellURLFailed ? 'Address bar not updated in this view. Open full page goes to the selected dip.'
    : frame.crossOrigin ? 'The Docket runs in a separate origin here (as when this page is opened from a file), so this view follows it by messages only. If the address bar stops following the selected dip, use Open full page.'
    : frame.frameURLFailed ? 'Address bar not updated inside the Docket in this view (a fallback frame cannot change its own address). The address bar above and Open full page follow the selected dip by messages.'
    : '');
}
// Desktop: the frame takes the viewport height less what sits above it (the route header, the tools,
// the status line) and the page's bottom padding, so the page itself does not scroll.
// The CSS keeps calc(100vh - 190px) as the fallback until this has run.
function fitFrame(){
  const f = $('#docketframe');
  if (!f || f.hidden || f.classList.contains('waiting') || $('#route-candidates').hidden || matchMedia('(max-width:699.98px)').matches) return;
  const top = f.getBoundingClientRect().top + window.scrollY;
  const below = parseFloat(getComputedStyle($('#main')).paddingBottom) || 0;
  document.documentElement.style.setProperty('--frame-offset', Math.ceil(top + below) + 'px');
}
function showBlocked(){
  clearTimeout(frame.timer);
  const f = $('#docketframe'); f.hidden = true; f.classList.remove('waiting');
  $('#frameblocked').hidden = false; frameStatus('');
  document.documentElement.style.removeProperty('--frame-offset');
  setFullHrefs(frame.dip);
  say(BLOCKED_TEXT + ' Open it on its own page.');
}
function frameLoadFailed(gen){
  if (gen !== frame.gen || frame.ready) return;
  showBlocked();
}
function onFrameReady(m){
  frame.ready = true; clearTimeout(frame.timer);
  const f = $('#docketframe'); f.hidden = false; f.classList.remove('waiting'); $('#frameblocked').hidden = true;
  try { void f.contentWindow.document.body; frame.crossOrigin = false; } catch (e) { frame.crossOrigin = true; }
  readyStatus();
  const p = frame.pending; frame.pending = null;
  if (p && ((p.dip && p.dip !== m.dip) || p.section)) tellFrame(p.dip, p.section);
  else { frame.dip = m.dip || frame.dip; syncShellURL(); }
  try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', theme: currentTheme()}, '*'); } catch (e) { /* frame gone */ }
}
window.addEventListener('message', e => {
  const f = $('#docketframe'), m = e.data;
  if (!f || e.source !== f.contentWindow || !m || m.source !== 'setuhq-docket') return;
  if (m.urlFailed) frame.frameURLFailed = true;
  if (m.kind === 'ready'){ onFrameReady(m); return; }
  if (!frame.ready) return;  // the Docket's own first pick, before the shell's dip is applied
  if (m.kind === 'dip' && m.dip){ if (m.dip !== frame.dip){ frame.section = null; if (frame.notice){ frame.notice = ''; readyStatus(); } } frame.dip = m.dip; }
  else if (m.kind === 'section'){ frame.section = DOCKET_SECTIONS.includes(m.section) ? m.section : null; if (m.dip) frame.dip = m.dip; }
  syncShellURL();
  if (m.urlFailed) readyStatus();
});
function loadDocket(dip, section, mode){
  const f = $('#docketframe'), url = docketURL(dip), gen = ++frame.gen;
  frame.run = runOf(dip);
  Object.assign(frame, {ready: false, mode: 'file', dip, section: section || null, pending: {dip, section: section || null},
    frameURLFailed: false});
  // Not shown until it reports ready: an empty bordered box would sit under the loading line.
  f.hidden = false; f.classList.add('waiting'); $('#frameblocked').hidden = true;
  frameStatus(LOADING_TEXT);
  clearTimeout(frame.timer);
  // A frame that never reports ready did not load (blocked by frame-src, say): try srcdoc, then say so.
  // The srcdoc copy needs no fetch, so its wait is shorter.
  frame.timer = setTimeout(() => frameLoadFailed(gen), 6000);
  const onload = () => {
    let blank = false;
    try { blank = f.contentWindow.location.href === 'about:blank'; } catch (e) { /* cross-origin: an error page or file:// */ }
    if (blank) { f.addEventListener('load', onload, {once: true}); return; }
    setTimeout(() => frameLoadFailed(gen), 800);
  };
  f.addEventListener('load', onload, {once: true});
  f.src = url;
}
function openDip(dip, section){
  const f = $('#docketframe');
  if (dip && !DIP_IDS.has(dip)){
    // An unknown dip id: say so, and rewrite the address to the lead dip (replace, not a new entry).
    const lead = leadDip();
    frame.notice = `No dip ${dip} in run ${D.run.name}; showing the lead dip${lead ? ' ' + lead : ''}.`;
    say(frame.notice); dip = lead;
    if (lead) setAddress(dipHref(lead), false);
    if (frame.ready) readyStatus(); else frameStatus(f.dataset.loaded ? LOADING_TEXT : '');
  } else if (dip) frame.notice = '';
  if (!DOCKET_SECTIONS.includes(section)) section = null;
  if (!f.dataset.loaded || (dip && frame.run && runOf(dip) !== frame.run)){ f.dataset.loaded = '1'; loadDocket(dip, section); setFullHrefs(dip); }
  else if (!frame.ready){ if (dip || section) frame.pending = {dip: dip || frame.dip, section}; setFullHrefs(dip || frame.dip); }
  else if (dip || section) tellFrame(dip, section);
  else syncShellURL();
  if (dip) say(`Docket open on dip ${dip}${section === 'ledger' ? ', verdict ledger' : ''}.`);
}
// The lead dip: the highest-SNR dip of the Overview's lead signal, else the first dossier.
const leadDip = () => (D.hero && D.hero.lead && D.hero.lead.dip) || D.dossier_ids[0] || null;
// The phone dip picker above the frame: every dip in time order, with its letter and outcome.
function renderDipPicker(){
  const sel = $('#dippick'); if (!sel) return;
  // Grouped by star: the lead run's dips first, then each other example run's.
  sel.innerHTML = (D.showcase || []).map(c => `<optgroup label="${esc(c.star)}">${c.dips.map(w => `<option value="${esc(w.id)}">${esc(w.label)} · ${esc(w.outcome)}</option>`).join('')}</optgroup>`).join('');
  if (frame.dip) sel.value = frame.dip;
}
function renderCandidates(){ renderDipPicker(); /* the frame loads in openDip, with the dip from the URL */ }

// ---------- discoveries (the feed) ----------
const disc = {sort: 'snr', dir: -1, filter: 'all'};
// The Feed's sort and filter live in the URL (#/explorer?sort=depth&filter=new) like the Overview
// layout, and in localStorage as the viewer's default. A view opened from a link is shown for that
// view only; storage is written only when the viewer changes the sort or the filter.
const FEED_SORTS = D.feed_view.sorts, FEED_FILTERS = D.feed_view.filters, FEED_NUMERIC = D.feed_view.numeric;
const FEED_KEY = 'setuhq-app:feed:' + D.title;
const shortOf = (map, key) => Object.keys(map).find(k => map[k] === key);
// Same rule as app.feed_view in Python.
function normaliseFeedView(raw){
  raw = raw && typeof raw === 'object' ? raw : {};
  const sort = Object.prototype.hasOwnProperty.call(FEED_SORTS, raw.sort) ? raw.sort : D.feed_view.default.sort;
  const defDir = FEED_NUMERIC.includes(sort) ? 'desc' : 'asc';
  const dir = raw.dir === 'asc' || raw.dir === 'desc' ? raw.dir : defDir;
  const filter = Object.prototype.hasOwnProperty.call(FEED_FILTERS, raw.filter) ? raw.filter : D.feed_view.default.filter;
  return {sort, dir, filter};
}
// Same format as app.encode_feed_view / app.decode_feed_view.
function encodeFeedView(v){
  v = normaliseFeedView(v);
  const defDir = FEED_NUMERIC.includes(v.sort) ? 'desc' : 'asc';
  return `sort=${v.sort}${v.dir === defDir ? '' : '&dir=' + v.dir}&filter=${v.filter}`;
}
function decodeFeedView(params){
  const get = k => params.get(k) || undefined;
  return normaliseFeedView({sort: get('sort'), dir: get('dir'), filter: get('filter')});
}
const currentFeedView = () => ({sort: shortOf(FEED_SORTS, disc.sort), dir: disc.dir > 0 ? 'asc' : 'desc', filter: shortOf(FEED_FILTERS, disc.filter)});
function applyFeedView(v){ v = normaliseFeedView(v); disc.sort = FEED_SORTS[v.sort]; disc.dir = v.dir === 'asc' ? 1 : -1; disc.filter = FEED_FILTERS[v.filter]; }
let ownFeedView = (() => { let raw = null; try { const s = getStorage(); raw = s ? JSON.parse(s.getItem(FEED_KEY)) : null; } catch (e) { raw = null; } return normaliseFeedView(raw); })();
function saveFeedView(){
  ownFeedView = currentFeedView();
  try { const s = getStorage(); if (s) s.setItem(FEED_KEY, JSON.stringify(ownFeedView)); } catch (e) { /* storage blocked: the view lasts for this visit */ }
}
// push: the viewer changed the sort or the filter, so Back returns to the previous view.
function syncFeedURL(push){
  if (current !== 'explorer') return;
  // The Feed table's sort and filter, then the scatter's filters; each left out when it is the default.
  const fv = encodeFeedView(currentFeedView()), q = [fv === encodeFeedView(D.feed_view.default) ? '' : fv, encodeExView(currentEx())].filter(Boolean).join('&');
  setHash('#/explorer' + (q ? '?' + q : ''), !!push);
}
applyFeedView(ownFeedView);
const COLS = [
  ['tic', 'TIC', x => x.tic, x => (D.tic_names || {})[x.tic] ? `${esc(x.tic)} · ${objLink('star', D.tic_names[x.tic])}` : esc(x.tic)],
  ['candidate_id', 'entry', x => x.candidate_id, x => dipLink(x.candidate_id)],
  ['t_center', 'mid-time', x => x.t_center, x => `${fmt(x.t_center,3)}<small>${esc(x.time_unit)}</small>`],
  ['period_days', 'period (d)', x => x.period_days, x => fmt(x.period_days,4)],
  ['depth_ppm', 'depth (ppm)', x => x.depth_ppm, x => fmt(x.depth_ppm,0)],
  ['snr', 'SNR', x => x.snr, x => fmt(x.snr,1)],
  ['status', 'status', x => x.status, x => `${esc(D.status_label[x.status] || x.status)} ${FEEDTAG(x)}`],
];
const NUMERIC = new Set(['tic','t_center','period_days','depth_ppm','snr']);
function discRows(){
  const f = D.catalog.candidates.filter(x => disc.filter === 'all' || x.status === disc.filter);
  const col = COLS.find(c => c[0] === disc.sort), key = col[2];
  return f.slice().sort((a, b) => { const va = key(a), vb = key(b); return (va < vb ? -1 : va > vb ? 1 : 0) * disc.dir; });
}
// Dip ids link to the Docket only when this run stored a dossier for them; say so when a row has none.
function noDossierLine(rows){
  const missing = rows.filter(x => !DIP_IDS.has(x.candidate_id)).length;
  if (!missing) return '';
  const text = missing === rows.length ? 'No dossier stored for these rows in this run.' : `No dossier stored for ${missing} of these rows in this run; their dip ids are plain text.`;
  return `<span class="capnote" id="nodossier">${text}</span>`;
}
// A known TOI match is an archive comparison: wherever one is shown, say this page claims no detection.
function archiveNote(rows){
  if (!rows.some(x => x.status === 'known_toi')) return '';
  return `<span class="capnote" id="archivenote">A known TOI match compares a stored BLS period with archive values. ${esc(D.no_detection)}</span>`;
}
function renderDiscTable(){
  const rows = discRows();
  $('#disctable').innerHTML = `<table><caption><span class="sr">Feed, sorted by ${esc(disc.sort)} ${disc.dir > 0 ? 'ascending' : 'descending'}. Every entry is a ${esc(D.unconfirmed)}.</span>${noDossierLine(rows)}${archiveNote(rows)}</caption>
    <thead><tr>${COLS.map(c => `<th scope="col" class="${NUMERIC.has(c[0]) ? 'num' : ''}" aria-sort="${disc.sort === c[0] ? (disc.dir > 0 ? 'ascending' : 'descending') : 'none'}"><button data-sort="${c[0]}">${esc(c[1])}<span aria-hidden="true">${disc.sort === c[0] ? (disc.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`).join('')}</tr></thead>
    <tbody>${rows.length ? rows.map(x => `<tr>${COLS.map((c, k) => k === 0 ? `<th scope="row" class="num" data-label="${esc(c[1])}">${c[3](x)}</th>` : `<td class="${NUMERIC.has(c[0]) ? 'num' : ''} c-${c[0]}" data-label="${esc(c[1])}">${c[3](x)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${COLS.length}" class="empty">No feed entries with this status.</td></tr>`}</tbody></table>`;
  // Phone: a labelled "Sort" group (outlined, unlike the filled filter chips) and one three-line card per entry.
  $('#disctable').insertAdjacentHTML('beforeend', feedSortBar() + feedCards(rows));
  $('#disccount').textContent = `${rows.length} of ${D.catalog.candidates.length} entries shown.`;
}
function feedSortBar(){
  return `<div class="sortbar" role="group" aria-label="Sort by"><span class="sortlbl" aria-hidden="true">Sort</span>${COLS.filter(c => c[0] !== 't_center').map(c => `<button class="sortbtn" data-sort="${c[0]}" aria-pressed="${disc.sort === c[0]}">${esc(c[1])}${disc.sort === c[0] ? `<span aria-hidden="true"> ${disc.dir > 0 ? '▲' : '▼'}</span><span class="sr">, ${disc.dir > 0 ? 'ascending' : 'descending'}</span>` : ''}</button>`).join('')}</div>`;
}
// One card per entry, three lines: the dip and its status; TIC · P · depth · SNR on one mono line; the hedge.
function feedCards(rows){
  if (!rows.length) return '<p class="empty feedcards">No feed entries with this status.</p>';
  return `<ol class="feedcards">${rows.map(x => `<li><div class="fc1">${dipLink(x.candidate_id)}<span class="fcst">${esc(D.status_label[x.status] || x.status)}</span></div><div class="fc2 mono">${ticLink(x.tic)} · P ${fmt(x.period_days,3)} d · ${fmt(x.depth_ppm,0)} ppm · SNR ${fmt(x.snr,1)}</div><div class="fc3">${FEEDTAG(x)} mid-time ${fmt(x.t_center,2)} ${esc(x.time_unit)}</div></li>`).join('')}</ol>`;
}
function renderDiscHead(){
  const f = D.catalog.candidates, n = s => f.filter(x => x.status === s).length, ft = D.catalog.found_times;
  const found = !ft.length ? 'no stored find time' : ft.length === 1 ? `found in the catalogue run of ${when(ft[0])}` : `found between ${when(ft[0])} and ${when(ft[ft.length-1])}`;
  $('#feedhead').innerHTML = f.length ? `${f.length} entries, ${found}. <b>${n('known_toi')} match a known TOI period</b>; ${n('new_candidate')} are new candidates. Every entry is a ${esc(D.unconfirmed)}.${n('known_toi') ? ` A TOI match is an archive comparison. ${esc(D.no_detection)}` : ''}` : 'The feed is empty.';
}
function renderDiscChips(){
  const f = D.catalog.candidates, n = s => f.filter(x => x.status === s).length;
  const chips = [['all', `all ${f.length}`], ['new_candidate', `new ${n('new_candidate')}`], ['known_toi', `known TOI ${n('known_toi')}`]];
  $('#discchips').innerHTML = chips.map(([k, l]) => `<button class="chip" data-f="${k}" aria-pressed="${disc.filter === k}">${esc(l)}</button>`).join('');
}

$('#disctable').addEventListener('click', e => {
  const b = e.target.closest('button[data-sort]'); if (!b) return;
  const k = b.dataset.sort;
  if (disc.sort === k) disc.dir = -disc.dir; else { disc.sort = k; disc.dir = NUMERIC.has(k) ? -1 : 1; }
  saveFeedView(); syncFeedURL(true);
  renderDiscTable();
  const again = $(`#disctable ${b.closest('.sortbar') ? '.sortbar' : 'thead'} button[data-sort="${k}"]`); if (again) again.focus();
  say(`Sorted by ${b.textContent.replace(/[▲▼]/g,'')}, ${disc.dir > 0 ? 'ascending' : 'descending'}.`);
});
$('#discchips').addEventListener('click', e => {
  const b = e.target.closest('button[data-f]'); if (!b) return;
  disc.filter = b.dataset.f; saveFeedView(); syncFeedURL(true); renderDiscChips(); renderDiscTable();
  $(`#discchips button[data-f="${disc.filter}"]`).focus();
  say($('#disccount').textContent);
});
function histogram(box, values, label, unit, maxRule){
  box.innerHTML = '';
  const vals = values.filter(v => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number);
  const W = 340, H = 190, pl = 34, pr = 10, pt = 14, pb = 34;
  const h3 = document.createElement('h3'); h3.textContent = label; box.appendChild(h3);
  if (!vals.length){ box.insertAdjacentHTML('beforeend', '<p class="empty">No stored values.</p>'); return; }
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (maxRule !== undefined) hi = Math.max(hi, maxRule);
  if (hi === lo){ lo -= 1; hi += 1; }
  const ticks = niceTicks(lo, hi, 6), step = ticks.length > 1 ? ticks[1] - ticks[0] : (hi - lo);
  const a = Math.floor(lo / step) * step, b = Math.max(a + step, Math.ceil(hi / step) * step);
  const nb = Math.max(1, Math.round((b - a) / step));
  const counts = new Array(nb).fill(0);
  for (const v of vals) counts[Math.min(nb - 1, Math.floor((v - a) / step))]++;
  const cmax = Math.max(...counts);
  const X = v => pl + (v - a) / (b - a) * (W - pl - pr), Y = c => pt + (1 - c / cmax) * (H - pt - pb);
  const summary = counts.map((c, i) => `${fmt(a + i*step, step < 1 ? 2 : 0)} to ${fmt(a + (i+1)*step, step < 1 ? 2 : 0)}: ${c}`).join('; ');
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Histogram of ${label}, ${vals.length} feed entries. ${summary}.`}, box);
  for (const c of niceTicks(0, cmax, 3)){ el('line', {x1: pl, x2: W - pr, y1: Y(c), y2: Y(c), class: 'grid'}, svg); tx(svg, pl - 6, Y(c) + 4, String(c), 'end'); }
  counts.forEach((c, i) => {
    if (!c) return;
    const x0 = X(a + i*step) + 1, x1 = X(a + (i+1)*step) - 1;
    el('rect', {x: x0, y: Y(c), width: Math.max(1, x1 - x0), height: Y(0) - Y(c), class: 'bar'}, svg);
    tx(svg, (x0 + x1) / 2, Y(c) - 3, String(c), 'middle', 'lbl');
  });
  el('line', {x1: pl, x2: W - pr, y1: Y(0), y2: Y(0), stroke: 'var(--muted)'}, svg);
  const every = Math.ceil((nb + 1) / 6);
  for (let i = 0; i <= nb; i += every){ const v = a + i*step; tx(svg, X(v), H - pb + 14, Number(v.toPrecision(6)).toString(), 'middle'); }
  tx(svg, W - pr, H - 4, unit, 'end');
  if (maxRule !== undefined){
    el('line', {x1: X(maxRule), x2: X(maxRule), y1: pt, y2: Y(0), stroke: 'var(--flag)', 'stroke-dasharray': '4 3'}, svg);
    tx(svg, X(maxRule) - 4, pt + 10, 'feed rule', 'end');
  }
  box.insertAdjacentHTML('beforeend', `<p class="muted" style="margin:4px 0 0;font-size:12px">${vals.length} feed entries, stored values, bin width ${Number(step.toPrecision(6))} ${esc(unit)}.</p>`);
}
function timeline(box){
  box.innerHTML = '';
  const f = D.catalog.candidates;
  if (!f.length){ box.innerHTML = '<p class="empty">The feed is empty.</p>'; return; }
  const tics = [...new Set(f.map(x => x.tic))].sort((p, q) => p - q);
  const narrow = box.clientWidth < 560;
  const W = Math.max(280, box.clientWidth || 600), rh = narrow ? 34 : 26, pl = narrow ? 8 : 120, pr = 14, pt = 8, pb = 34;
  const H = pt + tics.length * rh + pb;
  const ts = f.map(x => x.t_center), lo = Math.min(...ts), hi = Math.max(...ts), pad = (hi - lo) * 0.03 || 1;
  const a = lo - pad, b = hi + pad;
  const X = t => pl + (t - a) / (b - a) * (W - pl - pr);
  const unit = f[0].time_unit || '';
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Timeline by star: ${f.length} feed entries on ${tics.length} stars, mid-time in ${unit}. The table above lists the same entries.`}, box);
  svg.style.height = H + 'px';
  tics.forEach((tic, i) => {
    const y = pt + i*rh + rh/2 + (narrow ? 6 : 0);
    el('line', {x1: pl, x2: W - pr, y1: y, y2: y, class: 'grid'}, svg);
    const n = f.filter(x => x.tic === tic).length;
    if (narrow) tx(svg, pl, y - 8, `TIC ${tic} · ${n}`, 'start');
    else tx(svg, pl - 8, y + 4, `TIC ${tic}`, 'end');
    for (const x of f.filter(x => x.tic === tic)){
      const isNew = x.status === 'new_candidate';
      const c = el('circle', {cx: X(x.t_center), cy: y, r: isNew ? 5 : 4, fill: isNew ? 'var(--fit)' : 'var(--panel)', stroke: isNew ? 'var(--fit)' : 'var(--muted)', 'stroke-width': 1.6}, svg);
      const t = el('title', {}, c); t.textContent = `TIC ${tic} · ${fmt(x.t_center,3)} ${unit} · ${D.status_label[x.status] || x.status} · ${D.unconfirmed}`;
    }
  });
  for (const t of niceTicks(a, b, narrow ? 3 : 6)){ if (t < a || t > b) continue; el('line', {x1: X(t), x2: X(t), y1: H - pb, y2: H - pb + 4, stroke: 'var(--muted)'}, svg); tx(svg, X(t), H - pb + 16, String(t), 'middle'); }
  tx(svg, W - pr, H - 4, `mid-time (${unit})`, 'end');
}
let discWidth = -1;
function renderDiscCharts(force){
  const box = $('#timeline');
  if (!force && box.clientWidth === discWidth) return;
  discWidth = box.clientWidth;
  const f = D.catalog.candidates;
  histogram($('#h-depth'), f.map(x => x.depth_ppm), 'Depth', 'ppm', D.feed_rule.max_depth_ppm);
  histogram($('#h-snr'), f.map(x => x.snr), 'SNR', 'SNR');
  histogram($('#h-period'), f.map(x => x.period_days), 'Period', 'days');
  timeline(box);
}
function renderDiscoveries(){ renderDiscHead(); renderDiscChips(); renderDiscTable(); renderDiscCharts(true); }

// ---------- planets ----------
function renderPlanets(){
  const cards = D.planets, MAX = D.ratio_scale_max;
  $('#planetcards').innerHTML = cards.length ? cards.map(s => {
    const rowHtml = e => `<div class="ratio">
      <div>${dipLink(e.id)} ${e.source === 'run' ? DIPTAG(e.outcome) : UNC}</div>
      <div class="muted" style="font-size:12px">${e.source === 'run' ? 'this run' : 'feed'} · ${esc(e.status)} · ${e.period_days ? 'P ' + fmt(e.period_days,3) + ' d' : 'no period'}${e.n_transits ? ' · ' + e.n_transits + ' transits' : ''}</div>
      ${e.ratio === null ? '<div class="formula">No positive stored depth, so no ratio.</div>' : `<div class="formula">Rp/R* = √depth = √(${fmt(e.depth_ppm,1)} ppm × 10⁻⁶) = <b>${fmt(e.ratio,4)}</b></div>
      <div class="scale" role="img" aria-label="Rp/R* ${fmt(e.ratio,4)} on a scale from 0 to ${fmt(MAX,2)}"><i style="width:${Math.min(100, e.ratio / MAX * 100).toFixed(2)}%"></i></div>
      <div class="scalecap" aria-hidden="true"><span>0</span><span>${e.ratio > MAX ? 'beyond ' : ''}${fmt(MAX,2)} max</span></div>`}
      ${e.archive_line ? `<div class="muted" style="font-size:12px">Archive comparison: ${esc(e.archive_line)}. ${esc(D.no_detection)}</div>` : ''}
    </div>`;
    const SHOW = 3, more = s.entries.slice(SHOW);
    const rows = s.entries.slice(0, SHOW).map(rowHtml).join('') + (more.length ? `<details class="ratio"><summary>Show ${more.length} more entr${more.length===1?'y':'ies'} for ${esc(s.star)}</summary>${more.map(rowHtml).join('')}</details>` : '');
    const ar = s.archive || {status: 'not_stored', planets: []};
    // Stars with no stored cross-match get no box; the section header says so once.
    let arch = '';
    if (ar.status === 'not_run') arch = `<p style="margin:0">The archive cross-match did not run. Stored error, verbatim: <code>${esc(ar.error || 'none stored')}</code>. ${esc(D.no_detection)}</p>`;
    else if (ar.status !== 'not_stored' && !ar.planets.length) arch = `<p style="margin:0">No published planet matched in the archive. ${esc(D.no_detection)}</p>`;
    else if (ar.status !== 'not_stored') arch = `<p style="margin:0"><b>Published planets.</b> ${esc(D.no_detection)}</p><ul>${ar.planets.map(p => `<li><b>${objLink('planet', p.pl_name)}</b> · host ${objLink('star', p.hostname)} · P ${p.pl_orbper !== null && p.pl_orbper !== undefined ? esc(p.pl_orbper) + ' d' : 'not listed'} · ${p.tran_flag ? 'transiting' : 'not known to transit'}${p.rv_flag ? ' · radial-velocity detection' : ''}</li>`).join('')}</ul><p class="muted" style="margin:4px 0 0;font-size:12px">${esc(ar.source)}, ${ar.fallback_from ? `recorded ${when(ar.fetched_at)}${ar.recorded_commit ? ` (commit ${esc(ar.recorded_commit)})` : ''} in ${esc(ar.fallback_from)}; this run's own cross-match ${ar.run_status === 'not_run' ? 'did not run' : 'is not stored'}${ar.run_error ? ` (stored error, verbatim: <code>${esc(ar.run_error)}</code>)` : ''}` : `fetched ${when(ar.fetched_at)}`}.</p>`;
    const hid = 'pl-' + String(s.star).replace(/\W/g,'_');
    return `<article class="card" aria-labelledby="${hid}"><h2 id="${hid}">${esc(s.star)}${(D.tic_names || {})[String(s.star).replace(/^TIC /, '')] ? ' · ' + objLink('star', D.tic_names[String(s.star).replace(/^TIC /, '')]) : ''} <span class="muted" style="font:500 11px var(--mono)">${esc(s.sources.join(' · '))} · ${s.entries.length} entr${s.entries.length===1?'y':'ies'}</span></h2>${rows}${arch ? `<div class="archive">${arch}</div>` : ''}</article>`;
  }).join('') : '<p class="empty">No stars in the run or the feed.</p>';
}

// ---------- panel ----------
function renderPanel(){
  renderCalibration(); calWidth = $('#calplane').clientWidth;
  const ag = D.agreement;
  $('#agreement').innerHTML = ag.length ? `<ul class="agree">${ag.map(a => `<li>
      <span>${dipLink(a.id)}<small class="muted" style="display:block;font-size:11px">${esc(a.target)} · ${esc(DIPPHRASE(a.outcome))}</small></span>
      <span><b>${a.n} of ${a.of} reviewers</b> marked it: ${a.n_claude} of ${plural(a.of_claude, 'Sentinel')}, ${a.n_sim} of ${plural(a.of_sim, 'Probe')}<small class="muted" style="display:block;font-size:11px">${a.reviewers.map(r => `<span title="reviewer id ${esc(r)}">${esc(NAME(r))}</span>`).join(', ') || 'none'}</small></span>
      <a href="${dipHref(a.id, 'ledger')}">Verdict ledger</a></li>`).join('')}</ul>` : '<p class="empty">The run stored no dips.</p>';
  $('#panelcards').innerHTML = D.panel.length ? D.panel.map(r => `<article class="card"><h2>${esc(NAME(r.id))} <span class="sub mono" title="reviewer id">${esc(r.id)}</span></h2>
    <p style="margin:6px 0 0">${kindTag(r.kind)}</p>
    <p class="muted" style="margin:6px 0 0;font-size:13px">${r.kind === 'simulated' ? 'A Probe: a deterministic matched-filter detector that marks dips above an SNR threshold in the light curve. It is not a person.' : isSentinel(r.kind) ? `A Sentinel: an AI model (${esc(PROV(r.id) || PROVIDER_OF(r.kind))}) that reads the plotted light curve and marks dips. It is not a person.${(D.reviewer_provenance[r.id] || {}).calibration === 'uncalibrated' ? ' <b>Uncalibrated:</b> it votes at the floor weight until it is calibrated on this provider and model.' : ''}` : ''}</p>
    <dl class="kv">
      <dt>weight in this run</dt><dd>${r.run_weight === null || r.run_weight === undefined ? 'not stored' : esc(r.run_weight)} <span class="muted">(manifest.json)</span></dd>
      <dt>calibrated weight</dt><dd>${r.calibrated_weight === null || r.calibrated_weight === undefined ? 'not in the weights file' : fmt(r.calibrated_weight,3)}${D.weights_path ? `<small class="muted" style="display:block;font-size:11px">${esc(D.weights_path)}</small>` : ''}</dd>
      <dt>marks</dt><dd>${r.n_marks} span${r.n_marks===1?'':'s'} on ${r.n_subjects} subject${r.n_subjects===1?'':'s'}</dd>
      <dt>labels</dt><dd>${Object.entries(r.labels).map(([k,v]) => `${esc(k.replace(/_/g,' '))} ${v}`).join(' · ') || 'none'}</dd>
      <dt>dips marked</dt><dd>${r.marked_dips.length} of ${D.dossier_ids.length}<div class="marks">${r.marked_dips.map(dipLink).join('') || '<span class="muted">none</span>'}</div></dd>
    </dl></article>`).join('') : '<p class="empty">The manifest lists no reviewers.</p>';
}

// ---------- calibration plane ----------
// x = false-alarm rate (FPR on empty subjects), y = recall (TPR on injected transits), point size =
// calibrated weight, with the lines of constant weight = TPR − FPR (floored). Stored values only.
const fmtN = p => (p.n_injected !== null && p.n_injected !== undefined) ? `${p.n_injected} injected, ${p.n_empty} empty` : 'sample size not stored';
function calSample(){
  const pts = D.calibration.points, cl = pts.filter(p => isSentinel(p.kind) && !p.uncalibrated), sim = pts.filter(p => p.kind === 'simulated');
  const sizes = list => [...new Set(list.map(fmtN))];
  const parts = [];
  // The scores themselves, in one line: the Sentinels' weights and the Probes' range.
  const range = list => { const w = list.map(p => p.weight).filter(x => x !== null && x !== undefined); if (!w.length) return 'not stored'; const lo = Math.min(...w), hi = Math.max(...w); return lo === hi ? fmt(lo,2) : `${fmt(lo,2)} to ${fmt(hi,2)}`; };
  if (cl.length || sim.length) parts.push(`Calibrated weights: ${cl.length ? `Sentinels ${range(cl)}` : ''}${cl.length && sim.length ? '; ' : ''}${sim.length ? `Probes ${range(sim)}` : ''}.`);
  if (cl.length) parts.push(`<b>The Sentinels were calibrated on ${esc(sizes(cl).join(' / '))} subjects only.</b>`);
  if (sim.length) parts.push(`The Probes (code, not people) on ${esc(sizes(sim).join(' / '))}.`);
  const n = Math.max(0, ...pts.map(p => p.n_injected || 0));
  if (n) parts.push(`With ${n} injected subjects a recall moves in steps of ${fmt(1 / n, 2)}, so one subject more or less changes a weight by that much. These weights are rough.`);
  return parts.join(' ');
}
function calPlane(box){
  box.innerHTML = '';
  const C = D.calibration, pts = C.points.filter(p => p.tpr !== null && p.tpr !== undefined && p.fpr !== null && p.fpr !== undefined);
  if (!C.points.length){ box.innerHTML = '<p class="empty">No weights file was given to this build.</p>'; return; }
  if (!pts.length){ box.innerHTML = '<p class="empty">The weights file stores no recall or false-alarm rates, so there is nothing to plot.</p>'; return; }
  // pad keeps a point at FPR 0 clear of the axis labels. Narrow drops the floor-region note and the rotated
  // weight labels: each weight is written level, above the right-hand end of its line, in a top band of its own.
  const W = Math.min(560, Math.max(260, box.clientWidth || 520)), narrow = W < 420, pl = 46, pr = 14, pt = narrow ? 40 : 12, pb = 42;
  const pad = 14, side = W - pl - pr - pad, H = pt + side + pb;
  const X = v => pl + pad + v * side, Y = v => pt + (1 - v) * side, R = w => 3 + 10 * Math.max(0, Number(w) || 0);
  const groups = [];
  for (const p of pts){ let g = groups.find(g => g.fpr === p.fpr && g.tpr === p.tpr && g.kind === (isSentinel(p.kind) ? 'claude' : p.kind)); if (!g){ g = {fpr: p.fpr, tpr: p.tpr, kind: isSentinel(p.kind) ? 'claude' : p.kind, items: []}; groups.push(g); } g.items.push(p); }
  const label = `Calibration plane: ${pts.length} reviewers by false-alarm rate and recall. ` + groups.map(g => `${g.items.map(p => NAME(p.id)).join(' and ')}: recall ${fmt(g.tpr,2)}, false-alarm rate ${fmt(g.fpr,2)}, weight ${fmt(g.items[0].weight,2)}`).join('; ') + '. ' + calSample().replace(/<[^>]+>/g, '');
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': label, class: 'calplane'}, box);
  svg.style.maxWidth = W + 'px';
  // The floor: below TPR − FPR = floor every reviewer gets the floor weight.
  const f = C.floor;
  el('polygon', {points: `${X(0) - pad},${Y(f)} ${X(0)},${Y(f)} ${X(1-f)},${Y(1)} ${X(1)},${Y(1)} ${X(1)},${Y(0)} ${X(0) - pad},${Y(0)}`, class: 'floor'}, svg);
  for (const t of [0, 0.2, 0.4, 0.6, 0.8, 1]){
    el('line', {x1: X(t), x2: X(t), y1: Y(0), y2: Y(0) + 4, stroke: 'var(--muted)'}, svg); tx(svg, X(t), Y(0) + 16, String(t), 'middle');
    el('line', {x1: X(0) - pad - 4, x2: X(0) - pad, y1: Y(t), y2: Y(t), stroke: 'var(--muted)'}, svg); tx(svg, X(0) - pad - 7, Y(t) + 4, String(t), 'end');
  }
  el('rect', {x: X(0) - pad, y: Y(1), width: side + pad, height: side, fill: 'none', stroke: 'var(--rule)'}, svg);
  tx(svg, X(0.5), H - 6, 'false-alarm rate (FPR, empty subjects)', 'middle', 'lbl');
  const yl = tx(svg, 12, Y(0.5), 'recall (TPR, injected transits)', 'middle', 'lbl'); yl.setAttribute('transform', `rotate(-90 12 ${Y(0.5)})`);
  // Lines of constant weight: TPR = FPR + w. Wide: labelled along the line. Narrow: the weight sits level above
  // the line's right-hand end (every line ends on the top edge), with one heading line above them.
  if (narrow){
    tx(svg, X(0) - pad, pt - 24, 'lines of weight:', 'start', 'isolbl');
    if (C.iso.includes(f)) tx(svg, X(1) + pr - 2, pt - 24, `${f} is the floor`, 'end', 'isolbl floorlbl');
  }
  for (const w of C.iso){
    el('line', {x1: X(0), y1: Y(w), x2: X(1 - w), y2: Y(1), class: w === f ? 'iso floorline' : 'iso'}, svg);
    if (narrow){
      el('line', {x1: X(1 - w), x2: X(1 - w), y1: Y(1) - 4, y2: Y(1), class: w === f ? 'iso floorline' : 'iso'}, svg);
      tx(svg, X(1 - w), pt - 7, String(w), 'middle', w === f ? 'isolbl floorlbl' : 'isolbl');
      continue;
    }
    const a = w === f ? 0.55 : 0.72, lx = X(a * (1 - w)), ly = Y(w + a * (1 - w));
    const t = tx(svg, lx, ly - 5, w === f ? `weight ${w} (floor)` : `weight ${w}`, 'middle', 'isolbl'); t.setAttribute('transform', `rotate(-45 ${lx} ${ly})`);
  }
  if (!narrow) tx(svg, X(0.97), Y(0.30), `below the floor line: weight ${f}`, 'end');
  // The sample size, on the plane.
  const cl = pts.filter(p => isSentinel(p.kind));
  if (cl.length) tx(svg, X(0.97), Y(0.08), `Sentinels: ${fmtN(cl[0])} only`, 'end', 'samplelbl');
  if (pts.some(p => p.kind === 'simulated')) tx(svg, X(0.97), Y(0.08) + 14, `Probes: ${fmtN(pts.find(p => p.kind === 'simulated'))}`, 'end');
  for (const g of groups){
    const r = R(g.items[0].weight), cx = X(g.fpr), cy = Y(g.tpr);
    const c = el('circle', {cx, cy, r, class: g.kind === 'claude' ? 'pt cl' : 'pt sim'}, svg);
    el('title', {}, c).textContent = g.items.map(p => `${NAME(p.id)} (id ${p.id}; ${p.kind === 'simulated' ? 'Probe, not a person' : isSentinel(p.kind) ? `Sentinel, ${PROVIDER_OF(p.kind)}` : p.kind}): TPR ${fmt(p.tpr,2)}, FPR ${fmt(p.fpr,2)}, weight ${fmt(p.weight,2)}, ${fmtN(p)}`).join('\n');
    const word = g.kind === 'claude' ? 'Sentinel' : g.kind === 'simulated' ? 'Probe' : g.kind;
    tx(svg, cx + r + 6, cy + 4, `${plural(g.items.length, word)} · w ${fmt(g.items[0].weight,2)}`, 'start', 'lbl');
  }
}
function renderCalibration(){
  const C = D.calibration;
  $('#calsample').innerHTML = C.points.some(p => p.n_injected) ? calSample() : 'The sample size is not stored with these weights.';
  calPlane($('#calplane'));
  const kindWord = k => k === 'simulated' ? 'Probe · not a person' : isSentinel(k) ? `Sentinel · ${esc(PROVIDER_OF(k))}` : esc(k);
  $('#caltable').innerHTML = C.points.length ? `<table><caption class="sr">Calibration rates and weights per reviewer, as stored</caption><thead><tr><th scope="col">reviewer</th><th scope="col">kind</th><th scope="col" class="num">recall (TPR)</th><th scope="col" class="num">false alarms (FPR)</th><th scope="col" class="num">weight</th><th scope="col">sample</th></tr></thead><tbody>${C.points.map(p => `<tr><th scope="row">${nameWithId(p.id)}</th><td>${kindWord(p.kind)}</td><td class="num">${fmt(p.tpr,2)}</td><td class="num">${fmt(p.fpr,2)}</td><td class="num">${p.uncalibrated ? `<b>uncalibrated</b><small>floor weight ${fmt(C.floor,2)} in a run</small>` : fmt(p.weight,2)}${p.consistent === false ? '<small>not max(TPR − FPR, floor)</small>' : ''}</td><td>${esc(fmtN(p))}</td></tr>`).join('')}</tbody></table>` : '';
  // On a phone the same rows read as one card per reviewer (the table is hidden there, the cards elsewhere).
  $('#calcards').innerHTML = C.points.map(p => `<dl class="kv calcard"><dt>reviewer</dt><dd><b>${nameWithId(p.id)}</b></dd><dt>kind</dt><dd>${kindWord(p.kind)}</dd><dt>recall (TPR)</dt><dd>${fmt(p.tpr,2)}</dd><dt>false alarms (FPR)</dt><dd>${fmt(p.fpr,2)}</dd><dt>weight</dt><dd>${p.uncalibrated ? `uncalibrated (floor weight ${fmt(C.floor,2)} in a run)` : fmt(p.weight,2)}${p.consistent === false ? ' (not max(TPR − FPR, floor))' : ''}</dd><dt>sample</dt><dd>${esc(fmtN(p))}</dd></dl>`).join('');
  $('#calsource').textContent = C.source ? `Rates: ${C.record_path || 'the weights file'}. ${C.source}` : (C.record_path ? `Rates: ${C.record_path}.` : '');
}
let calWidth = -1;
function resizeCalibration(){ const box = $('#calplane'); if (!box || $('#route-sentinels').hidden || box.clientWidth === calWidth) return; calWidth = box.clientWidth; calPlane(box); }

// ---------- runs ----------
function renderRuns(){
  const runs = D.catalog.runs.slice().reverse();
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  $('#runtable').innerHTML = runs.length ? `<ol class="runlines">${runs.map(x => { const ne = (x.errors||[]).length; return `<li>
      <div class="line"><b>${when(x.time)}</b><span>${plural((x.targets||[]).length, 'target')}</span><span>${esc(x.new ?? '–')} new</span><span>${esc(x.known ?? '–')} known TOI</span><span>${esc(x.filtered_deep ?? '–')} filtered as too deep</span><span>${esc(x.filtered_single ?? '–')} filtered for too few transits</span><span class="${ne ? 'err' : 'muted'}">${ne ? plural(ne, 'error') : 'no errors'}</span></div>
      ${ne ? x.errors.map(e => `<pre class="err">${esc(e)}</pre>`).join('') : ''}
      ${(x.targets||[]).length ? `<details><summary>Targets</summary><p class="mono" style="margin:4px 0 0;font-size:12px">${(x.targets||[]).map(t => 'TIC ' + esc(t)).join(', ')}</p></details>` : ''}
      ${(x.tracebacks||[]).length ? `<details><summary>${plural(x.tracebacks.length, 'traceback')} (verbatim)</summary>${x.tracebacks.map(t => `<pre class="err">${esc(t)}</pre>`).join('')}</details>` : ''}</li>`; }).join('')}</ol>` : '<p class="empty">No search runs are stored in the catalogue.</p>';
  const c = D.config;
  const pk = Object.entries(c.packages || {});
  $('#runconfig').innerHTML = `<dl class="kv">
    <dt>config name</dt><dd>${esc(c.config_name)}</dd>
    <dt>config hash (sha256)</dt><dd>${esc(c.config_sha256)}</dd>
    <dt>created</dt><dd>${when(D.run.created_at)}</dd>
    <dt>SetuHQ</dt><dd>${esc(c.setuhq_version)}</dd>
    <dt>python</dt><dd>${esc(c.python)}</dd>
    <dt>platform</dt><dd>${esc(c.platform)}</dd>
    <dt>Sentinel prompt version</dt><dd>${esc(c.claude_prompt_version || 'not stored')}</dd>
    <dt>Sentinel providers</dt><dd>${Object.entries(D.reviewer_provenance || {}).map(([id, p]) => `${esc(NAME(id))}: ${esc(p.provider_label)} · ${esc(p.model)} · ${esc(p.calibration || 'calibration not stored')}`).join('<br>') || 'none in this run'}</dd>
    <dt>subject length</dt><dd>${esc(c.subject_days)} d</dd>
    <dt>skipped reviewers</dt><dd>${(c.skipped_reviewers_detail||[]).length ? c.skipped_reviewers_detail.map(s => `${esc(s.id)} (${esc(s.reason || 'unavailable')})`).join(', ') : (c.skipped_reviewers||[]).length ? esc(c.skipped_reviewers.join(', ')) : 'none'}</dd>
    <dt>archive cross-match</dt><dd>${xmConfig(D.crossmatch_info)}</dd>
    ${pk.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
  </dl>
  <h3 style="margin-top:14px">Measured inputs</h3>
  ${(c.inputs||[]).map(x => `<p style="margin:4px 0 0" class="mono">${esc(Object.entries(x).map(([k,v]) => k + ' ' + v).join(' · '))}</p>`).join('') || '<p class="empty">No inputs stored.</p>'}`;
  $('#catconfig').innerHTML = D.catalog.path ? `<dl class="kv"><dt>catalogue</dt><dd>${esc(D.catalog.path)}</dd><dt>config</dt><dd>${esc(D.catalog.config)}</dd><dt>config hash (sha256)</dt><dd>${esc(D.catalog.config_sha256)}</dd><dt>updated</dt><dd>${when(D.catalog.updated)}</dd><dt>targets reviewed</dt><dd>${esc(D.catalog.targets_reviewed)}</dd></dl>` : '<p class="empty">No search catalogue was given to this build.</p>';
}

// The archive cross-match this page was built from: the file, and when it is the repository's fallback,
// what the run's own cross-match stored (its status and its error, verbatim).
function xmConfig(x){
  if (!x) return 'not stored';
  if (x.fallback) return `${esc(x.file)} (fallback; run's own: ${esc(x.run_status || 'not stored')}${x.run_error ? ', ' + esc(x.run_error) : ''})`;
  if (x.status === 'not_run') return `not run (${esc(x.error || 'no error stored')})`;
  return `${esc(x.file)} (${esc(x.status)})`;
}


// ---------- the five sections' figures (Sky, Transit, Explorer, Sentinels) ----------
// Stored values only: the points are the run's stored flux, the marks the reviewers' stored spans,
// the scores, flags, rationales and confidences as stored. Decorative art is labelled as such.
const S = D.story;
// DIPS: the lead run's dips (the sky map and the panel read them); ALL_DIPS adds every other example run's.
const DIPS = S.dips, ALL_DIPS = DIPS.concat(D.showcase_dips || []), DIP_BY = Object.fromEntries(ALL_DIPS.map(d => [d.id, d]));
const CTX = d => (D.run_ctx || {})[d.run] || {star: S.star, planet: S.planet, lead: D.hero.lead};
const STC = {known: 'var(--blue)', open: 'var(--yellow)', rejected: 'var(--red)'};
const STC_SPACE = S.colours;  // the same colours as hex, for the space panels (dark in both themes)
const fmtSigned = (x, d) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d);
const dotPath = (pts, X, Y) => pts.map(p => `M${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}h0`).join('');
const transitHref = id => rtUrl('transit', {dip: id});
const tval = x => fmt(x, 2);
// The y range of a dip's window: from its depth and the scatter of its stored points outside the window.
function dipRange(list){
  let depth = 0, noise = 0;
  for (const d of list){
    depth = Math.max(depth, d.depth_ppm || 0);
    const out = d.pts.filter(p => p[0] < d.t_start - d.t || p[0] > d.t_end - d.t).map(p => p[1]);
    if (out.length > 3){ const m = out.reduce((a, b) => a + b, 0) / out.length; noise = Math.max(noise, Math.sqrt(out.reduce((a, b) => a + (b - m) * (b - m), 0) / out.length)); }
  }
  const D0 = Math.max(depth, 3 * noise, 80);
  return [-1.9 * D0, 1.1 * D0];
}

// ---------- Sky ----------
const sky = {known: true, open: true, rejected: true, rev: 'all'};
const REV_FILTERS = [['all', 'All'], ['sentinels', 'Sentinels'], ['probes', 'Probes only'], ['split', 'Split']];
function revOk(d){
  const w = d.who;
  if (sky.rev === 'sentinels') return w.sentinels > 0;
  if (sky.rev === 'probes') return w.sentinels === 0 && w.probes > 0;
  if (sky.rev === 'split') return (w.sentinels + w.probes) < (w.of_sentinels + w.of_probes);
  return true;
}
const skyShown = d => sky[d.status] && revOk(d);
// The Sky's filters live in the URL (#/sky?status=known,open&who=probes), like the Feed's sort: a viewer's
// change is a new history entry, a link opens the same view, and anything malformed falls back to the default.
const SKY_STATUS = ['known', 'open', 'rejected'], SKY_WHO = ['all', 'sentinels', 'probes', 'split'];
function decodeSkyView(params){
  const st = params.get('status'), who = params.get('who');
  let on = SKY_STATUS.slice();
  if (st === 'none') on = [];
  else if (st !== null){ const want = st.split(','); const ok = SKY_STATUS.filter(k => want.includes(k)); if (ok.length) on = ok; }
  return {status: on, who: SKY_WHO.includes(who) ? who : 'all'};
}
const encodeSkyView = v => `status=${v.status.length ? SKY_STATUS.filter(k => v.status.includes(k)).join(',') : 'none'}&who=${v.who}`;
const currentSky = () => ({status: SKY_STATUS.filter(k => sky[k]), who: sky.rev});
function applySky(v){ for (const k of SKY_STATUS) sky[k] = v.status.includes(k); sky.rev = v.who; }
// Survey-coverage layers on the sky map, kept in the URL as layers=... beside the filters.
const COVL = ((D.galaxy_meta && D.galaxy_meta.layers) || []).concat(D.sweep && D.sweep.n_sky ? ['sweep'] : []);
let skyLayers = [];
const decodeLayers = p => { const ls = (p.get('layers') || '').split(','); return COVL.filter(k => ls.includes(k)); };
function applySkyLayers(ls){
  skyLayers = ls;
  $$('#route-sky .covl').forEach(g => { g.style.display = ls.includes(g.dataset.layer) ? '' : 'none'; });
  $$('#skycov [data-cov]').forEach(b => b.setAttribute('aria-pressed', String(ls.includes(b.dataset.cov))));
}
function syncSkyURL(push){ if (current === 'sky') setHash('#/sky?' + encodeSkyView(currentSky()) + (skyLayers.length ? '&layers=' + skyLayers.join(',') : ''), !!push); }
if ($('#skycov')) $('#skycov').addEventListener('click', e => {
  const b = e.target.closest('button[data-cov]'); if (!b) return;
  const k = b.dataset.cov, on = skyLayers.includes(k);
  applySkyLayers(COVL.filter(x => x === k ? !on : skyLayers.includes(x))); syncSkyURL(true);
});
function renderSky(){
  const n = k => S.counts[k];
  // The zoom into the run star's system needs its stored example; without one the button stays hidden.
  $$('#route-sky [data-zoom]').forEach(el => { if (!(MX && MX.examples[el.dataset.zoom])) return; el.hidden = false; el.classList.add('on'); });
  $('#skychips').innerHTML = [['known', S.planet ? S.planet : 'Known'], ['open', 'Open'], ['rejected', 'Rejected']].map(([k, l]) =>
    `<button type="button" class="pill" data-st="${k}" aria-pressed="${sky[k]}" style="--c:${STC[k]}"><i></i>${esc(l)} <span class="n">${n(k)}</span></button>`).join('');
  $('#skyrev').innerHTML = REV_FILTERS.map(([k, l]) => `<button type="button" data-rev="${k}" aria-pressed="${sky.rev === k}">${esc(l)}</button>`).join('');
  const shown = DIPS.filter(skyShown);
  $('#skycount').textContent = `${shown.length} of ${DIPS.length}`;
  $('#skydips').innerHTML = shown.length ? shown.map(d => `<a class="dipitem" href="${transitHref(d.id)}" style="--c:${STC[d.status]}"><i></i><b>${esc(d.time_unit)} ${tval(d.t)}</b><span class="st">${esc(d.status_label)}</span><span class="sub">${fmt(d.depth_ppm, 0)} ppm · ${fmt(d.duration_hours, 2)} h · ${d.who.sentinels === d.who.of_sentinels && d.who.probes === d.who.of_probes ? `all ${d.who.of_sentinels + d.who.of_probes} reviewers` : `${d.who.probes} Probes, ${d.who.sentinels} Sentinels`} · ${esc(DIPPHRASE(d.outcome))}</span></a>`).join('')
    : '<p class="empty" style="margin:12px">No dips match.</p>';
  skyTimeline();
}
function skyTimeline(box = $('#skytimeline'), capEl = $('#skytlcap'), read = $('#skytlread')){
  if (!box) return;
  const subs = D.hero.subjects; if (!subs.length){ box.innerHTML = '<p class="empty">No light curve is stored.</p>'; return; }
  const a = subs[0].start, b = subs[subs.length - 1].end, W = 1000, H = 84;
  const [lo, hi] = [-700, 400], X = t => (t - a) / (b - a) * W, Y = v => 6 + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * 56;
  const pts = subs.map(s => s.t.map((t, i) => `M${X(t).toFixed(1)} ${Y(s.ppm[i]).toFixed(1)}h0`).join('')).join('');
  let ticks = '';
  for (const d of DIPS){ const on = skyShown(d), x = X(d.t).toFixed(1); ticks += `<path d="M${x} 66 V82" stroke="${on ? STC[d.status] : 'var(--line-2)'}" stroke-width="${on ? 2.5 : 1.5}" stroke-linecap="round"><title>${esc(d.time_unit)} ${tval(d.t)} · ${esc(d.status_label)}</title></path>`; }
  capEl.innerHTML = `<span>${esc(D.hero.time_unit)} ${fmt(a, 1)}</span><span>Stored brightness over the run, ${D.hero.n_points.toLocaleString('en-GB')} points; ticks: the dips shown above</span><span>${fmt(b, 1)}</span>`;
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Light curve of run ${esc(D.run.name)}: ${D.hero.n_points} stored points from ${esc(D.hero.time_unit)} ${fmt(a, 1)} to ${fmt(b, 1)}, with ${DIPS.filter(skyShown).length} of ${DIPS.length} dips ticked."><path d="${pts}" stroke="var(--ink)" stroke-width="1.1" stroke-linecap="round" opacity=".45"/>${ticks}</svg>`;
  // S06: the curve answers on hover and on the arrow keys, one stored point at a time (every 4th, for the keys).
  const xs = [], ys = [];
  if (read && window.SetuUI && SetuUI.crosshair){
    subs.forEach(s => s.t.forEach((t, i) => { if (i % 4 === 0){ xs.push(t); ys.push(s.ppm[i]); } }));
    SetuUI.crosshair(box.querySelector('svg'), {x0: a, x1: b, xs, readout: read, fmt: i => `${D.hero.time_unit} ${fmt(xs[i], 2)} · ${ys[i] < 0 ? '−' : '+'}${fmt(Math.abs(ys[i]), 0)} ppm`});
  }
}
// Zoom from the run star's marker into its system view (a magnifier; an illustration of scale).
function skyZoom(name, back){
  const m = $('#route-sky .skymark .skydot'), r = m ? m.getBoundingClientRect() : back.getBoundingClientRect();
  mxOpenSystem(name, back, {x: r.left + r.width / 2, y: r.top + r.height / 2, kind: 'sky'});
}
$('#route-sky').addEventListener('click', e => {
  const z = e.target.closest('.on[data-zoom]'); if (z){ skyZoom(z.dataset.zoom, z.tagName === 'BUTTON' ? z : $('#route-sky .skyzoom') || z); return; }
  const s = e.target.closest('button[data-st]'), r = e.target.closest('button[data-rev]');
  if (s){ sky[s.dataset.st] = !sky[s.dataset.st]; syncSkyURL(true); renderSky(); $(`#skychips button[data-st="${s.dataset.st}"]`).focus(); say(`${DIPS.filter(skyShown).length} of ${DIPS.length} dips shown.`); }
  if (r){ sky.rev = r.dataset.rev; syncSkyURL(true); renderSky(); $(`#skyrev button[data-rev="${r.dataset.rev}"]`).focus(); say(`${DIPS.filter(skyShown).length} of ${DIPS.length} dips shown.`); }
});

// ---------- Transit (the per-dip cockpit) ----------
const txs = {dip: null, cmp: []};
// The transit, played back with the shared system view: the star from the catalogue (blackbody colour from its
// Teff, limb darkening), the planet crossing it, a limb-darkened model curve, and this dip's stored points and its
// stored limb-darkened fit.
// A dip matched to a known planet uses that planet's stored radii and orbit; any other dip shows what a planet
// as deep as the stored depth would cast, with the orbit and the impact parameter illustrative (b = 0).
function txTheatre(d){
  const known = d.status === 'known', k = d.ratio || 0, C = CTX(d), planet = C.planet;
  let starNote = 'the star is the target as the catalogue stores it', k2 = k;
  const star = typeof MX !== 'undefined' && MX && planet ? MX.examples[planet] || null : null;
  const model = (d.model || []).map(p => [p[0], p[1]]);
  let p, bNote;
  if (known && star){ p = Object.assign({name: planet}, star); bNote = `impact parameter ${star.impact_parameter != null ? 'as stored' : 'illustrative'}`; }
  else {
    // This dip's own shape: the stored fit's Rp/R★, b and limb darkening when a fit is stored, else Rp/R★ = √depth and
    // b = 0. The star is the run's own (its TIC Teff and radius as the run stored them); the period is illustrative.
    // The fit is the signal's joint fit, shared by all of its dips; where it stores a mid-time and a T14, the model is
    // drawn there (its own t0, its own duration), so it lies on the dashed stored fit.
    const SP = C.star_params || {}, kk = d.fit_k || k, fitted = !!d.fit_k, timed = fitted && d.fit_dt0 != null && !!d.fit_t14_hours;
    const teff = (star && star.star_teff) || SP.teff || null, rs = (star && star.star_radius) || SP.radius || null;
    const P = (!wrongP(d) && d.period_days) || (C.lead && !wrongP(d) && C.lead.period_days) || 6;
    const bb = fitted && d.fit_b != null ? d.fit_b : 0, chord = Math.sqrt(Math.max(1e-4, (1 + kk) ** 2 - bb * bb));
    const T14 = Math.max(0.02, (d.fit_t14_hours || d.duration_hours || 2) / 24), ars = P / (Math.PI * T14) * chord;
    p = {name: 'a planet this deep', star_teff: teff, star_radius: rs || 1, radius: kk * (rs || 1) * 6.957e8 / 7.1492e7,
      orbital_period: P, semi_major_axis: ars * (rs || 1) * 6.957e8 / 1.495978707e11,
      impact_parameter: bb, ld: fitted ? d.fit_ld : null, t0_offset_days: timed ? d.fit_dt0 : 0,
      look: 'silhouette'};  // a candidate is drawn as a silhouette at Rp/R★, never as planet art
    bNote = timed ? 'Rp/R★, b, limb darkening, mid-time and T14 from the signal\'s stored fit'
      : fitted ? 'Rp/R★, b and limb darkening from the signal\'s stored fit; only its depth is the fit\'s, the mid-time and duration are illustrative'
      : 'impact parameter illustrative (b = 0), not fitted';
    starNote = teff ? `the star: ${Math.round(teff).toLocaleString('en-GB')} K${rs ? ', ' + fmt(rs, 2) + ' R☉' : ''} (${SP.source || 'as stored'})` : 'the star\'s temperature is not stored (drawn at the Sun\'s)';
    k2 = kk;
  }
  $('#txcap').textContent = known && star ? `${planet}, from stored values` : 'what a planet this deep would cast';
  $('#txfoot').textContent = (known && star
      ? `${planet} and its star as ${MX.source} stores them (fetched ${MX.fetched_at.slice(0, 10)}): the line is a limb-darkened model from those values, not a fit to this dip; ${bNote}. The match says the planet is already known; it does not confirm the dip.`
      : `If it were a planet: Rp/R★ = ${d.fit_k ? fmt(k2, 4) + ' from the signal\'s stored fit' : '√depth = ' + fmt(k2, 4) + ', from the stored depth ' + fmt(d.depth_ppm, 0) + ' ppm'}; ${starNote}; orbit and period illustrative; ${bNote}.`)
    + ` Dots: the ${d.pts.length} stored flux values within ${fmt(d.half * 24, 1)} hours of mid-time (${esc(d.time_unit)} ${fmt(d.t, 3)}). ${model.length ? 'Dashed: the signal\'s stored limb-darkened fit, at this dip.' : 'No transit fit is stored for this dip.'} The star's surface texture is decorative.`;
  const {st, S: SS} = mxSystemView($('#txsysfig'), p, {dip: {pts: d.pts, model}, on: current === 'transit', caption: false});
  if (!(known && star)){ st.opt.sys.bSrc = d.fit_k ? 'stored fit' : 'illustrative'; mxKick(st); }
  // What the drawing shows, for the tests: the star's temperature and the model's depth at mid-transit (ppm).
  const fig = $('#txsysfig'), [lu1, lu2] = SS.ld || mxLd(SS.teff);
  fig.dataset.teff = String(Math.round(SS.teff)); fig.dataset.modelDepthPpm = String(Math.round((1 - mxFlux(SS.b, SS.k, lu1, lu2)) * 1e6));
  // The canonical pages for the planet (when the dip matches one) and the star.
  $('#txlinks').innerHTML = (known && planet && C.planet_page !== false ? objLink('planet', planet, planet + ' ›') : '') + (C.star && C.star.name && C.star_page !== false ? objLink('star', C.star.name, C.star.name + ' ›') : '');
}
function lanesHTML(d){
  const pct = v => Math.max(0, Math.min(100, (v + d.half) / (2 * d.half) * 100));
  const w0 = pct(d.t_start - d.t), w1 = pct(d.t_end - d.t);
  return `<span class="small">Who marked it · stored spans in this window; dashed outline: the consensus window</span>` + d.lanes.map(l => {
    const c = l.role === 'sentinel' ? 'var(--sen)' : 'var(--prb)';
    const spans = l.spans.map(([a, b]) => `<i class="${l.counted ? '' : 'uncounted'}" style="left:${pct(a).toFixed(1)}%;width:${Math.max(1.5, pct(b) - pct(a)).toFixed(1)}%"></i>`).join('');
    return `<div class="lane" style="--c:${c}"><span style="color:${l.role === 'sentinel' ? 'var(--sen)' : 'var(--prb-ink)'}" title="reviewer id ${esc(l.id)}">${esc(l.name)}</span><div class="track" role="img" aria-label="${esc(l.name)}: ${l.spans.length ? `${l.spans.length} span${l.spans.length === 1 ? '' : 's'} in this window, ${l.counted ? 'counted for this dip' : 'not counted'}` : 'no mark in this window'}"><span class="win" style="left:${w0.toFixed(1)}%;width:${Math.max(.5, w1 - w0).toFixed(1)}%"></span>${spans || '<em>no mark</em>'}</div></div>`;
  }).join('');
}
function quoteHTML(d){
  const q = d.quotes[0];
  if (!q && CTX(d).probes_only) return `<div class="quote"><p style="font-size:14px">${esc(D.probes_only_label)}: the Probes marked this run, and no Sentinel was in its configuration, so no Sentinel's words are stored.</p></div>`;
  if (!q) return `<div class="quote"><p style="font-size:14px">No Sentinel rationale is stored for this subject.</p></div>`;
  return `<div class="quote"><div class="who"><b title="reviewer id ${esc(q.id)}">${esc(q.name)}</b><span>${q.confidence === null || q.confidence === undefined ? 'confidence not stored' : 'confidence ' + fmt(q.confidence, 1)}</span></div>
    <p>“${esc(q.text)}”</p><small>Its stored rationale for subject ${esc(d.subject_label || d.subject)} (${esc(d.time_unit)} ${fmt(d.subject_start, 1)} to ${fmt(d.subject_end, 1)}), one per subject, not per dip. It ${q.marked ? 'marked' : 'did not mark'} this dip. A Sentinel is an AI model${PROV(q.id || '') ? ` (${esc(PROV(q.id))})` : ''}, not a person.</small></div>`;
}
// A dip whose stored BLS period is known not to be its planet's (docs/results/showcase.json): no period is drawn for it.
const wrongP = d => (CTX(d).period_wrong || []).includes(d.id);
function orbitHTML(d){
  const C = CTX(d), L = C.lead; if (!L || d.phase === null || d.phase === undefined) return '';
  if (wrongP(d) || (C.period_wrong || []).includes(L.dip)) return '';
  const ang = Math.PI / 2 + d.phase * 2 * Math.PI, px = 100 + 80 * Math.cos(ang), py = 100 + 80 * Math.sin(ang);
  const who = C.planet ? `${esc(C.planet)}'s orbit` : "the lead signal's orbit";
  const near = Math.abs(d.phase) < 0.02;
  return `<figure class="glass orbitfig"><svg viewBox="0 0 200 200" role="img" aria-label="Orbit seen from above, with this dip at phase ${fmtSigned(d.phase, 2)} of the lead signal; the transit point faces us (bottom).">
      <circle cx="100" cy="100" r="80" fill="none" stroke="var(--line-2)" stroke-width=".8"/>
      <line x1="100" y1="100" x2="100" y2="196" stroke="var(--line-2)" stroke-dasharray="2 4"/>
      <circle cx="100" cy="100" r="10" fill="var(--star)"/>
      <g class="orbitfast" style="transform-origin:100px 100px"><circle cx="100" cy="20" r="4" fill="var(--ink)"/></g>
      <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="6" fill="none" stroke="${STC[d.status]}" stroke-width="1.6"/>
    </svg><figcaption><b>Where this dip sits on ${who}.</b><br>Phase ${fmtSigned(d.phase, 2)} on the lead signal's stored BLS period (${fmt(L.period_days, 3)} d), t0 ${fmt(L.t0, 3)}. ${near ? 'At the transit point, facing us.' : 'Not at the transit point, so it is not a transit of that signal.'} The orbit is drawn to show phase only; not to scale.</figcaption></figure>`;
}
function trayHTML(){
  if (!txs.cmp.length) return '';
  const list = txs.cmp.map(id => DIP_BY[id]).filter(Boolean), [lo, hi] = dipRange(list), half = Math.max(...list.map(d => d.half));
  const W = 300, H = 100, X = dt => (dt + half) / (2 * half) * W, Y = v => 6 + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * (H - 12);
  return `<div class="glass tray"><div class="cap"><span>Compare · same scale (±${fmt(half * 24, 1)} h, ${fmt(lo, 0)} to ${fmt(hi, 0)} ppm)</span><button type="button" class="btn" id="cmpclear">Clear</button></div><div class="grid">${list.map(d => {
    const model = (d.model || []).length ? d.model.map((p, i) => `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}`).join('') : '';
    return `<a href="${transitHref(d.id)}" aria-current="${d.id === txs.dip}" style="--c:${STC_SPACE[d.status]}"><span class="h"><span style="color:#F5F5F7">${esc(d.time_unit)} ${tval(d.t)}</span><span>${esc(d.planet || d.status)}</span></span><svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><path d="${dotPath(d.pts, X, Y)}" stroke="#F5F5F7" stroke-width="2.4" stroke-linecap="round" opacity=".8"/><path d="${model}" stroke="${STC_SPACE[d.status]}" stroke-width="1.2" fill="none"/></svg></a>`; }).join('')}</div></div>`;
}
function renderTransit(){
  const d = DIP_BY[txs.dip] || DIP_BY[S.lead_dip]; if (!d) return;
  txs.dip = d.id;
  // The chips, Previous and Next stay within the dip's own run (its star).
  const RD = ALL_DIPS.filter(x => x.run === d.run), i = RD.indexOf(d), prev = RD[(i + RD.length - 1) % RD.length], next = RD[(i + 1) % RD.length], inCmp = txs.cmp.includes(d.id);
  $('#txkicker').textContent = d.status_label; $('#txkicker').style.color = STC[d.status];
  $('#h-transit').textContent = DIP_NAME(d.id) || `dip ${d.letter}`;
  $('#txsub').textContent = `${d.time_unit} ${tval(d.t)} · ${fmt(d.depth_ppm, 0)} ppm · ${fmt(d.duration_hours, 2)} hours · SNR ${fmt(d.snr, 1)} · ${DIPPHRASE(d.outcome)}`;
  $('#txcapword').textContent = d.outcome === 'rejected' ? 'The dip, played back' : 'The transit, played back';
  $('#txnav').innerHTML = `<a class="roundbtn" href="${transitHref(prev.id)}" aria-label="Previous dip, ${esc(prev.time_unit)} ${tval(prev.t)}">‹</a><a class="roundbtn" href="${transitHref(next.id)}" aria-label="Next dip, ${esc(next.time_unit)} ${tval(next.t)}">›</a><button type="button" class="cmpbtn" id="cmptoggle" aria-pressed="${inCmp}">${inCmp ? 'In compare' : 'Add to compare'}</button>`;
  $('#txchips').innerHTML = RD.map(x => `<a href="${transitHref(x.id)}" aria-current="${x.id === d.id}" style="--c:${STC[x.status]}" title="${esc(x.id)} · ${esc(x.status_label)}"><i></i>${esc(x.letter)} · ${tval(x.t)}</a>`).join('');
  // Keep the current dip's chip in view in the sideways-scrolling row (without moving the page).
  const row = $('#txchips'), chip = $('#txchips a[aria-current="true"]');
  if (row && chip) row.scrollLeft = chip.offsetLeft - (row.clientWidth - chip.offsetWidth) / 2;
  txTheatre(d);
  $('#txscore').innerHTML = `<div class="top"><span>Panel score (weighted share that marked it)</span><b>${fmt(d.score, 2)}</b></div><div class="bar" style="--c:${STC[d.status]}"><i style="width:${Math.round((d.score || 0) * 100)}%"></i></div><p>${esc(d.verdict)}</p>`;
  $('#txlanes').innerHTML = lanesHTML(d);
  $('#txquote').innerHTML = quoteHTML(d);
  $('#txorbit').innerHTML = orbitHTML(d) + trayHTML();
  $('#txcase').innerHTML = `<a class="btn primary" href="${esc(dipHref(d.id))}">Open the full case file ›</a><span>Every check, the stored measurements, the verdict ledger and the archive provenance.</span>`;
  $('#txarchive').textContent = d.archive_line ? `Archive comparison: ${d.archive_line}. ${D.no_detection}` : '';
  const cv = CTX(d).caveat; $('#txcaveat').hidden = !cv; $('#txcaveat').textContent = cv ? `What this run did not recover: ${cv}` + (wrongP(d) ? ' This dip\'s stored BLS period is not its planet\'s, so no period is given for it.' : '') : '';
}
function openTransit(dip){
  const n = $('#txnotice');
  if (dip && !DIP_BY[dip]){
    // An unknown dip id: say so, and rewrite the address to the lead dip (replace, not a new entry).
    n.textContent = `No dip ${dip} in run ${D.run.name}; showing the lead dip ${S.lead_dip}.`; n.hidden = false; say(n.textContent);
    dip = S.lead_dip; setHash(transitHref(dip), false);
  } else n.hidden = true;
  txs.dip = dip || txs.dip || S.lead_dip;
  if (!dip) setHash(transitHref(txs.dip), false);
  renderTransit();
}
function txSysShown(on){ const fig = $('#txsysfig'); if (fig && fig._mx){ fig._mx.on = on; if (on) mxKick(fig._mx); } }
$('#route-transit').addEventListener('click', e => {
  if (e.target.closest('#cmptoggle')){ const k = txs.cmp.indexOf(txs.dip); if (k >= 0) txs.cmp.splice(k, 1); else txs.cmp.push(txs.dip); renderTransit(); $('#cmptoggle').focus(); say(k >= 0 ? 'Removed from compare.' : 'Added to compare.'); }
  if (e.target.closest('#cmpclear')){ txs.cmp = []; renderTransit(); $('#cmptoggle').focus(); say('Compare cleared.'); }
});

// ---------- Explorer (the feed scatter) ----------
const EXF = S.explorer, STAR_COL = ['#FF9F0A', '#0A84FF', '#BF5AF2', '#30D158', '#FF375F', '#64D2FF'];
const TICS = [...new Set(EXF.map(f => f.tic))];
const ex = {stars: Object.fromEntries(TICS.map(t => [t, true])), fNew: true, fKnown: true, snrMin: 0, sel: EXF.length ? EXF[0].i : null};
const starColour = tic => STAR_COL[TICS.indexOf(tic) % STAR_COL.length];
const exShown = f => ex.stars[f.tic] && (f.status === 'new_candidate' ? ex.fNew : ex.fKnown) && (f.snr || 0) >= ex.snrMin;
// The Explorer's filters live in the URL beside the Feed table's sort and filter:
// #/explorer?sort=snr&filter=all&stars=all&snr=8&new=1&known=1 (stars: all, none or a list of TIC ids).
const EX_SNR = [0, 7, 8, 9, 10];
function decodeExView(params){
  const st = params.get('stars'), snr = Number(params.get('snr'));
  let stars = TICS.map(String);
  if (st === 'none') stars = [];
  else if (st !== null && st !== 'all'){ const want = st.split(','); const ok = TICS.map(String).filter(t => want.includes(t)); if (ok.length) stars = ok; }
  return {stars, snr: EX_SNR.includes(snr) ? snr : 0, new: params.get('new') !== '0', known: params.get('known') !== '0'};
}
// Parameters equal to their defaults are left out (all stars, any SNR, both statuses), so a plain
// #/explorer stays plain; decodeExView still reads them, so older, longer links keep working.
function encodeExView(v){
  const all = TICS.map(String), on = all.filter(t => v.stars.includes(t)), out = [];
  if (on.length !== all.length) out.push(`stars=${on.length ? on.join(',') : 'none'}`);
  if (v.snr) out.push(`snr=${v.snr}`);
  if (!v.new) out.push('new=0');
  if (!v.known) out.push('known=0');
  return out.join('&');
}
const currentEx = () => ({stars: TICS.map(String).filter(t => ex.stars[t]), snr: ex.snrMin, new: ex.fNew, known: ex.fKnown});
function applyEx(v){ for (const t of TICS) ex.stars[t] = v.stars.includes(String(t)); ex.snrMin = v.snr; ex.fNew = v.new; ex.fKnown = v.known; }
function renderExplorer(){
  if (!EXF.length){ $('#exscatter').innerHTML = '<p class="empty">No search catalogue was given to this build.</p>'; return; }
  const nNew = EXF.filter(f => f.status === 'new_candidate').length, nKnown = EXF.length - nNew;
  $('#exstars').innerHTML = TICS.map(t => `<button type="button" class="pill" data-tic="${t}" aria-pressed="${ex.stars[t]}" style="--c:${starColour(t)}"><i></i>TIC ${esc(t)}</button>`).join('');
  $('#exstatus').innerHTML = `<button type="button" data-f="fNew" aria-pressed="${ex.fNew}">New ${nNew}</button><button type="button" data-f="fKnown" aria-pressed="${ex.fKnown}">Known TOI ${nKnown}</button>`;
  const snrs = [0, 7, 8, 9, 10].filter(v => v === 0 || EXF.some(f => f.snr >= v));
  $('#exsnr').innerHTML = snrs.map(v => `<button type="button" data-snr="${v}" aria-pressed="${ex.snrMin === v}">${v ? 'SNR ' + v + '+' : 'Any SNR'}</button>`).join('');
  const shown = EXF.filter(exShown);
  $('#excount').textContent = `${shown.length} of ${EXF.length} shown`;
  // Fewer than three distinct periods make an almost empty plot: a compact table says the same, readably.
  // Distinct periods: values within 2 per cent of each other are one period (one signal's repeat transits).
  const periods = []; for (const p of shown.map(f => f.period_days || 0).sort((a, b) => a - b)) if (!periods.length || p > periods[periods.length - 1] * 1.02) periods.push(p);
  const box = $('#exscatter'), compact = periods.length < 3;
  box.classList.toggle('astable', compact);
  $('#h-scatter').textContent = compact ? `Entries by star and period (${periods.length} period${periods.length === 1 ? '' : 's'}: too few for a plot)` : 'Depth against period (period on a log scale)';
  $('#exfoot').hidden = compact;
  if (compact){
    const groups = []; for (const f of shown){ const k = f.tic + '|' + periods.findIndex(p => Math.abs((f.period_days || 0) - p) <= p * 0.02 + 1e-9); let g = groups.find(x => x.k === k); if (!g){ g = {k, f, list: []}; groups.push(g); } g.list.push(f); }
    const rng = (a, d) => { const lo = Math.min(...a), hi = Math.max(...a); return lo === hi ? fmt(lo, d) : `${fmt(lo, d)}–${fmt(hi, d)}`; };
    box.innerHTML = groups.length ? `<table class="excompact"><thead><tr><th scope="col">Star</th><th scope="col" class="num">Period (d)</th><th scope="col" class="num">Entries</th><th scope="col" class="num">Depth (ppm)</th><th scope="col" class="num">SNR</th><th scope="col">Status</th></tr></thead><tbody>${groups.map(g => `<tr><th scope="row"><button type="button" data-i="${g.list[0].i}" aria-pressed="${g.list.some(f => f.i === ex.sel)}" style="--c:${g.f.status === 'new_candidate' ? '#FFD60A' : starColour(g.f.tic)}"><i></i>TIC ${esc(g.f.tic)}</button></th><td class="num">${fmt(g.f.period_days, 3)}</td><td class="num">${g.list.length}</td><td class="num">${rng(g.list.map(f => f.depth_ppm), 0)}</td><td class="num">${rng(g.list.map(f => f.snr), 1)}</td><td>${esc(D.status_label[g.f.status] || g.f.status)}</td></tr>`).join('')}</tbody></table>`
      : '<p class="empty">No entry matches these filters.</p>';
    renderExSel(); return;
  }
  const per = shown.map(f => f.period_days).filter(p => p > 0), dep = shown.map(f => f.depth_ppm).filter(x => x > 0);
  // Log axis: the range widened to whole 1-2-5 steps, with a tick at each.
  const steps = []; for (let k = -2; k <= 4; k++) for (const m of [1, 1.5, 2, 3, 5, 7]) steps.push(m * Math.pow(10, k));
  const p0 = steps.filter(v => v <= Math.min(...per) / 1.1).pop() || 0.01, p1 = steps.find(v => v >= Math.max(...per) * 1.1) || 1e4;
  const dticks = niceTicks(0, Math.max(...dep) * 1.1, 4), d1 = dticks[dticks.length - 1] >= Math.max(...dep) ? dticks[dticks.length - 1] : Math.max(...dep) * 1.1;
  const X = p => (Math.log(p) - Math.log(p0)) / (Math.log(p1) - Math.log(p0)) * 100, Yp = dp => (1 - dp / d1) * 100;
  const pticks = steps.filter(p => p >= p0 && p <= p1);
  const grid = pticks.map(p => `M${X(p).toFixed(2)} 0V52`).join('') + dticks.map(v => `M0 ${(Yp(v) * .52).toFixed(2)}H100`).join('');
  box.innerHTML = `<svg viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true"><path d="${grid}" stroke="rgba(255,255,255,.07)" stroke-width="1" vector-effect="non-scaling-stroke"/></svg>`
    + shown.map(f => { const s = Math.round(7 + Math.max(0, (f.snr || 7) - 7) * 1.4), c = f.status === 'new_candidate' ? '#FFD60A' : starColour(f.tic);
      return `<button type="button" data-i="${f.i}" aria-pressed="${f.i === ex.sel}" aria-label="TIC ${esc(f.tic)}, period ${fmt(f.period_days, 3)} days, depth ${fmt(f.depth_ppm, 0)} ppm, SNR ${fmt(f.snr, 1)}, ${esc(D.status_label[f.status] || f.status)}, ${esc(D.unconfirmed)}" style="left:${X(f.period_days).toFixed(2)}%;top:${Yp(f.depth_ppm).toFixed(2)}%;--s:${s}px;--c:${c};--g:${Math.round(Math.max(0, (f.snr || 6) - 6) * 2)}px"><i></i></button>`; }).join('')
    + pticks.map(p => `<span class="ax" style="left:${X(p).toFixed(1)}%;bottom:-18px;transform:translateX(-50%)">${+p.toPrecision(3)}${p === pticks[pticks.length - 1] ? ' d' : ''}</span>`).join('')
    + dticks.map(v => `<span class="ax" style="left:2px;top:calc(${Yp(v).toFixed(1)}% - 14px)">${v.toLocaleString('en-GB')}${v === dticks[dticks.length - 1] ? ' ppm' : ''}</span>`).join('');
  renderExSel();
}
function renderExSel(){
  const f = EXF.find(x => x.i === ex.sel); if (!f){ $('#exsel').innerHTML = '<p class="empty">Pick a signal.</p>'; return; }
  const k = f.depth_ppm > 0 ? Math.sqrt(f.depth_ppm * 1e-6) : 0, isNew = f.status === 'new_candidate', c = isNew ? 'var(--yellow)' : 'var(--blue)';
  $('#exsel').innerHTML = `<p class="st" style="--c:${c}">${isNew ? 'New candidate · unconfirmed' : 'At a known TOI period · ' + esc(D.unconfirmed)}</p><h2>${ticLink(f.tic)}</h2>
    <svg viewBox="-110 -110 220 220" role="img" aria-label="Sketch: a star and a planet disc to scale from the stored depth (Rp/R* ${fmt(k, 4)}); the orbit is not to scale."><defs><radialGradient id="exs" cx="40%" cy="35%" r="70%"><stop offset="0" stop-color="#FFF4DA"/><stop offset=".7" stop-color="#FFC46B"/><stop offset="1" stop-color="#C2620F"/></radialGradient></defs>
      <circle r="100" fill="none" stroke="var(--line-2)" stroke-width=".8"/><circle r="46" fill="url(#exs)"/>
      <g class="orbit" style="transform-origin:0 0"><circle cx="100" cy="0" r="${Math.max(1.2, 46 * k).toFixed(2)}" fill="var(--ink)"/><circle cx="100" cy="0" r="10" fill="none" stroke="var(--line-3)" stroke-width=".8"/></g></svg>
    <p class="small" style="text-align:center">Planet disc to scale from depth: Rp/R* ${fmt(k, 4)} · orbit not to scale · no stellar radius stored</p>
    <dl class="statgrid"><div><dt>Period</dt><dd>${fmt(f.period_days, 3)} d</dd></div><div><dt>Depth</dt><dd>${fmt(f.depth_ppm, 0)} ppm</dd></div><div><dt>Duration</dt><dd>${fmt(f.duration_hours, 2)} h</dd></div><div><dt>SNR</dt><dd>${fmt(f.snr, 1)}</dd></div></dl>
    <p class="small">TESS sectors ${esc(f.sectors || 'not stored')}. Feed ${esc(entryNo(f.id))} for this star (stored id <span class="mono">${esc(f.id)}</span>). ${isNew ? '' : 'A TOI match compares a stored period with archive values. '}${esc(D.no_detection)}</p>`;
}
const _cap = s => s.charAt(0).toUpperCase() + s.slice(1);
$('#route-explorer').addEventListener('click', e => {
  const t = e.target.closest('#exstars button[data-tic]'), f = e.target.closest('#exstatus button[data-f]'), n = e.target.closest('button[data-snr]'), p = e.target.closest('#exscatter button[data-i]');
  if (t){ ex.stars[t.dataset.tic] = !ex.stars[t.dataset.tic]; syncFeedURL(true); renderExplorer(); $(`#exstars button[data-tic="${t.dataset.tic}"]`).focus(); say($('#excount').textContent); }
  else if (f){ ex[f.dataset.f] = !ex[f.dataset.f]; syncFeedURL(true); renderExplorer(); $(`#exstatus button[data-f="${f.dataset.f}"]`).focus(); say($('#excount').textContent); }
  else if (n){ ex.snrMin = +n.dataset.snr; syncFeedURL(true); renderExplorer(); $(`#exsnr button[data-snr="${n.dataset.snr}"]`).focus(); say($('#excount').textContent); }
  else if (p){ ex.sel = +p.dataset.i; for (const b of $$('#exscatter button[data-i]')) b.setAttribute('aria-pressed', String(+b.dataset.i === ex.sel)); renderExSel(); }
});

// ---------- Sentinels (the panel) ----------
const sen = {filter: 'all', sel: S.reviewers.length ? S.reviewers[0].id : null};
function renderSentinels(){
  const R = S.reviewers, probes = R.filter(r => r.role === 'probe'), sents = R.filter(r => r.role === 'sentinel');
  const ring = (list, rad, cls, col) => list.map((r, i) => { const a = (-90 + i * 360 / list.length) * Math.PI / 180, x = 180 + rad * Math.cos(a), y = 180 + rad * Math.sin(a), s = 4 + 14 * (r.weight || 0);
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${s.toFixed(1)}" fill="${col}"><title>${esc(r.name)} (id ${esc(r.id)}): weight ${fmt(r.weight, 2)}</title></circle>`; }).join('');
  $('#senring').innerHTML = `<svg viewBox="0 0 360 360" role="img" aria-label="The panel as an orbital diagram: ${probes.length} Probes on the inner ring and ${sents.length} Sentinels on the outer ring, each sized by its calibrated weight (${R.map(r => `${r.name} ${fmt(r.weight, 2)}`).join(', ')}).">
      <circle cx="180" cy="180" r="18" fill="#FFB340"/><circle cx="180" cy="180" r="80" fill="none" stroke="rgba(191,90,242,.35)" stroke-width=".8"/><circle cx="180" cy="180" r="150" fill="none" stroke="rgba(100,210,255,.35)" stroke-width=".8"/>
      <g class="orbit" style="transform-origin:180px 180px">${ring(probes, 80, 'p', '#BF5AF2')}</g>
      <g class="orbitslow" style="transform-origin:180px 180px">${ring(sents, 150, 's', '#64D2FF')}</g></svg>
    <figcaption>Inner ring: Probes. Outer ring: Sentinels. Size is calibrated weight. The motion is decorative.</figcaption>`;
  $('#senfilter').innerHTML = [['all', 'All'], ['sentinel', 'Sentinels'], ['probe', 'Probes']].map(([k, l]) => `<button type="button" data-sf="${k}" aria-pressed="${sen.filter === k}">${l}</button>`).join('');
  $('#sencards').innerHTML = R.filter(r => sen.filter === 'all' || r.role === sen.filter).map(r => {
    const c = r.role === 'sentinel' ? 'var(--sen)' : 'var(--prb-ink)', n = r.n_injected || 0;
    const sq = Array.from({length: n}, (_, q) => `<i class="${q < (r.hits || 0) ? 'on' : ''}"></i>`).join('');
    return `<button type="button" class="revcard" data-rev="${esc(r.id)}" aria-pressed="${sen.sel === r.id}" style="--c:${c}"><span><span class="nm">${esc(r.name)}</span><span class="kd">${r.role === 'sentinel' ? 'Sentinel, runs on Claude (Anthropic)' : 'Probe, deterministic matched filter'} · <span class="mono">${esc(r.id)}</span></span></span><span class="w" title="calibrated weight">${fmt(r.weight, 2)}</span>
      <span class="hits" role="img" aria-label="${r.hits ?? '–'} hits in ${n} planted transits; ${r.false_alarms ?? '–'} false alarms in ${r.n_empty ?? '–'} empty light curves">${sq}</span><span class="hitcap">${r.hits ?? '–'} of ${n} planted transits found · ${r.false_alarms ?? '–'} of ${r.n_empty ?? '–'} empty light curves marked</span></button>`; }).join('');
  const r = R.find(x => x.id === sen.sel) || R[0];
  if (r) $('#senmarked').innerHTML = `<span class="small">${esc(r.name)}: what it marked in this run (counted for the dip)</span><div class="grid">${DIPS.map(d => { const on = r.marked.includes(d.id);
    return `<a href="${transitHref(d.id)}" class="${on ? 'on' : ''}" style="--c:${on ? (r.role === 'sentinel' ? 'var(--sen)' : 'var(--prb-ink)') : 'var(--ink-3)'}"><b>${esc(d.letter)} · ${tval(d.t)}</b><span>${on ? 'marked' : 'no mark'}</span></a>`; }).join('')}</div>`;
}
$('#route-sentinels').addEventListener('click', e => {
  const f = e.target.closest('button[data-sf]'), c = e.target.closest('button.revcard');
  if (f){ sen.filter = f.dataset.sf; renderSentinels(); $(`#senfilter button[data-sf="${f.dataset.sf}"]`).focus(); }
  else if (c){ sen.sel = c.dataset.rev; renderSentinels(); $(`#sencards button[data-rev="${c.dataset.rev}"]`).focus(); }
});

// ---------- router ----------
const RENDER = {overview: () => {}, sky: renderSky, galaxy: renderGalaxy, methods: renderMethods, mission: renderMission, catalogue: renderCatalogue, planet: () => {}, star: () => {}, variables: renderVariables, transit: renderTransit,
  explorer: () => { renderExplorer(); renderDiscoveries(); }, sentinels: () => { renderSentinels(); renderPanel(); }, candidates: renderCandidates, planets: renderPlanets, runs: renderRuns,
  leaderboard: () => {}, docs: () => {}, pictures: () => {}, notfound: () => {}};
const rendered = new Set();
const META = D.route_meta, MX_FIRST = Object.keys(D.chapter_titles)[0];
const ROUTES = () => $$('#content > .route').map(s => s.dataset.route);
// The page the address names: a clean path, its query (a deep link's view), and for a case file the section in its hash.
function parseLoc(){
  const p = rtParse(location.pathname, location.search) || {route: document.body.dataset.page === 'notfound' ? 'notfound' : (document.body.dataset.page || 'overview'), params: {}};
  if (!$('#route-' + p.route)) p.route = 'notfound';
  // A dip address the run does not hold is not found: never another dip in its place. One the run once held says so.
  let gone = '';
  if ((p.route === 'transit' || p.route === 'candidates') && p.params.dip && !((D.routes.dips || {})[p.params.dip])){
    gone = (D.routes.gone || []).includes(p.params.dip) ? p.params.dip : ''; p.route = 'notfound';
  }
  nfSay(gone);
  const params = new URLSearchParams(p.params);
  if (p.route === 'candidates' && location.hash.length > 1 && !params.has('section')) params.set('section', location.hash.slice(1));
  return {route: p.route, params};
}
// The not-found page, or "this dip is no longer in the run" for an address a dip once had (D.routes.gone).
function nfSay(gone){
  const h = $('#h-notfound'), p = h && h.closest('header').querySelector('p'); if (!h || !p) return;
  if (!h.dataset.plain) { h.dataset.plain = h.textContent; p.dataset.plain = p.textContent; }
  h.textContent = gone ? 'This dip is no longer in the run.' : h.dataset.plain;
  p.innerHTML = gone ? `The address /candidates/${esc(gone)}/ belonged to a dip that a later version of the run no longer holds. Its number is not given to another dip. <a href="${esc(rtUrl('explorer'))}">See the dips the run holds now ›</a>` : esc(p.dataset.plain);
}
let current = null;
// The header follows the page: the section it belongs to, its breadcrumbs (deep pages only), its sub-navigation and title.
function pageChrome(r, params){
  const m = META[r] || {}, h1 = $('#route-' + r + ' h1');
  $$('.nav a[data-nav], .menu a[data-nav]').forEach(a => { if (a.dataset.nav === m.nav) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const win = r === 'candidates' ? (D.dips || {})[params.get('dip')] : null;
  const name = r === 'methods' ? (D.chapter_titles[params.get('ch')] || m.label) : win ? win.label : (r === 'planet' || r === 'star' || r === 'transit') && h1 ? h1.textContent.trim() : m.label;
  document.title = m.title_tpl ? m.title_tpl.replace('{name}', name) : `${m.label} · SetuHQ`;
  const crumbs = $('#crumbs');
  if (crumbs){
    const chain = (m.crumbs || []).map(([label, href]) => `<li><a href="${esc(href)}">${esc(label)}</a></li>`);
    if (r === 'methods' && params.get('ch') && params.get('ch') !== MX_FIRST) chain.push(`<li><a href="${esc(rtUrl('methods'))}">How it works</a></li>`);
    if (r === 'candidates' && params.get('dip')) chain.push(`<li><a href="${esc(transitHref(params.get('dip')))}">${esc(DIP_NAME(params.get('dip')) || params.get('dip'))}</a></li>`);
    crumbs.hidden = !chain.length;
    crumbs.innerHTML = chain.length ? `<ol>${chain.join('')}<li aria-current="page">${esc(r === 'candidates' ? 'Case file' : name)}</li></ol>` : '';
  }
  const sub = $('#subnav');
  if (sub){
    const items = (D.subnav[m.nav] || []);
    sub.hidden = !items.length;
    sub.innerHTML = items.map(([label, route, routes]) => `<a href="${esc(R(route))}"${routes.includes(r) ? ' aria-current="page"' : ''}>${esc(label)}</a>`).join('');
  }
  const cv = $('#copyview'); if (cv) cv.hidden = !VIEW_QUERY[r];
}
function show(r, moveFocus, params){
  for (const id of ROUTES()) $('#route-' + id).hidden = id !== r;
  document.body.dataset.route = r;
  if (!rendered.has(r)){ RENDER[r](); rendered.add(r); }
  else if (r === 'explorer'){ renderOverview(); renderDiscCharts(false); }
  if (r === 'explorer' && !rendered.has('widgets')){ renderOverview(); rendered.add('widgets'); }
  if (moveFocus){ const h = $('#route-' + r + ' h1'); if (h) h.focus({preventScroll: true}); window.scrollTo(0, 0); }
  if (r === 'candidates') fitFrame();
  missionShown(r === 'mission');
  gxShown(gxWanted());
  mxShown(r === 'methods');
  mxIntroRoute(r);
  txSysShown(r === 'transit');
  plShown(r);
  // The shared renderer upgrades the view's pictures; the header settles; counters roll (setuhq.design, setuhq.renderer).
  const sec = $('#route-' + r);
  if (window.SetuRender && sec) SetuRender.mount(sec);
  if (window.SetuUI){ SetuUI.settle(); SetuUI.odometer(sec); }
}
// A change of view in place is a view transition (V13), except under reduced motion or on the first draw.
function viewTransition(f){
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches || document.hidden) return f();
  try { const t = document.startViewTransition(f); [t.ready, t.finished, t.updateCallbackDone].forEach(q => q && q.catch(() => {})); }
  catch (e) { f(); }
}
function go(p, moveFocus){
  // A new page moves focus to its heading; a new chapter keeps focus where it is (the Learn bar, the contents) and scrolls up.
  const changed = p.route !== current || ['planet', 'star', 'transit'].includes(p.route);
  if (p.route === 'methods' && current === 'methods' && moveFocus) window.scrollTo(0, 0);
  if (p.route === 'explorer'){
    if (p.params.has('layout')){
      layout = decodeLayout(p.params.get('layout'), WIDGET_IDS, D.default_size);
      sharedView = encodeLayout(layout) !== encodeLayout(ownLayout);
    } else if (p.route !== current){ layout = ownLayout.map(x => ({...x})); sharedView = false; }
  }
  if (p.route === 'sky'){
    applySky(decodeSkyView(p.params));
    applySkyLayers(decodeLayers(p.params));
    if (rendered.has('sky')) renderSky();
  }
  if (p.route === 'galaxy' && GXM) applyGalaxy(decodeGalaxyView(p.params));
  if (p.route === 'catalogue' && CTM) applyCatalogue(decodeCatView(p.params));
  if (p.route === 'variables' && VA) applyVariables(decodeVarView(p.params));
  if (p.route === 'explorer'){
    const beforeEx = encodeExView(currentEx());
    applyEx(decodeExView(p.params));
    if (rendered.has('explorer') && beforeEx !== encodeExView(currentEx())) renderExplorer();
    const fromURL = ['sort', 'dir', 'filter'].some(k => p.params.has(k));
    const before = currentFeedView();
    applyFeedView(fromURL ? decodeFeedView(p.params) : ownFeedView);
    if (rendered.has('explorer') && encodeFeedView(before) !== encodeFeedView(currentFeedView())){ renderDiscChips(); renderDiscTable(); }
  }
  current = p.route;
  show(p.route, moveFocus && changed, p.params);
  if (p.route === 'methods') mxShowChapter(p.params.get('ch'));
  if (p.route === 'planet') plShow(p.params.get('id') || '');
  if (p.route === 'star') stShow(p.params.get('id') || '');
  if (p.route === 'mission'){ applyMission(decodeMission(p.params)); gxShown(gxWanted()); }
  learnVisit(p);
  if (p.route === 'transit') openTransit(p.params.get('dip'));
  if (p.route === 'candidates') openDip(p.params.get('dip'), p.params.get('section'));
  if (p.route === 'explorer') $('#sharednote').hidden = !sharedView;
  pageChrome(p.route, p.params);
}
// In-app links: a click on a link to another page of the app changes the page in place (History API), so the
// header, the loaded data and the theme stay; the address is the page's own, and Back and Forward work as usual.
document.addEventListener('click', e => {
  const a = e.target.closest('a[href]');
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target || a.hasAttribute('download')) return;
  let u; try { u = new URL(a.getAttribute('href').startsWith('#/') ? R(a.getAttribute('href')) : a.href, location.href); } catch (err) { return; }
  if (u.origin !== location.origin) return;
  if (u.pathname === location.pathname && u.search === location.search && u.hash && current !== 'candidates') return;  // an anchor on this page
  const p = rtParse(u.pathname, u.search);
  if (!p || !$('#route-' + p.route)) return;  // a page outside the app (the report, the plates): a normal load
  e.preventDefault();
  navTo(u.href);
});
// Open an address: in place when it is a page of the app, else by a normal load.
function navTo(href){
  const u = new URL(R(href), location.href), p = u.origin === location.origin ? rtParse(u.pathname, u.search) : null;
  const gsd = $('#gsearch'); if (gsd && gsd.open) gsd.close();
  closeMenu();
  if (!p || !$('#route-' + p.route)){ location.href = u.href; return; }
  try { history.pushState(null, '', u.pathname + u.search + u.hash); } catch (err) { location.href = u.href; return; }
  viewTransition(() => go(parseLoc(), true));
}
// Back and Forward change the view at once (a page restored from the back-forward cache must not wait on a transition).
window.addEventListener('popstate', () => { const gsd = $('#gsearch'); if (gsd && gsd.open) gsd.close(); closeMenu(); go(parseLoc(), true); });
$('.skip').addEventListener('click', e => { e.preventDefault(); const c = $('#content'); c.focus({preventScroll: true}); c.scrollIntoView(); });
// ---------- "Copy link to this view": the one way view settings reach an address ----------
const VIEW_QUERY = {
  explorer: () => [layoutIsDefault() ? '' : 'layout=' + encodeLayout(layout), encodeFeedView(currentFeedView()) === encodeFeedView(D.feed_view.default) ? '' : encodeFeedView(currentFeedView()), encodeExView(currentEx())].filter(Boolean).join('&'),
  sky: () => encodeSkyView(currentSky()) + (skyLayers.length ? '&layers=' + skyLayers.join(',') : ''),
  galaxy: () => (typeof gx !== 'undefined' && gx.view) ? encodeGalaxyView(gx.view) : '',
  catalogue: () => (typeof ct !== 'undefined' && ct.view) ? encodeCatView(ct.view) : '',
  variables: () => (typeof va !== 'undefined' && va.view) ? encodeVarView(va.view) : '',
};
function layoutIsDefault(){ return encodeLayout(layout) === encodeLayout(normaliseLayout(null, WIDGET_IDS, D.default_size)); }
function viewLink(r){ const q = (VIEW_QUERY[r] || (() => ''))(); return location.origin + location.pathname + (q ? '?' + q : ''); }
async function copyViewLink(r, state, box){
  const url = viewLink(r);
  try { await navigator.clipboard.writeText(url); if (box) box.hidden = true; say('Link to this view copied.'); if (state) state.textContent = 'Link copied.'; }
  catch (e) { if (box){ box.hidden = false; box.value = url; box.focus(); box.select(); } say('Copy the selected link to share this view.'); if (state) state.textContent = box ? '' : url; }
  if (state) setTimeout(() => { state.textContent = ''; }, 4000);
}
document.addEventListener('click', e => { if (e.target.closest('[data-open-search]')) gsOpen(); });
if ($('#copyview')) $('#copyview').addEventListener('click', () => copyViewLink(current, $('#copyviewstate'), $('#copyviewbox')));
// The sticky top bar's height sets --top, which the case file's frame uses.
function measureTop(){ const t = $('.topbar'); if (t) document.documentElement.style.setProperty('--top', Math.ceil(t.getBoundingClientRect().height) + 'px'); }
measureTop();
if (window.ResizeObserver) new ResizeObserver(measureTop).observe($('.topbar'));
let rt = null;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if ($('#route-explorer') && !$('#route-explorer').hidden) renderDiscCharts(false); resizeCalibration(); fitFrame(); }, 120); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { measureTop(); fitFrame(); });  // web fonts can rewrap the header
try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', theme: currentTheme()}, '*'); } catch (e) { /* no frame yet */ }
document.addEventListener('setuhq-theme', e => { try { $('#docketframe').contentWindow.postMessage({source: 'setuhq-shell', theme: e.detail}, '*'); } catch (err) { /* no frame yet */ } });
$('#dippick').addEventListener('change', e => navTo(dipHref(e.target.value)));
// An old in-app address (#/galaxy?focus=x), typed, bookmarked or followed, lands on its page.
function fromOldHash(){ if (!location.hash.startsWith('#/')) return false; setAddress(rtFromHash(location.hash, true), false); return true; }
window.addEventListener('hashchange', () => { if (fromOldHash()) go(parseLoc(), true); });
fromOldHash();
go(parseLoc(), false);
"""
# The Galaxy section's code sits ahead of the router, which calls it.
APP_JS = APP_JS.replace("// ---------- router ----------\n", GALAXY_JS + METHODS_JS + CATALOGUE_JS + VARIABLES_JS + LEARN_JS + MISSION_JS + VIZ_JS + "// ---------- router ----------\n", 1)


def _eyebrow(label: str, parent: tuple[str, str] | None = None) -> str:
    """Nothing: the page's place in the site is shown once, by the breadcrumbs under the top bar (deep pages only)."""
    return ""


# The benchmark on the current code: the re-run after the two fixes. The first run (pre-fix code) stays in
# docs/results/benchmark_real_tois.json as the historical record.
BENCHMARK_JSON = "docs/results/benchmark_real_tois_clipfix.json"


def _load_benchmark(path: str | Path = BENCHMARK_JSON) -> dict | None:
    """The real-TOI benchmark's summary (scripts/benchmark_real_tois.py), without the per-star rows."""
    if not Path(path).exists():
        return None
    d = json.loads(Path(path).read_text())
    keep = ("edition", "generated_at", "sample", "panel", "stars_run", "summary", "sentinels", "feed_implication", "clipping", "code_provenance", "feed_rule")
    out = {k: d[k] for k in keep if k in d}
    if d.get("against_first_run"):
        af = d["against_first_run"]
        out["first_run"] = {"completeness": af["rows"][0]["first"], "clipping": af.get("clipping")}
    if d.get("summary_unaffected"):
        out["unaffected_held_out"] = {k: d["summary_unaffected"]["held_out"].get(k) for k in ("completeness", "fp_seen", "fp_flagged_of_seen")}
    return out


def _benchmark_card(b: dict | None) -> str:
    """The Sentinels page's statement of measured performance: on a stated benchmark, never as discoveries."""
    e = html.escape
    if not b:
        return ('<section class="card bench" aria-labelledby="h-bench"><h2 id="h-bench">Measured on real TOIs</h2>'
                '<p class="muted">The blind benchmark on real TESS Objects of Interest has not been run for this build '
                '(scripts/benchmark_real_tois.py).</p></section>')
    h, s = b["summary"]["held_out"], b["sample"]

    def pct(r):
        if not r or r.get("rate") is None:
            return "—"
        return f"{100 * r['rate']:.0f}% <span class='muted'>({r['k']}/{r['n']}; 95% CI {100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)</span>"

    ns = h.get("not_searchable") or {}
    clipfix = b.get("edition") == "clipfix"
    rows = [("Headline: planets recovered on searchable stars (CP/KP TOIs, a vetted dip on the published ephemeris)", pct(h["completeness"])),
            ("Planets recovered over all CP/KP stars (no 2-minute data counts as missed)", pct(h.get("completeness_all_stars"))),
            ("Planets recovered in the first run, on the pre-fix code (the historical record)", pct((b.get("first_run") or {}).get("completeness")))
            if clipfix else
            ("Planets recovered, stars exposed to the clipping bug excluded", pct((b.get("unaffected_held_out") or {}).get("completeness"))),
            ("Not searchable (no SPOC 2-minute light curve)", f"{sum(ns.values())} stars <span class='muted'>({ns.get('positive', 0)} CP/KP, {ns.get('fp', 0)} FP, {ns.get('fa', 0)} FA)</span>"
             + (" <b>skewed toward FP</b>: the FP rows describe FP stars with 2-minute data only" if ns.get("fp", 0) > 2 * max(1, ns.get("positive", 0)) else "")),
            ("False-positive TOIs found by the panel", pct(h["fp_seen"])),
            ("… of those, rejected or flagged binary-like", pct(h["fp_flagged_of_seen"]))]
    feed = h.get("feed")
    for v in ("inverted", "scrambled"):
        c = h["controls"][v]
        if feed and feed[v]["new_signals_per_1000"] is not None:
            rows.append((f"False alarms on {v} light curves at the feed's level (its full rule, FAP < 0.01)",
                         f"{feed[v]['new_signals_per_1000']:.0f} per 1,000 star-sectors <span class='muted'>({feed[v]['new_signals']} over {feed[v]['star_sectors']}; "
                         f"{c['vetted_false_alarms']} vetted dips before the feed's rule)</span>"))
        elif c["per_1000_star_sectors"] is not None:
            rows.append((f"False alarms on {v} light curves (vetted dips)", f"{c['per_1000_star_sectors']:.0f} per 1,000 star-sectors <span class='muted'>({c['vetted_false_alarms']} over {c['star_sectors']})</span>"))
    se = b.get("sentinels")
    if se:
        for rid, v in se["personas"].items():
            rows.append((f"{rid}: CP/KP dips marked (subsample of {se['n_stars']} stars)", pct(v["cp_kp_marked"])))
    body = "".join(f"<tr><th scope='row'>{e(k)}</th><td>{v}</td></tr>" for k, v in rows)
    imp = b.get("feed_implication")
    fr = (b.get("feed_rule") or {})
    frv = fr.get("validation")
    if frv:
        n, o, live = frv["held_out"], frv["held_out_old_rule"], fr.get("live")
        verdict_rule = (
            (f'<p class="note" style="margin:0"><b>The feed&#x27;s stricter rule, pre-registered and measured again on this code.</b> '
             if fr.get("edition") == "clipfix" else
             f'<p class="note" style="margin:0"><b>Update {e(frv["evaluated_at"][:10])}: a stricter feed rule, pre-registered and tested once.</b> ')
            + f'The signal must now pass in both reviewed sectors with a FAP below {frv["rule"]["fap_cut"]:g} over {frv["rule"]["fap_trials"]:,} trials. '
            f'On the held-out half, noise alone gives {n["expected_false_per_100_targets"]:.1f} false signals per 100 targets '
            f'(95% CI {n["expected_false_ci_per_100_targets"][0]:.1f}–{n["expected_false_ci_per_100_targets"][1]:.1f}), down from '
            f'{o["expected_false_per_100_targets"]:.1f} ({o["expected_false_ci_per_100_targets"][0]:.1f}–{o["expected_false_ci_per_100_targets"][1]:.1f}). '
            f'That is still far above the {n["real_new_per_100_targets"]:.1f} new signals per 100 targets the real light curves give, so the feed '
            f'is still dominated by false alarms, and feed-level completeness fell from {100 * o["completeness"]["rate"]:.0f}% to '
            f'{100 * n["completeness"]["rate"]:.0f}%. A feed admission is a lead for human or follow-up review, not a candidate of any confirmed status.'
            + ((f' Re-run on this code, the live feed&#x27;s {live["targets"]} targets admit {live["new_signals"]} new signals.'
                if fr.get("edition") == "clipfix" else
                f' Re-run under the new rule, {live["new_signals"]} of the live feed&#x27;s {live["old_new_signals"]} earlier new signals survive.') if live else "")
            + '</p>')
    else:
        verdict_rule = ""
    clip = (b.get("clipping") or {}).get("held_out")
    clipnote = ""
    fclip = (b.get("first_run") or {}).get("clipping")
    if clip and clipfix and fclip:
        a = clip["affected"]
        clipnote = (f'<p class="note" style="margin:0"><b>The clipping bug is fixed in the code that measured this.</b> {a["positive"]} CP/KP, '
                    f'{a["fp"]} FP and {a["fa"]} FA held-out stars were exposed (depth over {b["clipping"]["ratio"]:g}× the scatter); '
                    f'{fclip["now_recovered"]} of the {fclip["n"]} exposed CP/KP are recovered now, against {fclip["first_recovered"]} in the '
                    f'first run.</p>')
    elif clip:
        a = clip["affected"]
        clipnote = (f'<p class="note" style="margin:0"><b>Known bug in the code that measured this.</b> The cleaning step deletes points '
                    f'more than 10× the scatter below the running median, so very deep transits and eclipses lose their in-transit points. '
                    f'{a["positive"]} CP/KP, {a["fp"]} FP and {a["fa"]} FA held-out stars are exposed (depth over {b["clipping"]["ratio"]:g}× the scatter); '
                    f'{clip["cp_kp_misses_explained"]} of their CP/KP misses are explained by it. A fix is coming; only those stars will be re-run.</p>')
    verdict = ""
    if imp:
        verdict = (f'<p class="note" style="margin:0"><b>{"The live feed&#x27;s new signals are consistent with noise." if imp["bad"] else "What this means for the feed."}</b> '
                   f'Noise alone should give about {imp["expected_false_per_100_targets"]:.1f} false new_candidate signals per 100 targets reviewed'
                   + (f', against {imp["live_new_signals_per_100_targets"]:.1f} per 100 on the live feed' if imp.get("live_new_signals_per_100_targets") is not None else "")
                   + (('. Under that earlier rule a new_candidate on the feed was more likely noise than a signal.' if (b.get("feed_rule") or {}).get("validation")
                       else '. A new_candidate on the feed is more likely noise than a signal. Proposed fix, not yet applied: require the signal '
                            'in each of the two sectors reviewed and a stricter FAP, chosen on the tuning half and checked once on the held-out half.')
                      if imp["bad"] else '. False alarms alone account for less than half of that rate.') + '</p>')
    return (f'<section class="card bench" aria-labelledby="h-bench" style="display:grid;gap:8px"><h2 id="h-bench">Measured on real TOIs</h2>{verdict}{verdict_rule}'
            f'<p class="note" style="margin:0"><b>Measured on a stated benchmark, not discoveries.</b> {s["counts"]["positive"]} confirmed or known planets '
            f'(CP/KP), {s["counts"]["fp"]} false positives and {s["counts"]["fa"]} false alarms from the TOI table (fetched {e(s["fetched_at"][:10])}, seed {s["seed"]}), '
            f'one TOI per star; held-out half shown. Panel: {e(b["panel"])}.</p>'
            f'<div class="tablewrap" role="region" tabindex="0" aria-label="Benchmark results"><table class="bench"><tbody>{body}</tbody></table></div>{clipnote}'
            f'<p class="muted" style="margin:0;font-size:12px">'
            + (f'<a rel="noopener" href="{brand.REPO_URL}/blob/main/docs/results/benchmark_real_tois_clipfix.md">Full results</a> '
               f'(the first run, on the pre-fix code: <a rel="noopener" '
               f'href="{brand.REPO_URL}/blob/main/docs/results/benchmark_real_tois.md">benchmark_real_tois.md</a>)' if clipfix
               else f'<a rel="noopener" href="{brand.REPO_URL}/blob/main/docs/results/benchmark_real_tois.md">Full results</a>')
            + '. TFOPWG dispositions are the reference, not ground truth for every TOI.</p></section>')


LEADERBOARD_JSON = "docs/leaderboard/leaderboard.json"
LEADERBOARD_SCOPES = {"held_out": ("Held-out half", "every held-out star"),
                      "sentinel_subsample": ("The Sentinels' subsample", "{n} held-out stars · not ranked")}


def _load_leaderboard(path: str | Path = LEADERBOARD_JSON) -> dict | None:
    """The scored real-TOI leaderboard (setuhq leaderboard), without the submissions' per-star rows."""
    if not Path(path).exists():
        return None
    return json.loads(Path(path).read_text())


def _lb_cell(r: dict | None, label: str, missing: str = "n/a") -> str:
    e = html.escape
    if not r or r.get("rate") is None:
        return f'<td data-l="{e(label)}"><span class="na">{e(missing)}</span></td>'
    return (f'<td data-l="{e(label)}"><span class="v">{100 * r["rate"]:.0f}%</span>'
            f'<span class="ci">{r["k"]}/{r["n"]} · {100 * r["lo"]:.0f}–{100 * r["hi"]:.0f}%</span></td>')


def _lb_j(j: dict, label: str) -> str:
    if j["j"] is None:
        return f'<td data-l="{label}"><span class="na">n/a</span></td>'
    return f'<td data-l="{label}"><span class="v">{j["j"]:+.2f}</span><span class="ci">{j["lo"]:+.2f} to {j["hi"]:+.2f}</span></td>'


def _leaderboard(lb: dict | None) -> str:
    """The Leaderboard page: the scored table per scope, the rules, and the frozen sample's hash. Static HTML."""
    e = html.escape
    head = (f'<header>{_eyebrow("Leaderboard", ("sentinels", "Sentinels"))}<h1 class="lead-h" id="h-leaderboard" tabindex="-1">'
            'Methods, scored blind on real TOIs.</h1><p>The public leaderboard on the frozen real-TOI benchmark: each entry\'s '
            'detected events, scored by the leaderboard itself on the held-out half only, with Wilson 95% intervals. Not the injection threshold sweep '
            '(docs/threshold_sweep.md), which tunes Probe thresholds on synthetic light curves.</p></header>'
            f'<p class="note"><b>Measured on a stated benchmark; nothing here is a discovery.</b> {e(ATTRIBUTION)}</p>')
    if not lb:
        return head + ('<section class="card"><h2>Not built</h2><p class="muted" style="margin:0">The leaderboard has not been '
                       'scored for this build (setuhq leaderboard).</p></section>')
    cols = [("completeness_clean_searchable", "Clean completeness, searchable CP/KP"),
            ("fp_rejection_searchable", "FP rejection, searchable FP"), ("small", "Recovered below 4 R⊕"),
            ("inverted", "Inverted control: stars with any"), ("scrambled", "Scrambled control: stars with any"),
            ("reliability", "Reliability")]
    out = [head]
    for scope, (title, sub) in LEADERBOARD_SCOPES.items():
        es = [x for x in lb["entries"] if x["scope"] == scope]
        if not es:
            continue
        ranked_scope = scope == "held_out"
        rows = []
        for x in es:
            s = x["scores"]
            small = [b for b in s["completeness_by_radius"] if b["bin"][1] <= 4]
            k, n = sum(b["k"] for b in small), sum(b["n"] for b in small)
            p, lo, hi = wilson(k, n)
            cells = {"small": {"k": k, "n": n, "rate": p, "lo": lo, "hi": hi} if n else None,
                     **{v: (s["controls"][v] or {}).get("stars_with_any") for v in ("inverted", "scrambled")}}
            tds = "".join(_lb_cell(cells[c] if c in cells else s[c], label,
                                   "not measured" if c in ("inverted", "scrambled") else "n/a") for c, label in cols)
            jcell = _lb_j(s["youden_j"], "Youden J") + _lb_j(s["youden_j_all_stars"], "Youden J, all stars")
            rk = ""
            if ranked_scope:
                ov = x.get("overlaps_ranks") or []
                tie = f'<span class="kd">interval overlaps #{", #".join(map(str, ov))}</span>' if ov else ""
                rk = (f'<td class="rk" data-l="Rank">{x["rank"]}{tie}</td>' if x["ranked"] else
                      f'<td class="rk" data-l="Rank"><span class="na">unranked</span><span class="kd">{e(x["unranked_reason"])}</span></td>')
            rows.append(f'<tr>{rk}<th scope="row">{e(x["name"])}'
                        f'<span class="kd">{e(x["id"])} · tuned on {e(x["tuned_on"])}</span></th>{jcell}{tds}</tr>')
        hid = f"h-lb-{scope.replace('_', '-')}"
        ths = "".join(f'<th scope="col">{e(label)}</th>' for _, label in cols)
        note = ("Ranked by Youden's J on the searchable set the benchmark fixed, with one predicate on both sides (a clean "
                "candidate: on the ephemeris, passed, no eclipsing-binary flag), so calling every TOI a planet, flagged or "
                "not, scores zero. The controls gate ranking and do not enter J, and the control lists are the method's own "
                "report. Where intervals overlap the order is not a measured difference." if ranked_scope else "")
        rank_th = '<th scope="col">Rank</th>' if ranked_scope else ""
        lead_text = (lb.get("floor_note") or "") if ranked_scope else lb.get("subsample_note", "")
        lead = f'<p class="note" style="margin:0"><b>{e(lead_text)}</b></p>' if lead_text else ""
        out.append(f'<section class="card lb" aria-labelledby="{hid}"><h2 id="{hid}">{e(title)} <span class="sub">{e(sub.format(n=len(lb.get("sentinel_subsample") or [])))}</span></h2>{lead}'
                   f'<div class="tablewrap" role="region" tabindex="0" aria-labelledby="{hid}"><table class="lbtable"><thead><tr>'
                   f'{rank_th}<th scope="col">Entry</th><th scope="col">Youden J</th><th scope="col">Youden J, all stars</th>{ths}</tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table></div>'
                   f'<p class="small">Each cell: the rate, then k/n and the Wilson 95% interval. {e(note)}</p></section>')
    if any(x["scope"] == "sentinel_subsample" for x in lb["entries"]):
        ag = lb.get("sentinel_agreement") or {}
        agree = (f" (they agree on {ag['agree']} of {ag['n']} stars, φ = {ag['phi']:.2f})"
                 if ag.get("n") and ag.get("phi") is not None else "")
        out.append(f'<p class="note"><b>The Sentinel rows cover {len(lb.get("sentinel_subsample") or [])} stars.</b> Their '
                   f'intervals are wide, the two personas share one model{agree}, so they count as one correlated voter, not '
                   'two, and they were never run on the control light curves. The Probes + Sentinels rows are star-level combinations of stored outcomes, stated '
                   'before scoring, not a run of the panel\'s consensus.</p>')
    for x in lb.get("refused") or []:
        out.append(f'<p class="note"><b>Refused: {e(x.get("name") or x.get("id") or "a submission")}.</b> {e("; ".join(x["reasons"]))}</p>')
    rules = "".join(f"<li>{e(r)}</li>" for r in lb["rules"])
    out.append(f'<section class="card" aria-labelledby="h-lb-rules" style="display:grid;gap:10px"><h2 id="h-lb-rules">Rules</h2>'
               f'<ol class="lbrules">{rules}</ol><p class="small">Submission format and refusal rules: docs/leaderboard/README.md. '
               'Score a submission with setuhq leaderboard &lt;file&gt;.</p></section>')
    out.append(f'<section class="card" aria-labelledby="h-lb-hash"><h2 id="h-lb-hash">The frozen sample</h2><dl class="kv lbhash">'
               f'<dt>frozen sample sha256</dt><dd>{e(lb["sample_sha256"])}</dd>'
               f'<dt>public inputs sha256</dt><dd>{e(lb["inputs_sha256"])}</dd>'
               f'<dt>full sample (with held-out labels), canonical sha256: refused if stated</dt><dd>{e(lb["full_sample_sha256"])}</dd>'
               f'<dt>Sentinel subsample sha256</dt><dd>{e(lb["sentinel_subsample_sha256"])}</dd>'
               f'<dt>benchmark code commit</dt><dd>{e(lb.get("benchmark_code_commit") or "not stored")}</dd></dl>'
               '<p class="small" style="margin-top:10px">Sample: docs/results/benchmark_toi_sample.json. Public inputs: '
               'docs/leaderboard/tuning_inputs.json. TFOPWG dispositions are the reference, not ground truth for every TOI.</p></section>')
    return "".join(out)


def _sky(data: dict) -> str:
    """The Explore page: the sky by discovery year (V04, every catalogue planet) as the base layer, with the survey
    coverage layers, the ecliptic and the run star's pin over it in the same frame; the run's dips beside it; the
    coverage chips; the planets per year (V12); and the run's light curve."""
    from setuhq.viz import skyyears, timeline

    e = html.escape
    st, geo, h = data["story"], data["sky_geo"], data["hero"]
    star = st["star"]
    pin = marker = ""
    if geo.get("x") is not None:
        lead = st.get("lead_dip")
        known = f"{e(st['planet'])} · known planet" if st.get("planet") else f"{len(st['dips'])} dips · {UNCONFIRMED}"
        pin = (f'<a class="skypin" href="#/transit?dip={e(lead or "")}" style="left:{(geo["x"] + 460) / 920 * 100:.1f}%;top:{(geo["y"] + 235) / 470 * 100:.1f}%" '
               f'title="{e(star["name"])} placed from SIMBAD (ICRS J2000): RA {star["ra_deg"]:.2f}°, Dec {star["dec_deg"]:.2f}°">'
               f'<b>{e(star["name"])}</b><span>{known}</span><em>Open ›</em></a>')
        zoom = f' data-zoom="{e(st["planet"])}"' if st.get("planet") else ""
        marker = (f'<g class="skymark"{zoom}><circle class="pulse" cx="{geo["x"]}" cy="{geo["y"]}" r="22" fill="url(#pmg)"/>'
                  f'<circle cx="{geo["x"]}" cy="{geo["y"]}" r="10" fill="none" stroke="#64D2FF" stroke-width=".8"/>'
                  f'<circle class="skydot" cx="{geo["x"]}" cy="{geo["y"]}" r="3.2" fill="#FFFFFF"/></g>')
        where = f"{e(star['name'])} at RA {star['ra_deg']:.2f}°, Dec {star['dec_deg']:.2f}° ({e(star['source'])})"
    else:
        where = "The target's sky position is not stored, so it is not plotted"
    placed = f'{e(star["name"])} placed from SIMBAD (ICRS J2000) · ' if geo.get("x") is not None else "target not plotted (no position stored) · "
    overlay = (f'<svg class="skyover" viewBox="-460 -235 920 470" role="img" aria-label="Survey coverage layers (hidden until chosen), the ecliptic, and the run\'s star: {where}.">'
               f'<defs><radialGradient id="pmg"><stop offset="0" stop-color="#64D2FF" stop-opacity=".9"/><stop offset="1" stop-color="#64D2FF" stop-opacity="0"/></radialGradient></defs>'
               f'{sky_layers_svg(data.get("coverage"))}{sky_layer_svg(data.get("sweep"))}'
               f'<path d="{geo["ecl"]}" stroke="#FFB340" stroke-width=".9" fill="none" stroke-dasharray="2 6" opacity=".7"/>{marker}</svg>{pin}')
    cat = data.get("catalogue")
    src = skyyears.source_text(cat) if cat else ""
    base = skyyears.html({"source": src, "app": data}, where="explore", overlay=overlay, uid="skyyears") if cat else ""
    if not base:  # no catalogue in this build: the map is the frame, the layers and the pin
        base = (f'<div class="stage skystage"><div class="skybox">{overlay}</div><span class="stage-tag">Real data, cited</span></div>')
    tl = timeline.html({"source": src, "app": data}, where="explore", uid="timeline") if cat else ""
    links = "".join(obj_link(k, n, f"{n} ›") for k, n in (("star", star.get("name")), ("planet", st.get("planet"))) if n)
    if st.get("planet") and geo.get("x") is not None:
        links += (f'<button class="btn skyzoom" type="button" data-zoom="{e(st["planet"])}" hidden>'
                  f'Zoom into the {e(st["planet"])} system ›</button>')
    links = f'<div class="pllinks skylinks">{links}</div>' if links else ""
    t1, t2 = st["sky_title"]
    tl_sec = (f'<section class="sktl" aria-labelledby="h-sktl"><h2 id="h-sktl" class="secth">Planets found each year, by method</h2>{tl}</section>' if tl else "")
    return f"""<header class="headrow">
        <div>{_eyebrow("Sky")}<h1 class="lead-h" id="h-sky" tabindex="-1">{e(t1)}<br><span class="grey">{e(t2)}</span></h1></div>
        <div class="chips" id="skychips" role="group" aria-label="Show dips by status"></div>
      </header>
      <p class="muted" style="margin:0;max-width:80ch">{e(h["lede"])} {e(h["qualifier"])} {e(h["archive"])}</p>
      <div class="row2">
        <section class="skymap" aria-labelledby="h-skymap">
          <h2 id="h-skymap" class="sr">Sky map</h2>
          {base}
          <p class="skynote">Feed stars not plotted (positions not stored) · {placed}dashed: the ecliptic</p>
          {links}
        </section>
        <aside class="glass dipsbox" aria-labelledby="h-skydips">
          <div class="dhead"><b id="h-skydips">Dips</b><span class="muted" id="skycount"></span></div>
          <div class="segctl" id="skyrev" role="group" aria-label="Who marked it"></div>
          <div id="skydips"></div>
        </aside>
      </div>
      {_sky_coverage(data)}
      {tl_sec}
      <section class="glass runline" aria-labelledby="h-skytl">
        <h2 id="h-skytl" class="sr">The run's light curve</h2>
        <div class="cap" id="skytlcap"></div>
        <div id="skytimeline"></div>
        <p class="xread" id="skytlread" aria-live="polite"></p>
      </section>"""


def _with_sweep_chip(chips: str, meta: dict | None) -> str:
    """The survey-coverage chips with the sweep's own layer added at the end of the group."""
    extra = sky_chip(meta)
    if not extra or not chips.endswith("</div>"):
        return chips
    return chips[:-len("</div>")] + extra + "</div>"


def _sky_coverage(data: dict) -> str:
    cov = data.get("coverage")
    if not cov:
        return ""
    f = cov["fractions"]
    return (f'<section class="glass skycov" aria-label="Survey coverage">{_with_sweep_chip(coverage_chips(cov, "sky"), data.get("sweep"))}<p>Survey coverage: TESS has observed {f["tess"] * 100:.1f}% of the sky '
            f'(sectors 1–{cov["tess_last_sector"]}); {f["unmapped"] * 100:.1f}% has never been in a TESS, Kepler or K2 footprint. '
            f'Shading shows where surveys looked, not where planets are. <a href="#/galaxy">Figures and sources in the Galaxy ›</a></p>'
            + (f'<p>The setuhq sweep layer: one green dot per star-sector the sweep searched ({len(data["sweep"]["sky"]):,} so far, positions from MAST), '
               f'amber where it has an entry in a class that exceeds its null in this slice '
               f'({", ".join(c.replace("_", " ") for c in data["sweep"].get("sky_found_classes") or []) or "none"}). '
               f'<a href="#/variables">Everything that dims ›</a></p>'
               if data.get("sweep") and data["sweep"].get("sky") else "") + '</section>')


def _transit(data: dict) -> str:
    return f"""<header class="headrow">
        <div><p class="eyebrow" id="txkicker"></p><h1 class="lead-h" id="h-transit" tabindex="-1"></h1><p id="txsub"></p></div>
        <div style="display:flex;align-items:center;gap:8px" id="txnav"></div>
      </header>
      <p class="txnotice" id="txnotice" role="status" hidden></p>
      <nav class="dipchips" id="txchips" aria-label="Dips"></nav>
      <div class="row2">
        <section class="space theatre" id="txtheatre" aria-label="Transit theatre">
          <div class="cap"><span id="txcapword">The transit, played back</span><span id="txcap"></span></div>
          {system_stage("txsysfig", "The star in its blackbody colour with the planet crossing it, and a limb-darkened model light curve with this dip's stored points overlaid.")}
          <p class="foot" id="txfoot"></p>
          <div class="pllinks" id="txlinks"></div>
        </section>
        <aside class="tx-side">
          <section class="glass scorecard" id="txscore" aria-label="Panel score and verdict"></section>
          <section class="glass lanes" id="txlanes" aria-label="Who marked it"></section>
          <section id="txquote" aria-label="A Sentinel's words"></section>
        </aside>
      </div>
      <section class="row2" id="txorbit" aria-label="Orbit and compare"></section>
      <p class="note" id="txcaveat" hidden></p>
      <p class="casefile" id="txcase"></p>
      <p class="small" id="txarchive"></p>
      <p class="small">Only a dip that passed vetting is a candidate, and it stays unconfirmed; a rejected dip is not one. Stored values only: the points, marks, scores, flags and words are as the run stored them.</p>"""


def _explorer(data: dict) -> str:
    """The Candidates page's opening: what a visitor can open (every example run's dips, grouped by star, each
    with a case file), then the lead run's own figures. The search feed follows in its own section."""
    e = html.escape
    feed = data["catalog"]["candidates"]
    cards = data.get("showcase") or []
    n_all = sum(c["n_dips"] for c in cards)
    groups = []
    for c in cards:
        rows = []
        for d in c["dips"]:
            rows.append(f'<li><a class="rundip" href="#/transit?dip={e(d["id"])}"><b>{e(d["label"])}</b>'
                        f'<span class="muted">{e(d.get("status_label") or "")} · {d.get("depth_ppm") or 0:,.0f} ppm · SNR {d.get("snr") or 0:.1f}</span>'
                        f'{dip_tag(d.get("outcome"))}</a>'
                        f'<a class="rundipcf" href="#/candidates?dip={e(d["id"])}" aria-label="Case file for {e(d["label"])}">Case file ›</a></li>')
        hid = f'h-run-{e(c["slug"])}'
        groups.append(f"""<section class="card rundips" aria-labelledby="{hid}">
        <h2 id="{hid}">{e(c["star"])}{f' · {e(c["kind"])}' if c["kind"] else ""}: {e(c["count"])}</h2>
        <p class="small">Run {e(c["run"])}, TESS sector{"s" if len(c["sectors"]) != 1 else ""} {e(", ".join(str(x) for x in c["sectors"]))}. {e(c["panel_label"])}.{f" {e(c['outcome_line'])}" if c["outcome_line"] else ""}{f" {e(c['caveat'])}" if c["caveat"] else ""}</p>
        <ul class="rundiplist">{"".join(rows)}</ul>
        <p class="small runlinks"><a href="{e(c["case_file"])}">The run's case file ›</a> <a href="{e(c["plates"])}">Plates ›</a> <a href="{e(c["report"])}">Run report ›</a></p>
      </section>""")
    more = (f" Further down: the search feed's {len(feed)} entries from other stars, which have no case file yet." if feed else "")
    return f"""<header>
        <h1 class="lead-h" id="h-explorer" tabindex="-1">{n_all} dip{"s" if n_all != 1 else ""} you can open, from {number_words(len(cards))} example star{"s" if len(cards) != 1 else ""}.</h1>
        <p>Dips the panel marked in each example star's TESS light curve, grouped by star and counted by vetting outcome. A dip that passed vetting is a {UNCONFIRMED}; a flagged one is open; a rejected one is not a candidate. None is a confirmed planet. Open one to watch it played back, or its case file for every check behind its verdict.{e(more)}</p>
      </header>
      {"".join(groups)}
      <p class="small"><a href="#/planets">Radius ratios by star ›</a> What each depth would imply, if it were a planet.</p>"""


def _example_runs_table(data: dict) -> str:
    """Evidence > Runs: every stored example run with its provenance (the input files' sha256, the configuration's
    sha256, the code that ran) and its panel."""
    e = html.escape
    rows = []
    for c in data.get("showcase") or []:
        files = "<br>".join(f'sector {e(str(i["sector"]))}: <span class="mono">{e((i.get("file_sha256") or "not stored")[:16])}…</span>' for i in c["inputs"]) or "not stored"
        rows.append(f'<tr><th scope="row">{e(c["star"])}<br><span class="muted mono">{e(c["run"])}</span></th><td>{e(c["count"])}</td>'
                    f'<td>{files}</td><td><span class="mono">{e(c["config_sha256"][:16])}…</span></td>'
                    f'<td><span class="mono">{e(c["code"] or "not recorded")}</span></td><td>{e(c["panel_label"])}</td></tr>')
    if not rows:
        return ""
    return f"""<section class="card" aria-labelledby="h-exruns" style="display:grid;gap:8px"><h2 id="h-exruns">The example runs</h2>
        <p class="muted" style="margin:0;font-size:13px">Every stored run the candidate pages show, with the sha256 of each light-curve file read from MAST, of the configuration, and the code that ran (git describe). {e(ATTRIBUTION)}</p>
        <div class="tablewrap" tabindex="0" role="region" aria-label="The example runs and their provenance"><table><thead><tr><th scope="col">Star and run</th><th scope="col">Dips</th><th scope="col">Light curve sha256</th><th scope="col">Config sha256</th><th scope="col">Code</th><th scope="col">Panel</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
      </section>"""


def _sentinels(data: dict) -> str:
    e = html.escape
    st = data["story"]
    n = len(st["reviewers"])
    n_inj = max([r.get("n_injected") or 0 for r in st["reviewers"]] or [0])
    caveat = (f" Weights come from {n_inj} planted and {n_inj} empty light curves each: too few to separate 0.6 from 0.5."
              if n_inj else "")
    return f"""<header class="headrow">
        <div>{_eyebrow("Sentinels and Probes")}<h1 class="lead-h" id="h-sentinels" tabindex="-1">{e(number_words(n).capitalize())} reviewers.<br><span class="grey">Each one earns its vote.</span></h1>
        <p>The panel that marked dips in run {e(data["run"]["name"])}: the Sentinels and the Probes, no people. <span class="attribution">{e(ATTRIBUTION)}</span></p></div>
        <div class="segctl" id="senfilter" role="group" aria-label="Show"></div>
      </header>
      <div class="row2">
        <figure class="space ringfig" id="senring"></figure>
        <div class="revcards" id="sencards"></div>
      </div>
      <section class="glass marked" id="senmarked" aria-label="What the selected reviewer marked"></section>
      <p class="muted" style="margin:0;font-size:13px">{e(ATTRIBUTION)}{e(caveat)}</p>"""


def app_payload(data: dict) -> dict:
    """What the page's script reads (written once to assets/data/app-<hash>.json and shared by every page). The
    leaderboard, the sky geometry, the decoration and the galaxy teaser are rendered into the HTML at build time;
    the Docket the case file frames is a file of its own."""
    data = {**data, "methods": methods_meta(data["examples"], data.get("galaxy"), data["story"], data.get("coverage"))}
    slim = {**data, "sweep": sweep_payload(data["sweep"])} if data.get("sweep") else data
    server_only = ("galaxy", "coverage", "examples", "catalogue", "benchmark", "sweep_full", "leaderboard", "sky_geo", "deco",
                   "galaxy_teaser", "docket_html", "code_note", "extra_docket_html")
    return {k: v for k, v in slim.items() if k not in server_only}


def provenance_note(data: dict) -> str:
    """The one-sentence note on a page whose figures come from the stored run (empty when the run is current)."""
    from setuhq.codenote import visitor_note

    return visitor_note(data.get("code_note"))


def route_sections(data: dict) -> dict[str, str]:
    """Every view of the app as the inner HTML of its ``<section class="route">``, keyed by route.

    The site builder (setuhq.site) renders each page's own view into that page, and bundles all of them into one
    shared file, so a page can switch to another view in place."""
    run = data["run"]
    rule = data["feed_rule"]
    unc = html.escape(UNCONFIRMED)
    nodet = html.escape(NO_DETECTION)
    feed = data["catalog"]["candidates"]
    n_known = sum(1 for r in feed if r.get("status") == "known_toi")
    xm_targets = ", ".join(html.escape(str(t)) for t in data.get("crossmatch_targets") or []) or "no star"
    prov = provenance_note(data)
    out = {}
    from setuhq.home import _overview  # the home page (setuhq.home imports from this module)

    out["overview"] = _overview(data)
    out["sky"] = _sky(data)
    out["galaxy"] = galaxy_section(data.get("galaxy"), "", UNCONFIRMED, data.get("coverage"))
    out["transit"] = _transit(data).replace('<p class="txnotice"', prov + '<p class="txnotice"', 1)
    n_stars = len({r["tic"] for r in feed})
    out["explorer"] = f"""{_explorer(data)}
      {prov}
      <p class="note rule" id="sharednote" hidden>This is a shared view, shown for this visit only. Your own layout is unchanged unless you change a card here. <button class="btn" id="ownlayout" type="button">Show my layout</button></p>
      <div class="secthead"><h2 id="h-glance">The reference run ({html.escape(run["name"])}) at a glance</h2><button class="btn" id="customise" type="button" aria-pressed="false" aria-controls="widgets layouttools">Customise</button></div>
      <div class="layoutbar" id="layouttools" role="group" aria-label="Arrange the cards" hidden>
        <p class="small" style="flex:1 1 100%">Each card can be hidden, moved or resized; your arrangement is kept in this browser.</p>
        <div class="layoutbar" id="hiddenlist"></div>
        <button class="btn" id="resetlayout" type="button">Reset layout</button>
      </div>
      <div class="widgets" id="widgets"></div>
      <section class="feedsec" aria-labelledby="h-feedsec">
      <div class="secthead"><h2 id="h-feedsec">From the search feed: {len(feed)} entr{"y" if len(feed) == 1 else "ies"} from {n_stars} other star{"" if n_stars == 1 else "s"}</h2><p>SetuHQ's search batches run the same panel over more TESS stars. These entries are leads for review: {n_known} of {len(feed)} match a known TOI period, and none has a case file yet.{f" A TOI match is an archive comparison. {nodet}" if n_known else ""}</p></div>
      <p class="note rule"><b>Feed rule.</b> An entry joins the feed when its depth is at most {rule["max_depth_ppm"]:,.0f} ppm and its signal has at least {rule["min_transits"]} transits. This is an admission rule, not a vetting result.</p>
      <div class="filters exfilters">
        <div class="chips" id="exstars" role="group" aria-label="Stars"></div>
        <div><div class="segctl" id="exstatus" role="group" aria-label="Status"></div><div class="segctl" id="exsnr" role="group" aria-label="Minimum SNR"></div></div>
      </div>
      <div class="row2">
        <section class="space scatterbox" aria-labelledby="h-scatter">
          <div class="cap"><span id="h-scatter">Depth against period</span><span id="excount"></span></div>
          <div class="scatter" id="exscatter"></div>
          <p class="foot" id="exfoot">Each point a feed entry; size and glow follow SNR; yellow: no known TOI period. {nodet}</p>
        </section>
        <aside class="glass selpanel" id="exsel" aria-label="Selected entry"></aside>
      </div>
      <section class="card" aria-labelledby="h-feed" style="display:grid;gap:10px">
        <h2 id="h-feed">Feed entries</h2>
        <p class="muted" id="feedhead" style="margin:0;font-size:13px"></p>
        <div class="chips" id="discchips" role="group" aria-label="Filter the feed by status"></div>
        <div class="tablewrap scrollbox" id="disctable" tabindex="0" role="region" aria-label="Feed table, every entry shown; scrolls sideways when wider than the screen"></div>
        <p class="muted" id="disccount" style="margin:0;font-size:12px"></p>
      </section>
      <section aria-labelledby="h-dist" style="display:grid;gap:10px">
        <h2 id="h-dist">Distributions</h2>
        <div class="charts"><div class="card" id="h-depth"></div><div class="card" id="h-snr"></div><div class="card" id="h-period"></div></div>
      </section>
      <section class="card" aria-labelledby="h-time" style="display:grid;gap:8px">
        <h2 id="h-time">Timeline by star</h2>
        <div class="legend"><span><i class="k-new"></i>new candidate</span><span><i class="k-known"></i>period matches a known TOI</span><span>each dot: {unc}</span></div>
        <div id="timeline"></div>
      </section>
      </section>"""
    out["sentinels"] = f"""{_sentinels(data)}
      {prov}
      {_benchmark_card(data.get("benchmark"))}
      <p class="note rule"><b>Weights.</b> A reviewer's weight is its calibration skill from injection tests: the share of planted transits it finds minus the share of empty light curves it marks, with a floor. The weight a run used is the one its record stores; when it differs from the calibrated weight, the run did not use the calibrated weights. <a href="#/runs">Files and configuration ›</a></p>
      <section class="card" aria-labelledby="h-cal" style="display:grid;gap:8px">
        <h2 id="h-cal">Calibration plane</h2>
        <p class="muted" style="margin:0;font-size:13px">Each reviewer at its false-alarm rate (x: share of empty subjects it marked) and recall (y: share of injected transits it found) in calibration. Point size is its calibrated weight. The lines join points of equal weight, weight = TPR − FPR, floored at {data["calibration"]["floor"]}; up and to the left is better. Stored values only.</p>
        <div class="legend"><span><i class="k-sim"></i>Probe (deterministic detector), not a person</span><span><i class="k-cl"></i>Sentinel (Claude), not a person</span><span>size: calibrated weight</span></div>
        <div id="calplane"></div>
        <p class="note" id="calsample" style="margin:0"></p>
        <div class="tablewrap" id="caltable" tabindex="0" role="region" aria-label="Calibration rates per reviewer"></div>
        <div class="calcards" id="calcards"></div>
        <p class="muted" id="calsource" style="margin:0;font-size:12px;overflow-wrap:anywhere"></p>
      </section>
      <section class="card" aria-labelledby="h-agree" style="display:grid;gap:8px">
        <h2 id="h-agree">Marks per dip</h2>
        <p class="muted" style="margin:0;font-size:13px">Which reviewers marked each dip, from the run's stored reviewer list. The verdict ledger link opens the dip's checks in its case file.</p>
        <div id="agreement"></div>
      </section>
      <div class="cards" id="panelcards"></div>
      <p class="casefile"><a href="#/leaderboard">The real-TOI leaderboard ›</a><span>SetuHQ's configurations, and any method submitted, scored blind on the held-out half.</span></p>
      <p class="casefile"><a href="#/runs">Runs and configuration ›</a><span>Every search run, its errors as stored, and the configuration behind these pages.</span></p>"""
    out["methods"] = methods_section(data["examples"], data.get("galaxy"), {**data["story"], "run_created": run.get("created_at", "")}, data.get("coverage"), "")
    out["mission"] = mission_section("")
    out["catalogue"] = catalogue_section(data.get("catalogue_meta"), "").replace("</header>", "</header>" + (catalogue_tabs("catalogue") if data.get("sweep") else ""), 1)
    out["planet"] = planet_page("")
    out["star"] = star_page("") + '<section class="card stsweep" id="stsweep" aria-labelledby="h-stsweep" hidden><h2 id="h-stsweep">In SetuHQ\'s sweep</h2><div id="stsweepbody"></div></section>'
    # The sweep's figures, each class against its own null, open its page (the home page says it in one sentence).
    out["variables"] = variables_section(data.get("sweep"), "").replace("</header>", "</header>" + overview_counter(data.get("sweep")).replace('<a class="btn" href="#/variables">Everything that dims ›</a>', ""), 1)
    out["candidates"] = f"""<header><h1 class="lead-h" id="h-candidates" tabindex="-1">Every signal, its dips, and the checks behind each verdict.</h1><p>The case file for the dip's run: every signal and its dips, with the vetting outcome, the transit strip and the verdict ledger. Each signal that passed vetting is a {unc}; a rejected or flagged one is named by its status.</p></header>
      {prov}
      <div class="frametools"><a id="fullpage" href="/candidates/case-file/">Open full page</a><span class="muted">The case file on its own page, at the same dip.</span></div>
      <div class="dippicker"><label for="dippick">Dip</label><select id="dippick" aria-describedby="dippickhint"></select><span class="sr" id="dippickhint">Every dip of every example run, grouped by star and numbered in time order, with its vetting outcome. A dip that passed vetting is a {unc}.</span></div>
      <p class="note" id="framestatus" role="status" hidden></p>
      <p class="note blocked" id="frameblocked" role="alert" hidden>The case file could not load in this view. <a id="blockedlink" href="/candidates/case-file/">Open it on its own page.</a></p>
      <iframe class="frame waiting" id="docketframe" title="Case file: signals, dips and vetting"></iframe>"""
    out["planets"] = f"""<header><h1 class="lead-h" id="h-planets" tabindex="-1">What each depth would imply, if it were a planet.</h1><p>One card per star in the run or the feed. Each entry is a {unc}; the ratio below is what its stored depth implies if it were a planet.</p></header>
      {prov}
      <p class="note"><b>Radius ratio only.</b> Rp/R* = √depth, with depth as a fraction (ppm × 10⁻⁶). This assumes a full, undiluted transit and ignores limb darkening. {html.escape(NO_STELLAR_RADIUS)} Each bar is a ratio scale from 0 to {data["ratio_scale_max"]:.2f}, the same on every card.</p>
      <p class="note">Published planets come from the stored archive cross-match, which covers {xm_targets}. The other stars have no stored cross-match, so their cards have no archive box. {nodet}</p>
      <div class="cards" id="planetcards"></div>"""
    out["leaderboard"] = _leaderboard(data.get("leaderboard"))
    out["runs"] = f"""<header><h1 class="lead-h" id="h-runs" tabindex="-1">Every search run, its errors as stored, and the configuration behind these pages.</h1><p>The search run history from the catalogue, and the configuration of run {html.escape(run["name"])}. Error messages are shown as stored.</p></header>
      {prov}
      {_example_runs_table(data)}
      <section class="card" aria-labelledby="h-hist" style="display:grid;gap:4px"><h2 id="h-hist">Search runs</h2><div id="runtable"></div></section>
      <details class="card cfg"><summary>Configuration: run {html.escape(run["name"])} and the search catalogue</summary><div>
        <section aria-labelledby="h-cfg"><h3 id="h-cfg">This run's configuration</h3><div id="runconfig"></div></section>
        <section aria-labelledby="h-catcfg"><h3 id="h-catcfg">Search catalogue</h3><div id="catconfig"></div></section>
      </div></details>
      <p class="small">Calibrated weights: {html.escape(data["weights_path"] or "no weights file")}. Archive cross-match: {html.escape(data.get("crossmatch_file") or "crossmatch.json")}. Built from {html.escape(run["dir"])} and {html.escape(data["catalog"]["path"] or "no catalogue")}.</p>"""
    return out


GALAXY_JSON = "assets/data/galaxy.json"


def galaxy_json(data: dict) -> str:
    """The map's arrays, written beside the page and fetched (same origin) on the first visit to the Galaxy.
    Galactic l and b go to the CSV only; the page draws from x, y, z."""
    g = {**data["galaxy"], "hosts": {k: v for k, v in data["galaxy"]["hosts"].items() if k not in ("l", "b")}}
    return json.dumps(g, separators=(",", ":"), ensure_ascii=False)


def _galaxy_scripts(data: dict, galaxy_payload: str = "") -> str:
    """The map's arrays (parsed only when the Galaxy opens) and the Overview teaser's points and code."""
    out = f'<script id="galaxy-data" type="application/json">{galaxy_payload}</script>' if galaxy_payload else ""
    if data.get("galaxy_teaser"):
        teaser = json.dumps(data["galaxy_teaser"], separators=(",", ":")).replace("</", "<\\/")
        out += f'<script id="teaser-data" type="application/json">{teaser}</script><script>{TEASER_JS}</script>'
    return out


def _input_label(data: dict) -> str:
    inp = (data["config"].get("inputs") or [{}])[0]
    bits = [inp.get("mission"), f"Sector {inp['sector']}" if inp.get("sector") is not None else None]
    return " ".join(b for b in bits if b) or "stored input"


def build_app(run_dir: str | Path, out_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
              weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None,
              require_crossmatch: bool = False, sweep_path: str | Path | None = DEFAULT_SWEEP) -> Path:
    """Build the site into ``out_dir`` (see :mod:`setuhq.site`) without the report, plates and stand-alone case file
    (``setuhq site`` builds those too); returns the home page's path."""
    from setuhq.site import build_site

    return build_site(run_dir, out_dir, title=title, catalog_path=catalog_path, weights_path=weights_path, star=star,
                      require_crossmatch=require_crossmatch, sweep_path=sweep_path, extras=False)

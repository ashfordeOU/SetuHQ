"""The exoplan app shell: one self-contained page with a sidebar and six sections.

Each section is a route in the URL hash (``#/overview``, ``#/candidates``,
``#/discoveries``, ``#/planets``, ``#/panel``, ``#/runs``), with an optional
query: ``#/candidates?dip=<candidate_id>`` opens the Docket on that dip and
``#/overview?layout=kpis.L,top.L,...`` carries a widget layout and
``#/discoveries?sort=depth&filter=new`` the Feed's sort and filter. Hashes that do
not start with ``#/`` (the skip link's ``#content``) are not routes.

* Overview: a widget grid (run figures, feed count, recent runs, top
  candidates). Each widget's header hides it, moves it and sets its size; the
  layout lives in the URL and, when the browser allows it, in localStorage as
  the viewer's default. A layout opened from a shared link is shown for that
  view only; storage is written only when the viewer changes a control.
* Candidates: the Docket, rendered by :mod:`exoplan.docket` and embedded as an
  inline frame, so its code, honesty rules and keyboard handling are unchanged.
  The dip id is handed to the frame as its location hash, which the Docket reads.
  The shell's copy of the Docket carries :data:`FRAME_BRIDGE_JS`, which reports the
  selected dip and section back, so the shell URL follows in-frame navigation. A
  frame that never reports in (blocked by frame-src, say) is replaced by a message
  and a link to the Docket's own page.
* Discoveries (titled "Feed" when most entries match a known TOI): the feed
  from the discovery catalogue, with histograms and a timeline by star.
* Planets: one card per star with the planet-to-star radius ratio sqrt(depth).
  No stellar radius is stored, so nothing is converted to Earth or Jupiter radii.
* Panel: a calibration plane (each reviewer's false-alarm rate against its recall,
  sized by calibrated weight, with lines of constant weight and the sample size
  stated), which reviewers marked each dip, and one card per reviewer.
* Runs: one line per discovery run with its errors, and the configuration.

Every number on the page is read from the run directory, the catalogue or the
reviewer-weights file. Nothing is fitted or looked up at build time, apart from
the Docket's archive cross-match, which reuses crossmatch.json when it is stored.
"""

from __future__ import annotations

import html
import json
import math
from pathlib import Path

from exoplan.discover import MAX_FEED_DEPTH_PPM, MIN_FEED_TRANSITS
from exoplan.galaxy import (CSV_NAME, DEFAULT_COVERAGE, DEFAULT_MAP, DEFAULT_NOTABLE, coverage_chips, load_coverage, sky_layers_svg, GALAXY_CSS, GALAXY_JS, TEASER_JS, galaxy_data,
                            galaxy_meta, galaxy_section, map_csv, teaser_html, teaser_points)
from exoplan.catalogue import (CATALOGUE_CSS, CATALOGUE_JS, CATALOGUE_JSON, DEFAULT_CATALOGUE, SEARCH_BUTTON, SEARCH_DIALOG,
                               catalogue_meta, catalogue_section, load_catalogue, mentions, planet_page, star_page, tic_names)
from exoplan.objects import obj_link
from exoplan.learn import LEARN_BAR, LEARN_CSS, LEARN_JS, learn_card, learn_steps
from exoplan.mission import GRIDS as MISSION_GRIDS, MISSION_CSS, MISSION_JS, PANES as MISSION_PANES, mission_section
from exoplan.methods import DEFAULT_EXAMPLES, METHODS_CSS, METHODS_JS, load_examples, methods_meta, methods_section, system_stage, CHAPTERS, CHAPTER_PLANETS
from exoplan.docket import DOCKET_FONTS_CSS, OUTCOME_LABEL, docket_data, docket_page
from exoplan.names import ATTRIBUTION, panel_phrase, reviewer_names
from exoplan.story import DEFAULT_TARGETS, decoration, number_words, sky_geometry, story_data

# The eight sections of the top bar, and five pages each reached from one of them.
SECTIONS = [
    ("overview", "Overview"),
    ("sky", "Sky"),
    ("galaxy", "Galaxy"),
    ("catalogue", "Catalogue"),
    ("transit", "Transit"),
    ("explorer", "Explorer"),
    ("sentinels", "Sentinels"),
    ("methods", "Methods"),
    ("mission", "Mission Control"),
]
SUBPAGES = [("candidates", "Case file", "transit"), ("planets", "Planets", "explorer"), ("runs", "Runs", "sentinels"),
            ("planet", "Planet", "catalogue"), ("star", "Star", "catalogue")]
# Old addresses keep working: each is rewritten to the section that took its place (query kept).
ROUTE_ALIASES = {"discoveries": "explorer", "feed": "explorer", "panel": "sentinels", "home": "sky",
                 "cockpit": "transit", "about": "overview"}

WIDGETS = [
    ("kpis", "Run figures"),
    ("discoveries", "Feed count"),
    ("runs", "Recent runs"),
    ("top", "Top candidates"),
]
SIZES = ("S", "M", "L")
DEFAULT_SIZE = {"kpis": "L", "discoveries": "M", "runs": "M", "top": "L"}

UNCONFIRMED = "candidate, unconfirmed"
NO_DETECTION = "Archive values only. This page claims no detection."
NO_STELLAR_RADIUS = ("No stellar radius is stored in the run or the catalogue, so this page does not "
                     "convert the ratio to a planet radius in Earth or Jupiter units.")
STATUS_LABEL = {"new_candidate": "new candidate", "known_toi": "period matches a known TOI"}
ARCHIVE_FIELDS = ("pl_name", "hostname", "pl_orbper", "tran_flag", "rv_flag", "tic_id")
DEFAULT_WEIGHTS = "docs/results/reviewer_weights_full_panel.json"
RATIO_SCALE_MAX = 0.1  # Planets: every ratio bar runs from 0 to this Rp/R* value, labelled on the page.
# Kshana's families (the Observatory system): Geist for text, Geist Mono for numbers, Unbounded for the
# wordmark. Self-hosted as Kshana does: build_app copies src/exoplan/fonts to <out>/assets/fonts.
FONTS_DIR = Path(__file__).parent / "fonts"
FONTS_CSS = "assets/fonts/fonts.css"  # relative to the app page
# The shell's copy of the Docket runs from a blob URL, which cannot resolve a relative address; the shell
# swaps this placeholder for the absolute address of FONTS_CSS before it makes the blob.
FRAME_FONTS_HREF = "__EXOPLAN_FONTS_CSS__"


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
            "status": OUTCOME_LABEL.get(c.get("outcome"), ""),
            "archive_line": (comparison.get(c["candidate_id"]) or {}).get("line", ""),
        })
    for r in feed:
        star = _tic_label(r["tic"])
        entry = card(star)
        if "discovery feed" not in entry["sources"]:
            entry["sources"].append("discovery feed")
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
    from exoplan.calibrate import WEIGHT_FLOOR

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
    points.sort(key=lambda p: (p["kind"] != "simulated", p["id"]))
    return {"points": points, "iso": list(ISO_WEIGHTS), "floor": (record or {}).get("floor", WEIGHT_FLOOR),
            "source": (record or {}).get("source", ""), "rule": (record or {}).get("rule", "weight = max(TPR - FPR, floor)")}


def dip_agreement(dips: list[dict], kinds: dict[str, str]) -> list[dict]:
    """Per dip: which reviewers marked it, with simulated and Claude counts out of the panel."""
    sim_all = [r for r, k in kinds.items() if k == "simulated"]
    cl_all = [r for r, k in kinds.items() if k in ("claude", "claude_code")]
    out = []
    for d in dips:
        who = [r for r in kinds if r in (d.get("reviewers") or [])]
        out.append({
            "id": d["candidate_id"], "target": d.get("target", ""), "outcome_label": OUTCOME_LABEL.get(d.get("outcome"), ""),
            "reviewers": who, "n": len(who), "of": len(kinds),
            "n_sim": sum(r in sim_all for r in who), "of_sim": len(sim_all),
            "n_claude": sum(r in cl_all for r in who), "of_claude": len(cl_all),
        })
    return out


OUTCOME_ORDER = {"passed": 0, "flagged": 1, "rejected": 2}
MATCH_QUALIFIER = ("Each dip is this pipeline's own candidate, unconfirmed as an independent detection; the archive "
                   "match says the planet is already known, not that this run confirmed it.")


def _letter(i: int) -> str:
    """A, B, ... Z, AA, AB ...: a short label for the i-th marked window on the light curve."""
    out = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


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
    where = f" ({xm['fallback_from']})" if xm.get("fallback_from") else ""
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
  function send(m){ m.source = 'exoplan-docket'; m.dip = m.dip || selected(); try { P.postMessage(m, '*'); } catch (e) {} }
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
    var m = e.data; if (e.source !== P || !m || m.source !== 'exoplan-shell') return;
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


def app_data(run_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
             weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None,
             require_crossmatch: bool = False, targets_path: str | Path | None = DEFAULT_TARGETS,
             map_path: str | Path | None = DEFAULT_MAP, notable_path: str | Path | None = DEFAULT_NOTABLE,
             coverage_path: str | Path | None = DEFAULT_COVERAGE, examples_path: str | Path | None = DEFAULT_EXAMPLES,
             catalogue_path: str | Path | None = DEFAULT_CATALOGUE) -> dict:
    """Everything the shell shows, read from stored files only.

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
        from exoplan.calibrate import calibration_path

        calibrated = json.loads(Path(weights_path).read_text())
        weights_name = str(weights_path)
        if calibration_path(weights_path).exists():
            record = json.loads(calibration_path(weights_path).read_text())
            record_name = str(calibration_path(weights_path))
    # A weights entry may be a bare weight or a dict holding it with its rates.
    flat = {k: (v.get("weight") if isinstance(v, dict) else v) for k, v in (calibrated or {}).items()} if calibrated else None
    from exoplan.dashboard import _load_run

    run = _load_run(run_dir)
    feed = catalog.get("candidates") or []
    run_name = manifest.get("config_name") or run_dir.name
    cands = dock["candidates"]
    top = sorted(cands, key=lambda c: -c["snr"])[:5]
    crossmatch = dock.get("crossmatch") or {}
    comparison = (crossmatch.get("comparison") or {}).get("by_candidate") or {}
    per_signal: dict[str, int] = {}
    for c in cands:
        per_signal[c.get("signal_id", "")] = per_signal.get(c.get("signal_id", ""), 0) + 1

    def archive_match(cid: str) -> dict:
        cmp = comparison.get(cid) or {}
        name = cmp.get("consistent_with")
        hit = next((p for p in cmp.get("planets") or [] if p.get("pl_name") == name), {}) if name else {}
        return {"consistent_with": name, "dP_pct": hit.get("dP_pct"), "pl_orbper": hit.get("pl_orbper"),
                "archive_line": cmp.get("line", "")}

    top_rows = [{"id": c["candidate_id"], "target": c.get("target", ""), "depth_ppm": c["depth_ppm"], "snr": c["snr"],
                     "period_days": c.get("period_days"), "outcome": c["outcome"],
                     "outcome_label": OUTCOME_LABEL[c["outcome"]], "signal_id": c.get("signal_id", ""),
                     "signal_dips": per_signal.get(c.get("signal_id", ""), 1), **archive_match(c["candidate_id"])}
                    for c in top]
    sections = ([{"id": s, "label": label, "parent": None} for s, label in SECTIONS]
                + [{"id": s, "label": label, "parent": parent} for s, label, parent in SUBPAGES])
    hero = overview_hero(dock, top_rows)
    calib = {**calibration_plane(calibrated, record, dock["reviewers"]), "record_path": record_name}
    story = story_data(run_dir, dock, feed, calib, hero, targets_path=targets_path)
    galaxy = galaxy_data(map_path, notable_path, coverage_path=coverage_path, exoplan_star=story["star"]["name"] or "pi Men",
                         exoplan_planet=story.get("planet"), lead_dip=story.get("lead_dip"))
    return {
        "title": title,
        "sections": sections,
        "widgets": [{"id": w, "label": label} for w, label in WIDGETS],
        "default_layout": default_layout(),
        "default_size": DEFAULT_SIZE,
        "unconfirmed": UNCONFIRMED,
        "no_detection": NO_DETECTION,
        "no_stellar_radius": NO_STELLAR_RADIUS,
        "ratio_scale_max": RATIO_SCALE_MAX,
        "dossier_ids": [c["candidate_id"] for c in cands],
        "run": {
            "name": run_name, "dir": str(run_dir), "created_at": manifest.get("created_at", ""),
            "counts": manifest.get("counts", {}),
            "docket_counts": dock["counts"],
            "reviewer_kinds": dock["reviewers"],
            "top": top_rows,
        },
        "config": {
            "config_name": manifest.get("config_name", ""), "config_sha256": manifest.get("config_sha256", ""),
            "exoplan_version": manifest.get("exoplan_version", ""), "python": manifest.get("python", ""),
            "platform": manifest.get("platform", ""), "packages": manifest.get("packages", {}),
            "claude_prompt_version": manifest.get("claude_prompt_version", ""),
            "subject_days": manifest.get("subject_days"), "inputs": manifest.get("inputs", []),
            "skipped_reviewers": manifest.get("skipped_reviewers", []),
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
        "mission": {"panes": MISSION_PANES, "grids": MISSION_GRIDS},
        "catalogue": (cat := load_catalogue(catalogue_path)),
        "tic_names": tic_names(cat, [r["tic"] for r in feed], story["star"]),
        "catalogue_meta": catalogue_meta(cat, galaxy["methods"] if galaxy else None, galaxy["method_label"] if galaxy else None,
                                         {e["name"]: [e["ref"], e["ref_label"]] for e in (galaxy or {}).get("notable", [])},
                                         mentions((galaxy or {}).get("notable"), CHAPTERS, CHAPTER_PLANETS, story)),
        "galaxy_teaser": teaser_points(galaxy),
        "sky_geo": sky_geometry(story["star"]["ra_deg"], story["star"]["dec_deg"]),
        "deco": decoration(),
        "aliases": ROUTE_ALIASES,
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
        "attribution": ATTRIBUTION,
        "weights_path": weights_name,
        "docket_html": with_frame_bridge(docket_page(dock)),
        "fonts_css": FONTS_CSS, "frame_fonts_href": FRAME_FONTS_HREF,
    }


APP_CSS = """
/* The approved design: a pure black ground, frosted glass, hairlines, Geist with bold tight headlines and a
   grey second line, and system colours: blue for a known planet, yellow for open, red for rejected, cyan for
   the Sentinels, purple for the Probes, amber for the star. Dark first; a light variant uses the same names.
   The "space" panels (sky map, transit theatre, scatter, orbits) stay dark in both themes. */
:root{color-scheme:dark;
  --bg:#000;--bg-2:#0B0B0D;--bg-3:#161618;
  --glass:rgba(28,28,30,.55);--glass-2:rgba(28,28,30,.45);--panel:#1C1C1E;--panel-2:rgba(255,255,255,.06);
  --line:rgba(255,255,255,.08);--line-2:rgba(255,255,255,.14);--line-3:rgba(255,255,255,.24);
  --ink:#F5F5F7;--ink-2:#A1A1A6;--ink-3:#8E8E93;
  --blue:#0A84FF;--yellow:#FFD60A;--red:#FF453A;--sen:#64D2FF;--prb:#BF5AF2;--prb-ink:#D0A8FF;--star:#FFB340;--green:#30D158;
  --cyan:#64D2FF;--lime:#30D158;--amber:#FFB340;--coral:#FF6961;--magenta:#BF5AF2;
  --cyan-soft:rgba(100,210,255,.12);--lime-soft:rgba(48,209,88,.14);--amber-soft:rgba(255,179,64,.14);--coral-soft:rgba(255,69,58,.16);
  --seg-bg:#F5F5F7;--seg-ink:#000;--btn-bg:#0071E3;--btn-ink:#FFFFFF;
  --shadow:none;--gloss:none;
  --sans:"Geist",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"Geist Mono",ui-monospace,"SF Mono",Menlo,monospace;--display:var(--sans);
  --r:22px;--ease:cubic-bezier(.2,.8,.2,1);
  --paper:var(--bg);--rule:var(--line-2);--muted:var(--ink-3);--fit:var(--blue);--pass:var(--green);--flag:var(--yellow);--reject:var(--red);--sel:var(--panel-2);--side:var(--bg-2);
  --top:60px}
:root[data-theme="light"]{color-scheme:light;
  --bg:#F5F5F7;--bg-2:#FFFFFF;--bg-3:#E8E8ED;
  --glass:rgba(255,255,255,.72);--glass-2:rgba(255,255,255,.6);--panel:#FFFFFF;--panel-2:rgba(0,0,0,.05);
  --line:rgba(0,0,0,.08);--line-2:rgba(0,0,0,.14);--line-3:rgba(0,0,0,.26);
  --ink:#1D1D1F;--ink-2:#424245;--ink-3:#5E5E63;
  --blue:#0066CC;--yellow:#7A5600;--red:#C9001B;--sen:#006E99;--prb:#8944AB;--prb-ink:#8944AB;--star:#A05A00;--green:#1F7A35;
  --cyan:#0066CC;--lime:#1F7A35;--amber:#A05A00;--coral:#C9001B;--magenta:#8944AB;
  --cyan-soft:rgba(0,102,204,.1);--lime-soft:rgba(31,122,53,.12);--amber-soft:rgba(160,90,0,.12);--coral-soft:rgba(201,0,27,.1);
  --seg-bg:#1D1D1F;--seg-ink:#FFFFFF;--btn-bg:#0071E3;--btn-ink:#FFFFFF}
@media (prefers-color-scheme: light){:root[data-theme="system"]{color-scheme:light;
  --bg:#F5F5F7;--bg-2:#FFFFFF;--bg-3:#E8E8ED;
  --glass:rgba(255,255,255,.72);--glass-2:rgba(255,255,255,.6);--panel:#FFFFFF;--panel-2:rgba(0,0,0,.05);
  --line:rgba(0,0,0,.08);--line-2:rgba(0,0,0,.14);--line-3:rgba(0,0,0,.26);
  --ink:#1D1D1F;--ink-2:#424245;--ink-3:#5E5E63;
  --blue:#0066CC;--yellow:#7A5600;--red:#C9001B;--sen:#006E99;--prb:#8944AB;--prb-ink:#8944AB;--star:#A05A00;--green:#1F7A35;
  --cyan:#0066CC;--lime:#1F7A35;--amber:#A05A00;--coral:#C9001B;--magenta:#8944AB;
  --cyan-soft:rgba(0,102,204,.1);--lime-soft:rgba(31,122,53,.12);--amber-soft:rgba(160,90,0,.12);--coral-soft:rgba(201,0,27,.1);
  --seg-bg:#1D1D1F;--seg-ink:#FFFFFF;--btn-bg:#0071E3;--btn-ink:#FFFFFF}}
*{box-sizing:border-box}
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
/* decorative star field behind everything (dark themes only) */
.starfield{position:fixed;inset:0;width:100%;height:100%;z-index:-1;pointer-events:none}
:root[data-theme="light"] .starfield{display:none}
@media (prefers-color-scheme: light){:root[data-theme="system"] .starfield{display:none}}
/* the top bar: brand, the pill section switcher, the run, the theme control */
.topbar{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 18px;padding:8px clamp(16px,3vw,32px);background:color-mix(in oklab,var(--bg) 62%,transparent);-webkit-backdrop-filter:saturate(180%) blur(24px);backdrop-filter:saturate(180%) blur(24px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:9px;min-height:44px;padding:0 4px;color:var(--ink);text-decoration:none;font-weight:600;font-size:17px;letter-spacing:-.02em}
.brand:hover{color:var(--ink)}
.brand svg{width:22px;height:22px;flex:none}
.nav ul{list-style:none;margin:0;display:flex;gap:2px;padding:3px;border-radius:999px;background:var(--panel-2);border:1px solid var(--line)}
.nav a{display:flex;align-items:center;min-height:36px;padding:0 16px;border-radius:999px;color:var(--ink-2);text-decoration:none;font-size:13px;font-weight:500;white-space:nowrap;transition:background-color .25s var(--ease),color .25s var(--ease)}
.nav a:hover{color:var(--ink)}
.nav a[aria-current="page"]{background:var(--seg-bg);color:var(--seg-ink)}
.topmeta{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--ink-3)}
.topmeta .cur{white-space:nowrap}
main{min-width:0;padding:36px clamp(16px,3vw,40px) 56px}
main:focus{outline:none}
.route{display:grid;gap:22px;min-width:0;max-width:1280px;margin:0 auto;animation:rise .45s var(--ease) both}
.route[hidden]{display:none}
.route>header{display:grid;gap:8px;padding-bottom:4px}
.route>header .eyebrow{margin:0;font-size:15px;font-weight:500;color:var(--star);display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.route>header .eyebrow .idx{display:none}
.route>header .eyebrow .parent{color:var(--ink-3);font-weight:400}
.route>header .eyebrow .parent a{color:var(--ink-3)}
.route h1:focus{outline:none}
.route>header p{margin:0;color:var(--ink-2);max-width:72ch;font-size:clamp(15px,1.2vw,17px);line-height:1.5}
.route>header .lead-h,.headline{margin:0;font-weight:700;font-size:clamp(34px,4.4vw,60px);line-height:1.02;letter-spacing:-.045em;color:var(--ink);max-width:22ch;text-wrap:balance}
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
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;font:500 13px/1.2 var(--sans);color:var(--ink);background:var(--panel-2);border:1px solid var(--line);border-radius:999px;padding:6px 14px;cursor:pointer;min-height:34px;text-decoration:none;transition:background-color .25s var(--ease),color .25s var(--ease),border-color .25s var(--ease),transform .25s var(--ease)}
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
.space{border-radius:28px;border:1px solid rgba(255,255,255,.08);color:#F5F5F7;overflow:hidden;position:relative;min-width:0;--ink:#F5F5F7;--ink-2:#A1A1A6;--ink-3:#8E8E93;--line:rgba(255,255,255,.08);--cyan:#64D2FF}
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
.twinkle{animation:twinkle 6s ease-in-out infinite}
.twinkle2{animation:twinkle 9s ease-in-out infinite 2s}
.orbit{animation:orbit 60s linear infinite}
.orbitfast{animation:orbit 14s linear infinite}
.orbitslow{animation:orbit 90s linear infinite reverse}
.clouds{animation:drift 90s linear infinite}
.pulse{animation:pulse 3.2s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
.breathe{animation:breathe 7s ease-in-out infinite}
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
.skymap{flex:999 1 640px;padding:18px;background:radial-gradient(120% 120% at 50% 0%,#0B1220 0%,#000 60%)}
.skymap svg{display:block;width:100%;height:auto}
.skycov{display:grid;gap:8px;padding:14px 16px;border-radius:var(--r)}
.skycov p{margin:0;font-size:13px;color:var(--ink-2)}
.skycov a{display:inline-flex;align-items:center;min-height:44px}
.theatre .mxstage{padding:0 12px 4px}
.theatre .mxctl,.theatre .mxbadges{padding:0 2px}
.skypin{position:absolute;min-height:44px;padding:10px 14px;border-radius:16px;border:1px solid rgba(255,255,255,.14);background:rgba(28,28,30,.72);-webkit-backdrop-filter:blur(24px);backdrop-filter:blur(24px);color:#F5F5F7;text-decoration:none;line-height:1.35;font-size:12px}
.skypin b{font-size:15px;font-weight:600;display:block}
.skypin span{display:block;color:#A1A1A6}
.skypin em{font-style:normal;color:#64D2FF}
.skynote{position:absolute;right:20px;bottom:14px;font-size:11px;color:#8E8E93;text-align:right;max-width:60%}
.skymark.on{cursor:zoom-in}
.skylinks .skyzoom{min-height:44px;color:#F5F5F7;border-color:rgba(255,255,255,.18)}
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
.scatter button{position:absolute;width:44px;height:44px;margin:-22px 0 0 -22px;border:0;padding:0;background:transparent;border-radius:50%;cursor:pointer}
.scatter button i{position:absolute;left:50%;top:50%;width:var(--s);height:var(--s);margin:calc(var(--s) / -2) 0 0 calc(var(--s) / -2);border-radius:50%;background:var(--c);box-shadow:0 0 var(--g) var(--c)}
.scatter button[aria-pressed="true"] i{outline:2px solid #fff;outline-offset:2px}
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
.toplist .st .short,.phonehedge{display:none}
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
.themebtn{min-height:44px;min-width:44px;justify-content:center;gap:8px;font-size:13px;padding:0 12px}
.themebtn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5}
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
  table.bench tr{display:block;border-top:1px solid var(--line);padding:6px 0}table.bench tr:first-child{border-top:0}table.bench th,table.bench td{display:block;width:auto;border:0;padding:2px 12px}
  .topbar{padding:6px 12px;gap:4px 8px}
  .topbar .nav{order:3;flex:1 1 100%;min-width:0}
  .nav ul{overflow-x:auto;scrollbar-width:none;justify-content:space-between}
  .nav ul::-webkit-scrollbar{display:none}
  /* The strip scrolls sideways: its right edge fades so it reads as scrollable. */
  .nav ul{-webkit-mask-image:linear-gradient(to right,#000 calc(100% - 36px),transparent);mask-image:linear-gradient(to right,#000 calc(100% - 36px),transparent)}
  .nav a{min-height:44px;padding:0 12px;font-size:13px}
  .topmeta .cur{display:none}
  .themebtn .themelbl{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
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
  .toplist .unc{display:none}
  .phonehedge{display:inline}
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
APP_CSS += GALAXY_CSS + METHODS_CSS + CATALOGUE_CSS + LEARN_CSS + MISSION_CSS

ICONS = {
    "overview": '<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/>',
    "candidates": '<path d="M3 2h7l3 3v9H3z"/><path d="M5 8h6M5 11h6"/>',
    "discoveries": '<path d="M2 12l4-5 3 3 5-7"/>',
    "planets": '<circle cx="8" cy="8" r="4"/><path d="M1.5 10.5c2 1.5 11 -2.5 13 -5"/>',
    "panel": '<circle cx="5" cy="6" r="2"/><circle cx="11" cy="6" r="2"/><path d="M1.5 13c.5-2.5 6.5-2.5 7 0M7.5 13c.5-2.5 6.5-2.5 7 0"/>',
    "runs": '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
}

APP_JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const $ = (s, e=document) => e.querySelector(s);
const $$ = (s, e=document) => Array.from(e.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// ---------- one object model: every planet and star has one canonical page ----------
// The slug rule is catalogue.slugify's (the tests check every catalogue name gives its stored slug).
const objSlug = n => String(n).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'x';
const planetHref = n => '#/planet/' + objSlug(n);
const starHref = n => '#/star/' + objSlug(n);
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
const say = msg => { const a = $('#announce'); a.textContent = ''; setTimeout(() => { a.textContent = msg; }, 30); };
const isClaude = k => k === 'claude' || k === 'claude_code';
const OUTCOME_SHORT = {passed: 'passed', flagged: 'flagged', rejected: 'rejected'};
// The panel's display names (the Sentinels and the Probes); ids stay in the data and show beside the names.
const NAME = id => ((D.reviewer_names || {})[id] || {}).name || id;
const nameWithId = id => `${esc(NAME(id))} <span class="mono idtag" title="reviewer id">${esc(id)}</span>`;
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const kindTag = k => k === 'simulated' ? '<span class="tag sim">Probe · not a person</span>' : isClaude(k) ? `<span class="tag cl">Sentinel · Claude</span>` : `<span class="tag">${esc(k || 'unknown')}</span>`;
function niceTicks(lo, hi, n){
  if (!(hi > lo)) return [lo];
  const raw = (hi-lo)/Math.max(1,n), mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo/step)*step; v <= hi + 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}

// ---------- history ----------
// A change the viewer makes (a dip picked, a sort or filter changed) is a new history entry, so the
// browser's Back returns to the previous view. Rewrites that only tidy the address (the layout on
// load, a section scrolled into view) replace the current entry. Returns false when the browser
// refuses (a sandboxed or srcdoc context), so the caller can say so.
function setHash(h, push){
  if (location.hash === h) return true;
  try { if (push) history.pushState(null, '', h); else history.replaceState(null, '', h); return true; } catch (e) { return false; }
}

// ---------- links and dates ----------
const DIP_IDS = new Set(D.dossier_ids);
const dipHref = (id, section) => `#/candidates?dip=${encodeURIComponent(id)}${section ? '&section=' + section : ''}`;
// A dip identifier: a link to its dossier in the Docket when the run has one, plain text otherwise.
const dipLink = id => DIP_IDS.has(id) ? `<a class="dip" href="${dipHref(id)}" title="Open ${esc(id)} in the Docket">${esc(id)}</a>` : `<span class="dip" title="${esc(id)} (no dossier in this run)">${esc(id)}</span>`;
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
const LAYOUT_KEY = 'exoplan-app:layout:' + D.title;
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
const layoutLink = () => location.href.split('#')[0] + '#/overview?layout=' + encodeLayout(layout);
function syncLayoutURL(){
  const h = location.hash;
  if (h && !h.startsWith('#/overview')) return;
  setHash('#/overview?layout=' + encodeLayout(layout), false);  /* a tidy-up of the address: replace, not push */
}

// ---------- overview ----------
function widgetBody(id){
  function topBody(r){
    // Group the top dips by signal so repeat transits of one signal read as one signal, not several discoveries.
    const groups = [];
    for (const x of r.top){ let g = groups.find(g => g.signal_id === x.signal_id); if (!g){ g = {signal_id: x.signal_id, dips: []}; groups.push(g); } g.dips.push(x); }
    return `<ul class="toplist">${groups.map(g => {
      const f = g.dips[0], n = g.dips.length, xm = g.dips.find(x => x.consistent_with);
      const head = `<div><b>${esc(f.target)}</b> <span class="muted">· signal ${f.period_days ? 'P ' + fmt(f.period_days,3) + ' d' : 'with no period (one transit)'} · ${n} of the top dips${f.signal_dips > n ? `, ${f.signal_dips} dips in the run` : ''}<span class="phonehedge"> · each a ${esc(D.unconfirmed)}</span></span></div>`;
      const note = xm ? `<p class="note">Archive cross-match: ${n === 1 ? 'this dip is' : `these ${n} dips are`} consistent with <b>${esc(xm.consistent_with)}</b>, a published planet${xm.dP_pct !== null && xm.dP_pct !== undefined ? ` (period difference ${fmt(xm.dP_pct,2)}%)` : ''}. ${n === 1 ? 'It is a transit' : 'They are repeat transits'} of one known planet, not ${n === 1 ? 'a discovery' : n + ' discoveries'}. ${esc(D.no_detection)}</p>` : '';
      // One line per dip. On a phone the status shows as its short word and the hedge moves to the
      // signal line above, so each row stays one 44 px line; the full words stay for screen readers.
      return `<li>${head}${note}<ul>${g.dips.map(x => `<li class="toprow">${dipLink(x.id)}<span class="mono">SNR ${fmt(x.snr,1)}</span><span class="mono">${fmt(x.depth_ppm,0)} ppm</span><span class="st"><span class="long">${esc(x.outcome_label)}</span><span class="short" aria-hidden="true">${esc(OUTCOME_SHORT[x.outcome] || x.outcome_label)}</span></span><span class="muted unc">${esc(D.unconfirmed)}</span></li>`).join('')}</ul></li>`;
    }).join('')}</ul>`;
  }
  const r = D.run, c = r.counts || {}, dc = r.docket_counts || {};
  if (id === 'kpis'){
    const kinds = Object.values(r.reviewer_kinds), sim = kinds.filter(k => k === 'simulated').length, cl = kinds.filter(isClaude).length;
    const tiles = [[c.subjects, 'subjects'], [c.classifications, 'reviews'], [dc.signals, 'signals'], [dc.dips, 'dips'], [dc.passed, 'signals passed vetting'], [dc.flagged, 'signals flagged for review']];
    return `<div class="kpis">${tiles.map(([v,l]) => `<div class="kpi"><b>${esc(v ?? '–')}</b><span>${esc(l)}</span></div>`).join('')}</div>
      <p class="muted" style="margin:0;font-size:12px">Run ${esc(r.name)}, ${when(r.created_at)}. ${esc(dc.rejected ?? 0)} signal${dc.rejected===1?'':'s'} rejected by vetting. The light curves are measured (${esc((D.config.inputs[0]||{}).source || 'stored input')}); the reviews come from ${plural(cl, 'Sentinel')} and ${plural(sim, 'Probe')}, no people.</p>`;
  }
  if (id === 'discoveries'){
    const f = D.catalog.candidates, nNew = f.filter(x => x.status === 'new_candidate').length, nKnown = f.filter(x => x.status === 'known_toi').length;
    if (!D.catalog.path) return '<p class="empty">No discovery catalogue was given to this build.</p>';
    return `<div><span class="big">${f.length}</span> <span class="muted">feed entries</span></div>
      <p style="margin:0">${nKnown} match a known TOI period · ${nNew} new candidate${nNew===1?'':'s'} · ${esc(D.catalog.targets_reviewed)} targets reviewed</p>
      <p style="margin:0">${UNC} every entry</p>
      <p class="muted" style="margin:0;font-size:12px">Catalogue updated ${when(D.catalog.updated)}.</p>`;
  }
  if (id === 'runs'){
    const runs = D.catalog.runs.slice(-5).reverse();
    if (!runs.length) return '<p class="empty">No discovery runs are stored in the catalogue.</p>';
    return `<ul class="runlist">${runs.map(x => `<li><b>${when(x.time)}</b><span>${(x.targets||[]).length} targets · ${esc(x.new ?? '–')} new · ${esc(x.known ?? '–')} known · ${(x.errors||[]).length} error${(x.errors||[]).length===1?'':'s'}</span></li>`).join('')}</ul>
      <p class="muted" style="margin:0;font-size:12px">This page's run: ${esc(r.name)}, ${when(r.created_at)}.</p>`;
  }
  if (id === 'top'){
    if (!r.top.length) return '<p class="empty">This run stored no candidates.</p>';
    return `${topBody(r)}
      <p class="muted" style="margin:0;font-size:12px">The run's dips with the highest stored SNR, grouped by signal. Every one is a ${esc(D.unconfirmed)}. Select a dip to open its dossier.</p>`;
  }
  return '';
}
const WIDGET_LINK = {kpis:'transit', discoveries:'explorer', runs:'runs', top:'transit'};
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
    <a class="wopen" href="#/${WIDGET_LINK[x.id]}">Open ${esc(D.sections.find(s => s.id === WIDGET_LINK[x.id]).label)}</a></section>`).join('')
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
  const back = $('#route-overview ' + focusSel); if (back) back.focus();
}
$('#route-overview').addEventListener('click', e => { const b = e.target.closest('button[data-act]'); if (b) layoutAction(b.dataset.act, b.dataset.id, b.dataset.size); });
$('#ownlayout').addEventListener('click', () => { layout = ownLayout.map(x => ({...x})); sharedView = false; renderOverview(); $('#copylayout').focus(); say('Showing your own layout.'); });
$('#copylayout').addEventListener('click', async () => {
  const url = layoutLink(), box = $('#copyfallback');
  try { await navigator.clipboard.writeText(url); box.hidden = true; say('Link to this layout copied.'); $('#copystate').textContent = 'Link copied.'; }
  catch (e) { box.hidden = false; box.value = url; box.focus(); box.select(); say('Copy the selected link to share this layout.'); $('#copystate').textContent = ''; }
  setTimeout(() => { $('#copystate').textContent = ''; }, 4000);
});
$('#resetlayout').addEventListener('click', () => { layout = normaliseLayout(null, WIDGET_IDS, D.default_size); saveLayout(); renderOverview(); $('#resetlayout').focus(); say('Layout reset: every widget shown in the default order and size.'); });

// ---------- candidates (the Docket) ----------
const DOCKET_SECTIONS = ['strip', 'signal', 'ctx', 'cmp', 'ledger', 'rev'];
// The Docket reads a dip id from its own location hash on load, so the frame loads the Docket page
// from a blob URL with the dip as that hash. (A srcdoc frame cannot carry a hash; it is the fallback.)
// The shell's copy of the Docket carries a small bridge: it reports the selected dip and the section
// in view by postMessage, and takes the same from the shell, so the address bar follows the frame.
const BLOCKED_TEXT = 'The dossier could not load in this view.';
let docketBlob = null;
const LOADING_TEXT = 'Loading the Docket…';
const frame = {ready: false, mode: null, dip: null, section: null, pending: null, crossOrigin: false, timer: null, gen: 0,
  frameURLFailed: false, shellURLFailed: false};
// The Docket copy with the self-hosted font stylesheet at an absolute address (a blob URL has no base).
function frameHTML(){
  let href = D.fonts_css; try { href = new URL(D.fonts_css, location.href).href; } catch (e) { /* keep relative */ }
  return D.docket_html.split(D.frame_fonts_href).join(href);
}
function docketURL(dip){
  try { if (!docketBlob) docketBlob = URL.createObjectURL(new Blob([frameHTML()], {type: 'text/html'})); } catch (e) { docketBlob = null; }
  return docketBlob ? docketBlob + (dip ? '#' + encodeURIComponent(dip) : '') : null;
}
const fullHref = dip => '../docket/' + (dip ? '#' + encodeURIComponent(dip) : '');
function setFullHrefs(dip){ for (const a of $$('#fullpage, #topfull, #blockedlink')) a.href = fullHref(dip); }
// Keep the shell URL and the full-page links on the dip (and section) the frame shows.
function syncShellURL(){
  setFullHrefs(frame.dip);
  const pick = $('#dippick'); if (pick && frame.dip && pick.value !== frame.dip) pick.value = frame.dip;
  if (current !== 'candidates') return;
  const h = '#/candidates' + (frame.dip ? `?dip=${encodeURIComponent(frame.dip)}${frame.section ? '&section=' + frame.section : ''}` : '');
  if (location.hash !== h){
    // A new dip is a new history entry (Back returns to the last dip); a section change only replaces.
    const shown = (parseHash(location.hash) || {params: new URLSearchParams()}).params.get('dip');
    const push = !!frame.dip && !!shown && shown !== frame.dip;
    frame.shellURLFailed = !setHash(h, push);
    if (frame.ready) readyStatus();
  }
}
function tellFrame(dip, section){
  if (dip) { frame.dip = dip; frame.section = section || null; }
  else if (section) frame.section = section;
  try { $('#docketframe').contentWindow.postMessage({source: 'exoplan-shell', dip, section}, '*'); } catch (e) { /* frame gone */ }
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
  if (frame.mode === 'blob') loadDocket(frame.dip, frame.section, 'srcdoc'); else showBlocked();
}
function onFrameReady(m){
  frame.ready = true; clearTimeout(frame.timer);
  const f = $('#docketframe'); f.hidden = false; f.classList.remove('waiting'); $('#frameblocked').hidden = true;
  try { void f.contentWindow.document.body; frame.crossOrigin = false; } catch (e) { frame.crossOrigin = true; }
  readyStatus();
  const p = frame.pending; frame.pending = null;
  if (p && ((p.dip && p.dip !== m.dip) || p.section)) tellFrame(p.dip, p.section);
  else { frame.dip = m.dip || frame.dip; syncShellURL(); }
  try { $('#docketframe').contentWindow.postMessage({source: 'exoplan-shell', theme: currentTheme()}, '*'); } catch (e) { /* frame gone */ }
}
window.addEventListener('message', e => {
  const f = $('#docketframe'), m = e.data;
  if (!f || e.source !== f.contentWindow || !m || m.source !== 'exoplan-docket') return;
  if (m.urlFailed) frame.frameURLFailed = true;
  if (m.kind === 'ready'){ onFrameReady(m); return; }
  if (!frame.ready) return;  // the Docket's own first pick, before the shell's dip is applied
  if (m.kind === 'dip' && m.dip){ if (m.dip !== frame.dip){ frame.section = null; if (frame.notice){ frame.notice = ''; readyStatus(); } } frame.dip = m.dip; }
  else if (m.kind === 'section'){ frame.section = DOCKET_SECTIONS.includes(m.section) ? m.section : null; if (m.dip) frame.dip = m.dip; }
  syncShellURL();
  if (m.urlFailed) readyStatus();
});
function loadDocket(dip, section, mode){
  const f = $('#docketframe'), url = mode === 'srcdoc' ? null : docketURL(dip), gen = ++frame.gen;
  Object.assign(frame, {ready: false, mode: url ? 'blob' : 'srcdoc', dip, section: section || null, pending: {dip, section: section || null},
    frameURLFailed: false});
  // Not shown until it reports ready: an empty bordered box would sit under the loading line.
  f.hidden = false; f.classList.add('waiting'); $('#frameblocked').hidden = true;
  frameStatus(LOADING_TEXT);
  clearTimeout(frame.timer);
  // A frame that never reports ready did not load (blocked by frame-src, say): try srcdoc, then say so.
  // The srcdoc copy needs no fetch, so its wait is shorter.
  frame.timer = setTimeout(() => frameLoadFailed(gen), url ? 3000 : 1500);
  const onload = () => {
    let blank = false;
    try { blank = f.contentWindow.location.href === 'about:blank'; } catch (e) { /* cross-origin: an error page or file:// */ }
    if (blank) { f.addEventListener('load', onload, {once: true}); return; }
    setTimeout(() => frameLoadFailed(gen), 800);
  };
  f.addEventListener('load', onload, {once: true});
  if (url){ f.removeAttribute('srcdoc'); f.src = url; } else { f.removeAttribute('src'); f.srcdoc = frameHTML(); }
}
function openDip(dip, section){
  const f = $('#docketframe');
  if (dip && !DIP_IDS.has(dip)){
    // An unknown dip id: say so, and rewrite the address to the lead dip (replace, not a new entry).
    const lead = leadDip();
    frame.notice = `No dip ${dip} in run ${D.run.name}; showing the lead dip${lead ? ' ' + lead : ''}.`;
    say(frame.notice); dip = lead;
    setHash('#/candidates' + (lead ? '?dip=' + encodeURIComponent(lead) : ''), false);
    if (frame.ready) readyStatus(); else frameStatus(f.dataset.loaded ? LOADING_TEXT : '');
  } else if (dip) frame.notice = '';
  if (!DOCKET_SECTIONS.includes(section)) section = null;
  if (!f.dataset.loaded){ f.dataset.loaded = '1'; loadDocket(dip, section); setFullHrefs(dip); }
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
  sel.innerHTML = D.hero.windows.map(w => `<option value="${esc(w.id)}">${esc(w.letter)} · ${esc(w.outcome)} · ${esc(w.id)}</option>`).join('');
  if (frame.dip) sel.value = frame.dip;
}
function renderCandidates(){ renderDipPicker(); /* the frame loads in openDip, with the dip from the URL */ }

// ---------- discoveries (the feed) ----------
const disc = {sort: 'snr', dir: -1, filter: 'all'};
// The Feed's sort and filter live in the URL (#/explorer?sort=depth&filter=new) like the Overview
// layout, and in localStorage as the viewer's default. A view opened from a link is shown for that
// view only; storage is written only when the viewer changes the sort or the filter.
const FEED_SORTS = D.feed_view.sorts, FEED_FILTERS = D.feed_view.filters, FEED_NUMERIC = D.feed_view.numeric;
const FEED_KEY = 'exoplan-app:feed:' + D.title;
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
  ['candidate_id', 'dip', x => x.candidate_id, x => dipLink(x.candidate_id)],
  ['t_center', 'mid-time', x => x.t_center, x => `${fmt(x.t_center,3)}<small>${esc(x.time_unit)}</small>`],
  ['period_days', 'period (d)', x => x.period_days, x => fmt(x.period_days,4)],
  ['depth_ppm', 'depth (ppm)', x => x.depth_ppm, x => fmt(x.depth_ppm,0)],
  ['snr', 'SNR', x => x.snr, x => fmt(x.snr,1)],
  ['status', 'status', x => x.status, x => `${esc(D.status_label[x.status] || x.status)}<small>${esc(D.unconfirmed)}</small>`],
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
  return `<ol class="feedcards">${rows.map(x => `<li><div class="fc1">${dipLink(x.candidate_id)}<span class="fcst">${esc(D.status_label[x.status] || x.status)}</span></div><div class="fc2 mono">${ticLink(x.tic)} · P ${fmt(x.period_days,3)} d · ${fmt(x.depth_ppm,0)} ppm · SNR ${fmt(x.snr,1)}</div><div class="fc3">${esc(D.unconfirmed)} · mid-time ${fmt(x.t_center,2)} ${esc(x.time_unit)}</div></li>`).join('')}</ol>`;
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
      <div>${dipLink(e.id)} ${UNC}</div>
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
      <span>${dipLink(a.id)}<small class="muted" style="display:block;font-size:11px">${esc(a.target)} · ${esc(a.outcome_label)} · ${esc(D.unconfirmed)}</small></span>
      <span><b>${a.n} of ${a.of} reviewers</b> marked it: ${a.n_claude} of ${plural(a.of_claude, 'Sentinel')}, ${a.n_sim} of ${plural(a.of_sim, 'Probe')}<small class="muted" style="display:block;font-size:11px">${a.reviewers.map(r => `<span title="reviewer id ${esc(r)}">${esc(NAME(r))}</span>`).join(', ') || 'none'}</small></span>
      <a href="${dipHref(a.id, 'ledger')}">Verdict ledger</a></li>`).join('')}</ul>` : '<p class="empty">The run stored no dips.</p>';
  $('#panelcards').innerHTML = D.panel.length ? D.panel.map(r => `<article class="card"><h2>${esc(NAME(r.id))} <span class="sub mono" title="reviewer id">${esc(r.id)}</span></h2>
    <p style="margin:6px 0 0">${kindTag(r.kind)}</p>
    <p class="muted" style="margin:6px 0 0;font-size:13px">${r.kind === 'simulated' ? 'A Probe: a deterministic matched-filter detector that marks dips above an SNR threshold in the light curve. It is not a person.' : isClaude(r.kind) ? 'A Sentinel: a Claude model (Anthropic) that reads the plotted light curve and marks dips. It is not a person.' : ''}</p>
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
  const pts = D.calibration.points, cl = pts.filter(p => isClaude(p.kind)), sim = pts.filter(p => p.kind === 'simulated');
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
  for (const p of pts){ let g = groups.find(g => g.fpr === p.fpr && g.tpr === p.tpr && g.kind === (isClaude(p.kind) ? 'claude' : p.kind)); if (!g){ g = {fpr: p.fpr, tpr: p.tpr, kind: isClaude(p.kind) ? 'claude' : p.kind, items: []}; groups.push(g); } g.items.push(p); }
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
  const cl = pts.filter(p => isClaude(p.kind));
  if (cl.length) tx(svg, X(0.97), Y(0.08), `Sentinels: ${fmtN(cl[0])} only`, 'end', 'samplelbl');
  if (pts.some(p => p.kind === 'simulated')) tx(svg, X(0.97), Y(0.08) + 14, `Probes: ${fmtN(pts.find(p => p.kind === 'simulated'))}`, 'end');
  for (const g of groups){
    const r = R(g.items[0].weight), cx = X(g.fpr), cy = Y(g.tpr);
    const c = el('circle', {cx, cy, r, class: g.kind === 'claude' ? 'pt cl' : 'pt sim'}, svg);
    el('title', {}, c).textContent = g.items.map(p => `${NAME(p.id)} (id ${p.id}; ${p.kind === 'simulated' ? 'Probe, not a person' : isClaude(p.kind) ? 'Sentinel, Claude' : p.kind}): TPR ${fmt(p.tpr,2)}, FPR ${fmt(p.fpr,2)}, weight ${fmt(p.weight,2)}, ${fmtN(p)}`).join('\n');
    const word = g.kind === 'claude' ? 'Sentinel' : g.kind === 'simulated' ? 'Probe' : g.kind;
    tx(svg, cx + r + 6, cy + 4, `${plural(g.items.length, word)} · w ${fmt(g.items[0].weight,2)}`, 'start', 'lbl');
  }
}
function renderCalibration(){
  const C = D.calibration;
  $('#calsample').innerHTML = C.points.some(p => p.n_injected) ? calSample() : 'The sample size is not stored with these weights.';
  calPlane($('#calplane'));
  const kindWord = k => k === 'simulated' ? 'Probe · not a person' : isClaude(k) ? 'Sentinel · Claude' : esc(k);
  $('#caltable').innerHTML = C.points.length ? `<table><caption class="sr">Calibration rates and weights per reviewer, as stored</caption><thead><tr><th scope="col">reviewer</th><th scope="col">kind</th><th scope="col" class="num">recall (TPR)</th><th scope="col" class="num">false alarms (FPR)</th><th scope="col" class="num">weight</th><th scope="col">sample</th></tr></thead><tbody>${C.points.map(p => `<tr><th scope="row">${nameWithId(p.id)}</th><td>${kindWord(p.kind)}</td><td class="num">${fmt(p.tpr,2)}</td><td class="num">${fmt(p.fpr,2)}</td><td class="num">${fmt(p.weight,2)}${p.consistent === false ? '<small>not max(TPR − FPR, floor)</small>' : ''}</td><td>${esc(fmtN(p))}</td></tr>`).join('')}</tbody></table>` : '';
  // On a phone the same rows read as one card per reviewer (the table is hidden there, the cards elsewhere).
  $('#calcards').innerHTML = C.points.map(p => `<dl class="kv calcard"><dt>reviewer</dt><dd><b>${nameWithId(p.id)}</b></dd><dt>kind</dt><dd>${kindWord(p.kind)}</dd><dt>recall (TPR)</dt><dd>${fmt(p.tpr,2)}</dd><dt>false alarms (FPR)</dt><dd>${fmt(p.fpr,2)}</dd><dt>weight</dt><dd>${fmt(p.weight,2)}${p.consistent === false ? ' (not max(TPR − FPR, floor))' : ''}</dd><dt>sample</dt><dd>${esc(fmtN(p))}</dd></dl>`).join('');
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
      ${(x.tracebacks||[]).length ? `<details><summary>${plural(x.tracebacks.length, 'traceback')} (verbatim)</summary>${x.tracebacks.map(t => `<pre class="err">${esc(t)}</pre>`).join('')}</details>` : ''}</li>`; }).join('')}</ol>` : '<p class="empty">No discovery runs are stored in the catalogue.</p>';
  const c = D.config;
  const pk = Object.entries(c.packages || {});
  $('#runconfig').innerHTML = `<dl class="kv">
    <dt>config name</dt><dd>${esc(c.config_name)}</dd>
    <dt>config hash (sha256)</dt><dd>${esc(c.config_sha256)}</dd>
    <dt>created</dt><dd>${when(D.run.created_at)}</dd>
    <dt>exoplan</dt><dd>${esc(c.exoplan_version)}</dd>
    <dt>python</dt><dd>${esc(c.python)}</dd>
    <dt>platform</dt><dd>${esc(c.platform)}</dd>
    <dt>Claude prompt version</dt><dd>${esc(c.claude_prompt_version || 'not stored')}</dd>
    <dt>subject length</dt><dd>${esc(c.subject_days)} d</dd>
    <dt>skipped reviewers</dt><dd>${(c.skipped_reviewers||[]).length ? esc(c.skipped_reviewers.join(', ')) : 'none'}</dd>
    <dt>archive cross-match</dt><dd>${xmConfig(D.crossmatch_info)}</dd>
    ${pk.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
  </dl>
  <h3 style="margin-top:14px">Measured inputs</h3>
  ${(c.inputs||[]).map(x => `<p style="margin:4px 0 0" class="mono">${esc(Object.entries(x).map(([k,v]) => k + ' ' + v).join(' · '))}</p>`).join('') || '<p class="empty">No inputs stored.</p>'}`;
  $('#catconfig').innerHTML = D.catalog.path ? `<dl class="kv"><dt>catalogue</dt><dd>${esc(D.catalog.path)}</dd><dt>config</dt><dd>${esc(D.catalog.config)}</dd><dt>config hash (sha256)</dt><dd>${esc(D.catalog.config_sha256)}</dd><dt>updated</dt><dd>${when(D.catalog.updated)}</dd><dt>targets reviewed</dt><dd>${esc(D.catalog.targets_reviewed)}</dd></dl>` : '<p class="empty">No discovery catalogue was given to this build.</p>';
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
const DIPS = S.dips, DIP_BY = Object.fromEntries(DIPS.map(d => [d.id, d]));
const STC = {known: 'var(--blue)', open: 'var(--yellow)', rejected: 'var(--red)'};
const STC_SPACE = S.colours;  // the same colours as hex, for the space panels (dark in both themes)
const fmtSigned = (x, d) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d);
const dotPath = (pts, X, Y) => pts.map(p => `M${X(p[0]).toFixed(1)} ${Y(p[1]).toFixed(1)}h0`).join('');
const transitHref = id => `#/transit?dip=${encodeURIComponent(id)}`;
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
const COVL = (D.galaxy_meta && D.galaxy_meta.layers) || [];
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
  $('#skydips').innerHTML = shown.length ? shown.map(d => `<a class="dipitem" href="${transitHref(d.id)}" style="--c:${STC[d.status]}"><i></i><b>${esc(d.time_unit)} ${tval(d.t)}</b><span class="st">${esc(d.status_label)}</span><span class="sub">${fmt(d.depth_ppm, 0)} ppm · ${fmt(d.duration_hours, 2)} h · ${d.who.sentinels === d.who.of_sentinels && d.who.probes === d.who.of_probes ? `all ${d.who.of_sentinels + d.who.of_probes} reviewers` : `${d.who.probes} Probes, ${d.who.sentinels} Sentinels`} · ${esc(D.unconfirmed)}</span></a>`).join('')
    : '<p class="empty" style="margin:12px">No dips match.</p>';
  skyTimeline();
}
function skyTimeline(box = $('#skytimeline'), capEl = $('#skytlcap')){
  if (!box) return;
  const subs = D.hero.subjects; if (!subs.length){ box.innerHTML = '<p class="empty">No light curve is stored.</p>'; return; }
  const a = subs[0].start, b = subs[subs.length - 1].end, W = 1000, H = 84;
  const [lo, hi] = [-700, 400], X = t => (t - a) / (b - a) * W, Y = v => 6 + (hi - Math.max(lo, Math.min(hi, v))) / (hi - lo) * 56;
  const pts = subs.map(s => s.t.map((t, i) => `M${X(t).toFixed(1)} ${Y(s.ppm[i]).toFixed(1)}h0`).join('')).join('');
  let ticks = '';
  for (const d of DIPS){ const on = skyShown(d), x = X(d.t).toFixed(1); ticks += `<path d="M${x} 66 V82" stroke="${on ? STC[d.status] : 'var(--line-2)'}" stroke-width="${on ? 2.5 : 1.5}" stroke-linecap="round"><title>${esc(d.time_unit)} ${tval(d.t)} · ${esc(d.status_label)}</title></path>`; }
  capEl.innerHTML = `<span>${esc(D.hero.time_unit)} ${fmt(a, 1)}</span><span>Stored brightness over the run, ${D.hero.n_points.toLocaleString('en-GB')} points; ticks: the dips shown above</span><span>${fmt(b, 1)}</span>`;
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Light curve of run ${esc(D.run.name)}: ${D.hero.n_points} stored points from ${esc(D.hero.time_unit)} ${fmt(a, 1)} to ${fmt(b, 1)}, with ${DIPS.filter(skyShown).length} of ${DIPS.length} dips ticked."><path d="${pts}" stroke="var(--ink)" stroke-width="1.1" stroke-linecap="round" opacity=".45"/>${ticks}</svg>`;
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
  const known = d.status === 'known', k = d.ratio || 0;
  const star = typeof MX !== 'undefined' && MX && S.planet ? MX.examples[S.planet] : null;
  const model = (d.model || []).map(p => [p[0], p[1]]);
  let p, bNote;
  if (known && star){ p = Object.assign({name: S.planet}, star); bNote = `impact parameter ${star.impact_parameter != null ? 'as stored' : 'illustrative'}`; }
  else {
    // Rp/R★ = √depth; the duration sets a/R★ for an illustrative period (the lead signal's), b = 0 (not fitted).
    const P = (D.hero.lead && D.hero.lead.period_days) || 6, T14 = Math.max(0.02, (d.duration_hours || 2) / 24), ars = P / (Math.PI * T14) * (1 + k);
    const st = star || {};
    p = {name: 'a planet this deep', star_teff: st.star_teff || 5772, star_radius: st.star_radius || 1, radius: st.star_radius ? k * st.star_radius * 6.957e8 / 7.1492e7 : null,
      orbital_period: P, semi_major_axis: ars * (st.star_radius || 1) * 6.957e8 / 1.495978707e11, impact_parameter: 0};
    bNote = 'impact parameter illustrative (b = 0), not the fit\'s';
  }
  $('#txcap').textContent = known && star ? `${S.planet}, from stored values` : 'what a planet this deep would cast';
  $('#txfoot').textContent = (known && star
      ? `${S.planet} and its star as ${MX.source} stores them (fetched ${MX.fetched_at.slice(0, 10)}): the line is a limb-darkened model from those values, not a fit to this dip; ${bNote}. The match says the planet is already known; it does not confirm the dip.`
      : `If it were a planet: Rp/R★ = √depth = ${fmt(k, 4)}, from the stored depth ${fmt(d.depth_ppm, 0)} ppm; the star is the target as the catalogue stores it; orbit and period illustrative; ${bNote}.`)
    + ` Dots: the ${d.pts.length} stored flux values within ${fmt(d.half * 24, 1)} hours of mid-time (${esc(d.time_unit)} ${fmt(d.t, 3)}). ${model.length ? 'Dashed: the limb-darkened fit stored for this dip.' : 'No transit fit is stored for this dip.'} The star's surface texture is decorative.`;
  const {st} = mxSystemView($('#txsysfig'), p, {dip: {pts: d.pts, model}, on: current === 'transit', caption: false});
  if (!(known && star)){ st.opt.sys.bSrc = 'illustrative'; mxKick(st); }
  // The canonical pages for the planet (when the dip matches one) and the star.
  $('#txlinks').innerHTML = (known && S.planet ? objLink('planet', S.planet, S.planet + ' ›') : '') + (S.star.name ? objLink('star', S.star.name, S.star.name + ' ›') : '');
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
  if (!q) return `<div class="quote"><p style="font-size:14px">No Sentinel rationale is stored for this subject.</p></div>`;
  return `<div class="quote"><div class="who"><b title="reviewer id ${esc(q.id)}">${esc(q.name)}</b><span>${q.confidence === null || q.confidence === undefined ? 'confidence not stored' : 'confidence ' + fmt(q.confidence, 1)}</span></div>
    <p>“${esc(q.text)}”</p><small>Its stored rationale for subject ${esc(d.subject_label || d.subject)} (${esc(d.time_unit)} ${fmt(d.subject_start, 1)} to ${fmt(d.subject_end, 1)}), one per subject, not per dip. It ${q.marked ? 'marked' : 'did not mark'} this dip. A Sentinel is a Claude model, not a person.</small></div>`;
}
function orbitHTML(d){
  const L = D.hero.lead; if (!L || d.phase === null || d.phase === undefined) return '';
  const ang = Math.PI / 2 + d.phase * 2 * Math.PI, px = 100 + 80 * Math.cos(ang), py = 100 + 80 * Math.sin(ang);
  const who = S.planet ? `${esc(S.planet)}'s orbit` : "the lead signal's orbit";
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
  const i = DIPS.indexOf(d), prev = DIPS[(i + DIPS.length - 1) % DIPS.length], next = DIPS[(i + 1) % DIPS.length], inCmp = txs.cmp.includes(d.id);
  $('#txkicker').textContent = d.status_label; $('#txkicker').style.color = STC[d.status];
  $('#h-transit').innerHTML = `${esc(d.time_unit)} ${tval(d.t)}<span class="sr">, dip ${esc(d.letter)}, ${esc(d.status_label)}</span>`;
  $('#txsub').textContent = `${fmt(d.depth_ppm, 0)} ppm · ${fmt(d.duration_hours, 2)} hours · SNR ${fmt(d.snr, 1)} · ${D.unconfirmed}`;
  $('#txnav').innerHTML = `<a class="roundbtn" href="${transitHref(prev.id)}" aria-label="Previous dip, ${esc(prev.time_unit)} ${tval(prev.t)}">‹</a><a class="roundbtn" href="${transitHref(next.id)}" aria-label="Next dip, ${esc(next.time_unit)} ${tval(next.t)}">›</a><button type="button" class="cmpbtn" id="cmptoggle" aria-pressed="${inCmp}">${inCmp ? 'In compare' : 'Add to compare'}</button>`;
  $('#txchips').innerHTML = DIPS.map(x => `<a href="${transitHref(x.id)}" aria-current="${x.id === d.id}" style="--c:${STC[x.status]}" title="${esc(x.id)} · ${esc(x.status_label)}"><i></i>${esc(x.letter)} · ${tval(x.t)}</a>`).join('');
  // Keep the current dip's chip in view in the sideways-scrolling row (without moving the page).
  const row = $('#txchips'), chip = $('#txchips a[aria-current="true"]');
  if (row && chip) row.scrollLeft = chip.offsetLeft - (row.clientWidth - chip.offsetWidth) / 2;
  txTheatre(d);
  $('#txscore').innerHTML = `<div class="top"><span>Panel score (weighted share that marked it)</span><b>${fmt(d.score, 2)}</b></div><div class="bar" style="--c:${STC[d.status]}"><i style="width:${Math.round((d.score || 0) * 100)}%"></i></div><p>${esc(d.verdict)}</p>`;
  $('#txlanes').innerHTML = lanesHTML(d);
  $('#txquote').innerHTML = quoteHTML(d);
  $('#txorbit').innerHTML = orbitHTML(d) + trayHTML();
  $('#txcase').innerHTML = `<a href="#/candidates?dip=${encodeURIComponent(d.id)}">Open the full case file ›</a><span>The Docket: every check, the stored measurements, the verdict ledger and the archive provenance.</span>`;
  $('#txarchive').textContent = d.archive_line ? `Archive comparison: ${d.archive_line}. ${D.no_detection}` : '';
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
  if (!EXF.length){ $('#exscatter').innerHTML = '<p class="empty">No discovery catalogue was given to this build.</p>'; return; }
  const nNew = EXF.filter(f => f.status === 'new_candidate').length, nKnown = EXF.length - nNew;
  $('#exstars').innerHTML = TICS.map(t => `<button type="button" class="pill" data-tic="${t}" aria-pressed="${ex.stars[t]}" style="--c:${starColour(t)}"><i></i>TIC ${esc(t)}</button>`).join('');
  $('#exstatus').innerHTML = `<button type="button" data-f="fNew" aria-pressed="${ex.fNew}">New ${nNew}</button><button type="button" data-f="fKnown" aria-pressed="${ex.fKnown}">Known TOI ${nKnown}</button>`;
  const snrs = [0, 7, 8, 9, 10].filter(v => v === 0 || EXF.some(f => f.snr >= v));
  $('#exsnr').innerHTML = snrs.map(v => `<button type="button" data-snr="${v}" aria-pressed="${ex.snrMin === v}">${v ? 'SNR ' + v + '+' : 'Any SNR'}</button>`).join('');
  const per = EXF.map(f => f.period_days).filter(p => p > 0), dep = EXF.map(f => f.depth_ppm).filter(x => x > 0);
  const p0 = Math.max(0.5, Math.floor(Math.min(...per))), p1 = Math.ceil(Math.max(...per) + 0.5), d1 = Math.ceil(Math.max(...dep) / 500) * 500;
  const X = p => (Math.log(p) - Math.log(p0)) / (Math.log(p1) - Math.log(p0)) * 100, Yp = dp => (1 - dp / d1) * 100;
  const pticks = [1, 2, 3, 5, 7, 10, 20].filter(p => p >= p0 && p <= p1), dticks = []; for (let v = 0; v <= d1; v += 500) dticks.push(v);
  const grid = pticks.map(p => `M${X(p).toFixed(2)} 0V52`).join('') + dticks.map(v => `M0 ${(Yp(v) * .52).toFixed(2)}H100`).join('');
  const shown = EXF.filter(exShown);
  $('#excount').textContent = `${shown.length} of ${EXF.length} shown`;
  $('#exscatter').innerHTML = `<svg viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true"><path d="${grid}" stroke="rgba(255,255,255,.07)" stroke-width="1" vector-effect="non-scaling-stroke"/></svg>`
    + shown.map(f => { const s = Math.round(7 + Math.max(0, (f.snr || 7) - 7) * 1.4), c = f.status === 'new_candidate' ? '#FFD60A' : starColour(f.tic);
      return `<button type="button" data-i="${f.i}" aria-pressed="${f.i === ex.sel}" aria-label="TIC ${esc(f.tic)}, period ${fmt(f.period_days, 3)} days, depth ${fmt(f.depth_ppm, 0)} ppm, SNR ${fmt(f.snr, 1)}, ${esc(D.status_label[f.status] || f.status)}, ${esc(D.unconfirmed)}" style="left:${X(f.period_days).toFixed(2)}%;top:${Yp(f.depth_ppm).toFixed(2)}%;--s:${s}px;--c:${c};--g:${Math.round(Math.max(0, (f.snr || 6) - 6) * 2)}px"><i></i></button>`; }).join('')
    + pticks.map(p => `<span class="ax" style="left:${X(p).toFixed(1)}%;bottom:-18px;transform:translateX(-50%)">${p}${p === pticks[0] ? ' d' : ''}</span>`).join('')
    + `<span class="ax" style="left:0;top:-2px">${d1} ppm</span><span class="ax" style="left:0;bottom:2px">0</span>`;
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
    <p class="small">TESS sectors ${esc(f.sectors || 'not stored')}. Dip <span class="mono">${esc(f.id)}</span>. ${isNew ? '' : 'A TOI match compares a stored period with archive values. '}${esc(D.no_detection)} ${esc(_cap(D.unconfirmed))}.</p>`;
}
const _cap = s => s.charAt(0).toUpperCase() + s.slice(1);
$('#route-explorer').addEventListener('click', e => {
  const t = e.target.closest('button[data-tic]'), f = e.target.closest('#exstatus button[data-f]'), n = e.target.closest('button[data-snr]'), p = e.target.closest('#exscatter button[data-i]');
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
const RENDER = {overview: renderOverview, sky: renderSky, galaxy: renderGalaxy, methods: renderMethods, mission: renderMission, catalogue: renderCatalogue, planet: () => {}, star: () => {}, transit: renderTransit, explorer: () => { renderExplorer(); renderDiscoveries(); },
  sentinels: () => { renderSentinels(); renderPanel(); }, candidates: renderCandidates, planets: renderPlanets, runs: renderRuns};
const rendered = new Set();
const ROUTES = D.sections.map(s => s.id);
const SECTION = Object.fromEntries(D.sections.map(s => [s.id, s]));
// Only hashes that start with "#/" are routes; anything else (such as the skip link's #content) is left to the browser.
// An old address (#/discoveries, #/panel ...) is an alias: it opens the section that replaced it.
function parseHash(h){
  if (!h || h === '#' || h === '#/') return {route: 'overview', params: new URLSearchParams()};
  if (!h.startsWith('#/')) return null;
  const body = h.slice(2), q = body.indexOf('?');
  let route = q < 0 ? body : body.slice(0, q);
  try { route = decodeURIComponent(route); } catch (e) { /* keep as typed */ }
  const query = q < 0 ? '' : body.slice(q + 1), alias = D.aliases[route];
  // A planet or star page: #/planet/<slug>, #/star/<slug>.
  const pm = /^(planet|star)\/([a-z0-9-]{1,120})$/.exec(route);
  if (pm){ const params = new URLSearchParams(query); params.set('id', pm[2]); return {route: pm[1], params}; }
  if (alias) return {route: alias, alias: route, query, params: new URLSearchParams(query)};
  return {route: ROUTES.includes(route) ? route : 'overview', unknown: ROUTES.includes(route) ? null : route,
          params: new URLSearchParams(query)};
}
let current = null;
function show(r, moveFocus){
  for (const id of ROUTES) $('#route-' + id).hidden = id !== r;
  const top = SECTION[r].parent || r;
  $$('.nav a').forEach(a => { if (a.dataset.route === top) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const label = SECTION[r].label;
  document.title = `${label} · ${D.title}`;
  document.body.dataset.route = r;
  $('#curlabel').textContent = SECTION[r].parent ? `${SECTION[top].label} · ${label}` : label;
  if (r === 'overview') renderOverview();
  else if (!rendered.has(r)){ RENDER[r](); rendered.add(r); }
  else if (r === 'explorer') renderDiscCharts(false);
  if (moveFocus){ const h = $('#route-' + r + ' h1'); if (h) h.focus({preventScroll: true}); window.scrollTo(0, 0); }
  if (r === 'candidates') fitFrame();
  missionShown(r === 'mission');
  gxShown(gxWanted());
  mxShown(r === 'methods');
  mxIntroRoute(r);
  txSysShown(r === 'transit');
  plShown(r);
}
function go(p, moveFocus){
  // An old address: rewrite it to the section that replaced it, keeping its query (a replace, not a new entry).
  if (p.alias){ setHash('#/' + p.route + (p.query ? '?' + p.query : ''), false); }
  // An unknown section: rewrite the address to the Overview, and say so.
  if (p.unknown){ setHash('#/overview', false); say(`No section ${p.unknown}; showing the Overview.`); p = {route: 'overview', params: new URLSearchParams()}; }
  const changed = p.route !== current;
  if (p.route === 'overview'){
    if (p.params.has('layout')){
      layout = decodeLayout(p.params.get('layout'), WIDGET_IDS, D.default_size);
      sharedView = encodeLayout(layout) !== encodeLayout(ownLayout);
    } else { layout = ownLayout.map(x => ({...x})); sharedView = false; }
  }
  if (p.route === 'sky'){
    applySky(decodeSkyView(p.params));
    applySkyLayers(decodeLayers(p.params));
    if (rendered.has('sky')) renderSky();
  }
  if (p.route === 'galaxy' && GXM) applyGalaxy(decodeGalaxyView(p.params));
  if (p.route === 'catalogue' && CTM) applyCatalogue(decodeCatView(p.params));
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
  show(p.route, moveFocus && changed);
  if (p.route === 'explorer') syncFeedURL();
  if (p.route === 'sky') syncSkyURL(false);
  if (p.route === 'galaxy' && GXM) syncGalaxyURL(false);
  if (p.route === 'methods') mxShowChapter(p.params.get('ch'));
  if (p.route === 'catalogue' && CTM) syncCatURL(false);
  if (p.route === 'planet') plShow(p.params.get('id') || '');
  if (p.route === 'star') stShow(p.params.get('id') || '');
  if (p.route === 'mission'){ applyMission(decodeMission(p.params)); gxShown(gxWanted()); syncMissionURL(false); }
  learnVisit(p);
  if (p.route === 'transit') openTransit(p.params.get('dip'));
  if (p.route === 'candidates') openDip(p.params.get('dip'), p.params.get('section'));
}
// Back and Forward: hashchange for typed or linked hashes, popstate for entries made by pushState.
// Either way the shell re-reads the hash and pushes the dip (or the Feed view) into the view.
function onNavigate(){ const p = parseHash(location.hash); if (!p) return; const gsd = $('#gsearch'); if (gsd && gsd.open) gsd.close(); go(p, true); }
window.addEventListener('hashchange', onNavigate);
window.addEventListener('popstate', onNavigate);
$('.skip').addEventListener('click', e => { e.preventDefault(); const c = $('#content'); c.focus({preventScroll: true}); c.scrollIntoView(); });
// The sticky top bar's height (it wraps to two rows on a phone) sets --top, which the case file's frame uses.
function measureTop(){ const t = $('.topbar'); if (t) document.documentElement.style.setProperty('--top', Math.ceil(t.getBoundingClientRect().height) + 'px'); }
measureTop();
if (window.ResizeObserver) new ResizeObserver(measureTop).observe($('.topbar'));
let rt = null;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (!$('#route-explorer').hidden) renderDiscCharts(false); resizeCalibration(); fitFrame(); }, 120); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { measureTop(); fitFrame(); });  // web fonts can rewrap the header
// ---------- theme: dark (the default), light or system ----------
// The design is dark first. The choice is stored as exoplan-theme (when storage is allowed); the head
// script applies it before first paint. The Docket frame is told too, so it follows.
const THEMES = ['dark', 'light', 'system'], THEME_NAME = {system: 'System', light: 'Light', dark: 'Dark (default)'};
function currentTheme(){ const t = document.documentElement.getAttribute('data-theme'); return THEMES.includes(t) ? t : 'dark'; }
function applyTheme(t){
  document.documentElement.setAttribute('data-theme', t);
  try { const s = getStorage(); if (s){ if (t === 'dark') s.removeItem('exoplan-theme'); else s.setItem('exoplan-theme', t); } } catch (e) { /* storage blocked: the theme lasts for this visit */ }
  for (const b of $$('[data-theme-toggle]')){ b.setAttribute('aria-label', `Colour theme: ${THEME_NAME[t].toLowerCase()}. Change theme`); b.querySelector('.themelbl').textContent = THEME_NAME[t]; }
  try { $('#docketframe').contentWindow.postMessage({source: 'exoplan-shell', theme: t}, '*'); } catch (e) { /* no frame yet */ }
}
for (const b of $$('[data-theme-toggle]')) b.addEventListener('click', () => { const t = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]; applyTheme(t); say(`Theme: ${THEME_NAME[t]}.`); });
applyTheme(currentTheme());
$('#dippick').addEventListener('change', e => { location.hash = dipHref(e.target.value); });
go(parseHash(location.hash) || {route: 'overview', params: new URLSearchParams()}, false);
"""
# The Galaxy section's code sits ahead of the router, which calls it.
APP_JS = APP_JS.replace("// ---------- router ----------\n", GALAXY_JS + METHODS_JS + CATALOGUE_JS + LEARN_JS + MISSION_JS + "// ---------- router ----------\n", 1)


# Before first paint: apply the stored theme choice (system, light or dark), so the page never flashes.
THEME_KEY = "exoplan-theme"
THEME_HEAD_JS = ("(function(){var t='dark';try{var s=localStorage.getItem('" + THEME_KEY + "');"
                 "if(s==='light'||s==='system')t=s;}catch(e){}document.documentElement.setAttribute('data-theme',t);})();")
THEME_BUTTON = ('<button class="btn themebtn" type="button" data-theme-toggle aria-label="Colour theme: dark (default). Change theme">'
                '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 2.5v11" /><path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor"/></svg>'
                '<span class="themelbl">Dark (default)</span></button>')


def _nav(sections: list[dict]) -> str:
    items = "".join(f'<li><a href="#/{s["id"]}" data-route="{s["id"]}">{html.escape(s["label"])}</a></li>'
                    for s in sections if not s.get("parent"))
    return f'<nav class="nav" aria-label="Sections"><ul>{items}</ul></nav>'


BRAND_SVG = ('<svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="10" fill="none" stroke="currentColor" '
             'stroke-opacity=".5"/><circle cx="11" cy="11" r="3.5" fill="#FFB340"/><circle cx="19" cy="7.5" r="1.8" fill="currentColor"/></svg>')


def _eyebrow(label: str, parent: tuple[str, str] | None = None) -> str:
    up = f'<span class="parent"><a href="#/{parent[0]}">{html.escape(parent[1])}</a> ›</span>' if parent else ""
    return f'<p class="eyebrow">{up}{html.escape(label)}</p>'


def _honest(data: dict) -> str:
    e = html.escape
    h = data["hero"]
    dc = data["run"].get("docket_counts") or {}
    cal = data.get("calibration") or {}
    n_inj = max([p.get("n_injected") or 0 for p in cal.get("points") or []] or [0])
    weights = f" Their weights rest on calibration with {n_inj} planted and {n_inj} empty light curves each, so they are rough." if n_inj else ""
    match = f" The match with {e(h['match'])} says the planet is already known, not that this run confirmed it." if h.get("match") else ""
    return f"""<section class="honest" aria-labelledby="h-honest">
        <h2 id="h-honest">What this page does not claim</h2>
        <ul>
          <li><b>No confirmed planet.</b> Every dip, signal and feed entry here is a {UNCONFIRMED}. Passing vetting is not a confirmation.{match}</li>
          <li><b>No planet sizes.</b> No stellar radius is stored, so a depth gives only a planet-to-star radius ratio. The Planets page shows the working.</li>
          <li><b>No people on the panel.</b> The panel is the Sentinels and the Probes: {e(panel_phrase(dc.get('claude', 0), dc.get('simulated', 0), dc.get('other', 0)))}. {e(ATTRIBUTION)}{e(weights)}</li>
          <li><b>{e(NO_DETECTION.split(". ")[0])}.</b> {e(NO_DETECTION.split(". ", 1)[1])} A TOI or archive match compares a stored period with published values.</li>
          <li><b>No image of the planet.</b> The planet on the Overview is an artist's impression; the field stars on the sky map are decorative.</li>
        </ul>
      </section>"""


def _planet_figure(deco: dict) -> str:
    """The Overview's artist's impression: a planet's limb lit by its star. Decorative, and labelled so."""
    return f"""<figure class="planetfig">
        <svg viewBox="0 0 1440 560" role="img" aria-label="Artist's impression of a planet's limb lit by its star. No image of pi Men c exists." style="display:block;width:100%;height:auto">
          <defs>
            <radialGradient id="pBody" cx="35%" cy="15%" r="85%"><stop offset="0" stop-color="#3C5E8C"/><stop offset=".35" stop-color="#1D3352"/><stop offset=".7" stop-color="#0A1222"/><stop offset="1" stop-color="#000"/></radialGradient>
            <radialGradient id="pAtm" cx="50%" cy="100%" r="62%"><stop offset=".86" stop-color="#64D2FF" stop-opacity="0"/><stop offset=".92" stop-color="#64D2FF" stop-opacity=".55"/><stop offset=".97" stop-color="#0A84FF" stop-opacity=".18"/><stop offset="1" stop-color="#0A84FF" stop-opacity="0"/></radialGradient>
            <radialGradient id="sGlow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#FFF4D6"/><stop offset=".08" stop-color="#FFD28A" stop-opacity=".9"/><stop offset=".3" stop-color="#FF9F2E" stop-opacity=".18"/><stop offset="1" stop-color="#FF9F2E" stop-opacity="0"/></radialGradient>
            <filter id="soft"><feGaussianBlur stdDeviation="9"/></filter>
            <clipPath id="pClip"><circle cx="720" cy="1380" r="1000"/></clipPath>
          </defs>
          <path class="twinkle" d="{deco['bright']}" stroke="#E8EEFF" stroke-width="1.6" stroke-linecap="round"/>
          <circle class="breathe" cx="1170" cy="120" r="230" fill="url(#sGlow)"/>
          <circle cx="1170" cy="120" r="9" fill="#FFFBEF"/>
          <circle cx="720" cy="1380" r="1060" fill="url(#pAtm)"/>
          <circle cx="720" cy="1380" r="1000" fill="url(#pBody)"/>
          <g clip-path="url(#pClip)"><g class="clouds" filter="url(#soft)" opacity=".35"><path d="{deco['bands']}" stroke="#BFD6F2" stroke-width="16" fill="none" stroke-linecap="round"/></g></g>
          <path d="M-280 1380 A1000 1000 0 0 1 1720 1380" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.2"/>
        </svg>
        <figcaption>Artist's impression. No image of pi Men c exists.</figcaption>
      </figure>"""


def _overview(data: dict, with_view: bool = True) -> str:
    e = html.escape
    st = data["story"]
    lead = st.get("lead_dip")
    planet = st.get("planet")
    watch = (f'<a class="btn ghost" href="#/transit?dip={e(lead)}">Watch it find {e(planet)} ›</a>' if planet and lead
             else (f'<a class="btn ghost" href="#/transit?dip={e(lead)}">Watch the lead dip ›</a>' if lead else ""))
    proof = "".join(f'<div><b style="color:{p["colour"]}">{e(p["big"])}</b><span>{e(p["text"])}</span></div>' for p in st["proof"])
    return f"""<header class="launch">
        <p class="kick">exoplan</p>
        <h1 id="h-overview" tabindex="-1">The sky, reviewed.</h1>
        <p class="sub">A calibrated panel of Sentinels (Claude) and Probes (deterministic detectors) reads every light curve. Every verdict, explained. Nothing called a planet until it is one.</p>
        <div class="ctas"><a class="btn primary" href="#/sky">Explore the sky</a>{watch}</div>
      </header>
      {_planet_figure(data["deco"])}
      <div class="proof" role="list" aria-label="What this run shows">{proof.replace('<div>', '<div role="listitem">')}</div>
      {teaser_html(data.get("galaxy"), data.get("galaxy_teaser"))}
      {_honest(data)}
      {learn_card() if with_view else ""}
      {_view_head() if with_view else ""}"""


BENCHMARK_JSON = "docs/results/benchmark_real_tois.json"


def _load_benchmark(path: str | Path = BENCHMARK_JSON) -> dict | None:
    """The real-TOI benchmark's summary (scripts/benchmark_real_tois.py), without the per-star rows."""
    if not Path(path).exists():
        return None
    d = json.loads(Path(path).read_text())
    keep = ("generated_at", "sample", "panel", "stars_run", "summary", "sentinels", "feed_implication", "clipping", "code_provenance")
    out = {k: d[k] for k in keep if k in d}
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
    rows = [("Headline: planets recovered on searchable stars (CP/KP TOIs, a vetted dip on the published ephemeris)", pct(h["completeness"])),
            ("Planets recovered over all CP/KP stars (no 2-minute data counts as missed)", pct(h.get("completeness_all_stars"))),
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
    clip = (b.get("clipping") or {}).get("held_out")
    clipnote = ""
    if clip:
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
                   + ('. A new_candidate on the feed is more likely noise than a signal. Proposed fix, not yet applied: require the signal '
                      'in each of the two sectors reviewed and a stricter FAP, chosen on the tuning half and checked once on the held-out half.'
                      if imp["bad"] else '. False alarms alone account for less than half of that rate.') + '</p>')
    return (f'<section class="card bench" aria-labelledby="h-bench" style="display:grid;gap:8px"><h2 id="h-bench">Measured on real TOIs</h2>{verdict}'
            f'<p class="note" style="margin:0"><b>Measured on a stated benchmark, not discoveries.</b> {s["counts"]["positive"]} confirmed or known planets '
            f'(CP/KP), {s["counts"]["fp"]} false positives and {s["counts"]["fa"]} false alarms from the TOI table (fetched {e(s["fetched_at"][:10])}, seed {s["seed"]}), '
            f'one TOI per star; held-out half shown. Panel: {e(b["panel"])}.</p>'
            f'<div class="tablewrap" role="region" aria-label="Benchmark results"><table class="bench"><tbody>{body}</tbody></table></div>{clipnote}'
            f'<p class="muted" style="margin:0;font-size:12px">Full results: docs/results/benchmark_real_tois.md. TFOPWG dispositions are the reference, not ground truth for every TOI.</p></section>')


def _view_head() -> str:
    return """<div class="secthead"><h2 id="h-view">Your view</h2><p>Each widget's header can hide it, move it or set its size. Your changes are kept in this browser as your default when storage is allowed. Copy link to this layout shares it; a shared layout shows for that view only and never replaces the recipient's default.</p></div>"""


def _sky(data: dict) -> str:
    e = html.escape
    st, geo, h = data["story"], data["sky_geo"], data["hero"]
    star = st["star"]
    pin = ""
    if geo.get("x") is not None:
        bl = (geo["x"] + 460) / 920 * 100 + 3
        bt = (geo["y"] + 235) / 470 * 100 - 34
        lead = st.get("lead_dip")
        known = f"{e(st['planet'])} · known planet" if st.get("planet") else f"{len(st['dips'])} dips · {UNCONFIRMED}"
        pin = (f'<a class="skypin" href="#/transit?dip={e(lead or "")}" style="left:{bl:.1f}%;top:{bt:.1f}%" '
               f'title="{e(star["name"])} placed from SIMBAD (ICRS J2000): RA {star["ra_deg"]:.2f}°, Dec {star["dec_deg"]:.2f}°">'
               f'<b>{e(star["name"])}</b><span>{known}</span><em>Open ›</em></a>')
        zoom = f' data-zoom="{e(st["planet"])}"' if st.get("planet") else ""
        marker = (f'<g class="skymark"{zoom}><circle class="pulse" cx="{geo["x"]}" cy="{geo["y"]}" r="22" fill="url(#pmg)"/>'
                  f'<circle cx="{geo["x"]}" cy="{geo["y"]}" r="10" fill="none" stroke="#64D2FF" stroke-width=".8"/>'
                  f'<circle class="skydot" cx="{geo["x"]}" cy="{geo["y"]}" r="3.2" fill="#FFFFFF"/></g>')
        where = (f"{e(star['name'])} at RA {star['ra_deg']:.2f}°, Dec {star['dec_deg']:.2f}° ({e(star['source'])})")
    else:
        marker, where = "", "The target's sky position is not stored, so it is not plotted."
    placed = f'{e(star["name"])} placed from SIMBAD (ICRS J2000) · ' if geo.get("x") is not None else "target not plotted (no position stored) · "
    # The canonical pages for the run's star and its known planet.
    links = "".join(obj_link(k, n, f"{n} ›") for k, n in (("star", star.get("name")), ("planet", st.get("planet"))) if n)
    if st.get("planet") and geo.get("x") is not None:
        links += (f'<button class="btn skyzoom" type="button" data-zoom="{e(st["planet"])}" hidden>'
                  f'Zoom into the {e(st["planet"])} system ›</button>')
    links = f'<div class="pllinks skylinks">{links}</div>' if links else ""
    t1, t2 = st["sky_title"]
    return f"""<header class="headrow">
        <div>{_eyebrow("Sky")}<h1 class="lead-h" id="h-sky" tabindex="-1">{e(t1)}<br><span class="grey">{e(t2)}</span></h1></div>
        <div class="chips" id="skychips" role="group" aria-label="Show dips by status"></div>
      </header>
      <p class="muted" style="margin:0;max-width:80ch">{e(h["lede"])} {e(h["qualifier"])} {e(h["archive"])}</p>
      <div class="row2">
        <section class="space skymap" aria-labelledby="h-skymap">
          <h2 id="h-skymap" class="sr">Sky map</h2>
          <svg viewBox="-460 -235 920 470" role="img" aria-label="All-sky map (Mollweide). {where}. Field stars are decorative; the feed's stars are not plotted because their positions are not stored.">
            <defs><radialGradient id="pmg"><stop offset="0" stop-color="#64D2FF" stop-opacity=".9"/><stop offset="1" stop-color="#64D2FF" stop-opacity="0"/></radialGradient></defs>
            <ellipse rx="452" ry="226" fill="rgba(255,255,255,.015)" stroke="rgba(255,255,255,.14)" stroke-width=".8"/>
            <path d="{geo['grat']}" stroke="rgba(255,255,255,.06)" stroke-width=".8" fill="none"/>
            <path class="twinkle" d="{geo['stars']}" stroke="#E8EEFF" stroke-width="1.1" stroke-linecap="round"/>
            {sky_layers_svg(data.get("coverage"))}
            <path d="{geo['ecl']}" stroke="#FFB340" stroke-width=".9" fill="none" stroke-dasharray="2 6" opacity=".7"/>
            {marker}
          </svg>
          {pin}
          <p class="skynote">Field stars decorative · feed stars not plotted (positions not stored) · {placed}dashed: the ecliptic</p>
          {links}
        </section>
        <aside class="glass dipsbox" aria-labelledby="h-skydips">
          <div class="dhead"><b id="h-skydips">Dips</b><span class="muted" id="skycount"></span></div>
          <div class="segctl" id="skyrev" role="group" aria-label="Who marked it"></div>
          <div id="skydips"></div>
        </aside>
      </div>
      {_sky_coverage(data)}
      <section class="glass runline" aria-labelledby="h-skytl">
        <h2 id="h-skytl" class="sr">The run's light curve</h2>
        <div class="cap" id="skytlcap"></div>
        <div id="skytimeline"></div>
      </section>"""


def _sky_coverage(data: dict) -> str:
    cov = data.get("coverage")
    if not cov:
        return ""
    f = cov["fractions"]
    return (f'<section class="glass skycov" aria-label="Survey coverage">{coverage_chips(cov, "sky")}<p>Survey coverage: TESS has observed {f["tess"] * 100:.1f}% of the sky '
            f'(sectors 1–{cov["tess_last_sector"]}); {f["unmapped"] * 100:.1f}% has never been in a TESS, Kepler or K2 footprint. '
            f'Shading shows where surveys looked, not where planets are. <a href="#/galaxy">Figures and sources in the Galaxy ›</a></p></section>')


def _transit(data: dict) -> str:
    return f"""<header class="headrow">
        <div><p class="eyebrow" id="txkicker"></p><h1 class="lead-h" id="h-transit" tabindex="-1"></h1><p id="txsub"></p></div>
        <div style="display:flex;align-items:center;gap:8px" id="txnav"></div>
      </header>
      <p class="txnotice" id="txnotice" role="status" hidden></p>
      <nav class="dipchips" id="txchips" aria-label="Dips"></nav>
      <div class="row2">
        <section class="space theatre" id="txtheatre" aria-label="Transit theatre">
          <div class="cap"><span>The transit, played back</span><span id="txcap"></span></div>
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
      <p class="casefile" id="txcase"></p>
      <p class="small" id="txarchive"></p>
      <p class="small">Every dip here is a {UNCONFIRMED}. Stored values only: the points, marks, scores, flags and words are as the run stored them.</p>"""


def _explorer(data: dict) -> str:
    e = html.escape
    feed = data["catalog"]["candidates"]
    stars = len({r["tic"] for r in feed})
    n_new = sum(1 for r in feed if r.get("status") == "new_candidate")
    t1 = f"{len(feed)} signals. {stars} star{'s' if stars != 1 else ''}." if feed else "No discovery feed in this build."
    t2 = f"{n_new} at no known TOI period. All unconfirmed." if feed else ""
    return f"""<header class="headrow">
        <div>{_eyebrow("Explorer")}<h1 class="lead-h" id="h-explorer" tabindex="-1">{e(t1)}<br><span class="grey">{e(t2)}</span></h1></div>
        <div class="filters">
          <div class="chips" id="exstars" role="group" aria-label="Stars"></div>
          <div><div class="segctl" id="exstatus" role="group" aria-label="Status"></div><div class="segctl" id="exsnr" role="group" aria-label="Minimum SNR"></div></div>
        </div>
      </header>
      <div class="row2">
        <section class="space scatterbox" aria-labelledby="h-scatter">
          <div class="cap"><span id="h-scatter">Depth against period · period on a log scale</span><span id="excount"></span></div>
          <div class="scatter" id="exscatter"></div>
          <p class="foot">Each point a feed entry; size and glow follow SNR; yellow: no known TOI period. {e(NO_DETECTION)} Every entry is a {UNCONFIRMED}.</p>
        </section>
        <aside class="glass selpanel" id="exsel" aria-label="Selected signal"></aside>
      </div>
      <p class="casefile"><a href="#/planets">Radius ratios by star ›</a><span>What each depth would imply, if it were a planet; the stellar-radius limitation is stated there.</span></p>"""


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


def app_page(data: dict) -> str:
    """The shell as one self-contained HTML page."""
    title = html.escape(data["title"])
    run = data["run"]
    rule = data["feed_rule"]
    data = {**data, "methods": methods_meta(data["examples"], data.get("galaxy"), data["story"], data.get("coverage"))}
    payload = json.dumps({k: v for k, v in data.items() if k not in ("galaxy", "coverage", "examples", "catalogue", "benchmark")}).replace("</", "<\\/")
    galaxy_payload = ""  # the map's arrays are a separate file (galaxy_json), fetched when the Galaxy opens
    unc = html.escape(UNCONFIRMED)
    nodet = html.escape(NO_DETECTION)
    feed = data["catalog"]["candidates"]
    flabel = html.escape(feed_label(feed))
    n_known = sum(1 for r in feed if r.get("status") == "known_toi")
    description = (f"exoplan run {run['name']}: {data['hero']['headline']} Every dip is a {UNCONFIRMED}; "
                   f"stored values only.")
    xm_targets = ", ".join(html.escape(str(t)) for t in data.get("crossmatch_targets") or []) or "no star"
    deco = data["deco"]
    return f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{html.escape(description)}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: light)">
<link rel="icon" href="data:,">
<script>{THEME_HEAD_JS}</script>
<link rel="stylesheet" href="{FONTS_CSS}">
<style>{APP_CSS}</style></head>
<body>
<svg class="starfield" aria-hidden="true" viewBox="0 0 1440 1100" preserveAspectRatio="xMidYMid slice"><path class="twinkle" d="{deco['dust']}" stroke="#FFFFFF" stroke-width="1" stroke-linecap="round" opacity=".5"/><path class="twinkle2" d="{deco['bright']}" stroke="#E8EEFF" stroke-width="1.8" stroke-linecap="round"/></svg>
<a class="skip" href="#content">Skip to the section</a>
<header class="topbar">
  <a class="brand" href="#/overview" aria-label="{title}, Overview">{BRAND_SVG}<span>{title}</span></a>
  {_nav(data["sections"])}
  <div class="topmeta"><span class="cur" id="curlabel"></span><span class="mono">{html.escape(data["story"]["star"]["name"] or run["name"])} · {html.escape(_input_label(data))}</span>{SEARCH_BUTTON}{THEME_BUTTON}</div>
</header>
<main id="main">
 <div id="content" tabindex="-1">
    <section class="route" id="route-overview" data-route="overview" aria-labelledby="h-overview" hidden>
      {_overview(data)}
      <p class="note rule" id="sharednote" hidden>This is a shared layout, shown for this view only. Your own default layout is unchanged unless you change a widget here. <button class="btn" id="ownlayout" type="button">Show my layout</button></p>
      <div class="layoutbar" role="group" aria-label="Layout">
        <div class="layoutbar" id="hiddenlist"></div>
        <button class="btn" id="resetlayout" type="button">Reset layout</button>
        <button class="btn" id="copylayout" type="button">Copy link to this layout</button>
        <span class="muted" id="copystate" role="status"></span>
        <input class="copyfallback" id="copyfallback" type="text" readonly aria-label="Link to this layout" hidden>
      </div>
      <div class="widgets" id="widgets"></div>
    </section>
    <section class="route" id="route-sky" data-route="sky" aria-labelledby="h-sky" hidden>
      {_sky(data)}
    </section>
    <section class="route" id="route-galaxy" data-route="galaxy" aria-labelledby="h-galaxy" hidden>
      {galaxy_section(data.get("galaxy"), _eyebrow("Galaxy"), UNCONFIRMED, data.get("coverage"))}
    </section>
    <section class="route" id="route-transit" data-route="transit" aria-labelledby="h-transit" hidden>
      {_transit(data)}
    </section>
    <section class="route" id="route-explorer" data-route="explorer" aria-labelledby="h-explorer" hidden>
      {_explorer(data)}
      <div class="secthead"><h2 id="h-feedsec">{flabel}</h2><p>The feed from the discovery catalogue: {len(feed)} entries, {n_known} of them match a known TOI period. Every entry is a {unc}: a dip the panel marked, not a planet.{f" A TOI match is an archive comparison. {nodet}" if n_known else ""}</p></div>
      <p class="note rule"><b>Feed rule</b> (discover.py): an entry joins the feed when its depth is at most {rule["max_depth_ppm"]:,.0f} ppm and its signal has at least {rule["min_transits"]} transits. This is an admission rule, not a vetting result.</p>
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
    </section>
    <section class="route" id="route-sentinels" data-route="sentinels" aria-labelledby="h-sentinels" hidden>
      {_sentinels(data)}
      {_benchmark_card(data.get("benchmark"))}
      <p class="note rule"><b>Weights.</b> A reviewer's weight is its calibration skill from injection tests: the true-positive rate on injected transits minus the false-positive rate on empty light curves, floored (calibrate.py). The calibrated weights are stored in {html.escape(data["weights_path"] or "no weights file")}. The weight in this run is the one manifest.json records; when it differs from the calibrated weight, the run did not use the calibrated weights.</p>
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
        <p class="muted" style="margin:0;font-size:13px">Which reviewers marked each consensus dip, from the stored reviewer list in candidates.json. The verdict ledger link opens the dip's checks in the Docket.</p>
        <div id="agreement"></div>
      </section>
      <div class="cards" id="panelcards"></div>
      <p class="casefile"><a href="#/runs">Runs and configuration ›</a><span>Every discovery run, its errors as stored, and the configuration behind this page.</span></p>
    </section>
    <section class="route" id="route-methods" data-route="methods" aria-labelledby="h-methods" hidden>
      {methods_section(data["examples"], data.get("galaxy"), {**data["story"], "run_created": run.get("created_at", "")}, data.get("coverage"), _eyebrow("Methods"))}
    </section>
    <section class="route" id="route-mission" data-route="mission" aria-labelledby="h-mission" hidden>
      {mission_section(_eyebrow("Mission Control"))}
    </section>
    <section class="route" id="route-catalogue" data-route="catalogue" aria-labelledby="h-catalogue" hidden>
      {catalogue_section(data.get("catalogue_meta"), _eyebrow("Catalogue"))}
    </section>
    <section class="route" id="route-planet" data-route="planet" aria-labelledby="h-planet" hidden>
      {planet_page(_eyebrow("Planet", ("catalogue", "Catalogue")))}
    </section>
    <section class="route" id="route-star" data-route="star" aria-labelledby="h-star" hidden>
      {star_page(_eyebrow("Star", ("catalogue", "Catalogue")))}
    </section>
    <section class="route" id="route-candidates" data-route="candidates" aria-labelledby="h-candidates" hidden>
      <header>{_eyebrow("Case file", ("transit", "Transit"))}<h1 class="lead-h" id="h-candidates" tabindex="-1">Every signal, its dips, and the checks behind each verdict.</h1><p>The Docket for run {html.escape(run["name"])}: every signal and its dips, with the vetting outcome, the transit strip and the verdict ledger. Every signal here is a {unc}.</p></header>
      <div class="frametools"><a id="fullpage" href="../docket/">Open full page</a><span class="muted">The Docket on its own page, at the same dip.</span></div>
      <div class="dippicker"><label for="dippick">Dip</label><select id="dippick" aria-describedby="dippickhint"></select><span class="sr" id="dippickhint">Every dip in this run, lettered in time order, with its vetting outcome. Each is a {unc}.</span></div>
      <p class="note" id="framestatus" role="status" hidden></p>
      <p class="note blocked" id="frameblocked" role="alert" hidden>The dossier could not load in this view. <a id="blockedlink" href="../docket/">Open it on its own page.</a></p>
      <iframe class="frame waiting" id="docketframe" title="Docket for run {html.escape(run["name"])}: signals, dips and vetting"></iframe>
    </section>
    <section class="route" id="route-planets" data-route="planets" aria-labelledby="h-planets" hidden>
      <header>{_eyebrow("Planets", ("explorer", "Explorer"))}<h1 class="lead-h" id="h-planets" tabindex="-1">What each depth would imply, if it were a planet.</h1><p>One card per star in the run or the feed. Each entry is a {unc}; the ratio below is what its stored depth implies if it were a planet.</p></header>
      <p class="note"><b>Radius ratio only.</b> Rp/R* = √depth, with depth as a fraction (ppm × 10⁻⁶). This assumes a full, undiluted transit and ignores limb darkening. {html.escape(NO_STELLAR_RADIUS)} Each bar is a ratio scale from 0 to {data["ratio_scale_max"]:.2f}, the same on every card.</p>
      <p class="note">Published planets come from the stored archive cross-match ({html.escape(data.get("crossmatch_file") or "crossmatch.json")}), which covers {xm_targets}. The other stars have no stored cross-match, so their cards have no archive box. {nodet}</p>
      <div class="cards" id="planetcards"></div>
    </section>
    <section class="route" id="route-runs" data-route="runs" aria-labelledby="h-runs" hidden>
      <header>{_eyebrow("Runs", ("sentinels", "Sentinels"))}<h1 class="lead-h" id="h-runs" tabindex="-1">Every discovery run, its errors as stored, and the configuration behind this page.</h1><p>The discovery run history from the catalogue, and the configuration of run {html.escape(run["name"])}. Error messages are shown as stored.</p></header>
      <section class="card" aria-labelledby="h-hist" style="display:grid;gap:4px"><h2 id="h-hist">Discovery runs</h2><div id="runtable"></div></section>
      <details class="card cfg"><summary>Configuration: run {html.escape(run["name"])} and the discovery catalogue</summary><div>
        <section aria-labelledby="h-cfg"><h3 id="h-cfg">This run's configuration</h3><div id="runconfig"></div></section>
        <section aria-labelledby="h-catcfg"><h3 id="h-catcfg">Discovery catalogue</h3><div id="catconfig"></div></section>
      </div></details>
    </section>
 </div>
</main>
<div id="announce" class="sr" aria-live="polite" aria-atomic="true"></div>
{SEARCH_DIALOG}
{LEARN_BAR}
<template id="mxsystpl">{system_stage()}</template>
<script id="data" type="application/json">{payload}</script>
{_galaxy_scripts(data, galaxy_payload)}
<script>{APP_JS}</script>
</body></html>
"""


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


LANDING_JS = r"""
// The landing page's only script: the theme control (dark, light or system), as in the app.
(function(){
  var THEMES = ['dark', 'light', 'system'], NAME = {dark: 'Dark (default)', light: 'Light', system: 'System'};
  var b = document.querySelector('[data-theme-toggle]'); if (!b) return;
  function cur(){ var t = document.documentElement.getAttribute('data-theme'); return THEMES.indexOf(t) >= 0 ? t : 'dark'; }
  function apply(t){
    document.documentElement.setAttribute('data-theme', t);
    try { if (t === 'dark') localStorage.removeItem('exoplan-theme'); else localStorage.setItem('exoplan-theme', t); } catch (e) {}
    b.setAttribute('aria-label', 'Colour theme: ' + NAME[t].toLowerCase() + '. Change theme'); b.querySelector('.themelbl').textContent = NAME[t];
  }
  b.addEventListener('click', function(){ apply(THEMES[(THEMES.indexOf(cur()) + 1) % THEMES.length]); });
  apply(cur());
})();
"""


def landing_page(data: dict, app_href: str = "app/") -> str:
    """The public site's entry page: the app's Overview (launch hero, proof strip, what it does not claim),
    standalone, with every section link pointing into the app. Same fonts, tokens and theme control."""
    title = html.escape(data["title"])
    run = data["run"]
    deco = data["deco"]
    body = _overview(data, with_view=False).replace('href="#/', f'href="{app_href}#/')
    nav = _nav(data["sections"]).replace('href="#/', f'href="{app_href}#/').replace('data-route="overview">', 'data-route="overview" aria-current="page">')
    description = (f"exoplan: a calibrated panel of Sentinels and Probes reads TESS light curves. Run {run['name']}: "
                   f"{data['hero']['headline']} Every dip is a {UNCONFIRMED}.")
    fonts = app_href + FONTS_CSS
    links = (f'<a href="{app_href}#/sky">Sky</a><a href="{app_href}#/galaxy">Galaxy</a><a href="{app_href}#/transit">Transit</a><a href="{app_href}#/explorer">Explorer</a>'
             f'<a href="{app_href}#/sentinels">Sentinels</a><a href="docket/">The Docket</a><a href="plate/">Plates</a>'
             f'<a href="report/">Full run report (archived)</a>')
    return f"""<!doctype html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}: the sky, reviewed</title>
<meta name="description" content="{html.escape(description)}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#000000">
<link rel="icon" href="data:,">
<script>{THEME_HEAD_JS}</script>
<link rel="stylesheet" href="{html.escape(fonts)}">
<style>{APP_CSS}
.sitelinks{{display:flex;flex-wrap:wrap;gap:8px 18px;border-top:1px solid var(--line);padding-top:22px;font-size:14px}}
.sitelinks a{{display:inline-flex;align-items:center;min-height:44px}}
.landing .route{{display:grid}}</style></head>
<body class="landing" data-route="overview">
<svg class="starfield" aria-hidden="true" viewBox="0 0 1440 1100" preserveAspectRatio="xMidYMid slice"><path class="twinkle" d="{deco['dust']}" stroke="#FFFFFF" stroke-width="1" stroke-linecap="round" opacity=".5"/><path class="twinkle2" d="{deco['bright']}" stroke="#E8EEFF" stroke-width="1.8" stroke-linecap="round"/></svg>
<a class="skip" href="#content">Skip to the content</a>
<header class="topbar">
  <a class="brand" href="./" aria-label="{title}, home">{BRAND_SVG}<span>{title}</span></a>
  {nav}
  <div class="topmeta"><span class="mono">{html.escape(data["story"]["star"]["name"] or run["name"])} · {html.escape(_input_label(data))}</span>{THEME_BUTTON}</div>
</header>
<main id="main"><div id="content" tabindex="-1">
  <section class="route" aria-labelledby="h-overview">
    {body}
    <nav class="sitelinks" aria-label="More">{links}</nav>
    <p class="small">Built from {html.escape(run["dir"])} and {html.escape(data["catalog"]["path"] or "no catalogue")}. Stored values only.</p>
  </section>
</div></main>
{_galaxy_scripts(data)}
<script>{LANDING_JS}</script>
</body></html>
"""


def build_landing(run_dir: str | Path, out_path: str | Path, *, title: str, catalog_path: str | Path | None = None,
                  weights_path: str | Path | None = DEFAULT_WEIGHTS, app_href: str = "app/") -> Path:
    data = app_data(run_dir, title=title, catalog_path=catalog_path, weights_path=weights_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    from exoplan.codenote import code_note, with_code_note

    out.write_text(with_code_note(landing_page(data, app_href=app_href), code_note(run_dir)))
    return out


def build_app(run_dir: str | Path, out_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
              weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None,
              require_crossmatch: bool = False) -> Path:
    data = app_data(run_dir, title=title, catalog_path=catalog_path, weights_path=weights_path, star=star,
                    require_crossmatch=require_crossmatch)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    from exoplan.codenote import code_note, with_code_note

    path.write_text(with_code_note(app_page(data), code_note(run_dir)))
    # The fonts the page links to, self-hosted beside it (as Kshana serves them).
    import shutil

    shutil.copytree(FONTS_DIR, out / "assets" / "fonts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    # The Galaxy's table of every plotted planet, as CSV, beside the page.
    if data.get("galaxy"):
        (out / "assets" / "data").mkdir(parents=True, exist_ok=True)
        (out / "assets" / "data" / CSV_NAME).write_text(map_csv(data["galaxy"]))
        (out / GALAXY_JSON).write_text(galaxy_json(data))
    # Every catalogue record, fetched (same origin) by the Catalogue, the planet and star pages, and search.
    if data.get("catalogue"):
        (out / "assets" / "data").mkdir(parents=True, exist_ok=True)
        (out / CATALOGUE_JSON).write_text(json.dumps(data["catalogue"], separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    return path

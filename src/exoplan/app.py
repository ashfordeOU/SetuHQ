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
from exoplan.docket import OUTCOME_LABEL, docket_data, docket_page

SECTIONS = [
    ("overview", "Overview"),
    ("candidates", "Candidates"),
    ("discoveries", "Discoveries"),
    ("planets", "Planets"),
    ("panel", "Panel"),
    ("runs", "Runs"),
]

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
GOOGLE_FONTS = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600"
                "&family=JetBrains+Mono:wght@400;500;600&display=swap")  # the Docket's families


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
                            "fetched_at": (crossmatch or {}).get("fetched_at", "")}
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
  });
  document.addEventListener('DOMContentLoaded', function(){ send({kind: 'ready'}); });
})();
"""


# Also only in the shell's copy: on a phone-width frame the Docket's small controls become 44 px
# targets (min-height and padding, same font size). The standalone Docket page is unchanged.
FRAME_PHONE_CSS = (
    "@media (max-width:700px){"
    ".dipbtn,.chip,.listtoggle{min-height:44px;padding:10px 12px;box-sizing:border-box}"
    ".sectoggle{min-height:44px;padding:12px 0;box-sizing:border-box}"
    "}"
)


def with_frame_bridge(docket_html: str) -> str:
    """The Docket page with :data:`FRAME_PHONE_CSS` and :data:`FRAME_BRIDGE_JS` in its head.

    The bridge does nothing outside a frame; the phone rule applies to this copy only."""
    return docket_html.replace(
        "</head>", f"<style>{FRAME_PHONE_CSS}</style><script>{FRAME_BRIDGE_JS}</script></head>", 1)


def app_data(run_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
             weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None) -> dict:
    """Everything the shell shows, read from stored files only."""
    run_dir = Path(run_dir)
    dock = docket_data(run_dir, title=f"{title} · candidates", star=star)
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

    sections = [{"id": s, "label": feed_label(feed) if s == "discoveries" else label} for s, label in SECTIONS]
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
            "top": [{"id": c["candidate_id"], "target": c.get("target", ""), "depth_ppm": c["depth_ppm"], "snr": c["snr"],
                     "period_days": c.get("period_days"), "outcome": c["outcome"],
                     "outcome_label": OUTCOME_LABEL[c["outcome"]], "signal_id": c.get("signal_id", ""),
                     "signal_dips": per_signal.get(c.get("signal_id", ""), 1), **archive_match(c["candidate_id"])}
                    for c in top],
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
        "planets": planet_cards(cands, run_name, feed, crossmatch),
        "crossmatch_line": crossmatch.get("line", ""),
        "crossmatch_targets": crossmatch.get("targets") or [],
        "panel": panel_cards(manifest, run["marks"], run["reviewerDecisions"], flat, cands),
        "calibration": {**calibration_plane(calibrated, record, dock["reviewers"]), "record_path": record_name},
        "agreement": dip_agreement(cands, dock["reviewers"]),
        "weights_path": weights_name,
        "docket_html": with_frame_bridge(docket_page(dock)),
    }


APP_CSS = """
:root{--paper:#f7f6f2;--ink:#16181d;--rule:#d9d7d0;--muted:#62656d;--fit:#1f5fbf;--pass:#2e7d4f;--flag:#8a6400;--reject:#b23a3a;--panel:#fcfbf8;--sel:#ebe9e1;--side:#efede7;--top:56px}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--paper:#121317;--ink:#ecebe6;--rule:#2a2c33;--muted:#9a9ca4;--fit:#6fa0ff;--pass:#5cc08a;--flag:#e0b243;--reject:#ef7070;--panel:#17181d;--sel:#22242b;--side:#0e0f12;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#121317;--ink:#ecebe6;--rule:#2a2c33;--muted:#9a9ca4;--fit:#6fa0ff;--pass:#5cc08a;--flag:#e0b243;--reject:#ef7070;--panel:#17181d;--sel:#22242b;--side:#0e0f12;color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0;overflow-x:hidden}
body{background:var(--paper);color:var(--ink);font:14px/1.5 "Inter Tight",system-ui,-apple-system,"Segoe UI",sans-serif}
.mono,code,pre{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--fit);outline-offset:2px}
a{color:var(--fit)}
.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:8px;top:-60px;background:var(--ink);color:var(--paper);padding:8px 12px;border-radius:4px;z-index:50;display:inline-flex;align-items:center;min-height:44px}
.skip:focus{top:8px}
#content:focus{outline:none}
.topbar{display:none}
.shell{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh;background:linear-gradient(to right,var(--side) 231px,var(--rule) 231px,var(--rule) 232px,transparent 232px)}
.sidebar{background:var(--side);border-right:1px solid var(--rule);position:sticky;top:0;height:100vh;overflow:auto;overscroll-behavior:contain;display:flex;flex-direction:column;gap:16px;padding:18px 0}
.brand{padding:0 18px}
.brand b{display:block;font:600 17px/1.2 "Inter Tight",sans-serif}
.brand span{font:12px "JetBrains Mono",monospace;color:var(--muted);overflow-wrap:anywhere}
.nav ul{list-style:none;margin:0;padding:0 10px;display:grid;gap:2px}
.nav a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:6px;color:var(--ink);text-decoration:none;font-weight:500}
.nav a:hover{background:var(--sel)}
.nav a[aria-current="page"]{background:var(--ink);color:var(--paper)}
.nav svg{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.6}
.sidefoot{margin-top:auto;padding:0 18px;font:11px/1.6 "JetBrains Mono",monospace;color:var(--muted);overflow-wrap:anywhere}
.backdrop{display:none}
main{min-width:0;padding:24px 32px 48px}
main:focus{outline:none}
.route{display:grid;gap:18px;min-width:0;max-width:1180px}
.route[hidden]{display:none}
.route>header h1{font:600 24px/1.25 "Inter Tight",sans-serif;margin:0}
.route>header h1:focus{outline:none}
.route>header p{margin:4px 0 0;color:var(--muted);max-width:78ch}
h2{font:600 16px/1.3 "Inter Tight",sans-serif;margin:0}
h3{font:600 14px/1.3 "Inter Tight",sans-serif;margin:0}
.note{margin:0;border-left:3px solid var(--flag);background:var(--panel);padding:8px 12px;font-size:13px;max-width:90ch}
.note.rule{border-left-color:var(--fit)}
.tag{display:inline-block;font:600 11px/1.6 "JetBrains Mono",monospace;border:1px solid currentColor;border-radius:3px;padding:0 5px;white-space:nowrap}
.tag.unc{color:var(--flag)}
.tag.sim{color:var(--muted)}
.tag.cl{color:var(--fit)}
.muted{color:var(--muted)}
.btn{font:500 13px "Inter Tight",sans-serif;color:var(--ink);background:var(--panel);border:1px solid var(--rule);border-radius:5px;padding:5px 10px;cursor:pointer;min-height:32px}
.btn:hover{border-color:var(--ink)}
.btn[aria-disabled="true"]{opacity:.45;cursor:default}
.chip{font:12px "JetBrains Mono",monospace;border:1px solid var(--rule);background:none;color:var(--muted);padding:4px 10px;border-radius:999px;cursor:pointer;min-height:32px}
.chip[aria-pressed="true"]{color:var(--ink);border-color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;min-width:0}
.cards{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}
/* overview */
.layoutbar{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;font-size:13px}
.layoutbar .muted{font-size:12px}
.widgets{display:grid;gap:14px;grid-template-columns:repeat(6,minmax(0,1fr));min-width:0}
.widget{display:grid;gap:10px;align-content:start}
.widget.size-S{grid-column:span 2}
.widget.size-M{grid-column:span 3}
.widget.size-L{grid-column:1/-1}
.widget>header{display:flex;justify-content:space-between;align-items:center;gap:6px 8px;flex-wrap:wrap}
.wctl{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.wctl .btn{padding:2px 8px;min-height:30px;min-width:30px;font-size:12px}
.seg{display:inline-flex}
.seg .btn{border-radius:0;margin-left:-1px}
.seg .btn:first-child{border-radius:5px 0 0 5px;margin-left:0}
.seg .btn:last-child{border-radius:0 5px 5px 0}
.seg .btn[aria-pressed="true"]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.wopen{font-size:12px}
.dip{font:12px "JetBrains Mono",monospace;white-space:nowrap}
.toplist,.toplist ul{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.toplist>li{border-top:1px solid var(--rule);padding-top:8px;display:grid;gap:6px}
.toplist ul li{display:flex;flex-wrap:wrap;gap:2px 10px;align-items:baseline;font-size:13px}
.toplist .st .short,.phonehedge{display:none}
.toplist .note{font-size:12px}
.kpis{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(110px,1fr))}
.kpi{border-top:2px solid var(--rule);padding-top:6px}
.kpi b{display:block;font:600 26px/1.1 "JetBrains Mono",monospace}
.kpi span{font-size:12px;color:var(--muted)}
.big{font:600 40px/1 "JetBrains Mono",monospace}
.empty{color:var(--muted);font-style:italic}
.runlist{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.runlist li{display:grid;gap:2px;border-top:1px solid var(--rule);padding-top:6px;font-size:13px}
.runlines{list-style:none;margin:0;padding:0;display:grid;gap:0}
.runlines>li{border-top:1px solid var(--rule);padding:8px 0;font-size:13px;display:grid;gap:4px}
.runlines>li:first-child{border-top:0}
.runlines .line{display:flex;flex-wrap:wrap;gap:2px 12px;align-items:baseline}
.runlines .err{color:var(--reject)}
.ratio summary{font-size:13px}
/* tables */
.tablewrap{overflow-x:auto;min-width:0;border:1px solid var(--rule);border-radius:8px;background:var(--panel)}
.tablewrap.scrollbox{max-height:70vh;overflow:auto}
.scrollbox thead th{position:sticky;top:0;background:var(--panel);z-index:2}
.scrollbox th:first-child,.scrollbox td:first-child{position:sticky;left:0;background:var(--panel);z-index:1;box-shadow:1px 0 0 var(--rule)}
.scrollbox thead th:first-child{z-index:3}
.scrollbox td,.scrollbox tbody th{white-space:nowrap}
.scrollbox tbody th{font:400 13px "JetBrains Mono",monospace;color:var(--ink);text-transform:none;letter-spacing:0}
td .dip{font-size:11px;display:inline-block;max-width:24ch;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
table{width:100%;border-collapse:collapse;font:13px "JetBrains Mono",monospace}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--rule);vertical-align:top}
th{font:600 11px "JetBrains Mono",monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;white-space:nowrap}
td.num,th.num{text-align:right}
th button{font:inherit;color:inherit;text-transform:inherit;letter-spacing:inherit;background:none;border:0;padding:2px 0;cursor:pointer;display:inline-flex;gap:4px;align-items:center}
th[aria-sort="ascending"] button,th[aria-sort="descending"] button{color:var(--ink)}
tbody tr:last-child td{border-bottom:0}
td small{display:block;color:var(--muted);font-size:11px}
/* charts */
.charts{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr))}
svg{display:block;width:100%;height:auto}
svg text{font:11px "JetBrains Mono",monospace;fill:var(--muted)}
svg .grid{stroke:var(--rule)}
svg .bar{fill:var(--fit)}
svg .lbl{fill:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px}
.legend .k-new{background:var(--fit)}
.legend .k-known{border:2px solid var(--muted)}
.legend .k-sim{border:2px solid var(--muted)}
.legend .k-cl{background:var(--fit)}
svg.calplane{margin:0 auto}
svg.calplane .floor{fill:var(--sel)}
svg.calplane .iso{stroke:var(--muted);stroke-dasharray:4 3}
svg.calplane .floorline{stroke:var(--flag)}
svg.calplane .isolbl{fill:var(--muted);font-size:10px}
svg.calplane .samplelbl{fill:var(--flag);font-weight:600}
svg.calplane .pt.sim{fill:var(--panel);fill-opacity:.85;stroke:var(--muted);stroke-width:2}
svg.calplane .lbl,svg.calplane .samplelbl,svg.calplane .isolbl{paint-order:stroke;stroke:var(--panel);stroke-width:4px;stroke-linejoin:round}
#caltable th,#caltable td{white-space:nowrap}
#caltable tbody th{font:400 13px "JetBrains Mono",monospace;text-transform:none;letter-spacing:0;color:var(--ink)}
svg.calplane .pt.cl{fill:var(--fit);fill-opacity:.85;stroke:var(--fit);stroke-width:1.5}
/* planets */
.ratio{display:grid;gap:4px;border-top:1px solid var(--rule);padding-top:8px;margin-top:8px}
.ratio .formula{font:12px "JetBrains Mono",monospace;overflow-wrap:anywhere}
.scale{position:relative;height:10px;background:var(--sel);border:1px solid var(--rule);border-radius:3px;overflow:hidden}
.scale i{position:absolute;left:0;top:0;bottom:0;background:var(--fit);min-width:2px}
.scalecap{display:flex;justify-content:space-between;font:11px "JetBrains Mono",monospace;color:var(--muted)}
.archive{margin-top:12px;border:1px dashed var(--rule);border-radius:6px;padding:8px 10px;font-size:13px}
.archive ul{margin:6px 0 0;padding-left:18px}
.card h2{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:baseline}
details summary{cursor:pointer}
/* panel, runs */
.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 14px;font-size:13px;margin:8px 0 0}
.kv dt{color:var(--muted)}
.kv dd{margin:0;font-family:"JetBrains Mono",monospace;overflow-wrap:anywhere;min-width:0}
.agree{list-style:none;margin:0;padding:0;display:grid}
.agree li{display:grid;grid-template-columns:minmax(0,15em) minmax(0,1fr) auto;gap:4px 14px;align-items:baseline;border-top:1px solid var(--rule);padding:8px 0;font-size:13px}
.agree li:first-child{border-top:0}
.marks{display:flex;flex-wrap:wrap;gap:4px 10px;margin:4px 0 0}
details.cfg{padding:0}
details.cfg>summary{padding:12px 16px;font-weight:600}
details.cfg>div{padding:0 16px 14px;display:grid;gap:14px}
.frametools{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:13px}
pre.err{white-space:pre-wrap;overflow-wrap:anywhere;margin:4px 0;font-size:12px;background:var(--sel);padding:6px 8px;border-radius:4px}
.frame{width:100%;height:calc(100vh - 190px);height:calc(100vh - var(--frame-offset, 190px));min-height:520px;border:1px solid var(--rule);border-radius:8px;background:var(--paper);display:block}
.frame[hidden]{display:none}
/* Until the Docket reports ready the frame takes no space and the status line holds the slot. */
.frame.waiting,body[data-route="candidates"] .frame.waiting{height:0;min-height:0;flex:0 0 0;border:0;visibility:hidden}
.drawerclose{display:none}
.topfull{display:none}
.note.blocked{border-left-color:var(--reject);font-size:14px}
.copyfallback{font:12px "JetBrains Mono",monospace;width:min(100%,46ch);min-height:32px;padding:4px 8px;border:1px solid var(--rule);border-radius:5px;background:var(--panel);color:var(--ink)}
#sharednote{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
#sharednote[hidden]{display:none}
#disctable caption{caption-side:top;text-align:left}
.capnote{position:sticky;left:0;display:inline-block;padding:8px 10px;font:12px "Inter Tight",sans-serif;color:var(--muted)}
@media (max-width:1000px){
  .widget.size-S{grid-column:span 3}
  .agree li{grid-template-columns:minmax(0,1fr) auto}
  .agree li>:nth-child(2){grid-column:1/-1;grid-row:2}
}
@media (max-width:699.98px){
  .topbar{display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:20;height:var(--top);padding:0 16px;background:var(--side);border-bottom:1px solid var(--rule)}
  .topbar b{font:600 16px "Inter Tight",sans-serif;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
  .topbar .cur{color:var(--muted);font-size:13px;white-space:nowrap}
  .menu{display:inline-flex;align-items:center;gap:8px}
  .menu svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8}
  .shell{display:block}
  .sidebar{position:fixed;z-index:40;left:0;top:0;bottom:0;height:auto;width:min(280px,84vw);transform:translateX(-102%);visibility:hidden;transition:transform .18s ease,visibility 0s linear .18s;box-shadow:0 0 24px rgba(0,0,0,.25)}
  .sidebar.open{transform:none;visibility:visible;transition:transform .18s ease}
  .backdrop{display:block;position:fixed;inset:0;z-index:30;background:rgba(0,0,0,.35)}
  .backdrop[hidden]{display:none}
  main{padding:16px 16px 40px}
  .widgets{grid-template-columns:minmax(0,1fr)}
  .widget.size-S,.widget.size-M,.widget.size-L{grid-column:1/-1}
  .route>header h1{font-size:20px}
  .frame{height:calc(100vh - var(--top));height:calc(100dvh - var(--top));min-height:0;border-radius:0;border-left:0;border-right:0;margin:0 -16px;width:calc(100% + 32px)}
  .btn,.chip,.wctl .btn,.nav a{min-height:44px}
  .wctl .btn{min-width:44px}
  .shell{background:none}
  .seg{display:none}
  .frametools a{display:inline-flex;align-items:center;min-height:44px}
  .drawerclose{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;margin:0 18px}
  th button{min-height:44px;min-width:44px}
  .shell{min-height:0}
  /* Every link and disclosure in the page is a 44 px target: min-height and padding, same font size. */
  main a{display:inline-block;min-height:44px;min-width:44px;padding:12px 0;line-height:20px;box-sizing:border-box}
  td a.dip{padding:12px 0;line-height:20px}
  summary{min-height:44px;padding:12px 0;line-height:20px;box-sizing:border-box}
  .copyfallback{min-height:44px}
  /* Top candidates: each dip is one 44 px line. The link fills the row height, so the row needs no
     extra padding; the status shows its short word and the hedge sits on the signal line above. */
  .toplist ul{gap:0}
  .toplist ul li.toprow{display:grid;grid-template-columns:auto auto auto minmax(0,1fr);gap:0 10px;align-items:center;height:44px;white-space:nowrap;border-top:1px solid var(--rule);font-size:12px}
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
  body[data-route="candidates"] #route-candidates{display:flex;flex-direction:column;gap:0;height:calc(100vh - var(--top));height:calc(100dvh - var(--top));max-width:none}
  body[data-route="candidates"] #route-candidates>header{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
  body[data-route="candidates"] #route-candidates .frametools{display:none}
  body[data-route="candidates"] #route-candidates>.note{margin:8px 16px;flex:none}
  body[data-route="candidates"] .frame{flex:1 1 auto;height:auto;min-height:0;margin:0;width:100%;border:0;border-radius:0}
  body[data-route="candidates"] .topfull{display:inline-flex;align-items:center;min-height:44px;margin-left:auto;white-space:nowrap}
}
@media (prefers-reduced-motion: reduce){.sidebar,.sidebar.open{transition:none}}
"""

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
const fmt = (x, d=2) => (x === null || x === undefined || Number.isNaN(Number(x))) ? '–' : Number(x).toFixed(d);
const NS = 'http://www.w3.org/2000/svg';
function el(tag, a={}, p){ const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
function tx(svg, x, y, s, anchor='start', cls=''){ const t = el('text', {x, y, 'text-anchor': anchor, class: cls}, svg); t.textContent = s; return t; }
const UNC = `<span class="tag unc">${esc(D.unconfirmed)}</span>`;
const say = msg => { const a = $('#announce'); a.textContent = ''; setTimeout(() => { a.textContent = msg; }, 30); };
const isClaude = k => k === 'claude' || k === 'claude_code';
const OUTCOME_SHORT = {passed: 'passed', flagged: 'flagged', rejected: 'rejected'};
const kindTag = k => k === 'simulated' ? '<span class="tag sim">simulated · not a person</span>' : isClaude(k) ? `<span class="tag cl">Claude · ${esc(k)}</span>` : `<span class="tag">${esc(k || 'unknown')}</span>`;
function niceTicks(lo, hi, n){
  if (!(hi > lo)) return [lo];
  const raw = (hi-lo)/Math.max(1,n), mag = Math.pow(10, Math.floor(Math.log10(raw))), r = raw/mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo/step)*step; v <= hi + 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
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
  try { s = d.toLocaleString(undefined, {day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'}); } catch (e) { s = d.toUTCString(); }
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
  try { history.replaceState(null, '', '#/overview?layout=' + encodeLayout(layout)); } catch (e) { /* the layout still applies */ }
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
      <p class="muted" style="margin:0;font-size:12px">Run ${esc(r.name)}, ${when(r.created_at)}. ${esc(dc.rejected ?? 0)} signal${dc.rejected===1?'':'s'} rejected by vetting. The light curves are measured (${esc((D.config.inputs[0]||{}).source || 'stored input')}); the reviews come from ${sim} simulated detector${sim===1?'':'s'} (not people) and ${cl} Claude reviewer${cl===1?'':'s'}.</p>`;
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
const WIDGET_LINK = {kpis:'candidates', discoveries:'discoveries', runs:'runs', top:'candidates'};
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
function docketURL(dip){
  try { if (!docketBlob) docketBlob = URL.createObjectURL(new Blob([D.docket_html], {type: 'text/html'})); } catch (e) { docketBlob = null; }
  return docketBlob ? docketBlob + (dip ? '#' + encodeURIComponent(dip) : '') : null;
}
const fullHref = dip => '../docket/' + (dip ? '#' + encodeURIComponent(dip) : '');
function setFullHrefs(dip){ for (const a of $$('#fullpage, #topfull, #blockedlink')) a.href = fullHref(dip); }
// Keep the shell URL and the full-page links on the dip (and section) the frame shows.
function syncShellURL(){
  setFullHrefs(frame.dip);
  if (current !== 'candidates') return;
  const h = '#/candidates' + (frame.dip ? `?dip=${encodeURIComponent(frame.dip)}${frame.section ? '&section=' + frame.section : ''}` : '');
  if (location.hash !== h){
    try { history.replaceState(null, '', h); frame.shellURLFailed = false; } catch (e) { frame.shellURLFailed = true; }
    if (frame.ready) readyStatus();
  }
}
function tellFrame(dip, section){
  if (dip) { frame.dip = dip; frame.section = section || null; }
  else if (section) frame.section = section;
  try { $('#docketframe').contentWindow.postMessage({source: 'exoplan-shell', dip, section}, '*'); } catch (e) { /* frame gone */ }
  syncShellURL();
}
function frameStatus(text){ const s = $('#framestatus'); s.textContent = text || ''; s.hidden = !text; fitFrame(); }
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
}
window.addEventListener('message', e => {
  const f = $('#docketframe'), m = e.data;
  if (!f || e.source !== f.contentWindow || !m || m.source !== 'exoplan-docket') return;
  if (m.urlFailed) frame.frameURLFailed = true;
  if (m.kind === 'ready'){ onFrameReady(m); return; }
  if (!frame.ready) return;  // the Docket's own first pick, before the shell's dip is applied
  if (m.kind === 'dip' && m.dip){ if (m.dip !== frame.dip) frame.section = null; frame.dip = m.dip; }
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
  if (url){ f.removeAttribute('srcdoc'); f.src = url; } else { f.removeAttribute('src'); f.srcdoc = D.docket_html; }
}
function openDip(dip, section){
  const f = $('#docketframe');
  if (dip && !DIP_IDS.has(dip)){ say(`No dossier for ${dip} in this run.`); dip = null; }
  if (!DOCKET_SECTIONS.includes(section)) section = null;
  if (!f.dataset.loaded){ f.dataset.loaded = '1'; loadDocket(dip, section); setFullHrefs(dip); }
  else if (!frame.ready){ if (dip || section) frame.pending = {dip: dip || frame.dip, section}; setFullHrefs(dip || frame.dip); }
  else if (dip || section) tellFrame(dip, section);
  else syncShellURL();
  if (dip) say(`Docket open on dip ${dip}${section === 'ledger' ? ', verdict ledger' : ''}.`);
}
function renderCandidates(){ /* the frame loads in openDip, with the dip from the URL */ }

// ---------- discoveries (the feed) ----------
const disc = {sort: 'snr', dir: -1, filter: 'all'};
// The Feed's sort and filter live in the URL (#/discoveries?sort=depth&filter=new) like the Overview
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
function syncFeedURL(){
  if (current !== 'discoveries') return;
  const h = '#/discoveries?' + encodeFeedView(currentFeedView());
  if (location.hash !== h) try { history.replaceState(null, '', h); } catch (e) { /* the view still applies */ }
}
applyFeedView(ownFeedView);
const COLS = [
  ['tic', 'TIC', x => x.tic, x => esc(x.tic)],
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
function renderDiscTable(){
  const rows = discRows();
  $('#disctable').innerHTML = `<table><caption><span class="sr">Feed, sorted by ${esc(disc.sort)} ${disc.dir > 0 ? 'ascending' : 'descending'}. Every entry is a ${esc(D.unconfirmed)}.</span>${noDossierLine(rows)}</caption>
    <thead><tr>${COLS.map(c => `<th scope="col" class="${NUMERIC.has(c[0]) ? 'num' : ''}" aria-sort="${disc.sort === c[0] ? (disc.dir > 0 ? 'ascending' : 'descending') : 'none'}"><button data-sort="${c[0]}">${esc(c[1])}<span aria-hidden="true">${disc.sort === c[0] ? (disc.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`).join('')}</tr></thead>
    <tbody>${rows.length ? rows.map(x => `<tr>${COLS.map((c, k) => k === 0 ? `<th scope="row" class="num">${c[3](x)}</th>` : `<td class="${NUMERIC.has(c[0]) ? 'num' : ''}">${c[3](x)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${COLS.length}" class="empty">No feed entries with this status.</td></tr>`}</tbody></table>`;
  $('#disccount').textContent = `${rows.length} of ${D.catalog.candidates.length} entries shown.`;
}
function renderDiscHead(){
  const f = D.catalog.candidates, n = s => f.filter(x => x.status === s).length, ft = D.catalog.found_times;
  const found = !ft.length ? 'no stored find time' : ft.length === 1 ? `found in the catalogue run of ${when(ft[0])}` : `found between ${when(ft[0])} and ${when(ft[ft.length-1])}`;
  $('#feedhead').innerHTML = f.length ? `${f.length} entries, ${found}. <b>${n('known_toi')} match a known TOI period</b>; ${n('new_candidate')} are new candidates. Every entry is a ${esc(D.unconfirmed)}.` : 'The feed is empty.';
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
  saveFeedView(); syncFeedURL();
  renderDiscTable();
  $(`#disctable button[data-sort="${k}"]`).focus();
  say(`Sorted by ${b.textContent.replace(/[▲▼]/g,'')}, ${disc.dir > 0 ? 'ascending' : 'descending'}.`);
});
$('#discchips').addEventListener('click', e => {
  const b = e.target.closest('button[data-f]'); if (!b) return;
  disc.filter = b.dataset.f; saveFeedView(); syncFeedURL(); renderDiscChips(); renderDiscTable();
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
    if (ar.status === 'not_run') arch = `<p style="margin:0">The archive cross-match did not run (archive unreachable at build time). ${esc(D.no_detection)}</p>`;
    else if (ar.status !== 'not_stored' && !ar.planets.length) arch = `<p style="margin:0">No published planet matched in the archive. ${esc(D.no_detection)}</p>`;
    else if (ar.status !== 'not_stored') arch = `<p style="margin:0"><b>Published planets.</b> ${esc(D.no_detection)}</p><ul>${ar.planets.map(p => `<li><b>${esc(p.pl_name)}</b> · host ${esc(p.hostname)} · P ${p.pl_orbper !== null && p.pl_orbper !== undefined ? esc(p.pl_orbper) + ' d' : 'not listed'} · ${p.tran_flag ? 'transiting' : 'not known to transit'}${p.rv_flag ? ' · radial-velocity detection' : ''}</li>`).join('')}</ul><p class="muted" style="margin:4px 0 0;font-size:12px">${esc(ar.source)}, fetched ${when(ar.fetched_at)}.</p>`;
    const hid = 'pl-' + String(s.star).replace(/\W/g,'_');
    return `<article class="card" aria-labelledby="${hid}"><h2 id="${hid}">${esc(s.star)} <span class="muted" style="font:12px 'JetBrains Mono',monospace">${esc(s.sources.join(' · '))} · ${s.entries.length} entr${s.entries.length===1?'y':'ies'}</span></h2>${rows}${arch ? `<div class="archive">${arch}</div>` : ''}</article>`;
  }).join('') : '<p class="empty">No stars in the run or the feed.</p>';
}

// ---------- panel ----------
function renderPanel(){
  renderCalibration(); calWidth = $('#calplane').clientWidth;
  const ag = D.agreement;
  $('#agreement').innerHTML = ag.length ? `<ul class="agree">${ag.map(a => `<li>
      <span>${dipLink(a.id)}<small class="muted" style="display:block;font-size:11px">${esc(a.target)} · ${esc(a.outcome_label)} · ${esc(D.unconfirmed)}</small></span>
      <span><b>${a.n} of ${a.of} reviewers</b> marked it: ${a.n_sim} of ${a.of_sim} simulated, ${a.n_claude} of ${a.of_claude} Claude<small class="muted" style="display:block;font-size:11px;font-family:'JetBrains Mono',monospace">${esc(a.reviewers.join(', ') || 'none')}</small></span>
      <a href="${dipHref(a.id, 'ledger')}">Verdict ledger</a></li>`).join('')}</ul>` : '<p class="empty">The run stored no dips.</p>';
  $('#panelcards').innerHTML = D.panel.length ? D.panel.map(r => `<article class="card"><h2 class="mono">${esc(r.id)}</h2>
    <p style="margin:6px 0 0">${kindTag(r.kind)}</p>
    <p class="muted" style="margin:6px 0 0;font-size:13px">${r.kind === 'simulated' ? 'Code that marks dips above an SNR threshold in the light curve. It is not a person.' : isClaude(r.kind) ? 'A Claude model that reads the plotted light curve and marks dips. It is not a person.' : ''}</p>
    <dl class="kv">
      <dt>weight in this run</dt><dd>${r.run_weight === null || r.run_weight === undefined ? 'not stored' : esc(r.run_weight)} <span class="muted">(manifest.json)</span></dd>
      <dt>calibrated weight</dt><dd>${r.calibrated_weight === null || r.calibrated_weight === undefined ? 'not in the weights file' : fmt(r.calibrated_weight,3)}${D.weights_path ? ` <span class="muted">(${esc(D.weights_path)})</span>` : ''}</dd>
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
  if (cl.length) parts.push(`<b>The Claude reviewers were calibrated on ${esc(sizes(cl).join(' / '))} subjects only.</b>`);
  if (sim.length) parts.push(`The simulated detectors (code, not people) on ${esc(sizes(sim).join(' / '))}.`);
  const n = Math.max(0, ...pts.map(p => p.n_injected || 0));
  if (n) parts.push(`With ${n} injected subjects a recall moves in steps of ${fmt(1 / n, 2)}, so one subject more or less changes a weight by that much. These weights are rough.`);
  return parts.join(' ');
}
function calPlane(box){
  box.innerHTML = '';
  const C = D.calibration, pts = C.points.filter(p => p.tpr !== null && p.tpr !== undefined && p.fpr !== null && p.fpr !== undefined);
  if (!C.points.length){ box.innerHTML = '<p class="empty">No weights file was given to this build.</p>'; return; }
  if (!pts.length){ box.innerHTML = '<p class="empty">The weights file stores no recall or false-alarm rates, so there is nothing to plot.</p>'; return; }
  const W = Math.min(560, Math.max(260, box.clientWidth || 520)), pl = 46, pr = 14, pt = 12, pb = 42;
  // pad keeps a point at FPR 0 clear of the axis labels; narrow drops the floor-region note.
  const pad = 14, side = W - pl - pr - pad, H = pt + side + pb, narrow = W < 420;
  const X = v => pl + pad + v * side, Y = v => pt + (1 - v) * side, R = w => 3 + 10 * Math.max(0, Number(w) || 0);
  const groups = [];
  for (const p of pts){ let g = groups.find(g => g.fpr === p.fpr && g.tpr === p.tpr && g.kind === (isClaude(p.kind) ? 'claude' : p.kind)); if (!g){ g = {fpr: p.fpr, tpr: p.tpr, kind: isClaude(p.kind) ? 'claude' : p.kind, items: []}; groups.push(g); } g.items.push(p); }
  const label = `Calibration plane: ${pts.length} reviewers by false-alarm rate and recall. ` + groups.map(g => `${g.items.map(p => p.id).join(' and ')}: recall ${fmt(g.tpr,2)}, false-alarm rate ${fmt(g.fpr,2)}, weight ${fmt(g.items[0].weight,2)}`).join('; ') + '. ' + calSample().replace(/<[^>]+>/g, '');
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
  // Lines of constant weight: TPR = FPR + w, labelled along the line.
  for (const w of C.iso){
    el('line', {x1: X(0), y1: Y(w), x2: X(1 - w), y2: Y(1), class: w === f ? 'iso floorline' : 'iso'}, svg);
    const a = w === f ? 0.55 : 0.72, lx = X(a * (1 - w)), ly = Y(w + a * (1 - w));
    const t = tx(svg, lx, ly - 5, w === f ? `weight ${w} (floor)` : `weight ${w}`, 'middle', 'isolbl'); t.setAttribute('transform', `rotate(-45 ${lx} ${ly})`);
  }
  if (!narrow) tx(svg, X(0.97), Y(0.30), `below the floor line: weight ${f}`, 'end');
  // The sample size, on the plane.
  const cl = pts.filter(p => isClaude(p.kind));
  if (cl.length) tx(svg, X(0.97), Y(0.08), `Claude: ${fmtN(cl[0])} only`, 'end', 'samplelbl');
  if (pts.some(p => p.kind === 'simulated')) tx(svg, X(0.97), Y(0.08) + 14, `simulated: ${fmtN(pts.find(p => p.kind === 'simulated'))}`, 'end');
  for (const g of groups){
    const r = R(g.items[0].weight), cx = X(g.fpr), cy = Y(g.tpr);
    const c = el('circle', {cx, cy, r, class: g.kind === 'claude' ? 'pt cl' : 'pt sim'}, svg);
    el('title', {}, c).textContent = g.items.map(p => `${p.id} (${p.kind === 'simulated' ? 'simulated, not a person' : isClaude(p.kind) ? 'Claude' : p.kind}): TPR ${fmt(p.tpr,2)}, FPR ${fmt(p.fpr,2)}, weight ${fmt(p.weight,2)}, ${fmtN(p)}`).join('\n');
    const word = g.kind === 'claude' ? 'Claude' : g.kind === 'simulated' ? 'simulated' : g.kind;
    tx(svg, cx + r + 6, cy + 4, `${g.items.length} ${word} · w ${fmt(g.items[0].weight,2)}`, 'start', 'lbl');
  }
}
function renderCalibration(){
  const C = D.calibration;
  $('#calsample').innerHTML = C.points.some(p => p.n_injected) ? calSample() : 'The sample size is not stored with these weights.';
  calPlane($('#calplane'));
  const kindWord = k => k === 'simulated' ? 'simulated · not a person' : isClaude(k) ? 'Claude' : esc(k);
  $('#caltable').innerHTML = C.points.length ? `<table><caption class="sr">Calibration rates and weights per reviewer, as stored</caption><thead><tr><th scope="col">reviewer</th><th scope="col">kind</th><th scope="col" class="num">recall (TPR)</th><th scope="col" class="num">false alarms (FPR)</th><th scope="col" class="num">weight</th><th scope="col">sample</th></tr></thead><tbody>${C.points.map(p => `<tr><th scope="row" class="mono">${esc(p.id)}</th><td>${kindWord(p.kind)}</td><td class="num">${fmt(p.tpr,2)}</td><td class="num">${fmt(p.fpr,2)}</td><td class="num">${fmt(p.weight,2)}${p.consistent === false ? '<small>not max(TPR − FPR, floor)</small>' : ''}</td><td>${esc(fmtN(p))}</td></tr>`).join('')}</tbody></table>` : '';
  $('#calsource').textContent = C.source ? `Rates: ${C.record_path || 'the weights file'}. ${C.source}` : (C.record_path ? `Rates: ${C.record_path}.` : '');
}
let calWidth = -1;
function resizeCalibration(){ const box = $('#calplane'); if (!box || $('#route-panel').hidden || box.clientWidth === calWidth) return; calWidth = box.clientWidth; calPlane(box); }

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
    ${pk.map(([k,v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}
  </dl>
  <h3 style="margin-top:14px">Measured inputs</h3>
  ${(c.inputs||[]).map(x => `<p style="margin:4px 0 0" class="mono">${esc(Object.entries(x).map(([k,v]) => k + ' ' + v).join(' · '))}</p>`).join('') || '<p class="empty">No inputs stored.</p>'}`;
  $('#catconfig').innerHTML = D.catalog.path ? `<dl class="kv"><dt>catalogue</dt><dd>${esc(D.catalog.path)}</dd><dt>config</dt><dd>${esc(D.catalog.config)}</dd><dt>config hash (sha256)</dt><dd>${esc(D.catalog.config_sha256)}</dd><dt>updated</dt><dd>${when(D.catalog.updated)}</dd><dt>targets reviewed</dt><dd>${esc(D.catalog.targets_reviewed)}</dd></dl>` : '<p class="empty">No discovery catalogue was given to this build.</p>';
}

// ---------- router and drawer ----------
const RENDER = {overview: renderOverview, candidates: renderCandidates, discoveries: renderDiscoveries, planets: renderPlanets, panel: renderPanel, runs: renderRuns};
const rendered = new Set();
const ROUTES = D.sections.map(s => s.id);
// Only hashes that start with "#/" are routes; anything else (such as the skip link's #content) is left to the browser.
function parseHash(h){
  if (!h || h === '#' || h === '#/') return {route: 'overview', params: new URLSearchParams()};
  if (!h.startsWith('#/')) return null;
  const body = h.slice(2), q = body.indexOf('?');
  let route = q < 0 ? body : body.slice(0, q);
  try { route = decodeURIComponent(route); } catch (e) { /* keep as typed */ }
  return {route: ROUTES.includes(route) ? route : 'overview', params: new URLSearchParams(q < 0 ? '' : body.slice(q + 1))};
}
let current = null;
function show(r, moveFocus){
  for (const id of ROUTES) $('#route-' + id).hidden = id !== r;
  $$('.nav a').forEach(a => { if (a.dataset.route === r) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const label = D.sections.find(s => s.id === r).label;
  document.title = `${label} · ${D.title}`;
  document.body.dataset.route = r;
  $('#curlabel').textContent = label;
  if (r === 'overview') renderOverview();
  else if (!rendered.has(r)){ RENDER[r](); rendered.add(r); }
  else if (r === 'discoveries') renderDiscCharts(false);
  if (moveFocus){ const h = $('#route-' + r + ' h1'); if (h) h.focus({preventScroll: true}); window.scrollTo(0, 0); }
  if (r === 'candidates') fitFrame();
}
function go(p, moveFocus){
  const changed = p.route !== current;
  if (p.route === 'overview'){
    if (p.params.has('layout')){
      layout = decodeLayout(p.params.get('layout'), WIDGET_IDS, D.default_size);
      sharedView = encodeLayout(layout) !== encodeLayout(ownLayout);
    } else { layout = ownLayout.map(x => ({...x})); sharedView = false; }
  }
  if (p.route === 'discoveries'){
    const fromURL = ['sort', 'dir', 'filter'].some(k => p.params.has(k));
    const before = currentFeedView();
    applyFeedView(fromURL ? decodeFeedView(p.params) : ownFeedView);
    if (rendered.has('discoveries') && encodeFeedView(before) !== encodeFeedView(currentFeedView())){ renderDiscChips(); renderDiscTable(); }
  }
  current = p.route;
  show(p.route, moveFocus && changed);
  if (p.route === 'discoveries') syncFeedURL();
  if (p.route === 'candidates') openDip(p.params.get('dip'), p.params.get('section'));
}
window.addEventListener('hashchange', () => { const p = parseHash(location.hash); if (!p) return; closeDrawer(false); go(p, true); });
$('.skip').addEventListener('click', e => { e.preventDefault(); const c = $('#content'); c.focus({preventScroll: true}); c.scrollIntoView(); });
const drawerMQ = window.matchMedia('(max-width: 699.98px)');
const side = $('#sidebar'), menu = $('#menubtn'), backdrop = $('#backdrop');
// On a phone the sidebar is a modal drawer: a dialog with its own name and close button.
function setDrawerRole(){
  if (drawerMQ.matches){ side.setAttribute('role', 'dialog'); side.setAttribute('aria-modal', 'true'); side.setAttribute('aria-label', `${D.title} sections menu`); }
  else { side.removeAttribute('role'); side.removeAttribute('aria-modal'); side.setAttribute('aria-label', `${D.title} sections`); }
}
// html has overflow-x:hidden, so overflow on body alone would not stop the viewport scrolling:
// lock the root itself while the drawer is open, and restore the saved position on close.
let lockedY = null;
function lockScroll(){
  if (lockedY !== null) return;
  lockedY = window.scrollY;
  document.documentElement.style.overflow = 'hidden'; document.body.style.overflow = 'hidden';
}
function unlockScroll(){
  if (lockedY === null) return;
  const y = lockedY; lockedY = null;
  document.documentElement.style.overflow = ''; document.body.style.overflow = '';
  if (window.scrollY !== y) window.scrollTo(0, y);
}
// Touch drags on the backdrop would otherwise scroll the page behind it on some phones.
backdrop.addEventListener('touchmove', e => e.preventDefault(), {passive: false});
function openDrawer(){
  side.classList.add('open'); backdrop.hidden = false; menu.setAttribute('aria-expanded', 'true');
  $('#main').inert = true; $('.topbar').inert = true;
  lockScroll();
  const cur = $('.nav a[aria-current="page"]') || $('.nav a'); setTimeout(() => cur.focus(), 20);
}
function closeDrawer(returnFocus){
  if (!side.classList.contains('open')) return;
  side.classList.remove('open'); backdrop.hidden = true; menu.setAttribute('aria-expanded', 'false');
  $('#main').inert = false; $('.topbar').inert = false;
  unlockScroll();
  if (returnFocus) menu.focus({preventScroll: true});
}
menu.addEventListener('click', () => side.classList.contains('open') ? closeDrawer(true) : openDrawer());
$('#drawerclose').addEventListener('click', () => closeDrawer(true));
backdrop.addEventListener('click', () => closeDrawer(true));
document.addEventListener('keydown', e => { if (e.key === 'Escape' && side.classList.contains('open')) { closeDrawer(true); e.preventDefault(); } });
side.addEventListener('keydown', e => {
  if (e.key !== 'Tab' || !side.classList.contains('open')) return;
  const f = $$('a, button', side).filter(x => x.offsetParent !== null), first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first){ last.focus(); e.preventDefault(); }
  else if (!e.shiftKey && document.activeElement === last){ first.focus(); e.preventDefault(); }
});
$$('.nav a').forEach(a => a.addEventListener('click', () => { if (a.getAttribute('aria-current') === 'page') closeDrawer(false); }));
setDrawerRole();
if (drawerMQ.addEventListener) drawerMQ.addEventListener('change', () => { closeDrawer(false); setDrawerRole(); });
let rt = null;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (!$('#route-discoveries').hidden) renderDiscCharts(false); resizeCalibration(); fitFrame(); }, 120); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitFrame);  // web fonts can rewrap the header
go(parseHash(location.hash) || {route: 'overview', params: new URLSearchParams()}, false);
"""


def _nav(sections: list[dict]) -> str:
    items = "".join(
        f'<li><a href="#/{s["id"]}" data-route="{s["id"]}"><svg viewBox="0 0 16 16" aria-hidden="true">{ICONS[s["id"]]}</svg>{html.escape(s["label"])}</a></li>'
        for s in sections
    )
    return f'<nav class="nav" aria-label="Sections"><ul>{items}</ul></nav>'


def app_page(data: dict) -> str:
    """The shell as one self-contained HTML page."""
    title = html.escape(data["title"])
    run = data["run"]
    rule = data["feed_rule"]
    payload = json.dumps(data).replace("</", "<\\/")
    unc = html.escape(UNCONFIRMED)
    nodet = html.escape(NO_DETECTION)
    label = {s["id"]: html.escape(s["label"]) for s in data["sections"]}
    feed = data["catalog"]["candidates"]
    n_known = sum(1 for r in feed if r.get("status") == "known_toi")
    xm_targets = ", ".join(html.escape(str(t)) for t in data.get("crossmatch_targets") or []) or "no star"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" href="data:,">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{html.escape(GOOGLE_FONTS)}">
<style>{APP_CSS}</style></head>
<body>
<a class="skip" href="#content">Skip to the section</a>
<header class="topbar">
  <button class="btn menu" id="menubtn" aria-expanded="false" aria-controls="sidebar"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12"/></svg>Menu</button>
  <b>{title}</b><span class="cur" id="curlabel"></span>
  <a class="topfull" id="topfull" href="../docket/">Full page</a>
</header>
<div class="shell">
  <aside class="sidebar" id="sidebar" aria-label="{title} sections">
    <button class="btn drawerclose" id="drawerclose" type="button"><span aria-hidden="true">✕</span> Close menu</button>
    <div class="brand"><b>{title}</b><span>run {html.escape(run["name"])}</span></div>
    {_nav(data["sections"])}
    <div class="sidefoot">built from {html.escape(run["dir"])}<br>{html.escape(data["catalog"]["path"] or "no catalogue")}<br>stored values only</div>
  </aside>
  <div class="backdrop" id="backdrop" hidden></div>
  <main id="main">
   <div id="content" tabindex="-1">
    <section class="route" id="route-overview" data-route="overview" aria-labelledby="h-overview" hidden>
      <header><h1 id="h-overview" tabindex="-1">Overview</h1><p>Run {html.escape(run["name"])} and the feed at a glance. Each widget's header can hide it, move it or set its size. Your changes are kept in this browser as your default when storage is allowed. Copy link to this layout shares it; a shared layout shows for that view only and never replaces the recipient's default.</p></header>
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
    <section class="route" id="route-candidates" data-route="candidates" aria-labelledby="h-candidates" hidden>
      <header><h1 id="h-candidates" tabindex="-1">Candidates</h1><p>The Docket for run {html.escape(run["name"])}: every signal and its dips, with the vetting outcome, the transit strip and the verdict ledger. Every signal here is a {unc}.</p></header>
      <div class="frametools"><a id="fullpage" href="../docket/">Open full page</a><span class="muted">The Docket on its own page, at the same dip.</span></div>
      <p class="note" id="framestatus" role="status" hidden></p>
      <p class="note blocked" id="frameblocked" role="alert" hidden>The dossier could not load in this view. <a id="blockedlink" href="../docket/">Open it on its own page.</a></p>
      <iframe class="frame waiting" id="docketframe" title="Docket for run {html.escape(run["name"])}: signals, dips and vetting"></iframe>
    </section>
    <section class="route" id="route-discoveries" data-route="discoveries" aria-labelledby="h-discoveries" hidden>
      <header><h1 id="h-discoveries" tabindex="-1">{label["discoveries"]}</h1><p>The feed from the discovery catalogue: {len(feed)} entries, {n_known} of them match a known TOI period. Every entry is a {unc}: a dip the panel marked, not a planet.</p></header>
      <p class="note rule"><b>Feed rule</b> (discover.py): an entry joins the feed when its depth is at most {rule["max_depth_ppm"]:,.0f} ppm and its signal has at least {rule["min_transits"]} transits. This is an admission rule, not a vetting result.</p>
      <section class="card" aria-labelledby="h-feed" style="display:grid;gap:10px">
        <h2 id="h-feed">Feed entries</h2>
        <p class="muted" id="feedhead" style="margin:0;font-size:13px"></p>
        <div class="chips" id="discchips" role="group" aria-label="Filter the feed by status"></div>
        <div class="tablewrap scrollbox" id="disctable" tabindex="0" role="region" aria-label="Feed table, scrolls in both directions"></div>
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
    <section class="route" id="route-planets" data-route="planets" aria-labelledby="h-planets" hidden>
      <header><h1 id="h-planets" tabindex="-1">Planets</h1><p>One card per star in the run or the feed. Each entry is a {unc}; the ratio below is what its stored depth implies if it were a planet.</p></header>
      <p class="note"><b>Radius ratio only.</b> Rp/R* = √depth, with depth as a fraction (ppm × 10⁻⁶). This assumes a full, undiluted transit and ignores limb darkening. {html.escape(NO_STELLAR_RADIUS)} Each bar is a ratio scale from 0 to {data["ratio_scale_max"]:.2f}, the same on every card.</p>
      <p class="note">Published planets come from the stored archive cross-match (crossmatch.json), which covers {xm_targets}. The other stars have no stored cross-match, so their cards have no archive box. {nodet}</p>
      <div class="cards" id="planetcards"></div>
    </section>
    <section class="route" id="route-panel" data-route="panel" aria-labelledby="h-panel" hidden>
      <header><h1 id="h-panel" tabindex="-1">Panel</h1><p>The reviewers that marked dips in run {html.escape(run["name"])}. Simulated reviewers are code; Claude reviewers are model calls. None of them is a person.</p></header>
      <p class="note rule"><b>Weights.</b> A reviewer's weight is its calibration skill from injection tests: the true-positive rate on injected transits minus the false-positive rate on empty light curves, floored (calibrate.py). The calibrated weights are stored in {html.escape(data["weights_path"] or "no weights file")}. The weight in this run is the one manifest.json records; when it differs from the calibrated weight, the run did not use the calibrated weights.</p>
      <section class="card" aria-labelledby="h-cal" style="display:grid;gap:8px">
        <h2 id="h-cal">Calibration plane</h2>
        <p class="muted" style="margin:0;font-size:13px">Each reviewer at its false-alarm rate (x: share of empty subjects it marked) and recall (y: share of injected transits it found) in calibration. Point size is its calibrated weight. The lines join points of equal weight, weight = TPR − FPR, floored at {data["calibration"]["floor"]}; up and to the left is better. Stored values only.</p>
        <div class="legend"><span><i class="k-sim"></i>simulated detector, not a person</span><span><i class="k-cl"></i>Claude reviewer, not a person</span><span>size: calibrated weight</span></div>
        <div id="calplane"></div>
        <p class="note" id="calsample" style="margin:0"></p>
        <div class="tablewrap" id="caltable" tabindex="0" role="region" aria-label="Calibration rates per reviewer"></div>
        <p class="muted" id="calsource" style="margin:0;font-size:12px;overflow-wrap:anywhere"></p>
      </section>
      <section class="card" aria-labelledby="h-agree" style="display:grid;gap:8px">
        <h2 id="h-agree">Marks per dip</h2>
        <p class="muted" style="margin:0;font-size:13px">Which reviewers marked each consensus dip, from the stored reviewer list in candidates.json. The verdict ledger link opens the dip's checks in the Docket.</p>
        <div id="agreement"></div>
      </section>
      <div class="cards" id="panelcards"></div>
    </section>
    <section class="route" id="route-runs" data-route="runs" aria-labelledby="h-runs" hidden>
      <header><h1 id="h-runs" tabindex="-1">Runs</h1><p>The discovery run history from the catalogue, and the configuration of run {html.escape(run["name"])}. Error messages are shown as stored.</p></header>
      <section class="card" aria-labelledby="h-hist" style="display:grid;gap:4px"><h2 id="h-hist">Discovery runs</h2><div id="runtable"></div></section>
      <details class="card cfg"><summary>Configuration: run {html.escape(run["name"])} and the discovery catalogue</summary><div>
        <section aria-labelledby="h-cfg"><h3 id="h-cfg">This run's configuration</h3><div id="runconfig"></div></section>
        <section aria-labelledby="h-catcfg"><h3 id="h-catcfg">Discovery catalogue</h3><div id="catconfig"></div></section>
      </div></details>
    </section>
   </div>
  </main>
</div>
<div id="announce" class="sr" aria-live="polite" aria-atomic="true"></div>
<script id="data" type="application/json">{payload}</script>
<script>{APP_JS}</script>
</body></html>
"""


def build_app(run_dir: str | Path, out_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
              weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None) -> Path:
    data = app_data(run_dir, title=title, catalog_path=catalog_path, weights_path=weights_path, star=star)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(app_page(data))
    return path

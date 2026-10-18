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
                            "fallback_from": (crossmatch or {}).get("fallback_from", "")}
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
            f"{counts.get('reviewers', 0)} reviewers ({counts.get('simulated', 0)} simulated detectors and "
            f"{counts.get('claude', 0)} Claude reviewers; none of them a person) marked {counts.get('dips', len(cands))} dips, "
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
    return {
        "target": target, "time_unit": unit, "n_points": n_points, "span_days": span,
        "headline": headline, "accent": accent, "lede": lede, "archive": archive,
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
    if (m.theme === 'light' || m.theme === 'dark') document.documentElement.setAttribute('data-theme', m.theme);
    else if (m.theme === 'system') document.documentElement.removeAttribute('data-theme');
  });
  // On a phone the signal list sits below the dossier: a fixed "Signals" button jumps to it.
  function jumpToList(){
    var l = document.getElementById('listpanel'); if (!l) return;
    var body = document.getElementById('listbody'), t = document.getElementById('listtoggle');
    if (body && body.getAttribute('data-collapsed') === 'true' && t) t.click();
    var sc = scroller(l), top = l.getBoundingClientRect().top;
    if (sc !== document.scrollingElement && sc !== document.documentElement) top -= sc.getBoundingClientRect().top;
    sc.scrollTop += top - 8;
    var rows = document.getElementById('rows'); if (rows) rows.focus({preventScroll: true});
  }
  document.addEventListener('DOMContentLoaded', function(){
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'jumplist'; b.textContent = 'Signals ↑'; b.setAttribute('aria-label', 'Jump to the list of signals and dips');
    b.addEventListener('click', jumpToList); document.body.appendChild(b);
    send({kind: 'ready'});
  });
})();
"""


# Also only in the shell's copy: on a phone-width frame the Docket's small controls become 44 px
# targets (min-height and padding, same font size). The standalone Docket page is unchanged.
FRAME_PHONE_CSS = (
    "@media (max-width:700px){"
    ".jumplist{display:inline-flex;align-items:center;position:fixed;right:12px;bottom:max(12px,env(safe-area-inset-bottom,0px));"
    "z-index:30;min-height:44px;padding:0 16px;border-radius:999px;border:1px solid var(--rule);background:var(--ink);"
    "color:var(--paper);font:500 14px/1 \"Geist\",sans-serif;box-shadow:0 10px 30px -12px rgba(0,0,0,.5);cursor:pointer}"
    ".dipbtn,.chip,.listtoggle{min-height:44px;padding:10px 12px;box-sizing:border-box}"
    ".sectoggle{min-height:44px;padding:12px 0;box-sizing:border-box}"
    "}"
    "@media (min-width:700.02px){.jumplist{display:none}}"
)


# Also only in the shell's copy: the Docket in the shell's family dress (Kshana's Observatory tokens and
# Geist type), so the framed page reads as part of the app. Same layout and rules; only colour and type change.
DOCKET_FONTS = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600"
                       "&family=JetBrains+Mono:wght@400;500;600&display=swap")
FRAME_THEME_CSS = (
    ":root{--paper:#E8ECF3;--ink:#182033;--rule:rgba(28,44,84,.2);--muted:#4E5971;--fit:#066A86;--pass:#2F6E0A;"
    "--flag:#764600;--reject:#B42D1B;--panel:#F5F7FB;--sel:#DEE4EE;--cons:#182033}"
    "@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]){--paper:#060A14;--ink:#EAF0FF;"
    "--rule:rgba(150,175,230,.2);--muted:#8190B0;--fit:#3DDCF7;--pass:#A8EE5E;--flag:#FFB547;--reject:#FF6A5C;"
    "--panel:#0D1528;--sel:#0E1730;--cons:#EAF0FF}}"
    ":root[data-theme=\"dark\"]{--paper:#060A14;--ink:#EAF0FF;--rule:rgba(150,175,230,.2);--muted:#8190B0;--fit:#3DDCF7;"
    "--pass:#A8EE5E;--flag:#FFB547;--reject:#FF6A5C;--panel:#0D1528;--sel:#0E1730;--cons:#EAF0FF;color-scheme:dark}"
    ":root[data-theme=\"light\"]{color-scheme:light}"
    "body{-webkit-font-smoothing:antialiased;letter-spacing:-.006em}"
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
             require_crossmatch: bool = False) -> dict:
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
        "hero": overview_hero(dock, top_rows),
        "planets": planet_cards(cands, run_name, feed, crossmatch),
        "crossmatch_line": crossmatch.get("line", ""),
        "crossmatch_targets": crossmatch.get("targets") or [],
        "crossmatch_file": crossmatch.get("fallback_from") or "crossmatch.json in the run",
        "panel": panel_cards(manifest, run["marks"], run["reviewerDecisions"], flat, cands),
        "calibration": {**calibration_plane(calibrated, record, dock["reviewers"]), "record_path": record_name},
        "agreement": dip_agreement(cands, dock["reviewers"]),
        "weights_path": weights_name,
        "docket_html": with_frame_bridge(docket_page(dock)),
        "fonts_css": FONTS_CSS, "frame_fonts_href": FRAME_FONTS_HREF,
    }


APP_CSS = """
/* Tokens: the Kshana Observatory system (kshana web/theme.css), so the two products read as one family.
   Text colours keep WCAG AA (4.5:1) on the ground they sit on, in both themes. The "space" tokens are the
   instrument panels: they stay dark in both themes, like Kshana's charts and consoles. */
:root{color-scheme:light;
  --bg:#E8ECF3;--bg-2:#DEE4EE;--bg-3:#D3DBE8;
  --glass:rgba(247,249,252,.9);--panel-2:rgba(238,242,248,.86);--panel:#F5F7FB;
  --line:rgba(28,44,84,.12);--line-2:rgba(28,44,84,.2);--line-3:rgba(28,44,84,.32);
  --ink:#182033;--ink-2:#3A455E;--ink-3:#4E5971;
  --cyan:#066A86;--lime:#2F6E0A;--amber:#764600;--coral:#B42D1B;--magenta:#A8247F;
  --cyan-soft:rgba(7,130,163,.12);--lime-soft:rgba(47,110,10,.12);--amber-soft:rgba(158,95,0,.12);--coral-soft:rgba(180,45,27,.11);
  --btn-bg:#182033;--btn-ink:#FFFFFF;
  --shadow:0 1px 0 rgba(255,255,255,.7) inset,0 18px 40px -28px rgba(24,40,80,.3),0 1px 3px rgba(24,40,80,.08);
  --gloss:linear-gradient(180deg,rgba(255,255,255,.4),transparent 46%);
  --dot:rgba(28,44,84,.065);
  --space:#060A14;--space-2:#0A1122;--space-3:#0E1730;--space-ink:#EAF0FF;--space-ink-2:#A7B4D2;--space-ink-3:#8190B0;--space-line:rgba(150,175,230,.14);
  --s-cyan:#3DDCF7;--s-lime:#A8EE5E;--s-amber:#FFB547;--s-coral:#FF6A5C;
  --sans:"Geist",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"Geist Mono",ui-monospace,"SF Mono",Menlo,monospace;
  --display:"Unbounded","Geist",sans-serif;
  --r:14px;--ease:cubic-bezier(.22,.9,.24,1);
  /* the shell's own names, pointed at the family tokens */
  --paper:var(--bg);--rule:var(--line-2);--muted:var(--ink-3);--fit:var(--cyan);--pass:var(--lime);--flag:var(--amber);--reject:var(--coral);--sel:var(--bg-2);--side:#DEE4EE;
  --top:56px}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;
  --bg:#060A14;--bg-2:#0A1122;--bg-3:#0E1730;--glass:rgba(16,24,44,.62);--panel-2:rgba(22,33,60,.55);--panel:#0D1528;
  --line:rgba(150,175,230,.11);--line-2:rgba(150,175,230,.2);--line-3:rgba(150,175,230,.32);
  --ink:#EAF0FF;--ink-2:#A7B4D2;--ink-3:#8190B0;
  --cyan:#3DDCF7;--lime:#A8EE5E;--amber:#FFB547;--coral:#FF6A5C;--magenta:#F45CCB;
  --cyan-soft:rgba(61,220,247,.14);--lime-soft:rgba(168,238,94,.14);--amber-soft:rgba(255,181,71,.14);--coral-soft:rgba(255,106,92,.14);
  --btn-bg:#EAF0FF;--btn-ink:#070B16;
  --shadow:0 1px 0 rgba(255,255,255,.05) inset,0 24px 60px -28px rgba(0,0,0,.75),0 2px 8px -2px rgba(0,0,0,.35);
  --gloss:linear-gradient(180deg,rgba(255,255,255,.045),transparent 40%);--dot:rgba(150,175,230,.075);--side:#0A1122}}
:root[data-theme="dark"]{color-scheme:dark;
  --bg:#060A14;--bg-2:#0A1122;--bg-3:#0E1730;--glass:rgba(16,24,44,.62);--panel-2:rgba(22,33,60,.55);--panel:#0D1528;
  --line:rgba(150,175,230,.11);--line-2:rgba(150,175,230,.2);--line-3:rgba(150,175,230,.32);
  --ink:#EAF0FF;--ink-2:#A7B4D2;--ink-3:#8190B0;
  --cyan:#3DDCF7;--lime:#A8EE5E;--amber:#FFB547;--coral:#FF6A5C;--magenta:#F45CCB;
  --cyan-soft:rgba(61,220,247,.14);--lime-soft:rgba(168,238,94,.14);--amber-soft:rgba(255,181,71,.14);--coral-soft:rgba(255,106,92,.14);
  --btn-bg:#EAF0FF;--btn-ink:#070B16;
  --shadow:0 1px 0 rgba(255,255,255,.05) inset,0 24px 60px -28px rgba(0,0,0,.75),0 2px 8px -2px rgba(0,0,0,.35);
  --gloss:linear-gradient(180deg,rgba(255,255,255,.045),transparent 40%);--dot:rgba(150,175,230,.075);--side:#0A1122}
*{box-sizing:border-box}
html{background:var(--bg);-webkit-text-size-adjust:100%;text-size-adjust:100%}
html,body{margin:0;overflow-x:hidden}
body{background:transparent;color:var(--ink);font:400 15px/1.55 var(--sans);letter-spacing:-.006em;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
/* the Observatory ground: a soft radial field with a faint dot grid that fades down the page */
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:radial-gradient(1100px 640px at 78% -12%,var(--bg-3),transparent 70%),radial-gradient(900px 600px at -10% 40%,var(--bg-2),transparent 70%)}
body::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background-image:radial-gradient(var(--dot) 1px,transparent 1.2px);background-size:24px 24px;-webkit-mask-image:linear-gradient(to bottom,#000,rgba(0,0,0,.3) 60%,transparent);mask-image:linear-gradient(to bottom,#000,rgba(0,0,0,.3) 60%,transparent)}
.mono,code,pre{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:0}
:focus-visible{outline:2px solid var(--cyan);outline-offset:3px;border-radius:6px}
::selection{background:var(--cyan);color:var(--bg)}
a{color:var(--cyan);text-underline-offset:3px;text-decoration-thickness:1px}
.sr{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:12px;top:-60px;background:var(--btn-bg);color:var(--btn-ink);padding:11px 14px;border-radius:11px;z-index:50;display:inline-flex;align-items:center;min-height:44px;text-decoration:none}
.skip:focus{top:12px}
#content:focus{outline:none}
.topbar{display:none}
.shell{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh;background:linear-gradient(to right,var(--side) 247px,var(--line) 247px 248px,transparent 248px)}
.sidebar{background:color-mix(in oklab,var(--side) 82%,transparent);-webkit-backdrop-filter:blur(16px) saturate(150%);backdrop-filter:blur(16px) saturate(150%);border-right:1px solid var(--line);position:sticky;top:0;height:100vh;overflow:auto;overscroll-behavior:contain;display:flex;flex-direction:column;gap:22px;padding:22px 0 18px}
.brand{padding:0 20px;display:grid;gap:6px}
.brand b{display:flex;align-items:center;gap:9px;font:500 17px/1 var(--display);letter-spacing:-.01em}
.brand b::before{content:"";width:16px;height:16px;flex:none;border-radius:50%;background:radial-gradient(circle at 50% 50%,var(--bg) 0 34%,transparent 36%),conic-gradient(from 200deg,var(--cyan),var(--lime),var(--cyan))}
.brand span{font:500 11px/1.4 var(--mono);color:var(--ink-3);letter-spacing:.06em;text-transform:uppercase;overflow-wrap:anywhere}
.navlabel{padding:0 20px;font:500 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin:0 0 -12px}
.nav ul{list-style:none;margin:0;padding:0 12px;display:grid;gap:2px}
.nav a{display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:11px;color:var(--ink-2);text-decoration:none;font-weight:500;font-size:14.5px;transition:color .2s,background-color .2s}
.nav a .ix{margin-left:auto;font:500 11px/1 var(--display);color:var(--ink-3);letter-spacing:0}
.nav a:hover{background:var(--panel-2);color:var(--ink)}
.nav a[aria-current="page"]{background:var(--glass);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line-2),var(--shadow)}
.nav a[aria-current="page"] .ix{color:var(--cyan)}
.nav svg{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.6}
.sidefoot{margin-top:auto;padding:14px 20px 0;border-top:1px solid var(--line);font:400 11px/1.6 var(--mono);color:var(--ink-3);overflow-wrap:anywhere;display:grid;gap:6px}
.sidefoot .stored{display:inline-flex;align-items:center;gap:7px;color:var(--ink-2);letter-spacing:.06em;text-transform:uppercase;font-size:11px}
.sidefoot .stored i{width:6px;height:6px;border-radius:50%;background:var(--lime);box-shadow:0 0 0 3px var(--lime-soft)}
.backdrop{display:none}
main{min-width:0;padding:30px clamp(18px,3vw,44px) 64px}
main:focus{outline:none}
.route{display:grid;gap:22px;min-width:0;max-width:1180px}
.route[hidden]{display:none}
.route>header{display:grid;gap:11px;padding-bottom:6px}
.route>header .eyebrow{display:flex;align-items:center;gap:12px;font:500 12px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin:0}
.route>header .eyebrow .idx{font:500 11px/1 var(--display);letter-spacing:0;color:var(--cyan)}
.route>header .eyebrow::after{content:"";height:1px;width:48px;background:var(--line-2);flex:none}
.route h1:focus{outline:none}
.route>header p{margin:0;color:var(--ink-2);max-width:72ch;font-size:clamp(15px,1.15vw,16.5px);line-height:1.55}
.route>header .lead-h{margin:0;font:600 clamp(26px,3.1vw,42px)/1.05 var(--sans);letter-spacing:-.035em;color:var(--ink);max-width:24ch;text-wrap:balance}
#route-candidates>header .lead-h{font-size:clamp(22px,2.3vw,30px);max-width:40ch}
h2{font:600 18px/1.25 var(--sans);letter-spacing:-.015em;margin:0}
h3{font:600 14.5px/1.3 var(--sans);letter-spacing:-.01em;margin:0}
.note{margin:0;border-top:1px solid var(--line-2);padding:14px 0 0;font-size:14px;color:var(--ink-2);max-width:86ch}
.note b{color:var(--ink);font-weight:600}
.note.rule{border-top-color:var(--line-2)}
.tag{display:inline-flex;align-items:center;gap:6px;font:500 11px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);padding:5px 8px;border:1px solid var(--line);border-radius:999px;background:var(--panel-2);white-space:nowrap;vertical-align:1px}
.tag.unc{color:var(--amber);border-color:color-mix(in oklab,var(--amber) 30%,transparent);background:var(--amber-soft)}
.tag.unc::before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor}
.tag.sim{color:var(--ink-3)}
.tag.cl{color:var(--cyan);background:var(--cyan-soft);border-color:transparent}
.muted{color:var(--ink-3)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;font:500 13px/1.2 var(--sans);color:var(--ink);background:var(--glass);border:1px solid var(--line-2);border-radius:11px;padding:6px 12px;cursor:pointer;min-height:34px;text-decoration:none;transition:border-color .2s,background-color .2s,transform .25s var(--ease)}
.btn:hover{border-color:var(--line-3);background:var(--panel-2)}
.btn[aria-disabled="true"]{opacity:.45;cursor:default}
.btn.primary{background:var(--btn-bg);color:var(--btn-ink);border-color:transparent;min-height:44px;padding:0 18px;font-size:14.5px;box-shadow:0 1px 0 rgba(255,255,255,.4) inset,0 11px 30px -12px color-mix(in oklab,var(--btn-bg) 50%,transparent)}
.btn.primary:hover{transform:translateY(-1px);background:var(--btn-bg)}
.btn.ghost{min-height:44px;padding:0 18px;font-size:14.5px}
.chip{font:500 12px/1.2 var(--mono);border:1px solid var(--line-2);background:var(--glass);color:var(--ink-2);padding:6px 12px;border-radius:999px;cursor:pointer;min-height:34px}
.chip[aria-pressed="true"]{color:var(--btn-ink);background:var(--btn-bg);border-color:transparent}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.card{background:var(--glass);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);padding:18px 20px;min-width:0;position:relative;isolation:isolate;-webkit-backdrop-filter:blur(18px) saturate(150%);backdrop-filter:blur(18px) saturate(150%)}
.card::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;background:var(--gloss);z-index:-1}
.cards{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}
/* overview: the argument first (hero), then the instrument, then what the page does not claim, then the widgets */
.hero{display:grid;gap:18px;min-width:0}
.consolebar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;font:500 11.5px/1.2 var(--mono);color:var(--ink-3);letter-spacing:.04em;text-transform:uppercase;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:11px 0}
.consolebar b{color:var(--ink);font-weight:500;text-transform:none;letter-spacing:0;font-variant-numeric:tabular-nums}
.consolebar .live{display:inline-flex;align-items:center;gap:8px;color:var(--ink-2)}
.consolebar .live i{width:7px;height:7px;border-radius:50%;background:var(--lime);box-shadow:0 0 0 4px var(--lime-soft)}
.consolebar .sep{width:1px;height:12px;background:var(--line-2);flex:none}
.consolebar .right{margin-left:auto}
.hero-copy{display:grid;gap:16px;max-width:62ch}
.hero-h{font:600 clamp(34px,4.6vw,62px)/1 var(--sans);letter-spacing:-.045em;margin:0;max-width:17ch;text-wrap:balance}
.hero-h em{font-style:normal;color:var(--amber)}
.lede{margin:0;font-size:clamp(15.5px,1.25vw,17.5px);line-height:1.55;color:var(--ink-2);max-width:60ch}
.lede b{color:var(--ink);font-weight:560}
.ctas{display:flex;flex-wrap:wrap;gap:11px;align-items:center}
/* the instrument: Kshana's dark chart panel, dark in both themes */
.instrument{background:linear-gradient(180deg,var(--space-2),var(--space));color:var(--space-ink);border:1px solid var(--space-line);border-radius:var(--r);box-shadow:0 1px 0 rgba(255,255,255,.05) inset,0 40px 90px -50px rgba(6,10,20,.75),0 6px 18px -11px rgba(6,10,20,.4);padding:16px 18px 14px;display:grid;gap:12px;min-width:0}
.instrument .ihead{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:8px 16px}
.instrument .ititle{font-size:13.5px;color:var(--space-ink);line-height:1.3;min-width:0}
.instrument .ititle small{display:block;font:500 11px/1.5 var(--mono);color:var(--space-ink-2);letter-spacing:.06em;text-transform:uppercase;margin-top:4px;overflow-wrap:anywhere}
.instrument .ival{font:500 26px/1 var(--mono);letter-spacing:-.02em;color:var(--s-lime);text-align:right;white-space:nowrap}
.instrument .ival small{display:block;font:500 11px/1.5 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--space-ink-2);margin-top:4px}
.instrument .igrid{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1.15fr);gap:14px;min-width:0}
.instrument figure{margin:0;min-width:0;display:grid;gap:6px}
.instrument figcaption{font:400 11.5px/1.5 var(--mono);color:var(--space-ink-2)}
.instrument .fold{border-left:1px solid var(--space-line);padding-left:14px}
.instrument svg text{fill:var(--space-ink-2);font:11px var(--mono)}
.instrument svg .grid{stroke:var(--space-line)}
.instrument svg .axis{stroke:rgba(150,175,230,.35)}
.instrument svg .pts{stroke:var(--space-ink-3);stroke-opacity:.55;stroke-width:2.2;stroke-linecap:round;fill:none}
.instrument svg .mean{stroke:var(--s-cyan);stroke-width:1.2;stroke-opacity:.9;fill:none;stroke-linejoin:round}
.instrument svg .box{stroke:var(--s-lime);stroke-width:1.4;stroke-dasharray:4 3;fill:none}
.instrument svg .win{opacity:.2}
.instrument svg .win.passed{fill:var(--s-lime)}
.instrument svg .win.flagged{fill:var(--s-amber)}
.instrument svg .win.rejected{fill:var(--s-coral)}
.instrument svg text.wl{font:600 11px var(--mono)}
.instrument svg text.wl.passed{fill:var(--s-lime)}
.instrument svg text.wl.flagged{fill:var(--s-amber)}
.instrument svg text.wl.rejected{fill:var(--s-coral)}
.instrument svg .epoch{fill:var(--s-lime)}
.instrument svg .dur{fill:var(--s-lime);opacity:.1}
.ikey{display:flex;flex-wrap:wrap;gap:6px 18px;font:500 11px/1.5 var(--mono);color:var(--space-ink-2);border-top:1px solid var(--space-line);padding-top:11px}
.ikey i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.ikey .k-passed{background:var(--s-lime)}.ikey .k-flagged{background:var(--s-amber)}.ikey .k-rejected{background:var(--s-coral)}
.ikey .k-mean{height:2px;background:var(--s-cyan);vertical-align:3px}
.ikey .k-ep{width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:8px solid var(--s-lime);border-radius:0}
.ikey .unc{color:var(--s-amber)}
/* the vetting flow: one line of stored counts, read left to right, instead of a wall of number tiles */
.flow{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr)) minmax(0,1.45fr);border:1px solid var(--line);border-radius:var(--r);background:var(--glass);box-shadow:var(--shadow);overflow:hidden}
.flow li{display:grid;gap:4px;align-content:start;padding:14px 16px;border-left:1px solid var(--line);position:relative;min-width:0}
.flow li:first-child{border-left:0}
.flow li b{font:500 clamp(24px,2.4vw,32px)/1 var(--mono);letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.flow li span{font-size:12.5px;color:var(--ink-2);line-height:1.35}
.flow li small{font:500 11px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
.vet3{display:flex;flex-wrap:wrap;gap:4px 14px}
.vet3 span{display:grid;gap:2px;font:500 11px/1.3 var(--mono);color:var(--ink-3)}
.vet3 .pass b{color:var(--lime)}.vet3 .flag b{color:var(--amber)}.vet3 .rej b{color:var(--coral)}
.flow li+li::before{content:"→";position:absolute;left:-8px;top:15px;width:16px;height:16px;display:grid;place-items:center;font:500 11px/1 var(--mono);color:var(--ink-3);background:var(--panel);border:1px solid var(--line);border-radius:50%}
.honest{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2.2fr);gap:12px 32px;border-top:1px solid var(--line-2);padding-top:20px}
.honest h2{font:500 12px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.honest ul{list-style:none;margin:0;padding:0;display:grid;gap:11px;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr))}
.honest li{font-size:14px;color:var(--ink-2);line-height:1.5;padding-left:16px;position:relative}
.honest li::before{content:"";position:absolute;left:0;top:.6em;width:6px;height:6px;border-radius:2px;background:var(--amber)}
.honest li b{color:var(--ink);font-weight:600}
.secthead{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px 16px;border-top:1px solid var(--line-2);padding-top:20px}
.secthead h2{font:500 12px/1.4 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.secthead p{margin:0;font-size:13px;color:var(--ink-3);max-width:70ch}
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
.drawerclose{display:none}
.topfull{display:none}
.note.blocked{border-top-color:var(--reject);font-size:14px}
.copyfallback{font:12px var(--mono);width:min(100%,46ch);min-height:34px;padding:4px 8px;border:1px solid var(--line-2);border-radius:8px;background:var(--panel);color:var(--ink)}
#sharednote{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
#sharednote[hidden]{display:none}
#disctable{container-type:inline-size}
.themebtn{min-height:44px;justify-content:flex-start;gap:8px;font-size:13px}
.themebtn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.5}
.sidefoot .themebtn{justify-self:start;margin-bottom:6px}
.topbar .themebtn{display:none}
.dippicker{display:none}
.calcards{display:none}
.calcard{border-top:1px solid var(--line);padding-top:10px;margin:0}
#disctable caption{caption-side:top;text-align:left}
.capnote{position:sticky;left:0;display:block;max-width:min(100cqw,90ch);padding:11px 12px 0;font:12.5px/1.5 var(--sans);color:var(--ink-2)}
#archivenote{color:var(--amber);font-weight:500}
#archivenote+*,.capnote:last-child{padding-bottom:11px}
@media (max-width:1000px){
  .widget.size-S{grid-column:span 3}
  .agree li{grid-template-columns:minmax(0,1fr) auto}
  .agree li>:nth-child(2){grid-column:1/-1;grid-row:2}
  .instrument .igrid{grid-template-columns:minmax(0,1fr)}
  .instrument .fold{border-left:0;padding-left:0;border-top:1px solid var(--space-line);padding-top:12px}
  .honest{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:820px){
  .flow{grid-template-columns:repeat(2,minmax(0,1fr))}
  .flow li{border-left:0;border-top:1px solid var(--line)}
  .flow li:nth-child(-n+2){border-top:0}
  .flow li:nth-child(even){border-left:1px solid var(--line)}
  .flow li+li::before{display:none}
}
@media (max-width:699.98px){
  .topbar{display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:20;height:var(--top);padding:0 16px;background:color-mix(in oklab,var(--bg) 88%,transparent);-webkit-backdrop-filter:blur(16px) saturate(150%);backdrop-filter:blur(16px) saturate(150%);border-bottom:1px solid var(--line)}
  .topbar b{font:500 15px var(--display);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
  .topbar .cur{color:var(--muted);font-size:13px;white-space:nowrap}
  .menu{display:inline-flex;align-items:center;gap:8px}
  .menu svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8}
  .shell{display:block}
  .sidebar{background:var(--side);position:fixed;z-index:40;left:0;top:0;bottom:0;height:auto;width:min(280px,84vw);transform:translateX(-102%);visibility:hidden;transition:transform .18s ease,visibility 0s linear .18s;box-shadow:0 0 24px rgba(0,0,0,.25)}
  .sidebar.open{transform:none;visibility:visible;transition:transform .18s ease}
  .backdrop{display:block;position:fixed;inset:0;z-index:30;background:rgba(0,0,0,.35)}
  .backdrop[hidden]{display:none}
  main{padding:16px 16px 40px}
  .widgets{grid-template-columns:minmax(0,1fr)}
  .widget.size-S,.widget.size-M,.widget.size-L{grid-column:1/-1}
  .route>header .eyebrow{letter-spacing:.1em}
  .route{gap:20px}
  .hero-h{font-size:clamp(30px,8.6vw,40px);letter-spacing:-.04em}
  .consolebar{gap:6px 12px;font-size:11px}
  .consolebar .right{margin-left:0}
  .instrument{padding:14px 12px 12px}
  .instrument .ival{font-size:22px;text-align:left}
  .ctas .btn{flex:1 1 auto}
  .topbar .themebtn{display:inline-flex;margin-left:auto;padding:0 10px}
  .topbar .themebtn .themelbl{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
  .topbar .themebtn{min-width:44px;justify-content:center}
  body[data-route="candidates"] .topbar .themebtn{margin-left:0}
  /* Candidates: a dip picker above the frame, so no dip is a long scroll away inside it. */
  body[data-route="candidates"] .dippicker{display:flex;align-items:center;gap:10px;margin:8px 16px 4px;flex:none}
  .dippicker label{font:500 11px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
  .dippicker select{flex:1;min-width:0;min-height:44px;font:500 16px var(--mono);color:var(--ink);background:var(--panel);border:1px solid var(--line-2);border-radius:10px;padding:0 10px}
  /* Panel: the calibration rows as one card per reviewer. */
  #caltable{display:none}
  .calcards{display:grid;gap:4px}
  /* Feed: one card per entry, every value labelled; the column heads become a row of sort buttons. */
  #disctable{border:0;background:none;overflow:visible}
  #disctable table,#disctable thead,#disctable tbody,#disctable caption{display:block}
  #disctable thead tr{display:flex;flex-wrap:wrap;gap:6px;padding:0 0 10px}
  #disctable thead th{position:static;border:0;padding:0;background:none;box-shadow:none}
  #disctable thead th button{border:1px solid var(--line-2);border-radius:999px;padding:0 12px;background:var(--panel)}
  #disctable tbody tr{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px 12px;padding:12px 14px;margin-bottom:8px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
  #disctable tbody th,#disctable tbody td{display:block;position:static;border:0;padding:0;white-space:normal;text-align:left;background:none;box-shadow:none;min-width:0}
  #disctable tbody [data-label]::before{content:attr(data-label);display:block;font:500 11px/1.4 var(--mono);letter-spacing:.07em;text-transform:uppercase;color:var(--ink-3)}
  #disctable tbody .c-candidate_id,#disctable tbody .c-status{grid-column:1/-1}
  /* first line: TIC, SNR, depth; then the dip; then mid-time and period; then the status */
  #disctable tbody th{order:1}#disctable tbody .c-snr{order:2}#disctable tbody .c-depth_ppm{order:3}
  #disctable tbody .c-candidate_id{order:4}#disctable tbody .c-t_center{order:5}#disctable tbody .c-period_days{order:6}
  #disctable tbody .c-status{order:7}
  #disctable tbody td .dip{max-width:none}
  #disctable caption .capnote{padding:0 0 8px;position:static}
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

// ---------- overview hero: the stored light curve and the lead signal folded ----------
// Stored points only. The line is a plain mean of the stored points in fixed bins, drawn for reading;
// the dashed box in the fold sits at the stored depth and duration. Nothing is fitted.
function binMean(xs, ys, width){
  const out = [];
  let k0 = null, sx = 0, sy = 0, n = 0;
  for (let i = 0; i < xs.length; i++){
    const k = Math.floor(xs[i] / width);
    if (k !== k0 && n){ out.push([sx / n, sy / n, k0]); sx = sy = n = 0; }
    k0 = k; sx += xs[i]; sy += ys[i]; n++;
  }
  if (n) out.push([sx / n, sy / n, k0]);
  return out;
}
function meanPath(bins, X, Y){
  // A gap of more than one empty bin starts a new segment, so the line never bridges missing data.
  return bins.map((b, i) => `${i && b[2] - bins[i-1][2] <= 2 ? 'L' : 'M'}${X(b[0]).toFixed(1)},${Y(b[1]).toFixed(1)}`).join('');
}
function heroRange(){
  const L = D.hero.lead, depth = (L && L.depth_ppm) || Math.max(100, ...D.hero.windows.map(w => w.depth_ppm || 0));
  return [-2.6 * depth, 1.6 * depth];
}
let heroH = 300;
function heroCurve(box){
  box.innerHTML = '';
  const H0 = D.hero, subs = H0.subjects;
  if (!subs.length){ box.innerHTML = '<p class="empty">No light curve is stored for this run.</p>'; return; }
  const W = Math.max(280, box.clientWidth || 640), narrow = W < 520;
  const H = narrow ? 240 : 310, pl = 44, pr = 8, pt = 34, pb = 40;
  heroH = H;
  const a = subs[0].start, b = subs[subs.length - 1].end, [lo, hi] = heroRange();
  const X = t => pl + (t - a) / (b - a) * (W - pl - pr), Y = v => pt + (hi - v) / (hi - lo) * (H - pt - pb);
  const n = subs.reduce((s, x) => s + x.t.length, 0);
  let clipped = 0;
  for (const s of subs) for (const v of s.ppm) if (v < lo || v > hi) clipped++;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `Light curve of ${H0.target}: ${n} stored points, ${H0.time_unit} ${fmt(a,1)} to ${fmt(b,1)}, with ${H0.windows.length} marked windows: ` + H0.windows.map(w => `${w.letter} at ${fmt((w.t_start + w.t_end)/2, 2)}, ${w.outcome}`).join('; ') + `. Every window is a ${D.unconfirmed}.`}, box);
  svg.style.height = H + 'px';
  const cid = 'hc-clip';
  const defs = el('defs', {}, svg), cp = el('clipPath', {id: cid}, defs);
  el('rect', {x: pl, y: pt, width: W - pl - pr, height: H - pt - pb}, cp);
  for (const v of niceTicks(lo, hi, 4)){ el('line', {x1: pl, x2: W - pr, y1: Y(v), y2: Y(v), class: 'grid'}, svg); tx(svg, pl - 6, Y(v) + 3.5, String(v), 'end'); }
  // Marked windows, shaded by outcome and lettered in time order. Letters that would touch move up a row.
  let lastX = -99, row = 0;
  for (const w of H0.windows){
    const x1 = X(w.t_start), x2 = X(w.t_end), xm = (x1 + x2) / 2;
    const r = el('rect', {x: Math.min(x1, xm - 1.5), y: pt, width: Math.max(3, x2 - x1), height: H - pt - pb, class: 'win ' + w.outcome}, svg);
    el('title', {}, r).textContent = `${w.letter}: ${w.id} · ${w.outcome} · SNR ${fmt(w.snr,1)} · ${fmt(w.depth_ppm,0)} ppm · ${D.unconfirmed}`;
    row = xm - lastX < 14 ? 1 - row : 0; lastX = xm;
    tx(svg, xm, pt - 6 - row * 13, w.letter, 'middle', 'wl ' + w.outcome);
  }
  const pts = subs.map(s => s.t.map((t, i) => `M${X(t).toFixed(1)},${Y(s.ppm[i]).toFixed(1)}h0`).join('')).join('');
  el('path', {d: pts, class: 'pts', 'clip-path': `url(#${cid})`}, svg);
  for (const s of subs) el('path', {d: meanPath(binMean(s.t, s.ppm, 1/24), X, Y), class: 'mean', 'clip-path': `url(#${cid})`}, svg);
  const L = H0.lead;
  if (L && L.t0 !== null && L.t0 !== undefined){
    for (let k = Math.ceil((a - L.t0) / L.period_days); L.t0 + k * L.period_days <= b; k++){
      const xe = X(L.t0 + k * L.period_days);
      el('path', {d: `M${xe.toFixed(1)},${H - pb + 1} l-4,7 h8 z`, class: 'epoch'}, svg);
    }
  }
  el('line', {x1: pl, x2: W - pr, y1: H - pb, y2: H - pb, class: 'axis'}, svg);
  // Tick labels sit on their own row above the unit label, so the two never touch.
  for (const t of niceTicks(a, b, narrow ? 3 : 6)){ if (t < a || t > b) continue; tx(svg, X(t), H - pb + 16, String(t), 'middle'); }
  tx(svg, pl - 6, pt - 20, 'ppm', 'end');
  tx(svg, W - pr, H - 2, `time (${H0.time_unit})`, 'end');
  $('#herocurvecap').textContent = `${n.toLocaleString()} stored points, ${H0.time_unit} ${fmt(a,1)} to ${fmt(b,1)}. Shaded: the ${H0.windows.length} windows the reviewers marked, lettered in time order.` + (clipped ? ` ${clipped} point${clipped === 1 ? '' : 's'} outside the drawn range are not shown.` : '');
}
function heroFold(box){
  box.innerHTML = '';
  const L = D.hero.lead;
  if (!L || L.t0 === null || L.t0 === undefined){ box.closest('figure').hidden = true; return; }
  const W = Math.max(240, box.clientWidth || 300), H = heroH;
  const pl = 44, pr = 8, pt = 34, pb = 40, dur = (L.duration_days || 0.1) * 24, half = Math.max(3 * dur, 6);
  const [lo, hi] = heroRange(), ph = [], pv = [];
  for (const s of D.hero.subjects) s.t.forEach((t, i) => { const h = (((t - L.t0) % L.period_days + 1.5 * L.period_days) % L.period_days - L.period_days / 2) * 24; if (h >= -half && h <= half){ ph.push(h); pv.push(s.ppm[i]); } });
  const X = h => pl + (h + half) / (2 * half) * (W - pl - pr), Y = v => pt + (hi - v) / (hi - lo) * (H - pt - pb);
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `The lead signal folded on its stored period ${fmt(L.period_days,4)} d and t0 ${fmt(L.t0,4)}: ${ph.length} stored points within ${fmt(half,1)} h of mid-transit. Dashed: a box at the stored depth ${fmt(L.depth_ppm,0)} ppm and duration ${fmt(dur,1)} h, not a fit.`}, box);
  svg.style.height = H + 'px';
  const defs = el('defs', {}, svg), cp = el('clipPath', {id: 'hf-clip'}, defs);
  el('rect', {x: pl, y: pt, width: W - pl - pr, height: H - pt - pb}, cp);
  el('rect', {x: X(-dur / 2), y: pt, width: X(dur / 2) - X(-dur / 2), height: H - pt - pb, class: 'dur'}, svg);
  for (const v of niceTicks(lo, hi, 4)){ el('line', {x1: pl, x2: W - pr, y1: Y(v), y2: Y(v), class: 'grid'}, svg); tx(svg, pl - 6, Y(v) + 3.5, String(v), 'end'); }
  el('path', {d: ph.map((h, i) => `M${X(h).toFixed(1)},${Y(pv[i]).toFixed(1)}h0`).join(''), class: 'pts', 'clip-path': 'url(#hf-clip)'}, svg);
  const order = ph.map((h, i) => i).sort((p, q) => ph[p] - ph[q]);
  el('path', {d: meanPath(binMean(order.map(i => ph[i]), order.map(i => pv[i]), 0.5), X, Y), class: 'mean', 'clip-path': 'url(#hf-clip)'}, svg);
  el('path', {d: `M${X(-half)},${Y(0)}H${X(-dur/2)}V${Y(-L.depth_ppm)}H${X(dur/2)}V${Y(0)}H${X(half)}`, class: 'box'}, svg);
  el('line', {x1: pl, x2: W - pr, y1: H - pb, y2: H - pb, class: 'axis'}, svg);
  for (const h of niceTicks(-half, half, 4)) tx(svg, X(h), H - pb + 16, String(h), 'middle');
  tx(svg, X(0), pt - 6, (L.letters || []).join(' '), 'middle', 'wl ' + L.outcome);
  tx(svg, W - pr, H - 2, 'hours from mid-transit', 'end');
  $('#herofoldcap').textContent = `Folded on the stored period ${fmt(L.period_days,4)} d and t0 ${fmt(L.t0,3)}. Line: 30-minute mean of the stored points. Dashed: a box at the stored depth and duration, not a fit.`;
}
let heroWidth = -1;
function renderHero(force){
  const box = $('#herocurve');
  if (!box || (!force && box.clientWidth === heroWidth)) return;
  heroWidth = box.clientWidth;
  heroCurve(box); heroFold($('#herofold'));
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
  renderHero(false); renderWidgets(); syncLayoutURL();
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
// push: the viewer changed the sort or the filter, so Back returns to the previous view.
function syncFeedURL(push){
  if (current !== 'discoveries') return;
  setHash('#/discoveries?' + encodeFeedView(currentFeedView()), !!push);
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
  $('#disccount').textContent = `${rows.length} of ${D.catalog.candidates.length} entries shown.`;
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
  $(`#disctable button[data-sort="${k}"]`).focus();
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
    else if (ar.status !== 'not_stored') arch = `<p style="margin:0"><b>Published planets.</b> ${esc(D.no_detection)}</p><ul>${ar.planets.map(p => `<li><b>${esc(p.pl_name)}</b> · host ${esc(p.hostname)} · P ${p.pl_orbper !== null && p.pl_orbper !== undefined ? esc(p.pl_orbper) + ' d' : 'not listed'} · ${p.tran_flag ? 'transiting' : 'not known to transit'}${p.rv_flag ? ' · radial-velocity detection' : ''}</li>`).join('')}</ul><p class="muted" style="margin:4px 0 0;font-size:12px">${esc(ar.source)}, fetched ${when(ar.fetched_at)}.</p>`;
    const hid = 'pl-' + String(s.star).replace(/\W/g,'_');
    return `<article class="card" aria-labelledby="${hid}"><h2 id="${hid}">${esc(s.star)} <span class="muted" style="font:500 11px var(--mono)">${esc(s.sources.join(' · '))} · ${s.entries.length} entr${s.entries.length===1?'y':'ies'}</span></h2>${rows}${arch ? `<div class="archive">${arch}</div>` : ''}</article>`;
  }).join('') : '<p class="empty">No stars in the run or the feed.</p>';
}

// ---------- panel ----------
function renderPanel(){
  renderCalibration(); calWidth = $('#calplane').clientWidth;
  const ag = D.agreement;
  $('#agreement').innerHTML = ag.length ? `<ul class="agree">${ag.map(a => `<li>
      <span>${dipLink(a.id)}<small class="muted" style="display:block;font-size:11px">${esc(a.target)} · ${esc(a.outcome_label)} · ${esc(D.unconfirmed)}</small></span>
      <span><b>${a.n} of ${a.of} reviewers</b> marked it: ${a.n_sim} of ${a.of_sim} simulated, ${a.n_claude} of ${a.of_claude} Claude<small class="muted" style="display:block;font-size:11px;font-family:var(--mono)">${esc(a.reviewers.join(', ') || 'none')}</small></span>
      <a href="${dipHref(a.id, 'ledger')}">Verdict ledger</a></li>`).join('')}</ul>` : '<p class="empty">The run stored no dips.</p>';
  $('#panelcards').innerHTML = D.panel.length ? D.panel.map(r => `<article class="card"><h2 class="mono">${esc(r.id)}</h2>
    <p style="margin:6px 0 0">${kindTag(r.kind)}</p>
    <p class="muted" style="margin:6px 0 0;font-size:13px">${r.kind === 'simulated' ? 'Code that marks dips above an SNR threshold in the light curve. It is not a person.' : isClaude(r.kind) ? 'A Claude model that reads the plotted light curve and marks dips. It is not a person.' : ''}</p>
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
  // pad keeps a point at FPR 0 clear of the axis labels. Narrow drops the floor-region note and the rotated
  // weight labels: each weight is written level, above the right-hand end of its line, in a top band of its own.
  const W = Math.min(560, Math.max(260, box.clientWidth || 520)), narrow = W < 420, pl = 46, pr = 14, pt = narrow ? 40 : 12, pb = 42;
  const pad = 14, side = W - pl - pr - pad, H = pt + side + pb;
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
  // On a phone the same rows read as one card per reviewer (the table is hidden there, the cards elsewhere).
  $('#calcards').innerHTML = C.points.map(p => `<dl class="kv calcard"><dt>reviewer</dt><dd><b>${esc(p.id)}</b></dd><dt>kind</dt><dd>${kindWord(p.kind)}</dd><dt>recall (TPR)</dt><dd>${fmt(p.tpr,2)}</dd><dt>false alarms (FPR)</dt><dd>${fmt(p.fpr,2)}</dd><dt>weight</dt><dd>${fmt(p.weight,2)}${p.consistent === false ? ' (not max(TPR − FPR, floor))' : ''}</dd><dt>sample</dt><dd>${esc(fmtN(p))}</dd></dl>`).join('');
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
  return {route: ROUTES.includes(route) ? route : 'overview', unknown: ROUTES.includes(route) ? null : route,
          params: new URLSearchParams(q < 0 ? '' : body.slice(q + 1))};
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
  // An unknown section: rewrite the address to the Overview, and say so.
  if (p.unknown){ setHash('#/overview', false); say(`No section ${p.unknown}; showing the Overview.`); p = {route: 'overview', params: new URLSearchParams()}; }
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
// Back and Forward: hashchange for typed or linked hashes, popstate for entries made by pushState.
// Either way the shell re-reads the hash and pushes the dip (or the Feed view) into the view.
function onNavigate(){ const p = parseHash(location.hash); if (!p) return; closeDrawer(false); go(p, true); }
window.addEventListener('hashchange', onNavigate);
window.addEventListener('popstate', onNavigate);
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
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (!$('#route-discoveries').hidden) renderDiscCharts(false); if (!$('#route-overview').hidden) renderHero(false); resizeCalibration(); fitFrame(); }, 120); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitFrame);  // web fonts can rewrap the header
// ---------- theme: system, light or dark ----------
// The choice is stored as exoplan-theme (when storage is allowed); the head script applies it before
// first paint. The Docket frame is told too, so it follows.
const THEMES = ['system', 'light', 'dark'], THEME_NAME = {system: 'System', light: 'Light', dark: 'Dark'};
function currentTheme(){ const t = document.documentElement.getAttribute('data-theme'); return t === 'light' || t === 'dark' ? t : 'system'; }
function applyTheme(t){
  if (t === 'system') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
  try { const s = getStorage(); if (s){ if (t === 'system') s.removeItem('exoplan-theme'); else s.setItem('exoplan-theme', t); } } catch (e) { /* storage blocked: the theme lasts for this visit */ }
  for (const b of $$('[data-theme-toggle]')){ b.setAttribute('aria-label', `Colour theme: ${THEME_NAME[t].toLowerCase()}. Change theme`); b.querySelector('.themelbl').textContent = THEME_NAME[t]; }
  try { $('#docketframe').contentWindow.postMessage({source: 'exoplan-shell', theme: t}, '*'); } catch (e) { /* no frame yet */ }
}
for (const b of $$('[data-theme-toggle]')) b.addEventListener('click', () => { const t = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]; applyTheme(t); say(`Theme: ${THEME_NAME[t]}.`); });
applyTheme(currentTheme());
$('#dippick').addEventListener('change', e => { location.hash = dipHref(e.target.value); });
go(parseHash(location.hash) || {route: 'overview', params: new URLSearchParams()}, false);
"""


# Before first paint: apply the stored theme choice (system, light or dark), so the page never flashes.
THEME_KEY = "exoplan-theme"
THEME_HEAD_JS = ("(function(){try{var t=localStorage.getItem('" + THEME_KEY + "');"
                 "if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();")
THEME_BUTTON = ('<button class="btn themebtn" type="button" data-theme-toggle aria-label="Colour theme: system. Change theme">'
                '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 2.5v11" /><path d="M8 2.5a5.5 5.5 0 0 1 0 11z" fill="currentColor"/></svg>'
                '<span class="themelbl">System</span></button>')


def _nav(sections: list[dict]) -> str:
    items = "".join(
        f'<li><a href="#/{s["id"]}" data-route="{s["id"]}"><svg viewBox="0 0 16 16" aria-hidden="true">{ICONS[s["id"]]}</svg>{html.escape(s["label"])}'
        f'<span class="ix" aria-hidden="true">{i:02d}</span></a></li>'
        for i, s in enumerate(sections, 1)
    )
    return f'<nav class="nav" aria-label="Sections"><ul>{items}</ul></nav>'


def _hero(data: dict) -> str:
    """The Overview's opening: the argument, the stored light curve, the vetting flow, and what the page does not claim."""
    e = html.escape
    h, run, cfg = data["hero"], data["run"], data["config"]
    inp = (cfg.get("inputs") or [{}])[0]
    dc, c = run.get("docket_counts") or {}, run.get("counts") or {}
    lead = h.get("lead")
    feed_label_ = next((s["label"] for s in data["sections"] if s["id"] == "discoveries"), "Discoveries")
    source = " · ".join(str(x) for x in (inp.get("mission"), f"sector {inp['sector']}" if inp.get("sector") is not None else None,
                                          inp.get("author"), f"{inp['exptime_s']} s" if inp.get("exptime_s") else None) if x)
    open_lead = (f'<a class="btn primary" href="#/candidates?dip={e(lead["dip"])}">Open the lead dip in the Docket <span aria-hidden="true">→</span></a>'
                 if lead and lead.get("dip") else '<a class="btn primary" href="#/candidates">Open the Docket <span aria-hidden="true">→</span></a>')
    value = (f'<div class="ival">{lead["depth_ppm"]:,.0f} ppm<small>lead signal depth, median of {lead["n_dips"]} dips</small></div>'
             if lead and lead.get("depth_ppm") else "")
    cal = data.get("calibration") or {}
    n_inj = max([p.get("n_injected") or 0 for p in cal.get("points") or []] or [0])
    weights = (f" Their weights rest on calibration with {n_inj} injected subjects, so they are rough." if n_inj else "")
    flow = [
        ("", c.get("subjects", "–"), f"light-curve subjects of {cfg.get('subject_days') or '–'} days", "input"),
        ("", c.get("classifications", "–"), f"reviews from {dc.get('reviewers', '–')} reviewers, none of them a person", "marks"),
        ("", dc.get("dips", "–"), "dips the panel agreed on", "consensus"),
        ("", dc.get("signals", "–"), "signals, once repeat dips are grouped", "grouping"),
    ]
    flow_html = "".join(f'<li class="{k}"><small>{e(sm)}</small><b>{e(str(v))}</b><span>{e(t)}</span></li>' for k, v, t, sm in flow)
    flow_html += (f'<li class="vet"><small>vetting, signals by outcome</small><div class="vet3">'
                  f'<span class="pass"><b>{e(str(dc.get("passed", 0)))}</b>passed</span>'
                  f'<span class="flag"><b>{e(str(dc.get("flagged", 0)))}</b>flagged</span>'
                  f'<span class="rej"><b>{e(str(dc.get("rejected", 0)))}</b>rejected</span></div>'
                  f'<span>Passing makes a {UNCONFIRMED}, not a planet.</span></li>')
    return f"""<div class="hero">
        <div class="consolebar" aria-label="Run summary">
          <span class="live"><i></i>Stored run</span><span class="sep"></span>
          <span>Run <b>{e(run["name"])}</b></span><span class="sep"></span>
          <span>{e(source or "stored input")}</span><span class="sep"></span>
          <span><b>{e(h["target"])}</b></span>
          <span class="right">config <b>{e((cfg.get("config_sha256") or "")[:12] or "not stored")}</b></span>
        </div>
        <div class="hero-copy">
          <h1 class="hero-h" id="h-overview" tabindex="-1">{e(h["headline"])} <em>{e(h["accent"])}</em></h1>
          <p class="lede">{e(h["lede"])} Every one is a <b>{UNCONFIRMED}</b>.</p>
          <p class="lede" style="font-size:14.5px;color:var(--ink-3)">{e(h["archive"])}</p>
          <div class="ctas">{open_lead}<a class="btn ghost" href="#/discoveries">See the {e(feed_label_)}</a></div>
        </div>
        <section class="instrument" aria-labelledby="h-lc">
          <div class="ihead"><div class="ititle"><span id="h-lc">The light curve · {e(h["target"])}</span><small>{e(source or "stored input")} · {e(inp.get("flux_column") or "flux")} · normalised, in ppm</small></div>{value}</div>
          <div class="igrid">
            <figure><div id="herocurve"></div><figcaption id="herocurvecap"></figcaption></figure>
            <figure class="fold"><div id="herofold"></div><figcaption id="herofoldcap"></figcaption></figure>
          </div>
          <div class="ikey"><span><i class="k-passed"></i>passed vetting</span><span><i class="k-flagged"></i>flagged</span><span><i class="k-rejected"></i>rejected</span><span><i class="k-mean"></i>1-hour mean of the stored points, for reading only</span>{'<span><i class="k-ep"></i>transit times predicted by the stored period and t0</span>' if lead else ''}<span class="unc">each window: {UNCONFIRMED}</span></div>
        </section>
      </div>
      <section aria-labelledby="h-flow" style="display:grid;gap:14px">
        <div class="secthead"><h2 id="h-flow">02 · How the dips were vetted</h2><p>Read left to right. Counts from manifest.json and the Docket; nothing is re-estimated here.</p></div>
        <ol class="flow">{flow_html}</ol>
      </section>
      <section class="honest" aria-labelledby="h-honest">
        <h2 id="h-honest">03 · What this page does not claim</h2>
        <ul>
          <li><b>No confirmed planet.</b> Every dip, signal and feed entry here is a {UNCONFIRMED}. Passing vetting is not a confirmation.</li>
          <li><b>No planet sizes.</b> No stellar radius is stored, so a depth gives only a planet-to-star radius ratio. The Planets section shows the working.</li>
          <li><b>No people on the panel.</b> The reviewers are simulated detectors and Claude model calls.{e(weights)}</li>
          <li><b>{e(NO_DETECTION.split(". ")[0])}.</b> {e(NO_DETECTION.split(". ", 1)[1])} A TOI or archive match compares a stored period with published values.</li>
        </ul>
      </section>"""


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
    description = (f"exoplan run {run['name']}: {data['hero']['headline']} Every dip is a {UNCONFIRMED}; "
                   f"stored values only.")
    xm_targets = ", ".join(html.escape(str(t)) for t in data.get("crossmatch_targets") or []) or "no star"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{html.escape(description)}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#E8ECF3" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#060A14" media="(prefers-color-scheme: dark)">
<link rel="icon" href="data:,">
<script>{THEME_HEAD_JS}</script>
<link rel="stylesheet" href="{FONTS_CSS}">
<style>{APP_CSS}</style></head>
<body>
<a class="skip" href="#content">Skip to the section</a>
<header class="topbar">
  <button class="btn menu" id="menubtn" aria-expanded="false" aria-controls="sidebar"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12"/></svg>Menu</button>
  <b>{title}</b><span class="cur" id="curlabel"></span>
  {THEME_BUTTON}
  <a class="topfull" id="topfull" href="../docket/">Full page</a>
</header>
<div class="shell">
  <aside class="sidebar" id="sidebar" aria-label="{title} sections">
    <button class="btn drawerclose" id="drawerclose" type="button"><span aria-hidden="true">✕</span> Close menu</button>
    <div class="brand"><b>{title}</b><span>run {html.escape(run["name"])}</span></div>
    <p class="navlabel" aria-hidden="true">Sections</p>
    {_nav(data["sections"])}
    <div class="sidefoot">{THEME_BUTTON}<span class="stored"><i></i>Stored values only</span><span>built from {html.escape(run["dir"])}</span><span>{html.escape(data["catalog"]["path"] or "no catalogue")}</span></div>
  </aside>
  <div class="backdrop" id="backdrop" hidden></div>
  <main id="main">
   <div id="content" tabindex="-1">
    <section class="route" id="route-overview" data-route="overview" aria-labelledby="h-overview" hidden>
      <header><p class="eyebrow"><span class="idx">01</span>Overview</p></header>
      {_hero(data)}
      <div class="secthead"><h2 id="h-view">04 · Your view</h2><p>Each widget's header can hide it, move it or set its size. Your changes are kept in this browser as your default when storage is allowed. Copy link to this layout shares it; a shared layout shows for that view only and never replaces the recipient's default.</p></div>
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
      <header><p class="eyebrow"><span class="idx">02</span>Candidates</p><h1 class="lead-h" id="h-candidates" tabindex="-1">Every signal, its dips, and the checks behind each verdict.</h1><p>The Docket for run {html.escape(run["name"])}: every signal and its dips, with the vetting outcome, the transit strip and the verdict ledger. Every signal here is a {unc}.</p></header>
      <div class="frametools"><a id="fullpage" href="../docket/">Open full page</a><span class="muted">The Docket on its own page, at the same dip.</span></div>
      <div class="dippicker"><label for="dippick">Dip</label><select id="dippick" aria-describedby="dippickhint"></select><span class="sr" id="dippickhint">Every dip in this run, lettered in time order, with its vetting outcome. Each is a {unc}.</span></div>
      <p class="note" id="framestatus" role="status" hidden></p>
      <p class="note blocked" id="frameblocked" role="alert" hidden>The dossier could not load in this view. <a id="blockedlink" href="../docket/">Open it on its own page.</a></p>
      <iframe class="frame waiting" id="docketframe" title="Docket for run {html.escape(run["name"])}: signals, dips and vetting"></iframe>
    </section>
    <section class="route" id="route-discoveries" data-route="discoveries" aria-labelledby="h-discoveries" hidden>
      <header><p class="eyebrow"><span class="idx">03</span>{label["discoveries"]}</p><h1 class="lead-h" id="h-discoveries" tabindex="-1">What the discovery runs admitted, and how much of it the archive already knows.</h1><p>The feed from the discovery catalogue: {len(feed)} entries, {n_known} of them match a known TOI period. Every entry is a {unc}: a dip the panel marked, not a planet.{f" A TOI match is an archive comparison. {nodet}" if n_known else ""}</p></header>
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
    <section class="route" id="route-planets" data-route="planets" aria-labelledby="h-planets" hidden>
      <header><p class="eyebrow"><span class="idx">04</span>Planets</p><h1 class="lead-h" id="h-planets" tabindex="-1">What each depth would imply, if it were a planet.</h1><p>One card per star in the run or the feed. Each entry is a {unc}; the ratio below is what its stored depth implies if it were a planet.</p></header>
      <p class="note"><b>Radius ratio only.</b> Rp/R* = √depth, with depth as a fraction (ppm × 10⁻⁶). This assumes a full, undiluted transit and ignores limb darkening. {html.escape(NO_STELLAR_RADIUS)} Each bar is a ratio scale from 0 to {data["ratio_scale_max"]:.2f}, the same on every card.</p>
      <p class="note">Published planets come from the stored archive cross-match ({html.escape(data.get("crossmatch_file") or "crossmatch.json")}), which covers {xm_targets}. The other stars have no stored cross-match, so their cards have no archive box. {nodet}</p>
      <div class="cards" id="planetcards"></div>
    </section>
    <section class="route" id="route-panel" data-route="panel" aria-labelledby="h-panel" hidden>
      <header><p class="eyebrow"><span class="idx">05</span>Panel</p><h1 class="lead-h" id="h-panel" tabindex="-1">Who marked the dips, and how far to trust each of them.</h1><p>The reviewers that marked dips in run {html.escape(run["name"])}. Simulated reviewers are code; Claude reviewers are model calls. None of them is a person.</p></header>
      <p class="note rule"><b>Weights.</b> A reviewer's weight is its calibration skill from injection tests: the true-positive rate on injected transits minus the false-positive rate on empty light curves, floored (calibrate.py). The calibrated weights are stored in {html.escape(data["weights_path"] or "no weights file")}. The weight in this run is the one manifest.json records; when it differs from the calibrated weight, the run did not use the calibrated weights.</p>
      <section class="card" aria-labelledby="h-cal" style="display:grid;gap:8px">
        <h2 id="h-cal">Calibration plane</h2>
        <p class="muted" style="margin:0;font-size:13px">Each reviewer at its false-alarm rate (x: share of empty subjects it marked) and recall (y: share of injected transits it found) in calibration. Point size is its calibrated weight. The lines join points of equal weight, weight = TPR − FPR, floored at {data["calibration"]["floor"]}; up and to the left is better. Stored values only.</p>
        <div class="legend"><span><i class="k-sim"></i>simulated detector, not a person</span><span><i class="k-cl"></i>Claude reviewer, not a person</span><span>size: calibrated weight</span></div>
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
    </section>
    <section class="route" id="route-runs" data-route="runs" aria-labelledby="h-runs" hidden>
      <header><p class="eyebrow"><span class="idx">06</span>Runs</p><h1 class="lead-h" id="h-runs" tabindex="-1">Every discovery run, its errors as stored, and the configuration behind this page.</h1><p>The discovery run history from the catalogue, and the configuration of run {html.escape(run["name"])}. Error messages are shown as stored.</p></header>
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
              weights_path: str | Path | None = DEFAULT_WEIGHTS, star: str | None = None,
              require_crossmatch: bool = False) -> Path:
    data = app_data(run_dir, title=title, catalog_path=catalog_path, weights_path=weights_path, star=star,
                    require_crossmatch=require_crossmatch)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(app_page(data))
    # The fonts the page links to, self-hosted beside it (as Kshana serves them).
    import shutil

    shutil.copytree(FONTS_DIR, out / "assets" / "fonts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return path

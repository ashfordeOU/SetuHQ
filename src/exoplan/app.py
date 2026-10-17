"""The exoplan app shell: one self-contained page with a sidebar and six sections.

Each section is a route in the URL hash (``#/overview``, ``#/candidates``,
``#/discoveries``, ``#/planets``, ``#/panel``, ``#/runs``), with an optional
query: ``#/candidates?dip=<candidate_id>`` opens the Docket on that dip and
``#/overview?layout=kpis.L,top.L,...`` carries a widget layout. Hashes that do
not start with ``#/`` (the skip link's ``#content``) are not routes.

* Overview: a widget grid (run figures, feed count, recent runs, top
  candidates). Each widget's header hides it, moves it and sets its size; the
  layout lives in the URL and, when the browser allows it, in localStorage as
  the viewer's default.
* Candidates: the Docket, rendered by :mod:`exoplan.docket` and embedded as an
  inline frame, so its code, honesty rules and keyboard handling are unchanged.
  The dip id is handed to the frame as its location hash, which the Docket reads.
* Discoveries (titled "Feed" when most entries match a known TOI): the feed
  from the discovery catalogue, with histograms and a timeline by star.
* Planets: one card per star with the planet-to-star radius ratio sqrt(depth).
  No stellar radius is stored, so nothing is converted to Earth or Jupiter radii.
* Panel: which reviewers marked each dip, and one card per reviewer.
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
    calibrated, weights_name = None, ""
    if weights_path is not None and Path(weights_path).exists():
        calibrated = json.loads(Path(weights_path).read_text())
        weights_name = str(weights_path)
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
        "status_label": STATUS_LABEL,
        "planets": planet_cards(cands, run_name, feed, crossmatch),
        "crossmatch_line": crossmatch.get("line", ""),
        "crossmatch_targets": crossmatch.get("targets") or [],
        "panel": panel_cards(manifest, run["marks"], run["reviewerDecisions"], calibrated, cands),
        "agreement": dip_agreement(cands, dock["reviewers"]),
        "weights_path": weights_name,
        "docket_html": docket_page(dock),
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
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.skip{position:absolute;left:8px;top:-60px;background:var(--ink);color:var(--paper);padding:8px 12px;border-radius:4px;z-index:50}
.skip:focus{top:8px}
#content:focus{outline:none}
.topbar{display:none}
.shell{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh;background:linear-gradient(to right,var(--side) 231px,var(--rule) 231px,var(--rule) 232px,transparent 232px)}
.sidebar{background:var(--side);border-right:1px solid var(--rule);position:sticky;top:0;height:100vh;overflow:auto;display:flex;flex-direction:column;gap:16px;padding:18px 0}
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
.frame{width:100%;height:calc(100vh - 190px);min-height:520px;border:1px solid var(--rule);border-radius:8px;background:var(--paper);display:block}
.drawerclose{display:none}
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
  th button{min-height:44px}
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
let layout = readLayout(getStorage(), LAYOUT_KEY, WIDGET_IDS, D.default_size);
function saveLayout(){ try { const s = getStorage(); if (s) s.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch (e) { /* storage blocked: the layout lasts for this visit */ } }
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
      const head = `<div><b>${esc(f.target)}</b> <span class="muted">· signal ${f.period_days ? 'P ' + fmt(f.period_days,3) + ' d' : 'with no period (one transit)'} · ${n} of the top dips${f.signal_dips > n ? `, ${f.signal_dips} dips in the run` : ''}</span></div>`;
      const note = xm ? `<p class="note">Archive cross-match: ${n === 1 ? 'this dip is' : `these ${n} dips are`} consistent with <b>${esc(xm.consistent_with)}</b>, a published planet${xm.dP_pct !== null && xm.dP_pct !== undefined ? ` (period difference ${fmt(xm.dP_pct,2)}%)` : ''}. ${n === 1 ? 'It is a transit' : 'They are repeat transits'} of one known planet, not ${n === 1 ? 'a discovery' : n + ' discoveries'}. ${esc(D.no_detection)}</p>` : '';
      return `<li>${head}${note}<ul>${g.dips.map(x => `<li>${dipLink(x.id)}<span class="mono">SNR ${fmt(x.snr,1)}</span><span class="mono">${fmt(x.depth_ppm,0)} ppm</span><span>${esc(x.outcome_label)}</span><span class="muted">${esc(D.unconfirmed)}</span></li>`).join('')}</ul></li>`;
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
function renderOverview(){ renderWidgets(); syncLayoutURL(); }
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
$('#resetlayout').addEventListener('click', () => { layout = normaliseLayout(null, WIDGET_IDS, D.default_size); saveLayout(); renderOverview(); $('#resetlayout').focus(); say('Layout reset: every widget shown in the default order and size.'); });

// ---------- candidates (the Docket) ----------
const DOCKET_SECTIONS = ['strip', 'signal', 'ctx', 'cmp', 'ledger', 'rev'];
// The Docket reads a dip id from its own location hash on load, so the frame loads the Docket page
// from a blob URL with the dip as that hash. (A srcdoc frame cannot carry a hash.)
let docketBlob = null;
function docketURL(dip){
  try { if (!docketBlob) docketBlob = URL.createObjectURL(new Blob([D.docket_html], {type: 'text/html'})); } catch (e) { docketBlob = null; }
  return docketBlob ? docketBlob + (dip ? '#' + encodeURIComponent(dip) : '') : null;
}
function frameSelect(dip){
  try { const w = $('#docketframe').contentWindow; if (typeof w.select === 'function'){ w.select(dip, false); return true; } } catch (e) { /* not reachable */ }
  return false;
}
function scrollDocketTo(section){
  if (!DOCKET_SECTIONS.includes(section)) return;
  // scrollIntoView would also scroll this page; keep the shell where it is and move only the frame.
  const y = window.scrollY;
  try { const s = $('#docketframe').contentDocument.getElementById('sec-' + section); if (s) s.scrollIntoView({block: 'start'}); } catch (e) { /* frame not reachable: the dossier is still open */ }
  window.scrollTo(0, y);
}
function loadDocket(dip, section){
  const f = $('#docketframe'), url = docketURL(dip);
  f.addEventListener('load', () => {
    // Without a blob URL the Docket opens on its default dip; select the one asked for.
    if (dip && !url) frameSelect(dip);
    if (section) scrollDocketTo(section);
  }, {once: true});
  if (url){ f.removeAttribute('srcdoc'); f.src = url; } else f.srcdoc = D.docket_html;
}
function openDip(dip, section){
  const f = $('#docketframe');
  if (dip && !DIP_IDS.has(dip)){ say(`No dossier for ${dip} in this run.`); dip = null; }
  $('#fullpage').href = '../docket/' + (dip ? '#' + encodeURIComponent(dip) : '');
  if (!f.dataset.loaded){ f.dataset.loaded = '1'; loadDocket(dip, section); }
  else if (dip){
    if (frameSelect(dip)){ if (section) scrollDocketTo(section); }
    else loadDocket(dip, section);
  }
  if (dip) say(`Docket open on dip ${dip}${section === 'ledger' ? ', verdict ledger' : ''}.`);
}
function renderCandidates(){ /* the frame loads in openDip, with the dip from the URL */ }

// ---------- discoveries (the feed) ----------
const disc = {sort: 'snr', dir: -1, filter: 'all'};
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
function renderDiscTable(){
  const rows = discRows();
  $('#disctable').innerHTML = `<table><caption class="sr">Feed, sorted by ${esc(disc.sort)} ${disc.dir > 0 ? 'ascending' : 'descending'}. Every entry is a ${esc(D.unconfirmed)}.</caption>
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
  renderDiscTable();
  $(`#disctable button[data-sort="${k}"]`).focus();
  say(`Sorted by ${b.textContent.replace(/[▲▼]/g,'')}, ${disc.dir > 0 ? 'ascending' : 'descending'}.`);
});
$('#discchips').addEventListener('click', e => {
  const b = e.target.closest('button[data-f]'); if (!b) return;
  disc.filter = b.dataset.f; renderDiscChips(); renderDiscTable();
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
    else if (ar.status !== 'not_stored') arch = `<p style="margin:0"><b>Published planets (archive values only).</b> ${esc(D.no_detection)}</p><ul>${ar.planets.map(p => `<li><b>${esc(p.pl_name)}</b> · host ${esc(p.hostname)} · P ${p.pl_orbper !== null && p.pl_orbper !== undefined ? esc(p.pl_orbper) + ' d' : 'not listed'} · ${p.tran_flag ? 'transiting' : 'not known to transit'}${p.rv_flag ? ' · radial-velocity detection' : ''}</li>`).join('')}</ul><p class="muted" style="margin:4px 0 0;font-size:12px">${esc(ar.source)}, fetched ${when(ar.fetched_at)}.</p>`;
    const hid = 'pl-' + String(s.star).replace(/\W/g,'_');
    return `<article class="card" aria-labelledby="${hid}"><h2 id="${hid}">${esc(s.star)} <span class="muted" style="font:12px 'JetBrains Mono',monospace">${esc(s.sources.join(' · '))} · ${s.entries.length} entr${s.entries.length===1?'y':'ies'}</span></h2>${rows}${arch ? `<div class="archive">${arch}</div>` : ''}</article>`;
  }).join('') : '<p class="empty">No stars in the run or the feed.</p>';
}

// ---------- panel ----------
function renderPanel(){
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
  $('#curlabel').textContent = label;
  if (r === 'overview') renderOverview();
  else if (!rendered.has(r)){ RENDER[r](); rendered.add(r); }
  else if (r === 'discoveries') renderDiscCharts(false);
  if (moveFocus){ const h = $('#route-' + r + ' h1'); if (h) h.focus({preventScroll: true}); window.scrollTo(0, 0); }
}
function go(p, moveFocus){
  const changed = p.route !== current;
  if (p.route === 'overview' && p.params.has('layout')) layout = decodeLayout(p.params.get('layout'), WIDGET_IDS, D.default_size);
  current = p.route;
  show(p.route, moveFocus && changed);
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
function openDrawer(){
  side.classList.add('open'); backdrop.hidden = false; menu.setAttribute('aria-expanded', 'true');
  $('#main').inert = true; $('.topbar').inert = true;
  document.body.style.overflow = 'hidden';
  const cur = $('.nav a[aria-current="page"]') || $('.nav a'); setTimeout(() => cur.focus(), 20);
}
function closeDrawer(returnFocus){
  if (!side.classList.contains('open')) return;
  side.classList.remove('open'); backdrop.hidden = true; menu.setAttribute('aria-expanded', 'false');
  $('#main').inert = false; $('.topbar').inert = false;
  document.body.style.overflow = '';
  if (returnFocus) menu.focus();
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
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (!$('#route-discoveries').hidden) renderDiscCharts(false); }, 120); });
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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{html.escape(GOOGLE_FONTS)}">
<style>{APP_CSS}</style></head>
<body>
<a class="skip" href="#content">Skip to the section</a>
<header class="topbar">
  <button class="btn menu" id="menubtn" aria-expanded="false" aria-controls="sidebar"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12"/></svg>Menu</button>
  <b>{title}</b><span class="cur" id="curlabel"></span>
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
      <header><h1 id="h-overview" tabindex="-1">Overview</h1><p>Run {html.escape(run["name"])} and the feed at a glance. Each widget's header can hide it, move it or set its size. The layout is kept in the address bar, so a link shares it, and in this browser as your default when storage is allowed.</p></header>
      <div class="layoutbar" role="group" aria-label="Layout">
        <div class="layoutbar" id="hiddenlist"></div>
        <button class="btn" id="resetlayout" type="button">Reset layout</button>
      </div>
      <div class="widgets" id="widgets"></div>
    </section>
    <section class="route" id="route-candidates" data-route="candidates" aria-labelledby="h-candidates" hidden>
      <header><h1 id="h-candidates" tabindex="-1">Candidates</h1><p>The Docket for run {html.escape(run["name"])}: every signal and its dips, with the vetting outcome, the transit strip and the verdict ledger. Every signal here is a {unc}.</p></header>
      <div class="frametools"><a id="fullpage" href="../docket/">Open full page</a><span class="muted">The Docket on its own page, at the same dip.</span></div>
      <iframe class="frame" id="docketframe" title="Docket for run {html.escape(run["name"])}: signals, dips and vetting"></iframe>
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

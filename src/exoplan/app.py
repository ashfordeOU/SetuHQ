"""The exoplan app shell: one self-contained page with a sidebar and six sections.

Each section is a route in the URL hash (``#/overview``, ``#/candidates``,
``#/discoveries``, ``#/planets``, ``#/panel``, ``#/runs``):

* Overview: a widget grid (run figures, discovery count, recent runs, top
  candidates). Each widget can be hidden and moved; the layout is kept in
  localStorage when the browser allows it and the page works when it does not.
* Candidates: the Docket, rendered by :mod:`exoplan.docket` and embedded as an
  inline frame, so its code, honesty rules and keyboard handling are unchanged.
* Discoveries: the feed from the discovery catalogue, with histograms and a
  timeline by star. The feed rule is shown as a rule, not a vetting result.
* Planets: one card per star with the planet-to-star radius ratio sqrt(depth).
  No stellar radius is stored, so nothing is converted to Earth or Jupiter radii.
* Panel: one card per reviewer, its kind and its weights.
* Runs: the discovery run history and this run's configuration.

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
    ("discoveries", "Discovery count"),
    ("runs", "Recent runs"),
    ("top", "Top candidates"),
]

UNCONFIRMED = "candidate, unconfirmed"
NO_DETECTION = "Archive values only. This page claims no detection."
NO_STELLAR_RADIUS = ("No stellar radius is stored in the run or the catalogue, so this page does not "
                     "convert the ratio to a planet radius in Earth or Jupiter units.")
STATUS_LABEL = {"new_candidate": "new candidate", "known_toi": "period matches a known TOI"}
ARCHIVE_FIELDS = ("pl_name", "hostname", "pl_orbper", "tran_flag", "rv_flag", "tic_id")
DEFAULT_WEIGHTS = "docs/results/reviewer_weights_full_panel.json"


def default_layout() -> list[dict]:
    """Every widget, visible, in the default order."""
    return [{"id": wid, "visible": True} for wid, _ in WIDGETS]


def widget_layout(stored=None) -> list[dict]:
    """A valid layout from whatever storage held (or ``None`` when storage is absent).

    Unknown ids and repeats are dropped, missing widgets are appended visible,
    so the result always lists each widget exactly once. The page's
    ``normaliseLayout`` applies the same rule in JavaScript.
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
            out.append({"id": wid, "visible": item.get("visible") is not False})
    out.extend({"id": wid, "visible": True} for wid in ids if wid not in seen)
    return out


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


def panel_cards(manifest: dict, marks: dict, decisions: dict, calibrated: dict | None) -> list[dict]:
    """One card per reviewer in the run: kind, weight used in the run, calibrated weight, marks."""
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
    return {
        "title": title,
        "sections": [{"id": s, "label": label} for s, label in SECTIONS],
        "widgets": [{"id": w, "label": label} for w, label in WIDGETS],
        "default_layout": default_layout(),
        "unconfirmed": UNCONFIRMED,
        "no_detection": NO_DETECTION,
        "no_stellar_radius": NO_STELLAR_RADIUS,
        "run": {
            "name": run_name, "dir": str(run_dir), "created_at": manifest.get("created_at", ""),
            "counts": manifest.get("counts", {}),
            "docket_counts": dock["counts"],
            "reviewer_kinds": dock["reviewers"],
            "top": [{"id": c["candidate_id"], "target": c.get("target", ""), "depth_ppm": c["depth_ppm"], "snr": c["snr"],
                     "period_days": c.get("period_days"), "outcome": c["outcome"],
                     "outcome_label": OUTCOME_LABEL[c["outcome"]]} for c in top],
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
        },
        "feed_rule": {"max_depth_ppm": MAX_FEED_DEPTH_PPM, "min_transits": MIN_FEED_TRANSITS},
        "status_label": STATUS_LABEL,
        "planets": planet_cards(cands, run_name, feed, dock.get("crossmatch") or {}),
        "crossmatch_line": (dock.get("crossmatch") or {}).get("line", ""),
        "panel": panel_cards(manifest, run["marks"], run["reviewerDecisions"], calibrated),
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
.topbar{display:none}
.shell{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}
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
.chip{font:12px "JetBrains Mono",monospace;border:1px solid var(--rule);background:none;color:var(--muted);padding:4px 10px;border-radius:999px;cursor:pointer;min-height:30px}
.chip[aria-pressed="true"]{color:var(--ink);border-color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;min-width:0}
.cards{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}
/* overview */
.ovgrid{display:grid;gap:18px;grid-template-columns:minmax(0,1fr) 260px;align-items:start}
.widgets{display:grid;gap:14px;grid-template-columns:repeat(2,minmax(0,1fr));min-width:0}
.widget{display:grid;gap:10px;align-content:start}
.widget.wide{grid-column:1/-1}
.widget header{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}
.widget header a{font-size:12px}
.kpis{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(110px,1fr))}
.kpi{border-top:2px solid var(--rule);padding-top:6px}
.kpi b{display:block;font:600 26px/1.1 "JetBrains Mono",monospace}
.kpi span{font-size:12px;color:var(--muted)}
.big{font:600 40px/1 "JetBrains Mono",monospace}
.layout{position:sticky;top:16px;display:grid;gap:10px}
.layout ol{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.layout li{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:6px;align-items:center;border:1px solid var(--rule);border-radius:6px;padding:6px 8px;background:var(--paper)}
.layout label{display:flex;gap:8px;align-items:center;cursor:pointer;min-width:0}
.layout input{width:16px;height:16px;margin:0}
.layout .btn{padding:3px 8px;min-height:30px}
.empty{color:var(--muted);font-style:italic}
.runlist{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.runlist li{display:grid;gap:2px;border-top:1px solid var(--rule);padding-top:6px;font-size:13px}
.ratio summary{font-size:13px}
/* tables */
.tablewrap{overflow-x:auto;min-width:0;border:1px solid var(--rule);border-radius:8px;background:var(--panel)}
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
.sizebar{position:relative;height:14px;background:var(--sel);border:1px solid var(--rule);border-radius:3px;overflow:hidden}
.sizebar i{position:absolute;left:0;top:0;bottom:0;background:var(--fit);min-width:2px}
.sizecap{display:flex;justify-content:space-between;font:11px "JetBrains Mono",monospace;color:var(--muted)}
.archive{margin-top:12px;border:1px dashed var(--rule);border-radius:6px;padding:8px 10px;font-size:13px}
.archive ul{margin:6px 0 0;padding-left:18px}
.card h2{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:baseline}
details summary{cursor:pointer}
/* panel, runs */
.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 14px;font-size:13px;margin:8px 0 0}
.kv dt{color:var(--muted)}
.kv dd{margin:0;font-family:"JetBrains Mono",monospace;overflow-wrap:anywhere;min-width:0}
pre.err{white-space:pre-wrap;overflow-wrap:anywhere;margin:4px 0;font-size:12px;background:var(--sel);padding:6px 8px;border-radius:4px}
.frame{width:100%;height:calc(100vh - 190px);min-height:520px;border:1px solid var(--rule);border-radius:8px;background:var(--paper);display:block}
@media (max-width:1000px){
  .ovgrid{grid-template-columns:minmax(0,1fr)}
  .layout{position:static}
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
  .route>header h1{font-size:20px}
  .frame{height:calc(100vh - var(--top) - 150px);min-height:480px}
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

// ---------- widget layout (localStorage optional) ----------
const WIDGET_IDS = D.widgets.map(w => w.id);
const WIDGET_LABEL = Object.fromEntries(D.widgets.map(w => [w.id, w.label]));
const LAYOUT_KEY = 'exoplan-app:layout:' + D.title;
// Same rule as app.widget_layout in Python: each known widget exactly once, unknown ids dropped.
function normaliseLayout(raw, ids){
  const out = [], seen = new Set();
  if (Array.isArray(raw)) for (const it of raw){
    if (!it || typeof it !== 'object') continue;
    if (!ids.includes(it.id) || seen.has(it.id)) continue;
    seen.add(it.id); out.push({id: it.id, visible: it.visible !== false});
  }
  for (const id of ids) if (!seen.has(id)) out.push({id, visible: true});
  return out;
}
function readLayout(storage, key, ids){
  let raw = null;
  try { raw = storage ? JSON.parse(storage.getItem(key)) : null; } catch (e) { raw = null; }
  return normaliseLayout(raw, ids);
}
function getStorage(){ try { return window.localStorage; } catch (e) { return null; } }
let layout = readLayout(getStorage(), LAYOUT_KEY, WIDGET_IDS);
function saveLayout(){ try { const s = getStorage(); if (s) s.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch (e) { /* storage blocked: the layout lasts for this visit */ } }

// ---------- overview ----------
function widgetBody(id){
  const r = D.run, c = r.counts || {}, dc = r.docket_counts || {};
  if (id === 'kpis'){
    const kinds = Object.values(r.reviewer_kinds), sim = kinds.filter(k => k === 'simulated').length, cl = kinds.filter(isClaude).length;
    const tiles = [[c.subjects, 'subjects'], [c.classifications, 'reviews'], [dc.signals, 'signals'], [dc.dips, 'dips'], [dc.passed, 'signals passed vetting'], [dc.flagged, 'signals flagged for review']];
    return `<div class="kpis">${tiles.map(([v,l]) => `<div class="kpi"><b>${esc(v ?? '–')}</b><span>${esc(l)}</span></div>`).join('')}</div>
      <p class="muted" style="margin:0;font-size:12px">Run ${esc(r.name)}, ${esc(r.created_at)}. ${esc(dc.rejected ?? 0)} signal${dc.rejected===1?'':'s'} rejected by vetting. The light curves are measured (${esc((D.config.inputs[0]||{}).source || 'stored input')}); the reviews come from ${sim} simulated detector${sim===1?'':'s'} (not people) and ${cl} Claude reviewer${cl===1?'':'s'}.</p>`;
  }
  if (id === 'discoveries'){
    const f = D.catalog.candidates, nNew = f.filter(x => x.status === 'new_candidate').length, nKnown = f.filter(x => x.status === 'known_toi').length;
    if (!D.catalog.path) return '<p class="empty">No discovery catalogue was given to this build.</p>';
    return `<div><span class="big">${nNew}</span> <span class="muted">new candidates in the feed</span></div>
      <p style="margin:0">${nKnown} more match a known TOI period · ${f.length} entries · ${esc(D.catalog.targets_reviewed)} targets reviewed</p>
      <p style="margin:0">${UNC} every entry</p>
      <p class="muted" style="margin:0;font-size:12px">Catalogue updated ${esc(D.catalog.updated || 'never')}.</p>`;
  }
  if (id === 'runs'){
    const runs = D.catalog.runs.slice(-5).reverse();
    if (!runs.length) return '<p class="empty">No discovery runs are stored in the catalogue.</p>';
    return `<ul class="runlist">${runs.map(x => `<li><b class="mono">${esc(x.time)}</b><span>${(x.targets||[]).length} targets · ${esc(x.new ?? '–')} new · ${esc(x.known ?? '–')} known · ${(x.errors||[]).length} error${(x.errors||[]).length===1?'':'s'}</span></li>`).join('')}</ul>
      <p class="muted" style="margin:0;font-size:12px">This page's run: ${esc(r.name)}, ${esc(r.created_at)}.</p>`;
  }
  if (id === 'top'){
    if (!r.top.length) return '<p class="empty">This run stored no candidates.</p>';
    return `<div class="tablewrap" tabindex="0" role="region" aria-label="Top candidates by SNR"><table><thead><tr><th>dip</th><th class="num">depth ppm</th><th class="num">SNR</th><th class="num">BLS P (d)</th><th>vetting</th></tr></thead><tbody>${r.top.map(x => `<tr><td>${esc(x.id)}<small>${esc(x.target)} · ${esc(D.unconfirmed)}</small></td><td class="num">${fmt(x.depth_ppm,0)}</td><td class="num">${fmt(x.snr,1)}</td><td class="num">${x.period_days ? fmt(x.period_days,3) : 'none'}</td><td>${esc(x.outcome_label)}</td></tr>`).join('')}</tbody></table></div>
      <p class="muted" style="margin:0;font-size:12px">The run's dips with the highest stored SNR. Every one is a ${esc(D.unconfirmed)}.</p>`;
  }
  return '';
}
const WIDGET_LINK = {kpis:'candidates', discoveries:'discoveries', runs:'runs', top:'candidates'};
function renderWidgets(){
  const grid = $('#widgets');
  const shown = layout.filter(x => x.visible);
  grid.innerHTML = shown.length ? shown.map(x => `<section class="card widget${x.id === 'kpis' || x.id === 'top' ? ' wide' : ''}" data-widget="${x.id}" aria-labelledby="w-${x.id}">
    <header><h2 id="w-${x.id}">${esc(WIDGET_LABEL[x.id])}</h2><a href="#/${WIDGET_LINK[x.id]}">Open ${esc(D.sections.find(s => s.id === WIDGET_LINK[x.id]).label)}</a></header>${widgetBody(x.id)}</section>`).join('')
    : '<p class="empty">Every widget is hidden. Tick one in the layout list, or reset the layout.</p>';
}
function renderLayoutList(){
  const n = layout.length;
  $('#layoutlist').innerHTML = layout.map((x, i) => `<li data-id="${x.id}">
    <label><input type="checkbox" data-act="toggle" data-id="${x.id}" ${x.visible ? 'checked' : ''}> <span>${esc(WIDGET_LABEL[x.id])}</span></label>
    <button class="btn" data-act="up" data-id="${x.id}" aria-label="Move ${esc(WIDGET_LABEL[x.id])} up" aria-disabled="${i === 0}">↑</button>
    <button class="btn" data-act="down" data-id="${x.id}" aria-label="Move ${esc(WIDGET_LABEL[x.id])} down" aria-disabled="${i === n-1}">↓</button></li>`).join('');
}
function renderOverview(){ renderWidgets(); renderLayoutList(); }
function layoutAction(act, id){
  const i = layout.findIndex(x => x.id === id); if (i < 0) return;
  const name = WIDGET_LABEL[id];
  if (act === 'toggle'){ layout[i].visible = !layout[i].visible; say(`${name} ${layout[i].visible ? 'shown' : 'hidden'}.`); }
  else if (act === 'up' || act === 'down'){
    const j = act === 'up' ? i - 1 : i + 1;
    if (j < 0 || j >= layout.length) return;
    [layout[i], layout[j]] = [layout[j], layout[i]];
    say(`${name} moved to position ${j+1} of ${layout.length}.`);
  }
  saveLayout(); renderOverview();
  const back = $(`#layoutlist [data-act="${act}"][data-id="${id}"]`); if (back) back.focus();
}
$('#layoutlist').addEventListener('click', e => { const b = e.target.closest('button[data-act]'); if (b) layoutAction(b.dataset.act, b.dataset.id); });
$('#layoutlist').addEventListener('change', e => { const c = e.target.closest('input[data-act="toggle"]'); if (c) layoutAction('toggle', c.dataset.id); });
$('#resetlayout').addEventListener('click', () => { layout = normaliseLayout(null, WIDGET_IDS); saveLayout(); renderOverview(); say('Layout reset: every widget shown in the default order.'); });

// ---------- candidates (the Docket) ----------
function renderCandidates(){
  const f = $('#docketframe');
  if (!f.srcdoc) f.srcdoc = D.docket_html;
}

// ---------- discoveries ----------
const disc = {sort: 'snr', dir: -1, filter: 'all'};
const COLS = [
  ['tic', 'TIC', x => x.tic, x => esc(x.tic)],
  ['t_center', 'mid-time', x => x.t_center, x => `${fmt(x.t_center,3)}<small>${esc(x.time_unit)}</small>`],
  ['period_days', 'period (d)', x => x.period_days, x => fmt(x.period_days,4)],
  ['depth_ppm', 'depth (ppm)', x => x.depth_ppm, x => fmt(x.depth_ppm,0)],
  ['snr', 'SNR', x => x.snr, x => fmt(x.snr,1)],
  ['status', 'status', x => x.status, x => `${esc(D.status_label[x.status] || x.status)}<small>${esc(D.unconfirmed)}</small>`],
  ['found', 'found', x => x.found, x => esc(x.found)],
];
const NUMERIC = new Set(['tic','t_center','period_days','depth_ppm','snr']);
function discRows(){
  const f = D.catalog.candidates.filter(x => disc.filter === 'all' || x.status === disc.filter);
  const col = COLS.find(c => c[0] === disc.sort), key = col[2];
  return f.slice().sort((a, b) => { const va = key(a), vb = key(b); return (va < vb ? -1 : va > vb ? 1 : 0) * disc.dir; });
}
function renderDiscTable(){
  const rows = discRows();
  $('#disctable').innerHTML = `<table><caption class="sr">Discovery feed, sorted by ${esc(disc.sort)} ${disc.dir > 0 ? 'ascending' : 'descending'}. Every entry is a ${esc(D.unconfirmed)}.</caption>
    <thead><tr>${COLS.map(c => `<th scope="col" class="${NUMERIC.has(c[0]) ? 'num' : ''}" aria-sort="${disc.sort === c[0] ? (disc.dir > 0 ? 'ascending' : 'descending') : 'none'}"><button data-sort="${c[0]}">${esc(c[1])}<span aria-hidden="true">${disc.sort === c[0] ? (disc.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`).join('')}</tr></thead>
    <tbody>${rows.length ? rows.map(x => `<tr>${COLS.map(c => `<td class="${NUMERIC.has(c[0]) ? 'num' : ''}">${c[3](x)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${COLS.length}" class="empty">No feed entries with this status.</td></tr>`}</tbody></table>`;
  $('#disccount').textContent = `${rows.length} of ${D.catalog.candidates.length} entries shown.`;
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
function renderDiscoveries(){ renderDiscChips(); renderDiscTable(); renderDiscCharts(true); }

// ---------- planets ----------
function renderPlanets(){
  const cards = D.planets;
  $('#planetcards').innerHTML = cards.length ? cards.map(s => {
        const rowHtml = e => `<div class="ratio">
      <div><b class="mono">${esc(e.id)}</b> ${UNC}</div>
      <div class="muted" style="font-size:12px">${e.source === 'run' ? 'this run' : 'discovery feed'} · ${esc(e.status)} · depth ${fmt(e.depth_ppm,0)} ppm · ${e.period_days ? 'P ' + fmt(e.period_days,3) + ' d' : 'no period'}${e.n_transits ? ' · ' + e.n_transits + ' transits' : ''}</div>
      ${e.ratio === null ? '<div class="formula">No positive stored depth, so no ratio.</div>' : `<div class="formula">Rp/R* = √depth = √(${fmt(e.depth_ppm,1)} × 10⁻⁶) = <b>${fmt(e.ratio,4)}</b></div>
      <div class="sizebar" role="img" aria-label="Planet-to-star radius ratio ${fmt(e.ratio,4)}: the bar is the star's radius, the filled part the candidate's"><i style="width:${(e.ratio*100).toFixed(3)}%"></i></div>
      <div class="sizecap"><span>0</span><span>R* = 1 (full bar)</span></div>`}
      ${e.archive_line ? `<div class="muted" style="font-size:12px">Archive comparison: ${esc(e.archive_line)}. ${esc(D.no_detection)}</div>` : ''}
    </div>`;
    const SHOW = 3, more = s.entries.slice(SHOW);
    const rows = s.entries.slice(0, SHOW).map(rowHtml).join('') + (more.length ? `<details class="ratio"><summary>Show ${more.length} more entr${more.length===1?'y':'ies'} for ${esc(s.star)}</summary>${more.map(rowHtml).join('')}</details>` : '');
    const ar = s.archive || {status: 'not_stored', planets: []};
    let arch;
    if (ar.status === 'not_stored') arch = `<p style="margin:0">No archive cross-match is stored for this star. ${esc(D.no_detection)}</p>`;
    else if (ar.status === 'not_run') arch = `<p style="margin:0">The archive cross-match did not run (archive unreachable at build time). ${esc(D.no_detection)}</p>`;
    else if (!ar.planets.length) arch = `<p style="margin:0">No published planet matched in the archive. ${esc(D.no_detection)}</p>`;
    else arch = `<p style="margin:0"><b>Published planets (archive values only).</b> ${esc(D.no_detection)}</p><ul>${ar.planets.map(p => `<li><b>${esc(p.pl_name)}</b> · host ${esc(p.hostname)} · P ${p.pl_orbper !== null && p.pl_orbper !== undefined ? esc(p.pl_orbper) + ' d' : 'not listed'} · ${p.tran_flag ? 'transiting' : 'not known to transit'}${p.rv_flag ? ' · radial-velocity detection' : ''}</li>`).join('')}</ul><p class="muted" style="margin:4px 0 0;font-size:12px">${esc(ar.source)}, fetched ${esc(ar.fetched_at)}.</p>`;
    return `<article class="card" aria-labelledby="pl-${esc(s.star).replace(/\W/g,'_')}"><h2 id="pl-${esc(s.star).replace(/\W/g,'_')}">${esc(s.star)} <span class="muted" style="font:12px 'JetBrains Mono',monospace">${esc(s.sources.join(' · '))} · ${s.entries.length} entr${s.entries.length===1?'y':'ies'}</span></h2>${rows}<div class="archive">${arch}</div></article>`;
  }).join('') : '<p class="empty">No stars in the run or the feed.</p>';
}

// ---------- panel ----------
function renderPanel(){
  $('#panelcards').innerHTML = D.panel.length ? D.panel.map(r => `<article class="card"><h2 class="mono">${esc(r.id)}</h2>
    <p style="margin:6px 0 0">${kindTag(r.kind)}</p>
    <p class="muted" style="margin:6px 0 0;font-size:13px">${r.kind === 'simulated' ? 'Code that marks dips above an SNR threshold in the light curve. It is not a person.' : isClaude(r.kind) ? 'A Claude model that reads the plotted light curve and marks dips. It is not a person.' : ''}</p>
    <dl class="kv">
      <dt>weight in this run</dt><dd>${r.run_weight === null || r.run_weight === undefined ? 'not stored' : esc(r.run_weight)} <span class="muted">(manifest.json)</span></dd>
      <dt>calibrated weight</dt><dd>${r.calibrated_weight === null || r.calibrated_weight === undefined ? 'not in the weights file' : fmt(r.calibrated_weight,3)}${D.weights_path ? ` <span class="muted">(${esc(D.weights_path)})</span>` : ''}</dd>
      <dt>marks</dt><dd>${r.n_marks} span${r.n_marks===1?'':'s'} on ${r.n_subjects} subject${r.n_subjects===1?'':'s'}</dd>
      <dt>labels</dt><dd>${Object.entries(r.labels).map(([k,v]) => `${esc(k.replace(/_/g,' '))} ${v}`).join(' · ') || 'none'}</dd>
    </dl></article>`).join('') : '<p class="empty">The manifest lists no reviewers.</p>';
}

// ---------- runs ----------
function renderRuns(){
  const runs = D.catalog.runs.slice().reverse();
  $('#runtable').innerHTML = runs.length ? runs.map(x => `<article class="card"><h3 class="mono">${esc(x.time)}</h3>
      <dl class="kv"><dt>targets</dt><dd><details><summary>${(x.targets||[]).length}</summary>${(x.targets||[]).map(t => 'TIC ' + esc(t)).join(', ')}</details></dd>
      <dt>new</dt><dd>${esc(x.new ?? '–')}</dd><dt>known</dt><dd>${esc(x.known ?? '–')}</dd>
      <dt>filtered: deeper than the feed rule</dt><dd>${esc(x.filtered_deep ?? '–')}</dd><dt>filtered: fewer transits than the feed rule</dt><dd>${esc(x.filtered_single ?? '–')}</dd>
      <dt>errors</dt><dd>${(x.errors||[]).length ? x.errors.length : 'none'}</dd></dl>
      ${(x.errors||[]).length ? `<h4 style="margin:10px 0 0;font-size:13px">Error messages (verbatim)</h4>${x.errors.map(e => `<pre class="err">${esc(e)}</pre>`).join('')}` : ''}
      ${(x.tracebacks||[]).length ? `<details><summary>${x.tracebacks.length} traceback${x.tracebacks.length===1?'':'s'} (verbatim)</summary>${x.tracebacks.map(t => `<pre class="err">${esc(t)}</pre>`).join('')}</details>` : ''}</article>`).join('') : '<p class="empty">No discovery runs are stored in the catalogue.</p>';
  const c = D.config;
  const pk = Object.entries(c.packages || {});
  $('#runconfig').innerHTML = `<dl class="kv">
    <dt>config name</dt><dd>${esc(c.config_name)}</dd>
    <dt>config hash (sha256)</dt><dd>${esc(c.config_sha256)}</dd>
    <dt>created</dt><dd>${esc(D.run.created_at)}</dd>
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
  $('#catconfig').innerHTML = D.catalog.path ? `<dl class="kv"><dt>catalogue</dt><dd>${esc(D.catalog.path)}</dd><dt>config</dt><dd>${esc(D.catalog.config)}</dd><dt>config hash (sha256)</dt><dd>${esc(D.catalog.config_sha256)}</dd><dt>updated</dt><dd>${esc(D.catalog.updated)}</dd><dt>targets reviewed</dt><dd>${esc(D.catalog.targets_reviewed)}</dd></dl>` : '<p class="empty">No discovery catalogue was given to this build.</p>';
}

// ---------- router and drawer ----------
const RENDER = {overview: renderOverview, candidates: renderCandidates, discoveries: renderDiscoveries, planets: renderPlanets, panel: renderPanel, runs: renderRuns};
const rendered = new Set();
const ROUTES = D.sections.map(s => s.id);
function currentRoute(){ const h = decodeURIComponent(location.hash.replace(/^#\/?/, '')); return ROUTES.includes(h) ? h : 'overview'; }
function show(r, moveFocus){
  for (const id of ROUTES) $('#route-' + id).hidden = id !== r;
  $$('.nav a').forEach(a => { if (a.dataset.route === r) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  const label = D.sections.find(s => s.id === r).label;
  document.title = `${label} · ${D.title}`;
  $('#curlabel').textContent = label;
  if (!rendered.has(r)){ RENDER[r](); rendered.add(r); }
  else if (r === 'discoveries') renderDiscCharts(false);
  if (moveFocus){ const h = $('#route-' + r + ' h1'); if (h) h.focus({preventScroll: true}); window.scrollTo(0, 0); }
}
window.addEventListener('hashchange', () => { closeDrawer(false); show(currentRoute(), true); });
const drawerMQ = window.matchMedia('(max-width: 699.98px)');
const side = $('#sidebar'), menu = $('#menubtn'), backdrop = $('#backdrop');
function openDrawer(){
  side.classList.add('open'); backdrop.hidden = false; menu.setAttribute('aria-expanded', 'true');
  $('#main').inert = true; $('.topbar').inert = false;
  const cur = $('.nav a[aria-current="page"]') || $('.nav a'); setTimeout(() => cur.focus(), 20);
}
function closeDrawer(returnFocus){
  if (!side.classList.contains('open')) return;
  side.classList.remove('open'); backdrop.hidden = true; menu.setAttribute('aria-expanded', 'false');
  $('#main').inert = false;
  if (returnFocus) menu.focus();
}
menu.addEventListener('click', () => side.classList.contains('open') ? closeDrawer(true) : openDrawer());
backdrop.addEventListener('click', () => closeDrawer(true));
document.addEventListener('keydown', e => { if (e.key === 'Escape' && side.classList.contains('open')) { closeDrawer(true); e.preventDefault(); } });
side.addEventListener('keydown', e => {
  if (e.key !== 'Tab' || !side.classList.contains('open')) return;
  const f = $$('a, button', side), first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first){ last.focus(); e.preventDefault(); }
  else if (!e.shiftKey && document.activeElement === last){ first.focus(); e.preventDefault(); }
});
$$('.nav a').forEach(a => a.addEventListener('click', () => { if (a.getAttribute('aria-current') === 'page') closeDrawer(false); }));
if (drawerMQ.addEventListener) drawerMQ.addEventListener('change', () => closeDrawer(false));
let rt = null;
window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (!$('#route-discoveries').hidden) renderDiscCharts(false); }, 120); });
show(currentRoute(), false);
"""


def _nav() -> str:
    items = "".join(
        f'<li><a href="#/{sid}" data-route="{sid}"><svg viewBox="0 0 16 16" aria-hidden="true">{ICONS[sid]}</svg>{html.escape(label)}</a></li>'
        for sid, label in SECTIONS
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
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{APP_CSS}</style></head>
<body>
<a class="skip" href="#main">Skip to the section</a>
<header class="topbar">
  <button class="btn menu" id="menubtn" aria-expanded="false" aria-controls="sidebar"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12"/></svg>Menu</button>
  <b>{title}</b><span class="cur" id="curlabel"></span>
</header>
<div class="shell">
  <aside class="sidebar" id="sidebar" aria-label="{title} sections">
    <div class="brand"><b>{title}</b><span>run {html.escape(run["name"])}</span></div>
    {_nav()}
    <div class="sidefoot">built from {html.escape(run["dir"])}<br>{html.escape(data["catalog"]["path"] or "no catalogue")}<br>stored values only</div>
  </aside>
  <div class="backdrop" id="backdrop" hidden></div>
  <main id="main" tabindex="-1">
    <section class="route" id="route-overview" data-route="overview" aria-labelledby="h-overview" hidden>
      <header><h1 id="h-overview" tabindex="-1">Overview</h1><p>Run {html.escape(run["name"])} and the discovery feed at a glance. Choose which widgets to show and their order; the page keeps the layout in this browser when storage is allowed.</p></header>
      <div class="ovgrid">
        <div class="widgets" id="widgets"></div>
        <aside class="card layout" aria-labelledby="h-layout">
          <h2 id="h-layout">Layout</h2>
          <p class="muted" style="margin:0;font-size:12px">Tick to show a widget. ↑ and ↓ move it.</p>
          <ol id="layoutlist" aria-label="Widgets in display order"></ol>
          <button class="btn" id="resetlayout">Reset layout</button>
        </aside>
      </div>
    </section>
    <section class="route" id="route-candidates" data-route="candidates" aria-labelledby="h-candidates" hidden>
      <header><h1 id="h-candidates" tabindex="-1">Candidates</h1><p>The Docket for run {html.escape(run["name"])}: every signal and its dips, with the vetting outcome, the transit strip and the verdict ledger. Every signal here is a {unc}. <a href="../docket/">Open the Docket on its own page</a>.</p></header>
      <iframe class="frame" id="docketframe" title="Docket for run {html.escape(run["name"])}: signals, dips and vetting"></iframe>
    </section>
    <section class="route" id="route-discoveries" data-route="discoveries" aria-labelledby="h-discoveries" hidden>
      <header><h1 id="h-discoveries" tabindex="-1">Discoveries</h1><p>The feed from the discovery catalogue. Every entry is a {unc}: a dip the panel marked, not a planet.</p></header>
      <p class="note rule"><b>Feed rule</b> (discover.py): an entry joins the feed when its depth is at most {rule["max_depth_ppm"]:,.0f} ppm and its signal has at least {rule["min_transits"]} transits. This is an admission rule, not a vetting result.</p>
      <section class="card" aria-labelledby="h-feed" style="display:grid;gap:10px">
        <h2 id="h-feed">Feed entries</h2>
        <div class="chips" id="discchips" role="group" aria-label="Filter the feed by status"></div>
        <div class="tablewrap" id="disctable" tabindex="0" role="region" aria-label="Discovery feed table"></div>
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
      <p class="note"><b>Radius ratio only.</b> Rp/R* = √depth, with depth as a fraction (ppm × 10⁻⁶). This assumes a full, undiluted transit and ignores limb darkening. {html.escape(NO_STELLAR_RADIUS)}</p>
      <p class="note">Published planets come from the stored archive cross-match (crossmatch.json). {nodet}</p>
      <div class="cards" id="planetcards"></div>
    </section>
    <section class="route" id="route-panel" data-route="panel" aria-labelledby="h-panel" hidden>
      <header><h1 id="h-panel" tabindex="-1">Panel</h1><p>The reviewers that marked dips in run {html.escape(run["name"])}. Simulated reviewers are code; Claude reviewers are model calls. None of them is a person.</p></header>
      <p class="note rule"><b>Weights.</b> A reviewer's weight is its calibration skill from injection tests: the true-positive rate on injected transits minus the false-positive rate on empty light curves, floored (calibrate.py). The calibrated weights are stored in {html.escape(data["weights_path"] or "no weights file")}. The weight in this run is the one manifest.json records; when it differs from the calibrated weight, the run did not use the calibrated weights.</p>
      <div class="cards" id="panelcards"></div>
    </section>
    <section class="route" id="route-runs" data-route="runs" aria-labelledby="h-runs" hidden>
      <header><h1 id="h-runs" tabindex="-1">Runs</h1><p>The discovery run history from the catalogue, and the configuration of run {html.escape(run["name"])}. Error messages are shown as stored.</p></header>
      <section aria-labelledby="h-hist" style="display:grid;gap:8px"><h2 id="h-hist">Discovery runs</h2><div class="cards" id="runtable"></div></section>
      <div class="cards">
        <section class="card" aria-labelledby="h-cfg"><h2 id="h-cfg">This run's configuration</h2><div id="runconfig"></div></section>
        <section class="card" aria-labelledby="h-catcfg"><h2 id="h-catcfg">Discovery catalogue</h2><div id="catconfig"></div></section>
      </div>
    </section>
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

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Plates: a publication-style, print-ready page with one plate per star.

At the top, a "river of time": the whole feed (and the run's star), one row per
star, a tick per candidate, its height log SNR and its colour the status, the
status also written beside each row. Then one plate per star:

* a star in the run gets, per subject, the whole-subject light curve with each
  consensus window marked and the BLS epochs ticked, and a panel folded on the
  subject's stored BLS t0 and period where one exists;
* a star known only from the discovery catalogue has no stored light curve, so
  its plate draws its candidates on a time strip and says why there is no curve.

Each candidate gets one caption paragraph built from stored values only: the
mid-time, depth, duration and SNR, the consensus interval, how many reviewers
marked it, the BLS period it lies on, the vetting outcome or feed status, any
archive comparison (with the no-detection statement), and the hedge
"Candidate, unconfirmed". Nothing is fitted, binned into a number or looked up
here; the archive comparison is the one the Docket stored in crossmatch.json.

The page is one self-contained HTML file with plain SVG and no script. Its
print stylesheet is first class: A4 pages, no navigation, hairline rules, each
plate starting on a new page and each figure and caption kept whole.
"""

from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

from setuhq import brand
from setuhq.names import ATTRIBUTION, SENTINEL_KINDS
from setuhq.docket import OUTCOME_LABEL, docket_data

UNCONFIRMED = "Candidate, unconfirmed."
NO_DETECTION = "Archive values only. This page claims no detection."
NO_RADIUS = "No stellar radius is stored, so no depth on this page is converted to a planet radius."
FEED_STATUS = {"new_candidate": "new candidate", "known_toi": "period matches a known TOI"}
STATUS_CLASS = {"passed": "s-pass", "flagged": "s-flag", "rejected": "s-rej", "new_candidate": "s-new",
                "known_toi": "s-known"}
STATUS_WORD = {"passed": "passed vetting", "flagged": "flagged for review", "rejected": "rejected by vetting",
               "new_candidate": "new candidate", "known_toi": "known TOI period"}
RIVER_GAP_DAYS = 30.0  # stretches of time with no candidate longer than this are cut from the river
FLAG_WORDS = {"off_ephemeris": "off its star's ephemeris", "edge_event": "at a data edge"}

# The logo on the plates' paper: the light-ground variant, and the dark-ground one where the page turns dark.
PLATE_LOGO_CSS = (".kicker a{display:inline-block;vertical-align:middle;margin-right:10px}.brandlogo{display:block;height:20px;width:auto}"
                  ".brandlogo.dk{display:none}@media screen and (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]) "
                  ".brandlogo.dk{display:block}:root:not([data-theme=\"light\"]) .brandlogo.lt{display:none}}"
                  "@media screen{:root[data-theme=\"dark\"] .brandlogo.dk{display:block}:root[data-theme=\"dark\"] .brandlogo.lt{display:none}}")
PLATE_CSS = """
:root{--paper:#fbfaf7;--ink:#141414;--rule:#c9c6bd;--hair:#dcd9d0;--muted:#5d5f66;--pt:#8d8f96;--win:#e9e3cf;
--pass:#2e7d4f;--flag:#8a6400;--rej:#b23a3a;--new:#1f5fbf;--known:#64666e;--fit:#1f5fbf}
@media screen and (prefers-color-scheme: dark){:root:not([data-theme="light"]){--paper:#131417;--ink:#ecebe6;--rule:#3a3c43;--hair:#2a2c32;--muted:#a3a5ad;--pt:#7b7e87;--win:#3a3526;
--pass:#5cc08a;--flag:#e0b243;--rej:#ef7070;--new:#6fa0ff;--known:#9a9ca4;--fit:#6fa0ff;color-scheme:dark}}
@media screen{:root[data-theme="dark"]{--paper:#131417;--ink:#ecebe6;--rule:#3a3c43;--hair:#2a2c32;--muted:#a3a5ad;--pt:#7b7e87;--win:#3a3526;
--pass:#5cc08a;--flag:#e0b243;--rej:#ef7070;--new:#6fa0ff;--known:#9a9ca4;--fit:#6fa0ff;color-scheme:dark}}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--paper);color:var(--ink);font:15px/1.55 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;overflow-x:hidden}
.num,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;font-size:.9em}
a{color:var(--fit)}
:focus-visible{outline:2px solid var(--fit);outline-offset:2px}
.skip{position:absolute;left:8px;top:-60px;background:var(--ink);color:var(--paper);padding:10px 14px;z-index:9;min-height:44px;display:inline-flex;align-items:center}
.skip:focus{top:8px}
.sheet{max-width:210mm;margin:0 auto;padding:28px 16px 48px}
header.mast{border-bottom:1px solid var(--ink);padding-bottom:12px;margin-bottom:18px}
header.mast h1{font-weight:600;font-size:28px;line-height:1.15;margin:0;letter-spacing:-.01em}
header.mast p{margin:6px 0 0}
.hedge{font-weight:600}
.kicker{font:12px/1.4 ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 6px}
.notes{margin:12px 0 0;padding:0;list-style:none;font-size:13px;color:var(--muted);border-top:1px solid var(--hair)}
.notes li{border-bottom:1px solid var(--hair);padding:5px 0}
nav.toc{margin:0 0 22px;font-size:14px}
nav.toc h2{font-size:13px;font-weight:600;margin:0 0 4px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
nav.toc ol{margin:0;padding:0;list-style:none;display:flex;flex-wrap:wrap;gap:0 18px}
nav.toc a{display:inline-flex;align-items:center;min-height:44px}
section.river,article.plate{border-top:1px solid var(--ink);padding-top:10px;margin-top:26px}
h2.ptitle{font-size:20px;font-weight:600;margin:0;line-height:1.25}
h2.ptitle .num{font-size:14px;color:var(--muted);font-weight:400}
.psub{margin:2px 0 10px;color:var(--muted);font-size:13px}
figure{margin:12px 0 0;break-inside:avoid;page-break-inside:avoid}
figcaption{font-size:13px;color:var(--muted);margin-top:4px}
.figrow{display:grid;grid-template-columns:minmax(0,2.1fr) minmax(0,1fr);gap:10px;align-items:start}
.panel h3{font:600 12px/1.3 ui-monospace,Menlo,monospace;margin:0 0 2px;color:var(--muted);letter-spacing:.02em}
.scroll{overflow-x:auto;min-width:0}
svg{display:block;width:100%;height:auto}
svg text{font:11px ui-monospace,Menlo,Consolas,monospace;fill:var(--muted)}
svg .ink{fill:var(--ink)}
svg .axis{stroke:var(--ink);stroke-width:.75}
svg .grid{stroke:var(--hair);stroke-width:.5}
svg .pts{stroke:var(--pt);stroke-width:2.2;stroke-linecap:round;fill:none}
svg .win{fill:var(--win)}
svg .winedge{stroke:var(--ink);stroke-width:.6}
svg .epoch{fill:var(--ink)}
svg .durwin{fill:var(--win)}
.s-pass{color:var(--pass)} .s-flag{color:var(--flag)} .s-rej{color:var(--rej)} .s-new{color:var(--new)} .s-known{color:var(--known)}
svg .t.s-pass{stroke:var(--pass)} svg .t.s-flag{stroke:var(--flag)} svg .t.s-rej{stroke:var(--rej)} svg .t.s-new{stroke:var(--new)} svg .t.s-known{stroke:var(--known)}
svg .t{stroke-width:2.2;stroke-linecap:butt}
svg .cap.s-pass{fill:var(--pass)} svg .cap.s-flag{fill:var(--flag)} svg .cap.s-rej{fill:var(--rej)} svg .cap.s-new{fill:var(--new)} svg .cap.s-known{fill:var(--paper);stroke:var(--known);stroke-width:1.2}
svg .brk{stroke:var(--muted);stroke-width:.8}
.legend{display:flex;flex-wrap:wrap;gap:2px 16px;font-size:12px;margin:6px 0 0}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{display:inline-block;width:3px;height:12px;background:currentColor}
.legend i.k{width:9px;height:9px;border-radius:50%;background:none;border:1.5px solid currentColor}
ol.captions{list-style:none;margin:12px 0 0;padding:0;border-top:1px solid var(--hair)}
ol.captions li{border-bottom:1px solid var(--hair);padding:7px 0;break-inside:avoid;page-break-inside:avoid}
p.caption{margin:0;font-size:14px;line-height:1.5;hyphens:auto}
p.caption b.fig{font-weight:600}
.printonly{display:none}
.word.cand{color:var(--ink)}
.word{font:600 11px/1 ui-monospace,Menlo,monospace;text-transform:uppercase;letter-spacing:.05em;border:1px solid currentColor;padding:2px 4px;margin-right:4px;white-space:nowrap;display:inline-block;vertical-align:1px}
.archive{margin:12px 0 0;border:1px solid var(--rule);padding:8px 10px;font-size:13px;break-inside:avoid}
.archive p{margin:0}
.nocurve{margin:10px 0 0;font-size:13px;color:var(--muted);border-left:2px solid var(--rule);padding-left:8px}
footer.colophon{margin-top:30px;border-top:1px solid var(--ink);padding-top:8px;font-size:12px;color:var(--muted)}
footer.colophon p{margin:3px 0}
@media (max-width:640px){
  .sheet{padding:18px 16px 40px}
  header.mast h1{font-size:23px}
  .figrow{grid-template-columns:minmax(0,1fr)}
  .scroll>svg.wide{min-width:520px}
  section.river .scroll>svg.wide{min-width:700px}
  .panel>svg{max-width:340px}
  .scroll{border:1px solid var(--hair)}
}
@page{size:A4;margin:14mm 13mm 16mm;
  @bottom-left{content:"Candidate, unconfirmed. Stored values only.";font:8pt Georgia,serif;color:#444}
  @bottom-right{content:counter(page) " / " counter(pages);font:8pt Georgia,serif;color:#444}}
@media print{
  .printonly{display:inline}
  :root{--paper:#fff;--ink:#000;--rule:#999;--hair:#bbb;--muted:#333;--pt:#777;--win:#ece6d2}
  body{font-size:9.5pt;line-height:1.42;background:#fff}
  .skip,nav.toc{display:none}
  .sheet{max-width:none;padding:0}
  header.mast h1{font-size:19pt}
  section.river,article.plate{margin-top:0;padding-top:4pt;border-top-width:.5pt}
  header.mast,footer.colophon{border-width:.5pt}
  .notes li,ol.captions li,ol.captions{border-width:.5pt}
  /* One plate, one page: the plate is kept whole, its captions set in two columns under the figure. */
  article.plate{break-before:page;page-break-before:always;break-inside:avoid;page-break-inside:avoid}
  figure,figcaption,.archive,.nocurve,.legend{break-inside:avoid;page-break-inside:avoid}
  ol.captions{columns:2;column-gap:6mm;column-fill:balance;widows:3;orphans:3;margin-top:6pt}
  ol.captions li{break-inside:avoid;page-break-inside:avoid;widows:3;orphans:3;padding:3pt 0}
  p.caption{widows:3;orphans:3}
  h2.ptitle{break-after:avoid;page-break-after:avoid;font-size:13pt}
  .psub{break-after:avoid;page-break-after:avoid;margin:1pt 0 4pt}
  .panel h3{font-size:8pt}
  figcaption{margin-top:2pt}
  .archive{margin-top:6pt;padding:4pt 6pt}
  .figrow{grid-template-columns:minmax(0,2.1fr) minmax(0,1fr)}
  .scroll{overflow:visible;border:0}
  .scroll>svg.wide{min-width:0}
  p.caption{font-size:8.5pt;line-height:1.36}
  .word{font-size:7pt;padding:1px 3px}
  figure{margin-top:6pt}
  figcaption,.nocurve,.archive{font-size:8.5pt}
  a{color:inherit;text-decoration:none}
  /* Figures print at about 0.66 to 0.69 pt per SVG unit, so 12.5 units is at least 8.2 pt on paper. */
  svg text{font-size:12.5px}
}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _f(x, d) -> str:
    v = _num(x)
    return "–" if v is None else f"{v:.{d}f}".replace("-", "−")


def _ticks(lo: float, hi: float, n: int) -> list[float]:
    if not hi > lo:
        return [lo]
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    r = raw / mag
    step = (1 if r < 1.5 else 2 if r < 3 else 5 if r < 7 else 10) * mag
    out, v = [], math.ceil(lo / step) * step
    while v <= hi + 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def _tick_label(v: float) -> str:
    return (f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:g}").replace("-", "−")


# ---------- captions ----------


def run_caption(c: dict, n_panel: int, kinds: dict[str, str], comparison: dict | None) -> str:
    """One paragraph for a dip in the run, from stored values only."""
    unit = c.get("time_unit") or ""
    who = [r for r in kinds if r in (c.get("reviewers") or [])]
    n_sim = sum(1 for r in who if kinds[r] == "simulated")
    n_cl = sum(1 for r in who if kinds[r] in SENTINEL_KINDS)
    of_sim = sum(1 for k in kinds.values() if k == "simulated")
    of_cl = sum(1 for k in kinds.values() if k in SENTINEL_KINDS)
    parts = [
        f"Dip at {unit} {_f(c['t_center'], 3)}, {_f(c['depth_ppm'], 0)} ppm, {_f(c.get('duration_hours'), 2)} h, "
        f"SNR {_f(c['snr'], 1)}.",
        f"Consensus interval {unit} {_f(c['t_start'], 3)} to {_f(c['t_end'], 3)}.",
        f"Marked by {c.get('n_reviewers', len(who))} of {n_panel} reviewers ({n_cl} of {of_cl} Sentinels, "
        f"{n_sim} of {of_sim} Probes).",
    ]
    period = _num(c.get("period_days"))
    if period is not None:
        t0 = _num(c.get("bls_t0"))
        parts.append(f"Lies on a {period:.3f}-day BLS period" + (f" (t0 {unit} {t0:.3f})." if t0 is not None else "."))
    else:
        parts.append("No BLS period: a single dip.")
    outcome = OUTCOME_LABEL.get(c.get("outcome"), "vetting outcome not stored")
    flags = [FLAG_WORDS.get(f, f.replace("_", " ")) for f in c.get("flags") or []]
    parts.append(outcome[0].upper() + outcome[1:] + (f" ({', '.join(flags)})." if flags else "."))
    line = (comparison or {}).get("line")
    if line:
        parts.append(f"Archive: {line}. {NO_DETECTION}")
    return " ".join(parts)  # "candidate, unconfirmed" is said once in the lede; each caption carries a candidate tag


def feed_caption(r: dict) -> str:
    """One paragraph for a discovery-feed entry, from the catalogue's stored values only."""
    unit = r.get("time_unit") or ""
    parts = [
        f"Dip at {unit} {_f(r['t_center'], 3)}, {_f(r['depth_ppm'], 0)} ppm, {_f(r.get('duration_hours'), 2)} h, "
        f"SNR {_f(r['snr'], 1)}.",
        f"Marked by {r.get('n_reviewers', '–')} reviewers (the catalogue does not store the panel size or the "
        f"consensus interval).",
    ]
    period = _num(r.get("period_days"))
    if period is not None:
        n_tr = r.get("n_transits")
        parts.append(f"Lies on a {period:.3f}-day BLS period" + (f" with {n_tr} transits." if n_tr else "."))
    else:
        parts.append("No BLS period.")
    status = FEED_STATUS.get(r.get("status"), str(r.get("status", "")))
    if r.get("status") == "known_toi":
        parts.append(f"Status: {status}. {NO_DETECTION}")
    else:
        parts.append(f"Status: {status}.")
    return " ".join(parts)


# ---------- data ----------


def _xm_dated(xm: dict) -> str:
    """'recorded 2026-10-16 (commit 0f6dbdc), from docs/results/...; this run's own cross-match: not_run' for a
    fallback file, which was recorded from a validation note rather than fetched; else 'fetched <time>'."""
    if xm.get("fallback_from"):
        commit = f" (commit {xm['recorded_commit']})" if xm.get("recorded_commit") else ""
        return (f"recorded {str(xm.get('fetched_at', ''))[:10]}{commit} in {xm['fallback_from']}; this run's own "
                f"cross-match: {xm.get('run_status', 'not stored')}{', ' + xm['run_error'] if xm.get('run_error') else ''}")
    return f"fetched {xm.get('fetched_at', '')}"


def plate_data(run_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
               star: str | None = None, require_crossmatch: bool = False) -> dict:
    """Everything the plates show, read from the run directory and the catalogue."""
    run_dir = Path(run_dir)
    dock = docket_data(run_dir, title=title, star=star, require_crossmatch=require_crossmatch)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    kinds = dock["reviewers"]
    comparison = ((dock.get("crossmatch") or {}).get("comparison") or {}).get("by_candidate") or {}
    catalog = {}
    if catalog_path is not None and Path(catalog_path).exists():
        catalog = json.loads(Path(catalog_path).read_text())
    feed = catalog.get("candidates") or []

    stars: list[dict] = []
    by_target: dict[str, list[dict]] = {}
    for c in dock["candidates"]:
        by_target.setdefault(c.get("target") or c["subject_id"], []).append(c)
    for target, cands in by_target.items():
        cands.sort(key=lambda c: c["t_center"])
        subjects = []
        for sid in sorted({c["subject_id"] for c in cands}, key=lambda s: dock["subjects"][s]["start"]):
            subj = dock["subjects"][sid]
            mine = [c for c in cands if c["subject_id"] == sid]
            periodic = next((c for c in mine if _num(c.get("period_days")) is not None and _num(c.get("bls_t0")) is not None), None)
            subjects.append({
                "subject_id": sid, "time_unit": subj.get("time_unit", ""), "start": subj["start"], "end": subj["end"],
                "time": subj["time"], "flux": subj["flux"],
                "period_days": periodic["period_days"] if periodic else None,
                "bls_t0": periodic["bls_t0"] if periodic else None,
                "bls_duration_days": periodic.get("bls_duration_days") if periodic else None,
                "dips": [c["candidate_id"] for c in mine],
            })
        stars.append({
            "star": target, "source": "run", "run": manifest.get("config_name") or run_dir.name,
            "subjects": subjects,
            "candidates": [{**{k: c.get(k) for k in ("candidate_id", "subject_id", "t_center", "t_start", "t_end", "time_unit",
                                                     "depth_ppm", "duration_hours", "snr", "n_reviewers", "period_days",
                                                     "bls_t0", "outcome", "flags", "reviewers")},
                            "status": c.get("outcome"),
                            "archive_line": (comparison.get(c["candidate_id"]) or {}).get("line", ""),
                            "caption": run_caption(c, len(kinds), kinds, comparison.get(c["candidate_id"]))}
                           for c in cands],
            "crossmatch_line": (dock.get("crossmatch") or {}).get("line", ""),
            "crossmatch_source": (dock.get("crossmatch") or {}).get("source", ""),
            "crossmatch_fetched": (dock.get("crossmatch") or {}).get("fetched_at", ""),
            "crossmatch_dated": _xm_dated(dock.get("crossmatch") or {}),
        })
    feed_stars: dict[str, list[dict]] = {}
    for r in feed:
        feed_stars.setdefault(f"TIC {r['tic']}", []).append(r)
    for name in sorted(feed_stars, key=lambda n: int(n.split()[1]) if n.split()[1].isdigit() else 0):
        rows = sorted(feed_stars[name], key=lambda r: r["t_center"])
        stars.append({
            "star": name, "source": "feed", "sector_span": rows[0].get("sector_span"),
            "candidates": [{**{k: r.get(k) for k in ("candidate_id", "t_center", "time_unit", "depth_ppm", "duration_hours",
                                                     "snr", "n_reviewers", "period_days", "n_transits", "status")},
                            "caption": feed_caption(r)} for r in rows],
        })
    return {
        "title": title, "stars": stars, "kinds": kinds,
        "subject_days": manifest.get("subject_days"),
        "run": {"name": manifest.get("config_name") or run_dir.name, "dir": str(run_dir),
                "created_at": manifest.get("created_at", ""), "config_sha256": manifest.get("config_sha256", "")},
        "catalog": {"path": str(catalog_path) if catalog else "", "updated": catalog.get("updated", ""),
                    "n": len(feed)},
    }


# ---------- figures ----------


RIVER_MIN_SEGMENT = 76.0  # SVG units: room for a start and an end label on every segment, at the print text size


def river_segments(stars: list[dict]) -> list[tuple[float, float]]:
    """The river's segments: candidate mid-times grouped where no gap exceeds ``RIVER_GAP_DAYS``.

    Each segment runs from a whole day before its first candidate to a whole day after its last,
    so its start and end labels are whole days and its span is a whole number of days.
    """
    times = sorted(c["t_center"] for s in stars for c in s["candidates"])
    if not times:
        return []
    clusters = [[times[0], times[0]]]
    for t in times[1:]:
        if t - clusters[-1][1] > RIVER_GAP_DAYS:
            clusters.append([t, t])
        else:
            clusters[-1][1] = t
    out = []
    for lo, hi in clusters:
        pad = max(1.0, (hi - lo) * 0.04)
        out.append((float(math.floor(lo - pad)), float(math.ceil(hi + pad))))
    return out


def river_svg(stars: list[dict]) -> str:
    """The river of time: one row per star, a tick per candidate, height log SNR, colour status.

    Stretches longer than ``RIVER_GAP_DAYS`` with no candidate are cut and marked with a break,
    so stars observed years apart share one strip. The segments are not drawn to a common time
    scale: each has its own, labelled at its start and end, with its span written beneath it.
    """
    events = [(s["star"], c) for s in stars for c in s["candidates"]]
    if not events:
        return '<p class="nocurve">No candidates are stored.</p>'
    clusters = river_segments(stars)
    label_w, right_w, gap = 112, 172, 16
    line_h = 15  # status lines beside a row, and text lines under the axis
    n_lines = max(len({c.get("status") for c in s["candidates"]}) for s in stars)
    rh, top, bottom = max(34, line_h * n_lines + 12), 8, 6 + 4 * line_h + 22
    # Every segment gets a floor width, room for its start and end labels; the rest is shared by span.
    W = max(760.0, label_w + right_w + gap * (len(clusters) - 1) + RIVER_MIN_SEGMENT * len(clusters))
    plot_w = W - label_w - right_w - gap * (len(clusters) - 1)
    spans = [b - a for a, b in clusters]
    extra = plot_w - RIVER_MIN_SEGMENT * len(clusters)
    widths = [RIVER_MIN_SEGMENT + extra * sp / sum(spans) for sp in spans]
    x0s, x = [], float(label_w)
    for w in widths:
        x0s.append(x)
        x += w + gap

    def X(t):
        for (a, b), x0, w in zip(clusters, x0s, widths):
            if a <= t <= b:
                return x0 + (t - a) / (b - a) * w
        return None

    snrs = [_num(c["snr"]) or 1.0 for _, c in events]
    lmax = math.log10(max(max(snrs), 10.0))
    H = top + rh * len(stars) + bottom
    unit = events[0][1].get("time_unit") or ""
    out = [f'<svg class="wide" viewBox="0 0 {W:g} {H}" role="img" aria-labelledby="river-t river-d">'
           f'<title id="river-t">River of time</title>'
           f'<desc id="river-d">{len(events)} candidates on {len(stars)} stars by mid-time ({_e(unit)}); tick height is log SNR '
           f'and colour is status, written beside each row. Empty stretches longer than {RIVER_GAP_DAYS:.0f} days are cut, and the '
           f'{len(clusters)} segments are not drawn to a common time scale: each is labelled at its start and end, with its span.</desc>']
    for i, s in enumerate(stars):
        base = top + rh * (i + 1) - 6
        out.append(f'<line class="grid" x1="{label_w}" x2="{W - right_w:g}" y1="{base}" y2="{base}"/>')
        out.append(f'<text class="ink" x="{label_w - 8}" y="{base - 2}" text-anchor="end">{_e(s["star"])}</text>')
        counts: dict[str, int] = {}
        for c in s["candidates"]:
            st = c.get("status") or ""
            counts[st] = counts.get(st, 0) + 1
            x = X(c["t_center"])
            h = (rh - 10) * math.log10(max(_num(c["snr"]) or 1.0, 1.0)) / lmax
            cls = STATUS_CLASS.get(st, "")
            out.append(f'<g><title>{_e(s["star"])} · {_e(unit)} {_f(c["t_center"], 3)} · SNR {_f(c["snr"], 1)} · '
                       f'{_e(STATUS_WORD.get(st, st))}{" · candidate" if _cand_word(st) else ""}</title>'
                       f'<line class="t {cls}" x1="{x:.1f}" x2="{x:.1f}" y1="{base}" y2="{base - h:.1f}"/>'
                       f'<circle class="cap {cls}" cx="{x:.1f}" cy="{base - h:.1f}" r="2.2"/></g>')
        # The statuses in words, one per line, beside the row.
        lines = [f"{n} {STATUS_WORD.get(k, k)}" for k, n in sorted(counts.items())]
        for j, words in enumerate(lines):
            out.append(f'<text x="{W - right_w + 8:g}" y="{base - 2 - line_h * (len(lines) - 1 - j)}">{_e(words)}</text>')
    axis_y = top + rh * len(stars) - 6
    for (a, b), x0, w in zip(clusters, x0s, widths):
        out.append(f'<g class="seg"><line class="axis" x1="{x0:.1f}" x2="{x0 + w:.1f}" y1="{axis_y}" y2="{axis_y}"/>')
        # Start and end, always labelled (inside the segment); between them only ticks with room for a label.
        inner = [t for t in _ticks(a, b, max(1, int(w // 80))) if a < t < b
                 and x0 + (t - a) / (b - a) * w - x0 > 52 and x0 + w - (x0 + (t - a) / (b - a) * w) > 52]
        for t, anchor in [(a, "start"), *((t, "middle") for t in inner), (b, "end")]:
            xt = x0 + (t - a) / (b - a) * w
            out.append(f'<line class="axis" x1="{xt:.1f}" x2="{xt:.1f}" y1="{axis_y}" y2="{axis_y + 4}"/>'
                       f'<text class="tick" x="{xt:.1f}" y="{axis_y + line_h + 3}" text-anchor="{anchor}">{_tick_label(t)}</text>')
        out.append(f'<text class="span" x="{x0 + w / 2:.1f}" y="{axis_y + 2 * line_h + 5}" text-anchor="middle">'
                   f'{_tick_label(b - a)} d</text></g>')
    for x0 in x0s[1:]:
        xb = x0 - gap / 2
        out.append(f'<path class="brk" d="M{xb - 4:.1f},{axis_y + 4} l4,-8 M{xb:.1f},{axis_y + 4} l4,-8"/>')
    out.append(f'<text x="{W - right_w:g}" y="{axis_y + 3 * line_h + 9}" text-anchor="end">mid-time ({_e(unit)}); each segment on its own scale</text>')
    # Height key: the tick heights for SNR 10 and the largest stored SNR.
    out.append(f'<text x="{label_w}" y="{axis_y + 4 * line_h + 13}">tick height: log SNR (full row = SNR {max(max(snrs), 10.0):.1f})</text>')
    out.append("</svg>")
    return "".join(out)


def light_curve_svg(subj: dict, cands: list[dict], letters: dict[str, str]) -> tuple[str, str]:
    """The whole subject: stored flux, each consensus window shaded and lettered, BLS epochs ticked.

    Returns the SVG and a note on any points outside the drawn flux range.
    """
    W, H, pl, pr, pt, pb = 520, 188, 52, 8, 20, 32
    t, f = subj["time"], subj["flux"]
    ppm = [(v - 1.0) * 1e6 for v in f]
    depth = max((_num(c["depth_ppm"]) or 0 for c in cands), default=0) or 300.0
    lo, hi = -2.4 * depth, 1.4 * depth
    a, b = subj["start"], subj["end"]
    X = lambda x: pl + (x - a) / (b - a) * (W - pl - pr)  # noqa: E731
    Y = lambda y: pt + (hi - y) / (hi - lo) * (H - pt - pb)  # noqa: E731
    unit = subj.get("time_unit") or ""
    clipped = sum(1 for y in ppm if y < lo or y > hi)
    out = [f'<svg class="wide" viewBox="0 0 {W} {H}" role="img" aria-label="Light curve of subject {_e(subj["subject_id"])}, '
           f'{unit} {a:.2f} to {b:.2f}, {len(t)} stored points, with {len(cands)} consensus window{"s" if len(cands) != 1 else ""} marked.">',
           f'<defs><clipPath id="clip-{_e(subj["subject_id"])}"><rect x="{pl}" y="{pt}" width="{W - pl - pr}" height="{H - pt - pb}"/></clipPath></defs>']
    for y in _ticks(lo, hi, 4):
        out.append(f'<line class="grid" x1="{pl}" x2="{W - pr}" y1="{Y(y):.1f}" y2="{Y(y):.1f}"/>'
                   f'<text x="{pl - 5}" y="{Y(y) + 3.5:.1f}" text-anchor="end">{_tick_label(y)}</text>')
    for c in cands:
        x1, x2 = X(c["t_start"]), X(c["t_end"])
        out.append(f'<rect class="win" x="{x1:.1f}" y="{pt}" width="{max(1.5, x2 - x1):.1f}" height="{H - pt - pb}"/>'
                   f'<text class="ink" x="{(x1 + x2) / 2:.1f}" y="{pt - 5}" text-anchor="middle">{letters[c["candidate_id"]]}</text>')
    period, t0 = _num(subj.get("period_days")), _num(subj.get("bls_t0"))
    if period and t0 is not None:
        k = math.ceil((a - t0) / period)
        while t0 + k * period <= b:
            xe = X(t0 + k * period)
            out.append(f'<path class="epoch" d="M{xe:.1f},{H - pb - 1} l-3.5,6 h7 z"/>')
            k += 1
    d = "".join(f"M{X(x):.1f},{Y(y):.1f}h0" for x, y in zip(t, ppm))
    out.append(f'<path class="pts" clip-path="url(#clip-{_e(subj["subject_id"])})" d="{d}"/>')
    out.append(f'<line class="axis" x1="{pl}" x2="{W - pr}" y1="{H - pb}" y2="{H - pb}"/>'
               f'<line class="axis" x1="{pl}" x2="{pl}" y1="{pt}" y2="{H - pb}"/>')
    for x in _ticks(a, b, 6):
        if a <= x <= b:
            out.append(f'<text x="{X(x):.1f}" y="{H - pb + 13}" text-anchor="middle">{_tick_label(x)}</text>')
    out.append(f'<text x="{W - pr}" y="{H - 3}" text-anchor="end">time ({_e(unit)})</text>'
               f'<text x="{pl - 46}" y="{pt - 7}">ppm</text>')
    out.append("</svg>")
    note = f" {clipped} point{'s' if clipped != 1 else ''} outside the flux range are not drawn." if clipped else ""
    return "".join(out), note


def fold_svg(subj: dict, cands: list[dict], letters: dict[str, str]) -> str:
    """The subject's stored flux folded on its stored BLS t0 and period, hours from mid-transit."""
    W, H, pl, pr, pt, pb = 250, 188, 44, 8, 20, 32
    period, t0 = _num(subj["period_days"]), _num(subj["bls_t0"])
    dur_d = _num(subj.get("bls_duration_days")) or 0.1
    half = max(3 * dur_d * 24, 6.0)
    ppm, ph = [], []
    for x, v in zip(subj["time"], subj["flux"]):
        h = ((x - t0 + period / 2) % period - period / 2) * 24
        if -half <= h <= half:
            ph.append(h)
            ppm.append((v - 1.0) * 1e6)
    depth = max((_num(c["depth_ppm"]) or 0 for c in cands), default=0) or 300.0
    lo, hi = -2.4 * depth, 1.4 * depth
    X = lambda x: pl + (x + half) / (2 * half) * (W - pl - pr)  # noqa: E731
    Y = lambda y: pt + (hi - y) / (hi - lo) * (H - pt - pb)  # noqa: E731
    sid = _e(subj["subject_id"])
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Subject {sid} folded on its BLS period {period:.4f} d, '
           f't0 {t0:.4f}: {len(ph)} stored points within {half:.1f} h of mid-transit.">',
           f'<defs><clipPath id="fclip-{sid}"><rect x="{pl}" y="{pt}" width="{W - pl - pr}" height="{H - pt - pb}"/></clipPath></defs>']
    xd = X(-dur_d * 12), X(dur_d * 12)
    out.append(f'<rect class="durwin" x="{xd[0]:.1f}" y="{pt}" width="{xd[1] - xd[0]:.1f}" height="{H - pt - pb}"/>')
    for y in _ticks(lo, hi, 4):
        out.append(f'<line class="grid" x1="{pl}" x2="{W - pr}" y1="{Y(y):.1f}" y2="{Y(y):.1f}"/>'
                   f'<text x="{pl - 5}" y="{Y(y) + 3.5:.1f}" text-anchor="end">{_tick_label(y)}</text>')
    d = "".join(f"M{X(x):.1f},{Y(y):.1f}h0" for x, y in zip(ph, ppm))
    out.append(f'<path class="pts" clip-path="url(#fclip-{sid})" d="{d}"/>')
    out.append(f'<line class="axis" x1="{pl}" x2="{W - pr}" y1="{H - pb}" y2="{H - pb}"/>'
               f'<line class="axis" x1="{pl}" x2="{pl}" y1="{pt}" y2="{H - pb}"/>')
    for x in _ticks(-half, half, 4):
        out.append(f'<text x="{X(x):.1f}" y="{H - pb + 13}" text-anchor="middle">{_tick_label(x)}</text>')
    on = [letters[c["candidate_id"]] for c in cands if _num(c.get("period_days")) is not None]
    out.append(f'<text class="ink" x="{(xd[0] + xd[1]) / 2:.1f}" y="{pt - 5}" text-anchor="middle">{_e(", ".join(on))}</text>')
    out.append(f'<text x="{W - pr}" y="{H - 3}" text-anchor="end">hours from mid-transit</text>')
    out.append("</svg>")
    return "".join(out)


def feed_strip_svg(s: dict) -> str:
    """A star known only from the catalogue: its candidates on a time strip (no light curve is stored)."""
    W, H, pl, pr, pt, pb = 760, 106, 16, 16, 14, 38
    cands = s["candidates"]
    ts = [c["t_center"] for c in cands]
    pad = max(1.0, (max(ts) - min(ts)) * 0.04)
    a, b = min(ts) - pad, max(ts) + pad
    X = lambda x: pl + (x - a) / (b - a) * (W - pl - pr)  # noqa: E731
    base = H - pb
    lmax = math.log10(max(max(_num(c["snr"]) or 1 for c in cands), 10.0))
    unit = cands[0].get("time_unit") or ""
    out = [f'<svg class="wide" viewBox="0 0 {W} {H}" role="img" aria-label="{_e(s["star"])}: {len(cands)} candidates by mid-time '
           f'({_e(unit)}), tick height log SNR, colour status. No light curve is stored for this star.">']
    for i, c in enumerate(cands):
        x = X(c["t_center"])
        h = (base - pt - 6) * math.log10(max(_num(c["snr"]) or 1, 1)) / lmax
        cls = STATUS_CLASS.get(c.get("status"), "")
        out.append(f'<g><title>{_e(c["candidate_id"])} · {_e(unit)} {_f(c["t_center"], 3)} · SNR {_f(c["snr"], 1)} · '
                   f'{_e(STATUS_WORD.get(c.get("status"), c.get("status")))}</title>'
                   f'<line class="t {cls}" x1="{x:.1f}" x2="{x:.1f}" y1="{base}" y2="{base - h:.1f}"/>'
                   f'<circle class="cap {cls}" cx="{x:.1f}" cy="{base - h:.1f}" r="2.4"/></g>')
    out.append(f'<line class="axis" x1="{pl}" x2="{W - pr}" y1="{base}" y2="{base}"/>')
    for x in _ticks(a, b, 8):
        if a <= x <= b:
            out.append(f'<line class="axis" x1="{X(x):.1f}" x2="{X(x):.1f}" y1="{base}" y2="{base + 3}"/>'
                       f'<text x="{X(x):.1f}" y="{base + 15}" text-anchor="middle">{_tick_label(x)}</text>')
    out.append(f'<text x="{W - pr}" y="{H - 4}" text-anchor="end">mid-time ({_e(unit)}) · tick height log SNR</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- page ----------


def _letters(n: int) -> list[str]:
    """Candidate captions are lettered a, b, c, ... (the letters on the figures' consensus bands)."""
    return [chr(ord("a") + i) if i < 26 else f"a{i}" for i in range(n)]


def _roman(n: int) -> str:
    """Figure panels are numbered i, ii, iii, ... so they never share a label with a lettered caption."""
    out = ""
    for value, numeral in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"),
                           (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= value:
            out += numeral
            n -= value
    return out


def plate_labels(page: str) -> list[str]:
    """Every figure and caption label on the page, in order (Plate 1, panel i; 1a; ...), for collision checks."""
    panels = re.findall(r'<b class="flabel">(Plate \d+, panel [ivxlcdm]+)\.</b>', page)
    caps = re.findall(r'<b class="fig">(\d+[a-z]\d*)\.', page)
    return panels + caps


def _cand_word(status: str) -> str:
    """The small "candidate" tag, only on what is one: a rejected or flagged dip is named by its status word alone."""
    return '<span class="word cand">candidate</span>' if status in ("passed", "new_candidate", "known_toi") else ""


def _word(status: str) -> str:
    return f'<span class="word {STATUS_CLASS.get(status, "")}">{_e(STATUS_WORD.get(status, status))}</span>'


def _legend(statuses: list[str]) -> str:
    items = "".join(f'<span class="{STATUS_CLASS.get(s, "")}"><i{" class=k" if s == "known_toi" else ""}></i>'
                    f'<span style="color:var(--ink)">{_e(STATUS_WORD.get(s, s))}</span></span>' for s in statuses)
    return f'<div class="legend">{items}</div>'


def _plate(s: dict, i: int) -> str:
    pid = "plate-" + "".join(ch if ch.isalnum() else "-" for ch in s["star"])
    letters = dict(zip((c["candidate_id"] for c in s["candidates"]), _letters(len(s["candidates"]))))
    figs = []
    if s["source"] == "run":
        sub = (f'Run {_e(s["run"])} · {len(s["candidates"])} candidate{"s" if len(s["candidates"]) != 1 else ""} · '
               f'{len(s["subjects"])} subject{"s" if len(s["subjects"]) != 1 else ""}')
        for k, subj in enumerate(s["subjects"]):
            mine = [c for c in s["candidates"] if c["subject_id"] == subj["subject_id"]]
            lc, clip_note = light_curve_svg(subj, mine, letters)
            fold = (fold_svg(subj, mine, letters) if subj["period_days"] is not None and subj["bls_t0"] is not None
                    else '<p class="nocurve">No BLS period is stored for this subject, so there is no folded panel.</p>')
            per = (f'folded on its stored BLS period {_f(subj["period_days"], 4)} d and t0 {_e(subj["time_unit"])} {_f(subj["bls_t0"], 4)}; '
                   f'the shaded band is the stored BLS duration ({_f((_num(subj["bls_duration_days"]) or 0) * 24, 2)} h)'
                   if subj["period_days"] is not None else "no BLS period")
            figs.append(f'''<figure aria-labelledby="{pid}-f{k}">
  <div class="figrow">
    <div class="panel"><h3>{_roman(k + 1)} · whole subject {_e(subj["subject_id"])}</h3><div class="scroll" tabindex="0" role="region" aria-label="Light curve of subject {_e(subj["subject_id"])}, scrolls sideways on a narrow screen">{lc}</div></div>
    <div class="panel"><h3>Phase-folded</h3>{fold}</div>
  </div>
  <figcaption id="{pid}-f{k}"><b class="flabel">Plate {i}, panel {_roman(k + 1)}.</b> Stored flux of subject {_e(subj["subject_id"])} ({_e(subj["time_unit"])} {_f(subj["start"], 2)} to {_f(subj["end"], 2)}), relative flux − 1 in ppm. Shaded bands are consensus intervals, lettered as in the captions; triangles are the BLS epochs. Right: {per}.{clip_note}</figcaption>
</figure>''')
        archive = (f'<div class="archive"><p><b>Archive.</b> {_e(s["crossmatch_line"])}, from {_e(s["crossmatch_source"])}, {_e(s["crossmatch_dated"])}. '
                   f'{_e(NO_DETECTION)}</p></div>') if s.get("crossmatch_line") else ""
    else:
        span = s.get("sector_span") or []
        sub = (f'Search feed · {len(s["candidates"])} entr{"ies" if len(s["candidates"]) != 1 else "y"}'
               + (f' · TESS sectors {span[0]} to {span[-1]}' if span else ""))
        figs.append(f'''<figure aria-labelledby="{pid}-f0">
  <div class="scroll" tabindex="0" role="region" aria-label="Time strip for {_e(s["star"])}, scrolls sideways on a narrow screen">{feed_strip_svg(s)}</div>
  {_legend(sorted({c.get("status") for c in s["candidates"]}))}
  <figcaption id="{pid}-f0"><b class="flabel">Plate {i}, panel i.</b> The catalogue's candidates for {_e(s["star"])} by mid-time; tick height is log SNR, colour and word give the status.</figcaption>
</figure>
<p class="nocurve">No light curve is stored for this star in this build: the search catalogue keeps measured values only, so there is no whole-subject curve and no folded panel.</p>''')
        archive = ""
    caps = "".join(f'<li id="{pid}-{letters[c["candidate_id"]]}"><p class="caption">{_cand_word(c.get("status"))}{_word(c.get("status"))}'
                   f'<b class="fig">{i}{letters[c["candidate_id"]]}. <span class="mono">{_e(c["candidate_id"])}</span>.</b> '
                   f'{_e(c["caption"])}</p></li>' for c in s["candidates"])
    return f'''<article class="plate" id="{pid}" aria-labelledby="{pid}-h">
<h2 class="ptitle" id="{pid}-h"><span class="num">Plate {i}</span> {_e(s["star"])}</h2>
<p class="psub">{sub}.<span class="printonly"> Every candidate on this plate: candidate, unconfirmed.</span></p>
{"".join(figs)}
<ol class="captions" aria-label="Captions for plate {i}">{caps}</ol>
{archive}
</article>'''


def plate_page(data: dict) -> str:
    """The plates as one self-contained HTML page (plain SVG, no script)."""
    title = _e(data["title"])
    stars = data["stars"]
    n = sum(len(s["candidates"]) for s in stars)
    days = data.get("subject_days")
    scope = (f"BLS periods and epochs are found per {days:g}-day subject (a fixed-length cut of a sector), not per sector."
             if days else "BLS periods and epochs are found per subject, not per sector.")
    statuses = [k for k in ("passed", "flagged", "rejected", "new_candidate", "known_toi")
                if any(c.get("status") == k for s in stars for c in s["candidates"])]
    toc = "".join(f'<li><a href="#plate-{"".join(ch if ch.isalnum() else "-" for ch in s["star"])}">Plate {i} · {_e(s["star"])}</a></li>'
                  for i, s in enumerate(stars, 1))
    plates = "".join(_plate(s, i) for i, s in enumerate(stars, 1))
    cat = data["catalog"]
    run = data["run"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{brand.head(data["title"], "SetuHQ's plates: one print-ready plate per star, from the stored run and the search feed. Every number is a stored value; every candidate is unconfirmed.", "/evidence/plates/")}
<style>{PLATE_CSS}{PLATE_LOGO_CSS}</style></head>
<body>
<a class="skip" href="#plates">Skip to the plates</a>
<main class="sheet">
<header class="mast">
  <p class="kicker"><a href="/" aria-label="SetuHQ, home">{brand.logo()}</a><span>plates</span></p>
  <h1>{title}</h1>
  <p><span class="hedge">Candidate, unconfirmed.</span> {n} dips on {len(stars)} stars, one plate per star, from run {_e(run["name"])}{" and the search catalogue" if cat["path"] else ""}. Each dip that passed vetting is a candidate and is tagged so; a rejected or flagged dip is named by its status alone. Every number is a stored value.</p>
  <ul class="notes">
    <li>{_e(scope)}</li>
    <li>The panel is the Sentinels and the Probes, no people. {_e(ATTRIBUTION)} A dip's consensus interval is where their marks agree.</li>
    <li>{_e(NO_RADIUS)}</li>
    <li>Status is written as a word beside every colour.</li>
  </ul>
</header>
<nav class="toc" aria-label="Plates"><h2>Plates</h2><ol>{toc}</ol></nav>
<section class="river" aria-labelledby="river-h">
  <h2 class="ptitle" id="river-h"><span class="num">River of time</span> the whole feed</h2>
  <p class="psub">One row per star, a tick per candidate. Height is log SNR; colour is status, and each row lists its statuses in words. Stretches of more than {RIVER_GAP_DAYS:.0f} days with no candidate are cut, so the segments are not drawn to a common time scale: each has its own, labelled at its start and end, with its span in days (d) beneath it. A known TOI period is an archive value: {_e(NO_DETECTION)}</p>
  <div class="scroll" tabindex="0" role="region" aria-label="River of time, scrolls sideways on a narrow screen">{river_svg(stars)}</div>
  {_legend(statuses)}
</section>
<div id="plates">{plates}</div>
<footer class="colophon">
  <p>Run {_e(run["name"])} ({_e(run["dir"])}), created {_e(run["created_at"])}, config sha256 {_e(run["config_sha256"][:16])}…</p>
  <p>{f'Search catalogue {_e(cat["path"])}, updated {_e(cat["updated"])}, {cat["n"]} entries.' if cat["path"] else "No search catalogue was given to this build."}</p>
  <p>Stored values only; nothing on this page is fitted or looked up when it is built.</p>
</footer>
</main>
</body></html>
"""


def build_plate(run_dir: str | Path, out_dir: str | Path, *, title: str, catalog_path: str | Path | None = None,
                star: str | None = None, require_crossmatch: bool = False) -> Path:
    data = plate_data(run_dir, title=title, catalog_path=catalog_path, star=star, require_crossmatch=require_crossmatch)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    from setuhq.codenote import code_note, with_code_note

    path.write_text(with_code_note(plate_page(data), code_note(run_dir)))
    brand.copy_assets(out)
    return path

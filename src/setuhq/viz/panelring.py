# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""V06 panel ring: a dip's stored marks and calibrated weights converging on its stored panel score.

Used on: dip pages (P3), Home's lead dip (P1) and the Evidence page in "panel" mode (P4). Owner: P3.

Everything it draws is stored: which reviewer marked the dip (the run's mark audit, as the dip pages' lanes read it),
each reviewer's calibrated weight (docs/results/reviewer_weights_full_panel.json), and the panel score as the run
stored it. The words under the ring are the dip's status from ``names.DIP_STATE``, never a claim. A run whose
configuration named no Sentinel shows ``names.PROBES_ONLY`` and no Sentinel node at all (never greyed-out ones).
Wherever Sentinels are drawn, ``names.ATTRIBUTION`` is printed with them.

The markup is the same from Python (the server-rendered dip pages, readable without JavaScript, at final values)
and from :data:`JS` (``SetuPanelRing.html``, when the app changes dip in place); a test compares the two. Once, when
it comes on screen, the lines draw in, the nodes fill and the ring fills to the score (``--d-3``, ``--ease``); under
reduced motion it is its final still.

Data (``html(data)``):

* ``source`` (required): where the marks, weights and score come from.
* ``mode``: "dip" (default) or "panel" (every reviewer with its weight; no dip, so no score).
* ``reviewers``: ``[{id, name, role: "sentinel"|"probe", provider, marked, weight}]`` in the run's order.
* ``score``, ``outcome`` and ``label`` (the dip's name) in dip mode; ``probes_only``; ``uid`` (unique on the page).

:func:`for_dip` and :func:`for_panel` build it from the app's data (``setuhq.app.app_data``).
"""

from __future__ import annotations

import html as _html
import json
import math
from decimal import ROUND_HALF_UP, Decimal

from setuhq.names import ATTRIBUTION, DIP_STATE, PROBES_ONLY, dip_state
from setuhq.viz import require_source

W, H = 360, 240
CX, CY, RING = 180, 120, 46
COL = {"left": 56, "right": 304}
LABEL = "Real data, cited"  # stored marks, weights and score, with their source printed under them
PROBE_PROVIDER = "deterministic matched filter"


def _r1(x: float) -> float:
    """Round half up to one decimal (as JavaScript's Math.round does), so both sides print the same number."""
    return math.floor(x * 10 + 0.5) / 10


def _n(x: float) -> str:
    v = _r1(x)
    return str(int(v)) if v == int(v) else repr(v)


def _e(s) -> str:
    return _html.escape(str(s), quote=True)


def _f2(x: float) -> str:
    """Two decimals as JavaScript's toFixed(2) gives them (the exact binary value, a tie rounded up)."""
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _w(w) -> str:
    return "not stored" if w is None else _f2(w)


def _cl(v: float) -> float:
    return max(0.0, min(1.0, v))


def layout(reviewers: list[dict]) -> list[dict]:
    """Each node's side, position and size: Sentinels on the left and Probes on the right; a panel of one role
    alternates sides. A node's radius grows with its calibrated weight."""
    roles = {r["role"] for r in reviewers}
    sides: dict[str, list[dict]] = {"left": [], "right": []}
    for i, r in enumerate(reviewers):
        side = ("left" if r["role"] == "sentinel" else "right") if len(roles) > 1 else ("right" if i % 2 == 0 else "left")
        sides[side].append(r)
    out = []
    for side in ("left", "right"):
        rs = sides[side]
        k = len(rs)
        step = min(64.0, 190.0 / max(k, 1))
        for i, r in enumerate(rs):
            off = i - (k - 1) / 2
            out.append({**r, "side": side, "x": COL[side], "y": CY + off * step, "rad": 9 + 9 * _cl(r.get("weight") or 0.0),
                        "ty": CY + off * 10})
    return out


def aria(data: dict, rs: list[dict]) -> str:
    """The figure's text alternative: every reviewer, its mark and its weight, then the score and the status."""
    panel = data.get("mode") == "panel"
    who = "; ".join(f'{r["name"]}, weight {_w(r.get("weight"))}' + ("" if panel else (", marked it" if r.get("marked") else ", no mark"))
                    for r in rs)
    if panel:
        return f"The panel: {len(rs)} reviewers, each with its calibrated weight: {who}."
    k = sum(1 for r in rs if r.get("marked"))
    score = data.get("score")
    sc = "not stored" if score is None else _f2(score)
    return (f"{data.get('label') or 'This dip'}: {k} of {len(rs)} reviewers marked it ({who}). "
            f"Panel score {sc} as stored: {dip_state(data.get('outcome'))[2]}.")


def html(data: dict, **opts) -> str:
    """A black stage with the reviewers, their lines to the ring and the stored score, the status, a caption with the
    source, and a table of the same marks and weights. Raises ValueError without ``data["source"]``."""
    require_source(data)
    mode = data.get("mode") or "dip"
    uid = _e(data.get("uid") or "pr")
    rs = [r for r in data.get("reviewers") or [] if not (data.get("probes_only") and r.get("role") == "sentinel")]
    score = data.get("score") if mode == "dip" else None
    if not rs and score is None:
        return ""  # nothing stored to draw: never an empty ring labelled real data
    circ = 2 * math.pi * RING
    lines, dots = [], []
    for i, r in enumerate(layout(rs)):
        left = r["side"] == "left"
        x1 = r["x"] + (r["rad"] if left else -r["rad"])
        x2 = CX - (RING + 8) if left else CX + (RING + 8)
        mx = (x1 + x2) / 2
        on = mode == "panel" or bool(r.get("marked"))
        role = "sen" if r["role"] == "sentinel" else "prb"
        sw = 1 + 3 * _cl(r.get("weight") or 0.0)
        cls = f'{role}{"" if on else " off"}'
        lines.append(f'<path class="prline {cls}" d="M{_n(x1)} {_n(r["y"])}C{_n(mx)} {_n(r["y"])} {_n(mx)} {_n(r["ty"])} {_n(x2)} {_n(r["ty"])}"'
                     f' stroke-width="{_n(sw)}" pathLength="100" style="transition-delay:{i * 60}ms"/>')
        name = r.get("name") or r["id"]
        head, _, tail = name.partition(" · ")
        ly = r["y"] + r["rad"] + 12
        dots.append(f'<g class="prnode {cls}"><circle cx="{_n(r["x"])}" cy="{_n(r["y"])}" r="{_n(r["rad"])}"/>'
                    f'<text x="{_n(r["x"])}" y="{_n(ly)}">{_e(head)}</text>'
                    f'<text x="{_n(r["x"])}" y="{_n(ly + 12)}">{_e(tail)}{" · " if tail else ""}{_w(r.get("weight"))}</text></g>')
    track = f'<circle class="prtrack" cx="{CX}" cy="{CY}" r="{RING}"/>'
    if score is not None:
        ring = (f'{track}<circle class="prring" cx="{CX}" cy="{CY}" r="{RING}" stroke-dasharray="{_n(circ)}" '
                f'style="--off:{_n(circ * (1 - _cl(score)))};--c:{_n(circ)}" transform="rotate(-90 {CX} {CY})"/>'
                f'<text class="prnum" x="{CX}" y="{CY + 7}">{_f2(score)}</text><text class="prsub" x="{CX}" y="{CY + 22}">panel score</text>')
    elif mode == "dip":
        ring = f'{track}<text class="prsub" x="{CX}" y="{CY + 4}">score not stored</text>'
    else:
        ring = f'{track}<text class="prnum" x="{CX}" y="{CY + 7}">{len(rs)}</text><text class="prsub" x="{CX}" y="{CY + 22}">reviewers</text>'
    verdict = ""
    if mode == "dip":
        cls, _, phrase = dip_state(data.get("outcome"))
        k = sum(1 for r in rs if r.get("marked"))
        verdict = (f'<p class="prverdict"><span>{k} of {len(rs)} marked it · panel score '
                   f'{"not stored" if score is None else _f2(score)}, as stored</span>'
                   f'<strong class="prword {_e(cls)}" data-verdict="{_e(phrase)}">{_e(phrase)}</strong></p>')
        what = ("Each reviewer's stored mark on this dip (a solid line: it marked the dip; dashed: no mark), each sized by "
                "its calibrated weight; the ring fills to the panel score as the run stored it.")
    else:
        what = "Every reviewer in the panel, sized by its calibrated weight; no dip is selected, so no score is drawn."
    note = (f" {_e(PROBES_ONLY)}." if data.get("probes_only") else "") + \
        (f" {_e(ATTRIBUTION)}" if any(r["role"] == "sentinel" for r in rs) else "")
    rows = "".join(f'<tr><th scope="row">{_e(r.get("name") or r["id"])} <span class="mono">{_e(r["id"])}</span></th>'
                   f'<td>{"Sentinel" if r["role"] == "sentinel" else "Probe"}</td><td>{_e(r.get("provider") or "")}</td>'
                   + ("" if mode == "panel" else f'<td>{"yes" if r.get("marked") else "no"}</td>')
                   + f'<td class="num">{_w(r.get("weight"))}</td></tr>' for r in rs)
    head = ('<tr><th scope="col">Reviewer</th><th scope="col">Role</th><th scope="col">Provider</th>'
            + ("" if mode == "panel" else '<th scope="col">Marked this dip</th>') + '<th scope="col" class="num">Calibrated weight</th></tr>')
    return (f'<div class="panelring" data-panelring="{_e(mode)}"><figure class="stage prfig" aria-labelledby="prcap-{uid}">'
            f'<span class="stage-tag">{LABEL}</span><svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(aria({**data, "mode": mode}, rs))}">'
            f'<g class="prlines" aria-hidden="true">{"".join(lines)}</g>{ring}<g class="prnodes">{"".join(dots)}</g></svg>{verdict}'
            f'<figcaption class="readout" id="prcap-{uid}">{what} Source: {_e(data["source"])}.{note}</figcaption></figure>'
            f'<details class="prtable"><summary>The marks and weights as a table</summary><div class="tablewrap">'
            f'<table><thead>{head}</thead><tbody>{rows}</tbody></table></div></details></div>')


def source_line(run: str, weights_path: str) -> str:
    return (f"run {run or 'as stored'}, its stored marks and panel score; calibrated weights from "
            f"{weights_path or 'no weights file'}")


def dip_model(dip: dict, *, weights: dict, provenance: dict | None = None, probes_only: bool = False,
              weights_path: str = "", run: str = "", label: str = "") -> dict:
    """The data for one dip from its stored record as the app holds it (its lanes say who marked it, as counted),
    the calibrated weights ({reviewer id: weight}) and the Sentinels' providers (``names.reviewer_provenance``)."""
    prov = provenance or {}
    rs = []
    for ln in dip.get("lanes") or []:
        role = ln.get("role")
        if role not in ("sentinel", "probe"):
            continue
        provider = ((prov.get(ln["id"]) or {}).get("provider_label") or "provider not recorded") if role == "sentinel" else PROBE_PROVIDER
        rs.append({"id": ln["id"], "name": ln.get("name") or ln["id"], "role": role, "marked": bool(ln.get("counted")),
                   "weight": weights.get(ln["id"]), "provider": provider})
    return {"source": source_line(run, weights_path), "mode": "dip", "reviewers": rs, "score": dip.get("score"),
            "outcome": dip.get("outcome"), "label": label, "probes_only": probes_only, "uid": dip.get("id") or "pr"}


def summary(data: dict, dip_id: str) -> str:
    """A dip's ring in its smallest form, for a page with a tight budget (the home page): the label, the stored
    counts, score and status in words, and the source; the page's script draws the full ring in its place
    (``SetuPanelRing.fill``) from the same stored record. "" when nothing is stored, as :func:`html`."""
    require_source(data)
    rs = [r for r in data.get("reviewers") or [] if not (data.get("probes_only") and r.get("role") == "sentinel")]
    score = data.get("score")
    if not rs and score is None:
        return ""
    cls, _, phrase = dip_state(data.get("outcome"))
    k = sum(1 for r in rs if r.get("marked"))
    return (f'<div class="panelring" data-panelring="dip" data-pr-dip="{_e(dip_id)}" data-pr-uid="{_e(data.get("uid") or "pr")}">'
            f'<figure class="stage prfig"><span class="stage-tag">{LABEL}</span><p class="prverdict"><span>{k} of {len(rs)} marked it · panel score '
            f'{"not stored" if score is None else _f2(score)}, as stored</span><strong class="prword {_e(cls)}" data-verdict="{_e(phrase)}">{_e(phrase)}</strong></p>'
            f'<figcaption class="readout">Source: {_e(data["source"])}.</figcaption></figure></div>')


def weights_of(app_data: dict) -> dict:
    """{reviewer id: calibrated weight}, from the app's calibration plane (the weights file)."""
    return {p["id"]: p.get("weight") for p in (app_data.get("calibration") or {}).get("points") or []}


def for_dip(app_data: dict, dip_id: str) -> dict | None:
    """The data for one of the site's dips by id (the lead run's or another example run's), or None."""
    dips = list((app_data.get("story") or {}).get("dips") or []) + list(app_data.get("showcase_dips") or [])
    d = next((x for x in dips if x["id"] == dip_id), None)
    if d is None:
        return None
    run = d.get("run") or (app_data.get("run") or {}).get("name", "")
    ctx = (app_data.get("run_ctx") or {}).get(run) or {}
    return dip_model(d, weights=weights_of(app_data), provenance=app_data.get("reviewer_provenance"),
                     probes_only=bool(ctx.get("probes_only")), weights_path=app_data.get("weights_path") or "",
                     run=run, label=((app_data.get("dips") or {}).get(dip_id) or {}).get("label", ""))


def for_panel(app_data: dict) -> dict:
    """Panel mode: the lead run's reviewers with their calibrated weights; no dip, so no score."""
    prov = app_data.get("reviewer_provenance") or {}
    rs = [{"id": r["id"], "name": r["name"], "role": r["role"], "weight": r.get("weight"), "marked": True,
           "provider": PROBE_PROVIDER if r["role"] == "probe" else ((prov.get(r["id"]) or {}).get("provider_label") or "provider not recorded")}
          for r in (app_data.get("story") or {}).get("reviewers") or [] if r.get("role") in ("sentinel", "probe")]
    run = (app_data.get("run") or {}).get("name", "") or "as stored"
    return {"source": f"the reviewers of run {run}; calibrated weights from {app_data.get('weights_path') or 'no weights file'}",
            "mode": "panel", "reviewers": rs, "uid": "panel"}


CSS = """
/* ---------- viz/panelring (V06): the reviewers converging on the stored panel score ---------- */
.panelring{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;min-width:0}
.prfig{margin:0;display:grid;grid-template-columns:minmax(0,1fr);min-width:0;background-color:var(--stage);background-image:radial-gradient(ellipse at 50% 42%,#0E1630 0,#000 70%)}
.prfig svg{display:block;width:100%;height:auto;margin-top:30px}
.prfig .prline{fill:none;stroke-linecap:round;stroke-dasharray:100;stroke-dashoffset:0;stroke-opacity:.85;transition:stroke-dashoffset var(--d-3) var(--ease)}
.prfig .prline.sen{stroke:var(--sen)}
.prfig .prline.prb{stroke:var(--prb-ink)}
.prfig .prline.off{stroke:var(--stage-dim);stroke-opacity:.5;stroke-dasharray:3 5}
.prfig .prnode circle{stroke-width:1.5;transition:fill-opacity var(--d-3) var(--ease)}
.prfig .prnode.sen circle{fill:#0B4A66;stroke:var(--sen)}
.prfig .prnode.prb circle{fill:#4B2466;stroke:var(--prb-ink)}
.prfig .prnode.off circle{fill:transparent;stroke-dasharray:2 3}
.prfig .prnode text{font:500 10.5px/1 var(--mono);fill:var(--stage-ink);text-anchor:middle}
.prfig .prtrack{fill:#05070D;stroke:rgba(255,255,255,.12);stroke-width:8}
.prfig .prring{fill:none;stroke:#0A84FF;stroke-width:8;stroke-linecap:round;stroke-dashoffset:var(--off);transition:stroke-dashoffset var(--d-3) var(--ease)}
.prfig .prnum{font:700 24px/1 var(--sans);fill:var(--stage-ink);text-anchor:middle;font-variant-numeric:tabular-nums}
.prfig .prsub{font:500 9.5px/1 var(--mono);fill:var(--stage-dim);text-anchor:middle;letter-spacing:.06em;text-transform:uppercase}
.prfig.pr-pre .prline{stroke-dashoffset:100}
.prfig.pr-pre .prline.off{stroke-opacity:0}
.prfig.pr-pre .prnode circle{fill-opacity:0}
.prfig.pr-pre .prring{stroke-dashoffset:var(--c)}
.prverdict{margin:0;padding:4px 14px 0;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 12px;background:var(--stage);font:var(--t-data);color:var(--stage-dim);overflow-wrap:anywhere}
.prword{font:600 15px/1.3 var(--sans);color:var(--stage-ink)}
.prword.cand{color:#FFD60A}
.prword.rej{color:#FF6961}
.prfig .readout{background:var(--stage);color:var(--stage-dim);padding:8px 14px 12px;margin:0;font:12px/1.5 var(--sans);overflow-wrap:anywhere}
.prtable summary{font-size:13px;color:var(--ink-2)}
.prtable .tablewrap{overflow-x:auto}
.prtable table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.prtable th,.prtable td{text-align:left;padding:6px 8px;border-top:1px solid var(--line)}
.prtable td.num,.prtable th.num{text-align:right;font-variant-numeric:tabular-nums}
.prtable .mono{font:400 11px var(--mono);color:var(--ink-3)}
"""

JS = r"""
// ---------- viz/panelring (V06): the markup of setuhq.viz.panelring.html, and a one-time convergence on screen ----------
window.SetuPanelRing = (function(){
  const W = 360, H = 240, CX = 180, CY = 120, RING = 46, COL = {left: 56, right: 304};
  const STATE = __DIP_STATE__, FEED = ['new_candidate', 'known_toi'], PROBES_ONLY = __PROBES_ONLY__, ATTRIBUTION = __ATTRIBUTION__;
  const state = o => STATE[FEED.includes(o) ? 'passed' : (o || '')] || STATE.flagged;
  const n = x => String(Math.floor(x * 10 + 0.5) / 10);
  const e = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  const wf = w => (w === null || w === undefined) ? 'not stored' : w.toFixed(2);
  const cl = v => Math.max(0, Math.min(1, v));
  const has = v => v !== null && v !== undefined;
  function layout(rs){
    const roles = new Set(rs.map(r => r.role)), sides = {left: [], right: []};
    rs.forEach((r, i) => sides[roles.size > 1 ? (r.role === 'sentinel' ? 'left' : 'right') : (i % 2 === 0 ? 'right' : 'left')].push(r));
    const out = [];
    for (const side of ['left', 'right']){
      const list = sides[side], k = list.length, step = Math.min(64, 190 / Math.max(k, 1));
      list.forEach((r, i) => { const off = i - (k - 1) / 2;
        out.push(Object.assign({}, r, {side, x: COL[side], y: CY + off * step, rad: 9 + 9 * cl(r.weight || 0), ty: CY + off * 10})); });
    }
    return out;
  }
  function aria(d, rs){
    const panel = d.mode === 'panel', who = rs.map(r => `${r.name}, weight ${wf(r.weight)}` + (panel ? '' : (r.marked ? ', marked it' : ', no mark'))).join('; ');
    if (panel) return `The panel: ${rs.length} reviewers, each with its calibrated weight: ${who}.`;
    return `${d.label || 'This dip'}: ${rs.filter(r => r.marked).length} of ${rs.length} reviewers marked it (${who}). Panel score ${has(d.score) ? d.score.toFixed(2) : 'not stored'} as stored: ${state(d.outcome)[2]}.`;
  }
  function html(d){
    const mode = d.mode || 'dip', uid = e(d.uid || 'pr');
    if (!(d.reviewers || []).filter(r => !(d.probes_only && r.role === 'sentinel')).length && (mode !== 'dip' || !has(d.score))) return '';  // nothing stored: no ring
    const rs = (d.reviewers || []).filter(r => !(d.probes_only && r.role === 'sentinel'));
    const score = mode === 'dip' && has(d.score) ? d.score : null, circ = 2 * Math.PI * RING, lines = [], dots = [];
    layout(rs).forEach((r, i) => {
      const left = r.side === 'left', x1 = r.x + (left ? r.rad : -r.rad), x2 = left ? CX - (RING + 8) : CX + (RING + 8), mx = (x1 + x2) / 2;
      const on = mode === 'panel' || !!r.marked, cls = (r.role === 'sentinel' ? 'sen' : 'prb') + (on ? '' : ' off'), sw = 1 + 3 * cl(r.weight || 0);
      lines.push(`<path class="prline ${cls}" d="M${n(x1)} ${n(r.y)}C${n(mx)} ${n(r.y)} ${n(mx)} ${n(r.ty)} ${n(x2)} ${n(r.ty)}" stroke-width="${n(sw)}" pathLength="100" style="transition-delay:${i * 60}ms"/>`);
      const name = r.name || r.id, k = name.indexOf(' · '), head = k >= 0 ? name.slice(0, k) : name, tail = k >= 0 ? name.slice(k + 3) : '', ly = r.y + r.rad + 12;
      dots.push(`<g class="prnode ${cls}"><circle cx="${n(r.x)}" cy="${n(r.y)}" r="${n(r.rad)}"/><text x="${n(r.x)}" y="${n(ly)}">${e(head)}</text><text x="${n(r.x)}" y="${n(ly + 12)}">${e(tail)}${tail ? ' · ' : ''}${wf(r.weight)}</text></g>`);
    });
    const track = `<circle class="prtrack" cx="${CX}" cy="${CY}" r="${RING}"/>`;
    const ring = score !== null
      ? `${track}<circle class="prring" cx="${CX}" cy="${CY}" r="${RING}" stroke-dasharray="${n(circ)}" style="--off:${n(circ * (1 - cl(score)))};--c:${n(circ)}" transform="rotate(-90 ${CX} ${CY})"/><text class="prnum" x="${CX}" y="${CY + 7}">${score.toFixed(2)}</text><text class="prsub" x="${CX}" y="${CY + 22}">panel score</text>`
      : mode === 'dip' ? `${track}<text class="prsub" x="${CX}" y="${CY + 4}">score not stored</text>`
      : `${track}<text class="prnum" x="${CX}" y="${CY + 7}">${rs.length}</text><text class="prsub" x="${CX}" y="${CY + 22}">reviewers</text>`;
    let verdict = '', what = 'Every reviewer in the panel, sized by its calibrated weight; no dip is selected, so no score is drawn.';
    if (mode === 'dip'){
      const [c, , phrase] = state(d.outcome);
      verdict = `<p class="prverdict"><span>${rs.filter(r => r.marked).length} of ${rs.length} marked it · panel score ${score !== null ? score.toFixed(2) : 'not stored'}, as stored</span><strong class="prword ${e(c)}" data-verdict="${e(phrase)}">${e(phrase)}</strong></p>`;
      what = "Each reviewer's stored mark on this dip (a solid line: it marked the dip; dashed: no mark), each sized by its calibrated weight; the ring fills to the panel score as the run stored it.";
    }
    const note = (d.probes_only ? ` ${e(PROBES_ONLY)}.` : '') + (rs.some(r => r.role === 'sentinel') ? ` ${e(ATTRIBUTION)}` : '');
    const rows = rs.map(r => `<tr><th scope="row">${e(r.name || r.id)} <span class="mono">${e(r.id)}</span></th><td>${r.role === 'sentinel' ? 'Sentinel' : 'Probe'}</td><td>${e(r.provider || '')}</td>` + (mode === 'panel' ? '' : `<td>${r.marked ? 'yes' : 'no'}</td>`) + `<td class="num">${wf(r.weight)}</td></tr>`).join('');
    const head = '<tr><th scope="col">Reviewer</th><th scope="col">Role</th><th scope="col">Provider</th>' + (mode === 'panel' ? '' : '<th scope="col">Marked this dip</th>') + '<th scope="col" class="num">Calibrated weight</th></tr>';
    return `<div class="panelring" data-panelring="${e(mode)}"><figure class="stage prfig" aria-labelledby="prcap-${uid}"><span class="stage-tag">__LABEL__</span><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(aria(Object.assign({}, d, {mode}), rs))}"><g class="prlines" aria-hidden="true">${lines.join('')}</g>${ring}<g class="prnodes">${dots.join('')}</g></svg>${verdict}<figcaption class="readout" id="prcap-${uid}">${what} Source: ${e(d.source)}.${note}</figcaption></figure><details class="prtable"><summary>The marks and weights as a table</summary><div class="tablewrap"><table><thead>${head}</thead><tbody>${rows}</tbody></table></div></details></div>`;
  }
  // The data for one dip, as setuhq.viz.panelring.dip_model builds it.
  function dipModel(dip, o){
    const prov = o.provenance || {}, w = o.weights || {}, rs = [];
    for (const ln of dip.lanes || []){
      if (ln.role !== 'sentinel' && ln.role !== 'probe') continue;
      rs.push({id: ln.id, name: ln.name || ln.id, role: ln.role, marked: !!ln.counted, weight: has(w[ln.id]) ? w[ln.id] : null,
        provider: ln.role === 'sentinel' ? ((prov[ln.id] || {}).provider_label || 'provider not recorded') : '__PROBE_PROVIDER__'});
    }
    return {source: `run ${o.run || 'as stored'}, its stored marks and panel score; calibrated weights from ${o.weights_path || 'no weights file'}`,
      mode: 'dip', reviewers: rs, score: has(dip.score) ? dip.score : null, outcome: dip.outcome, label: o.label || '', probes_only: !!o.probes_only, uid: dip.id || 'pr'};
  }
  // Once, when it comes on screen: the lines draw in, the nodes fill and the ring fills to the score. Still under
  // reduced motion (the markup is already at its final values).
  let io = null;
  function mount(root){
    const figs = Array.from((root || document).querySelectorAll('.prfig:not([data-pr])'));
    const still = matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window);
    figs.forEach(f => {
      f.dataset.pr = '1'; if (still) return;
      f.classList.add('pr-pre');
      io = io || new IntersectionObserver(es => es.forEach(en => { if (!en.isIntersecting) return; io.unobserve(en.target);
        requestAnimationFrame(() => requestAnimationFrame(() => en.target.classList.remove('pr-pre'))); }), {rootMargin: '0px 0px -10% 0px'});
      io.observe(f);
    });
  }
  // A ring sent in its smallest form (setuhq.viz.panelring.summary) is drawn in full from the app's stored record.
  function fill(root){
    const A = window.D; if (!A) return;
    (root || document).querySelectorAll('[data-pr-dip]').forEach(el => {
      const d = [...((A.story || {}).dips || []), ...(A.showcase_dips || [])].find(x => x.id === el.dataset.prDip); if (!d) return;
      const run = d.run || (A.run || {}).name, w = Object.fromEntries(((A.calibration || {}).points || []).map(p => [p.id, p.weight]));
      const m = dipModel(d, {weights: w, provenance: A.reviewer_provenance, weights_path: A.weights_path, run, label: ((A.dips || {})[d.id] || {}).label || '',
        probes_only: !!(((A.run_ctx || {})[run] || {}).probes_only)});
      m.uid = el.dataset.prUid || m.uid;
      const t = document.createElement('div'); t.innerHTML = html(m); if (t.firstElementChild) el.replaceWith(t.firstElementChild);
    });
  }
  const init = () => { fill(document); mount(document); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  return {html, dipModel, mount, layout, fill};
})();
"""
JS = (JS.replace("__DIP_STATE__", json.dumps({k: list(v) for k, v in DIP_STATE.items()}), 1)
      .replace("__PROBES_ONLY__", json.dumps(PROBES_ONLY), 1).replace("__ATTRIBUTION__", json.dumps(ATTRIBUTION), 1)
      .replace("__LABEL__", LABEL, 1).replace("__PROBE_PROVIDER__", PROBE_PROVIDER, 1))

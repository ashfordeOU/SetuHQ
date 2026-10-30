# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""/candidates/be-the-vetter/: look at a real stored dip, decide, then see what the vetting decided.

A learning exercise, not a contribution to the science: answers stay in the visitor's browser (localStorage, when
allowed) and are never sent or collected. Every dip is a stored dip of a stored example run (the runs the site is built
from), drawn from the run's stored files only: the subject's light curve around the dip, the fold on its stored BLS
period, the stored odd and even depths, and the stored depth at phase 0.5. The answer is the case file's own decision
(:func:`setuhq.docket.outcome`, named by :data:`setuhq.names.DIP_STATE`), with the checks that decided it and the
panel's stored score. A rejected dip shows as rejected.

The four panels are static SVG on a stage ("Real data, cited"); the reveal is a ``<details>``, so the page works
without JavaScript, where the script adds the three answer buttons and the score.
"""

from __future__ import annotations

from setuhq.i18n import N_, k as ik, t

import html
import math
from statistics import median

from setuhq.names import ATTRIBUTION, DIP_STATE, PROBES_ONLY

MAX_DIPS = 8
W, H = 300, 120
CHOICES = (("passed", "Pass"), ("flagged", "Flag"), ("rejected", "Reject"))
NOTE = ("A learning exercise, not a contribution to the science. Your answers stay in this browser and are not collected or sent "
        "anywhere; the dips are stored dips from SetuHQ's example runs, already decided by its vetting.")


def pick(dockets: list[tuple[str, str, dict]]) -> list[tuple[str, str, dict, dict]]:
    """Up to MAX_DIPS stored dips: the first dip of each vetting outcome in each run, taken in turn by outcome (passed,
    rejected, flagged) so the answers mix. ``dockets``: (run name, star name, docket data)."""
    buckets: dict[str, list] = {"passed": [], "rejected": [], "flagged": []}
    for run, star, dock in dockets:
        got: dict[str, dict] = {}
        for c in dock["candidates"]:
            got.setdefault(c["outcome"], c)
        for o, c in got.items():
            buckets.setdefault(o, []).append((run, star, dock, c))
    out = []
    while any(buckets.values()) and len(out) < MAX_DIPS:
        for lst in buckets.values():
            if lst and len(out) < MAX_DIPS:
                out.append(lst.pop(0))
    return out


def _bins(xs: list[float], ys: list[float], lo: float, hi: float, n: int) -> list[tuple[float, float]]:
    acc = [[0.0, 0] for _ in range(n)]
    for x, y in zip(xs, ys):
        if lo <= x < hi and y is not None and math.isfinite(y):
            k = int((x - lo) / (hi - lo) * n)
            acc[k][0] += y
            acc[k][1] += 1
    return [(lo + (k + .5) * (hi - lo) / n, s / c) for k, (s, c) in enumerate(acc) if c]


def _poly(pts: list[tuple[float, float]], x0: float, x1: float, y0: float, y1: float) -> str:
    if not pts:
        return ""
    sx = lambda x: 8 + (x - x0) / ((x1 - x0) or 1) * (W - 16)  # noqa: E731
    sy = lambda y: 12 + (y1 - y) / ((y1 - y0) or 1) * (H - 30)  # noqa: E731
    return "M" + "L".join(f"{sx(x):.0f} {sy(y):.0f}" for x, y in pts)


def _panel(title: str, body: str, alt: str) -> str:
    return (f'<div class="vtp"><b>{html.escape(title)}</b><svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(alt)}">{body}</svg></div>')


def panels(c: dict, subj: dict) -> str:
    """The four stored views of one dip, as static SVG."""
    t, f = subj["time"], subj["flux"]
    med = median([v for v in f if v is not None]) or 1.0
    ppm = [None if v is None else (v / med - 1) * 1e6 for v in f]
    dur = (c.get("duration_hours") or 2) / 24
    out = []
    # 1. the light curve around the dip: ±6 durations (at least a day)
    half = max(1.0, 6 * dur)
    lo, hi = c["t_center"] - half, c["t_center"] + half
    pts = _bins(t, ppm, lo, hi, 120)
    ys = [y for _, y in pts] or [0, 1]
    y0, y1 = min(ys), max(ys)
    sx = lambda x: 8 + (x - lo) / (hi - lo) * (W - 16)  # noqa: E731
    band = f'<rect class="vtwin" x="{sx(c["t_start"]):.0f}" y="0" width="{max(2, sx(c["t_end"]) - sx(c["t_start"])):.0f}" height="{H - 18}"/>'
    out.append(_panel("Light curve", band + f'<path class="vtlc" d="{_poly(pts, lo, hi, y0, y1)}"/><text x="8" y="{H - 4}">'
                      f'{c["time_unit"]} {lo:.1f} to {hi:.1f} · {y0:,.0f} to {y1:,.0f} ppm</text>',
                      f"The stored light curve over {2 * half:.1f} days around the dip, binned, from {y0:,.0f} to {y1:,.0f} ppm; the shaded band is the dip's window."))
    # 2. the fold on the stored period
    P = c.get("period_days")
    if P:
        ph = [((x - c["t_center"]) / P + .5) % 1 - .5 for x in t]
        w = min(.5, max(.04, 4 * dur / P))
        fp = _bins(ph, ppm, -w, w, 80)
        fy = [y for _, y in fp] or [0, 1]
        out.append(_panel("Fold", f'<path class="vtlc" d="{_poly(fp, -w, w, min(fy), max(fy))}"/><text x="8" y="{H - 4}">phase ±{w:.2f} of {P:.3f} d</text>',
                          f"Every point folded on the stored period of {P:.3f} days, phase −{w:.2f} to {w:.2f}, binned."))
    else:
        out.append(_panel("Fold", f'<text x="8" y="60">No stored period: a single dip,</text><text x="8" y="78">so there is nothing to fold.</text>',
                          "No fold: the dip has no stored period."))
    m = c.get("metrics") or {}

    def bars(vals: list[tuple[str, float | None, float | None]], what: str) -> tuple[str, str]:
        fin = lambda x: x is not None and math.isfinite(x)  # noqa: E731
        got = [(n, v * 1e6, (e if fin(e) else 0) * 1e6) for n, v, e in vals if fin(v)]
        if not got:
            return f'<text x="8" y="66">Not measured for this dip.</text>', f"{what}: not measured."
        top = max(1.0, max(abs(v) + e for _, v, e in got))
        g, bw = [], (W - 40) / len(got)
        base = H - 26
        for k, (n, v, e) in enumerate(got):
            x = 24 + k * bw
            h = v / top * (H - 46)
            g.append(f'<rect class="vtbar" x="{x:.0f}" y="{min(base, base - h):.0f}" width="{bw * .5:.0f}" height="{abs(h):.0f}"/>'
                     f'<path class="vterr" d="M{x + bw * .25:.0f} {base - (v + e) / top * (H - 46):.0f}V{base - (v - e) / top * (H - 46):.0f}"/>'
                     f'<text x="{x:.0f}" y="{H - 8}">{html.escape(n)} {v:,.0f}±{e:,.0f}</text>')
        return (f'<path class="vtaxis" d="M16 {base}H{W - 8}"/>' + "".join(g),
                f"{what}: " + "; ".join(f"{n} {v:,.0f} ± {e:,.0f} ppm" for n, v, e in got) + ".")
    b, a = bars([("odd", m.get("odd_depth"), m.get("odd_err")), ("even", m.get("even_depth"), m.get("even_err"))], "Odd and even transit depths")
    out.append(_panel("Odd / even (ppm)", b, a))
    b, a = bars([("transit", m.get("depth"), None), ("phase 0.5", m.get("secondary_depth"), m.get("secondary_err"))], "The transit's depth and the stored depth at phase 0.5")
    out.append(_panel("Secondary (ppm)", b, a))
    return "".join(out)


def reasons(c: dict) -> list[str]:
    """What decided it: each check that did not pass, with its reason, and each stored flag."""
    out = [f"{k['name']}: {'not measured' if k['state'] == 'not_measured' else 'failed'}. {k.get('why') or ''}".strip()
           for k in c.get("checks") or [] if k.get("state") != "pass"]
    return out + [f"flag: {f}" for f in c.get("flags") or [] if not any(f in r for r in out)]


def section(data: dict) -> str:
    """The page's view, from the stored runs the app data names (the lead and the other example runs)."""
    from setuhq.docket import docket_data

    e = html.escape
    runs = [(data["run"]["name"], data["run"]["dir"])] + [(x["run"], x["dir"]) for x in data.get("extra_runs") or []]
    dockets = []
    for name, d in runs:
        ctx = (data.get("run_ctx") or {}).get(name) or {}
        dockets.append((name, ctx.get("star", {}).get("name") or name, docket_data(d, title=name)))
    chosen = pick(dockets)
    labels = data.get("dips") or {}
    stories = {d["id"]: d for d in (data.get("story") or {}).get("dips", []) + (data.get("showcase_dips") or [])}
    cards = []
    for k, (run, star, dock, c) in enumerate(chosen):
        subj = dock["subjects"].get(c["subject_id"])
        if not subj:
            continue
        word = DIP_STATE[c["outcome"]][2]
        why = reasons(c) or ["Every vetting check measured and passing."]
        st = stories.get(c["candidate_id"]) or {}
        lab = (labels.get(c["candidate_id"]) or {}).get("label") or f"{star}, {c['candidate_id']}"
        href = f'/candidates/{(labels.get(c["candidate_id"]) or {}).get("slug", "")}/' if labels.get(c["candidate_id"]) else ""
        probes = PROBES_ONLY if ((data.get("run_ctx") or {}).get(run) or {}).get("probes_only") else ""
        btns = "".join(f'<button class="btn" type="button" data-vt="{o}" aria-pressed="false">{t}</button>' for o, t in CHOICES)
        cards.append(
            f'<article class="card vtcard" id="vt-{k + 1}" data-dip="{e(c["candidate_id"])}" data-out="{c["outcome"]}" aria-labelledby="vth-{k + 1}">'
            f'<h2 id="vth-{k + 1}">Dip {k + 1} of {len(chosen)}</h2>'
            f'<p class="small">{c["time_unit"]} {c["t_center"]:.2f} · {c["depth_ppm"]:,.0f} ppm deep · {c["duration_hours"]:.2f} hours · SNR {c["snr"]:.1f}</p>'
            f'<figure class="vtfig"><div class="stage vtstage"><div class="vtgrid">{panels(c, subj)}</div><span class="stage-tag" data-i18n="label.real">Real data, cited</span></div>'
            f'<figcaption class="skysrc">Stored values of a SetuHQ example run (the star is named after you answer). Source: the run\'s stored '
            f'light curve (TESS SPOC, MAST) and the case file\'s stored measurements.</figcaption></figure>'
            f'<div class="vtpick" role="group" aria-label="Your call on dip {k + 1}" hidden>{btns}</div><p class="vtsay" role="status"></p>'
            f'<details class="vtreveal"><summary>Show what the vetting decided</summary>'
            f'<p><b>Vetting: {e(word)}.</b> {e(st.get("verdict") or "")}</p><ul>{"".join(f"<li>{e(r)}</li>" for r in why)}</ul>'
            f'<p class="small">This was {f"<a href={chr(34)}{e(href)}{chr(34)}>{e(lab)}</a>" if href else e(lab)}. Panel score {c["score"]:.2f}, '
            f'marked by {c["n_reviewers"]} reviewers.{f" {e(probes)}." if probes else ""}</p></details></article>')
    head = (f'<header><p class="eyebrow"{ik("nav.candidates")}>Candidates</p><h1 class="lead-h" id="h-vetter" tabindex="-1"{ik("vt.h1")}>{t("vt.h1", "Be the vetter.")}</h1>'
            f'<p{ik("vt.intro")}>' + t("vt.intro", "Each card is a real dip that one of SetuHQ's example runs stored. Look at its light curve, its fold, its odd and even depths "
            "and its depth half an orbit later, then call it: pass, flag or reject. Then see what the vetting decided, and why.") + '</p></header>')
    score = ('<div class="vtscore" hidden><p role="status" id="vtscore"></p><button class="btn" type="button" id="vtreset">Clear my answers</button></div>')
    guide = ('<details class="card"><summary>What to look for</summary><ul><li><b>Light curve</b>: a dip with a flat floor and sharp edges is '
             'transit-like; a V shape or a lone spike is suspect.</li><li><b>Fold</b>: a real periodic dip lines up at one phase.</li>'
             '<li><b>Odd / even</b>: different depths on alternate dips point to an eclipsing binary at twice the period.</li>'
             '<li><b>Secondary</b>: a dip at phase 0.5 points to a second star being eclipsed.</li></ul>'
             '<p class="small">Pass: a candidate (never a confirmed planet). Flag: open, needs a closer look. Reject: not a candidate.</p></details>')
    return (head + f'<p class="note"><b>{e(NOTE)}</b></p>' + guide + score + "".join(cards)
            + f'<p class="small attribution">{e(ATTRIBUTION)}</p>')


CSS = """
.vtgrid{display:grid;gap:8px;padding:40px 10px 44px;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr))}
.vtp b{font:500 12px var(--mono);color:var(--stage-dim)}.vtp svg{display:block;width:100%;height:auto;font:10px var(--mono);fill:var(--stage-dim)}
.vtlc,.vterr{fill:none;stroke:#ECEFF5}.vtwin{fill:rgba(255,214,10,.16)}.vtbar{fill:#64D2FF}.vtcard{margin:0 0 16px}.vtpick,.vtscore{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.vtpick[hidden],.vtscore[hidden]{display:none}
"""

JS = r"""
function vtWire(){
  const root = $('#route-vetter'); if (!root || root._w) return; root._w = 1;
  let A = {}; try { A = JSON.parse(localStorage.getItem('setuhq-vetter')) || {}; } catch (e) {}
  const C = $$('.vtcard', root), W = {passed: 'pass', flagged: 'flag', rejected: 'reject'};
  const show = (c, o) => { $$('[data-vt]', c).forEach(b => b.setAttribute('aria-pressed', b.dataset.vt === o)); $('.vtsay', c).textContent = o ? `You called it: ${W[o]}. The vetting: ${W[c.dataset.out]}.` : ''; $('.vtreveal', c).open = !!o; };
  const score = () => { const a = C.filter(c => A[c.dataset.dip]); try { localStorage.setItem('setuhq-vetter', JSON.stringify(A)); } catch (e) {}
    $('.vtscore', root).hidden = !a.length; $('#vtscore').textContent = `Your calls match the vetting on ${a.filter(c => A[c.dataset.dip] === c.dataset.out).length} of ${a.length} dips. Kept in this browser only.`; };
  C.forEach(c => { $('.vtpick', c).hidden = false; show(c, A[c.dataset.dip]); });
  root.addEventListener('click', e => { const b = e.target.closest('[data-vt]'), c = b && b.closest('.vtcard');
    if (c){ A[c.dataset.dip] = b.dataset.vt; show(c, b.dataset.vt); score(); } else if (e.target.id === 'vtreset'){ A = {}; C.forEach(c => show(c)); score(); } });
  score();
}
"""

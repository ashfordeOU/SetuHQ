# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""A dip's journey, step by step, and how long ago its light left the star. Read from stored files only.

The strip (on every dip page and in the case file) has six steps, each dated "as of" the date of the data behind it:

1. **Found by SetuHQ**: always, as of the run's date (its manifest).
2. **Vetted**: passed, flagged or rejected, as the case file decides it.
3. **Panel reviewed**: Sentinels and Probes, or Probes only.
4. **Matches a TOI?**: the stored TOI table (``docs/results/showcase_archive.json``, written by
   ``scripts/fetch_showcase_archive.py`` from the NASA Exoplanet Archive) through :func:`setuhq.discover.match_toi`.
5. **Follow-up**: "not announced", unless the matched TOI carries a TFOP Working Group disposition.
6. **In the literature as a planet?**: yes only when the dip's period matches a planet in the archive's ``ps`` table
   (planets the literature reports; :func:`setuhq.docket.compare_with_archive`), with the reference the archive gives.

Steps 1 to 3 are SetuHQ's own; 4 to 6 are other teams' records. A step with no stored record is drawn hollow. Nothing
here says SetuHQ confirmed anything: a "yes" in step 6 is the archive's planet, found by others.
"""

from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

from setuhq.i18n import k as ik, t

ARCHIVE = "docs/results/showcase_archive.json"
PC_TO_LY = 3.261563777  # light years per parsec (IAU)
LABELS = ("Found by SetuHQ", "Vetted", "Panel reviewed", "Matches a TOI?", "Follow-up", "In the literature as a planet?")
DISP = {"KP": "known planet", "CP": "a planet, per follow-up teams", "PC": "planet candidate", "APC": "ambiguous candidate",
        "FP": "false positive", "FA": "false alarm"}


def _root_path(p: str | Path) -> Path:
    q = Path(p)
    if q.exists():
        return q
    alt = Path(__file__).resolve().parents[2] / p
    return alt if alt.exists() else q


@lru_cache(maxsize=4)
def load_archive(path: str = ARCHIVE) -> dict:
    try:
        return json.loads(_root_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tic(target: str | int | None) -> int | None:
    m = re.search(r"(\d+)", str(target or ""))
    return int(m.group(1)) if m else None


def _day(s: str | None) -> str:
    return str(s or "")[:10]


def reference(refname: str | None) -> tuple[str, str]:
    """The archive's reference anchor ('<a ... href=URL ...>Label</a>') as (label, url)."""
    s = str(refname or "")
    m = re.search(r"href=([^\s>]+)", s)
    label = html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
    return label, (m.group(1).strip("'\"") if m else "")


def steps(dip: dict, *, target: str, run_time: str, probes_only: bool, archive: dict | None = None) -> list[dict]:
    """The six steps for one dip: [{label, state ('done', 'no' or 'open'), text, asof, href?}].

    ``dip`` needs ``candidate_id`` (or ``id``), ``outcome``, ``t_center`` (or ``t``), ``time_unit``, ``duration_hours``
    and ``period_days``."""
    from setuhq.discover import Target, Toi, match_toi
    from setuhq.docket import compare_with_archive

    arch = load_archive() if archive is None else archive
    tic, run_day = _tic(target), _day(run_time)
    covered = tic is not None and tic in (arch.get("tics") or [])
    out = [{"state": "done", "text": "yes", "asof": run_day}]
    oc = dip.get("outcome")
    out.append({"state": {"passed": "done", "flagged": "open"}.get(oc, "no"),
                "text": {"passed": "passed", "flagged": "flagged (open)", "rejected": "rejected"}.get(oc, str(oc or "not vetted")), "asof": run_day})
    out.append({"state": "done", "text": "Probes only" if probes_only else "Sentinels and Probes", "asof": run_day})
    cand = {"candidate_id": dip.get("candidate_id") or dip.get("id"), "t_center": dip.get("t_center", dip.get("t")),
            "time_unit": dip.get("time_unit") or "BTJD", "duration_hours": dip.get("duration_hours"), "period_days": dip.get("period_days")}
    toi_day, ps_day = _day((arch.get("toi") or {}).get("fetched_at")), _day((arch.get("ps") or {}).get("fetched_at"))
    if not covered:
        out.append({"state": "open", "text": "no stored TOI table for this star", "asof": ""})
        out.append({"state": "open", "text": "not announced", "asof": ""})
        out.append({"state": "open", "text": "no stored archive record for this star", "asof": ""})
    else:
        rows = [r for r in (arch.get("toi") or {}).get("rows") or [] if _tic(r.get("tid")) == tic]
        tg = Target(tic, tois=[Toi(name=str(r["toi"]), period=_f(r.get("pl_orbper")), tranmid=_f(r.get("pl_tranmid")),
                                   period_err=_f(r.get("pl_orbpererr1")), tranmid_err=_f(r.get("pl_tranmiderr1")),
                                   duration_hours=_f(r.get("pl_trandurh")), disposition=r.get("tfopwg_disp")) for r in rows])
        m = match_toi(cand, tg) if cand["t_center"] is not None else None
        out.append({"state": "done", "text": f"yes: TOI {m['toi']}", "asof": toi_day} if m else
                   {"state": "no", "text": "no TOI at this time and period", "asof": toi_day})
        row = next((r for r in rows if m and str(r["toi"]) == m["toi"]), None)
        disp = (row or {}).get("tfopwg_disp")
        out.append({"state": "done", "text": f"TFOPWG disposition {disp} ({DISP.get(disp, 'as recorded')}), updated {_day(row.get('rowupdate'))}",
                    "asof": toi_day} if disp else {"state": "open", "text": "not announced", "asof": toi_day})
        ps = [r for r in (arch.get("ps") or {}).get("rows") or [] if _tic(r.get("tic_id")) == tic]
        planets = [{"pl_name": r["pl_name"], "pl_orbper": _f(r.get("pl_orbper")), "pl_tranmid": _f(r.get("pl_tranmid")),
                    "tran_flag": str(r.get("tran_flag")) in ("1", "True", "true")} for r in ps]
        hit = compare_with_archive(planets, [cand])["by_candidate"].get(cand["candidate_id"], {}).get("consistent_with")
        if hit:
            label, url = reference(next((r.get("disc_refname") for r in ps if r["pl_name"] == hit), ""))
            out.append({"state": "done", "text": f"yes: {hit}" + (f" ({label})" if label else ""), "href": url, "asof": ps_day})
        else:
            out.append({"state": "no", "text": "no archive planet at this period", "asof": ps_day})
    for s, label in zip(out, LABELS):
        s["label"] = label
    return out


def strip_html(st: list[dict], *, archive: dict | None = None) -> str:
    """The journey strip: an ordered list, a filled dot for a recorded step and a hollow one for an unknown step."""
    e = html.escape
    arch = load_archive() if archive is None else archive
    mark = {"done": "✓", "no": "×", "open": ""}
    lis = []
    for s in st:
        txt = e(s["text"])
        if s.get("href"):
            txt = f'<a rel="noopener" href="{e(s["href"])}">{txt}</a>'
        asof = (f'<small{ik("journey.asof", d=s["asof"])}>{t("journey.asof", "as of {d}", d=s["asof"])}</small>' if s.get("asof")
                else f'<small{ik("journey.nodate")}>{t("journey.nodate", "no date: not recorded")}</small>')
        lis.append(f'<li class="j-{s["state"]}"><i aria-hidden="true">{mark[s["state"]]}</i><b>{e(s["label"])}</b><span>{txt}</span>{asof}</li>')
    src = e(arch.get("source") or "NASA Exoplanet Archive")
    return (f'<div class="journey"><h2 class="jh">This dip so far</h2><ol>{"".join(lis)}</ol>'
            f'<p class="jnote">The first three steps are SetuHQ\'s own; the last three are other teams\' records ({src}: the toi and ps tables), '
            'never SetuHQ results. A hollow dot is a step with no record. TFOPWG: the TESS Follow-up Observing Program Working Group.</p></div>')


def for_run(cands: list[dict], *, target: str, run_time: str, probes_only: bool) -> dict[str, str]:
    """{candidate id: its strip's HTML} for one run's dips."""
    return {c["candidate_id"]: strip_html(steps(c, target=target, run_time=run_time, probes_only=probes_only)) for c in cands}


def light_years(dist_pc: float | None) -> int | None:
    """Light-travel time in years for a distance in parsecs, rounded to two significant figures (at least 1)."""
    d = _f(dist_pc)
    if not d or d <= 0:
        return None
    y = d * PC_TO_LY
    n = len(str(int(y))) - 2
    return max(1, int(round(y, -n if n > 0 else 0)))


def light_line(dist_pc: float | None, source: str, *, what: str = "this dip") -> str:
    """'The light in this dip left the star about 60 years ago (distance 18.37 pc, exoplanet.eu, fetched …).', or ""."""
    y = light_years(dist_pc)
    if y is None:
        return ""
    lead = "The light in this dip left the star" if what == "this dip" else "The light from this star left it"
    return f"{lead} about {y:,} years ago (distance {'%g' % _f(dist_pc)} pc, {source})."


def star_distance(cat: dict | None, names: list[str]) -> float | None:
    """The catalogue's stored distance (pc) for a star, by its name, an alternative name, or one of its planets."""
    if not cat:
        return None
    P = cat["planets"]
    for n in [x for x in names if x]:
        for i in range(len(P["name"])):
            alts = {a.strip() for a in str(P["salt"][i] or "").split(",")}
            if (P["star"][i] == n or n in alts or P["name"][i] == n) and _f(P["dist"][i]):
                return _f(P["dist"][i])
    return None


CSS = """
/* ---------- the journey strip (setuhq.journey): a dip's steps, each dated ---------- */
.journey{margin:14px 0;border:1px solid var(--line-2);border-radius:14px;padding:12px 14px}
.journey .jh{margin:0 0 8px;font:600 14px/1.3 var(--sans)}
.journey ol{list-style:none;margin:0;padding:0;display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr))}
.journey li{display:grid;grid-template-columns:22px 1fr;column-gap:6px;font-size:13px;line-height:1.35}
.journey li i{grid-row:span 3;width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font:700 11px/1 var(--sans);font-style:normal;border:2px solid var(--ink-3);color:var(--bg)}
.journey .j-done i{background:var(--green);border-color:var(--green)}.journey .j-no i{background:var(--ink-3)}
.journey .j-open i{background:transparent}
.journey li span,.journey li small{color:var(--ink-3)}.journey li span{color:var(--ink)}
.journey .jnote{margin:8px 0 0;font-size:12px;color:var(--ink-3)}
"""

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Data for the app's five sections (Overview, Sky, Transit, Explorer, Sentinels).

Everything here is read from stored files: the run's subjects, marks, decisions and
classifications, the Docket's checks and cross-match, the discovery catalogue and the
reviewer weights. Points are the stored flux values (rounded for the page); nothing is
fitted. Where a figure is decorative (field stars, the artist's impression of the
planet) the page says so; where a value is not stored (feed stars' sky positions, an
impact parameter) the page says that too.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from setuhq.i18n import span as ispan
from setuhq.names import display_name, role

DEFAULT_TARGETS = "docs/results/targets.json"
STATUS_COLOURS = {"known": "#0A84FF", "open": "#FFD60A", "rejected": "#FF453A"}
_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
          "sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    """26 -> 'twenty-six' (0 to 99); larger numbers stay as digits."""
    if n < 0 or n > 99:
        return str(n)
    if n < 20:
        return _WORDS[n]
    t, u = divmod(n, 10)
    return _TENS[t] + ("" if u == 0 else "-" + _WORDS[u])


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def read_targets(path: str | Path | None = DEFAULT_TARGETS) -> dict:
    if path is None or not Path(path).exists():
        return {"source": "", "targets": {}}
    return json.loads(Path(path).read_text())


def confidences(run_dir: Path) -> dict[tuple[str, str], float]:
    """(subject, reviewer) -> the confidence the reviewer stored with its classification."""
    out: dict[tuple[str, str], float] = {}
    path = Path(run_dir) / "classifications.csv"
    if not path.exists():
        return out
    with path.open() as handle:
        for row in csv.DictReader(handle):
            try:
                meta = json.loads(row.get("metadata") or "{}")
            except ValueError:
                continue
            if meta.get("confidence") is not None:
                out[(row["subject_ids"], row["user_name"])] = float(meta["confidence"])
    return out


def dip_status(c: dict, comparison: dict) -> dict:
    """known (archive match), open (passed or flagged, no match) or rejected, with its label."""
    cmp = comparison.get(c["candidate_id"]) or {}
    planet = cmp.get("consistent_with")
    if planet and c.get("outcome") != "rejected":
        return {"key": "known", "label": f"{planet} · known planet", "planet": planet}
    if c.get("outcome") == "rejected":
        return {"key": "rejected", "label": "Rejected by vetting", "planet": None}
    if c.get("outcome") == "flagged":
        return {"key": "open", "label": "Open · flagged for review", "planet": None}
    return {"key": "open", "label": "Open · candidate, unconfirmed", "planet": None}


def _reasons(c: dict) -> list[str]:
    return [f"{k['name']} {k['value']} (rule {k['rule']})" for k in c.get("checks") or [] if k.get("state") in ("fail", "flag")]


def verdict_text(c: dict, status: dict, who: dict, cmp: dict) -> str:
    """One paragraph from the stored outcome, its failing or flagged checks and the archive comparison."""
    reasons = _reasons(c)
    out = c.get("outcome")
    if out == "passed":
        first = "Passed every vetting check."
    elif out == "flagged":
        first = f"Flagged for review: {'; '.join(reasons)}." if reasons else "Flagged for review."
    else:
        first = f"Rejected by vetting: {'; '.join(reasons)}." if reasons else "Rejected by vetting."
    if status["key"] == "known":
        hit = next((p for p in cmp.get("planets") or [] if p.get("pl_name") == status["planet"]), {})
        dp = f" (ΔP {hit['dP_pct']:.2f}%)" if hit.get("dP_pct") is not None else ""
        rest = (f" Its period matches {status['planet']} in the stored archive cross-match{dp}: a known planet, "
                f"recovered, not a discovery. The dip itself stays a candidate, unconfirmed as an independent detection.")
    else:
        single = " A single dip with no BLS period of its own." if not c.get("period_days") else ""
        tail = {"passed": " Candidate, unconfirmed.", "flagged": " Open: a candidate only if review clears it."}.get(
            out, " Not a candidate.")  # a rejected dip is never called a candidate
        rest = f"{single} Marked by {who['text']}.{tail}"
    return first + rest


def story_data(run_dir: str | Path, dock: dict, feed: list[dict], calibration: dict, hero: dict,
               targets_path: str | Path | None = DEFAULT_TARGETS) -> dict:
    run_dir = Path(run_dir)
    kinds = dock["reviewers"]
    sentinels = [r for r, k in kinds.items() if role(k) == "sentinel"]
    probes = [r for r, k in kinds.items() if role(k) == "probe"]
    xm = dock.get("crossmatch") or {}
    comparison = (xm.get("comparison") or {}).get("by_candidate") or {}
    conf = confidences(run_dir)
    subjects = dock["subjects"]
    cands = sorted(dock["candidates"], key=lambda c: c["t_center"])
    lead = hero.get("lead") or {}
    targets = read_targets(targets_path)

    dips = []
    for i, c in enumerate(cands):
        subj = subjects[c["subject_id"]]
        dur = max(1e-3, c["t_end"] - c["t_start"])
        half = max(0.25, 1.5 * dur)
        lo, hi = c["t_center"] - half, c["t_center"] + half
        pts = [[round(t - c["t_center"], 5), round((f - 1.0) * 1e6, 1)] for t, f in zip(subj["time"], subj["flux"]) if lo <= t <= hi]
        marks = (dock["marks"].get(c["subject_id"]) or {})
        audit = {a["reviewer_id"]: a for a in c.get("mark_audit") or []}
        lanes = []
        for rid, k in kinds.items():
            spans = [[round(a - c["t_center"], 5), round(b - c["t_center"], 5)] for a, b in marks.get(rid) or [] if b >= lo and a <= hi]
            lanes.append({"id": rid, "name": display_name(rid, k), "role": role(k) or "other", "spans": spans,
                          "counted": bool((audit.get(rid) or {}).get("counted")) and rid in (c.get("reviewers") or [])})
        marked = [ln["id"] for ln in lanes if ln["counted"]]
        n_s = sum(1 for r in marked if r in sentinels)
        n_p = sum(1 for r in marked if r in probes)
        who = {"sentinels": n_s, "of_sentinels": len(sentinels), "probes": n_p, "of_probes": len(probes),
               "text": f"{n_p} of {len(probes)} Probes and {n_s} of {len(sentinels)} Sentinels"}
        status = dip_status(c, comparison)
        cmp = comparison.get(c["candidate_id"]) or {}
        # The Sentinel's words: its stored rationale for this subject (one per 13-day subject, not per dip).
        dec = (dock.get("decisions") or {}).get(c["subject_id"]) or {}
        quotes = []
        for rid in sentinels:
            d = dec.get(rid) or {}
            if not d.get("rationale"):
                continue
            quotes.append({"id": rid, "name": display_name(rid, kinds[rid]), "text": d["rationale"],
                           "label": (d.get("label") or "").replace("_", " "), "confidence": conf.get((c["subject_id"], rid)),
                           "marked": rid in marked})
        quotes.sort(key=lambda q: (not q["marked"], -(q["confidence"] or 0)))
        phase = None
        if lead.get("period_days") and lead.get("t0") is not None:
            P, t0 = lead["period_days"], lead["t0"]
            ph = ((c["t_center"] - t0) / P) % 1.0
            phase = round(ph - 1.0 if ph > 0.5 else ph, 4)
        dips.append({
            "id": c["candidate_id"], "letter": _letter(i), "t": c["t_center"], "t_start": c["t_start"], "t_end": c["t_end"],
            "time_unit": c.get("time_unit", ""), "subject": c["subject_id"], "subject_label": c.get("subject_label", ""),
            "subject_start": subj["start"], "subject_end": subj["end"],
            "depth_ppm": c["depth_ppm"], "duration_hours": c.get("duration_hours"), "snr": c["snr"], "score": c.get("score"),
            "n_reviewers": c.get("n_reviewers"), "outcome": c.get("outcome"), "flags": c.get("flags") or [],
            "period_days": c.get("period_days"), "signal_id": c.get("signal_id", ""),
            "status": status["key"], "status_label": status["label"], "planet": status["planet"],
            "ratio": math.sqrt(c["depth_ppm"] * 1e-6) if c["depth_ppm"] and c["depth_ppm"] > 0 else None,
            "half": half, "pts": pts,
            # The stored limb-darkened fit of this dip, as (time from mid-dip, ppm); [] when no fit is stored.
            "model": [[round(t - c["t_center"], 5), round(p, 1)] for t, p in c.get("model") or []],
            "fit_depth_ppm": (c.get("fit") or {}).get("depth_ppm"), "fit_t14_hours": (c.get("fit") or {}).get("t14_hours"),
            # The fit's own shape, so a dip page can draw this dip's model: Rp/R★, b and the limb darkening it used.
            "fit_k": (c.get("fit") or {}).get("k"), "fit_b": (c.get("fit") or {}).get("b"),
            # Where the fit puts this dip's mid-time, from the dip's own mid-time (days): the model is drawn there.
            "fit_dt0": round((c.get("fit") or {})["t0"] - c["t_center"], 6) if (c.get("fit") or {}).get("t0") is not None else None,
            "fit_ld": [(c.get("fit") or {}).get("u1"), (c.get("fit") or {}).get("u2")] if (c.get("fit") or {}).get("u1") is not None else None,
            "lanes": lanes, "who": who, "quotes": quotes, "phase": phase,
            "on_lead": c.get("signal_id") == lead.get("signal_id"),
            "verdict": verdict_text(c, status, who, cmp), "archive_line": cmp.get("line", ""),
        })

    counts = {k: sum(1 for d in dips if d["status"] == k) for k in STATUS_COLOURS}
    planet = next((d["planet"] for d in dips if d["planet"]), None)
    target = hero.get("target") or ""
    info = (targets.get("targets") or {}).get(target) or {}
    star = info.get("name") or target
    span = round(hero.get("span_days") or 0)
    line1 = f"{_cap(number_words(span))} days of {star}."
    parts = []
    if planet:
        parts.append("One planet found again.")
    if counts["open"]:
        parts.append(f"{_cap(number_words(counts['open']))} dip{'' if counts['open'] == 1 else 's'} unexplained.")
    if not parts:
        parts.append(f"{_cap(number_words(len(dips)))} dips, every one a candidate.")
    sky_title = [line1, " ".join(parts)]

    # The proof strip: four stored facts.
    v = xm.get("validation") or {}
    proof = []
    if planet and v.get("pl_name") == planet:
        mins = f"{abs(v.get('mean_timing_offset_min', 0)):.0f}"
        proof.append({"big": str(v.get("epochs_recovered", "")), "colour": "#64D2FF",
                      "text": f"transits of {planet} found without being told where to look, each about "
                              f"{mins} minutes from its published timing. A known planet, recovered.",
                      "html": ispan("story.recovered", "transits of {planet} found without being told where to look, each about {min} minutes "
                                   "from its published timing. A known planet, recovered.", planet=planet, min=mins)})
    elif planet:
        proof.append({"big": str(counts["known"]), "colour": "#64D2FF",
                      "text": f"dips on the period of {planet}, a known planet. Recovered, not discovered.",
                      "html": ispan("story.recovered_period", "dips on the period of {planet}, a known planet. Recovered, not discovered.", planet=planet)})
    proof.append({"big": f"{len(sentinels)} + {len(probes)}", "colour": "#F5F5F7",
                  "text": "AI Sentinels and Probes read this run's light curve; each vote counts as much as it scored on planted test transits.",
                  "html": ispan("story.panel", "AI Sentinels and Probes read this run's light curve; each vote counts as much as it scored on planted test transits.")})
    if feed:
        stars = {r["tic"] for r in feed}
        n_new = sum(1 for r in feed if r.get("status") == "new_candidate")
        proof.append({"big": str(len(feed)), "colour": "#FFD60A",
                      "text": f"entries from {len(stars)} more star{'s' if len(stars) != 1 else ''} in the search feed, "
                              + (f"{n_new} at a new period. " if n_new else "matching known TOIs. ")
                              + "Leads for review, not planets.",
                      "html": ispan("story.feed", "entries from {stars, plural, one {# more star} other {# more stars}} in the search feed, "
                                   "{new, plural, =0 {matching known TOIs.} one {# at a new period.} other {# at a new period.}} Leads for review, not planets.",
                                   stars=len(stars), new=n_new)})
    opens = [d for d in dips if d["status"] == "open"]
    if opens:
        w = opens[0]["who"]
        saw = (f"The Probes saw it ({w['probes']} of {w['of_probes']})." if w["probes"] else "No Probe marked it.")
        saw_h = (ispan("story.probes_saw", "The Probes saw it ({k} of {n}).", k=w["probes"], n=w["of_probes"]) if w["probes"]
                 else ispan("story.no_probe", "No Probe marked it."))
        both = w["sentinels"] == 0 and w["of_sentinels"] == 2
        sen = "Both Sentinels passed it by." if both else f"{w['sentinels']} of {w['of_sentinels']} Sentinels marked it."
        sen_h = (ispan("story.both_passed", "Both Sentinels passed it by.") if both
                 else ispan("story.sentinels", "{k} of {n} Sentinels marked it.", k=w["sentinels"], n=w["of_sentinels"]))
        proof.append({"big": str(len(opens)), "colour": "#F5F5F7",
                      "text": f"dip{'' if len(opens) == 1 else 's'} still open. {saw} {sen}",
                      "html": f'{ispan("story.open", "{n, plural, one {dip} other {dips}} still open.", n=len(opens))} {saw_h} {sen_h}'})

    sectors = {}
    for r in feed:
        span_ = r.get("sector_span") or []
        if span_:
            sectors[r["tic"]] = f"{span_[0]}–{span_[-1]}" if span_[0] != span_[-1] else str(span_[0])
    explorer = [{"i": i, "id": r["candidate_id"], "tic": r["tic"], "period_days": r.get("period_days"),
                 "depth_ppm": r.get("depth_ppm"), "snr": r.get("snr"), "duration_hours": r.get("duration_hours"),
                 "status": r.get("status"), "sectors": sectors.get(r["tic"], ""), "t_center": r.get("t_center"),
                 "time_unit": r.get("time_unit", "")} for i, r in enumerate(feed)]

    reviewers = []
    for p in calibration.get("points") or []:
        if p["id"] not in kinds:
            continue
        n_inj, n_emp = p.get("n_injected"), p.get("n_empty")
        reviewers.append({
            "id": p["id"], "name": display_name(p["id"], kinds[p["id"]]), "role": role(kinds[p["id"]]) or "other",
            "weight": p.get("weight"), "tpr": p.get("tpr"), "fpr": p.get("fpr"), "n_injected": n_inj, "n_empty": n_emp,
            "hits": None if p.get("tpr") is None or not n_inj else round(p["tpr"] * n_inj),
            "false_alarms": None if p.get("fpr") is None or not n_emp else round(p["fpr"] * n_emp),
            "marked": [d["id"] for d in dips if p["id"] in [ln["id"] for ln in d["lanes"] if ln["counted"]]],
        })
    reviewers.sort(key=lambda r: (r["role"] != "sentinel", r["name"]))

    return {
        "star": {"target": target, "name": star, "ra_deg": info.get("ra_deg"), "dec_deg": info.get("dec_deg"),
                 "source": targets.get("source", "") if info else ""},
        "dips": dips, "counts": counts, "planet": planet, "sky_title": sky_title, "proof": proof,
        "explorer": explorer, "reviewers": reviewers, "colours": STATUS_COLOURS,
        "lead_dip": next((d["id"] for d in dips if d["id"] == lead.get("dip")), dips[0]["id"] if dips else None),
    }


def _letter(i: int) -> str:
    """A dip's number in time order (1, 2, 3 ...): its plain label, "dip 2", and its address, /candidates/<star>/dip-2/."""
    return str(i + 1)


# ---------- decorative and projected geometry (computed once, at build time) ----------

SQRT2 = math.sqrt(2)
SKY_R = 452 / (2 * SQRT2)


def mollweide(ra_deg: float, dec_deg: float) -> tuple[float, float]:
    """Mollweide projection to the sky map's frame (RA increasing to the left, as on the sky)."""
    ra = ra_deg - 360 if ra_deg > 180 else ra_deg
    lam, phi = -ra * math.pi / 180, dec_deg * math.pi / 180
    th = phi
    for _ in range(30):
        f = 2 * th + math.sin(2 * th) - math.pi * math.sin(phi)
        th -= f / (2 + 2 * math.cos(2 * th) + 1e-12)
    return SKY_R * 2 * SQRT2 / math.pi * lam * math.cos(th), -SKY_R * SQRT2 * math.sin(th)


class _Rand:
    """A small seeded generator, so the decorative stars are the same on every build."""

    def __init__(self, seed: int = 131):
        self.s = seed

    def __call__(self) -> float:
        self.s = (self.s * 1664525 + 1013904223) % 4294967296
        return self.s / 4294967296


def sky_geometry(ra_deg: float | None, dec_deg: float | None) -> dict:
    """Graticule, ecliptic and the target's projected position. (The map's stars are the catalogue's real hosts,
    drawn by setuhq.viz.skyyears; the decorative field stars are gone.)"""
    grat = []
    for dec in range(-60, 61, 30):
        grat.append("".join(("M" if ra == -180 else "L") + "%.1f %.1f" % mollweide(ra, dec) for ra in range(-180, 181, 6)))
    for ra in range(-150, 151, 30):
        grat.append("".join(("M" if d == -90 else "L") + "%.1f %.1f" % mollweide(ra, d) for d in range(-90, 91, 6)))
    eps, ecl, prev = 23.44 * math.pi / 180, [], None
    for lon in range(0, 361, 3):
        L = lon * math.pi / 180
        de = math.asin(math.sin(eps) * math.sin(L))
        al = math.atan2(math.cos(eps) * math.sin(L), math.cos(L)) * 180 / math.pi % 360
        x, y = mollweide(al, de * 180 / math.pi)
        ecl.append(("M" if prev is None or abs(x - prev) > 200 else "L") + "%.1f %.1f" % (x, y))
        prev = x
    pos = mollweide(ra_deg, dec_deg) if ra_deg is not None and dec_deg is not None else None
    return {"grat": "".join(grat), "ecl": "".join(ecl),
            "x": round(pos[0], 2) if pos else None, "y": round(pos[1], 2) if pos else None}


def decoration() -> dict:
    """The page's star dust and the artist's-impression cloud bands. Decorative only."""
    r = _Rand(977)
    dust = "".join("M%d %dh0" % (r() * 1440, r() * 1100) for _ in range(420))
    bright = "".join("M%d %dh0" % (r() * 1440, r() * 1100) for _ in range(40))
    bands = ""
    for b in range(9):
        y = 420 + b * 30 + r() * 12
        x0 = -200 + r() * 200
        bands += "M%d %d C%d %d %d %d %d %d" % (x0, y, x0 + 500, y - 18, x0 + 1100, y + 18, x0 + 2000, y)
    return {"dust": dust, "bright": bright, "bands": bands}

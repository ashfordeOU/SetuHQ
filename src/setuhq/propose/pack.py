# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Build a CHEOPS proposal preparation pack: one new directory with the rules check, the target status, the
evidence, the planning estimates, the anonymised drafts, the checklist and every source it read.

Files (generic names, nothing identifying):

    README.md                       summary, disclaimer, what to do next
    checklist.md                    ESA's seven steps, in order, with links and this pack's findings
    scientific-justification.md     anonymised draft (generic headings)
    technical-justification.md      anonymised draft (generic headings)
    anonymity-lint.txt              the lint's findings on the drafts and file names
    pack.json                       everything above, machine-readable, with provenance
    sources/                        the public responses read (RTL CSV, archive and SIMBAD answers), with URL,
                                    fetch time and SHA-256 in pack.json

The pack never overwrites: the directory must not exist.
"""

from __future__ import annotations

import json
import re
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from setuhq import __version__
from setuhq.propose import draft, evidence, planning, rules, sources, targets

ARCHIVE_RADIUS_ARCSEC = 30.0


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s[:40] or "target"


def default_name(target: str, cycle: str) -> str:
    return f"cheops-{slug(target)}-{cycle}"


def _mjd_iso(mjd):
    from astropy.time import Time

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # ERFA's "dubious year" for dates past the leap-second table
            return Time(float(mjd), format="mjd", scale="utc").isot[:19]
    except (TypeError, ValueError):
        return None


def _jd(d: date) -> float:
    from astropy.time import Time

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(Time(d.isoformat(), scale="utc").jd)


def _save(out: Path, name: str, got: sources.Fetched | None) -> dict | None:
    if got is None:
        return None
    p = out / "sources" / name
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(got.body)
    return got.record(saved_as=f"sources/{name}")


def build_pack(target: str, out_dir: Path, *, root: Path, programme: str = "regular", orbits: int | None = None,
               cycle: str | None = None, now: datetime | None = None, fetcher: sources.Fetcher | None = None,
               ra: float | None = None, dec: float | None = None, coord_source: str | None = None,
               gmag: float | None = None, event: str = "transit", depth_ppm: float | None = None,
               duration_hours: float | None = None, target_snr: float = 10.0, efficiency: float = 0.7,
               t0: float | None = None, t0_err: float | None = None, period: float | None = None,
               period_err: float | None = None, window_start: date | None = None, window_end: date | None = None,
               flare_rate: float | None = None, n_sigma: float = 3.0, rtl_radius_arcsec: float = 20.0,
               author_names=(), institutions=(), use_toi_table: bool = True, claimed: bool = False) -> dict:
    """Build the pack into ``out_dir`` and return its ``pack.json`` content. ``out_dir`` is created and must not
    exist, unless ``claimed``: then it is a directory the caller has just created, and it must be empty."""
    now = now or datetime.now(timezone.utc)
    fetcher = fetcher or sources.Fetcher(cache_dir=None)
    prog = rules.programme(programme)
    out_dir = Path(out_dir)
    errors_net: list[str] = []
    provenance: list[dict] = []

    # ---- the calendar
    if cycle:
        cy = rules.parse_cycle(cycle)
    else:
        cy = rules.next_cycle(now, prog)
        if cy is None:
            raise ValueError(f"no {prog.label} cycle left in the Running Call after {now:%Y-%m-%d}")
    cinfo = rules.cycle_info(*cy, prog, now)
    orbit_check = rules.check_orbits(orbits, prog)
    w_start = window_start or max(date.fromisoformat(cinfo["earliest_start"]), rules.CALL_START)
    w_end = window_end or rules.CALL_END
    window = rules.check_window(w_start, w_end, date.fromisoformat(cinfo["earliest_start"]))
    if claimed:
        if not out_dir.is_dir() or any(out_dir.iterdir()):
            raise ValueError(f"{out_dir}: a claimed pack directory must exist and be empty")
    else:
        out_dir.mkdir(parents=True, exist_ok=False)

    # ---- coordinates: SIMBAD first, MAST if SIMBAD does not know the name
    resolved, got_simbad, got_mast = None, None, None
    try:
        resolved, got_simbad = sources.resolve_simbad(fetcher, target)
    except sources.SourceError as exc:
        errors_net.append(f"SIMBAD: {exc}")
    if resolved is None:
        try:
            resolved, got_mast = sources.resolve_mast(fetcher, target)
        except sources.SourceError as exc:
            errors_net.append(f"MAST: {exc}")
    provenance += [r for r in (_save(out_dir, "simbad.json", got_simbad), _save(out_dir, "mast-lookup.json", got_mast)) if r]
    coord_warn = []
    if ra is not None and dec is not None:
        coord_warn = targets.coordinate_warnings(coord_source or "user", ra, dec,
                                                 resolved.ra if resolved else None, resolved.dec if resolved else None,
                                                 resolved.pmra if resolved else None, resolved.pmdec if resolved else None)
        replace = bool(resolved) and (coord_source or "").lower() in ("exofop", "gaia")
        use_ra, use_dec = (resolved.ra, resolved.dec) if replace else (ra, dec)
        csrc = (f"{resolved.source} (supplied {coord_source} position replaced)" if replace
                else f"supplied by the user ({coord_source or 'source not given'})")
    elif resolved:
        use_ra, use_dec, csrc = resolved.ra, resolved.dec, resolved.source
    else:
        use_ra = use_dec = None
        csrc = "unresolved: give --ra/--dec from the Target Checker, SIMBAD or MAST"
    g = gmag if gmag is not None else (resolved.gmag if resolved else None)
    aliases = resolved.aliases if resolved else []
    tic = sources.tic_from_aliases(aliases) or (int(m.group(1)) if (m := re.fullmatch(r"\s*TIC\s*(\d+)\s*", target, re.I)) else None)
    tinfo = {"name": target, "main_id": resolved.main_id if resolved else None, "ra": use_ra, "dec": use_dec,
             "coord_source": csrc, "coord_warnings": coord_warn, "gmag": g,
             "gmag_source": "user" if gmag is not None else ("SIMBAD" if g is not None else None),
             "sptype": resolved.sptype if resolved else None, "tic": tic,
             "resolved": resolved.as_dict() if resolved else None}

    # ---- target status: the RTL and the archive
    rtl = {"checked": False}
    try:
        lists = sources.load_rtl(fetcher)
        provenance.append(lists["call_page"] | {"what": "Running Call page (to find the RTL CSV links)"})
        entries = []
        for lst in lists["lists"]:
            rec = _save(out_dir, lst["file"], lst["fetched"])
            provenance.append(rec | {"what": f"Reserved Target List: {lst['title']}"})
            entries += lst["entries"]
        rtl = {"checked": True, "lists": [{"file": x["file"], "title": x["title"], "link_text": x["link_text"],
                                            "n_entries": len(x["entries"])} for x in lists["lists"]]}
        rtl |= targets.match_rtl(entries, name=target, aliases=aliases, ra=use_ra, dec=use_dec,
                                 radius_arcsec=rtl_radius_arcsec)
        rtl["note"] = ("Which list applies depends on the dates: ESA's page lists the 2027-2029 reservations; the "
                       "Target Checker is definitive at submission time.")
    except (sources.SourceError, ValueError) as exc:
        errors_net.append(f"RTL: {exc}")

    archive = {"checked": False}
    try:
        answers = []
        if use_ra is not None:
            answers.append(("cone", sources.dace_cone(fetcher, use_ra, use_dec, ARCHIVE_RADIUS_ARCSEC / 3600.0)))
        answers.append(("name", sources.dace_name(fetcher, (resolved.main_id if resolved else None) or target)))
        public, seen, no_match = [], set(), []
        for kind, a in answers:
            if a["fetched"] is not None:  # only the filtered copy exists: public visits and a count
                provenance.append(_save(out_dir, f"archive-{kind}.json", a["fetched"])
                                  | {"what": f"DACE CHEOPS visits, {kind} search (filtered: public fields only)"})
            if a["no_match"]:
                no_match.append(kind)
            for v in a["public_visits"]:
                if v.get("visit_id") not in seen:
                    seen.add(v.get("visit_id"))
                    public.append(v)
        # Visits not yet public are only counted per query, so the two counts cannot be merged exactly.
        hidden = max((a["n_not_public"] for _, a in answers), default=0)
        public_rows = [{"visit_id": v.get("visit_id"), "file_key": v.get("file_key"), "object": v.get("obj_id_catname"),
                        "programme_id": v.get("full_program_name"), "start_utc": _mjd_iso(v.get("date_mjd_start")),
                        "end_utc": _mjd_iso(v.get("date_mjd_end")), "light_curve_available": v.get("db_lc_available")}
                       for v in public]
        archive = {"checked": True, "source": f"DACE public CHEOPS metadata ({sources.DACE_CHEOPS}), the query interface "
                                              "of the CHEOPS Mission Archive",
                   "cone_radius_arcsec": ARCHIVE_RADIUS_ARCSEC, "already_observed": bool(public or hidden),
                   "n_public": len(public), "n_not_public": hidden, "public_visits": public_rows,
                   "no_match_queries": no_match,
                   "no_match_note": sources.DACE_NO_MATCH if no_match else None,
                   "programme_ids": sorted({r["programme_id"] for r in public_rows if r["programme_id"]}),
                   "note": ("Public metadata only: answers are filtered before anything is stored, keeping public "
                            "visits' public fields and a bare count of visits not yet public (at least that many); "
                            "no proprietary data or PI details are stored. The Mission Archive is definitive: search "
                            "it by name and by coordinates and screenshot the result (proposal file #4).")}
    except sources.SourceError as exc:
        errors_net.append(f"archive (DACE): not checked ({exc})")

    # ---- SetuHQ's own evidence
    ev = evidence.stored_evidence(root, tic=tic, names=[target] + ([resolved.main_id] if resolved else []))
    hooks = evidence.stellar_hooks(target, tic=tic, root=root)
    toi_rows = []
    if tic and use_toi_table:
        try:
            toi_rows, got = sources.toi_ephemerides(fetcher, tic)
            provenance.append(_save(out_dir, "toi-table.json", got) | {"what": "NASA Exoplanet Archive TOI table rows"})
        except (sources.SourceError, ValueError) as exc:
            errors_net.append(f"TOI table: {exc}")

    # ---- ephemeris: user > published TOI (with errors) > SetuHQ's stored fit
    eph_in = None
    if t0 is not None and period is not None:
        eph_in = {"t0": t0, "t0_err": t0_err, "period": period, "period_err": period_err, "source": "user input"}
    else:
        stored = evidence.best_ephemeris(ev)
        tois = [r for r in toi_rows if r.get("pl_tranmid") and r.get("pl_orbper")]
        if stored and tois:  # the TOI whose period matches the stored candidate's
            tois.sort(key=lambda r: abs(r["pl_orbper"] - stored["period"]))
        if tois:
            r = tois[0]
            eph_in = {"t0": r["pl_tranmid"], "t0_err": r.get("pl_tranmiderr1"), "period": r["pl_orbper"],
                      "period_err": r.get("pl_orbpererr1"), "duration_hours": r.get("pl_trandurh"),
                      "depth_ppm": r.get("pl_trandep"),
                      "source": f"NASA Exoplanet Archive TOI table, TOI-{r['toi']} ({r.get('tfopwg_disp')}); "
                                "someone else's published measurement"}
        elif stored:
            eph_in = stored
    if t0_err is not None and eph_in:
        eph_in["t0_err"] = t0_err
    if period_err is not None and eph_in:
        eph_in["period_err"] = period_err
    eph = None
    if eph_in:
        eph = planning.ephemeris_in_window(t0=eph_in["t0"], t0_err=eph_in.get("t0_err"), period=eph_in["period"],
                                           period_err=eph_in.get("period_err"), start_jd=_jd(w_start),
                                           end_jd=_jd(w_end), source=eph_in["source"])

    # ---- planning estimates
    dep = depth_ppm if depth_ppm is not None else (eph_in or {}).get("depth_ppm")
    dur = duration_hours if duration_hours is not None else (eph_in or {}).get("duration_hours")
    plan = {"precision": planning.precision(g, efficiency), "sun_screen": planning.sun_screen(use_ra, use_dec),
            "ephemeris": eph, "orbits": None}
    if g is not None and dep and dur:
        plan["orbits"] = planning.orbits_needed(
            gmag=g, depth_ppm=float(dep), duration_hours=float(dur), target_snr=target_snr, event=event,
            efficiency=efficiency, ephemeris_sigma_hours=(eph or {}).get("sigma_hours_max") or 0.0 if event != "flare" else 0.0,
            n_sigma=n_sigma, flare_rate_per_day=flare_rate)
        plan["orbits"]["inputs_from"] = ("user" if depth_ppm is not None and duration_hours is not None
                                         else (eph_in or {}).get("source"))
        if plan["orbits"].get("orbits_total"):
            plan["orbits"]["rules_check"] = rules.check_orbits(plan["orbits"]["orbits_total"], prog)
            plan["orbits"]["visit_check"] = rules.check_visit(plan["orbits"].get("orbits_per_visit") or 1)
    else:
        plan["orbits_note"] = "Give --depth-ppm and --duration-hours (and a G magnitude) for an orbit estimate."

    # ---- the evidence summary sentences used in the draft (neutral wording)
    summary = []
    for run in ev["runs"]:
        for c in run["candidates"]:
            if c.get("passed") and c.get("period_days"):
                summary.append(f"A periodic transit-like candidate at P = {c['period_days']:.4f} d, depth "
                               f"{c['depth_ppm']:.0f} ppm, S/N {c['snr']:.1f} in public TESS data "
                               f"({run['run']}); a candidate, not a confirmation.")
                break
        for n in run["noise"]:
            if n.get("1h"):
                summary.append(f"TESS noise after detrending (CDPP-like): {n['1h']:.0f} / {n.get('3h') or 0:.0f} / "
                               f"{n.get('6h') or 0:.0f} ppm at 1 / 3 / 6 h (TESS band, for context).")
                break
    for c in ev["catalogue"][:1]:
        summary.append(f"A transit-like candidate at P = {c['period_days']:.4f} d, depth {c['depth_ppm']:.0f} ppm "
                       f"(S/N {c['snr']:.1f}) in public TESS data; it matches TOI {c.get('toi_match')} "
                       "(already known; a match, not a confirmation).")
    ev_out = ev | {"summary": summary, "hooks": hooks, "toi_table": toi_rows}

    ctx = {"programme": prog.key, "target": tinfo, "evidence": ev_out, "planning": plan, "cycle": cinfo,
           "status": {"rtl": rtl, "archive": archive}}
    files = {
        "scientific-justification.md": draft.scientific_justification(ctx),
        "technical-justification.md": draft.technical_justification(ctx),
        "checklist.md": draft.checklist(ctx),
    }
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    drafts = [out_dir / "scientific-justification.md", out_dir / "technical-justification.md"]
    lint = draft.lint_files(drafts, author_names=author_names, institutions=institutions)
    lint += draft.lint_filenames([out_dir] + sorted(out_dir.rglob("*")), author_names=author_names,
                                 institutions=institutions)
    (out_dir / "anonymity-lint.txt").write_text(draft.format_findings(lint) + "\n", encoding="utf-8")

    pack = {
        "kind": "setuhq CHEOPS proposal preparation pack",
        "disclaimer": draft.DISCLAIMER, "preparation_only": draft.PREP_ONLY,
        "setuhq_version": __version__, "created_at": now.isoformat(timespec="seconds"),
        "programme": {"key": prog.key, "label": prog.label, "orbits_requested": orbits, "check": orbit_check},
        "cycle": cinfo, "window": window, "target": tinfo, "status": {"rtl": rtl, "archive": archive},
        "evidence": ev_out, "planning": plan, "anonymity_lint": lint,
        "acknowledgement": {"required_when": "a publication uses CHEOPS data (ESA publication guidelines)",
                            "text": draft.ACKNOWLEDGEMENT, "programme_ids": archive.get("programme_ids", []),
                            "reference_papers": draft.REFERENCE_PAPERS, "guidelines": draft.PUBLICATION_GUIDELINES},
        "honesty": [draft.DISCLAIMER, draft.PREP_ONLY, evidence.CANDIDATE_LABEL, planning.ESTIMATE_LABEL, planning.CONFIRM],
        "network_errors": errors_net, "sources": provenance,
        "rules_sources": rules.RULE_SOURCES,
    }
    (out_dir / "README.md").write_text(readme(pack), encoding="utf-8")
    (out_dir / "pack.json").write_text(json.dumps(_plain(pack), indent=1, default=str), encoding="utf-8")
    return pack


def _plain(x):
    from setuhq.tools import _plain as plain

    return plain(x)


def _f(x, nd=1):
    return "n/a" if x is None else f"{x:.{nd}f}"


def readme(p: dict) -> str:
    c, t, st, pl = p["cycle"], p["target"], p["status"], p["planning"]
    rtl, arch = st["rtl"], st["archive"]
    lines = [
        f"# CHEOPS proposal preparation pack: {t['name']}",
        "",
        f"> **{p['disclaimer']}**",
        ">",
        f"> {p['preparation_only']}",
        "",
        f"Made by SetuHQ {p['setuhq_version']} on {p['created_at']}. The machine-readable record is `pack.json`; "
        "every public response it read is in `sources/` with its URL, fetch time and SHA-256.",
        "",
        "## Rules check",
        "",
        f"- Programme: {p['programme']['label']}; orbits requested: {p['programme']['orbits_requested'] or 'not given'} "
        f"(limit {p['programme']['check']['limit'][0]}-{p['programme']['check']['limit'][1]}).",
        f"- Cycle {c['cycle']}: deadline {c['deadline_local']} ({c['deadline_zone']}), {c['deadline_utc']} UTC; "
        f"{_f(c['time_left_days'])} days left.",
        f"- TAC: {c['tac']}; outcome expected {c['outcome_expected']}; Phase 2 {c['phase2']}.",
        f"- Earliest start {c['earliest_start']}: {c['earliest_start_note']}; about three months after the close: "
        f"{c['about_three_months_after_close']}; nominal start month {c['nominal_start_month']}.",
        f"- {c['observable_by_note']}",
        f"- Window {p['window']['start']} to {p['window']['end']} (Running Call observing period "
        f"{rules.CALL_START} to {rules.CALL_END}: the end of EM1 to {rules.EM2_FROM - timedelta(days=1)}, then EM2).",
    ]
    for kind in ("errors", "warnings"):
        for msg in c[kind] + p["programme"]["check"][kind] + p["window"][kind]:
            lines.append(f"- **{kind[:-1].upper()}**: {msg}")
    for h in p["programme"]["check"]["hints"]:
        lines.append(f"- Note: {h}")
    lines += ["", "## Target status", "",
              f"- Coordinates: RA {_f(t['ra'], 6)}, Dec {_f(t['dec'], 5)} (ICRS, J2000) from {t['coord_source']}."
              + (f" SIMBAD main identifier: {t['main_id']}." if t.get("main_id") else ""),
              *[f"- **WARNING**: {w}" for w in t["coord_warnings"]],
              f"- Gaia G: {_f(t['gmag'], 2)} ({t.get('gmag_source') or 'not known'})."]
    if not rtl.get("checked"):
        lines.append("- RTL: **not checked** (the RTL CSV could not be read). Use the Target Checker.")
    elif rtl["reserved"]:
        for m in rtl["matches"]:
            lines.append(f"- RTL: **RESERVED**: matches {m['rtl_name']} on {m['list']} by {', '.join(m['matched_by'])}.")
    else:
        lines.append("- RTL: not on " + ", ".join(f"{x['file']} ({x['title']})" for x in rtl["lists"])
                     + f"; matched by name, SIMBAD aliases and position within {rtl['radius_arcsec']:g}\".")
    for m in rtl.get("nearby", []):
        lines.append(f"- RTL: an entry ({m['rtl_name']}) lies {m['separation_arcsec']}\" away: check the line of sight.")
    if not arch.get("checked"):
        lines.append("- Archive: **not checked**. Search the Mission Archive by name and coordinates.")
    elif arch["already_observed"]:
        ids = ", ".join(str(v["visit_id"]) for v in arch["public_visits"][:20])
        lines.append(f"- Archive: **already observed**: {arch['n_public']} public visit(s)"
                     + (f" (visit ids {ids}{', ...' if arch['n_public'] > 20 else ''})" if ids else "")
                     + (f" and at least {arch['n_not_public']} not yet public" if arch["n_not_public"] else "")
                     + ". Contact CHEOPS support and justify new data (P&P section 4.10).")
    else:
        lines.append(f"- Archive: {arch.get('no_match_note') or 'no visits in public metadata'}; DACE was searched by "
                     "position and by name. Still check the Mission Archive.")
    ss = pl.get("sun_screen") or {}
    if ss.get("checked"):
        lines.append(f"- Sky: ecliptic latitude {_f(ss['ecliptic_latitude_deg'])} deg. {ss['statement']}")
    ev = p["evidence"]
    lines += ["", "## Evidence from SetuHQ", "", f"> {ev['label']}", ""]
    lines += [f"- {s}" for s in ev["summary"]] or ["- No stored SetuHQ output for this target."]
    for key, h in ev["hooks"].items():
        lines.append(f"- {key}: {h['status']}")
    prec = pl["precision"]
    lines += ["", "## Planning estimates", "", f"> {planning.ESTIMATE_LABEL}", ">", f"> {planning.CONFIRM}", ""]
    if prec.get("available"):
        for case, v in prec["cases"].items():
            lines.append(f"- Precision ({case}): {_f(v['ppm_1h'])} ppm/1 h, {_f(v['ppm_3h'])} ppm/3 h, "
                         f"{_f(v['ppm_6h'])} ppm/6 h, {_f(v['ppm_per_orbit'])} ppm per orbit at efficiency "
                         f"{prec['efficiency_assumed']}.")
        if prec.get("warning"):
            lines.append(f"- **WARNING**: {prec['warning']}")
        lines.append(f"- Model: {prec['reference']}. {prec['efficiency_note']}")
    else:
        lines.append(f"- {prec['note']}")
    e = pl.get("ephemeris")
    if e:
        lines.append(f"- Ephemeris ({e['source']}): sigma {_f(e['window_start']['sigma_hours'], 2)} h at the window "
                     f"start, {_f(e['window_end']['sigma_hours'], 2)} h at its end; {e['transits_in_window']} transits "
                     "in the window." + (f" **{e['warning']}**" if e.get("warning") else ""))
    o = pl.get("orbits")
    if o:
        if o["event"] == "flare":
            lines.append(f"- Flare: S/N {_f(o['snr_per_event'])} per flare"
                         + (f"; {o['orbits_total']} orbits to expect {o['n_flares_expected']} flare(s)." if o.get("orbits_total") else "."))
        else:
            lines.append(f"- {o['event'].capitalize()}: depth {_f(o['depth_ppm'], 0)} ppm, {_f(o['duration_hours'], 2)} h "
                         f"(from {o.get('inputs_from')}); S/N {_f(o['snr_per_event'])} per event; S/N {o['target_snr']:g} "
                         f"needs {o['events_needed']} event(s) x {o['orbits_per_visit']} orbits = **{o['orbits_total']} orbits** "
                         "(conservative case)"
                         + (", raised to ESA's recommended minimum of 5 orbits per visit." if o.get("visit_minimum_applied") else "."))
            for msg in (o.get("rules_check") or {}).get("errors", []) + (o.get("visit_check") or []):
                lines.append(f"- Note: {msg}")
    else:
        lines.append(f"- {pl.get('orbits_note', '')}")
    n_warn = sum(f["level"] == "warn" for f in p["anonymity_lint"])
    lines += ["", "## Drafts and checklist", "",
              "- `scientific-justification.md` and `technical-justification.md`: anonymised drafts with generic "
              "headings. Move them into ESA's templates (linked in the checklist); do not submit these files.",
              f"- `anonymity-lint.txt`: {n_warn} warning(s). The lint is an aid and cannot guarantee anonymity; run "
              "`setuhq propose lint FILE...` on your edited text and read everything yourself.",
              "- `sources/` holds copies of the public files read, for your own record. Do not redistribute "
              "`sources/RTL_*.csv`: it is ESA's file; link to the call page instead.",
              "- `checklist.md`: ESA's seven steps in order, with links.",
              "- The Team Expertise & Management Plan (the one non-anonymous file) is not drafted here.",
              "", "## If you publish CHEOPS data", "",
              f"ESA's publication guidelines ({p['acknowledgement']['guidelines']}) ask for the programme IDs, a table "
              "of file keys, the acknowledgement below, and the reference papers.", "",
              f"> {p['acknowledgement']['text']}", ""]
    if p["acknowledgement"]["programme_ids"]:
        lines.append("Programme IDs of the public visits found: " + ", ".join(p["acknowledgement"]["programme_ids"]) + ".")
        lines.append("")
    lines += [f"- {r}" for r in p["acknowledgement"]["reference_papers"]]
    if p["network_errors"]:
        lines += ["", "## Not checked", ""] + [f"- {m}" for m in p["network_errors"]]
    lines += ["", "Support: cheops-support@cosmos.esa.int. SetuHQ is maintained by Ashforde OÜ.", ""]
    return "\n".join(lines)

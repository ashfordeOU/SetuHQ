# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The anonymised draft, its anonymity lint, and the step-by-step checklist.

The draft uses generic section headings that follow the structure the Policies and Procedures (P&P) document
asks for (sections 5.2.2 and 5.2.3.1). It does not reproduce ESA's Word templates or their text: the proposer
downloads those from ESA (linked) and moves the content across. Nothing in the draft names a person, an
institution or a team, and the file names are generic.

The anonymity lint lives in :mod:`setuhq.propose.lint` (re-exported here). It warns and never edits, and it is an
aid: it cannot guarantee anonymity.
"""

from __future__ import annotations


DISCLAIMER = ("SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the "
              "CHEOPS mission or the CHEOPS Consortium. It does not replace ESA's Target Checker, Visibility Tool, "
              "Exposure Time Calculator, Scheduling Feasibility Checker or the Policies & Procedures document; the "
              "official call and tools govern.")
PREP_ONLY = ("This is a proposal preparation pack: a drafting aid. It does not submit anything, it does not log in "
             "to any ESA system, and it makes no claim of ESA approval, feasibility or visibility.")
ACKNOWLEDGEMENT = ("CHEOPS is an ESA mission in partnership with Switzerland with important contributions to the "
                   "payload and the ground segment from Austria, Belgium, France, Germany, Hungary, Italy, Portugal, "
                   "Spain, Sweden, and the United Kingdom. The CHEOPS Consortium would like to gratefully acknowledge "
                   "the support received by all the agencies, offices, universities, and industries involved. Their "
                   "flexibility and willingness to explore new approaches were essential to the success of this "
                   "mission. CHEOPS data analysed in this article will be made available in the CHEOPS mission "
                   "archive (https://cheops.unige.ch/archive_browser/).")
PUBLICATION_GUIDELINES = "https://www.cosmos.esa.int/web/cheops-guest-observers-programme/publication-guidelines"
REFERENCE_PAPERS = [
    "Benz, W., et al. 2021, Experimental Astronomy 51, 109 (the mission and instrument), doi:10.1007/s10686-020-09679-4",
    "Hoyer, S., et al. 2020, A&A 635, A24 (the data reduction pipeline), doi:10.1051/0004-6361/201936325",
    "Fortier, A., et al. 2024, A&A 687, A302 (in-flight science performance), doi:10.1051/0004-6361/202348576",
]

GO = "https://www.cosmos.esa.int/web/cheops-guest-observers-programme"
LINKS = {
    "call": f"{GO}/cheops-running-call",
    "registration": f"{GO}/registration",
    "datalabs_registration": "https://www.cosmos.esa.int/web/datalabs/self-registration",
    "coordinates": f"{GO}/coordinates",
    "target_checker": "https://cheops.unige.ch/pht2/search-reserved-targets/",
    "simbad": "https://simbad.cds.unistra.fr/simbad/",
    "mast": "https://mast.stsci.edu/",
    "visibility": f"{GO}/visibility-checks",
    "sky_maps": "https://www.cosmos.esa.int/web/cheops/the-cheops-sky",
    "datalabs": "https://datalabs.esa.int",
    "target_status": f"{GO}/target-status-checks",
    "archive": "https://cheops.unige.ch/archive_browser",
    "archive_mirror": "https://cheops-archive.ssdc.asi.it/",
    "dace": "https://dace.unige.ch/",
    "etc_page": f"{GO}/exposure-time-calculation",
    "etc": "https://cheops.unige.ch/pht2/exposure-time-calculator/",
    "templates": f"{GO}/proposal-templates",
    "pht1": f"{GO}/pht1",
    "faq": f"{GO}/faq-ao",
    "support": "mailto:cheops-support@cosmos.esa.int",
}

from setuhq.propose.lint import TODO  # noqa: E402

# ---------------------------------------------------------------- the anonymity lint (setuhq.propose.lint)

from setuhq.propose.lint import (  # noqa: E402,F401 (re-exported: the pack, the CLI and the tests use them here)
    NOT_A_GUARANTEE, LintInputError, format_findings, lint_filenames, lint_files, lint_text)


# ---------------------------------------------------------------- the drafts


def _fmt(x, nd=1, unit=""):
    return "n/a" if x is None else f"{x:.{nd}f}{unit}"


def scientific_justification(ctx: dict) -> str:
    """A Markdown draft with generic headings in the order the P&P (section 5.2.2) asks for this programme type."""
    prog = ctx["programme"]
    t = ctx["target"]
    ev = ctx["evidence"]
    head = [
        "# Scientific Justification: draft",
        "",
        f"> {PREP_ONLY} Move this content into ESA's own template ({LINKS['templates']}) and follow the page limits "
        "and format in the Policies and Procedures (P&P), section 5.2.2. This document must stay strictly anonymous.",
        "",
    ]
    evidence_lines = []
    if ev.get("summary"):
        evidence_lines = [f"- {s}" for s in ev["summary"]]
    body = []
    if prog == "fasttrack":
        body += ["## Title", "", f"{TODO} (must match the PHT1 entry exactly)", "",
                 "## Coordination with an awarded HST or JWST programme", "",
                 f"{TODO} Evidence of the awarded HST or JWST programme executing during EM2. Do not name people "
                 "here; give the programme identifier only as the P&P asks.", "",
                 "## Data reduction and analysis plan", "", f"{TODO}", ""]
        return "\n".join(head + body)
    body += ["## Title", "", f"{TODO} (must match the PHT1 entry exactly)", "",
             "## Science goals", "",
             f"{TODO} The questions the observations address, and how CHEOPS data on {t['name']} advance them.", ""]
    if evidence_lines:
        body += ["Supporting evidence prepared with public software (candidates only, not confirmations):", ""]
        body += evidence_lines + [""]
    body += ["## Why CHEOPS", "",
             f"{TODO} Which CHEOPS capability the goals need (precision on a bright star, cadence, scheduling of "
             "specific events) and why other facilities do not suffice.", ""]
    if prog == "large":
        body += ["## Why a large programme, and its legacy", "",
                 f"{TODO} Why the programme needs the large format, the legacy it leaves, and any high-level "
                 "science products to be released.", ""]
    body += ["## Figures and tables", "", f"{TODO} (separate allowance; see the P&P for the limit)", "",
             "## Data reduction and analysis plan", "",
             f"{TODO} Pipeline products used (DRP or PIPE light curves), detrending, the joint fit with existing "
             "data, and how the result answers the science goals.", ""]
    return "\n".join(head + body)


def technical_justification(ctx: dict) -> str:
    """A Markdown draft with generic headings in the order the P&P (section 5.2.3.1) asks for."""
    t = ctx["target"]
    plan = ctx["planning"]
    est = plan.get("orbits") or {}
    prec = plan.get("precision") or {}
    lines = [
        "# Technical Justification and Implementation: draft",
        "",
        f"> {PREP_ONLY} Move this content into ESA's own template ({LINKS['templates']}); see the P&P, section "
        "5.2.3.1, for the required items and the page limit. This document must stay strictly anonymous.",
        "",
        "## Title", "", f"{TODO} (must match the PHT1 entry exactly)", "",
        "## Observing strategy", "",
        f"{TODO} Overall strategy and target selection. Time-critical or not; if not, how the visits can be split "
        "to fill scheduling gaps (P&P section 4.7).", "",
        "## Target details", "",
        "| Name | RA (J2000, ICRS, deg) | Dec (J2000, ICRS, deg) | Gmag | Spectral type | Orbits per visit | Visits |",
        "|---|---|---|---|---|---|---|",
        f"| {t['name']} | {_fmt(t.get('ra'), 6)} | {_fmt(t.get('dec'), 5)} | {_fmt(t.get('gmag'), 2)} | "
        f"{t.get('sptype') or TODO} | {est.get('orbits_per_visit', TODO)} | {est.get('events_needed', TODO)} |",
        "",
        f"Coordinates: {t.get('coord_source')}. Re-check them with the Target Checker before submission "
        f"({LINKS['target_checker']}).",
        "",
        "## Time request", "",
    ]
    if est.get("orbits_total"):
        c = (prec.get("cases") or {}).get("conservative", {})
        lines += [
            f"Draft numbers ({est.get('label', '')}):",
            "",
            f"- Expected precision: {_fmt(c.get('ppm_per_orbit'))} ppm per orbit at G = {_fmt(t.get('gmag'), 2)} "
            f"(conservative case, efficiency {est.get('efficiency_assumed')}), from published in-flight performance "
            "(Fortier et al. 2024).",
            f"- One event of depth {_fmt(est.get('depth_ppm'), 0)} ppm and duration {_fmt(est.get('duration_hours'), 2)} h "
            f"gives S/N {_fmt(est.get('snr_per_event'))}; S/N {_fmt(est.get('target_snr'), 0)} needs "
            f"{est.get('events_needed')} event(s) of {est.get('orbits_per_visit')} orbit(s) each: "
            f"{est.get('orbits_total')} orbits.",
            f"- {TODO} Replace these with the Exposure Time Calculator's numbers (its PDF is proposal file #5).",
            "",
        ]
    else:
        lines += [f"{TODO} Total orbits and visits with the full calculation, referring to the ETC results.", ""]
    eph = plan.get("ephemeris")
    lines += ["## Special requirements and constraints", ""]
    if eph and eph.get("sigma_hours_max") is not None:
        lines += [f"- Ephemeris uncertainty in the requested window: up to {_fmt(eph['sigma_hours_max'], 2)} h "
                  f"(1 sigma), from {eph['source']}; visits are padded by "
                  f"{_fmt(est.get('n_sigma'), 0)} sigma on each side.", ""]
    lines += [f"{TODO} Observing efficiency, start/stop criticality, coordination with other facilities.", "",
              "## Visibility checks", "",
              f"{TODO} Results of ESA's Visibility Tool or Scheduling Feasibility Checker (ESA Datalabs): dates "
              "or intervals when the target is observable with the required efficiency. SetuHQ does not determine "
              f"visibility ({LINKS['visibility']}).", "",
              "## Use of AI software", "",
              f"{TODO} The P&P (section 4.13) asks that any AI software used to prepare the proposal is acknowledged "
              "here with its exact version and purpose. If SetuHQ's Sentinels (AI models) contributed to the "
              "evidence, name the provider and model recorded in the run manifest.", ""]
    return "\n".join(lines)


def checklist(ctx: dict) -> str:
    """The seven steps of the call page, in order, with links and this pack's findings for each."""
    t = ctx["target"]
    st = ctx["status"]
    rtl = st.get("rtl") or {}
    arch = st.get("archive") or {}
    rtl_line = ("NOT CHECKED (RTL could not be read): use the Target Checker." if not rtl.get("checked") else
                ("RESERVED on " + ", ".join(sorted({m['list'] for m in rtl['matches']})) + ": a GO proposal for this "
                 "target is not possible while it is reserved.") if rtl.get("reserved") else
                "Not on the public RTL CSV(s) read for this pack. Confirm with the Target Checker by coordinates.")
    arch_line = ("NOT CHECKED: search the Mission Archive by name and by coordinates." if not arch.get("checked") else
                 f"ALREADY OBSERVED: {arch['n_public']} public visit(s) found"
                 + (f", plus at least {arch['n_not_public']} not yet public" if arch.get("n_not_public") else "")
                 + "; justify new observations and contact CHEOPS support (P&P section 4.10)."
                 if arch.get("already_observed") else
                 f"{arch.get('no_match_note') or 'No visits in public archive metadata'} (DACE).")
    steps = [
        ("Registration (Cosmos account and ESA Datalabs)", [LINKS["registration"], LINKS["datalabs_registration"]],
         "Register well before the deadline: registration and ESA Datalabs access may take several days (the "
         "call page warns that waiting until the deadline may prevent submission)."),
        ("Coordinates (ICRS, epoch J2000)", [LINKS["coordinates"], LINKS["target_checker"], LINKS["simbad"], LINKS["mast"]],
         f"Pack position: RA {_fmt(t.get('ra'), 6)}, Dec {_fmt(t.get('dec'), 5)} from {t.get('coord_source')}. "
         "Never paste ExoFOP or Gaia positions (epoch J2015.5)." + "".join(f" WARNING: {w}" for w in t.get("coord_warnings", []))),
        ("Visibility checks", [LINKS["visibility"], LINKS["sky_maps"], LINKS["datalabs"]],
         "Use the Visibility Tool or the SFC; the result goes into the Technical Justification. "
         + ((ctx["planning"].get("sun_screen") or {}).get("statement") or "")),
        ("Target status checks", [LINKS["target_status"], LINKS["target_checker"], LINKS["archive"], LINKS["archive_mirror"]],
         f"RTL: {rtl_line} Archive: {arch_line} Screenshots of both tools, by name and by coordinates, make "
         "proposal file #4."),
        ("Exposure time calculation", [LINKS["etc_page"], LINKS["etc"]],
         "Run the ETC for the target and export its PDF (proposal file #5); compare with the pack's estimates."),
        ("Proposal templates", [LINKS["templates"]],
         "Download ESA's templates and move the drafts across; the Team Expertise & Management Plan (file #1) "
         "is the only non-anonymous document and is not drafted here."),
        ("Phase 1 submission (PHT1)", [LINKS["pht1"]],
         f"Submit yourself before {ctx['cycle'].get('deadline_local', TODO)} "
         f"({ctx['cycle'].get('deadline_zone', '')}). Proposals cannot be edited after submission."),
    ]
    out = ["# Proposal preparation checklist", "", f"> {DISCLAIMER}", "",
           "The order follows the seven steps on ESA's Running Call page.", ""]
    for i, (title, links, note) in enumerate(steps, 1):
        out += [f"## {i}. {title}", "", "- [ ] " + note, ""] + [f"  - <{u}>" for u in links] + [""]
    out += ["Questions: cheops-support@cosmos.esa.int (allow several days for an answer).", ""]
    return "\n".join(out)

# Preparing a CHEOPS Guest Observers proposal

> **SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS
> mission or the CHEOPS Consortium. It does not replace ESA's Target Checker, Visibility Tool, Exposure Time
> Calculator, Scheduling Feasibility Checker or the Policies & Procedures document; the official call and tools
> govern.**

`setuhq propose cheops` writes a **proposal preparation pack** for the CHEOPS Guest Observers (GO)
Running Call: one new directory with what a proposer needs to get through ESA's seven steps. It is a
drafting aid only. It does not log in anywhere, does not submit anything, does not touch ESA's
Proposal Handling Tools (PHT1/PHT2), and makes no claim of ESA approval, feasibility or visibility.
You run ESA's tools yourself and submit through PHT1 yourself.

```bash
setuhq propose cheops "TOI-1987" --orbits 30
setuhq propose cheops "TOI-1987" --programme large --orbits 200 --cycle 2027-04
setuhq propose cheops "HD 189733" --event eclipse --depth-ppm 40 --duration-hours 1.8 --snr 5
setuhq propose lint my-edited-justification.md --author-name "Your Name"
```

The pack goes to `runs/propose/cheops-<target>-<cycle>/` (or `--out`), and an existing directory is
never overwritten. The same pack is available to AI assistants as the MCP tool `cheops_proposal_pack`
(see [MCP-INSTALL.md](MCP-INSTALL.md)). That tool writes only into a new `runs/propose/<run_name>` and
keeps no cache.

## What is in a pack

| File | Contents |
|---|---|
| `README.md` | The summary: rules check, target status, evidence, estimates, the disclaimer, and what to do next |
| `checklist.md` | ESA's seven steps in order, with links: Cosmos account, coordinates, visibility, target status, ETC, templates, PHT1 |
| `scientific-justification.md` | An anonymised draft with generic headings in the order the Policies and Procedures (P&P, section 5.2.2) asks for |
| `technical-justification.md` | The same for the Technical Justification and Implementation (P&P section 5.2.3.1), with target details and the draft time request |
| `anonymity-lint.txt` | The anonymity lint's findings on the drafts and on every file name |
| `pack.json` | Everything, machine-readable, with the URL, fetch time and SHA-256 of each source |
| `sources/` | The public responses read: the RTL CSV(s), SIMBAD, the archive metadata and the TOI table |

The drafts don't reproduce ESA's Word templates. Download those from the
[Proposal Templates page](https://www.cosmos.esa.int/web/cheops-guest-observers-programme/proposal-templates)
and move the text across. The Team Expertise & Management Plan is the only non-anonymous file, so the pack
doesn't draft it.

## The rules it checks

The pack restates the rules from the
[Running Call page](https://www.cosmos.esa.int/web/cheops-guest-observers-programme/cheops-running-call)
(last updated 15 October 2026) and its Policies and Procedures, CHEOPS-EST-SCI-TN-018 v1.0 (8 July 2026).
Both were read on 21 October 2026. If they disagree with the pack, they win.

- **Observing period:** 1 October 2026 to 31 December 2029. That covers the end of the first extended mission
  (EM1, to 31 December 2026) and the second (EM2, from 1 January 2027).
- **Monthly cycles:** the deadline is 23:59 CET/CEST on the last calendar day of the month, computed in
  Europe/Paris time. Daylight saving is handled, so the October deadline is CET and the March and April
  deadlines are CEST. A submission in the deadline minute is treated as late.
- **Timeline:** the TAC evaluates in the first weeks of month M+1 and outcomes come in the last week of M+1.
  Phase 2 is M+2. The earliest start is M+3 and the nominal start is M+4. The call page puts it as "ideally"
  about three months after the close.
- **Regular programmes:** up to 120 orbits, any month.
- **Large programmes:** 121 to 500 orbits, April and October cycles only, 2026 to 2029.
- **HST/JWST coordinated fast-track programmes:** up to 25 orbits (50 only in exceptional, justified cases),
  any month, no TAC.
- **Visits:** at least 1 orbit, 5 or more recommended for high precision, and at most 100.
- **First observable date:** at least one target should become observable within 6 months of the deadline.
- **Batch limits:** cycles from July to September 2026 could only ask for observations in 2026. The last
  ordinary batch is expected in September 2029.

## Target status

- **Coordinates** come from SIMBAD (ICRS, J2000), or from MAST's name lookup when SIMBAD doesn't know the
  name, and the pack says which. A position you give with `--coord-source exofop` or `gaia` is refused and
  replaced: those catalogues give epoch J2015.5. A position offset from SIMBAD's by about 15.5 years of proper
  motion is flagged.
- **Reserved Target List.** The RTL CSV files linked from the call page are downloaded at run time and cached
  under `cache/cheops-propose/` with the fetch date. The cache is ignored by git, and the RTL is not committed
  to this repository. A pack keeps a copy in `sources/` for your own record; don't redistribute it. The target is matched three ways:
  - by name, tolerant of spaces, dashes and spelling variants;
  - by every SIMBAD alias;
  - by position within 20″. Entries within 2′ are listed for a manual line-of-sight check.
- **Prior observations** come from the public metadata in [DACE](https://dace.unige.ch/), the public query
  interface of the CHEOPS Mission Archive, by position (30″) and by name. Each answer is filtered in memory
  before anything is stored: the pack and the cache keep only public visits' public fields (ids, file keys,
  programme IDs, dates) and a bare count of visits not yet public. No proprietary data, and no PI name or id,
  is ever written to disk. DACE answers an empty search with HTTP 404, so the pack reports "no match found
  (DACE does not distinguish an empty result from a missing endpoint)". For every other source, a 404 means
  "not checked".
- **Sun constraint.** One geometric screen is applied. ESA's Sky Visibility page gives a 117° Sun-exclusion
  hard constraint, so a target more than 63° from the ecliptic can never meet it, and the pack says so.
  Passing this screen is **not** a visibility result.

ESA's Target Checker and Mission Archive remain the definitive sources. Their screenshots, by name and by
coordinates, make up proposal file #4.

## Evidence from SetuHQ

SetuHQ's results are **candidates, never confirmations**. Where SetuHQ has stored outputs for the target, the
pack includes:

- the candidates, from runs under `runs/` and from the discovery catalogue;
- the transit fit's ephemeris;
- a CDPP-like noise level at 1, 3 and 6 hours from the stored TESS light curve (in-dip points masked, TESS
  band, given for context).

**Optional stellar hooks.** If `setuhq.flares`, `setuhq.pulsations` or `setuhq.cheops` is installed and
defines `proposal_evidence(target, *, tic, root) -> dict`, its answer is included. If the module or hook is
missing, or the hook fails, the pack records that and carries on.

## Planning estimates

These are **estimates for drafting only.** Confirm them with ESA's
[Exposure Time Calculator](https://cheops.unige.ch/pht2/exposure-time-calculator/), the Visibility Tool and the
Scheduling Feasibility Checker (both on [ESA Datalabs](https://www.cosmos.esa.int/web/cheops-guest-observers-programme/visibility-checks)).

- **Precision per orbit** is a function of Gaia G. It interpolates published in-flight performance from
  Fortier et al. 2024, A&A 687, A302 ([arXiv:2406.01716](https://arxiv.org/abs/2406.01716)):
  - 12.8 ppm in 6 h at G = 8.97;
  - at G = 12, either 128 ppm in 3 h (conservative: the paper's section 4.4 figure including hot pixels; the
    measured DRP light curves of a G = 11.98 star reached 116.5 and 102.8 ppm in 3 h in 2021 and 2023) or
    85 ppm in 3 h (optimistic: Science Requirement 1.2, met in other years and by PIPE light curves).

  The noise is assumed white. A CHEOPS orbit is 98.7 minutes. The observing efficiency is a placeholder
  (`--efficiency`, default 0.7); take yours from the Visibility Tool. Outside 8.5 ≤ G ≤ 12.5 the pack warns
  that the model is extrapolating.
- **Orbits for a target S/N** on a transit, eclipse or flare. For transits and eclipses, each visit covers the
  event, a baseline, and the ephemeris uncertainty padded at 3σ on each side, with at least 5 orbits per visit.
  For flares, give `--flare-rate` (flares per day) to turn S/N into orbits.
- **Ephemeris uncertainty** is propagated to the start and end of the requested window, using
  σ(Tₙ)² = σ_T0² + n²σ_P². The inputs are taken in this order:
  1. your own (`--t0`, `--period` and their errors);
  2. the published TOI table at the NASA Exoplanet Archive (someone else's measurement);
  3. SetuHQ's stored candidate fit.

## The anonymity lint

**The lint is an aid. It cannot guarantee anonymity:** a clean result does not prove a text is anonymous, so
read every document and file name yourself before submitting. The P&P requires double-anonymous proposals,
including file names. The lint warns about:

- e-mail addresses, including obfuscated ones ("jane.doe [at] unige.ch"), and ORCID iDs;
- names you give with `--author-name`, in their usual variants: "Jane Doe", "J. Doe", "Doe, J.", "Jane Doe's",
  and the surname alone in a citation ("Doe et al.", "Doe (2023)"). A third-person self-citation is what the
  P&P recommends, so treat that warning as a prompt to check the sentence around it, not as an error;
- institutions, case-insensitively: generic words ("university of ...", "institute", "observatory"), a short
  built-in list of major institutions ("ETH Zurich", "Harvard", "UniGE" and others), and any you give with
  `--institution`. Links to the public tools a proposal must cite, such as the Target Checker at
  cheops.unige.ch, are not counted;
- self-reference: "my previous paper", "our earlier CHEOPS programme", "our 2023 study", "our work (Doe et al.
  2023)", "our team", "we have previously shown", "we are the team that discovered";
- titles before names, funding acknowledgements and links to personal pages;
- file names that contain an e-mail address, an ORCID iD, an institution, a given name (`Doe_SJ.md`,
  `jdoe.md`) or initials.

Text is scanned paragraph by paragraph, so a phrase wrapped over two lines is still caught. A PDF is read with
[pypdf](https://pypi.org/project/pypdf/) when it is installed (`pip install pypdf`, or the `propose` extra).
Without pypdf, or when a PDF has no extractable text, `setuhq propose lint` refuses it with exit code 2 rather
than reporting it clean, and the same goes for any other non-text file. Exit code 1 means warnings were found.

The lint also notes where a draft names public software such as SetuHQ. Citing it is fine, but if you develop
it, cite it neutrally. The lint only warns; it never edits. The P&P (section 4.13) also asks you to acknowledge
any AI software used, with its version and purpose, in the Technical Justification. SetuHQ's Sentinels are AI
models.

## Being a good citizen of ESA's services

- **Reads only:** each pack reads public pages and services only, never in bulk. That means the call page, the
  RTL CSV files it links, one SIMBAD query (MAST only as a fallback), at most two archive metadata queries and
  one TOI table query.
- **Rate limits:** requests to one host are at least a second apart and retried at most twice; a 429 answer's
  Retry-After is honoured (up to two minutes).
- **Identified:** requests carry a `SetuHQ-proposal-prep` User-Agent.
- **Cached:** the command line reuses answers for the same day. `--offline` makes no request at all; the
  checks then say "not checked".
- **Nothing automated:** there is no login, no form submission and no PHT interaction.

## If you publish CHEOPS data

ESA's [publication guidelines](https://www.cosmos.esa.int/web/cheops-guest-observers-programme/publication-guidelines)
ask for the programme IDs, a table of file keys, the CHEOPS acknowledgement and the reference papers:
Benz et al. 2021 (mission), Hoyer et al. 2020 (pipeline) and Fortier et al. 2024 (performance). Every pack
carries the acknowledgement text, the reference papers, and the programme IDs of any public visits it found.

Questions about the call go to ESA: cheops-support@cosmos.esa.int. Questions about this helper go to
SetuHQ's issue tracker.

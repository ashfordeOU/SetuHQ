---
title: 'SetuHQ: an open, auditable transit search of TESS light curves with a calibrated panel of AI and matched-filter reviewers'
tags:
  - Python
  - astronomy
  - exoplanets
  - transit search
  - TESS
  - benchmark
  - large language models
  - Model Context Protocol
authors:
  - name: Chakshu Baweja
    orcid: 0009-0008-2098-0751
    affiliation: 1
affiliations:
  - index: 1
    name: Ashforde OÜ, Estonia
date: 21 October 2026
bibliography: paper.bib
---

<!--
SPDX-License-Identifier: CC-BY-4.0
The JOSS software paper. It describes the software and its design; it deliberately quotes no benchmark
result, because those are regenerated from the committed results (docs/results/, docs/paper/numbers.json)
and the methods paper (docs/paper/paper.md) carries them with their intervals. Compile with
.github/workflows/joss-draft.yml. Before submitting: the archived release's DOI goes into paper.bib
(the `setuhq` entry) and the repository must be public with an open-source licence (it is).
-->

# Summary

SetuHQ is a Python package for searching public light curves from NASA's Transiting Exoplanet Survey
Satellite [TESS, @ricker2015] for planetary transits, and for showing exactly how each candidate was found.
It copies the Planet Hunters task [@fischer2012; @eisner2021]: mark the start and end of every dip in a
blind-coded segment of a light curve, then label the segment a potential planet or noise. The volunteers are
replaced by a *reviewer panel* of two kinds. *Probes* are deterministic, seeded matched-filter detectors (a
single-event search and box least squares, BLS, @kovacs2002) with stated thresholds, miss probabilities and
boundary jitter. *Sentinels* are vision-capable language models (Claude by default; OpenAI, Gemini and any
OpenAI-compatible endpoint are supported and labelled) that read the same rendered plot and the same task text
and return strict, validated JSON with their marks and a sentence of reasoning.

Marks are clustered and scored by skill-weighted consensus, with each reviewer's weight measured on injected
transits. Every consensus dip is then vetted from the light curve alone (signal-to-noise, duration, edge,
odd/even and secondary-eclipse tests in the spirit of the Kepler and TESS Data Validation reports,
@twicken2018), fitted with a quadratic limb-darkened transit model [@mandel2002] using @claret2017
coefficients for the star's catalogue parameters [@stassun2019], and given a block-bootstrap false-alarm
probability that is never quoted below the resolution of its trials. Every output is labelled a
*candidate*; SetuHQ never calls anything it finds a confirmed or validated planet.

Each run records the SHA-256 of every light curve it read, the hash of its configuration, a fingerprint of
the code that produced it, and every reviewer's marks, labels and reasons, so a stored run can be re-vetted
with new code without asking the reviewers again, and anyone can check which code made a number.

# Statement of need

Two things are scarce in transit vetting. The first is an *auditable* path from a light curve to a
candidate that a non-specialist can follow: which reviewer marked which dip, with what weight, which tests
it passed, and which code and data produced it. The second is a *fair test* for new kinds of reviewers.
Language models that read plots and explain themselves are being tried on astronomical images
[@stoppa2025], but we found no open benchmark that measures such reviewers on TESS transit vetting with
false-alarm controls and a held-out split, beside deterministic detectors whose behaviour is known exactly.

SetuHQ provides both. For citizen-science teams, educators and researchers it is a transparent pipeline
whose every verdict can be inspected in a browser. For anyone building a vetter (a model, a pipeline or a
person) it provides a frozen, blind benchmark of real TESS Objects of Interest [@guerrero2021], a public
leaderboard that scores submissions itself, and a catalogue-metadata baseline that a method reading the
light curve should beat. Its results, including the negative ones, are printed first: the methods paper in
the repository (`docs/paper/paper.md`) reports them with their confidence intervals.

# State of the field

Kepler's Robovetter set the standard for measured completeness and reliability, using injected transits and
inverted and scrambled light curves [@coughlin2016; @thompson2018]. Machine-learned vetters such as AstroNet
[@shallue2018], its TESS triage variant [@yu2019] and ExoMiner [@valizadegan2022] rank threshold-crossing
events learned from labelled examples. Statistical validation tools such as vespa [@morton2016] and
TRICERATOPS [@giacalone2021] estimate false-positive probabilities. Planet Hunters TESS showed what human
volunteers recover by eye [@eisner2020; @eisner2021]. General-purpose libraries make the data accessible
[@lightkurve2018; @astroquery2019; @astropy2022].

SetuHQ does not replace any of these. It differs in three ways: it treats a language model as one
calibrated, correlated voice among measured deterministic ones rather than as a classifier to trust; it
measures the whole path from light curve to vetted dip on real TOIs with controls, not the vetting step
alone; and it exposes every step to people and to AI assistants with its provenance attached.

# Key features and design

- **Blind subjects.** Light curves are cleaned, detrended and cut into fixed segments with opaque ids, so
  no reviewer sees the target, its TOI status or its ephemeris; these are used only when scoring.
- **One reviewer interface.** Probes and Sentinels return the same `Classification`; a panel can mix
  providers, and each review records the provider, the model the API reported, the prompt version and the
  call time. Responses are cached by a hash of all of them, so a re-run reproduces them at no cost. Keys
  are read from the environment only and are refused anywhere they could be recorded.
- **Calibrated consensus.** Weights are skill on injected transits (true-positive minus false-positive
  rate, floored); a provider and model that have not been calibrated vote at the floor and are labelled so.
- **Vetting, fitting and a bounded false-alarm probability** as above, with every check's state shown as
  pass, fail, flag or *not measured*; a check that did not run is never shown as a pass.
- **The frozen real-TOI benchmark and leaderboard.** A stratified sample of confirmed and known planets,
  false positives and false alarms, frozen with a hash before any light curve was downloaded and split by
  star into tuning and held-out halves. Flux-inverted and block-scrambled copies of every light curve
  measure false alarms. The leaderboard (`setuhq leaderboard`) matches submitted events to the ephemerides
  and counts control false alarms itself, ranks by Youden's J [@youden1950] with Wilson intervals
  [@wilson1927], and refuses submissions that break its rules.
- **The everything-that-dims sweep.** A resumable, sector-wide search that classifies every star's
  variability, with sealed contribution bundles that are searched again on ingest before they count.
- **Pages.** Static, self-contained HTML: the Docket (a case file per candidate), print-ready plates, an
  app with every known exoplanet and animated Methods chapters with tested physics. No page loads a script
  or font from another site.
- **An MCP server.** `setuhq-mcp` exposes sixteen tools (catalogue lookups, stored candidates with
  provenance, BLS vetting, the transit fit, the false-alarm probability, the Methods physics and the stored
  benchmarks) over the Model Context Protocol, so an AI assistant runs SetuHQ's code instead of guessing.
  Every answer carries its provenance and honesty labels; over HTTP the tools that write are off unless
  allowed.
- **Reproducibility.** A worked example, TESS sector 1 of pi Mensae checked against @huang2018, is stored
  in the repository with its classifications and null distributions; the site, the README figures and the
  methods paper's numbers are rebuilt from committed results, and the checks fail when they drift.

SetuHQ is written in Python on NumPy [@harris2020], SciPy [@virtanen2020], Astropy [@astropy2022] and
Matplotlib [@hunter2007], and is tested offline by a pytest suite that runs in continuous integration. It is
distributed on PyPI as `setuhq`, under the AGPL-3.0-only or a commercial licence from Ashforde OÜ, and each
release is archived [@setuhq]; SetuHQ's own data, benchmark and papers are under CC BY 4.0.

# Acknowledgements

This work uses data from the TESS mission, funded by NASA's Science Mission Directorate, obtained from the
Mikulski Archive for Space Telescopes (MAST), and the NASA Exoplanet Archive, operated by the California
Institute of Technology under contract with NASA. It uses the Encyclopaedia of exoplanetary systems (exoplanet.eu). We thank the Planet Hunters teams,
whose task and published results SetuHQ is built to be compared with. SetuHQ is developed and maintained by
Ashforde OÜ.

# References

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
date: 24 October 2026
bibliography: paper.bib
---

<!--
SPDX-License-Identifier: CC-BY-4.0
The JOSS software paper. Compile with .github/workflows/joss-draft.yml (the Open Journals draft action) or
locally with `docker run --rm -v $PWD/paper:/data -e JOURNAL=joss openjournals/inara`.
Every result it quotes is copied verbatim from docs/paper/numbers.json, which scripts/paper_numbers.py
builds from the committed results; tests/test_release.py fails if a quoted value no longer matches.
The methods paper (docs/paper/paper.md) carries the full results with their intervals.
-->

# Summary

SetuHQ is a Python package that searches public light curves from NASA's Transiting Exoplanet Survey
Satellite [TESS, @ricker2015] for the brief dimming a planet causes when it crosses its star, and shows
exactly how each candidate was found. It copies the Planet Hunters task [@fischer2012; @eisner2021]: mark
the start and end of every dip in a blind-coded stretch of a light curve, then label it a potential planet
or noise. The volunteers are replaced by a *reviewer panel* of two kinds. *Probes* are deterministic, seeded
matched-filter detectors (a single-event search and box least squares, BLS, @kovacs2002) with stated
thresholds. *Sentinels* are vision-capable language models (Claude by default; OpenAI, Gemini and any
OpenAI-compatible endpoint are supported and labelled) that read the same plot and task text and return
strict, validated JSON with their marks and a sentence of reasoning.

Marks are clustered and scored by skill-weighted consensus, with each reviewer's weight measured on injected
transits. Every consensus dip is then vetted from the light curve alone (signal-to-noise, duration, edge,
odd/even and secondary-eclipse tests in the spirit of the Kepler and TESS Data Validation reports,
@twicken2018), fitted with a quadratic limb-darkened transit model [@mandel2002] using @claret2017
coefficients for the star's catalogue parameters [@stassun2019], and given a block-bootstrap false-alarm
probability never quoted below the resolution of its trials. Every output is labelled a *candidate*;
SetuHQ never calls anything it finds a confirmed or validated planet.

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
light curve should beat.

# State of the field

The TESS Science Processing Operations Center (SPOC) pipeline produces the light curves SetuHQ reads and
searches them for threshold-crossing events [@jenkins2016], with a Data Validation report for each
[@twicken2018]. Kepler's Robovetter set the standard for measured completeness and reliability, using
injected transits and inverted and scrambled light curves [@coughlin2016; @thompson2018]; DAVE brought
automated light-curve and centroid vetting to K2 [@kostov2019]. Machine-learned vetters such as AstroNet
[@shallue2018], its TESS triage variant [@yu2019] and ExoMiner [@valizadegan2022] rank events learned from
labelled examples. Statistical validation tools such as vespa [@morton2016] and TRICERATOPS
[@giacalone2021] estimate false-positive probabilities. Planet Hunters TESS showed what volunteers recover
by eye [@eisner2020; @eisner2021], and LATTE gives its vetters diagnostic plots for each candidate
[@eisner2020latte]. General-purpose libraries make the data accessible
[@lightkurve2018; @astroquery2019; @astropy2022].

*Build or contribute.* SetuHQ builds on these rather than replacing them: it reads SPOC light curves
through lightkurve and astroquery, and wraps TRICERATOPS as an optional validation step. What it adds does
not fit inside any of them, because it is a different kind of object: a reviewer *panel* with measured
weights, a benchmark with controls that scores whole pipelines (including the panel's own Sentinels) from
light curve to vetted dip, and a provenance record for every verdict. A vetter library has no place for
blind review by several kinds of reviewer, and a benchmark kept inside one method's code could not stay
neutral.

# Software design

Three trade-offs shape the code.

*Honesty over coverage.* A vetting check that did not run is shown as *not measured*, never as a pass; a
false-alarm probability is never quoted below the resolution of its trials; a Sentinel whose provider and
model have not been calibrated votes at the floor weight and is labelled so. This costs completeness on
paper and buys results a reader can take at their word.

*One interface for unlike reviewers.* Probes and Sentinels return the same `Classification`, so a panel can
mix deterministic detectors with any AI provider, and the aggregation and calibration code never knows
which is which. The price is that a Sentinel's answer must be forced into strict JSON, validated and
clipped; the gain is that adding a provider is a small adapter, and its effect on the benchmark is measured
the same way as any other change.

*Provenance as data.* A run stores the SHA-256 of every light curve, the configuration hash, a fingerprint
of the result-making code and every reviewer's marks, labels and reasons, and Sentinel answers are cached
by a hash of the request. A stored run can therefore be re-vetted with new code without asking the
reviewers again, and the benchmark records which commit produced each number. Fingerprints hash canonical
source text, so they survive renames and licence headers but not a change to the code.

The same functions serve four surfaces: the `setuhq` command line, self-contained HTML pages (the Docket,
print-ready plates and an app of every known exoplanet with tested Methods chapters), the frozen real-TOI
benchmark and its leaderboard (`setuhq leaderboard`, ranked by Youden's J [@youden1950] with Wilson
intervals [@wilson1927]), and an MCP server (`setuhq mcp`) whose tools are those public functions, so an AI
assistant runs SetuHQ's code instead of guessing. SetuHQ is written in Python on NumPy [@harris2020], SciPy
[@virtanen2020], Astropy [@astropy2022] and Matplotlib [@hunter2007]; it is distributed on PyPI as `setuhq`
under the AGPL-3.0-only or a commercial licence from Ashforde OÜ, and each release is archived on Zenodo
[@setuhq]. SetuHQ's own data, benchmark and papers are under CC BY 4.0.

# Research impact statement

SetuHQ is new, and we claim no realized impact yet: no external publication uses it so far. Its near-term
significance rests on results that exist and can be rebuilt from the repository today, including the
negative ones. The frozen benchmark holds 662 TESS Objects of Interest (300 confirmed or known planets, 300
false positives and 62 false alarms), split by star into tuning and held-out halves, with flux-inverted and
block-scrambled copies of every light curve as controls. On the held-out half the Probes recover
60% (90/150; 95% CI 52–67%) of the confirmed or known planets on stars with 2-minute data, but only
10% (2/20; 95% CI 3–30%) below 2 Earth radii; they find the dip of 77% (96/124; 95% CI 69–84%) of the false
positives with 2-minute data and reject or flag 68% (65/96; 95% CI 58–76%) of those. On the leaderboard a baseline that never
reads a light curve, a logistic regression on catalogue metadata, scores J = +0.39 (+0.27 to +0.49) against
+0.35 (+0.23 to +0.45) for the Probes, and the benchmark cannot show that the Probes beat it
(paired ΔJ (floor − Probes) = +0.039, 95% CI -0.096 to +0.173; the probability that ΔJ is zero or
below is 0.29). The two Sentinel
personas agree on 35 of 37 subsample stars (φ = 0.88), so they act as one correlated voter. A stored worked
example (TESS sector 1 of pi Mensae, checked against @huang2018) reproduces offline. These results, with
their intervals, are in the methods paper in the repository (`docs/paper/paper.md`); the open leaderboard,
the MCP server and a contribution path for community sector sweeps are how others can test their own
vetters against the same floor.

# AI usage disclosure

<!--
OWNER: check every sentence of this section against your own records and edit it before submitting.
JOSS's AI policy (joss.readthedocs.io/en/latest/policies.html) asks for the tools and their versions, where
they were used, the kind of help, and an affirmation that humans reviewed the output and made the core
design decisions; it treats an incomplete or inaccurate disclosure as an ethical violation.
Complete the list marked [OWNER] and confirm the sentence about the author's own role.
-->

Generative AI enters SetuHQ in two separate ways.

*In the software.* The Sentinel reviewers are language models by design. By default they call Anthropic's
Claude (model `claude-sonnet-5-5` in version 0.1.0); OpenAI, Gemini and OpenAI-compatible models can be
configured instead. Their answers are data that the benchmark measures, every answer is labelled with its
provider and model, and an uncalibrated Sentinel votes only at the floor weight.

*In making the software and this paper.* Large parts of SetuHQ's code, tests and documentation, and of the
text of this paper, were written with AI assistance: Anthropic's Claude, used through the Claude Code
agent (Claude Opus 5.5 for the preparation of this paper; [OWNER: list the other Claude models and versions
used in development]). The assistance included generating and refactoring code, writing tests, drafting
documentation and paper text, and finding and checking references. The author set the scientific scope and
the honesty rules (outputs are candidates only, every number comes from a committed result, negative results
are reported), chose the architecture and the benchmark design, and reviewed, edited and accepted the
AI-assisted code, documentation and text; the author takes full responsibility for the work. Correctness
does not rest on that review alone: the offline test suite runs in continuous integration, checks rebuild
every published number, figure and page from the committed results and fail on any difference, every
reference's DOI was resolved on Crossref, and the frozen benchmark scores the pipeline on held-out data. No
AI tool is used in correspondence with JOSS editors or reviewers.

# Acknowledgements

This work uses data from the TESS mission, funded by NASA's Science Mission Directorate, obtained from the
Mikulski Archive for Space Telescopes (MAST), and the NASA Exoplanet Archive, operated by the California
Institute of Technology under contract with NASA. It uses the Encyclopaedia of exoplanetary systems
(exoplanet.eu). We thank the Planet Hunters teams, whose task and published results SetuHQ is built to be
compared with. SetuHQ is developed and maintained by Ashforde OÜ and has received no external grant funding.
<!-- OWNER: confirm the funding sentence above; JOSS asks papers to acknowledge any financial support. -->

# References

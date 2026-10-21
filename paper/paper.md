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

*Build or contribute.* SetuHQ builds on these rather than replacing them: it reads light curves through
lightkurve and astroquery, and wraps TRICERATOPS as an optional validation step. What it adds does not fit
inside any of them, because it is a different kind of object: a reviewer *panel* with measured weights, a
benchmark with controls that scores whole pipelines (including the panel's own Sentinels) from light curve
to vetted dip, and a provenance record for every verdict. A vetter library has no place for blind review
by several kinds of reviewer, and a benchmark kept inside one method's code could not stay neutral.

# Software design

Three trade-offs shape the code.

*Honesty over coverage.* Every output is labelled a candidate. A vetting check that did not run is shown as
*not measured*, never as a pass; a false-alarm probability is never quoted below the resolution of its
trials; a Sentinel whose provider and model have not been calibrated votes at the floor weight and is
labelled so. This costs completeness on paper and buys results a reader can take at their word.

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

The same functions serve four surfaces: the `setuhq` command line, static self-contained HTML pages (the
Docket, print-ready plates and an app of every known exoplanet with tested Methods chapters), the frozen
real-TOI benchmark and its leaderboard (`setuhq leaderboard`, ranked by Youden's J [@youden1950] with
Wilson intervals [@wilson1927]), and an MCP server (`setuhq mcp`) whose tools are those public functions, so
an AI assistant runs SetuHQ's code instead of guessing and every answer carries its provenance. SetuHQ is
written in Python on NumPy [@harris2020], SciPy [@virtanen2020], Astropy [@astropy2022] and Matplotlib
[@hunter2007]; it is distributed on PyPI as `setuhq` under the AGPL-3.0-only or a commercial licence from
Ashforde OÜ, and each release is archived [@setuhq]. SetuHQ's own data, benchmark and papers are under
CC BY 4.0.

# Research impact statement

SetuHQ is new, and we claim no realized impact yet: no external publication uses it so far. Its near-term
significance rests on materials that exist and can be checked today. The frozen benchmark of real TOIs, with
its tuning and held-out split, controls and committed per-star outcomes, lets any vetting method be scored
on the same terms; the leaderboard already holds seeded entries, including a catalogue-metadata baseline
that never reads a light curve. A stored worked example (TESS sector 1 of pi Mensae, checked against
@huang2018) reproduces offline, and the methods paper in the repository (`docs/paper/paper.md`) reports
every benchmark result, including the negative ones, with its interval. The public site, the MCP server and
a contribution path for community sector sweeps are the means by which others can use and extend it.

# AI usage disclosure

Generative AI is part of the software by design: the Sentinels are vision-capable language models, and the
benchmark measures them as such. Development of the code, the documentation and the drafting of this paper
were also assisted by AI coding tools. Correctness is checked independently of those tools: by the offline
test suite run in continuous integration, by checks that rebuild every published number, figure and page
from the committed results and fail on any difference, and by the frozen benchmark. All results are
reproducible from the committed code and data.

# Acknowledgements

This work uses data from the TESS mission, funded by NASA's Science Mission Directorate, obtained from the
Mikulski Archive for Space Telescopes (MAST), and the NASA Exoplanet Archive, operated by the California
Institute of Technology under contract with NASA. It uses the Encyclopaedia of exoplanetary systems (exoplanet.eu). We thank the Planet Hunters teams,
whose task and published results SetuHQ is built to be compared with. SetuHQ is developed and maintained by
Ashforde OÜ.

# References

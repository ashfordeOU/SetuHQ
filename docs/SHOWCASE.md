# Worked examples

SetuHQ searches any TESS star. The site (setuhq.com) shows these stored runs as worked examples, each on public TESS SPOC 2-minute light curves from MAST, with its data hash, configuration hash and code fingerprint in its manifest. pi Men is one of them: the reference check against Huang et al. 2018.

Every run but pi Men is **Probes only; Sentinels not run on this example**: its configuration names only the three Probes, and its manifest records `"panel": {"mode": "probes_only"}`. Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.

Dips are counted by their vetting outcome: a candidate (passed vetting) stays unconfirmed, a flagged dip is open, and a rejected dip is not a candidate. A known planet found again is a check of the pipeline, not a discovery; each planet is named with its reference.

Published values: NASA Exoplanet Archive, table ps (every row for each planet), fetched 2026-10-22 (`docs/results/showcase_reference.json`); the comparisons are written by `scripts/showcase_compare.py`.

| star | kind | sectors | dips | against the literature | site |
|---|---|---|---|---|---|
| WASP-126 | Hot Jupiter | 1 | 8 dips (8 candidates) | WASP-126 b: 8 of 8 transits (8 candidates). | [case file](https://setuhq.com/candidates/wasp-126/case-file/) |
| TOI-270 | Multi-planet system | 5 | 7 dips (5 candidates, 2 flagged) | TOI-270 b: none of 6 transits; TOI-270 c: 5 of 5 transits (5 candidates); TOI-270 d: 2 of 2 transits (2 flagged; no period). | [case file](https://setuhq.com/candidates/toi-270/case-file/) |
| HD 15337 | Small planets near the limit | 4 | 3 dips (2 candidates, 1 flagged) | HD 15337 b: 1 of 5 transits (1 candidate; BLS period not the planet's); HD 15337 c: 2 of 2 transits (1 candidate, 1 flagged; BLS period not the planet's). | [case file](https://setuhq.com/candidates/hd-15337/case-file/) |
| TOI-236 | Known false positive | 2 | 6 dips (6 rejected) | Caught: all 6 dips on the TOI ephemeris were rejected by vetting (secondary_any_phase, secondary_eclipse), so none is a candidate. | [case file](https://setuhq.com/candidates/toi-236/case-file/) |
| pi Men | Reference check | 1 | 7 dips (5 candidates, 1 flagged, 1 rejected) | Rp/R★ and T14 within 5% of Huang et al. 2018 (docs/results/pi_men_validation.md). | [case file](https://setuhq.com/candidates/case-file/) |

## WASP-126: hot jupiter

A Jupiter-sized planet on a 3.3-day orbit: deep, easy transits, in the TESS southern continuous viewing zone.

**Why:** The easy case: a transit about 0.6% deep that any search should find, so it shows the whole path from light curve to fit with little doubt about the signal.

**Run:** `runs/tess-wasp-126-s1`, TESS sector 1; Probes only; Sentinels not run on this example. 8 dips (8 candidates).

**Against the literature** (Maxted et al. 2016): WASP-126 b: 8 of 8 transits (8 candidates). The full comparison: [docs/results/showcase/tess-wasp-126-s1.md](docs/results/showcase/tess-wasp-126-s1.md).

**Reproduce:**

```
setuhq run configs/showcase/tess-wasp-126-s1.toml --out runs/tess-wasp-126-s1 && setuhq crossmatch runs/tess-wasp-126-s1
```

## TOI-270: multi-planet system

An M dwarf with three known transiting planets at 3.4, 5.7 and 11.4 days: several periods in one star.

**Why:** One light curve, three periods. It shows what the search does when a star has more than one planet, and which of them a 13-day subject can hold.

**Run:** `runs/tess-toi-270-s5`, TESS sector 5; Probes only; Sentinels not run on this example. 7 dips (5 candidates, 2 flagged).

**Against the literature** (Günther et al. 2019): TOI-270 b: none of 6 transits; TOI-270 c: 5 of 5 transits (5 candidates); TOI-270 d: 2 of 2 transits (2 flagged; no period). The full comparison: [docs/results/showcase/tess-toi-270-s5.md](docs/results/showcase/tess-toi-270-s5.md).

**Reproduce:**

```
setuhq run configs/showcase/tess-toi-270-s5.toml --out runs/tess-toi-270-s5 && setuhq crossmatch runs/tess-toi-270-s5
```

## HD 15337: small planets near the limit

A bright K dwarf with two small known planets: b (about 1.6 Earth radii, 4.8 days, roughly 350 ppm deep) and c (17.2 days).

**Why:** A small planet whose single transits are near the noise of one sector: it shows what the panel and vetting do at the edge of what a 10-minute-binned search can see, and the page says what it missed.

**Run:** `runs/tess-hd-15337-s4`, TESS sector 4; Probes only; Sentinels not run on this example. 3 dips (2 candidates, 1 flagged).

**Against the literature** (Gandolfi et al. 2019): HD 15337 b: 1 of 5 transits (1 candidate; BLS period not the planet's); HD 15337 c: 2 of 2 transits (1 candidate, 1 flagged; BLS period not the planet's). The full comparison: [docs/results/showcase/tess-hd-15337-s4.md](docs/results/showcase/tess-hd-15337-s4.md).

**Reproduce:**

```
setuhq run configs/showcase/tess-hd-15337-s4.toml --out runs/tess-hd-15337-s4 && setuhq crossmatch runs/tess-hd-15337-s4
```

## TOI-236: known false positive

A TESS Object of Interest the TOI table dispositions as a false positive (FP): a 2.4% dip every 4.5 days.

**Why:** A test SetuHQ must fail to pass: TOI-236.01 is in the real-TOI benchmark's false-positive set. The page says what the vetting did with it, whatever it did.

**Run:** `runs/tess-toi-236-s2`, TESS sector 2; Probes only; Sentinels not run on this example. 6 dips (6 rejected).

**Against the literature** (TOI table (NASA Exoplanet Archive): TOI-236.01 dispositioned FP): Caught: all 6 dips on the TOI ephemeris were rejected by vetting (secondary_any_phase, secondary_eclipse), so none is a candidate. The full comparison: [docs/results/showcase/tess-toi-236-s2.md](docs/results/showcase/tess-toi-236-s2.md).

**Reproduce:**

```
setuhq run configs/showcase/tess-toi-236-s2.toml --out runs/tess-toi-236-s2 && setuhq crossmatch runs/tess-toi-236-s2
```

## pi Men: reference check

A sun-like star with a super-Earth on a 6.3-day orbit: the run checked in full against Huang et al. 2018.

**Why:** The reference check: the one run with the Sentinels as well as the Probes, its limb-darkened fit compared with the discovery paper in docs/results/pi_men_validation.md.

**Run:** `runs/tess-pi-men-s1`, TESS sector 1; Probes and Sentinels. 7 dips (5 candidates, 1 flagged, 1 rejected).

**Against the literature** (Huang et al. 2018): Rp/R★ and T14 within 5% of Huang et al. 2018 (docs/results/pi_men_validation.md). The full comparison: [docs/results/pi_men_validation.md](docs/results/pi_men_validation.md).

**Reproduce:**

```
python scripts/rerun_pi_men.py --out runs/tess-pi-men-s1-new
```

Build the site from every run (the lead run first):

```
setuhq site runs/tess-pi-men-s1 runs/tess-wasp-126-s1 runs/tess-toi-270-s5 runs/tess-hd-15337-s4 runs/tess-toi-236-s2 --catalog docs/discoveries/catalog.json --out site
```

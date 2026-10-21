<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Beyond planets: flares, pulsations and CHEOPS

SetuHQ's transit search keeps every dip; this part looks at the star itself. It detects **stellar flares**
and describes their shape and energy, extracts **pulsation frequencies** and the granulation-like background,
measures **numax and Δν** of solar-like oscillators, and reads **public CHEOPS light curves** alongside TESS.

Everything here is a measurement with a stated significance. A flare or a frequency is *detected*, never
confirmed; a variability type is *likely* or a *candidate*; an energy rests on stated assumptions or is
reported as unavailable. Each capability carries the status its validation earned
([results/stellar_validation.md](results/stellar_validation.md)); a tool output says it.

**SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS mission or the CHEOPS Consortium.**
The names CHEOPS and ESA are used descriptively; SetuHQ shows no mission logos or artwork and reproduces no
figures from the papers it follows.

```bash
pip install -e ".[tess,wavelets,cheops]"          # lightkurve (MAST), PyWavelets (denoising), DACE's client (CHEOPS)

setuhq flares "TIC 441420236" --sector 1 --completeness 10 --out aumic.json     # AU Mic: flares, null, completeness
setuhq flares my_lightcurve.csv --teff 3200 --radius 0.3 --denoise
setuhq pulsations "TIC 289592423" --sector 29 --surrogates 10 --out hr10.json   # HR 10: frequencies and the null
setuhq cheops "HR 10" --max-visits 1 --out hr10_cheops.json                    # public CHEOPS visits, detrended
setuhq cheops "EV Lac" --flares --denoise
```

MCP tools (`setuhq-mcp`): `find_flares`, `pulsation_spectrum`, `get_cheops_lightcurve`; the plugin's
`/setuhq-stellar` command uses them. Each answer carries its provenance (version, code, input sha256), its
labels and its capability's validation status.

## Flares (`src/setuhq/flares.py`)

The methods follow Bruno et al. (2024, A&A 686, A239), Poyatos et al. (2025, A&A 699, A242), Davenport et al.
(2014), Mendoza et al. (2022) and Günther et al. (2020), reimplemented from their descriptions.

1. **Detrending that keeps flares.** Each stretch of data between gaps is detrended on its own: an iterated
   running median (TESS, a 6-hour window, or P/8 but at least 20 minutes for a star that rotates in under
   2 days with a deep modulation), or a 20-minute Savitzky-Golay filter whose polynomial degree (2 to 10) minimises
   the AIC (CHEOPS, after Poyatos et al.). Upward excursions and the points after them are masked before the
   trend is recomputed, so a flare's decay is not absorbed. The local scatter is a running median absolute
   deviation of the masked residual.
2. **Candidates.** The three criteria of Chang et al. (2015) as AltaiPony applies them: residual over local
   scatter ≥ N1 = 3, residual less its photometric error ≥ N2 = 2, and N3 consecutive points (3 at 2-minute
   cadence; 5 at 20 s and for CHEOPS, as Poyatos et al.). A candidate is extended while the residual stays
   above half the scatter and never crosses a gap.
3. **Wavelet denoising (optional).** A stationary wavelet transform of each stretch (Daubechies-18, level 2 by
   default), hard thresholding at Donoho and Johnstone's universal threshold with the median absolute deviation
   for the scale, as Poyatos et al. describe. Candidates are found on the denoised series, with its own local
   scatter; every amplitude, ED and energy is measured on the original detrended data.
   `flares.tune_denoising` repeats their parameter search (wavelet and level by injection and recovery) on any
   light curve.
4. **Morphology.** Each candidate is fitted with the Mendoza et al. (2022) template (a Gaussian convolved with a
   double exponential, shape constants from GJ 1243), averaged over the exposure, plus a linear baseline. It is
   kept when one flare beats a quadratic by ΔBIC ≥ 6 and the chosen flare models beat as many symmetric Gaussian
   bumps by ΔBIC ≥ 10. Components are added one at a time, up to five, while each lowers the BIC by 6 or more
   (Davenport et al. 2014; Bruno et al. and Poyatos et al. do the same with the AIC). A flare with two or more
   components is *complex*. Recorded: peak time, amplitude, FWHM, rise and decay times, duration, the ED of the
   fitted model (`ed_s`) and of the data in the detection window (`ed_data_s`), each component, and the BIC and
   AIC of every model tried.
5. **Energies.** E_band = ED × L★,band, with the band luminosity from the TIC Teff and radius (a Planck spectrum
   through the TESS or CHEOPS response from the SVO Filter Profile Service), cross-checked against the TESS
   magnitude and distance. E_bol assumes **the flare radiates as a 9000 K blackbody** (Shibayama et al. 2013;
   Günther et al. 2020): E_bol = ED · πR★²σT⁴ ∫R B(Teff) dλ / ∫R B(9000 K) dλ. Without Teff and radius both are
   **unavailable**, and say so. TIC v8.2 has no Teff for AU Mic or Proxima Cen; `--teff` supplies one, and the
   record says it was supplied.
6. **Flare frequency distribution.** The cumulative FFD; the maximum-likelihood power-law index above a
   completeness energy, with (α − 1)/√n as its uncertainty and the small-sample correction (Clauset, Shalizi &
   Newman 2009); and the Vuong likelihood-ratio test against a truncated log-normal, as Bruno et al. and Poyatos
   et al. report.
7. **Completeness.** Synthetic Mendoza flares (log-uniform amplitude and FWHM) are multiplied into the star's own
   light curve, away from its real flares, and the whole detection runs again; recovery is reported against
   amplitude, ED and energy with Wilson 95% intervals, and the energy above which it stays at 90% or more.
8. **Nulls.** The flux-inverted light curve (no star makes a downward flare; a transit becomes a bump, so this
   is an upper bound), and quiet solar-type stars where every detection counts as a false positive.

The asymmetry test (step 4) was set on AU Mic's sector 1 and its flux-inverted null, then frozen before the other
stars were run; the validation says so.

## Pulsations and asteroseismology (`src/setuhq/pulsations.py`)

- **Amplitude spectrum**: Lomb-Scargle scaled to semi-amplitude, oversampled ten times the Rayleigh resolution.
- **Pre-whitening**: the highest residual peak, then a non-linear least-squares refit of every extracted sinusoid
  together, until the next peak's S/N falls below 4 (Breger et al. 1993), the noise being the mean residual
  amplitude in a 2 d⁻¹ box. Uncertainties follow Montgomery & O'Donoghue (1999); peaks within 1.5/T of a stronger
  one are flagged unresolved; harmonics and two-term combinations within 1/T are flagged.
- **Type** (heuristic): δ Scuti, γ Doradus, hybrid, solar-like or rotation from where the independent amplitude
  lies (5 d⁻¹ boundary), harmonics, a solar-like excess and Teff when known; confidence is medium or low, never
  high, with reasons and alternatives.
- **Background**: Harvey-like profiles a/(1 + (ν/b)^c) plus white noise, one or two by BIC, fitted by maximum
  likelihood to the χ²₂ periodogram of the pre-whitened residual (as Salmon et al. 2024 model HR 10's
  granulation-like signal).
- **numax and Δν**: a Gaussian envelope over the background (detected when it lowers the BIC by 10), Δν from the
  autocorrelation of the background-divided spectrum near the Stello et al. (2009) scaling, uncertainties from a
  bootstrap of the spectrum. Needs a Nyquist frequency above numax (2-minute TESS: 4167 µHz).
- **Null**: the whole extraction on AR(1) red-noise copies of the residual (the process the sweep's variability
  null uses, here at the native cadence) and on Gaussian noise with the fitted background's spectrum; the mean
  number of frequencies they yield is the false-frequency rate.

## CHEOPS (`src/setuhq/cheops.py`)

- **Public data only.** Visits are listed by position through DACE in public mode (no key is read or needed),
  only those the archive marks `status_published` are kept, the latest DRP version per visit, one request at a
  time, rate-limited, cached once under `cache/cheops/`. A visit not marked public is refused before any request.
  No raw CHEOPS file is in the repository or the wheel; the tests use a 140-point derived excerpt of one public
  visit with its programme, file key, observation id and DRP version. `read_drp_fits` reads a DRP light-curve
  FITS file you downloaded yourself, offline.
- **Detrending** (after pycheops, Maxted et al. 2022): linear decorrelation against sin and cos of the roll angle
  φ, 2φ, 3φ, time (linear and quadratic), background, centroid (x, y, x², y², xy) and contamination, terms added
  while each lowers the BIC by 2, with upward excursions kept out of the fit; bad data are the DRP event flags,
  non-finite values and 5σ low outliers. A known astrophysical signal (for example a pulsator's sinusoids) can be
  divided out first so the decorrelation does not absorb it.
- **One timeline with TESS**: DACE gives BJD_TDB − 2,400,000, converted to BTJD (BJD_TDB − 2,457,000) as TESS
  uses. The bands differ (CHEOPS 330-1100 nm, TESS 600-1000 nm), so amplitudes are not interchangeable.
- **Acknowledgement on every output.** `cheops.credit()` gives the block every CHEOPS-derived record, page and
  tool answer carries; a test checks each one.

### Data source and terms

ESA's CHEOPS publication guidelines name the CHEOPS mission archive (cheops.unige.ch/archive_browser) as the
place CHEOPS data are made available; its public light curves are served through DACE at the University of
Geneva. From this environment the archive browser answered 403 and no separate ESA ESDC CHEOPS service was
reachable, so SetuHQ uses DACE's public API (through its own client, `dace-query`, GPL-3.0, an optional extra).
DACE publishes an acknowledgement it asks published material to include
([dace.unige.ch/publications](https://dace.unige.ch/publications/)), reproduced below; no separate DACE terms-of-use
page was found. ESA's ESDC terms require prior authorisation from ESA (data.licences@esa.int) for any
commercial use of its archive data: **SetuHQ's commercial licence covers SetuHQ's code, not CHEOPS data.**

### Acknowledgement and credit

CHEOPS is an ESA mission in partnership with Switzerland with important contributions to the payload and the ground segment from Austria, Belgium, France, Germany, Hungary, Italy, Portugal, Spain, Sweden, and the United Kingdom. The CHEOPS Consortium would like to gratefully acknowledge the support received by all the agencies, offices, universities, and industries involved. Their flexibility and willingness to explore new approaches were essential to the success of this mission. CHEOPS data analysed in this article will be made available in the CHEOPS mission archive (https://cheops.unige.ch/archive_browser/).

The validation used public visits of programmes CH_PR100010 (Credit: ESA, Gyula SZABO, as the archive gives it) and CH_PR100018
(Credit: ESA, Isabella PAGANO); each output lists its own file keys, observation ids and credit lines.
Cite: Benz, W., et al. 2021, Experimental Astronomy, 51, 109 (the mission); Hoyer, S., et al. 2020, A&A, 635, A24
(the Data Reduction Pipeline); Fortier, A., et al. 2024, A&A, 687, A302 (in-flight performance).

This publication makes use of The Data & Analysis Center for Exoplanets (DACE), which is a facility based at the University of Geneva (CH) dedicated to extrasolar planets data visualisation, exchange and analysis. DACE is a platform of the Swiss National Centre of Competence in Research (NCCR) PlanetS, federating the Swiss expertise in Exoplanet research. The DACE platform is available at https://dace.unige.ch.

## Validation

The protocol, its seed, the published numbers compared against and every result are in
[results/stellar_validation.md](results/stellar_validation.md) and `.json`, generated by
`scripts/stellar_validation.py` (resumable per item; `--report` rebuilds the two files). The published values
are transcribed, with their sources, in [results/stellar_validation_references.json](results/stellar_validation_references.json).

Status (protocol v1, seed 20261021): **flares partly validated** (6 of 8 checks), **pulsations partly validated**
(4 of 6), **CHEOPS unvalidated** (0 of 3 checks; the decorrelation itself agrees with pycheops on two of three
visits). In short:

- **Flares, TESS.** AU Mic sector 1: 37 of Günther et al.'s 46 flare components fall in a SetuHQ flare
  (0.80, 95% CI 0.67-0.89), peak amplitudes agree (ours/theirs 0.97, 0.88-1.08), no flare on the inverted light
  curve; our complex fraction is higher (0.59 against 0.46). Proxima Cen sectors 11-12: 59 of our 61 flares are in
  Medina et al.'s list, but we recover only half of theirs (0.49), mostly missing flares with ED below 3 s (0.15
  below 1 s; 0.77 at 3-10 s). Energies: our 9000 K bolometric energies are 1.15× Günther et al.'s (1.05-1.34) for
  TIC 150359500; for Proxima our TESS-band energies are 4.3× Medina et al.'s, which we trace to the ED definition,
  the stellar luminosity and an untraced factor of about 1.8. Quiet stars: 1 detection in 147 days.
- **Flares, CHEOPS.** On public DRP light curves of five M dwarfs (11.3 days), the complex fraction (0.52,
  0.38-0.66) and the power-law index (2.08 ± 0.24) are consistent with Poyatos et al.'s 0.42 and 1.99 ± 0.10, but
  denoising gains nothing on DRP data (−2% against their +35% on imagettes) and the inverted null finds 8 events,
  so CHEOPS flare lists carry a substantial false-positive share.
- **Pulsations.** β Pic sectors 5-7: all 54 of Zieba et al.'s frequencies recovered within 3σ. HR 10: 76% and 61% of
  Salmon et al.'s frequencies in sectors 2 and 29 (8 and 9 of their 10 strongest), amplitudes within 10%; red-noise
  surrogates give 0.1-0.2 false frequencies per light curve. TOI-197: numax 433 ± 5 µHz and Δν 28.8 ± 3.0 µHz
  against Huber et al.'s 430 ± 18 and 28.94 ± 0.15. Our granulation frequency for HR 10 (56 µHz, one component)
  disagrees with Salmon et al.'s 151 µHz from a different estimator.
- **CHEOPS.** On the same input points and terms our decorrelation reproduces pycheops to 0.03 and 0.5 ppm on two
  visits; on the third pycheops' fit has three times our rms on the same points, so it did not reach the
  least-squares optimum. End to end the DACE arrays and pycheops' product differ (correlation 0.61-0.89). HR 10's
  strongest frequency is found in every CHEOPS visit, the second only in one.

What is not validated, and why, is listed in the results file.

## Limits

- TESS 2-minute cadence resolves few flares shorter than about 6 minutes; the morphology of short, low-amplitude
  flares is poorly constrained, and the asymmetry test rejects flares whose rise is unresolved.
- The Mendoza template was fitted on GJ 1243; flares of other stars, and low-energy flares in particular, can be
  more symmetric (Poyatos et al. discuss this), which biases both the template fit and the shape test.
- Energies depend on the TIC Teff and radius and on the 9000 K assumption; a factor of about two either way is
  the usual systematic.
- CHEOPS: DACE serves DRP subarray photometry (tens of seconds); Poyatos et al. and Bruno et al. used 3-s
  imagettes reduced with PIPE or the DRT, which SetuHQ does not reproduce. CHEOPS visits are short (often under
  5 hours), so long flares are cut and FFDs from them are incomplete at high energy.
- Pulsations: S/N ≥ 4 against a white-noise box is optimistic on red noise; read the surrogate null. Amplitude
  modulation and unresolved close frequencies (within 1.5/T) are flagged, not modelled.
- The type is a heuristic from photometry alone; mode identification needs spectroscopy or rotational splitting.

## References

Breger, M., et al. 1993, A&A, 271, 482 · Bruno, G., et al. 2024, A&A, 686, A239 · Chang, H.-Y., et al. 2015, ApJ,
814, 35 · Clauset, A., Shalizi, C. R., & Newman, M. E. J. 2009, SIAM Review, 51, 661 · Davenport, J. R. A., et al.
2014, ApJ, 797, 122 · Davenport, J. R. A. 2016, ApJ, 829, 23 · Günther, M. N., et al. 2020, AJ, 159, 60 · Harvey, J.
1985, ESA SP-235, 199 · Huber, D., et al. 2019, AJ, 157, 245 · Ilin, E., et al. 2022, MNRAS, 513, 4579 · Maxted,
P. F. L., et al. 2022, MNRAS, 514, 77 · Medina, A. A., et al. 2020, ApJ, 905, 107 · Mendoza, G. T., et al. 2022,
AJ, 164, 17 · Montgomery, M. H., & O'Donoghue, D. 1999, DSSN, 13, 28 · Poyatos, J., et al. 2025, A&A, 699, A242 ·
Rodrigo, C., & Solano, E. 2020, XIV.0 Scientific Meeting of the SEA, 182 · Salmon, S. J. A. J., et al. 2024, A&A,
690, A73 · Shibayama, T., et al. 2013, ApJS, 209, 5 · Stello, D., et al. 2009, MNRAS, 400, L80 · Zieba, S., et al.
2019, A&A, 625, L13

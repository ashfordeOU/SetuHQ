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
   (Davenport et al. 2014; Bruno et al. and Poyatos et al. do the same with the AIC). The BIC counts an effective
   number of points, N(1 − ρ)/(1 + ρ) for the noise's lag-one correlation ρ, and an extra component must also be a
   visible peak (3σ and a tenth of the strongest component): without these, injected single flares on AU Mic (the
   tuning star) came back split 41% of the time. The visibility rule has a cost: **a secondary peak below a tenth of
   the primary cannot be kept as a component by construction**, so such a flare is always reported as simple.
   The false-split rate is measured on injected single flares, and the merge rate on injected two-component flares,
   on stars that did not tune the rule, and both are reported. A flare with two or more
   components is *complex*. Recorded: peak time, amplitude, FWHM, rise and decay times, duration, the ED of the
   fitted model (`ed_s`) and of the data in the detection window (`ed_data_s`), each component, and the BIC and
   AIC of every model tried.
5. **Energies.** E_band = ED × L★,band. The band luminosity comes from the TESS magnitude and the distance with
   Sullivan et al. (2015)'s band-integrated zero point, 4.03 × 10⁻⁶ erg s⁻¹ cm⁻² at T = 0 (as Medina et al. 2020
   do), when both are known; otherwise from Teff and radius (a Planck spectrum through the TESS or CHEOPS response
   from the SVO Filter Profile Service). Both routes are reported side by side. E_bol assumes **the flare radiates as a 9000 K blackbody** (Shibayama et al. 2013;
   Günther et al. 2020): E_bol = E_band σT⁴ / (4π ∫R B(9000 K) dλ), which with the Teff and radius route is their
   ED · πR★²σT⁴ ∫R B(Teff) / ∫R B(9000 K). With neither route the energies are **unavailable**, and say so. TIC
   v8.2 has no Teff for AU Mic or Proxima Cen; their energies use the magnitude route. A Teff from elsewhere (for
   CHEOPS targets, the CHEOPS archive's) is labelled with its source in every record.
6. **Flare frequency distribution.** The cumulative FFD; the maximum-likelihood power-law index above a
   completeness energy, with (α − 1)/√n as its uncertainty and the small-sample correction (Clauset, Shalizi &
   Newman 2009); and the Vuong likelihood-ratio test against a truncated log-normal, as Bruno et al. and Poyatos
   et al. report.
7. **Completeness.** Synthetic Mendoza flares (log-uniform amplitude and FWHM) are multiplied into the star's own
   light curve, away from its real flares, and the whole detection runs again; recovery is reported against
   amplitude, ED and energy with Wilson 95% intervals, and the energy above which it stays at 90% or more.
8. **Nulls.** The flux-inverted light curve with the real flares' windows masked (no star makes a downward flare;
   unmasked, a real flare becomes a deep dip that drags the trend and leaves bumps beside it; a transit still
   becomes a bump, so this is an upper bound), and quiet solar-type stars where every detection counts as a false
   positive.

The asymmetry test (step 4) was set on AU Mic's sector 1 and its flux-inverted null, then frozen before the other
stars were run; the validation says so.

## Pulsations and asteroseismology (`src/setuhq/pulsations.py`)

- **Amplitude spectrum**: Lomb-Scargle scaled to semi-amplitude, oversampled ten times the Rayleigh resolution.
- **Pre-whitening**: the residual peak of highest S/N, fitted, then every amplitude and phase refitted, and every
  sinusoid refitted together by non-linear least squares every ten peaks and at the end, until no peak has S/N ≥ 4
  (Breger et al. 1993), the noise being the mean residual amplitude in a box (2 d⁻¹, at least 25/T) without the
  peak's own ±2/T. Uncertainties follow Montgomery & O'Donoghue (1999); peaks within 1.5/T of a stronger one are
  flagged unresolved; harmonics and two-term combinations of the ten strongest frequencies within a quarter of
  1/T (or 3σ_f) are flagged as possible combinations, with the rate at which a random frequency would be flagged
  by chance (about 6% for 40 random frequencies over 5-60 d⁻¹ in 27 days; it was 37-67% with every stronger peak
  as a parent and a 1/T tolerance).
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
- **Status check twice.** A visit must be marked public in the listing and in its cached copy, or it is refused.
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

ESA's CHEOPS publication guidelines name the **CHEOPS Mission Archive** (cheops.unige.ch/archive_browser) and its
**mirror at the ASI Space Science Data Center** (cheops-archive.ssdc.asi.it) as the places CHEOPS data are made
public. SetuHQ checks both first (`cheops.probe_archives`, a HEAD request whose result is cached for the day and
recorded in each listing): it records whether each archive was reachable from the environment SetuHQ runs in (in
the validation runs the Mission Archive was not reachable from this environment, HTTP 403), which says nothing
about the archives themselves. SetuHQ found no documented programmatic interface to either, so it lists and fetches
visits through **DACE** (dace.unige.ch), the University of Geneva's public API in front of the CHEOPS Mission
Archive, through DACE's own client `dace-query` (GPL-3.0, the optional `[cheops]` extra). ESA does not designate
DACE; each output names the source that served it. DACE asks published material to include its acknowledgement
([dace.unige.ch/publications](https://dace.unige.ch/publications/)), reproduced below; no separate DACE terms-of-use
page was found.

**Licence of the data.** Data in the ESA Space Science Archives are distributed under the **CC BY-NC 3.0 IGO**
licence, and ESA's terms require prior authorisation (data.licences@esa.int) for any commercial use, including use
that indirectly generates financial gain. CHEOPS data and every output derived from them stay under those terms:
SetuHQ's CC BY 4.0 data licence does not apply to them, and **neither SetuHQ's commercial licence nor SetuHQ Pro
covers them**; a hosted, Pro or other commercial use of CHEOPS data through SetuHQ needs ESA's authorisation first
([LICENSING.md](../LICENSING.md), [NOTICE](../NOTICE), [PRO.md](PRO.md)).

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
`scripts/stellar_validation.py` (resumable per item; `--report` rebuilds the files). The CHEOPS-derived results
are in [results/stellar_validation_cheops.md](results/stellar_validation_cheops.md) and `.json`, under ESA's
CC BY-NC 3.0 IGO terms. The published values
are transcribed, with their sources, in [results/stellar_validation_references.json](results/stellar_validation_references.json).

Status under protocol v3 (`results/stellar_validation_protocol_v3.json`, committed on its own in b2ac54c before
its run; seed 20261022). Rule: validated when every counted check passes, partly validated when more than half do,
otherwise not validated. **Flares: partly validated (5 of 8 checks pass)**; the AU Mic null is a tuning-set result
and not counted. **Pulsations: partly validated (7 of 9 checks pass).** **CHEOPS: not validated (2 of 5 checks
pass)**, and the two Poyatos et al. comparisons are inconclusive because the CHEOPS gates fail. Two criteria were
relaxed after v1 (pooled Proxima ED bins; pycheops "or a lower rms") and one was tightened after v2 (false splits
judged on the Wilson upper bound); the status table marks each. v1 and the algorithms were revised during development
on these same targets, so v3 is a re-test after review fixes, not an independent validation. In short:

- **Flares, TESS.** AU Mic sector 1 is the tuning star. 36 of Günther et al.'s 46 flare components fall in a
  SetuHQ flare (0.78, 95% CI 0.64-0.88). The check needs 0.70 at the lower bound, so it fails. Our complex fraction
  is 0.42 against their 0.46, but this is a tuning-set result (the shape test was set on this star), not
  agreement. Amplitudes are 0.92× theirs.
- **Proxima Cen, sectors 11-12.** All 48 of our flares are in Medina et al.'s list. We recover 0.72 (0.58-0.83)
  of their flares with ED ≥ 3 s but only 0.40 overall.
- **Proxima energies.** TESS-band energies measured as Medina et al. measure them are 1.33× theirs (1.15-1.51), so
  the check fails as recorded. The main cause is the TESS magnitude. Medina et al.'s table implies
  L_TESS = 8.2 × 10²⁹ erg/s against our 9.29 × 10²⁹ (×1.13). Their Table 1 gives Tmag 7.49 where TIC v8.2 gives
  7.36. Swapping in their magnitude closes the luminosity gap to 0.3%; the distance (0.2%) and the zero point (the
  same) do not explain it. A luminosity-matched cross-check, which is labelled and not counted, gives 1.18×
  (1.02-1.34). What remains is the difference between the two data-summed EDs.
- **TIC 150359500.** 9000 K bolometric energies, computed as Günther et al. do, are 1.14× theirs (1.02-1.29).
- **False splits.** These are injected single flares that come back as two or more components, measured on stars
  that did not tune the rule. Proxima alone splits 0.17 of the time (0.10-0.27); Proxima and GJ 1243 pooled split
  0.12 of the time (0.08-0.19). The limit of 15% now applies to the upper bound, so the check fails. Like with
  like on the tuning star, AU Mic went from 0.41 before the fixes to 0.08 after them; neither is a validation
  number.
- **Merges.** Two-component flares injected on Proxima and GJ 1243 come back merged as one 0.33 of the time
  (0.26-0.42). The rate is 0.55 when the second peak is 5-10% of the first, which cannot be kept as a component by
  construction. It is 0.32 at 10-20% and 0.12 at 20-50%. This is reported only; the protocol sets no pass
  criterion.
- **Quiet stars.** There was 1 detection in 147 days.
- **Flares, CHEOPS (gated).** Amplitude and FWHM are now drawn once per injection.
  - The placed FWHM is still skewed short: 28% of injections fall in 0.5-0.9 min and 12% in 5.5-10 min, against
    20% expected in each bin. 851 of 2352 injections found no position in the short CHEOPS visits: 13%, 22%, 34%, 50%
    and 62% of those drawn in the five bins from shortest to longest. In v2 the skew was 60% against 23% expected.
  - With the fairer mix, bright injected flares (S/N ≥ 10, FWHM ≥ 3 cadences) are recovered 0.51 of the time
    (0.46-0.56), down from v2's 0.73. Of the long flares among them (FWHM 5.5-10 min), 24 of 111 are recovered. The
    v2 gate was flattered by the short-flare skew. The gate is conditional on placement: it measures recovery of
    the flares that fit in a stretch. With equal weight per log-FWHM bin it is 0.51 as well, so it fails either way.
  - The masked inverted null finds 7 events against 47 flares (0.15).
  - Both gates fail. The Poyatos et al. comparisons are therefore reported as inconclusive: complex fraction 0.42
    against ~0.40; α 2.07 ± 0.22 against 1.92 ± 0.07; denoising +21% against +34%. The numbers are in
    [results/stellar_validation_cheops.md](results/stellar_validation_cheops.md).
- **Pulsations.**
  - β Pic sectors 5-7: all 54 of Zieba et al.'s frequencies are recovered within 3σ.
  - HR 10: we recover 95% of Salmon et al.'s frequencies in sector 2 and 74% in sector 29, including all of their
    10 strongest in both. Amplitudes agree within 10%. AR(1) surrogates give 0.6 false frequencies per light curve.
    A random frequency would be flagged as a combination 2-3% of the time.
  - HR 10's granulation frequency disagrees with Salmon et al.'s even with their estimator: 70 µHz against 151.
  - TOI-197: numax is 433 ± 6 µHz and Δν is 28.8 µHz, against Huber et al.'s 430 ± 18 and 28.94 ± 0.15.
- **CHEOPS.** On the same input our decorrelation matches pycheops, or reaches a lower rms where pycheops' fit is
  off the optimum. End to end, the DACE arrays and pycheops' DRP product differ (correlation 0.61-0.89). HR 10's
  two strongest δ Scuti frequencies are found in the three public CHEOPS visits together.

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

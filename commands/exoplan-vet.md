---
description: Vet a TESS target or a light curve for a transit with SetuHQ's own search, vetting, fit and false-alarm probability, via the exoplan MCP server
argument-hint: "[a TIC id and sector, a CSV light curve under the data root, or a candidate id, e.g. 'TIC 261136679 sector 1']"
---

# Vet a TESS target or a light curve

The user wants to know whether a light curve holds a transit-like signal and whether it survives
vetting. Use **SetuHQ's own code** through the `exoplan` Model Context Protocol (MCP) server; do not
estimate depths, periods or false-alarm probabilities yourself.

Request: **$ARGUMENTS**

Do this:

1. Pick the input.
   - A candidate id from a stored run: **`get_candidate`** (it already holds the vetting, the fit and the FAP).
   - A CSV light curve (columns `time`, `flux`, optional `flux_err`) under the data root, or arrays the
     user pasted: go to step 2.
   - A TIC id and sectors: **`run_pipeline_tess`** downloads the SPOC light curve from MAST and runs the
     whole pipeline (Probes only unless the user asks for Sentinels). It writes a run directory: say where
     before you call it. Then use **`list_candidates`** and **`get_candidate`** on that run.
2. Call **`vet_lightcurve`**. Without a window it vets the strongest periodic signal's first transit; with
   `t_start` and `t_end` it vets that dip. Report `passed`, each flag with its meaning, the SNR and depth.
3. Call **`fit_transit`** on the vetted dip (pass `teff` and `logg` if the star is in the catalogue:
   **`get_star`**). Report depth, T14, b and ρ★ with their errors.
4. Call **`compute_fap`** with at most 200 trials unless the user asks for more (the tool caps it at 2000).
   Quote `fap_label` as it is: with no trial above the signal it is an upper bound, never a value.
5. Report with the provenance line (code version, input SHA-256) and keep every honesty label. Call it a
   **candidate**, never a discovery or a planet. Say what would rule it out (odd/even depths, a secondary
   eclipse, a V shape, a density mismatch) and that confirmation needs follow-up by others.
6. Do not post, submit or send anything anywhere. If the user wants to share the result, give them the
   report and let them decide.

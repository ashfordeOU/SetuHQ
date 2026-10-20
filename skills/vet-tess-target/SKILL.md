---
name: vet-tess-target
description: Vet a TESS target or light curve for a transit with SetuHQ's own BLS search, vetting, limb-darkened fit and bounded false-alarm probability. Use when the user asks whether a star or light curve shows a planet-like dip, or asks to check a TIC, a sector or a CSV.
---

# Vet a TESS target

Use the `exoplan` MCP server's `vet_lightcurve`, `fit_transit`, `compute_fap`, `run_pipeline_tess`,
`list_candidates`, `get_candidate` and `get_star`. See `/exoplan-vet` for the step list.

Rules that apply every time:

- Numbers come from tool results only. Never estimate a depth, a period, an SNR or a FAP yourself.
- Quote the FAP as its `fap_label`. With no bootstrap trial above the signal it is an upper bound,
  `< 1/(N + 1)`, not a value; the Gumbel tail is indicative and labelled so.
- A flag is evidence, not a verdict: `odd_even_mismatch` and `secondary_eclipse` point to an eclipsing
  binary; `edge_event` only says look twice; a V shape or a density mismatch from the fit argues against a
  planet around this star.
- Ask before a tool that writes a run directory (`run_pipeline_tess`, `run_pipeline_csv`), and run Probes
  only unless the user asks for Sentinels.
- Call the result a **candidate**. It is not a discovery; confirmation needs follow-up observations by
  others. Keep the honesty labels the tools return.
- Never post, submit or send anything. The user decides what is shared.

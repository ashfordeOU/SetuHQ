---
description: Explain one SetuHQ candidate in plain words, from its stored vetting, fit, false-alarm probability and every reviewer's verdict, via the SetuHQ MCP server
argument-hint: "[a candidate id, e.g. 'tess-fa3483ce6f83-000', or 'the best candidate of runs/tess-pi-men-s1']"
---

# Explain a candidate

The user wants to understand one candidate: what was seen, who marked it, how it was checked and how far
to trust it. Read it from the `setuhq` MCP server; do not reconstruct it.

Request: **$ARGUMENTS**

Do this:

1. If no id is given, call **`list_candidates`** (default run `runs/tess-pi-men-s1`) and pick the one the
   user means; say which you picked.
2. Call **`get_candidate`**. It returns the stored candidate, the run's provenance and every reviewer's
   stored classification of that subject.
3. Explain, in this order and from those values only:
   - the dip: time, depth (ppm), duration (hours), SNR, and the period if a periodic signal covers it;
   - the panel: how many reviewers marked it. **Sentinels** are AI models (provider and model are in
     `run.sentinels`; say which), **Probes** are deterministic detectors; none are people. Quote a
     Sentinel's stored rationale if it helps;
   - the checks: passed or not, each flag in plain words, the transit fit (depth, T14, b, ρ★ against the
     catalogue density) and the FAP exactly as `fap_label` gives it;
   - the archive: if the star is in the catalogue (**`get_star`**), whether a known planet has this period.
4. Say how far to trust the panel with **`benchmark_results`** (`real_tois` for completeness and false
   alarms on real TOIs; `weights` for the calibration). Only Claude has been benchmarked as a Sentinel.
5. Keep every honesty label. A candidate is not a discovery; a known planet recovered is a recovery.

---
description: Report how well SetuHQ's reviewer panel and pipeline perform, from the stored benchmarks (real TOIs, injection-recovery, pi Men validation, calibration), via the exoplan MCP server
argument-hint: "[what to check, e.g. 'completeness on real TOIs', 'how independent are the Sentinels', 'which providers can run here']"
---

# What the benchmarks say

Request: **$ARGUMENTS**

Do this:

1. Call **`benchmark_results`** with the one that answers the question: `real_tois` (the blind benchmark on
   real TOIs, held-out half, with inverted and scrambled controls and the Sentinels' stated subsample),
   `injection` (the Probes on synthetic transits), `pi_men_validation`, `weights` (the calibrated weights and
   the rates and sample sizes behind them) or `threshold_sweep`.
2. Quote rates with their sample sizes and intervals as stored. Do not round a small sample into a claim.
3. On the Sentinels: only Claude has been benchmarked. The two Claude personas agree with φ ≈ 0.89 on the
   40-star subsample, so they count as about one voter. Other providers are supported
   (**`sentinel_providers`**), but they have not been measured; an uncalibrated provider votes at the floor
   weight. `scripts/benchmark_real_tois.py sentinels --panel <config>` measures cross-provider φ when keys
   are present.
4. Keep the honesty labels; say what each benchmark does not test.

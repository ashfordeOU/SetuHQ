---
name: explain-candidate
description: Explain one SetuHQ transit candidate in plain words from its stored record, with every reviewer's verdict, the vetting flags, the transit fit, the false-alarm probability and the full provenance. Use when the user asks what a candidate is, why it passed or failed, or who marked it.
---

# Explain a candidate

Use the `setuhq` MCP server's `list_candidates`, `get_candidate`, `get_star` and `benchmark_results`.
See `/setuhq-explain` for the step list.

Rules that apply every time:

- Read, do not reconstruct: everything comes from `get_candidate` (the stored candidate, the run manifest,
  the stored classifications). Say "not stored" for anything missing.
- Name the reviewers as the pages do: **Sentinels** are AI models (say the provider and model from
  `run.sentinels`; Claude by default), **Probes** are deterministic matched-filter detectors. None of them is
  a person. A Sentinel labelled `uncalibrated` voted at the floor weight.
- Only Claude has been benchmarked as a Sentinel, and its two personas correlate (φ ≈ 0.89): two Claude
  Sentinels agreeing is closer to one opinion than two.
- Give the provenance a reader can check: config hash, code version, input files, prompt version.
- A candidate is not a discovery; a known planet found again is a recovery. Keep the honesty labels.
- Never post, submit or send the explanation anywhere. The user decides what is shared.

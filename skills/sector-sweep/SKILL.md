---
name: sector-sweep
description: Run SetuHQ's full transit pipeline on TESS targets in a sector (or on CSV light curves) and summarise the candidates, the vetting and the skipped reviewers. Use when the user asks to search, sweep or scan one or more TESS stars or a sector.
---

# Run a sector sweep

Use the `exoplan` MCP server's `run_pipeline_tess`, `run_pipeline_csv`, `sentinel_providers`,
`list_candidates` and `get_candidate`. See `/exoplan-sweep` for the step list.

Rules that apply every time:

- State the plan (targets, sectors, a new run name under `runs/mcp/`, panel) and get a yes before the first run: each run
  writes a directory and downloads data from MAST.
- Probes only by default. Sentinels only when the user asks; they then may call a paid AI API, and only
  where its key is in the environment. Never ask the user to paste a key into the chat or a file.
- Report skipped reviewers with their reasons (from the manifest), and say that a tool run uses uniform
  weights, not the calibrated ones.
- Keep a sweep small unless the user says otherwise; one TESS sector of one star is minutes, a FAP with
  many trials is longer.
- Everything found is a candidate. Do not post, submit or send any of it.

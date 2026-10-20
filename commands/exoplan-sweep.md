---
description: Run SetuHQ's pipeline on a TESS target and sector (or a CSV light curve) and summarise the candidates it finds, via the exoplan MCP server
argument-hint: "[TIC ids and a sector, e.g. 'TIC 261136679, sector 1', or a CSV path under the data root]"
---

# Run a sector sweep

The user wants SetuHQ's full pipeline (prepare, blind subjects, reviewer panel, consensus, vetting, fit,
FAP) run on one or more targets. Use the `exoplan` MCP server.

Request: **$ARGUMENTS**

Do this:

1. Confirm the plan before running, in one line: the targets, the sector(s), the run name (`runs/mcp/<run_name>`), and the panel. The tools run **Probes only** by default. Run Sentinels (`sentinels: true`) only
   if the user asks: they then run only where a provider's key, SDK or CLI is present, and a paid API may be
   called. **`sentinel_providers`** says which can run here, without showing any key.
2. For each target call **`run_pipeline_tess`** (`tic`, `sectors`, a new `run_name`; the run goes to `runs/mcp/<run_name>`, never over an existing directory), or **`run_pipeline_csv`** for
   a CSV. A TESS download needs network access and lightkurve; if the tool says it is missing, say so.
3. Summarise each run: subjects, classifications, consensus dips and how many passed vetting, and the
   skipped reviewers with their reasons. List the passing candidates (id, time, depth, period, flags, FAP
   label). Uniform weights are used in a tool run; say so.
4. Offer **`get_candidate`** or `/exoplan-explain` for any of them.
5. Everything found is a **candidate**, not a discovery. Do not post, submit or send any of it; the user decides what to share.

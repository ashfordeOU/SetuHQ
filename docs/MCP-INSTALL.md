# Install the SetuHQ MCP server (setuhq-mcp)

> Candidates, not discoveries: every tool answer carries its provenance and honesty labels; keep them.
> The server runs on your computer. Nothing is sent to Ashforde OÜ, and no tool calls a paid AI API
> unless you ask it to run Sentinels and that provider's key is in your environment.

`setuhq-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server. Your assistant runs
SetuHQ's own code and reads its stored, reviewed results instead of guessing them. Each of its 16 tools is
a thin wrapper over a public function in [`src/setuhq/tools.py`](../src/setuhq/tools.py); the server holds
no logic of its own. The command is renamed `setuhq-mcp` at release.

## Install

From a checkout of this repository (Python 3.10 or later):

```sh
python -m venv .venv
.venv/bin/pip install -e '.[mcp]'        # adds the official MCP SDK; '.[mcp,tess]' also lets it download TESS data
.venv/bin/setuhq-mcp --list-tools       # check: prints the 16 tool names
```

Clients start the server themselves, usually without your virtual environment, so the snippets below use the
**absolute path** of `setuhq-mcp`. Replace `/path/to/SetuHQ` with your checkout. `SETUHQ_ROOT` is the data
root (the stored runs, the catalogue, the benchmarks); every path a tool reads or writes must be inside it.
It defaults to the checkout the package was installed from, so you can leave it out for an editable install.

| Channel | Command | Requires |
|---|---|---|
| Claude Code | `claude mcp add setuhq -- /path/to/SetuHQ/.venv/bin/setuhq-mcp` | the install above |
| Claude Code plugin | `/plugin install setuhq --marketplace ashfordeOU/SetuHQ` (or `/plugin marketplace add ashfordeOU/SetuHQ`, then `/plugin install setuhq@setuhq`) | `setuhq-mcp` on PATH |
| Claude Desktop | `claude_desktop_config.json`, below | the install above |
| Cursor | `~/.cursor/mcp.json`, below | the install above |
| VS Code | `.vscode/mcp.json`, below | the install above |
| Codex CLI | `codex mcp add setuhq -- /path/to/SetuHQ/.venv/bin/setuhq-mcp` | the install above |
| Gemini CLI | `gemini mcp add setuhq /path/to/SetuHQ/.venv/bin/setuhq-mcp` | the install above |
| Remote (streamable HTTP) | `setuhq-mcp --http 8080`, then `http://127.0.0.1:8080/mcp` (read-only tools unless `--allow-writes`) | your own host |

## Each client's configuration

### Claude Code

Where: run in a terminal (add `--scope user` for every project).

```sh
claude mcp add setuhq --env SETUHQ_ROOT=/path/to/SetuHQ -- /path/to/SetuHQ/.venv/bin/setuhq-mcp
```

Or as a plugin, with the slash commands and skills. The plugin declares the server once, in
`.claude-plugin/plugin.json` (the repository has no separate `.mcp.json`, so the two cannot clash):

```
/plugin install setuhq --marketplace ashfordeOU/SetuHQ
```

On an older Claude Code: `/plugin marketplace add ashfordeOU/SetuHQ`, then `/plugin install setuhq@setuhq`.
The plugin starts `setuhq-mcp` from your PATH, with the plugin's own copy of the repository as its data root.

### Claude Desktop

Where: `claude_desktop_config.json` (Settings, Developer, Edit Config).

```json
{
  "mcpServers": {
    "setuhq": {
      "command": "/path/to/SetuHQ/.venv/bin/setuhq-mcp",
      "args": [],
      "env": { "SETUHQ_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

### Cursor

Where: `~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project).

```json
{
  "mcpServers": {
    "setuhq": {
      "command": "/path/to/SetuHQ/.venv/bin/setuhq-mcp",
      "args": [],
      "env": { "SETUHQ_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

### VS Code

Where: `.vscode/mcp.json`. Or `code --add-mcp` with the same object plus a `name`.

```json
{
  "servers": {
    "setuhq": {
      "type": "stdio",
      "command": "/path/to/SetuHQ/.venv/bin/setuhq-mcp",
      "args": [],
      "env": { "SETUHQ_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

### Codex CLI

Where: run in a terminal, or `~/.codex/config.toml`.

```sh
codex mcp add setuhq --env SETUHQ_ROOT=/path/to/SetuHQ -- /path/to/SetuHQ/.venv/bin/setuhq-mcp
```

```toml
[mcp_servers.setuhq]
command = "/path/to/SetuHQ/.venv/bin/setuhq-mcp"
args = []
env = { SETUHQ_ROOT = "/path/to/SetuHQ" }
```

### Gemini CLI

Where: `~/.gemini/settings.json`, or `gemini mcp add`.

```json
{
  "mcpServers": {
    "setuhq": {
      "command": "/path/to/SetuHQ/.venv/bin/setuhq-mcp",
      "args": [],
      "env": { "SETUHQ_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

```sh
gemini mcp add -e SETUHQ_ROOT=/path/to/SetuHQ setuhq /path/to/SetuHQ/.venv/bin/setuhq-mcp
```

## The tools

| Tool | What it does | Wraps |
|---|---|---|
| `search_catalogue` | Find planets and stars by name, alternate name (a TIC id) or discovery method | `catalogue.catalogue_filter` |
| `get_planet` | One planet's stored record and its host's | the catalogue |
| `get_star` | A host star and every catalogued planet around it | the catalogue |
| `list_candidates` | A stored run's consensus dips, passed or not, with flags | `candidates.json` |
| `get_candidate` | One dip with full provenance: vetting, fit, FAP, each reviewer's verdict, provider and model | the run directory |
| `vet_lightcurve` | BLS search and vetting of a dip (SNR, duration, edges, odd/even, secondary eclipse) | `search.bls_search`, `vet.vet_event` |
| `fit_transit` | The limb-darkened transit fit: depth, T14, b, mid-time, Rp/R★, ρ★, with errors | `transitfit.fit_transit` |
| `compute_fap` | The bounded block-bootstrap false-alarm probability (at most 2,000 trials a call) | `search.false_alarm_probability` |
| `run_pipeline_csv` | The full pipeline on a CSV light curve, into a new `runs/mcp/<run_name>` (Probes only by default) | `pipeline.run_pipeline` |
| `run_pipeline_tess` | The full pipeline on a TIC and sectors from MAST; needs network and `.[tess]` | `loaders.load_tess`, `pipeline.run_pipeline` |
| `rv_semi_amplitude` | Radial-velocity K | `methods.rv_semi_amplitude` |
| `transit_depth` | Central-transit depth, geometric and limb-darkened | `methods.transit_flux` |
| `microlensing_magnification` | Point-lens A(u) | `methods.paczynski` |
| `habitable_zone` | Kopparapu et al. 2014 edges in AU | `methods.hz_distance_au` |
| `benchmark_results` | The stored benchmarks: real TOIs, the real-TOI leaderboard, injection-recovery, pi Men, calibration, threshold sweep | `docs/results/`, `docs/leaderboard/`, `docs/threshold_sweep.json` |
| `sentinel_providers` | Which Sentinel providers can run here (never shows a key) | `reviewers` |
| `find_flares` | Stellar flares in a light curve: detection (optional wavelet denoising), template morphology with multi-component fits chosen by BIC, ED, energies (9000 K blackbody) and the flux-inverted null | `flares.detect_flares` |
| `pulsation_spectrum` | Frequency analysis: pre-whitening to S/N 4, combination flags, granulation background, numax/Δν, a heuristic type and an optional red-noise null | `pulsations.analyse` |
| `get_cheops_lightcurve` | Public CHEOPS DRP light curves of a target (DACE public mode), detrended against roll angle, background and centroid, with ESA's acknowledgement and credit; needs network and `.[cheops]` unless cached (writes the cache, so over HTTP only with `--allow-writes`) | `cheops.get_cheops_lightcurve` |

Every tool returns `{"tool", "result", "provenance", "honesty"}`. Error messages give paths relative to the
data root, never the server's absolute paths.

Only the two `run_pipeline_*` tools write, and only into a **new** directory `runs/mcp/<run_name>`: a name
that is not a plain name, or a directory that already exists, is refused, so a tool can never overwrite a
stored, reviewed run (such as `runs/tess-pi-men-s1`) or anything else in the data root. They reach outside
this computer: `run_pipeline_tess` downloads from MAST, and with `sentinels: true` a run may call a provider's
paid API with the server's keys. Not exposed as tools (use the command line, where a person runs them): the
ExoFOP-style export (`setuhq export`), and scoring a leaderboard submission (`setuhq leaderboard`).

## Remote use

`setuhq-mcp --http 8080` serves streamable HTTP at `http://127.0.0.1:8080/mcp`, for a client that cannot
start a local process. It is for self-hosting, and it has **no authentication** of its own, so it is locked
down by default:

| Flag | Effect |
|---|---|
| `--http PORT` or `--http HOST:PORT` | binds to `127.0.0.1` unless you name another host; keep it there, or behind your own authenticating proxy |
| (default) | read-only tools only: the catalogue, stored runs, vetting, the fit, the FAP, the physics, the benchmarks |
| `--allow-writes` | adds `run_pipeline_csv` and `run_pipeline_tess` (each creates a new `runs/mcp/<run_name>`), Probes only |
| `--allow-sentinels` | with `--allow-writes`: lets a run use Sentinels, which may spend the server's AI-provider keys |

Over stdio the server is your own process and every tool is there (a pipeline run still uses Probes unless
the call asks for Sentinels). Ashforde OÜ does not run a public endpoint.

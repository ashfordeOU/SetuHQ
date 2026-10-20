# Install the SetuHQ MCP server (exoplan-mcp)

> Candidates, not discoveries: every tool answer carries its provenance and honesty labels; keep them.
> The server runs on your computer. Nothing is sent to Ashforde OÜ, and no tool calls a paid AI API
> unless you ask it to run Sentinels and that provider's key is in your environment.

`exoplan-mcp` is a [Model Context Protocol](https://modelcontextprotocol.io) server. Your assistant runs
SetuHQ's own code and reads its stored, reviewed results instead of guessing them. Each of its 16 tools is
a thin wrapper over a public function in [`src/exoplan/tools.py`](../src/exoplan/tools.py); the server holds
no logic of its own. The command is renamed `setuhq-mcp` at release.

## Install

From a checkout of this repository (Python 3.10 or later):

```sh
python -m venv .venv
.venv/bin/pip install -e '.[mcp]'        # adds the official MCP SDK; '.[mcp,tess]' also lets it download TESS data
.venv/bin/exoplan-mcp --list-tools       # check: prints the 16 tool names
```

Clients start the server themselves, usually without your virtual environment, so the snippets below use the
**absolute path** of `exoplan-mcp`. Replace `/path/to/SetuHQ` with your checkout. `EXOPLAN_ROOT` is the data
root (the stored runs, the catalogue, the benchmarks); every path a tool reads or writes must be inside it.
It defaults to the checkout the package was installed from, so you can leave it out for an editable install.

| Channel | Command | Requires |
|---|---|---|
| Claude Code | `claude mcp add exoplan -- /path/to/SetuHQ/.venv/bin/exoplan-mcp` | the install above |
| Claude Code plugin | `/plugin install exoplan --marketplace ashfordeOU/SetuHQ` (or `/plugin marketplace add ashfordeOU/SetuHQ`, then `/plugin install exoplan@setuhq`) | `exoplan-mcp` on PATH |
| Claude Desktop | `claude_desktop_config.json`, below | the install above |
| Cursor | `~/.cursor/mcp.json`, below | the install above |
| VS Code | `.vscode/mcp.json`, below | the install above |
| Codex CLI | `codex mcp add exoplan -- /path/to/SetuHQ/.venv/bin/exoplan-mcp` | the install above |
| Gemini CLI | `gemini mcp add exoplan /path/to/SetuHQ/.venv/bin/exoplan-mcp` | the install above |
| Remote (streamable HTTP) | `exoplan-mcp --http 127.0.0.1:8080`, then `http://127.0.0.1:8080/mcp` | your own host |

## Each client's configuration

### Claude Code

Where: run in a terminal (add `--scope user` for every project).

```sh
claude mcp add exoplan --env EXOPLAN_ROOT=/path/to/SetuHQ -- /path/to/SetuHQ/.venv/bin/exoplan-mcp
```

Inside this repository nothing is needed: its `.mcp.json` declares the server, and Claude Code offers to
enable it. As a plugin, with the slash commands and skills below:

```
/plugin install exoplan --marketplace ashfordeOU/SetuHQ
```

On an older Claude Code: `/plugin marketplace add ashfordeOU/SetuHQ`, then `/plugin install exoplan@setuhq`.
The plugin starts `exoplan-mcp` from your PATH, with the plugin's own copy of the repository as its data root.

### Claude Desktop

Where: `claude_desktop_config.json` (Settings, Developer, Edit Config).

```json
{
  "mcpServers": {
    "exoplan": {
      "command": "/path/to/SetuHQ/.venv/bin/exoplan-mcp",
      "args": [],
      "env": { "EXOPLAN_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

### Cursor

Where: `~/.cursor/mcp.json` (or `.cursor/mcp.json` in a project).

```json
{
  "mcpServers": {
    "exoplan": {
      "command": "/path/to/SetuHQ/.venv/bin/exoplan-mcp",
      "args": [],
      "env": { "EXOPLAN_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

### VS Code

Where: `.vscode/mcp.json`. Or `code --add-mcp` with the same object plus a `name`.

```json
{
  "servers": {
    "exoplan": {
      "type": "stdio",
      "command": "/path/to/SetuHQ/.venv/bin/exoplan-mcp",
      "args": [],
      "env": { "EXOPLAN_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

### Codex CLI

Where: run in a terminal, or `~/.codex/config.toml`.

```sh
codex mcp add exoplan --env EXOPLAN_ROOT=/path/to/SetuHQ -- /path/to/SetuHQ/.venv/bin/exoplan-mcp
```

```toml
[mcp_servers.exoplan]
command = "/path/to/SetuHQ/.venv/bin/exoplan-mcp"
args = []
env = { EXOPLAN_ROOT = "/path/to/SetuHQ" }
```

### Gemini CLI

Where: `~/.gemini/settings.json`, or `gemini mcp add`.

```json
{
  "mcpServers": {
    "exoplan": {
      "command": "/path/to/SetuHQ/.venv/bin/exoplan-mcp",
      "args": [],
      "env": { "EXOPLAN_ROOT": "/path/to/SetuHQ" }
    }
  }
}
```

```sh
gemini mcp add -e EXOPLAN_ROOT=/path/to/SetuHQ exoplan /path/to/SetuHQ/.venv/bin/exoplan-mcp
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
| `run_pipeline_csv` | The full pipeline on a CSV light curve; writes a run directory (Probes only by default) | `pipeline.run_pipeline` |
| `run_pipeline_tess` | The full pipeline on a TIC and sectors from MAST; needs network and `.[tess]` | `loaders.load_tess`, `pipeline.run_pipeline` |
| `rv_semi_amplitude` | Radial-velocity K | `methods.rv_semi_amplitude` |
| `transit_depth` | Central-transit depth, geometric and limb-darkened | `methods.transit_flux` |
| `microlensing_magnification` | Point-lens A(u) | `methods.paczynski` |
| `habitable_zone` | Kopparapu et al. 2014 edges in AU | `methods.hz_distance_au` |
| `benchmark_results` | The stored benchmarks: real TOIs, injection-recovery, pi Men, calibration, threshold sweep | `docs/results/` |
| `sentinel_providers` | Which Sentinel providers can run here (never shows a key) | `reviewers` |

Every tool returns `{"tool", "result", "provenance", "honesty"}`. Only the two `run_pipeline_*` tools write
(a run directory under the data root), and only `run_pipeline_tess` reaches the network. Not on this branch,
so not exposed: an export to ExoFOP, and scoring of a leaderboard submission.

## Remote use

`exoplan-mcp --http 127.0.0.1:8080` serves the same tools over streamable HTTP at `/mcp`, for a client that
cannot start a local process. It is for self-hosting: it has no authentication of its own, so keep it on
localhost or behind your own authenticating proxy. Ashforde OÜ does not run a public endpoint.

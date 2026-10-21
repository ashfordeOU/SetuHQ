<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Getting setuhq-mcp listed: owner steps

Everything here needs an account or a form that only the owner (the `ashfordeOU` GitHub account, for
Ashforde OÜ) can use. Nothing in the repository submits or publishes anything to a directory by itself.

Wording for every listing:

> SetuHQ's MCP server: search, vet and explain transit candidates in public NASA TESS data, with
> provenance on every answer. The server runs on your computer; nothing is sent to Ashforde OÜ. What an
> assistant finds with it is a candidate, never a confirmation.

The files that describe the server:

| File | For | Version kept in step by |
|---|---|---|
| [`server.json`](../../server.json) | the official MCP registry | `scripts/check_version_sync.py` |
| [`README.pypi.md`](../../README.pypi.md) | the PyPI page; carries the `mcp-name:` ownership marker | `scripts/check_version_sync.py` (marker equals `server.json` name) |
| [`smithery.yaml`](../../smithery.yaml) | Smithery, as a local stdio server | `scripts/check_version_sync.py` |
| [`glama.json`](../../glama.json) | Glama, the maintainer claim | (no version) |
| [`.claude-plugin/`](../../.claude-plugin/) | the Claude Code plugin and marketplace | `scripts/check_version_sync.py` |
| [`server.schema.json`](server.schema.json) | a copy of the registry's schema, `2025-12-11` | `tests/test_release.py` validates `server.json` against it |

`server.schema.json` is copied unchanged from
<https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json> (the registry project,
modelcontextprotocol/registry, MIT licence), so the check runs offline. When the registry publishes a
newer schema, replace the copy and the `$schema` line of `server.json` together.

## A. The official MCP registry (no account action)

1. Release the version to PyPI first (docs/RELEASING.md). The registry refuses an entry whose PyPI package
   does not exist at that version, or whose PyPI description lacks
   `mcp-name: io.github.ashfordeOU/setuhq` (README.pypi.md carries it in an HTML comment, which PyPI keeps
   in the raw description the registry reads).
2. Actions, then **Publish to the MCP registry** (`.github/workflows/mcp-publish.yml`), **Run workflow**
   on the release tag `vX.Y.Z`, first with `dry_run` on: it validates `server.json` against the schema and
   checks PyPI. Then run it again with `dry_run` off.
3. It logs in with GitHub OIDC (`mcp-publisher login github-oidc`): the registry gives the
   `io.github.ashfordeOU/*` namespace to workflows of the `ashfordeOU` account. No secret is needed.
4. Check the entry: <https://registry.modelcontextprotocol.io/v0/servers?search=io.github.ashfordeOU/setuhq>.
   The GitHub MCP Registry and the VS Code MCP gallery read the official registry; no separate submission.

**Known gap in the launch command.** The registry describes a PyPI package by name, and a client that
starts it through `uvx` runs the command named like the package, `setuhq`, which is the CLI and not the
server. `setuhq-mcp` is a second command of the same package, and the server needs the `mcp` extra. Until
the CLI gains a `setuhq mcp` subcommand (then `server.json` can say `"packageArguments": [{"type":
"positional", "value": "mcp"}]`), the entry names the right command in its publisher-provided metadata
(`_meta`: `uvx --from 'setuhq[mcp]' setuhq-mcp`), and every client snippet in
[docs/MCP-INSTALL.md](../../docs/MCP-INSTALL.md) starts `setuhq-mcp` directly. Decide this before the
first registry publish.

## B. Smithery (smithery.ai)

1. Sign in at <https://smithery.ai> with the GitHub account `ashfordeOU`.
2. New server, pick the repository `ashfordeOU/SetuHQ`. Smithery reads `smithery.yaml` at the repository
   root: a **local (stdio) server** started with `uvx --from setuhq[mcp]==<version> setuhq-mcp`, with an
   optional `setuhqRoot` setting (the data root, `SETUHQ_ROOT`).
3. Publish it as a local listing. **Do not choose a hosted or deployed option:** nothing of SetuHQ is
   hosted for it, and the listing must keep saying that the server runs on the user's computer.
4. Paste the wording above into the description. Check that the tool list shows the 16 tools.

## C. Glama (glama.ai)

1. Glama indexes public MCP repositories by itself. Once `ashfordeOU/SetuHQ` is listed, sign in with
   GitHub as `ashfordeOU`, open the server page and **Claim** it. Glama reads `glama.json` (maintainer
   `ashfordeOU`) and rescans.
2. If its score card asks for a Dockerfile, there is none on purpose: the server is a Python package
   started over stdio.

## D. Claude Code plugin directory

The plugin is `.claude-plugin/` (marketplace `setuhq`, plugin `setuhq`). Anyone can use it today with
`/plugin marketplace add ashfordeOU/SetuHQ`. To be listed in the official directory:

1. Run `claude plugin validate .` in the repository root and fix anything it reports.
2. Submit through the plugin directory's submission form (linked from the Claude Code plugin
   documentation), with the repository URL, the plugin name `setuhq`, the licence (AGPL-3.0-only, or a
   commercial licence from Ashforde OÜ) and the wording above. It needs the owner's Claude account.

## E. Others (optional)

Cursor, VS Code, Windsurf, Zed, Codex CLI and Gemini CLI need no listing; their snippets are in
[docs/MCP-INSTALL.md](../../docs/MCP-INSTALL.md). mcp.so and Docker's MCP catalogue take a form or a pull
request with the repository URL and the one-line description from `server.json`.

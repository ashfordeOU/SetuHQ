<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Security policy

## Reporting a vulnerability
Report it privately, by either route:

- **GitHub private vulnerability reporting**: the *Report a vulnerability* button on the
  repository's [Security tab](https://github.com/ashfordeOU/SetuHQ/security/advisories/new). The
  report is visible only to the maintainers, and a fix can be prepared in a private fork and
  published as a GitHub Security Advisory.
- **Email**: **contact@ashforde.org**, with details and steps to reproduce.

Please do not open a public issue for a security-sensitive report. We aim to acknowledge within a
few business days.

## Supported versions
Pre-1.0: only the latest commit of the default branch, and the latest tagged release once there is
one, are supported.

## What is in scope

- **Keys and tokens.** SetuHQ reads AI provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY`, or the variable an endpoint names) from the environment only and never writes
  them to a file, a manifest, a record or a log. A `base_url` that carries a credential is refused,
  error bodies are redacted (base64 forms of the key included), and `setuhq bundle` and
  `setuhq ingest` refuse a bundle in which anything looks like a key or token. A way to make any of
  these leak a key is a vulnerability.
- **The MCP server.** Over stdio it is the user's own process. Over HTTP (`setuhq-mcp --http`) it
  has **no authentication**: it binds to 127.0.0.1 by default and leaves out the tools that write
  (pipeline runs) unless `--allow-writes`, and Sentinels (which may call a paid API with the
  server's keys) unless `--allow-sentinels`. Every tool is confined to the data root
  (`SETUHQ_ROOT`). A way to read or write outside the data root, or to reach a writing tool without
  those flags, is a vulnerability. Exposing the HTTP server beyond your own machine without an
  authenticating proxy in front of it is unsupported.
- **Contribution bundles and the sweep catalogue.** Bundles are sealed, not signed (see
  [`CONTRIBUTING.md`](CONTRIBUTING.md)); `setuhq ingest` re-searches findings, and
  `setuhq check-sweep` with the append-only ingest ledger guards the catalogue. A way to get a
  forged entry past ingest and those checks is in scope.
- **The static site** (https://setuhq.com) loads no script or font from another site. A way to
  inject script through the data it renders (catalogue names, Sentinel text, contributor names) is
  in scope.

## Out of scope

- The scientific correctness of a candidate: report that as an ordinary issue. Every SetuHQ
  result is a candidate, never a confirmation.
- Vulnerabilities in dependencies with no SetuHQ-specific impact: report them upstream.

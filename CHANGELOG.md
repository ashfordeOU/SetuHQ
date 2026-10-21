<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Changelog

All notable changes to SetuHQ are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the project is pre-1.0, file formats and the command line may still change;
breaking changes are called out explicitly.

## [Unreleased]

## [0.1.0] - 2026-10-20

The first public release, under the name **SetuHQ** (*setu*, Sanskrit for bridge). Until this
release the code was developed privately as `exoplan`; the history before this entry is that
project's, and it is kept as it was.

### Changed

- **Renamed from exoplan to SetuHQ.** The Python package is `setuhq` (`src/setuhq`), the
  distribution `setuhq`, the command `setuhq` and the MCP server `setuhq-mcp`. The Claude Code
  plugin, its MCP server entry and its slash commands are `setuhq` and `/setuhq-…`
  (`/setuhq-vet`, `/setuhq-explain`, `/setuhq-sweep`, `/setuhq-catalogue`, `/setuhq-physics`,
  `/setuhq-benchmarks`). The data root is `SETUHQ_ROOT` and the ledger base `SETUHQ_BASE`. The
  repository is https://github.com/ashfordeOU/SetuHQ (the old `ashfordeOU/EXOPLAN` URL redirects)
  and the site is https://setuhq.com.
- **Compatibility kept on purpose:**
  - the `exoplan` and `exoplan-mcp` commands still work as deprecated aliases: each prints one line
    on stderr naming its replacement, then runs it unchanged. They will be removed in a later
    release. There is no `exoplan` import shim: `import exoplan` must become `import setuhq`;
  - `EXOPLAN_ROOT` and `EXOPLAN_BASE` are still read when the new variables are not set;
  - **data format names keep their `exoplan-` prefix** (`exoplan-sweep/1`,
    `exoplan-everything-that-dims/1`, `exoplan-contribution/2`, `exoplan-leaderboard/2`,
    `exoplan-leaderboard-inputs/1`, `exoplan-leaderboard-results/4`): they name schema versions,
    and the committed records, submissions and catalogues carry them;
  - a stored run's manifest from before the rename names its version `exoplan_version`; the pages
    and the MCP tools read it as `setuhq_version`;
  - committed results, the stored run and the archived catalogues are not renamed, and their
    numbers are not touched. Two pieces of display text in them were updated: the pre-fix note now
    reads "Pre-fix code: made with SetuHQ (then called exoplan) up to commit 5a03087" in the code and
    in every stored copy (no fingerprint or ledger covers those files' bytes; the README manifest that
    hashes the stored run was regenerated), and the stored pi Men cross-match names
    `setuhq crossmatch`. The leaderboard's seeded submitters and the sweep's
    contributor credit keep the name `exoplan` they were written with.
- **Code fingerprints survive the rename.** A fingerprint hashes each file's path relative to the
  package and its canonical text: the leading SPDX header lines removed and the package name
  written as it was when the committed results were made (`setuhq`/`SetuHQ` as `exoplan`,
  `SETUHQ` as `EXOPLAN`; `setuhq.starsearch.canonical_source`). Files from before the rename have
  neither, so every committed fingerprint is unchanged and still verifies against its commit:
  the sector-1 sweep record's search code (`20a2c1b2…`, commit 0e87409) and classification code
  (`78b84333…`, the current rules), and the real-TOI benchmark's per-star code fingerprints
  (`14f6f4830a525d78` = 76de67d, `e4fe4c99663ccba8` = 40cceca). `scripts/benchmark_real_tois.py`
  hashes each file under the path it had then (`src/exoplan/…`) and reads old commits from either
  path. The benchmark's fingerprint of the current code is also unchanged (`0b8e86a1fb71e777`),
  and so is the classification fingerprint.
  **One value changes: the search fingerprint of the current code** (`ff5f2568…` before this
  release). `starsearch.py`, which holds the fingerprint function, is itself one of the fingerprinted
  search files, and the canonicalisation added to it is a change to that file's code. No committed
  file records the old value: the committed sweep record names the search code of 0e87409, which
  still verifies. The practical effect is that a sweep cache or a contribution bundle made with the
  pre-release code is treated as made by different search code (a fresh search, or a refused
  bundle), as for any other code change.
- **Licence: AGPL-3.0-only or a commercial licence from Ashforde OÜ** (was MIT), with SetuHQ's own
  data, benchmark, leaderboard data and paper under CC BY 4.0. See [`LICENSING.md`](LICENSING.md),
  [`NOTICE`](NOTICE), [`TRADEMARKS.md`](TRADEMARKS.md) and [`CLA.md`](CLA.md). Every source file
  carries an SPDX header. Every commit before this release was made by Ashforde OÜ's own account.
- **Workflows run on GitHub-hosted runners** (`ubuntu-latest`), not the self-hosted runner, with
  every action pinned to a full commit SHA (its tag in a comment). `pages.yml` deploys on pushes to
  `main` and on request.
- **The discovery batch runs only on request** (`workflow_dispatch`): its six-hourly schedule is
  removed, and any commit it makes is authored as ashfordeOU. Without an `ANTHROPIC_API_KEY`
  secret it runs the Probes only. Before it commits it rebuilds every page that embeds the feed's
  catalogue (the app and landing page, the plates, the dashboard; `setuhq discover` writes the
  feed page) and runs the fast tests, because its push does not start `ci.yml`.
- **The site serves from the domain root,** https://setuhq.com (`site/CNAME`), with the SetuHQ
  logo, favicon and social card, and title, description, canonical, Open Graph and Twitter card
  tags on every page. `pages.yml` deploys the committed `site/`.

### Added

- [`CITATION.cff`](CITATION.cff), [`codemeta.json`](codemeta.json),
  [`GOVERNANCE.md`](GOVERNANCE.md), [`SECURITY.md`](SECURITY.md),
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), [`ROADMAP.md`](ROADMAP.md) and this changelog.
- [`docs/PRO.md`](docs/PRO.md): SetuHQ Pro, **planned and not built**, and the README's Editions
  section (Free, SetuHQ Pro, Custom study). Every paid route starts with a message to
  contact@ashforde.org; there are no prices.

### Removed

- `scripts/session_runner.sh`, which registered a self-hosted Actions runner from a short-lived
  session with a repository-administration token. Hosted runners replace it, and a public
  repository should not route its pull requests to a self-hosted runner.

### What the release contains

Everything developed as exoplan, unchanged in behaviour by this release: the blind-coded panel
of AI Sentinels and deterministic Probes; limb-darkened transit fits, bounded false-alarm
probabilities and DV-style and pixel-level vetting; the reduced false-positive probability with
its stability gate; the ephemeris cone and ExoFOP-style export; the frozen 662-TOI benchmark with
controls, its leaderboard with a catalogue-metadata floor (which the Probes are not shown to beat)
and the methods paper draft; the pre-registered two-sector feed rule (the feed is still dominated
by false alarms); the everything-that-dims sweep with contribution bundles and the append-only
ingest ledger; Sentinels on several providers; the MCP server, the Claude Code plugin and an
example agent; and the app (Mission Control, Galaxy, the catalogue, fifteen Methods chapters, the
Docket and the Plates). The real-TOI benchmark, its leaderboard and the paper's numbers were
measured before the deep-dip clipping fix and have not been re-run.

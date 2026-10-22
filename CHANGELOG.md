<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Changelog

All notable changes to SetuHQ are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the project is pre-1.0, file formats and the command line may still change;
breaking changes are called out explicitly.

## [Unreleased]

### Added

- **DOI and PyPI.** The Zenodo concept DOI `10.5281/zenodo.23568348` (all versions) is in `CITATION.cff`
  (`doi`, `identifiers`), `codemeta.json` (`identifier`) and `paper/paper.bib`; the README has a PyPI badge
  (static, from `__version__`, so `tools/gen_readme_assets.py --check` stays offline) and a DOI badge, its
  install section leads with `pip install setuhq`, and its Cite section names the DOIs.

### Changed

- **Releases are automatic.** A version bump merged to `main` releases itself once CI is green:
  `auto-tag.yml` is now on by default (opt out with the variable `AUTO_TAG=false`), pushes the tag with the
  workflow's own token and then dispatches `release.yml` on the tag; no `RELEASE_TAG_TOKEN` is needed.
  `release.yml` runs the full release for any run whose ref is a tag, pushed or dispatched, with the same
  strict checks; a dispatch on a branch is still a dry run. A second run for a tag that is already released
  waits for the first (concurrency) and skips building and publishing. See
  [docs/RELEASING.md](docs/RELEASING.md).

## [0.1.0] - 2026-10-22

The first public release, under the name **SetuHQ** (*setu*, Sanskrit for bridge). Until this
release the code was developed privately as `exoplan`; the history before this entry is that
project's, and it is kept as it was.

### Changed

- **Every stored result that can be re-run without calling a Sentinel is re-run on the fixed code**
  (after the two fixes that change default results: `preprocess.clean` keeps deep dips, and `vet.py`'s
  odd/even test no longer fails clean deep planets). The first runs are kept beside the re-runs, each
  with the pre-fix note in its own file (`codenote.HISTORICAL`).
  - The stored pi Men run, from the start (`scripts/rerun_pi_men.py`): every dip, vetting result, fit
    and FAP equals the first run's (Rp/R★ 0.0179 ± 0.0017 and T14 3.07 ± 0.17 h against Huang et al.
    2018); the Sentinels' stored answers were reused because the subject images and prompts are
    byte-identical.
  - The real-TOI benchmark, all 662 TOIs, protocol unchanged (`benchmark_real_tois.py --edition
    clipfix`): held-out completeness 60% (90/150) against 57% (86/150), 5 stars gained and 1 lost
    (paired bootstrap 95% CI 0 to +6 points, McNemar p = 0.22); FP found 77% and flagged 68% as
    before; controls 641 and 861 vetted dips per 1,000 star-sectors (573 and 848 before).
  - The pre-registered feed rule, evaluated again unchanged: noise 6.1 (4.0–9.4) false signals per
    100 targets under it, 27.8 (23.1–33.1) under the old rule; feed-level completeness 17%.
  - Why the controls and FP rates moved: on the inverted control 16 of the 24 newly passing dips were
    rejected by the old odd/even test and 5 are deep inverted features the old cleaning deleted; 4 of the
    5 newly passing FP TOIs were rejected by the old odd/even test.
  - The calibration record's provenance is corrected: its Probe rates were measured on the code of
    2026-10-16 (03f23bd); since the limb-darkened injections (fbc1ed9) the same seed gives 0.9, 0.8 and
    0.6. The weights stay frozen; a test shows both sets make the same two-of-three decisions.
  - The threshold sweep's held-out score fell from 0.875 to 0.833 (2 of 48 injections at 1000 ppm), a
    change that came with the limb-darkened injections, not the two fixes: the sweep dates from 2026-10-16.
  - Each historical record's note now names its re-run instead of "Not re-run since".
  - The re-run's report adds a stale-ephemeris audit (one held-out CP/KP miss, TOI 1905.01: no dip on the
    published ephemeris, a comparable dip within 12 h and at least 3σ of the propagated ephemeris error off
    it) and the window-measurement limit; the matching rule is unchanged.
  - The live catalogue, the injection-recovery benchmark and the threshold sweep; the leaderboard
    (Probes J 0.35 against the metadata floor's 0.39, paired ΔJ +0.04, −0.10 to +0.17: still not
    shown to beat it) and the methods paper read the re-run.
  - The Sentinels were not asked again: their stored answers are used on the 37 of the 40 subsample
    stars whose subjects are byte-identical; the 3 others are left out.
- **No site-wide banner.** A page built from a record that carries a code note states it once, in
  plain language, at the top of that page; no page of the current site carries one.
- **`candidates.csv` and `candidates.json` carry 10 more columns** on runs made with the current code:
  `sector`, `crowdsap`, `secondary_phase`, `secondary_snr`, `centroid_offset_arcsec`, `centroid_sigma`, `fpp`,
  `nfpp`, `fpp_method` and `validation_label` (the extended-vetting and reduced-FPP results; the full records are
  under `metrics`). The stored pi Men run now has them: FPP 0.0186 and 0.0148 per subject, class "undetermined".
- The Docket's page data keeps only the metrics the page reads (the extended-vetting record per dip
  stays in `candidates.json`).

- **Python 3.11 or later.** `setuhq.config` reads TOML with `tomllib`, which the standard library has from
  3.11.

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
  path. The classification fingerprint is unchanged.
  **The fingerprints of the current code change.** The search fingerprint goes from `ff5f2568…` before
  this release to `f7317ec9…`: `starsearch.py`, which holds the fingerprint function, is itself one of the
  fingerprinted search files and gained the canonicalisation, and `transitfit.py` now reads its
  limb-darkening table from the package. For that second reason the real-TOI benchmark's fingerprint of
  the current code goes from `0b8e86a1fb71e777` to `b1bf1166c71abdff`. No committed file records an old
  value: the committed sweep record names the search code of 0e87409, and the benchmark names the
  per-star codes above, which all still verify. The benchmark's threshold audit at the results' own
  commit is unchanged and clean; it now also tracks the sha256 of the reference tables, and accepts the
  table's move into the package only as that exact change of `LD_TABLE`. It therefore records 114 values
  (the 113 before, plus the limb-darkening table's hash). The practical effect is that a sweep cache or a contribution bundle made with the
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

- `codemeta.json` names Ashforde OÜ as copyright holder.

- **Release machinery.** A `v*` tag runs `.github/workflows/release.yml`: it checks the tag against the
  version, this changelog and CI (a green push run on `main` for that commit, which `main` contains), builds
  the sdist and the wheel, runs `twine check`, checks what they carry, installs the wheel cleanly, attests
  build provenance, creates the GitHub Release with this changelog's section as notes, and uploads the same
  attested files to PyPI as `setuhq` by trusted publishing (no token). A re-run never replaces a file
  already on the release. `mcp-publish.yml` lists the server in the official MCP registry as
  `io.github.ashfordeOU/setuhq` by GitHub OIDC; `auto-tag.yml` is optional and off by default. The steps
  are in [docs/RELEASING.md](docs/RELEASING.md).
- **One version.** `__version__` in `src/setuhq/__init__.py` is the only place it is written for the
  package (pyproject reads it); `scripts/check_version_sync.py` fails when CITATION.cff, codemeta.json,
  .zenodo.json, server.json, smithery.yaml or the plugin manifests disagree, when the release date here
  differs from CITATION.cff's `date-released`, and, for a release tag, when `[Unreleased]` is not empty.
  `scripts/set_release_date.py` sets both dates on the release day.
- **The package runs without a checkout.** The two reference tables the pipeline reads, the Claret 2017
  limb-darkening coefficients and the secondary-eclipse calibration, ship in the package as
  `src/setuhq/data/claret2017_tess_quadratic.json` and `src/setuhq/data/secondary_calibration.json`, and
  `transitfit` and `dvtests` read them with `importlib.resources`. They are byte-identical copies of the
  canonical files in `docs/results/`; `tests/test_release.py` fails until a rewritten original is copied
  over. `setuhq run` from a plain `pip install "setuhq[tess]"` searches, vets and fits outside a checkout.
- **`setuhq mcp`** starts the MCP server over stdio, as `setuhq-mcp` does, and says which extra to install
  when the MCP SDK is missing. The MCP registry entry (`server.json`) launches it as
  `uvx --with=mcp>=1.10 setuhq==<version> mcp`.
- The package ships `py.typed`; its PyPI page is `README.pypi.md` (absolute links only). The exact versions
  the README figures need are in `requirements-readme.txt`, not in the package metadata.
- `examples/quickstart.ipynb`: the stored pi Men run offline, from candidates to an MCP tool call; a test
  runs it. `paper/` holds the JOSS paper; issue forms, a pull request template, Dependabot and
  `.editorconfig` are under `.github/` and at the root. CI also runs the fast tests on Python 3.11.

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

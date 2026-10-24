<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SetuHQ's public API: stable and internal

Code that uses SetuHQ as a library (a notebook, a service, SetuHQ Pro, a product under the commercial licence)
should import from **`setuhq.api`**. Its `__all__` is the stable surface; `tests/test_api.py` pins it.

## The promise

* A stable name keeps its name, its call signature and its documented behaviour across minor releases. Existing
  parameters keep their meaning; new parameters are keyword-only and have a default.
* A stable name is removed only after a release that deprecates it with a warning, and only in a later major
  release. While SetuHQ is 0.x, the next minor version (0.2 after 0.1) plays the part of a major release.
* Everything else in the package is **internal**: it may change in any release, without notice.

## Stable (`setuhq.api`)

| Group | Names | What |
| --- | --- | --- |
| Version | `__version__` | the installed version |
| Configuration | `RunConfig`, `load_config`, `build_reviewers` | a run's settings from a TOML file, and its reviewers from `[[reviewers]]` entries (a config file never holds a key) |
| The panel | `standard_probes()` | the three Probes of the standard panel, exactly as `configs/sweep.toml` lists them |
| Weights | `default_weights()`, `default_weights_path()`, `packaged_weights_path()`, `apply_calibration` | the calibrated reviewer weights: the checkout's `docs/results/reviewer_weights_full_panel.json`, else the copy the wheel ships; uncalibrated Sentinels get the floor weight |
| Reviewers | `SimulatedVolunteer` (a Probe), `ClaudeReviewer`, `OpenAIReviewer`, `OpenAICompatibleReviewer`, `GeminiReviewer`, `Secret` | each Sentinel takes `api_key=` (a string or a `Secret`) for a key passed per call; without one it reads its provider's environment variable. A key is never logged, cached, pickled or written to a manifest |
| Light curves | `LightCurve`, `load_tess`, `load_spoc_file`, `load_csv` | TESS from MAST, a SPOC file on disk, or your own photometry |
| The run | `run_pipeline`, `aggregate`, `fit_transit`, `transit_model` | search, review, consensus, vetting and the limb-darkened transit fit |
| Wording | `ATTRIBUTION`, `PROBES_ONLY`, `dip_state`, `dip_count` | the exact words every output uses: a dip is a candidate, never a confirmed planet |

## Internal

Everything not listed above, including: the site and its pages (`setuhq.site`, `setuhq.app`, `setuhq.viz`, the page
modules), the stand-alone outputs (`report`, `docket`, `plate`, `dashboard`), the sweep and its ledger, the MCP
server's tool layout, the CLI's arguments beyond those documented in the README, every module-level constant, and
anything whose name starts with `_`.

`setuhq.loaders.load_cheops` and the stellar commands stay out of the stable API: CHEOPS data are under ESA's terms
(CC BY-NC 3.0 IGO) and are never part of SetuHQ Pro or the commercial licence.

Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.

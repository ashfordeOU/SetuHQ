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
| Weights | `default_weights()`, `default_weights_path()`, `packaged_weights_path()`, `default_calibration()`, `apply_calibration` | the calibrated reviewer weights: the checkout's `docs/results/reviewer_weights_full_panel.json`, else the copy the wheel ships; uncalibrated Sentinels get the floor weight. `default_calibration()` is the calibration record next to that file (pass it as `run_pipeline(calibration=...)`). `packaged_only=True` (keyword-only, on `default_weights_path`, `default_weights` and `default_calibration`) reads the packaged copy only, whatever the current directory holds: for a service |
| Reviewers | `SimulatedVolunteer` (a Probe), `ClaudeReviewer`, `OpenAIReviewer`, `OpenAICompatibleReviewer`, `GeminiReviewer`, `Secret` | each Sentinel takes `api_key=` (a string or a `Secret`) for a key passed per call; without one it reads its provider's environment variable. With `env_fallback=False` (keyword-only, default `True`) it never reads one: built without `api_key=`, it is refused with a `ValueError` (a keyless OpenAI-compatible endpoint, and a Claude Sentinel given its own `client=`, need no key). A key is never logged, cached, pickled or written to a manifest |
| Sentinel facts | `PROVIDER_KEY_ENV`, `DEFAULT_SENTINEL_MODELS`, `Transport` | see [Sentinels](#sentinels) |
| Light curves | `LightCurve`, `load_tess`, `load_spoc_file`, `load_csv` | TESS from MAST, a SPOC file on disk, or your own photometry |
| The run | `run_pipeline`, `aggregate`, `fit_transit`, `transit_model`, `RunSummary`, `Candidate` | search, review, consensus, vetting and the limb-darkened transit fit; see [The run's results](#the-runs-results) |
| Wording | `ATTRIBUTION`, `PROBES_ONLY`, `dip_state`, `dip_count` | the exact words every output uses: a dip is a candidate, never a confirmed planet |
| Language | `use_lang`, `current_lang`, `SUPPORTED_LANGS`, `attribution_text()`, `probes_only_text()`, `dip_state_text()` | see [Language per call](#language-per-call) |
| Stellar | `find_flares`, `pulsation_spectrum`, `find_eclipsing_binary`, `rotation_period`, `find_transients`, `StellarResult`, `STELLAR_CAPABILITIES`, `stellar_validation_status` | see [Stellar capabilities](#stellar-capabilities) |
| Honesty labels | `HONESTY_LABELS`, `TRANSIENT_SEARCH_AID`, `TRANSIENTS_LABEL`, `BINARIES_LABEL`, `BINARIES_VETTING_NOTE`, `ROTATION_LABEL`, `STELLAR_DETECTION_LABEL`, `FLARE_ENERGY_LABEL` | see [Honesty labels](#honesty-labels) |

## The run's results

`run_pipeline` returns a `RunSummary` with these fields:

| Field | What |
| --- | --- |
| `run_dir` | the run directory (a `Path`) |
| `n_light_curves`, `n_subjects`, `n_classifications`, `n_consensus`, `n_passed` | counts: light curves read, subjects reviewed, classifications made, consensus dips, dips that passed vetting |
| `skipped_reviewers` | ids of the reviewers that were not available (no key, no SDK) |
| `candidates` | the consensus dips, each a `Candidate` |
| `provider_calls` | per Sentinel, `{reviewer id: n}`: answers that took a call to the provider |
| `cached_answers` | per Sentinel, `{reviewer id: n}`: answers read from the reviewer's answer cache, with no call. A review that failed after its retries gave no answer and is in neither count |

`Candidate.as_row()` returns one flat dict per dip (the rows of `candidates.json`). These keys are stable:
`candidate_id`, `target`, `mission`, `subject_id`, `t_start`, `t_end`, `t_center`, `time_unit`, `duration_hours`,
`score`, `n_reviewers`, `planet_fraction`, `reviewers` (ids joined by `;`), `passed`, `flags` (joined by `;`),
`depth_ppm`, `snr`, `period_days`, `n_transits`, `fap`, `fap_label`, `sector`, `bls_t0`, `bls_duration_days`,
`fit_t0`, `fit_depth_ppm`, `fit_t14_hours`, `fit_b`, `fit_rho_star`, `validation_label` and `outcome`. Other keys
of the row are internal.

`outcome` is the dip's vetting outcome, `passed`, `flagged` or `rejected`, by the same rule as the report and the
case file: a disqualifying flag or a failed check rejects; any other flag, or a check that was not measured, flags
the dip for review; only every check measured and passing passes. `dip_state(outcome)` gives its words: a passed dip
is a "candidate, unconfirmed", never a confirmed planet.

## Sentinels

| | Claude | OpenAI | OpenAI-compatible | Gemini |
| --- | --- | --- | --- | --- |
| Class | `ClaudeReviewer` | `OpenAIReviewer` | `OpenAICompatibleReviewer` | `GeminiReviewer` |
| Key variable (`PROVIDER_KEY_ENV`) | `ANTHROPIC_API_KEY` | `OPENAI_API_KEY` | the one named by `api_key_env=`, or none | `GEMINI_API_KEY` |
| Default model (`DEFAULT_SENTINEL_MODELS`) | `claude-sonnet-5-5` | none: `model=` is required | none: `model=` is required | none: `model=` is required |
| `transport=` | no (the Anthropic SDK; `client=` instead) | yes | yes | yes |

`Transport` is the type of the `transport=` callable: `Callable[[str, dict, dict, float], dict]`, called as
`transport(url, headers, body, timeout)` with the request's JSON body and timeout in seconds, and returning the
response's parsed JSON. Without one, a request goes over HTTPS with the standard library. The headers carry the key,
so a transport must never log or store them.

## Language per call

`with use_lang("de"):` makes SetuHQ's human-facing words inside the block German, and yields the language used (a
BCP 47 tag or POSIX locale is accepted; a language SetuHQ does not speak gives English). It sets a context variable,
never the environment, so each thread and each asyncio task has its own language, and a shared worker can serve
each request in its own. `use_lang(None)` is the process default: `SETUHQ_LANG`, then `LC_ALL`, `LC_MESSAGES` and
`LANG`, else English. Outside every block nothing changes: a library speaks English, and the CLI and the MCP server
follow `--lang`, then `SETUHQ_LANG`. `current_lang()` says which language is in force; `SUPPORTED_LANGS` lists them.

`attribution_text(lang=None)`, `probes_only_text(lang=None)` and `dip_state_text(outcome, lang=None)` are
`ATTRIBUTION`, `PROBES_ONLY` and `dip_state(outcome)` in `lang`, or in the current language when `lang` is None. The
English constants never change with the language. JSON keys, file formats and machine-read fields stay English.

## Stellar capabilities

`find_flares`, `pulsation_spectrum`, `find_eclipsing_binary`, `rotation_period` and `find_transients` each take
`time` (days; BTJD for TESS), `flux` and an optional `flux_err` as arrays, and return a frozen `StellarResult`:

| Field | What |
| --- | --- |
| `capability` | `flares`, `pulsations`, `binaries`, `rotation` or `transients` (`STELLAR_CAPABILITIES`) |
| `result` | the analysis, JSON-safe, with the same fields as the MCP tool of the same name |
| `labels` | the honesty labels the result must be shown with, in English, each one of `HONESTY_LABELS` |
| `validation_status` | the capability's status as its committed validation record states it, with its count: "partly validated (N of M checks pass)" or "not validated (N of M checks pass)" (`stellar_validation_status(capability)`) |
| `validation_record` | the record it comes from, in the repository's `docs/results` (the wheel ships a copy of the statuses) |

Transients are a search aid: every result carries `TRANSIENT_SEARCH_AID`. Each result is a candidate or a
measurement, never a confirmation.

## Honesty labels

| Name | Carried by |
| --- | --- |
| `STELLAR_DETECTION_LABEL` | flares and pulsations |
| `FLARE_ENERGY_LABEL` | flares |
| `BINARIES_LABEL`, `BINARIES_VETTING_NOTE` | eclipsing binaries (`binaries.LABEL`, `binaries.VETTING_NOTE`) |
| `ROTATION_LABEL` | rotation (`rotation.LABEL`) |
| `TRANSIENTS_LABEL`, `TRANSIENT_SEARCH_AID` | transients (`transients.LABEL`, `stellar_tools.TRANSIENT_SEARCH_AID`) |

Callers must carry these labels **verbatim**: not shortened, reworded or filtered. Several say what a result is
not, in words an output filter may withhold ("never a new, discovered or confirmed object"). `HONESTY_LABELS` is a
frozenset of every label and wording constant of this API (these, `ATTRIBUTION`, `PROBES_ONLY` and the words of
`dip_state`), exactly as written, so a filter can exempt an exact match. The labels are not reworded for such
filters: `transients.LABEL` is part of the code fingerprint recorded with the protocol v4 results.

## Internal

Everything not listed above, including: the site and its pages (`setuhq.site`, `setuhq.app`, `setuhq.viz`, the page
modules), the stand-alone outputs (`report`, `docket`, `plate`, `dashboard`), the sweep and its ledger, the MCP
server's tool layout, the CLI's arguments beyond those documented in the README, every module-level constant, and
anything whose name starts with `_`.

`setuhq.loaders.load_cheops`, `setuhq.cheops`, the `mission="CHEOPS"` option of the flare tools, and the stellar
CLI commands stay out of the stable API: CHEOPS data are under ESA's terms, CC BY-NC 3.0 IGO, whose non-commercial
clause rules out commercial use, so CHEOPS is never part of SetuHQ Pro or the commercial licence. The stable stellar
functions analyse the light curve they are given (TESS, or your own photometry) and never fetch CHEOPS data.

Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.

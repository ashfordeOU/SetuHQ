# Contributing a sweep: bring your own reviewer

SetuHQ's sweep (`setuhq sweep`) searches TESS sectors star by star and keeps everything that dims:
every consensus dip, every brightening and every star's variability, each classified by stated rules
(src/setuhq/variables.py). Anyone can search a sector with their own reviewers and send the result back as
a contribution bundle. A bundle that passes `setuhq ingest` is merged into the catalogue, and the name you
choose is credited on every new search you made, on the object pages and in the CSV and JSON exports.

Nothing in a contribution becomes a planet. A planet candidate in this catalogue is a light-curve
classification, unconfirmed, and the site sets every class beside its own null (what its rule finds where its
signal cannot be) and says when a class is not distinguishable from noise.

## Keys stay in your environment

**Never paste a key anywhere**: not in a config, not in a bundle, not in an issue, a pull request or a chat.

* **Your Claude subscription (the `claude_code` reviewer).** Install the Claude Code CLI, run `claude` once
  and sign in with `/login`. The reviewer runs `claude -p` under your own login; SetuHQ never sees a token.
* **The Anthropic API (the `claude` reviewer).** Set `ANTHROPIC_API_KEY` in your shell's environment
  (`export ANTHROPIC_API_KEY=...` in your own terminal, or your secret manager). SetuHQ reads it from the
  environment only and never writes it to a file.
* **The Probes** need nothing.

A bundle holds results, the config and hashes only. `setuhq bundle` and `setuhq ingest` both refuse a
bundle in which anything looks like a key or token.

## 1. Run the sweep

```bash
pip install -e ".[dev]"                 # add ,claude for the API reviewer
git rev-parse HEAD                       # note the commit: the maintainers ingest with the same code

# Probes only (no account needed):
setuhq sweep configs/sweep.toml --sector 5 --limit 100 --out my-sweep --contributor "Your Name"

# With two Sentinels on your Claude subscription (each subject is one CLI call per Sentinel):
setuhq sweep configs/sweep_sentinels.toml --sector 5 --limit 50 --out my-sweep --contributor "Your Name"
```

For the API instead of the CLI, copy `configs/sweep_sentinels.toml` and change each Sentinel's `type` from
`"claude_code"` to `"claude"`; the key comes from `ANTHROPIC_API_KEY` in your environment.

* **Resumable.** Each finished star-sector is stored in `cache/sweep/` at once. Stop at any time (Ctrl-C,
  `--time-budget-min`) and run the same command again: done stars are skipped, failed ones retried.
* **Polite to MAST.** One request at a time, at least `--min-interval` seconds apart (1 s by default), with
  back-off on errors. Light-curve files are cached in `cache/mast/sweep/` and never fetched twice.
* **A fair slice.** Targets are taken in a fixed pseudo-random order (sha256 of `"<sector>:<tic>"`), so
  the first N of a sector are a fair sample and a larger `--limit` grows the same slice.
* Each star's classes are also measured against their nulls: the dip classes on the flux-inverted copy (a
  real dip becomes a bump; a real flare or pulsation maximum becomes a dip, so this null is not empty of
  real signals), flares as downward events with the real dips masked, and variability on a red-noise copy
  of the star (an AR(1) process fitted to its own bins). `--no-control` halves the time, but the site then cannot set your searches against their nulls.

The record is `my-sweep/sector_0005.json.gz`: every star-sector of the slice with what was searched (the
light-curve file and its sha256, points, subjects, reviewers and weights), what was found (entries by class,
with every mark, weight and the Sentinels' own words) and what was rejected (mark clusters below consensus,
dips that failed vetting).

## 2. Make a bundle

```bash
setuhq bundle my-sweep/sector_0005.json.gz --contributor "Your Name" --out your-name-s5
```

The bundle directory holds three files:

| File | What it is |
|---|---|
| `results.json` | the sector record, with its config text written without comments |
| `config.toml` | the sweep config that ran, written without comments (where a pasted key would hide); loading it gives the same config hash |
| `manifest.json` | your chosen name and statement, and the provenance: the search and classification code fingerprints (sha256 of the result-making source files, `setuhq.starsearch.SEARCH_FILES` and `CLASSIFY_FILES`), the config hash, the sha256 of every light curve read, the reviewers, the sha256 of the two files above, and `content_sha256` over the manifest itself |

**Sealed, not signed.** The content hashes make any later change to a file or to the manifest visible; they
are not a signature and do not prove who made the bundle (anyone can edit a bundle and recompute every hash).
That is why ingest checks the results against the world (below) and records who sent the bundle.
The name is yours to choose (1 to 60 letters, digits, spaces and `. , ' ( ) - _`; no links or e-mail).
Share the directory, or a zip of it, in a pull request: the pull request's author is the identity the
maintainers attest at ingest.

## 3. Ingest (maintainers)

```bash
setuhq ingest your-name-s5 --attested-by <pull-request-author>
```

`ingest` refuses the bundle, and says why, when:

* a file or the manifest does not match its hash, or the bundle (or zip) holds anything else;
* its search or classification code fingerprint is not this checkout's: check out the commit the
  contributor ran, then ingest;
* its config hash does not match `config.toml`, the manifest or the results, or the config has comments;
* a light-curve sha256 is missing, malformed or not in the manifest;
* an entry's class or confidence is not what the rules give for its stored inputs (the rules are
  re-applied to every dip, brightening and variability entry);
* a star-sector it fetches again from MAST hashes differently, or a fresh search of it with the bundle's
  config and this code does not reproduce every entry, count and null exactly. It fetches and searches
  **every star-sector that carries an entry in an astrophysical class** (planet candidate, eclipsing
  binary, flare, variable), and every one with an entry in a class that would exceed its null once the
  bundle is merged (judged on a provisional merge, so forged entries cannot push a class over its null
  unchecked), plus `max(3, 5%)` of the rest, which carry only systematic and unclassified entries, at random
  (`--verify-lightcurves N` sets that number). The random draw is seeded with a nonce the maintainer's
  machine makes at ingest (os.urandom), so renaming or resealing a bundle cannot steer it. The Probes are
  deterministic, so this catches results that were edited and resealed: a forged astrophysical entry
  always, a forged systematic or unclassified entry with the sampled probability;
* it has Sentinels, whose answers a fresh search cannot reproduce, unless the maintainer passes
  `--accept-sentinels` (the catalogue then records that its dips were not searched again);
* every star-sector in it is already in the catalogue as an identical search (same light curve, search code
  and config): a re-submission, under any name, adds nothing;
* anything in it looks like a credential: API keys of any form (sk-, AIza, hf_), cloud and GitHub tokens,
  bearer and x-api-key headers, JWTs, private keys, a bare AWS secret, a `key`, `token`, `secret` or
  `password` with a value, or a long random-looking value in the config;
* it was ingested before.

A valid bundle is copied to `docs/sweep/contributions/<bundle_id>/` with `ingest.json`: who attested it, when,
the nonce, what was fetched and searched again, and the manifest's hash. `docs/sweep/catalogue.json` is then
rebuilt. **The catalogue reads only folders that ingest wrote and whose hashes still verify**; a folder
placed or edited by hand is left out, and `setuhq check-sweep` (a step of `scripts/ci_local.sh`) fails on
it. One search counts for each star-sector, the latest: it alone gives the entries, counters, nulls and
credit, and earlier searches of the same star-sector stay as provenance on its coverage row. An identical
copy of a search earns nothing. Then rebuild the site (`scripts/ci_local.sh`) and commit.

Every ingest also appends a line to `docs/sweep/ingest_ledger.jsonl` (the bundle id, the manifest's and
files' hashes, who attested it, the nonce). `setuhq check-sweep` requires every contribution folder to match
its ledger line, and CI requires the ledger to be an append-only extension of the one at its merge-base with
the base branch (`--ledger-base auto`: `SETUHQ_BASE`, the pull request's base, or the remote's default
branch). The check fails closed: in hosted CI (`CI` set) a base that cannot be found fails it, and only a local
run skips it, with a note. So a contribution resealed after it was merged fails CI. **What these checks cannot do is
tell an honest new ledger line from a dishonest one in the same pull request:** someone with write access
could ingest, then edit a folder, its ingest.json and its ledger line before committing. Review of the pull
request that adds a contribution is what guards against that (`.github/CODEOWNERS` requires a maintainer's
review for every change under `docs/sweep/`, new ledger lines included): a reviewer runs `setuhq ingest` again on the
bundle (or compares the folder with the bundle in the pull request) before merging.

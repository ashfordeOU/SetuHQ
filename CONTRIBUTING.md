# Contributing a sweep: bring your own reviewer

exoplan's sweep (`exoplan sweep`) searches TESS sectors star by star and keeps everything that dims:
every consensus dip, every brightening and every star's variability, each classified by stated rules
(src/exoplan/variables.py). Anyone can search a sector with their own reviewers and send the result back as
a contribution bundle. A bundle that passes `exoplan ingest` is merged into the catalogue, and the name you
choose is credited on every entry you found, on the object pages and in the CSV and JSON exports.

Nothing in a contribution becomes a planet. A planet candidate in this catalogue is a light-curve
classification, unconfirmed, and the site shows beside it what the same rules found on flux-inverted copies
of the same stars.

## Keys stay in your environment

**Never paste a key anywhere**: not in a config, not in a bundle, not in an issue, a pull request or a chat.

* **Your Claude subscription (the `claude_code` reviewer).** Install the Claude Code CLI, run `claude` once
  and sign in with `/login`. The reviewer runs `claude -p` under your own login; exoplan never sees a token.
* **The Anthropic API (the `claude` reviewer).** Set `ANTHROPIC_API_KEY` in your shell's environment
  (`export ANTHROPIC_API_KEY=...` in your own terminal, or your secret manager). exoplan reads it from the
  environment only and never writes it to a file.
* **The Probes** need nothing.

A bundle holds results, the config and hashes only. `exoplan bundle` and `exoplan ingest` both refuse a
bundle in which anything looks like a key or token.

## 1. Run the sweep

```bash
pip install -e ".[dev]"                 # add ,claude for the API reviewer
git rev-parse HEAD                       # note the commit: the maintainers ingest with the same code

# Probes only (no account needed):
exoplan sweep configs/sweep.toml --sector 5 --limit 100 --out my-sweep --contributor "Your Name"

# With two Sentinels on your Claude subscription (each subject is one CLI call per Sentinel):
exoplan sweep configs/sweep_sentinels.toml --sector 5 --limit 50 --out my-sweep --contributor "Your Name"
```

For the API instead of the CLI, copy `configs/sweep_sentinels.toml` and change each Sentinel's `type` from
`"claude_code"` to `"claude"`; the key comes from `ANTHROPIC_API_KEY` in your environment.

* **Resumable.** Each finished star-sector is stored in `cache/sweep/` at once. Stop at any time (Ctrl-C,
  `--time-budget-min`) and run the same command again: done stars are skipped, failed ones retried.
* **Polite to MAST.** One request at a time, at least `--min-interval` seconds apart (1 s by default), with
  back-off on errors. Light-curve files are cached in `cache/mast/sweep/` and never fetched twice.
* **A fair slice.** Targets are taken in a fixed pseudo-random order (sha256 of `"<sector>:<tic>"`), so
  the first N of a sector are a fair sample and a larger `--limit` grows the same slice.
* Each star is also searched with its flux inverted (a control: nothing real can dim there). `--no-control`
  halves the time but the site then cannot show your false-alarm counts.

The record is `my-sweep/sector_0005.json`: every star-sector of the slice with what was searched (the
light-curve file and its sha256, points, subjects, reviewers and weights), what was found (entries by class,
with every mark, weight and the Sentinels' own words) and what was rejected (mark clusters below consensus,
dips that failed vetting).

## 2. Make a bundle

```bash
exoplan bundle my-sweep/sector_0005.json --contributor "Your Name" --out your-name-s5
```

The bundle directory holds three files:

| File | What it is |
|---|---|
| `results.json` | the sector record, unchanged |
| `config.toml` | the sweep config that ran; its hash is the run's config hash |
| `manifest.json` | the sign-off and the provenance: your chosen name, the code fingerprint (sha256 of the result-making source files, `exoplan.starsearch.CODE_FILES`), the config hash, the sha256 of every light curve read, the reviewers, the sha256 of the two files above, and `content_sha256` over the manifest itself |

Signing off means content hashes, not keys: any later change to a file or to the manifest breaks a hash.
The name is yours to choose (1 to 60 letters, digits, spaces and `. , ' ( ) - _`; no links or e-mail).
Share the directory, or a zip of it, in a pull request or an issue.

## 3. Ingest (maintainers)

```bash
exoplan ingest your-name-s5 [--verify-lightcurves 5]
```

`ingest` refuses the bundle, and says why, when:

* a file or the manifest does not match its hash, or the bundle holds other files;
* its code fingerprint is not this checkout's: check out the commit the contributor ran, then ingest;
* its config hash does not match `config.toml`, the manifest or the results;
* a light-curve sha256 is missing, malformed or not in the manifest;
* an entry's class or confidence is not what the rules give for its stored inputs (the rules are
  re-applied to every dip, brightening and variability entry);
* anything in it looks like a credential;
* it was ingested before.

`--verify-lightcurves N` re-downloads N of the light curves from MAST and checks their sha256.

A valid bundle is copied to `docs/sweep/contributions/<bundle_id>/` and `docs/sweep/catalogue.json` is
rebuilt: an entry found by two searches with the same class and panel is one entry with both credited; a
disagreement keeps both. Then rebuild the site (`scripts/ci_local.sh`) and commit.

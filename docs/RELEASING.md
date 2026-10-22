<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Releasing SetuHQ

A release is a version bump merged to `main`. Once CI is green on the merge, everything else is automatic:
`.github/workflows/auto-tag.yml` tags the commit and starts `.github/workflows/release.yml` on the tag, which
runs in one fixed order. No secret, token or click is involved.

```
release PR (version, CHANGELOG, date, README)  ->  merge, CI green on main
   ->  auto-tag.yml: checks, tags vX.Y.Z on that commit, dispatches release.yml on the tag
   ->  release.yml: verify -> build -> release (GitHub Release) -> pypi (PyPI)
   ->  Zenodo DOI (GitHub release webhook)
   later, by hand  ->  mcp-publish.yml (MCP registry)
```

Nothing reaches PyPI until the tag has been checked against the version, the changelog and its date, CI is
green on the tagged commit in a push to `main`, and the GitHub Release has been created with attested files.
PyPI and the GitHub Release receive the same bytes, built once.

> **The PyPI trusted publisher is `release.yml`.** The publishing job lives in `release.yml`, so the pending
> publisher on PyPI must name workflow **`release.yml`** (not `publish.yml`, which no longer exists). If a
> pending publisher was already added with `publish.yml`, delete it and add the one below.

## One-time set-up (the owner, once)

These need the owner's accounts; nothing in the repository can do them.

1. **PyPI pending trusted publisher.** On <https://pypi.org/manage/account/publishing/>, "Add a new
   pending publisher", GitHub tab:
   - PyPI project name: `setuhq`
   - Owner: `ashfordeOU`
   - Repository name: `SetuHQ`
   - Workflow name: **`release.yml`**
   - Environment name: `pypi`

   The first successful upload creates the project and turns the pending publisher into a normal one.
   No API token is created or stored anywhere. (Optional upload rehearsal: the same on
   <https://test.pypi.org/manage/account/publishing/>, workflow `release.yml`, environment `testpypi`.)
2. **GitHub environment `pypi`.** Repository Settings, Environments, `pypi`:
   - **Deployment branches and tags:** selected, tags matching `v*` only (already so). Every release run
     has the tag as its ref, whether a tag push or auto-tag's dispatch on the tag started it, so the rule
     is met; a dispatch on a branch can never deploy to `pypi`.
   - **Required reviewers: none.** Remove the owner as required reviewer, or every release waits at the
     `pypi` job for a click. This is the one setting the automatic flow needs. The gate is the release
     itself: the tag rule above, the checks in `verify` (version, changelog, date, CI green on this commit
     on `main`) and the protected `main` (step 5).

   (`testpypi`, if used: it runs on the branch a dry run is dispatched from, so do not restrict it to tags.)
3. **Zenodo.** Sign in at <https://zenodo.org> with GitHub, open <https://zenodo.org/account/settings/github/>,
   and switch `ashfordeOU/SetuHQ` **on**. From then on every published GitHub Release is archived and
   gets a DOI; `.zenodo.json` supplies the title, the creator (Chakshu Baweja, Ashforde OÜ), the licence
   (`agpl-3.0-only`, Zenodo's id), the keywords and the links. (Done: v0.1.0 is archived, version DOI
   `10.5281/zenodo.23568349`, concept DOI `10.5281/zenodo.23568348`.)
4. **MCP registry.** Nothing to set up: `mcp-publish.yml` logs in with GitHub OIDC, which the registry
   accepts for the `io.github.ashfordeOU/*` namespace. See `packaging/mcp/SUBMITTING.md` for the
   directories that need a form (Smithery, Glama, the Claude Code plugin directory).
5. **Protect `main`.** Settings, Rules, Rulesets, New branch ruleset on the default branch: require a pull
   request, require the status checks `test` and `test-python-3-11` (ci.yml), block force pushes and
   deletions. A tag ruleset on `v*` that blocks update and deletion keeps release tags immutable. If the
   ruleset also restricts **creation**, add **GitHub Actions** to its bypass list (auto-tag.yml creates
   the tag as `github-actions[bot]`); otherwise auto-tag fails at the push and says so.
6. **Private vulnerability reporting.** Settings, Code security, "Private vulnerability reporting":
   **Enable**. SECURITY.md and the issue chooser point reporters to it.

**auto-tag** (below) is on by default and needs no secret. A secret `RELEASE_TAG_TOKEN` or a variable
`AUTO_TAG=true` from the earlier, opt-in design is no longer read and can be deleted.

## Cutting a release

1. **Bump the version** in `src/setuhq/__init__.py` (`__version__`). It is the only place the package
   reads it from (pyproject.toml takes it from there). Bring every other surface to the same version:
   `CITATION.cff`, `codemeta.json`, `.zenodo.json`, `server.json` (the server and its package),
   `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and the pin in `smithery.yaml`.
2. **Write the changelog section.** Move everything under `[Unreleased]` into a new `## [X.Y.Z]` section
   and leave `[Unreleased]` empty: the section becomes the GitHub Release notes word for word
   (`python3 scripts/changelog_extract.py X.Y.Z` shows them), and the release refuses a tag while
   `[Unreleased]` still has entries.
3. **Date it for the day you will merge** (the release follows the merge within minutes), in the same pull
   request. `python3 scripts/set_release_date.py X.Y.Z YYYY-MM-DD` writes the date into the CHANGELOG heading
   and CITATION.cff's `date-released` together. If the merge slips to another day, run it again on the pull
   request before merging; the two dates must agree or the release stops. Then:

   ```bash
   python3 scripts/check_version_sync.py --tag vX.Y.Z
   ```

   It must say OK. (`tests/test_release.py` runs the same checks without the tag.)
4. **Regenerate the README** (the PyPI badge shows `__version__`):
   `python tools/gen_readme_assets.py && python tools/gen_readme_assets.py --write-readme`.
5. **Dry run (required), before merging.** Actions, **Release**, Run workflow on the release pull request's
   branch, and confirm the run is **green**. It checks the version surfaces (CI on that branch is reported as
   a warning), builds the sdist and the wheel, runs `twine check`, `scripts/check_dist.py` and a clean install
   with the MCP smoke test, and keeps the files as a workflow artifact; it creates and publishes nothing. These
   are the same build steps the release runs, and some of them (the build, `twine check`, the contents check)
   run nowhere else; since nothing comes between the merge and the release, this is the last chance to see
   them fail. Tick `testpypi` to also upload that build to TestPyPI as a rehearsal (needs the TestPyPI
   publisher).
6. **Merge to `main`** through a pull request. That is the last manual step. When CI (`ci.yml`) finishes
   green on the merge commit in the push to `main`, `auto-tag.yml` runs `check_version_sync.py --tag vX.Y.Z`,
   pushes the annotated tag `vX.Y.Z` on exactly that commit and starts `release.yml` on the tag; follow it
   under Actions, **Release**. If `main` moved on while CI ran, the run on the newer head tags it instead.

**Manual fallback.** A tag pushed by hand still releases the same way (a tag push starts `release.yml`):

```bash
git tag -a vX.Y.Z <commit> -m "SetuHQ vX.Y.Z"
git push origin vX.Y.Z
```

Tag only a commit on `main` that CI has passed in a push to `main`; the release refuses any other. If the tag
exists but no Release run started for it, run **Release** by hand with "Use workflow from" set to the tag
(Tags tab, `vX.Y.Z`): a dispatch on a tag is a full release, not a dry run. Starting a second run for a tag
that already has one is safe: see [One release per tag](#one-release-per-tag).

## What happens after the tag

| Stage | Where | What it does | If it fails |
|---|---|---|---|
| verify | `release.yml` job `verify` | the tag equals `v` + `__version__`, every surface agrees, `[Unreleased]` is empty, the CHANGELOG date equals CITATION.cff's; the commit is an ancestor of `origin/main` and ci.yml finished green on it in a push to `main` | nothing is built or published; delete the tag (`git push origin :refs/tags/vX.Y.Z`, or `gh api -X DELETE repos/ashfordeOU/SetuHQ/git/refs/tags/vX.Y.Z`), fix it on `main` by pull request, and the fix's green CI run tags it again (nothing was published yet) |
| build | `release.yml` job `build` | `python -m build` (sdist and wheel), `twine check --strict`, `scripts/check_dist.py` (package, `py.typed`, the reference tables, fonts, licences; no runs, site, docs, caches or tests), clean install of the wheel with `setuhq --help`, an MCP stdio smoke test of `setuhq-mcp` and `setuhq mcp` (`scripts/smoke_mcp.py`) and a read of the shipped tables; the files become the run's `dist` artifact | nothing is released; delete the tag and fix as above |
| release | `release.yml` job `release` | build-provenance attestation of both files (`actions/attest-build-provenance`), then the GitHub Release for the tag with the CHANGELOG section as notes and both files attached | "Re-run failed jobs" on the same run: it reuses the run's `dist` artifact, never replaces a file the release already has (different bytes fail the job), adds a missing one and refreshes the notes |
| pypi | `release.yml` job `pypi` (environment `pypi`) | uploads the same `dist` artifact to PyPI by trusted publishing, with PEP 740 attestations | "Re-run failed jobs" on the same run (within the artifact's 90 days); already-uploaded files are skipped. Nothing ever rebuilds for PyPI |
| Zenodo | Zenodo's GitHub integration | archives the release and mints a version DOI (and, the first time, the concept DOI for all versions) | re-publish from Zenodo's GitHub page |

Check a downloaded file's provenance with `gh attestation verify setuhq-X.Y.Z-py3-none-any.whl --repo ashfordeOU/SetuHQ`.

## After the release

1. **PyPI:** <https://pypi.org/project/setuhq/X.Y.Z/> shows the version, and `pip install "setuhq[mcp]==X.Y.Z"`
   in a clean environment gives working `setuhq`, `setuhq mcp` and `setuhq-mcp` commands.
2. **DOI:** nothing to change. Zenodo mints each release's version DOI itself; the repository carries only the
   **concept DOI** `10.5281/zenodo.23568348` (all versions; it resolves to the latest), which v0.1.0 created:
   `CITATION.cff` (`doi:` and `identifiers:`), `codemeta.json` (`identifier`), `paper/paper.bib` (the
   `setuhq` entry), the README badge (`CONCEPT_DOI` in `tools/gen_readme_assets.py`) and its Cite section.
   `.zenodo.json` carries no DOI: Zenodo assigns it. `tests/test_release.py` pins these.
3. **README badges** are generated (`tools/gen_readme_assets.py`, the `generated:badges` block). The PyPI badge
   is a static shields badge from `__version__`, so `tools/gen_readme_assets.py --check` stays offline and
   deterministic; the version bump changes it, so run `python tools/gen_readme_assets.py --write-readme` in the
   release pull request. Still to add once `mcp-publish.yml` has run: a static shields badge `MCP registry |
   io.github.ashfordeOU/setuhq` linking to
   `https://registry.modelcontextprotocol.io/v0/servers?search=io.github.ashfordeOU/setuhq`.
4. **MCP registry:** Actions, **Publish to the MCP registry**, on the tag (dry run first). See
   `packaging/mcp/SUBMITTING.md`.
5. **Release notes** are always the CHANGELOG section. To change them, fix CHANGELOG.md on `main` and run
   Actions, **Release notes**, with the tag.

## Auto-tag (on by default)

`.github/workflows/auto-tag.yml` runs when CI finishes green on a push to `main`. If `vX.Y.Z` (from
`__version__`) does not exist yet and the commit is still `main`'s head, it runs
`scripts/check_version_sync.py --tag vX.Y.Z` (surfaces, empty `[Unreleased]`, dates), pushes an annotated tag
on exactly that commit, and then starts `release.yml` on the tag with `gh workflow run release.yml --ref
vX.Y.Z`. It never moves or replaces a tag; if the version is already tagged it does nothing.

It uses only the workflow's own `GITHUB_TOKEN`, with `contents: write` (the tag) and `actions: write` (the
dispatch). A tag pushed with `GITHUB_TOKEN` starts no workflow (GitHub does not let that token trigger runs,
to prevent loops), but `workflow_dispatch` is one of the two events exempt from that rule, so the dispatch
does start `release.yml`. `release.yml` treats a run whose ref is a tag (`github.ref_type == 'tag'`) as a
release whichever event started it, so the dispatched run is the same release a tag push would run: strict CI
check, GitHub Release, attestation and PyPI.

To switch it off, set the repository **variable** `AUTO_TAG` to `false` (Settings, Secrets and variables,
Actions, Variables); then release by the manual fallback above.

## One release per tag

A tag push and a dispatch for the same tag (or two dispatches) never publish twice:

1. `release.yml`'s concurrency group is the ref (`release-refs/tags/vX.Y.Z`) with `cancel-in-progress: false`,
   so runs for one tag never overlap: a later run waits until the earlier one has finished.
2. The later run's `verify` then finds the GitHub Release carrying both files and the version on PyPI, and
   skips `build`, `release` and `pypi`; the run ends green with a notice. Nothing is rebuilt, attested or
   uploaded again.
3. If the earlier run stopped half-way, the later run does rebuild. The `release` job keeps any file whose
   bytes equal the release's and fails on a file that differs (setuptools stamps archive times, so a rebuild
   usually does), and `pypi` only runs after `release` succeeds. PyPI itself never accepts a second file under
   an existing name; `skip-existing: true` only makes an upload of a file that is already there a skip instead
   of an error. So the way to finish a half-done release is "Re-run failed jobs" on its own run, which reuses
   that run's attested `dist` artifact.

Auto-tag itself only dispatches for a tag it has just pushed. If someone pushes the same tag by hand at the same
moment, auto-tag's own push is refused (a plain push never overwrites) and it dispatches nothing, so in normal
use exactly one run starts per tag.

## Workflows at a glance

| Workflow | Trigger | Publishes |
|---|---|---|
| `release.yml` | push of a `v*` tag; dispatch (by auto-tag or by hand) | on a tag (pushed or dispatched): the GitHub Release and PyPI (trusted publisher); a dispatch on a branch is a dry run: nothing, or TestPyPI when asked |
| `mcp-publish.yml` | manual only, after PyPI | the official MCP registry, by GitHub OIDC |
| `release-notes.yml` | manual | edits an existing release's notes |
| `auto-tag.yml` | CI green on `main` (off only with `AUTO_TAG=false`) | a `v*` tag, then dispatches `release.yml` on it |
| `joss-draft.yml` | changes under `paper/`; manual | nothing (a PDF artifact) |
| `ci.yml` | every push and pull request | nothing (tests on 3.13 with the README check, fast tests on 3.11) |

Every action in these workflows is pinned by full commit SHA, with its tag in a comment; Dependabot
(`.github/dependabot.yml`) proposes updates weekly.

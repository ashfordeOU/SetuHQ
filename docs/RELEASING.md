<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Releasing SetuHQ

A release is one tag push. Everything after it is automatic, in one fixed order:

```
bump + CHANGELOG  ->  merge, CI green  ->  tag vX.Y.Z  ->  release.yml  ->  publish.yml (PyPI)
                                                                         ->  Zenodo DOI (GitHub release webhook)
                                                     later, by hand  ->  mcp-publish.yml (MCP registry)
```

Nothing reaches PyPI until the tag has been checked against the version, the changelog section exists,
CI is green on the tagged commit, and the GitHub Release has been created with attested files.

## One-time set-up (the owner, once)

These need the owner's accounts; nothing in the repository can do them.

1. **PyPI pending trusted publisher.** On <https://pypi.org/manage/account/publishing/>, "Add a new
   pending publisher", GitHub tab:
   - PyPI project name: `setuhq`
   - Owner: `ashfordeOU`
   - Repository name: `SetuHQ`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

   The first successful upload creates the project and turns the pending publisher into a normal one.
   No API token is created or stored anywhere. (Optional dry run: the same on
   <https://test.pypi.org/manage/account/publishing/> with environment `testpypi`.)
2. **GitHub environment `pypi`.** Repository Settings, Environments, New environment, `pypi`. Recommended:
   a deployment branch and tag rule that allows only tags matching `v*`, and the owner as required
   reviewer if each upload should wait for a click. (`testpypi` likewise, if used.)
3. **Zenodo.** Sign in at <https://zenodo.org> with GitHub, open <https://zenodo.org/account/settings/github/>,
   and switch `ashfordeOU/SetuHQ` **on**. From then on every published GitHub Release is archived and
   gets a DOI; `.zenodo.json` supplies the title, the creator (Chakshu Baweja, Ashforde OÜ), the licence,
   the keywords and the links. Switch it on **before** the first tag, or v0.1.0 gets no DOI.
4. **MCP registry.** Nothing to set up: `mcp-publish.yml` logs in with GitHub OIDC, which the registry
   accepts for the `io.github.ashfordeOU/*` namespace. See `packaging/mcp/SUBMITTING.md` for the
   directories that need a form (Smithery, Glama, the Claude Code plugin directory).
5. **Protect `main`.** Settings, Rules, Rulesets, New branch ruleset on the default branch: require a pull
   request, require the `test` status check (ci.yml), block force pushes and deletions. A tag ruleset on
   `v*` that restricts creation, update and deletion to the owner keeps release tags immutable.
6. **Private vulnerability reporting.** Settings, Code security, "Private vulnerability reporting":
   **Enable**. SECURITY.md and the issue chooser point reporters to it.

Optional: **auto-tag** (below) needs a repository variable `AUTO_TAG=true` and a secret
`RELEASE_TAG_TOKEN`. It is off by default.

## Cutting a release

1. **Bump the version** in `src/setuhq/__init__.py` (`__version__`). It is the only place the package
   reads it from (pyproject.toml takes it from there). Then bring every other surface to the same
   version: `CITATION.cff` (`version` and `date-released`), `codemeta.json`, `.zenodo.json`, `server.json`
   (the server and its package), `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and the
   pin in `smithery.yaml`. Run:

   ```bash
   python3 scripts/check_version_sync.py --tag vX.Y.Z
   ```

   It must say OK; `tests/test_release.py` runs the same check without the tag.
2. **Update CHANGELOG.md.** Rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD` and start a fresh, empty
   `[Unreleased]`. That section becomes the GitHub Release notes word for word
   (`python3 scripts/changelog_extract.py X.Y.Z` shows them).
3. **Merge to `main`** through a pull request and wait for CI (`ci.yml`) to pass on the merge commit.
   Run `scripts/ci_local.sh` too for anything that touches results or pages.
4. **Optional dry run.** Actions, **Release**, Run workflow on `main` with `dry_run` on: it checks the
   version surfaces and CI, builds the sdist and the wheel, runs `twine check`, the contents check and a
   clean install, and keeps the files as a workflow artifact. It creates and publishes nothing. For an
   upload rehearsal, Actions, **Publish to PyPI**, target `testpypi` (needs the TestPyPI publisher).
5. **Tag the green commit** and push the tag:

   ```bash
   git tag -a vX.Y.Z <commit> -m "SetuHQ vX.Y.Z"
   git push origin vX.Y.Z
   ```

   Tag only a commit CI has already passed; the release refuses any other.

## What happens after the tag

| Stage | Where | What it does | If it fails |
|---|---|---|---|
| verify | `release.yml` job `verify` | the tag equals `v` + `__version__` and every surface agrees; CHANGELOG has the section; ci.yml finished green on this exact commit | nothing is built or published; fix, move or re-cut the tag |
| build | `release.yml` job `build` | `python -m build` (sdist and wheel), `twine check --strict`, `scripts/check_dist.py` (package, `py.typed`, fonts, licences; no runs, site, docs, caches or tests), clean install of the wheel with `setuhq --help` and an MCP stdio smoke test (`scripts/smoke_mcp.py`) | nothing is released |
| release | `release.yml` job `release` | build-provenance attestation of both files (`actions/attest-build-provenance`), then the GitHub Release for the tag with the CHANGELOG section as notes and both files attached | rerun the failed job; or dispatch Release with the tag and `dry_run` off to rebuild the release (it never publishes) |
| PyPI | `publish.yml`, started when the Release run completes green for a pushed tag | downloads the exact files that run attested, checks them again, uploads them to PyPI by trusted publishing (environment `pypi`, PEP 740 attestations) | dispatch **Publish to PyPI** on the tag with target `pypi`; it rebuilds from the tag, checks that release.yml's verify passed for that commit, and skips files already uploaded |
| Zenodo | Zenodo's GitHub integration | archives the release and mints a version DOI (and, the first time, the concept DOI for all versions) | re-publish from Zenodo's GitHub page |

Check a downloaded file's provenance with `gh attestation verify setuhq-X.Y.Z-py3-none-any.whl --repo ashfordeOU/SetuHQ`.

## After the release

1. **PyPI:** <https://pypi.org/project/setuhq/X.Y.Z/> shows the version, and `pip install "setuhq[mcp]==X.Y.Z"`
   in a clean environment gives working `setuhq` and `setuhq-mcp` commands.
2. **DOI:** take the DOIs from the Zenodo record. Use the **concept DOI** (all versions) for the badge and the
   general citation, and the **version DOI** for this release. Then, in one pull request:
   - `CITATION.cff`: add `doi: <concept DOI>` and an `identifiers:` entry with the version DOI;
   - `codemeta.json`: add `"identifier": "https://doi.org/<concept DOI>"`;
   - `.zenodo.json`: add a `related_identifiers` entry `{"identifier": "<concept DOI>", "relation":
     "isVersionOf", "scheme": "doi", "resource_type": "software"}`;
   - `paper/paper.bib`: the `setuhq` entry's `doi`;
   - README: the DOI badge and the Cite section's "there is no DOI yet" sentence (see below).
3. **README badges and install line,** once the package is live (they are not added before, so the README
   never shows a badge that 404s). The badge row is generated: add them in `tools/gen_readme_assets.py`
   (the `generated:badges` block), then `python tools/gen_readme_assets.py --write-readme`.
   - PyPI: `https://img.shields.io/pypi/v/setuhq?style=flat-square&labelColor=0A1226` linking to
     `https://pypi.org/project/setuhq/`;
   - DOI: `https://zenodo.org/badge/DOI/<concept DOI>.svg` linking to `https://doi.org/<concept DOI>`;
   - MCP registry: a static shields badge `MCP registry | io.github.ashfordeOU/setuhq` linking to
     `https://registry.modelcontextprotocol.io/v0/servers?search=io.github.ashfordeOU/setuhq`, once
     `mcp-publish.yml` has run;
   - Install section: `pip install "setuhq[mcp]"` as the first line, the git install as the second.
4. **MCP registry:** Actions, **Publish to the MCP registry**, on the tag (dry run first). See
   `packaging/mcp/SUBMITTING.md`.
5. **Release notes** are always the CHANGELOG section. To change them, fix CHANGELOG.md on `main` and run
   Actions, **Release notes**, with the tag.

## Auto-tag (optional, off by default)

`.github/workflows/auto-tag.yml` does step 5 above by itself: when CI finishes green on a push to `main`
and `vX.Y.Z` (from `__version__`) does not exist yet, it checks the version surfaces and the changelog and
pushes an annotated tag on exactly that commit. It never moves or replaces a tag. It needs both:

- repository **variable** `AUTO_TAG` = `true`;
- repository **secret** `RELEASE_TAG_TOKEN`: a fine-grained personal access token for
  `ashfordeOU/SetuHQ` only, with Contents read and write. (A tag pushed with the workflow's own token
  would not start release.yml.)

Without the variable it does nothing. With the variable and without the secret it fails loudly.

## Workflows at a glance

| Workflow | Trigger | Publishes |
|---|---|---|
| `release.yml` | push of a `v*` tag; manual (dry run by default) | the GitHub Release (tag push, or a manual rebuild with a tag) |
| `publish.yml` | a green Release run of a pushed tag; manual (TestPyPI, or a PyPI retry on a tag) | PyPI / TestPyPI, by trusted publishing |
| `mcp-publish.yml` | manual only, after PyPI | the official MCP registry, by GitHub OIDC |
| `release-notes.yml` | manual | edits an existing release's notes |
| `auto-tag.yml` | CI green on `main`, only with `AUTO_TAG=true` | a `v*` tag |
| `joss-draft.yml` | changes under `paper/`; manual | nothing (a PDF artifact) |

Every action in these workflows is pinned by full commit SHA, with its tag in a comment; Dependabot
(`.github/dependabot.yml`) proposes updates weekly.

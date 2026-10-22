<!-- SPDX-License-Identifier: AGPL-3.0-only -->
## What and why

<!-- What this changes, and why. Link the issue it closes, if any. -->

## Checklist

- [ ] I agree to the [Contributor Licence Agreement](https://github.com/ashfordeOU/SetuHQ/blob/main/CLA.md) (CLA.md); on a first pull request, the line from [CLA.md](https://github.com/ashfordeOU/SetuHQ/blob/main/CLA.md#6-how-you-agree) is in the description.
- [ ] Tests pass locally: `python -m pytest -q` (and `scripts/ci_local.sh` for a change to results, pages or the site).
- [ ] New behaviour has a test; a change to a number in a result says how it was checked.
- [ ] Regenerated assets are current: `python tools/gen_readme_assets.py --check` passes (after `python tools/gen_readme_assets.py && python tools/gen_readme_assets.py --write-readme` if a figure, a badge or a count changed).
- [ ] `CHANGELOG.md` `[Unreleased]` names any user-visible change.
- [ ] No key, token or credential anywhere in the diff, the commits or the description.
- [ ] Nothing here calls a SetuHQ output confirmed, validated or discovered: outputs are candidates.

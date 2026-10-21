#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Print the release notes for a version: its CHANGELOG.md section, then where to get the release.

The GitHub Release body is exactly this (release.yml, release-notes.yml), so the notes are written once, in the
changelog, and never by hand on the release page. Exit status 1 when the changelog has no section for the version.

    python3 scripts/changelog_extract.py 0.1.0 > RELEASE_NOTES.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/ashfordeOU/SetuHQ"


def section(version: str, changelog: str) -> str:
    """The text between ``## [version]`` and the next ``## [`` heading, without surrounding blank lines."""
    out, grab = [], False
    for line in changelog.splitlines():
        if re.match(rf"^## \[{re.escape(version)}\]", line):
            grab = True
            continue
        if grab and line.startswith("## ["):
            break
        if grab:
            out.append(line)
    return "\n".join(out).strip("\n")


def notes(version: str, changelog: str) -> str:
    body = section(version, changelog)
    if not body.strip():
        raise LookupError(f"CHANGELOG.md has no section for {version}")
    return f"""{body}

---

### Get this release

| Channel | Get it |
| --- | --- |
| [PyPI](https://pypi.org/project/setuhq/{version}/) | `pip install "setuhq[mcp]=={version}"` |
| This release | the wheel and the sdist attached below |
| Source | `git clone --branch v{version} {REPO}` |

Every SetuHQ output is a candidate, never a confirmation.

The attached files carry a build-provenance attestation from the release workflow; check one with
`gh attestation verify <file> --repo ashfordeOU/SetuHQ`.

**Full changelog:** [`CHANGELOG.md`]({REPO}/blob/v{version}/CHANGELOG.md) · **Cite:** [`CITATION.cff`]({REPO}/blob/v{version}/CITATION.cff)
"""


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: changelog_extract.py <version>   (e.g. 0.1.0)", file=sys.stderr)
        return 2
    version = argv[0].removeprefix("v")
    try:
        sys.stdout.write(notes(version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")))
    except LookupError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

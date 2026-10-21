#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Set a release's date in CHANGELOG.md (``## [X.Y.Z] - YYYY-MM-DD``) and CITATION.cff (``date-released``).

Run it in the release pull request, with the day the tag will be pushed (default: today, UTC). The two dates must
agree; scripts/check_version_sync.py fails when they do not.

    python3 scripts/set_release_date.py 0.1.0 2026-10-21
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def set_date(version: str, date: str, root: Path = ROOT) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError(f"{date!r} is not YYYY-MM-DD")
    cl = root / "CHANGELOG.md"
    text, n = re.subn(rf"(?m)^## \[{re.escape(version)}\](?: - \S+)?\s*$", f"## [{version}] - {date}",
                      cl.read_text(encoding="utf-8"), count=1)
    if not n:
        raise LookupError(f"CHANGELOG.md has no '## [{version}]' heading")
    cl.write_text(text, encoding="utf-8")
    cff = root / "CITATION.cff"
    text, n = re.subn(r'(?m)^date-released:.*$', f'date-released: "{date}"', cff.read_text(encoding="utf-8"), count=1)
    if not n:
        raise LookupError("CITATION.cff has no date-released line")
    cff.write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (1, 2):
        print("usage: set_release_date.py <version> [YYYY-MM-DD]", file=sys.stderr)
        return 2
    date = argv[1] if len(argv) == 2 else datetime.now(timezone.utc).date().isoformat()
    set_date(argv[0].removeprefix("v"), date)
    print(f"CHANGELOG.md [{argv[0]}] and CITATION.cff date-released set to {date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

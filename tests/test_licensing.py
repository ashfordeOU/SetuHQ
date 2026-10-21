# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The licensing set: AGPL-3.0-only or a commercial licence for the code, CC BY 4.0 for the data, an SPDX header on
every source file, and nothing left that says MIT."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_licence_files_and_metadata_agree():
    assert (ROOT / "LICENSE").read_text().lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE")
    assert "Version 3, 19 November 2007" in (ROOT / "LICENSE").read_text()
    for name in ("LICENSING.md", "NOTICE", "TRADEMARKS.md", "CLA.md"):
        assert (ROOT / name).is_file(), name
    lic = (ROOT / "LICENSING.md").read_text()
    assert "AGPL-3.0-only" in lic and "contact@ashforde.org" in lic and "CC BY 4.0" in lic and "not legal advice" in lic
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    assert tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["license"] == "AGPL-3.0-only"
    for p in (".claude-plugin/plugin.json",):
        assert json.loads((ROOT / p).read_text())["license"] == "AGPL-3.0-only"
    cff = (ROOT / "CITATION.cff").read_text()
    assert "license:\n  - AGPL-3.0-only\n  - CC-BY-4.0\n" in cff
    assert json.loads((ROOT / "codemeta.json").read_text())["license"] == [
        "https://spdx.org/licenses/AGPL-3.0-only", "https://spdx.org/licenses/CC-BY-4.0"]
    for d in ("results", "leaderboard", "sweep", "discoveries", "paper"):
        assert "CC-BY-4.0" in (ROOT / "docs" / d / "LICENSE.md").read_text(), d


def test_every_source_file_carries_an_spdx_header():
    files = subprocess.run(["git", "ls-files", "*.py", "*.mjs", "*.js", "*.sh", "*.css"], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.split()
    # Vendored third-party files (tests/e2e/vendor/) keep their own licence header, named in NOTICE.
    vendored = [f for f in files if "/vendor/" in f]
    missing = [f for f in files if not f.startswith("site/") and f not in vendored and (ROOT / f).exists()
               and "SPDX-License-Identifier: AGPL-3.0-only" not in (ROOT / f).read_text(encoding="utf-8")[:400]]
    assert not missing, missing
    notice = (ROOT / "NOTICE").read_text()
    for f in vendored:
        assert f in notice and "License" in (ROOT / f).read_text(encoding="utf-8")[:400], f

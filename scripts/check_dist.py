#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Check what the built distributions carry before anything is uploaded.

The wheel must hold the package with its type marker, its fonts and their licences, the licence files and the
console scripts, and nothing else of the repository; the sdist must hold the package, pyproject.toml and the PyPI
README, and none of the data: the stored runs, the site, the results and figures under docs/, caches, tests or
tools. Both stay under a size limit, so a data file pulled in by mistake fails here rather than on PyPI.

    python3 scripts/check_dist.py dist/
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

MAX_WHEEL_BYTES = 5_000_000
MAX_SDIST_BYTES = 5_000_000
# Top-level directories of the repository that are data, generated output or development tools.
FORBIDDEN = ("runs/", "site/", "docs/", "cache/", "data/", "tests/", "tools/", "scripts/", "examples/", "configs/",
             "paper/", ".github/", ".venv/")
WHEEL_REQUIRED = ("setuhq/__init__.py", "setuhq/py.typed", "setuhq/mcp_server.py", "setuhq/tools.py",
                  "setuhq/fonts/fonts.css", "setuhq/fonts/OFL-geist.txt",
                  "setuhq/data/claret2017_tess_quadratic.json", "setuhq/data/secondary_calibration.json")
WHEEL_LICENCES = ("LICENSE", "NOTICE", "LICENSING.md")
SDIST_REQUIRED = ("pyproject.toml", "README.pypi.md", "PKG-INFO", "LICENSE", "src/setuhq/__init__.py",
                  "src/setuhq/py.typed", "src/setuhq/data/claret2017_tess_quadratic.json")


def check_wheel(path: Path) -> list[str]:
    problems = []
    if path.stat().st_size > MAX_WHEEL_BYTES:
        problems.append(f"{path.name}: {path.stat().st_size} bytes, over {MAX_WHEEL_BYTES}")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        info = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        meta = z.read(info).decode() if info else ""
        entry = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
        scripts = z.read(entry).decode() if entry else ""
    for req in WHEEL_REQUIRED:
        if req not in names:
            problems.append(f"{path.name}: missing {req}")
    for lic in WHEEL_LICENCES:
        if not any(n.endswith(f".dist-info/licenses/{lic}") for n in names):
            problems.append(f"{path.name}: missing licence file {lic}")
    for n in names:
        if not (n.startswith("setuhq/") or ".dist-info/" in n):
            problems.append(f"{path.name}: unexpected top-level file {n}")
    if "License-Expression: AGPL-3.0-only" not in meta:
        problems.append(f"{path.name}: METADATA lacks License-Expression: AGPL-3.0-only")
    if "Description-Content-Type: text/markdown" not in meta or "mcp-name: io.github.ashfordeOU/setuhq" not in meta:
        problems.append(f"{path.name}: METADATA lacks the markdown README.pypi.md with its mcp-name marker")
    exact = [line for line in meta.splitlines() if line.startswith("Requires-Dist:") and "==" in line]
    if exact:
        problems.append(f"{path.name}: the published metadata pins exact versions: {exact}")
    for script in ("setuhq = setuhq.cli:main", "setuhq-mcp = setuhq.mcp_server:main"):
        if script not in scripts:
            problems.append(f"{path.name}: entry point missing: {script}")
    return problems


def check_sdist(path: Path) -> list[str]:
    problems = []
    if path.stat().st_size > MAX_SDIST_BYTES:
        problems.append(f"{path.name}: {path.stat().st_size} bytes, over {MAX_SDIST_BYTES}")
    with tarfile.open(path) as t:
        names = [m.name.split("/", 1)[1] for m in t.getmembers() if "/" in m.name]
    for req in SDIST_REQUIRED:
        if req not in names:
            problems.append(f"{path.name}: missing {req}")
    for n in names:
        if n.startswith(FORBIDDEN) or "__pycache__" in n or n.endswith((".pyc", ".sqlite")):
            problems.append(f"{path.name}: carries {n}, which is data, output or tooling")
    return problems


def check(dist: Path) -> list[str]:
    wheels, sdists = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    problems = []
    if len(wheels) != 1 or len(sdists) != 1:
        problems.append(f"{dist}: expected one wheel and one sdist, found {[p.name for p in wheels + sdists]}")
    for w in wheels:
        problems += check_wheel(w)
    for s in sdists:
        problems += check_sdist(s)
    return problems


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dist = Path(argv[0] if argv else "dist")
    problems = check(dist)
    for p in problems:
        print(f"FAIL: {p}", file=sys.stderr)
    if problems:
        return 1
    for p in sorted(dist.iterdir()):
        print(f"OK: {p.name} ({p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

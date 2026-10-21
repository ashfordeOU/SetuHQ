#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Check that every file stating SetuHQ's version states the same one, and that a release tag matches it.

The version is written once, as ``__version__`` in ``src/setuhq/__init__.py``; pyproject.toml reads it from there
(``dynamic = ["version"]``), so the wheel and the sdist cannot drift. Every other file that writes a version down is
checked against it here:

- CITATION.cff ``version``, codemeta.json ``version``, .zenodo.json ``version``;
- server.json ``version`` and the version of each of its packages (the MCP registry entry);
- .claude-plugin/plugin.json ``version`` and .claude-plugin/marketplace.json ``plugins[].version``;
- smithery.yaml (the pinned ``setuhq[mcp]==X`` in its start command);
- CHANGELOG.md has a ``## [X]`` section (the release notes are that section);
- README.pypi.md names the same MCP server as server.json (the registry's ownership marker).

With a release tag (``--tag vX.Y.Z``, or ``GITHUB_REF_TYPE=tag`` and ``GITHUB_REF_NAME`` as GitHub Actions sets
them), the tag must be ``v`` plus that version. Exit status 1 on any mismatch, with one line per problem.

    python3 scripts/check_version_sync.py
    python3 scripts/check_version_sync.py --tag v0.1.0
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_version(root: Path = ROOT) -> str:
    """``__version__`` from src/setuhq/__init__.py, read without importing the package."""
    tree = ast.parse((root / "src/setuhq/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "__version__" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("src/setuhq/__init__.py has no __version__")


def _json(root: Path, rel: str):
    return json.loads((root / rel).read_text(encoding="utf-8"))


def check(root: Path = ROOT, tag: str | None = None) -> tuple[str, list[str]]:
    """Return (version, problems). An empty list means every surface agrees."""
    ver = source_version(root)
    problems: list[str] = []

    def same(label: str, got) -> None:
        if got != ver:
            problems.append(f"{label} is {got!r}, src/setuhq/__init__.py says {ver!r}")

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", ver):
        problems.append(f"__version__ {ver!r} is not X.Y.Z (optionally aN, bN or rcN)")

    py = (root / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"(?ms)^\[project\]\n(.*?)(?=^\[)", py)
    project = project.group(1) if project else ""
    if re.search(r"(?m)^version\s*=", project):
        problems.append("pyproject.toml [project] states a static version; it must stay dynamic (read from "
                        "setuhq.__version__)")
    if not re.search(r'(?m)^dynamic\s*=\s*\[[^\]]*"version"', project) \
            or 'version = { attr = "setuhq.__version__" }' not in py:
        problems.append('pyproject.toml must have dynamic = ["version"] with version = { attr = "setuhq.__version__" }')

    cff = re.search(r'(?m)^version:\s*"?([^"\s]+)"?\s*$', (root / "CITATION.cff").read_text(encoding="utf-8"))
    same("CITATION.cff version", cff.group(1) if cff else None)
    same("codemeta.json version", _json(root, "codemeta.json").get("version"))
    same(".zenodo.json version", _json(root, ".zenodo.json").get("version"))

    server = _json(root, "server.json")
    same("server.json version", server.get("version"))
    for i, pkg in enumerate(server.get("packages", [])):
        same(f"server.json packages[{i}].version", pkg.get("version"))
        if pkg.get("registryType") == "pypi" and pkg.get("identifier") != "setuhq":
            problems.append(f"server.json packages[{i}] names PyPI package {pkg.get('identifier')!r}, not 'setuhq'")

    same(".claude-plugin/plugin.json version", _json(root, ".claude-plugin/plugin.json").get("version"))
    for i, plugin in enumerate(_json(root, ".claude-plugin/marketplace.json").get("plugins", [])):
        same(f".claude-plugin/marketplace.json plugins[{i}].version", plugin.get("version"))

    pins = re.findall(r"setuhq\[mcp\]==([0-9A-Za-z.]+)", (root / "smithery.yaml").read_text(encoding="utf-8"))
    if not pins:
        problems.append("smithery.yaml does not pin setuhq[mcp]==<version> in its start command")
    for pin in pins:
        same("smithery.yaml setuhq[mcp] pin", pin)

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"(?m)^## \[{re.escape(ver)}\]", changelog):
        problems.append(f"CHANGELOG.md has no '## [{ver}]' section (the release notes are taken from it)")

    marker = re.search(r"mcp-name:\s*(\S+)", (root / "README.pypi.md").read_text(encoding="utf-8"))
    if not marker or marker.group(1) != server.get("name"):
        problems.append(f"README.pypi.md mcp-name marker {marker.group(1) if marker else None!r} "
                        f"!= server.json name {server.get('name')!r}")

    if tag is not None and tag != f"v{ver}":
        problems.append(f"release tag {tag!r} does not match the version: expected 'v{ver}'")
    return ver, problems


def _tag_from_env() -> str | None:
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        return os.environ.get("GITHUB_REF_NAME")
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tag", help="a release tag to check against the version, e.g. v0.1.0 (default: the GitHub "
                                      "Actions tag ref, if any)")
    parser.add_argument("--print-version", action="store_true", help="print the version and exit")
    args = parser.parse_args(argv)
    if args.print_version:
        print(source_version())
        return 0
    tag = args.tag or _tag_from_env()
    ver, problems = check(ROOT, tag)
    for p in problems:
        print(f"FAIL: {p}", file=sys.stderr)
    if problems:
        print(f"version drift: bring every surface to the version in src/setuhq/__init__.py ({ver})", file=sys.stderr)
        return 1
    print(f"OK: every surface states {ver}" + (f"; tag {tag} matches" if tag else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

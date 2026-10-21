# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The release machinery: one version everywhere, a registry entry the MCP registry accepts, a PyPI page with absolute
links, distributions without data, workflows pinned by commit SHA with no token, and the community files."""

import importlib.util
import io
import json
import re
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_WORKFLOWS = ("release.yml", "publish.yml", "auto-tag.yml", "release-notes.yml", "mcp-publish.yml",
                     "joss-draft.yml")


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- one version


def test_every_version_surface_agrees():
    sync = _script("check_version_sync")
    ver, problems = sync.check(ROOT)
    assert problems == []
    import setuhq
    assert ver == setuhq.__version__
    assert sync.check(ROOT, tag=f"v{ver}")[1] == []


def _copy_surfaces(tmp: Path) -> Path:
    for rel in ("src/setuhq/__init__.py", "pyproject.toml", "CITATION.cff", "codemeta.json", ".zenodo.json",
                "server.json", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", "smithery.yaml",
                "CHANGELOG.md", "README.pypi.md"):
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp / rel)
    return tmp


@pytest.mark.parametrize("rel, old, new", [
    ("codemeta.json", '"version": "{v}"', '"version": "9.9.9"'),
    (".zenodo.json", '"version": "{v}"', '"version": "9.9.9"'),
    ("CITATION.cff", "version: {v}", "version: 9.9.9"),
    ("server.json", '"version": "{v}"', '"version": "9.9.9"'),
    (".claude-plugin/plugin.json", '"version": "{v}"', '"version": "9.9.9"'),
    ("smithery.yaml", "setuhq[mcp]=={v}", "setuhq[mcp]==9.9.9"),
    ("pyproject.toml", 'dynamic = ["version"]', 'version = "{v}"'),
    ("README.pypi.md", "mcp-name: io.github.ashfordeOU/setuhq", "mcp-name: io.github.someone/else"),
])
def test_a_drifted_surface_fails_the_check(tmp_path, rel, old, new):
    sync = _script("check_version_sync")
    ver = sync.source_version(ROOT)
    root = _copy_surfaces(tmp_path)
    text = (root / rel).read_text(encoding="utf-8")
    old, new = old.format(v=ver), new.format(v=ver)
    assert old in text, (rel, old)
    (root / rel).write_text(text.replace(old, new, 1), encoding="utf-8")
    assert sync.check(root)[1], rel


def test_a_wrong_tag_and_a_missing_changelog_section_fail(tmp_path):
    sync = _script("check_version_sync")
    ver = sync.source_version(ROOT)
    assert sync.check(ROOT, tag="v0.0.0-wrong")[1]
    root = _copy_surfaces(tmp_path)
    cl = root / "CHANGELOG.md"
    cl.write_text(cl.read_text(encoding="utf-8").replace(f"## [{ver}]", "## [0.0.0]"), encoding="utf-8")
    assert any("CHANGELOG" in p for p in sync.check(root)[1])


def test_release_notes_are_the_changelog_section():
    extract = _script("changelog_extract")
    ver = _script("check_version_sync").source_version(ROOT)
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = extract.notes(ver, changelog)
    assert extract.section(ver, changelog).strip() in notes
    assert f"pip install \"setuhq[mcp]=={ver}\"" in notes and "candidate, never a confirmation" in notes
    assert "## [Unreleased]" not in notes
    with pytest.raises(LookupError):
        extract.notes("99.99.99", changelog)


# ---------------------------------------------------------------- packaging


def test_pyproject_packaging():
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'readme = { file = "README.pypi.md", content-type = "text/markdown" }' in py
    assert '"py.typed"' in py and (ROOT / "src/setuhq/py.typed").is_file()
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    for d in ("runs", "site", "docs", "cache", "tests", "tools"):
        assert f"prune {d}\n" in manifest, d


PACKAGE_DATA = ("claret2017_tess_quadratic.json", "secondary_calibration.json")


@pytest.mark.parametrize("name", PACKAGE_DATA)
def test_package_data_is_byte_identical_to_docs_results(name):
    """docs/results holds the canonical tables; the package ships copies so a wheel runs without a checkout. A
    re-run that rewrites a table in docs/results fails here until the copy in src/setuhq/data is synced:
    cp docs/results/<name> src/setuhq/data/<name>."""
    canonical = (ROOT / "docs" / "results" / name).read_bytes()
    shipped = (ROOT / "src" / "setuhq" / "data" / name).read_bytes()
    assert shipped == canonical, f"src/setuhq/data/{name} differs from docs/results/{name}: copy it over"


def test_the_fit_and_the_vetting_read_the_package_copies():
    from setuhq import dvtests, transitfit

    assert transitfit.LD_TABLE.read_bytes() == (ROOT / "docs/results/claret2017_tess_quadratic.json").read_bytes()
    assert dvtests.CALIBRATION_FILE.read_bytes() == (ROOT / "docs/results/secondary_calibration.json").read_bytes()
    assert "src/setuhq/data" in str(transitfit.LD_TABLE).replace("\\", "/")
    assert sorted(p.name for p in (ROOT / "src/setuhq/data").iterdir()) == sorted(PACKAGE_DATA)


def test_pypi_readme_has_only_absolute_links_and_honest_wording():
    text = (ROOT / "README.pypi.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", text) + re.findall(r'(?:src|href|srcset)="([^"]+)"', text)
    assert links
    for link in links:
        assert link.startswith(("https://", "mailto:")), link
    low = text.lower()
    assert "candidate, never a confirmation" in low
    for word in ("superintelligence", "confirmed planet", "discovered"):
        assert word not in low, word
    # No result numbers on the PyPI page: they change with every re-run and live in the repository.
    assert not re.search(r"\d+(\.\d+)?\s?%", text)


def _wheel(tmp: Path, extra: dict[str, bytes] | None = None) -> Path:
    path = tmp / "setuhq-0.1.0-py3-none-any.whl"
    files = {n: b"" for n in _script("check_dist").WHEEL_REQUIRED}
    meta = ("Metadata-Version: 2.4\nName: setuhq\nLicense-Expression: AGPL-3.0-only\n"
            "Description-Content-Type: text/markdown\n\n<!-- mcp-name: io.github.ashfordeOU/setuhq -->\n")
    files["setuhq-0.1.0.dist-info/METADATA"] = meta.encode()
    files["setuhq-0.1.0.dist-info/entry_points.txt"] = (b"[console_scripts]\nsetuhq = setuhq.cli:main\n"
                                                        b"setuhq-mcp = setuhq.mcp_server:main\n")
    for lic in ("LICENSE", "NOTICE", "LICENSING.md"):
        files[f"setuhq-0.1.0.dist-info/licenses/{lic}"] = b""
    files.update(extra or {})
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


def _sdist(tmp: Path, extra: tuple[str, ...] = ()) -> Path:
    path = tmp / "setuhq-0.1.0.tar.gz"
    with tarfile.open(path, "w:gz") as t:
        for name in (*_script("check_dist").SDIST_REQUIRED, *extra):
            info = tarfile.TarInfo(f"setuhq-0.1.0/{name}")
            t.addfile(info, io.BytesIO(b""))
    return path


def test_dist_check_passes_a_clean_pair_and_catches_data(tmp_path):
    check_dist = _script("check_dist")
    good = tmp_path / "good"
    good.mkdir()
    _wheel(good)
    _sdist(good)
    assert check_dist.check(good) == []
    bad = tmp_path / "bad"
    bad.mkdir()
    _wheel(bad, {"runs/tess-pi-men-s1/candidates.json": b"[]"})
    _sdist(bad, ("site/index.html", "docs/assets/readme/app/shot.png", "cache/x.json"))
    problems = check_dist.check(bad)
    assert any("runs/tess-pi-men-s1" in p for p in problems)
    for leaked in ("site/index.html", "docs/assets", "cache/x.json"):
        assert any(leaked in p for p in problems), leaked


# ---------------------------------------------------------------- the MCP registry entry


def test_server_json_is_valid_against_the_registry_schema():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "packaging/mcp/server.schema.json").read_text(encoding="utf-8"))
    assert server["$schema"] == schema["$id"]
    assert server["name"] == "io.github.ashfordeOU/setuhq"
    assert len(server["description"]) <= 100
    (pkg,) = server["packages"]
    assert (pkg["registryType"], pkg["identifier"], pkg["transport"]["type"]) == ("pypi", "setuhq", "stdio")
    assert server["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]["command"] == "setuhq-mcp"
    jsonschema = pytest.importorskip("jsonschema")
    cls = jsonschema.validators.validator_for(schema)
    cls(schema, format_checker=jsonschema.FormatChecker()).validate(server)


def test_directory_listings():
    assert json.loads((ROOT / "glama.json").read_text(encoding="utf-8"))["maintainers"] == ["ashfordeOU"]
    smithery = (ROOT / "smithery.yaml").read_text(encoding="utf-8")
    assert 'type: "stdio"' in smithery and "setuhq-mcp" in smithery
    assert "build:" not in smithery and "dockerfile" not in smithery.lower()
    zen = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert zen["creators"] == [{"name": "Baweja, Chakshu", "affiliation": "Ashforde OÜ"}]
    assert zen["license"] == "AGPL-3.0-only" and zen["upload_type"] == "software"
    related = {r["identifier"] for r in zen["related_identifiers"]}
    assert {"https://github.com/ashfordeOU/SetuHQ", "https://setuhq.com"} <= related
    assert "candidate, never a confirmation" in zen["description"]


# ---------------------------------------------------------------- workflows


def _uses(text: str) -> list[str]:
    return re.findall(r"^\s*(?:-\s*)?uses:\s*(.+?)\s*$", text, flags=re.M)


@pytest.mark.parametrize("name", RELEASE_WORKFLOWS)
def test_workflow_actions_are_pinned_by_commit_sha(name):
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    assert text.startswith("# SPDX-License-Identifier: AGPL-3.0-only"), name
    uses = _uses(text)
    assert uses, name
    for u in uses:
        if u.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}\s+#\s*v\d[\w.]*", u), u


def test_no_tokens_in_the_publishing_path():
    for name in ("release.yml", "publish.yml", "mcp-publish.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "secrets." not in text, name
        assert "password:" not in text and "PYPI_API_TOKEN" not in text, name
    publish = (WORKFLOWS / "publish.yml").read_text(encoding="utf-8")
    assert "name: pypi" in publish and "id-token: write" in publish and "pypa/gh-action-pypi-publish@" in publish
    assert "workflows: [Release]" in publish
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in release and "attest-build-provenance@" in release and "twine check" in release
    assert "workflow_dispatch:" in release and "dry_run" in release
    mcp = (WORKFLOWS / "mcp-publish.yml").read_text(encoding="utf-8")
    assert "login github-oidc" in mcp and "push:" not in mcp and "workflow_run" not in mcp
    auto = (WORKFLOWS / "auto-tag.yml").read_text(encoding="utf-8")
    assert "vars.AUTO_TAG == 'true'" in auto


# ---------------------------------------------------------------- community files and the paper


def test_issue_and_pull_request_templates():
    tpl = ROOT / ".github" / "ISSUE_TEMPLATE"
    candidate = (tpl / "candidate_question.yml").read_text(encoding="utf-8")
    assert "candidates, never confirmations" in candidate
    for field in ("id: tic", "id: sector", "id: docket"):
        assert field in candidate, field
    for name in ("bug_report.yml", "feature_request.yml"):
        assert (tpl / name).is_file()
    config = (tpl / "config.yml").read_text(encoding="utf-8")
    assert "security/advisories/new" in config and "contact@ashforde.org" in config
    pr = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    assert "CLA.md" in pr and "pytest" in pr and "gen_readme_assets.py --check" in pr
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert "package-ecosystem: pip" in dependabot and "package-ecosystem: github-actions" in dependabot
    assert dependabot.count("interval: weekly") == 2 and dependabot.count("groups:") == 2
    assert (ROOT / ".editorconfig").is_file()
    for path in (*tpl.iterdir(), ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"):
        assert "superintelligence" not in path.read_text(encoding="utf-8").lower()


def test_joss_paper_cites_only_what_its_bibliography_holds():
    paper = (ROOT / "paper" / "paper.md").read_text(encoding="utf-8")
    front, body = paper.split("---", 2)[1:]
    for key in ("title:", "authors:", "affiliations:", "date:", "bibliography: paper.bib", "orcid:"):
        assert key in front, key
    for heading in ("# Summary", "# Statement of need", "# State of the field", "# Acknowledgements", "# References"):
        assert heading in body, heading
    bib = (ROOT / "paper" / "paper.bib").read_text(encoding="utf-8")
    keys = set(re.findall(r"^@\w+\{([^,]+),", bib, flags=re.M))
    cited = set(re.findall(r"@([a-z][a-z0-9]+)", re.sub(r"<!--.*?-->", "", body, flags=re.S)))
    assert cited and cited <= keys, cited - keys
    low = body.lower()
    assert "superintelligence" not in low and "we discovered" not in low

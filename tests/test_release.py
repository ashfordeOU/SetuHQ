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
RELEASE_WORKFLOWS = ("release.yml", "auto-tag.yml", "release-notes.yml", "mcp-publish.yml",
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


def test_a_tag_needs_an_empty_unreleased_section_and_matching_dates(tmp_path):
    sync = _script("check_version_sync")
    setter = _script("set_release_date")
    ver = sync.source_version(ROOT)
    root = _copy_surfaces(tmp_path)
    cl = root / "CHANGELOG.md"
    setter.set_date(ver, "2031-02-03", root)
    assert f"## [{ver}] - 2031-02-03" in cl.read_text(encoding="utf-8")
    assert 'date-released: "2031-02-03"' in (root / "CITATION.cff").read_text(encoding="utf-8")
    text = cl.read_text(encoding="utf-8")
    empty = text.replace("## [Unreleased]\n", "## [Unreleased]\n\n", 1)
    cl.write_text(empty, encoding="utf-8")
    assert sync.check(root, tag=f"v{ver}")[1] == []
    cl.write_text(text.replace("## [Unreleased]\n", "## [Unreleased]\n\n- a change not in the release\n", 1),
                  encoding="utf-8")
    assert sync.check(root)[1] == []  # between releases [Unreleased] may hold entries
    assert any("[Unreleased]" in p for p in sync.check(root, tag=f"v{ver}")[1])
    cl.write_text(empty.replace(f"## [{ver}] - 2031-02-03", f"## [{ver}] - 2031-02-04"), encoding="utf-8")
    assert any("date-released" in p for p in sync.check(root)[1])
    cl.write_text(empty.replace(f"## [{ver}] - 2031-02-03", f"## [{ver}]"), encoding="utf-8")
    assert any("no YYYY-MM-DD date" in p for p in sync.check(root)[1])


def test_set_release_date_rejects_impossible_days_and_keeps_the_blank_line(tmp_path):
    setter = _script("set_release_date")
    ver = _script("check_version_sync").source_version(ROOT)
    root = _copy_surfaces(tmp_path)
    for bad in ("2026-02-30", "2026-13-01", "20261021", "2026-1-2"):
        with pytest.raises(ValueError):
            setter.set_date(ver, bad, root)
    before = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    setter.set_date(ver, "2031-02-03", root)
    after = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{ver}] - 2031-02-03\n\n" in after
    assert after.count("\n") == before.count("\n")  # the heading line only, no blank line swallowed


def test_the_drift_hint_appears_only_on_version_drift(monkeypatch, capsys):
    sync = _script("check_version_sync")
    monkeypatch.setattr(sync, "check", lambda root, tag: ("0.1.0", ["CHANGELOG.md '## [0.1.0]' has no YYYY-MM-DD date"]))
    assert sync.main([]) == 1
    assert "version drift" not in capsys.readouterr().err
    monkeypatch.setattr(sync, "check", lambda root, tag: ("0.1.0", [f"codemeta.json version is '0.0.9', {sync.DRIFT} '0.1.0'"]))
    assert sync.main([]) == 1
    assert "version drift" in capsys.readouterr().err


def test_release_notes_are_the_changelog_section():
    extract = _script("changelog_extract")
    assert _script("check_version_sync").check(ROOT, tag=None)[1] == []
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
    # The README figures' exact pins live in requirements-readme.txt, not in the published metadata.
    assert "readme = [" not in py and "==" not in py.split("[project.scripts]")[0]
    assert "fonttools==" in (ROOT / "requirements-readme.txt").read_text(encoding="utf-8")
    # setuhq.config reads TOML with tomllib, in the standard library from Python 3.11.
    assert 'requires-python = ">=3.11"' in py and "Python :: 3.10" not in py and "Python :: 3.11" in py
    assert json.loads((ROOT / "codemeta.json").read_text(encoding="utf-8"))["runtimePlatform"] == "Python 3.11+"
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


def test_exact_pins_reads_specifiers_not_markers():
    exact_pins = _script("check_dist").exact_pins
    meta = ("Metadata-Version: 2.4\nName: setuhq\nRequires-Dist: numpy>=1.24\n"
            'Requires-Dist: lightkurve>=2.4; extra == "tess"\n'
            'Requires-Dist: mcp>=1.10; extra == "mcp" and python_version >= "3.11"\n'
            "Provides-Extra: tess\n\nbody text with Requires-Dist: x==1 is not a header\n")
    assert exact_pins(meta) == []
    pinned = meta.replace("numpy>=1.24", "numpy==2.5.4").replace('lightkurve>=2.4; extra', 'lightkurve===2.4; extra')
    assert exact_pins(pinned) == ["numpy==2.5.4", 'lightkurve===2.4; extra == "tess"']


def test_the_real_package_metadata_passes_the_dist_check(tmp_path, monkeypatch):
    """Generate METADATA from the real pyproject.toml with the build backend and check it as the release job does:
    every extra's marker (extra == "...") must not read as an exact pin."""
    build_meta = pytest.importorskip("setuptools.build_meta")
    src = tmp_path / "src"
    for rel in ("pyproject.toml", "README.pypi.md", "LICENSE", "NOTICE", "LICENSING.md", "src/setuhq/__init__.py"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, src / rel)
    out = tmp_path / "meta"
    out.mkdir()
    monkeypatch.chdir(src)
    info = build_meta.prepare_metadata_for_build_wheel(str(out))
    meta = (out / info / "METADATA").read_text(encoding="utf-8")
    assert 'extra == "tess"' in meta and "Requires-Dist: numpy" in meta  # the markers really are there
    check_dist = _script("check_dist")
    assert check_dist.exact_pins(meta) == []
    good = tmp_path / "dist"
    good.mkdir()
    _wheel(good, {"setuhq-0.1.0.dist-info/METADATA": meta.encode()})
    assert check_dist.check_wheel(good / "setuhq-0.1.0-py3-none-any.whl") == []


def test_dist_check_passes_a_clean_pair_and_catches_data(tmp_path):
    check_dist = _script("check_dist")
    good = tmp_path / "good"
    good.mkdir()
    _wheel(good)
    _sdist(good)
    assert check_dist.check(good) == []
    bad = tmp_path / "bad"
    bad.mkdir()
    _wheel(bad, {"runs/tess-pi-men-s1/candidates.json": b"[]",
                 "setuhq-0.1.0.dist-info/METADATA": b"Requires-Dist: numpy==2.5.4\n"})
    _sdist(bad, ("site/index.html", "docs/assets/readme/app/shot.png", "cache/x.json"))
    problems = check_dist.check(bad)
    assert any("runs/tess-pi-men-s1" in p for p in problems)
    assert any("pins exact versions" in p for p in problems)
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
    assert server["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]["command"] == "setuhq mcp"
    # The registry entry launches `uvx --with=<the mcp extra> setuhq==<version> mcp`: the package's own command with
    # the `mcp` subcommand, and the SDK the extra names.
    assert pkg["runtimeHint"] == "uvx"
    assert pkg["packageArguments"] == [{"type": "positional", "value": "mcp", "description": pkg["packageArguments"][0]["description"]}]
    (with_sdk,) = pkg["runtimeArguments"]
    extra = re.search(r'^mcp = \[(.*)\]', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), flags=re.M).group(1)
    assert (with_sdk["type"], with_sdk["name"]) == ("named", "--with") and f'"{with_sdk["value"]}"' == extra.strip()
    jsonschema = pytest.importorskip("jsonschema")
    cls = jsonschema.validators.validator_for(schema)
    cls(schema, format_checker=jsonschema.FormatChecker()).validate(server)


def test_directory_listings():
    assert json.loads((ROOT / "glama.json").read_text(encoding="utf-8"))["maintainers"] == ["ashfordeOU"]
    smithery = (ROOT / "smithery.yaml").read_text(encoding="utf-8")
    assert 'type: "stdio"' in smithery and '"setuhq", "mcp"' in smithery
    assert "build:" not in smithery and "dockerfile" not in smithery.lower()
    zen = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert zen["creators"] == [{"name": "Baweja, Chakshu", "affiliation": "Ashforde OÜ", "orcid": "0009-0008-2098-0751"}]
    assert zen["license"] == "agpl-3.0-only"  # the id in Zenodo's licence vocabulary (lower case)
    assert zen["upload_type"] == "software"
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
    for name in ("release.yml", "mcp-publish.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "secrets." not in text, name
        assert "password:" not in text and "PYPI_API_TOKEN" not in text, name
    assert not (WORKFLOWS / "publish.yml").exists()
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in release and "attest-build-provenance@" in release and "twine check" in release
    assert "workflow_dispatch:" in release and "testpypi" in release


def _jobs(name: str) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))["jobs"]


def test_only_release_yml_publishes_to_pypi_on_a_tag_with_the_attested_files():
    """PyPI matches the trusted publisher on the top-level workflow file and the `pypi` environment only allows
    v* tags, so the publishing job runs inside release.yml on the tag push, after the release job, and uploads the
    run's own `dist` artifact: nothing is rebuilt for PyPI."""
    jobs = _jobs("release.yml")
    pypi = jobs["pypi"]
    assert pypi["environment"]["name"] == "pypi" and pypi["permissions"] == {"id-token": "write"}
    assert pypi["if"] == "${{ github.event_name == 'push' }}" and "release" in pypi["needs"]
    steps = pypi["steps"]
    assert not any("checkout" in st.get("uses", "") or "build" in str(st.get("run", "")) for st in steps)
    assert any(st.get("uses", "").startswith("actions/download-artifact@") and st["with"]["name"] == "dist"
               for st in steps)
    assert jobs["testpypi"]["environment"]["name"] == "testpypi"
    assert "workflow_dispatch" in jobs["testpypi"]["if"] and "repository-url" in str(jobs["testpypi"]["steps"])
    for name in sorted(p.name for p in WORKFLOWS.glob("*.yml")):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        if name != "release.yml":
            assert "gh-action-pypi-publish" not in text and "name: pypi" not in text, name


def test_a_release_rerun_never_replaces_a_file_and_ci_must_be_green_on_main():
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "--clobber" not in release and "cmp -s" in release and "never replaced" in release
    assert "event=push&branch=main" in release and "merge-base --is-ancestor" in release
    assert jobs_have_no_rebuild_on_dispatch(_jobs("release.yml"))


def jobs_have_no_rebuild_on_dispatch(jobs: dict) -> bool:
    return all(jobs[j]["if"] == "${{ github.event_name == 'push' }}" for j in ("release", "pypi"))


def test_every_github_yaml_file_parses():
    yaml = pytest.importorskip("yaml")
    files = [*sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")), ROOT / ".github" / "dependabot.yml",
             *sorted(WORKFLOWS.glob("*.yml")), ROOT / "smithery.yaml"]
    for f in files:
        assert isinstance(yaml.safe_load(f.read_text(encoding="utf-8")), dict), f


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
    assert "security/advisories/new" in config and "contact@ashforde.org" in config and "mailto:" not in config
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
    # JOSS's required sections (joss.readthedocs.io, "What should my paper contain?").
    for heading in ("# Summary", "# Statement of need", "# State of the field", "# Software design",
                    "# Research impact statement", "# AI usage disclosure", "# Acknowledgements", "# References"):
        assert f"\n{heading}\n" in body, heading
    words = len(re.sub(r"<!--.*?-->", "", body, flags=re.S).split())
    assert 750 <= words <= 1750, words
    bib = (ROOT / "paper" / "paper.bib").read_text(encoding="utf-8")
    keys = set(re.findall(r"^@\w+\{([^,]+),", bib, flags=re.M))
    # JOSS asks for full venue names, not abbreviations.
    for abbrev in ("{AJ}", "{ApJ}", "{ApJL}", "{ApJS}", "{MNRAS}", "{PASP}", "{A\\&A}"):
        assert f"journal = {abbrev}" not in bib, abbrev
    cited = set(re.findall(r"@([a-z][a-z0-9]+)", re.sub(r"<!--.*?-->", "", body, flags=re.S)))
    assert cited and cited <= keys, cited - keys
    low = body.lower()
    assert "superintelligence" not in low and "we discovered" not in low


# ---------------------------------------------------------------- setuhq mcp


def test_setuhq_mcp_hands_its_arguments_to_the_server(capsys):
    from setuhq import cli

    assert cli.main(["mcp", "--list-tools"]) == 0
    listed = capsys.readouterr().out.split()
    assert "search_catalogue" in listed and "sentinel_providers" in listed
    assert "mcp" in cli.build_parser()._subparsers._group_actions[0].choices


def test_setuhq_mcp_without_the_sdk_says_which_extra_to_install(monkeypatch, capsys):
    import importlib.util

    from setuhq import cli

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "mcp" else real(name, *a))
    assert cli.main(["mcp"]) == 2
    err = capsys.readouterr().err
    assert "pip install 'setuhq[mcp]'" in err and "uvx --from 'setuhq[mcp]' setuhq mcp" in err
    assert cli.main(["mcp", "--list-tools"]) == 0  # listing the tools needs no SDK

# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The site built from several stored runs, the Probes-only record, and the worked examples' stored files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from setuhq.names import ATTRIBUTION, PROBES_ONLY, dip_count, panel_mode

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "docs/results/showcase.json"


@pytest.fixture(scope="module")
def multi(app_run, story_run, tmp_path_factory):
    """A site from two synthetic runs: app_run leads, story_run is a second example run."""
    from setuhq.site import build_site

    out = tmp_path_factory.mktemp("multi") / "site"
    build_site(app_run, out, title="t", extra_runs=[story_run], showcase_path=None)
    return out


def _data(site: Path) -> dict:
    return json.loads(next(site.glob("assets/data/app-*.json")).read_text())


def test_a_probes_only_run_says_so_in_its_manifest(story_run):
    m = json.loads((Path(story_run) / "manifest.json").read_text())
    assert m["panel"]["mode"] == "probes_only" and m["panel"]["note"] == PROBES_ONLY
    assert panel_mode(m) == "probes_only" and "code" in m
    assert panel_mode({"reviewers": [{"kind": "claude_code"}]}) == "probes_and_sentinels"


def test_every_run_gets_its_dips_case_file_plates_and_report(multi):
    data = _data(multi)
    cards = data["showcase"]
    assert [c["lead"] for c in cards] == [True, False]
    second = cards[1]
    assert second["slug"] and second["case_file"] == f"/candidates/{second['slug']}/case-file/"
    pages = json.loads((multi / "assets" / "pages.json").read_text())
    standalone = json.loads((multi / "assets" / "standalone.json").read_text())
    for path in (second["case_file"], second["plates"], second["report"]):
        assert path in pages and path in standalone
        html = (multi / path.strip("/") / "index.html").read_text()
        assert f'<link rel="canonical" href="https://setuhq.com{path}">' in html, path
        assert PROBES_ONLY in html, path
    # Each of the second run's dips has its page, at its own star's address, with its run named.
    for d in second["dips"]:
        slug = data["routes"]["dips"][d["id"]]
        assert slug.startswith(second["slug"] + "/dip-")
        assert (multi / "candidates" / slug / "index.html").exists() and (multi / "candidates" / slug / "case-file" / "index.html").exists()
        assert data["dips"][d["id"]]["run"] == second["run"]
    assert {d["run"] for d in data["showcase_dips"]} == {second["run"]}
    assert set(data["docket_frames"]) == {c["run"] for c in cards}
    assert data["run_ctx"][second["run"]]["probes_only"] is True


def test_the_home_page_shows_every_example_with_its_dip_count(multi):
    home = (multi / "index.html").read_text()
    gallery = re.search(r'<section class="examples".*?</section>', home, re.S).group(0)
    data = _data(multi)
    for c in data["showcase"]:
        assert c["count"] == dip_count([d["outcome"] for d in c["dips"]])
        assert c["count"] in gallery and c["star"] in gallery
        assert c["case_file"] in gallery
    assert PROBES_ONLY in gallery
    assert home.index('class="dohere"') < home.index('class="examples"') < home.index('class="proof"')
    cands = (multi / "candidates" / "index.html").read_text()
    for c in data["showcase"]:
        assert f'id="h-run-{c["slug"]}"' in cands


def test_the_build_is_deterministic(app_run, story_run, multi, tmp_path):
    from setuhq.site import build_site

    again = tmp_path / "site"
    build_site(app_run, again, title="t", extra_runs=[story_run], showcase_path=None)
    assert (again / "index.html").read_text() == (multi / "index.html").read_text()


def test_two_runs_cannot_share_a_dip_address(app_run, tmp_path):
    from setuhq.site import build_site

    with pytest.raises(ValueError, match="already taken"):
        build_site(app_run, tmp_path / "s", title="t", extra_runs=[app_run], showcase_path=None, extras=False)


# ---------------------------------------------------------------- the stored worked examples


def _examples() -> list[dict]:
    return json.loads(SHOWCASE.read_text())["runs"]


def test_each_stored_example_keeps_its_provenance_and_its_panel():
    for e in _examples():
        run = ROOT / "runs" / e["run"]
        m = json.loads((run / "manifest.json").read_text())
        assert all(i.get("file_sha256") and i.get("source") == "MAST" for i in m["inputs"]), e["run"]
        assert m["config_sha256"] and m.get("code"), e["run"]
        assert (run / "slugs.json").exists() and (run / "candidates.json").exists() and (run / "crossmatch.json").exists()
        if e["star"] == "pi Men":
            assert panel_mode(m) == "probes_and_sentinels"
        else:
            assert m["panel"]["mode"] == "probes_only" and e["panel"] == "probes_only", e["run"]
            assert not [r for r in m["reviewers"] if r["kind"] != "simulated"]
        assert e["sectors"] and len(e["sectors"]) <= 2


def test_the_examples_compare_with_cited_values_and_never_overclaim():
    text = SHOWCASE.read_text() + (ROOT / "docs/SHOWCASE.md").read_text()
    text += "".join(p.read_text() for p in (ROOT / "docs/results/showcase").glob("*.md"))
    assert "SuperIntelligence" not in text
    for word in ("confirmed by SetuHQ", "SetuHQ confirmed", "SetuHQ discovered", "discovered by SetuHQ"):
        assert word not in text
    assert ATTRIBUTION.split(";")[0] in (ROOT / "docs/SHOWCASE.md").read_text()
    for e in _examples():
        if e.get("planets"):
            for p in e["planets"]:
                assert p["reference"] and p["reference"]["url"].startswith("https://"), p["planet"]
                for k in p.get("ratio") or {}:
                    assert p["published"][k] is not None
        if e.get("false_positive"):
            assert e["false_positive"]["disposition"] == "FP"


def test_the_readme_names_every_example():
    readme = (ROOT / "README.md").read_text()
    for e in _examples():
        assert e["star"] in readme and e["count"] in readme, e["star"]

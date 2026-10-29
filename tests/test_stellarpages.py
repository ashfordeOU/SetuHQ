# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The stellar pages (/evidence/stellar/, /docs/stellar/, /docs/cheops-proposals/; setuhq.stellarpages) and the
CHEOPS guardrails across the repository: the validation status is shown as earned, the figures are real data with
their source, the stars are drawn at their TIC Teff, and every CHEOPS statement carries ESA's terms."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from setuhq import cheops as ch
from setuhq import stellarpages as SP
from setuhq.app import ROUTE_META, SUBNAV
from setuhq.routes import parse_path, url_for
from setuhq.i18n import unkey

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = json.loads((ROOT / "docs/results/stellar_validation.json").read_text())
FIG = json.loads((ROOT / "docs/results/stellar_figures.json").read_text())
FIG4 = json.loads((ROOT / "docs/results/stellar_figures_v4.json").read_text())
LABELS_V4 = {"binaries": "partly validated (5 of 8 checks pass)", "rotation": "not validated (3 of 6 checks pass)",
             "transients": "not validated (1 of 9 checks pass)"}
LABELS = {"flares": "partly validated (5 of 8 checks pass)", "pulsations": "partly validated (7 of 9 checks pass)",
          "cheops": "not validated (2 of 5 checks pass)"}


def _text(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", markup)).replace("&#x27;", "'").replace("&quot;", '"')


def test_status_is_read_from_the_record_and_matches_what_the_docs_say():
    for cap, label in LABELS.items():
        assert VALIDATION["capabilities"][cap]["label"] == label
        assert SP.status_label(cap) == label
    v4 = json.loads((ROOT / "docs/results/stellar_validation_v4.json").read_text())
    stellar_md = (ROOT / "docs/STELLAR.md").read_text()
    for cap, label in LABELS_V4.items():
        assert v4["capabilities"][cap]["label"] == label and SP.status_label(cap) == label
        assert label in stellar_md and label in (ROOT / "docs/results/stellar_validation_v4.md").read_text()


@pytest.mark.parametrize("section", ["evidence_section", "docs_stellar_section"])
def test_every_page_shows_each_status_with_its_count_and_never_calls_one_validated(section):
    text = _text(getattr(SP, section)())
    for label in list(LABELS.values()) + list(LABELS_V4.values()):
        assert label in text
    # "validated" only ever appears as "partly validated", "not validated" or in the status rule's definition
    for m in re.finditer(r"(\w+)\W+validated", text):
        before = m.group(1).lower()
        assert before in ("partly", "not", "fully", "rule"), text[max(0, m.start() - 80):m.end() + 20]
    assert "CHEOPS: not validated (2 of 5 checks pass)" in _text(SP.evidence_section())


def test_the_figures_are_real_tess_data_with_their_source_and_the_stars_at_tic_teff():
    page = unkey(SP.evidence_section())
    assert page.count('<span class="stage-tag">Real data, cited</span>') == 5  # flare, pulsation, binary, rotation, transient
    assert page.count('<span class="stage-tag">Model from stored values</span>') == 4  # the stars; a supernova has none
    assert "no star disc is drawn beside it" in _text(page)
    for f in (FIG4["binary"], FIG4["rotation"]):
        teff = round(f["tic_values"]["teff"])
        assert f["tic_values"]["source"].startswith("TESS Input Catalog v8.2")
        assert f'data-render="star" data-params=\'{{"teff":{teff},"seed":1}}\'' in page
        assert len(f["file_sha256"]) == 64 and "Source: " + f["source"][:40] in _text(page)
    assert "Prša et al. (2022)" in page and "Canto Martins et al. (2020)" in page and "Fausnaugh et al. (2023)" in page
    assert FIG["flare"]["tic_values"]["teff"] == 3286.0 and FIG["pulsation"]["tic_values"]["teff"] > 7000
    for f in (FIG["flare"], FIG["pulsation"]):
        teff = round(f["tic_values"]["teff"])
        assert f'data-render="star" data-params=\'{{"teff":{teff},"seed":1}}\'' in page
        assert f["tic_values"]["source"].startswith("TESS Input Catalog v8.2")
        assert len(f["file_sha256"]) == 64 and "Source: " + f["source"][:40] in _text(page)
    assert "Günther et al. (2020)" in page and "Zieba et al. (2019)" in page
    # static SVG, no script, no external request
    assert "<script" not in page and "http://" not in page and not re.search(r'src="https?:', page)


def test_the_flare_figure_draws_what_the_stored_record_holds():
    svg, alt = SP.flare_svg(FIG["flare"])
    assert svg.count('class="ours"') == len(FIG["flare"]["ours"]) >= 3
    assert svg.count('class="pub"') == len(FIG["flare"]["published_peaks_btjd"])
    assert "TIC 150359500" in alt and "sector 2" in alt
    svg, alt = SP.pulsation_svg(FIG["pulsation"])
    assert svg.count("<circle") == len(FIG["pulsation"]["ours"]) and "beta Pic" in alt


def test_no_cheops_data_in_the_figures():
    assert "No CHEOPS data" in FIG["licence"] and "no CHEOPS data" in FIG4["licence"]
    assert "CH_PR" not in json.dumps(FIG) and "CH_PR" not in json.dumps(FIG4)


def test_the_v4_figures_draw_the_first_held_out_target_whatever_its_result():
    proto = json.loads((ROOT / "docs/results/stellar_validation_protocol_v4.json").read_text())
    first = lambda cap: next(x for x in proto[cap]["targets"] if x["split"] == "held_out")  # noqa: E731
    assert FIG4["binary"]["tic"] == first("binaries")["tic"] and FIG4["rotation"]["tic"] == first("rotation")["tic"]
    assert FIG4["transient"]["name"] == first("transients")["name"]
    svg, alt = SP.binary_svg(FIG4["binary"])
    assert "Prša et al. 2022" in alt and svg.count('class="pub"') >= 1
    svg, alt = SP.rotation_svg(FIG4["rotation"])
    assert "Canto Martins et al. (2020)" in alt and 'class="ours-t"' in svg
    svg, alt = SP.transient_svg(FIG4["transient"])
    assert "Fausnaugh et al. (2023)" in alt and "<circle" in svg
    page = SP.evidence_section()
    for word in ("new eclipsing binary", "new transient", "confirmed transient", "confirmed eclipsing"):
        assert word not in _text(page).lower()


def test_the_cheops_block_carries_esas_terms():
    text = _text(SP.cheops_block(lambda s: __import__("html").escape(s)))
    assert ch.ACKNOWLEDGEMENT in text and ch.DISCLAIMER in text and "CC BY-NC 3.0 IGO" in text
    for paper in ("Benz, W., et al. 2021", "Hoyer, S., et al. 2020", "Fortier, A., et al. 2024"):
        assert paper in text
    assert re.search(r"CH_PR\d{6}\s*: Credit: ESA, \S", text), "each programme ID with its credit line"
    assert "University of Geneva's public API" in text and "ESA does not designate DACE" in text
    assert "not validated" in text and "commercial licence" in text and "Pro" in text


def test_the_proposal_page_states_its_limits():
    text = _text(SP.docs_propose_section())
    assert ch.DISCLAIMER.rstrip(".") in text
    for phrase in ("never logs in, submits, or automates any ESA system", "no PI name or id", "never committed to the repository",
                   "not designated by ESA", "CC BY-NC 3.0 IGO", "an aid, not a guarantee"):
        assert phrase in text


def test_routes_and_sub_navigation():
    for route, path, nav in (("stellar", "/evidence/stellar/", "evidence"), ("stellardocs", "/docs/stellar/", "docs"),
                             ("propose", "/docs/cheops-proposals/", "docs")):
        assert url_for(route) == path and parse_path(path)["route"] == route
        assert ROUTE_META[route]["nav"] == nav
        assert any(route in rs for _, _, rs in SUBNAV[nav])


def test_the_cli_prints_and_records_the_status(capsys):
    from setuhq.stellar_cli import _status

    assert _status("cheops", "CHEOPS ingest") == LABELS["cheops"]
    assert "CHEOPS ingest: not validated (2 of 5 checks pass)" in capsys.readouterr().out


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [p for p in out.decode().split("\0") if p]


def test_no_raw_cheops_file_and_no_vendored_rtl_in_the_repository():
    files = _tracked()
    assert not [f for f in files if f.lower().endswith((".fits", ".fits.gz", ".fit", ".fts"))]
    assert not [f for f in files if re.search(r"CH_PR\d+_.*_(SCI|COR|RAW)", Path(f).name)]
    # the Reserved Target List is downloaded at run time; the only RTL-shaped file is the tests' synthetic one
    rtl = [f for f in files if "rtl" in Path(f).name.lower() or "reserved" in Path(f).name.lower()]
    assert rtl == ["tests/fixtures/cheops_propose/rtl_synthetic.csv"]
    # no ESA or CHEOPS artwork anywhere
    assert not [f for f in files if re.search(r"(esa|cheops).*\.(png|jpe?g|svg|webp|gif)$", f.lower())]


def test_the_wheel_carries_no_cheops_data():
    pkg = ROOT / "src" / "setuhq"
    shipped = [p for p in pkg.rglob("*") if p.is_file() and p.suffix not in (".py", ".pyc")]
    for p in shipped:
        if p.suffix in (".json", ".txt", ".css"):
            assert "CH_PR" not in p.read_text(encoding="utf-8", errors="ignore"), p
    assert not [p for p in shipped if "cheops" in p.name.lower()]


def test_cheops_derived_files_are_carved_out_of_cc_by():
    lic = (ROOT / "docs/results/LICENSE.md").read_text()
    assert "stellar_validation_cheops.json" in lic and "CC BY-NC 3.0 IGO" in lic
    md = (ROOT / "docs/results/stellar_validation_cheops.md").read_text()
    assert "CC BY-NC 3.0 IGO" in md.splitlines()[1] and ch.DISCLAIMER in md
    data = json.loads((ROOT / "docs/results/stellar_validation_cheops.json").read_text())
    c = data["cheops_credit"]
    assert c["acknowledgement"] == ch.ACKNOWLEDGEMENT and c["disclaimer"] == ch.DISCLAIMER
    assert all(r["programme"].startswith("CH_PR") and r["credit"].startswith("Credit: ESA") for r in c["credits"])
    pro = (ROOT / "docs/PRO.md").read_text()
    assert "CHEOPS data are not part of Pro" in pro

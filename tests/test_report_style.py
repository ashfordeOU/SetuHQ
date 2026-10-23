# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The CLI's HTML outputs in the site's visual system (the redesign's phase 5): `setuhq report`, `setuhq dashboard` and
the search feed page of `setuhq discover` read setuhq.design's tokens (under the report's names), print in the light
set, use the self-hosted fonts copied beside them, load nothing from another site, keep the old indigo palette out,
name each dip by its vetting outcome, carry the attribution line, and show the blind PNG the reviewers saw, byte for byte."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from setuhq import dashboard, design, report
from setuhq.names import ATTRIBUTION, PROBES_ONLY, dip_count
from setuhq.renderer import star_svg_stops

ROOT = Path(__file__).resolve().parent.parent
LEAD = ROOT / "runs" / "tess-pi-men-s1"
PROBES_RUN = ROOT / "runs" / "tess-wasp-126-s1"
FEED = ROOT / "docs" / "discoveries" / "catalog.json"
INDIGO = ("#4f46e5", "#818cf8", "#4F46E5", "#818CF8")
OLD_PALETTE = ("#0ea5a4", "#2dd4bf", "#f6f7fb", "#0b0d14", "system-ui,-apple-system,\"Segoe UI\",Roboto")


@pytest.fixture(scope="module")
def outs(tmp_path_factory):
    d = tmp_path_factory.mktemp("outputs")
    pages = {
        "report": report.build_report(LEAD, d / "report", title="SetuHQ: pi Men", validation_md=ROOT / "docs/results/pi_men_validation.md"),
        "probes": report.build_report(PROBES_RUN, d / "probes", title="SetuHQ: WASP-126"),
        "dashboard": dashboard.build_dashboard(LEAD, d / "dashboard", title="SetuHQ <dashboard>", catalog_path=FEED),
        "discover": report.build_discovery_site(FEED, d / "discover"),
        "site_report": report.build_report(LEAD, d / "site_report", title="t", path="/evidence/report/"),
    }
    return {k: Path(v) for k, v in pages.items()}


def test_the_style_sheets_are_the_design_tokens():
    assert report.STYLE.startswith(design.tokens_css(":root", aliases=design.REPORT_ALIASES))
    assert design.PRINT_CSS in report.STYLE and design.BASE_CSS in report.STYLE
    for k, v in design.REPORT_ALIASES.items():
        assert f"--{k}:var(--{v})" in report.STYLE
    assert '--sans:"Geist"' in report.STYLE and "var(--sans)" in report.REPORT_CSS
    for css in (report.STYLE, dashboard.DASHBOARD_CSS, dashboard.DASHBOARD_JS):
        assert not any(c in css for c in INDIGO + OLD_PALETTE), [c for c in INDIGO + OLD_PALETTE if c in css]
    assert design.motion_problems(report.STYLE + dashboard.DASHBOARD_CSS, "outputs") == []


@pytest.mark.parametrize("name", ["report", "probes", "dashboard", "discover"])
def test_every_output_uses_the_tokens_and_its_own_fonts_and_loads_nothing_from_elsewhere(outs, name):
    page = outs[name].read_text()
    assert "--bg:#04060B" in page and ':root[data-theme="light"]{' in page and "@media print{:root{" in page
    assert not any(c in page for c in INDIGO), name
    assert "<link rel='stylesheet' href='assets/fonts/fonts.css'>" in page
    fonts = outs[name].parent / "assets" / "fonts"
    assert (fonts / "fonts.css").is_file() and any(f.name.startswith("geist-") for f in (fonts / "files").iterdir())
    assert "Unbounded" not in (fonts / "fonts.css").read_text()
    # No script, stylesheet, image or font from another site (a canonical link and Open Graph tags are not loads).
    loads = re.findall(r"""<(?:script|link|img|iframe|source)\b[^>]*?(?:src|href)=["']([^"']+)""", page)
    loads = [u for u in loads if not re.search(r'rel=["\']canonical', page[page.find(u) - 120:page.find(u)])]
    assert not [u for u in loads if re.match(r"(https?:)?//", u)], name
    assert "@import" not in page and "url(http" not in page
    assert "render-" not in page and "SetuRender" not in page and "webgl" not in page.lower()  # no renderer, no WebGL
    assert "<html lang='en' data-theme='system'>" in page and 'localStorage.getItem("setuhq-theme")' in page


def test_the_report_names_each_dip_by_its_outcome_and_shows_its_star(outs):
    from setuhq.docket import docket_data

    page = outs["report"].read_text()
    d = docket_data(LEAD, title="t")
    line = dip_count([c["outcome"] for c in d["candidates"]])
    assert line == "7 dips (5 candidates, 1 flagged, 1 rejected)"
    assert f"<p class='count'>{line}</p>" in page
    assert page.count("<span class='tag cand'") == 5 and page.count("<span class='tag rej'") == 1 and page.count("<span class='tag open'") == 1
    # The hero is a black stage with the run's star in its blackbody colour at its stored Teff (TIC v8.2).
    hero = re.search(r"<div class='stage herostage'>.*?</div></div>", page, re.S).group(0)
    assert 'class="stardisc"' in hero and "5,992 K" in hero and "TESS Input Catalog v8.2" in hero
    first = "#" + "".join(f"{c:02x}" for c in star_svg_stops(5992.1)[0])
    assert f'stop-color="{first}"' in hero
    assert ATTRIBUTION in page and PROBES_ONLY not in page  # pi Men ran its Sentinels
    assert "SetuHQ discovered" not in page and "confirmed planet" not in page.replace("not a confirmed planet", "")


def test_the_blind_png_is_the_one_the_reviewers_saw_byte_for_byte(outs):
    page = outs["report"].read_text()
    pngs = sorted((LEAD / "subjects").glob("*.png"))
    assert pngs
    for src in pngs:
        copy = outs["report"].parent / "assets" / src.name
        assert hashlib.sha256(copy.read_bytes()).digest() == hashlib.sha256(src.read_bytes()).digest()
        assert f"src='assets/{src.name}'" in page
    assert page.count(report.REVIEWED_IMAGE) == 7 and page.count("<figure class='plate'>") == 7


def test_a_probes_only_run_says_so_with_the_attribution(outs):
    page = outs["probes"].read_text()
    assert PROBES_ONLY in page and ATTRIBUTION in page


def test_a_site_report_uses_the_sites_fonts(outs):
    page = outs["site_report"].read_text()
    assert "assets/fonts/fonts.css" not in page and not (outs["site_report"].parent / "assets" / "fonts").exists()
    assert '<link rel="canonical" href="https://setuhq.com/evidence/report/">' in page


def test_the_dashboard_uses_the_outcome_words_tokens_and_the_crosshair(outs):
    page = outs["dashboard"].read_text()
    assert "<h1>SetuHQ &lt;dashboard&gt;</h1>" in page  # the title is escaped
    assert "SetuUI.crosshair = function" in page and "SetuUI.crosshair(lc" in page
    assert page.count("class='tab' type='button'") == 4 and "aria-pressed='true'>all</button>" in page
    assert '"words": {"pass": ["candidate", "candidate, unconfirmed"]' in page
    assert ATTRIBUTION in page
    assert re.search(r'"outcome": "flagged"', page) and re.search(r'"outcome": "rejected"', page)


def test_the_feed_page_has_its_per_night_chart_and_tables(outs):
    page = outs["discover"].read_text()
    chart = re.search(r"<figure class='chart card'><svg[^>]*role='img' aria-label='([^']+)'", page)
    assert chart and "per night" in chart.group(1) and "24 matches to known TOIs" in chart.group(1)
    assert "<rect class='known'" in page and "candidate, unconfirmed" in page
    assert "None is a confirmed planet until independent follow-up confirms it." in page

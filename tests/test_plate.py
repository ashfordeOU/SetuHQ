# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
import json
import re

import pytest

from setuhq import docket as docket_mod
from setuhq.cli import main
from setuhq.plate import NO_DETECTION, PLATE_CSS, build_plate, feed_caption, plate_data


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    """No test reaches the network: the archive query fails as it would offline."""

    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def run_dir(app_run):
    return app_run


@pytest.fixture
def catalog(tmp_path):
    entry = {"tic": 1234, "sector_span": [1, 2], "t_center": 1500.25, "time_unit": "BTJD", "duration_hours": 2.0,
             "depth_ppm": 900.0, "snr": 9.5, "score": 1.0, "n_reviewers": 3, "period_days": 3.5, "n_transits": 4,
             "status": "new_candidate", "candidate_id": "tess-x-001", "found": "2026-10-17T00:00:00+00:00"}
    known = dict(entry, tic=5678, candidate_id="tess-y-002", status="known_toi", depth_ppm=1600.0, t_center=1620.5)
    path = tmp_path / "catalog.json"
    # A private deployment's catalogue (embargo off): the public one never holds a new_candidate (tests/test_embargo.py).
    path.write_text(json.dumps({"embargo": False, "candidates": [entry, known], "updated": "2026-10-17T00:00:00+00:00"}))
    return path


def _captions(page: str) -> list[str]:
    return re.findall(r'<p class="caption">(.*?)</p>', page, re.S)


def test_one_caption_per_candidate_each_unconfirmed(run_dir, catalog, tmp_path):
    assert main(["plate", str(run_dir), "--catalog", str(catalog), "--out", str(tmp_path / "plate"),
                 "--title", "setuhq plates", "--allow-missing-crossmatch"]) == 0
    page = (tmp_path / "plate" / "index.html").read_text()
    data = plate_data(run_dir, title="t", catalog_path=catalog)
    ids = [c["candidate_id"] for s in data["stars"] for c in s["candidates"]]
    run_ids = [c["candidate_id"] for c in json.loads((run_dir / "candidates.json").read_text())]
    assert sorted(ids) == sorted(run_ids + ["tess-x-001", "tess-y-002"])
    caps = _captions(page)
    assert len(caps) == len(ids)
    for cid in ids:
        mine = [c for c in caps if cid in c]
        assert len(mine) == 1, cid
        rejected = 'class="word s-rej"' in mine[0] or 'class="word s-flag"' in mine[0]
        assert ('<span class="word cand">candidate</span>' in mine[0]) != rejected, mine[0]  # only a candidate is tagged one
    # "candidate, unconfirmed" once in the lede, not on every caption.
    assert "Each dip that passed vetting is a candidate, unconfirmed, and is tagged so" in page
    assert '<span class="hedge">' not in page  # the count says what each dip is; no blanket word in front of it
    assert not any("unconfirmed" in c for c in caps)
    # One plate per star: the run's star and the two feed stars.
    assert page.count('<article class="plate"') == 3
    assert "<script" not in page  # one self-contained file, plain SVG


def test_run_captions_state_stored_values(run_dir, tmp_path):
    data = plate_data(run_dir, title="t")
    star = data["stars"][0]
    stored = {r["candidate_id"]: r for r in json.loads((run_dir / "candidates.json").read_text())}
    for c in star["candidates"]:
        r = stored[c["candidate_id"]]
        cap = c["caption"]
        assert f"Dip at BTJD {float(r['t_center']):.3f}, {float(r['depth_ppm']):.0f} ppm" in cap
        assert f"SNR {float(r['snr']):.1f}" in cap
        assert f"Consensus interval BTJD {float(r['t_start']):.3f} to {float(r['t_end']):.3f}" in cap
        assert f"Marked by {r['n_reviewers']} of 2 reviewers" in cap
        if r.get("period_days"):
            assert f"Lies on a {float(r['period_days']):.3f}-day BLS period" in cap
        assert "unconfirmed" not in cap  # said once, in the lede
    # Each subject of the star is drawn whole, with a folded panel where it has a stored period.
    assert star["subjects"] and all(len(s["time"]) == len(s["flux"]) for s in star["subjects"])


def test_feed_caption_marks_archive_status_with_the_no_detection_statement():
    known = {"t_center": 10.0, "time_unit": "BTJD", "depth_ppm": 500, "duration_hours": 2, "snr": 8, "n_reviewers": 3,
             "period_days": 2.5, "n_transits": 4, "status": "known_toi"}
    cap = feed_caption(known)
    assert "period matches a known TOI" in cap and NO_DETECTION in cap and cap.endswith(".")
    assert NO_DETECTION not in feed_caption(dict(known, status="new_candidate"))


def test_plate_page_states_no_radius_in_earth_or_jupiter_units(run_dir, catalog, tmp_path):
    page = build_plate(run_dir, tmp_path / "plate", title="t", catalog_path=catalog).read_text()
    no_radius = re.compile(r"\d\s*(R⊕|R_⊕|R♃|R_?J\b|R_?E\b|R_?earth|R_?jup|Earth radi|Jupiter radi|M⊕)", re.I)
    assert not no_radius.search(page)
    assert "pl_rade" not in page and "pl_radj" not in page
    assert page.count("No stellar radius is stored") == 1
    # The scope line is stated once.
    assert page.count("BLS periods and epochs are found per 13-day subject") == 1


def test_river_status_has_words_and_print_is_first_class(run_dir, catalog, tmp_path):
    page = build_plate(run_dir, tmp_path / "plate", title="t", catalog_path=catalog).read_text()
    river = re.search(r'<section class="river".*?</section>', page, re.S).group(0)
    assert "River of time" in river and "log SNR" in river
    assert "1 new candidate" in river and "1 known TOI period" in river  # status in words beside each row
    assert NO_DETECTION in river  # known TOI periods are archive values
    assert 'class="word s-new">new candidate</span>' in page
    # Print: A4, no navigation, every page carries the hedge, plates start a page and stay whole.
    assert "@page{size:A4" in PLATE_CSS and 'content:"Candidate, unconfirmed.' in PLATE_CSS
    printing = PLATE_CSS[PLATE_CSS.index("@media print{"):]
    assert "nav.toc{display:none}" in printing
    assert "article.plate{break-before:page" in printing
    assert "break-inside:avoid" in PLATE_CSS


def _print_css() -> str:
    return PLATE_CSS[PLATE_CSS.index("@media print{"):]


def test_plate_labels_are_unique(run_dir, catalog, tmp_path):
    from setuhq.plate import plate_labels

    page = build_plate(run_dir, tmp_path / "plate", title="t", catalog_path=catalog).read_text()
    labels = plate_labels(page)
    assert len(labels) == len(set(labels))
    # Subject panels are numbered with roman numerals; candidate captions keep their letters.
    assert "Plate 1, panel i" in labels and "1a" in labels
    assert not re.search(r"<b>Plate \d+[a-z]\.", page)
    n_caps = len(_captions(page))
    assert sum(1 for x in labels if not x.startswith("Plate")) == n_caps


def test_print_keeps_each_plate_and_caption_block_whole():
    printing = re.sub(r"/\*.*?\*/", "", _print_css(), flags=re.S)
    covered = {}
    for sels, body in re.findall(r"([^{}]+)\{([^{}]*)\}", printing[printing.index("{") + 1:]):
        for sel in sels.split(","):
            covered[sel.strip()] = covered.get(sel.strip(), "") + body
    for block in ("article.plate", "ol.captions li", "figure", "figcaption", ".archive"):
        assert "break-inside:avoid" in covered[block], block
    assert "columns:2" in covered["ol.captions"]
    assert "widows:3" in covered["ol.captions"] and "orphans:3" in covered["ol.captions"]


def test_print_svg_text_is_at_least_8pt_on_paper():
    printing = _print_css()
    px = float(re.search(r"svg text\{font-size:([\d.]+)px\}", printing).group(1))
    # A4 less the @page side margins (13 mm each) is 184 mm; the figures fill it as laid out in print.
    page_pt = (210 - 26) / 25.4 * 72
    lc_pt, fold_pt = page_pt * 2.1 / 3.1, page_pt * 1 / 3.1
    for width_pt, view_w in ((page_pt, 760), (lc_pt, 520), (fold_pt, 250)):
        assert px * width_pt / view_w >= 8.0, (width_pt, view_w)


def test_river_segments_are_labelled_at_start_and_end_with_their_span(run_dir, catalog, tmp_path):
    from setuhq.plate import river_segments, river_svg

    data = plate_data(run_dir, title="t", catalog_path=catalog)
    segs = river_segments(data["stars"])
    assert len(segs) >= 2  # the run and the feed are years apart
    svg = river_svg(data["stars"])
    view_w = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1))
    assert view_w <= 760  # wider would print the text below 8 pt
    for g, (a, b) in zip(re.findall(r'<g class="seg">(.*?)</g>', svg, re.S), segs):
        ticks = re.findall(r'<text class="tick"[^>]*text-anchor="(\w+)">([^<]+)</text>', g)
        assert ticks[0] == ("start", f"{a:.0f}") and ticks[-1] == ("end", f"{b:.0f}")
        assert re.search(rf'<text class="span"[^>]*>{b - a:.0f} d</text>', g)
    page = build_plate(run_dir, tmp_path / "plate", title="t", catalog_path=catalog).read_text()
    river = re.search(r'<section class="river".*?</section>', page, re.S).group(0)
    assert "not drawn to a common time scale" in river


def test_plate_says_a_fallback_cross_match_was_recorded_not_fetched():
    from setuhq.plate import _xm_dated

    fb = {"fallback_from": "docs/results/pi_men_crossmatch.json", "fetched_at": "2026-10-16T22:59:37+00:00",
          "recorded_commit": "0f6dbdc", "run_status": "not_run", "run_error": "ModuleNotFoundError: x"}
    text = _xm_dated(fb)
    assert text.startswith("recorded 2026-10-16 (commit 0f6dbdc) in docs/results/pi_men_crossmatch.json")
    assert "fetched" not in text and "ModuleNotFoundError: x" in text
    assert _xm_dated({"fetched_at": "2026-10-18T00:00:00+00:00"}) == "fetched 2026-10-18T00:00:00+00:00"


def test_counts_name_each_dip_by_its_status_and_rows_lead_with_the_run_label(run_dir, catalog, tmp_path):
    """The plates count dips, not candidates: "7 dips (5 candidates, 1 flagged, 1 rejected)", in the header, each run
    plate's line, the river's description and each strip's label. A run dip's caption leads with its website name."""
    from setuhq.names import dip_count

    data = plate_data(run_dir, title="t", catalog_path=catalog)
    page = build_plate(run_dir, tmp_path / "plate", title="t", catalog_path=catalog).read_text()
    every = [c.get("status") for s in data["stars"] for c in s["candidates"]]
    n = len(data["stars"])
    assert f"<p>{dip_count(every)} on {n} star{'' if n == 1 else 's'}, one plate per star" in page
    assert re.search(r'<desc id="river-d">' + re.escape(dip_count(every)) + " on ", page)
    for s in data["stars"]:
        if s["source"] == "run":
            assert f"Run {s['run']} · {dip_count([c.get('status') for c in s['candidates']])} · " in page
            for c in s["candidates"]:
                assert c["label"] and re.search(rf'<b class="fig">\d+[a-z]+\. {re.escape(c["label"])}\.</b> <span class="sid mono">stored id {re.escape(c["candidate_id"])}\.</span>', page), c
    assert not re.search(r"\d+ candidates? (on|by) ", page)  # every count is of dips, by status
    assert dip_count(["passed"] * 5 + ["flagged", "rejected"]) == "7 dips (5 candidates, 1 flagged, 1 rejected)"
    assert dip_count(["known_toi", "new_candidate"]) == "2 dips (2 candidates)"


def test_plates_read_the_site_tokens_and_print_light(run_dir, catalog, tmp_path):
    """The plates are on the site's tokens (design.PLATE_ALIASES): dark first, the light set on request, and the light
    set on white paper in print. No paper colour of their own is left; the type is Geist; the run's star heads its
    plate as a static disc; and a stand-alone copy carries its own fonts."""
    from setuhq.design import PLATE_ALIASES, PRINT_CSS, tokens_css

    assert PLATE_CSS.startswith(tokens_css(":root", aliases=PLATE_ALIASES) + PRINT_CSS)
    own = PLATE_CSS.replace(PRINT_CSS, "").replace(tokens_css(":root", aliases=PLATE_ALIASES), "")
    assert "#fbfaf7" not in own and "#f7f6f2" not in own and "#131417" not in own
    assert "--paper:var(--bg)" in PLATE_CSS and ":root[data-theme=\"light\"]{" in PLATE_CSS and "@media print{:root{" in PLATE_CSS
    assert "Georgia" not in own and "serif;" not in own.replace("sans-serif", "") and "font:15px/1.55 var(--sans)" in own
    out = build_plate(run_dir, tmp_path / "plate", title="t", catalog_path=catalog)
    page = out.read_text()
    assert '<html lang="en" data-theme="system">' in page and '<link rel="stylesheet" href="assets/fonts/fonts.css">' in page
    fonts = tmp_path / "plate" / "assets" / "fonts"
    assert (fonts / "fonts.css").exists() and "Unbounded" not in (fonts / "fonts.css").read_text()
    assert not list(fonts.glob("files/unbounded-*")) and list(fonts.glob("files/geist-*")) and list(fonts.glob("files/geistmono-*"))
    assert ".topbar,.pagebar,.skip{display:none!important}" in PLATE_CSS  # the site's chrome does not print
    site = build_plate(run_dir, tmp_path / "site", title="t", catalog_path=catalog, path="/evidence/plates/x/").read_text()
    assert '<link rel="stylesheet" href="/assets/fonts/fonts.css">' in site and not (tmp_path / "site" / "assets" / "fonts").exists()


def test_a_run_plate_is_headed_by_its_star_in_its_blackbody_colour(tmp_path):
    from setuhq.renderer import star_svg_stops

    page = build_plate("runs/tess-toi-270-s5", tmp_path / "p", title="t", catalog_path=None).read_text()
    head = re.search(r'<p class="pstar">(.*?)</p>', page, re.S).group(1)
    stellar = json.loads(open("runs/tess-toi-270-s5/stellar.json").read())["TIC 259377017"]
    assert f'{stellar["teff"]:,.0f} K' in head and "TESS Input Catalog" in head
    first = "#" + "".join(f"{c:02x}" for c in star_svg_stops(stellar["teff"])[0])
    assert f'stop-color="{first}"' in head

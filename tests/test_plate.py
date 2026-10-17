import json
import re

import numpy as np
import pytest

from exoplan import docket as docket_mod
from exoplan.cli import main
from exoplan.config import RunConfig
from exoplan.lightcurve import LightCurve
from exoplan.pipeline import run_pipeline
from exoplan.plate import NO_DETECTION, PLATE_CSS, build_plate, feed_caption, plate_data
from exoplan.reviewers import SimulatedVolunteer


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    """No test reaches the network: the archive query fails as it would offline."""

    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    rng = np.random.default_rng(11)
    time = np.arange(0.0, 26.0, 10 / 1440)
    flux = 1 + rng.normal(0, 2e-4, time.size)
    for k in range(6):
        centre = 2.5 + 4.0 * k
        flux -= 2500e-6 * ((time > centre - 0.125) & (time < centre + 0.125))
    lc = LightCurve(target="TIC TEST-3", mission="TESS", time=time, flux=flux,
                    flux_err=np.full(time.size, 2e-4), provenance={"sector": 1, "time_unit": "BTJD"})
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1),
                 SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.0, seed=2)]
    out = tmp_path_factory.mktemp("run")
    run_pipeline(RunConfig(name="plate", subject_days=13.0, min_points=100, bin_minutes=10.0), [lc], reviewers, out)
    return out


@pytest.fixture
def catalog(tmp_path):
    entry = {"tic": 1234, "sector_span": [1, 2], "t_center": 1500.25, "time_unit": "BTJD", "duration_hours": 2.0,
             "depth_ppm": 900.0, "snr": 9.5, "score": 1.0, "n_reviewers": 3, "period_days": 3.5, "n_transits": 4,
             "status": "new_candidate", "candidate_id": "tess-x-001", "found": "2026-10-17T00:00:00+00:00"}
    known = dict(entry, tic=5678, candidate_id="tess-y-002", status="known_toi", depth_ppm=1600.0, t_center=1620.5)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"candidates": [entry, known], "updated": "2026-10-17T00:00:00+00:00"}))
    return path


def _captions(page: str) -> list[str]:
    return re.findall(r'<p class="caption">(.*?)</p>', page, re.S)


def test_one_caption_per_candidate_each_unconfirmed(run_dir, catalog, tmp_path):
    assert main(["plate", str(run_dir), "--catalog", str(catalog), "--out", str(tmp_path / "plate"),
                 "--title", "exoplan plates"]) == 0
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
        assert "unconfirmed" in mine[0]
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
        assert cap.endswith("Candidate, unconfirmed.")
    # Each subject of the star is drawn whole, with a folded panel where it has a stored period.
    assert star["subjects"] and all(len(s["time"]) == len(s["flux"]) for s in star["subjects"])


def test_feed_caption_marks_archive_status_with_the_no_detection_statement():
    known = {"t_center": 10.0, "time_unit": "BTJD", "depth_ppm": 500, "duration_hours": 2, "snr": 8, "n_reviewers": 3,
             "period_days": 2.5, "n_transits": 4, "status": "known_toi"}
    cap = feed_caption(known)
    assert "period matches a known TOI" in cap and NO_DETECTION in cap and cap.endswith("Candidate, unconfirmed.")
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
    assert 'class="word s-new">new candidate</span>' in page
    # Print: A4, no navigation, every page carries the hedge, plates start a page and stay whole.
    assert "@page{size:A4" in PLATE_CSS and 'content:"Candidate, unconfirmed.' in PLATE_CSS
    printing = PLATE_CSS[PLATE_CSS.index("@media print{"):]
    assert "nav.toc{display:none}" in printing
    assert "article.plate{break-before:page" in printing
    assert "break-inside:avoid" in PLATE_CSS

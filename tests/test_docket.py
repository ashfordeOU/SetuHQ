import json
import re

import numpy as np
import pytest

from exoplan.config import RunConfig
from exoplan.docket import DOCKET_JS, box_model, build_docket
from exoplan.pipeline import plot_arrays, run_pipeline
from exoplan.reviewers import SimulatedVolunteer
from exoplan.search import bls_search
from exoplan.vet import measure_epochs


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    rng = np.random.default_rng(7)
    time = np.arange(0.0, 26.0, 10 / 1440)
    flux = 1 + rng.normal(0, 2e-4, time.size)
    for k in range(6):
        centre = 2.5 + 4.0 * k
        flux -= 2500e-6 * ((time > centre - 0.125) & (time < centre + 0.125))
    from exoplan.lightcurve import LightCurve

    lc = LightCurve(
        target="TIC TEST-2", mission="TESS", time=time, flux=flux,
        flux_err=np.full(time.size, 2e-4), provenance={"sector": 1, "time_unit": "BTJD"},
    )
    reviewers = [
        SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1),
        SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.0, seed=2),
    ]
    config = RunConfig(name="docket", subject_days=13.0, min_points=100, bin_minutes=10.0)
    out = tmp_path_factory.mktemp("run")
    run_pipeline(config, [lc], reviewers, out)
    return out


def test_plot_arrays_store_binned_flux_error(transit_subject):
    subject, _ = transit_subject
    native = plot_arrays(subject)
    assert len(native["flux_err"]) == len(subject.time)
    assert native["flux_err"][5] == pytest.approx(subject.flux_err[5], rel=1e-3)
    arrays = plot_arrays(subject, points=100)
    assert len(arrays["flux_err"]) == len(arrays["flux"]) == len(arrays["time"])
    # Same bin sums as the flux: sqrt(sum sigma^2) / n for one bin, checked by hand.
    edges = np.linspace(subject.start, subject.end, 101)
    first = (subject.time >= edges[0]) & (subject.time < edges[1])
    expected = np.sqrt(np.sum(subject.flux_err[first] ** 2)) / first.sum()
    assert arrays["flux_err"][0] == pytest.approx(expected, rel=1e-3)
    assert all(e > 0 for e in arrays["flux_err"])


def test_subject_json_carries_flux_err(run_dir):
    for path in (run_dir / "subjects").glob("*.json"):
        data = json.loads(path.read_text())
        assert len(data["flux_err"]) == len(data["flux"])


def test_candidates_json_has_bls_t0_and_duration(run_dir):
    rows = json.loads((run_dir / "candidates.json").read_text())
    periodic = [r for r in rows if r["period_days"] is not None]
    assert periodic, "expected at least one candidate on a BLS ephemeris"
    for r in rows:
        assert "bls_t0" in r and "bls_duration_days" in r
    for r in periodic:
        assert r["bls_t0"] is not None and r["bls_duration_days"] > 0
        # The dip sits on the stored ephemeris it was vetted against.
        phase = (r["t_center"] - r["bls_t0"] + 0.5 * r["period_days"]) % r["period_days"] - 0.5 * r["period_days"]
        assert abs(phase) <= r["bls_duration_days"]
    for r in rows:
        if r["period_days"] is None:
            assert r["bls_t0"] is None and r["epochs"] == []


def test_box_model_is_a_box_at_measured_depth_and_duration():
    row = {"t_start": 10.0, "t_end": 10.25, "depth_ppm": 300.0}
    assert box_model(row) == [[10.0, 0.0], [10.0, -300.0], [10.25, -300.0], [10.25, 0.0]]


def test_docket_embeds_box_from_stored_values(run_dir, tmp_path):
    page = build_docket(run_dir, tmp_path / "docket", title="t").read_text()
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))
    for c in data["candidates"]:
        assert c["box"] == box_model(c)
    assert "box model at measured depth and duration" in page
    assert "candidate, unconfirmed" in page
    assert "not per TESS sector" in page


def test_per_epoch_measurements_are_stored_with_sigma(run_dir):
    rows = json.loads((run_dir / "candidates.json").read_text())
    for r in rows:
        for e in r["epochs"] + r["secondary_epochs"]:
            assert set(e) == {"epoch", "t_mid", "n_points", "depth_ppm", "sigma_ppm"}
            if e["n_points"] >= 2:
                assert e["depth_ppm"] is not None and e["sigma_ppm"] > 0
            else:
                assert e["depth_ppm"] is None


def test_no_epoch_is_labelled_missed(run_dir, tmp_path):
    page = build_docket(run_dir, tmp_path / "docket", title="t").read_text()
    pattern = re.compile(r"\bmissed\b|not found|\bmissing transit", re.I)
    assert not pattern.search(DOCKET_JS)
    assert not pattern.search(page)
    # Every epoch the page can show is a stored measurement or an explicit data-coverage note.
    assert "measured: ${fmt(r.depth_ppm,0)} ± ${fmt(r.sigma_ppm,0)} ppm at epoch ${r.epoch}" in DOCKET_JS


def test_measure_epochs_stay_inside_the_subject(transit_subject):
    subject, _ = transit_subject
    signal = bls_search(subject)
    assert signal is not None
    rows = measure_epochs(subject, signal)
    assert rows and all(subject.start <= r["t_mid"] <= subject.end for r in rows)

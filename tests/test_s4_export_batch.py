"""S4: ephemeris propagation and transit windows, the ExoFOP CTOI-style export, and resumable batch mode."""

import csv
import json
import math

import numpy as np
import pytest

from exoplan.discover import Target, Toi, match_toi
from exoplan.ephemeris import BTJD_OFFSET, cone, propagate, transit_windows
from exoplan.exofop import CTOI_FIELDS, CTOI_FIELDS_STATUS, check_row, ctoi_rows, exclusion, export_run


# ---------------------------------------------------------------- ephemeris
def test_propagate_closed_form():
    t, s = propagate(100.0, 0.001, 5.0, 0.0001, 10)
    assert t == 150.0 and s == pytest.approx(math.hypot(0.001, 0.001))
    _, s_cov = propagate(100.0, 0.001, 5.0, 0.0001, 10, cov=-1e-8)
    assert s_cov == pytest.approx(math.sqrt(1e-6 + 1e-6 - 2e-7))
    assert propagate(100.0, None, 5.0, None, 3) == (115.0, 0.0)


def test_pi_men_discovery_ephemeris_cone_matches_the_atlas():
    """ATLAS G5: from the Huang 2018 ephemeris alone (σ_P = 0.00046 d), n ≈ 478 orbits later σ(T) ≈ 5.3 h."""
    _, s = propagate(0.0, 0.0, 6.2679, 0.00046, 478)
    assert s * 24 == pytest.approx(5.3, abs=0.1)


def test_match_toi_still_uses_the_same_propagation():
    toi = Toi(name="1.01", period=6.0, tranmid=2458000.0, period_err=0.001, tranmid_err=0.002, duration_hours=3.0)
    m = match_toi({"t_center": 1000.0 + 6.0 * 100 + 0.05, "time_unit": "BTJD", "duration_hours": 3.0,
                   "period_days": 6.0}, Target(1, tois=[toi]))
    assert m["ephemeris_sigma_hours"] == pytest.approx(24 * math.hypot(0.002, 100 * 0.001))


def test_transit_windows_widen_linearly():
    w = transit_windows(t0=1000.0, t0_err=0.001, period=10.0, period_err=0.001, duration_hours=3.0, start=1000.0,
                        end=1100.0, with_utc=False)
    assert [r["epoch"] for r in w] == list(range(0, 11))
    for r in w:
        sig = math.hypot(0.001, r["epoch"] * 0.001)
        assert r["sigma_hours"] == pytest.approx(sig * 24)
        assert r["window_end_btjd"] - r["window_start_btjd"] == pytest.approx(3.0 / 24 + 6 * sig)
        assert r["t_mid_bjd_tdb"] == pytest.approx(r["t_mid_btjd"] + BTJD_OFFSET)
    assert cone(t0=1000.0, t0_err=0.001, period=10.0, period_err=0.001, at=1100.0)["epoch"] == 10


def test_utc_window_removes_the_light_travel_time():
    """The barycentric correction is at most ~8.3 min plus TDB−UTC (69 s in 2026)."""
    common = dict(t0=3000.0, t0_err=0.001, period=10.0, period_err=0.0, duration_hours=2.0, start=3000.0, end=3001.0)
    exact = transit_windows(**common, ra=84.29, dec=-80.47)[0]
    approx = transit_windows(**common)[0]
    from astropy.time import Time

    d = abs((Time(exact["t_mid_utc"]) - Time(approx["t_mid_utc"])).to_value("min"))
    assert exact["utc_exact"] and not approx["utc_exact"]
    assert 0.0 < d < 8.4


# ---------------------------------------------------------------- export
def _cand(cid, *, target="TIC 777", passed=True, flags="", period=5.0, n=3, fit=True, fpp=0.01, fpp_class="undetermined"):
    row = {"candidate_id": cid, "target": target, "passed": passed, "flags": flags, "period_days": period,
           "n_transits": n, "time_unit": "BTJD", "snr": 20.0, "fap_snr": 25.0, "fap_label": "< 0.005",
           "fap_method": "block bootstrap", "metrics": {"validation": {"fpp": fpp, "nfpp": None, "fpp_class": fpp_class,
                                                                       "label": "not validated: no contrast curve",
                                                                       "method": "exoplan reduced FPP"},
                                                        "dv": {"crowding": {"crowdsap": 0.99}}}}
    if fit:
        row["fit"] = {"t0": 1500.0, "t0_err": 0.002, "period_days": period, "period_err": 0.0005, "depth_ppm": 800.0,
                      "depth_err_ppm": 40.0, "t14_hours": 3.0, "t14_err_hours": 0.2, "k": 0.03, "k_err": 0.002}
    return row


def test_exclusion_rules():
    assert exclusion(_cand("a")) is None
    assert exclusion(_cand("a", passed=False)) == "did not pass vetting"
    assert exclusion(_cand("a", flags="off_ephemeris")) == "off_ephemeris"
    assert "two or more" in exclusion(_cand("a", n=1))
    assert "S2 flags: centroid_offset" == exclusion(_cand("a", flags="crowded;centroid_offset"))
    assert "S3" in exclusion(_cand("a", fpp_class="likely nearby false positive"))
    assert "S3" in exclusion(_cand("a", fpp=0.7))
    assert exclusion(_cand("a", flags="crowded;timing_inconsistent")) is None       # informational flags pass


def test_ctoi_rows_dedupe_signals_and_refuse_toi_duplicates():
    stars = {"TIC 777": {"radius": 1.0, "radius_err": 0.05, "source": "TIC"}}
    cands = [_cand("a"), _cand("b"), _cand("c", target="TIC 888", period=3.0)]
    rows, excluded = ctoi_rows(cands, stars=stars, tois={})
    assert len(rows) == 2 and rows[0]["candidate_ids"] == "a;b"
    r = rows[0]
    assert r["tic_id"] == 777 and r["epoch_bjd_tdb"] == pytest.approx(2458500.0)
    assert r["planet_radius_earth"] == pytest.approx(0.03 * 109.076, rel=1e-3)
    assert r["epoch_sigma_hours_plus_1yr"] == pytest.approx(24 * math.hypot(0.002, 73 * 0.0005), rel=1e-6)
    assert not check_row(r)
    # a TOI with this period and epoch on the same TIC: excluded, never exported
    toi = Toi(name="999.01", period=5.0, tranmid=2458500.0 + 0.01, period_err=1e-4, tranmid_err=1e-3, duration_hours=3.0)
    rows, excluded = ctoi_rows(cands, stars=stars, tois={777: Target(777, tois=[toi])})
    assert [r["tic_id"] for r in rows] == [888]
    assert any("duplicates TOI 999.01" in e["reason"] for e in excluded)
    # without a TOI table nothing is exported unless allowed, and then the rows say so
    rows, excluded = ctoi_rows(cands, stars=stars, tois=None)
    assert rows == [] and all("TOI duplicate check not done" in e["reason"] for e in excluded)
    rows, _ = ctoi_rows(cands, stars=stars, tois=None, allow_unchecked=True)
    assert rows and all(r["toi_check"].startswith("not done") for r in rows)


def test_check_row_rejects_bad_rows():
    rows, _ = ctoi_rows([_cand("a")], tois={})
    good = rows[0]
    assert check_row(good) == []
    assert any("Period unc" in p or "period_unc" in p for p in check_row(dict(good, period_unc_days=None)))
    assert check_row(dict(good, epoch_bjd_tdb=1500.0))
    assert check_row(dict(good, validation_label="confirmed"))
    assert check_row({k: v for k, v in good.items() if k != "depth_ppm"})


def test_export_run_writes_valid_files(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "candidates.json").write_text(json.dumps([_cand("a"), _cand("b", passed=False)]))
    (run / "manifest.json").write_text(json.dumps({"config_sha256": "abc"}))
    out = tmp_path / "export"
    summary = export_run(run, out, tois={}, start_btjd=1500.0, days=30.0)
    assert summary["ctoi_fields_status"] == CTOI_FIELDS_STATUS and "UNVERIFIED" in CTOI_FIELDS_STATUS
    with (out / "ctoi.csv").open() as handle:
        rows = list(csv.reader(handle))
    assert rows[0][:len(CTOI_FIELDS)] == [h for _, h, _ in CTOI_FIELDS]
    assert len(rows) == 2
    windows = list(csv.DictReader((out / "predicted_windows.csv").open()))
    assert len(windows) == 7                                    # epochs 0 to 6 in [1500, 1530] at P = 5 d
    assert all(float(w["sigma_hours"]) > 0 for w in windows)
    data = json.loads((out / "ctoi.json").read_text())
    assert data["excluded"][0]["reason"] == "did not pass vetting"
    assert "confirmed" not in (out / "ctoi.csv").read_text().lower()


def test_export_of_the_stored_pi_men_run_excludes_the_known_toi(tmp_path):
    """pi Men c is TOI 144.01: with that TOI in the table, the stored run exports nothing and says why."""
    toi = Toi(name="144.01", period=6.26791, tranmid=2458325.50400, period_err=0.0005, tranmid_err=0.001,
              duration_hours=2.95)
    summary = export_run("runs/tess-pi-men-s1", tmp_path, tois={261136679: Target(261136679, tois=[toi])},
                         start_btjd=3000.0, days=30.0)
    assert summary["rows"] == []
    assert any("duplicates TOI 144.01" in e["reason"] for e in summary["excluded"])


# ---------------------------------------------------------------- batch
def _lc(tic, seed, sector=1):
    from exoplan.lightcurve import LightCurve

    rng = np.random.default_rng(seed)
    time = np.arange(0.0, 13.0, 10 / 1440)
    flux = 1 + rng.normal(0, 3e-4, time.size)
    for k in range(4):
        flux -= 2000e-6 * (np.abs(time - (1.5 + 3.0 * k)) < 0.1)
    return LightCurve(target=f"TIC {tic}", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 3e-4),
                      provenance={"sector": sector, "time_unit": "BTJD"})


@pytest.fixture
def batch_config(tmp_path):
    path = tmp_path / "batch.toml"
    path.write_text('[run]\nname = "batch-test"\nmin_points = 100\n[search]\nfap_trials = 0\nfap_cache = ""\n')
    return path


def test_batch_is_resumable_and_retries_failures(tmp_path, batch_config):
    from exoplan.batch import read_targets, run_batch
    from exoplan.reviewers.simulated import SimulatedVolunteer

    calls = []
    flaky = {"n": 0}

    def loader(label):
        calls.append(label)
        tic = int(label.split()[1])
        if tic == 3:
            raise LookupError("no SPOC 2-minute light curves")
        if tic == 4:
            flaky["n"] += 1
            if flaky["n"] == 1:
                raise ConnectionError("MAST proxy error")
        return [_lc(tic, tic)]

    targets_file = tmp_path / "targets.txt"
    targets_file.write_text("# list\n1\nTIC 2\n3\n4\n1\n")
    targets = read_targets(targets_file)
    assert targets == [1, 2, 3, 4]
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1)]
    work = tmp_path / "work"
    log = run_batch(batch_config, targets, work_dir=work, loader=loader, reviewers=reviewers, max_targets=2)
    assert (log["done"], log["stopped"]) == (2, "max_targets 2 reached")
    state = json.loads((work / "state.json").read_text())
    assert set(state["targets"]) == {"1", "2"}

    log = run_batch(batch_config, targets, work_dir=work, loader=loader, reviewers=reviewers)
    assert (log["skipped"], log["no_data"], log["failed"]) == (2, 1, 1)
    state = json.loads((work / "state.json").read_text())
    assert state["targets"]["3"]["status"] == "no_data" and state["targets"]["4"]["status"] == "failed"
    assert "MAST proxy error" in state["targets"]["4"]["error"]

    calls.clear()
    log = run_batch(batch_config, targets, work_dir=work, loader=loader, reviewers=reviewers)
    assert calls == ["TIC 4"] and log["done"] == 1 and log["remaining"] == 0     # only the failure is retried
    assert state["config_sha256"] == json.loads((work / "state.json").read_text())["config_sha256"]
    rows = list(csv.DictReader((work / "batch_candidates.csv").open()))
    assert {r["tic"] for r in rows} <= {"1", "2", "4"} and rows
    assert all(r["validation_label"] == "not validated: no contrast curve" for r in rows if r["period_days"])
    assert (work / "tic1" / "feed.json").exists()
    assert log["star_sectors_per_hour"] > 0


def test_batch_state_is_tied_to_the_config(tmp_path, batch_config):
    from exoplan.batch import run_batch
    from exoplan.reviewers.simulated import SimulatedVolunteer

    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1)]
    work = tmp_path / "work"
    run_batch(batch_config, [1], work_dir=work, loader=lambda label: [_lc(1, 1)], reviewers=reviewers)
    other = tmp_path / "other.toml"
    other.write_text(batch_config.read_text().replace("batch-test", "batch-test-2"))
    calls = []
    run_batch(other, [1], work_dir=work, loader=lambda label: calls.append(label) or [_lc(1, 1)], reviewers=reviewers)
    assert calls == ["TIC 1"]                                   # a new config redoes the target
    assert len(list(work.glob("state.*.json"))) == 1           # and the old state is kept aside

import json
import re

import numpy as np
import pytest

from exoplan.config import RunConfig
from exoplan import docket as docket_mod
from exoplan.cli import main
from exoplan.docket import (
    DOCKET_JS,
    NO_STORED_CROSSMATCH,
    CrossmatchUnavailable,
    fit_model,
    build_docket,
    compare_with_archive,
    crossmatch_line,
    group_signals,
    outcome,
    vetting_checks,
)
from exoplan.pipeline import plot_arrays, run_pipeline
from exoplan.reviewers import SimulatedVolunteer
from exoplan.search import bls_search
from exoplan.vet import measure_epochs


@pytest.fixture(autouse=True)
def archive_unreachable(monkeypatch):
    """No test reaches the network: the archive query fails as it would offline."""

    def unreachable(*args, **kwargs):
        raise ConnectionError("archive unreachable (test)")

    monkeypatch.setattr(docket_mod, "query_archive", unreachable)


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


def test_the_strip_draws_the_stored_limb_darkened_fit_not_a_box():
    from exoplan.transitfit import model_depth

    fit = {"t0": 10.125, "k": 0.017, "t14_hours": 3.0, "b": 0.5, "u1": 0.35, "u2": 0.2, "period_days": 6.27, "depth_ppm": 300.0}
    row = {"t_start": 10.0, "t_end": 10.25, "depth_ppm": 250.0, "fit": fit}
    model = fit_model(row)
    ts, ps = [p[0] for p in model], [p[1] for p in model]
    assert len(model) >= 100 and ts == sorted(ts) and ts[0] < 10.0 and ts[-1] > 10.25
    assert min(ps) == pytest.approx(-model_depth(0.017, 0.5, 0.35, 0.2) * 1e6, rel=0.02)
    assert ps[0] == 0 and ps[-1] == 0
    assert len({round(p, 1) for p in ps if p < 0}) > 20  # a curved, limb-darkened profile, not a flat box bottom
    assert fit_model({"t_start": 1, "t_end": 2, "depth_ppm": 9}) == []


def test_docket_embeds_the_fit_from_stored_values(run_dir, tmp_path):
    page = build_docket(run_dir, tmp_path / "docket", title="t").read_text()
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))
    for c in data["candidates"]:
        assert c["model"] == fit_model(c) and "box" not in c
    assert "box model" not in page and "limb-darkened fit (stored)" in page
    assert "nothing is fitted" not in page and "stored measurements and the stored fit" in page
    assert "ppm (window mean)" in page and "' · fit '" in page and "epochs of the signal (V-shape and density flags are signal-level" in page
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
    assert "measured: ${fmt(r.depth_ppm,0)} ± ${fmt(r.sigma_ppm,0)} ppm at ${epochName(r, what)}" in DOCKET_JS


def test_measure_epochs_stay_inside_the_subject(transit_subject):
    subject, _ = transit_subject
    signal = bls_search(subject)
    assert signal is not None
    rows = measure_epochs(subject, signal)
    assert rows and all(subject.start <= r["t_mid"] <= subject.end for r in rows)


def _page_data(page):
    return json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))


PERIODIC_METRICS = {
    "n_in_transit": 12.0, "depth": 2.4e-4, "snr": 14.0, "duration_minutes": 120.0,
    "odd_depth": 2.5e-4, "even_depth": 2.47e-4, "odd_err": 1.2e-5, "even_err": 8e-6,
    "secondary_depth": -9.7e-6, "secondary_err": 8.2e-6, "period": 6.27,
}


def _dip(cid, t, period=6.27, subject="s1", flags=(), metrics=None, passed=True, target="TIC 1", t0=1325.5):
    return {"candidate_id": cid, "subject_id": subject, "target": target, "t_center": t, "period_days": period,
            "bls_t0": t0 if period else None, "bls_duration_days": 0.0833 if period else None, "time_unit": "BTJD",
            "n_transits": 3 if period else 0, "flags": list(flags), "passed": passed, "depth_ppm": 240.0,
            "metrics": dict(PERIODIC_METRICS if metrics is None else metrics)}


def test_three_epochs_of_one_period_are_one_signal_with_three_dips():
    dips = [_dip("s1-000", 1331.77), _dip("s1-001", 1338.05), _dip("s1-003", 1325.50),
            _dip("s2-005", 1348.94, period=None, subject="s2", flags=["off_ephemeris"])]
    for d in dips:
        d["outcome"] = outcome(vetting_checks(d), d["flags"], d["passed"])
    signals = group_signals(dips)
    assert len(signals) == 2
    first = next(s for s in signals if s["subject_id"] == "s1")
    assert first["dips"] == ["s1-003", "s1-000", "s1-001"]  # one signal, three dips in time order
    singles = [s for s in signals if s["period_days"] is None]
    assert len(singles) == 1 and singles[0]["dips"] == ["s2-005"]


def test_run_signals_count_dips_once(run_dir, tmp_path):
    data = _page_data(build_docket(run_dir, tmp_path / "docket", title="t").read_text())
    assert data["counts"]["dips"] == len(data["candidates"])
    assert sum(len(s["dips"]) for s in data["signals"]) == len(data["candidates"])
    periodic = [s for s in data["signals"] if s["period_days"] is not None]
    assert periodic and max(len(s["dips"]) for s in periodic) >= 2
    assert data["counts"]["signals"] == len(data["signals"]) < len(data["candidates"])
    assert "signal${c.signals===1?'':'s'} · ${c.dips} dip" in DOCKET_JS


def test_outcome_all_measured_and_passing_is_passed():
    d = _dip("a", 1.0)
    checks = vetting_checks(d)
    assert all(k["state"] == "pass" for k in checks)
    assert outcome(checks, d["flags"], True) == "passed"


def test_unmeasured_check_never_passes():
    d = _dip("a", 1.0, period=None, metrics={"n_in_transit": 6.0, "depth": 2.6e-4, "snr": 9.5, "duration_minutes": 52.0})
    checks = {k["key"]: k for k in vetting_checks(d)}
    for key in ("oddeven", "secondary", "ephemeris"):
        assert checks[key]["state"] == "not_measured"
        assert checks[key]["value"] is None
    assert outcome(list(checks.values()), d["flags"], True) == "flagged"
    # Odd/even with one parity below 5 sigma: the comparison never ran.
    weak = dict(PERIODIC_METRICS, even_depth=1e-5)
    k = {c["key"]: c for c in vetting_checks(_dip("b", 1.0, metrics=weak))}
    assert k["oddeven"]["state"] == "not_measured"
    # Every missing value is not measured, never a pass.
    bare = _dip("c", 1.0, period=None, metrics={})
    states = [c["state"] for c in vetting_checks(bare)]
    assert set(states) == {"not_measured"}
    assert outcome(vetting_checks(bare), [], True) != "passed"


def test_outcome_order_rejected_then_flagged():
    d = _dip("a", 1.0, flags=["edge_event"])
    assert outcome(vetting_checks(d), d["flags"], True) == "flagged"
    d = _dip("b", 1.0, flags=["edge_event", "secondary_eclipse"], passed=False)
    checks = {k["key"]: k for k in vetting_checks(d)}
    assert checks["secondary"]["state"] == "fail" and checks["edge"]["state"] == "flag"
    assert outcome(list(checks.values()), d["flags"], False) == "rejected"
    # A disqualifying flag rejects even when another check is not measured.
    d = _dip("c", 1.0, period=None, flags=["low_snr"], passed=False, metrics={"n_in_transit": 6.0, "depth": 1e-5, "snr": 2.0, "duration_minutes": 50.0})
    assert outcome(vetting_checks(d), d["flags"], False) == "rejected"


def test_feed_rules_are_separate_from_vetting(run_dir, tmp_path):
    data = _page_data(build_docket(run_dir, tmp_path / "docket", title="t").read_text())
    for c in data["candidates"]:
        assert {k["key"] for k in c["checks"]}.isdisjoint({r["key"] for r in c["feed"]["rules"]})
        assert c["outcome"] in ("passed", "flagged", "rejected")
    assert "Feed admission rules (discover.py), not vetting" in DOCKET_JS


def test_known_planet_line_says_not_run_with_the_stored_error(run_dir, tmp_path):
    page = build_docket(run_dir, tmp_path / "docket", title="t").read_text()
    data = _page_data(page)
    assert data["crossmatch"]["status"] == "not_run"
    assert "not run" in data["crossmatch"]["line"] and NO_STORED_CROSSMATCH in data["crossmatch"]["line"]
    # A build reads only: it never writes crossmatch.json.
    assert not (run_dir / "crossmatch.json").exists()
    assert "cross-match not run" in DOCKET_JS and "Stored error, verbatim" in DOCKET_JS
    assert "unreachable" not in DOCKET_JS
    # A stored error is printed as stored, never replaced by "unreachable".
    stored = {"status": "not_run", "targets": ["TIC TEST-2"], "star": None, "planets": [],
              "error": "ModuleNotFoundError: No module named 'astroquery'"}
    path = run_dir / "crossmatch.json"
    path.write_text(json.dumps(stored))
    try:
        data = _page_data(build_docket(run_dir, tmp_path / "d2", title="t").read_text())
        assert data["crossmatch"]["error"] == stored["error"]
        assert "No module named 'astroquery'" in data["crossmatch"]["line"]
        assert json.loads(path.read_text()) == stored  # untouched by the build
    finally:
        path.unlink()


def test_strict_build_fails_instead_of_building_a_page_that_cannot_say(run_dir, tmp_path):
    with pytest.raises(CrossmatchUnavailable, match="no crossmatch.json is stored"):
        build_docket(run_dir, tmp_path / "docket", title="t", require_crossmatch=True)
    assert not (tmp_path / "docket" / "index.html").exists()
    # The CLI builds strictly by default and exits non-zero with the reason.
    assert main(["docket", str(run_dir), "--out", str(tmp_path / "d"), "--title", "t"]) == 2
    assert main(["app", str(run_dir), "--out", str(tmp_path / "a"), "--title", "t"]) == 2
    assert main(["docket", str(run_dir), "--out", str(tmp_path / "d"), "--title", "t", "--allow-missing-crossmatch"]) == 0


def test_crossmatch_command_is_the_only_writer(run_dir, tmp_path, monkeypatch):
    # Unreachable (the module fixture): the command fails, stores the error verbatim, and exits 1.
    assert main(["crossmatch", str(run_dir)]) == 1
    path = run_dir / "crossmatch.json"
    try:
        stored = json.loads(path.read_text())
        assert stored["status"] == "not_run" and stored["error"] == "ConnectionError: archive unreachable (test)"
        # Reachable: the result replaces it.
        monkeypatch.setattr(docket_mod, "query_archive", lambda target, star=None: [
            {"pl_name": "Test b", "hostname": "Test", "pl_orbper": 4.0, "pl_tranmid": None, "tran_flag": True,
             "rv_flag": False, "tic_id": target}])
        assert main(["crossmatch", str(run_dir)]) == 0
        assert json.loads(path.read_text())["status"] == "matched"
        # A later failure keeps the good stored result.
        monkeypatch.setattr(docket_mod, "query_archive", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
        assert main(["crossmatch", str(run_dir)]) == 1
        assert json.loads(path.read_text())["status"] == "matched"
    finally:
        path.unlink()


def test_fallback_crossmatch_covers_only_its_listed_targets(run_dir, tmp_path):
    fb = {"status": "matched", "targets": ["TIC TEST-2"], "star": None, "source": "test fallback",
          "fetched_at": "2026-10-16T00:00:00+00:00",
          "planets": [{"pl_name": "Test b", "pl_orbper": 4.0, "pl_tranmid": None, "tran_flag": True, "tic_id": "TIC TEST-2"}]}
    path = tmp_path / "fb.json"
    path.write_text(json.dumps(fb))
    data = docket_mod.docket_data(run_dir, title="t", crossmatch_fallback=path)
    assert data["crossmatch"]["status"] == "matched" and data["crossmatch"]["fallback_from"] == str(path)
    assert data["crossmatch"]["line"] == "Host of published planet Test b (P 4.000 d)"
    assert "fallback_from" in DOCKET_JS
    other = dict(fb, targets=["TIC 1"])
    path.write_text(json.dumps(other))
    assert docket_mod.docket_data(run_dir, title="t", crossmatch_fallback=path)["crossmatch"]["status"] == "not_run"


def test_known_planet_line_from_stored_archive_values():
    matched = {"status": "matched", "planets": [{"pl_name": "pi Men c", "pl_orbper": 6.2678399}]}
    assert crossmatch_line(matched) == "Host of published planet pi Men c (P 6.268 d)"
    assert crossmatch_line({"status": "no_match", "planets": []}) == "No published planet matched in the archive"


def test_stored_crossmatch_is_reused_offline(run_dir, tmp_path):
    stored = {"status": "matched", "targets": ["TIC TEST-2"], "star": None, "fetched_at": "2026-01-01T00:00:00+00:00",
              "source": "test", "planets": [{"pl_name": "Test b", "pl_orbper": 4.0}]}
    path = run_dir / "crossmatch.json"
    path.write_text(json.dumps(stored))
    try:
        data = _page_data(build_docket(run_dir, tmp_path / "docket", title="t").read_text())
        assert data["crossmatch"]["line"] == "Host of published planet Test b (P 4.000 d)"
    finally:
        path.unlink()


def test_reviewer_kinds_are_counted_in_the_header(run_dir, tmp_path):
    data = _page_data(build_docket(run_dir, tmp_path / "docket", title="t").read_text())
    assert data["counts"]["simulated"] == 2 and data["counts"]["reviewers"] == 2
    assert "reviewers: ${reviewerSummary(" in DOCKET_JS


def test_one_ephemeris_in_two_subjects_is_one_signal():
    # pi Men c as the run stores it: P 6.2726 d in one subject, 6.2616 d in the next.
    a = [_dip(f"s1-{i}", t, period=6.272620, t0=1325.5004) for i, t in enumerate((1325.4993, 1331.7711, 1338.0495))]
    b = [_dip(f"s2-{i}", t, period=6.261557, subject="s2", t0=1344.3218) for i, t in enumerate((1344.2644, 1350.5849))]
    for d in a + b:
        d["outcome"] = outcome(vetting_checks(d), d["flags"], d["passed"])
    signals = group_signals(a + b)
    assert len(signals) == 1
    s = signals[0]
    assert s["dips"] == ["s1-0", "s1-1", "s1-2", "s2-0", "s2-1"]
    assert s["subject_ids"] == ["s1", "s2"]
    # Each subject's BLS result is kept as provenance, unchanged.
    assert [(b_["subject_id"], b_["period_days"], b_["bls_t0"]) for b_ in s["bls"]] == [("s1", 6.272620, 1325.5004), ("s2", 6.261557, 1344.3218)]
    from exoplan.docket import signal_epoch
    assert [signal_epoch(d, s) for d in a + b] == [0, 1, 2, 3, 4]


def test_different_targets_or_ephemerides_never_merge():
    a = [_dip("a-0", 1325.50, period=6.2726, t0=1325.50, target="TIC 1")]
    b = [_dip("b-0", 1344.32, period=6.2616, subject="s2", t0=1344.32, target="TIC 2")]
    assert len(group_signals(a + b)) == 2
    # Same target, periods within 1 percent, but the epochs do not line up: two signals.
    c = [_dip("c-0", 1347.00, period=6.2616, subject="s3", t0=1347.00, target="TIC 1")]
    assert len(group_signals(a + c)) == 2
    # Same target, epochs line up, periods 2 percent apart: two signals.
    d = [_dip("d-0", 1344.32, period=6.40, subject="s4", t0=1344.32, target="TIC 1")]
    assert len(group_signals(a + d)) == 2


def test_ledger_shows_uncertainties_and_the_statistic():
    checks = {k["key"]: k for k in vetting_checks(_dip("a", 1.0, metrics=dict(
        PERIODIC_METRICS, odd_depth=2.512e-4, even_depth=2.471e-4, odd_err=1.164e-5, even_err=8.18e-6,
        secondary_depth=-9.73e-6, secondary_err=8.22e-6)))}
    assert checks["oddeven"]["value"] == "251 ± 12 / 247 ± 8 ppm, Δ = 0.3σ"
    assert checks["secondary"]["value"] == "−10 ± 8 ppm (−1.2σ)"
    assert "signal-level" in checks["oddeven"]["name"] and "signal-level" in checks["secondary"]["name"]


def test_archive_comparison_match_and_no_match():
    planets = [{"pl_name": "pi Men c", "pl_orbper": 6.2678399, "pl_tranmid": 2458325.50400, "tran_flag": True},
               {"pl_name": "pi Men d", "pl_orbper": 124.64, "pl_tranmid": None, "tran_flag": False, "rv_flag": True}]
    hit = _dip("hit", 1338.0495, period=6.272620)
    miss = _dip("miss", 1338.0495, period=4.0)
    single = _dip("single", 1348.94, period=None)
    out = compare_with_archive(planets, [hit, miss, single])["by_candidate"]
    h = out["hit"]
    assert h["consistent_with"] == "pi Men c"
    c = next(r for r in h["planets"] if r["pl_name"] == "pi Men c")
    assert c["dP_pct"] == pytest.approx(abs(6.272620 - 6.2678399) / 6.2678399 * 100)
    # Archive epoch 2: 2458325.504 + 2 * 6.2678399 = 2458338.0397 BJD = 1338.0397 BTJD, 0.0098 d before the dip.
    assert c["epoch_offset_min"] == pytest.approx((2458325.504 + 2 * 6.2678399 - 2458338.0495) * 1440)
    assert h["line"].startswith("consistent with pi Men c: ΔP 0.08%, nearest epoch offset −14 min")
    assert out["miss"]["consistent_with"] is None
    assert out["miss"]["line"] == "no archive planet within tolerance; pi Men d: no transit ephemeris to compare"
    assert out["single"]["line"].startswith("no archive planet within tolerance")
    d = next(r for r in h["planets"] if r["pl_name"] == "pi Men d")
    assert d["epoch_offset_min"] is None


def test_rv_planet_gets_no_transit_epoch_offset():
    # As the archive stores pi Men: c transits; d and HD 39091 b are radial-velocity planets.
    # HD 39091 b carries a pl_tranmid, but with tran_flag 0 it is not a transit ephemeris.
    planets = [
        {"pl_name": "pi Men c", "pl_orbper": 6.2678399, "pl_tranmid": 2458425.789204, "tran_flag": True, "rv_flag": True},
        {"pl_name": "pi Men d", "pl_orbper": 124.64, "pl_tranmid": None, "tran_flag": False, "rv_flag": True},
        {"pl_name": "HD 39091 b", "pl_orbper": 2088.8, "pl_tranmid": 2458632.6, "tran_flag": False, "rv_flag": True},
    ]
    out = compare_with_archive(planets, [_dip("hit", 1338.0495, period=6.272620)])["by_candidate"]["hit"]
    rows = {r["pl_name"]: r for r in out["planets"]}
    assert rows["pi Men c"]["epoch_offset_min"] is not None and rows["pi Men c"]["transit_ephemeris"]
    for name in ("pi Men d", "HD 39091 b"):
        assert rows[name]["epoch_offset_min"] is None
        assert rows[name]["transit_ephemeris"] is False
        assert rows[name]["offset_note"].startswith("no transit ephemeris to compare")
    assert out["line"].endswith("; pi Men d, HD 39091 b: no transit ephemeris to compare")
    line = crossmatch_line({"status": "matched", "planets": planets})
    assert line == "Host of published planets pi Men c (P 6.268 d), pi Men d (RV, non-transiting), HD 39091 b (RV, non-transiting)"
    # No flag stored, or an implausible mid-time: no offset either.
    unflagged = compare_with_archive([{"pl_name": "X b", "pl_orbper": 6.2678399, "pl_tranmid": 2458425.79}], [_dip("a", 1338.05, period=6.2726)])
    assert unflagged["by_candidate"]["a"]["planets"][0]["epoch_offset_min"] is None
    assert unflagged["by_candidate"]["a"]["line"].endswith("ΔP 0.08%, no transit ephemeris to compare")
    odd = compare_with_archive([{"pl_name": "Y b", "pl_orbper": 6.27, "pl_tranmid": 58425.79, "tran_flag": True}], [_dip("a", 1338.05)])
    assert odd["by_candidate"]["a"]["planets"][0]["offset_note"] == "no transit ephemeris to compare (transit mid-time implausible)"


def test_merged_signal_epochs_carry_signal_number_and_subject_parity():
    from exoplan.docket import CROSS_SUBJECT_NOTE, annotate_signal_epochs, signal_epoch

    def ep(k, t0, period=6.27262):
        return {"epoch": k, "t_mid": t0 + k * period, "n_points": 12, "depth_ppm": 240.0, "sigma_ppm": 10.0}

    a = [_dip(f"s1-{i}", t, period=6.272620, t0=1325.5004) for i, t in enumerate((1325.4993, 1331.7711, 1338.0495))]
    b = [_dip(f"s2-{i}", t, period=6.261557, subject="s2", t0=1344.3218) for i, t in enumerate((1344.2644, 1350.5849))]
    for d in a:
        d["epochs"] = [ep(k, 1325.5004) for k in range(3)]
    for d in b:
        d["epochs"] = [ep(k, 1344.3218, 6.261557) for k in range(2)]
    for d in a + b:
        d["outcome"] = outcome(vetting_checks(d), d["flags"], d["passed"])
    (s,) = group_signals(a + b)
    cands = {d["candidate_id"]: d for d in a + b}
    annotate_signal_epochs(s, cands)
    rows = [(r["signal_epoch"], r["subject_label"], r["epoch"], r["subject_parity"]) for r in s["epoch_rows"]]
    # Signal epoch E3 is even in its own subject: parity is numbered per subject.
    assert rows == [(0, "S1", 0, "even"), (1, "S1", 1, "odd"), (2, "S1", 2, "even"), (3, "S2", 0, "even"), (4, "S2", 1, "odd")]
    assert [signal_epoch(d, s) for d in a + b] == [0, 1, 2, 3, 4]
    assert CROSS_SUBJECT_NOTE == ("Odd/even and secondary were tested within each subject only; parity is numbered per subject. "
                                  "No cross-subject test ran.")
    assert "D.cross_subject_note" in DOCKET_JS and "subject_parity" in DOCKET_JS


def test_mark_audit_reports_overlap_and_the_interval_rule():
    from exoplan.aggregate import aggregate, audit_marks
    from exoplan.reviewers.base import Classification, Mark, POTENTIAL_PLANET

    def cls(r, a, b):
        return Classification(subject_id="s", reviewer_id=r, label=POTENTIAL_PLANET, marks=(Mark(a, b),))

    # Three narrow marks on the dip and a wide one whose centre sits 0.07 d early,
    # as on pi Men E0. The wide mark covers the whole window, so it counts.
    # A mark well clear of the dip does not.
    panel = [cls("v1", 1325.452, 1325.541), cls("v2", 1325.458, 1325.555), cls("v3", 1325.463, 1325.530),
             cls("c1", 1325.300, 1325.550), cls("c2", 1325.700, 1325.800)]
    events = aggregate(panel, {}, gap_days=0.05, min_score=0.5, min_planet_fraction=0.5)
    (event,) = events
    assert event.reviewers == ("c1", "v1", "v2", "v3")
    audit = {r["reviewer_id"]: r for r in audit_marks(event, panel, 0.05)}
    assert audit["c1"]["counted"] is True and audit["c1"]["overlap_frac"] == pytest.approx(1.0)
    assert audit["c1"]["marks"][0]["centre_gap_days"] > 0.05
    assert all(audit[r]["counted"] for r in ("v1", "v2", "v3"))
    assert audit["c2"]["counted"] is False and audit["c2"]["overlap_frac"] == 0.0


def test_candidates_store_mark_audit_and_counting_rule(run_dir, tmp_path):
    rows = json.loads((run_dir / "candidates.json").read_text())
    for r in rows:
        assert r["count_rule"]["gap_days"] == 0.05 and "overlaps" in r["count_rule"]["text"]
        counted = {a["reviewer_id"] for a in r["mark_audit"] if a["counted"]}
        assert counted == set(r["reviewers"].split(";"))
        for a in r["mark_audit"]:
            assert a["overlap_frac"] is None or 0.0 <= a["overlap_frac"] <= 1.0
    data = _page_data(build_docket(run_dir, tmp_path / "docket", title="t").read_text())
    assert all("mark_audit" in c and "count_rule" in c for c in data["candidates"])
    assert "not counted: overlaps no counted mark" in DOCKET_JS and "url(#hatch-" in DOCKET_JS


def test_verdict_card_archive_is_one_sentence_with_provenance_behind_a_disclosure():
    fn = re.search(r"function crossmatchLine\(c, feedLine\)\{.*?\n\}\n", DOCKET_JS, re.S).group(0)
    assert '<p class="xm-one">${sentence}' in fn and "<details class=\"xm-prov\"><summary>Provenance</summary>" in fn
    assert "from the repository's stored cross-match ${esc(x.fallback_from)}; this run's own cross-match ${x.run_status === 'not_run' ? 'did not run'" in fn
    assert "consistent with ${esc(hit.pl_name)} (P ${fmt(hit.pl_orbper,3)} d, ΔP ${fmt(hit.dP_pct,2)}%)" in fn
    # The full source and the verbatim errors sit in the disclosure.
    assert "Source: ${esc(x.source)}" in fn and "Stored error, verbatim" in fn and "esc(x.run_error)" in fn
    # A fallback was recorded, not fetched for this page.
    assert "recorded ${dayUTC(x.fetched_at)}${x.recorded_commit ? ` (commit ${esc(x.recorded_commit)})` : ''}" in fn
    assert "fetched ${dayUTC(x.fetched_at)}" in fn


def test_validation_note_supplies_the_timing_offset():
    from pathlib import Path

    stored = json.loads(Path(docket_mod.DEFAULT_CROSSMATCH).read_text())
    v = stored["validation"]
    note = Path(v["source"]).read_text()
    row = next(line for line in note.splitlines() if line.startswith("| pi Men c |"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    # Values as the validation note states them: predicted 5, recovered 5, mean offset -8.0 min.
    assert v["epochs_recovered"] == f"{cells[3]} of {cells[2]}" == "5 of 5"
    assert v["mean_timing_offset_min"] == float(cells[4]) == -8.0
    assert stored["recorded_commit"] == "0f6dbdc"
    planets = stored["planets"]
    out = compare_with_archive(planets, [_dip("a", 1338.05, period=6.2726)], validation=v)["by_candidate"]["a"]
    assert out["line"] == "consistent with pi Men c: ΔP 0.08%, timing offset from the validation note: −8.0 min mean over 5 epochs"
    bare = compare_with_archive(planets, [_dip("a", 1338.05, period=6.2726)])["by_candidate"]["a"]
    assert "no transit ephemeris to compare" in bare["line"]


def test_odd_even_subject_labels_are_11px_and_stack_on_a_narrow_screen():
    fn = re.search(r"function epochPlot\(rows, title, depth, colour\)\{.*?\n\}\n", DOCKET_JS, re.S).group(0)
    assert "9px" not in fn and fn.count("t.style.fontSize = '11px'") == 2
    assert "matchMedia('(max-width:419.98px)')" in fn and "[[0, r.subject_label || ''], [1, r.subject_parity || '']]" in fn


def test_verdict_card_is_the_verdict_and_the_archive_sentence_only():
    top = re.search(r"top.innerHTML = `.*?</section>", DOCKET_JS, re.S).group(0)
    assert '<div class="out-feed">' not in top  # the feed rule moved into the Provenance disclosure
    assert "crossmatchLine(c, `<span class=\"xm-k\">Feed admission rule (discover.py), not vetting:</span>" in top
    fn = re.search(r"function crossmatchLine\(c, feedLine\)\{.*?\n\}\n", DOCKET_JS, re.S).group(0)
    assert 'feedLine ? `<li class="out-feed">${feedLine}</li>`' in fn
    # The disclosure's summary is a 44 px target on a phone.
    assert "@media (max-width:699.98px){.xm-prov summary{display:flex;align-items:center;min-height:44px;padding:12px 0;" in docket_mod.DOCKET_CSS


def test_current_signal_is_marked_for_the_signals_button():
    sync = re.search(r"function syncActive\(\)\{.*?\n\}\n", DOCKET_JS, re.S).group(0)
    assert "g.classList.toggle('cur'" in sync
    assert ".sighead{scroll-margin-top:calc(var(--top, 0px) + 8px)}" in docket_mod.DOCKET_CSS


def test_stored_crossmatch_source_cites_the_validation_offset():
    from pathlib import Path

    src = json.loads(Path(docket_mod.DEFAULT_CROSSMATCH).read_text())["source"]
    assert ("its transit mid-time was not recorded, so no per-epoch offset is computed here; the validation note's "
            "mean timing offset (−8.0 min over 5 of 5 epochs) is cited instead.") in src


def test_lane_labels_are_short_display_names():
    js = DOCKET_JS
    assert "fitLabel(t, sn.slice(0, sp), sn.slice(sp + 1), pl - 8)" in js
    assert "SEN = Sentinel (Claude model, Anthropic; not a person), PRB = Probe (deterministic matched-filter detector; not a person)" in js
    assert "reviewers: ${reviewerSummary(" in js and "Sentinel${cl === 1 ? '' : 's'}" in js

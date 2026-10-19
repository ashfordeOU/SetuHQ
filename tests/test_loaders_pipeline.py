import csv
import json

import numpy as np
import pytest
from astropy.io import fits

from exoplan.calibrate import calibrate_weights
from exoplan.config import RunConfig, build_reviewers, load_config
from exoplan.injection import fixed_injection
from exoplan.lightcurve import LightCurve
from exoplan.loaders import load_cheops, load_csv
from exoplan.pipeline import run_pipeline
from exoplan.reviewers import SimulatedVolunteer


def _write_cheops_fits(path, *, flag_bad=True):
    time = np.arange(0, 5, 0.01)
    flux = 1000.0 + np.linspace(0, 1, time.size)
    flags = np.zeros(time.size, dtype=int)
    if flag_bad:
        flags[:10] = 1
    columns = fits.ColDefs(
        [
            fits.Column(name="BJD_TIME", format="D", array=time),
            fits.Column(name="FLUX", format="D", array=flux),
            fits.Column(name="FLUXERR", format="D", array=np.full(time.size, 1.0)),
            fits.Column(name="DATA_FLAG", format="J", array=flags),
        ]
    )
    primary = fits.PrimaryHDU()
    primary.header["OBJECT"] = "HD TEST"
    fits.HDUList([primary, fits.BinTableHDU.from_columns(columns, name="LIGHTCURVE")]).writeto(path)


def test_load_cheops_masks_flags_and_normalises(tmp_path):
    path = tmp_path / "SCI_COR_Lightcurve_test.fits"
    _write_cheops_fits(path)
    lc = load_cheops(path)
    assert lc.mission == "CHEOPS"
    assert lc.target == "HD TEST"
    assert len(lc) == 490
    assert abs(np.median(lc.flux) - 1.0) < 0.01
    assert lc.provenance["flux_column"] == "FLUX"
    assert len(lc.provenance["sha256"]) == 64


def test_load_cheops_rejects_file_without_flux(tmp_path):
    path = tmp_path / "bad.fits"
    columns = fits.ColDefs([fits.Column(name="TIME", format="D", array=np.arange(5.0))])
    fits.HDUList([fits.PrimaryHDU(), fits.BinTableHDU.from_columns(columns)]).writeto(path)
    with pytest.raises(ValueError):
        load_cheops(path)


def test_load_csv_defaults_error_when_absent(tmp_path):
    path = tmp_path / "lc.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", "flux"])
        for t in range(20):
            writer.writerow([t * 0.1, 1.0 + 0.001 * (t % 3)])
    lc = load_csv(path, target="X")
    assert len(lc) == 20
    assert np.all(lc.flux_err > 0)


def test_run_config_round_trip(tmp_path):
    path = tmp_path / "cfg.toml"
    path.write_text(
        '[run]\nname = "t"\n[[targets]]\nmission = "tess"\nid = "TIC 1"\nsectors = [1]\n'
        '[[reviewers]]\ntype = "simulated"\nid = "v1"\n'
    )
    config = load_config(path)
    assert config.targets[0].mission == "TESS"
    assert config.targets[0].sectors == (1,)
    assert len(config.digest()) == 64
    reviewers = build_reviewers(config.reviewers)
    assert isinstance(reviewers[0], SimulatedVolunteer)


def test_end_to_end_pipeline_recovers_injected_transits(tmp_path, lightcurve_with_transits):
    reviewers = [
        SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.05, seed=1),
        SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.10, seed=2),
        SimulatedVolunteer("vol-c", snr_threshold=5.5, miss_probability=0.10, seed=3),
    ]
    config = RunConfig(name="e2e", subject_days=13.0, min_points=100, bin_minutes=10.0)
    summary = run_pipeline(config, [lightcurve_with_transits], reviewers, tmp_path / "run")

    assert summary.n_subjects >= 3
    assert summary.n_consensus > 0
    passed = [c for c in summary.candidates if c.passed]
    assert passed, "expected at least one vetted candidate"
    truth_centres = [2.5 + 5.0 * k for k in range(8)]
    assert any(min(abs(c.t_center - t) for t in truth_centres) < 0.2 for c in passed)

    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert manifest["counts"]["subjects"] == summary.n_subjects
    assert manifest["reviewers"][0]["id"] == "vol-a"
    assert (tmp_path / "run" / "candidates.csv").exists()
    rows = json.loads((tmp_path / "run" / "candidates.json").read_text())
    periodic = [r for r in rows if r["period_days"] is not None]
    assert periodic and all(r["fap"] is not None and 0.0 <= r["fap"] <= 1.0 for r in periodic)
    assert all(r["fap"] is None for r in rows if r["period_days"] is None)
    assert (tmp_path / "run" / "classifications.csv").exists()
    assert len(list((tmp_path / "run" / "subjects").glob("*.png"))) == summary.n_subjects


def test_pipeline_skips_unavailable_reviewers(tmp_path, lightcurve_with_transits, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from exoplan.reviewers import ClaudeReviewer

    reviewers = [SimulatedVolunteer("vol-a", seed=1), ClaudeReviewer("claude-x")]
    # Only the reviewer bookkeeping is under test: no FAP trials, no transit fits.
    config = RunConfig(name="skip", subject_days=13.0, min_points=100, fap_trials=0, fit_transits=False)
    summary = run_pipeline(config, [lightcurve_with_transits], reviewers, tmp_path / "run")
    assert summary.skipped_reviewers == ["claude-x"]


def test_calibration_gives_real_volunteer_higher_weight_than_blind_one(tmp_path):
    good = SimulatedVolunteer("good", snr_threshold=4.0, miss_probability=0.0, seed=1)
    blind = SimulatedVolunteer("blind", snr_threshold=1e6, periodic_snr_threshold=1e6, miss_probability=0.0, seed=2)
    skills = calibrate_weights([good, blind], n_injected=12, n_empty=12, seed=5)
    assert skills["good"].tpr > skills["blind"].tpr
    assert skills["blind"].weight == pytest.approx(0.05)
    assert skills["good"].weight > skills["blind"].weight
    # The rates and sample sizes behind the weights are kept next to the weights file.
    from exoplan.calibrate import calibration_path, calibration_record

    assert calibration_path("docs/w.json").as_posix() == "docs/w.calibration.json"
    record = calibration_record(skills, weights_file="w.json")
    assert record["reviewers"]["good"] == {"tpr": skills["good"].tpr, "fpr": skills["good"].fpr,
                                           "weight": skills["good"].weight, "n_injected": 12, "n_empty": 12}


def test_fixed_injection_is_centred():
    injection = fixed_injection(13.0, 1000.0, 2.0)
    assert abs(0.5 * (injection.t_start + injection.t_end) - 6.5) < 1e-9
    assert injection.depth == pytest.approx(1e-3)


_TWO_VOLUNTEERS = """
[run]
name = "weights"
min_points = 100

[search]
fap_trials = 0
fit_transits = false

[[reviewers]]
type = "simulated"
id = "vol-a"
seed = 1

[[reviewers]]
type = "simulated"
id = "vol-b"
seed = 2
"""


def test_run_uses_calibrated_weights_when_reviewer_ids_match(tmp_path, lightcurve_with_transits, monkeypatch):
    from exoplan import cli

    config_path = tmp_path / "c.toml"
    config_path.write_text(_TWO_VOLUNTEERS)
    calibrated = tmp_path / "w.json"
    calibrated.write_text(json.dumps({"vol-a": 0.6, "vol-b": 0.4}))
    monkeypatch.setattr(cli, "_load_targets", lambda config: [lightcurve_with_transits])

    cli.main(["run", str(config_path), "--out", str(tmp_path / "run"), "--calibrated-weights", str(calibrated)])
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert manifest["weights"] == {"vol-a": 0.6, "vol-b": 0.4}
    assert {r["id"]: r["weight"] for r in manifest["reviewers"]} == {"vol-a": 0.6, "vol-b": 0.4}
    assert manifest["weights_source"] == str(calibrated)

    # A file whose reviewer ids differ from the config's is not used.
    calibrated.write_text(json.dumps({"vol-a": 0.6, "someone-else": 0.4}))
    cli.main(["run", str(config_path), "--out", str(tmp_path / "run2"), "--calibrated-weights", str(calibrated)])
    manifest = json.loads((tmp_path / "run2" / "manifest.json").read_text())
    assert manifest["weights"] == {"vol-a": 1.0, "vol-b": 1.0}
    assert manifest["weights_source"].startswith("uniform 1.0")


def test_pi_men_config_matches_the_stored_full_panel_weights():
    from pathlib import Path

    from exoplan.cli import resolve_weights

    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "tess_pi_men_s1.toml")
    weights, source = resolve_weights(config, None, str(root / "docs/results/reviewer_weights_full_panel.json"))
    assert weights is not None and source.endswith("reviewer_weights_full_panel.json")
    assert any(w != 1.0 for w in weights.values())

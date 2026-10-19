"""S2 wiring: the extended tests add flags without changing pass/fail by default; ``[vetting] decide`` turns them into
pass/fail; the pixel tests run from the pipeline; CROWDSAP and FLFRCSAP are read from SPOC headers."""

from dataclasses import replace

import numpy as np
import pytest

from exoplan.config import RunConfig, load_config
from exoplan.lightcurve import LightCurve
from exoplan.loaders import load_spoc_file, spoc_crowding
from exoplan.pipeline import run_pipeline
from exoplan.reviewers.simulated import SimulatedVolunteer


def _eccentric_binary(seed=3, *, crowdsap=0.7):
    """26 days, a 3000 ppm primary every 4 days and a 2000 ppm secondary at phase 0.37 (not 0.5)."""
    rng = np.random.default_rng(seed)
    time = np.arange(0.0, 26.0, 10 / 1440)
    flux = 1 + rng.normal(0, 4e-4, time.size)
    for k in range(7):
        flux -= 3000e-6 * (np.abs(time - (2.5 + 4.0 * k)) < 0.1)
        flux -= 2000e-6 * (np.abs(time - (2.5 + 4.0 * (k + 0.37))) < 0.1)
    return LightCurve(target="TIC 123", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 4e-4),
                      provenance={"sector": 1, "time_unit": "BTJD", "crowdsap": crowdsap, "flfrcsap": 0.9})


def _run(tmp_path, config, name):
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1),
                 SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.0, seed=2)]
    return run_pipeline(config, [_eccentric_binary()], reviewers, tmp_path / name).candidates


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("s2")
    base = RunConfig(name="s2", subject_days=13.0, min_points=100, bin_minutes=10.0, fit_transits=True, fap_trials=0)
    return {
        "off": _run(tmp, replace(base, vetting_extended=False), "off"),
        "flag": _run(tmp, base, "flag"),
        "decide": _run(tmp, replace(base, vetting_decide=True), "decide"),
    }


def _on_primary(cands):
    return [c for c in cands if c.period_days and abs(((c.t_center - 2.5 + 2.0) % 4.0) - 2.0) < 0.1]


def test_default_adds_flags_and_metrics_but_keeps_decisions(runs):
    off, flag = runs["off"], runs["flag"]
    assert [(c.t_center, c.passed) for c in off] == [(c.t_center, c.passed) for c in flag]
    prim = _on_primary(flag)
    assert prim, "the primary eclipses should be consensus dips"
    for c in prim:
        assert "dv" in c.metrics and "dv" not in next(o for o in off if o.t_center == c.t_center).metrics
        assert "crowded" in c.flags                         # CROWDSAP 0.7 from the provenance
        assert "secondary_any_phase" in c.flags             # the phase-0.37 secondary
        sec = c.metrics["dv"]["secondary"]
        assert abs(sec["phase"] - 0.37) < 0.03 and sec["snr"] > 7.1
        assert c.metrics["dv"]["ephemeris_source"] in ("transit fit", "BLS")
    assert any(c.passed for c in prim)                      # flags only: the plain vetting passed them


def test_decide_switch_turns_flags_into_failures(runs):
    for c in _on_primary(runs["decide"]):
        assert "secondary_any_phase" in c.flags and not c.passed


def test_candidates_csv_carries_the_s2_columns(runs, tmp_path):
    from exoplan.pipeline import write_candidates
    import csv

    write_candidates(runs["flag"], tmp_path)
    rows = list(csv.DictReader((tmp_path / "candidates.csv").open()))
    assert {"crowdsap", "secondary_phase", "secondary_snr", "centroid_offset_arcsec", "centroid_sigma"} <= set(rows[0])
    assert any(r["crowdsap"] == "0.7" for r in rows)


def test_pixel_tests_run_from_the_pipeline(tmp_path, monkeypatch):
    """With [vetting] pixel = true the pipeline fetches the TPF (stubbed here: a synthetic one with the eclipse on a
    neighbour) and stores the pixel report and its flags. Pass/fail is unchanged without decide."""
    from exoplan import pixel

    def fake_tpf(tic, sector, cache_dir):
        assert (tic, sector) == (123, 1)
        stars = [dict(x=5.2, y=5.4, flux=2e5), dict(x=6.7, y=5.4, flux=2e5 * 10 ** -1.2, eclipse=0.3)]
        return pixel.synthetic_tpf(stars=stars, days=26.0, period=4.0, t0=1002.5, duration=0.2, seed=1)

    monkeypatch.setattr(pixel, "fetch_tpf", fake_tpf)
    monkeypatch.setattr(pixel, "fetch_neighbours", lambda *a, **k: {"source": "stub", "stars": []})
    rng = np.random.default_rng(4)
    time = np.arange(1000.0, 1026.0, 10 / 1440)
    flux = 1 + rng.normal(0, 4e-4, time.size)
    for k in range(7):
        flux -= 3000e-6 * (np.abs(time - (1002.5 + 4.0 * k)) < 0.1)
    lc = LightCurve(target="TIC 123", mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 4e-4),
                    provenance={"sector": 1, "time_unit": "BTJD"})
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1)]
    config = RunConfig(name="px", subject_days=13.0, min_points=100, bin_minutes=10.0, vetting_pixel=True, fap_trials=0)
    cands = run_pipeline(config, [lc], reviewers, tmp_path / "px").candidates
    periodic = [c for c in cands if c.period_days]
    assert periodic
    for c in periodic:
        assert "centroid_offset" in c.flags, c.metrics["pixel"]
        assert c.metrics["pixel"]["centroid"]["psf_target"]["sigma"] > 5
        assert c.passed                                    # a flag, not a failure, without decide


def test_pixel_failure_is_recorded_not_raised(tmp_path, monkeypatch):
    from exoplan import pixel

    monkeypatch.setattr(pixel, "fetch_tpf", lambda *a, **k: (_ for _ in ()).throw(LookupError("MAST down")))
    lc = _eccentric_binary()
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1)]
    config = RunConfig(name="px", subject_days=13.0, min_points=100, bin_minutes=10.0, vetting_pixel=True, fap_trials=0)
    cands = run_pipeline(config, [lc], reviewers, tmp_path / "pxf").candidates
    reports = [c.metrics["pixel"] for c in cands if "pixel" in c.metrics]
    assert reports and all("MAST down" in r["error"] for r in reports)


def test_vetting_section_of_the_config(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[run]\nname = "x"\n[vetting]\npixel = true\ndecide = true\ncrowding_min = 0.75\n')
    c = load_config(path)
    assert c.vetting_pixel and c.vetting_decide and c.vetting_extended and c.crowding_min == 0.75
    d = load_config("configs/default.toml")
    assert d.vetting_extended and not d.vetting_pixel and not d.vetting_decide


def test_load_spoc_file_records_crowding(tmp_path):
    from astropy.io import fits

    n = 500
    time = np.linspace(1325.0, 1335.0, n)
    flux = np.full(n, 1000.0)
    quality = np.zeros(n, int)
    quality[5] = 32
    cols = [fits.Column("TIME", "D", array=time), fits.Column("PDCSAP_FLUX", "E", array=flux),
            fits.Column("PDCSAP_FLUX_ERR", "E", array=np.full(n, 1.0)), fits.Column("QUALITY", "J", array=quality)]
    table = fits.BinTableHDU.from_columns(cols, name="LIGHTCURVE")
    table.header["CROWDSAP"] = 0.6543
    table.header["FLFRCSAP"] = 0.876
    primary = fits.PrimaryHDU()
    primary.header["SECTOR"] = 7
    primary.header["TICID"] = 42
    path = tmp_path / "x_lc.fits"
    fits.HDUList([primary, table]).writeto(path)
    lc = load_spoc_file(path)
    assert lc.target == "TIC 42" and len(lc) == n - 1
    assert lc.provenance["crowdsap"] == pytest.approx(0.6543) and lc.provenance["flfrcsap"] == pytest.approx(0.876)
    assert lc.provenance["sector"] == 7 and len(lc.provenance["file_sha256"]) == 64
    assert np.allclose(lc.flux, 1.0)


def test_spoc_crowding_from_lightkurve_meta():
    class Fake:
        meta = {"CROWDSAP": 0.91, "FLFRCSAP": 0.88}

    assert spoc_crowding(Fake()) == {"crowdsap": 0.91, "flfrcsap": 0.88}

    class Empty:
        meta = {}

    assert spoc_crowding(Empty()) == {}


def _shallow_eb(seed, secondary):
    """1000 ppm primaries every 4 days, a shallow secondary at phase 0.5, 600 ppm per 2-minute point, 27 days."""
    from dvtests_helpers import trapezoid_lc

    return trapezoid_lc(seed=seed, period=4.0, t0=1.0, duration=0.15, depth=1000e-6, noise=600e-6,
                        secondary=secondary, gap=None)


def test_transit_masked_detrending_removes_the_shoulders():
    """The review detrending overshoots beside each transit; read as brightenings, those shoulders vetoed real
    secondaries (a 200 ppm secondary: 0 of 20 flagged). Re-detrended with the transits masked, as DV does, the
    largest brightening falls to the noise level (median 9.2 sigma -> 2.6 sigma over 20 seeds)."""
    from exoplan.dvtests import extended_vet
    from exoplan.pipeline import prepare_lightcurves, vetting_lightcurve

    cfg = RunConfig(name="x")
    plain, masked = [], []
    for seed in range(5):
        lc = _shallow_eb(seed, 200e-6)
        for out, l in ((plain, prepare_lightcurves([lc], cfg)[0]),
                       (masked, vetting_lightcurve([lc], cfg, period=4.0, t0=1.0, duration=0.15))):
            out.append(extended_vet(l.time, l.flux, l.flux_err, period=4.0, t0=1.0, duration=0.15)[1]["secondary"])
    assert np.median([s["max_brightening_snr"] for s in plain]) > 7
    assert np.median([s["max_brightening_snr"] for s in masked]) < 4


def test_shallow_secondary_is_flagged_through_the_full_preparation():
    """A 1000/300 ppm binary at 600 ppm noise, through clean, the transit-masked detrend and 10-minute bins, is
    flagged secondary_any_phase (19 of 20 seeds when measured; 1 of 20 with the unmasked detrend)."""
    from exoplan.dvtests import extended_vet
    from exoplan.pipeline import vetting_lightcurve

    cfg = RunConfig(name="x")
    flagged = 0
    for seed in range(5):
        l = vetting_lightcurve([_shallow_eb(seed, 300e-6)], cfg, period=4.0, t0=1.0, duration=0.15)
        flagged += "secondary_any_phase" in extended_vet(l.time, l.flux, l.flux_err, period=4.0, t0=1.0, duration=0.15)[0]
    assert flagged >= 4


def test_pipeline_uses_the_transit_masked_light_curve(runs):
    for c in _on_primary(runs["flag"]):
        assert c.metrics["dv"]["transit_masked_detrend"] is True

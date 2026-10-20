# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""S2 wiring: the extended tests add flags without changing pass/fail by default; ``[vetting] decide`` turns them into
pass/fail; the pixel tests run from the pipeline; CROWDSAP and FLFRCSAP are read from SPOC headers."""

from dataclasses import replace

import numpy as np
import pytest

from setuhq.config import RunConfig, load_config
from setuhq.lightcurve import LightCurve
from setuhq.loaders import load_spoc_file, spoc_crowding
from setuhq.pipeline import run_pipeline
from setuhq.reviewers.simulated import SimulatedVolunteer


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
    from setuhq.pipeline import write_candidates
    import csv

    write_candidates(runs["flag"], tmp_path)
    rows = list(csv.DictReader((tmp_path / "candidates.csv").open()))
    assert {"crowdsap", "secondary_phase", "secondary_snr", "centroid_offset_arcsec", "centroid_sigma"} <= set(rows[0])
    assert any(r["crowdsap"] == "0.7" for r in rows)


def test_pixel_tests_run_from_the_pipeline(tmp_path, monkeypatch):
    """With [vetting] pixel = true the pipeline fetches the TPF (stubbed here: a synthetic one with the eclipse on a
    neighbour) and stores the pixel report and its flags. Pass/fail is unchanged without decide."""
    from setuhq import pixel

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
    from setuhq import pixel

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


def test_clean_hot_jupiter_passes_the_pipeline(tmp_path):
    """A clean 1% hot Jupiter (P = 2.8 d, 2.6 h, 400 ppm per 2-minute point, 27 days with a mid-sector gap) passes:
    no odd_even_mismatch from vet.py and no odd_even_depth flag. Before the error inflation and the 2% floor, 6 of
    10 such planets failed on odd_even_mismatch (box depths of a deep transit scatter far beyond white noise)."""
    from dvtests_helpers import trapezoid_lc

    lc = trapezoid_lc(seed=4, period=2.8, t0=1.3, duration=0.11, depth=0.01, noise=4e-4)
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1),
                 SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.0, seed=2)]
    cands = run_pipeline(RunConfig(name="hj", subject_days=13.0, min_points=100, bin_minutes=10.0, fap_trials=0),
                         [lc], reviewers, tmp_path / "hj").candidates
    on = [c for c in cands if abs(((c.t_center - 1.3 + 1.4) % 2.8) - 1.4) < 0.06]
    assert len(on) >= 6
    for c in on:
        assert c.passed, c.flags
        assert "odd_even_mismatch" not in c.flags and "odd_even_depth" not in c.flags


def _shallow_eb(seed, secondary):
    """1000 ppm primaries every 4 days, a shallow secondary at phase 0.5, 600 ppm per 2-minute point, 27 days."""
    from dvtests_helpers import trapezoid_lc

    return trapezoid_lc(seed=seed, period=4.0, t0=1.0, duration=0.15, depth=1000e-6, noise=600e-6,
                        secondary=secondary, gap=None)


def test_transit_masked_detrending_removes_the_shoulders():
    """The review detrending overshoots beside each transit; read as brightenings, those shoulders vetoed real
    secondaries (a 200 ppm secondary: 0 of 20 flagged). Re-detrended with the transits masked, as DV does, the
    largest brightening falls to the noise level (median 9.2 sigma -> 2.6 sigma over 20 seeds)."""
    from setuhq.dvtests import extended_vet
    from setuhq.pipeline import prepare_lightcurves, vetting_lightcurve

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
    """A 1000/200 ppm binary at 600 ppm noise, through clean, the two-pass masked detrend and 10-minute bins: the
    secondary keeps most of its depth (the trend no longer absorbs it) and is flagged (19 of 20 seeds when measured,
    10 of 20 with one pass)."""
    from setuhq.dvtests import extended_vet
    from setuhq.pipeline import vetting_lightcurve, vetting_lightcurve_two_pass

    cfg = RunConfig(name="x")
    flagged, kept_one, kept_two = 0, [], []
    for seed in range(5):
        lc = _shallow_eb(seed, 200e-6)
        two, phases = vetting_lightcurve_two_pass([lc], cfg, period=4.0, t0=1.0, duration=0.15)
        assert 0.5 in phases
        f2, m2 = extended_vet(two.time, two.flux, two.flux_err, period=4.0, t0=1.0, duration=0.15)
        one = vetting_lightcurve([lc], cfg, period=4.0, t0=1.0, duration=0.15)
        m1 = extended_vet(one.time, one.flux, one.flux_err, period=4.0, t0=1.0, duration=0.15)[1]
        flagged += "secondary_any_phase" in f2
        kept_two.append(m2["secondary"]["phase_05"]["depth_ppm"])
        kept_one.append(m1["secondary"]["phase_05"]["depth_ppm"])
    assert flagged >= 4
    # the box mean of the injected 200 ppm trapezoid is ~180 ppm
    assert np.median(kept_two) > 150 and np.median(kept_two) > np.median(kept_one) + 15


def test_second_pass_masks_the_first_pass_dip_only_when_it_is_significant():
    """Masking the strongest first-pass dip of every light curve protects the largest noise dip from the trend and
    biases the second pass upward (red-noise false alarms 1/600 -> 8/600 when the reviewer measured it). The dip is
    masked only when the first pass already finds it significant; phase 0.5 is always masked."""
    from dvtests_helpers import trapezoid_lc
    from setuhq.pipeline import vetting_lightcurve_two_pass

    cfg = RunConfig(name="x")
    for seed in range(3):
        lc = trapezoid_lc(seed=seed, period=4.0, t0=1.0, duration=0.15, depth=1000e-6, noise=600e-6, gap=None)
        _, phases = vetting_lightcurve_two_pass([lc], cfg, period=4.0, t0=1.0, duration=0.15)
        assert phases == (0.5,), (seed, phases)
    lc = trapezoid_lc(seed=7, period=4.0, t0=1.0, duration=0.15, depth=4000e-6, noise=600e-6, secondary=1000e-6,
                      secondary_phase=0.37, gap=None)
    _, phases = vetting_lightcurve_two_pass([lc], cfg, period=4.0, t0=1.0, duration=0.15)
    assert len(phases) == 2 and phases[0] == 0.5 and abs(phases[1] - 0.37) < 0.01, phases


def test_pipeline_uses_the_transit_masked_light_curve(runs):
    for c in _on_primary(runs["flag"]):
        assert c.metrics["dv"]["transit_masked_detrend"] is True
        assert 0.5 in c.metrics["dv"]["masked_phases"]


@pytest.mark.parametrize("hours", [6.0, 10.0])
def test_long_transits_through_the_two_pass_detrend_and_the_variants(hours):
    """The path the pipeline takes (extended_vetting): two-pass masked detrend, the extended tests, the detrending
    variants and the reduced FPP, for a 1000 ppm planet with a 6 or 10 hour transit. No flag, no excursion beyond the
    transit, every variant anchored, and the FPP not refused."""
    from dvtests_helpers import trapezoid_lc
    from setuhq.dvtests import extended_vet
    from setuhq.pipeline import MIN_ANCHOR_SUPPORT, secondary_variants, vetting_lightcurve_two_pass
    from setuhq.validate import reduced_fpp

    dur, cfg = hours / 24.0, RunConfig(name="x")
    eph = dict(period=9.0, t0=2.0, duration=dur)
    for seed in range(2):
        lc = trapezoid_lc(seed=seed, depth=1000e-6, noise=3e-4, gap=(13.2, 14.2), **eph)
        lc = lc.with_data(lc.time, lc.flux + 2e-4 * np.sin(lc.time / 3.0), lc.flux_err)
        m, phases = vetting_lightcurve_two_pass([lc], cfg, **eph)
        assert phases == (0.5,) and np.max(np.abs(m.flux - 1)) < 2500e-6
        flags, dv = extended_vet(m.time, m.flux, m.flux_err, **eph)
        assert not flags, (seed, flags)
        var = secondary_variants([lc], cfg, **eph, extra_phases=phases)
        assert len(var) == 4 and all(v["anchor_support"] >= MIN_ANCHOR_SUPPORT for v in var)
        v = reduced_fpp(depth=1e-3, dv=dv, variants=var)
        assert v.refused is None, (seed, v.refused)


@pytest.mark.parametrize("hours", [6.0, 10.0])
def test_long_transits_survive_the_masked_detrend(hours):
    """A 1000 ppm planet with a 6 or 10 hour transit (P = 9 d, 300 ppm noise, slow stellar variability): masking 3 T14
    of a 1-day window left the quadratic extrapolating (excursions of 10^4 to 10^6 ppm, false secondary_any_phase and
    timing_inconsistent). With the trend interpolated across the masked span and the window widened to 12 T14, the
    light curve stays within the transit plus noise and no flag is raised."""
    from dvtests_helpers import trapezoid_lc
    from setuhq.dvtests import extended_vet
    from setuhq.pipeline import vetting_lightcurve

    dur = hours / 24.0
    for seed in range(4):
        lc = trapezoid_lc(seed=seed, period=9.0, t0=2.0, duration=dur, depth=1000e-6, noise=3e-4, gap=None)
        lc = lc.with_data(lc.time, lc.flux + 2e-4 * np.sin(lc.time / 3.0), lc.flux_err)
        m = vetting_lightcurve([lc], RunConfig(name="x"), period=9.0, t0=2.0, duration=dur)
        assert np.max(np.abs(m.flux - 1)) < 2500e-6
        flags, _ = extended_vet(m.time, m.flux, m.flux_err, period=9.0, t0=2.0, duration=dur)
        assert "secondary_any_phase" not in flags and "timing_inconsistent" not in flags, (seed, flags)


def test_mask_anchor_support():
    from setuhq.pipeline import mask_anchor_support

    t = np.arange(0.0, 10.0, 0.01)
    lone = (t >= 2.0) & (t < 2.6)
    assert mask_anchor_support(t, lone, 1.0) == 1.0
    pair = lone | ((t >= 2.8) & (t < 3.4))   # 0.2 d kept between the spans, inside half a window (0.5 d)
    assert 0.35 < mask_anchor_support(t, pair, 1.0) < 0.45
    assert mask_anchor_support(t, np.zeros(t.size, bool), 1.0) == 1.0


def test_poorly_anchored_variants_are_left_out():
    """P = 1.5 d with T14 = 0.15 d and phase 0.5 masked: a 2 T14 mask leaves 0.15 d between spans 0.75 d apart, too
    little to anchor the trend (spurious dips inside the spans refused the FPP), so those variants are dropped; the
    1 T14 variants are kept."""
    from dvtests_helpers import trapezoid_lc
    from setuhq.pipeline import MIN_ANCHOR_SUPPORT, secondary_variants

    lc = trapezoid_lc(seed=1, period=1.5, t0=0.4, duration=0.15, depth=1000e-6, noise=600e-6, gap=None)
    var = secondary_variants([lc], RunConfig(name="x"), period=1.5, t0=0.4, duration=0.15, extra_phases=(0.5,))
    assert sorted({v["mask_t14"] for v in var}) == [1.0]
    assert all(v["anchor_support"] >= MIN_ANCHOR_SUPPORT for v in var)

import pytest
import numpy as np

from exoplan.injection import synthetic_subject
from exoplan.search import bls_search, single_event_search


def test_single_event_search_finds_injected_transit(transit_subject):
    subject, injection = transit_subject
    events = single_event_search(subject)
    assert events, "expected at least one event"
    best = events[0]
    assert injection.t_start - 0.1 <= best.center <= injection.t_end + 0.1
    assert 0.002 < best.depth < 0.004


def test_single_event_search_is_quiet_on_pure_noise(empty_subject):
    assert single_event_search(empty_subject, snr_threshold=6.0) == []


def test_single_event_search_rejects_windows_bridging_a_gap(rng):
    time = np.arange(0, 13, 10 / 1440)
    keep = ~((time > 4.0) & (time < 6.0))  # two-day hole
    flux = np.ones(keep.sum()) + rng.normal(0, 2e-4, keep.sum())
    from exoplan.subjects import Subject

    subject = Subject("gap", "TESS", "BTJD", time[keep], flux, np.full(keep.sum(), 2e-4))
    assert single_event_search(subject, snr_threshold=5.0) == []


def test_bls_recovers_period_of_periodic_transits(rng):
    from exoplan.injection import Injection

    injections = tuple(
        Injection(t_start=1.0 + 3.1 * k, t_end=1.0 + 3.1 * k + 0.1, depth=0.002) for k in range(4)
    )
    subject = synthetic_subject(rng, subject_id="periodic", injections=injections, white_ppm=300.0, red_ppm=0.0)
    signal = bls_search(subject, min_period=1.0)
    assert signal is not None
    assert abs(signal.period - 3.1) / 3.1 < 0.01
    assert signal.n_transits >= 3


def test_bls_returns_none_for_too_short_subject(rng):
    subject = synthetic_subject(rng, subject_id="short", length_days=0.5)
    assert bls_search(subject) is None


def test_single_event_window_cannot_bridge_gap(rng):
    from exoplan.subjects import Subject

    time = np.arange(0, 13, 10 / 1440)
    keep = ~((time > 5.00) & (time < 5.03))  # a 40-minute hole inside a 1-hour box
    t = time[keep]
    flux = np.ones(t.size) + rng.normal(0, 2e-4, t.size)
    flux[(t > 5.03) & (t < 5.17)] -= 0.01
    subject = Subject("gap", "TESS", "BTJD", t, flux, np.full(t.size, 2e-4))
    for event in single_event_search(subject, durations=(1 / 24,)):
        assert event.t_end - event.t_start < 1.5 * (1 / 24)


def _two_sectors_with_9_day_planet(seed=3):
    """Two 13.5-day synthetic sectors with a 1-day gap; a 3000 ppm, 4-hour transit every 9 days from t=3."""
    from exoplan.lightcurve import LightCurve

    rng = np.random.default_rng(seed)
    curves = []
    for sector, (a, b) in ((1, (0.0, 13.5)), (2, (14.5, 28.0))):
        time = np.arange(a, b, 2 / 1440)
        flux = 1 + rng.normal(0, 1e-3, time.size)
        for centre in (3.0, 12.0, 21.0):
            flux -= 3000e-6 * (np.abs(time - centre) < 2 / 24)
        # Different flux levels per sector, as in real SPOC data.
        level = 1000.0 * sector
        curves.append(LightCurve(target="TIC SYN-9", mission="TESS", time=time, flux=flux * level,
                                 flux_err=np.full(time.size, 1e-3 * level), provenance={"sector": sector}))
    return curves


def test_sector_search_recovers_a_9_day_period_that_subject_search_cannot():
    from exoplan.config import RunConfig
    from exoplan.pipeline import prepare_lightcurves, prepare_subjects, sector_signals

    config = RunConfig(name="t", subject_days=13.0, min_points=100, bin_minutes=10.0, search="sector", fap_trials=0)
    prepared = prepare_lightcurves(_two_sectors_with_9_day_planet(), config)
    signal = sector_signals(prepared, config)["TIC SYN-9"]
    assert signal is not None and abs(signal.period - 9.0) < 0.09
    assert signal.n_transits == 3
    assert abs(((signal.t0 - 3.0 + 4.5) % 9.0) - 4.5) < 0.05

    for subject in prepare_subjects([], config, prepared=prepared):
        per_subject = bls_search(subject, min_period=config.min_period)
        assert per_subject is None or abs(per_subject.period - 9.0) > 0.09


def test_pipeline_sector_mode_reports_the_9_day_period(tmp_path):
    import json

    from exoplan.config import RunConfig
    from exoplan.pipeline import run_pipeline
    from exoplan.reviewers import SimulatedVolunteer

    reviewers = [SimulatedVolunteer(f"vol-{i}", snr_threshold=4.5, miss_probability=0.0, seed=i) for i in range(3)]
    periods = {}
    for mode in ("subject", "sector"):
        config = RunConfig(name=mode, subject_days=13.0, min_points=100, bin_minutes=10.0, search=mode, fap_trials=0)
        summary = run_pipeline(config, _two_sectors_with_9_day_planet(), reviewers, tmp_path / mode)
        periods[mode] = [c.period_days for c in summary.candidates if c.period_days]
        manifest = json.loads((tmp_path / mode / "manifest.json").read_text())
        assert manifest["search_scope"] == mode
    assert periods["sector"] and all(abs(p - 9.0) < 0.09 for p in periods["sector"])
    assert not any(abs(p - 9.0) < 0.09 for p in periods["subject"])


def test_config_reads_search_scope(tmp_path):
    from exoplan.config import load_config

    path = tmp_path / "c.toml"
    path.write_text('[run]\nname = "x"\nsearch = "sector"\n')
    assert load_config(path).search == "sector"
    path.write_text('[run]\nname = "x"\n')
    assert load_config(path).search == "subject"
    path.write_text('[run]\nsearch = "galaxy"\n')
    with pytest.raises(ValueError):
        load_config(path)


def _fap_subject(seed, *, red_ppm, signal):
    from exoplan.injection import Injection

    rng = np.random.default_rng(seed)
    injections = tuple(Injection(1.0 + 3.1 * k, 1.125 + 3.1 * k, 0.003) for k in range(4)) if signal else ()
    return synthetic_subject(rng, subject_id=f"fap-{seed}-{red_ppm}-{signal}", injections=injections,
                             white_ppm=300.0, red_ppm=red_ppm)


@pytest.mark.parametrize("red_ppm", [0.0, 600.0])
def test_fap_is_high_on_pure_noise(red_ppm):
    from exoplan.search import with_fap

    subject = _fap_subject(1, red_ppm=red_ppm, signal=False)
    signal = with_fap(subject, bls_search(subject))
    assert signal.fap_trials == 20
    assert signal.fap >= 0.3


def test_fap_is_low_for_an_injected_3000_ppm_periodic_signal_in_white_and_red_noise():
    from exoplan.search import with_fap

    for red_ppm in (0.0, 600.0):
        subject = _fap_subject(2, red_ppm=red_ppm, signal=True)
        # 20 trials cannot resolve 1%: no trial reaches the SNR, so the FAP is the bound 1/21 and says so.
        signal = with_fap(subject, bls_search(subject))
        assert abs(signal.period - 3.1) < 0.05
        assert signal.fap_exceed == 0 and signal.fap_bound and signal.fap == pytest.approx(1 / 21)
        assert signal.fap_label == "< 4.8e-02 (20 trials)"
        # 200 trials resolve it: the bound is 1/201 < 1%.
        signal = with_fap(subject, bls_search(subject), n_trials=200)
        assert signal.fap_bound and signal.fap == pytest.approx(1 / 201) and signal.fap < 0.01
        assert signal.fap_tail is not None and signal.fap_tail < signal.fap  # extrapolated, kept apart from the bound
        assert "Gumbel" in signal.fap_method and "upper bound" in signal.fap_method


def test_red_noise_fools_the_white_noise_snr_but_not_the_fap():
    from exoplan.search import with_fap

    subject = _fap_subject(1, red_ppm=600.0, signal=False)
    signal = with_fap(subject, bls_search(subject))
    assert signal.snr > 10.0 and signal.fap >= 0.3


def test_feed_admission_requires_fap_below_one_percent():
    from exoplan.discover import admits_fap

    assert admits_fap(0.0)
    assert not admits_fap(0.05)
    assert not admits_fap(None)



def test_fap_never_reports_below_its_resolution_and_is_cached(tmp_path):
    from exoplan.search import false_alarm_probability, fap_label

    subject = _fap_subject(3, red_ppm=0.0, signal=True)
    sig = bls_search(subject)
    one = false_alarm_probability(subject, sig, n_trials=40, seed=7, cache_dir=tmp_path, workers=1)
    assert one.exceed == 0 and one.bound and one.fap == 1 / 41
    assert len(list(tmp_path.glob("*.json"))) == 1
    # The cached null maxima give the same answer, and the worker count does not change it.
    again = false_alarm_probability(subject, sig, n_trials=40, seed=7, cache_dir=tmp_path, workers=1)
    assert again == one
    par = false_alarm_probability(subject, sig, n_trials=40, seed=7, workers=2)
    assert (par.fap, par.exceed) == (one.fap, one.exceed)
    assert fap_label(1 / 10001, 10000, True) == "< 1.0e-04 (10,000 trials)" and fap_label(0.25, 20, False) == "0.25 (20 trials)"
    assert fap_label(None, 0, False) == "not computed"

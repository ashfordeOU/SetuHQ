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

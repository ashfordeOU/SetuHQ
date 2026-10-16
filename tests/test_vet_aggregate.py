import numpy as np

from exoplan.aggregate import aggregate, cluster_marks
from exoplan.injection import Injection, synthetic_subject
from exoplan.reviewers.base import NOISE, POTENTIAL_PLANET, Classification, Mark
from exoplan.search import PeriodicSignal
from exoplan.vet import vet_event


def _cls(reviewer, marks, label=POTENTIAL_PLANET, subject="s1"):
    return Classification(reviewer, subject, label, tuple(Mark(a, b) for a, b in marks))


def test_vet_passes_clean_transit(transit_subject):
    subject, injection = transit_subject
    result = vet_event(injection.t_start, injection.t_end, subject)
    assert result.passed, result.flags


def test_vet_flags_low_snr_on_noise(empty_subject):
    result = vet_event(5.0, 5.2, empty_subject)
    assert not result.passed
    assert "low_snr" in result.flags


def test_vet_flags_secondary_eclipse(rng):
    injections = (
        Injection(2.0, 2.15, 0.004),
        Injection(2.0 + 0.5 * 4.0, 2.15 + 0.5 * 4.0, 0.004),
    )
    subject = synthetic_subject(rng, subject_id="eb", injections=injections, white_ppm=150.0, red_ppm=0.0)
    periodic = PeriodicSignal(
        period=4.0, t0=2.075, duration=0.15, depth=0.004, snr=40.0, n_transits=3,
        odd_depth=0.004, odd_err=1e-4, even_depth=0.004, even_err=1e-4,
        secondary_depth=0.004, secondary_err=1e-4,
    )
    result = vet_event(2.0, 2.15, subject, periodic)
    assert "secondary_eclipse" in result.flags
    assert not result.passed


def test_single_transit_seen_by_one_parity_is_not_odd_even_mismatch(rng):
    subject = synthetic_subject(rng, subject_id="single", white_ppm=150.0, red_ppm=0.0)
    periodic = PeriodicSignal(
        period=5.27, t0=1.23, duration=0.17, depth=0.001, snr=27.0, n_transits=3,
        odd_depth=0.0028, odd_err=6e-5, even_depth=0.00015, even_err=4e-5,
        secondary_depth=0.0, secondary_err=4.5e-5,
    )
    result = vet_event(2.0, 2.15, subject, periodic)
    assert "odd_even_mismatch" not in result.flags


def test_vet_flags_odd_even_mismatch(rng):
    subject = synthetic_subject(rng, subject_id="oe", white_ppm=150.0, red_ppm=0.0)
    periodic = PeriodicSignal(
        period=4.0, t0=2.075, duration=0.15, depth=0.003, snr=30.0, n_transits=3,
        odd_depth=0.005, odd_err=2e-4, even_depth=0.002, even_err=2e-4,
        secondary_depth=0.0, secondary_err=2e-4,
    )
    result = vet_event(2.0, 2.15, subject, periodic)
    assert "odd_even_mismatch" in result.flags


def test_cluster_marks_groups_nearby_centres_only():
    entries = [("a", 1.00, 1.10), ("b", 1.02, 1.12), ("c", 5.00, 5.10)]
    clusters = cluster_marks(entries, gap_days=0.05)
    assert [sorted(e[0] for e in c) for c in clusters] == [["a", "b"], ["c"]]


def test_aggregate_scores_by_skill_weighted_share():
    panel = [
        _cls("r1", [(1.0, 1.1)]),
        _cls("r2", [(1.01, 1.11)]),
        _cls("r3", [], label=NOISE),
        _cls("r4", [(1.02, 1.12)]),
    ]
    weights = {"r1": 1.0, "r2": 1.0, "r3": 1.0, "r4": 0.5}
    (event,) = aggregate(panel, weights, min_score=0.0, min_planet_fraction=0.0)
    assert event.n_reviewers == 3
    assert abs(event.score - (1.0 + 1.0 + 0.5) / 3.5) < 1e-9


def test_aggregate_drops_event_when_panel_says_noise():
    panel = [
        _cls("r1", [(1.0, 1.1)]),
        _cls("r2", [], label=NOISE),
        _cls("r3", [], label=NOISE),
    ]
    assert aggregate(panel, {}, min_score=0.0, min_planet_fraction=0.5) == []


def test_aggregate_keeps_only_events_above_min_score():
    panel = [_cls("r1", [(1.0, 1.1)]), _cls("r2", [(9.0, 9.1)]), _cls("r3", [(9.01, 9.11)])]
    events = aggregate(panel, {}, min_score=0.5, min_planet_fraction=0.0)
    assert len(events) == 1
    assert abs(events[0].center - 9.05) < 0.02


def test_later_classification_by_same_reviewer_replaces_earlier():
    panel = [_cls("r1", [(1.0, 1.1)]), _cls("r1", [(2.0, 2.1)])]
    (event,) = aggregate(panel, {}, min_score=0.0, min_planet_fraction=0.0)
    assert abs(event.center - 2.05) < 1e-9


def test_aggregate_merges_split_duplicates_of_one_dip():
    panel = [
        _cls("r1", [(1.00, 1.08)]),
        _cls("r2", [(1.00, 1.08)]),
        _cls("r3", [(1.03, 1.035)]),  # same dip, boundaries disagree, lands in its own cluster
    ]
    events = aggregate(panel, {}, gap_days=0.001, min_score=0.0, min_planet_fraction=0.0)
    assert len(events) == 1
    assert events[0].n_reviewers >= 2


def test_off_ephemeris_flag_does_not_change_pass_result(transit_subject):
    from exoplan.pipeline import _vet
    from exoplan.search import PeriodicSignal
    from exoplan.aggregate import Consensus

    subject, injection = transit_subject
    periodic = PeriodicSignal(
        period=4.0, t0=1.0, duration=0.1, depth=0.003, snr=30.0, n_transits=3,
        odd_depth=0.003, odd_err=1e-4, even_depth=0.003, even_err=1e-4,
        secondary_depth=0.0, secondary_err=1e-4,
    )
    event = Consensus(subject.subject_id, injection.t_start, injection.t_end, 1.0, 3, ("a",), 1.0)
    baseline = _vet(event, subject, None)
    flagged = _vet(event, subject, periodic)
    assert "off_ephemeris" in flagged.flags
    assert flagged.passed == baseline.passed


def test_vet_flags_large_eclipsing_binary_mismatch_at_half_period(rng):
    subject = synthetic_subject(rng, subject_id="eb-half", white_ppm=150.0, red_ppm=0.0)
    periodic = PeriodicSignal(
        period=4.0, t0=2.075, duration=0.15, depth=0.0058, snr=40.0, n_transits=3,
        odd_depth=0.010, odd_err=1e-4, even_depth=0.0015, even_err=1e-4,
        secondary_depth=0.0, secondary_err=1e-4,
    )
    result = vet_event(2.0, 2.15, subject, periodic)
    assert "odd_even_mismatch" in result.flags
    assert not result.passed

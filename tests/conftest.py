import numpy as np
import pytest

from setuhq.injection import fixed_injection, synthetic_subject
from setuhq.lightcurve import LightCurve


@pytest.fixture
def rng():
    return np.random.default_rng(12345)


@pytest.fixture
def transit_subject(rng):
    """A 13-day white-noise subject with one 3000 ppm, 4-hour transit at its centre."""
    injection = fixed_injection(13.0, depth_ppm=3000.0, duration_hours=4.0)
    subject = synthetic_subject(
        rng,
        subject_id="test-transit",
        injections=(injection,),
        white_ppm=200.0,
        red_ppm=0.0,
    )
    return subject, injection


@pytest.fixture
def empty_subject(rng):
    return synthetic_subject(rng, subject_id="test-empty", white_ppm=200.0, red_ppm=0.0)


@pytest.fixture
def lightcurve_with_transits(rng):
    """A 40-day light curve with a 6-hour transit every 5 days, for pipeline tests."""
    time = np.arange(0.0, 40.0, 10 / 1440)
    flux = 1 + rng.normal(0, 2e-4, time.size)
    for k in range(8):
        centre = 2.5 + 5.0 * k
        flux -= 2500e-6 * ((time > centre - 0.125) & (time < centre + 0.125))
    return LightCurve(
        target="TIC TEST-1",
        mission="TESS",
        time=time,
        flux=flux,
        flux_err=np.full(time.size, 2e-4),
        provenance={"sector": 1, "time_unit": "BTJD"},
    )


@pytest.fixture(scope="session")
def pi_men_app(tmp_path_factory):
    """The app built once per session from the committed pi Men run and the discovery catalogue, with the archive
    query refused (no network). Shared by every module that reads the built site; tests must not write into it."""
    from pathlib import Path

    import setuhq.docket as dm
    from setuhq.app import build_app

    keep = dm.query_archive
    dm.query_archive = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("test"))
    try:
        return build_app(Path("runs/tess-pi-men-s1"), tmp_path_factory.mktemp("pimen") / "app", title="t",
                         catalog_path="docs/discoveries/catalog.json")
    finally:
        dm.query_archive = keep


def _synthetic_run(out, *, seed, target, name):
    """A 26-day synthetic TESS run (six 2500 ppm transits every 4 days) through the pipeline with two Probes."""
    from setuhq.config import RunConfig
    from setuhq.pipeline import run_pipeline
    from setuhq.reviewers.simulated import SimulatedVolunteer

    rng = np.random.default_rng(seed)
    time = np.arange(0.0, 26.0, 10 / 1440)
    flux = 1 + rng.normal(0, 2e-4, time.size)
    for k in range(6):
        centre = 2.5 + 4.0 * k
        flux -= 2500e-6 * ((time > centre - 0.125) & (time < centre + 0.125))
    lc = LightCurve(target=target, mission="TESS", time=time, flux=flux, flux_err=np.full(time.size, 2e-4),
                    provenance={"sector": 1, "time_unit": "BTJD"})
    reviewers = [SimulatedVolunteer("vol-a", snr_threshold=4.5, miss_probability=0.0, seed=1),
                 SimulatedVolunteer("vol-b", snr_threshold=5.0, miss_probability=0.0, seed=2)]
    run_pipeline(RunConfig(name=name, subject_days=13.0, min_points=100, bin_minutes=10.0), [lc], reviewers, out)
    return out


@pytest.fixture(scope="session")
def app_run(tmp_path_factory):
    """The synthetic run the app and plate tests read (built once per session; tests must not write into it)."""
    return _synthetic_run(tmp_path_factory.mktemp("apprun"), seed=11, target="TIC TEST-3", name="app")


@pytest.fixture(scope="session")
def story_run(tmp_path_factory):
    """The synthetic run the story, methods, galaxy and round-6/7 tests read (built once per session)."""
    return _synthetic_run(tmp_path_factory.mktemp("storyrun"), seed=5, target="TIC STORY-1", name="story")

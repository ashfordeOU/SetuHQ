import numpy as np
import pytest

from exoplan.injection import fixed_injection, synthetic_subject
from exoplan.lightcurve import LightCurve


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

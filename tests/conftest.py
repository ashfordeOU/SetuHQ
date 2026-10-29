# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
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


def site_bundle(index_path) -> str:
    """A built site as one text, for the tests that read the app's views: every view's markup (the shared views file),
    then the home page, the app's data as a JSON script tag, the stylesheet and the script."""
    from pathlib import Path

    root = Path(index_path).parent
    one = lambda pattern: next(root.glob(pattern)).read_text()  # noqa: E731
    data = one("assets/data/app-*.json").replace("</", "<\\/")
    from setuhq.i18n import unkey

    return unkey(f'<main>{one("assets/views-*.html")}</main>\n{Path(index_path).read_text()}\n'
            f'<script id="data" type="application/json">{data}</script>\n<style>{one("assets/site-*.css")}</style>\n'
            f'<script>{one("assets/site-*.js")}</script><script>{one("assets/app-*.js")}</script>\n'
            f'<template id="docket-frame">{one("assets/frame/case-file-*.html")}</template>')  # the markup, keys aside


_SERVERS = {}


def served(index_path) -> str:
    """The address of a built site served at a local domain root, as GitHub Pages serves it (a folder's index.html,
    404.html for anything else), for the tests that drive Chromium. One server per site, for the session."""
    import functools
    import http.server
    import threading
    from pathlib import Path

    root = Path(index_path).resolve().parent
    if root not in _SERVERS:
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send_error(self, code, message=None, explain=None):
                nf = root / "404.html"
                if code == 404 and nf.exists():
                    body = nf.read_bytes()
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().send_error(code, message, explain)

        Handler.extensions_map = {**Handler.extensions_map, ".js": "text/javascript", ".json": "application/json",
                                  ".woff2": "font/woff2", ".svg": "image/svg+xml"}
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _SERVERS[root] = f"http://127.0.0.1:{srv.server_address[1]}/"
    return _SERVERS[root]

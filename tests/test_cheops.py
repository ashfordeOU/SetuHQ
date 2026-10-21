# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""CHEOPS (setuhq.cheops): public data only, the acknowledgement on every output, detrending, the common timeline.

Offline: the archive is replaced by a recorded excerpt of one public visit (tests/data/cheops_gj65_excerpt.json,
derived columns with their provenance, not a raw CHEOPS file)."""

import gzip
import json
import math
from pathlib import Path

import numpy as np
import pytest

from setuhq import cheops as ch
from setuhq.lightcurve import LightCurve

FIXTURE = Path(__file__).parent / "data" / "cheops_gj65_excerpt.json"
ESA_SENTENCE = ("CHEOPS is an ESA mission in partnership with Switzerland with important contributions to the payload and "
                "the ground segment from Austria, Belgium, France, Germany, Hungary, Italy, Portugal, Spain, Sweden, and "
                "the United Kingdom.")


def assert_credited(out: dict, file_keys=()):
    """Every CHEOPS-derived output carries ESA's acknowledgement, the programme and visit ids, the credit line, the
    three papers, DACE's acknowledgement and SetuHQ's disclaimer."""
    text = json.dumps(out, default=str)
    assert ESA_SENTENCE in text
    assert "not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS mission or the CHEOPS Consortium" in text
    for cite in ("Benz", "Hoyer", "Fortier"):
        assert cite in text
    assert "Data & Analysis Center for Exoplanets (DACE)" in text
    for fk in file_keys:
        assert fk in text and ch.programme_id(fk) in text
    if file_keys:
        assert "Credit: ESA, " in text


@pytest.fixture(scope="module")
def excerpt():
    return json.loads(FIXTURE.read_text())


@pytest.fixture
def cached(tmp_path, excerpt):
    """A cache holding the excerpt as if it had been fetched, and the visit listing."""
    meta = excerpt["meta"]
    vdir = tmp_path / "visits"
    vdir.mkdir()
    payload = {"meta": meta, "aperture": "default", "arrays": excerpt["arrays"]}
    (vdir / f"{meta['file_key']}_default.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode()))
    listing = {"target": "GJ 65", "visits": [meta], "n_public": 1, "n_not_public_dropped": 0, **ch.credit([meta])}
    (vdir / "GJ_65.json").write_text(json.dumps(listing))
    return tmp_path


def test_fixture_is_a_small_derived_public_excerpt(excerpt):
    p = excerpt["provenance"]
    assert p["status_published"] is True and p["programme"] == "CH_PR100018" and p["file_key"].startswith("CH_PR100018_TG")
    assert p["obs_id"] and p["pi_name"] and p["drp_version"]
    assert FIXTURE.stat().st_size < 50_000
    assert not any(FIXTURE.parent.glob("*.fits"))  # no raw CHEOPS file in the repository


def test_acknowledgement_is_esas_text_and_the_credit_block_is_complete():
    assert ch.ACKNOWLEDGEMENT.startswith(ESA_SENTENCE)
    assert "https://cheops.unige.ch/archive_browser/" in ch.ACKNOWLEDGEMENT
    c = ch.credit([{"file_key": "CH_PR100010_TG001501_V0300", "obs_id": 1, "pi_name": "A. PI"}])
    assert c["credits"][0]["credit"] == "Credit: ESA, A. PI" and c["credits"][0]["programme"] == "CH_PR100010"
    assert_credited(c, ["CH_PR100010_TG001501_V0300"])
    assert "data.licences@esa.int" in c["commercial_use"]
    t = ch.credit_text([{"file_key": "CH_PR100010_TG001501_V0300", "obs_id": 1, "pi_name": "A. PI"}])
    assert ESA_SENTENCE in t and "Credit: ESA, A. PI" in t and ch.DISCLAIMER in t


def test_only_public_visits_and_latest_versions_are_kept():
    rows = [{"file_key": "CH_PR1_TG0001_V0200", "status_published": True, "db_lc_available": True},
            {"file_key": "CH_PR1_TG0001_V0300", "status_published": True, "db_lc_available": True},
            {"file_key": "CH_PR1_TG0002_V0300", "status_published": False, "db_lc_available": True}]
    pub, dropped = ch.public_only(rows)
    assert dropped == 1 and all(r["status_published"] for r in pub)
    assert [r["file_key"] for r in ch.latest_versions(pub)] == ["CH_PR1_TG0001_V0300"]


def test_list_visits_without_network(tmp_path):
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    raw = {"file_key": ["CH_PR100018_TG000101_V0300", "CH_PR100018_TG000102_V0300"], "status_published": [True, False],
           "db_lc_available": [True, True], "obs_id": [11, 12], "pi_name": ["P I", "P I"], "visit_id": [1, 2],
           "obj_id_catname": ["X", "X"]}
    out = ch.list_visits("X", cache_dir=tmp_path, query=lambda c, r: raw, resolve=lambda n: SkyCoord(1 * u.deg, 2 * u.deg))
    assert out["n_public"] == 1 and out["n_not_public_dropped"] == 1
    assert [v["file_key"] for v in out["visits"]] == ["CH_PR100018_TG000101_V0300"]
    assert_credited(out, ["CH_PR100018_TG000101_V0300"])
    # cached: a second call needs no query
    again = ch.list_visits("X", cache_dir=tmp_path, query=lambda c, r: pytest.fail("cached"), resolve=lambda n: None)
    assert again == json.loads(json.dumps(out))


def test_a_visit_not_marked_public_is_refused_before_any_request(tmp_path):
    with pytest.raises(ch.CheopsUnavailable, match="public"):
        ch.fetch_visit({"file_key": "CH_PR1_TG1_V0300", "status_published": False}, cache_dir=tmp_path,
                       fetch=lambda *a: pytest.fail("no request for a proprietary visit"))


def test_fetch_caches_and_converts_time(tmp_path, excerpt):
    calls = []

    def fake(name, fk, ap):
        calls.append(fk)
        return excerpt["arrays"]

    meta = excerpt["meta"]
    v = ch.fetch_visit(meta, cache_dir=tmp_path, fetch=fake)
    v2 = ch.fetch_visit(meta, cache_dir=tmp_path, fetch=fake)
    assert calls == [meta["file_key"]] and v2.time.size == v.time.size
    bjd = np.array(excerpt["arrays"]["obj_date_bjd_vect"], float)
    assert v.time[0] == pytest.approx(bjd[0] - 57000.0)          # BTJD = BJD_TDB - 2457000
    assert 2100 < v.time[0] < 2200 and 40 < v.cadence_s < 70
    assert_credited(v.provenance(), [meta["file_key"]])


def test_detrend_removes_injected_roll_angle_systematics(cached):
    v = ch.fetch_visit(json.loads((cached / "visits" / "GJ_65.json").read_text())["visits"][0], cache_dir=cached, offline=True)
    base = ch.detrend_visit(v)
    phi = np.deg2rad(v.roll)
    v.flux = v.flux * (1 + 3e-3 * np.sin(phi) + 2e-3 * np.cos(2 * phi))
    d = ch.detrend_visit(v)
    assert {"sin1", "cos2"} <= set(d["terms"])
    assert d["rms_detrended_ppm"] < d["rms_raw_ppm"]
    assert d["rms_detrended_ppm"] == pytest.approx(base["rms_detrended_ppm"], rel=0.25)
    assert_credited(d["provenance"], [v.meta["file_key"]])


def test_detrend_protects_a_flare_and_flags_bad_data(cached):
    v = ch.fetch_visit(json.loads((cached / "visits" / "GJ_65.json").read_text())["visits"][0], cache_dir=cached, offline=True)
    k = v.time.size // 2
    v.flux = v.flux.copy()
    v.flux[k:k + 4] *= 1 + np.array([0.03, 0.02, 0.012, 0.006])
    v.flags = v.flags.copy()
    v.flags[3] = 1
    d = ch.detrend_visit(v)
    assert d["flux"][k] - 1 > 0.02           # the flare is not decorrelated away
    assert np.isnan(d["flux"][3]) and d["n_bad"] >= 1


def test_a_known_signal_is_kept_through_detrending(cached):
    v = ch.fetch_visit(json.loads((cached / "visits" / "GJ_65.json").read_text())["visits"][0], cache_dir=cached, offline=True)
    sig = 1 + 1e-2 * np.sin(2 * math.pi * 20.0 * (v.time - v.time[0]))
    v.flux = v.flux * sig
    d = ch.detrend_visit(v, signal=sig, protect_upward=False)
    ok = np.isfinite(d["flux"])
    kept = np.corrcoef(d["flux"][ok], sig[ok])[0, 1]
    assert kept > 0.8 and d["signal_model"]
    # the signal's amplitude survives: the systematics model did not absorb it
    amp = np.std(d["flux"][ok] / np.median(d["flux"][ok]) - 1)
    assert amp > 0.6 * 1e-2 / math.sqrt(2)


def test_common_timeline_and_end_to_end_offline(cached):
    out = ch.get_cheops_lightcurve("GJ 65", cache_dir=cached, offline=True)
    assert out["n_public_visits"] == 1 and out["visits"][0]["detrend"]["terms"] is not None
    assert_credited({k: v for k, v in out.items() if k != "visits"}, [out["visits"][0]["provenance"]["file_key"]])
    tess = LightCurve(target="TIC 632499596", mission="TESS", time=np.linspace(2120, 2140, 50), flux=np.ones(50),
                      flux_err=np.full(50, 1e-3), provenance={"time_unit": "BTJD", "sector": 30})
    tl = ch.common_timeline([out["visits"][0]["_detrended"]], [tess])
    assert [s["mission"] for s in tl["segments"]] == ["TESS", "CHEOPS"]
    assert tl["time_unit"].startswith("BTJD")
    assert_credited(tl, [out["visits"][0]["provenance"]["file_key"]])
    with pytest.raises(ValueError):
        ch.common_timeline([], [LightCurve(target="x", mission="TESS", time=np.arange(3.0), flux=np.ones(3),
                                           flux_err=np.ones(3), provenance={"time_unit": "BJD"})])


def test_offline_without_cache_says_so(tmp_path):
    with pytest.raises(ch.CheopsUnavailable, match="offline"):
        ch.get_cheops_lightcurve("Nowhere", cache_dir=tmp_path, offline=True)


def test_missing_client_gives_a_clear_message(monkeypatch, tmp_path):
    import builtins

    real = builtins.__import__

    def no_dace(name, *a, **k):
        if name.startswith("dace_query"):
            raise ImportError("no dace")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_dace)
    with pytest.raises(ch.CheopsUnavailable, match=r"setuhq\[cheops\]"):
        ch._client()


def test_read_drp_fits_offline(tmp_path):
    from astropy.io import fits

    n = 50
    cols = [fits.Column(name=k, format="D", array=a) for k, a in (
        ("BJD_TIME", 2459139.0 + np.arange(n) / 2000), ("FLUX", 1e6 + np.arange(n)), ("FLUXERR", np.full(n, 100.0)),
        ("ROLL_ANGLE", np.linspace(0, 360, n)), ("CENTROID_X", np.ones(n)), ("CENTROID_Y", np.ones(n)),
        ("BACKGROUND", np.ones(n)), ("CONTA_LC", np.zeros(n)), ("STATUS", np.zeros(n)), ("EVENT", np.zeros(n)))]
    h0 = fits.PrimaryHDU()
    h0.header["TARGNAME"] = "X"
    h0.header["PI_NAME"] = "P I"
    path = tmp_path / "CH_PR100018_TG000101_V0300_SCI_COR_Lightcurve-DEFAULT_V0300.fits"
    fits.HDUList([h0, fits.BinTableHDU.from_columns(cols)]).writeto(path)
    v = ch.read_drp_fits(path, meta={"file_key": "CH_PR100018_TG000101_V0300"})
    assert v.time[0] == pytest.approx(2139.0) and v.flux.size == n
    assert_credited(v.provenance(), ["CH_PR100018_TG000101_V0300"])


@pytest.mark.network
def test_live_public_listing_hr10():
    pytest.importorskip("dace_query")
    out = ch.list_visits("HR 10", cache_dir=Path("cache/cheops"))
    assert out["n_public"] >= 3 and all(v["status_published"] for v in out["visits"])

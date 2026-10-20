"""Everything that dims: the classification rules, the sweep (resumable, cached, polite) and contribution bundles."""

import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest

from exoplan import contrib as C
from exoplan import sweep as SW
from exoplan import variables as V
from exoplan.starsearch import CLASSIFY_FILES, CODE_FILES, SEARCH_FILES, classify_fingerprint, code_fingerprint, read_spoc, search_fingerprint

SECTOR = 99


# ---------- the rules, on synthetic cases ----------
def _dip(**kw):
    d = {"t_start": 10.0, "t_end": 10.15, "flags": [], "passed": True, "depth_ppm": 2000.0, "planet_fraction": 1.0,
         "shares": {"potential_planet": 1.0}, "n_transits": 3, "period_days": 3.2}
    d.update(kw)
    return d


EVENTS = {"momentum_dumps": [20.0], "scattered_light": [[30.0, 30.5]], "pointing": [[40.0, 40.2]], "gaps": [[13.0, 14.2]], "span": [0.0, 27.0]}


def test_a_clean_periodic_dip_is_a_planet_candidate_never_high():
    v = V.classify_dip(_dip(), EVENTS)
    assert (v["class"], v["confidence"]) == ("planet_candidate", "medium")
    assert {c["rule"] for c in v["cues"]} == {"passed", "panel_planet", "periodic"}
    assert V.classify_dip(_dip(n_transits=1, period_days=None))["confidence"] == "low"     # a single dip
    assert V.classify_dip(_dip(flags=["density_mismatch"]))["confidence"] == "low"
    assert all(V.classify_dip(_dip(**k))["confidence"] != "high" for k in ({}, {"n_transits": 9}, {"depth_ppm": 100.0}))


@pytest.mark.parametrize("kw, cls, conf, rule", [
    ({"flags": ["odd_even_mismatch"], "passed": False}, "eclipsing_binary", "high", "odd_even_mismatch"),
    ({"flags": ["secondary_eclipse"], "passed": False}, "eclipsing_binary", "high", "secondary_eclipse"),
    ({"depth_ppm": 45_000.0}, "eclipsing_binary", "medium", "deep"),
    ({"flags": ["v_shape"], "depth_ppm": 8000.0}, "eclipsing_binary", "medium", "v_shape_deep"),
    ({"shares": {"eclipsing_binary": 0.6, "potential_planet": 0.4}}, "eclipsing_binary", "low", "panel_eb"),
    ({"flags": ["edge_event"]}, "systematic", "medium", "edge_event"),
    ({"t_start": 19.95, "t_end": 20.02}, "systematic", "medium", "momentum_dump"),
    ({"t_start": 30.55, "t_end": 30.6}, "systematic", "medium", "scattered_light"),
    ({"t_start": 40.25, "t_end": 40.3}, "systematic", "medium", "pointing"),
    ({"t_start": 14.25, "t_end": 14.4}, "systematic", "medium", "data_gap"),
    ({"t_start": 19.95, "t_end": 20.02, "flags": ["edge_event"]}, "systematic", "high", "edge_event"),
    ({"shares": {"instrumental": 1.0}}, "systematic", "low", "panel_instrumental"),
    ({"shares": {"stellar_variability": 0.5, "potential_planet": 0.5}}, "variable", "low", "panel_variability"),
])
def test_each_rule_on_a_synthetic_dip(kw, cls, conf, rule):
    v = V.classify_dip(_dip(**kw), EVENTS)
    assert (v["class"], v["confidence"]) == (cls, conf), v
    assert v["cues"][0]["rule"] == rule and all(c["text"] for c in v["cues"])


def test_order_systematic_before_binary_and_shallow_v_is_not_a_binary():
    # A binary cue on an instrumental cue: the instrument wins (first match), as documented.
    assert V.classify_dip(_dip(flags=["odd_even_mismatch", "edge_event"]), EVENTS)["class"] == "systematic"
    assert V.classify_dip(_dip(flags=["v_shape"], depth_ppm=900.0))["class"] == "planet_candidate"


def test_a_dip_as_long_as_a_quarter_of_the_variability_period_is_a_trough():
    star = {"period_days": 0.5}
    assert V.classify_dip(_dip(t_start=10.0, t_end=10.13), None, star)["class"] == "variable"      # 0.26 of P
    assert V.classify_dip(_dip(t_start=10.0, t_end=10.1), None, star)["class"] == "planet_candidate"  # 0.2 of P


def test_unclassified_says_why():
    v = V.classify_dip(_dip(flags=["low_snr"], passed=False, planet_fraction=0.3))
    assert v["class"] == "unclassified" and v["confidence"] == "n/a"
    assert "low_snr" in v["why"] and "30%" in v["why"]
    assert "off_ephemeris" in V.classify_dip(_dip(flags=["off_ephemeris"]))["why"]


def test_panel_shares_weigh_labels_and_reasons():
    clfs = [{"reviewer_id": "a", "label": "potential_planet", "reason": None},
            {"reviewer_id": "b", "label": "noise", "reason": "eclipsing_binary"},
            {"reviewer_id": "b", "label": "noise", "reason": "instrumental"},  # a later one replaces the earlier
            {"reviewer_id": "c", "label": "noise", "reason": None}]
    s = V.panel_shares(clfs, {"a": 2.0, "b": 1.0, "c": 1.0})
    assert s == {"instrumental": 0.25, "noise": 0.25, "potential_planet": 0.5}


def _flare_lc(seed=1, amp=5e-3):
    rng = np.random.default_rng(seed)
    t = np.arange(0, 27, 2 / 1440)
    f = 1 + rng.normal(0, 5e-4, t.size)
    m = t >= 10
    f[m] += amp * np.exp(-(t[m] - 10) / (20 / 1440))
    return t, f


def test_a_flare_is_found_and_classified_and_noise_gives_none():
    t, f = _flare_lc()
    fl = V.find_flares(t, f)
    assert len(fl) == 1 and abs(fl[0]["t_peak"] - 10.0) < 0.01 and fl[0]["rise_days"] < fl[0]["decay_days"]
    v = V.classify_flare(fl[0])
    assert v["class"] == "flare" and v["confidence"] == "high" and v["cues"][1]["rule"] == "fast_rise"
    rng = np.random.default_rng(7)
    assert V.find_flares(t, 1 + rng.normal(0, 5e-4, t.size)) == []
    # A dip is not a brightening; nor is a coherent pulsation, whose scatter raises the bar.
    assert V.find_flares(t, 2 - f) == []
    assert V.find_flares(t, 1 + 3e-3 * np.sin(2 * np.pi * t / (25 / 1440)) + rng.normal(0, 3e-4, t.size)) == []
    # On a momentum dump it is systematic.
    assert V.classify_flare(fl[0], {"momentum_dumps": [10.02]})["class"] == "systematic"


def test_equal_rise_and_decay_is_not_a_fast_rise_despite_float_noise():
    # Found by ingest's rule re-check on the real sweep: 10 min each way, but rise < decay in floating point.
    f = {"t_start": 1336.86, "t_end": 1336.874, "n_points": 11, "peak_sigma": 6.01, "amplitude_ppm": 62563.0,
         "rise_days": 1336.867 - 1336.86, "decay_days": 1336.874 - 1336.867}
    assert abs(f["rise_days"] - f["decay_days"]) < 1e-6
    v = V.classify_flare(f)
    assert v["confidence"] == "low" and [c["rule"] for c in v["cues"]] == ["brightening"]
    assert V.classify_flare({**f, "rise_days": round(f["rise_days"] * 1440, 1) / 1440, "decay_days": round(f["decay_days"] * 1440, 1) / 1440})["confidence"] == "low"


def test_reclassify_reuses_the_stored_runs_and_keeps_the_search_code(swept):
    kw = swept["kw"]
    before = SW.read_record(kw["out_dir"] / f"sector_{SECTOR:04d}.json.gz")
    searched_by = {s["tic"]: s["search_code"] for s in before["stars"]}
    n = SW.reclassify_sweep("configs/sweep.toml", SECTOR, limit=3, out_dir=kw["out_dir"], cache_root=kw["cache_root"],
                            rule_changes=["test change"], log=lambda *a: None)
    assert n == 3
    rec = SW.read_record(kw["out_dir"] / f"sector_{SECTOR:04d}.json.gz")
    for s in rec["stars"]:
        assert s["search_code"] == searched_by[s["tic"]] == search_fingerprint()   # the code that made the dips stays named
        assert s["classify_code"] == classify_fingerprint() and "code" not in s
        last = s["reclassifications"][-1]
        assert last["rule_changes"] == ["test change"] and last["reclassified_from"] == before["stars"][0]["classify_code"]
    assert swept["mast"].fetched == [] and swept["mast"].queries == 0   # nothing downloaded, no reviewer asked


def test_a_record_from_one_code_gets_both_codes_from_named_commits(swept, monkeypatch):
    kw = swept["kw"]
    p = SW.record_path(kw["cache_root"], SECTOR, SW.read_record(kw["out_dir"] / f"sector_{SECTOR:04d}.json.gz")["stars"][0]["tic"])
    old = json.loads(p.read_text())
    old["code"] = "f" * 64
    old.pop("search_code"), old.pop("classify_code")
    p.write_text(json.dumps(old))
    monkeypatch.setattr(SW, "fingerprints_at", lambda rev: (f"search@{rev}", f"classify@{rev}"))
    SW.reclassify_sweep("configs/sweep.toml", SECTOR, limit=3, out_dir=kw["out_dir"], cache_root=kw["cache_root"],
                        search_commit="aaa", classified_commit="bbb", log=lambda *a: None)
    s = json.loads(p.read_text())
    assert s["search_code"] == "search@aaa" and s["search_commit"] == "aaa" and s["search_time_classify_code"] == "classify@aaa"
    assert s["reclassifications"][-1]["reclassified_from"] == "classify@bbb" and s["classify_code"] == classify_fingerprint()


def test_resume_searches_again_a_record_made_with_other_code_or_config(swept):
    kw = swept["kw"]
    p = SW.record_path(kw["cache_root"], SECTOR, SW.read_record(kw["out_dir"] / f"sector_{SECTOR:04d}.json.gz")["stars"][0]["tic"])
    rec = json.loads(p.read_text())
    rec["config_sha256"] = "0" * 64
    p.write_text(json.dumps(rec))
    res = SW.run_sweep("configs/sweep.toml", SECTOR, limit=3, **kw)
    assert (res.skipped, res.stale, res.ran) == (2, 1, 1)


def test_density_mismatch_at_a_short_period_is_a_binary():
    v = V.classify_dip(_dip(flags=["density_mismatch"], period_days=0.819))
    assert (v["class"], v["confidence"]) == ("eclipsing_binary", "medium") and v["cues"][0]["rule"] == "density_short_period"
    assert V.classify_dip(_dip(flags=["density_mismatch"], period_days=3.2))["class"] == "planet_candidate"


def test_each_class_has_its_own_null():
    t, f = _flare_lc()
    # A real flare turned upside down is a dip, so on the flipped flux with the real dips masked the flare rule finds nothing.
    assert V.flare_null(t, f, [])["counts"] == {}
    rng = np.random.default_rng(5)
    g = 1 + rng.normal(0, 5e-4, t.size)
    g[(t > 5) & (t < 5.01)] -= 6e-3   # a sharp drop: a flare-shaped event downward
    g[(t >= 5.01) & (t < 5.03)] -= 3e-3
    null = V.flare_null(t, g, [])
    assert null["events"] >= 1
    assert V.flare_null(t, g, [(4.9, 5.1)])["events"] == 0          # the real dips are masked
    # Block shuffling destroys a 2.3-day period; the periodogram of a flipped copy would not have.
    var = 1 + rng.normal(0, 5e-4, t.size) + 1e-3 * np.sin(2 * np.pi * t / 2.3)
    assert V.classify_variability(V.variability(t, var))["class"] == "variable"
    assert V.variability_null(t, var, [], seed=1)["variable"] == 0
    assert V.variability(t, 2 - var)["period_days"] == V.variability(t, var)["period_days"]
    plain = V.block_shuffled(t, var, seed=1, demean=False)
    assert sorted(plain) == sorted(var) and not np.array_equal(plain, var)
    # Demeaned blocks: no level steps at the joins, so a slow variable's null does not regrow a square wave.
    slow = 1 + 3e-3 * np.sin(2 * np.pi * t / 6.0) + rng.normal(0, 3e-4, t.size)
    idx = np.floor((t - t.min()) / 0.5).astype(int)
    d = V.block_shuffled(t, slow, seed=2)
    assert max(abs(np.median(d[idx == k]) - np.median(slow)) for k in np.unique(idx)) < 2e-4
    assert V.variability_null(t, slow, [], seed=2)["variable"] == 0


def test_variability_finds_the_period_and_the_rule_needs_amplitude():
    rng = np.random.default_rng(3)
    t = np.arange(0, 27, 2 / 1440)
    var = V.variability(t, 1 + rng.normal(0, 5e-4, t.size) + 1e-3 * np.sin(2 * np.pi * t / 2.3))
    assert abs(var["period_days"] - 2.3) < 0.02 and 900 < var["amplitude_ppm"] < 1100
    v = V.classify_variability(var)
    assert v["class"] == "variable" and v["confidence"] in ("high", "medium")
    noise = V.variability(t, 1 + rng.normal(0, 5e-4, t.size))
    assert V.classify_variability(noise) is None
    # A Baluev FAP alone is not enough: a tiny amplitude with a tiny FAP fails the amplitude rule.
    assert V.classify_variability({**var, "amplitude_ratio": 1.0}) is None
    # Variability at an eclipsing binary's period (or half of it) is the binary's own light curve.
    assert V.classify_variability(var, [4.6])["class"] == "eclipsing_binary"
    # Masked windows are left out.
    assert V.variability(t, np.ones(t.size), [(0, 27)]) is None


def test_quality_events_from_flags():
    t = np.arange(0, 10, 2 / 1440)
    q = np.zeros(t.size, int)
    q[(t > 2) & (t < 2.01)] = 32
    q[(t > 5) & (t < 5.5)] = 2048
    q[(t > 7) & (t < 7.1)] = 128
    good = (q == 0) & ~((t > 8) & (t < 9))
    ev = V.quality_events(t, q, good)
    assert len(ev["momentum_dumps"]) == 1 and abs(ev["momentum_dumps"][0] - 2.0) < 0.02
    assert len(ev["scattered_light"]) == 1 and len(ev["pointing"]) == 1
    assert len(ev["gaps"]) == 1 and abs(ev["gaps"][0][0] - 8.0) < 0.01


# ---------- the sweep, on synthetic SPOC files ----------
def _write_spoc(path: Path, tic: int, seed: int, kind: str):
    from astropy.io import fits

    rng = np.random.default_rng(seed)
    t = np.arange(1325.0, 1339.0, 2 / 1440)
    f = 1 + rng.normal(0, 4e-4, t.size)
    if kind == "planet":
        for k in range(4):
            c = 1326.5 + 3.3 * k
            f -= 3000e-6 * (np.abs(t - c) < 0.08)
    if kind == "flare":
        m = t >= 1331.0
        f[m] += 6e-3 * np.exp(-(t[m] - 1331.0) / (20 / 1440))
    q = np.zeros(t.size, np.int32)
    q[np.abs(t - 1333.0) < 0.003] = 32
    hdr = fits.Header({"TEFF": 5700.0, "LOGG": 4.4, "RADIUS": 1.0, "TESSMAG": 9.0, "RA_OBJ": 80.0 + seed, "DEC_OBJ": -60.0})
    cols = [fits.Column(name="TIME", format="D", array=t), fits.Column(name="PDCSAP_FLUX", format="E", array=f * 1e4),
            fits.Column(name="PDCSAP_FLUX_ERR", format="E", array=np.full(t.size, 4.0)), fits.Column(name="QUALITY", format="J", array=q)]
    fits.HDUList([fits.PrimaryHDU(header=hdr), fits.BinTableHDU.from_columns(cols)]).writeto(path)


TARGETS = [{"tic": 1000 + i, "ra": 80.0 + i, "dec": -60.0, "uri": f"mast:TESS/product/fake-s0099-{1000 + i}_lc.fits", "obs_id": str(i)} for i in range(4)]
KINDS = {1000: "planet", 1001: "flare", 1002: "quiet", 1003: "planet"}


class FakeMast:
    def __init__(self, fail=()):
        self.queries = 0
        self.fetched = []
        self.fail = set(fail)

    def query(self, sector):
        self.queries += 1
        return [dict(t) for t in TARGETS]

    def fetch(self, uri, local):
        tic = int(uri.rsplit("-", 1)[1].split("_")[0])
        if tic in self.fail:
            raise ConnectionError("connection reset (test)")
        self.fetched.append(tic)
        _write_spoc(Path(local), tic, tic - 1000, KINDS[tic])


@pytest.fixture(scope="module")
def _swept_once(tmp_path_factory):
    """Three targets of a synthetic sector swept once with the Probes; the fourth left for a resume."""
    base = tmp_path_factory.mktemp("swept")
    mast = FakeMast()
    kw = dict(out_dir=base / "sweep", cache_root=base / "cache", min_interval=0.0, control=True, query=mast.query,
              fetch=mast.fetch, toi_path=None, log=lambda *a: None)
    res = SW.run_sweep("configs/sweep.toml", SECTOR, limit=3, **kw)
    return base, res, mast


@pytest.fixture
def swept(_swept_once, tmp_path):
    """A private copy of the swept sector (its record, catalogue and cache), with a fresh fake archive."""
    base, res, first = _swept_once
    for d in ("sweep", "cache"):
        shutil.copytree(base / d, tmp_path / d)
    mast = FakeMast()
    kw = dict(out_dir=tmp_path / "sweep", cache_root=tmp_path / "cache", min_interval=0.0, control=True, query=mast.query,
              fetch=mast.fetch, toi_path=None, log=lambda *a: None)
    return {"res": res, "mast": mast, "first": first, "kw": kw, "tmp": tmp_path}


def test_sweep_records_every_star_and_builds_the_catalogue(swept):
    res, tmp = swept["res"], swept["tmp"]
    assert (res.done, res.ran, res.skipped) == (3, 3, 0)
    rec = SW.read_record(tmp / "sweep" / f"sector_{SECTOR:04d}.json.gz")
    assert rec["format"] == SW.FORMAT and rec["slice"] == 3 and rec["targets_in_sector"] == 4
    assert rec["status_counts"]["searched"] == 3
    assert rec["search_code"] == search_fingerprint() and rec["classify_code"] == classify_fingerprint()
    order = [s["tic"] for s in rec["stars"]]
    assert order == sorted([t["tic"] for t in TARGETS], key=lambda x: SW.sweep_key(SECTOR, x))[:3]   # the fixed sweep order
    for s in rec["stars"]:
        assert len(s["file_sha256"]) == 64 and s["n_points"] > 1000 and s["counts"] and "rejected" in s and s["reviewers"]
        assert len(s["events"]["momentum_dumps"]) == 1
    cat = json.loads((tmp / "sweep" / "catalogue.json").read_text())
    assert cat["counts"]["star_sectors_searched"] == 3 and cat["counts"]["entries"] == len(cat["entries"])
    assert cat["counts"]["dips_reviewed"] == sum(s["n_dips"] for s in rec["stars"])
    assert sum(cat["counts"]["by_class"].values()) == cat["counts"]["entries"]
    assert all(e["credit"] == [{"name": "exoplan", "source": f"sector_{SECTOR:04d}.json.gz"}] for e in cat["entries"])
    assert {c["id"] for c in cat["classes"]} == set(V.CLASS_IDS)
    nul = cat["counts"]["null"]
    assert nul["searches"] == 3 and set(nul["by_class"]) == set(V.CLASS_IDS) - {"unclassified"}
    for s in rec["stars"]:
        assert set(s["null"]) == {"dip_inverted", "flare_downward", "flare_shape", "variability_shuffled"}
        assert "control" not in s
    planets = [e for e in cat["entries"] if e["tic"] in (1000, 1003) and e["kind"] == "dip"]
    flares = [e for e in cat["entries"] if e["tic"] == 1001 and e["class"] == "flare"]
    if 1001 in order:
        assert len(flares) == 1 and flares[0]["marks"] == [] and "dips only" in flares[0]["note"]
    assert any(e["class"] == "planet_candidate" for e in planets)
    for e in planets:
        assert e["weights"] and e["marks"] and e["panel"]  # every entry keeps its marks and weights
    text = json.dumps(cat).lower()
    assert "confirmed planet" not in text.replace("not a confirmed planet", "") and "superintelligence" not in text


def test_sweep_resumes_without_repeating_work(swept):
    mast, kw = swept["mast"], swept["kw"]
    assert swept["first"].queries == 1 and len(swept["first"].fetched) == 3
    res = SW.run_sweep("configs/sweep.toml", SECTOR, limit=4, **kw)
    assert (res.skipped, res.ran, res.done) == (3, 1, 4)
    assert mast.queries == 0                       # the target list is cached
    assert len(mast.fetched) == 1                  # only the new star is downloaded; the others come from the cache
    again = SW.run_sweep("configs/sweep.toml", SECTOR, limit=4, **kw)
    assert (again.ran, again.skipped) == (0, 4)


def test_a_failed_download_is_recorded_then_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(SW.time, "sleep", lambda s: None)
    mast = FakeMast(fail={1002})
    kw = dict(out_dir=tmp_path / "sweep", cache_root=tmp_path / "cache", min_interval=0.0, control=False, query=mast.query,
              fetch=mast.fetch, toi_path=None, log=lambda *a: None)
    first = [t["tic"] for t in sorted(TARGETS, key=lambda t: SW.sweep_key(SECTOR, t["tic"]))]
    limit = first.index(1002) + 1
    res = SW.run_sweep("configs/sweep.toml", SECTOR, limit=limit, **kw)
    assert any("1002" in e and "download failed" in e for e in res.errors)
    rec = SW.read_record(tmp_path / "sweep" / f"sector_{SECTOR:04d}.json.gz")
    assert [s["status"] for s in rec["stars"] if s["tic"] == 1002] == ["error"]
    mast.fail.clear()
    res = SW.run_sweep("configs/sweep.toml", SECTOR, limit=limit, **kw)
    assert res.ran == 1 and res.errors == []
    cat = json.loads((tmp_path / "sweep" / "catalogue.json").read_text())
    assert cat["counts"]["not_searched"]["error"] == 0 and cat["counts"]["star_sectors_searched"] == limit


def test_time_budget_stops_cleanly_and_leaves_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(SW.time, "sleep", lambda s: None)
    mast = FakeMast()
    res = SW.run_sweep("configs/sweep.toml", SECTOR, limit=4, out_dir=tmp_path / "sweep", cache_root=tmp_path / "cache", min_interval=0.0,
                       control=False, query=mast.query, fetch=mast.fetch, toi_path=None, time_budget_s=0.0, log=lambda *a: None)
    assert res.stopped == "time budget reached" and res.ran == 0
    rec = SW.read_record(tmp_path / "sweep" / f"sector_{SECTOR:04d}.json.gz")
    assert rec["status_counts"]["pending"] == 4


def test_polite_backs_off_on_rate_limits_and_gives_up_on_other_errors():
    slept, calls = [], []
    th = SW.Throttle(min_interval=1.0, clock=iter([0.0, 0.0, 0.2, 1.2, 1.3, 2.5, 2.6]).__next__, sleep=slept.append)

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise OSError("HTTP Error 429: Too Many Requests")
        return "ok"

    backoff = []
    assert SW.polite(flaky, throttle=th, sleep=backoff.append) == "ok"
    assert len(calls) == 3 and len(backoff) == 2 and 2.0 <= backoff[0] <= 2.5 and 4.0 <= backoff[1] <= 5.0
    assert slept and all(s > 0 for s in slept)   # the throttle kept requests apart
    with pytest.raises(ValueError):
        SW.polite(lambda: (_ for _ in ()).throw(ValueError("bad file")), throttle=SW.Throttle(0.0), sleep=lambda s: None)


def test_read_spoc_matches_the_loader_rule(tmp_path):
    p = tmp_path / "x.fits"
    _write_spoc(p, 5, 5, "quiet")
    lc, ev, star = read_spoc(p, 5, SECTOR)
    assert abs(np.median(lc.flux) - 1.0) < 1e-6 and len(lc) < 14 * 720 and lc.provenance["file_sha256"]
    assert star["teff"] == 5700.0 and star["ra"] == 85.0 and ev["momentum_dumps"]


def test_code_fingerprint_covers_the_result_making_code():
    assert {"variables.py", "starsearch.py", "pipeline.py", "vet.py", "reviewers/claude.py"} <= set(CODE_FILES)
    assert "sweep.py" not in CODE_FILES and "contrib.py" not in CODE_FILES   # orchestration does not change results
    assert CLASSIFY_FILES == ["variables.py"] and set(SEARCH_FILES) | set(CLASSIFY_FILES) == set(CODE_FILES)
    assert len(code_fingerprint()) == 64 and search_fingerprint() != classify_fingerprint()


# ---------- contribution bundles ----------
@pytest.fixture
def bundle(swept):
    tmp = swept["tmp"]
    return C.make_bundle(tmp / "sweep" / f"sector_{SECTOR:04d}.json.gz", tmp / "bundle", contributor="Ada L.", now="2026-10-20T00:00:00+00:00")


def _ingest(b, swept, sweep_dir, **kw):
    """Ingest with the fake archive standing in for MAST (light curves fetched again and searched again)."""
    return C.ingest_bundle(b, sweep_dir=sweep_dir, fetch=swept["mast"].fetch, cache_root=swept["kw"]["cache_root"], **kw)


def _reseal(bdir: Path, mutate_results=None, mutate_manifest=None):
    """Change a bundle and seal it again properly (anyone can), so only the checks against the world can catch it."""
    if mutate_results:
        r = json.loads((bdir / "results.json").read_text())
        mutate_results(r)
        (bdir / "results.json").write_text(json.dumps(r))
    man = json.loads((bdir / "manifest.json").read_text())
    man["files"] = {f: C.sha256_bytes((bdir / f).read_bytes()) for f in C.FILES}
    if mutate_manifest:
        mutate_manifest(man)
    man["bundle_id"] = "c-" + C.sha256_bytes(C._canonical({"files": man["files"], "contributor": man["contributor"]["name"]}))[:16]
    man.pop("content_sha256")
    man["content_sha256"] = C.sha256_bytes(C._canonical(man))
    (bdir / "manifest.json").write_text(json.dumps(man))


def test_a_valid_bundle_is_fetched_searched_again_and_credited(bundle, swept, tmp_path):
    man = json.loads((bundle / "manifest.json").read_text())
    assert sorted(p.name for p in bundle.iterdir()) == ["config.toml", "manifest.json", "results.json"]
    assert (man["search_code"], man["classify_code"]) == (search_fingerprint(), classify_fingerprint())
    assert all(len(x["sha256"]) == 64 for x in man["lightcurves"]) and man["statement"]["by"] == "Ada L."
    assert "not a signature" in man["seal"] and "signed" not in json.dumps(man)
    empty = tmp_path / "empty"
    empty.mkdir()
    out = _ingest(bundle, swept, empty, attested_by="ada-l")
    assert out["verified"]["searched_again"] and len(out["verified"]["lightcurves_refetched"]) == 3
    assert set(out["verified"]["searched_again"]) == {s["tic"] for s in json.loads((bundle / "results.json").read_text())["stars"]}
    ing = json.loads((empty / "contributions" / man["bundle_id"] / "ingest.json").read_text())
    assert ing["attested_by"] == "ada-l" and ing["new_star_sectors"] == 3
    cat = json.loads((empty / "catalogue.json").read_text())
    assert {c["name"] for e in cat["entries"] for c in e["credit"]} == {"Ada L."}
    assert all(c.get("attested_by") == "ada-l" for e in cat["entries"] for c in e["credit"])
    with pytest.raises(C.BundleRefused, match="already ingested"):
        _ingest(bundle, swept, empty)


def test_resubmission_under_other_names_is_refused_and_counts_do_not_move(swept):
    """The reviewer's attack: the same sector record re-bundled under three names. Each is refused; counters,
    nulls and credit stay as they were."""
    sweep_dir = swept["kw"]["out_dir"]
    before = json.loads((sweep_dir / "catalogue.json").read_text())["counts"]
    rec = sweep_dir / f"sector_{SECTOR:04d}.json.gz"
    for name in ("Eve", "Frank", "Grace"):
        b = C.make_bundle(rec, swept["tmp"] / f"b-{name}", contributor=name)
        with pytest.raises(C.BundleRefused, match="re-submission"):
            _ingest(b, swept, sweep_dir)
    after = json.loads((sweep_dir / "catalogue.json").read_text())["counts"]
    assert after == before


def test_a_hand_placed_or_changed_contribution_is_left_out_and_ci_says_so(bundle, swept, tmp_path):
    """The reviewer's attack: a forged bundle copied into contributions/ by hand, without ingest. It is not read;
    nor is an ingested folder changed afterwards; check-sweep (a CI step) reports both."""
    sweep_dir = swept["kw"]["out_dir"]
    before = json.loads((sweep_dir / "catalogue.json").read_text())["counts"]
    assert SW.check_catalogue(sweep_dir) == []
    b = C.make_bundle(sweep_dir / f"sector_{SECTOR:04d}.json.gz", tmp_path / "handy", contributor="Handy")
    man = json.loads((b / "manifest.json").read_text())
    shutil.copytree(b, sweep_dir / "contributions" / man["bundle_id"])
    SW.build_catalogue(sweep_dir)
    cat = json.loads((sweep_dir / "catalogue.json").read_text())
    assert cat["counts"] == before and "Handy" not in {x["name"] for x in cat["contributors"]}
    assert cat["rejected_contributions"][0]["why"].startswith("holds")
    problems = SW.check_catalogue(sweep_dir)
    assert any("ingest" in p or "holds" in p for p in problems)
    from exoplan.cli import main

    assert main(["check-sweep", "--sweep-dir", str(sweep_dir)]) == 1
    # An ingested folder edited afterwards (ingest.json and all) is left out too.
    shutil.rmtree(sweep_dir / "contributions")
    empty = tmp_path / "e"
    empty.mkdir()
    _ingest(bundle, swept, empty)
    folder = empty / "contributions" / json.loads((bundle / "manifest.json").read_text())["bundle_id"]
    assert SW.check_catalogue(empty) == []
    r = json.loads((folder / "results.json").read_text())
    r["stars"][0]["n_dips"] += 1
    (folder / "results.json").write_text(json.dumps(r))
    SW.build_catalogue(empty)
    assert json.loads((empty / "catalogue.json").read_text())["counts"]["searches"] == 0
    assert any("differs from the manifest" in p for p in SW.check_catalogue(empty))


def test_one_search_counts_per_star_sector_the_latest(swept):
    """The reviewer's case: the same stars searched again with newer code. The later search counts; the earlier
    stays as provenance only, and nothing is counted twice."""
    sweep_dir = swept["kw"]["out_dir"]
    rec = SW.read_record(sweep_dir / f"sector_{SECTOR:04d}.json.gz")
    later = json.loads(json.dumps(rec))
    for s in later["stars"]:
        s["search_code"] = "1" * 64
        s["searched_at"] = "2099-01-01T00:00:00+00:00"
    later["contributor"] = "Later"
    (sweep_dir / f"sector_{SECTOR + 1:04d}.json").write_text(json.dumps(later))  # a second source of the same star-sectors
    SW.build_catalogue(sweep_dir)
    cat = json.loads((sweep_dir / "catalogue.json").read_text())
    c = cat["counts"]
    assert c["searches"] == c["star_sectors_searched"] == 3 and c["superseded_searches"] == 3
    assert {x["name"] for e in cat["entries"] for x in e["credit"]} == {"Later"}
    assert len({e["id"] for e in cat["entries"]}) == len(cat["entries"]) and not any(e["id"].endswith("+") for e in cat["entries"])
    assert all(r["earlier_searches"][0]["name"] == "exoplan" for r in cat["coverage"] if r["status"] == "searched")
    assert next(x for x in cat["contributors"] if x["name"] == "exoplan")["superseded"] == 3


def test_paired_statistics_do_not_let_two_clustered_stars_carry_a_class():
    # 50 star-sectors; two stars give 12 dips each, the null gives a few scattered ones: as Poisson events that
    # would look like an excess of +20; star by star it is not distinguishable from noise.
    real = [12, 12] + [0] * 48
    null = [0, 0, 1, 1, 1, 1] + [0] * 44
    v = SW.paired_versus_null(real, null)
    assert v["excess"] == 20 and v["lo"] <= 0 and v["significant"] is False
    assert (v["stars_real"], v["stars_null"]) == (2, 4) and v["mcnemar_p"] > 0.05
    # Many stars each a little above their null: a real excess.
    v = SW.paired_versus_null([1] * 30 + [0] * 20, [0] * 45 + [1] * 5)
    assert v["significant"] is True and v["lo"] > 0 and v["mcnemar_p"] < 0.05


def test_each_kind_is_compared_with_the_same_kind(swept):
    cat = json.loads((swept["kw"]["out_dir"] / "catalogue.json").read_text())
    comps = cat["counts"]["null"]["comparisons"]
    assert {(x["class"], x["kind"]) for x in comps} == {(c, k) for c, k, _, _ in SW.COMPARISONS}
    eb = next(x for x in comps if x["class"] == "eclipsing_binary")
    assert eb["kind"] == "dip" and eb["real"] == sum(1 for e in cat["entries"] if e["class"] == "eclipsing_binary" and e["kind"] == "dip")
    assert eb["star_sectors"] == cat["counts"]["null"]["searches"] == 3


def test_ingest_always_searches_planet_candidate_stars_and_draws_the_rest_from_its_own_nonce():
    stars = [{"tic": i, "sector": 1, "status": "searched", "entries": [{"class": "planet_candidate"}] if i == 7 else
              [{"class": "eclipsing_binary"}] if i == 9 else []} for i in range(100)]
    rec = {"stars": stars}
    forced, rand = C.select_for_search(rec, exceeding=set(), nonce="a")
    assert [s["tic"] for s in forced] == [7] and len(rand) == 5 and 7 not in {s["tic"] for s in rand}   # max(3, 5% of 100)
    forced, _ = C.select_for_search(rec, exceeding={"eclipsing_binary"}, nonce="a")
    assert {s["tic"] for s in forced} == {7, 9}
    picks = {tuple(s["tic"] for s in C.select_for_search(rec, exceeding=set(), nonce=n)[1]) for n in ("a", "b", "c")}
    assert len(picks) == 3                                                    # the nonce, not the bundle, decides
    assert len(C.select_for_search({"stars": stars[:10]}, exceeding=set(), nonce="a")[1]) == 3


def test_renaming_a_forged_bundle_does_not_dodge_the_check(bundle, swept, tmp_path):
    """The reviewer's attack: reseal a forged bundle under new names until the forged star is not sampled. A star
    with a planet candidate is always searched again, whatever the name."""
    def forge(r):
        for s in r["stars"]:
            for e in s.get("entries") or []:
                if e["kind"] == "dip" and e["class"] != "planet_candidate":
                    e.update(passed=True, planet_fraction=1.0, flags=[], shares={"potential_planet": 1.0}, n_transits=3, period_days=3.21,
                             depth_ppm=900.0, t_start=1327.9, t_end=1328.05, cues=[], why=None, **{"class": "planet_candidate", "confidence": "medium"})
                    return
        raise AssertionError("no dip to forge")
    _reseal(bundle, forge)
    for name in ("Mallory", "Mallory 2", "Mallory 3"):
        _reseal(bundle, mutate_manifest=lambda m, n=name: m.update(contributor={"name": n}, statement={**m["statement"], "by": n}))
        empty = tmp_path / name.replace(" ", "")
        empty.mkdir()
        with pytest.raises(C.BundleRefused, match="a fresh search does not reproduce"):
            _ingest(bundle, swept, empty, verify_lightcurves=0)   # no random sample at all: the candidate's star is still searched


def test_a_bundle_with_one_new_star_credits_only_that_star(swept):
    kw = swept["kw"]
    mine = swept["tmp"] / "mine"
    SW.run_sweep("configs/sweep.toml", SECTOR, limit=4, **{**kw, "out_dir": mine, "contributor": "Ada L."})
    b = C.make_bundle(mine / f"sector_{SECTOR:04d}.json.gz", swept["tmp"] / "b4", contributor="Ada L.")
    out = _ingest(b, swept, kw["out_dir"], verify_lightcurves=4)
    assert out["new_star_sectors"] == 1
    cat = json.loads((kw["out_dir"] / "catalogue.json").read_text())
    assert cat["counts"]["searches"] == 4 and cat["counts"]["duplicate_searches"] == 3
    ada = next(x for x in cat["contributors"] if x["name"] == "Ada L.")
    assert ada["star_sectors"] == 1 and ada["duplicates_not_credited"] == 3
    new_tic = next(s["tic"] for s in SW.read_record(mine / f"sector_{SECTOR:04d}.json.gz")["stars"]
                   if s["tic"] not in {r["tic"] for r in SW.read_record(kw["out_dir"] / f"sector_{SECTOR:04d}.json.gz")["stars"]})
    assert {c["name"] for e in cat["entries"] if e["tic"] == new_tic for c in e["credit"]} <= {"Ada L."}
    assert {c["name"] for e in cat["entries"] if e["tic"] != new_tic for c in e["credit"]} == {"exoplan"}


def test_a_forged_planet_candidate_with_consistent_inputs_is_caught_by_the_fresh_search(bundle, swept, tmp_path):
    """The reviewer's forgery: an entry's stored inputs edited so the rules give a planet candidate, then
    resealed. The rules re-check passes; searching the star again does not."""
    def forge(r):
        for s in r["stars"]:
            for e in s.get("entries") or []:
                if e["kind"] == "dip" and e["class"] != "planet_candidate":
                    e.update(passed=True, planet_fraction=1.0, flags=[], shares={"potential_planet": 1.0}, n_transits=3, period_days=3.21,
                             depth_ppm=900.0, t_start=1327.9, t_end=1328.05, cues=[], why=None, **{"class": "planet_candidate", "confidence": "medium"})
                    s["counts"]["planet_candidate"] = s["counts"].get("planet_candidate", 0) + 1
                    return
        raise AssertionError("no dip to forge")
    _reseal(bundle, forge)
    C.validate_bundle(bundle)          # sealed consistently and the rules agree with the forged inputs ...
    empty = tmp_path / "e"
    empty.mkdir()
    with pytest.raises(C.BundleRefused, match="a fresh search does not reproduce"):
        _ingest(bundle, swept, empty)  # ... but the star searched again does not give it
    assert not (empty / "contributions").exists()


def test_a_bundle_with_sentinels_needs_explicit_acceptance(bundle, swept, tmp_path):
    def add_sentinel(r):
        for s in r["stars"]:
            s["reviewers"] = s["reviewers"] + [{"id": "claude-volunteer", "kind": "claude_code", "weight": 0.5}]
    _reseal(bundle, add_sentinel, lambda m: m.update(reviewers=m["reviewers"] + [{"id": "claude-volunteer", "kind": "claude_code"}]))
    empty = tmp_path / "e"
    empty.mkdir()
    with pytest.raises(C.BundleRefused, match="accept-sentinels"):
        _ingest(bundle, swept, empty)
    out = _ingest(bundle, swept, empty, accept_sentinels=True)
    assert out["verified"]["dips_searched_again"] is False and out["verified"]["searched_again"] == []


def test_a_zipped_bundle_is_accepted_and_odd_zips_are_refused(bundle, tmp_path):
    z = tmp_path / "b.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in ("manifest.json", "results.json", "config.toml"):
            zf.write(bundle / f, f"bundle/{f}")
    assert C.validate_bundle(z)["manifest"]["contributor"]["name"] == "Ada L."
    for members in ([("../evil.py", "x")], [("..\\..\\results.json", "x")], [("/tmp/results.json", "x")],
                    [("a/results.json", "x"), ("b/results.json", "y")], [("a/b/results.json", "x")]):
        bad = tmp_path / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            for name, text in members:
                zf.writestr(name, text)
        with pytest.raises(C.BundleRefused, match="unexpected file"):
            C.validate_bundle(bad)


@pytest.mark.parametrize("damage, match", [
    (lambda b: (b / "results.json").write_text((b / "results.json").read_text().replace('"searched"', '"searched" ', 1)), "hash mismatch on results.json"),
    (lambda b: (b / "config.toml").write_text((b / "config.toml").read_text() + "\nextra = 1\n"), "hash mismatch on config.toml"),
    (lambda b: (b / "manifest.json").write_text((b / "manifest.json").read_text().replace("Ada L.", "Bob")), "manifest hash mismatch"),
    (lambda b: (b / "extra.txt").write_text("x"), "exactly manifest.json"),
    (lambda b: (b / "config.toml").unlink(), "exactly manifest.json"),
])
def test_tampering_is_refused(bundle, damage, match):
    damage(bundle)
    with pytest.raises(C.BundleRefused, match=match):
        C.validate_bundle(bundle)


def test_a_different_code_fingerprint_is_refused(bundle):
    with pytest.raises(C.BundleRefused, match="code fingerprint mismatch"):
        C.validate_bundle(bundle, codes=("0" * 64, classify_fingerprint()))
    with pytest.raises(C.BundleRefused, match="code fingerprint mismatch"):
        C.validate_bundle(bundle, codes=(search_fingerprint(), "0" * 64))


def test_an_edited_class_is_refused_even_when_resealed(bundle):
    def promote(r):
        for s in r["stars"]:
            for e in s.get("entries") or []:
                if e["class"] != "planet_candidate":
                    e["class"], e["confidence"] = "planet_candidate", "medium"
                    return
        raise AssertionError("no entry to edit")
    _reseal(bundle, promote)
    with pytest.raises(C.BundleRefused, match="the rules give|variability rule"):
        C.validate_bundle(bundle)


def test_a_bad_lightcurve_hash_is_refused_even_when_resealed(bundle):
    def drop(r):
        r["stars"][0]["file_sha256"] = "not-a-hash"
    _reseal(bundle, drop)
    with pytest.raises(C.BundleRefused, match="light-curve sha256"):
        C.validate_bundle(bundle)


def test_a_config_that_does_not_match_its_hash_is_refused(bundle):
    (bundle / "config.toml").write_text((bundle / "config.toml").read_text().replace("min_score = 0.5", "min_score = 0.4"))
    _reseal(bundle)
    with pytest.raises(C.BundleRefused, match="config hash mismatch"):
        C.validate_bundle(bundle)


@pytest.mark.parametrize("line", [
    '# api_key = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA"',
    '# key = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx-1234567890"',
    "# ANTHROPIC_API_KEY: sk_live_abcdefghijklmnopqrstuvwxyz0123",
    '# aws = "AKIAIOSFODNN7EXAMPLE"',
    '# secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
    'api_key = "anthropic-key-abcdefghijklmnopqrstuvwxyz0123456789"',
    "# token: abc123",
    'password = "hunter2"',
    "# github_token=ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "# Authorization: Bearer abcdefghijklmnop0123",
    "# x-api-key abcdefghijklmnopqrstu",
    '# google = "AIzaSyA1234567890abcdefghijklmnopqrstuv"',
    '# hf = "hf_abcdefghijklmnopqrstuvwxyz0123456789"',
    "# eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    "# wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
])
def test_every_kind_of_key_in_the_config_is_refused(swept, line):
    rec = SW.read_record(swept["kw"]["out_dir"] / f"sector_{SECTOR:04d}.json.gz")
    rec["config_text"] += "\n" + line + "\n"
    src = swept["tmp"] / "rec.json"
    src.write_text(json.dumps(rec))
    with pytest.raises(C.BundleRefused, match="credential"):
        C.make_bundle(src, swept["tmp"] / "kb", contributor="Key Tester")
    # And at ingest, when someone builds the bundle by hand.
    b = C.make_bundle(swept["kw"]["out_dir"] / f"sector_{SECTOR:04d}.json.gz", swept["tmp"] / "kb2", contributor="Key Tester")
    (b / "config.toml").write_text((b / "config.toml").read_text() + "\n" + line + "\n")
    _reseal(b)
    with pytest.raises(C.BundleRefused, match="credential|comments"):
        C.validate_bundle(b)


def test_a_bundled_config_has_no_comments_and_no_random_looking_values(swept):
    b = C.make_bundle(swept["kw"]["out_dir"] / f"sector_{SECTOR:04d}.json.gz", swept["tmp"] / "nc", contributor="Ada L.")
    text = (b / "config.toml").read_text()
    assert not C.has_comment(text) and "#" not in text
    from exoplan.config import load_config

    assert load_config(b / "config.toml").digest() == json.loads((b / "manifest.json").read_text())["config_sha256"]
    assert json.loads((b / "results.json").read_text())["config_text"] == text
    (b / "config.toml").write_text(text + "\n# just a note\n")
    _reseal(b)
    with pytest.raises(C.BundleRefused, match="comments"):
        C.validate_bundle(b)
    (b / "config.toml").write_text(text.replace('name = "sweep"', 'name = "Zq8vR2kLmN4pX7tB9wYc3HfJ6sDg1aEu"'))
    _reseal(b)
    with pytest.raises(C.BundleRefused, match="random-looking"):
        C.validate_bundle(b)
    assert C.has_comment('a = "x # y"') is False and C.has_comment("a = 1 # y") is True


def test_nothing_from_the_environment_goes_in_and_bad_names_are_refused(swept, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-THISISNOTAREALKEY0123456789")
    rec = swept["kw"]["out_dir"] / f"sector_{SECTOR:04d}.json.gz"
    b2 = C.make_bundle(rec, swept["tmp"] / "b2", contributor="Grace H.")
    assert "sk-ant" not in "".join(p.read_text() for p in b2.iterdir())
    for bad in ("", "x" * 61, "<script>", "see https://x.y", "me@example.org"):
        with pytest.raises(C.BundleRefused, match="contributor name"):
            C.make_bundle(rec, swept["tmp"] / "b3", contributor=bad)
    with pytest.raises(C.BundleRefused, match="attested-by"):
        C.ingest_bundle(b2, sweep_dir=swept["tmp"] / "x", attested_by="not a login!")


def test_a_lightcurve_that_hashes_differently_at_mast_is_refused(bundle, swept, tmp_path):
    def other(uri, local):
        _write_spoc(Path(local), 0, 42, "quiet")
    with pytest.raises(C.BundleRefused, match="hashes to"):
        C.check_at_mast(json.loads((bundle / "results.json").read_text()), 1, fetch=other, cache_root=swept["kw"]["cache_root"], seed="s")


def test_cli_ingest_refuses_with_a_message_and_verifies_by_default(bundle, capsys, tmp_path):
    from exoplan.cli import build_parser, main

    assert build_parser().parse_args(["ingest", "x"]).verify_lightcurves is None   # max(3, 5%) at random, plus every flagged star
    (bundle / "results.json").write_text("{}")
    assert main(["ingest", str(bundle), "--sweep-dir", str(tmp_path / "x")]) == 1
    assert "refused: hash mismatch on results.json" in capsys.readouterr().err


def test_contributing_doc_says_keys_stay_in_the_environment_and_bundles_are_sealed_not_signed():
    text = Path("CONTRIBUTING.md").read_text()
    for must in ("exoplan sweep", "exoplan bundle", "exoplan ingest", "ANTHROPIC_API_KEY", "environment", "configs/sweep_sentinels.toml",
                 "sealed", "not a signature", "--attested-by", "searched again"):
        assert must in text, must
    assert "Never paste" in text or "never paste" in text
    assert "signed" not in text.replace("not signed", "")


def test_sector_records_are_gzip_one_per_sector_and_byte_stable(swept, tmp_path):
    out = swept["kw"]["out_dir"]
    assert (out / f"sector_{SECTOR:04d}.json.gz").exists() and not (out / f"sector_{SECTOR:04d}.json").exists()
    rec = SW.read_record(out / f"sector_{SECTOR:04d}.json.gz")
    a, b = tmp_path / "a.json.gz", tmp_path / "b.json.gz"
    SW.write_record(a, rec)
    SW.write_record(b, rec)
    assert a.read_bytes() == b.read_bytes() and SW.read_record(a) == rec
    assert a.stat().st_size * 3 < len(json.dumps(rec))

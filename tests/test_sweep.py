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
from exoplan.starsearch import CODE_FILES, code_fingerprint, read_spoc

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
    kw = dict(out_dir=base / "sweep", cache_root=base / "cache", min_interval=0.0, control=False, query=mast.query,
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
    kw = dict(out_dir=tmp_path / "sweep", cache_root=tmp_path / "cache", min_interval=0.0, control=False, query=mast.query,
              fetch=mast.fetch, toi_path=None, log=lambda *a: None)
    return {"res": res, "mast": mast, "first": first, "kw": kw, "tmp": tmp_path}


def test_sweep_records_every_star_and_builds_the_catalogue(swept):
    res, tmp = swept["res"], swept["tmp"]
    assert (res.done, res.ran, res.skipped) == (3, 3, 0)
    rec = json.loads((tmp / "sweep" / f"sector_{SECTOR:04d}.json").read_text())
    assert rec["format"] == SW.FORMAT and rec["slice"] == 3 and rec["targets_in_sector"] == 4
    assert rec["status_counts"]["searched"] == 3 and rec["code"] == code_fingerprint()
    order = [s["tic"] for s in rec["stars"]]
    assert order == sorted([t["tic"] for t in TARGETS], key=lambda x: SW.sweep_key(SECTOR, x))[:3]   # the fixed sweep order
    for s in rec["stars"]:
        assert len(s["file_sha256"]) == 64 and s["n_points"] > 1000 and s["counts"] and "rejected" in s and s["reviewers"]
        assert len(s["events"]["momentum_dumps"]) == 1
    cat = json.loads((tmp / "sweep" / "catalogue.json").read_text())
    assert cat["counts"]["star_sectors_searched"] == 3 and cat["counts"]["entries"] == len(cat["entries"])
    assert cat["counts"]["dips_reviewed"] == sum(s["n_dips"] for s in rec["stars"])
    assert sum(cat["counts"]["by_class"].values()) == cat["counts"]["entries"]
    assert all(e["credit"] == [{"name": "exoplan", "source": f"sector_{SECTOR:04d}.json"}] for e in cat["entries"])
    assert {c["id"] for c in cat["classes"]} == set(V.CLASS_IDS)
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
    rec = json.loads((tmp_path / "sweep" / f"sector_{SECTOR:04d}.json").read_text())
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
    rec = json.loads((tmp_path / "sweep" / f"sector_{SECTOR:04d}.json").read_text())
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
    assert len(code_fingerprint()) == 64 and code_fingerprint() == code_fingerprint()


# ---------- contribution bundles ----------
@pytest.fixture
def bundle(swept):
    tmp = swept["tmp"]
    return C.make_bundle(tmp / "sweep" / f"sector_{SECTOR:04d}.json", tmp / "bundle", contributor="Ada L.", now="2026-10-20T00:00:00+00:00")


def _resign(bdir: Path, mutate_results=None, mutate_manifest=None):
    """Change a bundle and re-sign it properly, so only the deeper checks can catch it."""
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


def test_a_valid_bundle_is_ingested_with_credit(bundle, tmp_path):
    man = json.loads((bundle / "manifest.json").read_text())
    assert sorted(p.name for p in bundle.iterdir()) == ["config.toml", "manifest.json", "results.json"]
    assert man["code_fingerprint"] == code_fingerprint() and len(man["lightcurves"]) == 3
    assert all(len(x["sha256"]) == 64 for x in man["lightcurves"]) and man["signed_off"]["by"] == "Ada L."
    sweep_dir = tmp_path / "merged"
    shutil.copytree(tmp_path / "sweep", sweep_dir)
    out = C.ingest_bundle(bundle, sweep_dir=sweep_dir)
    assert out["contributor"] == "Ada L." and (sweep_dir / "contributions" / man["bundle_id"] / "manifest.json").exists()
    cat = json.loads((sweep_dir / "catalogue.json").read_text())
    names = {c["name"] for e in cat["entries"] for c in e["credit"]}
    assert names == {"exoplan", "Ada L."}
    # The same star-sectors searched twice with the same panel: one entry each, both credited; coverage counts the star-sector once.
    assert all({c["name"] for c in e["credit"]} == {"exoplan", "Ada L."} for e in cat["entries"])
    assert cat["counts"]["star_sectors_searched"] == 3 and cat["counts"]["searches"] == 6
    assert [c["name"] for c in cat["contributors"]] == ["exoplan", "Ada L."] or {c["name"] for c in cat["contributors"]} == {"exoplan", "Ada L."}
    with pytest.raises(C.BundleRefused, match="already ingested"):
        C.ingest_bundle(bundle, sweep_dir=sweep_dir)


def test_a_zipped_bundle_is_accepted(bundle, tmp_path):
    z = tmp_path / "b.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in ("manifest.json", "results.json", "config.toml"):
            zf.write(bundle / f, f"bundle/{f}")
    assert C.validate_bundle(z)["manifest"]["contributor"]["name"] == "Ada L."
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../evil.py", "x")
    with pytest.raises(C.BundleRefused, match="unexpected file"):
        C.validate_bundle(bad)


@pytest.mark.parametrize("damage, match", [
    (lambda b: (b / "results.json").write_text((b / "results.json").read_text().replace('"searched"', '"searched" ', 1)), "hash mismatch on results.json"),
    (lambda b: (b / "config.toml").write_text((b / "config.toml").read_text() + "\n# edited\n"), "hash mismatch on config.toml"),
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
        C.validate_bundle(bundle, code="0" * 64)


def test_an_edited_class_is_refused_even_when_re_signed(bundle):
    def promote(r):
        for s in r["stars"]:
            for e in s.get("entries") or []:
                if e["class"] != "planet_candidate":
                    e["class"], e["confidence"] = "planet_candidate", "medium"
                    return
        raise AssertionError("no entry to edit")
    _resign(bundle, promote)
    with pytest.raises(C.BundleRefused, match="the rules give|variability rule"):
        C.validate_bundle(bundle)


def test_a_bad_lightcurve_hash_is_refused_even_when_re_signed(bundle):
    def drop(r):
        r["stars"][0]["file_sha256"] = "not-a-hash"
    _resign(bundle, drop)
    with pytest.raises(C.BundleRefused, match="light-curve sha256"):
        C.validate_bundle(bundle)


def test_a_config_that_does_not_match_its_hash_is_refused(bundle):
    (bundle / "config.toml").write_text((bundle / "config.toml").read_text().replace("min_score = 0.5", "min_score = 0.4"))
    _resign(bundle)
    with pytest.raises(C.BundleRefused, match="config hash mismatch"):
        C.validate_bundle(bundle)


def test_credentials_and_bad_names_are_refused(bundle, swept, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-THISISNOTAREALKEY0123456789")
    rec = swept["tmp"] / "sweep" / f"sector_{SECTOR:04d}.json"
    b2 = C.make_bundle(rec, swept["tmp"] / "b2", contributor="Grace H.")
    assert "sk-ant" not in "".join(p.read_text() for p in b2.iterdir())   # nothing from the environment goes in
    (b2 / "config.toml").write_text((b2 / "config.toml").read_text() + '\n# key = "sk-ant-api03-THISISNOTAREALKEY0123456789"\n')
    _resign(b2)
    with pytest.raises(C.BundleRefused, match="credential"):
        C.validate_bundle(b2)
    for bad in ("", "x" * 61, "<script>", "see https://x.y", "me@example.org"):
        with pytest.raises(C.BundleRefused, match="contributor name"):
            C.make_bundle(rec, swept["tmp"] / "b3", contributor=bad)


def test_ingest_can_check_lightcurves_at_mast(bundle, swept, tmp_path):
    mast = swept["mast"]
    sweep_dir = tmp_path / "m2"
    sweep_dir.mkdir()
    # The bundle's light curves re-fetched (from the fake archive) hash to the same bytes.
    cache = tmp_path / "fresh"
    shutil.copytree(swept["tmp"] / "cache" / "sweep" / "targets", cache / "sweep" / "targets")
    out = C.ingest_bundle(bundle, sweep_dir=sweep_dir, verify_lightcurves=2, fetch=mast.fetch, cache_root=cache)
    assert out["star_sectors"] == 3

    def other(uri, local):
        _write_spoc(Path(local), 0, 42, "quiet")
    cache2 = tmp_path / "fresh2"
    shutil.copytree(swept["tmp"] / "cache" / "sweep" / "targets", cache2 / "sweep" / "targets")
    with pytest.raises(C.BundleRefused, match="hashes to"):
        C.check_at_mast(json.loads((bundle / "results.json").read_text()), 1, fetch=other, cache_root=cache2)


def test_cli_ingest_refuses_with_a_message(bundle, capsys, tmp_path):
    from exoplan.cli import main

    (bundle / "results.json").write_text("{}")
    assert main(["ingest", str(bundle), "--sweep-dir", str(tmp_path / "x")]) == 1
    assert "refused: hash mismatch on results.json" in capsys.readouterr().err


def test_contributing_doc_says_keys_stay_in_the_environment():
    text = Path("CONTRIBUTING.md").read_text()
    for must in ("exoplan sweep", "exoplan bundle", "exoplan ingest", "ANTHROPIC_API_KEY", "environment", "configs/sweep_sentinels.toml"):
        assert must in text
    assert "Never paste" in text or "never paste" in text

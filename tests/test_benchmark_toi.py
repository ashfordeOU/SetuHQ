# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""S1c: the real-TOI benchmark's sample, controls and scoring (offline, with fixtures)."""

import json
from pathlib import Path

import numpy as np
import pytest

from setuhq import benchmark_toi as B
from setuhq.lightcurve import LightCurve


def _row(tic, toi, disp, p=3.0, t0=2459000.5, dur=2.0, **kw):
    r = {"tid": str(tic), "toi": toi, "tfopwg_disp": disp, "pl_orbper": str(p), "pl_orbpererr1": "0.0001", "pl_tranmid": str(t0),
         "pl_tranmiderr1": "0.001", "pl_trandurh": str(dur), "pl_trandep": "1000", "pl_rade": "2.5", "st_tmag": "9", "st_teff": "5800",
         "st_logg": "4.4", "st_rad": "1.0", "rowupdate": "2026-01-01"}
    r.update({k: str(v) for k, v in kw.items()})
    return r


def _rows():
    rows = []
    for i in range(60):
        rows.append(_row(1000 + i, f"{1000 + i}.01", ["CP", "KP", "FP", "FA", "PC"][i % 5]))
    rows.append(_row(2000, "2000.01", "CP", p=20.0))       # too long a period
    rows.append(_row(2001, "2001.01", "CP", t0=""))         # no mid-time
    rows += [_row(2002, "2002.01", "CP"), _row(2002, "2002.02", "FP")]  # two TOIs on one star
    return rows


def test_wilson_interval():
    p, lo, hi = B.wilson(8, 10)
    assert p == 0.8 and lo == pytest.approx(0.4902, abs=1e-3) and hi == pytest.approx(0.9433, abs=1e-3)
    assert B.wilson(0, 0) == (None, None, None)
    p, lo, hi = B.wilson(0, 50)
    assert p == 0 and lo == 0 and 0.05 < hi < 0.08


def test_the_sample_is_frozen_seeded_one_per_star_and_split_by_star():
    rows = _rows()
    a = B.freeze_sample(rows, fetched_at="2026-10-19T00:00:00Z", n_pos=10, n_fp=10, n_fa=5)
    b = B.freeze_sample(list(reversed(rows)), fetched_at="2026-10-19T00:00:00Z", n_pos=10, n_fp=10, n_fa=5)
    assert a["sha256"] == b["sha256"] and a["counts"] == {"positive": 10, "fp": 10, "fa": 5}
    tics = [t["tic"] for t in a["tois"]]
    assert len(tics) == len(set(tics))  # held out by star: one TOI per star
    assert all(0.5 <= t["period"] <= B.MAX_PERIOD and t["tranmid_bjd"] for t in a["tois"])
    assert all(t["disposition"] in ("CP", "KP", "FP", "FA") for t in a["tois"])
    assert all(t["half"] == B.half_of(t["tic"]) for t in a["tois"]) and {t["half"] for t in a["tois"]} == {"held_out", "tuning"}
    assert "2000.01" not in {t["toi"] for t in a["tois"]} and "2001.01" not in {t["toi"] for t in a["tois"]}


def test_the_stored_sample_states_its_source_and_hash():
    s = json.loads(Path("docs/results/benchmark_toi_sample.json").read_text())
    assert s["counts"]["positive"] >= 300 and s["counts"]["fp"] >= 300
    assert s["source"].startswith("NASA Exoplanet Archive") and s["fetched_at"] and len(s["sha256"]) == 64
    import hashlib
    assert hashlib.sha256(json.dumps(s["tois"], sort_keys=True).encode()).hexdigest() == s["sha256"]
    assert len({t["tic"] for t in s["tois"]}) == len(s["tois"])


def test_controls_keep_the_times_and_destroy_the_signal():
    t = np.arange(0, 27, 2 / 1440)
    f = 1 + np.where(np.abs(((t - 1) % 3.0) - 1.5) > 1.45, -0.01, 0.0)
    lc = LightCurve("TIC 1", "TESS", t, f, np.full(t.size, 1e-4))
    inv = B.inverted(lc)
    assert np.array_equal(inv.time, t) and np.allclose(inv.flux, 2 - f)
    scr = B.scrambled(lc, seed=3)
    assert np.array_equal(scr.time, t) and np.allclose(np.sort(scr.flux), np.sort(f)) and not np.allclose(scr.flux, f)
    assert np.array_equal(B.scrambled(lc, seed=3).flux, scr.flux)  # seeded


@pytest.mark.parametrize("found,name", [(3.0, "P"), (6.0, "2P"), (1.5, "P/2"), (9.0, "3P"), (1.0, "P/3"), (4.5, "3P/2"), (2.0, "2P/3"), (3.7, None), (None, None)])
def test_period_aliases(found, name):
    assert B.alias(found, 3.0) == name


def test_scoring_a_star():
    toi = {"tic": 1, "toi": "1.01", "class": "fp", "disposition": "FP", "period": 3.0, "period_err": 1e-4, "tranmid_bjd": 2459000.5,
           "tranmid_err": 1e-3, "duration_hours": 2.0, "depth_ppm": 1000}
    on = {"t_center": 2459000.5 + 3 * 10 - 2457000, "duration_hours": 2.0, "period_days": 3.0, "time_unit": "BTJD", "passed": True,
          "flags": "v_shape", "snr": 12, "fit": {"depth_ppm": 900, "t14_hours": 2.1}}
    off = dict(on, t_center=on["t_center"] + 1.2, flags="", passed=True)
    s = B.score_star(toi, [on, off])
    assert s["recovered"] and s["flagged"] and s["eb_flags"] == ["v_shape"] and s["other_passed"] == 1
    assert s["period_alias"] == "P" and s["depth_ratio"] == pytest.approx(0.9) and s["duration_ratio"] == pytest.approx(1.05)
    rejected = B.score_star(toi, [dict(on, passed=False, flags="secondary_eclipse")])
    assert not rejected["recovered"] and rejected["seen"] and rejected["rejected_on_ephemeris"] and rejected["flagged"]
    missed = B.score_star(toi, [off])
    assert not missed["seen"] and not missed["flagged"]


def test_summary_and_report_wording():
    sample = {"source": "NASA Exoplanet Archive, table toi", "fetched_at": "2026-10-19T00:00:00Z", "seed": 1, "rule": "r",
              "counts": {"positive": 2, "fp": 1, "fa": 0}, "sha256": "0" * 64,
              "tois": [{"toi": "1", "class": "positive", "half": "held_out", "radius_re": 1.5, "period": 1.0},
                       {"toi": "2", "class": "positive", "half": "held_out", "radius_re": 3.0, "period": 4.0},
                       {"toi": "3", "class": "fp", "half": "tuning", "radius_re": 9.0, "period": 2.0},
                       {"toi": "4", "class": "positive", "half": "held_out", "radius_re": 2.0, "period": 3.0}]}
    mk = lambda toi, cls, rec, seen=None: {"toi": toi, "real": {"toi": toi, "class": cls, "recovered": rec, "seen": rec if seen is None else seen, "flagged": False,
                                                                 "period_alias": "P" if rec else None, "depth_ratio": 1.0 if rec else None, "duration_ratio": 1.0 if rec else None},
                                         "inverted": {"passed": 0}, "scrambled": {"passed": 1}}
    results = [mk("1", "positive", True), mk("2", "positive", False), mk("3", "fp", False, seen=True),
               {"toi": "4", "no_data": "no SPOC 2-minute light curve"}]
    results.append({"toi": "5", "no_data": "download failed: ProxyError"})
    sample["tois"].append({"toi": "5", "class": "fp", "half": "held_out", "radius_re": 2.0, "period": 3.0})
    s = B.summarise(results, sample)
    assert s["held_out"]["completeness"]["k"] == 1 and s["held_out"]["completeness"]["n"] == 2
    # A star with no 2-minute data is its own row; the all-stars completeness counts it as missed.
    assert s["held_out"]["not_searchable"] == {"positive": 1, "fp": 0, "fa": 0} and s["held_out"]["failed"] == 1
    assert s["held_out"]["completeness_all_stars"]["k"] == 1 and s["held_out"]["completeness_all_stars"]["n"] == 3
    assert s["all"]["controls"]["scrambled"]["vetted_false_alarms"] == 3 and s["all"]["controls"]["scrambled"]["per_1000_star_sectors"] == 1000
    md = B.to_markdown({"sample": sample, "panel": "the Probes", "summary": s, "sentinels": None})
    assert md.startswith("# Blind benchmark on real TESS Objects of Interest")
    assert "Measured on a stated benchmark; not discoveries." in md and "Wilson 95% intervals" in md
    assert "Robovetter" in md and "Planet Hunters TESS" in md
    assert "Completeness, headline: CP/KP TOIs recovered on searchable stars" in md and "1 stars (1 CP/KP, 0 FP, 0 FA)" in md and "1 more failed to download" in md


def test_feed_level_false_alarms_and_what_they_imply_for_the_live_feed():
    row = lambda new, pre=1: {"pre_fap": pre, "admitted": new, "new_candidate": new, "known_toi": 0, "new_signals": new, "fap": [0.005] * new}
    rs = [{"feed": {"real": row(0), "inverted": row(1), "scrambled": row(0)}} for _ in range(10)]
    f = B._feed_summary(rs)
    assert f["inverted"]["new_signals_per_1000"] == 1000 and f["scrambled"]["new_signals_per_1000"] == 0
    h = {"feed": f}
    imp = B.feed_implication(h, {"source": "x", "targets_reviewed": 19, "new_signals": 3})
    assert imp["expected_false_per_100_targets"] == pytest.approx(200) and imp["bad"]
    calm = B.feed_implication({"feed": B._feed_summary([{"feed": {v: row(0, 0) for v in ("real", "inverted", "scrambled")}}] * 10)},
                              {"source": "x", "targets_reviewed": 19, "new_signals": 3})
    assert calm["expected_false_per_100_targets"] == 0 and not calm["bad"]
    md = "\n".join(B._feed_lines({"feed_implication": imp}, h))
    assert "This is bad" in md and "Proposed next step (not applied here)" in md and "held-out half" in md
    head = "\n".join(B._headline({"feed_implication": dict(imp, live_new_signals_per_100_targets=15.8)}))
    assert "live discovery feed's \"new\" signals are consistent with noise" in head and "not applied" in head
    assert "This is bad" not in "\n".join(B._feed_lines({"feed_implication": calm}, h))


def test_the_feed_rule_matches_discover():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("bench_script", Path("scripts/benchmark_real_tois.py"))
    S = importlib.util.module_from_spec(spec)
    sys.modules["bench_script"] = S
    spec.loader.exec_module(S)
    ok = {"passed": True, "flags": "v_shape", "depth_ppm": 900, "period_days": 3.1, "n_transits": 3}
    assert S.feed_eligible(ok)
    assert not S.feed_eligible(dict(ok, passed=False)) and not S.feed_eligible(dict(ok, flags="off_ephemeris"))
    assert not S.feed_eligible(dict(ok, depth_ppm=6000)) and not S.feed_eligible(dict(ok, n_transits=1))
    assert not S.feed_eligible(dict(ok, period_days=None))
    assert S.FEED_FAP_TRIALS == 200 and "fap_trials = 200" in Path("configs/discovery.toml").read_text()


@pytest.mark.network
def test_toi_table_is_reachable(tmp_path):
    rows, fetched = B.fetch_toi_table(tmp_path / "toi.csv", refresh=True)
    assert len(rows) > 5000 and {"CP", "KP", "FP"} <= {r["tfopwg_disp"] for r in rows}


def test_scrambling_first_removes_every_known_transit():
    t = np.arange(0, 27, 2 / 1440)
    period, t0, dur_h = 3.0, 1.0, 3.0
    phase = (t - t0 + 0.5 * period) % period - 0.5 * period
    f = 1 - 0.01 * (np.abs(phase) < 0.5 * dur_h / 24)
    lc = LightCurve("TIC 1", "TESS", t, f, np.full(t.size, 1e-4))
    masked = B.mask_transits(lc, [(period, t0, dur_h)])
    assert masked.flux.min() == 1.0 and masked.time.size < t.size
    scr = B.scrambled(lc, seed=1, ephemerides=[(period, t0, dur_h)])
    assert scr.flux.min() == 1.0  # no real transit is moved to a new time


def test_the_threshold_audit_reads_the_values_themselves():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("bench_script2", Path("scripts/benchmark_real_tois.py"))
    S = importlib.util.module_from_spec(spec)
    sys.modules["bench_script2"] = S
    spec.loader.exec_module(S)
    now = S._threshold_values(None)
    assert now["src/setuhq/transitfit.py:V_SHAPE_DCHI2"] == "9.0"
    assert now["configs/discovery.toml:[search]fap_trials"] == "2000"
    assert now["src/setuhq/discover.py:MAX_FEED_DEPTH_PPM"] == "5000.0"
    assert "docs/results/reviewer_weights.json:volunteer-typical" in now
    assert all(x in S.NOT_THRESHOLDS for x in ("fap_cache", "FAP_TAIL_FLOOR"))


def test_losses_are_broken_down_by_class_and_half_and_a_skew_is_named():
    tois = [{"toi": str(i), "tic": i, "class": c, "half": "held_out"} for i, c in enumerate(["positive"] * 10 + ["fp"] * 10)]
    sample = {"tois": tois}
    ok = lambda t: {"toi": t["toi"], "real": {"recovered": True}}
    results = [ok(t) for t in tois[:10]] + [{"toi": t["toi"], "no_data": "download failed: X"} for t in tois[10:14]] \
        + [{"toi": t["toi"], "no_data": "no SPOC 2-minute light curve"} for t in tois[14:16]] + [ok(t) for t in tois[16:19]]
    loss = B.loss_table(results, sample)
    assert loss["held_out"]["fp"] == {"n": 10, "data": 3, "not_searchable": 2, "failed": 4, "not_run": 1}
    assert loss["held_out"]["positive"]["data"] == 10
    md = "\n".join(B._loss_lines(loss))
    assert "skewed by" in md and "| held-out | FP | 10 | 3 | 2 | 4 | 1 |" in md and "skewed toward FP" in md
    assert "balanced" not in md


def test_clipping_exposure_is_counted_by_class_and_misses_are_checked():
    tois = [{"toi": str(i), "tic": i, "class": c, "half": "held_out"} for i, c in enumerate(["positive"] * 4 + ["fp"] * 2)]
    real = lambda rec: {"recovered": rec, "class": "x"}
    clip = lambda aff, removed: {"affected": aff, "in_transit_removed_fraction": removed}
    results = [{"toi": "0", "real": real(False), "clip": clip(True, 1.0)}, {"toi": "1", "real": real(True), "clip": clip(True, 0.2)},
               {"toi": "2", "real": real(False), "clip": clip(True, 0.1)}, {"toi": "3", "real": real(True), "clip": clip(False, 0.0)},
               {"toi": "4", "real": real(False), "clip": clip(True, 0.9)}, {"toi": "5", "real": real(False), "clip": clip(False, 0.0)}]
    c = B.clipping_summary(results, {"tois": tois}, 8.0)["held_out"]
    assert c["affected"] == {"positive": 3, "fp": 1, "fa": 0} and c["cp_kp_affected_missed"] == 2
    assert c["cp_kp_misses_explained"] == 1 and c["explained_tois"] == ["0"] and c["cp_kp_affected_recovered"] == 1


def test_the_committed_benchmark_fingerprints_still_verify_after_the_rename():
    """docs/results/benchmark_real_tois.json maps each per-star code fingerprint to the commit whose pipeline made it
    (src/exoplan then). The script must still compute those values from those commits, and give HEAD's code the same
    value whether its files sit under src/setuhq with licence headers or under src/exoplan without."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import benchmark_real_tois as BR

    cp = json.loads((root / "docs/results/benchmark_real_tois.json").read_text())["code_provenance"]
    for fp, commit in cp["commit"].items():
        if subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root, capture_output=True).returncode:
            pytest.skip("needs the full history (fetch-depth 0)")
        assert BR.code_fingerprint(commit) == fp
    assert all(f.startswith("src/setuhq/") for f in BR.CODE_FILES) and BR._label(BR.CODE_FILES[0]) == "src/exoplan/discover.py"


def _bench_script():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("bench_script3", Path(__file__).resolve().parents[1] / "scripts/benchmark_real_tois.py")
    S = importlib.util.module_from_spec(spec)
    sys.modules["bench_script3"] = S
    spec.loader.exec_module(S)
    return S


def test_the_audit_exempts_only_the_exact_table_move_and_tracks_the_tables_bytes(monkeypatch):
    """Moving the limb-darkening table into the package (same bytes) is not a threshold change; pointing LD_TABLE
    anywhere else, or changing a reference table's bytes, is."""
    S = _bench_script()
    key = "src/setuhq/transitfit.py:LD_TABLE"
    then, now = S.EXACT_EXEMPTIONS[key]
    table = "table:claret2017_tess_quadratic.json:sha256"
    frozen = {key: then, table: "a" * 64}

    def audit(current):
        monkeypatch.setattr(S, "_threshold_values", lambda rev: frozen if rev == S.FROZEN_AFTER else current)
        monkeypatch.setattr(S, "_git", lambda *a: "")
        return S.threshold_audit("HEAD")

    assert audit({key: now, table: "a" * 64})["clean"]
    assert key in audit({key: 'files("setuhq") / "data" / "other_table.json"', table: "a" * 64})["changed"]
    assert table in audit({key: now, table: "b" * 64})["changed"]


def test_the_committed_threshold_audit_stays_clean_at_the_results_commit():
    import subprocess

    S = _bench_script()
    root = Path(__file__).resolve().parents[1]
    committed = json.loads((root / "docs/results/benchmark_real_tois.json").read_text())["threshold_audit"]
    for rev in (S.FROZEN_AFTER, "40cceca"):
        if subprocess.run(["git", "cat-file", "-e", f"{rev}^{{commit}}"], cwd=root, capture_output=True).returncode:
            pytest.skip("needs the full history (fetch-depth 0)")
    now = S.threshold_audit("40cceca")
    assert now["clean"] and committed["clean"] and now["changed"] == committed["changed"] == {}
    assert "table:claret2017_tess_quadratic.json:sha256" in S._threshold_values("40cceca")

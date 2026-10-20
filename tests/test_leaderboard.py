# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""The real-TOI leaderboard: it scores events itself, reproduces the benchmark report, cannot be won by calling
everything a planet, and refuses what it should."""

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from setuhq import leaderboard as L
from setuhq.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_BROWSER = shutil.which("node") is not None and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()

SAMPLE = L.load_sample()
BENCH = json.loads(L.BENCHMARK.read_text())
INPUTS = json.loads(L.INPUTS.read_text())
SUBS = {s["id"]: s for s in L.load_submissions()}
RESULTS = json.loads(L.RESULTS.read_text())
ENTRY = {e["id"]: e for e in RESULTS["entries"]}
H = BENCH["summary"]["held_out"]
TOI = {t["toi"]: t for t in SAMPLE["tois"]}


def _score(sid):
    return L.score(SUBS[sid], SAMPLE, INPUTS, BENCH)


def _kn(r):
    return (r["k"], r["n"])


def _on_ephemeris(name):
    """An event exactly on the TOI's published ephemeris (BTJD), passed and unflagged."""
    t = TOI[name]
    return {"t_center": t["tranmid_bjd"] - 2457000.0, "duration_hours": t["duration_hours"], "period_days": t["period"],
            "passed": True, "flags": []}


def everything_is_a_planet(controls):
    sub = copy.deepcopy(SUBS["probes"])
    sub.update(id="everything", name="Everything is a planet",
               provenance={"method": "call every TOI a planet", "code_version": "none", "generated_from": ["nothing"]})
    for p in sub["predictions"]:
        p.update(searched=True, events=[_on_ephemeris(p["toi"])], controls=copy.deepcopy(controls))
    return sub


# ---------- the public inputs ----------
def test_public_inputs_are_the_committed_file_and_carry_no_held_out_label():
    assert INPUTS == L.public_inputs(SAMPLE)
    assert L.inputs_sha256(INPUTS) == RESULTS["inputs_sha256"]
    assert INPUTS["sample_sha256"] == SAMPLE["sha256"] == RESULTS["sample_sha256"]
    held = INPUTS["held_out"]
    assert len(held) == sum(1 for t in SAMPLE["tois"] if t["half"] == "held_out")
    for t in held:
        assert set(t) == set(L.HELD_OUT_PUBLIC)
    assert all(t["half"] == "tuning" and "class" in t for t in INPUTS["tuning"])


# ---------- the scorer reproduces the benchmark report ----------
def test_probe_events_scored_by_the_leaderboard_reproduce_every_per_star_row():
    per = {r["toi"]: r for r in BENCH["per_star"]}
    for row in L.outcomes(SUBS["probes"], SAMPLE, BENCH):
        r = per[row["toi"]]
        if not r.get("real"):
            assert not row["searched"]
            continue
        assert (row["seen"], row["recovered"], row["flagged"]) == (r["real"]["seen"], r["real"]["recovered"], r["real"]["flagged"])
        assert row["controls"] == {"inverted": r["inverted"]["passed"], "scrambled": r["scrambled"]["passed"]}


def test_probes_entry_scores_equal_the_benchmark_reports_held_out_numbers():
    s = _score("probes")
    assert _kn(s["completeness"]) == _kn(H["completeness"])
    assert _kn(s["completeness_all_stars"]) == _kn(H["completeness_all_stars"])
    assert _kn(s["fp_found"]) == _kn(H["fp_seen"])
    assert _kn(s["fp_flagged_of_found"]) == _kn(H["fp_flagged_of_seen"])
    assert _kn(s["fa_found"]) == _kn(H["fa_seen"])
    assert s["fp_rejection"]["k"] == H["fp_seen"]["n"] - (H["fp_seen"]["k"] - H["fp_flagged_of_seen"]["k"])
    ns = H["not_searchable"]["fp"]
    assert _kn(s["fp_rejection_all_stars"]) == (s["fp_rejection"]["k"] + ns, s["fp_rejection"]["n"] + ns)
    for a, b in zip(s["completeness_by_radius"], H["completeness_by_radius"]):
        assert a["bin"] == b["bin"] and _kn(a) == _kn(b)
    for v in ("inverted", "scrambled"):
        c, hc = s["controls"][v], H["controls"][v]
        assert c["vetted_false_alarms"] == hc["vetted_false_alarms"] and _kn(c["stars_with_any"]) == _kn(hc["stars_with_any"])
    assert s["controls_complete"] and ENTRY["probes"]["ranked"]


def test_youden_j_uses_one_predicate_on_the_benchmark_searchable_set():
    s = _score("probes")
    a, b = s["completeness_clean_searchable"], s["fp_rejection_searchable"]
    # The searchable set is the benchmark's, not the submitter's.
    assert a["n"] == H["completeness"]["n"] and b["n"] == H["fp_seen"]["n"]
    # Clean on both sides: a recovered but flagged CP/KP dip is not counted as found.
    rows = [r for r in L.outcomes(SUBS["probes"], SAMPLE, BENCH) if r["searchable"]]
    assert a["k"] == sum(r["recovered"] and not r["flagged"] for r in rows if r["cls"] == "positive")
    assert b["k"] == sum(not (r["recovered"] and not r["flagged"]) for r in rows if r["cls"] == "fp")
    j = s["youden_j"]
    assert j["j"] == pytest.approx(a["rate"] + b["rate"] - 1) and j["lo"] < j["j"] < j["hi"]
    assert j["lo"] == pytest.approx(j["j"] - ((a["rate"] - a["lo"]) ** 2 + (b["rate"] - b["lo"]) ** 2) ** 0.5)
    ja = s["youden_j_all_stars"]
    assert ja["j"] == pytest.approx(s["completeness_clean_all_stars"]["rate"] + s["fp_rejection_all_stars"]["rate"] - 1)


def test_calling_searchable_stars_not_searched_cannot_help():
    sub = copy.deepcopy(SUBS["probes"])
    base = _score("probes")
    for p in sub["predictions"]:
        if p["searched"] and not any(e["passed"] for e in p["events"]):
            p.update(searched=False, events=[], controls=None)  # hide every star it would not offer anyway
    s = L.score(sub, SAMPLE, INPUTS, BENCH)
    assert s["youden_j"]["j"] == pytest.approx(base["youden_j"]["j"])
    assert s["completeness_clean_searchable"]["n"] == base["completeness_clean_searchable"]["n"]


def test_sentinel_entries_equal_the_benchmark_reports_persona_numbers():
    per = BENCH["sentinels"]["personas"]
    rows = {}
    for pid in ("claude-volunteer", "claude-skeptic"):
        s = _score(pid)
        assert _kn(s["completeness"]) == _kn(per[pid]["cp_kp_marked"])
        fp = per[pid]["fp_marked_as_planet"]
        assert _kn(s["fp_rejection"]) == (fp["n"] - fp["k"], fp["n"])
        assert s["controls"] == {"inverted": None, "scrambled": None}
        assert [p["toi"] for p in SUBS[pid]["predictions"]] == BENCH["sentinels"]["subsample"]
        rows[pid] = L.outcomes(SUBS[pid], SAMPLE, BENCH)
    agree = sum(x["recovered"] == y["recovered"] for x, y in zip(rows["claude-volunteer"], rows["claude-skeptic"]))
    assert (agree, len(rows["claude-volunteer"])) == (BENCH["sentinels"]["agreement"]["agree"], BENCH["sentinels"]["agreement"]["n"])


def test_derived_combinations_follow_their_stated_star_level_rules():
    pr = {r["toi"]: r for r in L.outcomes(SUBS["probes-subsample"], SAMPLE, BENCH)}
    se = [{r["toi"]: r for r in L.outcomes(SUBS[s], SAMPLE, BENCH)} for s in ("claude-volunteer", "claude-skeptic")]
    clean = lambda r: r["recovered"] and not r["flagged"]  # noqa: E731
    order = BENCH["sentinels"]["subsample"]
    for d in L.DERIVED:
        rows = L.combine([pr[n] for n in order], [[s[n] for n in order] for s in se], d["rule"])
        for n, r in zip(order, rows):
            hit = any(s[n]["recovered"] for s in se)
            assert clean(r) == ((clean(pr[n]) or hit) if d["rule"] == "either" else (clean(pr[n]) and hit))
        assert ENTRY[d["id"]]["scores"] == L.score_rows(rows)
        assert "star-level rule, fixed before scoring, not panel consensus" in ENTRY[d["id"]]["name"]


def test_committed_table_is_the_scoring_of_the_committed_submissions():
    res = L.build(SAMPLE, INPUTS, BENCH, L.load_submissions())
    assert res == RESULTS
    assert L.RESULTS_MD.read_text() == L.to_markdown(res)
    assert res["refused"] == [] and {e["id"] for e in res["entries"]} == set(SUBS) | {d["id"] for d in L.DERIVED}


def test_the_subsample_is_never_ranked_and_says_why():
    sub = [e for e in RESULTS["entries"] if e["scope"] == "sentinel_subsample"]
    assert sub and all(e["rank"] is None and not e["ranked"] for e in sub)
    md = L.RESULTS_MD.read_text()
    assert "40 stars cannot order these configurations" in md
    part = md.split("## The Sentinels' stated subsample")[1]
    assert "| rank |" not in part.split("\n\n")[2]


def test_every_seeded_entry_carries_provenance_and_the_attribution():
    for s in (v for k, v in SUBS.items() if k != L.FLOOR_ID):
        assert s["tuned_on"] == "none" and s["inputs_sha256"] == L.inputs_sha256(INPUTS)
        assert "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors." in s["provenance"]["method"]
        # The code that searched the stars (the report itself was regenerated later, at the feed-rule commit).
        assert any(c[:7] in s["provenance"]["code_version"] for c in BENCH["code_provenance"]["commit"].values())


# ---------- gaming ----------
@pytest.mark.parametrize("flag", [None, "odd_even_mismatch", "secondary_eclipse", "v_shape", "density_mismatch"])
def test_everything_is_a_planet_cannot_win(flag):
    """The reviewers' crafted entries: every held-out star searched, an event on its published ephemeris that passed,
    unflagged or carrying one eclipsing-binary flag on every star."""
    probes_j = ENTRY["probes"]["scores"]["youden_j"]["j"]

    def crafted(controls):
        sub = everything_is_a_planet(controls)
        for p in sub["predictions"]:
            p["events"][0]["flags"] = [flag] if flag else []
        return sub

    res = L.build(SAMPLE, INPUTS, BENCH, list(SUBS.values()) + [crafted(None)])
    e = next(x for x in res["entries"] if x["id"] == "everything")
    assert e["scores"]["youden_j"]["j"] == pytest.approx(0.0)
    assert e["scores"]["youden_j_all_stars"]["j"] == pytest.approx(0.0)
    assert not e["ranked"] and e["rank"] is None and "controls" in e["unranked_reason"]
    # With control lists claiming no false alarm at all it is ranked, and still below the Probes: J = 0.
    res = L.build(SAMPLE, INPUTS, BENCH, list(SUBS.values()) + [crafted({"inverted": [], "scrambled": []})])
    by = {x["id"]: x for x in res["entries"]}
    e = by["everything"]
    assert e["ranked"] and e["scores"]["youden_j"]["j"] == pytest.approx(0.0)
    assert e["rank"] > by["probes"]["rank"] and probes_j > 0


# ---------- the metadata-only floor ----------
def test_the_metadata_floor_is_built_reproducibly_from_public_inputs():
    import importlib.util

    spec = importlib.util.spec_from_file_location("mb", ROOT / "scripts/leaderboard_metadata_baseline.py")
    mb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mb)
    assert mb.build_submission() == SUBS[L.FLOOR_ID]
    f = ENTRY[L.FLOOR_ID]
    assert f["ranked"] and f["tuned_on"] == "tuning" and f["kind"] == "baseline"
    # It ignores the light curve, so it reports the same events on the controls.
    for p in SUBS[L.FLOOR_ID]["predictions"]:
        if p["searched"]:
            assert p["controls"]["inverted"] == p["events"] == p["controls"]["scrambled"]


def test_the_floor_verdict_comes_from_a_paired_delta_j():
    fl = RESULTS["floor"]
    dj = fl["paired"]
    rows_f = L.outcomes(SUBS[L.FLOOR_ID], SAMPLE, BENCH)
    rows_p = L.outcomes(SUBS["probes"], SAMPLE, BENCH)
    again = L.paired_delta_j(rows_f, rows_p)
    assert again == dj  # deterministic (seeded)
    # ΔJ is the difference of the two ranked J values, on the same stars.
    assert dj["delta_j"] == pytest.approx(ENTRY[L.FLOOR_ID]["scores"]["youden_j"]["j"] - ENTRY["probes"]["scores"]["youden_j"]["j"])
    assert dj["stars"] == {"positive": H["completeness"]["n"], "fp": H["fp_seen"]["n"]}
    assert dj["lo"] < dj["delta_j"] < dj["hi"] and 0 <= dj["p_le_0"] <= 1
    assert fl["verdict"] == ("floor_ahead" if dj["lo"] > 0 else "probes_ahead" if dj["hi"] < 0 else "not_shown")
    assert RESULTS["floor_note"] == L.floor_note(fl) and RESULTS["floor_note"] in L.RESULTS_MD.read_text()


@pytest.mark.parametrize("delta,lo,hi,starts", [
    (+0.086, -0.05, +0.22, "The benchmark cannot show"),   # the committed case: floor higher, interval spans 0
    (-0.05, -0.19, +0.09, "The benchmark cannot show"),    # Probes higher, intervals overlapping: still not shown
    (+0.20, +0.06, +0.34, "The metadata-only floor is significantly ahead"),
    (-0.20, -0.34, -0.06, "The Probes are significantly ahead"),
])
def test_the_floor_sentence_follows_the_paired_interval_only(delta, lo, hi, starts):
    dj = {"delta_j": delta, "lo": lo, "hi": hi, "p_le_0": 0.5}
    verdict = "floor_ahead" if lo > 0 else "probes_ahead" if hi < 0 else "not_shown"
    note = L.floor_note({"paired": dj, "verdict": verdict})
    assert note.startswith(starts)
    assert ("mostly measures how separable" in note) == (verdict == "floor_ahead")
    assert "do not beat" not in note


def test_a_perturbed_ranking_changes_the_floor_verdict():
    """Make the floor call every searchable star a planet: its J drops to 0 and the Probes pull significantly ahead."""
    sub = copy.deepcopy(SUBS[L.FLOOR_ID])
    for p in sub["predictions"]:
        if p["searched"]:
            ev = [_on_ephemeris(p["toi"])]
            p.update(events=ev, controls={"inverted": [], "scrambled": []})
    subs = [s for k, s in SUBS.items() if k != L.FLOOR_ID] + [sub]
    res = L.build(SAMPLE, INPUTS, BENCH, subs)
    assert res["floor"]["verdict"] == "probes_ahead" and res["floor_note"].startswith("The Probes are significantly ahead")


def test_the_floor_counts_the_same_stars_as_the_probes():
    searchable = L.benchmark_searchable(BENCH)
    for p in SUBS[L.FLOOR_ID]["predictions"]:
        assert p["searched"] == (p["toi"] in searchable)
    f, pr = ENTRY[L.FLOOR_ID]["scores"], ENTRY["probes"]["scores"]
    for v in ("inverted", "scrambled"):
        assert f["controls"][v]["star_sectors"] == pr["controls"][v]["star_sectors"]
    assert f["reliability_mix"] == pr["reliability_mix"]
    assert L.small_rate(f)["n"] == L.small_rate(pr)["n"]


def test_ranked_entries_name_the_ranks_their_interval_overlaps():
    ranked = [e for e in RESULTS["entries"] if e["ranked"]]
    for e in ranked:
        j = e["scores"]["youden_j"]
        want = sorted({o["rank"] for o in ranked if o is not e and o["scores"]["youden_j"]["lo"] <= j["hi"]
                       and j["lo"] <= o["scores"]["youden_j"]["hi"]})
        assert e["overlaps_ranks"] == want
        if want:
            assert f"| {L.rank_text(e)} |" in L.RESULTS_MD.read_text()


def test_outcomes_needs_the_benchmark():
    with pytest.raises(TypeError):
        L.outcomes(SUBS["probes"], SAMPLE)  # noqa


def test_self_reported_outcomes_are_not_accepted():
    sub = copy.deepcopy(SUBS["probes"])
    for p in sub["predictions"]:
        p.update(seen=True, recovered=True, flagged=False)
    with pytest.raises(L.Refused) as exc:
        L.score(sub, SAMPLE, INPUTS, BENCH)
    assert "fields outside the whitelist" in " ".join(exc.value.reasons)
    old = copy.deepcopy(SUBS["probes"])
    old["format"] = "exoplan-leaderboard/1"
    with pytest.raises(L.Refused, match="retired"):
        L.score(old, SAMPLE, INPUTS, BENCH)


# ---------- refusals ----------
def _refused(mutate):
    sub = copy.deepcopy(SUBS["probes"])
    mutate(sub)
    with pytest.raises(L.Refused) as exc:
        L.score(sub, SAMPLE, INPUTS, BENCH)
    return " ".join(exc.value.reasons)


def _searched(s):
    return next(p for p in s["predictions"] if p["searched"] and p["events"])


def test_refuses_a_submission_built_from_the_full_sample_with_held_out_labels():
    import hashlib

    for h in (L.full_sample_sha256(SAMPLE), SAMPLE["sha256"], hashlib.sha256(L.SAMPLE.read_bytes()).hexdigest()):
        assert "held-out labels" in _refused(lambda s, h=h: s.update(inputs_sha256=h))


def test_refuses_any_other_inputs_hash_sample_hash_or_tuning():
    assert "public tuning-half-only inputs" in _refused(lambda s: s.update(inputs_sha256="0" * 64))
    assert "frozen sample" in _refused(lambda s: s.update(sample_sha256="0" * 64))
    assert "touches held-out labels" in _refused(lambda s: s.update(tuned_on="held_out"))
    assert "tuned_on" in _refused(lambda s: s.pop("tuned_on"))


def test_whitelist_refuses_labels_and_label_proxies_anywhere():
    for key, value in (("class", "fp"), ("radius_re", 2.0), ("depth_ppm", 900), ("tfop", "CP"), ("meta", {"x": 1})):
        assert "whitelist" in _refused(lambda s, k=key, v=value: s["predictions"][0].update({k: v})), key
        assert "whitelist" in _refused(lambda s, k=key, v=value: _searched(s)["events"][0].update({k: v})), key
    assert "whitelist" in _refused(lambda s: s.update(disposition="CP"))
    assert "label field" in _refused(lambda s: s["provenance"].update(Disposition="CP"))


def test_refuses_missing_extra_duplicate_and_tuning_stars():
    assert "no prediction for 1" in _refused(lambda s: s["predictions"].pop())
    assert "duplicate" in _refused(lambda s: s["predictions"].append(dict(s["predictions"][0])))
    tun = next(t for t in SAMPLE["tois"] if t["half"] == "tuning")
    row = {"toi": tun["toi"], "tic": tun["tic"], "searched": False, "events": [], "controls": None}
    assert "tuning-half" in _refused(lambda s: s["predictions"].append(row))
    assert "outside the scope" in _refused(lambda s: s["predictions"].append(dict(row, toi="99999.01")))
    assert "is not the sample's" in _refused(lambda s: s["predictions"][0].update(tic=1))


def test_refuses_malformed_events_and_controls():
    assert "t_center" in _refused(lambda s: _searched(s)["events"][0].update(t_center="x"))
    assert "duration_hours" in _refused(lambda s: _searched(s)["events"][0].update(duration_hours=-1))
    assert "period_days" in _refused(lambda s: _searched(s)["events"][0].update(period_days=0))
    assert "passed" in _refused(lambda s: _searched(s)["events"][0].update(passed=1))
    assert "flags" in _refused(lambda s: _searched(s)["events"][0].update(flags=["looks_like_a_planet"]))
    assert "controls" in _refused(lambda s: _searched(s).update(controls={"inverted": []}))
    assert "not searched" in _refused(lambda s: _searched(s).update(searched=False))
    assert "provenance must state" in _refused(lambda s: s["provenance"].pop("code_version"))
    assert "scope" in _refused(lambda s: s.update(scope="everything"))


@pytest.mark.parametrize("bad", [None, [], "x", 3])
def test_refuses_a_non_object_submission_cleanly(bad):
    assert L.validate(bad, SAMPLE, INPUTS, BENCH) == ["a submission must be a JSON object"]
    with pytest.raises(L.Refused):
        L.score(bad, SAMPLE, INPUTS, BENCH)


def test_cli_scores_and_refuses(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(SUBS["probes"]))
    assert cli_main(["leaderboard", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["scores"]["completeness"]["k"] == H["completeness"]["k"]
    for text in ("[1, 2]", "null", "{not json"):
        (tmp_path / "bad.json").write_text(text)
        assert cli_main(["leaderboard", str(tmp_path / "bad.json")]) == 2
        assert "refused" in capsys.readouterr().err


# ---------- the threshold sweep is not the leaderboard ----------
def test_the_threshold_sweep_is_renamed_and_points_here():
    assert not (ROOT / "docs/leaderboard.md").exists() and not (ROOT / "docs/leaderboard.json").exists()
    sweep = (ROOT / "docs/threshold_sweep.md").read_text()
    assert sweep.startswith("# Threshold sweep") and "leaderboard/leaderboard.md" in sweep
    assert "threshold_sweep.md" in (ROOT / "scripts/improve.py").read_text()
    assert "threshold_sweep.md" in L.RESULTS_MD.read_text()
    assert "docs/threshold_sweep.md" in (ROOT / "README.md").read_text()


# ---------- the app's #/leaderboard ----------
def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


def test_app_leaderboard_route_shows_the_table_rules_and_hash(pi_men_app):
    page = pi_men_app.read_text()
    sec = _route(page, "leaderboard")
    assert 'id="h-leaderboard"' in sec and '<a href="#/sentinels">' in sec
    assert RESULTS["sample_sha256"] in sec and RESULTS["inputs_sha256"] in sec
    assert sec.count("<tr>") - sec.count("<thead><tr>") == len(RESULTS["entries"])
    c = H["completeness_all_stars"]
    c = ENTRY["probes"]["scores"]["completeness_clean_searchable"]
    assert f"{c['k']}/{c['n']}" in sec and "Youden J" in sec and "not measured" in sec
    assert RESULTS["floor_note"] in sec
    assert "40 stars cannot order these configurations" in sec
    assert sec.count('data-l="Rank"') == sum(1 for e in RESULTS["entries"] if e["scope"] == "held_out")
    from setuhq.names import ATTRIBUTION

    assert ATTRIBUTION in sec  # the app's attribution, provider-aware since the multi-provider Sentinels
    assert "SuperIntelligence" not in sec and "confirmed" not in sec.lower().replace("unconfirmed", "")
    assert 'href="#/leaderboard"' in _route(page, "sentinels")


@pytest.mark.skipif(not HAVE_BROWSER, reason="node, Playwright or Chromium is not available")
def test_leaderboard_in_the_browser_both_themes_phone_and_desktop(pi_men_app, tmp_path):
    url = pi_men_app.resolve().as_uri()
    script = tmp_path / "probe.js"
    script.write_text("""
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch({ executablePath: %s, args: ['--allow-file-access-from-files'] });
  const out = [], ext = [];
  for (const [w, h, mob] of [[1360, 900, false], [390, 844, true]]) for (const theme of ['dark', 'light']) {
    const c = await b.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
    await c.addInitScript(t => { try { localStorage.setItem('setuhq-theme', t); } catch (e) {} }, theme);
    const p = await c.newPage(), errs = [];
    p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    p.on('request', r => { if (!/^(file|data|blob):/.test(r.url())) ext.push(r.url()); });
    await p.goto(%s + '#/leaderboard'); await p.waitForTimeout(900);
    const r = await p.evaluate(() => {
      const vw = document.documentElement.clientWidth, sec = document.querySelector('.route:not([hidden])');
      const small = [...sec.querySelectorAll('a,button,select,input,summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.width < 44 || r.height < 44) && !e.closest('p:not(.eyebrow),td,dd,figcaption'); }).map(e => e.className || e.tagName);
      const wide = [...sec.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > vw + 1; }).map(e => e.tagName + '.' + e.className);
      const bg = getComputedStyle(sec.querySelector('h1')).color;  // the ink follows the theme
      const crumb = sec.querySelector('.eyebrow .parent a').getBoundingClientRect();
      return { id: sec.id, hs: document.documentElement.scrollWidth > vw, small, wide, bg, crumb: crumb.height,
               rows: sec.querySelectorAll('table.lbtable tbody tr').length,
               label: getComputedStyle(sec.querySelector('table.lbtable td:not(.rk)'), '::before').content };
    });
    out.push({ w, theme, errs, ...r }); await c.close();
  }
  console.log(JSON.stringify({ out, ext })); await b.close();
})();
""" % (json.dumps(PLAYWRIGHT), json.dumps(CHROMIUM), json.dumps(url)))
    res = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr
    data = json.loads(res.stdout.strip().splitlines()[-1])
    assert data["ext"] == []
    bgs = {}
    for r in data["out"]:
        assert r["errs"] == [] and r["id"] == "route-leaderboard", r
        assert not r["hs"] and r["wide"] == [], r
        assert r["small"] == [] and r["crumb"] >= 44, r
        assert r["rows"] == len(RESULTS["entries"])
        if r["w"] == 390:
            assert r["label"].strip('"') == "Youden J"  # each phone cell names its column
        bgs[(r["w"], r["theme"])] = r["bg"]
    assert bgs[(390, "dark")] != bgs[(390, "light")]


def test_the_docs_claim_about_the_floor_matches_the_table():
    fl = RESULTS["floor"]
    for doc in (ROOT / "README.md", L.LB_DIR / "README.md"):
        text = " ".join(doc.read_text().split())
        assert ("cannot show that the Probes beat it" in text) == (fl["verdict"] == "not_shown"), doc
        assert "Probes do not beat it" not in text
    top = " ".join((ROOT / "README.md").read_text().split())
    assert ("puts the floor ahead by a ΔJ whose interval includes zero" in top) == (
        fl["verdict"] == "not_shown" and fl["paired"]["delta_j"] > 0)

"""The real-TOI leaderboard: its scoring reproduces the benchmark report, and it refuses what it should."""

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from exoplan import leaderboard as L
from exoplan.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT = "/opt/node22/lib/node_modules/playwright"
CHROMIUM = "/opt/pw-browsers/chromium"
HAVE_BROWSER = shutil.which("node") is not None and Path(PLAYWRIGHT).exists() and Path(CHROMIUM).exists()

SAMPLE = L.load_sample()
BENCH = json.loads(L.BENCHMARK.read_text())
INPUTS = json.loads(L.INPUTS.read_text())
SUBS = {s["id"]: s for s in L.load_submissions()}
RESULTS = json.loads(L.RESULTS.read_text())


def _score(sid):
    return L.score(SUBS[sid], SAMPLE, INPUTS, BENCH)


def _kn(r):
    return (r["k"], r["n"])


# ---------- the public inputs ----------
def test_public_inputs_are_the_committed_file_and_carry_no_held_out_label():
    assert INPUTS == L.public_inputs(SAMPLE)
    assert L.inputs_sha256(INPUTS) == RESULTS["inputs_sha256"]
    assert INPUTS["sample_sha256"] == SAMPLE["sha256"] == RESULTS["sample_sha256"]
    held = INPUTS["held_out"]
    assert len(held) == sum(1 for t in SAMPLE["tois"] if t["half"] == "held_out") == 345
    for t in held:
        assert set(t) == set(L.HELD_OUT_PUBLIC)
        assert not set(t) & {"class", "disposition", "depth_ppm", "radius_re"}
    assert all(t["half"] == "tuning" and "class" in t for t in INPUTS["tuning"])
    assert L.inputs_sha256(INPUTS) != L.full_sample_sha256(SAMPLE)


# ---------- the seeded entries reproduce the benchmark report ----------
def test_probes_entry_scores_equal_the_benchmark_reports_held_out_numbers():
    s, h = _score("probes"), BENCH["summary"]["held_out"]
    assert _kn(s["completeness"]) == _kn(h["completeness"])
    assert _kn(s["completeness_all_stars"]) == _kn(h["completeness_all_stars"])
    assert _kn(s["fp_found"]) == _kn(h["fp_seen"])
    assert _kn(s["fp_flagged_of_found"]) == _kn(h["fp_flagged_of_seen"])
    assert _kn(s["fa_found"]) == _kn(h["fa_seen"])
    # FP rejection: every searched FP star that is not a clean candidate (not found, or found and flagged).
    assert s["fp_rejection"]["n"] == h["fp_seen"]["n"]
    assert s["fp_rejection"]["k"] == h["fp_seen"]["n"] - (h["fp_seen"]["k"] - h["fp_flagged_of_seen"]["k"])
    for a, b in zip(s["completeness_by_radius"], h["completeness_by_radius"]):
        assert a["bin"] == b["bin"] and _kn(a) == _kn(b)
        assert a["lo"] == pytest.approx(b["lo"]) and a["hi"] == pytest.approx(b["hi"])
    for v in ("inverted", "scrambled"):
        c, hc = s["controls"][v], h["controls"][v]
        assert c["star_sectors"] == hc["star_sectors"] and c["vetted_false_alarms"] == hc["vetted_false_alarms"]
        assert c["per_1000_star_sectors"] == pytest.approx(hc["per_1000_star_sectors"])
        assert _kn(c["stars_with_any"]) == _kn(hc["stars_with_any"])
    assert s["completeness"]["lo"] == pytest.approx(h["completeness"]["lo"])
    assert s["completeness"]["hi"] == pytest.approx(h["completeness"]["hi"])


def test_sentinel_entries_equal_the_benchmark_reports_persona_numbers():
    per = BENCH["sentinels"]["personas"]
    for pid in ("claude-volunteer", "claude-skeptic"):
        s = _score(pid)
        assert _kn(s["completeness"]) == _kn(per[pid]["cp_kp_marked"])
        fp = per[pid]["fp_marked_as_planet"]
        assert s["fp_rejection"]["n"] == fp["n"] and s["fp_rejection"]["k"] == fp["n"] - fp["k"]
        assert s["controls"] == {"inverted": None, "scrambled": None}
        assert [p["toi"] for p in SUBS[pid]["predictions"]] == BENCH["sentinels"]["subsample"]
    a, b = SUBS["claude-volunteer"]["predictions"], SUBS["claude-skeptic"]["predictions"]
    agree = sum(x["recovered"] == y["recovered"] for x, y in zip(a, b))
    assert (agree, len(a)) == (BENCH["sentinels"]["agreement"]["agree"], BENCH["sentinels"]["agreement"]["n"])


def test_probes_on_the_subsample_are_the_held_out_rows_restricted():
    held = {p["toi"]: p for p in SUBS["probes"]["predictions"]}
    for p in SUBS["probes-subsample"]["predictions"]:
        assert p == held[p["toi"]]


def test_the_combinations_follow_their_stated_rules():
    pr = {p["toi"]: p for p in SUBS["probes-subsample"]["predictions"]}
    se = [{p["toi"]: p for p in SUBS[s]["predictions"]} for s in ("claude-volunteer", "claude-skeptic")]
    clean = lambda p: p["recovered"] and not p["flagged"]  # noqa: E731
    for rule, sid in (("or", "probes-or-sentinel"), ("and", "probes-and-sentinel")):
        for p in SUBS[sid]["predictions"]:
            hit = any(s[p["toi"]]["recovered"] for s in se)
            want = (clean(pr[p["toi"]]) or hit) if rule == "or" else (clean(pr[p["toi"]]) and hit)
            assert clean(p) == want, (sid, p["toi"])


def test_committed_table_is_the_scoring_of_the_committed_submissions():
    res = L.build(SAMPLE, INPUTS, BENCH, L.load_submissions())
    assert res == RESULTS
    assert (L.LB_DIR / "leaderboard.md").read_text() == L.to_markdown(res)
    assert res["refused"] == [] and {e["id"] for e in res["entries"]} == set(SUBS)
    names = {e["name"] for e in res["entries"]}
    assert {"Probes only", "Sentinel · Volunteer alone", "Sentinel · Skeptic alone", "Probes + Sentinels (either)",
            "Probes + Sentinels (both)"} <= names
    # Equal completeness shares a rank.
    sub = [e for e in res["entries"] if e["scope"] == "sentinel_subsample"]
    for a in sub:
        for b in sub:
            if a["scores"]["completeness_all_stars"]["k"] == b["scores"]["completeness_all_stars"]["k"]:
                assert a["rank"] == b["rank"]


def test_every_seeded_entry_carries_provenance_and_the_attribution():
    for s in SUBS.values():
        assert s["tuned_on"] == "none" and s["inputs_sha256"] == L.inputs_sha256(INPUTS)
        assert "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors." in s["provenance"]["method"]
        assert "76de67d" in s["provenance"]["code_version"]
        assert s["provenance"]["generated_from"][0]["file"] == "docs/results/benchmark_real_tois.json"


# ---------- refusals ----------
def _refused(mutate):
    sub = copy.deepcopy(SUBS["probes"])
    mutate(sub)
    with pytest.raises(L.Refused) as exc:
        L.score(sub, SAMPLE, INPUTS, BENCH)
    return " ".join(exc.value.reasons)


def test_refuses_a_submission_built_from_the_full_sample_with_held_out_labels():
    why = _refused(lambda s: s.update(inputs_sha256=L.full_sample_sha256(SAMPLE)))
    assert "held-out labels" in why
    why = _refused(lambda s: s.update(inputs_sha256=SAMPLE["sha256"]))
    assert "held-out labels" in why


def test_refuses_any_other_inputs_hash_or_sample_hash():
    assert "public tuning-half-only inputs" in _refused(lambda s: s.update(inputs_sha256="0" * 64))
    assert "frozen sample" in _refused(lambda s: s.update(sample_sha256="0" * 64))


def test_refuses_tuning_on_the_held_out_half():
    assert "touches held-out labels" in _refused(lambda s: s.update(tuned_on="held_out"))
    assert "touches held-out labels" in _refused(lambda s: s.update(tuned_on="all"))


def test_refuses_label_fields_in_predictions():
    def add(s):
        s["predictions"][0]["class"] = "positive"
    assert "label fields" in _refused(add)

    def nested(s):
        s["predictions"][3]["extra"] = {"tfopwg_disp": "FP"}
    assert "label fields" in _refused(nested)


def test_refuses_missing_extra_duplicate_and_tuning_stars():
    assert "no prediction for 1" in _refused(lambda s: s["predictions"].pop())
    assert "duplicate" in _refused(lambda s: s["predictions"].append(dict(s["predictions"][0])))
    tun = next(t for t in SAMPLE["tois"] if t["half"] == "tuning")
    row = {"toi": tun["toi"], "tic": tun["tic"], "searched": False, "seen": False, "recovered": False, "flagged": False}
    assert "tuning-half" in _refused(lambda s: s["predictions"].append(row))
    assert "outside the scope" in _refused(lambda s: s["predictions"].append(dict(row, toi="99999.01")))

    def wrong_tic(s):
        s["predictions"][0]["tic"] = 1
    assert "is not the sample's" in _refused(wrong_tic)


def test_refuses_inconsistent_outcomes_and_missing_provenance():
    def rec_unseen(s):
        p = next(p for p in s["predictions"] if p["searched"])
        p.update(seen=False, recovered=True)
    assert "needs seen" in _refused(rec_unseen)

    def unsearched_seen(s):
        p = next(p for p in s["predictions"] if p["searched"])
        p.update(searched=False, seen=True)
    assert "cannot be seen" in _refused(unsearched_seen)

    def neg(s):
        p = next(p for p in s["predictions"] if p["searched"])
        p["controls"]["inverted"] = -1
    assert "non-negative" in _refused(neg)
    assert "provenance must state" in _refused(lambda s: s["provenance"].pop("code_version"))
    assert "format" in _refused(lambda s: s.update(format="other/1"))
    assert "scope" in _refused(lambda s: s.update(scope="everything"))


def test_a_valid_outside_submission_is_scored():
    sub = copy.deepcopy(SUBS["probes"])
    sub.update(id="someone", name="Someone's method", tuned_on="tuning")
    for p in sub["predictions"]:
        if p["searched"]:
            p.update(seen=True, recovered=True, flagged=False)
    s = L.score(sub, SAMPLE, INPUTS, BENCH)
    assert _kn(s["completeness"]) == (BENCH["summary"]["held_out"]["completeness"]["n"],) * 2 and s["fp_rejection"]["k"] == 0


def test_cli_scores_and_refuses(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(SUBS["probes"]))
    assert cli_main(["leaderboard", str(good)]) == 0
    assert json.loads(capsys.readouterr().out)["scores"]["completeness"]["k"] == BENCH["summary"]["held_out"]["completeness"]["k"]
    bad = copy.deepcopy(SUBS["probes"])
    bad["inputs_sha256"] = L.full_sample_sha256(SAMPLE)
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    assert cli_main(["leaderboard", str(tmp_path / "bad.json")]) == 2
    assert "held-out labels" in capsys.readouterr().err


# ---------- the threshold sweep is not the leaderboard ----------
def test_the_threshold_sweep_is_renamed_and_points_here():
    assert not (ROOT / "docs/leaderboard.md").exists() and not (ROOT / "docs/leaderboard.json").exists()
    sweep = (ROOT / "docs/threshold_sweep.md").read_text()
    assert sweep.startswith("# Threshold sweep") and "leaderboard/leaderboard.md" in sweep
    assert "threshold_sweep.md" in (ROOT / "scripts/improve.py").read_text()
    assert "threshold_sweep.md" in (L.LB_DIR / "leaderboard.md").read_text()
    assert "docs/threshold_sweep.md" in (ROOT / "README.md").read_text()


# ---------- the app's #/leaderboard ----------
def _route(page, rid):
    return re.search(rf'<section class="route" id="route-{rid}".*?(?=<section class="route" id="route-)', page, re.S).group(0)


def test_app_leaderboard_route_shows_the_table_rules_and_hash(pi_men_app):
    page = pi_men_app.read_text()
    sec = _route(page, "leaderboard")
    assert 'id="h-leaderboard"' in sec and '<a href="#/sentinels">' in sec
    assert RESULTS["sample_sha256"] in sec and RESULTS["inputs_sha256"] in sec
    assert sec.count("<tr><td class=\"rk\"") == len(RESULTS["entries"])
    c = BENCH["summary"]["held_out"]["completeness_all_stars"]
    assert f"{c['k']}/{c['n']}" in sec and "Rules" in sec and "not measured" in sec
    assert "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors." in sec
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
    await c.addInitScript(t => { try { localStorage.setItem('exoplan-theme', t); } catch (e) {} }, theme);
    const p = await c.newPage(), errs = [];
    p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    p.on('request', r => { if (!/^(file|data|blob):/.test(r.url())) ext.push(r.url()); });
    await p.goto(%s + '#/leaderboard'); await p.waitForTimeout(900);
    const r = await p.evaluate(() => {
      const vw = document.documentElement.clientWidth, sec = document.querySelector('.route:not([hidden])');
      const small = [...sec.querySelectorAll('a,button,select,input,summary')].filter(e => { const r = e.getBoundingClientRect(); return r.width && (r.width < 44 || r.height < 44) && !e.closest('p,td,dd,figcaption'); }).map(e => e.className || e.tagName);
      const wide = [...sec.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect(); return r.width && r.right > vw + 1; }).map(e => e.tagName + '.' + e.className);
      const bg = getComputedStyle(document.body).backgroundColor, ink = getComputedStyle(sec.querySelector('h1')).color;
      return { id: sec.id, hs: document.documentElement.scrollWidth > vw, small, wide, bg, ink,
               rows: sec.querySelectorAll('table.lbtable tbody tr').length, label: getComputedStyle(sec.querySelector('table.lbtable td:not(.rk)'), '::before').content };
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
        assert r["small"] == [], r
        assert r["rows"] == len(RESULTS["entries"])
        if r["w"] == 390:
            assert r["label"].strip('"').startswith("Completeness")  # each phone cell names its column
        bgs[(r["w"], r["theme"])] = (r["bg"], r["ink"])
    assert bgs[(390, "dark")] != bgs[(390, "light")]

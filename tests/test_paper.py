"""The methods paper: every number comes from the committed JSON, and the pending results stay pending."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import paper_numbers as PN  # noqa: E402
from setuhq.benchmark_toi import wilson  # noqa: E402

PAPER = (ROOT / "docs/paper/paper.md").read_text()
FLAT = " ".join(PAPER.split())  # line breaks in the prose do not matter
TEMPLATE = (ROOT / "docs/paper/paper.template.md").read_text()
B = json.loads((ROOT / "docs/results/benchmark_real_tois.json").read_text())
PM = json.loads((ROOT / "docs/results/pi_men_validation.json").read_text())
REFS = json.loads((ROOT / "docs/paper/references.json").read_text())
H = B["summary"]["held_out"]


def pct(r):
    """The paper's rate format, rebuilt here from the JSON independently of the script."""
    return f"{100 * r['rate']:.0f}% ({r['k']}/{r['n']}; 95% CI {100 * r['lo']:.0f}–{100 * r['hi']:.0f}%)"


@pytest.fixture(scope="module")
def built():
    return PN.build(ROOT)


def test_committed_paper_and_numbers_are_what_the_json_gives(built):
    paper, nums = built
    assert PAPER == paper, "docs/paper/paper.md is out of date: run python scripts/paper_numbers.py"
    assert (ROOT / "docs/paper/numbers.json").read_text() == nums
    assert "{{" not in FLAT and "}}" not in FLAT


def test_the_template_types_no_result():
    """Rates, k/n counts and decimals reach the paper only through placeholders."""
    body = re.sub(r"<!--.*?-->", "", TEMPLATE, flags=re.S)
    body = PN.PLACEHOLDER.sub("", body).replace("95%", "")  # the interval level is a definition, not a result
    lines = [ln for ln in body.splitlines() if not ln.startswith("#")]
    text = re.sub(r"Section \d+\.\d+", "", "\n".join(lines))  # cross-references to sections
    assert re.findall(r"\d+(?:\.\d+)?\s?%", text) == []
    assert re.findall(r"\b\d+/\d+\b", text) == []
    assert re.findall(r"\b\d+\.\d+\b", text) == []


def test_headline_numbers_match_the_benchmark_json():
    for r in (H["completeness"], H["completeness_all_stars"], H["fp_seen"], H["fp_flagged_of_seen"], H["pos_flagged"],
              H["fa_seen"], B["summary_unaffected"]["held_out"]["completeness"]):
        assert pct(r) in FLAT, pct(r)
    for b in H["completeness_by_radius"] + H["completeness_by_period"]:
        assert pct(b) in FLAT
    small = [b for b in H["completeness_by_radius"] if b["bin"][1] <= 4]
    k, n = sum(b["k"] for b in small), sum(b["n"] for b in small)
    p, lo, hi = wilson(k, n)
    assert pct({"k": k, "n": n, "rate": p, "lo": lo, "hi": hi}) in FLAT
    for v in ("inverted", "scrambled"):
        c = H["controls"][v]
        assert f"| {c['vetted_false_alarms']} over {c['star_sectors']} " in FLAT and pct(c["stars_with_any"]) in FLAT
        assert f"| {H['feed'][v]['new_signals_per_1000']:.0f} |" in FLAT
    imp = B["feed_implication"]
    assert f"{imp['expected_false_per_100_targets']:.1f}" in FLAT and f"{imp['live_new_signals_per_100_targets']:.1f}" in FLAT
    assert B["code_commit"] in FLAT and B["sample"]["sha256"] in FLAT


def test_negative_results_are_reported_with_their_numbers():
    se = B["sentinels"]
    assert "consistent with noise" in FLAT
    assert "**Completeness is low for small planets.**" in FLAT
    assert "**The two personas are correlated.**" in FLAT
    assert f"They agree on {se['agreement']['agree']} of {se['agreement']['n']} stars (φ = {se['agreement']['phi']:.2f})" in FLAT
    for pid in ("claude-volunteer", "claude-skeptic"):
        assert pct(se["personas"][pid]["cp_kp_marked"]) in FLAT and pct(se["personas"][pid]["fp_marked_as_planet"]) in FLAT
    assert "class skew" in FLAT.lower()
    loss = B["loss"]["held_out"]
    assert f"describe {loss['fp']['data']} of {loss['fp']['n']} held-out FP TOIs" in FLAT
    cl = B["clipping"]["held_out"]
    assert "A known bug in the code that produced these numbers" in FLAT
    assert f"{cl['affected']['positive']} CP/KP, {cl['affected']['fp']} FP and {cl['affected']['fa']} FA stars" in FLAT
    assert ", ".join(cl["explained_tois"]) in FLAT


def test_pi_men_numbers_match_the_validation_json():
    jf, jp = PM["joint_fit"], PM["joint_fit_density_prior"]
    assert f"Rp/R★ = {jf['k']:.4f} ± {jf['k_err']:.4f} (ratio {PM['ratios_vs_huang_2018']['k']:.2f}" in FLAT
    assert f"T14 = {jf['t14_hours']:.2f} ± {jf['t14_err_hours']:.2f} h (ratio {PM['ratios_vs_huang_2018']['duration']:.2f}" in FLAT
    assert f"b = {jp['b']:.2f} ± {jp['b_err']:.2f}" in FLAT and f"Huang's {PM['huang_2018']['pl_imppar']:.2f}" in FLAT


def test_leaderboard_numbers_match_the_leaderboard_json():
    lb = json.loads((ROOT / "docs/leaderboard/leaderboard.json").read_text())
    from setuhq.leaderboard import jtext

    for e in lb["entries"]:
        s = e["scores"]
        for k in ("completeness_clean_searchable", "fp_rejection_searchable", "reliability"):
            assert pct(s[k]) in FLAT, (e["id"], k)
        assert jtext(s["youden_j"]) in FLAT and jtext(s["youden_j_all_stars"]) in FLAT
    assert lb["floor_note"] in FLAT
    assert "do not beat" not in FLAT


def test_the_paper_floor_sentence_changes_with_the_paired_interval(tmp_path):
    from setuhq import leaderboard as LBm

    root = _tmp_root(tmp_path)
    path = root / "docs/leaderboard/leaderboard.json"
    data = json.loads(path.read_text())
    data["floor"]["paired"].update(delta_j=-0.2, lo=-0.33, hi=-0.07)
    data["floor"]["verdict"] = "probes_ahead"
    data["floor_note"] = LBm.floor_note(data["floor"])
    path.write_text(json.dumps(data))
    paper = " ".join(PN.build(root)[0].split())
    assert "The Probes are significantly ahead of the metadata-only floor" in paper
    assert "cannot show" not in paper and "mostly measures how separable" not in paper
    data["floor"]["verdict"] = "floor_ahead"  # inconsistent with the interval: the script refuses
    path.write_text(json.dumps(data))
    with pytest.raises(PN.ClaimFailed, match="paired"):
        PN.build(root)


def test_pending_results_print_pending_never_a_guess():
    for spec in PN.PENDING.values():
        if not (ROOT / spec["file"]).exists():  # a file that exists fills them (next test)
            assert f"*pending: {spec['label']}*" in FLAT
            assert f"`{spec['file']}`" in FLAT  # the pending section names where the result will come from


def test_pending_results_fill_from_their_file_when_it_exists(tmp_path):
    clip = tmp_path / PN.PENDING["clipfix"]["file"]
    clip.parent.mkdir(parents=True)
    r = {"k": 70, "n": 150, "rate": 70 / 150, "lo": 0.39, "hi": 0.55}
    clip.write_text(json.dumps({"summary": {"held_out": {"completeness": r, "fp_seen": r, "fp_flagged_of_seen": r,
                                                          "feed": {"inverted": {"new_signals_per_1000": 12.0},
                                                                   "scrambled": {"new_signals_per_1000": 20.4}}}},
                                "code_commit": "abcdef0123"}))
    feed = tmp_path / PN.PENDING["feedrule"]["file"]
    feed.write_text(json.dumps({"rule": "both sectors"}))  # keys missing: those stay pending, named
    out, status = PN.pending_numbers(tmp_path)
    assert out["clipfix_completeness"] == "47% (70/150; 95% CI 39–55%)" and out["clipfix_code"] == "abcdef0"
    assert out["clipfix_feed_scrambled"] == "20" and status["clipfix"]["filled"]
    assert out["feedrule_rule"] == "both sectors" and not status["feedrule"]["filled"]
    assert out["feedrule_inverted"].startswith("*pending: stricter feed rule (no `held_out.inverted")
    assert out["pixel_fp_flagged"] == "*pending: S2 pixel vetting*"
    n, _ = PN.numbers(ROOT)
    n.update(out)
    paper = PN.render(TEMPLATE, n)
    assert "47% (70/150; 95% CI 39–55%)" in paper and "*pending: clipping-fixed re-run*" not in paper


def test_every_doi_was_resolved_and_every_value_checked_in_its_paper():
    dois = set(re.findall(r"doi:\[([^\]]+)\]", PAPER))
    known = {v["doi"] for v in REFS["refs"].values() if v["doi"]}
    assert dois == known
    assert all(v["source"] == ("web" if not v["doi"] else "crossref") for v in REFS["refs"].values())
    assert "atlas" not in json.dumps(REFS).lower()
    # Every published value cites a reference in the list, records where it was checked, and has a number to compare.
    for k, v in REFS["values"].items():
        assert v["ref"] in REFS["refs"] and v["verified"] and isinstance(v["value"], (int, float)), k
    assert REFS["values"]["pht_mid"]["value"] == 0.51 and REFS["values"]["pht_large"]["value"] == 0.85
    # Every reference is cited in the text, except through the bibliography alone.
    for k, v in REFS["refs"].items():
        if k != "phcheops":
            assert v["cite"] in FLAT.split("## References")[0], k


def test_wording_rules():
    assert "SuperIntelligence" not in FLAT and "Superintelligence" not in FLAT
    assert "Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors." in FLAT
    for bad in ("we discovered", "setuhq discovered", "we confirm", "new planet", "newly discovered"):
        assert bad not in FLAT.lower(), bad
    assert "aastex631" in FLAT and "Markdown only" in FLAT


SAMPLE = {t["toi"]: t for t in json.loads((ROOT / "docs/results/benchmark_toi_sample.json").read_text())["tois"]}
HELD_POS = [r for r in B["per_star"] if r.get("real") and SAMPLE[r["toi"]]["half"] == "held_out"
            and SAMPLE[r["toi"]]["class"] == "positive"]


def test_recovered_signals_are_counted_from_the_per_star_rows():
    rec = [r for r in HELD_POS if r["real"]["recovered"]]
    at_p = sum(r["real"]["period_alias"] == "P" for r in rec)
    none = sum(r["real"]["period_alias"] is None for r in rec)
    assert len(rec) == H["completeness"]["k"] and len(HELD_POS) == H["completeness"]["n"]
    assert (f"Of the {len(HELD_POS)} searchable CP/KP TOIs, {len(rec)} were recovered ({at_p} on a periodic signal at "
            "the TOI's period") in FLAT
    assert f"{none} without a period) and {len(HELD_POS) - len(rec)} were not" in FLAT


def test_planet_hunters_comparison_uses_its_own_radius_bins():
    def bin_rate(lo, hi):
        sel = [r for r in HELD_POS if SAMPLE[r["toi"]].get("radius_re") is not None and lo <= SAMPLE[r["toi"]]["radius_re"] < hi]
        k, n = sum(r["real"]["recovered"] for r in sel), len(sel)
        p, low, up = wilson(k, n)
        return pct({"k": k, "n": n, "rate": p, "lo": low, "hi": up})

    assert f"| completeness, 3 to 4 R⊕ | {bin_rate(3, 4)} | Planet Hunters TESS: 51%" in FLAT
    assert f"| completeness, above 4 R⊕ | {bin_rate(4, float('inf'))} | Planet Hunters TESS: 85%" in FLAT
    assert "vetting alone, on injected transits already detected as TCEs" in FLAT
    assert "atlas" not in re.sub(r"<!--.*?-->", "", PAPER, flags=re.S).split("## References")[0].lower()


def test_the_feed_estimate_is_called_an_approximation():
    assert "This estimate is an approximation" in FLAT


def _tmp_root(tmp_path):
    for rel in ("docs/results/benchmark_real_tois.json", "docs/results/pi_men_validation.json",
                "docs/results/injection_recovery_simulated_panel.md", "docs/results/reviewer_weights_full_panel.calibration.json",
                "docs/results/benchmark_toi_sample.json", "docs/leaderboard/leaderboard.json", "docs/paper/references.json",
                "docs/paper/paper.template.md", "configs/default.toml", "configs/discovery.toml",
                "docs/results/feed_rule_validation.json",
                "runs/tess-pi-men-s1/candidates.json"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / rel).read_bytes())
    return tmp_path


@pytest.mark.parametrize("what", ["correlated voter", "noise", "'bad' verdict", "skewed toward FP"])
def test_qualitative_claims_fail_or_change_when_the_data_stops_supporting_them(tmp_path, what):
    root = _tmp_root(tmp_path)
    assert PN.build(root)[0] == PAPER  # an exact copy renders the committed paper
    path = root / "docs/results/benchmark_real_tois.json"
    data = json.loads(path.read_text())
    if what == "correlated voter":
        data["sentinels"]["agreement"]["phi"] = 0.4
    elif what == "noise":
        data["feed_implication"].update(expected_false_per_100_targets=2.0, bad=False)
    elif what == "'bad' verdict":
        data["feed_implication"]["bad"] = False
    else:
        data["loss"]["held_out"]["fp"]["not_searchable"] = 2
    path.write_text(json.dumps(data))
    if what == "noise":  # below one half the sentence changes instead of failing
        paper = " ".join(PN.build(root)[0].split())
        assert "less than half" in paper and "more likely noise than a signal" not in paper
        return
    with pytest.raises(PN.ClaimFailed, match=what):
        PN.build(root)


def test_the_planet_hunters_comparison_is_stated_by_significance():
    def bin_rate(lo, hi):
        sel = [r for r in HELD_POS if SAMPLE[r["toi"]].get("radius_re") is not None and lo <= SAMPLE[r["toi"]]["radius_re"] < hi]
        k, n = sum(r["real"]["recovered"] for r in sel), len(sel)
        return wilson(k, n)

    for (lo, hi), ref, label in (((3, 4), 0.51, "3 to 4 R⊕"), ((4, float("inf")), 0.85, "above 4 R⊕")):
        _, low, up = bin_rate(lo, hi)
        word = "significantly below" if up < ref else "significantly above" if low > ref else "consistent with"
        assert f"{label}, {word} Planet Hunters TESS's rate" in FLAT
    assert "in every comparable row" not in FLAT


def test_an_empty_comparison_bin_fails_loudly_not_with_a_type_error(tmp_path):
    root = _tmp_root(tmp_path)
    path = root / "docs/results/benchmark_toi_sample.json"
    data = json.loads(path.read_text())
    for t in data["tois"]:
        if t.get("radius_re") is not None and 3 <= t["radius_re"] < 4:
            t["radius_re"] = None
    path.write_text(json.dumps(data))
    with pytest.raises(PN.ClaimFailed, match="no stars in the bin"):
        PN.build(root)
